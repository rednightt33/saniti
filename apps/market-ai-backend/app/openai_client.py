from __future__ import annotations

import time
from typing import Any

import httpx


NON_RETRYABLE_429_CODES = {"credit_balance_exhausted", "insufficient_quota"}


PROVIDER_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
}


class ResponsesClient:
    """Provider-allowlisted Responses transport with bounded retry and no storage."""

    def __init__(self, provider: str, api_key: str, timeout_seconds: int) -> None:
        if provider not in PROVIDER_BASE_URLS:
            raise ValueError(f"Unsupported AI provider: {provider}")
        self.provider = provider
        self.client = httpx.Client(
            base_url=PROVIDER_BASE_URLS[provider],
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                **({"X-Title": "Saniti Market AI"} if provider == "openrouter" else {}),
            },
            timeout=httpx.Timeout(timeout_seconds),
        )

    def close(self) -> None:
        self.client.close()

    def _error_detail(self, response: httpx.Response) -> tuple[str, str | None, str | None]:
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
        detail = f"{self.provider} HTTP {response.status_code}"
        if request_id:
            detail += f" (request_id={request_id})"
        if labels:
            detail += f" {labels}"
        return f"{detail}: {safe_message}", error_type, error_code

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = self.client.post("/responses", json=payload)
                if 200 <= response.status_code < 300:
                    result = response.json()
                    if not isinstance(result, dict):
                        raise RuntimeError(f"{self.provider} response was not a JSON object")
                    return result
                detail, error_type, error_code = self._error_detail(response)
                if response.status_code == 429 and (
                    error_type in NON_RETRYABLE_429_CODES or error_code in NON_RETRYABLE_429_CODES
                ):
                    raise RuntimeError(detail)
                if response.status_code not in {408, 409, 429} and response.status_code < 500:
                    raise RuntimeError(detail)
                last_error = RuntimeError(detail)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_error = exc
            if attempt < 2:
                time.sleep(1.5 * (2 ** attempt))
        raise RuntimeError(f"{self.provider} Responses request failed after retries: {last_error}")
