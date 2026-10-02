"""Helpers of a persistent analysis session, available to session code as `saniti` (and pre-bound names).

A session works on one governed data bundle: one logical dataset per approved data request, read-only, complete
(every row of every partition), never sampled. The code has full programmatic access to it and writes any logic it
needs; nothing here computes an indicator or checks a formula.

    requests()                      the data requests: ids, logical names, columns, ranges, rows, quality flags
    manifest()                      the bundle: need, relationships (with join semantics) and their warnings
    quality(request)                the Data Quality Manifest of one request
    load(request, columns=None)     the whole dataset as a pandas DataFrame, in delivered order
    load_range(request, range_id, columns=None, include_buffers=False)
                                    the rows of one approved range (with its history/future buffers if asked); also
                                    saniti.range (S21: not pre-bound as `range`, which stays Python's built-in)
    sql(query, params=None)         DuckDB SQL over one view per logical name (read-only)
    relation(request)               a lazy DuckDB relation over one dataset
    join(relationship_id, left=None, right=None, how=None)
                                    the approved relationship as an analytic join with its point-in-time semantics,
                                    on every key pair, with cardinality checks (join_report() describes the last one)
    preaggregate(relationship_id, frame=None, measures=None)
                                    the many side of a relationship aggregated to its key grain with the catalog's
                                    cross-entity rules (required before a join that needs preaggregation)
    resample(frame, request, frequency=None)
                                    the catalog's resample rules (FIRST/LAST/MAX/MIN/SUM) per entity and period
                                    (derived frequency: daily source only, period metadata, period_complete)
    resampled_returns(frame, request, value_column="close")
                                    derived frequency: period close / previous period close - 1, with boundaries
    event_summary(events, baseline, hypothesis_id=..., outcome_column=..., date_column=..., ...)
                                    research findings: the effect size and the event-lookback share of one
                                    condition -> outcome experiment, its effective sample and verdict (released as
                                    research_events_<hypothesis_id> and research_summary_<hypothesis_id>)
    period_return(request, range_id, value_column="close", entity_column=None, date_column=None)
                                    a named calendar-period return per entity with one boundary convention
    research_conditional / research_persistence / research_group_comparison / research_quantiles /
    research_temporal_dependency / research_custom
                                    Multi-Angle Research: one approved angle's input recorded for the backend finding
                                    (only in an approved multi-angle research session)
    insufficient_data(request, range_id=None, value=None, unit=..., requirement_type=..., reason="")
                                    stop: the data cannot support the analysis; revise the DataNeedSpec
    intermediate_path(name)         a private file path for intermediate results
    emit_table / emit_chart / emit_json / emit_text / emit_file
                                    outputs (TABLE, CHART, JSON, TEXT, PARQUET, CSV, PNG, ARTIFACT)

`request` is a data_request_id or its logical name. Every helper read is recorded (what was read, how many rows):
the Coverage Validator later checks that every approved request and range was processed. Reading the input
files directly bypasses that record and is reported as not processed.
"""
from __future__ import annotations

import datetime as _dt
import json as _json
import math as _math
import os as _os
import re as _re
from typing import Any

__all__ = [
    "REQUESTS", "REFERENCE_DATE", "SEED", "requests", "manifest", "quality", "load", "range", "load_range", "sql",
    "relation",
    "join", "join_report", "preaggregate", "resample", "period_return", "insufficient_data", "intermediate_path", "duckdb_connection", "emit_table",
    "emit_chart", "emit_json", "emit_text", "emit_file", "emit_artifact", "add_warning", "SanitiError",
    "InsufficientInputData", "OutputLimitExceeded", "InvalidOutput", "ResampleRuleMissing", "PeriodReturnError",
    "JoinCardinalityError", "AggregationRuleMissing", "MaterializationLimitExceeded",
]
# pre-bound only when the session config lists them (session.json extra_helpers, set by a feature flag)
EXTRA_HELPERS = ("event_summary", "research_conditional", "research_persistence", "research_group_comparison",
                 "research_quantiles", "research_temporal_dependency", "research_custom")

REQUESTS: dict[str, dict[str, Any]] = {}
REFERENCE_DATE: str | None = None
SEED = 0
_BUNDLE: dict[str, Any] = {}
_LIMITS: dict[str, Any] = {}
_DUCKDB: dict[str, Any] = {}
_FRAMES: dict[str, Any] = {}  # G14: session.json "frames" (budget_mb, type_bytes, default_bytes)
_CONNECTION: Any = None
_OUTPUT_DIR = ""
_INTERMEDIATE_DIR = ""
_ACCESS: list[dict[str, Any]] = []
_OUTPUTS: list[dict[str, Any]] = []
_WARNINGS: list[dict[str, str]] = []
_SEQ = [0]
# Multi-Angle Research (session.json research_v2): the approved angles of this bundle group with their contracts;
# angles recorded by successful executions, and by the running one (settled when it ends)
_RESEARCH: dict[str, Any] = {}
_RESEARCH_DONE: set[str] = set()
_RESEARCH_PENDING: set[str] = set()
RESEARCH_RESERVED = ("research_input_", "research_call_")
RESEARCH_WRAPPER_VERSION = 1
NAME = _re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-. ]{0,79}$")
INTERMEDIATE_NAME = _re.compile(r"^[A-Za-z0-9_-]{1,64}$")
MAX_ACCESS = 500
PERIODS = {"1D": "D", "1W": "W-FRI", "1M": "ME", "1Q": "QE", "1Y": "YE"}
AGGREGATIONS = {"FIRST": "first", "LAST": "last", "MAX": "max", "MIN": "min", "SUM": "sum"}


class SanitiError(Exception):
    code = "PYTHON_EXCEPTION"


class InsufficientInputData(SanitiError):
    code = "INSUFFICIENT_INPUT_DATA"

    def __init__(self, data_request_id: str, range_id: str | None, requirement: dict[str, Any], reason: str) -> None:
        super().__init__(reason or f"{data_request_id} cannot support the analysis as approved.")
        self.data_request_id = data_request_id
        self.range_id = range_id
        self.requirement = requirement
        self.reason = reason


class OutputLimitExceeded(SanitiError):
    code = "OUTPUT_LIMIT_EXCEEDED"


class InvalidOutput(SanitiError):
    code = "OUTPUT_INVALID"


class ResampleRuleMissing(SanitiError):
    code = "RESAMPLE_RULE_MISSING"


class JoinCardinalityError(SanitiError):
    """A join would break its relationship's cardinality: duplicate keys on a side declared "one", a many-to-many
    result, or a raw join where the catalog requires the many side to be aggregated first."""
    code = "JOIN_CARDINALITY"


class AggregationRuleMissing(SanitiError):
    code = "AGGREGATION_RULE_MISSING"


class MaterializationLimitExceeded(SanitiError):
    """G14: a result too large for one pandas frame in this session's memory. Nothing was loaded; the session, its
    data and its variables stay. Filter or aggregate in DuckDB (sql(), relation()) and materialize the smaller
    result."""
    code = "MATERIALIZATION_LIMIT_EXCEEDED"


class PeriodReturnError(SanitiError):
    code = "PERIOD_RETURN_INVALID_ARGUMENTS"


# ---------------------------------------------------------------- configuration (harness only)

def _configure(session: dict[str, Any], session_dir: str) -> None:
    global REFERENCE_DATE, SEED, _OUTPUT_DIR, _INTERMEDIATE_DIR
    REQUESTS.clear()
    REQUESTS.update(session["requests"])
    _BUNDLE.clear()
    _BUNDLE.update(session["bundle"])
    _LIMITS.clear()
    _LIMITS.update(session["outputs"])
    REFERENCE_DATE = session["reference_date"]
    SEED = int(session["seed"])
    _OUTPUT_DIR = _os.path.join(session_dir, "output")
    _INTERMEDIATE_DIR = _os.path.join(session_dir, "intermediate")
    _DUCKDB.clear()
    _DUCKDB.update(session["duckdb"])
    _FRAMES.clear()
    _FRAMES.update(session.get("frames") or {})
    _RESEARCH.clear()
    _RESEARCH.update(session.get("research_v2") or {})
    _RESEARCH_DONE.clear()
    _RESEARCH_PENDING.clear()


def _quote(text: str) -> str:
    return "'" + str(text).replace("'", "''") + "'"


def _ident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _view_sql(request: dict[str, Any]) -> str:
    listed = ", ".join(_quote(path) for path in request["files"])
    order = ", ".join(f"{_ident(o['column'])} {o['direction']}" for o in request.get("order_by") or [])
    return f"SELECT * FROM read_parquet([{listed}])" + (f" ORDER BY {order}" if order else "")


def _locked_connection():
    raw = _DUCKDB["raw_connect"]
    con = raw(":memory:", False, {"threads": int(_DUCKDB["threads"]),
                                  "memory_limit": f"{int(_DUCKDB['memory_limit_mb'])}MB",
                                  "autoinstall_known_extensions": False, "autoload_known_extensions": False})
    con.execute(f"SET allowed_directories = [{', '.join(_quote(d) for d in _DUCKDB['allowed_directories'])}]")
    con.execute("SET extension_directory = '/nonexistent/duckdb-extensions'")
    con.execute("SET allow_community_extensions = false")
    con.execute(f"SET temp_directory = {_quote(_DUCKDB['temp_directory'])}")
    con.execute(f"SET max_temp_directory_size = '{int(_DUCKDB['max_temp_directory_mb'])}MB'")
    con.execute("SET enable_external_access = false")
    con.execute("SET lock_configuration = true")
    for request in REQUESTS.values():
        con.execute(f"CREATE VIEW {_ident(request['logical_name'])} AS {_view_sql(request)}")
    return con


