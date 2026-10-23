"""NEW_TABLE_ONBOARDING_PLAN.md section 3: an A/B measurement of one candidate index (EXEC-M204 step 4, user
2026-10-23: "uji ... dengan indexing dan tanpa indexing ... which one is faster", "measure cost-wise ... disk dan RAM
... untuk setiap masing-masing query").

One transaction: every pattern runs without the index, the index is built, every pattern runs again with it, then
ROLLBACK (nothing is kept; the table's SHARE lock blocks writers, never readers, for the duration). Each pattern runs
twice per side; both runs are printed (the first shows what came from outside Postgres' cache, the second is warm).
The planner chooses freely, as it does for the SQL Governor.

params.json:
  {"table": "...", "time_column": "trade_date", "entity_column": "ticker",
   "index_sql": "CREATE INDEX ab_candidate ON public.\"...\" (trade_date)",
   "patterns": {"name": {"sql": "SELECT ...", "run": true}}}
  run false: EXPLAIN only on both sides; "WITH_INDEX_ONLY": EXPLAIN only without the index (a pattern too large to
  execute without it, such as a Seq Scan per probe), executed with it. The Governor's verdict shows either way.

Per run: Governor gate from EXPLAIN (largest node rows, a Seq Scan counted as the relation's reltuples, plan cost; the
split it would get under extract.partitioning with the dev limits), execution time, access path, pages from Postgres'
cache (RAM) and pages read from outside it (OS cache or disk), temp pages written and read (sort or hash spill to
disk), peak sort/hash memory, rows returned. For the build: time, index size, WAL written, temp bytes.
Prints OUT lines, then JOB_DONE.
"""
import json
import os
import time

import psycopg
from psycopg.rows import dict_row

SCAN_LIMIT, COST_LIMIT, ROWS_LIMIT = 2_000_000, 600_000, 500_000  # market-sql-governor config.py defaults (dev)
SEQ = {"Seq Scan", "Parallel Seq Scan", "Sample Scan"}
PAGE = 8192

p = json.load(open("params.json"))
table, time_col = p["table"], p["time_column"]


def out(**kv):
    print("OUT " + json.dumps(kv, default=str), flush=True)


def nodes(plan):
    stack, found = [plan], []
    while stack:
        node = stack.pop()
        found.append(node)
        stack.extend(node.get("Plans") or [])
    return found


def mb(pages):
    return round((pages or 0) * PAGE / 1048576, 2)


def time_indexed(conn):
    return bool(conn.execute(
        """SELECT 1 FROM pg_index i JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = i.indkey[0]
           WHERE i.indrelid = to_regclass(%s) AND a.attname = %s AND i.indisvalid LIMIT 1""",
        (f'public."{table}"', time_col)).fetchone())


def gate(plan, reltuples, indexed, days):
    scan = 0
    for n in nodes(plan):
        rows = int(n.get("Plan Rows") or 0)
        if n.get("Node Type") in SEQ and n.get("Relation Name") == table:
            rows = max(rows, reltuples)
        scan = max(scan, rows)
    cost, result = float(plan.get("Total Cost") or 0), int(plan.get("Plan Rows") or 0)
    need = [k for k, v, lim in (("SCAN", scan, SCAN_LIMIT), ("COST", cost, COST_LIMIT), ("ROWS", result, ROWS_LIMIT))
            if v > lim]
    if not need:
        verdict = "APPROVED"
    elif days > 1 and ("SCAN" not in need or indexed):
        verdict = "SPLIT_BY_DATE"
    elif "SCAN" not in need:
        verdict = "SPLIT_BY_ENTITY"
    else:
        verdict = "REJECTED_SCAN_SIZE"
    return {"governor_scan_rows": scan, "plan_cost": round(cost), "planner_rows": result, "over": need,
            "governor": verdict}


