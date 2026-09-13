# Database schema

Generated from PostgreSQL schema `public` at `2026-09-13T03:58:35+00:00`.

`Latest Data Date` is the newest business date represented in a table. `Last Changed At` is the latest tracked database change or completed load. `Last Checked At` is only the time this catalog inspected the table.

## Tables

| Table Name | Category | Update Pattern | Latest Data Date | Last Changed At | Tracking | Definition |
|---|---|---|---|---|---|---|
| `Column_Catalog` | Reference | After approved column metadata changes | — | `2026-09-13 03:56:13.759386+00:00` | Tracked automatically | Physical column inventory and evidence-graded semantic definitions for tables registered in Table_Catalog. |
| `Database_Table_Status` | System | Automatic / daily documentation refresh | — | `2026-09-13 03:58:35+00:00` | System-managed | Tracks the data freshness, change time, and update pattern of each table. |
| `Feature_01_Stock_Daily` | Feature | After validated daily-price changes | `2026-09-11` | `2026-09-12 14:47:03+00:00` | Derived from Price_Stock_Indonesia_IDX | Daily per-ticker price, return, volatility, volume, and drawdown features. |
| `Feature_Calculation_Log` | System | After completed worker attempts; worker not active | — | `2026-09-13 03:56:31+00:00` | Baseline only | Completed attempt and retry history for Feature 01 calculation work. |
| `Feature_Calculation_Queue` | System | After price upsert and worker transitions; integration not active | — | `2026-09-13 03:56:31+00:00` | Baseline only | Durable pending and completed Feature 01 calculation work per changed source candle. |
| `Feature_Catalog` | Reference | After each validated Feature schema change | — | `2026-09-12 17:09:34+00:00` | Baseline; exact changes tracked from this time forward | Versioned semantic definitions and formulas for validated Feature columns. |
| `Feature_Status` | System | After enqueue and worker transitions; integration not active | — | `2026-09-13 03:56:31+00:00` | Baseline only | Current Feature 01 calculation freshness and outstanding-work summary per ticker. |
| `IDX_Broker_Profile` | Reference | Periodic / approximately annual | — | `2026-09-10 07:23:34.854803+00:00` | Tracked automatically | Broker code and name, domestic/foreign type, and usage profile such as Institutional-heavy, Retail-heavy, Mixed, or Niche. |
| `IDX_Broker_Summary` | Transactional | Continuous / each loaded trading day | `2026-08-31` | `2026-09-09 14:41:15.160142+00:00` | Derived from table data and load log | Daily broker buy/sell values and lots by symbol, broker, investor type, and market board. |
| `IDX_Stock_Universe` | Reference | Periodic / when the listed universe changes | — | `2026-09-12 13:34:43.352522+00:00` | Tracked automatically | Current Indonesian listed-security universe, ticker identity, and classifications. |
| `Monitoring_Price_ALL` | System | Twice daily alongside IDX price automation | `2026-09-13` | `2026-09-12 23:01:58.271364+00:00` | Derived from monitoring rows | Per-execution grouped outcomes and completeness of DAILY and RECOVERY price runs. |
| `Price_Stock_Indonesia_IDX` | Transactional | Periodic / when daily IDX prices are refreshed | `2026-09-11` | `2026-09-11 10:05:26.641709+00:00` | Latest date derived; future changes tracked automatically | Daily Indonesian stock OHLCV candles sourced from TradingView. |
| `Table_Catalog` | Reference | After approved table metadata changes | — | `2026-09-13 03:56:13.722596+00:00` | Tracked automatically | Curated meanings, grain, provenance, and update contracts for approved public data tables; not a freshness monitor. |
| `Telegram_Command_Log` | System | Event-driven / when an authorized Telegram command is received | — | `2026-09-11 14:19:34.821458+00:00` | Tracked automatically | Inbound Telegram command audit and duplicate-prevention ledger. |
| `Telegram_Notification_Log` | System | Event-driven / after a monitored job completes | — | `2026-09-12 23:02:02.452075+00:00` | Tracked automatically | Outbound Telegram delivery state and anti-duplicate ledger. |
| `Universe_Equity_Description` | Reference | Periodic / when equity descriptions change | — | `2026-09-06 13:21:52.115381+00:00` | Loaded from Universe_Equity_Description.xlsx; future changes tracked automatically | Issuer descriptions and TradingView/curated sector and industry classifications. |
| `stockbit_broker_summary_load_log` | System | Continuous / alongside broker-summary loads | `2026-08-31` | `2026-09-09 16:55:55.713468+00:00` | Derived from load log | Per-trading-date Stockbit broker-summary load progress, retries, and review state. |

## Logical relationships

These relationships are documented for analysis but are not enforced as PostgreSQL foreign keys.

| From | To | Relationship | Notes |
|---|---|---|---|
| `Table_Catalog.(table_schema, table_name)` | `Approved physical public tables` | Governed semantic reference | Exactly the approved table set is registered; Database_Table_Status remains a separate freshness monitor. |
| `Column_Catalog.(table_schema, table_name)` | `Table_Catalog.(table_schema, table_name)` | Enforced foreign key | Each cataloged physical column belongs to a registered table; physical facts are reconciled from PostgreSQL. |
| `IDX_Broker_Summary."Broker"` | `IDX_Broker_Profile.broker_code` | Logical | Broker activity uses the broker-code reference. No database foreign key is enforced. |
| `IDX_Broker_Summary."Symbol"` | `IDX_Stock_Universe."Ticker"` | Logical | Broker activity symbols map to the stock universe when a matching ticker exists. No database foreign key is enforced. |
| `Universe_Equity_Description."Ticker"` | `IDX_Stock_Universe."Ticker"` | Logical one-to-one by ticker | Both reference tables describe the same listed security when a matching ticker exists. No database foreign key is enforced. |
| `Price_Stock_Indonesia_IDX.ticker` | `IDX_Stock_Universe."Ticker"` | Logical many-to-one by ticker | Daily price rows map to the stock universe when a matching ticker exists. No database foreign key is enforced. |
| `Feature_01_Stock_Daily.(ticker, date)` | `Price_Stock_Indonesia_IDX.(ticker, date)` | Logical one-to-one by ticker and trading date | Each feature row is derived from exactly one available price candle. No database foreign key is enforced. |
| `Feature_01_Stock_Daily.ticker` | `IDX_Stock_Universe."Ticker"` | Logical many-to-one by ticker | Feature classifications use the current Sector and Industry values from the stock universe. No database foreign key is enforced. |
| `Feature_Catalog.(feature_table, feature_column)` | `Locked Feature table physical columns` | Governed semantic reference | Active catalog rows are validated by trigger against exact physical columns in the public schema. |
| `Monitoring_Price_ALL.asset_type` | `IDX_Stock_Universe."Security Type"` | Logical grouped snapshot | Monitoring rows group expected and missing ticker counts by the universe Security Type value. |
| `Monitoring_Price_ALL.update_for_date` | `Price_Stock_Indonesia_IDX.date` | Logical | A monitoring date describes the daily-price date targeted by an automation run. |
| `Telegram_Notification_Log.source_execution_id` | `Monitoring_Price_ALL.execution_id` | Logical many-to-one by execution | The notifier reads all monitoring rows for one execution before sending and recording delivery. No database foreign key is enforced. |

