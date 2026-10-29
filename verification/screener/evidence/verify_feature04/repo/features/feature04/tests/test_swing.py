from datetime import datetime, timezone

import pytest

from engine import calculate
from swing import calculate_swing, replay_swing, SWING_COLUMNS
from test_engine import bars


def test_smi_first_input_seed_and_independent_weighted_sum_reference():
    source = bars(80)
    high, low, close = [[r[k] for r in source] for k in ('high', 'low', 'close')]
    midpoint = [(max(high[max(0,i-13):i+1])+min(low[max(0,i-13):i+1]))/2 for i in range(len(source))]
    ranges = [max(high[max(0,i-13):i+1])-min(low[max(0,i-13):i+1]) for i in range(len(source))]
    def weighted_ema(values):
        # Closed-form first-input seed, independent of the recursive implementation.
        return [values[0]*(2/3)**i + sum((1/3)*(2/3)**(i-j)*values[j] for j in range(1,i+1)) for i in range(len(values))]
    numerator = weighted_ema(weighted_ema([c-m for c,m in zip(close,midpoint)]))
    denominator = weighted_ema(weighted_ema(ranges))
    actual = calculate_swing(high, low, close)
    assert [r['smi'] for r in actual] == pytest.approx([200*n/d for n,d in zip(numerator,denominator)],abs=1e-10)
    assert actual[0]['smi'] == 0  # available immediately; no SMA warmup
    assert calculate_swing([110],[90],[110])[0]['smi'] == 100
    flat = calculate_swing([100]*3,[100]*3,[100]*3)
    assert all(r['smi'] is None and r['break_swing_high']==0 for r in flat)


def test_confirmation_current_close_not_wick_repeat_and_no_smi_filter():
    high=[100,110,120,130,140,150,110,160]
    low=[90]*8
    close=[95,100,110,115,119,121,110,125]
    smi=[0,50,60,30,20,10,0,-10]
    out=replay_swing(high,low,close,smi)
    assert out[1]['tracking_high']==1 and out[1]['temp_high_bar']==1
    assert out[2]['temp_high']==120
    assert out[3]['last_swing_high']==120  # high=130 on confirming bar is excluded
    assert out[3]['tracking_high']==0 and out[3]['temp_high'] is None
    assert [r['break_swing_high'] for r in out]==[0,0,0,0,0,1,0,1]
    assert out[-1]['last_swing_high']==120  # no one-shot clearing


def test_equal_threshold_recross_resets_peak_and_equal_high_keeps_first_bar():
    out=replay_swing([100,150,150,140,120,130],[90]*6,[95]*6,[0,50,60,40,50,30])
    assert out[2]['temp_high_bar']==1  # tied high does not move index
    assert out[3]['tracking_high']==1 and out[3]['temp_high']==150
    assert out[4]['temp_high']==120 and out[4]['temp_high_bar']==4
    assert out[5]['last_swing_high']==120  # recross discards former 150 peak


def test_dynamic_level_crossover_and_first_confirmation_prior_na():
    out=replay_swing([100,200,210,160,150,180],[80]*6,
                     [90,190,205,140,140,170],[0,50,30,50,60,30])
    assert out[2]['last_swing_high']==200 and out[2]['break_swing_high']==0
    # Use a prior close 165 in the explicit lowered-level path below; replacing
    # yesterday's level with today's new 160 level would incorrectly miss it.
    second=replay_swing([100,200,210,160,180,190],[80]*6,
                        [90,190,205,140,175,185],[0,50,30,50,60,30])
    assert second[5]['last_swing_high']==180
    assert second[5]['break_swing_high']==1
    changed=replay_swing([100,200,210,160,170,190],[80]*6,
                         [90,190,205,140,165,185],[0,50,30,50,40,30])
    assert changed[5]['last_swing_high']==160 and changed[5]['break_swing_high']==1


def test_low_state_cleared_on_confirmation_and_zero_based_offset():
    out=replay_swing([110]*5,[100,90,80,80,70],[105,95,85,85,90],
                     [0,-50,-60,-70,-30],bar_offset=20)
    assert out[2]['temp_low']==80 and out[2]['temp_low_bar']==22
    assert out[3]['temp_low_bar']==22
    assert out[4]['tracking_low']==0 and out[4]['temp_low'] is None
    assert out[4]['last_swing_high'] is None


def test_prefix_partition_and_invalid_reset_no_backdated_values():
    stamp=datetime(2026,1,1,tzinfo=timezone.utc)
    source=bars(100)
    full=calculate(source,calculated_at=stamp)
    assert calculate(source[:65],calculated_at=stamp)==full[:65]
    mixed=calculate([*bars(40,ticker='MORE'),*reversed(source)],calculated_at=stamp)
    assert [r for r in mixed if r['ticker']=='TEST']==full
    source[60]['volume']=-1
    reset=calculate(source,calculated_at=stamp)
    assert all(reset[60][k] is None for k in SWING_COLUMNS)
    assert reset[61]['tracking_high']==0 and reset[61]['last_swing_high'] is None
    assert reset[61]['smi']==pytest.approx(0)
    assert all(type(r['break_swing_high']) is int for r in reset if r['break_swing_high'] is not None)
