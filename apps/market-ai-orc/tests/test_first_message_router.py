"""First-message router (user decisions 2026-10-04; ROUTER_BENCHMARK_2026-10-04.md, AI_ROUTER.md): every first message
is routed, also with the caller's analysis_path (which then only sets the depth of a data route); CHAT and FACT run
one step without warehouse data; a failed router runs one analysis step; later messages keep the conversation router;
mode 4's research steps run only after an analysis with figures from data (M79)."""
from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict

from app import conversation_router as router
from app.orchestrator import AgentOrchestrator, RunState
from app.schemas import AgentRunRequest, HistoryMessage
from app.tools.registry import ToolRegistry, ToolSpec
from conftest import make_settings
from test_mode4 import MODE4, FakeInner, first_round_script, response, run_result, stub

ROUTER_ON = {**MODE4, "AI_ENABLE_FIRST_TURN_ROUTER": "true"}


class RoutedInner(FakeInner):
    def __init__(self, script: dict[str, Any], route: str | None, **kwargs: Any) -> None:
        super().__init__(script, **kwargs)
        self.settings = make_settings(**ROUTER_ON)
        self.route, self.routed = route, []

    def classify_first(self, request_id: str, message: str):
        self.routed.append(message)
        return self.route, "r", {"status": "COMPLETED" if self.route else "FAILED", "input_tokens": 10,
                                 "output_tokens": 2, "cost": 0.0001, "latency_ms": 5}


def routed_stub(script: dict[str, Any], route: str | None) -> tuple[Any, RoutedInner]:
    wrapper, _ = stub(script)
    inner = RoutedInner(script, route)
    wrapper.inner, wrapper.first_router, wrapper.router = inner, True, True
    return wrapper, inner


def ask(path: str | None = None, **fields: Any) -> AgentRunRequest:
    return AgentRunRequest(request_id="q", message="bagaimana kabarmu", analysis_path=path, **fields)


@pytest.mark.parametrize("path", [None, "ANALYSIS", "RESEARCH", "MODE4"])
def test_chat_is_answered_as_chat_whatever_the_callers_path(path: str | None) -> None:
    wrapper, inner = routed_stub({"m4q": run_result("q-m4q", response("ANSWER", "Baik, ada yang bisa dibantu?"))},
                                 "CHAT")
    result = wrapper.run(ask(path))
    assert [r.request_id for r in inner.requests] == ["q-m4q"]  # one step, no analysis, plan or research
    assert result.execution.mode.route == "CHAT" and result.execution.mode.source == "ROUTER"
    assert result.mode4["turn_kind"] == "CONVERSATIONAL"


@pytest.mark.parametrize("route, path, expected", [
    ("ANALYSIS", None, "ANALYSIS"), ("RESEARCH", None, "RESEARCH"),
    ("EXPLORE", "ANALYSIS", "ANALYSIS"), ("ANALYSIS", "RESEARCH", "RESEARCH"),
    (None, None, "ANALYSIS"), (None, "RESEARCH", "RESEARCH"),  # router failed: one analysis step, or the caller's
])
def test_a_data_route_runs_at_the_callers_depth_else_the_routes(route, path, expected) -> None:
    wrapper, inner = routed_stub({"q": run_result("q", response("ANSWER", "Hasil."))}, route)
    result = wrapper.run(ask(path))
    assert [(r.request_id, r.analysis_path) for r in inner.requests] == [("q", expected)]
    assert result.execution.mode.route == (route or "ROUTER_FAILED") and result.execution.mode.name == expected


def test_explore_runs_mode4() -> None:
    wrapper, inner = routed_stub(first_round_script(), "EXPLORE")
    result = wrapper.run(ask())
    assert [r.request_id for r in inner.requests] == ["q-m4a", "q-m4b", "q-m4c", "q-m4d"]
    assert result.execution.mode.name == "MODE4" and result.execution.mode.route == "EXPLORE"


