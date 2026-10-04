"""D6 (round 2026-10-03, HIGH_ALERT_PLAN.md Prioritas 2): get_evidence recomputes each claim apart from the model's
code (tier 1 by a Governor summary, tier 2 from a released base table), compares it with the number as written
(the provenance rounding rule), keeps the rows for the user, and the final gate asks once for evidence and states any
mismatch instead of hiding it."""
from __future__ import annotations

import json

import httpx
import pytest

from app.tools import build_default_registry
from app.tools.analysis import SandboxClient
from app.tools.artifacts import RunResults, current_results
from app.tools.evidence import MAX_CLAIMS, compare
from app.tools.request_data import GovernorClient, current_request_id
from test_analysis_tools import SANDBOX_KEY
from test_artifacts import FakeSandbox, FakeStore
from test_conversations import ADMIN_URL, databases  # noqa: F401
from test_export import ExportSandbox
from test_result_store import conversation
from test_session_tools import OUTPUT, SESSION

CRASH_ROWS = [{"date": "2026-01-02", "broker": "RB", "net_value": 5.0}]


class Governor:
    def __init__(self, rows=None, status: str = "OK") -> None:
        self.bodies: list[dict] = []
        # as the live Governor sends them: numeric aggregates as decimal text (GT ma-golden-20261003d)
        self.rows = rows if rows is not None else [{"ticker": "BBCA", "claimed_value": "9450.00", "days_present": 20,
                                                    "first_date": "2026-09-03", "last_date": "2026-10-02"}]
        self.status = status

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.bodies.append(json.loads(request.content))
        if self.status != "OK":
            return httpx.Response(200, json={"status": self.status, "code": "AGGREGATION_NOT_ADDITIVE",
                                             "message": "no SUM rule"})
        return httpx.Response(200, json={"status": "OK", "query_id": "qry_" + "2" * 24, "rows": self.rows,
                                         "row_count": len(self.rows), "period": {"from": "2026-09-03",
                                                                                 "to": "2026-10-02"}})


class Store(FakeStore):
    def __init__(self) -> None:
        super().__init__()
        self.kept: list[dict] = []

    def save_evidence(self, conversation_id, request_id, entry):
        self.kept.append(entry)


def registry(sandbox: FakeSandbox, governor: Governor):
    client = SandboxClient("http://sandbox.test", SANDBOX_KEY, 10, 0, transport=httpx.MockTransport(sandbox.handler))
    gov = GovernorClient("http://governor.test", "g" * 40, 10, transport=httpx.MockTransport(governor.handler))
    return build_default_registry(sandbox_client=client, governor_client=gov, dataneed_enabled=True, evidence=True)


def check(claims: list[dict], sandbox=None, governor=None, store=None):
    record = {"outputs": [{"ref": "out.o3", "output_id": OUTPUT, "session_id": SESSION, "name": "crash_days"}]}
    results = RunResults(conversation_id="conv_1", request_id="req_1", store=store or Store(), record=record,
                         fetch=lambda sid, oid: b"PAR1")
    token, request = current_results.set(results), current_request_id.set("req_1")
    try:
        outcome = registry(sandbox or FakeSandbox(), governor or Governor()).execute("c1", "get_evidence",
                                                                                     {"claims": claims})
    finally:
        current_results.reset(token)
        current_request_id.reset(request)
    return outcome, results


def warehouse(value_text: str = "9.450", **overrides) -> dict:
    return {"text": "Harga penutupan terakhir BBCA", "value_text": value_text, "base_table": None,
            "warehouse": {"source_table": "Price_Stock_Indonesia_IDX", "filters": [{"column": "ticker",
                                                                                    "values": ["BBCA"]}],
                          "group_by": ["ticker"], "measure_column": "close", "function": "LAST",
                          "period": {"trading_days": 20, "start_date": None, "end_date": None},
                          "as_of": "2026-10-02", "row": [{"column": "ticker", "value": "BBCA"}], **overrides}}


