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
from app.user_texts import ANALYSIS_PATH_LINE, SESSION_NOT_COMPLETED_LINE, convention_numbers_line
from conftest import ANSWER, BASE_ENV, ScriptedClient, final_response, make_settings
from test_analysis_path import ON, Counting
from test_dataneed_orchestrator import BUNDLE, NEED, SESSION, Tools, answer, call, completed, flow

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


# ------------------------------------------------------------------------------------------ B3 exploratory tests

EXPLORED = {"version": 1, "policy": "BENJAMINI_HOCHBERG", "alpha": 0.05, "count": 3, "held": 1, "unstable": 1,
            "small_samples": 0, "tests": []}
EXPLORE_ON = {**FAST_ON, "AI_FASTLANE_EXPLORE_TESTS": "true"}


def explore_run(*, lane=lanes.FAST, settings=EXPLORE_ON, capable=True, mode=None, turn_kind=None, explored=EXPLORED):
    from app import conversation_router as router

    tools = Counting([completed(explore_tests=explored) if explored else completed()])
    scripted = Recording([*flow(), final_response(answer("Return YTD BBCA 12,35% dan BBRI turun 4,32%."))])
    config = make_settings(**settings)
    orchestrator = AgentOrchestrator(config, scripted, tools.registry(), explore_tests=capable)
    tokens = [(current_model_choice, current_model_choice.set(resolve("deepseek/deepseek-v4.1-flash", "high", config))),
              (lanes.current_lane, lanes.current_lane.set(lane)),
              (lanes.current_explore_mode, lanes.current_explore_mode.set(mode)),
              (router.current_turn_kind, router.current_turn_kind.set(turn_kind))]
    try:
        result = orchestrator.run(AgentRunRequest(request_id="f1", message="Apakah akumulasi asing diikuti kenaikan?",
                                                  analysis_path="ANALYSIS"))
    finally:
        for variable, token in reversed(tokens):
            variable.reset(token)
    return result, scripted


def test_explore_tests_tell_the_answer_mode_to_test_only_the_question_and_add_the_systems_evidence_line() -> None:
    from app.orchestrator import EXPLORE_ANSWER_NOTE
    from app.user_texts import explore_evidence_line

    result, scripted = explore_run()
    first = json.dumps(scripted.payloads[0])
    assert json.dumps(EXPLORE_ANSWER_NOTE)[1:-1] in first and "saniti.explore_test" in first
    assert "conditional_distribution" not in first  # the library list is for insight only
    # Mode Jawab v2: the model tests with its own code; only insight requires explore_test
    assert "never with scipy" not in json.dumps(EXPLORE_ANSWER_NOTE) and "scipy and statsmodels are available" in first
    line = explore_evidence_line(3, 1, 1, 0)
    assert result.status == "COMPLETED" and line in result.response.limitations
    # the analysis path's "no significance test" line would contradict the reported tests
    assert ANALYSIS_PATH_LINE not in result.response.limitations
    assert "3 uji dicoba, 1 bertahan" in line and "tidak konsisten" in line


def test_the_insight_mode_lists_the_research_library_for_the_explore_route_and_the_insight_turn() -> None:
    from app.research_library import LIBRARY

    for kwargs in ({"mode": lanes.INSIGHT}, {"turn_kind": "INSIGHT"}):
        _, scripted = explore_run(**kwargs)
        first = json.dumps(scripted.payloads[0])
        assert "at most 5 angles" in first and all(m["method_id"] in first for m in LIBRARY), kwargs
        assert "stability=True" in first


def test_without_tests_recorded_nothing_is_said_and_none_held_says_so() -> None:
    from app.user_texts import EXPLORE_NONE_HELD, explore_evidence_line

    result, _ = explore_run(explored=None)
    assert not any("Bukti statistik" in line for line in result.response.limitations)
    # Mode Jawab v2: no recorded test, so the line says the model's own code computed any test
    from app.user_texts import FASTLANE_ANSWER_LINE
    assert FASTLANE_ANSWER_LINE in result.response.limitations and ANALYSIS_PATH_LINE not in result.response.limitations
    assert EXPLORE_NONE_HELD in explore_evidence_line(4, 0, 0, 2) and "2 uji sampel" in explore_evidence_line(4, 0, 0, 2)


@pytest.mark.parametrize("kwargs", [{"settings": FAST_ON}, {"capable": False}, {"lane": lanes.STANDARD},
                                    {"lane": None}])
