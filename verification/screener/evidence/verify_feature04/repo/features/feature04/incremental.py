"""Exact suffix calculation from a versioned Feature04 checkpoint.

The daily worker uses this module only after a trusted checkpoint immediately
before ``dirty_from_date``.  The existing full-history engine remains the
reference oracle and the explicit repair/bootstrap path.
"""
from __future__ import annotations

from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from math import isfinite
from typing import Iterable

import numpy as np
import talib

from engine import (
    BOLLINGER_COLUMNS,
    COLUMNS,
    DIRECT_COLUMNS,
    FEATURE_COLUMNS,
    MACD_COLUMNS,
    PATTERNS,
    VERSION,
    _valid,
    dependency_closure,
    library_contract,
    observation_date,
)
from swing import SMI_D_LENGTH, SMI_EMA_LENGTH, SMI_K_LENGTH, SMI_THRESHOLD, SWING_COLUMNS


STATE_VERSION = "feature04-state-v3"
EMA_PERIODS = (12, 26, 50, 200)
MAX_CLOSE_BUFFER = 50
MAX_PATTERN_LOOKBACK = max(
    value["lookback"] for value in library_contract()["patterns"].values()
)


def _ema_state() -> dict:
    return {"count": 0, "sum": 0.0, "value": None}


def new_state() -> dict:
    return {
        "state_version": STATE_VERSION,
        "calculation_version": VERSION,
        "last_date": None,
        "source_chain_sha256": hashlib.sha256(b"").hexdigest(),
        "position": 0,
        "segment_count": 0,
        "close_buffer": [],
        "sma": {"20": {"sum": 0.0, "buffer": []},
                "50": {"sum": 0.0, "buffer": []}},
        "bbands": {"sum": 0.0, "sum_squares": 0.0, "buffer": []},
        "pattern_buffer": [],
        "previous_valid": None,
        "ema": {str(period): _ema_state() for period in EMA_PERIODS},
        "macd_signal": _ema_state(),
        "rsi": {
            "previous_close": None,
            "delta_count": 0,
            "gain_sum": 0.0,
            "loss_sum": 0.0,
            "average_gain": None,
            "average_loss": None,
        },
        "atr": {
            "previous_close": None,
            "delta_count": 0,
            "tr_sum": 0.0,
            "value": None,
        },
        "adx": {
            "previous_high": None,
            "previous_low": None,
            "previous_close": None,
            "delta_count": 0,
            "smoothed_tr": 0.0,
            "smoothed_plus_dm": 0.0,
            "smoothed_minus_dm": 0.0,
            "dx_seed": [],
            "value": None,
        },
        "smi": {
            "highs": [],
            "lows": [],
            "rel_ema": None,
            "rel_double": None,
            "range_ema": None,
            "range_double": None,
        },
        "swing": {
            "tracking_high": False,
            "tracking_low": False,
            "temp_high": None,
            "temp_high_bar": None,
            "temp_low": None,
            "temp_low_bar": None,
            "last_swing_high": None,
            "previous_smi": None,
            "previous_close": None,
            "previous_level": None,
        },
    }


def validate_state(state: dict) -> dict:
    value = deepcopy(state)
    if value.get("state_version") != STATE_VERSION:
        raise ValueError("Feature04 checkpoint state version is incompatible")
    if value.get("calculation_version") != VERSION:
        raise ValueError("Feature04 checkpoint calculation version is incompatible")
    if int(value.get("position", -1)) < 0:
        raise ValueError("Feature04 checkpoint position is invalid")
    return value


def _reset_segment(state: dict) -> None:
    fresh = new_state()
    for key in (
        "segment_count", "close_buffer", "sma", "bbands", "pattern_buffer", "previous_valid", "ema",
        "macd_signal", "rsi", "atr", "adx", "smi", "swing",
    ):
        state[key] = fresh[key]


def _update_seeded_ema(state: dict, value: float, period: int) -> float | None:
    state["count"] += 1
    if state["value"] is None:
        state["sum"] += value
        if state["count"] < period:
            return None
        state["value"] = state["sum"] / period
        return state["value"]
    alpha = 2.0 / (period + 1.0)
    state["value"] = state["value"] + alpha * (value - state["value"])
    return state["value"]


def _update_rolling_mean(state: dict, value: float, period: int) -> float | None:
    """Match TA-Lib SMA's add/output/subtract order across checkpoints."""
    buffer = deque(state["buffer"])
    state["sum"] += value
    buffer.append(value)
    if len(buffer) < period:
        state["buffer"] = list(buffer)
        return None
    result = state["sum"] / period
    state["sum"] -= buffer.popleft()
    state["buffer"] = list(buffer)
    return result