def base_table(value_text: str = "116") -> dict:
    return {"text": "RB beli bersih pada hari crash", "value_text": value_text, "warehouse": None,
            "base_table": {"ref": "o3", "output_id": None, "measure": "COUNT", "column": None,
                           "where": [{"column": "net_value", "op": "GT", "value": "0", "values": None}]}}


def test_the_rounding_rule_is_the_provenance_rule() -> None:
    assert compare("33,29%", 0.33291) == ("TERCEK", 0.0)      # a fraction shown as percent, 2 decimals
    assert compare("1,25 miliar", 1_249_600_000.0)[0] == "TERCEK"
    status, difference = compare("116", 115.0)
    assert status == "TIDAK_COCOK" and difference == -1.0
    assert compare("116", None)[0] == "TIDAK_BISA_DICEK"


def test_tier_1_recomputes_a_claim_with_a_governor_summary() -> None:
    governor, store = Governor(), Store()
    outcome, results = check([warehouse()], governor=governor, store=store)
    claim = outcome.output["result"]["claims"][0]
    assert claim["status"] == "TERCEK" and claim["backend_value"] == 9450.0
    summary = governor.bodies[0]["summary"]
    assert summary["measures"] == [{"column": "close", "function": "LAST", "as": "claimed_value"}]
    assert governor.bodies[0]["lineage"]["purpose"] == "EVIDENCE"
    assert results.evidence[0]["rows"] and store.kept[0]["status"] == "TERCEK"
    assert "rows" not in claim  # the model sees the status, the user gets the rows


def test_tier_2_recounts_the_released_base_table() -> None:
    sandbox = FakeSandbox()
    sandbox.answers["/v1/stored-tables/recount"] = (200, {"value": 116, "rows": CRASH_ROWS, "rows_matched": 116,
                                                          "rows_total": 132})
    outcome, results = check([base_table()], sandbox=sandbox)
    claim = outcome.output["result"]["claims"][0]
    assert claim["status"] == "TERCEK" and claim["rows_matched"] == 116
    assert results.evidence[0]["source"]["rows_total"] == 132


def test_a_wrong_number_is_not_matching_with_its_difference() -> None:
    outcome, _ = check([warehouse("9.500")])
    claim = outcome.output["result"]["claims"][0]
    assert claim["status"] == "TIDAK_COCOK" and claim["difference"] == -50.0
    assert outcome.output["result"]["next_action"] == "FIX_THE_NUMBERS_OR_SAY_SO"


def test_a_refused_recipe_and_the_limit_are_stated_never_dropped() -> None:
    refused, _ = check([warehouse()], governor=Governor(status="REJECTED_POLICY"))
    assert refused.output["result"]["claims"][0]["status"] == "TIDAK_BISA_DICEK"
    assert "AGGREGATION_NOT_ADDITIVE" in refused.output["result"]["claims"][0]["reason"]
    many, _ = check([warehouse()] * (MAX_CLAIMS + 2))
    statuses = [c["status"] for c in many.output["result"]["claims"]]
    assert statuses.count("TERCEK") == MAX_CLAIMS and statuses.count("TIDAK_DICEK_BATAS") == 2
    ambiguous, _ = check([warehouse(row=None)], governor=Governor(rows=[
        {"ticker": "BBCA", "claimed_value": 1.0}, {"ticker": "BBRI", "claimed_value": 2.0}]))
    assert ambiguous.output["result"]["claims"][0]["status"] == "TIDAK_BISA_DICEK"


