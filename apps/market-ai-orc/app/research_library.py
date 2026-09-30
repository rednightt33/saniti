"""Multi-Angle Research: the research library, the model-facing description of the eight methods (C07, 2026-09-29).

This file is byte-identical in market-python-sandbox and market-ai-orc (app/research_library.py); a test in each app
compares the two when both are present. The sandbox reports LIBRARY_SHA256 in its multi_angle_research capability;
database migration 20260930_001 writes one row of public."AI_research_library" per method from LIBRARY; market-ai-orc
serves those rows to the model (get_research_library) and enables multi-angle research only when the table, the
sandbox and this file carry the same hash.

It describes; it does not compute. The engines (runtime/research_engines.py), the recomputation by the harness and the
decision rules (research_engines.decide) stay in code, and a new row does not create a method.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

LIBRARY_VERSION = 1
ENGINE_VERSION = 1

COMMON_REQUIREMENTS = [
    "One row per entity and date (DUPLICATE_ENTITY_DATE otherwise).",
    "Declarative form: every role is an expression over the columns of one data request of the angle's contract; a "
    "forward return may name another contract request that holds the price column.",
    "A forward-return outcome needs a numeric price-level column and a future buffer of at least the horizon; rows "
    "without a later value are censored.",
    "A return outcome (PERCENT or DECIMAL) is never a price level or a trailing return column (OUTCOME_NOT_APPROVED).",
    "The effective sample counts dates at least one horizon apart, so overlapping outcomes are not counted twice.",
]
DECISION_RULES = "research_engines.decide v1: MULTI_ANGLE_RESEARCH.md section 4"


def _role(role: str, kind: str, meaning: str, required: bool = True) -> dict[str, Any]:
    return {"role": role, "type": kind, "required": required, "meaning": meaning}


def _param(name: str, rule: str) -> dict[str, str]:
    return {"name": name, "rule": rule}


OUTCOME = _role("outcome", "NUMBER", "The measured result, normally {'forward_return': '<price column>'} over the "
                                     "approved horizon.")
BASELINE = _param("baseline_mode", "COMPLEMENT (rows without the condition) or ALL (every row).")
GROUPS = [_param("groups", "2 to 12 short labels (at most 60 characters), in the order the hypothesis reads."),
          _param("comparison", "PAIRWISE, VS_REST or FIRST_VS_OTHERS; the implied pairwise comparisons must be "
                               "declared in pairwise_comparisons.")]
CORRELATION = _param("correlation_method", "PEARSON or SPEARMAN.")

LIBRARY: list[dict[str, Any]] = [
    {"method_id": "conditional_distribution", "method_family": "CONDITIONAL_OUTCOME",
     "question_shape": "After a condition holds, is the outcome different from the baseline?",
     "input_roles": [_role("condition", "BOOLEAN", "True on the rows where the condition holds (past values only)."),
                     OUTCOME],
     "required_parameters": [BASELINE], "optional_parameters": [],
     "data_requirements": {"entity_column": "OPTIONAL", "label": None, "outcome": "FORWARD_RETURN",
                           "min_entities_per_date": None, "notes": []},
     "sample_unit": "DATES", "secondary_checks": [],
     "interpretation": "The mean outcome after the condition minus the baseline mean, with a 95% interval from the "
                       "spread of per-date means, and the difference in the share of positive outcomes.",
     "misuse_warning": "A historical association only, not a cause or a prediction; a rare condition gives an "
                       "anecdotal sample.",
     "example_question": "Do bank stocks that fall more than 5% in a day return more over the next 5 days than on "
                         "other days?"},
    {"method_id": "threshold_sensitivity", "method_family": "CONDITIONAL_OUTCOME",
     "question_shape": "Does the effect depend on how large the signal is (several thresholds)?",
     "input_roles": [_role("signal", "NUMBER", "The value compared with each approved threshold."), OUTCOME],
     "required_parameters": [_param("thresholds", "1 to 20 distinct numbers in the signal's own unit."),
                             _param("threshold_operator", ">= or <=, applied as signal operator threshold."),
                             BASELINE],
     "optional_parameters": [],
     "data_requirements": {"entity_column": "OPTIONAL", "label": None, "outcome": "FORWARD_RETURN",
                           "min_entities_per_date": None,
                           "notes": ["Every threshold is one comparison: more than one needs a multiple-testing "
                                     "policy other than NONE."]},
     "sample_unit": "DATES", "secondary_checks": [],
     "interpretation": "The difference from the baseline at every threshold, corrected for multiple testing; the "
                       "reported candidate is the most significant one in the expected direction.",
     "misuse_warning": "Trying many thresholds and keeping the best one overstates the effect; read the corrected "
                       "interval.",
     "example_question": "Is the 5-day rebound after a daily fall different for falls of 3%, 5%, 7% and 10%?"},
    {"method_id": "streak_persistence", "method_family": "PERSISTENCE",
     "question_shape": "After a state has held for k observations in a row, how often does it continue?",
     "input_roles": [_role("state", "BOOLEAN", "True while the state holds, per entity in date order.")],
     "required_parameters": [_param("streak_lengths", "1 to 10 distinct integers from 1 to 20.")],
     "optional_parameters": [],
     "data_requirements": {"entity_column": "OPTIONAL", "label": None, "outcome": "STATE_CONTINUATION",
                           "min_entities_per_date": None,
                           "notes": ["The outcome is whether the state stays true over the next horizon observations; "
                                     "no return is measured. For the return after a streak use "
                                     "conditional_distribution with the streak as its condition.",
                                     "Needs consecutive observations per entity."]},
     "sample_unit": "DATES", "secondary_checks": [],
     "interpretation": "The continuation rate after streaks of at least k against the base rate of continuation, "
                       "with the distribution of streak lengths.",
     "misuse_warning": "Says nothing about returns; overlapping streaks of the same entity are not independent.",
     "example_question": "After three up days in a row, how often does the next day rise too?"},
    {"method_id": "regime_comparison", "method_family": "GROUP_COMPARISON",
     "question_shape": "Is the outcome different between market regimes (a label of the date)?",
     "input_roles": [_role("group", "LABEL", "The regime label; the same for every entity on a date."), OUTCOME],
     "required_parameters": GROUPS, "optional_parameters": [],
     "data_requirements": {"entity_column": "OPTIONAL", "label": "CONSTANT_PER_DATE", "outcome": "FORWARD_RETURN",
                           "min_entities_per_date": None,
                           "notes": ["A label that differs between stocks on the same date is not a regime "
                                     "(REGIME_NOT_CONSTANT); use cohort_comparison or quantile_ranking for it.",
                                     "Only the approved labels may appear (UNDECLARED_GROUP)."]},
     "sample_unit": "DATES", "secondary_checks": [],
     "interpretation": "Differences of the per-date mean outcome between regimes, corrected for the comparisons.",
     "misuse_warning": "Regimes chosen after looking at the data, or years used as regimes, describe history only.",
     "example_question": "Is the 10-day return different when the market is above or below its 26-day average?"},
    {"method_id": "cohort_comparison", "method_family": "GROUP_COMPARISON",
     "question_shape": "Is the outcome different between groups of entities (a fixed label per entity)?",
     "input_roles": [_role("group", "LABEL", "The cohort label; one label per entity for the whole input."), OUTCOME],
     "required_parameters": GROUPS, "optional_parameters": [],
     "data_requirements": {"entity_column": "REQUIRED", "label": "CONSTANT_PER_ENTITY", "outcome": "FORWARD_RETURN",
                           "min_entities_per_date": None,
                           "notes": ["An entity that changes label is refused (COHORT_NOT_CONSTANT).",
                                     "Each entity's mean outcome is one observation: the sample is the number of "
                                     "entities."]},
     "sample_unit": "ENTITIES", "secondary_checks": [],
     "interpretation": "Differences of the per-entity mean outcome between cohorts (Welch), corrected for the "
                       "comparisons.",
     "misuse_warning": "Few entities per cohort give a weak test; current-state labels (sector) are applied to the "
                       "whole history.",
     "example_question": "After a 60-day drawdown above 30%, is the 20-day return different for energy, basic "
                         "materials and financial stocks?"},
    {"method_id": "quantile_ranking", "method_family": "QUANTILE_RANKING",
     "question_shape": "On the same date, do entities with a higher signal have a higher outcome?",
     "input_roles": [_role("signal", "NUMBER", "The value that ranks the entities on each date."), OUTCOME],
     "required_parameters": [_param("buckets", "An integer from 2 to 10 (equal-count groups per date).")],
     "optional_parameters": [],
     "data_requirements": {"entity_column": "REQUIRED", "label": None, "outcome": "FORWARD_RETURN",
                           "min_entities_per_date": "buckets",
                           "notes": ["Dates with fewer entities than buckets are skipped."]},
     "sample_unit": "DATES", "secondary_checks": ["monotonicity"],
     "interpretation": "The mean top-minus-bottom spread per date, the monotonicity of the bucket means (must pass for "
                       "SUPPORTED) and the mean rank correlation (IC).",
     "misuse_warning": "Needs a cross-section: one or two stocks cannot be ranked.",
     "example_question": "Do industrial stocks in the highest volume-ratio quintile return more over 10 days than the "
                         "lowest?"},
    {"method_id": "lead_lag", "method_family": "TEMPORAL_DEPENDENCY",
     "question_shape": "Is the leader today correlated with the follower k observations later?",
     "input_roles": [_role("leader", "NUMBER", "The earlier series."),
                     _role("follower", "NUMBER", "The later series, normally a forward return.")],
     "required_parameters": [_param("lags", "1 to 20 distinct integers from 0 to 260."),
                             _param("primary_lag", "One of lags: the predeclared lag reported as primary."),
                             CORRELATION],
     "optional_parameters": [],
     "data_requirements": {"entity_column": "OPTIONAL", "label": None, "outcome": "FORWARD_RETURN",
                           "min_entities_per_date": None,
                           "notes": ["A panel is reduced to per-date means (one series).",
                                     "Needs more dates than the largest lag."]},
     "sample_unit": "DATES_AUTOCORRELATION_ADJUSTED", "secondary_checks": [],
     "interpretation": "The correlation at every lag (the lag curve), the predeclared lag as primary, with an "
                       "effective sample reduced for autocorrelation.",
     "misuse_warning": "A correlation is not a cause; several lags need a multiple-testing policy.",
     "example_question": "Does daily foreign net buying of large banks lead their returns 1 to 5 days later?"},
    {"method_id": "correlation_dependency", "method_family": "TEMPORAL_DEPENDENCY",
     "question_shape": "How strong is the relation between two series, is it stable, and does it change under a "
                       "condition?",
     "input_roles": [_role("leader", "NUMBER", "The first series."),
                     _role("follower", "NUMBER", "The second series, normally a forward return."),
                     _role("condition", "BOOLEAN", "Optional: the relation when it holds against when it does not.",
                           required=False)],
     "required_parameters": [CORRELATION],
     "optional_parameters": [_param("primary_lag", "An integer from 0 to 260 (default 0)."),
                             _param("rolling_window", "An integer from 5 to 260 for a rolling correlation.")],
     "data_requirements": {"entity_column": "OPTIONAL", "label": None, "outcome": "FORWARD_RETURN",
                           "min_entities_per_date": None,
                           "notes": ["A panel is reduced to per-date means; a date's condition holds only when it "
                                     "holds for every entity that date."]},
     "sample_unit": "DATES_AUTOCORRELATION_ADJUSTED", "secondary_checks": [],
     "interpretation": "The correlation at the lag, a rolling correlation and, with a condition, the difference "
                       "between the two conditional correlations.",
     "misuse_warning": "Averaging a panel into one series hides differences between entities.",
     "example_question": "How strong is the link between the change in 20-day volatility and the next 20-day return "
                         "of healthcare stocks?"},
]


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def rows() -> list[dict[str, Any]]:
    """One row per method, as public."AI_research_library" holds it."""
    return [{**method, "engine_version": ENGINE_VERSION, "library_version": LIBRARY_VERSION,
             "common_requirements": COMMON_REQUIREMENTS, "decision_rules_ref": DECISION_RULES}
            for method in sorted(LIBRARY, key=lambda m: m["method_id"])]


def library_sha256() -> str:
    return hashlib.sha256(_canonical({"library_version": LIBRARY_VERSION, "engine_version": ENGINE_VERSION,
                                      "methods": rows()})).hexdigest()


LIBRARY_SHA256 = library_sha256()


def by_method() -> dict[str, dict[str, Any]]:
    return {row["method_id"]: row for row in rows()}


def forward_return_role(method_id: str) -> str | None:
    """The role that carries a forward-return outcome (outcome or follower), or None (streak_persistence)."""
    method = by_method().get(method_id) or {}
    if (method.get("data_requirements") or {}).get("outcome") != "FORWARD_RETURN":
        return None
    return "follower" if any(r["role"] == "follower" for r in method.get("input_roles") or []) else "outcome"
