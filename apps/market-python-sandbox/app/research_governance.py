"""Research Governor for DataNeedSpec research runs (mode RESEARCH).

A research data need carries a companion ResearchGovernanceRequest. It declares what the experiment will search and
how it will guard against false discovery, never how it computes anything: there is no formula, method enum, design
enum or output grain, so a new formula is never refused because the backend has no implementation of it. The optional
condition, outcome and baseline are plain-language declarations (market-ai-orc binds them to the user's approved
Research Plan); they are validated as bounded text, recorded and returned, never matched against the analysis code.

The governor decides, deterministically and before any data is extracted, whether the experiment fits the run's
budgets: experiments, hypotheses, follow-ups, candidates, pairwise comparisons, revisions (retries), a declared
multiple-testing policy when more than one comparison is made, a holdout that is a declared time range, a minimum
sample at or above policy (only while research findings v1 are off: with them the sample is categorised
after the run, app/research_findings.py), and the compute budget the sandbox session will receive. It answers APPROVED,
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
# research findings v1: what the backend needs to recompute the sample category and the verdict
FINDINGS = ("expected_direction", "outcome_horizon_periods", "outcome_unit", "min_effect", "success_definition")
FINDINGS_REQUIRED = ("expected_direction", "outcome_horizon_periods", "outcome_unit")
DIRECTIONS = ("HIGHER", "LOWER", "DIFFERENT")
OUTCOME_UNITS = ("PERCENT", "DECIMAL", "OTHER")
FIELDS = {"hypothesis_id", "hypothesis", "objective", "candidate_count", "pairwise_comparisons", "holdout",
          "minimum_sample", "multiple_testing_policy", "followup_of", *DECLARATIONS, *FINDINGS}
# The declarations are optional (absent or null) so a request without them is unchanged.
NULLABLE = {"holdout", "minimum_sample", "followup_of", *DECLARATIONS, *FINDINGS}


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
    # research findings v1 replace the fixed minimum sample with a sample category computed after the run
    enforce_minimum_sample: bool = True
    findings_fields_required: bool = False

    def minimum(self, unit: str) -> int:
        defaults = {"EVENTS": 30, "OBSERVATIONS": 100, "ENTITIES": 10}
        return (self.min_sample or defaults).get(unit, defaults[unit])

    def public(self) -> dict[str, Any]:
        return {"max_experiments": self.max_experiments, "max_hypotheses": self.max_hypotheses,
                "max_followups_per_hypothesis": self.max_followups_per_hypothesis,
                "max_candidates": self.max_candidates, "max_pairwise_comparisons": self.max_pairwise_comparisons,
                "max_revisions_per_group": self.max_revisions_per_group,
                "minimum_sample": {u: self.minimum(u) for u in SAMPLE_UNITS} if self.enforce_minimum_sample
                else None,
                "compute_seconds_per_experiment": self.compute_seconds_per_experiment}


def check_request(raw: Any, findings_required: bool = False) -> list[dict[str, Any]]:
    """Structural problems of a ResearchGovernanceRequest, as DataNeedValidator issues (data_request_id None).
    findings_required (research findings v1): expected_direction, outcome_horizon_periods and outcome_unit are
    required."""
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
    if findings_required:
        for key in FINDINGS_REQUIRED:
            if raw.get(key) is None:
                add("MISSING_REQUIRED_FIELD", f".{key}", None)
    if raw.get("expected_direction") is not None and raw["expected_direction"] not in DIRECTIONS:
        add("INVALID_FIELD_VALUE", ".expected_direction", raw["expected_direction"])
    if raw.get("outcome_unit") is not None and raw["outcome_unit"] not in OUTCOME_UNITS:
        add("INVALID_FIELD_VALUE", ".outcome_unit", raw["outcome_unit"])
    horizon = raw.get("outcome_horizon_periods")
    if horizon is not None and (isinstance(horizon, bool) or not isinstance(horizon, int) or not 1 <= horizon <= 260):
        add("INVALID_FIELD_VALUE", ".outcome_horizon_periods", horizon)
    effect = raw.get("min_effect")
    if effect is not None and (isinstance(effect, bool) or not isinstance(effect, (int, float)) or not effect > 0):
        add("INVALID_FIELD_VALUE", ".min_effect", effect)
    success = raw.get("success_definition")
    if success is not None and (not isinstance(success, str) or not success.strip() or len(success) > 500):
        add("INVALID_FIELD_VALUE", ".success_definition", success)
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
    if policy.enforce_minimum_sample and sample is not None and sample["value"] < policy.minimum(sample["unit"]):
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
    findings = {key: governance[key] for key in FINDINGS if governance.get(key) is not None}
    if findings:
        constraints["findings"] = findings
    return constraints


# ---------------------------------------------------------------- research_governance/v2 (Multi-Angle Research)

GOVERNANCE_V2 = "research_governance/v2"
ANGLE_ID = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
PLAN_ID = re.compile(r"^rp_[0-9a-f]{24}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
ANGLE_FIELDS = {"angle_id", "angle_question", "method_id", "method_family", "angle_signature", "condition", "outcome",
                "baseline_or_comparator", "expected_direction", "outcome_horizon_periods", "outcome_unit",
                "min_effect", "parameters", "candidate_count", "pairwise_comparisons", "multiple_testing_policy",
                "holdout_required", "minimum_sample", "followup_of_angle_id", "bundle_group_id",
                "angle_data_contract_sha256"}
V2_FIELDS = {"governance_version", "plan_id", "root_hypothesis_id", "root_hypothesis", "angles",
             "angle_to_bundle_group", "totals", "hashes"}
HASH_FIELDS = {"plan_sha256", "research_data_plan_sha256", "spec_sha256s", "draft_ids", "angle_data_contract_sha256s"}


@dataclass(frozen=True)
class MultiAnglePolicy:
    """Budgets of a multi-angle Research run. The angle budget is separate from findings v1's hypothesis budget: one
    root hypothesis may be examined by every angle."""

    min_angles: int = 2  # user decision 2026-09-29: do not force many angles; market-ai-orc may require more
    max_angles_per_plan: int = 6
    max_candidates_per_angle: int = 50
    max_pairwise_per_angle: int = 20_000
    max_candidates_per_plan: int = 150
    max_pairwise_per_plan: int = 20_000
    max_followups_per_angle: int = 5

    def public(self) -> dict[str, Any]:
        return {"min_angles": self.min_angles, "max_angles_per_plan": self.max_angles_per_plan,
                "max_candidates_per_angle": self.max_candidates_per_angle,
                "max_pairwise_per_angle": self.max_pairwise_per_angle,
                "max_candidates_per_plan": self.max_candidates_per_plan,
                "max_pairwise_per_plan": self.max_pairwise_per_plan}


def check_request_v2(raw: Any, policy: MultiAnglePolicy) -> list[dict[str, Any]]:
    """Structural problems of a research_governance/v2 declaration, in the validator's issue shape."""
    from .research_methods import METHODS, angle_signature, parameter_problems

    problems: list[dict[str, Any]] = []

    def add(code: str, path: str, value: Any) -> None:
        problems.append({"data_request_id": None, "code": code, "field_path": f"research_governance{path}",
                         "rejected_value": value if not isinstance(value, (dict, list)) else str(value)[:200]})

    if not isinstance(raw, dict):
        add("INVALID_FIELD_TYPE", "", raw)
        return problems
    for key in sorted(set(raw) - V2_FIELDS):
        add("UNKNOWN_FIELD", f".{key}", raw[key])
    for key in sorted(V2_FIELDS - set(raw)):
        add("MISSING_REQUIRED_FIELD", f".{key}", None)
    if raw.get("governance_version") != GOVERNANCE_V2:
        add("INVALID_FIELD_VALUE", ".governance_version", raw.get("governance_version"))
    if not isinstance(raw.get("plan_id"), str) or not PLAN_ID.fullmatch(raw["plan_id"]):
        add("INVALID_FIELD_VALUE", ".plan_id", raw.get("plan_id"))
    if not isinstance(raw.get("root_hypothesis_id"), str) or not HYPOTHESIS_ID.fullmatch(raw["root_hypothesis_id"]):
        add("INVALID_FIELD_VALUE", ".root_hypothesis_id", raw.get("root_hypothesis_id"))
    if not isinstance(raw.get("root_hypothesis"), str) or not raw["root_hypothesis"].strip() \
            or len(raw["root_hypothesis"]) > 1000:
        add("INVALID_FIELD_VALUE", ".root_hypothesis", raw.get("root_hypothesis"))
    angles = raw.get("angles")
    if not isinstance(angles, list) or not policy.min_angles <= len(angles) <= policy.max_angles_per_plan:
        add("ANGLE_COUNT_INVALID", ".angles", len(angles) if isinstance(angles, list) else angles)
        return problems
    ids, signatures, questions = set(), set(), set()
    totals = {"candidates": 0, "pairwise_comparisons": 0}
    for index, angle in enumerate(angles):
        path = f".angles[{index}]"
        if not isinstance(angle, dict):
            add("INVALID_FIELD_TYPE", path, angle)
            continue
        for key in sorted(set(angle) - ANGLE_FIELDS):
            add("UNKNOWN_FIELD", f"{path}.{key}", angle[key])
        for key in sorted(ANGLE_FIELDS - set(angle)):
            add("MISSING_REQUIRED_FIELD", f"{path}.{key}", None)
        angle_id = angle.get("angle_id")
        if not isinstance(angle_id, str) or not ANGLE_ID.fullmatch(angle_id):
            add("INVALID_FIELD_VALUE", f"{path}.angle_id", angle_id)
        elif angle_id in ids:
            add("DUPLICATE_ANGLE_ID", f"{path}.angle_id", angle_id)
        ids.add(angle_id)
        method = angle.get("method_id")
        if method not in METHODS:
            add("METHOD_NOT_REGISTERED", f"{path}.method_id", method)
            continue
        if angle.get("method_family") != METHODS[method]:
            add("METHOD_FAMILY_MISMATCH", f"{path}.method_family", angle.get("method_family"))
        for key in ("angle_question", "condition", "outcome", "baseline_or_comparator"):
            value = angle.get(key)
            if not isinstance(value, str) or not value.strip() or len(value) > 1000:
                add("INVALID_FIELD_VALUE", f"{path}.{key}", value)
        question = " ".join(str(angle.get("angle_question") or "").casefold().split())
        if question in questions:
            add("DUPLICATE_ANGLE_QUESTION", f"{path}.angle_question", angle.get("angle_question"))
        questions.add(question)
        if angle.get("expected_direction") not in DIRECTIONS:
            add("INVALID_FIELD_VALUE", f"{path}.expected_direction", angle.get("expected_direction"))
        if angle.get("outcome_unit") not in OUTCOME_UNITS:
            add("INVALID_FIELD_VALUE", f"{path}.outcome_unit", angle.get("outcome_unit"))
        horizon = angle.get("outcome_horizon_periods")
        if isinstance(horizon, bool) or not isinstance(horizon, int) or not 1 <= horizon <= 260:
            add("INVALID_FIELD_VALUE", f"{path}.outcome_horizon_periods", horizon)
            continue
        effect = angle.get("min_effect")
        if effect is not None and (isinstance(effect, bool) or not isinstance(effect, (int, float)) or not effect > 0):
            add("INVALID_FIELD_VALUE", f"{path}.min_effect", effect)
        candidates, pairwise = angle.get("candidate_count"), angle.get("pairwise_comparisons")
        if isinstance(candidates, bool) or not isinstance(candidates, int) or candidates < 1 \
                or isinstance(pairwise, bool) or not isinstance(pairwise, int) or pairwise < 0:
            add("INVALID_FIELD_VALUE", f"{path}.candidate_count", candidates)
            continue
        if candidates > policy.max_candidates_per_angle:
            add("CANDIDATE_LIMIT_EXCEEDED", f"{path}.candidate_count", candidates)
        if pairwise > policy.max_pairwise_per_angle:
            add("PAIRWISE_LIMIT_EXCEEDED", f"{path}.pairwise_comparisons", pairwise)
        totals["candidates"] += candidates
        totals["pairwise_comparisons"] += pairwise
        if angle.get("multiple_testing_policy") not in POLICIES:
            add("INVALID_FIELD_VALUE", f"{path}.multiple_testing_policy", angle.get("multiple_testing_policy"))
        elif max(candidates, pairwise) > 1 and angle["multiple_testing_policy"] == "NONE":
            add("MULTIPLE_TESTING_POLICY_REQUIRED", f"{path}.multiple_testing_policy", "NONE")
        for problem in parameter_problems(method, angle.get("parameters") if isinstance(angle.get("parameters"),
                                                                                         dict) else None,
                                          candidates, pairwise):
            add("PARAMETER_INVALID", f"{path}.parameters", problem)
        sample = angle.get("minimum_sample")
        if sample is not None and (not isinstance(sample, dict) or set(sample) != {"value", "unit"}
                                   or sample.get("unit") not in SAMPLE_UNITS or isinstance(sample.get("value"), bool)
                                   or not isinstance(sample.get("value"), int) or sample["value"] < 1):
            add("INVALID_FIELD_VALUE", f"{path}.minimum_sample", sample)
        if not isinstance(angle.get("holdout_required"), bool):
            add("INVALID_FIELD_VALUE", f"{path}.holdout_required", angle.get("holdout_required"))
        followup = angle.get("followup_of_angle_id")
        if followup is not None and (not isinstance(followup, str) or not ANGLE_ID.fullmatch(followup)):
            add("INVALID_FIELD_VALUE", f"{path}.followup_of_angle_id", followup)
        try:
            signature = angle_signature(angle)
        except (TypeError, ValueError):
            signature = None
        if signature is None or angle.get("angle_signature") != signature:
            add("ANGLE_SIGNATURE_MISMATCH", f"{path}.angle_signature", angle.get("angle_signature"))
        elif signature in signatures:
            add("DUPLICATE_ANGLE_SIGNATURE", f"{path}.angle_signature", signature)
        signatures.add(signature)
        if not isinstance(angle.get("bundle_group_id"), str) \
                or angle.get("bundle_group_id") != (raw.get("angle_to_bundle_group") or {}).get(angle_id):
            add("ANGLE_GROUP_MISMATCH", f"{path}.bundle_group_id", angle.get("bundle_group_id"))
        contract = angle.get("angle_data_contract_sha256")
        if not isinstance(contract, str) or not SHA256.fullmatch(contract):
            add("INVALID_FIELD_VALUE", f"{path}.angle_data_contract_sha256", contract)
    if totals["candidates"] > policy.max_candidates_per_plan:
        add("PLAN_CANDIDATE_LIMIT_EXCEEDED", ".totals.candidates", totals["candidates"])
    if totals["pairwise_comparisons"] > policy.max_pairwise_per_plan:
        add("PLAN_PAIRWISE_LIMIT_EXCEEDED", ".totals.pairwise_comparisons", totals["pairwise_comparisons"])
    if raw.get("totals") != totals:
        add("TOTALS_MISMATCH", ".totals", raw.get("totals"))
    mapping = raw.get("angle_to_bundle_group")
    if not isinstance(mapping, dict) or set(mapping) != ids:
        add("ANGLE_GROUP_MISMATCH", ".angle_to_bundle_group", mapping)
    hashes = raw.get("hashes")
    if not isinstance(hashes, dict) or set(hashes) != HASH_FIELDS:
        add("INVALID_FIELD_VALUE", ".hashes", hashes)
    return problems


