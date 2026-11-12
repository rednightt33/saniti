"""Cross-stock comparison of the pre-rally pullbacks (decline leg HIGH -> LOW that is followed by a rally) produced by analyze_stock.py.
Usage: SWING_DATA_DIR=<dir> python3 aggregate_swings.py TICKER [TICKER ...]
Part 1: one row per pre-rally pullback (broker features of the whole leg, anchored top-3 buy VWAP / underwater at the swing low, size and speed of the rally that follows).
Part 2: near-bottom vs earlier-in-the-same-decline (paired within each leg, windows of 10 candles): does the broker footprint change as the low approaches?
Statistics: sign test and a cluster bootstrap that resamples STOCKS (legs of one stock are not independent). Exploratory: ~100 legs, 12 stocks, hindsight pivots."""
import os, sys, json
import numpy as np, pandas as pd
S = os.path.join(os.environ.get('SWING_DATA_DIR', '.'), ''); TKS = [t.upper() for t in sys.argv[1:]]
rng = np.random.default_rng(7)


def load(tk):
    P = pd.read_pickle(S + f'{tk.lower()}_price.pkl').reset_index(drop=True); B = pd.read_pickle(S + f'{tk.lower()}_broker.pkl'); n = len(P); dates = P.d.tolist(); di = {d: i for i, d in enumerate(dates)}
    R = B[(B.mb == 'Regular') & B.d.isin(di)].copy(); R['i'] = R.d.map(di); brokers = sorted(R.b.unique()); bi = {b: k for k, b in enumerate(brokers)}; nb = len(brokers)
    M = {k: np.zeros((n, nb)) for k in ('bl', 'sl', 'bv', 'sv')}; ii = R.i.values; bj = R.b.map(bi).values
    for k in M: np.add.at(M[k], (ii, bj), R[k].values)
    return dict(P=P, di=di, dates=dates, BL=M['bl'], SL=M['sl'], BV=M['bv'], SV=M['sv'], NL=M['bl'] - M['sl'], NV=M['bv'] - M['sv'], v=P.v.values.astype(float), c=P.c.values.astype(float))


def feat(D, a, b):
    """broker features of candles a..b (Regular, lots)"""
    nl = D['NL'][a:b + 1].sum(0); tot = D['BL'][a:b + 1].sum()
    if tot <= 0: return None
    od = [x for x in np.argsort(-nl, kind='stable')[:3] if nl[x] > 0]; os_ = [x for x in np.argsort(nl, kind='stable')[:3] if nl[x] < 0]; pos = nl[nl > 0]
    bal = []
    for d_ in range(a, b + 1):
        if D['BV'][d_].sum() > 0:
            r_ = np.sort(D['NV'][d_]); big, sm = r_[::-1][:3], r_[:3]; bal.append(np.where(big > 0, big, 0).sum() + np.where(sm < 0, sm, 0).sum())
    bs = 100 * sum(nl[x] for x in od) / tot; ss = -100 * sum(nl[x] for x in os_) / tot
    return dict(buy_share=bs, sell_share=ss, asym=bs - ss, hhi=float(((pos / pos.sum()) ** 2).sum()) if len(pos) else np.nan, top1=100 * pos.max() / pos.sum() if len(pos) else np.nan,
                fl29=100 * np.mean(np.array(bal) > 0) if bal else np.nan, vol=D['v'][a:b + 1].mean())


rows, near = [], []
for tk in TKS:
    r = json.load(open(S + f'{tk.lower()}_result.json')); D = load(tk); th = r['th']; legs = {(L['d0'], L['d1']): L for L in r['legs'] if L['kind'] == 'TURUN'}
    for t1 in r['tafsir1']:
        L = legs.get((t1['anchor'], t1['low_date'])); iH, iL = D['di'][t1['anchor']], D['di'][t1['low_date']]
        rows.append(dict(tk=tk, th=th, anchor=t1['anchor'], low=t1['low_date'], days=t1['window'], drop=t1['drop'], buy_share=L['buy_share'], asym=L['buy_share'] - L['sell_share'], hhi=L['hhi'], top1=L['top1_net'], fl29=L['fl29'],
                         uw=t1['uw_close'], uw_low=t1['uw_low'], uw_mkt=t1['uw_mkt'], rally=t1['rally'], rally_days=t1['rally_days'], rally_rel=t1['rally'] / (100 * th), speed=t1['rally'] / max(t1['rally_days'], 1)))
        if iL - iH >= 20:
            A, Bw = feat(D, iL - 9, iL), feat(D, iL - 19, iL - 10)
            if A and Bw: near.append(dict(tk=tk, **{f'{k}_A': A[k] for k in A}, **{f'{k}_B': Bw[k] for k in Bw}))
