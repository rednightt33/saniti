# Database schema

Generated from PostgreSQL schema `public` at `2026-09-24T07:26:13+00:00`.

`Latest Data Date` is the newest business date represented in a table. `Last Changed At` is the latest tracked database change or completed load. `Last Checked At` is only the time this catalog inspected the table.

## Tables

| Table Name | Category | Update Pattern | Latest Data Date | Last Changed At | Tracking | Definition |
|---|---|---|---|---|---|---|
| `AI_calculation_catalog` | Unclassified | Unknown | — | `2026-09-22 16:55:06+00:00` | Baseline only | AI-facing calculation contracts derived from active, validated Feature definitions. |
| `AI_catalog_relationships` | Unclassified | Unknown | — | `2026-09-22 16:55:06+00:00` | Baseline only | AI-facing safe join, temporal alignment, preaggregation, and output-grain contracts. |
| `AI_column_catalog` | Unclassified | Unknown | — | `2026-09-22 16:55:06+00:00` | Baseline only | AI-facing column semantics and bounded-query permissions for the seven approved tables. |
| `AI_data_coverage` | Unclassified | Unknown | — | `2026-09-22 16:55:06+00:00` | Baseline only | Automated actual raw-source coverage plus explicitly inferred expectations for derived Feature tables. |
| `AI_research_catalog` | Unclassified | Unknown | — | `2026-09-24 07:24:52+00:00` | Baseline only | Global reference catalog of research methods for the orchestrator; entries do not enable sandbox execution. |
| `AI_table_catalog` | Unclassified | Unknown | — | `2026-09-22 16:55:06+00:00` | Baseline only | AI-facing master list and bounded-access contract for seven approved source and Feature tables. |
| `Analysis_Evidence` | System | When compact evidence is recorded for an analysis | — | `2026-09-13 15:02:15+00:00` | Baseline only | Compact reproducible evidence supporting material AI analysis claims. |
| `Analysis_Model_Call` | System | One row after every provider model response; retained reasoning is purged by policy | — | `2026-09-14 03:49:36+00:00` | Baseline only | Per-provider-call audit containing usage, progressive tool exposure, a concise decision summary, and temporarily retained provider-returned reasoning. |
| `Analysis_Request` | System | One lifecycle per submitted AI analysis | — | `2026-09-13 15:02:15+00:00` | Baseline only | Durable AI analysis request lifecycle, structured result, progressive tool exposure state, and token usage. |
| `Analysis_Step_Log` | System | After each AI analysis tool or compaction step | — | `2026-09-13 15:02:15+00:00` | Baseline only | Audit record for every query, tool, compaction, or analytical step in an AI request. |
| `Analytics_Dataset_Snapshot` | System | Per bounded analytics input; remove private object after terminal grace or expiry | — | `2026-09-14 07:39:52+00:00` | Baseline only | Metadata and retention state for immutable bounded raw or Feature analytical input snapshots stored in a private Railway bucket. |
| `Analytics_Job` | System | Per generic analytics submission, lease, result, or failure | — | `2026-09-14 07:39:52+00:00` | Baseline only | Durable queue, lease, resource contract, result, and failure audit for separately authenticated query-sandbox and statistical-validation workers. |
| `Column_Catalog` | Reference | After approved column metadata changes | — | `2026-09-24 07:14:54.914847+00:00` | Tracked automatically | Physical column inventory and evidence-graded semantic definitions for tables registered in Table_Catalog. |
| `Database_Table_Status` | System | Automatic / daily documentation refresh | — | `2026-09-24 07:26:13+00:00` | System-managed | Tracks the data freshness, change time, and update pattern of each table. |
| `Feature_01_Stock_Daily` | Feature | After validated daily-price changes | `2026-09-23` | `2026-09-23 10:05:13.286404+00:00` | Derived from Price_Stock_Indonesia_IDX | Daily per-ticker price, return, volatility, volume, and drawdown features. |
| `Feature_02_Broker_Rolling` | Feature | After validated broker-summary changes; manual v2 ticker rebuild | `2026-08-31` | `2026-09-14 14:26:33.580099+00:00` | Derived from IDX_Broker_Summary; Investor-Type Feature 02 v2 refresh is manual | Validated daily and rolling broker flows by source ticker, broker, Investor Type, Market Board and transaction date. Investor Type is exact source investor identity; broker_classification remains current profile metadata. |
| `Feature_03_Stock_Broker_Daily` | Feature | After Feature 02 refresh; manual Investor-Type v2 refresh | `2026-08-31` | `2026-09-14 15:17:23.131992+00:00` | Derived from Investor-Type Feature_02_Broker_Rolling; Feature 03 v2 refresh is manual | Validated stock-level daily broker breadth, source-Investor-Type flows, current broker-profile classified flows, dominant brokers and net-flow concentration; Market Boards remain separate. |
| `Feature_Calculation_Log` | System | After completed worker attempts | `2026-09-23` | `2026-09-23 10:05:13.295145+00:00` | Derived from attempt log rows | Completed attempt and retry history for Feature 01 calculation work. |
| `Feature_Calculation_Queue` | System | After committed price inserts/updates and worker transitions | `2026-09-23` | `2026-09-23 10:05:13.242779+00:00` | Derived from queue rows | Durable pending and completed Feature 01 calculation work per changed source candle. |
| `Feature_Catalog` | Reference | After each validated Feature schema change | — | `2026-09-14 15:17:06.460831+00:00` | Tracked automatically | Versioned, machine-readable formula, interpretation, recommended-use, misuse, availability, point-in-time safety and validation-evidence contract for every validated Feature column. |
| `Feature_Relationship_Catalog` | Reference | After a validated Feature join contract changes | — | `2026-09-13 15:02:15+00:00` | Baseline only | Versioned safe-join and grain contracts between verified Feature tables. |
| `Feature_Status` | System | After enqueue and worker state transitions | `2026-09-23` | `2026-09-23 10:05:13.242779+00:00` | Derived from per-ticker status rows | Current Feature 01 calculation freshness and outstanding-work summary per ticker. |
| `Golden_Analysis_Test` | System | After a versioned golden analytical expectation changes | — | `2026-09-13 15:08:56+00:00` | Baseline only | Versioned analytical regression-test definitions with reproducible conditions and tolerances. |
| `Golden_Analysis_Test_Result` | System | After each test in a golden-suite run | — | `2026-09-13 15:08:56+00:00` | Baseline only | Per-test correctness, methodology, evidence, warning, latency and token outcome. |
| `Golden_Analysis_Test_Run` | System | Before major releases and material model, prompt, Feature, or tool changes | — | `2026-09-13 15:08:56+00:00` | Baseline only | Historical execution record for one complete golden analytical regression suite. |
| `IDX_Broker_Profile` | Reference | Periodic / approximately annual | — | `2026-09-10 07:23:34.854803+00:00` | Tracked automatically | Broker code and name, domestic/foreign type, and usage profile such as Institutional-heavy, Retail-heavy, Mixed, or Niche. |
| `IDX_Broker_Summary` | Transactional | Continuous / each loaded trading day | `2026-08-31` | `2026-09-09 14:41:15.160142+00:00` | Derived from table data and load log | Daily broker buy/sell values and lots by symbol, broker, investor type, and market board. |
| `IDX_Stock_Universe` | Reference | Periodic / when the listed universe changes | — | `2026-09-12 13:34:43.352522+00:00` | Tracked automatically | Current Indonesian listed-security universe, ticker identity, and classifications. |
| `Monitoring_Price_ALL` | System | Twice daily alongside IDX price automation | `2026-09-23` | `2026-09-23 23:01:25.390125+00:00` | Derived from monitoring rows | Per-execution grouped outcomes and completeness of DAILY and RECOVERY price runs. |
| `Price_Stock_Indonesia_IDX` | Transactional | Periodic / when daily IDX prices are refreshed | `2026-09-23` | `2026-09-23 10:03:22.949645+00:00` | Latest date derived; future changes tracked automatically | Daily Indonesian stock OHLCV candles sourced from TradingView. |
| `Table_Catalog` | Reference | After approved table metadata changes | — | `2026-09-24 07:14:54.904752+00:00` | Tracked automatically | Curated meanings, grain, provenance, and update contracts for approved public data tables; not a freshness monitor. |
| `Telegram_Command_Log` | System | Event-driven / when an authorized Telegram command is received | — | `2026-09-11 14:19:34.821458+00:00` | Tracked automatically | Inbound Telegram command audit and duplicate-prevention ledger. |
| `Telegram_Notification_Log` | System | Event-driven / after a monitored job completes | — | `2026-09-23 23:01:30.221581+00:00` | Tracked automatically | Outbound Telegram delivery state and anti-duplicate ledger. |
| `Tool_Catalog` | Reference | With each approved backend or analytics tool release | — | `2026-09-13 15:02:15+00:00` | Baseline only | Versioned generic AI tool metadata, activation state, schemas, and advertised operational ceilings. |
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

