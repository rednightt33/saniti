"""One stock at a time: swing highs/lows on the DAILY chart, broker behaviour inside every leg, and the anchored top-3 buy VWAP of the pre-rally pullback (user reading 1).
Usage: SWING_DATA_DIR=<dir> python3 analyze_stock.py TICKER [threshold]   (reads <dir>/<ticker>_price.pkl and <ticker>_broker.pkl from pull_stock.py)
Swing: ZigZag on raw high/low; threshold = 5 x the stock's median daily range, rounded to 5% (15%..50%) unless given; a reversal is confirmed only on a candle AFTER the extreme candle.
Legs: Regular board, lots, every investor type merged per broker; the other boards (Nego, Cash) are reported separately. Pivots are known only in hindsight (confirmation lag is printed)."""
import os, sys, json
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
S = os.path.join(os.environ.get('SWING_DATA_DIR', '.'), '')
TK = sys.argv[1].upper()
P = pd.read_pickle(S + f'{TK.lower()}_price.pkl').reset_index(drop=True); B = pd.read_pickle(S + f'{TK.lower()}_broker.pkl')
h, l, o, c, v = (P[k].values.astype(float) for k in ('h', 'l', 'o', 'c', 'v')); n = len(P); dates = P.d.tolist(); di = {d: i for i, d in enumerate(dates)}
RNG = float(np.median((h - l) / c)); TH = float(sys.argv[2]) if len(sys.argv) > 2 else float(np.clip(round(5 * RNG / 0.05) * 0.05, 0.15, 0.50))


def zigzag(h, l, th):
    piv = []; trend = 0; hi, hi_i, lo, lo_i = h[0], 0, l[0], 0
    for i in range(1, len(h)):
        if h[i] > hi: hi, hi_i = h[i], i
        if l[i] < lo: lo, lo_i = l[i], i
        if trend == 0:
            if h[i] >= lo * (1 + th) and i > lo_i: piv.append((lo_i, 'L', lo, i)); trend = 1; hi, hi_i = h[i], i
            elif l[i] <= hi * (1 - th) and i > hi_i: piv.append((hi_i, 'H', hi, i)); trend = -1; lo, lo_i = l[i], i
        elif trend == 1:
            if l[i] <= hi * (1 - th) and i > hi_i: piv.append((hi_i, 'H', hi, i)); trend = -1; lo, lo_i = l[i], i
        else:
            if h[i] >= lo * (1 + th) and i > lo_i: piv.append((lo_i, 'L', lo, i)); trend = 1; hi, hi_i = h[i], i
    last = (hi_i, 'H', hi, None) if trend == 1 else (lo_i, 'L', lo, None) if trend == -1 else None
    return piv, last


piv, last = zigzag(h, l, TH); prov = last is not None and (not piv or last[0] != piv[-1][0]); allp = piv + ([last] if prov else [])
print(f'{TK}: {n} candle harian {dates[0]} .. {dates[-1]} | median rentang harian {100 * RNG:.1f}% -> ambang swing {TH:.0%} | {len(piv)} pivot terkonfirmasi' + (f' + 1 sementara ({last[1]} {dates[last[0]]})' if prov else ''))

# ---- Regular board per candle, aggregated over investor types
R = B[B.mb == 'Regular'].copy(); R = R[R.d.isin(di)]; R['i'] = R.d.map(di); brokers = sorted(R.b.unique()); bi = {b: k for k, b in enumerate(brokers)}; nb = len(brokers)
BL = np.zeros((n, nb)); SL = np.zeros((n, nb)); BV = np.zeros((n, nb)); SV = np.zeros((n, nb)); ii = R.i.values; bj = R.b.map(bi).values
for M, col in ((BL, 'bl'), (SL, 'sl'), (BV, 'bv'), (SV, 'sv')): np.add.at(M, (ii, bj), R[col].values)
NL = BL - SL; NV = BV - SV; OT = B[(B.mb != 'Regular') & B.d.isin(di)].copy()
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'terminal_api')); import pgq
codes = sorted(set(B.b)); pr = pgq.q("SELECT broker_code, broker_name, broker_type, broker_classification FROM public.\"IDX_Broker_Profile\" WHERE broker_code IN (" + ','.join("'" + x.replace("'", '') + "'" for x in codes) + ')')
prof = {r[0]: (r[1], r[2], r[3]) for r in pr.get('rows', [])}; cls = lambda b: prof.get(b, ('?', '?', '?'))[2]; nm = lambda b: f'{b} ({cls(b)})'