def test_without_the_switch_the_sandbox_or_the_fast_lane_nothing_changes(kwargs) -> None:
    result, scripted = explore_run(**kwargs)
    payloads = json.dumps(scripted.payloads)
    assert "saniti.explore_test" not in payloads and "the user asks for insight" not in payloads
    assert not any("Bukti statistik" in line for line in result.response.limitations)
    assert ANALYSIS_PATH_LINE in result.response.limitations or kwargs.get("lane") != lanes.FAST


def test_the_first_message_router_reading_sets_the_explore_mode_only_for_its_run() -> None:
    from app.mode4 import _reading

    with _reading(None, None, lanes.INSIGHT):
        assert lanes.current_explore_mode.get() == lanes.INSIGHT
    assert lanes.current_explore_mode.get() is None
    with _reading(None, None):
        assert lanes.current_explore_mode.get() is None


def test_mode_jawab_v2_insight_keeps_the_explore_rule_and_the_fast_lane_drops_get_system_capabilities() -> None:
    from app.orchestrator import EXPLORE_TEST_RULE, explore_note
    from app.tool_desks import DESKS

    assert EXPLORE_TEST_RULE in explore_note(lanes.INSIGHT) and EXPLORE_TEST_RULE not in explore_note(lanes.ANSWER)
    assert "get_system_capabilities" in DESKS["FASTLANE"].never and "preview_table_rows" not in DESKS["FASTLANE"].never
    assert "check_data_feasibility" in DESKS["FASTLANE"].must
    assert "get_system_capabilities" in FASTLANE_NOTE and "get_system_capabilities" not in DESKS["ANALYSIS"].never


# --- EXEC-FASTLANE F1, F2 and the section caps (user 2026-10-14: "Yg lain sudah OK") -------------------------------

SECOND = "sess_" + "6" * 24
LONG = {"AI_MAX_TOOL_ITERATIONS": "20", "AI_MAX_TOOL_CALLS": "20"}


class TwoSessions(Counting):
    """open_analysis_session gives a new session each time (the data need sent again); run_python takes code."""

    def registry(self):
        import dataclasses

        from pydantic import BaseModel, ConfigDict

        class CodeArgs(BaseModel):
            model_config = ConfigDict(extra="forbid")
            session_id: str
            code: str | None = None

        registry = super().registry()
        sessions = [SESSION, SECOND]
        opened = registry.get("open_analysis_session")
        registry._tools[opened.name] = dataclasses.replace(opened, handler=lambda a: {
            "session_id": sessions.pop(0) if sessions else SECOND, "status": "ACTIVE", "bundle_id": BUNDLE,
            "need_id": NEED})
        python = registry.get("run_python")
        registry._tools[python.name] = dataclasses.replace(python, arguments_model=CodeArgs, handler=lambda a: {
            "execution_id": "exe_1", "session_id": a.session_id, "status": "OK", "stdout": "", "outputs": []})
        return registry


def resubmitted() -> list:
    return [*flow(complete=False),
            call("submit_data_need_spec", {"mode": "ANALYSIS", "research_governance": None}, "d1"),
            call("prepare_data_bundle", {"need_id": NEED}, "d2"), call("open_analysis_session",
                                                                       {"input_bundle_id": BUNDLE}, "d3"),
            call("run_python", {"session_id": SECOND}, "d4"), call("complete_analysis", {"session_id": SECOND}, "d5")]


@pytest.mark.parametrize("settings, lane, kept", [({**FAST_ON, **LONG, "AI_FASTLANE_ABANDONED_SESSIONS": "true"},
                                                   lanes.FAST, True),
                                                  ({**FAST_ON, **LONG}, lanes.FAST, False),
                                                  ({**FAST_ON, **LONG, "AI_FASTLANE_ABANDONED_SESSIONS": "true"},
                                                   lanes.STANDARD, False)])
def test_f1_a_session_left_for_a_completed_one_blocks_only_without_the_switch(settings, lane, kept) -> None:
    """ma-jawab2-20261014-v2 j2: the data need was sent again, the first session ran code and was left."""
    final = final_response(answer("Return YTD BBCA 12,35% dan BBRI turun 4,32%."))
    result, _, _ = run([*resubmitted(), final, final], lane=lane, path="ANALYSIS", settings=settings,
                       tools=TwoSessions([completed()]))
    assert (result.response.response_type == "ANSWER") is kept, result.response
    assert (SESSION_NOT_COMPLETED_LINE in result.response.limitations) is not kept


