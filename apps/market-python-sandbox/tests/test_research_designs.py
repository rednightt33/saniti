"""Generic research designs (Research Governor) and profile X evidence (validator), beyond the event study.

The designs are topic-free: COMPARATIVE compares group means of a per-entity metric, ASSOCIATION evaluates a
correlation, PREDICTIVE_TEMPORAL needs a temporal holdout, EXPLORATORY_SEARCH declares its search space. A design
that makes several comparisons must declare them and adjust for them; physical partitions of one data plan are not
experiments.
"""
from __future__ import annotations

import copy
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))

import validator  # noqa: E402
from app.research_policy import ResearchPolicy, research_context, review  # noqa: E402
from app.spec import resolve_period  # noqa: E402
from conftest import requires_root  # noqa: E402
from test_two_path import (GROUPED, Q6, Q6_CODE, Q7, Q7_CODE, REF, ask, calc, contracts, executed,  # noqa: E402
                           grouped_prices, param, prepare, q6_spec, q7_spec, run, v2)

POLICY = ResearchPolicy()
HYPOTHESIS = {"id": "H1", "statement": "The groups differ."}


def research(spec: dict, **block) -> dict:
    spec = copy.deepcopy(spec)
    spec["analysis_type"] = "RESEARCH"
    spec["research"] = {"evidence_standard": "HISTORICAL_PATTERN", "objective": "Do the groups differ?",
                        "hypothesis": HYPOTHESIS, **block}
    return spec


def comparative(**block) -> dict:
    values = {"design_type": "COMPARATIVE", "primary_metric": "sector_volatility",
              "comparator": {"type": "GROUPS", "groups": ["Energy", "Technology"]}}
    values.update(block)
    return research(q6_spec(), **values)


def association(**block) -> dict:
    return research(q7_spec(), **{"design_type": "ASSOCIATION", "primary_metric": "correlation", **block})


def decide(spec: dict, experiments=None, parent=None) -> dict:
    canonical = v2(spec)
    return review(canonical, resolve_period(canonical["analysis_period"], REF), experiments or [], parent, POLICY)


def event_study_v2(**block) -> dict:
    spec = q7_spec()
    spec["inputs"][1]["columns"] = ["ticker", "date", "open", "close"]
    spec["calculations"] = [
        calc("z20", "ROLLING_ZSCORE", columns=["close"], params=[param("window", 20)]),
        calc("fwd5", "FORWARD_RETURN", columns=["close", "open"], params=[param("horizon", 5)]),
        calc("study", "EVENT_STUDY", upstream="fwd5",
             signal=[{"calculation": "z20", "op": "<", "value": -1.5, "provenance": "USER_EXPLICIT"}])]
    spec["outputs"] = [{"name": "summary", "grain": "SUMMARY", "coverage": "FULL", "calculations": ["study"]}]
    return research(spec, **{"design_type": "PREDICTIVE_TEMPORAL", "primary_metric": "study", **block})


# ---------------------------------------------------------------- Research Governor

def test_a_v2_research_claim_declares_its_design() -> None:
    decision = decide(research(q6_spec()))
    assert (decision["decision"], decision["reason_code"]) == ("REPLAN_REQUIRED", "RESEARCH_DESIGN_REQUIRED")


def test_a_non_event_study_design_is_approved_with_its_evidence_contract() -> None:
    decision = decide(comparative())
    assert decision["decision"] == "APPROVED", decision
    constraints = decision["constraints"]
    assert constraints["design_type"] == "COMPARATIVE" and constraints["comparisons"] == 1
    assert {"comparator", "uncertainty", "multiple_testing"} <= set(constraints["required_validation"])
    assert "min_group_observations" in constraints["evidence_thresholds"]
    assert v2(comparative())["research"]["observation_unit"] == "ENTITY"
    association_decision = decide(association())
    assert association_decision["decision"] == "APPROVED" and association_decision["constraints"]["comparisons"] == 1


