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

`Tool_Catalog` also holds nine `ORCHESTRATOR` rows for `market-ai-orc`: `get_system_capabilities`, `discover_catalog`, `get_catalog_details`, `read_catalog_rows`, `preview_table_rows`, `request_data` and `get_dataset_manifest` (both executed by `market-sql-governor`), and `run_python_analysis` and `get_analysis_result` (executed by `market-python-sandbox`). They are registered with `is_active = false` so market-ai-backend, which lists every active `META`/`DISCOVERY`/`QUALITY` row to its model, does not advertise tools it cannot execute. Their runtime activation is owned by the market-ai-orc registry and recorded in `tool_specific_limits.runtime_service = 'market-ai-orc'`. The function `public.ai_preview_table_rows(text)` is listed in `related_functions` of the seven tables it serves.

The legacy `Table_Catalog`, `Column_Catalog`, `Feature_Catalog`, and relationship catalog remain authoritative and are not replaced. The AI-facing layer contains seven table rows, 138 column rows, five relationship rows, and 91 active calculation rows. Only `AI_data_coverage` is automated. Its job scans raw price and Broker Summary for actual date coverage, uses `Feature_Status` only to confirm Feature 01 pipeline completion, and derives expected Feature 02/03 coverage from Broker Summary without scanning the Feature tables themselves.

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
| `AI_table_catalog` | AI-facing seven-table master catalog | This document |
| `Analytics_Dataset_Snapshot` | Immutable bounded raw/Feature input metadata and private-object retention | `apps/market-ai-backend/README.md` |
| `Analytics_Job` | Class-separated query/statistical queue, lease, resource contract, compact result, and failure audit | `apps/market-ai-backend/README.md` |
| `Column_Catalog` | Physical and semantic column inventory | This document |
| `Database_Table_Status` | Operational table freshness/change status | This document; deliberately not a semantic-catalog target |
| `Feature_01_Stock_Daily` | Daily price-derived stock features | `FEATURE_01_AUTOMATION_PLAN.md` |
| `Feature_02_Broker_Rolling` | Canonical broker rolling features by stock/broker/Investor Type/board/date | `FEATURE_02_BROKER_ROLLING_V2.md` |
| `Feature_03_Stock_Broker_Daily` | Stock/day/board broker breadth and flow features | `FEATURE_03_STOCK_BROKER_DAILY.md` |
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
| `Telegram_Notification_Log` | Outbound notification state and duplicate prevention | `apps/telegram-monitor/README.md` |
| `Tool_Catalog` | Generic AI tool contracts and advertised limits | `AI_ANALYST_IMPLEMENTATION_PLAN.md` |
| `Universe_Equity_Description` | Issuer descriptions and sector/industry classifications | This document and `DATABASE_SCHEMA.md` |
| `stockbit_broker_summary_load_log` | Per-date Stockbit load progress/retry history | `apps/stockbit-broker-backfill/README.md` |

Do not invent active Feature Catalog entries for Feature 04 before that table exists and is validated.

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