def test_f1_a_left_session_still_blocks_when_no_session_completed() -> None:
    final = final_response(answer("Return YTD BBCA 12,35% dan BBRI turun 4,32%."))
    result, _, _ = run([*flow(complete=False), final, final], lane=lanes.FAST, path="ANALYSIS",
                       settings={**FAST_ON, "AI_FASTLANE_ABANDONED_SESSIONS": "true"}, tools=TwoSessions([completed()]))
    assert result.response.response_type == "LIMITATION"


CONVENTION_ON = {**FAST_ON, "AI_FASTLANE_CONVENTION_NUMBERS": "true"}
CODE = "window = 21\nlevel = 0.95\n"


def coded_flow() -> list:
    return [call("submit_data_need_spec", {"mode": "ANALYSIS", "research_governance": None}, "c1"),
            call("prepare_data_bundle", {"need_id": NEED}, "c2"),
            call("open_analysis_session", {"input_bundle_id": BUNDLE}, "c3"),
            call("run_python", {"session_id": SESSION, "code": CODE}, "c4"),
            call("complete_analysis", {"session_id": SESSION}, "c5")]


def convention_run(text, settings=CONVENTION_ON, lane=lanes.FAST):
    final = final_response(answer(text))
    return run([*coded_flow(), final, final_response(answer("Return YTD BBCA 12,35% dan BBRI turun 4,32%."))],
               lane=lane, path="ANALYSIS", settings=settings, tools=TwoSessions([completed()]))


ACCEPTED = "Return YTD BBCA 12,35% dan BBRI turun 4,32%; batas kepercayaan 95% dihitung dengan jendela 21 hari."


def test_f2_a_confidence_level_and_a_code_parameter_pass_without_a_round_and_are_labelled() -> None:
    result, scripted, _ = convention_run(ACCEPTED)
    assert result.response.response_type == "ANSWER" and result.response.answer.startswith("Return YTD BBCA")
    assert "95%" in result.response.answer and "jendela 21 hari" in result.response.answer
    assert convention_numbers_line([("95%", "CONFIDENCE_LEVEL"), ("21", "CODE_PARAMETER")]) \
        in result.response.assumptions
    assert not any("no governed source" in json.dumps(p) for p in scripted.payloads)  # no repair round


@pytest.mark.parametrize("text", [
    "Return YTD BBCA 12,35% dan BBRI turun 4,32%; BBCA naik 95% sejak awal.",           # 95% is no confidence level
    "Return YTD BBCA 12,35% dan BBRI turun 4,32%; ada 21 saham yang naik.",              # 21 is in code, no parameter
    "Return YTD BBCA 12,35% dan BBRI turun 4,32%; jendela 34 hari.",                     # a parameter not in the code
    "Return YTD BBCA 12,35% dan BBRI turun 4,32%; jendela 21 hari, dan 21 saham naik."])  # one place lacks the word
def test_f2_other_unsourced_numbers_are_still_refused(text) -> None:
    result, scripted, _ = convention_run(text)
    assert any("no governed source" in json.dumps(p) for p in scripted.payloads)
    assert not any(a.startswith("Angka berikut tidak berasal") for a in result.response.assumptions)


@pytest.mark.parametrize("settings, lane", [(FAST_ON, lanes.FAST), (CONVENTION_ON, lanes.STANDARD)])
def test_f2_without_the_switch_or_on_the_standard_lane_the_numbers_are_refused(settings, lane) -> None:
    _, scripted, _ = convention_run(ACCEPTED, settings=settings, lane=lane)
    assert any("no governed source in this run: 95%, 21" in json.dumps(p) for p in scripted.payloads)


def test_the_section_caps_note_is_sent_only_with_its_switch_on_the_fast_lane() -> None:
    from app.orchestrator import FASTLANE_SECTIONS_NOTE

    script = [*flow(), final_response(answer("Return YTD BBCA 12,35% dan BBRI turun 4,32%."))]
    note = json.dumps(FASTLANE_SECTIONS_NOTE)[1:-1]
    _, on, _ = run(script, lane=lanes.FAST, path="ANALYSIS", settings={**FAST_ON, "AI_FASTLANE_SECTION_CAPS": "true"})
    assert note in json.dumps(on.payloads[0]) and not any(ch.isdigit() for ch in FASTLANE_SECTIONS_NOTE)
    _, off, _ = run(script, lane=lanes.FAST, path="ANALYSIS")
    _, standard, _ = run(script, lane=lanes.STANDARD, path="ANALYSIS",
                         settings={**FAST_ON, "AI_FASTLANE_SECTION_CAPS": "true"})
    assert note not in json.dumps(off.payloads[0]) and note not in json.dumps(standard.payloads[0])
    assert "at most three assumptions" in FASTLANE_SECTIONS_NOTE and "one short paragraph" in FASTLANE_SECTIONS_NOTE


