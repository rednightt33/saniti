"""Read-only: every OHLCV field, TradingView now vs stored, 2026-08-03..2026-10-30, all universe stocks; the six
mismatching stocks also over their whole stored history. Writes only ohlcv_scan.json in the scratchpad."""
import json, sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'apps' / 'idx-price-cron')); sys.path.insert(0, str(ROOT / 'verification' / 'terminal_api'))
import pgq
from price_update import Symbol, open_socket, request_symbol, start_chart_session
SIX = ['AHAP', 'BUVA', 'ENRG', 'FORU', 'PBSA', 'VKTR']
def sql(q):
    r = pgq.q(q)
    if 'error' in r: raise SystemExit(r['error'][:300])
    return r['rows']
uni = sql('''select "Company Name","Ticker","TradingView Symbol","Exchange","Security Type" from "IDX_Stock_Universe"
             where not public.is_universe_index("Ticker") order by "Ticker"''')
stored = defaultdict(dict)
for t, d, o, h, l, c, v in sql('''select ticker, date::date::text, open::float8, high::float8, low::float8, close::float8, volume::float8
     from "Price_Stock_Indonesia_IDX" where timeframe='Daily' and is_final and date between '2026-08-03' and '2026-10-30'
     and not public.is_universe_index(ticker)'''):
    stored[t][d] = (o, h, l, c, v)
for t, d, o, h, l, c, v in sql('''select ticker, date::date::text, open::float8, high::float8, low::float8, close::float8, volume::float8
     from "Price_Stock_Indonesia_IDX" where timeframe='Daily' and is_final and ticker in (%s)''' % ','.join(f"'{x}'" for x in SIX)):
    stored[t][d] = (o, h, l, c, v)
symbols = [Symbol(ordinal=i + 1, company_name=n, ticker=t, tradingview_symbol=s, exchange=e or 'IDX', asset_type=a or 'stock')
           for i, (n, t, s, e, a) in enumerate(uni) if t in stored and s]
def work(chunk):
    out, ws, cs = {}, None, None
    for s in chunk:
        bars = 5000 if s.ticker in SIX else 70
        for attempt in range(2):
            try:
                if ws is None: ws = open_socket(60, False); cs = start_chart_session(ws)
                rows = request_symbol(ws, cs, s, bars, 60, date(2026, 10, 30))
                out[s.ticker] = {str(r['date']): (float(r['open']), float(r['high']), float(r['low']), float(r['close']),
                                 None if r['volume'] is None else float(r['volume'])) for r in rows}
                break
            except Exception as exc:
                out[s.ticker] = {'error': f'{type(exc).__name__}: {exc}'[:200]}
                try: ws and ws.close()
                except Exception: pass
                ws = None
    if ws: ws.close()
    return out
tv = {}
with ThreadPoolExecutor(4) as ex:
    for part in ex.map(work, [symbols[i::4] for i in range(4)]): tv.update(part)
json.dump({'stored': stored, 'tv': tv}, open('ohlcv_scan.json', 'w'))
print('fetched', len(tv), 'errors', sum(1 for v in tv.values() if 'error' in v))
