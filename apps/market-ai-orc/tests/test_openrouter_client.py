from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from app.openrouter_client import OPENROUTER_BASE_URL, OpenRouterClient, ProviderError, response_usage


API_KEY = "sk-or-very-secret"


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.openrouter_client.time.sleep", lambda _seconds: None)


def make_client(
    handler: Callable[[httpx.Request], httpx.Response], **kwargs
) -> tuple[OpenRouterClient, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def recording(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    return OpenRouterClient(API_KEY, 30, transport=httpx.MockTransport(recording), **kwargs), seen


def sequence(*steps: httpx.Response | Exception) -> Callable[[httpx.Request], httpx.Response]:
    queue = list(steps)

    def handler(_request: httpx.Request) -> httpx.Response:
        step = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(step, Exception):
            raise step
        return step

    return handler


def error(status: int, code: str = "server_error", error_type: str = "server_error") -> httpx.Response:
    return httpx.Response(
        status, headers={"x-request-id": "req_safe"},
        json={"error": {"type": error_type, "code": code, "message": "Something happened."}},
    )


OK = httpx.Response(200, json={"id": "resp_ok", "output": []})


def test_successful_request_uses_responses_endpoint_and_headers() -> None:
    client, seen = make_client(sequence(OK))
    assert client.create({"model": "m"}) == {"id": "resp_ok", "output": []}
    request = seen[0]
    assert str(request.url) == f"{OPENROUTER_BASE_URL}/responses"
    assert request.method == "POST"
    assert request.headers["Authorization"] == f"Bearer {API_KEY}"
    assert request.headers["X-Title"] == "Saniti Market AI"
    assert "HTTP-Referer" not in request.headers


def test_optional_referer_header() -> None:
    client, seen = make_client(sequence(OK), http_referer="https://saniti.example")
    client.create({})
    assert seen[0].headers["HTTP-Referer"] == "https://saniti.example"


def test_timeout_is_retried() -> None:
    client, seen = make_client(sequence(httpx.ReadTimeout("slow"), OK))
    assert client.create({})["id"] == "resp_ok"
    assert len(seen) == 2


def test_network_error_is_retried() -> None:
    client, seen = make_client(sequence(httpx.ConnectError("down"), OK))
    assert client.create({})["id"] == "resp_ok"
    assert len(seen) == 2


@pytest.mark.parametrize("status", [500, 502, 503, 408, 409])
def test_transient_status_is_retried(status: int) -> None:
    client, seen = make_client(sequence(error(status), OK))
    assert client.create({})["id"] == "resp_ok"
    assert len(seen) == 2


def test_transient_rate_limit_is_retried() -> None:
    client, seen = make_client(sequence(error(429, "rate_limit_exceeded", "rate_limit_error"), OK))
    assert client.create({})["id"] == "resp_ok"
    assert len(seen) == 2


@pytest.mark.parametrize("code", ["credit_balance_exhausted", "insufficient_quota"])
def test_quota_failure_is_not_retried(code: str) -> None:
    client, seen = make_client(sequence(error(429, code, "insufficient_quota")))
    with pytest.raises(ProviderError) as raised:
        client.create({})
    assert len(seen) == 1
    assert raised.value.code == "PROVIDER_QUOTA_EXHAUSTED"
    assert "req_safe" in str(raised.value)


def test_client_error_is_not_retried() -> None:
    client, seen = make_client(sequence(error(400, "invalid_request_error", "invalid_request_error")))
    with pytest.raises(ProviderError) as raised:
        client.create({})
    assert len(seen) == 1
    assert raised.value.code == "PROVIDER_REJECTED"


def test_persistent_server_error_stops_after_bounded_attempts() -> None:
    client, seen = make_client(sequence(error(503)))
    with pytest.raises(ProviderError, match="after 3 attempts") as raised:
        client.create({})
    assert len(seen) == 3
    assert raised.value.code == "PROVIDER_UNAVAILABLE"


def test_persistent_timeout_reports_timeout_code() -> None:
    client, seen = make_client(sequence(httpx.ReadTimeout("slow")))
    with pytest.raises(ProviderError) as raised:
        client.create({})
    assert len(seen) == 3
    assert raised.value.code == "PROVIDER_TIMEOUT"


@pytest.mark.parametrize(
    "body",
    [
        httpx.Response(200, content=b"{not json", headers={"content-type": "application/json"}),
        httpx.Response(200, json=["not", "an", "object"]),
    ],
)
def test_malformed_provider_json_fails_without_retry(body: httpx.Response) -> None:
    client, seen = make_client(sequence(body))
    with pytest.raises(ProviderError) as raised:
        client.create({})
    assert len(seen) == 1
    assert raised.value.code == "PROVIDER_MALFORMED_RESPONSE"


def test_errors_never_contain_the_api_key() -> None:
    client, _ = make_client(sequence(error(401, "unauthorized", "auth_error")))
    with pytest.raises(ProviderError) as raised:
        client.create({})
    assert API_KEY not in str(raised.value)
    assert "Bearer" not in str(raised.value)


def test_response_usage_reads_responses_and_legacy_fields() -> None:
    assert response_usage({
        "usage": {"input_tokens": 10, "output_tokens": 4,
                  "output_tokens_details": {"reasoning_tokens": 3}, "total_tokens": 14}
    }) == {"input_tokens": 10, "output_tokens": 4, "reasoning_tokens": 3, "total_tokens": 14}
    assert response_usage({
        "usage": {"prompt_tokens": 7, "completion_tokens": 2,
                  "completion_tokens_details": {"reasoning_tokens": 1}}
    }) == {"input_tokens": 7, "output_tokens": 2, "reasoning_tokens": 1, "total_tokens": 9}
    assert response_usage({}) == {
        "input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0, "total_tokens": 0,
    }
