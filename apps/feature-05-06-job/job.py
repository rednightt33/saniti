"""EXEC-F05-F06 one-off job: applies the Feature 05/06 migrations and runs their backfills and checks.

Runs as a temporary Railway service (restart NEVER, only a ${{Postgres.DATABASE_URL}} reference) because the
working session cannot reach PostgreSQL directly. JOB_TASKS is a comma-separated list of tasks run in order;
every task logs one JSON line per step and stops the job on the first failed check.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

import psycopg

SQL_DIR = Path(__file__).with_name("sql")
FIRST_MONTH = dt.date(2016, 1, 1)


def log(event: str, **fields) -> None:
    print(json.dumps({"event": event, "at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), **fields},
                     default=str), flush=True)


def connect(autocommit: bool = False) -> psycopg.Connection:
    return psycopg.connect(os.environ["DATABASE_URL"], autocommit=autocommit,
                           application_name="feature-05-06-job")


def months(start: dt.date, end_exclusive: dt.date):
    m = start.replace(day=1)
    while m < end_exclusive:
        nxt = (m.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
        yield m, nxt
        m = nxt


def migrate(name: str) -> None:
    sql = (SQL_DIR / name).read_text(encoding="utf-8")
    started = time.monotonic()
    with connect() as conn:
        conn.execute(sql)
        conn.commit()
    log("migration_applied", file=name, seconds=round(time.monotonic() - started, 1))


BS_MONTH_FACTS = """
SELECT count(*), coalesce(sum("Buy Value"),0), coalesce(sum("Sell Value"),0),
       coalesce(sum("Buy Lots"),0), coalesce(sum("Sell Lots"),0),
       count(buy_freq), count(sell_freq)
FROM public."IDX_Broker_Summary" WHERE "Date" >= %s AND "Date" < %s
"""
FREQ_MISMATCH = """
SELECT count(*) FILTER (WHERE b.buy_freq IS DISTINCT FROM f.buy_freq OR b.sell_freq IS DISTINCT FROM f.sell_freq),
       count(*)
FROM public."IDX_Broker_Summary" b
JOIN public."IDX_Broker_Summary_Freq" f
  ON f.trade_date = b."Date" AND f.symbol = b."Symbol" AND f.broker = b."Broker"
 AND f.investor_type::text = b."Investor Type" AND f.market_board::text = b."Market Board"
WHERE b."Date" >= %s AND b."Date" < %s AND f.trade_date >= %s AND f.trade_date < %s
"""


def phase1_backfill() -> None:
    """Per month: facts before, sync, facts after; values and row counts must not change and every joined key must
    equal Freq. A failed check rolls the month back and stops the job. VACUUM after each year reuses the space."""
    with connect() as conn:
        last = conn.execute('SELECT max("Date") FROM public."IDX_Broker_Summary"').fetchone()[0]
    end = (last.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    total_started = time.monotonic()
    year_done = None
    for a, b in months(FIRST_MONTH, end):
        started = time.monotonic()
        with connect() as conn:
            conn.execute("SET LOCAL statement_timeout = '30min'")
            before = conn.execute(BS_MONTH_FACTS, (a, b)).fetchone()
            written = conn.execute("SELECT public.sync_broker_summary_freq(%s, %s)", (a, b)).fetchone()[0]
            after = conn.execute(BS_MONTH_FACTS, (a, b)).fetchone()
            mismatch, joined = conn.execute(FREQ_MISMATCH, (a, b, a, b)).fetchone()
            ok = before[:5] == after[:5] and mismatch == 0 and after[5] == joined and after[6] == joined
            if not ok:
                conn.rollback()
                log("phase1_month_failed", month=a, before=before, after=after, mismatch=mismatch, joined=joined)
                sys.exit(1)
            conn.commit()
        log("phase1_month", month=a, rows=after[0], written=written, with_freq=after[5],
            without_freq=after[0] - after[5], seconds=round(time.monotonic() - started, 1))
        if b.year != a.year or b >= end:
            vstart = time.monotonic()
            with connect(autocommit=True) as conn:
                conn.execute('VACUUM (ANALYZE) public."IDX_Broker_Summary"')
            log("phase1_vacuum", year=a.year, seconds=round(time.monotonic() - vstart, 1))
    with connect() as conn:
        conn.execute("SET LOCAL statement_timeout = '60min'")
        conn.execute('ALTER TABLE public."IDX_Broker_Summary" VALIDATE CONSTRAINT "IDX_Broker_Summary_freq_nonnegative_check"')
        conn.commit()
    log("phase1_done", seconds=round(time.monotonic() - total_started, 1))


F05_CHECK = """
SELECT (SELECT count(*) FROM public."IDX_Broker_Summary" WHERE "Date" >= %(a)s AND "Date" < %(b)s),
       (SELECT count(*) FROM public.feature_05_foreign_domestic_broker_detail WHERE trade_date >= %(a)s AND trade_date < %(b)s),
       (SELECT count(*) FROM public."IDX_Broker_Summary" b
        LEFT JOIN public.feature_05_foreign_domestic_broker_detail f
          ON f.ticker = b."Symbol" AND f.trade_date = b."Date" AND f.broker = b."Broker"
         AND f.investor_type = b."Investor Type" AND f.market_board = b."Market Board"
        WHERE b."Date" >= %(a)s AND b."Date" < %(b)s
          AND (f.ticker IS NULL OR f.buy_value <> b."Buy Value" OR f.sell_value <> b."Sell Value"
               OR f.buy_lots <> b."Buy Lots" OR f.sell_lots <> b."Sell Lots"
               OR f.buy_freq IS DISTINCT FROM b.buy_freq OR f.sell_freq IS DISTINCT FROM b.sell_freq))
