"""NEW_TABLE_ONBOARDING_PLAN.md section 3 (index acceptance): measure the query patterns the SQL Governor will run on a
table to onboard, judged the way the Governor judges them, and print a PASS/FAIL verdict per pattern. Read-only.

params.json:
  {"table": "Feature_06_Foreign_Domestic", "entity_column": "ticker", "time_column": "trade_date",
   "entity": "BBCA", "filters": {"market_board": "Regular"}, "expected_rows_next_year": 2800000}
  entity        a busy entity for P1 (default: the one with the most rows on the newest date);
  filters       equality filters every pattern carries (a board, an asset type, a metric), as the AI sends them;
  expected_rows_next_year  the table's size a year from now (default: today's rows).

Patterns:
  P1 one entity, the last 365 days     P2 every entity on the newest date (cross-section)
  P3 every entity, the last 7 days     P4 every entity, the last 365 days (the date split's case; not executed)
  P5 the query_metric calendar: summary.calendar_sql, the 20 newest dates; since 2026-10-23 the Governor EXPLAINs it
     first and refuses it above the cost or scan limit (CALENDAR_NOT_INDEXED, M204)
For P1-P4: the Governor's gate from EXPLAIN (largest node rows, a Seq Scan counted as the whole relation, plan cost;
governor.py _explain), EXPLAIN (ANALYZE, BUFFERS) time and access path (P1-P3), and an unordered count(*) within the
Governor's count limit and cap (_counted, G15: at most SQL_MAX_DATASET_ROWS + 1 rows).

Verdict (Governor defaults, market-sql-governor config.py, live on dev 2026-10-22; evidence in
DATABASE_INDEX_ACCEPTANCE.md 2026-10-22):
  FAIL  scan estimate > 2,000,000 or plan cost > 600,000 while no index leads with the time column (the Governor
        cannot split it by date: REJECTED_SCAN_SIZE / REJECTED_COMPUTE_COST); P1-P3 run longer than 10,000 ms (half of
        the 20 s statement_timeout); a count longer than 7,000 ms (the estimate falls back to the planner,
        ROW_ESTIMATE_UNCERTAIN); P5 longer than 1,000 ms or with a Seq Scan;
  WARN  a Seq Scan of a table above 1,000,000 rows; scan or cost above the limit but splittable by date.
  Table FAIL when it holds or will hold more than 2,000,000 rows, or P5 fails, and no index leads with the time
  column: add the narrow (time_column) index and measure every pattern again before and after, because a date index
  can make cross-sections slower on a table stored in entity order (F02 against F05).
A view is judged like the Governor judges it: a Seq Scan counts the base relation the plan names, at its own
reltuples; the table's rows are an exact count within 30 s, else the planner estimate (OUT rows_source).
Prints `OUT`, `VERDICT {json}` per pattern and one `VERDICT_TABLE` line, then JOB_DONE.
"""
import datetime as dt
import json
import os
import time

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

SCAN_LIMIT = 2_000_000
COST_LIMIT = 600_000
COUNT_LIMIT_MS = 7_000
ROWS_COUNT_LIMIT_MS = 30_000
COUNT_CAP = 500_001  # SQL_MAX_DATASET_ROWS (default 500,000; unset on dev 2026-10-23) + 1
EXEC_LIMIT_MS = 10_000
CALENDAR_LIMIT_MS = 1_000
SEQ_SCAN_WARN_ROWS = 1_000_000
SEQ_SCAN_NODES = {"Seq Scan", "Parallel Seq Scan", "Sample Scan"}

LEADING_SQL = """
WITH obj AS (
    SELECT c.oid FROM pg_catalog.pg_class AS c JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relname = %s
), base AS (
    SELECT obj.oid AS relid, NULL::smallint AS attnum FROM obj
    UNION
    SELECT d.refobjid, d.refobjsubid
    FROM pg_catalog.pg_rewrite AS r JOIN obj ON r.ev_class = obj.oid
    JOIN pg_catalog.pg_depend AS d ON d.classid = 'pg_catalog.pg_rewrite'::regclass AND d.objid = r.oid
        AND d.refclassid = 'pg_catalog.pg_class'::regclass AND d.refobjid <> obj.oid AND d.refobjsubid > 0
)
SELECT DISTINCT a.attname AS column_name
FROM base
JOIN pg_catalog.pg_index AS i ON i.indrelid = base.relid AND i.indisvalid
JOIN pg_catalog.pg_attribute AS a ON a.attrelid = i.indrelid AND a.attnum = i.indkey[0]
WHERE base.attnum IS NULL OR base.attnum = i.indkey[0]
"""

