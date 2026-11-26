-- EXEC-SECTOR-ANALYSIS S1 rehearsal: definitions read from dev on 2026-11-26 (read-only, pgweb; no data): the columns,
-- checks, keys, indexes and catalog triggers of the tables migration 20261126_001 and the worker's Feature 08 step read or
-- write. Generated with a copy of verification/index_group_history/extract_ddl.py.
CREATE OR REPLACE FUNCTION public.set_database_catalog_updated_at()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
BEGIN
    NEW.updated_at := CURRENT_TIMESTAMP;
    RETURN NEW;
END
$function$
;
CREATE OR REPLACE FUNCTION public.validate_table_catalog_temporal_metadata()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
BEGIN
    IF NEW.observation_date_column IS NOT NULL
       AND NOT EXISTS (
           SELECT 1 FROM information_schema.columns
           WHERE table_schema = NEW.table_schema AND table_name = NEW.table_name
             AND column_name = NEW.observation_date_column
       ) THEN
        RAISE EXCEPTION 'Observation-date target %.%.% does not exist',
            NEW.table_schema, NEW.table_name, NEW.observation_date_column;
    END IF;
    IF NEW.data_available_at_column IS NOT NULL
       AND NOT EXISTS (
           SELECT 1 FROM information_schema.columns
           WHERE table_schema = NEW.table_schema AND table_name = NEW.table_name
             AND column_name = NEW.data_available_at_column
       ) THEN
        RAISE EXCEPTION 'Availability-time target %.%.% does not exist',
            NEW.table_schema, NEW.table_name, NEW.data_available_at_column;
    END IF;
    RETURN NEW;
END
$function$
;
CREATE OR REPLACE FUNCTION public.set_feature_catalog_updated_at()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
BEGIN
    NEW.updated_at := CURRENT_TIMESTAMP;
    RETURN NEW;
END
$function$
;
CREATE OR REPLACE FUNCTION public.validate_feature_catalog_target()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
BEGIN
    IF NEW.is_active THEN
        IF NEW.feature_table !~ '^Feature_[0-9]{2}_[A-Za-z0-9_]+$' THEN
            RAISE EXCEPTION 'Active Feature table name % is not governed', NEW.feature_table;
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='public' AND table_name=NEW.feature_table
              AND column_name=NEW.feature_column
        ) THEN
            RAISE EXCEPTION 'Active catalog target %.% does not exist',
                NEW.feature_table,NEW.feature_column;
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM public."Table_Catalog"
            WHERE table_schema='public' AND table_name=NEW.feature_table
              AND category='Feature' AND documentation_status='VERIFIED'
        ) THEN
            RAISE EXCEPTION 'Active Feature table % is not VERIFIED in Table_Catalog',NEW.feature_table;
        END IF;
    END IF;
    RETURN NEW;
