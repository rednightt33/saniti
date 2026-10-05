"""Research findings v1: both angles, the effective sample, the fixed sample categories, the verdict rules, the
Research Governor without a fixed minimum sample (flag on only), and the backend's recomputation from the released
per-date aggregates with the approved plan's values."""
from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.research_findings import evaluate, parameters
from app.research_governance import GovernancePolicy, check_request, review

RUNTIME = Path(__file__).resolve().parents[1] / "runtime" / "research_stats.py"
_spec = importlib.util.spec_from_file_location("research_stats_under_test", RUNTIME)
rs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rs)


def frames(n_dates: int, effect: float, sd: float = 1.0, per_date: int = 1, seed: int = 7, base_mean: float = 0.0,
           start: str = "2024-01-01", baseline_dates: int | None = None):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start, periods=max(n_dates, baseline_dates or n_dates))
    events = pd.DataFrame({"date": np.repeat(dates[:n_dates], per_date)})
    events["ret"] = base_mean + effect + rng.normal(0, sd, len(events))
    base = pd.DataFrame({"date": np.repeat(dates[:baseline_dates or n_dates], per_date)})
    base["ret"] = base_mean + rng.normal(0, sd, len(base))
    return events, base


def summary(events, base, **kw):
    table = rs.aggregate(events, base, "ret", "date")
    return rs.summarize(table, **kw)


# ------------------------------------------------------------------------------------------ sample and verdict

def test_a_strong_effect_on_many_independent_dates_is_supported() -> None:
    s = summary(*frames(400, effect=1.0, sd=1.0))
    assert s["sample"]["flag"] == "ADEQUATE" and s["verdict"] == "SUPPORTED"
    assert s["angle_a"]["ci_low"] > 0 and s["angle_b"]["difference"] > 0 and not s["angles_disagree"]


def test_an_effect_opposite_to_the_hypothesis_is_not_supported() -> None:
    s = summary(*frames(400, effect=-1.0), expected_direction="HIGHER")
    assert s["verdict"] == "NOT_SUPPORTED" and s["verdict_reason"] == "EFFECT_OPPOSITE_TO_EXPECTED"


def test_no_effect_with_enough_data_is_not_supported_and_a_small_sample_is_inconclusive() -> None:
    adequate = summary(*frames(2000, effect=0.0, sd=0.5))
    assert adequate["sample"]["flag"] == "ADEQUATE"
    assert adequate["sample"]["minimum_detectable_effect"] <= adequate["sample"]["smallest_effect_of_interest"]
    assert adequate["verdict"] == "NOT_SUPPORTED"
    # identical, widely spread outcomes on both sides: no difference, far too few dates for a 0.5-point effect
    dates = pd.bdate_range("2024-01-01", periods=40)
    spread = pd.DataFrame({"date": dates, "ret": np.tile([-8.0, 8.0], 20)})
    under = summary(spread, spread.copy())
    assert under["sample"]["flag"] == "UNDERPOWERED" and under["verdict"] == "INCONCLUSIVE"
    assert under["sample"]["recommended_effective_per_group"] > 40


def test_fewer_than_ten_independent_dates_are_anecdotal_whatever_the_statistics_say() -> None:
    s = summary(*frames(6, effect=5.0, sd=0.1, baseline_dates=300))
    assert s["sample"]["flag"] == "ANECDOTAL" and s["verdict"] == "INCONCLUSIVE"


def test_a_market_wide_day_is_one_observation_and_one_date_is_insufficient() -> None:
    events, base = frames(1, effect=2.0, per_date=100, baseline_dates=300)
    s = summary(events, base)
    assert s["groups"]["CONDITION"]["rows"] == 100 and s["groups"]["CONDITION"]["effective"] == 1
    assert s["sample"]["flag"] == "INSUFFICIENT" and s["verdict"] == "NOT_EVALUATED"


def test_overlapping_outcomes_count_only_dates_a_horizon_apart() -> None:
    events, base = frames(20, effect=0.5)
    assert summary(events, base, horizon_periods=1)["groups"]["CONDITION"]["effective"] == 20
    assert summary(events, base, horizon_periods=5)["groups"]["CONDITION"]["effective"] == 4


