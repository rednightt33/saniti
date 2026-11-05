-- EXEC-PUBLISH-FLOW S1 (user go 2026-11-05: "Q3 per device ok, go EXEC-PUBLISH-FLOW"): the signal that a loader finished
-- filling its tables, so terminal-publisher runs after the tables are full instead of at fixed clock times.
-- * terminal_publish_signal: one row per finished loader run that changed data (price, fixed income, intraday, broker
--   round), written by telegram-monitor when the loader's own completion notice arrives (the loaders notify after their
--   commit). telegram-monitor then presses Run Now on terminal-publisher. The publisher only reads it: a run that started
--   before a newer signal runs once more, and a signal newer than the last publication is what the check alerts on.
-- * terminal_market_reader (the publisher's group) may read the signals and Monitoring_Stockbit_Update (a broker round
--   still RUNNING means a loader is writing; the round's updater is not redeployed for this change).
-- Rollback: DROP TABLE public.terminal_publish_signal; REVOKE the grants below; DELETE the catalog rows below.
BEGIN;

CREATE TABLE IF NOT EXISTS public.terminal_publish_signal (
    signal_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source text NOT NULL CHECK (source ~ '^[A-Za-z][A-Za-z0-9_]{0,63}$'),
    execution_id text NOT NULL CHECK (execution_id ~ '^[A-Za-z0-9._:-]{1,200}$'),
    run_type text CHECK (run_type IS NULL OR run_type ~ '^[A-Z_]{1,32}$'),
    changed integer NOT NULL CHECK (changed >= 0),
    created_at timestamptz NOT NULL DEFAULT statement_timestamp(),
    trigger_status text NOT NULL DEFAULT 'PENDING' CHECK (trigger_status IN ('PENDING', 'TRIGGERED', 'NOT_CONFIGURED', 'FAILED')),
    trigger_error text CHECK (trigger_error IS NULL OR length(trigger_error) <= 300),
    triggered_at timestamptz,
    CONSTRAINT terminal_publish_signal_once UNIQUE (source, execution_id)
);
CREATE INDEX IF NOT EXISTS terminal_publish_signal_created ON public.terminal_publish_signal (created_at);
COMMENT ON TABLE public.terminal_publish_signal IS
 'One row per finished loader run that changed data (price, fixed income, intraday, broker round), written by telegram-monitor from the loader''s completion notice, which the loader sends after its commit; telegram-monitor then presses Run Now on terminal-publisher (trigger_status). terminal-publisher reads it to run again when a newer signal arrived during its run (EXEC-PUBLISH-FLOW).';

DO $grant$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'terminal_market_reader') THEN
        GRANT SELECT ON public.terminal_publish_signal, public."Monitoring_Stockbit_Update" TO terminal_market_reader;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pgweb_reader') THEN
        GRANT SELECT ON public.terminal_publish_signal TO pgweb_reader;
    END IF;
END $grant$;

INSERT INTO public."Table_Catalog"(table_schema, table_name, category, definition, grain, primary_key_columns,
 source_system, source_tables, source_code_paths, update_rule, related_functions, documentation_status,
 readiness_mode, readiness_date_column, observation_date_column, availability_rule, point_in_time_status)
VALUES
('public', 'terminal_publish_signal', 'System', 'One row per finished loader run that changed data (price, fixed income, intraday, broker round): the signal that its tables are full, after which terminal-publisher runs (Run Now by telegram-monitor).', 'One loader run (source, execution_id)', ARRAY['signal_id']::text[], 'apps/telegram-monitor/telegram_monitor.py', ARRAY['Monitoring_Price_ALL', 'Monitoring_Fixed_Income', 'Monitoring_Stockbit_Update']::text[], ARRAY['database/migrations/20261105_001_terminal_publish_signal.sql', 'apps/telegram-monitor/telegram_monitor.py', 'apps/terminal-publisher/publisher.py', 'apps/idx-price-cron/intraday_update.py']::text[], 'Inserted once per loader run by telegram-monitor when the loader''s completion notice arrives (unique source, execution_id); trigger_status records the Run Now; read by terminal-publisher.', ARRAY[]::text[], 'VERIFIED', 'NOT_APPLICABLE', NULL, NULL, 'Operational record, not market data; not exposed to the AI.', 'NOT_APPLICABLE')
ON CONFLICT (table_schema, table_name) DO NOTHING;

WITH d(column_name, definition, unit, null_rule) AS (VALUES
 ('signal_id', 'Row identity, in insertion order.', 'id', 'Never NULL.'),
 ('source', 'Who finished: the monitoring table of the loader (Monitoring_Price_ALL, Monitoring_Fixed_Income, Monitoring_Stockbit_Update) or Terminal_Publish_Request for a loader without one (idx-intraday-cron).', 'code', 'Never NULL.'),
 ('execution_id', 'The loader run''s execution id, as in its monitoring row.', 'code', 'Never NULL.'),
 ('run_type', 'DAILY or RECOVERY when the loader has one.', 'code', 'NULL for a loader without a run type.'),
 ('changed', 'How much the run changed: updated symbols or series, broker rows, or bars written.', 'count', 'Never NULL.'),
 ('created_at', 'When telegram-monitor recorded the signal.', 'timestamp', 'Never NULL.'),
 ('trigger_status', 'PENDING, TRIGGERED (Run Now accepted), NOT_CONFIGURED (no token or instance id) or FAILED.', 'code', 'Never NULL.'),
 ('trigger_error', 'The class of the Run Now failure.', 'text', 'NULL unless FAILED.'),
 ('triggered_at', 'When Run Now was accepted.', 'timestamp', 'NULL unless TRIGGERED.'))
INSERT INTO public."Column_Catalog"(table_schema, table_name, column_name, ordinal_position, data_type, is_nullable,
 default_expression, is_primary_key, definition, source_column_or_expression, unit, null_rule, source_code_paths,
 documentation_status)
SELECT 'public', c.table_name, c.column_name, c.ordinal_position, c.data_type, c.is_nullable = 'YES', c.column_default,
 c.column_name = 'signal_id', d.definition, 'apps/telegram-monitor/telegram_monitor.py (record_publish_signal)',
 d.unit, d.null_rule, ARRAY['database/migrations/20261105_001_terminal_publish_signal.sql'], 'VERIFIED'
FROM information_schema.columns c JOIN d USING (column_name)
WHERE c.table_schema = 'public' AND c.table_name = 'terminal_publish_signal'
ON CONFLICT (table_schema, table_name, column_name) DO NOTHING;

COMMIT;
