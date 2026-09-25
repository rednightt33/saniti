"""Independent validation of one analysis, run by the harness in its own confined process.

It runs as a dedicated non-root validator user with the same rlimits and seccomp filter as an
analysis, only after the analysis process has exited, and it reads only harness-written files:
the workspace manifest, the approved spec, the read-only input Parquet, and harness copies of the
outputs the spec declares. It never trusts anything the analysis code reported about itself.

    preflight   inputs + spec   -> resolved period, universe, warm-up and duplicate evidence;
                                   blocking problems stop the analysis before it runs
    postflight  + outputs       -> actual scope of every declared output, gap classification,
                                   reference recalculation of supported methods, statuses
    selftest                    -> proves this process is confined like an analysis

Output: validation/result/<mode>.json.
"""
from __future__ import annotations

import itertools
import json
import math
import os
import sys
from datetime import timedelta
from typing import Any

RTOL, ATOL = 1e-6, 1e-8
MAX_VALUE_CHECKS = 500_000
MAX_LIST = 20
MAX_EXAMPLES = 5
STALE_GRACE_DAYS = 7
FAILED_CODES = ("REQUIRED_OUTPUT_MISSING", "OUTPUT_GRAIN_VIOLATION", "ANALYSIS_SCOPE_MISMATCH", "UNIVERSE_MISMATCH",
                "CALCULATION_MISMATCH", "SELECTION_MISMATCH", "TEMPORAL_LEAKAGE_DETECTED", "GROUP_COVERAGE_MISMATCH",
                "GROUP_KEY_AMBIGUOUS", "RANKING_MISMATCH")
NULL_KEY = "<NULL>"
EVENT_COLUMNS = ("event_count", "mean", "median", "hit_rate", "baseline_count", "baseline_mean", "baseline_median",
                 "delta_mean", "censored_count", "overlapping_dropped")
COUNT_COLUMNS = ("event_count", "baseline_count", "censored_count", "overlapping_dropped")
DEFAULT_THRESHOLDS = {"min_events": 30, "min_baseline_observations": 100, "min_coverage_pct": 95}
INCOMPLETE_CODES = ("INSUFFICIENT_WARMUP_HISTORY", "SOURCE_PERIOD_UNAVAILABLE", "UNIVERSE_SOURCE_UNAVAILABLE",
                    "SCOPE_EMPTY", "SEGMENT_EMPTY")
NUMERIC_TYPES = ("smallint", "integer", "bigint", "numeric", "real", "double precision")
PERIOD_MODES = ("EXPLICIT_DATES", "TRAILING", "TRADING_DAYS")
TZ = "Asia/Jakarta"


def _load_json(path: str) -> Any:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _sample(values, limit: int = MAX_LIST) -> list:
    items = sorted(str(v) for v in values)
    return items[:limit]


class Evidence:
    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []
        self.reasons: dict[str, str] = {}

    def add(self, check: str, result: str, code: str | None = None, **detail: Any) -> None:
        item = {"check": check, "result": result, **({"code": code} if code else {}), **detail}
        self.items.append(item)
        if code and result in ("FAIL", "INCOMPLETE", "WARN"):
            severity = "FAILED" if code in FAILED_CODES else "INCOMPLETE" if code in INCOMPLETE_CODES else "WARNING"
            if result == "WARN":
                severity = "WARNING"
            order = {"FAILED": 3, "INCOMPLETE": 2, "WARNING": 1}
            if order[severity] > order.get(self.reasons.get(code, ""), 0):
                self.reasons[code] = severity


# ---------------------------------------------------------------- inputs

def _dates(series):
    import pandas as pd

    values = pd.to_datetime(series, errors="coerce")
    if getattr(values.dt, "tz", None) is not None:
        values = values.dt.tz_convert(TZ).dt.tz_localize(None)
    return values.dt.normalize().astype("datetime64[ns]")


def load_inputs(job_dir: str, manifest: dict[str, Any], spec: dict[str, Any], evidence: Evidence,
                blocking: list[dict[str, Any]]) -> dict[str, Any]:
    import pandas as pd
    import pyarrow.parquet as pq

    needed: dict[str, set[str]] = {}
    for calc in spec["calculations"]:
        needed.setdefault(calc["dataset"], set()).update(calc["columns"])
        for key in calc.get("group_by") or []:
            needed.setdefault(key["input"], set()).add(key["column"])
        for segment in calc.get("segments") or []:
            for predicate in segment["predicates"]:
                needed.setdefault(predicate["input"], set()).add(predicate["column"])
    frames: dict[str, Any] = {}
    for name, logical in manifest["logical_datasets"].items():
        columns = set(needed.get(name, set())) | set(logical["key_columns"]) | set(logical["series_key"])
        columns |= {c for c in (logical["entity_column"], logical["date_column"]) if c}
        ranked = sorted(enumerate(logical["files"]), key=lambda item: (item[1].get("created_at") or "", item[0]))
        parts = []
        for rank, (_, file) in enumerate(ranked):
            table = pq.read_table(os.path.join(job_dir, file["local_path"]), columns=sorted(columns))
            part = table.to_pandas()
            part["_saniti_rank"] = rank
            parts.append(part)
        df = pd.concat(parts, ignore_index=True) if len(parts) > 1 else parts[0]
        rows_read = len(df)
        entity, time = logical["entity_column"], logical["date_column"]
        if time:
            df[time] = _dates(df[time])
        if entity:
            df[entity] = df[entity].astype(str)
        key = logical["key_columns"]
        compare = sorted(columns)
        identical = int(df.duplicated(subset=compare, keep="first").sum())
        if identical:
            df = df.drop_duplicates(subset=compare, keep="last")
        conflicts = int(df.duplicated(subset=key, keep=False).sum())
        if conflicts:
            if logical["duplicate_policy"] == "PREFER_LATEST_SNAPSHOT":
                df = df.sort_values("_saniti_rank").drop_duplicates(subset=key, keep="last")
            else:
                blocking.append({"code": "DUPLICATE_CONFLICT", "input": name, "rows": conflicts,
                                 "message": f"{conflicts} rows of input {name} share a key {key} with different "
                                            f"values. Bind non-overlapping datasets or choose duplicate_policy "
                                            f"PREFER_LATEST_SNAPSHOT."})
        series_duplicates = 0
        unresolved = conflicts and logical["duplicate_policy"] != "PREFER_LATEST_SNAPSHOT"
        if logical["series_key"] and name in needed and not unresolved:
            series_duplicates = int(df.duplicated(subset=logical["series_key"], keep=False).sum())
            if series_duplicates:
                blocking.append({"code": "GRAIN_AMBIGUOUS", "input": name, "rows": series_duplicates,
                                 "message": f"Input {name} has several rows per {logical['series_key']} (grain "
                                            f"{logical['grain']}). Filter it to one row per entity and date (for "
                                            f"example one market board) before a per-entity time-series calculation."})
        df = df.sort_values([c for c in (entity, time) if c] or key, kind="stable").reset_index(drop=True)
        frames[name] = df
        evidence.add(f"input.{name}", "PASS" if not (conflicts and logical["duplicate_policy"] != "PREFER_LATEST_SNAPSHOT")
                     and not series_duplicates else "FAIL",
                     files=len(logical["files"]), rows_read=rows_read, rows_used=len(df),
                     identical_duplicates_removed=identical, conflicting_duplicates=conflicts,
                     entities=int(df[entity].nunique()) if entity else None,
                     date_range=[str(df[time].min().date()), str(df[time].max().date())] if time and len(df) else None,
                     duplicate_policy=logical["duplicate_policy"])
    return frames


def _primary(spec: dict[str, Any], manifest: dict[str, Any]) -> str:
    for calc in spec["calculations"]:
        if manifest["logical_datasets"][calc["dataset"]]["date_column"]:
            return calc["dataset"]
    for name, logical in manifest["logical_datasets"].items():
        if logical["date_column"]:
            return name
    return spec["inputs"][0]["name"]


def resolve_period(analysis_spec: dict[str, Any], manifest: dict[str, Any], frames: dict[str, Any],
                   blocking: list[dict[str, Any]]) -> dict[str, Any]:
    import pandas as pd

    spec, resolved = analysis_spec["spec"], analysis_spec["resolved_period"]
    ref = pd.Timestamp(analysis_spec["reference"]["date"])
    primary = _primary(spec, manifest)
    time = manifest["logical_datasets"][primary]["date_column"]
    calendar = [pd.Timestamp(d) for d in sorted(frames[primary][time][frames[primary][time] <= ref].unique())] \
        if time else []
    mode = resolved["mode"]
    if mode in ("EXPLICIT_DATES", "TRAILING"):
        start, end = pd.Timestamp(resolved["start"]), pd.Timestamp(resolved["end"])
    elif not time:
        start = end = ref  # no date column: nothing to resolve against a calendar
    else:
        count = int(resolved.get("trading_days") or 1)
        if len(calendar) < count:
            blocking.append({"code": "PERIOD_NOT_COVERED", "message": f"The input holds {len(calendar)} trading dates "
                             f"up to the reference date; the spec needs {count}. Request a longer date range."})
            start = end = calendar[-1] if calendar else ref
        else:
            start, end = pd.Timestamp(calendar[-count]), pd.Timestamp(calendar[-1])
    in_period = [d for d in calendar if start <= d <= end]
    return {"mode": mode, "start": start, "end": end, "reference_date": ref, "primary_input": primary,
            "trading_dates": len(in_period), "calendar_first": in_period[0] if in_period else None,
            "calendar_last": in_period[-1] if in_period else None}


def _requested(logical: dict[str, Any]) -> dict[str, Any]:
    """Union of what the bound datasets asked the Governor for."""
    starts, ends, entities, unfiltered, truncated, missing = [], [], set(), False, False, set()
    for file in logical["files"]:
        scope = file.get("requested_scope") or {}
        date_range = scope.get("date_range") or {}
        starts.append(date_range.get("from"))
        ends.append(date_range.get("to"))
        listed = scope.get("entities")
        if not listed and not scope.get("entities_count"):
            unfiltered = True
        else:
            entities.update(listed or [])
            truncated |= (scope.get("entities_count") or 0) > len(listed or [])
        missing.update(file.get("missing_entities") or [])
    start = None if any(s is None for s in starts) else min(starts)
    end = None if any(e is None for e in ends) else max(ends)
    return {"from": start, "to": end, "entities": None if unfiltered else entities, "entities_truncated": truncated,
            "missing": missing}


