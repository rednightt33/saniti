"""Research engines (research findings v2, Multi-Angle Research): five table-agnostic statistical engines with eight
method ids. They know nothing about PostgreSQL tables or asset types: each takes one pandas DataFrame with canonical
column roles and the approved parameters of one angle, and returns plain JSON-able numbers. The session wrappers
(saniti.research_*) call them for the model's immediate view; the harness (app/research_validation.py) calls them
again on the recorded input with the approved values, and only that result is a finding.

Canonical columns: date (any date-like), entity (optional unless an engine needs it), and the roles
    condition (bool)  signal (number)  outcome (number)  state (bool)  group (label)  leader/follower (number)

Conventions shared with findings v1 (runtime/research_stats.py):
- rows on one date form one cluster; outcomes spanning horizon periods overlap, so the effective sample of a
  date-based estimate is the number of distinct dates left after keeping only dates at least `horizon` positions
  apart on the frame's own calendar;
- differences of means use row means with standard errors from the spread of per-date means (Welch-Satterthwaite
  degrees of freedom); proportions use Wilson intervals on the effective count and Newcombe's interval for a
  difference; correlations use a Fisher z interval on an effective count reduced for autocorrelation
  (n * (1 - r1x r1y) / (1 + r1x r1y), Bretherton et al. 1999), Spearman with the 1.06 variance factor;
- sample category: INSUFFICIENT (effective below 2), ANECDOTAL (below 10), UNDERPOWERED (the minimum detectable
  effect exceeds the smallest effect of interest), ADEQUATE.

Multiple testing inside one angle: p-values are adjusted with Bonferroni, Holm (step-down) or Benjamini-Hochberg
(step-up) over m = max(declared comparisons, comparisons computed). Adjusted intervals use alpha/m for Bonferroni and
Holm (Holm has no simultaneous interval; Bonferroni width is the conservative choice) and the false-coverage level
alpha * R / m of Benjamini-Yekutieli (2005) for Benjamini-Hochberg, R being the number of rejections (alpha/m when
there is none). Angles are separate questions and are not corrected against each other.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any

ENGINE_VERSION = 1
FINDINGS_VERSION = "research_findings/v2"
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
FAMILIES = ("CONDITIONAL_OUTCOME", "PERSISTENCE", "GROUP_COMPARISON", "QUANTILE_RANKING", "TEMPORAL_DEPENDENCY")
DIRECTIONS = ("HIGHER", "LOWER", "DIFFERENT")
UNITS = ("PERCENT", "DECIMAL", "OTHER")
POLICIES = ("NONE", "BONFERRONI", "HOLM", "BENJAMINI_HOCHBERG")
STATUSES = ("SUPPORTED", "PARTIALLY_SUPPORTED", "INSUFFICIENT_EVIDENCE", "INVALID", "NOT_RUN")
LEVELS = ("FORMULA_AND_STATISTICS_VERIFIED", "STATISTICS_VERIFIED", "EXECUTION_ONLY")
FLAGS = ("INSUFFICIENT", "ANECDOTAL", "UNDERPOWERED", "ADEQUATE")
ALPHA = 0.05
POWER = 0.80
MIN_EFFECTIVE = 2
ANECDOTAL_BELOW = 10
MAX_INPUT_ROWS = 1_000_000
PERCENTILES = (5, 10, 25, 50, 75, 90, 95)
TAIL_SHARE = 0.05
MONOTONIC_RHO = 0.8
# smallest effect of interest when the plan names none: an IDX round-trip trading cost for returns (as findings v1),
# five percentage points for a probability, a small correlation (Cohen) for an association
DEFAULT_MIN_EFFECT = {"PERCENT": 0.5, "DECIMAL": 0.005}
DEFAULT_PROPORTION_EFFECT = 0.05
DEFAULT_CORRELATION_EFFECT = 0.1
SMALL_STANDARDIZED_EFFECT = 0.2
COMPARISONS = ("PAIRWISE", "VS_REST", "FIRST_VS_OTHERS")


class EngineError(ValueError):
    """The input or the parameters cannot be evaluated as approved (the finding becomes INVALID)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def registry() -> dict[str, Any]:
    """The method registry both services compare before multi-angle research is enabled."""
    methods = [{"method_id": m, "method_family": f} for m, f in sorted(METHODS.items())]
    raw = json.dumps({"engine_version": ENGINE_VERSION, "methods": methods}, sort_keys=True,
                     separators=(",", ":")).encode()
    return {"engine_version": ENGINE_VERSION, "methods": methods, "sha256": hashlib.sha256(raw).hexdigest()}


# ---------------------------------------------------------------- small numeric helpers

def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _clean(value: Any) -> Any:
    """JSON-able: NaN and infinities become None, numpy scalars become Python numbers."""
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if hasattr(value, "item") and not isinstance(value, (list, dict)):
        try:
            value = value.item()
        except (AttributeError, ValueError):
            pass
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return value


def _wilson(k: float, n: float, z: float) -> tuple[float | None, float | None]:
    if n <= 0:
        return None, None
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centre - half), min(1.0, centre + half)


def _thinned(dates: list[str], calendar: dict[str, int], horizon: int) -> int:
    """Distinct dates kept when each kept date is at least `horizon` calendar positions after the previous one."""
    kept, last = 0, None
    for date in sorted(set(dates), key=lambda d: calendar[d]):
        position = calendar[date]
        if last is None or position - last >= horizon:
            kept, last = kept + 1, position
    return kept


def adjust_p_values(p_values: list[float | None], policy: str, m: int) -> list[float | None]:
    """Adjusted p-values over m tests (the p-values given plus m - len(p_values) untested ones treated as p = 1)."""
    if policy not in POLICIES:
        raise EngineError("PARAMETER_INVALID", f"multiple_testing_policy must be one of {POLICIES}.")
    m = max(int(m), sum(1 for p in p_values if p is not None), 1)
    if policy == "NONE" or m == 1:
        return [None if p is None else min(1.0, p) for p in p_values]
    indexed = [(p, i) for i, p in enumerate(p_values) if p is not None]
    out: list[float | None] = [None] * len(p_values)
    if policy == "BONFERRONI":
        for p, i in indexed:
            out[i] = min(1.0, p * m)
        return out
    ordered = sorted(indexed)
    if policy == "HOLM":
        running = 0.0
        for rank, (p, i) in enumerate(ordered):
            running = max(running, min(1.0, (m - rank) * p))
            out[i] = running
        return out
    # Benjamini-Hochberg step-up
    running = 1.0
    for rank in range(len(ordered) - 1, -1, -1):
        p, i = ordered[rank]
        running = min(running, p * m / (rank + 1))
        out[i] = min(1.0, running)
    return out


def adjusted_alpha(policy: str, m: int, rejections: int) -> float:
    m = max(1, int(m))
    if policy == "NONE" or m == 1:
        return ALPHA
    if policy == "BENJAMINI_HOCHBERG" and rejections > 0:
        return ALPHA * rejections / m
    return ALPHA / m


def sample_flag(effective: int, mde: float | None, delta: float | None) -> str:
    if effective < MIN_EFFECTIVE:
        return "INSUFFICIENT"
    if effective < ANECDOTAL_BELOW:
        return "ANECDOTAL"
    if mde is None or delta is None or mde > delta:
        return "UNDERPOWERED"
    return "ADEQUATE"


