"""M44 and P14 (ANSWER_INTEGRITY_FIX_PLAN.md, 2026-10-01): references resolve against the complete released table,
never the last page read, keyed tables are referenced by their key, and every JSON value has a display."""
from __future__ import annotations

from app.orchestrator import AgentOrchestrator, RunState
from app.tools import ToolOutcome, build_default_registry
from app.value_refs import ReferenceSources, TableRows, render


def tracker(row_reader=None) -> AgentOrchestrator:
    orc = AgentOrchestrator.__new__(AgentOrchestrator)
    orc.row_reader = row_reader
    orc.registry = build_default_registry()
    return orc


def broker_table(n: int = 68) -> list[dict]:
    """A ranking like crash_broker_ranking: one row per broker, XL first."""
    codes = ["XL", "SQ"] + [f"B{i:02d}" for i in range(2, n)]
    return [{"broker": code, "crash_net_bn": float(n - i), "times_largest_net_buyer": n - i}
            for i, code in enumerate(codes)]


def reader(tables: dict[str, list[dict]], calls: list | None = None):
    def read(session_id, output_id, request_id, offset, limit):
        if calls is not None:
            calls.append((output_id, offset, limit))
        rows = tables[output_id]
        return {"released": True, "rows": [dict(r) for r in rows[offset:offset + limit]], "row_count": len(rows)}
    return read


def track(orc, state, name, result, arguments=None):
    orc._track_references(state, name, ToolOutcome(call_id="c", name=name, ok=True, output={"result": result}),
                          arguments)


def complete(table: list[dict], shown: int, output_id: str = "out_rank") -> dict:
    return {"status": "COMPLETED", "session_id": "sess_1", "released_contents": [
        {"output_id": output_id, "name": "ranking", "type": "TABLE", "rows": [dict(r) for r in table[:shown]],
         "row_count": len(table), "truncated": shown < len(table)}]}


def page(table: list[dict], offset: int, limit: int, output_id: str = "out_rank") -> dict:
    return {"output_id": output_id, "released": True, "offset": offset, "row_count": len(table),
            "rows": [dict(r) for r in table[offset:offset + limit]]}


def test_m44_a_later_page_does_not_replace_the_rows_read_before() -> None:
    table = broker_table()
    orc, state = tracker(reader({"out_rank": table})), RunState(request_id="r", started=0.0, input_items=[])
    track(orc, state, "complete_analysis", complete(table, 13))
    track(orc, state, "get_session_output", page(table, 13, 12), {"session_id": "sess_1"})  # as in the M44 run
    out = render("XL {{out.out_rank.rows[broker=XL].crash_net_bn|dec:0}}, "
                 "SQ {{out.out_rank.rows[broker=SQ].times_largest_net_buyer|int}}", state.ref_sources)
    assert out.problems == [] and out.text == "XL 68, SQ 67"


def test_m44_a_row_the_run_never_read_is_fetched_from_the_released_table() -> None:
    table = broker_table()
    calls: list = []
    orc, state = tracker(reader({"out_rank": table}, calls)), RunState(request_id="r", started=0.0, input_items=[])
    track(orc, state, "get_session_output", page(table, 13, 12), {"session_id": "sess_1"})  # only a later page read
    out = render("{{out.out_rank.rows[broker=XL].crash_net_bn|dec:0}}", state.ref_sources)
    assert out.text == "68" and calls  # read by the backend, not taken from the page
    assert out.values[0].label == "DATA_COVERAGE_VERIFIED"


def test_m44_a_position_in_a_keyed_table_is_refused_with_the_selector_to_use() -> None:
    table = broker_table()
    orc, state = tracker(reader({"out_rank": table})), RunState(request_id="r", started=0.0, input_items=[])
    track(orc, state, "get_session_output", page(table, 13, 12), {"session_id": "sess_1"})
    out = render("XL {{out.out_rank.rows[0].crash_net_bn}}", state.ref_sources)
    assert out.problems and "identified by 'broker'" in out.problems[0]
    assert "rows[broker=XL]" in out.problems[0]  # the hint names the row the position really means


def test_m44_rows_carry_their_position_in_the_complete_table() -> None:
    table = broker_table()
    orc, state = tracker(), RunState(request_id="r", started=0.0, input_items=[])
    shown = page(table, 13, 12)
    track(orc, state, "get_session_output", shown, {"session_id": "sess_1"})
    assert [row["_row"] for row in shown["rows"]][:2] == [13, 14]  # the model sees the true positions


