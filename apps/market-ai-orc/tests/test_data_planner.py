"""prepare_data_bundle: the Execution Planner (envelopes, partitions, lineage, statuses) and its contracts with the
SQL Governor's /v1/extract and the sandbox's bundle builder."""
from __future__ import annotations

import copy
import importlib
import importlib.machinery
import importlib.util
import sys
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from app.tools import build_default_registry
from app.tools.data_planner import (ExecutionPlanner, merge_windows, part_key, sha256_json, split_entities,
                                    split_window)
from app.tools.request_data import current_request_id
from test_analysis_tools import sandbox_module

GOVERNOR_ROOT = Path(__file__).resolve().parents[2] / "market-sql-governor"
NEED = "need_" + "a" * 24


def governor_module(name: str):
    """Import a module of apps/market-sql-governor/app (every service names its package 'app')."""
    if "governor_app" not in sys.modules:
        spec = importlib.machinery.ModuleSpec("governor_app", None, is_package=True)
        spec.submodule_search_locations = [str(GOVERNOR_ROOT / "app")]
        sys.modules["governor_app"] = importlib.util.module_from_spec(spec)
    return importlib.import_module(f"governor_app.{name}")


def window(range_id: str, start: str, end: str, extract_from: str, extract_to: str) -> dict[str, str]:
    return {"range_id": range_id, "start": start, "end": end, "extract_from": extract_from, "extract_to": extract_to}


def need(**overrides: Any) -> dict[str, Any]:
    prices = {"data_request_id": "data_request_1_A", "logical_name": "prices", "source_table": "Price_Stock_Indonesia_IDX",
              "entity_column": "ticker", "time_column": "date", "key_columns": ["ticker", "date"],
              "extract_columns": ["ticker", "date", "close"], "scope": {"type": "ALL"}, "scope_sha256": "1" * 64,
              "windows": [window("current_ytd", "2026-01-01", "2026-09-25", "2025-12-19", "2026-09-25"),
                          window("previous_comparable", "2025-01-01", "2025-09-25", "2024-12-19", "2025-09-26")],
              "source_frequency": "1D", "analysis_frequency": "1D", "resample": None,
              "ordering": [{"column": "ticker", "direction": "ASC"}],
              "restrictions": [{"relationship_id": 2, "join_semantics": "CURRENT_STATE", "left_column": "ticker",
                                "right_column": "Ticker", "left_time_column": None, "right_time_column": None,
                                "as_of_direction": None, "effective_from_column": None, "effective_to_column": None,
                                "right_table": "IDX_Stock_Universe",
                                "right_scope": {"type": "PREDICATE", "column": "Industry", "operator": "EQ",
                                                "values": ["Banks"]},
                                "right_scope_sha256": "2" * 64}],
              "restriction_sha256": "3" * 64}
    banks = {"data_request_id": "data_request_1_B", "logical_name": "stock_classification",
             "source_table": "IDX_Stock_Universe", "entity_column": "Ticker", "time_column": None,
             "key_columns": ["Ticker"], "extract_columns": ["Ticker", "Industry"],
             "scope": {"type": "PREDICATE", "column": "Industry", "operator": "EQ", "values": ["Banks"]},
             "scope_sha256": "2" * 64, "windows": [], "source_frequency": "STATIC", "analysis_frequency": "STATIC",
             "resample": None, "ordering": [], "restrictions": [], "restriction_sha256": "4" * 64}
    body = {"need_id": NEED, "request_id": "run-plan-1", "spec_sha256": "5" * 64, "request_group_id": "data_request_1",
            "revision": 1, "catalog_sha256": "6" * 64, "reference_date": "2026-09-25",
            "requests": {"data_request_1_A": prices, "data_request_1_B": banks}}
    body.update(overrides)
    return body


class FakeGovernor:
    """Answers /v1/extract: a scripted status per (data_request_id, window, partition), APPROVED otherwise."""

    def __init__(self, script: dict | None = None) -> None:
        self.script = script or {}
        self.calls: list[dict[str, Any]] = []

    def extract(self, spec, lineage, *, planned_parts=1):
        self.calls.append({"spec": copy.deepcopy(spec), "lineage": copy.deepcopy(lineage), "planned": planned_parts})
        key = (spec["data_request_id"], (spec["window"] or {}).get("from"), (spec["window"] or {}).get("to"),
               (spec["entity_partition"] or {}).get("modulus"), (spec["entity_partition"] or {}).get("remainder"))
        answer = self.script.get(key)
        if answer is not None:
            return {"data_request_id": spec["data_request_id"], **answer}
        return {"status": "APPROVED", "code": "OK", "dataset": {"dataset_id": f"ds_{len(self.calls):024x}"}}