def top_idx(vec, k=3, sign=1): return [x for x in np.argsort(-sign * vec, kind='stable')[:k] if sign * vec[x] > 0]


def leg_stats(a, b_):
    nl = NL[a:b_ + 1].sum(0); tot = BL[a:b_ + 1].sum(); od = top_idx(nl, 3, 1); os_ = top_idx(nl, 3, -1); pos = nl[nl > 0]
    hhi = float(((pos / pos.sum()) ** 2).sum()) if len(pos) else np.nan; p1 = (NL[a:b_ + 1, od[0]] > 0).mean() * 100 if od else np.nan
    bal = [np.where(np.sort(NV[d_])[::-1][:3] > 0, np.sort(NV[d_])[::-1][:3], 0).sum() + np.where(np.sort(NV[d_])[:3] < 0, np.sort(NV[d_])[:3], 0).sum() for d_ in range(a, b_ + 1) if BV[d_].sum() > 0]
    inv = R[(R.i >= a) & (R.i <= b_) & (R.b == brokers[od[0]])].assign(net=lambda x: x.bl - x.sl).groupby('inv').net.sum().round(0).to_dict() if od else {}
    return dict(tot=tot, buy=[(brokers[x], nl[x]) for x in od], sell=[(brokers[x], nl[x]) for x in os_], buy_share=100 * sum(nl[x] for x in od) / tot if tot else np.nan,
                sell_share=-100 * sum(nl[x] for x in os_) / tot if tot else np.nan, persist1=p1, fl29=100 * np.mean(np.array(bal) > 0) if bal else np.nan, kpos=int((nl > 0).sum()), hhi=hhi, even=1 / len(pos) if len(pos) else np.nan,
                top1_net=100 * pos.max() / pos.sum() if len(pos) else np.nan, top3_net=100 * np.sort(pos)[::-1][:3].sum() / pos.sum() if len(pos) else np.nan, inv=inv)


def other_boards(a, b_):
    x = OT[(OT.d >= dates[a]) & (OT.d <= dates[b_])]
    if not len(x): return None
    g = x.assign(net=lambda r: r.bl - r.sl).groupby('b').agg(net=('net', 'sum'), bl=('bl', 'sum'), bv=('bv', 'sum')); g['px'] = g.bv / (100 * g.bl.replace(0, np.nan)); top = g.net.abs().sort_values(ascending=False).index[0]
    return top, float(g.loc[top, 'net']), float(g.loc[top, 'px']) if np.isfinite(g.loc[top, 'px']) else np.nan, len(x)


legs = []
for k in range(len(allp) - 1):
    (i0, t0, p0, _), (i1, t1, p1, _) = allp[k], allp[k + 1]; st = leg_stats(i0 + 1, i1); st.update(leg=k + 1, kind='NAIK' if p1 > p0 else 'TURUN', d0=dates[i0], p0=p0, d1=dates[i1], p1=p1, chg=100 * (p1 / p0 - 1), days=i1 - i0, other=other_boards(i0 + 1, i1), prov=(k == len(allp) - 2 and prov)); legs.append(st)

print('\n== 1. Pivot (data mentah harian)')
rows = []
for k, (i, t, p, ci) in enumerate(allp):
    prev = allp[k - 1] if k else None
    rows.append([k + 1, dates[i], 'swing HIGH' if t == 'H' else 'swing LOW', p, o[i], h[i], l[i], c[i], (dates[ci] if ci is not None else 'sementara'), (ci - i if ci is not None else ''), (f'{100 * (p / prev[2] - 1):+.0f}%' if prev else '')])
