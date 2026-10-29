select date, count(*), string_agg(distinct ticker, ',') from public."Price_Stock_Indonesia_IDX" where date between '2026-09-15' and '2026-09-22' group by 1 order by 1;;
select "Date", count(*) from public."IDX_Broker_Summary" where "Date" between '2026-09-15' and '2026-09-22' group by 1 order by 1;;
select table_name from information_schema.tables where table_schema='public' and (table_name ilike '%holiday%' or table_name ilike '%calendar%' or table_name ilike '%schedule%' or table_name ilike 'monitoring%') order by 1
