"""Research engines v2 (Multi-Angle Research): golden values for the five engines and eight method ids, parity with
findings v1 (runtime/research_stats.py) and the Analysis Spec validator's Welch statistics, the multiple-testing
adjustments against statsmodels, deterministic ties, missing values, overlap, censoring, no look-ahead, and the status
rules (MULTI_ANGLE_RESEARCH.md §4)."""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))

import research_engines as E  # noqa: E402
import research_stats  # noqa: E402

BASE = {"expected_direction": "HIGHER", "outcome_horizon_periods": 1, "outcome_unit": "PERCENT", "min_effect": None,
        "multiple_testing_policy": "NONE", "candidate_count": 1, "pairwise_comparisons": 0}


def approved(**overrides):
    return {**BASE, **overrides}


def panel(seed: int = 7, days: int = 120, entities: int = 20) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for d in pd.bdate_range("2025-01-01", periods=days):
        for i in range(entities):
            signal = rng.normal()
            rows.append({"date": d, "entity": f"E{i:02d}", "signal": signal,
                         "outcome": 0.4 * signal + rng.normal(), "condition": signal > 1.0})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------------------------------ registry and adjustment

def test_the_registry_has_five_engines_and_eight_methods() -> None:
    reg = E.registry()
    assert len(reg["methods"]) == 8 and {m["method_family"] for m in reg["methods"]} == set(E.FAMILIES)
    assert reg == E.registry() and len(reg["sha256"]) == 64


@pytest.mark.parametrize("policy,name", [("BONFERRONI", "bonferroni"), ("HOLM", "holm"),
                                         ("BENJAMINI_HOCHBERG", "fdr_bh")])
def test_adjusted_p_values_match_statsmodels(policy: str, name: str) -> None:
    from statsmodels.stats.multitest import multipletests

    p = [0.001, 0.02, 0.04, 0.3, 0.012]
    expected = multipletests(p, method=name)[1]
    assert np.allclose(E.adjust_p_values(p, policy, len(p)), expected)
    # untested declared comparisons count against the family (m larger than the p-values given)
    assert E.adjust_p_values([0.01], "BONFERRONI", 5) == [pytest.approx(0.05)]
    assert E.adjust_p_values([0.01, None], "NONE", 2) == [0.01, None]


# ------------------------------------------------------------------------------------------ conditional outcome

def test_conditional_distribution_matches_findings_v1() -> None:
    frame = panel()
    events = frame[frame["condition"]]
    baseline = frame[~frame["condition"]]
    table = research_stats.aggregate(events, baseline, "outcome", "date")
    v1 = research_stats.summarize(table, horizon_periods=3, expected_direction="HIGHER", outcome_unit="PERCENT")
    result = E.evaluate("conditional_distribution", frame,
                        approved(outcome_horizon_periods=3, parameters={"baseline_mode": "COMPLEMENT"}))
    primary = result["primary"]
    assert primary["estimate"] == pytest.approx(v1["angle_a"]["difference"])
    assert primary["ci"] == pytest.approx([v1["angle_a"]["ci_low"], v1["angle_a"]["ci_high"]])
    assert primary["p_value"] == pytest.approx(v1["angle_a"]["p_value"])
    assert result["sample"]["effective"] == v1["sample"]["effective"]
    assert result["sample"]["flag"] == v1["sample"]["flag"]
    groups = result["method_payload"]["groups"]["condition"]
    assert groups["condition"]["hit_rate"] == pytest.approx(v1["groups"]["CONDITION"]["success_rate"])
    decision = E.decide(result, expected_direction="HIGHER", validation_level="STATISTICS_VERIFIED")
    assert decision["status"] == "SUPPORTED" and decision["evidence_direction"] == "EXPECTED"