def test_a_multiple_testing_policy_widens_the_interval() -> None:
    events, base = frames(200, effect=0.3)
    plain = summary(events, base)
    corrected = summary(events, base, comparisons=10, multiple_testing_policy="BONFERRONI")
    assert corrected["parameters"]["alpha_adjusted"] == pytest.approx(0.005)
    assert corrected["angle_a"]["ci_high"] - corrected["angle_a"]["ci_low"] > \
        plain["angle_a"]["ci_high"] - plain["angle_a"]["ci_low"]


def test_the_two_angles_can_disagree_and_that_is_flagged() -> None:
    # like r03: more often slightly up, but the falls are deep, so the mean is lower
    dates = pd.bdate_range("2024-01-01", periods=300)
    events = pd.DataFrame({"date": dates, "ret": np.where(np.arange(300) % 10 < 6, 0.2, -3.0)})
    base = pd.DataFrame({"date": dates, "ret": np.where(np.arange(300) % 10 < 4, 1.0, -0.5)})
    s = summary(events, base)
    assert s["angle_a"]["difference"] < 0 < s["angle_b"]["difference"] and s["angles_disagree"] is True


def test_wilson_bounds_hold_at_zero_and_all_successes() -> None:
    events, base = frames(50, effect=0.0)
    events["ret"] = -1.0
    s = summary(events, base)
    assert s["angle_b"]["condition_rate"] == 0 and 0 <= s["angle_b"]["condition_ci"][0] <= s["angle_b"]["condition_ci"][1] <= 1
    events["ret"] = 1.0
    s = summary(events, base)
    assert s["angle_b"]["condition_rate"] == 1 and s["angle_b"]["condition_ci"][1] == 1


def test_the_smallest_effect_comes_from_the_plan_the_trading_cost_or_the_spread() -> None:
    events, base = frames(100, effect=0.0)
    assert summary(events, base, min_effect=2.0)["sample"]["smallest_effect_source"] == "PLAN"
    percent = summary(events, base, outcome_unit="PERCENT")["sample"]
    assert percent["smallest_effect_of_interest"] == 0.5 and percent["smallest_effect_source"] == "ROUND_TRIP_TRADING_COST"
    assert summary(events, base, outcome_unit="DECIMAL")["sample"]["smallest_effect_of_interest"] == 0.005
    other = summary(events, base, outcome_unit="OTHER")["sample"]
    assert other["smallest_effect_source"] == "SMALL_STANDARDIZED_EFFECT" and 0 < other["smallest_effect_of_interest"] < 1


def test_a_success_column_and_missing_outcomes_are_respected() -> None:
    events, base = frames(30, effect=0.0)
    events.loc[:4, "ret"] = np.nan
    events["recovered"] = [True, False] * 15
    base["recovered"] = False
    table = rs.aggregate(events, base, "ret", "date", success_column="recovered")
    cond = table[table["group"] == "CONDITION"]
    assert cond["n"].sum() == 25 and cond["m"].sum() == 30 and cond["k"].sum() == 15
    with pytest.raises(rs.ResearchStatsError):
        rs.aggregate(events, base, "missing_column", "date")


# ------------------------------------------------------------------------------------------ Research Governor

def governance(**overrides):
    g = {"hypothesis_id": "gap_down", "hypothesis": "Falls recover.", "objective": "Pattern.", "candidate_count": 1,
         "pairwise_comparisons": 0, "holdout": None, "minimum_sample": {"value": 10, "unit": "EVENTS"},
         "multiple_testing_policy": "NONE", "followup_of": None}
    g.update(overrides)
    return g


