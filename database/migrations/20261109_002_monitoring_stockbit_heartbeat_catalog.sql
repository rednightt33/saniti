-- EXEC-ROUND-HEARTBEAT (user go 2026-11-09: "Ok 1 dan 2.. serta fix M414. Jalankan."), ERRORS M413: stockbit-updater
-- stamps Monitoring_Stockbit_Update.updated_at every 60 s while a round is RUNNING (a heartbeat from its own
-- connection); terminal-publisher counts a RUNNING round only while that stamp is younger than 10 minutes. Metadata
-- only: no column, row or constraint changes.
BEGIN;
SET LOCAL lock_timeout = '5s';

UPDATE public."Column_Catalog"
SET definition = 'Last change of the row; while status is RUNNING also the round''s heartbeat, stamped every 60 seconds '
                 'by the live updater process (a RUNNING row not stamped for 10 minutes is a round whose process died).',
    source_code_paths = ARRAY['apps/stockbit-updater/updater.py', 'apps/stockbit-updater/broker_import.py',
                              'apps/terminal-publisher/publisher.py',
                              'database/migrations/20261109_002_monitoring_stockbit_heartbeat_catalog.sql'],
    updated_at = now()
WHERE table_schema = 'public' AND table_name = 'Monitoring_Stockbit_Update' AND column_name = 'updated_at';

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM public."Column_Catalog" WHERE table_name = 'Monitoring_Stockbit_Update'
                 AND column_name = 'updated_at' AND definition LIKE '%heartbeat%') THEN
    RAISE EXCEPTION 'Column_Catalog row for Monitoring_Stockbit_Update.updated_at not updated';
  END IF;
END $$;

COMMIT;