"""


def years(start: dt.date, end_exclusive: dt.date):
    y = start.year
    while dt.date(y, 1, 1) < end_exclusive:
        yield dt.date(y, 1, 1), dt.date(y + 1, 1, 1)
        y += 1


# Sequential scans; no parallel workers: a parallel hash needs dynamic shared memory, and the Postgres container's
# /dev/shm is too small for it ("could not resize shared memory segment", 2026-10-22 Fase 2 first run).
SEQ_SCAN = ("SET LOCAL enable_indexscan = off", "SET LOCAL enable_bitmapscan = off",
            "SET LOCAL max_parallel_workers_per_gather = 0")


def phase2_backfill() -> None:
    """Feature 05 per year with sequential scans (Fase 1 showed month-by-index reads of IDX_Broker_Summary are
    random I/O, ~190 s a month); every year must equal IDX_Broker_Summary row for row before it commits. Rows are
    written ticker-ordered so Feature 06 reads a ticker from few heap ranges. Re-running a year replaces it (idempotent)."""
    with connect() as conn:
        last = conn.execute('SELECT max("Date") FROM public."IDX_Broker_Summary"').fetchone()[0]
    end = (last.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    total_started = time.monotonic()
    for a, b in years(FIRST_MONTH, end):
        started = time.monotonic()
        with connect() as conn:
            conn.execute("SET LOCAL statement_timeout = '120min'")
            conn.execute("SET LOCAL work_mem = '64MB'")
            for stmt in SEQ_SCAN:
                conn.execute(stmt)
            written = conn.execute("SELECT public.refresh_feature_05(%s, %s)", (a, b)).fetchone()[0]
            bs_rows, f05_rows, differing = conn.execute(F05_CHECK, {"a": a, "b": b}).fetchone()
            if bs_rows != f05_rows or differing != 0 or written != bs_rows:
                conn.rollback()
                log("phase2_year_failed", year=a.year, bs_rows=bs_rows, f05_rows=f05_rows, differing=differing)
                sys.exit(1)
            conn.commit()
        log("phase2_year", year=a.year, rows=f05_rows, seconds=round(time.monotonic() - started, 1))
    with connect(autocommit=True) as conn:
        conn.execute("VACUUM (ANALYZE) public.feature_05_foreign_domestic_broker_detail")
    log("phase2_done", seconds=round(time.monotonic() - total_started, 1))


def phase3_backfill() -> None:
    """Feature 06 for every ticker, full history, one transaction per ticker; resumable (tickers that already have
    Feature 06 rows are skipped). Afterwards every month of Feature 06 must equal the Feature 05 daily sums."""
    total_started = time.monotonic()
    with connect() as conn:
        tickers = [r[0] for r in conn.execute(
            "SELECT DISTINCT ticker FROM public.feature_05_foreign_domestic_broker_detail ORDER BY 1")]
        done = {r[0] for r in conn.execute("SELECT DISTINCT ticker FROM public.feature_06_foreign_domestic")}
    todo = [t for t in tickers if t not in done]
    log("phase3_start", tickers=len(tickers), already_done=len(done), todo=len(todo))
    rows_total = 0
    for i, t in enumerate(todo, 1):
        started = time.monotonic()
        with connect() as conn:
            conn.execute("SET LOCAL statement_timeout = '30min'")
            rows = conn.execute("SELECT public.refresh_feature_06(%s)", (t,)).fetchone()[0]
            conn.commit()
        rows_total += rows
        seconds = time.monotonic() - started
        if i % 50 == 0 or seconds > 30 or i == len(todo):
            log("phase3_progress", done=i, of=len(todo), ticker=t, rows=rows, seconds=round(seconds, 1),
                rows_total=rows_total, elapsed=round(time.monotonic() - total_started, 1))
    with connect(autocommit=True) as conn:
        conn.execute("VACUUM (ANALYZE) public.feature_06_foreign_domestic")
    phase3_reconcile()
    log("phase3_done", seconds=round(time.monotonic() - total_started, 1))


F06_RECONCILE = """
WITH s AS (
    SELECT trade_date, ticker, market_board,
           coalesce(sum(buy_value) FILTER (WHERE investor_type = 'Foreign'), 0) AS fb,
           coalesce(sum(sell_value) FILTER (WHERE investor_type = 'Foreign'), 0) AS fs,
           coalesce(sum(buy_value) FILTER (WHERE investor_type = 'Domestic'), 0) AS db,
           coalesce(sum(sell_value) FILTER (WHERE investor_type = 'Domestic'), 0) AS ds,
           sum(buy_freq) FILTER (WHERE investor_type = 'Foreign') AS bf,
           sum(sell_freq) FILTER (WHERE investor_type = 'Domestic') AS dsf
    FROM public.feature_05_foreign_domestic_broker_detail
    WHERE trade_date >= %(a)s AND trade_date < %(b)s
    GROUP BY 1, 2, 3)
