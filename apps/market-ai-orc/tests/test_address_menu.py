"""Plan 2026-10-05 item 10 (golden test ma-qa-20261005b, user decision): every result that holds values lists their
full value references (10.1), check_references renders addresses before the answer (10.2), a repeated wrong reference
is replaced everywhere by an edit (10.3), a field a hypothesis finding lacks is read from its research summary (10.4),
a lookup_reference read has a citable matched count (10.5d), and a plan threshold may be a cited earlier result when
the router read the message as building on it (10.6)."""
from __future__ import annotations

import json

import pytest

from app import edit_repair
from app.orchestrator import AgentOrchestrator, RunState
from app.tools import ToolOutcome, build_default_registry
from app.tools.references import check
from app.value_refs import ReferenceSources, TableRows, menu_address, render

UNITS = {"angle_a.difference": "PERCENT", "mean": "PERCENT", "median": "PERCENT", "angle_b.difference": "FRACTION"}


def hypothesis_finding() -> dict:
    """The backend's finding (app/research_findings.py): groups without a median."""
    return {"hypothesis_id": "bank_up5", "verdict": "INCONCLUSIVE", "confidence_level": 0.95,
            "angle_a": {"difference": 2.23, "ci_low": -0.5, "ci_high": 4.96, "p_value": 0.11},
            "angle_b": {"difference": -0.0103},
            "groups": {"CONDITION": {"rows": 4017, "mean": 2.73}, "BASELINE": {"rows": 86057, "mean": 0.5}},
            "sample": {"effective": 202}, "units": UNITS, "hashes": {"plan": "abc"}}


def summary_output() -> dict:
    """The released research_summary_<id> (saniti_session.event_summary): the same groups with their median."""
    return {"output_id": "out_sum", "name": "research_summary_bank_up5", "type": "JSON",
            "content": {"groups": {"CONDITION": {"rows": 4017, "mean": 2.73, "median": -2.4},
                                   "BASELINE": {"rows": 86057, "mean": 0.5, "median": 0.0}}},
            "units": {"median": "PERCENT", "mean": "PERCENT"}}


def orchestrator(menu: bool = True) -> AgentOrchestrator:
    orc = AgentOrchestrator.__new__(AgentOrchestrator)
    orc.row_reader = None
    orc.registry = build_default_registry()
    orc.address_menu = menu
    return orc


def track(orc, state, name, result, arguments=None) -> dict:
    orc._track_references(state, name, ToolOutcome(call_id="c", name=name, ok=True, output={"result": result}),
                          arguments)
    return result


def completed_hypothesis(state: RunState, orc: AgentOrchestrator) -> dict:
    return track(orc, state, "complete_analysis", {
        "status": "COMPLETED", "session_id": "sess_1", "released_contents": [summary_output()],
        "final_status": {"research_findings": [hypothesis_finding()]}})


def state() -> RunState:
    return RunState(request_id="r", started=0.0, input_items=[])


# 10.1 --------------------------------------------------------------------------------------------------------------

def test_menu_lists_full_addresses_with_values_and_units() -> None:
    sources = ReferenceSources()
    sources.add("finding", "bank_up5", hypothesis_finding(), "DATA_COVERAGE_VERIFIED")
    menu = sources.menu("finding.bank_up5")
    assert "angle_a difference: 2,23 [PERCENT] → {{finding.bank_up5.angle_a.difference}}" in menu
    assert "CONDITION mean: 2,73 [PERCENT] → {{finding.bank_up5.groups.CONDITION.mean}}" in menu
    assert "confidence_level: 0,95 → {{finding.bank_up5.confidence_level}}" in menu
    assert not any(".hashes" in line or ".units" in line for line in menu)


def test_menu_shows_nested_json_content_of_an_output() -> None:
    orc, run = orchestrator(), state()
    result = completed_hypothesis(run, orc)
    # the user's example (2026-10-05): "median: −2,40 → {{out.o2.content.groups.CONDITION.median}}"
    assert "CONDITION median: −2,40 [PERCENT] → {{out.o1.content.groups.CONDITION.median}}" in result["addresses"]
    assert any("{{finding.bank_up5.angle_a.ci_low}}" in line for line in result["addresses"])
    assert result["addresses_note"].startswith("Each line is \"name: value as shown")


