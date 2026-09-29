"""research_governance/v2 (Multi-Angle Research): the angle budget separate from hypotheses, repeated methods allowed,
duplicate ids, questions and signatures refused, parameters bound to the method, budgets per angle and per plan,
multiple testing, follow-up semantics, and one method registry shared with the engines and market-ai-orc."""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

from app.research_governance import MultiAnglePolicy, check_request_v2, review_v2
from app.research_methods import METHODS, angle_signature, parameter_problems, registry

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))
import research_engines  # noqa: E402

POLICY = MultiAnglePolicy()


def angle(angle_id: str, method: str = "conditional_distribution", question: str | None = None, **overrides) -> dict:
    parameters = {k: None for k in ("thresholds", "threshold_operator", "lags", "primary_lag", "buckets", "groups",
                                    "comparison", "streak_lengths", "rolling_window", "baseline_mode",
                                    "correlation_method")}
    parameters.update({"conditional_distribution": {"baseline_mode": "COMPLEMENT"},
                       "threshold_sensitivity": {"thresholds": [1.0, 2.0], "threshold_operator": ">=",
                                                 "baseline_mode": "ALL"},
                       "quantile_ranking": {"buckets": 5},
                       "lead_lag": {"lags": [1, 2, 3], "primary_lag": 2, "correlation_method": "PEARSON"},
                       "cohort_comparison": {"groups": ["SMALL", "LARGE"], "comparison": "PAIRWISE"},
                       "streak_persistence": {"streak_lengths": [2, 3]}}.get(method, {}))
    parameters.update(overrides.pop("parameters", {}))
    value = {"angle_id": angle_id, "angle_question": question or f"Question of {angle_id}?", "method_id": method,
             "method_family": METHODS[method], "condition": "A fall of more than five percent.",
             "outcome": "Forward return over five days.", "baseline_or_comparator": "Every other day.",
             "expected_direction": "HIGHER", "outcome_horizon_periods": 5, "outcome_unit": "PERCENT",
             "min_effect": None, "parameters": parameters, "candidate_count": 1, "pairwise_comparisons": 0,
             "multiple_testing_policy": "NONE", "holdout_required": False, "minimum_sample": None,
             "followup_of_angle_id": None, "bundle_group_id": "g1", "angle_data_contract_sha256": "c" * 64}
    value.update(overrides)
    value["angle_signature"] = angle_signature(value)
    return value


def governance(angles: list[dict]) -> dict:
    return {"governance_version": "research_governance/v2", "plan_id": "rp_" + "a" * 24,
            "root_hypothesis_id": "foreign_accumulation", "root_hypothesis": "Foreign accumulation precedes gains.",
            "angles": angles, "angle_to_bundle_group": {a["angle_id"]: a["bundle_group_id"] for a in angles},
            "totals": {"candidates": sum(a["candidate_count"] for a in angles),
                       "pairwise_comparisons": sum(a["pairwise_comparisons"] for a in angles)},
            "hashes": {"plan_sha256": "p" * 64, "research_data_plan_sha256": "d" * 64, "spec_sha256s": ["s" * 64],
                       "draft_ids": ["draft_" + "0" * 24], "angle_data_contract_sha256s": {}}}


def codes(raw: dict) -> list[str]:
    return [p["code"] for p in check_request_v2(raw, POLICY)]


def test_three_angles_of_the_same_family_pass_and_share_the_root_hypothesis() -> None:
    angles = [angle("a1", question="Do falls recover in five days?"),
              angle("a2", question="Do falls recover in ten days?", outcome_horizon_periods=10),
              angle("a3", "threshold_sensitivity", question="Which fall size matters?", candidate_count=2,
                    multiple_testing_policy="HOLM")]
    raw = governance(angles)
    assert codes(raw) == []
    decision = review_v2(raw, [], POLICY)
    assert decision["decision"] == "APPROVED" and set(decision["constraints"]["angles"]) == {"a1", "a2", "a3"}
    assert decision["budget"]["angles"] == 3 and decision["constraints"]["root_hypothesis_id"] == \
        "foreign_accumulation"


@pytest.mark.parametrize("count", [1, 7])
def test_fewer_than_two_or_more_than_six_angles_fail(count: int) -> None:
    # the minimum became 2 on 2026-09-29 (user decision: do not force many angles; market-ai-orc may require more)
    angles = [angle(f"a{i}", question=f"Q{i}?", outcome_horizon_periods=i + 1) for i in range(count)]
    assert codes(governance(angles)) == ["ANGLE_COUNT_INVALID"]


def test_two_angles_pass() -> None:
    angles = [angle(f"a{i}", question=f"Q{i}?", outcome_horizon_periods=i + 1) for i in range(2)]
    assert "ANGLE_COUNT_INVALID" not in codes(governance(angles))


