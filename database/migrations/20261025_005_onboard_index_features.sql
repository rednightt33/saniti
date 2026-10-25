-- EXEC-INDEX-1 C (user 2026-10-25: "saya ada tambahkan feature 1-6 _INDEX... buat visible ke AI juga ya"; joins
-- "Sesama INDEX + ke saham per tanggal (Recommended)"; description_id "Dari Feature_Vocabulary (Recommended)"):
-- the six dedicated INDEX Feature tables (migrations 20261024_010 to 20261025_003, branch codex/ihsg-f356-one-date,
-- merged to main 2026-10-25) onboarded to the AI (NEW_TABLE_ONBOARDING_PLAN.md section 4; template 20261023_004).
--
-- Every rule is read from the catalogs, not typed per column:
-- 1. The tables are exposed directly (every row is an INDEX row; no view needed). Grants to market_ai_sql_reader and
--    market_ai_preview_owner.
-- 2. AI_table_catalog: one row per table; subject MARKET / INDEX / IDX_INDEX; freshness one day like the stock tables,
--    so a table that is not refreshed reads late (automatic daily routing is not enabled, PLAN.md INDEX).
-- 3. AI_column_catalog: description and unit from the INDEX table's own Feature_Catalog definition (index points, not
--    IDR); the structural rules (semantic type, aggregations, summary rules, filter/group, value basis, visibility)
--    from the already reviewed AI_column_catalog row of the same column of the stock counterpart (the table without
--    _INDEX, or its exposed _Stock view). A column the stock view leaves out of a base column is hidden here too (the
--    decision of 20261023_004); a column only the INDEX table has takes the 20261023_004 rules from Feature_Catalog.
--    description_id from Feature_Vocabulary (id-ID, review_status VERIFIED) as REVIEWED; Feature 04 has no vocabulary
--    entries, so its description_id stays NULL.
-- 4. AI_catalog_relationships: every active Feature_Relationship_Catalog row between two INDEX tables (EXACT_DATE on
--    the tables' time columns), and the reference joins of the stock counterpart (CURRENT_STATE / EFFECTIVE_DATED to
--    the universe and broker profile), copied onto the INDEX table. A stock-to-IHSG join on the date alone is not
--    registered: the join contract needs at least one entity key pair (Governor extract.py Restriction.pairs, orc
--    data_need.py Relationship.left_column, sandbox data_need.py entity_key_pairs); recorded in EXEC-INDEX-1.
-- 5. AI_calculation_catalog: one contract per column from the INDEX Feature_Catalog, with the counterpart's formula
--    reference ids when it has them.
-- 6. Preview for the six tables, hidden columns = the columns hidden in step 3.
-- Index acceptance: DATABASE_INDEX_ACCEPTANCE.md 2026-10-25 (every table has an index led by its time column).
-- Rollback (forward-only): is_active = false on the six AI_table_catalog rows, is_allowed = false on their
-- relationships, revoke the grants, restore the twelve-object preview function of 20261023_004.
BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '5min';

CREATE TEMP TABLE index_onboard (index_table text PRIMARY KEY, base text NOT NULL, counterpart text, time_column text NOT NULL,
                                 key text[] NOT NULL, feature_count int NOT NULL) ON COMMIT DROP;
INSERT INTO index_onboard (index_table, base, time_column, key, feature_count)
SELECT t.table_name, left(t.table_name, length(t.table_name) - 6), t.observation_date_column, t.primary_key_columns,
       (SELECT count(*) FROM public."Feature_Catalog" AS f WHERE f.feature_table = t.table_name AND f.is_active)
FROM public."Table_Catalog" AS t
WHERE t.table_schema = 'public' AND t.table_name ~ '^Feature_0[1-6]_[A-Za-z_]+_INDEX$';
-- the counterpart is the exposed stock object of the same base table
UPDATE index_onboard AS o
SET counterpart = (SELECT a.table_name FROM public."AI_table_catalog" AS a
                   WHERE a.is_active AND a.table_name IN (o.base, o.base || '_Stock') ORDER BY a.table_name = o.base DESC LIMIT 1);