def test_m44_a_table_without_an_identity_column_keeps_absolute_positions() -> None:
    table = [{"value": float(i)} for i in range(300)]  # numbers only: no column identifies a row
    orc, state = tracker(reader({"out_v": table})), RunState(request_id="r", started=0.0, input_items=[])
    track(orc, state, "get_session_output", page(table, 200, 50, "out_v"), {"session_id": "sess_1"})
    out = render("{{out.out_v.rows[0].value|int}} {{out.out_v.rows[210].value|int}}", state.ref_sources)
    assert out.problems == [] and out.text == "0 210"  # row 0 of the table, not of the page


def test_m44_a_second_table_type_a_ticker_ranking_read_in_pages() -> None:
    tickers = [{"ticker": f"T{i:03d}", "ret": i / 1000} for i in range(840)]
    orc, state = tracker(reader({"out_ret": tickers})), RunState(request_id="r", started=0.0, input_items=[])
    track(orc, state, "complete_analysis", complete(tickers, 200, "out_ret"))
    track(orc, state, "get_session_output", page(tickers, 600, 200, "out_ret"), {"session_id": "sess_1"})
    out = render("{{out.out_ret.rows[ticker=T005].ret|pct:1}} {{out.out_ret.rows[ticker=T805].ret|pct:1}}",
                 state.ref_sources)
    assert out.problems == [] and out.text == "0,5% 80,5%"


def test_m44_without_a_reader_an_unread_row_is_unresolved_never_another_row() -> None:
    table = broker_table()
    orc, state = tracker(None), RunState(request_id="r", started=0.0, input_items=[])
    track(orc, state, "get_session_output", page(table, 13, 12), {"session_id": "sess_1"})
    out = render("{{out.out_rank.rows[broker=XL].crash_net_bn}}", state.ref_sources)
    assert out.problems and "no row" in out.problems[0]


def p14_sources() -> ReferenceSources:
    sources = ReferenceSources()
    sources.add("finding", "a", {"backend": {"ci": [-0.505, 0.561], "p_value": None},
                                 "warnings": ["FREQUENCY_GAPS", "HISTORICAL_REFERENCE_USES_CURRENT_STATE"],
                                 "flag": True, "nan": float("nan"), "inf": float("inf"), "empty": [],
                                 "rows": [{"a": 1}], "long": list(range(12)), "date": "2026-09-30"}, "L")
    return sources


def test_p14_every_value_has_a_display() -> None:
    cases = {
        "{{finding.a.backend.ci|dec:2}}": "−0,51; 0,56",
        "{{finding.a.backend.p_value}}": "null",
        "{{finding.a.warnings}}": "FREQUENCY_GAPS; HISTORICAL_REFERENCE_USES_CURRENT_STATE",
        "{{finding.a.flag}}": "ya",
        "{{finding.a.nan}}": "undefined",
        "{{finding.a.inf|dec:1}}": "undefined",
        "{{finding.a.empty}}": "tidak ada",
        "{{finding.a.long|int}}": "0; 1; 2; 3; 4; 5; 6; 7 (+4 lainnya)",
        "{{finding.a.date|dec:1}}": "2026-09-30",
    }
    for reference, shown in cases.items():
        out = render(reference, p14_sources())
        assert out.problems == [] and out.missing == [] and out.text == shown, (reference, out.text, out.problems)


def test_p14_numbers_inside_a_list_are_provenance_sources() -> None:
    out = render("{{finding.a.backend.ci|dec:2}}", p14_sources())
    assert [v.value for v in out.values] == [-0.505, 0.561] and {v.label for v in out.values} == {"L"}


def test_p14_an_object_or_a_list_of_objects_is_a_marker() -> None:
    for reference, marker in (("{{finding.a.backend}}", "[backend]"), ("{{finding.a.rows}}", "[rows]")):
        out = render(reference, p14_sources())
        assert out.text == marker and out.missing and out.problems == []


def test_table_rows_read_on_demand_are_bounded() -> None:
    calls: list = []

    def fetch(offset, limit):
        calls.append(offset)
        return [{"k": f"r{i}"} for i in range(offset, offset + limit)], 100_000

    table = TableRows(100_000, fetch)
    table.all()
    assert len(calls) == 25  # TABLE_MAX_FETCHES: at most 5,000 rows read at render time


# ---------------------------------------------------------------- P17: claims are marked, never rejected