def test_distribution_tails_percentiles_and_expected_outcome() -> None:
    dates = pd.bdate_range("2025-01-01", periods=40)
    frame = pd.DataFrame({"date": dates, "condition": [i < 20 for i in range(40)],
                          "outcome": [float(i + 1) for i in range(20)] + [0.0] * 20})
    result = E.evaluate("conditional_distribution", frame, approved(parameters={"baseline_mode": "COMPLEMENT"}))
    cond = result["method_payload"]["groups"]["condition"]["condition"]
    values = np.arange(1, 21, dtype=float)
    assert cond["mean"] == pytest.approx(10.5) and cond["median"] == pytest.approx(10.5)
    assert cond["percentiles"]["p25"] == pytest.approx(np.percentile(values, 25))
    assert cond["downside_tail"] == {"p5": pytest.approx(np.percentile(values, 5)), "mean_of_worst": 1.0, "rows": 1}
    assert cond["upside_tail"]["mean_of_best"] == 20.0 and cond["hit_rate"] == 1.0
    assert cond["expected_outcome"] == pytest.approx(10.5)
    # baseline ALL uses every row with a defined condition as the comparator
    everything = E.evaluate("conditional_distribution", frame, approved(parameters={"baseline_mode": "ALL"}))
    assert everything["method_payload"]["groups"]["condition"]["baseline"]["rows"] == 40


def test_threshold_sensitivity_adjusts_over_every_threshold() -> None:
    frame = panel()
    result = E.evaluate("threshold_sensitivity", frame, approved(
        multiple_testing_policy="BONFERRONI", candidate_count=4,
        parameters={"thresholds": [0.5, 1.0, 1.5], "threshold_operator": ">="}))
    assert [c["candidate"] for c in result["candidates"]] == [">=0.5", ">=1", ">=1.5"]
    assert result["multiple_testing"]["tests"] == 4  # the declared count, larger than the thresholds computed
    for candidate in result["candidates"]:
        assert candidate["p_adjusted"] == pytest.approx(min(1.0, candidate["p_value"] * 4))
        low, high = candidate["ci_adjusted"]
        assert low < candidate["ci"][0] and high > candidate["ci"][1]  # wider than the unadjusted interval


def test_overlapping_outcomes_are_thinned_and_missing_outcomes_counted() -> None:
    dates = pd.bdate_range("2025-01-01", periods=20)
    frame = pd.DataFrame({"date": dates, "condition": [True] * 20,
                          "outcome": [float(i % 3) for i in range(19)] + [np.nan]})
    base = pd.DataFrame({"date": dates, "condition": [False] * 20, "outcome": [0.5] * 20, "entity": "B"})
    frame["entity"] = "A"
    result = E.evaluate("conditional_distribution", pd.concat([frame, base]),
                        approved(outcome_horizon_periods=5, parameters={"baseline_mode": "COMPLEMENT"}))
    cond = result["method_payload"]["groups"]["condition"]["condition"]
    assert cond["rows"] == 19 and cond["effective"] == 4  # positions 0, 5, 10, 15 of 19 dates with an outcome
    assert result["sample"]["missing_outcome_rows"] == 1


def test_zero_variance_has_no_uncertainty_and_no_verdict() -> None:
    dates = pd.bdate_range("2025-01-01", periods=30)
    frame = pd.DataFrame({"date": dates, "condition": [i % 2 == 0 for i in range(30)], "outcome": 1.0})
    result = E.evaluate("conditional_distribution", frame, approved(parameters={"baseline_mode": "COMPLEMENT"}))
    assert result["primary"]["ci"] is None and result["primary"]["degenerate"] is True
    decision = E.decide(result, expected_direction="HIGHER", validation_level="STATISTICS_VERIFIED")
    assert decision["status"] == "INSUFFICIENT_EVIDENCE"


def test_duplicate_entity_dates_and_missing_columns_fail_closed() -> None:
    dates = pd.bdate_range("2025-01-01", periods=3)
    frame = pd.DataFrame({"date": list(dates) * 2, "entity": "A", "condition": True, "outcome": 1.0})
    with pytest.raises(E.EngineError) as error:
        E.evaluate("conditional_distribution", frame, approved(parameters={"baseline_mode": "ALL"}))
    assert error.value.code == "DUPLICATE_ENTITY_DATE"
    with pytest.raises(E.EngineError) as error:
        E.evaluate("conditional_distribution", frame.drop(columns="condition"), approved(parameters={}))
    assert error.value.code == "INPUT_COLUMNS_MISSING"


# ------------------------------------------------------------------------------------------ persistence

