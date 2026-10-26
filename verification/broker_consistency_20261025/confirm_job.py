"""Read-only: freshness and AI visibility of Feature 01-06 (stock and INDEX), the live sources of the broker refresh
functions, and per-date consistency of IDX_Broker_Summary -> F05 -> F02 -> F03 and F05 -> F06 over the whole history."""
import json, os, time
from decimal import Decimal
import psycopg
OUT = lambda **k: print("OUT " + json.dumps(k, default=str), flush=True)
FEATURES = ["Feature_01_Stock_Daily", "Feature_02_Broker_Rolling", "Feature_03_Stock_Broker_Daily",
            "Feature_04_Technical_Indicator", "Feature_05_Foreign_Domestic_Broker_Detail", "Feature_06_Foreign_Domestic"]
with psycopg.connect(os.environ["DATABASE_URL"]) as db:
    db.execute("SET default_transaction_read_only = on"); db.execute("SET statement_timeout = '20min'")
    db.execute("SET work_mem = '128MB'")
    # 1 freshness: newest date of every Feature object and its sources (date column from Table_Catalog)
    objs = FEATURES + [f + "_INDEX" for f in FEATURES] + ["IDX_Broker_Summary", "Price_Stock_Indonesia_IDX"]
    for t in objs:
        col = db.execute("""SELECT observation_date_column FROM public."Table_Catalog" WHERE table_schema='public'
                            AND table_name=%s""", (t,)).fetchone()[0]
        newest = db.execute(f'SELECT max("{col}") FROM public."{t}"').fetchone()[0]
        n = db.execute(f'SELECT count(*) FROM public."{t}" WHERE "{col}" = %s', (newest,)).fetchone()[0]
        OUT(q="freshness", table=t, date_column=col, newest=newest, rows_on_newest=n)
    # 2 AI visibility: catalog registration, reader privilege and coverage the AI is told
    for r in db.execute("""SELECT a.table_name, a.is_active, a.ai_access_level, a.time_column,
            has_table_privilege('market_ai_sql_reader', format('public.%I', a.table_name), 'SELECT') AS reader_can_select
        FROM public."AI_table_catalog" a WHERE a.table_name ~ '^Feature_0[1-6]' ORDER BY 1""").fetchall():
        OUT(q="ai_table", row=r)
    for t in FEATURES:
        r = db.execute("SELECT has_table_privilege('market_ai_sql_reader', %s, 'SELECT')", (f'public."{t}"',)).fetchone()[0]
        OUT(q="reader_base_table", table=t, reader_can_select=r)
    for r in db.execute("""SELECT dataset_name, coverage_scope, max(actual_max_date), max(last_checked_at), count(*)
        FROM public."AI_data_coverage" WHERE dataset_name ~ '^Feature_0[1-6]|IDX_Broker_Summary|Price_Stock'
        GROUP BY 1, 2 ORDER BY 1, 2""").fetchall():
        OUT(q="coverage", row=r)
    # 3 live sources of the refresh functions
    for f in ("refresh_feature_05", "refresh_feature_02", "refresh_feature_03_stock_broker_daily", "refresh_feature_06"):
        body = db.execute("SELECT string_agg(pg_get_functiondef(p.oid), ' ') FROM pg_proc p WHERE p.proname = %s", (f,)).fetchone()[0]
        OUT(q="function_sources", function=f, reads={t: t in body for t in ("IDX_Broker_Summary", "Feature_05_Foreign_Domestic_Broker_Detail",
            "Feature_02_Broker_Rolling", "IDX_Broker_Profile")})
    # 4 per-date consistency over the whole history
    def agg(name, q):
        t = time.monotonic(); rows = {r[0]: r[1:] for r in db.execute(q).fetchall()}
        OUT(q="agg_done", name=name, dates=len(rows), seconds=round(time.monotonic() - t, 1)); return rows
    src = agg("broker_summary", '''SELECT "Date", count(*), sum("Buy Value"), sum("Sell Value"), sum("Net Value"),
        sum(buy_freq), count(buy_freq), sum("Net Value") FILTER (WHERE "Investor Type"='Foreign')
        FROM public."IDX_Broker_Summary" GROUP BY 1''')
    f05 = agg("f05", '''SELECT trade_date, count(*), sum(buy_value), sum(sell_value), sum(net_value), sum(buy_freq),
        count(buy_freq), sum(net_value) FILTER (WHERE investor_type='Foreign')
        FROM public."Feature_05_Foreign_Domestic_Broker_Detail" GROUP BY 1''')
    f02 = agg("f02", '''SELECT date, count(*), sum(buy_value_1d), sum(sell_value_1d), sum(net_value_1d),
        count(DISTINCT (ticker, market_board)) FROM public."Feature_02_Broker_Rolling" GROUP BY 1''')
    f03 = agg("f03", '''SELECT date, count(*), sum(total_buy_value), sum(foreign_net_value) + sum(domestic_net_value)
        FROM public."Feature_03_Stock_Broker_Daily" GROUP BY 1''')
    f06 = agg("f06", '''SELECT trade_date, sum(foreign_net_1d), sum(foreign_buy_1d) + sum(domestic_buy_1d)
        FROM public."Feature_06_Foreign_Domestic" GROUP BY 1''')
    def diff(name, a, b, pairs):
        bad = []
        for d in sorted(set(a) | set(b)):
            x, y = a.get(d), b.get(d)
            if x is None or y is None or any((x[i] or 0) != (y[j] or 0) for i, j in pairs):
                bad.append([d, x, y])
        OUT(q="consistency", check=name, dates_a=len(a), dates_b=len(b), differing_dates=len(bad),
            first=min(a) if a else None, last=max(a) if a else None, examples=bad[:3])
    diff("broker_summary_vs_f05 (rows, buy, sell, net, buy_freq, freq_rows, foreign_net)", src, f05, [(i, i) for i in range(7)])
    diff("f05_vs_f02 (rows, buy, sell, net)", f05, f02, [(0, 0), (1, 1), (2, 2), (3, 3)])
    diff("f02_vs_f03 (ticker-board groups, buy, net)", f02, f03, [(4, 0), (1, 1), (3, 2)])
    diff("f05_vs_f06 (foreign net, total buy)", f05, f06, [(6, 0), (1, 1)])
print("JOB_DONE", flush=True)
