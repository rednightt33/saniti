"""Research AI unit tests (no processes): research specs, formula conventions and CUSTOM expressions, the Research
Governor, and the post-run evidence assessment. Test numbers refer to the Research AI requirements (1-37)."""
from __future__ import annotations

import copy
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))

import expression  # noqa: E402
import validator  # noqa: E402
from app.research_policy import ResearchPolicy, pairwise_candidates, research_context, review  # noqa: E402
from app.spec import (AnalysisSpec, SpecInvalid, convention_notes, derived_feature_definitions, normalize,  # noqa: E402
                      required_input, resolve_period)
from conftest import zscore_spec  # noqa: E402

REF = date(2026, 9, 23)
POLICY = ResearchPolicy()


def normalized(raw: dict) -> dict:
    return normalize(AnalysisSpec.model_validate(raw), REF)


def problems(raw: dict) -> str:
    with pytest.raises(SpecInvalid) as error:
        normalized(raw)
    return "; ".join(error.value.problems)


def ohlc_input(columns=("ticker", "date", "open", "close", "volume")) -> dict:
    return {"name": "prices", "source_table": "Price_Stock_Indonesia_IDX", "entity_column": "ticker",
            "date_column": "date", "columns": list(columns)}


def event_study_spec(research: dict | None = None, **changes) -> dict:
    spec = zscore_spec(question="Event study for all IDX stocks from 2025-01-02 to 2026-06-30: after a 20-day z-score "
                                "below -1.5, what is the 5-day forward return?")
    spec["analysis_period"] = {"mode": "EXPLICIT_DATES", "start": "2025-01-02", "end": "2026-06-30",
                               "provenance": "USER_EXPLICIT"}
    spec["inputs"] = [ohlc_input()]
    spec["calculations"] = [
        {"id": "z20", "method": "ROLLING_ZSCORE", "dataset": "prices", "columns": ["close"],
         "params": [{"name": "window", "value": 20, "provenance": "USER_EXPLICIT"}],
         "output_column": "zscore_20", "provenance": "USER_EXPLICIT"},
        {"id": "fwd5", "method": "FORWARD_RETURN", "dataset": "prices", "columns": ["close", "open"],
         "params": [{"name": "horizon", "value": 5, "provenance": "USER_EXPLICIT"}],
         "output_column": "fwd_5", "provenance": "USER_EXPLICIT"},
        {"id": "study", "method": "EVENT_STUDY", "dataset": "prices", "input_calculation": "fwd5",
         "signal": [{"calculation": "z20", "op": "<", "value": -1.5, "provenance": "USER_EXPLICIT"}],
         "output_column": "event_study", "provenance": "USER_EXPLICIT"},
    ]
    spec["outputs"] = [{"name": "summary", "grain": "SUMMARY", "calculations": ["study"]}]
    spec["research"] = research if research is not None else {
        "evidence_standard": "HISTORICAL_PATTERN", "objective": "Is a deep z-score followed by higher returns?",
        "hypothesis": {"id": "H1", "statement": "Deep negative z-scores are followed by above-baseline returns."},
        "method_ref": "event_study"}
    for key, value in changes.items():
        spec[key] = value
    return spec


def custom_ratio_spec(expression_text: str = "rolling_sum(net_value, 20) / rolling_sum(value, 20)",
                      **calc_changes) -> dict:
    spec = zscore_spec(question="Foreign accumulation ratio for all stocks over the last three months.")
    spec["inputs"] = [{"name": "flows", "source_table": "Feature_03_Stock_Broker_Daily", "entity_column": "ticker",
                       "date_column": "date", "columns": ["ticker", "date", "net_value", "value"]}]
    calc = {"id": "far", "method": "CUSTOM", "dataset": "flows", "columns": ["net_value", "value"],
            "output_column": "foreign_accumulation_ratio", "formula": "sum(net 20d) / sum(value 20d)",
            "time_alignment": "trailing 20 observations including t", "expression": expression_text,
            "meaning": "Net foreign accumulation relative to traded value.", "unit": "ratio",
            "provenance": "AI_INFERRED"}
    calc.update(calc_changes)
    spec["calculations"] = [calc]
    spec["outputs"] = [{"name": "ratios", "grain": "ENTITY_DATE", "calculations": ["far"]}]
    return spec


