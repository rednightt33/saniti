"""Research findings statistics (version 1), shared by the session helper saniti.event_summary() and the harness.

A condition -> outcome experiment is summarised from one table of per-date aggregates, one row per group and date:
group (CONDITION or BASELINE), date, n (rows with an outcome), total (sum of outcomes), total_sq (sum of squares),
k (rows whose outcome counts as a success) and m (rows with a defined success). The session helper builds it from
the model's event and baseline rows; the harness recomputes everything below from the released table with the
approved plan's parameters, so the reported sample category and verdict never come from the model.

Two angles:
  A  effect size: mean outcome after the condition against the baseline mean (difference, CI, p-value);
  B  event lookback: the share of condition rows whose outcome is a success against the baseline share.

Dependence: rows on one date are one cluster (a market-wide day is one observation, not hundreds), and outcomes that
span horizon_periods overlap, so the effective sample is the number of distinct dates left after keeping only dates
at least horizon_periods apart on the table's own calendar. Standard errors use the spread of per-date means over
that effective count (an approximation of cluster-robust errors; correlation across nearby dates beyond the horizon
is not modelled). Proportions use Wilson intervals on the effective count and Newcombe's interval for the difference.

Sample category (fixed): INSUFFICIENT (effective count below 2 in a group: no verdict), ANECDOTAL (below 10),
UNDERPOWERED (the minimum detectable effect exceeds the smallest effect of interest), ADEQUATE.
Verdict (fixed): ANECDOTAL -> INCONCLUSIVE; a CI excluding zero in the expected direction -> SUPPORTED, or
PARTIALLY_SUPPORTED (BELOW_USER_MINIMUM_EFFECT) when the difference is smaller than the minimum effect the user named
(M26 option B, 2026-10-05); in the other direction -> NOT_SUPPORTED; a CI including zero -> NOT_SUPPORTED when ADEQUATE,
INCONCLUSIVE when UNDERPOWERED.
"""
from __future__ import annotations

import math
from typing import Any

VERSION = 1
GROUPS = ("CONDITION", "BASELINE")
AGGREGATE_COLUMNS = ("group", "date", "n", "total", "total_sq", "k", "m")
DIRECTIONS = ("HIGHER", "LOWER", "DIFFERENT")
UNITS = ("PERCENT", "DECIMAL", "OTHER")
POLICIES = ("NONE", "BONFERRONI", "HOLM", "BENJAMINI_HOCHBERG")
FLAGS = ("INSUFFICIENT", "ANECDOTAL", "UNDERPOWERED", "ADEQUATE")
# M26 option B (user decision 2026-10-05): PARTIALLY_SUPPORTED when the effect is in the expected direction but smaller
# than the minimum effect the user named (min_effect, in the outcome's unit)
VERDICTS = ("SUPPORTED", "PARTIALLY_SUPPORTED", "NOT_SUPPORTED", "INCONCLUSIVE", "NOT_EVALUATED")
BELOW_USER_MINIMUM = "BELOW_USER_MINIMUM_EFFECT"
MIN_EFFECTIVE = 2
ANECDOTAL_BELOW = 10
ALPHA = 0.05
POWER = 0.80
# smallest effect of interest when the plan names none: an IDX round-trip trading cost for returns, else a small
# standardized effect (0.2 standard deviations)
DEFAULT_MIN_EFFECT = {"PERCENT": 0.5, "DECIMAL": 0.005}
SMALL_STANDARDIZED_EFFECT = 0.2
VALUE_UNITS = {"PERCENT": "PERCENT", "DECIMAL": "FRACTION"}


def summary_units(outcome_unit: str) -> dict[str, str]:
    """P23 (2026-10-02): {field path: FRACTION | PERCENT | P_VALUE} of a summary, so the answer formats each figure
    by its unit: angle A and the group means are in the outcome unit (none for OTHER), angle B's rates are shares."""
    unit = VALUE_UNITS.get(outcome_unit)
    outcome = {path: unit for path in (
        "angle_a.condition_mean", "angle_a.baseline_mean", "angle_a.difference", "angle_a.ci_low", "angle_a.ci_high",
        "angle_a.standard_error", "mean", "median", "sd", "sample.minimum_detectable_effect",
        "sample.smallest_effect_of_interest")} if unit else {}
    shares = {path: "FRACTION" for path in (
        "angle_b.condition_rate", "angle_b.baseline_rate", "angle_b.difference", "angle_b.ci_low", "angle_b.ci_high",
        "angle_b.condition_ci", "angle_b.baseline_ci", "success_rate")}
    return {**outcome, **shares, "p_value": "P_VALUE"}


