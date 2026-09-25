"""prepare_analysis_data: the backend compiles an approved Analysis Spec V2 into governed data requests.

The model never writes a data request for the analysis path; the compiler derives every request from the approved
contract, partitions only by date when the Governor asks for smaller extractions, and returns structured refusals.
"""
from __future__ import annotations

import importlib
import importlib.machinery
import importlib.util
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.orchestrator import SYSTEM_PROMPT, AgentOrchestrator, build_system_prompt
from app.schemas import AgentRunRequest
from app.tools import build_default_registry
from app.tools.analysis import SandboxClient
from app.tools.data_compiler import (MAX_PARTS, Bundle, BundleStore, compile_request, sha256_json, split_range)
from app.tools.request_data import GovernorClient, current_request_id
from conftest import ScriptedClient, final_response, make_settings, tool_call_response
from test_analysis_tools import ANA, REFERENCE, SANDBOX_KEY, completed

SPEC = "spec_" + "7" * 24
PRICE, UNIVERSE = "Price_Stock_Indonesia_IDX", "IDX_Stock_Universe"
GOVERNOR_ROOT = Path(__file__).resolve().parents[2] / "market-sql-governor"
BANKS = {"table": UNIVERSE, "column": "Industry", "operator": "EQ", "values": ["Banks"], "data_type": "text"}


def governor_module(name: str):
    if "governor_app" not in sys.modules:
        spec = importlib.machinery.ModuleSpec("governor_app", None, is_package=True)
        spec.submodule_search_locations = [str(GOVERNOR_ROOT / "app")]
        sys.modules["governor_app"] = importlib.util.module_from_spec(spec)
    return importlib.import_module(f"governor_app.{name}")


def contract(request_id: str = "run-1", **overrides: Any) -> dict[str, Any]:
    body = {
        "spec_id": SPEC, "spec_sha256": "a" * 64, "status": "APPROVED_WITH_UNVERIFIED", "request_id": request_id,
        "spec_version": "analysis_spec/v2", "scope_sha256": "b" * 64,
        "catalog": {"catalog_sha256": "c" * 64},
        "spec": {"question": "Lima saham bank dengan kenaikan terbesar dalam satu bulan"},
        "data_plan": {
            "universe": {"input": "universe", "source_table": UNIVERSE, "role": "UNIVERSE", "entity_column": "Ticker",
                         "time_column": None, "columns": ["Ticker", "Industry"], "joins": [], "filters": [BANKS],
                         "date_range": None},
            "prices": {"input": "prices", "source_table": PRICE, "role": "PRIMARY_DATA", "entity_column": "ticker",
                       "time_column": "date", "columns": ["ticker", "date", "close"],
                       "joins": [{"table": UNIVERSE, "relationship_id": 2}], "filters": [BANKS],
                       "date_range": {"column": "date", "from": "2026-08-12", "to": "2026-09-23"}},
        },
    }
    body.update(overrides)
    return body


def ready(dataset_id: str, rows: int = 100) -> dict[str, Any]:
    return {"decision": "DATASET_READY", "next_action": "RUN_ANALYSIS", "reason_code": "OK", "message": "m",
            "request_id": "run-1", "query_id": "qry_1", "dataset": {
                "dataset_id": dataset_id, "row_count": rows, "completeness_status": "COMPLETE",
                "actual_date_range": None, "entities_present_count": 8, "missing_entities": None}}


def refused(reason: str, decision: str = "NEEDS_NARROWING", **details: Any) -> dict[str, Any]:
    return {"decision": decision, "next_action": "REVISE_DATA_REQUEST", "reason_code": reason, "message": reason,
            "request_id": "run-1", "query_id": "qry_1", "details": details}


