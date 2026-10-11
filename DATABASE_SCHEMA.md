# Database schema

Generated from PostgreSQL schema `public` at `2026-10-11T14:43:29+00:00`.

`Latest Data Date` is the newest business date represented in a table. `Last Changed At` is the latest tracked database change or completed load. `Last Checked At` is only the time this catalog inspected the table.

## Tables

| Table Name | Category | Update Pattern | Latest Data Date | Last Changed At | Tracking | Definition |
|---|---|---|---|---|---|---|
| `AI_calculation_catalog` | Unclassified | Unknown | — | `2026-09-22 16:55:06+00:00` | Baseline only | AI-facing calculation contracts derived from active Feature Catalog definitions. |
| `AI_catalog_relationships` | Unclassified | Unknown | — | `2026-09-22 16:55:06+00:00` | Baseline only | AI-facing safe join and output-grain contracts across approved tables. |
| `AI_column_catalog` | Unclassified | Unknown | — | `2026-09-22 16:55:06+00:00` | Baseline only | AI-facing column meanings and bounded-query permissions for approved tables. |
| `AI_conversation` | Unclassified | Unknown | — | `2026-09-27 08:23:59+00:00` | Baseline only | One market-ai-orc chat box (history_mode SERVER): owner, retention and the single-active-run lease. |
| `AI_conversation_evidence` | Unclassified | Unknown | — | `2026-10-09 05:36:34+00:00` | Baseline only | A claim of a market-ai-orc answer recomputed by the backend (Governor summary or base table), with its status and at most 200 rows of evidence, kept for the life of the conversation (round 2026-10-03 D6). |
| `AI_conversation_execution` | Unclassified | Unknown | — | `2026-10-09 05:36:34+00:00` | Baseline only | The code of one sandbox execution of a market-ai-orc conversation, kept for the life of the conversation (R-STORE). |
| `AI_conversation_export` | Unclassified | Unknown | — | `2026-10-09 05:36:34+00:00` | Baseline only | A file exported from a market-ai-orc conversation for download (phase D), at most 20 MB. |
| `AI_conversation_output` | Unclassified | Unknown | — | `2026-10-09 05:36:34+00:00` | Baseline only | A released output of a market-ai-orc conversation, kept for the life of the conversation (R-STORE). |
| `AI_conversation_run_memory` | Unclassified | Unknown | — | `2026-10-09 05:36:34+00:00` | Baseline only | What each run of a market-ai-orc conversation leaves for the runs after it (EXEC-C): memo, full texts, citable sources, the model's note and its reasoning; deleted with the conversation. |
| `AI_conversation_turn` | Unclassified | Unknown | — | `2026-09-27 08:23:59+00:00` | Baseline only | One message of a market-ai-orc conversation and the response returned for it (history_mode SERVER). |
| `AI_data_coverage` | Unclassified | Unknown | — | `2026-09-22 16:55:06+00:00` | Baseline only | Automated raw-source coverage and explicitly inferred derived-table expectations; Feature 01-03 are never scanned by the coverage job. |
| `AI_formula_reference` | Unclassified | Unknown | — | `2026-09-24 09:22:02+00:00` | Baseline only | Reference calculation formulas for the orchestrator; documented definitions, not verified or executable implementations. |
| `AI_method_guide` | Unclassified | Unknown | — | `2026-10-09 05:36:34+00:00` | Baseline only | Model-facing menu and manual of the analysis paths and session helpers; generated from code, hash-bound (guides_sha256). Enforcement stays in code. |
| `AI_metric_catalog` | Unclassified | Unknown | — | `2026-10-09 05:36:34+00:00` | Baseline only | Official metrics for query_metric (one Governor summary per period); units and additivity are read from AI_column_catalog, never repeated here. |
| `AI_research_catalog` | Unclassified | Unknown | — | `2026-09-24 07:24:52+00:00` | Baseline only | Reference methods for the orchestrator; REFERENCE_ONLY does not imply installed sandbox code or validation. |
| `AI_research_library` | Unclassified | Unknown | — | `2026-10-09 05:36:34+00:00` | Baseline only | Model-facing description of the Multi-Angle Research methods the sandbox engines compute; generated from code, hash-bound (library_sha256). Enforcement stays in code. |
| `AI_research_run_audit` | Unclassified | Unknown | — | `2026-09-24 12:33:35+00:00` | Baseline only | One audit row per market-ai-orc run: question, final answer, evidence label, and experiments with their governor, validation and evidence decisions. Written once (INSERT only). |
| `AI_table_catalog` | Unclassified | Unknown | — | `2026-09-22 16:55:06+00:00` | Baseline only | AI-facing master list for the seven approved Indonesian equity data tables. |
| `Analysis_Evidence` | System | When compact evidence is recorded for an analysis | — | `2026-09-13 15:02:15+00:00` | Baseline only | Compact reproducible evidence supporting material AI analysis claims. |
| `Analysis_Model_Call` | System | One row after every provider model response; retained reasoning is purged by policy | — | `2026-09-14 03:49:36+00:00` | Baseline only | One durable audit row per provider model call. Provider-returned reasoning is retained temporarily; concise decision summary and usage remain for long-term audit. |
| `Analysis_Request` | System | One lifecycle per submitted AI analysis | — | `2026-09-13 15:02:15+00:00` | Baseline only | Durable AI analysis lifecycle, compact result, version snapshot, methodology metadata, and token usage. |
| `Analysis_Step_Log` | System | After each AI analysis tool or compaction step | — | `2026-09-13 15:02:15+00:00` | Baseline only | Audit record for each AI query, tool, compaction, or analytical step. |
| `Analytics_Dataset_Snapshot` | System | Per bounded analytics input; remove private object after terminal grace or expiry | — | `2026-09-14 07:39:52+00:00` | Baseline only | Metadata for immutable private bounded raw/Feature analytical input objects. Only the backend reads PostgreSQL; worker input objects expire quickly. |
| `Analytics_Job` | System | Per generic analytics submission, lease, result, or failure | — | `2026-09-14 07:39:52+00:00` | Baseline only | Durable isolated-worker queue. execution_class prevents a query-sandbox credential from claiming statistical jobs and vice versa. |
| `Column_Catalog` | Reference | After approved column metadata changes | — | `2026-10-11 14:38:13.427711+00:00` | Tracked automatically | Physical column inventory and evidence-graded semantic definitions for tables registered in Table_Catalog. |
| `Database_Table_Status` | System | Automatic / daily documentation refresh | — | `2026-10-11 14:43:29+00:00` | System-managed | Tracks the data freshness, change time, and update pattern of each table. |
| `Feature04_Calculation_Log` | System | After each Feature04 worker attempt | — | `2026-10-11 08:51:27+00:00` | Baseline only | Immutable Feature04 worker attempt history with per-group success/failure and retry lineage. |
| `Feature04_Calculation_Queue` | System | After relevant price changes and Feature04 worker transitions | — | `2026-10-11 08:51:27+00:00` | Baseline only | Durable coalesced Feature04 work per ticker/timeframe; generation tracks source change and work_revision tracks retry scope. |
| `Feature04_Column_Status` | System | After Feature04 validation or failure | — | `2026-10-11 08:51:27+00:00` | Baseline only | Current readiness/failure state for each Feature04 output column per ticker; expected NULL is a successful availability outcome. |
| `Feature04_Notification_Outbox` | System | After a Feature04 execution becomes terminal | — | `2026-10-11 08:51:27+00:00` | Baseline only | Durable Feature04 completion delivery request; calculation success never depends on Telegram availability. |
| `Feature04_Retry_Request` | System | When the owner requests an active failure retry | — | `2026-10-11 08:51:27+00:00` | Baseline only | Audited owner Telegram retry request for one failed ticker or failed indicator bundle. |
| `Feature_01_Stock_Daily` | Feature | After validated daily-price changes | `2026-10-09` | `2026-10-09 10:06:33.150795+00:00` | Derived from Price_Stock_Indonesia_IDX | Daily ticker-level price, return, volatility, volume, and price-position features derived from IDX prices and the current stock universe. |
| `Feature_02_Broker_Rolling` | Feature | After validated broker-summary changes; manual v2 ticker rebuild | `2026-08-31` | `2026-09-14 14:26:33.580099+00:00` | Derived from IDX_Broker_Summary; Investor-Type Feature 02 v2 refresh is manual | Canonical Feature 02 v2: one source ticker, broker, investor type, board and transaction date per row. Investor type is source investor identity, not broker domicile. |
| `Feature_03_Stock_Broker_Daily` | Feature | After Feature 02 refresh; manual Investor-Type v2 refresh | `2026-08-31` | `2026-09-14 15:17:23.131992+00:00` | Derived from Investor-Type Feature_02_Broker_Rolling; Feature 03 v2 refresh is manual | Feature 03 v2 stock-level broker structure by ticker and board. Domestic/Foreign flows use source Investor Type; broker-profile classifications are current metadata. Boards never mix. |
| `Feature_04_Technical_Indicator` | Feature | Event-driven after committed equity or bond price changes; full-history per asset/ticker | `2026-10-09` | `2026-10-11 13:55:17.102127+00:00` | Derived from price rows; changes queued and tracked per ticker | 57-column cross-asset Daily technical Feature04. Identity is asset_type/ticker/trade_date/timeframe; close is copied from the exact classified source row and the other measures are calculated per asset/ticker history. |
| `Feature_Calculation_Log` | System | After completed worker attempts | `2026-10-09` | `2026-10-09 10:06:33.159836+00:00` | Derived from attempt log rows | Completed attempt history for Feature 01 calculation queue items, including retries and superseded claims. |
| `Feature_Calculation_Queue` | System | After committed price inserts/updates and worker transitions | `2026-10-09` | `2026-10-09 10:06:33.099491+00:00` | Derived from queue rows | Durable Feature 01 work item per changed price candle; DONE means feature calculation succeeded, not price ingestion. |
| `Feature_Catalog` | Reference | After each validated Feature schema change | — | `2026-10-11 14:38:13.428279+00:00` | Tracked automatically | Machine-readable semantic and usage contract for validated Feature-table columns. |
| `Feature_Relationship_Catalog` | Reference | After a validated Feature join contract changes | — | `2026-09-13 15:02:15+00:00` | Baseline only | Versioned safe-join and grain contracts between verified Feature tables. |
| `Feature_Status` | System | After enqueue and worker state transitions | `2026-10-09` | `2026-10-09 10:06:33.099491+00:00` | Derived from per-ticker status rows | Current per-ticker Feature 01 calculation state; SUCCESS requires all committed source changes to be processed. |
| `Golden_Analysis_Test` | System | After a versioned golden analytical expectation changes | — | `2026-09-13 15:08:56+00:00` | Baseline only | Versioned analytical correctness and safety expectations; evaluation compares data and methodology rather than exact prose. |
| `Golden_Analysis_Test_Result` | System | After each test in a golden-suite run | — | `2026-09-13 15:08:56+00:00` | Baseline only | Per-test observed metrics, warnings, methodology checks, evidence and token usage. |
| `Golden_Analysis_Test_Run` | System | Before major releases and material model, prompt, Feature, or tool changes | — | `2026-09-13 15:08:56+00:00` | Baseline only | One complete regression-suite execution with immutable release/model/prompt/tool/Feature version context. |
| `IDX_Broker_Profile` | Reference | Periodic / approximately annual | — | `2026-09-10 07:23:34.854803+00:00` | Tracked automatically | Reference list of IDX broker codes, names, and domestic/foreign classification. |
| `IDX_Broker_Profile_History` | Reference | Captured after every write to IDX_Broker_Profile; never deleted | — | `2026-10-09 05:36:34+00:00` | Baseline; exact changes tracked from this time forward | Point-in-time history of IDX_Broker_Profile (name, broker_type, broker_classification), captured from the first capture onward: one row per broker version and knowledge version (bitemporal); superseded knowledge is kept. |
| `IDX_Broker_Summary` | Transactional | Continuous / each loaded trading day | `2026-08-31` | `2026-09-09 14:41:15.160142+00:00` | Derived from table data and load log | Daily broker buy/sell activity by symbol, broker, investor type, and market board. |
| `IDX_Stock_Universe` | Reference | Periodic / when the listed universe changes | — | `2026-10-02 18:07:58.944512+00:00` | Tracked automatically | Reference universe of Indonesian listed securities and TradingView fundamentals. |
| `IDX_Stock_Universe_History` | Reference | Captured after every write to IDX_Stock_Universe; never deleted | — | `2026-10-09 05:36:34+00:00` | Baseline; exact changes tracked from this time forward | Point-in-time history of the tracked IDX_Stock_Universe attributes, captured from the first capture onward: one row per ticker version and knowledge version (bitemporal); superseded knowledge is kept. |
| `Monitoring_Feature04` | Monitoring | Per automatic or Telegram Feature04 execution | — | `2026-10-11 08:51:27+00:00` | Baseline only | Feature04 batch/retry run summary and price-notification ordering gate. |
| `Monitoring_Feature04_Ticker` | Monitoring | Per eligible ticker in a Feature04 execution | — | `2026-10-11 08:51:27+00:00` | Baseline only | Per-ticker membership and terminal result for one Feature04 run. |
| `Monitoring_Fixed_Income` | Monitoring | One row after each fixed-income daily or recovery execution | `2026-10-11` | `2026-10-11 10:04:30.478506+00:00` | Derived from fixed-income cron monitoring rows | Operational result for one independent fixed-income daily or recovery cron execution. |
| `Monitoring_Price_ALL` | System | Twice daily alongside IDX price automation | `2026-10-11` | `2026-10-11 10:02:52.080137+00:00` | Derived from monitoring rows | Operational results for daily and recovery IDX price-update runs. |
| `Price_Fixed_Income` | Transactional | Daily and recovery fixed-income price/yield schedules | `2026-10-09` | `2026-10-11 09:38:18+00:00` | Latest date and write time derived from fixed-income observations | TradingView fixed-income OHLC observations separated by metric_type and Timeframe; Feature04 consumes price/1D only. |
| `Price_Stock_Indonesia_IDX` | Transactional | Periodic / when daily IDX prices are refreshed | `2026-10-09` | `2026-10-09 10:04:22.765289+00:00` | Latest date derived; future changes tracked automatically | Daily Indonesian stock OHLCV prices sourced from TradingView. |
| `Reference_History_Capture_Log` | System | One row per reference-history capture or correction | — | `2026-10-09 05:36:34+00:00` | Baseline; exact changes tracked from this time forward | One row per capture of a reference table into its history (trigger, initial, manual or correction): counts of changed and new versions, keys absent from the load, and the error of a failed capture. |
| `Table_Catalog` | Reference | After approved table metadata changes | — | `2026-10-11 14:38:13.425352+00:00` | Tracked automatically | Curated meanings, grain, provenance, and update contracts for approved public data tables; not a freshness monitor. |
| `Telegram_Command_Log` | System | Event-driven / when an authorized Telegram command is received | — | `2026-09-11 14:19:34.821458+00:00` | Tracked automatically | Inbound Telegram command audit and duplicate-prevention ledger for telegram-trigger. |
| `Telegram_Notification_Log` | System | Event-driven / after a monitored job completes | — | `2026-10-11 13:55:21.706787+00:00` | Tracked automatically | Delivery ledger used by telegram-monitor to prevent duplicate notifications. |
| `Tool_Catalog` | Reference | With each approved backend or analytics tool release | — | `2026-09-13 15:02:15+00:00` | Baseline only | Versioned tool registry and advertised operational ceilings. Backend and worker configuration remain the enforcement authority. |
| `Universe_Equity_Description` | Reference | Periodic / when equity descriptions change | — | `2026-10-02 18:07:58.949068+00:00` | Tracked automatically | Reference descriptions and sector classifications for the Indonesian equity universe. |
| `Universe_Fixed_income` | Reference | Periodic / when the fixed-income universe changes | — | `2026-10-11 14:01:27.117686+00:00` | Baseline only | Approved fixed-income instruments and their TradingView price/yield series classification. |
| `feature04_backfill_log` | Monitoring | Atomic per-run/ticker Feature04 calculation metadata | `2026-10-09` | `2026-10-11 06:25:12.790322+00:00` | Derived from completed atomic ticker loads; manual execution only | Atomic per-run/ticker Feature04 historical load metadata and resume fingerprints; no copied price or feature rows. Source hash is an extraction fingerprint, not point-in-time availability. |
| `stockbit_broker_summary_load_log` | System | Continuous / alongside broker-summary loads | `2026-08-31` | `2026-09-09 16:55:55.713468+00:00` | Derived from load log | Audit log used to resume and verify Stockbit broker-summary loads by date. |

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

## AI_calculation_catalog

AI-facing calculation contracts derived from active Feature Catalog definitions.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `calculation_name` | `text` | No | — | No column description has been recorded. |
| `version` | `text` | No | — | No column description has been recorded. |
| `target_table` | `text` | No | — | No column description has been recorded. |
| `target_columns` | `ARRAY` | No | — | No column description has been recorded. |
| `definition` | `text` | No | — | No column description has been recorded. |
| `required_inputs` | `jsonb` | No | — | No column description has been recorded. |
| `parameters` | `jsonb` | No | `'{}'::jsonb` | No column description has been recorded. |
| `defaults` | `jsonb` | No | `'{}'::jsonb` | No column description has been recorded. |
| `implementation_ref` | `ARRAY` | No | — | No column description has been recorded. |
| `alignment_rules` | `text` | No | — | No column description has been recorded. |
| `missing_data_policy` | `text` | No | — | No column description has been recorded. |
| `output_definition` | `jsonb` | No | — | No column description has been recorded. |
| `validation_evidence` | `ARRAY` | No | — | No column description has been recorded. |
| `status` | `text` | No | `'ACTIVE'::text` | No column description has been recorded. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | No column description has been recorded. |
| `updated_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `AI_calculation_catalog_json_check` | Check | `CHECK (jsonb_typeof(required_inputs) = 'object'::text AND jsonb_typeof(parameters) = 'object'::text AND jsonb_typeof(defaults) = 'object'::text AND jsonb_typeof(output_definition) = 'object'::text)` |
| `AI_calculation_catalog_status_check` | Check | `CHECK (status = ANY (ARRAY['ACTIVE'::text, 'INACTIVE'::text]))` |
| `AI_calculation_catalog_timestamp_check` | Check | `CHECK (updated_at >= created_at)` |
| `AI_calculation_catalog_version_check` | Check | `CHECK (version ~ '^v[1-9][0-9]*$'::text)` |
| `AI_calculation_catalog_table_fkey` | Foreign key | `FOREIGN KEY (target_table) REFERENCES "AI_table_catalog"(table_name) ON DELETE CASCADE` |
| `AI_calculation_catalog_pkey` | Primary key | `PRIMARY KEY (target_table, calculation_name, version)` |

### Indexes

| Name | Definition |
|---|---|
| `AI_calculation_catalog_pkey` | `CREATE UNIQUE INDEX "AI_calculation_catalog_pkey" ON public."AI_calculation_catalog" USING btree (target_table, calculation_name, version)` |

## AI_catalog_relationships

AI-facing safe join and output-grain contracts across approved tables.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `relationship_id` | `bigint` | No | — | No column description has been recorded. |
| `left_table` | `text` | No | — | No column description has been recorded. |
| `left_columns` | `ARRAY` | No | — | No column description has been recorded. |
| `right_table` | `text` | No | — | No column description has been recorded. |
| `right_columns` | `ARRAY` | No | — | No column description has been recorded. |
| `relationship_type` | `text` | No | — | No column description has been recorded. |
| `temporal_rule` | `text` | No | — | No column description has been recorded. |
| `safe_output_grain` | `text` | No | — | No column description has been recorded. |
| `requires_preaggregation` | `boolean` | No | `false` | No column description has been recorded. |
| `description` | `text` | No | — | No column description has been recorded. |
| `version` | `text` | No | `'v1'::text` | No column description has been recorded. |
| `is_allowed` | `boolean` | No | `true` | No column description has been recorded. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | No column description has been recorded. |
| `updated_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | No column description has been recorded. |
| `supported_join_semantics` | `ARRAY` | No | `'{}'::text[]` | Join semantics a DataNeedSpec may request for this relationship: CURRENT_STATE, EXACT_DATE, AS_OF, EFFECTIVE_DATED. |
| `left_time_column` | `text` | Yes | — | Time column of left_table that EXACT_DATE and AS_OF joins align on. |
| `right_time_column` | `text` | Yes | — | Time column of right_table that EXACT_DATE and AS_OF joins align on (AS_OF: latest value at or before the observation). |
| `effective_from_column` | `text` | Yes | — | Inclusive start of validity of a right_table row for EFFECTIVE_DATED joins. |
| `effective_to_column` | `text` | Yes | — | Exclusive end of validity of a right_table row for EFFECTIVE_DATED joins; NULL means still valid. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `AI_catalog_relationships_columns_check` | Check | `CHECK (cardinality(left_columns) > 0 AND cardinality(left_columns) = cardinality(right_columns))` |
| `AI_catalog_relationships_effective_columns_check` | Check | `CHECK (NOT ('EFFECTIVE_DATED'::text = ANY (supported_join_semantics)) OR effective_from_column IS NOT NULL AND effective_to_column IS NOT NULL)` |
| `AI_catalog_relationships_join_semantics_check` | Check | `CHECK (supported_join_semantics <@ ARRAY['CURRENT_STATE'::text, 'EXACT_DATE'::text, 'AS_OF'::text, 'EFFECTIVE_DATED'::text])` |
| `AI_catalog_relationships_temporal_columns_check` | Check | `CHECK (NOT supported_join_semantics && ARRAY['EXACT_DATE'::text, 'AS_OF'::text] OR left_time_column IS NOT NULL AND right_time_column IS NOT NULL)` |
| `AI_catalog_relationships_timestamp_check` | Check | `CHECK (updated_at >= created_at)` |
| `AI_catalog_relationships_type_check` | Check | `CHECK (relationship_type = ANY (ARRAY['ONE_TO_ONE'::text, 'ONE_TO_MANY'::text, 'MANY_TO_ONE'::text, 'MANY_TO_MANY'::text]))` |
| `AI_catalog_relationships_version_check` | Check | `CHECK (version ~ '^v[1-9][0-9]*$'::text)` |
| `AI_catalog_relationships_left_fkey` | Foreign key | `FOREIGN KEY (left_table) REFERENCES "AI_table_catalog"(table_name)` |
| `AI_catalog_relationships_right_fkey` | Foreign key | `FOREIGN KEY (right_table) REFERENCES "AI_table_catalog"(table_name)` |
| `AI_catalog_relationships_pkey` | Primary key | `PRIMARY KEY (relationship_id)` |
| `AI_catalog_relationships_unique` | Unique | `UNIQUE (left_table, right_table, version)` |

### Indexes

| Name | Definition |
|---|---|
| `AI_catalog_relationships_pkey` | `CREATE UNIQUE INDEX "AI_catalog_relationships_pkey" ON public."AI_catalog_relationships" USING btree (relationship_id)` |
| `AI_catalog_relationships_unique` | `CREATE UNIQUE INDEX "AI_catalog_relationships_unique" ON public."AI_catalog_relationships" USING btree (left_table, right_table, version)` |

## AI_column_catalog

