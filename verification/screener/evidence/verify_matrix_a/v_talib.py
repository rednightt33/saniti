"""Verifier: TA-Lib 0.6.8 vs terminal F outputs (dumped by v_dump_ts.mjs). Prints max rel diff, null mismatches, first valid."""
import json, sys
import numpy as np, talib
D = '/tmp/claude-0/-home-user-saniti/65bd49d0-9dca-5072-b7db-b62314cf2cd3/scratchpad/audit/verify_matrix_a/data/'
assert talib.__version__ == '0.6.8' and talib.get_compatibility() == 0
def arr(s): return np.array([np.nan if v is None else v for v in s], dtype=float)
def fv(a):
    w = np.where(np.isfinite(a))[0]; return int(w[0]) if len(w) else -1
def cmp(ts, tl, scale=None):
    ts, tl = arr(ts), np.asarray(tl, dtype=float)
    nm = int(np.sum(np.isfinite(ts) != np.isfinite(tl)))
    m = np.isfinite(ts) & np.isfinite(tl)
    if not m.any(): return f'fvTS={fv(ts)} fvTL={fv(tl)} nullMis={nm} (no overlap)'
    d = np.abs(ts[m] - tl[m]); den = np.maximum(np.abs(ts[m]), np.abs(tl[m]))
    rel = np.where(d == 0, 0, d / np.where(den == 0, 1, den))
    sc = '' if scale is None else f' maxAbs/scale={d.max()/scale:.2e}'
    return f'fvTS={fv(ts)} fvTL={fv(tl)} nullMis={nm} maxRel={rel.max():.2e} maxAbs={d.max():.2e}{sc} n={int(m.sum())}'
