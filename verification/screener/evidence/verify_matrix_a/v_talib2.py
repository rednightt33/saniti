import json, sys
import numpy as np, talib
D = '/tmp/claude-0/-home-user-saniti/65bd49d0-9dca-5072-b7db-b62314cf2cd3/scratchpad/audit/verify_matrix_a/data/'
def arr(s): return np.array([np.nan if v is None else v for v in s], dtype=float)
for t in sys.argv[1:]:
    d = json.load(open(D + t + '.json')); ts = json.load(open(D + t + '.ts.json'))
    P = d['price']['rows']; H, L, C = [np.array([r[k] for r in P], dtype=float) for k in (2, 3, 4)]
    m = arr(ts['macd']['macd']); tm = talib.MACD(C, 12, 26, 9)[0]
    ok = np.isfinite(m) & np.isfinite(tm); sc = np.nanmax(np.abs(m))
    bad = np.where(ok & (np.abs(m - tm) > 1e-6 * sc))[0]
    rel = np.abs(m - tm) / np.maximum(np.abs(m), np.abs(tm))
    cmo = arr(ts['cmo']['cmo']); tc = talib.CMO(C, 14); ok2 = np.isfinite(cmo) & np.isfinite(tc)
    dif = np.abs(cmo - tc)[ok2]
    print(f'{t}: MACD talib last bar >1e-6*scale: {bad.max() if len(bad) else None}; max rel (bars 33..60) {np.nanmax(rel[33:60]) if len(C)>60 else None:.3f}; '
          f'CMO median|diff|={np.median(dif):.2f} p90={np.percentile(dif,90):.2f} last TS={cmo[-1]:.2f} talib={tc[-1]:.2f}')
