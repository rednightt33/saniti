"""Read-only pull for ONE stock: daily OHLCV and every broker row (all boards, both investor types) from a start date.
Usage: SWING_DATA_DIR=<dir> python3 pull_stock.py TICKER [from_date, default 2025-06-01]
Goes through verification/terminal_api/pgq.py (pgweb, role pgweb, read-only, statement_timeout 30 s); the query is bounded by symbol and date.
Writes <dir>/<ticker>_price.pkl (d,o,h,l,c,v) and <dir>/<ticker>_broker.pkl (d,b,inv,mb,bv,sv,bl,sl)."""
import os, sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'terminal_api')); import pgq
tk = sys.argv[1].upper(); since = sys.argv[2] if len(sys.argv) > 2 else '2025-06-01'; out = os.environ.get('SWING_DATA_DIR', '.')
if not tk.isalnum() or len(since) != 10: sys.exit('ticker must be alphanumeric and from_date YYYY-MM-DD')
q = pgq.q(f"""SELECT date::text d, open o, high h, low l, close c, volume v FROM public."Price_Stock_Indonesia_IDX" WHERE ticker='{tk}' AND timeframe='Daily' AND is_final AND date >= date '{since}' ORDER BY date""")
P = pd.DataFrame(q['rows'], columns=q['columns'])
for c in 'ohlcv': P[c] = pd.to_numeric(P[c])
q = pgq.q(f"""SELECT "Date"::text d, "Broker" b, "Investor Type" inv, "Market Board" mb, "Buy Value" bv, "Sell Value" sv, "Buy Lots" bl, "Sell Lots" sl FROM public."IDX_Broker_Summary" WHERE "Symbol"='{tk}' AND "Date" >= date '{since}'""")
if 'error' in q: sys.exit('query refused: ' + q['error'])
B = pd.DataFrame(q['rows'], columns=q['columns'])
for c in ('bv', 'sv', 'bl', 'sl'): B[c] = pd.to_numeric(B[c])
P.to_pickle(os.path.join(out, f'{tk.lower()}_price.pkl')); B.to_pickle(os.path.join(out, f'{tk.lower()}_broker.pkl'))
print(tk, len(P), 'candles', P.d.min(), '..', P.d.max(), '|', len(B), 'broker rows', B.d.min(), '..', B.d.max(), '| boards', B.mb.value_counts().to_dict())
