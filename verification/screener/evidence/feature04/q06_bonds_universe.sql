select metric_type, "Timeframe", is_final, count(*) n, count(distinct ticker) tickers, min(date), max(date) from public."Price_Fixed_Income" group by 1,2,3 order by 1,2,3;;
with p as (select ticker, count(*) n, min(date) f, max(date) l from public."Price_Fixed_Income" where metric_type='price' and "Timeframe"='1D' and is_final group by ticker),
f as (select ticker, count(*) n, min(trade_date) f, max(trade_date) l from public."Feature_04_Technical_Indicator" where asset_type='bonds' group by ticker)
select coalesce(p.ticker,f.ticker) ticker, p.n pn, f.n fn, p.f pf, f.f ff, p.l pl, f.l fl from p full join f using (ticker) where p.ticker is null or f.ticker is null or p.n<>f.n or p.f<>f.f or p.l<>f.l order by 1;;
select metric_type, count(*), count(distinct ticker), string_agg(distinct country, ',') from public."Universe_Fixed_income" group by 1;;
select "Security Type", count(*) from public."IDX_Stock_Universe" group by 1;;
select column_name, data_type from information_schema.columns where table_schema='public' and table_name='IDX_Stock_Universe' order by ordinal_position