## Column_Catalog

Physical column inventory and evidence-graded semantic definitions for tables registered in Table_Catalog.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `table_schema` | `text` | No | — | Physical PostgreSQL schema containing the cataloged column. |
| `table_name` | `text` | No | — | Exact case-sensitive physical table name. |
| `column_name` | `text` | No | — | Exact case-sensitive physical column name. |
| `ordinal_position` | `integer` | No | — | Column position in the physical table. |
| `data_type` | `text` | No | — | Physical PostgreSQL information_schema data type. |
| `is_nullable` | `boolean` | No | — | Whether PostgreSQL permits a NULL value in this column. |
| `default_expression` | `text` | Yes | — | Physical PostgreSQL default expression, when present. |
| `is_primary_key` | `boolean` | No | — | Whether the column participates in the primary key. |
| `definition` | `text` | Yes | — | Human-readable meaning of values stored in this column. |
| `source_column_or_expression` | `text` | Yes | — | Source reference or concise derivation; Feature_Catalog remains authoritative for detailed Feature formulas. |
| `unit` | `text` | Yes | — | Semantic unit, when applicable. |
| `null_rule` | `text` | Yes | — | Meaning or rule for a NULL value, when documented. |
| `source_code_paths` | `ARRAY` | No | `'{}'::text[]` | Repository paths supporting the column definition. |
| `documentation_status` | `text` | No | `'NEEDS_REVIEW'::text` | Semantic confidence only. Physical type, nullability, default, position, and primary-key membership are read from live PostgreSQL. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Timestamp when the catalog row was created. |
| `updated_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Timestamp when the catalog row was last changed. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `Column_Catalog_definition_check` | Check | `CHECK (definition IS NULL AND documentation_status = 'NEEDS_REVIEW'::text OR definition IS NOT NULL AND btrim(definition) <> ''::text)` |
| `Column_Catalog_documentation_status_check` | Check | `CHECK (documentation_status = ANY (ARRAY['VERIFIED'::text, 'PARTIAL'::text, 'NEEDS_REVIEW'::text]))` |
| `Column_Catalog_name_check` | Check | `CHECK (btrim(column_name) <> ''::text AND btrim(data_type) <> ''::text)` |
| `Column_Catalog_position_check` | Check | `CHECK (ordinal_position > 0)` |
| `Column_Catalog_timestamps_check` | Check | `CHECK (updated_at >= created_at)` |
| `Column_Catalog_table_fkey` | Foreign key | `FOREIGN KEY (table_schema, table_name) REFERENCES "Table_Catalog"(table_schema, table_name)` |
| `Column_Catalog_pkey` | Primary key | `PRIMARY KEY (table_schema, table_name, column_name)` |

### Indexes

| Name | Definition |
|---|---|
| `Column_Catalog_pkey` | `CREATE UNIQUE INDEX "Column_Catalog_pkey" ON public."Column_Catalog" USING btree (table_schema, table_name, column_name)` |
| `Column_Catalog_status_idx` | `CREATE INDEX "Column_Catalog_status_idx" ON public."Column_Catalog" USING btree (documentation_status, table_name)` |

## Database_Table_Status

Tracks the data freshness, change time, and update pattern of each table.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `Table Name` | `text` | No | — | Exact PostgreSQL table name in the public schema. |
| `Last Checked At` | `timestamp with time zone` | No | — | UTC timestamp when the catalog last inspected the table. |
| `Table Category` | `text` | No | `'Unclassified'::text` | Operational role: Reference, Transactional, or System. |
| `Update Pattern` | `text` | No | `'Unknown'::text` | Expected frequency or event that updates the table. |
| `Latest Data Date` | `date` | Yes | — | Latest business or trading date represented by the table, when applicable. |
| `Last Changed At` | `timestamp with time zone` | Yes | — | UTC timestamp of the latest tracked data load or table change. |
| `Tracking Status` | `text` | No | `'Baseline'::text` | Explains whether freshness is derived, tracked, or only a baseline. |
| `Last Operation` | `text` | Yes | — | Last tracked operation, such as LOAD, INSERT, UPDATE, DELETE, or TRUNCATE. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `Database_Table_Status_pkey` | Primary key | `PRIMARY KEY ("Table Name")` |

### Indexes

| Name | Definition |
|---|---|
| `Database_Table_Status_pkey` | `CREATE UNIQUE INDEX "Database_Table_Status_pkey" ON public."Database_Table_Status" USING btree ("Table Name")` |

## Feature_01_Stock_Daily

Daily per-ticker price, return, volatility, volume, and drawdown features.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `date` | `date` | No | — | Trading date of the source candle represented by the feature row. |
| `ticker` | `text` | No | — | Exact IDX ticker identifying the security represented by the feature row. |
| `close` | `numeric` | No | — | Closing price for the ticker on the trading date. |
| `volume` | `numeric` | No | — | Trading volume reported for the ticker on the trading date. |
| `sector` | `text` | No | — | Current Sector classification for the ticker; it is not point-in-time historical classification. |
| `industry` | `text` | No | — | Current Industry classification for the ticker; it is not point-in-time historical classification. |
| `close_1d_ago` | `numeric` | Yes | — | Closing price one prior valid trading observation earlier for the same ticker. |
| `close_5d_ago` | `numeric` | Yes | — | Closing price five prior valid trading observations earlier for the same ticker. |
| `close_20d_ago` | `numeric` | Yes | — | Closing price twenty prior valid trading observations earlier for the same ticker. |
| `close_60d_ago` | `numeric` | Yes | — | Closing price sixty prior valid trading observations earlier for the same ticker. |
| `return_1d_pct` | `double precision` | Yes | — | Percentage price return between the current close and the close one valid trading observation earlier for the same ticker. |
| `return_5d_pct` | `double precision` | Yes | — | Percentage price return between the current close and the close five valid trading observations earlier for the same ticker. |
| `return_20d_pct` | `double precision` | Yes | — | Percentage price return between the current close and the close twenty valid trading observations earlier for the same ticker. |
| `return_60d_pct` | `double precision` | Yes | — | Percentage price return between the current close and the close sixty valid trading observations earlier for the same ticker. |
| `abs_return_1d_pct` | `double precision` | Yes | — | Absolute magnitude of the one-trading-observation percentage return, without direction. |
| `volatility_5d_ann_pct` | `double precision` | Yes | — | Annualized sample standard deviation of the latest five valid daily decimal returns for the ticker, expressed as percent. |
| `volatility_20d_ann_pct` | `double precision` | Yes | — | Annualized sample standard deviation of the latest twenty valid daily decimal returns for the ticker, expressed as percent. |
| `volatility_60d_ann_pct` | `double precision` | Yes | — | Annualized sample standard deviation of the latest sixty valid daily decimal returns for the ticker, expressed as percent. |
| `volatility_5d_change_pct` | `double precision` | Yes | — | Percentage change in annualized five-return volatility versus its value five valid trading observations earlier. |
| `volatility_20d_change_pct` | `double precision` | Yes | — | Percentage change in annualized twenty-return volatility versus its value twenty valid trading observations earlier. |
| `volatility_60d_change_pct` | `double precision` | Yes | — | Percentage change in annualized sixty-return volatility versus its value sixty valid trading observations earlier. |
| `volume_avg_20d` | `double precision` | Yes | — | Average source trading volume over the latest twenty valid trading observations for the ticker. |
| `volume_std_20d` | `double precision` | Yes | — | Sample standard deviation of source trading volume over the latest twenty valid trading observations for the ticker. |
| `volume_ratio_20d` | `double precision` | Yes | — | Current trading volume divided by the average volume of the latest twenty valid trading observations. |
| `volume_zscore_20d` | `double precision` | Yes | — | Current trading-volume deviation from its latest twenty-observation average, measured in sample standard deviations. |
| `high_20d` | `numeric` | Yes | — | Highest closing price among the latest twenty valid trading observations for the ticker. |
| `high_60d` | `numeric` | Yes | — | Highest closing price among the latest sixty valid trading observations for the ticker. |
| `drawdown_20d_pct` | `double precision` | Yes | — | Percentage position of the current close below the highest close in the latest twenty valid trading observations. |
| `drawdown_60d_pct` | `double precision` | Yes | — | Percentage position of the current close below the highest close in the latest sixty valid trading observations. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `Feature_01_Stock_Daily_close_nonnegative` | Check | `CHECK (close >= 0::numeric)` |
| `Feature_01_Stock_Daily_ticker_not_blank` | Check | `CHECK (btrim(ticker) <> ''::text)` |
| `Feature_01_Stock_Daily_volume_nonnegative` | Check | `CHECK (volume >= 0::numeric)` |
| `Feature_01_Stock_Daily_pkey` | Primary key | `PRIMARY KEY (ticker, date)` |

### Indexes

| Name | Definition |
|---|---|
| `Feature_01_Stock_Daily_date_idx` | `CREATE INDEX "Feature_01_Stock_Daily_date_idx" ON public."Feature_01_Stock_Daily" USING btree (date)` |
| `Feature_01_Stock_Daily_pkey` | `CREATE UNIQUE INDEX "Feature_01_Stock_Daily_pkey" ON public."Feature_01_Stock_Daily" USING btree (ticker, date)` |

## Feature_Calculation_Log

Completed attempt and retry history for Feature 01 calculation work.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `id` | `bigint` | No | — | Unique completed-attempt record identifier. |
| `feature_table` | `text` | No | — | Target Feature table of the attempted work item. |
| `ticker` | `text` | No | — | Ticker of the attempted work item. |
| `price_date` | `date` | No | — | Source trading date of the attempted work item. |
| `source_ingestion_time` | `timestamp with time zone` | No | — | Source version captured by this worker attempt. |
| `attempt_no` | `integer` | No | — | Monotonic attempt number for this queue key. |
| `result` | `text` | No | — | Attempt outcome: SUCCESS, FAILED, or SUPERSEDED by newer source data. |
| `started_at` | `timestamp with time zone` | No | — | Time the worker attempt began. |
| `finished_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Time the worker attempt finished. |
| `rows_refreshed` | `integer` | Yes | — | Number of Feature rows refreshed, if measured by the worker. |
| `detail` | `text` | Yes | — | Concise outcome or error detail without credentials. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `Feature_Calculation_Log_attempt_check` | Check | `CHECK (attempt_no > 0)` |
| `Feature_Calculation_Log_result_check` | Check | `CHECK (result = ANY (ARRAY['SUCCESS'::text, 'FAILED'::text, 'SUPERSEDED'::text]))` |
| `Feature_Calculation_Log_rows_check` | Check | `CHECK (rows_refreshed IS NULL OR rows_refreshed >= 0)` |
| `Feature_Calculation_Log_time_check` | Check | `CHECK (finished_at >= started_at)` |
| `Feature_Calculation_Log_queue_fkey` | Foreign key | `FOREIGN KEY (feature_table, ticker, price_date) REFERENCES "Feature_Calculation_Queue"(feature_table, ticker, price_date)` |
| `Feature_Calculation_Log_pkey` | Primary key | `PRIMARY KEY (id)` |
| `Feature_Calculation_Log_attempt_key` | Unique | `UNIQUE (feature_table, ticker, price_date, attempt_no)` |

