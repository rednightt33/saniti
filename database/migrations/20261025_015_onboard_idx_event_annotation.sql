-- EXEC-GO-1025 item 2 (user 2026-10-25: "go for this as well Service stockbit-updater dan onboarding hanya table
-- idx_event_annotation"): idx_event_annotation onboarded to the AI (NEW_TABLE_ONBOARDING_PLAN.md section 4). The two
-- source tables (stockbit_corporate_action, stockbit_insider_transaction) stay hidden.
--
-- Step 2 decisions (taken in the go, recorded here and in EXEC.md; each can be changed by a later migration):
-- - exposed directly, every row (corporate actions of every Stockbit code incl. structured warrants on their underlying
--   ticker; insider movements of IDX stocks);
-- - hidden columns: source_payload (verbatim Stockbit row, large), source_endpoint, source_fetched_at, ingestion_time
--   (bookkeeping); the details the AI needs are typed columns;
-- - no preview, no relationship in this version: an event date need not be a trading date and one date can hold several
--   events per ticker, so a join to the price tables would multiply rows; the AI reads events on their own and
--   combines them in its analysis code;
-- - subject MARKET / STOCK / IDX_EQUITY, frequency 1D, ACTIVITY_ONLY (a row only when an event exists);
-- - freshness 7 days: the table is refreshed by each stockbit-updater round (the user deploys with a new token, K2);
-- - coverage from the table itself (apps/ai-data-coverage RAW_SOURCES);
-- - Indonesian meanings DRAFT.
-- Index acceptance (measure_indexes.py job, 2026-10-25): P1 23.9 ms, P2 0.7 ms, P3 0.1 ms, P4 count 9 ms, P5 calendar
-- 352 ms without Seq Scan, table PASS (123,047 rows, 140,000 expected in a year); no index added.
-- Rollback (forward-only): is_active = false on the AI_table_catalog row and REVOKE the grant.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '5min';

DO $preflight$
BEGIN
    IF EXISTS (SELECT 1 FROM public."AI_table_catalog" WHERE table_name = 'idx_event_annotation') THEN
        RAISE EXCEPTION 'idx_event_annotation is already in AI_table_catalog';
    END IF;
    IF (SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public'
        AND table_name = 'idx_event_annotation') <> 26 THEN
        RAISE EXCEPTION 'idx_event_annotation does not have the 26 columns of 20261025_013';
    END IF;
    IF (SELECT count(*) FROM public."Column_Catalog" WHERE table_schema = 'public'
        AND table_name = 'idx_event_annotation') <> 26 THEN
        RAISE EXCEPTION 'idx_event_annotation lacks its Column_Catalog rows';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'market_ai_sql_reader') THEN
        RAISE EXCEPTION 'market_ai_sql_reader is missing';
    END IF;
END
$preflight$;

REVOKE ALL ON public.idx_event_annotation FROM PUBLIC;
GRANT SELECT ON public.idx_event_annotation TO market_ai_sql_reader;
DO $grant$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pgweb_reader') THEN
        GRANT SELECT ON public.idx_event_annotation TO pgweb_reader;
    END IF;
END $grant$;

INSERT INTO public."AI_table_catalog" (
    table_name, description, category, grain, primary_key_columns, time_column, entity_column, owner, is_active,
    ai_access_level, freshness_sla, coverage_enabled, documentation_status, data_domain, entity_type, asset_type,
    supported_frequencies, time_semantics, subject_metadata_status, row_presence, row_presence_status)
VALUES ('idx_event_annotation',
 'Corporate actions and insider ownership movements of IDX stocks (aksi korporasi dan transaksi orang dalam / insider), one row per event, from Stockbit. Corporate actions: dividend (dividen, cum and ex date), stock dividend, stock split, reverse split, bonus share (saham bonus), rights issue (HMETD), warrant (waran, structured warrants on their underlying ticker), tender offer, RUPS shareholder meeting, public expose; annotation_date is the ex date, trading start, offer start, meeting or expose date (annotation_date_role). Insider movements (INSIDER_TRANSACTION): IDX insider reports and KSEI 5% major holder changes (pemegang saham di atas 5 persen): action (BUY, SELL, ...), holder name, role (direktur, komisaris, pengendali), nationality (LOCAL or FOREIGN), broker, shares before, after and change, current ownership percent (pct_after) and change percent (pct_change), price and value in IDR, data_origin IDX or KSEI. Use it for jadwal dividen, cum date, stock split, rights issue, siapa insider yang beli atau jual, kepemilikan direktur, pemegang 5 persen. pct_quality_flag marks percent values that fail an in-row check. KSEI dates are report dates. Future dates are announced schedules.',
 'TRANSACTIONAL', 'One event: a corporate action or an insider movement', ARRAY['event_key'], 'annotation_date',
 'ticker', 'Saniti', true, 'BOUNDED_READ', interval '7 days', true, 'PARTIAL', 'MARKET', 'STOCK', 'IDX_EQUITY',
 ARRAY['1D'], 'Asia/Jakarta calendar date of the event (not always a trading date)', 'INFERRED', 'ACTIVITY_ONLY',
 'INFERRED');

