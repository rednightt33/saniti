from datetime import date, datetime, timedelta, timezone
import sys
from pathlib import Path
import numpy as np
import pytest
import talib
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import calculate, COLUMNS, FEATURE_COLUMNS, PATTERNS, library_contract


def bars(n=100, ticker='TEST', closes=None):
    days = [date(2024, 1, 1) + timedelta(days=i) for i in range(n*2)]
    days = [d for d in days if d.weekday() < 5][:n]
    prices = closes if closes is not None else [100 + i + 3*np.sin(i) for i in range(n)]
    return [dict(ticker=ticker,date=d,timeframe='Daily',asset_type='equity',tradingview_symbol='IDX:'+ticker,
                 open=float(c),high=float(c)+2,low=float(c)-2,close=float(c),volume=0)
            for d,c in zip(days,prices)]


def test_sma_bb_first_valid_and_population_variance():
    source=bars();result=calculate(source);close=[r['close'] for r in source]
    assert all(r['sma_20'] is None for r in result[:19])
    assert all(r['sma_50'] is None for r in result[:49])
    for i,r in enumerate(result):
        if i>=19:
            mean=sum(close[i-19:i+1])/20
            variance=sum((x-mean)**2 for x in close[i-19:i+1])/20
            assert r['sma_20']==pytest.approx(mean)
            assert r['bb_middle_20']==pytest.approx(mean)
            assert r['bb_upper_20']==pytest.approx(mean+2*variance**0.5)
            assert r['bb_lower_20']==pytest.approx(mean-2*variance**0.5)
        if i>=49:assert r['sma_50']==pytest.approx(sum(close[i-49:i+1])/50)


def test_ema_seed_recurrence_macd_composition_and_signal():
    source=bars(250);result=calculate(source)
    for length in (12,26,50,200):
        key=f'ema_{length}';seed=sum(r['close'] for r in source[:length])/length
        assert all(r[key] is None for r in result[:length-1])
        for i in range(length-1,len(source)):
            if i>=length:seed+=(source[i]['close']-seed)*2/(length+1)
            assert result[i][key]==pytest.approx(seed)
    assert all(r['macd'] is None for r in result[:25])
    assert all(r['macd_signal'] is None for r in result[:33])
    signal=sum(r['macd'] for r in result[25:34])/9
    for i in range(25,len(source)):
        r=result[i];assert r['macd']==pytest.approx(r['ema_12']-r['ema_26'])
        if i>=33:
            if i>33:signal+=(r['macd']-signal)*0.2
            assert r['macd_signal']==pytest.approx(signal)
            assert r['macd_histogram']==pytest.approx(r['macd']-signal)


def test_wilder_rsi_atr_independent_reference():
    source=bars();out=calculate(source)
    changes=np.diff([r['close'] for r in source]);gain=sum(max(x,0) for x in changes[:14])/14;loss=sum(max(-x,0) for x in changes[:14])/14
    trs=[max(r['high']-r['low'],abs(r['high']-prev['close']),abs(r['low']-prev['close'])) for prev,r in zip(source,source[1:])]
    atr=sum(trs[:14])/14
    assert all(r['rsi_14'] is None and r['atr_14'] is None for r in out[:14])
    for i in range(14,len(source)):
        if i>14:
            gain=(gain*13+max(changes[i-1],0))/14;loss=(loss*13+max(-changes[i-1],0))/14;atr=(atr*13+trs[i-1])/14
        assert out[i]['rsi_14']==pytest.approx(100*gain/(gain+loss))
        assert out[i]['atr_14']==pytest.approx(atr)


def test_all_patterns_native_signed_zero_and_unavailable_outputs():
    source=bars(100);source[70].update(open=200,high=202,low=190,close=191);source[71].update(open=190,high=205,low=188,close=204)
    source[72].update(open=205,high=207,low=187,close=188)
    out=calculate(source);contract=library_contract();arrays=[np.array([r[k] for r in source]) for k in ('open','high','low','close')]
    for key,name in PATTERNS.items():
        native=getattr(talib,name)(*arrays,**contract['patterns'][name]['parameters']);lookback=contract['patterns'][name]['lookback']
        assert all(r[key] is None for r in out[:lookback])
        assert [r[key] for r in out[lookback:]]==native[lookback:].tolist()
        assert all(type(r[key]) is int for r in out[lookback:])
    assert out[71]['cdl_engulfing']>0 and out[72]['cdl_engulfing']<0
    assert any(r['cdl_doji']==0 for r in out[20:])
    assert any(sum(r[k]!=0 for k in PATTERNS if r[k] is not None)>1 for r in out)


def test_causal_prefix_sorted_partition_and_missing_reset():
    source=bars(100);stamp=datetime(2026,1,1,tzinfo=timezone.utc)
    full=calculate(source,calculated_at=stamp)
    assert calculate(source[:60],calculated_at=stamp)==full[:60]
    assert calculate(reversed(source),calculated_at=stamp)==full
    other=bars(100,ticker='MORE');mixed=calculate([*source,*other],calculated_at=stamp)
    assert [r for r in mixed if r['ticker']=='TEST']==full
    source[60]['close']=None;invalid=calculate(source)
    assert all(invalid[60][k] is None for k in FEATURE_COLUMNS)
    assert invalid[79]['sma_20'] is None and invalid[80]['sma_20'] is not None
    assert invalid[61]['cdl_engulfing'] is None
    assert len(invalid)==100


@pytest.mark.parametrize('field,value',[('close',float('nan')),('high',50),('volume',-1)])
def test_invalid_bar_is_null_not_zero(field,value):
    source=bars();source[70][field]=value;out=calculate(source)
    assert all(out[70][k] is None for k in FEATURE_COLUMNS)


def test_short_history_and_identity_guards():
    out=calculate(bars(3));assert len(out[0])==56
    assert all(r['sma_50'] is None for r in out)
    source=bars()
    with pytest.raises(ValueError,match='Duplicate'):calculate([*source,source[0]])
    source[0]['timeframe']='1H'
    with pytest.raises(ValueError,match='Daily'):calculate(source)
    with pytest.raises(ValueError,match='timezone'):calculate(bars(),calculated_at=datetime(2026,1,1))


def test_history_correction_cannot_change_earlier_features():
    source=bars();stamp=datetime(2026,1,1,tzinfo=timezone.utc);old=calculate(source,calculated_at=stamp)
    source[60].update(open=180,high=182,low=178,close=180);new=calculate(source,calculated_at=stamp)
    assert old[:60]==new[:60]
    assert old[90]['ema_26']!=new[90]['ema_26']


def test_bond_ohlc_allows_missing_volume_and_keeps_asset_partition():
    source = bars(60, ticker='ID10Y')
    for row in source:
        row.update(asset_type='bonds', tradingview_symbol='TVC:ID10', volume=None)
    result = calculate(source)
    assert len(result) == 60
    assert {row['asset_type'] for row in result} == {'bonds'}
    assert result[19]['sma_20'] is not None
    assert result[27]['adx_14'] is not None


def test_asset_type_is_required_and_equity_still_requires_volume():
    missing_type = bars(2)
    del missing_type[0]['asset_type']
    with pytest.raises(ValueError, match='asset_type'):
        calculate(missing_type)
    missing_volume = bars(2)
    missing_volume[0]['volume'] = None
    output = calculate(missing_volume)
    assert all(output[0][column] is None for column in FEATURE_COLUMNS)
    assert output[1]['inside_bar'] is None
