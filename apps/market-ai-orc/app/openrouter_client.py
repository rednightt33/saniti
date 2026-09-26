from __future__ import annotations

import time
from typing import Any

import httpx


OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
NON_RETRYABLE_429_CODES = {"credit_balance_exhausted", "insufficient_quota"}
RETRYABLE_STATUS_CODES = {408, 409, 429}
MAX_ATTEMPTS = 3


class ProviderError(RuntimeError):
    """Normalized OpenRouter failure. The message never contains credentials or headers."""

    def __init__(self, message: str, *, code: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


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

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        last_error: ProviderError | None = None
        for attempt in range(MAX_ATTEMPTS):
            try:
                response = self.client.post("/responses", json=payload)
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
                if response.status_code == 429 and (
                    error_type in NON_RETRYABLE_429_CODES or error_code in NON_RETRYABLE_429_CODES
                ):
                    raise ProviderError(detail, code="PROVIDER_QUOTA_EXHAUSTED", status_code=429)
                if response.status_code not in RETRYABLE_STATUS_CODES and response.status_code < 500:
                    raise ProviderError(detail, code="PROVIDER_REJECTED", status_code=response.status_code)
                last_error = ProviderError(
                    detail, code="PROVIDER_UNAVAILABLE", status_code=response.status_code
                )
            if attempt < MAX_ATTEMPTS - 1:
                time.sleep(1.5 * (2 ** attempt))
        assert last_error is not None
        raise ProviderError(
            f"openrouter request failed after {MAX_ATTEMPTS} attempts: {last_error}",
            code=last_error.code,
            status_code=last_error.status_code,
        )
