with cal as (select distinct trade_date d from public."Feature_04_Technical_Indicator" where asset_type='equity'),
calx as (select d, row_number() over (order by d) rn from cal),
t as (select ticker, count(*) n, min(trade_date) f, max(trade_date) l from public."Feature_04_Technical_Indicator" where asset_type='equity' group by ticker),
e as (select t.*, (select rn from calx where d=t.l)-(select rn from calx where d=t.f)+1 expected from t)
select (select count(*) from cal) calendar_dates, count(*) tickers,
 count(*) filter (where n=expected) no_gap, count(*) filter (where n<expected) with_gaps,
 count(*) filter (where n < 0.95*expected) gap_gt5pct, count(*) filter (where n < 0.5*expected) gap_gt50pct,
 sum(expected-n) missing_ticker_sessions
from e
