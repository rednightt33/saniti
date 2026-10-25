-- EXEC-GO-1025 item 7 (user 2026-10-25: "Okay, yang menunggu GO silahkan di jalankan"; ERRORS M222): Table_Catalog and
-- Column_Catalog rows for the two Stockbit backfill tables that were created outside Git, so Database_Table_Status and
-- the schema document stop listing them as "Unclassified". stockbit_full_broker_import_status was registered by
-- 20261025_014.
--
-- Evidence, read-only job 187fa567 (2026-10-25): idx_stockbit_backfill_status 2,599 rows, trade dates
-- 2016-01-04..2026-10-09, every state 'completed', written 2026-10-11..2026-10-15, one row keeps error_class
-- ValueError; idx_stockbit_value_corrections 10 rows (BHIT, 2016-11-02..2017-02-07, Foreign and Domestic five each,
-- created 2026-10-15, reason USER_APPROVED_ABS_BHIT_20261016). No trigger, no comment; pgweb_reader may read both. The
-- writer (the user's date-first Stockbit backfill) is not in Git, so a meaning read only from a column name is left
-- NULL with NEEDS_REVIEW (DATABASE_CATALOG.md: the AI must not infer it); what the constraints, the reason text and
-- the stored rows show is PARTIAL. Neither table is exposed to the AI.
BEGIN;

INSERT INTO public."Table_Catalog"(table_schema, table_name, category, definition, grain, primary_key_columns,
 source_system, source_tables, source_code_paths, update_rule, related_functions, documentation_status,
 readiness_mode, readiness_date_column, observation_date_column, availability_rule)
VALUES
('public', 'idx_stockbit_backfill_status', 'System',
 'Per-date control of the date-first Stockbit Broker Summary backfill of 2016-2026 (the user''s importer, before the ticker-first import of stockbit_full_broker_import_status): state, filter and request counts, rows written, attempts, error.',
 'One Broker Summary trade date', ARRAY['trade_date'], 'Stockbit backfill (user importer, outside Git)',
 ARRAY['IDX_Broker_Summary'], ARRAY['database/migrations/20261025_017_catalog_stockbit_backfill_tables.sql'],
 'Written by the date-first backfill between 2026-10-11 and 2026-10-15; every date completed; no job writes it now.',
 ARRAY[]::text[], 'PARTIAL', 'NOT_APPLICABLE', NULL, 'trade_date', 'Operational log, not market data.'),
('public', 'idx_stockbit_value_corrections', 'System',
 'Audit of user-approved corrections to Stockbit Broker Summary values: per trade date, ticker and investor type the summary row before and after, the per-broker patches, the raw source rows and the reason. Holds the BHIT negative-value correction (USER_APPROVED_ABS_BHIT_20261016: negative raw trade values made positive per user instruction; not independently source-verified).',
 'One corrected trade date, ticker and investor type', ARRAY['trade_date', 'ticker', 'investor_type'],
 'Stockbit backfill (user importer, outside Git)', ARRAY['IDX_Broker_Summary'],
 ARRAY['database/migrations/20261025_017_catalog_stockbit_backfill_tables.sql'],
 'Inserted once per correction the user approves; 10 rows written 2026-10-15.',
 ARRAY[]::text[], 'PARTIAL', 'NOT_APPLICABLE', NULL, 'trade_date', 'Audit log, not market data.')
ON CONFLICT (table_schema, table_name) DO NOTHING;

WITH d(table_name, column_name, definition, unit, null_rule, status) AS (VALUES
 ('idx_stockbit_backfill_status', 'trade_date', 'Broker Summary trade date the row controls.', NULL, 'Never NULL.', 'PARTIAL'),
 ('idx_stockbit_backfill_status', 'backfill_year', 'Calendar year of trade_date the backfill batch belongs to (CHECK 2016-2100).', NULL, 'Never NULL.', 'PARTIAL'),
 ('idx_stockbit_backfill_status', 'state', 'queued, fetching, uploading, completed, failed_fetch, failed_reconciliation, failed_database, blocked_auth or blocked_storage (CHECK); every stored row is completed.', NULL, 'Never NULL.', 'PARTIAL'),
 ('idx_stockbit_backfill_status', 'expected_filters', NULL, NULL, 'Never NULL; default 0.', 'NEEDS_REVIEW'),
 ('idx_stockbit_backfill_status', 'completed_filters', NULL, NULL, 'Never NULL; default 0.', 'NEEDS_REVIEW'),
 ('idx_stockbit_backfill_status', 'detail_rows', NULL, 'rows', 'Never NULL; default 0.', 'NEEDS_REVIEW'),
 ('idx_stockbit_backfill_status', 'summary_rows', NULL, 'rows', 'Never NULL; default 0.', 'NEEDS_REVIEW'),
 ('idx_stockbit_backfill_status', 'request_count', NULL, 'requests', 'Never NULL; default 0.', 'NEEDS_REVIEW'),
 ('idx_stockbit_backfill_status', 'attempt_count', 'Attempts the backfill made for the date.', NULL, 'Never NULL; default 0.', 'PARTIAL'),
 ('idx_stockbit_backfill_status', 'error_class', 'Exception class of the last error; may remain on a completed row.', NULL, 'NULL when no error was recorded.', 'PARTIAL'),
 ('idx_stockbit_backfill_status', 'error_message', 'Message of the last error.', NULL, 'NULL when no error was recorded.', 'PARTIAL'),
 ('idx_stockbit_backfill_status', 'started_at', 'Start of the last attempt.', NULL, 'NULL before the first attempt.', 'PARTIAL'),
 ('idx_stockbit_backfill_status', 'heartbeat_at', 'Last progress time.', NULL, 'Never NULL; default now().', 'PARTIAL'),
 ('idx_stockbit_backfill_status', 'completed_at', 'Time the date completed.', NULL, 'NULL until completed.', 'PARTIAL'),
 ('idx_stockbit_backfill_status', 'updated_at', 'Last change of the row.', NULL, 'Never NULL; default now().', 'PARTIAL'),
 ('idx_stockbit_value_corrections', 'trade_date', 'Trade date of the corrected Broker Summary rows.', NULL, 'Never NULL.', 'PARTIAL'),
 ('idx_stockbit_value_corrections', 'ticker', 'Ticker of the corrected rows.', NULL, 'Never NULL.', 'PARTIAL'),
 ('idx_stockbit_value_corrections', 'investor_type', 'Foreign or Domestic, as in IDX_Broker_Summary.', NULL, 'Never NULL.', 'PARTIAL'),
 ('idx_stockbit_value_corrections', 'before_summary', 'JSON array: the summary row before the correction (date, ticker, investor type, buy value, sell value, two counts, a flag and the source note).', NULL, 'Never NULL.', 'PARTIAL'),
 ('idx_stockbit_value_corrections', 'after_summary', 'JSON array: the same summary row after the correction, its note extended with the reason.', NULL, 'Never NULL.', 'PARTIAL'),
 ('idx_stockbit_value_corrections', 'detail_patches', 'JSON array of per-broker changes: board, broker, investor and the buy and sell values and counts before and after.', NULL, 'Never NULL.', 'PARTIAL'),
 ('idx_stockbit_value_corrections', 'raw_source_rows', 'JSON array: the per-broker rows as the source returned them, kept as the original values.', NULL, 'Never NULL.', 'PARTIAL'),
 ('idx_stockbit_value_corrections', 'reason', 'Approval code and reason of the correction.', NULL, 'Never NULL.', 'PARTIAL'),
 ('idx_stockbit_value_corrections', 'created_at', 'Time the correction was recorded.', NULL, 'Never NULL; default now().', 'PARTIAL'))
INSERT INTO public."Column_Catalog"(table_schema, table_name, column_name, ordinal_position, data_type, is_nullable,
 default_expression, is_primary_key, definition, source_column_or_expression, unit, null_rule, source_code_paths,
 documentation_status)
SELECT 'public', c.table_name, c.column_name, c.ordinal_position, c.data_type, c.is_nullable = 'YES', c.column_default,
 (c.table_name = 'idx_stockbit_backfill_status' AND c.column_name = 'trade_date')
  OR (c.table_name = 'idx_stockbit_value_corrections' AND c.column_name IN ('trade_date', 'ticker', 'investor_type')),
 d.definition, 'Stockbit backfill (outside Git)', d.unit, d.null_rule,
 ARRAY['database/migrations/20261025_017_catalog_stockbit_backfill_tables.sql'], d.status
FROM information_schema.columns c JOIN d USING (table_name, column_name)
WHERE c.table_schema = 'public'
ON CONFLICT (table_schema, table_name, column_name) DO NOTHING;

DO $check$ DECLARE missing int; BEGIN
 SELECT count(*) INTO missing FROM information_schema.columns c
 WHERE c.table_schema = 'public' AND c.table_name IN ('idx_stockbit_backfill_status', 'idx_stockbit_value_corrections')
   AND NOT EXISTS (SELECT 1 FROM public."Column_Catalog" k WHERE k.table_schema = 'public' AND k.table_name = c.table_name
                   AND k.column_name = c.column_name);
 IF missing > 0 THEN RAISE EXCEPTION '% columns lack a Column_Catalog row', missing; END IF;
 SELECT count(*) INTO missing FROM (VALUES ('idx_stockbit_backfill_status'), ('idx_stockbit_value_corrections')) v(t)
 WHERE NOT EXISTS (SELECT 1 FROM public."Table_Catalog" k WHERE k.table_schema = 'public' AND k.table_name = v.t);
 IF missing > 0 THEN RAISE EXCEPTION '% tables lack a Table_Catalog row', missing; END IF;
END $check$;

COMMIT;
