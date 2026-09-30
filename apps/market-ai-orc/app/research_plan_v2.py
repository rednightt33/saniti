"""Research Plan v2 (Multi-Angle Research, AI_ENABLE_MULTI_ANGLE_RESEARCH; MULTI_ANGLE_RESEARCH.md).

A v2 plan examines one root hypothesis from two to six angles (AI_RESEARCH_MIN_ANGLES may require more). Each angle is one analytical question with one
registered method and its parameters; angles may repeat a method or its family when their questions differ, and an
exact duplicate (the same angle_signature) is refused. The plan is still conceptual: no tables, SQL or code.

The continuation of a v2 plan is signed as rpc2: besides the plan it binds the research data plan the backend built
before the plan was shown (research_data_plan/v1: bundle groups, feasibility drafts, DataNeedSpec hashes, the angle to
group mapping and every angle data contract). The caller keeps the exact plan and data plan and sends both back; the
server recomputes every hash. A v1 token (rpc1) is never read as rpc2 or the reverse.

The method registry, the parameter rules and the angle signature equal market-python-sandbox's
app/research_methods.py; both test suites pin the same signature vector and the capability negotiation compares the
registry hash. The model-facing description of the methods is the research library (app/research_library.py, the
table public."AI_research_library"); the negotiation also compares its hash (C07, 2026-09-29).
"""
from __future__ import annotations

from contextvars import ContextVar

import hashlib
import hmac
import json
import math
import re
import secrets
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from . import research_library
from .research_plan import (CLOCK_SKEW_SECONDS, IDENTIFIER, MAX_TTL_SECONDS, PLAN_ID, SHA256, TOKEN_KIND, Action,
                            PlanVerificationError, _b64decode, _b64encode, _no_code, _no_duplicates, _utc,
                            canonical_json, normalize_text)

PLAN_VERSION_V2 = "research_plan/v2"
DATA_PLAN_VERSION = "research_data_plan/v1"
CONTRACT_VERSION = "angle_data_contract/v1"
GOVERNANCE_V2 = "research_governance/v2"
FINDINGS_V2 = "research_findings/v2"
TOKEN_VERSION_V2 = "rpc2"
MAX_TOKEN_CHARS_V2 = 4096
TOKEN_V2 = re.compile(r"^rpc2\.[A-Za-z0-9_-]{16,3900}\.[A-Za-z0-9_-]{43}$")
DRAFT_ID = re.compile(r"^draft_[0-9a-f]{24}$")
# the lowest minimum became 2 on 2026-09-29 (user decision: do not force many angles; AI_RESEARCH_MIN_ANGLES may raise it);
# the schema admits 1 since 2026-09-30 for the one-angle follow-up suggestions of mode 4 (app/mode4.py): a plan's angle
# count is enforced by the plan gate and check_research_feasibility (AI_RESEARCH_MIN_ANGLES, or the request's bounds)
MIN_ANGLES, MAX_ANGLES = 1, 6
# Mode 4: the angle count one request must plan (low, high); None uses the deployment's AI_RESEARCH_MIN/MAX_ANGLES
current_angle_bounds: ContextVar[tuple[int, int] | None] = ContextVar("current_angle_bounds", default=None)
FAMILY_COUNT = 5
ENGINE_VERSION = 1
METHODS: dict[str, str] = {
    "conditional_distribution": "CONDITIONAL_OUTCOME",
    "threshold_sensitivity": "CONDITIONAL_OUTCOME",
    "streak_persistence": "PERSISTENCE",
    "regime_comparison": "GROUP_COMPARISON",
    "cohort_comparison": "GROUP_COMPARISON",
    "quantile_ranking": "QUANTILE_RANKING",
    "lead_lag": "TEMPORAL_DEPENDENCY",
    "correlation_dependency": "TEMPORAL_DEPENDENCY",
}
PARAMETER_FIELDS = ("thresholds", "threshold_operator", "lags", "primary_lag", "buckets", "groups", "comparison",
                    "streak_lengths", "rolling_window", "baseline_mode", "correlation_method")
USES: dict[str, tuple[str, ...]] = {
    "conditional_distribution": ("baseline_mode",),
    "threshold_sensitivity": ("thresholds", "threshold_operator", "baseline_mode"),
    "streak_persistence": ("streak_lengths",),
    "regime_comparison": ("groups", "comparison"),
    "cohort_comparison": ("groups", "comparison"),
    "quantile_ranking": ("buckets",),
    "lead_lag": ("lags", "primary_lag", "correlation_method"),
    "correlation_dependency": ("primary_lag", "rolling_window", "correlation_method"),
}
OPTIONAL_USES = {"correlation_dependency": ("primary_lag", "rolling_window")}
MAX_CANDIDATES_PER_ANGLE = 50
MAX_PAIRWISE_PER_ANGLE = 20_000
MAX_CANDIDATES_PER_PLAN = 150
MAX_PAIRWISE_PER_PLAN = 20_000

