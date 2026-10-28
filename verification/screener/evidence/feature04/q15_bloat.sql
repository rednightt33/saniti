select relname, relpages, reltuples::bigint, round(reltuples/nullif(relpages,0),2) tuples_per_page, pg_size_pretty(pg_relation_size(oid)) heap, pg_size_pretty(pg_indexes_size(oid)) idx from pg_class where relname in ('Feature_04_Technical_Indicator','Feature_04_Technical_Indicator_INDEX','Price_Stock_Indonesia_IDX','Feature_01_Stock_Daily');;
select extname, extversion from pg_extension order by 1;;
select ctid, ticker, trade_date from public."Feature_04_Technical_Indicator" where ticker='BBCA' and trade_date >= '2026-10-01' order by trade_date;;
select setting from pg_settings where name in ('shared_buffers','effective_cache_size','work_mem','max_parallel_workers_per_gather','random_page_cost','server_version')
