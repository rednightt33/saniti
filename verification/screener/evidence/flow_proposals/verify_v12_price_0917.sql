SELECT date, count(*) rows FROM "Price_Stock_Indonesia_IDX" WHERE timeframe = 'Daily' AND date BETWEEN DATE '2026-09-16' AND DATE '2026-09-21' GROUP BY 1 ORDER BY 1
