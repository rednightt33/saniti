select asset_type, timeframe, max(trade_date), count(*) from public."Feature_04_Technical_Indicator" where trade_date >= date '2026-10-20' group by 1,2 ;;
select trade_date, count(*) from public."Feature_04_Technical_Indicator" where trade_date >= date '2026-10-20' and asset_type='equity' group by 1 order by 1 ;;
select attname, n_distinct, correlation from pg_stats where schemaname='public' and tablename='Feature_04_Technical_Indicator' and attname in ('ticker','trade_date','asset_type') ;;
select calculation_version, count(*) from public."Feature_04_Technical_Indicator" where trade_date >= date '2026-10-20' group by 1
