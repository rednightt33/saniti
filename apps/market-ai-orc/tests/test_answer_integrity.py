"""M44 and P14 (ANSWER_INTEGRITY_FIX_PLAN.md, 2026-10-01): references resolve against the complete released table,
never the last page read, keyed tables are referenced by their key, and every JSON value has a display."""
from __future__ import annotations

from app.orchestrator import AgentOrchestrator, RunState
from app.tools import ToolOutcome
from app.value_refs import ReferenceSources, TableRows, render


def tracker(row_reader=None) -> AgentOrchestrator:
    orc = AgentOrchestrator.__new__(AgentOrchestrator)
    orc.row_reader = row_reader
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