AI-facing column meanings and bounded-query permissions for approved tables.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `table_name` | `text` | No | — | No column description has been recorded. |
| `column_name` | `text` | No | — | No column description has been recorded. |
| `ordinal_position` | `integer` | No | — | No column description has been recorded. |
| `description` | `text` | Yes | — | No column description has been recorded. |
| `data_type` | `text` | No | — | No column description has been recorded. |
| `semantic_type` | `text` | No | — | No column description has been recorded. |
| `unit` | `text` | Yes | — | No column description has been recorded. |
| `nullable` | `boolean` | No | — | No column description has been recorded. |
| `is_primary_key` | `boolean` | No | — | No column description has been recorded. |
| `source_column_or_expression` | `text` | Yes | — | No column description has been recorded. |
| `is_sensitive` | `boolean` | No | `false` | No column description has been recorded. |
| `ai_allowed` | `boolean` | No | `true` | No column description has been recorded. |
| `allowed_aggregations` | `ARRAY` | No | `'{}'::text[]` | No column description has been recorded. |
| `filter_allowed` | `boolean` | No | `true` | No column description has been recorded. |
| `group_by_allowed` | `boolean` | No | `false` | No column description has been recorded. |
| `example_value` | `text` | Yes | — | No column description has been recorded. |
| `coverage_required` | `boolean` | No | `false` | No column description has been recorded. |
| `documentation_status` | `text` | No | — | No column description has been recorded. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | No column description has been recorded. |
| `updated_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | No column description has been recorded. |
| `resample_aggregation` | `text` | Yes | — | Exact rule for aggregating this column to a coarser frequency (FIRST, LAST, MAX, MIN, SUM); NULL = not established, never pushed down. |
| `cross_entity_aggregation` | `text` | Yes | — | Rule for aggregating the column across entities of a finer grain (SUM, MIN, MAX); NULL means the column is not additive across entities and is never summed. Used by saniti.preaggregate before a relationship join and, since migration 20261002_002 (G18 phase 1), by a DataNeed request's aggregate: the SQL Governor computes SUM across entities only for a SUM rule (re-derived from its own catalog contract). Read through the Governor catalog contract and shown by get_catalog_details. |
| `value_time_basis` | `text` | No | — | HISTORICAL: the value belongs to its row's date (or version). CURRENT_STATE: today's reference value repeated on every row (current classification); a point-in-time DataNeedSpec may not read or filter it. |
| `description_id` | `text` | Yes | — | The column meaning in Indonesian, translated from description; description stays the source text. |
| `description_id_status` | `text` | Yes | — | DRAFT (machine translation, not yet reviewed) or REVIEWED; NULL when there is no translation. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `AI_column_catalog_aggregations_check` | Check | `CHECK (allowed_aggregations <@ ARRAY['SUM'::text, 'AVG'::text, 'MEDIAN'::text, 'MIN'::text, 'MAX'::text, 'COUNT'::text, 'COUNT_DISTINCT'::text, 'PERCENTILE'::text, 'WEIGHTED_AVG'::text])` |
| `AI_column_catalog_cross_entity_aggregation_check` | Check | `CHECK (cross_entity_aggregation IS NULL OR (cross_entity_aggregation = ANY (ARRAY['SUM'::text, 'MIN'::text, 'MAX'::text])))` |
| `AI_column_catalog_description_id_status_check` | Check | `CHECK (description_id IS NULL AND description_id_status IS NULL OR description_id IS NOT NULL AND (description_id_status = ANY (ARRAY['DRAFT'::text, 'REVIEWED'::text])))` |
| `AI_column_catalog_documentation_check` | Check | `CHECK (documentation_status = ANY (ARRAY['VERIFIED'::text, 'PARTIAL'::text, 'NEEDS_REVIEW'::text]))` |
| `AI_column_catalog_position_check` | Check | `CHECK (ordinal_position > 0)` |
| `AI_column_catalog_resample_aggregation_check` | Check | `CHECK (resample_aggregation IS NULL OR (resample_aggregation = ANY (ARRAY['FIRST'::text, 'LAST'::text, 'MAX'::text, 'MIN'::text, 'SUM'::text])))` |
| `AI_column_catalog_semantic_check` | Check | `CHECK (semantic_type = ANY (ARRAY['IDENTIFIER'::text, 'TIME'::text, 'DIMENSION'::text, 'MEASURE'::text]))` |
| `AI_column_catalog_timestamp_check` | Check | `CHECK (updated_at >= created_at)` |
| `AI_column_catalog_value_time_basis_check` | Check | `CHECK (value_time_basis = ANY (ARRAY['HISTORICAL'::text, 'CURRENT_STATE'::text]))` |
| `AI_column_catalog_table_fkey` | Foreign key | `FOREIGN KEY (table_name) REFERENCES "AI_table_catalog"(table_name) ON DELETE CASCADE` |
| `AI_column_catalog_pkey` | Primary key | `PRIMARY KEY (table_name, column_name)` |

### Indexes

| Name | Definition |
|---|---|
| `AI_column_catalog_pkey` | `CREATE UNIQUE INDEX "AI_column_catalog_pkey" ON public."AI_column_catalog" USING btree (table_name, column_name)` |

## AI_conversation

One market-ai-orc chat box (history_mode SERVER): owner, retention and the single-active-run lease.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `conversation_id` | `text` | No | — | No column description has been recorded. |
| `owner_key` | `text` | No | — | No column description has been recorded. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | No column description has been recorded. |
| `updated_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | No column description has been recorded. |
| `expires_at` | `timestamp with time zone` | No | — | No column description has been recorded. |
| `next_turn_index` | `integer` | No | `0` | No column description has been recorded. |
| `active_request_id` | `text` | Yes | — | No column description has been recorded. |
| `lease_generation` | `bigint` | No | `0` | No column description has been recorded. |
| `lease_expires_at` | `timestamp with time zone` | Yes | — | No column description has been recorded. |
| `state` | `jsonb` | No | `'{}'::jsonb` | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `ai_conversation_expiry_check` | Check | `CHECK (expires_at > created_at)` |
| `ai_conversation_id_check` | Check | `CHECK (conversation_id ~ '^conv_[0-9a-f]{32}$'::text)` |
| `ai_conversation_lease_check` | Check | `CHECK ((active_request_id IS NULL) = (lease_expires_at IS NULL))` |
| `ai_conversation_owner_check` | Check | `CHECK (owner_key ~ '^[A-Za-z0-9._:@-]{1,128}$'::text)` |
| `ai_conversation_state_check` | Check | `CHECK (jsonb_typeof(state) = 'object'::text)` |
| `ai_conversation_turn_index_check` | Check | `CHECK (next_turn_index >= 0 AND lease_generation >= 0)` |
| `AI_conversation_pkey` | Primary key | `PRIMARY KEY (conversation_id)` |

### Indexes

| Name | Definition |
|---|---|
| `AI_conversation_pkey` | `CREATE UNIQUE INDEX "AI_conversation_pkey" ON public."AI_conversation" USING btree (conversation_id)` |
| `ai_conversation_expiry_idx` | `CREATE INDEX ai_conversation_expiry_idx ON public."AI_conversation" USING btree (expires_at)` |
| `ai_conversation_owner_idx` | `CREATE INDEX ai_conversation_owner_idx ON public."AI_conversation" USING btree (owner_key, updated_at DESC)` |

## AI_conversation_evidence

A claim of a market-ai-orc answer recomputed by the backend (Governor summary or base table), with its status and at most 200 rows of evidence, kept for the life of the conversation (round 2026-10-03 D6).

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `evidence_id` | `text` | No | — | No column description has been recorded. |
| `conversation_id` | `text` | No | — | No column description has been recorded. |
| `request_id` | `text` | No | — | No column description has been recorded. |
| `claim` | `text` | No | — | No column description has been recorded. |
| `value_text` | `text` | No | — | No column description has been recorded. |
| `kind` | `text` | No | — | No column description has been recorded. |
| `recipe` | `jsonb` | No | — | No column description has been recorded. |
| `status` | `text` | No | — | No column description has been recorded. |
| `backend_value` | `double precision` | Yes | — | No column description has been recorded. |
| `difference` | `double precision` | Yes | — | No column description has been recorded. |
| `source` | `jsonb` | No | `'{}'::jsonb` | No column description has been recorded. |
| `rows` | `jsonb` | No | `'[]'::jsonb` | No column description has been recorded. |
| `rows_matched` | `bigint` | Yes | — | No column description has been recorded. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `ai_conversation_evidence_claim_check` | Check | `CHECK (length(claim) >= 1 AND length(claim) <= 300 AND length(value_text) >= 1 AND length(value_text) <= 40)` |
| `ai_conversation_evidence_id_check` | Check | `CHECK (evidence_id ~ '^evd_[0-9a-f]{24}$'::text)` |
| `ai_conversation_evidence_json_check` | Check | `CHECK (jsonb_typeof(recipe) = 'object'::text AND jsonb_typeof(source) = 'object'::text AND jsonb_typeof(rows) = 'array'::text AND jsonb_array_length(rows) <= 200)` |
| `ai_conversation_evidence_kind_check` | Check | `CHECK (kind = ANY (ARRAY['WAREHOUSE'::text, 'BASE_TABLE'::text]))` |
| `ai_conversation_evidence_request_check` | Check | `CHECK (request_id ~ '^[A-Za-z0-9._:-]{1,200}$'::text)` |
| `ai_conversation_evidence_status_check` | Check | `CHECK (status = ANY (ARRAY['TERCEK'::text, 'TIDAK_COCOK'::text, 'TIDAK_BISA_DICEK'::text, 'TIDAK_DICEK_BATAS'::text]))` |
| `AI_conversation_evidence_conversation_id_fkey` | Foreign key | `FOREIGN KEY (conversation_id) REFERENCES "AI_conversation"(conversation_id) ON DELETE CASCADE` |
| `AI_conversation_evidence_pkey` | Primary key | `PRIMARY KEY (evidence_id)` |

### Indexes

| Name | Definition |
|---|---|
| `AI_conversation_evidence_pkey` | `CREATE UNIQUE INDEX "AI_conversation_evidence_pkey" ON public."AI_conversation_evidence" USING btree (evidence_id)` |
| `ai_conversation_evidence_conversation_idx` | `CREATE INDEX ai_conversation_evidence_conversation_idx ON public."AI_conversation_evidence" USING btree (conversation_id, created_at)` |

## AI_conversation_execution

The code of one sandbox execution of a market-ai-orc conversation, kept for the life of the conversation (R-STORE).

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `execution_id` | `text` | No | — | No column description has been recorded. |
| `conversation_id` | `text` | No | — | No column description has been recorded. |
| `request_id` | `text` | No | — | No column description has been recorded. |
| `session_id` | `text` | Yes | — | No column description has been recorded. |
| `code` | `text` | No | — | No column description has been recorded. |
| `code_truncated` | `boolean` | No | `false` | No column description has been recorded. |
| `code_sha256` | `text` | No | — | No column description has been recorded. |
| `modules` | `jsonb` | Yes | — | No column description has been recorded. |
| `access` | `jsonb` | Yes | — | No column description has been recorded. |
| `status` | `text` | Yes | — | No column description has been recorded. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `ai_conversation_execution_code_check` | Check | `CHECK (length(code) <= 65536)` |
| `ai_conversation_execution_id_check` | Check | `CHECK (execution_id ~ '^exe_[0-9a-f]{24}$'::text)` |
| `ai_conversation_execution_json_check` | Check | `CHECK ((modules IS NULL OR jsonb_typeof(modules) = 'array'::text) AND (access IS NULL OR (jsonb_typeof(access) = ANY (ARRAY['array'::text, 'object'::text]))))` |
| `ai_conversation_execution_request_check` | Check | `CHECK (request_id ~ '^[A-Za-z0-9._:-]{1,200}$'::text)` |
| `ai_conversation_execution_session_check` | Check | `CHECK (session_id IS NULL OR session_id ~ '^sess_[0-9a-f]{24}$'::text)` |
| `ai_conversation_execution_sha_check` | Check | `CHECK (code_sha256 ~ '^[0-9a-f]{64}$'::text)` |
| `AI_conversation_execution_conversation_id_fkey` | Foreign key | `FOREIGN KEY (conversation_id) REFERENCES "AI_conversation"(conversation_id) ON DELETE CASCADE` |
| `AI_conversation_execution_pkey` | Primary key | `PRIMARY KEY (execution_id)` |

### Indexes

| Name | Definition |
|---|---|
| `AI_conversation_execution_pkey` | `CREATE UNIQUE INDEX "AI_conversation_execution_pkey" ON public."AI_conversation_execution" USING btree (execution_id)` |
| `ai_conversation_execution_conversation_idx` | `CREATE INDEX ai_conversation_execution_conversation_idx ON public."AI_conversation_execution" USING btree (conversation_id, created_at)` |

## AI_conversation_export

A file exported from a market-ai-orc conversation for download (phase D), at most 20 MB.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `export_id` | `text` | No | — | No column description has been recorded. |
| `conversation_id` | `text` | No | — | No column description has been recorded. |
| `request_id` | `text` | No | — | No column description has been recorded. |
| `source_ref` | `text` | No | — | No column description has been recorded. |
| `format` | `text` | No | — | No column description has been recorded. |
| `file_name` | `text` | No | — | No column description has been recorded. |
| `mime_type` | `text` | No | — | No column description has been recorded. |
| `size_bytes` | `bigint` | No | — | No column description has been recorded. |
| `sha256` | `text` | No | — | No column description has been recorded. |
| `content` | `bytea` | No | — | No column description has been recorded. |
| `includes` | `jsonb` | No | `'{}'::jsonb` | No column description has been recorded. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `ai_conversation_export_format_check` | Check | `CHECK (format = ANY (ARRAY['CSV'::text, 'XLSX'::text, 'PARQUET'::text]))` |
| `ai_conversation_export_id_check` | Check | `CHECK (export_id ~ '^exp_[0-9a-f]{24}$'::text)` |
| `ai_conversation_export_includes_check` | Check | `CHECK (jsonb_typeof(includes) = 'object'::text)` |
| `ai_conversation_export_name_check` | Check | `CHECK (file_name ~ '^[A-Za-z0-9._-]{1,120}$'::text)` |
| `ai_conversation_export_request_check` | Check | `CHECK (request_id ~ '^[A-Za-z0-9._:-]{1,200}$'::text)` |
| `ai_conversation_export_sha_check` | Check | `CHECK (sha256 ~ '^[0-9a-f]{64}$'::text)` |
| `ai_conversation_export_size_check` | Check | `CHECK (size_bytes = octet_length(content) AND size_bytes >= 1 AND size_bytes <= 20971520)` |
| `ai_conversation_export_source_check` | Check | `CHECK (length(source_ref) >= 1 AND length(source_ref) <= 200)` |
| `AI_conversation_export_conversation_id_fkey` | Foreign key | `FOREIGN KEY (conversation_id) REFERENCES "AI_conversation"(conversation_id) ON DELETE CASCADE` |
| `AI_conversation_export_pkey` | Primary key | `PRIMARY KEY (export_id)` |

### Indexes

| Name | Definition |
|---|---|
| `AI_conversation_export_pkey` | `CREATE UNIQUE INDEX "AI_conversation_export_pkey" ON public."AI_conversation_export" USING btree (export_id)` |
| `ai_conversation_export_conversation_idx` | `CREATE INDEX ai_conversation_export_conversation_idx ON public."AI_conversation_export" USING btree (conversation_id, created_at)` |

## AI_conversation_output

A released output of a market-ai-orc conversation, kept for the life of the conversation (R-STORE).

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `output_id` | `text` | No | — | No column description has been recorded. |
| `conversation_id` | `text` | No | — | No column description has been recorded. |
| `request_id` | `text` | No | — | No column description has been recorded. |
| `session_id` | `text` | Yes | — | No column description has been recorded. |
| `execution_id` | `text` | Yes | — | No column description has been recorded. |
| `name` | `text` | No | — | No column description has been recorded. |
| `output_type` | `text` | No | — | No column description has been recorded. |
| `format` | `text` | No | — | No column description has been recorded. |
| `label` | `text` | Yes | — | No column description has been recorded. |
| `definition` | `jsonb` | Yes | — | No column description has been recorded. |
| `units` | `jsonb` | Yes | — | No column description has been recorded. |
| `lineage` | `jsonb` | Yes | — | No column description has been recorded. |
| `data_as_of` | `date` | Yes | — | No column description has been recorded. |
| `row_count` | `bigint` | Yes | — | No column description has been recorded. |
| `columns` | `jsonb` | Yes | — | No column description has been recorded. |
| `byte_count` | `bigint` | No | — | No column description has been recorded. |
| `checksum_sha256` | `text` | No | — | No column description has been recorded. |
| `storage` | `text` | No | — | No column description has been recorded. |
| `content` | `bytea` | Yes | — | No column description has been recorded. |
| `object_key` | `text` | Yes | — | No column description has been recorded. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `ai_conversation_output_checksum_check` | Check | `CHECK (checksum_sha256 ~ '^[0-9a-f]{64}$'::text)` |
| `ai_conversation_output_execution_check` | Check | `CHECK (execution_id IS NULL OR execution_id ~ '^exe_[0-9a-f]{24}$'::text)` |
| `ai_conversation_output_format_check` | Check | `CHECK (format = ANY (ARRAY['PARQUET'::text, 'CSV'::text, 'PNG'::text, 'JSON'::text, 'TEXT'::text, 'BIN'::text]))` |
| `ai_conversation_output_id_check` | Check | `CHECK (output_id ~ '^out_[0-9a-f]{24}$'::text)` |
| `ai_conversation_output_json_check` | Check | `CHECK ((definition IS NULL OR jsonb_typeof(definition) = 'object'::text) AND (units IS NULL OR jsonb_typeof(units) = 'object'::text) AND (lineage IS NULL OR jsonb_typeof(lineage) = 'object'::text) AND (columns IS NULL OR jsonb_typeof(columns) = 'array'::text))` |
| `ai_conversation_output_name_check` | Check | `CHECK (length(name) >= 1 AND length(name) <= 80)` |
| `ai_conversation_output_request_check` | Check | `CHECK (request_id ~ '^[A-Za-z0-9._:-]{1,200}$'::text)` |
| `ai_conversation_output_session_check` | Check | `CHECK (session_id IS NULL OR session_id ~ '^sess_[0-9a-f]{24}$'::text)` |
| `ai_conversation_output_size_check` | Check | `CHECK (byte_count >= 0 AND (row_count IS NULL OR row_count >= 0))` |
| `ai_conversation_output_storage_check` | Check | `CHECK (storage = 'POSTGRES'::text AND content IS NOT NULL AND object_key IS NULL AND octet_length(content) = byte_count AND byte_count <= 20971520 OR storage = 'BUCKET'::text AND content IS NULL AND object_key IS NOT NULL AND object_key ~ '^outputs/conv_[0-9a-f]{32}/out_[0-9a-f]{24}\.[a-z]{3,7}$'::text)` |
| `AI_conversation_output_conversation_id_fkey` | Foreign key | `FOREIGN KEY (conversation_id) REFERENCES "AI_conversation"(conversation_id) ON DELETE CASCADE` |
| `AI_conversation_output_pkey` | Primary key | `PRIMARY KEY (output_id)` |

### Indexes

| Name | Definition |
|---|---|
| `AI_conversation_output_pkey` | `CREATE UNIQUE INDEX "AI_conversation_output_pkey" ON public."AI_conversation_output" USING btree (output_id)` |
| `ai_conversation_output_conversation_idx` | `CREATE INDEX ai_conversation_output_conversation_idx ON public."AI_conversation_output" USING btree (conversation_id, created_at)` |

## AI_conversation_run_memory

What each run of a market-ai-orc conversation leaves for the runs after it (EXEC-C): memo, full texts, citable sources, the model's note and its reasoning; deleted with the conversation.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `run_id` | `text` | No | — | No column description has been recorded. |
| `conversation_id` | `text` | No | — | No column description has been recorded. |
| `turn_request_id` | `text` | No | — | No column description has been recorded. |
| `seq` | `bigint` | No | — | No column description has been recorded. |
| `status` | `text` | No | — | No column description has been recorded. |
| `response_type` | `text` | Yes | — | No column description has been recorded. |
| `error_code` | `text` | Yes | — | No column description has been recorded. |
| `memo` | `text` | No | — | No column description has been recorded. |
| `content` | `jsonb` | No | — | No column description has been recorded. |
| `sources` | `jsonb` | No | `'{}'::jsonb` | No column description has been recorded. |
| `note` | `text` | Yes | — | No column description has been recorded. |
| `reasoning` | `text` | Yes | — | No column description has been recorded. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `ai_conversation_run_memory_json_check` | Check | `CHECK (jsonb_typeof(content) = 'object'::text AND jsonb_typeof(sources) = 'object'::text)` |
| `ai_conversation_run_memory_run_check` | Check | `CHECK (run_id ~ '^[A-Za-z0-9._:-]{1,200}$'::text)` |
| `ai_conversation_run_memory_size_check` | Check | `CHECK (length(memo) >= 1 AND length(memo) <= 200000 AND (note IS NULL OR length(note) <= 20000) AND (reasoning IS NULL OR length(reasoning) <= 800000))` |
| `ai_conversation_run_memory_status_check` | Check | `CHECK (status = ANY (ARRAY['COMPLETED'::text, 'NEEDS_CLARIFICATION'::text, 'AWAITING_CONFIRMATION'::text, 'LIMITED'::text, 'FAILED'::text]))` |
| `ai_conversation_run_memory_turn_check` | Check | `CHECK (turn_request_id ~ '^[A-Za-z0-9._:-]{1,200}$'::text)` |
| `AI_conversation_run_memory_conversation_id_fkey` | Foreign key | `FOREIGN KEY (conversation_id) REFERENCES "AI_conversation"(conversation_id) ON DELETE CASCADE` |
| `AI_conversation_run_memory_pkey` | Primary key | `PRIMARY KEY (run_id)` |

### Indexes

| Name | Definition |
|---|---|
| `AI_conversation_run_memory_pkey` | `CREATE UNIQUE INDEX "AI_conversation_run_memory_pkey" ON public."AI_conversation_run_memory" USING btree (run_id)` |
| `ai_conversation_run_memory_conversation_idx` | `CREATE UNIQUE INDEX ai_conversation_run_memory_conversation_idx ON public."AI_conversation_run_memory" USING btree (conversation_id, seq)` |

## AI_conversation_turn

One message of a market-ai-orc conversation and the response returned for it (history_mode SERVER).

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `request_id` | `text` | No | — | No column description has been recorded. |
| `conversation_id` | `text` | No | — | No column description has been recorded. |
| `turn_index` | `integer` | No | — | No column description has been recorded. |
| `request_fingerprint` | `text` | No | — | No column description has been recorded. |
| `user_message` | `text` | No | — | No column description has been recorded. |
| `status` | `text` | No | — | No column description has been recorded. |
| `lease_generation` | `bigint` | No | — | No column description has been recorded. |
| `run_status` | `text` | Yes | — | No column description has been recorded. |
| `response_type` | `text` | Yes | — | No column description has been recorded. |
| `assistant_text` | `text` | Yes | — | No column description has been recorded. |
| `response` | `jsonb` | Yes | — | No column description has been recorded. |
| `error_code` | `text` | Yes | — | No column description has been recorded. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | No column description has been recorded. |
| `completed_at` | `timestamp with time zone` | Yes | — | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `ai_conversation_turn_fingerprint_check` | Check | `CHECK (request_fingerprint ~ '^[0-9a-f]{64}$'::text)` |
| `ai_conversation_turn_finished_check` | Check | `CHECK ((status = 'RUNNING'::text) = (completed_at IS NULL))` |
| `ai_conversation_turn_index_check` | Check | `CHECK (turn_index >= 0 AND lease_generation >= 0)` |
| `ai_conversation_turn_request_id_check` | Check | `CHECK (request_id ~ '^[A-Za-z0-9._:-]{1,200}$'::text)` |
| `ai_conversation_turn_response_check` | Check | `CHECK (response IS NULL OR jsonb_typeof(response) = 'object'::text)` |
| `ai_conversation_turn_status_check` | Check | `CHECK (status = ANY (ARRAY['RUNNING'::text, 'COMPLETED'::text, 'FAILED'::text, 'INTERRUPTED'::text]))` |
| `ai_conversation_turn_text_check` | Check | `CHECK (length(user_message) >= 1 AND length(user_message) <= 20000 AND (assistant_text IS NULL OR length(assistant_text) <= 40000))` |
| `AI_conversation_turn_conversation_id_fkey` | Foreign key | `FOREIGN KEY (conversation_id) REFERENCES "AI_conversation"(conversation_id) ON DELETE CASCADE` |
| `AI_conversation_turn_pkey` | Primary key | `PRIMARY KEY (request_id)` |
| `ai_conversation_turn_position_key` | Unique | `UNIQUE (conversation_id, turn_index)` |

### Indexes

| Name | Definition |
|---|---|
| `AI_conversation_turn_pkey` | `CREATE UNIQUE INDEX "AI_conversation_turn_pkey" ON public."AI_conversation_turn" USING btree (request_id)` |
| `ai_conversation_turn_position_key` | `CREATE UNIQUE INDEX ai_conversation_turn_position_key ON public."AI_conversation_turn" USING btree (conversation_id, turn_index)` |

## AI_data_coverage

