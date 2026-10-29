select result, count(*) from "Feature04_Calculation_Log" group by 1 order by 2 desc;;
select status, count(*) from "Feature04_Notification_Outbox" group by 1;;
select run_type, status, count(*) from "Monitoring_Feature04" group by 1,2 order by 1,2;;
select id, asset_type, ticker, result, error_code, left(detail,300) as detail, started_at, dirty_from_date, checkpoint_date from "Feature04_Calculation_Log" where result not in ('SUCCESS') order by id desc limit 20;;
select status, count(*), count(distinct ticker), min(calculation_version), max(calculation_version), count(distinct run_id) from feature04_backfill_log group by 1;;
select n_live_tup, n_dead_tup, n_tup_ins, n_tup_upd, n_tup_hot_upd, n_tup_del, last_vacuum, last_autovacuum, last_analyze, last_autoanalyze from pg_stat_user_tables where relname='Feature_04_Technical_Indicator'
