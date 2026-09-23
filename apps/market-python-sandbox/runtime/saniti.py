"""Runtime helpers available to analysis code as `import saniti` (or `from saniti import ...`).

Official results are only what these functions emit: TABLE, METRICS, CHART, and ARTIFACT outputs.
print() output is kept only as bounded diagnostics.

Time-series helpers keep entity histories separate and ordered, surface duplicates, and enforce
minimum history. They never fill missing values.
"""
from __future__ import annotations

import datetime as _dt
import decimal as _decimal
import json as _json
import math as _math
import os as _os
from collections.abc import Iterator
from typing import Any

__all__ = [
    "DATASETS", "SEED", "load_dataset", "emit_table", "emit_metrics", "emit_chart", "emit_artifact",
    "add_warning", "panel_check", "prepare_panel", "iter_series", "SanitiError", "InsufficientHistory",
    "DuplicateObservations", "OutputLimitExceeded", "UndeclaredOutput", "InvalidOutput",
]

# Populated by runner.py from the harness-controlled job file. Model code cannot choose paths.
DATASETS: dict[str, str] = {}
SEED: int = 0
_LIMITS: dict[str, int] = {}
_EXPECTED: set[str] = set()
_OUTPUT_DIR = ""
_INDEX: list[dict[str, Any]] = []
_WARNINGS: list[dict[str, str]] = []
_COUNTS = {"TABLE": 0, "METRICS": 0, "CHART": 0, "ARTIFACT": 0}
NAME_MAX = 80
TEXT_MAX = 500
CELL_TEXT_MAX = 200
MAX_WARNINGS = 50
MAX_COLUMNS = 100


class SanitiError(Exception):
    code = "PYTHON_EXCEPTION"


class InsufficientHistory(SanitiError):
    code = "INSUFFICIENT_HISTORY"


class DuplicateObservations(SanitiError):
    code = "DUPLICATE_OBSERVATIONS"


class OutputLimitExceeded(SanitiError):
    code = "OUTPUT_LIMIT_EXCEEDED"


class UndeclaredOutput(SanitiError):
    code = "OUTPUT_INVALID"


class InvalidOutput(SanitiError):
    code = "OUTPUT_INVALID"


def _configure(job: dict[str, Any], output_dir: str) -> None:
    global SEED, _OUTPUT_DIR
    DATASETS.clear()
    DATASETS.update(job["datasets"])
    SEED = int(job["seed"])
    _LIMITS.clear()
    _LIMITS.update(job["limits"])
    _EXPECTED.clear()
    _EXPECTED.update(job["expected_outputs"])
    _OUTPUT_DIR = output_dir


# ---------------------------------------------------------------- inputs

def load_dataset(dataset_id: str, columns: list[str] | None = None):
    """Read one governed dataset into a pandas DataFrame."""
    import pandas as pd

    if dataset_id not in DATASETS:
        raise SanitiError(f"Dataset {dataset_id!r} is not an input of this analysis. Inputs: {sorted(DATASETS)}")
    return pd.read_parquet(DATASETS[dataset_id], columns=columns)


# ---------------------------------------------------------------- warnings

def add_warning(code: str, message: str) -> None:
    """Record an analytical limitation that must be preserved in the final answer."""
    if len(_WARNINGS) >= MAX_WARNINGS:
        return
    _WARNINGS.append({"code": _name(str(code), "warning code")[:NAME_MAX].upper(),
                      "message": str(message)[:TEXT_MAX]})
    _write_index()


# ---------------------------------------------------------------- time-series safety

def _pandas(frame):
    if hasattr(frame, "to_pandas") and not hasattr(frame, "iloc"):
        return frame.to_pandas()  # polars or pyarrow
    return frame


