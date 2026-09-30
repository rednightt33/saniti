"""G13 (suite20d e02, 2026-09-30): a question about BBCA read every stock (2,590,834 rows) and its bundle was refused
as too large. check_research_feasibility now refuses a request that reads every entity of its table while the
question names specific entities, unless the angle declares it in broad_scope with a reason."""
from __future__ import annotations

import copy

from test_data_need_tool import node
from test_multi_angle import feasibility_args, planner, run_plan

BBCA_QUESTION = "Apakah net beli asing BBCA mendahului kenaikan harga BBCA?"


def scoped_planner(known=("BBCA",), fail=False):
    planner_, sandbox = planner()
    calls = []

    def checker(table: str, column: str, token: str) -> bool:
        calls.append((table, column, token))
        if fail:
            raise RuntimeError("governor down")
        return token in known

    planner_.entity_checker = checker
    return planner_, calls


def bbca_args(scope=None, broad=None):
    args = feasibility_args()
    args["question"] = BBCA_QUESTION
    for angle in args["angles"]:
        angle["broad_scope"] = None
        for request in angle["data_requests"]:
            request["scope"] = copy.deepcopy(scope or node("ALL"))
    if broad:
        args["angles"][0]["broad_scope"] = broad
    return args


def test_a_question_about_bbca_may_not_read_every_stock() -> None:
    planner_, calls = scoped_planner()
    outcome = run_plan(planner_, bbca_args())
    assert outcome["status"] == "REVISION_REQUIRED"
    issues = outcome["view"]["issues"]
    assert {i["code"] for i in issues} == {"SCOPE_WIDER_THAN_QUESTION"} and len(issues) == 3
    assert "names BBCA" in issues[0]["message"] and "broad_scope" in issues[0]["message"]
    assert ("Price_Stock_Indonesia_IDX", "ticker", "BBCA") in calls
    assert len(calls) == len(set(calls))  # each (table, column, token) is checked once


def test_a_scope_on_the_named_ticker_or_a_declared_broad_scope_passes() -> None:
    planner_, _ = scoped_planner()
    scoped = node("PREDICATE", "ticker", "IN", ["BBCA"])
    assert run_plan(planner_, bbca_args(scope=scoped))["status"] == "FEASIBLE"
    args = bbca_args()
    for angle in args["angles"]:
        angle["broad_scope"] = [{"data_request_id": r["data_request_id"], "reason": "Pembanding seluruh pasar."}
                                for r in angle["data_requests"]]
    outcome = run_plan(planner_, args)
    assert outcome["status"] == "FEASIBLE"
    assert set(outcome["data_plan"]["broad_scope"]) == {a["angle_id"] for a in args["angles"]}


def test_no_named_entity_or_a_failed_check_leaves_the_scope_alone() -> None:
    planner_, _ = scoped_planner(known=())
    assert run_plan(planner_, bbca_args())["status"] == "FEASIBLE"  # BBCA is not an entity of these tables
    planner_, _ = scoped_planner(fail=True)
    assert run_plan(planner_, bbca_args())["status"] == "FEASIBLE"  # the Governor check failed: advisory only
    planner_, calls = scoped_planner()
    args = bbca_args()
    args["question"] = "Apakah saham yang turun tajam cenderung naik sesudahnya? IHSG sebagai pembanding."
    assert run_plan(planner_, args)["status"] == "FEASIBLE" and calls == []  # IHSG is never a stock code
