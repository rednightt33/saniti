"""G19 (ERRORS_AND_SOLUTIONS.md, golden test ma-golden-20261002c g5 turns 5-8): angles that read the same flow and
price tables for different groups of stocks must not be merged into one request carrying every group's restriction
(BUMN AND NOT BUMN returned 0 rows). Equal requests of equal groups are still merged."""
from __future__ import annotations

import json
from collections import Counter

from app.tools.research_planner import ResearchDataPlanner


def _angle(angle_id: str, universe_scope: dict) -> dict:
    requests = [
        {"data_request_id": "A", "logical_name": "flow", "source_table": "IDX_Broker_Summary", "entity_column": "Symbol",
         "time_column": "Date", "columns": ["Broker", "Net Value"],
         "scope": {"type": "PREDICATE", "column": "Broker", "operator": "EQ", "value": "RB"},
         "time_ranges": [{"range_id": "full", "start": "2018-01-02", "end": "2026-08-31"}],
         "source_frequency": "1D", "analysis_frequency": "1D", "resample": None},
        {"data_request_id": "B", "logical_name": "universe", "source_table": "IDX_Stock_Universe",
         "entity_column": "Ticker", "time_column": None, "columns": ["Industry"], "scope": universe_scope,
         "time_ranges": [], "source_frequency": None, "analysis_frequency": None, "resample": None},
        {"data_request_id": "C", "logical_name": "price", "source_table": "Price_Stock_Indonesia_IDX",
         "entity_column": "ticker", "time_column": "date", "columns": ["close"], "scope": {"type": "ALL"},
         "time_ranges": [{"range_id": "full", "start": "2018-01-02", "end": "2026-08-31"}],
         "source_frequency": "1D", "analysis_frequency": "1D", "resample": None}]
    relationships = [{"relationship_id": 17, "left_request_id": "B", "right_request_id": "A", "join_type": "INNER",
                      "join_semantics": "CURRENT_STATE"},
                     {"relationship_id": 2, "left_request_id": "B", "right_request_id": "C", "join_type": "INNER",
                      "join_semantics": "CURRENT_STATE"}]
    return {"angle_id": angle_id, "data_requests": requests, "relationships": relationships}


def _group(value: str) -> dict:
    return {"type": "PREDICATE", "column": "Industry", "operator": "EQ", "value": value}


def _restrictions_per_request(angles: list[dict]) -> Counter:
    planner = ResearchDataPlanner(None, None)
    merged, mapping, _ = planner._merge(angles)
    spec, _ = planner._group_spec({"question": "q", "subject": {}}, angles, merged, mapping, "g1", "rg",
                                  [a["angle_id"] for a in angles])
    universe = {r["data_request_id"] for r in spec["data_requests"] if r["source_table"] == "IDX_Stock_Universe"}
    return Counter(rel["right_request_id"] for rel in spec["relationships"] if rel["left_request_id"] in universe)


def test_two_groups_get_separate_flow_and_price_requests() -> None:
    bumn = {"type": "PREDICATE", "column": "Company Name", "operator": "IN", "value": ["Bank Mandiri", "Bank BRI"]}
    angles = [_angle("bumn", bumn), _angle("non_bumn", {"type": "NOT", "child": bumn})]
    merged, _, _ = ResearchDataPlanner(None, None)._merge(angles)
    tables = Counter(m["base"]["source_table"] for m in merged)
    assert tables == {"IDX_Broker_Summary": 2, "IDX_Stock_Universe": 2, "Price_Stock_Indonesia_IDX": 2}


def test_no_request_carries_two_group_restrictions_with_four_groups() -> None:
    angles = [_angle(f"g{i}", _group(name)) for i, name in enumerate(["Banks", "Insurance", "Mining", "Retail"])]
    per_request = _restrictions_per_request(angles)
    assert per_request and max(per_request.values()) == 1


def test_angles_on_the_same_group_still_share_their_requests() -> None:
    merged, _, decisions = ResearchDataPlanner(None, None)._merge([_angle("a1", _group("Banks")),
                                                                   _angle("a2", _group("Banks"))])
    assert len(merged) == 3 and len(decisions) == 3


class _CountedEstimator:
    """The Governor's counted estimate: row_basis COUNTED, with chosen tables counted at 0 rows."""

    max_bundle_rows = None

    def __init__(self, empty_tables: set[str]) -> None:
        self.empty = empty_tables

    def estimate(self, draft: dict) -> dict:
        return {"feasible": True, "requests": [
            {"data_request_id": k, "source_table": e["source_table"], "extraction_parts": 1,
             "estimated_rows": 0 if e["source_table"] in self.empty else 1000, "row_basis": "COUNTED",
             "governor_status": "WITHIN_LIMITS"} for k, e in draft["requests"].items()]}