END
$function$
;
CREATE TABLE public."Price_Stock_Indonesia_IDX" (
    "company_name" text NOT NULL,
    "ticker" character varying(12) NOT NULL,
    "tradingview_symbol" character varying(32) NOT NULL,
    "date" date NOT NULL,
    "open" numeric(24,8) NOT NULL,
    "high" numeric(24,8) NOT NULL,
    "low" numeric(24,8) NOT NULL,
    "close" numeric(24,8) NOT NULL,
    "volume" numeric(30,8),
    "source" character varying(64) NOT NULL,
    "query_date" date NOT NULL,
    "timeframe" character varying(32) NOT NULL,
    "ingestion_time" timestamp with time zone DEFAULT statement_timestamp(),
    "market_code" text NOT NULL,
    "source_bar_time" timestamp with time zone,
    "market_close_at" timestamp with time zone NOT NULL,
    "is_final" boolean DEFAULT false NOT NULL,
    "finalized_at" timestamp with time zone NOT NULL,
    CONSTRAINT "Price_Stock_Indonesia_IDX_pkey" PRIMARY KEY (ticker, date),
    CONSTRAINT "Price_Stock_Indonesia_IDX_finality_check" CHECK (((NOT is_final) OR (finalized_at >= market_close_at))),
    CONSTRAINT "price_stock_indonesia_IDX_check" CHECK (((low <= open) AND (open <= high))),
    CONSTRAINT "price_stock_indonesia_IDX_check1" CHECK (((low <= close) AND (close <= high))),
    CONSTRAINT "price_stock_indonesia_IDX_close_check" CHECK ((close >= (0)::numeric)),
    CONSTRAINT "price_stock_indonesia_IDX_high_check" CHECK ((high >= (0)::numeric)),
    CONSTRAINT "price_stock_indonesia_IDX_low_check" CHECK ((low >= (0)::numeric)),
    CONSTRAINT "price_stock_indonesia_IDX_open_check" CHECK ((open >= (0)::numeric)),
    CONSTRAINT "price_stock_indonesia_IDX_volume_check" CHECK ((volume >= (0)::numeric))
);
CREATE INDEX "Price_Stock_Indonesia_IDX_date_idx" ON public."Price_Stock_Indonesia_IDX" USING btree (date);
CREATE INDEX "Price_Stock_Indonesia_IDX_final_idx" ON public."Price_Stock_Indonesia_IDX" USING btree (ticker, date DESC) WHERE (is_final AND ((timeframe)::text = 'Daily'::text));
CREATE TABLE public."Feature_Index_Entity" (
    "ticker" text NOT NULL,
    "entity_kind" text NOT NULL,
    "name" text NOT NULL,
    "member_source" text NOT NULL,
    "list_key" text,
    "sector" text,
    "has_price" boolean NOT NULL,
    "rows_from" date,
    "created_at" timestamp with time zone DEFAULT now() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT "Feature_Index_Entity_pkey" PRIMARY KEY (ticker),
    CONSTRAINT "Feature_Index_Entity_kind_check" CHECK ((entity_kind = ANY (ARRAY['MARKET'::text, 'INDEX'::text, 'SECTOR'::text, 'GROUP'::text]))),
    CONSTRAINT "Feature_Index_Entity_price_check" CHECK ((has_price = (entity_kind <> 'GROUP'::text))),
    CONSTRAINT "Feature_Index_Entity_rows_from_check" CHECK (((rows_from IS NULL) = (entity_kind = 'MARKET'::text))),
    CONSTRAINT "Feature_Index_Entity_source_check" CHECK ((((member_source = 'ALL_SOURCE_SYMBOLS'::text) AND (entity_kind = 'MARKET'::text) AND (sector IS NULL)) OR ((member_source = 'STOCK_LIST'::text) AND (sector IS NULL) AND (((entity_kind = 'INDEX'::text) AND (list_key ~~ 'INDEX:%'::text)) OR ((entity_kind = 'GROUP'::text) AND (list_key ~~ 'KONGLO:%'::text)))) OR ((member_source = 'UNIVERSE_SECTOR'::text) AND (entity_kind = 'SECTOR'::text) AND (sector IS NOT NULL) AND (list_key IS NULL)))),
    CONSTRAINT "Feature_Index_Entity_ticker_check" CHECK ((ticker ~ '^[A-Z0-9]{1,12}$'::text))
);
CREATE TABLE public."IDX_Stock_Universe" (
    "Region" text NOT NULL,
    "Country" text NOT NULL,
    "Company Name" text NOT NULL,
    "Ticker" text NOT NULL,
    "Exchange" text NOT NULL,
    "TradingView Symbol" text NOT NULL,
    "TradingView URL" text NOT NULL,
    "Security Type" text NOT NULL,
    "Type Specs" text NOT NULL,
    "Is Common Stock" text NOT NULL,
    "TradingView Country" text NOT NULL,
    "Currency" text NOT NULL,
    "Fundamental Currency" text NOT NULL,
    "ISIN" text NOT NULL,
    "Sector" text NOT NULL,
    "Industry" text NOT NULL,
    "price_feed_daily" numeric(18,4),
    CONSTRAINT "IDX_Stock_Universe_pkey" PRIMARY KEY ("Ticker")
);
CREATE TABLE public."Feature_04_Technical_Indicator" (
    "ticker" text NOT NULL,
    "trade_date" date NOT NULL,
    "timeframe" text NOT NULL,
    "sma_20" double precision,
    "sma_50" double precision,
    "ema_12" double precision,
    "ema_26" double precision,
    "rsi_14" double precision,
    "macd" double precision,
    "macd_signal" double precision,
    "macd_histogram" double precision,
    "atr_14" double precision,
    "bb_upper_20" double precision,
    "bb_middle_20" double precision,
    "bb_lower_20" double precision,
    "cdl_piercing" integer,
    "cdl_morning_star" integer,
    "cdl_morning_doji_star" integer,
    "cdl_engulfing" integer,
    "cdl_3_white_soldiers" integer,
    "cdl_hammer" integer,
    "cdl_inverted_hammer" integer,
    "cdl_3_inside" integer,
    "cdl_3_outside" integer,
    "cdl_harami" integer,
    "cdl_harami_cross" integer,
    "cdl_dark_cloud_cover" integer,
    "cdl_evening_star" integer,
    "cdl_evening_doji_star" integer,
    "cdl_3_black_crows" integer,
    "cdl_shooting_star" integer,
    "cdl_hanging_man" integer,
    "cdl_doji" integer,
    "cdl_dragonfly_doji" integer,
    "cdl_gravestone_doji" integer,
    "cdl_marubozu" integer,
    "cdl_kicking" integer,
    "cdl_rise_fall_3_methods" integer,
    "cdl_mat_hold" integer,
    "cdl_hikkake" integer,
    "calculation_version" text NOT NULL,
    "calculated_at" timestamp with time zone NOT NULL,
    "adx_14" double precision,
    "ema_50" double precision,
    "ema_200" double precision,
    "inside_bar" integer,
    "smi" double precision,
    "tracking_high" integer,
    "tracking_low" integer,
    "temp_high" double precision,
    "temp_high_bar" integer,
    "temp_low" double precision,
    "temp_low_bar" integer,
    "last_swing_high" double precision,
    "break_swing_high" integer,
    "asset_type" text NOT NULL,
    "close" double precision NOT NULL,
    CONSTRAINT "Feature_04_Technical_Indicator_pkey" PRIMARY KEY (ticker, trade_date, timeframe, asset_type),
    CONSTRAINT "Feature_04_Technical_Indicator_asset_type_check" CHECK ((asset_type = ANY (ARRAY['equity'::text, 'bonds'::text]))),
    CONSTRAINT "Feature_04_Technical_Indicator_atr_14_check" CHECK (((atr_14 IS NULL) OR ((atr_14 > '-Infinity'::double precision) AND (atr_14 < 'Infinity'::double precision)))),
    CONSTRAINT "Feature_04_Technical_Indicator_atr_14_check1" CHECK (((atr_14 IS NULL) OR (atr_14 >= (0)::double precision))),
    CONSTRAINT "Feature_04_Technical_Indicator_bb_lower_20_check" CHECK (((bb_lower_20 IS NULL) OR ((bb_lower_20 > '-Infinity'::double precision) AND (bb_lower_20 < 'Infinity'::double precision)))),
    CONSTRAINT "Feature_04_Technical_Indicator_bb_middle_20_check" CHECK (((bb_middle_20 IS NULL) OR ((bb_middle_20 > '-Infinity'::double precision) AND (bb_middle_20 < 'Infinity'::double precision)))),
    CONSTRAINT "Feature_04_Technical_Indicator_bb_upper_20_check" CHECK (((bb_upper_20 IS NULL) OR ((bb_upper_20 > '-Infinity'::double precision) AND (bb_upper_20 < 'Infinity'::double precision)))),
    CONSTRAINT "Feature_04_Technical_Indicator_calculation_version_check" CHECK ((btrim(calculation_version) <> ''::text)),
    CONSTRAINT "Feature_04_Technical_Indicator_close_finite_check" CHECK (((close > '-Infinity'::double precision) AND (close < 'Infinity'::double precision))),
    CONSTRAINT "Feature_04_Technical_Indicator_close_nonnegative_check" CHECK ((close >= (0)::double precision)),
    CONSTRAINT "Feature_04_Technical_Indicator_ema_12_check" CHECK (((ema_12 IS NULL) OR ((ema_12 > '-Infinity'::double precision) AND (ema_12 < 'Infinity'::double precision)))),
    CONSTRAINT "Feature_04_Technical_Indicator_ema_26_check" CHECK (((ema_26 IS NULL) OR ((ema_26 > '-Infinity'::double precision) AND (ema_26 < 'Infinity'::double precision)))),
    CONSTRAINT "Feature_04_Technical_Indicator_macd_check" CHECK (((macd IS NULL) OR ((macd > '-Infinity'::double precision) AND (macd < 'Infinity'::double precision)))),
    CONSTRAINT "Feature_04_Technical_Indicator_macd_histogram_check" CHECK (((macd_histogram IS NULL) OR ((macd_histogram > '-Infinity'::double precision) AND (macd_histogram < 'Infinity'::double precision)))),
    CONSTRAINT "Feature_04_Technical_Indicator_macd_signal_check" CHECK (((macd_signal IS NULL) OR ((macd_signal > '-Infinity'::double precision) AND (macd_signal < 'Infinity'::double precision)))),
    CONSTRAINT "Feature_04_Technical_Indicator_rsi_14_check" CHECK (((rsi_14 IS NULL) OR ((rsi_14 > '-Infinity'::double precision) AND (rsi_14 < 'Infinity'::double precision)))),
    CONSTRAINT "Feature_04_Technical_Indicator_rsi_14_check1" CHECK (((rsi_14 IS NULL) OR ((rsi_14 >= (0)::double precision) AND (rsi_14 <= (100)::double precision)))),
    CONSTRAINT "Feature_04_Technical_Indicator_sma_20_check" CHECK (((sma_20 IS NULL) OR ((sma_20 > '-Infinity'::double precision) AND (sma_20 < 'Infinity'::double precision)))),
    CONSTRAINT "Feature_04_Technical_Indicator_sma_50_check" CHECK (((sma_50 IS NULL) OR ((sma_50 > '-Infinity'::double precision) AND (sma_50 < 'Infinity'::double precision)))),
    CONSTRAINT "Feature_04_Technical_Indicator_ticker_check" CHECK (((ticker = upper(btrim(ticker))) AND (ticker <> ''::text))),
    CONSTRAINT "Feature_04_Technical_Indicator_timeframe_check" CHECK ((timeframe = 'Daily'::text)),
    CONSTRAINT "feature04_adx_14_valid" CHECK (((adx_14 IS NULL) OR ((adx_14 >= (0)::double precision) AND (adx_14 <= (100)::double precision)))),
    CONSTRAINT "feature04_break_swing_high_valid" CHECK (((break_swing_high IS NULL) OR (break_swing_high = ANY (ARRAY[0, 1])))),
    CONSTRAINT "feature04_ema_200_finite" CHECK (((ema_200 IS NULL) OR ((ema_200 > '-Infinity'::double precision) AND (ema_200 < 'Infinity'::double precision)))),
    CONSTRAINT "feature04_ema_50_finite" CHECK (((ema_50 IS NULL) OR ((ema_50 > '-Infinity'::double precision) AND (ema_50 < 'Infinity'::double precision)))),
    CONSTRAINT "feature04_inside_bar_binary" CHECK (((inside_bar IS NULL) OR (inside_bar = ANY (ARRAY[0, 1])))),
    CONSTRAINT "feature04_last_swing_high_valid" CHECK (((last_swing_high IS NULL) OR ((last_swing_high > '-Infinity'::double precision) AND (last_swing_high < 'Infinity'::double precision)))),
    CONSTRAINT "feature04_smi_valid" CHECK (((smi IS NULL) OR ((smi > '-Infinity'::double precision) AND (smi < 'Infinity'::double precision)))),
    CONSTRAINT "feature04_temp_high_bar_valid" CHECK (((temp_high_bar IS NULL) OR (temp_high_bar >= 0))),
    CONSTRAINT "feature04_temp_high_valid" CHECK (((temp_high IS NULL) OR ((temp_high > '-Infinity'::double precision) AND (temp_high < 'Infinity'::double precision)))),
    CONSTRAINT "feature04_temp_low_bar_valid" CHECK (((temp_low_bar IS NULL) OR (temp_low_bar >= 0))),
    CONSTRAINT "feature04_temp_low_valid" CHECK (((temp_low IS NULL) OR ((temp_low > '-Infinity'::double precision) AND (temp_low < 'Infinity'::double precision)))),
    CONSTRAINT "feature04_tracking_high_valid" CHECK (((tracking_high IS NULL) OR (tracking_high = ANY (ARRAY[0, 1])))),
    CONSTRAINT "feature04_tracking_low_valid" CHECK (((tracking_low IS NULL) OR (tracking_low = ANY (ARRAY[0, 1]))))
);
CREATE INDEX "Feature_04_Technical_Indicator_trade_date_idx" ON public."Feature_04_Technical_Indicator" USING btree (trade_date);
CREATE TABLE public."Table_Catalog" (
    "table_schema" text DEFAULT 'public'::text NOT NULL,
    "table_name" text NOT NULL,
    "category" text NOT NULL,
    "definition" text,
    "grain" text,
    "primary_key_columns" text[] DEFAULT '{}'::text[] NOT NULL,
    "source_system" text,
    "source_tables" text[] DEFAULT '{}'::text[] NOT NULL,
    "source_code_paths" text[] DEFAULT '{}'::text[] NOT NULL,
    "update_rule" text,
    "related_functions" text[] DEFAULT '{}'::text[] NOT NULL,
    "documentation_status" text DEFAULT 'NEEDS_REVIEW'::text NOT NULL,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updated_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "readiness_mode" text DEFAULT 'NOT_APPLICABLE'::text NOT NULL,
    "readiness_date_column" text,
    "observation_date_column" text,
    "data_available_at_column" text,
    "availability_rule" text DEFAULT 'Not applicable.'::text NOT NULL,
    "point_in_time_status" text DEFAULT 'NOT_APPLICABLE'::text NOT NULL,
    "historical_metadata_method" text,
    CONSTRAINT "Table_Catalog_pkey" PRIMARY KEY (table_schema, table_name),
    CONSTRAINT "Table_Catalog_availability_rule_check" CHECK ((btrim(availability_rule) <> ''::text)),
    CONSTRAINT "Table_Catalog_definition_check" CHECK ((((definition IS NULL) AND (documentation_status = 'NEEDS_REVIEW'::text)) OR ((definition IS NOT NULL) AND (btrim(definition) <> ''::text)))),
    CONSTRAINT "Table_Catalog_documentation_status_check" CHECK ((documentation_status = ANY (ARRAY['VERIFIED'::text, 'PARTIAL'::text, 'NEEDS_REVIEW'::text]))),
    CONSTRAINT "Table_Catalog_name_check" CHECK ((btrim(table_name) <> ''::text)),
    CONSTRAINT "Table_Catalog_point_in_time_status_check" CHECK ((point_in_time_status = ANY (ARRAY['AVAILABLE'::text, 'PARTIAL'::text, 'UNAVAILABLE'::text, 'NOT_APPLICABLE'::text]))),
    CONSTRAINT "Table_Catalog_readiness_column_check" CHECK ((((readiness_mode = 'DATA_DATE'::text) AND (readiness_date_column IS NOT NULL) AND (btrim(readiness_date_column) <> ''::text)) OR ((readiness_mode <> 'DATA_DATE'::text) AND (readiness_date_column IS NULL)))),
    CONSTRAINT "Table_Catalog_readiness_mode_check" CHECK ((readiness_mode = ANY (ARRAY['DATA_DATE'::text, 'REFERENCE_STATE'::text, 'NOT_APPLICABLE'::text]))),
    CONSTRAINT "Table_Catalog_target_schema_check" CHECK ((table_schema = 'public'::text)),
    CONSTRAINT "Table_Catalog_timestamps_check" CHECK ((updated_at >= created_at))
);
CREATE TRIGGER "Table_Catalog_set_updated_at" BEFORE UPDATE ON public."Table_Catalog" FOR EACH ROW EXECUTE FUNCTION set_database_catalog_updated_at();
CREATE TRIGGER "Table_Catalog_validate_temporal_metadata" BEFORE INSERT OR UPDATE OF table_schema, table_name, observation_date_column, data_available_at_column ON public."Table_Catalog" FOR EACH ROW EXECUTE FUNCTION validate_table_catalog_temporal_metadata();
CREATE TABLE public."Column_Catalog" (
    "table_schema" text NOT NULL,
    "table_name" text NOT NULL,
    "column_name" text NOT NULL,
    "ordinal_position" integer NOT NULL,
    "data_type" text NOT NULL,
    "is_nullable" boolean NOT NULL,
    "default_expression" text,
    "is_primary_key" boolean NOT NULL,
    "definition" text,
    "source_column_or_expression" text,
    "unit" text,
    "null_rule" text,
    "source_code_paths" text[] DEFAULT '{}'::text[] NOT NULL,
    "documentation_status" text DEFAULT 'NEEDS_REVIEW'::text NOT NULL,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updated_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "Column_Catalog_pkey" PRIMARY KEY (table_schema, table_name, column_name),
    CONSTRAINT "Column_Catalog_definition_check" CHECK ((((definition IS NULL) AND (documentation_status = 'NEEDS_REVIEW'::text)) OR ((definition IS NOT NULL) AND (btrim(definition) <> ''::text)))),
    CONSTRAINT "Column_Catalog_documentation_status_check" CHECK ((documentation_status = ANY (ARRAY['VERIFIED'::text, 'PARTIAL'::text, 'NEEDS_REVIEW'::text]))),
    CONSTRAINT "Column_Catalog_name_check" CHECK (((btrim(column_name) <> ''::text) AND (btrim(data_type) <> ''::text))),
    CONSTRAINT "Column_Catalog_position_check" CHECK ((ordinal_position > 0)),
    CONSTRAINT "Column_Catalog_timestamps_check" CHECK ((updated_at >= created_at))
);
CREATE INDEX "Column_Catalog_status_idx" ON public."Column_Catalog" USING btree (documentation_status, table_name);
CREATE TRIGGER "Column_Catalog_set_updated_at" BEFORE UPDATE ON public."Column_Catalog" FOR EACH ROW EXECUTE FUNCTION set_database_catalog_updated_at();
CREATE TABLE public."Feature_Catalog" (
    "feature_table" text NOT NULL,
    "feature_column" text NOT NULL,
    "grain" text NOT NULL,
    "feature_category" text NOT NULL,
    "definition" text NOT NULL,
    "calculation" text NOT NULL,
    "source_tables" text NOT NULL,
    "source_columns" text NOT NULL,
    "lookback_window" text NOT NULL,
    "minimum_history" text NOT NULL,
    "unit" text NOT NULL,
    "null_rule" text NOT NULL,
    "refresh_trigger" text NOT NULL,
    "dependency_rule" text NOT NULL,
    "version" text DEFAULT 'v1'::text NOT NULL,
    "is_active" boolean DEFAULT true NOT NULL,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updated_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "semantic_role" text DEFAULT 'MEASURE'::text NOT NULL,
    "allowed_aggregations" text[] DEFAULT '{}'::text[] NOT NULL,
    "ranking_interpretation" text DEFAULT 'CONTEXTUAL'::text NOT NULL,
    "is_filterable" boolean DEFAULT true NOT NULL,
    "is_groupable" boolean DEFAULT false NOT NULL,
    "availability_rule" text DEFAULT 'Use no earlier than the next valid trading observation after observation date unless earlier source availability is documented.'::text NOT NULL,
    "point_in_time_safe" boolean DEFAULT false NOT NULL,
    "historical_metadata_warning" text,
    "analytical_interpretation" text NOT NULL,
    "recommended_use" text NOT NULL,
    "misuse_warning" text NOT NULL,
    "semantic_review_status" text NOT NULL,
    "validation_evidence" text[] NOT NULL,
    CONSTRAINT "Feature_Catalog_pkey" PRIMARY KEY (feature_table, feature_column, version),
    CONSTRAINT "Feature_Catalog_aggregations_check" CHECK ((allowed_aggregations <@ ARRAY['SUM'::text, 'AVG'::text, 'MEDIAN'::text, 'MIN'::text, 'MAX'::text, 'COUNT'::text, 'COUNT_DISTINCT'::text, 'PERCENTILE'::text, 'WEIGHTED_AVG'::text])),
    CONSTRAINT "Feature_Catalog_availability_rule_check" CHECK ((btrim(availability_rule) <> ''::text)),
    CONSTRAINT "Feature_Catalog_feature_category_check" CHECK ((feature_category = ANY (ARRAY['Identity'::text, 'Metadata'::text, 'Price'::text, 'Return'::text, 'Volatility'::text, 'Volume'::text, 'Price Positioning'::text, 'Broker Flow'::text, 'Broker Persistence'::text, 'Broker Abnormality'::text, 'Broker Concentration'::text, 'Broker Classification'::text, 'Historical Outcome'::text, 'Smart Money'::text, 'Data Quality'::text]))),
    CONSTRAINT "Feature_Catalog_ranking_interpretation_check" CHECK ((ranking_interpretation = ANY (ARRAY['HIGHER'::text, 'LOWER'::text, 'CONTEXTUAL'::text, 'NOT_APPLICABLE'::text]))),
    CONSTRAINT "Feature_Catalog_required_text_check" CHECK (((btrim(feature_table) <> ''::text) AND (btrim(feature_column) <> ''::text) AND (btrim(grain) <> ''::text) AND (btrim(feature_category) <> ''::text) AND (btrim(definition) <> ''::text) AND (btrim(calculation) <> ''::text) AND (btrim(source_tables) <> ''::text) AND (btrim(source_columns) <> ''::text) AND (btrim(lookback_window) <> ''::text) AND (btrim(minimum_history) <> ''::text) AND (btrim(unit) <> ''::text) AND (btrim(null_rule) <> ''::text) AND (btrim(refresh_trigger) <> ''::text) AND (btrim(dependency_rule) <> ''::text) AND (btrim(version) <> ''::text))),
    CONSTRAINT "Feature_Catalog_semantic_guidance_check" CHECK (((btrim(analytical_interpretation) <> ''::text) AND (btrim(recommended_use) <> ''::text) AND (btrim(misuse_warning) <> ''::text))),
    CONSTRAINT "Feature_Catalog_semantic_review_status_check" CHECK ((semantic_review_status = ANY (ARRAY['NEEDS_REVIEW'::text, 'SOURCE_VERIFIED'::text, 'CALCULATION_VERIFIED'::text]))),
    CONSTRAINT "Feature_Catalog_semantic_role_check" CHECK ((semantic_role = ANY (ARRAY['IDENTITY'::text, 'DIMENSION'::text, 'MEASURE'::text]))),
    CONSTRAINT "Feature_Catalog_timestamps_check" CHECK ((updated_at >= created_at)),
    CONSTRAINT "Feature_Catalog_validation_evidence_check" CHECK (((cardinality(validation_evidence) > 0) AND (array_position(validation_evidence, ''::text) IS NULL))),
    CONSTRAINT "Feature_Catalog_version_check" CHECK ((version ~ '^v[1-9][0-9]*$'::text))
);
CREATE UNIQUE INDEX "Feature_Catalog_one_active_definition_idx" ON public."Feature_Catalog" USING btree (feature_table, feature_column) WHERE is_active;
CREATE TRIGGER "Feature_Catalog_set_updated_at" BEFORE UPDATE ON public."Feature_Catalog" FOR EACH ROW EXECUTE FUNCTION set_feature_catalog_updated_at();
CREATE TRIGGER "Feature_Catalog_validate_target" BEFORE INSERT OR UPDATE OF feature_table, feature_column, is_active ON public."Feature_Catalog" FOR EACH ROW EXECUTE FUNCTION validate_feature_catalog_target();
CREATE TABLE public."Monitoring_Feature04" (
    "execution_id" text NOT NULL,
    "source_execution_id" text,
    "run_type" text NOT NULL,
    "trigger_source" text NOT NULL,
    "update_for_date" date,
    "price_notification_required" boolean DEFAULT true NOT NULL,
    "price_notification_sent_at" timestamp with time zone,
    "eligible_tickers" integer DEFAULT 0 NOT NULL,
    "completed_tickers" integer DEFAULT 0 NOT NULL,
    "failed_tickers" integer DEFAULT 0 NOT NULL,
    "blocked_tickers" integer DEFAULT 0 NOT NULL,
    "status" text DEFAULT 'OPEN'::text NOT NULL,
    "started_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "sealed_at" timestamp with time zone,
    "finished_at" timestamp with time zone,
    "last_error" text,
    "updated_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "source_monitor_table" text DEFAULT 'Monitoring_Price_ALL'::text NOT NULL,
    CONSTRAINT "Monitoring_Feature04_pkey" PRIMARY KEY (execution_id),
    CONSTRAINT "Monitoring_Feature04_check" CHECK (((eligible_tickers >= 0) AND (completed_tickers >= 0) AND (failed_tickers >= 0) AND (blocked_tickers >= 0))),
    CONSTRAINT "Monitoring_Feature04_execution_id_check" CHECK ((btrim(execution_id) <> ''::text)),
    CONSTRAINT "Monitoring_Feature04_run_type_check" CHECK ((run_type = ANY (ARRAY['DAILY'::text, 'RECOVERY'::text, 'RETRY_TICKER'::text, 'RETRY_COLUMN'::text, 'ADHOC'::text, 'RECONCILIATION'::text]))),
    CONSTRAINT "Monitoring_Feature04_source_monitor_table_check" CHECK ((source_monitor_table = ANY (ARRAY['Monitoring_Price_ALL'::text, 'Monitoring_Fixed_Income'::text]))),
    CONSTRAINT "Monitoring_Feature04_status_check" CHECK ((status = ANY (ARRAY['OPEN'::text, 'READY'::text, 'PROCESSING'::text, 'SUCCESS'::text, 'PARTIAL'::text, 'NEEDS_REVIEW'::text, 'FAILED'::text, 'SKIPPED'::text]))),
    CONSTRAINT "Monitoring_Feature04_trigger_source_check" CHECK ((trigger_source = ANY (ARRAY['SCHEDULED'::text, 'MANUAL'::text, 'TELEGRAM'::text, 'DATABASE'::text, 'RECONCILIATION'::text])))
);
CREATE INDEX "Monitoring_Feature04_status_idx" ON public."Monitoring_Feature04" USING btree (status, updated_at);
CREATE TABLE public."Equity_Market_Schedule" (
    "market_code" text NOT NULL,
    "exchange" text NOT NULL,
    "timezone_name" text NOT NULL,
    "session_close_local" time without time zone NOT NULL,
    "finality_delay_minutes" integer NOT NULL,
    "correction_lookback_sessions" integer DEFAULT 5 NOT NULL,
    "enabled" boolean DEFAULT true NOT NULL,
    "updated_at" timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    CONSTRAINT "Equity_Market_Schedule_exchange_key" UNIQUE (exchange),
    CONSTRAINT "Equity_Market_Schedule_pkey" PRIMARY KEY (market_code),
    CONSTRAINT "Equity_Market_Schedule_code_check" CHECK (((market_code = upper(btrim(market_code))) AND (market_code <> ''::text))),
    CONSTRAINT "Equity_Market_Schedule_correction_window_check" CHECK (((correction_lookback_sessions >= 1) AND (correction_lookback_sessions <= 20))),
    CONSTRAINT "Equity_Market_Schedule_delay_check" CHECK (((finality_delay_minutes >= 0) AND (finality_delay_minutes <= 360))),
    CONSTRAINT "Equity_Market_Schedule_exchange_check" CHECK (((exchange = upper(btrim(exchange))) AND (exchange <> ''::text))),
    CONSTRAINT "Equity_Market_Schedule_timezone_check" CHECK (((timezone_name = btrim(timezone_name)) AND (timezone_name <> ''::text)))
);
