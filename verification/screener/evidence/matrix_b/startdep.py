"""Start dependence: TS on truncated history vs TS on full history; bars until rel diff stays <= tol."""
import json, os, sys, numpy as np
D = os.path.dirname(os.path.abspath(__file__))
def arr(x): return np.array([np.nan if v is None else v for v in x], dtype=np.float64)
lines = []
for t in ['BBCA', 'TLKM', 'BNBR']:
    full = json.load(open(f'{D}/ts/{t}.json'))['res']
    for s in ['2021-01-04', '2024-01-02', '2025-01-02']:
        tr = json.load(open(f'{D}/ts/{t}_{s}.json')); i0 = tr['i0']; res = tr['res']
        lines.append(f'== {t} start {tr["start"]} (offset {i0}, {tr["n"]} bars)')
        for k, outs in res.items():
            for o, v in outs.items():
                a = arr(v); b = arr(full[k][o])[i0:]
                both = ~np.isnan(a) & ~np.isnan(b)
                den = np.maximum(np.abs(a), np.abs(b))
                with np.errstate(divide='ignore', invalid='ignore'):
                    rel = np.where(den > 0, np.abs(a - b) / den, 0.0)
                rel[~both] = np.nan
                def settle(tol):
                    bad = np.where(both & (rel > tol))[0]
                    return 0 if len(bad) == 0 else (int(bad[-1]) + 1 if bad[-1] < len(a) - 1 else 'never')
                first_a = int(np.argmax(~np.isnan(a))) if (~np.isnan(a)).any() else None
                last_rel = float(rel[both][-1]) if both.any() else None
                lines.append(f'  {k}.{o}: first_valid_trunc={first_a} settle_1e-6={settle(1e-6)} settle_1e-9={settle(1e-9)} last_rel={last_rel:.3g}' if last_rel is not None else f'  {k}.{o}: no overlap')
open(f'{D}/startdep_report.txt', 'w').write('\n'.join(lines) + '\n')
print('\n'.join(lines))
