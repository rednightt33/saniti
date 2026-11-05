"""Reference implementations used by the validator to recalculate supported methods independently.

They are written directly from the formulas in app/spec.py with NumPy (explicit sliding windows and
an explicit Wilder loop), deliberately not with TA-Lib or pandas rolling, so an analysis that used
those libraries is checked against a separate implementation. Every function takes one entity's
values in date order and returns an array of the same length; undefined values are NaN.
"""
from __future__ import annotations

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

# Where a calculation divides by (nearly) zero, the libraries in Saniti answer differently (ERRORS M349, measured
# 2026-11-05). REFERENCE is this module (NumPy). TA_LIB_0_8 is TA-Lib 0.8.1, the sandbox's library: an exact zero test,
# 0 for a Pearson correlation without variance and for a simple return over a zero base. TA_LIB_0_6 is TA-Lib 0.6.8
# (C 0.6.4), the library of Feature 04 and the Terminal kernels: in addition, |v| < 1e-14 counts as zero (TA_IS_ZERO,
# TA_IS_ZERO_OR_NEG), so RSI is 0 when average gain + average loss < 1e-14 and a standard deviation is 0 when the
# variance is < 1e-14. Everywhere else the three agree. The validator re-checks a failing output with the other two
# (validator.postflight), so an analysis that used any of them is not refused at those points.
CONVENTIONS = ("REFERENCE", "TA_LIB_0_8", "TA_LIB_0_6")
TA_LIB_EPSILON = 1e-14


def _empty(n: int) -> np.ndarray:
    return np.full(n, np.nan, dtype=float)


def sma(x: np.ndarray, window: int) -> np.ndarray:
    out = _empty(len(x))
    if len(x) >= window:
        out[window - 1:] = sliding_window_view(x, window).mean(axis=1)
    return out


def rolling_std(x: np.ndarray, window: int, ddof: int, convention: str = "REFERENCE") -> np.ndarray:
    out = _empty(len(x))
    if len(x) >= window and window > ddof:
        out[window - 1:] = sliding_window_view(x, window).std(axis=1, ddof=ddof)
    if convention == "TA_LIB_0_6":
        with np.errstate(invalid="ignore"):
            out[out * out < TA_LIB_EPSILON] = 0.0      # TA_IS_ZERO_OR_NEG(variance) -> 0
    return out


def rolling_zscore(x: np.ndarray, window: int, ddof: int, include_current: bool) -> np.ndarray:
    if include_current:
        mean, std = sma(x, window), rolling_std(x, window, ddof)
    else:
        mean, std = _empty(len(x)), _empty(len(x))
        if len(x) > window:
            mean[window:] = sma(x, window)[window - 1:-1]
            std[window:] = rolling_std(x, window, ddof)[window - 1:-1]
    with np.errstate(divide="ignore", invalid="ignore"):
        z = (x - mean) / std
    z[~np.isfinite(z)] = np.nan
    return z


def simple_return(x: np.ndarray, horizon: int, convention: str = "REFERENCE") -> np.ndarray:
    out = _empty(len(x))
    if len(x) > horizon:
        with np.errstate(divide="ignore", invalid="ignore"):
            out[horizon:] = x[horizon:] / x[:-horizon] - 1.0
    out[~np.isfinite(out)] = np.nan
    if convention != "REFERENCE" and len(x) > horizon:
        base_zero = np.zeros(len(x), dtype=bool)
        base_zero[horizon:] = (x[:-horizon] == 0) & np.isfinite(x[horizon:])
        out[base_zero] = 0.0                            # TA-Lib ROCP: 0 over a zero base
    return out


def log_return(x: np.ndarray, horizon: int) -> np.ndarray:
    out = _empty(len(x))
    if len(x) > horizon:
        with np.errstate(divide="ignore", invalid="ignore"):
            out[horizon:] = np.log(x[horizon:] / x[:-horizon])
    out[~np.isfinite(out)] = np.nan
    return out


def returns(x: np.ndarray, horizon: int, kind: str, as_percent: bool, convention: str = "REFERENCE") -> np.ndarray:
    out = log_return(x, horizon) if kind == "LOG" else simple_return(x, horizon, convention)
    return out * 100.0 if as_percent else out


def forward_returns(x: np.ndarray, horizon: int, kind: str, as_percent: bool, entry: str = "SIGNAL_CLOSE",
                    entry_prices: np.ndarray | None = None) -> np.ndarray:
    """Value at t: exit close x[t+horizon] over the entry price, x[t] (SIGNAL_CLOSE, CALC_010) or the next
    observation's open entry_prices[t+1] (NEXT_OPEN, CALC_011)."""
    out = _empty(len(x))
    n = len(x)
    if n <= horizon:
        return out
    base = entry_prices[1:n - horizon + 1] if entry == "NEXT_OPEN" else x[:n - horizon]
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = x[horizon:] / base
        values = np.log(np.where(ratio > 0, ratio, np.nan)) if kind == "LOG" else ratio - 1.0
    values[~np.isfinite(values)] = np.nan
    out[:n - horizon] = values
    return out * 100.0 if as_percent else out


