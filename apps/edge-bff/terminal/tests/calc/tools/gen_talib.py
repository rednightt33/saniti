"""Add TA-Lib 0.6.8 expected values to the parity fixtures of tests/calc.

Reads every <dir>/<TICKER>.json.gz written by fetch_live.py and stores, under "talib", one case per
compared output: the terminal key, its params and output key, and the TA-Lib values (leading nulls
dropped). The case list below is the TA-Lib side of PARITY.md: TA_LIB rows, the +DI/-DI outputs of
I07, and the TA-Lib parts named in the spec for HTML rows (I14 STOCHRSI fast %K + SMA; I28/I29 from BBANDS,
the bands the spec sets for them).
Alternative parameters run on GOTO only (small prices with long flat stretches), to show the general formulas still equal TA-Lib.

  <venv with TA-Lib 0.6.8>/bin/python apps/edge-bff/terminal/tests/calc/tools/gen_talib.py <dir> [--digits 11]

--digits rounds the stored values to that many significant digits (committed fixtures: 11, which
adds at most 5e-12 relative to a comparison, far below the 1e-9 tolerance, and keeps the fixtures under
5 MB; the 23-ticker run in PARITY.md used full precision).
"""
import argparse, glob, gzip, json, math, os
import numpy as np
import talib

assert talib.__version__ == '0.6.8', talib.__version__
assert talib.get_compatibility() == 0

NAN = float('nan')


def ema_tail(x, n):
    """talib.EMA on the values after the leading NaNs (as Feature 04 does for the MACD signal)."""
    o = np.full(len(x), NAN)
    ok = np.where(~np.isnan(x))[0]
    if len(ok):
        o[ok[0]:] = talib.EMA(x[ok[0]:], timeperiod=n)
    return o


def sma_tail(x, n):
    o = np.full(len(x), NAN)
    ok = np.where(~np.isnan(x))[0]
    if len(ok):
        o[ok[0]:] = talib.SMA(x[ok[0]:], timeperiod=n)
    return o


def src(B, s):
    o, h, l, c = B['O'], B['H'], B['L'], B['C']
    return {'open': o, 'high': h, 'low': l, 'close': c, 'hl2': talib.MEDPRICE(h, l), 'hlc3': talib.TYPPRICE(h, l, c),
            'ohlc4': talib.AVGPRICE(o, h, l, c)}[s]


def psar(B, start, inc, mx):
    s = talib.SAREXT(B['H'], B['L'], startvalue=0, offsetonreverse=0, accelerationinitlong=start, accelerationlong=inc,
                     accelerationmaxlong=mx, accelerationinitshort=start, accelerationshort=inc, accelerationmaxshort=mx)
    if start == inc:
        assert np.allclose(np.abs(s), talib.SAR(B['H'], B['L'], acceleration=inc, maximum=mx), rtol=0, atol=0, equal_nan=True)
    return {'sar': np.abs(s), 'direction': np.sign(s)}


def po(x, f, s, g):
    p = talib.PPO(x, fastperiod=f, slowperiod=s, matype=1)
    sig = ema_tail(p, g)
    return p, sig, p - sig


def stochrsi(x, n, m, k, d):
    fk, _ = talib.STOCHRSI(x, timeperiod=n, fastk_period=m, fastd_period=1, fastd_matype=0)
    K = sma_tail(fk, k)
    return {'k': K, 'd': sma_tail(K, d)}


def bb_derived(B, n, sd, s='close', matype=0):
    x = src(B, s)
    u, m, l = talib.BBANDS(x, timeperiod=n, nbdevup=sd, nbdevdn=sd, matype=matype)
    with np.errstate(divide='ignore', invalid='ignore'):
        pctb = np.where(u - l != 0, (x - l) / (u - l), NAN)
        q = np.where(m != 0, (u - l) / m, NAN)
    return {'percent_b': pctb, 'bandwidth': 100 * q}


def vroc(v, n):
    r = talib.ROC(v, timeperiod=n)
    base = np.concatenate([np.full(n, NAN), v[:-n]]) if len(v) > n else np.full(len(v), NAN)
    return np.where(base == 0, NAN, r)        # spec I39: null when V[t-n] = 0 (TA-Lib gives 0)