## AI_calculation_catalog

AI-facing calculation contracts derived from active, validated Feature definitions.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `calculation_name` | `text` | No | — | Governed calculation_name field of AI_calculation_catalog; see the creating migration for its exact contract. |
| `version` | `text` | No | — | Governed version field of AI_calculation_catalog; see the creating migration for its exact contract. |
| `target_table` | `text` | No | — | Governed target_table field of AI_calculation_catalog; see the creating migration for its exact contract. |
| `target_columns` | `ARRAY` | No | — | Governed target_columns field of AI_calculation_catalog; see the creating migration for its exact contract. |
| `definition` | `text` | No | — | Governed definition field of AI_calculation_catalog; see the creating migration for its exact contract. |
| `required_inputs` | `jsonb` | No | — | Governed required_inputs field of AI_calculation_catalog; see the creating migration for its exact contract. |
| `parameters` | `jsonb` | No | `'{}'::jsonb` | Governed parameters field of AI_calculation_catalog; see the creating migration for its exact contract. |
| `defaults` | `jsonb` | No | `'{}'::jsonb` | Governed defaults field of AI_calculation_catalog; see the creating migration for its exact contract. |
| `implementation_ref` | `ARRAY` | No | — | Governed implementation_ref field of AI_calculation_catalog; see the creating migration for its exact contract. |
| `alignment_rules` | `text` | No | — | Governed alignment_rules field of AI_calculation_catalog; see the creating migration for its exact contract. |
| `missing_data_policy` | `text` | No | — | Governed missing_data_policy field of AI_calculation_catalog; see the creating migration for its exact contract. |
| `output_definition` | `jsonb` | No | — | Governed output_definition field of AI_calculation_catalog; see the creating migration for its exact contract. |
| `validation_evidence` | `ARRAY` | No | — | Governed validation_evidence field of AI_calculation_catalog; see the creating migration for its exact contract. |
| `status` | `text` | No | `'ACTIVE'::text` | Governed status field of AI_calculation_catalog; see the creating migration for its exact contract. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Governed created_at field of AI_calculation_catalog; see the creating migration for its exact contract. |
| `updated_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Governed updated_at field of AI_calculation_catalog; see the creating migration for its exact contract. |

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

AI-facing safe join, temporal alignment, preaggregation, and output-grain contracts.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `relationship_id` | `bigint` | No | — | Governed relationship_id field of AI_catalog_relationships; see the creating migration for its exact contract. |
| `left_table` | `text` | No | — | Governed left_table field of AI_catalog_relationships; see the creating migration for its exact contract. |
| `left_columns` | `ARRAY` | No | — | Governed left_columns field of AI_catalog_relationships; see the creating migration for its exact contract. |
| `right_table` | `text` | No | — | Governed right_table field of AI_catalog_relationships; see the creating migration for its exact contract. |
| `right_columns` | `ARRAY` | No | — | Governed right_columns field of AI_catalog_relationships; see the creating migration for its exact contract. |
| `relationship_type` | `text` | No | — | Governed relationship_type field of AI_catalog_relationships; see the creating migration for its exact contract. |
| `temporal_rule` | `text` | No | — | Governed temporal_rule field of AI_catalog_relationships; see the creating migration for its exact contract. |
| `safe_output_grain` | `text` | No | — | Governed safe_output_grain field of AI_catalog_relationships; see the creating migration for its exact contract. |
| `requires_preaggregation` | `boolean` | No | `false` | Governed requires_preaggregation field of AI_catalog_relationships; see the creating migration for its exact contract. |
| `description` | `text` | No | — | Governed description field of AI_catalog_relationships; see the creating migration for its exact contract. |
| `version` | `text` | No | `'v1'::text` | Governed version field of AI_catalog_relationships; see the creating migration for its exact contract. |
| `is_allowed` | `boolean` | No | `true` | Governed is_allowed field of AI_catalog_relationships; see the creating migration for its exact contract. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Governed created_at field of AI_catalog_relationships; see the creating migration for its exact contract. |
| `updated_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Governed updated_at field of AI_catalog_relationships; see the creating migration for its exact contract. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `AI_catalog_relationships_columns_check` | Check | `CHECK (cardinality(left_columns) > 0 AND cardinality(left_columns) = cardinality(right_columns))` |
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

