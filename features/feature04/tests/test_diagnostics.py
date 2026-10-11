from datetime import date, timedelta
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine import (
    MACD_COLUMNS,
    SWING_COLUMNS,
    calculate,
    calculate_with_diagnostics,
    dependency_closure,
    validate_output_availability,
)


def bars(n=250):
    days = [date(2024, 1, 1) + timedelta(days=i) for i in range(n * 2)]
    days = [day for day in days if day.weekday() < 5][:n]
    return [
        dict(
            ticker='TEST', date=day, timeframe='Daily', asset_type='equity',
            tradingview_symbol='IDX:TEST', source='TradingView',
            open=100 + i, high=102 + i, low=98 + i, close=101 + i,
            volume=1000 + i,
        )
        for i, day in enumerate(days)
    ]


def test_full_diagnostic_path_is_byte_for_byte_equivalent():
    source = bars()
    expected = calculate(source)
    actual, outcomes = calculate_with_diagnostics(
        source, calculated_at=expected[0]['calculated_at']
    )
    assert actual == expected
    assert outcomes
    assert all(item['status'] == 'SUCCESS' for item in outcomes.values())


def test_dependency_closure_keeps_stateful_bundles_coherent():
    assert set(MACD_COLUMNS).issubset(dependency_closure(['ema_12']))
    assert set(SWING_COLUMNS) == set(dependency_closure(['break_swing_high']))
    assert dependency_closure(['adx_14']) == ('adx_14',)


def test_one_failed_group_keeps_other_groups_available():
    result, outcomes = calculate_with_diagnostics(
        bars(), requested_columns=['adx_14', 'break_swing_high'],
        fail_groups=['adx_14'],
    )
    assert outcomes['adx_14']['status'] == 'FAILED'
    assert outcomes['smi_swing_bundle']['status'] == 'SUCCESS'
    assert all(row['adx_14'] is None for row in result)
    assert any(row['break_swing_high'] is not None for row in result)


def test_warmup_and_conditional_swing_nulls_are_valid():
    source = bars(62)
    output = calculate(source)
    assert output[-1]['ema_200'] is None
    assert any(row['last_swing_high'] is None for row in output)
    assert validate_output_availability(source, output) == {}


def test_missing_historical_indicator_and_pattern_are_failures_even_if_latest_is_available():
    source = bars()
    output = calculate(source)
    output[220]['ema_200'] = None
    output[100]['cdl_doji'] = None
    failures = validate_output_availability(source, output)
    assert set(failures) == {'ema_200', 'cdl_doji'}
    assert failures['ema_200']['first_date'] == str(source[220]['date'])
    assert failures['ema_200']['missing_rows'] == 1
    assert output[-1]['ema_200'] is not None


def test_zero_range_smi_null_is_valid_but_missing_processed_flags_are_failures():
    source = bars(30)
    for row in source:
        row.update(open=100, high=100, low=100, close=100)
    output = calculate(source)
    assert all(row['smi'] is None for row in output)
    assert validate_output_availability(source, output) == {}
    output[15]['break_swing_high'] = None
    assert set(validate_output_availability(source, output)) == {'break_swing_high'}


def test_available_smi_and_active_temp_peak_cannot_be_null():
    source = bars()
    from math import sin
    for i, row in enumerate(source):
        price = 100 + 20 * sin(i / 8)
        row.update(open=price, high=price + 2, low=price - 2, close=price)
    output = calculate(source)
    index = next(i for i, row in enumerate(output) if row['temp_high'] is not None)
    output[index]['temp_high'] = None
    output[50]['smi'] = None
    assert set(validate_output_availability(source, output)) == {'temp_high', 'smi'}


def test_invalid_source_restarts_warmup_without_a_false_failure():
    source = bars()
    source[210]['close'] = None
    output = calculate(source)
    assert output[-1]['ema_200'] is None
    assert validate_output_availability(source, output) == {}
    output[240]['adx_14'] = None
    assert set(validate_output_availability(source, output)) == {'adx_14'}


def test_partial_retry_checks_only_its_selected_bundle():
    source = bars()
    output, _ = calculate_with_diagnostics(source, requested_columns=['adx_14'])
    assert output[-1]['ema_200'] is None
    assert validate_output_availability(source, output, requested_columns=['adx_14']) == {}
    output[100]['adx_14'] = None
    assert set(validate_output_availability(
        source, output, requested_columns=['adx_14']
    )) == {'adx_14'}