def preflight(job_dir: str, analysis_spec: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    import pandas as pd

    spec = analysis_spec["spec"]
    evidence, blocking = Evidence(), []
    frames = load_inputs(job_dir, manifest, spec, evidence, blocking)
    period = resolve_period(analysis_spec, manifest, frames, blocking)
    start, end = period["start"], period["end"]
    primary = period["primary_input"]
    logical = manifest["logical_datasets"][primary]
    entity, time = logical["entity_column"], logical["date_column"]
    frame = frames[primary]
    requested = _requested(logical)
    universe = spec["universe"]

    # period coverage: extracted vs requested, then what the source actually had
    if period["mode"] in ("EXPLICIT_DATES", "TRAILING") and time:
        if requested["from"] and pd.Timestamp(requested["from"]) > start:
            blocking.append({"code": "ANALYSIS_SCOPE_MISMATCH", "classification": "NOT_EXTRACTED",
                             "message": f"The bound data starts at {requested['from']} but the analysis period starts "
                                        f"{start.date()}. Request data from the recommended date."})
        if requested["to"] and pd.Timestamp(requested["to"]) < end:
            blocking.append({"code": "ANALYSIS_SCOPE_MISMATCH", "classification": "NOT_EXTRACTED",
                             "message": f"The bound data ends at {requested['to']} but the analysis period ends "
                                        f"{end.date()}. Request data up to the period end."})
        head = (period["calendar_first"] - start).days if period["calendar_first"] is not None else None
        tail = (end - period["calendar_last"]).days if period["calendar_last"] is not None else None
        if head is None or head > STALE_GRACE_DAYS or tail > STALE_GRACE_DAYS:
            evidence.add("period.source_coverage", "INCOMPLETE", "SOURCE_PERIOD_UNAVAILABLE",
                         classification="SOURCE_UNAVAILABLE", expected=[str(start.date()), str(end.date())],
                         actual=[str(period["calendar_first"].date()) if head is not None else None,
                                 str(period["calendar_last"].date()) if tail is not None else None],
                         detail="The source has no trading data for part of the requested period.")
        else:
            evidence.add("period.source_coverage", "PASS", expected=[str(start.date()), str(end.date())],
                         trading_dates=period["trading_dates"])

    # data-plan lineage checked by the harness at binding (V2): the executed scope equals the approved scope
    for item in manifest.get("scope_evidence") or []:
        evidence.add(item["check"], item["result"], **{k: v for k, v in item.items() if k not in ("check", "result")})

    # universe
    expected, unavailable = _expected_universe(spec, frame, entity, time, period, requested, evidence)
    _population(spec, manifest, frames, expected, evidence, blocking)
    _segments(spec, manifest, frames, expected, evidence, blocking)
    if universe["type"] == "ALL_IN_SOURCE" and requested["entities"] is not None:
        blocking.append({"code": "UNIVERSE_MISMATCH", "classification": "NOT_EXTRACTED",
                         "message": "The spec analyses every ticker, but the bound data was extracted for a subset of "
                                    "tickers. Request the data without a ticker filter."})
    not_extracted = sorted(t for t, why in unavailable.items() if why == "NOT_EXTRACTED")
    if not_extracted:
        blocking.append({"code": "UNIVERSE_MISMATCH", "classification": "NOT_EXTRACTED",
                         "message": f"Tickers {not_extracted[:MAX_LIST]} were not requested from the SQL Governor."})

    # units of CUSTOM expressions (AI_column_catalog units carried by the Governor manifest)
    import expression

    calcs = {c["id"]: c for c in spec["calculations"]}
    for calc in spec["calculations"]:
        if calc["method"] != "CUSTOM" or not calc.get("expression"):
            continue
        units = {c["name"]: c.get("unit") for c in manifest["logical_datasets"][calc["dataset"]]["columns"]}
        units.update({cid: calcs[cid].get("unit") if calcs[cid]["method"] == "CUSTOM" else None
                      for cid in calc.get("expression_calcs") or []})
        conflicts = expression.unit_conflicts(calc["expression"], units)
        if conflicts:
            blocking.append({"code": "UNIT_MISMATCH", "calculation": calc["id"], "conflicts": conflicts[:MAX_LIST],
                             "message": f"Calculation {calc['id']} combines values with different units: "
                                        f"{'; '.join(conflicts[:5])}. Convert them first or revise the formula."})
        else:
            evidence.add(f"units.{calc['id']}", "PASS", units={n: units.get(n) for n in sorted(units)
                                                               if n in calc["expression"]})

    # warm-up and look-ahead per expected entity
    warmup = _warmup(analysis_spec, manifest, frames, period, expected, requested, evidence)
    for name, info in warmup.items():
        if info["not_extracted"]:
            earlier = info["suggested_from"]
            blocking.append({"code": "INSUFFICIENT_WARMUP_HISTORY", "classification": "NOT_EXTRACTED", "input": name,
                             "entities": info["not_extracted"], "suggested_from": earlier,
                             "message": f"{info['not_extracted_count']} entities have fewer than "
                                        f"{info['minimum']} observations before the analysis period in the bound "
                                        f"data; they trade on fewer days than the recommended range assumes. "
                                        f"Request data from {earlier} or earlier (estimated from their own trading "
                                        f"frequency), or exclude them with an EXCLUDE_TICKERS rule: "
                                        f"{', '.join(info['not_extracted'][:20])}."})
    return {"mode": "preflight", "blocking": blocking, "evidence": evidence.items, "reasons": evidence.reasons,
            "period": _period_json(period), "expected_entities": len(expected),
            "expected_entities_sample": _sample(expected), "unavailable_entities": _sample(unavailable),
            "unavailable_count": len(unavailable), "warmup": warmup}


def _period_json(period: dict[str, Any]) -> dict[str, Any]:
    def day(value: Any) -> str | None:
        return str(value.date()) if value is not None else None

    return {"mode": period["mode"], "start": day(period["start"]), "end": day(period["end"]),
            "reference_date": day(period["reference_date"]), "trading_dates": period["trading_dates"],
            "calendar_first": day(period["calendar_first"]), "calendar_last": day(period["calendar_last"]),
            "primary_input": period["primary_input"]}


def _expected_universe(spec: dict[str, Any], frame, entity: str | None, time: str | None, period: dict[str, Any],
                       requested: dict[str, Any], evidence: Evidence) -> tuple[set[str], dict[str, str]]:
    if not entity:
        return set(), {}
    start, end = period["start"], period["end"]
    present = set(frame[entity].unique())
    if time is not None:
        window = frame[(frame[time] <= end) & (frame[time] >= start)] if period["mode"] != "LATEST" \
            else frame[frame[time] <= end]
        active = set(window[entity].unique())
    else:
        active = present
    unavailable: dict[str, str] = {}
    universe = spec["universe"]
    if universe["type"] == "TICKERS":
        wanted = set(universe["tickers"])
        for ticker in wanted - active:
            if requested["entities"] is not None and ticker not in requested["entities"] \
                    and not requested["entities_truncated"]:
                unavailable[ticker] = "NOT_EXTRACTED"
            elif ticker in requested["missing"] or ticker not in present:
                unavailable[ticker] = "SOURCE_UNAVAILABLE"
            else:
                unavailable[ticker] = "SOURCE_UNAVAILABLE_IN_PERIOD"
        expected = wanted & active
        if unavailable:
            source = sorted(t for t, why in unavailable.items() if why != "NOT_EXTRACTED")
            if source:
                evidence.add("universe.availability", "INCOMPLETE", "UNIVERSE_SOURCE_UNAVAILABLE",
                             classification="SOURCE_UNAVAILABLE", entities=source[:MAX_LIST], count=len(source))
    else:
        expected = active
        quiet = present - active
        if quiet:
            evidence.add("universe.availability", "WARN", "SOURCE_UNAVAILABLE_IN_PERIOD",
                         classification="SOURCE_UNAVAILABLE", count=len(quiet), entities=_sample(quiet),
                         detail="Tickers in the source without observations in the analysis period are not part of "
                                "the analysed universe.")
    for rule in spec["exclusion_rules"]:
        if rule["rule"] == "EXCLUDE_TICKERS":
            dropped = expected & set(rule["value"])
            expected -= dropped
            if dropped:
                evidence.add("exclusion.EXCLUDE_TICKERS", "WARN", "DOCUMENTED_EXCLUSION", count=len(dropped),
                             entities=_sample(dropped), provenance=rule["provenance"])
    evidence.add("universe.expected", "PASS", type=universe["type"], expected_entities=len(expected),
                 unavailable=len(unavailable))
    return expected, unavailable


def _warmup(analysis_spec: dict[str, Any], manifest: dict[str, Any], frames: dict[str, Any], period: dict[str, Any],
            expected: set[str], requested_primary: dict[str, Any], evidence: Evidence) -> dict[str, Any]:
    import pandas as pd

    out: dict[str, Any] = {}
    for name, need in analysis_spec["required_input"].items():
        logical = manifest["logical_datasets"][name]
        entity, time = logical["entity_column"], logical["date_column"]
        minimum, recommended = need["minimum_warmup_observations"], need["recommended_warmup_observations"]
        if not entity or not time or (minimum == 0 and recommended == 0):
            continue
        frame = frames[name]
        requested = _requested(logical)
        extraction_start = pd.Timestamp(requested["from"]) if requested["from"] else frame[time].min()
        source_limited, not_extracted, path_dependent, affected = [], [], [], 0
        needed_from: list[Any] = []  # per not-extracted entity: the start its own trading density needs
        groups = frame.groupby(entity, sort=False)[time]
        for ent, dates in groups:
            if ent not in expected:
                continue
            anchor = period["start"] if period["mode"] != "LATEST" else dates[dates <= period["end"]].max()
            prior = int((dates < anchor).sum())
            if prior < minimum:
                first = dates.min()
                in_period = int(((dates >= period["start"]) & (dates <= period["end"])).sum())
                if requested["from"] is None or first > extraction_start + timedelta(days=STALE_GRACE_DAYS):
                    source_limited.append(ent)
                    affected += min(minimum - prior, in_period)
                else:
                    not_extracted.append(ent)
                    # A thinly traded entity needs more calendar days per observation than the recommended
                    # range assumes; scale its bound pre-period span by its own density, with 25% margin.
                    if prior:  # without any prior observation its density is unknown: the recommended range
                        span = max((anchor - extraction_start).days, 1)
                        needed_from.append(anchor - timedelta(days=math.ceil(span * minimum / prior * 1.25)))
            elif prior < recommended:
                path_dependent.append(ent)
        info = {"minimum": minimum, "recommended": recommended, "source_limited": _sample(source_limited),
                "source_limited_count": len(source_limited), "not_extracted": _sample(not_extracted),
                "not_extracted_count": len(not_extracted), "affected_observations": affected,
                "path_dependent_count": len(path_dependent),
                "recommended_from": need["recommended_request_date_range"]["from"],
                "suggested_from": min([need["recommended_request_date_range"]["from"]]
                                      + [d.date().isoformat() for d in needed_from])}
        out[name] = info
        if not_extracted:
            evidence.add(f"warmup.{name}", "INCOMPLETE", "INSUFFICIENT_WARMUP_HISTORY", classification="NOT_EXTRACTED",
                         required_observations=minimum, entities=_sample(not_extracted), count=len(not_extracted))
        if source_limited:
            severity = "INCOMPLETE" if analysis_spec["spec"]["universe"]["type"] == "TICKERS" else "WARN"
            evidence.add(f"warmup.{name}.source", severity, "INSUFFICIENT_WARMUP_HISTORY",
                         classification="SOURCE_LIMITED_HISTORY", required_observations=minimum,
                         entities=_sample(source_limited), count=len(source_limited),
                         affected_observations=affected,
                         detail="The source has no earlier history for these entities (for example recent listings); "
                                "their first observations in the period have no defined value.")
        if path_dependent:
            evidence.add(f"warmup.{name}.recommended", "WARN", "PATH_DEPENDENT_WARMUP",
                         recommended_observations=recommended, count=len(path_dependent),
                         detail="Fewer than the recommended warm-up observations: recursive indicators (such as "
                                "Wilder RSI) still depend on where the input starts.")
        if not (not_extracted or source_limited or path_dependent):
            evidence.add(f"warmup.{name}", "PASS", required_observations=minimum,
                         recommended_observations=recommended)
    return out


# ---------------------------------------------------------------- reference values

def reference_frames(spec: dict[str, Any], manifest: dict[str, Any], frames: dict[str, Any],
                     period: dict[str, Any] | None = None) -> dict[str, Any]:
    """Per input: entity, date, and one column per supported calculation (NaN where undefined). GROUP_AGGREGATE and
    GROUP_CORRELATION values are recalculated per output by the group checks."""
    import numpy as np
    import expression
    import reference

    by_dataset: dict[str, Any] = {}
    unverifiable: set[str] = set()
    for calc in spec["calculations"]:
        name = calc["dataset"]
        logical = manifest["logical_datasets"][name]
        entity, time = logical["entity_column"], logical["date_column"]
        upstream = calc["input_calculation"]
        if calc["method"] in ("GROUP_AGGREGATE", "GROUP_CORRELATION"):
            if upstream and upstream in unverifiable:
                unverifiable.add(calc["id"])
            continue
        if not entity or not time:
            unverifiable.add(calc["id"])
            continue
        frame = frames[name]
        if name not in by_dataset:
            by_dataset[name] = frame[[entity, time]].copy()
        target = by_dataset[name]
        if calc["method"] == "PERIOD_RETURN":
            if period is None or period.get("mode") not in ("EXPLICIT_DATES", "TRAILING") or \
                    (upstream and upstream in unverifiable):
                unverifiable.add(calc["id"])
                continue
            params = {p["name"]: p["value"] for p in calc["params"]}
            source = target[_calc_column(spec, upstream)] if upstream else frame[calc["columns"][0]]
            target[calc["output_column"]] = _period_return(frame, entity, time, _numeric(source), params, period)
            continue
        if calc["method"] == "PERIOD_STAT":
            if period is None or period.get("mode") not in PERIOD_MODES or (upstream and upstream in unverifiable):
                unverifiable.add(calc["id"])
                continue
            params = {p["name"]: p["value"] for p in calc["params"]}
            source = target[_calc_column(spec, upstream)] if upstream else frame[calc["columns"][0]]
            target[calc["output_column"]] = _period_stat(frame, entity, time, _numeric(source), params, period)
            continue
        if calc["method"] == "EVENT_STUDY":
            # summarised in check_output; verifiable when its outcome and every signal are
            deps = [upstream] + [p["calculation"] for p in calc.get("signal") or []]
            if any(d in unverifiable for d in deps):
                unverifiable.add(calc["id"])
            continue
        if calc["method"] == "CUSTOM":
            used = list(calc.get("expression_calcs") or [])
            if not calc.get("expression") or any(u in unverifiable for u in used):
                unverifiable.add(calc["id"])
                continue
            try:
                columns = {c: _numeric(frame[c]) for c in calc["columns"]}
                columns.update({u: target[_calc_column(spec, u)].to_numpy(dtype=float) for u in used})
                groups = list(frame.groupby(entity, sort=False).indices.values())
                policy = (calc.get("data_policies") or {}).get("zero_denominator", "NULL")
                target[calc["output_column"]] = expression.evaluate(calc["expression"], columns, groups, policy)
            except Exception:  # noqa: BLE001 - an expression that cannot be evaluated is not verifiable
                unverifiable.add(calc["id"])
            continue
        if calc["method"] == "CORRELATION" or (upstream and upstream in unverifiable):
            unverifiable.add(calc["id"])
            continue
        params = {p["name"]: p["value"] for p in calc["params"]}
        source = target[_calc_column(spec, upstream)] if upstream else frame[calc["columns"][0]]
        other = frame[calc["columns"][1]] if len(calc["columns"]) == 2 else None
        values = np.full(len(frame), np.nan)
        x_all = source.to_numpy(dtype=float)
        y_all = other.to_numpy(dtype=float) if other is not None else None
        for _, index in frame.groupby(entity, sort=False).indices.items():
            y = y_all[index] if y_all is not None else None
            values[index] = reference.compute(calc["method"], params, x_all[index], y)
        target[calc["output_column"]] = values
    return {"frames": by_dataset, "unverifiable": unverifiable}


def _calc_column(spec: dict[str, Any], calc_id: str) -> str:
    return next(c["output_column"] for c in spec["calculations"] if c["id"] == calc_id)


def _period_return(frame, entity: str, time: str, x, params: dict[str, Any], period: dict[str, Any]):
    """x_t / x_base - 1 on period dates (x_base: last observation before the period, or first in it)."""
    import numpy as np

    values = np.full(len(frame), np.nan)
    dates = frame[time].to_numpy()
    start, end = np.datetime64(period["start"]), np.datetime64(period["end"])
    for _, index in frame.groupby(entity, sort=False).indices.items():
        own = dates[index]
        inside = (own >= start) & (own <= end)
        if not inside.any():
            continue
        if params.get("base", "PREVIOUS_OBSERVATION") == "PREVIOUS_OBSERVATION":
            before = np.where(own < start)[0]
            if not len(before):
                continue
            base = x[index[before[-1]]]
        else:
            base = x[index[np.where(inside)[0][0]]]
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = x[index[inside]] / base
            change = np.log(ratio) if params.get("kind") == "LOG" else ratio - 1.0
        change[~np.isfinite(change)] = np.nan
        values[index[inside]] = change * (100.0 if params.get("as_percent") else 1.0)
    return values


def _period_stat(frame, entity: str, time: str, x, params: dict[str, Any], period: dict[str, Any]):
    """function(x over the entity's period observations up to t) on period dates; null values excluded; fewer than
    min_observations non-null values -> NaN. Nothing before the period start is used."""
    import numpy as np
    import pandas as pd

    values = np.full(len(frame), np.nan)
    dates = frame[time].to_numpy()
    start, end = np.datetime64(period["start"]), np.datetime64(period["end"])
    function, minimum = params["function"], int(params.get("min_observations") or 1)
    for _, index in frame.groupby(entity, sort=False).indices.items():
        own = dates[index]
        inside = (own >= start) & (own <= end)
        if not inside.any():
            continue
        series = pd.Series(x[index[inside]], dtype=float)
        window = series.expanding(min_periods=1)
        if function == "STD":
            out = window.std(ddof=int(params.get("ddof", 1)))
        else:
            out = {"AVG": window.mean, "MEDIAN": window.median, "MIN": window.min, "MAX": window.max,
                   "SUM": window.sum, "COUNT": window.count}[function]()
        out = np.array(out, dtype=float)  # a writable copy
        out[series.notna().cumsum().to_numpy() < minimum] = np.nan
        values[index[inside]] = out
    return values


def _population(spec: dict[str, Any], manifest: dict[str, Any], frames: dict[str, Any], expected: set[str],
                evidence: Evidence, blocking: list[dict[str, Any]]) -> None:
    """V2 attribute scope: the candidate population is every member of the UNIVERSE input (extracted with the
    approved predicates); members without data in the period are reported, and an empty scope is not a result."""
    scope = spec.get("scope") or {}
    if scope.get("selection_type") != "ATTRIBUTE_FILTER":
        return
    universe = next((i for i in spec["inputs"] if i.get("role") == "UNIVERSE"), None)
    if universe is None:
        members = expected
    else:
        logical = manifest["logical_datasets"][universe["name"]]
        members = set(frames[universe["name"]][logical["entity_column"]].astype(str)) \
            if logical["entity_column"] else set()
    if not members:
        blocking.append({"code": "SCOPE_EMPTY", "classification": "SOURCE_UNAVAILABLE",
                         "message": "No entity satisfies the approved scope predicates "
                                    f"{[(p['column'], p['operator'], p['values']) for p in scope['predicates']]}; check "
                                    "the values against the catalog data."})
        evidence.add("scope.population", "INCOMPLETE", "SCOPE_EMPTY", members=0)
        return
    without = members - expected if universe is not None and universe["name"] != _primary(spec, manifest) else set()
    if without:
        evidence.add("scope.population", "WARN", "UNIVERSE_MEMBERS_WITHOUT_DATA", classification="SOURCE_UNAVAILABLE",
                     members=len(members), with_data=len(members & expected), count=len(without),
                     entities=_sample(without),
                     detail="Members of the approved scope without observations in the analysis period are not "
                            "candidates.")
    else:
        evidence.add("scope.population", "PASS", members=len(members), with_data=len(members & expected) if
                     universe is not None else len(members),
                     predicates=[{k: p[k] for k in ("table", "column", "operator", "values")}
                                 for p in scope["predicates"]])


def _segments(spec: dict[str, Any], manifest: dict[str, Any], frames: dict[str, Any], expected: set[str],
              evidence: Evidence, blocking: list[dict[str, Any]]) -> None:
    """Segments are checked before the analysis runs: a segment no in-scope entity satisfies cannot be answered, and a
    segment attribute with several values per entity cannot assign entities."""
    for calc in spec["calculations"]:
        if not calc.get("segments"):
            continue
        entity = manifest["logical_datasets"][calc["dataset"]]["entity_column"]
        frame = frames[calc["dataset"]]
        base = frame[frame[entity].astype(str).isin(expected)] if entity else frame
        attached = _attach_groups(calc, manifest, frames, base, entity, evidence, calc["id"])
        if attached is None:
            blocking.append({"code": "GROUP_KEY_AMBIGUOUS", "calculation": calc["id"],
                             "message": f"A segment attribute of calculation {calc['id']} has several values for one "
                                        f"entity; segments need one value per entity."})
            continue
        members = attached[2]["segment_members"]
        empty = sorted(label for label, count in members.items() if count == 0)
        if empty:
            evidence.add(f"segments.{calc['id']}", "INCOMPLETE", "SEGMENT_EMPTY", members=members)
            blocking.append({"code": "SEGMENT_EMPTY", "calculation": calc["id"], "segments": empty, "members": members,
                             "message": f"Segments {empty} of calculation {calc['id']} contain no in-scope entity. "
                                        f"Check their predicate values against the catalog (get_dimension_values) and "
                                        f"revise the spec; do not report these segments."})
        else:
            evidence.add(f"segments.{calc['id']}", "PASS", **attached[2])


def _ranked(values, keys, direction: str, limit: int, tie_policy: str):
    """Indices chosen by a top-N over the complete candidate population (NaN values are not candidates)."""
    import numpy as np

    order = sorted(range(len(values)), key=lambda i: (values[i] if direction == "ASC" else -values[i], keys[i]))
    order = [i for i in order if np.isfinite(values[i])]
    chosen = order[:limit]
    if tie_policy == "INCLUDE_TIES" and chosen:
        boundary = values[chosen[-1]]
        chosen = [i for i in order if (values[i] >= boundary if direction == "DESC" else values[i] <= boundary)]
    return set(chosen), (values[order[limit - 1]] if len(order) >= limit else None), len(order)


# ---------------------------------------------------------------- postflight

def _numeric(series):
    import numpy as np
    import pandas as pd

    values = np.array(pd.to_numeric(series, errors="coerce"), dtype=float)
    values[~np.isfinite(values)] = np.nan
    return values


def _compare(actual, expected) -> Any:
    import numpy as np

    both_nan = np.isnan(actual) & np.isnan(expected)
    with np.errstate(invalid="ignore"):
        close = np.isclose(actual, expected, rtol=RTOL, atol=ATOL)
    return both_nan | close


def _exclusions(spec: dict[str, Any], frame, entity: str, time: str, period: dict[str, Any], expected: set[str],
                evidence: Evidence) -> set[str]:
    excluded: set[str] = set()
    for rule in spec["exclusion_rules"]:
        if rule["rule"] == "MIN_OBSERVATIONS_IN_PERIOD":
            window = frame[(frame[time] >= period["start"]) & (frame[time] <= period["end"])]
            counts = window.groupby(entity).size()
            dropped = {e for e in expected if counts.get(e, 0) < int(rule["value"])}
        elif rule["rule"] == "MAX_STALENESS_DAYS":
            last = frame[frame[time] <= period["end"]].groupby(entity)[time].max()
            limit = period["end"] - timedelta(days=int(rule["value"]))
            dropped = {e for e in expected if e in last.index and last[e] < limit}
        else:
            continue
        excluded |= dropped
        evidence.add(f"exclusion.{rule['rule']}", "WARN" if dropped else "PASS",
                     "DOCUMENTED_EXCLUSION" if dropped else None, value=rule["value"], count=len(dropped),
                     entities=_sample(dropped), provenance=rule["provenance"])
    return excluded


def _diagnose(calc: dict[str, Any], frame, entity: str, time: str, period: dict[str, Any], keys, actual) -> dict | None:
    """Explain a calculation mismatch: which parameter or procedure the actual values match."""
    import numpy as np
    import reference

    if calc["method"] in ("CUSTOM", "CORRELATION") or calc["input_calculation"]:
        return None
    params = {p["name"]: p["value"] for p in calc["params"]}
    column = calc["columns"][0]
    sub = keys.head(2000)
    entities = set(sub[entity])
    local = frame[frame[entity].isin(entities)]
    act = actual[: len(sub)]

    def score(alt_params: dict, restrict_period: bool = False, unpartitioned: bool = False) -> float:
        values = np.full(len(local), np.nan)
        source = local if not restrict_period else local[(local[time] >= period["start"])]
        if unpartitioned:
            ordered = frame.sort_values([entity, time], kind="stable")
            computed = reference.compute(calc["method"], alt_params, ordered[column].to_numpy(dtype=float),
                                         ordered[calc["columns"][1]].to_numpy(dtype=float)
                                         if len(calc["columns"]) == 2 else None)
            lookup = dict(zip(zip(ordered[entity], ordered[time]), computed))
        else:
            lookup = {}
            for ent, part in source.groupby(entity, sort=False):
                computed = reference.compute(calc["method"], alt_params, part[column].to_numpy(dtype=float),
                                             part[calc["columns"][1]].to_numpy(dtype=float)
                                             if len(calc["columns"]) == 2 else None)
                lookup.update(zip(zip(part[entity], part[time]), computed))
        values = np.array([lookup.get((e, d), np.nan) for e, d in zip(sub[entity], sub[time])], dtype=float)
        return float(_compare(act, values).mean()) if len(values) else 0.0

    candidates: list[tuple[str, Any, dict]] = []
    for name in ("window", "period", "horizon"):
        if name in params:
            options = sorted({2, 3, 5, 7, 9, 10, 12, 14, 15, 20, 21, 25, 26, 30, 40, 50, 60, 90, 100, 120, 200, 250,
                              params[name] - 1, params[name] + 1} - {params[name]})
            candidates += [(name, v, {**params, name: v}) for v in options if v >= 1]
    if "ddof" in params:
        candidates.append(("ddof", 1 - params["ddof"], {**params, "ddof": 1 - params["ddof"]}))
    if "include_current" in params:
        candidates.append(("include_current", not params["include_current"],
                           {**params, "include_current": not params["include_current"]}))
    if "as_percent" in params:
        candidates.append(("as_percent", not params["as_percent"], {**params, "as_percent": not params["as_percent"]}))
    if "kind" in params:
        other = "LOG" if params["kind"] == "SIMPLE" else "SIMPLE"
        candidates.append(("kind", other, {**params, "kind": other}))
    if params.get("entry") == "NEXT_OPEN":
        candidates.append(("entry", "SIGNAL_CLOSE", {**params, "entry": "SIGNAL_CLOSE"}))
    for name, value, alt in candidates:
        if score(alt) >= 0.99:
            return {"finding": "PARAMETER_DIFFERS", "parameter": name, "spec_value": params.get(name),
                    "values_match": value}
    if period["mode"] != "LATEST" and score(params, restrict_period=True) >= 0.99:
        return {"finding": "WARMUP_NOT_USED", "detail": "The values match a calculation that ignored the history "
                                                        "before the analysis period."}
    if score(params, unpartitioned=True) >= 0.99:
        return {"finding": "NOT_PARTITIONED_BY_ENTITY", "detail": "The values match a calculation run across "
                                                                  "entities without separating their histories."}
    return None


def check_output(output: dict[str, Any], path: str | None, spec: dict[str, Any], manifest: dict[str, Any],
                 frames: dict[str, Any], refs: dict[str, Any], period: dict[str, Any], expected_all: set[str],
                 evidence: Evidence, warmups: dict[str, int], research_context: dict[str, Any] | None = None
                 ) -> dict[str, Any]:
    import numpy as np
    import pyarrow.parquet as pq

    name = output["name"]
    scope: dict[str, Any] = {"name": name, "grain": output["grain"], "checked": False}
    if output["grain"] == "UNSPECIFIED":
        evidence.add(f"output.{name}", "SKIPPED", detail="Output grain UNSPECIFIED: its scope and values cannot be "
                                                         "checked independently.")
        return scope
    if path is None:
        evidence.add(f"output.{name}", "FAIL", "REQUIRED_OUTPUT_MISSING",
                     detail="The spec declares this output, but the analysis did not emit a TABLE or PARQUET "
                            "ARTIFACT with this name.")
        return scope
    calcs = {c["id"]: c for c in spec["calculations"]}
    used = [calcs[c] for c in output["calculations"]]
    if output["grain"] == "SUMMARY":
        return _check_summary(output, path, used[0], spec, manifest, frames, refs, period, expected_all, evidence,
                              scope, research_context or {})
    if output["grain"] in ("GROUP", "GROUP_DATE"):
        return _check_groups(output, path, used, spec, manifest, frames, refs, period, expected_all, evidence, scope,
                             research_context or {})
    if output["grain"] == "GROUP_PAIR":
        return _check_group_pairs(output, path, used, spec, manifest, frames, refs, period, expected_all, evidence,
                                  scope, research_context or {})
    value_columns = [c["output_column"] for c in used]
    if output["grain"] == "ENTITY_PAIR":
        key_columns = list(output["pair_columns"])
    else:
        key_columns = [output["entity_column"]] + ([output["date_column"]] if output["grain"] == "ENTITY_DATE" else [])
    schema = pq.read_schema(path).names
    date_optional = output["grain"] == "ENTITY" and output["date_column"] in schema
    wanted = key_columns + value_columns + ([output["date_column"]] if date_optional else [])
    missing = [c for c in wanted if c not in schema]
    if missing:
        evidence.add(f"output.{name}", "FAIL", "REQUIRED_OUTPUT_MISSING", missing_columns=missing,
                     detail="Declared key or value columns are missing from the output.")
        return scope
    table = pq.read_table(path, columns=list(dict.fromkeys(wanted))).to_pandas()
    for column in key_columns:
        if column == output.get("date_column"):
            table[column] = _dates(table[column])
        else:
            table[column] = table[column].astype(str)
    if date_optional:
        table[output["date_column"]] = _dates(table[output["date_column"]])
    duplicates = int(table.duplicated(subset=key_columns, keep=False).sum())
    scope.update(rows=len(table), checked=True)
    if duplicates:
        evidence.add(f"output.{name}.grain", "FAIL", "OUTPUT_GRAIN_VIOLATION", rows=duplicates, key=key_columns,
                     detail="Several output rows share one key; the output does not have the declared grain.")
        return scope
    if output["grain"] == "ENTITY_PAIR":
        return _check_pairs(output, table, key_columns, used, spec, manifest, frames, period, evidence, scope,
                            research_context or {})

    dataset = used[0]["dataset"]
    logical = manifest["logical_datasets"][dataset]
    entity, time = logical["entity_column"], logical["date_column"]
    frame = frames[dataset].assign(_pos=frames[dataset].groupby(entity, sort=False).cumcount())
    excluded = _exclusions(spec, frame, entity, time, period, expected_all, evidence)
    universe = expected_all - excluded
    reference_frame = refs["frames"].get(dataset)
    verifiable = [c for c in used if c["id"] not in refs["unverifiable"]]
    out_entity = output["entity_column"]
    start, end = period["start"], period["end"]
    selection = output["coverage"] == "SELECTION"
    selectable = not selection or all(p["calculation"] not in refs["unverifiable"] for p in output["selection"] or [])

    if output["grain"] == "ENTITY_DATE":
        out_time = output["date_column"]
        outside = table[(table[out_time] < start) | (table[out_time] > end)]
        inside = table[(table[out_time] >= start) & (table[out_time] <= end)]
        scope.update(entities=int(inside[out_entity].nunique()),
                     date_range=[str(inside[out_time].min().date()), str(inside[out_time].max().date())]
                     if len(inside) else None, in_period_rows=len(inside), rows_outside_period=len(outside))
        if len(outside):
            evidence.add(f"output.{name}.period", "FAIL", "ANALYSIS_SCOPE_MISMATCH", rows=len(outside),
                         actual_range=[str(table[out_time].min().date()), str(table[out_time].max().date())],
                         expected_range=[str(start.date()), str(end.date())],
                         detail="The output contains rows outside the analysis period (warm-up history is not part "
                                "of the requested period).")
        base = frame[(frame[time] >= start) & (frame[time] <= end) & frame[entity].isin(universe)][
            [entity, time, "_pos"]]
        if reference_frame is not None:
            base = base.merge(reference_frame, on=[entity, time], how="left")
        base = base.rename(columns={entity: out_entity, time: out_time})
        merged = base.merge(inside, on=[out_entity, out_time], how="outer", suffixes=("_ref", ""), indicator=True)
    else:
        out_time = "_period_end_date"
        latest = frame[(frame[time] <= end) & frame[entity].isin(universe)]
        if period["mode"] != "LATEST":
            latest = latest[latest[time] >= start]
        latest = latest.sort_values([entity, time]).groupby(entity, sort=False).tail(1)[[entity, time, "_pos"]]
        stale = latest[latest[time] < end - timedelta(days=STALE_GRACE_DAYS)]
        if len(stale):
            evidence.add(f"output.{name}.staleness", "WARN", "STALE_LATEST_OBSERVATION", count=len(stale),
                         entities=_sample(stale[entity]),
                         detail="These entities' latest observation is more than a week before the period end.")
        if reference_frame is not None:
            latest = latest.merge(reference_frame, on=[entity, time], how="left")
        base = latest.rename(columns={entity: out_entity, time: out_time})
        if date_optional:
            wrong = table.merge(base[[out_entity, out_time]], on=out_entity, how="inner")
            wrong = wrong[wrong[output["date_column"]] != wrong[out_time]]
            if len(wrong):
                evidence.add(f"output.{name}.as_of", "FAIL", "ANALYSIS_SCOPE_MISMATCH", rows=len(wrong),
                             examples=[{"entity": r[out_entity], "output_date": str(r[output["date_column"]].date()),
                                        "expected_date": str(r[out_time].date())}
                                       for _, r in wrong.head(MAX_EXAMPLES).iterrows()],
                             detail="Values are not taken at each entity's latest observation in the period.")
        merged = base.merge(table, on=out_entity, how="outer", suffixes=("_ref", ""), indicator=True)
        scope.update(entities=int(table[out_entity].nunique()))

    ref_col = {c["output_column"]: (c["output_column"] + "_ref" if c["output_column"] in table.columns
                                    else c["output_column"]) for c in verifiable}
    in_ref = merged["_merge"] != "right_only"
    in_out = merged["_merge"] != "left_only"
    defined = np.ones(len(merged), dtype=bool)
    for c in verifiable:
        defined &= np.isfinite(_numeric(merged[ref_col[c["output_column"]]]))

    def satisfies(predicates: list[dict[str, Any]]):
        chosen = defined.copy()
        for predicate in predicates:
            column = ref_col[calcs[predicate["calculation"]]["output_column"]]
            values = _numeric(merged[column])
            op = predicate["op"]
            with np.errstate(invalid="ignore"):
                test = {">": values > predicate["value"], ">=": values >= predicate["value"],
                        "<": values < predicate["value"], "<=": values <= predicate["value"],
                        "==": np.isclose(values, predicate["value"]),
                        "!=": ~np.isclose(values, predicate["value"])}[op]
            chosen &= np.nan_to_num(test, nan=False).astype(bool)
        return chosen

    ranking = output.get("ranking")
    if ranking and ranking["calculation"] in {c["id"] for c in verifiable}:
        column = ref_col[calcs[ranking["calculation"]]["output_column"]]
        candidates = in_ref & defined
        values = _numeric(merged[column])
        keys = merged[out_entity].astype(str).to_numpy()
        index = np.where(candidates)[0]
        picked, boundary, population = _ranked(values[index], keys[index], ranking["direction"], ranking["limit"],
                                               ranking["tie_policy"])
        chosen = np.zeros(len(merged), dtype=bool)
        chosen[index[sorted(picked)]] = True
        false_negative = merged[chosen & ~in_out]
        false_positive = merged[in_out & ~chosen]
        detail = {"candidates": population, "limit": ranking["limit"], "direction": ranking["direction"],
                  "tie_policy": ranking["tie_policy"], "boundary_value": _round(boundary),
                  "population": "every in-scope entity with a defined value (recalculated)"}
        if len(false_negative) or len(false_positive):
            evidence.add(f"output.{name}.ranking", "FAIL", "RANKING_MISMATCH", missing=len(false_negative),
                         unexpected=len(false_positive), missing_examples=_keys(false_negative, out_entity, out_time),
                         unexpected_examples=_keys(false_positive, out_entity, out_time), **detail,
                         detail="The emitted rows are not the top-N of the complete candidate population when every "
                                "candidate is recalculated independently.")
        else:
            evidence.add(f"output.{name}.ranking", "PASS", selected=int(chosen.sum()), **detail)
        scope["selected"] = int(in_out.sum())
    elif ranking:
        evidence.add(f"output.{name}.ranking", "SKIPPED",
                     detail="The ranked calculation has no independent reference; the top-N cannot be checked.")
        scope["scope_unverifiable"] = True
        scope["selected"] = int(in_out.sum())
    elif selection and selectable:
        chosen = satisfies(output["selection"])
        false_negative = merged[in_ref & chosen & ~in_out]
        false_positive = merged[in_out & ~(in_ref & chosen)]
        if len(false_negative) or len(false_positive):
            evidence.add(f"output.{name}.selection", "FAIL", "SELECTION_MISMATCH",
                         missing=len(false_negative), unexpected=len(false_positive),
                         missing_examples=_keys(false_negative, out_entity, out_time),
                         unexpected_examples=_keys(false_positive, out_entity, out_time),
                         detail="The selected rows differ from the rows that satisfy the spec's selection when "
                                "recalculated independently.")
        else:
            evidence.add(f"output.{name}.selection", "PASS", selected=int((in_ref & chosen).sum()))
        scope["selected"] = int(in_out.sum())
    elif selection:
        checkable = [p for p in output["selection"] if p["calculation"] not in refs["unverifiable"]]
        if checkable:
            # A necessary condition still holds: every selected row must satisfy the recalculable predicates.
            violating = merged[in_out & ~(in_ref & satisfies(checkable))]
            if len(violating):
                evidence.add(f"output.{name}.selection", "FAIL", "SELECTION_MISMATCH", missing=0,
                             unexpected=len(violating), unexpected_examples=_keys(violating, out_entity, out_time),
                             detail="Selected rows do not satisfy the selection predicates that can be recalculated "
                                    "independently.")
            else:
                evidence.add(f"output.{name}.selection.checkable", "PASS", selected=int(in_out.sum()),
                             predicates=[p["calculation"] for p in checkable],
                             detail="Every selected row satisfies the recalculable predicates; rows the other "
                                    "predicates excluded cannot be checked.")
        evidence.add(f"output.{name}.selection", "SKIPPED",
                     detail="The selection uses a calculation without an independent reference; the complete "
                            "selected set cannot be checked.")
        scope["scope_unverifiable"] = True
        scope["selected"] = int(in_out.sum())
    else:
        # Without a reference, rows inside the declared warm-up of each entity's input may be undefined.
        position = merged["_pos"].fillna(-1).to_numpy() >= warmups.get(dataset, 0)
        required = in_ref & (defined if verifiable else position)
        lost = merged[required & ~in_out]
        undefined_missing = merged[in_ref & ~defined & ~in_out]
        extra = merged[in_out & ~in_ref]
        if len(lost):
            present_entities = set(merged.loc[in_out, out_entity])
            lost_entities = set(lost[out_entity]) - present_entities
            if lost_entities:
                evidence.add(f"output.{name}.universe", "FAIL", "UNIVERSE_MISMATCH",
                             classification="LOST_IN_TRANSFORMATION", missing_entities=len(lost_entities),
                             expected_entities=int(merged.loc[in_ref, out_entity].nunique()),
                             actual_entities=len(present_entities), examples=_sample(lost_entities),
                             detail="Entities in the analysed universe have no rows in the output.")
            partial = lost[~lost[out_entity].isin(lost_entities)]
            if len(partial):
                detail = {"classification": "LOST_IN_TRANSFORMATION", "missing_observations": len(partial),
                          "examples": _keys(partial, out_entity, out_time)}
                if out_time in partial.columns and output["grain"] == "ENTITY_DATE":
                    detail["expected_range"] = [str(start.date()), str(end.date())]
                    detail["actual_range"] = scope.get("date_range")
                evidence.add(f"output.{name}.coverage", "FAIL", "ANALYSIS_SCOPE_MISMATCH", **detail,
                             detail="Observations inside the analysis period with a defined value are missing from "
                                    "the output.")
        else:
            evidence.add(f"output.{name}.coverage", "PASS", expected_rows=int(required.sum()),
                         actual_rows=int(in_out.sum()))
        if len(undefined_missing):
            evidence.add(f"output.{name}.undefined", "WARN", "UNDEFINED_VALUES_OMITTED", rows=len(undefined_missing),
                         detail="Rows whose value is undefined (for example insufficient warm-up history) are not in "
                                "the output; they are reported, not treated as lost.")
        if len(extra):
            evidence.add(f"output.{name}.extra_rows", "FAIL", "ANALYSIS_SCOPE_MISMATCH", rows=len(extra),
                         examples=_keys(extra, out_entity, out_time),
                         detail="The output contains keys that are not observations of the analysed universe in the "
                                "analysis period.")
    # values
    both = merged[in_ref & in_out]
    checked_total = 0
    for calc in verifiable:
        column = calc["output_column"]
        actual = _numeric(both[column])
        expected = _numeric(both[ref_col[column]])
        count = len(actual)
        if count > MAX_VALUE_CHECKS:
            order = np.argsort(both[out_entity].astype(str).to_numpy(), kind="stable")[:MAX_VALUE_CHECKS]
            actual, expected = actual[order], expected[order]
        ok = _compare(actual, expected)
        checked_total += len(ok)
        if not ok.all():
            bad = both[~np.pad(ok, (0, count - len(ok)), constant_values=True)] if count > len(ok) else both[~ok]
            examples = [{"entity": r[out_entity], **({"date": str(r[out_time].date())} if out_time in r and
                                                     hasattr(r[out_time], "date") else {}),
                         "expected": _round(r[ref_col[column]]), "actual": _round(r[column])}
                        for _, r in bad.head(MAX_EXAMPLES).iterrows()]
            key_frame = bad[[out_entity] + ([out_time] if out_time in bad.columns else [])].rename(
                columns={out_entity: entity, out_time: time})
            diagnosis = _diagnose(calc, frame, entity, time, period, key_frame.reset_index(drop=True),
                                  _numeric(bad[column])) if time in key_frame.columns else None
            diagnosis = diagnosis or _diagnose_scale(calc, _numeric(bad[column]), _numeric(bad[ref_col[column]]))
            evidence.add(f"calculation.{calc['id']}.{name}", "FAIL", "CALCULATION_MISMATCH", method=calc["method"],
                         mismatched=int((~ok).sum()), checked=len(ok), examples=examples,
                         **({"diagnosis": diagnosis} if diagnosis else {}),
                         detail="Output values differ from the independent reference recalculation.")
        else:
            evidence.add(f"calculation.{calc['id']}.{name}", "PASS", method=calc["method"], checked=len(ok),
                         of=count)
    for calc in used:
        if calc["id"] in refs["unverifiable"]:
            evidence.add(f"calculation.{calc['id']}.{name}", "SKIPPED", method=calc["method"],
                         detail="No independent reference implementation for this calculation.")
    scope.update(values_checked=checked_total, verified_calculations=[c["id"] for c in verifiable],
                 unverified_calculations=[c["id"] for c in used if c["id"] in refs["unverifiable"]])
    return scope


def _canonical(value: Any, data_type: str | None) -> str | None:
    """app/spec_v2.canonical_value for values read from Parquet (None for a missing value); tests compare them."""
    from decimal import Decimal

    import numpy as np
    import pandas as pd

    if value is None or (isinstance(value, float) and value != value) or value is pd.NaT:
        return None
    if isinstance(value, np.datetime64):
        value = pd.Timestamp(value)
    elif isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and value != value:
        return None
    kind = (data_type or "").lower()
    if isinstance(value, bool):
        return "true" if value else "false"
    if kind == "date" and hasattr(value, "isoformat"):
        return value.date().isoformat() if hasattr(value, "hour") else value.isoformat()
    if isinstance(value, (int, float, Decimal)):
        text = format(Decimal(str(value)).normalize(), "f")
        return "0" if text in ("-0", "") else text
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _segment_mask(values, predicate: dict[str, Any]):
    """Rows whose attribute satisfies one segment predicate (a missing value satisfies only IS_NULL)."""
    from decimal import Decimal

    import numpy as np

    kind = predicate.get("data_type")
    canon = [_canonical(v, kind) for v in values]
    wanted = predicate["values"]
    op = predicate["operator"]
    if op == "IS_NULL":
        return np.array([c is None for c in canon], dtype=bool)
    if op == "IS_NOT_NULL":
        return np.array([c is not None for c in canon], dtype=bool)
    if op in ("EQ", "IN"):
        allowed = set(wanted)
        return np.array([c is not None and c in allowed for c in canon], dtype=bool)
    if op == "NEQ":
        return np.array([c is not None and c != wanted[0] for c in canon], dtype=bool)
    numeric = (kind or "").lower() in NUMERIC_TYPES
    order = (lambda text: Decimal(text)) if numeric else (lambda text: text)
    bound = order(wanted[0])
    test = {"GT": lambda a: a > bound, "GTE": lambda a: a >= bound, "LT": lambda a: a < bound,
            "LTE": lambda a: a <= bound}[op]
    return np.array([c is not None and test(order(c)) for c in canon], dtype=bool)


def _entity_attribute(input_name: str, column: str, calc: dict[str, Any], manifest: dict[str, Any],
                      frames: dict[str, Any], base, entity: str, evidence: Evidence, name: str):
    """The value of an input column for every row of base (rows of the aggregated input). A column of another input is
    mapped by entity; an entity with more than one value there makes the grouping ambiguous (None)."""
    if input_name == calc["dataset"]:
        return frames[input_name].loc[base.index, column].to_numpy(dtype=object)
    other = manifest["logical_datasets"][input_name]
    mapping = frames[input_name][[other["entity_column"], column]].drop_duplicates()
    ambiguous = mapping[mapping.duplicated(subset=[other["entity_column"]], keep=False)]
    if len(ambiguous):
        evidence.add(f"output.{name}.group_keys", "FAIL", "GROUP_KEY_AMBIGUOUS", key=column,
                     entities=_sample(ambiguous[other["entity_column"]].astype(str)),
                     detail="An entity has several values of the grouping attribute in its reference input.")
        return None
    lookup = dict(zip(mapping[other["entity_column"]].astype(str), mapping[column]))
    return base[entity].astype(str).map(lookup).to_numpy(dtype=object)


def _normalized_key(value: Any, unknown: set[str]) -> str:
    if value is None or (isinstance(value, float) and value != value):
        return NULL_KEY
    text = str(value.date()) if hasattr(value, "date") and hasattr(value, "hour") else str(value)
    return NULL_KEY if not text.strip() or text in unknown else text


def _attach_groups(calc: dict[str, Any], manifest: dict[str, Any], frames: dict[str, Any], base, entity: str,
                   evidence: Evidence, name: str):
    """(work, key columns, membership) for base (entity rows): work holds '_row' (the base index) and one column per
    key. group_by maps each row to one group (a missing value: the NULL_KEY group, or dropped with
    missing_group_policy EXCLUDE); segments map a row to every segment whose predicates all hold (rows in no segment
    are not aggregated). None when a grouping attribute is ambiguous."""
    import numpy as np
    import pandas as pd

    params = {p["name"]: p["value"] for p in calc["params"]}
    if calc.get("segments"):
        parts, members, membership = [], np.zeros(len(base), dtype=bool), {}
        for segment in calc["segments"]:
            mask = np.ones(len(base), dtype=bool)
            for predicate in segment["predicates"]:
                values = _entity_attribute(predicate["input"], predicate["column"], calc, manifest, frames, base,
                                           entity, evidence, name)
                if values is None:
                    return None
                mask &= _segment_mask(values, predicate)
            members |= mask
            membership[segment["label"]] = int(base.loc[mask, entity].nunique()) if entity else int(mask.sum())
            parts.append(pd.DataFrame({"_row": base.index[mask], "segment": segment["label"]}))
        work = pd.concat(parts, ignore_index=True)
        outside = int(base.loc[~members, entity].nunique()) if entity else int((~members).sum())
        return work, ["segment"], {"segment_members": membership, "entities_in_no_segment": outside}
    unknown = set(params.get("unknown_group_values") or [])
    work = pd.DataFrame({"_row": base.index})
    columns = []
    for key in calc.get("group_by") or []:
        values = _entity_attribute(key["input"], key["column"], calc, manifest, frames, base, entity, evidence, name)
        if values is None:
            return None
        work[key["column"]] = [_normalized_key(v, unknown) for v in values]
        columns.append(key["column"])
    if params.get("missing_group_policy") == "EXCLUDE":
        mask = np.ones(len(work), dtype=bool)
        for column in columns:
            mask &= (work[column] != NULL_KEY).to_numpy()
        work = work[mask]
    return work, columns, {}


def _group_expected(items: list[dict[str, Any]], date_key: str | None, spec, manifest, frames, refs, period,
                    expected_all: set[str], evidence: Evidence, name: str) -> dict[str, Any] | None:
    """Recalculate GROUP_AGGREGATE items (one grouping) from the entity rows: membership from the catalog attribute
    (group_by column or segment predicates), values from the input column or the independently recalculated
    per-entity calculation. Rows: every in-scope entity's last period observation, or every period date (per_date,
    keyed by date_key)."""
    import numpy as np
    import pandas as pd

    calc = items[0]
    per_date = bool({p["name"]: p["value"] for p in calc["params"]}.get("per_date"))
    dataset = calc["dataset"]
    logical = manifest["logical_datasets"][dataset]
    entity, time = logical["entity_column"], logical["date_column"]
    frame = frames[dataset]
    rows = frame[frame[entity].astype(str).isin(expected_all)] if entity else frame
    excluded = _exclusions(spec, frame, entity, time, period, expected_all, evidence) if entity and time else set()
    rows = rows[~rows[entity].isin(excluded)] if excluded else rows
    if time:
        rows = rows[(rows[time] <= period["end"]) & ((rows[time] >= period["start"]) if period["mode"] != "LATEST"
                                                     else True)]
        if not per_date:
            rows = rows.sort_values([entity, time]).groupby(entity, sort=False).tail(1)
    base = rows
    attached = _attach_groups(calc, manifest, frames, base, entity, evidence, name)
    if attached is None:
        return None
    work, group_columns, membership = attached
    if per_date:
        work[date_key] = base.loc[work["_row"], time].dt.date.astype(str).to_numpy()
        group_columns = group_columns + [date_key]
    verified, unverified, expected_frames, samples = [], [], [], {}
    for item in items:
        params = {p["name"]: p["value"] for p in item["params"]}
        upstream = item["input_calculation"]
        if item["id"] in refs["unverifiable"]:
            unverified.append(item["id"])
            continue
        if upstream:
            values = refs["frames"][dataset].loc[work["_row"], _calc_column(spec, upstream)].to_numpy(dtype=float)
        else:
            values = base.loc[work["_row"], item["columns"][0]].to_numpy()
        grouping = work[group_columns].copy()
        grouping["_value"] = values
        if not per_date:  # per-entity values of each group: the observations of a group comparison
            numbers = pd.to_numeric(pd.Series(values), errors="coerce").to_numpy(dtype=float)
            labels = grouping[group_columns].astype(str).agg("|".join, axis=1).to_numpy()
            samples[item["id"]] = {label: numbers[(labels == label) & np.isfinite(numbers)]
                                   for label in sorted(set(labels))}
        function = params["function"]
        grouped = grouping.groupby(group_columns, sort=True, dropna=False)["_value"]
        if function == "COUNT":
            result = grouped.count()
        elif function == "COUNT_DISTINCT":
            result = grouped.nunique()
        else:
            numeric = grouping.assign(_value=pd.to_numeric(grouping["_value"], errors="coerce")).groupby(
                group_columns, sort=True, dropna=False)["_value"]
            result = {"SUM": numeric.sum, "AVG": numeric.mean, "MEDIAN": numeric.median, "MIN": numeric.min,
                      "MAX": numeric.max}[function]()
            if function == "SUM":
                result = result.where(numeric.count() > 0)
        contributors = grouped.count()
        result = result.astype(float).where(contributors >= int(params.get("min_observations") or 1))
        expected_frames.append(result.rename(item["output_column"] + "_ref"))
        verified.append(item["id"])
    expected = None
    if expected_frames:
        expected = pd.concat(expected_frames, axis=1).reset_index()
        expected.columns = group_columns + list(expected.columns[len(group_columns):])
    empty = sorted(label for label, count in membership.get("segment_members", {}).items() if count == 0)
    if empty:
        evidence.add(f"output.{name}.segments", "INCOMPLETE", "SEGMENT_EMPTY", segments=empty,
                     members=membership["segment_members"],
                     detail="No in-scope entity satisfies these segments' predicates in the period; check the values "
                            "against the catalog (get_dimension_values) instead of reporting the segment.")
        return None  # nothing to compare an empty segment with
    if membership:
        evidence.add(f"output.{name}.segments", "PASS", **membership)
    return {"expected": expected, "keys": group_columns, "verified": verified, "unverified": unverified,
            "entities": int(base[entity].nunique()) if entity else len(base), "membership": membership,
            "samples": samples}


def _group_table(path: str, keys: list[str], value_columns: list[str], date_key: str | None, unknown: set[str],
                 evidence: Evidence, name: str):
    import pyarrow.parquet as pq

    schema = pq.read_schema(path).names
    missing = [c for c in keys + value_columns if c not in schema]
    if missing:
        evidence.add(f"output.{name}", "FAIL", "REQUIRED_OUTPUT_MISSING", missing_columns=missing,
                     detail="Declared key or value columns are missing from the output.")
        return None
    table = pq.read_table(path, columns=list(dict.fromkeys(keys + value_columns))).to_pandas()
    for column in keys:
        if column == date_key:
            table[column] = _dates(table[column]).dt.date.astype(str)
        else:
            table[column] = [_normalized_key(v, unknown) for v in table[column]]
    return table


def _check_groups(output, path, used, spec, manifest, frames, refs, period, expected_all, evidence, scope,
                  context=None):
    """GROUP / GROUP_DATE outputs: recompute every group from the entity rows, then compare keys (omitted or extra
    groups), the top-N over every recalculated group, and values (cross-group contamination shows as a value
    mismatch)."""
    import numpy as np

    name = output["name"]
    keys = list(output["key_columns"])
    value_columns = [c["output_column"] for c in used]
    calc = used[0]
    params = {p["name"]: p["value"] for p in calc["params"]}
    per_date = bool(params.get("per_date"))
    date_key = output.get("date_column") if per_date else None
    table = _group_table(path, keys, value_columns, date_key, set(params.get("unknown_group_values") or []),
                         evidence, name)
    if table is None:
        return scope
    scope.update(rows=len(table), checked=True)
    duplicates = int(table.duplicated(subset=keys, keep=False).sum())
    if duplicates:
        evidence.add(f"output.{name}.grain", "FAIL", "OUTPUT_GRAIN_VIOLATION", rows=duplicates, key=keys,
                     detail="Several output rows share one group key.")
        return scope
    result = _group_expected(used, date_key, spec, manifest, frames, refs, period, expected_all, evidence, name)
    if result is None:
        return scope
    verified, unverified = result["verified"], result["unverified"]
    if result["expected"] is None:
        evidence.add(f"output.{name}", "SKIPPED", detail="No independent reference for these group values.")
        scope["scope_unverifiable"] = True
        return scope
    expected = result["expected"]
    expected.columns = keys + list(expected.columns[len(keys):])
    merged = expected.merge(table, on=keys, how="outer", indicator=True)
    in_ref, in_out = merged["_merge"] != "right_only", merged["_merge"] != "left_only"
    omitted, extra = merged[in_ref & ~in_out], merged[in_out & ~in_ref]
    ranking = output.get("ranking")
    if ranking:
        column = next(c["output_column"] for c in used if c["id"] == ranking["calculation"]) + "_ref"
        values = _numeric(merged[column])
        labels = merged[keys].astype(str).agg("|".join, axis=1).to_numpy()
        index = np.where(in_ref.to_numpy())[0]
        picked, boundary, population = _ranked(values[index], labels[index], ranking["direction"], ranking["limit"],
                                               ranking["tie_policy"])
        chosen = np.zeros(len(merged), dtype=bool)
        chosen[index[sorted(picked)]] = True
        wrong_missing, wrong_extra = merged[chosen & ~in_out], merged[in_out & ~chosen]
        if len(wrong_missing) or len(wrong_extra):
            evidence.add(f"output.{name}.ranking", "FAIL", "RANKING_MISMATCH", missing=len(wrong_missing),
                         unexpected=len(wrong_extra), candidates=population, limit=ranking["limit"],
                         missing_examples=wrong_missing[keys].head(MAX_EXAMPLES).to_dict("records"),
                         unexpected_examples=wrong_extra[keys].head(MAX_EXAMPLES).to_dict("records"),
                         detail="The emitted groups are not the top-N of every recalculated group.")
        else:
            evidence.add(f"output.{name}.ranking", "PASS", candidates=population, limit=ranking["limit"],
                         direction=ranking["direction"], boundary_value=_round(boundary))
        compare = merged[in_out & chosen]
    else:
        if len(omitted) or len(extra):
            evidence.add(f"output.{name}.groups", "FAIL", "GROUP_COVERAGE_MISMATCH", omitted=len(omitted),
                         unexpected=len(extra), omitted_examples=omitted[keys].head(MAX_EXAMPLES).to_dict("records"),
                         unexpected_examples=extra[keys].head(MAX_EXAMPLES).to_dict("records"),
                         detail="Groups in the recalculated result are missing from the output, or the output has "
                                "groups the scope does not produce.")
        else:
            evidence.add(f"output.{name}.groups", "PASS", groups=int(in_ref.sum()), entities=result["entities"],
                         null_key_groups=int((merged[keys] == NULL_KEY).any(axis=1).sum()), key=keys)
        compare = merged[in_ref & in_out]
    checked_total = 0
    for item in used:
        if item["id"] not in verified:
            continue
        column = item["output_column"]
        actual, reference = _numeric(compare[column]), _numeric(compare[column + "_ref"])
        ok = _compare(actual, reference)
        checked_total += len(ok)
        if not ok.all():
            bad = compare[~ok]
            upstream = next((c for c in spec["calculations"] if c["id"] == item["input_calculation"]), None)
            diagnosis = _diagnose_scale(upstream, actual[~ok], reference[~ok]) if upstream else None
            evidence.add(f"calculation.{item['id']}.{name}", "FAIL", "CALCULATION_MISMATCH", method=item["method"],
                         mismatched=int((~ok).sum()), checked=len(ok),
                         examples=[{**{k: r[k] for k in keys}, "expected": _round(r[column + "_ref"]),
                                    "actual": _round(r[column])} for _, r in bad.head(MAX_EXAMPLES).iterrows()],
                         **({"diagnosis": diagnosis} if diagnosis else {}),
                         detail="Group values differ from the independent recalculation (for example entities counted "
                                "in the wrong group).")
        else:
            evidence.add(f"calculation.{item['id']}.{name}", "PASS", method=item["method"], checked=len(ok))
    for item_id in unverified:
        evidence.add(f"calculation.{item_id}.{name}", "SKIPPED", detail="No independent reference for the aggregated "
                                                                         "calculation.")
    scope.update(groups=int(in_ref.sum()), values_checked=checked_total, verified_calculations=verified,
                 unverified_calculations=unverified)
    context = context or {}
    metric = context.get("primary_metric")
    if context.get("design_type") in ("COMPARATIVE", "EXPLORATORY_SEARCH") and metric in result["samples"]:
        scope["comparison"] = _comparison(result["samples"][metric], context.get("comparator") or {})
    return scope


def _comparison(samples: dict[str, Any], comparator: dict[str, Any]) -> dict[str, Any]:
    """Welch statistics of the compared groups from the validator's own per-entity values (the null-key group is not
    compared)."""
    import numpy as np

    groups = {g: v for g, v in samples.items() if g != NULL_KEY}
    listed = list(comparator.get("groups") or sorted(groups))
    summary = {g: {"n": int(len(v)), "mean": _round(np.mean(v)) if len(v) else None,
                   "std": _round(np.std(v, ddof=1)) if len(v) > 1 else None} for g, v in groups.items()}
    present = [g for g in listed if g in groups]
    rows = []
    if comparator.get("type") == "ALL_OTHERS":
        for g in present:
            others = [v for o, v in groups.items() if o != g]
            rows.append(_welch(g, groups[g], "ALL_OTHERS", np.concatenate(others) if others else np.array([])))
    else:
        rows = [_welch(a, groups[a], b, groups[b]) for a, b in itertools.combinations(present, 2)]
    return {"type": comparator.get("type") or "GROUPS", "groups": summary, "comparisons": rows,
            "missing_groups": [g for g in listed if g not in groups]}


def _welch(a: str, x, b: str, y) -> dict[str, Any]:
    import numpy as np

    row: dict[str, Any] = {"a": a, "b": b, "n_a": int(len(x)), "n_b": int(len(y)), "mean_a": None, "mean_b": None,
                           "difference": None, "standard_error": None, "df": None}
    if len(x) < 2 or len(y) < 2:
        return row
    va, vb = float(np.var(x, ddof=1)) / len(x), float(np.var(y, ddof=1)) / len(y)
    se = math.sqrt(va + vb)
    df = (va + vb) ** 2 / (va ** 2 / (len(x) - 1) + vb ** 2 / (len(y) - 1)) if se > 0 else len(x) + len(y) - 2
    row.update(mean_a=float(np.mean(x)), mean_b=float(np.mean(y)), difference=float(np.mean(x) - np.mean(y)),
               standard_error=se, df=float(df))
    return row


def _check_group_pairs(output, path, used, spec, manifest, frames, refs, period, expected_all, evidence, scope,
                       context=None):
    """GROUP_PAIR outputs: recompute the aligned per-date group series from the entity rows (the same group check as
    GROUP_DATE outputs), then the correlation of every pair of non-null groups on their common dates."""
    import numpy as np
    import reference

    name = output["name"]
    calcs = {c["id"]: c for c in spec["calculations"]}
    series_calc = calcs[used[0]["input_calculation"]]
    keys = list(output["key_columns"])
    series_params = {p["name"]: p["value"] for p in series_calc["params"]}
    table = _group_table(path, keys, [c["output_column"] for c in used], None,
                         set(series_params.get("unknown_group_values") or []), evidence, name)
    if table is None:
        return scope
    scope.update(rows=len(table), checked=True)
    if any(c["id"] in refs["unverifiable"] for c in used) or series_calc["id"] in refs["unverifiable"]:
        evidence.add(f"output.{name}", "SKIPPED", detail="The group series has no independent reference; the "
                                                         "correlations cannot be recalculated.")
        scope.update(scope_unverifiable=True, unverified_calculations=[c["id"] for c in used])
        return scope
    result = _group_expected([series_calc], "_date", spec, manifest, frames, refs, period, expected_all, evidence,
                             name)
    if result is None or result["expected"] is None:
        return scope
    key = result["keys"][0]
    wide = result["expected"].pivot(index="_date", columns=key, values=series_calc["output_column"] + "_ref")
    groups = sorted(g for g in wide.columns if g != NULL_KEY)
    series = {g: wide[g].to_numpy(dtype=float) for g in groups}
    overlap = {(a, b): int((np.isfinite(series[a]) & np.isfinite(series[b])).sum())
               for a, b in itertools.combinations(groups, 2)}
    evidence.add(f"output.{name}.series", "PASS", calculation=series_calc["id"], groups=groups,
                 dates={g: int(np.isfinite(series[g]).sum()) for g in groups},
                 common_dates={f"{a}|{b}": n for (a, b), n in overlap.items()},
                 detail="Per-date group series recalculated from the entity rows and aligned on common dates.")
    left, right = keys
    checked_total = 0
    verified = [series_calc["id"]]
    for calc in used:
        params = {p["name"]: p["value"] for p in calc["params"]}
        expected = {pair: reference.pair_correlation(series[pair[0]], series[pair[1]], params["method"],
                                                     int(params["min_overlap"])) for pair in overlap}
        actual: dict[tuple[str, str], float] = {}
        for _, row in table.iterrows():
            pair = tuple(sorted((row[left], row[right])))
            if pair[0] != pair[1]:
                actual.setdefault(pair, float(_numeric(np.array([row[calc["output_column"]]]))[0]))
        missing, extra = sorted(set(expected) - set(actual)), sorted(set(actual) - set(expected))
        if missing or extra:
            evidence.add(f"output.{name}.pairs", "FAIL", "GROUP_COVERAGE_MISMATCH", missing=[list(p) for p in missing[:10]],
                         unexpected=[list(p) for p in extra[:10]],
                         detail="The group pairs differ from every pair of recalculated groups.")
        common = sorted(set(expected) & set(actual))
        ok = _compare(np.array([actual[p] for p in common], dtype=float),
                      np.array([expected[p] for p in common], dtype=float))
        checked_total += len(ok)
        if len(ok) and not ok.all():
            evidence.add(f"calculation.{calc['id']}.{name}", "FAIL", "CALCULATION_MISMATCH", method=calc["method"],
                         mismatched=int((~ok).sum()), checked=len(ok),
                         examples=[{"pair": list(p), "expected": _round(expected[p]), "actual": _round(actual[p]),
                                    "common_dates": overlap[p]} for p, good in zip(common, ok) if not good][:MAX_EXAMPLES],
                         detail="Correlations differ from the recalculation on the aligned group series (check the "
                                "group membership, the per-date aggregate, and that only common dates are used).")
        else:
            evidence.add(f"calculation.{calc['id']}.{name}", "PASS", method=calc["method"], checked=len(ok))
        verified.append(calc["id"])
        if (context or {}).get("primary_metric") == calc["id"]:
            scope["association"] = {"method": params["method"], "unit": "GROUP_DATE",
                                    "pairs": [{"pair": list(p), "r": _round(expected[p]), "n": overlap[p]}
                                              for p in sorted(expected)]}
    scope.update(groups=len(groups), pairs=len(overlap), values_checked=checked_total, verified_calculations=verified,
                 unverified_calculations=[])
    return scope


def _diagnose_scale(calc: dict[str, Any], actual, expected) -> dict | None:
    """A period statistic that differs from the reference by a constant factor: annualized or percent-scaled."""
    import numpy as np

    if calc["method"] != "PERIOD_STAT":
        return None
    usable = np.isfinite(actual) & np.isfinite(expected) & (np.abs(expected) > 0)
    if not usable.any():
        return None
    ratio = actual[usable] / expected[usable]
    for label, factor in (("ANNUALIZED_SQRT_252", math.sqrt(252)), ("ANNUALIZED_SQRT_252_PERCENT", 100 * math.sqrt(252)),
                          ("PERCENT_SCALE", 100.0), ("FRACTION_SCALE", 0.01)):
        if np.allclose(ratio, factor, rtol=1e-6):
            return {"finding": "SCALE_DIFFERS", "factor": label,
                    "detail": "The values equal the period statistic times a constant; the spec asks for the plain "
                              "statistic of the input values (not annualized, same unit)."}
    return None


def _pair_series(frame, entity: str, time: str, tickers: list[str], column: str, kind: str, period: dict[str, Any],
                 warmup: bool = True) -> dict[str, dict]:
    """Per ticker: {date: transformed value} inside the period (transformed on the full history when warmup)."""
    import reference

    series = {}
    for ticker, part in frame[frame[entity].isin(tickers)].groupby(entity):
        if not warmup:
            part = part[part[time] >= period["start"]]
        values = reference.transform(part[column].to_numpy(dtype=float), kind)
        mask = (part[time] >= period["start"]).to_numpy() & (part[time] <= period["end"]).to_numpy()
        series[ticker] = dict(zip(part[time].to_numpy()[mask], values[mask]))
    return series


def _pair_values(series: dict[str, dict], tickers: list[str], method: str, min_overlap: int,
                 listwise: bool = False) -> dict[tuple[str, str], float]:
    import numpy as np
    import reference

    shared = set.intersection(*(set(series.get(t, {})) for t in tickers)) if listwise and tickers else None
    if shared is not None:  # listwise deletion: only dates where every ticker has a defined value
        shared = {d for d in shared if all(np.isfinite(series[t][d]) for t in tickers)}
    out = {}
    for a, b in itertools.combinations(tickers, 2):
        common = sorted(shared if shared is not None else set(series.get(a, {})) & set(series.get(b, {})))
        out[(a, b)] = reference.pair_correlation(np.array([series[a][d] for d in common], dtype=float),
                                                 np.array([series[b][d] for d in common], dtype=float),
                                                 method, min_overlap)
    return out


def _diagnose_pairs(frame, entity, time, tickers, column, params, period, actual, pairs) -> dict | None:
    """Explain a pair-correlation mismatch: which transform, method, or procedure the actual values match."""
    import numpy as np

    act = np.array([actual[p] for p in pairs], dtype=float)

    def matches(values: dict) -> bool:
        return bool(_compare(act, np.array([values[p] for p in pairs], dtype=float)).all())

    for kind in ("SIMPLE_RETURN", "LOG_RETURN", "NONE"):
        series = _pair_series(frame, entity, time, tickers, column, kind, period)
        for method in ("PEARSON", "SPEARMAN"):
            if (kind, method) == (params["transform"], params["method"]):
                continue
            if matches(_pair_values(series, tickers, method, params["min_overlap"])):
                name = "transform" if method == params["method"] else "method"
                if kind != params["transform"] and method != params["method"]:
                    name = "transform+method"
                return {"finding": "PARAMETER_DIFFERS", "parameter": name,
                        "spec_value": f"{params['transform']}/{params['method']}", "values_match": f"{kind}/{method}"}
    series = _pair_series(frame, entity, time, tickers, column, params["transform"], period, warmup=False)
    if params["transform"] != "NONE" and matches(_pair_values(series, tickers, params["method"],
                                                               params["min_overlap"])):
        return {"finding": "WARMUP_NOT_USED", "detail": "The values match returns computed only from prices inside "
                                                        "the analysis period, which drops the first return; compute "
                                                        "returns on the full input history, then restrict dates."}
    if len(tickers) > 2:
        series = _pair_series(frame, entity, time, tickers, column, params["transform"], period)
        if matches(_pair_values(series, tickers, params["method"], params["min_overlap"], listwise=True)):
            return {"finding": "LISTWISE_DELETION", "detail": "The values match correlations over only the dates where "
                                                              "every ticker has a value; the spec uses each pair's own "
                                                              "overlapping dates."}
    return None


def _check_pairs(output, table, key_columns, used, spec, manifest, frames, period, evidence, scope, context=None):
    import numpy as np

    calc = used[0]
    if calc["method"] != "CORRELATION":
        evidence.add(f"output.{output['name']}", "SKIPPED", detail="CUSTOM pair calculations are not recalculated.")
        return scope
    logical = manifest["logical_datasets"][calc["dataset"]]
    entity, time = logical["entity_column"], logical["date_column"]
    frame = frames[calc["dataset"]]
    params = {p["name"]: p["value"] for p in calc["params"]}
    tickers = sorted(set(spec["universe"]["tickers"]) & set(frame[entity]))
    column = calc["columns"][0]
    series = _pair_series(frame, entity, time, tickers, column, params["transform"], period)
    expected = _pair_values(series, tickers, params["method"], params["min_overlap"])
    left, right = key_columns
    actual = {}
    for _, row in table.iterrows():
        pair = tuple(sorted((row[left], row[right])))
        if pair[0] != pair[1]:
            actual.setdefault(pair, float(_numeric(np.array([row[calc["output_column"]]]))[0]))
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    scope.update(pairs_expected=len(expected), pairs_actual=len(actual))
    if missing or extra:
        evidence.add(f"output.{output['name']}.pairs", "FAIL", "UNIVERSE_MISMATCH", missing=[list(p) for p in missing[:10]],
                     unexpected=[list(p) for p in extra[:10]], detail="Ticker pairs differ from the spec universe.")
    common = sorted(set(expected) & set(actual))
    ok = _compare(np.array([actual[p] for p in common]), np.array([expected[p] for p in common]))
    if len(ok) and not ok.all():
        bad = [p for p, good in zip(common, ok) if not good]
        diagnosis = _diagnose_pairs(frame, entity, time, tickers, column, params, period, actual, bad[:50])
        evidence.add(f"calculation.{calc['id']}.{output['name']}", "FAIL", "CALCULATION_MISMATCH",
                     mismatched=int((~ok).sum()), checked=len(ok),
                     **({"diagnosis": diagnosis} if diagnosis else {}),
                     examples=[{"pair": list(p), "expected": _round(expected[p]), "actual": _round(actual[p])}
                               for p in bad][:MAX_EXAMPLES])
    else:
        evidence.add(f"calculation.{calc['id']}.{output['name']}", "PASS", method="CORRELATION", checked=len(ok))
    scope.update(values_checked=len(ok), verified_calculations=[calc["id"]], unverified_calculations=[])
    if (context or {}).get("primary_metric") == calc["id"]:
        import numpy as np

        def common(a: str, b: str) -> int:
            shared = set(series.get(a, {})) & set(series.get(b, {}))
            return sum(1 for d in shared if np.isfinite(series[a][d]) and np.isfinite(series[b][d]))

        scope["association"] = {"method": params["method"], "unit": "ENTITY_DATE",
                                 "pairs": [{"pair": list(p), "r": _round(expected[p]), "n": common(*p)}
                                           for p in sorted(expected)]}
    return scope


# ---------------------------------------------------------------- event studies

def _segment_stats(outcome, kept, eligible, censored, dropped, mask) -> dict[str, Any]:
    import numpy as np
    from scipy import stats

    events = outcome[kept & mask]
    base = outcome[eligible & mask]
    n, nb = len(events), len(base)
    row: dict[str, Any] = {
        "event_count": int(n), "mean": float(events.mean()) if n else float("nan"),
        "median": float(np.median(events)) if n else float("nan"),
        "hit_rate": float((events > 0).mean()) if n else float("nan"),
        "baseline_count": int(nb), "baseline_mean": float(base.mean()) if nb else float("nan"),
        "baseline_median": float(np.median(base)) if nb else float("nan"),
        "censored_count": int((censored & mask).sum()), "overlapping_dropped": int((dropped & mask).sum()),
    }
    row["delta_mean"] = row["mean"] - row["baseline_mean"]
    # uncertainty of the event mean and of its difference from the baseline mean (Welch)
    std = float(events.std(ddof=1)) if n > 1 else float("nan")
    base_std = float(base.std(ddof=1)) if nb > 1 else float("nan")
    se = std / np.sqrt(n) if n > 1 else float("nan")
    delta_se = float(np.sqrt(se ** 2 + (base_std / np.sqrt(nb)) ** 2)) if n > 1 and nb > 1 else float("nan")
    t = float(stats.t.ppf(0.975, n - 1)) if n > 1 else float("nan")
    row.update(std=std, standard_error=se, ci95=[row["mean"] - t * se, row["mean"] + t * se] if n > 1 else None,
               delta_standard_error=delta_se,
               delta_ci95=[row["delta_mean"] - t * delta_se, row["delta_mean"] + t * delta_se] if n > 1 and nb > 1
               else None, _t_df=n - 1)
    return row


def _event_study_reference(calc: dict[str, Any], spec: dict[str, Any], manifest: dict[str, Any],
                           frames: dict[str, Any], refs: dict[str, Any], period: dict[str, Any], universe: set[str],
                           research_context: dict[str, Any]) -> dict[str, Any]:
    """Recompute events, outcomes and the baseline from the validator's own reference values."""
    import numpy as np
    import pandas as pd

    logical = manifest["logical_datasets"][calc["dataset"]]
    entity, time = logical["entity_column"], logical["date_column"]
    frame = frames[calc["dataset"]]
    ref = refs["frames"][calc["dataset"]]
    calcs = {c["id"]: c for c in spec["calculations"]}
    outcome_calc = calcs[calc["input_calculation"]]
    horizon = int(next(p["value"] for p in outcome_calc["params"] if p["name"] == "horizon"))
    params = {p["name"]: p["value"] for p in calc["params"]}
    in_period = ((frame[time] >= period["start"]) & (frame[time] <= period["end"]) &
                 frame[entity].isin(universe)).to_numpy()
    outcome = ref[outcome_calc["output_column"]].to_numpy(dtype=float)
    defined, true = np.ones(len(frame), dtype=bool), np.ones(len(frame), dtype=bool)
    for predicate in calc["signal"]:
        values = ref[calcs[predicate["calculation"]]["output_column"]].to_numpy(dtype=float)
        finite = np.isfinite(values)
        with np.errstate(invalid="ignore"):
            test = {">": values > predicate["value"], ">=": values >= predicate["value"],
                    "<": values < predicate["value"], "<=": values <= predicate["value"],
                    "==": np.isclose(values, predicate["value"]), "!=": ~np.isclose(values, predicate["value"])}[
                predicate["op"]]
        defined &= finite
        true &= finite & test
    has_outcome = np.isfinite(outcome)
    eligible = in_period & defined & has_outcome
    raw = in_period & defined & true
    censored = raw & ~has_outcome
    events = raw & has_outcome
    kept = events.copy()
    overlapping = 0
    positions = frame.groupby(entity, sort=False).cumcount().to_numpy()
    for _, index in frame.groupby(entity, sort=False).indices.items():
        last = None
        for i in index[events[index]]:
            if last is not None and positions[i] < positions[last] + horizon:
                overlapping += 1
                if params["overlap_policy"] == "NON_OVERLAPPING":
                    kept[i] = False
                    continue
            last = i
    dropped = events & ~kept
    segments = {"ALL": np.ones(len(frame), dtype=bool)}
    holdout = (spec.get("research") or {}).get("holdout")
    if holdout:
        dates = frame[time]
        cut = dates >= pd.Timestamp(holdout["start"])
        if holdout.get("end"):
            cut &= dates <= pd.Timestamp(holdout["end"])
        segments["IN_SAMPLE"] = (dates < pd.Timestamp(holdout["start"])).to_numpy()
        segments["OUT_OF_SAMPLE"] = cut.to_numpy()
    rows = {name: _segment_stats(outcome, kept, eligible, censored, dropped, mask)
            for name, mask in segments.items()}
    covered = frame.loc[eligible, entity].nunique()
    return {"segments": rows, "horizon": horizon, "overlap_policy": params["overlap_policy"],
            "overlapping_events": overlapping, "entities_with_eligible": int(covered),
            "universe_entities": len(universe),
            "coverage_pct": round(100.0 * covered / len(universe), 2) if universe else 0.0}


def _check_summary(output, path, calc, spec, manifest, frames, refs, period, expected_all, evidence, scope,
                   research_context):
    import numpy as np
    import pyarrow.parquet as pq

    name = output["name"]
    if path is None:
        evidence.add(f"output.{name}", "FAIL", "REQUIRED_OUTPUT_MISSING",
                     detail="The spec declares this event-study summary, but the analysis did not emit it.")
        return scope
    wanted = ["segment", *EVENT_COLUMNS]
    schema = pq.read_schema(path).names
    missing = [c for c in wanted if c not in schema]
    if missing:
        evidence.add(f"output.{name}", "FAIL", "REQUIRED_OUTPUT_MISSING", missing_columns=missing,
                     detail="An event-study summary has the columns segment, " + ", ".join(EVENT_COLUMNS) + ".")
        return scope
    table = pq.read_table(path, columns=wanted).to_pandas()
    table["segment"] = table["segment"].astype(str)
    scope.update(rows=len(table), checked=True)
    if table["segment"].duplicated().any():
        evidence.add(f"output.{name}.grain", "FAIL", "OUTPUT_GRAIN_VIOLATION", key=["segment"],
                     detail="Several rows share one segment.")
        return scope
    expected_segments = ["ALL"] + (["IN_SAMPLE", "OUT_OF_SAMPLE"] if (spec.get("research") or {}).get("holdout")
                                   else [])
    got = set(table["segment"])
    if got != set(expected_segments):
        evidence.add(f"output.{name}.segments", "FAIL", "ANALYSIS_SCOPE_MISMATCH", expected=expected_segments,
                     actual=sorted(got), detail="The summary rows are not the declared segments.")
    if calc["id"] in refs["unverifiable"]:
        evidence.add(f"calculation.{calc['id']}.{name}", "SKIPPED", method="EVENT_STUDY",
                     detail="A signal or the outcome has no independent reference, so events cannot be recalculated.")
        scope.update(scope_unverifiable=True, verified_calculations=[], unverified_calculations=[calc["id"]],
                     event_study={"unverifiable": True})
        return scope
    logical = manifest["logical_datasets"][calc["dataset"]]
    frame = frames[calc["dataset"]]
    excluded = _exclusions(spec, frame, logical["entity_column"], logical["date_column"], period, expected_all,
                           evidence)
    reference_values = _event_study_reference(calc, spec, manifest, frames, refs, period, expected_all - excluded,
                                              research_context)
    mismatches, checked = [], 0
    for _, row in table.iterrows():
        expected = reference_values["segments"].get(row["segment"])
        if expected is None:
            continue
        for column in EVENT_COLUMNS:
            actual = float(_numeric(np.array([row[column]]))[0])
            want = float(expected[column])
            checked += 1
            same = (np.isnan(actual) and np.isnan(want)) or (
                actual == want if column in COUNT_COLUMNS else bool(np.isclose(actual, want, rtol=RTOL, atol=ATOL)))
            if not same:
                mismatches.append({"segment": row["segment"], "column": column, "expected": _round(want),
                                   "actual": _round(actual)})
    if mismatches:
        evidence.add(f"calculation.{calc['id']}.{name}", "FAIL", "CALCULATION_MISMATCH", method="EVENT_STUDY",
                     mismatched=len(mismatches), checked=checked, examples=mismatches[:MAX_EXAMPLES],
                     detail="The summary differs from the independent recalculation of events, outcomes and the "
                            "baseline.")
    else:
        evidence.add(f"calculation.{calc['id']}.{name}", "PASS", method="EVENT_STUDY", checked=checked)
    all_row = reference_values["segments"]["ALL"]
    evidence.add(f"event_study.{calc['id']}", "PASS", events=all_row["event_count"],
                 baseline=all_row["baseline_count"], censored=all_row["censored_count"],
                 overlapping_events=reference_values["overlapping_events"],
                 coverage_pct=reference_values["coverage_pct"])
    scope.update(values_checked=checked, verified_calculations=[calc["id"]], unverified_calculations=[],
                 event_study=reference_values)
    return scope


# ---------------------------------------------------------------- evidence assessment (post-run evidence gate)

def _clean(value: Any) -> Any:
    if isinstance(value, float):
        return None if value != value else round(value, 10)
    if isinstance(value, list):
        return [_clean(v) for v in value]
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items() if not k.startswith("_")}
    return value