Automated raw-source coverage and explicitly inferred derived-table expectations; Feature 01-03 are never scanned by the coverage job.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `coverage_id` | `bigint` | No | — | No column description has been recorded. |
| `dataset_name` | `text` | No | — | No column description has been recorded. |
| `coverage_scope` | `text` | No | — | No column description has been recorded. |
| `entity_id` | `text` | Yes | — | No column description has been recorded. |
| `reference_dataset_name` | `text` | Yes | — | No column description has been recorded. |
| `coverage_mode` | `text` | No | — | No column description has been recorded. |
| `actual_min_date` | `date` | Yes | — | No column description has been recorded. |
| `actual_max_date` | `date` | Yes | — | No column description has been recorded. |
| `expected_min_date` | `date` | Yes | — | No column description has been recorded. |
| `expected_max_date` | `date` | Yes | — | No column description has been recorded. |
| `source_row_count` | `bigint` | Yes | — | No column description has been recorded. |
| `source_key_count` | `bigint` | Yes | — | No column description has been recorded. |
| `pipeline_status` | `text` | No | — | No column description has been recorded. |
| `verification_status` | `text` | No | — | No column description has been recorded. |
| `quality_status` | `text` | No | — | No column description has been recorded. |
| `check_error` | `text` | Yes | — | No column description has been recorded. |
| `last_checked_at` | `timestamp with time zone` | No | — | No column description has been recorded. |
| `last_full_checked_at` | `timestamp with time zone` | Yes | — | No column description has been recorded. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | No column description has been recorded. |
| `updated_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `AI_data_coverage_actual_dates_check` | Check | `CHECK (actual_min_date IS NULL OR actual_max_date IS NULL OR actual_max_date >= actual_min_date)` |
| `AI_data_coverage_counts_check` | Check | `CHECK ((source_row_count IS NULL OR source_row_count >= 0) AND (source_key_count IS NULL OR source_key_count >= 0))` |
| `AI_data_coverage_entity_check` | Check | `CHECK (coverage_scope = 'DATASET'::text AND entity_id IS NULL OR coverage_scope = 'ENTITY'::text AND entity_id IS NOT NULL AND btrim(entity_id) <> ''::text)` |
| `AI_data_coverage_expected_dates_check` | Check | `CHECK (expected_min_date IS NULL OR expected_max_date IS NULL OR expected_max_date >= expected_min_date)` |
| `AI_data_coverage_mode_check` | Check | `CHECK (coverage_mode = ANY (ARRAY['ACTUAL_SOURCE'::text, 'EXPECTED_DERIVED'::text, 'SNAPSHOT'::text]))` |
| `AI_data_coverage_quality_check` | Check | `CHECK (quality_status = ANY (ARRAY['HEALTHY'::text, 'WARNING'::text, 'FAILED'::text, 'ERROR'::text]))` |
| `AI_data_coverage_scope_check` | Check | `CHECK (coverage_scope = ANY (ARRAY['DATASET'::text, 'ENTITY'::text]))` |
| `AI_data_coverage_timestamp_check` | Check | `CHECK (updated_at >= created_at)` |
| `AI_data_coverage_verification_check` | Check | `CHECK (verification_status = ANY (ARRAY['VERIFIED'::text, 'PIPELINE_CONFIRMED'::text, 'UNVERIFIED'::text]))` |
| `AI_data_coverage_dataset_fkey` | Foreign key | `FOREIGN KEY (dataset_name) REFERENCES "AI_table_catalog"(table_name) ON DELETE CASCADE` |
| `AI_data_coverage_reference_fkey` | Foreign key | `FOREIGN KEY (reference_dataset_name) REFERENCES "AI_table_catalog"(table_name)` |
| `AI_data_coverage_pkey` | Primary key | `PRIMARY KEY (coverage_id)` |

### Indexes

| Name | Definition |
|---|---|
| `AI_data_coverage_identity_idx` | `CREATE UNIQUE INDEX "AI_data_coverage_identity_idx" ON public."AI_data_coverage" USING btree (dataset_name, coverage_scope, COALESCE(entity_id, ''::text))` |
| `AI_data_coverage_pkey` | `CREATE UNIQUE INDEX "AI_data_coverage_pkey" ON public."AI_data_coverage" USING btree (coverage_id)` |
| `AI_data_coverage_reference_idx` | `CREATE INDEX "AI_data_coverage_reference_idx" ON public."AI_data_coverage" USING btree (reference_dataset_name, entity_id) WHERE (reference_dataset_name IS NOT NULL)` |
| `AI_data_coverage_status_idx` | `CREATE INDEX "AI_data_coverage_status_idx" ON public."AI_data_coverage" USING btree (quality_status, verification_status, dataset_name)` |

## AI_formula_reference

Reference calculation formulas for the orchestrator; documented definitions, not verified or executable implementations.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `calculation_id` | `text` | No | — | No column description has been recorded. |
| `calculation_name` | `text` | No | — | No column description has been recorded. |
| `description` | `text` | No | — | No column description has been recorded. |
| `required_inputs` | `text` | No | — | Semicolon-delimited logical input roles, not actual PostgreSQL column names. |
| `formula_method` | `text` | No | — | Renamed from the source workbook column "formula / method" to a valid identifier. |
| `parameters` | `text` | No | — | No column description has been recorded. |
| `output` | `text` | No | — | No column description has been recorded. |
| `implementation` | `text` | No | — | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `ai_formula_reference_nonempty_id` | Check | `CHECK (calculation_id ~ '^[A-Za-z][A-Za-z0-9_]{0,62}$'::text)` |
| `AI_formula_reference_pkey` | Primary key | `PRIMARY KEY (calculation_id)` |

### Indexes

| Name | Definition |
|---|---|
| `AI_formula_reference_pkey` | `CREATE UNIQUE INDEX "AI_formula_reference_pkey" ON public."AI_formula_reference" USING btree (calculation_id)` |

## AI_method_guide

Model-facing menu and manual of the analysis paths and session helpers; generated from code, hash-bound (guides_sha256). Enforcement stays in code.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `name` | `text` | No | — | No column description has been recorded. |
| `guides_version` | `integer` | No | — | No column description has been recorded. |
| `kind` | `text` | No | — | No column description has been recorded. |
| `g` | `text` | Yes | — | No column description has been recorded. |
| `guide` | `jsonb` | No | — | No column description has been recorded. |
| `guide_sha256` | `text` | No | — | No column description has been recorded. |
| `guides_sha256` | `text` | No | — | No column description has been recorded. |
| `is_active` | `boolean` | No | `true` | No column description has been recorded. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | No column description has been recorded. |
| `updated_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `ai_method_guide_g` | Check | `CHECK (g IS NULL OR (g = ANY (ARRAY['G1'::text, 'G2'::text, 'G3'::text, 'G4'::text])))` |
| `ai_method_guide_json` | Check | `CHECK (jsonb_typeof(guide) = 'object'::text AND (guide ->> 'name'::text) = name)` |
| `ai_method_guide_kind` | Check | `CHECK (kind = ANY (ARRAY['PATH'::text, 'HELPER'::text]))` |
| `ai_method_guide_name` | Check | `CHECK (name ~ '^[a-z][a-z0-9_]{0,62}$'::text)` |
| `ai_method_guide_path_has_g` | Check | `CHECK ((kind = 'PATH'::text) = (g IS NOT NULL))` |
| `ai_method_guide_sha` | Check | `CHECK (guide_sha256 ~ '^[0-9a-f]{64}$'::text AND guides_sha256 ~ '^[0-9a-f]{64}$'::text)` |
| `AI_method_guide_pkey` | Primary key | `PRIMARY KEY (name, guides_version)` |

### Indexes

| Name | Definition |
|---|---|
| `AI_method_guide_pkey` | `CREATE UNIQUE INDEX "AI_method_guide_pkey" ON public."AI_method_guide" USING btree (name, guides_version)` |

## AI_metric_catalog

Official metrics for query_metric (one Governor summary per period); units and additivity are read from AI_column_catalog, never repeated here.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `metric_id` | `text` | No | — | No column description has been recorded. |
| `metric_version` | `integer` | No | `1` | No column description has been recorded. |
| `label` | `text` | No | — | No column description has been recorded. |
| `description` | `text` | No | — | No column description has been recorded. |
| `source_table` | `text` | No | — | No column description has been recorded. |
| `measure_column` | `text` | No | — | No column description has been recorded. |
| `time_function` | `text` | No | — | No column description has been recorded. |
| `entity_column` | `text` | No | — | No column description has been recorded. |
| `default_dimensions` | `ARRAY` | No | `ARRAY[]::text[]` | No column description has been recorded. |
| `allowed_dimensions` | `ARRAY` | No | `ARRAY[]::text[]` | No column description has been recorded. |
| `default_scope` | `jsonb` | No | `'{"type": "ALL"}'::jsonb` | No column description has been recorded. |
| `formula` | `text` | No | — | No column description has been recorded. |
| `interpretation` | `text` | No | — | No column description has been recorded. |
| `recommended_use` | `text` | No | — | No column description has been recorded. |
| `misuse_warning` | `text` | No | — | No column description has been recorded. |
| `review_status` | `text` | No | `'INFERRED'::text` | No column description has been recorded. |
| `source_decision` | `text` | No | — | No column description has been recorded. |
| `is_active` | `boolean` | No | `true` | No column description has been recorded. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `ai_metric_catalog_dimensions` | Check | `CHECK (default_dimensions <@ allowed_dimensions AND (entity_column = ANY (allowed_dimensions)))` |
| `ai_metric_catalog_function` | Check | `CHECK (time_function = ANY (ARRAY['SUM'::text, 'MIN'::text, 'MAX'::text, 'FIRST'::text, 'LAST'::text, 'COUNT'::text]))` |
| `ai_metric_catalog_id` | Check | `CHECK (metric_id ~ '^[a-z][a-z0-9_]{0,63}$'::text AND metric_version >= 1)` |
| `ai_metric_catalog_review` | Check | `CHECK (review_status = ANY (ARRAY['INFERRED'::text, 'REVIEWED'::text, 'VERIFIED'::text]))` |
| `ai_metric_catalog_scope` | Check | `CHECK (jsonb_typeof(default_scope) = 'object'::text AND default_scope ? 'type'::text)` |
| `AI_metric_catalog_pkey` | Primary key | `PRIMARY KEY (metric_id, metric_version)` |

### Indexes

| Name | Definition |
|---|---|
| `AI_metric_catalog_pkey` | `CREATE UNIQUE INDEX "AI_metric_catalog_pkey" ON public."AI_metric_catalog" USING btree (metric_id, metric_version)` |
| `ai_metric_catalog_one_active` | `CREATE UNIQUE INDEX ai_metric_catalog_one_active ON public."AI_metric_catalog" USING btree (metric_id) WHERE is_active` |

## AI_research_catalog

Reference methods for the orchestrator; REFERENCE_ONLY does not imply installed sandbox code or validation.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `method_id` | `text` | No | — | No column description has been recorded. |
| `method_name` | `text` | No | — | No column description has been recorded. |
| `category` | `text` | No | — | No column description has been recorded. |
| `purpose` | `text` | No | — | No column description has been recorded. |
| `example_question` | `text` | No | — | No column description has been recorded. |
| `analysis_kind` | `text` | No | — | No column description has been recorded. |
| `input_grain` | `text` | No | — | No column description has been recorded. |
| `required_inputs_json` | `jsonb` | No | — | Logical input roles, not PostgreSQL table or column identifiers. |
| `optional_inputs_json` | `jsonb` | No | — | No column description has been recorded. |
| `future_outcome_required` | `boolean` | No | — | No column description has been recorded. |
| `supports_numeric_directly` | `boolean` | No | — | No column description has been recorded. |
| `preprocessing` | `text` | No | — | No column description has been recorded. |
| `parameter_keys_json` | `jsonb` | No | — | No column description has been recorded. |
| `expected_outputs_json` | `jsonb` | No | — | No column description has been recorded. |
| `validation_requirements_json` | `jsonb` | No | — | No column description has been recorded. |
| `main_risks` | `text` | No | — | No column description has been recorded. |
| `compute_strategy` | `text` | No | — | No column description has been recorded. |
| `tool_or_library_examples` | `text` | No | — | No column description has been recorded. |
| `implementation_status` | `text` | No | — | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `ai_research_json_arrays` | Check | `CHECK (jsonb_typeof(required_inputs_json) = 'array'::text AND jsonb_typeof(optional_inputs_json) = 'array'::text AND jsonb_typeof(parameter_keys_json) = 'array'::text AND jsonb_typeof(expected_outputs_json) = 'array'::text AND jsonb_typeof(validation_requirements_json) = 'array'::text)` |
| `ai_research_nonempty_id` | Check | `CHECK (method_id ~ '^[A-Za-z][A-Za-z0-9_]{0,62}$'::text)` |
| `ai_research_nonempty_status` | Check | `CHECK (length(TRIM(BOTH FROM implementation_status)) > 0)` |
| `AI_research_catalog_pkey` | Primary key | `PRIMARY KEY (method_id)` |

### Indexes

| Name | Definition |
|---|---|
| `AI_research_catalog_pkey` | `CREATE UNIQUE INDEX "AI_research_catalog_pkey" ON public."AI_research_catalog" USING btree (method_id)` |

## AI_research_library

Model-facing description of the Multi-Angle Research methods the sandbox engines compute; generated from code, hash-bound (library_sha256). Enforcement stays in code.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `method_id` | `text` | No | — | No column description has been recorded. |
| `engine_version` | `integer` | No | — | No column description has been recorded. |
| `library_version` | `integer` | No | — | No column description has been recorded. |
| `method_family` | `text` | No | — | No column description has been recorded. |
| `question_shape` | `text` | No | — | No column description has been recorded. |
| `input_roles` | `jsonb` | No | — | No column description has been recorded. |
| `required_parameters` | `jsonb` | No | — | No column description has been recorded. |
| `optional_parameters` | `jsonb` | No | — | No column description has been recorded. |
| `data_requirements` | `jsonb` | No | — | No column description has been recorded. |
| `common_requirements` | `jsonb` | No | — | No column description has been recorded. |
| `sample_unit` | `text` | No | — | No column description has been recorded. |
| `secondary_checks` | `jsonb` | No | — | No column description has been recorded. |
| `decision_rules_ref` | `text` | No | — | No column description has been recorded. |
| `interpretation` | `text` | No | — | No column description has been recorded. |
| `misuse_warning` | `text` | No | — | No column description has been recorded. |
| `example_question` | `text` | No | — | No column description has been recorded. |
| `library_sha256` | `text` | No | — | No column description has been recorded. |
| `is_active` | `boolean` | No | `true` | No column description has been recorded. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | No column description has been recorded. |
| `updated_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `ai_research_library_family` | Check | `CHECK (method_family = ANY (ARRAY['CONDITIONAL_OUTCOME'::text, 'PERSISTENCE'::text, 'GROUP_COMPARISON'::text, 'QUANTILE_RANKING'::text, 'TEMPORAL_DEPENDENCY'::text]))` |
| `ai_research_library_json` | Check | `CHECK (jsonb_typeof(input_roles) = 'array'::text AND jsonb_typeof(required_parameters) = 'array'::text AND jsonb_typeof(optional_parameters) = 'array'::text AND jsonb_typeof(data_requirements) = 'object'::text AND jsonb_typeof(common_requirements) = 'array'::text AND jsonb_typeof(secondary_checks) = 'array'::text)` |
| `ai_research_library_method_id` | Check | `CHECK (method_id ~ '^[a-z][a-z0-9_]{0,62}$'::text)` |
| `ai_research_library_sample_unit` | Check | `CHECK (sample_unit = ANY (ARRAY['DATES'::text, 'ENTITIES'::text, 'DATES_AUTOCORRELATION_ADJUSTED'::text]))` |
| `ai_research_library_sha` | Check | `CHECK (library_sha256 ~ '^[0-9a-f]{64}$'::text)` |
| `AI_research_library_pkey` | Primary key | `PRIMARY KEY (method_id, engine_version)` |

### Indexes

| Name | Definition |
|---|---|
| `AI_research_library_pkey` | `CREATE UNIQUE INDEX "AI_research_library_pkey" ON public."AI_research_library" USING btree (method_id, engine_version)` |

## AI_research_run_audit

One audit row per market-ai-orc run: question, final answer, evidence label, and experiments with their governor, validation and evidence decisions. Written once (INSERT only).

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `request_id` | `text` | No | — | No column description has been recorded. |
| `recorded_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | No column description has been recorded. |
| `status` | `text` | No | — | No column description has been recorded. |
| `response_type` | `text` | Yes | — | No column description has been recorded. |
| `evidence_label` | `text` | Yes | — | No column description has been recorded. |
| `validation_gate` | `text` | No | — | No column description has been recorded. |
| `error_code` | `text` | Yes | — | No column description has been recorded. |
| `question_sha256` | `text` | No | — | No column description has been recorded. |
| `question` | `text` | No | — | No column description has been recorded. |
| `answer_sha256` | `text` | Yes | — | No column description has been recorded. |
| `answer` | `text` | Yes | — | No column description has been recorded. |
| `limitations` | `jsonb` | No | `'[]'::jsonb` | No column description has been recorded. |
| `number_provenance` | `jsonb` | Yes | — | No column description has been recorded. |
| `experiments` | `jsonb` | No | `'[]'::jsonb` | No column description has been recorded. |
| `datasets` | `jsonb` | No | `'[]'::jsonb` | No column description has been recorded. |
| `budget` | `jsonb` | No | `'{}'::jsonb` | No column description has been recorded. |
| `model` | `text` | No | — | No column description has been recorded. |
| `tool_call_count` | `integer` | No | — | No column description has been recorded. |
| `total_tokens` | `integer` | No | — | No column description has been recorded. |
| `duration_ms` | `integer` | No | — | No column description has been recorded. |
| `sandbox_summary_status` | `text` | No | — | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `ai_research_run_audit_counts_check` | Check | `CHECK (tool_call_count >= 0 AND total_tokens >= 0 AND duration_ms >= 0)` |
| `ai_research_run_audit_gate_check` | Check | `CHECK (validation_gate = ANY (ARRAY['NOT_APPLICABLE'::text, 'PASSED'::text, 'ANNOTATED'::text, 'FORCED_LIMITATION'::text]))` |
| `ai_research_run_audit_hash_check` | Check | `CHECK (question_sha256 ~ '^[0-9a-f]{64}$'::text AND (answer_sha256 IS NULL OR answer_sha256 ~ '^[0-9a-f]{64}$'::text))` |
| `ai_research_run_audit_json_check` | Check | `CHECK (jsonb_typeof(limitations) = 'array'::text AND jsonb_typeof(experiments) = 'array'::text AND jsonb_typeof(datasets) = 'array'::text AND jsonb_typeof(budget) = 'object'::text)` |
| `ai_research_run_audit_request_id_check` | Check | `CHECK (request_id ~ '^[A-Za-z0-9._:-]{1,200}$'::text)` |
| `ai_research_run_audit_response_check` | Check | `CHECK (response_type IS NULL OR (response_type = ANY (ARRAY['ANSWER'::text, 'CLARIFICATION'::text, 'RESEARCH_PLAN_CONFIRMATION'::text, 'LIMITATION'::text])))` |
| `ai_research_run_audit_sandbox_check` | Check | `CHECK (sandbox_summary_status = ANY (ARRAY['REPORTED'::text, 'AWAITING_REPORT'::text, 'ACTIVE'::text, 'UNAVAILABLE'::text, 'NOT_USED'::text]))` |
| `ai_research_run_audit_status_check` | Check | `CHECK (status = ANY (ARRAY['COMPLETED'::text, 'NEEDS_CLARIFICATION'::text, 'AWAITING_CONFIRMATION'::text, 'LIMITED'::text, 'FAILED'::text]))` |
| `ai_research_run_audit_text_check` | Check | `CHECK (length(question) <= 16000 AND (answer IS NULL OR length(answer) <= 20000))` |
| `AI_research_run_audit_pkey` | Primary key | `PRIMARY KEY (request_id)` |

### Indexes

| Name | Definition |
|---|---|
| `AI_research_run_audit_pkey` | `CREATE UNIQUE INDEX "AI_research_run_audit_pkey" ON public."AI_research_run_audit" USING btree (request_id)` |
| `ai_research_run_audit_recorded_idx` | `CREATE INDEX ai_research_run_audit_recorded_idx ON public."AI_research_run_audit" USING btree (recorded_at)` |

## AI_table_catalog

