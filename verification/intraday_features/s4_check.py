#!/usr/bin/env python3
"""EXEC-INTRADAY-FEATURES S4: the first daily run of idx-intraday-cron with the feature step (2026-11-02), read-only
through pgweb. Checks: the session in the bars for the 4 timeframes, the feature queue empty of PENDING/FAILED, the
Feature 04 state at the session for the stocks that traded, and Feature 01/04 rows equal to the stock bars per timeframe
(the session and the whole table). Usage: python3 s4_check.py 2026-11-02"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'terminal_api'))
import pgq  # noqa: E402

day = sys.argv[1]
STOCK = "NOT public.is_universe_index(ticker)"
checks = {
    'bars_session': f"""SELECT timeframe, count(*) bars, count(DISTINCT ticker) tickers,
        count(*) FILTER (WHERE {STOCK}) stock_bars, min(bar_time) first, max(bar_time) last
        FROM public.price_stock_idx_intraday WHERE session_date = '{day}' GROUP BY 1 ORDER BY 1""",
    'queue': """SELECT timeframe, status, count(*) n, max(done_at) last_done, max(attempts) max_attempts
        FROM public.intraday_feature_queue GROUP BY 1, 2 ORDER BY 1, 2""",
    'state_vs_traded': f"""WITH traded AS (SELECT DISTINCT ticker, timeframe FROM public.price_stock_idx_intraday
                         WHERE session_date = '{day}' AND {STOCK})
        SELECT t.timeframe, count(*) traded,
               count(*) FILTER (WHERE (s.last_bar_time AT TIME ZONE 'Asia/Jakarta')::date = '{day}') state_on_day,
               count(*) FILTER (WHERE s.ticker IS NULL) no_state
        FROM traded t LEFT JOIN public.feature04_intraday_state s USING (ticker, timeframe) GROUP BY 1 ORDER BY 1""",
    'rows_session': f"""SELECT b.timeframe, b.n stock_bars, f1.n f01, f4.n f04 FROM
        (SELECT timeframe, count(*) n FROM public.price_stock_idx_intraday WHERE session_date = '{day}' AND {STOCK} GROUP BY 1) b
        LEFT JOIN (SELECT timeframe, count(*) n FROM public."Feature_01_Stock_Intraday" WHERE session_date = '{day}' GROUP BY 1) f1 USING (timeframe)
        LEFT JOIN (SELECT timeframe, count(*) n FROM public."Feature_04_Technical_Indicator_Intraday" WHERE session_date = '{day}' GROUP BY 1) f4 USING (timeframe)
        ORDER BY 1""",
    'rows_total': f"""SELECT b.timeframe, b.n stock_bars, f1.n f01, f4.n f04 FROM
        (SELECT timeframe, count(*) n FROM public.price_stock_idx_intraday WHERE {STOCK} GROUP BY 1) b
        LEFT JOIN (SELECT timeframe, count(*) n FROM public."Feature_01_Stock_Intraday" GROUP BY 1) f1 USING (timeframe)
        LEFT JOIN (SELECT timeframe, count(*) n FROM public."Feature_04_Technical_Indicator_Intraday" GROUP BY 1) f4 USING (timeframe)
        ORDER BY 1""",
}
for name, sql in checks.items():
    r = pgq.q(sql)
    print(f'== {name} ({r["_ms"]} ms)')
    pgq.show(r)