SELECT count(*), count(*) FILTER (WHERE f.ticker IS NULL OR f.foreign_buy_1d <> s.fb OR f.foreign_sell_1d <> s.fs
           OR f.domestic_buy_1d <> s.db OR f.domestic_sell_1d <> s.ds
           OR f.foreign_net_1d <> s.fb - s.fs OR f.domestic_net_1d <> s.db - s.ds
           OR (s.bf IS NOT NULL AND f.foreign_buy_freq_1d IS DISTINCT FROM s.bf)
           OR (s.dsf IS NOT NULL AND f.domestic_sell_freq_1d IS DISTINCT FROM s.dsf)),
       (SELECT count(*) FROM public.feature_06_foreign_domestic WHERE trade_date >= %(a)s AND trade_date < %(b)s)
FROM s LEFT JOIN public.feature_06_foreign_domestic f USING (trade_date, ticker, market_board)
"""


def phase3_reconcile() -> None:
    with connect() as conn:
        last = conn.execute("SELECT max(trade_date) FROM public.feature_05_foreign_domestic_broker_detail").fetchone()[0]
    end = (last.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    bad = 0
    for a, b in years(FIRST_MONTH, end):
        with connect() as conn:
            conn.execute("SET LOCAL statement_timeout = '120min'")
            conn.execute("SET LOCAL work_mem = '64MB'")
            for stmt in SEQ_SCAN:
                conn.execute(stmt)
            groups, differing, f06_rows = conn.execute(F06_RECONCILE, {"a": a, "b": b}).fetchone()
        ok = differing == 0 and groups == f06_rows
        bad += 0 if ok else 1
        log("phase3_reconcile_year", year=a.year, f05_groups=groups, f06_rows=f06_rows, differing=differing, ok=ok)
    if bad:
        log("phase3_reconcile_failed", months=bad)
        sys.exit(1)


def validate_samples() -> None:
    """Independent pandas recalculation of every Feature 06 field for sample tickers, then incremental refreshes
    from several dates compared with the stored full calculation (rolled back, nothing changes)."""
    import check_feature_06_sample as chk
    import pandas as pd
    with connect() as conn:
        nego = conn.execute("""SELECT ticker FROM public.feature_06_foreign_domestic WHERE market_board = 'Nego'
                               GROUP BY 1 ORDER BY count(*) DESC LIMIT 1""").fetchone()[0]
        newest = (conn.execute("""SELECT ticker FROM public.feature_06_foreign_domestic GROUP BY 1
                                  HAVING min(trade_date) > '2025-06-01' ORDER BY count(*) DESC LIMIT 1""").fetchone()
                  or [None])[0]
    with connect() as conn:
        present = {r[0] for r in conn.execute("SELECT DISTINCT ticker FROM public.feature_06_foreign_domestic")}
    samples = [t for t in dict.fromkeys(["BBCA", "BBRI", "MIKA", "XSPI", "ISAP-W", nego, newest]) if t in present]
    failed = []
    for t in samples:
        with connect() as conn:
            f05 = pd.DataFrame(conn.execute(
                "SELECT trade_date, market_board, investor_type, buy_value, sell_value, buy_lots, sell_lots, "
                "buy_freq, sell_freq, source_balance_gap FROM public.feature_05_foreign_domestic_broker_detail "
                "WHERE ticker = %s", (t,)).fetchall(),
                columns=["trade_date", "market_board", "investor_type", "buy_value", "sell_value", "buy_lots",
                         "sell_lots", "buy_freq", "sell_freq", "source_balance_gap"])
            cur = conn.execute("SELECT * FROM public.feature_06_foreign_domestic WHERE ticker = %s", (t,))
            got = pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])
        got = got.drop(columns=["ticker", "calculated_at"])
        ok = chk.compare(chk.compute(f05), got)
        log("validate_sample", ticker=t, rows=len(got), ok=ok)
        if not ok:
            failed.append(t)
    cols_sql = """SELECT string_agg(format('%I', column_name), ',') FROM information_schema.columns
                  WHERE table_name = 'feature_06_foreign_domestic' AND column_name <> 'calculated_at'"""
    for t in [x for x in dict.fromkeys(["BBCA", "MIKA", nego]) if x in present]:
        for back in (1, 21, 400):
            with connect() as conn:
                conn.execute("SET LOCAL statement_timeout = '30min'")
                cols = conn.execute(cols_sql).fetchone()[0]
                start = conn.execute("""SELECT min(d) FROM (SELECT DISTINCT trade_date d
                    FROM public.feature_06_foreign_domestic WHERE ticker = %s ORDER BY d DESC LIMIT %s) x""",
                                     (t, back)).fetchone()[0]
                conn.execute(f"CREATE TEMP TABLE before ON COMMIT DROP AS SELECT {cols} FROM "
                             "public.feature_06_foreign_domestic WHERE ticker = %s", (t,))
                began = time.monotonic()
                rows = conn.execute("SELECT public.refresh_feature_06(%s, %s)", (t, start)).fetchone()[0]
                seconds = time.monotonic() - began
                diff = conn.execute(f"""SELECT count(*) FROM (
                    (SELECT {cols} FROM public.feature_06_foreign_domestic WHERE ticker = %s EXCEPT SELECT * FROM before)
                    UNION ALL (SELECT * FROM before EXCEPT SELECT {cols} FROM public.feature_06_foreign_domestic
                               WHERE ticker = %s)) x""", (t, t)).fetchone()[0]
                conn.rollback()
            log("validate_incremental", ticker=t, sessions_back=back, start=start, rewrote=rows,
                seconds=round(seconds, 3), differences=diff)
            if diff:
                failed.append(f"{t}@{start}")
    if failed:
        log("validate_failed", failed=failed)
        sys.exit(1)


def measure() -> None:
    """Plans and sizes recorded in DATABASE_CHANGELOG (no change)."""
    with connect() as conn:
        for label, sql in (
            ("f05_incremental_read", """EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
                SELECT trade_date, market_board, sum(buy_value) FROM public.feature_05_foreign_domestic_broker_detail
                WHERE ticker = 'BBCA' AND trade_date >= (SELECT min(d) FROM (SELECT DISTINCT trade_date d
                  FROM public.feature_05_foreign_domestic_broker_detail WHERE ticker = 'BBCA' ORDER BY d DESC LIMIT 313) x)
                GROUP BY 1, 2"""),
            ("f06_ticker_read", """EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
                SELECT * FROM public.feature_06_foreign_domestic WHERE ticker = 'BBCA' AND market_board = 'Regular'
                AND trade_date >= '2026-01-01'"""),
            ("f06_date_cross_section", """EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
                SELECT ticker, foreign_net_20d FROM public.feature_06_foreign_domestic
                WHERE trade_date = (SELECT max(trade_date) FROM public.feature_06_foreign_domestic)
                AND market_board = 'Regular'"""),
        ):
            plan = [r[0] for r in conn.execute(sql)]
            log("measure_plan", label=label, plan=plan)
        sizes = conn.execute("""SELECT relname, pg_total_relation_size(oid), pg_relation_size(oid)
            FROM pg_class WHERE relname IN ('IDX_Broker_Summary', 'feature_05_foreign_domestic_broker_detail',
                                            'feature_06_foreign_domestic')""").fetchall()
        log("measure_sizes", sizes=sizes, database=conn.execute("SELECT pg_database_size(current_database())").fetchone()[0])


TASKS = {"phase1_backfill": phase1_backfill, "phase2_backfill": phase2_backfill, "phase3_backfill": phase3_backfill,
         "phase3_reconcile": phase3_reconcile, "validate_samples": validate_samples, "measure": measure}


def main() -> None:
    tasks = [t.strip() for t in os.environ.get("JOB_TASKS", "").split(",") if t.strip()]
    log("job_start", tasks=tasks)
    for task in tasks:
        if task.startswith("migrate:"):
            migrate(task.split(":", 1)[1])
        elif task in TASKS:
            TASKS[task]()
        else:
            log("unknown_task", task=task)
            sys.exit(2)
    log("job_done")


if __name__ == "__main__":
    main()
