-- Stock-level daily broker structure, separated by the three source market boards.
-- Feature definitions remain PARTIAL until the historical backfill validates.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '10min';

DO $preflight$
BEGIN
    IF to_regclass('public."Feature_03_Stock_Broker_Daily"') IS NOT NULL THEN
        RAISE EXCEPTION 'Feature_03_Stock_Broker_Daily already exists';
    END IF;
    IF to_regclass('public."Feature_02_Broker_Rolling"') IS NULL
       OR to_regclass('public."IDX_Broker_Profile"') IS NULL
       OR to_regclass('public."Table_Catalog"') IS NULL
       OR to_regclass('public."Column_Catalog"') IS NULL THEN
        RAISE EXCEPTION 'Feature 03 dependency or catalog table is missing';
    END IF;
END
$preflight$;

CREATE TABLE public."Feature_03_Stock_Broker_Daily" (
    date date NOT NULL,
    ticker text NOT NULL,
    market_board text NOT NULL,
    total_buy_value numeric NOT NULL,
    total_sell_value numeric NOT NULL,
    active_broker_count smallint NOT NULL,
    net_buy_broker_count smallint NOT NULL,
    net_sell_broker_count smallint NOT NULL,
    net_buy_broker_ratio double precision,
    foreign_net_value numeric NOT NULL,
    domestic_net_value numeric NOT NULL,
    institutional_net_value numeric NOT NULL,
    retail_net_value numeric NOT NULL,
    mixed_net_value numeric NOT NULL,
    niche_net_value numeric NOT NULL,
    top_buyer text,
    top_buyer_net_value numeric,
    top_seller text,
    top_seller_net_value numeric,
    top3_buyer_net_value numeric NOT NULL,
    positive_net_value_total numeric NOT NULL,
    top3_buyer_share double precision,
    broker_concentration_hhi double precision,
    calculated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Feature_03_Stock_Broker_Daily_pkey"
        PRIMARY KEY (ticker, market_board, date),
    CONSTRAINT "Feature_03_Stock_Broker_Daily_board_check"
        CHECK (market_board IN ('Regular', 'Nego', 'Tunai')),
    CONSTRAINT "Feature_03_Stock_Broker_Daily_identity_check"
        CHECK (btrim(ticker) <> ''),
    CONSTRAINT "Feature_03_Stock_Broker_Daily_gross_check"
        CHECK (total_buy_value >= 0 AND total_sell_value >= 0),
    CONSTRAINT "Feature_03_Stock_Broker_Daily_count_check"
        CHECK (active_broker_count >= 0
           AND net_buy_broker_count >= 0
           AND net_sell_broker_count >= 0
           AND net_buy_broker_count + net_sell_broker_count <= active_broker_count),
    CONSTRAINT "Feature_03_Stock_Broker_Daily_ratio_check"
        CHECK ((net_buy_broker_ratio IS NULL OR net_buy_broker_ratio BETWEEN 0 AND 1)
           AND (top3_buyer_share IS NULL OR top3_buyer_share BETWEEN 0 AND 1)
           AND (broker_concentration_hhi IS NULL OR broker_concentration_hhi > 0
                AND broker_concentration_hhi <= 1)),
    CONSTRAINT "Feature_03_Stock_Broker_Daily_dominant_check"
        CHECK ((top_buyer IS NULL) = (top_buyer_net_value IS NULL)
           AND (top_seller IS NULL) = (top_seller_net_value IS NULL)
           AND (top_buyer_net_value IS NULL OR top_buyer_net_value > 0)
           AND (top_seller_net_value IS NULL OR top_seller_net_value < 0)
           AND top3_buyer_net_value >= 0
           AND positive_net_value_total >= top3_buyer_net_value)
);

COMMENT ON TABLE public."Feature_03_Stock_Broker_Daily" IS
    'Stock-level daily broker structure and concentration by ticker and market board; Regular, Nego and Tunai never mix.';

