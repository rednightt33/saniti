"""Turns the pickles of pull_episode_stocks.py into <ticker>_input.json for point_series.ts. Usage: EP_DIR=<dir> python3 prepare_inputs.py [TICKER ...]
The candle list is the stock's own daily price candles; broker rows on dates that are not candles are dropped by the engine (flowRows)."""
import os, sys, json
from pathlib import Path
import pandas as pd
D = os.environ.get('EP_DIR', '.'); tks = [t.upper() for t in sys.argv[1:]] or sorted(set(pd.read_csv(Path(__file__).resolve().parent / 'episodes_step1.csv').tk))
prof = pd.read_pickle(os.path.join(D, 'profile.pkl')); cls = {a: b for a, b in prof.itertuples(index=False) if b}
for tk in tks:
    P = pd.read_pickle(os.path.join(D, f'{tk.lower()}_price.pkl')); B = pd.read_pickle(os.path.join(D, f'{tk.lower()}_broker.pkl'))
    B = B[B.d.isin(set(P.d))]; nn = lambda s: [None if pd.isna(x) else float(x) for x in s]
    rows = [dict(d=r.d, b=r.b, i=r.i, m=r.m, bv=float(r.bv), sv=float(r.sv), bl=float(r.bl), sl=float(r.sl), bf=None if pd.isna(r.bf) else float(r.bf), sf=None if pd.isna(r.sf) else float(r.sf)) for r in B.itertuples(index=False)]
    json.dump(dict(dates=P.d.tolist(), O=P.o.tolist(), H=P.h.tolist(), L=P.l.tolist(), C=P.c.tolist(), V=P.v.tolist(), rows=rows, classification=cls), open(os.path.join(D, f'{tk.lower()}_input.json'), 'w'))
    print(tk, len(P), 'candles', len(rows), 'rows')
