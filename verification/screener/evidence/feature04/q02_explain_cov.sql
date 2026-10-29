explain select asset_type, ticker, count(*), min(trade_date), max(trade_date) from public."Feature_04_Technical_Indicator" group by asset_type, ticker;;
select attname, avg_width, null_frac from pg_stats where schemaname='public' and tablename='Feature_04_Technical_Indicator' order by attname;;
select sum(avg_width) sum_avg_width, count(*) from pg_stats where schemaname='public' and tablename='Feature_04_Technical_Indicator'