from app.orchestrator import AgentOrchestrator as _Orc, annotate_claims, negated_in_clause  # noqa: E402

E02 = ("Jadi klaim bahwa net beli asing menyebabkan harga BBCA naik **tidak terbukti** oleh pemeriksaan historis ini, "
       "dan hasil ini bukan prediksi.")


def spans(text: str, dataneed: bool = True) -> list[tuple[str, int, int]]:
    state = RunState(request_id="r", started=0.0, input_items=[])
    return _Orc._claim_spans(state, text, dataneed=dataneed)


def test_p17_the_e02_sentence_denies_the_claim_and_is_not_flagged() -> None:
    assert spans(E02) == []


def test_p17_a_negation_after_the_phrase_in_its_clause_governs_it() -> None:
    for text in ("Klaim bahwa X menyebabkan Y tidak didukung data.", "That foreign buying causes the rebound is not "
                 "supported by this run.", "Hipotesis kenaikan ini tidak terbukti."):
        assert spans(text) == [], text


def test_p17_a_claim_with_a_negation_in_another_clause_is_still_flagged() -> None:
    text = "Net beli asing menyebabkan kenaikan, bukan sekadar kebetulan."
    assert [k for k, _, _ in spans(text)] == ["CAUSAL"]
    assert negated_in_clause(text, text.index("menyebabkan"), text.index("menyebabkan") + 11) is False


def test_p17_the_users_example_terbukti_naik_is_flagged_as_proof_and_italicised() -> None:
    text = "Ringkasnya: BBCA terbukti naik setelah net beli asing. Data berakhir 2026-08-31."
    found = spans(text)
    assert [k for k, _, _ in found] == ["PROOF"]
    marked, annotations = annotate_claims(text, found)
    assert marked == "Ringkasnya: *BBCA terbukti naik setelah net beli asing*. Data berakhir 2026-08-31."
    (a,) = annotations
    assert a["kind"] == "PROOF" and marked[a["start"]:a["end"]] == a["quote"] and "bukan bukti" in a["note"]


def test_p17_two_claims_in_one_sentence_give_one_italic_span_and_two_annotations() -> None:
    text = "- Net beli asing menyebabkan kenaikan dan memprediksi reli berikutnya."
    marked, annotations = annotate_claims(text, spans(text))
    assert marked == "- *Net beli asing menyebabkan kenaikan dan memprediksi reli berikutnya*."
    assert sorted(a["kind"] for a in annotations) == ["CAUSAL", "PREDICTIVE"]
    assert all(marked[a["start"]:a["end"]] == a["quote"] for a in annotations)


def test_p17_a_sentence_with_emphasis_marks_only_the_phrase() -> None:
    text = "**XL** menyebabkan kenaikan."
    marked, annotations = annotate_claims(text, spans(text))
    assert marked == "**XL** *menyebabkan* kenaikan." and annotations[0]["quote"] == "menyebabkan"


def test_p17_the_response_shape_is_unchanged_without_annotations() -> None:
    from app.schemas import AgentRunResponse, ClaimAnnotation

    base = {"request_id": "r", "status": "COMPLETED", "response": None,
            "execution": {"provider": "openrouter", "model": "m", "iterations": 0, "tool_call_count": 0}}
    plain = AgentRunResponse.model_validate(base).model_dump(mode="json")
    assert "annotations" not in plain
    marked = AgentRunResponse.model_validate({**base, "annotations": [ClaimAnnotation(
        kind="CAUSAL", quote="q", start=1, end=2, note="n")]}).model_dump(mode="json")
    assert marked["annotations"][0]["kind"] == "CAUSAL"


def test_p17_mode4_moves_each_steps_annotations_into_the_combined_answer() -> None:
    from types import SimpleNamespace

    from app.mode4 import Mode4Orchestrator as _M4  # noqa: F401 - the merge lives on the run
    from app.mode4 import _Mode4Run
    from app.schemas import ClaimAnnotation

    research_answer = "Ringkasnya: *net beli asing menyebabkan kenaikan*."
    note = ClaimAnnotation(kind="CAUSAL", quote="net beli asing menyebabkan kenaikan", start=13, end=48, note="n")
    research = SimpleNamespace(annotations=[note], response=SimpleNamespace(answer=research_answer))
    combined = SimpleNamespace(answer="**Jawaban**\n\nJawaban.\n\n**Hasil riset**\n\n" + research_answer)
    (moved,) = _Mode4Run._annotations(combined, (None, research, None))
    assert combined.answer[moved.start:moved.end] == "net beli asing menyebabkan kenaikan"


