select ticker, asset_type, calculation_version, count(*), min(trade_date), max(trade_date), max(calculated_at) from public."Feature_04_Technical_Indicator_INDEX" group by 1,2,3;;
select max(date) from public."Price_Stock_Indonesia_IDX" where ticker='IHSG' and is_final;;
select count(*) from public."Price_Stock_Indonesia_IDX" p where p.ticker='IHSG' and p.is_final and not exists (select 1 from public."Feature_04_Technical_Indicator_INDEX" f where f.ticker='IHSG' and f.trade_date=p.date)