class FakeSandbox:
    def __init__(self, contract: dict | None = None) -> None:
        self.contract = contract if contract is not None else need()
        self.bundles: list[dict[str, Any]] = []

    def get_need(self, need_id):
        return self.contract if need_id == NEED else None

    def build_bundle(self, request_id, need_id, plan):
        self.bundles.append({"request_id": request_id, "need_id": need_id, "plan": copy.deepcopy(plan)})
        return {"status": "READY", "input_bundle_id": "bundle_" + "b" * 24, "coverage_status": "PASS"}


def run(planner: ExecutionPlanner, need_id: str = NEED, request_id: str = "run-plan-1") -> dict[str, Any]:
    token = current_request_id.set(request_id)
    try:
        return planner.prepare(need_id)
    finally:
        current_request_id.reset(token)


def test_windows_merge_only_when_they_overlap_or_touch() -> None:
    separate = merge_windows(need()["requests"]["data_request_1_A"]["windows"])
    assert [e["range_ids"] for e in separate] == [["previous_comparable"], ["current_ytd"]]
    touching = merge_windows([window("a", "2026-01-01", "2026-03-31", "2025-12-01", "2026-03-31"),
                              window("b", "2026-04-01", "2026-06-30", "2026-04-01", "2026-06-30"),
                              window("c", "2026-02-01", "2026-02-28", "2026-01-20", "2026-02-28")])
    assert touching == [{"from": "2025-12-01", "to": "2026-06-30", "range_ids": ["a", "c", "b"]}]


def test_splits_are_exact_and_disjoint() -> None:
    parts = split_window({"from": "2026-01-01", "to": "2026-01-10"}, 3)
    assert parts[0]["from"] == "2026-01-01" and parts[-1]["to"] == "2026-01-10" and len(parts) == 3
    refined = split_entities({"modulus": 2, "remainder": 1}, 3)
    assert refined == [{"modulus": 6, "remainder": 1}, {"modulus": 6, "remainder": 3},
                       {"modulus": 6, "remainder": 5}]
    assert {r for r in range(12) if r % 2 == 1} == {r for p in refined for r in range(12)
                                                   if r % p["modulus"] == p["remainder"]}


def test_the_ytd_need_becomes_three_extractions_with_complete_lineage() -> None:
    governor, sandbox = FakeGovernor(), FakeSandbox()
    result = run(ExecutionPlanner(sandbox, governor))
    assert result["status"] == "READY" and result["plan"]["decisions"] == [
        "COLUMN_PRUNING", "PREDICATE_PUSHDOWN", "SEMI_JOIN_PUSHDOWN"]
    assert len(governor.calls) == 3
    plan = sandbox.bundles[0]["plan"]
    ids = [p["partition_id"] for r in plan["requests"] for p in r["parts"]]
    assert ids == ["data_request_1_A__previous_comparable__part_001", "data_request_1_A__current_ytd__part_001",
                   "data_request_1_B__static__part_001"]
    for call in governor.calls:
        spec, lineage = call["spec"], call["lineage"]
        assert lineage["extraction_sha256"] == sha256_json(spec)
        assert lineage["part_key"] == part_key(spec["window"], spec["entity_partition"])
        assert lineage["plan_id"] == plan["plan_id"] and lineage["need_id"] == NEED
        assert "sql" not in str(spec).lower()
    prices_call = governor.calls[0]["spec"]
    assert prices_call["columns"] == ["ticker", "date", "close"] and prices_call["restrictions"][0]["relationship_id"] == 2
    assert governor.calls[2]["spec"]["window"] is None and governor.calls[2]["lineage"]["envelope"] is None


def test_governor_partitioning_is_followed_and_parts_are_named_in_order() -> None:
    date_split = {("data_request_1_A", "2025-12-19", "2026-09-25", None, None):
                  {"status": "APPROVED_WITH_PARTITIONING", "code": "ROWS_LIMIT",
                   "partitioning": {"kind": "DATE", "parts": 2}}}
    first_half = split_window({"from": "2025-12-19", "to": "2026-09-25"}, 2)[0]
    entity_split = {("data_request_1_A", first_half["from"], first_half["to"], None, None):
                    {"status": "APPROVED_WITH_PARTITIONING", "code": "ROWS_LIMIT",
                     "partitioning": {"kind": "ENTITY", "parts": 2}}}
    governor, sandbox = FakeGovernor({**date_split, **entity_split}), FakeSandbox()
    assert run(ExecutionPlanner(sandbox, governor))["status"] == "READY"
    current = next(r for r in sandbox.bundles[0]["plan"]["requests"] if r["data_request_id"] == "data_request_1_A")
    parts = [p for p in current["parts"] if p["partition_id"].startswith("data_request_1_A__current_ytd")]
    assert [p["partition_id"][-3:] for p in parts] == ["001", "002", "003"]
    assert [p["entity_partition"] for p in parts] == [{"modulus": 2, "remainder": 0}, {"modulus": 2, "remainder": 1},
                                                      None]
    assert max(c["planned"] for c in governor.calls) >= 3
    # the sandbox accepts the plan and its tiling covers the approved windows exactly
    coverage = sandbox_module("coverage")
    windows = [(date(2025, 12, 19), date(2026, 9, 25))]
    assert coverage.tiling(parts, windows) == []


