"""EXEC-REFRESH-1025 R1 check: Feature 06 as refreshed incrementally equals a full recomputation (rolled back)."""
import json, os
import psycopg
F06 = 'public."Feature_06_Foreign_Domestic"'
def out(q, **kw): print("OUT " + json.dumps({"q": q, **kw}, default=str), flush=True)
with psycopg.connect(os.environ["DATABASE_URL"], application_name="exec-refresh-1025-r1-check") as c:
    cols = c.execute("""SELECT string_agg(format('%I', column_name), ',') FROM information_schema.columns
                        WHERE table_schema='public' AND table_name='Feature_06_Foreign_Domestic' AND column_name <> 'calculated_at'""").fetchone()[0]
    c.rollback()
    for t in ("BBCA", "BBRI", "MIKA", "GOTO", "TLKM", "ANTM", "BUMI"):
        c.execute("SET LOCAL statement_timeout = '30min'"); c.execute("SET LOCAL max_parallel_workers_per_gather = 0")
        c.execute(f"CREATE TEMP TABLE before ON COMMIT DROP AS SELECT {cols} FROM {F06} WHERE ticker = %s", (t,))
        n_new = c.execute("SELECT count(*) FROM before WHERE trade_date >= '2026-09-01'").fetchone()[0]
        c.execute("SELECT public.refresh_feature_06(%s, NULL)", (t,))
        diff = c.execute(f"""SELECT count(*) FROM ((SELECT {cols} FROM {F06} WHERE ticker=%s EXCEPT SELECT * FROM before)
              UNION ALL (SELECT * FROM before EXCEPT SELECT {cols} FROM {F06} WHERE ticker=%s)) x""", (t, t)).fetchone()[0]
        n = c.execute("SELECT count(*) FROM before").fetchone()[0]
        c.rollback()
        out("f06_incremental_equals_full", ticker=t, rows=n, rows_since_2026_09_01=n_new, differences=diff)
print("JOB_DONE", flush=True)