def approve(spec: dict, experiments: list | None = None, parent: dict | None = None, policy=POLICY) -> dict:
    canonical = normalized(spec)
    return review(canonical, resolve_period(canonical["analysis_period"], REF), experiments or [], parent, policy)


def experiment(hypothesis: str | None, followup_of: str | None = None, candidates: int | None = None) -> dict:
    return {"spec_id": "spec_" + "0" * 24, "research": {
        "evidence_standard": "HISTORICAL_PATTERN", "objective": "o",
        "hypothesis": {"id": hypothesis, "statement": "s"} if hypothesis else None, "followup_of": followup_of,
        "candidates": candidates}}


# ---------------------------------------------------------------- specifications (1-5)

def test_01_valid_research_spec_is_accepted_and_approved() -> None:
    spec = normalized(event_study_spec())
    assert spec["research"]["evidence_standard"] == "HISTORICAL_PATTERN"
    decision = approve(event_study_spec())
    assert decision["decision"] == "APPROVED" and decision["reason_code"] is None
    assert decision["budget_before"]["experiments_remaining"] == 6
    assert decision["budget_after_reservation"]["experiments_remaining"] == 5
    assert "minimum_sample" in decision["constraints"]["required_validation"]


def test_02_invalid_research_spec_is_rejected() -> None:
    bad = event_study_spec({"evidence_standard": "HISTORICAL_PATTERN", "objective": "o",
                            "holdout": {"start": "2026-03-01", "end": "2026-01-01"}})
    assert "holdout: end is before start" in problems(bad)
    with pytest.raises(ValueError):
        AnalysisSpec.model_validate(event_study_spec({"evidence_standard": "PROVEN", "objective": "o"}))


def test_03_minimal_simple_analysis_spec_needs_no_research() -> None:
    spec = normalized(zscore_spec())
    assert spec["research"] is None and spec["calculations"][0]["convention"]["source"] == "FORMULA_REFERENCE"


def test_04_method_specific_required_parameters_are_enforced() -> None:
    spec = event_study_spec()
    spec["calculations"][1]["params"] = []
    assert "parameter horizon is required for FORWARD_RETURN" in problems(spec)
    spec = event_study_spec()
    spec["calculations"][2]["signal"] = None
    assert "EVENT_STUDY needs signal predicates" in problems(spec)
    spec = event_study_spec()
    spec["calculations"][1]["columns"] = ["close"]
    assert "FORWARD_RETURN takes 2 input column(s)" in problems(spec)


def test_05_unsupported_dataset_reference_is_rejected() -> None:
    spec = zscore_spec()
    spec["calculations"][0]["dataset"] = "fundamentals"
    assert "dataset 'fundamentals' is not one of the inputs" in problems(spec)


# ---------------------------------------------------------------- formulas (6-14)

def test_06_formula_references_are_recorded_and_validated() -> None:
    spec = normalized(custom_ratio_spec(formula_refs=["CALC_139"]))
    definition = derived_feature_definitions(spec)[0]
    assert definition["formula_refs"] == ["CALC_139"] and definition["convention"]["source"] == "AI_GENERATED"
    with pytest.raises(ValueError):
        AnalysisSpec.model_validate(custom_ratio_spec(formula_refs=["RSI"]))


def test_07_tested_implementation_is_selected_with_the_ta_lib_convention() -> None:
    spec = zscore_spec()
    spec["calculations"][0] = {"id": "rsi", "method": "RSI", "dataset": "prices", "columns": ["close"],
                               "params": [], "output_column": "rsi_14", "provenance": "USER_EXPLICIT"}
    spec["outputs"][0]["calculations"] = ["rsi"]
    canonical = normalized(spec)
    assert canonical["calculations"][0]["convention"] == {"source": "TA_LIB", "function": "RSI",
                                                          "formula_refs": ["CALC_028"]}
    assert derived_feature_definitions(canonical)[0]["formula_status"] == "TESTED_IMPLEMENTATION"
    # CUSTOM may not re-implement a tested method: the TA-Lib convention takes precedence
    assert "use that method" in problems(custom_ratio_spec(formula_refs=["CALC_028"]))


