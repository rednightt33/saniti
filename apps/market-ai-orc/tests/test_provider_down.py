"""M160 (user 2026-10-15, "Ok, confirmed. Go."): when the model provider is down (the account refused: credit or key
limit used up, key revoked; or the provider unavailable after every retry) no model call can succeed. The client
classifies the refusal from the key's own record (GET /key) as well as HTTP 401/402, stops calling for a while and lets
one probe through; the routers do not ask the user back, nothing is retried, and the run ends SERVICE_UNAVAILABLE with
one plain line; a refusal of one request (an invalid payload) keeps its old handling, and a call after the answer
(follow-ups) never fails the answer."""
from __future__ import annotations

import json

import httpx
import pytest

from app import openrouter_client as client_module
from app import user_texts
from app.mode4 import Mode4Orchestrator
from app.openrouter_client import CreditMonitor, OpenRouterClient, ProviderError
from app.orchestrator import AgentOrchestrator, service_error
from app.schemas import AgentRunRequest, HistoryMessage
from app.tools import ToolRegistry
from conftest import ScriptedClient, make_settings
from test_first_message_router import ROUTER_ON

ASK_ON = {**ROUTER_ON, "AI_ENABLE_CONVERSATION_ROUTER": "true", "AI_ENABLE_ASK_BACK": "true"}


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.openrouter_client.time.sleep", lambda _seconds: None)


def refusal(status: int, code: str = "x") -> httpx.Response:
    return httpx.Response(status, json={"error": {"code": code, "message": "refused"}})


def key(remaining: float | None) -> httpx.Response:
    return httpx.Response(200, json={"data": {"limit": 41.5, "limit_remaining": remaining, "usage": 41.5}})


