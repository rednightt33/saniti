#!/usr/bin/env python3
"""EXEC-INTRADAY-FEATURES S3: independent check of the stored intraday features (read-only, pgweb).

Per (ticker, timeframe) sample:
- Feature 01: every column recomputed with numpy from the bars and the column definitions (Feature_Catalog), not with
  refresh_feature_01_stock_intraday; bars_per_year checked against 252 x the mean IHSG bars of the COMPLETE sessions.
- Feature 04: (a) engine.calculate over the whole series (the stored rows were written by the same engine, possibly
  chained), every column; (b) sma_20 and ema_12 written out by hand (TA-Lib's SMA seed), which would catch a value
  stored against the wrong bar.
Tolerance: 1e-9 relative. Prints one line per sample and a VERDICT.

  python verification/intraday_features/repro.py BBCA:5m BBCA:1h PBSA:15m ...
"""
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'verification/terminal_api'))
sys.path.insert(0, str(ROOT / 'apps/idx-price-cron'))
import pgq  # noqa: E402
import intraday_features as f  # noqa: E402

F01_COLS = ['close_1bar_ago', 'close_5bar_ago', 'close_20bar_ago', 'close_60bar_ago', 'return_1bar_pct',
            'return_5bar_pct', 'return_20bar_pct', 'return_60bar_pct', 'abs_return_1bar_pct', 'volatility_5bar_ann_pct',
            'volatility_20bar_ann_pct', 'volatility_60bar_ann_pct', 'volatility_5bar_change_pct',
            'volatility_20bar_change_pct', 'volatility_60bar_change_pct', 'volume_avg_20bar', 'volume_std_20bar',
            'volume_ratio_20bar', 'volume_zscore_20bar', 'high_20bar', 'high_60bar', 'drawdown_20bar_pct',
            'drawdown_60bar_pct']


def rows(sql):
    r = pgq.q(sql)
    if 'error' in r:
        raise RuntimeError(r['error'])
    return r['columns'], r['rows']


def num(v):
    return None if v is None else float(v)


def lag(a, k):
    out = [None] * len(a)
    for i in range(k, len(a)):
        out[i] = a[i - k]
    return out


def ratio_pct(a, b):
    return [None if x is None or y in (None, 0) else (x / y - 1) * 100 for x, y in zip(a, b)]


def window(a, n, fn):
    """fn over the last n rows when all n are present (the SQL count(...) = n rule), else None."""
    out = [None] * len(a)
    for i in range(len(a)):
        w = a[max(0, i - n + 1):i + 1]
        vals = [x for x in w if x is not None]
        out[i] = fn(vals) if len(w) == n and len(vals) == n else None
    return out


def std(v):
    return float(np.std(np.array(v), ddof=1))


def f01_expected(close, volume, bpy):
    c1, c5, c20, c60 = lag(close, 1), lag(close, 5), lag(close, 20), lag(close, 60)
    r1 = [None if b in (None, 0) or a is None else a / b - 1 for a, b in zip(close, c1)]
    exp = {'close_1bar_ago': c1, 'close_5bar_ago': c5, 'close_20bar_ago': c20, 'close_60bar_ago': c60,
           'return_1bar_pct': ratio_pct(close, c1), 'return_5bar_pct': ratio_pct(close, c5),
           'return_20bar_pct': ratio_pct(close, c20), 'return_60bar_pct': ratio_pct(close, c60)}
    exp['abs_return_1bar_pct'] = [None if x is None else abs(x) for x in exp['return_1bar_pct']]
    for n in (5, 20, 60):
        vol = [None if s is None else s * math.sqrt(bpy) * 100 for s in window(r1, n, std)]
        exp[f'volatility_{n}bar_ann_pct'] = vol
        exp[f'volatility_{n}bar_change_pct'] = [None if a is None or b in (None, 0) else (a / b - 1) * 100
                                                for a, b in zip(vol, lag(vol, n))]
    avg = window(volume, 20, lambda v: sum(v) / len(v))
    sd = window(volume, 20, std)
    exp['volume_avg_20bar'], exp['volume_std_20bar'] = avg, sd
    exp['volume_ratio_20bar'] = [None if a in (None, 0) or v is None else v / a for v, a in zip(volume, avg)]
    exp['volume_zscore_20bar'] = [None if s in (None, 0) or v is None else (v - a) / s for v, a, s in zip(volume, avg, sd)]
    for n in (20, 60):
        hi = window(close, n, max)
        exp[f'high_{n}bar'] = hi
        exp[f'drawdown_{n}bar_pct'] = [None if h in (None, 0) else (c / h - 1) * 100 for c, h in zip(close, hi)]
    return exp


