-- query_metric (round 2026-10-03 D5; ROUND_PLAN_2026-10-03_FASE_D.md): the official metrics a short question can be
-- answered with in one Governor summary (POST /v1/summary) instead of a data need, a bundle and a Python session.
-- public."AI_metric_catalog" holds one row per metric version: its source table and measure column, how it runs over
-- time, the dimensions it may be split by, a default row filter, and its meaning. It defines; it does not compute and
-- does not repeat the catalog's rules: units and additivity (resample_aggregation, cross_entity_aggregation) stay in
-- AI_column_catalog and are read when the metric runs, and the Governor re-derives them for every summary.
-- Initial metrics: user decision 1 (2026-10-03) with the sources the user chose on 2026-10-03 (net foreign value from
-- Feature_03_Stock_Broker_Daily, broker net value from IDX_Broker_Summary, transaction value postponed until an
-- official column exists). Every row is INFERRED until the user reviews it; none is VERIFIED.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';

DO $preflight$
BEGIN
    IF to_regclass('public."AI_metric_catalog"') IS NOT NULL THEN
        RAISE EXCEPTION 'AI_metric_catalog already exists';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'market_ai_catalog_reader') THEN
        RAISE EXCEPTION 'market_ai_catalog_reader role is required';
    END IF;
    IF EXISTS (SELECT 1 FROM public."Table_Catalog" WHERE table_schema = 'public'
               AND table_name = 'AI_metric_catalog') THEN
        RAISE EXCEPTION 'Table_Catalog already documents AI_metric_catalog';
    END IF;
END
$preflight$;

CREATE TABLE public."AI_metric_catalog" (
    metric_id text NOT NULL,
    metric_version integer NOT NULL DEFAULT 1,
    label text NOT NULL,
    description text NOT NULL,
    source_table text NOT NULL,
    measure_column text NOT NULL,
    time_function text NOT NULL,
    entity_column text NOT NULL,
    default_dimensions text[] NOT NULL DEFAULT ARRAY[]::text[],
    allowed_dimensions text[] NOT NULL DEFAULT ARRAY[]::text[],
    default_scope jsonb NOT NULL DEFAULT '{"type": "ALL"}'::jsonb,
    formula text NOT NULL,
    interpretation text NOT NULL,
    recommended_use text NOT NULL,
    misuse_warning text NOT NULL,
    review_status text NOT NULL DEFAULT 'INFERRED',
    source_decision text NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "AI_metric_catalog_pkey" PRIMARY KEY (metric_id, metric_version),
    CONSTRAINT ai_metric_catalog_id CHECK (metric_id ~ '^[a-z][a-z0-9_]{0,63}$' AND metric_version >= 1),
    CONSTRAINT ai_metric_catalog_function CHECK (time_function IN ('SUM', 'MIN', 'MAX', 'FIRST', 'LAST', 'COUNT')),
    CONSTRAINT ai_metric_catalog_review CHECK (review_status IN ('INFERRED', 'REVIEWED', 'VERIFIED')),
    CONSTRAINT ai_metric_catalog_scope CHECK (jsonb_typeof(default_scope) = 'object' AND default_scope ? 'type'),
    CONSTRAINT ai_metric_catalog_dimensions CHECK (default_dimensions <@ allowed_dimensions
                                                   AND entity_column = ANY (allowed_dimensions))
);
CREATE UNIQUE INDEX ai_metric_catalog_one_active ON public."AI_metric_catalog" (metric_id) WHERE is_active;
COMMENT ON TABLE public."AI_metric_catalog" IS
    'Official metrics for query_metric (one Governor summary per period); units and additivity are read from '
    'AI_column_catalog, never repeated here.';

-- market-ai-orc's catalog login inherits this role; the SQL Governor role gets no grant (it validates from
-- AI_column_catalog).
GRANT SELECT ON public."AI_metric_catalog" TO market_ai_catalog_reader;
REVOKE ALL ON public."AI_metric_catalog" FROM PUBLIC;

