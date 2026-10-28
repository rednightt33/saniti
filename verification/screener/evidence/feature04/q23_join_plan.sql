explain (analyze, buffers) with d as (select max(trade_date) d from public."Feature_04_Technical_Indicator" where asset_type='equity')
select f.ticker, f.close, f.rsi_14, f.sma_50, p.volume, p.close*p.volume as value_idr
from public."Feature_04_Technical_Indicator" f join d on f.trade_date=d.d
join public."Price_Stock_Indonesia_IDX" p on p.ticker=f.ticker and p.date=f.trade_date
where f.asset_type='equity' and f.rsi_14 < 30 and f.close > f.sma_50
