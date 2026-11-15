WITH m(t, s, f, u) AS (VALUES
  ('GAGOES','AMMN','-infinity'::date,'infinity'::date), ('GAGOES','BRMS','-infinity','infinity'),
  ('GCTCORP','BBHI','-infinity','infinity'), ('GCTCORP','MEGA','-infinity','infinity'),
  ('GHARITA','CITA','-infinity','infinity'), ('GHARITA','NCKL','-infinity','infinity'), ('GHARITA','TIRT','-infinity','infinity'),
  ('GRAJAWALI','ARCI','-infinity','infinity'), ('GRAJAWALI','BWPT','-infinity','infinity'),
  ('LQ45','AMMN','-infinity','infinity'), ('LQ45','BRMS','-infinity','infinity'),
  ('LQ45','MEGA','-infinity','2025-09-02'), ('LQ45','NCKL','2025-07-15','infinity'),
  ('IDXBASIC','AMMN','-infinity','infinity'), ('IDXBASIC','ARCI','-infinity','infinity'), ('IDXBASIC','BRMS','-infinity','infinity'),
  ('IDXBASIC','NCKL','-infinity','infinity'), ('IDXBASIC','CITA','-infinity','infinity'), ('IDXBASIC','BWPT','2025-08-05','infinity')),
exp AS (SELECT r."Date" AS trade_date, m.t AS ticker, r."Broker" AS broker, r."Market Board" AS market_board, r."Investor Type" AS investor_type,
   SUM(r."Buy Value") AS bv, SUM(r."Sell Value") AS sv, SUM(r."Buy Lots") AS bl, SUM(r."Sell Lots") AS sl
   FROM "IDX_Broker_Summary" r JOIN m ON m.s = r."Symbol" AND r."Date" >= m.f AND r."Date" < m.u
   WHERE r."Date" >= '2025-07-01' AND r."Date" <= '2025-10-31' GROUP BY 1,2,3,4,5),
got AS (SELECT trade_date, ticker, broker::text, market_board::text, investor_type::text, buy_value, sell_value, buy_lots, sell_lots
   FROM "Feature_05_Foreign_Domestic_Broker_Detail_INDEX" WHERE ticker <> 'IHSG')
SELECT (SELECT count(*) FROM exp) AS expected_rows, (SELECT count(*) FROM got) AS stored_rows,
  (SELECT count(*) FROM ((SELECT * FROM exp EXCEPT SELECT * FROM got) UNION ALL (SELECT * FROM got EXCEPT SELECT * FROM exp)) x) AS differing;
-- the day boundaries: LQ45 total buy value with and without NCKL / MEGA, IDXBASIC with and without BWPT
SELECT f.ticker, f.trade_date, sum(f.buy_value) AS stored_buy,
  (SELECT sum("Buy Value") FROM "IDX_Broker_Summary" WHERE "Date" = f.trade_date AND "Symbol" = 'NCKL') AS nckl,
  (SELECT sum("Buy Value") FROM "IDX_Broker_Summary" WHERE "Date" = f.trade_date AND "Symbol" = 'MEGA') AS mega,
  (SELECT sum("Buy Value") FROM "IDX_Broker_Summary" WHERE "Date" = f.trade_date AND "Symbol" = 'BWPT') AS bwpt,
  (SELECT sum("Buy Value") FROM "IDX_Broker_Summary" WHERE "Date" = f.trade_date AND "Symbol" IN ('AMMN','BRMS')) AS ammn_brms
FROM "Feature_05_Foreign_Domestic_Broker_Detail_INDEX" f
WHERE (f.ticker = 'LQ45' AND f.trade_date IN ('2025-07-14','2025-07-15','2025-09-01','2025-09-02'))
   OR (f.ticker = 'IDXBASIC' AND f.trade_date IN ('2025-08-04','2025-08-05'))
GROUP BY 1, 2 ORDER BY 1, 2;
