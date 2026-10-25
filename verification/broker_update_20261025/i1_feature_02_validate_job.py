"""EXEC-INCR-1025 T (part of the parent session): in ONE rolled-back transaction, create refresh_feature_02 and prove
that it rewrites stored historical Feature 02 rows (computed by the full backfill) identically, for sample tickers and
start dates, including a ticker with fewer than 311 earlier sessions (whole-history path). Nothing is kept."""
import json, os, time
import psycopg

MIG = "20261025_008_refresh_feature_02_incremental.sql"
F02 = 'public."Feature_02_Broker_Rolling"'
def out(q, **kw): print("OUT " + json.dumps({"q": q, **kw}, default=str), flush=True)

with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True, application_name="exec-incr-1025-validate") as c:
    c.execute("BEGIN")
    c.execute("SET LOCAL statement_timeout = '60min'"); c.execute("SET LOCAL max_parallel_workers_per_gather = 0")
    body = open(MIG).read(); s = body.find("BEGIN;"); e = body.rstrip().rfind("COMMIT;")
    c.execute(body[s + len("BEGIN;"):e]); out("function_created")
    cols = c.execute("""SELECT string_agg(format('%I', column_name), ',' ORDER BY ordinal_position) FROM information_schema.columns
                        WHERE table_schema='public' AND table_name='Feature_02_Broker_Rolling' AND column_name <> 'calculated_at'""").fetchone()[0]
    pick = lambda sql: (c.execute(sql).fetchone() or [None])[0]
    newest = pick(f"""SELECT ticker FROM (SELECT ticker, min(date) m, count(DISTINCT date) n FROM {F02} WHERE date >= '2025-01-01'
                     GROUP BY 1) x WHERE m > '2025-06-01' AND n BETWEEN 60 AND 300 ORDER BY n DESC LIMIT 1""")
    nego = pick(f"""SELECT ticker FROM {F02} WHERE market_board='Nego' AND date >= '2026-06-01' GROUP BY 1 ORDER BY count(*) DESC LIMIT 1""")
    thin = pick(f"""SELECT ticker FROM {F02} WHERE date >= '2026-01-01' GROUP BY 1 HAVING count(DISTINCT date) BETWEEN 20 AND 60
                   ORDER BY ticker LIMIT 1""")
    warrant = pick(f"""SELECT ticker FROM {F02} WHERE ticker LIKE '%%-W' AND date >= '2026-06-01' GROUP BY 1 ORDER BY count(*) DESC LIMIT 1""")
    cases = [("BBCA", "2026-08-03"), ("BBCA", "2024-01-02"), ("BBRI", "2026-06-02"), ("GOTO", "2026-08-25"),
             ("TLKM", "2020-06-02"), (nego, "2026-07-01"), (thin, "2026-03-02"), (warrant, "2026-08-03"),
             (newest, "2026-08-03"), (newest, None)]
    out("cases", cases=cases)
    bad = 0
    for t, f in cases:
        if not t: continue
        c.execute("SAVEPOINT s")
        lo = f or "1900-01-01"
        c.execute("DROP TABLE IF EXISTS snap")
        c.execute(f"CREATE TEMP TABLE snap AS SELECT {cols} FROM {F02} WHERE ticker=%s AND date >= %s AND date <= '2026-08-31'", (t, lo))
        n = c.execute("SELECT count(*) FROM snap").fetchone()[0]
        t0 = time.monotonic()
        rows = c.execute("SELECT public.refresh_feature_02(%s, %s)", (t, f)).fetchone()[0]
        sec = round(time.monotonic() - t0, 2)
        diff = c.execute(f"""SELECT count(*) FROM ((SELECT {cols} FROM {F02} WHERE ticker=%s AND date >= %s AND date <= '2026-08-31'
                  EXCEPT SELECT * FROM snap) UNION ALL (SELECT * FROM snap EXCEPT SELECT {cols} FROM {F02}
                  WHERE ticker=%s AND date >= %s AND date <= '2026-08-31')) x""", (t, lo, t, lo)).fetchone()[0]
        new = c.execute(f"SELECT count(*), min(date), max(date) FROM {F02} WHERE ticker=%s AND date > '2026-08-31'", (t,)).fetchone()
        src_new = c.execute("""SELECT count(*) FROM public."Feature_05_Foreign_Domestic_Broker_Detail" WHERE ticker=%s AND trade_date > '2026-08-31'""", (t,)).fetchone()[0]
        out("case", ticker=t, p_from=f, stored_rows=n, rewritten=rows, differences=diff, seconds=sec,
            new_rows=new[0], new_range=[new[1], new[2]], source_new_rows=src_new)
        bad += 1 if diff or new[0] != src_new else 0
        c.execute("ROLLBACK TO SAVEPOINT s")
    out("verdict", ok=bad == 0, failing_cases=bad)
    c.execute("ROLLBACK")
print("JOB_DONE", flush=True)