def test_08_niche_custom_formula_absent_from_the_catalog_is_allowed_and_recalculable() -> None:
    canonical = normalized(custom_ratio_spec())
    calc = canonical["calculations"][0]
    assert calc["expression_warmup"] == 19 and calc["data_policies"]["zero_denominator"] == "NULL"
    definition = derived_feature_definitions(canonical)[0]
    assert (definition["formula_status"], definition["independent_check"]) == ("CUSTOM_FORMULA",
                                                                             "EXPRESSION_RECALCULATION")
    assert required_input(canonical, resolve_period(canonical["analysis_period"], REF), REF)["flows"][
        "minimum_warmup_observations"] == 19


def test_09_zero_denominator_follows_the_declared_policy() -> None:
    groups = [np.arange(3)]
    columns = {"a": np.array([1.0, 2.0, 3.0]), "b": np.array([1.0, 0.0, 2.0])}
    assert np.isnan(expression.evaluate("a / b", columns, groups)[1])
    assert expression.evaluate("a / b", columns, groups, "ZERO")[1] == 0.0
    assert np.isfinite(expression.evaluate("a / b", columns, groups)).sum() == 2


def test_10_missing_values_propagate() -> None:
    groups = [np.arange(4)]
    values = expression.evaluate("rolling_sum(a, 2)", {"a": np.array([1.0, np.nan, 3.0, 4.0])}, groups)
    assert np.isnan(values[:3]).all() and values[3] == 7.0


def test_11_incompatible_units_are_detected() -> None:
    assert expression.unit_conflicts("net_value + volume", {"net_value": "IDR", "volume": "shares"})
    assert expression.unit_conflicts("rolling_sum(net_value, 20) / rolling_sum(value, 20)",
                                     {"net_value": "IDR", "value": "IDR"}) == []


def test_12_expression_lags_never_cross_entities() -> None:
    groups = [np.array([0, 1, 2]), np.array([3, 4, 5])]
    values = expression.evaluate("lag(x, 1)", {"x": np.array([1.0, 2, 3, 10, 20, 30])}, groups)
    assert np.isnan(values[0]) and np.isnan(values[3]) and values[4] == 10.0  # not 3.0 from the previous entity


def test_13_insufficient_lookback_is_derived_from_the_expression() -> None:
    info = expression.analyze("rolling_mean(lag(x, 5), 20)", {"x"})
    assert info.warmup == 24
    with pytest.raises(expression.ExpressionError):
        expression.analyze("lag(x, -1)", {"x"})  # no look-ahead
    with pytest.raises(expression.ExpressionError):
        expression.analyze("__import__('os')", {"x"})


def test_14_conflicting_definitions_resolve_by_precedence_and_are_disclosed() -> None:
    spec = zscore_spec()
    spec["calculations"][0] = {"id": "rsi", "method": "RSI", "dataset": "prices", "columns": ["close"],
                               "params": [], "output_column": "rsi_14", "provenance": "USER_EXPLICIT"}
    spec["outputs"][0]["calculations"] = ["rsi"]
    notes = convention_notes(normalized(spec))
    assert notes and notes[0]["formula_ref"] == "CALC_028" and "TA-Lib" in notes[0]["note"]
    # z-score of a return excludes the current observation (CALC_053); of a price it includes it (CALC_054)
    returns = zscore_spec()
    returns["calculations"] = [
        {"id": "r1", "method": "RETURN", "dataset": "prices", "columns": ["close"], "params": [],
         "output_column": "ret_1", "provenance": "AI_INFERRED"},
        {"id": "z20", "method": "ROLLING_ZSCORE", "dataset": "prices", "columns": [], "input_calculation": "r1",
         "params": [{"name": "window", "value": 20, "provenance": "USER_EXPLICIT"}], "output_column": "z",
         "provenance": "USER_EXPLICIT"}]
    params = {p["name"]: p["value"] for p in normalized(returns)["calculations"][1]["params"]}
    assert params["include_current"] is False and params["ddof"] == 1
    std = zscore_spec()
    std["calculations"][0]["method"] = "ROLLING_STD"
    params = {p["name"]: p["value"] for p in normalized(std)["calculations"][0]["params"]}
    assert params["ddof"] == 0  # TA-Lib STDDEV


