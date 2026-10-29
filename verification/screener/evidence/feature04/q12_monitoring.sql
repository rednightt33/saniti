select execution_id, run_type, trigger_source, update_for_date, eligible_tickers, completed_tickers, failed_tickers, blocked_tickers, status, started_at, finished_at, left(last_error,80) err from public."Monitoring_Feature04" order by started_at desc limit 15;;
select status, run_type, count(*), min(started_at), max(started_at) from public."Monitoring_Feature04" group by 1,2 order by 1,2;;
select result, error_code, count(*), min(started_at), max(started_at) from public."Feature04_Calculation_Log" group by 1,2 order by 1,2;;
select result, error_code, count(*), round(avg(source_rows),1) avg_src_rows, max(source_rows) max_src_rows, round(avg(extract(epoch from finished_at-started_at))::numeric,2) avg_s, max(extract(epoch from finished_at-started_at)) max_s from public."Feature04_Calculation_Log" where started_at > now()-interval '7 days' group by 1,2 order by 1,2;;
select status, notification_type, count(*), max(sent_at) from public."Feature04_Notification_Outbox" group by 1,2;;
select status, count(*), count(distinct run_id) runs, count(distinct ticker), min(started_at), max(finished_at), string_agg(distinct calculation_version, ',') from public.feature04_backfill_log group by 1
