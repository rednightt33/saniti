from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engine import calculate,COLUMNS,FEATURE_COLUMNS
from backfill import bulk_upsert,digest,verify_values
from test_engine import bars

def test_adx_wilder_reference_and_warmup():
    source=bars(250);out=calculate(source);n=14
    plus=[];minus=[];tr=[]
    for previous,current in zip(source,source[1:]):
        up=current['high']-previous['high'];down=previous['low']-current['low']
        plus.append(up if up>0 and up>down else 0)
        minus.append(down if down>0 and down>up else 0)
        tr.append(max(current['high']-current['low'],abs(current['high']-previous['close']),abs(current['low']-previous['close'])))
    p=sum(plus[:n-1]);m=sum(minus[:n-1]);t=sum(tr[:n-1]);dxs=[];adx=None
    assert all(r['adx_14'] is None for r in out[:27])
    for i in range(n,len(source)):
        p=p-p/n+plus[i-1];m=m-m/n+minus[i-1];t=t-t/n+tr[i-1]
        positive=100*p/t if t else 0;negative=100*m/t if t else 0
        dx=100*abs(positive-negative)/(positive+negative) if positive+negative else 0
        dxs.append(dx)
        if i==27:adx=sum(dxs)/14
        elif i>27:adx=(adx*13+dx)/14
        if adx is not None:assert out[i]['adx_14']==pytest.approx(adx,rel=1e-12)
    flat=calculate(bars(40,closes=[100]*40))
    assert flat[27]['adx_14']==0

def test_inside_bar_current_candle_strict_edges_and_reset():
    source=bars(6)
    for r in source:r.update(open=100,close=100,high=110,low=90)
    source[1].update(high=109,low=91)
    source[2].update(high=109,low=92)  # equal high is excluded
    source[3].update(high=108,low=92)  # equal low is excluded
    source[4]['volume']=-1
    out=calculate(source)
    assert [r['inside_bar'] for r in out]==[None,1,0,0,None,None]
    assert all(out[4][c] is None for c in FEATURE_COLUMNS if c != 'close')
    assert out[4]['close'] == source[4]['close']

def test_inside_bar_uses_original_decimal_boundaries():
    source=bars(2)
    for r in source:r.update(open=Decimal('100'),close=Decimal('100'))
    source[0].update(high=Decimal('101.000000000000000001'),low=Decimal('98.999999999999999999'))
    source[1].update(high=Decimal('101'),low=Decimal('99'))
    assert calculate(source)[1]['inside_bar']==1

def test_all_extensions_causal_and_partitioned():
    stamp=datetime(2026,1,1,tzinfo=timezone.utc)
    source=bars(250);full=calculate(source,calculated_at=stamp)
    assert calculate(source[:200],calculated_at=stamp)==full[:200]
    mix=calculate([*bars(20,ticker='MORE'),*reversed(source)],calculated_at=stamp)
    assert [r for r in mix if r['ticker']=='TEST']==full
    assert len(COLUMNS)==len(set(COLUMNS))==57

def test_resume_hash_excludes_only_calculation_timestamp():
    source=bars(40);first=calculate(source)
    second=calculate(source,calculated_at=datetime(2026,1,1,tzinfo=timezone.utc))
    assert digest(first,output=True)==digest(second,output=True)
    assert verify_values(first,second)==digest(first,output=True)
    second[-1]['adx_14']+=1
    with pytest.raises(ValueError,match='differs'):verify_values(first,second)

def test_serial_bulk_guards_before_database_use():
    with pytest.raises(ValueError):bulk_upsert(None,[])
    with pytest.raises(ValueError):bulk_upsert(None,[{}]*5001)
    with pytest.raises(ValueError):bulk_upsert(None,[{'ticker':'BBCA'},{'ticker':'GOTO'}])