# ---------------------------------------------------------------- Research Governor (15-23)

def test_15_experiment_within_budget_is_approved() -> None:
    assert approve(event_study_spec(), [experiment("H2"), experiment("H3")])["decision"] == "APPROVED"


def test_16_experiment_above_budget_is_rejected() -> None:
    decision = approve(event_study_spec(), [experiment(f"H{i}") for i in range(6)])
    assert (decision["decision"], decision["reason_code"]) == ("REJECTED", "RESEARCH_BUDGET_EXCEEDED")


def test_17_pairwise_candidate_limit() -> None:
    # the 200-ticker universe cap keeps pairs at 19,900 < 20,000 by default; a stricter policy shows the gate
    spec = zscore_spec(universe="TICKERS", tickers=[f"T{i:03d}" for i in range(50)])
    spec["calculations"] = [{"id": "corr", "method": "CORRELATION", "dataset": "prices", "columns": ["close"],
                             "params": [], "output_column": "corr", "provenance": "USER_EXPLICIT"}]
    spec["outputs"] = [{"name": "pairs", "grain": "ENTITY_PAIR", "calculations": ["corr"],
                        "pair_columns": ["a", "b"]}]
    spec["research"] = {"evidence_standard": "EXPLORATORY", "objective": "Which pairs co-move?"}
    assert pairwise_candidates(normalized(spec)) == 50 * 49 // 2
    assert approve(spec)["decision"] == "APPROVED"
    decision = approve(spec, policy=ResearchPolicy(max_pairwise_candidates=1000))
    assert (decision["decision"], decision["reason_code"]) == ("REPLAN_REQUIRED", "PAIRWISE_LIMIT_EXCEEDED")
    assert "1225 pairwise comparisons" in decision["message"]


def test_18_follow_up_limit() -> None:
    parent = {"exists": True, "hypothesis_id": "H1", "completed": True}
    research = {**event_study_spec()["research"], "followup_of": "spec_" + "1" * 24}
    ledger = [experiment("H1")] + [experiment("H1", "spec_" + "1" * 24) for _ in range(5)]
    decision = approve(event_study_spec(research), ledger[:5], parent,
                       ResearchPolicy(max_experiments=20))
    assert decision["decision"] == "APPROVED"
    decision = approve(event_study_spec(research), ledger, parent, ResearchPolicy(max_experiments=20))
    assert (decision["decision"], decision["reason_code"]) == ("REJECTED", "FOLLOWUP_LIMIT_EXCEEDED")
    not_done = approve(event_study_spec(research), ledger[:1], {**parent, "completed": False})
    assert not_done["reason_code"] == "FOLLOWUP_PARENT_NOT_COMPLETED"
    unrelated = approve(event_study_spec(research), ledger[:1], {**parent, "hypothesis_id": "H9"})
    assert unrelated["reason_code"] == "FOLLOWUP_HYPOTHESIS_MISMATCH"


def test_19_custom_formula_approval_path() -> None:
    spec = custom_ratio_spec()
    spec["research"] = {"evidence_standard": "DESCRIPTIVE", "objective": "Describe foreign accumulation."}
    decision = approve(spec)
    assert decision["decision"] == "APPROVED" and "calculation" in decision["constraints"]["required_validation"]


def test_20_custom_method_approval_path_and_its_limits() -> None:
    spec = custom_ratio_spec(expression=None)
    spec["research"] = {"evidence_standard": "EXPLORATORY", "objective": "Scan conditions", "candidates": 40}
    assert approve(spec)["decision"] == "APPROVED"
    spec["research"]["candidates"] = 500
    assert approve(spec)["reason_code"] == "CANDIDATE_LIMIT_EXCEEDED"
    spec["research"] = {"evidence_standard": "HISTORICAL_PATTERN", "objective": "o",
                        "hypothesis": {"id": "H1", "statement": "s"}}
    assert approve(spec)["reason_code"] == "MISSING_BASELINE_DEFINITION"  # a pattern claim needs an event study


