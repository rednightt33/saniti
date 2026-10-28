# verify_matrix_b: bars after a later history start until TS output equals the full-history output within tol x series max-abs (permanently).
import json, os, sys, math
import numpy as np
D = os.path.dirname(os.path.abspath(__file__))
tick = sys.argv[1].split(','); starts = sys.argv[2].split(',')
res = {}
for t in tick:
    full = json.load(open(os.path.join(D, 'ts', t + '.json')))
    for s in starts:
        p = os.path.join(D, 'ts', f'{t}_{s}.json')
        if not os.path.exists(p): continue
        part = json.load(open(p)); i0 = part['i0']
        for k, outs in part['res'].items():
            for o, ser in outs.items():
                a = np.array([np.nan if v is None else v for v in ser], float)
                b = np.array([np.nan if v is None else v for v in full['res'][k][o][i0:]], float)
                scale = np.nanmax(np.abs(b)) if np.isfinite(b).any() else 1.0
                both = np.isfinite(a) & np.isfinite(b); nm = np.isfinite(a) != np.isfinite(b)
                bad = nm | (both & (np.abs(a - b) > 1e-9 * scale))
                idx = np.nonzero(bad)[0]
                settle = 0 if len(idx) == 0 else (idx[-1] + 1 if idx[-1] < len(a) - 1 else None)
                lastrel = abs(a[-1] - b[-1]) / abs(b[-1]) if np.isfinite(a[-1]) and np.isfinite(b[-1]) and b[-1] != 0 else float('nan')
                res.setdefault(f'{k}.{o}', []).append((t, s, len(a), settle, int(nm.sum()), lastrel))
for k, v in res.items():
    st = [x[3] for x in v]
    never = sum(1 for x in st if x is None)
    fin = [x for x in st if x is not None]
    print(f"{k}: settle_bars min={min(fin) if fin else '-'} max={max(fin) if fin else '-'} never={never}/{len(v)} | nullmismatch max={max(x[4] for x in v)} | lastbar rel diff max={max((x[5] for x in v if not math.isnan(x[5])), default=float('nan')):.3g} | " + ' '.join(f"{x[0]}@{x[1][:4]}:{x[3]}" for x in v if x[3] is None or x[3] > 0)[:400])
