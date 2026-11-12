"""Real-time test: which footprint, computed with data up to day t only, separates pullback days that are followed by a rally from those that are not?
Usage: SWING_DATA_DIR=<dir> python3 realtime_lift.py TICKER [TICKER ...]      (needs <dir>/<t>_price.pkl, <t>_broker.pkl, <t>_result.json from pull_stock.py / analyze_stock.py)
State at day t (no hindsight): peak = highest close of the last 60 candles (latest occurrence); pullback state = close <= peak x (1 - theta/2) and >= 5 candles since the peak (theta = the stock's own swing threshold).
Label: the highest high of the next 20 candles >= close(t) x (1 + theta)  (a rally as large as the stock's own swing threshold).
Features: depth, age, close vs the anchored top-3 buy VWAP since the peak (underwater), broker footprint since the peak and over the last 10 candles (Regular, lots), volume ratio, rebound so far.
Each feature is turned into its percentile within its own stock (pullback days only) before pooling; the interval is a cluster bootstrap over STOCKS. Exploratory: days overlap heavily, few stocks."""
import os, sys, json
import numpy as np, pandas as pd
S = os.path.join(os.environ.get('SWING_DATA_DIR', '.'), ''); TKS = [t.upper() for t in sys.argv[1:]]; rng = np.random.default_rng(11); LB, FWD, RECENT = 60, 20, 10


def stock_rows(tk):
    P = pd.read_pickle(S + f'{tk.lower()}_price.pkl').reset_index(drop=True); B = pd.read_pickle(S + f'{tk.lower()}_broker.pkl'); th = json.load(open(S + f'{tk.lower()}_result.json'))['th']
    n = len(P); dates = P.d.tolist(); di = {d: i for i, d in enumerate(dates)}; c, h, l, v = (P[k].values.astype(float) for k in ('c', 'h', 'l', 'v'))
    R = B[(B.mb == 'Regular') & B.d.isin(di)].copy(); R['i'] = R.d.map(di); brokers = sorted(R.b.unique()); bi = {b: k for k, b in enumerate(brokers)}; nb = len(brokers)
    M = {k: np.zeros((n, nb)) for k in ('bl', 'sl', 'bv', 'sv')}; ii = R.i.values; bj = R.b.map(bi).values
    for k in M: np.add.at(M[k], (ii, bj), R[k].values)
    BL, SL, BV, SV = M['bl'], M['sl'], M['bv'], M['sv']; NL = BL - SL; NV = BV - SV; z = np.zeros((1, nb)); cNL = np.vstack([z, np.cumsum(NL, 0)]); cBL = np.vstack([z, np.cumsum(BL, 0)]); cBV = np.vstack([z, np.cumsum(BV, 0)])
    pos = np.zeros(n); valid = np.zeros(n)
    for d_ in range(n):
        if BV[d_].sum() > 0:
            r_ = np.sort(NV[d_]); valid[d_] = 1; pos[d_] = float(np.where(r_[::-1][:3] > 0, r_[::-1][:3], 0).sum() + np.where(r_[:3] < 0, r_[:3], 0).sum() > 0)
    cpos = np.concatenate([[0.0], np.cumsum(pos)]); cval = np.concatenate([[0.0], np.cumsum(valid)])
    rows = []
    for t in range(LB, n - FWD):
        w = c[t - LB + 1:t + 1]; p = t - (LB - 1 - int(np.argmax(w[::-1]))) + (LB - 1) - (LB - 1)    # latest occurrence of the maximum
        p = t - LB + 1 + (LB - 1 - int(np.argmax(w[::-1])))
        age = t - p; dd = c[t] / c[p] - 1
        if age < 5 or dd > -th / 2: continue
        a = p + 1; nl = cNL[t + 1] - cNL[a]; tot = (cBL[t + 1] - cBL[a]).sum()
        if tot <= 0: continue
        od = [x for x in np.argsort(-nl, kind='stable')[:3] if nl[x] > 0]; os_ = [x for x in np.argsort(nl, kind='stable')[:3] if nl[x] < 0]; pp = nl[nl > 0]
        if not od or not os_: continue
        bs = 100 * sum(nl[x] for x in od) / tot; ss = -100 * sum(nl[x] for x in os_) / tot; vw = (cBV[t + 1] - cBV[a])[od].sum() / (100 * (cBL[t + 1] - cBL[a])[od].sum()); nvld = cval[t + 1] - cval[a]
        r0 = t - RECENT + 1; nl10 = cNL[t + 1] - cNL[r0]; tot10 = (cBL[t + 1] - cBL[r0]).sum(); od10 = [x for x in np.argsort(-nl10, kind='stable')[:3] if nl10[x] > 0]; os10 = [x for x in np.argsort(nl10, kind='stable')[:3] if nl10[x] < 0]
        if tot10 <= 0: continue
        rows.append(dict(tk=tk, t=t, d=dates[t], depth=-dd, age=age, uw=c[t] / vw - 1, buy_share=bs, sell_share=ss, asym=bs - ss, hhi=float(((pp / pp.sum()) ** 2).sum()), fl29=100 * (cpos[t + 1] - cpos[a]) / nvld if nvld else np.nan,
                         cohort_recent=100 * nl10[od].sum() / tot10, asym10=100 * (nl10[od10].sum() + nl10[os10].sum()) / tot10 if od10 and os10 else np.nan, fl29_10=100 * (cpos[t + 1] - cpos[r0]) / max(cval[t + 1] - cval[r0], 1),
                         vol_ratio=v[t - 4:t + 1].mean() / max(v[t - 24:t - 4].mean(), 1), rebound=c[t] / l[a:t + 1].min() - 1, ret5=c[t] / c[t - 5] - 1, y=int(h[t + 1:t + FWD + 1].max() >= c[t] * (1 + th))))
    return rows, th


