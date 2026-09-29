"""The session's research view (found live, golden run 2026-09-29): every example call is a valid declaration in the
real expression grammar, and a contract entry passed as request= gets an actionable error."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

from app.sessions import RESEARCH_EXAMPLES, RESEARCH_RULES, research_view

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))
import expression  # noqa: E402
import research_inputs  # noqa: E402
import research_engines  # noqa: E402


def roles_of(text: str) -> dict:
    call = ast.parse(f"f({text})", mode="eval").body
    return {k.arg: ast.literal_eval(k.value) for k in call.keywords}


@pytest.mark.parametrize("method", sorted(research_engines.METHODS))
def test_every_method_has_an_example_that_parses(method: str) -> None:
    helper, text = RESEARCH_EXAMPLES[method]
    roles = roles_of(text)
    declaration = research_inputs.normalize(method, {"request": "g1_A", "range_id": None, "roles": roles})
    for role, value in declaration["roles"].items():
        if isinstance(value, str):
            expression.analyze(value, {"close"})


def test_the_view_carries_one_example_per_angle_and_the_rules() -> None:
    view = research_view({"research_run_id": "rrun_1", "bundle_group_id": "g1", "angles": {
        "a_fall": {"method_id": "conditional_distribution", "method_family": "CONDITIONAL_OUTCOME",
                   "contract": {"datasets": [{"data_request_id": "mar1_g1_A", "logical_name": "prices",
                                              "columns": ["close"], "ranges": [{"range_id": "history"}]}]}}}})
    [entry] = view["angles"]
    assert entry["example"].startswith("saniti.research_conditional('a_fall', request='mar1_g1_A', condition=")
    assert "forward_return" in view["record_each_angle"] and "trailing return" in RESEARCH_RULES


def _view(datasets):
    return research_view({"research_run_id": "rrun_1", "bundle_group_id": "g1", "angles": {
        "a1": {"method_id": "conditional_distribution", "contract": {"datasets": datasets}}}})["angles"][0]["example"]


def test_the_example_takes_the_price_column_from_the_contract() -> None:
    """S15/G12 (suite20, 2026-09-29): the example always named close, even when the angle's first request had none."""
    broker = {"data_request_id": "g1_A", "logical_name": "broker_daily", "columns": ["foreign_net_value"],
              "ranges": []}
    daily = {"data_request_id": "g1_B", "logical_name": "features", "columns": ["close", "volume"], "ranges": []}
    assert "{'forward_return': 'close', 'request': 'g1_B'}" in _view([broker, daily])
    same = _view([daily])
    assert "{'forward_return': 'close'}" in same and "'request':" not in same
    assert "no price column" in _view([broker])


def test_a_price_level_outcome_is_not_a_return() -> None:
    import pandas as pd

    level = pd.DataFrame({"date": ["2026-01-02"] * 3, "outcome": [1400.0, 1772.0, 1500.0], "condition": [True] * 3})
    assert "not a return in PERCENT" in research_inputs.outcome_problem("conditional_distribution", level, "PERCENT")
    returns = level.assign(outcome=[1.2, -0.8, 3.5])
    assert research_inputs.outcome_problem("conditional_distribution", returns, "PERCENT") is None
    assert research_inputs.outcome_problem("conditional_distribution", level, "OTHER") is None
    follower = pd.DataFrame({"date": ["2026-01-02"] * 2, "leader": [1.0, 2.0], "follower": [2.5, 3.1]})
    assert "follower" in research_inputs.outcome_problem("lead_lag", follower, "DECIMAL")