def _lock_duckdb() -> None:
    global _CONNECTION
    import duckdb

    _DUCKDB["raw_connect"] = duckdb.connect
    _os.makedirs(_DUCKDB["temp_directory"], exist_ok=True)
    _CONNECTION = _locked_connection()
    duckdb.set_default_connection(_CONNECTION)

    def connect(database: str = ":memory:", read_only: bool = False, config: dict | None = None, **_: Any):
        if database not in (":memory:", "", None):
            raise PermissionError(13, "Only in-memory DuckDB connections are available in a session.")
        return _locked_connection()

    duckdb.connect = connect


def _begin() -> None:
    _ACCESS.clear()
    _OUTPUTS.clear()


def _end() -> dict[str, Any]:
    return {"access": list(_ACCESS), "outputs": list(_OUTPUTS), "warnings": list(_WARNINGS[-20:])}


def _research_settle(ok: bool) -> None:
    """Angles recorded by the execution that just ended count as recorded only when it succeeded (the harness reads
    outputs of successful executions only), so a failed execution can be fixed and run again."""
    if ok:
        _RESEARCH_DONE.update(_RESEARCH_PENDING)
    _RESEARCH_PENDING.clear()


def _log(entry: dict[str, Any]) -> None:
    if len(_ACCESS) < MAX_ACCESS:
        _ACCESS.append(entry)


# ---------------------------------------------------------------- reading

def _request(name: str) -> dict[str, Any]:
    if name in REQUESTS:
        return REQUESTS[name]
    for request in REQUESTS.values():
        if request["logical_name"] == name:
            return request
    raise SanitiError(f"{name!r} is not a data request of this bundle. Requests: "
                      f"{[(r['data_request_id'], r['logical_name']) for r in REQUESTS.values()]}")


def _columns(request: dict[str, Any], columns: list[str] | None) -> list[str]:
    chosen = list(columns) if columns else list(request["columns"])
    unknown = [c for c in chosen if c not in request["columns"]]
    if unknown:
        raise SanitiError(f"Columns {unknown} are not in {request['logical_name']}. Columns: {request['columns']}")
    return chosen


def duckdb_connection():
    """The locked DuckDB connection with one read-only view per logical name."""
    return _CONNECTION


def requests() -> list[dict[str, Any]]:
    """Every data request of the bundle: ids, logical name, table, columns, keys, ranges, rows, quality flags."""
    return [{k: r.get(k) for k in ("data_request_id", "logical_name", "source_table", "columns", "key_columns",
                                   "entity_column", "time_column", "source_frequency", "analysis_frequency",
                                   "resample", "resample_rules", "aggregation_rules", "rows")}
            | {"ranges": [{k: w[k] for k in ("range_id", "start", "end", "extract_from", "extract_to")}
                          for w in r.get("ranges") or []],
               "quality_flags": (r.get("quality") or {}).get("quality_flags") or []}
            | _frame_estimate(r)
            for r in REQUESTS.values()]


def _frame_estimate(request: dict[str, Any]) -> dict[str, Any]:
    """G14: the request's estimated pandas size and whether load() may materialize it whole (DIRECT) or it must be
    filtered or aggregated in DuckDB first (AGGREGATE_FIRST)."""
    budget = _frame_budget()
    if not budget or _CONNECTION is None:
        return {}
    per_row = sum(_type_bytes(t) for t in _CONNECTION.table(request["logical_name"]).types) or 72
    size = int(request.get("rows") or 0) * per_row
    return {"frame_mb": round(size / (1 << 20), 1), "frame_budget_mb": int(_FRAMES.get("budget_mb") or 0),
            "materialize": "DIRECT" if size <= budget else "AGGREGATE_FIRST"}


def manifest() -> dict[str, Any]:
    """The bundle: need, reference date, relationships with their join semantics, relationship warnings."""
    return _json.loads(_json.dumps(_BUNDLE, default=str))


def quality(request: str) -> dict[str, Any]:
    """The Data Quality Manifest of one data request (rows, ranges, gaps, buffers, duplicates, nulls, flags)."""
    return _json.loads(_json.dumps(_request(request).get("quality") or {}, default=str))


def _frame_budget() -> int:
    """G14: the largest pandas frame in bytes (session.json "frames"); 0 turns the check off."""
    return int(_FRAMES.get("budget_bytes") or 0) or int(_FRAMES.get("budget_mb") or 0) << 20


def _type_bytes(type_name: Any) -> int:
    name = str(type_name).lower()
    return next((int(size) for key, size in _FRAMES.get("type_bytes") or [] if key in name),
                int(_FRAMES.get("default_bytes") or 72))


