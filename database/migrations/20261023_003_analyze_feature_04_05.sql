-- EXEC-M204 step 4: fresh planner statistics after 20261023_001/002 (NEW_TABLE_ONBOARDING_PLAN.md section 3: "then
-- ANALYZE"). Feature 04 was last analyzed 2026-10-11 and its reltuples reads 3,008,498 while count(*) is 1,386,698
-- (pgweb 2026-10-23); the SQL Governor counts a Seq Scan as reltuples, so the stale figure doubles its scan estimate.
BEGIN;
ANALYZE public."Feature_04_Technical_Indicator";
ANALYZE public."Feature_05_Foreign_Domestic_Broker_Detail";
COMMIT;