def test_menu_lists_every_row_of_a_keyed_table_after_its_pattern() -> None:
    sources = ReferenceSources()
    table = TableRows(2)
    table.add(0, [{"broker": "XL", "net_bn": 6.75}, {"broker": "SQ", "net_bn": 1.2}])
    sources.add("out", "out_rank", {"name": "ranking", "rows": table}, "DATA_COVERAGE_VERIFIED")
    assert sources.menu("out.out_rank") == [
        "pattern: {{out.out_rank.rows[broker=<broker>].<column>}}, numeric columns: net_bn",
        "XL net_bn: 6,75 → {{out.out_rank.rows[broker=XL].net_bn}}",
        "SQ net_bn: 1,20 → {{out.out_rank.rows[broker=SQ].net_bn}}"]
    assert render("{{out.out_rank.rows[broker=SQ].net_bn|dec}}", sources).text == "1,20"


def test_a_long_table_lists_its_first_rows_and_names_the_others_for_the_pattern() -> None:
    sources = ReferenceSources()
    table = TableRows(100)
    table.add(0, [{"ticker": f"T{i:03d}", "ret": i / 10} for i in range(40)])
    sources.add("out", "big_table", {"rows": table}, "DATA_COVERAGE_VERIFIED")
    menu = sources.menu("out.big_table")
    assert menu[0] == ("pattern: {{out.big_table.rows[ticker=<ticker>].<column>}}, numeric columns: ret "
                       "(30 of 100 rows listed below; the others use the same pattern)")
    assert menu[1].startswith("other ticker values: T030, T031") and menu[1].endswith("…")
    assert len([line for line in menu if menu_address(line)]) == 30
    assert "T029 ret: 2,90 → {{out.big_table.rows[ticker=T029].ret}}" in menu


def test_a_table_without_an_identifying_column_is_listed_by_position() -> None:
    sources = ReferenceSources()
    table = TableRows(2)
    table.add(0, [{"x": 1.5}, {"x": 2.5}])
    sources.add("out", "plain", {"rows": table}, "DATA_COVERAGE_VERIFIED")
    menu = sources.menu("out.plain")
    assert menu[0] == "pattern: {{out.plain.rows.<baris>.<column>}}, numeric columns: x"
    assert "row 1 x: 2,50 → {{out.plain.rows.1.x}}" in menu
    assert render("{{out.plain.rows.1.x|dec}}", sources).text == "2,50"


def test_menu_is_bounded() -> None:
    sources = ReferenceSources()
    sources.add("out", "big", {"content": {f"v{i}": float(i) for i in range(100)}}, "DATA_COVERAGE_VERIFIED")
    assert len(sources.menu("out.big", limit=10)) == 10


def test_no_menu_when_the_switch_is_off() -> None:
    orc, run = orchestrator(menu=False), state()
    assert "addresses" not in completed_hypothesis(run, orc)


# 10.4 --------------------------------------------------------------------------------------------------------------

def test_a_field_the_finding_lacks_is_read_from_its_research_summary() -> None:
    orc, run = orchestrator(), state()
    completed_hypothesis(run, orc)
    out = render("median {{finding.bank_up5.groups.CONDITION.median|pp:2}}", run.ref_sources)
    assert out.problems == [] and out.missing == []
    assert out.text == "median −2,40 pp"
    assert run.ref_sources.redirected == {
        "finding.bank_up5.groups.CONDITION.median": "out.o1.content.groups.CONDITION.median"}


def test_without_a_summary_the_missing_field_is_still_marked() -> None:
    sources = ReferenceSources()
    sources.add("finding", "bank_up5", hypothesis_finding(), "DATA_COVERAGE_VERIFIED")
    out = render("{{finding.bank_up5.groups.CONDITION.median|pp:2}}", sources)
    assert out.text == "[median]" and out.missing


def test_two_summaries_for_one_hypothesis_give_no_fallback() -> None:
    orc, run = orchestrator(), state()
    second = summary_output() | {"output_id": "out_sum2"}
    track(orc, run, "complete_analysis", {
        "status": "COMPLETED", "session_id": "sess_1", "released_contents": [summary_output(), second],
        "final_status": {"research_findings": [hypothesis_finding()]}})
    assert ("finding", "bank_up5") not in run.ref_sources.fallbacks


# 10.2 --------------------------------------------------------------------------------------------------------------

