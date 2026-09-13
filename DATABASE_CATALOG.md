# Database catalogs

The live PostgreSQL schema is the authority for physical types, constraints, and indexes. These catalogs record **meaning and provenance** so a human or AI can interpret the schema without guessing from names. Use exact case-sensitive PostgreSQL identifiers.

## Catalog roles and initial scope

| Object | Purpose | Grain |
|---|---|---|
| `Table_Catalog` | Purpose, row grain, primary key, data source, writer paths, update rule, and related routines | One row per approved physical table |
| `Column_Catalog` | Physical column inventory, value meaning, null rule, unit, and evidence status | One row per physical column of a registered table |
| `Feature_Catalog` | Versioned formulas, lookback, minimum history, units, null rules, and dependencies for validated Feature columns | One row per Feature table, column, and semantic version |
| `Database_Table_Status` | Operational freshness and last-change tracking | One row per public table; **not** a semantic catalog |

The initial `Table_Catalog` scope was exactly these eleven existing tables:
`IDX_Stock_Universe`, `Universe_Equity_Description`, `IDX_Broker_Profile`,
`IDX_Broker_Summary`, `Price_Stock_Indonesia_IDX`, `Feature_01_Stock_Daily`,
`Feature_Catalog`, `Monitoring_Price_ALL`, `stockbit_broker_summary_load_log`,
`Telegram_Command_Log`, and `Telegram_Notification_Log`.
`Database_Table_Status`, the deleted `IDX_Broker_Summary_Data_Quality`, and the two new catalog tables themselves are not initial catalog entries.

The current scope adds `Feature_Calculation_Queue`, `Feature_Status`, and `Feature_Calculation_Log`, for 14 registered tables and 202 registered columns. They are `System` control tables, not calculated Feature-output tables; they do not require formula entries in `Feature_Catalog`. Their semantic entries remain `PARTIAL` until the writer and worker are implemented and verified. The 29 active Feature 01 formula definitions are unchanged.

The only existing Feature table is Feature 01. `Feature_Catalog` already has active `v1` definitions for its 29 physical columns; do not invent entries for Feature 02–04 before those tables exist and are validated.

## Field contract

`Table_Catalog` has primary key `(table_schema, table_name)`. `category`, `definition`, and `grain` describe the table. `primary_key_columns` holds the ordered physical key. `source_system` and `source_tables` identify provenance. `source_code_paths` points to supporting repository code/migrations. `update_rule` states when/how rows change. `related_functions` lists table-related PostgreSQL routines. `documentation_status` grades the semantic claim, and `created_at`/`updated_at` audit metadata changes.

`Column_Catalog` has primary key `(table_schema, table_name, column_name)` and a foreign key to `Table_Catalog`. `ordinal_position`, `data_type`, `is_nullable`, `default_expression`, and `is_primary_key` are synchronized from live PostgreSQL. `definition`, `source_column_or_expression`, `unit`, and `null_rule` explain meaning. `source_code_paths`, `documentation_status`, and timestamps record evidence and maintenance.

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
```

## Mandatory maintenance for future changes

1. Inspect the live schema and relevant writer script, migration, or source data. Do not promote an inferred definition to `VERIFIED`.
2. Add a **new forward-only migration** under `database/migrations/`. Register a new approved table in `Table_Catalog`; register new or changed columns in `Column_Catalog`. A deleted or renamed target needs a migration that reconciles its catalog entries in the same transaction.
3. For new/changed Feature columns or formulas, add a new semantic version in `Feature_Catalog` and reconcile the generic `Column_Catalog` entry. `Feature_Catalog` remains formula authority.
4. For a new/changed PostgreSQL function, update `Table_Catalog.related_functions` for every registered table it directly serves; record its signature, behavior, and affected tables in the migration and `DATABASE_CHANGELOG.md`. Standalone functions with no registered table have no row-level function catalog in this two-catalog design and must be documented explicitly in the changelog and this guide until a separate Function Catalog is approved.
5. Run `python scripts/sync_database_catalog.py --host <proxy-host> --port <proxy-port>` with `PGDATABASE`, `PGUSER`, and `PGPASSWORD` held only in the process environment. The script reconciles physical column facts, fills previously unknown descriptions from source documentation, and refreshes Feature semantics from the active `Feature_Catalog`; it never overwrites a manually reviewed non-Feature definition. It fails on unregistered/stale tables or columns and missing active Feature definitions. The daily GitHub Action runs this check before schema generation.
6. Run `python scripts/sync_database_schema.py --host <proxy-host> --port <proxy-port>` to refresh `DATABASE_SCHEMA.md`, append `DATABASE_CHANGELOG.md`, verify catalog coverage, and push the documentation/migration commit to `main`. The schema generator uses catalog descriptions for registered tables and columns.

These rules are also mandatory in `AGENTS.md`, `README.md`, and `database/migrations/README.md`. Do not edit an applied migration or commit credentials.
