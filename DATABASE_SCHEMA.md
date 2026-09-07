# Database schema

Generated from PostgreSQL schema `public` at `2026-09-07T03:24:29+00:00`.

`Latest Data Date` is the newest business date represented in a table. `Last Changed At` is the latest tracked database change or completed load. `Last Checked At` is only the time this catalog inspected the table.

## Tables

| Table Name | Category | Update Pattern | Latest Data Date | Last Changed At | Tracking | Definition |
|---|---|---|---|---|---|---|
| `Database_Table_Status` | System | Automatic / daily documentation refresh | — | `2026-09-07 03:24:29+00:00` | System-managed | Tracks the data freshness, change time, and update pattern of each table. |
| `IDX_Broker_Profile` | Reference | Periodic / approximately annual | — | `2026-09-06 13:04:02+00:00` | Baseline; exact changes tracked from this time forward | Reference list of IDX broker codes, names, and domestic/foreign classification. |
| `IDX_Broker_Summary` | Transactional | Continuous / each loaded trading day | `2026-08-31` | `2026-09-07 03:23:30.435290+00:00` | Derived from table data and load log | Daily broker buy/sell activity by symbol, broker, investor type, and market board. |
| `IDX_Stock_Universe` | Reference | Periodic / when the listed universe changes | — | `2026-09-07 02:32:29.837245+00:00` | Tracked automatically | Reference universe of Indonesian listed securities and TradingView fundamentals. |
| `Monitoring_Price_ALL` | System | Twice daily alongside IDX price automation | `2026-09-07` | `2026-09-07 03:21:00.320830+00:00` | Derived from monitoring rows | Operational results for daily and recovery IDX price-update runs. |
| `Price_Stock_Indonesia_IDX` | Transactional | Periodic / when daily IDX prices are refreshed | `2026-09-07` | `2026-09-07 03:22:04.339332+00:00` | Latest date derived; future changes tracked automatically | Daily Indonesian stock OHLCV prices sourced from TradingView. |
| `Universe_Equity_Description` | Reference | Periodic / when equity descriptions change | — | `2026-09-06 13:21:52.115381+00:00` | Loaded from Universe_Equity_Description.xlsx; future changes tracked automatically | Reference descriptions and sector classifications for the Indonesian equity universe. |
| `stockbit_broker_summary_load_log` | System | Continuous / alongside broker-summary loads | `2026-08-31` | `2026-09-07 03:23:30.435290+00:00` | Derived from load log | Audit log used to resume and verify Stockbit broker-summary loads by date. |

## Logical relationships

These relationships are documented for analysis but are not enforced as PostgreSQL foreign keys.

| From | To | Relationship | Notes |
|---|---|---|---|
| `IDX_Broker_Summary."Broker"` | `IDX_Broker_Profile.broker_code` | Logical | Broker activity uses the broker-code reference. No database foreign key is enforced. |
| `IDX_Broker_Summary."Symbol"` | `IDX_Stock_Universe."Ticker"` | Logical | Broker activity symbols map to the stock universe when a matching ticker exists. No database foreign key is enforced. |
| `Universe_Equity_Description."Ticker"` | `IDX_Stock_Universe."Ticker"` | Logical one-to-one by ticker | Both reference tables describe the same listed security when a matching ticker exists. No database foreign key is enforced. |
| `Price_Stock_Indonesia_IDX.ticker` | `IDX_Stock_Universe."Ticker"` | Logical many-to-one by ticker | Daily price rows map to the stock universe when a matching ticker exists. No database foreign key is enforced. |
| `Monitoring_Price_ALL.asset_type` | `IDX_Stock_Universe."Security Type"` | Logical grouped snapshot | Monitoring rows group expected and missing ticker counts by the universe Security Type value. |
| `Monitoring_Price_ALL.update_for_date` | `Price_Stock_Indonesia_IDX.date` | Logical | A monitoring date describes the daily-price date targeted by an automation run. |

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

## IDX_Broker_Profile

Reference list of IDX broker codes, names, and domestic/foreign classification.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `broker_code` | `character varying` | No | — | Two-character IDX broker code. |
| `broker_name` | `text` | No | — | Registered broker or securities-company name. |
| `broker_type` | `text` | No | — | Broker classification: Domestic or Foreign. |

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

Daily broker buy/sell activity by symbol, broker, investor type, and market board.

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

Reference universe of Indonesian listed securities and TradingView fundamentals.

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

### Constraints

| Name | Type | Definition |
|---|---|---|
| `IDX_Stock_Universe_pkey` | Primary key | `PRIMARY KEY ("Ticker")` |

### Indexes

| Name | Definition |
|---|---|
| `IDX_Stock_Universe_pkey` | `CREATE UNIQUE INDEX "IDX_Stock_Universe_pkey" ON public."IDX_Stock_Universe" USING btree ("Ticker")` |

## Monitoring_Price_ALL

Operational results for daily and recovery IDX price-update runs.

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

Daily Indonesian stock OHLCV prices sourced from TradingView.

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

## Universe_Equity_Description

Reference descriptions and sector classifications for the Indonesian equity universe.

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

Audit log used to resume and verify Stockbit broker-summary loads by date.

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