def cases(B, alt):
    """(name, key, params, {out: values}, note)."""
    o, h, l, c, v = B['O'], B['H'], B['L'], B['C'], B['V']
    vol = not np.isnan(v).all()
    L = [
        ('plus_minus_di_14', 'adx', {'di_length': 14, 'adx_smoothing': 14},
         {'plus_di': talib.PLUS_DI(h, l, c, 14), 'minus_di': talib.MINUS_DI(h, l, c, 14)}, 'PLUS_DI / MINUS_DI'),
        ('wma_20', 'wma', {'length': 20, 'source': 'close'}, {'wma': talib.WMA(c, 20)}, 'WMA'),
        ('kama_10', 'kama', {'length': 10, 'fast_length': 2, 'slow_length': 30, 'source': 'close'}, {'kama': talib.KAMA(c, 10)}, 'KAMA'),
        ('aroon_14', 'aroon', {'length': 14}, dict(zip(('aroon_down', 'aroon_up'), talib.AROON(h, l, 14))), 'AROON'),
        ('donchian_20', 'donchian', {'length': 20},
         {'upper': talib.MAX(h, 20), 'lower': talib.MIN(l, 20), 'basis': (talib.MAX(h, 20) + talib.MIN(l, 20)) / 2}, 'MAX / MIN, basis (u+l)/2'),
        ('psar_default', 'psar', {'start': 0.02, 'increment': 0.02, 'maximum': 0.2}, psar(B, 0.02, 0.02, 0.2), 'SAREXT = SAR; sar |SAREXT|, direction sign'),
        ('stochastic_14_3_3', 'stochastic', {'k_length': 14, 'smooth_k': 3, 'd_length': 3},
         dict(zip(('k', 'd'), talib.STOCH(h, l, c, 14, 3, 0, 3, 0))), 'STOCH slowk/slowd, SMA'),
        ('williams_r_14', 'williams_r', {'length': 14, 'source': 'close'}, {'williams_r': talib.WILLR(h, l, c, 14)}, 'WILLR'),
        ('roc_9', 'roc', {'length': 9, 'source': 'close'}, {'roc': talib.ROC(c, 9)}, 'ROC'),
        ('momentum_10', 'momentum', {'length': 10, 'source': 'close'}, {'momentum': talib.MOM(c, 10)}, 'MOM'),
        ('cci_20', 'cci', {'length': 20, 'constant': 0.015}, {'cci': talib.CCI(h, l, c, 20)}, 'CCI'),
        ('trix_15', 'trix', {'length': 15, 'source': 'close'}, {'trix': talib.TRIX(c, 15)}, 'TRIX'),
        ('ultosc_7_14_28', 'ultimate_osc', {'fast_length': 7, 'middle_length': 14, 'slow_length': 28, 'weight_fast': 4, 'weight_middle': 2, 'weight_slow': 1},
         {'uo': talib.ULTOSC(h, l, c, 7, 14, 28)}, 'ULTOSC'),
        ('ppo_12_26_9', 'ppo', {'fast_length': 12, 'slow_length': 26, 'signal_length': 9, 'source': 'close'},
         dict(zip(('ppo', 'signal', 'histogram'), po(c, 12, 26, 9))), 'PPO matype 1; signal talib.EMA(PPO, 9)'),
        ('bop', 'bop', {}, {'bop': talib.BOP(o, h, l, c)}, 'BOP'),
        ('natr_14', 'natr', {'length': 14, 'smoothing_type': 'RMA'}, {'natr': talib.NATR(h, l, c, 14)}, 'NATR'),
        ('stddev_20', 'stddev', {'length': 20, 'source': 'close', 'stdev_method': 'population'}, {'stddev': talib.STDDEV(c, 20, 1)}, 'STDDEV nbdev 1'),
        ('stoch_rsi_14_14_3_3', 'stoch_rsi', {'rsi_length': 14, 'stoch_length': 14, 'smooth_k': 3, 'smooth_d': 3, 'source': 'close'},
         stochrsi(c, 14, 14, 3, 3), 'STOCHRSI fast %K (fastd 1) + talib.SMA 3, 3'),
        ('bb_pctb_20_2', 'bollinger_pctb', {'length': 20, 'source': 'close', 'std_dev': 2, 'basis_ma_type': 'SMA'},
         {'percent_b': bb_derived(B, 20, 2)['percent_b']}, 'BBANDS: (C-lower)/(upper-lower)'),
        ('bb_width_20_2', 'bollinger_width', {'length': 20, 'source': 'close', 'std_dev': 2, 'basis_ma_type': 'SMA'},
         {'bandwidth': bb_derived(B, 20, 2)['bandwidth']}, 'BBANDS: 100*((upper-lower)/middle)'),
    ]
    if vol:
        L += [
            ('volume_sma_20', 'volume_sma', {'length': 20}, {'volume_sma': talib.SMA(v, 20)}, 'SMA(V)'),
            ('volume_ema_20', 'volume_ema', {'length': 20}, {'volume_ema': talib.EMA(v, 20)}, 'EMA(V)'),
            ('pvo_12_26_9', 'pvo', {'fast_length': 12, 'slow_length': 26, 'signal_length': 9},
             dict(zip(('pvo', 'signal', 'histogram'), po(v, 12, 26, 9))), 'PPO(V) matype 1; signal talib.EMA(PVO, 9)'),
            ('volume_roc_10', 'volume_roc', {'length': 10}, {'volume_roc': vroc(v, 10)}, 'ROC(V); null where V[t-10] = 0 (spec I39)'),
            ('obv', 'obv', {}, {'obv': talib.OBV(c, v)}, 'OBV'),
            ('adl', 'adl', {}, {'adl': talib.AD(h, l, c, v)}, 'AD'),
            ('chaikin_osc_3_10', 'chaikin_osc', {'fast_length': 3, 'slow_length': 10}, {'chaikin_osc': talib.ADOSC(h, l, c, v, 3, 10)}, 'ADOSC'),
            ('mfi_14', 'mfi', {'length': 14}, {'mfi': talib.MFI(h, l, c, v, 14)}, 'MFI'),
        ]
    if alt:   # other parameters (GOTO only): the general formulas at TA-Lib-supported settings
        x = src(B, 'hlc3')
        L += [
            ('alt_sma_7_hl2', 'sma', {'length': 7, 'source': 'hl2'}, {'sma': talib.SMA(src(B, 'hl2'), 7)}, 'SMA(MEDPRICE)'),
            ('alt_ema_9_ohlc4', 'ema', {'length': 9, 'source': 'ohlc4'}, {'ema': talib.EMA(src(B, 'ohlc4'), 9)}, 'EMA(AVGPRICE)'),
            ('alt_wma_9_hlc3', 'wma', {'length': 9, 'source': 'hlc3'}, {'wma': talib.WMA(x, 9)}, 'WMA(TYPPRICE)'),
            ('alt_rsi_7_open', 'rsi', {'length': 7, 'source': 'open'}, {'rsi': talib.RSI(o, 7)}, 'RSI(O)'),
            ('alt_atr_5', 'atr', {'length': 5, 'smoothing_type': 'RMA'}, {'atr': talib.ATR(h, l, c, 5)}, 'ATR 5'),
            ('alt_atr_sma_10', 'atr', {'length': 10, 'smoothing_type': 'SMA'}, {'atr': sma_tail(talib.TRANGE(h, l, c), 10)}, 'SMA(TRANGE)'),
            ('alt_adx_7', 'adx', {'di_length': 7, 'adx_smoothing': 7},
             {'adx': talib.ADX(h, l, c, 7), 'plus_di': talib.PLUS_DI(h, l, c, 7), 'minus_di': talib.MINUS_DI(h, l, c, 7)}, 'ADX / DI 7'),
            ('alt_bb_10_1_5', 'bollinger', {'length': 10, 'source': 'close', 'std_dev': 1.5, 'basis_ma_type': 'SMA'},
             dict(zip(('upper', 'basis', 'lower'), talib.BBANDS(c, 10, 1.5, 1.5, 0))), 'BBANDS 10, 1.5'),
            ('alt_bb_ema_20_2', 'bollinger', {'length': 20, 'source': 'close', 'std_dev': 2, 'basis_ma_type': 'EMA'},
             dict(zip(('upper', 'basis', 'lower'), talib.BBANDS(c, 20, 2, 2, 1))), 'BBANDS matype 1 (EMA basis)'),
            ('alt_macd_ema_5_35_5', 'macd', {'fast_length': 5, 'slow_length': 35, 'signal_length': 5, 'source': 'close'},
             (lambda m: {'macd': m, 'signal': ema_tail(m, 5), 'histogram': m - ema_tail(m, 5)})(talib.EMA(c, 5) - talib.EMA(c, 35)),
             'EMA 5 - EMA 35, signal EMA 5 (Feature 04 method)'),
            ('alt_kama_5', 'kama', {'length': 5, 'fast_length': 2, 'slow_length': 30, 'source': 'close'}, {'kama': talib.KAMA(c, 5)}, 'KAMA 5'),
            ('alt_psar_ext', 'psar', {'start': 0.01, 'increment': 0.03, 'maximum': 0.25}, psar(B, 0.01, 0.03, 0.25), 'SAREXT init 0.01, step 0.03, max 0.25'),
            ('alt_stoch_5_1_3', 'stochastic', {'k_length': 5, 'smooth_k': 1, 'd_length': 3},
             dict(zip(('k', 'd'), talib.STOCH(h, l, c, 5, 1, 0, 3, 0))), 'STOCH 5/1/3'),
            ('alt_cci_14', 'cci', {'length': 14, 'constant': 0.015}, {'cci': talib.CCI(h, l, c, 14)}, 'CCI 14'),
            ('alt_ultosc_5_10_20', 'ultimate_osc', {'fast_length': 5, 'middle_length': 10, 'slow_length': 20, 'weight_fast': 4, 'weight_middle': 2, 'weight_slow': 1},
             {'uo': talib.ULTOSC(h, l, c, 5, 10, 20)}, 'ULTOSC 5/10/20'),
            ('alt_trix_9_hl2', 'trix', {'length': 9, 'source': 'hl2'}, {'trix': talib.TRIX(src(B, 'hl2'), 9)}, 'TRIX(MEDPRICE)'),
            ('alt_ppo_5_20_4', 'ppo', {'fast_length': 5, 'slow_length': 20, 'signal_length': 4, 'source': 'close'},
             dict(zip(('ppo', 'signal', 'histogram'), po(c, 5, 20, 4))), 'PPO 5/20, signal 4'),
            ('alt_adosc_5_20', 'chaikin_osc', {'fast_length': 5, 'slow_length': 20}, {'chaikin_osc': talib.ADOSC(h, l, c, v, 5, 20)}, 'ADOSC 5/20'),
            ('alt_mfi_5', 'mfi', {'length': 5}, {'mfi': talib.MFI(h, l, c, v, 5)}, 'MFI 5'),
            ('alt_aroon_25', 'aroon', {'length': 25}, dict(zip(('aroon_down', 'aroon_up'), talib.AROON(h, l, 25))), 'AROON 25'),
            ('alt_pctb_ema_10_1', 'bollinger_pctb', {'length': 10, 'source': 'close', 'std_dev': 1, 'basis_ma_type': 'EMA'},
             {'percent_b': bb_derived(B, 10, 1, matype=1)['percent_b']}, 'BBANDS matype 1 (EMA basis)'),
            ('alt_width_wma_15_2_5', 'bollinger_width', {'length': 15, 'source': 'hl2', 'std_dev': 2.5, 'basis_ma_type': 'WMA'},
             {'bandwidth': bb_derived(B, 15, 2.5, 'hl2', matype=2)['bandwidth']}, 'BBANDS(MEDPRICE) matype 2 (WMA basis)'),
            ('alt_stddev_5_hl2', 'stddev', {'length': 5, 'source': 'hl2', 'stdev_method': 'population'}, {'stddev': talib.STDDEV(src(B, 'hl2'), 5, 1)}, 'STDDEV(MEDPRICE) 5'),
        ]
    return L