class ResearchStatsError(ValueError):
    pass


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


SUCCESS_OPERATORS = (">=", ">", "<=", "<")


def success_mask(outcome, rule: dict[str, Any]):
    """M28: outcome compared with the approved success rule {operator, value} (NaN where the outcome is missing)."""
    import numpy as np

    operator, value = rule.get("operator"), float(rule.get("value"))
    if operator not in SUCCESS_OPERATORS:
        raise ResearchStatsError(f"success_rule operator {operator!r} is not one of {list(SUCCESS_OPERATORS)}.")
    compare = {">=": np.greater_equal, ">": np.greater, "<=": np.less_equal, "<": np.less}[operator]
    return compare(outcome, value)


def aggregate(events, baseline, outcome_column: str, date_column: str, success_column: str | None = None,
              success_above: float = 0.0, success_rule: dict[str, Any] | None = None):
    """Per-date aggregates of the condition rows (events) and the baseline rows. A success is success_column when
    given (boolean), else the outcome compared by success_rule ({operator, value}, M28) when given, else
    outcome > success_above."""
    import numpy as np
    import pandas as pd

    parts = []
    for group, frame in (("CONDITION", events), ("BASELINE", baseline)):
        if not isinstance(frame, pd.DataFrame):
            raise ResearchStatsError(f"The {group.lower()} rows must be a pandas DataFrame.")
        missing = [c for c in (outcome_column, date_column, success_column) if c and c not in frame.columns]
        if missing:
            raise ResearchStatsError(f"The {group.lower()} rows lack the columns {missing}.")
        outcome = pd.to_numeric(frame[outcome_column], errors="coerce").astype("float64")
        dates = pd.to_datetime(frame[date_column], errors="coerce").dt.normalize()
        if success_column:
            raw = frame[success_column]
            success = raw.map(lambda v: None if v is None or (isinstance(v, float) and math.isnan(v)) else bool(v))
        else:
            rule = success_rule or {"operator": ">", "value": float(success_above)}
            success = pd.Series(np.where(outcome.notna(), success_mask(outcome.to_numpy(), rule), None),
                                index=frame.index)
        work = pd.DataFrame({"date": dates, "outcome": outcome, "success": success})
        work = work[work["date"].notna()]
        valid = work["outcome"].notna()
        defined = work["success"].notna()
        table = pd.DataFrame({
            "n": valid.groupby(work["date"]).sum(),
            "total": work["outcome"].where(valid, 0.0).groupby(work["date"]).sum(),
            "total_sq": (work["outcome"].where(valid, 0.0) ** 2).groupby(work["date"]).sum(),
            "k": (work["success"].where(defined, False).astype(bool) & defined).groupby(work["date"]).sum(),
            "m": defined.groupby(work["date"]).sum()}).reset_index()
        table.insert(0, "group", group)
        parts.append(table[(table["n"] > 0) | (table["m"] > 0)])
    out = pd.concat(parts, ignore_index=True)
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    for column in ("n", "k", "m"):
        out[column] = out[column].astype("int64")
    return out[list(AGGREGATE_COLUMNS)].sort_values(["group", "date"], kind="mergesort").reset_index(drop=True)


def _thinned(dates: list[str], calendar: dict[str, int], horizon: int) -> int:
    """Distinct dates kept when each kept date is at least `horizon` calendar positions after the previous one."""
    kept, last = 0, None
    for date in sorted(set(dates), key=lambda d: calendar[d]):
        position = calendar[date]
        if last is None or position - last >= horizon:
            kept, last = kept + 1, position
    return kept


def _wilson(k: float, n: float, z: float) -> tuple[float | None, float | None]:
    if n <= 0:
        return None, None
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centre - half), min(1.0, centre + half)