MethodId = Literal["conditional_distribution", "threshold_sensitivity", "streak_persistence", "regime_comparison",
                   "cohort_comparison", "quantile_ranking", "lead_lag", "correlation_dependency"]
MethodFamily = Literal["CONDITIONAL_OUTCOME", "PERSISTENCE", "GROUP_COMPARISON", "QUANTILE_RANKING",
                       "TEMPORAL_DEPENDENCY"]
Direction = Literal["HIGHER", "LOWER", "DIFFERENT"]
OutcomeUnit = Literal["PERCENT", "DECIMAL", "OTHER"]
Policy = Literal["NONE", "BONFERRONI", "HOLM", "BENJAMINI_HOCHBERG"]
SampleUnit = Literal["EVENTS", "OBSERVATIONS", "ENTITIES"]
AngleStatus = Literal["SUPPORTED", "PARTIALLY_SUPPORTED", "INSUFFICIENT_EVIDENCE", "INVALID", "NOT_RUN"]


def registry() -> dict[str, Any]:
    methods = [{"method_id": m, "method_family": f} for m, f in sorted(METHODS.items())]
    raw = json.dumps({"engine_version": ENGINE_VERSION, "methods": methods}, sort_keys=True,
                     separators=(",", ":")).encode()
    return {"engine_version": ENGINE_VERSION, "methods": methods, "sha256": hashlib.sha256(raw).hexdigest()}


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def normalized_parameters(parameters: dict[str, Any] | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in PARAMETER_FIELDS:
        value = (parameters or {}).get(key)
        if value is None:
            continue
        if key == "thresholds":
            value = sorted(float(v) for v in value)
        elif key in ("lags", "streak_lengths"):
            value = sorted(int(v) for v in value)
        elif key in ("primary_lag", "buckets", "rolling_window"):
            value = int(value)
        elif key == "groups":
            value = [str(v) for v in value]
        out[key] = value
    return out


def angle_signature(angle: dict[str, Any]) -> str:
    """The identity of an angle's analytical question (the same algorithm as the sandbox)."""
    return sha256_json({
        "question": normalize_text(angle.get("angle_question")), "method_id": angle.get("method_id"),
        "condition": normalize_text(angle.get("condition")), "outcome": normalize_text(angle.get("outcome")),
        "comparator": normalize_text(angle.get("baseline_or_comparator")),
        "horizon": int(angle.get("outcome_horizon_periods") or 0), "unit": angle.get("outcome_unit"),
        "direction": angle.get("expected_direction"),
        "parameters": normalized_parameters(angle.get("parameters"))})


# M38 (suite20, 2026-09-29): the method rules the final plan enforces are checked by check_research_feasibility on
# each angle's design; the plan must then carry exactly the checked design (compared by this hash)
DESIGN_FIELDS = ("method_id", "parameters", "outcome_horizon_periods", "outcome_unit", "candidate_count",
                 "pairwise_comparisons", "multiple_testing_policy", "holdout_required")


def design_sha256(angle: dict[str, Any]) -> str:
    """The identity of an angle's checked design (an angle of a plan or the design sent to the feasibility check)."""
    return sha256_json({"method_id": angle.get("method_id"),
                        "parameters": normalized_parameters(angle.get("parameters")),
                        "outcome_horizon_periods": int(angle.get("outcome_horizon_periods") or 0),
                        "outcome_unit": angle.get("outcome_unit"),
                        "candidate_count": int(angle.get("candidate_count") or 0),
                        "pairwise_comparisons": int(angle.get("pairwise_comparisons") or 0),
                        "multiple_testing_policy": angle.get("multiple_testing_policy"),
                        "holdout_required": bool(angle.get("holdout_required"))})


def design_differences(angle: dict[str, Any], checked: dict[str, Any]) -> list[str]:
    """The design fields in which a plan angle differs from its checked design."""
    return [key for key in DESIGN_FIELDS
            if (normalized_parameters(angle.get(key)) != normalized_parameters(checked.get(key)) if key == "parameters"
                else angle.get(key) != checked.get(key))]


def family_count(method_ids: list[str]) -> int:
    return len({METHODS[m] for m in method_ids if m in METHODS})


def implied_comparisons(method_id: str, parameters: dict[str, Any]) -> tuple[int, int]:
    params = parameters or {}
    if method_id == "threshold_sensitivity":
        return len(params.get("thresholds") or []), 0
    if method_id == "streak_persistence":
        return len(params.get("streak_lengths") or []), 0
    if method_id == "lead_lag":
        return len(params.get("lags") or []), 0
    if method_id in ("regime_comparison", "cohort_comparison"):
        groups = len(params.get("groups") or [])
        mode = params.get("comparison")
        pairs = groups * (groups - 1) // 2 if mode == "PAIRWISE" else groups if mode == "VS_REST" else groups - 1
        return 1, max(pairs, 0)
    return 1, 0


def parameter_problems(method_id: str, parameters: dict[str, Any] | None, candidate_count: int,
                       pairwise_comparisons: int) -> list[str]:
    """The same rules as the sandbox's Research Governor v2."""
    if method_id not in METHODS:
        return [f"method_id {method_id!r} is not registered"]
    params = parameters or {}
    problems = [f"{key} is not used by {method_id}; set it to null" for key in PARAMETER_FIELDS
                if params.get(key) is not None and key not in USES[method_id]]
    required = [k for k in USES[method_id] if k not in OPTIONAL_USES.get(method_id, ())]
    problems += [f"{method_id} needs {key}" for key in required if params.get(key) is None]

    def numbers(key: str, low: float, high: float, integer: bool, size: tuple[int, int]) -> None:
        values = params.get(key)
        if values is None:
            return
        if not isinstance(values, list) or not size[0] <= len(values) <= size[1]:
            problems.append(f"{key} needs between {size[0]} and {size[1]} values")
            return
        for value in values:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) \
                    or (integer and float(value) != int(value)) or not low <= float(value) <= high:
                problems.append(f"{key} has an invalid value {value!r}")
                return
        if len({float(v) for v in values}) != len(values):
            problems.append(f"{key} repeats a value")

    numbers("thresholds", -1e12, 1e12, False, (1, 20))
    numbers("lags", 0, 260, True, (1, 20))
    numbers("streak_lengths", 1, 20, True, (1, 10))
    for key, low, high in (("primary_lag", 0, 260), ("buckets", 2, 10), ("rolling_window", 5, 260)):
        value = params.get(key)
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high):
            problems.append(f"{key} must be an integer from {low} to {high}")
    groups = params.get("groups")
    if groups is not None:
        if not isinstance(groups, list) or not 2 <= len(groups) <= 12 \
                or any(not isinstance(g, str) or not g.strip() or len(g) > 60 for g in groups):
            problems.append("groups needs between two and twelve short labels")
        elif len({g.strip() for g in groups}) != len(groups):
            problems.append("groups repeats a label")
    if method_id == "lead_lag" and params.get("lags") and params.get("primary_lag") is not None \
            and params["primary_lag"] not in params["lags"]:
        problems.append("primary_lag must be one of lags")
    if not problems:
        candidates, pairwise = implied_comparisons(method_id, params)
        if candidate_count < candidates:
            problems.append(f"candidate_count {candidate_count} is below the {candidates} candidates the parameters "
                            "evaluate")
        if pairwise_comparisons < pairwise:
            problems.append(f"pairwise_comparisons {pairwise_comparisons} is below the {pairwise} comparisons the "
                            "groups imply")
    return problems


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AngleParameters(Strict):
    """Every field is present; null when the angle's method does not use it."""

    thresholds: list[float] | None = Field(description="threshold_sensitivity: the signal thresholds tested.")
    threshold_operator: Literal[">=", "<="] | None = Field(description="threshold_sensitivity: signal >= or <= each "
                                                                        "threshold.")
    lags: list[int] | None = Field(description="lead_lag: the lags tested, in analysis periods.")
    primary_lag: int | None = Field(description="lead_lag: the predeclared lag (one of lags); correlation_dependency: "
                                                "the lag of the main correlation (null for none).")
    buckets: int | None = Field(description="quantile_ranking: the number of equal-count buckets.")
    groups: list[str] | None = Field(description="regime_comparison / cohort_comparison: the group labels, in the "
                                                 "order the hypothesis reads (differences are earlier minus later).")
    comparison: Literal["PAIRWISE", "VS_REST", "FIRST_VS_OTHERS"] | None = Field(
        description="regime_comparison / cohort_comparison: which differences are tested.")
    streak_lengths: list[int] | None = Field(description="streak_persistence: the streak lengths tested.")
    rolling_window: int | None = Field(description="correlation_dependency: the rolling window in periods, or null.")
    baseline_mode: Literal["COMPLEMENT", "ALL"] | None = Field(
        description="conditional_distribution / threshold_sensitivity: compare with the rows without the condition "
                    "(COMPLEMENT) or with every row (ALL).")
    correlation_method: Literal["PEARSON", "SPEARMAN"] | None = Field(
        description="lead_lag / correlation_dependency: the correlation.")