DO $preflight$
BEGIN
    IF (SELECT count(*) FROM index_onboard) <> 6 THEN
        RAISE EXCEPTION 'Expected the six Feature 01-06 INDEX tables in Table_Catalog';
    END IF;
    IF EXISTS (SELECT 1 FROM index_onboard WHERE counterpart IS NULL OR time_column IS NULL) THEN
        RAISE EXCEPTION 'An INDEX table has no exposed stock counterpart or no time column';
    END IF;
    IF EXISTS (SELECT 1 FROM public."AI_table_catalog" AS a JOIN index_onboard AS o ON o.index_table = a.table_name) THEN
        RAISE EXCEPTION 'An INDEX table is already in AI_table_catalog';
    END IF;
    IF EXISTS (SELECT 1 FROM index_onboard AS o WHERE o.feature_count = 0 OR o.feature_count <>
               (SELECT count(*) FROM information_schema.columns AS c WHERE c.table_schema = 'public' AND c.table_name = o.index_table)) THEN
        RAISE EXCEPTION 'Every INDEX column needs exactly one active Feature_Catalog definition';
    END IF;
    IF (SELECT count(*) FROM pg_roles WHERE rolname IN ('market_ai_sql_reader', 'market_ai_preview_owner', 'market_ai_preview_reader')) <> 3 THEN
        RAISE EXCEPTION 'An expected AI role is missing';
    END IF;
    IF to_regclass('public."Feature_Vocabulary"') IS NULL THEN
        RAISE EXCEPTION 'Feature_Vocabulary is missing (migration 20261025_003)';
    END IF;
END
$preflight$;

-- 1. grants
DO $grant$
DECLARE
    t text;
BEGIN
    FOR t IN SELECT index_table FROM index_onboard LOOP
        EXECUTE format('REVOKE ALL ON public.%I FROM PUBLIC', t);
        EXECUTE format('GRANT SELECT ON public.%I TO market_ai_sql_reader, market_ai_preview_owner', t);
    END LOOP;
END
$grant$;

-- 2. AI_table_catalog
INSERT INTO public."AI_table_catalog" (
    table_name, description, category, grain, primary_key_columns, time_column, entity_column, owner, is_active,
    ai_access_level, freshness_sla, coverage_enabled, documentation_status, data_domain, entity_type, asset_type,
    supported_frequencies, time_semantics, subject_metadata_status, row_presence, row_presence_status)
SELECT o.index_table, d.description, 'FEATURE', t.grain, o.key, o.time_column, 'ticker', 'Saniti', true,
       'BOUNDED_READ', interval '1 day', true, 'PARTIAL', 'MARKET', 'INDEX', 'IDX_INDEX', ARRAY['1D'],
       'Asia/Jakarta exchange trading date (market sessions of the index)', 'INFERRED', 'ACTIVITY_ONLY', 'INFERRED'
