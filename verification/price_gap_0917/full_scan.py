"""Read-only: every stock's whole stored Daily history against TradingView now (adjustment=splits, close and volume).
Per stock: days compared, days whose close differs, the ratio segments, TradingView days missing from storage.
Writes only full_scan.json in the scratchpad."""
import json, sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "idx-price-cron")); sys.path.insert(0, str(ROOT / "verification" / "terminal_api"))
import pgq
from price_update import Symbol, open_socket, request_symbol, start_chart_session
def sql(q):
    for _ in range(4):
        r = pgq.q(q)
        if 'error' not in r: return r['rows']
    raise SystemExit(r['error'][:300])
uni = sql('''select "Company Name","Ticker","TradingView Symbol","Exchange","Security Type" from "IDX_Stock_Universe"
             where not public.is_universe_index("Ticker") order by "Ticker"''')
tick = [u[1] for u in uni]
stored = defaultdict(dict)
for i in range(0, len(tick), 60):
    part = ','.join(f"'{t}'" for t in tick[i:i + 60])
    for t, d, c, v in sql(f'''select ticker, date::date::text, close::float8, volume::float8 from "Price_Stock_Indonesia_IDX"
                             where timeframe='Daily' and is_final and ticker in ({part})'''):
        stored[t][d] = (c, v)
symbols = [Symbol(ordinal=i + 1, company_name=n, ticker=t, tradingview_symbol=s, exchange=e or 'IDX', asset_type=a or 'stock')
           for i, (n, t, s, e, a) in enumerate(uni) if t in stored and s]
print('stocks', len(symbols), 'stored rows', sum(len(v) for v in stored.values()), flush=True)
def work(chunk):
    out, ws, cs = {}, None, None
    for s in chunk:
        for attempt in range(3):
            try:
                if ws is None: ws = open_socket(90, False); cs = start_chart_session(ws)
                rows = request_symbol(ws, cs, s, 5000, 90, date(2026, 10, 31))
                out[s.ticker] = {str(r['date']): (float(r['close']), None if r['volume'] is None else float(r['volume'])) for r in rows}
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
res = {}
for s in symbols:
    t, st, g = s.ticker, stored[s.ticker], tv.get(s.ticker, {})
    if 'error' in g: res[t] = {'error': g['error']}; continue
    days = sorted(d for d in st if d in g)
    segs = []
    for d in days:
        r = round(st[d][0] / g[d][0], 6) if g[d][0] else None
        if not segs or segs[-1][2] != r: segs.append([d, d, r, 1])
        else: segs[-1][1] = d; segs[-1][3] += 1
    lo, hi = min(st), max(st)
    res[t] = {'stored': len(st), 'first': lo, 'last': hi, 'common': len(days),
              'stored_not_in_tv': len(st) - len(days),
              'tv_not_stored': sorted(d for d in g if lo <= d <= hi and d not in st),
              'close_differ_days': sum(1 for d in days if abs(st[d][0] - g[d][0]) > 1e-9 * max(1, abs(st[d][0]))),
              'volume_differ_days': sum(1 for d in days if st[d][1] is not None and g[d][1] is not None and abs(st[d][1] - g[d][1]) > 0.5),
              'segments': segs if len(segs) <= 40 else segs[:20] + [['...', len(segs)]] + segs[-20:]}
json.dump(res, open('full_scan.json', 'w'))
print('done', len(res), 'errors', sum(1 for v in res.values() if 'error' in v))
