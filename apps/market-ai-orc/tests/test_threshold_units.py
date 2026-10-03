"""P26 (golden g6 2026-10-02): a research threshold carries its unit and reaches the engine in the outcome's unit.

The plan of g6 wrote the user's "one point" as min_effect 0.01 with outcome_unit DECIMAL and the "+3%" success rule
as 3.0, while the data were percent; the recommended sample came out 14,868,205 instead of about 1,487."""
from __future__ import annotations

import copy

import pytest
from pydantic import ValidationError

from app.research_plan import match_governance, parse_plan
from app.research_plan_v2 import ResearchAngle
from app.units import UnitError, convert, in_outcome_unit
from test_research_findings import FINDINGS_VALUES, findings_plan


def test_conversion_between_return_units() -> None:
    assert convert(0.03, "DECIMAL", "PERCENT") == pytest.approx(3.0)
    assert convert(3, "PERCENT", "BASIS_POINT") == pytest.approx(300.0)
    assert convert(300, "BASIS_POINT", "DECIMAL") == pytest.approx(0.03)
    with pytest.raises(UnitError):
        convert(3, "PERCENT", "OTHER")


def test_unit_absent_means_the_outcome_unit_unless_implausible() -> None:
    assert in_outcome_unit(0.01, None, "DECIMAL", "min_effect") == 0.01   # plans written before P26
    assert in_outcome_unit(0.5, None, "PERCENT", "min_effect") == 0.5
    assert in_outcome_unit(0.0, None, "PERCENT", "success_rule.value") == 0.0  # "above zero" is not ambiguous
    with pytest.raises(UnitError, match="300 percent"):
        in_outcome_unit(3.0, None, "DECIMAL", "success_rule.value")  # the g6 rule: 3 in DECIMAL is +300 %
    with pytest.raises(UnitError, match="State its unit"):
        in_outcome_unit(0.03, None, "PERCENT", "min_effect")  # a fraction written into a percent outcome
    assert in_outcome_unit(3.0, "DECIMAL", "DECIMAL", "success_rule.value") == 3.0  # an explicit unit is honoured
    with pytest.raises(UnitError, match="not a return"):
        in_outcome_unit(2.0, "PERCENT", "OTHER", "min_effect")


def _plan(**experiment) -> dict:
    plan = findings_plan()
    plan["experiments"][0].update(experiment)
    return plan


def _governance(plan_experiment: dict, **values) -> dict:
    keys = ("hypothesis_id", "hypothesis", "objective", "condition", "outcome", "baseline", "candidate_count",
            "pairwise_comparisons", "multiple_testing_policy")
    return {**{k: plan_experiment[k] for k in keys}, "holdout": None, "minimum_sample": None,
            **{k: plan_experiment[k] for k in FINDINGS_VALUES}, **values}


def test_the_g6_plan_reaches_the_engine_in_the_outcome_unit() -> None:
    """The g6 plan, written with units: outcome DECIMAL, one percentage point, at least three percent."""
    raw = _plan(outcome_unit="DECIMAL", outcome_horizon_periods=10, min_effect=1.0, min_effect_unit="PERCENT",
                success_rule={"operator": ">=", "value": 3.0, "unit": "PERCENT"})
    plan = parse_plan(raw)
    experiment = raw["experiments"][0]
    # the model copies the plan's numbers (the tool's success_rule has no unit field)
    governance = _governance(experiment, success_rule={"operator": ">=", "value": 3.0})
    assert match_governance(governance, plan) is None
    assert governance["min_effect"] == pytest.approx(0.01)
    assert governance["success_rule"] == {"operator": ">=", "value": pytest.approx(0.03)}
    # already converted numbers are accepted too, and stay as they are
    converted = _governance(experiment, min_effect=0.01, success_rule={"operator": ">=", "value": 0.03})
    assert match_governance(converted, plan) is None and converted["min_effect"] == pytest.approx(0.01)
    # another number is still a mismatch
    other = _governance(experiment, min_effect=0.02, success_rule={"operator": ">=", "value": 3.0})
    rejection = match_governance(other, plan)
    assert rejection is not None and [i["field_path"] for i in rejection["error"]["issues"]] == [
        "research_governance.min_effect"]


def test_the_g6_plan_without_units_is_refused_with_its_numbers() -> None:
    raw = _plan(outcome_unit="DECIMAL", min_effect=0.01, success_rule={"operator": ">=", "value": 3.0})
    with pytest.raises(ValidationError, match="success_rule.value 3 has no unit"):
        parse_plan(raw)


def test_basis_points_into_a_percent_outcome() -> None:
    """Another case than g6: "at least 50 bps" for a percent outcome."""
    raw = _plan(min_effect=50.0, min_effect_unit="BASIS_POINT")
    plan = parse_plan(raw)
    governance = _governance(raw["experiments"][0])
    assert match_governance(governance, plan) is None and governance["min_effect"] == pytest.approx(0.5)


def test_a_unit_on_a_non_return_outcome_is_refused() -> None:
    with pytest.raises(ValidationError, match="not a return"):
        parse_plan(_plan(outcome_unit="OTHER", min_effect=2.0, min_effect_unit="PERCENT"))


def test_a_plan_before_p26_is_unchanged() -> None:
    raw = _plan(min_effect=0.5, success_rule={"operator": ">", "value": 0.0})
    plan = parse_plan(raw)
    governance = _governance(raw["experiments"][0], success_rule={"operator": ">", "value": 0.0})
    assert match_governance(governance, plan) is None
    assert governance["min_effect"] == 0.5 and governance["success_rule"] == {"operator": ">", "value": 0.0}


def test_a_v2_angle_min_effect_is_converted() -> None:
    from test_multi_angle import angles  # noqa: PLC0415 - valid angles of the v2 tests

    angle = copy.deepcopy(angles()[0])
    angle.update(outcome_unit="DECIMAL", min_effect=2.0, min_effect_unit="PERCENT")
    assert ResearchAngle.model_validate(angle).min_effect_in_outcome_unit() == pytest.approx(0.02)
    angle.update(min_effect=2.0, min_effect_unit=None)
    with pytest.raises(ValidationError, match="min_effect 2 has no unit"):
        ResearchAngle.model_validate(angle)