def test_check_references_shows_values_errors_and_where_a_value_was_read() -> None:
    orc, run = orchestrator(), state()
    completed_hypothesis(run, orc)
    result = check(["finding.bank_up5.angle_a.difference|pp:2", "{{finding.bank_up5.groups.CONDITION.median|pp:2}}",
                    "finding.bank_up5.angle_c.difference"], run.ref_sources)
    first, second, third = result["results"]
    assert first == {"reference": "finding.bank_up5.angle_a.difference|pp:2", "ok": True, "shows": "2,23 pp"}
    assert second["ok"] and second["read_from"] == "out.o1.content.groups.CONDITION.median"
    assert not third["ok"] and "angle_c" in third["error"]


def test_check_references_without_results() -> None:
    assert check(["finding.x.y"], None)["status"] == "NO_REFERENCES"


def test_check_references_is_registered_as_a_read_only_tool() -> None:
    registry = build_default_registry(reference_check=True)
    assert registry.get("check_references") is not None
    assert "check_references" in registry.names_with_effect()


# 10.5d -------------------------------------------------------------------------------------------------------------

def test_a_reference_read_has_a_citable_matched_count() -> None:
    orc, run = orchestrator(), state()
    result = track(orc, run, "lookup_reference", {
        "status": "ROWS_READY", "table": "IDX_Stock_Universe", "matched": 48, "truncated": False,
        "rows": [{"Ticker": "BBRI", "Sector": "Banks"}]})
    assert result["ref"] == "reference.r1"
    assert result["addresses"] == ["matched: 48 → {{reference.r1.matched}}"]
    assert render("{{reference.r1.matched|int}} bank", run.ref_sources).text == "48 bank"


# 10.3 --------------------------------------------------------------------------------------------------------------

def draft() -> dict:
    return {"response_type": "ANSWER", "answer": "IK 95% a; IK 95% b; {{finding.x.median|pp:2}} and "
                                                 "{{finding.x.median|pp:2}}", "assumptions": [], "limitations": []}


def test_all_replaces_every_occurrence_of_a_whole_reference() -> None:
    merged, _ = edit_repair.apply(draft(), {"edits": [{"find": "{{finding.x.median|pp:2}}",
                                                       "replace": "{{out.o2.content.median|pp:2}}", "all": True}]},
                                  {"response_type", "answer", "assumptions", "limitations"})
    assert json.loads(merged)["answer"].count("{{out.o2.content.median|pp:2}}") == 2


def test_count_replaces_repeated_text_when_it_matches() -> None:
    merged, _ = edit_repair.apply(draft(), {"edits": [{"find": "IK 95% ", "replace": "IK ", "count": 2}]},
                                  {"answer"})
    assert "95%" not in json.loads(merged)["answer"]


def test_all_replaces_every_occurrence_of_plain_text_too() -> None:
    """EXEC-R R4c (2026-10-06): "all" on text that is not a reference was refused and the answer rewritten in full."""
    merged, _ = edit_repair.apply(draft(), {"edits": [{"find": "IK 95% ", "replace": "IK ", "all": True}]},
                                  {"answer"})
    assert "IK 95% " not in json.loads(merged)["answer"]


def test_a_wrong_count_is_refused() -> None:
    with pytest.raises(edit_repair.EditNotApplied, match="not 3"):
        edit_repair.apply(draft(), {"edits": [{"find": "IK 95% ", "replace": "IK ", "count": 3}]}, {"answer"})


def test_without_all_or_count_a_repeated_find_is_still_refused() -> None:
    with pytest.raises(edit_repair.EditNotApplied, match="not once"):
        edit_repair.apply(draft(), {"edits": [{"find": "IK 95% ", "replace": "IK "}]}, {"answer"})


def test_the_refusal_suggests_addresses_with_the_same_field() -> None:
    orc, run = orchestrator(), state()
    run.ref_sources.add("out", "out_sum", summary_output(), "DATA_COVERAGE_VERIFIED")
    run.ref_sources.alias("out", "o2", "out_sum")
    hint = AgentOrchestrator._reference_suggestions(run, ["finding.bank_up5.groups.CONDITION.median|pp:2"])
    assert "out.o2.content.groups.CONDITION.median" in hint


# 10.6 --------------------------------------------------------------------------------------------------------------

def _threshold_plan(value: float):
    from test_mode4_user_rules import _plan
    return _plan(10, success_rule={"operator": ">=", "value": value, "unit": "PERCENT"})


