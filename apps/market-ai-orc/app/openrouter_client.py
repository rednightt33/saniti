from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any

import httpx


OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
NON_RETRYABLE_429_CODES = {"credit_balance_exhausted", "insufficient_quota"}
RETRYABLE_STATUS_CODES = {408, 409, 429}
MAX_ATTEMPTS = 3
# M160 (user 2026-10-15, "Ok, confirmed. Go."): a refusal of the account (key revoked, no credit, key limit reached)
# is not a refusal of one request. HTTP 401 and 402 say so themselves; for any other refusal the key's own record
# (GET /key, limit_remaining) decides, so a provider's wording or status for "limit reached" needs no list here.
ACCOUNT_STATUS_CODES = {401, 402}
# Codes after which no model call of any request can succeed for now: the run ends with one plain line and the
# routers do not ask the user back. A timeout or a refused request stays the request's own failure.
SERVICE_DOWN_CODES = {"PROVIDER_ACCOUNT_BLOCKED", "PROVIDER_QUOTA_EXHAUSTED", "PROVIDER_UNAVAILABLE"}
# After an account refusal the client sends nothing for this long, then lets one call through as the probe.
BREAKER_SECONDS = 120.0
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
        """EXEC-FASTLANE R4: timeout (seconds) and attempts override the client's own for one call."""
        self._check_breaker()
        try:
            result = self._create(payload, timeout=timeout, attempts=attempts)
        except ProviderError as exc:
            if exc.code in ("PROVIDER_ACCOUNT_BLOCKED", "PROVIDER_QUOTA_EXHAUSTED"):
                self._open_breaker(exc)
            raise
        self._probe_passed()
        return result

    def _create(self, payload: dict[str, Any], *, timeout: float | None, attempts: int | None) -> dict[str, Any]:
        last_error: ProviderError | None = None
        tries = attempts or MAX_ATTEMPTS
        for attempt in range(tries):
            try:
                response = self.client.post("/responses", json=payload,
                                            **({"timeout": timeout} if timeout is not None else {}))
            except httpx.TimeoutException:
                last_error = ProviderError("openrouter request timed out", code="PROVIDER_TIMEOUT")
            except httpx.NetworkError as exc:
                last_error = ProviderError(
                    f"openrouter network error: {type(exc).__name__}", code="PROVIDER_NETWORK_ERROR"
                )
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
                time.sleep(1.5 * (2 ** attempt))
        assert last_error is not None
        raise ProviderError(
            f"openrouter request failed after {MAX_ATTEMPTS} attempts: {last_error}",
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
