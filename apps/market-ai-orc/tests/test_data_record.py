"""M47 (user decision 2026-10-01): the conversation's data record.

Live (ma-integrity-20261001a, m01): the mode 4 research-plan step got only the analysis text, so it read the catalog
again (5 calls) for the tables the analysis had just used; nothing structured about the data used was carried between
steps or turns. The record (tables and columns used and read, approved needs, released outputs with their ref,
research angles' data) is now carried from step to step and turn to turn, offered as one bounded note, seeds the
catalog ledger, and is returned with the response.
"""
from __future__ import annotations

from typing import Any

from app import data_record as records
from app.catalog_protocol import CatalogLedger, TableSeen
from app.conversation_plans import DATA_RECORD_KEY, advance
from app.orchestrator import AgentOrchestrator, RunState
from app.tools import ToolRegistry
from app.tools.registry import ToolOutcome
from conftest import final_response
from test_mode4 import first_round_script, m4, run_result, response, stub
from test_orchestrator import ANSWER, orchestrator, request

APPROVED = {
    "status": "APPROVED", "need_id": "need_" + "a" * 24,
    "approved": {"spec_sha256": "s" * 64, "catalog_sha256": "c" * 64, "reference_date": "2026-10-01",
                 "requests": [{"data_request_id": "flows_c", "logical_name": "flows",
                               "source_table": "Feature_02_Broker_Rolling",
                               "extract_columns": ["date", "broker_code", "ticker", "net_value"],
                               "ranges": [{"range_id": "study", "start": "2022-01-03", "end": "2026-08-31"}],
                               "scope_sha256": "d" * 64, "restricted_by": [3]},
                              {"data_request_id": "banks_b", "logical_name": "banks",
                               "source_table": "IDX_Stock_Universe", "extract_columns": ["Ticker", "Industry"],
                               "ranges": [], "scope_sha256": "e" * 64, "restricted_by": []}]}}


def built() -> dict[str, Any]:
    record = records.empty()
    records.add_need(record, "q-m4a", APPROVED, "ANALYSIS")
    ledger = CatalogLedger()
    ledger.tables["Feature_02_Broker_Rolling"] = TableSeen(contract=True, time_column="date",
                                                           entity_column="broker_code",
                                                           columns={"date", "broker_code", "net_value", "buy_value"})
    records.add_catalog(record, ledger.tables, "q-m4a")
    records.add_output(record, "q-m4a", alias="o1", output_id="out_" + "f" * 24, session_id="sess_1",
                       name="broker_crash_days", columns=["broker", "days", "net_value"], row_count=120)
    records.add_research(record, "q-m4b", {"angle_data_contracts": {"a_fall": {"datasets": [
        {"source_table": "Price_Stock_Indonesia_IDX", "columns": ["close", "return_1d_pct"]}]}}})
    return record


def test_the_record_keeps_tables_columns_needs_outputs_and_research() -> None:
    record = built()
    flows = record["tables"]["Feature_02_Broker_Rolling"]
    assert flows["used"] == ["broker_code", "date", "net_value", "ticker"]
    assert flows["read"] == ["broker_code", "buy_value", "date", "net_value"]
    assert flows["time_column"] == "date" and flows["entity_column"] == "broker_code"
    assert set(record["tables"]) == {"Feature_02_Broker_Rolling", "IDX_Stock_Universe", "Price_Stock_Indonesia_IDX"}
    assert record["needs"][0]["requests"][0]["columns"] == ["date", "broker_code", "ticker", "net_value"]
    assert record["outputs"][0]["ref"] == "out.o1" and record["research"][0]["angle_id"] == "a_fall"
    note = records.note(record)
    assert note.startswith("DATA RECORD") and "Feature_02_Broker_Rolling [entity_column=broker_code" in note
    assert "out.o1 = out_" in note and "a_fall (q-m4b)" in note
    assert records.normalize(record) == record and records.normalize({"version": 99}) == records.empty()