def test_the_legacy_provenance_refusal_names_the_derived_references_once() -> None:
    """Side finding 2026-10-14 ("ya perbaiki"): the hint was added twice to one refusal."""
    import inspect

    assert inspect.getsource(AgentOrchestrator._validation_gate).count("self._derived_hint(") == 1


# --- advice in refusals (user 2026-10-14: "OK") ----------------------------------------------------------------------

def test_the_dataneed_provenance_refusal_names_the_derived_reference() -> None:
    """EXEC-DERIVED meant the PROVENANCE refusal; the DataNeed gate (fast and standard lane) never had the hint."""
    text = "Return YTD BBCA 12,35% dan BBRI −4,32%; selisih keduanya 16,67 poin persen."
    for lane in (lanes.FAST, lanes.STANDARD):
        _, scripted, _ = run([*flow(), final_response(answer(text)), final_response(answer(text))], lane=lane,
                             path="ANALYSIS", settings={**FAST_ON, "AI_ENABLE_VALUE_REFERENCES": "true"})
        refusal = next(json.dumps(p) for p in scripted.payloads if "no governed source" in json.dumps(p))
        assert "16,67" in refusal and "equals {{diff(" in refusal and "if that is what the number means" in refusal


def test_the_units_refusal_says_what_each_value_looks_like_and_how_to_split_a_mixed_column() -> None:
    from app.orchestrator import units_advice

    cell = "out.o2.rows[uji=Bootstrap: selisih simpangan baku (pp, Q3-Q2)].estimasi"
    text = units_advice({cell: -0.01, "out.o3.content.net_pct": -6.07})
    assert f"{cell} = -0.01: a decimal, so units='FRACTION' if it is a share" in text
    assert "units='FRACTION' first, then |pp" in text
    assert "out.o3.content.net_pct = -6.07: units='PERCENT' if it is already in percent" in text
    assert text.count("no single unit fits") == 1 and "estimasi of out.o2" in text
    assert "no single unit" not in units_advice({"out.o3.content.net_pct": 0.2}) and units_advice({}) == ""


def test_every_repair_the_units_refusal_offers_passes_the_units_check() -> None:
    """M167 (go 2026-10-15): edge_b90899… was told to write |pct, which the check refuses on a column without a unit, so
    it re-ran code. Each format the refusal and its advice name is rendered on a column of undeclared unit: a format
    outside the percent formats must pass as it is; a percent format must be refused there and pass once the column's
    unit is declared, and the text must name units= wherever it offers one."""
    import re as _re

    from app.orchestrator import UNITS_INSTRUCTION, units_advice
    from app.value_refs import PERCENT_FORMATS, ReferenceSources, render

    text = UNITS_INSTRUCTION.format(references="out.o2.rows.0.range_before") + units_advice(
        {"out.o2.rows.0.range_before": 0.034, "out.o2.rows.0.spread_level": 2.74})
    offered = set(_re.findall(r"\|([a-z]+)\b", text))
    assert offered >= {"x", "dec"} and offered & set(PERCENT_FORMATS)

    def shown(fmt: str, units: dict) -> list[str]:
        refs = ReferenceSources()
        refs.add("out", "out_r", {"rows": [{"range_before": 0.034}], "units": units}, "DATA_COVERAGE_VERIFIED")
        refs.alias("out", "o2", "out_r")
        return render("{{out.o2.rows.0.range_before|" + fmt + "}}", refs).unknown_units

    for fmt in offered:
        if fmt in PERCENT_FORMATS:
            assert shown(fmt, {}) and not shown(fmt, {"range_before": "FRACTION"}), fmt
            assert not _re.search(r"(?<!then )\|" + fmt + r"\b(?![,)])", text), f"|{fmt} offered without units="
        else:
            assert not shown(fmt, {}), fmt


# --- V4: decision rules (user 2026-10-14, "save ini as V4") ---------------------------------------------------------

V4_ON = {**EXPLORE_ON, "AI_FASTLANE_DECISION_RULES": "true"}