def test_streak_persistence_golden_counts() -> None:
    states = [True, True, False, True, True, True, False, True]
    frame = pd.DataFrame({"date": pd.bdate_range("2025-01-01", periods=8), "entity": "A", "state": states})
    result = E.evaluate("streak_persistence", frame, approved(
        multiple_testing_policy="HOLM", candidate_count=2, parameters={"streak_lengths": [1, 2]}))
    by = {c["streak_length"]: c for c in result["candidates"]}
    assert result["comparator"]["base_rate"] == pytest.approx(5 / 7)
    assert (by[1]["events"], by[1]["continuations"], by[1]["rate_a"]) == (5, 3, pytest.approx(3 / 5))
    assert (by[2]["events"], by[2]["continuations"], by[2]["rate_a"]) == (3, 1, pytest.approx(1 / 3))
    payload = result["method_payload"]
    assert payload["episodes"] == 3 and payload["censored_episodes"] == 1
    assert payload["episode_counts_by_length"] == {"1": 1, "2": 1, ">=3": 1}
    assert [s["share_at_least"] for s in payload["survival_curve"]] == pytest.approx([1.0, 2 / 3, 1 / 3])
    assert [e["continuation_rate"] for e in payload["continuation_by_exact_length"]] == [1.0, 0.5]


def test_persistence_ignores_a_continuation_without_a_complete_horizon() -> None:
    frame = pd.DataFrame({"date": pd.bdate_range("2025-01-01", periods=5), "entity": "A",
                          "state": [True, True, None, True, True]})
    result = E.evaluate("streak_persistence", frame, approved(outcome_horizon_periods=2,
                                                              parameters={"streak_lengths": [1]}))
    # rows 0..2 have two later observations; row 0 and 1 see the null state, row 2 is itself null
    assert result["sample"]["observations_with_outcome"] == 0


# ------------------------------------------------------------------------------------------ group comparison

def test_cohort_comparison_matches_welch_on_entity_means() -> None:
    from scipy import stats

    frame = panel()
    frame["group"] = np.where(frame["entity"] < "E10", "SMALL", "LARGE")
    frame.loc[frame["group"] == "SMALL", "outcome"] += 0.3
    result = E.evaluate("cohort_comparison", frame[["date", "entity", "group", "outcome"]], approved(
        pairwise_comparisons=1, parameters={"groups": ["SMALL", "LARGE"], "comparison": "PAIRWISE"}))
    means = frame.groupby(["group", "entity"])["outcome"].mean()
    small, large = means.loc["SMALL"].to_numpy(), means.loc["LARGE"].to_numpy()
    scipy = stats.ttest_ind(small, large, equal_var=False)
    primary = result["primary"]
    assert primary["estimate"] == pytest.approx(small.mean() - large.mean())
    assert primary["p_value"] == pytest.approx(scipy.pvalue)
    import validator  # the inactive Analysis Spec validator: the parity reference for group comparisons

    reference = validator._welch("SMALL", small, "LARGE", large)
    assert primary["standard_error"] == pytest.approx(reference["standard_error"])
    assert primary["df"] == pytest.approx(reference["df"])
    assert result["sample"]["unit"] == "ENTITIES" and result["sample"]["effective"] == 10


def test_group_comparison_refuses_undeclared_and_unstable_groups() -> None:
    frame = panel(days=10, entities=4)
    frame["group"] = np.where(frame["entity"] < "E02", "A", "C")
    with pytest.raises(E.EngineError) as error:
        E.evaluate("cohort_comparison", frame, approved(parameters={"groups": ["A", "B"], "comparison": "PAIRWISE"}))
    assert error.value.code == "UNDECLARED_GROUP"
    frame["group"] = np.where(pd.to_datetime(frame["date"]).dt.day % 2 == 0, "A", "B")  # changes over time
    with pytest.raises(E.EngineError) as error:
        E.evaluate("cohort_comparison", frame, approved(parameters={"groups": ["A", "B"], "comparison": "PAIRWISE"}))
    assert error.value.code == "COHORT_NOT_CONSTANT"