def rsi_wilder(x: np.ndarray, period: int, convention: str = "REFERENCE") -> np.ndarray:
    """Wilder RSI seeded with the simple average of the first `period` changes of this series."""
    zero = TA_LIB_EPSILON if convention == "TA_LIB_0_6" else 0.0
    out = _empty(len(x))
    if len(x) <= period:
        return out
    change = np.diff(x)
    gains, losses = np.clip(change, 0, None), np.clip(-change, 0, None)
    avg_gain, avg_loss = gains[:period].mean(), losses[:period].mean()

    def value(gain: float, loss: float) -> float:
        total = gain + loss
        return 0.0 if total == 0 or abs(total) < zero else 100.0 * gain / total

    out[period] = value(avg_gain, avg_loss)
    for i in range(period, len(change)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        out[i + 1] = value(avg_gain, avg_loss)
    return out


def transform(x: np.ndarray, kind: str) -> np.ndarray:
    if kind == "SIMPLE_RETURN":
        return simple_return(x, 1)
    if kind == "LOG_RETURN":
        return log_return(x, 1)
    return x.astype(float)


def _ranks(values: np.ndarray) -> np.ndarray:
    """Average ranks along the last axis (ties share their mean rank)."""
    from scipy.stats import rankdata

    return rankdata(values, axis=-1)


def _pearson_rows(a: np.ndarray, b: np.ndarray, convention: str = "REFERENCE") -> np.ndarray:
    am = a - a.mean(axis=-1, keepdims=True)
    bm = b - b.mean(axis=-1, keepdims=True)
    denominator = (am * am).sum(axis=-1) * (bm * bm).sum(axis=-1)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = (am * bm).sum(axis=-1) / np.sqrt(denominator)
    r = np.where(np.isfinite(r), r, np.nan)
    if convention != "REFERENCE":                       # TA-Lib CORREL: TA_IS_ZERO_OR_NEG(denominator) -> 0
        r = np.where(denominator < TA_LIB_EPSILON, 0.0, r)
    return r


def rolling_correlation(x: np.ndarray, y: np.ndarray, window: int, method: str, kind: str,
                        convention: str = "REFERENCE") -> np.ndarray:
    fx, fy = transform(x, kind), transform(y, kind)
    out = _empty(len(x))
    if len(x) < window:
        return out
    wx, wy = sliding_window_view(fx, window), sliding_window_view(fy, window)
    valid = np.isfinite(wx).all(axis=1) & np.isfinite(wy).all(axis=1)
    if method == "SPEARMAN":
        wx, wy = _ranks(np.where(np.isfinite(wx), wx, 0)), _ranks(np.where(np.isfinite(wy), wy, 0))
    # TA-Lib CORREL is a Pearson correlation; a Spearman correlation keeps the reference answer
    r = _pearson_rows(np.where(np.isfinite(wx), wx, 0), np.where(np.isfinite(wy), wy, 0),
                      convention if method == "PEARSON" else "REFERENCE")
    out[window - 1:] = np.where(valid, r, np.nan)
    return out


def pair_correlation(a: np.ndarray, b: np.ndarray, method: str, min_overlap: int, convention: str = "REFERENCE") -> float:
    mask = np.isfinite(a) & np.isfinite(b)
    if mask.sum() < min_overlap:
        return float("nan")
    a, b = a[mask], b[mask]
    if method == "SPEARMAN":
        a, b = _ranks(a), _ranks(b)
    return float(_pearson_rows(a, b, convention if method == "PEARSON" else "REFERENCE"))


def compute(method: str, params: dict, x: np.ndarray, y: np.ndarray | None = None,
            convention: str = "REFERENCE") -> np.ndarray:
    """Reference values of a supported method for one entity series, under one of CONVENTIONS."""
    assert convention in CONVENTIONS, convention
    if method == "SMA":
        return sma(x, params["window"])
    if method == "ROLLING_STD":
        return rolling_std(x, params["window"], params["ddof"], convention)
    if method == "ROLLING_ZSCORE":
        return rolling_zscore(x, params["window"], params["ddof"], params["include_current"])
    if method == "RETURN":
        return returns(x, params["horizon"], params["kind"], params["as_percent"], convention)
    if method == "FORWARD_RETURN":
        return forward_returns(x, params["horizon"], params["kind"], params["as_percent"],
                               params.get("entry", "SIGNAL_CLOSE"), y)
    if method == "RSI":
        return rsi_wilder(x, params["period"], convention)
    if method == "ROLLING_CORRELATION":
        assert y is not None
        return rolling_correlation(x, y, params["window"], params["method"], params["transform"], convention)
    raise ValueError(f"no reference implementation for {method}")
