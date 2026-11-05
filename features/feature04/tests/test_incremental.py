from datetime import datetime, timezone

import pytest

from engine import FEATURE_COLUMNS, calculate
from incremental import STATE_VERSION, calculate_incremental
from test_engine import bars


STAMP = datetime(2026, 10, 12, tzinfo=timezone.utc)


def assert_feature_rows_equal(actual, expected):
    assert len(actual) == len(expected)
    for left, right in zip(actual, expected):
        assert (left["ticker"], left["trade_date"], left["timeframe"], left["asset_type"]) == (
            right["ticker"], right["trade_date"], right["timeframe"], right["asset_type"]
        )
        for column in FEATURE_COLUMNS:
            if isinstance(right[column], float):
                assert left[column] == pytest.approx(right[column], rel=1e-12, abs=1e-10), (
                    column, left["trade_date"], left[column], right[column]
                )
            else:
                assert left[column] == right[column], (column, left["trade_date"])


def checkpoint_before(source, split):
    _, outcomes, state, _ = calculate_incremental(source[:split], calculated_at=STAMP)
    assert all(value["status"] == "SUCCESS" for value in outcomes.values())
    assert state["state_version"] == STATE_VERSION
    return state


@pytest.mark.parametrize("changed_offset", range(1, 6))
def test_last_five_session_correction_matches_full_reference(changed_offset):
    source = bars(260)
    split = len(source) - changed_offset
    checkpoint = checkpoint_before(source, split)
    source[split].update(
        open=source[split]["open"] + 0.5,
        high=source[split]["high"] + 1.0,
        low=source[split]["low"] - 0.5,
        close=source[split]["close"] + 0.25,
    )
    expected = calculate(source, calculated_at=STAMP)[split:]
    actual, outcomes, _, checkpoints = calculate_incremental(
        source[split:], checkpoint=checkpoint, calculated_at=STAMP
    )
    assert all(value["status"] == "SUCCESS" for value in outcomes.values())
    assert len(checkpoints) == changed_offset
    assert_feature_rows_equal(actual, expected)


def test_incremental_short_history_warmup_and_bond_null_volume():
    source = bars(40, ticker="ID10Y")
    for row in source:
        row.update(asset_type="bonds", tradingview_symbol="TVC:ID10", volume=None)
    expected = calculate(source, calculated_at=STAMP)
    actual, outcomes, _, _ = calculate_incremental(source, calculated_at=STAMP)
    assert all(value["status"] == "SUCCESS" for value in outcomes.values())
    assert_feature_rows_equal(actual, expected)


def test_incremental_invalid_row_resets_warmup_and_swing_state():
    source = bars(100)
    source[70]["volume"] = -1
    expected = calculate(source, calculated_at=STAMP)
    actual, outcomes, _, _ = calculate_incremental(source, calculated_at=STAMP)
    assert all(value["status"] == "SUCCESS" for value in outcomes.values())
    assert_feature_rows_equal(actual, expected)


def test_checkpoint_rejects_wrong_versions_and_non_chronological_suffix():
    source = bars(10)
    checkpoint = checkpoint_before(source, 5)
    incompatible = dict(checkpoint, state_version="wrong")
    with pytest.raises(ValueError, match="state version"):
        calculate_incremental(source[5:], checkpoint=incompatible)
    with pytest.raises(ValueError, match="strictly chronological"):
        calculate_incremental(source[4:], checkpoint=checkpoint)


def test_candlestick_flags_do_not_depend_on_an_unrelated_old_prefix():
    source = bars(260)
    expected = calculate(source, calculated_at=STAMP)
    actual, outcomes, _, _ = calculate_incremental(source, calculated_at=STAMP)
    assert all(value["status"] == "SUCCESS" for value in outcomes.values())
    for left, right in zip(actual, expected):
        for column in (value for value in FEATURE_COLUMNS if value.startswith("cdl_")):
            assert left[column] == right[column]


def test_index_without_volume_matches_observed_zero_price_only_reference():
    source = bars(260, ticker="IHSG")
    for row in source:
        row.update(security_type="index", universe_tradingview_symbol="IDX:COMPOSITE",
                   tradingview_symbol="IDX:COMPOSITE", volume=None)
    reference = [dict(row, volume=0) for row in source]
    expected = calculate(reference, calculated_at=STAMP)
    actual = calculate(source, calculated_at=STAMP)
    assert_feature_rows_equal(actual, expected)
    checkpoint = checkpoint_before(source, 255)
    suffix, outcomes, _, _ = calculate_incremental(source[255:], checkpoint=checkpoint, calculated_at=STAMP)
    assert all(value["status"] == "SUCCESS" for value in outcomes.values())
    assert_feature_rows_equal(suffix, expected[255:])
    assert all(row["volume"] is None for row in source)


def test_equity_missing_volume_still_invalid_and_index_mapping_required():
    source = bars(40)
    for row in source:
        row["volume"] = None
    assert all(row["sma_20"] is None for row in calculate(source))
    for row in source:
        row.update(security_type="index", tradingview_symbol="IDX:COMPOSITE")
    with pytest.raises(ValueError, match="universe mapping"):
        calculate(source)


def _rows(highs, lows, closes):
    from datetime import date, timedelta
    day, rows = date(2020, 1, 1), []
    for high, low, close in zip(highs, lows, closes):
        while day.weekday() > 4:
            day += timedelta(days=1)
        rows.append(dict(ticker="FLAT", date=day, timeframe="Daily", asset_type="equity",
                         tradingview_symbol="IDX:FLAT", open=float(close), high=float(high), low=float(low),
                         close=float(close), volume=0))
        day += timedelta(days=1)
    return rows


def test_long_flat_stretch_matches_talib_zero_tests():
    """ERRORS M349: after ~460 sessions without a trade avg_gain + avg_loss < 1e-14 and TA-Lib's RSI is 0 (TA_IS_ZERO);
    the chain kept the last ratio (AKKU rsi_14 2022-02-18: 45.81 against 0.0). Trading resumes afterwards."""
    trend = bars(300)
    last = trend[-1]["close"]
    closes = [row["close"] for row in trend] + [last] * 700 + [row["close"] for row in bars(80)]
    highs = [row["high"] for row in trend] + [last] * 700 + [row["high"] for row in bars(80)]
    lows = [row["low"] for row in trend] + [last] * 700 + [row["low"] for row in bars(80)]
    source = _rows(highs, lows, closes)
    expected = calculate(source, calculated_at=STAMP)
    assert any(row["rsi_14"] == 0.0 for row in expected[300:1000])
    actual, outcomes, _, _ = calculate_incremental(source, calculated_at=STAMP)
    assert all(value["status"] == "SUCCESS" for value in outcomes.values())
    assert_feature_rows_equal(actual, expected)


def test_tiny_scale_matches_talib_adx_and_bbands_zero_tests():
    """The same TA-Lib zero tests in ADX (no DX, ADX held) and the BBANDS deviation, on values below 1e-14."""
    base = bars(120)
    source = _rows([row["high"] * 1e-16 for row in base], [row["low"] * 1e-16 for row in base],
                   [row["close"] * 1e-16 for row in base])
    expected = calculate(source, calculated_at=STAMP)
    assert expected[-1]["adx_14"] == 0.0 and expected[-1]["bb_upper_20"] == expected[-1]["bb_middle_20"]
    actual, _, _, _ = calculate_incremental(source, calculated_at=STAMP)
    assert_feature_rows_equal(actual, expected)