### Indexes

| Name | Definition |
|---|---|
| `Feature_Calculation_Log_attempt_key` | `CREATE UNIQUE INDEX "Feature_Calculation_Log_attempt_key" ON public."Feature_Calculation_Log" USING btree (feature_table, ticker, price_date, attempt_no)` |
| `Feature_Calculation_Log_pkey` | `CREATE UNIQUE INDEX "Feature_Calculation_Log_pkey" ON public."Feature_Calculation_Log" USING btree (id)` |
| `Feature_Calculation_Log_ticker_time_idx` | `CREATE INDEX "Feature_Calculation_Log_ticker_time_idx" ON public."Feature_Calculation_Log" USING btree (feature_table, ticker, started_at DESC)` |

## Feature_Calculation_Queue

Durable pending and completed Feature 01 calculation work per changed source candle.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `feature_table` | `text` | No | `'Feature_01_Stock_Daily'::text` | Target Feature table; currently restricted to Feature_01_Stock_Daily. |
| `ticker` | `text` | No | — | Ticker of the changed source candle. |
| `price_date` | `date` | No | — | Trading date of the changed source candle. |
| `source_ingestion_time` | `timestamp with time zone` | No | — | Source candle ingestion timestamp captured when the work item is enqueued. |
| `source_execution_id` | `text` | Yes | — | Optional source price-run execution identifier. |
| `status` | `text` | No | `'PENDING'::text` | Work state: PENDING, PROCESSING, DONE, or FAILED. |
| `attempt_count` | `integer` | No | `0` | Number of worker claims made for this queue key. |
| `next_attempt_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Earliest time when a pending or failed item may be claimed. |
| `claimed_at` | `timestamp with time zone` | Yes | — | Time the active worker claim began. |
| `claim_token` | `uuid` | Yes | — | Unique token of the active worker claim. |
| `claim_expires_at` | `timestamp with time zone` | Yes | — | Lease expiry of the active worker claim. |
| `last_error` | `text` | Yes | — | Concise error from the most recent failed attempt. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Time this queue key was first created. |
| `updated_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Time the queue row was last changed by the writer or worker. |
| `completed_at` | `timestamp with time zone` | Yes | — | Time the current source version completed Feature calculation. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `Feature_Calculation_Queue_attempt_check` | Check | `CHECK (attempt_count >= 0)` |
| `Feature_Calculation_Queue_claim_check` | Check | `CHECK ((status = 'PROCESSING'::text) = (claimed_at IS NOT NULL AND claim_token IS NOT NULL AND claim_expires_at IS NOT NULL))` |
| `Feature_Calculation_Queue_completion_check` | Check | `CHECK ((status = 'DONE'::text) = (completed_at IS NOT NULL))` |
| `Feature_Calculation_Queue_feature_check` | Check | `CHECK (feature_table = 'Feature_01_Stock_Daily'::text)` |
| `Feature_Calculation_Queue_status_check` | Check | `CHECK (status = ANY (ARRAY['PENDING'::text, 'PROCESSING'::text, 'DONE'::text, 'FAILED'::text]))` |
| `Feature_Calculation_Queue_timestamps_check` | Check | `CHECK (updated_at >= created_at)` |
| `Feature_Calculation_Queue_price_fkey` | Foreign key | `FOREIGN KEY (ticker, price_date) REFERENCES "Price_Stock_Indonesia_IDX"(ticker, date)` |
| `Feature_Calculation_Queue_pkey` | Primary key | `PRIMARY KEY (feature_table, ticker, price_date)` |

