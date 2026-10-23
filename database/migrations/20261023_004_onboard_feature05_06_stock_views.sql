-- EXEC-M204 step 5 (user 2026-10-23): Feature 05 and Feature 06 onboarded to the AI through two views of IDX stocks
-- (NEW_TABLE_ONBOARDING_PLAN.md section 4; template 20261020_001). Decisions (EXEC.md EXEC-M204, user 2026-10-23):
-- "1. tidak usah, khusus saham saja for now. Jadi dibuat view"; list "Daftar saham sekarang (Recommended)"; "1 aja"
-- (F02/F03 unchanged); 2-10 "ok"; 11 (Indonesian meanings) "nanti saja".
--
-- 1. Views Feature_05_Foreign_Domestic_Broker_Detail_Stock and Feature_06_Foreign_Domestic_Stock: the rows of the current
--    IDX stock universe ("Security Type" = 'stock', read from IDX_Stock_Universe, not a code list), every column
--    except calculated_at (bookkeeping). source_balance_gap is shown (decision 2). The base tables stay hidden from the
--    AI (no catalog has a row filter). Live 2026-10-23: 844 of 4,125 codes; the other codes are warrants and rights
--    (3,058), ETFs (62) and delisted or suspended stocks (about 161), which the views leave out (survivorship: recorded).
-- 2. AI_table_catalog, AI_column_catalog (from the active Feature_Catalog definitions; summary rules derived from them:
--    a column whose allowed_aggregations hold SUM (the one-session flows) sums over time and across entities, a
--    cumulative column (lookback 'all sessions') takes its LAST value over time and is not summed across entities,
--    every other column has no summary rule), AI_calculation_catalog (one per column, with the AI_formula_reference ids
--    a column implements), 11 relationships, preview, Table_Catalog / Column_Catalog for the views.
-- 3. Indonesian meanings (description_id) are left NULL (decision 11, later).
-- Index acceptance: Feature 05 / 06 PASS on every pattern (DATABASE_INDEX_ACCEPTANCE.md 2026-10-23); the views read
-- the base indexes (the Governor follows a view to its base columns, M205).
-- Rollback (forward-only): is_active = false on the two AI_table_catalog rows, is_allowed = false on their
-- relationships, revoke the grants, restore the ten-object preview function.
BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '5min';

DO $preflight$
BEGIN
    IF to_regclass('public."Feature_05_Foreign_Domestic_Broker_Detail_Stock"') IS NOT NULL OR to_regclass('public."Feature_06_Foreign_Domestic_Stock"') IS NOT NULL THEN
        RAISE EXCEPTION 'A Feature 05/06 view already exists';
    END IF;
    IF EXISTS (SELECT 1 FROM public."AI_table_catalog" WHERE table_name IN ('Feature_05_Foreign_Domestic_Broker_Detail_Stock', 'Feature_06_Foreign_Domestic_Stock', 'Feature_05_Foreign_Domestic_Broker_Detail', 'Feature_06_Foreign_Domestic')) THEN
        RAISE EXCEPTION 'Feature 05/06 are already in AI_table_catalog';
    END IF;
    IF (SELECT count(*) FROM public."Feature_Catalog" WHERE feature_table = 'Feature_05_Foreign_Domestic_Broker_Detail' AND is_active) <> 15
       OR (SELECT count(*) FROM public."Feature_Catalog" WHERE feature_table = 'Feature_06_Foreign_Domestic' AND is_active) <> 87 THEN
        RAISE EXCEPTION 'Expected 15 and 87 active Feature_Catalog definitions';
    END IF;
    IF (SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'Feature_05_Foreign_Domestic_Broker_Detail') <> 15
       OR (SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'Feature_06_Foreign_Domestic') <> 87 THEN
        RAISE EXCEPTION 'Unexpected Feature 05/06 column counts';
    END IF;
    IF (SELECT count(*) FROM pg_roles WHERE rolname IN ('market_ai_sql_reader', 'market_ai_preview_owner',
                                                        'market_ai_preview_reader')) <> 3 THEN
        RAISE EXCEPTION 'An expected AI role is missing';
    END IF;
    IF (SELECT count(*) FROM public."AI_formula_reference" WHERE calculation_id IN ('CALC_080', 'CALC_131', 'CALC_136', 'CALC_137', 'CALC_138', 'CALC_139')) <> 6 THEN
        RAISE EXCEPTION 'Expected the 6 referenced AI_formula_reference rows';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM public."IDX_Stock_Universe" WHERE "Security Type" = 'stock') THEN
        RAISE EXCEPTION 'IDX_Stock_Universe has no stock row';
    END IF;
END
$preflight$;

-- 1. the views
CREATE VIEW public."Feature_05_Foreign_Domestic_Broker_Detail_Stock" AS
SELECT f.trade_date,
       f.ticker,
       f.broker,
       f.market_board,
       f.investor_type,
       f.buy_value,
       f.sell_value,
       f.net_value,
       f.buy_lots,
       f.sell_lots,
       f.net_lots,
       f.buy_freq,
       f.sell_freq,
       f.source_balance_gap
FROM public."Feature_05_Foreign_Domestic_Broker_Detail" AS f
WHERE f.ticker IN (SELECT u."Ticker" FROM public."IDX_Stock_Universe" AS u WHERE u."Security Type" = 'stock');

