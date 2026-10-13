"""EXEC-DAYS (user 2026-10-13, "Ok, coba perbaiki ya"): the trading days of a prepared data request's range are a
referable count ({{data.<request>.<range>.dates}}), so "19 hari bursa" is cited by what it means instead of one
stock's day count. Solution 2 (EXEC-M143, "also enable solusi 2"): check_references with a draft lists what the
answer checks would refuse, without effect on the run."""
from __future__ import annotations

from app.orchestrator import AgentOrchestrator, RunState
from app.tools import ToolOutcome
from app.tools.references import CheckReferencesArguments, check
from app.tools.request_data import current_draft_checker
from app.value_refs import render
from conftest import ScriptedClient, make_settings
from test_multi_angle import Clock, RunSandbox, ma_registry
from test_value_references import REFS

BUNDLE = {"status": "READY", "input_bundle_id": "bundle_1", "datasets": [
    {"data_request_id": "flows", "ranges": [{"range_id": "august", "rows": 15200, "dates": 19, "entities": 800}]},
    {"data_request_id": "prices", "ranges": [{"range_id": "august", "rows": 16000, "dates": 19, "entities": 840},
                                             {"range_id": "old", "rows": 10}]}]}
DAYS = [{"ticker": f"T{i}", "value_days": 19, "net": float(i)} for i in range(3)]


def orchestrator() -> AgentOrchestrator:
    return AgentOrchestrator(make_settings(**REFS), ScriptedClient([]), ma_registry(RunSandbox()), wall_clock=Clock(),
                             draft_reader=lambda draft_id: None)


def tracked() -> tuple[AgentOrchestrator, RunState]:
    orc, state = orchestrator(), RunState(request_id="r", started=0.0, input_items=[])
    result = {k: v for k, v in BUNDLE.items()}
    orc._track_references(state, "prepare_data_bundle",
                          ToolOutcome(call_id="c", name="prepare_data_bundle", ok=True, output={"result": result}))
    orc._track_references(state, "complete_analysis", ToolOutcome(
        call_id="d", name="complete_analysis", ok=True, output={"result": {"status": "COMPLETED", "released_contents": [
            {"output_id": "out_1", "name": "days", "type": "TABLE", "rows": [dict(r) for r in DAYS]}]}}))
    # as the completion tracker does live: a released output's values are provenance sources of the run
    state.analysis_values["completion:c"] = {"label": "DATA_COVERAGE_VERIFIED",
                                             "values": [v for r in DAYS for v in (r["value_days"], r["net"])]}
    return orc, state


def test_a_ranges_trading_days_are_referable_and_listed() -> None:
    _, state = tracked()
    out = render("Agustus 2026 ({{data.flows.august.dates|int}} hari bursa)", state.ref_sources)
    assert out.text == "Agustus 2026 (19 hari bursa)" and out.problems == []
    assert out.values[0].label == "DATA_COVERAGE_VERIFIED"
    assert "{{data.prices.august.dates}}" in "".join(state.ref_sources.menu("data.prices"))
    assert "old" not in state.ref_sources.objects["data"]["prices"]  # a range without a date count is not listed


def test_a_typed_day_count_lists_the_data_address_among_its_candidates() -> None:
    orc, state = tracked()
    report = orc._check_draft(state, "Periode Agustus 2026 (19 hari bursa), {{out.o1.rows[ticker=T1].net|int}}.")
    assert report["status"] == "WOULD_BE_REFUSED"
    figure = report["typed_figures"][0]
    assert figure["figure"].startswith("19") and "data.flows.august.dates" in figure["addresses"]
    assert state.referenced == []  # nothing is cited by a draft check


def test_a_draft_check_reports_unsourced_numbers_and_changes_nothing() -> None:
    orc, state = tracked()
    report = orc._check_draft(state, "Nominal Rp 100 miliar di saham besar, {{data.flows.august.dates|int}} hari.")
    assert report["numbers_without_source"] and "100" in report["numbers_without_source"][0]
    clean = orc._check_draft(state, "Periode {{data.flows.august.dates|int}} hari bursa.")
    assert clean["status"] == "OK" and not clean["typed_figures"] and not clean["numbers_without_source"]
    assert state.ref_values == []  # the run's sources are untouched


def test_check_references_passes_a_draft_to_the_run_checker() -> None:
    orc, state = tracked()
    token = current_draft_checker.set(lambda text: orc._check_draft(state, text))
    try:
        result = check([], state.ref_sources, "Periode 19 hari bursa.")
        assert result["draft"]["status"] == "WOULD_BE_REFUSED"
    finally:
        current_draft_checker.reset(token)
    assert check([], state.ref_sources, "x")["draft"] == {"status": "UNAVAILABLE"}
    assert CheckReferencesArguments(references=["data.flows.august.dates"], draft=None).draft is None
    try:
        CheckReferencesArguments(references=[], draft=None)
    except ValueError:
        pass
    else:
        raise AssertionError("an empty check must be refused")