WITH r(column_name, semantic_type, ai_allowed, aggs, filter_ok, group_ok, resample, cross_entity, description_id) AS (VALUES
 ('event_key', 'IDENTIFIER', true, ARRAY['COUNT','COUNT_DISTINCT'], true, false, NULL, NULL, 'Kunci unik kejadian.'),
 ('event_family', 'DIMENSION', true, ARRAY['COUNT','COUNT_DISTINCT'], true, true, NULL, NULL, 'Kelompok kejadian: CORPORATE_ACTION (aksi korporasi) atau INSIDER (transaksi orang dalam).'),
 ('event_type', 'DIMENSION', true, ARRAY['COUNT','COUNT_DISTINCT'], true, true, NULL, NULL, 'Jenis kejadian: dividen, stock split, rights issue, waran, RUPS, public expose, transaksi insider, dan lainnya.'),
 ('ticker', 'IDENTIFIER', true, ARRAY['COUNT','COUNT_DISTINCT'], true, true, NULL, NULL, 'Kode saham.'),
 ('instrument_code', 'IDENTIFIER', true, ARRAY['COUNT','COUNT_DISTINCT'], true, true, NULL, NULL, 'Kode waran terstruktur bila kejadian ditampilkan di saham induknya.'),
 ('annotation_date', 'TIME', true, ARRAY['COUNT','COUNT_DISTINCT','MIN','MAX'], true, true, NULL, NULL, 'Tanggal kejadian: tanggal ex, mulai perdagangan, mulai penawaran, RUPS, public expose, atau tanggal transaksi insider.'),
 ('annotation_date_role', 'DIMENSION', true, ARRAY['COUNT','COUNT_DISTINCT'], true, true, NULL, NULL, 'Arti tanggal kejadian.'),
 ('action', 'DIMENSION', true, ARRAY['COUNT','COUNT_DISTINCT'], true, true, NULL, NULL, 'Jenis transaksi insider (BUY beli, SELL jual, dan lainnya).'),
 ('holder_name', 'DIMENSION', true, ARRAY['COUNT','COUNT_DISTINCT'], true, true, NULL, NULL, 'Nama pemegang saham insider.'),
 ('holder_role', 'DIMENSION', true, ARRAY['COUNT','COUNT_DISTINCT'], true, true, NULL, NULL, 'Peran insider: direktur, komisaris, pengendali.'),
 ('holder_nationality', 'DIMENSION', true, ARRAY['COUNT','COUNT_DISTINCT'], true, true, NULL, NULL, 'Kewarganegaraan pemegang: LOCAL atau FOREIGN.'),
 ('broker_code', 'DIMENSION', true, ARRAY['COUNT','COUNT_DISTINCT'], true, true, NULL, NULL, 'Kode broker transaksi insider.'),
 ('shares_before', 'MEASURE', true, ARRAY['MIN','MAX','AVG'], true, false, NULL, NULL, 'Jumlah saham sebelum transaksi.'),
 ('shares_after', 'MEASURE', true, ARRAY['MIN','MAX','AVG'], true, false, NULL, NULL, 'Jumlah saham sesudah transaksi.'),
 ('shares_change', 'MEASURE', true, ARRAY['SUM','MIN','MAX','AVG'], true, false, 'SUM', NULL, 'Perubahan jumlah saham (+ bertambah, - berkurang).'),
 ('pct_after', 'MEASURE', true, ARRAY['MIN','MAX','AVG'], true, false, NULL, NULL, 'Persentase kepemilikan sesudah transaksi (Current %).'),
 ('pct_change', 'MEASURE', true, ARRAY['MIN','MAX','AVG'], true, false, NULL, NULL, 'Perubahan persentase kepemilikan (Change %).'),
 ('pct_quality_flag', 'DIMENSION', true, ARRAY['COUNT','COUNT_DISTINCT'], true, true, NULL, NULL, 'Hasil cek persentase dalam baris: OK, ROUNDING, INCONSISTENT, NOT_CHECKABLE, INVALID_SENTINEL.'),
 ('price', 'MEASURE', true, ARRAY['MIN','MAX','AVG'], true, false, NULL, NULL, 'Harga transaksi insider per saham.'),
 ('is_estimated_price', 'DIMENSION', true, ARRAY['COUNT'], true, true, NULL, NULL, 'TRUE bila harga adalah perkiraan Stockbit.'),
 ('value_idr', 'MEASURE', true, ARRAY['SUM','MIN','MAX','AVG'], true, false, 'SUM', 'SUM', 'Nilai transaksi insider dalam rupiah.'),
 ('data_origin', 'DIMENSION', true, ARRAY['COUNT','COUNT_DISTINCT'], true, true, NULL, NULL, 'Asal data insider: IDX (laporan insider) atau KSEI (perubahan pemegang 5 persen).'),
 ('source_payload', 'DIMENSION', false, ARRAY[]::text[], false, false, NULL, NULL, NULL),
 ('source_endpoint', 'DIMENSION', false, ARRAY[]::text[], false, false, NULL, NULL, NULL),
 ('source_fetched_at', 'TIME', false, ARRAY[]::text[], false, false, NULL, NULL, NULL),
 ('ingestion_time', 'TIME', false, ARRAY[]::text[], false, false, NULL, NULL, NULL))
