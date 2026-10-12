# Database schema

Refreshed from the applied public-schema migration and live readback at `2026-10-12T09:21:56+00:00`.

`Latest Data Date` is the newest business date represented in a table. `Last Changed At` is the latest tracked database change or completed load. `Last Checked At` is only the time this catalog inspected the table.

## Tables

| Table Name | Category | Update Pattern | Latest Data Date | Last Changed At | Tracking | Definition |
|---|---|---|---|---|---|---|
| `AI_calculation_catalog` | Unclassified | Unknown | — | `2026-09-22 16:55:06+00:00` | Baseline only | AI-facing calculation contracts derived from active, validated Feature definitions. |
| `AI_catalog_relationships` | Unclassified | Unknown | — | `2026-09-22 16:55:06+00:00` | Baseline only | AI-facing safe join, temporal alignment, preaggregation, and output-grain contracts. |
| `AI_column_catalog` | Unclassified | Unknown | — | `2026-09-22 16:55:06+00:00` | Baseline only | AI-facing column semantics and bounded-query permissions for the seven approved tables. |
| `AI_conversation` | Unclassified | Unknown | — | `2026-09-27 08:23:59+00:00` | Baseline only | market-ai-orc conversations kept by the server (history_mode SERVER): one row per chat box with its owner, retention and the lease that allows one active run at a time. |
| `AI_conversation_evidence` | Unclassified | Unknown | — | `2026-10-09 05:36:34+00:00` | Baseline only | Claims of market-ai-orc answers recomputed by the backend on a path separate from the model's code (SQL Governor summary or the released base table), with the status, the backend value and at most 200 rows of evidence. |
| `AI_conversation_execution` | Unclassified | Unknown | — | `2026-10-09 05:36:34+00:00` | Baseline only | The code of each sandbox execution of a market-ai-orc conversation, so a result can be traced and reproduced after the sandbox copy expired. |
| `AI_conversation_export` | Unclassified | Unknown | — | `2026-10-09 05:36:34+00:00` | Baseline only | Files exported from a market-ai-orc conversation for the user to download (CSV, XLSX or Parquet, at most 20 MB). |
| `AI_conversation_output` | Unclassified | Unknown | — | `2026-10-09 05:36:34+00:00` | Baseline only | Released outputs of market-ai-orc conversations (tables, JSON, text, charts) with their definition, units, lineage and the last date of the data they were computed from; the content up to 20 MB is here, a larger one in the bucket market-ai-conversation-outputs. |
| `AI_conversation_run_memory` | Unclassified | Unknown | — | `2026-10-09 05:36:34+00:00` | Baseline only | What each run of a market-ai-orc conversation (a turn or a step of a mode 4 turn) leaves for the runs after it: the memo later runs read in their prompt, the full texts it names (message, answer, plan, refusals with the refused drafts, design values with their origin, web facts, catalog details), the values it made citable, the model's own note and its reasoning. |
| `AI_conversation_turn` | Unclassified | Unknown | — | `2026-09-27 08:23:59+00:00` | Baseline only | One message of a market-ai-orc conversation: the user message, the run status and the response returned to the caller. |
| `AI_data_coverage` | Unclassified | Unknown | — | `2026-09-22 16:55:06+00:00` | Baseline only | Automated actual raw-source coverage plus explicitly inferred expectations for derived Feature tables. |
| `AI_formula_reference` | Unclassified | Unknown | — | `2026-09-24 09:22:02+00:00` | Baseline only | Global reference catalog of calculation formulas for the orchestrator; entries document a formula, not a verified or executable implementation. |
| `AI_method_guide` | Unclassified | Unknown | — | `2026-10-09 05:36:34+00:00` | Baseline only | Model-facing menu and manual of the analysis paths (G1-G4) and session helpers: when to use and not, inputs, limits, what the backend checks, results, common errors and tested examples; bound to the code by guides_sha256. |
| `AI_metric_catalog` | Unclassified | Unknown | — | `2026-10-09 05:36:34+00:00` | Baseline only | Official metrics market-ai-orc's query_metric answers in one SQL Governor summary: source table, measure column, rule over time, dimensions, default row filter and meaning. Units and additivity are read from AI_column_catalog. |
| `AI_research_catalog` | Unclassified | Unknown | — | `2026-09-24 07:24:52+00:00` | Baseline only | Global reference catalog of research methods for the orchestrator; entries do not enable sandbox execution. |
| `AI_research_library` | Unclassified | Unknown | — | `2026-10-09 05:36:34+00:00` | Baseline only | Model-facing description of the eight Multi-Angle Research methods (roles, parameters, data requirements, interpretation, misuse warning), generated from the sandbox research library and bound to it by library_sha256. |
| `AI_research_run_audit` | Unclassified | Unknown | — | `2026-09-24 12:33:35+00:00` | Baseline only | Durable audit of market-ai-orc runs: the question, the final answer, its evidence label and gate outcome, and every experiment with its Research Governor decision, validation, evidence decision and fingerprints. |
| `AI_table_catalog` | Unclassified | Unknown | — | `2026-09-22 16:55:06+00:00` | Baseline only | AI-facing master list and bounded-access contract for seven approved source and Feature tables. |
| `Analysis_Evidence` | System | When compact evidence is recorded for an analysis | — | `2026-09-13 15:02:15+00:00` | Baseline only | Compact reproducible evidence supporting material AI analysis claims. |
| `Analysis_Model_Call` | System | One row after every provider model response; retained reasoning is purged by policy | — | `2026-09-14 03:49:36+00:00` | Baseline only | Per-provider-call audit containing usage, progressive tool exposure, a concise decision summary, and temporarily retained provider-returned reasoning. |
| `Analysis_Request` | System | One lifecycle per submitted AI analysis | — | `2026-09-13 15:02:15+00:00` | Baseline only | Durable AI analysis request lifecycle, structured result, progressive tool exposure state, and token usage. |
| `Analysis_Step_Log` | System | After each AI analysis tool or compaction step | — | `2026-09-13 15:02:15+00:00` | Baseline only | Audit record for every query, tool, compaction, or analytical step in an AI request. |
| `Analytics_Dataset_Snapshot` | System | Per bounded analytics input; remove private object after terminal grace or expiry | — | `2026-09-14 07:39:52+00:00` | Baseline only | Metadata and retention state for immutable bounded raw or Feature analytical input snapshots stored in a private Railway bucket. |
| `Analytics_Job` | System | Per generic analytics submission, lease, result, or failure | — | `2026-09-14 07:39:52+00:00` | Baseline only | Durable queue, lease, resource contract, result, and failure audit for separately authenticated query-sandbox and statistical-validation workers. |
| `Column_Catalog` | Reference | After approved column metadata changes | — | `2026-10-12 02:22:41.938133+00:00` | Tracked automatically | Physical column inventory and evidence-graded semantic definitions for tables registered in Table_Catalog. |
| `Database_Table_Status` | System | Automatic / daily documentation refresh | — | `2026-10-12 02:39:08+00:00` | System-managed | Tracks the data freshness, change time, and update pattern of each table. |
| `Equity_Market_Schedule` | Reference | When an equity market close, finality delay or correction window changes | — | `2026-10-12 04:59:16+00:00` | Baseline only | Equity market timezone, closing clock, final-candle delay and correction-session policy. |
| `Feature04_Calculation_Log` | System | After each Feature04 worker attempt | — | `2026-10-11 08:51:27+00:00` | Baseline only | Immutable Feature04 calculation attempt audit. |
| `Feature04_Calculation_State` | System | After Feature04 checkpoint bootstrap or successful suffix calculation | `2026-10-09` | `2026-10-12 05:43:20+00:00` | Derived from final source observations | Recent versioned per-instrument calculation checkpoints for exact bounded Feature04 suffix updates. |
| `Feature04_Calculation_Queue` | System | After relevant price changes and Feature04 worker transitions | — | `2026-10-11 08:51:27+00:00` | Baseline only | Durable coalesced Feature04 work and lease state. |
| `Feature04_Column_Status` | System | After Feature04 validation or failure | — | `2026-10-11 08:51:27+00:00` | Baseline only | Per-ticker per-output Feature04 readiness and failure state. |
| `Feature04_Notification_Outbox` | System | After a Feature04 execution becomes terminal | — | `2026-10-11 08:51:27+00:00` | Baseline only | Durable Feature04 completion-notification work. |
| `Feature04_Retry_Request` | System | When the owner requests an active failure retry or its Telegram acknowledgement is recorded | — | `2026-10-11 08:51:27+00:00` | Baseline only | Audited failure-only Telegram retry request, bounded five-session scope, editable acknowledgement, and child execution. |
| `Feature_01_Stock_Daily` | Feature | After validated daily-price changes | `2026-10-09` | `2026-10-09 10:06:33.150795+00:00` | Derived from Price_Stock_Indonesia_IDX | Daily per-ticker price, return, volatility, volume, and drawdown features. |
| `Feature_02_Broker_Rolling` | Feature | After validated broker-summary changes; manual v2 ticker rebuild | `2026-08-31` | `2026-09-14 14:26:33.580099+00:00` | Derived from IDX_Broker_Summary; Investor-Type Feature 02 v2 refresh is manual | Validated daily and rolling broker flows by source ticker, broker, Investor Type, Market Board and transaction date. Investor Type is exact source investor identity; broker_classification remains current profile metadata. |
| `Feature_03_Stock_Broker_Daily` | Feature | After Feature 02 refresh; manual Investor-Type v2 refresh | `2026-08-31` | `2026-09-14 15:17:23.131992+00:00` | Derived from Investor-Type Feature_02_Broker_Rolling; Feature 03 v2 refresh is manual | Validated stock-level daily broker breadth, source-Investor-Type flows, current broker-profile classified flows, dominant brokers and net-flow concentration; Market Boards remain separate. |
| `Feature_04_Technical_Indicator` | Feature | Event-driven after committed final price changes; exact affected suffix per asset/ticker | `2026-10-09` | `2026-10-12 05:43:20+00:00` | Derived from final price rows; changes queued and tracked per ticker | Cross-asset Daily closing price and causal technical indicators from universe-classified equity or bonds OHLC. |
| `Feature_Calculation_Log` | System | After completed worker attempts | `2026-10-09` | `2026-10-09 10:06:33.159836+00:00` | Derived from attempt log rows | Completed attempt and retry history for Feature 01 calculation work. |
| `Feature_Calculation_Queue` | System | After committed price inserts/updates and worker transitions | `2026-10-09` | `2026-10-09 10:06:33.099491+00:00` | Derived from queue rows | Durable pending and completed Feature 01 calculation work per changed source candle. |
| `Feature_Catalog` | Reference | After each validated Feature schema change | — | `2026-10-12 02:04:32.840328+00:00` | Tracked automatically | Versioned, machine-readable formula, interpretation, recommended-use, misuse, availability, point-in-time safety and validation-evidence contract for every validated Feature column. |
| `Feature_Relationship_Catalog` | Reference | After a validated Feature join contract changes | — | `2026-09-13 15:02:15+00:00` | Baseline only | Versioned safe-join and grain contracts between verified Feature tables. |
| `Feature_Status` | System | After enqueue and worker state transitions | `2026-10-09` | `2026-10-09 10:06:33.099491+00:00` | Derived from per-ticker status rows | Current Feature 01 calculation freshness and outstanding-work summary per ticker. |
| `Fixed_Income_Market_Schedule` | Reference | When a market close or source-label convention changes | — | `2026-10-12 02:33:20+00:00` | Baseline only | Fixed-income market timezone, closing clock, final-candle delay and source-label date mapping. |
| `Golden_Analysis_Test` | System | After a versioned golden analytical expectation changes | — | `2026-09-13 15:08:56+00:00` | Baseline only | Versioned analytical regression-test definitions with reproducible conditions and tolerances. |
| `Golden_Analysis_Test_Result` | System | After each test in a golden-suite run | — | `2026-09-13 15:08:56+00:00` | Baseline only | Per-test correctness, methodology, evidence, warning, latency and token outcome. |
| `Golden_Analysis_Test_Run` | System | Before major releases and material model, prompt, Feature, or tool changes | — | `2026-09-13 15:08:56+00:00` | Baseline only | Historical execution record for one complete golden analytical regression suite. |
| `IDX_Broker_Profile` | Reference | Periodic / approximately annual | — | `2026-09-10 07:23:34.854803+00:00` | Tracked automatically | Broker code and name, domestic/foreign type, and usage profile such as Institutional-heavy, Retail-heavy, Mixed, or Niche. |
| `IDX_Broker_Profile_History` | Reference | Captured after every write to IDX_Broker_Profile; never deleted | — | `2026-10-09 05:36:34+00:00` | Baseline; exact changes tracked from this time forward | Point-in-time (bitemporal) history of the tracked IDX_Broker_Profile attributes (broker_name, broker_type, broker_classification), captured by Saniti from the first capture onward. Current knowledge is recorded_to IS NULL; superseded knowledge is kept. |
| `IDX_Broker_Summary` | Transactional | Continuous / each loaded trading day | `2026-08-31` | `2026-09-09 14:41:15.160142+00:00` | Derived from table data and load log | Daily broker buy/sell values and lots by symbol, broker, investor type, and market board. |
| `IDX_Broker_Summary_Freq` | Unclassified | Unknown | — | `2026-10-12 02:33:20+00:00` | Baseline only | No description has been recorded. |
| `IDX_Net_Foreign_Summary` | Unclassified | Unknown | — | `2026-10-12 02:33:20+00:00` | Baseline only | No description has been recorded. |
| `IDX_Stock_Universe` | Reference | Periodic / when the listed universe changes | — | `2026-10-02 18:07:58.944512+00:00` | Tracked automatically | Current Indonesian listed-security universe, ticker identity, and classifications. |
| `IDX_Stock_Universe_History` | Reference | Captured after every write to IDX_Stock_Universe; never deleted | — | `2026-10-09 05:36:34+00:00` | Baseline; exact changes tracked from this time forward | Point-in-time (bitemporal) history of the tracked IDX_Stock_Universe attributes (Company Name, Exchange, Security Type, Type Specs, Is Common Stock, ISIN, Sector, Industry), captured by Saniti from the first capture onward. Current knowledge is recorded_to IS NULL; superseded knowledge is kept. |
| `Monitoring_Feature04` | Monitoring | Per automatic or Telegram Feature04 execution | — | `2026-10-11 08:51:27+00:00` | Baseline only | Feature04 automatic/retry batch summary and notification ordering gate. |
| `Monitoring_Feature04_Ticker` | Monitoring | Per eligible ticker in a Feature04 execution | — | `2026-10-11 08:51:27+00:00` | Baseline only | Per-ticker membership and outcome of a Feature04 execution. |
| `Monitoring_Fixed_Income` | Monitoring | One row after each fixed-income daily or recovery execution | `2026-10-11` | `2026-10-12 02:30:28.508014+00:00` | Derived from fixed-income cron monitoring rows | One market-specific fixed-income daily or recovery execution summary. |
| `Monitoring_Price_ALL` | System | Twice daily alongside IDX price automation | `2026-10-11` | `2026-10-11 23:00:25.791923+00:00` | Derived from monitoring rows | Per-execution grouped outcomes and completeness of DAILY and RECOVERY price runs. |
| `Price_Fixed_Income` | Transactional | Daily and recovery fixed-income price/yield schedules | `2026-10-09` | `2026-10-12 02:29:42.035219+00:00` | Latest date and write time derived from fixed-income observations | Final daily fixed-income OHLC observations with source-bar and market-close finality evidence. |
| `Price_Stock_Indonesia_IDX` | Transactional | Periodic / when daily IDX prices are refreshed | `2026-10-09` | `2026-10-12 04:59:16+00:00` | Latest date and finality evidence derived | Final daily Indonesian stock OHLCV candles sourced from TradingView. |
| `Reference_History_Capture_Log` | System | One row per reference-history capture or correction | — | `2026-10-09 05:36:34+00:00` | Baseline; exact changes tracked from this time forward | One row per capture of IDX_Stock_Universe or IDX_Broker_Profile into its history (trigger, initial, manual or correction): changed and new versions, keys absent from the load, and the error of a failed capture. |
| `Table_Catalog` | Reference | After approved table metadata changes | — | `2026-10-12 02:22:41.935764+00:00` | Tracked automatically | Curated meanings, grain, provenance, and update contracts for approved public data tables; not a freshness monitor. |
| `Telegram_Command_Log` | System | Event-driven / when an authorized Telegram command is received | — | `2026-09-11 14:19:34.821458+00:00` | Tracked automatically | Inbound Telegram command audit and duplicate-prevention ledger. |
| `Telegram_Notification_Log` | System | Event-driven / after a monitored job completes | — | `2026-10-12 02:32:28.134150+00:00` | Tracked automatically | Outbound Telegram delivery state and anti-duplicate ledger. |
| `Tool_Catalog` | Reference | With each approved backend or analytics tool release | — | `2026-09-13 15:02:15+00:00` | Baseline only | Versioned generic AI tool metadata, activation state, schemas, and advertised operational ceilings. |
| `Universe_Equity_Description` | Reference | Periodic / when equity descriptions change | — | `2026-10-02 18:07:58.949068+00:00` | Tracked automatically | Issuer descriptions and TradingView/curated sector and industry classifications. |
| `Universe_Fixed_income` | Reference | Periodic / when the fixed-income universe changes | — | `2026-10-11 14:01:27.117686+00:00` | Baseline only | Approved fixed-income series with explicit source symbol, unit and market-country membership. |
| `feature04_backfill_log` | Monitoring | Atomic per-run/ticker Feature04 calculation metadata | `2026-10-09` | `2026-10-11 06:25:12.790322+00:00` | Derived from completed atomic ticker loads; manual execution only | Atomic Feature04 per-run/ticker historical calculation audit and resumable extraction/output fingerprints. |
| `idx_broker_summary_freq_2016` | Unclassified | Unknown | — | `2026-10-12 02:33:20+00:00` | Baseline only | No description has been recorded. |
| `idx_broker_summary_freq_2017` | Unclassified | Unknown | — | `2026-10-12 02:33:20+00:00` | Baseline only | No description has been recorded. |
| `idx_broker_summary_freq_2018` | Unclassified | Unknown | — | `2026-10-12 02:33:20+00:00` | Baseline only | No description has been recorded. |
| `idx_broker_summary_freq_2019` | Unclassified | Unknown | — | `2026-10-12 02:33:20+00:00` | Baseline only | No description has been recorded. |
| `idx_broker_summary_freq_2020` | Unclassified | Unknown | — | `2026-10-12 02:33:20+00:00` | Baseline only | No description has been recorded. |
| `idx_broker_summary_freq_2021` | Unclassified | Unknown | — | `2026-10-12 02:33:20+00:00` | Baseline only | No description has been recorded. |
| `idx_broker_summary_freq_2022` | Unclassified | Unknown | — | `2026-10-12 02:33:20+00:00` | Baseline only | No description has been recorded. |
| `idx_broker_summary_freq_2023` | Unclassified | Unknown | — | `2026-10-12 02:33:20+00:00` | Baseline only | No description has been recorded. |
| `idx_broker_summary_freq_2024` | Unclassified | Unknown | — | `2026-10-12 02:33:20+00:00` | Baseline only | No description has been recorded. |
| `idx_broker_summary_freq_2025` | Unclassified | Unknown | — | `2026-10-12 02:33:20+00:00` | Baseline only | No description has been recorded. |
| `idx_broker_summary_freq_2026` | Unclassified | Unknown | — | `2026-10-12 02:33:20+00:00` | Baseline only | No description has been recorded. |
| `idx_broker_summary_freq_2027` | Unclassified | Unknown | — | `2026-10-12 02:33:20+00:00` | Baseline only | No description has been recorded. |
| `idx_net_foreign_summary_2016` | Unclassified | Unknown | — | `2026-10-12 02:33:20+00:00` | Baseline only | No description has been recorded. |
| `idx_net_foreign_summary_2017` | Unclassified | Unknown | — | `2026-10-12 02:33:20+00:00` | Baseline only | No description has been recorded. |
| `idx_net_foreign_summary_2018` | Unclassified | Unknown | — | `2026-10-12 02:33:20+00:00` | Baseline only | No description has been recorded. |
| `idx_net_foreign_summary_2019` | Unclassified | Unknown | — | `2026-10-12 02:33:20+00:00` | Baseline only | No description has been recorded. |
| `idx_net_foreign_summary_2020` | Unclassified | Unknown | — | `2026-10-12 02:33:20+00:00` | Baseline only | No description has been recorded. |
| `idx_net_foreign_summary_2021` | Unclassified | Unknown | — | `2026-10-12 02:33:20+00:00` | Baseline only | No description has been recorded. |
| `idx_net_foreign_summary_2022` | Unclassified | Unknown | — | `2026-10-12 02:33:20+00:00` | Baseline only | No description has been recorded. |
| `idx_net_foreign_summary_2023` | Unclassified | Unknown | — | `2026-10-12 02:33:20+00:00` | Baseline only | No description has been recorded. |
| `idx_net_foreign_summary_2024` | Unclassified | Unknown | — | `2026-10-12 02:33:20+00:00` | Baseline only | No description has been recorded. |
| `idx_net_foreign_summary_2025` | Unclassified | Unknown | — | `2026-10-12 02:33:20+00:00` | Baseline only | No description has been recorded. |
| `idx_net_foreign_summary_2026` | Unclassified | Unknown | — | `2026-10-12 02:33:20+00:00` | Baseline only | No description has been recorded. |
| `idx_net_foreign_summary_2027` | Unclassified | Unknown | — | `2026-10-12 02:33:20+00:00` | Baseline only | No description has been recorded. |
| `idx_stockbit_backfill_status` | Unclassified | Unknown | — | `2026-10-12 02:33:20+00:00` | Baseline only | No description has been recorded. |
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
| `Telegram_Notification_Log.source_execution_id` | Source monitor or Feature04 logical delivery key | Logical delivery identity | Price/manual results use one source execution; scheduled Feature04 uses market/trade date and retry uses its child execution. No database foreign key is enforced. |

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
| `supported_join_semantics` | `ARRAY` | No | `'{}'::text[]` | Join semantics a DataNeedSpec may request for this relationship (CURRENT_STATE, EXACT_DATE, AS_OF, EFFECTIVE_DATED); empty means the DataNeed planner cannot use it. |
| `left_time_column` | `text` | Yes | — | Time column of left_table used by EXACT_DATE and AS_OF joins. |
| `right_time_column` | `text` | Yes | — | Time column of right_table used by EXACT_DATE and AS_OF joins. |
| `effective_from_column` | `text` | Yes | — | Inclusive validity start of a right_table row for EFFECTIVE_DATED joins. |
| `effective_to_column` | `text` | Yes | — | Exclusive validity end of a right_table row for EFFECTIVE_DATED joins; NULL in the data means still valid. |

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
| `resample_aggregation` | `text` | Yes | — | Exact aggregation rule to a coarser frequency (FIRST, LAST, MAX, MIN, SUM); NULL means no established rule, so resampling is never pushed down. |
| `cross_entity_aggregation` | `text` | Yes | — | Rule for aggregating the column across entities of a finer grain (SUM, MIN, MAX); NULL means the column is not additive across entities and is never summed. Used by saniti.preaggregate before a relationship join and, since migration 20261002_002 (G18 phase 1), by a DataNeed request's aggregate: the SQL Governor computes SUM across entities only for a SUM rule (re-derived from its own catalog contract). Read through the Governor catalog contract and shown by get_catalog_details. |
| `value_time_basis` | `text` | No | — | HISTORICAL (the value belongs to its row's date or version) or CURRENT_STATE (today's reference value on every row); a point-in-time DataNeedSpec may not read or filter a CURRENT_STATE column. |
| `description_id` | `text` | Yes | — | The column meaning in Indonesian, translated once from description by the production model; description stays the source text. |
| `description_id_status` | `text` | Yes | — | DRAFT (machine translation, not yet reviewed) or REVIEWED; NULL exactly when description_id is NULL. |

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

