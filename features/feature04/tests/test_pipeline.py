from datetime import date
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pipeline import refresh,upsert


@pytest.mark.parametrize('tickers,start,end',[
    ([],date(2026,1,1),date(2026,1,2)),
    (['BBCA','BBCA'],date(2026,1,1),date(2026,1,2)),
    (['BBCA'],date(2026,1,2),date(2026,1,1)),
    (['BBCA'],date(2024,1,1),date(2026,1,1)),
])
def test_bulk_or_ambiguous_refresh_refused_before_database_use(tickers,start,end):
    with pytest.raises(ValueError):refresh(None,tickers,start,end,write=True)


def test_bulk_write_refused_before_database_use():
    with pytest.raises(ValueError):upsert(None,[{}]*5001)
