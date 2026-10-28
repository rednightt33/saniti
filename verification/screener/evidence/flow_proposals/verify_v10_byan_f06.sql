SELECT ticker, market_board, round((foreign_net_20d / 1e9)::numeric, 2) stored_fnet20_b
FROM "Feature_06_Foreign_Domestic" WHERE trade_date = DATE '2026-10-27' AND ticker IN ('BYAN', 'CARE') ORDER BY 1, 2
