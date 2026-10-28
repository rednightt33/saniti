select asset_type, ticker, count(*) n, min(trade_date) first_date, max(trade_date) last_date from public."Feature_04_Technical_Indicator" group by asset_type, ticker order by asset_type, ticker
