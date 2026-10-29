"""Compare TS outputs (ts/<T>.json) with TA-Lib 0.6.8 and Feature 04 (data/<T>.json). Writes compare_report.txt."""
import json, math, os, sys
import numpy as np, talib
D = os.path.dirname(os.path.abspath(__file__))
NAN = float('nan')
def arr(x): return np.array([NAN if v is None else v for v in x], dtype=np.float64)
def ema_tail(x, n):
    o = np.full(len(x), NAN); ok = np.where(~np.isnan(x))[0]
    if len(ok): o[ok[0]:] = talib.EMA(x[ok[0]:], timeperiod=n)
    return o
def sma_tail(x, n):
    o = np.full(len(x), NAN); ok = np.where(~np.isnan(x))[0]
    if len(ok): o[ok[0]:] = talib.SMA(x[ok[0]:], timeperiod=n)
    return o
def cmp(a, b, tol_abs_frac=0.0):
    """first valid index of each, null-pattern equality, max relative diff on common bars."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    fa = int(np.argmax(~np.isnan(a))) if (~np.isnan(a)).any() else None
    fb = int(np.argmax(~np.isnan(b))) if (~np.isnan(b)).any() else None
    na, nb = np.isnan(a), np.isnan(b)
    both = ~na & ~nb
    with np.errstate(divide='ignore', invalid='ignore'):
        den = np.maximum(np.abs(a), np.abs(b)); rel = np.where(den > 0, np.abs(a - b) / den, 0.0)
    scale = np.nanmax(np.abs(b)) if (~nb).any() else 0
    absd = np.abs(a - b)
    big = both & (rel > 1e-9) & (absd > tol_abs_frac * scale)
    return dict(first_ts=fa, first_ref=fb, null_mismatch=int((na != nb).sum()), only_ts=int((~na & nb).sum()), only_ref=int((na & ~nb).sum()),
                max_rel=float(rel[both].max()) if both.any() else None, n_diff_gt_1e9=int(big.sum()), n=int(both.sum()))
lines = []
for t in sys.argv[1:]:
    d = json.load(open(os.path.join(D, 'data', t + '.json'))); r = json.load(open(os.path.join(D, 'ts', t + '.json')))['res']
    O, H, L, C, V = (arr(d[k]) for k in 'OHLCV'); f = {k: arr(v) if k != 'calculation_version' else v for k, v in d['f04'].items()}
    ts = lambda k, o: arr(r[k][o])
    u, m, l = talib.BBANDS(C, 20, 2, 2, 0)
    with np.errstate(divide='ignore', invalid='ignore'):
        cases = [
          ('I28 percent_b vs F04 (close-bb_lower)/(bb_upper-bb_lower)', ts('bollinger_pctb','percent_b'), np.where(f['bb_upper_20']-f['bb_lower_20']!=0,(f['close']-f['bb_lower_20'])/(f['bb_upper_20']-f['bb_lower_20']),NAN), 0),
          ('I28 percent_b vs TA-Lib BBANDS(20,2,2,0)', ts('bollinger_pctb','percent_b'), np.where(u-l!=0,(C-l)/(u-l),NAN), 0),
          ('I29 bandwidth vs F04 100*(bb_upper-bb_lower)/bb_middle', ts('bollinger_width','bandwidth'), 100*(f['bb_upper_20']-f['bb_lower_20'])/f['bb_middle_20'], 0),
          ('I29 bandwidth vs TA-Lib BBANDS', ts('bollinger_width','bandwidth'), 100*((u-l)/m), 0),
          ('I30 atr vs F04 atr_14', ts('atr','atr'), f['atr_14'], 0),
          ('I30 atr vs TA-Lib ATR 14', ts('atr','atr'), talib.ATR(H,L,C,14), 0),
          ('I31 natr vs F04 100*atr_14/close', ts('natr','natr'), 100*f['atr_14']/f['close'], 0),
          ('I31 natr vs TA-Lib NATR 14', ts('natr','natr'), talib.NATR(H,L,C,14), 0),
          ('I32 stddev vs F04 (bb_upper-bb_middle)/2', ts('stddev','stddev'), (f['bb_upper_20']-f['bb_middle_20'])/2, 0),
          ('I32 stddev vs TA-Lib STDDEV 20 nbdev1', ts('stddev','stddev'), talib.STDDEV(C,20,1), 0),
          ('I33 hist_vol vs TA-Lib STDDEV(log ret,20)*sqrt252*100', ts('hist_vol','historical_volatility'), (lambda lr: (lambda s: s*math.sqrt(252)*100)(np.concatenate([[NAN], talib.STDDEV(lr[1:],20,1)])))(np.concatenate([[NAN], np.log(C[1:]/C[:-1])])), 1e-9),
          ('I34 adr vs TA-Lib SMA(H-L,14)', ts('adr','adr'), talib.SMA(H-L,14), 0),
        ]
        if not np.isnan(V).all():
            p = talib.PPO(V,12,26,1); ps = ema_tail(p,9)
            base = np.concatenate([np.full(10,NAN), V[:-10]]); vr = np.where(base==0,NAN,talib.ROC(V,10))
            cases += [
              ('I35 volume_sma vs TA-Lib SMA(V,20)', ts('volume_sma','volume_sma'), talib.SMA(V,20), 0),
              ('I36 volume_ema vs TA-Lib EMA(V,20)', ts('volume_ema','volume_ema'), talib.EMA(V,20), 0),
              ('I37 rvol vs V/TA-Lib SMA(V,20)', ts('rvol','rvol'), np.where(talib.SMA(V,20)!=0, V/talib.SMA(V,20), NAN), 0),
              ('I38 pvo vs TA-Lib PPO(V,12,26,matype1)', ts('pvo','pvo'), p, 0),
              ('I38 pvo signal vs TA-Lib EMA(PVO,9)', ts('pvo','signal'), ps, 0),
              ('I38 pvo histogram', ts('pvo','histogram'), p-ps, 0),
              ('I39 volume_roc vs TA-Lib ROC(V,10) null at V[t-10]=0', ts('volume_roc','volume_roc'), vr, 0),
              ('I40 obv vs TA-Lib OBV', ts('obv','obv'), talib.OBV(C,V), 0),
              ('I42 vwma vs SMA(C*V,20)/SMA(V,20) (TA-Lib SMA)', ts('vwma','vwma'), talib.SMA(C*V,20)/talib.SMA(V,20), 1e-12),
              ('I43 vwap Session vs hlc3 (TYPPRICE)', ts('vwap','vwap'), np.where(V!=0, talib.TYPPRICE(H,L,C), NAN), 0),
              ('I44 adl vs TA-Lib AD', ts('adl','adl'), talib.AD(H,L,C,V), 0),
              ('I45 cmf vs SUM(MFM*V,20)/SUM(V,20) (TA-Lib SUM)', ts('cmf','cmf'), talib.SUM(np.where(H!=L,((C-L)-(H-C))/(H-L),0)*V,20)/talib.SUM(V,20), 1e-12),
              ('I46 chaikin_osc vs TA-Lib ADOSC(3,10)', ts('chaikin_osc','chaikin_osc'), talib.ADOSC(H,L,C,V,3,10), 0),
              ('I47 mfi vs TA-Lib MFI 14', ts('mfi','mfi'), talib.MFI(H,L,C,V,14), 0),
              ('I48 force_index vs TA-Lib EMA(dC*V,13)', ts('force_index','force_index'), ema_tail(np.concatenate([[NAN], (C[1:]-C[:-1])*V[1:]]),13), 1e-12),
            ]
    lines.append(f'== {t} ({len(C)} bars, {d["T"][0]}..{d["T"][-1]})')
    for name, a, b, tol in cases:
        lines.append(f'  {name}: {cmp(a, b, tol)}')
    # first valid index of every TS output
    fv = {f'{k}.{o}': (int(np.argmax(~np.isnan(arr(v)))) if (~np.isnan(arr(v))).any() else None) for k, outs in r.items() for o, v in outs.items()}
    lines.append(f'  first valid index (TS): {fv}')
    nulls = {f'{k}.{o}': int(np.isnan(arr(v)).sum()) for k, outs in r.items() for o, v in outs.items()}
    lines.append(f'  null count (TS): {nulls}')
open(os.path.join(D, 'compare_report.txt'), 'w').write('\n'.join(lines) + '\n')
print('\n'.join(lines))