def _update_bbands(state: dict, value: float, period: int = 20) -> tuple[float, float, float] | None:
    """Match TA-Lib's rolling mean/variance update order for BBANDS."""
    buffer = deque(state["buffer"])
    state["sum"] += value
    state["sum_squares"] += value * value
    buffer.append(value)
    if len(buffer) < period:
        state["buffer"] = list(buffer)
        return None
    middle = state["sum"] / period
    variance = state["sum_squares"] / period - middle * middle
    deviation = variance ** 0.5 if variance > 0.0 else 0.0
    oldest = buffer.popleft()
    state["sum"] -= oldest
    state["sum_squares"] -= oldest * oldest
    state["buffer"] = list(buffer)
    return middle + 2.0 * deviation, middle, middle - 2.0 * deviation


def _pine_ema(value: float, previous: float | None, length: int) -> float:
    if previous is None:
        return value
    alpha = 2.0 / (length + 1.0)
    return alpha * value + (1.0 - alpha) * previous


def _update_rsi(state: dict, close: float, period: int = 14) -> float | None:
    previous = state["previous_close"]
    state["previous_close"] = close
    if previous is None:
        return None
    delta = close - previous
    gain, loss = max(delta, 0.0), max(-delta, 0.0)
    state["delta_count"] += 1
    if state["average_gain"] is None:
        state["gain_sum"] += gain
        state["loss_sum"] += loss
        if state["delta_count"] < period:
            return None
        state["average_gain"] = state["gain_sum"] / period
        state["average_loss"] = state["loss_sum"] / period
    else:
        state["average_gain"] = (state["average_gain"] * (period - 1) + gain) / period
        state["average_loss"] = (state["average_loss"] * (period - 1) + loss) / period
    total = state["average_gain"] + state["average_loss"]
    return 100.0 * state["average_gain"] / total if total else 0.0


def _true_range(high: float, low: float, previous_close: float) -> float:
    return max(high - low, abs(high - previous_close), abs(low - previous_close))


def _update_atr(state: dict, high: float, low: float, close: float, period: int = 14) -> float | None:
    previous = state["previous_close"]
    state["previous_close"] = close
    if previous is None:
        return None
    tr = _true_range(high, low, previous)
    state["delta_count"] += 1
    if state["value"] is None:
        state["tr_sum"] += tr
        if state["delta_count"] < period:
            return None
        state["value"] = state["tr_sum"] / period
    else:
        state["value"] = (state["value"] * (period - 1) + tr) / period
    return state["value"]


def _update_adx(state: dict, high: float, low: float, close: float, period: int = 14) -> float | None:
    previous_high = state["previous_high"]
    previous_low = state["previous_low"]
    previous_close = state["previous_close"]
    state["previous_high"], state["previous_low"], state["previous_close"] = high, low, close
    if previous_high is None:
        return None
    up_move, down_move = high - previous_high, previous_low - low
    plus_dm = up_move if up_move > down_move and up_move > 0.0 else 0.0
    minus_dm = down_move if down_move > up_move and down_move > 0.0 else 0.0
    tr = _true_range(high, low, previous_close)
    state["delta_count"] += 1
    if state["delta_count"] <= period - 1:
        state["smoothed_tr"] += tr
        state["smoothed_plus_dm"] += plus_dm
        state["smoothed_minus_dm"] += minus_dm
        return None
    state["smoothed_tr"] = state["smoothed_tr"] - state["smoothed_tr"] / period + tr
    state["smoothed_plus_dm"] = (
        state["smoothed_plus_dm"] - state["smoothed_plus_dm"] / period + plus_dm
    )
    state["smoothed_minus_dm"] = (
        state["smoothed_minus_dm"] - state["smoothed_minus_dm"] / period + minus_dm
    )
    if state["smoothed_tr"]:
        plus_di = 100.0 * state["smoothed_plus_dm"] / state["smoothed_tr"]
        minus_di = 100.0 * state["smoothed_minus_dm"] / state["smoothed_tr"]
    else:
        plus_di = minus_di = 0.0
    denominator = plus_di + minus_di
    dx = 100.0 * abs(plus_di - minus_di) / denominator if denominator else 0.0
    if state["value"] is None:
        state["dx_seed"].append(dx)
        if len(state["dx_seed"]) < period:
            return None
        state["value"] = sum(state["dx_seed"]) / period
    else:
        state["value"] = (state["value"] * (period - 1) + dx) / period
    return state["value"]