# ---------------------------------------------------------------- G13: counted rows reach the plan

class CountingGovernor:
    """/v1/extract estimate_only as the Governor answers with SQL_ESTIMATE_COUNT_ENABLED: result_rows is the counted
    number (row_basis COUNTED), or the planner's estimate when a part's count timed out (PLANNER)."""

    def __init__(self, rows: int, timed_out: bool = False) -> None:
        self.rows = rows
        self.timed_out = timed_out

    def extract(self, spec, lineage, *, planned_parts=1, estimate_only=False):
        basis = "PLANNER" if self.timed_out else "COUNTED"
        return {"status": "WITHIN_LIMITS", "estimates": {"result_rows": self.rows, "row_basis": basis,
                                                         "planner_rows": self.rows // 3}}


def test_g13_feasibility_reports_counted_rows_and_their_basis() -> None:
    from app.tools.data_planner import ExecutionPlanner
    from test_data_planner import NEED, need

    for preflight in (False, True):
        draft = need()
        draft.update(draft_id=NEED)
        counted = ExecutionPlanner(None, CountingGovernor(319_801), preflight=preflight).estimate(draft)
        assert {r.get("row_basis") for r in counted["requests"]} == {"COUNTED"}, preflight
        assert all(r["estimated_rows"] % 319_801 == 0 for r in counted["requests"])
        uncertain = ExecutionPlanner(None, CountingGovernor(10, timed_out=True), preflight=preflight).estimate(draft)
        assert {r.get("row_basis") for r in uncertain["requests"]} == {"PLANNER"}


def test_g13_without_counting_the_estimate_keeps_its_shape() -> None:
    from app.tools.data_planner import ExecutionPlanner
    from test_data_planner import NEED, need
    from test_preflight_parts import CostGovernor

    draft = need()
    draft.update(draft_id=NEED)
    assert all("row_basis" not in r for r in ExecutionPlanner(None, CostGovernor()).estimate(draft)["requests"])


def test_g13_an_e02_shaped_plan_over_the_bundle_limit_is_stopped_before_the_user_sees_it() -> None:
    from test_multi_angle import feasibility_args, planner, request, requirement, run_plan

    # e02 (suite20d): one angle needs two requests over every stock, 1,295,417 counted rows each (2,590,834 in all)
    rows = {"Price_Stock_Indonesia_IDX": 1_295_417, "Feature_03_Stock_Broker_Daily": 1_295_417}
    args = feasibility_args([
        requirement("a_fall", request("a_fall_A"),
                    request("a_fall_B", table="Feature_03_Stock_Broker_Daily", name="broker_daily")),
        requirement("a_rank", request("a_rank_A")),
    ])
    outcome = run_plan(planner(rows=rows, max_rows=2_000_000)[0], args)
    assert outcome["status"] != "FEASIBLE", outcome["view"]  # never a plan that its bundle cannot hold


# ---------------------------------------------------------------- P23 and P25 (golden test 2026-10-02)

def test_p23_a_released_table_is_shown_by_the_units_it_declared() -> None:
    """The declared units travel with the table: in the completion's contents, in a page read later, and for a table
    listed without its content (learned with its first page)."""
    rows = [{"segment": "ALL", "delta_mean": 0.78, "hit_rate": 0.62}]
    units = {"delta_mean": "PERCENT", "hit_rate": "FRACTION"}

    def read(session_id, output_id, request_id, offset, limit):
        return {"released": True, "rows": [dict(r) for r in rows], "row_count": 1, "meta": {"units": units}}

    orc, state = tracker(read), RunState(request_id="r", started=0.0, input_items=[])
    shown = {"status": "COMPLETED", "session_id": "sess_1", "released_contents": [
        {"output_id": "out_es", "name": "drops", "type": "TABLE", "rows": [dict(r) for r in rows], "row_count": 1,
         "units": units}],
        "released_outputs": [{"output_id": "out_es"}, {"output_id": "out_hidden", "name": "drops2", "type": "TABLE",
                                                         "row_count": 1}]}
    track(orc, state, "complete_analysis", shown)
    out = render("{{out.o1.rows[segment=ALL].delta_mean|pct:2}}, {{out.o1.rows[segment=ALL].hit_rate|pctv:0}}, "
                 "{{out.o2.rows[segment=ALL].hit_rate|dec:1}} persen", state.ref_sources)
    assert out.problems == [] and out.text == "0,78%, 62%, 62,0%"
    page = {"output_id": "out_es", "released": True, "offset": 0, "row_count": 1, "rows": [dict(r) for r in rows],
            "meta": {"units": units}}
    track(orc, state, "get_session_output", page, {"session_id": "sess_1"})
    assert render("{{out.o1.rows[segment=ALL].hit_rate|pp:1}}", state.ref_sources).text == "62,0 pp"


def test_p25_a_refused_number_from_the_runs_own_code_is_named_as_a_code_literal() -> None:
    """A threshold the code chose ("persentil ke-90") is not a result source, but the refusal says where it came from
    and where it belongs; a number from nowhere is not named so."""
    state = RunState(request_id="r", started=0.0, input_items=[])
    text = "Pembelian di atas persentil ke-90 diikuti return 7,7%."
    assert AgentOrchestrator._code_literal_hint(state, text, ["90", "7,7%"]) == ""  # no successful code
    state.code_numbers.extend([50.0, 75.0, 90.0, 0.9])
    hint = AgentOrchestrator._code_literal_hint(state, text, ["90", "7,7%"])
    assert "Of these, 90 appear only as literals in the code that ran" in hint and "7,7%" not in hint
    assert "methodology" in hint and "emit_json" in hint


def test_an_insight_turn_must_open_the_result_it_explains() -> None:
    """H1 (M63, golden test 2026-10-02): turn 3 explained the turn 1 ranking with a guessed board filter instead of
    opening the ranking; an INSIGHT turn is refused at complete_analysis until it opens an earlier result."""
    from app import data_record as records

    orc = tracker()
    state = RunState(request_id="req_3", started=0.0, input_items=[])
    state.plan_meta["turn_kind"] = "INSIGHT"
    records.add_output(state.data_record, "req_1", alias="o1", output_id="out_rank", session_id="s1", name="ranking",
                       columns=["broker"], row_count=5, kind="TABLE")
    refused = orc._insight_source_unopened(state, "c1", "complete_analysis")
    assert refused is not None and refused.output["error"]["code"] == "INSIGHT_SOURCE_NOT_OPENED"
    assert "out_rank" in refused.output["error"]["message"] and "load_output" in refused.output["error"]["message"]
    state.opened_earlier = True
    assert orc._insight_source_unopened(state, "c1", "complete_analysis") is None
    # another turn kind, or an INSIGHT turn with no earlier result, is never refused
    other = RunState(request_id="req_3", started=0.0, input_items=[])
    other.plan_meta["turn_kind"] = "CONTINUE"
    other.data_record = state.data_record
    assert orc._insight_source_unopened(other, "c1", "complete_analysis") is None
    fresh = RunState(request_id="req_3", started=0.0, input_items=[])
    fresh.plan_meta["turn_kind"] = "INSIGHT"
    assert orc._insight_source_unopened(fresh, "c1", "complete_analysis") is None


def test_a_consistency_claim_with_another_definition_is_repaired_or_stated() -> None:
    """H1 (M63): the answer is sent back once; if the claim stays, a limitation states the difference."""
    import pytest
    from conftest import ANSWER

    from app import data_record as records
    from app.orchestrator import GateRejection
    from app.schemas import FinalResponse

    orc = tracker()
    orc.audit_outbox = None
    state = RunState(request_id="req_3", started=0.0, input_items=[])
    records.add_output(state.data_record, "req_3", alias="o2", output_id="out_top", session_id="s", name="top15",
                       columns=["broker"], row_count=15, kind="TABLE",
                       definition={"filters": [{"column": "market_board", "operator": "EQ", "value": "Regular"}]})
    state.completions["s"] = {"status": "COMPLETED", "final": {"carried_inputs": [
        {"output_id": "out_rank", "name": "ranking", "definition": {"filters": [], "notes": "boards combined"}}]}}
    final = FinalResponse.model_validate({**ANSWER, "answer": "Dibatasi pada board Regular agar konsisten dengan "
                                                              "jawaban sebelumnya."})
    with pytest.raises(GateRejection):
        orc._definition_claims(state, final)
    state.gate_kinds_rejected.add("DEFINITION")
    kept = orc._definition_claims(state, final)
    assert kept.answer == final.answer and state.definition_annotated
    assert any("tidak didukung" in line and "Regular" in line for line in kept.limitations)