def test_v4_the_decisions_note_and_the_answer_modes_method_rule_come_only_with_the_switch() -> None:
    from app.orchestrator import EXPLORE_ANSWER_HELPERS, EXPLORE_ANSWER_HELPERS_V4, decisions_note

    _, on = explore_run(settings=V4_ON)
    first = json.dumps(on.payloads[0])
    assert json.dumps(decisions_note())[1:-1] in first
    assert json.dumps(EXPLORE_ANSWER_HELPERS_V4)[1:-1] in first
    assert json.dumps(EXPLORE_ANSWER_HELPERS)[1:-1] not in first
    _, off = explore_run()
    assert "decide each of these once" not in json.dumps(off.payloads[0])
    assert json.dumps(EXPLORE_ANSWER_HELPERS)[1:-1] in json.dumps(off.payloads[0])


def test_v4_the_standard_lane_is_unchanged_by_the_switch() -> None:
    script = [*flow(), final_response(answer("Return YTD BBCA 12,35% dan BBRI turun 4,32%."))]
    _, on, _ = run(script, lane=lanes.STANDARD, path="ANALYSIS",
                   settings={**FAST_ON, "AI_FASTLANE_DECISION_RULES": "true"})
    _, off, _ = run(script, lane=lanes.STANDARD, path="ANALYSIS")
    assert on.payloads == off.payloads


def test_v4_the_note_takes_its_numbers_from_the_defaults_table(monkeypatch) -> None:
    """C and E are tweaked in app/fastlane_defaults.py (AGENTS.md, Fast-lane defaults); the note follows the table."""
    from app import fastlane_defaults as defaults
    from app.orchestrator import decisions_note

    text = decisions_note()
    assert "at most 5 years back" in text and "exceed 100" in text
    assert "90 percentile" in text and "21 trading days" in text
    monkeypatch.setitem(defaults.FASTLANE_DEFAULTS["large_threshold_percentile"], "value", 80)
    monkeypatch.setitem(defaults.FASTLANE_DEFAULTS["feasibility_entity_years"], "value", 250)
    changed = decisions_note()
    assert "80 percentile" in changed and "exceed 250" in changed
    assert all({"value", "unit", "means"} <= set(entry) for entry in defaults.FASTLANE_DEFAULTS.values())
    # O5 item 2 (EXEC-IMPL-1016): the readings of open words come from the same table, and a changed one reaches it
    assert "the net value (buy minus sell)" in text and "(implementation close)" in text
    assert "Send the data need as soon as its scope is clear" in text
    monkeypatch.setitem(defaults.FASTLANE_DEFAULTS["largest_buying_measure"], "value", "gross")
    assert "buy minus sell); the gross buy is shown beside it (gross)" in decisions_note()


def test_v4_1_the_exploratory_sentence_follows_the_explore_mode_and_spans_count_trading_days() -> None:
    """V4.1 (user 2026-10-14): Mode Jawab is not told "without a formal test"; a relative span is rolling trading days
    from the last date ("5 hari bursa terakhir", "semua hari bursa")."""
    from app.orchestrator import (FASTLANE_EXPLORATORY, FASTLANE_EXPLORATORY_ANSWER, FASTLANE_EXPLORATORY_INSIGHT,
                                  decisions_note)

    _, on = explore_run(settings=V4_ON)
    first = json.dumps(on.payloads[0])
    assert json.dumps(FASTLANE_EXPLORATORY_ANSWER)[1:-1] in first
    assert json.dumps(FASTLANE_EXPLORATORY)[1:-1] not in first
    _, insight = explore_run(settings=V4_ON, mode=lanes.INSIGHT)
    assert json.dumps(FASTLANE_EXPLORATORY_INSIGHT)[1:-1] in json.dumps(insight.payloads[0])
    _, off = explore_run()
    assert json.dumps(FASTLANE_EXPLORATORY)[1:-1] in json.dumps(off.payloads[0])
    text = decisions_note()
    assert "1 minggu = 5 trading days" in text and "1 bulan = 21 trading days" in text
    assert "1 tahun = 252 trading days" in text and "saniti.period_return" in text


# --- V5 (user 2026-10-14: gates advise, no Batasan in an answer, pp as %, category values, scope example) ----------

ADVICE_ON = {**FAST_ON, "AI_FASTLANE_GATE_ADVICE": "true"}
V5_ON = {**FAST_ON, "AI_FASTLANE_V5_PRESENTATION": "true", "AI_FASTLANE_SECTION_CAPS": "true"}


