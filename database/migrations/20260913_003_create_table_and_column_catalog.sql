BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '5min';

DO $preflight$
DECLARE
    required_tables text[] := ARRAY[
        'IDX_Stock_Universe',
        'Universe_Equity_Description',
        'IDX_Broker_Profile',
        'IDX_Broker_Summary',
        'Price_Stock_Indonesia_IDX',
        'Feature_01_Stock_Daily',
        'Feature_Catalog',
        'Monitoring_Price_ALL',
        'stockbit_broker_summary_load_log',
        'Telegram_Command_Log',
        'Telegram_Notification_Log'
    ];
    missing_tables text[];
BEGIN
    IF to_regclass('public."Table_Catalog"') IS NOT NULL
       OR to_regclass('public."Column_Catalog"') IS NOT NULL THEN
        RAISE EXCEPTION 'Table_Catalog or Column_Catalog already exists; migration was not applied';
    END IF;

    SELECT array_agg(name ORDER BY name)
    INTO missing_tables
    FROM unnest(required_tables) AS name
    WHERE to_regclass(format('%I.%I', 'public', name)) IS NULL;

    IF missing_tables IS NOT NULL THEN
        RAISE EXCEPTION 'Required source tables are missing: %', missing_tables;
    END IF;
END
$preflight$;

CREATE TABLE public."Table_Catalog" (
    table_schema text NOT NULL DEFAULT 'public',
    table_name text NOT NULL,
    category text NOT NULL,
    definition text,
    grain text,
    primary_key_columns text[] NOT NULL DEFAULT '{}',
    source_system text,
    source_tables text[] NOT NULL DEFAULT '{}',
    source_code_paths text[] NOT NULL DEFAULT '{}',
    update_rule text,
    related_functions text[] NOT NULL DEFAULT '{}',
    documentation_status text NOT NULL DEFAULT 'NEEDS_REVIEW',
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Table_Catalog_pkey" PRIMARY KEY (table_schema, table_name),
    CONSTRAINT "Table_Catalog_target_schema_check" CHECK (table_schema = 'public'),
    CONSTRAINT "Table_Catalog_name_check" CHECK (btrim(table_name) <> ''),
    CONSTRAINT "Table_Catalog_documentation_status_check"
        CHECK (documentation_status IN ('VERIFIED', 'PARTIAL', 'NEEDS_REVIEW')),
    CONSTRAINT "Table_Catalog_definition_check"
        CHECK (
            (definition IS NULL AND documentation_status = 'NEEDS_REVIEW')
            OR (definition IS NOT NULL AND btrim(definition) <> '')
        ),
    CONSTRAINT "Table_Catalog_timestamps_check" CHECK (updated_at >= created_at)
);

CREATE TABLE public."Column_Catalog" (
    table_schema text NOT NULL,
    table_name text NOT NULL,
    column_name text NOT NULL,
    ordinal_position integer NOT NULL,
    data_type text NOT NULL,
    is_nullable boolean NOT NULL,
    default_expression text,
    is_primary_key boolean NOT NULL,
    definition text,
    source_column_or_expression text,
    unit text,
    null_rule text,
    source_code_paths text[] NOT NULL DEFAULT '{}',
    documentation_status text NOT NULL DEFAULT 'NEEDS_REVIEW',
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Column_Catalog_pkey"
        PRIMARY KEY (table_schema, table_name, column_name),
    CONSTRAINT "Column_Catalog_table_fkey"
        FOREIGN KEY (table_schema, table_name)
        REFERENCES public."Table_Catalog" (table_schema, table_name),
    CONSTRAINT "Column_Catalog_name_check"
        CHECK (btrim(column_name) <> '' AND btrim(data_type) <> ''),
    CONSTRAINT "Column_Catalog_position_check" CHECK (ordinal_position > 0),
    CONSTRAINT "Column_Catalog_documentation_status_check"
        CHECK (documentation_status IN ('VERIFIED', 'PARTIAL', 'NEEDS_REVIEW')),
    CONSTRAINT "Column_Catalog_definition_check"
        CHECK (
            (definition IS NULL AND documentation_status = 'NEEDS_REVIEW')
            OR (definition IS NOT NULL AND btrim(definition) <> '')
        ),
    CONSTRAINT "Column_Catalog_timestamps_check" CHECK (updated_at >= created_at)
);

CREATE INDEX "Column_Catalog_status_idx"
    ON public."Column_Catalog" (documentation_status, table_name);

CREATE FUNCTION public.set_database_catalog_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
BEGIN
    NEW.updated_at := CURRENT_TIMESTAMP;
    RETURN NEW;
END
$function$;

CREATE TRIGGER "Table_Catalog_set_updated_at"
BEFORE UPDATE ON public."Table_Catalog"
FOR EACH ROW EXECUTE FUNCTION public.set_database_catalog_updated_at();

