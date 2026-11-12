"""Broker footprint of the decline legs HIGH -> LOW between V3 swing points (price ZigZag confirmed by Stochastic 14,3,3 in the 30/70 zone), one stock at a time, read-only on local pickles.
Usage: SWING_DATA_DIR=<dir> python3 v3_legs.py TICKER [TICKER ...]    (needs <dir>/<t>_price.pkl, <t>_broker.pkl from pull_stock.py and <t>_result.json from analyze_stock.py for the stock's own threshold)
A "pre-rally leg" = a V3 decline leg H(k) -> L(k+1) that is followed by H(k+2): the window is the candle after the high (the high itself is not included) through the low candle.
Regular board, lots, every investor type merged per broker. Per leg: concentration of net buying (top-3 net-buyer share, HHI of net-buy lots, top-1 share, number of net buyers), buyer-dominant days (FL29 style),
the cumulative position of the top accumulator (path and how much of it came in the last third), the top-3 cohort's gross-buy VWAP and the close's underwater % (reading 1), last third vs first third of the leg,
what the same cohort and the top buyer do in the rally leg that follows, and a CONTROL: where the leg's value falls among all windows of the same length in the same stock that ended after a decline of at least the threshold.
Hindsight: V3 pivots are known only afterwards. Exploratory: few legs, few stocks."""
import os, sys, json
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.ticker import FuncFormatter
from swing_lib import stochastic, zigzag, combine
S = os.path.join(os.environ.get('SWING_DATA_DIR', '.'), ''); TKS = [t.upper() for t in sys.argv[1:]]; WIN = 5
LAB = lambda k: chr(65 + k) if k < 26 else chr(65 + k // 26 - 1) + chr(65 + k % 26)
try:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'terminal_api')); import pgq
except Exception: pgq = None


def profile(codes):
    if pgq is None: return {}
    try:
        r = pgq.q("SELECT broker_code, broker_classification FROM public.\"IDX_Broker_Profile\" WHERE broker_code IN (" + ','.join("'" + x.replace("'", '') + "'" for x in codes) + ')')
        return {a: b for a, b in r.get('rows', [])}
    except Exception: return {}


