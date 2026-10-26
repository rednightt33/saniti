"""EXEC-INCR-1025 I2: bring the INDEX Feature tables up to the newest source dates with the formulas of the approved
bootstrap (scripts/backfill_index_features.py), unchanged: prepare() recomputes the whole history in session tables
from IDX_Broker_Summary and the index prices with the production routines cloned, runs the independent F02/F03/F06
checks and requires the accepted 2026-08-31 sample to equal the stored rows; apply_chunks() then upserts each year
with `IS DISTINCT FROM`, reruns it (must modify 0) and compares the table with the payload. Rows that did not change
are not written, so the written count per year shows that historical rows keep their values. archive_and_migrate() is
skipped: migration 20261025_001 is applied and the archive snapshot exists."""
import json, sys, uuid
from datetime import date
sys.path.insert(0, "/job/scripts")
import psycopg
from psycopg.rows import dict_row
import backfill_index_features as b

p = json.load(open("params.json"))
ticker, sample = p["ticker"], date.fromisoformat(p["sample_date"])
import os
with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row, autocommit=True,
                     application_name="exec-incr-1025-index") as db:
    db.execute("SET statement_timeout='20min'"); db.execute("SET lock_timeout='10s'"); db.execute("SET work_mem='64MB'")
    db.execute("SET max_parallel_workers_per_gather=0")
    if not db.execute("SELECT pg_try_advisory_lock(hashtextextended(%s,0)) AS ok", ("index-bulk:" + ticker,)).fetchone()["ok"]:
        raise RuntimeError("Another INDEX writer is active")
    before = {f: db.execute(f'SELECT count(*) AS n, max({"date" if f in (1,2,3) else "trade_date"}) AS last FROM public."{t}_INDEX"').fetchone()
              for f, t in b.BASE.items()}
    b.emit("before", tables=before)
    with db.transaction():
        db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        b.prepare(db, ticker, sample, False)
    b.apply_chunks(db, ticker, uuid.UUID(p["run_id"]))
    after = {f: db.execute(f'SELECT count(*) AS n, max({"date" if f in (1,2,3) else "trade_date"}) AS last FROM public."{t}_INDEX"').fetchone()
             for f, t in b.BASE.items()}
    b.emit("after", tables=after)
    for f, t in b.BASE.items():
        db.execute(f'ANALYZE public."{t}_INDEX"')
print("JOB_DONE", flush=True)