def panel_check(frame, entity: str, date: str, value_columns: list[str] | None = None) -> dict[str, Any]:
    """Describe a multi-entity time series without changing it."""
    df = _pandas(frame)
    for column in [entity, date, *(value_columns or [])]:
        if column not in df.columns:
            raise SanitiError(f"Column {column!r} is not in the data. Columns: {list(df.columns)}")
    sizes = df.groupby(entity, sort=False).size()
    duplicated = int(df.duplicated([entity, date]).sum())
    ordered = df.groupby(entity, sort=False)[date].apply(lambda s: s.is_monotonic_increasing)
    report = {
        "rows": int(len(df)), "entities": int(sizes.size),
        "duplicate_observations": duplicated,
        "entities_not_date_ordered": int((~ordered).sum()) if len(ordered) else 0,
        "null_entity_or_date_rows": int(df[[entity, date]].isna().any(axis=1).sum()),
        "min_history": int(sizes.min()) if sizes.size else 0,
        "max_history": int(sizes.max()) if sizes.size else 0,
        "date_range": [_scalar(df[date].min()), _scalar(df[date].max())] if len(df) else None,
        "null_values": {c: int(df[c].isna().sum()) for c in (value_columns or [])},
    }
    return report


def prepare_panel(frame, entity: str, date: str, on_duplicate: str = "error"):
    """Return the data sorted by (entity, date) with duplicates handled explicitly.

    on_duplicate: "error" (default) raises DuplicateObservations; "keep_last"/"keep_first" keep one
    row per (entity, date) and record a warning. Rows with a null entity or date are dropped and
    recorded in a warning. Missing observations are never filled.
    """
    if on_duplicate not in {"error", "keep_last", "keep_first"}:
        raise SanitiError("on_duplicate must be 'error', 'keep_last', or 'keep_first'")
    df = _pandas(frame)
    report = panel_check(df, entity, date)
    if report["null_entity_or_date_rows"]:
        add_warning("NULL_KEYS_DROPPED", f"{report['null_entity_or_date_rows']} rows with a null {entity} or {date} "
                                         f"were excluded.")
        df = df.dropna(subset=[entity, date])
    if report["duplicate_observations"]:
        if on_duplicate == "error":
            raise DuplicateObservations(
                f"{report['duplicate_observations']} duplicate ({entity}, {date}) observations. Choose "
                f"on_duplicate='keep_last' or 'keep_first' explicitly, or aggregate them first.")
        keep = "last" if on_duplicate == "keep_last" else "first"
        df = df.sort_values([entity, date], kind="stable").drop_duplicates([entity, date], keep=keep)
        add_warning("DUPLICATES_RESOLVED", f"{report['duplicate_observations']} duplicate ({entity}, {date}) "
                                           f"observations resolved with keep='{keep}'.")
    return df.sort_values([entity, date], kind="stable").reset_index(drop=True)


def iter_series(frame, entity: str, date: str, min_history: int = 1,
                on_duplicate: str = "error") -> Iterator[tuple[Any, Any]]:
    """Yield (entity_value, history) per entity, each sorted by date, never mixing entities.

    Entities with fewer than min_history observations are skipped and recorded in an
    INSUFFICIENT_HISTORY warning. If no entity qualifies, InsufficientHistory is raised.
    """
    if int(min_history) < 1:
        raise SanitiError("min_history must be at least 1")
    df = prepare_panel(frame, entity, date, on_duplicate=on_duplicate)
    skipped: list[str] = []
    yielded = 0
    for key, group in df.groupby(entity, sort=True):
        if len(group) < min_history:
            skipped.append(str(key))
            continue
        yielded += 1
        yield key, group.reset_index(drop=True)
    if skipped:
        sample = ", ".join(skipped[:10])
        add_warning("INSUFFICIENT_HISTORY",
                    f"{len(skipped)} of {len(skipped) + yielded} entities had fewer than {min_history} observations "
                    f"and were excluded (e.g. {sample}).")
    if not yielded:
        raise InsufficientHistory(f"No entity has at least {min_history} observations.")


# ---------------------------------------------------------------- outputs

def _name(value: str, what: str) -> str:
    text = str(value).strip()
    if not text or len(text) > NAME_MAX or not all(ch.isalnum() or ch in "_-. " for ch in text):
        raise InvalidOutput(f"{what} must be 1-{NAME_MAX} characters of letters, digits, space, _ - .")
    return text


def _declared(kind: str) -> None:
    if kind not in _EXPECTED:
        raise UndeclaredOutput(f"{kind} output was not declared in expected_outputs {sorted(_EXPECTED)}.")
    limit = {"TABLE": "max_tables", "METRICS": "max_metrics", "CHART": "max_charts", "ARTIFACT": "max_artifacts"}[kind]
    if _COUNTS[kind] >= _LIMITS[limit]:
        raise OutputLimitExceeded(f"At most {_LIMITS[limit]} {kind} outputs are allowed per analysis.")