print(pd.DataFrame(rows, columns=['#', 'tanggal', 'jenis', 'harga pivot', 'open', 'high', 'low', 'close', 'dikonfirmasi', 'jeda candle', 'gerak']).to_string(index=False))
print('\n== 2. Broker per kaki (Regular, lot)')
for L in legs:
    print(f"\nKaki {L['leg']} {L['kind']}: {L['d0']} ({L['p0']:.0f}) -> {L['d1']} ({L['p1']:.0f})  {L['chg']:+.0f}%, {L['days']} candle{' [belum selesai]' if L['prov'] else ''} | total lot {L['tot']:,.0f}")
    print('   3 pembeli bersih :', '; '.join(f"{nm(b)} {x:,.0f}" for b, x in L['buy']) or '-', f"| porsi lot {L['buy_share']:.1f}%")
    print('   3 penjual bersih :', '; '.join(f"{nm(b)} {x:,.0f}" for b, x in L['sell']) or '-', f"| porsi lot {L['sell_share']:.1f}%")
    print(f"   asimetri {L['buy_share'] - L['sell_share']:+.1f} poin | pembeli terbesar net beli {L['persist1']:.0f}% hari | hari akumulasi (FL29) {L['fl29']:.0f}% | {L['kpos']} broker net beli | HHI net beli {L['hhi']:.2f} (merata {L['even']:.2f}) | top-1 {L['top1_net']:.0f}% dan top-3 {L['top3_net']:.0f}% dari net beli | tipe investor pembeli terbesar {L['inv']}" + (f" | papan lain: {L['other'][0]} net {L['other'][1]:+,.0f} lot" + (f" @ {L['other'][2]:.0f}" if np.isfinite(L['other'][2]) else ' (hanya jual)') if L['other'] else ''))

print('\n== 3. Tafsir 1: VWAP beli kohort top-3 dari puncak pra-rally sampai swing low (anchor = puncak, tidak ikut)')
t1 = []
for k in range(len(allp) - 2):
    (iH, tH, pH, _), (iL, tL, pL, _), (iN, tN, pN, _) = allp[k], allp[k + 1], allp[k + 2]
    if not (tH == 'H' and tL == 'L' and tN == 'H'): continue
    a, b_ = iH + 1, iL; nl = NL[a:b_ + 1].sum(0); od = top_idx(nl, 3, 1)
    if not od: continue
    cb, cl = BV[a:b_ + 1][:, od].sum(), BL[a:b_ + 1][:, od].sum(); vw = cb / (100 * cl); mv = BV[a:b_ + 1].sum() / (100 * BL[a:b_ + 1].sum()); tot = BL[a:b_ + 1].sum()
    mem = '; '.join(f"{brokers[x]} net {nl[x]:,.0f} @ {BV[a:b_ + 1, x].sum() / (100 * BL[a:b_ + 1, x].sum()):.1f}" for x in od)
    ob = OT[(OT.d >= dates[a]) & (OT.d <= dates[b_]) & (OT.b.isin([brokers[x] for x in od])) & (OT.bl > 0)]; ng = (ob.bv.sum() / (100 * ob.bl.sum()), ob.bl.sum()) if len(ob) else None
    rec = dict(anchor=dates[iH], pH=pH, low_date=dates[iL], pL=pL, close=c[iL], low=l[iL], window=b_ - iH, vwap=vw, mkt_vwap=mv, uw_close=100 * (c[iL] / vw - 1), uw_low=100 * (l[iL] / vw - 1), uw_mkt=100 * (c[iL] / mv - 1),
               net=float(nl[od].sum()), share=100 * float(nl[od].sum()) / tot, members=mem, rally=100 * (pN / pL - 1), rally_days=iN - iL, nego=ng, drop=100 * (pL / pH - 1)); t1.append(rec)
    print(f"\nPuncak {rec['anchor']} ({pH:.0f}) -> swing low {rec['low_date']} (close {c[iL]:.0f}, low {l[iL]:.0f}), {rec['window']} candle, turun {rec['drop']:+.0f}% | rally sesudahnya {rec['rally']:+.0f}% dalam {rec['rally_days']} candle")
    print(f"   kohort top-3: {mem} | net kohort {rec['net']:,.0f} lot = {rec['share']:.1f}% dari {tot:,.0f} lot")
    print(f"   VWAP beli kohort {vw:.1f} | underwater pada close swing low {rec['uw_close']:+.1f}% (pada low {rec['uw_low']:+.1f}%) | pembanding VWAP seluruh pasar {mv:.1f} ({rec['uw_mkt']:+.1f}%)" + (f" | papan lain: kohort membeli {ng[1]:,.0f} lot @ {ng[0]:.1f}" if ng else ''))
