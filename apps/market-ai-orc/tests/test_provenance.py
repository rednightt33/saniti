"""Number provenance gate, routing guard, and evidence labels (the answer contract enforced in code)."""
from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from pydantic import BaseModel, ConfigDict

from app.orchestrator import AgentOrchestrator
from app.provenance import FAMILY_PATTERNS, SourceIndex, check_answer, parse_numbers, requested_statistics
from app.schemas import AgentRunRequest, HistoryMessage
from app.tools import ToolSpec, build_default_registry
from app.tools.request_data import GovernorClient
from conftest import ScriptedClient, final_response, make_settings, tool_call_response
from test_analysis_tools import (ANA, REFERENCE, approved, completed, mock_sandbox, run_args, sandbox_module,
                                 spec_args)

PRICE = "Price_Stock_Indonesia_IDX"


def fact(value: Any, kind: str = "VALUE", aggregation: str | None = None, entity: str | None = "BBCA",
         date: str | None = "2026-08-31") -> dict[str, Any]:
    return {"fact_id": "fct_" + "1" * 24, "kind": kind, "table": PRICE, "column": "close" if kind == "VALUE" else
            "volume", "aggregation": aggregation, "entity": entity, "date": date if kind == "VALUE" else None,
            "scope": None if kind == "VALUE" else {"entities": ["BBCA"], "from": "2026-08-24", "to": "2026-08-28"},
            "value": value, "query_id": "qry_1"}


def facts_body(*facts: dict[str, Any]) -> dict[str, Any]:
    return {"decision": "FACTS_READY", "next_action": "USE_FACTS", "reason_code": "OK", "message": "ok",
            "request_id": "r", "query_id": "qry_1", "facts": list(facts), "missing": []}


def governor(lookup: dict[str, Any] | None = None) -> GovernorClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/lookup":
            return httpx.Response(200, json=lookup or facts_body())
        return httpx.Response(200, json={"decision": "DATASET_READY", "next_action": "RUN_ANALYSIS",
                                         "dataset": {"dataset_id": "ds_" + "a" * 24, "row_count": 148,
                                                     "entities_present_count": 2}})
    return GovernorClient("http://governor.test", "g" * 40, 5, transport=httpx.MockTransport(handler))


class NoArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


def preview_tool() -> ToolSpec:
    return ToolSpec(name="preview_table_rows", description="Example rows.", arguments_model=NoArgs,
                    handler=lambda _: {"rows": [["BBCA", "2026-08-31", 9137.5, 0.4213]]}, timeout_seconds=2)


def run(script: list, message: str, *, lookup: dict | None = None, sandbox: dict | None = None,
        history: list[HistoryMessage] | None = None):
    registry = build_default_registry(None, governor_client=governor(lookup),
                                      sandbox_client=mock_sandbox(sandbox or {}), sandbox_timeout_seconds=5)
    registry.register(preview_tool())
    scripted = ScriptedClient(script)
    result = AgentOrchestrator(make_settings(), scripted, registry, wall_clock=lambda: REFERENCE).run(
        AgentRunRequest(request_id="prov", message=message, history=history or []))
    return result, scripted


def answer(text: str, kind: str = "ANSWER", limitations: list[str] | None = None) -> dict[str, Any]:
    return {"response_type": kind, "answer": text, "clarification_question": None, "assumptions": [],
            "limitations": limitations if limitations is not None else ([] if kind == "ANSWER" else ["x"])}


def lookup_call(call_id: str = "c1") -> dict:
    return tool_call_response("lookup_fact", json.dumps({
        "purpose": "p", "mode": "VALUE", "table": PRICE, "entities": ["BBCA"], "dates": ["2026-08-31"],
        "date_range": None, "columns": ["close"], "aggregations": None, "per_entity": None}), call_id=call_id)


def rejection_text(scripted: ScriptedClient) -> str:
    return [i["content"] for i in scripted.payloads[-1]["input"] if i.get("role") == "user"][-1]