def _excludes_zero(interval) -> bool:
    return bool(interval) and all(v == v for v in interval) and (interval[0] > 0 or interval[1] < 0)


def assess(context: dict[str, Any], status: str, level: str, scopes: list[dict[str, Any]]) -> dict[str, Any]:
    """Does the validated evidence support the intended claim? Deterministic; uses only the validator's own
    recalculated statistics, never numbers the analysis reported."""
    import math

    from scipy import stats

    claim = context.get("evidence_standard") or "CALCULATION"
    thresholds = {**DEFAULT_THRESHOLDS, **(context.get("thresholds") or {})}
    checks: dict[str, str] = {"scope": "PASS" if status == "PASS" else "FAIL" if status == "FAILED" else "PARTIAL",
                              "calculation": "PASS" if level == "CALCULATION_VERIFIED" else
                              "PARTIAL" if level == "SCOPE_VERIFIED" else "NOT_VERIFIABLE"}
    constraints: list[str] = []
    statistics: dict[str, Any] = {}
    if status == "FAILED":
        return {"claim_type": claim, "decision": "INVALID", "evidence_level": "NONE", "checks": checks,
                "reporting_constraints": ["Validation failed: no result of this analysis may be reported as a "
                                          "finding."], "statistics": {}, "source": "VALIDATOR"}
    if status == "INCOMPLETE":
        return {"claim_type": claim, "decision": "INSUFFICIENT_EVIDENCE", "evidence_level": "NONE", "checks": checks,
                "reporting_constraints": ["The input does not cover the requested scope; state what is missing."],
                "statistics": {}, "source": "VALIDATOR"}
    if claim in ("CALCULATION", "SCREEN", "DESCRIPTIVE", "SCENARIO"):
        for name in ("minimum_sample", "baseline", "multiple_testing", "temporal_holdout"):
            checks[name] = "NOT_APPLICABLE"
        decision = "SUPPORTED" if status == "PASS" and level == "CALCULATION_VERIFIED" else "PARTIALLY_SUPPORTED"
        if decision != "SUPPORTED":
            constraints.append("State that the calculation could not be fully recalculated independently.")
        if claim == "SCENARIO":
            constraints.append("Present the result as a hypothetical scenario, not a forecast.")
        return {"claim_type": claim, "decision": decision,
                "evidence_level": "SCENARIO" if claim == "SCENARIO" else "OBSERVATION", "checks": checks,
                "reporting_constraints": constraints, "statistics": {}, "source": "VALIDATOR"}

    design = context.get("design_type")
    if design == "COMPARATIVE" or (design == "EXPLORATORY_SEARCH" and any(s.get("comparison") for s in scopes)):
        return _assess_comparison(context, claim, thresholds, checks, scopes)
    if design == "ASSOCIATION" or (design == "EXPLORATORY_SEARCH" and any(s.get("association") for s in scopes)):
        return _assess_association(context, claim, thresholds, checks, scopes)
    study = next((s["event_study"] for s in scopes if s.get("event_study")), None)
    constraints.append("Describe the result as a historical association, not causation.")
    if claim != "PREDICTIVE":
        constraints.append("Do not describe the result as a prediction of future returns.")
    if study is None or study.get("unverifiable"):
        checks["minimum_sample"] = checks["baseline"] = "NOT_VERIFIABLE"
        decision = "PARTIALLY_SUPPORTED" if claim == "EXPLORATORY" and status == "PASS" else "INSUFFICIENT_EVIDENCE"
        constraints.append("No independently recalculated event study supports this claim; report it as "
                           "exploratory at most.")
        return {"claim_type": claim, "decision": decision,
                "evidence_level": "EXPLORATORY" if decision == "PARTIALLY_SUPPORTED" else "NONE", "checks": checks,
                "reporting_constraints": constraints, "statistics": {}, "source": "VALIDATOR"}

    segments = study["segments"]
    holdout = context.get("holdout")
    main = segments["IN_SAMPLE"] if claim == "PREDICTIVE" and "IN_SAMPLE" in segments else segments["ALL"]
    tests = max(1, int(context.get("tests_on_hypothesis") or 1))
    checks["minimum_sample"] = "PASS" if main["event_count"] >= thresholds["min_events"] else "FAIL"
    checks["baseline"] = "PASS" if main["baseline_count"] >= thresholds["min_baseline_observations"] else "FAIL"
    checks["coverage"] = "PASS" if study["coverage_pct"] >= thresholds["min_coverage_pct"] else "PARTIAL"
    checks["overlap"] = "PASS" if study["overlap_policy"] == "NON_OVERLAPPING" or not study["overlapping_events"] \
        else "PARTIAL"
    checks["censoring"] = "PASS" if not main["censored_count"] else "PARTIAL"
    checks["uncertainty"] = "PASS" if _excludes_zero(main.get("delta_ci95")) else "PARTIAL"
    adjusted = None
    if main["event_count"] > 1 and main.get("delta_standard_error") == main.get("delta_standard_error"):
        t = float(stats.t.ppf(1 - 0.05 / (2 * tests), main["_t_df"]))
        adjusted = [main["delta_mean"] - t * main["delta_standard_error"],
                    main["delta_mean"] + t * main["delta_standard_error"]]
    checks["multiple_testing"] = "PASS" if _excludes_zero(adjusted) else "PARTIAL"
    if claim == "PREDICTIVE":
        out = segments.get("OUT_OF_SAMPLE")
        needed = max(10, math.ceil(thresholds["min_events"] / 3))
        consistent = bool(out) and out["event_count"] >= needed and out["delta_mean"] == out["delta_mean"] and \
            main["delta_mean"] == main["delta_mean"] and out["delta_mean"] * main["delta_mean"] > 0
        checks["temporal_holdout"] = "PASS" if consistent else "FAIL"
    else:
        checks["temporal_holdout"] = "NOT_APPLICABLE"
    if checks["minimum_sample"] == "FAIL" or checks["baseline"] == "FAIL":
        decision = "INSUFFICIENT_EVIDENCE"
    elif claim == "PREDICTIVE" and checks["temporal_holdout"] == "FAIL":
        decision = "INSUFFICIENT_EVIDENCE"
    elif all(checks[k] == "PASS" for k in ("calculation", "coverage", "uncertainty", "multiple_testing")):
        decision = "SUPPORTED"
    else:
        decision = "PARTIALLY_SUPPORTED"
    if claim == "EXPLORATORY" and decision == "SUPPORTED":
        decision = "PARTIALLY_SUPPORTED"
    level_name = {"PREDICTIVE": "PREDICTIVE_SIGNAL", "HISTORICAL_PATTERN": "PATTERN",
                  "EXPLORATORY": "EXPLORATORY"}[claim] if decision in ("SUPPORTED", "PARTIALLY_SUPPORTED") else "NONE"
    if claim == "PREDICTIVE" and decision != "SUPPORTED":
        constraints.append("Do not describe the result as predictive: the out-of-sample evidence does not support it.")
        if level_name == "PREDICTIVE_SIGNAL":
            level_name = "PATTERN"
    if claim == "EXPLORATORY":
        constraints.append("Label the finding as exploratory and hypothesis-generating.")
    constraints.append("Report the event count, the baseline, and the difference with its uncertainty.")
    if main["censored_count"]:
        constraints.append(f"{main['censored_count']} events near the end of the data had no complete outcome and "
                           f"were not counted.")
    if checks["coverage"] != "PASS":
        constraints.append(f"Only {study['coverage_pct']}% of the analysed universe had eligible observations.")
    if tests > 1:
        constraints.append(f"{tests} tests were run on this hypothesis; use the multiple-testing adjusted interval.")
    if checks["uncertainty"] != "PASS":
        constraints.append("The difference from the baseline is not distinguishable from zero at 95% confidence.")
    statistics = {"segments": segments, "horizon": study["horizon"], "overlap_policy": study["overlap_policy"],
                  "overlapping_events": study["overlapping_events"], "coverage_pct": study["coverage_pct"],
                  "tests_on_hypothesis": tests, "delta_ci_adjusted": adjusted, "confidence_level": 0.95}
    return {"claim_type": claim, "decision": decision, "evidence_level": level_name, "checks": checks,
            "reporting_constraints": constraints, "statistics": _clean(statistics), "source": "VALIDATOR",
            "holdout": holdout}