def test_the_fixed_minimum_sample_applies_only_while_findings_are_off() -> None:
    spec = {"request_group_id": "data_request_1", "data_requests": []}
    old = review(governance(), spec, [], 0, GovernancePolicy())
    assert old["decision"] == "REPLAN_REQUIRED" and old["reason_code"] == "MINIMUM_SAMPLE_TOO_LOW"
    new = review(governance(), spec, [], 0, GovernancePolicy(enforce_minimum_sample=False))
    assert new["decision"] == "APPROVED"
    assert GovernancePolicy(enforce_minimum_sample=False).public()["minimum_sample"] is None


def test_findings_fields_are_required_only_with_the_flag_and_validated_when_given() -> None:
    assert check_request(governance()) == []
    missing = {p["field_path"] for p in check_request(governance(), findings_required=True)}
    assert missing == {"research_governance.expected_direction", "research_governance.outcome_horizon_periods",
                       "research_governance.outcome_unit"}
    good = governance(expected_direction="HIGHER", outcome_horizon_periods=5, outcome_unit="PERCENT",
                      min_effect=0.5, success_definition="5-day return > 0")
    assert check_request(good, findings_required=True) == []
    bad = governance(expected_direction="UP", outcome_horizon_periods=0, outcome_unit="IDR", min_effect=-1,
                     success_definition=" ")
    assert {p["field_path"].split(".")[-1] for p in check_request(bad)} == {
        "expected_direction", "outcome_horizon_periods", "outcome_unit", "min_effect", "success_definition"}
    decision = review(good, {"request_group_id": "data_request_1", "data_requests": []}, [], 0,
                      GovernancePolicy(enforce_minimum_sample=False))
    assert decision["constraints"]["findings"]["outcome_horizon_periods"] == 5


# ------------------------------------------------------------------------------------------ backend recomputation

def write(root: Path, name: str, table: pd.DataFrame) -> dict:
    relative = f"sess/{name}.parquet"
    (root / "sess").mkdir(parents=True, exist_ok=True)
    table.to_parquet(root / relative, index=False)
    return {"name": name, "format": "PARQUET", "relative_path": relative, "output_id": "out_1"}


def constraints(**findings):
    return {"hypothesis_id": "gap_down", "candidate_count": 1, "pairwise_comparisons": 0,
            "multiple_testing_policy": "NONE",
            "findings": {"expected_direction": "HIGHER", "outcome_horizon_periods": 1, "outcome_unit": "PERCENT",
                         **findings}}


def test_the_backend_needs_the_released_aggregates(tmp_path) -> None:
    result = evaluate(constraints(), [], tmp_path)
    assert result["status"] == "MISSING" and "event_summary" in result["message"]


def test_the_backend_uses_the_plan_values_not_the_models(tmp_path) -> None:
    events, base = frames(20, effect=0.5)
    table = rs.aggregate(events, base, "ret", "date")
    output = write(tmp_path, "research_events_gap_down", table)
    one = evaluate(constraints(), [output], tmp_path)
    five = evaluate(constraints(outcome_horizon_periods=5), [output], tmp_path)
    assert one["status"] == five["status"] == "OK"
    assert one["finding"]["sample"]["effective"] == 20 and five["finding"]["sample"]["effective"] == 4
    assert five["finding"]["sample_flag"] == "ANECDOTAL" and five["finding"]["verdict"] == "INCONCLUSIVE"
    assert parameters(constraints(outcome_horizon_periods=5))["horizon_periods"] == 5


def test_a_malformed_table_is_reported_not_trusted(tmp_path) -> None:
    events, base = frames(20, effect=0.5)
    table = rs.aggregate(events, base, "ret", "date")
    table.loc[0, "k"] = table.loc[0, "m"] + 5
    result = evaluate(constraints(), [write(tmp_path, "research_events_gap_down", table)], tmp_path)
    assert result["status"] == "INVALID"
    table = table.drop(columns=["total_sq"])
    result = evaluate(constraints(), [write(tmp_path, "research_events_gap_down", table)], tmp_path)
    assert result["status"] == "INVALID"


