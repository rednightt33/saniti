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
                "CALCULATION_MISMATCH", "SELECTION_MISMATCH")
INCOMPLETE_CODES = ("INSUFFICIENT_WARMUP_HISTORY", "SOURCE_PERIOD_UNAVAILABLE", "UNIVERSE_SOURCE_UNAVAILABLE")
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

    # universe
    expected, unavailable = _expected_universe(spec, frame, entity, time, period, requested, evidence)
    if universe["type"] == "ALL_IN_SOURCE" and requested["entities"] is not None:
        blocking.append({"code": "UNIVERSE_MISMATCH", "classification": "NOT_EXTRACTED",
                         "message": "The spec analyses every ticker, but the bound data was extracted for a subset of "
                                    "tickers. Request the data without a ticker filter."})
    not_extracted = sorted(t for t, why in unavailable.items() if why == "NOT_EXTRACTED")
    if not_extracted:
        blocking.append({"code": "UNIVERSE_MISMATCH", "classification": "NOT_EXTRACTED",
                         "message": f"Tickers {not_extracted[:MAX_LIST]} were not requested from the SQL Governor."})

    # warm-up and look-ahead per expected entity
    warmup = _warmup(analysis_spec, manifest, frames, period, expected, requested, evidence)
    for name, info in warmup.items():
        if info["not_extracted"]:
            blocking.append({"code": "INSUFFICIENT_WARMUP_HISTORY", "classification": "NOT_EXTRACTED", "input": name,
                             "message": f"{info['not_extracted_count']} entities have fewer than "
                                        f"{info['minimum']} observations before the analysis period because the "
                                        f"bound data starts too late. Request data from "
                                        f"{info['recommended_from']} or earlier."})
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
            elif prior < recommended:
                path_dependent.append(ent)
        info = {"minimum": minimum, "recommended": recommended, "source_limited": _sample(source_limited),
                "source_limited_count": len(source_limited), "not_extracted": _sample(not_extracted),
                "not_extracted_count": len(not_extracted), "affected_observations": affected,
                "path_dependent_count": len(path_dependent),
                "recommended_from": need["recommended_request_date_range"]["from"]}
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

def reference_frames(spec: dict[str, Any], manifest: dict[str, Any], frames: dict[str, Any]) -> dict[str, Any]:
    """Per input: entity, date, and one column per supported calculation (NaN where undefined)."""
    import numpy as np
    import reference

    by_dataset: dict[str, Any] = {}
    unverifiable: set[str] = set()
    for calc in spec["calculations"]:
        name = calc["dataset"]
        logical = manifest["logical_datasets"][name]
        entity, time = logical["entity_column"], logical["date_column"]
        if not entity or not time:
            unverifiable.add(calc["id"])
            continue
        frame = frames[name]
        if name not in by_dataset:
            by_dataset[name] = frame[[entity, time]].copy()
        target = by_dataset[name]
        upstream = calc["input_calculation"]
        if calc["method"] in ("CUSTOM", "CORRELATION") or (upstream and upstream in unverifiable):
            unverifiable.add(calc["id"])
            continue
        params = {p["name"]: p["value"] for p in calc["params"]}
        source = target[_calc_column(spec, upstream)] if upstream else frame[calc["columns"][0]]
        other = frame[calc["columns"][1]] if calc["method"] == "ROLLING_CORRELATION" else None
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
                                         if calc["method"] == "ROLLING_CORRELATION" else None)
            lookup = dict(zip(zip(ordered[entity], ordered[time]), computed))
        else:
            lookup = {}
            for ent, part in source.groupby(entity, sort=False):
                computed = reference.compute(calc["method"], alt_params, part[column].to_numpy(dtype=float),
                                             part[calc["columns"][1]].to_numpy(dtype=float)
                                             if calc["method"] == "ROLLING_CORRELATION" else None)
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
                 evidence: Evidence, warmups: dict[str, int]) -> dict[str, Any]:
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
        return _check_pairs(output, table, key_columns, used, spec, manifest, frames, period, evidence, scope)

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
    selectable = not selection or all(p["calculation"] not in refs["unverifiable"] for p in output["selection"])

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

    if selection and selectable:
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


def _check_pairs(output, table, key_columns, used, spec, manifest, frames, period, evidence, scope):
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
    return scope


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
    expected, _ = _expected_universe(spec, frames[period["primary_input"]], primary["entity_column"],
                                     primary["date_column"], period, requested, evidence)
    _warmup(analysis_spec, manifest, frames, period, expected, requested, evidence)
    refs = reference_frames(spec, manifest, frames)
    warmups = {name: need["minimum_warmup_observations"] for name, need in analysis_spec["required_input"].items()}
    scopes = []
    for output in spec["outputs"]:
        path = request["outputs"].get(output["name"])
        scopes.append(check_output(output, os.path.join(job_dir, path) if path else None, spec, manifest, frames,
                                   refs, period, expected, evidence, warmups))
    status, level = aggregate(spec, evidence, scopes, refs)
    return {"mode": "postflight", "validation_status": status, "validation_level": level,
            "reasons": evidence.reasons, "evidence": evidence.items, "period": _period_json(period),
            "expected_entities": len(expected), "outputs": scopes}


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
                                        "OUTPUT_GRAIN_VIOLATION", "SELECTION_MISMATCH"} & set(evidence.reasons))
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
            result = preflight(job_dir, analysis_spec, manifest) if mode == "preflight" else \
                postflight(job_dir, analysis_spec, manifest, runtime)
    except Exception as exc:  # noqa: BLE001 - reported to the harness as a validator failure
        result = {"mode": mode, "validator_error": f"{type(exc).__name__}: {str(exc)[:400]}"}
    path = os.path.join(result_dir, f"{mode}.json")
    with open(path + ".tmp", "w", encoding="utf-8") as handle:
        json.dump(result, handle, default=str, separators=(",", ":"))
    os.replace(path + ".tmp", path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
