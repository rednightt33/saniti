explain select asset_type, ticker, count(*) from public."Feature_04_Technical_Indicator" group by 1,2;;
with t as (select asset_type, ticker, count(*) n, min(trade_date) f, max(trade_date) l from public."Feature_04_Technical_Indicator" group by 1,2)
select asset_type, count(*), sum(n), min(f), max(l), count(*) filter (where f='2018-01-02') s18, count(*) filter (where f>'2018-01-02') later, percentile_cont(0.5) within group (order by n) med, min(n), max(n), count(*) filter (where n<200) lt200, count(*) filter (where n<750) lt750 from t group by 1;;
with p as (select ticker, count(*) n, min(date) f, max(date) l from public."Price_Stock_Indonesia_IDX" where is_final and timeframe='Daily' group by ticker),
f as (select ticker, count(*) n, min(trade_date) f, max(trade_date) l from public."Feature_04_Technical_Indicator" where asset_type='equity' group by ticker)
select coalesce(p.ticker,f.ticker), p.n, f.n, p.f, f.f, p.l, f.l from p full join f using (ticker) where p.ticker is null or f.ticker is null or p.n<>f.n or p.f<>f.f or p.l<>f.l;;
select timeframe, is_final, count(*), count(distinct ticker) from public."Price_Stock_Indonesia_IDX" group by 1,2;;
with t as (select ticker, max(trade_date) l from public."Feature_04_Technical_Indicator" where asset_type='equity' group by 1) select ticker, l from t where l < '2026-10-27' order by l
