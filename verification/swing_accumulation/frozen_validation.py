"""Frozen-rule validation (VALIDATION_1_FROZEN_RULE.md, written and committed BEFORE the new data was pulled). Prints verdicts exactly as the rule defines them; nothing here is tuned afterwards.
Usage: python3 frozen_validation.py <v3_legs_*.pkl from v3_legs.py> <realtime_days.pkl from realtime_lift.py>
Test A (V3 legs, hindsight): H1 = flag HHI of net buying >= 0.3, H2 = flag top-3 net-buyer share of total buy lots >= 20%; outcome = retrace = ln(next high / low) / ln(old high / low); flagged vs other legs, provisional rallies excluded.
Test B (per day, no hindsight): AUC of FL29-since-peak (expected < 0.5) and depth (expected > 0.5); the exploratory rule (depth >= median, top-3 share in the top third, FL29 in the bottom third); the same two flags on days.
Uncertainty: cluster bootstrap resampling STOCKS (2000 resamples, seed 2026), 90% interval."""
import sys
import numpy as np, pandas as pd
rng = np.random.default_rng(2026); NB = 2000
L = pd.read_pickle(sys.argv[1]).copy(); D = pd.read_pickle(sys.argv[2]).copy()
pd.set_option('display.width', 250)


def boot(df, fn, n=NB):
    ks = list(df.tk.unique()); g = {k: df[df.tk == k] for k in ks}; out = []
    for _ in range(n):
        v = fn(pd.concat([g[ks[i]] for i in rng.integers(0, len(ks), len(ks))]))
        if np.isfinite(v): out.append(v)
    return (np.percentile(out, [5, 95]) if len(out) > 100 else (np.nan, np.nan))


# ---------------- Test A
L = L[~L.rally_prov].copy(); L['retrace'] = np.log1p(L.rally / 100) / -np.log1p(L['drop'] / 100)
print(f"TEST A (V3, hindsight): {len(L)} kaki dari {L.tk.nunique()} saham (kaki dengan rally sementara dikeluarkan)\n")
for nm, flag, desc in (('H1', L.hhi >= 0.3, 'HHI net beli >= 0,3'), ('H2', L.buy_share >= 20, 'porsi top-3 pembeli >= 20% dari total lot beli')):
    d = L.assign(f=flag); a, b = d[d.f], d[~d.f]; nst = a.tk.nunique()
    diff = (a.retrace.median() - b.retrace.median()) if len(a) and len(b) else np.nan
    ci = boot(d, lambda x: x[x.f].retrace.median() - x[~x.f].retrace.median() if x.f.any() and (~x.f).any() else np.nan)
    elig = [(g[g.f].retrace.median() > g[~g.f].retrace.median()) for _, g in d.groupby('tk') if g.f.any() and (~g.f).any()]; agree = np.mean(elig) if elig else np.nan
    if len(a) < 15 or nst < 6 or len(elig) < 4: verdict = 'TIDAK DISIMPULKAN (kaki terflag < 15, atau saham dengan flag < 6, atau saham yang bisa dibandingkan < 4)'
    elif ci[0] > 0 and agree >= 0.6: verdict = 'LULUS'
    else: verdict = 'TIDAK MENDUKUNG'
    print(f"{nm} ({desc}): kaki terflag {len(a)} dari {nst} saham | retrace median {a.retrace.median():.2f} vs {b.retrace.median():.2f} | selisih {diff:+.2f}, interval 90% [{ci[0]:+.2f}; {ci[1]:+.2f}] | "
          f"searah di {int(np.sum(elig))} dari {len(elig)} saham ({100 * agree:.0f}%) | retrace >= 1: {int((a.retrace >= 1).sum())}/{len(a)} vs {int((b.retrace >= 1).sum())}/{len(b)}\n   VERDICT {nm}: {verdict}")
print('\nPendamping (deskriptif, tanpa verdict): korelasi peringkat dengan retrace')
for c in ('hhi', 'buy_share', 'fl29'):
    r = L[c].rank().corr(L.retrace.rank()); ci = boot(L, lambda x: x[c].rank().corr(x.retrace.rank())); print(f'   {c}: rho {r:+.2f} [{ci[0]:+.2f}; {ci[1]:+.2f}]')