AI-facing column semantics and bounded-query permissions for the seven approved tables.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `table_name` | `text` | No | — | Governed table_name field of AI_column_catalog; see the creating migration for its exact contract. |
| `column_name` | `text` | No | — | Governed column_name field of AI_column_catalog; see the creating migration for its exact contract. |
| `ordinal_position` | `integer` | No | — | Governed ordinal_position field of AI_column_catalog; see the creating migration for its exact contract. |
| `description` | `text` | Yes | — | Governed description field of AI_column_catalog; see the creating migration for its exact contract. |
| `data_type` | `text` | No | — | Governed data_type field of AI_column_catalog; see the creating migration for its exact contract. |
| `semantic_type` | `text` | No | — | Governed semantic_type field of AI_column_catalog; see the creating migration for its exact contract. |
| `unit` | `text` | Yes | — | Governed unit field of AI_column_catalog; see the creating migration for its exact contract. |
| `nullable` | `boolean` | No | — | Governed nullable field of AI_column_catalog; see the creating migration for its exact contract. |
| `is_primary_key` | `boolean` | No | — | Governed is_primary_key field of AI_column_catalog; see the creating migration for its exact contract. |
| `source_column_or_expression` | `text` | Yes | — | Governed source_column_or_expression field of AI_column_catalog; see the creating migration for its exact contract. |
| `is_sensitive` | `boolean` | No | `false` | Governed is_sensitive field of AI_column_catalog; see the creating migration for its exact contract. |
| `ai_allowed` | `boolean` | No | `true` | Governed ai_allowed field of AI_column_catalog; see the creating migration for its exact contract. |
| `allowed_aggregations` | `ARRAY` | No | `'{}'::text[]` | Governed allowed_aggregations field of AI_column_catalog; see the creating migration for its exact contract. |
| `filter_allowed` | `boolean` | No | `true` | Governed filter_allowed field of AI_column_catalog; see the creating migration for its exact contract. |
| `group_by_allowed` | `boolean` | No | `false` | Governed group_by_allowed field of AI_column_catalog; see the creating migration for its exact contract. |
| `example_value` | `text` | Yes | — | Governed example_value field of AI_column_catalog; see the creating migration for its exact contract. |
| `coverage_required` | `boolean` | No | `false` | Governed coverage_required field of AI_column_catalog; see the creating migration for its exact contract. |
| `documentation_status` | `text` | No | — | Governed documentation_status field of AI_column_catalog; see the creating migration for its exact contract. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Governed created_at field of AI_column_catalog; see the creating migration for its exact contract. |
| `updated_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Governed updated_at field of AI_column_catalog; see the creating migration for its exact contract. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `AI_column_catalog_aggregations_check` | Check | `CHECK (allowed_aggregations <@ ARRAY['SUM'::text, 'AVG'::text, 'MEDIAN'::text, 'MIN'::text, 'MAX'::text, 'COUNT'::text, 'COUNT_DISTINCT'::text, 'PERCENTILE'::text, 'WEIGHTED_AVG'::text])` |
| `AI_column_catalog_documentation_check` | Check | `CHECK (documentation_status = ANY (ARRAY['VERIFIED'::text, 'PARTIAL'::text, 'NEEDS_REVIEW'::text]))` |
| `AI_column_catalog_position_check` | Check | `CHECK (ordinal_position > 0)` |
| `AI_column_catalog_semantic_check` | Check | `CHECK (semantic_type = ANY (ARRAY['IDENTIFIER'::text, 'TIME'::text, 'DIMENSION'::text, 'MEASURE'::text]))` |
| `AI_column_catalog_timestamp_check` | Check | `CHECK (updated_at >= created_at)` |
| `AI_column_catalog_table_fkey` | Foreign key | `FOREIGN KEY (table_name) REFERENCES "AI_table_catalog"(table_name) ON DELETE CASCADE` |
| `AI_column_catalog_pkey` | Primary key | `PRIMARY KEY (table_name, column_name)` |

### Indexes

| Name | Definition |
|---|---|
| `AI_column_catalog_pkey` | `CREATE UNIQUE INDEX "AI_column_catalog_pkey" ON public."AI_column_catalog" USING btree (table_name, column_name)` |

## AI_data_coverage

Automated actual raw-source coverage plus explicitly inferred expectations for derived Feature tables.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `coverage_id` | `bigint` | No | — | Governed coverage_id field of AI_data_coverage; see the creating migration for its exact contract. |
| `dataset_name` | `text` | No | — | Governed dataset_name field of AI_data_coverage; see the creating migration for its exact contract. |
| `coverage_scope` | `text` | No | — | Governed coverage_scope field of AI_data_coverage; see the creating migration for its exact contract. |
| `entity_id` | `text` | Yes | — | Governed entity_id field of AI_data_coverage; see the creating migration for its exact contract. |
| `reference_dataset_name` | `text` | Yes | — | Governed reference_dataset_name field of AI_data_coverage; see the creating migration for its exact contract. |
| `coverage_mode` | `text` | No | — | Governed coverage_mode field of AI_data_coverage; see the creating migration for its exact contract. |
| `actual_min_date` | `date` | Yes | — | Governed actual_min_date field of AI_data_coverage; see the creating migration for its exact contract. |
| `actual_max_date` | `date` | Yes | — | Governed actual_max_date field of AI_data_coverage; see the creating migration for its exact contract. |
| `expected_min_date` | `date` | Yes | — | Governed expected_min_date field of AI_data_coverage; see the creating migration for its exact contract. |
| `expected_max_date` | `date` | Yes | — | Governed expected_max_date field of AI_data_coverage; see the creating migration for its exact contract. |
| `source_row_count` | `bigint` | Yes | — | Governed source_row_count field of AI_data_coverage; see the creating migration for its exact contract. |
| `source_key_count` | `bigint` | Yes | — | Governed source_key_count field of AI_data_coverage; see the creating migration for its exact contract. |
| `pipeline_status` | `text` | No | — | Governed pipeline_status field of AI_data_coverage; see the creating migration for its exact contract. |
| `verification_status` | `text` | No | — | Governed verification_status field of AI_data_coverage; see the creating migration for its exact contract. |
| `quality_status` | `text` | No | — | Governed quality_status field of AI_data_coverage; see the creating migration for its exact contract. |
| `check_error` | `text` | Yes | — | Governed check_error field of AI_data_coverage; see the creating migration for its exact contract. |
| `last_checked_at` | `timestamp with time zone` | No | — | Governed last_checked_at field of AI_data_coverage; see the creating migration for its exact contract. |
| `last_full_checked_at` | `timestamp with time zone` | Yes | — | Governed last_full_checked_at field of AI_data_coverage; see the creating migration for its exact contract. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Governed created_at field of AI_data_coverage; see the creating migration for its exact contract. |
| `updated_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Governed updated_at field of AI_data_coverage; see the creating migration for its exact contract. |

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