def test_a_governor_refusal_stops_the_plan_and_names_the_request() -> None:
    governor = FakeGovernor({("data_request_1_A", "2024-12-19", "2025-09-26", None, None):
                             {"status": "REJECTED_POLICY", "code": "COLUMN_NOT_ALLOWED", "message": "no",
                              "next_action": "REVISE_DATA_NEED_SPEC"}})
    sandbox = FakeSandbox()
    result = run(ExecutionPlanner(sandbox, governor))
    assert (result["status"], result["data_request_id"], result["governor_status"], result["next_action"]) == (
        "REJECTED", "data_request_1_A", "REJECTED_POLICY", "REVISE_DATA_NEED_SPEC")
    assert sandbox.bundles == [] and "CHANGE_USER_SCOPE" in result["forbidden_actions"]


def test_partitioning_beyond_the_part_limit_is_a_row_limit_refusal() -> None:
    governor = FakeGovernor({("data_request_1_A", "2025-12-19", "2026-09-25", None, None):
                             {"status": "APPROVED_WITH_PARTITIONING", "partitioning": {"kind": "DATE", "parts": 90}}})
    result = run(ExecutionPlanner(FakeSandbox(), governor))
    assert result["status"] == "REJECTED" and result["governor_status"] == "REJECTED_ROW_LIMIT"
    assert result["next_action"] == "REPLAN_OR_REVISE_DATA_NEED_SPEC"


def test_a_need_of_another_request_is_not_found() -> None:
    planner = ExecutionPlanner(FakeSandbox(), FakeGovernor())
    assert run(planner, request_id="run-other")["code"] == "NEED_NOT_FOUND"
    assert run(planner, need_id="need_" + "0" * 24)["code"] == "NEED_NOT_FOUND"


def test_a_merged_envelope_is_one_extraction_of_several_ranges() -> None:
    contract = need()
    contract["requests"]["data_request_1_A"]["windows"] = [
        window("q1", "2026-01-01", "2026-03-31", "2025-12-19", "2026-03-31"),
        window("q2", "2026-04-01", "2026-06-30", "2026-04-01", "2026-06-30")]
    governor, sandbox = FakeGovernor(), FakeSandbox(contract)
    result = run(ExecutionPlanner(sandbox, governor))
    assert "RANGE_MERGE" in result["plan"]["decisions"]
    first = sandbox.bundles[0]["plan"]["requests"][0]
    assert [p["partition_id"] for p in first["parts"]] == ["data_request_1_A__part_001"]
    assert governor.calls[0]["lineage"]["envelope"] == {"from": "2025-12-19", "to": "2026-06-30",
                                                        "range_ids": ["q1", "q2"]}


def test_part_keys_and_splits_equal_the_governor_and_sandbox_implementations() -> None:
    extract = governor_module("extract")
    coverage = sandbox_module("coverage")
    for w, p in (({"from": "2026-01-01", "to": "2026-02-01"}, None), (None, {"modulus": 4, "remainder": 3}),
                 ({"from": "2026-01-01", "to": "2026-01-01"}, {"modulus": 2, "remainder": 0})):
        assert part_key(w, p) == extract.part_key(w, p) == coverage.part_key(w, p)
    ours = split_window({"from": "2025-12-19", "to": "2026-09-25"}, 7)
    theirs = extract.split_window(date(2025, 12, 19), date(2026, 9, 25), 7)
    assert [(w["from"], w["to"]) for w in ours] == [(a.isoformat(), b.isoformat()) for a, b in theirs]


def test_the_bundle_plan_passes_the_sandbox_plan_check() -> None:
    bundles = sandbox_module("bundles")
    sandbox = FakeSandbox()
    run(ExecutionPlanner(sandbox, FakeGovernor()))
    plan = bundles.normalize_plan(sandbox.bundles[0]["plan"], need(), 128)
    assert [r["data_request_id"] for r in plan["requests"]] == ["data_request_1_A", "data_request_1_B"]


def test_the_tool_is_registered_only_with_the_flag_and_both_services() -> None:
    import httpx

    from app.tools.analysis import SandboxClient
    from app.tools.request_data import GovernorClient

    sandbox = SandboxClient("http://sandbox.test", "s" * 40, 10, 0, transport=httpx.MockTransport(
        lambda r: httpx.Response(404)))
    governor = GovernorClient("http://governor.test", "g" * 40, 10, transport=httpx.MockTransport(
        lambda r: httpx.Response(404)))
    on = build_default_registry(sandbox_client=sandbox, governor_client=governor, dataneed_enabled=True).names()
    off = build_default_registry(sandbox_client=sandbox, governor_client=governor).names()
    assert "prepare_data_bundle" in on and "prepare_data_bundle" not in off
    assert "prepare_data_bundle" not in build_default_registry(sandbox_client=sandbox, dataneed_enabled=True).names()