def advice_orchestrator(**settings):
    import httpx

    from app.tools.analysis import SandboxClient
    from app.tools.request_data import GovernorClient
    from test_analysis_tools import SANDBOX_KEY
    from test_artifacts import FakeSandbox
    from test_g23_desk import governor_handler

    client = SandboxClient("http://sandbox.test", SANDBOX_KEY, 10, 0, transport=httpx.MockTransport(FakeSandbox().handler))
    governor = GovernorClient("http://governor.test", "g" * 40, 10, transport=httpx.MockTransport(governor_handler))
    registry = build_default_registry(sandbox_client=client, governor_client=governor, dataneed_enabled=True)
    return AgentOrchestrator(make_settings(**{"AI_ENABLE_DATANEED": "true", "AI_ENABLE_VALUE_REFERENCES": "true",
                                              **settings}), ScriptedClient([]), registry)


@pytest.mark.parametrize("lane, settings, advised", [(lanes.FAST, ADVICE_ON, True), (lanes.FAST, FAST_ON, False),
                                                      (lanes.STANDARD, ADVICE_ON, False)])
def test_v5_typed_figures_are_labelled_at_once_only_on_the_fast_lane_with_the_switch(lane, settings, advised) -> None:
    from app.orchestrator import GateRejection, TYPED_FIGURES_LINE
    from test_g23_desk import DESKS, FIGURES, state_with

    orc = advice_orchestrator(**settings)
    state = state_with(frozenset(DESKS["analysis"]))
    state.lane = lane
    if advised:
        out = orc._evidence_gate(state, FIGURES, ["DATA_COVERAGE_VERIFIED"])
        assert TYPED_FIGURES_LINE.format(numbers="116, 132") in out.limitations
        assert "TYPED_FIGURES" not in state.gate_kinds_rejected
    else:
        with pytest.raises(GateRejection):
            orc._evidence_gate(state, FIGURES, ["DATA_COVERAGE_VERIFIED"])


@pytest.mark.parametrize("lane, settings, kept", [(lanes.FAST, ADVICE_ON, True), (lanes.STANDARD, ADVICE_ON, False)])
def test_v5_methodology_numbers_pass_in_advice_mode(lane, settings, kept) -> None:
    from app.orchestrator import GateRejection
    from app.schemas import FinalResponse
    from test_g23_desk import state_with

    orc = advice_orchestrator(AI_ENABLE_METHODOLOGY="true", **settings)
    state = state_with(frozenset({"run_python"}))
    state.lane = lane
    state.completions["cmp_1"] = {"status": "COMPLETED"}
    final = FinalResponse(response_type="ANSWER", answer="RB beli bersih 116 dari 132 hari.",
                          clarification_question=None, assumptions=[], limitations=[],
                          methodology="Ambang persentil 87 dari jendela 63 hari.")
    if kept:
        assert orc._methodology_gate(state, final).methodology == "Ambang persentil 87 dari jendela 63 hari."
    else:
        with pytest.raises(GateRejection):
            orc._methodology_gate(state, final)


def test_v5_provenance_accepts_a_code_literal_anywhere_and_labels_it() -> None:
    result, scripted, _ = convention_run("Return YTD BBCA 12,35% dan BBRI turun 4,32%; ada 21 saham yang naik.",
                                         settings=ADVICE_ON)
    assert result.response.answer.endswith("ada 21 saham yang naik.")
    assert convention_numbers_line([("21", "CODE_PARAMETER")]) in result.response.assumptions
    assert not any("no governed source" in json.dumps(p) for p in scripted.payloads)


def test_v5_a_number_matching_nothing_is_asked_once_and_the_refusal_names_its_sentence() -> None:
    _, scripted, _ = convention_run("Return YTD BBCA 12,35% dan BBRI turun 4,32%; jendela 34 hari.",
                                    settings=ADVICE_ON)
    refusal = next(json.dumps(p) for p in scripted.payloads if "no governed source" in json.dumps(p))
    assert "Written in:" in refusal and "jendela 34 hari" in refusal
    _, standard, _ = convention_run("Return YTD BBCA 12,35% dan BBRI turun 4,32%; jendela 34 hari.",
                                    settings=ADVICE_ON, lane=lanes.STANDARD)
    assert "Written in:" not in json.dumps(standard.payloads)


