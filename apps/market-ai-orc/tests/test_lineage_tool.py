"""D3 (round 2026-10-03): get_lineage puts together where an output's numbers came from (output, execution, bundle,
Governor queries, source tables, earlier outputs it loaded) from the data record, the store and the sandbox, behind
AI_ENABLE_LINEAGE_TOOL."""
from __future__ import annotations

import httpx

from app.tools import build_default_registry
from app.tools.analysis import SandboxClient
from app.tools.artifacts import RunResults, current_results
from app.tools.request_data import GovernorClient
from test_analysis_tools import SANDBOX_KEY
from test_artifacts import EXECUTION, FakeSandbox, FakeStore
from test_session_tools import OUTPUT, SESSION, call

BUNDLE = "bundle_" + "f" * 24
EARLIER = "out_" + "9" * 24
BUNDLE_LINEAGE = {"input_bundle_id": BUNDLE, "need_id": "need_1", "status": "READY", "datasets": [
    {"data_request_id": "data_request_1_A", "logical_name": "broker_flow", "source_table": "IDX_Broker_Summary",
     "scope_sha256": "s" * 64, "restricted_by": [1], "rows": 13319,
     "ranges": [{"range_id": "full", "actual_start": "2018-01-02", "actual_end": "2026-08-31", "rows": 13319}],
     "governor": [{"dataset_id": "ds_1", "query_id": "qry_1", "query_hash": "h" * 64, "rows": 13319}]}],
    "relationships": [{"relationship_id": 1, "left_request_id": "data_request_1_A",
                       "right_request_id": "data_request_1_B"}]}


def registry(fake: FakeSandbox, enabled: bool = True):
    sandbox = SandboxClient("http://sandbox.test", SANDBOX_KEY, 10, 0, transport=httpx.MockTransport(fake.handler))
    governor = GovernorClient("http://governor.test", "g" * 40, 10, transport=httpx.MockTransport(
        lambda r: httpx.Response(404)))
    return build_default_registry(sandbox_client=sandbox, governor_client=governor, dataneed_enabled=True,
                                  session_timeout_seconds=200, lineage_tool=enabled)


def record() -> dict:
    return {
        "outputs": [{"ref": "out.o3", "output_id": OUTPUT, "session_id": SESSION, "name": "crash_rank",
                     "label": "DATA_COVERAGE_VERIFIED", "definition": {"notes": "crash days"},
                     "lineage": {"execution_id": EXECUTION, "need_id": "need_1", "bundle_id": BUNDLE,
                                 "data_as_of": "2026-08-31"}}],
        "needs": [{"need_id": "need_1", "requests": [
            {"data_request_id": "data_request_1_A", "source_table": "IDX_Broker_Summary",
             "scope": "Investor Type EQ Foreign",
             "restrictions": ["IDX_Stock_Universe: Industry EQ Banks"]}]}]}


class LoadingStore(FakeStore):
    """The execution loaded an earlier output (load_output), which has its own lineage."""

    def execution(self, conversation_id: str, execution_id: str):
        row = super().execution(conversation_id, execution_id)
        if row is not None:
            row["access"] = {"reads": [{"kind": "range", "data_request_id": "data_request_1_A"},
                                       {"kind": "load_output", "output_id": EARLIER}]}
        return row


def run(fake: FakeSandbox, arguments: dict, store=None):
    token = current_results.set(RunResults(conversation_id="conv_1", request_id="run-session-1",
                                           store=store or FakeStore(), record=record()))
    try:
        return call(registry(fake), "get_lineage", arguments)
    finally:
        current_results.reset(token)


def test_the_tool_exists_only_behind_its_switch() -> None:
    assert "get_lineage" in registry(FakeSandbox()).names()
    assert "get_lineage" not in registry(FakeSandbox(), enabled=False).names()


def test_a_reference_is_traced_to_its_tables_queries_and_code() -> None:
    fake = FakeSandbox({f"/v1/bundles/{BUNDLE}/lineage": (200, BUNDLE_LINEAGE)})
    result = run(fake, {"ref": "o3"}).output["result"]
    assert result["output"]["name"] == "crash_rank" and result["output"]["data_as_of"] == "2026-08-31"
    assert result["execution"]["code_sha256"] == "b" * 64 and result["execution"]["modules"] == ["pandas"]
    dataset = result["bundle"]["datasets"][0]
    assert dataset["scope"] == "Investor Type EQ Foreign"  # the readable row filter of the data record
    assert result["governor"] == [{"dataset_id": "ds_1", "query_id": "qry_1", "query_hash": "h" * 64,
                                   "rows": 13319}]
    assert result["source_tables"] == ["IDX_Broker_Summary", "IDX_Stock_Universe"]
    lineage_call = [c for c in fake.calls if c["path"].endswith("/lineage")][0]
    assert lineage_call["params"]["request_id"] == "run-session-1"


def test_an_earlier_output_the_code_loaded_is_followed() -> None:
    fake = FakeSandbox({f"/v1/bundles/{BUNDLE}/lineage": (200, BUNDLE_LINEAGE)})
    store = LoadingStore()
    store.outputs[EARLIER] = store.outputs[OUTPUT].__class__(**{**store.outputs[OUTPUT].__dict__,
                                                                "output_id": EARLIER, "name": "crash_days",
                                                                "lineage": {"need_id": "need_1"}})
    result = run(fake, {"output_id": OUTPUT}, store).output["result"]
    assert [i["output"]["name"] for i in result["inputs"]] == ["crash_days"]


def test_an_unknown_output_and_a_bundle_the_sandbox_refuses() -> None:
    unknown = run(FakeSandbox(), {"output_id": "out_" + "0" * 24}).output["result"]
    assert unknown["code"] == "OUTPUT_NOT_FOUND" and unknown["next_action"] == "FIX_ARGUMENTS"
    refused = run(FakeSandbox({f"/v1/bundles/{BUNDLE}/lineage": (404, {"error": {"code": "BUNDLE_NOT_FOUND"}})}),
                  {"ref": "o3"}).output["result"]
    assert refused["bundle"]["status"] == "NOT_AVAILABLE" and refused["source_tables"] == []