## AI_research_catalog

Global reference catalog of research methods for the orchestrator; entries do not enable sandbox execution.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `method_id` | `text` | No | — | Stable unique method ID. |
| `method_name` | `text` | No | — | Display name for agent and human review. |
| `category` | `text` | No | — | Broad method family. |
| `purpose` | `text` | No | — | Method objective, not proof of enabled tooling. |
| `example_question` | `text` | No | — | Illustrative natural-language request. |
| `analysis_kind` | `text` | No | — | Evidence type: descriptive, exploratory, conditional_outcome or inference. |
| `input_grain` | `text` | No | — | Observation granularity required by analysis. |
| `required_inputs_json` | `jsonb` | No | — | JSON array of logical input roles, NOT actual Postgres column names. |
| `optional_inputs_json` | `jsonb` | No | — | JSON array of additional logical input roles. |
| `future_outcome_required` | `boolean` | No | — | True if a forward or outcome variable is part of this method. |
| `supports_numeric_directly` | `boolean` | No | — | False if categorical/binary encoding is required. |
| `preprocessing` | `text` | No | — | Preparation, time alignment and signal availability requirements. |
| `parameter_keys_json` | `jsonb` | No | — | JSON array of unresolved analysis parameter names; no silently imposed numeric defaults. |
| `expected_outputs_json` | `jsonb` | No | — | JSON array of expected result field names. |
| `validation_requirements_json` | `jsonb` | No | — | JSON array of method-specific checks; enforcement belongs in code. |
| `main_risks` | `text` | No | — | Likely data, model or interpretation failure modes. |
| `compute_strategy` | `text` | No | — | Execution hint, not a resource guarantee. |
| `tool_or_library_examples` | `text` | No | — | Potential libraries; NOT evidence of installed/registered tools. |
| `implementation_status` | `text` | No | — | REFERENCE_ONLY until developer implements, tests and registers a usable tool. |

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

## AI_table_catalog

