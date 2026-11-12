"""Three ways to find swing points on one stock's DAILY chart, drawn together for comparison (research, read-only, local).
Usage: SWING_DATA_DIR=<dir> python3 stoch_zigzag.py TICKER [price_threshold=0.30] [window=5]      (needs <dir>/<ticker>_price.pkl from pull_stock.py)
  V1  price ZigZag (analyze_stock.py): a reversal of >= threshold from the running extreme, confirmed only on a LATER candle; pivot = the extreme candle's high/low.
  V2  stochastic only (user 2026-11-12): Stochastic Slow 14,3,3 as in the terminal (raw %K = 100 (C-LL14)/(HH14-LL14), K = SMA3(raw), D = SMA3(K); 0 on a zero range).
      Rule: K falls to <= 30, later K rises to >= 70  -> a "swing low" at the CLOSE of the day K reaches 70; then K falls to <= 30 -> a "swing high" at the CLOSE of that day; and so on.
      (The user chose "price at the crossing". That price is NOT the true extreme: it is printed next to the true extreme of the phase so the gap is visible.)
  V3  combined: a V1 pivot is kept only if K is <= 30 (for a low) or >= 70 (for a high) on at least one candle within +-window candles of the pivot candle; if dropping pivots leaves two of the same
      kind in a row, the more extreme one is kept (lower low / higher high) so the sequence still alternates.
Pivots are known only in hindsight (V1: confirmation lag; V3: needs +window candles; V2: known on the crossing day)."""
import os, sys
import numpy as np, pandas as pd
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.ticker import FuncFormatter
S = os.path.join(os.environ.get('SWING_DATA_DIR', '.'), '')
TK = sys.argv[1].upper(); TH = float(sys.argv[2]) if len(sys.argv) > 2 else 0.30; W = int(sys.argv[3]) if len(sys.argv) > 3 else 5
P = pd.read_pickle(S + f'{TK.lower()}_price.pkl').reset_index(drop=True)
h, l, o, c = (P[k].values.astype(float) for k in ('h', 'l', 'o', 'c')); n = len(P); dates = P.d.tolist()
LAB = lambda k: chr(65 + k) if k < 26 else chr(65 + k // 26 - 1) + chr(65 + k % 26)


def stochastic(h, l, c, kn=14, sk=3, sd=3):
    """terminal definition (indicators.ts I15): raw %K over kn candles (0 on a zero range), K = SMA(raw, sk), D = SMA(K, sd); NaN until enough candles"""
    n = len(c); raw = np.full(n, np.nan)
    for i in range(kn - 1, n):
        hh, ll = h[i - kn + 1:i + 1].max(), l[i - kn + 1:i + 1].min(); raw[i] = 0.0 if hh == ll else 100 * (c[i] - ll) / (hh - ll)
    K = pd.Series(raw).rolling(sk).mean().values; D = pd.Series(K).rolling(sd).mean().values
    return K, D


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
    return piv + ([last] if last is not None and (not piv or last[0] != piv[-1][0]) else [])


def stoch_pivots(K, lo_th=30, hi_th=70):
    """state machine on K only. Returns (index, kind, close, true_extreme_index, true_extreme_price) where kind 'L' = K reached hi_th after a visit to lo_th, 'H' = K reached lo_th after a visit to hi_th"""
    out = []; state = None; start = 0   # state: 'os' (K was <= lo_th, waiting for >= hi_th), 'ob' (K was >= hi_th, waiting for <= lo_th)
    for i in range(n):
        k = K[i]
        if np.isnan(k): continue
        if state is None:
            state = 'os' if k <= lo_th else 'ob' if k >= hi_th else None; start = i
            continue
        if state == 'os' and k >= hi_th:
            j = start + int(np.argmin(l[start:i + 1])); out.append((i, 'L', c[i], j, l[j])); state = 'ob'; start = i
        elif state == 'ob' and k <= lo_th:
            j = start + int(np.argmax(h[start:i + 1])); out.append((i, 'H', c[i], j, h[j])); state = 'os'; start = i
    return out


def combine(piv, K, w):
    keep = []
    for (i, t, p, ci) in piv:
        win = K[max(0, i - w):i + w + 1]; win = win[~np.isnan(win)]
        ok = len(win) > 0 and ((win.min() <= 30) if t == 'L' else (win.max() >= 70))
        keep.append(((i, t, p, ci), ok, (win.min() if t == 'L' else win.max()) if len(win) else np.nan))
    kept = [x[0] for x in keep if x[1]]; merged = []
    for q in kept:
        if merged and merged[-1][1] == q[1]:
            if (q[1] == 'L' and q[2] < merged[-1][2]) or (q[1] == 'H' and q[2] > merged[-1][2]): merged[-1] = q
        else: merged.append(q)
    return merged, keep


K, D = stochastic(h, l, c)
v1 = zigzag(h, l, TH); sp = stoch_pivots(K); v2 = [(i, t, p, None) for i, t, p, _, _ in sp]; v3, v3detail = combine(v1, K, W)

print(f'{TK}: {n} candle {dates[0]}..{dates[-1]} | Stochastic Slow 14,3,3 (K valid from {dates[int(np.argmax(~np.isnan(K)))]})')
print(f'V1 ZigZag harga {TH:.0%}: {len(v1)} titik | V2 stochastic saja 30/70: {len(v2)} titik | V3 gabungan (zona stochastic dalam +-{W} candle): {len(v3)} titik')
for w_ in (2, 3, 5, 10, 20): print(f'   sensitivitas jendela +-{w_}: {len(combine(v1, K, w_)[0])} titik', end='')
print()
print('\n== V3: titik ZigZag harga yang DIBUANG (stochastic tidak masuk zona di sekitarnya)')
for (i, t, p, ci), ok, kv in v3detail:
    if not ok: print(f"   {t} {dates[i]} {p:g}: K {'terendah' if t == 'L' else 'tertinggi'} dalam +-{W} candle = {kv:.0f} ({'tidak <= 30' if t == 'L' else 'tidak >= 70'})")
print('\n== V2: stochastic saja. "L" = K mencapai >= 70 (setelah <= 30), "H" = K mencapai <= 30 (setelah >= 70). Harga = close hari itu; ekstrem sebenarnya = low/high terendah/tertinggi fase sebelumnya')
rows = []
for k, (i, t, p, j, ep) in enumerate(sp):
    rows.append([LAB(k), dates[i], 'low' if t == 'L' else 'high', p, round(K[i], 1), dates[j], ep, f'{100 * (p / ep - 1):+.0f}%', i - j])
print(pd.DataFrame(rows, columns=['titik', 'tanggal tembus', 'jenis', 'close (pivot)', 'K', 'tanggal ekstrem fase', 'ekstrem', 'close vs ekstrem', 'candle sesudah ekstrem']).to_string(index=False))
gap = [abs(r[3] / r[6] - 1) for r in rows]; lag = [r[8] for r in rows]
print(f'\nSelisih close terhadap ekstrem fase: median {100 * np.median(gap):.0f}%, jeda median {np.median(lag):.0f} candle. Jumlah kaki V2 (antar-titik): {len(sp) - 1}; arah kaki V2 menurut harga (close ke close): '
      f'naik {sum(sp[k + 1][2] > sp[k][2] for k in range(len(sp) - 1))}, turun {sum(sp[k + 1][2] < sp[k][2] for k in range(len(sp) - 1))}')
print('   Arah label vs arah harga: kaki "low->high" V2 naik menurut harga pada', sum(1 for k in range(len(sp) - 1) if sp[k][1] == 'L' and sp[k + 1][2] > sp[k][2]), 'dari', sum(1 for k in range(len(sp) - 1) if sp[k][1] == 'L'), 'kali')
print('\n== V1 dan V3 (huruf per versi)')
for nm, v in (('V1', v1), ('V3', v3)): print(nm + ': ' + '; '.join(f"{LAB(k)} {t}{dates[i][2:7]} {p:g}" for k, (i, t, p, _) in enumerate(v)))

# ---- chart: three price panels (log) + stochastic
fig, ax = plt.subplots(4, 1, figsize=(19, 20), sharex=True, gridspec_kw={'height_ratios': [4, 4, 4, 1.8]}); x = np.arange(n)
for a in ax[:3]:
    a.set_yscale('log')
    for i in range(n):
        col = '#1b9e77' if c[i] >= o[i] else '#d6403a'; a.vlines(i, l[i], h[i], color=col, lw=0.7); a.add_patch(Rectangle((i - 0.32, min(o[i], c[i])), 0.64, max(abs(c[i] - o[i]), 0.003 * c[i]), color=col, alpha=0.85))
    a.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f'{v:g}')); a.yaxis.set_minor_formatter(FuncFormatter(lambda v, _: f'{v:g}' if v in (100, 200, 300, 500, 700) else '')); a.grid(alpha=0.2, which='both')