market-ai-orc conversations kept by the server (history_mode SERVER): one row per chat box with its owner, retention and the lease that allows one active run at a time.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `conversation_id` | `text` | No | — | Server-generated id of the chat box (conv_ + 32 hex). Not a credential: every lookup also checks owner_key. |
| `owner_key` | `text` | No | — | The owner given by the trusted server-side caller in the X-Saniti-Owner header (default when absent); never taken from the model. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | When the conversation was created. |
| `updated_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Last activity: a turn started or finished. |
| `expires_at` | `timestamp with time zone` | No | — | When the cleanup may delete the conversation and its turns: updated_at plus AI_CONVERSATION_RETENTION_DAYS. |
| `next_turn_index` | `integer` | No | `0` | The turn_index the next message receives. |
| `active_request_id` | `text` | Yes | — | request_id of the running turn; NULL when no turn runs. |
| `lease_generation` | `bigint` | No | `0` | Incremented by every turn start; a turn may finish only with the generation it started with (fencing). |
| `lease_expires_at` | `timestamp with time zone` | Yes | — | When a running turn's lease lapses and another message may take over; NULL when no turn runs. |
| `state` | `jsonb` | No | `'{}'::jsonb` | Structured conversation state kept by the orchestrator (for example the latest Research Plan reference); never model-written text. |

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

Claims of market-ai-orc answers recomputed by the backend on a path separate from the model's code (SQL Governor summary or the released base table), with the status, the backend value and at most 200 rows of evidence.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `evidence_id` | `text` | No | — | Id of the check (evd_ + 24 hex); export_result takes it as a source. |
| `conversation_id` | `text` | No | — | The conversation the claim belongs to. |
| `request_id` | `text` | No | — | The market-ai-orc request that checked the claim. |
| `claim` | `text` | No | — | The claim in words, as the model stated it (at most 300 characters). |
| `value_text` | `text` | No | — | The number as written in the answer (for example 1,25 miliar or 116); compared with the rounding it shows. |
| `kind` | `text` | No | — | WAREHOUSE (recomputed by a SQL Governor summary) or BASE_TABLE (recomputed from a released base table). |
| `recipe` | `jsonb` | No | — | How the backend recomputed the claim: table, filters, measure and period, or the base table, conditions and measure. |
| `status` | `text` | No | — | TERCEK (matches within the rounding shown), TIDAK_COCOK, TIDAK_BISA_DICEK (the recipe was refused) or TIDAK_DICEK_BATAS (over the per-answer limit). |
| `backend_value` | `double precision` | Yes | — | The value the backend computed; NULL when it could not. |
| `difference` | `double precision` | Yes | — | backend_value minus the claimed value; NULL when not compared. |
| `source` | `jsonb` | No | `'{}'::jsonb` | Where the evidence came from: output id and reference, or source table, Governor query id and period. |
| `rows` | `jsonb` | No | `'[]'::jsonb` | At most 200 rows of evidence a user can read (the matching base rows or the summary rows). |
| `rows_matched` | `bigint` | Yes | — | Rows that matched the recipe before the 200-row limit. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | When the claim was checked. |

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

The code of each sandbox execution of a market-ai-orc conversation, so a result can be traced and reproduced after the sandbox copy expired.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `execution_id` | `text` | No | — | The sandbox execution_id (exe_ + 24 hex). |
| `conversation_id` | `text` | No | — | The conversation the execution belongs to. |
| `request_id` | `text` | No | — | The market-ai-orc request that ran the code. |
| `session_id` | `text` | Yes | — | The sandbox session that ran the code. |
| `code` | `text` | No | — | The code that ran (its first 65,536 characters when code_truncated). |
| `code_truncated` | `boolean` | No | `false` | True when the code was longer than 65,536 characters and only its start is stored. |
| `code_sha256` | `text` | No | — | SHA-256 of the whole code, as the sandbox recorded it. |
| `modules` | `jsonb` | Yes | — | Modules the code imported, as the sandbox reported them. |
| `access` | `jsonb` | Yes | — | The data the code read (requests, ranges, carried tables), as the sandbox reported it. |
| `status` | `text` | Yes | — | The execution status the sandbox returned (OK, SCRIPT_ERROR, TIMEOUT, ...). |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | When the execution was stored. |

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

Files exported from a market-ai-orc conversation for the user to download (CSV, XLSX or Parquet, at most 20 MB).

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `export_id` | `text` | No | — | Id of the export (exp_ + 24 hex). |
| `conversation_id` | `text` | No | — | The conversation the export belongs to. |
| `request_id` | `text` | No | — | The market-ai-orc request that created the export. |
| `source_ref` | `text` | No | — | What was exported: an output ref or id, or an evidence reference. |
| `format` | `text` | No | — | CSV, XLSX or PARQUET. |
| `file_name` | `text` | No | — | The download file name. |
| `mime_type` | `text` | No | — | The media type sent with the download. |
| `size_bytes` | `bigint` | No | — | Size of the file in bytes (at most 20 MB). |
| `sha256` | `text` | No | — | SHA-256 of the file. |
| `content` | `bytea` | No | — | The file. |
| `includes` | `jsonb` | No | `'{}'::jsonb` | What the file contains besides the rows (definitions, lineage). |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | When the export was created. |

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

Released outputs of market-ai-orc conversations (tables, JSON, text, charts) with their definition, units, lineage and the last date of the data they were computed from; the content up to 20 MB is here, a larger one in the bucket market-ai-conversation-outputs.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `output_id` | `text` | No | — | The sandbox output_id (out_ + 24 hex); the same id the data record and load_output use. |
| `conversation_id` | `text` | No | — | The conversation the output belongs to. |
| `request_id` | `text` | No | — | The market-ai-orc request that released the output. |
| `session_id` | `text` | Yes | — | The sandbox session that produced the output. |
| `execution_id` | `text` | Yes | — | The sandbox execution that produced the output (see AI_conversation_execution). |
| `name` | `text` | No | — | The output name given in emit_table / emit_json (at most 80 characters). |
| `output_type` | `text` | No | — | The sandbox output type (TABLE, JSON, TEXT, CHART or FILE). |
| `format` | `text` | No | — | The stored file format: PARQUET, CSV, PNG, JSON, TEXT or BIN. |
| `label` | `text` | Yes | — | The evidence label the sandbox gave the output (for example DATA_COVERAGE_VERIFIED). |
| `definition` | `jsonb` | Yes | — | How the output was made: filters, period, entities, thresholds and notes, as declared when it was released. |
| `units` | `jsonb` | Yes | — | Unit of each column that has one (FRACTION, PERCENT or P_VALUE). |
| `lineage` | `jsonb` | Yes | — | Where the output came from: need_id, bundle_id, execution code hash and reference date. |
| `data_as_of` | `date` | Yes | — | The last date of the data the output was computed from (the largest actual end date of its bundle ranges); a recomputation of the conversation uses the same date unless the user asks for newer data. |
| `row_count` | `bigint` | Yes | — | Rows of a table output; NULL for other outputs. |
| `columns` | `jsonb` | Yes | — | Column names of a table output, in order; NULL for other outputs. |
| `byte_count` | `bigint` | No | — | Size of the stored file in bytes. |
| `checksum_sha256` | `text` | No | — | SHA-256 of the stored file; checked when the file is loaded into a new session. |
| `storage` | `text` | No | — | POSTGRES (content holds the file, at most 20 MB) or BUCKET (object_key names it in market-ai-conversation-outputs). |
| `content` | `bytea` | Yes | — | The file when storage is POSTGRES; NULL otherwise. |
| `object_key` | `text` | Yes | — | The bucket key (outputs/<conversation_id>/<output_id>.<ext>) when storage is BUCKET; NULL otherwise. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | When the output was stored. |

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

What each run of a market-ai-orc conversation (a turn or a step of a mode 4 turn) leaves for the runs after it: the memo later runs read in their prompt, the full texts it names (message, answer, plan, refusals with the refused drafts, design values with their origin, web facts, catalog details), the values it made citable, the model's own note and its reasoning.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `run_id` | `text` | No | — | The run's request id: a turn's request_id, or <request_id>-m4a ... for a step of a mode 4 turn. |
| `conversation_id` | `text` | No | — | The conversation the run belongs to. |
| `turn_request_id` | `text` | No | — | The request id of the turn the run belongs to (the run's own id for a turn that is one run). |
| `seq` | `bigint` | No | — | The order runs ended in; later runs read the memos in this order (oldest first). |
| `status` | `text` | No | — | The run's status: COMPLETED, NEEDS_CLARIFICATION, AWAITING_CONFIRMATION, LIMITED or FAILED. |
| `response_type` | `text` | Yes | — | ANSWER, CLARIFICATION, RESEARCH_PLAN_CONFIRMATION or LIMITATION; NULL when the run failed without a response. |
| `error_code` | `text` | Yes | — | The run's error code (for example ANALYSIS_TIMEOUT); NULL without one. |
| `memo` | `text` | No | — | The run's memo as later runs of the conversation read it in their prompt (written by the backend from the run's events plus the model's note); never changed. |
| `content` | `jsonb` | No | — | The full texts the memo names: message, answer (with assumptions, limitations and methodology), plan, refusals with the drafts they refused, design values with their origin, web entries, catalog details, code executions, error. |
| `sources` | `jsonb` | No | `'{}'::jsonb` | The values the run made citable (fact, metric, reference, web, the content of a JSON output) with their evidence label, units and origin; later runs register them again under the same address. |
| `note` | `text` | Yes | — | The note the model wrote for later runs in its final response (memo_note); NULL when it wrote none. |
| `reasoning` | `text` | Yes | — | The run's reasoning text (each model call in order), read only with read_conversation_memory; NULL when the provider returned none. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | When the run ended and its memory was stored. |

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

One message of a market-ai-orc conversation: the user message, the run status and the response returned to the caller.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `request_id` | `text` | No | — | The market-ai-orc request_id of the turn; unique across all conversations. |
| `conversation_id` | `text` | No | — | The conversation the turn belongs to. |
| `turn_index` | `integer` | No | — | Position of the turn in its conversation, from 0. |
| `request_fingerprint` | `text` | No | — | SHA-256 of the request content; a retry with the same request_id must match it. |
| `user_message` | `text` | No | — | The user's message. |
| `status` | `text` | No | — | RUNNING, COMPLETED (a response was returned), FAILED (the run raised no response) or INTERRUPTED (the lease lapsed before the turn finished). |
| `lease_generation` | `bigint` | No | — | The conversation lease generation the turn started with. |
| `run_status` | `text` | Yes | — | The status returned to the caller (COMPLETED, NEEDS_CLARIFICATION, AWAITING_CONFIRMATION, LIMITED, FAILED); NULL while running. |
| `response_type` | `text` | Yes | — | ANSWER, CLARIFICATION, RESEARCH_PLAN_CONFIRMATION or LIMITATION; NULL without a response. |
| `assistant_text` | `text` | Yes | — | The text that later turns see as the assistant message: the answer, or the clarification question for a CLARIFICATION. |
| `response` | `jsonb` | Yes | — | The complete response returned to the caller, so a retry of the same request_id returns it without a new run. |
| `error_code` | `text` | Yes | — | Error code of a failed or interrupted turn; NULL otherwise. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | When the turn started. |
| `completed_at` | `timestamp with time zone` | Yes | — | When the turn finished; NULL while RUNNING. |

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

## AI_formula_reference

Global reference catalog of calculation formulas for the orchestrator; entries document a formula, not a verified or executable implementation.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `calculation_id` | `text` | No | — | Stable unique formula ID. |
| `calculation_name` | `text` | No | — | Display name for agent and human review. |
| `description` | `text` | No | — | What the formula computes. |
| `required_inputs` | `text` | No | — | Semicolon-delimited logical input roles, NOT actual Postgres column names. |
| `formula_method` | `text` | No | — | The documented formula or method text; renamed from source column "formula / method". |
| `parameters` | `text` | No | — | Documented parameter names/defaults as free text; enforcement belongs in code. |
| `output` | `text` | No | — | Name of the documented output value. |
| `implementation` | `text` | No | — | Suggested implementation stack; NOT evidence of installed/registered tooling. |

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

Model-facing menu and manual of the analysis paths (G1-G4) and session helpers: when to use and not, inputs, limits, what the backend checks, results, common errors and tested examples; bound to the code by guides_sha256.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `name` | `text` | No | — | Guide name (free_code, event_study, hypothesis_plan, multi_angle or a session helper's guide). |
| `guides_version` | `integer` | No | — | Version of the method guides content. |
| `kind` | `text` | No | — | PATH (an analysis path G1-G4) or HELPER (a session helper). |
| `g` | `text` | Yes | — | The analysis path G1, G2, G3 or G4; NULL for a helper guide. |
| `guide` | `jsonb` | No | — | JSON object: when to use and not, inputs with defaults, limits, what the backend checks and does not, results, common errors and examples. |
| `guide_sha256` | `text` | No | — | Hash of this guide; the conversation data record keeps it to carry the version a model opened. |
| `guides_sha256` | `text` | No | — | Hash of all guides; market-ai-orc serves them only when it equals the sandbox's and its own. |
| `is_active` | `boolean` | No | `true` | Whether the guide is offered to the model. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Row creation time. |
| `updated_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Last update time. |

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

