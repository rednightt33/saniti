"""EXEC-REFRESH-1025 R1: Feature 05 for 2026-09-01..2026-10-23 from IDX_Broker_Summary, then Feature 06 per ticker
from 2026-09-01 (refresh_feature_06 incremental, 312-session base), ANALYZE, reconcile and incremental=full samples.
Resumable: F05 is skipped when it already equals the source for the range; a ticker whose Feature 06 already reaches
its newest Feature 05 date is skipped. Prints OUT/ERR lines and JOB_DONE; no secret is printed."""
import json, os, sys, time
import psycopg

A, B = "2026-09-01", "2026-10-24"
F05 = 'public."Feature_05_Foreign_Domestic_Broker_Detail"'
F06 = 'public."Feature_06_Foreign_Domestic"'
DIFF = f"""SELECT (SELECT count(*) FROM public."IDX_Broker_Summary" WHERE "Date" >= %(a)s AND "Date" < %(b)s),
  (SELECT count(*) FROM {F05} WHERE trade_date >= %(a)s AND trade_date < %(b)s),
  (SELECT count(*) FROM public."IDX_Broker_Summary" b LEFT JOIN {F05} f
     ON f.ticker=b."Symbol" AND f.trade_date=b."Date" AND f.broker=b."Broker" AND f.investor_type=b."Investor Type" AND f.market_board=b."Market Board"
   WHERE b."Date" >= %(a)s AND b."Date" < %(b)s
     AND (f.ticker IS NULL OR f.buy_value<>b."Buy Value" OR f.sell_value<>b."Sell Value" OR f.buy_lots<>b."Buy Lots"
          OR f.sell_lots<>b."Sell Lots" OR f.buy_freq IS DISTINCT FROM b.buy_freq OR f.sell_freq IS DISTINCT FROM b.sell_freq))"""
RECON = f"""WITH s AS (
    SELECT trade_date, ticker, market_board,
           coalesce(sum(buy_value) FILTER (WHERE investor_type='Foreign'),0) fb, coalesce(sum(sell_value) FILTER (WHERE investor_type='Foreign'),0) fs,
           coalesce(sum(buy_value) FILTER (WHERE investor_type='Domestic'),0) db, coalesce(sum(sell_value) FILTER (WHERE investor_type='Domestic'),0) ds,
           sum(buy_freq) FILTER (WHERE investor_type='Foreign') bf, sum(sell_freq) FILTER (WHERE investor_type='Domestic') dsf
    FROM {F05} WHERE trade_date >= %(a)s AND trade_date < %(b)s GROUP BY 1,2,3)
SELECT count(*), count(*) FILTER (WHERE f.ticker IS NULL OR f.foreign_buy_1d<>s.fb OR f.foreign_sell_1d<>s.fs OR f.domestic_buy_1d<>s.db
           OR f.domestic_sell_1d<>s.ds OR f.foreign_net_1d<>s.fb-s.fs OR f.domestic_net_1d<>s.db-s.ds
           OR (s.bf IS NOT NULL AND f.foreign_buy_freq_1d IS DISTINCT FROM s.bf) OR (s.dsf IS NOT NULL AND f.domestic_sell_freq_1d IS DISTINCT FROM s.dsf)),
       (SELECT count(*) FROM {F06} WHERE trade_date >= %(a)s AND trade_date < %(b)s)
FROM s LEFT JOIN {F06} f USING (trade_date, ticker, market_board)"""

def out(q, **kw): print("OUT " + json.dumps({"q": q, **kw}, default=str), flush=True)
def conn(): return psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=30, application_name="exec-refresh-1025-r1")

started = time.monotonic()
with conn() as c:
    c.execute("SET LOCAL statement_timeout = '60min'"); c.execute("SET LOCAL max_parallel_workers_per_gather = 0")
    before = c.execute(DIFF, {"a": A, "b": B}).fetchone()
    out("f05_before", source_rows=before[0], f05_rows=before[1], differing=before[2])
    if before[2] == 0 and before[0] == before[1]:
        out("f05_skip", reason="already equals the source")
    else:
        t0 = time.monotonic()
        rows = c.execute("SELECT public.refresh_feature_05(%s, %s)", (A, B)).fetchone()[0]
        after = c.execute(DIFF, {"a": A, "b": B}).fetchone()
        if after[2] != 0 or after[0] != after[1] or rows != after[0]:
            c.rollback(); out("f05_failed", rows=rows, after=after); print("JOB_DONE"); sys.exit(1)
        c.commit(); out("f05_refreshed", rows=rows, source_rows=after[0], seconds=round(time.monotonic()-t0, 1))
