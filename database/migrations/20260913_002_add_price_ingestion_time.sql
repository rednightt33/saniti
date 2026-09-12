BEGIN;

DO $migration$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'Price_Stock_Indonesia_IDX'
          AND column_name = 'ingestion_time'
    ) THEN
        RAISE EXCEPTION
            'public."Price_Stock_Indonesia_IDX".ingestion_time already exists';
    END IF;
END
$migration$;

ALTER TABLE public."Price_Stock_Indonesia_IDX"
    ADD COLUMN ingestion_time timestamp with time zone;

ALTER TABLE public."Price_Stock_Indonesia_IDX"
    ALTER COLUMN ingestion_time SET DEFAULT statement_timestamp();

COMMENT ON COLUMN public."Price_Stock_Indonesia_IDX".ingestion_time IS
    'Timezone-aware database statement time of the latest successful insert or upsert; null for historical rows whose exact ingestion time is unknown.';

COMMIT;