LIMITED = "Data harga hanya sampai Agustus 2026."


@pytest.mark.parametrize("lane, settings, kind, folded", [
    (lanes.FAST, V5_ON, "ANSWER", True), (lanes.FAST, FAST_ON, "ANSWER", False),
    (lanes.STANDARD, V5_ON, "ANSWER", False), (lanes.FAST, V5_ON, "LIMITATION", False)])
def test_v5_a_fast_lane_answer_shows_no_limitations_and_keeps_its_caveats_in_the_assumptions(lane, settings, kind,
                                                                                               folded) -> None:
    final = final_response(answer("Return YTD BBCA 12,35% dan BBRI turun 4,32%.", kind=kind, limitations=[LIMITED]))
    result, _, _ = run([*flow(), final, final], lane=lane, path="ANALYSIS", settings=settings)
    response = result.response
    assert response.response_type == kind
    if folded:
        assert response.limitations == [] and LIMITED in response.assumptions
        assert ANALYSIS_PATH_LINE not in response.assumptions  # the analysis-path line is dropped, not moved
    else:
        assert LIMITED in response.limitations


def test_v5_the_presentation_note_comes_only_with_its_switch_on_the_fast_lane() -> None:
    from app.orchestrator import FASTLANE_PRESENTATION_NOTE, FASTLANE_SECTIONS_NOTE, SECTIONS_LIMITATIONS_CAP

    script = [*flow(), final_response(answer("Return YTD BBCA 12,35% dan BBRI turun 4,32%."))]
    note = json.dumps(FASTLANE_PRESENTATION_NOTE)[1:-1]
    _, on, _ = run(script, lane=lanes.FAST, path="ANALYSIS", settings=V5_ON)
    first = json.dumps(on.payloads[0])
    assert note in first and json.dumps(FASTLANE_SECTIONS_NOTE)[1:-1] not in first
    assert "at most three assumptions, each" in first and SECTIONS_LIMITATIONS_CAP in FASTLANE_SECTIONS_NOTE
    _, off, _ = run(script, lane=lanes.FAST, path="ANALYSIS")
    _, standard_on, _ = run(script, lane=lanes.STANDARD, path="ANALYSIS", settings=V5_ON)
    _, standard_off, _ = run(script, lane=lanes.STANDARD, path="ANALYSIS")
    assert note not in json.dumps(off.payloads[0]) and standard_on.payloads == standard_off.payloads


def test_v5_pp_is_shown_as_percent_only_while_the_run_sets_it() -> None:
    from app.value_refs import format_value, pp_as_percent

    assert format_value(1.5, "pp") == "1,50 pp" and format_value(0.015, "pp", unit="FRACTION") == "1,50 pp"
    token = pp_as_percent.set(True)
    try:
        assert format_value(1.5, "pp") == "1,50%" and format_value(0.015, "pp", unit="FRACTION") == "1,50%"
        assert format_value(0.123, "pct") == "12,30%"
    finally:
        pp_as_percent.reset(token)


def test_v5_the_run_sets_pp_as_percent_and_catalog_values_on_the_fast_lane_only() -> None:
    from app.tools.catalog import catalog_values_shown
    from app.value_refs import pp_as_percent

    seen = []

    class Watching(Counting):
        def registry(self):
            import dataclasses

            registry = super().registry()
            spec = registry.get("submit_data_need_spec")
            handler = spec.handler
            registry._tools[spec.name] = dataclasses.replace(spec, handler=lambda a: (
                seen.append((pp_as_percent.get(), catalog_values_shown.get())), handler(a))[1])
            return registry

    script = [*flow(), final_response(answer("Return YTD BBCA 12,35% dan BBRI turun 4,32%."))]
    settings = {**V5_ON, "AI_FASTLANE_DECISION_RULES": "true"}
    run(script, lane=lanes.FAST, path="ANALYSIS", settings=settings, tools=Watching([completed()]))
    run(script, lane=lanes.STANDARD, path="ANALYSIS", settings=settings, tools=Watching([completed()]))
    assert seen == [(True, True), (False, False)]
    assert pp_as_percent.get() is False and catalog_values_shown.get() is False


def test_v5_the_decisions_note_names_category_values_and_a_valid_and_scope() -> None:
    import re

    from app.orchestrator import decisions_note
    from app.tools.data_need import ScopeNode

    text = decisions_note()
    assert "column_values" in text and "never call get_dimension_values on a dated table" in text
    example = json.loads(re.search(r"e\.g\. (\{.*\}); a NOT", text).group(1))
    node = ScopeNode.model_validate(example)
    assert node.type == "AND" and len(node.children) == 2 and node.child is None