def _frame_limit(relation_, what: str, request: dict[str, Any] | None = None) -> None:
    """G14: refuse, before anything is loaded, a result whose estimated pandas size exceeds the session's frame
    budget. The count stops one row past the limit, so a huge result is never counted in full."""
    budget = _frame_budget()
    if not budget:
        return
    budget_mb = int(_FRAMES.get("budget_mb") or 0)
    per_row = sum(_type_bytes(t) for t in relation_.types) or 72
    cap = max(1, budget // per_row)
    rows = int(relation_.limit(cap + 1).aggregate("count(*)").fetchone()[0])
    if rows <= cap:
        return
    keys = [c for c in ((request or {}).get("entity_column"), (request or {}).get("time_column")) if c]
    hint = (f"for example sql(\"SELECT {', '.join(keys)}, sum(<measure>) FROM {request['logical_name']} GROUP BY "
            f"{', '.join(keys)}\")" if request and keys else "for example sql(\"SELECT <keys>, sum(<measure>) FROM "
                                                                  "<view> WHERE <filter> GROUP BY <keys>\")")
    _WARNINGS.append({"code": "MATERIALIZATION_LIMIT_EXCEEDED", "message": what})
    raise MaterializationLimitExceeded(
        f"{what} holds more than {cap} rows (about {per_row} bytes each in pandas, over the {budget_mb} MB frame "
        f"budget of this session). Nothing was loaded and the session, its data and variables stay. Filter or "
        f"aggregate in DuckDB first, {hint}, or select fewer columns, then materialize the smaller result. Do not "
        "prepare the data again.")


def _frame(query: str, params: list | None = None, what: str = "This query result",
           request: dict[str, Any] | None = None):
    con = duckdb_connection()
    relation_ = con.sql(query, params=params) if params else con.sql(query)
    _frame_limit(relation_, what, request)
    return relation_.df(date_as_object=True)


def load(request: str, columns: list[str] | None = None):
    """The whole dataset (every row of every partition and range, with the buffers) in delivered order."""
    r = _request(request)
    chosen = _columns(r, columns)
    frame = _frame(f"SELECT {', '.join(_ident(c) for c in chosen)} FROM {_ident(r['logical_name'])}",
                   what=f"load({r['data_request_id']!r})", request=r)
    _log({"call": "load", "data_request_id": r["data_request_id"], "columns": chosen[:30], "rows": len(frame),
          "full": True})
    return frame


def range(request: str, range_id: str, columns: list[str] | None = None, include_buffers: bool = False):  # noqa: A001
    """The rows of one approved range; include_buffers=True widens it to the extracted window (warm-up history
    before it, future observations after it)."""
    r = _request(request)
    window = next((w for w in r.get("ranges") or [] if w["range_id"] == range_id), None)
    if window is None:
        raise SanitiError(f"{range_id!r} is not a range of {r['logical_name']}. Ranges: "
                          f"{[w['range_id'] for w in r.get('ranges') or []]}")
    chosen = _columns(r, columns)
    low, high = (window["extract_from"], window["extract_to"]) if include_buffers else (window["start"],
                                                                                         window["end"])
    frame = _frame(f"SELECT {', '.join(_ident(c) for c in chosen)} FROM {_ident(r['logical_name'])} "
                   f"WHERE {_ident(r['time_column'])} BETWEEN CAST(? AS DATE) AND CAST(? AS DATE)", [low, high],
                   what=f"range({r['data_request_id']!r}, {range_id!r})", request=r)
    _log({"call": "range", "data_request_id": r["data_request_id"], "range_id": range_id,
          "include_buffers": bool(include_buffers), "columns": chosen[:30], "rows": len(frame)})
    return frame


def load_range(request: str, range_id: str, columns: list[str] | None = None, include_buffers: bool = False):
    """The rows of one approved range (saniti.range under a name that does not shadow Python's built-in range)."""
    return range(request, range_id, columns, include_buffers)


def sql(query: str, params: list | None = None):
    """DuckDB SQL over the read-only views (one per logical name); returns a pandas DataFrame."""
    frame = _frame(query, params)
    lowered = query.lower()
    for r in REQUESTS.values():
        if _re.search(r"(?<![a-z0-9_])" + _re.escape(r["logical_name"].lower()) + r"(?![a-z0-9_])", lowered):
            _log({"call": "sql", "data_request_id": r["data_request_id"], "rows": len(frame), "full": True})
    return frame


def relation(request: str):
    """A lazy DuckDB relation over one dataset: filter, project or aggregate it in DuckDB, then materialize the
    smaller result with .df(). (G14: its own .df() is not size-checked; the session's memory limit still applies.)"""
    r = _request(request)
    _log({"call": "relation", "data_request_id": r["data_request_id"], "full": True})
    return duckdb_connection().table(r["logical_name"])


# ---------------------------------------------------------------- relationships and resampling

def _relationship(relationship_id: int) -> dict[str, Any]:
    for rel in _BUNDLE.get("relationships") or []:
        if rel["relationship_id"] == relationship_id:
            return rel
    raise SanitiError(f"Relationship {relationship_id} is not part of this bundle. Relationships: "
                      f"{[r['relationship_id'] for r in _BUNDLE.get('relationships') or []]}")


def _keys(rel: dict[str, Any]) -> tuple[list[str], list[str]]:
    """The entity key columns of a relationship (one pair, or a composite key), in the spec's orientation."""
    if isinstance(rel.get("left_columns"), list):
        return list(rel["left_columns"]), list(rel.get("right_columns") or [])
    return [rel["left_column"]], [rel["right_column"]]


_JOIN_REPORT: dict[str, Any] = {}


def join_report() -> dict[str, Any]:
    """What the last saniti.join did: rows on each side and out, null keys, unmatched rows, the checked grain."""
    return dict(_JOIN_REPORT)


def _duplicates(frame, columns: list[str]) -> tuple[int, list[Any]]:
    keyed = frame.dropna(subset=columns)
    dup = keyed[keyed.duplicated(subset=columns, keep=False)]
    return int(len(dup)), dup[columns].drop_duplicates().head(5).to_dict("records")


def join(relationship_id: int, left=None, right=None, how: str | None = None):
    """Join two datasets on an approved relationship with its join semantics, per observation date:
    CURRENT_STATE on the key, EXACT_DATE on key and date, AS_OF the latest right row at or before each left date,
    EFFECTIVE_DATED the right row valid on each left date (effective_from <= date < effective_to, open end = NULL).
    Every entity key pair of the relationship is used (a composite key never joins on part of itself).
    left/right default to the whole datasets; how defaults to the approved join type (INNER or LEFT).

    Checks (IP1 Stage B): a side the relationship declares "one" must be unique on its key (and date), otherwise
    JoinCardinalityError; rows with a null key never match; a LEFT join keeps every left row and marks it in
    _saniti_match (matched / unmatched); a result larger than the declared grain allows is refused. A relationship that
    requires preaggregation joins only a many side produced by saniti.preaggregate. join_report() has the counts."""
    import pandas as pd

    rel = _relationship(relationship_id)
    left_request, right_request = _request(rel["left_request_id"]), _request(rel["right_request_id"])
    left = load(left_request["data_request_id"]) if left is None else left
    right = load(right_request["data_request_id"]) if right is None else right
    kind = (how or rel["join_type"]).lower()
    if kind not in ("inner", "left"):
        raise SanitiError("how must be 'inner' or 'left'.")
    lc, rc = _keys(rel)
    semantics = rel["join_semantics"]
    rtype = rel.get("relationship_type")
    suffixes = ("", f"_{right_request['logical_name']}")
    lt = rel.get("left_time_column") or left_request.get("time_column")
    rt = rel.get("right_time_column")
    left_grain = lc + ([lt] if semantics in ("EXACT_DATE", "AS_OF") and lt else [])
    right_grain = rc + ([rt] if semantics in ("EXACT_DATE", "AS_OF") and rt else []) + (
        [rel["effective_from_column"]] if semantics == "EFFECTIVE_DATED" else [])
    if rel.get("requires_preaggregation"):
        many = left if rtype == "MANY_TO_ONE" else right
        if many.attrs.get("saniti_preaggregated") != relationship_id:
            raise JoinCardinalityError(
                f"Relationship {relationship_id} requires the many side to be aggregated to the key grain first: "
                f"call saniti.preaggregate({relationship_id}, frame, measures) and join its result.")
    one_sides = {"ONE_TO_MANY": ["left"], "MANY_TO_ONE": ["right"], "ONE_TO_ONE": ["left", "right"]}.get(rtype, [])
    if semantics == "EFFECTIVE_DATED":
        # a history row whose validity is empty (effective_to <= effective_from) applies to no date: dropped before
        # the checks, as the Governor's restriction never matches it; the rest must not overlap per key (IP1 D4)
        start, end = rel["effective_from_column"], rel["effective_to_column"]
        right = right[right[end].isna() | (pd.to_datetime(right[end]) > pd.to_datetime(right[start]))]
        ordered = right.dropna(subset=rc + [start]).sort_values(rc + [start], kind="mergesort")
        previous_end = pd.to_datetime(ordered.groupby(rc, sort=False)[end].shift(1))
        previous_open = ordered.groupby(rc, sort=False)[end].shift(1).isna() & \
            ordered.groupby(rc, sort=False)[start].shift(1).notna()
        overlap = previous_open | (previous_end > pd.to_datetime(ordered[start]))
        if overlap.any():
            examples = ordered[overlap.values][rc + [start]].head(5).to_dict("records")
            raise JoinCardinalityError(
                f"Relationship {relationship_id} (EFFECTIVE_DATED) needs non-overlapping validity per key; "
                f"{int(overlap.sum())} versions overlap an earlier one, e.g. {examples}.")
    if semantics in ("AS_OF", "EFFECTIVE_DATED"):
        one_sides = [s for s in one_sides if s == "left"] + ["right"]  # one history row per key and time
    for side in one_sides:
        frame, grain = (left, left_grain) if side == "left" else (right, right_grain)
        count, examples = _duplicates(frame, grain)
        if count:
            raise JoinCardinalityError(
                f"Relationship {relationship_id} ({rtype}) needs the {side} side unique on {grain}; {count} rows "
                f"repeat a key, e.g. {examples}. Aggregate or deduplicate that side first.")
    null_left = int(left[lc].isna().any(axis=1).sum())
    null_right = int(right[rc].isna().any(axis=1).sum())
    if semantics == "CURRENT_STATE":
        merged = left.merge(right, left_on=lc, right_on=rc, how="left", suffixes=suffixes, indicator=True)
    elif semantics == "EXACT_DATE":
        merged = left.merge(right, left_on=lc + [lt], right_on=rc + [rt], how="left", suffixes=suffixes,
                            indicator=True)
    elif semantics == "AS_OF":
        l_sorted = left.assign(_t=pd.to_datetime(left[lt])).sort_values("_t", kind="mergesort")
        r_sorted = right.assign(_t=pd.to_datetime(right[rt]), _m=1).sort_values("_t", kind="mergesort")
        merged = pd.merge_asof(l_sorted, r_sorted, on="_t", left_by=lc, right_by=rc, direction="backward",
                               suffixes=suffixes)
        merged["_merge"] = merged.pop("_m").map({1: "both"}).fillna("left_only")
        merged = merged.drop(columns="_t")
    else:
        start, end = rel["effective_from_column"], rel["effective_to_column"]
        base = left.reset_index(drop=True).reset_index(names="_row")
        candidates = base.merge(right, left_on=lc, right_on=rc, how="inner", suffixes=suffixes)
        t = pd.to_datetime(candidates[lt])
        valid = (pd.to_datetime(candidates[start]) <= t) & (candidates[end].isna()
                                                             | (t < pd.to_datetime(candidates[end])))
        matched = candidates[valid].assign(_merge="both")
        missing = base[~base["_row"].isin(matched["_row"])].assign(_merge="left_only")
        merged = pd.concat([matched, missing], ignore_index=True).sort_values("_row", kind="mergesort")
        merged = merged.drop(columns="_row")
    matched_mask = merged["_merge"].astype(str) == "both"
    left_unmatched = int((~matched_mask).sum())
    merged = merged.drop(columns="_merge")
    if kind == "inner":
        out = merged[matched_mask.values].reset_index(drop=True)
    else:
        out = merged.assign(_saniti_match=["matched" if m else "unmatched" for m in matched_mask]).reset_index(
            drop=True)
    limit = len(right) if rtype == "ONE_TO_MANY" else len(left)
    if rtype in ("ONE_TO_MANY", "MANY_TO_ONE", "ONE_TO_ONE") and kind == "inner" and len(out) > max(limit, 0) \
            and semantics in ("CURRENT_STATE", "EXACT_DATE"):
        raise JoinCardinalityError(f"Relationship {relationship_id} produced {len(out)} rows, more than its "
                                   f"{rtype} grain allows ({limit}): an unexpected many-to-many match.")
    if len(out) > len(left) and rtype in ("MANY_TO_ONE", "ONE_TO_ONE"):
        raise JoinCardinalityError(f"Relationship {relationship_id} ({rtype}) multiplied the left rows "
                                   f"({len(left)} -> {len(out)}).")
    _JOIN_REPORT.clear()
    _JOIN_REPORT.update({"relationship_id": relationship_id, "join_semantics": semantics, "relationship_type": rtype,
                         "how": kind, "keys": list(zip(lc, rc)), "rows_left": int(len(left)),
                         "rows_right": int(len(right)), "rows_out": int(len(out)),
                         "left_unmatched": left_unmatched, "left_null_keys": null_left,
                         "right_null_keys": null_right, "grain_checked": one_sides})
    _log({"call": "join", "data_request_id": left_request["data_request_id"],
          "right_request_id": right_request["data_request_id"],
          **{k: v for k, v in _JOIN_REPORT.items() if k != "keys"}})
    return out


def preaggregate(relationship_id: int, frame=None, measures=None):
    """The many side of a relationship aggregated to the relationship's key grain (its entity keys and date), with
    the catalog's cross-entity rule per column (AI_column_catalog.cross_entity_aggregation, IP1 Stage C).

    measures: a list of columns, or {column: rule}; every column needs a catalog rule and a given rule must equal it.
    Only additive measures have one (SUM): ratios, percentiles, z-scores, day counts and values repeated from a
    coarser grain have none and are refused (AggregationRuleMissing). The result has one row per key and date, a
    source_rows count, and is marked so saniti.join accepts it for a relationship that requires preaggregation."""
    rel = _relationship(relationship_id)
    rtype = rel.get("relationship_type")
    if rtype not in ("MANY_TO_ONE", "ONE_TO_MANY"):
        raise SanitiError(f"Relationship {relationship_id} ({rtype}) has no many side to aggregate.")
    left_many = rtype == "MANY_TO_ONE"
    request = _request(rel["left_request_id"] if left_many else rel["right_request_id"])
    frame = load(request["data_request_id"]) if frame is None else frame
    lc, rc = _keys(rel)
    keys = lc if left_many else rc
    time = (rel.get("left_time_column") if left_many else rel.get("right_time_column")) \
        if rel["join_semantics"] in ("EXACT_DATE", "AS_OF") else None
    grain = keys + ([time] if time else [])
    rules = request.get("aggregation_rules") or {}
    wanted = dict.fromkeys(measures) if isinstance(measures, (list, tuple)) else dict(measures or {})
    if not wanted:
        raise SanitiError("measures names the columns to aggregate, e.g. ['net_value_1d'].")
    plan = {}
    for column, given in wanted.items():
        if column in grain:
            raise SanitiError(f"{column} is a key of the target grain {grain}, not a measure.")
        rule = rules.get(column)
        if rule is None:
            raise AggregationRuleMissing(
                f"{column} has no cross-entity aggregation rule in the catalog, so it cannot be aggregated across "
                f"{request['logical_name']} rows (ratios, percentiles, z-scores, day counts and repeated values are "
                f"not additive). Columns with a rule: {sorted(rules)}")
        if given is not None and str(given).upper() != rule:
            raise AggregationRuleMissing(f"{column} aggregates with {rule} in the catalog, not {given}.")
        plan[column] = AGGREGATIONS[rule]
    missing = [c for c in grain + list(plan) if c not in frame.columns]
    if missing:
        raise SanitiError(f"The frame lacks {missing}.")
    grouped = frame.groupby(grain, dropna=False, sort=True)
    out = grouped.agg(plan)
    out["source_rows"] = grouped.size()
    out = out.reset_index()
    out.attrs["saniti_preaggregated"] = relationship_id
    _log({"call": "preaggregate", "relationship_id": relationship_id, "data_request_id": request["data_request_id"],
          "rows_in": int(len(frame)), "rows_out": int(len(out)), "grain": grain, "measures": plan})
    return out


def resample(frame, request: str, frequency: str | None = None):
    """Aggregate a daily (or finer) frame to a coarser frequency per entity with the catalog's resample rules.
    Periods: 1W weeks ending Friday, 1M calendar months, 1Q quarters, 1Y years, labelled by their last date.
    A request approved with a resample_semantics_version (derived frequency, IP2) uses the hardened semantics of
    _resample_v1: daily source only, full-grain groups, duplicate keys refused, period metadata and completeness.

    Both forms return one row per entity (and per grain column such as a market board) and period, with the period
    columns period_start, period_end, actual_first_date, actual_last_date, observations and period_complete; the time
    column holds the period's label (its last date). Grain columns group the periods; every other column needs a
    catalog resample rule (requests() shows them). Example: weekly = saniti.resample(saniti.load('prices'), 'prices',
    '1W'), then weekly[weekly['period_complete']]."""
    import pandas as pd

    r = _request(request)
    target = frequency or r.get("analysis_frequency")
    if r.get("resample_semantics_version") is not None:
        return _resample_v1(frame, r, target)
    if target not in PERIODS:
        raise SanitiError(f"frequency must be one of {sorted(PERIODS)}.")
    entity, time = r.get("entity_column"), r.get("time_column")
    # P13 (2026-10-01): the table's grain columns (a board, an investor type) group the periods like the entity; they
    # are not values to aggregate (e02 lost a turn to ResampleRuleMissing for market_board)
    keys = [c for c in dict.fromkeys([entity, *(r.get("key_columns") or [])]) if c and c != time and c in frame.columns]
    rules = r.get("resample_rules") or {}
    values = [c for c in frame.columns if c not in keys and c != time]
    missing = [c for c in values if not rules.get(c)]
    if missing:
        raise ResampleRuleMissing(f"The catalog has no resample rule for {missing}: aggregate them yourself or drop "
                                  f"them. Rules: {rules}")
    dates = pd.to_datetime(frame[time])
    work = frame.assign(**{time: dates, "_saniti_date": dates}).set_index(time).groupby(keys)
    # one aggregation per column (S09: a dict passed to agg on a grouped resampler crossed every rule with every
    # column under pandas 3)
    out = pd.DataFrame({c: work[c].resample(PERIODS[target]).agg(AGGREGATIONS[rules[c]]) for c in values})
    first = work["_saniti_date"].resample(PERIODS[target]).min()
    last = work["_saniti_date"].resample(PERIODS[target]).max()
    out["observations"] = work["_saniti_date"].resample(PERIODS[target]).size()
    out["actual_first_date"], out["actual_last_date"] = first, last
    out = out[out["observations"] > 0].reset_index()
    # P13: the same period columns as the derived-frequency semantics (e02 expected period_end and got a KeyError)
    labels = out[time].dt.normalize()
    out["period_end"] = labels
    out["period_start"] = (labels.dt.to_period(DERIVED_PERIODS[target]).dt.start_time.dt.normalize()
                           if target in DERIVED_PERIODS else labels)
    windows = [w for w in r.get("ranges") or [] if w.get("extract_from") and w.get("extract_to")]
    if windows and REFERENCE_DATE and target in DERIVED_PERIODS:
        data_last = pd.to_datetime(frame[time]).max().normalize()
        out["period_complete"] = ((out["period_start"] >= pd.Timestamp(min(w["extract_from"] for w in windows)))
                                  & (out["period_end"] <= pd.Timestamp(max(w["extract_to"] for w in windows)))
                                  & (out["period_end"] <= pd.Timestamp(REFERENCE_DATE))
                                  & (out["period_end"] <= data_last)).astype(bool)
    else:
        out["period_complete"] = False
    for column in ("period_start", "period_end", "actual_first_date", "actual_last_date", time):
        out[column] = pd.to_datetime(out[column]).dt.date
    return out


# ---------------------------------------------------------------- derived weekly/monthly (IP2, semantics version 1)

RESAMPLE_SEMANTICS_VERSION = 1
DERIVED_PERIODS = {"1W": "W-FRI", "1M": "M", "1Q": "Q-DEC", "1Y": "Y-DEC"}
PERIOD_COLUMNS = ["period_start", "period_end", "actual_first_date", "actual_last_date", "observations",
                  "period_complete"]
NULL_POLICY = ("FIRST/LAST take the first/last non-null value in date order; MAX/MIN ignore nulls; SUM adds the "
               "non-null values and is null when every value of the period is null; nothing is filled")
PERIOD_POLICY = {"1W": "calendar week Saturday to Friday, labelled by its Friday",
                 "1M": "calendar month, labelled by its last calendar day",
                 "1Q": "calendar quarter, labelled by its last calendar day",
                 "1Y": "calendar year, labelled by 31 December"}
COMPLETENESS_RULE = ("period_complete is true only when the whole calendar period lies inside the approved extraction "
                     "window, ends on or before the reference date, and the data (any entity) reaches its last "
                     "calendar day; otherwise false (an open or partly covered period, or completeness that cannot "
                     "be established)")


class ResampleError(SanitiError):
    """A derived-frequency precondition failed: the source is not daily, the frame was already resampled, or an
    entity has duplicate rows for one date."""
    code = "RESAMPLE_INVALID"

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _jakarta_dates(series):
    """Trading dates as Asia/Jakarta calendar dates (datetime64[ns], midnight). A timezone-aware timestamp is
    converted to Asia/Jakarta first; a naive timestamp or a date is already a trading date."""
    import pandas as pd

    values = pd.to_datetime(series)
    if getattr(values.dt, "tz", None) is not None:
        values = values.dt.tz_convert("Asia/Jakarta").dt.tz_localize(None)
    return values.dt.normalize()


def _rules_sha256(rules: dict[str, str]) -> str:
    import hashlib

    return hashlib.sha256(_json.dumps(dict(sorted(rules.items())), separators=(",", ":")).encode()).hexdigest()


def _resample_v1(frame, r: dict[str, Any], target: str | None):
    import pandas as pd

    source = r.get("source_frequency")
    if source != "1D":
        raise ResampleError("RESAMPLE_SOURCE_NOT_DAILY", f"{r['logical_name']} has source_frequency {source}; weekly "
                            "and monthly data are derived only from daily rows.")
    if target not in DERIVED_PERIODS:
        raise ResampleError("RESAMPLE_TARGET_INVALID", f"frequency must be one of {sorted(DERIVED_PERIODS)}.")
    if set(PERIOD_COLUMNS) & set(frame.columns):
        raise ResampleError("RESAMPLE_ALREADY_RESAMPLED", "This frame was already resampled. Derive every frequency "
                            "from the daily rows (saniti.load), never monthly from weekly.")
    entity, time = r.get("entity_column"), r.get("time_column")
    keys = [c for c in dict.fromkeys([entity, *(r.get("key_columns") or [])]) if c and c != time]
    absent = [c for c in [*keys, time] if c not in frame.columns]
    if absent:
        raise ResampleError("RESAMPLE_KEY_MISSING", f"The frame lacks the key columns {absent}; keep the table's "
                            f"grain {keys + [time]} so no entity or broker is mixed with another.")
    rules = r.get("resample_rules") or {}
    values = [c for c in frame.columns if c not in keys and c != time]
    missing = [c for c in values if not rules.get(c)]
    if missing:
        raise ResampleRuleMissing(f"The catalog has no resample rule for {missing}; they cannot be aggregated to a "
                                  f"period. Drop them or ask for daily analysis. Rules: {rules}")
    work = frame[[*keys, time, *values]].copy()
    work["_saniti_date"] = _jakarta_dates(work[time])
    if work["_saniti_date"].isna().any():
        raise ResampleError("RESAMPLE_NULL_DATE", f"{time} has null values.")
    duplicated = work.duplicated([*keys, "_saniti_date"], keep=False)
    if duplicated.any():
        sample = work.loc[duplicated, [*keys, "_saniti_date"]].head(3).astype(str).to_dict("records")
        raise ResampleError("DUPLICATE_ENTITY_DATE", f"{int(duplicated.sum())} rows share an entity and trading date "
                            f"(for example {sample}); deduplicate before resampling.")
    work = work.sort_values([*keys, "_saniti_date"], kind="mergesort")
    periods = work["_saniti_date"].dt.to_period(DERIVED_PERIODS[target])
    work["_saniti_start"] = periods.dt.start_time.dt.normalize()
    work["_saniti_end"] = periods.dt.end_time.dt.normalize()
    grouped = work.groupby([*keys, "_saniti_end"], sort=True, dropna=False)
    out = pd.DataFrame({
        "period_start": grouped["_saniti_start"].first(),
        "actual_first_date": grouped["_saniti_date"].min(),
        "actual_last_date": grouped["_saniti_date"].max(),
        "observations": grouped["_saniti_date"].size().astype("int64")})
    for column in values:
        rule = rules[column]
        series = grouped[column]
        out[column] = (series.sum(min_count=1) if rule == "SUM" else series.first() if rule == "FIRST"
                       else series.last() if rule == "LAST" else series.max() if rule == "MAX" else series.min())
    out = out.reset_index().rename(columns={"_saniti_end": "period_end"})
    windows = [w for w in r.get("ranges") or [] if w.get("extract_from") and w.get("extract_to")]
    if windows and REFERENCE_DATE:
        window_from = pd.Timestamp(min(w["extract_from"] for w in windows))
        window_to = pd.Timestamp(max(w["extract_to"] for w in windows))
        data_last = work["_saniti_date"].max()
        complete = ((out["period_start"] >= window_from) & (out["period_end"] <= window_to)
                    & (out["period_end"] <= pd.Timestamp(REFERENCE_DATE)) & (out["period_end"] <= data_last))
    else:
        complete = pd.Series(False, index=out.index)
    out["period_complete"] = complete.astype(bool)
    out[time] = out["period_end"]
    for column in ("period_start", "period_end", "actual_first_date", "actual_last_date", time):
        out[column] = out[column].dt.date
    out = out[[*keys, time, *values, *PERIOD_COLUMNS]].sort_values([*keys, time], kind="mergesort")
    out = out.reset_index(drop=True)
    incomplete = sorted({str(d) for d in out.loc[~out["period_complete"], "period_end"]})
    _log({"call": "resample", "data_request_id": r["data_request_id"], "source_frequency": source,
          "target_frequency": target, "semantics_version": RESAMPLE_SEMANTICS_VERSION,
          "input_rows": int(len(frame)), "rows": int(len(out)), "periods": int(out["period_end"].nunique()),
          "entities": int(out[entity].nunique()) if entity in out.columns else None,
          "rules_sha256": _rules_sha256({c: rules[c] for c in values}), "rules": {c: rules[c] for c in values},
          "incomplete_periods": len(incomplete), "incomplete_period_ends": incomplete[:10],
          "period_policy": PERIOD_POLICY[target]})
    return out


def resampled_returns(frame, request: str, value_column: str = "close"):
    """Period returns from a frame resample() returned: value (the period's LAST close) divided by the previous
    period's value of the same entity, minus one. Daily returns are never summed. One row per entity and period
    with its boundary: base_period_end, base_value, value, return_decimal, return_pct, periods_between (0 when the
    previous period is adjacent), period_complete and base_period_complete; the first period of an entity has no
    base (calculation_status NO_PRIOR_PERIOD)."""
    import numpy as np
    import pandas as pd

    r = _request(request)
    if r.get("resample_semantics_version") is None or not set(PERIOD_COLUMNS) <= set(frame.columns):
        raise ResampleError("RESAMPLED_FRAME_REQUIRED", "Pass the frame saniti.resample() returned for this request.")
    if (r.get("resample_rules") or {}).get(value_column) != "LAST":
        raise ResampleError("RETURN_NEEDS_LAST_VALUE", f"{value_column} must be resampled with LAST (a period close) "
                            "to compute period returns.")
    time = r.get("time_column")
    keys = [c for c in dict.fromkeys([r.get("entity_column"), *(r.get("key_columns") or [])]) if c and c != time]
    work = frame.sort_values([*keys, "period_end"], kind="mergesort").reset_index(drop=True)
    grouped = work.groupby(keys, sort=False, dropna=False)
    value = pd.to_numeric(work[value_column], errors="coerce").astype("float64")
    base = grouped[value_column].shift(1)
    base_end = grouped["period_end"].shift(1)
    base_complete = grouped["period_complete"].shift(1)
    order = grouped.cumcount()
    period = pd.PeriodIndex(pd.to_datetime(work["period_end"]), freq=DERIVED_PERIODS[r.get("analysis_frequency")])
    base_period = pd.PeriodIndex(pd.to_datetime(base_end), freq=DERIVED_PERIODS[r.get("analysis_frequency")])
    base_value = pd.to_numeric(base, errors="coerce").astype("float64")
    valid = (order > 0) & np.isfinite(base_value) & (base_value > 0) & np.isfinite(value)
    ret = np.where(valid, value / base_value - 1.0, np.nan)
    status = np.where(order == 0, "NO_PRIOR_PERIOD", np.where(valid, "COMPLETE", "INVALID_BASE_VALUE"))
    between = [None if o == 0 else int((p - b).n) - 1 for o, p, b in zip(order, period, base_period)]
    out = pd.DataFrame({**{k: work[k] for k in keys}, "period_end": work["period_end"],
                        "base_period_end": base_end, "base_value": base_value, "value": value,
                        "return_decimal": ret, "return_pct": ret * 100.0, "periods_between": between,
                        "period_complete": work["period_complete"].astype(bool),
                        "base_period_complete": base_complete, "calculation_status": status})
    _log({"call": "resampled_returns", "data_request_id": r["data_request_id"], "value_column": value_column,
          "rows": int(len(out)), "formula": f"{value_column}[period] / {value_column}[previous period] - 1"})
    return out


def event_summary(events, baseline, *, hypothesis_id: str, outcome_column: str, date_column: str,
                  success_column: str | None = None, success_above: float = 0.0, horizon_periods: int = 1,
                  outcome_unit: str = "PERCENT", expected_direction: str = "HIGHER", min_effect: float | None = None,
                  comparisons: int = 1, multiple_testing_policy: str = "NONE") -> dict[str, Any]:
    """The research findings of one condition -> outcome experiment (research_stats version 1).

    events: one row per condition occurrence with its outcome; baseline: the comparison rows (for example every
    other date or entity-date); both carry outcome_column and date_column. A success is success_column (boolean)
    when given, else outcome > success_above. Rows on one date are one cluster and outcomes spanning
    horizon_periods overlap, so the effective sample counts distinct dates at least horizon_periods apart.

    Releases research_events_<hypothesis_id> (per-date aggregates) and research_summary_<hypothesis_id>, and returns
    the summary: angle_a (mean difference with CI and p-value), angle_b (success share against the baseline share),
    sample (effective count, category, minimum detectable effect) and verdict. The backend recomputes all of it from
    research_events_<hypothesis_id> with the approved plan's direction, horizon, unit, smallest effect and
    multiple-testing values; those are the values reported to the user."""
    import research_stats

    if not isinstance(hypothesis_id, str) or not _re.fullmatch(r"[a-z][a-z0-9_]{0,39}", hypothesis_id):
        raise SanitiError("hypothesis_id is the approved experiment's hypothesis_id (lower-case letters, digits, _).")
    try:
        table = research_stats.aggregate(events, baseline, outcome_column, date_column, success_column,
                                         success_above)
        summary = research_stats.summarize(table, horizon_periods=horizon_periods,
                                           expected_direction=expected_direction, outcome_unit=outcome_unit,
                                           min_effect=min_effect, comparisons=comparisons,
                                           multiple_testing_policy=multiple_testing_policy)
    except research_stats.ResearchStatsError as exc:
        raise SanitiError(str(exc)) from None
    import pandas as pd

    for group, frame in (("CONDITION", events), ("BASELINE", baseline)):
        values = pd.to_numeric(frame[outcome_column], errors="coerce").dropna()
        summary["groups"][group]["median"] = float(values.median()) if len(values) else None
    emit_table(f"research_events_{hypothesis_id}", table,
               "Per-date aggregates of the condition and baseline rows (research findings input).")
    emit_json(f"research_summary_{hypothesis_id}", summary, "Research findings: both angles, sample and verdict.")
    _log({"call": "event_summary", "hypothesis_id": hypothesis_id, "rows": int(table["n"].sum()),
          "dates": int(len(table)), "flag": summary["sample"]["flag"], "verdict": summary["verdict"]})
    return summary


# ---------------------------------------------------------------- Multi-Angle Research wrappers

RESEARCH_FAMILIES = {"research_conditional": "CONDITIONAL_OUTCOME", "research_persistence": "PERSISTENCE",
                     "research_group_comparison": "GROUP_COMPARISON", "research_quantiles": "QUANTILE_RANKING",
                     "research_temporal_dependency": "TEMPORAL_DEPENDENCY"}


def _research_angle(angle_id: Any, family: str | None) -> dict[str, Any]:
    if not _RESEARCH:
        raise SanitiError("The research_* helpers work only in an approved multi-angle research session.")
    angles = _RESEARCH.get("angles") or {}
    if angle_id not in angles:
        raise SanitiError(f"{angle_id!r} is not an approved angle of bundle group {_RESEARCH.get('bundle_group_id')}: "
                          f"{sorted(angles)}.")
    if angle_id in _RESEARCH_DONE or angle_id in _RESEARCH_PENDING:
        raise SanitiError(f"Angle {angle_id} is already recorded. Each angle is recorded once; its finding is computed "
                          "from that input and is final. Record the next approved angle, or call complete_research_run "
                          "(do not modify the sandbox's modules to record it again).")
    angle = angles[angle_id]
    if family is not None and angle["method_family"] != family:
        wrapper = next(name for name, f in RESEARCH_FAMILIES.items() if f == angle["method_family"])
        raise SanitiError(f"Angle {angle_id} uses {angle['method_id']} ({angle['method_family']}); record it with "
                          f"saniti.{wrapper}.")
    return angle


def _research_dataset(angle: dict[str, Any], request: str) -> dict[str, Any]:
    contract = angle.get("contract") or {}
    allowed = [(d["data_request_id"], d.get("logical_name")) for d in contract.get("datasets") or []]
    if not isinstance(request, str):
        # found live (golden run 2026-09-29): a contract entry passed as request= failed with "unhashable type: dict"
        example = f"request={allowed[0][0]!r}; " if allowed else ""
        raise SanitiError(f"request is the data_request_id string of one contract request ({example}allowed: "
                          f"{allowed}), not the contract entry itself.")
    local = (contract.get("local_request_ids") or {}).get(request)
    for dataset in contract.get("datasets") or []:
        if request in (dataset["data_request_id"], dataset.get("logical_name")) or local == dataset["data_request_id"]:
            return dataset
    raise SanitiError(f"{request!r} is not a data request of this angle's contract; allowed: {allowed}.")


def _research_approved(angle: dict[str, Any]) -> dict[str, Any]:
    return {k: angle.get(k) for k in ("parameters", "expected_direction", "outcome_horizon_periods", "outcome_unit",
                                      "min_effect", "multiple_testing_policy", "candidate_count",
                                      "pairwise_comparisons", "holdout_start")}


def _research_bounds(angle: dict[str, Any], frame) -> None:
    """A frame the code built stays inside the angle's contract: its dates inside the extracted windows of the
    contract's requests, its entities among those the requests delivered."""
    import pandas as pd

    datasets = [_request(d["data_request_id"]) for d in (angle.get("contract") or {}).get("datasets") or []]
    windows = [(w["extract_from"], w["extract_to"]) for r in datasets for w in r.get("ranges") or []
               if w.get("extract_from") and w.get("extract_to")]
    if "date" in frame.columns and windows:
        dates = pd.to_datetime(frame["date"], errors="coerce")
        low, high = pd.Timestamp(min(w[0] for w in windows)), pd.Timestamp(max(w[1] for w in windows))
        outside = int(((dates < low) | (dates > high)).sum())
        if outside:
            raise SanitiError(f"CONTRACT_DATE_OUTSIDE: {outside} rows have dates outside the angle's contract "
                              f"({low.date()} to {high.date()}).")
    if "entity" in frame.columns:
        delivered: set[str] = set()
        for r in datasets:
            column = r.get("entity_column")
            if column:
                found = _frame(f"SELECT DISTINCT {_ident(column)} AS e FROM {_ident(r['logical_name'])}")
                delivered |= {str(v) for v in found["e"].tolist()}
        unknown = sorted({str(v) for v in frame["entity"].dropna().tolist()} - delivered)
        if delivered and unknown:
            raise SanitiError(f"CONTRACT_ENTITY_OUTSIDE: entities {unknown[:10]} are not in the angle's contract data.")


def _write_research_input(angle_id: str, frame) -> dict[str, Any]:
    import hashlib

    import pandas as pd
    import pyarrow as pa
    import pyarrow.parquet as pq
    import research_engines

    if len(frame) > research_engines.MAX_INPUT_ROWS:
        raise OutputLimitExceeded(f"An angle's input has at most {research_engines.MAX_INPUT_ROWS} rows.")
    flat = frame.reset_index(drop=True).copy()
    flat["date"] = pd.to_datetime(flat["date"]).dt.normalize()
    for column in flat.columns:
        if flat[column].dtype == object and column != "entity":
            flat[column] = flat[column].map(lambda v: None if v is None else v)
    name = f"research_input_{angle_id}"
    file_name = _file(_name(name, internal=True), "parquet")
    path = _os.path.join(_OUTPUT_DIR, file_name)
    table = pa.Table.from_pandas(flat, preserve_index=False)
    pq.write_table(table, path, compression="zstd")
    with open(path, "rb") as handle:
        digest = hashlib.sha256(handle.read()).hexdigest()
    _record("TABLE", "PARQUET", name, file_name, f"Research input of angle {angle_id} (recorded for the backend "
                                                 "finding).", columns=table.column_names, row_count=table.num_rows)
    return {"name": name, "sha256": digest, "rows": table.num_rows, "columns": table.column_names}


def _write_research_call(angle_id: str, call: dict[str, Any]) -> None:
    name = f"research_call_{angle_id}"
    text = _json.dumps(_jsonable(call), ensure_ascii=False, separators=(",", ":"))
    if len(text.encode("utf-8")) > int(_LIMITS["max_json_bytes"]):
        raise OutputLimitExceeded("The research call record is too large.")
    file_name = _file(_name(name, internal=True), "json")
    with open(_os.path.join(_OUTPUT_DIR, file_name), "w", encoding="utf-8") as handle:
        handle.write(text)
    _record("JSON", "JSON", name, file_name, f"Research call of angle {angle_id}.")


def _research(family: str, angle_id: str, frame, request: str | None, range_id: str | None,
              roles: dict[str, Any]) -> dict[str, Any]:
    import research_engines
    import research_inputs

    angle = _research_angle(angle_id, family)
    method = angle["method_id"]
    declared = {k: v for k, v in roles.items() if v is not None}
    if (frame is None) == (request is None):
        raise SanitiError("Pass either frame (a DataFrame your code built, with columns date, entity and the roles) "
                          "or request with the role declarations, not both.")
    if frame is not None:
        if declared:
            raise SanitiError("Role declarations (expressions) go with request=...; with frame=, name the frame's "
                              "columns after the roles.")
        required, optional = research_inputs.roles_for(method)
        import pandas as pd

        if not isinstance(frame, pd.DataFrame):
            raise SanitiError("frame must be a pandas DataFrame.")
        missing = [c for c in ("date", *required) if c not in frame.columns]
        if missing:
            raise SanitiError(f"frame lacks the columns {missing}; {method} takes date, entity (optional) and "
                              f"{list(required)}" + (f" (optional {list(optional)})" if optional else "") + ".")
        canonical = frame[[c for c in ("date", "entity", *required, *optional) if c in frame.columns]].copy()
        _research_bounds(angle, canonical)
        mode, level, declaration = "FRAME", "STATISTICS_VERIFIED", None
        info = {"rows": int(len(canonical)), "outcome_source": "FRAME"}
    else:
        dataset = _research_dataset(angle, request)
        r = _request(dataset["data_request_id"])
        allowed_ranges = {w["range_id"] for w in dataset.get("ranges") or []}
        local_ranges = (angle.get("contract") or {}).get("local_range_ids") or {}
        chosen = local_ranges.get(f"{request}:{range_id}", range_id) if range_id is not None else None
        if chosen is not None and chosen not in allowed_ranges:
            raise SanitiError(f"{range_id!r} is not a range of this angle's contract for {request}; allowed: "
                              f"{sorted(allowed_ranges)}.")
        windows = [(w["start"], w["end"]) for w in r.get("ranges") or []
                   if w["range_id"] in allowed_ranges and (chosen is None or w["range_id"] == chosen)]
        keys = [c for c in (r.get("entity_column"), r.get("time_column")) if c]
        columns = [c for c in dataset.get("columns") or [] if c not in keys]
        rows = load(r["data_request_id"], columns=list(dict.fromkeys(keys + columns)))
        # a forward return may read another request of the contract (S15): name it by its data_request_id
        for role, spec in list(declared.items()):
            if isinstance(spec, dict) and isinstance(spec.get("request"), str):
                declared[role] = {**spec, "request": _research_dataset(angle, spec["request"])["data_request_id"]}
        declaration = {"request": r["data_request_id"], "range_id": chosen, "roles": declared}
        try:
            related = {}
            for other_id in research_inputs.related_requests(research_inputs.normalize(method, declaration)):
                other_dataset = _research_dataset(angle, other_id)
                other = _request(other_dataset["data_request_id"])
                other_keys = [c for c in (other.get("entity_column"), other.get("time_column")) if c]
                other_columns = [c for c in other_dataset.get("columns") or [] if c not in other_keys]
                related[other["data_request_id"]] = {
                    "rows": load(other["data_request_id"], columns=list(dict.fromkeys(other_keys + other_columns))),
                    "entity_column": other.get("entity_column"), "time_column": other["time_column"],
                    "columns": other_columns}
            canonical, info = research_inputs.build(
                method, declaration, rows, entity_column=r.get("entity_column"), time_column=r["time_column"],
                columns=columns, windows=windows, horizon=int(angle["outcome_horizon_periods"]),
                unit=angle["outcome_unit"], related=related)
        except research_inputs.InputError as exc:
            raise SanitiError(f"{exc.code}: {exc}") from None
        mode, level = "DECLARATIVE", "FORMULA_AND_STATISTICS_VERIFIED"
    problem = research_inputs.outcome_problem(method, canonical, angle.get("outcome_unit"))
    if problem:
        raise SanitiError(f"OUTCOME_NOT_APPROVED: {problem}")
    try:
        result = research_engines.evaluate(method, canonical, _research_approved(angle))
    except research_engines.EngineError as exc:
        raise SanitiError(f"{exc.code}: {exc}") from None
    decision = research_engines.decide(result, expected_direction=angle["expected_direction"], validation_level=level,
                                       minimum_sample=angle.get("minimum_sample"))
    stored = _write_research_input(angle_id, canonical)
    _write_research_call(angle_id, {"version": RESEARCH_WRAPPER_VERSION, "angle_id": angle_id, "method_id": method,
                                    "mode": mode, "validation_level": level, "declaration": declaration,
                                    "input": stored, "input_info": {k: info.get(k) for k in
                                                                    ("rows", "censored_outcome_rows",
                                                                     "forward_horizon", "expressions",
                                                                     "outcome_source")}})
    _RESEARCH_PENDING.add(angle_id)
    _log({"call": "research", "angle_id": angle_id, "method_id": method, "mode": mode, "rows": stored["rows"]})
    primary = result.get("primary") or {}
    return {"angle_id": angle_id, "method_id": method, "mode": mode, "validation_level": level,
            "preview": {**decision, "primary": {k: primary.get(k) for k in ("candidate", "estimate", "ci",
                                                                            "ci_adjusted", "p_value", "p_adjusted")},
                        "sample": result.get("sample")},
            "note": "Preview only: when the bundle group completes, the backend recomputes this angle's finding from "
                    "the recorded input with the approved values; that finding is the one reported."}


def research_conditional(angle_id: str, frame=None, *, request: str | None = None, range_id: str | None = None,
                         condition: Any = None, signal: Any = None, outcome: Any = None) -> dict[str, Any]:
    """Record one conditional-outcome angle (conditional_distribution: condition + outcome; threshold_sensitivity:
    signal + outcome, thresholds from the approved plan). Either frame= a DataFrame with date, entity and the role
    columns (validation STATISTICS_VERIFIED), or request= a contract data request with each role declared as an
    expression over its columns and outcome={'forward_return': 'close'} (FORMULA_AND_STATISTICS_VERIFIED)."""
    return _research("CONDITIONAL_OUTCOME", angle_id, frame, request, range_id,
                     {"condition": condition, "signal": signal, "outcome": outcome})


def research_persistence(angle_id: str, frame=None, *, request: str | None = None, range_id: str | None = None,
                         state: Any = None) -> dict[str, Any]:
    """Record one streak_persistence angle: state (True/False per entity and date); streak lengths and horizon come
    from the approved plan."""
    return _research("PERSISTENCE", angle_id, frame, request, range_id, {"state": state})


def research_group_comparison(angle_id: str, frame=None, *, request: str | None = None, range_id: str | None = None,
                              group: Any = None, outcome: Any = None) -> dict[str, Any]:
    """Record one regime_comparison (group = a property of the date) or cohort_comparison (group fixed per entity)
    angle; only the approved group labels may appear."""
    return _research("GROUP_COMPARISON", angle_id, frame, request, range_id, {"group": group, "outcome": outcome})


def research_quantiles(angle_id: str, frame=None, *, request: str | None = None, range_id: str | None = None,
                       signal: Any = None, outcome: Any = None) -> dict[str, Any]:
    """Record one quantile_ranking angle: signal ranked per date into the approved number of buckets."""
    return _research("QUANTILE_RANKING", angle_id, frame, request, range_id, {"signal": signal, "outcome": outcome})


def research_temporal_dependency(angle_id: str, frame=None, *, request: str | None = None,
                                 range_id: str | None = None, leader: Any = None, follower: Any = None,
                                 condition: Any = None) -> dict[str, Any]:
    """Record one lead_lag or correlation_dependency angle: leader and follower (and, for correlation_dependency, an
    optional condition); lags, rolling window and method come from the approved plan."""
    return _research("TEMPORAL_DEPENDENCY", angle_id, frame, request, range_id,
                     {"leader": leader, "follower": follower, "condition": condition})


def research_custom(angle_id: str, result: Any, note: str) -> dict[str, Any]:
    """Record an angle the research helpers cannot express: the result of custom code. Its finding is
    EXECUTION_ONLY (nothing is recomputed) and can be at most INSUFFICIENT_EVIDENCE."""
    angle = _research_angle(angle_id, None)
    if not isinstance(note, str) or not note.strip():
        raise SanitiError("note says why the approved method could not be used.")
    _write_research_call(angle_id, {"version": RESEARCH_WRAPPER_VERSION, "angle_id": angle_id,
                                    "method_id": angle["method_id"], "mode": "CUSTOM",
                                    "validation_level": "EXECUTION_ONLY", "note": note[:1000],
                                    "result": _jsonable(result)})
    _RESEARCH_PENDING.add(angle_id)
    _log({"call": "research", "angle_id": angle_id, "method_id": angle["method_id"], "mode": "CUSTOM", "rows": 0})
    return {"angle_id": angle_id, "mode": "CUSTOM", "validation_level": "EXECUTION_ONLY",
            "note": "Recorded as EXECUTION_ONLY: the backend cannot recompute it, so it cannot support the hypothesis."}


PERIOD_RETURN_STATUSES = ("COMPLETE", "NO_PRIOR_CLOSE", "NO_END_VALUE", "INVALID_BASE_VALUE",
                          "INSUFFICIENT_INPUT_DATA", "DUPLICATE_BOUNDARY_OBSERVATION")
PERIOD_RETURN_COLUMNS = ["entity", "base_date", "base_value", "end_date", "end_value", "return_decimal", "return_pct",
                         "calculation_status", "range_id", "period_start", "period_end"]


def _period_values(series) -> Any:
    """The value column as float64 (NaN for null); a non-numeric value is an argument error, not a silent NaN."""
    import decimal

    import numpy as np
    import pandas as pd

    if pd.api.types.is_bool_dtype(series):
        raise PeriodReturnError("value_column must be numeric, not boolean.")
    if pd.api.types.is_numeric_dtype(series):
        return series.astype("float64")
    out = []
    for value in series.tolist():
        if value is None or (isinstance(value, float) and _math.isnan(value)) or value is pd.NA:
            out.append(float("nan"))
        elif isinstance(value, (int, float, decimal.Decimal, np.number)) and not isinstance(value, (bool, np.bool_)):
            out.append(float(value))
        else:
            raise PeriodReturnError(f"value_column holds a non-numeric value ({type(value).__name__}).")
    return pd.Series(out, index=series.index, dtype="float64")


def period_return(request: str, range_id: str, value_column: str = "close", entity_column: str | None = None,
                  date_column: str | None = None):
    """A named calendar-period return (YTD, month, quarter, year, a comparable calendar period), one row per entity.

    Convention: base = the last valid value strictly before the range start; end = the last valid value on or
    before the range end, observed inside the range (a value from before the start is never reused as the end);
    return_decimal = end / base - 1; return_pct = return_decimal * 100. Valid means non-null and finite. Values are
    never rounded. The rows are read through range(request, range_id, include_buffers=True), so the Coverage Validator
    records the range and its history buffer; the request needs a history_buffer (1 TRADING_OBSERVATIONS).

    calculation_status per entity: COMPLETE; NO_PRIOR_CLOSE (no valid value before the start within the delivered
    history buffer: the first value inside the period is never used instead); NO_END_VALUE (no valid value inside the
    period); INVALID_BASE_VALUE (the base is zero or negative: no division); INSUFFICIENT_INPUT_DATA (no valid value
    at all, or an entity the scope named that has no row); DUPLICATE_BOUNDARY_OBSERVATION (two different valid values
    for the entity on the base or end date: none is chosen). Entities come from the delivered rows of this range and
    its buffers plus those the scope named without data; the other statuses keep base/end details when known. Leave
    entities that are not COMPLETE out of rankings and report how many were left out.

    Not for a date-to-date formula the user gives, event forward returns, rolling returns or intraday returns."""
    import numpy as np
    import pandas as pd

    r = _request(request)
    window = next((w for w in r.get("ranges") or [] if w["range_id"] == range_id), None)
    if window is None:
        raise PeriodReturnError(f"{range_id!r} is not a range of {r['logical_name']}. Ranges: "
                                f"{[w['range_id'] for w in r.get('ranges') or []]}")
    entity = entity_column or r.get("entity_column")
    time = date_column or r.get("time_column")
    if not entity:
        raise PeriodReturnError(f"{r['logical_name']} has no catalog entity column: pass entity_column.")
    if not time:
        raise PeriodReturnError(f"{r['logical_name']} has no time column, so it has no calendar period.")
    if time != r.get("time_column"):
        raise PeriodReturnError(f"date_column must be the request's time column {r.get('time_column')!r}: the range "
                                "and its buffers are defined on it.")
    for role, column in (("value_column", value_column), ("entity_column", entity)):
        if column not in r["columns"]:
            raise PeriodReturnError(f"{role} {column!r} is not a column of {r['logical_name']}. Columns: "
                                    f"{r['columns']}")
    if len({value_column, entity, time}) < 3:
        raise PeriodReturnError("value_column, entity_column and date_column must be three different columns.")
    start, end = _dt.date.fromisoformat(window["start"]), _dt.date.fromisoformat(window["end"])
    if _dt.date.fromisoformat(window["extract_from"]) >= start:
        raise PeriodReturnError(f"{r['data_request_id']} has no history buffer before {range_id}: declare "
                                "history_buffer 1 TRADING_OBSERVATIONS on the request, prepare the bundle again and "
                                "rerun. The first value inside the period is never used as the base.")

    frame = range(request, range_id, columns=[entity, time, value_column], include_buffers=True)
    values = _period_values(frame[value_column])
    try:
        stamps = pd.to_datetime(frame[time])
    except (TypeError, ValueError) as exc:
        raise PeriodReturnError(f"date_column {time!r} does not hold dates.") from exc
    if getattr(stamps.dt, "tz", None) is not None:
        stamps = stamps.dt.tz_localize(None)
    work = pd.DataFrame({"entity": frame[entity], "date": stamps.dt.normalize(), "value": values})
    dropped = int(work["entity"].isna().sum())
    if dropped:
        add_warning("PERIOD_RETURN_NULL_ENTITY", f"{dropped} rows of {r['logical_name']} have no {entity}; they were "
                                                 "not assigned to any entity.")
        work = work[work["entity"].notna()]
    # input order never matters: every boundary is chosen from the dates, and duplicates are compared, not picked
    work = work.assign(_key=work["entity"].astype(str)).sort_values(["_key", "date"], kind="mergesort")
    valid = work[np.isfinite(work["value"].to_numpy(dtype="float64"))]
    start_ts, after_end = pd.Timestamp(start), pd.Timestamp(end) + pd.Timedelta(days=1)

    def boundary(rows) -> tuple[Any, Any, bool]:
        """(date, value, conflicting) of the last date in rows; conflicting when it holds different valid values."""
        if rows.empty:
            return None, None, False
        last = rows["date"].max()
        found = pd.unique(rows.loc[rows["date"] == last, "value"])
        return last.date(), float(found[0]), len(found) > 1

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    valid_by_entity = {key: rows for key, rows in valid.groupby("_key", sort=False)}
    empty = valid.iloc[0:0]
    for key, group in work.groupby("_key", sort=True):
        seen.add(key)
        rows = valid_by_entity.get(key, empty)
        base_date, base_value, base_conflict = boundary(rows[rows["date"] < start_ts])
        end_date, end_value, end_conflict = boundary(rows[(rows["date"] >= start_ts) & (rows["date"] < after_end)])
        result = None
        if rows.empty:
            status = "INSUFFICIENT_INPUT_DATA"
        elif base_date is None:
            status = "NO_PRIOR_CLOSE"
        elif base_conflict:
            status, base_value = "DUPLICATE_BOUNDARY_OBSERVATION", None
        elif base_value <= 0:
            status = "INVALID_BASE_VALUE"
        elif end_date is None:
            status = "NO_END_VALUE"
        elif end_conflict:
            status, end_value = "DUPLICATE_BOUNDARY_OBSERVATION", None
        else:
            status, result = "COMPLETE", end_value / base_value - 1.0
        if end_conflict:
            end_value = None
        out.append({"entity": group["entity"].iloc[0], "base_date": base_date, "base_value": base_value,
                    "end_date": end_date, "end_value": end_value, "return_decimal": result,
                    "return_pct": result * 100.0 if result is not None else None, "calculation_status": status})
    for named in (r.get("quality") or {}).get("empty_entities") or []:
        if str(named) not in seen:
            seen.add(str(named))
            out.append({"entity": named, "base_date": None, "base_value": None, "end_date": None, "end_value": None,
                        "return_decimal": None, "return_pct": None, "calculation_status": "INSUFFICIENT_INPUT_DATA"})
    table = pd.DataFrame(out, columns=PERIOD_RETURN_COLUMNS[:8])
    table["range_id"], table["period_start"], table["period_end"] = range_id, start, end
    table = table.assign(_key=table["entity"].astype(str)).sort_values("_key", kind="mergesort") \
        .drop(columns="_key").reset_index(drop=True)
    for column in ("base_value", "end_value", "return_decimal", "return_pct"):
        table[column] = pd.to_numeric(table[column], errors="coerce").astype("float64")
    excluded = table[table["calculation_status"] != "COMPLETE"]
    if len(excluded):
        counts = excluded["calculation_status"].value_counts().sort_index().to_dict()
        add_warning("PERIOD_RETURN_EXCLUSIONS", f"{len(excluded)} of {len(table)} entities in {range_id} have no "
                                                f"period return: {counts}. Leave them out of rankings and say so.")
    return table


def insufficient_data(request: str, range_id: str | None = None, value: int | None = None,
                      unit: str = "TRADING_OBSERVATIONS", requirement_type: str = "ADDITIONAL_HISTORY",
                      reason: str = "") -> None:
    """Stop this execution: the approved data cannot support the analysis. The session answers
    INSUFFICIENT_INPUT_DATA with the requirement, and the DataNeedSpec gets a new revision."""
    r = _request(request)
    raise InsufficientInputData(r["data_request_id"], range_id, {"type": requirement_type, "value": value,
                                                                  "unit": unit}, str(reason)[:500])


def intermediate_path(name: str) -> str:
    if not INTERMEDIATE_NAME.fullmatch(name or ""):
        raise SanitiError("Intermediate names are 1-64 letters, digits, '_' or '-'.")
    return _os.path.join(_INTERMEDIATE_DIR, f"{name}.parquet")


def add_warning(code: str, message: str) -> None:
    if len(_WARNINGS) < 50:
        _WARNINGS.append({"code": str(code)[:60], "message": str(message)[:500]})


# ---------------------------------------------------------------- outputs

def _name(name: str, internal: bool = False) -> str:
    if not isinstance(name, str) or not NAME.fullmatch(name):
        raise InvalidOutput("Output names are 1-80 letters, digits, spaces, '_', '-' or '.'.")
    if not internal and name.startswith(RESEARCH_RESERVED):
        raise InvalidOutput(f"Output names starting with {RESEARCH_RESERVED} are written only by the research_* "
                            "helpers.")
    return name


def _file(name: str, extension: str) -> str:
    total = len([f for f in _os.listdir(_OUTPUT_DIR) if not f.startswith(".")])
    if total >= int(_LIMITS["max_outputs"]):
        raise OutputLimitExceeded(f"A session emits at most {_LIMITS['max_outputs']} outputs.")
    _SEQ[0] += 1
    safe = _re.sub(r"[^A-Za-z0-9_-]", "_", name)[:40]
    return f"{_SEQ[0]:04d}_{safe}.{extension}"


def _record(kind: str, fmt: str, name: str, file_name: str, description: str, **extra: Any) -> dict[str, Any]:
    entry = {"type": kind, "format": fmt, "name": name, "file": file_name, "description": str(description)[:500],
             **extra}
    _OUTPUTS.append(entry)
    return {k: v for k, v in entry.items() if k != "file"}


def _arrow(frame):
    import pandas as pd
    import pyarrow as pa

    if isinstance(frame, pd.Series):
        frame = frame.to_frame()
    if not isinstance(frame, pd.DataFrame):
        raise InvalidOutput("A table output must be a pandas DataFrame or Series.")
    if len(frame.columns) > 200:
        raise InvalidOutput("A table output has at most 200 columns.")
    limit = int(_LIMITS.get("max_table_rows") or 0)  # P12: 0 = no row limit (the default)
    if limit and len(frame) > limit:
        raise OutputLimitExceeded(f"A table output has at most {limit} rows.")
    flat = frame.reset_index(drop=not any(n is not None for n in frame.index.names)) \
        if not isinstance(frame.index, pd.RangeIndex) else frame
    flat.columns = [str(c) for c in flat.columns]
    return pa.Table.from_pandas(flat, preserve_index=False)


def emit_table(name: str, data, description: str = "") -> dict[str, Any]:
    """A TABLE output (stored as Parquet; readable back page by page)."""
    import pyarrow.parquet as pq

    table = _arrow(data)
    file_name = _file(_name(name), "parquet")
    pq.write_table(table, _os.path.join(_OUTPUT_DIR, file_name), compression="zstd")
    return _record("TABLE", "PARQUET", name, file_name, description, columns=table.column_names,
                   row_count=table.num_rows)


def emit_chart(figure=None, name: str = "chart", title: str = "", description: str = "") -> dict[str, Any]:
    """A CHART output (PNG) from a matplotlib figure (default: the current figure)."""
    import matplotlib.pyplot as plt

    fig = figure if figure is not None else plt.gcf()
    if title:
        fig.suptitle(str(title)[:200])
    file_name = _file(_name(name), "png")
    fig.savefig(_os.path.join(_OUTPUT_DIR, file_name), format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    return _record("CHART", "PNG", name, file_name, description, title=str(title)[:200])


def _jsonable(value: Any, depth: int = 0) -> Any:
    if depth > 8:
        raise InvalidOutput("JSON outputs nest at most 8 levels.")
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if _math.isfinite(value) else None
    if isinstance(value, (_dt.date, _dt.datetime)):
        return value.isoformat()
    if hasattr(value, "item") and not hasattr(value, "__len__"):
        return _jsonable(value.item(), depth)
    if isinstance(value, dict):
        return {str(k): _jsonable(v, depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v, depth + 1) for v in value]
    if hasattr(value, "tolist"):
        return _jsonable(value.tolist(), depth + 1)
    return str(value)


def emit_json(name: str, value, description: str = "") -> dict[str, Any]:
    """A JSON output (numbers, strings, lists and objects)."""
    text = _json.dumps(_jsonable(value), ensure_ascii=False, separators=(",", ":"))
    if len(text.encode("utf-8")) > int(_LIMITS["max_json_bytes"]):
        raise OutputLimitExceeded(f"A JSON output is at most {_LIMITS['max_json_bytes']} bytes.")
    file_name = _file(_name(name), "json")
    with open(_os.path.join(_OUTPUT_DIR, file_name), "w", encoding="utf-8") as handle:
        handle.write(text)
    return _record("JSON", "JSON", name, file_name, description)


def emit_text(name: str, text: str, description: str = "") -> dict[str, Any]:
    """A TEXT output."""
    body = str(text)
    if len(body) > int(_LIMITS["max_text_chars"]):
        raise OutputLimitExceeded(f"A TEXT output is at most {_LIMITS['max_text_chars']} characters.")
    file_name = _file(_name(name), "txt")
    with open(_os.path.join(_OUTPUT_DIR, file_name), "w", encoding="utf-8") as handle:
        handle.write(body)
    return _record("TEXT", "TEXT", name, file_name, description, characters=len(body))


def emit_file(name: str, data, format: str = "PARQUET", description: str = "") -> dict[str, Any]:  # noqa: A002
    """A file output: PARQUET or CSV from a DataFrame, PNG from bytes, or any other bytes as ARTIFACT."""
    fmt = str(format).upper()
    if fmt in ("PARQUET", "CSV"):
        table = _arrow(data)
        file_name = _file(_name(name), fmt.lower())
        path = _os.path.join(_OUTPUT_DIR, file_name)
        if fmt == "PARQUET":
            import pyarrow.parquet as pq

            pq.write_table(table, path, compression="zstd")
        else:
            import pyarrow.csv as pc

            pc.write_csv(table, path)
        return _record(fmt, fmt, name, file_name, description, columns=table.column_names, row_count=table.num_rows)
    if not isinstance(data, (bytes, bytearray)):
        raise InvalidOutput(f"A {fmt} output takes bytes.")
    kind = "PNG" if fmt == "PNG" else "ARTIFACT"
    file_name = _file(_name(name), "png" if kind == "PNG" else "bin")
    with open(_os.path.join(_OUTPUT_DIR, file_name), "wb") as handle:
        handle.write(bytes(data))
    return _record(kind, fmt, name, file_name, description)


emit_artifact = emit_file
