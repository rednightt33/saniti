from __future__ import annotations

import httpx
import pytest

from app.openai_client import ResponsesClient, extract_reasoning_audit, response_usage


class FakeHttpClient:
    def __init__(self, responses: list[httpx.Response]) -> None:
        self.responses = responses
        self.calls = 0

    def post(self, *_args, **_kwargs) -> httpx.Response:
        response = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        return response


def response(status: int, code: str, error_type: str = "insufficient_quota") -> httpx.Response:
    return httpx.Response(
        status,
        headers={"x-request-id": "req_safe_test"},
        json={"error": {"type": error_type, "code": code, "message": "No credits remain."}},
        request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
    )


def test_credit_exhaustion_is_not_retried() -> None:
    client = object.__new__(ResponsesClient)
    client.provider = "openai"
    client.client = FakeHttpClient([response(429, "credit_balance_exhausted")])

    with pytest.raises(RuntimeError, match="credit_balance_exhausted") as error:
        client.create({"input": "test"})

    assert client.client.calls == 1
    assert "req_safe_test" in str(error.value)


def test_transient_429_is_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    client = object.__new__(ResponsesClient)
    client.provider = "openai"
    client.client = FakeHttpClient([
        response(429, "rate_limit_exceeded", "rate_limit_error"),
        httpx.Response(
            200,
            json={"id": "resp_ok"},
            request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
        ),
    ])
    monkeypatch.setattr("app.openai_client.time.sleep", lambda _seconds: None)

    assert client.create({"input": "test"}) == {"id": "resp_ok"}
    assert client.client.calls == 2


def test_non_retryable_client_error_keeps_safe_provider_detail() -> None:
    client = object.__new__(ResponsesClient)
    client.provider = "openai"
    client.client = FakeHttpClient([response(400, "invalid_request_error", "invalid_request_error")])

    with pytest.raises(RuntimeError, match="invalid_request_error"):
        client.create({"input": "test"})

    assert client.client.calls == 1


def test_provider_base_url_is_allowlisted() -> None:
    with pytest.raises(ValueError, match="Unsupported AI provider"):
        ResponsesClient("https://attacker.invalid", "secret", 15)


def test_extracts_only_provider_returned_reasoning_and_summary() -> None:
    blocks, format_name, summary, source = extract_reasoning_audit(
        {
            "output": [
                {
                    "type": "reasoning",
                    "summary": [{"type": "summary_text", "text": "Use a bounded screen first."}],
                    "encrypted_content": "opaque-provider-value",
                },
                {"type": "function_call", "name": "screen_features"},
            ]
        },
        max_bytes=4096,
    )
    assert len(blocks) == 1
    assert format_name == "MIXED"
    assert summary == "Use a bounded screen first."
    assert source == "PROVIDER_REASONING"


def test_reasoning_audit_has_deterministic_action_fallback() -> None:
    blocks, format_name, summary, source = extract_reasoning_audit(
        {"output": [{"type": "function_call", "name": "query_features"}]},
        max_bytes=4096,
    )
    assert blocks == []
    assert format_name == "NONE"
    assert summary == "Requested tools: query_features"
    assert source == "DERIVED_ACTION"


def test_response_usage_supports_openrouter_compatible_fields() -> None:
    assert response_usage({
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 4,
            "completion_tokens_details": {"reasoning_tokens": 3},
        }
    }) == {"input_tokens": 10, "output_tokens": 4, "reasoning_tokens": 3}