AI-facing master list for the seven approved Indonesian equity data tables.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `table_name` | `text` | No | — | No column description has been recorded. |
| `description` | `text` | No | — | No column description has been recorded. |
| `category` | `text` | No | — | No column description has been recorded. |
| `grain` | `text` | No | — | No column description has been recorded. |
| `primary_key_columns` | `ARRAY` | No | — | No column description has been recorded. |
| `time_column` | `text` | Yes | — | No column description has been recorded. |
| `entity_column` | `text` | No | — | No column description has been recorded. |
| `owner` | `text` | No | `'Saniti'::text` | No column description has been recorded. |
| `is_active` | `boolean` | No | `true` | No column description has been recorded. |
| `ai_access_level` | `text` | No | `'BOUNDED_READ'::text` | No column description has been recorded. |
| `freshness_sla` | `interval` | Yes | — | No column description has been recorded. |
| `coverage_enabled` | `boolean` | No | `true` | No column description has been recorded. |
| `documentation_status` | `text` | No | — | No column description has been recorded. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | No column description has been recorded. |
| `updated_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | No column description has been recorded. |
| `data_domain` | `text` | No | — | Catalog-managed subject area of the table (MARKET, MACRO, RATES, FUNDAMENTAL, ...); syntax-checked, not an enum. |
| `entity_type` | `text` | No | — | Catalog-managed type of the entity that entity_column identifies (STOCK, BROKER, SERIES, ...). |
| `asset_type` | `text` | Yes | — | Asset type of the entities when they are assets (IDX_EQUITY, ...); NULL for non-asset entities. |
| `supported_frequencies` | `ARRAY` | No | — | Observation frequencies the table supports; {STATIC} exactly when the table has no time_column. |
| `time_semantics` | `text` | Yes | — | What a value of time_column means (trading date, observation date) or that the table is current state. |
| `subject_metadata_status` | `text` | No | `'INFERRED'::text` | INFERRED until a person reviews the subject values; REVIEWED or VERIFIED only after review. |
| `row_presence` | `text` | Yes | — | What a missing row means: DENSE (missing data), ACTIVITY_ONLY (no activity on that date), NOT_APPLICABLE (no time column). |
| `row_presence_status` | `text` | Yes | — | INFERRED until a person reviews row_presence; REVIEWED or VERIFIED only after review. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `AI_table_catalog_access_check` | Check | `CHECK (ai_access_level = ANY (ARRAY['BOUNDED_READ'::text, 'DENIED'::text]))` |
| `AI_table_catalog_asset_type_check` | Check | `CHECK (asset_type IS NULL OR asset_type ~ '^[A-Z][A-Z0-9_]{1,39}$'::text)` |
| `AI_table_catalog_category_check` | Check | `CHECK (category = ANY (ARRAY['REFERENCE'::text, 'TRANSACTIONAL'::text, 'FEATURE'::text]))` |
| `AI_table_catalog_data_domain_check` | Check | `CHECK (data_domain ~ '^[A-Z][A-Z0-9_]{1,39}$'::text)` |
| `AI_table_catalog_documentation_check` | Check | `CHECK (documentation_status = ANY (ARRAY['VERIFIED'::text, 'PARTIAL'::text, 'NEEDS_REVIEW'::text]))` |
| `AI_table_catalog_entity_type_check` | Check | `CHECK (entity_type ~ '^[A-Z][A-Z0-9_]{1,39}$'::text)` |
| `AI_table_catalog_frequencies_check` | Check | `CHECK (cardinality(supported_frequencies) >= 1 AND cardinality(supported_frequencies) <= 8 AND supported_frequencies <@ ARRAY['STATIC'::text, '1MIN'::text, '5MIN'::text, '15MIN'::text, '1H'::text, '1D'::text, '1W'::text, '1M'::text, '1Q'::text, '1Y'::text] AND (time_column IS NULL) = (supported_frequencies = ARRAY['STATIC'::text]))` |
| `AI_table_catalog_name_check` | Check | `CHECK (btrim(table_name) <> ''::text)` |
| `AI_table_catalog_row_presence_check` | Check | `CHECK (row_presence IS NULL OR (row_presence = ANY (ARRAY['DENSE'::text, 'ACTIVITY_ONLY'::text, 'NOT_APPLICABLE'::text])))` |
| `AI_table_catalog_row_presence_status_check` | Check | `CHECK (row_presence_status IS NULL OR (row_presence_status = ANY (ARRAY['INFERRED'::text, 'REVIEWED'::text, 'VERIFIED'::text])))` |
| `AI_table_catalog_row_presence_time_check` | Check | `CHECK (row_presence IS NULL OR (row_presence = 'NOT_APPLICABLE'::text) = (time_column IS NULL))` |
| `AI_table_catalog_subject_status_check` | Check | `CHECK (subject_metadata_status = ANY (ARRAY['INFERRED'::text, 'REVIEWED'::text, 'VERIFIED'::text]))` |
| `AI_table_catalog_timestamp_check` | Check | `CHECK (updated_at >= created_at)` |
| `AI_table_catalog_pkey` | Primary key | `PRIMARY KEY (table_name)` |

### Indexes

| Name | Definition |
|---|---|
| `AI_table_catalog_pkey` | `CREATE UNIQUE INDEX "AI_table_catalog_pkey" ON public."AI_table_catalog" USING btree (table_name)` |

## Analysis_Evidence

Compact reproducible evidence supporting material AI analysis claims.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `evidence_id` | `uuid` | No | `gen_random_uuid()` | No column description has been recorded. |
| `request_id` | `uuid` | No | — | No column description has been recorded. |
| `step_id` | `bigint` | Yes | — | No column description has been recorded. |
| `evidence_type` | `text` | No | — | No column description has been recorded. |
| `claim` | `text` | No | — | No column description has been recorded. |
| `compact_payload` | `jsonb` | No | — | No column description has been recorded. |
| `query_hash` | `text` | Yes | — | No column description has been recorded. |
| `source_tables` | `ARRAY` | No | `'{}'::text[]` | No column description has been recorded. |
| `source_row_count` | `bigint` | Yes | — | No column description has been recorded. |
| `analysis_ready_date` | `date` | Yes | — | No column description has been recorded. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `Analysis_Evidence_row_count_check` | Check | `CHECK (source_row_count IS NULL OR source_row_count >= 0)` |
| `Analysis_Evidence_type_check` | Check | `CHECK (evidence_type = ANY (ARRAY['OBSERVATION'::text, 'QUALITY'::text, 'ANOMALY'::text, 'STATISTIC'::text, 'HISTORICAL_TEST'::text, 'WARNING'::text]))` |
| `Analysis_Evidence_request_id_fkey` | Foreign key | `FOREIGN KEY (request_id) REFERENCES "Analysis_Request"(request_id) ON DELETE CASCADE` |
| `Analysis_Evidence_step_id_fkey` | Foreign key | `FOREIGN KEY (step_id) REFERENCES "Analysis_Step_Log"(step_id) ON DELETE SET NULL` |
| `Analysis_Evidence_pkey` | Primary key | `PRIMARY KEY (evidence_id)` |

### Indexes

| Name | Definition |
|---|---|
| `Analysis_Evidence_pkey` | `CREATE UNIQUE INDEX "Analysis_Evidence_pkey" ON public."Analysis_Evidence" USING btree (evidence_id)` |
| `Analysis_Evidence_request_idx` | `CREATE INDEX "Analysis_Evidence_request_idx" ON public."Analysis_Evidence" USING btree (request_id, created_at)` |

## Analysis_Model_Call

One durable audit row per provider model call. Provider-returned reasoning is retained temporarily; concise decision summary and usage remain for long-term audit.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `model_call_id` | `bigint` | No | — | Generated model-call audit identifier. |
| `request_id` | `uuid` | No | — | Analysis request that caused this provider call. |
| `iteration_number` | `integer` | No | — | One-based provider-call number within the analysis request. |
| `provider` | `text` | No | — | Allowlisted provider selected by runtime configuration. |
| `model` | `text` | No | — | Exact configured provider model identifier. |
| `reasoning_effort` | `text` | No | — | Configured reasoning effort sent to the provider. |
| `stage` | `text` | No | — | Progressive analytical stage active for this call. |
| `exposed_tool_families` | `ARRAY` | No | `'{}'::text[]` | Tool families exposed to this specific model call. |
| `provider_response_id` | `text` | Yes | — | Provider response identifier when returned. |
| `decision_summary` | `text` | Yes | — | Concise provider reasoning summary when supplied; otherwise a deterministic summary of the requested tool or final-answer action. |
| `decision_summary_source` | `text` | No | — | PROVIDER_REASONING or DERIVED_ACTION; never an invented chain-of-thought reconstruction. |
| `reasoning_format` | `text` | No | `'NONE'::text` | NONE, TEXT, SUMMARY, ENCRYPTED, MIXED, or PURGED representation actually stored. |
| `reasoning_details` | `jsonb` | No | `'[]'::jsonb` | Bounded provider-returned reasoning blocks only; prompts and tool results are not copied here and expired details are replaced by an empty array. |
| `input_tokens` | `integer` | No | `0` | Provider-reported input tokens for this one call. |
| `output_tokens` | `integer` | No | `0` | Provider-reported output tokens for this one call. |
| `reasoning_tokens` | `integer` | No | `0` | Provider-reported reasoning-token subset when available; zero means unavailable or zero, not an estimate. |
| `active_context_tokens` | `integer` | No | `0` | Backend estimate of active instructions, input items, and tool schemas for this call. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | UTC database timestamp when the audit row was written. |
| `reasoning_expires_at` | `timestamp with time zone` | No | — | UTC deadline after which raw provider-returned reasoning is purged. |
| `reasoning_purged_at` | `timestamp with time zone` | Yes | — | UTC timestamp when reasoning_details was cleared; NULL while retained or absent. |
| `attempt_number` | `integer` | No | — | One-based Analysis_Request processing attempt; iteration numbering restarts within each lease attempt. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `Analysis_Model_Call_attempt_check` | Check | `CHECK (attempt_number > 0)` |
| `Analysis_Model_Call_decision_source_check` | Check | `CHECK (decision_summary_source = ANY (ARRAY['PROVIDER_REASONING'::text, 'DERIVED_ACTION'::text]))` |
| `Analysis_Model_Call_iteration_check` | Check | `CHECK (iteration_number > 0)` |
| `Analysis_Model_Call_provider_check` | Check | `CHECK (provider = ANY (ARRAY['openai'::text, 'openrouter'::text]))` |
| `Analysis_Model_Call_reasoning_array_check` | Check | `CHECK (jsonb_typeof(reasoning_details) = 'array'::text)` |
| `Analysis_Model_Call_reasoning_format_check` | Check | `CHECK (reasoning_format = ANY (ARRAY['NONE'::text, 'TEXT'::text, 'SUMMARY'::text, 'ENCRYPTED'::text, 'MIXED'::text, 'PURGED'::text]))` |
| `Analysis_Model_Call_retention_check` | Check | `CHECK (reasoning_expires_at >= created_at AND (reasoning_purged_at IS NULL OR reasoning_purged_at >= created_at))` |
| `Analysis_Model_Call_stage_check` | Check | `CHECK (stage = ANY (ARRAY['DISCOVERY'::text, 'SCREENING'::text, 'HISTORICAL_VALIDATION'::text, 'ADVANCED'::text, 'FINAL'::text]))` |
| `Analysis_Model_Call_token_counts_check` | Check | `CHECK (input_tokens >= 0 AND output_tokens >= 0 AND reasoning_tokens >= 0 AND active_context_tokens >= 0)` |
| `Analysis_Model_Call_request_id_fkey` | Foreign key | `FOREIGN KEY (request_id) REFERENCES "Analysis_Request"(request_id) ON DELETE CASCADE` |
| `Analysis_Model_Call_pkey` | Primary key | `PRIMARY KEY (model_call_id)` |
| `Analysis_Model_Call_request_attempt_iteration_key` | Unique | `UNIQUE (request_id, attempt_number, iteration_number)` |

### Indexes

| Name | Definition |
|---|---|
| `Analysis_Model_Call_pkey` | `CREATE UNIQUE INDEX "Analysis_Model_Call_pkey" ON public."Analysis_Model_Call" USING btree (model_call_id)` |
| `Analysis_Model_Call_request_attempt_iteration_key` | `CREATE UNIQUE INDEX "Analysis_Model_Call_request_attempt_iteration_key" ON public."Analysis_Model_Call" USING btree (request_id, attempt_number, iteration_number)` |
| `Analysis_Model_Call_retention_idx` | `CREATE INDEX "Analysis_Model_Call_retention_idx" ON public."Analysis_Model_Call" USING btree (reasoning_expires_at) WHERE (reasoning_format <> ALL (ARRAY['NONE'::text, 'PURGED'::text]))` |

## Analysis_Request

Durable AI analysis lifecycle, compact result, version snapshot, methodology metadata, and token usage.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `request_id` | `uuid` | No | `gen_random_uuid()` | No column description has been recorded. |
| `user_reference` | `text` | Yes | — | No column description has been recorded. |
| `question` | `text` | No | — | No column description has been recorded. |
| `status` | `text` | No | `'PENDING'::text` | No column description has been recorded. |
| `current_stage` | `text` | No | `'DISCOVERY'::text` | No column description has been recorded. |
| `exposed_tool_families` | `ARRAY` | No | `ARRAY['META'::text, 'DISCOVERY'::text, 'QUALITY'::text]` | No column description has been recorded. |
| `model` | `text` | Yes | — | No column description has been recorded. |
| `openai_response_id` | `text` | Yes | — | No column description has been recorded. |
| `analysis_ready_date` | `date` | Yes | — | No column description has been recorded. |
| `features_used` | `ARRAY` | No | `'{}'::text[]` | No column description has been recorded. |
| `input_tokens` | `integer` | No | `0` | Cumulative OpenAI input tokens across every model call in this request. |
| `output_tokens` | `integer` | No | `0` | Cumulative OpenAI output tokens across every model call in this request. |
| `total_tokens` | `integer` | No | `0` | Cumulative input plus output tokens across every model call in this request. |
| `tool_result_tokens` | `integer` | No | `0` | No column description has been recorded. |
| `history_tokens` | `integer` | No | `0` | No column description has been recorded. |
| `feature_metadata_tokens` | `integer` | No | `0` | No column description has been recorded. |
| `tool_call_count` | `integer` | No | `0` | No column description has been recorded. |
| `tool_iteration_count` | `integer` | No | `0` | No column description has been recorded. |
| `context_compaction_count` | `integer` | No | `0` | No column description has been recorded. |
| `answer` | `jsonb` | Yes | — | No column description has been recorded. |
| `recommended_next_analysis` | `jsonb` | No | `'[]'::jsonb` | No column description has been recorded. |
| `error_message` | `text` | Yes | — | No column description has been recorded. |
| `attempt_count` | `integer` | No | `0` | No column description has been recorded. |
| `lease_owner` | `text` | Yes | — | No column description has been recorded. |
| `lease_expires_at` | `timestamp with time zone` | Yes | — | No column description has been recorded. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | No column description has been recorded. |
| `started_at` | `timestamp with time zone` | Yes | — | No column description has been recorded. |
| `completed_at` | `timestamp with time zone` | Yes | — | No column description has been recorded. |
| `updated_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | No column description has been recorded. |
| `version_snapshot` | `jsonb` | No | `'{}'::jsonb` | Immutable completed-request snapshot of provider/model, orchestrator/prompt, Feature, tool, analytics methodology, query hash, and evidence versions. |
| `methodology_metadata` | `jsonb` | No | `'{}'::jsonb` | Point-in-time universe, survivorship, historical metadata, signal availability, entry time, and look-ahead validation metadata. |
| `current_context_tokens` | `integer` | No | `0` | Estimated active tokens sent on the latest model call; distinct from cumulative input usage. |
| `peak_context_tokens` | `integer` | No | `0` | Maximum active context tokens observed in any single model call for this request. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `Analysis_Request_context_tokens_check` | Check | `CHECK (current_context_tokens >= 0 AND peak_context_tokens >= 0 AND peak_context_tokens >= current_context_tokens)` |
| `Analysis_Request_snapshot_object_check` | Check | `CHECK (jsonb_typeof(version_snapshot) = 'object'::text AND jsonb_typeof(methodology_metadata) = 'object'::text)` |
| `Analysis_Request_stage_check` | Check | `CHECK (current_stage = ANY (ARRAY['DISCOVERY'::text, 'SCREENING'::text, 'HISTORICAL_VALIDATION'::text, 'ADVANCED'::text, 'FINAL'::text]))` |
| `Analysis_Request_status_check` | Check | `CHECK (status = ANY (ARRAY['PENDING'::text, 'PROCESSING'::text, 'SUCCESS'::text, 'FAILED'::text, 'CANCELLED'::text]))` |
| `Analysis_Request_success_audit_check` | Check | `CHECK (status <> 'SUCCESS'::text OR version_snapshot <> '{}'::jsonb AND methodology_metadata <> '{}'::jsonb)` |
| `Analysis_Request_token_counts_check` | Check | `CHECK (input_tokens >= 0 AND output_tokens >= 0 AND total_tokens >= 0 AND tool_result_tokens >= 0 AND history_tokens >= 0 AND feature_metadata_tokens >= 0 AND tool_call_count >= 0 AND tool_iteration_count >= 0 AND context_compaction_count >= 0 AND attempt_count >= 0)` |
| `Analysis_Request_pkey` | Primary key | `PRIMARY KEY (request_id)` |

### Indexes

| Name | Definition |
|---|---|
| `Analysis_Request_pending_idx` | `CREATE INDEX "Analysis_Request_pending_idx" ON public."Analysis_Request" USING btree (status, created_at) WHERE (status = ANY (ARRAY['PENDING'::text, 'PROCESSING'::text]))` |
| `Analysis_Request_pkey` | `CREATE UNIQUE INDEX "Analysis_Request_pkey" ON public."Analysis_Request" USING btree (request_id)` |

## Analysis_Step_Log

Audit record for each AI query, tool, compaction, or analytical step.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `step_id` | `bigint` | No | — | No column description has been recorded. |
| `request_id` | `uuid` | No | — | No column description has been recorded. |
| `step_number` | `integer` | No | — | No column description has been recorded. |
| `stage` | `text` | No | — | No column description has been recorded. |
| `tool_name` | `text` | Yes | — | No column description has been recorded. |
| `sanitized_arguments` | `jsonb` | No | `'{}'::jsonb` | No column description has been recorded. |
| `estimated_rows` | `bigint` | Yes | — | No column description has been recorded. |
| `processed_rows` | `bigint` | Yes | — | No column description has been recorded. |
| `returned_rows` | `bigint` | Yes | — | No column description has been recorded. |
| `returned_bytes` | `bigint` | Yes | — | No column description has been recorded. |
| `llm_result_tokens` | `integer` | Yes | — | No column description has been recorded. |
| `duration_ms` | `integer` | Yes | — | No column description has been recorded. |
| `query_hash` | `text` | Yes | — | No column description has been recorded. |
| `evidence_references` | `jsonb` | No | `'[]'::jsonb` | No column description has been recorded. |
| `result_summary` | `jsonb` | Yes | — | No column description has been recorded. |
| `status` | `text` | No | — | No column description has been recorded. |
| `error_message` | `text` | Yes | — | No column description has been recorded. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `Analysis_Step_Log_counts_check` | Check | `CHECK ((estimated_rows IS NULL OR estimated_rows >= 0) AND (processed_rows IS NULL OR processed_rows >= 0) AND (returned_rows IS NULL OR returned_rows >= 0) AND (returned_bytes IS NULL OR returned_bytes >= 0) AND (llm_result_tokens IS NULL OR llm_result_tokens >= 0) AND (duration_ms IS NULL OR duration_ms >= 0))` |
| `Analysis_Step_Log_status_check` | Check | `CHECK (status = ANY (ARRAY['STARTED'::text, 'SUCCESS'::text, 'WARNING'::text, 'FAILED'::text, 'COMPACTED'::text]))` |
| `Analysis_Step_Log_request_id_fkey` | Foreign key | `FOREIGN KEY (request_id) REFERENCES "Analysis_Request"(request_id) ON DELETE CASCADE` |
| `Analysis_Step_Log_pkey` | Primary key | `PRIMARY KEY (step_id)` |
| `Analysis_Step_Log_request_step_key` | Unique | `UNIQUE (request_id, step_number)` |

### Indexes

| Name | Definition |
|---|---|
| `Analysis_Step_Log_pkey` | `CREATE UNIQUE INDEX "Analysis_Step_Log_pkey" ON public."Analysis_Step_Log" USING btree (step_id)` |
| `Analysis_Step_Log_request_idx` | `CREATE INDEX "Analysis_Step_Log_request_idx" ON public."Analysis_Step_Log" USING btree (request_id, step_number)` |
| `Analysis_Step_Log_request_step_key` | `CREATE UNIQUE INDEX "Analysis_Step_Log_request_step_key" ON public."Analysis_Step_Log" USING btree (request_id, step_number)` |

## Analytics_Dataset_Snapshot

Metadata for immutable private bounded raw/Feature analytical input objects. Only the backend reads PostgreSQL; worker input objects expire quickly.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `snapshot_id` | `uuid` | No | `gen_random_uuid()` | No column description has been recorded. |
| `request_id` | `uuid` | No | — | No column description has been recorded. |
| `object_key` | `text` | No | — | No column description has been recorded. |
| `content_sha256` | `text` | No | — | SHA-256 of the exact compressed object; the worker verifies it before execution. |
| `format` | `text` | No | — | No column description has been recorded. |
| `row_count` | `integer` | No | — | No column description has been recorded. |
| `column_count` | `integer` | No | — | No column description has been recorded. |
| `byte_count` | `integer` | No | — | No column description has been recorded. |
| `compressed_byte_count` | `integer` | No | — | No column description has been recorded. |
| `schema_json` | `jsonb` | No | — | No column description has been recorded. |
| `source_spec_json` | `jsonb` | No | — | Catalog-validated structured raw/Feature reads created by the backend; never model-written PostgreSQL SQL. |
| `source_tables` | `ARRAY` | No | — | No column description has been recorded. |
| `query_hashes` | `ARRAY` | No | — | No column description has been recorded. |
| `analysis_ready_date` | `date` | Yes | — | No column description has been recorded. |
| `status` | `text` | No | `'AVAILABLE'::text` | No column description has been recorded. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | No column description has been recorded. |
| `expires_at` | `timestamp with time zone` | No | — | No column description has been recorded. |
| `deleted_at` | `timestamp with time zone` | Yes | — | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `Analytics_Dataset_Snapshot_counts_check` | Check | `CHECK (row_count > 0 AND column_count > 0 AND byte_count > 0 AND compressed_byte_count > 0)` |
| `Analytics_Dataset_Snapshot_expiry_check` | Check | `CHECK (expires_at > created_at)` |
| `Analytics_Dataset_Snapshot_format_check` | Check | `CHECK (format = 'JSON_GZIP'::text)` |
| `Analytics_Dataset_Snapshot_hash_check` | Check | `CHECK (content_sha256 ~ '^[0-9a-f]{64}$'::text)` |
| `Analytics_Dataset_Snapshot_json_check` | Check | `CHECK (jsonb_typeof(schema_json) = 'object'::text AND jsonb_typeof(source_spec_json) = 'array'::text)` |
| `Analytics_Dataset_Snapshot_status_check` | Check | `CHECK (status = ANY (ARRAY['AVAILABLE'::text, 'EXPIRED'::text, 'DELETED'::text]))` |
| `Analytics_Dataset_Snapshot_request_id_fkey` | Foreign key | `FOREIGN KEY (request_id) REFERENCES "Analysis_Request"(request_id) ON DELETE CASCADE` |
| `Analytics_Dataset_Snapshot_pkey` | Primary key | `PRIMARY KEY (snapshot_id)` |
| `Analytics_Dataset_Snapshot_content_sha256_key` | Unique | `UNIQUE (content_sha256)` |
| `Analytics_Dataset_Snapshot_object_key_key` | Unique | `UNIQUE (object_key)` |

### Indexes

| Name | Definition |
|---|---|
| `Analytics_Dataset_Snapshot_content_sha256_key` | `CREATE UNIQUE INDEX "Analytics_Dataset_Snapshot_content_sha256_key" ON public."Analytics_Dataset_Snapshot" USING btree (content_sha256)` |
| `Analytics_Dataset_Snapshot_expiry_idx` | `CREATE INDEX "Analytics_Dataset_Snapshot_expiry_idx" ON public."Analytics_Dataset_Snapshot" USING btree (expires_at, snapshot_id) WHERE (status = 'AVAILABLE'::text)` |
| `Analytics_Dataset_Snapshot_object_key_key` | `CREATE UNIQUE INDEX "Analytics_Dataset_Snapshot_object_key_key" ON public."Analytics_Dataset_Snapshot" USING btree (object_key)` |
| `Analytics_Dataset_Snapshot_pkey` | `CREATE UNIQUE INDEX "Analytics_Dataset_Snapshot_pkey" ON public."Analytics_Dataset_Snapshot" USING btree (snapshot_id)` |
| `Analytics_Dataset_Snapshot_request_idx` | `CREATE INDEX "Analytics_Dataset_Snapshot_request_idx" ON public."Analytics_Dataset_Snapshot" USING btree (request_id, created_at DESC)` |

## Analytics_Job

Durable isolated-worker queue. execution_class prevents a query-sandbox credential from claiming statistical jobs and vice versa.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `job_id` | `uuid` | No | `gen_random_uuid()` | No column description has been recorded. |
| `request_id` | `uuid` | No | — | No column description has been recorded. |
| `snapshot_id` | `uuid` | No | — | No column description has been recorded. |
| `job_label` | `text` | No | — | No column description has been recorded. |
| `purpose` | `text` | No | — | No column description has been recorded. |
| `method` | `text` | No | — | No column description has been recorded. |
| `analysis_spec_json` | `jsonb` | No | — | Worker computation specification. v1 contains one allowlisted SELECT/WITH DuckDB statement over snapshot dataset names only. |
| `status` | `text` | No | `'PENDING'::text` | No column description has been recorded. |
| `attempt_count` | `smallint` | No | `0` | No column description has been recorded. |
| `max_attempts` | `smallint` | No | `3` | No column description has been recorded. |
| `worker_id` | `text` | Yes | — | No column description has been recorded. |
| `lease_token` | `uuid` | Yes | — | No column description has been recorded. |
| `lease_expires_at` | `timestamp with time zone` | Yes | — | No column description has been recorded. |
| `max_runtime_seconds` | `integer` | No | — | No column description has been recorded. |
| `max_memory_mb` | `integer` | No | — | No column description has been recorded. |
| `max_result_rows` | `integer` | No | — | No column description has been recorded. |
| `max_result_bytes` | `integer` | No | — | No column description has been recorded. |
| `result_json` | `jsonb` | Yes | — | Compact bounded analytical output; the full snapshot is never copied here or sent to the LLM. |
| `evidence_id` | `uuid` | Yes | — | No column description has been recorded. |
| `error_class` | `text` | Yes | — | No column description has been recorded. |
| `error_message` | `text` | Yes | — | No column description has been recorded. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | No column description has been recorded. |
| `started_at` | `timestamp with time zone` | Yes | — | No column description has been recorded. |
| `completed_at` | `timestamp with time zone` | Yes | — | No column description has been recorded. |
| `result_expires_at` | `timestamp with time zone` | No | — | No column description has been recorded. |
| `updated_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | No column description has been recorded. |
| `execution_class` | `text` | No | `'STATISTICAL_VALIDATION'::text` | Physical worker boundary. QUERY_SANDBOX and STATISTICAL_VALIDATION use different credentials and claim endpoints. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `Analytics_Job_attempts_check` | Check | `CHECK (attempt_count >= 0 AND max_attempts >= 1 AND max_attempts <= 10)` |
| `Analytics_Job_execution_class_check` | Check | `CHECK (execution_class = ANY (ARRAY['QUERY_SANDBOX'::text, 'STATISTICAL_VALIDATION'::text]))` |
| `Analytics_Job_lease_check` | Check | `CHECK (status = 'PROCESSING'::text AND worker_id IS NOT NULL AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL OR status <> 'PROCESSING'::text)` |
| `Analytics_Job_limits_check` | Check | `CHECK (max_runtime_seconds > 0 AND max_memory_mb > 0 AND max_result_rows > 0 AND max_result_bytes > 0)` |
| `Analytics_Job_method_check` | Check | `CHECK (execution_class = 'QUERY_SANDBOX'::text AND method = 'SAFE_DUCKDB_SQL'::text OR execution_class = 'STATISTICAL_VALIDATION'::text AND (method = ANY (ARRAY['DESCRIPTIVE_STATISTICS_SQL'::text, 'EVENT_STUDY_SQL'::text, 'BACKTEST_SQL'::text, 'SIGNIFICANCE_TEST_SQL'::text, 'REGRESSION_SQL'::text, 'CLUSTERING_SQL'::text, 'HMM_SQL'::text, 'PREDICTIVE_VALIDATION_SQL'::text, 'SAFE_DUCKDB_SQL'::text])))` |
| `Analytics_Job_result_check` | Check | `CHECK (result_json IS NULL OR jsonb_typeof(result_json) = 'object'::text)` |
| `Analytics_Job_spec_check` | Check | `CHECK (jsonb_typeof(analysis_spec_json) = 'object'::text)` |
| `Analytics_Job_status_check` | Check | `CHECK (status = ANY (ARRAY['PENDING'::text, 'PROCESSING'::text, 'SUCCESS'::text, 'FAILED'::text, 'CANCELLED'::text]))` |
| `Analytics_Job_terminal_check` | Check | `CHECK ((status = ANY (ARRAY['SUCCESS'::text, 'FAILED'::text, 'CANCELLED'::text])) AND completed_at IS NOT NULL OR (status = ANY (ARRAY['PENDING'::text, 'PROCESSING'::text])))` |
| `Analytics_Job_evidence_id_fkey` | Foreign key | `FOREIGN KEY (evidence_id) REFERENCES "Analysis_Evidence"(evidence_id) ON DELETE SET NULL` |
| `Analytics_Job_request_id_fkey` | Foreign key | `FOREIGN KEY (request_id) REFERENCES "Analysis_Request"(request_id) ON DELETE CASCADE` |
| `Analytics_Job_snapshot_id_fkey` | Foreign key | `FOREIGN KEY (snapshot_id) REFERENCES "Analytics_Dataset_Snapshot"(snapshot_id) ON DELETE RESTRICT` |
| `Analytics_Job_pkey` | Primary key | `PRIMARY KEY (job_id)` |
| `Analytics_Job_request_label_key` | Unique | `UNIQUE (request_id, job_label)` |

### Indexes

| Name | Definition |
|---|---|
| `Analytics_Job_claim_idx` | `CREATE INDEX "Analytics_Job_claim_idx" ON public."Analytics_Job" USING btree (execution_class, status, created_at, lease_expires_at) WHERE (status = ANY (ARRAY['PENDING'::text, 'PROCESSING'::text]))` |
| `Analytics_Job_pkey` | `CREATE UNIQUE INDEX "Analytics_Job_pkey" ON public."Analytics_Job" USING btree (job_id)` |
| `Analytics_Job_request_idx` | `CREATE INDEX "Analytics_Job_request_idx" ON public."Analytics_Job" USING btree (request_id, created_at DESC)` |
| `Analytics_Job_request_label_key` | `CREATE UNIQUE INDEX "Analytics_Job_request_label_key" ON public."Analytics_Job" USING btree (request_id, job_label)` |

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

## Feature04_Calculation_Log

Immutable Feature04 worker attempt history with per-group success/failure and retry lineage.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `id` | `bigint` | No | — | No column description has been recorded. |
| `ticker` | `text` | No | — | No column description has been recorded. |
| `timeframe` | `text` | No | — | No column description has been recorded. |
| `source_generation` | `bigint` | No | — | No column description has been recorded. |
| `work_revision` | `bigint` | No | — | No column description has been recorded. |
| `retry_request_id` | `uuid` | Yes | — | No column description has been recorded. |
| `requested_columns` | `ARRAY` | Yes | — | No column description has been recorded. |
| `successful_columns` | `ARRAY` | No | `'{}'::text[]` | No column description has been recorded. |
| `failed_columns` | `ARRAY` | No | `'{}'::text[]` | No column description has been recorded. |
| `group_outcomes` | `jsonb` | No | `'{}'::jsonb` | No column description has been recorded. |
| `result` | `text` | No | — | No column description has been recorded. |
| `source_start` | `date` | Yes | — | No column description has been recorded. |
| `source_end` | `date` | Yes | — | No column description has been recorded. |
| `source_rows` | `integer` | Yes | — | No column description has been recorded. |
| `source_sha256` | `text` | Yes | — | No column description has been recorded. |
| `changed_rows` | `integer` | Yes | — | No column description has been recorded. |
| `calculation_version` | `text` | No | — | No column description has been recorded. |
| `started_at` | `timestamp with time zone` | No | — | No column description has been recorded. |
| `finished_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | No column description has been recorded. |
| `error_code` | `text` | Yes | — | No column description has been recorded. |
| `detail` | `text` | Yes | — | No column description has been recorded. |
| `asset_type` | `text` | No | — | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `Feature04_Calculation_Log_asset_type_check` | Check | `CHECK (asset_type = ANY (ARRAY['equity'::text, 'bonds'::text]))` |
| `Feature04_Calculation_Log_changed_rows_check` | Check | `CHECK (changed_rows IS NULL OR changed_rows >= 0)` |
| `Feature04_Calculation_Log_check` | Check | `CHECK (source_generation >= 0 AND work_revision > 0)` |
| `Feature04_Calculation_Log_check1` | Check | `CHECK (finished_at >= started_at)` |
| `Feature04_Calculation_Log_result_check` | Check | `CHECK (result = ANY (ARRAY['SUCCESS'::text, 'PARTIAL'::text, 'FAILED'::text, 'SUPERSEDED'::text]))` |
| `Feature04_Calculation_Log_source_rows_check` | Check | `CHECK (source_rows IS NULL OR source_rows >= 0)` |
| `Feature04_Calculation_Log_timeframe_check` | Check | `CHECK (timeframe = 'Daily'::text)` |
| `Feature04_Calculation_Log_retry_fkey` | Foreign key | `FOREIGN KEY (retry_request_id) REFERENCES "Feature04_Retry_Request"(request_id)` |
| `Feature04_Calculation_Log_pkey` | Primary key | `PRIMARY KEY (id)` |