def _write_index() -> None:
    if not _OUTPUT_DIR:
        return
    path = _os.path.join(_OUTPUT_DIR, "index.json")
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8") as handle:
        _json.dump({"outputs": _INDEX, "warnings": _WARNINGS}, handle, separators=(",", ":"), allow_nan=False)
    _os.replace(temp, path)


def _scalar(value: Any) -> Any:
    """JSON-safe scalar. NaN/inf become None; text is bounded."""
    if value is None:
        return None
    try:
        import numpy as np
        if isinstance(value, np.generic):
            value = value.item()
    except ImportError:  # pragma: no cover
        pass
    if isinstance(value, bool) or isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if _math.isfinite(value) else None
    if isinstance(value, _decimal.Decimal):
        return float(value) if value.is_finite() else None
    if isinstance(value, (_dt.datetime, _dt.date, _dt.time)):
        return value.isoformat()
    if hasattr(value, "isoformat"):  # pandas Timestamp
        try:
            if value != value:  # NaT
                return None
        except (TypeError, ValueError):
            pass
        return value.isoformat()
    text = str(value)
    return text[:CELL_TEXT_MAX]


def _arrow_table(data):
    import pyarrow as pa

    if isinstance(data, pa.Table):
        table = data
    elif hasattr(data, "to_arrow"):          # polars
        table = data.to_arrow()
    elif hasattr(data, "iloc"):              # pandas
        table = pa.Table.from_pandas(data, preserve_index=False)
    elif isinstance(data, list):
        table = pa.Table.from_pylist(data)
    elif isinstance(data, dict):
        table = pa.table(data)
    else:
        raise InvalidOutput("Table data must be a pandas/polars DataFrame, a pyarrow Table, a list of dicts, "
                            "or a dict of columns.")
    names = [str(n) for n in table.column_names]
    if len(names) > MAX_COLUMNS:
        raise OutputLimitExceeded(f"A table may have at most {MAX_COLUMNS} columns.")
    if len(set(names)) != len(names):
        raise InvalidOutput("Table column names must be unique.")
    return table.rename_columns(names)


def _type_name(arrow_type) -> str:
    import pyarrow as pa

    if pa.types.is_floating(arrow_type):
        return "float"
    if pa.types.is_integer(arrow_type):
        return "integer"
    if pa.types.is_boolean(arrow_type):
        return "boolean"
    if pa.types.is_date(arrow_type):
        return "date"
    if pa.types.is_timestamp(arrow_type):
        return "timestamp"
    if pa.types.is_string(arrow_type) or pa.types.is_large_string(arrow_type):
        return "string"
    if pa.types.is_decimal(arrow_type):
        return "decimal"
    return str(arrow_type)


def _write_parquet(table, filename: str) -> int:
    import pyarrow.parquet as pq

    path = _os.path.join(_OUTPUT_DIR, filename)
    pq.write_table(table, path, compression="zstd")
    size = _os.path.getsize(path)
    if size > _LIMITS["max_artifact_bytes"]:
        _os.unlink(path)
        raise OutputLimitExceeded(f"The output file is {size} bytes, above the per-output limit.")
    return size


def emit_table(name: str, data, description: str = "") -> None:
    """Emit a TABLE. The complete table is stored; the model receives a bounded preview."""
    _declared("TABLE")
    name = _name(name, "Table name")
    table = _arrow_table(data)
    if table.num_rows > _LIMITS["max_table_output_rows"]:
        raise OutputLimitExceeded(
            f"Table {name!r} has {table.num_rows} rows, above the table output limit of "
            f"{_LIMITS['max_table_output_rows']}. Filter or aggregate it, or emit it as a PARQUET artifact.")
    _COUNTS["TABLE"] += 1
    filename = f"table_{_COUNTS['TABLE']}.parquet"
    _write_parquet(table, filename)
    preview = table.slice(0, _LIMITS["max_table_preview_rows"]).to_pylist()
    _INDEX.append({
        "type": "TABLE", "name": name, "description": str(description)[:TEXT_MAX], "file": filename,
        "row_count": table.num_rows,
        "columns": [{"name": f.name, "type": _type_name(f.type)} for f in table.schema],
        "preview_rows": [[_scalar(row[c]) for c in table.column_names] for row in preview],
    })
    _write_index()


