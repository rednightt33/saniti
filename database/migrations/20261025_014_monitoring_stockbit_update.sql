-- EXEC-STOCKBIT-UPDATER (user go 2026-10-25, EXEC-GO-1025): one row per round of the stockbit-updater service, read
-- by telegram-monitor to send the round summary (decision K5). Also registers stockbit_full_broker_import_status, the
-- per-date control table the user's importer created and the service keeps writing (ERRORS M222).
BEGIN;
SET LOCAL lock_timeout = '5s';

CREATE TABLE public."Monitoring_Stockbit_Update" (
 execution_id uuid PRIMARY KEY,
 mode text NOT NULL CHECK (mode IN ('APPLY', 'VERIFY')),
 status text NOT NULL CHECK (status IN ('RUNNING', 'SUCCESS', 'FAILED')),
 started_at timestamptz NOT NULL,
 finished_at timestamptz,
 deployment_id text,
 token_expires_at timestamptz,
 broker jsonb,
 broker_dates jsonb,
 broker_rows bigint CHECK (broker_rows >= 0),
 features jsonb,
 index_result jsonb,
 events jsonb,
 last_error text,
 updated_at timestamptz NOT NULL DEFAULT now(),
 CHECK (finished_at IS NULL OR finished_at >= started_at),
 CHECK ((status = 'RUNNING') = (finished_at IS NULL))
);
CREATE INDEX "Monitoring_Stockbit_Update_started_idx" ON public."Monitoring_Stockbit_Update" (started_at DESC);
COMMENT ON TABLE public."Monitoring_Stockbit_Update" IS
 'One row per stockbit-updater round: Broker Summary dates loaded, Feature 02/03/05/06 and INDEX refresh, Stockbit event reload, status; read by telegram-monitor.';

INSERT INTO public."Table_Catalog"(table_schema, table_name, category, definition, grain, primary_key_columns,
 source_system, source_tables, source_code_paths, update_rule, related_functions, documentation_status,
 readiness_mode, readiness_date_column, observation_date_column, availability_rule)
VALUES
('public', 'Monitoring_Stockbit_Update', 'Monitoring',
 'One row per round of the stockbit-updater service: mode, status, token expiry, Broker Summary dates and rows loaded, Feature 02/03/05/06 and INDEX refresh results, Stockbit corporate action and insider reload, error.',
 'One updater round', ARRAY['execution_id'], 'stockbit-updater service', ARRAY['IDX_Broker_Summary'],
 ARRAY['apps/stockbit-updater/updater.py', 'database/migrations/20261025_014_monitoring_stockbit_update.sql'],
 'Inserted RUNNING when a round starts and finished once per round (each deploy of stockbit-updater).',
 ARRAY[]::text[], 'VERIFIED', 'NOT_APPLICABLE', NULL, 'started_at', 'Operational log, not market data.'),
('public', 'stockbit_full_broker_import_status', 'System',
 'Per-date control of the ticker-first Broker Summary import (the user''s importer, then stockbit-updater): manifest hash of the symbol list, state, expected and completed symbols, rows, anomaly symbols, heartbeat, error.',
 'One Broker Summary trade date', ARRAY['trade_date'], 'Stockbit importer', ARRAY['IDX_Broker_Summary'],
 ARRAY['apps/stockbit-updater/broker_import.py'],
 'Written fetching, completed or failed by each import of a date.',
 ARRAY[]::text[], 'VERIFIED', 'NOT_APPLICABLE', NULL, 'trade_date', 'Operational log, not market data.')
ON CONFLICT (table_schema, table_name) DO NOTHING;