def _tests(context: dict[str, Any], actual: int) -> int:
    """Tests on this hypothesis for the multiple-testing adjustment: the earlier experiments' candidates plus this
    experiment's comparisons, counted from the data when there are more than it declared."""
    declared = int(context.get("candidates") or 1)
    earlier = max(0, int(context.get("tests_on_hypothesis") or declared) - declared)
    return max(1, earlier + max(declared, actual))


def _design_decision(claim: str, checks: dict[str, str], keys: tuple[str, ...]) -> tuple[str, str]:
    if checks.get("minimum_sample") == "FAIL":
        decision = "INSUFFICIENT_EVIDENCE"
    elif all(checks.get(k) == "PASS" for k in ("calculation",) + keys):
        decision = "SUPPORTED"
    else:
        decision = "PARTIALLY_SUPPORTED"
    if claim == "EXPLORATORY" and decision == "SUPPORTED":
        decision = "PARTIALLY_SUPPORTED"
    level = {"HISTORICAL_PATTERN": "PATTERN", "EXPLORATORY": "EXPLORATORY"}.get(claim, "OBSERVATION") \
        if decision != "INSUFFICIENT_EVIDENCE" else "NONE"
    return decision, level


def _assess_comparison(context: dict[str, Any], claim: str, thresholds: dict[str, Any], checks: dict[str, str],
                       scopes: list[dict[str, Any]]) -> dict[str, Any]:
    """Profile X for a COMPARATIVE design: group sizes, the differences of group means with Welch intervals, and the
    multiple-testing adjustment over every comparison actually made."""
    from scipy import stats

    comparison = next((s["comparison"] for s in scopes if s.get("comparison")), None)
    constraints = ["Describe differences between groups as historical associations, not causes.",
                   "Group membership is the catalog classification used by the spec (current, not point-in-time, "
                   "unless the catalog says otherwise)."]
    checks.update(baseline="NOT_APPLICABLE", temporal_holdout="NOT_APPLICABLE", overlap="NOT_APPLICABLE",
                  censoring="NOT_APPLICABLE")
    if comparison is None or not comparison["comparisons"]:
        checks.update(minimum_sample="NOT_VERIFIABLE", comparator="NOT_VERIFIABLE", uncertainty="NOT_VERIFIABLE",
                      multiple_testing="NOT_VERIFIABLE")
        constraints.append("No independently recalculated group comparison supports this claim.")
        return {"claim_type": claim, "decision": "INSUFFICIENT_EVIDENCE", "evidence_level": "NONE", "checks": checks,
                "reporting_constraints": constraints, "statistics": {}, "source": "VALIDATOR"}
    tests = _tests(context, len(comparison["comparisons"]))
    rows = []
    for row in comparison["comparisons"]:
        ci = adjusted = None
        if row["standard_error"]:
            half = float(stats.t.ppf(0.975, row["df"])) * row["standard_error"]
            wide = float(stats.t.ppf(1 - 0.05 / (2 * tests), row["df"])) * row["standard_error"]
            ci = [row["difference"] - half, row["difference"] + half]
            adjusted = [row["difference"] - wide, row["difference"] + wide]
        rows.append({**row, "ci95": ci, "ci_adjusted": adjusted})
    minimum = int(thresholds.get("min_group_observations") or 10)
    small = sorted({g for r in rows for g, n in ((r["a"], r["n_a"]), (r["b"], r["n_b"])) if n < minimum})
    checks["minimum_sample"] = "FAIL" if small else "PASS"
    checks["comparator"] = "PARTIAL" if comparison["missing_groups"] else "PASS"
    checks["coverage"] = "PASS" if checks["scope"] == "PASS" else "PARTIAL"
    checks["uncertainty"] = "PASS" if any(_excludes_zero(r["ci95"]) for r in rows) else "PARTIAL"
    checks["multiple_testing"] = "PASS" if any(_excludes_zero(r["ci_adjusted"]) for r in rows) else "PARTIAL"
    decision, level = _design_decision(claim, checks, ("minimum_sample", "comparator", "uncertainty",
                                                       "multiple_testing"))
    if small:
        constraints.append(f"Groups {small} have fewer than {minimum} entities; no difference can be supported.")
    if comparison["missing_groups"]:
        constraints.append(f"Groups {comparison['missing_groups']} had no in-scope entity and were not compared.")
    constraints.append("Report each group's size and mean, and each difference with its interval.")
    if tests > 1:
        constraints.append(f"{tests} comparisons were tested on this hypothesis; use the adjusted intervals.")
    if checks["multiple_testing"] != "PASS":
        constraints.append("No difference is distinguishable from zero after the multiple-testing adjustment.")
    if claim == "EXPLORATORY":
        constraints.append("Label the finding as exploratory and hypothesis-generating.")
    statistics = {"test": "Welch t on per-entity values", "comparator": comparison["type"],
                  "groups": comparison["groups"], "comparisons": rows, "tests_on_hypothesis": tests,
                  "confidence_level": 0.95}
    return {"claim_type": claim, "decision": decision, "evidence_level": level, "checks": checks,
            "reporting_constraints": constraints, "statistics": _clean(statistics), "source": "VALIDATOR"}