CREATE VIEW public."Feature_06_Foreign_Domestic_Stock" AS
SELECT f.trade_date,
       f.ticker,
       f.market_board,
       f.foreign_buy_1d,
       f.foreign_sell_1d,
       f.foreign_net_1d,
       f.domestic_buy_1d,
       f.domestic_sell_1d,
       f.domestic_net_1d,
       f.foreign_cumulative_net,
       f.domestic_cumulative_net,
       f.foreign_net_5d,
       f.foreign_net_10d,
       f.foreign_net_20d,
       f.foreign_net_40d,
       f.foreign_net_60d,
       f.domestic_net_5d,
       f.domestic_net_10d,
       f.domestic_net_20d,
       f.domestic_net_60d,
       f.foreign_net_turnover_ratio_1d,
       f.foreign_net_turnover_ratio_5d,
       f.foreign_net_turnover_ratio_20d,
       f.foreign_buy_share_1d,
       f.foreign_sell_share_1d,
       f.foreign_buy_days_5d,
       f.foreign_buy_days_10d,
       f.foreign_buy_days_20d,
       f.foreign_buy_days_40d,
       f.foreign_sell_days_5d,
       f.foreign_sell_days_10d,
       f.foreign_sell_days_20d,
       f.foreign_sell_days_40d,
       f.foreign_net_zscore_5d_base252d,
       f.foreign_net_zscore_10d_base252d,
       f.foreign_net_zscore_20d_base252d,
       f.foreign_net_zscore_40d_base252d,
       f.foreign_net_zscore_60d_base252d,
       f.foreign_net_percentile_5d_base252d,
       f.foreign_net_percentile_10d_base252d,
       f.foreign_net_percentile_20d_base252d,
       f.foreign_net_percentile_40d_base252d,
       f.foreign_net_percentile_60d_base252d,
       f.foreign_net_zscore_5d_base60d,
       f.foreign_net_zscore_10d_base60d,
       f.foreign_net_zscore_20d_base60d,
       f.foreign_net_percentile_5d_base60d,
       f.foreign_net_percentile_10d_base60d,
       f.foreign_net_percentile_20d_base60d,
       f.foreign_flow_vs_prev_20d,
       f.foreign_flow_vs_prev_40d,
       f.foreign_strength_20d,
       f.foreign_strength_50d,
       f.foreign_strength_momentum_5d,
       f.foreign_buy_freq_1d,
       f.foreign_sell_freq_1d,
       f.domestic_buy_freq_1d,
       f.domestic_sell_freq_1d,
       f.foreign_freq_imbalance_1d,
       f.foreign_freq_imbalance_20d,
       f.foreign_buy_freq_share_1d,
       f.foreign_sell_freq_share_1d,
       f.foreign_avg_buy_value_per_freq_1d,
       f.foreign_avg_sell_value_per_freq_1d,
       f.foreign_buy_sell_ticket_ratio_1d,
       f.foreign_avg_buy_lots_per_freq_1d,
       f.foreign_avg_sell_lots_per_freq_1d,
       f.domestic_freq_imbalance_1d,
       f.domestic_freq_imbalance_20d,
       f.domestic_buy_freq_share_1d,
       f.domestic_sell_freq_share_1d,
       f.domestic_avg_buy_value_per_freq_1d,
       f.domestic_avg_sell_value_per_freq_1d,
       f.domestic_buy_sell_ticket_ratio_1d,
       f.domestic_avg_buy_lots_per_freq_1d,
       f.domestic_avg_sell_lots_per_freq_1d,
       f.domestic_buy_freq_share_change_5d_vs_prev20d,
       f.foreign_buy_freq_share_change_5d_vs_prev20d,
       f.domestic_buy_value_per_freq_change_5d_vs_prev20d,
       f.foreign_buy_value_per_freq_change_5d_vs_prev20d,
       f.domestic_sell_freq_share_change_5d_vs_prev20d,
       f.foreign_sell_freq_share_change_5d_vs_prev20d,
       f.domestic_sell_value_per_freq_change_5d_vs_prev20d,
       f.foreign_sell_value_per_freq_change_5d_vs_prev20d,
       f.foreign_value_freq_sign_mismatch_1d,
       f.source_balance_gap
FROM public."Feature_06_Foreign_Domestic" AS f
WHERE f.ticker IN (SELECT u."Ticker" FROM public."IDX_Stock_Universe" AS u WHERE u."Security Type" = 'stock');

COMMENT ON VIEW public."Feature_05_Foreign_Domestic_Broker_Detail_Stock" IS
    'Feature 05 rows of the current IDX stock universe (Security Type stock), without calculated_at. The object exposed to the AI (EXEC-M204).';
COMMENT ON VIEW public."Feature_06_Foreign_Domestic_Stock" IS
    'Feature 06 rows of the current IDX stock universe (Security Type stock), without calculated_at. The object exposed to the AI (EXEC-M204).';

REVOKE ALL ON public."Feature_05_Foreign_Domestic_Broker_Detail_Stock", public."Feature_06_Foreign_Domestic_Stock" FROM PUBLIC;
GRANT SELECT ON public."Feature_05_Foreign_Domestic_Broker_Detail_Stock", public."Feature_06_Foreign_Domestic_Stock" TO market_ai_sql_reader, market_ai_preview_owner;
DO $grant$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pgweb_reader') THEN
        GRANT SELECT ON public."Feature_05_Foreign_Domestic_Broker_Detail_Stock", public."Feature_06_Foreign_Domestic_Stock" TO pgweb_reader;
    END IF;
END
$grant$;

-- 2. AI_table_catalog
INSERT INTO public."AI_table_catalog" (
    table_name, description, category, grain, primary_key_columns, time_column, entity_column, owner, is_active,
    ai_access_level, freshness_sla, coverage_enabled, documentation_status, data_domain, entity_type, asset_type,
    supported_frequencies, time_semantics, subject_metadata_status, row_presence, row_presence_status)