def test_a_need_keeps_its_subject_and_relationships_for_the_next_run() -> None:
    """EXEC-D P-h (M106, golden test 2026-10-07): the approved view of a need has no subject and no relationships, so a
    later step read the catalog again for them (q7 turn 1 step B: 3 calls); the record keeps them from the arguments."""
    state = RunState(request_id="q-m4a", started=0.0, input_items=[])
    arguments = {"mode": "ANALYSIS",
                 "subject": {"data_domain": "broker_flow", "entity_type": "broker", "asset_type": "STOCK"},
                 "relationships": [{"relationship_id": 3, "left_request_id": "flows_c", "left_columns": ["ticker"],
                                    "right_request_id": "banks_b", "right_columns": ["Ticker"], "join_type": "INNER",
                                    "join_semantics": "CURRENT_STATE"},
                                   {"relationship_id": 7, "left_request_id": "flows_c", "left_column": "date",
                                    "right_request_id": "banks_b", "right_column": "date", "join_type": "LEFT",
                                    "join_semantics": "EXACT_DATE"}]}
    AgentOrchestrator._track_dataneed(state, "submit_data_need_spec", arguments,
                                      ToolOutcome("c1", "submit_data_need_spec", True, {"result": APPROVED}))
    need = state.data_record["needs"][0]
    assert need["subject"] == "broker_flow/broker/STOCK"
    assert need["relationships"] == [
        "flows_c.ticker = banks_b.Ticker (INNER, CURRENT_STATE, relationship 3)",
        "flows_c.date = banks_b.date (LEFT, EXACT_DATE, relationship 7)"]
    for text in (records.note(state.data_record), records.full_note(state.data_record)):
        assert "subject broker_flow/broker/STOCK" in text
        assert "relationships flows_c.ticker = banks_b.Ticker (INNER, CURRENT_STATE, relationship 3)" in text
    assert records.normalize(state.data_record) == state.data_record
    plain = records.empty()
    records.add_need(plain, "q", APPROVED, "ANALYSIS")
    assert "subject" not in plain["needs"][0] and "relationships" not in plain["needs"][0]


def test_the_note_is_bounded_and_never_drops_tables() -> None:
    record = built()
    for n in range(200):
        records.add_output(record, f"q-{n}", alias=f"o{n + 2}", output_id=f"out_{n:024x}", session_id="s",
                           name="x" * 80, columns=[f"c{i}" for i in range(30)], row_count=n)
    note = records.note(record)
    assert len(note) <= records.MAX_NOTE_CHARS and len(record["outputs"]) == records.MAX_OUTPUTS
    assert all(table in note for table in record["tables"])  # tables and columns come first


def test_a_run_offers_the_record_returns_it_and_extends_it() -> None:
    agent, client = orchestrator([final_response(ANSWER)], registry=ToolRegistry())
    result = agent.run(request(), data_record=built())
    first_input = client.payloads[0]["input"]
    assert any(isinstance(item.get("content"), str) and item["content"].startswith("DATA RECORD")
               for item in first_input)
    assert result.data_record["tables"]["Feature_02_Broker_Rolling"]["used"] == [
        "broker_code", "date", "net_value", "ticker"]
    state = RunState(request_id="q-2", started=0.0, input_items=[])
    AgentOrchestrator._track_dataneed(state, "submit_data_need_spec", {"mode": "ANALYSIS"},
                                      ToolOutcome("c1", "submit_data_need_spec", True, {"result": APPROVED}))
    assert state.data_record["needs"][0]["need_id"] == APPROVED["need_id"]
    plain, _ = orchestrator([final_response(ANSWER)], registry=ToolRegistry())
    empty = plain.run(request())
    assert empty.data_record is None and "data_record" not in empty.model_dump(mode="json")