def _delta(min_effect: float | None, unit: str, kind: str, pooled_sd: float | None = None) -> tuple[float | None, str]:
    if min_effect is not None and _finite(min_effect) is not None and float(min_effect) > 0:
        return float(min_effect), "PLAN"
    if kind == "CORRELATION":
        return DEFAULT_CORRELATION_EFFECT, "SMALL_CORRELATION"
    if kind == "PROPORTION":
        return DEFAULT_PROPORTION_EFFECT, "FIVE_PERCENTAGE_POINTS"
    if unit in DEFAULT_MIN_EFFECT:
        return DEFAULT_MIN_EFFECT[unit], "ROUND_TRIP_TRADING_COST"
    if pooled_sd:
        return SMALL_STANDARDIZED_EFFECT * pooled_sd, "SMALL_STANDARDIZED_EFFECT"
    return None, "UNAVAILABLE"


# ---------------------------------------------------------------- input preparation

def prepare(frame, roles: tuple[str, ...], *, entity_required: bool = False, numeric: tuple[str, ...] = (),
            boolean: tuple[str, ...] = (), label: tuple[str, ...] = ()):
    """The canonical frame: date normalized, sorted by entity then date (mergesort, so ties keep their order), the
    role columns typed. Rows with a missing role value are kept (each engine drops what it cannot use and counts it)."""
    import numpy as np
    import pandas as pd

    if not isinstance(frame, pd.DataFrame):
        raise EngineError("INPUT_INVALID", "The input must be a pandas DataFrame.")
    if len(frame) > MAX_INPUT_ROWS:
        raise EngineError("INPUT_TOO_LARGE", f"The input has {len(frame)} rows; an angle takes at most "
                                             f"{MAX_INPUT_ROWS}. Aggregate or narrow it first.")
    needed = ["date", *roles] + (["entity"] if entity_required else [])
    missing = [c for c in needed if c not in frame.columns]
    if missing:
        raise EngineError("INPUT_COLUMNS_MISSING", f"The input lacks the columns {missing}; name them "
                                                   f"{needed} (entity optional where not required).")
    work = pd.DataFrame(index=frame.index)
    try:
        dates = pd.to_datetime(frame["date"], errors="raise")
    except (TypeError, ValueError) as exc:
        raise EngineError("INPUT_INVALID", "date does not hold dates.") from exc
    if getattr(dates.dt, "tz", None) is not None:
        dates = dates.dt.tz_localize(None)
    if dates.isna().any():
        raise EngineError("INPUT_INVALID", "date has null values.")
    work["date"] = dates.dt.normalize()
    work["entity"] = frame["entity"].astype(str) if "entity" in frame.columns else "_all"
    for column in roles:
        series = frame[column]
        if column in numeric:
            if pd.api.types.is_bool_dtype(series):
                raise EngineError("INPUT_INVALID", f"{column} must be numeric, not boolean.")
            work[column] = pd.to_numeric(series, errors="coerce").astype("float64")
            work.loc[~np.isfinite(work[column].to_numpy(dtype="float64")), column] = np.nan
        elif column in boolean:
            values = []
            for value in series.tolist():
                if value is None or (isinstance(value, float) and math.isnan(value)) or value is pd.NA:
                    values.append(None)
                elif isinstance(value, (bool, np.bool_)) or value in (0, 1):
                    values.append(bool(value))
                else:
                    raise EngineError("INPUT_INVALID", f"{column} must be boolean (True/False or null).")
            work[column] = pd.Series(values, index=frame.index, dtype="object")
        elif column in label:
            work[column] = series.map(lambda v: None if v is None or (isinstance(v, float) and math.isnan(v))
                                      else str(v))
        else:
            work[column] = series
    work = work.sort_values(["entity", "date"], kind="mergesort").reset_index(drop=True)
    if work.duplicated(["entity", "date"]).any():
        raise EngineError("DUPLICATE_ENTITY_DATE", "Two rows share an entity and a date; keep one row per entity "
                                                   "and date.")
    return work


def _calendar(dates) -> dict[str, int]:
    return {d: i for i, d in enumerate(sorted(set(dates)))}


def _date_keys(series) -> list[str]:
    return [d.strftime("%Y-%m-%d") for d in series]


# ---------------------------------------------------------------- differences of means on per-date clusters

def _group_stats(values, date_keys: list[str], calendar: dict[str, int], horizon: int) -> dict[str, Any]:
    import numpy as np
    import pandas as pd

    frame = pd.DataFrame({"value": np.asarray(values, dtype="float64"), "date": date_keys})
    frame = frame[np.isfinite(frame["value"].to_numpy())]
    n = int(len(frame))
    mean = float(frame["value"].mean()) if n else None
    sd = float(frame["value"].std(ddof=1)) if n > 1 else None
    date_means = frame.groupby("date", sort=True)["value"].mean() if n else pd.Series(dtype="float64")
    sd_dates = float(date_means.std(ddof=1)) if len(date_means) > 1 else None
    effective = _thinned(list(date_means.index), calendar, horizon) if n else 0
    stats: dict[str, Any] = {"rows": n, "dates": int(len(date_means)), "effective": effective, "mean": mean,
                             "median": float(frame["value"].median()) if n else None, "sd": sd,
                             "sd_of_date_means": _finite(sd_dates)}
    if n:
        ordered = np.sort(frame["value"].to_numpy())
        stats["percentiles"] = {f"p{q}": float(np.percentile(ordered, q)) for q in PERCENTILES}
        tail = max(1, int(math.ceil(TAIL_SHARE * n)))
        stats["downside_tail"] = {"p5": stats["percentiles"]["p5"], "mean_of_worst": float(ordered[:tail].mean()),
                                  "rows": tail}
        stats["upside_tail"] = {"p95": stats["percentiles"]["p95"], "mean_of_best": float(ordered[-tail:].mean()),
                                "rows": tail}
        hits = int((frame["value"] > 0).sum())
        stats["hit_rate"] = hits / n
        stats["hits"] = hits
        stats["expected_outcome"] = mean
    return stats


def _welch(a: dict[str, Any], b: dict[str, Any], alpha: float) -> dict[str, Any]:
    """Difference of means a - b; standard errors from the spread of per-date means over the effective counts."""
    from scipy import stats

    out: dict[str, Any] = {"estimate": None, "standard_error": None, "df": None, "ci": None, "p_value": None,
                           "degenerate": False}
    if a["mean"] is None or b["mean"] is None:
        return out
    out["estimate"] = a["mean"] - b["mean"]
    if a["effective"] < MIN_EFFECTIVE or b["effective"] < MIN_EFFECTIVE or a["sd_of_date_means"] is None \
            or b["sd_of_date_means"] is None:
        return out
    se_a = a["sd_of_date_means"] / math.sqrt(a["effective"])
    se_b = b["sd_of_date_means"] / math.sqrt(b["effective"])
    se = math.sqrt(se_a ** 2 + se_b ** 2)
    if se <= 0:
        out["degenerate"] = True
        return out
    denominator = se_a ** 4 / (a["effective"] - 1) + se_b ** 4 / (b["effective"] - 1)
    df = se ** 4 / denominator if denominator > 0 else float(min(a["effective"], b["effective"]) - 1)
    t_crit = float(stats.t.ppf(1 - alpha / 2, df))
    out.update(standard_error=se, df=df, ci=[out["estimate"] - t_crit * se, out["estimate"] + t_crit * se],
               p_value=float(2 * stats.t.sf(abs(out["estimate"] / se), df)))
    return out


