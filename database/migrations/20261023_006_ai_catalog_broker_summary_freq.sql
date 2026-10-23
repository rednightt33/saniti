-- IDX_Broker_Summary buy_freq / sell_freq visible to the AI (user 2026-10-23: "apakah data buy freq dan sell freq di
-- table idx broker summary sudah visible ke AI?" -> not yet -> "Boleh").
-- The columns exist since EXEC-F05-F06 Phase 1 (bigint, NULL for symbols without frequency: warrants and rights) and
-- have Column_Catalog definitions; the reader role already reads them (has_column_privilege, job 812c0e18). Only the
-- AI_column_catalog rows were missing (job 812c0e18). Shape copied from the table's own measure rows ("Buy Lots":
-- SUM over time and across entities, HISTORICAL); unit from the same column of the Feature 05 stock view; meaning from
-- Column_Catalog. Rollback: DELETE these two rows (a forward migration).
BEGIN;
SET LOCAL lock_timeout = '10s';

DO $preflight$
BEGIN
    IF (SELECT count(*) FROM public."Column_Catalog"
        WHERE table_name = 'IDX_Broker_Summary' AND column_name IN ('buy_freq', 'sell_freq')) <> 2 THEN
        RAISE EXCEPTION 'Column_Catalog must define IDX_Broker_Summary buy_freq and sell_freq';
    END IF;
    IF EXISTS (SELECT 1 FROM public."AI_column_catalog"
               WHERE table_name = 'IDX_Broker_Summary' AND column_name IN ('buy_freq', 'sell_freq')) THEN
        RAISE EXCEPTION 'IDX_Broker_Summary buy_freq / sell_freq are already in AI_column_catalog';
    END IF;
    IF (SELECT count(*) FROM public."AI_column_catalog"
        WHERE table_name = 'Feature_05_Foreign_Domestic_Broker_Detail_Stock' AND column_name IN ('buy_freq', 'sell_freq')) <> 2 THEN
        RAISE EXCEPTION 'The Feature 05 stock view rows for buy_freq / sell_freq are missing';
    END IF;
END
$preflight$;

INSERT INTO public."AI_column_catalog" (
    table_name, column_name, ordinal_position, description, data_type, semantic_type, unit, nullable, is_primary_key,
    source_column_or_expression, is_sensitive, ai_allowed, allowed_aggregations, filter_allowed, group_by_allowed,
    example_value, coverage_required, documentation_status, resample_aggregation, cross_entity_aggregation,
    value_time_basis, description_id, description_id_status, entity_name)
SELECT 'IDX_Broker_Summary', c.column_name, a.attnum,
       c.definition || ' NULL for symbols without frequency in the source (warrants, rights).',
       format_type(a.atttypid, a.atttypmod), 'MEASURE', f.unit, true, false,
       NULL, false, true, ARRAY['SUM', 'AVG', 'MIN', 'MAX'], true, false,
       NULL, false, 'PARTIAL', 'SUM', 'SUM',
       'HISTORICAL', NULL, NULL, false
FROM public."Column_Catalog" AS c
JOIN pg_catalog.pg_attribute AS a
  ON a.attrelid = 'public."IDX_Broker_Summary"'::regclass AND a.attname = c.column_name AND NOT a.attisdropped
JOIN public."AI_column_catalog" AS f
  ON f.table_name = 'Feature_05_Foreign_Domestic_Broker_Detail_Stock' AND f.column_name = c.column_name
WHERE c.table_name = 'IDX_Broker_Summary' AND c.column_name IN ('buy_freq', 'sell_freq');

DO $verify$
BEGIN
    IF (SELECT count(*) FROM public."AI_column_catalog"
        WHERE table_name = 'IDX_Broker_Summary' AND column_name IN ('buy_freq', 'sell_freq')
          AND ai_allowed AND NOT is_sensitive) <> 2 THEN
        RAISE EXCEPTION 'expected two visible AI_column_catalog rows';
    END IF;
END
$verify$;

COMMIT;