def _metric_value(value: Any, depth: int) -> Any:
    if isinstance(value, (dict, list, tuple)) and depth > 3:
        raise InvalidOutput("Metric objects and lists may nest at most 3 levels deep.")
    if isinstance(value, dict):
        if len(value) > 100:
            raise InvalidOutput("A metrics object may have at most 100 keys per level.")
        return {_name(str(k), "Metric name"): _metric_value(v, depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        if len(value) > 100:
            raise InvalidOutput("A metric list may have at most 100 items; emit a TABLE for more.")
        return [_metric_value(v, depth + 1) for v in value]
    scalar = _scalar(value)
    if isinstance(scalar, str) and len(scalar) > TEXT_MAX:
        scalar = scalar[:TEXT_MAX]
    return scalar


def emit_metrics(values: dict, name: str = "metrics") -> None:
    """Emit compact JSON-compatible METRICS (numbers, short text, small lists/objects)."""
    _declared("METRICS")
    if not isinstance(values, dict) or not values:
        raise InvalidOutput("emit_metrics expects a non-empty dict.")
    cleaned = _metric_value(values, 1)
    raw = _json.dumps(cleaned, separators=(",", ":"), allow_nan=False)
    if len(raw.encode()) > _LIMITS["max_metrics_bytes"]:
        raise OutputLimitExceeded("The metrics object is too large; emit a TABLE instead.")
    _COUNTS["METRICS"] += 1
    _INDEX.append({"type": "METRICS", "name": _name(name, "Metrics name"), "values": cleaned})
    _write_index()


def emit_chart(figure=None, name: str = "chart", title: str = "", description: str = "") -> None:
    """Save a matplotlib figure (default: the current figure) as a PNG CHART."""
    _declared("CHART")
    name = _name(name, "Chart name")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig = figure if figure is not None else plt.gcf()
    _COUNTS["CHART"] += 1
    filename = f"chart_{_COUNTS['CHART']}.png"
    path = _os.path.join(_OUTPUT_DIR, filename)
    fig.savefig(path, format="png", dpi=100, bbox_inches="tight")
    if _os.path.getsize(path) > _LIMITS["max_artifact_bytes"]:
        _os.unlink(path)
        raise OutputLimitExceeded("The chart image is larger than the per-output limit.")
    _INDEX.append({"type": "CHART", "name": name, "title": str(title)[:TEXT_MAX] or name,
                   "description": str(description)[:TEXT_MAX], "file": filename, "format": "PNG"})
    _write_index()


def emit_artifact(name: str, data, format: str = "PARQUET", description: str = "") -> None:
    """Emit a large complete ARTIFACT: PARQUET (preferred) or CSV for tables, JSON for small objects."""
    _declared("ARTIFACT")
    name = _name(name, "Artifact name")
    fmt = str(format).upper()
    if fmt not in {"PARQUET", "CSV", "JSON"}:
        raise InvalidOutput("Artifact format must be PARQUET, CSV, or JSON.")
    _COUNTS["ARTIFACT"] += 1
    stem = f"artifact_{_COUNTS['ARTIFACT']}"
    row_count = None
    if fmt == "JSON":
        filename = stem + ".json"
        path = _os.path.join(_OUTPUT_DIR, filename)
        with open(path, "w", encoding="utf-8") as handle:
            _json.dump(_metric_value(data, 1) if isinstance(data, dict) else [_metric_value(v, 2) for v in data],
                       handle, separators=(",", ":"), allow_nan=False)
    else:
        table = _arrow_table(data)
        row_count = table.num_rows
        if fmt == "PARQUET":
            filename = stem + ".parquet"
            _write_parquet(table, filename)
        else:
            import pyarrow.csv as pcsv
            filename = stem + ".csv"
            pcsv.write_csv(table, _os.path.join(_OUTPUT_DIR, filename))
    if _os.path.getsize(_os.path.join(_OUTPUT_DIR, filename)) > _LIMITS["max_artifact_bytes"]:
        _os.unlink(_os.path.join(_OUTPUT_DIR, filename))
        raise OutputLimitExceeded("The artifact is larger than the per-output limit.")
    _INDEX.append({"type": "ARTIFACT", "name": name, "description": str(description)[:TEXT_MAX],
                   "file": filename, "format": fmt, "row_count": row_count})
    _write_index()