VALUES
    ('Feature_05_Foreign_Domestic_Broker_Detail_Stock',
     'Broker-level daily foreign and domestic flows of IDX stocks: buy, sell and net value (IDR), lots and transaction frequency per stock, broker, source investor type (Foreign or Domestic) and board (Regular, Nego, Tunai). Use it for broker asing, net beli asing per broker, aliran dana asing dan domestik per broker, which brokers bought or sold a stock. Stocks of the current IDX stock universe only (no warrants, rights or ETFs; delisted stocks are not in it); Feature_02_Broker_Rolling and Feature_03_Stock_Broker_Daily keep every traded code. 2016 to the last refreshed Broker Summary date, refreshed manually. investor_type is the source investor identity, not the broker''s domicile. source_balance_gap marks rows from 2016 to August 2020 whose source lacks some brokers, so foreign and domestic nets do not offset there.',
     'FEATURE', 'One row per IDX stock, broker, source investor type, market board and trading date',
     ARRAY['ticker', 'trade_date', 'broker', 'investor_type', 'market_board'], 'trade_date', 'ticker', 'Saniti', true,
     'BOUNDED_READ', interval '1 day', true, 'PARTIAL', 'MARKET', 'STOCK', 'IDX_EQUITY', ARRAY['1D'],
     'Asia/Jakarta exchange trading date', 'INFERRED', 'ACTIVITY_ONLY', 'INFERRED'),
    ('Feature_06_Foreign_Domestic_Stock',
     'Stock-level daily foreign and domestic flow per IDX stock and board: buy, sell and net value of foreign and domestic investors, cumulative net, rolling net over 5 to 60 sessions, net-to-turnover ratios, buy and sell days, z-scores and midrank percentiles of the rolling foreign net against the previous 252 and 60 sessions, foreign strength, transaction frequency and ticket size. Use it for net beli asing, net jual asing, aliran dana asing (foreign flow), akumulasi asing, foreign flow persistence and unusual foreign flow. Read the stored column instead of recomputing a rolling sum, z-score or percentile. Stocks of the current IDX stock universe only (no warrants, rights or ETFs; delisted stocks are not in it); Feature_03_Stock_Broker_Daily keeps every traded code. Sessions are the ticker''s own trading sessions (Feature 02 definition). 2016 to the last refreshed Broker Summary date, refreshed manually. source_balance_gap marks 2016 to August 2020 rows whose source lacks some brokers.',
     'FEATURE', 'One row per IDX stock, market board and trading session date',
     ARRAY['ticker', 'market_board', 'trade_date'], 'trade_date', 'ticker', 'Saniti', true,
     'BOUNDED_READ', interval '1 day', true, 'PARTIAL', 'MARKET', 'STOCK', 'IDX_EQUITY', ARRAY['1D'],
     'Asia/Jakarta exchange trading date (the ticker''s own trading sessions)', 'INFERRED', 'ACTIVITY_ONLY', 'INFERRED');

-- 3. AI_column_catalog from the active Feature_Catalog definitions of the base tables (view columns only)
INSERT INTO public."AI_column_catalog" (
    table_name, column_name, ordinal_position, description, data_type, semantic_type, unit, nullable, is_primary_key,
    source_column_or_expression, is_sensitive, ai_allowed, allowed_aggregations, filter_allowed, group_by_allowed,
    example_value, coverage_required, documentation_status, resample_aggregation, cross_entity_aggregation,
    value_time_basis, description_id, description_id_status, entity_name)
SELECT v.table_name, v.column_name, v.ordinal_position,
       f.definition || CASE WHEN v.column_name = 'source_balance_gap'
           THEN ' True on 2016 to August 2020 rows whose source lacks some brokers (ERRORS M157): foreign and domestic nets do not offset there; filter it out or name it when such rows are used.'
           ELSE '' END,
       v.data_type,
       CASE WHEN v.column_name = 'trade_date' THEN 'TIME'
            WHEN f.semantic_role = 'IDENTITY' THEN 'IDENTIFIER'
            WHEN f.semantic_role = 'DIMENSION' THEN 'DIMENSION' ELSE 'MEASURE' END,
       f.unit, v.is_nullable = 'YES', v.column_name = ANY (k.key), f.calculation, false, true,
       CASE WHEN v.column_name = 'trade_date' THEN ARRAY['COUNT', 'COUNT_DISTINCT', 'MIN', 'MAX']
            ELSE f.allowed_aggregations END,
       f.is_filterable, f.is_groupable OR v.column_name = ANY (k.key), NULL,
       v.column_name IN ('ticker', 'trade_date'), 'PARTIAL',
       CASE WHEN 'SUM' = ANY (f.allowed_aggregations) THEN 'SUM'
            WHEN f.lookback_window = 'all sessions' THEN 'LAST' END,
       CASE WHEN 'SUM' = ANY (f.allowed_aggregations) THEN 'SUM' END,
       'HISTORICAL', NULL, NULL, false
FROM information_schema.columns AS v
JOIN (VALUES ('Feature_05_Foreign_Domestic_Broker_Detail_Stock', 'Feature_05_Foreign_Domestic_Broker_Detail', ARRAY['ticker', 'trade_date', 'broker', 'investor_type', 'market_board']),
             ('Feature_06_Foreign_Domestic_Stock', 'Feature_06_Foreign_Domestic', ARRAY['ticker', 'market_board', 'trade_date'])) AS k(view_name, base, key)
  ON k.view_name = v.table_name
JOIN public."Feature_Catalog" AS f
  ON f.feature_table = k.base AND f.feature_column = v.column_name AND f.is_active
WHERE v.table_schema = 'public' AND v.table_name IN ('Feature_05_Foreign_Domestic_Broker_Detail_Stock', 'Feature_06_Foreign_Domestic_Stock');

-- 4. relationships
INSERT INTO public."AI_catalog_relationships" (
    left_table, left_columns, right_table, right_columns, relationship_type, temporal_rule, safe_output_grain,
    requires_preaggregation, description, version, is_allowed, supported_join_semantics, left_time_column,
    right_time_column, effective_from_column, effective_to_column)
