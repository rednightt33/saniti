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
| `Database_Table_Status` | Operational freshness and last-change tracking | One row per public table; **not** a semantic catalog |

The initial `Table_Catalog` scope was exactly these eleven existing tables:
`IDX_Stock_Universe`, `Universe_Equity_Description`, `IDX_Broker_Profile`,
`IDX_Broker_Summary`, `Price_Stock_Indonesia_IDX`, `Feature_01_Stock_Daily`,
`Feature_Catalog`, `Monitoring_Price_ALL`, `stockbit_broker_summary_load_log`,
`Telegram_Command_Log`, and `Telegram_Notification_Log`.
`Database_Table_Status`, the deleted `IDX_Broker_Summary_Data_Quality`, and the two new catalog tables themselves are not initial catalog entries.

The scope subsequently added `Feature_Calculation_Queue`, `Feature_Status`, and `Feature_Calculation_Log`. They are `System` control tables, not calculated Feature-output tables; they do not require formula entries in `Feature_Catalog`. The price trigger and worker implementation are recorded in their `Table_Catalog.related_functions` and `source_code_paths`. The Railway worker deployment and one live re-ingestion succeeded; catalog entries still marked `PARTIAL` retain that evidence grade until separately reviewed and promoted.

`Feature_02_Broker_Rolling` is an approved, validated Feature-output table. It added one `Table_Catalog` entry, 38 `Column_Catalog` entries, and 38 active `Feature_Catalog` `v1` definitions after its full backfill passed validation. Its three board partitions and ticker transaction-date calendar are explained in `FEATURE_02_BROKER_ROLLING.md`.

`Feature_03_Stock_Broker_Daily` is also approved and validated. It adds one table entry, 24 verified column entries, and 24 active `Feature_Catalog` `v1` definitions. Its grain is date, source ticker, and market board; Regular, Nego, and Tunai never mix. Two safe Feature 03 join contracts are registered in `Feature_Relationship_Catalog`. See `FEATURE_03_STOCK_BROKER_DAILY.md`.

The market-AI foundation adds `Feature_Relationship_Catalog`, `Tool_Catalog`, three analysis audit tables, and three Golden Test tables. The current live scope is 24 registered tables and 424 registered physical columns across those tables. `Tool_Catalog` has 17 active core tools and 11 inactive analytics/deferred tools. Inactive tools are metadata only and cannot be invoked. Release 1B registers 15 deterministic golden expectations; the first persisted run passed 15/15. Feature 3 usage metadata explicitly permits board/ticker/date grouping and only type-appropriate aggregations.

Do not invent active Feature Catalog entries for Feature 04 before that table exists and is validated.

## Field contract

`Table_Catalog` has primary key `(table_schema, table_name)`. `category`, `definition`, and `grain` describe the table. `primary_key_columns` holds the ordered physical key. `source_system` and `source_tables` identify provenance. `source_code_paths` points to supporting repository code/migrations. `update_rule` states when/how rows change. `related_functions` lists table-related PostgreSQL routines. `documentation_status` grades the semantic claim. `readiness_mode`/`readiness_date_column` define live freshness. `observation_date_column`, `data_available_at_column`, `availability_rule`, `point_in_time_status`, and `historical_metadata_method` keep freshness distinct from decision-time and historical-universe validity.

`Column_Catalog` has primary key `(table_schema, table_name, column_name)` and a foreign key to `Table_Catalog`. `ordinal_position`, `data_type`, `is_nullable`, `default_expression`, and `is_primary_key` are synchronized from live PostgreSQL. `definition`, `source_column_or_expression`, `unit`, and `null_rule` explain meaning. `source_code_paths`, `documentation_status`, and timestamps record evidence and maintenance.

`Feature_Catalog` additionally defines `semantic_role`, `allowed_aggregations`, `ranking_interpretation`, filter/group eligibility, decision-time `availability_rule`, `point_in_time_safe`, and `historical_metadata_warning`. An active definition must reference a physical column in a VERIFIED Feature table, and only one definition version may be active per physical column.

`Analysis_Request` records progressive tool exposure, compact results, cumulative OpenAI input/output usage, current and peak active context, compaction count, methodology metadata, and an immutable completed-request version snapshot. `Analysis_Step_Log` and `Analysis_Evidence` retain compact reproducibility details rather than large raw query results.

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

SELECT feature_column, definition, calculation, null_rule
FROM public."Feature_Catalog"
WHERE feature_table = 'Feature_01_Stock_Daily'
  AND version = 'v1' AND is_active
ORDER BY feature_column;

-- Feature 02 validated active definitions:
SELECT feature_column, calculation, minimum_history, null_rule
FROM public."Feature_Catalog"
WHERE feature_table = 'Feature_02_Broker_Rolling'
  AND version = 'v1' AND is_active
ORDER BY feature_column;

-- Feature 03 validated active definitions:
SELECT feature_column, calculation, unit, null_rule
FROM public."Feature_Catalog"
WHERE feature_table = 'Feature_03_Stock_Broker_Daily'
  AND version = 'v1' AND is_active
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
3. For new/changed Feature columns or formulas, add a new semantic version in `Feature_Catalog` and reconcile the generic `Column_Catalog` entry. `Feature_Catalog` remains formula authority.
4. For a new/changed PostgreSQL function, update `Table_Catalog.related_functions` for every registered table it directly serves; record its signature, behavior, and affected tables in the migration and `DATABASE_CHANGELOG.md`. Standalone functions with no registered table have no row-level function catalog in this two-catalog design and must be documented explicitly in the changelog and this guide until a separate Function Catalog is approved.
5. Register or version every safe cross-Feature join in `Feature_Relationship_Catalog`. Register every new/changed AI tool, schema, activation state, and advertised limit in `Tool_Catalog`; runtime configuration remains the actual enforcement layer.
6. Record observation date, actual availability evidence, point-in-time status, and conservative fallback. Never reinterpret current metadata or a backfill timestamp as historical availability.
7. Define expected high-frequency access patterns and run controlled `EXPLAIN (ANALYZE, BUFFERS)` before adding a large Feature index. Result limits do not replace physical scan validation; see `DATABASE_INDEX_ACCEPTANCE.md`.
8. Run `python scripts/sync_database_catalog.py --host <proxy-host> --port <proxy-port>` with `PGDATABASE`, `PGUSER`, and `PGPASSWORD` held only in the process environment. The script reconciles physical column facts, fills previously unknown descriptions from source documentation, and refreshes Feature semantics from the active `Feature_Catalog`; it never overwrites a manually reviewed non-Feature definition. It fails on unregistered/stale tables or columns and missing active Feature definitions. The daily GitHub Action runs this check before schema generation.
9. Run `python scripts/sync_database_schema.py --host <proxy-host> --port <proxy-port>` to refresh `DATABASE_SCHEMA.md`, append `DATABASE_CHANGELOG.md`, verify catalog coverage, and push the documentation/migration commit to `main`. The schema generator uses catalog descriptions for registered tables and columns.

These rules are also mandatory in `AGENTS.md`, `README.md`, and `database/migrations/README.md`. Do not edit an applied migration or commit credentials.
