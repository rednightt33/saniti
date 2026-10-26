# Database catalogs

The live PostgreSQL schema is the authority for physical types, constraints, and indexes. These catalogs record **meaning and provenance** so a human or AI can interpret the schema without guessing from names. Use exact case-sensitive PostgreSQL identifiers.

## Catalog roles and initial scope

| Object | Purpose | Grain |
|---|---|---|
| `Table_Catalog` | Purpose, row grain, primary key, data source, writer paths, update rule, and related routines | One row per approved physical table |
| `Column_Catalog` | Physical column inventory, value meaning, null rule, unit, and evidence status | One row per physical column of a registered table |
| `Feature_Catalog` | Versioned formulas, semantic usage, availability, point-in-time safety, null rules, and dependencies for validated Feature columns | One row per Feature table, column, and semantic version |
| `Feature_Relationship_Catalog` | Versioned safe joins, cardinality, required preaggregation, and output grain between Features | One row per Feature-table pair and version |
| `Tool_Catalog` | Versioned generic tool schemas, activation, handler, and advertised database/worker/LLM-facing limits | One row per tool and version |
| `AI_table_catalog` | Compact master list for exactly the seven AI-approved market-data tables | One row per approved table |
| `AI_column_catalog` | AI-facing column semantics copied from reviewed legacy catalogs | One row per column of an AI-approved table |
| `AI_catalog_relationships` | Safe join and output-grain contracts among AI-approved tables | One row per relationship contract |
| `AI_calculation_catalog` | Active Feature formula and analytical-use contracts | One row per active Feature column |
| `AI_data_coverage` | Actual raw-source coverage and clearly labelled source-derived Feature expectations | One row per dataset or dataset/entity pair |
| `Database_Table_Status` | Operational freshness and last-change tracking | One row per public table; **not** a semantic catalog |

The initial `Table_Catalog` scope was exactly these eleven existing tables:
`IDX_Stock_Universe`, `Universe_Equity_Description`, `IDX_Broker_Profile`,
`IDX_Broker_Summary`, `Price_Stock_Indonesia_IDX`, `Feature_01_Stock_Daily`,
`Feature_Catalog`, `Monitoring_Price_ALL`, `stockbit_broker_summary_load_log`,
`Telegram_Command_Log`, and `Telegram_Notification_Log`.
`Database_Table_Status`, the deleted `IDX_Broker_Summary_Data_Quality`, and the two new catalog tables themselves are not initial catalog entries.

The scope subsequently added `Feature_Calculation_Queue`, `Feature_Status`, and `Feature_Calculation_Log`. They are `System` control tables, not calculated Feature-output tables; they do not require formula entries in `Feature_Catalog`. The price trigger and worker implementation are recorded in their `Table_Catalog.related_functions` and `source_code_paths`. The Railway worker deployment and one live re-ingestion succeeded; catalog entries still marked `PARTIAL` retain that evidence grade until separately reviewed and promoted.

`Feature_02_Broker_Rolling` is the approved, validated Investor-Type v2 output table. It has one `Table_Catalog` entry, 38 verified `Column_Catalog` entries, and 38 active `Feature_Catalog` `v2` definitions. The 38 historical v1 definitions remain inactive. `investor_type` is copied from the broker-summary row, not inferred from broker domicile. Its board/type partitions and ticker transaction-date calendar are explained in `FEATURE_02_BROKER_ROLLING_V2.md`.

`Feature_03_Stock_Broker_Daily` is approved and validated at its existing date/ticker/board grain. Its 24 active `Feature_Catalog` `v2` definitions use source `Investor Type` for the Domestic/Foreign net-flow columns. Broker breadth, rankings, HHI, and current broker-profile classification fields first aggregate both Investor Types per broker. Regular, Nego, and Tunai never mix. Safe join contracts are versioned in `Feature_Relationship_Catalog`. See `FEATURE_03_STOCK_BROKER_DAILY.md`.

The market-AI foundation adds `Feature_Relationship_Catalog`, `Tool_Catalog`, four analysis audit tables, and three Golden Test tables. Release 2 adds `Analytics_Dataset_Snapshot` and `Analytics_Job`. The AI-facing catalog migration then adds five registered `AI_*` tables, bringing the live scope to 32 registered tables, 580 registered physical columns, and 35 public tables including the three explicit catalog/status exclusions. `Tool_Catalog` exposes deterministic `route_analysis`, one generic query-sandbox surface, and one generic statistical-validation surface rather than a tool per ticker or investment question. Feature 3 v2 clearly separates source investor identity from current broker-profile metadata.

