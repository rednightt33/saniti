"""Research Governor: deterministic pre-run approval of research experiments.

The model proposes; this module decides. A spec with a `research` block is an experiment of the
run identified by request_id (one market-ai-orc request). After the intent check approves the spec,
`review` compares it with the run's ledger (earlier approved research specs of the same request)
and the configured policy, and returns APPROVED (the spec_id becomes the reservation), REJECTED
(the research budget does not allow it), or REPLAN_REQUIRED (the experiment can be corrected).

`research_context` is what the validator needs after the run to assess the evidence: the claim
type, the thresholds, and how many tests the hypothesis has had (multiple testing).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

# What the post-run evidence gate checks for each evidence standard.
REQUIRED_VALIDATION = {
    "CALCULATION": ["scope", "calculation"],
    "SCREEN": ["scope", "calculation", "selection"],
    "DESCRIPTIVE": ["scope", "calculation", "coverage"],
    "HISTORICAL_PATTERN": ["scope", "calculation", "coverage", "minimum_sample", "baseline", "overlap", "censoring",
                           "uncertainty", "multiple_testing"],
    "EXPLORATORY": ["scope", "calculation", "search_budget", "multiple_testing"],
    "PREDICTIVE": ["scope", "calculation", "coverage", "minimum_sample", "baseline", "overlap", "censoring",
                   "uncertainty", "multiple_testing", "temporal_holdout"],
    "SCENARIO": ["scope", "calculation", "assumptions_disclosed"],
}
NEEDS_HYPOTHESIS = {"HISTORICAL_PATTERN", "PREDICTIVE"}
NEEDS_EVENT_STUDY = {"HISTORICAL_PATTERN", "PREDICTIVE"}


@dataclass(frozen=True)
class ResearchPolicy:
    max_hypotheses: int = 4
    max_experiments: int = 6
    max_followups_per_hypothesis: int = 5
    max_pairwise_candidates: int = 20_000
    max_candidates: int = 50
    min_events: int = 30
    min_baseline_observations: int = 100
    min_coverage_pct: int = 95
    min_holdout_pct: int = 20

    def public(self) -> dict[str, int]:
        return dict(self.__dict__)


def _decision(decision: str, code: str | None, message: str | None, before: dict[str, Any],
              after: dict[str, Any] | None, constraints: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"decision": decision, "reason_code": code, "message": message, "constraints": constraints or {},
            "budget_before": before, "budget_after_reservation": after or before}


def ledger(experiments: list[dict[str, Any]]) -> dict[str, Any]:
    """Counters over the run's approved research experiments (oldest first)."""
    hypotheses: dict[str, int] = {}
    followups: dict[str, int] = {}
    for item in experiments:
        research = item["research"]
        hypothesis = (research.get("hypothesis") or {}).get("id")
        if hypothesis:
            hypotheses[hypothesis] = hypotheses.get(hypothesis, 0) + 1
            if research.get("followup_of"):
                followups[hypothesis] = followups.get(hypothesis, 0) + 1
    return {"experiments": len(experiments), "hypotheses": hypotheses, "followups": followups}


def _budget(policy: ResearchPolicy, counters: dict[str, Any]) -> dict[str, Any]:
    return {"experiments_used": counters["experiments"],
            "experiments_remaining": max(0, policy.max_experiments - counters["experiments"]),
            "hypotheses_used": len(counters["hypotheses"]),
            "hypotheses_remaining": max(0, policy.max_hypotheses - len(counters["hypotheses"]))}


def pairwise_candidates(spec: dict[str, Any]) -> int:
    """Entity pairs an ENTITY_PAIR output evaluates (n choose 2 of the TICKERS universe)."""
    if not any(o["grain"] == "ENTITY_PAIR" for o in spec["outputs"]):
        return 0
    n = len(spec["universe"].get("tickers") or [])
    return n * (n - 1) // 2


