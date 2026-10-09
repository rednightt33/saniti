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


# M128b (2026-10-09): an XLSX is read by people. The caller may give the column titles the reader sees ("headers":
# {name: title}) and a column sheet ("columns": [{label, name, meaning, unit}]); without them the file is as before.
COLUMN_SHEET = ("kolom", ("Kolom", "Nama asli", "Arti", "Satuan"), ("label", "name", "meaning", "unit"))
MAX_COLUMN_ROWS = 200


def _xlsx(table, meta: dict[str, Any]) -> bytes:
    from openpyxl import Workbook

    book = Workbook(write_only=True)
    sheet = book.create_sheet("data")
    headers = meta.get("headers") if isinstance(meta.get("headers"), dict) else {}
    sheet.append([str(headers.get(name) or name)[:200] for name in table.column_names])
    for batch in table.to_batches(max_chunksize=5000):
        columns = [batch.column(i).to_pylist() for i in range(batch.num_columns)]
        for row in zip(*columns):
            sheet.append([_cell(v) for v in row])
    columns = meta.get("columns")
    if isinstance(columns, list) and columns:
        title, head, keys = COLUMN_SHEET
        extra = book.create_sheet(title)
        extra.append(list(head))
        for column in columns[:MAX_COLUMN_ROWS]:
            if isinstance(column, dict):
                extra.append(["" if column.get(k) is None else str(column.get(k))[:32000] for k in keys])
    texts = meta.get("texts") if isinstance(meta.get("texts"), dict) else {}
    for title, key in (("definisi", "definition"), ("asal data", "lineage")):
        rows = _pairs(meta[key]) if meta.get(key) else []
        if key == "definition" and texts:
            rows += _reading_rows(table, meta, texts)
        if rows:
            extra = book.create_sheet(title)
            extra.append(["field", "value"])
            for field, value in rows:
                extra.append([field, value[:32000]])
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


# EXEC-Y Fase 3 E1(1) and E1(3) (user decision 2026-10-09 "E1 ok 2-4"): two rows of the 'definisi' sheet say how to
# read the file. Both are derived from the file itself and, for completeness, from the source counts the caller read
# from the SQL Governor, so a new table needs no code. The caller gives the reader's words ("texts"); without them the
# sheet is as before.
ROW_KEY_COLUMNS = 8  # the first non-numeric columns tried as the row key
ROW_KEY_SIZE = 3
MAX_COMPLETENESS_LINES = 50


def _row_key(table) -> list[str] | None:
    """The smallest set of non-numeric columns (text, date, time, flag) that is unique per row, in column order; None
    when no set of at most three is."""
    import itertools

    import pyarrow.types as t

    names = [f.name for f in table.schema if not (t.is_integer(f.type) or t.is_floating(f.type)
                                                  or t.is_decimal(f.type))][:ROW_KEY_COLUMNS]
    if not names or table.num_rows == 0:
        return None
    frame = table.select(names).to_pandas()
    for size in range(1, min(ROW_KEY_SIZE, len(names)) + 1):
        for combo in itertools.combinations(names, size):
            if not frame.duplicated(subset=list(combo)).any():
                return list(combo)
    return None


def _day_strings(series):
    import pandas as pd

    days = pd.to_datetime(series, errors="coerce")
    return days.dt.strftime("%Y-%m-%d").where(days.notna(), None)


def _completeness_rows(table, meta: dict[str, Any], texts: dict[str, str]) -> list[tuple[str, str]]:
    """The file's days per group against the days the source table has for the same group and period."""
    label = texts.get("completeness_label") or "completeness"
    check = meta.get("completeness") if isinstance(meta.get("completeness"), dict) else None
    unchecked = [(label, texts.get("unchecked") or "")]
    if not check or check.get("status") != "CHECKED":
        return unchecked if check else []
    time_column, groups = check.get("time_column"), list(check.get("group_columns") or [])
    if time_column not in table.column_names or any(g not in table.column_names for g in groups):
        return unchecked
    frame = table.select([time_column, *groups]).to_pandas()
    frame["__day"] = _day_strings(frame[time_column])
    frame = frame[frame["__day"].notna()]
    frame = frame[(frame["__day"] >= str(check.get("from"))) & (frame["__day"] <= str(check.get("to")))]
    file_days: dict[tuple, int] = {(): int(frame["__day"].nunique())}
    if groups:
        counted = frame.groupby([frame[g].astype("string").fillna("") for g in groups])["__day"].nunique()
        file_days = {(k if isinstance(k, tuple) else (k,)): int(v) for k, v in counted.items()}
    headers = meta.get("headers") if isinstance(meta.get("headers"), dict) else {}
    rows = [(label, texts.get("period", "").format(start=check.get("from"), end=check.get("to"),
                                                    calendar=check.get("calendar_dates")))]
    for group in (check.get("groups") or [])[:MAX_COMPLETENESS_LINES]:
        key = tuple("" if v is None else str(v) for v in group.get("key") or [])
        found = file_days.get(key if groups else (), 0)
        name = " / ".join(f"{headers.get(g) or g} {v}" for g, v in zip(groups, key)) or texts.get("all_rows", "")
        rows.append((label, texts.get("group", "").format(group=name, file=found, source=group.get("days"))))
    if texts.get("activity_only") and check.get("row_presence") == "ACTIVITY_ONLY":
        rows.append((label, texts["activity_only"]))
    return rows


def _reading_rows(table, meta: dict[str, Any], texts: dict[str, str]) -> list[tuple[str, str]]:
    headers = meta.get("headers") if isinstance(meta.get("headers"), dict) else {}
    key = _row_key(table)
    if key is None:
        rule = texts.get("row_rule_none") or ""
    else:
        words = [str(headers.get(name) or name) for name in key]
        rule = (texts.get("row_rule_one") or "").format(key=words[0]) if len(words) == 1 else \
            (texts.get("row_rule_many") or "").format(keys=(texts.get("and") or ", ").join(words))
    rows = [(texts.get("row_rule_label") or "row", rule)] if rule else []
    return rows + _completeness_rows(table, meta, texts)


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


def _date_extreme(series, measure: str) -> str | None:
    """MIN or MAX of a date or time column as ISO text (EXEC-Y Fase 3: the export reads a file's period this way);
    None for any other measure or a column that is not dates."""
    import pandas as pd

    if measure not in ("MIN", "MAX") or series.notna().sum() == 0:
        return None
    if not (pd.api.types.is_datetime64_any_dtype(series)
            or isinstance(series.dropna().iloc[0], (date, datetime, str))):
        return None
    days = pd.to_datetime(series, errors="coerce")
    if days.notna().sum() == 0:
        return None
    value = days.min() if measure == "MIN" else days.max()
    return value.date().isoformat() if value == value.normalize() else value.isoformat()


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
            value = _date_extreme(matched[column], measure)
        else:
            value = {"SUM": series.sum, "MIN": series.min, "MAX": series.max, "MEAN": series.mean}[measure]()
            value = float(value)
    keep = [c for c in (meta.get("columns") or []) if c in matched.columns] or list(matched.columns)[:30]
    rows = matched[keep].head(RECOUNT_MAX_ROWS).to_dict(orient="records")
    return {"value": value, "measure": measure, "column": column, "rows_matched": int(len(matched)),
            "rows_total": int(len(frame)), "rows": _plain(rows), "rows_truncated": len(matched) > RECOUNT_MAX_ROWS,
            "columns": keep}

