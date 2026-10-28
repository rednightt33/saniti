with cal as (select trade_date d from public."Feature_04_Technical_Indicator_INDEX"),
t as (select ticker, count(*) n, min(trade_date) f, max(trade_date) l from public."Feature_04_Technical_Indicator" where asset_type='equity' group by 1),
e as (select t.*, (select count(*) from cal where d between t.f and t.l) expected from t)
select (select count(*) from cal) cal_days, count(*) tickers, count(*) filter (where expected=n) no_gap, count(*) filter (where expected>n) with_gap,
 count(*) filter (where (expected-n) > 0.05*expected) gt5pct, count(*) filter (where (expected-n) > 0.5*expected) gt50pct, sum(expected-n) missing_total, count(*) filter (where f<='2026-09-16' and l>='2026-09-21') span_m238 from e