for t in sys.argv[1:]:
    d = json.load(open(D + t + '.json')); ts = json.load(open(D + t + '.ts.json'))
    P = d['price']['rows']
    O, H, L, C, V = [np.array([r[k] for r in P], dtype=float) for k in (1, 2, 3, 4, 5)]
    hlc3 = (H + L + C) / 3; hl2 = (H + L) / 2
    print(f'== {t} bars={len(C)}')
    R = []
    R.append(('I01 SMA', ts['sma']['sma'], talib.SMA(C, 20)))
    R.append(('I02 EMA', ts['ema']['ema'], talib.EMA(C, 20)))
    R.append(('I03 WMA', ts['wma']['wma'], talib.WMA(C, 20)))
    R.append(('I03 WMA hlc3 9', ts['wma_hlc3_9']['wma'], talib.WMA(hlc3, 9)))
    for nm_, n in (('hma', 9), ('hma_16', 16), ('hma_7', 7)):
        h, r = max(1, n // 2), max(1, int(np.floor(np.sqrt(n))))
        R.append((f'I04 HMA{n} via talib.WMA floor', ts[nm_]['hma'], talib.WMA(2 * talib.WMA(C, h) - talib.WMA(C, n), r)))
    R.append(('I04 HMA7 via round(sqrt)', ts['hma_7']['hma'], talib.WMA(2 * talib.WMA(C, 3) - talib.WMA(C, 7), int(round(np.sqrt(7))))))
    R.append(('I05 KAMA', ts['kama']['kama'], talib.KAMA(C, 10)))
    R.append(('I05 KAMA hl2 5', ts['kama_hl2_5']['kama'], talib.KAMA(hl2, 5)))
    R.append(('I05 KAMA fast3/slow20 vs talib KAMA10', ts['kama_3_20']['kama'], talib.KAMA(C, 10)))
    m, s, h = talib.MACD(C, 12, 26, 9)
    R.append(('I06 macd vs talib.MACD', ts['macd']['macd'], m, np.nanmax(np.abs(m))))
    R.append(('I06 signal vs talib.MACD', ts['macd']['signal'], s))
    e = talib.EMA(C, 12) - talib.EMA(C, 26); sg = np.full(len(C), np.nan)
    if len(C) >= 26: sg[25:] = talib.EMA(e[25:], 9)
    R.append(('I06 macd EMA-EMA build', ts['macd']['macd'], e)); R.append(('I06 signal build', ts['macd']['signal'], sg)); R.append(('I06 hist build', ts['macd']['histogram'], e - sg))
    me, se, he = talib.MACDEXT(C, 12, 1, 26, 1, 9, 1)
    R.append(('I06 macd vs MACDEXT(EMA)', ts['macd']['macd'], me))
    R.append(('I07 ADX', ts['adx']['adx'], talib.ADX(H, L, C, 14))); R.append(('I07 +DI', ts['adx']['plus_di'], talib.PLUS_DI(H, L, C, 14))); R.append(('I07 -DI', ts['adx']['minus_di'], talib.MINUS_DI(H, L, C, 14)))
    R.append(('I07 ADX 7/7', ts['adx_7_7']['adx'], talib.ADX(H, L, C, 7)))
    R.append(('I07 ADX 14/7 vs ADX14', ts['adx_14_7']['adx'], talib.ADX(H, L, C, 14), 100))
    ad, au = talib.AROON(H, L, 14)
    R.append(('I08 aroon_up', ts['aroon']['aroon_up'], au)); R.append(('I08 aroon_down', ts['aroon']['aroon_down'], ad))
    R.append(('I10 upper', ts['donchian']['upper'], talib.MAX(H, 20))); R.append(('I10 lower', ts['donchian']['lower'], talib.MIN(L, 20)))
    R.append(('I10 basis', ts['donchian']['basis'], (talib.MAX(H, 20) + talib.MIN(L, 20)) / 2))
    R.append(('I11 keltner upper ~ EMA20+2ATR10', ts['keltner']['upper'], talib.EMA(C, 20) + 2 * talib.ATR(H, L, C, 10)))
    R.append(('I11 keltner basis ~ EMA20', ts['keltner']['basis'], talib.EMA(C, 20)))
    R.append(('I12 SAR', ts['psar']['sar'], talib.SAR(H, L, 0.02, 0.2)))
    sx = talib.SAREXT(H, L, 0, 0, 0.02, 0.02, 0.2, 0.02, 0.02, 0.2)
    R.append(('I12 direction vs sign(SAREXT)', ts['psar']['direction'], np.sign(sx)))
    sx2 = talib.SAREXT(H, L, 0, 0, 0.01, 0.03, 0.25, 0.01, 0.03, 0.25)
    R.append(('I12 alt |SAREXT|', ts['psar_alt']['sar'], np.abs(sx2)))
    R.append(('I13 RSI', ts['rsi']['rsi'], talib.RSI(C, 14)))
    fk, fd = talib.STOCHRSI(C, 14, 14, 3, 0)
    R.append(('I14 K vs STOCHRSI fastd', ts['stoch_rsi']['k'], fd, 100)); R.append(('I14 K vs STOCHRSI fastk', ts['stoch_rsi']['k'], fk, 100))
    R.append(('I14 D vs SMA(fastd,3)', ts['stoch_rsi']['d'], talib.SMA(fd, 3) if np.isfinite(fd).sum() else fd))
    sk, sd = talib.STOCH(H, L, C, 14, 3, 0, 3, 0)
    R.append(('I15 K', ts['stochastic']['k'], sk)); R.append(('I15 D', ts['stochastic']['d'], sd))
    sk5, sd5 = talib.STOCH(H, L, C, 5, 1, 0, 3, 0)
    R.append(('I15 5/1/3 K', ts['stochastic_5_1_3']['k'], sk5))
    R.append(('I16 WILLR', ts['williams_r']['williams_r'], talib.WILLR(H, L, C, 14)))
    R.append(('I17 ROC', ts['roc']['roc'], talib.ROC(C, 9))); R.append(('I18 MOM', ts['momentum']['momentum'], talib.MOM(C, 10)))
    R.append(('I19 CCI', ts['cci']['cci'], talib.CCI(H, L, C, 20))); R.append(('I19 CCI14', ts['cci_14']['cci'], talib.CCI(H, L, C, 14)))
    R.append(('I20 CMO vs talib.CMO', ts['cmo']['cmo'], talib.CMO(C, 14), 100))
    dd = np.diff(C, prepend=np.nan); g = talib.SUM(np.where(np.isnan(dd), np.nan, np.maximum(dd, 0))[1:], 14); l = talib.SUM(np.where(np.isnan(dd), np.nan, np.maximum(-dd, 0))[1:], 14)
    cm = np.concatenate([[np.nan], np.where((g + l) != 0, 100 * (g - l) / np.where((g + l) == 0, 1, g + l), np.nan)])
    R.append(('I20 CMO plain-sum build', ts['cmo']['cmo'], cm))
    R.append(('I22 TRIX', ts['trix']['trix'], talib.TRIX(C, 15)))
    R.append(('I23 ULTOSC', ts['ultimate_osc']['uo'], talib.ULTOSC(H, L, C, 7, 14, 28)))
    R.append(('I23 desc periods vs ULTOSC(7,14,28)', ts['uo_desc']['uo'], talib.ULTOSC(H, L, C, 28, 14, 7), 100))
    mp = talib.MEDPRICE(H, L)
    R.append(('I24 AO ~ SMA(MED,5)-SMA(MED,34)', ts['awesome_osc']['ao'], talib.SMA(mp, 5) - talib.SMA(mp, 34), np.nanmax(np.abs(C))))
    pp = talib.PPO(C, 12, 26, 1)
    R.append(('I25 PPO matype1', ts['ppo']['ppo'], pp))
    psg = np.full(len(C), np.nan); fvp = fv(pp)
    if fvp >= 0: psg[fvp:] = talib.EMA(pp[fvp:], 9)
    R.append(('I25 signal EMA(ppo,9)', ts['ppo']['signal'], psg))
    R.append(('I25 PPO matype0 (default)', ts['ppo']['ppo'], talib.PPO(C, 12, 26), 1))
    pp5 = talib.PPO(C, 5, 20, 1); R.append(('I25 PPO 5/20 matype1', ts['ppo_5_20_4']['ppo'], pp5))
    R.append(('I25 PPO fast26/slow12 vs talib(26,12)', ts['ppo_swap']['ppo'], talib.PPO(C, 26, 12, 1), 1))
    R.append(('I25 PPO line vs 100*macd/ema26', ts['ppo']['ppo'], 100 * (talib.EMA(C, 12) - talib.EMA(C, 26)) / talib.EMA(C, 26)))
    R.append(('I26 BOP', ts['bop']['bop'], talib.BOP(O, H, L, C)))
    u, mi, lo = talib.BBANDS(C, 20, 2, 2, 0)
    R.append(('I27 upper', ts['bollinger']['upper'], u)); R.append(('I27 basis', ts['bollinger']['basis'], mi)); R.append(('I27 lower', ts['bollinger']['lower'], lo))
    u1, m1, l1 = talib.BBANDS(C, 20, 2, 2, 1); R.append(('I27 EMA basis upper vs matype1', ts['bb_ema']['upper'], u1)); R.append(('I27 EMA basis vs matype1', ts['bb_ema']['basis'], m1))
    u2, m2, l2 = talib.BBANDS(C, 20, 2, 2, 2); R.append(('I27 WMA basis upper vs matype2', ts['bb_wma']['upper'], u2))
    R.append(('I30 ATR14', ts['atr']['atr'], talib.ATR(H, L, C, 14))); R.append(('I30 ATR10', ts['atr_10']['atr'], talib.ATR(H, L, C, 10)))
    for row in R:
        name, a, b = row[:3]; sc = row[3] if len(row) > 3 else None
        print(f'  {name:42s} {cmp(a, b, sc)}')
