from __future__ import annotations

import time
from typing import Any

import httpx


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

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = self.client.post("/responses", json=payload)
                if response.status_code not in {408, 409, 429} and response.status_code < 500:
                    response.raise_for_status()
                    result = response.json()
                    if not isinstance(result, dict):
                        raise RuntimeError("OpenAI response was not a JSON object")
                    return result
                last_error = RuntimeError(f"OpenAI temporary HTTP status {response.status_code}")
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_error = exc
            if attempt < 2:
                time.sleep(1.5 * (2 ** attempt))
        raise RuntimeError(f"OpenAI Responses request failed after retries: {last_error}")