@pytest.mark.parametrize(("block", "code"), [
    ({"primary_metric": "volatility"}, "PRIMARY_METRIC_INVALID"),        # a per-entity value, not a group mean
    ({"comparator": None}, "COMPARATOR_REQUIRED"),                        # a comparative claim needs a comparison
    ({"comparator": {"type": "GROUPS", "groups": ["Energy", "Technology", "Financials"]}}, "CANDIDATES_UNDERSTATED"),
    ({"comparator": {"type": "GROUPS", "groups": ["Energy", "Technology", "Financials"]}, "candidates": 3},
     "MULTIPLE_TESTING_POLICY_REQUIRED"),
])
def test_comparative_designs_need_a_group_mean_a_comparator_and_an_adjustment(block, code) -> None:
    decision = decide(comparative(**block))
    assert (decision["decision"], decision["reason_code"]) == ("REPLAN_REQUIRED", code)


def test_declared_comparisons_with_an_adjustment_are_approved() -> None:
    decision = decide(comparative(comparator={"type": "GROUPS", "groups": ["Energy", "Technology", "Financials"]},
                                  candidates=3, multiple_testing_policy="BONFERRONI"))
    assert decision["decision"] == "APPROVED" and decision["constraints"]["comparisons"] == 3


@pytest.mark.parametrize(("spec", "code"), [
    (lambda: association(primary_metric="daily_return"), "PRIMARY_METRIC_INVALID"),
    (lambda: comparative(design_type="EXPLORATORY_SEARCH"), "DESIGN_STANDARD_MISMATCH"),
    (lambda: {**comparative(), "research": {**comparative()["research"], "evidence_standard": "PREDICTIVE"}},
     "DESIGN_STANDARD_MISMATCH"),
    (lambda: {**comparative(design_type="EXPLORATORY_SEARCH"),
              "research": {**comparative(design_type="EXPLORATORY_SEARCH")["research"],
                           "evidence_standard": "EXPLORATORY"}}, "SEARCH_SPACE_REQUIRED"),
])
def test_a_design_must_fit_its_claim(spec, code) -> None:
    decision = decide(spec())
    assert (decision["decision"], decision["reason_code"]) == ("REPLAN_REQUIRED", code)


def test_a_predictive_design_without_a_temporal_holdout_is_rejected() -> None:
    spec = event_study_v2()
    spec["research"]["evidence_standard"] = "PREDICTIVE"
    decision = decide(spec)
    assert (decision["decision"], decision["reason_code"]) == ("REPLAN_REQUIRED", "PREDICTIVE_REQUIRES_HOLDOUT")
    spec["research"]["holdout"] = {"start": "2026-09-01"}
    assert decide(spec)["decision"] == "APPROVED"
    spec["research"]["evidence_standard"] = "HISTORICAL_PATTERN"
    assert decide(spec)["reason_code"] == "DESIGN_STANDARD_MISMATCH"  # a predictive design is a predictive claim


def test_no_fishing_a_second_look_is_an_explicit_budgeted_follow_up() -> None:
    parent = {"spec_id": "spec_" + "0" * 24, "research": {**comparative()["research"], "candidates": 1}}
    again = decide(comparative(), experiments=[parent])
    assert again["reason_code"] == "HYPOTHESIS_ALREADY_TESTED"
    follow = comparative(followup_of="spec_" + "0" * 24)
    assert decide(follow, [parent], {"exists": True, "hypothesis_id": "H1", "completed": False})["reason_code"] == \
        "FOLLOWUP_PARENT_NOT_COMPLETED"
    approved = decide(follow, [parent], {"exists": True, "hypothesis_id": "H1", "completed": True})
    assert approved["decision"] == "APPROVED"
    context = research_context(v2(follow), approved, [parent], POLICY)
    assert context["tests_on_hypothesis"] == 2 and context["design_type"] == "COMPARATIVE"


# ---------------------------------------------------------------- profile X statistics

def comparison_scope(samples: dict, comparator: dict | None = None) -> list[dict]:
    return [{"comparison": validator._comparison(samples, comparator or {"type": "GROUPS"})}]


def design_context(design: str, standard: str = "HISTORICAL_PATTERN", candidates: int = 1, tests: int = 1) -> dict:
    return {"evidence_standard": standard, "design_type": design, "candidates": candidates,
            "tests_on_hypothesis": tests, "thresholds": {"min_group_observations": 10,
                                                         "min_association_observations": 30}}


