"""One stock at a time: swing highs / lows on the DAILY chart (ZigZag from raw OHLC, reversal threshold TH) and what each broker did inside every leg.
Usage: SWING_DATA_DIR=<dir> python3 stock_swings.py TICKER [threshold]   (reads <dir>/<ticker>_price.pkl and <ticker>_broker.pkl written by pull_stock.py)."""
import os, sys
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
S = os.path.join(os.environ.get('SWING_DATA_DIR', '.'), '')      # where pull_stock.py wrote the pickles; outputs go here too
TK = sys.argv[1].upper(); TH = float(sys.argv[2]) if len(sys.argv) > 2 else 0.20
P = pd.read_pickle(S + f'{TK.lower()}_price.pkl').reset_index(drop=True); B = pd.read_pickle(S + f'{TK.lower()}_broker.pkl')
h, l, o, c, v = (P[k].values.astype(float) for k in ('h', 'l', 'o', 'c', 'v')); n = len(P); dates = P.d.tolist(); di = {d: i for i, d in enumerate(dates)}


def zigzag(h, l, th):
    """ZigZag on raw highs/lows. A reversal is confirmed only on a candle AFTER the extreme candle (no zero-length legs)."""
    piv = []; trend = 0; hi, hi_i, lo, lo_i = h[0], 0, l[0], 0
    for i in range(1, len(h)):
        if h[i] > hi: hi, hi_i = h[i], i
        if l[i] < lo: lo, lo_i = l[i], i
        if trend == 0:
            if h[i] >= lo * (1 + th) and i > lo_i: piv.append((lo_i, 'L', lo)); trend = 1; hi, hi_i = h[i], i
            elif l[i] <= hi * (1 - th) and i > hi_i: piv.append((hi_i, 'H', hi)); trend = -1; lo, lo_i = l[i], i
        elif trend == 1:
            if l[i] <= hi * (1 - th) and i > hi_i: piv.append((hi_i, 'H', hi)); trend = -1; lo, lo_i = l[i], i
        else:
            if h[i] >= lo * (1 + th) and i > lo_i: piv.append((lo_i, 'L', lo)); trend = 1; hi, hi_i = h[i], i
    last = (hi_i, 'H', hi) if trend == 1 else (lo_i, 'L', lo) if trend == -1 else None
    return piv, last


piv, last = zigzag(h, l, TH); prov = last is not None and (not piv or last[0] != piv[-1][0])
allp = piv + ([last] if prov else [])
print(f'{TK}: {n} candle harian {dates[0]} .. {dates[-1]} | ambang pembalikan {TH:.0%} | {len(piv)} pivot terkonfirmasi' + (f' + 1 pivot sementara ({last[1]} {dates[last[0]]})' if prov else ''))

# ---- broker table (Regular board), aggregated over investor types, per candle
R = B[B.mb == 'Regular'].copy(); R = R[R.d.isin(di)]; R['i'] = R.d.map(di); brokers = sorted(R.b.unique()); bi = {b: k for k, b in enumerate(brokers)}; nb = len(brokers)
BL = np.zeros((n, nb)); SL = np.zeros((n, nb)); BV = np.zeros((n, nb)); SV = np.zeros((n, nb)); ii = R.i.values; bj = R.b.map(bi).values
for M, col in ((BL, 'bl'), (SL, 'sl'), (BV, 'bv'), (SV, 'sv')): np.add.at(M, (ii, bj), R[col].values)
NL = BL - SL; NV = BV - SV
# ---- broker names
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'terminal_api')); import pgq
pr = pgq.q("SELECT broker_code, broker_name, broker_type, broker_classification FROM public.\"IDX_Broker_Profile\""); prof = {r[0]: (r[1], r[2], r[3]) for r in pr.get('rows', [])}

