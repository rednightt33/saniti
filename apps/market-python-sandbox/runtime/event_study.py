"""Event study (G2, user decision 2026-10-02): the outcome after an event against a baseline, one implementation shared
by the session helper saniti.event_study() and the harness that recomputes it (app/event_study_validation.py).

The input is the canonical frame research_inputs.build() makes from a declaration over one governed data request:
columns date, entity, condition (True / False / None) and outcome (the backend's forward return over the horizon).

    events     condition True with a defined outcome; NON_OVERLAPPING keeps an entity's next event only when it is at
               least `horizon` of that entity's observations after the previous kept event (an overlapping outcome is
               the same move counted twice); ALL keeps every one
    censored   condition True whose outcome runs past the delivered data (not counted)
    baseline   ALL_ELIGIBLE: every row with a defined condition and outcome (the Analysis Spec EVENT_STUDY convention);
               NON_EVENT: those rows without the condition
    segments   ALL, and IN_SAMPLE / OUT_OF_SAMPLE split at holdout_start when one is given

Uncertainty follows the research engines (runtime/research_engines.py): rows on one date are one cluster and dates
closer than the horizon overlap, so the difference of means uses the spread of per-date means over the effective
(thinned) date counts (Welch). The Analysis Spec version treated every row as independent; a market-wide day with many
events is one observation here.

Nothing in this module names a table, a column, an entity or an asset: the event, the outcome and the horizon come
from the caller's declaration.
"""
from __future__ import annotations

import sys
from typing import Any

VERSION = 1
OVERLAP_POLICIES = ("NON_OVERLAPPING", "ALL")
BASELINES = ("ALL_ELIGIBLE", "NON_EVENT")
DEFAULT_MIN_EVENTS = 30  # the Analysis Spec default (DEFAULT_EVENT_MIN_EVENTS); a policy value, reported in the result
SUMMARY_COLUMNS = ("segment", "event_count", "event_dates", "effective_event_dates", "mean", "median", "hit_rate",
                   "baseline_count", "baseline_mean", "baseline_median", "delta_mean", "delta_ci_low",
                   "delta_ci_high", "delta_p_value", "censored_count", "overlapping_dropped", "meets_min_events")
COUNT_COLUMNS = ("event_count", "event_dates", "effective_event_dates", "baseline_count", "censored_count",
                 "overlapping_dropped")
EVENT_COLUMNS = ("date", "entity", "outcome")


class EventStudyError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _engines():
    """runtime/research_engines.py: by name in a session; the harness loads it first under a private name."""
    module = sys.modules.get("saniti_runtime_research_engines")
    if module is None:
        import research_engines as module
    return module


def parameters(horizon: Any, overlap_policy: Any = "NON_OVERLAPPING", baseline: Any = "ALL_ELIGIBLE",
               min_events: Any = None, holdout_start: Any = None) -> dict[str, Any]:
    """The checked parameters, or EventStudyError."""
    import datetime as dt

    if isinstance(horizon, bool) or not isinstance(horizon, int) or not 1 <= horizon <= 260:
        raise EventStudyError("PARAMETER_INVALID", "horizon is a whole number of observations from 1 to 260.")
    if overlap_policy not in OVERLAP_POLICIES:
        raise EventStudyError("PARAMETER_INVALID", f"overlap_policy is one of {OVERLAP_POLICIES}.")
    if baseline not in BASELINES:
        raise EventStudyError("PARAMETER_INVALID", f"baseline is one of {BASELINES}.")
    minimum = DEFAULT_MIN_EVENTS if min_events is None else min_events
    if isinstance(minimum, bool) or not isinstance(minimum, int) or minimum < 1:
        raise EventStudyError("PARAMETER_INVALID", "min_events is a whole number of at least 1.")
    start = None
    if holdout_start is not None:
        try:
            start = dt.date.fromisoformat(str(holdout_start)).isoformat()
        except ValueError:
            raise EventStudyError("PARAMETER_INVALID", "holdout_start is a date YYYY-MM-DD.") from None
    return {"horizon": horizon, "overlap_policy": overlap_policy, "baseline": baseline, "min_events": minimum,
            "holdout_start": start}


