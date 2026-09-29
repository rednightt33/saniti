"""Caller-chosen path (AI_ENABLE_ANALYSIS_PATH): a request may fix ANALYSIS or RESEARCH. The fixed mode is enforced on
submit_data_need_spec (the other mode is refused before the sandbox sees it), ANALYSIS proposes no Research Plan and
its answer carries the descriptive-statistics line, and without the flag nothing changes."""
from __future__ import annotations

import dataclasses
import json

from fastapi.testclient import TestClient

from app.main import create_app
from app.orchestrator import ANALYSIS_PATH_LINE, ANALYSIS_PATH_NOTE, RESEARCH_PATH_NOTE, AgentOrchestrator
from app.schemas import AgentRunRequest
from conftest import BASE_ENV, ScriptedClient, final_response, make_settings
from test_dataneed_orchestrator import Tools, answer, call, completed, flow
from test_research_findings import PLAN

ON = {"AI_ENABLE_DATANEED": "true", "AI_REQUIRE_RESEARCH_PLAN_CONFIRMATION": "true",
      "AI_RESEARCH_PLAN_SIGNING_KEY": "0123456789abcdef" * 4, "AI_ENABLE_ANALYSIS_PATH": "true"}
AUTH = {"Authorization": f"Bearer {BASE_ENV['MARKET_AI_ORC_API_KEY']}"}


class Counting(Tools):
    """Records the modes that reached the (fake) sandbox."""

    def registry(self):
        registry = super().registry()
        spec = registry.get("submit_data_need_spec")
        self.modes: list[str] = []

        def record(arguments):
            self.modes.append(arguments.mode)
            return spec.handler(arguments)

        registry._tools[spec.name] = dataclasses.replace(spec, handler=record)
        return registry


def agent(script: list, tools: Tools, **settings: str) -> tuple[AgentOrchestrator, ScriptedClient]:
    scripted = ScriptedClient(script)
    return AgentOrchestrator(make_settings(**{**ON, **settings}), scripted, tools.registry()), scripted


def test_a_fixed_analysis_path_refuses_research_and_labels_the_answer() -> None:
    tools = Counting([completed()])
    script = [call("submit_data_need_spec", {"mode": "RESEARCH", "research_governance": {"hypothesis_id": "h1"}},
                   "c0"), *flow(), final_response(answer("Return YTD BBCA 12,35% dan BBRI turun 4,32%."))]
    orchestrator, scripted = agent(script, tools)
    result = orchestrator.run(AgentRunRequest(request_id="p1", message="Broker mana ...?", analysis_path="ANALYSIS"))
    assert result.status == "COMPLETED" and tools.modes == ["ANALYSIS"]  # the RESEARCH need never reached it
    refusal = json.dumps(scripted.payloads[1])
    assert "PATH_MISMATCH" in refusal and "fixed this request to the ANALYSIS path" in refusal
    assert ANALYSIS_PATH_NOTE in json.dumps(scripted.payloads[0])
    assert ANALYSIS_PATH_LINE in result.response.limitations
    path = result.execution.analysis_path
    assert path.requested == "ANALYSIS" and path.source == "CALLER" and path.mismatches_refused == 1
    assert result.execution.research_plan is None  # no plan turn, so a pending SERVER-mode plan stays untouched
    assert "check_data_feasibility" not in {t["name"] for t in scripted.payloads[0].get("tools", [])}


def test_a_fixed_analysis_path_allows_no_research_plan() -> None:
    plan = {"response_type": "RESEARCH_PLAN_CONFIRMATION", "answer": "Rencana", "clarification_question": None,
            "assumptions": [], "limitations": [], "research_plan": PLAN}
    orchestrator, scripted = agent([final_response(plan), final_response(answer("Halo."))], Tools([]))
    result = orchestrator.run(AgentRunRequest(request_id="p2", message="Halo", analysis_path="ANALYSIS"))
    assert result.response.response_type == "ANSWER"
    assert "the caller fixed the ANALYSIS path" in json.dumps(scripted.payloads[1])


def test_a_fixed_research_path_refuses_analysis_and_asks_for_a_plan() -> None:
    tools = Counting([])
    clarify = {"response_type": "CLARIFICATION", "answer": "Perlu periode.", "clarification_question": "Periode?",
               "assumptions": [], "limitations": []}
    orchestrator, scripted = agent([call("submit_data_need_spec", {"mode": "ANALYSIS", "research_governance": None},
                                         "c0"), final_response(clarify)], tools)
    result = orchestrator.run(AgentRunRequest(request_id="p3", message="Pola?", analysis_path="RESEARCH"))
    # the plan turn offers no data-need tool at all, so the ANALYSIS need is refused before the mode check
    assert tools.modes == [] and result.execution.analysis_path.requested == "RESEARCH"
    assert "submit_data_need_spec" not in {t["name"] for t in scripted.payloads[0].get("tools", [])}
    assert RESEARCH_PATH_NOTE in json.dumps(scripted.payloads[0])
    assert result.execution.research_plan.turn == "PROPOSE"


def test_without_the_path_nothing_changes() -> None:
    orchestrator, _ = agent([*flow(), final_response(answer("Return YTD BBCA 12,35% dan BBRI turun 4,32%."))],
                            Tools([completed()]))
    result = orchestrator.run(AgentRunRequest(request_id="p4", message="Return YTD?"))
    assert "analysis_path" not in result.model_dump(mode="json")["execution"]
    assert ANALYSIS_PATH_LINE not in result.response.limitations
    off, _ = agent([], Tools([]), AI_ENABLE_ANALYSIS_PATH="false")
    assert off.analysis_path is False
    # without plan confirmation the path cannot be enforced and stays inactive
    assert agent([], Tools([]), AI_REQUIRE_RESEARCH_PLAN_CONFIRMATION="false")[0].analysis_path is False


def test_the_api_refuses_a_path_it_cannot_honour() -> None:
    settings = make_settings()
    off = AgentOrchestrator(settings, ScriptedClient([]), Tools([]).registry())
    with TestClient(create_app(settings, orchestrator=off)) as client:
        body = {"request_id": "p5", "message": "x", "analysis_path": "ANALYSIS"}
        response = client.post("/v1/agent/run", json=body, headers=AUTH)
        assert response.status_code == 400 and response.json()["detail"]["code"] == "ANALYSIS_PATH_UNAVAILABLE"
    on, _ = agent([], Tools([]))
    with TestClient(create_app(make_settings(**ON), orchestrator=on)) as client:
        body = {"request_id": "p6", "message": "Setuju", "history_mode": "SERVER", "analysis_path": "ANALYSIS",
                "plan_reply": {"plan_id": "rp_" + "a" * 24, "action": "APPROVE"}}
        response = client.post("/v1/agent/run", json=body, headers=AUTH)
        assert response.status_code == 400 and response.json()["detail"]["code"] == "ANALYSIS_PATH_CONFLICT"
        assert client.post("/v1/agent/run", json={**body, "analysis_path": "BOTH"}, headers=AUTH).status_code == 422
