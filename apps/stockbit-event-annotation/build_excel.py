#!/usr/bin/env python3
"""Rebuild idx_event_annotation as Excel from an export_job.py log (or a local CSV for tests).

    python build_excel.py --log export.log --output idx_event_annotation.xlsx

Fails when a chunk is missing or the sha256 differs, so the workbook is exactly what the database held.
Sheets: the table (one row per event), column definitions from Column_Catalog, and counts per family and flag.
"""
from __future__ import annotations

import argparse
import base64
import collections
import csv
import gzip
import hashlib
import io
import json
import re
from datetime import date, datetime
from pathlib import Path

NUMERIC = {"shares_before", "shares_after", "shares_change", "pct_after", "pct_change", "price", "value_idr"}


def read_log(path: Path) -> tuple[list[list[str]], list[list]]:
    chunks, end, defs = {}, None, []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.search(r"\bEXP (\d+) (\S+)", line)
        if m:
            chunks[int(m.group(1))] = m.group(2)
        m = re.search(r"\bEXP_END (\d+) ([0-9a-f]{64}) (\d+)", line)
        if m:
            end = (int(m.group(1)), m.group(2), int(m.group(3)))
        m = re.search(r"\bDEFS (\[.*\])\s*$", line)
        if m:
            defs = json.loads(m.group(1))
    if end is None:
        raise SystemExit("EXP_END not found: the export did not finish")
    missing = [i for i in range(end[0]) if i not in chunks]
    if missing:
        raise SystemExit(f"{len(missing)} chunks missing (first {missing[:5]}): fetch the log again")
    data = base64.b64decode("".join(chunks[i] for i in range(end[0])))
    if hashlib.sha256(data).hexdigest() != end[1]:
        raise SystemExit("sha256 mismatch: the log is incomplete or altered")
    rows = list(csv.reader(io.StringIO(gzip.decompress(data).decode())))
    if len(rows) - 1 != end[2]:
        raise SystemExit(f"row count {len(rows) - 1} != {end[2]}")
    return rows, defs


def typed(col: str, value: str):
    if value == "":
        return None
    if col in NUMERIC:
        f = float(value)
        return int(f) if f.is_integer() and col != "pct_after" and col != "pct_change" else f
    if col == "annotation_date":
        return date.fromisoformat(value)
    if col == "is_estimated_price":
        return value == "True"
    if col in ("source_fetched_at", "ingestion_time"):
        return datetime.fromisoformat(value).replace(tzinfo=None)
    return value


def write(rows: list[list[str]], defs: list[list], output: Path) -> dict:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    head, body = rows[0], rows[1:]
    wb = Workbook(write_only=True)
    bold, fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="305496")
    ws = wb.create_sheet("idx_event_annotation")
    ws.freeze_panes = "B2"
    for i, col in enumerate(head, 1):
        ws.column_dimensions[get_column_letter(i)].width = max(12, min(30, len(col) + 4))
    from openpyxl.cell import WriteOnlyCell
    cells = []
    for col in head:
        c = WriteOnlyCell(ws, value=col)
        c.font, c.fill = bold, fill
        cells.append(c)
    ws.append(cells)
    fam, flags = collections.Counter(), collections.Counter()
    for r in body:
        ws.append([typed(c, v) for c, v in zip(head, r)])
        fam[(r[1], r[2])] += 1
        if r[1] == "INSIDER":
            flags[r[head.index("pct_quality_flag")]] += 1
    d = wb.create_sheet("Definisi kolom")
    d.append(["Kolom", "Tipe", "Satuan", "Arti", "Aturan NULL"])
    for row in defs:
        d.append(row)
    s = wb.create_sheet("Ringkasan")
    s.append(["event_family", "event_type", "baris"])
    for (a, b), n in sorted(fam.items()):
        s.append([a, b, n])
    s.append([])
    s.append(["pct_quality_flag (insider)", "baris"])
    for k, n in flags.most_common():
        s.append([k, n])
    wb.save(output)
    return {"rows": len(body), "by_type": {f"{a}/{b}": n for (a, b), n in sorted(fam.items())}}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    rows, defs = read_log(args.log)
    print(json.dumps(write(rows, defs, args.output)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