def test_regime_comparison_uses_dates_and_reports_small_and_missing_groups() -> None:
    frame = panel(days=60, entities=5)
    month = pd.to_datetime(frame["date"]).dt.month
    frame["group"] = np.where(month == 1, "JAN", np.where(month == 2, "FEB", "MAR"))
    result = E.evaluate("regime_comparison", frame[["date", "entity", "group", "outcome"]], approved(
        multiple_testing_policy="BONFERRONI", pairwise_comparisons=3,
        parameters={"groups": ["JAN", "FEB", "MAR", "APR"], "comparison": "FIRST_VS_OTHERS"}))
    assert result["sample"]["unit"] == "DATES"
    assert result["comparator"]["missing_groups"] == ["APR"]
    assert [c["candidate"] for c in result["candidates"]] == ["JAN - FEB", "JAN - MAR", "JAN - APR"]
    missing = result["candidates"][2]
    assert missing["estimate"] is None and missing["p_value"] is None


# ------------------------------------------------------------------------------------------ quantile ranking

def test_quantile_ranking_breaks_ties_by_entity_and_skips_thin_dates() -> None:
    d1, d2, d3 = pd.Timestamp("2025-01-02"), pd.Timestamp("2025-01-03"), pd.Timestamp("2025-01-06")
    frame = pd.DataFrame({
        "date": [d1] * 4 + [d2] * 4 + [d3],
        "entity": ["A", "B", "C", "D"] * 2 + ["A"],
        "signal": [1, 2, 3, 4, 5, 5, 5, 5, 9],
        "outcome": [1, 2, 3, 4, 4, 3, 2, 1, 9]})
    result = E.evaluate("quantile_ranking", frame, approved(parameters={"buckets": 2}))
    payload = result["method_payload"]
    # d1: bottom (A, B) 1.5, top (C, D) 3.5; d2: equal signals ranked A, B | C, D: bottom 3.5, top 1.5
    assert payload["bucket_mean_outcome"] == [2.5, 2.5]
    assert result["primary"]["estimate"] == pytest.approx(0.0) and result["primary"]["dates"] == 2
    assert result["sample"]["dates_skipped_too_few_entities"] == 1
    again = E.evaluate("quantile_ranking", frame.sample(frac=1, random_state=3), approved(parameters={"buckets": 2}))
    assert again["method_payload"]["bucket_mean_outcome"] == payload["bucket_mean_outcome"]


def test_quantile_ranking_spread_monotonicity_and_ic() -> None:
    frame = panel(days=150, entities=25)
    result = E.evaluate("quantile_ranking", frame, approved(parameters={"buckets": 5}))
    means = result["method_payload"]["bucket_mean_outcome"]
    assert means == sorted(means) and result["secondary"]["monotonicity"] == "PASS"
    assert result["primary"]["estimate"] == pytest.approx(means[-1] - means[0], rel=1e-9)
    assert result["method_payload"]["rank_ic"]["mean"] > 0.2
    assert E.decide(result, expected_direction="HIGHER", validation_level="STATISTICS_VERIFIED")["status"] == \
        "SUPPORTED"
    lower = E.evaluate("quantile_ranking", frame, approved(expected_direction="LOWER", parameters={"buckets": 5}))
    decision = E.decide(lower, expected_direction="LOWER", validation_level="STATISTICS_VERIFIED")
    assert decision == {"status": "INSUFFICIENT_EVIDENCE", "reason": "EFFECT_OPPOSITE_TO_EXPECTED",
                        "evidence_direction": "OPPOSITE"}


# ------------------------------------------------------------------------------------------ temporal dependency

def test_lead_lag_finds_the_true_lag_and_never_looks_ahead() -> None:
    rng = np.random.default_rng(11)
    x = rng.normal(size=300)
    y = np.concatenate([[0.0, 0.0], x[:-2]]) + 0.5 * rng.normal(size=300)
    dates = pd.bdate_range("2024-01-01", periods=300)
    frame = pd.DataFrame({"date": dates, "leader": x, "follower": y})
    result = E.evaluate("lead_lag", frame, approved(
        multiple_testing_policy="BONFERRONI", candidate_count=4,
        parameters={"lags": [0, 1, 2, 3], "primary_lag": 2, "correlation_method": "PEARSON"}))
    curve = {c["lag"]: c["r"] for c in result["method_payload"]["lag_curve"]}
    assert max(curve, key=lambda k: curve[k]) == 2 and curve[2] > 0.8
    assert E.decide(result, expected_direction="HIGHER", validation_level="STATISTICS_VERIFIED")["status"] == \
        "SUPPORTED"
    # a follower that equals the leader's next value: pairing x_t with y_{t+k} never reaches back, so no lag shows it
    ahead = pd.DataFrame({"date": dates[:-1], "leader": x[:-1], "follower": x[1:]})
    result = E.evaluate("lead_lag", ahead, approved(parameters={"lags": [0, 1, 2], "primary_lag": 0,
                                                                 "correlation_method": "PEARSON"}))
    assert all(abs(c["r"]) < 0.2 for c in result["method_payload"]["lag_curve"])


