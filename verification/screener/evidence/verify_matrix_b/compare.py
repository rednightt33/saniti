# verify_matrix_b: independent comparison of TS F (I28..I53, defaults) with TA-Lib 0.6.8 / numpy references, Feature 04 and Feature 01.
import json, os, sys, math
import numpy as np, talib
D = os.path.dirname(os.path.abspath(__file__))
def arr(x): return np.array([np.nan if v is None else v for v in x], dtype=float)
def cmp(name, ts, ref, out):
    ts = arr(ts) if not isinstance(ts, np.ndarray) else ts; ref = np.asarray(ref, dtype=float)
    a, b = np.isfinite(ts), np.isfinite(ref)
    nm = int((a != b).sum()); both = a & b
    fa = int(np.argmax(a)) if a.any() else -1; fb = int(np.argmax(b)) if b.any() else -1
    if both.any():
        d = np.abs(ts[both] - ref[both]); scale = np.nanmax(np.abs(ref[both])) or 1.0
        rel = d / np.maximum(np.abs(ref[both]), 1e-300)
        relx = float(np.max(np.where(np.abs(ref[both]) > 1e-9 * scale, rel, 0)))
        out.append((name, int(both.sum()), nm, fa, fb, relx, float(d.max() / scale)))
    else: out.append((name, 0, nm, fa, fb, float('nan'), float('nan')))
def sma(x, n):
    o = np.full(len(x), np.nan)
    for i in range(n - 1, len(x)):
        w = x[i - n + 1:i + 1]
        if np.all(np.isfinite(w)): o[i] = w.mean()
    return o
def popstd(x, n):
    o = np.full(len(x), np.nan)
    for i in range(n - 1, len(x)):
        w = x[i - n + 1:i + 1]
        if np.all(np.isfinite(w)): m = w.mean(); o[i] = math.sqrt(((w - m) ** 2).sum() / n)
    return o