AI-facing master list and bounded-access contract for seven approved source and Feature tables.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `table_name` | `text` | No | — | Governed table_name field of AI_table_catalog; see the creating migration for its exact contract. |
| `description` | `text` | No | — | Governed description field of AI_table_catalog; see the creating migration for its exact contract. |
| `category` | `text` | No | — | Governed category field of AI_table_catalog; see the creating migration for its exact contract. |
| `grain` | `text` | No | — | Governed grain field of AI_table_catalog; see the creating migration for its exact contract. |
| `primary_key_columns` | `ARRAY` | No | — | Governed primary_key_columns field of AI_table_catalog; see the creating migration for its exact contract. |
| `time_column` | `text` | Yes | — | Governed time_column field of AI_table_catalog; see the creating migration for its exact contract. |
| `entity_column` | `text` | No | — | Governed entity_column field of AI_table_catalog; see the creating migration for its exact contract. |
| `owner` | `text` | No | `'Saniti'::text` | Governed owner field of AI_table_catalog; see the creating migration for its exact contract. |
| `is_active` | `boolean` | No | `true` | Governed is_active field of AI_table_catalog; see the creating migration for its exact contract. |
| `ai_access_level` | `text` | No | `'BOUNDED_READ'::text` | Governed ai_access_level field of AI_table_catalog; see the creating migration for its exact contract. |
| `freshness_sla` | `interval` | Yes | — | Governed freshness_sla field of AI_table_catalog; see the creating migration for its exact contract. |
| `coverage_enabled` | `boolean` | No | `true` | Governed coverage_enabled field of AI_table_catalog; see the creating migration for its exact contract. |
| `documentation_status` | `text` | No | — | Governed documentation_status field of AI_table_catalog; see the creating migration for its exact contract. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Governed created_at field of AI_table_catalog; see the creating migration for its exact contract. |
| `updated_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Governed updated_at field of AI_table_catalog; see the creating migration for its exact contract. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `AI_table_catalog_access_check` | Check | `CHECK (ai_access_level = ANY (ARRAY['BOUNDED_READ'::text, 'DENIED'::text]))` |
| `AI_table_catalog_category_check` | Check | `CHECK (category = ANY (ARRAY['REFERENCE'::text, 'TRANSACTIONAL'::text, 'FEATURE'::text]))` |
| `AI_table_catalog_documentation_check` | Check | `CHECK (documentation_status = ANY (ARRAY['VERIFIED'::text, 'PARTIAL'::text, 'NEEDS_REVIEW'::text]))` |
| `AI_table_catalog_name_check` | Check | `CHECK (btrim(table_name) <> ''::text)` |
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
| `evidence_id` | `uuid` | No | `gen_random_uuid()` | Physical evidence_id field for Analysis_Evidence. |
| `request_id` | `uuid` | No | — | Physical request_id field for Analysis_Evidence. |
| `step_id` | `bigint` | Yes | — | Physical step_id field for Analysis_Evidence. |
| `evidence_type` | `text` | No | — | Physical evidence_type field for Analysis_Evidence. |
| `claim` | `text` | No | — | Physical claim field for Analysis_Evidence. |
| `compact_payload` | `jsonb` | No | — | Physical compact_payload field for Analysis_Evidence. |
| `query_hash` | `text` | Yes | — | Physical query_hash field for Analysis_Evidence. |
| `source_tables` | `ARRAY` | No | `'{}'::text[]` | Physical source_tables field for Analysis_Evidence. |
| `source_row_count` | `bigint` | Yes | — | Physical source_row_count field for Analysis_Evidence. |
| `analysis_ready_date` | `date` | Yes | — | Physical analysis_ready_date field for Analysis_Evidence. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Physical created_at field for Analysis_Evidence. |

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

Per-provider-call audit containing usage, progressive tool exposure, a concise decision summary, and temporarily retained provider-returned reasoning.

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

Durable AI analysis request lifecycle, structured result, progressive tool exposure state, and token usage.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `request_id` | `uuid` | No | `gen_random_uuid()` | Physical request_id field for Analysis_Request. |
| `user_reference` | `text` | Yes | — | Physical user_reference field for Analysis_Request. |
| `question` | `text` | No | — | Physical question field for Analysis_Request. |
| `status` | `text` | No | `'PENDING'::text` | Physical status field for Analysis_Request. |
| `current_stage` | `text` | No | `'DISCOVERY'::text` | Physical current_stage field for Analysis_Request. |
| `exposed_tool_families` | `ARRAY` | No | `ARRAY['META'::text, 'DISCOVERY'::text, 'QUALITY'::text]` | Physical exposed_tool_families field for Analysis_Request. |
| `model` | `text` | Yes | — | Physical model field for Analysis_Request. |
| `openai_response_id` | `text` | Yes | — | Physical openai_response_id field for Analysis_Request. |
| `analysis_ready_date` | `date` | Yes | — | Physical analysis_ready_date field for Analysis_Request. |
| `features_used` | `ARRAY` | No | `'{}'::text[]` | Physical features_used field for Analysis_Request. |
| `input_tokens` | `integer` | No | `0` | Physical input_tokens field for Analysis_Request. |
| `output_tokens` | `integer` | No | `0` | Physical output_tokens field for Analysis_Request. |
| `total_tokens` | `integer` | No | `0` | Physical total_tokens field for Analysis_Request. |
| `tool_result_tokens` | `integer` | No | `0` | Physical tool_result_tokens field for Analysis_Request. |
| `history_tokens` | `integer` | No | `0` | Physical history_tokens field for Analysis_Request. |
| `feature_metadata_tokens` | `integer` | No | `0` | Physical feature_metadata_tokens field for Analysis_Request. |
| `tool_call_count` | `integer` | No | `0` | Physical tool_call_count field for Analysis_Request. |
| `tool_iteration_count` | `integer` | No | `0` | Physical tool_iteration_count field for Analysis_Request. |
| `context_compaction_count` | `integer` | No | `0` | Physical context_compaction_count field for Analysis_Request. |
| `answer` | `jsonb` | Yes | — | Physical answer field for Analysis_Request. |
| `recommended_next_analysis` | `jsonb` | No | `'[]'::jsonb` | Physical recommended_next_analysis field for Analysis_Request. |
| `error_message` | `text` | Yes | — | Physical error_message field for Analysis_Request. |
| `attempt_count` | `integer` | No | `0` | Physical attempt_count field for Analysis_Request. |
| `lease_owner` | `text` | Yes | — | Physical lease_owner field for Analysis_Request. |
| `lease_expires_at` | `timestamp with time zone` | Yes | — | Physical lease_expires_at field for Analysis_Request. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Physical created_at field for Analysis_Request. |
| `started_at` | `timestamp with time zone` | Yes | — | Physical started_at field for Analysis_Request. |
| `completed_at` | `timestamp with time zone` | Yes | — | Physical completed_at field for Analysis_Request. |
| `updated_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Physical updated_at field for Analysis_Request. |
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

