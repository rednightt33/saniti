"""EXEC-MANUAL (user 2026-10-17, "buat nomor satu ya, saklar yang aktif. Ini hanya untuk mode troubleshooting aja ...
Ensure ada jalur fallback"): Claude answers the agent loop of a run that chose the manual model, through the same
tools and gates; a step with no reply goes to AI_MODEL; with the switch off nothing changes."""
from __future__ import annotations

import threading
import time

from fastapi.testclient import TestClient

from app import stop
from app.main import create_app
from app.manual_agent import MANUAL_MODEL, ManualAgent
from app.model_choices import ModelChoiceError, resolve
from app.orchestrator import AgentOrchestrator
from app.tools import build_default_registry
from app.tools.request_data import current_request_id
from conftest import ANSWER, BASE_ENV, ScriptedClient, final_response, make_settings, tool_call_response

AUTH = {"Authorization": f"Bearer {BASE_ENV['MARKET_AI_ORC_API_KEY']}"}
ON = {"AI_ENABLE_MANUAL_AGENT": "true", "AI_MANUAL_AGENT_WAIT_SECONDS": "30"}


def answer_when_waiting(agent: ManualAgent, replies: list[dict], seen: list[dict]) -> threading.Thread:
    """Plays Claude: answers each waiting step in turn with the next reply, keeping the payload it saw."""
    answered: set[str] = set()

    def play() -> None:
        for reply in replies:
            for _ in range(500):
                steps = [s for s in agent.pending() if s["step_id"] not in answered]
                if steps:
                    answered.add(steps[0]["step_id"])
                    seen.append(steps[0]["payload"])
                    assert agent.answer(steps[0]["step_id"], reply) == "ANSWERED"
                    break
                time.sleep(0.01)
    thread = threading.Thread(target=play, daemon=True)
    thread.start()
    return thread


def test_the_manual_model_is_offered_only_with_its_switch() -> None:
    off, on = make_settings(), make_settings(**ON)
    try:
        resolve(MANUAL_MODEL, None, off)
        raise AssertionError("offered with the switch off")
    except ModelChoiceError as exc:
        assert exc.code == "MODEL_NOT_ALLOWED"
    assert resolve(MANUAL_MODEL, None, on).model == MANUAL_MODEL
    for settings in (off, on):
        client = TestClient(create_app(settings, orchestrator=AgentOrchestrator(settings, ScriptedClient([]),
                                                                                build_default_registry())))
        with client:
            models = [m["model"] for m in client.get("/v1/models", headers=AUTH).json()["models"]]
            steps = client.get("/v1/dev/manual/steps", headers=AUTH)
        assert (MANUAL_MODEL in models) is (settings is on)
        assert steps.status_code == 404  # no manual agent was built for these apps


def test_a_manual_run_goes_through_the_same_loop_with_claudes_replies() -> None:
    settings = make_settings(**ON)
    real = ScriptedClient([])  # OpenRouter is never called for the loop
    agent = ManualAgent(real, settings, poll_seconds=0.01)
    orchestrator = AgentOrchestrator(settings, agent, build_default_registry())
    seen: list[dict] = []
    player = answer_when_waiting(agent, [tool_call_response("get_system_capabilities"), final_response(ANSWER)],
                                 seen)
    client = TestClient(create_app(settings, orchestrator=orchestrator, manual_agent=agent))
    with client:
        reply = client.post("/v1/agent/run", headers=AUTH, json={
            "request_id": "man1", "message": "Apa yang bisa kamu bantu?", "model": MANUAL_MODEL})
    player.join(timeout=5)
    assert reply.status_code == 200 and reply.json()["status"] == "COMPLETED"
    assert real.payloads == []
    assert [p["model"] for p in seen] == [MANUAL_MODEL] * 2
    assert any(t.get("name") == "get_system_capabilities" for t in seen[0]["tools"])  # the model's own tools
    assert seen[1]["input"][-1]["type"] == "function_call_output"  # the tool result came back to Claude
    assert len(seen[1]["input"]) > len(seen[0]["input"])


def test_a_step_without_a_reply_falls_back_to_the_server_model_for_the_rest_of_the_run() -> None:
    settings = make_settings(**ON)
    real = ScriptedClient([final_response(ANSWER), final_response(ANSWER)])
    now = [0.0]
    agent = ManualAgent(real, settings, clock=lambda: now[0], poll_seconds=0.001)

    def later() -> None:
        time.sleep(0.05)
        now[0] = 10_000.0
    threading.Thread(target=later, daemon=True).start()
    token = current_request_id.set("fb1")
    try:
        first = agent.create({"model": MANUAL_MODEL, "reasoning": {"enabled": True}, "input": []})
        second = agent.create({"model": MANUAL_MODEL, "reasoning": {"enabled": True}, "input": []})
    finally:
        current_request_id.reset(token)
    assert first == final_response(ANSWER) and second == final_response(ANSWER)
    assert [p["model"] for p in real.payloads] == [settings.ai_model] * 2
    assert real.payloads[0]["reasoning"] == settings.reasoning(settings.ai_reasoning_effort)
    assert agent.pending() == []


def test_the_stop_button_ends_a_wait_and_other_calls_pass_through() -> None:
    settings = make_settings(**ON)
    real = ScriptedClient([final_response(ANSWER)])
    agent = ManualAgent(real, settings, poll_seconds=0.01)
    assert agent.create({"model": settings.ai_model, "input": []}) == final_response(ANSWER)  # a router call
    with stop.running("st1", None) as flag:
        threading.Timer(0.05, flag.set).start()
        empty = agent.create({"model": MANUAL_MODEL, "input": []})
    assert empty["output"] == [] and len(real.payloads) == 1


def test_a_reply_must_have_the_model_shape_and_answers_once() -> None:
    settings = make_settings(**ON)
    agent = ManualAgent(ScriptedClient([]), settings, poll_seconds=0.01)
    seen: list[dict] = []
    player = answer_when_waiting(agent, [tool_call_response("get_system_capabilities")], seen)
    token = current_request_id.set("sh1")
    try:
        assert agent.answer("nope", {"output": []}) == "NOT_WAITING"
        result = agent.create({"model": MANUAL_MODEL, "input": []})
    finally:
        current_request_id.reset(token)
    player.join(timeout=5)
    assert result["output"][-1]["name"] == "get_system_capabilities" and result["model"] == MANUAL_MODEL
    assert agent.answer("x", "not a response") == "INVALID"
