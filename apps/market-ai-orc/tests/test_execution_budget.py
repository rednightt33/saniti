"""User 2026-10-19: 96k combined, no silent model/level change, no paid blind retry after exhaustion."""
from __future__ import annotations

import asyncio
import time

import httpx
import pytest

from app import lanes, stop
from app.execution_budget import resolve as budget
from app.model_choices import MODEL_CHOICES, current_model_choice, resolve
from app.model_choices import ModelChoiceError
from app.openrouter_client import OpenRouterClient, ProviderError
from app.orchestrator import AgentOrchestrator
from app.schemas import AgentRunRequest
from app.tools import build_default_registry
from app.tools.request_data import current_run_deadline
from conftest import ANSWER, ScriptedClient, final_response, make_settings, tool_call_response

LIVE_BUDGET = {"AI_MAX_OUTPUT_TOKENS":"96000", "AI_MAX_REASONING_TOKENS":"48000",
               "AI_MAX_PRESENTATION_TOKENS":"48000", "AI_MAX_CONTEXT_TOKENS":"500000"}
CHOICES = [(o.model, level) for o in MODEL_CHOICES for level in o.levels]


@pytest.mark.parametrize("model,level", CHOICES)
@pytest.mark.parametrize("lane", [lanes.STANDARD, lanes.FAST])
def test_every_executor_call_keeps_the_choice_and_combined_budget(model, level, lane):
    settings = make_settings(**LIVE_BUDGET, AI_ENABLE_FASTLANE="true")
    script = ScriptedClient([tool_call_response("get_system_capabilities"), final_response(ANSWER)])
    selected = resolve(model, level, settings)
    token, lane_token = current_model_choice.set(selected), lanes.current_lane.set(lane)
    try:
        result = AgentOrchestrator(settings, script, build_default_registry()).run(
            AgentRunRequest(request_id="budget", message="Halo"))
    finally:
        lanes.current_lane.reset(lane_token)
        current_model_choice.reset(token)
    assert result.status == "COMPLETED"
    assert len(script.payloads) == 2
    assert all(p["model"] == model and p["reasoning"] == selected.reasoning
               and p["max_output_tokens"] == 96000 for p in script.payloads)
    assert result.execution.reasoning_level == level
    assert all(c["sent_reasoning"] == selected.reasoning for c in result.execution.model_calls)
    assert result.execution.token_budget["split_guaranteed"] is False
    assert result.execution.token_budget["reasoning_max_tokens"] == (48000 if model.startswith("qwen/")
                                                                   and level == "on" else None)


def test_incomplete_but_parseable_final_is_repaired_once_without_data_tools():
    settings = make_settings(**LIVE_BUDGET)
    cut = {**final_response(ANSWER), "status":"incomplete", "incomplete_details":{"reason":"max_output_tokens"}}
    script = ScriptedClient([cut, cut, final_response(ANSWER)])
    token = current_model_choice.set(resolve("deepseek/deepseek-v4.1-flash", "max", settings))
    try:
        result = AgentOrchestrator(settings, script, build_default_registry()).run(
            AgentRunRequest(request_id="cut", message="Halo"))
    finally:
        current_model_choice.reset(token)
    assert result.status == "FAILED" and result.error.code == "OUTPUT_BUDGET_EXHAUSTED"
    assert len(script.payloads) == 2 and "tools" not in script.payloads[1]
    assert all(p["reasoning"] == {"effort":"max"} for p in script.payloads)


def test_an_incomplete_tool_with_valid_json_and_no_usage_is_never_executed():
    cut = {**tool_call_response("get_system_capabilities"), "status":"incomplete",
           "incomplete_details":{"reason":"max_output_tokens"}}
    cut.pop("usage")
    script = ScriptedClient([cut, final_response(ANSWER)])
    result = AgentOrchestrator(make_settings(**LIVE_BUDGET), script, build_default_registry()).run(
        AgentRunRequest(request_id="cut-tool", message="Halo"))
    assert result.execution.tool_call_count == 0
    assert "MODEL_OUTPUT_TRUNCATED" in str(script.payloads[1]["input"])


