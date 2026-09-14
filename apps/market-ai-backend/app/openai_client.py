from __future__ import annotations

import json
import time
from typing import Any

import httpx


NON_RETRYABLE_429_CODES = {"credit_balance_exhausted", "insufficient_quota"}


PROVIDER_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
}


def extract_reasoning_audit(
    response: dict[str, Any], *, max_bytes: int
) -> tuple[list[dict[str, Any]], str, str | None, str]:
    """Return only provider-supplied reasoning blocks, never prompts or tool results."""
    blocks: list[dict[str, Any]] = []
    for item in response.get("output", []):
        if not isinstance(item, dict):
            continue
        if item.get("type") == "reasoning":
            blocks.append(item)
        for key in ("reasoning", "reasoning_details"):
            value = item.get(key)
            if isinstance(value, str) and value:
                blocks.append({"type": key, "text": value})
            elif isinstance(value, list):
                blocks.extend(entry for entry in value if isinstance(entry, dict))
    for key in ("reasoning", "reasoning_details"):
        value = response.get(key)
        if isinstance(value, str) and value:
            blocks.append({"type": key, "text": value})
        elif isinstance(value, list):
            blocks.extend(entry for entry in value if isinstance(entry, dict))

    encoded = json.dumps(blocks, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > max_bytes:
        blocks = [{
            "type": "storage_compaction",
            "original_bytes": len(encoded),
            "note": "Provider-returned reasoning exceeded the configured audit byte limit.",
        }]

    labels = {str(block.get("type") or "").lower() for block in blocks}
    has_text = any(label in {"reasoning", "text", "reasoning.text"} for label in labels)
    has_summary = any(
        "summary" in str(block.get("type") or "").lower() or bool(block.get("summary"))
        for block in blocks
    )
    has_encrypted = any(
        "encrypted" in str(block.get("type") or "").lower() or bool(block.get("encrypted_content"))
        for block in blocks
    )
    kinds = sum((has_text, has_summary, has_encrypted))
    reasoning_format = "MIXED" if kinds > 1 else (
        "ENCRYPTED" if has_encrypted else "SUMMARY" if has_summary else "TEXT" if blocks else "NONE"
    )

    summaries: list[str] = []
    for block in blocks:
        for candidate in (block.get("summary"), block.get("text")):
            if isinstance(candidate, str) and candidate.strip():
                summaries.append(" ".join(candidate.split()))
            elif isinstance(candidate, list):
                for entry in candidate:
                    if isinstance(entry, dict) and isinstance(entry.get("text"), str):
                        summaries.append(" ".join(entry["text"].split()))
    if summaries:
        return blocks, reasoning_format, " ".join(summaries)[:2000], "PROVIDER_REASONING"

    calls = [
        str(item.get("name")) for item in response.get("output", [])
        if isinstance(item, dict) and item.get("type") == "function_call" and item.get("name")
    ]
    if calls:
        return blocks, reasoning_format, f"Requested tools: {', '.join(calls)}", "DERIVED_ACTION"
    return blocks, reasoning_format, "Returned a candidate final answer.", "DERIVED_ACTION"


def response_usage(response: dict[str, Any]) -> dict[str, int]:
    usage = response.get("usage") or {}
    output_details = usage.get("output_tokens_details") or usage.get("completion_tokens_details") or {}
    return {
        "input_tokens": int(usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0),
        "output_tokens": int(usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0),
        "reasoning_tokens": int(output_details.get("reasoning_tokens", 0) or 0),
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
