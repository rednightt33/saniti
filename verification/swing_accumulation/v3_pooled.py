"""Pooled statistics over the V3 pre-rally legs written by v3_legs.py (research, local, read-only).
Usage: SWING_DATA_DIR=<dir> python3 v3_pooled.py <pickle written by v3_legs.py>
Question: does any footprint of the decline leg (HIGH -> LOW) line up with how much the stock rallies afterwards, once the depth of the decline and the stock itself are taken out?
Rally outcome (all derived from the leg's own prices, so no extra data):
  rally_log  = ln(1 + rally%)                         raw size (mechanically larger after a deeper decline)
  retrace    = ln(next high / low) / ln(high / low)   share of the decline that the rally wins back (depth normalised; 1 = back to the old high)
Every statistic is a rank correlation (Spearman). Uncertainty: cluster bootstrap that resamples STOCKS (legs of one stock are not independent); 'within-stock' ranks every value inside its own stock first.
Exploratory: ~50 legs, 12 stocks, hindsight pivots, every leg is followed by a rally by construction (there are no negative cases here)."""
import os, sys
import numpy as np, pandas as pd
rng = np.random.default_rng(23)
T = pd.read_pickle(sys.argv[1]).copy(); T['rally_log'] = np.log1p(T.rally / 100); T['retrace'] = np.log1p(T.rally / 100) / -np.log1p(T['drop'] / 100)
T['m_log'] = np.log(T.m); FEATS = ['buy_share', 'sell_share', 'asym', 'hhi', 'top1', 'fl29', 'top1_last3', 'uw', 'drop', 'm']
print(f'{len(T)} kaki, {T.tk.nunique()} saham: ' + ', '.join(f'{k} {v}' for k, v in T.groupby('tk').size().items()))


def rho(x, y): return x.rank().corr(y.rank())


def within(df, col): return df.groupby('tk')[col].rank(pct=True)


def partial(df, x, y, z):
    rx, ry, rz = df[x].rank(), df[y].rank(), df[z].rank(); ex = rx - np.polyval(np.polyfit(rz, rx, 1), rz); ey = ry - np.polyval(np.polyfit(rz, ry, 1), rz); return ex.corr(ey)


def boot(fn, n=2000):
    ks = list(T.tk.unique()); g = {k: T[T.tk == k] for k in ks}; out = []
    for _ in range(n):
        d = pd.concat([g[ks[i]] for i in rng.integers(0, len(ks), len(ks))]); v = fn(d)
        if np.isfinite(v): out.append(v)
    return np.percentile(out, [5, 95])


rows = []
for f in FEATS:
    d = T.dropna(subset=[f]); r_raw = rho(d[f], d.rally_log); r_ret = rho(d[f], d.retrace)
    d2 = d.assign(wf=within(d, f), wr=within(d, 'retrace')); r_w = rho(d2.wf, d2.wr)
    pr = partial(d, f, 'rally_log', 'drop') if f != 'drop' else np.nan
    ci = boot(lambda x: rho(x[f], x.retrace)); sg = [rho(g[f], g.retrace) for _, g in d.groupby('tk') if len(g) >= 3]
    rows.append([f, r_raw, r_ret, ci[0], ci[1], r_w, pr, sum(s > 0 for s in sg), sum(s < 0 for s in sg), len(sg)])
R = pd.DataFrame(rows, columns=['ciri kaki turun', 'rho vs besar rally', 'rho vs pengembalian (retrace)', 'P5', 'P95', 'rho dalam-saham (retrace)', 'rho parsial vs rally, kedalaman dikendalikan', 'saham rho>0', 'saham rho<0', 'dari saham (>=3 kaki)'])
pd.set_option('display.width', 250); pd.set_option('display.max_columns', 30); print('\nKorelasi peringkat dengan hasil rally sesudahnya (interval 90% = bootstrap per saham, untuk kolom retrace)'); print(R.to_string(index=False, float_format=lambda v: f'{v:+.2f}'))
print('\nLeave-one-stock-out (rho ciri vs retrace; rentang saat satu saham dikeluarkan):')
for f in ('buy_share', 'fl29', 'hhi', 'top1', 'uw'):
    v = [rho(T[T.tk != k][f], T[T.tk != k].retrace) for k in T.tk.unique()]; print(f'   {f}: {min(v):+.2f} sampai {max(v):+.2f} (semua kaki: {rho(T[f], T.retrace):+.2f})')
print('\nPembanding jendela turun sama panjang di saham yang sama: persentil kaki (50 = biasa); median dan interval 90% bootstrap per saham')
for f in ('buy_share', 'sell_share', 'asym', 'hhi', 'top1', 'fl29'):
    c = 'pct_' + f; d = T.dropna(subset=[c]); ci = boot(lambda x: x[c].median()) if len(d) else (np.nan, np.nan)
    print(f'   {f}: median {d[c].median():.0f} [{ci[0]:.0f}; {ci[1]:.0f}] | di atas 75: {int((d[c] > 75).sum())} | di bawah 25: {int((d[c] < 25).sum())} dari {len(d)} kaki')
print('\nHasil per saham (median per kaki): saham, jumlah kaki, rally median %, retrace median, porsi top-3 pembeli, FL29, HHI, underwater')
G = T.groupby('tk').agg(n=('rally', 'size'), rally=('rally', 'median'), retrace=('retrace', 'median'), buy_share=('buy_share', 'median'), fl29=('fl29', 'median'), hhi=('hhi', 'median'), uw=('uw', 'median')); print(G.round(2).to_string())
print('\nKonsentrasi tinggi (HHI >= 0,3) atau porsi top-3 >= 20%: ' + ', '.join(f"{r.tk} {r.leg} (HHI {r.hhi:.2f}, top-3 {r.buy_share:.0f}%, rally {r.rally:+.0f}%, retrace {r.retrace:.2f})" for r in T[(T.hhi >= 0.3) | (T.buy_share >= 20)].itertuples()))
hi = T[(T.hhi >= 0.3) | (T.buy_share >= 20)]; lo = T.drop(hi.index)
print(f'   {len(hi)} kaki "terkonsentrasi": retrace median {hi.retrace.median():.2f}, rally median {hi.rally.median():.0f}% | {len(lo)} kaki lain: retrace median {lo.retrace.median():.2f}, rally median {lo.rally.median():.0f}%')
