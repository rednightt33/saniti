-- Resample rules for derived weekly and monthly analysis (implementation plan IP2, solution 1).
--
-- AI_column_catalog.resample_aggregation (migration 20260925_003) tells saniti.resample() how one column aggregates
-- from daily rows to a coarser period within the same entity and grain. Before this migration no column had a rule,
-- so every weekly or monthly request failed with RESAMPLE_RULE_MISSING. This seeds only rules whose semantics the
-- catalog definition proves (review: IP2_RESAMPLE_RULE_REVIEW.md):
--   open FIRST, high MAX, low MIN, close LAST, traded volume SUM,
--   daily gross buy/sell and daily net value or lots SUM (net = buy - sell per day, so the period net is the sum).
-- Everything else stays NULL and fails closed: returns and percentages, ratios, z-scores, percentiles,
-- concentration, rolling 5/20/60-date metrics, averages, counts of distinct brokers, top-N values, values repeated
-- from another grain (sector, broker classification, names) and timestamps.
-- Weekly and monthly are always derived from daily rows (never monthly from weekly); returns are never summed.
-- Forward-only. Only resample_aggregation of the 27 listed columns changes; a NULL rule can be restored by a later
-- forward migration.
BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';

CREATE TEMP TABLE resample_seed (table_name text, column_name text, rule text) ON COMMIT DROP;
INSERT INTO resample_seed (table_name, column_name, rule) VALUES
    ('Price_Stock_Indonesia_IDX', 'open', 'FIRST'),
    ('Price_Stock_Indonesia_IDX', 'high', 'MAX'),
    ('Price_Stock_Indonesia_IDX', 'low', 'MIN'),
    ('Price_Stock_Indonesia_IDX', 'close', 'LAST'),
    ('Price_Stock_Indonesia_IDX', 'volume', 'SUM'),
    ('Feature_01_Stock_Daily', 'close', 'LAST'),
    ('Feature_01_Stock_Daily', 'volume', 'SUM'),
    ('IDX_Broker_Summary', 'Buy Value', 'SUM'),
    ('IDX_Broker_Summary', 'Sell Value', 'SUM'),
    ('IDX_Broker_Summary', 'Net Value', 'SUM'),
    ('IDX_Broker_Summary', 'Buy Lots', 'SUM'),
    ('IDX_Broker_Summary', 'Sell Lots', 'SUM'),
    ('IDX_Broker_Summary', 'Net Lots', 'SUM'),
    ('Feature_02_Broker_Rolling', 'buy_value_1d', 'SUM'),
    ('Feature_02_Broker_Rolling', 'sell_value_1d', 'SUM'),
    ('Feature_02_Broker_Rolling', 'net_value_1d', 'SUM'),
    ('Feature_02_Broker_Rolling', 'buy_lots_1d', 'SUM'),
    ('Feature_02_Broker_Rolling', 'sell_lots_1d', 'SUM'),
    ('Feature_02_Broker_Rolling', 'net_lots_1d', 'SUM'),
    ('Feature_03_Stock_Broker_Daily', 'total_buy_value', 'SUM'),
    ('Feature_03_Stock_Broker_Daily', 'total_sell_value', 'SUM'),
    ('Feature_03_Stock_Broker_Daily', 'foreign_net_value', 'SUM'),
    ('Feature_03_Stock_Broker_Daily', 'domestic_net_value', 'SUM'),
    ('Feature_03_Stock_Broker_Daily', 'institutional_net_value', 'SUM'),
    ('Feature_03_Stock_Broker_Daily', 'retail_net_value', 'SUM'),
    ('Feature_03_Stock_Broker_Daily', 'mixed_net_value', 'SUM'),
    ('Feature_03_Stock_Broker_Daily', 'niche_net_value', 'SUM');

DO $preflight$
BEGIN
    IF (SELECT count(*) FROM resample_seed) <> 27 THEN
        RAISE EXCEPTION 'The seed must list 27 columns';
    END IF;
    IF EXISTS (SELECT 1 FROM resample_seed s
               LEFT JOIN public."AI_column_catalog" c USING (table_name, column_name)
               WHERE c.column_name IS NULL) THEN
        RAISE EXCEPTION 'A seeded column is missing from AI_column_catalog';
    END IF;
    IF EXISTS (SELECT 1 FROM resample_seed s
               JOIN public."AI_column_catalog" c USING (table_name, column_name)
               WHERE c.resample_aggregation IS NOT NULL AND c.resample_aggregation <> s.rule) THEN
        RAISE EXCEPTION 'A seeded column already has a different resample rule: inspect before applying';
    END IF;
    IF EXISTS (SELECT 1 FROM public."AI_column_catalog" c
               WHERE c.resample_aggregation IS NOT NULL
                 AND NOT EXISTS (SELECT 1 FROM resample_seed s
                                 WHERE s.table_name = c.table_name AND s.column_name = c.column_name)) THEN
        RAISE EXCEPTION 'A column outside this seed already has a resample rule: inspect before applying';
    END IF;
    -- every seeded column is a daily measure of a table with a time column
    IF EXISTS (SELECT 1 FROM resample_seed s
               JOIN public."AI_column_catalog" c USING (table_name, column_name)
               JOIN public."AI_table_catalog" t USING (table_name)
               WHERE t.time_column IS NULL OR c.is_primary_key
                  OR c.data_type NOT IN ('numeric', 'double precision', 'bigint', 'integer', 'smallint')) THEN
        RAISE EXCEPTION 'A seeded column is not a numeric measure of a dated table';
    END IF;
END
$preflight$;

UPDATE public."AI_column_catalog" AS c
SET resample_aggregation = s.rule
FROM resample_seed AS s
WHERE c.table_name = s.table_name AND c.column_name = s.column_name
  AND c.resample_aggregation IS DISTINCT FROM s.rule;

DO $verify$
BEGIN
    IF (SELECT count(*) FROM public."AI_column_catalog" c JOIN resample_seed s USING (table_name, column_name)
        WHERE c.resample_aggregation = s.rule) <> 27 THEN
        RAISE EXCEPTION 'Not every seeded column carries its rule';
    END IF;
    IF (SELECT count(*) FROM public."AI_column_catalog" WHERE resample_aggregation IS NOT NULL) <> 27 THEN
        RAISE EXCEPTION 'Only the 27 seeded columns may carry a resample rule';
    END IF;
    IF EXISTS (SELECT 1 FROM public."AI_column_catalog"
               WHERE resample_aggregation IS NOT NULL
                 AND (column_name ~ '(return|pct|ratio|zscore|percentile|share|hhi|avg|std|_5d|_20d|_60d|count)'
                      OR column_name IN ('Avg Buy', 'Avg Sell'))) THEN
        RAISE EXCEPTION 'A return, ratio, rolling, average or count column received a rule';
    END IF;
END
$verify$;

COMMIT;