Audit record for every query, tool, compaction, or analytical step in an AI request.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `step_id` | `bigint` | No | — | Physical step_id field for Analysis_Step_Log. |
| `request_id` | `uuid` | No | — | Physical request_id field for Analysis_Step_Log. |
| `step_number` | `integer` | No | — | Physical step_number field for Analysis_Step_Log. |
| `stage` | `text` | No | — | Physical stage field for Analysis_Step_Log. |
| `tool_name` | `text` | Yes | — | Physical tool_name field for Analysis_Step_Log. |
| `sanitized_arguments` | `jsonb` | No | `'{}'::jsonb` | Physical sanitized_arguments field for Analysis_Step_Log. |
| `estimated_rows` | `bigint` | Yes | — | Physical estimated_rows field for Analysis_Step_Log. |
| `processed_rows` | `bigint` | Yes | — | Physical processed_rows field for Analysis_Step_Log. |
| `returned_rows` | `bigint` | Yes | — | Physical returned_rows field for Analysis_Step_Log. |
| `returned_bytes` | `bigint` | Yes | — | Physical returned_bytes field for Analysis_Step_Log. |
| `llm_result_tokens` | `integer` | Yes | — | Physical llm_result_tokens field for Analysis_Step_Log. |
| `duration_ms` | `integer` | Yes | — | Physical duration_ms field for Analysis_Step_Log. |
| `query_hash` | `text` | Yes | — | Physical query_hash field for Analysis_Step_Log. |
| `evidence_references` | `jsonb` | No | `'[]'::jsonb` | Physical evidence_references field for Analysis_Step_Log. |
| `result_summary` | `jsonb` | Yes | — | Physical result_summary field for Analysis_Step_Log. |
| `status` | `text` | No | — | Physical status field for Analysis_Step_Log. |
| `error_message` | `text` | Yes | — | Physical error_message field for Analysis_Step_Log. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Physical created_at field for Analysis_Step_Log. |

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

Metadata and retention state for immutable bounded raw or Feature analytical input snapshots stored in a private Railway bucket.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `snapshot_id` | `uuid` | No | `gen_random_uuid()` | Immutable snapshot metadata identifier. |
| `request_id` | `uuid` | No | — | Analysis request that owns this snapshot or job. |
| `object_key` | `text` | No | — | Private bucket path; never returned to the model. |
| `content_sha256` | `text` | No | — | Checksum of exact compressed input bytes. |
| `format` | `text` | No | — | Serialized snapshot format and compression contract. |
| `row_count` | `integer` | No | — | Total observations across all snapshot datasets. |
| `column_count` | `integer` | No | — | Sum of selected columns across snapshot datasets. |
| `byte_count` | `integer` | No | — | Uncompressed serialized input size in bytes. |
| `compressed_byte_count` | `integer` | No | — | Private object size in bytes. |
| `schema_json` | `jsonb` | No | — | Dataset names and their exact ordered column names. |
| `source_spec_json` | `jsonb` | No | — | Structured catalog-validated Feature query requests used to build the snapshot. |
| `source_tables` | `ARRAY` | No | — | Exact Feature tables contributing observations. |
| `query_hashes` | `ARRAY` | No | — | Reproducible hashes of controlled PostgreSQL reads. |
| `analysis_ready_date` | `date` | Yes | — | Common safe source date supplied for this analysis. |
| `status` | `text` | No | `'AVAILABLE'::text` | Current lifecycle state under the table-specific status constraint. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Row creation time. |
| `expires_at` | `timestamp with time zone` | No | — | Deadline after which the private input object must be removed. |
| `deleted_at` | `timestamp with time zone` | Yes | — | Time the private input object was confirmed deleted. |

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

