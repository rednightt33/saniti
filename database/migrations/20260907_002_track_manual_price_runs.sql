BEGIN;

ALTER TABLE public."Monitoring_Price_ALL"
    ADD COLUMN IF NOT EXISTS execution_id text,
    ADD COLUMN IF NOT EXISTS trigger_source text,
    ADD COLUMN IF NOT EXISTS query_time timestamp with time zone;

UPDATE public."Monitoring_Price_ALL"
SET execution_id = 'legacy-' || id::text
WHERE execution_id IS NULL;

UPDATE public."Monitoring_Price_ALL"
SET trigger_source = 'SCHEDULED'
WHERE trigger_source IS NULL;

UPDATE public."Monitoring_Price_ALL"
SET query_time = run_time
WHERE query_time IS NULL;

ALTER TABLE public."Monitoring_Price_ALL"
    ALTER COLUMN execution_id SET NOT NULL,
    ALTER COLUMN trigger_source SET NOT NULL,
    ALTER COLUMN query_time SET NOT NULL;

ALTER TABLE public."Monitoring_Price_ALL"
    DROP CONSTRAINT IF EXISTS "Monitoring_Price_ALL_run_key";

DO $migration$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'public."Monitoring_Price_ALL"'::regclass
          AND conname = 'Monitoring_Price_ALL_execution_key'
    ) THEN
        ALTER TABLE public."Monitoring_Price_ALL"
            ADD CONSTRAINT "Monitoring_Price_ALL_execution_key"
            UNIQUE (execution_id, exchange, asset_type, timeframe);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'public."Monitoring_Price_ALL"'::regclass
          AND conname = 'Monitoring_Price_ALL_trigger_source_check'
    ) THEN
        ALTER TABLE public."Monitoring_Price_ALL"
            ADD CONSTRAINT "Monitoring_Price_ALL_trigger_source_check"
            CHECK (trigger_source IN ('SCHEDULED', 'MANUAL'));
    END IF;
END
$migration$;

CREATE INDEX IF NOT EXISTS "Monitoring_Price_ALL_execution_idx"
    ON public."Monitoring_Price_ALL" (update_for_date DESC, query_time DESC);

COMMENT ON COLUMN public."Monitoring_Price_ALL".execution_id IS
    'Unique identifier shared by all asset-type rows written by one service execution.';
COMMENT ON COLUMN public."Monitoring_Price_ALL".trigger_source IS
    'Execution origin inferred by the service: SCHEDULED or MANUAL.';
COMMENT ON COLUMN public."Monitoring_Price_ALL".query_time IS
    'UTC time immediately before the TradingView request begins.';

COMMIT;