def _update_smi(state: dict, high: float, low: float, close: float) -> float | None:
    highs = deque(state["highs"], maxlen=SMI_K_LENGTH)
    lows = deque(state["lows"], maxlen=SMI_K_LENGTH)
    highs.append(high)
    lows.append(low)
    state["highs"], state["lows"] = list(highs), list(lows)
    highest, lowest = max(highs), min(lows)
    relative = close - (highest + lowest) / 2.0
    price_range = highest - lowest
    state["rel_ema"] = _pine_ema(relative, state["rel_ema"], SMI_D_LENGTH)
    state["rel_double"] = _pine_ema(state["rel_ema"], state["rel_double"], SMI_EMA_LENGTH)
    state["range_ema"] = _pine_ema(price_range, state["range_ema"], SMI_D_LENGTH)
    state["range_double"] = _pine_ema(state["range_ema"], state["range_double"], SMI_EMA_LENGTH)
    if state["range_double"] == 0:
        return None
    value = 200.0 * state["rel_double"] / state["range_double"]
    return float(value) if isfinite(value) else None


def _update_swing(state: dict, high: float, low: float, close: float, smi: float | None, position: int) -> dict:
    previous_smi = state["previous_smi"]
    valid_cross = smi is not None and previous_smi is not None
    high_up = valid_cross and smi > SMI_THRESHOLD and previous_smi <= SMI_THRESHOLD
    high_down = valid_cross and smi < SMI_THRESHOLD and previous_smi >= SMI_THRESHOLD
    low_down = valid_cross and smi < -SMI_THRESHOLD and previous_smi >= -SMI_THRESHOLD
    low_up = valid_cross and smi > -SMI_THRESHOLD and previous_smi <= -SMI_THRESHOLD
    if high_up:
        state["tracking_high"], state["temp_high"], state["temp_high_bar"] = True, high, position
    if state["tracking_high"] and smi is not None and smi > SMI_THRESHOLD:
        if high > state["temp_high"]:
            state["temp_high"], state["temp_high_bar"] = high, position
    if state["tracking_high"] and high_down:
        state["last_swing_high"] = state["temp_high"]
        state["tracking_high"] = False
        state["temp_high"] = state["temp_high_bar"] = None
    if low_down:
        state["tracking_low"], state["temp_low"], state["temp_low_bar"] = True, low, position
    if state["tracking_low"] and smi is not None and smi < -SMI_THRESHOLD:
        if low < state["temp_low"]:
            state["temp_low"], state["temp_low_bar"] = low, position
    if state["tracking_low"] and low_up:
        state["tracking_low"] = False
        state["temp_low"] = state["temp_low_bar"] = None
    breakout = (
        state["last_swing_high"] is not None
        and state["previous_level"] is not None
        and state["previous_close"] is not None
        and close > state["last_swing_high"]
        and state["previous_close"] <= state["previous_level"]
    )
    result = {
        "smi": smi,
        "tracking_high": int(state["tracking_high"]),
        "tracking_low": int(state["tracking_low"]),
        "temp_high": state["temp_high"],
        "temp_high_bar": state["temp_high_bar"],
        "temp_low": state["temp_low"],
        "temp_low_bar": state["temp_low_bar"],
        "last_swing_high": state["last_swing_high"],
        "break_swing_high": int(breakout),
    }
    state["previous_smi"] = smi
    state["previous_close"] = close
    state["previous_level"] = state["last_swing_high"]
    return result