with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as c:
    t0 = time.monotonic(); c.execute(f"ANALYZE {F05}"); out("f05_analyze", seconds=round(time.monotonic()-t0, 1))

with conn() as c:
    todo = [r[0] for r in c.execute(f"""SELECT n.ticker FROM (SELECT ticker, max(trade_date) m FROM {F05} WHERE trade_date >= %s GROUP BY 1) n
        LEFT JOIN LATERAL (SELECT trade_date FROM {F06} x WHERE x.ticker = n.ticker ORDER BY trade_date DESC LIMIT 1) o ON true
        WHERE o.trade_date IS NULL OR o.trade_date < n.m ORDER BY 1""", (A,))]
out("f06_start", tickers=len(todo))
total = 0; slow = []
for i, t in enumerate(todo, 1):
    t0 = time.monotonic()
    with conn() as c:
        c.execute("SET LOCAL statement_timeout = '30min'"); c.execute("SET LOCAL max_parallel_workers_per_gather = 0")
        total += c.execute("SELECT public.refresh_feature_06(%s, %s)", (t, A)).fetchone()[0]
        c.commit()
    sec = time.monotonic() - t0
    if sec > 20: slow.append((t, round(sec, 1)))
    if i % 100 == 0 or i == len(todo): out("f06_progress", done=i, of=len(todo), rows_total=total, elapsed=round(time.monotonic()-started, 1))
out("f06_done", tickers=len(todo), rows_total=total, slow=slow[:20])
with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as c:
    c.execute(f"ANALYZE {F06}")

with conn() as c:
    c.execute("SET LOCAL statement_timeout = '60min'"); c.execute("SET LOCAL max_parallel_workers_per_gather = 0")
    groups, differing, f06_rows = c.execute(RECON, {"a": A, "b": B}).fetchone()
    out("f06_reconcile", f05_groups=groups, f06_rows=f06_rows, differing=differing, ok=differing == 0 and groups == f06_rows)
    cols = c.execute("""SELECT string_agg(format('%%I', column_name), ',') FROM information_schema.columns
                        WHERE table_schema='public' AND table_name='Feature_06_Foreign_Domestic' AND column_name <> 'calculated_at'""").fetchone()[0]
# incremental (as refreshed) equals a full recomputation, rolled back
for t in ("BBCA", "BBRI", "MIKA", "GOTO", "TLKM"):
    with conn() as c:
        c.execute("SET LOCAL statement_timeout = '30min'"); c.execute("SET LOCAL max_parallel_workers_per_gather = 0")
        if not c.execute(f"SELECT 1 FROM {F06} WHERE ticker=%s AND trade_date >= %s LIMIT 1", (t, A)).fetchone():
            out("f06_full_check_skip", ticker=t); continue
        c.execute(f"CREATE TEMP TABLE before ON COMMIT DROP AS SELECT {cols} FROM {F06} WHERE ticker = %s", (t,))
        c.execute("SELECT public.refresh_feature_06(%s, NULL)", (t,))
        diff = c.execute(f"""SELECT count(*) FROM ((SELECT {cols} FROM {F06} WHERE ticker=%s EXCEPT SELECT * FROM before)
              UNION ALL (SELECT * FROM before EXCEPT SELECT {cols} FROM {F06} WHERE ticker=%s)) x""", (t, t)).fetchone()[0]
        n = c.execute("SELECT count(*) FROM before").fetchone()[0]
        c.rollback()
    out("f06_incremental_equals_full", ticker=t, rows=n, differences=diff)
with conn() as c:
    out("newest", f05=c.execute(f"SELECT trade_date FROM {F05} ORDER BY trade_date DESC LIMIT 1").fetchone()[0],
        f06=c.execute(f"SELECT trade_date FROM {F06} ORDER BY trade_date DESC LIMIT 1").fetchone()[0],
        db_gb=c.execute("SELECT round(pg_database_size(current_database())/1e9,2)").fetchone()[0])
out("elapsed", seconds=round(time.monotonic()-started, 1))
print("JOB_DONE", flush=True)