def _proportion_difference(k_a: int, n_a: int, eff_a: int, k_b: int, n_b: int, eff_b: int, alpha: float
                           ) -> dict[str, Any]:
    """Share a - share b with Newcombe's interval on the effective counts (findings v1 convention)."""
    from scipy import stats

    out: dict[str, Any] = {"estimate": None, "standard_error": None, "ci": None, "p_value": None, "rate_a": None,
                           "rate_b": None, "degenerate": False}
    if n_a <= 0 or n_b <= 0:
        return out
    p_a, p_b = k_a / n_a, k_b / n_b
    out.update(rate_a=p_a, rate_b=p_b, estimate=p_a - p_b)
    if eff_a < 1 or eff_b < 1:
        return out
    z = float(stats.norm.ppf(1 - alpha / 2))
    l_a, u_a = _wilson(p_a * eff_a, eff_a, z)
    l_b, u_b = _wilson(p_b * eff_b, eff_b, z)
    diff = p_a - p_b
    out["ci"] = [diff - math.sqrt((p_a - l_a) ** 2 + (u_b - p_b) ** 2),
                 diff + math.sqrt((u_a - p_a) ** 2 + (p_b - l_b) ** 2)]
    pooled = (p_a * eff_a + p_b * eff_b) / (eff_a + eff_b)
    spread = math.sqrt(pooled * (1 - pooled) * (1 / eff_a + 1 / eff_b))
    out["standard_error"] = spread if spread > 0 else None
    if spread > 0:
        out["p_value"] = float(2 * stats.norm.sf(abs(diff) / spread))
    else:
        out["degenerate"] = True
    return out


def _correlation(x, y, method: str, alpha: float) -> dict[str, Any]:
    """r with a Fisher z interval on the effective count (lag-one autocorrelation adjustment)."""
    import numpy as np
    from scipy import stats

    x, y = np.asarray(x, dtype="float64"), np.asarray(y, dtype="float64")
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    n = int(len(x))
    out: dict[str, Any] = {"estimate": None, "n": n, "effective": 0, "ci": None, "p_value": None,
                           "standard_error": None, "degenerate": False}
    if n < 3:
        out["effective"] = n
        return out
    if np.std(x) == 0 or np.std(y) == 0:
        out.update(degenerate=True, effective=n)
        return out
    r = float(stats.spearmanr(x, y).statistic) if method == "SPEARMAN" else float(np.corrcoef(x, y)[0, 1])

    def lag1(values) -> float:
        if len(values) < 3 or np.std(values[:-1]) == 0 or np.std(values[1:]) == 0:
            return 0.0
        return float(np.corrcoef(values[:-1], values[1:])[0, 1])

    product = lag1(x) * lag1(y)
    factor = (1 - product) / (1 + product) if product > -1 else 1.0
    effective = int(max(3, min(n, math.floor(n * max(factor, 0.0)))))
    out.update(estimate=r, effective=effective)
    if effective <= 3 or abs(r) >= 1:
        return out
    variance = 1.06 if method == "SPEARMAN" else 1.0
    se = math.sqrt(variance / (effective - 3))
    z = math.atanh(r)
    z_crit = float(stats.norm.ppf(1 - alpha / 2))
    out.update(standard_error=se, ci=[math.tanh(z - z_crit * se), math.tanh(z + z_crit * se)],
               p_value=float(2 * stats.norm.sf(abs(z) / se)))
    return out


def _with_adjusted(candidates: list[dict[str, Any]], policy: str, m: int, kind: str) -> list[dict[str, Any]]:
    """Adjusted p-values and adjusted intervals for the candidates of one angle."""
    from scipy import stats

    adjusted = adjust_p_values([c.get("p_value") for c in candidates], policy, m)
    rejections = sum(1 for p in adjusted if p is not None and p < ALPHA)
    alpha_adj = adjusted_alpha(policy, max(m, len(candidates)), rejections)
    for candidate, p in zip(candidates, adjusted):
        candidate["p_adjusted"] = p
        candidate["ci_adjusted"] = None
        se, estimate = candidate.get("standard_error"), candidate.get("estimate")
        if se is None or estimate is None or candidate.get("degenerate"):
            continue
        if kind == "CORRELATION":
            if abs(estimate) < 1:
                z = math.atanh(estimate)
                crit = float(stats.norm.ppf(1 - alpha_adj / 2))
                candidate["ci_adjusted"] = [math.tanh(z - crit * se), math.tanh(z + crit * se)]
        elif kind == "PROPORTION":
            crit = float(stats.norm.ppf(1 - alpha_adj / 2))
            scale = crit / float(stats.norm.ppf(1 - ALPHA / 2))
            low, high = candidate["ci"] or [None, None]
            if low is not None and high is not None:
                candidate["ci_adjusted"] = [estimate - (estimate - low) * scale, estimate + (high - estimate) * scale]
        else:
            df = candidate.get("df")
            crit = float(stats.t.ppf(1 - alpha_adj / 2, df)) if df else float(stats.norm.ppf(1 - alpha_adj / 2))
            candidate["ci_adjusted"] = [estimate - crit * se, estimate + crit * se]
    return candidates


