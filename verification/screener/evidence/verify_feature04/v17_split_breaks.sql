with s as (select distinct ticker, ex_date::date ex, action_type, (source_payload->>'stocksplit_factor') factor from public.stockbit_corporate_action where action_type in ('STOCK_SPLIT','REVERSE_SPLIT','BONUS_SHARE','RIGHT_ISSUE') and ex_date between '2025-01-01' and '2026-10-27')
select s.ticker, s.ex, s.action_type, s.factor,
 (select close from public."Price_Stock_Indonesia_IDX" p where p.ticker=s.ticker and p.date<s.ex order by date desc limit 1) prev_close,
 (select close from public."Price_Stock_Indonesia_IDX" p where p.ticker=s.ticker and p.date>=s.ex order by date limit 1) ex_close,
 (select ingestion_time from public."Price_Stock_Indonesia_IDX" p where p.ticker=s.ticker and p.date<s.ex order by date desc limit 1) prev_ingested
from s order by s.ex