# --- parser ------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize(("text", "expected"), [
    ("Korelasi ≈ −0,031 pada 1 Juni – 31 Agustus 2026", [[-0.031]]),
    ("2.707 baris dan 1,234.5 serta 12.345.678,9", [[2.707, 2707.0], [1234.5], [12345678.9]]),
    ("RSI(14) di bawah 30, volume 1,25 juta", [[14.0], [30.0], [1250000.0]]),
    ("1. pertama\n2) kedua (3) ketiga", []),
    ("ticker T001, spec_3edb950c843bd9f9fab58b02, ds_1a2b, tahun 2026, 2026-08-31, Q3", []),
])
def test_numbers_are_read_like_a_reader_would_and_dates_ids_and_markers_are_skipped(text, expected) -> None:
    assert [sorted(v for v, _ in n.candidates) for n in parse_numbers(text)] == [sorted(e) for e in expected]


@pytest.mark.parametrize(("shown", "source", "ok"), [
    ("0.0112", 0.011158, True), ("0.0111", 0.011158, False),            # rounding to the displayed decimals
    ("1.12%", 0.011158, True), ("1,12%", 0.011158, True),              # decimal <-> percent, ID and EN separators
    ("turun 2,44%", -0.0244, True), ("naik 2,44%", -0.0244, False),     # a sign stated in words
    ("9.137,50", 9137.5, True), ("9,137.50", 9137.5, True), ("9136", 9137.5, False),
    ("-0.031", -0.03095364981854117, True), ("-0.030", -0.03095364981854117, False),
])
def test_matching_allows_display_rounding_and_percent_but_not_other_values(shown, source, ok) -> None:
    index = SourceIndex()
    index.add("FACT", [source])
    assert (check_answer(f"Nilai {shown}.", index).unsupported == []) is ok


def test_routing_patterns_are_the_sandbox_intent_rules() -> None:
    assert FAMILY_PATTERNS == sandbox_module("intent").FAMILY_PATTERNS
    assert requested_statistics("Berapa korelasi return BBCA dan BBRI?")[0] == {"CORRELATION", "RETURN"}
    assert requested_statistics("5 saham dengan volume tertinggi hari ini")[0] == {"RANKING"}
    assert requested_statistics("rata-rata close BBCA minggu ini") == (set(), True)
    assert requested_statistics("moving average 20 hari BBCA")[0] == {"SMA"}
    assert requested_statistics("Berapa close BBCA kemarin?") == (set(), False)


# --- the gate ----------------------------------------------------------------------------------------------------

def test_a_fact_answer_is_labelled_fact() -> None:
    result, _ = run([lookup_call(), final_response(answer("Close BBCA pada 31 Agustus 2026 adalah 9.125."))],
                    "Berapa close BBCA pada 31 Agustus 2026?", lookup=facts_body(fact("9125.00")))
    assert result.status == "COMPLETED" and result.evidence_label == "FACT"
    assert result.execution.number_provenance.model_dump() == {"checked": 1, "unsupported": []}


def test_a_number_without_a_source_is_rejected_once_then_repaired() -> None:
    result, scripted = run([lookup_call(), final_response(answer("Close BBCA 9.140.")),
                            final_response(answer("Close BBCA 9.125."))],
                           "Berapa close BBCA kemarin?", lookup=facts_body(fact(9125)))
    assert "9.140" in rejection_text(scripted) and scripted.payloads[-1].get("tools")
    assert result.response.response_type == "ANSWER" and result.evidence_label == "FACT"


def test_a_correlation_calculated_in_the_head_is_refused() -> None:
    head = answer("Korelasi return harian BBCA dan BBRI adalah 0,42.")
    result, scripted = run([lookup_call(), final_response(head), final_response(head)],
                           "Berapa korelasi return harian BBCA dan BBRI bulan ini?",
                           lookup=facts_body(fact(9125), fact(4120, entity="BBRI")))
    assert "CORRELATION" in rejection_text(scripted) and "run_python_analysis" in rejection_text(scripted)
    assert result.status == "LIMITED" and result.response.response_type == "LIMITATION"
    assert result.execution.validation_gate == "FORCED_LIMITATION" and result.evidence_label == "NOT_VALIDATED"