def _assess_association(context: dict[str, Any], claim: str, thresholds: dict[str, Any], checks: dict[str, str],
                        scopes: list[dict[str, Any]]) -> dict[str, Any]:
    """Profile X for an ASSOCIATION design: each recalculated correlation with its overlap, a Fisher-z interval, and
    the multiple-testing adjustment over every pair actually evaluated."""
    from scipy import stats

    association = next((s["association"] for s in scopes if s.get("association")), None)
    constraints = ["Describe the correlation as an association, not causation.",
                   "Observations of a time series are autocorrelated; the interval assumes independent observations "
                   "and can be too narrow."]
    checks.update(baseline="NOT_APPLICABLE", temporal_holdout="NOT_APPLICABLE", comparator="NOT_APPLICABLE")
    if association is None or not association["pairs"]:
        checks.update(minimum_sample="NOT_VERIFIABLE", uncertainty="NOT_VERIFIABLE", multiple_testing="NOT_VERIFIABLE")
        constraints.append("No independently recalculated correlation supports this claim.")
        return {"claim_type": claim, "decision": "INSUFFICIENT_EVIDENCE", "evidence_level": "NONE", "checks": checks,
                "reporting_constraints": constraints, "statistics": {}, "source": "VALIDATOR"}
    tests = _tests(context, len(association["pairs"]))
    factor = 1.06 if association["method"] == "SPEARMAN" else 1.0
    normal, wide = float(stats.norm.ppf(0.975)), float(stats.norm.ppf(1 - 0.05 / (2 * tests)))
    rows = []
    for item in association["pairs"]:
        r, n = item["r"], item["n"]
        ci = adjusted = None
        if r is not None and n > 3 and abs(r) < 1:
            z, se = math.atanh(r), math.sqrt(factor / (n - 3))
            ci = [math.tanh(z - normal * se), math.tanh(z + normal * se)]
            adjusted = [math.tanh(z - wide * se), math.tanh(z + wide * se)]
        rows.append({**item, "ci95": ci, "ci_adjusted": adjusted})
    minimum = int(thresholds.get("min_association_observations") or 30)
    short = [r["pair"] for r in rows if (r["n"] or 0) < minimum or r["r"] is None]
    checks["minimum_sample"] = "FAIL" if short and len(short) == len(rows) else "PARTIAL" if short else "PASS"
    checks["uncertainty"] = "PASS" if any(_excludes_zero(r["ci95"]) for r in rows) else "PARTIAL"
    checks["multiple_testing"] = "PASS" if any(_excludes_zero(r["ci_adjusted"]) for r in rows) else "PARTIAL"
    decision, level = _design_decision(claim, checks, ("minimum_sample", "uncertainty", "multiple_testing"))
    if short:
        constraints.append(f"Pairs {short[:5]} have fewer than {minimum} common observations.")
    constraints.append("Report each correlation with its number of common observations and interval.")
    if tests > 1:
        constraints.append(f"{tests} correlations were tested on this hypothesis; use the adjusted intervals.")
    if checks["multiple_testing"] != "PASS":
        constraints.append("No correlation is distinguishable from zero after the multiple-testing adjustment.")
    if claim == "EXPLORATORY":
        constraints.append("Label the finding as exploratory and hypothesis-generating.")
    statistics = {"test": "Fisher z interval", "method": association["method"], "unit": association["unit"],
                  "pairs": rows, "tests_on_hypothesis": tests, "confidence_level": 0.95}
    return {"claim_type": claim, "decision": decision, "evidence_level": level, "checks": checks,
            "reporting_constraints": constraints, "statistics": _clean(statistics), "source": "VALIDATOR"}


