"""EXEC-INCR-1025 I1: Feature 02 from 2026-09-01 for every ticker with new Feature 05 rows (refresh_feature_02, proven
equal to the full calculation), then Feature 03 per new date (refresh_feature_03_stock_broker_daily), ANALYZE, checks:
F02 rows = source rows for the range; F03 rows = F02 (ticker, board, date) groups; F02 new rows equal a full-history
rewrite for sample tickers (rolled back). Resumable: a ticker whose F02 already reaches its newest F05 date is skipped;
F03 dates are rewritten idempotently."""
import json, os, time
import psycopg

A, B = "2026-09-01", "2026-10-24"
F02 = 'public."Feature_02_Broker_Rolling"'; F03 = 'public."Feature_03_Stock_Broker_Daily"'
F05 = 'public."Feature_05_Foreign_Domestic_Broker_Detail"'
def out(q, **kw): print("OUT " + json.dumps({"q": q, **kw}, default=str), flush=True)
def conn(): return psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=30, application_name="exec-incr-1025-f02")
t_all = time.monotonic()
with conn() as c:
    todo = [r[0] for r in c.execute(f"""SELECT n.ticker FROM (SELECT ticker, max(trade_date) m FROM {F05} WHERE trade_date >= %s GROUP BY 1) n
        LEFT JOIN LATERAL (SELECT date FROM {F02} x WHERE x.ticker = n.ticker ORDER BY date DESC LIMIT 1) o ON true
        WHERE o.date IS NULL OR o.date < n.m ORDER BY 1""", (A,))]
out("f02_start", tickers=len(todo))
total = 0; slow = []
for i, t in enumerate(todo, 1):
    t0 = time.monotonic()
    with conn() as c:
        c.execute("SET LOCAL statement_timeout = '30min'"); c.execute("SET LOCAL max_parallel_workers_per_gather = 0")
        c.execute("SET LOCAL work_mem = '64MB'")
        total += c.execute("SELECT public.refresh_feature_02(%s, %s)", (t, A)).fetchone()[0]
        c.commit()
    s = time.monotonic() - t0
    if s > 60: slow.append((t, round(s, 1)))
    if i % 100 == 0 or i == len(todo): out("f02_progress", done=i, of=len(todo), rows_total=total, elapsed=round(time.monotonic() - t_all, 1))
out("f02_done", tickers=len(todo), rows_total=total, slow=slow[:20])
with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as c:
    c.execute(f"ANALYZE {F02}")
with conn() as c:
    c.execute("SET LOCAL statement_timeout = '30min'")
    src, f02n = c.execute(f"SELECT (SELECT count(*) FROM {F05} WHERE trade_date >= %s AND trade_date < %s), (SELECT count(*) FROM {F02} WHERE date >= %s AND date < %s)", (A, B, A, B)).fetchone()
    out("f02_rows_vs_source", source_rows=src, f02_rows=f02n, ok=src == f02n)
    dates = [r[0] for r in c.execute(f"SELECT DISTINCT trade_date FROM {F05} WHERE trade_date >= %s AND trade_date < %s ORDER BY 1", (A, B))]
f03_total = 0
for d in dates:
    with conn() as c:
        c.execute("SET LOCAL statement_timeout = '30min'"); c.execute("SET LOCAL max_parallel_workers_per_gather = 0")
        f03_total += c.execute("SELECT public.refresh_feature_03_stock_broker_daily(%s, NULL)", (d,)).fetchone()[0]
        c.commit()
out("f03_done", dates=len(dates), rows_total=f03_total)
with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as c:
    c.execute(f"ANALYZE {F03}")
with conn() as c:
    c.execute("SET LOCAL statement_timeout = '30min'")
    groups, f03n = c.execute(f"""SELECT (SELECT count(*) FROM (SELECT DISTINCT date, ticker, market_board FROM {F02} WHERE date >= %s AND date < %s) g),
                                 (SELECT count(*) FROM {F03} WHERE date >= %s AND date < %s)""", (A, B, A, B)).fetchone()
    out("f03_rows_vs_f02_groups", f02_groups=groups, f03_rows=f03n, ok=groups == f03n)
    cols = c.execute("""SELECT string_agg(format('%I', column_name), ',' ORDER BY ordinal_position) FROM information_schema.columns
                        WHERE table_schema='public' AND table_name='Feature_02_Broker_Rolling' AND column_name <> 'calculated_at'""").fetchone()[0]
    c.rollback()
    for t in ("BBCA", "BBRI", "GOTO", "PSAT", "TLKM"):
        c.execute("SET LOCAL statement_timeout = '30min'"); c.execute("SET LOCAL max_parallel_workers_per_gather = 0")
        c.execute(f"CREATE TEMP TABLE snap ON COMMIT DROP AS SELECT {cols} FROM {F02} WHERE ticker=%s AND date >= '2026-06-01'", (t,))
        c.execute("SELECT public.refresh_feature_02(%s, '2026-06-01')", (t,))
        diff = c.execute(f"""SELECT count(*) FROM ((SELECT {cols} FROM {F02} WHERE ticker=%s AND date >= '2026-06-01' EXCEPT SELECT * FROM snap)
              UNION ALL (SELECT * FROM snap EXCEPT SELECT {cols} FROM {F02} WHERE ticker=%s AND date >= '2026-06-01')) x""", (t, t)).fetchone()[0]
        n = c.execute("SELECT count(*), count(*) FILTER (WHERE date >= %s) FROM snap", (A,)).fetchone()
        c.rollback()
        out("f02_new_rows_equal_longer_rewrite", ticker=t, rows=n[0], new_rows=n[1], differences=diff)
    out("newest", f02=c.execute(f"SELECT date FROM {F02} ORDER BY date DESC LIMIT 1").fetchone()[0],
        f03=c.execute(f"SELECT date FROM {F03} ORDER BY date DESC LIMIT 1").fetchone()[0],
        db_gb=c.execute("SELECT round(pg_database_size(current_database())/1e9,2)").fetchone()[0])
out("elapsed", seconds=round(time.monotonic() - t_all, 1))
print("JOB_DONE", flush=True)