INSERT INTO public."AI_column_catalog" (
    table_name, column_name, ordinal_position, description, data_type, semantic_type, unit, nullable, is_primary_key,
    source_column_or_expression, is_sensitive, ai_allowed, allowed_aggregations, filter_allowed, group_by_allowed,
    example_value, coverage_required, documentation_status, resample_aggregation, cross_entity_aggregation,
    value_time_basis, description_id, description_id_status, entity_name)
SELECT c.table_name, c.column_name, c.ordinal_position, k.definition || coalesce(' Null: ' || k.null_rule, ''),
       c.data_type, r.semantic_type, k.unit, c.is_nullable = 'YES', c.column_name = 'event_key',
       k.source_column_or_expression, false, r.ai_allowed, r.aggs, r.filter_ok, r.group_ok, NULL,
       c.column_name IN ('ticker', 'annotation_date'), 'PARTIAL', r.resample, r.cross_entity, 'HISTORICAL',
       r.description_id, CASE WHEN r.description_id IS NOT NULL THEN 'DRAFT' END, false
FROM information_schema.columns AS c
JOIN r ON r.column_name = c.column_name
JOIN public."Column_Catalog" AS k ON k.table_schema = 'public' AND k.table_name = c.table_name AND k.column_name = c.column_name
WHERE c.table_schema = 'public' AND c.table_name = 'idx_event_annotation';

UPDATE public."Table_Catalog"
SET source_code_paths = CASE WHEN 'database/migrations/20261025_015_onboard_idx_event_annotation.sql' = ANY (source_code_paths)
                             THEN source_code_paths
                             ELSE array_append(source_code_paths, 'database/migrations/20261025_015_onboard_idx_event_annotation.sql') END,
    update_rule = 'Rebuilt by refresh_idx_event_annotation() at the end of every Stockbit event load (stockbit-updater round or apps/stockbit-event-annotation job), in the same transaction.',
    updated_at = CURRENT_TIMESTAMP
WHERE table_schema = 'public' AND table_name = 'idx_event_annotation';

DO $verify$
BEGIN
    IF (SELECT count(*) FROM public."AI_column_catalog" WHERE table_name = 'idx_event_annotation') <> 26
       OR (SELECT count(*) FROM public."AI_column_catalog" WHERE table_name = 'idx_event_annotation' AND ai_allowed) <> 22 THEN
        RAISE EXCEPTION 'Expected 26 AI_column_catalog rows, 22 visible';
    END IF;
    IF NOT has_table_privilege('market_ai_sql_reader', 'public.idx_event_annotation', 'SELECT') THEN
        RAISE EXCEPTION 'market_ai_sql_reader cannot read idx_event_annotation';
    END IF;
    IF has_table_privilege('market_ai_sql_reader', 'public.stockbit_insider_transaction', 'SELECT')
       OR has_table_privilege('market_ai_sql_reader', 'public.stockbit_corporate_action', 'SELECT') THEN
        RAISE EXCEPTION 'A source table must stay hidden from the AI reader';
    END IF;
    IF EXISTS (SELECT 1 FROM public."AI_column_catalog" WHERE table_name = 'idx_event_annotation' AND ai_allowed
               AND (description IS NULL OR btrim(description) = '')) THEN
        RAISE EXCEPTION 'A visible column lacks its description';
    END IF;
END
$verify$;
COMMIT;
