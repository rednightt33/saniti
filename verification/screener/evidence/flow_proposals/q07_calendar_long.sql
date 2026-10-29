SELECT k, d FROM (SELECT d, row_number() OVER (ORDER BY d DESC) k FROM (SELECT DISTINCT date d FROM "Feature_03_Stock_Broker_Daily" WHERE date BETWEEN DATE '2025-06-01' AND DATE '2026-10-27' AND market_board = 'Regular') x) y
WHERE k IN (1, 5, 10, 20, 25, 41, 60, 61, 130, 252, 272, 280, 300, 330) ORDER BY k
