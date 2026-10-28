"""Closed-bar replay of the supplied Pine v6 Nic - HH LL script.

Pine EMA seeds from the first available input (not TA-Lib's SMA seed).
The returned state is the state AFTER every if block executes on that bar.
No labels are backdated into earlier feature rows.
"""
from __future__ import annotations

from collections import deque
from math import isfinite

SWING_COLUMNS = ('smi', 'tracking_high', 'tracking_low', 'temp_high',
                 'temp_high_bar', 'temp_low', 'temp_low_bar',
                 'last_swing_high', 'break_swing_high')
SMI_K_LENGTH = 14
SMI_D_LENGTH = 5
SMI_EMA_LENGTH = 5
SMI_THRESHOLD = 40


def _ema(value, previous, length):
    return value if previous is None else (2.0 / (length + 1)) * value + (1.0 - 2.0 / (length + 1)) * previous


def replay_swing(highs, lows, closes, smi_values, *, bar_offset=0):
    """Replay the literal Pine block order, including a changing swing level.

    Equal threshold touches and recrosses reset temporary peaks exactly as
    in the source. Crossover compares today's close/level AND yesterday's
    close/level; a newly confirmed level is not substituted into yesterday.
    """
    if not (len(highs) == len(lows) == len(closes) == len(smi_values)):
        raise ValueError('Swing inputs must have equal lengths')
    tracking_high = tracking_low = False
    temp_high = temp_high_bar = temp_low = temp_low_bar = last_high = None
    previous_smi = previous_close = previous_level = None
    output = []
    for i, (high, low, close, smi) in enumerate(zip(highs, lows, closes, smi_values)):
        valid_cross = smi is not None and previous_smi is not None
        high_up = valid_cross and smi > SMI_THRESHOLD and previous_smi <= SMI_THRESHOLD
        high_down = valid_cross and smi < SMI_THRESHOLD and previous_smi >= SMI_THRESHOLD
        low_down = valid_cross and smi < -SMI_THRESHOLD and previous_smi >= -SMI_THRESHOLD
        low_up = valid_cross and smi > -SMI_THRESHOLD and previous_smi <= -SMI_THRESHOLD
        if high_up:
            tracking_high, temp_high, temp_high_bar = True, float(high), bar_offset + i
        if tracking_high and smi is not None and smi > SMI_THRESHOLD:
            if high > temp_high:
                temp_high, temp_high_bar = float(high), bar_offset + i
        if tracking_high and high_down:
            last_high = temp_high
            tracking_high = False
            temp_high = temp_high_bar = None
        if low_down:
            tracking_low, temp_low, temp_low_bar = True, float(low), bar_offset + i
        if tracking_low and smi is not None and smi < -SMI_THRESHOLD:
            if low < temp_low:
                temp_low, temp_low_bar = float(low), bar_offset + i
        if tracking_low and low_up:
            tracking_low = False
            temp_low = temp_low_bar = None
        breakout = (last_high is not None and previous_level is not None
                    and previous_close is not None and close > last_high
                    and previous_close <= previous_level)
        output.append(dict(smi=smi, tracking_high=int(tracking_high),
                           tracking_low=int(tracking_low), temp_high=temp_high,
                           temp_high_bar=temp_high_bar, temp_low=temp_low,
                           temp_low_bar=temp_low_bar, last_swing_high=last_high,
                           break_swing_high=int(breakout)))
        previous_smi, previous_close, previous_level = smi, close, last_high
    return output


def calculate_swing(highs, lows, closes, *, bar_offset=0):
    """Valid contiguous OHLC segment; 14-bar extrema allow early partial windows."""
    if not (len(highs) == len(lows) == len(closes)):
        raise ValueError('SMI inputs must have equal lengths')
    rolling_high, rolling_low = deque(maxlen=SMI_K_LENGTH), deque(maxlen=SMI_K_LENGTH)
    rel_ema = rel_double = range_ema = range_double = None
    smi_values = []
    for high, low, close in zip(highs, lows, closes):
        rolling_high.append(float(high))
        rolling_low.append(float(low))
        hh, ll = max(rolling_high), min(rolling_low)
        rel = close - (hh + ll) / 2.0
        rel_ema = _ema(rel, rel_ema, SMI_D_LENGTH)
        rel_double = _ema(rel_ema, rel_double, SMI_EMA_LENGTH)
        range_ema = _ema(hh - ll, range_ema, SMI_D_LENGTH)
        range_double = _ema(range_ema, range_double, SMI_EMA_LENGTH)
        smi = 200.0 * rel_double / range_double if range_double != 0 else None
        smi_values.append(float(smi) if smi is not None and isfinite(smi) else None)
    return replay_swing(highs, lows, closes, smi_values, bar_offset=bar_offset)
