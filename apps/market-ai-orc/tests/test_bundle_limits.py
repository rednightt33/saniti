"""G14: the Execution Planner checks a bundle's size before it extracts it.

Live (ma-integrity-20261001a, m4a): the analysis path extracted 3,191,458 rows in 30 parts over 3 min 42 s and the
sandbox then refused the bundle (BUNDLE_TOO_LARGE, limit 2,000,000), although the preflight had already counted
2,837,101 rows. The planner now receives the sandbox's bundle limits, keeps a running total of the estimated rows and
stops before the first extraction; during extraction it adds each part's real rows and stops at the first part over
the limit (a part whose count timed out); check_data_feasibility compares the total of all requests with the limit.
"""
from __future__ import annotations

import copy
from datetime import date
from typing import Any

from app.main import _bundle_limits
from app.tools.analysis import current_run_context, run_context
from app.tools.data_planner import ExecutionPlanner, check_feasibility
from app.tools.request_data import current_request_id
from test_data_planner import FakeSandbox, need, run, window
from test_plan_feasibility import NOW


def days(spec: dict[str, Any]) -> int:
    w = spec["window"]
    return 1 if w is None else (date.fromisoformat(w["to"]) - date.fromisoformat(w["from"])).days + 1


class RowGovernor:
    """/v1/extract where every day of a window holds `per_day` rows; windows over 120 days need date parts (scan)."""

    def __init__(self, per_day: int = 1000, real_per_day: int | None = None) -> None:
        self.per_day = per_day
        self.real_per_day = per_day if real_per_day is None else real_per_day
        self.calls: list[dict[str, Any]] = []

    def extract(self, spec, lineage, *, planned_parts=1, estimate_only=False, count_cap=None):
        self.calls.append({"spec": copy.deepcopy(spec), "estimate_only": estimate_only, "count_cap": count_cap})
        n = days(spec)
        if spec["window"] is not None and n > 120:
            return {"status": "APPROVED_WITH_PARTITIONING", "code": "SCAN_LIMIT",
                    "partitioning": {"kind": "DATE", "parts": -(-n // 100)}}
        if estimate_only:
            rows = self.per_day * n
            if count_cap is not None and rows >= count_cap:  # G15: the Governor's count stops at the cap
                return {"status": "WITHIN_LIMITS", "estimates": {"result_rows": count_cap, "row_basis": "AT_LEAST"}}
            return {"status": "WITHIN_LIMITS", "estimates": {"result_rows": rows, "row_basis": "COUNTED"}}
        return {"status": "APPROVED", "code": "OK",
                "dataset": {"dataset_id": f"ds_{len(self.calls):024x}", "row_count": self.real_per_day * n}}


def one_window(start: str, end: str) -> dict[str, Any]:
    contract = need()
    contract["requests"]["data_request_1_A"]["windows"] = [window("r", start, end, start, end)]
    return contract


def extractions(governor: RowGovernor) -> list[dict[str, Any]]:
    return [c for c in governor.calls if not c["estimate_only"]]


def limits(rows: int) -> dict[str, int]:
    return {"bundle_max_rows": rows, "bundle_max_bytes": 1 << 28, "bundle_max_parts": 128}


def test_a_plan_over_the_bundle_limit_stops_before_any_extraction() -> None:
    governor, sandbox = RowGovernor(), FakeSandbox(one_window("2026-01-01", "2026-03-31"))  # 90 days, 90,000 rows
    result = run(ExecutionPlanner(sandbox, governor, preflight=True, limits=limits(50_000)))
    assert result["status"] == "REJECTED" and result["code"] == "BUNDLE_TOO_LARGE"
    assert result["stage"] == "PREFLIGHT" and result["next_action"] == "REVISE_DATA_NEED_SPEC"
    assert result["details"]["limit_rows"] == 50_000 and result["details"]["rows_at_least"] == 50_001
    assert result["details"]["rows_by_request"] == {"data_request_1_A": 50_001}  # G15: counted up to the cap only
    assert result["details"]["row_basis"] == ["AT_LEAST"] and "counted" in result["message"]
    assert extractions(governor) == [] and sandbox.bundles == []  # nothing read, no bundle asked for


def test_each_estimate_counts_no_further_than_the_bundle_can_still_hold() -> None:
    # G15: the count of a part stops one row past the rows the bundle has left (row_basis AT_LEAST)
    governor, sandbox = RowGovernor(), FakeSandbox(one_window("2026-01-01", "2026-03-31"))  # 90,000 rows
    result = run(ExecutionPlanner(sandbox, governor, preflight=True, limits=limits(50_000)))
    assert result["code"] == "BUNDLE_TOO_LARGE" and governor.calls[0]["count_cap"] == 50_001
    assert result["details"]["rows_at_least"] == 50_001 and result["details"]["row_basis"] == ["AT_LEAST"]
    assert "(counted)" in result["message"] and extractions(governor) == []
    # the second request is capped by what the first one left; without known limits nothing is capped
    governor = RowGovernor()
    assert run(ExecutionPlanner(FakeSandbox(one_window("2026-01-01", "2026-03-31")), governor, preflight=True,
                                limits=limits(200_000)))["status"] == "READY"
    caps = [c["count_cap"] for c in governor.calls if c["estimate_only"]]
    assert caps[0] == 200_001 and caps[1] == 200_001 - 90_000
    governor = RowGovernor()
    run(ExecutionPlanner(FakeSandbox(one_window("2026-01-01", "2026-03-31")), governor, preflight=True))
    assert all(c["count_cap"] is None for c in governor.calls)


def test_the_remaining_parts_are_not_estimated_once_the_total_is_over() -> None:
    # 281 days: the scan needs 3 date parts of about 94 days; the second part already passes 100,000 rows
    governor, sandbox = RowGovernor(), FakeSandbox(one_window("2025-12-19", "2026-09-25"))
    result = run(ExecutionPlanner(sandbox, governor, preflight=True, limits=limits(100_000)))
    assert result["code"] == "BUNDLE_TOO_LARGE" and extractions(governor) == []
    parts = [c for c in governor.calls if days(c["spec"]) < 120]
    assert len(parts) == 2  # the third part was never estimated


def test_a_plan_within_the_limit_is_extracted_as_before() -> None:
    governor, sandbox = RowGovernor(), FakeSandbox(one_window("2026-01-01", "2026-03-31"))
    assert run(ExecutionPlanner(sandbox, governor, preflight=True, limits=limits(200_000)))["status"] == "READY"
    assert len(extractions(governor)) == 2 and len(sandbox.bundles) == 1
    # without known limits the size check stays with the sandbox alone
    assert run(ExecutionPlanner(FakeSandbox(one_window("2026-01-01", "2026-03-31")), RowGovernor(),
                                preflight=True))["status"] == "READY"


def test_extraction_stops_at_the_first_part_whose_real_rows_pass_the_limit() -> None:
    # the estimate says 500 rows a day (fits), the extracted parts hold 1,000 a day (a count that was uncertain)
    governor, sandbox = RowGovernor(per_day=500, real_per_day=1000), FakeSandbox(one_window("2025-12-19",
                                                                                            "2026-09-25"))
    result = run(ExecutionPlanner(sandbox, governor, preflight=True, limits=limits(200_000)))
    assert result["code"] == "BUNDLE_TOO_LARGE" and result["stage"] == "EXTRACTION"
    assert len(extractions(governor)) == 3 and sandbox.bundles == []  # 94k + 94k fit, the third part does not
    assert result["details"]["rows_at_least"] == 281_000


def test_the_running_total_also_guards_the_path_without_preflight() -> None:
    governor, sandbox = RowGovernor(), FakeSandbox(one_window("2025-12-19", "2026-09-25"))
    result = run(ExecutionPlanner(sandbox, governor, limits=limits(150_000)))
    assert result["code"] == "BUNDLE_TOO_LARGE" and result["stage"] == "EXTRACTION"
    # the whole window is answered with a partitioning; of its 3 parts only 2 were extracted
    assert len([c for c in extractions(governor) if days(c["spec"]) < 120]) == 2 and sandbox.bundles == []


class DraftClient:
    """check_data_feasibility's sandbox side: the draft validates, its view has two requests."""

    def __init__(self, contract: dict[str, Any]) -> None:
        self.contract = contract

    def _request_id(self) -> str:
        return "run-plan-1"

    def check_data_need(self, body):
        return {"status": "APPROVED", "draft_id": "draft_" + "d" * 24, "warnings": []}

    def get_draft(self, draft_id):
        return self.contract


def feasibility(rows_limit: int | None) -> dict[str, Any]:
    contract = one_window("2026-01-01", "2026-03-31")  # A: 90,000 rows; B (static): 1,000 rows
    planner = ExecutionPlanner(None, RowGovernor(), preflight=True,
                               limits=limits(rows_limit) if rows_limit else None)
    tokens = (current_request_id.set("run-plan-1"),
              current_run_context.set(run_context(NOW, "Asia/Jakarta", [], "q")))
    try:
        return check_feasibility(DraftClient(contract), planner, _Args())
    finally:
        current_request_id.reset(tokens[0])
        current_run_context.reset(tokens[1])


class _Args:
    def model_dump(self, mode: str = "json") -> dict[str, Any]:
        return {}


def test_feasibility_compares_the_total_of_all_requests_with_the_bundle_limit() -> None:
    over = feasibility(90_500)  # each request fits on its own, together they do not
    assert over["status"] == "NOT_FEASIBLE" and over["next_action"] == "NARROW_THE_PLAN_OR_REPORT_LIMITATION"
    assert over["bundle"] == {"code": "BUNDLE_TOO_LARGE", "estimated_rows": 91_000, "limit_rows": 90_500,
                              "message": over["bundle"]["message"]}
    fits = feasibility(200_000)
    assert fits["status"] == "FEASIBLE" and "bundle" not in fits  # the shape is unchanged when it fits
    assert feasibility(None)["status"] == "FEASIBLE"


class RuntimeSandbox:
    def __init__(self, runtime: dict[str, Any]) -> None:
        self._runtime = runtime

    def runtime(self) -> dict[str, Any]:
        return self._runtime


def test_the_limits_come_from_the_sandbox_runtime() -> None:
    top = {"limits": {"bundle_max_rows": 5_000_000, "bundle_max_bytes": 268_435_456, "bundle_max_parts": 128}}
    assert _bundle_limits(RuntimeSandbox(top)) == top["limits"]
    older = {"limits": {}, "multi_angle_research": {"limits": {"bundle_max_rows": 2_000_000, "bundle_max_parts": 128}}}
    assert _bundle_limits(RuntimeSandbox(older)) == {"bundle_max_rows": 2_000_000, "bundle_max_parts": 128}
    assert _bundle_limits(RuntimeSandbox({})) is None