def _round(value: Any) -> Any:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if number != number else round(number, 10)


def _keys(frame, entity: str, time: str) -> list[dict[str, Any]]:
    rows = []
    for _, row in frame.head(MAX_EXAMPLES).iterrows():
        item = {"entity": row[entity]}
        if time in row and hasattr(row[time], "date"):
            item["date"] = str(row[time].date())
        rows.append(item)
    return rows


def postflight(job_dir: str, analysis_spec: dict[str, Any], manifest: dict[str, Any],
               request: dict[str, Any]) -> dict[str, Any]:
    spec = analysis_spec["spec"]
    evidence, blocking = Evidence(), []
    frames = load_inputs(job_dir, manifest, spec, evidence, blocking)
    period = resolve_period(analysis_spec, manifest, frames, blocking)
    primary = manifest["logical_datasets"][period["primary_input"]]
    requested = _requested(primary)
    for item in manifest.get("scope_evidence") or []:
        evidence.add(item["check"], item["result"], **{k: v for k, v in item.items() if k not in ("check", "result")})
    expected, _ = _expected_universe(spec, frames[period["primary_input"]], primary["entity_column"],
                                     primary["date_column"], period, requested, evidence)
    _population(spec, manifest, frames, expected, evidence, [])
    _warmup(analysis_spec, manifest, frames, period, expected, requested, evidence)
    refs = reference_frames(spec, manifest, frames, period)
    warmups = {name: need["minimum_warmup_observations"] for name, need in analysis_spec["required_input"].items()}
    scopes = []
    for output in spec["outputs"]:
        path = request["outputs"].get(output["name"])
        scopes.append(check_output(output, os.path.join(job_dir, path) if path else None, spec, manifest, frames,
                                   refs, period, expected, evidence, warmups, request.get("research_context")))
    status, level = aggregate(spec, evidence, scopes, refs)
    assessment = assess(request.get("research_context") or {}, status, level, scopes)
    for scope in scopes:
        scope.pop("event_study", None)  # the assessment carries the validator's statistics
    return {"mode": "postflight", "validation_status": status, "validation_level": level,
            "validation_profile": manifest.get("validation_profile") or "Y_ANALYSIS",
            "reasons": evidence.reasons, "evidence": evidence.items, "period": _period_json(period),
            "expected_entities": len(expected), "outputs": scopes, "evidence_assessment": assessment}