FROM index_onboard AS o
JOIN public."Table_Catalog" AS t ON t.table_schema = 'public' AND t.table_name = o.index_table
JOIN (VALUES
    ('Feature_01_Stock_Daily_INDEX',
     'Daily features of the IDX Composite Index (IHSG, indeks harga saham gabungan) and any other index of the IDX universe: close level in index points, returns over 1 to 60 sessions, volatility, highest close, drawdown. Use it for kinerja IHSG, return IHSG, volatilitas IHSG, IHSG naik atau turun, and as the market benchmark beside a stock (request the stock and the index separately and align them on the date). The index has no source volume: volume and volume-based columns are NULL. Stock rows are in Feature_01_Stock_Daily. Loaded by an explicit historical bootstrap from 2018; daily updates are not automatic yet.'),
    ('Feature_02_Broker_Rolling_INDEX',
     'Market-wide broker flows behind the IDX Composite Index (IHSG): per broker, source investor type (Foreign or Domestic) and board, the buy, sell and net value and lots of all traded source symbols on the date, with rolling 5 to 60 session nets, buy and sell days and percentiles. Use it for broker terbesar di seluruh pasar, net beli broker se-market, akumulasi broker di IHSG. The aggregate covers every raw source symbol (including warrants and rights), not the official historical IHSG constituents. Broker Summary dates only (2016 to the last loaded date); refreshed manually. Per-stock rows are in Feature_02_Broker_Rolling.'),
    ('Feature_03_Stock_Broker_Daily_INDEX',
     'Market-wide daily broker structure behind the IDX Composite Index (IHSG) per board: total buy and sell value, active, net-buying and net-selling broker counts, foreign, domestic, institutional and retail net value, top buyer and seller. Use it for net asing se-market, jumlah broker aktif, dominasi broker di seluruh pasar. Covers every raw source symbol, not the official IHSG constituents; HHI concentration is NULL by policy. Broker Summary dates only, refreshed manually. Per-stock rows are in Feature_03_Stock_Broker_Daily.'),
    ('Feature_04_Technical_Indicator_INDEX',
     'Daily technical indicators of the IDX Composite Index (IHSG) calculated from its actual index close: SMA 20/50, EMA 12/26/50/200, RSI 14, MACD, ATR 14, Bollinger bands, ADX, SMI, swing-high break, inside bar and TA-Lib candlestick patterns (asset_type index). Use it for RSI IHSG, MACD IHSG, tren IHSG, golden cross IHSG. Read the stored column instead of computing the indicator again. Stock and bond rows are in Feature_04_Technical_Indicator. Loaded from 2018; daily updates are not automatic yet.'),
    ('Feature_05_Foreign_Domestic_Broker_Detail_INDEX',
     'Market-wide broker-level foreign and domestic flows behind the IDX Composite Index (IHSG): per broker, source investor type and board, the buy, sell and net value (IDR), lots and transaction frequency summed over every raw source symbol of the date. Use it for broker asing se-market, net beli asing per broker di seluruh pasar. Frequency sums the known source counts; it is NULL only when no input is known. Not the official IHSG constituents. Broker Summary dates only, refreshed manually. Per-stock rows are in Feature_05_Foreign_Domestic_Broker_Detail_Stock.'),
    ('Feature_06_Foreign_Domestic_INDEX',
     'Market-wide daily foreign and domestic flow behind the IDX Composite Index (IHSG) per board: buy, sell and net value of foreign and domestic investors, cumulative net, rolling net over 5 to 60 sessions, net-to-turnover ratios, z-scores and percentiles, foreign strength, frequency and frequency coverage. Use it for net beli asing IHSG, net jual asing se-market, aliran dana asing pasar, foreign flow IHSG. Sessions are market sessions; cumulative values include earlier balances of symbols absent on the date. Every raw source symbol, not the official IHSG constituents. Broker Summary dates only, refreshed manually. Per-stock rows are in Feature_06_Foreign_Domestic_Stock.')
) AS d(table_name, description) ON d.table_name = o.index_table;

-- 3. AI_column_catalog
INSERT INTO public."AI_column_catalog" (
    table_name, column_name, ordinal_position, description, data_type, semantic_type, unit, nullable, is_primary_key,
    source_column_or_expression, is_sensitive, ai_allowed, allowed_aggregations, filter_allowed, group_by_allowed,
    example_value, coverage_required, documentation_status, resample_aggregation, cross_entity_aggregation,
    value_time_basis, description_id, description_id_status, entity_name)
SELECT c.table_name, c.column_name, c.ordinal_position, f.definition, c.data_type,
       coalesce(s.semantic_type, CASE WHEN c.column_name = o.time_column THEN 'TIME'
                                      WHEN f.semantic_role = 'IDENTITY' THEN 'IDENTIFIER'
                                      WHEN f.semantic_role = 'DIMENSION' THEN 'DIMENSION' ELSE 'MEASURE' END),
       f.unit, c.is_nullable = 'YES', c.column_name = ANY (o.key), f.calculation, false,
       CASE WHEN s.column_name IS NOT NULL THEN s.ai_allowed
            WHEN base_column.column_name IS NOT NULL THEN false   -- left out of the stock view
            ELSE true END,
       coalesce(s.allowed_aggregations, CASE WHEN c.column_name = o.time_column THEN ARRAY['COUNT', 'COUNT_DISTINCT', 'MIN', 'MAX']
                                             ELSE f.allowed_aggregations END),
       coalesce(s.filter_allowed, f.is_filterable),
       coalesce(s.group_by_allowed, f.is_groupable OR c.column_name = ANY (o.key)),
       NULL, c.column_name IN ('ticker', o.time_column), 'PARTIAL',
       CASE WHEN s.column_name IS NOT NULL THEN s.resample_aggregation
            WHEN 'SUM' = ANY (f.allowed_aggregations) THEN 'SUM'
            WHEN f.lookback_window = 'all sessions' THEN 'LAST' END,
       CASE WHEN s.column_name IS NOT NULL THEN s.cross_entity_aggregation
            WHEN 'SUM' = ANY (f.allowed_aggregations) THEN 'SUM' END,
       coalesce(s.value_time_basis, 'HISTORICAL'),
       v.definition, CASE WHEN v.definition IS NOT NULL THEN 'REVIEWED' END,
       coalesce(s.entity_name, false)
