SELECT "Security Type", count(*) FROM "IDX_Stock_Universe" GROUP BY 1;;
SELECT market_board, count(*) rows, count(DISTINCT ticker) tickers FROM "Feature_03_Stock_Broker_Daily" WHERE date = DATE '2026-10-27' GROUP BY 1;;
SELECT count(DISTINCT f.ticker) any_board_univ, count(DISTINCT f.ticker) FILTER (WHERE f.market_board='Regular') reg_univ
FROM "Feature_03_Stock_Broker_Daily" f JOIN "IDX_Stock_Universe" u ON u."Ticker"=f.ticker AND u."Security Type"='stock' WHERE f.date = DATE '2026-10-27'