### Indexes

| Name | Definition |
|---|---|
| `Feature_Calculation_Queue_lease_idx` | `CREATE INDEX "Feature_Calculation_Queue_lease_idx" ON public."Feature_Calculation_Queue" USING btree (claim_expires_at) WHERE (status = 'PROCESSING'::text)` |
| `Feature_Calculation_Queue_pkey` | `CREATE UNIQUE INDEX "Feature_Calculation_Queue_pkey" ON public."Feature_Calculation_Queue" USING btree (feature_table, ticker, price_date)` |
| `Feature_Calculation_Queue_ready_idx` | `CREATE INDEX "Feature_Calculation_Queue_ready_idx" ON public."Feature_Calculation_Queue" USING btree (next_attempt_at, created_at) WHERE (status = ANY (ARRAY['PENDING'::text, 'FAILED'::text]))` |
| `Feature_Calculation_Queue_ticker_state_idx` | `CREATE INDEX "Feature_Calculation_Queue_ticker_state_idx" ON public."Feature_Calculation_Queue" USING btree (feature_table, ticker, status, price_date)` |

## Feature_Catalog

Versioned semantic definitions and formulas for validated Feature columns.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `feature_table` | `text` | No | — | Exact physical name of one of the four locked Feature tables. |
| `feature_column` | `text` | No | — | Exact physical PostgreSQL column name. |
| `grain` | `text` | No | — | Business grain represented by one row in the Feature table. |
| `feature_category` | `text` | No | — | Controlled semantic category for the feature. |
| `definition` | `text` | No | — | Human-readable meaning of the feature value. |
| `calculation` | `text` | No | — | Exact formula or ordered calculation logic used by the implementation. |
| `source_tables` | `text` | No | — | Pipe-delimited exact source-table names required by the calculation. |
| `source_columns` | `text` | No | — | Pipe-delimited exact source-column references used by the calculation. |
| `lookback_window` | `text` | No | — | Effective observation-based historical window. |
| `minimum_history` | `text` | No | — | Minimum valid observation history required for a usable value. |
| `unit` | `text` | No | — | Semantic unit of the feature value. |
| `null_rule` | `text` | No | — | Conditions under which the feature is NULL. |
| `refresh_trigger` | `text` | No | — | Upstream event that requires the feature to be recalculated. |
| `dependency_rule` | `text` | No | — | Upstream availability conditions required before the feature is valid. |
| `version` | `text` | No | `'v1'::text` | Semantic-definition version; material formula changes require a new version. |
| `is_active` | `boolean` | No | `true` | Whether AI analytics may use this catalog definition. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Timestamp when this semantic version was created. |
| `updated_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Timestamp of the latest metadata change, maintained by trigger. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `Feature_Catalog_feature_category_check` | Check | `CHECK (feature_category = ANY (ARRAY['Identity'::text, 'Metadata'::text, 'Price'::text, 'Return'::text, 'Volatility'::text, 'Volume'::text, 'Price Positioning'::text, 'Broker Flow'::text, 'Broker Persistence'::text, 'Broker Abnormality'::text, 'Broker Concentration'::text, 'Broker Classification'::text, 'Historical Outcome'::text, 'Smart Money'::text, 'Data Quality'::text]))` |
| `Feature_Catalog_feature_table_check` | Check | `CHECK (feature_table = ANY (ARRAY['Feature_01_Stock_Daily'::text, 'Feature_02_Broker_Rolling'::text, 'Feature_03_Stock_Broker_Daily'::text, 'Feature_04_Broker_Behavior_Profile'::text]))` |
| `Feature_Catalog_required_text_check` | Check | `CHECK (btrim(feature_table) <> ''::text AND btrim(feature_column) <> ''::text AND btrim(grain) <> ''::text AND btrim(feature_category) <> ''::text AND btrim(definition) <> ''::text AND btrim(calculation) <> ''::text AND btrim(source_tables) <> ''::text AND btrim(source_columns) <> ''::text AND btrim(lookback_window) <> ''::text AND btrim(minimum_history) <> ''::text AND btrim(unit) <> ''::text AND btrim(null_rule) <> ''::text AND btrim(refresh_trigger) <> ''::text AND btrim(dependency_rule) <> ''::text AND btrim(version) <> ''::text)` |
| `Feature_Catalog_timestamps_check` | Check | `CHECK (updated_at >= created_at)` |
| `Feature_Catalog_version_check` | Check | `CHECK (version ~ '^v[1-9][0-9]*$'::text)` |
| `Feature_Catalog_pkey` | Primary key | `PRIMARY KEY (feature_table, feature_column, version)` |

### Indexes

| Name | Definition |
|---|---|
| `Feature_Catalog_pkey` | `CREATE UNIQUE INDEX "Feature_Catalog_pkey" ON public."Feature_Catalog" USING btree (feature_table, feature_column, version)` |

## Feature_Status

Current Feature 01 calculation freshness and outstanding-work summary per ticker.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `feature_table` | `text` | No | `'Feature_01_Stock_Daily'::text` | Target Feature table; currently restricted to Feature_01_Stock_Daily. |
| `ticker` | `text` | No | — | Ticker summarized by this status row. |
| `latest_price_date` | `date` | No | — | Latest trading date observed for this ticker by the enqueue flow. |
| `latest_source_ingestion_time` | `timestamp with time zone` | No | — | Latest source ingestion timestamp observed by the enqueue flow. |
| `last_successful_source_ingestion_time` | `timestamp with time zone` | Yes | — | Latest source version covered by a validated Feature calculation. |
| `last_successful_price_date` | `date` | Yes | — | Latest trading date covered by a validated Feature calculation. |
| `last_calculated_at` | `timestamp with time zone` | Yes | — | Time of the latest validated Feature calculation. |
| `pending_count` | `integer` | No | `0` | Number of PENDING queue rows for this ticker. |
| `processing_count` | `integer` | No | `0` | Number of PROCESSING queue rows for this ticker. |
| `failed_count` | `integer` | No | `0` | Number of FAILED queue rows for this ticker. |
| `status` | `text` | No | `'PENDING'::text` | Current ticker state: PENDING, PROCESSING, SUCCESS, or FAILED. |
| `last_error` | `text` | Yes | — | Concise most recent calculation error for this ticker. |
| `updated_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Time this status summary was last changed. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `Feature_Status_counts_check` | Check | `CHECK (pending_count >= 0 AND processing_count >= 0 AND failed_count >= 0)` |
| `Feature_Status_feature_check` | Check | `CHECK (feature_table = 'Feature_01_Stock_Daily'::text)` |
| `Feature_Status_status_check` | Check | `CHECK (status = ANY (ARRAY['PENDING'::text, 'PROCESSING'::text, 'SUCCESS'::text, 'FAILED'::text]))` |
| `Feature_Status_success_check` | Check | `CHECK (status <> 'SUCCESS'::text OR pending_count = 0 AND processing_count = 0 AND failed_count = 0 AND last_successful_source_ingestion_time IS NOT NULL AND last_successful_source_ingestion_time >= latest_source_ingestion_time)` |
| `Feature_Status_pkey` | Primary key | `PRIMARY KEY (feature_table, ticker)` |