def review(spec: dict[str, Any], resolved: dict[str, Any], experiments: list[dict[str, Any]],
           parent_status: dict[str, Any] | None, policy: ResearchPolicy) -> dict[str, Any]:
    """Decide whether this experiment may run. experiments: the run's approved research specs so far;
    parent_status: {"exists", "hypothesis_id", "completed"} of research.followup_of, if any."""
    research = spec["research"]
    standard = research["evidence_standard"]
    hypothesis = (research.get("hypothesis") or {}).get("id")
    counters = ledger(experiments)
    before = _budget(policy, counters)
    methods = {c["method"] for c in spec["calculations"]}

    if counters["experiments"] >= policy.max_experiments:
        return _decision("REJECTED", "RESEARCH_BUDGET_EXCEEDED",
                         f"This run has used all {policy.max_experiments} research experiments. Report what the "
                         f"completed experiments show.", before, None)
    if standard in NEEDS_HYPOTHESIS and not hypothesis:
        return _decision("REPLAN_REQUIRED", "HYPOTHESIS_REQUIRED",
                         f"A {standard} experiment states the hypothesis it tests (research.hypothesis).", before, None)
    if standard in NEEDS_EVENT_STUDY and "EVENT_STUDY" not in methods:
        return _decision("REPLAN_REQUIRED", "MISSING_BASELINE_DEFINITION",
                         f"A {standard} claim needs an outcome compared with a baseline: add an EVENT_STUDY calculation "
                         f"(signal, FORWARD_RETURN outcome, baseline), or lower the evidence standard to DESCRIPTIVE "
                         f"or EXPLORATORY.", before, None)
    if standard == "PREDICTIVE":
        holdout = research.get("holdout")
        if not holdout:
            return _decision("REPLAN_REQUIRED", "PREDICTIVE_REQUIRES_HOLDOUT",
                             "A predictive claim needs a temporal holdout (research.holdout.start inside the analysis "
                             "period) evaluated out of sample.", before, None)
        start, end = resolved.get("start"), resolved.get("end")
        if start and end:
            first, last, cut = date.fromisoformat(start), date.fromisoformat(end), date.fromisoformat(holdout["start"])
            span = (last - first).days or 1
            share = 100.0 * ((last - cut).days + 1) / (span + 1)
            if not first < cut <= last:
                return _decision("REPLAN_REQUIRED", "HOLDOUT_OUTSIDE_PERIOD",
                                 f"The holdout start {cut} must lie inside the analysis period ({first} .. {last}).",
                                 before, None)
            if share < policy.min_holdout_pct:
                return _decision("REPLAN_REQUIRED", "HOLDOUT_TOO_SHORT",
                                 f"The holdout covers {share:.0f}% of the period; at least {policy.min_holdout_pct}% "
                                 f"is required.", before, None)
    followup = research.get("followup_of")
    if followup:
        if not parent_status or not parent_status.get("exists"):
            return _decision("REPLAN_REQUIRED", "FOLLOWUP_PARENT_NOT_FOUND",
                             "followup_of must name an approved research spec of this run.", before, None)
        if parent_status.get("hypothesis_id") != hypothesis:
            return _decision("REPLAN_REQUIRED", "FOLLOWUP_HYPOTHESIS_MISMATCH",
                             "A follow-up tests the same hypothesis as its parent; a new question is a new "
                             "hypothesis.", before, None)
        if not parent_status.get("completed"):
            return _decision("REPLAN_REQUIRED", "FOLLOWUP_PARENT_NOT_COMPLETED",
                             "A follow-up is justified only by a completed parent analysis; run the parent first.",
                             before, None)
        if counters["followups"].get(hypothesis, 0) >= policy.max_followups_per_hypothesis:
            return _decision("REJECTED", "FOLLOWUP_LIMIT_EXCEEDED",
                             f"Hypothesis {hypothesis} has used its {policy.max_followups_per_hypothesis} follow-ups.",
                             before, None)
    elif hypothesis and hypothesis not in counters["hypotheses"] \
            and len(counters["hypotheses"]) >= policy.max_hypotheses:
        return _decision("REJECTED", "HYPOTHESIS_LIMIT_EXCEEDED",
                         f"This run has tested {policy.max_hypotheses} hypotheses, the configured maximum.", before,
                         None)
    elif hypothesis and hypothesis in counters["hypotheses"]:
        return _decision("REPLAN_REQUIRED", "HYPOTHESIS_ALREADY_TESTED",
                         f"Hypothesis {hypothesis} already has an experiment; a further experiment on it is a "
                         f"follow-up (research.followup_of).", before, None)
    pairs = pairwise_candidates(spec)
    if pairs > policy.max_pairwise_candidates:
        return _decision("REPLAN_REQUIRED", "PAIRWISE_LIMIT_EXCEEDED",
                         f"Requested {pairs} pairwise comparisons; the configured maximum is "
                         f"{policy.max_pairwise_candidates}.", before, None)
    candidates = research.get("candidates") or 1
    if candidates > policy.max_candidates:
        return _decision("REPLAN_REQUIRED", "CANDIDATE_LIMIT_EXCEEDED",
                         f"The experiment evaluates {candidates} candidate conditions; the configured maximum per "
                         f"experiment is {policy.max_candidates}.", before, None)

    after_counters = {**counters, "experiments": counters["experiments"] + 1,
                      "hypotheses": {**counters["hypotheses"], **({hypothesis: 1} if hypothesis else {})}}
    constraints = {"required_validation": REQUIRED_VALIDATION[standard],
                   "evidence_thresholds": {"min_events": policy.min_events,
                                           "min_baseline_observations": policy.min_baseline_observations,
                                           "min_coverage_pct": policy.min_coverage_pct},
                   "pairwise_candidates": pairs, "candidates": candidates}
    return _decision("APPROVED", None, None, before, _budget(policy, after_counters), constraints)


def research_context(spec: dict[str, Any], governor: dict[str, Any], experiments: list[dict[str, Any]],
                     policy: ResearchPolicy) -> dict[str, Any]:
    """Frozen at approval: what the post-run evidence assessment needs."""
    research = spec["research"]
    hypothesis = (research.get("hypothesis") or {}).get("id")
    earlier = [e for e in experiments if (e["research"].get("hypothesis") or {}).get("id") == hypothesis] \
        if hypothesis else []
    tests = sum(int(e["research"].get("candidates") or 1) for e in earlier) + int(research.get("candidates") or 1)
    return {"evidence_standard": research["evidence_standard"], "hypothesis_id": hypothesis,
            "followup_of": research.get("followup_of"), "method_ref": research.get("method_ref"),
            "holdout": research.get("holdout"), "tests_on_hypothesis": tests,
            "thresholds": governor["constraints"]["evidence_thresholds"],
            "required_validation": governor["constraints"]["required_validation"]}