DO $comments$
DECLARE item record;
BEGIN
    FOR item IN
        SELECT * FROM (VALUES
            ('date','Source transaction date for this ticker and market board.'),
            ('ticker','Source broker-summary Symbol, including instruments outside the current stock universe.'),
            ('market_board','Exact source board: Regular, Nego or Tunai; aggregates never mix boards.'),
            ('total_buy_value','Sum of all broker buy_value_1d for the ticker, date and board.'),
            ('total_sell_value','Sum of all broker sell_value_1d for the ticker, date and board.'),
            ('active_broker_count','Brokers with nonzero gross buy/sell value or lots on the ticker, date and board.'),
            ('net_buy_broker_count','Brokers whose aggregated daily net value is positive.'),
            ('net_sell_broker_count','Brokers whose aggregated daily net value is negative.'),
            ('net_buy_broker_ratio','net_buy_broker_count divided by active_broker_count; null when no broker is active.'),
            ('foreign_net_value','Sum of daily broker net value where current broker_type is Foreign.'),
            ('domestic_net_value','Sum of daily broker net value where current broker_type is Domestic.'),
            ('institutional_net_value','Sum of daily broker net value where current broker_classification is Institutional-heavy.'),
            ('retail_net_value','Sum of daily broker net value where current broker_classification is Retail-heavy.'),
            ('mixed_net_value','Sum of daily broker net value where current broker_classification is Mixed.'),
            ('niche_net_value','Sum of daily broker net value where current broker_classification is Niche.'),
            ('top_buyer','Positive-net broker with the greatest daily net value; ties use broker code ascending.'),
            ('top_buyer_net_value','Positive daily net value of top_buyer.'),
            ('top_seller','Negative-net broker with the lowest daily net value; ties use broker code ascending.'),
            ('top_seller_net_value','Negative daily net value of top_seller.'),
            ('top3_buyer_net_value','Sum of the three greatest positive broker net values, with fewer used when fewer exist.'),
            ('positive_net_value_total','Sum of every positive broker daily net value.'),
            ('top3_buyer_share','top3_buyer_net_value divided by positive_net_value_total; null when the denominator is zero.'),
            ('broker_concentration_hhi','Sum of squared absolute-net-flow weights across brokers; null when total absolute net value is zero.'),
            ('calculated_at','Database statement timestamp when the row was calculated.')
        ) AS definitions(column_name, definition)
    LOOP
        EXECUTE format('COMMENT ON COLUMN public.%I.%I IS %L',
            'Feature_03_Stock_Broker_Daily', item.column_name, item.definition);
    END LOOP;
END
$comments$;

CREATE FUNCTION public.refresh_feature_03_stock_broker_daily(
    p_changed_date date DEFAULT NULL,
    p_tickers text[] DEFAULT NULL
)
RETURNS bigint
LANGUAGE plpgsql
AS $function$
DECLARE
    v_rows bigint;
BEGIN
    IF p_tickers IS NOT NULL AND cardinality(p_tickers) = 0 THEN
        RETURN 0;
    END IF;

    PERFORM pg_advisory_xact_lock(hashtextextended('refresh_feature_03_stock_broker_daily', 0));

    DELETE FROM public."Feature_03_Stock_Broker_Daily" AS target
    WHERE (p_changed_date IS NULL OR target.date = p_changed_date)
      AND (p_tickers IS NULL OR target.ticker = ANY(p_tickers));

    WITH broker_daily AS (
        SELECT f.date, f.ticker, f.market_board, f.broker,
               p.broker_type, p.broker_classification,
               f.buy_value_1d, f.sell_value_1d, f.net_value_1d,
               (f.buy_value_1d <> 0 OR f.sell_value_1d <> 0
                OR f.buy_lots_1d <> 0 OR f.sell_lots_1d <> 0) AS is_active,
               row_number() OVER (
                   PARTITION BY f.date, f.ticker, f.market_board
                   ORDER BY f.net_value_1d DESC, f.broker ASC
               ) AS buy_rank
        FROM public."Feature_02_Broker_Rolling" AS f
        LEFT JOIN public."IDX_Broker_Profile" AS p
          ON p.broker_code = f.broker
        WHERE (p_changed_date IS NULL OR f.date = p_changed_date)
          AND (p_tickers IS NULL OR f.ticker = ANY(p_tickers))
    ), aggregated AS (
        SELECT date, ticker, market_board,
               sum(buy_value_1d) AS total_buy_value,
               sum(sell_value_1d) AS total_sell_value,
               count(*) FILTER (WHERE is_active)::smallint AS active_broker_count,
               count(*) FILTER (WHERE net_value_1d > 0)::smallint AS net_buy_broker_count,
               count(*) FILTER (WHERE net_value_1d < 0)::smallint AS net_sell_broker_count,
               coalesce(sum(net_value_1d) FILTER (WHERE broker_type = 'Foreign'), 0) AS foreign_net_value,
               coalesce(sum(net_value_1d) FILTER (WHERE broker_type = 'Domestic'), 0) AS domestic_net_value,
               coalesce(sum(net_value_1d) FILTER (WHERE broker_classification = 'Institutional-heavy'), 0) AS institutional_net_value,
               coalesce(sum(net_value_1d) FILTER (WHERE broker_classification = 'Retail-heavy'), 0) AS retail_net_value,
               coalesce(sum(net_value_1d) FILTER (WHERE broker_classification = 'Mixed'), 0) AS mixed_net_value,
               coalesce(sum(net_value_1d) FILTER (WHERE broker_classification = 'Niche'), 0) AS niche_net_value,
               (array_agg(broker ORDER BY net_value_1d DESC, broker ASC)
                    FILTER (WHERE net_value_1d > 0))[1] AS top_buyer,
               max(net_value_1d) FILTER (WHERE net_value_1d > 0) AS top_buyer_net_value,
               (array_agg(broker ORDER BY net_value_1d ASC, broker ASC)
                    FILTER (WHERE net_value_1d < 0))[1] AS top_seller,
               min(net_value_1d) FILTER (WHERE net_value_1d < 0) AS top_seller_net_value,
               coalesce(sum(net_value_1d) FILTER (WHERE net_value_1d > 0 AND buy_rank <= 3), 0) AS top3_buyer_net_value,
               coalesce(sum(net_value_1d) FILTER (WHERE net_value_1d > 0), 0) AS positive_net_value_total,
               sum(abs(net_value_1d)) AS absolute_net_value_total,
               sum(net_value_1d * net_value_1d) AS squared_net_value_total
        FROM broker_daily
        GROUP BY date, ticker, market_board
    )
    INSERT INTO public."Feature_03_Stock_Broker_Daily" (
        date, ticker, market_board, total_buy_value, total_sell_value,
        active_broker_count, net_buy_broker_count, net_sell_broker_count,
        net_buy_broker_ratio, foreign_net_value, domestic_net_value,
        institutional_net_value, retail_net_value, mixed_net_value, niche_net_value,
        top_buyer, top_buyer_net_value, top_seller, top_seller_net_value,
        top3_buyer_net_value, positive_net_value_total, top3_buyer_share,
        broker_concentration_hhi, calculated_at
    )
    SELECT date, ticker, market_board, total_buy_value, total_sell_value,
           active_broker_count, net_buy_broker_count, net_sell_broker_count,
           net_buy_broker_count::double precision / NULLIF(active_broker_count, 0),
           foreign_net_value, domestic_net_value,
           institutional_net_value, retail_net_value, mixed_net_value, niche_net_value,
           top_buyer, top_buyer_net_value, top_seller, top_seller_net_value,
           top3_buyer_net_value, positive_net_value_total,
           top3_buyer_net_value::double precision / NULLIF(positive_net_value_total, 0),
           squared_net_value_total::double precision
             / NULLIF(absolute_net_value_total::double precision
                      * absolute_net_value_total::double precision, 0),
           statement_timestamp()
    FROM aggregated;

    GET DIAGNOSTICS v_rows = ROW_COUNT;
    RETURN v_rows;
