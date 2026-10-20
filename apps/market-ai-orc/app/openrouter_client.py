from __future__ import annotations

import json
import logging
import socket
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
TRANSPORT_HEADERS = frozenset({"content-encoding", "content-length", "transfer-encoding"})
KEY_STATUS_TTL_SECONDS = 60.0
# EXEC-M181 (user 2026-10-20): the stream events that show the model is producing something. OpenRouter's keep-alive
# comments (": OPENROUTER PROCESSING") arrive while a stalled provider keeps the connection open, so they never count
# (measured 2026-10-20: up to 83 comments in 107 s between content events).
CONTENT_EVENTS = frozenset({"response.reasoning_text.delta", "response.reasoning_summary_text.delta",
                            "response.output_text.delta", "response.function_call_arguments.delta",
                            "response.refusal.delta"})
# the events that carry the whole response, in the same shape as a call without streaming
REASONING_EVENTS = frozenset({"response.reasoning_text.delta", "response.reasoning_summary_text.delta"})
FINAL_EVENTS = frozenset({"response.completed", "response.incomplete", "response.failed"})
WATCH_SECONDS = 0.25
# a call that ended because the run was stopped or ran out of time: never retried
CALL_STOPPED, RUN_DEADLINE = "CALL_STOPPED", "RUN_DEADLINE"
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