@pytest.mark.parametrize("silent_before", [True, False])
def test_deadline_cancels_a_stalled_http_read_and_closes_the_stream(silent_before):
    class Stalled(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self):
            if not silent_before:
                yield b" "
            await asyncio.sleep(5)
            yield b'{"id":"too-late"}'

        async def aclose(self):
            self.closed = True

    body, seen = Stalled(), []
    def handler(request):
        seen.append(request)
        return httpx.Response(200, stream=body)
    client = OpenRouterClient("test", 10, transport=httpx.MockTransport(handler))
    started = time.monotonic()
    with pytest.raises(ProviderError) as raised:
        client.create({}, timeout=0.05)
    assert raised.value.code == "PROVIDER_TIMEOUT" and len(seen) == 1
    assert time.monotonic() - started < 1 and body.closed
    client.close()


def test_no_dispatch_after_the_root_deadline_or_stop():
    sent = []
    client = OpenRouterClient("test", 600, transport=httpx.MockTransport(lambda r: sent.append(r)))
    token = current_run_deadline.set(time.monotonic() - 1)
    try:
        with pytest.raises(ProviderError) as raised:
            client.create({})
        assert raised.value.code == "PROVIDER_TIMEOUT" and sent == []
    finally:
        current_run_deadline.reset(token)
    with stop.running("stopped", "owner") as flag:
        flag.set()
        with pytest.raises(ProviderError) as raised:
            client.create({})
        assert raised.value.code == "STOPPED_BY_USER" and sent == []
    client.close()


def test_transient_retry_uses_only_the_remaining_deadline(monkeypatch):
    from app import openrouter_client as transport
    now, budgets = [0.0], []
    monkeypatch.setattr(transport.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(transport.time, "sleep", lambda seconds: now.__setitem__(0, now[0] + seconds))
    client = OpenRouterClient("test", 600, transport=httpx.MockTransport(lambda r: None))
    def post(payload, timeout):
        budgets.append(timeout)
        now[0] += 30
        return httpx.Response(503, json={"error":{"message":"busy"}}) if len(budgets) == 1 \
            else httpx.Response(200, json={"id":"ok","output":[]})
    monkeypatch.setattr(client, "_post_within", post)
    token = current_run_deadline.set(100.0)
    try:
        assert client.create({"model":"chosen", "reasoning":{"effort":"max"}})["id"] == "ok"
    finally:
        current_run_deadline.reset(token)
        client.close()
    assert budgets == [100.0, 68.5]


def test_a_provider_response_after_ninety_seconds_does_not_restart_the_call(monkeypatch):
    from app import openrouter_client as transport
    now, budgets = [0.0], []
    monkeypatch.setattr(transport.time, "monotonic", lambda: now[0])
    client = OpenRouterClient("test", 600, transport=httpx.MockTransport(lambda r: None))
    def post(payload, timeout):
        budgets.append(timeout)
        now[0] += 95
        return httpx.Response(200, json={"id":"after-90","output":[]})
    monkeypatch.setattr(client, "_post_within", post)
    try:
        assert client.create({"model":"chosen", "reasoning":{"effort":"max"}})["id"] == "after-90"
    finally:
        client.close()
    assert budgets == [600.0]


@pytest.mark.parametrize("input_tokens,expected", [(303999,"offered"),(304000,"withdrawn"),(404001,"refused")])
def test_the_96k_reservation_respects_soft_and_hard_context_boundaries(monkeypatch, input_tokens, expected):
    script = ScriptedClient([final_response({**ANSWER,"response_type":"LIMITATION","limitations":["Batas konteks."]})])
    agent = AgentOrchestrator(make_settings(**LIVE_BUDGET), script, build_default_registry())
    monkeypatch.setattr(agent, "_estimate_context", lambda state, tools: input_tokens)
    result = agent.run(AgentRunRequest(request_id="context-boundary", message="Halo"))
    if expected == "refused":
        assert result.error.code == "CONTEXT_LIMIT" and script.payloads == []
    else:
        assert result.status == "LIMITED" and len(script.payloads) == 1
        assert bool(script.payloads[0].get("tools")) == (expected == "offered")
        assert script.payloads[0]["max_output_tokens"] == 96000


def test_an_invalid_numeric_budget_is_refused_without_silently_disabling_reasoning():
    settings = make_settings(AI_MAX_OUTPUT_TOKENS="12000", AI_MAX_REASONING_TOKENS="48000")
    with pytest.raises(ModelChoiceError) as refused:
        resolve("qwen/qwen3.8-flash", "on", settings)
    assert refused.value.code == "MODEL_BUDGET_UNSUPPORTED"
    assert resolve("qwen/qwen3.8-flash", "off", settings).reasoning == {"enabled":False}