INSERT INTO public."AI_metric_catalog" (
    metric_id, label, description, source_table, measure_column, time_function, entity_column, default_dimensions,
    allowed_dimensions, default_scope, formula, interpretation, recommended_use, misuse_warning, source_decision
) VALUES (
    'net_foreign_value', 'Net beli asing (nilai)',
    'Net value of source Foreign investors (buy value minus sell value) per stock and market board, summed over the period.',
    'Feature_03_Stock_Broker_Daily', 'foreign_net_value', 'SUM', 'ticker', ARRAY['ticker', 'market_board'],
    ARRAY['ticker', 'market_board'], '{"type": "ALL"}',
    'SUM(foreign_net_value) over the period''s trading days, per ticker (and market board unless the boards are combined).',
    'Positive: foreign investors bought more than they sold over the period; negative: they sold more. Investor Type '
    'is the source''s investor classification, not the broker''s domicile.',
    'Short questions on foreign flow of one or a few stocks over 1-60 trading days.',
    'Boards stay separate by default; combining Regular with Nego or Tunai mixes negotiated block trades into the '
    'flow. Not a price signal by itself.',
    'User decision 1 and source choice D-a (2026-10-03)'
), (
    'broker_net_value', 'Net beli per broker (nilai)',
    'Net value (buy value minus sell value) of each broker per stock and market board, summed over the period.',
    'IDX_Broker_Summary', 'Net Value', 'SUM', 'Symbol', ARRAY['Symbol', 'Broker', 'Market Board'],
    ARRAY['Symbol', 'Broker', 'Investor Type', 'Market Board'], '{"type": "ALL"}',
    'SUM("Net Value") over the period''s trading days, per Symbol and Broker (and Market Board unless combined).',
    'Positive: the broker bought more than it sold for its clients over the period. A broker''s flow mixes all of '
    'its clients; Investor Type splits Domestic and Foreign clients.',
    'Which brokers accumulated or distributed one stock over a period.',
    'A broker is not one investor. Many brokers per stock: filter by Symbol, and group by Broker only for a few '
    'stocks, or the summary exceeds 200 rows.',
    'User decision 1 and source choice D-c (2026-10-03)'
), (
    'volume', 'Volume',
    'Shares traded per stock, summed over the period.',
    'Price_Stock_Indonesia_IDX', 'volume', 'SUM', 'ticker', ARRAY['ticker'], ARRAY['ticker'], '{"type": "ALL"}',
    'SUM(volume) over the period''s trading days, per ticker.',
    'Total shares traded in the period as reported by the price source.',
    'Liquidity of one or a few stocks over a period.',
    'Per stock only: the catalog has no rule for adding volumes of different stocks.',
    'User decision 1 (2026-10-03)'
), (
    'last_close', 'Harga penutupan terakhir',
    'The last closing price of each stock within the period.',
    'Price_Stock_Indonesia_IDX', 'close', 'LAST', 'ticker', ARRAY['ticker'], ARRAY['ticker'], '{"type": "ALL"}',
    'The close of the latest trading day with a close, per ticker, within the period.',
    'The price at the end of the period; last_date shows which day it is.',
    'The latest price of one or a few stocks, as of the conversation''s data date.',
    'Not adjusted for corporate actions; compare closes across dates only with that in mind.',
    'User decision 1 (2026-10-03)'
), (
    'period_high', 'Harga tertinggi dalam periode',
    'The highest intraday price of each stock within the period.',
    'Price_Stock_Indonesia_IDX', 'high', 'MAX', 'ticker', ARRAY['ticker'], ARRAY['ticker'], '{"type": "ALL"}',
    'MAX(high) over the period''s trading days, per ticker.',
    'The highest traded price in the period.',
    'Price ranges of one or a few stocks over a period.',
    'Intraday high, not the highest close; not adjusted for corporate actions.',
    'User decision 1 (2026-10-03)'
), (
    'period_low', 'Harga terendah dalam periode',
    'The lowest intraday price of each stock within the period.',
    'Price_Stock_Indonesia_IDX', 'low', 'MIN', 'ticker', ARRAY['ticker'], ARRAY['ticker'], '{"type": "ALL"}',
    'MIN(low) over the period''s trading days, per ticker.',
    'The lowest traded price in the period.',
    'Price ranges of one or a few stocks over a period.',
    'Intraday low, not the lowest close; not adjusted for corporate actions.',
    'User decision 1 (2026-10-03)'
);

INSERT INTO public."Table_Catalog" (
    table_schema, table_name, category, definition, grain,
    primary_key_columns, source_system, source_tables, source_code_paths,
    update_rule, related_functions, documentation_status,
    readiness_mode, readiness_date_column, observation_date_column,
    data_available_at_column, availability_rule, point_in_time_status,
    historical_metadata_method
) VALUES (
    'public', 'AI_metric_catalog', 'System',
    'Official metrics market-ai-orc''s query_metric answers in one SQL Governor summary: source table, measure column, rule over time, dimensions, default row filter and meaning. Units and additivity are read from AI_column_catalog.',
    'One row per metric version', ARRAY['metric_id', 'metric_version'],
    'Forward migrations (round 2026-10-03 D5); metric list approved by the user',
    ARRAY['AI_column_catalog', 'Feature_03_Stock_Broker_Daily', 'IDX_Broker_Summary',
          'Price_Stock_Indonesia_IDX']::text[],
    ARRAY['database/migrations/20261003_008_ai_metric_catalog.sql', 'apps/market-ai-orc/app/tools/metric.py',
          'apps/market-sql-governor/app/summary.py'],
    'A changed metric is a new metric_version through a forward migration; the old version is set inactive.',
    ARRAY[]::text[], 'VERIFIED', 'NOT_APPLICABLE', NULL, NULL, 'created_at',
    'Metadata, not market data.', 'NOT_APPLICABLE', NULL
);

