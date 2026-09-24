"""Validates what an analysis process produced and stores it as durable results.

Everything in the output directory is untrusted: the model's code can bypass the saniti helper
and write any file. The harness therefore re-checks every limit itself, opens files without
following links, accepts only regular files owned by the job's slot user, reads Parquet footers
only (never full tables) and PNG headers only, and copies accepted files into private storage.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import secrets
import stat
import struct
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from .config import Settings
from .executor import read_child_json
from .records import Records

FILE_NAMES = {
    "TABLE": re.compile(r"^table_[0-9]{1,2}\.parquet$"),
    "CHART": re.compile(r"^chart_[0-9]{1,2}\.png$"),
    "ARTIFACT": re.compile(r"^artifact_[0-9]{1,2}\.(parquet|csv|json)$"),
}
NAME = re.compile(r"^[A-Za-z0-9_\-. ]{1,80}$")
TEXT_MAX = 500
CELL_TEXT_MAX = 200
INDEX_MAX_BYTES = 1 << 20
JSON_ARTIFACT_MAX_BYTES = 1 << 20
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_PNG_SIDE = 8000
UNCOMPRESSED_FACTOR = 8  # a stored Parquet table may expand at most this much when read back
CONTENT_TYPES = {"PARQUET": "application/vnd.apache.parquet", "CSV": "text/csv", "JSON": "application/json",
                 "PNG": "image/png"}


class OutputRejected(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class Collected:
    outputs: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, str]] = field(default_factory=list)
    output_rows: int = 0
    stored_bytes: int = 0


def _json_value(value: Any, depth: int = 0) -> Any:
    if depth > 4:
        raise OutputRejected("OUTPUT_INVALID", "Metric values nest too deeply.")
    if value is None or isinstance(value, bool) or isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise OutputRejected("OUTPUT_INVALID", "Metric values must be finite numbers.")
        return value
    if isinstance(value, str):
        return value[:TEXT_MAX]
    if isinstance(value, list):
        if len(value) > 100:
            raise OutputRejected("OUTPUT_INVALID", "Metric lists may have at most 100 items.")
        return [_json_value(v, depth + 1) for v in value]
    if isinstance(value, dict):
        if len(value) > 100 or not all(isinstance(k, str) and NAME.fullmatch(k) for k in value):
            raise OutputRejected("OUTPUT_INVALID", "Metric objects need at most 100 simple string keys.")
        return {k: _json_value(v, depth + 1) for k, v in value.items()}
    raise OutputRejected("OUTPUT_INVALID", "Metric values must be JSON numbers, strings, booleans, lists, or objects.")


def _cell(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, str):
        return value[:CELL_TEXT_MAX]
    raise OutputRejected("OUTPUT_INVALID", "Table preview cells must be JSON scalars.")


def _text(value: Any) -> str:
    return str(value if isinstance(value, str) else "")[:TEXT_MAX]


class OutputStore:
    def __init__(self, settings: Settings, records: Records) -> None:
        self.settings = settings
        self.records = records
        self.root = Path(settings.data_dir) / "results"
        self.root.mkdir(parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)

    # ------------------------------------------------------------ reading child files

    def _open_child_file(self, output_dir: Path, name: str, uid: int | None) -> tuple[int, os.stat_result]:
        try:
            fd = os.open(output_dir / name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except OSError:  # missing, or a symbolic link (ELOOP)
            raise OutputRejected("OUTPUT_INVALID", f"Output file {name} is missing or not a regular file.")
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > self.settings.max_artifact_bytes
                or (uid is not None and info.st_uid != uid)):
            os.close(fd)
            raise OutputRejected("OUTPUT_INVALID", f"Output file {name} is not an acceptable regular file.")
        return fd, info

    def _store(self, analysis_id: str, fd: int, kind: str, fmt: str, prefix: str, row_count: int | None,
               expires: str) -> dict[str, Any]:
        file_id = f"{prefix}_{secrets.token_hex(12)}"
        directory = self.root / analysis_id
        directory.mkdir(mode=0o700, exist_ok=True)
        relative = f"{analysis_id}/{file_id}.{fmt.lower()}"
        digest, size = hashlib.sha256(), 0
        os.lseek(fd, 0, os.SEEK_SET)
        with open(self.root / relative, "wb") as sink:
            while chunk := os.read(fd, 1 << 20):
                size += len(chunk)
                if size > self.settings.max_artifact_bytes:
                    raise OutputRejected("OUTPUT_LIMIT_EXCEEDED", "An output file exceeds the per-output byte limit.")
                digest.update(chunk)
                sink.write(chunk)
        entry = {"file_id": file_id, "analysis_id": analysis_id, "kind": kind, "format": fmt,
                 "relative_path": relative, "byte_count": size, "row_count": row_count,
                 "checksum_sha256": digest.hexdigest(), "created_at": datetime.now(timezone.utc).isoformat(),
                 "expires_at": expires}
        self.records.add_file(entry)
        return entry

    def store_json(self, analysis_id: str, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Persist a harness-generated JSON artifact (for example derived-feature definitions)."""
        expires = (datetime.now(timezone.utc) + timedelta(hours=self.settings.result_retention_hours)).replace(
            microsecond=0).isoformat()
        raw = json.dumps(payload, sort_keys=True, default=str).encode()
        with tempfile.TemporaryFile(dir=self.root) as handle:
            handle.write(raw)
            handle.flush()
            stored = self._store(analysis_id, handle.fileno(), "ARTIFACT", "JSON", "art", None, expires)
        return {"type": "ARTIFACT", "name": name, "generated_by": "HARNESS",
                "description": "Machine-readable definitions of the features derived in this analysis.",
                "artifact_id": stored["file_id"], "format": "JSON", "row_count": None,
                "byte_count": stored["byte_count"], "checksum_sha256": stored["checksum_sha256"], "expires_at": expires}

    def _parquet_rows(self, fd: int, name: str, expected_columns: list[str] | None) -> int:
        with os.fdopen(os.dup(fd), "rb") as handle:
            try:
                meta = pq.ParquetFile(handle).metadata
            except Exception as exc:  # noqa: BLE001 - any parse failure means the file is invalid
                raise OutputRejected("OUTPUT_INVALID", f"Output file {name} is not a valid Parquet file.") from exc
            uncompressed = sum(meta.row_group(i).total_byte_size for i in range(meta.num_row_groups))
            if uncompressed > self.settings.max_artifact_bytes * UNCOMPRESSED_FACTOR:
                raise OutputRejected("OUTPUT_LIMIT_EXCEEDED", f"Output {name} expands beyond the stored-output limit.")
            names = [meta.schema.column(i).name for i in range(meta.num_columns)]
            if expected_columns is not None and names != expected_columns:
                raise OutputRejected("OUTPUT_INVALID", f"Output {name} columns do not match its declaration.")
            return int(meta.num_rows)

    @staticmethod
    def _png_size(fd: int, name: str) -> tuple[int, int]:
        header = os.pread(fd, 24, 0)
        if len(header) < 24 or header[:8] != PNG_SIGNATURE or header[12:16] != b"IHDR":
            raise OutputRejected("OUTPUT_INVALID", f"Chart {name} is not a PNG image.")
        width, height = struct.unpack(">II", header[16:24])
        if not (0 < width <= MAX_PNG_SIDE and 0 < height <= MAX_PNG_SIDE):
            raise OutputRejected("OUTPUT_INVALID", f"Chart {name} has unsupported dimensions {width}x{height}.")
        return width, height

    # ------------------------------------------------------------ collection

    def collect(self, analysis_id: str, output_dir: Path, uid: int | None, expected: list[str]) -> Collected:
        s = self.settings
        try:
            index = read_child_json(output_dir / "index.json", uid, INDEX_MAX_BYTES)
        except FileNotFoundError:
            index = {"outputs": [], "warnings": []}
        except (OSError, ValueError):
            raise OutputRejected("OUTPUT_INVALID", "The output index is missing or invalid.")
        if not isinstance(index, dict) or not isinstance(index.get("outputs"), list):
            raise OutputRejected("OUTPUT_INVALID", "The output index is invalid.")
        collected = Collected()
        for warning in (index.get("warnings") or [])[:50]:
            if isinstance(warning, dict):
                collected.warnings.append({"code": _text(warning.get("code"))[:80] or "WARNING",
                                           "message": _text(warning.get("message"))})
        limits = {"TABLE": s.max_tables, "METRICS": s.max_metrics, "CHART": s.max_charts, "ARTIFACT": s.max_artifacts}
        counts = dict.fromkeys(limits, 0)
        expires = (datetime.now(timezone.utc) + timedelta(hours=s.result_retention_hours)).replace(
            microsecond=0).isoformat()
        for item in index["outputs"]:
            kind = item.get("type") if isinstance(item, dict) else None
            if kind not in limits:
                raise OutputRejected("OUTPUT_INVALID", "An output has an unknown type.")
            if kind not in expected:
                raise OutputRejected("OUTPUT_INVALID", f"{kind} output was not declared in expected_outputs.")
            counts[kind] += 1
            if counts[kind] > limits[kind]:
                raise OutputRejected("OUTPUT_LIMIT_EXCEEDED", f"Too many {kind} outputs.")
            name = item.get("name")
            if not isinstance(name, str) or not NAME.fullmatch(name):
                raise OutputRejected("OUTPUT_INVALID", f"A {kind} output has an invalid name.")
            if kind == "METRICS":
                values = _json_value(item.get("values"))
                if not isinstance(values, dict) or len(json.dumps(values).encode()) > s.max_metrics_bytes:
                    raise OutputRejected("OUTPUT_LIMIT_EXCEEDED", "A METRICS output is too large or not an object.")
                collected.outputs.append({"type": "METRICS", "name": name, "values": values})
                continue
            filename = item.get("file")
            if not isinstance(filename, str) or not FILE_NAMES[kind].fullmatch(filename):
                raise OutputRejected("OUTPUT_INVALID", f"A {kind} output has an invalid file reference.")
            fd, info = self._open_child_file(output_dir, filename, uid)
            try:
                if kind == "TABLE":
                    collected.outputs.append(self._table(analysis_id, fd, item, filename, expires, collected))
                elif kind == "CHART":
                    width, height = self._png_size(fd, filename)
                    stored = self._store(analysis_id, fd, "CHART", "PNG", "art", None, expires)
                    collected.stored_bytes += stored["byte_count"]
                    collected.outputs.append({
                        "type": "CHART", "name": name, "artifact_id": stored["file_id"], "format": "PNG",
                        "title": _text(item.get("title")) or name, "description": _text(item.get("description")),
                        "width": width, "height": height, "byte_count": stored["byte_count"],
                        "expires_at": expires})
                else:
                    collected.outputs.append(self._artifact(analysis_id, fd, info, item, filename, expires, collected))
            finally:
                os.close(fd)
        for kind in expected:
            if counts[kind] == 0:
                collected.warnings.append({"code": "EXPECTED_OUTPUT_MISSING",
                                           "message": f"The analysis declared a {kind} output but produced none."})
        if not collected.outputs:
            raise OutputRejected("NO_OUTPUT", "The code finished without emitting any TABLE, METRICS, CHART, or "
                                              "ARTIFACT output (use saniti.emit_*). print() output is not a result.")
        self._fit_previews(collected)
        return collected

    def copy_tables(self, output_dir: Path, uid: int | None, names: dict[str, Path]) -> dict[str, Path]:
        """Copy child-written TABLE outputs (by output name) to harness-owned read-only files, without storing
        them as results. Used for the prefix re-run of the leakage check."""
        try:
            index = read_child_json(output_dir / "index.json", uid, INDEX_MAX_BYTES)
        except (OSError, ValueError):
            return {}
        copied: dict[str, Path] = {}
        for item in index.get("outputs") or [] if isinstance(index, dict) else []:
            if not isinstance(item, dict) or item.get("type") != "TABLE" or item.get("name") not in names:
                continue
            filename = item.get("file")
            if not isinstance(filename, str) or not FILE_NAMES["TABLE"].fullmatch(filename):
                continue
            try:
                fd, _ = self._open_child_file(output_dir, filename, uid)
            except OutputRejected:
                continue
            try:
                self._parquet_rows(fd, filename, None)
                target = names[item["name"]]
                os.lseek(fd, 0, os.SEEK_SET)
                with open(target, "wb") as sink:
                    while chunk := os.read(fd, 1 << 20):
                        sink.write(chunk)
                os.chmod(target, 0o444)
                copied[item["name"]] = target
            except OutputRejected:
                continue
            finally:
                os.close(fd)
        return copied

    def _table(self, analysis_id: str, fd: int, item: dict, filename: str, expires: str,
               collected: Collected) -> dict[str, Any]:
        s = self.settings
        columns = item.get("columns")
        if (not isinstance(columns, list) or not columns or len(columns) > 100
                or not all(isinstance(c, dict) and isinstance(c.get("name"), str) for c in columns)):
            raise OutputRejected("OUTPUT_INVALID", f"Table {filename} has invalid column metadata.")
        names = [c["name"] for c in columns]
        rows = self._parquet_rows(fd, filename, names)
        if rows > s.max_table_output_rows:
            raise OutputRejected("OUTPUT_LIMIT_EXCEEDED",
                                 f"A TABLE has {rows} rows, above the table output limit. Filter or aggregate it, or "
                                 f"emit it as a PARQUET ARTIFACT.")
        if item.get("row_count") != rows:
            raise OutputRejected("OUTPUT_INVALID", f"Table {filename} row_count does not match its file.")
        preview = item.get("preview_rows")
        if not isinstance(preview, list) or len(preview) > min(rows, s.max_table_preview_rows):
            raise OutputRejected("OUTPUT_INVALID", f"Table {filename} preview is invalid or exceeds the preview limit.")
        clean = []
        for row in preview:
            if not isinstance(row, list) or len(row) != len(names):
                raise OutputRejected("OUTPUT_INVALID", f"Table {filename} preview rows do not match its columns.")
            clean.append([_cell(v) for v in row])
        stored = self._store(analysis_id, fd, "TABLE", "PARQUET", "res", rows, expires)
        collected.output_rows += rows
        collected.stored_bytes += stored["byte_count"]
        return {"type": "TABLE", "name": item["name"], "description": _text(item.get("description")),
                "row_count": rows,
                "columns": [{"name": c["name"][:80], "type": str(c.get("type", ""))[:40]} for c in columns],
                "preview_rows": clean, "preview_row_count": len(clean), "preview_truncated": len(clean) < rows,
                "result_id": stored["file_id"], "expires_at": expires}

    def _artifact(self, analysis_id: str, fd: int, info: os.stat_result, item: dict, filename: str, expires: str,
                  collected: Collected) -> dict[str, Any]:
        fmt = filename.rsplit(".", 1)[1].upper()
        if item.get("format") != fmt:
            raise OutputRejected("OUTPUT_INVALID", f"Artifact {filename} format does not match its file.")
        rows = None
        if fmt == "PARQUET":
            rows = self._parquet_rows(fd, filename, None)
        elif fmt == "JSON":
            if info.st_size > JSON_ARTIFACT_MAX_BYTES:
                raise OutputRejected("OUTPUT_LIMIT_EXCEEDED", "JSON artifacts are for small structured output; "
                                                              "use PARQUET for tables.")
            try:
                json.loads(os.pread(fd, info.st_size, 0))
            except ValueError:
                raise OutputRejected("OUTPUT_INVALID", f"Artifact {filename} is not valid JSON.")
        stored = self._store(analysis_id, fd, "ARTIFACT", fmt, "art", rows, expires)
        collected.stored_bytes += stored["byte_count"]
        return {"type": "ARTIFACT", "name": item["name"], "description": _text(item.get("description")),
                "artifact_id": stored["file_id"], "format": fmt, "row_count": rows,
                "byte_count": stored["byte_count"], "checksum_sha256": stored["checksum_sha256"],
                "expires_at": expires}

    def _fit_previews(self, collected: Collected) -> None:
        """Keep the model-facing result within PY_SANDBOX_MAX_OUTPUT_BYTES by shortening table previews.

        Shortening is always explicit (preview_row_count, preview_truncated); complete tables stay stored.
        """
        budget = self.settings.max_output_bytes

        def size() -> int:
            return len(json.dumps({"outputs": collected.outputs, "warnings": collected.warnings},
                                  separators=(",", ":")).encode())

        tables = [o for o in collected.outputs if o["type"] == "TABLE"]
        while size() > budget and any(t["preview_rows"] for t in tables):
            for table in tables:
                if table["preview_rows"]:
                    table["preview_rows"] = table["preview_rows"][: len(table["preview_rows"]) // 2]
                    table["preview_row_count"] = len(table["preview_rows"])
                    table["preview_truncated"] = table["preview_row_count"] < table["row_count"]
        if size() > budget:
            raise OutputRejected("OUTPUT_LIMIT_EXCEEDED", "The structured result is too large even without table "
                                                          "previews; emit fewer or smaller METRICS.")

    # ------------------------------------------------------------ retrieval and expiry

    def path_for(self, entry: dict[str, Any]) -> Path:
        return self.root / entry["relative_path"]

    def read_table_page(self, entry: dict[str, Any], offset: int, limit: int) -> dict[str, Any]:
        table = pq.ParquetFile(self.path_for(entry))
        columns = table.schema_arrow.names
        rows: list[list[Any]] = []
        position = 0
        for batch in table.iter_batches(batch_size=max(limit, 1)):
            if position + batch.num_rows <= offset:
                position += batch.num_rows
                continue
            start = max(0, offset - position)
            for record in batch.slice(start).to_pylist():
                if len(rows) >= limit:
                    break
                rows.append([_jsonable(record[c]) for c in columns])
            position += batch.num_rows
            if len(rows) >= limit:
                break
        end = offset + len(rows)
        return {"result_id": entry["file_id"], "analysis_id": entry["analysis_id"], "row_count": entry["row_count"],
                "columns": columns, "offset": offset, "rows": rows,
                "next_offset": end if end < (entry["row_count"] or 0) else None, "expires_at": entry["expires_at"]}

    def purge_expired(self, now: str) -> int:
        removed = 0
        for entry in self.records.expired_files(now):
            try:
                self.path_for(entry).unlink(missing_ok=True)
                self.records.delete_file(entry["file_id"])
                removed += 1
            except OSError:
                continue
        for directory in self.root.iterdir():
            if directory.is_dir() and not any(directory.iterdir()):
                directory.rmdir()
        return removed


def _jsonable(value: Any) -> Any:
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)
