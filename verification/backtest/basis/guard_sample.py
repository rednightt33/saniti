"""EXEC-BACKTEST-REVAMP P9: the per-day guard of apps/backtest-worker/src/basis.ts (a Regular-board broker VWAP outside the
session's low and high, 1 % either way) on 40 stocks (every k-th stock trading on 2025-06-02), every session of 2025,
without any factor: how often a clean stock is flagged. Read-only through the pgweb role (credentials from the
environment, as export.sh), one aggregated SELECT per stock.
  PGWEB_HOST=<host> PGWEB_AUTH=<user:password> python3 -I guard_sample.py"""
import json, os, subprocess, sys
def q(sql):
    d = json.loads(subprocess.run(['curl', '-sS', '-m', '120', '-u', os.environ['PGWEB_AUTH'], '--data-urlencode', f'query={sql}',
                                   f'https://{os.environ["PGWEB_HOST"]}/api/query'], capture_output=True, text=True).stdout)
    if 'rows' not in d: raise SystemExit(str(d)[:300])
    return d['rows'] or []
tickers = [r[0] for r in q("SELECT ticker FROM \"Feature_05_Foreign_Domestic_Broker_Detail\" WHERE trade_date = '2025-06-02' AND market_board = 'Regular' GROUP BY ticker ORDER BY ticker")]
sample = tickers[::max(1, len(tickers) // 40)][:40]
acts = {r[0]: r[1] for r in q("SELECT ticker, string_agg(event_type || ' ' || ex_date::text, ', ' ORDER BY ex_date) FROM idx_event_annotation WHERE event_family='CORPORATE_ACTION' AND event_type IN ('STOCK_SPLIT','REVERSE_SPLIT','BONUS_SHARE','RIGHT_ISSUE','STOCK_DIVIDEND') AND ex_date BETWEEN '2025-01-01' AND '2026-11-13' GROUP BY ticker")}
tot = off = 0; bad = []
for t in sample:
    rows = q(f"""SELECT b.trade_date::text, ((sum(b.buy_value)+sum(b.sell_value))/nullif(100*(sum(b.buy_lots)+sum(b.sell_lots)),0))::float8, p.high::float8, p.low::float8
      FROM "Feature_05_Foreign_Domestic_Broker_Detail" b JOIN "Price_Stock_Indonesia_IDX" p ON p.ticker=b.ticker AND p.timeframe='Daily' AND p.is_final AND p.date=b.trade_date
      WHERE b.ticker='{t}' AND b.market_board='Regular' AND b.trade_date BETWEEN '2025-01-01' AND '2025-12-31' GROUP BY b.trade_date, p.high, p.low""")
    n = sum(1 for d, v, h, l in rows if v is not None)
    o = [(d, round(float(v), 2), float(l), float(h)) for d, v, h, l in rows if v is not None and (float(v) > float(h) * 1.01 or float(v) < float(l) * 0.99)]
    tot += n; off += len(o)
    if o: bad.append((t, len(o), n, acts.get(t), o[:2]))
print('tickers', len(sample), 'sessions', tot, 'outside range', off)
for b in bad: print(b)
