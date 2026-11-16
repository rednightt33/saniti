"""Step 2 of the point-behaviour study: pull PRICE and BROKER data for the stocks of episodes_step1.csv (read-only, through pgq / pgweb, statement_timeout 30 s).
Usage: EP_DIR=<dir> python3 pull_episode_stocks.py [TICKER ...]   (default: every stock in episodes_step1.csv)
Price: Price_Stock_Indonesia_IDX daily final from 2023-01-02. Broker: IDX_Broker_Summary, every board and both investor types, with buy_freq / sell_freq, from 2023-01-02, pulled in half-year ranges that split in
halves when a query is refused (timeout). Broker classification: IDX_Broker_Profile (one small query). Writes <dir>/<ticker>_price.pkl, <ticker>_broker.pkl and <dir>/profile.pkl; prints rows and seconds per stock."""
import os, sys, time
from pathlib import Path
from datetime import date, timedelta
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'terminal_api')); import pgq
OUT = os.environ.get('EP_DIR', '.'); SINCE = date(2023, 1, 2); END = date(2027, 1, 1)
tks = [t.upper() for t in sys.argv[1:]] or sorted(set(pd.read_csv(Path(__file__).resolve().parent / 'episodes_step1.csv').tk))


def rng_pull(tk, a, b, depth=0):
    """broker rows of tk with a <= Date < b; split the range in halves on any refusal"""
    q = pgq.q(f"""SELECT "Date"::text d, "Broker" b, "Investor Type" i, "Market Board" m, "Buy Value" bv, "Sell Value" sv, "Buy Lots" bl, "Sell Lots" sl, buy_freq bf, sell_freq sf FROM public."IDX_Broker_Summary" WHERE "Symbol"='{tk}' AND "Date" >= date '{a}' AND "Date" < date '{b}'""")
    if 'error' in q:
        days = (b - a).days
        if days <= 7 or depth >= 4: sys.exit(f'{tk} {a}..{b}: refused even in small ranges: {q["error"]}')
        mid = a + timedelta(days=days // 2); print(f'   {tk} {a}..{b} refused ({q["error"][:60]}), splitting', flush=True)
        return pd.concat([rng_pull(tk, a, mid, depth + 1), rng_pull(tk, mid, b, depth + 1)])
    return pd.DataFrame(q['rows'], columns=q['columns'])


for tk in tks:
    if not tk.isalnum(): sys.exit('bad ticker')
    t0 = time.time()
    q = pgq.q(f"""SELECT date::text d, open o, high h, low l, close c, volume v FROM public."Price_Stock_Indonesia_IDX" WHERE ticker='{tk}' AND timeframe='Daily' AND is_final AND date >= date '{SINCE}' ORDER BY date""")
    P = pd.DataFrame(q['rows'], columns=q['columns'])
    for c in 'ohlcv': P[c] = pd.to_numeric(P[c])
    parts = []; a = SINCE
    while a < END:
        b = date(a.year + (a.month + 5) // 12, (a.month + 5) % 12 + 1, 1); parts.append(rng_pull(tk, a, min(b, END))); a = b
    B = pd.concat(parts, ignore_index=True)
    for c in ('bv', 'sv', 'bl', 'sl', 'bf', 'sf'): B[c] = pd.to_numeric(B[c])
    P.to_pickle(os.path.join(OUT, f'{tk.lower()}_price.pkl')); B.to_pickle(os.path.join(OUT, f'{tk.lower()}_broker.pkl'))
    print(f'{tk} | {time.time() - t0:.0f}s | {len(P)} candles {P.d.min()}..{P.d.max()} | {len(B)} broker rows {B.d.min()}..{B.d.max()} | boards {B.m.value_counts().to_dict()} | freq filled {100 * B.bf.notna().mean():.0f}%', flush=True)
q = pgq.q('SELECT broker_code, broker_classification FROM public."IDX_Broker_Profile"'); pd.DataFrame(q['rows'], columns=q['columns']).to_pickle(os.path.join(OUT, 'profile.pkl')); print('profile rows', len(q['rows']))