def build_input(inputs, declaration: dict[str, Any], rows, *, entity_column: str | None, time_column: str,
                columns: list[str], ranges: list[dict[str, Any]], horizon: int, unit: str,
                related: dict[str, dict[str, Any]] | None = None) -> tuple[Any, dict[str, Any]]:
    """The canonical frame (date, entity, condition, outcome) of the chosen ranges, each range built on its own
    extracted window: a forward return never reads the rows of another range (two ranges of one request are often a
    year apart, and a forward return counted by position would join them). inputs is runtime/research_inputs.py."""
    import pandas as pd

    spans = sorted((pd.Timestamp(w["start"]), pd.Timestamp(w["end"])) for w in ranges)
    if any(later[0] <= earlier[1] for earlier, later in zip(spans, spans[1:])):
        raise EventStudyError("RANGES_OVERLAP", "The request's ranges overlap; choose one with range_id.")

    def within(frame, time: str, low, high):
        dates = pd.to_datetime(frame[time], errors="coerce").dt.normalize()
        if getattr(dates.dt, "tz", None) is not None:
            dates = dates.dt.tz_localize(None)
        return frame[(dates >= low) & (dates <= high)]

    frames, info = [], {"rows": 0, "censored_outcome_rows": 0, "forward_horizon": None, "expressions": None,
                        "outcome_source": None, "ranges": []}
    for window in ranges:
        low = pd.Timestamp(window.get("extract_from") or window["start"])
        high = pd.Timestamp(window.get("extract_to") or window["end"])
        nearby = {rid: {**other, "rows": within(other["rows"], other["time_column"], low, high)}
                  for rid, other in (related or {}).items()}
        frame, part = inputs.build("conditional_distribution", declaration, within(rows, time_column, low, high),
                                   entity_column=entity_column, time_column=time_column, columns=columns,
                                   windows=[(window["start"], window["end"])], horizon=horizon, unit=unit,
                                   related=nearby)
        frames.append(frame)
        info["rows"] += int(part.get("rows") or 0)
        info["censored_outcome_rows"] += int(part.get("censored_outcome_rows") or 0)
        info.update({k: part.get(k) for k in ("forward_horizon", "expressions", "outcome_source")})
        info["ranges"].append({"range_id": window.get("range_id"), "rows": int(part.get("rows") or 0)})
    frame = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["date", "entity", "condition",
                                                                                      "outcome"])
    frame = frame.sort_values(["entity", "date"], kind="mergesort").reset_index(drop=True)
    return frame, info


def _masks(frame, horizon: int, overlap_policy: str):
    import numpy as np

    condition = frame["condition"].to_numpy(dtype=object)
    outcome = frame["outcome"].to_numpy(dtype="float64")
    known = np.array([c is not None for c in condition])
    finite = np.isfinite(outcome)
    true = np.array([c is True or c == True for c in condition], dtype=bool)  # noqa: E712 - numpy bools
    eligible = known & finite
    candidate = true & finite
    censored = true & ~finite
    kept = candidate.copy()
    if overlap_policy == "NON_OVERLAPPING":
        entities = frame["entity"].to_numpy(dtype=object)
        last: dict[Any, int] = {}
        position: dict[Any, int] = {}
        for i in range(len(frame)):
            entity = entities[i]
            here = position.get(entity, -1) + 1
            position[entity] = here
            if not candidate[i]:
                continue
            previous = last.get(entity)
            if previous is not None and here - previous < horizon:
                kept[i] = False
                continue
            last[entity] = here
    return eligible, true, kept, censored, candidate & ~kept


def summarize(frame, params: dict[str, Any], alpha: float | None = None) -> tuple[list[dict[str, Any]], Any]:
    """(summary rows, one per segment, in SUMMARY_COLUMNS; the kept events as a frame of EVENT_COLUMNS)."""
    import numpy as np
    import pandas as pd

    E = _engines()
    alpha = E.ALPHA if alpha is None else alpha
    missing = [c for c in ("date", "entity", "condition", "outcome") if c not in frame.columns]
    if missing:
        raise EventStudyError("INPUT_COLUMNS_MISSING", f"The event-study input lacks {missing}.")
    work = frame.reset_index(drop=True)
    work = work.assign(date=pd.to_datetime(work["date"]).dt.normalize())
    if work.duplicated(["entity", "date"]).any():
        # a forward return counts observations of one series per entity; two rows on one date make it ambiguous
        raise EventStudyError("DUPLICATE_ENTITY_DATE", "The request has more than one row per entity and date, so "
                                                       "the forward return is ambiguous: use a request with one row "
                                                       "per entity and date (or narrow its scope).")
    horizon = params["horizon"]
    eligible, true, kept, censored, dropped = _masks(work, horizon, params["overlap_policy"])
    baseline = eligible if params["baseline"] == "ALL_ELIGIBLE" else eligible & ~true
    keys = E._date_keys(work["date"])
    calendar = E._calendar(keys)
    outcome = work["outcome"].to_numpy(dtype="float64")
    segments = [("ALL", np.ones(len(work), dtype=bool))]
    if params.get("holdout_start"):
        cut = (work["date"] >= pd.Timestamp(params["holdout_start"])).to_numpy()
        segments += [("IN_SAMPLE", ~cut), ("OUT_OF_SAMPLE", cut)]
    rows = []
    for name, mask in segments:
        ev_mask, base_mask = kept & mask, baseline & mask
        ev = E._group_stats(outcome[ev_mask], [k for k, m in zip(keys, ev_mask) if m], calendar, horizon)
        base = E._group_stats(outcome[base_mask], [k for k, m in zip(keys, base_mask) if m], calendar, horizon)
        diff = E._welch(ev, base, alpha)
        ci = diff.get("ci") or [None, None]
        rows.append({
            "segment": name, "event_count": ev["rows"], "event_dates": ev["dates"],
            "effective_event_dates": ev["effective"], "mean": ev["mean"], "median": ev["median"],
            "hit_rate": ev.get("hit_rate"), "baseline_count": base["rows"], "baseline_mean": base["mean"],
            "baseline_median": base["median"], "delta_mean": diff["estimate"], "delta_ci_low": ci[0],
            "delta_ci_high": ci[1], "delta_p_value": diff["p_value"],
            "censored_count": int((censored & mask).sum()), "overlapping_dropped": int((dropped & mask).sum()),
            "meets_min_events": bool(ev["rows"] >= params["min_events"])})
    events = work.loc[kept, ["date", "entity", "outcome"]].reset_index(drop=True)
    return [{k: E._clean(v) for k, v in row.items()} for row in rows], events


