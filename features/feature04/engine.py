"""Causal daily technical features; no database writes in this module.

v3 preserves v1/v2 calculations and adds Pine-seeded SMI and closed-bar swing state.
The existing indicators use TA-Lib default compatibility/initialization.
TradingView formula definitions are the intended benchmark, but
its chart seed/history and ATR first-bar treatment are NOT claimed equivalent.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from math import isfinite
from typing import Iterable

import numpy as np
import talib
from talib import abstract
from swing import SWING_COLUMNS, calculate_swing

VERSION = 'feature04-v3-smi14-5-5-th40-talib0.6.8-c0.6.4'
TABLE = 'Feature04_Technical_Indicator'
IDENTITY = ('ticker', 'trade_date', 'timeframe')
INDICATORS = ('sma_20', 'sma_50', 'ema_12', 'ema_26', 'rsi_14', 'macd',
              'macd_signal', 'macd_histogram', 'atr_14', 'bb_upper_20',
              'bb_middle_20', 'bb_lower_20')
PATTERNS = {
 'cdl_piercing': 'CDLPIERCING', 'cdl_morning_star': 'CDLMORNINGSTAR',
 'cdl_morning_doji_star': 'CDLMORNINGDOJISTAR', 'cdl_engulfing': 'CDLENGULFING',
 'cdl_3_white_soldiers': 'CDL3WHITESOLDIERS', 'cdl_hammer': 'CDLHAMMER',
 'cdl_inverted_hammer': 'CDLINVERTEDHAMMER', 'cdl_3_inside': 'CDL3INSIDE',
 'cdl_3_outside': 'CDL3OUTSIDE', 'cdl_harami': 'CDLHARAMI',
 'cdl_harami_cross': 'CDLHARAMICROSS', 'cdl_dark_cloud_cover': 'CDLDARKCLOUDCOVER',
 'cdl_evening_star': 'CDLEVENINGSTAR', 'cdl_evening_doji_star': 'CDLEVENINGDOJISTAR',
 'cdl_3_black_crows': 'CDL3BLACKCROWS', 'cdl_shooting_star': 'CDLSHOOTINGSTAR',
 'cdl_hanging_man': 'CDLHANGINGMAN', 'cdl_doji': 'CDLDOJI',
 'cdl_dragonfly_doji': 'CDLDRAGONFLYDOJI', 'cdl_gravestone_doji': 'CDLGRAVESTONEDOJI',
 'cdl_marubozu': 'CDLMARUBOZU', 'cdl_kicking': 'CDLKICKING',
 'cdl_rise_fall_3_methods': 'CDLRISEFALL3METHODS', 'cdl_mat_hold': 'CDLMATHOLD',
 'cdl_hikkake': 'CDLHIKKAKE',
}
V1_COLUMNS = IDENTITY + INDICATORS + tuple(PATTERNS) + ('calculation_version', 'calculated_at')
EXTENSIONS = ('adx_14', 'ema_50', 'ema_200', 'inside_bar')
INDICATORS = INDICATORS + EXTENSIONS[:3]
FEATURE_COLUMNS = INDICATORS + tuple(PATTERNS) + ('inside_bar',) + SWING_COLUMNS
# PostgreSQL appends new columns; retain the physical v1 order for old columns.
V2_COLUMNS = V1_COLUMNS + EXTENSIONS
COLUMNS = V2_COLUMNS + SWING_COLUMNS


def library_contract() -> dict:
    if talib.__version__ != '0.6.8' or not talib.__ta_version__.startswith(b'0.6.4 '):
        raise RuntimeError('Calculation version requires TA-Lib Python 0.6.8 / C 0.6.4')
    if talib.get_compatibility() != 0:
        raise RuntimeError('TA-Lib default compatibility is required')
    for name in ('EMA', 'RSI', 'ATR', 'ADX'):
        if talib.get_unstable_period(name) != 0:
            raise RuntimeError('TA-Lib unstable periods must remain zero')
    functions = {}
    for name in PATTERNS.values():
        f = abstract.Function(name)
        functions[name] = {'lookback': f.lookback, 'parameters': dict(f.parameters)}
    return {'python': talib.__version__, 'c': talib.__ta_version__.decode(),
            'numpy': np.__version__, 'compatibility': 0, 'unstable_period': 0,
            'patterns': functions}


def observation_date(value) -> date:
    if isinstance(value, datetime):
        raise ValueError('Source requires a DATE, not an intraday timestamp')
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _valid(row) -> bool:
    try:
        o, h, l, c, v = [float(row[k]) for k in ('open', 'high', 'low', 'close', 'volume')]
        return all(isfinite(x) and x >= 0 for x in (o, h, l, c, v)) and l <= o <= h and l <= c <= h
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def _segments(valid):
    start = None
    for i, ok in enumerate([*valid, False]):
        if ok and start is None:
            start = i
        elif not ok and start is not None:
            yield start, i
            start = None


def calculate(rows: Iterable[dict], *, calculated_at: datetime | None = None) -> list[dict]:
    """Partition and sort daily observations, never fill missing dates.

    An invalid/missing OHLCV row is retained with NULL features and resets all
    indicator histories. TA-Lib's leading candlestick zeroes before lookback
    are unavailable, so become NULL. Genuine post-lookback zeroes stay INTEGER 0.
    """
    contract = library_contract()
    stamp = calculated_at or datetime.now(timezone.utc)
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError('calculated_at must be timezone-aware')
    groups = defaultdict(list)
    keys = set()
    for source in rows:
        r = dict(source)
        ticker = r['ticker']
        if not isinstance(ticker, str) or not ticker or ticker != ticker.strip().upper():
            raise ValueError('Ticker must be nonempty, trimmed and upper-case')
        if r['timeframe'] != 'Daily':
            raise ValueError('Only verified source timeframe Daily is supported')
        if 'source' in r and r['source'] != 'TradingView':
            raise ValueError('Source provider must remain TradingView')
        day = observation_date(r['date'])
        if day.isoweekday() > 5:
            raise ValueError('Weekend source bar is unsupported')
        symbol = r.get('tradingview_symbol', 'IDX:' + ticker)
        if symbol != 'IDX:' + ticker:
            raise ValueError('Source ticker/exchange mapping differs from IDX:ticker')
        key = (ticker, day, r['timeframe'])
        if key in keys:
            raise ValueError('Duplicate security/date/timeframe observation')
        keys.add(key)
        r['date'] = day
        groups[(ticker, r['timeframe'])].append(r)
    output = []
    for (ticker, timeframe), series in sorted(groups.items()):
        series.sort(key=lambda r: r['date'])
        results = [dict.fromkeys(COLUMNS) for _ in series]
        for r, out in zip(series, results):
            out.update(ticker=ticker, trade_date=r['date'], timeframe=timeframe,
                       calculation_version=VERSION, calculated_at=stamp)
        for start, end in _segments([_valid(r) for r in series]):
            segment = series[start:end]
            o, h, l, c = [np.array([float(r[k]) for r in segment], dtype=np.float64)
                           for k in ('open', 'high', 'low', 'close')]
            for j, state in enumerate(calculate_swing(h, l, c, bar_offset=start)):
                results[start + j].update(state)
            numeric = {
                'sma_20': talib.SMA(c, timeperiod=20),
                'sma_50': talib.SMA(c, timeperiod=50),
                'ema_12': talib.EMA(c, timeperiod=12),
                'ema_26': talib.EMA(c, timeperiod=26),
                'ema_50': talib.EMA(c, timeperiod=50),
                'ema_200': talib.EMA(c, timeperiod=200),
                'adx_14': talib.ADX(h, l, c, timeperiod=14),
                'rsi_14': talib.RSI(c, timeperiod=14),
                'atr_14': talib.ATR(h, l, c, timeperiod=14),
            }
            macd = numeric['ema_12'] - numeric['ema_26']
            signal = np.full(len(c), np.nan)
            if len(c) >= 26:
                signal[25:] = talib.EMA(macd[25:], timeperiod=9)
            histogram = macd - signal
            numeric.update(macd=macd, macd_signal=signal, macd_histogram=histogram)
            upper, middle, lower = talib.BBANDS(c, timeperiod=20, nbdevup=2.0, nbdevdn=2.0, matype=0)
            numeric.update(bb_upper_20=upper, bb_middle_20=middle, bb_lower_20=lower)
            # Strict range containment labels this candle, using only its predecessor.
            # Compare original numeric values rather than rounding prices to float64.
            for j in range(1, len(segment)):
                current, previous = segment[j], segment[j - 1]
                high, low, previous_high, previous_low = [Decimal(str(v)) for v in
                    (current['high'], current['low'], previous['high'], previous['low'])]
                results[start + j]['inside_bar'] = int(high < previous_high and low > previous_low)
            for column, array in numeric.items():
                for j, value in enumerate(array):
                    results[start + j][column] = float(value) if np.isfinite(value) else None
            for column, name in PATTERNS.items():
                lookback = contract['patterns'][name]['lookback']
                array = getattr(talib, name)(o, h, l, c, **contract['patterns'][name]['parameters'])
                for j, value in enumerate(array):
                    if j >= lookback:
                        results[start + j][column] = int(value)
        output.extend(results)
    return output
