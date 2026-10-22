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
    print(json.dumps({"event": event, "at": dt.datetime.utcnow().isoformat(timespec="seconds"), **fields},
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


TASKS = {"phase1_backfill": phase1_backfill}


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