FROM index_onboard AS o
JOIN information_schema.columns AS c ON c.table_schema = 'public' AND c.table_name = o.index_table
JOIN public."Feature_Catalog" AS f ON f.feature_table = o.index_table AND f.feature_column = c.column_name AND f.is_active
LEFT JOIN public."AI_column_catalog" AS s ON s.table_name = o.counterpart AND s.column_name = c.column_name
LEFT JOIN information_schema.columns AS base_column
       ON o.counterpart <> o.base AND base_column.table_schema = 'public' AND base_column.table_name = o.base
      AND base_column.column_name = c.column_name
LEFT JOIN public."Feature_Vocabulary" AS v
       ON v.source_schema = 'public' AND v.source_table = o.index_table AND v.column_name = c.column_name
      AND v.language_code = 'id-ID' AND v.review_status = 'VERIFIED';

-- 4. relationships
INSERT INTO public."AI_catalog_relationships" (
    left_table, left_columns, right_table, right_columns, relationship_type, temporal_rule, safe_output_grain,
    requires_preaggregation, description, version, is_allowed, supported_join_semantics, left_time_column,
    right_time_column, effective_from_column, effective_to_column)
SELECT r.left_feature_table, r.left_join_columns, r.right_feature_table, r.right_join_columns, r.relationship_type,
       'Exact trading date', r.safe_output_grain, r.requires_preaggregation,
       r.definition || ' (Feature_Relationship_Catalog ' || r.version || ')', 'v1', true, ARRAY['EXACT_DATE'],
       l.time_column, rr.time_column, NULL, NULL
FROM public."Feature_Relationship_Catalog" AS r
JOIN index_onboard AS l ON l.index_table = r.left_feature_table
JOIN index_onboard AS rr ON rr.index_table = r.right_feature_table
WHERE r.is_active;

INSERT INTO public."AI_catalog_relationships" (
    left_table, left_columns, right_table, right_columns, relationship_type, temporal_rule, safe_output_grain,
    requires_preaggregation, description, version, is_allowed, supported_join_semantics, left_time_column,
    right_time_column, effective_from_column, effective_to_column)
SELECT CASE WHEN a.left_table = o.counterpart THEN o.index_table ELSE a.left_table END, a.left_columns,
       CASE WHEN a.right_table = o.counterpart THEN o.index_table ELSE a.right_table END, a.right_columns,
       a.relationship_type, a.temporal_rule, a.safe_output_grain, a.requires_preaggregation,
       'Reference join of the INDEX table, as registered for ' || o.counterpart || ': ' || a.description,
       'v1', true, a.supported_join_semantics, a.left_time_column, a.right_time_column, a.effective_from_column,
       a.effective_to_column
FROM public."AI_catalog_relationships" AS a
JOIN index_onboard AS o ON o.counterpart IN (a.left_table, a.right_table)
WHERE a.is_allowed AND a.supported_join_semantics <@ ARRAY['CURRENT_STATE', 'EFFECTIVE_DATED']
  AND NOT EXISTS (SELECT 1 FROM index_onboard AS other
                  WHERE other.counterpart IN (a.left_table, a.right_table) AND other.counterpart <> o.counterpart);

-- 5. AI_calculation_catalog
INSERT INTO public."AI_calculation_catalog" (
    calculation_name, version, target_table, target_columns, definition, required_inputs, parameters, defaults,
    implementation_ref, alignment_rules, missing_data_policy, output_definition, validation_evidence, status)