res_all = []
for t in sys.argv[1:]:
    d = json.load(open(os.path.join(D, 'data', t + '.json'))); r = json.load(open(os.path.join(D, 'ts', t + '.json')))['res']
    T = d['T']; O, H, L, C, V = (np.array(d[k], dtype=float) for k in 'OHLCV'); N = len(C)
    out = []
    up, mid, lo = talib.BBANDS(C, 20, 2, 2, 0)
    w = up - lo
    pctb = np.where(w != 0, (C - lo) / np.where(w != 0, w, 1), np.nan); pctb[~np.isfinite(w)] = np.nan
    cmp('I28 pctb vs BBANDS', r['bollinger_pctb']['percent_b'], pctb, out)
    f4 = np.array([d['f4'].get(x, [None]*5) for x in T], dtype=object)
    fu, fm, fl, fa, fc = (arr(f4[:, k]) for k in range(5))
    fw = fu - fl
    cmp('I28 pctb vs F04', r['bollinger_pctb']['percent_b'], np.where(fw != 0, (fc - fl) / np.where(fw != 0, fw, 1), np.nan), out)
    cmp('I29 bbw vs BBANDS', r['bollinger_width']['bandwidth'], np.where(mid != 0, 100 * (up - lo) / mid, np.nan), out)
    cmp('I29 bbw vs F04', r['bollinger_width']['bandwidth'], np.where(fm != 0, 100 * (fu - fl) / fm, np.nan), out)
    cmp('I30 atr vs ATR', r['atr']['atr'], talib.ATR(H, L, C, 14), out)
    cmp('I30 atr vs F04', r['atr']['atr'], fa, out)
    cmp('I31 natr vs NATR', r['natr']['natr'], talib.NATR(H, L, C, 14), out)
    cmp('I31 natr vs F04', r['natr']['natr'], 100 * fa / fc, out)
    cmp('I32 std vs STDDEV', r['stddev']['stddev'], talib.STDDEV(C, 20, 1), out)
    cmp('I32 std vs F04', r['stddev']['stddev'], (fu - fm) / 2, out)
    lr = np.full(N, np.nan); lr[1:] = np.where((C[:-1] > 0) & (C[1:] > 0), np.log(C[1:] / np.where(C[:-1] > 0, C[:-1], 1)), np.nan)
    hv = popstd(lr, 20) * math.sqrt(252) * 100
    cmp('I33 hv vs 2pass', r['hist_vol']['historical_volatility'], hv, out)
    f1 = np.array([d['f1'].get(x, [None]*3) for x in T], dtype=object)
    cmp('I33 hv vs F01 vol20', r['hist_vol']['historical_volatility'], arr(f1[:, 2]), out)
    cmp('I34 adr vs SMA(H-L)', r['adr']['adr'], talib.SMA(H - L, 14), out)
    cmp('I35 vsma vs SMA', r['volume_sma']['volume_sma'], talib.SMA(V, 20), out)
    cmp('I35 vsma vs F01', r['volume_sma']['volume_sma'], arr(f1[:, 0]), out)
    cmp('I36 vema vs EMA', r['volume_ema']['volume_ema'], talib.EMA(V, 20), out)
    vs = talib.SMA(V, 20)
    cmp('I37 rvol vs V/SMA', r['rvol']['rvol'], np.where(vs != 0, V / np.where(vs != 0, vs, 1), np.nan), out)
    cmp('I37 rvol vs F01', r['rvol']['rvol'], arr(f1[:, 1]), out)
    ppo = talib.PPO(V, 12, 26, 1); sig = talib.EMA(ppo, 9)
    cmp('I38 pvo vs PPO', r['pvo']['pvo'], ppo, out); cmp('I38 sig vs EMA(PPO)', r['pvo']['signal'], sig, out); cmp('I38 hist', r['pvo']['histogram'], ppo - sig, out)
    roc = talib.ROC(V, 10)
    cmp('I39 vroc vs ROC raw', r['volume_roc']['volume_roc'], roc, out)
    base = np.full(N, np.nan); base[10:] = V[:-10]
    cmp('I39 vroc vs ROC nullrule', r['volume_roc']['volume_roc'], np.where(base == 0, np.nan, roc), out)
    cmp('I40 obv vs OBV', r['obv']['obv'], talib.OBV(C, V), out)
    pvt = np.zeros(N)
    for i in range(1, N): pvt[i] = pvt[i - 1] + (V[i] * (C[i] - C[i - 1]) / C[i - 1] if C[i - 1] else 0)
    cmp('I41 pvt vs numpy', r['pvt']['pvt'], pvt, out)
    cmp('I42 vwma vs SUM', r['vwma']['vwma'], talib.SUM(C * V, 20) / talib.SUM(V, 20), out)
    tp = talib.TYPPRICE(H, L, C)
    cmp('I43 vwap(Session) vs TYPPRICE', r['vwap']['vwap'], np.where(V != 0, tp, np.nan), out)
    cmp('I43 upper1 vs TYPPRICE', r['vwap']['upper1'], np.where(V != 0, tp, np.nan), out)
    cmp('I44 adl vs AD', r['adl']['adl'], talib.AD(H, L, C, V), out)
    rng = H - L; mfm = np.where(rng != 0, ((C - L) - (H - C)) / np.where(rng != 0, rng, 1), 0)
    cmp('I45 cmf vs SUM', r['cmf']['cmf'], talib.SUM(mfm * V, 20) / talib.SUM(V, 20), out)
    cmp('I46 chosc vs ADOSC', r['chaikin_osc']['chaikin_osc'], talib.ADOSC(H, L, C, V, 3, 10), out)
    cmp('I47 mfi vs MFI', r['mfi']['mfi'], talib.MFI(H, L, C, V, 14), out)
    raw = np.full(N, np.nan); raw[1:] = (C[1:] - C[:-1]) * V[1:]
    cmp('I48 force vs EMA', r['force_index']['force_index'], talib.EMA(raw, 13), out)
    hl2 = (H + L) / 2; e = np.full(N, np.nan)
    for i in range(1, N):
        if V[i]: e[i] = (hl2[i] - hl2[i - 1]) * (H[i] - L[i]) / V[i] * 1e6
    cmp('I49 eom vs numpy sma', r['eom']['eom'], sma(e, 14), out)
    nvi = np.zeros(N); pvi = np.zeros(N); a = b = 1000.0
    for i in range(N):
        if i and V[i] < V[i - 1] and C[i - 1]: a *= C[i] / C[i - 1]
        if i and V[i] > V[i - 1] and C[i - 1]: b *= C[i] / C[i - 1]
        nvi[i] = a; pvi[i] = b
    cmp('I50 nvi vs numpy', r['nvi']['nvi'], nvi, out); cmp('I51 pvi vs numpy', r['pvi']['pvi'], pvi, out)
    cmp('I53 mfi_bw vs numpy', r['market_fi']['market_fi'], np.where(V != 0, (H - L) / np.where(V != 0, V, 1), np.nan), out)
    for row in out: res_all.append((t,) + row)
import collections
agg = collections.OrderedDict()
for t, name, n, nm, fa, fb, relx, absx in res_all:
    a = agg.setdefault(name, dict(tk=0, n=0, nm=0, fdiff=[], relx=0.0, absx=0.0, nmt=[]))
    a['tk'] += 1; a['n'] += n; a['nm'] += nm
    if nm: a['nmt'].append(f'{t}:{nm}')
    if fa != fb: a['fdiff'].append(f'{t}:{fa}/{fb}')
    if not math.isnan(relx): a['relx'] = max(a['relx'], relx); a['absx'] = max(a['absx'], absx)
print('check | tickers | bars_both | null_mismatch | max_rel (ref>1e-9*scale) | max_abs/scale | first-valid differs (ts/ref) | null-mismatch tickers')
for k, a in agg.items():
    print(f"{k} | {a['tk']} | {a['n']} | {a['nm']} | {a['relx']:.3g} | {a['absx']:.3g} | {','.join(a['fdiff'][:6])} | {','.join(a['nmt'][:8])}")