VALUES
    ('Feature_05_Foreign_Domestic_Broker_Detail_Stock', ARRAY['ticker', 'market_board', 'trade_date'], 'Feature_06_Foreign_Domestic_Stock', ARRAY['ticker', 'market_board', 'trade_date'], 'MANY_TO_ONE', 'Exact trading date and market board', 'trade_date x ticker x broker x investor_type x market_board', false,
     'Broker-level rows of a stock and board joined to its stock-level foreign/domestic row of the same date (Feature_Relationship_Catalog F05 -> F06); stock values repeat per broker and investor type: aggregate Feature 05 to ticker, board and date before a stock-level result.',
     'v1', true, ARRAY['EXACT_DATE'], 'trade_date', 'trade_date', NULL, NULL),
    ('IDX_Stock_Universe', ARRAY['Ticker'], 'Feature_05_Foreign_Domestic_Broker_Detail_Stock', ARRAY['ticker'], 'ONE_TO_MANY', 'Current-state reference metadata', 'trade_date x ticker x broker x investor_type x market_board', false,
     'Current stock-universe classification joined to broker-level foreign/domestic flows, so a sector or industry scope restricts Feature 05 by ticker. Current state, not point in time.',
     'v1', true, ARRAY['CURRENT_STATE'], NULL, NULL, NULL, NULL),
    ('IDX_Stock_Universe', ARRAY['Ticker'], 'Feature_06_Foreign_Domestic_Stock', ARRAY['ticker'], 'ONE_TO_MANY', 'Current-state reference metadata', 'trade_date x ticker x market_board', false,
     'Current stock-universe classification joined to stock-level foreign/domestic flows, so a sector or industry scope restricts Feature 06 by ticker. Boards stay separate rows. Current state, not point in time.',
     'v1', true, ARRAY['CURRENT_STATE'], NULL, NULL, NULL, NULL),
    ('Feature_05_Foreign_Domestic_Broker_Detail_Stock', ARRAY['ticker'], 'IDX_Stock_Universe_History', ARRAY['Ticker'], 'MANY_TO_ONE', 'Point in time: the version in effect and already recorded on the observation date', 'trade_date x ticker x broker x investor_type x market_board', false,
     'Broker-level foreign/domestic flows joined to the stock classification recorded before each date (point in time).',
     'v1', true, ARRAY['EFFECTIVE_DATED'], NULL, NULL, 'pit_valid_from', 'pit_valid_to'),
    ('Feature_06_Foreign_Domestic_Stock', ARRAY['ticker'], 'IDX_Stock_Universe_History', ARRAY['Ticker'], 'MANY_TO_ONE', 'Point in time: the version in effect and already recorded on the observation date', 'trade_date x ticker x market_board', false,
     'Stock-level foreign/domestic flows joined to the stock classification recorded before each date (point in time); boards stay separate rows.',
     'v1', true, ARRAY['EFFECTIVE_DATED'], NULL, NULL, 'pit_valid_from', 'pit_valid_to'),
    ('IDX_Broker_Profile', ARRAY['broker_code'], 'Feature_05_Foreign_Domestic_Broker_Detail_Stock', ARRAY['broker'], 'ONE_TO_MANY', 'Current-state broker metadata', 'trade_date x ticker x broker x investor_type x market_board', false,
     'Current broker identity, domestic/foreign broker type and usage classification joined to broker-level flows. broker_type is the broker domicile; investor_type in Feature 05 is the source investor. Current state, not point in time.',
     'v1', true, ARRAY['CURRENT_STATE'], NULL, NULL, NULL, NULL),
    ('Feature_05_Foreign_Domestic_Broker_Detail_Stock', ARRAY['broker'], 'IDX_Broker_Profile_History', ARRAY['broker_code'], 'MANY_TO_ONE', 'Point in time: the version in effect and already recorded on the observation date', 'trade_date x ticker x broker x investor_type x market_board', false,
     'Broker-level flows joined to the broker profile recorded before each date (point in time).',
     'v1', true, ARRAY['EFFECTIVE_DATED'], NULL, NULL, 'pit_valid_from', 'pit_valid_to'),
    ('Price_Stock_Indonesia_IDX', ARRAY['ticker', 'date'], 'Feature_05_Foreign_Domestic_Broker_Detail_Stock', ARRAY['ticker', 'trade_date'], 'ONE_TO_MANY', 'Exact trading date', 'trade_date x ticker x broker x investor_type x market_board; price values repeat per row', false,
     'Price candle of the same stock and trading date joined to broker-level flows (price repeats per broker, investor type and board); aggregate Feature 05 to ticker and date before a ticker-date result.',
     'v1', true, ARRAY['EXACT_DATE'], 'date', 'trade_date', NULL, NULL),
    ('Price_Stock_Indonesia_IDX', ARRAY['ticker', 'date'], 'Feature_06_Foreign_Domestic_Stock', ARRAY['ticker', 'trade_date'], 'ONE_TO_MANY', 'Exact trading date', 'trade_date x ticker x market_board; price values repeat per board', false,
     'Price candle of the same stock and trading date joined to stock-level foreign/domestic flows (one row per board): filter market_board before a ticker-date result.',
     'v1', true, ARRAY['EXACT_DATE'], 'date', 'trade_date', NULL, NULL),
    ('Feature_01_Stock_Daily', ARRAY['ticker', 'date'], 'Feature_05_Foreign_Domestic_Broker_Detail_Stock', ARRAY['ticker', 'trade_date'], 'ONE_TO_MANY', 'Exact trading date', 'trade_date x ticker x broker x investor_type x market_board; Feature 01 values repeat per row', false,
     'Daily stock features joined to broker-level flows; aggregate Feature 05 to ticker and date before a ticker-date result.',
     'v1', true, ARRAY['EXACT_DATE'], 'date', 'trade_date', NULL, NULL),
    ('Feature_01_Stock_Daily', ARRAY['ticker', 'date'], 'Feature_06_Foreign_Domestic_Stock', ARRAY['ticker', 'trade_date'], 'ONE_TO_MANY', 'Exact trading date', 'trade_date x ticker x market_board; Feature 01 values repeat per board', false,
     'Daily stock features joined to stock-level foreign/domestic flows (one row per board): filter market_board before a ticker-date result.',
     'v1', true, ARRAY['EXACT_DATE'], 'date', 'trade_date', NULL, NULL);

