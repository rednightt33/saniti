with t as (select asset_type, ticker, count(*) n, min(trade_date) f, max(trade_date) l from public."Feature_04_Technical_Indicator" group by asset_type, ticker),
g as (select max(l) gl from t)
select asset_type, count(*) tickers, sum(n) rows_, min(f) min_first, max(l) max_last,
 count(*) filter (where f='2018-01-02') start_20180102, count(*) filter (where f<'2018-01-02') start_before_2018, count(*) filter (where f>'2018-01-02') start_after_20180102,
 count(*) filter (where l=(select gl from g)) end_on_latest, count(*) filter (where l<(select gl from g)) end_before_latest,
 min(n) min_rows, percentile_cont(0.5) within group (order by n) median_rows, max(n) max_rows,
 count(*) filter (where n<200) lt200_rows, count(*) filter (where n<750) lt750_rows
from t group by asset_type order by 1;;
with t as (select asset_type, ticker, count(*) n, min(trade_date) f, max(trade_date) l from public."Feature_04_Technical_Indicator" group by asset_type, ticker)
select asset_type, l last_date, count(*) tickers from t group by 1,2 order by 1,2 desc;;
with t as (select asset_type, ticker, min(trade_date) f from public."Feature_04_Technical_Indicator" group by asset_type, ticker)
select asset_type, extract(year from f)::int first_year, count(*) from t group by 1,2 order by 1,2
