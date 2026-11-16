"""EXEC-MANUAL (user 2026-10-17, "buat nomor satu ya, saklar yang aktif. Ini hanya untuk mode troubleshooting aja ...
Ensure ada jalur fallback"): Claude answers the agent loop of a run that chose the manual model, through the same
tools and gates; a step with no reply goes to AI_MODEL; with the switch off nothing changes."""
from __future__ import annotations

import threading
import time

from fastapi.testclient import TestClient

from app import stop
from app.conversations import current_owner
from app.main import create_app
from app.manual_agent import MANUAL_MODEL, ManualAgent
from app.model_choices import ModelChoiceError, resolve
from app.orchestrator import AgentOrchestrator
from app.tools import build_default_registry
from app.tools.request_data import current_request_id
from conftest import ANSWER, BASE_ENV, ScriptedClient, final_response, make_settings, tool_call_response

AUTH = {"Authorization": f"Bearer {BASE_ENV['MARKET_AI_ORC_API_KEY']}", "X-Saniti-Owner": "owner-a"}
ON = {"AI_ENABLE_MANUAL_AGENT": "true", "AI_MANUAL_AGENT_WAIT_SECONDS": "30"}


def answer_when_waiting(agent: ManualAgent, replies: list[dict], seen: list[dict],
                        owner: str = "owner-a") -> threading.Thread:
    """Plays Claude: answers each waiting step of the owner in turn with the next reply, keeping the payload it saw."""
    answered: set[str] = set()

    def play() -> None:
        for reply in replies:
            for _ in range(500):
                steps = [s for s in agent.pending(owner) if s["step_id"] not in answered]
                if steps:
                    answered.add(steps[0]["step_id"])
                    seen.append(steps[0]["payload"])
                    assert agent.answer(owner, steps[0]["step_id"], reply) == "ANSWERED"
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
    assert agent.pending("owner-a") == []


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
    token, owner = current_request_id.set("sh1"), current_owner.set("owner-a")
    try:
        assert agent.answer("owner-a", "nope", {"output": []}) == "NOT_WAITING"
        result = agent.create({"model": MANUAL_MODEL, "input": []})
    finally:
        current_owner.reset(owner)
        current_request_id.reset(token)
    player.join(timeout=5)
    assert result["output"][-1]["name"] == "get_system_capabilities" and result["model"] == MANUAL_MODEL
    assert agent.answer("owner-a", "x", "not a response") == "INVALID"


def test_the_dev_routes_list_a_waiting_step_and_take_a_reply_over_http() -> None:
    settings = make_settings(**ON)
    agent = ManualAgent(ScriptedClient([]), settings, poll_seconds=0.01)
    client = TestClient(create_app(settings, orchestrator=AgentOrchestrator(settings, agent, build_default_registry()),
                                   manual_agent=agent))
    result: list[dict] = []

    def wait() -> None:
        token, owner = current_request_id.set("http1"), current_owner.set("owner-a")
        try:
            result.append(agent.create({"model": MANUAL_MODEL, "input": []}))
        finally:
            current_owner.reset(owner)
            current_request_id.reset(token)
    waiter = threading.Thread(target=wait, daemon=True)
    with client:
        waiter.start()
        for _ in range(200):
            steps = client.get("/v1/dev/manual/steps", headers=AUTH).json()["steps"]
            if steps:
                break
            time.sleep(0.01)
        step = steps[0]["step_id"]
        assert steps[0]["request_id"] == "http1" and steps[0]["payload"]["model"] == MANUAL_MODEL
        assert client.post(f"/v1/dev/manual/steps/{step}", headers=AUTH, json={"response": "x"}).status_code == 422
        reply = client.post(f"/v1/dev/manual/steps/{step}", headers=AUTH,
                            json={"response": tool_call_response("get_system_capabilities")})
        assert reply.status_code == 200 and reply.json() == {"status": "ANSWERED"}
        waiter.join(timeout=5)
        assert client.post(f"/v1/dev/manual/steps/{step}", headers=AUTH,
                           json={"response": {"output": []}}).status_code == 409
    assert result[0]["output"][-1]["name"] == "get_system_capabilities"


def waiting_step(agent: ManualAgent, owner: str | None, request_id: str) -> tuple[threading.Thread, list[dict]]:
    """A manual step of the given owner's run, waiting in a thread (its result lands in the list)."""
    result: list[dict] = []

    def wait() -> None:
        token, owner_token = current_request_id.set(request_id), current_owner.set(owner)
        try:
            result.append(agent.create({"model": MANUAL_MODEL, "input": []}))
        finally:
            current_owner.reset(owner_token)
            current_request_id.reset(token)
    thread = threading.Thread(target=wait, daemon=True)
    thread.start()
    for _ in range(200):
        if any(s.request_id == request_id for s in list(agent._steps.values())):
            break
        time.sleep(0.01)
    return thread, result


