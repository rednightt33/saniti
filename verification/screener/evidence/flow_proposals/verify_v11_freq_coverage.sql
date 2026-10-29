-- FL16/FL17 coverage: frequency NULLs on 4-letter tickers (stocks) on 12 more sampled dates, all boards (q21 sampled
-- 6 dates, Regular only).
SELECT trade_date::date, market_board, count(*) rows, count(*) FILTER (WHERE length(ticker) = 4) rows_4letter,
       count(*) FILTER (WHERE (foreign_buy_freq_1d IS NULL OR domestic_buy_freq_1d IS NULL) AND length(ticker) = 4) freq_null_4letter
FROM "Feature_06_Foreign_Domestic"
WHERE trade_date IN (DATE '2017-03-15', DATE '2019-03-13', DATE '2021-03-15', DATE '2023-03-15', DATE '2025-09-15', DATE '2025-12-10',
                     DATE '2026-05-20', DATE '2026-08-20', DATE '2026-08-31', DATE '2026-09-17', DATE '2026-10-26', DATE '2026-10-27')
GROUP BY 1, 2 ORDER BY 1, 2
