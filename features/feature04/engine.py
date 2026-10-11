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
TABLE = 'Feature_04_Technical_Indicator'
ASSET_TYPES = ('equity', 'bonds')
IDENTITY = ('ticker', 'trade_date', 'timeframe', 'asset_type')
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
V1_COLUMNS = IDENTITY[:3] + INDICATORS + tuple(PATTERNS) + ('calculation_version', 'calculated_at')
EXTENSIONS = ('adx_14', 'ema_50', 'ema_200', 'inside_bar')
INDICATORS = INDICATORS + EXTENSIONS[:3]
DIRECT_COLUMNS = ('close',)
FEATURE_COLUMNS = INDICATORS + tuple(PATTERNS) + ('inside_bar',) + SWING_COLUMNS + DIRECT_COLUMNS
# PostgreSQL appends new columns; retain the physical v1 order for old columns.
V2_COLUMNS = V1_COLUMNS + EXTENSIONS
# PostgreSQL appends asset_type and then close in forward migrations; retain physical order.
COLUMNS = V2_COLUMNS + SWING_COLUMNS + ('asset_type',) + DIRECT_COLUMNS
MACD_COLUMNS = ('macd', 'macd_signal', 'macd_histogram')
BOLLINGER_COLUMNS = ('bb_upper_20', 'bb_middle_20', 'bb_lower_20')
REQUIRED_AFTER = {
    'sma_20': 20, 'sma_50': 50, 'ema_12': 12, 'ema_26': 26,
    'rsi_14': 15, 'macd': 26, 'macd_signal': 34, 'macd_histogram': 34,
    'atr_14': 15, 'bb_upper_20': 20, 'bb_middle_20': 20, 'bb_lower_20': 20,
    'adx_14': 28, 'ema_50': 50, 'ema_200': 200, 'inside_bar': 2,
}


def dependency_closure(columns: Iterable[str] | None) -> tuple[str, ...]:
    """Return the output bundle that must remain coherent for a retry.

    ``None`` means a normal full-ticker refresh. Identity and metadata fields
    are deliberately excluded from the selectable surface.
    """
    if columns is None:
        return FEATURE_COLUMNS
    requested = set(columns)
    unknown = requested.difference(FEATURE_COLUMNS)
    if unknown:
        raise ValueError(f'Unknown Feature04 columns: {sorted(unknown)}')
    if requested.intersection(MACD_COLUMNS) or requested.intersection({'ema_12', 'ema_26'}):
        requested.update(MACD_COLUMNS)
    if requested.intersection(BOLLINGER_COLUMNS):
        requested.update(BOLLINGER_COLUMNS)
    if requested.intersection(SWING_COLUMNS):
        requested.update(SWING_COLUMNS)
    return tuple(column for column in FEATURE_COLUMNS if column in requested)


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
        o, h, l, c = [float(row[k]) for k in ('open', 'high', 'low', 'close')]
        if not (all(isfinite(x) and x >= 0 for x in (o, h, l, c))
                and l <= o <= h and l <= c <= h):
            return False
        if row['asset_type'] == 'bonds':
            return row.get('volume') is None or (
                isfinite(float(row['volume'])) and float(row['volume']) >= 0
            )
        v = float(row['volume'])
        return isfinite(v) and v >= 0
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