### Indexes

| Name | Definition |
|---|---|
| `Feature04_Calculation_Log_pkey` | `CREATE UNIQUE INDEX "Feature04_Calculation_Log_pkey" ON public."Feature04_Calculation_Log" USING btree (id)` |
| `Feature04_Calculation_Log_ticker_time_idx` | `CREATE INDEX "Feature04_Calculation_Log_ticker_time_idx" ON public."Feature04_Calculation_Log" USING btree (asset_type, ticker, started_at DESC)` |

## Feature04_Calculation_Queue

Durable coalesced Feature04 work per ticker/timeframe; generation tracks source change and work_revision tracks retry scope.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `ticker` | `text` | No | — | No column description has been recorded. |
| `timeframe` | `text` | No | `'Daily'::text` | No column description has been recorded. |
| `dirty_from_date` | `date` | No | — | No column description has been recorded. |
| `requested_generation` | `bigint` | No | `1` | No column description has been recorded. |
| `completed_generation` | `bigint` | No | `0` | No column description has been recorded. |
| `work_revision` | `bigint` | No | `1` | No column description has been recorded. |
| `requested_columns` | `ARRAY` | Yes | — | No column description has been recorded. |
| `origin_execution_id` | `text` | Yes | — | No column description has been recorded. |
| `status` | `text` | No | `'PENDING'::text` | No column description has been recorded. |
| `attempt_count` | `bigint` | No | `0` | No column description has been recorded. |
| `source_attempt_count` | `integer` | No | `0` | No column description has been recorded. |
| `next_attempt_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | No column description has been recorded. |
| `claimed_at` | `timestamp with time zone` | Yes | — | No column description has been recorded. |
| `claim_token` | `uuid` | Yes | — | No column description has been recorded. |
| `claim_expires_at` | `timestamp with time zone` | Yes | — | No column description has been recorded. |
| `last_error_code` | `text` | Yes | — | No column description has been recorded. |
| `last_error` | `text` | Yes | — | No column description has been recorded. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | No column description has been recorded. |
| `updated_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | No column description has been recorded. |
| `completed_at` | `timestamp with time zone` | Yes | — | No column description has been recorded. |
| `asset_type` | `text` | No | — | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `Feature04_Calculation_Queue_asset_type_check` | Check | `CHECK (asset_type = ANY (ARRAY['equity'::text, 'bonds'::text]))` |
| `Feature04_Calculation_Queue_check` | Check | `CHECK (requested_generation >= completed_generation AND completed_generation >= 0)` |
| `Feature04_Calculation_Queue_check1` | Check | `CHECK (work_revision > 0 AND attempt_count >= 0 AND source_attempt_count >= 0)` |
| `Feature04_Calculation_Queue_check2` | Check | `CHECK ((status = 'PROCESSING'::text) = (claimed_at IS NOT NULL AND claim_token IS NOT NULL AND claim_expires_at IS NOT NULL))` |
| `Feature04_Calculation_Queue_requested_columns_check` | Check | `CHECK (requested_columns IS NULL OR cardinality(requested_columns) > 0)` |
| `Feature04_Calculation_Queue_status_check` | Check | `CHECK (status = ANY (ARRAY['PENDING'::text, 'PROCESSING'::text, 'DONE'::text, 'FAILED'::text]))` |
| `Feature04_Calculation_Queue_ticker_check` | Check | `CHECK (ticker = upper(btrim(ticker)) AND ticker <> ''::text)` |
| `Feature04_Calculation_Queue_timeframe_check` | Check | `CHECK (timeframe = 'Daily'::text)` |
| `Feature04_Calculation_Queue_pkey` | Primary key | `PRIMARY KEY (asset_type, ticker, timeframe)` |

### Indexes

| Name | Definition |
|---|---|
| `Feature04_Calculation_Queue_lease_idx` | `CREATE INDEX "Feature04_Calculation_Queue_lease_idx" ON public."Feature04_Calculation_Queue" USING btree (claim_expires_at) WHERE (status = 'PROCESSING'::text)` |
| `Feature04_Calculation_Queue_pkey` | `CREATE UNIQUE INDEX "Feature04_Calculation_Queue_pkey" ON public."Feature04_Calculation_Queue" USING btree (asset_type, ticker, timeframe)` |
| `Feature04_Calculation_Queue_ready_idx` | `CREATE INDEX "Feature04_Calculation_Queue_ready_idx" ON public."Feature04_Calculation_Queue" USING btree (next_attempt_at, updated_at) WHERE (status = ANY (ARRAY['PENDING'::text, 'FAILED'::text]))` |

## Feature04_Column_Status

Current readiness/failure state for each Feature04 output column per ticker; expected NULL is a successful availability outcome.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `ticker` | `text` | No | — | No column description has been recorded. |
| `timeframe` | `text` | No | `'Daily'::text` | No column description has been recorded. |
| `feature_column` | `text` | No | — | No column description has been recorded. |
| `requested_generation` | `bigint` | No | `0` | No column description has been recorded. |
| `completed_generation` | `bigint` | No | `0` | No column description has been recorded. |
| `calculation_version` | `text` | No | — | No column description has been recorded. |
| `status` | `text` | No | — | No column description has been recorded. |
| `dirty_from_date` | `date` | Yes | — | No column description has been recorded. |
| `validated_through` | `date` | Yes | — | No column description has been recorded. |
| `latest_value_available` | `boolean` | Yes | — | No column description has been recorded. |
| `null_reason` | `text` | Yes | — | No column description has been recorded. |
| `last_attempt_id` | `bigint` | Yes | — | No column description has been recorded. |
| `last_error_code` | `text` | Yes | — | No column description has been recorded. |
| `last_error` | `text` | Yes | — | No column description has been recorded. |
| `last_calculated_at` | `timestamp with time zone` | Yes | — | No column description has been recorded. |
| `updated_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | No column description has been recorded. |
| `asset_type` | `text` | No | — | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `Feature04_Column_Status_asset_type_check` | Check | `CHECK (asset_type = ANY (ARRAY['equity'::text, 'bonds'::text]))` |
| `Feature04_Column_Status_check` | Check | `CHECK (btrim(feature_column) <> ''::text AND btrim(calculation_version) <> ''::text)` |
| `Feature04_Column_Status_check1` | Check | `CHECK (requested_generation >= completed_generation AND completed_generation >= 0)` |
| `Feature04_Column_Status_status_check` | Check | `CHECK (status = ANY (ARRAY['PENDING'::text, 'PROCESSING'::text, 'SUCCESS'::text, 'FAILED'::text, 'BLOCKED'::text]))` |
| `Feature04_Column_Status_ticker_check` | Check | `CHECK (ticker = upper(btrim(ticker)) AND ticker <> ''::text)` |
| `Feature04_Column_Status_timeframe_check` | Check | `CHECK (timeframe = 'Daily'::text)` |
| `Feature04_Column_Status_attempt_fkey` | Foreign key | `FOREIGN KEY (last_attempt_id) REFERENCES "Feature04_Calculation_Log"(id)` |
| `Feature04_Column_Status_pkey` | Primary key | `PRIMARY KEY (asset_type, ticker, timeframe, feature_column)` |

### Indexes

| Name | Definition |
|---|---|
| `Feature04_Column_Status_failure_idx` | `CREATE INDEX "Feature04_Column_Status_failure_idx" ON public."Feature04_Column_Status" USING btree (status, updated_at DESC, asset_type, ticker, feature_column) WHERE (status = ANY (ARRAY['FAILED'::text, 'BLOCKED'::text]))` |
| `Feature04_Column_Status_pkey` | `CREATE UNIQUE INDEX "Feature04_Column_Status_pkey" ON public."Feature04_Column_Status" USING btree (asset_type, ticker, timeframe, feature_column)` |

## Feature04_Notification_Outbox

Durable Feature04 completion delivery request; calculation success never depends on Telegram availability.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `event_id` | `uuid` | No | — | No column description has been recorded. |
| `execution_id` | `text` | No | — | No column description has been recorded. |
| `notification_type` | `text` | No | `'COMPLETED'::text` | No column description has been recorded. |
| `status` | `text` | No | `'PENDING'::text` | No column description has been recorded. |
| `attempt_count` | `integer` | No | `0` | No column description has been recorded. |
| `next_attempt_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | No column description has been recorded. |
| `claimed_at` | `timestamp with time zone` | Yes | — | No column description has been recorded. |
| `claim_token` | `uuid` | Yes | — | No column description has been recorded. |
| `claim_expires_at` | `timestamp with time zone` | Yes | — | No column description has been recorded. |
| `sent_at` | `timestamp with time zone` | Yes | — | No column description has been recorded. |
| `last_error` | `text` | Yes | — | No column description has been recorded. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | No column description has been recorded. |
| `updated_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `Feature04_Notification_Outbox_attempt_count_check` | Check | `CHECK (attempt_count >= 0)` |
| `Feature04_Notification_Outbox_check` | Check | `CHECK ((status = 'SENDING'::text) = (claimed_at IS NOT NULL AND claim_token IS NOT NULL AND claim_expires_at IS NOT NULL))` |
| `Feature04_Notification_Outbox_status_check` | Check | `CHECK (status = ANY (ARRAY['PENDING'::text, 'SENDING'::text, 'SENT'::text, 'FAILED'::text]))` |
| `Feature04_Notification_Outbox_execution_id_fkey` | Foreign key | `FOREIGN KEY (execution_id) REFERENCES "Monitoring_Feature04"(execution_id) ON DELETE CASCADE` |
| `Feature04_Notification_Outbox_pkey` | Primary key | `PRIMARY KEY (event_id)` |
| `Feature04_Notification_Outbox_execution_id_notification_typ_key` | Unique | `UNIQUE (execution_id, notification_type)` |

### Indexes

| Name | Definition |
|---|---|
| `Feature04_Notification_Outbox_execution_id_notification_typ_key` | `CREATE UNIQUE INDEX "Feature04_Notification_Outbox_execution_id_notification_typ_key" ON public."Feature04_Notification_Outbox" USING btree (execution_id, notification_type)` |
| `Feature04_Notification_Outbox_pkey` | `CREATE UNIQUE INDEX "Feature04_Notification_Outbox_pkey" ON public."Feature04_Notification_Outbox" USING btree (event_id)` |
| `Feature04_Notification_Outbox_ready_idx` | `CREATE INDEX "Feature04_Notification_Outbox_ready_idx" ON public."Feature04_Notification_Outbox" USING btree (next_attempt_at, created_at) WHERE (status = ANY (ARRAY['PENDING'::text, 'FAILED'::text]))` |

## Feature04_Retry_Request

Audited owner Telegram retry request for one failed ticker or failed indicator bundle.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `request_id` | `uuid` | No | — | No column description has been recorded. |
| `telegram_update_id` | `bigint` | Yes | — | No column description has been recorded. |
| `chat_id` | `bigint` | Yes | — | No column description has been recorded. |
| `request_scope` | `text` | No | — | No column description has been recorded. |
| `source_execution_id` | `text` | Yes | — | No column description has been recorded. |
| `ticker` | `text` | Yes | — | No column description has been recorded. |
| `requested_columns` | `ARRAY` | Yes | — | No column description has been recorded. |
| `source_generation` | `bigint` | No | — | No column description has been recorded. |
| `work_revision` | `bigint` | No | — | No column description has been recorded. |
| `status` | `text` | No | `'PENDING'::text` | No column description has been recorded. |
| `child_execution_id` | `text` | No | — | No column description has been recorded. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | No column description has been recorded. |
| `started_at` | `timestamp with time zone` | Yes | — | No column description has been recorded. |
| `finished_at` | `timestamp with time zone` | Yes | — | No column description has been recorded. |
| `last_error` | `text` | Yes | — | No column description has been recorded. |
| `asset_type` | `text` | Yes | — | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `Feature04_Retry_Request_asset_type_check` | Check | `CHECK (asset_type IS NULL OR (asset_type = ANY (ARRAY['equity'::text, 'bonds'::text])))` |
| `Feature04_Retry_Request_check` | Check | `CHECK (request_scope = 'TICKER'::text AND requested_columns IS NULL OR request_scope = 'COLUMN'::text AND requested_columns IS NOT NULL AND cardinality(requested_columns) > 0)` |
| `Feature04_Retry_Request_check1` | Check | `CHECK (source_generation >= 0 AND work_revision > 0)` |
| `Feature04_Retry_Request_request_scope_check` | Check | `CHECK (request_scope = ANY (ARRAY['TICKER'::text, 'COLUMN'::text]))` |
| `Feature04_Retry_Request_status_check` | Check | `CHECK (status = ANY (ARRAY['PENDING'::text, 'PROCESSING'::text, 'SUCCESS'::text, 'PARTIAL'::text, 'FAILED'::text, 'SUPERSEDED'::text, 'CANCELLED'::text]))` |
| `Feature04_Retry_Request_pkey` | Primary key | `PRIMARY KEY (request_id)` |
| `Feature04_Retry_Request_child_execution_id_key` | Unique | `UNIQUE (child_execution_id)` |
| `Feature04_Retry_Request_telegram_update_id_key` | Unique | `UNIQUE (telegram_update_id)` |

### Indexes

| Name | Definition |
|---|---|
| `Feature04_Retry_Request_child_execution_id_key` | `CREATE UNIQUE INDEX "Feature04_Retry_Request_child_execution_id_key" ON public."Feature04_Retry_Request" USING btree (child_execution_id)` |
| `Feature04_Retry_Request_pkey` | `CREATE UNIQUE INDEX "Feature04_Retry_Request_pkey" ON public."Feature04_Retry_Request" USING btree (request_id)` |
| `Feature04_Retry_Request_telegram_update_id_key` | `CREATE UNIQUE INDEX "Feature04_Retry_Request_telegram_update_id_key" ON public."Feature04_Retry_Request" USING btree (telegram_update_id)` |

## Feature_01_Stock_Daily

Daily ticker-level price, return, volatility, volume, and price-position features derived from IDX prices and the current stock universe.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `date` | `date` | No | — | Trading observation date from Price_Stock_Indonesia_IDX. |
| `ticker` | `text` | No | — | IDX ticker; feature grain is one row per ticker and trading date. |
| `close` | `numeric` | No | — | Source closing price. |
| `volume` | `numeric` | No | — | Source trading volume. |
| `sector` | `text` | No | — | Current Sector value inherited exactly from IDX_Stock_Universe. |
| `industry` | `text` | No | — | Current Industry value inherited exactly from IDX_Stock_Universe. |
| `close_1d_ago` | `numeric` | Yes | — | Closing price one prior trading observation ago. |
| `close_5d_ago` | `numeric` | Yes | — | Closing price five prior trading observations ago. |
| `close_20d_ago` | `numeric` | Yes | — | Closing price twenty prior trading observations ago. |
| `close_60d_ago` | `numeric` | Yes | — | Closing price sixty prior trading observations ago. |
| `return_1d_pct` | `double precision` | Yes | — | Percent close return versus one prior trading observation. |
| `return_5d_pct` | `double precision` | Yes | — | Percent close return versus five prior trading observations. |
| `return_20d_pct` | `double precision` | Yes | — | Percent close return versus twenty prior trading observations. |
| `return_60d_pct` | `double precision` | Yes | — | Percent close return versus sixty prior trading observations. |
| `abs_return_1d_pct` | `double precision` | Yes | — | Absolute one-observation percent return. |
| `volatility_5d_ann_pct` | `double precision` | Yes | — | Annualized sample standard deviation of five daily decimal returns, in percent. |
| `volatility_20d_ann_pct` | `double precision` | Yes | — | Annualized sample standard deviation of twenty daily decimal returns, in percent. |
| `volatility_60d_ann_pct` | `double precision` | Yes | — | Annualized sample standard deviation of sixty daily decimal returns, in percent. |
| `volatility_5d_change_pct` | `double precision` | Yes | — | Percent change versus the five-day volatility from five observations ago. |
| `volatility_20d_change_pct` | `double precision` | Yes | — | Percent change versus the twenty-day volatility from twenty observations ago. |
| `volatility_60d_change_pct` | `double precision` | Yes | — | Percent change versus the sixty-day volatility from sixty observations ago. |
| `volume_avg_20d` | `double precision` | Yes | — | Average volume over a complete twenty-observation window. |
| `volume_std_20d` | `double precision` | Yes | — | Sample standard deviation of volume over a complete twenty-observation window. |
| `volume_ratio_20d` | `double precision` | Yes | — | Current volume divided by the complete twenty-observation average. |
| `volume_zscore_20d` | `double precision` | Yes | — | Current volume deviation from the twenty-observation average in standard deviations. |
| `high_20d` | `numeric` | Yes | — | Maximum close over a complete twenty-observation window. |
| `high_60d` | `numeric` | Yes | — | Maximum close over a complete sixty-observation window. |
| `drawdown_20d_pct` | `double precision` | Yes | — | Percent close position below the complete twenty-observation maximum close. |
| `drawdown_60d_pct` | `double precision` | Yes | — | Percent close position below the complete sixty-observation maximum close. |

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

## Feature_02_Broker_Rolling

Canonical Feature 02 v2: one source ticker, broker, investor type, board and transaction date per row. Investor type is source investor identity, not broker domicile.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `date` | `date` | No | — | Ticker transaction date from IDX_Broker_Summary; the rolling calendar uses all observed dates for the ticker across investor types and boards. |
| `ticker` | `text` | No | — | Exact IDX_Broker_Summary Symbol; no Stock Universe filter is applied. |
| `broker` | `text` | No | — | Exact source Broker code identifying the executing broker. |
| `investor_type` | `text` | No | — | Exact source Investor Type: Domestic or Foreign. This describes the investor represented by the source row, not the broker domicile. |
| `market_board` | `text` | No | — | Exact source Market Board: Regular, Nego or Tunai; boards never mix in rolling calculations. |
| `broker_classification` | `text` | Yes | — | Current broker usage classification from IDX_Broker_Profile; metadata only and not point-in-time history. |
| `buy_value_1d` | `numeric` | No | — | Source Buy Value for this date, ticker, broker, investor type and board. |
| `sell_value_1d` | `numeric` | No | — | Source Sell Value for this date, ticker, broker, investor type and board. |
| `net_value_1d` | `numeric` | No | — | buy_value_1d minus sell_value_1d for the same investor type and board. |
| `buy_lots_1d` | `numeric` | No | — | Source Buy Lots for this date, ticker, broker, investor type and board. |
| `sell_lots_1d` | `numeric` | No | — | Source Sell Lots for this date, ticker, broker, investor type and board. |
| `net_lots_1d` | `numeric` | No | — | buy_lots_1d minus sell_lots_1d for the same investor type and board. |
| `net_value_5d` | `numeric` | Yes | — | Sum of net_value_1d over 5 ticker transaction dates within broker, investor type and board; missing activity contributes zero. |
| `net_value_20d` | `numeric` | Yes | — | Sum of net_value_1d over 20 ticker transaction dates within broker, investor type and board; missing activity contributes zero. |
| `net_value_60d` | `numeric` | Yes | — | Sum of net_value_1d over 60 ticker transaction dates within broker, investor type and board; missing activity contributes zero. |
| `net_lots_5d` | `numeric` | Yes | — | Sum of net_lots_1d over 5 ticker transaction dates within broker, investor type and board. |
| `net_lots_20d` | `numeric` | Yes | — | Sum of net_lots_1d over 20 ticker transaction dates within broker, investor type and board. |
| `net_lots_60d` | `numeric` | Yes | — | Sum of net_lots_1d over 60 ticker transaction dates within broker, investor type and board. |
| `buy_days_20d` | `smallint` | Yes | — | Number of positive net-value dates in the complete 20-date window for this broker, investor type and board. |
| `sell_days_20d` | `smallint` | Yes | — | Number of negative net-value dates in the complete 20-date window for this broker, investor type and board. |
| `active_days_20d` | `smallint` | Yes | — | Number of dates with nonzero gross activity in the complete 20-date window for this broker, investor type and board. |
| `stock_trading_days_20d` | `smallint` | Yes | — | 20 after the ticker has 20 observed transaction dates across any investor type or board; otherwise NULL. |
| `buy_day_ratio_20d` | `double precision` | Yes | — | buy_days_20d divided by 20; for example 12 positive dates produces 0.60. |
| `buy_share_active_days_20d` | `double precision` | Yes | — | buy_days_20d divided by active_days_20d; NULL when there are no active dates. |
| `buy_days_60d` | `smallint` | Yes | — | Number of positive net-value dates in the complete 60-date window for this broker, investor type and board. |
| `sell_days_60d` | `smallint` | Yes | — | Number of negative net-value dates in the complete 60-date window for this broker, investor type and board. |
| `active_days_60d` | `smallint` | Yes | — | Number of dates with nonzero gross activity in the complete 60-date window for this broker, investor type and board. |
| `stock_trading_days_60d` | `smallint` | Yes | — | 60 after the ticker has 60 observed transaction dates across any investor type or board; otherwise NULL. |
| `buy_day_ratio_60d` | `double precision` | Yes | — | buy_days_60d divided by 60. |
| `buy_share_active_days_60d` | `double precision` | Yes | — | buy_days_60d divided by active_days_60d; NULL when there are no active dates. |
| `net_value_zscore_20d` | `double precision` | Yes | — | Current 20-date net value minus the mean of the preceding 252 complete 20-date values, divided by their sample standard deviation; current date excluded. |
| `net_value_zscore_60d` | `double precision` | Yes | — | Current 60-date net value minus the mean of the preceding 252 complete 60-date values, divided by their sample standard deviation; current date excluded. |
| `net_value_percentile_20d` | `double precision` | Yes | — | Empirical midrank percentile of current 20-date net value against the preceding 252 complete values in the same broker, investor type and board partition. |
| `net_value_percentile_60d` | `double precision` | Yes | — | Empirical midrank percentile of current 60-date net value against the preceding 252 complete values in the same broker, investor type and board partition. |
| `positive_net_value_20d` | `numeric` | Yes | — | Sum of positive daily net values in the complete 20-date window; zero when the complete window has no positive date. |
| `largest_buy_day_20d` | `numeric` | Yes | — | Largest positive daily net value in the complete 20-date window; NULL when no positive date exists. |
| `largest_buy_day_share_20d` | `double precision` | Yes | — | largest_buy_day_20d divided by positive_net_value_20d; for example 40 of 100 total positive flow produces 0.40. |
| `calculated_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Database statement timestamp when this canonical v2 row was materialized; not source event time or data availability time. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `Feature_02_Broker_Rolling_v2_board_check` | Check | `CHECK (market_board = ANY (ARRAY['Regular'::text, 'Nego'::text, 'Tunai'::text]))` |
| `Feature_02_Broker_Rolling_v2_gross_check` | Check | `CHECK (buy_value_1d >= 0::numeric AND sell_value_1d >= 0::numeric AND buy_lots_1d >= 0::numeric AND sell_lots_1d >= 0::numeric)` |
| `Feature_02_Broker_Rolling_v2_identity_check` | Check | `CHECK (btrim(ticker) <> ''::text AND btrim(broker) <> ''::text)` |
| `Feature_02_Broker_Rolling_v2_investor_type_check` | Check | `CHECK (investor_type = ANY (ARRAY['Domestic'::text, 'Foreign'::text]))` |
| `Feature_02_Broker_Rolling_v2_net_check` | Check | `CHECK (net_value_1d = (buy_value_1d - sell_value_1d) AND net_lots_1d = (buy_lots_1d - sell_lots_1d))` |
| `Feature_02_Broker_Rolling_v2_percentile_check` | Check | `CHECK ((net_value_percentile_20d IS NULL OR net_value_percentile_20d >= 0::double precision AND net_value_percentile_20d <= 100::double precision) AND (net_value_percentile_60d IS NULL OR net_value_percentile_60d >= 0::double precision AND net_value_percentile_60d <= 100::double precision))` |
| `Feature_02_Broker_Rolling_v2_ratio_check` | Check | `CHECK ((buy_day_ratio_20d IS NULL OR buy_day_ratio_20d >= 0::double precision AND buy_day_ratio_20d <= 1::double precision) AND (buy_share_active_days_20d IS NULL OR buy_share_active_days_20d >= 0::double precision AND buy_share_active_days_20d <= 1::double precision) AND (buy_day_ratio_60d IS NULL OR buy_day_ratio_60d >= 0::double precision AND buy_day_ratio_60d <= 1::double precision) AND (buy_share_active_days_60d IS NULL OR buy_share_active_days_60d >= 0::double precision AND buy_share_active_days_60d <= 1::double precision) AND (largest_buy_day_share_20d IS NULL OR largest_buy_day_share_20d >= 0::double precision AND largest_buy_day_share_20d <= 1::double precision))` |
| `Feature_02_Broker_Rolling_pkey` | Primary key | `PRIMARY KEY (ticker, market_board, broker, investor_type, date)` |

### Indexes

| Name | Definition |
|---|---|
| `Feature_02_Broker_Rolling_date_board_ticker_idx` | `CREATE INDEX "Feature_02_Broker_Rolling_date_board_ticker_idx" ON public."Feature_02_Broker_Rolling" USING btree (date, market_board, ticker)` |
| `Feature_02_Broker_Rolling_pkey` | `CREATE UNIQUE INDEX "Feature_02_Broker_Rolling_pkey" ON public."Feature_02_Broker_Rolling" USING btree (ticker, market_board, broker, investor_type, date)` |

## Feature_03_Stock_Broker_Daily

