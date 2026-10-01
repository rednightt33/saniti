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
