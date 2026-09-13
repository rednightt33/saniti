from __future__ import annotations

import time
from typing import Any

import httpx


NON_RETRYABLE_429_CODES = {"credit_balance_exhausted", "insufficient_quota"}


class OpenAIResponsesClient:
    """Small Responses API transport with bounded retry and no stateful storage."""

    def __init__(self, api_key: str, timeout_seconds: int) -> None:
        self.client = httpx.Client(
            base_url="https://api.openai.com/v1",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=httpx.Timeout(timeout_seconds),
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
        detail = f"OpenAI HTTP {response.status_code}"
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
                        raise RuntimeError("OpenAI response was not a JSON object")
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
        raise RuntimeError(f"OpenAI Responses request failed after retries: {last_error}")