Feature 03 v2 stock-level broker structure by ticker and board. Domestic/Foreign flows use source Investor Type; broker-profile classifications are current metadata. Boards never mix.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `date` | `date` | No | — | Source transaction date for this ticker and market board. |
| `ticker` | `text` | No | — | Source broker-summary Symbol, including instruments outside the current stock universe. |
| `market_board` | `text` | No | — | Exact source board: Regular, Nego or Tunai; aggregates never mix boards. |
| `total_buy_value` | `numeric` | No | — | Sum of all broker buy_value_1d for the ticker, date and board. |
| `total_sell_value` | `numeric` | No | — | Sum of all broker sell_value_1d for the ticker, date and board. |
| `active_broker_count` | `smallint` | No | — | Brokers with nonzero gross buy/sell value or lots on the ticker, date and board. |
| `net_buy_broker_count` | `smallint` | No | — | Brokers whose aggregated daily net value is positive. |
| `net_sell_broker_count` | `smallint` | No | — | Brokers whose aggregated daily net value is negative. |
| `net_buy_broker_ratio` | `double precision` | Yes | — | net_buy_broker_count divided by active_broker_count; null when no broker is active. |
| `foreign_net_value` | `numeric` | No | — | Sum of Feature 02 net_value_1d where source investor_type is Foreign, across all brokers for this date, ticker and board. It is investor identity, not broker domicile. |
| `domestic_net_value` | `numeric` | No | — | Sum of Feature 02 net_value_1d where source investor_type is Domestic, across all brokers for this date, ticker and board. It is investor identity, not broker domicile. |
| `institutional_net_value` | `numeric` | No | — | Sum of daily broker net value where current broker_classification is Institutional-heavy. |
| `retail_net_value` | `numeric` | No | — | Sum of daily broker net value where current broker_classification is Retail-heavy. |
| `mixed_net_value` | `numeric` | No | — | Sum of daily broker net value where current broker_classification is Mixed. |
| `niche_net_value` | `numeric` | No | — | Sum of daily broker net value where current broker_classification is Niche. |
| `top_buyer` | `text` | Yes | — | Positive-net broker with the greatest daily net value; ties use broker code ascending. |
| `top_buyer_net_value` | `numeric` | Yes | — | Positive daily net value of top_buyer. |
| `top_seller` | `text` | Yes | — | Negative-net broker with the lowest daily net value; ties use broker code ascending. |
| `top_seller_net_value` | `numeric` | Yes | — | Negative daily net value of top_seller. |
| `top3_buyer_net_value` | `numeric` | No | — | Sum of the three greatest positive broker net values, with fewer used when fewer exist. |
| `positive_net_value_total` | `numeric` | No | — | Sum of every positive broker daily net value. |
| `top3_buyer_share` | `double precision` | Yes | — | top3_buyer_net_value divided by positive_net_value_total; null when the denominator is zero. |
| `broker_concentration_hhi` | `double precision` | Yes | — | Sum of squared absolute-net-flow weights across brokers; null when total absolute net value is zero. |
| `calculated_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Database statement timestamp when the row was calculated. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `Feature_03_Stock_Broker_Daily_board_check` | Check | `CHECK (market_board = ANY (ARRAY['Regular'::text, 'Nego'::text, 'Tunai'::text]))` |
| `Feature_03_Stock_Broker_Daily_count_check` | Check | `CHECK (active_broker_count >= 0 AND net_buy_broker_count >= 0 AND net_sell_broker_count >= 0 AND (net_buy_broker_count + net_sell_broker_count) <= active_broker_count)` |
| `Feature_03_Stock_Broker_Daily_dominant_check` | Check | `CHECK ((top_buyer IS NULL) = (top_buyer_net_value IS NULL) AND (top_seller IS NULL) = (top_seller_net_value IS NULL) AND (top_buyer_net_value IS NULL OR top_buyer_net_value > 0::numeric) AND (top_seller_net_value IS NULL OR top_seller_net_value < 0::numeric) AND top3_buyer_net_value >= 0::numeric AND positive_net_value_total >= top3_buyer_net_value)` |
| `Feature_03_Stock_Broker_Daily_gross_check` | Check | `CHECK (total_buy_value >= 0::numeric AND total_sell_value >= 0::numeric)` |
| `Feature_03_Stock_Broker_Daily_identity_check` | Check | `CHECK (btrim(ticker) <> ''::text)` |
| `Feature_03_Stock_Broker_Daily_ratio_check` | Check | `CHECK ((net_buy_broker_ratio IS NULL OR net_buy_broker_ratio >= 0::double precision AND net_buy_broker_ratio <= 1::double precision) AND (top3_buyer_share IS NULL OR top3_buyer_share >= 0::double precision AND top3_buyer_share <= 1::double precision) AND (broker_concentration_hhi IS NULL OR broker_concentration_hhi > 0::double precision AND broker_concentration_hhi <= 1::double precision))` |
| `Feature_03_Stock_Broker_Daily_pkey` | Primary key | `PRIMARY KEY (ticker, market_board, date)` |

### Indexes

| Name | Definition |
|---|---|
| `Feature_03_Stock_Broker_Daily_date_board_ticker_idx` | `CREATE INDEX "Feature_03_Stock_Broker_Daily_date_board_ticker_idx" ON public."Feature_03_Stock_Broker_Daily" USING btree (date, market_board, ticker)` |
| `Feature_03_Stock_Broker_Daily_pkey` | `CREATE UNIQUE INDEX "Feature_03_Stock_Broker_Daily_pkey" ON public."Feature_03_Stock_Broker_Daily" USING btree (ticker, market_board, date)` |

## Feature_04_Technical_Indicator

57-column cross-asset Daily technical Feature04. Identity is asset_type/ticker/trade_date/timeframe; close is copied from the exact classified source row and the other measures are calculated per asset/ticker history.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `ticker` | `text` | No | — | IDX security code copied from source ticker. ticker |
| `trade_date` | `date` | No | — | Trading observation date copied from source date. date |
| `timeframe` | `text` | No | — | Verified daily timeframe copied exactly from source. timeframe = Daily |
| `sma_20` | `double precision` | Yes | — | Unweighted mean of 20 observed closes. TA-Lib SMA(close,20) |
| `sma_50` | `double precision` | Yes | — | Unweighted mean of 50 observed closes. TA-Lib SMA(close,50) |
| `ema_12` | `double precision` | Yes | — | Fast exponentially weighted close; alpha=2/13. Seed=SMA(first12 closes); EMA[t]=EMA[t-1]+2/13*(close[t]-EMA[t-1]) |
| `ema_26` | `double precision` | Yes | — | Slow exponentially weighted close; alpha=2/27. Seed=SMA(first26 closes); EMA[t]=EMA[t-1]+2/27*(close[t]-EMA[t-1]) |
| `rsi_14` | `double precision` | Yes | — | Wilder gain/loss oscillator on 14 consecutive close changes, scaled 0–100. TA-Lib RSI(close,14): SMA seed of 14 gains/losses; RMA alpha=1/14; 100*gain/(gain+loss); both-zero uses native 0 |
| `macd` | `double precision` | Yes | — | Difference of the stored fast and slow EMA price baselines. ema_12 - ema_26; independently SMA-seeded EMAs, not TA-Lib MACD internal fast reseeding |
| `macd_signal` | `double precision` | Yes | — | Nine-period EMA of valid MACD line observations. Seed=SMA(first9 valid macd); signal[t]=signal[t-1]+0.2*(macd[t]-signal[t-1]) |
| `macd_histogram` | `double precision` | Yes | — | Difference between MACD line and its nine-period signal. macd - macd_signal |
| `atr_14` | `double precision` | Yes | — | Wilder average of 14 true ranges using prior observed close. TA-Lib ATR(high,low,close,14): TR=max(high-low,abs(high-prev_close),abs(low-prev_close)); first TR excludes bar1; SMA seed then RMA alpha=1/14 |
| `bb_upper_20` | `double precision` | Yes | — | Upper 20-period Bollinger band, population standard deviation multiplier 2. SMA20(close) + 2*sqrt(sum((close-SMA20)^2)/20) |
| `bb_middle_20` | `double precision` | Yes | — | Middle 20-period Bollinger band, identical to SMA20. SMA20(close) |
| `bb_lower_20` | `double precision` | Yes | — | Lower 20-period Bollinger band, population standard deviation multiplier 2. SMA20(close) - 2*sqrt(sum((close-SMA20)^2)/20) |
| `cdl_piercing` | `integer` | Yes | — | Native TA-Lib piercing pattern recognition code from historical OHLC. TA-Lib CDLPIERCING(open,high,low,close), default candle settings; parameters={}; native signed integers including non-100 codes retained |
| `cdl_morning_star` | `integer` | Yes | — | Native TA-Lib morning star pattern recognition code from historical OHLC. TA-Lib CDLMORNINGSTAR(open,high,low,close), default candle settings; parameters={'penetration': 0.3}; native signed integers including non-100 codes retained |
| `cdl_morning_doji_star` | `integer` | Yes | — | Native TA-Lib morning doji star pattern recognition code from historical OHLC. TA-Lib CDLMORNINGDOJISTAR(open,high,low,close), default candle settings; parameters={'penetration': 0.3}; native signed integers including non-100 codes retained |
| `cdl_engulfing` | `integer` | Yes | — | Native TA-Lib engulfing pattern recognition code from historical OHLC. TA-Lib CDLENGULFING(open,high,low,close), default candle settings; parameters={}; native signed integers including non-100 codes retained |
| `cdl_3_white_soldiers` | `integer` | Yes | — | Native TA-Lib 3 white soldiers pattern recognition code from historical OHLC. TA-Lib CDL3WHITESOLDIERS(open,high,low,close), default candle settings; parameters={}; native signed integers including non-100 codes retained |
| `cdl_hammer` | `integer` | Yes | — | Native TA-Lib hammer pattern recognition code from historical OHLC. TA-Lib CDLHAMMER(open,high,low,close), default candle settings; parameters={}; native signed integers including non-100 codes retained |
| `cdl_inverted_hammer` | `integer` | Yes | — | Native TA-Lib inverted hammer pattern recognition code from historical OHLC. TA-Lib CDLINVERTEDHAMMER(open,high,low,close), default candle settings; parameters={}; native signed integers including non-100 codes retained |
| `cdl_3_inside` | `integer` | Yes | — | Native TA-Lib 3 inside pattern recognition code from historical OHLC. TA-Lib CDL3INSIDE(open,high,low,close), default candle settings; parameters={}; native signed integers including non-100 codes retained |
| `cdl_3_outside` | `integer` | Yes | — | Native TA-Lib 3 outside pattern recognition code from historical OHLC. TA-Lib CDL3OUTSIDE(open,high,low,close), default candle settings; parameters={}; native signed integers including non-100 codes retained |
| `cdl_harami` | `integer` | Yes | — | Native TA-Lib harami pattern recognition code from historical OHLC. TA-Lib CDLHARAMI(open,high,low,close), default candle settings; parameters={}; native signed integers including non-100 codes retained |
| `cdl_harami_cross` | `integer` | Yes | — | Native TA-Lib harami cross pattern recognition code from historical OHLC. TA-Lib CDLHARAMICROSS(open,high,low,close), default candle settings; parameters={}; native signed integers including non-100 codes retained |
| `cdl_dark_cloud_cover` | `integer` | Yes | — | Native TA-Lib dark cloud cover pattern recognition code from historical OHLC. TA-Lib CDLDARKCLOUDCOVER(open,high,low,close), default candle settings; parameters={'penetration': 0.5}; native signed integers including non-100 codes retained |
| `cdl_evening_star` | `integer` | Yes | — | Native TA-Lib evening star pattern recognition code from historical OHLC. TA-Lib CDLEVENINGSTAR(open,high,low,close), default candle settings; parameters={'penetration': 0.3}; native signed integers including non-100 codes retained |
| `cdl_evening_doji_star` | `integer` | Yes | — | Native TA-Lib evening doji star pattern recognition code from historical OHLC. TA-Lib CDLEVENINGDOJISTAR(open,high,low,close), default candle settings; parameters={'penetration': 0.3}; native signed integers including non-100 codes retained |
| `cdl_3_black_crows` | `integer` | Yes | — | Native TA-Lib 3 black crows pattern recognition code from historical OHLC. TA-Lib CDL3BLACKCROWS(open,high,low,close), default candle settings; parameters={}; native signed integers including non-100 codes retained |
| `cdl_shooting_star` | `integer` | Yes | — | Native TA-Lib shooting star pattern recognition code from historical OHLC. TA-Lib CDLSHOOTINGSTAR(open,high,low,close), default candle settings; parameters={}; native signed integers including non-100 codes retained |
| `cdl_hanging_man` | `integer` | Yes | — | Native TA-Lib hanging man pattern recognition code from historical OHLC. TA-Lib CDLHANGINGMAN(open,high,low,close), default candle settings; parameters={}; native signed integers including non-100 codes retained |
| `cdl_doji` | `integer` | Yes | — | Native TA-Lib doji pattern recognition code from historical OHLC. TA-Lib CDLDOJI(open,high,low,close), default candle settings; parameters={}; native signed integers including non-100 codes retained |
| `cdl_dragonfly_doji` | `integer` | Yes | — | Native TA-Lib dragonfly doji pattern recognition code from historical OHLC. TA-Lib CDLDRAGONFLYDOJI(open,high,low,close), default candle settings; parameters={}; native signed integers including non-100 codes retained |
| `cdl_gravestone_doji` | `integer` | Yes | — | Native TA-Lib gravestone doji pattern recognition code from historical OHLC. TA-Lib CDLGRAVESTONEDOJI(open,high,low,close), default candle settings; parameters={}; native signed integers including non-100 codes retained |
| `cdl_marubozu` | `integer` | Yes | — | Native TA-Lib marubozu pattern recognition code from historical OHLC. TA-Lib CDLMARUBOZU(open,high,low,close), default candle settings; parameters={}; native signed integers including non-100 codes retained |
| `cdl_kicking` | `integer` | Yes | — | Native TA-Lib kicking pattern recognition code from historical OHLC. TA-Lib CDLKICKING(open,high,low,close), default candle settings; parameters={}; native signed integers including non-100 codes retained |
| `cdl_rise_fall_3_methods` | `integer` | Yes | — | Native TA-Lib rise fall 3 methods pattern recognition code from historical OHLC. TA-Lib CDLRISEFALL3METHODS(open,high,low,close), default candle settings; parameters={}; native signed integers including non-100 codes retained |
| `cdl_mat_hold` | `integer` | Yes | — | Native TA-Lib mat hold pattern recognition code from historical OHLC. TA-Lib CDLMATHOLD(open,high,low,close), default candle settings; parameters={'penetration': 0.5}; native signed integers including non-100 codes retained |
| `cdl_hikkake` | `integer` | Yes | — | Native TA-Lib hikkake pattern recognition code from historical OHLC. TA-Lib CDLHIKKAKE(open,high,low,close), default candle settings; parameters={}; native signed integers including non-100 codes retained |
| `calculation_version` | `text` | No | — | Version binds formulas, seeds and pinned TA-Lib versions. engine.VERSION |
| `calculated_at` | `timestamp with time zone` | No | — | Timezone-aware execution time of the last changed output row. UTC execution timestamp; unchanged UPSERT preserves existing timestamp |
| `adx_14` | `double precision` | Yes | — | Wilder average directional index measuring trend strength on a 0–100 scale. TA-Lib ADX(high,low,close,14); directional movement and true range Wilder-smoothed over 14, DX=100*abs(+DI-(-DI))/(+DI+(-DI)), then 14-period Wilder ADX; native zero-denominator convention; unstable period 0 |
| `ema_50` | `double precision` | Yes | — | Fifty-observation exponentially weighted close; alpha=2/51. Seed=SMA(first50 closes); EMA[t]=EMA[t-1]+2/51*(close[t]-EMA[t-1]) |
| `ema_200` | `double precision` | Yes | — | Two-hundred-observation exponentially weighted close; alpha=2/201. Seed=SMA(first200 closes); EMA[t]=EMA[t-1]+2/201*(close[t]-EMA[t-1]) |
| `inside_bar` | `integer` | Yes | — | Strict current-candle range containment within the previous valid observed candle. 1 if high[t]<high[t-1] AND low[t]>low[t-1], else 0; compare original numeric prices; no future candle |
| `smi` | `double precision` | Yes | — | Stochastic Momentum Index: double-smoothed close displacement from the midpoint of a rolling 14-bar high/low range. 200*EMA5(EMA5(close-(highest14(high)+lowest14(low))/2))/EMA5(EMA5(highest14(high)-lowest14(low))); first-input EMA seed, alpha=1/3, partial extrema windows at startup NULL for an uncomputed ticker, invalid OHLCV, or a zero double-smoothed range; no zero imputation. |
| `tracking_high` | `integer` | Yes | — | High-search state after all current-bar Pine blocks execute. Set 1 on SMI crossover above +40, reset 0 on SMI crossunder below +40; initial 0; recross above +40 resets the temporary peak Uncomputed/invalid row NULL; valid processed row is INTEGER 1 while tracking or 0 otherwise, including initialization. |
| `tracking_low` | `integer` | Yes | — | Low-search state after all current-bar Pine blocks execute. Set 1 on SMI crossunder below -40, reset 0 on SMI crossover above -40; initial 0; recross below -40 resets the temporary trough Uncomputed/invalid row NULL; valid processed row is INTEGER 1 while tracking or 0 otherwise, including initialization. |
| `temp_high` | `double precision` | Yes | — | Provisional highest high in the current active SMI-above-40 tracking interval. Initialize high on +40 upcross; update only if tracking_high and SMI>40 and high>temp_high; clear on +40 downcross after copying to last_swing_high NULL outside active high tracking, including immediately after confirmation; uncomputed/invalid rows NULL. |
| `temp_high_bar` | `integer` | Yes | — | Zero-based source observation index of the currently tracked temporary high. bar_index on temp_high initialization or strictly higher high; index 0 is earliest available source row for this ticker and timeframe; NULL when temp_high is cleared NULL together with temp_high; uncomputed/invalid rows NULL. Zero is a valid first-bar index. |
| `temp_low` | `double precision` | Yes | — | Provisional lowest low in the current active SMI-below-minus-40 tracking interval. Initialize low on -40 downcross; update only if tracking_low and SMI<-40 and low<temp_low; clear on -40 upcross NULL outside active low tracking, including immediately after confirmation; uncomputed/invalid rows NULL. |
| `temp_low_bar` | `integer` | Yes | — | Zero-based source observation index of the currently tracked temporary low. bar_index on temp_low initialization or strictly lower low; index 0 is earliest available source row for this ticker and timeframe; NULL when temp_low is cleared NULL together with temp_low; uncomputed/invalid rows NULL. Zero is a valid first-bar index. |
| `last_swing_high` | `double precision` | Yes | — | Latest swing-high price available after its SMI-downcross confirmation, carried forward. When tracking_high and SMI[t]<40 and SMI[t-1]>=40, copy tracked temp_high before clearing it; retain until the next high confirmation NULL before the first confirmed high or after invalid-row state reset; uncomputed rows NULL. |
| `break_swing_high` | `integer` | Yes | — | Integer event flag for the supplied Pine close/last-swing-high crossover. 1 iff last_swing_high[t] and last_swing_high[t-1] exist AND close[t]>last_swing_high[t] AND close[t-1]<=last_swing_high[t-1]; otherwise 0 on a valid processed bar Valid processed row INTEGER 1 on a crossover, otherwise INTEGER 0, including before any confirmed high. NULL only for uncomputed/invalid rows. |
| `asset_type` | `text` | No | — | Universe-derived asset class: equity from IDX_Stock_Universe; bonds from Universe_Fixed_income. |
| `close` | `double precision` | No | — | Daily closing price copied from the exact equity or bonds source row matched on ticker and trade_date. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `Feature_04_Technical_Indicator_asset_type_check` | Check | `CHECK (asset_type = ANY (ARRAY['equity'::text, 'bonds'::text]))` |
| `Feature_04_Technical_Indicator_atr_14_check` | Check | `CHECK (atr_14 IS NULL OR atr_14 > '-Infinity'::double precision AND atr_14 < 'Infinity'::double precision)` |
| `Feature_04_Technical_Indicator_atr_14_check1` | Check | `CHECK (atr_14 IS NULL OR atr_14 >= 0::double precision)` |
| `Feature_04_Technical_Indicator_bb_lower_20_check` | Check | `CHECK (bb_lower_20 IS NULL OR bb_lower_20 > '-Infinity'::double precision AND bb_lower_20 < 'Infinity'::double precision)` |
| `Feature_04_Technical_Indicator_bb_middle_20_check` | Check | `CHECK (bb_middle_20 IS NULL OR bb_middle_20 > '-Infinity'::double precision AND bb_middle_20 < 'Infinity'::double precision)` |
| `Feature_04_Technical_Indicator_bb_upper_20_check` | Check | `CHECK (bb_upper_20 IS NULL OR bb_upper_20 > '-Infinity'::double precision AND bb_upper_20 < 'Infinity'::double precision)` |
| `Feature_04_Technical_Indicator_calculation_version_check` | Check | `CHECK (btrim(calculation_version) <> ''::text)` |
| `Feature_04_Technical_Indicator_close_finite_check` | Check | `CHECK (close > '-Infinity'::double precision AND close < 'Infinity'::double precision)` |
| `Feature_04_Technical_Indicator_close_nonnegative_check` | Check | `CHECK (close >= 0::double precision)` |
| `Feature_04_Technical_Indicator_ema_12_check` | Check | `CHECK (ema_12 IS NULL OR ema_12 > '-Infinity'::double precision AND ema_12 < 'Infinity'::double precision)` |
| `Feature_04_Technical_Indicator_ema_26_check` | Check | `CHECK (ema_26 IS NULL OR ema_26 > '-Infinity'::double precision AND ema_26 < 'Infinity'::double precision)` |
| `Feature_04_Technical_Indicator_macd_check` | Check | `CHECK (macd IS NULL OR macd > '-Infinity'::double precision AND macd < 'Infinity'::double precision)` |
| `Feature_04_Technical_Indicator_macd_histogram_check` | Check | `CHECK (macd_histogram IS NULL OR macd_histogram > '-Infinity'::double precision AND macd_histogram < 'Infinity'::double precision)` |
| `Feature_04_Technical_Indicator_macd_signal_check` | Check | `CHECK (macd_signal IS NULL OR macd_signal > '-Infinity'::double precision AND macd_signal < 'Infinity'::double precision)` |
| `Feature_04_Technical_Indicator_rsi_14_check` | Check | `CHECK (rsi_14 IS NULL OR rsi_14 > '-Infinity'::double precision AND rsi_14 < 'Infinity'::double precision)` |
| `Feature_04_Technical_Indicator_rsi_14_check1` | Check | `CHECK (rsi_14 IS NULL OR rsi_14 >= 0::double precision AND rsi_14 <= 100::double precision)` |
| `Feature_04_Technical_Indicator_sma_20_check` | Check | `CHECK (sma_20 IS NULL OR sma_20 > '-Infinity'::double precision AND sma_20 < 'Infinity'::double precision)` |
| `Feature_04_Technical_Indicator_sma_50_check` | Check | `CHECK (sma_50 IS NULL OR sma_50 > '-Infinity'::double precision AND sma_50 < 'Infinity'::double precision)` |
| `Feature_04_Technical_Indicator_ticker_check` | Check | `CHECK (ticker = upper(btrim(ticker)) AND ticker <> ''::text)` |
| `Feature_04_Technical_Indicator_timeframe_check` | Check | `CHECK (timeframe = 'Daily'::text)` |
| `feature04_adx_14_valid` | Check | `CHECK (adx_14 IS NULL OR adx_14 >= 0::double precision AND adx_14 <= 100::double precision)` |
| `feature04_break_swing_high_valid` | Check | `CHECK (break_swing_high IS NULL OR (break_swing_high = ANY (ARRAY[0, 1])))` |
| `feature04_ema_200_finite` | Check | `CHECK (ema_200 IS NULL OR ema_200 > '-Infinity'::double precision AND ema_200 < 'Infinity'::double precision)` |
| `feature04_ema_50_finite` | Check | `CHECK (ema_50 IS NULL OR ema_50 > '-Infinity'::double precision AND ema_50 < 'Infinity'::double precision)` |
| `feature04_inside_bar_binary` | Check | `CHECK (inside_bar IS NULL OR (inside_bar = ANY (ARRAY[0, 1])))` |
| `feature04_last_swing_high_valid` | Check | `CHECK (last_swing_high IS NULL OR last_swing_high > '-Infinity'::double precision AND last_swing_high < 'Infinity'::double precision)` |
| `feature04_smi_valid` | Check | `CHECK (smi IS NULL OR smi > '-Infinity'::double precision AND smi < 'Infinity'::double precision)` |
| `feature04_temp_high_bar_valid` | Check | `CHECK (temp_high_bar IS NULL OR temp_high_bar >= 0)` |
| `feature04_temp_high_valid` | Check | `CHECK (temp_high IS NULL OR temp_high > '-Infinity'::double precision AND temp_high < 'Infinity'::double precision)` |
| `feature04_temp_low_bar_valid` | Check | `CHECK (temp_low_bar IS NULL OR temp_low_bar >= 0)` |
| `feature04_temp_low_valid` | Check | `CHECK (temp_low IS NULL OR temp_low > '-Infinity'::double precision AND temp_low < 'Infinity'::double precision)` |
| `feature04_tracking_high_valid` | Check | `CHECK (tracking_high IS NULL OR (tracking_high = ANY (ARRAY[0, 1])))` |
| `feature04_tracking_low_valid` | Check | `CHECK (tracking_low IS NULL OR (tracking_low = ANY (ARRAY[0, 1])))` |
| `Feature_04_Technical_Indicator_pkey` | Primary key | `PRIMARY KEY (ticker, trade_date, timeframe, asset_type)` |

### Indexes

| Name | Definition |
|---|---|
| `Feature_04_Technical_Indicator_pkey` | `CREATE UNIQUE INDEX "Feature_04_Technical_Indicator_pkey" ON public."Feature_04_Technical_Indicator" USING btree (ticker, trade_date, timeframe, asset_type)` |

## Feature_Calculation_Log

Completed attempt history for Feature 01 calculation queue items, including retries and superseded claims.

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

Durable Feature 01 work item per changed price candle; DONE means feature calculation succeeded, not price ingestion.

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
| `source_attempt_count` | `integer` | No | `0` | Worker claims for the current price ingestion version; resets on source re-ingestion while attempt_count remains lifetime-monotonic. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `Feature_Calculation_Queue_attempt_check` | Check | `CHECK (attempt_count >= 0)` |
| `Feature_Calculation_Queue_claim_check` | Check | `CHECK ((status = 'PROCESSING'::text) = (claimed_at IS NOT NULL AND claim_token IS NOT NULL AND claim_expires_at IS NOT NULL))` |
| `Feature_Calculation_Queue_completion_check` | Check | `CHECK ((status = 'DONE'::text) = (completed_at IS NOT NULL))` |
| `Feature_Calculation_Queue_feature_check` | Check | `CHECK (feature_table = 'Feature_01_Stock_Daily'::text)` |
| `Feature_Calculation_Queue_source_attempt_check` | Check | `CHECK (source_attempt_count >= 0 AND source_attempt_count <= attempt_count)` |
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

Machine-readable semantic and usage contract for validated Feature-table columns.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `feature_table` | `text` | No | — | Exact physical name of a verified table registered as category Feature. |
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
| `semantic_role` | `text` | No | `'MEASURE'::text` | IDENTITY, DIMENSION, or MEASURE role used by generic query tools. |
| `allowed_aggregations` | `ARRAY` | No | `'{}'::text[]` | Allow-list of generic aggregations valid for this column. |
| `ranking_interpretation` | `text` | No | `'CONTEXTUAL'::text` | Default analytical direction; CONTEXTUAL requires the request to state direction. |
| `is_filterable` | `boolean` | No | `true` | Whether generic tools may use this column in a structured filter. |
| `is_groupable` | `boolean` | No | `false` | Whether generic tools may use this column as a grouping dimension. |
| `availability_rule` | `text` | No | `'Use no earlier than the next valid trading observation after observation date unless earlier source availability is documented.'::text` | Decision-time rule used by historical validation and no-look-ahead checks. |
| `point_in_time_safe` | `boolean` | No | `false` | True only when the value itself is time-indexed and usable under its documented availability rule; analysis-level universe limitations still apply. |
| `historical_metadata_warning` | `text` | Yes | — | Required warning when a definition uses current state or otherwise incomplete historical metadata. |
| `analytical_interpretation` | `text` | No | — | Plain-language interpretation of sign, magnitude, category and analytical context; not a formula substitute. |
| `recommended_use` | `text` | No | — | Approved analyst use cases for this exact Feature column and grain. |
| `misuse_warning` | `text` | No | — | Column-specific analytical traps, null/board/window caveats and claims that must not be inferred. |
| `semantic_review_status` | `text` | No | — | Evidence grade for semantic guidance: NEEDS_REVIEW, SOURCE_VERIFIED, or CALCULATION_VERIFIED. |
| `validation_evidence` | `ARRAY` | No | — | Repository evidence paths supporting the formula and semantic review status. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `Feature_Catalog_aggregations_check` | Check | `CHECK (allowed_aggregations <@ ARRAY['SUM'::text, 'AVG'::text, 'MEDIAN'::text, 'MIN'::text, 'MAX'::text, 'COUNT'::text, 'COUNT_DISTINCT'::text, 'PERCENTILE'::text, 'WEIGHTED_AVG'::text])` |
| `Feature_Catalog_availability_rule_check` | Check | `CHECK (btrim(availability_rule) <> ''::text)` |
| `Feature_Catalog_feature_category_check` | Check | `CHECK (feature_category = ANY (ARRAY['Identity'::text, 'Metadata'::text, 'Price'::text, 'Return'::text, 'Volatility'::text, 'Volume'::text, 'Price Positioning'::text, 'Broker Flow'::text, 'Broker Persistence'::text, 'Broker Abnormality'::text, 'Broker Concentration'::text, 'Broker Classification'::text, 'Historical Outcome'::text, 'Smart Money'::text, 'Data Quality'::text]))` |
| `Feature_Catalog_ranking_interpretation_check` | Check | `CHECK (ranking_interpretation = ANY (ARRAY['HIGHER'::text, 'LOWER'::text, 'CONTEXTUAL'::text, 'NOT_APPLICABLE'::text]))` |
| `Feature_Catalog_required_text_check` | Check | `CHECK (btrim(feature_table) <> ''::text AND btrim(feature_column) <> ''::text AND btrim(grain) <> ''::text AND btrim(feature_category) <> ''::text AND btrim(definition) <> ''::text AND btrim(calculation) <> ''::text AND btrim(source_tables) <> ''::text AND btrim(source_columns) <> ''::text AND btrim(lookback_window) <> ''::text AND btrim(minimum_history) <> ''::text AND btrim(unit) <> ''::text AND btrim(null_rule) <> ''::text AND btrim(refresh_trigger) <> ''::text AND btrim(dependency_rule) <> ''::text AND btrim(version) <> ''::text)` |
| `Feature_Catalog_semantic_guidance_check` | Check | `CHECK (btrim(analytical_interpretation) <> ''::text AND btrim(recommended_use) <> ''::text AND btrim(misuse_warning) <> ''::text)` |
| `Feature_Catalog_semantic_review_status_check` | Check | `CHECK (semantic_review_status = ANY (ARRAY['NEEDS_REVIEW'::text, 'SOURCE_VERIFIED'::text, 'CALCULATION_VERIFIED'::text]))` |
| `Feature_Catalog_semantic_role_check` | Check | `CHECK (semantic_role = ANY (ARRAY['IDENTITY'::text, 'DIMENSION'::text, 'MEASURE'::text]))` |
| `Feature_Catalog_timestamps_check` | Check | `CHECK (updated_at >= created_at)` |
| `Feature_Catalog_validation_evidence_check` | Check | `CHECK (cardinality(validation_evidence) > 0 AND array_position(validation_evidence, ''::text) IS NULL)` |
| `Feature_Catalog_version_check` | Check | `CHECK (version ~ '^v[1-9][0-9]*$'::text)` |
| `Feature_Catalog_pkey` | Primary key | `PRIMARY KEY (feature_table, feature_column, version)` |

### Indexes

| Name | Definition |
|---|---|
| `Feature_Catalog_one_active_definition_idx` | `CREATE UNIQUE INDEX "Feature_Catalog_one_active_definition_idx" ON public."Feature_Catalog" USING btree (feature_table, feature_column) WHERE is_active` |
| `Feature_Catalog_pkey` | `CREATE UNIQUE INDEX "Feature_Catalog_pkey" ON public."Feature_Catalog" USING btree (feature_table, feature_column, version)` |

## Feature_Relationship_Catalog

Versioned safe-join and grain contracts between verified Feature tables.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `left_feature_table` | `text` | No | — | No column description has been recorded. |
| `right_feature_table` | `text` | No | — | No column description has been recorded. |
| `left_join_columns` | `ARRAY` | No | — | No column description has been recorded. |
| `right_join_columns` | `ARRAY` | No | — | No column description has been recorded. |
| `relationship_type` | `text` | No | — | No column description has been recorded. |
| `safe_output_grain` | `text` | No | — | No column description has been recorded. |
| `requires_preaggregation` | `boolean` | No | — | No column description has been recorded. |
| `definition` | `text` | No | — | No column description has been recorded. |
| `version` | `text` | No | `'v1'::text` | No column description has been recorded. |
| `is_active` | `boolean` | No | `true` | No column description has been recorded. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | No column description has been recorded. |
| `updated_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `Feature_Relationship_Catalog_columns_check` | Check | `CHECK (cardinality(left_join_columns) > 0 AND cardinality(left_join_columns) = cardinality(right_join_columns))` |
| `Feature_Relationship_Catalog_type_check` | Check | `CHECK (relationship_type = ANY (ARRAY['ONE_TO_ONE'::text, 'ONE_TO_MANY'::text, 'MANY_TO_ONE'::text, 'MANY_TO_MANY'::text]))` |
| `Feature_Relationship_Catalog_version_check` | Check | `CHECK (version ~ '^v[1-9][0-9]*$'::text)` |
| `Feature_Relationship_Catalog_pkey` | Primary key | `PRIMARY KEY (left_feature_table, right_feature_table, version)` |

