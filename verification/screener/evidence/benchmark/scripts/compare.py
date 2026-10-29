"""(e) warm-up / recursion sensitivity: latest values computed on the last K bars (or from 2023-10-01) vs full history.
Differs = |x-y| > 1e-9 * max(|x|,|y|) (both 0 -> equal); null mismatch = exactly one side null. Writes results/compare.json."""
import json, math
R = '/tmp/claude-0/-home-user-saniti/65bd49d0-9dca-5072-b7db-b62314cf2cd3/scratchpad/audit/benchmark/results/'
WINDOWS = ['last250', 'last500', 'last750', 'from20231001']
def cmp(full, part):
    n = diff = diff_abs = nullmm = 0; mx = 0.0; mxt = None; mxa = 0.0; maxabs = 0.0
    for t, x in full.items():
        y = part.get(t, 'MISSING')
        if y == 'MISSING': continue
        n += 1
        if (x is None) != (y is None): nullmm += 1; continue
        if x is None: continue
        d = abs(x - y); m = max(abs(x), abs(y)); rel = 0.0 if m == 0 else d / m
        if rel > 1e-9: diff += 1
        if rel > 1e-9 and d > 1e-9: diff_abs += 1
        maxabs = max(maxabs, d)
        if rel > mx: mx, mxt, mxa = rel, t, d
    return {'tickers': n, 'differ_gt_1e-9_rel': diff, 'differ_rel_and_abs_gt_1e-9': diff_abs, 'null_mismatch': nullmm, 'max_rel': mx, 'max_rel_ticker': mxt, 'abs_diff_at_max': mxa, 'max_abs_diff': maxabs}
out = {'abc': {}, 'all53': {}}
full = {r['t']: r for r in json.load(open(R + 'abc_full.json'))['rows']}
for w in WINDOWS:
    part = {r['t']: r for r in json.load(open(R + f'abc_{w}.json'))['rows']}
    res = {}
    for k in ['rsi7', 'sma75', 'macd', 'signal']:
        res[k] = cmp({t: r[k] for t, r in full.items()}, {t: r[k] for t, r in part.items()})
    for k in ['a', 'b', 'c', 'c_sessions_ago']:
        res['flag_' + k + '_differs'] = sum(1 for t in full if full[t].get(k) != part[t].get(k))
    out['abc'][w] = res
F = json.load(open(R + 'all53_full.json'))['latest']
for w in WINDOWS:
    P = json.load(open(R + f'all53_{w}.json'))['latest']
    out['all53'][w] = {f'{i}.{o}': cmp(F[i][o], P[i][o]) for i in F for o in F[i]}
json.dump(out, open(R + 'compare.json', 'w'), indent=1)
print('== (a)-(c) latest values vs full history ==')
for w, res in out['abc'].items():
    print(w, {k: (v if not isinstance(v, dict) else (v['differ_gt_1e-9_rel'], v['null_mismatch'], f"{v['max_rel']:.3g}", v['max_rel_ticker'])) for k, v in res.items()})
print('== all 53 outputs per window (last250 | last500 | last750 | from20231001): differ_rel>1e-9, differ_rel&abs>1e-9, null mismatch, max rel, max abs ==')
ids = list(out['all53']['last250'].keys())
for k in ids:
    row = [out['all53'][w][k] for w in WINDOWS]
    print(f"{k:28s}", ' | '.join(f"{r['differ_gt_1e-9_rel']:4d} {r['differ_rel_and_abs_gt_1e-9']:4d} {r['null_mismatch']:2d} {r['max_rel']:.1e} {r['max_abs_diff']:.1e}" for r in row))