json.dump(dict(ticker=TK, th=TH, rng=RNG, pivots=[(dates[i], t, p, (dates[ci] if ci is not None else None)) for i, t, p, ci in allp], legs=legs, tafsir1=t1), open(S + f'{TK.lower()}_result.json', 'w'), default=lambda x: float(x) if isinstance(x, (np.floating, np.integer)) else str(x), ensure_ascii=False)

# ---- chart
acc = {}
for L in legs:
    if L['kind'] == 'TURUN':
        for b, x in L['buy']: acc[b] = acc.get(b, 0) + abs(x)
pick = [b for b, _ in sorted(acc.items(), key=lambda z: -z[1])[:4]]
fig, ax = plt.subplots(3, 1, figsize=(17, 12), sharex=True, gridspec_kw={'height_ratios': [5, 1.3, 2.4]}); x = np.arange(n)
for i in range(n):
    col = '#1b9e77' if c[i] >= o[i] else '#d6403a'; ax[0].vlines(i, l[i], h[i], color=col, lw=0.8); ax[0].add_patch(Rectangle((i - 0.32, min(o[i], c[i])), 0.64, max(abs(c[i] - o[i]), 0.001 * c[i]), color=col))
for k in range(len(allp) - 1):
    (i0, _, p0, _), (i1, _, p1, _) = allp[k], allp[k + 1]; ax[0].axvspan(i0, i1, color='#d6403a' if p1 < p0 else '#1b9e77', alpha=0.07); ax[0].plot([i0, i1], [p0, p1], color='#444', lw=1.4, ls='--'); ax[0].annotate(f'{100 * (p1 / p0 - 1):+.0f}%', ((i0 + i1) / 2, (p0 + p1) / 2), fontsize=9, ha='center', backgroundcolor='#ffffffcc')
for k, (i, t, p, _) in enumerate(allp): ax[0].scatter(i, p, marker='v' if t == 'H' else '^', s=70, color='#d6403a' if t == 'H' else '#1b9e77', zorder=5, edgecolor='k'); ax[0].annotate(f'{dates[i][2:7]}\n{p:g}', (i, p), textcoords='offset points', xytext=(0, 12 if t == 'H' else -26), ha='center', fontsize=8)
for r in t1:
    ia, ib = di[r['anchor']], di[r['low_date']]; ax[0].hlines(r['vwap'], ia, ib, colors='#7b3fbf', lw=2.2); ax[0].annotate(f"VWAP top-3 {r['vwap']:.0f}\n{r['uw_close']:+.0f}% di swing low", ((ia + ib) / 2, r['vwap']), textcoords='offset points', xytext=(0, 8), ha='center', fontsize=8, color='#7b3fbf', backgroundcolor='#ffffffcc')
ax[0].set_title(f'{TK} harian: swing (ZigZag {TH:.0%}) dan VWAP beli kohort top-3 dari puncak pra-rally ke swing low (ungu)', fontsize=13); ax[0].set_ylabel('harga'); ax[0].grid(alpha=0.2)
ax[1].bar(x, v / 1e6, color=['#1b9e77' if c[i] >= o[i] else '#d6403a' for i in range(n)], width=0.8); ax[1].set_ylabel('volume (juta lembar)'); ax[1].grid(alpha=0.2); cm = plt.get_cmap('tab10')
for j, b in enumerate(pick): ax[2].plot(x, np.cumsum(NL[:, bi[b]]), label=nm(b), color=cm(j), lw=1.6)
ax[2].axhline(0, color='k', lw=0.6); ax[2].set_ylabel('posisi bersih kumulatif\n(lot, Regular)'); ax[2].legend(loc='upper left', fontsize=8, ncol=2); ax[2].grid(alpha=0.2)
for (i, _, _, _) in allp: ax[2].axvline(i, color='#999', lw=0.6, ls=':')
ticks = [i for i in range(n) if i == 0 or dates[i][:7] != dates[i - 1][:7]]; ax[2].set_xticks(ticks); ax[2].set_xticklabels([dates[i][:7] for i in ticks], fontsize=8); ax[2].set_xlim(-2, n + 1)
plt.tight_layout(); plt.savefig(S + f'{TK}_swings.png', dpi=110); print('\ngrafik:', S + f'{TK}_swings.png')