SELECT f.feature_column, f.version, o.index_table, ARRAY[f.feature_column],
       f.definition || ' Calculation: ' || f.calculation,
       jsonb_build_object('source_tables', string_to_array(f.source_tables, ' | '),
                          'source_columns', string_to_array(f.source_columns, ' | ')),
       jsonb_build_object('lookback_window', f.lookback_window, 'minimum_history', f.minimum_history)
           || CASE WHEN s.parameters ? 'formula_reference'
                   THEN jsonb_build_object('formula_reference', s.parameters -> 'formula_reference') ELSE '{}'::jsonb END,
       '{}'::jsonb,
       t.source_code_paths || ARRAY['database/migrations/20261025_005_onboard_index_features.sql']
           || coalesce((SELECT array_agg(ref ORDER BY ref) FROM unnest(s.implementation_ref) AS ref
                        WHERE ref LIKE 'AI_formula_reference:%'), '{}'),
       f.dependency_rule, f.null_rule,
       jsonb_build_object('unit', f.unit, 'semantic_role', f.semantic_role, 'allowed_aggregations', f.allowed_aggregations,
                          'availability_rule', f.availability_rule, 'point_in_time_safe', f.point_in_time_safe,
                          'ai_allowed', col.ai_allowed),
       f.validation_evidence, 'ACTIVE'
FROM index_onboard AS o
JOIN public."Feature_Catalog" AS f ON f.feature_table = o.index_table AND f.is_active
JOIN public."Table_Catalog" AS t ON t.table_schema = 'public' AND t.table_name = o.index_table
JOIN public."AI_column_catalog" AS col ON col.table_name = o.index_table AND col.column_name = f.feature_column
LEFT JOIN public."AI_calculation_catalog" AS s
       ON s.target_table = o.counterpart AND s.calculation_name = f.feature_column AND s.status = 'ACTIVE';

-- 6. preview: the six INDEX tables added
CREATE OR REPLACE FUNCTION public.ai_preview_table_rows(p_table_name text)
 RETURNS json
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'pg_temp'
AS $function$
DECLARE
    order_clause text;
    hidden text[];
    result json;