def aggregate(spec: dict[str, Any], evidence: Evidence, scopes: list[dict[str, Any]], refs: dict[str, Any]
              ) -> tuple[str, str]:
    severities = set(evidence.reasons.values())
    checked = [s for s in scopes if s.get("checked") and not s.get("scope_unverifiable")]
    if "FAILED" in severities:
        status = "FAILED"
    elif "INCOMPLETE" in severities:
        status = "INCOMPLETE"
    elif not checked:
        status = "UNVERIFIED"
    else:
        status = "PASS"
    scope_ok = bool(checked) and not ({"ANALYSIS_SCOPE_MISMATCH", "UNIVERSE_MISMATCH", "REQUIRED_OUTPUT_MISSING",
                                        "OUTPUT_GRAIN_VIOLATION", "SELECTION_MISMATCH", "GROUP_COVERAGE_MISMATCH",
                                        "GROUP_KEY_AMBIGUOUS", "RANKING_MISMATCH"} & set(evidence.reasons))
    # Each output check reports which calculations it actually recalculated (pair correlations are recalculated by
    # the pair check even though they have no per-entity reference series).
    verified = {c for s in checked for c in s.get("verified_calculations", [])}
    all_verified = bool(verified) and all(not s.get("unverified_calculations") for s in scopes if s.get("checked"))
    if status == "PASS" and all_verified:
        level = "CALCULATION_VERIFIED"
    elif scope_ok:
        level = "SCOPE_VERIFIED"
    else:
        level = "EXECUTION_ONLY"
    return status, level