def enc(a, digits):
    vals = [None if (x is None or not math.isfinite(x)) else (float(f'{x:.{digits}g}') if digits else float(x)) for x in np.asarray(a, float).tolist()]
    s = next((i for i, x in enumerate(vals) if x is not None), len(vals))
    return {'s': s, 'v': vals[s:]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('dir')
    ap.add_argument('--digits', type=int, default=0)
    a = ap.parse_args()
    for path in sorted(glob.glob(os.path.join(a.dir, '*.json.gz'))):
        with gzip.open(path, 'rt') as f:
            d = json.load(f)
        B = {k: np.array([NAN if x is None else x for x in d[k]], dtype=np.float64) for k in 'OHLCV'}
        out = []
        for name, key, params, outs, note in cases(B, d['ticker'] == 'GOTO'):
            out.append({'name': name, 'key': key, 'params': params, 'note': note, 'outs': {k: enc(v, a.digits) for k, v in outs.items()}})
        d['talib'] = out
        d['talib_meta'] = {'talib': talib.__version__, 'c': talib.__ta_version__.decode(), 'digits': a.digits or 'full'}
        with gzip.open(path, 'wt') as f:
            json.dump(d, f, separators=(',', ':'))
        print(d['ticker'], len(out), 'cases')


if __name__ == '__main__':
    main()