def test_the_record_seeds_the_catalog_ledger() -> None:
    ledger = CatalogLedger()
    records.seed_ledger(built(), ledger)
    flows = ledger.tables["Feature_02_Broker_Rolling"]
    assert flows.contract and {"ticker", "buy_value", "net_value"} <= flows.columns and flows.time_column == "date"


def test_mode4_hands_each_step_the_record_of_the_steps_before() -> None:
    record = built()
    script = first_round_script(m4a=run_result("q-m4a", response("ANSWER", "Analisis: broker ZP."))
                                .model_copy(update={"data_record": record}))
    wrapper, inner = stub(script)
    result = wrapper.run(m4(request_id="q", conversation_id="conv", message="Siapa broker?"), data_record=None)
    assert inner.records[0] is None  # the first turn starts empty
    assert all(r is record for r in inner.records[1:])  # the plan, research and suggestion steps get it
    assert result.data_record == record


def test_the_conversation_state_keeps_the_record_for_the_next_turn() -> None:
    result = run_result("q-1", response("ANSWER", "Jawaban.")).model_copy(update={"data_record": built()})
    state = advance({}, result, "q-1", 0)
    assert state[DATA_RECORD_KEY]["tables"]["IDX_Stock_Universe"]["used"] == ["Industry", "Ticker"]
    later = advance(state, run_result("q-2", response("ANSWER", "Jawaban.")), "q-2", 1)
    assert later[DATA_RECORD_KEY] == state[DATA_RECORD_KEY]  # a turn without a record keeps the stored one


def test_aliases_continue_across_steps_and_turns() -> None:
    """P18 live defect (ma-steps-20261001a, m01): every step numbered its outputs from o1 again, so out.o1 named a
    different output in m4a and m4c. The numbering now comes from the record and never restarts."""
    record = built()  # o1 = out_fff… from q-m4a
    state = RunState(request_id="q-m4c", started=0.0, input_items=[{"role": "user", "content": "q"}])
    agent, _ = orchestrator([final_response(ANSWER)], registry=ToolRegistry())
    agent._seed_data_record(state, record)
    assert state.ref_aliases == {"out_" + "f" * 24: "o1"} and state.ref_next == 2
    listed = {"output_id": "out_" + "1" * 24, "name": "n", "columns": ["a"], "row_count": 1}
    agent._track_references(state, "complete_analysis", ToolOutcome("c1", "complete_analysis", True, {
        "result": {"status": "COMPLETED", "session_id": "s",
                   "released_contents": [listed, {"output_id": "out_" + "f" * 24, "name": "old"}]}}))
    assert state.ref_aliases["out_" + "1" * 24] == "o2"  # a new output continues the numbering
    assert state.ref_aliases["out_" + "f" * 24] == "o1"  # an earlier output read again keeps its alias
    assert state.data_record["next_alias"] == 3
    # an older record that gave one alias to two outputs: the newer keeps it, the numbering goes past both
    clash = records.normalize({**built(), "next_alias": None})
    records.add_output(clash, "q-old", alias="o1", output_id="out_" + "2" * 24, session_id="s", name="x",
                       columns=[], row_count=1)
    assert records.aliases(clash) == ({"out_" + "2" * 24: "o1"}, 2)
    for n in range(3, 60):  # outputs past MAX_OUTPUTS are dropped, their numbers are never given again
        records.add_output(clash, "q", alias=f"o{n}", output_id=f"out_{n:024x}", session_id="s", name="x",
                           columns=[], row_count=1)
    assert records.normalize(clash)["next_alias"] == 60