def test_v5_option_2_typed_figures_resolve_by_the_row_named_or_count_as_code_parameters() -> None:
    """User 2026-10-15 ("2 alright"): in advice mode a figure equal to several released values takes the one whose row
    its sentence names; a literal of the run's code is a parameter; only the rest keeps the typed-figures label."""
    from app.orchestrator import TYPED_FIGURES_LINE
    from test_g23_desk import FIGURES as FIGURES_RB
    from test_g23_desk import released_state

    rows = [{"broker": "RB", "net_days": 116.0, "days": 132.0}, {"broker": "YP", "net_days": 116.0, "days": 140.0}]
    orc = advice_orchestrator(**ADVICE_ON)
    state = released_state(rows, "RB beli bersih 116 dari 132 hari.")
    state.lane = lanes.FAST
    out = orc._evidence_gate(state, FIGURES_RB, ["DATA_COVERAGE_VERIFIED"])
    assert "out.o3.rows[broker=RB].net_days" in state.referenced and not state.gate_kinds_rejected
    assert not any(line.startswith("Angka berikut diketik") for line in out.limitations)
    unnamed = released_state(rows, "Ada broker yang beli bersih 116 dari 132 hari.")
    unnamed.lane = lanes.FAST
    labelled = orc._evidence_gate(unnamed, FIGURES_RB.model_copy(update={
        "answer": "Ada broker yang beli bersih 116 dari 132 hari."}), ["DATA_COVERAGE_VERIFIED"])
    assert TYPED_FIGURES_LINE.format(numbers="116") in labelled.limitations  # no row named: still labelled
    coded = released_state(rows, "Ada broker yang beli bersih 116 dari 132 hari.")
    coded.lane, coded.code_numbers = lanes.FAST, [116.0]
    out = orc._evidence_gate(coded, FIGURES_RB, ["DATA_COVERAGE_VERIFIED"])
    assert convention_numbers_line([("116", "CODE_PARAMETER")]) in out.limitations
    assert not any(line.startswith("Angka berikut diketik") for line in out.limitations)


# --- O3 (EXEC-IMPL-1016 Fase 2): one brief per turn --------------------------------------------------------------------

def test_a_turns_notes_reach_the_model_as_one_brief_and_a_read_turn_gets_no_data_work_note() -> None:
    """edge_2f7523a7 read 7-8 separate application notes, some pulling different ways, and a CLARIFY turn on the fast
    lane was told to send a data need while its tools could only read. The notes now come as one brief that says the
    later part applies; a read-only turn drops the notes about data work."""
    from app.orchestrator import TURN_BRIEF_HEADER, AgentOrchestrator, RunState

    def brief(kind: str | None) -> tuple[list[dict], RunState]:
        state = RunState(request_id="b", started=0.0, input_items=[{"role": "user", "content": "m"}])
        state.turn_notes = [("lane note: send one data need", True), ("presentation note", False),
                            ("explore note", True), ("class note", False)]
        if kind:
            state.plan_meta["turn_kind"] = kind
        AgentOrchestrator._insert_turn_brief(state)
        return state.input_items, state

    items, _ = brief("INSIGHT")
    assert len(items) == 2 and items[0]["content"].startswith(TURN_BRIEF_HEADER) and items[1]["content"] == "m"
    assert [line for line in items[0]["content"].splitlines()[1:]] == [
        "- lane note: send one data need", "- presentation note", "- explore note", "- class note"]
    items, _ = brief("CLARIFY")
    assert "data need" not in items[0]["content"] and "explore" not in items[0]["content"]
    assert "presentation note" in items[0]["content"] and "class note" in items[0]["content"]
    empty = RunState(request_id="b", started=0.0, input_items=[{"role": "user", "content": "m"}])
    AgentOrchestrator._insert_turn_brief(empty)
    assert empty.input_items == [{"role": "user", "content": "m"}]


def test_the_insight_note_tests_patterns_and_answers_a_search_with_a_table() -> None:
    """EXEC-M163 item 2 / O3: the insight mode tests why and patterns; a request to find, list or rank is a table."""
    from app.orchestrator import explore_note

    note = explore_note(lanes.INSIGHT)
    assert "When the user asks why" in note and "answer with that table and run no tests" in note