def draw(a, v, title, price_of=lambda i, p: p):
    a.set_title(title, fontsize=11)
    for k in range(len(v) - 1): a.plot([v[k][0], v[k + 1][0]], [v[k][2], v[k + 1][2]], color='#444', lw=1.2, ls='--')
    for k, (i, t, p, ci) in enumerate(v):
        a.scatter(i, p, marker='v' if t == 'H' else '^', s=45, color='#d6403a' if t == 'H' else '#1b9e77', zorder=5, edgecolor='white', linewidth=0.5)
        a.annotate(LAB(k), (i, p), textcoords='offset points', xytext=(0, 9 if t == 'H' else -15), ha='center', fontsize=8, fontweight='bold', bbox=dict(boxstyle='round,pad=0.08', fc='white', ec='none', alpha=0.7))


draw(ax[0], v1, f'V1  ZigZag harga {TH:.0%} (pivot = high/low candle ekstrem; dikonfirmasi setelah pembalikan {TH:.0%}): {len(v1)} titik')
draw(ax[1], v2, f'V2  stochastic saja (14,3,3 slow; 30/70): pivot = CLOSE hari K mencapai 70 ("low") atau 30 ("high"): {len(v2)} titik  (BUKAN ekstrem sebenarnya)')
draw(ax[2], v3, f'V3  gabungan: titik ZigZag harga yang stochastic-nya masuk zona 30/70 dalam +-{W} candle: {len(v3)} dari {len(v1)} titik V1')
for (i, t, p, ci), ok, kv in v3detail:
    if not ok: ax[2].scatter(i, p, marker='x', s=70, color='#888', zorder=4)