CREATE TRIGGER "Column_Catalog_set_updated_at"
BEFORE UPDATE ON public."Column_Catalog"
FOR EACH ROW EXECUTE FUNCTION public.set_database_catalog_updated_at();

COMMENT ON TABLE public."Table_Catalog" IS
    'Curated meanings, grain, provenance, and update contracts for the eleven approved public data tables; not a freshness monitor.';
COMMENT ON TABLE public."Column_Catalog" IS
    'Physical column inventory and evidence-graded semantic definitions for tables registered in Table_Catalog.';
COMMENT ON COLUMN public."Table_Catalog".documentation_status IS
    'VERIFIED means checked against implementation and live schema; PARTIAL means supported but not fully verified; NEEDS_REVIEW means meaning is not established.';
COMMENT ON COLUMN public."Column_Catalog".documentation_status IS
    'Semantic confidence only. Physical type, nullability, default, position, and primary-key membership are read from live PostgreSQL.';
COMMENT ON COLUMN public."Column_Catalog".source_column_or_expression IS
    'Source reference or concise derivation; Feature_Catalog remains authoritative for detailed Feature formulas.';

INSERT INTO public."Table_Catalog" (
    table_name, category, definition, grain, primary_key_columns,
    source_system, source_tables, source_code_paths, update_rule,
    related_functions, documentation_status
)
VALUES
    (
        'IDX_Stock_Universe', 'Reference',
        'Current Indonesian listed-security universe, ticker identity, and classifications.',
        'One current row per ticker', ARRAY['Ticker'],
        'TradingView and curated reference data', ARRAY['Universe_Equity_Description'],
        ARRAY['database/migrations/20260907_001_simplify_idx_stock_universe.sql',
              'apps/idx-price-cron/price_update.py'],
        'Updated when the listed universe or classifications change.',
        ARRAY[]::text[], 'PARTIAL'
    ),
    (
        'Universe_Equity_Description', 'Reference',
        'Issuer descriptions and TradingView/curated sector and industry classifications.',
        'One current row per ticker', ARRAY['Ticker'],
        'Universe_Equity_Description.xlsx', ARRAY[]::text[],
        ARRAY['database/migrations/20260907_001_simplify_idx_stock_universe.sql'],
        'Updated when equity descriptions or classifications change.',
        ARRAY[]::text[], 'PARTIAL'
    ),
    (
        'IDX_Broker_Profile', 'Reference',
        'Broker code and name, domestic/foreign type, and usage profile such as Institutional-heavy, Retail-heavy, Mixed, or Niche.',
        'One current row per broker code', ARRAY['broker_code'],
        NULL, ARRAY[]::text[], ARRAY[]::text[],
        'Updated when broker reference data or broker usage classification changes.',
        ARRAY[]::text[], 'PARTIAL'
    ),
    (
        'IDX_Broker_Summary', 'Transactional',
        'Daily broker buy/sell values and lots by symbol, broker, investor type, and market board.',
        'One row per date, symbol, broker, investor type, and market board',
        ARRAY['Date','Symbol','Broker','Investor Type','Market Board'],
        'Stockbit', ARRAY['IDX_Broker_Profile','IDX_Stock_Universe'],
        ARRAY['apps/stockbit-broker-backfill/stockbit_marketwide_broker_activity.py'],
        'Loaded by the Stockbit broker backfill or subsequent daily broker ingestion.',
        ARRAY[]::text[], 'PARTIAL'
    ),
    (
        'Price_Stock_Indonesia_IDX', 'Transactional',
        'Daily Indonesian stock OHLCV candles sourced from TradingView.',
        'One row per ticker and trading date', ARRAY['ticker','date'],
        'TradingView', ARRAY['IDX_Stock_Universe'],
        ARRAY['apps/idx-price-cron/price_update.py',
              'database/migrations/20260913_002_add_price_ingestion_time.sql'],
        'DAILY and RECOVERY price runs upsert exact-date candles.',
        ARRAY[]::text[], 'VERIFIED'
    ),
    (
        'Feature_01_Stock_Daily', 'Feature',
        'Daily per-ticker price, return, volatility, volume, and drawdown features.',
        'One row per ticker and trading date', ARRAY['ticker','date'],
        'PostgreSQL calculation', ARRAY['Price_Stock_Indonesia_IDX','IDX_Stock_Universe'],
        ARRAY['database/migrations/20260912_001_create_feature_01_stock_daily.sql'],
        'Explicit refresh routine after validated source changes; automatic price-cron integration is not active.',
        ARRAY['refresh_feature_01_stock_daily(date,text[])'], 'VERIFIED'
    ),
    (
        'Feature_Catalog', 'Reference',
        'Versioned semantic definitions and formulas for validated Feature columns.',
        'One row per feature table, feature column, and semantic version',
        ARRAY['feature_table','feature_column','version'],
        'PostgreSQL metadata', ARRAY['Feature_01_Stock_Daily'],
        ARRAY['database/migrations/20260913_001_create_feature_catalog.sql'],
        'Updated by a forward-only migration after a Feature definition or physical schema change.',
        ARRAY['set_feature_catalog_updated_at()','validate_feature_catalog_target()'], 'VERIFIED'
    ),
    (
        'Monitoring_Price_ALL', 'System',
        'Per-execution grouped outcomes and completeness of DAILY and RECOVERY price runs.',
        'One row per execution, exchange, asset type, and timeframe', ARRAY['id'],
        'IDX price automation', ARRAY['IDX_Stock_Universe','Price_Stock_Indonesia_IDX'],
        ARRAY['apps/idx-price-cron/price_update.py',
              'database/migrations/20260907_002_track_manual_price_runs.sql'],
        'Written after each DAILY or RECOVERY price execution.',
        ARRAY[]::text[], 'VERIFIED'
    ),
    (
        'stockbit_broker_summary_load_log', 'System',
        'Per-trading-date Stockbit broker-summary load progress, retries, and review state.',
        'One row per target table and trading date', ARRAY['target_table','trade_date'],
        'Stockbit broker backfill', ARRAY['IDX_Broker_Summary'],
        ARRAY['apps/stockbit-broker-backfill/stockbit_marketwide_broker_activity.py'],
        'Updated by each broker-summary load attempt.',
        ARRAY[]::text[], 'VERIFIED'
    ),
    (
        'Telegram_Command_Log', 'System',
        'Inbound Telegram command audit and duplicate-prevention ledger.',
        'One row per Telegram update ID', ARRAY['id'],
        'Telegram webhook', ARRAY[]::text[],
        ARRAY['apps/telegram-trigger/telegram_trigger.py',
              'database/migrations/20260909_002_create_telegram_command_log.sql'],
        'Written when an authorized Telegram command is received.',
        ARRAY[]::text[], 'VERIFIED'
    ),
    (
        'Telegram_Notification_Log', 'System',
        'Outbound Telegram delivery state and anti-duplicate ledger.',
        'One row per source table, execution ID, and notification type', ARRAY['id'],
        'Telegram notifier', ARRAY['Monitoring_Price_ALL'],
        ARRAY['apps/telegram-monitor/telegram_monitor.py',
              'database/migrations/20260909_001_create_telegram_notification_log.sql'],
        'Written when a completed monitoring execution is sent to Telegram.',
        ARRAY[]::text[], 'VERIFIED'
    );

