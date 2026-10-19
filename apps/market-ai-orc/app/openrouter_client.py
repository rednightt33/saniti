from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from typing import Any

import httpx


OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
NON_RETRYABLE_429_CODES = {"credit_balance_exhausted", "insufficient_quota"}
RETRYABLE_STATUS_CODES = {408, 409, 429}
MAX_ATTEMPTS = 2  # at most one retry of an explicit transient HTTP refusal
# M160 (user 2026-10-15, "Ok, confirmed. Go."): a refusal of the account (key revoked, no credit, key limit reached)
# is not a refusal of one request. HTTP 401 and 402 say so themselves; for any other refusal the key's own record
# (GET /key, limit_remaining) decides, so a provider's wording or status for "limit reached" needs no list here.
ACCOUNT_STATUS_CODES = {401, 402}
# Codes after which no model call of any request can succeed for now: the run ends with one plain line and the
# routers do not ask the user back. A timeout or a refused request stays the request's own failure.
SERVICE_DOWN_CODES = {"PROVIDER_ACCOUNT_BLOCKED", "PROVIDER_QUOTA_EXHAUSTED", "PROVIDER_UNAVAILABLE"}
# After an account refusal the client sends nothing for this long, then lets one call through as the probe.
BREAKER_SECONDS = 120.0
TRANSPORT_HEADERS = frozenset({"content-encoding", "content-length", "transfer-encoding"})
KEY_STATUS_TTL_SECONDS = 60.0
logger = logging.getLogger("market_ai_orc")


def _log(event: str, **fields: Any) -> None:
    logger.info(json.dumps({"event": event, **fields}, default=str))


class ProviderError(RuntimeError):
    """Normalized OpenRouter failure. The message never contains credentials or headers."""

    def __init__(self, message: str, *, code: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code

    @property
    def service_down(self) -> bool:
        """M160: no model call can succeed for now (account refused, or the provider down after every retry)."""
        return self.code in SERVICE_DOWN_CODES


def response_usage(response: dict[str, Any]) -> dict[str, Any]:
    """Token usage of one provider response, including provider-side prompt caching.

    OpenRouter reports cache activity in usage.input_tokens_details (Responses API) or
    usage.prompt_tokens_details (Chat Completions): cached_tokens were read from the provider's cache,
    cache_write_tokens were written to it. input_tokens counts every prompt token, cached or not, so
    fresh_input_tokens = input_tokens - cached_input_tokens is what was processed without a cache hit.
    cache_metrics_reported tells a reported zero apart from a response without cache metrics. cost is
    OpenRouter's charged amount for the call (usage.cost), or None when the response has none.
    """
    usage = response.get("usage") or {}
    output_details = usage.get("output_tokens_details") or usage.get("completion_tokens_details") or {}
    input_details = usage.get("input_tokens_details") or usage.get("prompt_tokens_details")
    details = input_details if isinstance(input_details, dict) else {}
    input_tokens = int(usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0)
    output_tokens = int(usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0)
    cached = int(details.get("cached_tokens", 0) or 0)
    cost = usage.get("cost")
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "reasoning_tokens": int(output_details.get("reasoning_tokens", 0) or 0),
        "total_tokens": int(usage.get("total_tokens", 0) or 0) or input_tokens + output_tokens,
        "cached_input_tokens": cached,
        "cache_write_tokens": int(details.get("cache_write_tokens", 0) or 0),
        "fresh_input_tokens": max(input_tokens - cached, 0),
        "cache_metrics_reported": "cached_tokens" in details,
        "cost": float(cost) if isinstance(cost, (int, float)) and not isinstance(cost, bool) else None,
    }


def output_cut_reason(response: dict[str, Any], cap: int) -> str | None:
    """Provider completion flags take precedence over parseable JSON and absent/inexact token usage."""
    details = response.get("incomplete_details") or {}
    reason = details.get("reason") if isinstance(details, dict) else None
    finish = response.get("finish_reason")
    for choice in response.get("choices") or []:
        if isinstance(choice, dict) and choice.get("finish_reason"):
            finish = choice["finish_reason"]
    if reason in ("max_output_tokens", "max_tokens", "length") or finish in ("length", "max_tokens"):
        return "OUTPUT_BUDGET_EXHAUSTED"
    if response_usage(response)["output_tokens"] >= cap:
        return "OUTPUT_BUDGET_EXHAUSTED"
    if response.get("status") in ("incomplete", "failed", "cancelled") or reason or response.get("error") \
            or finish in ("content_filter", "error", "cancelled"):
        return "PROVIDER_INCOMPLETE"
    if any(isinstance(item, dict) and item.get("status") == "incomplete" for item in response.get("output") or []):
        return "PROVIDER_INCOMPLETE"
    return None