def test_the_runtime_and_the_backend_compute_the_same_numbers(tmp_path) -> None:
    events, base = frames(120, effect=0.4, sd=2.0, per_date=3)
    table = rs.aggregate(events, base, "ret", "date")
    direct = rs.summarize(table, horizon_periods=1, expected_direction="HIGHER", outcome_unit="PERCENT")
    backend = evaluate(constraints(), [write(tmp_path, "research_events_gap_down", table)], tmp_path)["finding"]
    assert backend["verdict"] == direct["verdict"]
    assert math.isclose(backend["angle_a"]["difference"], direct["angle_a"]["difference"])
    assert math.isclose(backend["sample"]["minimum_detectable_effect"], direct["sample"]["minimum_detectable_effect"])


# ------------------------------------------------------------------------------------------ P26 units

def test_the_same_data_in_percent_or_decimal_gives_the_same_judgement() -> None:
    """P26 (golden g6): a smallest effect of one point is 1.0 for percent outcomes and 0.01 for decimal outcomes; the
    recommended sample is the same, not 10,000 times larger."""
    events, base = frames(184, effect=0.7, sd=7.0)
    percent = summary(events, base, outcome_unit="PERCENT", min_effect=1.0, horizon_periods=1)
    events_d, base_d = events.assign(ret=events["ret"] / 100), base.assign(ret=base["ret"] / 100)
    decimal = summary(events_d, base_d, outcome_unit="DECIMAL", min_effect=0.01, horizon_periods=1)
    assert percent["sample"]["recommended_effective_per_group"] == decimal["sample"]["recommended_effective_per_group"]
    assert percent["sample"]["flag"] == decimal["sample"]["flag"] and percent["verdict"] == decimal["verdict"]
    mixed = summary(events, base, outcome_unit="DECIMAL", min_effect=0.01, horizon_periods=1)  # the g6 mistake
    assert mixed["sample"]["recommended_effective_per_group"] > 1000 * percent["sample"]["recommended_effective_per_group"]


def test_percent_outcomes_under_a_decimal_plan_are_invalid(tmp_path) -> None:
    events, base = frames(120, effect=0.7, sd=7.0)  # ten-day returns in percent, as in g6
    output = write(tmp_path, "research_events_gap_down", rs.aggregate(events, base, "ret", "date"))
    result = evaluate(constraints(outcome_unit="DECIMAL", min_effect=0.01), [output], tmp_path)
    assert result["status"] == "INVALID" and "look like percent" in result["message"]
    events_d, base_d = events.assign(ret=events["ret"] / 100), base.assign(ret=base["ret"] / 100)
    output = write(tmp_path, "research_events_gap_down", rs.aggregate(events_d, base_d, "ret", "date"))
    assert evaluate(constraints(outcome_unit="DECIMAL", min_effect=0.01), [output], tmp_path)["status"] == "OK"


def test_a_summary_built_in_another_unit_is_invalid(tmp_path) -> None:
    import json

    events, base = frames(60, effect=0.01, sd=0.02)
    table = write(tmp_path, "research_events_gap_down", rs.aggregate(events, base, "ret", "date"))
    built = rs.summarize(rs.aggregate(events, base, "ret", "date"), outcome_unit="PERCENT")
    (tmp_path / "sess" / "summary.json").write_text(json.dumps(built, default=str), encoding="utf-8")
    summary_output = {"name": "research_summary_gap_down", "format": "JSON", "relative_path": "sess/summary.json"}
    result = evaluate(constraints(outcome_unit="DECIMAL"), [table, summary_output], tmp_path)
    assert result["status"] == "INVALID" and "built with outcome_unit PERCENT" in result["message"]


def test_the_finding_carries_the_confidence_level_of_its_intervals(tmp_path) -> None:
    """10.5b (plan 2026-10-05 item 10): finding.<id>.confidence_level is citable, so "IK 95%" is not typed."""
    events, base = frames(20, effect=0.5)
    table = rs.aggregate(events, base, "ret", "date")
    finding = evaluate(constraints(), [write(tmp_path, "research_events_gap_down", table)], tmp_path)["finding"]
    assert finding["confidence_level"] == round(1 - finding["parameters"]["alpha_adjusted"], 6)
    assert finding["confidence_level"] == 0.95