-- 5. AI_calculation_catalog: one contract per exposed column (the 20261020_001 pattern), targeting the view
INSERT INTO public."AI_calculation_catalog" (
    calculation_name, version, target_table, target_columns, definition,
    required_inputs, parameters, defaults, implementation_ref,
    alignment_rules, missing_data_policy, output_definition,
    validation_evidence, status
)
SELECT
    feature.feature_column,
    feature.version,
    k.view_name,
    ARRAY[feature.feature_column],
    feature.definition || ' Calculation: ' || feature.calculation,
    jsonb_build_object(
        'source_tables', string_to_array(feature.source_tables, ' | '),
        'source_columns', string_to_array(feature.source_columns, ' | ')
    ),
    jsonb_build_object(
        'lookback_window', feature.lookback_window,
        'minimum_history', feature.minimum_history
    ) || CASE WHEN ref.ids IS NULL THEN '{}'::jsonb ELSE jsonb_build_object('formula_reference', jsonb_build_object(
            'calculation_ids', to_jsonb(ref.ids), 'relation', ref.relation, 'note', ref.note)) END,
    '{}'::jsonb,
    table_catalog.source_code_paths
        || ARRAY['database/migrations/20261023_004_onboard_feature05_06_stock_views.sql']
        || coalesce((SELECT array_agg('AI_formula_reference:' || id ORDER BY id) FROM unnest(ref.ids) AS id), '{}'),
    feature.dependency_rule,
    feature.null_rule,
    jsonb_build_object(
        'unit', feature.unit,
        'semantic_role', feature.semantic_role,
        'allowed_aggregations', feature.allowed_aggregations,
        'availability_rule', feature.availability_rule,
        'point_in_time_safe', feature.point_in_time_safe,
        'ai_allowed', column_catalog.ai_allowed
    ),
    feature.validation_evidence,
    'ACTIVE'
FROM public."Feature_Catalog" AS feature
JOIN (VALUES ('Feature_05_Foreign_Domestic_Broker_Detail_Stock', 'Feature_05_Foreign_Domestic_Broker_Detail'), ('Feature_06_Foreign_Domestic_Stock', 'Feature_06_Foreign_Domestic')) AS k(view_name, base) ON k.base = feature.feature_table
JOIN public."Table_Catalog" AS table_catalog
  ON table_catalog.table_schema = 'public' AND table_catalog.table_name = feature.feature_table
JOIN public."AI_column_catalog" AS column_catalog
  ON column_catalog.table_name = k.view_name AND column_catalog.column_name = feature.feature_column