# ---------------------------------------------------------------- temporal leakage (prefix re-run)

def leakcheck(job_dir: str, analysis_spec: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    """Compare the outputs of the full run with a re-run on inputs truncated at the cutoff date: every value at or
    before the cutoff of a trailing calculation must be identical."""
    import pandas as pd
    import pyarrow.parquet as pq

    spec = analysis_spec["spec"]
    cutoff = pd.Timestamp(request["cutoff"])
    evidence = Evidence()
    outputs = {o["name"]: o for o in spec["outputs"]}
    summary = []
    for name, columns in request["targets"].items():
        output = outputs[name]
        keys = [output["entity_column"], output["date_column"]]
        frames = []
        for path in (request["outputs"][name], request["prefix_outputs"][name]):
            table = pq.read_table(os.path.join(job_dir, path), columns=keys + columns).to_pandas()
            table[keys[0]] = table[keys[0]].astype(str)
            table[keys[1]] = _dates(table[keys[1]])
            frames.append(table[table[keys[1]] <= cutoff])
        full, prefix = frames
        merged = full.merge(prefix, on=keys, how="outer", suffixes=("", "_prefix"), indicator=True)
        only_full = int((merged["_merge"] == "left_only").sum())
        only_prefix = int((merged["_merge"] == "right_only").sum())
        both = merged[merged["_merge"] == "both"]
        changed = {}
        for column in columns:
            ok = _compare(_numeric(both[column]), _numeric(both[column + "_prefix"]))
            if not ok.all():
                bad = both[~ok]
                changed[column] = {"rows": int((~ok).sum()), "examples": [
                    {"entity": r[keys[0]], "date": str(r[keys[1]].date()), "full_data": _round(r[column]),
                     "data_up_to_cutoff": _round(r[column + "_prefix"])} for _, r in bad.head(MAX_EXAMPLES).iterrows()]}
        summary.append({"output": name, "rows_compared": len(both), "rows_only_with_future_data": only_full,
                        "rows_only_without_future_data": only_prefix, "changed_columns": sorted(changed)})
        if changed or only_full or only_prefix:
            evidence.add(f"temporal.leakage.{name}", "FAIL", "TEMPORAL_LEAKAGE_DETECTED", cutoff=str(cutoff.date()),
                         changed=changed, rows_only_with_future_data=only_full,
                         rows_only_without_future_data=only_prefix,
                         detail="Values dated on or before the cutoff change when data after the cutoff is removed: "
                                "the calculation uses information from after each date.")
        else:
            evidence.add(f"temporal.leakage.{name}", "PASS", cutoff=str(cutoff.date()), rows_compared=len(both),
                         detail="Values up to the cutoff are identical without the later data.")
    return {"mode": "leakcheck", "result": "FAIL" if "TEMPORAL_LEAKAGE_DETECTED" in evidence.reasons else "PASS",
            "outputs": summary, "evidence": evidence.items}


# ---------------------------------------------------------------- entry point

def selftest(job_dir: str) -> dict[str, Any]:
    import errno
    import socket

    status = open("/proc/self/status").read()
    checks = {"uid_non_root": "PASS" if os.getuid() != 0 else "FAIL: running as root",
              "seccomp_filter_active": "PASS" if "Seccomp:\t2" in status else "FAIL: no seccomp filter"}
    try:
        socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        checks["socket_inet_denied"] = "FAIL: allowed"
    except OSError as exc:
        checks["socket_inet_denied"] = "PASS" if exc.errno == errno.EACCES else f"FAIL: errno {exc.errno}"
    import pandas  # noqa: F401 - the validator's libraries load under its limits
    import pyarrow  # noqa: F401
    import reference  # noqa: F401
    return {"mode": "selftest", "checks": checks}


def main(job_dir: str, mode: str) -> int:
    runtime = _load_json(os.path.join(job_dir, "validation", "request.json"))
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import confine

    confine.apply(runtime["limits"], runtime.get("cpus"), runtime.get("require_seccomp", True))
    result_dir = os.path.join(job_dir, "validation", "result")
    try:
        if mode == "selftest":
            result = selftest(job_dir)
        else:
            analysis_spec = _load_json(os.path.join(job_dir, "analysis_spec.json"))
            manifest = _load_json(os.path.join(job_dir, "manifest.json"))
            if mode == "preflight":
                result = preflight(job_dir, analysis_spec, manifest)
            elif mode == "leakcheck":
                result = leakcheck(job_dir, analysis_spec, runtime)
            else:
                result = postflight(job_dir, analysis_spec, manifest, runtime)
    except Exception as exc:  # noqa: BLE001 - reported to the harness as a validator failure
        result = {"mode": mode, "validator_error": f"{type(exc).__name__}: {str(exc)[:400]}"}
    path = os.path.join(result_dir, f"{mode}.json")
    with open(path + ".tmp", "w", encoding="utf-8") as handle:
        json.dump(result, handle, default=str, separators=(",", ":"))
    os.replace(path + ".tmp", path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
