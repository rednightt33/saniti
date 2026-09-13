-- Register safe join contracts for the validated Feature 03 table.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '2min';

DO $preflight$
BEGIN
    IF to_regclass('public."Feature_Relationship_Catalog"') IS NULL
       OR to_regclass('public."Feature_01_Stock_Daily"') IS NULL
       OR to_regclass('public."Feature_02_Broker_Rolling"') IS NULL
       OR to_regclass('public."Feature_03_Stock_Broker_Daily"') IS NULL THEN
        RAISE EXCEPTION 'Feature 03 relationship dependency is missing';
    END IF;
END
$preflight$;

INSERT INTO public."Feature_Relationship_Catalog" (
    left_feature_table, right_feature_table,
    left_join_columns, right_join_columns,
    relationship_type, safe_output_grain, requires_preaggregation,
    definition, version, is_active
) VALUES
(
    'Feature_02_Broker_Rolling', 'Feature_03_Stock_Broker_Daily',
    ARRAY['ticker','market_board','date'], ARRAY['ticker','market_board','date'],
    'MANY_TO_ONE', 'Date × ticker × market_board × broker', false,
    'Feature 03 is unique at ticker, market_board and date, so joining it onto Feature 02 preserves the Feature 02 broker-level grain. Broker is intentionally absent from the Feature 03 key.',
    'v1', true
),
(
    'Feature_01_Stock_Daily', 'Feature_03_Stock_Broker_Daily',
    ARRAY['ticker','date'], ARRAY['ticker','date'],
    'ONE_TO_MANY', 'Date × ticker × market_board after an explicit board filter, or Date × ticker after valid Feature 03 board preaggregation', true,
    'Feature 01 has one ticker-date row while Feature 03 can have one row per board. Filter a specific board, normally Regular, or preaggregate Feature 03 explicitly before claiming ticker-date output.',
    'v1', true
);

COMMIT;
