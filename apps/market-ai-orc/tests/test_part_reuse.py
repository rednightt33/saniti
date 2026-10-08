"""EXEC-V 2026-10-08 (option D, version (i), one conversation; M113): the Execution Planner keeps each part's identity
(data_sha256) from the Governor's estimate, asks the sandbox which parts an earlier answer of the conversation already
extracted with the same SQL, plans those as reuse_of parts without a Governor extraction, extracts the others, and
tells the model which part was reused (and when it was extracted) or why it was extracted."""
from __future__ import annotations

import copy
from typing import Any

from app.tools.analysis import current_conversation_key
from app.tools.data_planner import REUSE_NOTE, ExecutionPlanner
from app.tools.request_data import current_request_id
from test_data_planner import NEED, need

KEY = "ck_" + "c" * 32


class IdentityGovernor:
    """Every estimate fits and names its data_sha256 (the window decides it here); extractions are counted."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def extract(self, spec, lineage, *, planned_parts=1, estimate_only=False, count_cap=None):
        self.calls.append({"spec": copy.deepcopy(spec), "estimate_only": estimate_only})
        if estimate_only:
            return {"status": "WITHIN_LIMITS", "estimates": {"result_rows": 10},
                    "data_sha256": f"{spec['data_request_id']}:{(spec['window'] or {}).get('from')}".ljust(64, "0")}
        return {"status": "APPROVED", "code": "OK", "dataset": {"dataset_id": f"ds_{len(self.calls):024x}",
                                                                "row_count": 10}}


class ReuseSandbox:
    """Answers the lookup: the previous_comparable part of data_request_1_A was extracted by an earlier answer."""

    def __init__(self, available: bool = True, refuse_build: bool = False) -> None:
        self.part_reuse = available
        self.refuse_build = refuse_build
        self.lookups: list[list[dict[str, Any]]] = []
        self.bundles: list[dict[str, Any]] = []

    def get_need(self, need_id):
        return need() if need_id == NEED else None

    def reuse_bundle(self, request_id, need_id):
        return None

    def lookup_parts(self, request_id, need_id, parts):
        self.lookups.append(copy.deepcopy(parts))
        answers = []
        for part in parts:
            if part["window"] and part["window"]["from"] == "2024-12-19":
                answers.append({"status": "MATCH", "reuse_of": {"bundle_id": "bundle_" + "e" * 24,
                                                                 "partition_id": "data_request_9_A__old__part_001"},
                                "dataset_id": "ds_" + "e" * 24, "rows": 10, "request_id": "r0",
                                "extracted_at": "2026-10-07T17:00:00+00:00"})
            elif part["window"] is None:
                answers.append({"status": "NO_MATCH", "reason": "NO_DATE_RANGE", "message": "static"})
            else:
                answers.append({"status": "NO_MATCH", "reason": "RANGE_INCLUDES_TODAY", "message": "today"})
        return answers

    def build_bundle(self, request_id, need_id, plan):
        self.bundles.append(copy.deepcopy(plan))
        if self.refuse_build and len(self.bundles) == 1:
            return {"status": "REJECTED", "stage": "BUNDLE", "code": "REUSE_NOT_ALLOWED", "message": "expired"}
        return {"status": "READY", "input_bundle_id": "bundle_" + "b" * 24, "coverage_status": "PASS"}


def prepare(planner: ExecutionPlanner, key: str | None = KEY) -> dict[str, Any]:
    tokens = (current_request_id.set("run-plan-1"), current_conversation_key.set(key))
    try:
        return planner.prepare(NEED)
    finally:
        current_request_id.reset(tokens[0])
        current_conversation_key.reset(tokens[1])


def extractions(governor: IdentityGovernor) -> list[dict[str, Any]]:
    return [c for c in governor.calls if not c["estimate_only"]]


def test_a_part_with_the_same_sql_is_reused_and_the_others_are_extracted_with_their_reason() -> None:
    governor, sandbox = IdentityGovernor(), ReuseSandbox()
    result = prepare(ExecutionPlanner(sandbox, governor))  # the preflight runs because reuse needs the identities
    assert result["status"] == "READY"
    [asked] = sandbox.lookups
    assert len(asked) == 3 and all(len(p["data_sha256"]) == 64 for p in asked)
    windows = [(c["spec"]["data_request_id"], (c["spec"]["window"] or {}).get("from")) for c in extractions(governor)]
    assert ("data_request_1_A", "2024-12-19") not in windows and len(windows) == 2  # no Governor call for it
    prices = next(r for r in sandbox.bundles[0]["requests"] if r["data_request_id"] == "data_request_1_A")
    reused = [p for p in prices["parts"] if p.get("reuse_of")]
    assert len(reused) == 1 and reused[0]["dataset_id"] == "ds_" + "e" * 24 and reused[0]["data_sha256"]
    report = result["data_reuse"]
    assert (report["parts_reused"], report["parts_extracted"]) == (1, 2) and report["note"] == REUSE_NOTE
    assert {(p["status"], p.get("reason")) for p in report["parts"]} == {
        ("REUSED", None), ("EXTRACTED", "RANGE_INCLUDES_TODAY"), ("EXTRACTED", "NO_DATE_RANGE")}
    assert next(p for p in report["parts"] if p["status"] == "REUSED")["reused_from"]["extracted_at"]


def test_without_a_conversation_or_the_capability_nothing_is_looked_up() -> None:
    for key, available in ((None, True), (KEY, False)):
        governor, sandbox = IdentityGovernor(), ReuseSandbox(available=available)
        result = prepare(ExecutionPlanner(sandbox, governor), key)
        assert result["status"] == "READY" and sandbox.lookups == [] and "data_reuse" not in result
        assert len(extractions(governor)) == 3


def test_a_reuse_the_sandbox_refuses_at_build_time_falls_back_to_extraction() -> None:
    governor, sandbox = IdentityGovernor(), ReuseSandbox(refuse_build=True)
    result = prepare(ExecutionPlanner(sandbox, governor))
    assert result["status"] == "READY" and len(sandbox.bundles) == 2
    assert not any(p.get("reuse_of") for r in sandbox.bundles[1]["requests"] for p in r["parts"])
    assert len(extractions(governor)) == 2 + 3  # the second plan extracts every part