Official metrics market-ai-orc's query_metric answers in one SQL Governor summary: source table, measure column, rule over time, dimensions, default row filter and meaning. Units and additivity are read from AI_column_catalog.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `metric_id` | `text` | No | — | Stable name of the metric the model passes to query_metric. |
| `metric_version` | `integer` | No | `1` | Version of the metric definition; a change is a new version. |
| `label` | `text` | No | — | Indonesian label shown to users. |
| `description` | `text` | No | — | What the metric measures, in plain words. |
| `source_table` | `text` | No | — | The governed table the metric is computed from. |
| `measure_column` | `text` | No | — | The column the metric summarises. |
| `time_function` | `text` | No | — | How the metric runs over the period: SUM, MIN, MAX, FIRST, LAST or COUNT; checked against the column's catalog rule by the Governor. |
| `entity_column` | `text` | No | — | The column the entities of a question (tickers or symbols) filter. |
| `default_dimensions` | `ARRAY` | No | `ARRAY[]::text[]` | The columns the result is split by when the question names none. |
| `allowed_dimensions` | `ARRAY` | No | `ARRAY[]::text[]` | Every column the result may be split by. |
| `default_scope` | `jsonb` | No | `'{"type": "ALL"}'::jsonb` | A canonical scope tree always applied (ALL: none). |
| `formula` | `text` | No | — | The computation in words. |
| `interpretation` | `text` | No | — | How to read the value. |
| `recommended_use` | `text` | No | — | The questions the metric answers. |
| `misuse_warning` | `text` | No | — | How the metric is misread or misused. |
| `review_status` | `text` | No | `'INFERRED'::text` | INFERRED (proposed), REVIEWED or VERIFIED (confirmed by the user). |
| `source_decision` | `text` | No | — | The user decision the metric comes from. |
| `is_active` | `boolean` | No | `true` | Whether query_metric offers this version. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | When the row was inserted. |

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

## AI_research_library

