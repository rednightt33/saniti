"""Operations on a stored table without a session (round 2026-10-03 D0).

market-ai-orc keeps released outputs for the life of a conversation (R-STORE) but cannot read Parquet, and the
sandbox's own copy is deleted after PY_SANDBOX_RESULT_RETENTION_HOURS. These operations take the file itself as the
request body, so a table can be paged (get_session_output), written as a download (export_result) or recounted
(get_evidence) whether or not the sandbox still holds it. One reader, one size cap, one checksum check for all three.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
from datetime import date, datetime
from typing import Any

STORED_TABLES_VERSION = 1
OPS = ("page", "export", "recount")
SOURCE_FORMATS = ("PARQUET", "CSV", "JSON", "TEXT")
EXPORT_FORMATS = {"CSV": ("text/csv", "csv"), "PARQUET": ("application/vnd.apache.parquet", "parquet"),
                  "XLSX": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx")}
EXPORT_MAX_BYTES = 20 * 1024 * 1024  # AI_conversation_export.size_bytes (decision 3)
XLSX_MAX_ROWS = 1_048_575  # one header row
PAGE_MAX = 500
RECOUNT_MAX_ROWS = 200
WHERE_OPS = ("EQ", "NE", "GT", "GE", "LT", "LE", "IN")
MEASURES = ("COUNT", "COUNT_DISTINCT", "SUM", "MIN", "MAX", "MEAN")


class StoredTableError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 422, next_action: str | None = None,
                 **details: Any) -> None:
        super().__init__(message)
        self.code, self.message, self.http_status = code, message, http_status
        self.next_action, self.details = next_action, details


def verify(data: bytes, meta: dict[str, Any]) -> str:
    """The source format once the body matches the checksum the orchestrator stored."""
    fmt = meta.get("format")
    if fmt not in SOURCE_FORMATS:
        raise StoredTableError("STORED_TABLE_FORMAT", f"format must be one of {', '.join(SOURCE_FORMATS)}.")
    if hashlib.sha256(data).hexdigest() != meta.get("checksum_sha256"):
        raise StoredTableError("STORED_TABLE_CHECKSUM_MISMATCH",
                               "The file does not match its checksum; it was not read.")
    return fmt


def _table(data: bytes, fmt: str):
    import pyarrow as pa
    import pyarrow.csv as pc
    import pyarrow.parquet as pq

    if fmt == "PARQUET":
        return pq.read_table(io.BytesIO(data))
    if fmt == "CSV":
        return pc.read_csv(io.BytesIO(data))
    if fmt == "JSON":
        rows = json.loads(data)
        if isinstance(rows, dict) and isinstance(rows.get("rows"), list):
            rows = rows["rows"]
        if isinstance(rows, list) and all(isinstance(r, dict) for r in rows):
            return pa.Table.from_pylist(rows)
    raise StoredTableError("STORED_TABLE_NOT_TABULAR", f"A {fmt} output is not a table.",
                           next_action="Use page to read it as text, or choose a table output.")


def _plain(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return json.loads(json.dumps(rows, default=str))


def page(data: bytes, meta: dict[str, Any], offset: int, limit: int) -> dict[str, Any]:
    """The same shape as reading a session output: rows for tables, 100-character chunks for JSON and TEXT."""
    fmt = verify(data, meta)
    offset, limit = max(0, int(offset)), max(1, min(int(limit), PAGE_MAX))
    if fmt in ("PARQUET", "CSV"):
        table = _table(data, fmt)
        rows = table.slice(offset, limit).to_pylist()
        return {"format": fmt, "row_count": table.num_rows, "offset": offset, "rows": _plain(rows),
                "next_offset": offset + len(rows) if offset + len(rows) < table.num_rows else None}
    text = data.decode("utf-8")
    chunk = text[offset * 100: offset * 100 + limit * 100]
    value: Any = json.loads(text) if fmt == "JSON" and len(text) <= limit * 100 and offset == 0 else chunk
    return {"format": fmt, "offset": offset, "content": value,
            "next_offset": offset + limit if offset * 100 + limit * 100 < len(text) else None}


def _cell(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, str, date, datetime)):
        return value
    if isinstance(value, float):
        return None if math.isnan(value) or math.isinf(value) else value
    if hasattr(value, "is_integer") or hasattr(value, "as_tuple"):  # Decimal
        return float(value)
    return json.dumps(value, default=str) if isinstance(value, (list, dict)) else str(value)


def _pairs(value: Any, prefix: str = "") -> list[tuple[str, str]]:
    """A nested definition or lineage as readable key/value rows."""
    if isinstance(value, dict):
        out: list[tuple[str, str]] = []
        for key, item in value.items():
            out.extend(_pairs(item, f"{prefix}{key}" if not prefix else f"{prefix}.{key}"))
        return out
    if isinstance(value, list) and value and all(not isinstance(v, (dict, list)) for v in value):
        return [(prefix, ", ".join(str(v) for v in value))]
    if isinstance(value, list):
        out = []
        for i, item in enumerate(value):
            out.extend(_pairs(item, f"{prefix}[{i}]"))
        return out
    return [(prefix or "value", "" if value is None else str(value))]


def export(data: bytes, meta: dict[str, Any]) -> tuple[bytes, str, str]:
    """(file bytes, mime type, extension). XLSX adds a 'definisi' and a 'lineage' sheet when they are given."""
    import pyarrow.csv as pc
    import pyarrow.parquet as pq

    target = meta.get("target")
    if target not in EXPORT_FORMATS:
        raise StoredTableError("EXPORT_FORMAT", f"target must be one of {', '.join(EXPORT_FORMATS)}.")
    table = _table(data, verify(data, meta))
    limit = min(int(meta.get("max_bytes") or EXPORT_MAX_BYTES), EXPORT_MAX_BYTES)
    out = io.BytesIO()
    if target == "CSV":
        pc.write_csv(table, out)
    elif target == "PARQUET":
        pq.write_table(table, out, compression="zstd")
    else:
        if table.num_rows > XLSX_MAX_ROWS:
            raise StoredTableError("EXPORT_TOO_LARGE", f"{table.num_rows} rows exceed the XLSX limit of "
                                   f"{XLSX_MAX_ROWS}.", 413, next_action="Choose PARQUET or CSV, or export fewer rows.")
        out = io.BytesIO(_xlsx(table, meta))
    body = out.getvalue()
    if len(body) > limit:
        raise StoredTableError("EXPORT_TOO_LARGE", f"The {target} file is {len(body)} bytes; the limit is {limit}.",
                               413, next_action="Export fewer columns or rows, or choose PARQUET.",
                               size_bytes=len(body), limit_bytes=limit)
    mime, ext = EXPORT_FORMATS[target]
    return body, mime, ext


def _xlsx(table, meta: dict[str, Any]) -> bytes:
    from openpyxl import Workbook

    book = Workbook(write_only=True)
    sheet = book.create_sheet("data")
    sheet.append(table.column_names)
    for batch in table.to_batches(max_chunksize=5000):
        columns = [batch.column(i).to_pylist() for i in range(batch.num_columns)]
        for row in zip(*columns):
            sheet.append([_cell(v) for v in row])
    for title, key in (("definisi", "definition"), ("lineage", "lineage")):
        if meta.get(key):
            extra = book.create_sheet(title)
            extra.append(["field", "value"])
            for field, value in _pairs(meta[key]):
                extra.append([field, value[:32000]])
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def _mask(frame, where: list[dict[str, Any]]):
    import pandas as pd

    mask = pd.Series(True, index=frame.index)
    for condition in where:
        column, op = condition.get("column"), condition.get("op")
        if column not in frame.columns:
            raise StoredTableError("RECOUNT_INVALID", f"Unknown column '{column}'.",
                                   next_action="Use a column of the table; read it with get_session_output first.",
                                   columns=list(frame.columns)[:50])
        if op not in WHERE_OPS:
            raise StoredTableError("RECOUNT_INVALID", f"op must be one of {', '.join(WHERE_OPS)}.")
        series = frame[column]
        values = condition.get("values") if op == "IN" else [condition.get("value")]
        if not isinstance(values, list) or not values:
            raise StoredTableError("RECOUNT_INVALID", f"'{column}' {op} needs a value.")
        series, values = _comparable(series, values)
        if op == "IN":
            mask &= series.isin(values)
        else:
            value = values[0]
            mask &= {"EQ": series == value, "NE": series != value, "GT": series > value, "GE": series >= value,
                     "LT": series < value, "LE": series <= value}[op]
    return mask


def _comparable(series, values: list[Any]):
    """Compare like with like: numbers as numbers, dates as dates, anything else as text."""
    import pandas as pd

    if pd.api.types.is_bool_dtype(series):
        return series, [v if isinstance(v, bool) else str(v).lower() == "true" for v in values]
    if pd.api.types.is_numeric_dtype(series):
        try:
            return series, [float(v) for v in values]
        except (TypeError, ValueError):
            raise StoredTableError("RECOUNT_INVALID", f"'{series.name}' is numeric; compare it with numbers.")
    if pd.api.types.is_datetime64_any_dtype(series) or (
            len(series) and isinstance(series.dropna().iloc[0] if series.notna().any() else None, (date, datetime))):
        try:
            return pd.to_datetime(series), [pd.Timestamp(v) for v in values]
        except (TypeError, ValueError):
            raise StoredTableError("RECOUNT_INVALID", f"'{series.name}' is a date; compare it with YYYY-MM-DD.")
    return series.astype("string"), [str(v) for v in values]


def recount(data: bytes, meta: dict[str, Any]) -> dict[str, Any]:
    """Evidence tier 2: the claim's number recomputed from the released base table, deterministically, with the
    matching rows (at most 200) as the evidence a user can check."""
    import pandas as pd

    frame = _table(data, verify(data, meta)).to_pandas()
    where = meta.get("where") or []
    measure, column = meta.get("measure"), meta.get("column")
    if not isinstance(where, list) or len(where) > 10:
        raise StoredTableError("RECOUNT_INVALID", "where must be a list of at most 10 conditions.")
    if measure not in MEASURES:
        raise StoredTableError("RECOUNT_INVALID", f"measure must be one of {', '.join(MEASURES)}.")
    if measure != "COUNT" and column not in frame.columns:
        raise StoredTableError("RECOUNT_INVALID", f"{measure} needs a column of the table.",
                               columns=list(frame.columns)[:50])
    matched = frame[_mask(frame, where)]
    if measure == "COUNT":
        value: Any = int(len(matched))
    elif measure == "COUNT_DISTINCT":
        value = int(matched[column].nunique(dropna=True))
    else:
        series = pd.to_numeric(matched[column], errors="coerce")
        if series.notna().sum() == 0:
            value = None
        else:
            value = {"SUM": series.sum, "MIN": series.min, "MAX": series.max, "MEAN": series.mean}[measure]()
            value = float(value)
    keep = [c for c in (meta.get("columns") or []) if c in matched.columns] or list(matched.columns)[:30]
    rows = matched[keep].head(RECOUNT_MAX_ROWS).to_dict(orient="records")
    return {"value": value, "measure": measure, "column": column, "rows_matched": int(len(matched)),
            "rows_total": int(len(frame)), "rows": _plain(rows), "rows_truncated": len(matched) > RECOUNT_MAX_ROWS,
            "columns": keep}