# ---------------- Test B
def auc(x, y):
    d = pd.DataFrame({'x': x, 'y': y}); n1, n0 = int(d.y.sum()), int((d.y == 0).sum()); rk = d.x.rank()
    return (rk[d.y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0) if n1 and n0 else np.nan


D['rule'] = (D.r_depth >= 0.5) & (D.r_buy_share >= 2 / 3) & (D.r_fl29 <= 1 / 3)
print(f"\nTEST B (per hari, tanpa hindsight): {len(D)} hari pullback dari {D.tk.nunique()} saham | hari dengan rally >= ambang sendiri dalam 20 candle: {int(D.y.sum())} ({100 * D.y.mean():.0f}%)\n")
for col, nm, want in (('r_fl29', 'FL29 sejak puncak', 'lt'), ('r_depth', 'kedalaman pullback', 'gt')):
    a = auc(D[col], D.y); ci = boot(D, lambda x: auc(x[col], x.y)); per = [auc(g[col], g.y) for _, g in D.groupby('tk')]; per = [p for p in per if np.isfinite(p)]
    share = np.mean([(p < 0.5) if want == 'lt' else (p > 0.5) for p in per]); ok = (ci[1] < 0.5) if want == 'lt' else (ci[0] > 0.5)
    print(f"{nm}: AUC {a:.3f} [{ci[0]:.3f}; {ci[1]:.3f}] (harapan {'< 0,5' if want == 'lt' else '> 0,5'}) | saham sesuai harapan {int(round(share * len(per)))} dari {len(per)} ({100 * share:.0f}%)\n   VERDICT: {'LULUS' if ok and share >= 0.6 else 'TIDAK MENDUKUNG'}")


def rate_test(df, flagcol, label, min_days):
    a, b = df[df[flagcol]], df[~df[flagcol]]; nst = a.tk.nunique()
    diff = a.y.mean() - b.y.mean() if len(a) and len(b) else np.nan
    ci = boot(df, lambda x: x[x[flagcol]].y.mean() - x[~x[flagcol]].y.mean() if x[flagcol].any() and (~x[flagcol]).any() else np.nan)
    elig = [(g[g[flagcol]].y.mean() > g[~g[flagcol]].y.mean()) for _, g in df.groupby('tk') if g[flagcol].sum() >= 10 and g.y.sum() >= 10 and (~g[flagcol]).any()]; agree = np.mean(elig) if elig else np.nan
    if len(a) < min_days or nst < 6 or len(elig) < 4: v = f'TIDAK DISIMPULKAN (hari terflag < {min_days}, atau saham dengan flag < 6, atau saham yang bisa dibandingkan < 4)'
    elif ci[0] > 0 and agree >= 0.6: v = 'LULUS'
    else: v = 'TIDAK MENDUKUNG'
    print(f"{label}: hari terflag {len(a)} dari {nst} saham | laju rally {100 * a.y.mean():.0f}% vs {100 * b.y.mean():.0f}% | selisih {100 * diff:+.1f} poin [{100 * ci[0]:+.1f}; {100 * ci[1]:+.1f}] | searah di {int(np.sum(elig))} dari {len(elig)} saham ({100 * agree:.0f}%)\n   VERDICT: {v}")


D['h1'] = D.hhi >= 0.3; D['h2'] = D.buy_share >= 20
rate_test(D, 'rule', 'Aturan eksploratori (kedalaman >= median, top-3 sepertiga atas, FL29 sepertiga bawah)', 50)
rate_test(D, 'h1', 'Flag H1 pada hari (HHI sejak puncak >= 0,3)', 100)
rate_test(D, 'h2', 'Flag H2 pada hari (porsi top-3 sejak puncak >= 20%)', 100)
print('\nLaju dasar per saham:', {tk: f'{100 * g.y.mean():.0f}% (n={len(g)})' for tk, g in D.groupby('tk')})