Durable queue, lease, resource contract, result, and failure audit for separately authenticated query-sandbox and statistical-validation workers.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `job_id` | `uuid` | No | `gen_random_uuid()` | Generic analytics job identifier. |
| `request_id` | `uuid` | No | — | Analysis request that owns this snapshot or job. |
| `snapshot_id` | `uuid` | No | — | Immutable snapshot metadata identifier. |
| `job_label` | `text` | No | — | Stable per-request idempotency label chosen for one analytical hypothesis. |
| `purpose` | `text` | No | — | Human-readable analytical question addressed by the job. |
| `method` | `text` | No | — | Versioned safe execution surface; v1 is SAFE_DUCKDB_SQL. |
| `analysis_spec_json` | `jsonb` | No | — | Bounded worker computation over named snapshot datasets. |
| `status` | `text` | No | `'PENDING'::text` | Current lifecycle state under the table-specific status constraint. |
| `attempt_count` | `smallint` | No | `0` | Number of successful worker lease claims. |
| `max_attempts` | `smallint` | No | `3` | Retry ceiling after expired worker leases. |
| `worker_id` | `text` | Yes | — | Ephemeral identifier of the worker holding the lease. |
| `lease_token` | `uuid` | Yes | — | Random token required to complete or fail the current lease. |
| `lease_expires_at` | `timestamp with time zone` | Yes | — | Expiry of the current worker lease. |
| `max_runtime_seconds` | `integer` | No | — | Per-job worker execution timeout copied from configuration. |
| `max_memory_mb` | `integer` | No | — | Per-job DuckDB memory ceiling copied from configuration. |
| `max_result_rows` | `integer` | No | — | Maximum analytical result rows accepted by the backend. |
| `max_result_bytes` | `integer` | No | — | Maximum serialized analytical result bytes accepted by the backend. |
| `result_json` | `jsonb` | Yes | — | Compact successful result; never the full analytical input. |
| `evidence_id` | `uuid` | Yes | — | Evidence record automatically created for a successful analytical job. |
| `error_class` | `text` | Yes | — | Bounded machine-readable failure category. |
| `error_message` | `text` | Yes | — | Bounded failure explanation without credentials or raw snapshot content. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Row creation time. |
| `started_at` | `timestamp with time zone` | Yes | — | Time of first worker lease. |
| `completed_at` | `timestamp with time zone` | Yes | — | Terminal completion, failure or cancellation time. |
| `result_expires_at` | `timestamp with time zone` | No | — | Retention deadline for compact job result detail. |
| `updated_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Last lifecycle update time. |
| `execution_class` | `text` | No | `'STATISTICAL_VALIDATION'::text` | Physical execution boundary selecting the separately authenticated query sandbox or statistical validation worker. |

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

## Feature_02_Broker_Rolling

Validated daily and rolling broker flows by source ticker, broker, Investor Type, Market Board and transaction date. Investor Type is exact source investor identity; broker_classification remains current profile metadata.

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
| `net_value_1d` | `numeric` | No | — | Buy value minus sell value for this date, ticker, broker, source Investor Type and board. Positive means net buying; negative means net selling. |
| `buy_lots_1d` | `numeric` | No | — | Source Buy Lots for this date, ticker, broker, investor type and board. |
| `sell_lots_1d` | `numeric` | No | — | Source Sell Lots for this date, ticker, broker, investor type and board. |
| `net_lots_1d` | `numeric` | No | — | Buy lots minus sell lots for this date, ticker, broker, source Investor Type and board. Positive means net buying; negative means net selling. |
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

Validated stock-level daily broker breadth, source-Investor-Type flows, current broker-profile classified flows, dominant brokers and net-flow concentration; Market Boards remain separate.

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
| `foreign_net_value` | `numeric` | No | — | Sum of daily net value for source Foreign Investor Type across all brokers. Investor Type identifies the source investor, not broker domicile. |
| `domestic_net_value` | `numeric` | No | — | Sum of daily net value for source Domestic Investor Type across all brokers. Investor Type identifies the source investor, not broker domicile. |
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

Versioned, machine-readable formula, interpretation, recommended-use, misuse, availability, point-in-time safety and validation-evidence contract for every validated Feature column.

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
| `semantic_role` | `text` | No | `'MEASURE'::text` | IDENTITY, DIMENSION, or MEASURE role used by generic query tools. |
| `allowed_aggregations` | `ARRAY` | No | `'{}'::text[]` | Allow-list of generic aggregations valid for this column. |
| `ranking_interpretation` | `text` | No | `'CONTEXTUAL'::text` | Default analytical direction; CONTEXTUAL requires the request to state direction. |
| `is_filterable` | `boolean` | No | `true` | Physical is_filterable field for Feature_Catalog. |
| `is_groupable` | `boolean` | No | `false` | Physical is_groupable field for Feature_Catalog. |
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
| `left_feature_table` | `text` | No | — | Physical left_feature_table field for Feature_Relationship_Catalog. |
| `right_feature_table` | `text` | No | — | Physical right_feature_table field for Feature_Relationship_Catalog. |
| `left_join_columns` | `ARRAY` | No | — | Physical left_join_columns field for Feature_Relationship_Catalog. |
| `right_join_columns` | `ARRAY` | No | — | Physical right_join_columns field for Feature_Relationship_Catalog. |
| `relationship_type` | `text` | No | — | Physical relationship_type field for Feature_Relationship_Catalog. |
| `safe_output_grain` | `text` | No | — | Physical safe_output_grain field for Feature_Relationship_Catalog. |
| `requires_preaggregation` | `boolean` | No | — | Physical requires_preaggregation field for Feature_Relationship_Catalog. |
| `definition` | `text` | No | — | Physical definition field for Feature_Relationship_Catalog. |
| `version` | `text` | No | `'v1'::text` | Physical version field for Feature_Relationship_Catalog. |
| `is_active` | `boolean` | No | `true` | Physical is_active field for Feature_Relationship_Catalog. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Physical created_at field for Feature_Relationship_Catalog. |
| `updated_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Physical updated_at field for Feature_Relationship_Catalog. |

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

## Golden_Analysis_Test

