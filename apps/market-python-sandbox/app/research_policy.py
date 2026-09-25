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
NEEDS_EVENT_STUDY = {"HISTORICAL_PATTERN", "PREDICTIVE"}  # V1 specs without a declared design only
NEEDS_DESIGN = {"HISTORICAL_PATTERN", "PREDICTIVE", "EXPLORATORY"}
# Which claims each generic design can support, and what profile X checks for it. Nothing here is topic-specific.
DESIGN_STANDARDS = {
    "EVENT_STUDY": {"HISTORICAL_PATTERN", "EXPLORATORY", "DESCRIPTIVE"},
    "COMPARATIVE": {"HISTORICAL_PATTERN", "EXPLORATORY", "DESCRIPTIVE"},
    "ASSOCIATION": {"HISTORICAL_PATTERN", "EXPLORATORY", "DESCRIPTIVE"},
    "PREDICTIVE_TEMPORAL": {"PREDICTIVE"},
    "EXPLORATORY_SEARCH": {"EXPLORATORY"},
}
DESIGN_VALIDATION = {
    "EVENT_STUDY": REQUIRED_VALIDATION["HISTORICAL_PATTERN"],
    "COMPARATIVE": ["scope", "calculation", "coverage", "minimum_sample", "comparator", "uncertainty",
                    "multiple_testing"],
    "ASSOCIATION": ["scope", "calculation", "minimum_sample", "uncertainty", "multiple_testing"],
    "PREDICTIVE_TEMPORAL": REQUIRED_VALIDATION["PREDICTIVE"],
    "EXPLORATORY_SEARCH": REQUIRED_VALIDATION["EXPLORATORY"],
}


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
    min_group_observations: int = 10
    min_association_observations: int = 30

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


def design_of(spec: dict[str, Any]) -> str | None:
    """The declared design; a V1 spec without one that has an EVENT_STUDY is an event study (compatibility)."""
    research = spec["research"]
    if research.get("design_type"):
        return research["design_type"]
    if spec.get("spec_version") != "2.0" and any(c["method"] == "EVENT_STUDY" for c in spec["calculations"]):
        return "PREDICTIVE_TEMPORAL" if research["evidence_standard"] == "PREDICTIVE" else "EVENT_STUDY"
    return None


def comparisons(spec: dict[str, Any]) -> int | None:
    """How many statistical comparisons the design makes, when the spec alone determines it (None: from the data)."""
    research = spec["research"]
    design = design_of(spec)
    calcs = {c["id"]: c for c in spec["calculations"]}
    metric = calcs.get(research.get("primary_metric") or "")
    if design == "COMPARATIVE" and metric is not None:
        comparator = research.get("comparator") or {}
        groups = comparator.get("groups") or [s["label"] for s in metric.get("segments") or []]
        if not groups:
            return None
        k = len(groups)
        return k if comparator.get("type") == "ALL_OTHERS" else k * (k - 1) // 2
    if design == "ASSOCIATION" and metric is not None:
        if metric["method"] == "CORRELATION":
            return pairwise_candidates(spec) or None
        series = calcs.get(metric.get("input_calculation") or "") or {}
        k = len(series.get("segments") or [])
        return k * (k - 1) // 2 if k else None
    return 1 if design in ("EVENT_STUDY", "PREDICTIVE_TEMPORAL") else None