class Services:
    """Mock sandbox (/v1/specs, /v1/analyses) and Governor (/v1/query) recording every request."""

    def __init__(self, spec_body: dict | None, answer) -> None:
        self.spec_body, self.answer = spec_body, answer
        self.queries: list[dict] = []
        self.analyses: list[dict] = []
        self.counter = 0

    def sandbox(self) -> SandboxClient:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "GET" and request.url.path == f"/v1/specs/{SPEC}":
                return httpx.Response(200 if self.spec_body else 404, json=self.spec_body or {"detail": "x"})
            if request.method == "POST" and request.url.path == "/v1/analyses":
                self.analyses.append(json.loads(request.content))
                return httpx.Response(200, json=completed())
            return httpx.Response(404, json={"detail": "not found"})
        return SandboxClient("http://sandbox.test", SANDBOX_KEY, 5, 20, transport=httpx.MockTransport(handler))

    def governor(self) -> GovernorClient:
        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            assert request.url.path == "/v1/query" and "sql" not in json.dumps(body["spec"]).lower()
            self.queries.append(body)
            self.counter += 1
            return httpx.Response(200, json=self.answer(body, self.counter))
        return GovernorClient("http://governor.test", "g" * 40, 5, transport=httpx.MockTransport(handler))

    def registry(self, bundles: BundleStore | None = None):
        return build_default_registry(None, governor_client=self.governor(), sandbox_client=self.sandbox(),
                                      sandbox_timeout_seconds=5, bundles=bundles)


def prepare(services: Services, request_id: str = "run-1", bundles: BundleStore | None = None):
    registry = services.registry(bundles)
    token = current_request_id.set(request_id)
    try:
        return registry, registry.execute("c1", "prepare_analysis_data", json.dumps({"spec_id": SPEC}))
    finally:
        current_request_id.reset(token)


def test_the_compiled_request_is_the_approved_scope_and_nothing_else() -> None:
    request = compile_request(contract()["data_plan"]["prices"], ("2026-08-12", "2026-09-23"), "p")
    assert request["from_table"] == PRICE and request["joins"] == [{"table": UNIVERSE, "relationship_id": 2}]
    assert {"table": UNIVERSE, "column": "Industry", "operator": "EQ", "value": "Banks"} in request["filters"]
    assert {"table": PRICE, "column": "date", "operator": "BETWEEN", "value": ["2026-08-12", "2026-09-23"]} \
        in request["filters"]
    assert request["group_by"] == request["aggregations"] == request["order_by"] == []
    assert request["requested_limit"] is None
    # typed values follow the catalog type the sandbox recorded for each predicate
    numeric = {**BANKS, "column": "Shares", "operator": "GT", "values": ["1000000"], "data_type": "bigint"}
    typed = compile_request({**contract()["data_plan"]["universe"], "filters": [numeric]}, None, "p")
    assert typed["filters"] == [{"table": UNIVERSE, "column": "Shares", "operator": "GT", "value": 1000000}]


def test_the_request_hash_equals_the_governor_hash_of_the_same_request() -> None:
    request = compile_request(contract()["data_plan"]["prices"], ("2026-08-12", "2026-09-23"), "p")
    governor_spec = governor_module("spec").DataRequestSpec.model_validate(request)
    assert sha256_json(request) == governor_module("catalog_contract").sha256_json(governor_spec.model_dump())


@pytest.mark.parametrize("parts", [1, 2, 3, 7, 16])
def test_partitions_cover_the_range_exactly_without_gaps_or_overlaps(parts: int) -> None:
    windows = split_range("2025-01-02", "2026-07-31", parts)
    assert windows[0][0] == "2025-01-02" and windows[-1][1] == "2026-07-31" and len(windows) <= parts
    for (_, end), (start, _) in zip(windows, windows[1:]):
        assert date.fromisoformat(start) == date.fromisoformat(end) + timedelta(days=1)