def test_22_multiple_testing_counts_every_attempt_on_a_hypothesis() -> None:
    governor = approve(event_study_spec())
    context = research_context(normalized(event_study_spec()), governor,
                               [experiment("H1", candidates=3), experiment("H1")], POLICY)
    assert context["tests_on_hypothesis"] == 5  # 3 + 1 earlier, + this experiment


def test_23_budget_exhaustion_and_hypothesis_limit() -> None:
    decision = approve(event_study_spec(), [experiment(f"H{i}") for i in range(2, 6)])
    assert (decision["decision"], decision["reason_code"]) == ("REJECTED", "HYPOTHESIS_LIMIT_EXCEEDED")
    again = approve(event_study_spec(), [experiment("H1")])
    assert again["reason_code"] == "HYPOTHESIS_ALREADY_TESTED"


def test_predictive_claims_need_a_holdout_of_sufficient_length() -> None:
    research = {**event_study_spec()["research"], "evidence_standard": "PREDICTIVE"}
    assert approve(event_study_spec(research))["reason_code"] == "PREDICTIVE_REQUIRES_HOLDOUT"
    short = {**research, "holdout": {"start": "2026-06-20"}}
    assert approve(event_study_spec(short))["reason_code"] == "HOLDOUT_TOO_SHORT"
    good = {**research, "holdout": {"start": "2026-01-02"}}
    assert approve(event_study_spec(good))["decision"] == "APPROVED"


# ---------------------------------------------------------------- temporal safety (29)

def test_29_a_look_ahead_label_can_never_be_a_signal() -> None:
    spec = event_study_spec()
    spec["calculations"][2]["signal"] = [{"calculation": "fwd5", "op": ">", "value": 0.0}]
    assert "FUTURE_LABEL_IN_SIGNAL" in problems(spec)
    custom = event_study_spec()
    custom["calculations"].insert(2, {"id": "peek", "method": "CUSTOM", "dataset": "prices", "columns": ["close"],
                                      "params": [{"name": "lookahead_observations", "value": 1,
                                                  "provenance": "AI_INFERRED"}],
                                      "output_column": "peek", "formula": "close[t+1] > close[t]",
                                      "time_alignment": "uses t+1", "provenance": "AI_INFERRED"})
    custom["calculations"][3]["signal"] = [{"calculation": "peek", "op": ">", "value": 0.0}]
    assert "FUTURE_LABEL_IN_SIGNAL" in problems(custom)


# ---------------------------------------------------------------- evidence assessment (33-37)

def segment(events: int, delta: float, baseline: int = 500, censored: int = 0, se: float = 0.004) -> dict:
    return {"event_count": events, "mean": 0.01 + delta, "median": 0.01 + delta, "hit_rate": 0.55,
            "baseline_count": baseline, "baseline_mean": 0.01, "baseline_median": 0.01, "delta_mean": delta,
            "censored_count": censored, "overlapping_dropped": 0, "std": 0.03, "standard_error": se,
            "ci95": [0.0, 0.0], "delta_standard_error": se, "_t_df": max(1, events - 1),
            "delta_ci95": [delta - 2 * se, delta + 2 * se]}


def study_scope(**segments) -> list[dict]:
    return [{"event_study": {"segments": segments, "horizon": 5, "overlap_policy": "NON_OVERLAPPING",
                             "overlapping_events": 0, "coverage_pct": 100.0}}]


def context(standard: str, tests: int = 1, holdout: dict | None = None) -> dict:
    return {"evidence_standard": standard, "tests_on_hypothesis": tests, "holdout": holdout,
            "thresholds": {"min_events": 30, "min_baseline_observations": 100, "min_coverage_pct": 95}}


def test_33_partial_validation_gives_partially_supported() -> None:
    assessment = validator.assess(context("CALCULATION"), "PASS", "SCOPE_VERIFIED", [])
    assert assessment["decision"] == "PARTIALLY_SUPPORTED" and assessment["checks"]["calculation"] == "PARTIAL"


def test_34_a_simple_calculation_is_not_forced_through_statistical_tests() -> None:
    assessment = validator.assess(context("CALCULATION"), "PASS", "CALCULATION_VERIFIED", [])
    assert assessment["decision"] == "SUPPORTED" and assessment["evidence_level"] == "OBSERVATION"
    assert {assessment["checks"][k] for k in ("minimum_sample", "baseline", "multiple_testing",
                                               "temporal_holdout")} == {"NOT_APPLICABLE"}


