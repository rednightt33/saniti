"""Swing-point functions shared by stoch_zigzag.py and v3_legs.py (research). stochastic = terminal Stochastic Slow (indicators.ts I15); zigzag = price ZigZag (analyze_stock.py);
combine = V3: a ZigZag pivot is kept only if K is in the 30/70 zone within +-w candles of the pivot, then consecutive pivots of one kind are merged to the more extreme one."""
import numpy as np, pandas as pd


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
