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
)


def bars(n=250):
    days = [date(2024, 1, 1) + timedelta(days=i) for i in range(n * 2)]
    days = [day for day in days if day.weekday() < 5][:n]
    return [
        dict(
            ticker='TEST', date=day, timeframe='Daily',
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