class ResearchAngle(Strict):
    angle_id: str = Field(pattern=IDENTIFIER, description="Lower-case id, unique in the plan, e.g. angle_one.")
    title: str = Field(min_length=1, max_length=200)
    angle_question: str = Field(min_length=1, max_length=1000,
                                description="The exact analytical question of this angle, unique in the plan.")
    method_id: MethodId
    method_family: MethodFamily
    objective: str = Field(min_length=1, max_length=1000)
    condition: str = Field(min_length=1, max_length=1000, description="The condition, signal or grouping in words.")
    outcome: str = Field(min_length=1, max_length=1000, description="The outcome measured, in words.")
    baseline_or_comparator: str = Field(min_length=1, max_length=1000,
                                        description="What the outcome is compared with, in words.")
    expected_direction: Direction = Field(description="HIGHER or LOWER when the hypothesis expects the outcome above "
                                                      "or below the comparator; DIFFERENT when it names no direction.")
    outcome_horizon_periods: int = Field(ge=1, le=260, description="Analysis periods one outcome spans.")
    outcome_unit: OutcomeUnit
    min_effect: float | None = Field(gt=0, le=1_000_000_000, description="The smallest effect worth knowing, only "
                                                                         "when the user named one; else null.")
    parameters: AngleParameters
    candidate_count: int = Field(ge=1, le=MAX_CANDIDATES_PER_ANGLE,
                                 description="Thresholds, lags, lengths or conditions evaluated inside this angle.")
    pairwise_comparisons: int = Field(ge=0, le=MAX_PAIRWISE_PER_ANGLE)
    multiple_testing_policy: Policy = Field(description="NONE only for a single comparison.")
    holdout_required: bool = Field(description="True when the latest range is kept as a holdout.")
    minimum_sample_value: int | None = Field(ge=1, le=10_000_000)
    minimum_sample_unit: SampleUnit | None
    why_distinct: str = Field(min_length=1, max_length=1000,
                              description="Why this question differs from the other angles.")

    @model_validator(mode="before")
    @classmethod
    def _unused_parameters_are_null(cls, data: Any) -> Any:
        """Found live (golden run 2026-09-29): the strict schema requires every parameters field, and the model often
        filled fields its method does not use (thresholds for conditional_distribution, groups for quantile_ranking),
        so plans were refused until the retries ran out. A field the method does not use carries no meaning for it:
        it is set to null before validation, so the signed plan, its signature and the governance declaration hold
        only the method's own parameters. Missing required parameters and invalid values are still refused."""
        if isinstance(data, dict) and isinstance(data.get("parameters"), dict) and data.get("method_id") in USES:
            used = USES[data["method_id"]]
            data = {**data, "parameters": {key: (value if key in used else None)
                                           for key, value in data["parameters"].items()}}
        return data

    @field_validator("title", "angle_question", "objective", "condition", "outcome", "baseline_or_comparator",
                     "why_distinct")
    @classmethod
    def _text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return _no_code(value)

    @model_validator(mode="after")
    def _consistent(self) -> "ResearchAngle":
        if METHODS[self.method_id] != self.method_family:
            raise ValueError(f"{self.method_id} belongs to method_family {METHODS[self.method_id]}")
        if (self.minimum_sample_value is None) != (self.minimum_sample_unit is None):
            raise ValueError("minimum_sample_value and minimum_sample_unit are both set or both null")
        if self.multiple_testing_policy == "NONE" and max(self.candidate_count, self.pairwise_comparisons) > 1:
            raise ValueError("more than one comparison needs a multiple_testing_policy other than NONE")
        problems = parameter_problems(self.method_id, self.parameters.model_dump(), self.candidate_count,
                                      self.pairwise_comparisons)
        if problems:
            raise ValueError("; ".join(problems))
        return self

    def signature(self) -> str:
        return angle_signature(self.model_dump(mode="json"))