INSERT INTO public."Column_Catalog" (
    table_schema, table_name, column_name, ordinal_position, data_type,
    is_nullable, default_expression, is_primary_key, source_code_paths
)
SELECT
    columns.table_schema,
    columns.table_name,
    columns.column_name,
    columns.ordinal_position,
    columns.data_type,
    columns.is_nullable = 'YES',
    columns.column_default,
    EXISTS (
        SELECT 1
        FROM information_schema.table_constraints AS constraint_definition
        JOIN information_schema.key_column_usage AS key_column
          ON key_column.constraint_catalog = constraint_definition.constraint_catalog
         AND key_column.constraint_schema = constraint_definition.constraint_schema
         AND key_column.constraint_name = constraint_definition.constraint_name
         AND key_column.table_schema = constraint_definition.table_schema
         AND key_column.table_name = constraint_definition.table_name
        WHERE constraint_definition.constraint_type = 'PRIMARY KEY'
          AND constraint_definition.table_schema = columns.table_schema
          AND constraint_definition.table_name = columns.table_name
          AND key_column.column_name = columns.column_name
    ),
    catalog.source_code_paths
FROM information_schema.columns AS columns
JOIN public."Table_Catalog" AS catalog
  ON catalog.table_schema = columns.table_schema
 AND catalog.table_name = columns.table_name;

DO $validate$
DECLARE
    table_count integer;
    physical_column_count integer;
    catalog_column_count integer;
BEGIN
    SELECT count(*) INTO table_count FROM public."Table_Catalog";
    SELECT count(*) INTO physical_column_count
    FROM information_schema.columns AS columns
    JOIN public."Table_Catalog" AS catalog
      ON catalog.table_schema = columns.table_schema
     AND catalog.table_name = columns.table_name;
    SELECT count(*) INTO catalog_column_count FROM public."Column_Catalog";

    IF table_count <> 11 OR physical_column_count <> catalog_column_count THEN
        RAISE EXCEPTION
            'Catalog seed failed: tables %, physical columns %, catalog columns %',
            table_count, physical_column_count, catalog_column_count;
    END IF;
END
$validate$;

COMMIT;