### Indexes

| Name | Definition |
|---|---|
| `Feature_Relationship_Catalog_pkey` | `CREATE UNIQUE INDEX "Feature_Relationship_Catalog_pkey" ON public."Feature_Relationship_Catalog" USING btree (left_feature_table, right_feature_table, version)` |

## Feature_Status

Current per-ticker Feature 01 calculation state; SUCCESS requires all committed source changes to be processed.

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

## Golden_Analysis_Test

Versioned analytical correctness and safety expectations; evaluation compares data and methodology rather than exact prose.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `test_id` | `text` | No | — | No column description has been recorded. |
| `version` | `text` | No | `'v1'::text` | No column description has been recorded. |
| `category` | `text` | No | — | No column description has been recorded. |
| `question` | `text` | No | — | No column description has been recorded. |
| `required_capabilities` | `ARRAY` | No | `'{}'::text[]` | No column description has been recorded. |
| `fixed_start_date` | `date` | Yes | — | No column description has been recorded. |
| `fixed_end_date` | `date` | Yes | — | No column description has been recorded. |
| `expected_features` | `ARRAY` | No | `'{}'::text[]` | No column description has been recorded. |
| `expected_tools` | `ARRAY` | No | `'{}'::text[]` | No column description has been recorded. |
| `expected_conditions` | `jsonb` | No | `'{}'::jsonb` | No column description has been recorded. |
| `tolerance` | `jsonb` | No | `'{}'::jsonb` | No column description has been recorded. |
| `expected_warnings` | `ARRAY` | No | `'{}'::text[]` | No column description has been recorded. |
| `expected_status` | `text` | No | — | No column description has been recorded. |
| `is_active` | `boolean` | No | `true` | No column description has been recorded. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | No column description has been recorded. |
| `updated_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `Golden_Analysis_Test_category_check` | Check | `CHECK (category = ANY (ARRAY['RETRIEVAL'::text, 'BROKER_ACCUMULATION'::text, 'CROSS_FEATURE'::text, 'PERIOD_COMPARISON'::text, 'READINESS'::text, 'EVENT_STUDY'::text, 'SIGNAL_VALIDATION'::text, 'BACKTEST'::text, 'SAFETY'::text, 'DATA_QUALITY'::text, 'POINT_IN_TIME'::text, 'NO_LOOKAHEAD'::text, 'REPRODUCIBILITY'::text, 'TOKEN_CONTEXT'::text]))` |
| `Golden_Analysis_Test_dates_check` | Check | `CHECK (fixed_start_date IS NULL OR fixed_end_date IS NULL OR fixed_end_date >= fixed_start_date)` |
| `Golden_Analysis_Test_json_check` | Check | `CHECK (jsonb_typeof(expected_conditions) = 'object'::text AND jsonb_typeof(tolerance) = 'object'::text)` |
| `Golden_Analysis_Test_required_text_check` | Check | `CHECK (btrim(test_id) <> ''::text AND btrim(category) <> ''::text AND btrim(question) <> ''::text)` |
| `Golden_Analysis_Test_status_check` | Check | `CHECK (expected_status = ANY (ARRAY['SUCCESS'::text, 'WARNING'::text, 'REJECTED'::text]))` |
| `Golden_Analysis_Test_version_check` | Check | `CHECK (version ~ '^v[1-9][0-9]*$'::text)` |
| `Golden_Analysis_Test_pkey` | Primary key | `PRIMARY KEY (test_id, version)` |

### Indexes

| Name | Definition |
|---|---|
| `Golden_Analysis_Test_one_active_version_idx` | `CREATE UNIQUE INDEX "Golden_Analysis_Test_one_active_version_idx" ON public."Golden_Analysis_Test" USING btree (test_id) WHERE is_active` |
| `Golden_Analysis_Test_pkey` | `CREATE UNIQUE INDEX "Golden_Analysis_Test_pkey" ON public."Golden_Analysis_Test" USING btree (test_id, version)` |

## Golden_Analysis_Test_Result

Per-test observed metrics, warnings, methodology checks, evidence and token usage.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `run_id` | `uuid` | No | — | No column description has been recorded. |
| `test_id` | `text` | No | — | No column description has been recorded. |
| `test_version` | `text` | No | — | No column description has been recorded. |
| `request_id` | `uuid` | Yes | — | No column description has been recorded. |
| `status` | `text` | No | — | No column description has been recorded. |
| `observed_metrics` | `jsonb` | No | `'{}'::jsonb` | No column description has been recorded. |
| `deviation` | `jsonb` | No | `'{}'::jsonb` | No column description has been recorded. |
| `observed_warnings` | `ARRAY` | No | `'{}'::text[]` | No column description has been recorded. |
| `evidence_ids` | `ARRAY` | No | `'{}'::uuid[]` | No column description has been recorded. |
| `methodology_checks` | `jsonb` | No | `'{}'::jsonb` | No column description has been recorded. |
| `input_tokens` | `integer` | No | `0` | No column description has been recorded. |
| `output_tokens` | `integer` | No | `0` | No column description has been recorded. |
| `total_tokens` | `integer` | No | `0` | No column description has been recorded. |
| `duration_ms` | `integer` | Yes | — | No column description has been recorded. |
| `failure_reason` | `text` | Yes | — | No column description has been recorded. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `Golden_Analysis_Test_Result_metrics_check` | Check | `CHECK (jsonb_typeof(observed_metrics) = 'object'::text AND jsonb_typeof(deviation) = 'object'::text AND jsonb_typeof(methodology_checks) = 'object'::text)` |
| `Golden_Analysis_Test_Result_status_check` | Check | `CHECK (status = ANY (ARRAY['PASS'::text, 'FAIL'::text, 'ERROR'::text, 'SKIPPED'::text]))` |
| `Golden_Analysis_Test_Result_usage_check` | Check | `CHECK (input_tokens >= 0 AND output_tokens >= 0 AND total_tokens >= 0 AND (duration_ms IS NULL OR duration_ms >= 0))` |
| `Golden_Analysis_Test_Result_request_id_fkey` | Foreign key | `FOREIGN KEY (request_id) REFERENCES "Analysis_Request"(request_id) ON DELETE SET NULL` |
| `Golden_Analysis_Test_Result_run_id_fkey` | Foreign key | `FOREIGN KEY (run_id) REFERENCES "Golden_Analysis_Test_Run"(run_id) ON DELETE CASCADE` |
| `Golden_Analysis_Test_Result_test_fkey` | Foreign key | `FOREIGN KEY (test_id, test_version) REFERENCES "Golden_Analysis_Test"(test_id, version)` |
| `Golden_Analysis_Test_Result_pkey` | Primary key | `PRIMARY KEY (run_id, test_id, test_version)` |

### Indexes

| Name | Definition |
|---|---|
| `Golden_Analysis_Test_Result_pkey` | `CREATE UNIQUE INDEX "Golden_Analysis_Test_Result_pkey" ON public."Golden_Analysis_Test_Result" USING btree (run_id, test_id, test_version)` |
| `Golden_Analysis_Test_Result_test_idx` | `CREATE INDEX "Golden_Analysis_Test_Result_test_idx" ON public."Golden_Analysis_Test_Result" USING btree (test_id, test_version, created_at DESC)` |

## Golden_Analysis_Test_Run

One complete regression-suite execution with immutable release/model/prompt/tool/Feature version context.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `run_id` | `uuid` | No | `gen_random_uuid()` | No column description has been recorded. |
| `release_version` | `text` | No | — | No column description has been recorded. |
| `model_provider` | `text` | No | — | No column description has been recorded. |
| `model_id` | `text` | No | — | No column description has been recorded. |
| `reasoning_effort` | `text` | Yes | — | No column description has been recorded. |
| `orchestrator_version` | `text` | No | — | No column description has been recorded. |
| `orchestrator_prompt_version` | `text` | No | — | No column description has been recorded. |
| `version_snapshot` | `jsonb` | No | — | No column description has been recorded. |
| `status` | `text` | No | `'PENDING'::text` | No column description has been recorded. |
| `tests_total` | `integer` | No | `0` | No column description has been recorded. |
| `tests_passed` | `integer` | No | `0` | No column description has been recorded. |
| `tests_failed` | `integer` | No | `0` | No column description has been recorded. |
| `cumulative_input_tokens` | `integer` | No | `0` | No column description has been recorded. |
| `cumulative_output_tokens` | `integer` | No | `0` | No column description has been recorded. |
| `cumulative_total_tokens` | `integer` | No | `0` | No column description has been recorded. |
| `started_at` | `timestamp with time zone` | Yes | — | No column description has been recorded. |
| `completed_at` | `timestamp with time zone` | Yes | — | No column description has been recorded. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `Golden_Analysis_Test_Run_counts_check` | Check | `CHECK (tests_total >= 0 AND tests_passed >= 0 AND tests_failed >= 0 AND (tests_passed + tests_failed) <= tests_total AND cumulative_input_tokens >= 0 AND cumulative_output_tokens >= 0 AND cumulative_total_tokens >= 0)` |
| `Golden_Analysis_Test_Run_snapshot_check` | Check | `CHECK (jsonb_typeof(version_snapshot) = 'object'::text)` |
| `Golden_Analysis_Test_Run_status_check` | Check | `CHECK (status = ANY (ARRAY['PENDING'::text, 'RUNNING'::text, 'PASS'::text, 'FAIL'::text, 'ERROR'::text]))` |
| `Golden_Analysis_Test_Run_times_check` | Check | `CHECK (completed_at IS NULL OR started_at IS NULL OR completed_at >= started_at)` |
| `Golden_Analysis_Test_Run_pkey` | Primary key | `PRIMARY KEY (run_id)` |

### Indexes

| Name | Definition |
|---|---|
| `Golden_Analysis_Test_Run_pkey` | `CREATE UNIQUE INDEX "Golden_Analysis_Test_Run_pkey" ON public."Golden_Analysis_Test_Run" USING btree (run_id)` |
| `Golden_Analysis_Test_Run_status_created_idx` | `CREATE INDEX "Golden_Analysis_Test_Run_status_created_idx" ON public."Golden_Analysis_Test_Run" USING btree (status, created_at DESC)` |

## IDX_Broker_Profile

Reference list of IDX broker codes, names, and domestic/foreign classification.

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

## IDX_Broker_Profile_History

Point-in-time history of IDX_Broker_Profile (name, broker_type, broker_classification), captured from the first capture onward: one row per broker version and knowledge version (bitemporal); superseded knowledge is kept.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `history_id` | `bigint` | No | — | No column description has been recorded. |
| `broker_code` | `text` | No | — | No column description has been recorded. |
| `broker_name` | `text` | Yes | — | No column description has been recorded. |
| `broker_type` | `text` | Yes | — | No column description has been recorded. |
| `broker_classification` | `text` | Yes | — | No column description has been recorded. |
| `valid_from` | `date` | No | — | No column description has been recorded. |
| `valid_to` | `date` | Yes | — | No column description has been recorded. |
| `valid_basis` | `text` | No | — | No column description has been recorded. |
| `available_at` | `timestamp with time zone` | No | — | No column description has been recorded. |
| `available_basis` | `text` | No | — | No column description has been recorded. |
| `recorded_from` | `timestamp with time zone` | No | — | No column description has been recorded. |
| `recorded_to` | `timestamp with time zone` | Yes | — | No column description has been recorded. |
| `superseded_reason` | `text` | Yes | — | No column description has been recorded. |
| `pit_valid_from` | `date` | Yes | — | No column description has been recorded. |
| `pit_valid_to` | `date` | Yes | — | No column description has been recorded. |
| `capture_id` | `bigint` | No | — | No column description has been recorded. |
| `source_provenance` | `jsonb` | No | — | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `IDX_Broker_Profile_History_available_basis_check` | Check | `CHECK (available_basis = ANY (ARRAY['RECORDED'::text, 'DOCUMENTED_PUBLICATION'::text]))` |
| `IDX_Broker_Profile_History_available_check` | Check | `CHECK (available_at <= recorded_from)` |
| `IDX_Broker_Profile_History_key_check` | Check | `CHECK (btrim(broker_code) <> ''::text)` |
| `IDX_Broker_Profile_History_provenance_check` | Check | `CHECK (jsonb_typeof(source_provenance) = 'object'::text)` |
| `IDX_Broker_Profile_History_recorded_check` | Check | `CHECK (recorded_to IS NULL OR recorded_to >= recorded_from)` |
| `IDX_Broker_Profile_History_superseded_check` | Check | `CHECK (recorded_to IS NULL AND superseded_reason IS NULL OR recorded_to IS NOT NULL AND (superseded_reason = ANY (ARRAY['CHANGE_CAPTURED'::text, 'SAME_DAY_REVISION'::text, 'CORRECTION'::text])))` |
| `IDX_Broker_Profile_History_valid_basis_check` | Check | `CHECK (valid_basis = ANY (ARRAY['FIRST_CAPTURE'::text, 'CHANGE_CAPTURED'::text, 'DOCUMENTED'::text]))` |
| `IDX_Broker_Profile_History_valid_check` | Check | `CHECK (valid_to IS NULL OR valid_to > valid_from)` |
| `IDX_Broker_Profile_History_capture_fkey` | Foreign key | `FOREIGN KEY (capture_id) REFERENCES "Reference_History_Capture_Log"(capture_id)` |
| `IDX_Broker_Profile_History_pkey` | Primary key | `PRIMARY KEY (history_id)` |

### Indexes

| Name | Definition |
|---|---|
| `IDX_Broker_Profile_History_no_overlap` | `CREATE INDEX "IDX_Broker_Profile_History_no_overlap" ON public."IDX_Broker_Profile_History" USING gist (broker_code, daterange(valid_from, valid_to, '[)'::text), tstzrange(recorded_from, recorded_to, '[)'::text))` |
| `IDX_Broker_Profile_History_pkey` | `CREATE UNIQUE INDEX "IDX_Broker_Profile_History_pkey" ON public."IDX_Broker_Profile_History" USING btree (history_id)` |

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
| `price_feed_daily` | `numeric` | Yes | — | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `IDX_Stock_Universe_pkey` | Primary key | `PRIMARY KEY ("Ticker")` |

### Indexes

| Name | Definition |
|---|---|
| `IDX_Stock_Universe_pkey` | `CREATE UNIQUE INDEX "IDX_Stock_Universe_pkey" ON public."IDX_Stock_Universe" USING btree ("Ticker")` |

## IDX_Stock_Universe_History

Point-in-time history of the tracked IDX_Stock_Universe attributes, captured from the first capture onward: one row per ticker version and knowledge version (bitemporal); superseded knowledge is kept.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `history_id` | `bigint` | No | — | No column description has been recorded. |
| `Ticker` | `text` | No | — | No column description has been recorded. |
| `Company Name` | `text` | Yes | — | No column description has been recorded. |
| `Exchange` | `text` | Yes | — | No column description has been recorded. |
| `Security Type` | `text` | Yes | — | No column description has been recorded. |
| `Type Specs` | `text` | Yes | — | No column description has been recorded. |
| `Is Common Stock` | `text` | Yes | — | No column description has been recorded. |
| `ISIN` | `text` | Yes | — | No column description has been recorded. |
| `Sector` | `text` | Yes | — | No column description has been recorded. |
| `Industry` | `text` | Yes | — | No column description has been recorded. |
| `valid_from` | `date` | No | — | No column description has been recorded. |
| `valid_to` | `date` | Yes | — | No column description has been recorded. |
| `valid_basis` | `text` | No | — | No column description has been recorded. |
| `available_at` | `timestamp with time zone` | No | — | No column description has been recorded. |
| `available_basis` | `text` | No | — | No column description has been recorded. |
| `recorded_from` | `timestamp with time zone` | No | — | No column description has been recorded. |
| `recorded_to` | `timestamp with time zone` | Yes | — | No column description has been recorded. |
| `superseded_reason` | `text` | Yes | — | No column description has been recorded. |
| `pit_valid_from` | `date` | Yes | — | No column description has been recorded. |
| `pit_valid_to` | `date` | Yes | — | No column description has been recorded. |
| `capture_id` | `bigint` | No | — | No column description has been recorded. |
| `source_provenance` | `jsonb` | No | — | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `IDX_Stock_Universe_History_available_basis_check` | Check | `CHECK (available_basis = ANY (ARRAY['RECORDED'::text, 'DOCUMENTED_PUBLICATION'::text]))` |
| `IDX_Stock_Universe_History_available_check` | Check | `CHECK (available_at <= recorded_from)` |
| `IDX_Stock_Universe_History_key_check` | Check | `CHECK (btrim("Ticker") <> ''::text)` |
| `IDX_Stock_Universe_History_provenance_check` | Check | `CHECK (jsonb_typeof(source_provenance) = 'object'::text)` |
| `IDX_Stock_Universe_History_recorded_check` | Check | `CHECK (recorded_to IS NULL OR recorded_to >= recorded_from)` |
| `IDX_Stock_Universe_History_superseded_check` | Check | `CHECK (recorded_to IS NULL AND superseded_reason IS NULL OR recorded_to IS NOT NULL AND (superseded_reason = ANY (ARRAY['CHANGE_CAPTURED'::text, 'SAME_DAY_REVISION'::text, 'CORRECTION'::text])))` |
| `IDX_Stock_Universe_History_valid_basis_check` | Check | `CHECK (valid_basis = ANY (ARRAY['FIRST_CAPTURE'::text, 'CHANGE_CAPTURED'::text, 'DOCUMENTED'::text]))` |
| `IDX_Stock_Universe_History_valid_check` | Check | `CHECK (valid_to IS NULL OR valid_to > valid_from)` |
| `IDX_Stock_Universe_History_capture_fkey` | Foreign key | `FOREIGN KEY (capture_id) REFERENCES "Reference_History_Capture_Log"(capture_id)` |
| `IDX_Stock_Universe_History_pkey` | Primary key | `PRIMARY KEY (history_id)` |

### Indexes

| Name | Definition |
|---|---|
| `IDX_Stock_Universe_History_no_overlap` | `CREATE INDEX "IDX_Stock_Universe_History_no_overlap" ON public."IDX_Stock_Universe_History" USING gist ("Ticker", daterange(valid_from, valid_to, '[)'::text), tstzrange(recorded_from, recorded_to, '[)'::text))` |
| `IDX_Stock_Universe_History_pkey` | `CREATE UNIQUE INDEX "IDX_Stock_Universe_History_pkey" ON public."IDX_Stock_Universe_History" USING btree (history_id)` |

## Monitoring_Feature04

Feature04 batch/retry run summary and price-notification ordering gate.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `execution_id` | `text` | No | — | No column description has been recorded. |
| `source_execution_id` | `text` | Yes | — | No column description has been recorded. |
| `run_type` | `text` | No | — | No column description has been recorded. |
| `trigger_source` | `text` | No | — | No column description has been recorded. |
| `update_for_date` | `date` | Yes | — | No column description has been recorded. |
| `price_notification_required` | `boolean` | No | `true` | No column description has been recorded. |
| `price_notification_sent_at` | `timestamp with time zone` | Yes | — | No column description has been recorded. |
| `eligible_tickers` | `integer` | No | `0` | No column description has been recorded. |
| `completed_tickers` | `integer` | No | `0` | No column description has been recorded. |
| `failed_tickers` | `integer` | No | `0` | No column description has been recorded. |
| `blocked_tickers` | `integer` | No | `0` | No column description has been recorded. |
| `status` | `text` | No | `'OPEN'::text` | No column description has been recorded. |
| `started_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | No column description has been recorded. |
| `sealed_at` | `timestamp with time zone` | Yes | — | No column description has been recorded. |
| `finished_at` | `timestamp with time zone` | Yes | — | No column description has been recorded. |
| `last_error` | `text` | Yes | — | No column description has been recorded. |
| `updated_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | No column description has been recorded. |
| `source_monitor_table` | `text` | No | `'Monitoring_Price_ALL'::text` | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `Monitoring_Feature04_check` | Check | `CHECK (eligible_tickers >= 0 AND completed_tickers >= 0 AND failed_tickers >= 0 AND blocked_tickers >= 0)` |
| `Monitoring_Feature04_execution_id_check` | Check | `CHECK (btrim(execution_id) <> ''::text)` |
| `Monitoring_Feature04_run_type_check` | Check | `CHECK (run_type = ANY (ARRAY['DAILY'::text, 'RECOVERY'::text, 'RETRY_TICKER'::text, 'RETRY_COLUMN'::text, 'ADHOC'::text, 'RECONCILIATION'::text]))` |
| `Monitoring_Feature04_source_monitor_table_check` | Check | `CHECK (source_monitor_table = ANY (ARRAY['Monitoring_Price_ALL'::text, 'Monitoring_Fixed_Income'::text]))` |
| `Monitoring_Feature04_status_check` | Check | `CHECK (status = ANY (ARRAY['OPEN'::text, 'READY'::text, 'PROCESSING'::text, 'SUCCESS'::text, 'PARTIAL'::text, 'NEEDS_REVIEW'::text, 'FAILED'::text, 'SKIPPED'::text]))` |
| `Monitoring_Feature04_trigger_source_check` | Check | `CHECK (trigger_source = ANY (ARRAY['SCHEDULED'::text, 'MANUAL'::text, 'TELEGRAM'::text, 'DATABASE'::text, 'RECONCILIATION'::text]))` |
| `Monitoring_Feature04_pkey` | Primary key | `PRIMARY KEY (execution_id)` |

### Indexes

| Name | Definition |
|---|---|
| `Monitoring_Feature04_pkey` | `CREATE UNIQUE INDEX "Monitoring_Feature04_pkey" ON public."Monitoring_Feature04" USING btree (execution_id)` |
| `Monitoring_Feature04_status_idx` | `CREATE INDEX "Monitoring_Feature04_status_idx" ON public."Monitoring_Feature04" USING btree (status, updated_at)` |

## Monitoring_Feature04_Ticker

Per-ticker membership and terminal result for one Feature04 run.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `execution_id` | `text` | No | — | No column description has been recorded. |
| `ticker` | `text` | No | — | No column description has been recorded. |
| `timeframe` | `text` | No | `'Daily'::text` | No column description has been recorded. |
| `required_generation` | `bigint` | No | — | No column description has been recorded. |
| `requested_columns` | `ARRAY` | Yes | — | No column description has been recorded. |
| `status` | `text` | No | `'PENDING'::text` | No column description has been recorded. |
| `completed_generation` | `bigint` | Yes | — | No column description has been recorded. |
| `retry_request_id` | `uuid` | Yes | — | No column description has been recorded. |
| `last_error_code` | `text` | Yes | — | No column description has been recorded. |
| `last_error` | `text` | Yes | — | No column description has been recorded. |
| `started_at` | `timestamp with time zone` | Yes | — | No column description has been recorded. |
| `finished_at` | `timestamp with time zone` | Yes | — | No column description has been recorded. |
| `updated_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | No column description has been recorded. |
| `asset_type` | `text` | No | — | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `Monitoring_Feature04_Ticker_asset_type_check` | Check | `CHECK (asset_type = ANY (ARRAY['equity'::text, 'bonds'::text]))` |
| `Monitoring_Feature04_Ticker_required_generation_check` | Check | `CHECK (required_generation >= 0)` |
| `Monitoring_Feature04_Ticker_status_check` | Check | `CHECK (status = ANY (ARRAY['PENDING'::text, 'PROCESSING'::text, 'SUCCESS'::text, 'FAILED'::text, 'BLOCKED'::text, 'SUPERSEDED'::text]))` |
| `Monitoring_Feature04_Ticker_timeframe_check` | Check | `CHECK (timeframe = 'Daily'::text)` |
| `Monitoring_Feature04_Ticker_execution_id_fkey` | Foreign key | `FOREIGN KEY (execution_id) REFERENCES "Monitoring_Feature04"(execution_id) ON DELETE CASCADE` |
| `Monitoring_Feature04_Ticker_retry_fkey` | Foreign key | `FOREIGN KEY (retry_request_id) REFERENCES "Feature04_Retry_Request"(request_id)` |
| `Monitoring_Feature04_Ticker_pkey` | Primary key | `PRIMARY KEY (execution_id, asset_type, ticker, timeframe)` |

