"""Helpers of a persistent analysis session, available to session code as `saniti` (and pre-bound names).

A session works on one governed data bundle: one logical dataset per approved data request, read-only, complete
(every row of every partition), never sampled. The code has full programmatic access to it and writes any logic it
needs; nothing here computes an indicator or checks a formula.

    requests()                      the data requests: ids, logical names, columns, ranges, rows, quality flags
    manifest()                      the bundle: need, relationships (with join semantics) and their warnings
    quality(request)                the Data Quality Manifest of one request
    load(request, columns=None)     the whole dataset as a pandas DataFrame, in delivered order
    range(request, range_id, columns=None, include_buffers=False)
                                    the rows of one approved range (with its history/future buffers if asked)
    sql(query, params=None)         DuckDB SQL over one view per logical name (read-only)
    relation(request)               a lazy DuckDB relation over one dataset
    join(relationship_id, left=None, right=None, how=None)
                                    the approved relationship as an analytic join with its point-in-time semantics
    resample(frame, request, frequency=None)
                                    the catalog's resample rules (FIRST/LAST/MAX/MIN/SUM) per entity and period
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
    "REQUESTS", "REFERENCE_DATE", "SEED", "requests", "manifest", "quality", "load", "range", "sql", "relation",
    "join", "resample", "insufficient_data", "intermediate_path", "duckdb_connection", "emit_table", "emit_chart",
    "emit_json", "emit_text", "emit_file", "emit_artifact", "add_warning", "SanitiError", "InsufficientInputData",
    "OutputLimitExceeded", "InvalidOutput", "ResampleRuleMissing",
]

REQUESTS: dict[str, dict[str, Any]] = {}
REFERENCE_DATE: str | None = None
SEED = 0
_BUNDLE: dict[str, Any] = {}
_LIMITS: dict[str, Any] = {}
_DUCKDB: dict[str, Any] = {}
_CONNECTION: Any = None
_OUTPUT_DIR = ""
_INTERMEDIATE_DIR = ""
_ACCESS: list[dict[str, Any]] = []
_OUTPUTS: list[dict[str, Any]] = []
_WARNINGS: list[dict[str, str]] = []
_SEQ = [0]
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
                                   "resample", "resample_rules", "rows")}
            | {"ranges": [{k: w[k] for k in ("range_id", "start", "end", "extract_from", "extract_to")}
                          for w in r.get("ranges") or []],
               "quality_flags": (r.get("quality") or {}).get("quality_flags") or []}
            for r in REQUESTS.values()]


def manifest() -> dict[str, Any]:
    """The bundle: need, reference date, relationships with their join semantics, relationship warnings."""
    return _json.loads(_json.dumps(_BUNDLE, default=str))


def quality(request: str) -> dict[str, Any]:
    """The Data Quality Manifest of one data request (rows, ranges, gaps, buffers, duplicates, nulls, flags)."""
    return _json.loads(_json.dumps(_request(request).get("quality") or {}, default=str))


def _frame(query: str, params: list | None = None):
    con = duckdb_connection()
    relation_ = con.sql(query, params=params) if params else con.sql(query)
    return relation_.df(date_as_object=True)


def load(request: str, columns: list[str] | None = None):
    """The whole dataset (every row of every partition and range, with the buffers) in delivered order."""
    r = _request(request)
    chosen = _columns(r, columns)
    frame = _frame(f"SELECT {', '.join(_ident(c) for c in chosen)} FROM {_ident(r['logical_name'])}")
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
                   f"WHERE {_ident(r['time_column'])} BETWEEN CAST(? AS DATE) AND CAST(? AS DATE)", [low, high])
    _log({"call": "range", "data_request_id": r["data_request_id"], "range_id": range_id,
          "include_buffers": bool(include_buffers), "columns": chosen[:30], "rows": len(frame)})
    return frame


def sql(query: str, params: list | None = None):
    """DuckDB SQL over the read-only views (one per logical name); returns a pandas DataFrame."""
    frame = _frame(query, params)
    lowered = query.lower()
    for r in REQUESTS.values():
        if _re.search(r"(?<![a-z0-9_])" + _re.escape(r["logical_name"].lower()) + r"(?![a-z0-9_])", lowered):
            _log({"call": "sql", "data_request_id": r["data_request_id"], "rows": len(frame), "full": True})
    return frame


def relation(request: str):
    """A lazy DuckDB relation over one dataset (materialize it with .df())."""
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


def join(relationship_id: int, left=None, right=None, how: str | None = None):
    """Join two datasets on an approved relationship with its join semantics, per observation date:
    CURRENT_STATE on the key, EXACT_DATE on key and date, AS_OF the latest right row at or before each left date,
    EFFECTIVE_DATED the right row valid on each left date (effective_from <= date < effective_to, open end = NULL).
    left/right default to the whole datasets; how defaults to the approved join type (INNER or LEFT)."""
    import pandas as pd

    rel = _relationship(relationship_id)
    left_request, right_request = _request(rel["left_request_id"]), _request(rel["right_request_id"])
    left = load(left_request["data_request_id"]) if left is None else left
    right = load(right_request["data_request_id"]) if right is None else right
    kind = (how or rel["join_type"]).lower()
    if kind not in ("inner", "left"):
        raise SanitiError("how must be 'inner' or 'left'.")
    lc, rc = rel["left_column"], rel["right_column"]
    semantics = rel["join_semantics"]
    suffixes = ("", f"_{right_request['logical_name']}")
    if semantics == "CURRENT_STATE":
        return left.merge(right, left_on=lc, right_on=rc, how=kind, suffixes=suffixes)
    lt = rel.get("left_time_column") or left_request.get("time_column")
    if semantics == "EXACT_DATE":
        return left.merge(right, left_on=[lc, lt], right_on=[rc, rel["right_time_column"]], how=kind,
                          suffixes=suffixes)
    if semantics == "AS_OF":
        rt = rel["right_time_column"]
        l_sorted = left.assign(_t=pd.to_datetime(left[lt])).sort_values("_t", kind="mergesort")
        r_sorted = right.assign(_t=pd.to_datetime(right[rt])).sort_values("_t", kind="mergesort")
        merged = pd.merge_asof(l_sorted, r_sorted, on="_t", left_by=lc, right_by=rc, direction="backward",
                               suffixes=suffixes)
        merged = merged.drop(columns="_t")
        if kind == "inner":
            probe = rt if rt in merged.columns else f"{rt}{suffixes[1]}"
            merged = merged[merged[probe].notna()]
        return merged.reset_index(drop=True)
    start, end = rel["effective_from_column"], rel["effective_to_column"]
    candidates = left.reset_index(drop=True).reset_index(names="_row").merge(right, left_on=lc, right_on=rc,
                                                                              how="inner", suffixes=suffixes)
    t = pd.to_datetime(candidates[lt])
    valid = (pd.to_datetime(candidates[start]) <= t) & (candidates[end].isna() | (t < pd.to_datetime(candidates[end])))
    matched = candidates[valid]
    if kind == "left":
        missing = left.reset_index(drop=True).reset_index(names="_row")
        missing = missing[~missing["_row"].isin(matched["_row"])]
        matched = pd.concat([matched, missing], ignore_index=True).sort_values("_row", kind="mergesort")
    return matched.drop(columns="_row").reset_index(drop=True)


def resample(frame, request: str, frequency: str | None = None):
    """Aggregate a daily (or finer) frame to a coarser frequency per entity with the catalog's resample rules.
    Periods: 1W weeks ending Friday, 1M calendar months, 1Q quarters, 1Y years, labelled by their last date."""
    import pandas as pd

    r = _request(request)
    target = frequency or r.get("analysis_frequency")
    if target not in PERIODS:
        raise SanitiError(f"frequency must be one of {sorted(PERIODS)}.")
    entity, time = r.get("entity_column"), r.get("time_column")
    rules = r.get("resample_rules") or {}
    values = [c for c in frame.columns if c not in (entity, time)]
    missing = [c for c in values if not rules.get(c)]
    if missing:
        raise ResampleRuleMissing(f"The catalog has no resample rule for {missing}: aggregate them yourself or drop "
                                  f"them. Rules: {rules}")
    work = frame.assign(**{time: pd.to_datetime(frame[time])})
    grouped = work.set_index(time).groupby(entity)[values].resample(PERIODS[target])
    out = grouped.agg({c: AGGREGATIONS[rules[c]] for c in values})
    counts = work.set_index(time).groupby(entity)[values[0] if values else entity].resample(PERIODS[target]).size()
    out["observations"] = counts
    out = out[out["observations"] > 0].reset_index()
    out[time] = out[time].dt.date
    return out


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

def _name(name: str) -> str:
    if not isinstance(name, str) or not NAME.fullmatch(name):
        raise InvalidOutput("Output names are 1-80 letters, digits, spaces, '_', '-' or '.'.")
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
    if len(frame) > int(_LIMITS["max_table_rows"]):
        raise OutputLimitExceeded(f"A table output has at most {_LIMITS['max_table_rows']} rows.")
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