def _interrupt(response: httpx.Response) -> None:
    """Wake a read that waits on this response from another thread. Closing the response alone does not interrupt a
    read blocked on its socket (tested 2026-10-20 against a silent server), so the socket is shut down first."""
    stream = response.extensions.get("network_stream")
    try:
        sock = stream.get_extra_info("socket") if stream is not None else None
        if sock is not None:
            sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    try:
        response.close()
    except Exception:  # noqa: BLE001 - the reading thread still sees the reason on its next line
        pass


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
        streaming: bool = False,
        first_content_seconds: float = 45.0,
        idle_seconds: float = 30.0,
        tool_idle_seconds: float = 120.0,
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
        self.streaming = streaming
        self.first_content_seconds, self.idle_seconds = float(first_content_seconds), float(idle_seconds)
        self.tool_idle_seconds = max(float(tool_idle_seconds), self.idle_seconds)
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
               attempts: int | None = None, retry_stalls: bool = True) -> dict[str, Any]:
        """EXEC-FASTLANE R4: timeout (seconds) and attempts override the client's own for one call. EXEC-M181:
        retry_stalls false raises a stalled or timed-out call at once, so the caller retries it where the user sees
        it; other failures keep their retries."""
        self._check_breaker()
        try:
            result = self._create(payload, timeout=timeout, attempts=attempts, retry_stalls=retry_stalls)
        except ProviderError as exc:
            if exc.code in ("PROVIDER_ACCOUNT_BLOCKED", "PROVIDER_QUOTA_EXHAUSTED"):
                self._open_breaker(exc)
            raise
        self._probe_passed()
        return result

    def _post_within(self, payload: dict[str, Any], timeout: float | None) -> httpx.Response:
        """M163 (user 2026-10-15, go for EXEC-M163 item 1): one POST /responses that ends at a total deadline. An httpx
        timeout only bounds each wait for the next bytes, so a provider that keeps the connection alive while the model
        thinks was never cut (the fast lane's 90 s cap never fired). The body is read as a stream and the call is
        closed once the deadline has passed; a wait without any bytes still ends at the same length. The deadline is
        the call's timeout, else the client's own."""
        seconds = float(timeout if timeout is not None else self.timeout_seconds)
        deadline = time.monotonic() + seconds
        with self.client.stream("POST", "/responses", json=payload, timeout=seconds) as response:
            chunks: list[bytes] = []
            for chunk in response.iter_bytes():
                chunks.append(chunk)
                if time.monotonic() > deadline:
                    _log("ai_provider_call_deadline", seconds=seconds)
                    raise httpx.ReadTimeout(f"no complete response within {seconds:g} s")
            # M168: the bytes are already decoded, so the headers that describe the transport (compression, length)
            # are dropped; kept, they made the new response decode the body a second time (DecodingError)
            headers = [(k, v) for k, v in response.headers.multi_items() if k.lower() not in TRANSPORT_HEADERS]
            return httpx.Response(response.status_code, headers=headers, content=b"".join(chunks),
                                  request=response.request)

    def _stream_within(self, payload: dict[str, Any], timeout: float | None) -> httpx.Response:
        """EXEC-M181 (user 2026-10-20): one streamed POST /responses. The call ends early when the provider sends no
        content event within first_content_seconds, or none for idle_seconds after that (PROVIDER_STALLED), when the
        run is stopped (CALL_STOPPED) or out of time (RUN_DEADLINE); the total limit stays the call's timeout. The
        final event carries the whole response, which is returned as if it had been sent without streaming.

        Measured 2026-10-20: DeepSeek and MiMo send a tool call's arguments in one piece at the end, after a silence
        that grows with their length (31 s for about 4,200 tokens), and the function_call item only appears then. So
        when tools are offered, the silence after reasoning (or from the start, with reasoning off) may be a tool call
        being written: it ends at tool_idle_seconds instead."""
        from .stop import current_stop  # the run's flags (both modules import this one)
        from .tools.request_data import current_run_deadline

        seconds = float(timeout if timeout is not None else self.timeout_seconds)
        started = time.monotonic()
        deadline, run_deadline, stop_flag = started + seconds, current_run_deadline.get(), current_stop.get()
        seen: dict[str, Any] = {"first": None, "last": None, "kind": None, "gap": 0.0, "events": 0, "comments": 0,
                                "reason": None, "limit": None}
        tools = bool(payload.get("tools")) and payload.get("tool_choice") != "none"
        thinking_off = (payload.get("reasoning") or {}).get("enabled") is False
        first_limit = self.tool_idle_seconds if tools and thinking_off else self.first_content_seconds

        def idle_limit() -> float:
            return self.tool_idle_seconds if tools and seen["kind"] in REASONING_EVENTS else self.idle_seconds
        done = threading.Event()
        limits = httpx.Timeout(seconds, read=max(first_limit, self.tool_idle_seconds) + 5.0)
        with self.client.stream("POST", "/responses", json={**payload, "stream": True}, timeout=limits) as response:
            if response.status_code != 200 or "text/event-stream" not in response.headers.get("content-type", ""):
                return httpx.Response(response.status_code, headers=self._kept_headers(response),
                                      content=response.read(), request=response.request)

            def watch() -> None:
                while not done.wait(WATCH_SECONDS):
                    now = time.monotonic()
                    reason = (CALL_STOPPED if stop_flag is not None and stop_flag.is_set()
                              else RUN_DEADLINE if run_deadline is not None and now >= run_deadline
                              else "DEADLINE" if now >= deadline
                              else "NO_FIRST_CONTENT" if seen["first"] is None and now - started >= first_limit
                              else "IDLE" if seen["last"] is not None and now - seen["last"] >= idle_limit()
                              else None)
                    if reason is not None:
                        seen["reason"] = reason
                        seen["limit"] = first_limit if reason == "NO_FIRST_CONTENT" else idle_limit()
                        _interrupt(response)
                        return

            watcher = threading.Thread(target=watch, name="provider-stream-watch", daemon=True)
            watcher.start()
            final: dict[str, Any] | None = None
            failure: dict[str, Any] | None = None
            try:
                for line in response.iter_lines():
                    if seen["reason"] is not None:
                        break
                    if line.startswith(":"):
                        seen["comments"] += 1
                        continue
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        event = json.loads(data)
                    except ValueError:
                        continue
                    kind = event.get("type") if isinstance(event, dict) else None
                    if kind in CONTENT_EVENTS:
                        now = time.monotonic()
                        if seen["last"] is not None:
                            seen["gap"] = max(seen["gap"], now - seen["last"])
                        seen["first"] = seen["first"] or now
                        seen["last"], seen["kind"] = now, kind
                        seen["events"] += 1
                    elif kind in FINAL_EVENTS and isinstance(event.get("response"), dict):
                        final = event["response"]
                    elif kind == "error" or (kind is None and isinstance(event, dict) and event.get("error")):
                        failure = event
            except (httpx.HTTPError, httpx.StreamError, ValueError) as exc:
                if seen["reason"] is None and isinstance(exc, httpx.ReadTimeout):
                    seen["reason"] = "NO_FIRST_CONTENT" if seen["first"] is None else "IDLE"
                    seen["limit"] = first_limit if seen["first"] is None else idle_limit()
                elif seen["reason"] is None:
                    raise
            finally:
                done.set()
        reason = seen["reason"]
        _log("ai_provider_stream", outcome=reason or (final or {}).get("status") or ("error" if failure else "ended"),
             seconds=round(time.monotonic() - started, 1),
             first_content_ms=int((seen["first"] - started) * 1000) if seen["first"] else None,
             max_content_gap_ms=int(seen["gap"] * 1000), content_events=seen["events"], keepalives=seen["comments"])
        if reason == CALL_STOPPED:
            raise ProviderError("the run was stopped during the model call", code=CALL_STOPPED)
        if reason == RUN_DEADLINE:
            raise ProviderError("the run's time ran out during the model call", code=RUN_DEADLINE)
        if reason == "DEADLINE":
            raise httpx.ReadTimeout(f"no complete response within {seconds:g} s")
        if reason is not None:
            raise ProviderError(f"the AI provider sent no output for {seen['limit']:g} s", code="PROVIDER_STALLED")
        if final is not None:
            return httpx.Response(200, json=final, request=response.request)
        if failure is not None:  # an error inside the stream counts as the provider failing (retried like a 5xx)
            error = failure.get("error") if isinstance(failure.get("error"), dict) else failure
            return httpx.Response(502, json={"error": {"message": str(error.get("message") or "stream error")[:500],
                                                       "code": error.get("code")}}, request=response.request)
        raise httpx.ReadError("the stream ended without a final response")

    @staticmethod
    def _kept_headers(response: httpx.Response) -> list[tuple[str, str]]:
        return [(k, v) for k, v in response.headers.multi_items() if k.lower() not in TRANSPORT_HEADERS]

    def _create(self, payload: dict[str, Any], *, timeout: float | None, attempts: int | None,
                retry_stalls: bool = True) -> dict[str, Any]:
        last_error: ProviderError | None = None
        tries = attempts or MAX_ATTEMPTS
        for attempt in range(tries):
            try:
                response = self._stream_within(payload, timeout) if self.streaming \
                    else self._post_within(payload, timeout)
            except ProviderError as exc:
                if exc.code != "PROVIDER_STALLED" or not retry_stalls:
                    raise
                last_error = exc
            except httpx.TimeoutException:
                last_error = ProviderError("openrouter request timed out", code="PROVIDER_TIMEOUT")
                if not retry_stalls:
                    raise last_error
            except httpx.DecodingError as exc:
                # M168: a body that cannot be decoded is the provider's malformed answer, not retried (tokens may
                # already be spent) and never an exception that ends the run as INTERNAL_ERROR
                raise ProviderError("openrouter returned a body that cannot be decoded",
                                    code="PROVIDER_MALFORMED_RESPONSE") from exc
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