END
$function$;

COMMENT ON FUNCTION public.refresh_feature_03_stock_broker_daily(date,text[]) IS
    'Rebuilds Feature 03 for an exact changed date and optional ticker list; null date means all available history in scope.';

INSERT INTO public."Table_Catalog" (
    table_name, category, definition, grain, primary_key_columns,
    source_system, source_tables, source_code_paths, update_rule,
    related_functions, documentation_status
) VALUES (
    'Feature_03_Stock_Broker_Daily', 'Feature',
    'Stock-level daily broker breadth, classified flows, dominant brokers and net-flow concentration, separated by market board.',
    'One row per date, source ticker and Market Board',
    ARRAY['ticker','market_board','date'],
    'Validated Feature 02 broker daily flows and current IDX broker profile',
    ARRAY['Feature_02_Broker_Rolling','IDX_Broker_Profile'],
    ARRAY['database/migrations/20260913_009_create_feature_03_stock_broker_daily.sql',
          'scripts/backfill_feature_03.py'],
    'Backfill after Feature 02 validation; refresh the affected date/tickers after valid Broker Summary changes.',
    ARRAY['refresh_feature_03_stock_broker_daily(date,text[])'],
    'PARTIAL'
);

INSERT INTO public."Column_Catalog" (
    table_schema, table_name, column_name, ordinal_position, data_type,
    is_nullable, default_expression, is_primary_key, definition,
    source_code_paths, documentation_status
)
SELECT c.table_schema, c.table_name, c.column_name, c.ordinal_position,
       c.data_type, c.is_nullable = 'YES', c.column_default,
       c.column_name = ANY(ARRAY['ticker','market_board','date']),
       pg_catalog.col_description(rel.oid, att.attnum),
       ARRAY['database/migrations/20260913_009_create_feature_03_stock_broker_daily.sql',
             'scripts/backfill_feature_03.py'],
       'PARTIAL'
FROM information_schema.columns AS c
JOIN pg_catalog.pg_namespace AS n ON n.nspname = c.table_schema
JOIN pg_catalog.pg_class AS rel ON rel.relnamespace = n.oid AND rel.relname = c.table_name
JOIN pg_catalog.pg_attribute AS att ON att.attrelid = rel.oid AND att.attname = c.column_name
WHERE c.table_schema = 'public' AND c.table_name = 'Feature_03_Stock_Broker_Daily';

COMMIT;