def test_unsupported_numbers_force_a_limitation_after_one_rejection() -> None:
    bad = answer("Close BBCA 9.140 dan BBRI 4.200.")
    result, scripted = run([lookup_call(), final_response(bad), final_response(bad)], "Close BBCA dan BBRI kemarin?",
                           lookup=facts_body(fact(9125)))
    assert "9.140" in rejection_text(scripted) and "4.200" in rejection_text(scripted)
    assert result.response.response_type == "LIMITATION" and result.response.answer.startswith("Some figures")
    assert result.execution.number_provenance.unsupported == ["9.140", "4.200"]
    assert any("9.140" in line for line in result.response.limitations)
    assert result.evidence_label == "NOT_VALIDATED"


def test_metrics_of_a_passed_analysis_are_a_source_and_labelled_by_level() -> None:
    passed = completed(outputs=[{"type": "METRICS", "name": "metrics", "values": {"correlation": -0.03095364981}}])
    script = [tool_call_response("create_analysis_spec", json.dumps(spec_args()), call_id="c1"),
              tool_call_response("run_python_analysis", json.dumps(run_args()), call_id="c2"),
              final_response(answer("Korelasi ≈ −0,031 (20 hari)."))]
    result, _ = run(script, "Hitung korelasi return BBCA BBRI", sandbox={
        ("POST", "/v1/specs"): (200, approved()), ("POST", "/v1/analyses"): (200, passed)})
    assert result.response.response_type == "ANSWER" and result.evidence_label == "CALCULATION_VERIFIED"
    scope = completed(validation_level="SCOPE_VERIFIED",
                      outputs=[{"type": "METRICS", "name": "m", "values": {"x": 1.2345}}])
    result, _ = run([tool_call_response("run_python_analysis", json.dumps(run_args())),
                     final_response(answer("Nilai 1,23."))], "Hitung z-score BBCA", sandbox={
        ("POST", "/v1/analyses"): (200, scope)})
    assert result.evidence_label == "SCOPE_VERIFIED"
    unverified = completed(validation_status="UNVERIFIED", validation_level="EXECUTION_ONLY",
                           outputs=[{"type": "TABLE", "name": "screen", "row_count": 1,
                                     "preview_rows": [["T001", "2026-08-31", 6.0568]]}])
    result, _ = run([tool_call_response("run_python_analysis", json.dumps(run_args())),
                     final_response(answer("T001: RSI 6,06."))], "Screen RSI < 30", sandbox={
        ("POST", "/v1/analyses"): (200, unverified)})
    assert result.response.response_type == "ANSWER" and result.evidence_label == "UNVERIFIED_EXPLORATORY"
    assert any("UNVERIFIED" in line for line in result.response.limitations)


def test_outputs_of_a_failed_analysis_are_not_a_source_even_in_a_limitation() -> None:
    failed = completed(validation_status="FAILED", validation_level="SCOPE_VERIFIED",
                       reason_codes=["CALCULATION_MISMATCH"],
                       outputs=[{"type": "METRICS", "name": "m", "values": {"correlation": -0.0319418606}}])
    quoting = answer("Estimasi eksploratif ≈ −0,032.", kind="LIMITATION")
    result, scripted = run([tool_call_response("run_python_analysis", json.dumps(run_args())),
                            final_response(quoting), final_response(quoting)],
                           "Hitung korelasi return BBCA BBRI", sandbox={("POST", "/v1/analyses"): (200, failed)})
    assert "−0,032" in rejection_text(scripted)
    assert result.response.response_type == "LIMITATION" and result.evidence_label == "NOT_VALIDATED"
    assert result.execution.number_provenance.unsupported == ["−0,032"]


def test_user_spec_and_manifest_numbers_are_context_not_data() -> None:
    result, _ = run([tool_call_response("request_data", json.dumps({
        "purpose": "p", "from_table": PRICE, "columns": [{"table": PRICE, "column": "close"}], "joins": [],
        "filters": [], "group_by": [], "aggregations": [], "order_by": [], "requested_limit": None})),
        final_response(answer("Dataset berisi 148 baris untuk 2 saham, jendela 20 hari.", kind="LIMITATION"))],
        "Siapkan data 20 hari BBCA dan BBRI")
    assert result.execution.number_provenance.unsupported == [] and result.evidence_label is None


def test_preview_rows_are_never_a_source() -> None:
    result, scripted = run([tool_call_response("preview_table_rows", "{}"), final_response(answer("Close BBCA 9.137,5.")),
                            final_response(answer("Close BBCA 9.137,5."))], "Berapa close BBCA kemarin?")
    assert "9.137,5" in rejection_text(scripted)
    assert result.response.response_type == "LIMITATION" and result.evidence_label == "NOT_VALIDATED"