ax[3].plot(x, K, color='#1f77b4', lw=1.1, label='%K halus (14,3,3)'); ax[3].plot(x, D, color='#ff7f0e', lw=0.9, label='%D'); ax[3].axhline(70, color='#d6403a', lw=0.8, ls='--'); ax[3].axhline(30, color='#1b9e77', lw=0.8, ls='--')
for k, (i, t, p, j, ep) in enumerate(sp): ax[3].scatter(i, K[i], marker='v' if t == 'H' else '^', s=22, color='#d6403a' if t == 'H' else '#1b9e77', zorder=5)
ax[3].set_ylim(-3, 103); ax[3].legend(loc='upper left', fontsize=8, ncol=2); ax[3].grid(alpha=0.2); ax[3].set_ylabel('stochastic')
ticks = [i for i in range(n) if i == 0 or dates[i][:7] != dates[i - 1][:7]]; ax[3].set_xticks(ticks); ax[3].set_xticklabels([dates[i][:7] for i in ticks], fontsize=8); ax[3].set_xlim(-2, n + 1)
fig.text(0.995, 0.002, 'x abu-abu pada V3 = titik V1 yang dibuang; segitiga hijau = swing low, merah = swing high', ha='right', fontsize=8, color='#555')
plt.tight_layout(); out = S + f'{TK}_zigzag_variants.png'; plt.savefig(out, dpi=90); print('\ngrafik:', out)