class OpenRouterClient:
    """OpenRouter Responses transport with bounded retry and no provider-side storage."""

    def __init__(
        self,
        api_key: str,
        timeout_seconds: int,
        *,
        x_title: str = "Saniti Market AI",
        http_referer: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-Title": x_title,
        }
        if http_referer:
            headers["HTTP-Referer"] = http_referer
        self.client = httpx.Client(
            base_url=OPENROUTER_BASE_URL,
            headers=headers,
            timeout=httpx.Timeout(timeout_seconds),
            transport=transport,
        )
        self.timeout_seconds = timeout_seconds
        self._response_transport = transport
        self._lock = threading.Lock()
        self._blocked_until = 0.0
        self._blocked_reason = ""
        self._key_status: tuple[float, dict[str, Any] | None] | None = None

    def key_status(self, *, max_age: float = KEY_STATUS_TTL_SECONDS) -> dict[str, Any] | None:
        """M160: the key's own record from OpenRouter (limit, limit_remaining, usage), cached max_age seconds; None on
        any failure. It costs no credit."""
        now = time.monotonic()
        cached = self._key_status
        if cached is not None and now - cached[0] < max_age:
            return cached[1]
        data = None
        try:
            response = self.client.get("/key", timeout=15.0)
            if response.status_code == 200:
                body = response.json().get("data")
                data = body if isinstance(body, dict) else None
        except (httpx.HTTPError, AttributeError, ValueError):
            data = None
        self._key_status = (now, data)
        return data

    def _account_refused(self, status_code: int) -> bool:
        if status_code in ACCOUNT_STATUS_CODES:
            return True
        record = self.key_status(max_age=0)
        remaining = record.get("limit_remaining") if record else None
        return isinstance(remaining, (int, float)) and remaining <= 0

    def _open_breaker(self, error: ProviderError) -> None:
        with self._lock:
            self._blocked_until = time.monotonic() + BREAKER_SECONDS
            self._blocked_reason = error.code
        _log("ai_provider_breaker_open", code=error.code, status_code=error.status_code, seconds=BREAKER_SECONDS)

    def _check_breaker(self) -> None:
        with self._lock:
            if self._blocked_until <= 0:
                return
            if time.monotonic() < self._blocked_until:
                raise ProviderError("openrouter account refused recently; no call sent",
                                    code="PROVIDER_ACCOUNT_BLOCKED")
            self._blocked_until = 0.0  # the window passed: this call is the probe

    def _probe_passed(self) -> None:
        if self._blocked_reason:
            _log("ai_provider_breaker_closed", code=self._blocked_reason)
            self._blocked_reason = ""

    def close(self) -> None:
        self.client.close()

    @staticmethod
    def _error_detail(response: httpx.Response) -> tuple[str, str | None, str | None]:
        error_type: str | None = None
        error_code: str | None = None
        message: str | None = None
        try:
            body = response.json()
            error = body.get("error", {}) if isinstance(body, dict) else {}
            if isinstance(error, dict):
                error_type = str(error.get("type") or "") or None
                error_code = str(error.get("code") or "") or None
                message = str(error.get("message") or "") or None
        except (TypeError, ValueError):
            pass

        labels = "/".join(item for item in (error_type, error_code) if item)
        safe_message = " ".join((message or "request failed").split())[:500]
        request_id = response.headers.get("x-request-id")
        detail = f"openrouter HTTP {response.status_code}"
        if request_id:
            detail += f" (request_id={request_id})"
        if labels:
            detail += f" {labels}"
        return f"{detail}: {safe_message}", error_type, error_code

    def generation(self, generation_id: str) -> dict[str, Any] | None:
        """OpenRouter's record of one generation (provider_name, generation_time, native token counts), or None while
        it is not available yet (HTTP 404) or on any failure. One attempt; the caller decides whether to retry."""
        try:
            response = self.client.get("/generation", params={"id": generation_id})
        except httpx.HTTPError:
            return None
        if response.status_code != 200:
            return None
        try:
            data = response.json().get("data")
        except (AttributeError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    def model_endpoints(self, model: str) -> list[dict[str, Any]] | None:
        """OpenRouter's endpoints of one model (provider tag, pricing, supported parameters, uptime), or None on any
        failure. One attempt; CachePricePolicy keeps its last list when this fails."""
        try:
            response = self.client.get(f"/models/{model}/endpoints", timeout=15.0)
        except httpx.HTTPError:
            return None
        if response.status_code != 200:
            return None
        try:
            endpoints = (response.json().get("data") or {}).get("endpoints")
        except (AttributeError, ValueError):
            return None
        return [e for e in endpoints if isinstance(e, dict)] if isinstance(endpoints, list) else None

    def models(self) -> list[dict[str, Any]] | None:
        """EXEC-MODELS: OpenRouter's public model list (id, pricing per token, supported parameters), or None on any
        failure. One attempt; ModelPrices keeps its last prices when this fails."""
        try:
            response = self.client.get("/models", timeout=30.0)
        except httpx.HTTPError:
            return None
        if response.status_code != 200:
            return None
        try:
            listed = response.json().get("data")
        except (AttributeError, ValueError):
            return None
        return [m for m in listed if isinstance(m, dict)] if isinstance(listed, list) else None

    def create(self, payload: dict[str, Any], *, timeout: float | None = None,
               attempts: int | None = None) -> dict[str, Any]:
        """One operation, including any explicit HTTP retry, within the call and remaining run deadlines."""
        self._check_breaker()
        try:
            result = self._create(payload, timeout=timeout, attempts=attempts)
        except ProviderError as exc:
            if exc.code in ("PROVIDER_ACCOUNT_BLOCKED", "PROVIDER_QUOTA_EXHAUSTED"):
                self._open_breaker(exc)
            raise
        self._probe_passed()
        return result

    def _post_within(self, payload: dict[str, Any], timeout: float | None) -> httpx.Response:
        """Cancel the HTTP operation at its total deadline, including silence after earlier keep-alive bytes.

        The public client is synchronous (the API runs it in a worker thread). Async I/O here allows cancellation of
        a pending read; checking the clock only between sync chunks allowed another full timeout on each read.
        Metadata GETs keep the existing pooled synchronous client. No background inference thread outlives timeout.
        """
        seconds = float(timeout if timeout is not None else self.timeout_seconds)
        deadline = time.monotonic() + seconds

        async def post() -> httpx.Response:
            async with asyncio.timeout(seconds):
                async with httpx.AsyncClient(base_url=OPENROUTER_BASE_URL, headers=self.client.headers,
                                             timeout=seconds, transport=self._response_transport) as client:
                    async with client.stream("POST", "/responses", json=payload) as response:
                        chunks: list[bytes] = []
                        async for chunk in response.aiter_bytes():
                            chunks.append(chunk)
                            if time.monotonic() >= deadline:
                                raise TimeoutError
                        # M168: iterated bytes are decoded already, so do not decode compression a second time.
                        headers = [(k, v) for k, v in response.headers.multi_items()
                                   if k.lower() not in TRANSPORT_HEADERS]
                        return httpx.Response(response.status_code, headers=headers, content=b"".join(chunks),
                                              request=response.request)

        try:
            return asyncio.run(post())
        except TimeoutError as exc:
            _log("ai_provider_call_deadline", seconds=seconds)
            raise httpx.ReadTimeout(f"no complete response within {seconds:g} s") from exc

    def _create(self, payload: dict[str, Any], *, timeout: float | None, attempts: int | None) -> dict[str, Any]:
        from . import stop
        from . import progress, user_texts
        from .tools.request_data import current_request_id, current_run_deadline

        last_error: ProviderError | None = None
        seconds = min(float(timeout or self.timeout_seconds), float(self.timeout_seconds))
        deadline = min(time.monotonic() + seconds, current_run_deadline.get() or float("inf"))
        tries = min(max(1, attempts or MAX_ATTEMPTS), MAX_ATTEMPTS)
        for attempt in range(tries):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ProviderError("openrouter operation deadline reached; no new call sent", code="PROVIDER_TIMEOUT")
            if stop.requested():
                raise ProviderError("request stopped; no new call sent", code="STOPPED_BY_USER")
            _log("ai_provider_attempt", request_id=current_request_id.get(), attempt=attempt + 1,
                 model=payload.get("model"), sent_reasoning=payload.get("reasoning"),
                 max_output_tokens=payload.get("max_output_tokens"), remaining_seconds=round(remaining, 3))
            try:
                response = self._post_within(payload, remaining)
            except httpx.TimeoutException as exc:
                # An ambiguous interruption may already have consumed tokens. Never silently send it again.
                _log("ai_provider_attempt_interrupted", request_id=current_request_id.get(), attempt=attempt + 1,
                     code="PROVIDER_TIMEOUT", cost_status="UNKNOWN", retried=False)
                raise ProviderError("openrouter request timed out; not retried", code="PROVIDER_TIMEOUT") from exc
            except httpx.DecodingError as exc:
                # M168: a body that cannot be decoded is the provider's malformed answer, not retried (tokens may
                # already be spent) and never an exception that ends the run as INTERNAL_ERROR
                raise ProviderError("openrouter returned a body that cannot be decoded",
                                    code="PROVIDER_MALFORMED_RESPONSE") from exc
            except (httpx.NetworkError, httpx.RemoteProtocolError) as exc:
                _log("ai_provider_attempt_interrupted", request_id=current_request_id.get(), attempt=attempt + 1,
                     code="PROVIDER_NETWORK_ERROR", cost_status="UNKNOWN", retried=False)
                raise ProviderError(
                    f"openrouter network error: {type(exc).__name__}", code="PROVIDER_NETWORK_ERROR"
                ) from exc
            else:
                if 200 <= response.status_code < 300:
                    # A 2xx already consumed tokens, so a malformed body is not retried.
                    try:
                        result = response.json()
                    except ValueError as exc:
                        raise ProviderError(
                            "openrouter returned malformed JSON",
                            code="PROVIDER_MALFORMED_RESPONSE",
                            status_code=response.status_code,
                        ) from exc
                    if not isinstance(result, dict):
                        raise ProviderError(
                            "openrouter response was not a JSON object",
                            code="PROVIDER_MALFORMED_RESPONSE",
                            status_code=response.status_code,
                        )
                    result.pop("_executor_settings", None)  # reserved for the local manual-agent adapter only
                    return result
                detail, error_type, error_code = self._error_detail(response)
                refused = None
                if response.status_code == 429 and (
                    error_type in NON_RETRYABLE_429_CODES or error_code in NON_RETRYABLE_429_CODES
                ):
                    refused = "PROVIDER_QUOTA_EXHAUSTED"
                elif response.status_code not in RETRYABLE_STATUS_CODES and response.status_code < 500:
                    refused = ("PROVIDER_ACCOUNT_BLOCKED" if self._account_refused(response.status_code)
                               else "PROVIDER_REJECTED")
                if refused is not None:
                    _log("ai_provider_refused", code=refused, status_code=response.status_code,
                         error_type=error_type, error_code=error_code)
                    raise ProviderError(detail, code=refused, status_code=response.status_code)
                last_error = ProviderError(
                    detail, code="PROVIDER_UNAVAILABLE", status_code=response.status_code
                )
            if attempt < tries - 1:
                delay = 1.5 * (2 ** attempt)
                if time.monotonic() + delay >= deadline:
                    raise ProviderError("openrouter operation deadline reached before retry", code="PROVIDER_TIMEOUT")
                _log("ai_provider_retry", request_id=current_request_id.get(), attempt=attempt + 2,
                     status_code=response.status_code, remaining_seconds=round(deadline - time.monotonic(), 3))
                with progress.step(user_texts.PROGRESS_PROVIDER_RETRY):
                    time.sleep(delay)
        assert last_error is not None
        raise ProviderError(
            f"openrouter request failed after {tries} attempts: {last_error}",
            code=last_error.code,
            status_code=last_error.status_code,
        )


class CreditMonitor:
    """M160: reads the key's record (no credit used) at start and every interval_seconds in a daemon thread and logs
    ai_provider_credit; below low_usd remaining it also logs ai_provider_credit_low, so an empty key is seen before
    the readers meet it. A key without a limit reports no remaining amount and is only logged."""

    def __init__(self, client: OpenRouterClient, interval_seconds: int, low_usd: float) -> None:
        self.client = client
        self.interval_seconds = interval_seconds
        self.low_usd = low_usd
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, name="provider-credit", daemon=True)

    def start(self) -> None:
        if self.interval_seconds > 0:
            self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()

    def check(self) -> dict[str, Any] | None:
        record = self.client.key_status(max_age=0)
        if record is None:
            _log("ai_provider_credit_unknown")
            return None
        remaining = record.get("limit_remaining")
        fields = {"limit": record.get("limit"), "limit_remaining": remaining, "usage": record.get("usage"),
                  "usage_daily": record.get("usage_daily")}
        _log("ai_provider_credit", **fields)
        if isinstance(remaining, (int, float)) and remaining < self.low_usd:
            _log("ai_provider_credit_low", threshold=self.low_usd, **fields)
        return record

    def _run(self) -> None:
        while not self.stop_event.is_set():
            try:
                self.check()
            except Exception as exc:  # noqa: BLE001 - monitoring never stops the service
                _log("ai_provider_credit_unknown", error=type(exc).__name__)
            self.stop_event.wait(self.interval_seconds)