`Tool_Catalog` also holds nine `ORCHESTRATOR` rows for `market-ai-orc`: `get_system_capabilities`, `discover_catalog`, `get_catalog_details`, `read_catalog_rows`, `preview_table_rows`, `request_data` and `get_dataset_manifest` (both executed by `market-sql-governor`), and `run_python_analysis` and `get_analysis_result` (executed by `market-python-sandbox`). They are registered with `is_active = false` so market-ai-backend, which lists every active `META`/`DISCOVERY`/`QUALITY` row to its model, does not advertise tools it cannot execute. Their runtime activation is owned by the market-ai-orc registry and recorded in `tool_specific_limits.runtime_service = 'market-ai-orc'`. Since market-ai-backend was deactivated on 2026-09-25, no running service reads `is_active`. The flags are left as they were, so the backend could be restored unchanged, and they do not describe what market-ai-orc currently exposes. The function `public.ai_preview_table_rows(text)` is listed in `related_functions` of the seven tables it serves. Migration `20260929_001` (applied on dev 2026-09-29) adds the four Multi-Angle Research tools `check_research_feasibility`, `start_research_run`, `run_research_code` and `complete_research_run` the same way (inactive, `runtime_service = 'market-ai-orc'`) and notes on `check_data_feasibility` `v3` that multi-angle research replaces it; `AI_research_catalog` is unchanged (see `MULTI_ANGLE_RESEARCH.md` §8). Migration `20260930_002` (applied on dev 2026-09-29) adds inactive `v2` rows of `check_research_feasibility` (each angle's design checked before a plan, M38), `run_research_code` (cross-request forward return, S15) and `complete_research_run` (early finalize answered with the missing angles, M36), each copying its `v1` row plus `replaces_version`, and `get_research_library` `v1`; the latest version is read with `ORDER BY length(version) DESC, version DESC`. Migration `20260930_003` (applied on dev 2026-09-30) adds an inactive `check_research_feasibility` `v3` (the scope check `SCOPE_WIDER_THAN_QUESTION` and the angle field `broad_scope`, G13), copying `v2` plus `replaces_version`.

`AI_research_library` (migration `20260930_001`, applied on dev 2026-09-29; `MULTI_ANGLE_FIX_PLAN.md` item 2) is the model-facing description of the eight Multi-Angle Research methods the sandbox engines compute: one row per method and engine version with its family, question shape, input roles, parameters, data requirements, sample unit, secondary checks, interpretation, misuse warning and example question. Its content is generated from `apps/market-python-sandbox/app/research_library.py` (byte-identical in market-ai-orc) and bound to it by `library_sha256`; market-ai-orc serves the active rows through `get_research_library` and enables multi-angle research only when the table, the sandbox capability and its own copy carry the same hash. The table describes; the engines and `research_engines.decide` enforce, and a new row does not create a method. It has one `Table_Catalog` row and 20 `Column_Catalog` rows (`VERIFIED`: the definitions are the generating code's own); SELECT only to `market_ai_catalog_reader`, no SQL Governor access. A change is a new forward migration regenerated from the code, never an edit by hand.

Migration `20260926_001` (applied to `dev` on 2026-09-26) registers the seven tools of the DataNeed flow, which market-ai-orc exposes only with `AI_ENABLE_DATANEED`. All seven are `is_active = false`, with `runtime_commit = "daa05cc"`:
- `submit_data_need_spec`;
- `prepare_data_bundle`;
- `open_analysis_session`;
- `run_python`;
- `inspect_session`;
- `get_session_output`;
- `complete_analysis`, registered as version `orc-v1`. market-ai-backend's retired `complete_analysis` v1 is an unrelated tool of the same name; its row, which is still `is_active` for that deactivated service, is unchanged.

The latest market-ai-orc versions of `create_analysis_spec`, `prepare_analysis_data`, `run_python_analysis`, `get_analysis_result` and `get_dataset_manifest` carry `tool_specific_limits.dataneed_flow`, naming the DataNeed tool that replaces them while the flag is on.

Migration `20260926_002` (applied to `dev` on 2026-09-26) registers `submit_data_need_spec` v2 (`is_active = false`, `runtime_commit = "be59c68"`). Its `research_governance` adds the `condition`, `outcome` and `baseline` declarations, and the tool refuses a RESEARCH data need without an approved Research Plan when `AI_REQUIRE_RESEARCH_PLAN_CONFIRMATION` is on. v1 carries `superseded_by = "v2"`. `run_python` v1 records the `saniti.period_return` helper and its flag `AI_ENABLE_STANDARD_PERIOD_RETURN` in `tool_specific_limits.standard_period_return`. The same migration lets `AI_research_run_audit` record status `AWAITING_CONFIRMATION` and response type `RESEARCH_PLAN_CONFIRMATION`.

The legacy `Table_Catalog`, `Column_Catalog`, `Feature_Catalog`, and relationship catalog remain authoritative and are not replaced. The AI-facing layer contains seven table rows, 138 column rows, five relationship rows, and 91 active calculation rows. Only `AI_data_coverage` is automated. Its job scans raw price and Broker Summary for actual date coverage, uses `Feature_Status` only to confirm Feature 01 pipeline completion, and derives expected Feature 02/03 coverage from Broker Summary without scanning the Feature tables themselves.

Migration `20260925_003` (applied to `dev` on 2026-09-26) adds the point-in-time contract the DataNeed flow reads through the SQL Governor's catalog contract:
- `AI_catalog_relationships.supported_join_semantics` is the subset of `CURRENT_STATE`, `EXACT_DATE`, `AS_OF` and `EFFECTIVE_DATED` a DataNeedSpec may request; an empty array means the DataNeed planner cannot use the relationship. `left_time_column`/`right_time_column` name the time columns of `EXACT_DATE` and `AS_OF` joins, and `effective_from_column`/`effective_to_column` the validity interval of `EFFECTIVE_DATED` rows. Check constraints refuse unknown semantics and temporal semantics without their columns.
- The two current-state reference relationships (`IDX_Stock_Universe` → price, `IDX_Broker_Profile` → Broker Summary) support `CURRENT_STATE` only: a historical question joined to them uses today's classification, and the sandbox reports that as `HISTORICAL_REFERENCE_USES_CURRENT_STATE`. The three same-date relationships support `EXACT_DATE`. No relationship is `AS_OF` or `EFFECTIVE_DATED`, because no catalog table keeps a history of reference values yet.
- `AI_column_catalog.resample_aggregation` (`FIRST`, `LAST`, `MAX`, `MIN`, `SUM`) is the exact rule for aggregating a column to a coarser frequency. It is `NULL` for every column: no rule is established, so resampling is never pushed down and the analysis session resamples source-frequency data itself.
- The six columns are documented in `Column_Catalog` as `PARTIAL`.

## Complete public-table documentation map

Every current public table is listed here so GitHub readers can find its semantic
or physical documentation. `DATABASE_SCHEMA.md` remains the exhaustive generated
column/constraint/index reference for every row below.

| Table | Purpose | Additional semantic/operational guide |
|---|---|---|
| `Analysis_Evidence` | Compact reproducible support for material AI claims | `apps/market-ai-backend/README.md` |
| `Analysis_Model_Call` | Per-provider-call usage, tool exposure, decision summary, and temporary reasoning audit | `ANALYSIS_MODEL_CALL_AUDIT.md` |
| `Analysis_Request` | Durable request lifecycle, cumulative usage, result, and version snapshot | `apps/market-ai-backend/README.md` |
| `Analysis_Step_Log` | Tool/query/compaction execution audit | `apps/market-ai-backend/README.md` |
| `AI_calculation_catalog` | AI-facing active Feature calculation contracts | This document and `apps/ai-data-coverage/README.md` |
| `AI_catalog_relationships` | AI-facing safe join and output-grain contracts | This document |
| `AI_column_catalog` | AI-facing semantics for the seven approved tables | This document |
| `AI_data_coverage` | Actual source coverage and labelled derived expectations | `apps/ai-data-coverage/README.md` |
| `AI_research_run_audit` | One INSERT-only audit row per market-ai-orc run: question, final answer, evidence label, gate outcome, and experiments | `apps/market-ai-orc/README.md` (Research run audit) |
| `AI_table_catalog` | AI-facing seven-table master catalog | This document |
| `Analytics_Dataset_Snapshot` | Immutable bounded raw/Feature input metadata and private-object retention | `apps/market-ai-backend/README.md` |
| `Analytics_Job` | Class-separated query/statistical queue, lease, resource contract, compact result, and failure audit | `apps/market-ai-backend/README.md` |
| `Column_Catalog` | Physical and semantic column inventory | This document |
| `Database_Table_Status` | Operational table freshness/change status | This document; deliberately not a semantic-catalog target |
| `Feature_01_Stock_Daily` | Daily price-derived stock features | `FEATURE_01_AUTOMATION_PLAN.md` |
| `Feature_02_Broker_Rolling` | Canonical broker rolling features by stock/broker/Investor Type/board/date | `FEATURE_02_BROKER_ROLLING_V2.md` |
| `Feature_03_Stock_Broker_Daily` | Stock/day/board broker breadth and flow features | `FEATURE_03_STOCK_BROKER_DAILY.md` |
| `Feature_04_Technical_Indicator` | Cross-asset Daily close, technical indicators, candlestick codes, inside bars and Pine SMI/swing state | `FEATURE04_COLUMN_DEFINITIONS.md` |
| `feature04_backfill_log` | Atomic per-run/ticker historical-load metadata and resume fingerprints | `FEATURE04_TECHNICAL_INDICATOR.md` |
| `Feature_Calculation_Log` | Completed Feature 01 worker attempts and retries | `apps/feature-01-worker/README.md` |
| `Feature_Calculation_Queue` | Durable changed-price work items for Feature 01 | `apps/feature-01-worker/README.md` |
| `Feature_Catalog` | Versioned formula and analytical-usage authority for Feature columns | This document |
| `Feature_Relationship_Catalog` | Safe cross-Feature join/grain contracts | This document |
| `Feature_Status` | Current Feature 01 refresh state per ticker | `apps/feature-01-worker/README.md` |
| `Golden_Analysis_Test` | Versioned deterministic analytical expectations | `AI_ANALYST_IMPLEMENTATION_PLAN.md` |
| `Golden_Analysis_Test_Result` | Per-test observed acceptance result | `AI_ANALYST_IMPLEMENTATION_PLAN.md` |
| `Golden_Analysis_Test_Run` | One complete golden-suite execution | `AI_ANALYST_IMPLEMENTATION_PLAN.md` |
| `IDX_Broker_Profile` | Broker identity, domicile type, and usage classification | This document and `DATABASE_SCHEMA.md` |
| `IDX_Broker_Summary` | Daily broker activity by stock, investor type, and board | `FEATURE_02_BROKER_ROLLING.md` |
| `IDX_Stock_Universe` | Current IDX security universe and classifications | This document and `DATABASE_SCHEMA.md` |
| `Monitoring_Price_ALL` | Per-execution price-ingestion monitoring | `apps/idx-price-cron/README.md` |
| `Price_Stock_Indonesia_IDX` | TradingView daily OHLCV source rows | `apps/idx-price-cron/README.md` |
| `Table_Catalog` | Table meaning, grain, provenance, update, and routine registry | This document |
| `Telegram_Command_Log` | Inbound command audit and duplicate prevention | `apps/telegram-trigger/README.md` |
| `Telegram_Notification_Log` | Outbound send/edit state and logical delivery deduplication | `apps/telegram-monitor/README.md` |
| `Tool_Catalog` | Generic AI tool contracts and advertised limits | `AI_ANALYST_IMPLEMENTATION_PLAN.md` |
| `Universe_Equity_Description` | Issuer descriptions and sector/industry classifications | This document and `DATABASE_SCHEMA.md` |
| `stockbit_broker_summary_load_log` | Per-date Stockbit load progress/retry history | `apps/stockbit-broker-backfill/README.md` |

`Feature_04_Technical_Indicator` has 57 physical columns and 57 active v4 definitions: four identity fields, direct source `close`, the unchanged indicators/patterns, Pine SMI/swing state, and calculation metadata. It contains 844 equity tickers / 1,318,633 Daily rows and 24 bonds tickers / 60,409 price rows. `break_swing_high` remains INTEGER 1/0; indicator formulas remain engine v3. The 42 v1 and 46 v2 definitions remain as inactive history under the renamed physical table reference. Full definitions are in `FEATURE04_COLUMN_DEFINITIONS.md`; rename/close evidence is in `verification/feature04/RENAME_CLOSE.md`, cross-asset evidence in `verification/feature04/BONDS.md`, and SMI evidence in `verification/feature04/SMI_ALL_TICKERS.md`. The Feature01 exact-date relationship is safe only after filtering `asset_type='equity'`. `feature04_backfill_log` records atomic output/audit commits without copying source rows. Exposed to the AI since migration `20261020_001` (EXEC-ONBOARD-1): `AI_table_catalog`/`AI_column_catalog` rows (Pine state and calculation bookkeeping columns `ai_allowed = false`), one `AI_calculation_catalog` row per active definition, relationships, preview and SELECT for `market_ai_sql_reader`. TradingView numerical parity and point-in-time training eligibility remain NOT VERIFIED. The catalog validator uses the standard governed Feature-table naming rule.

Feature04 automation adds `Feature04_Calculation_Queue`, `Feature04_Column_Status`,
`Feature04_Calculation_Log`, `Monitoring_Feature04`, `Monitoring_Feature04_Ticker`,
`Feature04_Retry_Request`, and `Feature04_Notification_Outbox`. These are operational
state and audit tables, not model features. A committed price trigger coalesces work by
ticker; `feature-04-worker` owns calculation/status writes. Telegram can create only
failure-backed retry requests. Each retry records the editable Telegram acknowledgement and
derives its start from the latest configured five final sessions. The Feature04 outbox is
gated by successful price-message delivery for automatic runs and by acknowledgement
recording for retries. Scheduled DAILY/RECOVERY results share a market/date delivery key.
Their physical definitions and keys are generated in
`DATABASE_SCHEMA.md`; behavior is specified in `FEATURE04_TECHNICAL_INDICATOR.md`.

`Feature04_Calculation_State` stores recent versioned calculation checkpoints. Its grain is
asset type, ticker, Daily timeframe and checkpoint date. `Equity_Market_Schedule` and
`Fixed_Income_Market_Schedule.correction_lookback_sessions` control finality and the normal
five-session correction boundary. Checkpoints are invalidated on or after a material source
change and replaced only with a successful suffix transaction.
The live retention is seven sessions per instrument (6,076 rows across 868 instruments):
five correction sessions plus two boundary snapshots. Candlestick state uses one canonical
15-bar TA-Lib window so full repair and suffix execution produce the same integer flags.

Fixed-income ingestion is market-partitioned. `Fixed_Income_Market_Schedule` stores the
current timezone, local close and finality delay for Indonesia and the United States.
`Universe_Fixed_income` stores the exact TradingView symbol and value unit for every
ticker/metric pair. `Price_Fixed_Income` retains the provider bar timestamp, configured
market close, final flag and verification time. Legacy history is marked as completed
session data but has NULL `source_bar_time`; the current jobs populate complete evidence.
Feature04 consumes only final `price`/`1D` rows.

## Field contract

`Table_Catalog` has primary key `(table_schema, table_name)`. `category`, `definition`, and `grain` describe the table. `primary_key_columns` holds the ordered physical key. `source_system` and `source_tables` identify provenance. `source_code_paths` points to supporting repository code/migrations. `update_rule` states when/how rows change. `related_functions` lists table-related PostgreSQL routines. `documentation_status` grades the semantic claim. `readiness_mode`/`readiness_date_column` define live freshness. `observation_date_column`, `data_available_at_column`, `availability_rule`, `point_in_time_status`, and `historical_metadata_method` keep freshness distinct from decision-time and historical-universe validity.

`Column_Catalog` has primary key `(table_schema, table_name, column_name)` and a foreign key to `Table_Catalog`. `ordinal_position`, `data_type`, `is_nullable`, `default_expression`, and `is_primary_key` are synchronized from live PostgreSQL. `definition`, `source_column_or_expression`, `unit`, and `null_rule` explain meaning. `source_code_paths`, `documentation_status`, and timestamps record evidence and maintenance.

`Feature_Catalog` additionally defines `semantic_role`, `allowed_aggregations`, `ranking_interpretation`, filter/group eligibility, decision-time `availability_rule`, `point_in_time_safe`, `historical_metadata_warning`, `analytical_interpretation`, `recommended_use`, `misuse_warning`, `semantic_review_status`, and `validation_evidence`. An active definition must reference a physical column in a VERIFIED Feature table, contain nonblank semantic guidance and evidence, and only one definition version may be active per physical column. `CALCULATION_VERIFIED` means formula and semantics are backed by the listed migration/validator evidence; it does not make the Feature predictive.

`Analysis_Request` records progressive tool exposure, compact results, cumulative provider input/output usage, current and peak active context, compaction count, methodology metadata, and an immutable completed-request version snapshot. `Analysis_Model_Call` records one provider response at a time, including per-call tokens and temporarily retained provider-returned reasoning; see `ANALYSIS_MODEL_CALL_AUDIT.md`. `Analysis_Step_Log` and `Analysis_Evidence` retain compact reproducibility details rather than large raw query results.

`Analytics_Dataset_Snapshot` records exact catalog-approved raw/Feature source specifications, schema, row/byte counts, query hashes, object checksum, readiness date, and deletion deadline. `Analytics_Job.execution_class` selects `QUERY_SANDBOX` or `STATISTICAL_VALIDATION`; class-scoped credentials and claim indexes prevent cross-worker leasing. Neither worker receives PostgreSQL or bucket credentials—only a short-lived URL for the exact leased snapshot. Every session starts with a compact data map and operating handoff; the first `route_analysis` call selects the smallest sufficient execution path.

`documentation_status` means:

- `VERIFIED`: checked against implementation and live schema, or the validated `Feature_Catalog`.
- `PARTIAL`: documented by code, migration, or existing project notes, but not fully verified end-to-end.
- `NEEDS_REVIEW`: meaning is not established. A null `definition` is intentional; AI must not infer one from a name.

`IDX_Broker_Profile.broker_type` is Domestic/Foreign. Its separate `broker_classification` describes observed usage profile: Institutional-heavy, Retail-heavy, Mixed, or Niche. The latter meaning was confirmed by the project owner and the four categories were observed in live data.

## How to read

Start with `Table_Catalog` for row grain and provenance, then `Column_Catalog` for physical and semantic details. For any Feature calculation, follow `Feature_Catalog` for the authoritative formula; the generic column catalog is not a second formula source.

```sql
SELECT table_name, definition, grain, documentation_status
FROM public."Table_Catalog"
WHERE table_schema = 'public'
ORDER BY table_name;

SELECT column_name, data_type, definition, documentation_status
FROM public."Column_Catalog"
WHERE table_schema = 'public' AND table_name = 'Price_Stock_Indonesia_IDX'
ORDER BY ordinal_position;

SELECT feature_column, definition, calculation, analytical_interpretation,
       recommended_use, misuse_warning, semantic_review_status,
       validation_evidence, null_rule
FROM public."Feature_Catalog"
WHERE feature_table = 'Feature_01_Stock_Daily'
  AND version = 'v1' AND is_active
ORDER BY feature_column;

-- Feature 02 validated active definitions:
SELECT feature_column, calculation, minimum_history, null_rule
FROM public."Feature_Catalog"
WHERE feature_table = 'Feature_02_Broker_Rolling'
  AND version = 'v2' AND is_active
ORDER BY feature_column;

-- Feature 03 validated active definitions:
SELECT feature_column, calculation, unit, null_rule
FROM public."Feature_Catalog"
WHERE feature_table = 'Feature_03_Stock_Broker_Daily'
  AND version = 'v2' AND is_active
ORDER BY feature_column;

SELECT tool_name, tool_family, max_output_rows, max_llm_result_rows,
       max_llm_result_bytes, max_llm_result_tokens, is_active
FROM public."Tool_Catalog"
ORDER BY tool_family, tool_name;

SELECT *
FROM public.check_analysis_data_readiness(
  ARRAY['Feature_01_Stock_Daily','Feature_02_Broker_Rolling',
        'Feature_03_Stock_Broker_Daily']
);
```

## Mandatory maintenance for future changes

1. Inspect the live schema and relevant writer script, migration, or source data. Do not promote an inferred definition to `VERIFIED`.
2. Add a **new forward-only migration** under `database/migrations/`. Register a new approved table in `Table_Catalog`; register new or changed columns in `Column_Catalog`. A deleted or renamed target needs a migration that reconciles its catalog entries in the same transaction.
3. For new/changed Feature columns or formulas, add a new semantic version in `Feature_Catalog` and reconcile the generic `Column_Catalog` entry. Populate `analytical_interpretation`, `recommended_use`, `misuse_warning`, `semantic_review_status`, and `validation_evidence` for every row; do not use blank or name-only boilerplate. Run `scripts/audit_feature_catalog_semantics.py`. `Feature_Catalog` remains formula authority.
4. For a new/changed PostgreSQL function, update `Table_Catalog.related_functions` for every registered table it directly serves; record its signature, behavior, and affected tables in the migration and `DATABASE_CHANGELOG.md`. Standalone functions with no registered table have no row-level function catalog in this two-catalog design and must be documented explicitly in the changelog and this guide until a separate Function Catalog is approved.
5. Register or version every safe cross-Feature join in `Feature_Relationship_Catalog`. Register every new/changed AI tool, schema, activation state, and advertised limit in `Tool_Catalog`; runtime configuration remains the actual enforcement layer.
6. Record observation date, actual availability evidence, point-in-time status, and conservative fallback. Never reinterpret current metadata or a backfill timestamp as historical availability.
7. Define expected high-frequency access patterns and run controlled `EXPLAIN (ANALYZE, BUFFERS)` before adding a large Feature index. Result limits do not replace physical scan validation; see `DATABASE_INDEX_ACCEPTANCE.md`.
8. Run `python scripts/sync_database_catalog.py --host <proxy-host> --port <proxy-port>` with `PGDATABASE`, `PGUSER`, and `PGPASSWORD` held only in the process environment. The script reconciles physical column facts, fills previously unknown descriptions from source documentation, and refreshes Feature semantics from the active `Feature_Catalog`; it never overwrites a manually reviewed non-Feature definition. It fails on unregistered/stale tables or columns and missing active Feature definitions. The daily GitHub Action runs this check before schema generation.
9. Run `python scripts/sync_database_schema.py --host <proxy-host> --port <proxy-port>` to refresh `DATABASE_SCHEMA.md`, append `DATABASE_CHANGELOG.md`, verify catalog coverage, and push the documentation/migration commit to `main`. The schema generator uses catalog descriptions for registered tables and columns.

These rules are also mandatory in `AGENTS.md`, `README.md`, and `database/migrations/README.md`. Do not edit an applied migration or commit credentials.

## Applied fixed-income session metadata — 2026-10-20

Migration `20261013_011_verify_fixed_income_sessions.sql` updates the schedule Table_Catalog definition and registers provider_timezone_name/provider_session plus the corrected source_date_mapping definition in Column_Catalog. These describe provider anchors, separately from the economic-market timezone/close. No Feature formula or relationship changes. Applied live and independently read back at18:43 WIB. Operator evidence: `verification/fixed_income_session_repair/README.md`.

## AI exposure of fixed income and Feature 04 — 2026-10-20 (EXEC-ONBOARD-1)

Migration `20261020_001` exposes three objects to the AI catalog: the view `Price_Fixed_Income_Final` (final daily bars
of `Price_Fixed_Income`; the base table stays hidden because the catalog and the SQL Governor have no row filter),
`Universe_Fixed_income` (reference, `instrument_name` marked `entity_name`) and `Feature_04_Technical_Indicator` (the
calculation state columns `ai_allowed = false`). The view has its own `Table_Catalog` / `Column_Catalog` rows (category
`Source`), because `scripts/sync_database_catalog.py` registers base tables only. Feature 04's `AI_calculation_catalog`
rows follow the `20260922_001` pattern (one per active `Feature_Catalog` definition, version `v4`); an indicator or candle
column that holds a formula of `AI_formula_reference` names it in `implementation_ref` as `AI_formula_reference:CALC_nnn`
and in `parameters.formula_reference` with its relation, and market-ai-orc shows it as `stored_in` of that formula. Every
Indonesian meaning written by this change is `DRAFT`. Earlier statements in this file that Feature 04 has no AI
allowlist or permission change describe the state before 2026-10-20.

## AI exposure of Feature 05 and Feature 06 through stock views — 2026-10-23 (EXEC-M204 step 5)

Migration `20261023_004` exposes `Feature_05_Foreign_Domestic_Broker_Detail_Stock` and
`Feature_06_Foreign_Domestic_Stock`. Each view shows its base Feature table for the current IDX stock universe only
(`IDX_Stock_Universe`, `"Security Type" = 'stock'`, 844 of the 4,125 codes in the base tables). The base tables stay
hidden from the AI, as the bond base table is.

The views have their own `Table_Catalog` and `Column_Catalog` rows (14 and 86 columns). `calculated_at` is left out.

`AI_column_catalog` summary rules are derived from the base definitions' `Feature_Catalog.allowed_aggregations`:
- daily flows: SUM over time and across entities;
- cumulative series: LAST, without a sum across entities;
- rolling windows, z-scores, percentiles and ratios: no summary rule.

`AI_calculation_catalog` has one row per column. A column that holds a formula of `AI_formula_reference` names it as
`AI_formula_reference:CALC_nnn` (29 Feature 06 columns).

There are 11 relationships:
- EXACT_DATE: Feature 05 to Feature 06 (ticker, board, date); each view to stock prices and to Feature 01;
- CURRENT_STATE: the stock universe to each view; the broker profile to Feature 05;
- EFFECTIVE_DATED: each view to the universe history; Feature 05 to the broker profile history.

Every Indonesian meaning is left empty (`description_id` NULL; user decision, step 2 item 11 later).

Feature 02 and Feature 03 keep every code; the views' table descriptions say so. Read-back: DATABASE_CHANGELOG.md
2026-10-23.


## INDEX bootstrap and frontend vocabulary — 2026-10-25

The six dedicated *_INDEX tables now contain validated IHSG history (DATABASE_CHANGELOG.md).
F05 INDEX has the original 15 analytical/identity fields after the five coverage columns were removed;
F06 INDEX retains all five coverage fields. Active Feature/physical column metadata is synchronized
for all 255 INDEX columns. Current broker scope is all source symbols, each board, with common
aggregate sessions and a broker-history cumulative baseline independent of index price inception.
Daily updates and new AI exposure remain separate; existing legacy worker routing is unchanged.

`Feature_Vocabulary` is a **Reference** presentation dictionary, not a new numerical Feature.
It has 24 documented physical fields and 391 reviewed rows for F01/02/03/05/06 stock and INDEX
sources. Exact source table/column/language identity separates meanings. Source semantic hashes
reject drift at sync; idempotent updates preserve timestamps for unchanged entries. Formula text
is never executed. Scope stock labels legacy non-INDEX tables, which can contain non-stock raw
symbols. The seven frontend fields and maintenance/query instructions are in FEATURE_VOCABULARY.md.
No Feature_Catalog definitions are required for vocabulary metadata fields; their registration is
Table_Catalog/Column_Catalog. No frontend endpoint, browser credentials or AI tools were added.

## Relationships on the date only and on non-entity keys — 2026-10-25 (EXEC-M216)

Migration `20261025_010` registers six relationships from each exposed stock Feature object to its `_INDEX`
counterpart (`AI_catalog_relationships` 250-255, and `Feature_Relationship_Catalog` on the base tables), EXACT_DATE,
MANY_TO_ONE. The keys are derived, not listed: the primary key columns both tables share, without the entity and the
time column, that hold a common stored value.

| Stock object | Paired with the INDEX row on |
|---|---|
| Feature 01 | the date only |
| Feature 02 | market_board, broker, investor_type, date |
| Feature 03 | market_board, date |
| Feature 04 | timeframe, trade_date (asset_type differs: equity/bonds against index) |
| Feature 05 stock view | broker, investor_type, market_board, trade_date |
| Feature 06 stock view | market_board, trade_date |

Rules (enforced in code, not only described):
- A relationship whose only pair is the time pair has empty `request_key_columns` in the AI catalog and supports
  `EXACT_DATE` / `AS_OF` only (`AI_catalog_relationships_date_only_check`; sandbox and Governor refuse other semantics).
- When a relationship does not pair the entity column of the side it declares "one", that side's data request must fix
  every primary key column the relationship leaves open with `EQ` or one-value `IN` (`ONE_SIDE_NOT_UNIQUE`, sandbox
  `data_need.py`; Governor `extract.py` for a date-only `AS_OF`). For the INDEX tables that is `ticker` (and
  `asset_type` for Feature 04), so a second index never doubles or mixes rows.
- `/v1/query` (the retired `request_data` path) refuses a date-only row join (`DATE_ONLY_JOIN_NOT_SUPPORTED`).
- The same rule covers a future macro or cross-asset series table: a series id in its primary key is fixed by the
  scope; a table with one row per date (no entity column) needs nothing.
