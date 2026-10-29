-- 16.3 calendar claim: do price bars exist on days a stock had no broker row? Universe stocks, 20 market sessions
-- 2026-09-30..10-27: stock-days with broker rows (any board), with a Daily price row, and the mismatches.
WITH s AS (SELECT "Ticker" t FROM "IDX_Stock_Universe" WHERE "Security Type" = 'stock'),
b AS (SELECT DISTINCT ticker, date FROM "Feature_03_Stock_Broker_Daily" WHERE date BETWEEN DATE '2026-09-30' AND DATE '2026-10-27'),
p AS (SELECT ticker, date, volume FROM "Price_Stock_Indonesia_IDX" WHERE timeframe = 'Daily' AND date BETWEEN DATE '2026-09-30' AND DATE '2026-10-27')
SELECT count(*) FILTER (WHERE b.ticker IS NOT NULL) broker_days, count(*) FILTER (WHERE p.ticker IS NOT NULL) price_days,
  count(*) FILTER (WHERE b.ticker IS NOT NULL AND p.ticker IS NULL) broker_no_price,
  count(*) FILTER (WHERE b.ticker IS NULL AND p.ticker IS NOT NULL) price_no_broker,
  count(*) FILTER (WHERE b.ticker IS NULL AND p.ticker IS NOT NULL AND coalesce(p.volume, 0) = 0) price_no_broker_vol0,
  count(DISTINCT coalesce(b.ticker, p.ticker)) FILTER (WHERE b.ticker IS NULL AND p.ticker IS NOT NULL) tickers_price_no_broker,
  count(DISTINCT coalesce(b.ticker, p.ticker)) FILTER (WHERE b.ticker IS NOT NULL AND p.ticker IS NULL) tickers_broker_no_price
FROM b FULL JOIN p ON p.ticker = b.ticker AND p.date = b.date
WHERE coalesce(b.ticker, p.ticker) IN (SELECT t FROM s)
