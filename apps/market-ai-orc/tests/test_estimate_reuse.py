"""R1 (user 2026-10-20, go "opsi 1"): prepare_data_bundle takes the counted WITHIN_LIMITS estimate of the same SQL from
the feasibility check of the same request (Governor log 2026-10-20: 136 of 139 repeated estimates were draft_ then
need_ of one request); every other answer goes to the Governor as before."""
from __future__ import annotations

import copy
from typing import Any

import pytest

from app.tools import data_planner
from app.tools.data_planner import ESTIMATES, ExecutionPlanner
from app.tools.request_data import current_request_id
from test_data_planner import NEED, FakeSandbox, need, window


class CountingGovernor:
    """/v1/extract whose estimates are counted (row_basis COUNTED) unless told otherwise."""

    def __init__(self, rows: int = 100, basis: str = "COUNTED", status: str = "WITHIN_LIMITS") -> None:
        self.rows, self.basis, self.status = rows, basis, status
        self.calls: list[dict[str, Any]] = []

    def extract(self, spec, lineage, *, planned_parts=1, estimate_only=False, count_cap=None):
        self.calls.append({"spec": copy.deepcopy(spec), "estimate_only": estimate_only, "count_cap": count_cap,
                           "need_id": lineage["need_id"]})
        if estimate_only:
            if self.status != "WITHIN_LIMITS":
                return {"status": self.status, "code": "COST_LIMIT", "partitioning": {"kind": "DATE", "parts": 2}}
            return {"status": "WITHIN_LIMITS", "data_sha256": "d" * 64,
                    "estimates": {"result_rows": self.rows, "row_basis": self.basis}}
        return {"status": "APPROVED", "code": "OK", "dataset": {"dataset_id": f"ds_{len(self.calls):024x}"}}

    def estimates(self, need_prefix: str) -> list[dict[str, Any]]:
        return [c for c in self.calls if c["estimate_only"] and c["need_id"].startswith(need_prefix)]


def one_window() -> dict[str, Any]:
    contract = need()
    contract["requests"] = {"data_request_1_A": contract["requests"]["data_request_1_A"]}
    contract["requests"]["data_request_1_A"]["windows"] = [window("r", "2026-06-01", "2026-06-30", "2026-06-01",
                                                                  "2026-06-30")]
    return contract


@pytest.fixture(autouse=True)
def fresh_cache():
    ESTIMATES._entries.clear()
    ESTIMATES.enabled = True
    yield
    ESTIMATES._entries.clear()
    ESTIMATES.enabled = True


def feasibility_then_prepare(governor: CountingGovernor, request_id: str = "run-r1", prepare_request: str | None = None,
                             max_rows: int | None = None) -> dict[str, Any]:
    contract = one_window()
    contract["request_id"] = prepare_request or request_id
    draft = {**copy.deepcopy(contract), "need_id": "draft_" + "a" * 24}
    limits = {"bundle_max_rows": max_rows} if max_rows else None
    token = current_request_id.set(request_id)
    try:
        ExecutionPlanner(None, governor, preflight=True, limits=limits).estimate(draft)
    finally:
        current_request_id.reset(token)
    token = current_request_id.set(prepare_request or request_id)
    try:
        return ExecutionPlanner(FakeSandbox(contract), governor, preflight=True, limits=limits).prepare(NEED)
    finally:
        current_request_id.reset(token)


def test_prepare_takes_the_counted_feasibility_estimate_of_the_same_request() -> None:
    governor = CountingGovernor()
    assert feasibility_then_prepare(governor)["status"] == "READY"
    assert len(governor.estimates("draft_")) == 1
    assert governor.estimates("need_") == []  # answered from the feasibility check
    assert len([c for c in governor.calls if not c["estimate_only"]]) == 1  # the extraction is still checked


def test_another_request_never_takes_the_estimate() -> None:
    governor = CountingGovernor()
    feasibility_then_prepare(governor, prepare_request="run-r1-other")
    assert len(governor.estimates("need_")) == 1


@pytest.mark.parametrize("basis", ["PLANNER", "AT_LEAST"])
def test_an_uncounted_estimate_goes_to_the_governor_again(basis: str) -> None:
    governor = CountingGovernor(basis=basis)
    feasibility_then_prepare(governor)
    assert len(governor.estimates("need_")) == 1


def test_a_count_at_or_above_the_new_cap_goes_to_the_governor_again() -> None:
    governor = CountingGovernor(rows=100)
    feasibility_then_prepare(governor, max_rows=99)  # the bundle cap counts at most 100 rows: 100 is not below it
    assert len(governor.estimates("need_")) == 1


def test_a_partitioning_answer_is_never_kept() -> None:
    governor = CountingGovernor(status="APPROVED_WITH_PARTITIONING")
    ESTIMATES.put("run-r1", "x" * 64, {"status": "APPROVED_WITH_PARTITIONING",
                                        "estimates": {"result_rows": 1, "row_basis": "COUNTED"}})
    assert ESTIMATES.get("run-r1", "x" * 64, None) is None
    assert governor.calls == []


def test_the_switch_off_sends_every_estimate() -> None:
    ESTIMATES.enabled = False
    governor = CountingGovernor()
    feasibility_then_prepare(governor)
    assert len(governor.estimates("need_")) == 1


def test_a_reuse_is_logged_once_per_prepare(monkeypatch) -> None:
    events = []
    from app import orchestrator

    monkeypatch.setattr(orchestrator, "log_event", lambda name, **fields: events.append((name, fields)))
    feasibility_then_prepare(CountingGovernor())
    assert [(n, f["estimates"]) for n, f in events if n == "planner_estimate_reused"] == [("planner_estimate_reused", 1)]


def test_an_old_entry_expires(monkeypatch) -> None:
    ESTIMATES.put("run-r1", "y" * 64, {"status": "WITHIN_LIMITS", "estimates": {"result_rows": 1,
                                                                                 "row_basis": "COUNTED"}})
    clock = data_planner.time.monotonic() + ESTIMATES.ttl_seconds + 1
    monkeypatch.setattr(data_planner.time, "monotonic", lambda: clock)
    assert ESTIMATES.get("run-r1", "y" * 64, None) is None
