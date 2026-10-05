"""M26 option B (user decision 2026-10-05, PLAN_2026-10-05.md item 8), sandbox side: when the user named the smallest
effect that matters (smallest_effect_source PLAN), an effect in the expected direction but smaller than it is
PARTIALLY_SUPPORTED with reason BELOW_USER_MINIMUM_EFFECT instead of SUPPORTED. Without a minimum from the user, and
for every other verdict, nothing changes. One rule for both paths: research_stats.summarize (hypothesis plans, the
session and the backend's recomputation) and research_engines.decide (multi-angle research, the session and the
independent validator)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))

import research_engines as E  # noqa: E402
import research_stats as rs  # noqa: E402


def summary(effect: float, *, sd: float = 1.0, unit: str = "PERCENT", **kw) -> dict:
    rng = np.random.default_rng(7)
    dates = pd.bdate_range("2024-01-01", periods=400)
    events = pd.DataFrame({"date": dates, "ret": effect + rng.normal(0, sd, len(dates))})
    base = pd.DataFrame({"date": dates, "ret": rng.normal(0, sd, len(dates))})
    return rs.summarize(rs.aggregate(events, base, "ret", "date"), outcome_unit=unit, **kw)


# ------------------------------------------------------------------------------------ hypothesis plan (summarize)

def test_an_effect_above_the_users_minimum_stays_supported() -> None:
    s = summary(1.0, min_effect=0.5)
    assert s["verdict"] == "SUPPORTED" and s["sample"]["smallest_effect_source"] == "PLAN"


def test_an_effect_below_the_users_minimum_is_partly_supported() -> None:
    s = summary(1.0, min_effect=2.0)
    assert (s["verdict"], s["verdict_reason"]) == ("PARTIALLY_SUPPORTED", rs.BELOW_USER_MINIMUM)
    assert s["angle_a"]["ci_low"] > 0 and s["angle_a"]["difference"] < 2.0  # in the expected direction, below it


def test_without_a_minimum_from_the_user_the_verdict_is_unchanged() -> None:
    s = summary(0.3)  # the trading-cost default is no user's minimum
    assert s["sample"]["smallest_effect_source"] == "ROUND_TRIP_TRADING_COST" and s["verdict"] == "SUPPORTED"


@pytest.mark.parametrize("effect,direction,minimum,verdict", [
    (-1.0, "LOWER", 0.5, "SUPPORTED"), (-1.0, "LOWER", 2.0, "PARTIALLY_SUPPORTED"),
    (-1.0, "DIFFERENT", 0.5, "SUPPORTED"), (-1.0, "DIFFERENT", 2.0, "PARTIALLY_SUPPORTED"),
    (-1.0, "HIGHER", 2.0, "NOT_SUPPORTED"),  # the opposite direction is not touched
])
def test_the_minimum_is_compared_in_the_expected_direction(effect, direction, minimum, verdict) -> None:
    assert summary(effect, expected_direction=direction, min_effect=minimum)["verdict"] == verdict


def test_the_same_data_in_decimal_gives_the_same_judgement() -> None:
    """P26: the orchestrator converts the user's minimum to the outcome unit; the comparison is then unit free."""
    percent = summary(1.0, min_effect=2.0)
    decimal = summary(0.01, sd=0.01, unit="DECIMAL", min_effect=0.02)
    assert percent["verdict"] == decimal["verdict"] == "PARTIALLY_SUPPORTED"


def test_the_verdict_list_names_the_new_verdict() -> None:
    assert "PARTIALLY_SUPPORTED" in rs.VERDICTS


# ------------------------------------------------------------------------------------ multi-angle (decide)

def result(estimate: float, ci: tuple[float, float], *, delta: float = 1.0, source: str = "PLAN",
           kind: str = "MEAN_DIFFERENCE") -> dict:
    candidate = {"candidate": "c1", "estimate": estimate, "ci": list(ci), "ci_adjusted": list(ci)}
    return {"estimate_kind": kind, "primary": candidate, "primary_is_predeclared": True, "candidates": [candidate],
            "secondary": {}, "sample": {"flag": "ADEQUATE", "effective": 200, "smallest_effect_of_interest": delta,
                                        "smallest_effect_source": source}}


def status(res: dict, direction: str = "HIGHER") -> tuple[str, str]:
    decision = E.decide(res, expected_direction=direction, validation_level="STATISTICS_VERIFIED")
    return decision["status"], decision["reason"]


def test_an_angle_below_the_users_minimum_is_partly_supported() -> None:
    assert status(result(0.8, (0.3, 1.3), delta=1.0)) == ("PARTIALLY_SUPPORTED", E.BELOW_USER_MINIMUM)
    assert status(result(0.8, (0.3, 1.3), delta=0.5)) == ("SUPPORTED", "EFFECT_IN_EXPECTED_DIRECTION")
    assert status(result(-0.8, (-1.3, -0.3), delta=1.0), "LOWER") == ("PARTIALLY_SUPPORTED", E.BELOW_USER_MINIMUM)
    assert status(result(-0.8, (-1.3, -0.3), delta=1.0), "DIFFERENT") == ("PARTIALLY_SUPPORTED",
                                                                        E.BELOW_USER_MINIMUM)
    assert status(result(0.8, (0.3, 1.3), delta=1.0, kind="SPREAD"))[0] == "PARTIALLY_SUPPORTED"


def test_an_angle_without_a_user_minimum_or_on_another_scale_keeps_its_status() -> None:
    assert status(result(0.8, (0.3, 1.3), source="ROUND_TRIP_TRADING_COST"))[0] == "SUPPORTED"
    # the user's minimum is in the outcome's unit: a rate difference or a correlation is not on that scale
    assert status(result(0.3, (0.1, 0.5), kind="CORRELATION"))[0] == "SUPPORTED"
    assert status(result(0.1, (0.05, 0.15), kind="RATE_DIFFERENCE"))[0] == "SUPPORTED"
    # a result against the hypothesis is not touched
    assert status(result(-0.8, (-1.3, -0.3)))[0] == "INSUFFICIENT_EVIDENCE"


def test_the_independent_validator_decides_with_the_same_rule() -> None:
    from app import research_validation

    validator = research_validation.engines()
    assert validator.decide.__code__.co_code == E.decide.__code__.co_code
    assert validator.below_user_minimum(result(0.8, (0.3, 1.3)), "HIGHER") is True
