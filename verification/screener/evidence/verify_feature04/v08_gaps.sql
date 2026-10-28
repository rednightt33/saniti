with cal as (select distinct trade_date d from public."Feature_04_Technical_Indicator" where asset_type='equity'),
t as (select ticker, count(*) n, min(trade_date) f, max(trade_date) l from public."Feature_04_Technical_Indicator" where asset_type='equity' group by 1),
e as (select t.*, (select count(*) from cal where d between t.f and t.l) expected from t)
select (select count(*) from cal) cal_days, count(*) tickers, count(*) filter (where expected=n) no_gap, count(*) filter (where expected>n) with_gap,
 count(*) filter (where (expected-n) > 0.05*expected) gt5pct, count(*) filter (where (expected-n) > 0.5*expected) gt50pct, sum(expected-n) missing_total,
 count(*) filter (where expected<n) impossible from e;;
with cal as (select distinct trade_date d from public."Feature_04_Technical_Indicator" where asset_type='equity'),
t as (select ticker, count(*) n, min(trade_date) f, max(trade_date) l from public."Feature_04_Technical_Indicator" where asset_type='equity' group by 1),
e as (select t.*, (select count(*) from cal where d between t.f and t.l) expected from t)
select ticker, n, expected, f, l, round(100.0*(expected-n)/expected,1) pct_missing from e order by (expected-n)::numeric/expected desc limit 12