def test_m474_a_step_is_listed_and_answered_only_for_its_own_owner() -> None:
    settings = make_settings(**ON)
    agent = ManualAgent(ScriptedClient([]), settings, poll_seconds=0.01)
    thread_a, result_a = waiting_step(agent, "owner-a", "own-a")
    thread_n, result_n = waiting_step(agent, None, "own-none")  # a step outside any owned run
    try:
        mine = agent.pending("owner-a")
        assert [s["request_id"] for s in mine] == ["own-a"]
        assert agent.pending("owner-b") == [] and agent.pending(None) == []
        step_id = mine[0]["step_id"]
        none_id = next(s.step_id for s in agent._steps.values() if s.request_id == "own-none")
        reply = tool_call_response("get_system_capabilities")
        # owner B knows A's step id: the same answer as an unknown step, and A's step keeps waiting
        assert agent.answer("owner-b", step_id, reply) == agent.answer("owner-b", "unknown", reply) == "NOT_WAITING"
        assert agent.answer(None, none_id, reply) == "NOT_WAITING" and agent.answer("owner-a", none_id, reply) \
            == "NOT_WAITING"
        assert [s["step_id"] for s in agent.pending("owner-a")] == [step_id]
        assert agent.answer("owner-a", step_id, reply) == "ANSWERED"
        thread_a.join(timeout=5)
        assert result_a[0]["output"][-1]["name"] == "get_system_capabilities"
    finally:
        for step in list(agent._steps.values()):  # release the owner-less step
            step.reply = {"output": []}
            step.done.set()
        thread_n.join(timeout=5)


def test_m474_the_dev_routes_read_the_owner_and_refuse_a_missing_one() -> None:
    settings = make_settings(**ON)
    agent = ManualAgent(ScriptedClient([]), settings, poll_seconds=0.01)
    client = TestClient(create_app(settings, orchestrator=AgentOrchestrator(settings, agent, build_default_registry()),
                                   manual_agent=agent))
    bare = {"Authorization": AUTH["Authorization"]}
    other = {**bare, "X-Saniti-Owner": "owner-b"}
    with client:
        thread, result = waiting_step(agent, "owner-a", "http-own")
        listed = client.get("/v1/dev/manual/steps", headers=AUTH).json()["steps"]
        assert [s["request_id"] for s in listed] == ["http-own"]
        assert client.get("/v1/dev/manual/steps", headers=other).json()["steps"] == []
        for headers in (bare, {**bare, "X-Saniti-Owner": "  "}):
            refused = client.get("/v1/dev/manual/steps", headers=headers)
            assert refused.status_code == 400 and refused.json()["error"]["code"] == "OWNER_REQUIRED"
            posted = client.post(f"/v1/dev/manual/steps/{listed[0]['step_id']}", headers=headers,
                                 json={"response": {"output": []}})
            assert posted.status_code == 400 and posted.json()["error"]["code"] == "OWNER_REQUIRED"
        stranger = client.post(f"/v1/dev/manual/steps/{listed[0]['step_id']}", headers=other,
                               json={"response": {"output": []}})
        unknown = client.post("/v1/dev/manual/steps/0000000000000000", headers=other,
                              json={"response": {"output": []}})
        assert stranger.status_code == unknown.status_code == 409 and stranger.json() == unknown.json()
        mine = client.post(f"/v1/dev/manual/steps/{listed[0]['step_id']}", headers=AUTH,
                           json={"response": tool_call_response("get_system_capabilities")})
        assert mine.status_code == 200
        thread.join(timeout=5)
    assert result[0]["output"][-1]["name"] == "get_system_capabilities"


def test_m474_a_manual_run_stores_the_owner_of_its_request() -> None:
    """End to end: the step of a run posted by owner A is visible to A only (the owner comes from the run route)."""
    settings = make_settings(**ON)
    agent = ManualAgent(ScriptedClient([]), settings, poll_seconds=0.01)
    orchestrator = AgentOrchestrator(settings, agent, build_default_registry())
    seen: list[dict] = []
    leaked: list[list] = []

    def watch_b() -> None:
        for _ in range(300):
            leaked.append(agent.pending("owner-b"))
            time.sleep(0.005)
    spy = threading.Thread(target=watch_b, daemon=True)
    spy.start()
    player = answer_when_waiting(agent, [final_response(ANSWER)], seen, owner="owner-a")
    client = TestClient(create_app(settings, orchestrator=orchestrator, manual_agent=agent))
    with client:
        reply = client.post("/v1/agent/run", headers=AUTH, json={
            "request_id": "man-owned", "message": "Apa yang bisa kamu bantu?", "model": MANUAL_MODEL})
    player.join(timeout=5)
    spy.join(timeout=5)
    assert reply.status_code == 200 and reply.json()["status"] == "COMPLETED" and len(seen) == 1
    assert all(found == [] for found in leaked)