def calculate_with_diagnostics(
    rows: Iterable[dict],
    *,
    requested_columns: Iterable[str] | None = None,
    calculated_at: datetime | None = None,
    fail_groups: Iterable[str] = (),
) -> tuple[list[dict], dict[str, dict]]:
    """Partition and sort daily observations, never fill missing dates.

    An invalid/missing OHLCV row is retained with NULL features and resets all
    indicator histories. TA-Lib's leading candlestick zeroes before lookback
    are unavailable, so become NULL. Genuine post-lookback zeroes stay INTEGER 0.
    """
    contract = library_contract()
    selected = dependency_closure(requested_columns)
    selected_set = set(selected)
    injected_failures = set(fail_groups)
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
        asset_type = r.get('asset_type')
        if asset_type not in ASSET_TYPES:
            raise ValueError('asset_type must be classified from an approved universe')
        if r['timeframe'] != 'Daily':
            raise ValueError('Only verified source timeframe Daily is supported')
        if 'source' in r and r['source'] != 'TradingView':
            raise ValueError('Source provider must remain TradingView')
        day = observation_date(r['date'])
        if day.isoweekday() > 5:
            raise ValueError('Weekend source bar is unsupported')
        symbol = r.get('tradingview_symbol')
        if asset_type == 'equity' and symbol != 'IDX:' + ticker:
            raise ValueError('Equity source ticker/exchange mapping differs from IDX:ticker')
        if asset_type == 'bonds' and (not isinstance(symbol, str) or not symbol.strip()):
            raise ValueError('Bond source requires a nonempty TradingView symbol')
        key = (asset_type, ticker, day, r['timeframe'])
        if key in keys:
            raise ValueError('Duplicate security/date/timeframe observation')
        keys.add(key)
        r['date'] = day
        groups[(asset_type, ticker, r['timeframe'])].append(r)
    output = []
    outcomes: dict[str, dict] = {}

    def run_group(name: str, columns: tuple[str, ...], operation) -> None:
        if not selected_set.intersection(columns):
            return
        if outcomes.get(name, {}).get('status') == 'FAILED':
            return
        try:
            if name in injected_failures:
                raise RuntimeError(f'injected failure for {name}')
            operation()
            outcomes[name] = {'status': 'SUCCESS', 'columns': list(columns)}
        except Exception as exc:
            outcomes[name] = {
                'status': 'FAILED',
                'columns': list(columns),
                'error': f'{type(exc).__name__}: {exc}'[:1000],
            }
    for (asset_type, ticker, timeframe), series in sorted(groups.items()):
        series.sort(key=lambda r: r['date'])
        results = [dict.fromkeys(COLUMNS) for _ in series]
        for r, out in zip(series, results):
            out.update(ticker=ticker, trade_date=r['date'], timeframe=timeframe,
                       asset_type=asset_type,
                       calculation_version=VERSION, calculated_at=stamp)

        def copy_close():
            for source, result in zip(series, results):
                value = float(source['close'])
                if not isfinite(value) or value < 0:
                    raise ValueError('Source close must be finite and nonnegative')
                result['close'] = value

        run_group('source_close', DIRECT_COLUMNS, copy_close)
        for start, end in _segments([_valid(r) for r in series]):
            segment = series[start:end]
            o, h, l, c = [np.array([float(r[k]) for r in segment], dtype=np.float64)
                           for k in ('open', 'high', 'low', 'close')]
            def assign_numeric(column, array):
                for j, value in enumerate(array):
                    results[start + j][column] = float(value) if np.isfinite(value) else None

            for column, function, arguments in (
                ('sma_20', talib.SMA, (c,)), ('sma_50', talib.SMA, (c,)),
                ('ema_12', talib.EMA, (c,)), ('ema_26', talib.EMA, (c,)),
                ('ema_50', talib.EMA, (c,)), ('ema_200', talib.EMA, (c,)),
                ('adx_14', talib.ADX, (h, l, c)), ('rsi_14', talib.RSI, (c,)),
                ('atr_14', talib.ATR, (h, l, c)),
            ):
                period = int(column.rsplit('_', 1)[1])
                run_group(column, (column,), lambda col=column, fn=function, args=arguments, p=period:
                          assign_numeric(col, fn(*args, timeperiod=p)))

            def calculate_macd_bundle():
                ema12 = talib.EMA(c, timeperiod=12)
                ema26 = talib.EMA(c, timeperiod=26)
                macd = ema12 - ema26
                signal = np.full(len(c), np.nan)
                if len(c) >= 26:
                    signal[25:] = talib.EMA(macd[25:], timeperiod=9)
                for column, array in zip(MACD_COLUMNS, (macd, signal, macd - signal)):
                    assign_numeric(column, array)
            run_group('macd_bundle', MACD_COLUMNS, calculate_macd_bundle)

            def calculate_bollinger_bundle():
                arrays = talib.BBANDS(c, timeperiod=20, nbdevup=2.0, nbdevdn=2.0, matype=0)
                for column, array in zip(BOLLINGER_COLUMNS, arrays):
                    assign_numeric(column, array)
            run_group('bollinger_bundle', BOLLINGER_COLUMNS, calculate_bollinger_bundle)

            def calculate_inside_bar():
                for j in range(1, len(segment)):
                    current, previous = segment[j], segment[j - 1]
                    high, low, previous_high, previous_low = [Decimal(str(v)) for v in
                        (current['high'], current['low'], previous['high'], previous['low'])]
                    results[start + j]['inside_bar'] = int(high < previous_high and low > previous_low)
            run_group('inside_bar', ('inside_bar',), calculate_inside_bar)

            def calculate_swing_bundle():
                for j, state in enumerate(calculate_swing(h, l, c, bar_offset=start)):
                    results[start + j].update(state)
            run_group('smi_swing_bundle', SWING_COLUMNS, calculate_swing_bundle)

            for column, name in PATTERNS.items():
                def calculate_pattern(col=column, fn_name=name):
                    lookback = contract['patterns'][fn_name]['lookback']
                    array = getattr(talib, fn_name)(o, h, l, c, **contract['patterns'][fn_name]['parameters'])
                    for j, value in enumerate(array):
                        if j >= lookback:
                            results[start + j][col] = int(value)
                run_group('pattern:' + column, (column,), calculate_pattern)
        output.extend(results)
    return output, outcomes