def review_v2(governance: dict[str, Any], history: list[dict[str, Any]], policy: MultiAnglePolicy
              ) -> dict[str, Any]:
    """The Research Governor's decision on a structurally valid v2 declaration. history: earlier research runs of
    this request ({"governance": ..., "data_plan_sha256": ...}). The same data plan again reuses its reservation; an
    angle already run in this request needs followup_of_angle_id naming it; a new analytical question needs a new
    angle_id."""
    earlier: dict[str, str] = {}
    followups: dict[str, int] = {}
    for item in history:
        for angle in (item.get("governance") or {}).get("angles") or []:
            earlier.setdefault(angle["angle_id"], angle["angle_signature"])
            if angle.get("followup_of_angle_id"):
                followups[angle["followup_of_angle_id"]] = followups.get(angle["followup_of_angle_id"], 0) + 1
    angles = governance["angles"]
    budget = {"angles": len(angles), "angles_limit": policy.max_angles_per_plan, "min_angles": policy.min_angles,
              "candidates": governance["totals"]["candidates"],
              "candidates_limit": policy.max_candidates_per_plan,
              "pairwise_comparisons": governance["totals"]["pairwise_comparisons"],
              "pairwise_limit": policy.max_pairwise_per_plan, "earlier_runs": len(history)}
    for angle in angles:
        angle_id, followup = angle["angle_id"], angle.get("followup_of_angle_id")
        if followup is not None:
            if followup not in earlier:
                return _decision("REPLAN_REQUIRED", "FOLLOWUP_PARENT_NOT_FOUND",
                                 f"{angle_id}: followup_of_angle_id names an angle already run in this request.",
                                 budget)
            if followups.get(followup, 0) >= policy.max_followups_per_angle:
                return _decision("REJECTED", "FOLLOWUP_LIMIT_EXCEEDED",
                                 f"Angle {followup} has used its {policy.max_followups_per_angle} follow-ups.", budget)
        elif angle_id in earlier:
            return _decision("REPLAN_REQUIRED", "ANGLE_ALREADY_RUN",
                             f"Angle {angle_id} already ran in this request; rerun it as a follow-up "
                             "(followup_of_angle_id) or give a new question a new angle_id.", budget)
    constraints = {"governance_version": GOVERNANCE_V2, "plan_id": governance["plan_id"],
                   "root_hypothesis_id": governance["root_hypothesis_id"],
                   "angles": {a["angle_id"]: {k: a[k] for k in sorted(ANGLE_FIELDS) if k != "angle_id"}
                              for a in angles},
                   "note": "Each angle's finding is computed by the backend from its recorded input with these "
                           "approved values."}
    return _decision("APPROVED", None, None, budget, constraints)