def test_lead_lag_reports_a_non_predeclared_lag_as_partial() -> None:
    rng = np.random.default_rng(5)
    x = rng.normal(size=250)
    y = np.concatenate([[0.0], x[:-1]]) + 0.5 * rng.normal(size=250)
    frame = pd.DataFrame({"date": pd.bdate_range("2024-01-01", periods=250), "leader": x, "follower": y})
    result = E.evaluate("lead_lag", frame, approved(
        multiple_testing_policy="HOLM", candidate_count=3,
        parameters={"lags": [1, 3, 5], "primary_lag": 5, "correlation_method": "SPEARMAN"}))
    decision = E.decide(result, expected_direction="HIGHER", validation_level="STATISTICS_VERIFIED")
    assert decision["status"] == "PARTIALLY_SUPPORTED" and decision["reason"] == "NOT_AT_PREDECLARED_CANDIDATE"


def test_correlation_dependency_rolling_and_conditional() -> None:
    rng = np.random.default_rng(3)
    x = rng.normal(size=200)
    condition = np.arange(200) % 2 == 0
    y = np.where(condition, x, -x) + 0.3 * rng.normal(size=200)
    frame = pd.DataFrame({"date": pd.bdate_range("2024-01-01", periods=200), "leader": x, "follower": y,
                          "condition": condition})
    result = E.evaluate("correlation_dependency", frame, approved(
        expected_direction="DIFFERENT", parameters={"primary_lag": 0, "rolling_window": 20,
                                                    "correlation_method": "PEARSON"}))
    payload = result["method_payload"]
    assert payload["rolling"]["count"] == 181
    conditional = payload["conditional"]
    assert conditional["when_true"]["estimate"] > 0.9 and conditional["when_false"]["estimate"] < -0.9
    assert conditional["difference"]["p_value"] < 1e-6
    assert result["multiple_testing"]["tests"] == 2  # the conditional difference counts as a comparison


def test_autocorrelation_reduces_the_effective_sample() -> None:
    rng = np.random.default_rng(9)
    walk_x, walk_y = np.cumsum(rng.normal(size=300)), np.cumsum(rng.normal(size=300))
    frame = pd.DataFrame({"date": pd.bdate_range("2024-01-01", periods=300), "leader": walk_x, "follower": walk_y})
    result = E.evaluate("correlation_dependency", frame, approved(parameters={"primary_lag": 0,
                                                                              "correlation_method": "PEARSON"}))
    assert result["primary"]["n"] == 300 and result["primary"]["effective"] < 30


# ------------------------------------------------------------------------------------------ holdout and status rules

def test_holdout_must_agree_for_support() -> None:
    frame = panel(days=160)
    result = E.evaluate("quantile_ranking", frame, approved(parameters={"buckets": 5}, holdout_start="2025-05-01"))
    assert result["secondary"]["holdout"] == "PASS" and result["holdout"]["rows"] > 0
    flipped = frame.copy()
    late = pd.to_datetime(flipped["date"]) >= pd.Timestamp("2025-05-01")
    flipped.loc[late, "outcome"] = -flipped.loc[late, "outcome"]
    result = E.evaluate("quantile_ranking", flipped, approved(parameters={"buckets": 5}, holdout_start="2025-05-01"))
    decision = E.decide(result, expected_direction="HIGHER", validation_level="STATISTICS_VERIFIED")
    assert decision["status"] == "PARTIALLY_SUPPORTED" and "holdout" in decision["reason"]


def candidate(name: str, estimate: float, ci, ci_adjusted) -> dict:
    return {"candidate": name, "estimate": estimate, "ci": ci, "ci_adjusted": ci_adjusted, "degenerate": False}