def _multiple_testing(policy: str, m: int, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    rejections = sum(1 for c in candidates if c.get("p_adjusted") is not None and c["p_adjusted"] < ALPHA)
    return {"policy": policy, "tests": max(int(m), len(candidates), 1), "computed": len(candidates),
            "rejections": rejections, "alpha": ALPHA,
            "alpha_adjusted_interval": adjusted_alpha(policy, max(int(m), len(candidates), 1), rejections)}


def _mde(standard_error: float | None, m: int, policy: str) -> float | None:
    from scipy import stats

    if standard_error is None:
        return None
    alpha = adjusted_alpha(policy, m, 0)
    return (float(stats.norm.ppf(1 - alpha / 2)) + float(stats.norm.ppf(POWER))) * standard_error


# ---------------------------------------------------------------- engine 1: conditional outcome

def conditional_outcome(frame, *, method_id: str, parameters: dict[str, Any], expected_direction: str,
                        horizon: int, unit: str, min_effect: float | None, policy: str, comparisons: int
                        ) -> dict[str, Any]:
    """conditional_distribution: the outcome distribution after the condition against the baseline (the complement
    or all rows). threshold_sensitivity: the same for signal >= t (or <= t) at every approved threshold."""
    import numpy as np

    horizon = max(1, int(horizon))
    baseline_mode = parameters.get("baseline_mode") or "COMPLEMENT"
    if method_id == "conditional_distribution":
        work = prepare(frame, ("condition", "outcome"), numeric=("outcome",), boolean=("condition",))
        masks = [("condition", work["condition"].map(lambda v: v is True).to_numpy(dtype=bool),
                  work["condition"].notna().to_numpy(dtype=bool))]
    else:
        thresholds = parameters.get("thresholds") or []
        operator = parameters.get("threshold_operator")
        if not thresholds or operator not in (">=", "<="):
            raise EngineError("PARAMETER_INVALID", "threshold_sensitivity needs thresholds and threshold_operator.")
        work = prepare(frame, ("signal", "outcome"), numeric=("signal", "outcome"))
        signal = work["signal"].to_numpy(dtype="float64")
        defined = np.isfinite(signal)
        masks = []
        for threshold in thresholds:
            hit = (signal >= float(threshold)) if operator == ">=" else (signal <= float(threshold))
            masks.append((f"{operator}{float(threshold):g}", hit & defined, defined))
    outcome = work["outcome"].to_numpy(dtype="float64")
    dates = _date_keys(work["date"])
    calendar = _calendar(dates)
    missing_outcome = int((~np.isfinite(outcome)).sum())
    candidates, groups = [], {}
    for name, hit, defined in masks:
        base_mask = (defined & ~hit) if baseline_mode == "COMPLEMENT" else defined
        cond = _group_stats(outcome[hit], [d for d, h in zip(dates, hit) if h], calendar, horizon)
        base = _group_stats(outcome[base_mask], [d for d, h in zip(dates, base_mask) if h], calendar, horizon)
        difference = _welch(cond, base, ALPHA)
        hits = _proportion_difference(cond.get("hits", 0), cond["rows"], cond["effective"], base.get("hits", 0),
                                      base["rows"], base["effective"], ALPHA)
        candidates.append({"candidate": name, **difference, "effective": min(cond["effective"], base["effective"]),
                           "hit_rate_difference": {k: hits[k] for k in ("estimate", "ci", "p_value", "rate_a",
                                                                         "rate_b")}})
        groups[name] = {"condition": cond, "baseline": base}
    m = max(int(comparisons), len(candidates))
    _with_adjusted(candidates, policy, m, "MEAN")
    primary = _best(candidates, expected_direction)
    chosen = groups[primary["candidate"]]
    pooled_sd = math.sqrt(((chosen["condition"]["sd"] or 0.0) ** 2 + (chosen["baseline"]["sd"] or 0.0) ** 2) / 2)
    delta, source = _delta(min_effect, unit, "MEAN", pooled_sd)
    mde = _mde(primary.get("standard_error"), m, policy)
    effective = primary["effective"]
    return {"engine": "CONDITIONAL_OUTCOME", "method_id": method_id, "estimate_kind": "MEAN_DIFFERENCE",
            "primary": primary, "primary_is_predeclared": method_id == "conditional_distribution",
            "candidates": candidates, "multiple_testing": _multiple_testing(policy, m, candidates),
            "sample": {"rows": int(len(work)), "effective": effective, "unit": "DATES",
                       "missing_outcome_rows": missing_outcome, "flag": sample_flag(effective, mde, delta),
                       "minimum_detectable_effect": mde, "smallest_effect_of_interest": delta,
                       "smallest_effect_source": source, "condition_rows": chosen["condition"]["rows"],
                       "entities": int(work["entity"].nunique())},
            "comparator": {"baseline_mode": baseline_mode}, "secondary": {},
            "method_payload": {"groups": groups, "horizon_periods": horizon}}


def _best(candidates: list[dict[str, Any]], expected: str) -> dict[str, Any]:
    """The candidate reported as primary when none is predeclared: the most significant one in the expected
    direction, else the most significant one."""
    def key(c: dict[str, Any]) -> tuple:
        p = c.get("p_adjusted")
        estimate = c.get("estimate")
        agrees = estimate is not None and (expected == "DIFFERENT" or (expected == "HIGHER") == (estimate > 0))
        return (0 if agrees else 1, p if p is not None else 2.0, c.get("candidate") or "")

    return sorted(candidates, key=key)[0] if candidates else {"candidate": None, "estimate": None}


# ---------------------------------------------------------------- engine 2: persistence

def streak_persistence(frame, *, method_id: str, parameters: dict[str, Any], expected_direction: str,
                       horizon: int, unit: str, min_effect: float | None, policy: str, comparisons: int
                       ) -> dict[str, Any]:
    """After a streak of at least k consecutive observations with state True (per entity, in date order), how often
    does the state stay True over the next `horizon` observations, against the base rate of that continuation over
    every observation. Also episode counts by length and the survival curve of streak lengths."""
    import numpy as np

    lengths = sorted({int(k) for k in parameters.get("streak_lengths") or []})
    if not lengths or any(k < 1 for k in lengths):
        raise EngineError("PARAMETER_INVALID", "streak_persistence needs streak_lengths of at least one.")
    horizon = max(1, int(horizon))
    work = prepare(frame, ("state",), boolean=("state",))
    rows = []
    episodes: list[tuple[int, bool]] = []  # (length, censored at the end of the series)
    for _, part in work.groupby("entity", sort=True):
        states = part["state"].tolist()
        dates = _date_keys(part["date"])
        run = 0
        for i, state in enumerate(states):
            if state is True:
                run += 1
            else:
                if run:
                    episodes.append((run, False))
                run = 0
            if i + horizon < len(states) and state is not None:
                future = states[i + 1:i + 1 + horizon]
                if any(s is None for s in future):
                    continue
                rows.append({"date": dates[i], "run": run if state is True else 0,
                             "continues": all(s is True for s in future)})
        if run:
            episodes.append((run, True))
    calendar = _calendar([r["date"] for r in rows]) if rows else {}
    base_dates = [r["date"] for r in rows]
    base_k = sum(1 for r in rows if r["continues"])
    base_eff = _thinned(base_dates, calendar, horizon) if rows else 0
    candidates = []
    for k in lengths:
        selected = [r for r in rows if r["run"] >= k]
        eff = _thinned([r["date"] for r in selected], calendar, horizon) if selected else 0
        kk = sum(1 for r in selected if r["continues"])
        diff = _proportion_difference(kk, len(selected), eff, base_k, len(rows), base_eff, ALPHA)
        candidates.append({"candidate": f"streak>={k}", "streak_length": k, "events": len(selected),
                           "continuations": kk, "effective": min(eff, base_eff), **diff})
    m = max(int(comparisons), len(candidates))
    _with_adjusted(candidates, policy, m, "PROPORTION")
    primary = _best(candidates, expected_direction)
    delta, source = _delta(min_effect, unit, "PROPORTION")
    mde = _mde(primary.get("standard_error"), m, policy)
    top = max(lengths) + 1
    counts = {str(k): sum(1 for length, _ in episodes if length == k) for k in range(1, top)}
    counts[f">={top}"] = sum(1 for length, _ in episodes if length >= top)
    total = len(episodes)
    survival = [{"length": k, "share_at_least": (sum(1 for length, _ in episodes if length >= k) / total)
                 if total else None} for k in range(1, top + 1)]
    exact = []
    for k in range(1, top):
        selected = [r for r in rows if r["run"] == k]
        exact.append({"length": k, "events": len(selected),
                      "continuation_rate": (sum(1 for r in selected if r["continues"]) / len(selected))
                      if selected else None})
    effective = primary.get("effective") or 0
    return {"engine": "PERSISTENCE", "method_id": method_id, "estimate_kind": "RATE_DIFFERENCE",
            "primary": primary, "primary_is_predeclared": len(candidates) == 1, "candidates": candidates,
            "multiple_testing": _multiple_testing(policy, m, candidates),
            "sample": {"rows": int(len(work)), "observations_with_outcome": len(rows), "effective": effective,
                       "unit": "DATES", "flag": sample_flag(effective, mde, delta), "minimum_detectable_effect": mde,
                       "smallest_effect_of_interest": delta, "smallest_effect_source": source,
                       "entities": int(work["entity"].nunique())},
            "comparator": {"base_rate": (base_k / len(rows)) if rows else None, "base_events": len(rows)},
            "secondary": {},
            "method_payload": {"episodes": total, "censored_episodes": sum(1 for _, c in episodes if c),
                               "episode_counts_by_length": counts, "continuation_by_exact_length": exact,
                               "survival_curve": survival, "horizon_periods": horizon}}


# ---------------------------------------------------------------- engine 3: group comparison

def group_comparison(frame, *, method_id: str, parameters: dict[str, Any], expected_direction: str, horizon: int,
                     unit: str, min_effect: float | None, policy: str, comparisons: int) -> dict[str, Any]:
    """cohort_comparison: entities keep one group; each entity's mean outcome is one observation (Welch on per-entity
    values, as the Analysis Spec validator). regime_comparison: the group is a property of the date; each date's mean
    outcome is one observation, thinned by the horizon. Differences read a - b with a listed before b."""
    import numpy as np

    listed = [str(g) for g in parameters.get("groups") or []]
    mode = parameters.get("comparison") or "PAIRWISE"
    if len(listed) < 2 or mode not in COMPARISONS:
        raise EngineError("PARAMETER_INVALID", "A group comparison needs at least two groups and a comparison mode.")
    horizon = max(1, int(horizon))
    cohort = method_id == "cohort_comparison"
    work = prepare(frame, ("group", "outcome"), entity_required=cohort, numeric=("outcome",), label=("group",))
    work = work[work["group"].notna()]
    unknown = sorted(set(work["group"]) - set(listed))
    if unknown:
        raise EngineError("UNDECLARED_GROUP", f"Groups {unknown[:10]} are not approved for this angle; approved: "
                                              f"{listed}.")
    work = work[np.isfinite(work["outcome"].to_numpy(dtype="float64"))]
    samples: dict[str, Any] = {}
    stats_by_group: dict[str, dict[str, Any]] = {}
    if cohort:
        labels = work.groupby("entity")["group"].nunique()
        if (labels > 1).any():
            raise EngineError("COHORT_NOT_CONSTANT", f"Entities {list(labels[labels > 1].index[:5])} carry more "
                                                     "than one group; a cohort is fixed per entity.")
        means = work.groupby(["group", "entity"], sort=True)["outcome"].mean()
        for group in listed:
            values = means.loc[group].to_numpy(dtype="float64") if group in means.index.get_level_values(0) \
                else np.array([])
            samples[group] = values
            n = int(len(values))
            stats_by_group[group] = {"observations": n, "effective": n, "mean": float(values.mean()) if n else None,
                                     "median": float(np.median(values)) if n else None,
                                     "sd": float(values.std(ddof=1)) if n > 1 else None,
                                     "rows": int((work["group"] == group).sum())}
    else:
        per_date = work.groupby(["date", "group"], sort=True)["outcome"].mean().reset_index()
        labels = per_date.groupby("date")["group"].nunique()
        if (labels > 1).any():
            raise EngineError("REGIME_NOT_CONSTANT", "A regime is a property of the date; some dates carry more "
                                                     "than one group.")
        keys = _date_keys(per_date["date"])
        calendar = _calendar(keys)
        for group in listed:
            mask = (per_date["group"] == group).to_numpy()
            values = per_date["outcome"].to_numpy(dtype="float64")[mask]
            group_dates = [k for k, flag in zip(keys, mask) if flag]
            samples[group] = values
            n = int(len(values))
            stats_by_group[group] = {"observations": n,
                                     "effective": _thinned(group_dates, calendar, horizon) if n else 0,
                                     "mean": float(values.mean()) if n else None,
                                     "median": float(np.median(values)) if n else None,
                                     "sd": float(values.std(ddof=1)) if n > 1 else None,
                                     "rows": int((work["group"] == group).sum())}
    present = [g for g in listed if stats_by_group[g]["observations"]]
    pairs: list[tuple[str, str]] = []
    if mode == "PAIRWISE":
        pairs = [(a, b) for i, a in enumerate(listed) for b in listed[i + 1:]]
    elif mode == "FIRST_VS_OTHERS":
        pairs = [(listed[0], b) for b in listed[1:]]
    else:
        pairs = [(a, f"REST_OF:{a}") for a in listed]
    candidates = []
    for a, b in pairs:
        x = samples.get(a, np.array([]))
        if b.startswith("REST_OF:"):
            y = np.concatenate([samples[g] for g in listed if g != a and len(samples[g])]) \
                if any(len(samples[g]) for g in listed if g != a) else np.array([])
            eff_b = sum(stats_by_group[g]["effective"] for g in listed if g != a)
        else:
            y = samples.get(b, np.array([]))
            eff_b = stats_by_group[b]["effective"]
        candidates.append({"candidate": f"{a} - {b}", "a": a, "b": b,
                           **_welch_values(x, y, stats_by_group[a]["effective"], eff_b)})
    m = max(int(comparisons), len(candidates))
    _with_adjusted(candidates, policy, m, "MEAN")
    primary = _best(candidates, expected_direction)
    pooled = [s for s in samples.values() if len(s) > 1]
    pooled_sd = float(np.sqrt(np.mean([s.var(ddof=1) for s in pooled]))) if pooled else None
    delta, source = _delta(min_effect, unit, "MEAN", pooled_sd)
    mde = _mde(primary.get("standard_error"), m, policy)
    effective = primary.get("effective") or 0
    small = sorted(g for g in listed if stats_by_group[g]["effective"] < ANECDOTAL_BELOW)
    return {"engine": "GROUP_COMPARISON", "method_id": method_id, "estimate_kind": "MEAN_DIFFERENCE",
            "primary": primary, "primary_is_predeclared": len(candidates) == 1, "candidates": candidates,
            "multiple_testing": _multiple_testing(policy, m, candidates),
            "sample": {"rows": int(len(work)), "effective": effective, "unit": "ENTITIES" if cohort else "DATES",
                       "flag": sample_flag(effective, mde, delta), "minimum_detectable_effect": mde,
                       "smallest_effect_of_interest": delta, "smallest_effect_source": source,
                       "small_groups": small, "entities": int(work["entity"].nunique())},
            "comparator": {"comparison": mode, "groups": listed,
                           "missing_groups": [g for g in listed if g not in present]},
            "secondary": {},
            "method_payload": {"groups": stats_by_group, "unit_of_analysis": "entity mean" if cohort
                               else "date mean", "horizon_periods": horizon}}


def _welch_values(x, y, eff_x: int, eff_y: int) -> dict[str, Any]:
    """Welch difference of two samples of independent observations (effective counts cap the degrees of freedom)."""
    import numpy as np
    from scipy import stats

    out: dict[str, Any] = {"n_a": int(len(x)), "n_b": int(len(y)), "estimate": None, "standard_error": None,
                           "df": None, "ci": None, "p_value": None, "effective": int(min(eff_x, eff_y)),
                           "degenerate": False}
    if len(x) == 0 or len(y) == 0:
        return out
    out["estimate"] = float(np.mean(x) - np.mean(y))
    n_x, n_y = max(2, min(len(x), eff_x)), max(2, min(len(y), eff_y))
    if len(x) < 2 or len(y) < 2 or eff_x < MIN_EFFECTIVE or eff_y < MIN_EFFECTIVE:
        return out
    va, vb = float(np.var(x, ddof=1)) / n_x, float(np.var(y, ddof=1)) / n_y
    se = math.sqrt(va + vb)
    if se <= 0:
        out["degenerate"] = True
        return out
    df = (va + vb) ** 2 / (va ** 2 / (n_x - 1) + vb ** 2 / (n_y - 1)) if (va or vb) else n_x + n_y - 2
    t_crit = float(stats.t.ppf(1 - ALPHA / 2, df))
    out.update(standard_error=se, df=float(df), ci=[out["estimate"] - t_crit * se, out["estimate"] + t_crit * se],
               p_value=float(2 * stats.t.sf(abs(out["estimate"] / se), df)))
    return out


# ---------------------------------------------------------------- engine 4: quantile ranking

def quantile_ranking(frame, *, method_id: str, parameters: dict[str, Any], expected_direction: str, horizon: int,
                     unit: str, min_effect: float | None, policy: str, comparisons: int) -> dict[str, Any]:
    """On every date, rank the entities by signal (ties broken by entity, so ranks are deterministic) into `buckets`
    equal-count buckets; the outcome per bucket, the top-minus-bottom spread per date and its mean over the dates
    (thinned by the horizon), the monotonicity of the bucket means and the mean per-date rank correlation (IC)."""
    import numpy as np
    from scipy import stats

    buckets = int(parameters.get("buckets") or 0)
    if not 2 <= buckets <= 10:
        raise EngineError("PARAMETER_INVALID", "quantile_ranking needs buckets between two and ten.")
    horizon = max(1, int(horizon))
    work = prepare(frame, ("signal", "outcome"), entity_required=True, numeric=("signal", "outcome"))
    valid = work[np.isfinite(work["signal"].to_numpy()) & np.isfinite(work["outcome"].to_numpy())]
    per_bucket: dict[int, list[float]] = {b: [] for b in range(buckets)}
    spreads, spread_dates, ics, ic_dates, skipped, empty = [], [], [], [], 0, 0
    for date, part in valid.groupby("date", sort=True):
        part = part.sort_values(["signal", "entity"], kind="mergesort")
        n = len(part)
        if n < buckets:
            skipped += 1
            continue
        index = (np.arange(n) * buckets) // n
        outcomes = part["outcome"].to_numpy(dtype="float64")
        means = []
        for b in range(buckets):
            chosen = outcomes[index == b]
            if len(chosen) == 0:
                empty += 1
                means.append(None)
                continue
            means.append(float(chosen.mean()))
            per_bucket[b].append(float(chosen.mean()))
        key = date.strftime("%Y-%m-%d")
        if means[0] is not None and means[-1] is not None:
            spreads.append(means[-1] - means[0])
            spread_dates.append(key)
        if np.std(part["signal"].to_numpy()) > 0 and np.std(outcomes) > 0:
            ics.append(float(stats.spearmanr(part["signal"].to_numpy(), outcomes).statistic))
            ic_dates.append(key)
    calendar = _calendar(spread_dates + ic_dates)
    effective = _thinned(spread_dates, calendar, horizon) if spreads else 0
    primary: dict[str, Any] = {"candidate": "top_minus_bottom", "estimate": float(np.mean(spreads)) if spreads
                               else None, "standard_error": None, "df": None, "ci": None, "p_value": None,
                               "effective": effective, "dates": len(spreads), "degenerate": False}
    if len(spreads) > 1 and effective >= MIN_EFFECTIVE:
        sd = float(np.std(spreads, ddof=1))
        if sd > 0:
            se = sd / math.sqrt(effective)
            df = effective - 1
            crit = float(stats.t.ppf(1 - ALPHA / 2, df))
            primary.update(standard_error=se, df=float(df), ci=[primary["estimate"] - crit * se,
                                                                primary["estimate"] + crit * se],
                           p_value=float(2 * stats.t.sf(abs(primary["estimate"] / se), df)))
        else:
            primary["degenerate"] = True
    candidates = [primary]
    m = max(int(comparisons), 1)
    _with_adjusted(candidates, policy, m, "MEAN")
    bucket_means = [float(np.mean(per_bucket[b])) if per_bucket[b] else None for b in range(buckets)]
    defined = [(b, v) for b, v in enumerate(bucket_means) if v is not None]
    rho = None
    if len(defined) >= 3 and np.std([v for _, v in defined]) > 0:
        rho = float(stats.spearmanr([b for b, _ in defined], [v for _, v in defined]).statistic)
    elif len(defined) == 2:
        rho = 1.0 if defined[1][1] > defined[0][1] else -1.0 if defined[1][1] < defined[0][1] else 0.0
    if rho is None:
        monotonic = "NOT_APPLICABLE"
    elif expected_direction == "HIGHER":
        monotonic = "PASS" if rho >= MONOTONIC_RHO else "FAIL"
    elif expected_direction == "LOWER":
        monotonic = "PASS" if rho <= -MONOTONIC_RHO else "FAIL"
    else:
        monotonic = "PASS" if abs(rho) >= MONOTONIC_RHO else "FAIL"
    ic_eff = _thinned(ic_dates, calendar, horizon) if ics else 0
    ic = {"mean": float(np.mean(ics)) if ics else None, "dates": len(ics), "effective": ic_eff, "t_stat": None}
    if len(ics) > 1 and ic_eff >= MIN_EFFECTIVE and np.std(ics, ddof=1) > 0:
        ic["t_stat"] = float(np.mean(ics) / (np.std(ics, ddof=1) / math.sqrt(ic_eff)))
    delta, source = _delta(min_effect, unit, "MEAN", float(np.std(spreads, ddof=1)) if len(spreads) > 1 else None)
    mde = _mde(primary.get("standard_error"), m, policy)
    return {"engine": "QUANTILE_RANKING", "method_id": method_id, "estimate_kind": "SPREAD",
            "primary": primary, "primary_is_predeclared": True, "candidates": candidates,
            "multiple_testing": _multiple_testing(policy, m, candidates),
            "sample": {"rows": int(len(work)), "effective": effective, "unit": "DATES",
                       "flag": sample_flag(effective, mde, delta), "minimum_detectable_effect": mde,
                       "smallest_effect_of_interest": delta, "smallest_effect_source": source,
                       "dates_skipped_too_few_entities": skipped, "empty_buckets": empty,
                       "entities": int(work["entity"].nunique())},
            "comparator": {"bottom_bucket": 1, "top_bucket": buckets},
            "secondary": {"monotonicity": monotonic},
            "method_payload": {"buckets": buckets, "bucket_mean_outcome": bucket_means,
                               "bucket_dates": [len(per_bucket[b]) for b in range(buckets)],
                               "monotonicity_rho": rho, "rank_ic": ic, "horizon_periods": horizon,
                               "ties": "ranked by signal, then entity"}}


# ---------------------------------------------------------------- engine 5: temporal dependency

def _daily_series(frame, x: str, y: str):
    """The per-date mean of each series (a panel is reduced to one series; dates are the observations)."""
    grouped = frame.groupby("date", sort=True)[[x, y]].mean()
    return grouped.index, grouped[x].to_numpy(dtype="float64"), grouped[y].to_numpy(dtype="float64")


def temporal_dependency(frame, *, method_id: str, parameters: dict[str, Any], expected_direction: str,
                        horizon: int, unit: str, min_effect: float | None, policy: str, comparisons: int
                        ) -> dict[str, Any]:
    """lead_lag: the correlation of leader at t with follower at t + k observations for every approved lag k (the
    lag curve), the predeclared lag as primary. correlation_dependency: the correlation at the predeclared lag
    (default 0), a rolling correlation over rolling_window observations, and, when the input has a condition column,
    the correlation when the condition holds against when it does not. A panel is reduced to per-date means; the
    leader value never comes from after the follower value it is paired with."""
    import numpy as np

    method = parameters.get("correlation_method") or "PEARSON"
    if method not in ("PEARSON", "SPEARMAN"):
        raise EngineError("PARAMETER_INVALID", "correlation_method must be PEARSON or SPEARMAN.")
    has_condition = "condition" in frame.columns and method_id == "correlation_dependency"
    roles = ("leader", "follower", "condition") if has_condition else ("leader", "follower")
    work = prepare(frame, roles, numeric=("leader", "follower"), boolean=("condition",) if has_condition else ())
    dates, x, y = _daily_series(work, "leader", "follower")
    if method_id == "lead_lag":
        lags = sorted({int(k) for k in parameters.get("lags") or []})
        primary_lag = parameters.get("primary_lag")
        if not lags or primary_lag is None or int(primary_lag) not in lags or any(k < 0 for k in lags):
            raise EngineError("PARAMETER_INVALID", "lead_lag needs non-negative lags and a primary_lag among them.")
    else:
        primary_lag = int(parameters.get("primary_lag") or 0)
        lags = [primary_lag]
    candidates = []
    for k in lags:
        if k >= len(x):
            candidates.append({"candidate": f"lag {k}", "lag": k, "estimate": None, "n": 0, "effective": 0,
                               "ci": None, "p_value": None, "standard_error": None, "degenerate": False})
            continue
        lead, follow = (x[:len(x) - k], y[k:]) if k else (x, y)
        candidates.append({"candidate": f"lag {k}", "lag": k, **_correlation(lead, follow, method, ALPHA)})
    conditional = None
    if has_condition:
        # a date's condition holds when it holds for every entity that date (1.0), fails for every one (0.0), else it is
        # mixed (NaN) and the date is left out of both subsets
        coded = work["condition"].map(lambda v: np.nan if v is None else 1.0 if v else 0.0).astype("float64")
        flags = coded.groupby(work["date"]).agg(lambda s: 1.0 if (s == 1.0).all() else 0.0 if (s == 0.0).all()
                                                else np.nan)
        flag = flags.reindex(dates).to_numpy(dtype="float64")
        k = int(primary_lag)
        lead, follow = (x[:len(x) - k], y[k:]) if k else (x, y)
        cond = flag[:len(lead)]
        true_mask = cond == 1.0
        false_mask = cond == 0.0
        when_true = _correlation(lead[true_mask], follow[true_mask], method, ALPHA)
        when_false = _correlation(lead[false_mask], follow[false_mask], method, ALPHA)
        difference = None
        if when_true["estimate"] is not None and when_false["estimate"] is not None \
                and abs(when_true["estimate"]) < 1 and abs(when_false["estimate"]) < 1 \
                and when_true["effective"] > 3 and when_false["effective"] > 3:
            from scipy import stats

            variance = 1.06 if method == "SPEARMAN" else 1.0
            se = math.sqrt(variance / (when_true["effective"] - 3) + variance / (when_false["effective"] - 3))
            z = math.atanh(when_true["estimate"]) - math.atanh(when_false["estimate"])
            difference = {"z_difference": z, "standard_error": se,
                          "p_value": float(2 * stats.norm.sf(abs(z) / se))}
        conditional = {"when_true": when_true, "when_false": when_false, "difference": difference}
    m = max(int(comparisons), len(candidates) + (1 if conditional and conditional["difference"] else 0))
    _with_adjusted(candidates, policy, m, "CORRELATION")
    if method_id == "lead_lag":
        primary = next(c for c in candidates if c["lag"] == int(primary_lag))
    else:
        primary = candidates[0]
    rolling = None
    window = parameters.get("rolling_window")
    if method_id == "correlation_dependency" and window:
        window = int(window)
        k = int(primary_lag)
        lead, follow = (x[:len(x) - k], y[k:]) if k else (x, y)
        values = []
        for end in range(window, len(lead) + 1):
            a, b = lead[end - window:end], follow[end - window:end]
            mask = np.isfinite(a) & np.isfinite(b)
            if mask.sum() >= 3 and np.std(a[mask]) > 0 and np.std(b[mask]) > 0:
                values.append(float(np.corrcoef(a[mask], b[mask])[0, 1]))
        rolling = {"window": window, "count": len(values), "mean": float(np.mean(values)) if values else None,
                   "min": float(np.min(values)) if values else None, "max": float(np.max(values)) if values else None,
                   "share_positive": (sum(1 for v in values if v > 0) / len(values)) if values else None,
                   "last": values[-1] if values else None}
    delta, source = _delta(min_effect, unit if min_effect is not None else "OTHER", "CORRELATION")
    from scipy import stats as _stats

    effective = primary.get("effective") or 0
    mde = None
    if effective > 3:
        alpha = adjusted_alpha(policy, m, 0)
        mde = math.tanh((float(_stats.norm.ppf(1 - alpha / 2)) + float(_stats.norm.ppf(POWER)))
                        / math.sqrt(effective - 3))
    return {"engine": "TEMPORAL_DEPENDENCY", "method_id": method_id, "estimate_kind": "CORRELATION",
            "primary": primary, "primary_is_predeclared": True, "candidates": candidates,
            "multiple_testing": _multiple_testing(policy, m, candidates),
            "sample": {"rows": int(len(work)), "dates": int(len(dates)), "effective": effective,
                       "unit": "DATES_AUTOCORRELATION_ADJUSTED", "flag": sample_flag(effective, mde, delta),
                       "minimum_detectable_effect": mde, "smallest_effect_of_interest": delta,
                       "smallest_effect_source": source, "entities": int(work["entity"].nunique())},
            "comparator": {"null": "no correlation", "predeclared_lag": int(primary_lag)},
            "secondary": {},
            "method_payload": {"method": method, "lag_curve": [{"lag": c["lag"], "r": c["estimate"], "n": c["n"],
                                                                "effective": c["effective"],
                                                                "ci_adjusted": c.get("ci_adjusted")}
                                                               for c in candidates],
                               "rolling": rolling, "conditional": conditional,
                               "panel_reduction": "per-date mean across entities"}}


ENGINES = {"CONDITIONAL_OUTCOME": conditional_outcome, "PERSISTENCE": streak_persistence,
           "GROUP_COMPARISON": group_comparison, "QUANTILE_RANKING": quantile_ranking,
           "TEMPORAL_DEPENDENCY": temporal_dependency}


# ---------------------------------------------------------------- one angle

def evaluate(method_id: str, frame, approved: dict[str, Any]) -> dict[str, Any]:
    """The engine result for one angle with its approved values: parameters, expected_direction,
    outcome_horizon_periods, outcome_unit, min_effect, multiple_testing_policy, candidate_count,
    pairwise_comparisons and, when holdout_required, holdout_start (the first date of the holdout range)."""
    if method_id not in METHODS:
        raise EngineError("METHOD_UNKNOWN", f"{method_id!r} is not a registered method.")
    expected = approved.get("expected_direction") or "DIFFERENT"
    if expected not in DIRECTIONS:
        raise EngineError("PARAMETER_INVALID", f"expected_direction must be one of {DIRECTIONS}.")
    unit = approved.get("outcome_unit") or "OTHER"
    if unit not in UNITS:
        raise EngineError("PARAMETER_INVALID", f"outcome_unit must be one of {UNITS}.")
    kwargs = {"method_id": method_id, "parameters": approved.get("parameters") or {}, "expected_direction": expected,
              "horizon": int(approved.get("outcome_horizon_periods") or 1), "unit": unit,
              "min_effect": approved.get("min_effect"), "policy": approved.get("multiple_testing_policy") or "NONE",
              "comparisons": max(int(approved.get("candidate_count") or 1),
                                 int(approved.get("pairwise_comparisons") or 0), 1)}
    engine = ENGINES[METHODS[method_id]]
    holdout = approved.get("holdout_start")
    if not holdout:
        return _clean(engine(frame, **kwargs))
    import pandas as pd

    if "date" not in getattr(frame, "columns", []):
        raise EngineError("INPUT_COLUMNS_MISSING", "The input lacks the column date.")
    start = pd.Timestamp(holdout)
    dates = pd.to_datetime(frame["date"], errors="coerce")
    inside, outside = frame[dates < start], frame[dates >= start]
    result = engine(inside, **kwargs)
    check = {"holdout_start": str(start.date()), "rows": int(len(outside))}
    try:
        out = engine(outside, **kwargs)
        estimate, held = result["primary"].get("estimate"), out["primary"].get("estimate")
        check.update(estimate=held, effective=out["primary"].get("effective"))
        agrees = estimate is not None and held is not None and (out["primary"].get("effective") or 0) >= MIN_EFFECTIVE \
            and estimate * held > 0
        result["secondary"]["holdout"] = "PASS" if agrees else "FAIL"
    except EngineError as exc:
        check["error"] = exc.code
        result["secondary"]["holdout"] = "FAIL"
    result["holdout"] = check
    return _clean(result)


def _significant(candidate: dict[str, Any], expected: str, adjusted: bool) -> str | None:
    """EXPECTED or OPPOSITE when the (adjusted) interval excludes zero, else None."""
    interval = candidate.get("ci_adjusted") if adjusted else candidate.get("ci")
    estimate = candidate.get("estimate")
    if candidate.get("degenerate") or not interval or interval[0] is None or interval[1] is None or estimate is None:
        return None
    if not (interval[0] > 0 or interval[1] < 0):
        return None
    if expected == "DIFFERENT":
        return "EXPECTED"
    return "EXPECTED" if (expected == "HIGHER") == (interval[0] > 0) else "OPPOSITE"


def decide(result: dict[str, Any], *, expected_direction: str, validation_level: str,
           minimum_sample: dict[str, Any] | None = None) -> dict[str, str]:
    """{status, reason, evidence_direction} under the multi-angle status rules (MULTI_ANGLE_RESEARCH.md §4). An
    effect against the expected direction is INSUFFICIENT_EVIDENCE with evidence_direction OPPOSITE: the plan has no
    status for evidence against a hypothesis."""
    candidates = result.get("candidates") or []
    primary = result.get("primary") or {}
    sample = result.get("sample") or {}
    flag = sample.get("flag")
    adjusted = {c.get("candidate"): _significant(c, expected_direction, True) for c in candidates}
    raw = {c.get("candidate"): _significant(c, expected_direction, False) for c in candidates}
    opposite = any(v == "OPPOSITE" for v in adjusted.values())
    direction = "NONE"
    primary_adjusted = adjusted.get(primary.get("candidate"))
    primary_raw = raw.get(primary.get("candidate"))
    if primary_adjusted or primary_raw:
        direction = primary_adjusted or primary_raw
    elif opposite:
        direction = "OPPOSITE"

    def out(status: str, reason: str) -> dict[str, str]:
        return {"status": status, "reason": reason, "evidence_direction": direction}

    if validation_level == "EXECUTION_ONLY":
        return out("INSUFFICIENT_EVIDENCE", "EXECUTION_ONLY_NOT_VERIFIABLE")
    if flag == "INSUFFICIENT":
        return out("INSUFFICIENT_EVIDENCE", "INSUFFICIENT_SAMPLE")
    if flag == "ANECDOTAL":
        return out("INSUFFICIENT_EVIDENCE", "ANECDOTAL_SAMPLE")
    if minimum_sample and minimum_sample.get("value") is not None:
        unit = minimum_sample.get("unit")
        observed = sample.get("condition_rows") if unit == "EVENTS" and sample.get("condition_rows") is not None \
            else sample.get("entities") if unit == "ENTITIES" else sample.get("rows")
        if observed is not None and observed < int(minimum_sample["value"]):
            return out("INSUFFICIENT_EVIDENCE", "MINIMUM_SAMPLE_NOT_MET")
    expected_any = any(v == "EXPECTED" for v in adjusted.values())
    if expected_any:
        secondary = [v for v in (result.get("secondary") or {}).values() if v not in ("PASS", "NOT_APPLICABLE")]
        if result.get("primary_is_predeclared") and primary_adjusted != "EXPECTED":
            return out("PARTIALLY_SUPPORTED", "NOT_AT_PREDECLARED_CANDIDATE")
        if opposite:
            return out("PARTIALLY_SUPPORTED", "CANDIDATES_DISAGREE")
        if secondary:
            failed = sorted(k for k, v in (result.get("secondary") or {}).items() if v not in ("PASS",
                                                                                               "NOT_APPLICABLE"))
            return out("PARTIALLY_SUPPORTED", "SECONDARY_CHECK_FAILED:" + ",".join(failed))
        return out("SUPPORTED", "EFFECT_IN_EXPECTED_DIRECTION")
    if any(v == "EXPECTED" for v in raw.values()) and not opposite:
        return out("PARTIALLY_SUPPORTED", "MULTIPLE_TESTING_NOT_PASSED")
    if opposite:
        return out("INSUFFICIENT_EVIDENCE", "EFFECT_OPPOSITE_TO_EXPECTED")
    if all(c.get("ci") is None for c in candidates):
        return out("INSUFFICIENT_EVIDENCE", "NO_UNCERTAINTY_ESTIMATE")
    if flag == "ADEQUATE":
        return out("INSUFFICIENT_EVIDENCE", "NO_DISTINGUISHABLE_EFFECT")
    return out("INSUFFICIENT_EVIDENCE", "UNDERPOWERED_NO_SIGNIFICANT_EFFECT")