allr = []; ths = {}
for tk in TKS:
    r, th = stock_rows(tk); allr += r; ths[tk] = th
D = pd.DataFrame(allr).dropna(); pd.set_option('display.width', 250); pd.set_option('display.float_format', lambda x: f'{x:,.2f}')
print(f'{len(TKS)} saham | hari dalam keadaan pullback (data lengkap): {len(D):,} | dengan rally >= ambang sendiri dalam {FWD} candle: {int(D.y.sum()):,} ({100 * D.y.mean():.0f}%)')
print('tingkat dasar per saham:', {tk: f'{100 * g.y.mean():.0f}% (n={len(g)})' for tk, g in D.groupby('tk')})
feats = ['depth', 'age', 'uw', 'buy_share', 'sell_share', 'asym', 'hhi', 'fl29', 'cohort_recent', 'asym10', 'fl29_10', 'vol_ratio', 'rebound', 'ret5']
for f in feats: D['r_' + f] = D.groupby('tk')[f].rank(pct=True)


def auc(x, y):
    d = pd.DataFrame({'x': x, 'y': y}); n1, n0 = int(d.y.sum()), int((d.y == 0).sum()); rk = d.x.rank()
    return (rk[d.y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0) if n1 and n0 else np.nan


def cboot(f, col='r_', n=1000):
    ks = list(D.tk.unique()); g = {k: D[D.tk == k] for k in ks}; out = []
    for _ in range(n):
        dd = pd.concat([g[ks[i]] for i in rng.integers(0, len(ks), len(ks))]); out.append(auc(dd[col + f], dd.y))
    return np.nanpercentile(out, [5, 95])


D['depth_bin'] = D.groupby('tk').depth.transform(lambda s: pd.qcut(s.rank(method='first'), 3, labels=False))
rows = []
for f in feats:
    a = auc(D['r_' + f], D.y); ci = cboot(f); strat = np.nanmean([auc(D[D.depth_bin == b]['r_' + f], D[D.depth_bin == b].y) for b in (0, 1, 2)]); per = [auc(g['r_' + f], g.y) for _, g in D.groupby('tk')]
    rows.append([f, a, ci[0], ci[1], strat, int(np.sum(np.array(per) > 0.5)), len(per)])
print('\nAUC = peluang bahwa hari yang diikuti rally bernilai LEBIH BESAR daripada hari tanpa rally (0,50 = tidak ada beda); nilai diubah menjadi persentil di dalam tiap saham')
print(pd.DataFrame(rows, columns=['ciri (dihitung hanya dari data sampai hari t)', 'AUC gabungan', 'P5', 'P95', 'AUC pada kedalaman yang sama', 'saham dengan AUC>0,5', 'dari']).to_string(index=False, float_format=lambda x: f'{x:.2f}'))
D.to_pickle(S + 'realtime_days.pkl')


print('\n== Laju rally menurut sepertiga ciri (sepertiga dihitung di dalam tiap saham); selisih sepertiga atas dikurangi bawah dengan interval bootstrap per saham')
def terc(col):
    return D.groupby('tk')['r_' + col].transform(lambda x: pd.qcut(x.rank(method='first'), 3, labels=False))
rows2 = []
for f in ('depth', 'uw', 'buy_share', 'sell_share', 'asym', 'fl29', 'fl29_10'):
    D['tz'] = terc(f); lo, mid, hi = (D[D.tz == k].y.mean() for k in (0, 1, 2)); ks = list(D.tk.unique()); g = {k: D[D.tk == k] for k in ks}; dif = []
    for _ in range(1000):
        dd = pd.concat([g[ks[i]] for i in rng.integers(0, len(ks), len(ks))]); dif.append(dd[dd.tz == 2].y.mean() - dd[dd.tz == 0].y.mean())
    ci = np.nanpercentile(dif, [5, 95]); rows2.append([f, 100 * lo, 100 * mid, 100 * hi, 100 * (hi - lo), 100 * ci[0], 100 * ci[1]])
print(pd.DataFrame(rows2, columns=['ciri', 'sepertiga bawah %', 'tengah %', 'atas %', 'atas - bawah (poin)', 'P5', 'P95']).to_string(index=False, float_format=lambda x: f'{x:.1f}'))
D['rule'] = (D.r_depth >= 0.5) & (D.r_buy_share >= 2 / 3) & (D.r_fl29 <= 1 / 3)
print(f"\n== Aturan sederhana (dipilih SESUDAH melihat tabel di atas, jadi hipotesis, bukan hasil uji): kedalaman di atas median saham & porsi lot top-3 pembeli di sepertiga atas & hari akumulasi di sepertiga bawah")
print(f"hari yang memenuhi aturan: {int(D.rule.sum())} dari {len(D)} ({100 * D.rule.mean():.0f}%) | laju rally {100 * D[D.rule].y.mean():.0f}% vs {100 * D[~D.rule].y.mean():.0f}% pada hari lain | tingkat dasar {100 * D.y.mean():.0f}%")
pr = []
for tk, g in D.groupby('tk'):
    a, b = g[g.rule], g[~g.rule]; pr.append([tk, len(a), 100 * a.y.mean() if len(a) else np.nan, 100 * b.y.mean(), int(g.y.sum())])
P2 = pd.DataFrame(pr, columns=['saham', 'hari aturan', 'laju rally saat aturan %', 'laju rally hari lain %', 'hari rally total']); print(P2.to_string(index=False, float_format=lambda x: f'{x:.0f}'))
ok = P2[(P2['hari aturan'] >= 10) & (P2['hari rally total'] >= 10)]; print(f"saham dengan >= 10 hari aturan dan >= 10 hari rally: {len(ok)} | laju saat aturan > laju hari lain pada {int((ok['laju rally saat aturan %'] > ok['laju rally hari lain %']).sum())} dari {len(ok)}")
ks = list(D.tk.unique()); g = {k: D[D.tk == k] for k in ks}; dif = []
for _ in range(1000):
    dd = pd.concat([g[ks[i]] for i in rng.integers(0, len(ks), len(ks))]); dif.append(dd[dd.rule].y.mean() - dd[~dd.rule].y.mean())
print('selisih laju (aturan - lainnya), interval 90% bootstrap per saham (poin):', (100 * np.nanpercentile(dif, [5, 95])).round(1).tolist())
