select action_type, count(*), min(ex_date), max(ex_date) from public.stockbit_corporate_action group by 1 order by 2 desc;;
with x as (select ticker, date, close, lag(close) over (partition by ticker order by date) pc, lag(date) over (partition by ticker order by date) pd from public."Price_Stock_Indonesia_IDX" where date >= '2024-01-01' and ticker <> 'IHSG')
select * from x where pc>0 and (close/pc < 0.45 or close/pc > 2.2);;
select ticker, ex_date, action_type, left(source_payload::text, 300) from public.stockbit_corporate_action where action_type ilike '%split%' and ex_date >= '2024-01-01' order by ex_date limit 15
