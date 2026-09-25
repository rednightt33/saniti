"""Data Quality Profiler: one confined process (the validator user) per governed bundle.

It measures every logical dataset of the bundle and never changes it: no recalculation of any formula, no cleaning,
no imputation, no outlier removal. Per data request it reports

- rows, entities, first and last date;
- per requested range: requested and extracted bounds, actual first and last date, rows, entities, status
  (OK, PARTIAL, EMPTY);
- per partition: rows, first and last date, rows outside the partition's window;
- duplicate primary keys (groups and excess rows);
- null counts per column;
- frequency gaps: per entity, dates of the dataset's own calendar inside the range that the entity misses between
  its first and last observation (a listing or a delisting is not a gap);
- history- and future-buffer shortfalls per range (entities with fewer observations than the buffer asked for);
- empty entities: entities the scope named explicitly that have no row;
- date ordering: dates that go backwards inside an entity when the delivered order puts the date first;
- quality_flags, the codes of everything above that is not clean.

The harness writes profile_request.json (root-owned, read-only); the result goes to result/quality.json.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import date, timedelta
from typing import Any

FREQUENCY_DAYS = {"MIN": 1 / 1440, "H": 1 / 24, "D": 1, "W": 7, "M": 30, "Q": 91, "Y": 365}
EXAMPLES = 5


def _ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _literal(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _tolerance_days(frequency: str | None) -> int:
    if not frequency or frequency == "STATIC":
        return 0
    digits = "".join(c for c in frequency if c.isdigit()) or "1"
    unit = frequency[len(digits):]
    return max(10, int(int(digits) * FREQUENCY_DAYS.get(unit, 1) * 1.5))


class Profiler:
    def __init__(self, connection: Any, reference_date: str) -> None:
        self.db = connection
        self.reference = date.fromisoformat(reference_date)
        self.views = 0

    def scalar(self, query: str) -> Any:
        row = self.db.execute(query).fetchone()
        return row[0] if row else None

    def rows(self, query: str) -> list[tuple]:
        return self.db.execute(query).fetchall()

    def profile(self, request: dict[str, Any]) -> dict[str, Any]:
        files = request["files"]
        self.views += 1
        view = f"dataset_{self.views}"
        listed = ", ".join(_literal(f["path"]) for f in files)
        self.db.execute(f"CREATE OR REPLACE TEMP VIEW {view} AS SELECT * FROM read_parquet([{listed}], "
                        f"filename=true, file_row_number=true)")
        entity, time = request.get("entity_column"), request.get("time_column")
        e, t = (_ident(entity) if entity else None), (_ident(time) if time else None)
        flags: list[str] = []
        total = int(self.scalar(f"SELECT count(*) FROM {view}") or 0)
        result: dict[str, Any] = {"data_request_id": request["data_request_id"],
                                  "logical_name": request["logical_name"], "rows": total,
                                  "entities": int(self.scalar(f"SELECT count(DISTINCT {e}) FROM {view}") or 0)
                                  if e else None}
        if t:
            low, high = self.rows(f"SELECT min({t}), max({t}) FROM {view}")[0]
            result["min_date"], result["max_date"] = _iso(low), _iso(high)
        if total == 0:
            flags.append("EMPTY_DATASET")

        result["partitions"] = self._partitions(view, files, e, t, flags)
        result["duplicate_keys"] = self._duplicates(view, request.get("key_columns") or [], flags)
        nulls = {}
        for column in request["columns"]:
            nulls[column] = int(self.scalar(f"SELECT count(*) - count({_ident(column)}) FROM {view}") or 0)
        result["null_by_column"] = nulls
        if any(nulls.values()):
            flags.append("NULL_VALUES")
        if t:
            result["requested_ranges"] = self._ranges(view, request, e, t, flags)
            result["date_ordering"] = self._ordering(view, request, e, t, flags)
        explicit = request.get("explicit_entities")
        if e and explicit:
            present = {str(r[0]) for r in self.rows(f"SELECT DISTINCT {e} FROM {view}")}
            missing = sorted(set(explicit) - present)
            result["empty_entities"] = missing[:50]
            result["empty_entities_count"] = len(missing)
            if missing:
                flags.append("EMPTY_ENTITY")
        result["quality_flags"] = sorted(set(flags))
        return result

    def _partitions(self, view: str, files: list[dict[str, Any]], e: str | None, t: str | None, flags: list[str]
                    ) -> list[dict[str, Any]]:
        out = []
        for part in files:
            where = f"filename = {_literal(part['path'])}"
            entry: dict[str, Any] = {"partition_id": part["partition_id"],
                                     "rows": int(self.scalar(f"SELECT count(*) FROM {view} WHERE {where}") or 0)}
            if e:
                # the entity set of the delivered file, hashed like the SQL manifest's entities_present
                entities = sorted({str(r[0]) for r in self.rows(
                    f"SELECT DISTINCT {e} FROM {view} WHERE {where} AND {e} IS NOT NULL")})
                entry["entities"] = len(entities)
                entry["entities_sha256"] = hashlib.sha256(json.dumps(
                    entities, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
            window = part.get("window")
            if t:
                low, high = self.rows(f"SELECT min({t}), max({t}) FROM {view} WHERE {where}")[0]
                entry.update(min_date=_iso(low), max_date=_iso(high))
                if window:
                    outside = int(self.scalar(
                        f"SELECT count(*) FROM {view} WHERE {where} AND ({t} < DATE {_literal(window['from'])} "
                        f"OR {t} > DATE {_literal(window['to'])} OR {t} IS NULL)") or 0)
                    entry["rows_outside_window"] = outside
                    if outside:
                        flags.append("ROWS_OUTSIDE_WINDOW")
            out.append(entry)
        return out

    def _duplicates(self, view: str, keys: list[str], flags: list[str]) -> dict[str, Any]:
        if not keys:
            return {"key_columns": [], "groups": None, "excess_rows": None}
        grouped = ", ".join(_ident(k) for k in keys)
        groups, excess = self.rows(f"SELECT count(*), coalesce(sum(n - 1), 0) FROM (SELECT count(*) AS n FROM {view} "
                                   f"GROUP BY {grouped} HAVING count(*) > 1)")[0]
        examples = [dict(zip(keys, map(_iso, row))) for row in self.rows(
            f"SELECT {grouped} FROM {view} GROUP BY {grouped} HAVING count(*) > 1 LIMIT {EXAMPLES}")] if groups else []
        if groups:
            flags.append("DUPLICATE_KEYS")
        return {"key_columns": keys, "groups": int(groups), "excess_rows": int(excess), "examples": examples}

    def _ranges(self, view: str, request: dict[str, Any], e: str | None, t: str, flags: list[str]
                ) -> list[dict[str, Any]]:
        tolerance = _tolerance_days(request.get("source_frequency"))
        history, future = request.get("history_buffer"), request.get("future_buffer")
        out = []
        gaps_total, gap_entities = 0, set()
        for item in request["ranges"]:
            start, end = date.fromisoformat(item["start"]), date.fromisoformat(item["end"])
            inside = f"{t} BETWEEN DATE {_literal(item['start'])} AND DATE {_literal(item['end'])}"
            rows, entities, low, high = self.rows(
                f"SELECT count(*), {f'count(DISTINCT {e})' if e else 'NULL'}, min({t}), max({t}) FROM {view} "
                f"WHERE {inside}")[0]
            entry: dict[str, Any] = {"range_id": item["range_id"], "requested_start": item["start"],
                                     "requested_end": item["end"], "extract_from": item["extract_from"],
                                     "extract_to": item["extract_to"], "actual_start": _iso(low),
                                     "actual_end": _iso(high), "rows": int(rows),
                                     "entities": int(entities) if entities is not None else None}
            if not rows:
                entry["status"] = "EMPTY"
                flags.append("EMPTY_RANGE")
            else:
                first = low if isinstance(low, date) else date.fromisoformat(str(low)[:10])
                last = high if isinstance(high, date) else date.fromisoformat(str(high)[:10])
                late = (first - start).days > tolerance
                early = (min(end, self.reference) - last).days > tolerance
                entry["status"] = "PARTIAL" if late or early else "OK"
                if late or early:
                    flags.append("PARTIAL_RANGE_COVERAGE")
            if e and rows:
                gaps = self.rows(
                    f"WITH cal AS (SELECT DISTINCT {t} AS t FROM {view} WHERE {inside}), "
                    f"ent AS (SELECT {e} AS e, min({t}) AS f, max({t}) AS l, count(DISTINCT {t}) AS n "
                    f"FROM {view} WHERE {inside} GROUP BY 1) "
                    f"SELECT ent.e, count(cal.t) - min(ent.n) AS missing FROM ent JOIN cal ON cal.t BETWEEN ent.f "
                    f"AND ent.l GROUP BY ent.e HAVING count(cal.t) > min(ent.n) ORDER BY missing DESC, ent.e")
                missing = sum(int(g[1]) for g in gaps)
                entry["frequency_gaps"] = {"missing_observations": missing, "entities_with_gaps": len(gaps),
                                           "examples": [{"entity": str(g[0]), "missing": int(g[1])}
                                                        for g in gaps[:EXAMPLES]]}
                gaps_total += missing
                gap_entities.update(str(g[0]) for g in gaps)
                if history:
                    entry["history_buffer"] = self._buffer(view, e, t, history, item["extract_from"], item["start"],
                                                           inside, before=True, flags=flags)
                if future:
                    entry["future_buffer"] = self._buffer(view, e, t, future, item["end"], item["extract_to"],
                                                          inside, before=False, flags=flags)
                    # the window stops at the reference date: observations after it do not exist yet
                    entry["future_buffer"]["capped_at_reference_date"] = bool(item.get("future_capped"))
            out.append(entry)
        if gaps_total:
            flags.append("FREQUENCY_GAPS")
        return out

    def _buffer(self, view: str, e: str, t: str, buffer: dict[str, Any], low: str, high: str, inside: str, *,
                before: bool, flags: list[str]) -> dict[str, Any]:
        """Entities of the range whose observations before (after) it fall short of the buffer."""
        span = f"{t} >= DATE {_literal(low)} AND {t} < DATE {_literal(high)}" if before else \
            f"{t} > DATE {_literal(low)} AND {t} <= DATE {_literal(high)}"
        present = f"SELECT DISTINCT {e} AS e FROM {view} WHERE {inside}"
        if buffer["unit"] == "TRADING_OBSERVATIONS":
            short = self.rows(
                f"SELECT p.e, coalesce(b.n, 0) FROM ({present}) AS p LEFT JOIN (SELECT {e} AS e, count(*) AS n "
                f"FROM {view} WHERE {span} GROUP BY 1) AS b ON b.e = p.e WHERE coalesce(b.n, 0) < {int(buffer['value'])} "
                f"ORDER BY 2, 1")
        else:
            edge = f"min({t})" if before else f"max({t})"
            limit = (date.fromisoformat(low) + timedelta(days=10)) if before else (
                date.fromisoformat(high) - timedelta(days=10))
            compare = ">" if before else "<"
            short = self.rows(
                f"SELECT p.e, b.x FROM ({present}) AS p LEFT JOIN (SELECT {e} AS e, {edge} AS x FROM {view} "
                f"WHERE {span} GROUP BY 1) AS b ON b.e = p.e WHERE b.x IS NULL OR b.x {compare} "
                f"DATE {_literal(limit.isoformat())} ORDER BY 1")
        if short:
            flags.append("HISTORY_BUFFER_SHORTFALL" if before else "FUTURE_BUFFER_SHORTFALL")
        observed = "observations" if buffer["unit"] == "TRADING_OBSERVATIONS" else "edge_date"
        return {"required": buffer, "entities_short": len(short),
                "examples": [{"entity": str(r[0]), observed: int(r[1]) if observed == "observations" else _iso(r[1])}
                             for r in short[:EXAMPLES]]}

    def _ordering(self, view: str, request: dict[str, Any], e: str | None, t: str, flags: list[str]
                  ) -> dict[str, Any]:
        """Dates must not go backwards inside an entity when the delivered order sorts by keys up to the date."""
        order = request.get("order_by") or []
        keys = set(request.get("key_columns") or [])
        prefix = []
        for item in order:
            prefix.append(item)
            if item["column"] == request["time_column"]:
                break
        checkable = bool(prefix) and prefix[-1]["column"] == request["time_column"] and all(
            p["column"] in keys for p in prefix)
        if not checkable or not e:
            return {"checked": False}
        direction = prefix[-1]["direction"]
        wrong = ">" if direction == "ASC" else "<"
        backwards = int(self.scalar(
            f"SELECT count(*) FROM (SELECT {t} AS t, lag({t}) OVER (PARTITION BY filename, {e} "
            f"ORDER BY file_row_number) AS p FROM {view}) WHERE p {wrong} t") or 0)
        if backwards:
            flags.append("INVALID_DATE_ORDERING")
        return {"checked": True, "direction": direction, "backward_steps": backwards}


def main(job_dir: str) -> int:
    with open(os.path.join(job_dir, "profile_request.json"), encoding="utf-8") as handle:
        runtime = json.load(handle)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import confine

    confine.apply(runtime["limits"], runtime.get("cpus"), runtime.get("require_seccomp", True))
    result_dir = os.path.join(job_dir, "result")
    try:
        import duckdb

        settings = runtime["duckdb"]
        connection = duckdb.connect(":memory:", config={
            "memory_limit": f"{settings['memory_limit_mb']}MB", "threads": settings["threads"],
            "temp_directory": settings["temp_directory"], "enable_external_access": True,
            "autoinstall_known_extensions": False, "autoload_known_extensions": False})
        profiler = Profiler(connection, runtime["reference_date"])
        result = {"requests": [profiler.profile(request) for request in runtime["requests"]]}
    except Exception as exc:  # noqa: BLE001 - reported to the harness as a profiler failure
        result = {"profiler_error": f"{type(exc).__name__}: {str(exc)[:400]}"}
    path = os.path.join(result_dir, "quality.json")
    with open(path + ".tmp", "w", encoding="utf-8") as handle:
        json.dump(result, handle, default=str, separators=(",", ":"))
    os.replace(path + ".tmp", path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