### Indexes

| Name | Definition |
|---|---|
| `Feature_Status_pkey` | `CREATE UNIQUE INDEX "Feature_Status_pkey" ON public."Feature_Status" USING btree (feature_table, ticker)` |
| `Feature_Status_state_idx` | `CREATE INDEX "Feature_Status_state_idx" ON public."Feature_Status" USING btree (feature_table, status, updated_at)` |

## IDX_Broker_Profile

Broker code and name, domestic/foreign type, and usage profile such as Institutional-heavy, Retail-heavy, Mixed, or Niche.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `broker_code` | `character varying` | No | — | Two-character IDX broker code. |
| `broker_name` | `text` | No | — | Registered broker or securities-company name. |
| `broker_type` | `text` | No | — | Broker classification: Domestic or Foreign. |
| `broker_classification` | `text` | Yes | — | Observed broker usage profile: Institutional-heavy, Retail-heavy, Mixed, or Niche; this is distinct from domestic/foreign broker_type. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `idx_broker_profile_code_format` | Check | `CHECK (broker_code::text ~ '^[A-Z0-9]{2}$'::text)` |
| `idx_broker_profile_name_not_blank` | Check | `CHECK (length(btrim(broker_name)) > 0)` |
| `idx_broker_profile_type_valid` | Check | `CHECK (broker_type = ANY (ARRAY['Domestic'::text, 'Foreign'::text]))` |
| `IDX_Broker_Profile_pkey` | Primary key | `PRIMARY KEY (broker_code)` |

### Indexes

| Name | Definition |
|---|---|
| `IDX_Broker_Profile_pkey` | `CREATE UNIQUE INDEX "IDX_Broker_Profile_pkey" ON public."IDX_Broker_Profile" USING btree (broker_code)` |

## IDX_Broker_Summary

Daily broker buy/sell values and lots by symbol, broker, investor type, and market board.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `Date` | `date` | No | — | Exchange trading date. |
| `Symbol` | `character varying` | No | — | IDX security ticker. |
| `Broker` | `character varying` | No | — | Two-character broker code. |
| `Investor Type` | `character varying` | No | — | Investor classification: Domestic or Foreign. |
| `Market Board` | `character varying` | No | — | IDX market board: Regular, Nego, or Tunai. |
| `Buy Value` | `numeric` | No | — | Gross purchase value for the key combination. |
| `Sell Value` | `numeric` | No | — | Gross sale value for the key combination. |
| `Net Value` | `numeric` | No | — | Buy Value minus Sell Value. |
| `Buy Lots` | `numeric` | No | — | Number of lots purchased. |
| `Sell Lots` | `numeric` | No | — | Number of lots sold. |
| `Net Lots` | `numeric` | No | — | Buy Lots minus Sell Lots. |
| `Avg Buy` | `numeric` | Yes | — | Average purchase price when supplied by Stockbit. |
| `Avg Sell` | `numeric` | Yes | — | Average sale price when supplied by Stockbit. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `IDX_Broker_Summary_avg_buy_check` | Check | `CHECK ("Avg Buy" IS NULL OR "Avg Buy" >= 0::numeric)` |
| `IDX_Broker_Summary_avg_sell_check` | Check | `CHECK ("Avg Sell" IS NULL OR "Avg Sell" >= 0::numeric)` |
| `IDX_Broker_Summary_broker_check` | Check | `CHECK ("Broker"::text ~ '^[A-Z0-9]{2}$'::text)` |
| `IDX_Broker_Summary_buy_lots_check` | Check | `CHECK ("Buy Lots" >= 0::numeric)` |
| `IDX_Broker_Summary_buy_value_check` | Check | `CHECK ("Buy Value" >= 0::numeric)` |
| `IDX_Broker_Summary_investor_type_check` | Check | `CHECK ("Investor Type"::text = ANY (ARRAY['Foreign'::character varying, 'Domestic'::character varying]::text[]))` |
| `IDX_Broker_Summary_market_board_check` | Check | `CHECK ("Market Board"::text = ANY (ARRAY['Regular'::character varying, 'Nego'::character varying, 'Tunai'::character varying]::text[]))` |
| `IDX_Broker_Summary_net_lots_check` | Check | `CHECK ("Net Lots" = ("Buy Lots" - "Sell Lots"))` |
| `IDX_Broker_Summary_net_value_check` | Check | `CHECK ("Net Value" = ("Buy Value" - "Sell Value"))` |
| `IDX_Broker_Summary_sell_lots_check` | Check | `CHECK ("Sell Lots" >= 0::numeric)` |
| `IDX_Broker_Summary_sell_value_check` | Check | `CHECK ("Sell Value" >= 0::numeric)` |
| `IDX_Broker_Summary_symbol_check` | Check | `CHECK (btrim("Symbol"::text) <> ''::text AND "Symbol"::text = upper("Symbol"::text))` |
| `IDX_Broker_Summary_pkey` | Primary key | `PRIMARY KEY ("Date", "Symbol", "Broker", "Investor Type", "Market Board")` |