Model-facing description of the eight Multi-Angle Research methods (roles, parameters, data requirements, interpretation, misuse warning), generated from the sandbox research library and bound to it by library_sha256.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `method_id` | `text` | No | — | Registered method id (research_plan/v2 method_id). |
| `engine_version` | `integer` | No | — | Version of the statistical engines the row describes. |
| `library_version` | `integer` | No | — | Version of the research library content. |
| `method_family` | `text` | No | — | One of the five method families; an agreement between angles needs two families. |
| `question_shape` | `text` | No | — | The question the method answers, in general form. |
| `input_roles` | `jsonb` | No | — | JSON array of input roles (role, type, required, meaning); logical roles, not column names. |
| `required_parameters` | `jsonb` | No | — | JSON array of the parameters an angle of this method must set, with their rules. |
| `optional_parameters` | `jsonb` | No | — | JSON array of the parameters an angle may set, with their rules. |
| `data_requirements` | `jsonb` | No | — | JSON object: entity column, label constancy, outcome kind, minimum entities per date and notes; the feasibility check enforces them. |
| `common_requirements` | `jsonb` | No | — | JSON array of the requirements every method shares (one row per entity and date, declarations, forward returns). |
| `sample_unit` | `text` | No | — | Unit of the effective sample: DATES, ENTITIES or DATES_AUTOCORRELATION_ADJUSTED. |
| `secondary_checks` | `jsonb` | No | — | JSON array of checks that must pass for SUPPORTED (for example monotonicity). |
| `decision_rules_ref` | `text` | No | — | Where the status rules are defined; enforcement is research_engines.decide in code. |
| `interpretation` | `text` | No | — | What the method's estimate means. |
| `misuse_warning` | `text` | No | — | How the result is commonly misread. |
| `example_question` | `text` | No | — | An illustrative question the method answers. |
| `library_sha256` | `text` | No | — | Hash of the whole library; market-ai-orc enables multi-angle research only when it equals the sandbox's and its own. |
| `is_active` | `boolean` | No | `true` | Whether the method is offered to the model. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Row creation time. |
| `updated_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Last update time. |

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

Durable audit of market-ai-orc runs: the question, the final answer, its evidence label and gate outcome, and every experiment with its Research Governor decision, validation, evidence decision and fingerprints.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `request_id` | `text` | No | — | The orchestrator request_id of the run (one research run = one market-ai-orc request). |
| `recorded_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | When the audit row was written. |
| `status` | `text` | No | — | Run status returned to the caller: COMPLETED, NEEDS_CLARIFICATION, AWAITING_CONFIRMATION (a Research Plan awaits the user's approval), LIMITED or FAILED. |
| `response_type` | `text` | Yes | — | ANSWER, CLARIFICATION, RESEARCH_PLAN_CONFIRMATION or LIMITATION; NULL for a failed run. |
| `evidence_label` | `text` | Yes | — | The evidence label of the final answer (FACT ... NOT_VALIDATED); NULL without data numbers. |
| `validation_gate` | `text` | No | — | What the answer gate did: NOT_APPLICABLE, PASSED, ANNOTATED or FORCED_LIMITATION. |
| `error_code` | `text` | Yes | — | Error code of a failed run, else NULL. |
| `question_sha256` | `text` | No | — | SHA-256 of the user's message. |
| `question` | `text` | No | — | The user's message (at most 16000 characters). |
| `answer_sha256` | `text` | Yes | — | SHA-256 of the final answer text; NULL for a failed run. |
| `answer` | `text` | Yes | — | The final answer text (at most 20000 characters); NULL for a failed run. |
| `limitations` | `jsonb` | No | `'[]'::jsonb` | JSON array of the limitation lines returned with the answer. |
| `number_provenance` | `jsonb` | Yes | — | JSON {checked, unsupported} of the answer's numbers, or NULL. |
| `experiments` | `jsonb` | No | `'[]'::jsonb` | JSON array of the run's analysis specs: governor decision, validation, evidence decision, whether the answer relies on it (RETAINED/DISCARDED/FOLLOWED_UP/NOT_RUN), code and dataset fingerprints. |
| `datasets` | `jsonb` | No | `'[]'::jsonb` | JSON array of governed datasets used: dataset_id, checksum, row count, source tables, completeness. |
| `budget` | `jsonb` | No | `'{}'::jsonb` | JSON of the run's budgets as the sandbox counted them (analyses, specs, CPU, research experiments). |
| `model` | `text` | No | — | The OpenRouter model identifier the run used. |
| `tool_call_count` | `integer` | No | — | Tool calls in the run. |
| `total_tokens` | `integer` | No | — | Provider-reported total tokens of the run. |
| `duration_ms` | `integer` | No | — | Run duration in milliseconds. |
| `sandbox_summary_status` | `text` | No | — | State of the sandbox run record when copied: REPORTED, AWAITING_REPORT, ACTIVE, UNAVAILABLE or NOT_USED. |

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
| `data_domain` | `text` | No | — | Catalog-managed subject area of the table (MARKET, MACRO, RATES, FUNDAMENTAL, ...); validated by syntax, resolved from catalog rows, never a code enum. |
| `entity_type` | `text` | No | — | Catalog-managed type of the entity identified by entity_column (STOCK, BROKER, ...). |
| `asset_type` | `text` | Yes | — | Asset type of the entities when they are assets (IDX_EQUITY); NULL for non-asset entities such as brokers or macro series. |
| `supported_frequencies` | `ARRAY` | No | — | Observation frequencies the table supports; {STATIC} exactly when time_column is NULL. |
| `time_semantics` | `text` | Yes | — | Meaning of time_column values (exchange trading date, observation date) or that the table holds current-state reference data. |
| `subject_metadata_status` | `text` | No | `'INFERRED'::text` | Review state of the subject values: INFERRED (seeded by migration 20260925_001), REVIEWED, or VERIFIED after a person confirms them. |
| `row_presence` | `text` | Yes | — | What a missing row of the table means: DENSE (every expected date has a row; an absent row is missing data), ACTIVITY_ONLY (a row exists only when something happened; an absent row on a trading day means none happened) or NOT_APPLICABLE (no time column). |
| `row_presence_status` | `text` | Yes | — | Review state of row_presence: INFERRED (seeded by migration 20261009_002 from time_column and a read-only measurement), REVIEWED or VERIFIED after a person confirms it. |

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

## Equity_Market_Schedule

Equity market timezone, closing clock, final-candle delay and correction-session policy.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `market_code` | `text` | No | — | Canonical equity market code. |
| `exchange` | `text` | No | — | TradingView exchange code for the market. |
| `timezone_name` | `text` | No | — | IANA timezone used to interpret the local session close. |
| `session_close_local` | `time without time zone` | No | — | Local official daily-session close. |
| `finality_delay_minutes` | `integer` | No | — | Delay after close before a daily candle can be accepted as final. |
| `correction_lookback_sessions` | `integer` | No | `5` | Number of recent completed sessions reverified and eligible for normal suffix repair. |
| `enabled` | `boolean` | No | `true` | Whether this market policy is active. |
| `updated_at` | `timestamp with time zone` | No | `statement_timestamp()` | Time of the latest policy write. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `Equity_Market_Schedule_code_check` | Check | `CHECK (market_code = upper(btrim(market_code)) AND market_code <> ''::text)` |
| `Equity_Market_Schedule_exchange_check` | Check | `CHECK (exchange = upper(btrim(exchange)) AND exchange <> ''::text)` |
| `Equity_Market_Schedule_timezone_check` | Check | `CHECK (timezone_name = btrim(timezone_name) AND timezone_name <> ''::text)` |
| `Equity_Market_Schedule_delay_check` | Check | `CHECK (finality_delay_minutes >= 0 AND finality_delay_minutes <= 360)` |
| `Equity_Market_Schedule_correction_window_check` | Check | `CHECK (correction_lookback_sessions >= 1 AND correction_lookback_sessions <= 20)` |
| `Equity_Market_Schedule_pkey` | Primary key | `PRIMARY KEY (market_code)` |
| `Equity_Market_Schedule_exchange_key` | Unique | `UNIQUE (exchange)` |

### Indexes

| Name | Definition |
|---|---|
| `Equity_Market_Schedule_exchange_key` | `CREATE UNIQUE INDEX "Equity_Market_Schedule_exchange_key" ON public."Equity_Market_Schedule" USING btree (exchange)` |
| `Equity_Market_Schedule_pkey` | `CREATE UNIQUE INDEX "Equity_Market_Schedule_pkey" ON public."Equity_Market_Schedule" USING btree (market_code)` |

## Feature04_Calculation_Log

Immutable Feature04 calculation attempt audit.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `id` | `bigint` | No | — | Operational id field for Feature04_Calculation_Log. |
| `ticker` | `text` | No | — | Operational ticker field for Feature04_Calculation_Log. |
| `timeframe` | `text` | No | — | Operational timeframe field for Feature04_Calculation_Log. |
| `source_generation` | `bigint` | No | — | Operational source generation field for Feature04_Calculation_Log. |
| `work_revision` | `bigint` | No | — | Operational work revision field for Feature04_Calculation_Log. |
| `retry_request_id` | `uuid` | Yes | — | Operational retry request id field for Feature04_Calculation_Log. |
| `requested_columns` | `ARRAY` | Yes | — | Operational requested columns field for Feature04_Calculation_Log. |
| `successful_columns` | `ARRAY` | No | `'{}'::text[]` | Operational successful columns field for Feature04_Calculation_Log. |
| `failed_columns` | `ARRAY` | No | `'{}'::text[]` | Operational failed columns field for Feature04_Calculation_Log. |
| `group_outcomes` | `jsonb` | No | `'{}'::jsonb` | Operational group outcomes field for Feature04_Calculation_Log. |
| `result` | `text` | No | — | Operational result field for Feature04_Calculation_Log. |
| `source_start` | `date` | Yes | — | Operational source start field for Feature04_Calculation_Log. |
| `source_end` | `date` | Yes | — | Operational source end field for Feature04_Calculation_Log. |
| `source_rows` | `integer` | Yes | — | Operational source rows field for Feature04_Calculation_Log. |
| `source_sha256` | `text` | Yes | — | Operational source sha256 field for Feature04_Calculation_Log. |
| `changed_rows` | `integer` | Yes | — | Operational changed rows field for Feature04_Calculation_Log. |
| `calculation_version` | `text` | No | — | Operational calculation version field for Feature04_Calculation_Log. |
| `started_at` | `timestamp with time zone` | No | — | Operational started at field for Feature04_Calculation_Log. |
| `finished_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Operational finished at field for Feature04_Calculation_Log. |
| `error_code` | `text` | Yes | — | Operational error code field for Feature04_Calculation_Log. |
| `detail` | `text` | Yes | — | Operational detail field for Feature04_Calculation_Log. |
| `asset_type` | `text` | No | — | Universe-derived asset class: equity from IDX_Stock_Universe; bonds from Universe_Fixed_income. |
| `checkpoint_date` | `date` | Yes | — | Trusted checkpoint immediately before the recalculated suffix. |
| `dirty_from_date` | `date` | Yes | — | Earliest source observation recalculated by this attempt. |

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
| `Feature04_Calculation_Log_incremental_range_check` | Check | `CHECK (checkpoint_date IS NULL OR dirty_from_date IS NULL OR checkpoint_date < dirty_from_date)` |
| `Feature04_Calculation_Log_retry_fkey` | Foreign key | `FOREIGN KEY (retry_request_id) REFERENCES "Feature04_Retry_Request"(request_id)` |
| `Feature04_Calculation_Log_pkey` | Primary key | `PRIMARY KEY (id)` |

### Indexes

| Name | Definition |
|---|---|
| `Feature04_Calculation_Log_pkey` | `CREATE UNIQUE INDEX "Feature04_Calculation_Log_pkey" ON public."Feature04_Calculation_Log" USING btree (id)` |
| `Feature04_Calculation_Log_ticker_time_idx` | `CREATE INDEX "Feature04_Calculation_Log_ticker_time_idx" ON public."Feature04_Calculation_Log" USING btree (asset_type, ticker, started_at DESC)` |

## Feature04_Calculation_State

Recent versioned per-instrument calculation checkpoints for exact bounded Feature04 suffix updates.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `asset_type` | `text` | No | — | Universe-derived asset class: equity or bonds. |
| `ticker` | `text` | No | — | Canonical universe ticker. |
| `timeframe` | `text` | No | `'Daily'::text` | Supported observation interval. |
| `checkpoint_date` | `date` | No | — | Source date represented by the post-row state snapshot. |
| `state_version` | `text` | No | — | Serialization and state-machine compatibility version. |
| `calculation_version` | `text` | No | — | Feature04 formula/library contract version. |
| `source_position` | `integer` | No | — | One-based position of the checkpoint observation in the valid source stream. |
| `source_chain_sha256` | `text` | No | — | Cumulative digest of source observations through the checkpoint. |
| `state_payload` | `jsonb` | No | — | Recursive, rolling, pattern, SMI and swing state after the checkpoint row. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Initial checkpoint creation time. |
| `updated_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Latest replacement time. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `Feature04_Calculation_State_asset_type_check` | Check | `CHECK (asset_type = ANY (ARRAY['equity'::text, 'bonds'::text]))` |
| `Feature04_Calculation_State_ticker_check` | Check | `CHECK (ticker = upper(btrim(ticker)) AND ticker <> ''::text)` |
| `Feature04_Calculation_State_timeframe_check` | Check | `CHECK (timeframe = 'Daily'::text)` |
| `Feature04_Calculation_State_state_version_check` | Check | `CHECK (btrim(state_version) <> ''::text AND btrim(calculation_version) <> ''::text)` |
| `Feature04_Calculation_State_source_position_check` | Check | `CHECK (source_position > 0)` |
| `Feature04_Calculation_State_source_chain_sha256_check` | Check | `CHECK (source_chain_sha256 ~ '^[0-9a-f]{64}$'::text)` |
| `Feature04_Calculation_State_state_payload_check` | Check | `CHECK (state_payload ->> 'last_date'::text = checkpoint_date::text)` |
| `Feature04_Calculation_State_state_payload_check1` | Check | `CHECK (state_payload ->> 'source_chain_sha256'::text = source_chain_sha256)` |
| `Feature04_Calculation_State_pkey` | Primary key | `PRIMARY KEY (asset_type, ticker, timeframe, checkpoint_date)` |

### Indexes

| Name | Definition |
|---|---|
| `Feature04_Calculation_State_latest_idx` | `CREATE INDEX "Feature04_Calculation_State_latest_idx" ON public."Feature04_Calculation_State" USING btree (asset_type, ticker, timeframe, checkpoint_date DESC)` |
| `Feature04_Calculation_State_pkey` | `CREATE UNIQUE INDEX "Feature04_Calculation_State_pkey" ON public."Feature04_Calculation_State" USING btree (asset_type, ticker, timeframe, checkpoint_date)` |

## Feature04_Calculation_Queue

Durable coalesced Feature04 work and lease state.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `ticker` | `text` | No | — | Operational ticker field for Feature04_Calculation_Queue. |
| `timeframe` | `text` | No | `'Daily'::text` | Operational timeframe field for Feature04_Calculation_Queue. |
| `dirty_from_date` | `date` | No | — | Operational dirty from date field for Feature04_Calculation_Queue. |
| `requested_generation` | `bigint` | No | `1` | Operational requested generation field for Feature04_Calculation_Queue. |
| `completed_generation` | `bigint` | No | `0` | Operational completed generation field for Feature04_Calculation_Queue. |
| `work_revision` | `bigint` | No | `1` | Operational work revision field for Feature04_Calculation_Queue. |
| `requested_columns` | `ARRAY` | Yes | — | Operational requested columns field for Feature04_Calculation_Queue. |
| `origin_execution_id` | `text` | Yes | — | Operational origin execution id field for Feature04_Calculation_Queue. |
| `status` | `text` | No | `'PENDING'::text` | Operational status field for Feature04_Calculation_Queue. |
| `attempt_count` | `bigint` | No | `0` | Operational attempt count field for Feature04_Calculation_Queue. |
| `source_attempt_count` | `integer` | No | `0` | Operational source attempt count field for Feature04_Calculation_Queue. |
| `next_attempt_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Operational next attempt at field for Feature04_Calculation_Queue. |
| `claimed_at` | `timestamp with time zone` | Yes | — | Operational claimed at field for Feature04_Calculation_Queue. |
| `claim_token` | `uuid` | Yes | — | Operational claim token field for Feature04_Calculation_Queue. |
| `claim_expires_at` | `timestamp with time zone` | Yes | — | Operational claim expires at field for Feature04_Calculation_Queue. |
| `last_error_code` | `text` | Yes | — | Operational last error code field for Feature04_Calculation_Queue. |
| `last_error` | `text` | Yes | — | Operational last error field for Feature04_Calculation_Queue. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Operational created at field for Feature04_Calculation_Queue. |
| `updated_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Operational updated at field for Feature04_Calculation_Queue. |
| `completed_at` | `timestamp with time zone` | Yes | — | Operational completed at field for Feature04_Calculation_Queue. |
| `asset_type` | `text` | No | — | Universe-derived asset class: equity from IDX_Stock_Universe; bonds from Universe_Fixed_income. |

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

Per-ticker per-output Feature04 readiness and failure state.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `ticker` | `text` | No | — | Operational ticker field for Feature04_Column_Status. |
| `timeframe` | `text` | No | `'Daily'::text` | Operational timeframe field for Feature04_Column_Status. |
| `feature_column` | `text` | No | — | Operational feature column field for Feature04_Column_Status. |
| `requested_generation` | `bigint` | No | `0` | Operational requested generation field for Feature04_Column_Status. |
| `completed_generation` | `bigint` | No | `0` | Operational completed generation field for Feature04_Column_Status. |
| `calculation_version` | `text` | No | — | Operational calculation version field for Feature04_Column_Status. |
| `status` | `text` | No | — | Operational status field for Feature04_Column_Status. |
| `dirty_from_date` | `date` | Yes | — | Operational dirty from date field for Feature04_Column_Status. |
| `validated_through` | `date` | Yes | — | Operational validated through field for Feature04_Column_Status. |
| `latest_value_available` | `boolean` | Yes | — | Operational latest value available field for Feature04_Column_Status. |
| `null_reason` | `text` | Yes | — | Operational null reason field for Feature04_Column_Status. |
| `last_attempt_id` | `bigint` | Yes | — | Operational last attempt id field for Feature04_Column_Status. |
| `last_error_code` | `text` | Yes | — | Operational last error code field for Feature04_Column_Status. |
| `last_error` | `text` | Yes | — | Operational last error field for Feature04_Column_Status. |
| `last_calculated_at` | `timestamp with time zone` | Yes | — | Operational last calculated at field for Feature04_Column_Status. |
| `updated_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Operational updated at field for Feature04_Column_Status. |
| `asset_type` | `text` | No | — | Universe-derived asset class: equity from IDX_Stock_Universe; bonds from Universe_Fixed_income. |

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

Durable Feature04 completion-notification work.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `event_id` | `uuid` | No | — | Operational event id field for Feature04_Notification_Outbox. |
| `execution_id` | `text` | No | — | Operational execution id field for Feature04_Notification_Outbox. |
| `notification_type` | `text` | No | `'COMPLETED'::text` | Operational notification type field for Feature04_Notification_Outbox. |
| `status` | `text` | No | `'PENDING'::text` | Operational status field for Feature04_Notification_Outbox. |
| `attempt_count` | `integer` | No | `0` | Operational attempt count field for Feature04_Notification_Outbox. |
| `next_attempt_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Operational next attempt at field for Feature04_Notification_Outbox. |
| `claimed_at` | `timestamp with time zone` | Yes | — | Operational claimed at field for Feature04_Notification_Outbox. |
| `claim_token` | `uuid` | Yes | — | Operational claim token field for Feature04_Notification_Outbox. |
| `claim_expires_at` | `timestamp with time zone` | Yes | — | Operational claim expires at field for Feature04_Notification_Outbox. |
| `sent_at` | `timestamp with time zone` | Yes | — | Operational sent at field for Feature04_Notification_Outbox. |
| `last_error` | `text` | Yes | — | Operational last error field for Feature04_Notification_Outbox. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Operational created at field for Feature04_Notification_Outbox. |
| `updated_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Operational updated at field for Feature04_Notification_Outbox. |

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

Audited failure-only Telegram retry request with a bounded five-session scope and editable acknowledgement.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `request_id` | `uuid` | No | — | Operational request id field for Feature04_Retry_Request. |
| `telegram_update_id` | `bigint` | Yes | — | Operational telegram update id field for Feature04_Retry_Request. |
| `chat_id` | `bigint` | Yes | — | Operational chat id field for Feature04_Retry_Request. |
| `request_scope` | `text` | No | — | Operational request scope field for Feature04_Retry_Request. |
| `source_execution_id` | `text` | Yes | — | Operational source execution id field for Feature04_Retry_Request. |
| `ticker` | `text` | Yes | — | Operational ticker field for Feature04_Retry_Request. |
| `requested_columns` | `ARRAY` | Yes | — | Operational requested columns field for Feature04_Retry_Request. |
| `source_generation` | `bigint` | No | — | Operational source generation field for Feature04_Retry_Request. |
| `work_revision` | `bigint` | No | — | Operational work revision field for Feature04_Retry_Request. |
| `status` | `text` | No | `'PENDING'::text` | Operational status field for Feature04_Retry_Request. |
| `child_execution_id` | `text` | No | — | Operational child execution id field for Feature04_Retry_Request. |
| `created_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Operational created at field for Feature04_Retry_Request. |
| `started_at` | `timestamp with time zone` | Yes | — | Operational started at field for Feature04_Retry_Request. |
| `finished_at` | `timestamp with time zone` | Yes | — | Operational finished at field for Feature04_Retry_Request. |
| `last_error` | `text` | Yes | — | Operational last error field for Feature04_Retry_Request. |
| `asset_type` | `text` | Yes | — | Universe-derived asset class: equity from IDX_Stock_Universe; bonds from Universe_Fixed_income. |
| `acknowledgement_message_id` | `bigint` | Yes | — | Telegram acknowledgement message edited with the terminal retry result; zero means acknowledgement delivery failed. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `Feature04_Retry_Request_asset_type_check` | Check | `CHECK (asset_type IS NULL OR (asset_type = ANY (ARRAY['equity'::text, 'bonds'::text])))` |
| `Feature04_Retry_Request_ack_message_check` | Check | `CHECK (acknowledgement_message_id IS NULL OR acknowledgement_message_id >= 0)` |
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

## Feature_04_Technical_Indicator

Cross-asset Daily closing price and causal technical indicators from universe-classified equity or bonds OHLC.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `ticker` | `text` | No | — | IDX security code copied from source ticker. |
| `trade_date` | `date` | No | — | Trading observation date copied from source date. |
| `timeframe` | `text` | No | — | Verified daily timeframe copied exactly from source. |
| `sma_20` | `double precision` | Yes | — | Unweighted mean of 20 observed closes. |
| `sma_50` | `double precision` | Yes | — | Unweighted mean of 50 observed closes. |
| `ema_12` | `double precision` | Yes | — | Fast exponentially weighted close; alpha=2/13. |
| `ema_26` | `double precision` | Yes | — | Slow exponentially weighted close; alpha=2/27. |
| `rsi_14` | `double precision` | Yes | — | Wilder gain/loss oscillator on 14 consecutive close changes, scaled 0–100. |
| `macd` | `double precision` | Yes | — | Difference of the stored fast and slow EMA price baselines. |
| `macd_signal` | `double precision` | Yes | — | Nine-period EMA of valid MACD line observations. |
| `macd_histogram` | `double precision` | Yes | — | Difference between MACD line and its nine-period signal. |
| `atr_14` | `double precision` | Yes | — | Wilder average of 14 true ranges using prior observed close. |
| `bb_upper_20` | `double precision` | Yes | — | Upper 20-period Bollinger band, population standard deviation multiplier 2. |
| `bb_middle_20` | `double precision` | Yes | — | Middle 20-period Bollinger band, identical to SMA20. |
| `bb_lower_20` | `double precision` | Yes | — | Lower 20-period Bollinger band, population standard deviation multiplier 2. |
| `cdl_piercing` | `integer` | Yes | — | Native TA-Lib piercing pattern recognition code from historical OHLC. |
| `cdl_morning_star` | `integer` | Yes | — | Native TA-Lib morning star pattern recognition code from historical OHLC. |
| `cdl_morning_doji_star` | `integer` | Yes | — | Native TA-Lib morning doji star pattern recognition code from historical OHLC. |
| `cdl_engulfing` | `integer` | Yes | — | Native TA-Lib engulfing pattern recognition code from historical OHLC. |
| `cdl_3_white_soldiers` | `integer` | Yes | — | Native TA-Lib 3 white soldiers pattern recognition code from historical OHLC. |
| `cdl_hammer` | `integer` | Yes | — | Native TA-Lib hammer pattern recognition code from historical OHLC. |
| `cdl_inverted_hammer` | `integer` | Yes | — | Native TA-Lib inverted hammer pattern recognition code from historical OHLC. |
| `cdl_3_inside` | `integer` | Yes | — | Native TA-Lib 3 inside pattern recognition code from historical OHLC. |
| `cdl_3_outside` | `integer` | Yes | — | Native TA-Lib 3 outside pattern recognition code from historical OHLC. |
| `cdl_harami` | `integer` | Yes | — | Native TA-Lib harami pattern recognition code from historical OHLC. |
| `cdl_harami_cross` | `integer` | Yes | — | Native TA-Lib harami cross pattern recognition code from historical OHLC. |
| `cdl_dark_cloud_cover` | `integer` | Yes | — | Native TA-Lib dark cloud cover pattern recognition code from historical OHLC. |
| `cdl_evening_star` | `integer` | Yes | — | Native TA-Lib evening star pattern recognition code from historical OHLC. |
| `cdl_evening_doji_star` | `integer` | Yes | — | Native TA-Lib evening doji star pattern recognition code from historical OHLC. |
| `cdl_3_black_crows` | `integer` | Yes | — | Native TA-Lib 3 black crows pattern recognition code from historical OHLC. |
| `cdl_shooting_star` | `integer` | Yes | — | Native TA-Lib shooting star pattern recognition code from historical OHLC. |
| `cdl_hanging_man` | `integer` | Yes | — | Native TA-Lib hanging man pattern recognition code from historical OHLC. |
| `cdl_doji` | `integer` | Yes | — | Native TA-Lib doji pattern recognition code from historical OHLC. |
| `cdl_dragonfly_doji` | `integer` | Yes | — | Native TA-Lib dragonfly doji pattern recognition code from historical OHLC. |
| `cdl_gravestone_doji` | `integer` | Yes | — | Native TA-Lib gravestone doji pattern recognition code from historical OHLC. |
| `cdl_marubozu` | `integer` | Yes | — | Native TA-Lib marubozu pattern recognition code from historical OHLC. |
| `cdl_kicking` | `integer` | Yes | — | Native TA-Lib kicking pattern recognition code from historical OHLC. |
| `cdl_rise_fall_3_methods` | `integer` | Yes | — | Native TA-Lib rise fall 3 methods pattern recognition code from historical OHLC. |
| `cdl_mat_hold` | `integer` | Yes | — | Native TA-Lib mat hold pattern recognition code from historical OHLC. |
| `cdl_hikkake` | `integer` | Yes | — | Native TA-Lib hikkake pattern recognition code from historical OHLC. |
| `calculation_version` | `text` | No | — | Version binds formulas, seeds and pinned TA-Lib versions. |
| `calculated_at` | `timestamp with time zone` | No | — | Timezone-aware execution time of the last changed output row. |
| `adx_14` | `double precision` | Yes | — | Wilder average directional index measuring trend strength on a 0–100 scale. |
| `ema_50` | `double precision` | Yes | — | Fifty-observation exponentially weighted close; alpha=2/51. |
| `ema_200` | `double precision` | Yes | — | Two-hundred-observation exponentially weighted close; alpha=2/201. |
| `inside_bar` | `integer` | Yes | — | Strict current-candle range containment within the previous valid observed candle. |
| `smi` | `double precision` | Yes | — | Stochastic Momentum Index: double-smoothed close displacement from the midpoint of a rolling 14-bar high/low range. |
| `tracking_high` | `integer` | Yes | — | High-search state after all current-bar Pine blocks execute. |
| `tracking_low` | `integer` | Yes | — | Low-search state after all current-bar Pine blocks execute. |
| `temp_high` | `double precision` | Yes | — | Provisional highest high in the current active SMI-above-40 tracking interval. |
| `temp_high_bar` | `integer` | Yes | — | Zero-based source observation index of the currently tracked temporary high. |
| `temp_low` | `double precision` | Yes | — | Provisional lowest low in the current active SMI-below-minus-40 tracking interval. |
| `temp_low_bar` | `integer` | Yes | — | Zero-based source observation index of the currently tracked temporary low. |
| `last_swing_high` | `double precision` | Yes | — | Latest swing-high price available after its SMI-downcross confirmation, carried forward. |
| `break_swing_high` | `integer` | Yes | — | Integer event flag for the supplied Pine close/last-swing-high crossover. |
| `asset_type` | `text` | No | — | Universe-derived asset class: equity from IDX_Stock_Universe; bonds from Universe_Fixed_income. |
| `close` | `double precision` | No | — | Daily closing price copied from the exact classified source row on ticker and trade_date. |

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

## Fixed_Income_Market_Schedule

Fixed-income market timezone, closing clock, final-candle delay and source-label date mapping.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `market_code` | `text` | No | — | Fixed-income market schedule configuration. |
| `country` | `text` | No | — | Fixed-income market schedule configuration. |
| `timezone_name` | `text` | No | — | Fixed-income market schedule configuration. |
| `session_close_local` | `time without time zone` | No | — | Fixed-income market schedule configuration. |
| `finality_delay_minutes` | `integer` | No | — | Fixed-income market schedule configuration. |
| `enabled` | `boolean` | No | `true` | Fixed-income market schedule configuration. |
| `updated_at` | `timestamp with time zone` | No | `statement_timestamp()` | Fixed-income market schedule configuration. |
| `source_date_mapping` | `text` | No | — | Rule that maps the raw TradingView UTC daily-bar label to this market session date. |
| `correction_lookback_sessions` | `integer` | No | `5` | Number of recent completed market sessions reverified and eligible for normal suffix repair. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `Fixed_Income_Market_Schedule_code_check` | Check | `CHECK (market_code = upper(btrim(market_code)) AND market_code <> ''::text)` |
| `Fixed_Income_Market_Schedule_delay_check` | Check | `CHECK (finality_delay_minutes >= 0 AND finality_delay_minutes <= 360)` |
| `Fixed_Income_Market_Schedule_source_date_mapping_check` | Check | `CHECK (source_date_mapping = ANY (ARRAY['CURRENT_OR_PREVIOUS_BUSINESS_DAY'::text, 'NEXT_BUSINESS_DAY'::text]))` |
| `Fixed_Income_Market_Schedule_correction_window_check` | Check | `CHECK (correction_lookback_sessions >= 1 AND correction_lookback_sessions <= 20)` |
| `Fixed_Income_Market_Schedule_timezone_check` | Check | `CHECK (timezone_name = btrim(timezone_name) AND timezone_name <> ''::text)` |
| `Fixed_Income_Market_Schedule_pkey` | Primary key | `PRIMARY KEY (market_code)` |
| `Fixed_Income_Market_Schedule_country_key` | Unique | `UNIQUE (country)` |

### Indexes

| Name | Definition |
|---|---|
| `Fixed_Income_Market_Schedule_country_key` | `CREATE UNIQUE INDEX "Fixed_Income_Market_Schedule_country_key" ON public."Fixed_Income_Market_Schedule" USING btree (country)` |
| `Fixed_Income_Market_Schedule_pkey` | `CREATE UNIQUE INDEX "Fixed_Income_Market_Schedule_pkey" ON public."Fixed_Income_Market_Schedule" USING btree (market_code)` |

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

## IDX_Broker_Profile_History

Point-in-time (bitemporal) history of the tracked IDX_Broker_Profile attributes (broker_name, broker_type, broker_classification), captured by Saniti from the first capture onward. Current knowledge is recorded_to IS NULL; superseded knowledge is kept.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `history_id` | `bigint` | No | — | Row id of one version (identity only). |
| `broker_code` | `text` | No | — | Two-character IDX broker code: the entity key (several rows per broker, one per version; history_id identifies a row). |
| `broker_name` | `text` | Yes | — | IDX_Broker_Profile.broker_name of this version. |
| `broker_type` | `text` | Yes | — | IDX_Broker_Profile.broker_type of this version. |
| `broker_classification` | `text` | Yes | — | IDX_Broker_Profile.broker_classification of this version. |
| `valid_from` | `date` | No | — | Effective start of this version (inclusive). FIRST_CAPTURE and CHANGE_CAPTURED rows use the Asia/Jakarta date Saniti recorded it; the true date is on or before it and unknown (valid_basis). |
| `valid_to` | `date` | Yes | — | Effective end of this version (exclusive); NULL = still in effect in this knowledge version. |
| `valid_basis` | `text` | No | — | FIRST_CAPTURE (valid_from is the first recording date; the true start is earlier and unknown), CHANGE_CAPTURED (valid_from is the date the change was recorded; the true change date is on or before it) or DOCUMENTED (a documented effective date given by a correction). |
| `available_at` | `timestamp with time zone` | No | — | When the information was available to decisions: the recording time (available_basis RECORDED) or a documented publication time (DOCUMENTED_PUBLICATION, corrections only). Point-in-time selection uses recorded time, its conservative bound. |
| `available_basis` | `text` | No | — | RECORDED or DOCUMENTED_PUBLICATION: where available_at comes from. |
| `recorded_from` | `timestamp with time zone` | No | — | When Saniti recorded this row (start of the knowledge period). |
| `recorded_to` | `timestamp with time zone` | Yes | — | When Saniti superseded this row (end of the knowledge period, exclusive); NULL = current knowledge. Superseded rows are kept. |
| `superseded_reason` | `text` | Yes | — | Why the row was superseded: CHANGE_CAPTURED, SAME_DAY_REVISION or CORRECTION; NULL for current knowledge. |
| `pit_valid_from` | `date` | Yes | — | First observation date this row applies to point in time: the later of valid_from and the Asia/Jakarta date after recorded_from (a value recorded on a date is used from the next date). EFFECTIVE_DATED joins use pit_valid_from <= date < pit_valid_to. |
| `pit_valid_to` | `date` | Yes | — | Observation date from which this row no longer applies point in time (exclusive): the earlier of valid_to and the Asia/Jakarta date after recorded_to; NULL = open. A row with pit_valid_to <= pit_valid_from applies to no date. |
| `capture_id` | `bigint` | No | — | The Reference_History_Capture_Log row of the capture or correction that wrote this row. |
| `source_provenance` | `jsonb` | No | — | How the row was written: source table, operation and capture id, the version it closes or replaces, or a correction's reason, source and superseded ids. |

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

## IDX_Broker_Summary_Freq

No description has been recorded.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `trade_date` | `date` | No | — | No column description has been recorded. |
| `symbol` | `text` | No | — | No column description has been recorded. |
| `broker` | `text` | No | — | No column description has been recorded. |
| `broker_name` | `text` | No | — | No column description has been recorded. |
| `investor_type` | `idx_investor_type` | No | — | No column description has been recorded. |
| `market_board` | `idx_market_board` | No | — | No column description has been recorded. |
| `buy_freq` | `bigint` | No | — | No column description has been recorded. |
| `sell_freq` | `bigint` | No | — | No column description has been recorded. |
| `updated_at` | `timestamp with time zone` | No | `now()` | No column description has been recorded. |
| `is_anomaly` | `boolean` | No | `false` | No column description has been recorded. |
| `remark` | `text` | Yes | — | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `IDX_Broker_Summary_Freq_broker_check` | Check | `CHECK (broker ~ '^[A-Z0-9]{2}$'::text)` |
| `IDX_Broker_Summary_Freq_symbol_check` | Check | `CHECK (symbol ~ '^[A-Z]{4}$'::text)` |
| `IDX_Broker_Summary_Freq_pkey` | Primary key | `PRIMARY KEY (trade_date, symbol, broker, investor_type, market_board)` |

### Indexes

| Name | Definition |
|---|---|
| `IDX_Broker_Summary_Freq_pkey` | `CREATE UNIQUE INDEX "IDX_Broker_Summary_Freq_pkey" ON ONLY public."IDX_Broker_Summary_Freq" USING btree (trade_date, symbol, broker, investor_type, market_board)` |
| `idx_broker_freq_broker_date` | `CREATE INDEX idx_broker_freq_broker_date ON ONLY public."IDX_Broker_Summary_Freq" USING btree (broker, trade_date DESC)` |
| `idx_broker_freq_symbol_date` | `CREATE INDEX idx_broker_freq_symbol_date ON ONLY public."IDX_Broker_Summary_Freq" USING btree (symbol, trade_date DESC, investor_type, market_board)` |

## IDX_Net_Foreign_Summary

No description has been recorded.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `trade_date` | `date` | No | — | No column description has been recorded. |
| `ticker` | `text` | No | — | No column description has been recorded. |
| `investor_type` | `idx_investor_type` | No | — | No column description has been recorded. |
| `buy_value` | `numeric` | No | — | No column description has been recorded. |
| `sell_value` | `numeric` | No | — | No column description has been recorded. |
| `net_value` | `numeric` | Yes | — | No column description has been recorded. |
| `buy_freq` | `bigint` | No | — | No column description has been recorded. |
| `sell_freq` | `bigint` | No | — | No column description has been recorded. |
| `updated_at` | `timestamp with time zone` | No | `now()` | No column description has been recorded. |
| `is_anomaly` | `boolean` | No | `false` | No column description has been recorded. |
| `remark` | `text` | Yes | — | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `IDX_Net_Foreign_Summary_ticker_check` | Check | `CHECK (ticker ~ '^[A-Z]{4}$'::text)` |
| `IDX_Net_Foreign_Summary_pkey` | Primary key | `PRIMARY KEY (trade_date, ticker, investor_type)` |

### Indexes

| Name | Definition |
|---|---|
| `IDX_Net_Foreign_Summary_pkey` | `CREATE UNIQUE INDEX "IDX_Net_Foreign_Summary_pkey" ON ONLY public."IDX_Net_Foreign_Summary" USING btree (trade_date, ticker, investor_type)` |
| `idx_net_foreign_ticker_date` | `CREATE INDEX idx_net_foreign_ticker_date ON ONLY public."IDX_Net_Foreign_Summary" USING btree (ticker, trade_date DESC, investor_type)` |

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
| `Sector` | `text` | No | — | Source sector classification. 'Undefined' means the source gives no classification for the security (D02, migration 20261003_001; it replaced the placeholder '0'). It is not a real sector or industry: count it apart, never as a category of its own. |
| `Industry` | `text` | No | — | Source industry classification. 'Undefined' means the source gives no classification for the security (D02, migration 20261003_001; it replaced the placeholder '0'). It is not a real sector or industry: count it apart, never as a category of its own. |
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

Point-in-time (bitemporal) history of the tracked IDX_Stock_Universe attributes (Company Name, Exchange, Security Type, Type Specs, Is Common Stock, ISIN, Sector, Industry), captured by Saniti from the first capture onward. Current knowledge is recorded_to IS NULL; superseded knowledge is kept.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `history_id` | `bigint` | No | — | Row id of one version (identity only). |
| `Ticker` | `text` | No | — | IDX ticker: the entity key (several rows per ticker, one per version; history_id identifies a row). |
| `Company Name` | `text` | Yes | — | IDX_Stock_Universe.Company Name of this version. |
| `Exchange` | `text` | Yes | — | IDX_Stock_Universe.Exchange of this version. |
| `Security Type` | `text` | Yes | — | IDX_Stock_Universe.Security Type of this version. |
| `Type Specs` | `text` | Yes | — | IDX_Stock_Universe.Type Specs of this version. |
| `Is Common Stock` | `text` | Yes | — | IDX_Stock_Universe.Is Common Stock of this version. |
| `ISIN` | `text` | Yes | — | IDX_Stock_Universe.ISIN of this version. |
| `Sector` | `text` | Yes | — | IDX_Stock_Universe.Sector of this version. |
| `Industry` | `text` | Yes | — | IDX_Stock_Universe.Industry of this version. |
| `valid_from` | `date` | No | — | Effective start of this version (inclusive). FIRST_CAPTURE and CHANGE_CAPTURED rows use the Asia/Jakarta date Saniti recorded it; the true date is on or before it and unknown (valid_basis). |
| `valid_to` | `date` | Yes | — | Effective end of this version (exclusive); NULL = still in effect in this knowledge version. |
| `valid_basis` | `text` | No | — | FIRST_CAPTURE (valid_from is the first recording date; the true start is earlier and unknown), CHANGE_CAPTURED (valid_from is the date the change was recorded; the true change date is on or before it) or DOCUMENTED (a documented effective date given by a correction). |
| `available_at` | `timestamp with time zone` | No | — | When the information was available to decisions: the recording time (available_basis RECORDED) or a documented publication time (DOCUMENTED_PUBLICATION, corrections only). Point-in-time selection uses recorded time, its conservative bound. |
| `available_basis` | `text` | No | — | RECORDED or DOCUMENTED_PUBLICATION: where available_at comes from. |
| `recorded_from` | `timestamp with time zone` | No | — | When Saniti recorded this row (start of the knowledge period). |
| `recorded_to` | `timestamp with time zone` | Yes | — | When Saniti superseded this row (end of the knowledge period, exclusive); NULL = current knowledge. Superseded rows are kept. |
| `superseded_reason` | `text` | Yes | — | Why the row was superseded: CHANGE_CAPTURED, SAME_DAY_REVISION or CORRECTION; NULL for current knowledge. |
| `pit_valid_from` | `date` | Yes | — | First observation date this row applies to point in time: the later of valid_from and the Asia/Jakarta date after recorded_from (a value recorded on a date is used from the next date). EFFECTIVE_DATED joins use pit_valid_from <= date < pit_valid_to. |
| `pit_valid_to` | `date` | Yes | — | Observation date from which this row no longer applies point in time (exclusive): the earlier of valid_to and the Asia/Jakarta date after recorded_to; NULL = open. A row with pit_valid_to <= pit_valid_from applies to no date. |
| `capture_id` | `bigint` | No | — | The Reference_History_Capture_Log row of the capture or correction that wrote this row. |
| `source_provenance` | `jsonb` | No | — | How the row was written: source table, operation and capture id, the version it closes or replaces, or a correction's reason, source and superseded ids. |

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

Feature04 automatic/retry batch summary and notification ordering gate.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `execution_id` | `text` | No | — | Operational execution id field for Monitoring_Feature04. |
| `source_execution_id` | `text` | Yes | — | Operational source execution id field for Monitoring_Feature04. |
| `run_type` | `text` | No | — | Operational run type field for Monitoring_Feature04. |
| `trigger_source` | `text` | No | — | Operational trigger source field for Monitoring_Feature04. |
| `update_for_date` | `date` | Yes | — | Operational update for date field for Monitoring_Feature04. |
| `price_notification_required` | `boolean` | No | `true` | Operational price notification required field for Monitoring_Feature04. |
| `price_notification_sent_at` | `timestamp with time zone` | Yes | — | Operational price notification sent at field for Monitoring_Feature04. |
| `eligible_tickers` | `integer` | No | `0` | Operational eligible tickers field for Monitoring_Feature04. |
| `completed_tickers` | `integer` | No | `0` | Operational completed tickers field for Monitoring_Feature04. |
| `failed_tickers` | `integer` | No | `0` | Operational failed tickers field for Monitoring_Feature04. |
| `blocked_tickers` | `integer` | No | `0` | Operational blocked tickers field for Monitoring_Feature04. |
| `status` | `text` | No | `'OPEN'::text` | Operational status field for Monitoring_Feature04. |
| `started_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Operational started at field for Monitoring_Feature04. |
| `sealed_at` | `timestamp with time zone` | Yes | — | Operational sealed at field for Monitoring_Feature04. |
| `finished_at` | `timestamp with time zone` | Yes | — | Operational finished at field for Monitoring_Feature04. |
| `last_error` | `text` | Yes | — | Operational last error field for Monitoring_Feature04. |
| `updated_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Operational updated at field for Monitoring_Feature04. |
| `source_monitor_table` | `text` | No | `'Monitoring_Price_ALL'::text` | Monitoring table whose Telegram delivery must precede this Feature04 result. |

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

Per-ticker membership and outcome of a Feature04 execution.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `execution_id` | `text` | No | — | Operational execution id field for Monitoring_Feature04_Ticker. |
| `ticker` | `text` | No | — | Operational ticker field for Monitoring_Feature04_Ticker. |
| `timeframe` | `text` | No | `'Daily'::text` | Operational timeframe field for Monitoring_Feature04_Ticker. |
| `required_generation` | `bigint` | No | — | Operational required generation field for Monitoring_Feature04_Ticker. |
| `requested_columns` | `ARRAY` | Yes | — | Operational requested columns field for Monitoring_Feature04_Ticker. |
| `status` | `text` | No | `'PENDING'::text` | Operational status field for Monitoring_Feature04_Ticker. |
| `completed_generation` | `bigint` | Yes | — | Operational completed generation field for Monitoring_Feature04_Ticker. |
| `retry_request_id` | `uuid` | Yes | — | Operational retry request id field for Monitoring_Feature04_Ticker. |
| `last_error_code` | `text` | Yes | — | Operational last error code field for Monitoring_Feature04_Ticker. |
| `last_error` | `text` | Yes | — | Operational last error field for Monitoring_Feature04_Ticker. |
| `started_at` | `timestamp with time zone` | Yes | — | Operational started at field for Monitoring_Feature04_Ticker. |
| `finished_at` | `timestamp with time zone` | Yes | — | Operational finished at field for Monitoring_Feature04_Ticker. |
| `updated_at` | `timestamp with time zone` | No | `CURRENT_TIMESTAMP` | Operational updated at field for Monitoring_Feature04_Ticker. |
| `asset_type` | `text` | No | — | Universe-derived asset class: equity from IDX_Stock_Universe; bonds from Universe_Fixed_income. |

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

One market-specific fixed-income daily or recovery execution summary.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `execution_id` | `uuid` | No | — | Physical source or operational column; source-specific semantic review remains open. |
| `run_type` | `text` | No | — | Physical source or operational column; source-specific semantic review remains open. |
| `trigger_source` | `text` | No | — | Physical source or operational column; source-specific semantic review remains open. |
| `target_date` | `date` | No | — | Physical source or operational column; source-specific semantic review remains open. |
| `timeframe` | `text` | No | — | Physical source or operational column; source-specific semantic review remains open. |
| `started_at` | `timestamp with time zone` | No | — | Physical source or operational column; source-specific semantic review remains open. |
| `finished_at` | `timestamp with time zone` | No | — | Physical source or operational column; source-specific semantic review remains open. |
| `expected_series` | `integer` | No | — | Physical source or operational column; source-specific semantic review remains open. |
| `queried_series` | `integer` | No | — | Physical source or operational column; source-specific semantic review remains open. |
| `updated_series` | `integer` | No | — | Physical source or operational column; source-specific semantic review remains open. |
| `missing_series` | `integer` | No | — | Physical source or operational column; source-specific semantic review remains open. |
| `missing_series_list` | `jsonb` | No | — | Physical source or operational column; source-specific semantic review remains open. |
| `status` | `text` | No | — | Physical source or operational column; source-specific semantic review remains open. |
| `last_error` | `text` | Yes | — | Physical source or operational column; source-specific semantic review remains open. |
| `service_name` | `text` | Yes | — | Physical source or operational column; source-specific semantic review remains open. |
| `created_at` | `timestamp with time zone` | No | `statement_timestamp()` | Physical source or operational column; source-specific semantic review remains open. |
| `market_code` | `text` | Yes | — | Market processed by the execution. |
| `final_series` | `integer` | No | `0` | Number of exact-date final series verified. |
| `changed_series` | `integer` | No | `0` | Number of material source payload changes. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `Monitoring_Fixed_Income_final_counts_check` | Check | `CHECK (final_series >= 0 AND changed_series >= 0 AND final_series <= queried_series AND changed_series <= final_series)` |
| `Monitoring_Fixed_Income_market_fkey` | Foreign key | `FOREIGN KEY (market_code) REFERENCES "Fixed_Income_Market_Schedule"(market_code)` |
| `Monitoring_Fixed_Income_pkey` | Primary key | `PRIMARY KEY (execution_id)` |

### Indexes

| Name | Definition |
|---|---|
| `Monitoring_Fixed_Income_market_target_idx` | `CREATE INDEX "Monitoring_Fixed_Income_market_target_idx" ON public."Monitoring_Fixed_Income" USING btree (market_code, target_date DESC, started_at DESC)` |
| `Monitoring_Fixed_Income_pkey` | `CREATE UNIQUE INDEX "Monitoring_Fixed_Income_pkey" ON public."Monitoring_Fixed_Income" USING btree (execution_id)` |
| `monitoring_fixed_income_target_idx` | `CREATE INDEX monitoring_fixed_income_target_idx ON public."Monitoring_Fixed_Income" USING btree (target_date, run_type, started_at DESC)` |

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

## Price_Fixed_Income

Final daily fixed-income OHLC observations with source-bar and market-close finality evidence.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `Country` | `text` | No | — | Physical source or operational column; source-specific semantic review remains open. |
| `instrument_name` | `text` | No | — | Physical source or operational column; source-specific semantic review remains open. |
| `ticker` | `character varying` | No | — | Physical source or operational column; source-specific semantic review remains open. |
| `tradingview_symbol` | `character varying` | No | — | Physical source or operational column; source-specific semantic review remains open. |
| `date` | `date` | No | — | Physical source or operational column; source-specific semantic review remains open. |
| `open` | `numeric` | No | — | Physical source or operational column; source-specific semantic review remains open. |
| `high` | `numeric` | No | — | Physical source or operational column; source-specific semantic review remains open. |
| `low` | `numeric` | No | — | Physical source or operational column; source-specific semantic review remains open. |
| `close` | `numeric` | No | — | Physical source or operational column; source-specific semantic review remains open. |
| `volume` | `numeric` | Yes | — | Physical source or operational column; source-specific semantic review remains open. |
| `source` | `character varying` | No | — | Physical source or operational column; source-specific semantic review remains open. |
| `query_date` | `date` | No | — | Physical source or operational column; source-specific semantic review remains open. |
| `ingestion_time` | `timestamp with time zone` | No | — | Physical source or operational column; source-specific semantic review remains open. |
| `metric_type` | `character varying` | No | — | Physical source or operational column; source-specific semantic review remains open. |
| `value_unit` | `character varying` | No | — | Physical source or operational column; source-specific semantic review remains open. |
| `Timeframe` | `character varying` | No | — | Physical source or operational column; source-specific semantic review remains open. |
| `source_bar_time` | `timestamp with time zone` | Yes | — | Original TradingView daily bar timestamp. |
| `market_close_at` | `timestamp with time zone` | No | — | Configured market close instant for the observation date. |
| `is_final` | `boolean` | No | `false` | Whether the exact daily candle was accepted after market close. |
| `finalized_at` | `timestamp with time zone` | No | — | Time this exact final candle was verified. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `Price_Fixed_Income_finality_check` | Check | `CHECK (NOT is_final OR finalized_at >= market_close_at)` |
| `Price_Fixed_Income_metric_type_check` | Check | `CHECK (metric_type::text = ANY (ARRAY['price'::character varying, 'yield_to_maturity'::character varying]::text[]))` |
| `Price_Fixed_Income_universe_fkey` | Foreign key | `FOREIGN KEY (ticker, metric_type) REFERENCES "Universe_Fixed_income"(ticker, metric_type)` |
| `Price_Fixed_Income_pkey` | Primary key | `PRIMARY KEY (tradingview_symbol, date, metric_type, "Timeframe")` |

### Indexes

| Name | Definition |
|---|---|
| `Price_Fixed_Income_date_idx` | `CREATE INDEX "Price_Fixed_Income_date_idx" ON public."Price_Fixed_Income" USING btree (date)` |
| `Price_Fixed_Income_final_market_idx` | `CREATE INDEX "Price_Fixed_Income_final_market_idx" ON public."Price_Fixed_Income" USING btree ("Country", date DESC, ticker, metric_type) WHERE (is_final AND (("Timeframe")::text = '1D'::text))` |
| `Price_Fixed_Income_pkey` | `CREATE UNIQUE INDEX "Price_Fixed_Income_pkey" ON public."Price_Fixed_Income" USING btree (tradingview_symbol, date, metric_type, "Timeframe")` |
| `Price_Fixed_Income_ticker_metric_idx` | `CREATE INDEX "Price_Fixed_Income_ticker_metric_idx" ON public."Price_Fixed_Income" USING btree (ticker, metric_type)` |

## Price_Stock_Indonesia_IDX

Final daily Indonesian stock OHLCV candles sourced from TradingView.

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
| `market_code` | `text` | No | — | Equity market policy used for close and finality. |
| `source_bar_time` | `timestamp with time zone` | Yes | — | Original provider daily-bar timestamp; NULL for legacy rows where it was not retained. |
| `market_close_at` | `timestamp with time zone` | No | — | Configured market close instant for this observation date. |
| `is_final` | `boolean` | No | `false` | Whether the exact daily candle was accepted after the configured finality delay. |
| `finalized_at` | `timestamp with time zone` | No | — | Time this completed candle was verified. |

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
| `Price_Stock_Indonesia_IDX_finality_check` | Check | `CHECK (NOT is_final OR finalized_at >= market_close_at)` |
| `Price_Stock_Indonesia_IDX_market_fkey` | Foreign key | `FOREIGN KEY (market_code) REFERENCES "Equity_Market_Schedule"(market_code)` |
| `Price_Stock_Indonesia_IDX_pkey` | Primary key | `PRIMARY KEY (ticker, date)` |

### Indexes

| Name | Definition |
|---|---|
| `Price_Stock_Indonesia_IDX_date_idx` | `CREATE INDEX "Price_Stock_Indonesia_IDX_date_idx" ON public."Price_Stock_Indonesia_IDX" USING btree (date)` |
| `Price_Stock_Indonesia_IDX_final_idx` | `CREATE INDEX "Price_Stock_Indonesia_IDX_final_idx" ON public."Price_Stock_Indonesia_IDX" USING btree (ticker, date DESC) WHERE (is_final AND ((timeframe)::text = 'Daily'::text))` |
| `Price_Stock_Indonesia_IDX_pkey` | `CREATE UNIQUE INDEX "Price_Stock_Indonesia_IDX_pkey" ON public."Price_Stock_Indonesia_IDX" USING btree (ticker, date)` |

## Reference_History_Capture_Log

One row per capture of IDX_Stock_Universe or IDX_Broker_Profile into its history (trigger, initial, manual or correction): changed and new versions, keys absent from the load, and the error of a failed capture.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `capture_id` | `bigint` | No | — | Identity of one capture or correction. |
| `source_table` | `text` | No | — | IDX_Stock_Universe or IDX_Broker_Profile. |
| `trigger_operation` | `text` | No | — | INSERT, UPDATE, DELETE or TRUNCATE (trigger), INITIAL (migration), MANUAL, or CORRECTION. |
| `captured_at` | `timestamp with time zone` | No | `now()` | Transaction time of the capture; the recorded_from of the rows it wrote. |
| `status` | `text` | No | — | CAPTURED (versions written), NO_CHANGE, or FAILED (error set; the reference load itself succeeded). |
| `source_rows` | `integer` | Yes | — | Rows in the source table at capture time. |
| `versions_changed` | `integer` | Yes | — | Versions superseded (changed attributes, or overlapped by a correction). |
| `versions_opened` | `integer` | Yes | — | Versions written for new keys, reappearing keys or correction remainders. |
| `absent_entities` | `integer` | Yes | — | Keys with an open version but no source row: counted only, never closed. |
| `absent_examples` | `ARRAY` | No | `'{}'::text[]` | Up to 20 of the absent keys. |
| `error` | `text` | Yes | — | SQLSTATE and message of a failed capture; NULL otherwise. |

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
| `feature04_request_id` | `uuid` | Yes | — | Optional Feature04 retry request created by this Telegram command. |

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

Outbound Telegram delivery and edit ledger for execution-level price results and logical Feature04 market/date or retry results.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `id` | `bigint` | No | — | Generated Telegram delivery-log identifier. |
| `source_table` | `text` | No | — | Monitoring table from which notification details are read. |
| `source_execution_id` | `text` | No | — | Delivery identity: source execution ID for price/manual results, or logical market/date/retry key for Feature04. |
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
| `Sector` | `text` | No | — | IDX or curated sector classification. 'Undefined' means the source gives no classification for the security (D02, migration 20261003_001; it replaced the placeholder '0'). It is not a real sector or industry: count it apart, never as a category of its own. |
| `Industry` | `text` | No | — | IDX or curated industry classification. 'Undefined' means the source gives no classification for the security (D02, migration 20261003_001; it replaced the placeholder '0'). It is not a real sector or industry: count it apart, never as a category of its own. |

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

Approved fixed-income series with explicit source symbol, unit and market-country membership.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `region` | `text` | No | — | Physical source or operational column; source-specific semantic review remains open. |
| `country` | `text` | No | — | Physical source or operational column; source-specific semantic review remains open. |
| `instrument_name` | `text` | No | — | Physical source or operational column; source-specific semantic review remains open. |
| `ticker` | `text` | No | — | Physical source or operational column; source-specific semantic review remains open. |
| `exchange` | `text` | No | — | Physical source or operational column; source-specific semantic review remains open. |
| `security_type` | `text` | No | — | Physical source or operational column; source-specific semantic review remains open. |
| `type_specs` | `text` | No | — | Physical source or operational column; source-specific semantic review remains open. |
| `is_common_stock` | `boolean` | No | — | Physical source or operational column; source-specific semantic review remains open. |
| `tradingview_country` | `text` | No | — | Physical source or operational column; source-specific semantic review remains open. |
| `metric_type` | `text` | No | — | Physical source or operational column; source-specific semantic review remains open. |
| `tenor` | `text` | No | — | Physical source or operational column; source-specific semantic review remains open. |
| `updated_at` | `timestamp with time zone` | No | `statement_timestamp()` | Physical source or operational column; source-specific semantic review remains open. |
| `tradingview_symbol` | `text` | No | — | Exact TradingView symbol for the universe series. |
| `value_unit` | `text` | No | — | Source unit for the universe series. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `Universe_Fixed_income_metric_type_check` | Check | `CHECK (metric_type = ANY (ARRAY['price'::text, 'yield_to_maturity'::text]))` |
| `Universe_Fixed_income_country_schedule_fkey` | Foreign key | `FOREIGN KEY (country) REFERENCES "Fixed_Income_Market_Schedule"(country)` |
| `Universe_Fixed_income_pkey` | Primary key | `PRIMARY KEY (ticker, metric_type)` |
| `Universe_Fixed_income_symbol_metric_key` | Unique | `UNIQUE (tradingview_symbol, metric_type)` |

### Indexes

| Name | Definition |
|---|---|
| `Universe_Fixed_income_pkey` | `CREATE UNIQUE INDEX "Universe_Fixed_income_pkey" ON public."Universe_Fixed_income" USING btree (ticker, metric_type)` |
| `Universe_Fixed_income_symbol_metric_key` | `CREATE UNIQUE INDEX "Universe_Fixed_income_symbol_metric_key" ON public."Universe_Fixed_income" USING btree (tradingview_symbol, metric_type)` |

## feature04_backfill_log

Atomic Feature04 per-run/ticker historical calculation audit and resumable extraction/output fingerprints.

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

## idx_broker_summary_freq_2016

No description has been recorded.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `trade_date` | `date` | No | — | No column description has been recorded. |
| `symbol` | `text` | No | — | No column description has been recorded. |
| `broker` | `text` | No | — | No column description has been recorded. |
| `broker_name` | `text` | No | — | No column description has been recorded. |
| `investor_type` | `idx_investor_type` | No | — | No column description has been recorded. |
| `market_board` | `idx_market_board` | No | — | No column description has been recorded. |
| `buy_freq` | `bigint` | No | — | No column description has been recorded. |
| `sell_freq` | `bigint` | No | — | No column description has been recorded. |
| `updated_at` | `timestamp with time zone` | No | `now()` | No column description has been recorded. |
| `is_anomaly` | `boolean` | No | `false` | No column description has been recorded. |
| `remark` | `text` | Yes | — | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `IDX_Broker_Summary_Freq_broker_check` | Check | `CHECK (broker ~ '^[A-Z0-9]{2}$'::text)` |
| `IDX_Broker_Summary_Freq_symbol_check` | Check | `CHECK (symbol ~ '^[A-Z]{4}$'::text)` |
| `idx_broker_summary_freq_2016_pkey` | Primary key | `PRIMARY KEY (trade_date, symbol, broker, investor_type, market_board)` |

### Indexes

| Name | Definition |
|---|---|
| `idx_broker_summary_freq_2016_broker_trade_date_idx` | `CREATE INDEX idx_broker_summary_freq_2016_broker_trade_date_idx ON public.idx_broker_summary_freq_2016 USING btree (broker, trade_date DESC)` |
| `idx_broker_summary_freq_2016_pkey` | `CREATE UNIQUE INDEX idx_broker_summary_freq_2016_pkey ON public.idx_broker_summary_freq_2016 USING btree (trade_date, symbol, broker, investor_type, market_board)` |
| `idx_broker_summary_freq_2016_symbol_trade_date_investor_typ_idx` | `CREATE INDEX idx_broker_summary_freq_2016_symbol_trade_date_investor_typ_idx ON public.idx_broker_summary_freq_2016 USING btree (symbol, trade_date DESC, investor_type, market_board)` |

## idx_broker_summary_freq_2017

No description has been recorded.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `trade_date` | `date` | No | — | No column description has been recorded. |
| `symbol` | `text` | No | — | No column description has been recorded. |
| `broker` | `text` | No | — | No column description has been recorded. |
| `broker_name` | `text` | No | — | No column description has been recorded. |
| `investor_type` | `idx_investor_type` | No | — | No column description has been recorded. |
| `market_board` | `idx_market_board` | No | — | No column description has been recorded. |
| `buy_freq` | `bigint` | No | — | No column description has been recorded. |
| `sell_freq` | `bigint` | No | — | No column description has been recorded. |
| `updated_at` | `timestamp with time zone` | No | `now()` | No column description has been recorded. |
| `is_anomaly` | `boolean` | No | `false` | No column description has been recorded. |
| `remark` | `text` | Yes | — | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `IDX_Broker_Summary_Freq_broker_check` | Check | `CHECK (broker ~ '^[A-Z0-9]{2}$'::text)` |
| `IDX_Broker_Summary_Freq_symbol_check` | Check | `CHECK (symbol ~ '^[A-Z]{4}$'::text)` |
| `idx_broker_summary_freq_2017_pkey` | Primary key | `PRIMARY KEY (trade_date, symbol, broker, investor_type, market_board)` |

### Indexes

| Name | Definition |
|---|---|
| `idx_broker_summary_freq_2017_broker_trade_date_idx` | `CREATE INDEX idx_broker_summary_freq_2017_broker_trade_date_idx ON public.idx_broker_summary_freq_2017 USING btree (broker, trade_date DESC)` |
| `idx_broker_summary_freq_2017_pkey` | `CREATE UNIQUE INDEX idx_broker_summary_freq_2017_pkey ON public.idx_broker_summary_freq_2017 USING btree (trade_date, symbol, broker, investor_type, market_board)` |
| `idx_broker_summary_freq_2017_symbol_trade_date_investor_typ_idx` | `CREATE INDEX idx_broker_summary_freq_2017_symbol_trade_date_investor_typ_idx ON public.idx_broker_summary_freq_2017 USING btree (symbol, trade_date DESC, investor_type, market_board)` |

## idx_broker_summary_freq_2018

No description has been recorded.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `trade_date` | `date` | No | — | No column description has been recorded. |
| `symbol` | `text` | No | — | No column description has been recorded. |
| `broker` | `text` | No | — | No column description has been recorded. |
| `broker_name` | `text` | No | — | No column description has been recorded. |
| `investor_type` | `idx_investor_type` | No | — | No column description has been recorded. |
| `market_board` | `idx_market_board` | No | — | No column description has been recorded. |
| `buy_freq` | `bigint` | No | — | No column description has been recorded. |
| `sell_freq` | `bigint` | No | — | No column description has been recorded. |
| `updated_at` | `timestamp with time zone` | No | `now()` | No column description has been recorded. |
| `is_anomaly` | `boolean` | No | `false` | No column description has been recorded. |
| `remark` | `text` | Yes | — | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `IDX_Broker_Summary_Freq_broker_check` | Check | `CHECK (broker ~ '^[A-Z0-9]{2}$'::text)` |
| `IDX_Broker_Summary_Freq_symbol_check` | Check | `CHECK (symbol ~ '^[A-Z]{4}$'::text)` |
| `idx_broker_summary_freq_2018_pkey` | Primary key | `PRIMARY KEY (trade_date, symbol, broker, investor_type, market_board)` |

### Indexes

| Name | Definition |
|---|---|
| `idx_broker_summary_freq_2018_broker_trade_date_idx` | `CREATE INDEX idx_broker_summary_freq_2018_broker_trade_date_idx ON public.idx_broker_summary_freq_2018 USING btree (broker, trade_date DESC)` |
| `idx_broker_summary_freq_2018_pkey` | `CREATE UNIQUE INDEX idx_broker_summary_freq_2018_pkey ON public.idx_broker_summary_freq_2018 USING btree (trade_date, symbol, broker, investor_type, market_board)` |
| `idx_broker_summary_freq_2018_symbol_trade_date_investor_typ_idx` | `CREATE INDEX idx_broker_summary_freq_2018_symbol_trade_date_investor_typ_idx ON public.idx_broker_summary_freq_2018 USING btree (symbol, trade_date DESC, investor_type, market_board)` |

## idx_broker_summary_freq_2019

No description has been recorded.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `trade_date` | `date` | No | — | No column description has been recorded. |
| `symbol` | `text` | No | — | No column description has been recorded. |
| `broker` | `text` | No | — | No column description has been recorded. |
| `broker_name` | `text` | No | — | No column description has been recorded. |
| `investor_type` | `idx_investor_type` | No | — | No column description has been recorded. |
| `market_board` | `idx_market_board` | No | — | No column description has been recorded. |
| `buy_freq` | `bigint` | No | — | No column description has been recorded. |
| `sell_freq` | `bigint` | No | — | No column description has been recorded. |
| `updated_at` | `timestamp with time zone` | No | `now()` | No column description has been recorded. |
| `is_anomaly` | `boolean` | No | `false` | No column description has been recorded. |
| `remark` | `text` | Yes | — | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `IDX_Broker_Summary_Freq_broker_check` | Check | `CHECK (broker ~ '^[A-Z0-9]{2}$'::text)` |
| `IDX_Broker_Summary_Freq_symbol_check` | Check | `CHECK (symbol ~ '^[A-Z]{4}$'::text)` |
| `idx_broker_summary_freq_2019_pkey` | Primary key | `PRIMARY KEY (trade_date, symbol, broker, investor_type, market_board)` |

### Indexes

| Name | Definition |
|---|---|
| `idx_broker_summary_freq_2019_broker_trade_date_idx` | `CREATE INDEX idx_broker_summary_freq_2019_broker_trade_date_idx ON public.idx_broker_summary_freq_2019 USING btree (broker, trade_date DESC)` |
| `idx_broker_summary_freq_2019_pkey` | `CREATE UNIQUE INDEX idx_broker_summary_freq_2019_pkey ON public.idx_broker_summary_freq_2019 USING btree (trade_date, symbol, broker, investor_type, market_board)` |
| `idx_broker_summary_freq_2019_symbol_trade_date_investor_typ_idx` | `CREATE INDEX idx_broker_summary_freq_2019_symbol_trade_date_investor_typ_idx ON public.idx_broker_summary_freq_2019 USING btree (symbol, trade_date DESC, investor_type, market_board)` |

## idx_broker_summary_freq_2020

No description has been recorded.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `trade_date` | `date` | No | — | No column description has been recorded. |
| `symbol` | `text` | No | — | No column description has been recorded. |
| `broker` | `text` | No | — | No column description has been recorded. |
| `broker_name` | `text` | No | — | No column description has been recorded. |
| `investor_type` | `idx_investor_type` | No | — | No column description has been recorded. |
| `market_board` | `idx_market_board` | No | — | No column description has been recorded. |
| `buy_freq` | `bigint` | No | — | No column description has been recorded. |
| `sell_freq` | `bigint` | No | — | No column description has been recorded. |
| `updated_at` | `timestamp with time zone` | No | `now()` | No column description has been recorded. |
| `is_anomaly` | `boolean` | No | `false` | No column description has been recorded. |
| `remark` | `text` | Yes | — | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `IDX_Broker_Summary_Freq_broker_check` | Check | `CHECK (broker ~ '^[A-Z0-9]{2}$'::text)` |
| `IDX_Broker_Summary_Freq_symbol_check` | Check | `CHECK (symbol ~ '^[A-Z]{4}$'::text)` |
| `idx_broker_summary_freq_2020_pkey` | Primary key | `PRIMARY KEY (trade_date, symbol, broker, investor_type, market_board)` |

### Indexes

| Name | Definition |
|---|---|
| `idx_broker_summary_freq_2020_broker_trade_date_idx` | `CREATE INDEX idx_broker_summary_freq_2020_broker_trade_date_idx ON public.idx_broker_summary_freq_2020 USING btree (broker, trade_date DESC)` |
| `idx_broker_summary_freq_2020_pkey` | `CREATE UNIQUE INDEX idx_broker_summary_freq_2020_pkey ON public.idx_broker_summary_freq_2020 USING btree (trade_date, symbol, broker, investor_type, market_board)` |
| `idx_broker_summary_freq_2020_symbol_trade_date_investor_typ_idx` | `CREATE INDEX idx_broker_summary_freq_2020_symbol_trade_date_investor_typ_idx ON public.idx_broker_summary_freq_2020 USING btree (symbol, trade_date DESC, investor_type, market_board)` |

## idx_broker_summary_freq_2021

No description has been recorded.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `trade_date` | `date` | No | — | No column description has been recorded. |
| `symbol` | `text` | No | — | No column description has been recorded. |
| `broker` | `text` | No | — | No column description has been recorded. |
| `broker_name` | `text` | No | — | No column description has been recorded. |
| `investor_type` | `idx_investor_type` | No | — | No column description has been recorded. |
| `market_board` | `idx_market_board` | No | — | No column description has been recorded. |
| `buy_freq` | `bigint` | No | — | No column description has been recorded. |
| `sell_freq` | `bigint` | No | — | No column description has been recorded. |
| `updated_at` | `timestamp with time zone` | No | `now()` | No column description has been recorded. |
| `is_anomaly` | `boolean` | No | `false` | No column description has been recorded. |
| `remark` | `text` | Yes | — | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `IDX_Broker_Summary_Freq_broker_check` | Check | `CHECK (broker ~ '^[A-Z0-9]{2}$'::text)` |
| `IDX_Broker_Summary_Freq_symbol_check` | Check | `CHECK (symbol ~ '^[A-Z]{4}$'::text)` |
| `idx_broker_summary_freq_2021_pkey` | Primary key | `PRIMARY KEY (trade_date, symbol, broker, investor_type, market_board)` |

### Indexes

| Name | Definition |
|---|---|
| `idx_broker_summary_freq_2021_broker_trade_date_idx` | `CREATE INDEX idx_broker_summary_freq_2021_broker_trade_date_idx ON public.idx_broker_summary_freq_2021 USING btree (broker, trade_date DESC)` |
| `idx_broker_summary_freq_2021_pkey` | `CREATE UNIQUE INDEX idx_broker_summary_freq_2021_pkey ON public.idx_broker_summary_freq_2021 USING btree (trade_date, symbol, broker, investor_type, market_board)` |
| `idx_broker_summary_freq_2021_symbol_trade_date_investor_typ_idx` | `CREATE INDEX idx_broker_summary_freq_2021_symbol_trade_date_investor_typ_idx ON public.idx_broker_summary_freq_2021 USING btree (symbol, trade_date DESC, investor_type, market_board)` |

## idx_broker_summary_freq_2022

No description has been recorded.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `trade_date` | `date` | No | — | No column description has been recorded. |
| `symbol` | `text` | No | — | No column description has been recorded. |
| `broker` | `text` | No | — | No column description has been recorded. |
| `broker_name` | `text` | No | — | No column description has been recorded. |
| `investor_type` | `idx_investor_type` | No | — | No column description has been recorded. |
| `market_board` | `idx_market_board` | No | — | No column description has been recorded. |
| `buy_freq` | `bigint` | No | — | No column description has been recorded. |
| `sell_freq` | `bigint` | No | — | No column description has been recorded. |
| `updated_at` | `timestamp with time zone` | No | `now()` | No column description has been recorded. |
| `is_anomaly` | `boolean` | No | `false` | No column description has been recorded. |
| `remark` | `text` | Yes | — | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `IDX_Broker_Summary_Freq_broker_check` | Check | `CHECK (broker ~ '^[A-Z0-9]{2}$'::text)` |
| `IDX_Broker_Summary_Freq_symbol_check` | Check | `CHECK (symbol ~ '^[A-Z]{4}$'::text)` |
| `idx_broker_summary_freq_2022_pkey` | Primary key | `PRIMARY KEY (trade_date, symbol, broker, investor_type, market_board)` |

### Indexes

| Name | Definition |
|---|---|
| `idx_broker_summary_freq_2022_broker_trade_date_idx` | `CREATE INDEX idx_broker_summary_freq_2022_broker_trade_date_idx ON public.idx_broker_summary_freq_2022 USING btree (broker, trade_date DESC)` |
| `idx_broker_summary_freq_2022_pkey` | `CREATE UNIQUE INDEX idx_broker_summary_freq_2022_pkey ON public.idx_broker_summary_freq_2022 USING btree (trade_date, symbol, broker, investor_type, market_board)` |
| `idx_broker_summary_freq_2022_symbol_trade_date_investor_typ_idx` | `CREATE INDEX idx_broker_summary_freq_2022_symbol_trade_date_investor_typ_idx ON public.idx_broker_summary_freq_2022 USING btree (symbol, trade_date DESC, investor_type, market_board)` |

## idx_broker_summary_freq_2023

No description has been recorded.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `trade_date` | `date` | No | — | No column description has been recorded. |
| `symbol` | `text` | No | — | No column description has been recorded. |
| `broker` | `text` | No | — | No column description has been recorded. |
| `broker_name` | `text` | No | — | No column description has been recorded. |
| `investor_type` | `idx_investor_type` | No | — | No column description has been recorded. |
| `market_board` | `idx_market_board` | No | — | No column description has been recorded. |
| `buy_freq` | `bigint` | No | — | No column description has been recorded. |
| `sell_freq` | `bigint` | No | — | No column description has been recorded. |
| `updated_at` | `timestamp with time zone` | No | `now()` | No column description has been recorded. |
| `is_anomaly` | `boolean` | No | `false` | No column description has been recorded. |
| `remark` | `text` | Yes | — | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `IDX_Broker_Summary_Freq_broker_check` | Check | `CHECK (broker ~ '^[A-Z0-9]{2}$'::text)` |
| `IDX_Broker_Summary_Freq_symbol_check` | Check | `CHECK (symbol ~ '^[A-Z]{4}$'::text)` |
| `idx_broker_summary_freq_2023_pkey` | Primary key | `PRIMARY KEY (trade_date, symbol, broker, investor_type, market_board)` |

### Indexes

| Name | Definition |
|---|---|
| `idx_broker_summary_freq_2023_broker_trade_date_idx` | `CREATE INDEX idx_broker_summary_freq_2023_broker_trade_date_idx ON public.idx_broker_summary_freq_2023 USING btree (broker, trade_date DESC)` |
| `idx_broker_summary_freq_2023_pkey` | `CREATE UNIQUE INDEX idx_broker_summary_freq_2023_pkey ON public.idx_broker_summary_freq_2023 USING btree (trade_date, symbol, broker, investor_type, market_board)` |
| `idx_broker_summary_freq_2023_symbol_trade_date_investor_typ_idx` | `CREATE INDEX idx_broker_summary_freq_2023_symbol_trade_date_investor_typ_idx ON public.idx_broker_summary_freq_2023 USING btree (symbol, trade_date DESC, investor_type, market_board)` |

## idx_broker_summary_freq_2024

No description has been recorded.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `trade_date` | `date` | No | — | No column description has been recorded. |
| `symbol` | `text` | No | — | No column description has been recorded. |
| `broker` | `text` | No | — | No column description has been recorded. |
| `broker_name` | `text` | No | — | No column description has been recorded. |
| `investor_type` | `idx_investor_type` | No | — | No column description has been recorded. |
| `market_board` | `idx_market_board` | No | — | No column description has been recorded. |
| `buy_freq` | `bigint` | No | — | No column description has been recorded. |
| `sell_freq` | `bigint` | No | — | No column description has been recorded. |
| `updated_at` | `timestamp with time zone` | No | `now()` | No column description has been recorded. |
| `is_anomaly` | `boolean` | No | `false` | No column description has been recorded. |
| `remark` | `text` | Yes | — | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `IDX_Broker_Summary_Freq_broker_check` | Check | `CHECK (broker ~ '^[A-Z0-9]{2}$'::text)` |
| `IDX_Broker_Summary_Freq_symbol_check` | Check | `CHECK (symbol ~ '^[A-Z]{4}$'::text)` |
| `idx_broker_summary_freq_2024_pkey` | Primary key | `PRIMARY KEY (trade_date, symbol, broker, investor_type, market_board)` |

### Indexes

| Name | Definition |
|---|---|
| `idx_broker_summary_freq_2024_broker_trade_date_idx` | `CREATE INDEX idx_broker_summary_freq_2024_broker_trade_date_idx ON public.idx_broker_summary_freq_2024 USING btree (broker, trade_date DESC)` |
| `idx_broker_summary_freq_2024_pkey` | `CREATE UNIQUE INDEX idx_broker_summary_freq_2024_pkey ON public.idx_broker_summary_freq_2024 USING btree (trade_date, symbol, broker, investor_type, market_board)` |
| `idx_broker_summary_freq_2024_symbol_trade_date_investor_typ_idx` | `CREATE INDEX idx_broker_summary_freq_2024_symbol_trade_date_investor_typ_idx ON public.idx_broker_summary_freq_2024 USING btree (symbol, trade_date DESC, investor_type, market_board)` |

## idx_broker_summary_freq_2025

No description has been recorded.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `trade_date` | `date` | No | — | No column description has been recorded. |
| `symbol` | `text` | No | — | No column description has been recorded. |
| `broker` | `text` | No | — | No column description has been recorded. |
| `broker_name` | `text` | No | — | No column description has been recorded. |
| `investor_type` | `idx_investor_type` | No | — | No column description has been recorded. |
| `market_board` | `idx_market_board` | No | — | No column description has been recorded. |
| `buy_freq` | `bigint` | No | — | No column description has been recorded. |
| `sell_freq` | `bigint` | No | — | No column description has been recorded. |
| `updated_at` | `timestamp with time zone` | No | `now()` | No column description has been recorded. |
| `is_anomaly` | `boolean` | No | `false` | No column description has been recorded. |
| `remark` | `text` | Yes | — | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `IDX_Broker_Summary_Freq_broker_check` | Check | `CHECK (broker ~ '^[A-Z0-9]{2}$'::text)` |
| `IDX_Broker_Summary_Freq_symbol_check` | Check | `CHECK (symbol ~ '^[A-Z]{4}$'::text)` |
| `idx_broker_summary_freq_2025_pkey` | Primary key | `PRIMARY KEY (trade_date, symbol, broker, investor_type, market_board)` |

### Indexes

| Name | Definition |
|---|---|
| `idx_broker_summary_freq_2025_broker_trade_date_idx` | `CREATE INDEX idx_broker_summary_freq_2025_broker_trade_date_idx ON public.idx_broker_summary_freq_2025 USING btree (broker, trade_date DESC)` |
| `idx_broker_summary_freq_2025_pkey` | `CREATE UNIQUE INDEX idx_broker_summary_freq_2025_pkey ON public.idx_broker_summary_freq_2025 USING btree (trade_date, symbol, broker, investor_type, market_board)` |
| `idx_broker_summary_freq_2025_symbol_trade_date_investor_typ_idx` | `CREATE INDEX idx_broker_summary_freq_2025_symbol_trade_date_investor_typ_idx ON public.idx_broker_summary_freq_2025 USING btree (symbol, trade_date DESC, investor_type, market_board)` |

## idx_broker_summary_freq_2026

No description has been recorded.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `trade_date` | `date` | No | — | No column description has been recorded. |
| `symbol` | `text` | No | — | No column description has been recorded. |
| `broker` | `text` | No | — | No column description has been recorded. |
| `broker_name` | `text` | No | — | No column description has been recorded. |
| `investor_type` | `idx_investor_type` | No | — | No column description has been recorded. |
| `market_board` | `idx_market_board` | No | — | No column description has been recorded. |
| `buy_freq` | `bigint` | No | — | No column description has been recorded. |
| `sell_freq` | `bigint` | No | — | No column description has been recorded. |
| `updated_at` | `timestamp with time zone` | No | `now()` | No column description has been recorded. |
| `is_anomaly` | `boolean` | No | `false` | No column description has been recorded. |
| `remark` | `text` | Yes | — | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `IDX_Broker_Summary_Freq_broker_check` | Check | `CHECK (broker ~ '^[A-Z0-9]{2}$'::text)` |
| `IDX_Broker_Summary_Freq_symbol_check` | Check | `CHECK (symbol ~ '^[A-Z]{4}$'::text)` |
| `idx_broker_summary_freq_2026_pkey` | Primary key | `PRIMARY KEY (trade_date, symbol, broker, investor_type, market_board)` |

### Indexes

| Name | Definition |
|---|---|
| `idx_broker_summary_freq_2026_broker_trade_date_idx` | `CREATE INDEX idx_broker_summary_freq_2026_broker_trade_date_idx ON public.idx_broker_summary_freq_2026 USING btree (broker, trade_date DESC)` |
| `idx_broker_summary_freq_2026_pkey` | `CREATE UNIQUE INDEX idx_broker_summary_freq_2026_pkey ON public.idx_broker_summary_freq_2026 USING btree (trade_date, symbol, broker, investor_type, market_board)` |
| `idx_broker_summary_freq_2026_symbol_trade_date_investor_typ_idx` | `CREATE INDEX idx_broker_summary_freq_2026_symbol_trade_date_investor_typ_idx ON public.idx_broker_summary_freq_2026 USING btree (symbol, trade_date DESC, investor_type, market_board)` |

## idx_broker_summary_freq_2027

No description has been recorded.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `trade_date` | `date` | No | — | No column description has been recorded. |
| `symbol` | `text` | No | — | No column description has been recorded. |
| `broker` | `text` | No | — | No column description has been recorded. |
| `broker_name` | `text` | No | — | No column description has been recorded. |
| `investor_type` | `idx_investor_type` | No | — | No column description has been recorded. |
| `market_board` | `idx_market_board` | No | — | No column description has been recorded. |
| `buy_freq` | `bigint` | No | — | No column description has been recorded. |
| `sell_freq` | `bigint` | No | — | No column description has been recorded. |
| `updated_at` | `timestamp with time zone` | No | `now()` | No column description has been recorded. |
| `is_anomaly` | `boolean` | No | `false` | No column description has been recorded. |
| `remark` | `text` | Yes | — | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `IDX_Broker_Summary_Freq_broker_check` | Check | `CHECK (broker ~ '^[A-Z0-9]{2}$'::text)` |
| `IDX_Broker_Summary_Freq_symbol_check` | Check | `CHECK (symbol ~ '^[A-Z]{4}$'::text)` |
| `idx_broker_summary_freq_2027_pkey` | Primary key | `PRIMARY KEY (trade_date, symbol, broker, investor_type, market_board)` |

### Indexes

| Name | Definition |
|---|---|
| `idx_broker_summary_freq_2027_broker_trade_date_idx` | `CREATE INDEX idx_broker_summary_freq_2027_broker_trade_date_idx ON public.idx_broker_summary_freq_2027 USING btree (broker, trade_date DESC)` |
| `idx_broker_summary_freq_2027_pkey` | `CREATE UNIQUE INDEX idx_broker_summary_freq_2027_pkey ON public.idx_broker_summary_freq_2027 USING btree (trade_date, symbol, broker, investor_type, market_board)` |
| `idx_broker_summary_freq_2027_symbol_trade_date_investor_typ_idx` | `CREATE INDEX idx_broker_summary_freq_2027_symbol_trade_date_investor_typ_idx ON public.idx_broker_summary_freq_2027 USING btree (symbol, trade_date DESC, investor_type, market_board)` |

## idx_net_foreign_summary_2016

No description has been recorded.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `trade_date` | `date` | No | — | No column description has been recorded. |
| `ticker` | `text` | No | — | No column description has been recorded. |
| `investor_type` | `idx_investor_type` | No | — | No column description has been recorded. |
| `buy_value` | `numeric` | No | — | No column description has been recorded. |
| `sell_value` | `numeric` | No | — | No column description has been recorded. |
| `net_value` | `numeric` | Yes | — | No column description has been recorded. |
| `buy_freq` | `bigint` | No | — | No column description has been recorded. |
| `sell_freq` | `bigint` | No | — | No column description has been recorded. |
| `updated_at` | `timestamp with time zone` | No | `now()` | No column description has been recorded. |
| `is_anomaly` | `boolean` | No | `false` | No column description has been recorded. |
| `remark` | `text` | Yes | — | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `IDX_Net_Foreign_Summary_ticker_check` | Check | `CHECK (ticker ~ '^[A-Z]{4}$'::text)` |
| `idx_net_foreign_summary_2016_pkey` | Primary key | `PRIMARY KEY (trade_date, ticker, investor_type)` |

### Indexes

| Name | Definition |
|---|---|
| `idx_net_foreign_summary_2016_pkey` | `CREATE UNIQUE INDEX idx_net_foreign_summary_2016_pkey ON public.idx_net_foreign_summary_2016 USING btree (trade_date, ticker, investor_type)` |
| `idx_net_foreign_summary_2016_ticker_trade_date_investor_typ_idx` | `CREATE INDEX idx_net_foreign_summary_2016_ticker_trade_date_investor_typ_idx ON public.idx_net_foreign_summary_2016 USING btree (ticker, trade_date DESC, investor_type)` |

## idx_net_foreign_summary_2017

No description has been recorded.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `trade_date` | `date` | No | — | No column description has been recorded. |
| `ticker` | `text` | No | — | No column description has been recorded. |
| `investor_type` | `idx_investor_type` | No | — | No column description has been recorded. |
| `buy_value` | `numeric` | No | — | No column description has been recorded. |
| `sell_value` | `numeric` | No | — | No column description has been recorded. |
| `net_value` | `numeric` | Yes | — | No column description has been recorded. |
| `buy_freq` | `bigint` | No | — | No column description has been recorded. |
| `sell_freq` | `bigint` | No | — | No column description has been recorded. |
| `updated_at` | `timestamp with time zone` | No | `now()` | No column description has been recorded. |
| `is_anomaly` | `boolean` | No | `false` | No column description has been recorded. |
| `remark` | `text` | Yes | — | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `IDX_Net_Foreign_Summary_ticker_check` | Check | `CHECK (ticker ~ '^[A-Z]{4}$'::text)` |
| `idx_net_foreign_summary_2017_pkey` | Primary key | `PRIMARY KEY (trade_date, ticker, investor_type)` |

### Indexes

| Name | Definition |
|---|---|
| `idx_net_foreign_summary_2017_pkey` | `CREATE UNIQUE INDEX idx_net_foreign_summary_2017_pkey ON public.idx_net_foreign_summary_2017 USING btree (trade_date, ticker, investor_type)` |
| `idx_net_foreign_summary_2017_ticker_trade_date_investor_typ_idx` | `CREATE INDEX idx_net_foreign_summary_2017_ticker_trade_date_investor_typ_idx ON public.idx_net_foreign_summary_2017 USING btree (ticker, trade_date DESC, investor_type)` |

## idx_net_foreign_summary_2018

No description has been recorded.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `trade_date` | `date` | No | — | No column description has been recorded. |
| `ticker` | `text` | No | — | No column description has been recorded. |
| `investor_type` | `idx_investor_type` | No | — | No column description has been recorded. |
| `buy_value` | `numeric` | No | — | No column description has been recorded. |
| `sell_value` | `numeric` | No | — | No column description has been recorded. |
| `net_value` | `numeric` | Yes | — | No column description has been recorded. |
| `buy_freq` | `bigint` | No | — | No column description has been recorded. |
| `sell_freq` | `bigint` | No | — | No column description has been recorded. |
| `updated_at` | `timestamp with time zone` | No | `now()` | No column description has been recorded. |
| `is_anomaly` | `boolean` | No | `false` | No column description has been recorded. |
| `remark` | `text` | Yes | — | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `IDX_Net_Foreign_Summary_ticker_check` | Check | `CHECK (ticker ~ '^[A-Z]{4}$'::text)` |
| `idx_net_foreign_summary_2018_pkey` | Primary key | `PRIMARY KEY (trade_date, ticker, investor_type)` |

### Indexes

| Name | Definition |
|---|---|
| `idx_net_foreign_summary_2018_pkey` | `CREATE UNIQUE INDEX idx_net_foreign_summary_2018_pkey ON public.idx_net_foreign_summary_2018 USING btree (trade_date, ticker, investor_type)` |
| `idx_net_foreign_summary_2018_ticker_trade_date_investor_typ_idx` | `CREATE INDEX idx_net_foreign_summary_2018_ticker_trade_date_investor_typ_idx ON public.idx_net_foreign_summary_2018 USING btree (ticker, trade_date DESC, investor_type)` |

## idx_net_foreign_summary_2019

No description has been recorded.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `trade_date` | `date` | No | — | No column description has been recorded. |
| `ticker` | `text` | No | — | No column description has been recorded. |
| `investor_type` | `idx_investor_type` | No | — | No column description has been recorded. |
| `buy_value` | `numeric` | No | — | No column description has been recorded. |
| `sell_value` | `numeric` | No | — | No column description has been recorded. |
| `net_value` | `numeric` | Yes | — | No column description has been recorded. |
| `buy_freq` | `bigint` | No | — | No column description has been recorded. |
| `sell_freq` | `bigint` | No | — | No column description has been recorded. |
| `updated_at` | `timestamp with time zone` | No | `now()` | No column description has been recorded. |
| `is_anomaly` | `boolean` | No | `false` | No column description has been recorded. |
| `remark` | `text` | Yes | — | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `IDX_Net_Foreign_Summary_ticker_check` | Check | `CHECK (ticker ~ '^[A-Z]{4}$'::text)` |
| `idx_net_foreign_summary_2019_pkey` | Primary key | `PRIMARY KEY (trade_date, ticker, investor_type)` |

### Indexes

| Name | Definition |
|---|---|
| `idx_net_foreign_summary_2019_pkey` | `CREATE UNIQUE INDEX idx_net_foreign_summary_2019_pkey ON public.idx_net_foreign_summary_2019 USING btree (trade_date, ticker, investor_type)` |
| `idx_net_foreign_summary_2019_ticker_trade_date_investor_typ_idx` | `CREATE INDEX idx_net_foreign_summary_2019_ticker_trade_date_investor_typ_idx ON public.idx_net_foreign_summary_2019 USING btree (ticker, trade_date DESC, investor_type)` |

## idx_net_foreign_summary_2020

No description has been recorded.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `trade_date` | `date` | No | — | No column description has been recorded. |
| `ticker` | `text` | No | — | No column description has been recorded. |
| `investor_type` | `idx_investor_type` | No | — | No column description has been recorded. |
| `buy_value` | `numeric` | No | — | No column description has been recorded. |
| `sell_value` | `numeric` | No | — | No column description has been recorded. |
| `net_value` | `numeric` | Yes | — | No column description has been recorded. |
| `buy_freq` | `bigint` | No | — | No column description has been recorded. |
| `sell_freq` | `bigint` | No | — | No column description has been recorded. |
| `updated_at` | `timestamp with time zone` | No | `now()` | No column description has been recorded. |
| `is_anomaly` | `boolean` | No | `false` | No column description has been recorded. |
| `remark` | `text` | Yes | — | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `IDX_Net_Foreign_Summary_ticker_check` | Check | `CHECK (ticker ~ '^[A-Z]{4}$'::text)` |
| `idx_net_foreign_summary_2020_pkey` | Primary key | `PRIMARY KEY (trade_date, ticker, investor_type)` |

### Indexes

| Name | Definition |
|---|---|
| `idx_net_foreign_summary_2020_pkey` | `CREATE UNIQUE INDEX idx_net_foreign_summary_2020_pkey ON public.idx_net_foreign_summary_2020 USING btree (trade_date, ticker, investor_type)` |
| `idx_net_foreign_summary_2020_ticker_trade_date_investor_typ_idx` | `CREATE INDEX idx_net_foreign_summary_2020_ticker_trade_date_investor_typ_idx ON public.idx_net_foreign_summary_2020 USING btree (ticker, trade_date DESC, investor_type)` |

## idx_net_foreign_summary_2021

No description has been recorded.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `trade_date` | `date` | No | — | No column description has been recorded. |
| `ticker` | `text` | No | — | No column description has been recorded. |
| `investor_type` | `idx_investor_type` | No | — | No column description has been recorded. |
| `buy_value` | `numeric` | No | — | No column description has been recorded. |
| `sell_value` | `numeric` | No | — | No column description has been recorded. |
| `net_value` | `numeric` | Yes | — | No column description has been recorded. |
| `buy_freq` | `bigint` | No | — | No column description has been recorded. |
| `sell_freq` | `bigint` | No | — | No column description has been recorded. |
| `updated_at` | `timestamp with time zone` | No | `now()` | No column description has been recorded. |
| `is_anomaly` | `boolean` | No | `false` | No column description has been recorded. |
| `remark` | `text` | Yes | — | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `IDX_Net_Foreign_Summary_ticker_check` | Check | `CHECK (ticker ~ '^[A-Z]{4}$'::text)` |
| `idx_net_foreign_summary_2021_pkey` | Primary key | `PRIMARY KEY (trade_date, ticker, investor_type)` |

### Indexes

| Name | Definition |
|---|---|
| `idx_net_foreign_summary_2021_pkey` | `CREATE UNIQUE INDEX idx_net_foreign_summary_2021_pkey ON public.idx_net_foreign_summary_2021 USING btree (trade_date, ticker, investor_type)` |
| `idx_net_foreign_summary_2021_ticker_trade_date_investor_typ_idx` | `CREATE INDEX idx_net_foreign_summary_2021_ticker_trade_date_investor_typ_idx ON public.idx_net_foreign_summary_2021 USING btree (ticker, trade_date DESC, investor_type)` |

## idx_net_foreign_summary_2022

No description has been recorded.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `trade_date` | `date` | No | — | No column description has been recorded. |
| `ticker` | `text` | No | — | No column description has been recorded. |
| `investor_type` | `idx_investor_type` | No | — | No column description has been recorded. |
| `buy_value` | `numeric` | No | — | No column description has been recorded. |
| `sell_value` | `numeric` | No | — | No column description has been recorded. |
| `net_value` | `numeric` | Yes | — | No column description has been recorded. |
| `buy_freq` | `bigint` | No | — | No column description has been recorded. |
| `sell_freq` | `bigint` | No | — | No column description has been recorded. |
| `updated_at` | `timestamp with time zone` | No | `now()` | No column description has been recorded. |
| `is_anomaly` | `boolean` | No | `false` | No column description has been recorded. |
| `remark` | `text` | Yes | — | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `IDX_Net_Foreign_Summary_ticker_check` | Check | `CHECK (ticker ~ '^[A-Z]{4}$'::text)` |
| `idx_net_foreign_summary_2022_pkey` | Primary key | `PRIMARY KEY (trade_date, ticker, investor_type)` |

### Indexes

| Name | Definition |
|---|---|
| `idx_net_foreign_summary_2022_pkey` | `CREATE UNIQUE INDEX idx_net_foreign_summary_2022_pkey ON public.idx_net_foreign_summary_2022 USING btree (trade_date, ticker, investor_type)` |
| `idx_net_foreign_summary_2022_ticker_trade_date_investor_typ_idx` | `CREATE INDEX idx_net_foreign_summary_2022_ticker_trade_date_investor_typ_idx ON public.idx_net_foreign_summary_2022 USING btree (ticker, trade_date DESC, investor_type)` |

## idx_net_foreign_summary_2023

No description has been recorded.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `trade_date` | `date` | No | — | No column description has been recorded. |
| `ticker` | `text` | No | — | No column description has been recorded. |
| `investor_type` | `idx_investor_type` | No | — | No column description has been recorded. |
| `buy_value` | `numeric` | No | — | No column description has been recorded. |
| `sell_value` | `numeric` | No | — | No column description has been recorded. |
| `net_value` | `numeric` | Yes | — | No column description has been recorded. |
| `buy_freq` | `bigint` | No | — | No column description has been recorded. |
| `sell_freq` | `bigint` | No | — | No column description has been recorded. |
| `updated_at` | `timestamp with time zone` | No | `now()` | No column description has been recorded. |
| `is_anomaly` | `boolean` | No | `false` | No column description has been recorded. |
| `remark` | `text` | Yes | — | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `IDX_Net_Foreign_Summary_ticker_check` | Check | `CHECK (ticker ~ '^[A-Z]{4}$'::text)` |
| `idx_net_foreign_summary_2023_pkey` | Primary key | `PRIMARY KEY (trade_date, ticker, investor_type)` |

### Indexes

| Name | Definition |
|---|---|
| `idx_net_foreign_summary_2023_pkey` | `CREATE UNIQUE INDEX idx_net_foreign_summary_2023_pkey ON public.idx_net_foreign_summary_2023 USING btree (trade_date, ticker, investor_type)` |
| `idx_net_foreign_summary_2023_ticker_trade_date_investor_typ_idx` | `CREATE INDEX idx_net_foreign_summary_2023_ticker_trade_date_investor_typ_idx ON public.idx_net_foreign_summary_2023 USING btree (ticker, trade_date DESC, investor_type)` |

## idx_net_foreign_summary_2024

No description has been recorded.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `trade_date` | `date` | No | — | No column description has been recorded. |
| `ticker` | `text` | No | — | No column description has been recorded. |
| `investor_type` | `idx_investor_type` | No | — | No column description has been recorded. |
| `buy_value` | `numeric` | No | — | No column description has been recorded. |
| `sell_value` | `numeric` | No | — | No column description has been recorded. |
| `net_value` | `numeric` | Yes | — | No column description has been recorded. |
| `buy_freq` | `bigint` | No | — | No column description has been recorded. |
| `sell_freq` | `bigint` | No | — | No column description has been recorded. |
| `updated_at` | `timestamp with time zone` | No | `now()` | No column description has been recorded. |
| `is_anomaly` | `boolean` | No | `false` | No column description has been recorded. |
| `remark` | `text` | Yes | — | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `IDX_Net_Foreign_Summary_ticker_check` | Check | `CHECK (ticker ~ '^[A-Z]{4}$'::text)` |
| `idx_net_foreign_summary_2024_pkey` | Primary key | `PRIMARY KEY (trade_date, ticker, investor_type)` |

### Indexes

| Name | Definition |
|---|---|
| `idx_net_foreign_summary_2024_pkey` | `CREATE UNIQUE INDEX idx_net_foreign_summary_2024_pkey ON public.idx_net_foreign_summary_2024 USING btree (trade_date, ticker, investor_type)` |
| `idx_net_foreign_summary_2024_ticker_trade_date_investor_typ_idx` | `CREATE INDEX idx_net_foreign_summary_2024_ticker_trade_date_investor_typ_idx ON public.idx_net_foreign_summary_2024 USING btree (ticker, trade_date DESC, investor_type)` |

## idx_net_foreign_summary_2025

No description has been recorded.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `trade_date` | `date` | No | — | No column description has been recorded. |
| `ticker` | `text` | No | — | No column description has been recorded. |
| `investor_type` | `idx_investor_type` | No | — | No column description has been recorded. |
| `buy_value` | `numeric` | No | — | No column description has been recorded. |
| `sell_value` | `numeric` | No | — | No column description has been recorded. |
| `net_value` | `numeric` | Yes | — | No column description has been recorded. |
| `buy_freq` | `bigint` | No | — | No column description has been recorded. |
| `sell_freq` | `bigint` | No | — | No column description has been recorded. |
| `updated_at` | `timestamp with time zone` | No | `now()` | No column description has been recorded. |
| `is_anomaly` | `boolean` | No | `false` | No column description has been recorded. |
| `remark` | `text` | Yes | — | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `IDX_Net_Foreign_Summary_ticker_check` | Check | `CHECK (ticker ~ '^[A-Z]{4}$'::text)` |
| `idx_net_foreign_summary_2025_pkey` | Primary key | `PRIMARY KEY (trade_date, ticker, investor_type)` |

### Indexes

| Name | Definition |
|---|---|
| `idx_net_foreign_summary_2025_pkey` | `CREATE UNIQUE INDEX idx_net_foreign_summary_2025_pkey ON public.idx_net_foreign_summary_2025 USING btree (trade_date, ticker, investor_type)` |
| `idx_net_foreign_summary_2025_ticker_trade_date_investor_typ_idx` | `CREATE INDEX idx_net_foreign_summary_2025_ticker_trade_date_investor_typ_idx ON public.idx_net_foreign_summary_2025 USING btree (ticker, trade_date DESC, investor_type)` |

## idx_net_foreign_summary_2026

No description has been recorded.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `trade_date` | `date` | No | — | No column description has been recorded. |
| `ticker` | `text` | No | — | No column description has been recorded. |
| `investor_type` | `idx_investor_type` | No | — | No column description has been recorded. |
| `buy_value` | `numeric` | No | — | No column description has been recorded. |
| `sell_value` | `numeric` | No | — | No column description has been recorded. |
| `net_value` | `numeric` | Yes | — | No column description has been recorded. |
| `buy_freq` | `bigint` | No | — | No column description has been recorded. |
| `sell_freq` | `bigint` | No | — | No column description has been recorded. |
| `updated_at` | `timestamp with time zone` | No | `now()` | No column description has been recorded. |
| `is_anomaly` | `boolean` | No | `false` | No column description has been recorded. |
| `remark` | `text` | Yes | — | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `IDX_Net_Foreign_Summary_ticker_check` | Check | `CHECK (ticker ~ '^[A-Z]{4}$'::text)` |
| `idx_net_foreign_summary_2026_pkey` | Primary key | `PRIMARY KEY (trade_date, ticker, investor_type)` |

### Indexes

| Name | Definition |
|---|---|
| `idx_net_foreign_summary_2026_pkey` | `CREATE UNIQUE INDEX idx_net_foreign_summary_2026_pkey ON public.idx_net_foreign_summary_2026 USING btree (trade_date, ticker, investor_type)` |
| `idx_net_foreign_summary_2026_ticker_trade_date_investor_typ_idx` | `CREATE INDEX idx_net_foreign_summary_2026_ticker_trade_date_investor_typ_idx ON public.idx_net_foreign_summary_2026 USING btree (ticker, trade_date DESC, investor_type)` |

## idx_net_foreign_summary_2027

No description has been recorded.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `trade_date` | `date` | No | — | No column description has been recorded. |
| `ticker` | `text` | No | — | No column description has been recorded. |
| `investor_type` | `idx_investor_type` | No | — | No column description has been recorded. |
| `buy_value` | `numeric` | No | — | No column description has been recorded. |
| `sell_value` | `numeric` | No | — | No column description has been recorded. |
| `net_value` | `numeric` | Yes | — | No column description has been recorded. |
| `buy_freq` | `bigint` | No | — | No column description has been recorded. |
| `sell_freq` | `bigint` | No | — | No column description has been recorded. |
| `updated_at` | `timestamp with time zone` | No | `now()` | No column description has been recorded. |
| `is_anomaly` | `boolean` | No | `false` | No column description has been recorded. |
| `remark` | `text` | Yes | — | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `IDX_Net_Foreign_Summary_ticker_check` | Check | `CHECK (ticker ~ '^[A-Z]{4}$'::text)` |
| `idx_net_foreign_summary_2027_pkey` | Primary key | `PRIMARY KEY (trade_date, ticker, investor_type)` |

### Indexes

| Name | Definition |
|---|---|
| `idx_net_foreign_summary_2027_pkey` | `CREATE UNIQUE INDEX idx_net_foreign_summary_2027_pkey ON public.idx_net_foreign_summary_2027 USING btree (trade_date, ticker, investor_type)` |
| `idx_net_foreign_summary_2027_ticker_trade_date_investor_typ_idx` | `CREATE INDEX idx_net_foreign_summary_2027_ticker_trade_date_investor_typ_idx ON public.idx_net_foreign_summary_2027 USING btree (ticker, trade_date DESC, investor_type)` |

## idx_stockbit_backfill_status

No description has been recorded.

### Columns

| Column | Type | Nullable | Default | Definition |
|---|---|---|---|---|
| `trade_date` | `date` | No | — | No column description has been recorded. |
| `backfill_year` | `integer` | No | — | No column description has been recorded. |
| `state` | `text` | No | — | No column description has been recorded. |
| `expected_filters` | `integer` | No | `0` | No column description has been recorded. |
| `completed_filters` | `integer` | No | `0` | No column description has been recorded. |
| `detail_rows` | `bigint` | No | `0` | No column description has been recorded. |
| `summary_rows` | `bigint` | No | `0` | No column description has been recorded. |
| `request_count` | `bigint` | No | `0` | No column description has been recorded. |
| `attempt_count` | `integer` | No | `0` | No column description has been recorded. |
| `error_class` | `text` | Yes | — | No column description has been recorded. |
| `error_message` | `text` | Yes | — | No column description has been recorded. |
| `started_at` | `timestamp with time zone` | Yes | — | No column description has been recorded. |
| `heartbeat_at` | `timestamp with time zone` | No | `now()` | No column description has been recorded. |
| `completed_at` | `timestamp with time zone` | Yes | — | No column description has been recorded. |
| `updated_at` | `timestamp with time zone` | No | `now()` | No column description has been recorded. |

### Constraints

| Name | Type | Definition |
|---|---|---|
| `idx_stockbit_backfill_status_attempt_count_check` | Check | `CHECK (attempt_count >= 0)` |
| `idx_stockbit_backfill_status_backfill_year_check` | Check | `CHECK (backfill_year >= 2016 AND backfill_year <= 2100)` |
| `idx_stockbit_backfill_status_completed_filters_check` | Check | `CHECK (completed_filters >= 0)` |
| `idx_stockbit_backfill_status_detail_rows_check` | Check | `CHECK (detail_rows >= 0)` |
| `idx_stockbit_backfill_status_expected_filters_check` | Check | `CHECK (expected_filters >= 0)` |
| `idx_stockbit_backfill_status_request_count_check` | Check | `CHECK (request_count >= 0)` |
| `idx_stockbit_backfill_status_state_check` | Check | `CHECK (state = ANY (ARRAY['queued'::text, 'fetching'::text, 'uploading'::text, 'completed'::text, 'failed_fetch'::text, 'failed_reconciliation'::text, 'failed_database'::text, 'blocked_auth'::text, 'blocked_storage'::text]))` |
| `idx_stockbit_backfill_status_summary_rows_check` | Check | `CHECK (summary_rows >= 0)` |
| `idx_stockbit_backfill_status_pkey` | Primary key | `PRIMARY KEY (trade_date)` |

### Indexes

| Name | Definition |
|---|---|
| `idx_stockbit_backfill_state_date` | `CREATE INDEX idx_stockbit_backfill_state_date ON public.idx_stockbit_backfill_status USING btree (state, trade_date)` |
| `idx_stockbit_backfill_status_pkey` | `CREATE UNIQUE INDEX idx_stockbit_backfill_status_pkey ON public.idx_stockbit_backfill_status USING btree (trade_date)` |

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