INSERT INTO public."Column_Catalog" (
    table_schema, table_name, column_name, ordinal_position, data_type,
    is_nullable, default_expression, is_primary_key, definition,
    source_column_or_expression, unit, null_rule, source_code_paths,
    documentation_status
)
SELECT columns.table_schema, columns.table_name, columns.column_name, columns.ordinal_position,
       columns.data_type, columns.is_nullable = 'YES', columns.column_default,
       columns.column_name IN ('metric_id', 'metric_version'),
       CASE columns.column_name
        WHEN 'metric_id' THEN 'Stable name of the metric the model passes to query_metric.'
        WHEN 'metric_version' THEN 'Version of the metric definition; a change is a new version.'
        WHEN 'label' THEN 'Indonesian label shown to users.'
        WHEN 'description' THEN 'What the metric measures, in plain words.'
        WHEN 'source_table' THEN 'The governed table the metric is computed from.'
        WHEN 'measure_column' THEN 'The column the metric summarises.'
        WHEN 'time_function' THEN 'How the metric runs over the period: SUM, MIN, MAX, FIRST, LAST or COUNT; checked against the column''s catalog rule by the Governor.'
        WHEN 'entity_column' THEN 'The column the entities of a question (tickers or symbols) filter.'
        WHEN 'default_dimensions' THEN 'The columns the result is split by when the question names none.'
        WHEN 'allowed_dimensions' THEN 'Every column the result may be split by.'
        WHEN 'default_scope' THEN 'A canonical scope tree always applied (ALL: none).'
        WHEN 'formula' THEN 'The computation in words.'
        WHEN 'interpretation' THEN 'How to read the value.'
        WHEN 'recommended_use' THEN 'The questions the metric answers.'
        WHEN 'misuse_warning' THEN 'How the metric is misread or misused.'
        WHEN 'review_status' THEN 'INFERRED (proposed), REVIEWED or VERIFIED (confirmed by the user).'
        WHEN 'source_decision' THEN 'The user decision the metric comes from.'
        WHEN 'is_active' THEN 'Whether query_metric offers this version.'
        WHEN 'created_at' THEN 'When the row was inserted.'
       END,
       columns.column_name, NULL, NULL, ARRAY['database/migrations/20261003_008_ai_metric_catalog.sql'], 'VERIFIED'
FROM information_schema.columns
WHERE columns.table_schema = 'public' AND columns.table_name = 'AI_metric_catalog';

DO $verify$
BEGIN
    IF (SELECT count(*) FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'AI_metric_catalog') <> 19 THEN
        RAISE EXCEPTION 'AI_metric_catalog does not have the expected columns';
    END IF;
    IF (SELECT count(*) FROM public."Column_Catalog"
        WHERE table_name = 'AI_metric_catalog' AND definition IS NOT NULL) <> 19 THEN
        RAISE EXCEPTION 'Every AI_metric_catalog column needs a Column_Catalog definition';
    END IF;
    IF (SELECT count(*) FROM public."AI_metric_catalog" WHERE is_active AND review_status = 'INFERRED') <> 6 THEN
        RAISE EXCEPTION 'Expected the six initial metrics, all INFERRED';
    END IF;
    -- every metric names AI-allowed catalog columns (the Governor would refuse it at run time otherwise)
    IF EXISTS (SELECT 1 FROM public."AI_metric_catalog" m
               WHERE NOT EXISTS (SELECT 1 FROM public."AI_column_catalog" c
                                 WHERE c.table_name = m.source_table AND c.column_name = m.measure_column
                                   AND c.ai_allowed)
                  OR EXISTS (SELECT 1 FROM unnest(m.allowed_dimensions) AS d(name)
                             WHERE NOT EXISTS (SELECT 1 FROM public."AI_column_catalog" c
                                               WHERE c.table_name = m.source_table AND c.column_name = d.name
                                                 AND c.ai_allowed))) THEN
        RAISE EXCEPTION 'A metric names a column that is not an AI-allowed catalog column';
    END IF;
    IF NOT has_table_privilege('market_ai_catalog_reader', 'public."AI_metric_catalog"', 'SELECT')
       OR has_table_privilege('market_ai_catalog_reader', 'public."AI_metric_catalog"', 'INSERT,UPDATE,DELETE') THEN
        RAISE EXCEPTION 'market_ai_catalog_reader must read AI_metric_catalog only';
    END IF;
END
$verify$;

COMMIT;
