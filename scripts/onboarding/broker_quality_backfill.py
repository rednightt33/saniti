"""EXEC-LOADER-M217 backfill (go 2026-10-29): remark_broker_summary_date for every IDX_Broker_Summary trade date in
date order (each date's baseline is the earlier dates), one commit per date (Part A item 23: partitioned, never one
long statement). Run as an orc-test-runner job: `run_job.sh scripts/onboarding/broker_quality_backfill.py params.json
<log>` (params.json may be {}). Prints progress, the status counts, the findings per check and the INCOMPLETE dates
with their remark, then JOB_DONE. No secret is printed."""
import json
import os
import time

import psycopg

with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as conn:
    conn.execute("SET application_name = 'broker-quality-backfill'")
    # the distinct dates through the primary key (a loose index scan; no full table scan)
    dates = [r[0] for r in conn.execute('''
        WITH RECURSIVE d AS (SELECT min("Date") AS day FROM public."IDX_Broker_Summary"
            UNION ALL SELECT (SELECT min("Date") FROM public."IDX_Broker_Summary" WHERE "Date" > d.day)
            FROM d WHERE d.day IS NOT NULL)
        SELECT day FROM d WHERE day IS NOT NULL ORDER BY day''').fetchall()]
    print("OUT " + json.dumps({"q": "dates", "n": len(dates), "first": str(dates[0]), "last": str(dates[-1])}), flush=True)
    started = time.monotonic()
    for i, day in enumerate(dates, 1):
        conn.execute("SELECT public.remark_broker_summary_date(%s)", (day,))
        if i % 250 == 0:
            print("OUT " + json.dumps({"q": "progress", "done": i, "seconds": round(time.monotonic() - started)}), flush=True)
    for name, query in (
        ("status", "SELECT status, count(*), min(trade_date)::text, max(trade_date)::text "
                   "FROM public.broker_summary_date_quality GROUP BY 1 ORDER BY 1"),
        ("checks", "SELECT f->>'check', count(*), min(trade_date)::text, max(trade_date)::text FROM "
                   "public.broker_summary_date_quality, jsonb_array_elements(findings) f GROUP BY 1 ORDER BY 1"),
        ("stock_incomplete", "SELECT trade_date::text, remark FROM public.broker_summary_date_quality "
                             "WHERE NOT stock_complete ORDER BY trade_date"),
        ("total", "SELECT count(*) FROM public.broker_summary_date_quality")):
        rows = conn.execute(query).fetchall()
        for j in range(0, max(len(rows), 1), 20):
            print("OUT " + json.dumps({"q": name, "part": j // 20, "rows": rows[j:j + 20]}, default=str), flush=True)
    print("OUT " + json.dumps({"q": "seconds", "total": round(time.monotonic() - started)}), flush=True)
print("JOB_DONE BROKER_QUALITY_BACKFILL", flush=True)
