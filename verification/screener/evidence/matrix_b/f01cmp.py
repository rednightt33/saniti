"""Compare TS volume_sma / rvol / hist_vol with Feature_01_Stock_Daily (read-only)."""
import json, os, sys, numpy as np
sys.path.insert(0, '/tmp/claude-0/-home-user-saniti/65bd49d0-9dca-5072-b7db-b62314cf2cd3/scratchpad/tools'); import pgq2
D = os.path.dirname(os.path.abspath(__file__))
def arr(x): return np.array([np.nan if v is None else v for v in x], dtype=np.float64)
for t in ['BBCA', 'GOTO', 'BNBR', 'AYAM']:
    r = pgq2.q(f"""select date::text, volume_avg_20d, volume_ratio_20d, volatility_20d_ann_pct from public."Feature_01_Stock_Daily" where ticker='{t}' order by date""")
    if 'error' in r: print(r['error']); continue
    m = {row[0][:10]: row[1:] for row in r['rows']}
    d = json.load(open(f'{D}/data/{t}.json')); ts = json.load(open(f'{D}/ts/{t}.json'))['res']
    idx = [i for i, x in enumerate(d['T']) if x in m]
    for name, tsv, j in [('volume_sma vs F01 volume_avg_20d', ts['volume_sma']['volume_sma'], 0), ('rvol vs F01 volume_ratio_20d', ts['rvol']['rvol'], 1), ('hist_vol vs F01 volatility_20d_ann_pct', ts['hist_vol']['historical_volatility'], 2)]:
        a = arr([tsv[i] for i in idx]); b = arr([m[d['T'][i]][j] for i in idx])
        both = ~np.isnan(a) & ~np.isnan(b)
        rel = np.abs(a - b)[both] / np.maximum(np.abs(a), np.abs(b))[both].clip(1e-300)
        print(t, name, 'F01 rows', len(m), 'common', len(idx), 'both', int(both.sum()), 'null mismatch', int((np.isnan(a) != np.isnan(b)).sum()), 'max rel', float(rel.max()) if both.any() else None, 'median rel', float(np.median(rel)) if both.any() else None)