def baseline_rows(frame, params: dict[str, Any]):
    """The baseline rows of a study (date, entity, outcome), for a hypothesis test of the same events (G3:
    event_summary(events, baseline, ...))."""
    import pandas as pd

    work = frame.reset_index(drop=True)
    work = work.assign(date=pd.to_datetime(work["date"]).dt.normalize())
    eligible, true, _, _, _ = _masks(work, params["horizon"], params["overlap_policy"])
    chosen = eligible if params["baseline"] == "ALL_ELIGIBLE" else eligible & ~true
    return work.loc[chosen, list(EVENT_COLUMNS)].reset_index(drop=True)


def compare(released, recomputed: list[dict[str, Any]], rtol: float = 1e-9, atol: float = 1e-12
            ) -> list[dict[str, Any]]:
    """The cells of the released summary that differ from the recomputed one (counts exactly, numbers within rtol)."""
    import math

    by_segment = {r["segment"]: r for r in recomputed}
    mismatches = []
    seen = set()
    for row in released:
        segment = row.get("segment")
        seen.add(segment)
        want = by_segment.get(segment)
        if want is None:
            mismatches.append({"segment": segment, "column": "segment", "expected": None, "actual": segment})
            continue
        for column in SUMMARY_COLUMNS[1:]:
            actual, expected = row.get(column), want.get(column)
            if isinstance(expected, bool) or isinstance(actual, bool):
                same = bool(actual) == bool(expected)
            elif expected is None or actual is None or (isinstance(actual, float) and math.isnan(actual)):
                same = (expected is None) == (actual is None or (isinstance(actual, float) and math.isnan(actual)))
            elif column in COUNT_COLUMNS:
                same = int(actual) == int(expected)
            else:
                same = math.isclose(float(actual), float(expected), rel_tol=rtol, abs_tol=atol)
            if not same:
                mismatches.append({"segment": segment, "column": column, "expected": expected, "actual": actual})
    for segment in by_segment:
        if segment not in seen:
            mismatches.append({"segment": segment, "column": "segment", "expected": segment, "actual": None})
    return mismatches


def compare_events(released, recomputed, rtol: float = 1e-9, atol: float = 1e-12) -> list[dict[str, Any]]:
    """The rows of the released events table that differ from the recomputed events (same order: entity, date)."""
    import math

    import pandas as pd

    want = [(pd.Timestamp(d).date().isoformat(), str(e), float(o)) for d, e, o in
            zip(recomputed["date"], recomputed["entity"], recomputed["outcome"])]
    mismatches = []
    if len(released) != len(want):
        mismatches.append({"row": None, "column": "rows", "expected": len(want), "actual": len(released)})
    for i, (row, (date, entity, outcome)) in enumerate(zip(released, want)):
        try:
            got = (pd.Timestamp(row.get("date")).date().isoformat(), str(row.get("entity")), float(row.get("outcome")))
        except (TypeError, ValueError):
            mismatches.append({"row": i, "column": "row", "expected": [date, entity, outcome], "actual": row})
            continue
        if got[:2] != (date, entity) or not math.isclose(got[2], outcome, rel_tol=rtol, abs_tol=atol):
            mismatches.append({"row": i, "column": "row", "expected": [date, entity, outcome], "actual": list(got)})
    return mismatches
