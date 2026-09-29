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
