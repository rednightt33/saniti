-- Bounded pre-index EXPLAIN ANALYZE showed a 2.14s parallel heap scan and
-- 1,416,602 shared buffers for one Regular-board date on the 45.2M-row v2.
-- Feature 02 has no automatic writer, so this transactional build is safe.
BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='15min';

DO $preflight$
BEGIN
    IF to_regclass('public."Feature_02_Broker_Rolling"') IS NULL
       OR NOT EXISTS (
           SELECT 1 FROM information_schema.columns
           WHERE table_schema='public' AND table_name='Feature_02_Broker_Rolling'
             AND column_name='investor_type'
       ) THEN
        RAISE EXCEPTION 'Expected canonical Investor-Type Feature 02 v2';
    END IF;
    IF to_regclass('public."Feature_02_Broker_Rolling_date_board_ticker_idx"') IS NOT NULL THEN
        RAISE EXCEPTION 'Feature 02 daily index already exists';
    END IF;
END
$preflight$;

CREATE INDEX "Feature_02_Broker_Rolling_date_board_ticker_idx"
    ON public."Feature_02_Broker_Rolling" (date, market_board, ticker);
COMMIT;