legs = []
for k in range(len(allp) - 1):
    (i0, t0, p0), (i1, t1, p1) = allp[k], allp[k + 1]; a, b_ = i0 + 1, i1                 # candles after the start pivot, up to and including the end pivot
    nl = NL[a:b_ + 1].sum(0); tot = BL[a:b_ + 1].sum(); days = b_ - i0
    od = [x for x in np.argsort(-nl, kind='stable')[:3] if nl[x] > 0]; os_ = [x for x in np.argsort(nl, kind='stable')[:3] if nl[x] < 0]
    top1 = od[0] if od else None
    daily1 = (NL[a:b_ + 1, top1] > 0).mean() * 100 if top1 is not None else np.nan; daily3 = (NL[a:b_ + 1][:, od].sum(1) > 0).mean() * 100 if od else np.nan
    # FL29 style: share of days when the day's top-3 net buyers (value) beat the day's top-3 net sellers
    bal = []
    for d_ in range(a, b_ + 1):
        r_ = np.sort(NV[d_]); big = r_[::-1][:3]; sm = r_[:3]; tb = BV[d_].sum()
        if tb > 0: bal.append(np.where(big > 0, big, 0).sum() + np.where(sm < 0, sm, 0).sum())
    fl29 = 100 * np.mean(np.array(bal) > 0) if bal else np.nan
    sub = R[(R.i >= a) & (R.i <= b_)]; inv = sub[sub.b == (brokers[top1] if top1 is not None else '')].assign(net=lambda x: x.bl - x.sl).groupby('inv').net.sum().round(0).to_dict() if top1 is not None else {}
    nego = B[(B.mb == 'Nego') & (B.d >= dates[a]) & (B.d <= dates[b_])]; ng = (nego.groupby('b').apply(lambda x: (x.bl - x.sl).sum(), include_groups=False).sort_values(ascending=False) if len(nego) else pd.Series(dtype=float))
    legs.append(dict(k=k + 1, kind='NAIK' if p1 > p0 else 'TURUN', d0=dates[i0], p0=p0, d1=dates[i1], p1=p1, chg=100 * (p1 / p0 - 1), days=days, tot=tot, vol_avg=tot / days,
                     buy=[(brokers[x], nl[x]) for x in od], sell=[(brokers[x], nl[x]) for x in os_], buy_share=100 * sum(nl[x] for x in od) / tot if tot else np.nan, sell_share=-100 * sum(nl[x] for x in os_) / tot if tot else np.nan,
                     p1d=daily1, p3d=daily3, fl29=fl29, kpos=int((nl > 0).sum()), inv=inv, nego=(ng.index[0], ng.iloc[0]) if len(ng) and abs(ng.iloc[0]) > 0 else None, prov=(k == len(allp) - 2 and prov)))
print('\n== 1. Pivot (data mentah harian)')
rows = []
for k, (i, t, p) in enumerate(allp):
    prev = allp[k - 1] if k else None
    rows.append([k + 1, dates[i], 'swing HIGH' if t == 'H' else 'swing LOW', p, o[i], h[i], l[i], c[i], f'{v[i]:,.0f}', (f'{100 * (p / prev[2] - 1):+.0f}%' if prev else ''), (i - prev[0] if prev else ''), 'sementara' if (k == len(allp) - 1 and prov) else ''])
print(pd.DataFrame(rows, columns=['#', 'tanggal', 'jenis', 'harga pivot', 'open', 'high', 'low', 'close', 'volume', 'gerak dari pivot sebelumnya', 'candle', 'status']).to_string(index=False))
print('\n== 2. Apa yang dilakukan broker di setiap kaki (papan Regular, lot)')
for L in legs:
    nm = lambda b: f"{b} ({prof.get(b, ('?', '?', '?'))[2]})"
    print(f"\nKaki {L['k']} {L['kind']}: {L['d0']} ({L['p0']:.0f}) -> {L['d1']} ({L['p1']:.0f})  {L['chg']:+.0f}%, {L['days']} candle{' [kaki belum selesai]' if L['prov'] else ''} | total lot {L['tot']:,.0f}")
    print('   3 pembeli bersih terbesar :', '; '.join(f"{nm(b)} {x:,.0f} lot" for b, x in L['buy']) or '-', f"| porsi dari total lot {L['buy_share']:.1f}%")
    print('   3 penjual bersih terbesar :', '; '.join(f"{nm(b)} {x:,.0f} lot" for b, x in L['sell']) or '-', f"| porsi {L['sell_share']:.1f}%")
    print(f"   asimetri pembeli-penjual {L['buy_share'] - L['sell_share']:+.1f} poin | pembeli terbesar net beli {L['p1d']:.0f}% hari, kohort 3 pembeli {L['p3d']:.0f}% hari | hari akumulasi (gaya FL29) {L['fl29']:.0f}% | pembeli net: {L['kpos']} broker | tipe investor pembeli terbesar (net lot): {L['inv']}" + (f" | Nego: {L['nego'][0]} {L['nego'][1]:+,.0f} lot" if L['nego'] else ''))