WITH d(table_name, column_name, definition, unit, null_rule) AS (VALUES
 ('Monitoring_Stockbit_Update', 'execution_id', 'Round id, also the Telegram delivery key.', NULL, 'Never NULL.'),
 ('Monitoring_Stockbit_Update', 'mode', 'APPLY (load and refresh) or VERIFY (fetch one stored date and compare, no write).', NULL, 'Never NULL.'),
 ('Monitoring_Stockbit_Update', 'status', 'RUNNING, SUCCESS or FAILED.', NULL, 'Never NULL.'),
 ('Monitoring_Stockbit_Update', 'started_at', 'Start of the round.', NULL, 'Never NULL.'),
 ('Monitoring_Stockbit_Update', 'finished_at', 'End of the round.', NULL, 'NULL while RUNNING.'),
 ('Monitoring_Stockbit_Update', 'deployment_id', 'Railway deployment that ran the round.', NULL, 'NULL when Railway gives none.'),
 ('Monitoring_Stockbit_Update', 'token_expires_at', 'Expiry (JWT exp) of the Stockbit token the round used; the token itself is never stored.', NULL, 'NULL when the token is missing or not a JWT.'),
 ('Monitoring_Stockbit_Update', 'broker', 'Broker Summary step result: symbols, dates, per-date rows (VERIFY: comparison counts).', NULL, 'NULL when the step did not run.'),
 ('Monitoring_Stockbit_Update', 'broker_dates', 'Trade dates the round loaded into IDX_Broker_Summary.', NULL, 'NULL when the step did not run.'),
 ('Monitoring_Stockbit_Update', 'broker_rows', 'Rows loaded into IDX_Broker_Summary.', 'rows', 'NULL when the step did not run.'),
 ('Monitoring_Stockbit_Update', 'features', 'Feature 05/02/03/06 refresh: changed dates and counts.', NULL, 'NULL when the step did not run.'),
 ('Monitoring_Stockbit_Update', 'index_result', 'INDEX tables refresh result or why it was skipped.', NULL, 'NULL when the step did not run.'),
 ('Monitoring_Stockbit_Update', 'events', 'Stockbit corporate action and insider reconcile counts.', NULL, 'NULL when the step did not run.'),
 ('Monitoring_Stockbit_Update', 'last_error', 'Error that ended the round.', NULL, 'NULL on success.'),
 ('Monitoring_Stockbit_Update', 'updated_at', 'Last change of the row.', NULL, 'Never NULL.'),
 ('stockbit_full_broker_import_status', 'trade_date', 'Broker Summary trade date.', NULL, 'Never NULL.'),
 ('stockbit_full_broker_import_status', 'manifest_hash', 'SHA-256 of the symbol list fetched for the date.', NULL, 'Never NULL.'),
 ('stockbit_full_broker_import_status', 'state', 'fetching, completed or failed.', NULL, 'Never NULL.'),
 ('stockbit_full_broker_import_status', 'expected_symbols', 'Symbols in the list for the date.', 'symbols', 'Never NULL.'),
 ('stockbit_full_broker_import_status', 'completed_symbols', 'Symbols whose six filters finished.', 'symbols', 'Never NULL.'),
 ('stockbit_full_broker_import_status', 'row_count', 'IDX_Broker_Summary rows written for the date.', 'rows', 'Never NULL; 0 until completed.'),
 ('stockbit_full_broker_import_status', 'anomaly_symbols', 'Symbols with a retained source anomaly (missing average, buy/sell imbalance).', 'symbols', 'Never NULL.'),
 ('stockbit_full_broker_import_status', 'heartbeat_at', 'Last progress time.', NULL, 'Never NULL.'),
 ('stockbit_full_broker_import_status', 'completed_at', 'Commit time of the date.', NULL, 'NULL until completed.'),
 ('stockbit_full_broker_import_status', 'error_message', 'Error that stopped the date.', NULL, 'NULL unless failed.'))
INSERT INTO public."Column_Catalog"(table_schema, table_name, column_name, ordinal_position, data_type, is_nullable,
 default_expression, is_primary_key, definition, source_column_or_expression, unit, null_rule, source_code_paths,
 documentation_status)
SELECT 'public', c.table_name, c.column_name, c.ordinal_position, c.data_type, c.is_nullable = 'YES', c.column_default,
 c.column_name = ANY (ARRAY['execution_id', 'trade_date']), d.definition, 'apps/stockbit-updater', d.unit, d.null_rule,
 ARRAY['apps/stockbit-updater/updater.py', 'apps/stockbit-updater/broker_import.py'], 'VERIFIED'
FROM information_schema.columns c JOIN d USING (table_name, column_name)
WHERE c.table_schema = 'public'
ON CONFLICT (table_schema, table_name, column_name) DO NOTHING;

DO $check$ DECLARE missing int; BEGIN
 SELECT count(*) INTO missing FROM information_schema.columns c
 WHERE c.table_schema = 'public' AND c.table_name IN ('Monitoring_Stockbit_Update', 'stockbit_full_broker_import_status')
   AND NOT EXISTS (SELECT 1 FROM public."Column_Catalog" k WHERE k.table_schema = 'public' AND k.table_name = c.table_name
                   AND k.column_name = c.column_name);
 IF missing > 0 THEN RAISE EXCEPTION '% columns lack a Column_Catalog row', missing; END IF;
END $check$;
COMMIT;