def _gate_state(orchestrator, cited: float | None):
    from app.value_refs import Resolved
    from test_research_findings import state as findings_state
    s = findings_state(orchestrator)
    s.user_text = "Uji apakah naik dalam 10 hari berikutnya, pakai angka hasil analisa kamu barusan sebagai ambang."
    if cited is not None:
        s.ref_values.append(Resolved(cited, "DATA_COVERAGE_VERIFIED", "PERCENT"))
    return s


def test_a_threshold_cited_from_an_earlier_result_passes_when_the_router_read_the_reference() -> None:
    from app.user_words import current_turn_referent
    from test_research_findings import agent
    orchestrator = agent()
    orchestrator.audit_outbox = None
    token = current_turn_referent.set("NEWEST_RESULT")
    try:
        final = orchestrator._plan_gate(_gate_state(orchestrator, 2.4), _threshold_plan(2.4))
    finally:
        current_turn_referent.reset(token)
    assert final.research_plan.experiments[0].success_rule.value == 2.4


def test_without_the_routers_reading_the_cited_value_is_not_a_users_threshold() -> None:
    from app.orchestrator import GateRejection
    from test_research_findings import agent
    orchestrator = agent()
    orchestrator.audit_outbox = None
    with pytest.raises(GateRejection, match="success_rule value 2.4"):
        orchestrator._plan_gate(_gate_state(orchestrator, 2.4), _threshold_plan(2.4))


def test_a_threshold_the_plan_does_not_cite_is_refused_with_the_hint() -> None:
    from app.orchestrator import GateRejection
    from app.user_words import current_turn_referent
    from test_research_findings import agent
    orchestrator = agent()
    orchestrator.audit_outbox = None
    token = current_turn_referent.set("NEWEST_RESULT")
    try:
        with pytest.raises(GateRejection, match="refers to an earlier result"):
            orchestrator._plan_gate(_gate_state(orchestrator, None), _threshold_plan(2.4))
    finally:
        current_turn_referent.reset(token)


def test_a_plan_citing_an_earlier_result_by_reference_passes_end_to_end() -> None:
    """Golden test ma-qa-20261006b threshold_from_result turn 2: the plan cited the earlier result, but references
    were rendered only for answers, so the value never reached the plan gate."""
    from app.user_words import current_turn_referent
    from test_research_findings import agent
    orchestrator = agent()
    orchestrator.audit_outbox = None
    orchestrator.value_references = True
    run = _gate_state(orchestrator, None)
    run.ref_sources.add("out", "out_mean", {"name": "mean_return", "content": {"mean": 2.4}}, "DATA_COVERAGE_VERIFIED",
                        units={"content.mean": "PERCENT"})
    run.ref_sources.alias("out", "o1", "out_mean")
    plan = _threshold_plan(2.4)
    plan = plan.model_copy(update={"answer": "Ambang dari hasil sebelumnya: {{out.o1.content.mean|pctv}}."})
    token = current_turn_referent.set("NEWEST_RESULT")
    try:
        rendered, _ = orchestrator._resolve_references(run, plan)
        final = orchestrator._plan_gate(run, rendered)
    finally:
        current_turn_referent.reset(token)
    assert "2,40%" in rendered.answer and final.research_plan.experiments[0].success_rule.value == 2.4


def test_a_cited_value_matches_as_the_plan_writes_it() -> None:
    from app.orchestrator import cited_match
    # re-test ma-qa-20261006c turn 2: the cited difference was −0,705… pp and the plan's minimum effect 0.705
    assert cited_match(0.705, [-0.70524], magnitude=True)
    assert cited_match(0.71, [-0.70524], magnitude=True)
    assert not cited_match(0.705, [-0.70524], magnitude=False)  # a success threshold keeps its sign
    assert cited_match(-0.71, [-0.70524], magnitude=False)
    assert cited_match(70.5, [-0.70524], magnitude=True)  # the percent scale, as for the user's own numbers
    assert not cited_match(0.8, [-0.70524], magnitude=True)


def test_a_minimum_effect_cited_from_a_negative_difference_passes_the_gate() -> None:
    from app.user_words import current_turn_referent
    from test_mode4_user_rules import _plan
    from test_research_findings import agent
    orchestrator = agent()
    orchestrator.audit_outbox = None
    token = current_turn_referent.set("NEWEST_RESULT")
    try:
        final = orchestrator._plan_gate(_gate_state(orchestrator, -0.70524),
                                        _plan(10, min_effect=0.705, min_effect_unit="PERCENT"))
    finally:
        current_turn_referent.reset(token)
    assert final.research_plan.experiments[0].min_effect == 0.705
