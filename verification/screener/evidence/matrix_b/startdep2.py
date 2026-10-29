"""Same as startdep.py but a difference counts only if |a-b| > 1e-9 * max|full series| (scale-normalised), and null-pattern diffs are counted."""
import json, os, numpy as np
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
                a = arr(v); fb = arr(full[k][o]); b = fb[i0:]
                scale = np.nanmax(np.abs(fb)) if (~np.isnan(fb)).any() else 1
                both = ~np.isnan(a) & ~np.isnan(b)
                bad = both & (np.abs(a - b) > 1e-9 * scale)
                fa = int(np.argmax(~np.isnan(a))) if (~np.isnan(a)).any() else 0
                nullmis = int(((np.isnan(a) != np.isnan(b)) & (np.arange(len(a)) >= fa)).sum())
                idx = np.where(bad)[0]
                st = 0 if len(idx) == 0 else (int(idx[-1]) + 1 if idx[-1] < len(a) - 1 else 'never')
                if st != 0 or nullmis:
                    lines.append(f'  {k}.{o}: settle_abs1e-9xscale={st} null_mismatch_after_first_valid={nullmis}')
open(f'{D}/startdep2_report.txt', 'w').write('\n'.join(lines) + '\n')
print('\n'.join(lines))