### Indexes

| Name | Definition |
|---|---|
| `IDX_Broker_Summary_pkey` | `CREATE UNIQUE INDEX "IDX_Broker_Summary_pkey" ON public."IDX_Broker_Summary" USING btree ("Date", "Symbol", "Broker", "Investor Type", "Market Board")` |

## IDX_Stock_Universe

Current Indonesian listed-security universe, ticker identity, and classifications.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `Region` | `text` | No | — | Geographic market region. |
| `Country` | `text` | No | — | Country represented by the listing. |
| `Company Name` | `text` | No | — | Issuer or company name. |
| `Ticker` | `text` | No | — | IDX ticker and primary identifier for this table. |
| `Exchange` | `text` | No | — | Exchange on which the security is listed. |
| `TradingView Symbol` | `text` | No | — | Symbol used by TradingView. |
| `TradingView URL` | `text` | No | — | TradingView instrument page URL. |
| `Security Type` | `text` | No | — | Broad security classification. |
| `Type Specs` | `text` | No | — | More specific security-type detail. |
| `Is Common Stock` | `text` | No | — | Source flag indicating whether the security is common stock. |
| `TradingView Country` | `text` | No | — | Country value used by TradingView. |
| `Currency` | `text` | No | — | Trading currency. |
| `Fundamental Currency` | `text` | No | — | Currency used for fundamental figures. |
| `ISIN` | `text` | No | — | International Securities Identification Number. |
| `Sector` | `text` | No | — | Source sector classification. |
| `Industry` | `text` | No | — | Source industry classification. |
| `price_feed_daily` | `numeric` | Yes | — | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `IDX_Stock_Universe_pkey` | Primary key | `PRIMARY KEY ("Ticker")` |

### Indexes

| Name | Definition |
|---|---|
| `IDX_Stock_Universe_pkey` | `CREATE UNIQUE INDEX "IDX_Stock_Universe_pkey" ON public."IDX_Stock_Universe" USING btree ("Ticker")` |

## Monitoring_Price_ALL