T = pd.DataFrame(rows); N = pd.DataFrame(near)
pd.set_option('display.width', 250); pd.set_option('display.float_format', lambda v: f'{v:,.1f}')
print(f'{len(TKS)} saham | {len(T)} kaki turun pra-rally | kaki dengan >= 20 candle untuk uji dekat-dasar: {len(N)}')
print('\n== 1. Ringkasan per saham (median per kaki turun pra-rally)')
G = T.groupby('tk').agg(n=('drop', 'size'), th=('th', lambda s: 100 * s.iloc[0]), drop=('drop', 'median'), buy_share=('buy_share', 'median'), asym=('asym', 'median'), hhi=('hhi', 'median'), top1=('top1', 'median'), fl29=('fl29', 'median'), uw=('uw', 'median'), rally=('rally', 'median'), rally_days=('rally_days', 'median'))
print(G.round(1).to_string())
print('\n== 2. Semua kaki turun pra-rally digabung: sebaran')
print(T[['drop', 'days', 'buy_share', 'asym', 'hhi', 'top1', 'fl29', 'uw', 'uw_low', 'rally', 'rally_days']].quantile([.1, .25, .5, .75, .9]).T.rename(columns={.1: 'P10', .25: 'P25', .5: 'P50', .75: 'P75', .9: 'P90'}).round(1).to_string())
sig = (T.buy_share >= 10) & (T.asym >= 5) & (T.fl29 >= 50)
print(f'\ntanda tangan "akumulasi terpusat" (porsi lot top-3 >= 10%, asimetri >= +5, hari akumulasi >= 50%): {int(sig.sum())} dari {len(T)} kaki ({", ".join(sorted(set(T[sig].tk)))}) | rally median: {T[sig].rally.median():.0f}% vs {T[~sig].rally.median():.0f}% pada kaki lain')
for nm, m in (('porsi lot top-3 >= 10%', T.buy_share >= 10), ('asimetri >= +5', T.asym >= 5), ('hari akumulasi >= 50%', T.fl29 >= 50), ('HHI net beli >= 0,3', T.hhi >= 0.3)): print(f'   {nm}: {int(m.sum())} kaki ({100 * m.mean():.0f}%)')
print('\nUnderwater pada close swing low terhadap VWAP kohort top-3: P25/P50/P75 =', T.uw.quantile([.25, .5, .75]).round(1).tolist(), '| kaki dengan underwater <= -10%:', f'{100 * (T.uw <= -10).mean():.0f}%', '| <= -20%:', f'{100 * (T.uw <= -20).mean():.0f}%')


def boot_corr(x, y, tk, n=2000):
    ks = list(set(tk)); d = pd.DataFrame({'x': x, 'y': y, 'k': tk}); g = {k: d[d.k == k] for k in ks}; out = []
    for _ in range(n):
        dd = pd.concat([g[ks[i]] for i in rng.integers(0, len(ks), len(ks))]); out.append(dd.x.rank().corr(dd.y.rank()))
    return np.nanpercentile(out, [5, 95])


print('\n== 3. Ciri kaki turun vs rally yang menyusul (korelasi peringkat; interval 90% dengan bootstrap per saham)')
rows3 = []
for f, lab in (('buy_share', 'porsi lot top-3 pembeli'), ('asym', 'asimetri pembeli-penjual'), ('hhi', 'HHI net beli'), ('top1', 'porsi top-1 dari net beli'), ('fl29', 'hari akumulasi'), ('uw', 'underwater pada swing low (close)'), ('drop', 'besar penurunan'), ('days', 'lama penurunan')):
    for tgt, tl in (('rally_rel', 'besar rally (dibanding ambang saham)'), ('speed', 'kecepatan rally (%/candle)')):
        c = T[f].rank().corr(T[tgt].rank()); ci = boot_corr(T[f], T[tgt], T.tk); rows3.append([lab, tl, c, ci[0], ci[1]])
print(pd.DataFrame(rows3, columns=['ciri kaki turun', 'rally', 'korelasi', 'P5', 'P95']).to_string(index=False, float_format=lambda v: f'{v:+.2f}'))


def boot_med(d, col, n=2000):
    ks = list(d.tk.unique()); g = {k: d[d.tk == k][col].values for k in ks}; out = []
    for _ in range(n): out.append(np.median(np.concatenate([g[ks[i]] for i in rng.integers(0, len(ks), len(ks))])))
    return np.nanpercentile(out, [5, 95])


print('\n== 4. Dekat dasar (10 candle terakhir sampai swing low) dibanding 10 candle sebelumnya, di kaki yang sama (selisih A - B)')
rows4 = []
for f, lab in (('buy_share', 'porsi lot top-3 pembeli (poin)'), ('asym', 'asimetri pembeli-penjual (poin)'), ('fl29', 'hari akumulasi (poin %)'), ('hhi', 'HHI net beli'), ('top1', 'porsi top-1 dari net beli (poin)')):
    N[f'd_{f}'] = N[f'{f}_A'] - N[f'{f}_B']; x = N[f'd_{f}'].dropna(); ci = boot_med(N.dropna(subset=[f'd_{f}']), f'd_{f}')
    rows4.append([lab, len(x), x.median(), ci[0], ci[1], 100 * (x > 0).mean()])
N['d_vol'] = 100 * (N.vol_A / N.vol_B - 1); x = N.d_vol.dropna(); ci = boot_med(N.dropna(subset=['d_vol']), 'd_vol'); rows4.append(['volume rata-rata (%)', len(x), x.median(), ci[0], ci[1], 100 * (x > 0).mean()])
print(pd.DataFrame(rows4, columns=['ukuran', 'n kaki', 'median selisih A-B', 'P5', 'P95', '% kaki A > B']).to_string(index=False, float_format=lambda v: f'{v:+.2f}' if abs(v) < 10 else f'{v:+.1f}'))
T.to_pickle(S + 'prerally_legs.pkl'); N.to_pickle(S + 'nearbottom.pkl')