p = json.load(open("params.json"))
table, entity_col, time_col = p["table"], p["entity_column"], p["time_column"]
filters = p.get("filters") or {}
T, E, D = sql.Identifier(table), sql.Identifier(entity_col), sql.Identifier(time_col)


def where(*extra):
    parts = [sql.SQL("{} = {}").format(sql.Identifier(k), sql.Literal(v)) for k, v in filters.items()] + list(extra)
    return sql.SQL(" AND ").join(parts) if parts else sql.SQL("TRUE")


def nodes(plan):
    stack, found = [plan], []
    while stack:
        node = stack.pop()
        found.append(node)
        stack.extend(node.get("Plans") or [])
    return found


def first(row):
    return list(row.values())[0]


with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row, autocommit=True,
                     options="-c default_transaction_read_only=on -c statement_timeout=60000"
                             " -c max_parallel_workers_per_gather=0") as conn:
    relation_rows: dict[str, int] = {}

    def reltuples_of(name):
        # the Governor's RELTUPLES_SQL (governor.py _explain): a Seq Scan reads the whole relation it names, which for
        # a view is a base table, not the view itself
        if name not in relation_rows:
            found = conn.execute("SELECT reltuples::bigint FROM pg_class WHERE oid = to_regclass(%s)",
                                 (f'public."{name}"',)).fetchone()
            relation_rows[name] = max(int(first(found) or 0), 0) if found else 0
        return relation_rows[name]

    def seq_scans(plan_nodes):
        return [n for n in plan_nodes if n["Node Type"] in SEQ_SCAN_NODES and n.get("Relation Name")]

    reltuples = reltuples_of(table)
    # exact count within ROWS_COUNT_LIMIT_MS; a view over a large table (Feature 05 stock view, 45 million base rows)
    # cannot be counted in time, so the planner's estimate stands in and rows_source says which one was used
    try:
        with conn.transaction():
            conn.execute(sql.SQL("SET LOCAL statement_timeout = {}").format(sql.Literal(ROWS_COUNT_LIMIT_MS)))
            rows_now = first(conn.execute(sql.SQL("SELECT count(*) FROM public.{}").format(T)).fetchone())
        rows_source = "count"
    except psycopg.errors.QueryCanceled:
        with conn.transaction():
            estimate = first(conn.execute(sql.SQL("EXPLAIN (FORMAT JSON) SELECT * FROM public.{}").format(T))
                             .fetchone())[0]["Plan"]
        rows_now, rows_source = int(estimate.get("Plan Rows") or 0), "planner_estimate"
    # one step down the date index, as the Governor reads it (governor.py newest_sql, M207): max() through a view
    # that joins reads every row
    newest = first(conn.execute(sql.SQL("SELECT {d} FROM public.{t} WHERE {w} AND {d} IS NOT NULL ORDER BY {d} DESC "
                                        "LIMIT 1").format(d=D, t=T, w=where())).fetchone())
    entity = p.get("entity") or first(conn.execute(sql.SQL(
        "SELECT {e} FROM public.{t} WHERE {w} GROUP BY 1 ORDER BY count(*) DESC LIMIT 1").format(
        e=E, t=T, w=where(sql.SQL("{} = {}").format(D, sql.Literal(newest))))).fetchone())
    # the SQL Governor's own lookup (market-sql-governor governor.py INDEX_LEADING_SQL): a view counts the indexes of
    # the base columns it reads (M205)
    leading = {r["column_name"] for r in conn.execute(LEADING_SQL, (table,)).fetchall()}
    time_indexed = time_col in leading
    print("OUT " + json.dumps({"table": table, "rows": rows_now, "rows_source": rows_source, "reltuples": reltuples,
                               "newest": newest,
                               "entity": entity, "index_leading_columns": sorted(leading),
                               "time_index_available": time_indexed, "filters": filters}, default=str), flush=True)
    day = sql.Literal(newest)
    patterns = {
        "P1_one_entity_365d": where(sql.SQL("{} = {}").format(E, sql.Literal(entity)),
                                    sql.SQL("{} >= {} - 365").format(D, day)),
        "P2_cross_section_newest": where(sql.SQL("{} = {}").format(D, day)),
        "P3_all_entities_7d": where(sql.SQL("{} > {} - 7").format(D, day)),
        "P4_all_entities_365d": where(sql.SQL("{} > {} - 365").format(D, day)),
    }
    verdicts = []
    for name, condition in patterns.items():
        select = sql.SQL("SELECT * FROM public.{} WHERE {} ORDER BY {}, {}").format(T, condition, E, D)
        result, fail, warn = {"pattern": name}, [], []
        try:
            with conn.transaction():
                plan = first(conn.execute(sql.SQL("EXPLAIN (FORMAT JSON) {}").format(select)).fetchone())[0]["Plan"]
            scan = 0
            for node in nodes(plan):
                rows = int(node.get("Plan Rows") or 0)
                if node.get("Node Type") in SEQ_SCAN_NODES and node.get("Relation Name"):
                    rows = max(rows, reltuples_of(node["Relation Name"]))
                scan = max(scan, rows)
            result.update(governor_scan_estimate=scan, planner_result_rows=int(plan.get("Plan Rows") or 0),
                          plan_cost=round(float(plan.get("Total Cost") or 0)))
            if name != "P4_all_entities_365d":
                with conn.transaction():
                    top = first(conn.execute(sql.SQL("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {}").format(select))
                                .fetchone())[0]
                plan_nodes = nodes(top["Plan"])
                result.update(
                    execution_ms=round(top.get("Execution Time") or 0, 1),
                    access=sorted({n["Node Type"] + (f" ({n['Index Name']})" if n.get("Index Name") else "")
                                   for n in plan_nodes if n.get("Relation Name") or n.get("Index Name")}),
                    shared_hit=top["Plan"].get("Shared Hit Blocks"), shared_read=top["Plan"].get("Shared Read Blocks"),
                    seq_scan=[n["Relation Name"] for n in seq_scans(plan_nodes)
                              if reltuples_of(n["Relation Name"]) > SEQ_SCAN_WARN_ROWS])
            started = time.monotonic()
            try:
                with conn.transaction():
                    conn.execute(sql.SQL("SET LOCAL statement_timeout = {}").format(sql.Literal(COUNT_LIMIT_MS)))
                    # G15 (governor.py _counted): unordered and capped at SQL_MAX_DATASET_ROWS + 1, so a count stops
                    # once the request must be split; the parts are then counted one by one
                    counted = first(conn.execute(sql.SQL("SELECT count(*) FROM (SELECT 1 FROM public.{} WHERE {} "
                                                         "LIMIT {}) c").format(T, condition, sql.Literal(COUNT_CAP)))
                                    .fetchone())
                result.update(counted_rows=counted, count_ms=round((time.monotonic() - started) * 1000))
            except psycopg.errors.QueryCanceled:
                result.update(counted_rows=None, count_timed_out=True)
        except Exception as e:  # noqa: BLE001
            result["error"] = f"{type(e).__name__}: {str(e)[:300]}"
            fail.append("query failed")
        over = [g for g, v, lim in (("scan", result.get("governor_scan_estimate"), SCAN_LIMIT),
                                    ("cost", result.get("plan_cost"), COST_LIMIT)) if (v or 0) > lim]
        if over:
            (warn if time_indexed else fail).append(
                f"{'/'.join(over)} above the Governor limit; " + ("split by date (time index present)" if time_indexed
                                                                  else "no index leads with the time column, so no date split"))
        if result.get("count_timed_out"):
            fail.append(f"count above {COUNT_LIMIT_MS} ms (falls back to the planner estimate)")
        if (result.get("execution_ms") or 0) > EXEC_LIMIT_MS:
            fail.append(f"execution {result['execution_ms']} ms above {EXEC_LIMIT_MS} ms")
        if result.get("seq_scan"):
            warn.append(f"Seq Scan of a table above {SEQ_SCAN_WARN_ROWS} rows: {', '.join(result['seq_scan'])}")
        result.update(verdict="FAIL" if fail else "PASS", fail=fail, warn=warn)
        verdicts.append(result)
        print("VERDICT " + json.dumps(result, default=str), flush=True)
    # P5: the query_metric calendar (market-sql-governor summary.calendar_sql), 20 newest dates, not EXPLAIN-gated
    calendar = sql.SQL(
        "WITH RECURSIVE cal(d) AS ((SELECT {c} FROM public.{t} WHERE {c} <= %s ORDER BY {c} DESC LIMIT 1) UNION ALL "
        "SELECT (SELECT {c} FROM public.{t} WHERE {c} < cal.d ORDER BY {c} DESC LIMIT 1) FROM cal WHERE cal.d >= %s) "
        "SELECT d FROM cal WHERE d IS NOT NULL AND d >= %s LIMIT %s").format(c=D, t=T)
    earliest = newest - dt.timedelta(days=60) if isinstance(newest, dt.date) else newest
    args = (newest, earliest, earliest, 20)
    result, fail = {"pattern": "P5_calendar_20_dates"}, []
    try:
        with conn.transaction():
            plan = first(conn.execute(sql.SQL("EXPLAIN (FORMAT JSON) {}").format(calendar), args).fetchone())[0]["Plan"]
        largest = max([reltuples_of(n["Relation Name"]) for n in seq_scans(nodes(plan))] or [0])
        seq = largest > SEQ_SCAN_WARN_ROWS  # a small lookup (the stock universe a view filters on) is no finding
        result.update(seq_scan=seq, plan_cost=round(float(plan.get("Total Cost") or 0)))
        if result["plan_cost"] > COST_LIMIT:
            # the Governor's calendar gate (governor.py Summarizer._gate_calendar, M204) refuses it before it runs
            fail.append(f"calendar plan cost {result['plan_cost']} above {COST_LIMIT}: the Governor refuses "
                        "query_metric on this table (CALENDAR_NOT_INDEXED)")
        if seq and largest > SCAN_LIMIT:
            fail.append("Seq Scan per probed date on a table above the scan limit (not run, M204)")
        else:
            with conn.transaction():
                top = first(conn.execute(sql.SQL("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {}").format(calendar), args)
                            .fetchone())[0]
            result.update(execution_ms=round(top.get("Execution Time") or 0, 1),
                          shared_hit=top["Plan"].get("Shared Hit Blocks"))
            if result["execution_ms"] > CALENDAR_LIMIT_MS:
                fail.append(f"calendar {result['execution_ms']} ms above {CALENDAR_LIMIT_MS} ms (no time-led index, M204)")
            if seq:
                fail.append("calendar uses a Seq Scan")
    except Exception as e:  # noqa: BLE001
        result["error"] = f"{type(e).__name__}: {str(e)[:300]}"
        fail.append("query failed")
    result.update(verdict="FAIL" if fail else "PASS", fail=fail, warn=[])
    verdicts.append(result)
    print("VERDICT " + json.dumps(result, default=str), flush=True)

    expected = int(p.get("expected_rows_next_year") or rows_now)
    needs_time_index = max(rows_now, expected) > SCAN_LIMIT or result["verdict"] == "FAIL"
    reasons = [f"{v['pattern']}: {'; '.join(v['fail'])}" for v in verdicts if v["verdict"] == "FAIL"]
    if needs_time_index and not time_indexed:
        reasons.append(f"no index leads with {time_col}: add the narrow ({time_col}) index and measure every pattern "
                       "again before and after (a date index can slow cross-sections)")
    print("VERDICT_TABLE " + json.dumps({"table": table, "verdict": "FAIL" if reasons else "PASS",
                                         "time_index_required": needs_time_index, "time_index_present": time_indexed,
                                         "reasons": reasons}), flush=True)
print("JOB_DONE MEASURE", flush=True)