def test_duplicate_ids_questions_and_signatures_fail() -> None:
    base = [angle("a1", question="Same?"), angle("a2", question="Other?", outcome_horizon_periods=3),
            angle("a3", question="Third?", outcome_horizon_periods=4)]
    duplicate_id = copy.deepcopy(base)
    duplicate_id[1]["angle_id"] = "a1"
    assert "DUPLICATE_ANGLE_ID" in codes(governance(duplicate_id))
    duplicate_question = copy.deepcopy(base)
    duplicate_question[1] = angle("a2", question="  SAME? ", outcome_horizon_periods=3)
    assert "DUPLICATE_ANGLE_QUESTION" in codes(governance(duplicate_question))
    # an exact duplicate analytical question under another id and a reworded question with identical design
    twin = copy.deepcopy(base)
    twin[2] = angle("a3", question="Same?")
    assert {"DUPLICATE_ANGLE_QUESTION", "DUPLICATE_ANGLE_SIGNATURE"} <= set(codes(governance(twin)))
    forged = copy.deepcopy(base)
    forged[0]["angle_signature"] = "0" * 64
    assert "ANGLE_SIGNATURE_MISMATCH" in codes(governance(forged))


def test_parameters_are_bound_to_the_method() -> None:
    assert parameter_problems("lead_lag", {"lags": [1, 2], "primary_lag": 3, "correlation_method": "PEARSON"}, 2, 0) \
        == ["primary_lag must be one of lags"]
    assert parameter_problems("quantile_ranking", {"buckets": 5, "thresholds": [1.0]}, 1, 0) == \
        ["thresholds is not used by quantile_ranking; set it to null"]
    assert parameter_problems("threshold_sensitivity", {"thresholds": [1.0, 2.0, 3.0], "threshold_operator": ">=",
                                                        "baseline_mode": "ALL"}, 2, 0) == \
        ["candidate_count 2 is below the 3 candidates the parameters evaluate"]
    assert parameter_problems("cohort_comparison", {"groups": ["A", "B", "C"], "comparison": "PAIRWISE"}, 1, 2) == \
        ["pairwise_comparisons 2 is below the 3 comparisons the groups imply"]
    raw = governance([angle("a1"), angle("a2", "quantile_ranking", question="Rank?"),
                      angle("a3", "lead_lag", question="Lead?", candidate_count=3, multiple_testing_policy="NONE")])
    assert "MULTIPLE_TESTING_POLICY_REQUIRED" in codes(raw)


def test_budgets_per_angle_and_per_plan() -> None:
    big = [angle(f"a{i}", "threshold_sensitivity", question=f"Q{i}?", candidate_count=40,
                 multiple_testing_policy="BONFERRONI", outcome_horizon_periods=i + 1) for i in range(4)]
    assert "PLAN_CANDIDATE_LIMIT_EXCEEDED" in codes(governance(big))
    over = [angle("a1", "threshold_sensitivity", candidate_count=51, multiple_testing_policy="HOLM"),
            angle("a2", question="B?"), angle("a3", question="C?", outcome_horizon_periods=2)]
    assert "CANDIDATE_LIMIT_EXCEEDED" in codes(governance(over))
    raw = governance([angle("a1"), angle("a2", question="B?"), angle("a3", question="C?", outcome_horizon_periods=2)])
    raw["totals"]["candidates"] = 99
    assert "TOTALS_MISMATCH" in codes(raw)


def test_a_repeated_angle_needs_follow_up_semantics() -> None:
    first = governance([angle("a1"), angle("a2", question="B?"), angle("a3", question="C?",
                                                                     outcome_horizon_periods=2)])
    again = review_v2(first, [{"governance": first}], POLICY)
    assert again["decision"] == "REPLAN_REQUIRED" and again["reason_code"] == "ANGLE_ALREADY_RUN"
    renamed = governance([angle("a4"), angle("a5", question="B?"), angle("a6", question="C?",
                                                                       outcome_horizon_periods=2)])
    assert review_v2(renamed, [{"governance": first}], POLICY)["decision"] == "APPROVED"
    followup = governance([angle("a1", followup_of_angle_id="a1", outcome_horizon_periods=20),
                           angle("a7", question="D?"), angle("a8", question="E?", outcome_horizon_periods=2)])
    assert review_v2(followup, [{"governance": first}], POLICY)["decision"] == "APPROVED"
    orphan = governance([angle("a9", followup_of_angle_id="zz"), angle("b1", question="F?"),
                         angle("b2", question="G?", outcome_horizon_periods=2)])
    assert review_v2(orphan, [], POLICY)["reason_code"] == "FOLLOWUP_PARENT_NOT_FOUND"


def test_the_registry_matches_the_engines_and_the_signature_vector_is_pinned() -> None:
    assert registry() == research_engines.registry()
    assert set(METHODS) == set(research_engines.METHODS)
    vector = {"angle_question": "Do falls recover?", "method_id": "lead_lag", "condition": "A fall.",
              "outcome": "Return.", "baseline_or_comparator": "All days.", "outcome_horizon_periods": 5,
              "outcome_unit": "PERCENT", "expected_direction": "HIGHER",
              "parameters": {"lags": [3, 1, 2], "primary_lag": 2, "correlation_method": "PEARSON",
                             "thresholds": None}}
    # the same vector is pinned in market-ai-orc's tests/test_research_plan_v2.py
    assert angle_signature(vector) == "507cc31407e8ab03ae8e49c10f454bf2f9744ce9e6b510b018a27d7821b70955"
    assert angle_signature(vector) == angle_signature({**vector, "parameters": {**vector["parameters"],
                                                                                "lags": [1, 2, 3]}})
    assert angle_signature(vector) != angle_signature({**vector, "outcome_horizon_periods": 10})