LEFT JOIN (VALUES
    ('domestic_freq_imbalance_1d', ARRAY['CALC_136'], 'RELATED_NOT_IDENTICAL', '100 * (buy frequency - sell frequency) / (buy + sell frequency): transactions, where the reference uses shares.'),
    ('domestic_freq_imbalance_20d', ARRAY['CALC_136'], 'RELATED_NOT_IDENTICAL', '100 * (buy frequency - sell frequency) / (buy + sell frequency): transactions, where the reference uses shares.'),
    ('foreign_freq_imbalance_1d', ARRAY['CALC_136'], 'RELATED_NOT_IDENTICAL', '100 * (buy frequency - sell frequency) / (buy + sell frequency): transactions, where the reference uses shares.'),
    ('foreign_freq_imbalance_20d', ARRAY['CALC_136'], 'RELATED_NOT_IDENTICAL', '100 * (buy frequency - sell frequency) / (buy + sell frequency): transactions, where the reference uses shares.'),
    ('foreign_net_10d', ARRAY['CALC_138'], 'STORED_VARIANT', 'Sum of foreign_net_1d over the last 10 ticker sessions (Feature 02 session definition); a session without a row is not counted as zero.'),
    ('foreign_net_1d', ARRAY['CALC_137'], 'STORED_VARIANT', 'foreign_buy_1d - foreign_sell_1d of source Foreign investor rows (same source basis on both sides).'),
    ('foreign_net_20d', ARRAY['CALC_138'], 'STORED_VARIANT', 'Sum of foreign_net_1d over the last 20 ticker sessions (Feature 02 session definition); a session without a row is not counted as zero.'),
    ('foreign_net_40d', ARRAY['CALC_138'], 'STORED_VARIANT', 'Sum of foreign_net_1d over the last 40 ticker sessions (Feature 02 session definition); a session without a row is not counted as zero.'),
    ('foreign_net_5d', ARRAY['CALC_138'], 'STORED_VARIANT', 'Sum of foreign_net_1d over the last 5 ticker sessions (Feature 02 session definition); a session without a row is not counted as zero.'),
    ('foreign_net_60d', ARRAY['CALC_138'], 'STORED_VARIANT', 'Sum of foreign_net_1d over the last 60 ticker sessions (Feature 02 session definition); a session without a row is not counted as zero.'),
    ('foreign_net_percentile_10d_base252d', ARRAY['CALC_080'], 'RELATED_NOT_IDENTICAL', 'Midrank percentile against the previous baseline values, 100 * (count below + 0.5 * count equal) / baseline, today excluded; the reference counts values at or below.'),
    ('foreign_net_percentile_10d_base60d', ARRAY['CALC_080'], 'RELATED_NOT_IDENTICAL', 'Midrank percentile against the previous baseline values, 100 * (count below + 0.5 * count equal) / baseline, today excluded; the reference counts values at or below.'),
    ('foreign_net_percentile_20d_base252d', ARRAY['CALC_080'], 'RELATED_NOT_IDENTICAL', 'Midrank percentile against the previous baseline values, 100 * (count below + 0.5 * count equal) / baseline, today excluded; the reference counts values at or below.'),
    ('foreign_net_percentile_20d_base60d', ARRAY['CALC_080'], 'RELATED_NOT_IDENTICAL', 'Midrank percentile against the previous baseline values, 100 * (count below + 0.5 * count equal) / baseline, today excluded; the reference counts values at or below.'),
    ('foreign_net_percentile_40d_base252d', ARRAY['CALC_080'], 'RELATED_NOT_IDENTICAL', 'Midrank percentile against the previous baseline values, 100 * (count below + 0.5 * count equal) / baseline, today excluded; the reference counts values at or below.'),
    ('foreign_net_percentile_5d_base252d', ARRAY['CALC_080'], 'RELATED_NOT_IDENTICAL', 'Midrank percentile against the previous baseline values, 100 * (count below + 0.5 * count equal) / baseline, today excluded; the reference counts values at or below.'),
    ('foreign_net_percentile_5d_base60d', ARRAY['CALC_080'], 'RELATED_NOT_IDENTICAL', 'Midrank percentile against the previous baseline values, 100 * (count below + 0.5 * count equal) / baseline, today excluded; the reference counts values at or below.'),
    ('foreign_net_percentile_60d_base252d', ARRAY['CALC_080'], 'RELATED_NOT_IDENTICAL', 'Midrank percentile against the previous baseline values, 100 * (count below + 0.5 * count equal) / baseline, today excluded; the reference counts values at or below.'),
    ('foreign_net_turnover_ratio_1d', ARRAY['CALC_139'], 'RELATED_NOT_IDENTICAL', 'Stored as 100 * foreign net / (foreign buy + domestic buy) of the window, in percent; the reference divides by the asset traded value.'),
    ('foreign_net_turnover_ratio_20d', ARRAY['CALC_139'], 'RELATED_NOT_IDENTICAL', 'Stored as 100 * foreign net / (foreign buy + domestic buy) of the window, in percent; the reference divides by the asset traded value.'),
    ('foreign_net_turnover_ratio_5d', ARRAY['CALC_139'], 'RELATED_NOT_IDENTICAL', 'Stored as 100 * foreign net / (foreign buy + domestic buy) of the window, in percent; the reference divides by the asset traded value.'),
    ('foreign_net_zscore_10d_base252d', ARRAY['CALC_131'], 'STORED_VARIANT', '(rolling foreign net - mean of the previous baseline values) / sample standard deviation of them; today excluded, as the reference.'),
    ('foreign_net_zscore_10d_base60d', ARRAY['CALC_131'], 'STORED_VARIANT', '(rolling foreign net - mean of the previous baseline values) / sample standard deviation of them; today excluded, as the reference.'),
    ('foreign_net_zscore_20d_base252d', ARRAY['CALC_131'], 'STORED_VARIANT', '(rolling foreign net - mean of the previous baseline values) / sample standard deviation of them; today excluded, as the reference.'),
    ('foreign_net_zscore_20d_base60d', ARRAY['CALC_131'], 'STORED_VARIANT', '(rolling foreign net - mean of the previous baseline values) / sample standard deviation of them; today excluded, as the reference.'),
    ('foreign_net_zscore_40d_base252d', ARRAY['CALC_131'], 'STORED_VARIANT', '(rolling foreign net - mean of the previous baseline values) / sample standard deviation of them; today excluded, as the reference.'),
    ('foreign_net_zscore_5d_base252d', ARRAY['CALC_131'], 'STORED_VARIANT', '(rolling foreign net - mean of the previous baseline values) / sample standard deviation of them; today excluded, as the reference.'),
    ('foreign_net_zscore_5d_base60d', ARRAY['CALC_131'], 'STORED_VARIANT', '(rolling foreign net - mean of the previous baseline values) / sample standard deviation of them; today excluded, as the reference.'),
    ('foreign_net_zscore_60d_base252d', ARRAY['CALC_131'], 'STORED_VARIANT', '(rolling foreign net - mean of the previous baseline values) / sample standard deviation of them; today excluded, as the reference.')
) AS ref(column_name, ids, relation, note) ON ref.column_name = feature.feature_column AND k.view_name = 'Feature_06_Foreign_Domestic_Stock'
WHERE feature.is_active;

-- 6. preview: the two views added (no hidden column: calculated_at is not in the views)
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
    -- on the large tables; Feature 04's order and the Feature 05/06 views' orders were measured (DATABASE_CHANGELOG.md).
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
        ELSE NULL
    END;
    IF order_clause IS NULL THEN
        RAISE EXCEPTION 'Table is not approved for preview' USING ERRCODE = 'insufficient_privilege';
    END IF;
    hidden := CASE p_table_name
        WHEN 'Feature_04_Technical_Indicator' THEN ARRAY['tracking_high', 'tracking_low', 'temp_high',
            'temp_high_bar', 'temp_low', 'temp_low_bar', 'calculation_version', 'calculated_at']
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
    'market-ai-orc preview: at most 20 rows in a fixed order from twelve approved market-data objects (Feature 04 without its hidden state columns); EXECUTE only via market_ai_preview_reader.';

