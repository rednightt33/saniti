-- EXEC-UNIVERSE-BROKER P2 (user go 2026-11-05: "S2 P2 P3 bisa dijalankan"; alarm decision "Opsi A" the same day):
-- the daily price run separates "no trade that day" from "could not fetch".
-- * no_trade_symbols / no_trade_symbol_list: TradingView answered for the symbol but has no bar on the target date,
--   while the same run got that date's bar for other symbols of the exchange (the session exists at the provider).
--   These are not missing: the run is SUCCESS when nothing else failed, and no alarm is raised for them.
-- * no_trade_contradicted: earlier no-trade (date, ticker) pairs that IDX_Broker_Summary later shows traded on the
--   Regular board while no price row exists: a real gap, reported once by the run that finds it.
-- Columns are added with defaults, so the code deployed before this migration keeps working.
-- Rollback: restore Monitoring_Price_ALL_counts_check as missing_symbols = queried_symbols - updated_symbols (only
-- when no row has no_trade_symbols > 0), DROP CONSTRAINT Monitoring_Price_ALL_no_trade_list_check, DROP COLUMN no_trade_symbols, DROP COLUMN no_trade_symbol_list,
-- DROP COLUMN no_trade_contradicted; DELETE the Column_Catalog rows below.
BEGIN;
SET LOCAL lock_timeout = '10s';

ALTER TABLE public."Monitoring_Price_ALL"
    ADD COLUMN IF NOT EXISTS no_trade_symbols integer NOT NULL DEFAULT 0 CHECK (no_trade_symbols >= 0),
    ADD COLUMN IF NOT EXISTS no_trade_symbol_list jsonb NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(no_trade_symbol_list) = 'array'),
    ADD COLUMN IF NOT EXISTS no_trade_contradicted jsonb NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(no_trade_contradicted) = 'array');

-- The count rule becomes missing + no trade = queried - updated (old code writes no_trade_symbols = 0 and still holds).
ALTER TABLE public."Monitoring_Price_ALL" DROP CONSTRAINT "Monitoring_Price_ALL_counts_check";
ALTER TABLE public."Monitoring_Price_ALL" ADD CONSTRAINT "Monitoring_Price_ALL_counts_check" CHECK (
    expected_symbols >= 0 AND queried_symbols >= 0 AND updated_symbols >= 0 AND missing_symbols >= 0
    AND queried_symbols <= expected_symbols AND updated_symbols <= queried_symbols
    AND missing_symbols + no_trade_symbols = queried_symbols - updated_symbols);
ALTER TABLE public."Monitoring_Price_ALL" ADD CONSTRAINT "Monitoring_Price_ALL_no_trade_list_check"
    CHECK (jsonb_array_length(no_trade_symbol_list) = no_trade_symbols);

COMMENT ON COLUMN public."Monitoring_Price_ALL".no_trade_symbols IS
 'EXEC-UNIVERSE-BROKER P2: symbols TradingView answered without a bar on the target date while the session exists (other symbols got it); not counted as missing.';
COMMENT ON COLUMN public."Monitoring_Price_ALL".no_trade_symbol_list IS
 'EXEC-UNIVERSE-BROKER P2: the tickers counted in no_trade_symbols.';
COMMENT ON COLUMN public."Monitoring_Price_ALL".no_trade_contradicted IS
 'EXEC-UNIVERSE-BROKER P2: [{date, ticker}] earlier no-trade pairs that IDX_Broker_Summary shows traded on the Regular board while no price row exists; reported once.';

WITH d(column_name, definition, unit, null_rule) AS (VALUES
 ('no_trade_symbols', 'Symbols TradingView answered without a bar on the target date while other symbols of the exchange got that date''s bar: no trade that day, not a fetch failure; not counted in missing_symbols.', 'count', 'Never NULL; 0 when none.'),
 ('no_trade_symbol_list', 'The tickers counted in no_trade_symbols.', 'list', 'Never NULL; [] when none.'),
 ('no_trade_contradicted', 'Earlier no-trade (date, ticker) pairs that IDX_Broker_Summary later shows traded on the Regular board while no price row exists for that date: a real price gap, reported once by the run that found it.', 'list', 'Never NULL; [] when none.'))
INSERT INTO public."Column_Catalog"(table_schema, table_name, column_name, ordinal_position, data_type, is_nullable,
 default_expression, is_primary_key, definition, source_column_or_expression, unit, null_rule, source_code_paths,
 documentation_status)
SELECT 'public', c.table_name, c.column_name, c.ordinal_position, c.data_type, c.is_nullable = 'YES', c.column_default,
 false, d.definition, 'apps/idx-price-cron/price_update.py (monitoring_records, no_trade_contradictions)',
 d.unit, d.null_rule, ARRAY['database/migrations/20261105_003_price_no_trade.sql'], 'VERIFIED'
FROM information_schema.columns c JOIN d USING (column_name)
WHERE c.table_schema = 'public' AND c.table_name = 'Monitoring_Price_ALL'
ON CONFLICT (table_schema, table_name, column_name) DO NOTHING;

COMMIT;
