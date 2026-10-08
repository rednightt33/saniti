"""IP1 Stage D in the orchestrator (AI_ENABLE_POINT_IN_TIME): data_need_spec/v2 carries time_basis, the TIME BASIS
rules exist only with it, and an answer that rests on descriptive data after a point-in-time refusal says so."""
from __future__ import annotations

from app.orchestrator import markdown_prompt  # noqa: E402 - prompt audit C (2026-10-05)

import re
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict

from app.orchestrator import (PIT_FALLBACK_LINE, POINT_IN_TIME_RULES, WARNING_LINES, AgentOrchestrator,
                              build_system_prompt)
from app.schemas import AgentRunRequest
from app.tools import ToolSpec, build_default_registry
from app.tools.analysis import SandboxClient
from app.tools.request_data import GovernorClient
from conftest import ScriptedClient, final_response, make_settings
from test_dataneed_orchestrator import NEED, Tools, answer, call, completed, flow

REFUSED = {"status": "REVISION_REQUIRED", "need_id": None, "issues": [{
    "data_request_id": "data_request_1_A", "code": "POINT_IN_TIME_UNAVAILABLE",
    "field_path": "relationships[0].relationship_id",
    "rejected_value": "IDX_Stock_Universe_History history answers dates from 2026-09-29"}],
    "next_action": "REVISE_DATA_NEED_SPEC"}


def registry_defs(point_in_time: bool, composite: bool = True) -> dict[str, Any]:
    t = httpx.MockTransport(lambda r: httpx.Response(404))
    registry = build_default_registry(
        object(), cursor_secret=b"x" * 32, governor_client=GovernorClient("http://g", "k" * 40, 90, transport=t),
        sandbox_client=SandboxClient("http://s", "s" * 40, 45, 20, transport=t), dataneed_enabled=True,
        plan_feasibility=True, composite_keys=composite, point_in_time=point_in_time)
    return {d["name"]: d["parameters"] for d in registry.definitions()}


def test_time_basis_is_a_required_v2_field_only_behind_the_flag() -> None:
    on, off, v1 = registry_defs(True), registry_defs(False), registry_defs(True, composite=False)
    for name in ("submit_data_need_spec", "check_data_feasibility"):
        assert on[name]["properties"]["time_basis"]["enum"] == ["HISTORICAL_DESCRIPTIVE", "POINT_IN_TIME"]
        assert "time_basis" in on[name]["required"]
        assert "time_basis" not in off[name]["properties"]
        assert "time_basis" not in v1[name]["properties"]  # time_basis is a data_need_spec/v2 field


def test_the_time_basis_rules_are_in_the_prompt_only_when_on() -> None:
    assert build_system_prompt(False, True, point_in_time=True).endswith(markdown_prompt(POINT_IN_TIME_RULES))
    assert markdown_prompt(POINT_IN_TIME_RULES) not in build_system_prompt(False, True)
    # the rules add no source numbers to the system prompt (list markers are skipped)
    assert not any(ch.isdigit() for ch in re.sub(r"(?m)^\d+\. ", "", POINT_IN_TIME_RULES))


class PitSpecArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: str
    research_governance: dict | None = None
    time_basis: str


class PitTools(Tools):
    """The fake DataNeed tools with a submit_data_need_spec that carries time_basis; point-in-time is refused."""

    def registry(self):
        registry = super().registry()
        registry._tools["submit_data_need_spec"] = ToolSpec(
            name="submit_data_need_spec", description="submit_data_need_spec", arguments_model=PitSpecArgs,
            handler=lambda a: REFUSED if a.time_basis == "POINT_IN_TIME" else
            {"status": "APPROVED", "need_id": NEED, "revision": 1, "research_governance": None})
        return registry


def pit_flow(basis: str) -> list:
    steps = flow()
    steps[0] = call("submit_data_need_spec", {"mode": "ANALYSIS", "research_governance": None,
                                              "time_basis": basis}, "c1")
    return steps


def run(script: list, completion: dict[str, Any]):
    agent = AgentOrchestrator(make_settings(AI_ENABLE_DATANEED="true"), ScriptedClient(script),
                              PitTools([completion]).registry())
    assert agent.point_in_time and agent.system_prompt.endswith(markdown_prompt(POINT_IN_TIME_RULES))
    return agent.run(AgentRunRequest(request_id="pit", message="Backtest tanpa look-ahead sektor tambang"))


def test_a_descriptive_answer_after_a_point_in_time_refusal_is_disclosed() -> None:
    refused = call("submit_data_need_spec", {"mode": "ANALYSIS", "research_governance": None,
                                             "time_basis": "POINT_IN_TIME"}, "c0")
    result = run([refused] + pit_flow("HISTORICAL_DESCRIPTIVE") + [final_response(answer("BBCA naik 12,35%."))],
                 completed(time_basis="HISTORICAL_DESCRIPTIVE"))
    assert result.response.response_type == "ANSWER"
    line = PIT_FALLBACK_LINE.format(detail=REFUSED["issues"][0]["rejected_value"])
    assert line in result.response.limitations
    assert result.execution.number_provenance.unsupported == []  # the detail's date is not a claim of the answer


def test_no_refusal_no_disclosure() -> None:
    result = run(pit_flow("HISTORICAL_DESCRIPTIVE") + [final_response(answer("BBCA naik 12,35%."))],
                 completed(time_basis="HISTORICAL_DESCRIPTIVE"))
    assert not any("Point-in-time data was requested" in x for x in result.response.limitations)


def test_the_current_state_column_warning_is_disclosed() -> None:
    assert "nilai hari ini" in WARNING_LINES["CURRENT_STATE_COLUMN"]
    result = run(pit_flow("HISTORICAL_DESCRIPTIVE") + [final_response(answer("BBCA naik 12,35%."))],
                 completed(time_basis="HISTORICAL_DESCRIPTIVE", warnings=["CURRENT_STATE_COLUMN"]))
    assert WARNING_LINES["CURRENT_STATE_COLUMN"] in result.response.limitations


def test_without_the_time_basis_field_the_orchestrator_is_unchanged() -> None:
    agent = AgentOrchestrator(make_settings(AI_ENABLE_DATANEED="true"), ScriptedClient([]), Tools([]).registry())
    assert agent.point_in_time is False and markdown_prompt(POINT_IN_TIME_RULES) not in agent.system_prompt