BEGIN
    -- Each ORDER BY follows an existing index or the primary key where one exists, so LIMIT 20 needs no full sort
    -- on the large tables; Feature 04's order, the Feature 05/06 views' orders and the INDEX tables' orders (their keys and time indexes) were measured (DATABASE_CHANGELOG.md).
    order_clause := CASE p_table_name
        WHEN 'Feature_01_Stock_Daily' THEN 'date DESC, ticker DESC'
        WHEN 'Feature_02_Broker_Rolling' THEN
            'date DESC, market_board DESC, ticker DESC, broker DESC, investor_type DESC'
        WHEN 'Feature_03_Stock_Broker_Daily' THEN 'date DESC, market_board DESC, ticker DESC'
        WHEN 'IDX_Broker_Profile' THEN 'broker_code ASC'
        WHEN 'IDX_Broker_Summary' THEN
            '"Date" DESC, "Symbol" DESC, "Broker" DESC, "Investor Type" DESC, "Market Board" DESC'
        WHEN 'IDX_Stock_Universe' THEN '"Ticker" ASC'
        WHEN 'Price_Stock_Indonesia_IDX' THEN 'date DESC, ticker DESC'
        WHEN 'Price_Fixed_Income_Final' THEN 'date DESC, ticker DESC, metric_type DESC'
        WHEN 'Universe_Fixed_income' THEN 'ticker ASC, metric_type ASC'
        WHEN 'Feature_04_Technical_Indicator' THEN 'trade_date DESC, asset_type DESC, ticker DESC'
        WHEN 'Feature_05_Foreign_Domestic_Broker_Detail_Stock' THEN
            'trade_date DESC, ticker DESC, broker DESC, investor_type DESC, market_board DESC'
        WHEN 'Feature_06_Foreign_Domestic_Stock' THEN 'trade_date DESC, market_board DESC, ticker DESC'
        WHEN 'Feature_01_Stock_Daily_INDEX' THEN 'date DESC, ticker DESC'
        WHEN 'Feature_02_Broker_Rolling_INDEX' THEN
            'date DESC, market_board DESC, ticker DESC, broker DESC, investor_type DESC'
        WHEN 'Feature_03_Stock_Broker_Daily_INDEX' THEN 'date DESC, market_board DESC, ticker DESC'
        WHEN 'Feature_04_Technical_Indicator_INDEX' THEN 'trade_date DESC, asset_type DESC, ticker DESC'
        WHEN 'Feature_05_Foreign_Domestic_Broker_Detail_INDEX' THEN
            'trade_date DESC, ticker DESC, broker DESC, investor_type DESC, market_board DESC'
        WHEN 'Feature_06_Foreign_Domestic_INDEX' THEN 'trade_date DESC, market_board DESC, ticker DESC'
        ELSE NULL
    END;
    IF order_clause IS NULL THEN
        RAISE EXCEPTION 'Table is not approved for preview' USING ERRCODE = 'insufficient_privilege';
    END IF;
    -- the columns AI_column_catalog hides (20261025_005 DRYRUN job db778889 listed them)
    hidden := CASE p_table_name
        WHEN 'Feature_04_Technical_Indicator' THEN ARRAY['tracking_high', 'tracking_low', 'temp_high',
            'temp_high_bar', 'temp_low', 'temp_low_bar', 'calculation_version', 'calculated_at']
        WHEN 'Feature_04_Technical_Indicator_INDEX' THEN ARRAY['tracking_high', 'tracking_low', 'temp_high',
            'temp_high_bar', 'temp_low', 'temp_low_bar', 'calculation_version', 'calculated_at']
        WHEN 'Feature_05_Foreign_Domestic_Broker_Detail_INDEX' THEN ARRAY['calculated_at']
        WHEN 'Feature_06_Foreign_Domestic_INDEX' THEN ARRAY['calculated_at']
        ELSE ARRAY[]::text[]
    END;

    EXECUTE format(
        $query$
        SELECT json_build_object(
            'table_name', %1$L,
            'order_by', %2$L,
            'row_limit', 20,
            'columns', (
                SELECT json_agg(json_build_object(
                           'name', a.attname,
                           'type', format_type(a.atttypid, a.atttypmod),
                           'nullable', NOT a.attnotnull) ORDER BY a.attnum)
                FROM pg_catalog.pg_attribute AS a
                WHERE a.attrelid = %3$L::regclass AND a.attnum > 0 AND NOT a.attisdropped
                  AND NOT (a.attname::text = ANY (%4$L::text[]))
            ),
            'rows', COALESCE((
                SELECT json_agg(CASE WHEN cardinality(%4$L::text[]) = 0 THEN to_json(sample)
                                     ELSE (to_jsonb(sample) - %4$L::text[])::json END ORDER BY %2$s)
                FROM (SELECT * FROM public.%1$I ORDER BY %2$s LIMIT 20) AS sample
            ), '[]'::json)
        )
        $query$,
        p_table_name, order_clause, format('public.%I', p_table_name), hidden
    ) INTO result;
    RETURN result;
END
$function$;

COMMENT ON FUNCTION public.ai_preview_table_rows(text) IS
    'market-ai-orc preview: at most 20 rows in a fixed order from eighteen approved market-data objects (Feature 04 and the INDEX tables without their hidden columns); EXECUTE only via market_ai_preview_reader.';

-- 7. Table_Catalog: the migration path on the touched rows
UPDATE public."Table_Catalog"
SET source_code_paths = source_code_paths || ARRAY['database/migrations/20261025_005_onboard_index_features.sql']
WHERE table_schema = 'public'
  AND (table_name IN (SELECT index_table FROM index_onboard)
       OR table_name IN ('AI_table_catalog', 'AI_column_catalog', 'AI_catalog_relationships', 'AI_calculation_catalog'))
  AND NOT ('database/migrations/20261025_005_onboard_index_features.sql' = ANY (source_code_paths));

