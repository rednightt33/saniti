"""Results carried from G to G (user decision 2026-10-02, extends speed plan step 9) and the data profile the model
sees (P1, P2, P5).

Carried outputs: every released table of the conversation (an analysis table, an event study's tables, a hypothesis
plan's aggregates, a multi-angle angle's recorded input) can be loaded in any later session of the same conversation
with saniti.load_output(output_id). Before each execution the server links the allowed tables read-only into the
session's input/carried directory with a manifest: what each table is, which path made it (G1-G4), its label (how the
backend checked it), where it came from (completion, request, time) and a short profile. A session of a RESEARCH need
loads only the tables its approved plan names (carried_outputs at session open; none when the plan names none), so a
research input is part of what the user approved.

The profile (P1 at session open for every bundle dataset, P2 for every carried table) lets the model see the shape of
the data before writing code, as data-analysis agents do (LIDA's data summary, the head/describe a notebook shows):
per column its type, nulls, distinct values, range or most frequent values, plus the row and entity counts, the date
range and a few sample rows. It is for understanding only: an answer still cites released outputs and findings.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any, Callable

CARRIED_DIR = "carried"
MANIFEST = "manifest.json"
MAX_CARRIED = 40
# records the backend recomputes from, never results (released for the audit only)
RECORD_PREFIXES = ("research_call_", "event_study_call_", "backtest_call_")
PROFILE_COLUMNS = 40
SAMPLE_ROWS = 5
TOP_VALUES = 5
MAX_TOP_COLUMNS = 12  # most frequent values for at most this many text columns
LABEL_MEANING = {
    "CALCULATION_VERIFIED": "the backend rebuilt this table from its declaration and recomputed it; it matched",
    "DATA_COVERAGE_VERIFIED": "the data read covered the approved need; the formula of the code was not recalculated",
    "NOT_RELEASED": "not released: a session output that may not be cited yet",
}


def kind_of(name: str, verified: bool) -> str:
    """Which path made a table, from the names the helpers give their tables."""
    if name.startswith("research_input_"):
        return "G4"
    if name.startswith(("research_events_", "research_summary_")):
        return "G3"
    if verified:
        return "G2"
    return "G1"


def label_of(origin: dict[str, Any] | None) -> str:
    return "CALCULATION_VERIFIED" if (origin or {}).get("calculation_verified") else \
        str((origin or {}).get("evidence_label") or "DATA_COVERAGE_VERIFIED")


def _scalar(value: Any) -> Any:
    import datetime as dt
    import decimal
    import math

    if isinstance(value, float):
        return None if math.isnan(value) or math.isinf(value) else round(value, 6)
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    return value


def profile(paths: list[str], *, time_column: str | None = None, entity_column: str | None = None,
            columns: list[str] | None = None) -> dict[str, Any]:
    """A compact summary of a table read from Parquet files: rows, entities, date range, per column type, nulls,
    distinct values and either min / median / max (numbers, dates) or the most frequent values (text), and a few
    sample rows. Columns beyond PROFILE_COLUMNS are counted, not shown (P5: never cut silently)."""
    import duckdb

    if not paths:
        return {"rows": 0, "columns": {}}
    con = duckdb.connect(":memory:")
    try:
        source = "read_parquet([" + ", ".join("'" + p.replace("'", "''") + "'" for p in paths) + "])"
        described = con.execute(f"DESCRIBE SELECT * FROM {source}").fetchall()
        types = {row[0]: str(row[1]) for row in described}
        names = [c for c in (columns or list(types)) if c in types]
        shown, hidden = names[:PROFILE_COLUMNS], names[PROFILE_COLUMNS:]

        def q(name: str) -> str:
            return '"' + name.replace('"', '""') + '"'

        numeric_kinds = ("INT", "DOUBLE", "FLOAT", "DECIMAL", "REAL", "NUMERIC")
        kinds = {n: ("NUMBER" if any(t in types[n].upper() for t in numeric_kinds)
                     else "TIME" if any(t in types[n].upper() for t in ("DATE", "TIME")) else "TEXT") for n in shown}
        # one scan for every count and range (a bundle can hold millions of rows)
        parts = ["count(*)"]
        for name in shown:
            parts += [f"count(*) - count({q(name)})", f"approx_count_distinct({q(name)})"]
            if kinds[name] == "NUMBER":
                parts += [f"min({q(name)})", f"median({q(name)})", f"max({q(name)})"]
            elif kinds[name] == "TIME":
                parts += [f"min({q(name)})", f"max({q(name)})"]
        if entity_column and entity_column in types:
            parts.append(f"count(DISTINCT {q(entity_column)})")
        if time_column and time_column in types:
            parts += [f"min({q(time_column)})", f"max({q(time_column)})"]
        values = list(con.execute(f"SELECT {', '.join(parts)} FROM {source}").fetchone())
        rows = int(values.pop(0))
        result: dict[str, Any] = {"rows": rows, "columns": {}}
        text_columns = []
        for name in shown:
            entry: dict[str, Any] = {"type": types[name], "nulls": int(values.pop(0)), "distinct": int(values.pop(0))}
            if kinds[name] == "NUMBER":
                entry.update(min=_scalar(values.pop(0)), median=_scalar(values.pop(0)), max=_scalar(values.pop(0)))
            elif kinds[name] == "TIME":
                entry.update(min=_scalar(values.pop(0)), max=_scalar(values.pop(0)))
            else:
                text_columns.append(name)
            result["columns"][name] = entry
        if entity_column and entity_column in types:
            result["entities"] = int(values.pop(0))
        if time_column and time_column in types:
            result["date_range"] = [_scalar(values.pop(0)), _scalar(values.pop(0))]
        for name in text_columns[:MAX_TOP_COLUMNS]:
            top = con.execute(f"SELECT {q(name)}, count(*) AS n FROM {source} WHERE {q(name)} IS NOT NULL "
                              f"GROUP BY 1 ORDER BY n DESC, 1 LIMIT {TOP_VALUES}").fetchall()
            result["columns"][name]["top"] = [[_scalar(v), int(n)] for v, n in top]
        if hidden:
            result["columns_not_shown"] = len(hidden)
        sample = con.execute(f"SELECT {', '.join(q(c) for c in shown) or '*'} FROM {source} LIMIT {SAMPLE_ROWS}")
        header = [d[0] for d in sample.description]
        result["sample"] = [{k: _scalar(v) for k, v in zip(header, row)} for row in sample.fetchall()]
        return result
    finally:
        con.close()


def candidates(store: Any, conversation_key: str | None, session_id: str) -> list[dict[str, Any]]:
    """Released tables a session may carry: the conversation's, newest first (none without a conversation key),
    never its own (those it already has) and never a backend record."""
    if not conversation_key:
        return []
    found = []
    for output in store.released_outputs(conversation_key, MAX_CARRIED * 3):
        name = str(output.get("name") or "")
        meta = output.get("meta") if isinstance(output.get("meta"), dict) else {}
        # a table restored into this session from the orchestrator's store is carried, unlike its own outputs
        if (output.get("session_id") == session_id and not meta.get("restored")) or output.get("format") != "PARQUET" \
                or name.startswith(RECORD_PREFIXES):
            continue
        found.append(output)
        if len(found) >= MAX_CARRIED:
            break
    return found


def stage(directory: Path, outputs: list[dict[str, Any]], *, outputs_root: Path,
          origin_of: Callable[[str, str], dict[str, Any] | None], allowed: set[str] | None,
          profiles: dict[str, dict[str, Any]], now: str) -> list[dict[str, Any]]:
    """Link the allowed, unexpired tables into input/carried read-only and write the manifest the session's
    load_output reads; returns the manifest entries. profiles caches a table's profile by output_id."""
    target = directory / "input" / CARRIED_DIR
    target.mkdir(mode=0o755, exist_ok=True)
    entries = []
    keep = set()
    for output in outputs:
        output_id = str(output["output_id"])
        if allowed is not None and output_id not in allowed:
            continue
        if str(output.get("expires_at") or "") <= now:
            continue
        source = outputs_root / output["relative_path"]
        if not source.is_file():
            continue
        file_name = f"{output_id}.parquet"
        path = target / file_name
        if not path.exists():
            try:
                os.link(source, path)
            except OSError:
                shutil.copyfile(source, path)
            os.chmod(path, 0o444)
        keep.add(file_name)
        origin = origin_of(str(output["session_id"]), output_id) or {}
        label = label_of(origin)
        if output_id not in profiles:
            profiles[output_id] = profile([str(path)])
        entries.append({
            "output_id": output_id, "name": output.get("name"), "file": file_name,
            "kind": kind_of(str(output.get("name") or ""), bool(origin.get("calculation_verified"))),
            "label": label, "label_meaning": LABEL_MEANING.get(label, ""),
            "columns": output.get("columns"), "rows": output.get("row_count"),
            "origin": {k: origin.get(k) for k in ("completion_id", "request_id", "need_id", "completed_at",
                                                  "calculation_validation")},
            "expires_at": output.get("expires_at"), "profile": profiles[output_id],
            # H1 (M63): how the table was made, so a later step reads it instead of guessing
            "definition": (output.get("meta") or {}).get("definition") if isinstance(output.get("meta"), dict)
            else None,
            "execution_id": output.get("execution_id"),
            # R-STORE: a table restored from the orchestrator's store, and the last date of its data
            **({"restored": True} if (output.get("meta") or {}).get("restored") else {}),
            **({"data_as_of": (output.get("meta") or {})["data_as_of"]}
               if (output.get("meta") or {}).get("data_as_of") else {})})
    for stale in target.iterdir():
        if stale.name not in keep and stale.name != MANIFEST:
            stale.unlink(missing_ok=True)
    manifest = target / MANIFEST
    temporary = target / (MANIFEST + ".tmp")
    temporary.write_text(json.dumps(entries, default=str), encoding="utf-8")
    os.chmod(temporary, 0o444)
    os.replace(temporary, manifest)
    return entries


def listing(entries: list[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
    """What the session's open view lists (P2, P5): each table with its label and origin; profiles via carried()."""
    shown = [{k: e.get(k) for k in ("output_id", "name", "kind", "label", "label_meaning", "rows", "columns", "origin",
                                     "definition")}
             for e in entries[:limit]]
    if len(entries) > limit:
        shown.append({"not_shown": len(entries) - limit})
    return shown