def draws(mean: float, n: int, seed: int) -> np.ndarray:
    return np.random.default_rng(seed).normal(mean, 1.0, n)


def test_a_clear_group_difference_is_supported_with_welch_intervals() -> None:
    assessment = validator.assess(design_context("COMPARATIVE"), "PASS", "CALCULATION_VERIFIED",
                                  comparison_scope({"A": draws(2.0, 25, 1), "B": draws(0.0, 25, 2)}))
    assert (assessment["decision"], assessment["evidence_level"]) == ("SUPPORTED", "PATTERN")
    row = assessment["statistics"]["comparisons"][0]
    assert row["n_a"] == row["n_b"] == 25 and row["ci95"][0] > 0
    assert "not causes" in assessment["reporting_constraints"][0]


def test_small_groups_cannot_support_a_difference() -> None:
    assessment = validator.assess(design_context("COMPARATIVE"), "PASS", "CALCULATION_VERIFIED",
                                  comparison_scope({"A": draws(2.0, 6, 1), "B": draws(0.0, 6, 2)}))
    assert assessment["decision"] == "INSUFFICIENT_EVIDENCE" and assessment["checks"]["minimum_sample"] == "FAIL"


def test_comparisons_counted_from_the_data_raise_the_adjustment() -> None:
    samples = {g: draws(m, 30, i) for i, (g, m) in enumerate((("A", 0.55), ("B", 0.0), ("C", 0.0), ("D", 0.0)))}
    declared_one = validator.assess(design_context("COMPARATIVE"), "PASS", "CALCULATION_VERIFIED",
                                    comparison_scope(samples))
    assert declared_one["statistics"]["tests_on_hypothesis"] == 6  # 4 groups -> 6 pairs, not the declared 1
    assert declared_one["checks"]["uncertainty"] == "PASS" and declared_one["checks"]["multiple_testing"] == "PARTIAL"
    assert declared_one["decision"] == "PARTIALLY_SUPPORTED"
    exploratory = validator.assess(design_context("COMPARATIVE", "EXPLORATORY"), "PASS", "CALCULATION_VERIFIED",
                                   comparison_scope({"A": draws(2.0, 25, 1), "B": draws(0.0, 25, 2)}))
    assert exploratory["decision"] == "PARTIALLY_SUPPORTED"  # exploration is never SUPPORTED


def test_an_association_needs_overlap_and_survives_the_adjustment() -> None:
    def scope(r: float, n: int, pairs: int = 1) -> list[dict]:
        return [{"association": {"method": "PEARSON", "unit": "GROUP_DATE",
                                 "pairs": [{"pair": [f"g{i}", "h"], "r": r, "n": n} for i in range(pairs)]}}]

    strong = validator.assess(design_context("ASSOCIATION"), "PASS", "CALCULATION_VERIFIED", scope(0.6, 80))
    assert strong["decision"] == "SUPPORTED" and strong["statistics"]["pairs"][0]["ci95"][0] > 0
    assert any("autocorrelated" in c for c in strong["reporting_constraints"])
    short = validator.assess(design_context("ASSOCIATION"), "PASS", "CALCULATION_VERIFIED", scope(0.6, 12))
    assert short["decision"] == "INSUFFICIENT_EVIDENCE"
    searched = validator.assess(design_context("ASSOCIATION"), "PASS", "CALCULATION_VERIFIED", scope(0.25, 80, 20))
    assert searched["checks"]["uncertainty"] == "PASS" and searched["checks"]["multiple_testing"] == "PARTIAL"


def test_a_design_without_recalculated_statistics_supports_nothing() -> None:
    for design in ("COMPARATIVE", "ASSOCIATION"):
        assessment = validator.assess(design_context(design), "PASS", "SCOPE_VERIFIED", [])
        assert assessment["decision"] == "INSUFFICIENT_EVIDENCE"


# ---------------------------------------------------------------- end to end (profile X through the service)

