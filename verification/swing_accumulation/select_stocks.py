"""One stock per sector for the swing / broker-accumulation study (rules: user 2026-11-12).
Usage: python3 select_stocks.py [until_date, default = all data]      Read-only through pgq (pgweb); two bounded queries (universe; 24 months of daily OHLCV).
Rules: sector != Undefined; common stock; Screener floor (last close >= 50 and ADV20 >= Rp1 bn, ADV = close x volume) AND ADV60 above the median ADV60 of the floor-passers of that sector;
at least one HIGH -> LOW -> HIGH swing sequence in the window (ZigZag threshold = 5 x the stock's median daily range, rounded to 5%, limited to 15%..50%); BEEF excluded (reference case);
pick = random.Random(11).choice over the sorted candidates of each sector."""
import random, sys
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'terminal_api')); import pgq
UNTIL = sys.argv[1] if len(sys.argv) > 1 else '2999-12-31'; SINCE = '2024-11-01'
u = pgq.q('select "Ticker" t, "Company Name" nm, "Security Type" st, "Is Common Stock" cs, "Sector" sec from public."IDX_Stock_Universe"'); U = pd.DataFrame(u['rows'], columns=u['columns'])
U = U[(U.st == 'stock') & (U.cs == 'Yes') & (U.sec != 'Undefined') & (U.t != 'BEEF')]
q = pgq.q(f"""SELECT ticker t, date::text d, open o, high h, low l, close c, volume v FROM public."Price_Stock_Indonesia_IDX" WHERE timeframe='Daily' AND is_final AND date >= date '{SINCE}' AND date <= date '{UNTIL}' ORDER BY ticker, date""")
if 'error' in q: sys.exit('query refused: ' + q['error'])
P = pd.DataFrame(q['rows'], columns=q['columns'])
for c in 'ohlcv': P[c] = pd.to_numeric(P[c])
latest = P.d.max()


def zigzag(h, l, th):
    piv = []; trend = 0; hi, hi_i, lo, lo_i = h[0], 0, l[0], 0
    for i in range(1, len(h)):
        if h[i] > hi: hi, hi_i = h[i], i
        if l[i] < lo: lo, lo_i = l[i], i
        if trend == 0:
            if h[i] >= lo * (1 + th) and i > lo_i: piv.append((lo_i, 'L')); trend = 1; hi, hi_i = h[i], i
            elif l[i] <= hi * (1 - th) and i > hi_i: piv.append((hi_i, 'H')); trend = -1; lo, lo_i = l[i], i
        elif trend == 1:
            if l[i] <= hi * (1 - th) and i > hi_i: piv.append((hi_i, 'H')); trend = -1; lo, lo_i = l[i], i
        else:
            if h[i] >= lo * (1 + th) and i > lo_i: piv.append((lo_i, 'L')); trend = 1; hi, hi_i = h[i], i
    last = (hi_i, 'H') if trend == 1 else (lo_i, 'L') if trend == -1 else None
    if last and (not piv or last[0] != piv[-1][0]): piv.append(last)
    return piv


rows = []; keep = set(U.t)
for t, g in P.groupby('t'):
    if t not in keep or len(g) < 200 or g.d.max() < (pd.Timestamp(latest) - pd.Timedelta(days=5)).strftime('%Y-%m-%d'): continue
    c, v, h, l = g.c.values, g.v.values, g.h.values, g.l.values; val = c * v; rng = np.median((h - l) / c); th = float(np.clip(round(5 * rng / 0.05) * 0.05, 0.15, 0.50))
    types = ''.join(p[1] for p in zigzag(h, l, th)); rows.append(dict(t=t, close=c[-1], adv20=val[-20:].mean(), adv60=val[-60:].mean(), th=th, pairs=sum(1 for k in range(len(types) - 2) if types[k:k + 3] == 'HLH')))
D = pd.DataFrame(rows).merge(U[['t', 'nm', 'sec']], on='t'); D['floor'] = (D.close >= 50) & (D.adv20 >= 1e9)
D = D.join(D[D.floor].groupby('sec').adv60.median().rename('med60'), on='sec'); D['cand'] = D.floor & (D.adv60 > D.med60) & (D.pairs >= 1)
out = []
for sec, g in sorted(D.groupby('sec')):
    c = sorted(g[g.cand].t); pick = random.Random(11).choice(c) if c else None; r = g[g.t == pick].iloc[0] if pick else None
    out.append([sec, len(c), pick, r.nm[:34] if pick else '', round(r.adv20 / 1e9, 2) if pick else '', round(r.adv60 / 1e9, 2) if pick else '', r.th if pick else ''])
print(f'data terakhir {latest} | jendela {SINCE}..{UNTIL if UNTIL < "2999" else latest}')
print(pd.DataFrame(out, columns=['sektor', 'kandidat', 'terpilih', 'nama', 'ADV20 (Rp mi)', 'ADV60 (Rp mi)', 'ambang swing']).to_string(index=False))
