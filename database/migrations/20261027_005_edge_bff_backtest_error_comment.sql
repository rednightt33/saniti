-- EDGE backtest, second review of the result-store fix (2026-10-27; ERRORS M246, apps/edge-bff/backtest/CONTRACT.md
-- section 11 and decision B2): the comment of edge_bff.backtest_jobs.error that 20261026_005 wrote listed the codes
-- edge-bff sets, and the list went stale when edge-bff began to set RESULT_NOT_STORED (it never had WORKER_FAILED
-- either). The comment now says what the column holds and points to the one list of the codes, CONTRACT.md section 11,
-- so a new code needs no migration. Only the comment changes: no data, table, role or grant.
BEGIN;
SET LOCAL lock_timeout = '5s';
COMMENT ON COLUMN edge_bff.backtest_jobs.error IS 'ApiError.error of a FAILED job ({code, message?, field?, details?}): the worker''s error as it gave it, or one edge-bff set. Every code and who sets it: apps/edge-bff/backtest/CONTRACT.md section 11.';
DO $verify$
BEGIN
    IF coalesce(col_description('edge_bff.backtest_jobs'::regclass,
                                (SELECT attnum FROM pg_attribute WHERE attrelid = 'edge_bff.backtest_jobs'::regclass
                                 AND attname = 'error')), '') NOT LIKE '%CONTRACT.md section 11%' THEN
        RAISE EXCEPTION 'the comment of edge_bff.backtest_jobs.error was not changed';
    END IF;
END $verify$;
COMMIT;

-- Rollback (a new forward migration with this body):
-- COMMENT ON COLUMN edge_bff.backtest_jobs.error IS 'ApiError.error of a FAILED job: the worker''s error, or WORKER_LOST / TIMEOUT / RESULT_INVALID / LIMIT_EXCEEDED set by edge-bff.';