-- 7. Table_Catalog / Column_Catalog for the views (scripts/sync_database_catalog.py covers base tables only); the
--    availability contract is the base table's
INSERT INTO public."Table_Catalog" (
    table_schema, table_name, category, definition, grain, primary_key_columns, source_system, source_tables,
    source_code_paths, update_rule, related_functions, documentation_status, readiness_mode, readiness_date_column,
    observation_date_column, data_available_at_column, availability_rule, point_in_time_status,
    historical_metadata_method)
SELECT 'public', k.view_name, 'Feature',
       'View of ' || k.base || ' limited to the current IDX stock universe (IDX_Stock_Universe "Security Type" = stock), without calculated_at. The object exposed to the AI. ' || b.definition,
       b.grain, b.primary_key_columns, b.source_system, ARRAY[k.base, 'IDX_Stock_Universe']::text[],
       ARRAY['database/migrations/20261023_004_onboard_feature05_06_stock_views.sql'] || b.source_code_paths,
       'A view: changes when ' || k.base || ' or the stock universe changes. ' || b.update_rule,
       ARRAY['public.ai_preview_table_rows(text)']::text[], 'PARTIAL', 'DATA_DATE', 'trade_date',
       b.observation_date_column, b.data_available_at_column,
       b.availability_rule || ' Current stock universe only: a stock that left the universe is not in the view.',
       b.point_in_time_status, b.historical_metadata_method
FROM (VALUES ('Feature_05_Foreign_Domestic_Broker_Detail_Stock', 'Feature_05_Foreign_Domestic_Broker_Detail'), ('Feature_06_Foreign_Domestic_Stock', 'Feature_06_Foreign_Domestic')) AS k(view_name, base)
JOIN public."Table_Catalog" AS b ON b.table_schema = 'public' AND b.table_name = k.base;

UPDATE public."Table_Catalog"
SET source_code_paths = source_code_paths || ARRAY['database/migrations/20261023_004_onboard_feature05_06_stock_views.sql']
WHERE table_schema = 'public' AND table_name IN ('Feature_05_Foreign_Domestic_Broker_Detail', 'Feature_06_Foreign_Domestic', 'AI_table_catalog', 'AI_column_catalog',
                                                 'AI_catalog_relationships', 'AI_calculation_catalog')
  AND NOT ('database/migrations/20261023_004_onboard_feature05_06_stock_views.sql' = ANY (source_code_paths));

INSERT INTO public."Column_Catalog" (
    table_schema, table_name, column_name, ordinal_position, data_type, is_nullable, default_expression,
    is_primary_key, definition, source_column_or_expression, unit, null_rule, source_code_paths, documentation_status)
SELECT 'public', v.table_name, v.column_name, v.ordinal_position, v.data_type, v.is_nullable = 'YES', NULL,
       false, b.definition, k.base || '.' || v.column_name, b.unit, b.null_rule,
       ARRAY['database/migrations/20261023_004_onboard_feature05_06_stock_views.sql'], 'PARTIAL'
FROM information_schema.columns AS v
JOIN (VALUES ('Feature_05_Foreign_Domestic_Broker_Detail_Stock', 'Feature_05_Foreign_Domestic_Broker_Detail'), ('Feature_06_Foreign_Domestic_Stock', 'Feature_06_Foreign_Domestic')) AS k(view_name, base) ON k.view_name = v.table_name
JOIN public."Column_Catalog" AS b ON b.table_schema = 'public' AND b.table_name = k.base AND b.column_name = v.column_name
WHERE v.table_schema = 'public';

