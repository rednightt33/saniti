select timeframe, is_final, count(*) n, count(distinct ticker) tickers, min(date) mn, max(date) mx from public."Price_Stock_Indonesia_IDX" group by 1,2;;
with p as (select ticker, count(*) n, min(date) f, max(date) l from public."Price_Stock_Indonesia_IDX" where is_final and timeframe='Daily' group by ticker),
f as (select ticker, count(*) n, min(trade_date) f, max(trade_date) l from public."Feature_04_Technical_Indicator" where asset_type='equity' group by ticker),
u as (select "Ticker" ticker, "Security Type" st from public."IDX_Stock_Universe")
select
 count(*) filter (where p.ticker is not null) price_tickers,
 count(*) filter (where f.ticker is not null) f04_tickers,
 count(*) filter (where p.ticker is not null and f.ticker is null) price_only,
 count(*) filter (where p.ticker is null and f.ticker is not null) f04_only,
 count(*) filter (where p.ticker is not null and f.ticker is not null and (p.n<>f.n or p.f<>f.f or p.l<>f.l)) mismatched,
 count(*) filter (where p.ticker is not null and f.ticker is not null and p.n=f.n and p.f=f.f and p.l=f.l) matched
from p full join f using (ticker);;
with p as (select ticker, count(*) n, min(date) f, max(date) l from public."Price_Stock_Indonesia_IDX" where is_final and timeframe='Daily' group by ticker),
f as (select ticker, count(*) n, min(trade_date) f, max(trade_date) l from public."Feature_04_Technical_Indicator" where asset_type='equity' group by ticker)
select coalesce(p.ticker,f.ticker) ticker, p.n pn, f.n fn, p.f pf, f.f ff, p.l pl, f.l fl,
 (select "Security Type" from public."IDX_Stock_Universe" u where u."Ticker"=coalesce(p.ticker,f.ticker)) sec_type
from p full join f using (ticker) where p.ticker is null or f.ticker is null or p.n<>f.n or p.f<>f.f or p.l<>f.l order by 1
