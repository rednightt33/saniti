select string_agg(column_name, ',' order by ordinal_position) from information_schema.columns where table_schema='public' and table_name='stockbit_corporate_action';;
with x as (select ticker, date, close, lag(close) over (partition by ticker order by date) pc from public."Price_Stock_Indonesia_IDX" where date >= '2024-01-01' and ticker <> 'IHSG')
select count(*) filter (where close/pc < 0.45) big_drop, count(*) filter (where close/pc > 2.2) big_jump from x where pc > 0
