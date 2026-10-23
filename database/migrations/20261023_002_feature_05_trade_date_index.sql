-- EXEC-M204 step 4 (user 2026-10-23, same decision as 20261023_001).
-- Feature 05 (45.2 M rows) has only its ticker-first key: every ticker over 365 days is refused (Seq Scan counted as
-- 45,245,000 rows) and cannot be split by date. A/B 2026-10-23 (DATABASE_INDEX_ACCEPTANCE.md "Feature 05: A/B of a
-- (trade_date) index", job f2d33648): with this index the same request is split by date; index 300 MB, built in 132 s.
-- Known cost from the same A/B: one broker across every ticker over 6 months touches 2.5x the data with it (measured
-- separately for a second index, EXEC-M204 step 4).
-- One statement, no transaction (CREATE INDEX CONCURRENTLY). A failed build leaves an INVALID index: drop it and rerun.
CREATE INDEX CONCURRENTLY IF NOT EXISTS "Feature_05_Foreign_Domestic_Broker_Detail_trade_date_idx"
    ON public."Feature_05_Foreign_Domestic_Broker_Detail" (trade_date);
