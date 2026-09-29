"""Multi-Angle Research: the method registry, the parameters each method takes and the angle signature.

The registry must equal runtime/research_engines.py (a test compares them) and market-ai-orc's
app/research_plan_v2.py (the capability negotiation compares the registry hash; both test suites pin the same
signature vectors). Nothing here computes a statistic.
"""
from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from typing import Any

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
# the parameters each method uses; every other parameter must be null
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


def registry() -> dict[str, Any]:
    methods = [{"method_id": m, "method_family": f} for m, f in sorted(METHODS.items())]
    raw = json.dumps({"engine_version": ENGINE_VERSION, "methods": methods}, sort_keys=True,
                     separators=(",", ":")).encode()
    return {"engine_version": ENGINE_VERSION, "methods": methods, "sha256": hashlib.sha256(raw).hexdigest()}


def normalize_text(value: str | None) -> str:
    """NFKC, case-folded, whitespace collapsed (the same equality as market-ai-orc's research plan)."""
    return " ".join(unicodedata.normalize("NFKC", value or "").casefold().split())


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def normalized_parameters(parameters: dict[str, Any] | None) -> dict[str, Any]:
    """Only the set parameters; numeric lists sorted (their order carries no meaning), groups kept in order (it
    defines the direction of a difference)."""
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
    """The identity of an angle's analytical question: two angles with the same signature are duplicates, whatever
    their ids; the same method in two angles is fine when anything here differs."""
    return sha256_json({
        "question": normalize_text(angle.get("angle_question")), "method_id": angle.get("method_id"),
        "condition": normalize_text(angle.get("condition")), "outcome": normalize_text(angle.get("outcome")),
        "comparator": normalize_text(angle.get("baseline_or_comparator")),
        "horizon": int(angle.get("outcome_horizon_periods") or 0), "unit": angle.get("outcome_unit"),
        "direction": angle.get("expected_direction"),
        "parameters": normalized_parameters(angle.get("parameters"))})


def implied_comparisons(method_id: str, parameters: dict[str, Any]) -> tuple[int, int]:
    """(candidates, pairwise comparisons) the parameters imply."""
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
    """What is wrong with an angle's parameters for its method (empty when nothing)."""
    if method_id not in METHODS:
        return [f"method_id {method_id!r} is not registered ({', '.join(sorted(METHODS))})"]
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
            problems.append(f"{key} needs {size[0]} to {size[1]} values")
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
    if params.get("threshold_operator") is not None and params["threshold_operator"] not in (">=", "<="):
        problems.append("threshold_operator is >= or <=")
    if params.get("baseline_mode") is not None and params["baseline_mode"] not in ("COMPLEMENT", "ALL"):
        problems.append("baseline_mode is COMPLEMENT or ALL")
    if params.get("correlation_method") is not None and params["correlation_method"] not in ("PEARSON", "SPEARMAN"):
        problems.append("correlation_method is PEARSON or SPEARMAN")
    if params.get("comparison") is not None and params["comparison"] not in ("PAIRWISE", "VS_REST",
                                                                             "FIRST_VS_OTHERS"):
        problems.append("comparison is PAIRWISE, VS_REST or FIRST_VS_OTHERS")
    groups = params.get("groups")
    if groups is not None:
        if not isinstance(groups, list) or not 2 <= len(groups) <= 12 \
                or any(not isinstance(g, str) or not g.strip() or len(g) > 60 for g in groups):
            problems.append("groups needs 2 to 12 labels of at most 60 characters")
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
