"""Research Governor for DataNeedSpec research runs (mode RESEARCH).

A research data need carries a companion ResearchGovernanceRequest. It declares what the experiment will search and
how it will guard against false discovery, never how it computes anything: there is no formula, method enum, design
enum or output grain, so a new formula is never refused because the backend has no implementation of it. The optional
condition, outcome and baseline are plain-language declarations (market-ai-orc binds them to the user's approved
Research Plan); they are validated as bounded text, recorded and returned, never matched against the analysis code.

The governor decides, deterministically and before any data is extracted, whether the experiment fits the run's
budgets: experiments, hypotheses, follow-ups, candidates, pairwise comparisons, revisions (retries), a declared
multiple-testing policy when more than one comparison is made, a holdout that is a declared time range, a minimum
sample at or above policy, and the compute budget the sandbox session will receive. It answers APPROVED,
REPLAN_REQUIRED or REJECTED with a reason code. It never validates Python code, recalculates results, or assesses
evidence: the backend does not verify calculations in this architecture.

Revisions of one request group are one experiment: a later revision (for example with more history) reuses the
reservation of its approved predecessor as long as the hypothesis is unchanged.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

HYPOTHESIS_ID = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
GROUP_ID = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
POLICIES = ("NONE", "BONFERRONI", "HOLM", "BENJAMINI_HOCHBERG")
SAMPLE_UNITS = ("EVENTS", "OBSERVATIONS", "ENTITIES")
DECLARATIONS = ("condition", "outcome", "baseline")
FIELDS = {"hypothesis_id", "hypothesis", "objective", "candidate_count", "pairwise_comparisons", "holdout",
          "minimum_sample", "multiple_testing_policy", "followup_of", *DECLARATIONS}
# The declarations are optional (absent or null) so a request without them is unchanged.
NULLABLE = {"holdout", "minimum_sample", "followup_of", *DECLARATIONS}


@dataclass(frozen=True)
class GovernancePolicy:
    max_experiments: int = 6
    max_hypotheses: int = 4
    max_followups_per_hypothesis: int = 5
    max_candidates: int = 50
    max_pairwise_comparisons: int = 20_000
    max_revisions_per_group: int = 6
    min_sample: dict[str, int] | None = None
    compute_seconds_per_experiment: int = 600

    def minimum(self, unit: str) -> int:
        defaults = {"EVENTS": 30, "OBSERVATIONS": 100, "ENTITIES": 10}
        return (self.min_sample or defaults).get(unit, defaults[unit])

    def public(self) -> dict[str, Any]:
        return {"max_experiments": self.max_experiments, "max_hypotheses": self.max_hypotheses,
                "max_followups_per_hypothesis": self.max_followups_per_hypothesis,
                "max_candidates": self.max_candidates, "max_pairwise_comparisons": self.max_pairwise_comparisons,
                "max_revisions_per_group": self.max_revisions_per_group,
                "minimum_sample": {u: self.minimum(u) for u in SAMPLE_UNITS},
                "compute_seconds_per_experiment": self.compute_seconds_per_experiment}


def check_request(raw: Any) -> list[dict[str, Any]]:
    """Structural problems of a ResearchGovernanceRequest, as DataNeedValidator issues (data_request_id None)."""
    problems: list[dict[str, Any]] = []

    def add(code: str, path: str, value: Any) -> None:
        problems.append({"data_request_id": None, "code": code, "field_path": f"research_governance{path}",
                         "rejected_value": value if not isinstance(value, (dict, list)) else str(value)[:200]})

    if not isinstance(raw, dict):
        add("INVALID_FIELD_TYPE", "", raw)
        return problems
    for key in raw:
        if key not in FIELDS:
            add("UNKNOWN_FIELD", f".{key}", raw[key])
    for key in sorted(FIELDS - NULLABLE):
        if key not in raw:
            add("MISSING_REQUIRED_FIELD", f".{key}", None)
    if not isinstance(raw.get("hypothesis_id"), str) or not HYPOTHESIS_ID.fullmatch(raw["hypothesis_id"]):
        add("INVALID_FIELD_VALUE", ".hypothesis_id", raw.get("hypothesis_id"))
    for key in ("hypothesis", "objective"):
        value = raw.get(key)
        if not isinstance(value, str) or not value.strip() or len(value) > 1000:
            add("INVALID_FIELD_VALUE", f".{key}", value)
    for key in DECLARATIONS:
        value = raw.get(key)
        if value is not None and (not isinstance(value, str) or not value.strip() or len(value) > 1000):
            add("INVALID_FIELD_VALUE", f".{key}", value)
    for key, low in (("candidate_count", 1), ("pairwise_comparisons", 0)):
        value = raw.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < low:
            add("INVALID_FIELD_VALUE", f".{key}", value)
    if raw.get("multiple_testing_policy") not in POLICIES:
        add("INVALID_FIELD_VALUE", ".multiple_testing_policy", raw.get("multiple_testing_policy"))
    holdout = raw.get("holdout")
    if holdout is not None and (not isinstance(holdout, dict) or set(holdout) != {"data_request_id", "range_id"}
                                or not all(isinstance(holdout[k], str) for k in holdout)):
        add("INVALID_FIELD_VALUE", ".holdout", holdout)
    sample = raw.get("minimum_sample")
    if sample is not None and (not isinstance(sample, dict) or set(sample) != {"value", "unit"}
                               or sample.get("unit") not in SAMPLE_UNITS or isinstance(sample.get("value"), bool)
                               or not isinstance(sample.get("value"), int) or sample["value"] < 1):
        add("INVALID_FIELD_VALUE", ".minimum_sample", sample)
    followup = raw.get("followup_of")
    if followup is not None and (not isinstance(followup, str) or not GROUP_ID.fullmatch(followup)):
        add("INVALID_FIELD_VALUE", ".followup_of", followup)
    return problems


def _decision(decision: str, code: str | None, message: str | None, budget: dict[str, Any],
              constraints: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"decision": decision, "reason_code": code, "message": message, "budget": budget,
            "constraints": constraints or {}}


def review(governance: dict[str, Any], spec: dict[str, Any], history: list[dict[str, Any]],
           revisions_in_group: int, policy: GovernancePolicy) -> dict[str, Any]:
    """history: the run's earlier APPROVED research data needs, each {request_group_id, revision, governance}.
    revisions_in_group: how many revisions of this request group were submitted before this one."""
    group = spec["request_group_id"]
    hypothesis = governance["hypothesis_id"]
    groups: dict[str, str] = {}
    followups: dict[str, int] = {}
    for item in history:
        if item["request_group_id"] not in groups:
            groups[item["request_group_id"]] = item["governance"]["hypothesis_id"]
            if item["governance"].get("followup_of"):
                h = item["governance"]["hypothesis_id"]
                followups[h] = followups.get(h, 0) + 1
    hypotheses = set(groups.values())
    budget = {"experiments_used": len(groups), "experiments_limit": policy.max_experiments,
              "hypotheses_used": len(hypotheses), "hypotheses_limit": policy.max_hypotheses,
              "revisions_used_in_group": revisions_in_group, "revisions_limit": policy.max_revisions_per_group}

    if revisions_in_group >= policy.max_revisions_per_group:
        return _decision("REJECTED", "RETRY_BUDGET_EXCEEDED",
                         f"Request group {group} has used its {policy.max_revisions_per_group} revisions.", budget)
    if governance["candidate_count"] > policy.max_candidates:
        return _decision("REPLAN_REQUIRED", "CANDIDATE_LIMIT_EXCEEDED",
                         f"{governance['candidate_count']} candidates; the maximum per experiment is "
                         f"{policy.max_candidates}.", budget)
    if governance["pairwise_comparisons"] > policy.max_pairwise_comparisons:
        return _decision("REPLAN_REQUIRED", "PAIRWISE_LIMIT_EXCEEDED",
                         f"{governance['pairwise_comparisons']} pairwise comparisons; the maximum is "
                         f"{policy.max_pairwise_comparisons}.", budget)
    comparisons = max(governance["candidate_count"], governance["pairwise_comparisons"])
    if comparisons > 1 and governance["multiple_testing_policy"] == "NONE":
        return _decision("REPLAN_REQUIRED", "MULTIPLE_TESTING_POLICY_REQUIRED",
                         f"The experiment makes {comparisons} comparisons; declare a multiple_testing_policy "
                         f"(BONFERRONI, HOLM or BENJAMINI_HOCHBERG).", budget)
    holdout = governance.get("holdout")
    if holdout is not None:
        request = next((r for r in spec["data_requests"] if r["data_request_id"] == holdout["data_request_id"]), None)
        range_ids = [r["range_id"] for r in (request or {}).get("time_ranges") or []]
        if request is None or holdout["range_id"] not in range_ids:
            return _decision("REPLAN_REQUIRED", "HOLDOUT_INVALID",
                             "The holdout names a data_request_id and one of its declared range_ids.", budget)
        if len(range_ids) < 2:
            return _decision("REPLAN_REQUIRED", "HOLDOUT_INVALID",
                             "A holdout range needs at least one other range of the same request to fit on.", budget)
    sample = governance.get("minimum_sample")
    if sample is not None and sample["value"] < policy.minimum(sample["unit"]):
        return _decision("REPLAN_REQUIRED", "MINIMUM_SAMPLE_TOO_LOW",
                         f"The declared minimum sample {sample['value']} {sample['unit']} is below the policy minimum "
                         f"{policy.minimum(sample['unit'])}.", budget)

    if group in groups:  # a later revision of an approved experiment keeps its reservation
        if groups[group] != hypothesis:
            return _decision("REPLAN_REQUIRED", "HYPOTHESIS_CHANGED_IN_REVISION",
                             "A revision keeps the hypothesis of its request group; a new hypothesis is a new "
                             "request group.", budget)
        return _decision("APPROVED", None, None, budget, _constraints(governance, policy, reused=True))
    if len(groups) >= policy.max_experiments:
        return _decision("REJECTED", "EXPERIMENT_BUDGET_EXCEEDED",
                         f"This run has used all {policy.max_experiments} research experiments.", budget)
    followup = governance.get("followup_of")
    if followup:
        if followup not in groups:
            return _decision("REPLAN_REQUIRED", "FOLLOWUP_PARENT_NOT_FOUND",
                             "followup_of names an approved research request group of this run.", budget)
        if groups[followup] != hypothesis:
            return _decision("REPLAN_REQUIRED", "FOLLOWUP_HYPOTHESIS_MISMATCH",
                             "A follow-up tests the same hypothesis as its parent.", budget)
        if followups.get(hypothesis, 0) >= policy.max_followups_per_hypothesis:
            return _decision("REJECTED", "FOLLOWUP_LIMIT_EXCEEDED",
                             f"Hypothesis {hypothesis} has used its {policy.max_followups_per_hypothesis} follow-ups.",
                             budget)
    elif hypothesis in hypotheses:
        return _decision("REPLAN_REQUIRED", "HYPOTHESIS_ALREADY_TESTED",
                         f"Hypothesis {hypothesis} already has an experiment; test it again as a follow-up "
                         f"(followup_of).", budget)
    elif len(hypotheses) >= policy.max_hypotheses:
        return _decision("REJECTED", "HYPOTHESIS_LIMIT_EXCEEDED",
                         f"This run has tested {policy.max_hypotheses} hypotheses, the configured maximum.", budget)
    after = {**budget, "experiments_used": len(groups) + 1,
             "hypotheses_used": len(hypotheses | {hypothesis})}
    return _decision("APPROVED", None, None, after, _constraints(governance, policy, reused=False))


def _constraints(governance: dict[str, Any], policy: GovernancePolicy, *, reused: bool) -> dict[str, Any]:
    constraints = {"hypothesis_id": governance["hypothesis_id"], "candidate_count": governance["candidate_count"],
                   "pairwise_comparisons": governance["pairwise_comparisons"],
                   "multiple_testing_policy": governance["multiple_testing_policy"],
                   "holdout": governance.get("holdout"), "minimum_sample": governance.get("minimum_sample"),
                   "compute_seconds": policy.compute_seconds_per_experiment, "reservation_reused": reused,
                   "note": "Declared design constraints; the backend records them and does not verify the analysis "
                           "code against them."}
    declared = {key: governance[key] for key in DECLARATIONS if governance.get(key) is not None}
    if declared:
        constraints["declarations"] = declared
    return constraints