def calculate_incremental(
    rows: Iterable[dict], *, checkpoint: dict | None = None,
    requested_columns: Iterable[str] | None = None,
    calculated_at: datetime | None = None,
    state_only: bool = False,
    checkpoint_limit: int | None = None,
) -> tuple[list[dict], dict[str, dict], dict, list[dict]]:
    """Calculate a chronological suffix and return outputs, outcomes, final state and checkpoints."""
    # A checkpoint must be complete even when a retry writes only one dependency
    # bundle.  ``requested_columns`` controls the worker write surface; all state
    # groups still advance over every changed source observation.
    dependency_closure(requested_columns)
    selected = set(FEATURE_COLUMNS)
    state = validate_state(checkpoint) if checkpoint is not None else new_state()
    stamp = calculated_at or datetime.now(timezone.utc)
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("calculated_at must be timezone-aware")
    contract = library_contract()
    outcomes: dict[str, dict] = {}
    output: list[dict] = []
    checkpoints = deque(maxlen=checkpoint_limit) if checkpoint_limit else []
    previous_date = observation_date(state["last_date"]) if state["last_date"] else None

    def group(name: str, columns: tuple[str, ...], operation) -> None:
        if not selected.intersection(columns) or outcomes.get(name, {}).get("status") == "FAILED":
            return
        try:
            operation()
            outcomes.setdefault(name, {"status": "SUCCESS", "columns": list(columns)})
        except Exception as exc:
            outcomes[name] = {
                "status": "FAILED", "columns": list(columns),
                "error": f"{type(exc).__name__}: {exc}"[:1000],
            }

    for source_value in rows:
        source = dict(source_value)
        day = observation_date(source["date"])
        if previous_date is not None and day <= previous_date:
            raise ValueError("Incremental source rows must be strictly chronological after the checkpoint")
        previous_date = day
        ticker, timeframe, asset_type = source["ticker"], source["timeframe"], source["asset_type"]
        if not isinstance(ticker, str) or ticker != ticker.strip().upper() or not ticker:
            raise ValueError("Ticker must be nonempty, trimmed and upper-case")
        if timeframe != "Daily" or asset_type not in ("equity", "bonds"):
            raise ValueError("Incremental Feature04 source classification is invalid")
        result = dict.fromkeys(COLUMNS)
        result.update(
            ticker=ticker, trade_date=day, timeframe=timeframe, asset_type=asset_type,
            calculation_version=VERSION, calculated_at=stamp,
        )
        current_position = int(state["position"])
        state["position"] = current_position + 1
        state["last_date"] = day.isoformat()
        source_fingerprint = {
            key: source.get(key)
            for key in (
                "ticker", "date", "open", "high", "low", "close", "volume",
                "timeframe", "tradingview_symbol", "source", "asset_type",
            )
        }
        state["source_chain_sha256"] = hashlib.sha256(
            (
                state["source_chain_sha256"]
                + json.dumps(source_fingerprint, sort_keys=True, default=str, separators=(",", ":"))
            ).encode()
        ).hexdigest()

        if not state_only:
            group("source_close", DIRECT_COLUMNS, lambda: result.update(close=float(source["close"])))
        if not _valid(source):
            _reset_segment(state)
            if not state_only:
                output.append(result)
            checkpoints.append(deepcopy(state))
            continue

        open_, high, low, close = [float(source[key]) for key in ("open", "high", "low", "close")]
        state["segment_count"] += 1
        close_buffer = deque(state["close_buffer"], maxlen=MAX_CLOSE_BUFFER)
        close_buffer.append(close)
        state["close_buffer"] = list(close_buffer)
        pattern_buffer = deque(state["pattern_buffer"], maxlen=MAX_PATTERN_LOOKBACK + 1)
        pattern_buffer.append([open_, high, low, close])
        state["pattern_buffer"] = list(pattern_buffer)

        for period, column in ((20, "sma_20"), (50, "sma_50")):
            def sma_operation(p=period, col=column):
                value = _update_rolling_mean(state["sma"][str(p)], close, p)
                if not state_only:
                    result[col] = value
            group(column, (column,), sma_operation)

        ema_values: dict[int, float | None] = {}
        for period, column in ((12, "ema_12"), (26, "ema_26"), (50, "ema_50"), (200, "ema_200")):
            def ema_operation(p=period, col=column):
                value = _update_seeded_ema(state["ema"][str(p)], close, p)
                ema_values[p] = value
                if not state_only:
                    result[col] = value
            group(column, (column,), ema_operation)

        def rsi_operation():
            value = _update_rsi(state["rsi"], close)
            if not state_only:
                result["rsi_14"] = value
        group("rsi_14", ("rsi_14",), rsi_operation)

        def atr_operation():
            value = _update_atr(state["atr"], high, low, close)
            if not state_only:
                result["atr_14"] = value
        group("atr_14", ("atr_14",), atr_operation)

        def adx_operation():
            value = _update_adx(state["adx"], high, low, close)
            if not state_only:
                result["adx_14"] = value
        group("adx_14", ("adx_14",), adx_operation)

        def macd_operation():
            ema12 = ema_values.get(12, state["ema"]["12"]["value"])
            ema26 = ema_values.get(26, state["ema"]["26"]["value"])
            if ema12 is None or ema26 is None:
                return
            macd = ema12 - ema26
            signal = _update_seeded_ema(state["macd_signal"], macd, 9)
            if not state_only:
                result["macd"] = macd
                result["macd_signal"] = signal
                result["macd_histogram"] = macd - signal if signal is not None else None
        group("macd_bundle", MACD_COLUMNS, macd_operation)

        def bollinger_operation():
            values = _update_bbands(state["bbands"], close)
            if not state_only and values is not None:
                for column, value in zip(BOLLINGER_COLUMNS, values):
                    result[column] = value
        group("bollinger_bundle", BOLLINGER_COLUMNS, bollinger_operation)

        def inside_operation():
            previous = state["previous_valid"]
            if not state_only and previous is not None:
                result["inside_bar"] = int(high < previous["high"] and low > previous["low"])
        group("inside_bar", ("inside_bar",), inside_operation)

        def swing_operation():
            smi = _update_smi(state["smi"], high, low, close)
            swing_result = _update_swing(state["swing"], high, low, close, smi, current_position)
            if not state_only:
                result.update(swing_result)
        group("smi_swing_bundle", SWING_COLUMNS, swing_operation)

        for column, function_name in PATTERNS.items():
            def pattern_operation(col=column, fn_name=function_name):
                lookback = contract["patterns"][fn_name]["lookback"]
                if state_only or len(pattern_buffer) <= lookback:
                    return
                values = np.asarray(pattern_buffer, dtype=np.float64)
                calculated = getattr(talib, fn_name)(
                    values[:, 0], values[:, 1], values[:, 2], values[:, 3],
                    **contract["patterns"][fn_name]["parameters"],
                )
                result[col] = int(calculated[-1])
            group("pattern:" + column, (column,), pattern_operation)

        state["previous_valid"] = {"open": open_, "high": high, "low": low, "close": close}
        if not state_only:
            output.append(result)
        checkpoints.append(deepcopy(state))
    return output, outcomes, state, list(checkpoints)