def test_category_values_relationships_and_coverage_are_kept_and_shown_without_silent_cuts() -> None:
    """P5 (ma-steps-20261001a, m01): later steps looked up Industry "Banks", relationships and coverage again."""
    record = built()
    records.add_catalog_facts(record, "get_dimension_values", {}, {
        "status": "VALUES_READY", "table": "IDX_Stock_Universe", "column": "Industry", "match": "Bank",
        "truncated": False, "values": ["Banks"]}, "q-m4a", "2026-10-01T10:00:00")
    records.add_catalog_facts(record, "get_dimension_values", {}, {
        "status": "VALUES_READY", "table": "IDX_Broker_Profile", "column": "broker_type", "match": None,
        "truncated": False, "values": ["Domestic", "Foreign"]}, "q-m4a", "2026-10-01T10:00:00")
    records.add_catalog_facts(record, "get_dimension_values", {}, {
        "status": "REJECTED", "table": "X", "column": "y"}, "q-m4a", "2026-10-01T10:00:00")
    records.add_catalog_facts(record, "get_catalog_details", {}, {"sections": {
        "RELATIONSHIPS": {"entries": [{"relationship_id": 7, "left_table": "Feature_02_Broker_Rolling",
                                       "left_columns": ["ticker"], "right_table": "IDX_Stock_Universe",
                                       "right_columns": ["Ticker"], "temporal_rule": "CURRENT_STATE"}]},
        "COVERAGE": {"datasets": {"Feature_02_Broker_Rolling": {"actual_max_date": "2026-08-31",
                                                                "last_checked_at": "2026-10-01T00:34"}}}}},
        "q-m4a", "2026-10-01T10:00:00")
    assert record["values"]["IDX_Stock_Universe.Industry"] == {"values": ["Banks"], "complete": False,
                                                               "checked_at": "2026-10-01T10:00:00",
                                                               "request_id": "q-m4a"}
    assert record["values"]["IDX_Broker_Profile.broker_type"]["complete"] and "X.y" not in record["values"]
    note = records.note(record)
    assert "IDX_Stock_Universe.Industry: Banks [only those read]" in note
    assert "7: Feature_02_Broker_Rolling(ticker) -> IDX_Stock_Universe(Ticker) CURRENT_STATE" in note
    assert "Feature_02_Broker_Rolling: actual_max_date=2026-08-31" in note
    assert records.normalize(record) == record
    many = records.empty()
    records.add_catalog_facts(many, "get_dimension_values", {}, {
        "status": "VALUES_READY", "table": "T", "column": "c", "match": None, "truncated": False,
        "values": [f"v{i:02d}" for i in range(30)]}, "q", "t")
    assert "… and 10 more (not shown)" in records.note(many)
    for n in range(300):
        records.add_output(many, "q", alias=f"o{n + 1}", output_id=f"out_{n:024x}", session_id="s", name="x" * 60,
                           columns=[f"c{i}" for i in range(30)], row_count=n)
    assert "more not shown (the full record is kept by the backend)" in records.note(many)


def test_the_note_shows_each_request_filter_and_each_output_definition() -> None:
    """H1 (M63): the filter applied by the data request (derived) and the filters applied in code (declared) are read
    by later turns, so the definition of an earlier result is never guessed."""
    record = records.empty()
    records.add_need(record, "req_1", {"need_id": "need_1", "approved": {"spec_sha256": "s", "requests": [{
        "data_request_id": "r_A", "logical_name": "flows", "source_table": "Feature_02_Broker_Rolling",
        "extract_columns": ["ticker", "date", "net_value_1d"], "ranges": [], "scope_sha256": "x",
        "scope": {"type": "AND", "children": [
            {"type": "PREDICATE", "column": "market_board", "operator": "EQ", "value": "Regular"},
            {"type": "PREDICATE", "column": "investor_type", "operator": "IN", "value": ["F", "D"]}]},
        "restrictions": [{"right_table": "IDX_Stock_Universe",
                          "right_scope": {"type": "PREDICATE", "column": "Industry", "operator": "EQ",
                                          "value": "Banks"}}]}]}}, "ANALYSIS")
    records.add_output(record, "req_1", alias="o1", output_id="out_1", session_id="sess_1", name="ranking",
                       columns=["broker"], row_count=10,
                       definition={"filters": [], "period": {"start": "2022-01-03", "end": "2026-08-31"},
                                   "notes": "all boards combined"},
                       lineage={"execution_id": "exe_1", "code_sha256": "c", "need_id": "need_1"})
    records.add_output(record, "req_1", alias="o2", output_id="out_2", session_id="sess_1", name="old",
                       columns=["x"], row_count=1)
    text = records.note(record)
    assert "where (investor_type IN F, D AND market_board EQ Regular)" in text \
        or "where (market_board EQ Regular AND investor_type IN F, D)" in text
    assert "restricted to IDX_Stock_Universe: Industry EQ Banks" in text
    assert "definition: filters: none beyond the data request; period 2022-01-03..2026-08-31; notes: all boards " \
           "combined" in text
    assert "out.o2 = out_2 \"old\"" in text and "definition: NOT STATED" in text
    # an output read again keeps its definition and lineage
    records.add_output(record, "req_2", alias="o1", output_id="out_1", session_id="sess_1", name="ranking",
                       columns=["broker"], row_count=10)
    again = next(o for o in record["outputs"] if o["output_id"] == "out_1")
    assert again["definition"]["notes"] == "all boards combined" and again["lineage"]["execution_id"] == "exe_1"