def measure(conn, side, reltuples):
    indexed = time_indexed(conn)
    for name, spec in p["patterns"].items():
        q, days = spec["sql"], int(spec.get("days") or 1)
        conn.execute("SAVEPOINT pattern")
        try:
            plan = conn.execute("EXPLAIN (FORMAT JSON) " + q).fetchone()["QUERY PLAN"][0]["Plan"]
            base = {"side": side, "pattern": name, **gate(plan, reltuples, indexed, days)}
            if not spec.get("run", True) or (spec.get("run") == "WITH_INDEX_ONLY" and side == "WITHOUT_INDEX"):
                out(**base, run="EXPLAIN_ONLY", access=sorted({n["Node Type"] + (f" ({n['Index Name']})" if n.get(
                    "Index Name") else "") for n in nodes(plan) if n.get("Relation Name") or n.get("Index Name")}))
                continue
            for attempt in (1, 2):
                conn.execute("SAVEPOINT m")
                try:
                    top = conn.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + q).fetchone()["QUERY PLAN"][0]
                    conn.execute("RELEASE SAVEPOINT m")
                except psycopg.errors.QueryCanceled:
                    conn.execute("ROLLBACK TO SAVEPOINT m")
                    out(**base, run=attempt, error="statement_timeout")
                    break
                pl = top["Plan"]
                ns = nodes(pl)
                peak_kb = max([int(n.get("Peak Memory Usage") or 0) for n in ns]
                              + [int(n.get("Sort Space Used") or 0) for n in ns if n.get("Sort Space Type") == "Memory"]
                              + [0])
                out(**base, run=attempt, ms=round(top.get("Execution Time") or 0, 1), rows=pl.get("Actual Rows"),
                    access=sorted({n["Node Type"] + (f" ({n['Index Name']})" if n.get("Index Name") else "")
                                   for n in ns if n.get("Relation Name") or n.get("Index Name")}),
                    ram_cache_mb=mb(pl.get("Shared Hit Blocks")), read_outside_cache_mb=mb(pl.get("Shared Read Blocks")),
                    io_read_ms=round(float(pl.get("Shared I/O Read Time") or pl.get("I/O Read Time") or 0), 1),
                    temp_written_mb=mb(pl.get("Temp Written Blocks")), temp_read_mb=mb(pl.get("Temp Read Blocks")),
                    peak_work_mem_kb=peak_kb)
        except Exception as e:  # noqa: BLE001
            conn.execute("ROLLBACK TO SAVEPOINT pattern")
            out(side=side, pattern=name, error=f"{type(e).__name__}: {str(e)[:300]}")


with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row, autocommit=True) as conn:
    conn.execute("BEGIN")
    conn.execute("SET LOCAL max_parallel_workers_per_gather = 0")  # as the Governor's session (M201 disabled parallel)
    try:
        conn.execute("SET LOCAL track_io_timing = on")
    except Exception as e:  # noqa: BLE001
        out(note=f"track_io_timing not set: {type(e).__name__}")
    conn.execute("SET LOCAL statement_timeout = '120s'")
    reltuples = int(conn.execute("SELECT reltuples::bigint AS r FROM pg_class WHERE oid = to_regclass(%s)",
                                 (f'public."{table}"',)).fetchone()["r"])
    out(table=table, reltuples=reltuples, time_index_before=time_indexed(conn),
        database_gb=round(conn.execute("SELECT pg_database_size(current_database()) AS s").fetchone()["s"] / 2**30, 1),
        table_mb=round(conn.execute("SELECT pg_relation_size(to_regclass(%s)) AS s", (f'public."{table}"',))
                       .fetchone()["s"] / 1048576))
    measure(conn, "WITHOUT_INDEX", reltuples)
    conn.execute("SET LOCAL statement_timeout = '30min'")
    stat = "SELECT temp_bytes FROM pg_stat_database WHERE datname = current_database()"
    temp0, wal0 = conn.execute(stat).fetchone()["temp_bytes"], conn.execute("SELECT pg_current_wal_lsn() AS l").fetchone()["l"]
    started = time.monotonic()
    conn.execute(p["index_sql"])
    build_s = round(time.monotonic() - started, 1)
    name = p["index_sql"].split("INDEX", 1)[1].split()[0].strip('"')
    size = conn.execute("SELECT pg_relation_size(to_regclass(%s)) AS s", (f"public.{name}",)).fetchone()["s"]
    wal = conn.execute("SELECT pg_wal_lsn_diff(pg_current_wal_lsn(), %s::pg_lsn) AS d", (wal0,)).fetchone()["d"]
    out(build_seconds=build_s, index_mb=round(size / 1048576, 1), wal_mb=round(float(wal) / 1048576, 1),
        temp_bytes_delta_mb=round((conn.execute(stat).fetchone()["temp_bytes"] - temp0) / 1048576, 1))
    conn.execute("SET LOCAL statement_timeout = '120s'")
    measure(conn, "WITH_INDEX", reltuples)
    conn.execute("ROLLBACK")
    out(rolled_back=True, time_index_after=time_indexed(conn))
print("JOB_DONE AB_INDEX", flush=True)
