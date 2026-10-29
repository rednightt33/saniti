select now(), version();;
select status, count(*), sum(case when requested_generation is distinct from completed_generation then 1 else 0 end) as lag from "Feature04_Calculation_Queue" group by 1;;
select status, count(*) from "Feature04_Column_Status" group by 1;;
select count(*), count(distinct (asset_type, ticker)), min(state_version), max(state_version) from "Feature04_Calculation_State";;
select status, count(*) from "Feature04_Calculation_Log" group by 1;;
select status, count(*) from "Feature04_Telegram_Outbox" group by 1;;
select count(*) from "Feature04_Retry_Request"
