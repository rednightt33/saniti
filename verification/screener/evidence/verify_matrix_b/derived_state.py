# verify_matrix_b: are the "start-independent" derived states of cumulative rows really start-independent?
# state = level > MA(level, n) on the same bars, MA = SMA or EMA (SMA seed, as indicators.ts ema / prototype xEMA).
import json, os, numpy as np
D = os.path.dirname(os.path.abspath(__file__))
def sma(x, n):
    o = np.full(len(x), np.nan); c = np.cumsum(np.insert(x, 0, 0.0))
    o[n-1:] = (c[n:] - c[:-n]) / n; return o
def ema(x, n):
    o = np.full(len(x), np.nan)
    if len(x) < n: return o
    a = 2 / (n + 1); p = x[:n].mean(); o[n-1] = p
    for i in range(n, len(x)): p = a * x[i] + (1 - a) * p; o[i] = p
    return o
rows = []
for t in ['BBCA','TLKM','BNBR','ASII','ANTM','AGRO']:
    full = json.load(open(os.path.join(D, 'ts', t + '.json')))
    for s in ['2021-01-04','2024-01-02','2025-01-02']:
        part = json.load(open(os.path.join(D, 'ts', f'{t}_{s}.json'))); i0 = part['i0']
        for key, n, kind in [('obv',20,'SMA'),('obv',20,'EMA'),('adl',20,'EMA'),('pvt',20,'EMA'),('nvi',255,'EMA'),('pvi',255,'EMA')]:
            a = np.array(part['res'][key][key], float); b = np.array(full['res'][key][key], float)
            mf = (sma if kind=='SMA' else ema)(b, n)[i0:]; mp = (sma if kind=='SMA' else ema)(a, n)
            bb = b[i0:]
            ok = np.isfinite(mf) & np.isfinite(mp)
            sf = bb[ok] > mf[ok]; sp = a[ok] > mp[ok]
            dis = np.nonzero(sf != sp)[0]
            last = (np.nonzero(ok)[0][dis[-1]] if len(dis) else None)
            rows.append(f"{t} start {s} {key}>{kind}{n}: bars_both={ok.sum()} disagree={len(dis)} last_disagree_bar_after_start={last} (of {len(a)})")
open(os.path.join(D, 'derived_state_report.txt'), 'w').write('\n'.join(rows) + '\n')
print('\n'.join(rows))