def test_35_a_historical_pattern_needs_sample_and_baseline() -> None:
    few = validator.assess(context("HISTORICAL_PATTERN"), "PASS", "CALCULATION_VERIFIED",
                           study_scope(ALL=segment(12, 0.02)))
    assert few["decision"] == "INSUFFICIENT_EVIDENCE" and few["checks"]["minimum_sample"] == "FAIL"
    no_baseline = validator.assess(context("HISTORICAL_PATTERN"), "PASS", "CALCULATION_VERIFIED",
                                   study_scope(ALL=segment(80, 0.02, baseline=40)))
    assert no_baseline["decision"] == "INSUFFICIENT_EVIDENCE"
    strong = validator.assess(context("HISTORICAL_PATTERN"), "PASS", "CALCULATION_VERIFIED",
                              study_scope(ALL=segment(80, 0.02)))
    assert (strong["decision"], strong["evidence_level"]) == ("SUPPORTED", "PATTERN")
    searched = validator.assess(context("HISTORICAL_PATTERN", tests=500), "PASS", "CALCULATION_VERIFIED",
                                study_scope(ALL=segment(80, 0.02, se=0.0085)))
    assert searched["checks"]["multiple_testing"] == "PARTIAL" and searched["decision"] == "PARTIALLY_SUPPORTED"


def test_36_a_predictive_claim_needs_a_consistent_out_of_sample_result() -> None:
    holdout = {"start": "2026-01-02"}
    flipped = validator.assess(context("PREDICTIVE", holdout=holdout), "PASS", "CALCULATION_VERIFIED",
                               study_scope(ALL=segment(120, 0.01), IN_SAMPLE=segment(90, 0.02),
                                           OUT_OF_SAMPLE=segment(30, -0.01)))
    assert flipped["decision"] == "INSUFFICIENT_EVIDENCE" and flipped["checks"]["temporal_holdout"] == "FAIL"
    assert any("not describe the result as predictive" in c for c in flipped["reporting_constraints"])
    consistent = validator.assess(context("PREDICTIVE", holdout=holdout), "PASS", "CALCULATION_VERIFIED",
                                  study_scope(ALL=segment(120, 0.02), IN_SAMPLE=segment(90, 0.02),
                                              OUT_OF_SAMPLE=segment(30, 0.015)))
    assert (consistent["decision"], consistent["evidence_level"]) == ("SUPPORTED", "PREDICTIVE_SIGNAL")


def test_37_an_association_is_never_reported_as_causal() -> None:
    for standard in ("HISTORICAL_PATTERN", "PREDICTIVE", "EXPLORATORY"):
        assessment = validator.assess(context(standard, holdout={"start": "2026-01-02"}), "PASS",
                                      "CALCULATION_VERIFIED",
                                      study_scope(ALL=segment(80, 0.02), IN_SAMPLE=segment(60, 0.02),
                                                  OUT_OF_SAMPLE=segment(20, 0.02)))
        assert "Describe the result as a historical association, not causation." in \
            assessment["reporting_constraints"]
    exploratory = validator.assess(context("EXPLORATORY"), "PASS", "CALCULATION_VERIFIED",
                                   study_scope(ALL=segment(80, 0.02)))
    assert exploratory["decision"] == "PARTIALLY_SUPPORTED"  # exploration is never SUPPORTED


def test_failed_or_incomplete_validation_never_supports_a_claim() -> None:
    assert validator.assess(context("HISTORICAL_PATTERN"), "FAILED", "EXECUTION_ONLY", [])["decision"] == "INVALID"
    assert validator.assess(context("CALCULATION"), "INCOMPLETE", "EXECUTION_ONLY", [])["decision"] == \
        "INSUFFICIENT_EVIDENCE"


def test_research_block_is_part_of_the_canonical_spec_and_its_copy() -> None:
    spec = normalized(event_study_spec())
    assert copy.deepcopy(spec)["research"]["hypothesis"]["id"] == "H1"