def result_with(candidates, primary=None, flag="ADEQUATE", predeclared=False, secondary=None) -> dict:
    return {"candidates": candidates, "primary": primary or candidates[0], "primary_is_predeclared": predeclared,
            "sample": {"flag": flag, "rows": 100, "entities": 10}, "secondary": secondary or {}}


@pytest.mark.parametrize("case,expected", [
    (result_with([candidate("a", 1.0, [0.5, 1.5], [0.2, 1.8])]), ("SUPPORTED", "EXPECTED")),
    (result_with([candidate("a", 1.0, [0.5, 1.5], [-0.2, 2.2])]), ("PARTIALLY_SUPPORTED", "EXPECTED")),
    (result_with([candidate("a", -1.0, [-1.5, -0.5], [-1.8, -0.2])]), ("INSUFFICIENT_EVIDENCE", "OPPOSITE")),
    (result_with([candidate("a", 0.1, [-0.5, 0.7], [-0.9, 1.1])]), ("INSUFFICIENT_EVIDENCE", "NONE")),
    (result_with([candidate("a", 1.0, [0.5, 1.5], [0.2, 1.8])], flag="ANECDOTAL"), ("INSUFFICIENT_EVIDENCE",
                                                                                     "EXPECTED")),
    (result_with([candidate("a", 1.0, [0.5, 1.5], [0.2, 1.8])], secondary={"monotonicity": "FAIL"}),
     ("PARTIALLY_SUPPORTED", "EXPECTED")),
    (result_with([candidate("a", 1.0, [0.5, 1.5], [0.2, 1.8]), candidate("b", -1.0, [-1.5, -0.5], [-1.8, -0.2])]),
     ("PARTIALLY_SUPPORTED", "EXPECTED")),
])
def test_status_rules(case: dict, expected: tuple[str, str]) -> None:
    decision = E.decide(case, expected_direction="HIGHER", validation_level="STATISTICS_VERIFIED")
    assert (decision["status"], decision["evidence_direction"]) == expected


def test_execution_only_and_minimum_sample_cap_the_status() -> None:
    supported = result_with([candidate("a", 1.0, [0.5, 1.5], [0.2, 1.8])])
    assert E.decide(supported, expected_direction="HIGHER", validation_level="EXECUTION_ONLY")["status"] == \
        "INSUFFICIENT_EVIDENCE"
    decision = E.decide(supported, expected_direction="HIGHER", validation_level="STATISTICS_VERIFIED",
                        minimum_sample={"value": 500, "unit": "OBSERVATIONS"})
    assert decision == {"status": "INSUFFICIENT_EVIDENCE", "reason": "MINIMUM_SAMPLE_NOT_MET",
                        "evidence_direction": "EXPECTED"}
    # DIFFERENT accepts either direction
    lower = result_with([candidate("a", -1.0, [-1.5, -0.5], [-1.8, -0.2])])
    assert E.decide(lower, expected_direction="DIFFERENT", validation_level="STATISTICS_VERIFIED")["status"] == \
        "SUPPORTED"


def test_every_result_is_json_ready() -> None:
    import json

    frame = panel(days=40, entities=6)
    frame["state"] = frame["outcome"] > 0
    frame["group"] = np.where(frame["entity"] < "E03", "A", "B")
    frame["leader"], frame["follower"] = frame["signal"], frame["outcome"]
    parameters = {"conditional_distribution": {"baseline_mode": "ALL"},
                  "threshold_sensitivity": {"thresholds": [0.0], "threshold_operator": "<="},
                  "streak_persistence": {"streak_lengths": [2]},
                  "cohort_comparison": {"groups": ["A", "B"], "comparison": "VS_REST"},
                  "quantile_ranking": {"buckets": 3},
                  "lead_lag": {"lags": [0, 1], "primary_lag": 0, "correlation_method": "PEARSON"},
                  "correlation_dependency": {"primary_lag": 1, "rolling_window": 10, "correlation_method": "PEARSON"}}
    for method, params in parameters.items():
        result = E.evaluate(method, frame, approved(parameters=params, candidate_count=2, pairwise_comparisons=2,
                                                    multiple_testing_policy="BENJAMINI_HOCHBERG"))
        text = json.dumps(result, allow_nan=False)
        assert method in text and not math.isnan(len(text))
