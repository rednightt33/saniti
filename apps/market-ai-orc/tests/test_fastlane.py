"""EXEC-FASTLANE B1/B2 (user 2026-10-13: "kita buat jalur baru saja untuk nanti A/B test", "harus selalu ada
fallback", "B1 + B2 berturut2"): lane "fast" answers a data question in one turn on the FASTLANE desk with the lane
note; the calls after the first think low; one call is cut at FAST_CALL_SECONDS and asked again lower; a refused data
size says how much fits. Without the switch, or with no lane named, nothing differs from before."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app import lanes
from app.main import create_app
from app.model_choices import current_model_choice, resolve
from app.openrouter_client import ProviderError
from app.orchestrator import (ANALYSIS_PATH_NOTE, FASTLANE_DRAFT_STEP, FASTLANE_NO_DRAFT_STEP, FASTLANE_NOTE,
                              RESEARCH_PATH_NOTE, AgentOrchestrator)
from app.schemas import AgentRunRequest
from app.tools import build_default_registry
from app.tools.data_planner import fit_hints
from app.tools.references import check_references_spec
from conftest import ANSWER, BASE_ENV, ScriptedClient, final_response, make_settings
from test_analysis_path import ON, Counting
from test_dataneed_orchestrator import Tools, answer, completed, flow

AUTH = {"Authorization": f"Bearer {BASE_ENV['MARKET_AI_ORC_API_KEY']}"}
FAST_ON = {**ON, "AI_ENABLE_FASTLANE": "true"}


class Checking(Counting):
    """The fake registry with the real check_references (the draft pre-check)."""

    def registry(self):
        registry = super().registry()
        registry.register(check_references_spec())
        return registry


class Recording(ScriptedClient):
    def __init__(self, responses):
        super().__init__(responses)
        self.options: list[dict] = []

    def create(self, payload, **options):
        self.options.append(dict(options))
        return super().create(payload, **options)


def run(script, *, lane, path=None, settings=FAST_ON, model=("deepseek/deepseek-v4.1-flash", "high"), tools=None):
    tools = tools or Counting([completed()])
    scripted = Recording(script)
    config = make_settings(**settings)
    orchestrator = AgentOrchestrator(config, scripted, tools.registry())
    tokens = (current_model_choice.set(resolve(*model, config)), lanes.current_lane.set(lane))
    try:
        result = orchestrator.run(AgentRunRequest(request_id="f1", message="Saham mana yang diakumulasi asing?",
                                                  analysis_path=path))
    finally:
        lanes.current_lane.reset(tokens[1])
        current_model_choice.reset(tokens[0])
    return result, scripted, tools


def names(payload):
    return {t["name"] for t in payload.get("tools", [])}


def test_the_fast_lane_answers_in_one_turn_on_its_desk_with_lower_reasoning_after_the_first_call() -> None:
    result, scripted, tools = run([*flow(), final_response(answer("Return YTD BBCA 12,35% dan BBRI turun 4,32%."))],
                                  lane=lanes.FAST, path="RESEARCH")
    assert result.status == "COMPLETED" and tools.modes == ["ANALYSIS"]
    first = json.dumps(scripted.payloads[0])
    assert FASTLANE_NOTE.format(draft_step=FASTLANE_DRAFT_STEP) in first
    assert RESEARCH_PATH_NOTE not in first and ANALYSIS_PATH_NOTE not in first
    assert "check_research_feasibility" not in names(scripted.payloads[0])
    assert "run_python" in names(scripted.payloads[0])
    assert scripted.payloads[0]["reasoning"] == {"effort": "high"}
    assert {json.dumps(p["reasoning"]) for p in scripted.payloads[1:]} == {json.dumps({"effort": "low"})}
    assert all(o == {"timeout": lanes.FAST_CALL_SECONDS, "attempts": 1} for o in scripted.options)
    assert result.execution.lane == "fast" and result.execution.research_plan is None


def test_without_the_draft_check_the_fast_lane_withdraws_check_references_and_its_note_step() -> None:
    """EXEC-FASTLANE B2b A/B (user 2026-10-14: "bedanya pra draft enable dan disable"); the standard lane keeps it."""
    script = [*flow(), final_response(answer("Return YTD BBCA 12,35% dan BBRI turun 4,32%."))]
    _, default, _ = run(script, lane=lanes.FAST, path="RESEARCH", tools=Checking([completed()]))
    assert "check_references" in names(default.payloads[0])  # AI_FASTLANE_DRAFT_CHECK default on
    result, scripted, _ = run(script, lane=lanes.FAST, path="RESEARCH", tools=Checking([completed()]),
                              settings={**FAST_ON, "AI_FASTLANE_DRAFT_CHECK": "false"})
    assert result.status == "COMPLETED"
    first = json.dumps(scripted.payloads[0])
    assert FASTLANE_NOTE.format(draft_step=FASTLANE_NO_DRAFT_STEP) in first and "check_references with a" not in first
    assert all("check_references" not in names(p) for p in scripted.payloads)
    _, standard, _ = run(script, lane=lanes.STANDARD, path="ANALYSIS", tools=Checking([completed()]),
                         settings={**FAST_ON, "AI_FASTLANE_DRAFT_CHECK": "false"})
    assert "check_references" in names(standard.payloads[0])


def test_a_call_cut_at_the_time_limit_is_asked_again_once_with_lower_reasoning() -> None:
    timeout = ProviderError("openrouter request timed out", code="PROVIDER_TIMEOUT")
    result, scripted, _ = run([timeout, final_response(ANSWER)], lane=lanes.FAST,
                              model=("deepseek/deepseek-v4.1-flash", "max"))
    assert result.status == "COMPLETED"
    assert scripted.payloads[1]["reasoning"] == {"effort": "low"}
    assert scripted.options == [{"timeout": lanes.FAST_CALL_SECONDS, "attempts": 1}, {}]  # one cut per run


@pytest.mark.parametrize("lane", [None, lanes.STANDARD])
def test_without_the_fast_lane_the_run_is_exactly_as_before(lane) -> None:
    """The fallback: no lane named, or the standard lane, sends the same payloads as a run with the switch off."""
    script = [*flow(), final_response(answer("Return YTD BBCA 12,35% dan BBRI turun 4,32%."))]
    off, off_client, _ = run(script, lane=None, path="ANALYSIS", settings=ON)
    on, on_client, _ = run(script, lane=lane, path="ANALYSIS")
    assert on_client.payloads == off_client.payloads and set(map(json.dumps, on_client.options)) == {"{}"}
    assert ANALYSIS_PATH_NOTE in json.dumps(on_client.payloads[0])
    assert on.execution.lane == lane and off.execution.lane is None
    assert "lane" not in off.model_dump(mode="json")["execution"]


def test_the_api_refuses_the_fast_lane_when_it_is_switched_off_and_lists_it_when_on() -> None:
    def client(settings):
        config = make_settings(**settings)
        return TestClient(create_app(config, orchestrator=AgentOrchestrator(
            config, ScriptedClient([final_response(ANSWER)]), build_default_registry())))
    with client({}) as off:
        refused = off.post("/v1/agent/run", headers=AUTH, json={"request_id": "l1", "message": "Halo", "lane": "fast"})
        assert refused.status_code == 400 and refused.json()["detail"]["code"] == "LANE_NOT_AVAILABLE"
        assert off.get("/v1/models", headers=AUTH).json()["lane_selection"] is False
    with client({"AI_ENABLE_FASTLANE": "true"}) as on:
        assert on.get("/v1/models", headers=AUTH).json()["lane_selection"] is True
        reply = on.post("/v1/agent/run", headers=AUTH, json={"request_id": "l2", "message": "Halo", "lane": "fast"})
        assert reply.status_code == 200 and reply.json()["execution"]["lane"] == "fast"


def test_a_refused_data_size_says_how_much_fits() -> None:
    """G1 (run edge_e5faf07f tried 105, 67, 128 and 122 parts against 64)."""
    hints = fit_hints([{"data_request_id": "broker_accum_1", "extraction_parts": 0,
                        "message": "The extraction needs 128 parts; the limit is 64."},
                       {"data_request_id": "prices", "extraction_parts": 3}], 64,
                      {"estimated_rows": 4_000_000, "limit_rows": 1_000_000})
    assert hints[0]["share_that_fits"] == 0.5 and "50%" in hints[0]["how"] and hints[0]["parts_limit"] == 64
    assert len(hints) == 2 and hints[1]["bundle"] and hints[1]["share_that_fits"] == 0.25
