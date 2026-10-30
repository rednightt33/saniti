"""PRICE-GAP-0917 (read-only): TradingView daily candles (adjustment=splits, as the price job asks) against the stored
Price_Stock_Indonesia_IDX closes, 2026-09-01..2026-10-30, every universe stock. Nothing is written anywhere.
Reports per stock whether the stored neighbours of the gap (09-16, 09-21) equal TradingView, and the TradingView
candles of 09-17/18.

Needs websocket-client and psycopg (the price job's requirements.txt). Usage: python scale_scan.py [OUT.json]"""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'apps' / 'idx-price-cron'))           # the price job's own TradingView client
sys.path.insert(0, str(ROOT / 'verification' / 'terminal_api'))     # pgq: read-only SQL through pgweb
import pgq  # noqa: E402
from price_update import Symbol, open_socket, request_symbol, start_chart_session  # noqa: E402

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('scale_scan.json')   # per-stock detail, kept out of Git
LO, HI = '2026-09-01', '2026-10-30'


def sql(q):
    r = pgq.q(q)
    if 'error' in r:
        raise SystemExit(r['error'][:300])
    return r['rows']


uni = sql('''select "Company Name","Ticker","TradingView Symbol","Exchange","Security Type" from "IDX_Stock_Universe"
             where not public.is_universe_index("Ticker") order by "Ticker"''')
stored = {}
for t, d, c, v in sql(f'''select ticker, date::date::text, close::float8, volume::float8 from "Price_Stock_Indonesia_IDX"
                          where timeframe='Daily' and is_final and date between '{LO}' and '{HI}'
                            and not public.is_universe_index(ticker)'''):
    stored.setdefault(t, {})[d] = (c, v)
symbols = [Symbol(ordinal=i + 1, company_name=n, ticker=t, tradingview_symbol=s, exchange=e or 'IDX', asset_type=a or 'stock')
           for i, (n, t, s, e, a) in enumerate(uni) if t in stored and s]
print('symbols', len(symbols), flush=True)


def work(chunk):
    out, ws, cs = {}, None, None
    for s in chunk:
        for attempt in range(2):
            try:
                if ws is None:
                    ws = open_socket(30, False); cs = start_chart_session(ws)
                rows = request_symbol(ws, cs, s, 50, 30, date(2026, 10, 30))
                out[s.ticker] = {str(r['date']): (float(r['open']), float(r['high']), float(r['low']), float(r['close']),
                                                  None if r['volume'] is None else float(r['volume'])) for r in rows}
                break
            except Exception as exc:
                out[s.ticker] = {'error': f'{type(exc).__name__}: {exc}'[:200]}
                try:
                    ws and ws.close()
                except Exception:
                    pass
                ws = None
    if ws:
        ws.close()
    return out


chunks = [symbols[i::4] for i in range(4)]
tv = {}
with ThreadPoolExecutor(4) as ex:
    for part in ex.map(work, chunks):
        tv.update(part)

res = {}
for s in symbols:
    t, st, got = s.ticker, stored[s.ticker], tv.get(s.ticker, {})
    if 'error' in got:
        res[t] = {'status': 'TV_ERROR', 'error': got['error']}; continue
    ratios = {d: st[d][0] / got[d][3] for d in st if d in got and got[d][3]}
    off = {d: round(r, 6) for d, r in ratios.items() if abs(r - 1) > 1e-9}
    nb = {d: ratios.get(d) for d in ('2026-09-16', '2026-09-21')}
    if any(v is None for v in nb.values()):
        status = 'NO_NEIGHBOUR'
    elif all(abs(v - 1) <= 1e-9 for v in nb.values()):
        status = 'SAME_SCALE'
    else:
        status = 'SCALE_MISMATCH'
    res[t] = {'status': status, 'neighbours': nb, 'off_dates': off, 'stored_dates': len(st), 'common': len(ratios),
              'tv_0917': got.get('2026-09-17'), 'tv_0918': got.get('2026-09-18'),
              'st_0916': st.get('2026-09-16'), 'st_0921': st.get('2026-09-21')}
OUT.write_text(json.dumps(res, indent=1, sort_keys=True))
from collections import Counter  # noqa: E402
print(Counter(v['status'] for v in res.values()))
print('with any off date', sum(1 for v in res.values() if v.get('off_dates')))
