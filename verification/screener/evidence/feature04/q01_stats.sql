select now() as db_now, current_user, current_setting('default_transaction_read_only') ro, current_setting('statement_timeout') st;;
select c.relname, c.reltuples::bigint, pg_size_pretty(pg_total_relation_size(c.oid)) total, pg_size_pretty(pg_relation_size(c.oid)) heap, s.n_live_tup, s.n_dead_tup, s.last_analyze, s.last_autoanalyze, s.last_autovacuum
from pg_class c join pg_namespace n on n.oid=c.relnamespace left join pg_stat_user_tables s on s.relid=c.oid
where n.nspname='public' and (c.relname ilike 'feature04%' or c.relname ilike 'feature_04%' or c.relname ilike 'monitoring_feature04%' or c.relname in ('Price_Stock_Indonesia_IDX','Price_Fixed_Income','IDX_Stock_Universe','Universe_Fixed_income','Equity_Market_Schedule','Fixed_Income_Market_Schedule')) and c.relkind='r' order by 1;;
select schemaname, tablename, indexname, indexdef from pg_indexes where tablename in ('Feature_04_Technical_Indicator','Feature_04_Technical_Indicator_INDEX','Price_Stock_Indonesia_IDX') order by 2,3