### Indexes

| Name | Definition |
|---|---|
| `Monitoring_Feature04_Ticker_pending_idx` | `CREATE INDEX "Monitoring_Feature04_Ticker_pending_idx" ON public."Monitoring_Feature04_Ticker" USING btree (asset_type, ticker, timeframe, required_generation) WHERE (status = ANY (ARRAY['PENDING'::text, 'PROCESSING'::text]))` |
| `Monitoring_Feature04_Ticker_pkey` | `CREATE UNIQUE INDEX "Monitoring_Feature04_Ticker_pkey" ON public."Monitoring_Feature04_Ticker" USING btree (execution_id, asset_type, ticker, timeframe)` |

## Monitoring_Fixed_Income

Operational result for one independent fixed-income daily or recovery cron execution.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `execution_id` | `uuid` | No | — | No column description has been recorded. |
| `run_type` | `text` | No | — | No column description has been recorded. |
| `trigger_source` | `text` | No | — | No column description has been recorded. |
| `target_date` | `date` | No | — | No column description has been recorded. |
| `timeframe` | `text` | No | — | No column description has been recorded. |
| `started_at` | `timestamp with time zone` | No | — | No column description has been recorded. |
| `finished_at` | `timestamp with time zone` | No | — | No column description has been recorded. |
| `expected_series` | `integer` | No | — | No column description has been recorded. |
| `queried_series` | `integer` | No | — | No column description has been recorded. |
| `updated_series` | `integer` | No | — | No column description has been recorded. |
| `missing_series` | `integer` | No | — | No column description has been recorded. |
| `missing_series_list` | `jsonb` | No | — | No column description has been recorded. |
| `status` | `text` | No | — | No column description has been recorded. |
| `last_error` | `text` | Yes | — | No column description has been recorded. |
| `service_name` | `text` | Yes | — | No column description has been recorded. |
| `created_at` | `timestamp with time zone` | No | `statement_timestamp()` | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `Monitoring_Fixed_Income_pkey` | Primary key | `PRIMARY KEY (execution_id)` |

### Indexes

| Name | Definition |
|---|---|
| `Monitoring_Fixed_Income_pkey` | `CREATE UNIQUE INDEX "Monitoring_Fixed_Income_pkey" ON public."Monitoring_Fixed_Income" USING btree (execution_id)` |
| `monitoring_fixed_income_target_idx` | `CREATE INDEX monitoring_fixed_income_target_idx ON public."Monitoring_Fixed_Income" USING btree (target_date, run_type, started_at DESC)` |

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

## Price_Fixed_Income

TradingView fixed-income OHLC observations separated by metric_type and Timeframe; Feature04 consumes price/1D only.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `Country` | `text` | No | — | No column description has been recorded. |
| `instrument_name` | `text` | No | — | No column description has been recorded. |
| `ticker` | `character varying` | No | — | No column description has been recorded. |
| `tradingview_symbol` | `character varying` | No | — | No column description has been recorded. |
| `date` | `date` | No | — | No column description has been recorded. |
| `open` | `numeric` | No | — | No column description has been recorded. |
| `high` | `numeric` | No | — | No column description has been recorded. |
| `low` | `numeric` | No | — | No column description has been recorded. |
| `close` | `numeric` | No | — | No column description has been recorded. |
| `volume` | `numeric` | Yes | — | No column description has been recorded. |
| `source` | `character varying` | No | — | No column description has been recorded. |
| `query_date` | `date` | No | — | No column description has been recorded. |
| `ingestion_time` | `timestamp with time zone` | No | — | No column description has been recorded. |
| `metric_type` | `character varying` | No | — | No column description has been recorded. |
| `value_unit` | `character varying` | No | — | No column description has been recorded. |
| `Timeframe` | `character varying` | No | — | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `Price_Fixed_Income_metric_type_check` | Check | `CHECK (metric_type::text = ANY (ARRAY['price'::character varying, 'yield_to_maturity'::character varying]::text[]))` |
| `Price_Fixed_Income_pkey` | Primary key | `PRIMARY KEY (tradingview_symbol, date, metric_type, "Timeframe")` |

### Indexes

| Name | Definition |
|---|---|
| `Price_Fixed_Income_date_idx` | `CREATE INDEX "Price_Fixed_Income_date_idx" ON public."Price_Fixed_Income" USING btree (date)` |
| `Price_Fixed_Income_pkey` | `CREATE UNIQUE INDEX "Price_Fixed_Income_pkey" ON public."Price_Fixed_Income" USING btree (tradingview_symbol, date, metric_type, "Timeframe")` |
| `Price_Fixed_Income_ticker_metric_idx` | `CREATE INDEX "Price_Fixed_Income_ticker_metric_idx" ON public."Price_Fixed_Income" USING btree (ticker, metric_type)` |

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

## Reference_History_Capture_Log

One row per capture of a reference table into its history (trigger, initial, manual or correction): counts of changed and new versions, keys absent from the load, and the error of a failed capture.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `capture_id` | `bigint` | No | — | No column description has been recorded. |
| `source_table` | `text` | No | — | No column description has been recorded. |
| `trigger_operation` | `text` | No | — | No column description has been recorded. |
| `captured_at` | `timestamp with time zone` | No | `now()` | No column description has been recorded. |
| `status` | `text` | No | — | No column description has been recorded. |
| `source_rows` | `integer` | Yes | — | No column description has been recorded. |
| `versions_changed` | `integer` | Yes | — | No column description has been recorded. |
| `versions_opened` | `integer` | Yes | — | No column description has been recorded. |
| `absent_entities` | `integer` | Yes | — | No column description has been recorded. |
| `absent_examples` | `ARRAY` | No | `'{}'::text[]` | No column description has been recorded. |
| `error` | `text` | Yes | — | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `Reference_History_Capture_Log_operation_check` | Check | `CHECK (trigger_operation = ANY (ARRAY['INSERT'::text, 'UPDATE'::text, 'DELETE'::text, 'TRUNCATE'::text, 'INITIAL'::text, 'MANUAL'::text, 'CORRECTION'::text]))` |
| `Reference_History_Capture_Log_source_check` | Check | `CHECK (source_table = ANY (ARRAY['IDX_Stock_Universe'::text, 'IDX_Broker_Profile'::text]))` |
| `Reference_History_Capture_Log_status_check` | Check | `CHECK ((status = ANY (ARRAY['CAPTURED'::text, 'NO_CHANGE'::text])) AND error IS NULL OR status = 'FAILED'::text AND error IS NOT NULL)` |
| `Reference_History_Capture_Log_pkey` | Primary key | `PRIMARY KEY (capture_id)` |

### Indexes

| Name | Definition |
|---|---|
| `Reference_History_Capture_Log_pkey` | `CREATE UNIQUE INDEX "Reference_History_Capture_Log_pkey" ON public."Reference_History_Capture_Log" USING btree (capture_id)` |

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
| `readiness_mode` | `text` | No | `'NOT_APPLICABLE'::text` | DATA_DATE uses a registered date column; REFERENCE_STATE reports state without reducing the common analysis date; NOT_APPLICABLE has no readiness contribution. |
| `readiness_date_column` | `text` | Yes | — | Exact physical date column used for live readiness when readiness_mode is DATA_DATE. |
| `observation_date_column` | `text` | Yes | — | Exact physical column representing the market or source observation date. |
| `data_available_at_column` | `text` | Yes | — | Exact physical timestamp column representing proven decision-time availability; NULL when unavailable or not applicable. |
| `availability_rule` | `text` | No | `'Not applicable.'::text` | Conservative rule for when observations may be used by historical decisions. |
| `point_in_time_status` | `text` | No | `'NOT_APPLICABLE'::text` | AVAILABLE, PARTIAL, UNAVAILABLE, or NOT_APPLICABLE status for historical universe and metadata. |
| `historical_metadata_method` | `text` | Yes | — | Method used to select historical universe/classification metadata, including explicit current-state fallback. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `Table_Catalog_availability_rule_check` | Check | `CHECK (btrim(availability_rule) <> ''::text)` |
| `Table_Catalog_definition_check` | Check | `CHECK (definition IS NULL AND documentation_status = 'NEEDS_REVIEW'::text OR definition IS NOT NULL AND btrim(definition) <> ''::text)` |
| `Table_Catalog_documentation_status_check` | Check | `CHECK (documentation_status = ANY (ARRAY['VERIFIED'::text, 'PARTIAL'::text, 'NEEDS_REVIEW'::text]))` |
| `Table_Catalog_name_check` | Check | `CHECK (btrim(table_name) <> ''::text)` |
| `Table_Catalog_point_in_time_status_check` | Check | `CHECK (point_in_time_status = ANY (ARRAY['AVAILABLE'::text, 'PARTIAL'::text, 'UNAVAILABLE'::text, 'NOT_APPLICABLE'::text]))` |
| `Table_Catalog_readiness_column_check` | Check | `CHECK (readiness_mode = 'DATA_DATE'::text AND readiness_date_column IS NOT NULL AND btrim(readiness_date_column) <> ''::text OR readiness_mode <> 'DATA_DATE'::text AND readiness_date_column IS NULL)` |
| `Table_Catalog_readiness_mode_check` | Check | `CHECK (readiness_mode = ANY (ARRAY['DATA_DATE'::text, 'REFERENCE_STATE'::text, 'NOT_APPLICABLE'::text]))` |
| `Table_Catalog_target_schema_check` | Check | `CHECK (table_schema = 'public'::text)` |
| `Table_Catalog_timestamps_check` | Check | `CHECK (updated_at >= created_at)` |
| `Table_Catalog_pkey` | Primary key | `PRIMARY KEY (table_schema, table_name)` |

### Indexes

| Name | Definition |
|---|---|
| `Table_Catalog_pkey` | `CREATE UNIQUE INDEX "Table_Catalog_pkey" ON public."Table_Catalog" USING btree (table_schema, table_name)` |

## Telegram_Command_Log

Inbound Telegram command audit and duplicate-prevention ledger for telegram-trigger.

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
| `feature04_request_id` | `uuid` | Yes | — | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `Telegram_Command_Log_command_not_blank` | Check | `CHECK (btrim(command) <> ''::text)` |
| `Telegram_Command_Log_status_check` | Check | `CHECK (status = ANY (ARRAY['RECEIVED'::text, 'TRIGGERED'::text, 'BLOCKED'::text, 'FAILED'::text]))` |
| `Telegram_Command_Log_target_not_blank` | Check | `CHECK (btrim(target_service) <> ''::text)` |
| `Telegram_Command_Log_feature04_request_fkey` | Foreign key | `FOREIGN KEY (feature04_request_id) REFERENCES "Feature04_Retry_Request"(request_id)` |
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

Delivery ledger used by telegram-monitor to prevent duplicate notifications.

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

## Tool_Catalog

Versioned tool registry and advertised operational ceilings. Backend and worker configuration remain the enforcement authority.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `tool_name` | `text` | No | — | No column description has been recorded. |
| `tool_family` | `text` | No | — | No column description has been recorded. |
| `tool_type` | `text` | No | — | No column description has been recorded. |
| `purpose` | `text` | No | — | No column description has been recorded. |
| `input_schema` | `jsonb` | No | — | No column description has been recorded. |
| `output_schema` | `jsonb` | No | — | No column description has been recorded. |
| `execution_type` | `text` | No | — | No column description has been recorded. |
| `handler_name` | `text` | Yes | — | No column description has been recorded. |
| `default_output_rows` | `integer` | Yes | — | No column description has been recorded. |
| `max_output_rows` | `integer` | Yes | — | Backend result ceiling; this is independent of the smaller LLM-facing result limits. |
| `max_input_rows` | `integer` | Yes | — | No column description has been recorded. |
| `max_tickers` | `integer` | Yes | — | No column description has been recorded. |
| `max_date_range_days` | `integer` | Yes | — | No column description has been recorded. |
| `max_estimated_rows` | `bigint` | Yes | — | No column description has been recorded. |
| `timeout_seconds` | `integer` | Yes | — | No column description has been recorded. |
| `max_output_bytes` | `bigint` | Yes | — | No column description has been recorded. |
| `max_llm_result_rows` | `integer` | Yes | — | No column description has been recorded. |
| `max_llm_result_bytes` | `bigint` | Yes | — | No column description has been recorded. |
| `max_llm_result_tokens` | `integer` | Yes | — | Maximum compact tool-result tokens exposed to the model for one call. |
| `requires_analytics_worker` | `boolean` | No | `false` | No column description has been recorded. |
| `requires_feature_catalog` | `boolean` | No | `true` | No column description has been recorded. |
| `requires_data_readiness` | `boolean` | No | `true` | No column description has been recorded. |
| `tool_specific_limits` | `jsonb` | No | `'{}'::jsonb` | No column description has been recorded. |
| `version` | `text` | No | `'v1'::text` | No column description has been recorded. |
| `is_active` | `boolean` | No | `false` | No column description has been recorded. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | No column description has been recorded. |
| `updated_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `Tool_Catalog_execution_check` | Check | `CHECK (execution_type = ANY (ARRAY['BACKEND'::text, 'ANALYTICS_WORKER'::text, 'QUERY_SANDBOX'::text, 'STATISTICAL_WORKER'::text, 'ORCHESTRATOR'::text]))` |
| `Tool_Catalog_family_check` | Check | `CHECK (tool_family = ANY (ARRAY['META'::text, 'DISCOVERY'::text, 'QUALITY'::text, 'QUERY'::text, 'SCREENING'::text, 'HISTORICAL_VALIDATION'::text, 'ADVANCED'::text, 'AUDIT'::text]))` |
| `Tool_Catalog_positive_limits_check` | Check | `CHECK ((default_output_rows IS NULL OR default_output_rows > 0) AND (max_output_rows IS NULL OR max_output_rows > 0) AND (max_input_rows IS NULL OR max_input_rows > 0) AND (max_tickers IS NULL OR max_tickers > 0) AND (max_date_range_days IS NULL OR max_date_range_days > 0) AND (max_estimated_rows IS NULL OR max_estimated_rows > 0) AND (timeout_seconds IS NULL OR timeout_seconds > 0) AND (max_output_bytes IS NULL OR max_output_bytes > 0) AND (max_llm_result_rows IS NULL OR max_llm_result_rows > 0) AND (max_llm_result_bytes IS NULL OR max_llm_result_bytes > 0) AND (max_llm_result_tokens IS NULL OR max_llm_result_tokens > 0))` |
| `Tool_Catalog_pkey` | Primary key | `PRIMARY KEY (tool_name, version)` |

### Indexes

| Name | Definition |
|---|---|
| `Tool_Catalog_one_active_version_idx` | `CREATE UNIQUE INDEX "Tool_Catalog_one_active_version_idx" ON public."Tool_Catalog" USING btree (tool_name) WHERE is_active` |
| `Tool_Catalog_pkey` | `CREATE UNIQUE INDEX "Tool_Catalog_pkey" ON public."Tool_Catalog" USING btree (tool_name, version)` |

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

## Universe_Fixed_income

Approved fixed-income instruments and their TradingView price/yield series classification.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `region` | `text` | No | — | No column description has been recorded. |
| `country` | `text` | No | — | No column description has been recorded. |
| `instrument_name` | `text` | No | — | No column description has been recorded. |
| `ticker` | `text` | No | — | No column description has been recorded. |
| `exchange` | `text` | No | — | No column description has been recorded. |
| `security_type` | `text` | No | — | No column description has been recorded. |
| `type_specs` | `text` | No | — | No column description has been recorded. |
| `is_common_stock` | `boolean` | No | — | No column description has been recorded. |
| `tradingview_country` | `text` | No | — | No column description has been recorded. |
| `metric_type` | `text` | No | — | No column description has been recorded. |
| `tenor` | `text` | No | — | No column description has been recorded. |
| `updated_at` | `timestamp with time zone` | No | `statement_timestamp()` | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `Universe_Fixed_income_metric_type_check` | Check | `CHECK (metric_type = ANY (ARRAY['price'::text, 'yield_to_maturity'::text]))` |
| `Universe_Fixed_income_pkey` | Primary key | `PRIMARY KEY (ticker, metric_type)` |

### Indexes

| Name | Definition |
|---|---|
| `Universe_Fixed_income_pkey` | `CREATE UNIQUE INDEX "Universe_Fixed_income_pkey" ON public."Universe_Fixed_income" USING btree (ticker, metric_type)` |

## feature04_backfill_log

Atomic per-run/ticker Feature04 historical load metadata and resume fingerprints; no copied price or feature rows. Source hash is an extraction fingerprint, not point-in-time availability.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `run_id` | `uuid` | No | — | Caller-supplied UUID identifying an authorized resumable load run. |
| `ticker` | `text` | No | — | Actual source ticker processed in this atomic transaction. |
| `source_start` | `date` | Yes | — | Earliest observation in this ticker source snapshot. |
| `source_end` | `date` | Yes | — | Latest observation in this ticker source snapshot. |
| `source_rows` | `integer` | Yes | — | Number of source observations processed for this ticker. |
| `source_sha256` | `text` | Yes | — | SHA256 of canonical source serialization, including known source metadata. |
| `output_sha256` | `text` | Yes | — | SHA256 of all stored feature payloads, excluding calculated_at. |
| `calculation_version` | `text` | No | — | Version of the engine that produced the stored payload. |
| `status` | `text` | No | — | COMPLETED means verified target and log committed atomically; FAILED means no partial ticker write was committed. |
| `changed_rows` | `integer` | Yes | — | Inserted or materially changed rows in this ticker UPSERT. |
| `started_at` | `timestamp with time zone` | No | — | UTC time this ticker attempt began. |
| `finished_at` | `timestamp with time zone` | No | — | UTC time verification finished, before atomic commit. |
| `detail` | `text` | Yes | — | Bounded execution or failure explanation without credentials. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `feature04_backfill_log_changed_rows_check` | Check | `CHECK (changed_rows >= 0)` |
| `feature04_backfill_log_check` | Check | `CHECK (source_start IS NULL OR source_end >= source_start)` |
| `feature04_backfill_log_check1` | Check | `CHECK (finished_at >= started_at)` |
| `feature04_backfill_log_check2` | Check | `CHECK (status <> 'COMPLETED'::text OR source_start IS NOT NULL AND source_end IS NOT NULL AND source_rows > 0 AND source_sha256 IS NOT NULL AND output_sha256 IS NOT NULL AND changed_rows IS NOT NULL)` |
| `feature04_backfill_log_output_sha256_check` | Check | `CHECK (output_sha256 ~ '^[0-9a-f]{64}$'::text)` |
| `feature04_backfill_log_source_rows_check` | Check | `CHECK (source_rows >= 0)` |
| `feature04_backfill_log_source_sha256_check` | Check | `CHECK (source_sha256 ~ '^[0-9a-f]{64}$'::text)` |
| `feature04_backfill_log_status_check` | Check | `CHECK (status = ANY (ARRAY['COMPLETED'::text, 'FAILED'::text]))` |
| `feature04_backfill_log_ticker_check` | Check | `CHECK (ticker = upper(btrim(ticker)) AND ticker <> ''::text)` |
| `feature04_backfill_log_pkey` | Primary key | `PRIMARY KEY (run_id, ticker)` |

### Indexes

| Name | Definition |
|---|---|
| `feature04_backfill_log_pkey` | `CREATE UNIQUE INDEX feature04_backfill_log_pkey ON public.feature04_backfill_log USING btree (run_id, ticker)` |

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