def test_the_gate_asks_once_for_evidence_and_states_a_mismatch() -> None:
    from app.orchestrator import AgentOrchestrator, GateRejection, RunState
    from app.schemas import FinalResponse
    from conftest import ScriptedClient, make_settings

    orchestrator = AgentOrchestrator(make_settings(), ScriptedClient([]), registry(FakeSandbox(), Governor()))
    final = FinalResponse(response_type="ANSWER", answer="RB beli bersih 116 dari 132 hari.",
                          clarification_question=None, assumptions=[], limitations=[])
    state = RunState(request_id="req_gate", started=0.0, input_items=[])
    try:
        orchestrator._evidence_gate(state, final, ["DATA_COVERAGE_VERIFIED"])
        raise AssertionError("the first answer without evidence is sent back")
    except GateRejection:
        pass
    # asked once: the second time the answer goes out with the limitation
    second = orchestrator._evidence_gate(state, final, ["DATA_COVERAGE_VERIFIED"])
    assert any("Bukti klaim tidak dihitung" in line for line in second.limitations)
    mismatch = RunState(request_id="req_gate2", started=0.0, input_items=[])
    mismatch.evidence_items.append({"claim": "RB beli bersih", "value_text": "116", "status": "TIDAK_COCOK",
                                    "backend_value": 115.0})
    mismatch.gate_kinds_rejected.add("EVIDENCE_MISMATCH")  # its one repair was spent
    shown = orchestrator._evidence_gate(mismatch, final, ["DATA_COVERAGE_VERIFIED"])
    assert any("TIDAK COCOK, backend menghitung 115.0" in line for line in shown.limitations)


@pytest.mark.skipif(not ADMIN_URL, reason="ORC_TEST_POSTGRES_URL not set")
def test_evidence_is_kept_with_the_conversation_and_exported(databases) -> None:  # noqa: F811
    """Tier 2's rows kept in AI_conversation_evidence, read back within the conversation only, and exported as a
    file through the sandbox (another case than an output table)."""
    from app.result_store import ResultStore

    admin, login = databases
    mine, other = conversation(admin), conversation(admin)
    store = ResultStore(login)
    entry = {"evidence_id": "evd_" + "3" * 24, "claim": "RB beli bersih", "value_text": "116", "kind": "BASE_TABLE",
             "recipe": {"measure": "COUNT"}, "status": "TERCEK", "backend_value": 116.0, "difference": 0.0,
             "source": {"ref": "out.o3"}, "rows": CRASH_ROWS * 3, "rows_matched": 116}
    store.save_evidence(mine, "req_1", entry)
    assert store.evidence(mine, entry["evidence_id"])["rows_matched"] == 116
    assert store.evidence(other, entry["evidence_id"]) is None
    sandbox = ExportSandbox()
    client = SandboxClient("http://sandbox.test", SANDBOX_KEY, 10, 0, transport=httpx.MockTransport(sandbox.handler))
    exporting = build_default_registry(sandbox_client=client, governor_client=GovernorClient(
        "http://governor.test", "g" * 40, 10, transport=httpx.MockTransport(lambda r: httpx.Response(404))),
        dataneed_enabled=True, export=True)
    token = current_results.set(RunResults(conversation_id=mine, request_id="req_1", store=store, record={}))
    try:
        result = exporting.execute("c1", "export_result", {"evidence_id": entry["evidence_id"], "format": "XLSX"})
    finally:
        current_results.reset(token)
    assert result.output["result"]["status"] == "EXPORTED"
    assert result.output["result"]["file_name"].startswith("bukti_evd_")
    sent = json.loads(sandbox.calls[-1]["body"])
    assert len(sent["rows"]) == 3


def test_distinct_days_are_checked_from_the_summary_coverage() -> None:
    """GT ma-golden-20261003d g7: "BRIS traded on 128 days" was checked with COUNT (broker rows, 179) and judged
    TIDAK_COCOK; DAYS reads the distinct dates of the group instead (any table, its own calendar)."""
    governor = Governor(rows=[{"Symbol": "BRIS", "claimed_value": 179, "days_present": 128}])
    claim = warehouse("128", function="DAYS", measure_column=None, group_by=["Symbol"],
                      row=[{"column": "Symbol", "value": "BRIS"}])
    outcome, _ = check([claim], governor=governor)
    assert outcome.output["result"]["claims"][0]["status"] == "TERCEK"
    assert governor.bodies[0]["summary"]["measures"][0]["function"] == "COUNT"


def test_an_unreadable_backend_value_says_why() -> None:
    outcome, _ = check([warehouse()], governor=Governor(rows=[{"ticker": "BBCA", "claimed_value": None}]))
    claim = outcome.output["result"]["claims"][0]
    assert claim["status"] == "TIDAK_BISA_DICEK" and claim["reason"]