def build_recent_checkpoints(rows: Iterable[dict], retain: int = 7) -> list[dict]:
    """Build recent state snapshots without writing or replacing feature output."""
    source = list(rows)
    if retain < 1:
        raise ValueError("retain must be positive")
    _, outcomes, _, checkpoints = calculate_incremental(
        source, state_only=True, checkpoint_limit=retain
    )
    failures = {name: value for name, value in outcomes.items() if value["status"] == "FAILED"}
    if failures:
        raise RuntimeError(f"Feature04 checkpoint bootstrap failed: {failures}")
    return checkpoints[-retain:]


def validate_incremental_availability(
    history: Iterable[dict], output: Iterable[dict], checkpoints: Iterable[dict],
    *, requested_columns: Iterable[str] | None = None,
) -> dict[str, dict]:
    """Reject NULLs that the post-row checkpoint says must be available."""
    selected = set(dependency_closure(requested_columns))
    failures: dict[str, dict] = {}
    contract = library_contract()
    source_rows, output_rows, states = list(history), list(output), list(checkpoints)
    if not (len(source_rows) == len(output_rows) == len(states)):
        raise ValueError("Incremental availability inputs must have equal lengths")

    def record(column: str, source: dict) -> None:
        info = failures.setdefault(column, {
            "status": "FAILED", "columns": [column], "missing_rows": 0,
            "first_ticker": source["ticker"], "first_date": str(source["date"]),
            "error": "Unexpected NULL where checkpoint state requires a value",
        })
        info["missing_rows"] += 1
        info["last_date"] = str(source["date"])

    for source, row, state in zip(source_rows, output_rows, states):
        required = {"close"}
        if _valid(source):
            segment_count = int(state["segment_count"])
            if segment_count >= 20:
                required.update(("sma_20", *BOLLINGER_COLUMNS))
            if segment_count >= 50:
                required.add("sma_50")
            for period in EMA_PERIODS:
                if state["ema"][str(period)]["value"] is not None:
                    required.add(f"ema_{period}")
            if state["rsi"]["average_gain"] is not None:
                required.add("rsi_14")
            if state["atr"]["value"] is not None:
                required.add("atr_14")
            if state["adx"]["value"] is not None:
                required.add("adx_14")
            if state["ema"]["12"]["value"] is not None and state["ema"]["26"]["value"] is not None:
                required.add("macd")
            if state["macd_signal"]["value"] is not None:
                required.update(("macd_signal", "macd_histogram"))
            if segment_count >= 2:
                required.add("inside_bar")
            for column, function_name in PATTERNS.items():
                if len(state["pattern_buffer"]) > contract["patterns"][function_name]["lookback"]:
                    required.add(column)
            required.update(("tracking_high", "tracking_low", "break_swing_high"))
            if state["smi"]["range_double"] not in (None, 0):
                required.add("smi")
            for column, state_key in (
                ("temp_high", "temp_high"), ("temp_high_bar", "temp_high_bar"),
                ("temp_low", "temp_low"), ("temp_low_bar", "temp_low_bar"),
                ("last_swing_high", "last_swing_high"),
            ):
                if state["swing"][state_key] is not None:
                    required.add(column)
        for column in selected.intersection(required):
            if row.get(column) is None:
                record(column, source)
    return failures