pd.to_pickle(dict(allp=allp, legs=legs, prov=prov), S + f'{TK.lower()}_swings.pkl')

# ---- chart
top_acc = {}
for L in legs:
    for b, x in L['buy']: top_acc[b] = top_acc.get(b, 0) + abs(x)
pick = [b for b, _ in sorted(top_acc.items(), key=lambda z: -z[1])[:4]]
fig, ax = plt.subplots(3, 1, figsize=(17, 12), sharex=True, gridspec_kw={'height_ratios': [5, 1.3, 2.4]}); x = np.arange(n)
for i in range(n):
    col = '#1b9e77' if c[i] >= o[i] else '#d6403a'; ax[0].vlines(i, l[i], h[i], color=col, lw=0.8); ax[0].add_patch(Rectangle((i - 0.32, min(o[i], c[i])), 0.64, max(abs(c[i] - o[i]), 0.001 * c[i]), color=col))
for k in range(len(allp) - 1):
    (i0, _, p0), (i1, _, p1) = allp[k], allp[k + 1]; ax[0].axvspan(i0, i1, color='#d6403a' if p1 < p0 else '#1b9e77', alpha=0.07); ax[0].plot([i0, i1], [p0, p1], color='#444', lw=1.4, ls='--'); ax[0].annotate(f'{100 * (p1 / p0 - 1):+.0f}%', ((i0 + i1) / 2, (p0 + p1) / 2), fontsize=9, color='#222', ha='center', backgroundcolor='#ffffffcc')
for k, (i, t, p) in enumerate(allp):
    ax[0].scatter(i, p, marker='v' if t == 'H' else '^', s=70, color='#d6403a' if t == 'H' else '#1b9e77', zorder=5, edgecolor='k'); ax[0].annotate(f'{dates[i][5:]}\n{p:.0f}', (i, p), textcoords='offset points', xytext=(0, 12 if t == 'H' else -26), ha='center', fontsize=8)
ax[0].set_title(f'{TK} harian: swing high dan swing low (ZigZag, ambang {TH:.0%}) dari data mentah OHLC', fontsize=13); ax[0].set_ylabel('harga'); ax[0].grid(alpha=0.2)
ax[1].bar(x, v / 1e6, color=['#1b9e77' if c[i] >= o[i] else '#d6403a' for i in range(n)], width=0.8); ax[1].set_ylabel('volume (juta lembar)'); ax[1].grid(alpha=0.2)
cm = plt.get_cmap('tab10')
for j, b in enumerate(pick): ax[2].plot(x, np.cumsum(NL[:, bi[b]]), label=f"{b} ({prof.get(b, ('?', '?', '?'))[2]})", color=cm(j), lw=1.6)
ax[2].axhline(0, color='k', lw=0.6); ax[2].set_ylabel('posisi bersih kumulatif\n(lot, papan Regular)'); ax[2].legend(loc='upper left', fontsize=8, ncol=2); ax[2].grid(alpha=0.2)
for (i, _, _) in allp: ax[2].axvline(i, color='#999', lw=0.6, ls=':')
ticks = [i for i in range(n) if i == 0 or dates[i][:7] != dates[i - 1][:7]]; ax[2].set_xticks(ticks); ax[2].set_xticklabels([dates[i][:7] for i in ticks], rotation=0, fontsize=9); ax[2].set_xlim(-2, n + 1)
plt.tight_layout(); plt.savefig(S + f'{TK}_swings.png', dpi=110); print('\ngrafik disimpan:', S + f'{TK}_swings.png')