def test_a_later_message_keeps_the_conversation_router() -> None:
    wrapper, inner = routed_stub({"q": run_result("q", response("ANSWER", "x"))}, "CHAT")
    wrapper.run(AgentRunRequest(request_id="q", message="lanjut", analysis_path="ANALYSIS",
                                history=[HistoryMessage(role="user", content="a"),
                                         HistoryMessage(role="assistant", content="b")]))
    assert inner.routed == []


def test_mode4_research_does_not_run_after_an_answer_without_data() -> None:
    """M79 (g13: a web fact answered, then 23 minutes of research on unrelated data)."""
    script = first_round_script(m4a=run_result("q-m4a", response("ANSWER", "BBCA bank swasta.")).model_copy(
        update={"evidence_label": None}))
    wrapper, inner = stub(script)
    result = wrapper.run(AgentRunRequest(request_id="q", message="BBCA BUMN?", analysis_path="MODE4"))
    assert [r.request_id for r in inner.requests] == ["q-m4a"]
    assert any("tidak memakai angka dari data" in n for n in result.mode4["notes"])


class Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


def test_the_fact_step_gets_read_tools_and_the_web_fact_but_no_warehouse_data() -> None:
    registry = ToolRegistry()
    for name, effect in (("discover_catalog", "READS"), ("find_web_fact", "FETCHES_WEB"),
                         ("prepare_data_bundle", "FETCHES_DATA"), ("run_python", "COMPUTES")):
        registry.register(ToolSpec(name=name, description=name, arguments_model=Args, handler=lambda a: {},
                                   effect=effect))
    orchestrator = AgentOrchestrator(make_settings(**ROUTER_ON), object(), registry)
    for kind, expected in (("FACT", {"discover_catalog", "find_web_fact"}), ("CONVERSATIONAL", {"discover_catalog"})):
        state = RunState(request_id="q", started=0.0, input_items=[{"role": "user", "content": "m"}])
        token = router.current_turn_kind.set(kind)
        try:
            orchestrator._apply_turn_kind(state)
        finally:
            router.current_turn_kind.reset(token)
        assert state.tool_filter == expected


def test_every_benchmark_route_is_a_route_the_backend_knows() -> None:
    import json
    from pathlib import Path

    cases = json.loads((Path(__file__).parent / "fixtures/first_message_router_cases.json").read_text())
    for item in cases["development"] + cases["heldout"]:
        assert set(item["routes"]) <= set(router.FIRST_ROUTES), item


def test_through_the_api_a_greeting_is_one_step_and_a_data_question_takes_the_routes_depth() -> None:
    """End to end: AI_MODE_SWITCH=4 no longer decides a first message; the router call goes to the model first."""
    from app.main import create_app
    from conftest import ANSWER, final_response
    from test_mode4 import mode4_agent
    from test_modes import post

    settings = {**ROUTER_ON, "AI_MODE_SWITCH": "4"}
    runner, scripted, _ = mode4_agent([final_response({"route": "CHAT", "reason": "greeting"}), final_response(ANSWER)])
    runner.inner.settings = make_settings(**settings)
    app = create_app(make_settings(**settings), orchestrator=runner.inner)
    body = post(app, {"request_id": "f1", "message": "bagaimana kabarmu"})
    assert body["execution"]["mode"] == {"mode": 4, "name": "MODE4", "source": "ROUTER", "route": "CHAT"}
    assert scripted.payloads[0]["text"]["format"]["name"] == "first_message_route"
    assert scripted.payloads[0]["reasoning"] == {"effort": "low"} and "tools" not in scripted.payloads[0]
    assert len(scripted.payloads) == 2  # the router call and one step
    runner, scripted, _ = mode4_agent([final_response({"route": "ANALYSIS", "reason": "data"}),
                                       final_response(ANSWER)])
    runner.inner.settings = make_settings(**settings)
    app = create_app(make_settings(**settings), orchestrator=runner.inner)
    body = post(app, {"request_id": "f2", "message": "Berapa harga penutupan BBRI kemarin?"})
    assert body["execution"]["mode"] == {"mode": 2, "name": "ANALYSIS", "source": "ROUTER", "route": "ANALYSIS"}
    assert "mode4" not in body