def summarize(table, *, horizon_periods: int = 1, expected_direction: str = "HIGHER", outcome_unit: str = "PERCENT",
              min_effect: float | None = None, comparisons: int = 1, multiple_testing_policy: str = "NONE"
              ) -> dict[str, Any]:
    """Both angles, the effective sample, the minimum detectable effect, the sample category and the verdict."""
    import pandas as pd
    from scipy import stats

    if not isinstance(table, pd.DataFrame) or list(table.columns) != list(AGGREGATE_COLUMNS):
        raise ResearchStatsError(f"The aggregate table must have exactly the columns {list(AGGREGATE_COLUMNS)}.")
    if expected_direction not in DIRECTIONS:
        raise ResearchStatsError(f"expected_direction must be one of {DIRECTIONS}.")
    if outcome_unit not in UNITS:
        raise ResearchStatsError(f"outcome_unit must be one of {UNITS}.")
    if multiple_testing_policy not in POLICIES:
        raise ResearchStatsError(f"multiple_testing_policy must be one of {POLICIES}.")
    horizon = max(1, int(horizon_periods))
    comparisons = max(1, int(comparisons))
    alpha = ALPHA if multiple_testing_policy == "NONE" or comparisons == 1 else ALPHA / comparisons
    z_alpha = float(stats.norm.ppf(1 - alpha / 2))
    z_power = float(stats.norm.ppf(POWER))
    calendar = {d: i for i, d in enumerate(sorted(set(table["date"].astype(str))))}

    groups: dict[str, dict[str, Any]] = {}
    for group in GROUPS:
        rows = table[table["group"] == group]
        n = int(rows["n"].sum())
        total, total_sq = float(rows["total"].sum()), float(rows["total_sq"].sum())
        mean = total / n if n else None
        sd = math.sqrt(max(0.0, (total_sq - n * mean * mean) / (n - 1))) if n > 1 else None
        with_outcome = rows[rows["n"] > 0]
        date_means = (with_outcome["total"] / with_outcome["n"]).astype("float64")
        sd_dates = float(date_means.std(ddof=1)) if len(date_means) > 1 else None
        effective = _thinned([str(d) for d in with_outcome["date"]], calendar, horizon)
        k, m = int(rows["k"].sum()), int(rows["m"].sum())
        groups[group] = {"rows": n, "dates": int(len(with_outcome)), "effective": effective, "mean": mean, "sd": sd,
                         "sd_of_date_means": _finite(sd_dates), "successes": k, "success_defined": m,
                         "success_rate": (k / m) if m else None}
    cond, base = groups["CONDITION"], groups["BASELINE"]
    effective = min(cond["effective"], base["effective"])

    def se_of(g: dict[str, Any]) -> float | None:
        if g["effective"] < MIN_EFFECTIVE or g["sd_of_date_means"] is None:
            return None
        return g["sd_of_date_means"] / math.sqrt(g["effective"])

    angle_a: dict[str, Any] = {"condition_mean": cond["mean"], "baseline_mean": base["mean"], "difference": None,
                               "ci_low": None, "ci_high": None, "p_value": None, "standard_error": None}
    se_c, se_b = se_of(cond), se_of(base)
    if cond["mean"] is not None and base["mean"] is not None:
        angle_a["difference"] = cond["mean"] - base["mean"]
    if angle_a["difference"] is not None and se_c is not None and se_b is not None:
        se = math.sqrt(se_c ** 2 + se_b ** 2)
        if se > 0:
            denominator = se_c ** 4 / (cond["effective"] - 1) + se_b ** 4 / (base["effective"] - 1)
            df = se ** 4 / denominator if denominator > 0 else float(effective - 1)
            t_crit = float(stats.t.ppf(1 - alpha / 2, df))
            angle_a.update(standard_error=se, degrees_of_freedom=df,
                           ci_low=angle_a["difference"] - t_crit * se, ci_high=angle_a["difference"] + t_crit * se,
                           p_value=float(2 * stats.t.sf(abs(angle_a["difference"] / se), df)))
        else:
            angle_a.update(standard_error=0.0, ci_low=angle_a["difference"], ci_high=angle_a["difference"])

    angle_b: dict[str, Any] = {"condition_rate": cond["success_rate"], "baseline_rate": base["success_rate"],
                               "difference": None, "ci_low": None, "ci_high": None, "p_value": None}
    if cond["success_rate"] is not None and base["success_rate"] is not None \
            and cond["effective"] >= 1 and base["effective"] >= 1:
        p_c, p_b = cond["success_rate"], base["success_rate"]
        n_c, n_b = cond["effective"], base["effective"]
        l_c, u_c = _wilson(p_c * n_c, n_c, z_alpha)
        l_b, u_b = _wilson(p_b * n_b, n_b, z_alpha)
        diff = p_c - p_b
        angle_b.update(difference=diff, condition_ci=[l_c, u_c], baseline_ci=[l_b, u_b],
                       ci_low=diff - math.sqrt((p_c - l_c) ** 2 + (u_b - p_b) ** 2),
                       ci_high=diff + math.sqrt((u_c - p_c) ** 2 + (p_b - l_b) ** 2))
        pooled = (p_c * n_c + p_b * n_b) / (n_c + n_b)
        spread = math.sqrt(pooled * (1 - pooled) * (1 / n_c + 1 / n_b))
        if spread > 0:
            angle_b["p_value"] = float(2 * stats.norm.sf(abs(diff) / spread))

    if min_effect is not None and _finite(min_effect) is not None and float(min_effect) > 0:
        delta, delta_source = float(min_effect), "PLAN"
    elif outcome_unit in DEFAULT_MIN_EFFECT:
        delta, delta_source = DEFAULT_MIN_EFFECT[outcome_unit], "ROUND_TRIP_TRADING_COST"
    else:
        pooled_sd = math.sqrt(((cond["sd"] or 0.0) ** 2 + (base["sd"] or 0.0) ** 2) / 2)
        delta, delta_source = (SMALL_STANDARDIZED_EFFECT * pooled_sd or None), "SMALL_STANDARDIZED_EFFECT"
    sigma = None
    if cond["sd_of_date_means"] is not None and base["sd_of_date_means"] is not None:
        sigma = math.sqrt((cond["sd_of_date_means"] ** 2 + base["sd_of_date_means"] ** 2) / 2)
    recommended = math.ceil(2 * ((z_alpha + z_power) * sigma / delta) ** 2) if sigma and delta else None
    mde = (z_alpha + z_power) * angle_a["standard_error"] if angle_a["standard_error"] is not None else None

    if effective < MIN_EFFECTIVE:
        flag = "INSUFFICIENT"
    elif effective < ANECDOTAL_BELOW:
        flag = "ANECDOTAL"
    elif mde is None or delta is None or mde > delta:
        flag = "UNDERPOWERED"
    else:
        flag = "ADEQUATE"

    difference, low, high = angle_a["difference"], angle_a["ci_low"], angle_a["ci_high"]
    if flag == "INSUFFICIENT" or difference is None:
        verdict, reason = "NOT_EVALUATED", "FEWER_THAN_TWO_INDEPENDENT_OBSERVATIONS"
    elif flag == "ANECDOTAL":
        verdict, reason = "INCONCLUSIVE", "ANECDOTAL_SAMPLE"
    elif low is None or high is None:
        verdict, reason = "INCONCLUSIVE", "NO_UNCERTAINTY_ESTIMATE"
    elif low > 0 or high < 0:
        agrees = expected_direction == "DIFFERENT" or (expected_direction == "HIGHER") == (low > 0)
        verdict, reason = ("SUPPORTED", "EFFECT_IN_EXPECTED_DIRECTION") if agrees else \
            ("NOT_SUPPORTED", "EFFECT_OPPOSITE_TO_EXPECTED")
        directed = -difference if expected_direction == "LOWER" else abs(difference) \
            if expected_direction == "DIFFERENT" else difference
        if verdict == "SUPPORTED" and delta_source == "PLAN" and delta is not None and directed < delta:
            verdict, reason = "PARTIALLY_SUPPORTED", BELOW_USER_MINIMUM
    elif flag == "ADEQUATE":
        verdict, reason = "NOT_SUPPORTED", "NO_EFFECT_AS_LARGE_AS_THE_SMALLEST_EFFECT_OF_INTEREST"
    else:
        verdict, reason = "INCONCLUSIVE", "UNDERPOWERED_NO_SIGNIFICANT_EFFECT"
    disagree = bool(difference is not None and angle_b["difference"] is not None and difference != 0
                    and angle_b["difference"] != 0 and (difference > 0) != (angle_b["difference"] > 0))
    return {"version": VERSION,
            "parameters": {"horizon_periods": horizon, "expected_direction": expected_direction,
                           "outcome_unit": outcome_unit, "comparisons": comparisons,
                           "multiple_testing_policy": multiple_testing_policy, "alpha": ALPHA,
                           "alpha_adjusted": alpha, "power": POWER},
            "groups": groups, "angle_a": angle_a, "angle_b": angle_b,
            "sample": {"effective": effective, "flag": flag, "minimum_detectable_effect": mde,
                       "smallest_effect_of_interest": delta, "smallest_effect_source": delta_source,
                       "recommended_effective_per_group": recommended,
                       "thresholds": {"insufficient_below": MIN_EFFECTIVE, "anecdotal_below": ANECDOTAL_BELOW}},
            "verdict": verdict, "verdict_reason": reason, "angles_disagree": disagree}