DO $verify$
BEGIN
    IF (SELECT count(*) FROM public."AI_table_catalog" AS a JOIN index_onboard AS o ON o.index_table = a.table_name
        WHERE a.is_active AND a.ai_access_level = 'BOUNDED_READ') <> 6 THEN
        RAISE EXCEPTION 'The six INDEX tables are not active in AI_table_catalog';
    END IF;
    IF (SELECT count(*) FROM public."AI_column_catalog" AS a JOIN index_onboard AS o ON o.index_table = a.table_name)
       <> (SELECT sum(feature_count) FROM index_onboard) THEN
        RAISE EXCEPTION 'AI_column_catalog does not hold every INDEX column';
    END IF;
    IF EXISTS (SELECT 1 FROM public."AI_column_catalog" AS a JOIN index_onboard AS o ON o.index_table = a.table_name
               WHERE a.ai_allowed AND (a.description IS NULL OR btrim(a.description) = '' OR a.unit IS NULL)) THEN
        RAISE EXCEPTION 'An exposed INDEX column lacks its description or unit';
    END IF;
    IF EXISTS (SELECT 1 FROM public."AI_column_catalog" AS a JOIN index_onboard AS o ON o.index_table = a.table_name
               WHERE a.column_name IN ('ticker', o.time_column) AND NOT a.ai_allowed) THEN
        RAISE EXCEPTION 'An entity or time column of an INDEX table is hidden';
    END IF;
    IF (SELECT count(*) FROM public."AI_calculation_catalog" AS k JOIN index_onboard AS o ON o.index_table = k.target_table
        WHERE k.status = 'ACTIVE') <> (SELECT sum(feature_count) FROM index_onboard) THEN
        RAISE EXCEPTION 'AI_calculation_catalog does not hold one contract per INDEX column';
    END IF;
    IF EXISTS (SELECT 1 FROM public."AI_calculation_catalog" AS k, unnest(k.implementation_ref) AS ref
               WHERE k.target_table IN (SELECT index_table FROM index_onboard) AND ref LIKE 'AI_formula_reference:%'
                 AND NOT EXISTS (SELECT 1 FROM public."AI_formula_reference" AS f WHERE 'AI_formula_reference:' || f.calculation_id = ref)) THEN
        RAISE EXCEPTION 'A formula reference names a missing AI_formula_reference row';
    END IF;
    IF EXISTS (SELECT 1 FROM public."AI_catalog_relationships" AS r,
                    LATERAL (SELECT r.left_table AS t, unnest(r.left_columns) AS col
                             UNION ALL SELECT r.right_table, unnest(r.right_columns)) AS k
               WHERE (r.left_table IN (SELECT index_table FROM index_onboard) OR r.right_table IN (SELECT index_table FROM index_onboard))
                 AND NOT EXISTS (SELECT 1 FROM public."AI_column_catalog" AS c
                                 WHERE c.table_name = k.t AND c.column_name = k.col AND c.ai_allowed)) THEN
        RAISE EXCEPTION 'A relationship key column is not an exposed AI catalog column';
    END IF;
    IF EXISTS (SELECT 1 FROM public."AI_catalog_relationships" AS r
               WHERE r.left_table IN (SELECT index_table FROM index_onboard) AND r.right_table IN (SELECT index_table FROM index_onboard)
                 AND NOT (r.left_time_column = ANY (r.left_columns) AND r.right_time_column = ANY (r.right_columns))) THEN
        RAISE EXCEPTION 'An INDEX-to-INDEX relationship does not pair the time columns';
    END IF;
    IF EXISTS (SELECT 1 FROM index_onboard AS o, public."AI_column_catalog" AS c
               WHERE c.table_name = o.index_table AND NOT c.ai_allowed
                 AND public.ai_preview_table_rows(o.index_table)::jsonb -> 'rows' -> 0 ? c.column_name) THEN
        RAISE EXCEPTION 'The preview shows a column AI_column_catalog hides';
    END IF;
    IF EXISTS (SELECT 1 FROM index_onboard AS o
               WHERE NOT has_table_privilege('market_ai_sql_reader', format('public.%I', o.index_table), 'SELECT')
                  OR has_table_privilege('market_ai_sql_reader', format('public.%I', o.index_table), 'INSERT,UPDATE,DELETE,TRUNCATE')
                  OR has_table_privilege('market_ai_preview_reader', format('public.%I', o.index_table), 'SELECT')) THEN
        RAISE EXCEPTION 'Unexpected privileges on an INDEX table';
    END IF;
END
$verify$;

COMMIT;