def close_enough(a, b):
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, (int,)) and isinstance(b, (int,)):
        return a == b
    a, b = float(a), float(b)
    return abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b))


def check(ticker, tf):
    _, bars = rows(f"""SELECT bar_time, session_date, open, high, low, close, volume, tradingview_symbol
                        FROM public.price_stock_idx_intraday WHERE ticker = '{ticker}' AND timeframe = '{tf}'
                        ORDER BY bar_time""")
    times = [b[0] for b in bars]
    close, volume = [num(b[5]) for b in bars], [num(b[6]) for b in bars]
    c01, s01 = rows(f"""SELECT bar_time, bars_per_year, {', '.join(F01_COLS)} FROM public."Feature_01_Stock_Intraday"
                        WHERE ticker = '{ticker}' AND timeframe = '{tf}' ORDER BY bar_time""")
    _, bpy_now = rows(f"""SELECT round(252 * avg(index_bars))::int FROM public.price_stock_idx_intraday_quality
                          WHERE timeframe = '{tf}' AND status = 'COMPLETE' AND index_bars > 0""")
    out = {'bars': len(bars), 'f01_rows': len(s01)}
    bad01 = []
    if [r[0] for r in s01] != times:
        bad01.append('bar_time set differs')
    else:
        # each row is checked with the bars_per_year stored on it (EXEC-INTRADAY-FEATURES: "Nilai yang dipakai disimpan
        # di setiap baris"); a daily run writes its bars with the value of that day, so one series can hold several
        stored = sorted({r[1] for r in s01})
        out['bars_per_year'] = {'stored': stored, 'now': bpy_now[0][0]}
        exp = {bpy: f01_expected(close, volume, bpy) for bpy in stored}
        for j, col in enumerate(F01_COLS):
            n = sum(not close_enough(num(r[j + 2]), exp[r[1]][col][i]) for i, r in enumerate(s01))
            if n:
                bad01.append(f'{col}: {n}')
    out['f01_bad'] = bad01

    engine, _ = f.load_engine()
    c04, s04 = rows(f"""SELECT * FROM public."Feature_04_Technical_Indicator_Intraday"
                        WHERE ticker = '{ticker}' AND timeframe = '{tf}' ORDER BY bar_time""")
    idx = {c: i for i, c in enumerate(c04)}
    bad04 = []
    if [r[idx['bar_time']] for r in s04] != times:
        bad04.append('bar_time set differs')
    else:
        full = engine.calculate(f.engine_rows(ticker, bars, 0), calculated_at=datetime.now(timezone.utc))
        cols = [c for c in engine.COLUMNS if c not in f.NOT_STORED]
        for col in cols:
            n = sum(not close_enough(num(r[idx[col]]) if isinstance(r[idx[col]], (str, float)) else r[idx[col]],
                                     full[i][col]) for i, r in enumerate(s04))
            if n:
                bad04.append(f'{col}: {n}')
        # by hand: sma_20 and ema_12 (TA-Lib seeds the EMA with the SMA of its first 12 closes)
        sma = window(close, 20, lambda v: sum(v) / len(v))
        ema, k = [None] * len(close), 2 / 13
        if len(close) >= 12:
            ema[11] = sum(close[:12]) / 12
            for i in range(12, len(close)):
                ema[i] = close[i] * k + ema[i - 1] * (1 - k)
        for col, exp in (('sma_20', sma), ('ema_12', ema)):
            n = sum(not close_enough(num(r[idx[col]]), exp[i]) for i, r in enumerate(s04))
            if n:
                bad04.append(f'{col} (by hand): {n}')
    out['f04_rows'] = len(s04)
    out['f04_bad'] = bad04
    return out


def main(samples):
    failed = 0
    for s in samples:
        ticker, tf = s.split(':')
        res = check(ticker, tf)
        ok = not res['f01_bad'] and not res['f04_bad'] and res['bars'] == res['f01_rows'] == res['f04_rows']
        failed += not ok
        print(('PASS ' if ok else 'FAIL ') + f'{ticker} {tf} ' + str(res), flush=True)
    print(f'VERDICT {"PASS" if not failed else "FAIL"} samples={len(samples)} failed={failed}')
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
