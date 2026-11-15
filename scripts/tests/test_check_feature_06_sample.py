"""ERRORS M444: the independent Feature 06 check sums each window from its own values, so a window of near-zero values
after a large one gives the exact ratio the stored SQL (numeric) gives; the missing-value rules stay pandas'."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_feature_06_sample import wsum  # noqa: E402


@pytest.mark.parametrize("n, min_periods", [(5, None), (20, None), (20, 1), (60, None)])
def test_same_rules_as_a_rolling_sum(n, min_periods):
    rng = np.random.default_rng(7)
    values = rng.normal(0, 1e9, 400)
    values[rng.random(400) < 0.2] = np.nan
    series = pd.Series(values)
    expected = series.rolling(n, min_periods=n if min_periods is None else min_periods).sum()
    actual = wsum(series, n, min_periods)
    assert actual.isna().equals(expected.isna())
    assert np.allclose(actual.dropna(), expected.dropna(), rtol=1e-9, atol=1e-3)


def test_a_near_zero_window_after_a_large_value_is_exact():
    """GAGOES, Nego, 2022-04-01 (dev): the only non-zero daily foreign share of the 20-session window is -7.5e-10, after
    a -1 left the window and a long history of ordinary values; the strength is -100 on both dates, its momentum 0 (the
    stored SQL value). The running sum of pandas kept a remainder (dev: -2.96e-05; here -2.8e-06), beyond the check's
    absolute tolerance of 1e-7; the direct window sum is off by rounding only."""
    tail = [np.nan, 0.0, np.nan, 0.0, -1.0, 0.0, 0.0, 0.0, np.nan] + [0.0] * 5 + [-7.50682273132265794e-10] + \
        [0.0] * 3 + [np.nan, 0.0, 0.0, np.nan, 0.0, 0.0, 0.0]
    r = pd.Series(list(np.random.default_rng(0).uniform(-1, 1, 300)) + tail)
    strength = 100 * wsum(r, 20, 1) / wsum(r.abs(), 20, 1)
    assert abs(strength.iloc[-1] + 100) < 1e-12 and abs(strength.iloc[-6] + 100) < 1e-12
    assert abs(strength.iloc[-1] - strength.iloc[-6]) < 1e-12
    running = 100 * r.rolling(20, min_periods=1).sum() / r.abs().rolling(20, min_periods=1).sum()
    assert abs(running.iloc[-1] - running.iloc[-6]) > 1e-7  # the defect the direct sum removes
