"""G15 (plan step 2.4, AI_PLANNER_PARALLEL_PARTS): the parts the preflight chose are extracted a few at a time.

Live (ma-integrity-20261001a, m4a): 29 parts of one need were estimated and extracted one after the other (117.6 s of
extraction). With parallel_parts > 1 the chosen parts go to the Governor in waves; the answers are taken in part order,
so the bundle, its part names and every stop are the same as one at a time.
"""
from __future__ import annotations

import copy
import threading
import time
from typing import Any

import pytest

from app.config import ConfigError, Settings
from app.tools.data_planner import ExecutionPlanner
from app.tools.request_data import current_request_id
from conftest import BASE_ENV
from test_bundle_limits import RowGovernor, limits, one_window
from test_data_planner import FakeSandbox, run


class SlowGovernor(RowGovernor):
    """RowGovernor whose extractions take a moment, recording how many run at once and the request id each saw."""

    def __init__(self, fail_window: str | None = None, **kw: Any) -> None:
        super().__init__(**kw)
        self.lock = threading.Lock()
        self.active = 0
        self.peak = 0
        self.seen: set[str | None] = set()
        self.fail_window = fail_window

    def extract(self, spec, lineage, *, planned_parts=1, estimate_only=False, count_cap=None):
        if estimate_only:
            return super().extract(spec, lineage, planned_parts=planned_parts, estimate_only=True, count_cap=count_cap)
        with self.lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
            self.seen.add(current_request_id.get())
        try:
            time.sleep(0.05)
            if self.fail_window and spec["window"] and spec["window"]["from"] == self.fail_window:
                with self.lock:
                    self.calls.append({"spec": copy.deepcopy(spec), "estimate_only": False, "count_cap": None})
                return {"status": "REJECTED_TIMEOUT_RISK", "code": "TIME_LIMIT", "message": "too slow"}
            return super().extract(spec, lineage, planned_parts=planned_parts)
        finally:
            with self.lock:
                self.active -= 1


def bundle_parts(sandbox: FakeSandbox) -> list[tuple[str, Any]]:
    [bundle] = sandbox.bundles
    return [(p["partition_id"], p["window"]) for r in bundle["plan"]["requests"] for p in r["parts"]]


def test_parts_are_extracted_in_waves_with_the_same_bundle() -> None:
    # 281 days: the scan needs 3 date parts, plus the static request
    sequential, one_sandbox = SlowGovernor(), FakeSandbox(one_window("2025-12-19", "2026-09-25"))
    assert run(ExecutionPlanner(one_sandbox, sequential, preflight=True))["status"] == "READY"
    parallel, many_sandbox = SlowGovernor(), FakeSandbox(one_window("2025-12-19", "2026-09-25"))
    assert run(ExecutionPlanner(many_sandbox, parallel, preflight=True, parallel_parts=3))["status"] == "READY"
    assert sequential.peak == 1 and parallel.peak == 3
    assert bundle_parts(many_sandbox) == bundle_parts(one_sandbox)  # same parts, names and order
    assert parallel.seen == {"run-plan-1"}  # every worker carried the request id


def test_a_stop_in_a_wave_is_the_same_stop_and_wastes_at_most_the_wave() -> None:
    governor, sandbox = SlowGovernor(fail_window="2025-12-19"), FakeSandbox(one_window("2025-12-19", "2026-09-25"))
    result = run(ExecutionPlanner(sandbox, governor, preflight=True, parallel_parts=2))
    assert result["status"] == "REJECTED" and result["governor_status"] == "REJECTED_TIMEOUT_RISK"
    assert sandbox.bundles == []
    assert len([c for c in governor.calls if not c["estimate_only"]]) == 2  # the failing part and its wave partner


def test_the_bundle_limit_still_stops_at_the_first_part_over_it() -> None:
    governor = SlowGovernor(per_day=500, real_per_day=1000)
    sandbox = FakeSandbox(one_window("2025-12-19", "2026-09-25"))
    result = run(ExecutionPlanner(sandbox, governor, preflight=True, limits=limits(200_000), parallel_parts=3))
    assert result["code"] == "BUNDLE_TOO_LARGE" and result["stage"] == "EXTRACTION"
    assert result["details"]["rows_at_least"] == 281_000 and sandbox.bundles == []


def test_the_setting_is_one_to_four_and_defaults_to_one() -> None:
    assert Settings.from_env(dict(BASE_ENV)).ai_planner_parallel_parts == 1
    assert Settings.from_env({**BASE_ENV, "AI_PLANNER_PARALLEL_PARTS": "3"}).ai_planner_parallel_parts == 3
    for bad in ("0", "5"):
        with pytest.raises(ConfigError, match="AI_PLANNER_PARALLEL_PARTS"):
            Settings.from_env({**BASE_ENV, "AI_PLANNER_PARALLEL_PARTS": bad})