def test_a_research_plan_with_a_request_counted_at_zero_rows_is_sent_back() -> None:
    from test_multi_angle import PlannerSandbox, feasibility_args, run_plan

    planner = ResearchDataPlanner(PlannerSandbox(), _CountedEstimator({"Price_Stock_Indonesia_IDX"}),
                                  limits={"bundle_max_rows": 2_000_000, "bundle_max_parts": 128,
                                          "max_requests_per_spec": 8})
    outcome = run_plan(planner, feasibility_args())
    assert outcome["status"] == "REVISION_REQUIRED", outcome["view"]
    issues = outcome["view"]["issues"]
    assert issues and {i["code"] for i in issues} == {"EMPTY_REQUEST"}
    assert all(i["source_table"] == "Price_Stock_Indonesia_IDX" and i["angle_ids"] for i in issues)
    assert outcome["view"]["next_action"] == "REVISE_ANGLE_REQUIREMENTS"


def test_a_data_feasibility_check_with_a_request_counted_at_zero_rows_is_sent_back() -> None:
    from test_bundle_limits import DraftClient, _Args, one_window

    from app.tools.analysis import current_run_context, run_context
    from app.tools.data_planner import check_feasibility
    from app.tools.request_data import current_request_id
    from test_multi_angle import NOW

    contract = one_window("2026-01-01", "2026-03-31")
    empty_table = next(iter(contract["requests"].values()))["source_table"]
    tokens = (current_request_id.set("run-plan-1"),
              current_run_context.set(run_context(NOW, "Asia/Jakarta", [], "q")))
    try:
        result = check_feasibility(DraftClient(contract), _CountedEstimator({empty_table}), _Args())
    finally:
        current_request_id.reset(tokens[0])
        current_run_context.reset(tokens[1])
    assert result["status"] == "REVISION_REQUIRED" and result["draft_id"] is None
    assert result["issues"][0]["code"] == "EMPTY_REQUEST" and result["issues"][0]["source_table"] == empty_table


def test_a_research_group_whose_bundle_came_back_empty_does_not_run() -> None:
    from test_multi_angle import BundlePlanner, RunSandbox, executor, two_groups

    from app.tools.request_data import current_request_id

    class EmptyBundles(BundlePlanner):
        def prepare(self, need_id: str) -> dict:
            self.prepared.append(need_id)
            return {"status": "READY", "input_bundle_id": "bundle_" + "e" * 24,
                    "datasets": [{"data_request_id": "x_A", "logical_name": "flow", "rows": 0,
                                  "quality_flags": ["EMPTY_DATASET", "EMPTY_RANGE"]}]}

    sandbox = RunSandbox()
    run = executor(sandbox, bundles=EmptyBundles(), dp=two_groups())
    token = current_request_id.set("run_002")
    try:
        started = run.start()
    finally:
        current_request_id.reset(token)
    assert {g["status"] for g in started["groups"]} == {"FAILED"}
    assert {g["reason"] for g in started["groups"]} == {"EMPTY_INPUT"}
    assert all(g["empty_datasets"] == ["flow"] for g in started["groups"])
    assert started["next_action"] == "COMPLETE_RESEARCH_RUN"


def test_audit_keeps_long_tool_arguments_whole():
    """G19 lapis 3: a feasibility check's arguments longer than MAX_STRING are kept whole in the audit trace."""
    from datetime import datetime, timezone

    from app.audit_outbox import MAX_STRING, tool_event

    scopes = [{"op": "IN", "field": "symbol", "values": [f"S{i:03d}" for i in range(40)]} for _ in range(12)]
    arguments = json.dumps({"data_need": {"requests": [{"id": f"r{i}", "scope": s} for i, s in enumerate(scopes)]},
                            "token": "secret-value"})
    assert len(arguments) > MAX_STRING
    event = tool_event(tool="check_data_feasibility", call_id="c1", iteration=1, arguments=arguments,
                       output={"ok": True, "result": {"status": "READY", "notes": "x" * (MAX_STRING + 50)}}, ok=True,
                       error_code=None, duration_ms=5, occurred_at=datetime.now(timezone.utc))
    assert event["arguments"]["data_need"]["requests"][11]["scope"]["values"][-1] == "S039"
    assert event["arguments"]["token"] == "[redacted]"
    # results keep their own (smaller) bound
    assert "more chars" in event["result"]["result"]["notes"]