def calculate(rows: Iterable[dict], *, calculated_at: datetime | None = None) -> list[dict]:
    """Calculate the complete v3 payload and fail atomically on any formula error."""
    output, outcomes = calculate_with_diagnostics(rows, calculated_at=calculated_at)
    failed = {name: value for name, value in outcomes.items() if value['status'] == 'FAILED'}
    if failed:
        raise RuntimeError(f'Feature04 calculation group failed: {failed}')
    return output


def validate_output_availability(
    history: Iterable[dict], output: Iterable[dict],
    *, requested_columns: Iterable[str] | None = None,
) -> dict[str, dict]:
    """Report unavailable values where valid source history requires an output.

    Check every observation, counting warmup again after each invalid source row.
    Stateful swing availability follows the Pine replay: a temporary peak or a
    confirmed high is required only while its corresponding state exists.
    """
    selected = set(dependency_closure(requested_columns))
    contract = library_contract()
    required_after = {
        **REQUIRED_AFTER,
        **{column: contract['patterns'][name]['lookback'] + 1
           for column, name in PATTERNS.items()},
    }
    by_key = {}
    for row in output:
        key = (row['asset_type'], row['ticker'], observation_date(row['trade_date']), row['timeframe'])
        if key in by_key:
            raise ValueError('Duplicate Feature04 output observation')
        by_key[key] = row
    groups = defaultdict(list)
    seen = set()
    for source in history:
        row = dict(source)
        row['date'] = observation_date(row['date'])
        key = (row['asset_type'], row['ticker'], row['date'], row['timeframe'])
        if key in seen or key not in by_key:
            raise ValueError('Feature04 output must match each source observation once')
        seen.add(key)
        groups[(row['asset_type'], row['ticker'], row['timeframe'])].append(row)
    if seen != set(by_key):
        raise ValueError('Feature04 output contains observations outside source history')
    failures = {}

    def record(column, row):
        info = failures.setdefault(column, {
            'status': 'FAILED', 'columns': [column], 'missing_rows': 0,
            'first_ticker': row['ticker'], 'first_date': str(row['date']),
            'error': 'Unexpected NULL where the source/formula availability contract requires a value',
        })
        info['missing_rows'] += 1
        info['last_date'] = str(row['date'])

    for (asset_type, ticker, timeframe), series in sorted(groups.items()):
        series.sort(key=lambda row: row['date'])
        if 'close' in selected:
            for source in series:
                actual = by_key[(asset_type, ticker, source['date'], timeframe)]
                if actual.get('close') is None:
                    record('close', source)
        for start, end in _segments([_valid(row) for row in series]):
            segment = series[start:end]
            swing = None
            if selected.intersection(SWING_COLUMNS):
                h, l, c = [np.array([float(row[key]) for row in segment], dtype=np.float64)
                           for key in ('high', 'low', 'close')]
                swing = calculate_swing(h, l, c, bar_offset=start)
            for position, source in enumerate(segment):
                actual = by_key[(asset_type, ticker, source['date'], timeframe)]
                required = {
                    column for column, first_bar in required_after.items()
                    if position + 1 >= first_bar
                }
                if swing is not None:
                    required.update(column for column in SWING_COLUMNS
                                    if swing[position][column] is not None)
                for column in sorted(selected.intersection(required)):
                    if actual.get(column) is None:
                        record(column, source)
    return failures