class ResearchPlanV2(Strict):
    plan_version: Literal["research_plan/v2"]
    original_question: str = Field(min_length=1, max_length=4000)
    objective: str = Field(min_length=1, max_length=1000)
    root_hypothesis_id: str = Field(pattern=IDENTIFIER)
    root_hypothesis: str = Field(min_length=1, max_length=1000, description="The one hypothesis every angle examines.")
    universe: str = Field(min_length=1, max_length=1000)
    time_scope: str = Field(min_length=1, max_length=500)
    analysis_frequency: str | None = Field(max_length=100)
    angles: list[ResearchAngle] = Field(min_length=MIN_ANGLES, max_length=MAX_ANGLES,
                                        description="Two to six distinct angles.")
    assumptions: list[str] = Field(max_length=12)
    limitations: list[str] = Field(max_length=12)
    confirmation_question: str = Field(min_length=1, max_length=500)

    @field_validator("original_question", "objective", "root_hypothesis", "universe", "time_scope",
                     "confirmation_question")
    @classmethod
    def _text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return _no_code(value)

    @field_validator("assumptions", "limitations")
    @classmethod
    def _lines(cls, value: list[str]) -> list[str]:
        for line in value:
            if not isinstance(line, str) or not line.strip() or len(line) > 500:
                raise ValueError("each line is a non-blank string of at most 500 characters")
            _no_code(line)
        return value

    @model_validator(mode="after")
    def _distinct(self) -> "ResearchPlanV2":
        ids = [a.angle_id for a in self.angles]
        if len(set(ids)) != len(ids):
            raise ValueError("every angle needs its own angle_id")
        questions = [normalize_text(a.angle_question) for a in self.angles]
        if len(set(questions)) != len(questions):
            raise ValueError("every angle needs its own angle_question")
        signatures = [a.signature() for a in self.angles]
        if len(set(signatures)) != len(signatures):
            raise ValueError("two angles are the same analytical question (same method, condition, outcome, "
                             "comparator, horizon and parameters); make each angle distinct")
        if sum(a.candidate_count for a in self.angles) > MAX_CANDIDATES_PER_PLAN:
            raise ValueError("the angles together evaluate too many candidates for one plan")
        if sum(a.pairwise_comparisons for a in self.angles) > MAX_PAIRWISE_PER_PLAN:
            raise ValueError("the angles together make too many pairwise comparisons for one plan")
        return self