def _design_problem(spec: dict[str, Any], standard: str, design: str | None) -> tuple[str, str] | None:
    """(reason_code, message) when the declared design cannot support the claim; None when it can."""
    research = spec["research"]
    methods = {c["method"] for c in spec["calculations"]}
    calcs = {c["id"]: c for c in spec["calculations"]}
    if design is None:
        if spec.get("spec_version") == "2.0" and standard in NEEDS_DESIGN:
            return ("RESEARCH_DESIGN_REQUIRED", f"A {standard} experiment declares its design (research.design_type: "
                                                f"EVENT_STUDY, COMPARATIVE, ASSOCIATION, PREDICTIVE_TEMPORAL or "
                                                f"EXPLORATORY_SEARCH) and its primary_metric.")
        if standard in NEEDS_EVENT_STUDY:
            return ("MISSING_BASELINE_DEFINITION", f"A {standard} claim needs an outcome compared with a baseline: add "
                                                   f"an EVENT_STUDY calculation (signal, FORWARD_RETURN outcome, "
                                                   f"baseline), or lower the evidence standard to DESCRIPTIVE or "
                                                   f"EXPLORATORY.")
        return None
    if standard in NEEDS_DESIGN | {"DESCRIPTIVE"} and standard not in DESIGN_STANDARDS[design]:
        return ("DESIGN_STANDARD_MISMATCH", f"A {design} design cannot support a {standard} claim; a predictive claim "
                                            f"needs PREDICTIVE_TEMPORAL, a bounded search EXPLORATORY_SEARCH with "
                                            f"evidence_standard EXPLORATORY.")
    metric = calcs.get(research.get("primary_metric") or "")
    params = {p["name"]: p["value"] for p in (metric or {}).get("params", [])}
    if design in ("EVENT_STUDY", "PREDICTIVE_TEMPORAL") and "EVENT_STUDY" not in methods:
        return ("MISSING_BASELINE_DEFINITION", f"A {design} design needs an EVENT_STUDY calculation (signal, "
                                               f"FORWARD_RETURN outcome, baseline); it is the implemented evaluator of "
                                               f"temporal claims.")
    if design == "COMPARATIVE":
        if metric is None or metric["method"] != "GROUP_AGGREGATE" or params.get("function") != "AVG" or \
                params.get("per_date") or not any(metric["id"] in o["calculations"] and o["grain"] == "GROUP"
                                                  for o in spec["outputs"]):
            return ("PRIMARY_METRIC_INVALID", "A COMPARATIVE design compares group means: primary_metric names a "
                                              "GROUP_AGGREGATE AVG (not per_date) of a per-entity metric that a GROUP "
                                              "output lists.")
        if not research.get("comparator"):
            return ("COMPARATOR_REQUIRED", "A COMPARATIVE claim depends on a comparison: declare research.comparator "
                                           "(GROUPS or ALL_OTHERS).")
    if design == "ASSOCIATION" and (metric is None or metric["method"] not in ("CORRELATION", "GROUP_CORRELATION")):
        return ("PRIMARY_METRIC_INVALID", "An ASSOCIATION design names a CORRELATION or GROUP_CORRELATION "
                                          "calculation as primary_metric.")
    if design == "EXPLORATORY_SEARCH" and (research.get("candidates") or 1) < 2:
        return ("SEARCH_SPACE_REQUIRED", "An EXPLORATORY_SEARCH declares its search space: candidates = the number of "
                                         "conditions, lags or combinations it evaluates.")
    return None


def review(spec: dict[str, Any], resolved: dict[str, Any], experiments: list[dict[str, Any]],
           parent_status: dict[str, Any] | None, policy: ResearchPolicy) -> dict[str, Any]:
    """Decide whether this experiment may run. experiments: the run's approved research specs so far;
    parent_status: {"exists", "hypothesis_id", "completed"} of research.followup_of, if any."""
    research = spec["research"]
    standard = research["evidence_standard"]
    hypothesis = (research.get("hypothesis") or {}).get("id")
    counters = ledger(experiments)
    before = _budget(policy, counters)
    design = design_of(spec)

    if counters["experiments"] >= policy.max_experiments:
        return _decision("REJECTED", "RESEARCH_BUDGET_EXCEEDED",
                         f"This run has used all {policy.max_experiments} research experiments. Report what the "
                         f"completed experiments show.", before, None)
    if standard in NEEDS_HYPOTHESIS and not hypothesis:
        return _decision("REPLAN_REQUIRED", "HYPOTHESIS_REQUIRED",
                         f"A {standard} experiment states the hypothesis it tests (research.hypothesis).", before, None)
    problem = _design_problem(spec, standard, design)
    if problem:
        return _decision("REPLAN_REQUIRED", problem[0], problem[1], before, None)
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
    declared = research.get("design_type")  # V1 specs keep their earlier rules
    known = comparisons(spec) if declared else None
    if known and known > candidates:
        return _decision("REPLAN_REQUIRED", "CANDIDATES_UNDERSTATED",
                         f"The design makes {known} comparisons; declare research.candidates >= {known} so the "
                         f"multiple-testing adjustment covers all of them.", before, None)
    if declared and max(candidates, known or 1) > 1 and research.get("multiple_testing_policy") != "BONFERRONI":
        return _decision("REPLAN_REQUIRED", "MULTIPLE_TESTING_POLICY_REQUIRED",
                         "A design with more than one comparison declares multiple_testing_policy BONFERRONI.", before,
                         None)

    after_counters = {**counters, "experiments": counters["experiments"] + 1,
                      "hypotheses": {**counters["hypotheses"], **({hypothesis: 1} if hypothesis else {})}}
    required = DESIGN_VALIDATION[design] if design and standard in NEEDS_DESIGN else REQUIRED_VALIDATION[standard]
    constraints = {"required_validation": required, "design_type": design,
                   "primary_metric": research.get("primary_metric"), "comparisons": known,
                   "multiple_testing_policy": research.get("multiple_testing_policy"),
                   "evidence_thresholds": {"min_events": policy.min_events,
                                           "min_baseline_observations": policy.min_baseline_observations,
                                           "min_coverage_pct": policy.min_coverage_pct,
                                           "min_group_observations": policy.min_group_observations,
                                           "min_association_observations": policy.min_association_observations},
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
            "candidates": int(research.get("candidates") or 1), "design_type": governor["constraints"]["design_type"],
            "primary_metric": research.get("primary_metric"), "comparator": research.get("comparator"),
            "multiple_testing_policy": research.get("multiple_testing_policy"),
            "thresholds": governor["constraints"]["evidence_thresholds"],
            "required_validation": governor["constraints"]["required_validation"]}