Per-execution grouped outcomes and completeness of DAILY and RECOVERY price runs.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `id` | `bigint` | No | — | Generated monitoring-row identifier. |
| `exchange` | `text` | No | — | Exchange copied from IDX_Stock_Universe for the monitored group. |
| `asset_type` | `text` | No | — | Security Type copied from IDX_Stock_Universe for the monitored group. |
| `timeframe` | `text` | No | `'1d'::text` | TradingView interval; fixed to 1d. |
| `run_type` | `text` | No | — | Scheduled phase: DAILY at 17:00 WIB or RECOVERY at 06:00 WIB. |
| `expected_symbols` | `integer` | No | — | Distinct universe tickers in the exchange and asset-type group at run time. |
| `queried_symbols` | `integer` | No | — | Symbols sent to TradingView during this run. |
| `updated_symbols` | `integer` | No | — | Symbols verified in the price table after bulk upsert. |
| `missing_symbols` | `integer` | No | — | Queried symbols still missing after this run. |
| `missing_symbol_list` | `jsonb` | No | `'[]'::jsonb` | JSON array of tickers still missing after this run. |
| `update_for_date` | `date` | No | — | Trading date targeted by the run. |
| `run_time` | `timestamp with time zone` | No | — | UTC timestamp when the run started; display in Asia/Jakarta when needed. |
| `finished_at` | `timestamp with time zone` | No | — | UTC timestamp when the run completed. |
| `attempt_count` | `smallint` | No | — | Automation attempt number: 1 for DAILY and 2 for RECOVERY. |
| `status` | `text` | No | — | Run result: SUCCESS, PARTIAL, FAILED, SKIPPED, or NEEDS_REVIEW. |
| `last_error` | `text` | Yes | — | Condensed failure detail when a run did not fully succeed. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | UTC timestamp when the monitoring row was first created. |
| `updated_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | UTC timestamp when the monitoring row was last refreshed. |
| `execution_id` | `text` | No | — | Unique identifier shared by all asset-type rows written by one service execution. |
| `trigger_source` | `text` | No | — | Execution origin inferred by the service: SCHEDULED or MANUAL. |
| `query_time` | `timestamp with time zone` | No | — | UTC time immediately before the TradingView request begins. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `Monitoring_Price_ALL_attempt_check` | Check | `CHECK (run_type = 'DAILY'::text AND attempt_count = 1 OR run_type = 'RECOVERY'::text AND attempt_count = 2)` |
| `Monitoring_Price_ALL_counts_check` | Check | `CHECK (expected_symbols >= 0 AND queried_symbols >= 0 AND updated_symbols >= 0 AND missing_symbols >= 0 AND queried_symbols <= expected_symbols AND updated_symbols <= queried_symbols AND missing_symbols = (queried_symbols - updated_symbols))` |
| `Monitoring_Price_ALL_finished_check` | Check | `CHECK (finished_at >= run_time)` |
| `Monitoring_Price_ALL_missing_list_check` | Check | `CHECK (jsonb_typeof(missing_symbol_list) = 'array'::text)` |
| `Monitoring_Price_ALL_run_type_check` | Check | `CHECK (run_type = ANY (ARRAY['DAILY'::text, 'RECOVERY'::text]))` |
| `Monitoring_Price_ALL_status_check` | Check | `CHECK (status = ANY (ARRAY['SUCCESS'::text, 'PARTIAL'::text, 'FAILED'::text, 'SKIPPED'::text, 'NEEDS_REVIEW'::text]))` |
| `Monitoring_Price_ALL_timeframe_check` | Check | `CHECK (timeframe = '1d'::text)` |
| `Monitoring_Price_ALL_trigger_source_check` | Check | `CHECK (trigger_source = ANY (ARRAY['SCHEDULED'::text, 'MANUAL'::text]))` |
| `Monitoring_Price_ALL_pkey` | Primary key | `PRIMARY KEY (id)` |
| `Monitoring_Price_ALL_execution_key` | Unique | `UNIQUE (execution_id, exchange, asset_type, timeframe)` |

### Indexes

| Name | Definition |
|---|---|
| `Monitoring_Price_ALL_date_status_idx` | `CREATE INDEX "Monitoring_Price_ALL_date_status_idx" ON public."Monitoring_Price_ALL" USING btree (update_for_date DESC, status)` |
| `Monitoring_Price_ALL_execution_idx` | `CREATE INDEX "Monitoring_Price_ALL_execution_idx" ON public."Monitoring_Price_ALL" USING btree (update_for_date DESC, query_time DESC)` |
| `Monitoring_Price_ALL_execution_key` | `CREATE UNIQUE INDEX "Monitoring_Price_ALL_execution_key" ON public."Monitoring_Price_ALL" USING btree (execution_id, exchange, asset_type, timeframe)` |
| `Monitoring_Price_ALL_pkey` | `CREATE UNIQUE INDEX "Monitoring_Price_ALL_pkey" ON public."Monitoring_Price_ALL" USING btree (id)` |

## Price_Stock_Indonesia_IDX

Daily Indonesian stock OHLCV candles sourced from TradingView.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `company_name` | `text` | No | — | Listed company name. |
| `ticker` | `character varying` | No | — | Four-character IDX ticker. |
| `tradingview_symbol` | `character varying` | No | — | TradingView exchange-qualified symbol. |
| `date` | `date` | No | — | Trading date represented by the price row. |
| `open` | `numeric` | No | — | Opening price. |
| `high` | `numeric` | No | — | Highest price. |
| `low` | `numeric` | No | — | Lowest price. |
| `close` | `numeric` | No | — | Closing price. |
| `volume` | `numeric` | No | — | Trading volume reported by the source. |
| `source` | `character varying` | No | — | Price data source. |
| `query_date` | `date` | No | — | Date the source data was queried. |
| `timeframe` | `character varying` | No | — | Price-series interval. |
| `ingestion_time` | `timestamp with time zone` | Yes | `statement_timestamp()` | Timezone-aware database statement time of the latest successful insert or upsert; null for historical rows whose exact ingestion time is unknown. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `price_stock_indonesia_IDX_check` | Check | `CHECK (low <= open AND open <= high)` |
| `price_stock_indonesia_IDX_check1` | Check | `CHECK (low <= close AND close <= high)` |
| `price_stock_indonesia_IDX_close_check` | Check | `CHECK (close >= 0::numeric)` |
| `price_stock_indonesia_IDX_high_check` | Check | `CHECK (high >= 0::numeric)` |
| `price_stock_indonesia_IDX_low_check` | Check | `CHECK (low >= 0::numeric)` |
| `price_stock_indonesia_IDX_open_check` | Check | `CHECK (open >= 0::numeric)` |
| `price_stock_indonesia_IDX_volume_check` | Check | `CHECK (volume >= 0::numeric)` |
| `Price_Stock_Indonesia_IDX_pkey` | Primary key | `PRIMARY KEY (ticker, date)` |

### Indexes

| Name | Definition |
|---|---|
| `Price_Stock_Indonesia_IDX_date_idx` | `CREATE INDEX "Price_Stock_Indonesia_IDX_date_idx" ON public."Price_Stock_Indonesia_IDX" USING btree (date)` |
| `Price_Stock_Indonesia_IDX_pkey` | `CREATE UNIQUE INDEX "Price_Stock_Indonesia_IDX_pkey" ON public."Price_Stock_Indonesia_IDX" USING btree (ticker, date)` |

## Table_Catalog

Curated meanings, grain, provenance, and update contracts for approved public data tables; not a freshness monitor.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `table_schema` | `text` | No | `'public'::text` | Physical PostgreSQL schema containing the cataloged table. |
| `table_name` | `text` | No | — | Exact case-sensitive physical table name. |
| `category` | `text` | No | — | Operational role: Reference, Transactional, Feature, or System. |
| `definition` | `text` | Yes | — | Human-readable purpose and meaning of the table. |
| `grain` | `text` | Yes | — | Business entity represented by one table row. |
| `primary_key_columns` | `ARRAY` | No | `'{}'::text[]` | Ordered physical columns in the table primary key. |
| `source_system` | `text` | Yes | — | External system or internal process supplying the data, when known. |
| `source_tables` | `ARRAY` | No | `'{}'::text[]` | Physical upstream tables used to populate or derive the table. |
| `source_code_paths` | `ARRAY` | No | `'{}'::text[]` | Repository paths of relevant scripts and migrations. |
| `update_rule` | `text` | Yes | — | Event or process that changes table data. |
| `related_functions` | `ARRAY` | No | `'{}'::text[]` | PostgreSQL routines directly related to this table. |
| `documentation_status` | `text` | No | `'NEEDS_REVIEW'::text` | VERIFIED means checked against implementation and live schema; PARTIAL means supported but not fully verified; NEEDS_REVIEW means meaning is not established. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Timestamp when the catalog row was created. |
| `updated_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Timestamp when the catalog row was last changed. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `Table_Catalog_definition_check` | Check | `CHECK (definition IS NULL AND documentation_status = 'NEEDS_REVIEW'::text OR definition IS NOT NULL AND btrim(definition) <> ''::text)` |
| `Table_Catalog_documentation_status_check` | Check | `CHECK (documentation_status = ANY (ARRAY['VERIFIED'::text, 'PARTIAL'::text, 'NEEDS_REVIEW'::text]))` |
| `Table_Catalog_name_check` | Check | `CHECK (btrim(table_name) <> ''::text)` |
| `Table_Catalog_target_schema_check` | Check | `CHECK (table_schema = 'public'::text)` |
| `Table_Catalog_timestamps_check` | Check | `CHECK (updated_at >= created_at)` |
| `Table_Catalog_pkey` | Primary key | `PRIMARY KEY (table_schema, table_name)` |

### Indexes

| Name | Definition |
|---|---|
| `Table_Catalog_pkey` | `CREATE UNIQUE INDEX "Table_Catalog_pkey" ON public."Table_Catalog" USING btree (table_schema, table_name)` |

## Telegram_Command_Log

Inbound Telegram command audit and duplicate-prevention ledger.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `id` | `bigint` | No | — | Generated inbound-command identifier. |
| `telegram_update_id` | `bigint` | No | — | Unique Telegram update identifier; repeated webhook deliveries reuse the existing command row. |
| `chat_id` | `bigint` | No | — | Telegram chat that requested the action; only the configured owner is accepted. |
| `command` | `text` | No | — | Allowlisted action requested from the bot. |
| `target_service` | `text` | No | — | Fixed Railway service selected by the allowlisted command. |
| `requested_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | UTC timestamp when telegram-trigger accepted the update. |
| `triggered_at` | `timestamp with time zone` | Yes | — | UTC timestamp when Railway accepted the Run Now request. |
| `finished_at` | `timestamp with time zone` | Yes | — | UTC timestamp when a trigger request failed before Railway accepted it. |
| `status` | `text` | No | `'RECEIVED'::text` | Trigger state: RECEIVED, TRIGGERED, BLOCKED, or FAILED. |
| `railway_reference` | `text` | Yes | — | Allowlisted Railway service-instance identifier used for the Run Now request. |
| `last_error` | `text` | Yes | — | Cooldown reason or condensed trigger failure detail. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | UTC timestamp when the command row was created. |
| `updated_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | UTC timestamp when the command row was last changed. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `Telegram_Command_Log_command_not_blank` | Check | `CHECK (btrim(command) <> ''::text)` |
| `Telegram_Command_Log_status_check` | Check | `CHECK (status = ANY (ARRAY['RECEIVED'::text, 'TRIGGERED'::text, 'BLOCKED'::text, 'FAILED'::text]))` |
| `Telegram_Command_Log_target_not_blank` | Check | `CHECK (btrim(target_service) <> ''::text)` |
| `Telegram_Command_Log_pkey` | Primary key | `PRIMARY KEY (id)` |
| `Telegram_Command_Log_update_key` | Unique | `UNIQUE (telegram_update_id)` |