Versioned analytical regression-test definitions with reproducible conditions and tolerances.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `test_id` | `text` | No | — | Versioned golden-test definition field: test_id. |
| `version` | `text` | No | `'v1'::text` | Versioned golden-test definition field: version. |
| `category` | `text` | No | — | Versioned golden-test definition field: category. |
| `question` | `text` | No | — | Versioned golden-test definition field: question. |
| `required_capabilities` | `ARRAY` | No | `'{}'::text[]` | Versioned golden-test definition field: required_capabilities. |
| `fixed_start_date` | `date` | Yes | — | Versioned golden-test definition field: fixed_start_date. |
| `fixed_end_date` | `date` | Yes | — | Versioned golden-test definition field: fixed_end_date. |
| `expected_features` | `ARRAY` | No | `'{}'::text[]` | Versioned golden-test definition field: expected_features. |
| `expected_tools` | `ARRAY` | No | `'{}'::text[]` | Versioned golden-test definition field: expected_tools. |
| `expected_conditions` | `jsonb` | No | `'{}'::jsonb` | Versioned golden-test definition field: expected_conditions. |
| `tolerance` | `jsonb` | No | `'{}'::jsonb` | Versioned golden-test definition field: tolerance. |
| `expected_warnings` | `ARRAY` | No | `'{}'::text[]` | Versioned golden-test definition field: expected_warnings. |
| `expected_status` | `text` | No | — | Versioned golden-test definition field: expected_status. |
| `is_active` | `boolean` | No | `true` | Versioned golden-test definition field: is_active. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Versioned golden-test definition field: created_at. |
| `updated_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Versioned golden-test definition field: updated_at. |

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

Per-test correctness, methodology, evidence, warning, latency and token outcome.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `run_id` | `uuid` | No | — | Per-golden-test result field: run_id. |
| `test_id` | `text` | No | — | Per-golden-test result field: test_id. |
| `test_version` | `text` | No | — | Per-golden-test result field: test_version. |
| `request_id` | `uuid` | Yes | — | Per-golden-test result field: request_id. |
| `status` | `text` | No | — | Per-golden-test result field: status. |
| `observed_metrics` | `jsonb` | No | `'{}'::jsonb` | Per-golden-test result field: observed_metrics. |
| `deviation` | `jsonb` | No | `'{}'::jsonb` | Per-golden-test result field: deviation. |
| `observed_warnings` | `ARRAY` | No | `'{}'::text[]` | Per-golden-test result field: observed_warnings. |
| `evidence_ids` | `ARRAY` | No | `'{}'::uuid[]` | Per-golden-test result field: evidence_ids. |
| `methodology_checks` | `jsonb` | No | `'{}'::jsonb` | Per-golden-test result field: methodology_checks. |
| `input_tokens` | `integer` | No | `0` | Per-golden-test result field: input_tokens. |
| `output_tokens` | `integer` | No | `0` | Per-golden-test result field: output_tokens. |
| `total_tokens` | `integer` | No | `0` | Per-golden-test result field: total_tokens. |
| `duration_ms` | `integer` | Yes | — | Per-golden-test result field: duration_ms. |
| `failure_reason` | `text` | Yes | — | Per-golden-test result field: failure_reason. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Per-golden-test result field: created_at. |

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

Historical execution record for one complete golden analytical regression suite.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `run_id` | `uuid` | No | `gen_random_uuid()` | Golden-suite execution field: run_id. |
| `release_version` | `text` | No | — | Golden-suite execution field: release_version. |
| `model_provider` | `text` | No | — | Golden-suite execution field: model_provider. |
| `model_id` | `text` | No | — | Golden-suite execution field: model_id. |
| `reasoning_effort` | `text` | Yes | — | Golden-suite execution field: reasoning_effort. |
| `orchestrator_version` | `text` | No | — | Golden-suite execution field: orchestrator_version. |
| `orchestrator_prompt_version` | `text` | No | — | Golden-suite execution field: orchestrator_prompt_version. |
| `version_snapshot` | `jsonb` | No | — | Golden-suite execution field: version_snapshot. |
| `status` | `text` | No | `'PENDING'::text` | Golden-suite execution field: status. |
| `tests_total` | `integer` | No | `0` | Golden-suite execution field: tests_total. |
| `tests_passed` | `integer` | No | `0` | Golden-suite execution field: tests_passed. |
| `tests_failed` | `integer` | No | `0` | Golden-suite execution field: tests_failed. |
| `cumulative_input_tokens` | `integer` | No | `0` | Golden-suite execution field: cumulative_input_tokens. |
| `cumulative_output_tokens` | `integer` | No | `0` | Golden-suite execution field: cumulative_output_tokens. |
| `cumulative_total_tokens` | `integer` | No | `0` | Golden-suite execution field: cumulative_total_tokens. |
| `started_at` | `timestamp with time zone` | Yes | — | Golden-suite execution field: started_at. |
| `completed_at` | `timestamp with time zone` | Yes | — | Golden-suite execution field: completed_at. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Golden-suite execution field: created_at. |

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

## Tool_Catalog

Versioned generic AI tool metadata, activation state, schemas, and advertised operational ceilings.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `tool_name` | `text` | No | — | Physical tool_name field for Tool_Catalog. |
| `tool_family` | `text` | No | — | Physical tool_family field for Tool_Catalog. |
| `tool_type` | `text` | No | — | Physical tool_type field for Tool_Catalog. |
| `purpose` | `text` | No | — | Physical purpose field for Tool_Catalog. |
| `input_schema` | `jsonb` | No | — | Physical input_schema field for Tool_Catalog. |
| `output_schema` | `jsonb` | No | — | Physical output_schema field for Tool_Catalog. |
| `execution_type` | `text` | No | — | Physical execution_type field for Tool_Catalog. |
| `handler_name` | `text` | Yes | — | Physical handler_name field for Tool_Catalog. |
| `default_output_rows` | `integer` | Yes | — | Physical default_output_rows field for Tool_Catalog. |
| `max_output_rows` | `integer` | Yes | — | Backend result ceiling; this is independent of the smaller LLM-facing result limits. |
| `max_input_rows` | `integer` | Yes | — | Physical max_input_rows field for Tool_Catalog. |
| `max_tickers` | `integer` | Yes | — | Physical max_tickers field for Tool_Catalog. |
| `max_date_range_days` | `integer` | Yes | — | Physical max_date_range_days field for Tool_Catalog. |
| `max_estimated_rows` | `bigint` | Yes | — | Physical max_estimated_rows field for Tool_Catalog. |
| `timeout_seconds` | `integer` | Yes | — | Physical timeout_seconds field for Tool_Catalog. |
| `max_output_bytes` | `bigint` | Yes | — | Physical max_output_bytes field for Tool_Catalog. |
| `max_llm_result_rows` | `integer` | Yes | — | Physical max_llm_result_rows field for Tool_Catalog. |
| `max_llm_result_bytes` | `bigint` | Yes | — | Physical max_llm_result_bytes field for Tool_Catalog. |
| `max_llm_result_tokens` | `integer` | Yes | — | Maximum compact tool-result tokens exposed to the model for one call. |
| `requires_analytics_worker` | `boolean` | No | `false` | Physical requires_analytics_worker field for Tool_Catalog. |
| `requires_feature_catalog` | `boolean` | No | `true` | Physical requires_feature_catalog field for Tool_Catalog. |
| `requires_data_readiness` | `boolean` | No | `true` | Physical requires_data_readiness field for Tool_Catalog. |
| `tool_specific_limits` | `jsonb` | No | `'{}'::jsonb` | Physical tool_specific_limits field for Tool_Catalog. |
| `version` | `text` | No | `'v1'::text` | Physical version field for Tool_Catalog. |
| `is_active` | `boolean` | No | `false` | Physical is_active field for Tool_Catalog. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Physical created_at field for Tool_Catalog. |
| `updated_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Physical updated_at field for Tool_Catalog. |

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