DO $verify$
BEGIN
    -- the views hold exactly the base rows of universe stocks
    IF (SELECT count(*) FROM public."Feature_06_Foreign_Domestic_Stock") <> (SELECT count(*) FROM public."Feature_06_Foreign_Domestic" AS f
            WHERE f.ticker IN (SELECT u."Ticker" FROM public."IDX_Stock_Universe" AS u WHERE u."Security Type" = 'stock'))
       OR (SELECT count(*) FROM public."Feature_06_Foreign_Domestic_Stock") = 0
       OR EXISTS (SELECT 1 FROM public."Feature_06_Foreign_Domestic_Stock" AS v WHERE v.ticker NOT IN (SELECT "Ticker" FROM public."IDX_Stock_Universe")) THEN
        RAISE EXCEPTION 'Feature 06 view rows do not equal the universe rows of the base table';
    END IF;
    IF (SELECT count(*) FROM public."AI_table_catalog" WHERE table_name IN ('Feature_05_Foreign_Domestic_Broker_Detail_Stock', 'Feature_06_Foreign_Domestic_Stock') AND is_active
            AND ai_access_level = 'BOUNDED_READ') <> 2 THEN
        RAISE EXCEPTION 'The two views are not active in AI_table_catalog';
    END IF;
    IF (SELECT count(*) FROM public."AI_column_catalog" WHERE table_name = 'Feature_05_Foreign_Domestic_Broker_Detail_Stock' AND ai_allowed) <> 14
       OR (SELECT count(*) FROM public."AI_column_catalog" WHERE table_name = 'Feature_06_Foreign_Domestic_Stock' AND ai_allowed) <> 86 THEN
        RAISE EXCEPTION 'Unexpected AI_column_catalog rows for the views';
    END IF;
    IF EXISTS (SELECT 1 FROM public."AI_column_catalog" WHERE table_name IN ('Feature_05_Foreign_Domestic_Broker_Detail_Stock', 'Feature_06_Foreign_Domestic_Stock')
               AND (description IS NULL OR btrim(description) = '' OR unit IS NULL)) THEN
        RAISE EXCEPTION 'An exposed column lacks its description or unit';
    END IF;
    -- summary rules: only the one-session flows sum; cumulative columns take LAST
    IF (SELECT count(*) FROM public."AI_column_catalog" WHERE table_name = 'Feature_05_Foreign_Domestic_Broker_Detail_Stock' AND resample_aggregation = 'SUM'
            AND cross_entity_aggregation = 'SUM') <> 8
       OR (SELECT count(*) FROM public."AI_column_catalog" WHERE table_name = 'Feature_06_Foreign_Domestic_Stock' AND resample_aggregation = 'SUM'
            AND cross_entity_aggregation = 'SUM') <> 10
       OR (SELECT count(*) FROM public."AI_column_catalog" WHERE table_name = 'Feature_06_Foreign_Domestic_Stock' AND resample_aggregation = 'LAST'
            AND cross_entity_aggregation IS NULL) <> 2 THEN
        RAISE EXCEPTION 'Unexpected summary rules on the views';
    END IF;
    IF (SELECT count(*) FROM public."AI_calculation_catalog" WHERE target_table = 'Feature_05_Foreign_Domestic_Broker_Detail_Stock' AND status = 'ACTIVE') <> 14
       OR (SELECT count(*) FROM public."AI_calculation_catalog" WHERE target_table = 'Feature_06_Foreign_Domestic_Stock' AND status = 'ACTIVE') <> 86
       OR (SELECT count(*) FROM public."AI_calculation_catalog" WHERE target_table = 'Feature_06_Foreign_Domestic_Stock'
           AND parameters ? 'formula_reference') <> 29 THEN
        RAISE EXCEPTION 'Unexpected Feature 05/06 AI_calculation_catalog rows';
    END IF;
    IF EXISTS (SELECT 1 FROM public."AI_calculation_catalog" AS k, unnest(k.implementation_ref) AS ref
               WHERE k.target_table IN ('Feature_05_Foreign_Domestic_Broker_Detail_Stock', 'Feature_06_Foreign_Domestic_Stock') AND ref LIKE 'AI_formula_reference:%'
                 AND NOT EXISTS (SELECT 1 FROM public."AI_formula_reference" AS f
                                 WHERE 'AI_formula_reference:' || f.calculation_id = ref)) THEN
        RAISE EXCEPTION 'A formula reference names a missing AI_formula_reference row';
    END IF;
    IF EXISTS (SELECT 1 FROM public."AI_catalog_relationships" AS r,
                    LATERAL (SELECT r.left_table AS t, unnest(r.left_columns) AS col
                             UNION ALL SELECT r.right_table, unnest(r.right_columns)) AS k
               WHERE (r.left_table IN ('Feature_05_Foreign_Domestic_Broker_Detail_Stock', 'Feature_06_Foreign_Domestic_Stock') OR r.right_table IN ('Feature_05_Foreign_Domestic_Broker_Detail_Stock', 'Feature_06_Foreign_Domestic_Stock'))
                 AND NOT EXISTS (SELECT 1 FROM public."AI_column_catalog" AS c
                                 WHERE c.table_name = k.t AND c.column_name = k.col AND c.ai_allowed)) THEN
        RAISE EXCEPTION 'A relationship key column is not an exposed AI catalog column';
    END IF;
    IF (SELECT count(*) FROM public."AI_catalog_relationships" WHERE is_allowed AND
        (left_table IN ('Feature_05_Foreign_Domestic_Broker_Detail_Stock', 'Feature_06_Foreign_Domestic_Stock') OR right_table IN ('Feature_05_Foreign_Domestic_Broker_Detail_Stock', 'Feature_06_Foreign_Domestic_Stock'))) <> 11 THEN
        RAISE EXCEPTION 'Expected eleven relationships for the views';
    END IF;
    IF NOT has_table_privilege('market_ai_sql_reader', 'public."Feature_05_Foreign_Domestic_Broker_Detail_Stock"', 'SELECT')
       OR NOT has_table_privilege('market_ai_sql_reader', 'public."Feature_06_Foreign_Domestic_Stock"', 'SELECT')
       OR has_table_privilege('market_ai_sql_reader', 'public."Feature_05_Foreign_Domestic_Broker_Detail"', 'SELECT')
       OR has_table_privilege('market_ai_sql_reader', 'public."Feature_06_Foreign_Domestic"', 'SELECT')
       OR has_table_privilege('market_ai_sql_reader', 'public."Feature_06_Foreign_Domestic_Stock"', 'INSERT,UPDATE,DELETE,TRUNCATE')
       OR has_table_privilege('market_ai_preview_reader', 'public."Feature_05_Foreign_Domestic_Broker_Detail_Stock"', 'SELECT')
       OR (SELECT proowner FROM pg_proc WHERE oid = 'public.ai_preview_table_rows(text)'::regprocedure)
          <> 'market_ai_preview_owner'::regrole
       OR NOT (SELECT prosecdef FROM pg_proc WHERE oid = 'public.ai_preview_table_rows(text)'::regprocedure) THEN
        RAISE EXCEPTION 'Unexpected privileges on the views, the base tables or the preview function';
    END IF;
    IF (SELECT count(*) FROM public."Table_Catalog" WHERE table_schema = 'public' AND table_name IN ('Feature_05_Foreign_Domestic_Broker_Detail_Stock', 'Feature_06_Foreign_Domestic_Stock')) <> 2
       OR (SELECT count(*) FROM public."Column_Catalog" WHERE table_schema = 'public' AND table_name = 'Feature_05_Foreign_Domestic_Broker_Detail_Stock') <> 14
       OR (SELECT count(*) FROM public."Column_Catalog" WHERE table_schema = 'public' AND table_name = 'Feature_06_Foreign_Domestic_Stock') <> 86 THEN
        RAISE EXCEPTION 'Table_Catalog / Column_Catalog are not complete for the views';
    END IF;
END
$verify$;

COMMIT;