### Indexes

| Name | Definition |
|---|---|
| `Telegram_Command_Log_pkey` | `CREATE UNIQUE INDEX "Telegram_Command_Log_pkey" ON public."Telegram_Command_Log" USING btree (id)` |
| `Telegram_Command_Log_service_time_idx` | `CREATE INDEX "Telegram_Command_Log_service_time_idx" ON public."Telegram_Command_Log" USING btree (target_service, requested_at DESC)` |
| `Telegram_Command_Log_status_idx` | `CREATE INDEX "Telegram_Command_Log_status_idx" ON public."Telegram_Command_Log" USING btree (status, requested_at DESC)` |
| `Telegram_Command_Log_update_key` | `CREATE UNIQUE INDEX "Telegram_Command_Log_update_key" ON public."Telegram_Command_Log" USING btree (telegram_update_id)` |

## Telegram_Notification_Log

Outbound Telegram delivery state and anti-duplicate ledger.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `id` | `bigint` | No | — | Generated Telegram delivery-log identifier. |
| `source_table` | `text` | No | — | Monitoring table from which notification details are read. |
| `source_execution_id` | `text` | No | — | The execution_id from the source monitoring table; one completed run is sent once. |
| `notification_type` | `text` | No | `'COMPLETED'::text` | Notification event type; currently COMPLETED. |
| `send_status` | `text` | No | `'PENDING'::text` | Delivery state: PENDING, SENDING, SENT, or FAILED. |
| `attempt_count` | `integer` | No | `0` | Number of claimed Telegram delivery attempts. |
| `telegram_message_ids` | `jsonb` | No | `'[]'::jsonb` | JSON array of Telegram message IDs returned after delivery. |
| `sent_at` | `timestamp with time zone` | Yes | — | UTC timestamp when all Telegram message parts were sent. |
| `last_error` | `text` | Yes | — | Most recent Telegram delivery error; cleared after success. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | UTC timestamp when the delivery record was created. |
| `updated_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | UTC timestamp when the delivery record last changed. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `Telegram_Notification_Log_attempt_count_check` | Check | `CHECK (attempt_count >= 0)` |
| `Telegram_Notification_Log_status_check` | Check | `CHECK (send_status = ANY (ARRAY['PENDING'::text, 'SENDING'::text, 'SENT'::text, 'FAILED'::text]))` |
| `Telegram_Notification_Log_pkey` | Primary key | `PRIMARY KEY (id)` |
| `Telegram_Notification_Log_delivery_key` | Unique | `UNIQUE (source_table, source_execution_id, notification_type)` |

### Indexes

| Name | Definition |
|---|---|
| `Telegram_Notification_Log_delivery_key` | `CREATE UNIQUE INDEX "Telegram_Notification_Log_delivery_key" ON public."Telegram_Notification_Log" USING btree (source_table, source_execution_id, notification_type)` |
| `Telegram_Notification_Log_pkey` | `CREATE UNIQUE INDEX "Telegram_Notification_Log_pkey" ON public."Telegram_Notification_Log" USING btree (id)` |
| `Telegram_Notification_Log_status_idx` | `CREATE INDEX "Telegram_Notification_Log_status_idx" ON public."Telegram_Notification_Log" USING btree (send_status, updated_at DESC)` |

## Universe_Equity_Description

Issuer descriptions and TradingView/curated sector and industry classifications.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `Region` | `text` | No | — | Geographic market region. |
| `Market` | `text` | No | — | Market-development classification. |
| `Country` | `text` | No | — | Country represented by the listing. |
| `Exchange` | `text` | No | — | Exchange on which the security is listed. |
| `Ticker` | `text` | No | — | Four-character IDX ticker and primary identifier for this table. |
| `Company_Name` | `text` | No | — | Issuer or security name. |
| `TV_Sector` | `text` | No | — | TradingView sector classification. |
| `TV_Industry` | `text` | No | — | TradingView industry classification. |
| `ISIN` | `text` | No | — | Unique International Securities Identification Number. |
| `Sector` | `text` | No | — | IDX or curated sector classification. |
| `Industry` | `text` | No | — | IDX or curated industry classification. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `Universe_Equity_Description_pkey` | Primary key | `PRIMARY KEY ("Ticker")` |
| `Universe_Equity_Description_isin_key` | Unique | `UNIQUE ("ISIN")` |

### Indexes

| Name | Definition |
|---|---|
| `Universe_Equity_Description_isin_key` | `CREATE UNIQUE INDEX "Universe_Equity_Description_isin_key" ON public."Universe_Equity_Description" USING btree ("ISIN")` |
| `Universe_Equity_Description_pkey` | `CREATE UNIQUE INDEX "Universe_Equity_Description_pkey" ON public."Universe_Equity_Description" USING btree ("Ticker")` |

## stockbit_broker_summary_load_log

Per-trading-date Stockbit broker-summary load progress, retries, and review state.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `target_table` | `text` | No | — | Schema-qualified table populated by the load. |
| `trade_date` | `date` | No | — | Trading date covered by this load record. |
| `status` | `text` | No | — | Per-date state: COMPLETED or NEEDS_REVIEW. |
| `filter_count` | `integer` | No | — | Number of broker/investor/board combinations processed. |
| `request_count` | `integer` | No | — | Number of Stockbit API requests made. |
| `row_count` | `bigint` | No | — | Number of summary rows stored for the trading date. |
| `response_bytes` | `bigint` | No | — | Total Stockbit response payload size in bytes. |
| `fetch_elapsed_ms` | `bigint` | No | — | Cumulative API request duration in milliseconds. |
| `completed_at` | `timestamp with time zone` | Yes | — | UTC timestamp when the date completed successfully; null while NEEDS_REVIEW. |
| `attempt_count` | `integer` | No | `0` | Cumulative number of date-level attempts across supervisor restarts. |
| `last_error` | `text` | Yes | — | Most recent error for a date; cleared after a successful load. |
| `last_attempt_at` | `timestamp with time zone` | Yes | — | UTC timestamp of the latest attempt. |
| `status_changed_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | UTC timestamp when this date's status was last changed. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `stockbit_broker_summary_load_log_pkey` | Primary key | `PRIMARY KEY (target_table, trade_date)` |

### Indexes

| Name | Definition |
|---|---|
| `stockbit_broker_summary_load_log_pkey` | `CREATE UNIQUE INDEX stockbit_broker_summary_load_log_pkey ON public.stockbit_broker_summary_load_log USING btree (target_table, trade_date)` |