def make(responses: dict[str, list[httpx.Response]]) -> tuple[OpenRouterClient, list[str]]:
    """A client whose /responses and /key answers come from the given queues (the last one repeats)."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path.rsplit("/", 1)[-1]
        seen.append(path)
        queue = responses[path]
        return queue.pop(0) if len(queue) > 1 else queue[0]

    return OpenRouterClient("sk-or-secret", 30, transport=httpx.MockTransport(handler)), seen


OK = httpx.Response(200, json={"id": "resp_ok", "output": []})


@pytest.mark.parametrize("status", [401, 402])
def test_an_account_refusal_is_classified_from_its_status_and_not_retried(status: int) -> None:
    client, seen = make({"responses": [refusal(status)], "key": [key(5.0)]})
    with pytest.raises(ProviderError) as raised:
        client.create({})
    assert raised.value.code == "PROVIDER_ACCOUNT_BLOCKED" and raised.value.service_down
    assert seen == ["responses"]


@pytest.mark.parametrize("status", [403, 400])
def test_any_other_refusal_reads_the_keys_own_record(status: int) -> None:
    empty, _ = make({"responses": [refusal(status, "key_limit")], "key": [key(0)]})
    with pytest.raises(ProviderError) as raised:
        empty.create({})
    assert raised.value.code == "PROVIDER_ACCOUNT_BLOCKED"
    funded, _ = make({"responses": [refusal(status, "moderation")], "key": [key(12.0)]})
    with pytest.raises(ProviderError) as raised:
        funded.create({})
    assert raised.value.code == "PROVIDER_REJECTED" and not raised.value.service_down
    unknown, _ = make({"responses": [refusal(status)], "key": [httpx.Response(500)]})
    with pytest.raises(ProviderError) as raised:
        unknown.create({})
    assert raised.value.code == "PROVIDER_REJECTED"  # without the key's record nothing is assumed


def test_the_breaker_sends_nothing_for_a_while_then_one_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    now = [1000.0]
    monkeypatch.setattr(client_module.time, "monotonic", lambda: now[0])
    client, seen = make({"responses": [refusal(402), OK], "key": [key(0)]})
    with pytest.raises(ProviderError):
        client.create({})
    with pytest.raises(ProviderError) as raised:
        client.create({})
    assert raised.value.code == "PROVIDER_ACCOUNT_BLOCKED" and seen == ["responses"]  # nothing sent
    now[0] += client_module.BREAKER_SECONDS + 1
    assert client.create({})["id"] == "resp_ok"  # the probe passes and closes the breaker
    assert client.create({})["id"] == "resp_ok" and seen == ["responses", "responses", "responses"]


def test_unavailable_after_every_retry_is_down_and_a_timeout_is_not() -> None:
    client, seen = make({"responses": [refusal(503)], "key": [key(5.0)]})
    with pytest.raises(ProviderError) as raised:
        client.create({})
    assert raised.value.code == "PROVIDER_UNAVAILABLE" and raised.value.service_down and len(seen) == 3
    assert not ProviderError("slow", code="PROVIDER_TIMEOUT").service_down


def test_a_run_error_carries_the_plain_line_only_when_the_provider_is_down() -> None:
    down = service_error("PROVIDER_QUOTA_EXHAUSTED", "openrouter HTTP 429")
    assert down.code == "SERVICE_UNAVAILABLE" and down.user_message == user_texts.SERVICE_UNAVAILABLE_LINE
    assert down.message.startswith("PROVIDER_QUOTA_EXHAUSTED")
    own = service_error("PROVIDER_REJECTED", "openrouter HTTP 400")
    assert own.code == "PROVIDER_REJECTED" and own.user_message is None


def mode4(script: list) -> tuple[Mode4Orchestrator, ScriptedClient]:
    scripted = ScriptedClient(script)
    inner = AgentOrchestrator(make_settings(**ASK_ON), scripted, ToolRegistry())
    return Mode4Orchestrator(inner), scripted


BLOCKED = ProviderError("openrouter HTTP 402: no credit", code="PROVIDER_ACCOUNT_BLOCKED", status_code=402)


def test_a_first_message_with_the_provider_down_ends_with_the_line_not_a_question() -> None:
    wrapper, scripted = mode4([BLOCKED])
    result = wrapper.run(AgentRunRequest(request_id="down-1", message="Bagaimana BBRI kemarin?"))
    assert result.status == "FAILED" and result.error.code == "SERVICE_UNAVAILABLE"
    assert result.error.user_message == user_texts.SERVICE_UNAVAILABLE_LINE
    assert len(scripted.payloads) == 1  # not retried, no step ran, no ask-back


def test_a_later_message_with_the_provider_down_ends_the_same_way() -> None:
    wrapper, scripted = mode4([BLOCKED])
    history = [HistoryMessage(role="user", content="BBRI"), HistoryMessage(role="assistant", content="BBRI naik 2%.")]
    result = wrapper.run(AgentRunRequest(request_id="down-2", message="lanjut", history=history, analysis_path="MODE4"))
    assert result.status == "FAILED" and result.error.code == "SERVICE_UNAVAILABLE" and len(scripted.payloads) == 1


def test_a_refusal_of_the_request_itself_keeps_the_ask_back() -> None:
    rejected = ProviderError("openrouter HTTP 400: bad schema", code="PROVIDER_REJECTED", status_code=400)
    wrapper, scripted = mode4([rejected, rejected])
    result = wrapper.run(AgentRunRequest(request_id="down-3", message="Bagaimana BBRI kemarin?"))
    assert result.status == "NEEDS_CLARIFICATION" and result.execution.mode.route == "ROUTER_FAILED"
    assert len(scripted.payloads) == 2  # retried once, as before


def test_follow_ups_with_the_provider_down_never_fail_the_answer() -> None:
    scripted = ScriptedClient([BLOCKED])
    inner = AgentOrchestrator(make_settings(**ASK_ON), scripted, ToolRegistry())
    parsed, record = inner.suggest_follow_ups("down-4", "jawaban")
    assert parsed is None and record["status"] == "PROVIDER_DOWN"


def test_the_credit_monitor_logs_a_low_balance(monkeypatch: pytest.MonkeyPatch) -> None:
    logged: list[tuple[str, dict]] = []
    monkeypatch.setattr(client_module, "_log", lambda event, **fields: logged.append((event, fields)))
    client, _ = make({"responses": [OK], "key": [key(0.4)]})
    CreditMonitor(client, 900, 2.0).check()
    assert [event for event, _ in logged] == ["ai_provider_credit", "ai_provider_credit_low"]
    assert logged[1][1]["limit_remaining"] == 0.4 and "sk-or-secret" not in json.dumps(logged)
    logged.clear()
    funded, _ = make({"responses": [OK], "key": [key(30.0)]})
    CreditMonitor(funded, 900, 2.0).check()
    assert [event for event, _ in logged] == ["ai_provider_credit"]


def test_a_call_ends_at_its_total_deadline_even_while_bytes_keep_coming(monkeypatch: pytest.MonkeyPatch) -> None:
    """M163 (go for EXEC-M163 item 1): `edge_2f7523a7…` thought 210 s on the fast lane although its call was capped at
    90 s: an httpx timeout only bounds the wait for the next bytes. A provider sending a keep-alive byte every 30 s is
    now cut at the call's total deadline; a complete answer within the deadline is read as before."""
    now = [0.0]
    monkeypatch.setattr(client_module.time, "monotonic", lambda: now[0])
    logged: list[str] = []
    monkeypatch.setattr(client_module, "_log", lambda event, **fields: logged.append(event))

    def keep_alive():
        for _ in range(20):
            now[0] += 30.0
            yield b" "
        yield b'{"id": "resp_late", "output": []}'

    slow, _ = make({"responses": [httpx.Response(200, content=keep_alive())], "key": [key(5.0)]})
    with pytest.raises(ProviderError) as raised:
        slow.create({}, timeout=90.0, attempts=1)
    assert raised.value.code == "PROVIDER_TIMEOUT" and not raised.value.service_down
    assert 90.0 < now[0] <= 120.0 and logged == ["ai_provider_call_deadline"]

    def prompt():
        now[0] += 20.0
        yield b'{"id": "resp_ok",'
        yield b' "output": []}'

    quick, _ = make({"responses": [httpx.Response(200, content=prompt())], "key": [key(5.0)]})
    assert quick.create({}, timeout=90.0, attempts=1)["id"] == "resp_ok"