def plan_sha256_v2(plan: ResearchPlanV2) -> str:
    return sha256_json(plan.model_dump(mode="json"))


def data_plan_sha256(data_plan: dict[str, Any]) -> str:
    return sha256_json({k: v for k, v in data_plan.items() if k != "research_data_plan_sha256"})


def contract_sha256(contract: dict[str, Any]) -> str:
    return sha256_json({k: v for k, v in contract.items() if k != "angle_data_contract_sha256"})


class ContinuationOutV2(Strict):
    """A v2 plan's continuation: the caller keeps the exact plan and research data plan with the token."""

    kind: Literal["RESEARCH_PLAN"] = "RESEARCH_PLAN"
    plan_id: str
    origin_request_id: str
    conversation_id: str | None = None
    token: str
    expires_at: str
    plan_version: Literal["research_plan/v2"] = "research_plan/v2"
    research_data_plan: dict[str, Any]


class ContinuationInV2(Strict):
    kind: Literal["RESEARCH_PLAN"]
    plan_id: str = Field(min_length=1, max_length=40)
    origin_request_id: str = Field(min_length=1, max_length=200)
    plan: ResearchPlanV2
    research_data_plan: dict[str, Any]
    token: str = Field(min_length=1, max_length=MAX_TOKEN_CHARS_V2)
    action: Action | None = None
    revision_instruction: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _instruction(self) -> "ContinuationInV2":
        if self.revision_instruction is not None and self.action not in (None, "REVISE"):
            raise ValueError("revision_instruction is only for action REVISE")
        return self