def test_prepare_returns_a_bundle_with_lineage_for_every_input() -> None:
    services = Services(contract(), lambda body, n: ready(f"ds_{n:024d}"))
    registry, outcome = prepare(services)
    result = outcome.output["result"]
    assert result["status"] == "READY" and result["input_bundle_id"].startswith("bundle_")
    assert [i["input"] for i in result["inputs"]] == ["prices", "universe"]
    lineages = [q["lineage"] for q in services.queries]
    assert {l["logical_input_name"] for l in lineages} == {"prices", "universe"}
    assert all(l["spec_id"] == SPEC and l["scope_sha256"] == "b" * 64 and l["part_count"] == 1 for l in lineages)
    assert all(l["request_sha256"] == sha256_json(q["spec"]) for l, q in zip(lineages, services.queries))
    assert len({l["data_plan_id"] for l in lineages}) == 1


def test_a_date_range_refusal_is_partitioned_without_changing_the_scope() -> None:
    def answer(body, n):
        window = next(f["value"] for f in body["spec"]["filters"] if f["operator"] == "BETWEEN") \
            if body["lineage"]["logical_input_name"] == "prices" else None
        if window and (date.fromisoformat(window[1]) - date.fromisoformat(window[0])).days + 1 > 20:
            return refused("DATE_RANGE_TOO_LARGE", max_days=20)
        return ready(f"ds_{n:024d}")

    services = Services(contract(), answer)
    _, outcome = prepare(services)
    result = outcome.output["result"]
    assert result["status"] == "READY"
    prices = next(i for i in result["inputs"] if i["input"] == "prices")
    assert prices["parts"] == 3
    parts = [q for q in services.queries if q["lineage"]["logical_input_name"] == "prices"
             and q["lineage"]["part_count"] == 3]
    assert [p["lineage"]["part_index"] for p in parts] == [1, 2, 3]
    for query in parts:  # every partition keeps the approved join and predicate
        assert query["spec"]["joins"] == [{"table": UNIVERSE, "relationship_id": 2}]
        assert {"table": UNIVERSE, "column": "Industry", "operator": "EQ", "value": "Banks"} in query["spec"]["filters"]


def test_a_refusal_the_compiler_cannot_fix_is_structured_and_not_retryable() -> None:
    services = Services(contract(), lambda body, n: refused("FILTER_NOT_ALLOWED", decision="REJECTED"))
    _, outcome = prepare(services)
    result = outcome.output["result"]
    assert result["status"] == "REJECTED" and result["next_action"] == "REVISE_SPEC"
    rejection = result["rejection"]
    assert rejection["stage"] == "SQL_GOVERNOR" and rejection["reason_code"] == "FILTER_NOT_ALLOWED"
    assert rejection["retryable"] is False and "CHANGE_USER_SCOPE" in rejection["forbidden_actions"]
    assert rejection["allowed_actions"] == ["REVISE_SPEC_FROM_CATALOG"]


def test_partitioning_is_bounded() -> None:
    services = Services(contract(), lambda body, n: refused("ESTIMATED_SCAN_TOO_LARGE", estimated_scan_rows=10 ** 8,
                                                            limit=2_000_000)
                        if body["lineage"]["logical_input_name"] == "prices" else ready(f"ds_{n:024d}"))
    _, outcome = prepare(services)
    rejection = outcome.output["result"]["rejection"]
    assert rejection["retryable"] is False and rejection["partitions_tried"] <= MAX_PARTS
    assert rejection["observed"] == {"estimated_scan_rows": 10 ** 8} and rejection["limit"] == {"limit": 2_000_000}
    assert "SAMPLE_WITHOUT_PERMISSION" in rejection["forbidden_actions"]


@pytest.mark.parametrize(("body", "code"), [
    (None, "SPEC_NOT_FOUND"),
    (contract(request_id="another-run"), "SPEC_NOT_FOUND"),
    (contract(status="ANALYSIS_SPEC_MISMATCH"), "SPEC_NOT_FOUND"),
    (contract(spec_version="analysis_spec/v1", data_plan=None), "SPEC_VERSION_NOT_SUPPORTED"),
])
def test_only_an_approved_v2_spec_of_this_request_is_prepared(body, code) -> None:
    services = Services(body, lambda b, n: ready(f"ds_{n:024d}"))
    _, outcome = prepare(services)
    assert outcome.output["result"]["rejection"]["reason_code"] == code and services.queries == []