def prepare_partitioned(service, governor, review_body: dict, frames: dict, parts: int = 2) -> list[dict]:
    """The compiler's physical date partitions of one approved plan (lineage part i of n)."""
    stored = service.get_spec(review_body["spec_id"])
    inputs = []
    for name, entry in stored["data_plan"].items():
        window = entry["date_range"]
        frame = frames[name]
        if not window:
            ranges = [None]
        else:
            first, last = date.fromisoformat(window["from"]), date.fromisoformat(window["to"])
            cut = first + timedelta(days=(last - first).days // 2)
            ranges = [(first, cut), (cut + timedelta(days=1), last)][:parts]
        ids = []
        for index, bounds in enumerate(ranges, start=1):
            part = frame if bounds is None else frame[(pd.to_datetime(frame["date"]).dt.date >= bounds[0]) &
                                                      (pd.to_datetime(frame["date"]).dt.date <= bounds[1])]
            scope = executed(entry, (bounds[0].isoformat(), bounds[1].isoformat()) if bounds else None)
            ids.append(governor.add(part, source_table=entry["source_table"], source_contracts=contracts(scope),
                                    requested_from=bounds[0].isoformat() if bounds else None,
                                    requested_to=bounds[1].isoformat() if bounds else None,
                                    lineage={"spec_id": review_body["spec_id"], "spec_sha256": stored["spec_sha256"],
                                             "scope_sha256": stored["scope_sha256"],
                                             "data_plan_id": "plan_" + "1" * 24, "logical_input_name": name,
                                             "part_index": index, "part_count": len(ranges),
                                             "request_sha256": "2" * 64},
                                    executed_scope=scope))
        inputs.append({"name": name, "dataset_ids": ids, "duplicate_policy": "ERROR_ON_CONFLICT"})
    return inputs


Q6_RESEARCH = ("Apakah volatilitas harian (standar deviasi return harian) rata-rata saham sektor energi berbeda "
               "dengan sektor teknologi selama 3 bulan terakhir?")


@requires_root
def test_a_partitioned_comparative_experiment_is_one_experiment_assessed_by_profile_x(make_service, governor) -> None:
    service = make_service()
    spec = comparative()
    spec["question"] = Q6_RESEARCH
    spec["scope"]["predicates"][0]["user_text"] = "sektor energi berbeda dengan sektor teknologi"
    body = ask(service, spec, Q6_RESEARCH)
    assert body.get("spec_id") and body["validation_profile"] == "X_RESEARCH", body
    kept = GROUPED[GROUPED["Sector"].isin(["Energy", "Technology"])]
    prices = grouped_prices()
    frames = {"universe": kept[["Ticker", "Sector"]], "prices": prices[prices["ticker"].isin(kept["Ticker"])]}
    inputs = prepare_partitioned(service, governor, body, frames)
    assert len(next(i for i in inputs if i["name"] == "prices")["dataset_ids"]) == 2
    result = run(service, body, inputs, Q6_CODE)
    assert (result["validation_status"], result["validation_level"]) == ("PASS", "CALCULATION_VERIFIED"), \
        result["validation_evidence"]
    assessment = result["evidence_assessment"]
    assert assessment["claim_type"] == "HISTORICAL_PATTERN" and assessment["statistics"]["test"].startswith("Welch")
    groups = assessment["statistics"]["groups"]
    assert {g: v["n"] for g, v in groups.items()} == {"Energy": 4, "Technology": 4}
    # four entities per group is below the configured minimum: reported as insufficient, not as a finding
    assert assessment["decision"] == "INSUFFICIENT_EVIDENCE" and assessment["checks"]["minimum_sample"] == "FAIL"
    summary = service.run_summary("req")
    assert summary["budget"]["research"]["experiments"]["used"] == 1  # two partitions, one experiment


@requires_root
def test_an_association_experiment_on_group_series_reports_its_interval(make_service, governor) -> None:
    service = make_service()
    body = ask(service, association(), Q7)
    assert body.get("spec_id"), body
    frames = {"universe": GROUPED[["Ticker", "Sector", "Industry"]], "prices": grouped_prices()}
    result = run(service, body, prepare(service, governor, body, frames), Q7_CODE)
    assert result["validation_status"] == "PASS", result["validation_evidence"]
    statistics = result["evidence_assessment"]["statistics"]
    pair = statistics["pairs"][0]
    assert pair["pair"] == ["banks", "property"] and pair["n"] > 30 and len(pair["ci95"]) == 2
    assert result["evidence_assessment"]["decision"] in ("SUPPORTED", "PARTIALLY_SUPPORTED")