def analyse(tk):
    P = pd.read_pickle(S + f'{tk.lower()}_price.pkl').reset_index(drop=True); B = pd.read_pickle(S + f'{tk.lower()}_broker.pkl'); th = json.load(open(S + f'{tk.lower()}_result.json'))['th']
    h, l, o, c, v = (P[k].values.astype(float) for k in ('h', 'l', 'o', 'c', 'v')); n = len(P); dates = P.d.tolist(); di = {d: i for i, d in enumerate(dates)}
    K, _ = stochastic(h, l, c); v1 = zigzag(h, l, th); v3, _ = combine(v1, K, WIN)
    R = B[(B.mb == 'Regular') & B.d.isin(di)].copy(); R['i'] = R.d.map(di); brokers = sorted(R.b.unique()); bi = {b: k for k, b in enumerate(brokers)}; nb = len(brokers); prof = profile(brokers); nm = lambda b: f'{b} ({prof.get(b, "?")})'
    M = {k: np.zeros((n, nb)) for k in ('bl', 'sl', 'bv', 'sv')}; ii = R.i.values; bj = R.b.map(bi).values
    for k in M: np.add.at(M[k], (ii, bj), R[k].values)
    BL, SL, BV, SV = M['bl'], M['sl'], M['bv'], M['sv']; NL = BL - SL; NV = BV - SV; z = np.zeros((1, nb)); cNL = np.vstack([z, np.cumsum(NL, 0)]); cBL = np.vstack([z, np.cumsum(BL, 0)]); cBV = np.vstack([z, np.cumsum(BV, 0)])
    pos = np.zeros(n); valid = np.zeros(n)
    for d_ in range(n):
        if BV[d_].sum() > 0:
            r_ = np.sort(NV[d_]); valid[d_] = 1; pos[d_] = float(np.where(r_[::-1][:3] > 0, r_[::-1][:3], 0).sum() + np.where(r_[:3] < 0, r_[:3], 0).sum() > 0)
    cpos = np.concatenate([[0.0], np.cumsum(pos)]); cval = np.concatenate([[0.0], np.cumsum(valid)])

    def feats(a, b):
        """broker features of candles a..b (inclusive)"""
        nl = cNL[b + 1] - cNL[a]; tot = (cBL[b + 1] - cBL[a]).sum()
        if tot <= 0: return None
        od = [x for x in np.argsort(-nl, kind='stable')[:3] if nl[x] > 0]; os_ = [x for x in np.argsort(nl, kind='stable')[:3] if nl[x] < 0]; pp = nl[nl > 0]
        if not od or not os_: return None
        bs = 100 * nl[od].sum() / tot; ss = -100 * nl[os_].sum() / tot; nvld = cval[b + 1] - cval[a]
        return dict(buy_share=bs, sell_share=ss, asym=bs - ss, hhi=float(((pp / pp.sum()) ** 2).sum()), k=int(len(pp)), top1=100 * pp.max() / pp.sum(), fl29=100 * (cpos[b + 1] - cpos[a]) / nvld if nvld else np.nan, od=od, nl=nl, tot=tot)

    rows, legs = [], []
    for k in range(len(v3) - 2):
        (iH, tH, pH, _), (iL, tL, pL, _), (iN, tN, pN, ciN) = v3[k], v3[k + 1], v3[k + 2]
        if not (tH == 'H' and tL == 'L' and tN == 'H'): continue
        a, b = iH + 1, iL; m = b - a + 1; F = feats(a, b)
        if F is None: continue
        od = F['od']; x1 = od[0]; cum = np.cumsum(NL[a:b + 1, x1]); third = max(m // 3, 1)
        vw = (cBV[b + 1] - cBV[a])[od].sum() / (100 * (cBL[b + 1] - cBL[a])[od].sum()); mv = (cBV[b + 1] - cBV[a]).sum() / (100 * (cBL[b + 1] - cBL[a]).sum())
        last3 = cum[-1] - (cum[m - third - 1] if m - third - 1 >= 0 else 0.0); lastshare = 100 * last3 / cum[-1] if cum[-1] > 0 else np.nan
        F1 = feats(a, a + third - 1) if m >= 6 else None; F3 = feats(b - third + 1, b) if m >= 6 else None
        a2, b2 = iL + 1, iN; G = feats(a2, b2)
        cohort_rally = float((cNL[b2 + 1] - cNL[a2])[od].sum()) if G else np.nan; rt = float((cBL[b2 + 1] - cBL[a2]).sum()); top1r = int(np.argmax(cNL[b2 + 1] - cNL[a2])) if G else None
        # control: windows of the same length ending after a decline >= th (peak high in the window to the low of the last candle), same stock
        ctrl = {kk: [] for kk in ('buy_share', 'sell_share', 'asym', 'hhi', 'top1', 'fl29')}; nctrl = 0
        for t in range(m - 1, n):
            w0 = t - m + 1
            if l[t] / h[w0:t + 1].max() - 1 > -th: continue
            Fw = feats(w0, t)
            if Fw is None: continue
            nctrl += 1
            for kk in ctrl: ctrl[kk].append(Fw[kk])
        pct = {kk: (100 * np.mean(np.array(vv) <= F[kk]) if nctrl >= 15 else np.nan) for kk, vv in ctrl.items()}
        rows.append(dict(tk=tk, leg=f'{LAB(k)}→{LAB(k + 1)}', rally_leg=f'{LAB(k + 1)}→{LAB(k + 2)}', anchor=dates[iH], pH=pH, low=dates[iL], pL=pL, drop=100 * (pL / pH - 1), m=m, tot=F['tot'], buy_share=F['buy_share'], sell_share=F['sell_share'], asym=F['asym'],
                         hhi=F['hhi'], even=1 / F['k'], k=F['k'], top1=F['top1'], fl29=F['fl29'], top1_broker=nm(brokers[x1]), top1_net=float(cum[-1]), top1_share_of_leg=100 * cum[-1] / F['tot'], top1_last3=lastshare,
                         buy_share_first=F1['buy_share'] if F1 else np.nan, buy_share_last=F3['buy_share'] if F3 else np.nan, hhi_first=F1['hhi'] if F1 else np.nan, hhi_last=F3['hhi'] if F3 else np.nan,
                         fl29_first=F1['fl29'] if F1 else np.nan, fl29_last=F3['fl29'] if F3 else np.nan, vwap=vw, uw=100 * (c[iL] / vw - 1), uw_low=100 * (l[iL] / vw - 1), uw_mkt=100 * (c[iL] / mv - 1),
                         cohort=', '.join(brokers[x] for x in od), rally=100 * (pN / pL - 1), rally_days=iN - iL, rally_prov=ciN is None, cohort_rally_net=cohort_rally, cohort_rally_share=100 * cohort_rally / rt if G and rt > 0 else np.nan,
                         top1_rally=nm(brokers[top1r]) if top1r is not None else '?', top1_in_cohort=bool(top1r in od) if top1r is not None else False, rally_buy_share=G['buy_share'] if G else np.nan, rally_hhi=G['hhi'] if G else np.nan,
                         n_ctrl=nctrl, **{f'pct_{kk}': vv for kk, vv in pct.items()}))
        legs.append((iH, iL, iN, od))
    # ---- chart
    acc = {}
    for (iH, iL, iN, od), r in zip(legs, rows):
        for x in od: acc[x] = acc.get(x, 0) + float((cNL[iL + 1] - cNL[iH + 1])[x])
    pick = [x for x, _ in sorted(acc.items(), key=lambda z_: -z_[1])[:4]]
    fig, ax = plt.subplots(3, 1, figsize=(19, 12), sharex=True, gridspec_kw={'height_ratios': [5.5, 1.2, 2.3]}); ax[0].set_yscale('log'); x_ = np.arange(n)
    for i in range(n):
        col = '#1b9e77' if c[i] >= o[i] else '#d6403a'; ax[0].vlines(i, l[i], h[i], color=col, lw=0.8); ax[0].add_patch(Rectangle((i - 0.32, min(o[i], c[i])), 0.64, max(abs(c[i] - o[i]), 0.003 * c[i]), color=col))
    for k in range(len(v3) - 1):
        (i0, _, p0, _), (i1, _, p1, _) = v3[k], v3[k + 1]; ax[0].axvspan(i0, i1, color='#d6403a' if p1 < p0 else '#1b9e77', alpha=0.07); ax[0].plot([i0, i1], [p0, p1], color='#444', lw=1.4, ls='--')
        if i1 - i0 >= 6: ax[0].annotate(f'{100 * (p1 / p0 - 1):+.0f}%', ((i0 + i1) / 2, np.sqrt(p0 * p1)), fontsize=8, ha='center', va='center', bbox=dict(boxstyle='round,pad=0.15', fc='white', ec='none', alpha=0.75))
    for k, (i, t, p, ci) in enumerate(v3):
        ax[0].scatter(i, p, marker='v' if t == 'H' else '^', s=60, facecolor='white' if ci is None else ('#d6403a' if t == 'H' else '#1b9e77'), edgecolor='#d6403a' if t == 'H' else '#1b9e77', linewidth=1.4 if ci is None else 0.8, zorder=5)
        ax[0].annotate(f'{LAB(k)}  {dates[i][2:7]} {p:g}', (i, p), textcoords='offset points', xytext=(0, 11 + 8 * (k % 2) if t == 'H' else -(20 + 8 * (k % 2))), ha='center', fontsize=8, fontweight='bold', bbox=dict(boxstyle='round,pad=0.1', fc='white', ec='none', alpha=0.7))
    for r in rows:
        ia, ib = di[r['anchor']], di[r['low']]; ax[0].hlines(r['vwap'], ia, ib, colors='#7b3fbf', lw=2.2, zorder=4)
        if ib - ia >= 4: ax[0].annotate(f"{r['leg']}  {r['uw']:+.0f}%", ((ia + ib) / 2, r['vwap']), textcoords='offset points', xytext=(0, 6), ha='center', fontsize=7.5, color='#5a2a99', fontweight='bold', bbox=dict(boxstyle='round,pad=0.1', fc='white', ec='none', alpha=0.8), zorder=6)
    ax[0].yaxis.set_major_formatter(FuncFormatter(lambda v_, _: f'{v_:g}')); ax[0].yaxis.set_minor_formatter(FuncFormatter(lambda v_, _: f'{v_:g}')); ax[0].grid(alpha=0.2, which='both')
    ax[0].set_title(f'{tk} V3 (ZigZag {th:.0%} + stochastic 14,3,3 zona 30/70 dalam +-{WIN} candle): {len(v3)} titik. Ungu = VWAP beli kohort top-3 dari puncak ke swing low; angka = underwater pada close swing low', fontsize=11)
    ax[1].bar(x_, v / 1e6, color=['#1b9e77' if c[i] >= o[i] else '#d6403a' for i in range(n)], width=0.8); ax[1].set_ylabel('volume (juta)'); ax[1].grid(alpha=0.2); cm = plt.get_cmap('tab10')
    for j, x in enumerate(pick): ax[2].plot(x_, np.cumsum(NL[:, x]), label=nm(brokers[x]), color=cm(j), lw=1.6)
    ax[2].axhline(0, color='k', lw=0.6); ax[2].set_ylabel('posisi bersih kumulatif\n(lot, Regular)'); ax[2].legend(loc='upper left', fontsize=8, ncol=2); ax[2].grid(alpha=0.2)
    for (i, _, _, _) in v3: ax[2].axvline(i, color='#999', lw=0.6, ls=':')
    ticks = [i for i in range(n) if i == 0 or dates[i][:7] != dates[i - 1][:7]]; ax[2].set_xticks(ticks); ax[2].set_xticklabels([dates[i][:7] for i in ticks], fontsize=8); ax[2].set_xlim(-2, n + 1)
    plt.tight_layout(); png = S + f'{tk}_v3_legs.png'; plt.savefig(png, dpi=90); plt.close(fig)
    return rows, v3, dates, th, png


pd.set_option('display.width', 250); pd.set_option('display.max_columns', 60); pd.set_option('display.float_format', lambda v: f'{v:,.1f}')
allrows = []
for tk in TKS:
    rows, v3, dates, th, png = analyse(tk); allrows += rows
    print(f"\n######## {tk}: ambang {th:.0%}, {len(v3)} titik V3, {len(rows)} kaki turun pra-rally ########")
    print('V3: ' + '; '.join(f"{LAB(k)} {t}{dates[i][2:7]} {p:g}" for k, (i, t, p, _) in enumerate(v3)))
    for r in rows:
        print(f"\nKaki {r['leg']}: {r['anchor']} ({r['pH']:g}) -> {r['low']} ({r['pL']:g})  {r['drop']:+.0f}%, {r['m']} candle, {r['tot']:,.0f} lot | rally {r['rally_leg']}: {r['rally']:+.0f}% dalam {r['rally_days']} candle" + (' [belum selesai]' if r['rally_prov'] else ''))
        print(f"   konsentrasi: top-3 pembeli {r['buy_share']:.1f}% | top-3 penjual {r['sell_share']:.1f}% | asimetri {r['asym']:+.1f} | {r['k']} broker net beli | HHI net beli {r['hhi']:.2f} (merata {r['even']:.2f}) | top-1 {r['top1']:.0f}% dari net beli | hari akumulasi (FL29) {r['fl29']:.0f}%")
        print(f"   top akumulator {r['top1_broker']}: net {r['top1_net']:,.0f} lot ({r['top1_share_of_leg']:.1f}% dari total lot), {r['top1_last3']:.0f}% dari net-nya datang di sepertiga terakhir kaki | kohort {r['cohort']}")
        print(f"   sepertiga awal -> akhir: porsi top-3 {r['buy_share_first']:.1f} -> {r['buy_share_last']:.1f}; HHI {r['hhi_first']:.2f} -> {r['hhi_last']:.2f}; FL29 {r['fl29_first']:.0f}% -> {r['fl29_last']:.0f}%")
        print(f"   VWAP kohort {r['vwap']:.1f}: underwater {r['uw']:+.1f}% pada close ({r['uw_low']:+.1f}% pada low) | VWAP pasar {r['uw_mkt']:+.1f}%")
        print(f"   saat rally: kohort net {r['cohort_rally_net']:,.0f} lot ({r['cohort_rally_share']:.1f}% dari lot rally); pembeli terbesar rally {r['top1_rally']}{' (anggota kohort)' if r['top1_in_cohort'] else ''}; porsi top-3 rally {r['rally_buy_share']:.1f}%, HHI rally {r['rally_hhi']:.2f}")
        print(f"   pembanding ({r['n_ctrl']} jendela sepanjang {r['m']} candle yang berakhir sesudah turun >= {th:.0%}): persentil kaki ini = porsi top-3 {r['pct_buy_share']:.0f}, penjual {r['pct_sell_share']:.0f}, asimetri {r['pct_asym']:.0f}, HHI {r['pct_hhi']:.0f}, top-1 {r['pct_top1']:.0f}, FL29 {r['pct_fl29']:.0f}")
    print('grafik:', png)
T = pd.DataFrame(allrows); T.to_pickle(S + 'v3_legs_' + '_'.join(TKS) + '.pkl')
if len(TKS) > 1:
    print(f'\n######## GABUNGAN {len(TKS)} saham, {len(T)} kaki turun pra-rally ########')
    print(T[['tk', 'leg', 'anchor', 'low', 'drop', 'm', 'buy_share', 'asym', 'hhi', 'top1', 'fl29', 'top1_last3', 'uw', 'rally', 'rally_days']].to_string(index=False))
    q = T[['drop', 'm', 'buy_share', 'sell_share', 'asym', 'hhi', 'k', 'top1', 'fl29', 'top1_share_of_leg', 'top1_last3', 'uw', 'rally', 'rally_days']].quantile([.25, .5, .75]).T.rename(columns={.25: 'P25', .5: 'P50', .75: 'P75'}); print('\nSebaran (semua kaki):'); print(q.to_string())
    print('\nPersentil kaki di antara jendela pembanding (50 = biasa; di bawah 25 atau di atas 75 = tidak biasa). Median dan jumlah kaki di atas 75 / di bawah 25:')
    for kk in ('buy_share', 'sell_share', 'asym', 'hhi', 'top1', 'fl29'):
        s = T['pct_' + kk].dropna(); print(f"   {kk}: median {s.median():.0f}, di atas 75: {int((s > 75).sum())}, di bawah 25: {int((s < 25).sum())} dari {len(s)} kaki")
    print('\nSepertiga akhir dibanding sepertiga awal kaki (selisih median, dan jumlah kaki yang naik):')
    for kk in ('buy_share', 'hhi', 'fl29'):
        d = (T[kk + '_last'] - T[kk + '_first']).dropna(); print(f"   {kk}: median selisih {d.median():+.2f}, naik pada {int((d > 0).sum())} dari {len(d)} kaki")
    print(f"\nKohort kaki turun juga pembeli terbesar di kaki rally: {int(T.top1_in_cohort.sum())} dari {len(T)}; kohort net beli di rally pada {int((T.cohort_rally_net > 0).sum())} dari {len(T)} kaki")
    print('\nKorelasi peringkat dengan besar rally sesudahnya (n kecil, hanya deskriptif):')
    for kk in ('drop', 'm', 'buy_share', 'asym', 'hhi', 'top1', 'fl29', 'top1_last3', 'uw'):
        d = T[[kk, 'rally']].dropna(); print(f"   {kk}: rho {d[kk].rank().corr(d['rally'].rank()):+.2f} (n={len(d)})")
