"""EXEC-SCREENER-FLOW-CANDLES P6 evidence (verification/screener/P6_CANDLES.md section 6): Feature 04's cdl_* columns
against the P6 candlestick patterns on the Terminal parity fixtures, without database access.

Feature 04 computes its cdl_* columns with TA-Lib 0.6.8 / C 0.6.4 at default settings, each bar from a bounded window
of the largest pattern lookback + 1 bars (features/feature04/engine.py PATTERNS, library_contract,
_calculate_canonical_pattern). This script does the same on the fixtures' bars (the same rows the fixtures were read
from: Price_Stock_Indonesia_IDX, apps/edge-bff/terminal/tests/calc/fixtures) and compares bar by bar with the P6
signals written by export_signals.mjs. It also counts TA-Lib bearish engulfing bars whose first candle has close ==
open (TA-Lib's colour of such a candle is white), the main cause of the difference there.

Needs TA-Lib 0.6.8 (pip install TA-Lib==0.6.8 numpy). Run:
  python -I verification/screener/p6_candles/f04_compare.py apps/edge-bff/terminal/tests/calc/fixtures <signals.json>
"""
import gzip
import json
import os
import sys

import numpy as np
import talib
from talib import abstract

FIX, OURS = sys.argv[1], sys.argv[2]
assert talib.__version__ == '0.6.8' and talib.__ta_version__.startswith(b'0.6.4 '), 'Feature 04 runs TA-Lib 0.6.8 / C 0.6.4'
F04 = ['CDLPIERCING', 'CDLMORNINGSTAR', 'CDLMORNINGDOJISTAR', 'CDLENGULFING', 'CDL3WHITESOLDIERS', 'CDLHAMMER',
       'CDLINVERTEDHAMMER', 'CDL3INSIDE', 'CDL3OUTSIDE', 'CDLHARAMI', 'CDLHARAMICROSS', 'CDLDARKCLOUDCOVER',
       'CDLEVENINGSTAR', 'CDLEVENINGDOJISTAR', 'CDL3BLACKCROWS', 'CDLSHOOTINGSTAR', 'CDLHANGINGMAN', 'CDLDOJI',
       'CDLDRAGONFLYDOJI', 'CDLGRAVESTONEDOJI', 'CDLMARUBOZU', 'CDLKICKING', 'CDLRISEFALL3METHODS', 'CDLMATHOLD',
       'CDLHIKKAKE']
# P6 pattern -> (TA-Lib function of the Feature 04 column, the sign that side reads)
MAP = {
    'hammer': ('CDLHAMMER', 1), 'hanging_man': ('CDLHANGINGMAN', -1),
    'inverted_hammer': ('CDLINVERTEDHAMMER', 1), 'shooting_star': ('CDLSHOOTINGSTAR', -1),
    'dragonfly_doji': ('CDLDRAGONFLYDOJI', 1), 'gravestone_doji': ('CDLGRAVESTONEDOJI', 1),
    'bullish_marubozu': ('CDLMARUBOZU', 1), 'bearish_marubozu': ('CDLMARUBOZU', -1),
    'bullish_engulfing': ('CDLENGULFING', 1), 'bearish_engulfing': ('CDLENGULFING', -1),
    'bullish_harami': ('CDLHARAMI', 1), 'bearish_harami': ('CDLHARAMI', -1),
    'piercing_line': ('CDLPIERCING', 1), 'dark_cloud_cover': ('CDLDARKCLOUDCOVER', -1),
    'morning_star': ('CDLMORNINGSTAR', 1), 'evening_star': ('CDLEVENINGSTAR', -1),
    'three_white_soldiers': ('CDL3WHITESOLDIERS', 1), 'three_black_crows': ('CDL3BLACKCROWS', -1),
}
window = max(abstract.Function(n).lookback for n in F04) + 1
ours = json.load(open(OURS))
tot, doji, flat_bear = {}, 0, 0
for name in sorted(os.listdir(FIX)):
    if not name.endswith('.json.gz'):
        continue
    f = json.loads(gzip.decompress(open(os.path.join(FIX, name), 'rb').read()))
    if f['ticker'] not in ours:
        continue
    o, h, l, c = (np.array(f[k], dtype=float) for k in 'OHLC')
    n = len(c)
    res = {}
    for fn in set(v[0] for v in MAP.values()) | {'CDLDOJI'}:
        func, lb = getattr(talib, fn), abstract.Function(fn).lookback
        r = np.zeros(n, dtype=np.int32)
        for i in range(lb, n):
            s = max(0, i - window + 1)
            r[i] = func(o[s:i + 1], h[s:i + 1], l[s:i + 1], c[s:i + 1])[-1]
        res[fn] = r
    doji += int((res['CDLDOJI'] != 0).sum())
    flat_bear += int(sum(1 for i in np.nonzero(res['CDLENGULFING'] < 0)[0] if c[i - 1] == o[i - 1]))
    t = ours[f['ticker']]
    for pid, (fn, sign) in MAP.items():
        ta = set(np.nonzero(res[fn] * sign > 0)[0].tolist())
        for v in ('default', 'notrend', 'notrend_tick1'):
            mine = set(t['sig'][f'{pid}|{v}'])
            a = tot.setdefault((pid, v), [0, 0, 0])
            a[0] += len(mine); a[1] += len(ta); a[2] += len(mine & ta)
print(f"bars {sum(ours[k]['n'] for k in ours)}, TA-Lib window {window}, cdl_doji (any doji, no P6 counterpart) {doji}, "
      f'bearish engulfing after a candle with close == open {flat_bear}')
print(f"{'pattern':22} {'setting':14} {'P6':>5} {'F04':>5} {'both':>5} {'P6 in F04 %':>12} {'F04 in P6 %':>12}")
for (pid, v), (a, b, both) in tot.items():
    p1 = 100 * both / a if a else float('nan'); p2 = 100 * both / b if b else float('nan')
    print(f'{pid:22} {v:14} {a:5d} {b:5d} {both:5d} {p1:12.1f} {p2:12.1f}')