class VerifiedPlanV2(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    plan: ResearchPlanV2
    research_data_plan: dict[str, Any]
    plan_id: str
    plan_sha256: str
    data_plan_sha256: str
    origin_request_id: str
    conversation_id: str | None
    expires_at: datetime
    token: str


def bound_components(data_plan: dict[str, Any]) -> dict[str, Any]:
    """What an rpc2 token binds besides the plan: the data plan hash, the ordered drafts and spec hashes, the angle to
    group mapping and every angle contract hash (recomputed, never read from a stored field)."""
    groups = data_plan.get("bundle_groups") or []
    contracts = data_plan.get("angle_data_contracts") or {}
    return {"dph": data_plan_sha256(data_plan), "dids": [g.get("draft_id") for g in groups],
            "shs": [g.get("spec_sha256") for g in groups],
            "gm": dict(sorted((data_plan.get("angle_to_bundle_group") or {}).items())),
            "ach": {angle: contract_sha256(contract) for angle, contract in sorted(contracts.items())
                    if isinstance(contract, dict)}}


class PlanSignerV2:
    """rpc2: HMAC-SHA256 over canonical claims with the same key as rpc1, under its own token prefix."""

    def __init__(self, key: str, ttl_seconds: int, clock) -> None:
        if len(key) < 32:
            raise ValueError("the signing key must have at least 32 characters")
        self._key = key.encode("utf-8")
        self.ttl_seconds = ttl_seconds
        self.clock = clock

    def __repr__(self) -> str:
        return f"PlanSignerV2(ttl_seconds={self.ttl_seconds})"

    def _signature(self, payload: str) -> str:
        return _b64encode(hmac.new(self._key, f"{TOKEN_VERSION_V2}.{payload}".encode("ascii"),
                                   hashlib.sha256).digest())

    def issue(self, plan: ResearchPlanV2, data_plan: dict[str, Any], origin_request_id: str,
              conversation_id: str | None) -> ContinuationOutV2:
        now = int(_utc(self.clock()).timestamp())
        plan_id = f"rp_{secrets.token_hex(12)}"
        claims = {"v": 2, "typ": TOKEN_KIND, "pid": plan_id, "ph": plan_sha256_v2(plan), "org": origin_request_id,
                  "cid": conversation_id, "iat": now, "exp": now + self.ttl_seconds, **bound_components(data_plan)}
        payload = _b64encode(canonical_json(claims))
        token = f"{TOKEN_VERSION_V2}.{payload}.{self._signature(payload)}"
        return ContinuationOutV2(plan_id=plan_id, origin_request_id=origin_request_id,
                                 conversation_id=conversation_id, token=token,
                                 expires_at=datetime.fromtimestamp(claims["exp"], timezone.utc).isoformat(),
                                 research_data_plan=data_plan)

    def _claims(self, token: str) -> dict[str, Any]:
        if not isinstance(token, str) or len(token) > MAX_TOKEN_CHARS_V2 or not TOKEN_V2.fullmatch(token):
            raise PlanVerificationError("RESEARCH_PLAN_TOKEN_INVALID", "FORMAT")
        _, payload, signature = token.split(".")
        if not hmac.compare_digest(self._signature(payload), signature):
            raise PlanVerificationError("RESEARCH_PLAN_TOKEN_INVALID", "SIGNATURE")
        try:
            claims = json.loads(_b64decode(payload), object_pairs_hook=_no_duplicates)
        except ValueError:
            raise PlanVerificationError("RESEARCH_PLAN_TOKEN_INVALID", "CLAIMS") from None
        expected = {"v", "typ", "pid", "ph", "org", "cid", "iat", "exp", "dph", "dids", "shs", "gm", "ach"}
        if not isinstance(claims, dict) or set(claims) != expected or claims["v"] != 2 or claims["typ"] != TOKEN_KIND \
                or not isinstance(claims["pid"], str) or not PLAN_ID.fullmatch(claims["pid"]) \
                or not isinstance(claims["ph"], str) or not SHA256.fullmatch(claims["ph"]) \
                or not isinstance(claims["dph"], str) or not SHA256.fullmatch(claims["dph"]) \
                or not isinstance(claims["dids"], list) or not all(isinstance(d, str) and DRAFT_ID.fullmatch(d)
                                                                    for d in claims["dids"]) \
                or not isinstance(claims["shs"], list) or not isinstance(claims["gm"], dict) \
                or not isinstance(claims["ach"], dict) \
                or not isinstance(claims["org"], str) or not 1 <= len(claims["org"]) <= 200 \
                or not (claims["cid"] is None or isinstance(claims["cid"], str) and 1 <= len(claims["cid"]) <= 200) \
                or any(isinstance(claims[k], bool) or not isinstance(claims[k], int) for k in ("iat", "exp")) \
                or not 0 < claims["exp"] - claims["iat"] <= MAX_TTL_SECONDS:
            raise PlanVerificationError("RESEARCH_PLAN_TOKEN_INVALID", "CLAIMS")
        return claims

    def verify(self, continuation: ContinuationInV2, conversation_id: str | None) -> VerifiedPlanV2:
        """Signature first, then every binding (plan, data plan, drafts, spec hashes, group mapping, angle contracts),
        then the time window."""
        claims = self._claims(continuation.token)
        bound = bound_components(continuation.research_data_plan)
        checks = (("PLAN_ID", claims["pid"] == continuation.plan_id),
                  ("ORIGIN", claims["org"] == continuation.origin_request_id),
                  ("CONVERSATION", claims["cid"] == conversation_id),
                  ("PLAN_HASH", hmac.compare_digest(claims["ph"], plan_sha256_v2(continuation.plan))),
                  ("DATA_PLAN_HASH", hmac.compare_digest(claims["dph"], bound["dph"])),
                  ("DRAFTS", claims["dids"] == bound["dids"]),
                  ("SPEC_HASHES", claims["shs"] == bound["shs"]),
                  ("GROUP_MAPPING", claims["gm"] == bound["gm"]),
                  ("ANGLE_CONTRACTS", claims["ach"] == bound["ach"]),
                  ("STORED_DATA_PLAN_HASH", continuation.research_data_plan.get("research_data_plan_sha256")
                   == bound["dph"]),
                  ("STORED_CONTRACT_HASHES", all(
                      (c or {}).get("angle_data_contract_sha256") == bound["ach"].get(a)
                      for a, c in (continuation.research_data_plan.get("angle_data_contracts") or {}).items())),
                  ("ANGLES", sorted(a.angle_id for a in continuation.plan.angles) == sorted(bound["gm"])))
        for reason, ok in checks:
            if not ok:
                raise PlanVerificationError("RESEARCH_PLAN_TOKEN_INVALID", reason)
        now = int(_utc(self.clock()).timestamp())
        if claims["iat"] > now + CLOCK_SKEW_SECONDS:
            raise PlanVerificationError("RESEARCH_PLAN_TOKEN_INVALID", "NOT_YET_VALID")
        if now >= claims["exp"]:
            raise PlanVerificationError("RESEARCH_PLAN_TOKEN_EXPIRED", "EXPIRED")
        return VerifiedPlanV2(plan=continuation.plan, research_data_plan=continuation.research_data_plan,
                              plan_id=claims["pid"], plan_sha256=claims["ph"], data_plan_sha256=claims["dph"],
                              origin_request_id=claims["org"], conversation_id=claims["cid"],
                              expires_at=datetime.fromtimestamp(claims["exp"], timezone.utc),
                              token=continuation.token)


def governance_v2(verified: VerifiedPlanV2) -> dict[str, Any]:
    """The research_governance/v2 declaration of an approved plan, built from the verified plan and data plan (the
    model never writes it)."""
    plan, data_plan = verified.plan, verified.research_data_plan
    contracts = data_plan.get("angle_data_contracts") or {}
    mapping = data_plan.get("angle_to_bundle_group") or {}
    angles = []
    for angle in plan.angles:
        dumped = angle.model_dump(mode="json")
        angles.append({
            "angle_id": angle.angle_id, "angle_question": angle.angle_question, "method_id": angle.method_id,
            "method_family": angle.method_family, "angle_signature": angle.signature(), "condition": angle.condition,
            "outcome": angle.outcome, "baseline_or_comparator": angle.baseline_or_comparator,
            "expected_direction": angle.expected_direction, "outcome_horizon_periods": angle.outcome_horizon_periods,
            "outcome_unit": angle.outcome_unit, "min_effect": angle.min_effect, "parameters": dumped["parameters"],
            "candidate_count": angle.candidate_count, "pairwise_comparisons": angle.pairwise_comparisons,
            "multiple_testing_policy": angle.multiple_testing_policy, "holdout_required": angle.holdout_required,
            "minimum_sample": {"value": angle.minimum_sample_value, "unit": angle.minimum_sample_unit}
            if angle.minimum_sample_value is not None else None,
            "followup_of_angle_id": None, "bundle_group_id": mapping.get(angle.angle_id),
            "angle_data_contract_sha256": contract_sha256(contracts.get(angle.angle_id) or {})})
    bound = bound_components(data_plan)
    return {"governance_version": GOVERNANCE_V2, "plan_id": verified.plan_id,
            "root_hypothesis_id": plan.root_hypothesis_id, "root_hypothesis": plan.root_hypothesis,
            "angles": angles, "angle_to_bundle_group": dict(mapping),
            "totals": {"candidates": sum(a.candidate_count for a in plan.angles),
                       "pairwise_comparisons": sum(a.pairwise_comparisons for a in plan.angles)},
            "hashes": {"plan_sha256": verified.plan_sha256, "research_data_plan_sha256": bound["dph"],
                       "spec_sha256s": bound["shs"], "draft_ids": bound["dids"],
                       "angle_data_contract_sha256s": bound["ach"]}}


def holdout_start(angle_contract: dict[str, Any]) -> str | None:
    """The first date of the latest range of an angle's contract (its holdout) when it has at least two ranges; the
    same rule as the sandbox's research_validation.holdout_start."""
    starts = sorted({w["start"] for d in angle_contract.get("datasets") or [] for w in d.get("ranges") or []})
    return starts[-1] if len(starts) >= 2 else None


def negotiate(capability: dict[str, Any] | None, *, min_angles: int, max_angles: int, max_groups: int,
              feasibility: bool, composite: bool, min_families: int = 0) -> tuple[dict[str, Any] | None, str | None]:
    """Startup negotiation with the sandbox's multi_angle_research capability (fail closed): (the multi_angle settings
    for build_default_registry, None) or (None, the reason it stays inactive). Both services must report version 2,
    grouped execution, the same findings and governance versions, the same method registry and the same research
    library; Research Plan feasibility and DataNeedSpec v2 must be active. The table AI_research_library is compared
    separately (library_problem), since it is read from the catalog database."""
    if not feasibility or not composite:
        return None, "needs AI_ENABLE_PLAN_FEASIBILITY (Research Plan confirmation) and AI_ENABLE_COMPOSITE_KEYS " \
                     "(data_need_spec/v2)"
    capability = capability or {}
    reg = registry()
    expected = {"enabled": True, "version": 2, "supports_grouped_execution": True, "findings_version": FINDINGS_V2,
                "governance_version": GOVERNANCE_V2, "method_registry_sha256": reg["sha256"],
                "method_ids": [m["method_id"] for m in reg["methods"]],
                "library_sha256": research_library.LIBRARY_SHA256}
    wrong = sorted(key for key, value in expected.items() if capability.get(key) != value)
    if wrong:
        return None, f"the sandbox's multi_angle_research capability does not match ({', '.join(wrong)})"
    low, high = int(capability.get("min_angles") or 0), int(capability.get("max_angles") or 0)
    if not low <= min_angles <= max_angles <= high:
        return None, f"AI_RESEARCH_MIN_ANGLES/MAX_ANGLES ({min_angles}-{max_angles}) are outside the sandbox policy " \
                     f"({low}-{high})"
    if not 0 <= min_families <= min(FAMILY_COUNT, max_angles):
        return None, f"AI_RESEARCH_MIN_FAMILIES ({min_families}) must be from 0 to {min(FAMILY_COUNT, max_angles)}"
    limits = capability.get("limits") or {}
    # sandbox_min_angles: the fewest angles the sandbox runs in one plan (mode 4 proposes one-angle follow-ups only when
    # it is 1, PY_SANDBOX_RESEARCH_MIN_ANGLES)
    return {"max_groups": max_groups, "min_angles": min_angles, "max_angles": max_angles, "min_families": min_families,
            "sandbox_min_angles": low,
            "limits": {k: limits.get(k) for k in ("bundle_max_rows", "bundle_max_parts", "max_requests_per_spec")}}, None


LIBRARY_COLUMNS = ("method_id", "engine_version", "library_version", "method_family", "question_shape", "input_roles",
                   "required_parameters", "optional_parameters", "data_requirements", "common_requirements",
                   "sample_unit", "secondary_checks", "decision_rules_ref", "interpretation", "misuse_warning",
                   "example_question")


def library_problem(rows: list[dict[str, Any]] | None) -> str | None:
    """None when the active rows of public."AI_research_library" (read at startup) are exactly this service's research
    library: the same content, recomputed, and the same stored library_sha256. Otherwise the reason multi-angle
    research stays inactive (the model would read method descriptions the engines do not implement)."""
    if not rows:
        return "AI_research_library has no active rows for this engine version"
    stored = {row.get("library_sha256") for row in rows}
    if stored != {research_library.LIBRARY_SHA256}:
        return "AI_research_library carries another library_sha256"
    content = sorted(({key: row.get(key) for key in LIBRARY_COLUMNS} for row in rows), key=lambda r: r["method_id"])
    if content != research_library.rows():
        return "AI_research_library content differs from the research library of this service"
    return None


def plan_digest_v2(plan: ResearchPlanV2) -> dict[str, Any]:
    """What the reply classifier sees of a v2 plan."""
    return {"objective": plan.objective, "universe": plan.universe, "time_scope": plan.time_scope,
            "hypotheses": [plan.root_hypothesis] + [a.angle_question for a in plan.angles],
            "confirmation_question": plan.confirmation_question}