def test_a_finding_run_again_with_another_rule_keeps_the_earlier_one() -> None:
    """H2 (user decision 2026-10-02): "ubah jadi 5%" runs the test again; the 3% result stays beside the new one."""
    record = records.empty()
    three = {"hypothesis_id": "h1", "verdict": "SUPPORTED", "success_rule": {"operator": ">=", "value": 3.0}}
    five = {**three, "verdict": "INCONCLUSIVE", "success_rule": {"operator": ">=", "value": 5.0}}
    records.add_finding(record, "req_1", kind="HYPOTHESIS", finding_id="h1", finding=three)
    records.add_finding(record, "req_2", kind="HYPOTHESIS", finding_id="h1", finding=five)
    ids = {f["id"]: f["finding"] for f in record["findings"]}
    assert ids["h1"]["success_rule"]["value"] == 5.0 and ids["h1@1"]["success_rule"]["value"] == 3.0
    text = records.note(record)
    assert "finding.h1 " in text and "finding.h1@1" in text and "success rule applied: outcome >= 3.0" in text
    # the same rule recorded again replaces it (a repeat, not a new test)
    records.add_finding(record, "req_3", kind="HYPOTHESIS", finding_id="h1", finding=five)
    assert sorted(f["id"] for f in record["findings"]) == ["h1", "h1@1"]


def test_a_need_keeps_its_canonical_filter_for_a_later_count_unless_it_is_long() -> None:
    """EXEC-Y Fase 3 E1(1): an export counts the same rows in the source with the need's own filter; a filter longer
    than MAX_SCOPE_SPEC_CHARS is not kept (the file then says it was not checked) and the note never shows it."""
    short = {"type": "PREDICATE", "column": "ticker", "operator": "EQ", "values": ["BBRI"]}
    long = {"type": "PREDICATE", "column": "ticker", "operator": "IN", "values": [f"T{i:04d}" for i in range(400)]}
    record = records.empty()
    for need, scope in (("need_1", short), ("need_2", long)):
        records.add_need(record, "req_1", {"need_id": need, "approved": {"spec_sha256": "s", "requests": [{
            "data_request_id": "r", "logical_name": "flows", "source_table": "Feature_03_Stock_Broker_Daily",
            "extract_columns": ["date"], "ranges": [], "scope_sha256": "x", "scope": scope}]}}, "ANALYSIS")
    kept = [n["requests"][0].get("scope_spec") for n in record["needs"]]
    assert kept == [short, None]
    assert "scope_spec" not in records.note(record) and "ticker EQ BBRI" in records.note(record)
    assert records.normalize(record)["needs"][0]["requests"][0]["scope_spec"] == short