def test_a_plain_average_may_come_from_a_database_aggregate() -> None:
    avg = facts_body(fact(9120.4, kind="AGGREGATE", aggregation="AVG"))
    call = tool_call_response("lookup_fact", json.dumps({
        "purpose": "p", "mode": "AGGREGATE", "table": PRICE, "entities": ["BBCA"], "dates": None,
        "date_range": {"start": "2026-08-24", "end": "2026-08-28"}, "columns": None,
        "aggregations": [{"column": "close", "function": "AVG"}], "per_entity": True}))
    result, _ = run([call, final_response(answer("Rata-rata close BBCA minggu itu 9.120,4."))],
                    "Berapa rata-rata close BBCA minggu lalu?", lookup=avg)
    assert result.response.response_type == "ANSWER" and result.evidence_label == "DATABASE_AGGREGATE"
    # a moving average is a statistic: only an analysis can answer it
    result, scripted = run([call, final_response(answer("MA20 BBCA 9.120,4.")),
                            final_response(answer("MA20 BBCA 9.120,4."))], "Berapa moving average 20 hari BBCA?",
                           lookup=avg)
    assert "SMA" in rejection_text(scripted) and result.evidence_label == "NOT_VALIDATED"


def test_a_mixed_answer_carries_its_weakest_label() -> None:
    passed = completed(outputs=[{"type": "METRICS", "name": "m", "values": {"zscore": 1.8731}}])
    result, _ = run([lookup_call("c1"), tool_call_response("run_python_analysis", json.dumps(run_args()), call_id="c2"),
                     final_response(answer("Close BBCA 9.125; z-score 20 hari 1,87."))],
                    "Close BBCA kemarin dan z-score 20 hari?", lookup=facts_body(fact(9125)),
                    sandbox={("POST", "/v1/analyses"): (200, passed)})
    assert result.response.response_type == "ANSWER" and result.evidence_label == "CALCULATION_VERIFIED"


def test_clarifications_and_answers_without_data_numbers_have_no_label() -> None:
    clarify = {"response_type": "CLARIFICATION", "answer": "", "clarification_question": "Periode berapa lama?",
               "assumptions": [], "limitations": []}
    result, _ = run([final_response(clarify)], "Hitung z-score BBCA")
    assert result.evidence_label is None and result.execution.number_provenance is None
    result, _ = run([final_response(answer("Saya bisa mencari fakta dan menjalankan analisis Python."))],
                    "Apa kemampuanmu?")
    assert result.evidence_label is None and result.execution.number_provenance.checked == 0


def test_the_question_before_a_clarification_still_routes() -> None:
    history = [HistoryMessage(role="user", content="Hitung korelasi BBCA dan BBRI"),
               HistoryMessage(role="assistant", content="Periode berapa lama?")]
    head = answer("Korelasi 3 bulan terakhir 0,42.")
    result, scripted = run([final_response(head), final_response(head)], "3 bulan terakhir", history=history)
    assert "CORRELATION" in rejection_text(scripted) and result.evidence_label == "NOT_VALIDATED"


def test_analysis_evidence_counts_are_context_but_mismatch_examples_are_not() -> None:
    passed = completed(validation_evidence=[
        {"check": "calculation.z20.zscores", "result": "PASS", "checked": 300},
        {"check": "x", "result": "FAIL", "code": "CALCULATION_MISMATCH", "examples": [{"expected": 0.777}]}],
        outputs=[{"type": "METRICS", "name": "m", "values": {"zscore": 1.8731}}])
    result, scripted = run([tool_call_response("run_python_analysis", json.dumps(run_args())),
                            final_response(answer("300 nilai dicek; z 1,87; contoh 0,777.")),
                            final_response(answer("300 nilai dicek; z 1,87."))],
                           "Hitung z-score BBCA", sandbox={("POST", "/v1/analyses"): (200, passed)})
    assert "0,777" in rejection_text(scripted) and "300" not in rejection_text(scripted).split(":")[1]
    assert result.response.response_type == "ANSWER" and result.evidence_label == "CALCULATION_VERIFIED"
    assert ANA in json.dumps(result.model_dump(mode="json"))
