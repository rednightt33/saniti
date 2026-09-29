"""A0/A2 (AI_ENABLE_PREFLIGHT_PARTS, G10): the Execution Planner estimates every part before the first extraction and
takes the fewest date parts that all fit, because the planner cost is not monotonic in the window (A4: a week of broker
x banks cost more than a month). Feasibility uses the same estimate, so FEASIBLE means every part fits, and a part that
fits nowhere stops the plan before any row is read."""
from __future__ import annotations

import copy
from datetime import date
from typing import Any

from app.tools.data_planner import ExecutionPlanner
from test_data_planner import NEED, FakeSandbox, need, run, window


def days(spec: dict[str, Any]) -> int | None:
    w = spec["window"]
    return None if w is None else (date.fromisoformat(w["to"]) - date.fromisoformat(w["from"])).days + 1


class CostGovernor:
    """/v1/extract with a non-monotonic cost: windows of 6 to 16 days hit the expensive plan shape, windows over 120
    days need date parts for the scan; every other window fits. `never` makes every window too expensive."""

    def __init__(self, never: bool = False) -> None:
        self.never = never
        self.calls: list[dict[str, Any]] = []

    def extract(self, spec, lineage, *, planned_parts=1, estimate_only=False):
        self.calls.append({"spec": copy.deepcopy(spec), "estimate_only": estimate_only, "planned": planned_parts})
        n = days(spec)
        if n is not None and (self.never or 6 <= n <= 16):
            return {"status": "APPROVED_WITH_PARTITIONING", "code": "COST_LIMIT",
                    "partitioning": {"kind": "DATE", "parts": 2}, "estimates": {"plan_cost": 700_000.0}}
        if n is not None and n > 120:
            return {"status": "APPROVED_WITH_PARTITIONING", "code": "SCAN_LIMIT",
                    "partitioning": {"kind": "DATE", "parts": -(-n // 100)}}
        if estimate_only:
            return {"status": "WITHIN_LIMITS", "estimates": {"result_rows": 10 * (n or 1)}}
        return {"status": "APPROVED", "code": "OK", "dataset": {"dataset_id": f"ds_{len(self.calls):024x}"}}


def one_window(start: str, end: str) -> dict[str, Any]:
    contract = need()
    contract["requests"]["data_request_1_A"]["windows"] = [window("r", start, end, start, end)]
    return contract


def extractions(governor: CostGovernor) -> list[dict[str, Any]]:
    return [c for c in governor.calls if not c["estimate_only"]]


def test_every_part_is_estimated_before_the_first_extraction() -> None:
    governor, sandbox = CostGovernor(), FakeSandbox(one_window("2025-12-19", "2026-09-25"))  # 281 days
    result = run(ExecutionPlanner(sandbox, governor, preflight=True))
    assert result["status"] == "READY"
    first_extraction = next(i for i, c in enumerate(governor.calls) if not c["estimate_only"])
    assert all(c["estimate_only"] for c in governor.calls[:first_extraction])
    assert all(not c["estimate_only"] for c in governor.calls[first_extraction:])
    prices = [c for c in extractions(governor) if c["spec"]["data_request_id"] == "data_request_1_A"]
    assert len(prices) == 3 and [days(c["spec"]) for c in prices] == [94, 94, 93]  # the scan needs three parts


def test_the_fewest_parts_that_fit_are_taken_not_the_finest() -> None:
    # 30 days: the whole window fits no limit here (scripted below), halves (15 days) and thirds (10 days) and
    # quarters (8 days) hit the expensive shape; six parts of five days fit
    governor = CostGovernor()
    original = governor.extract

    def whole_is_expensive(spec, lineage, *, planned_parts=1, estimate_only=False):
        if days(spec) == 30:
            governor.calls.append({"spec": copy.deepcopy(spec), "estimate_only": estimate_only,
                                   "planned": planned_parts})
            return {"status": "APPROVED_WITH_PARTITIONING", "code": "COST_LIMIT",
                    "partitioning": {"kind": "DATE", "parts": 2}}
        return original(spec, lineage, planned_parts=planned_parts, estimate_only=estimate_only)

    governor.extract = whole_is_expensive
    sandbox = FakeSandbox(one_window("2026-06-01", "2026-06-30"))
    assert run(ExecutionPlanner(sandbox, governor, preflight=True))["status"] == "READY"
    prices = [c for c in extractions(governor) if c["spec"]["data_request_id"] == "data_request_1_A"]
    assert [days(c["spec"]) for c in prices] == [5] * 6
    current = next(r for r in sandbox.bundles[0]["plan"]["requests"] if r["data_request_id"] == "data_request_1_A")
    assert [p["partition_id"] for p in current["parts"]] == [f"data_request_1_A__r__part_{i:03d}" for i in range(1, 7)]


def test_a_part_that_fits_nowhere_stops_the_plan_before_any_row_is_read() -> None:
    governor, sandbox = CostGovernor(never=True), FakeSandbox(one_window("2026-06-01", "2026-06-30"))
    result = run(ExecutionPlanner(sandbox, governor, preflight=True))
    assert result["status"] == "REJECTED" and result["data_request_id"] == "data_request_1_A"
    assert result["governor_status"] == "REJECTED_JOIN_COST"  # the request is restricted by a relationship
    assert result["failing_window"] and result["extracted_requests"] == []
    assert extractions(governor) == [] and sandbox.bundles == []


def test_feasibility_uses_the_same_part_estimate() -> None:
    draft = one_window("2025-12-19", "2026-09-25")
    draft.update(draft_id=NEED)
    fits = ExecutionPlanner(None, CostGovernor(), preflight=True).estimate(draft)
    prices = next(r for r in fits["requests"] if r["data_request_id"] == "data_request_1_A")
    assert fits["feasible"] is True and prices["extraction_parts"] == 3
    assert prices["governor_status"] == "NEEDS_PARTITIONING" and prices["estimated_rows"] == 2810
    refused = ExecutionPlanner(None, CostGovernor(never=True), preflight=True).estimate(one_window("2026-06-01",
                                                                                                   "2026-06-30"))
    prices = next(r for r in refused["requests"] if r["data_request_id"] == "data_request_1_A")
    assert refused["feasible"] is False and prices["governor_status"] == "REJECTED_JOIN_COST"
    assert prices["failing_window"]


def test_without_the_flag_the_planner_extracts_as_before() -> None:
    governor = CostGovernor()
    planner = ExecutionPlanner(FakeSandbox(one_window("2025-12-19", "2026-09-25")), governor)
    assert planner.preflight is False
    assert run(planner)["status"] == "READY" and not any(c["estimate_only"] for c in governor.calls)
