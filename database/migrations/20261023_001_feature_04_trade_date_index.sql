-- EXEC-M204 step 4 (user 2026-10-23: "Kenapa kita tidak tambahkan indexing saja untuk feature yang belum ada";
-- "Semua saham berbulan-bulan sampai bertahun-tahun harus bisa dijawab dari feature 1 sampai feature 6"; go "Semua
-- approve exec bisa dieksekusi").
-- Feature 04 has only its ticker-first key, so the SQL Governor cannot split a long all-ticker extraction by date
-- (extract.py partitioning needs an index whose first column is the time column) and the query_metric calendar runs
-- 7.0 s (scripts/onboarding/measure_indexes.py 2026-10-23, job bcfce0bd: P4 FAIL, P5 FAIL; P1-P3 PASS in 7-14 ms).
-- One statement, no transaction: CREATE INDEX CONCURRENTLY takes no write lock (feature-04-worker keeps writing) and
-- cannot run in a transaction block. A failed build leaves an INVALID index: drop it and run this file again.
CREATE INDEX CONCURRENTLY IF NOT EXISTS "Feature_04_Technical_Indicator_trade_date_idx"
    ON public."Feature_04_Technical_Indicator" (trade_date);