def test_run_binds_only_the_prepared_bundle_of_the_same_request_and_spec() -> None:
    bundles = BundleStore()
    services = Services(contract(), lambda body, n: ready(f"ds_{n:024d}"))
    registry, outcome = prepare(services, bundles=bundles)
    bundle_id = outcome.output["result"]["input_bundle_id"]
    run = {"spec_id": SPEC, "input_bundle_id": bundle_id, "python_code": "print(1)", "expected_outputs": ["TABLE"]}
    for request_id, spec_id in (("another-run", SPEC), ("run-1", "spec_" + "8" * 24)):
        token = current_request_id.set(request_id)
        try:
            bad = registry.execute("c2", "run_python_analysis", json.dumps({**run, "spec_id": spec_id}))
        finally:
            current_request_id.reset(token)
        assert bad.output["result"]["error"]["code"] == "INPUT_BUNDLE_MISMATCH"
    assert services.analyses == []
    token = current_request_id.set("run-1")
    try:
        registry.execute("c3", "run_python_analysis", json.dumps(run))
    finally:
        current_request_id.reset(token)
    sent = services.analyses[0]["inputs"]
    assert {b["name"]: b["dataset_ids"] for b in sent} == bundles.get(bundle_id).inputs


def test_model_facing_tools_follow_the_flags_and_the_prompt_follows_lookup() -> None:
    services = Services(contract(), lambda b, n: ready("ds_" + "0" * 24))
    names = build_default_registry(None, governor_client=services.governor(), sandbox_client=services.sandbox()).names()
    assert "prepare_analysis_data" in names and "lookup_fact" in names and "request_data" not in names
    off = build_default_registry(None, governor_client=services.governor(), sandbox_client=services.sandbox(),
                                 lookup_fact_enabled=False).names()
    assert "lookup_fact" not in off and "prepare_analysis_data" in off
    rollback = build_default_registry(None, governor_client=services.governor(), request_data_enabled=True).names()
    assert "request_data" in rollback
    assert "lookup_fact" in SYSTEM_PROMPT and "lookup_fact" not in build_system_prompt(False)
    assert build_system_prompt(True) == SYSTEM_PROMPT


def test_repeated_identical_rejections_exhaust_the_repair_budget() -> None:
    invalid = {"status": "INVALID_SPEC", "problems": ["x (UNKNOWN_COLUMN)"], "problem_codes": ["UNKNOWN_COLUMN"],
               "next_action": "REVISE_SPEC"}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=invalid)

    sandbox = SandboxClient("http://sandbox.test", SANDBOX_KEY, 5, 20, transport=httpx.MockTransport(handler))
    registry = build_default_registry(None, sandbox_client=sandbox, sandbox_timeout_seconds=5)
    from test_analysis_tools import spec_args

    calls = [tool_call_response("create_analysis_spec", json.dumps(spec_args(question=f"q{i}")), call_id=f"c{i}")
             for i in range(5)]
    limitation = {"response_type": "LIMITATION", "answer": "Spesifikasi ditolak (UNKNOWN_COLUMN).",
                  "clarification_question": None, "assumptions": [], "limitations": ["UNKNOWN_COLUMN"]}
    scripted = ScriptedClient(calls + [final_response(limitation)])
    AgentOrchestrator(make_settings(), scripted, registry, wall_clock=lambda: REFERENCE).run(
        AgentRunRequest(request_id="repairs", message="hitung sesuatu"))
    outputs = [item for item in scripted.payloads[-1]["input"] if item.get("type") == "function_call_output"]
    codes = [json.loads(o["output"]).get("error", {}).get("code") for o in outputs]
    assert codes[:3] == [None, None, None] and codes[3:] == ["REPAIR_BUDGET_EXHAUSTED"] * 2
