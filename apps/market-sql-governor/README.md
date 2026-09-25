# market-sql-governor

The only path from the AI to market data in PostgreSQL. `market-ai-orc` exposes two tools that
forward structured specs to this service, one per purpose:
- `request_data` (**analysis input**): a Data Request Spec. An approved request is **always** an
  immutable Parquet dataset (`DATASET_READY`), whatever its size. Its rows never go to the model.
- `lookup_fact` (**specific facts**): a narrow Lookup Fact Spec. It returns at most 20 source
  values (`VALUE`) or database aggregates (`AGGREGATE`), each with a `fact_id`.

Both validate against the five AI catalogs with the same gates, compile safe SQL, check the
planner estimate, and execute read-only, or return a structured refusal. The AI never sends SQL,
never sees a database credential, and never chooses the delivery format.

```text
market-ai-orc ── request_data(spec) ──► POST /v1/query (Bearer SQL_GOVERNOR_API_KEY)
                                              │
      Gate 1-7  AI catalog policy (tables, columns, filters, joins, grouping, aggregation, coverage)
      Gate 8    SQL compiler (psycopg.sql identifiers, every value a bound parameter)
      Gate 9    EXPLAIN (FORMAT JSON) scan-rows and cost gate
      Gate 10   read-only execution ──► Parquet + manifest in a private bucket ─► DATASET_READY (dataset_id)

market-ai-orc ── lookup_fact(spec) ──► POST /v1/lookup   same gates 1-9 on a generated narrow request
                                              └─► ≤ 20 values ─► FACTS_READY (facts with fact_id)
```

## Separation and credentials

| | market-ai-orc | market-sql-governor |
|---|---|---|
| Database login | `market_ai_orc`: catalogs + 20-row preview function | `market_sql_governor`: 5 catalogs + 7 market tables |
| SQL logic | none | all of it |
| Bucket credentials | none | the dataset bucket only |
| Talks to OpenRouter | yes | never |

`market-ai-orc` holds only `SQL_GOVERNOR_URL` and `SQL_GOVERNOR_API_KEY`.
`market-python-sandbox` holds only `SQL_GOVERNOR_URL` and `SQL_GOVERNOR_DATASET_ACCESS_KEY`, a
second key with a disjoint purpose. That key can read dataset manifests and obtain a short-lived
read URL for one dataset. It **cannot** call `/v1/query`, and the orc key cannot obtain URLs.

## API

- `GET /health`: liveness.
- `GET /ready`: returns 200 only when the governed database is reachable.
- `POST /v1/query`: requires `Authorization: Bearer ${SQL_GOVERNOR_API_KEY}`. The body is
  `{"request_id": "...", "spec": DataRequestSpec}` plus an optional `lineage` object. Any other
  key gets a 422.
  - `lineage` is sent only by market-ai-orc's backend compiler (`prepare_analysis_data`), never by
    the model. Fields: `spec_id`, `spec_sha256`, `scope_sha256`, `data_plan_id`, the logical input
    name, `part_index` of `part_count`, `request_sha256`, and an optional date partition.
  - It is validated (`app/spec.py DataPlanLineage`; malformed or `part_index > part_count` gets
    422) and stored in the dataset's full manifest. It never changes what is compiled.
- `POST /v1/lookup`: the same key and body shape with a `LookupFactSpec` (see
  [Lookup facts](#lookup-facts)).

- `GET /v1/datasets/{dataset_id}/manifest`: requires either key. It returns a bounded safe
  subset of the manifest (`app/datasets.py`):
  - columns with friendly types (`float64`, `date`, `string`, …), their source types, and their
    `unit` from `AI_column_catalog.unit` (null for a COUNT). market-python-sandbox uses the units
    to refuse a CUSTOM formula that adds or compares columns with different units;
  - row, column, and byte counts; source tables; `query_id`;
  - requested and actual scope, entities present;
  - missing entities (at most 200, plus the full count);
  - completeness, checksum, created/expires;
  - `numeric_float64_columns`, with a `NUMERIC_AS_FLOAT64` warning.

  It never returns the request spec, the 5000-entity list, object keys, or URLs. Responses
  are `AVAILABLE` (200), `DATASET_EXPIRED` (410, with `expires_at`), `DATASET_NOT_FOUND` (404),
  or `INVALID_DATASET_ID` (422).
- `POST /v1/datasets/{dataset_id}/access`: requires `SQL_GOVERNOR_DATASET_ACCESS_KEY` only. The
  body is exactly `{request_id, analysis_id}`. It returns the safe manifest plus
  `download: {url, expires_in_seconds}`. The URL is a **SigV4 presigned GET for exactly
  `datasets/<id>/data.parquet`** that expires after `SQL_DATASET_ACCESS_URL_TTL_SECONDS`
  (default 120). It cannot list or write, and it carries the access-key id and a signature but
  never the secret key.
  - Before granting, the Governor checks expiry and confirms that the object exists with the
    manifest's byte count (`DATASET_UNAVAILABLE` / `DATASET_INTEGRITY_ERROR` otherwise).
  - Each call logs `sql_governor_dataset_access` (request_id, analysis_id, dataset_id, outcome,
    byte_count). The URL is never logged.

- `POST /v1/catalog/contract`: requires either key. The body is `{request_id, tables: 1-10 names}`.
  It returns catalog metadata only, never rows (`app/catalog_contract.py`):
  - for each active, AI-readable table: its keys and time column, the subject metadata of
    migration 20260925_001 (`data_domain`, `entity_type`, `asset_type`, `supported_frequencies`,
    `time_semantics`, `subject_metadata_status`), and its AI-allowed columns with types, units and
    filter/group/aggregation permissions;
  - the relationships touching those tables;
  - a per-table content hash (`catalog_table_sha256`) and `catalog_sha256`;
  - `unknown_tables`.

  market-python-sandbox approves an Analysis Spec V2 against this contract. Before migration
  20260925_001 is applied it answers with `subject_metadata: false` and null subject fields.

  After migration 20260925_003, each relationship also carries `supported_join_semantics`
  (CURRENT_STATE, EXACT_DATE, AS_OF, EFFECTIVE_DATED) with `left_time_column`, `right_time_column`,
  `effective_from_column` and `effective_to_column`, and each column carries `resample_aggregation`
  (FIRST, LAST, MAX, MIN, SUM or null). The sandbox's DataNeedValidator binds DataNeedSpecs to these
  fields. Before that migration they are absent, and no relationship is joinable by a DataNeedSpec.
- **Executed scope and the validator manifest.** Each dataset's full manifest (`manifest_version`
  v2) also records:
  - `request_sha256`;
  - the caller's `lineage`;
  - `executed_scope`, derived from the validated query itself: source table, joined tables with
    relationship ids, every filter with its type-coerced values in canonical text form, grouping,
    aggregations, and the requested range;
  - `source_contracts` with the catalog hash of every table read.

  Only the sandbox's access grant returns them, as `validator_manifest`. `/manifest` and
  market-ai-orc never see them, and none of them is SQL text, an object key, or a credential.
  The sandbox refuses to analyse a dataset whose executed scope differs from the approved spec.

There is no SQL endpoint and no OpenAPI or docs route.

### Data Request Spec (`app/spec.py`)

Every field is required; optional values use `null`. Unknown fields are rejected at every
level. No field accepts SQL, expressions, join keys, or a delivery format.

| Field | Contract |
|---|---|
| `purpose` | 1–500 characters |
| `from_table` | Catalog `table_name` (`^[A-Za-z][A-Za-z0-9_]{0,62}$`) |
| `columns` | `[{table, column}]`. When aggregating or grouping, every returned column must also be in `group_by` |
| `joins` | `[{table, relationship_id or null}]`. Keys come from `AI_catalog_relationships`; the join is an `INNER JOIN` |
| `filters` | `[{table, column, operator, value}]`. Operators: `EQ NEQ GT GTE LT LTE IN BETWEEN IS_NULL IS_NOT_NULL`. Values are typed per the catalog `data_type` and always bound as parameters |
| `group_by` | `[{table, column}]` |
| `aggregations` | `[{table, column, function}]`. Functions: `SUM AVG MEDIAN MIN MAX COUNT COUNT_DISTINCT`, each only when listed in `allowed_aggregations`. `MEDIAN` is `percentile_cont(0.5)`. `PERCENTILE` and `WEIGHTED_AVG` are not supported in v1 |
| `order_by` | `[{table, column, function or null, direction}]`. Must name a returned column or a requested aggregation |
| `requested_limit` | `null`, or at least 1. It can only lower the backend ceilings, never raise them |

### Response (`app/decisions.py`)

The response always contains `decision`, `next_action`, `reason_code`, `message`,
`request_id`, `query_id`, `query_hash`, `source_tables`, `columns`, `estimated_scan_rows`,
`estimated_plan_cost`, `returned_rows`, `output_bytes`, `dataset`, `details`, `warnings`, and
`runtime_ms`. There is no `rows` field.

| decision | next_action | Meaning |
|---|---|---|
| `DATASET_READY` | `RUN_ANALYSIS` | Executed and stored as Parquet; `dataset` holds the reference and summary, never rows or object keys |
| `NEEDS_NARROWING` | `REVISE_DATA_REQUEST` | Allowed but too broad or expensive. `details` names the limit and the available range |
| `REJECTED` | `STOP_OR_REFORMULATE` | Not allowed as specified. `reason_code` names the gate |
| `SANDBOX_REQUIRED` | `USE_ANALYSIS_SANDBOX` | Reserved; not produced in this milestone |

`next_action` is a fixed function of `decision`.

## Gates

1. **Tables.** `AI_table_catalog` must have `is_active = true` and
   `ai_access_level = 'BOUNDED_READ'`. There are at most `SQL_MAX_TABLES` tables and no
   self-joins.
2. **Columns.** Every referenced column (selected, filtered, grouped, aggregated, ordered) must
   exist in `AI_column_catalog` with `ai_allowed = true` and `is_sensitive = false`. Otherwise the
   whole request is rejected; columns are never silently removed.
3. **Filters.** `filter_allowed = true`. Values are coerced to the column type (a bad value is
   `INVALID_FILTER_VALUE`), `IN` takes at most `SQL_MAX_IN_VALUES` values, and `BETWEEN` needs
   `low <= high`.
4. **Joins.** Only `AI_catalog_relationships` rows with `is_allowed = true` that connect the new
   table to a table already in the request. The join uses the catalog `left_columns[i] =
   right_columns[i]`.
   - `requires_preaggregation = true` returns `REJECTED`/`PREAGGREGATION_REQUIRED` with
     `safe_output_grain`, `temporal_rule`, and the relationship. It never performs a naive join.
   - Ambiguity (`AMBIGUOUS_RELATIONSHIP`) requires a `relationship_id`.
5. **GROUP BY.** `group_by_allowed = true`.
6. **Aggregation.** The function must be listed in `allowed_aggregations`. Migration
   `20260923_007` adds `MIN`/`MAX` to every `date` column of the seven approved tables, for
   example for first and last available dates.
7. **Coverage and dates.** Uses the `DATASET` row in `AI_data_coverage` for the first table
   that has a time column.
   - **ACTUAL_SOURCE + VERIFIED:** a range entirely outside it gets
     `NEEDS_NARROWING`/`OUTSIDE_VERIFIED_COVERAGE`, and a partial overlap gets a warning.
   - **EXPECTED_DERIVED / UNVERIFIED:** only a warning. The expected range is never treated as
     confirmed availability.
   - **Range limit:** the effective range (filters, else coverage) may span at most
     `SQL_MAX_DATE_RANGE_DAYS` when the entity column is filtered with `EQ`/`IN`, otherwise
     `SQL_MAX_UNFILTERED_DATE_RANGE_DAYS`. This matches the legacy backend semantics.
8. **Compile.** Uses `psycopg.sql.Identifier` for tables, aliases, and columns. Every value and
   the `LIMIT` are placeholders. The row cap is `min(requested_limit, SQL_MAX_DATASET_ROWS + 1)`.
   `query_hash` is the SHA-256 of the SQL text plus its parameters.
9. **EXPLAIN (FORMAT JSON).** Walks the whole plan tree. The estimate is the largest node's
   `Plan Rows`, except that a sequential scan counts the relation's full `reltuples`, because it
   reads every row. Three checks run before anything executes:
   - the scan estimate against `SQL_MAX_ESTIMATED_SCAN_ROWS`;
   - the root `Plan Rows` (the estimated result size, capped by the compiled `LIMIT`) against
     `SQL_MAX_DATASET_ROWS`, which gives `ESTIMATED_RESULT_TOO_LARGE`;
   - the root `Total Cost` against `SQL_MAX_PLAN_COST`.
10. **Execute.** Runs in the same read-only `REPEATABLE READ` transaction as the policy read and
    `EXPLAIN`, through a server-side cursor with `statement_timeout`, `lock_timeout`, and
    `idle_in_transaction_session_timeout`. `statement_timeout` bounds each `FETCH`, and
    `SQL_MAX_EXECUTION_SECONDS` bounds the whole extraction (`QUERY_TIMEOUT`).

## Delivery

- **Dataset only:** every approved request, even a single row, streams in batches of 10,000 into
  a zstd Parquet file, bounded by `SQL_MAX_DATASET_ROWS` and `SQL_MAX_DATASET_BYTES`. Exceeding a
  bound gives `NEEDS_NARROWING`/`DATASET_TOO_LARGE`, and nothing is stored. An empty result is an
  empty dataset.
- **No storage:** without dataset storage an approved request gets
  `REJECTED`/`DATASET_STORAGE_UNAVAILABLE` after the gates; rows are never returned instead.

The row, byte, and time bounds are cost limits, not a delivery choice.

## DataNeed extractions (`POST /v1/extract`, `app/extract.py`)

market-ai-orc's Execution Planner sends one physical part of an approved DataNeedSpec request:
`{request_id, extraction, lineage, planned_parts}`, with the orc key only. The model never writes an extraction.
The planner builds it from the sandbox's approved contract, which holds only catalog identifiers and canonical
values:

- the table and its pruned columns (the requested columns plus the key columns);
- the canonical scope tree (ALL, PREDICATE, AND, OR, NOT);
- restrictions: the INNER relationships of the DataNeedSpec, each compiled as an `EXISTS` semi-join on a catalog
  relationship. The join semantics decide which reference row applies to each observation date:
  - `CURRENT_STATE`: the key only;
  - `EXACT_DATE`: the same date (the catalog's time columns);
  - `AS_OF`: the latest reference row at or before the date, backward only;
  - `EFFECTIVE_DATED`: `effective_from <= date < effective_to`, where a NULL `effective_to` is still valid;
- the window (an envelope of approved ranges, or a date partition of it);
- an optional entity partition `{modulus, remainder}` over `hashtextextended(entity)`: a complete, disjoint split
  of the entities;
- the requested ordering. The Governor appends the key columns, so the order is total and deterministic.

The Governor re-validates everything against the catalog: tables, AI-allowed columns, filter permissions, value
types (canonical text values must round-trip), relationship ids, `supported_join_semantics`, time and effective
columns, and temporal direction. The lineage must describe the body it came with: `extraction_sha256` is the hash
of the raw extraction and `part_key` the hash of its window and partition. The Governor compiles parameterized SQL,
reads the leading index columns of the table, and EXPLAINs the query. The status is one of:

| Status | Meaning | `next_action` |
|---|---|---|
| `APPROVED` | Extracted: an immutable Parquet dataset. The manifest carries the lineage and an `executed_scope` of version `extract/v1`, with the canonical scope, restrictions, their hashes, window, partition, `sampling: false` and `truncation: false`. | `ADD_TO_BUNDLE` |
| `APPROVED_WITH_PARTITIONING` | Nothing extracted. The part fits only as `{kind DATE or ENTITY, parts}`. | `PARTITION_AND_RESUBMIT` |
| `REJECTED_SCAN_SIZE`, `REJECTED_ROW_LIMIT`, `REJECTED_COMPUTE_COST`, `REJECTED_JOIN_COST`, `REJECTED_TIMEOUT_RISK` | No semantics-preserving split fits the limits. | `REPLAN_OR_REVISE_DATA_NEED_SPEC` |
| `REJECTED_POLICY` | The request breaks catalog policy. | `REVISE_DATA_NEED_SPEC` |

Every response names the logical `data_request_id`.

How a limit is split:
- A date split narrows the window. It reduces the scanned rows only when an index leads with the time column;
  without one, a scan over the limit is `REJECTED_SCAN_SIZE`.
- An entity split reduces result rows and sort cost, never scanned rows.
- A result over the row cap during execution is never truncated. It becomes a partitioning answer, or a refusal
  once `SQL_EXTRACT_MAX_PARTS` is reached.
- Each call logs one JSON line (`event = sql_governor_extract`) with status, code, estimates, partitioning,
  dataset id, row count, need, plan and part key. It holds no values.

## Lookup facts

`POST /v1/lookup` answers specific factual questions (a close on a date, a week's total volume)
without Python. `LookupFactSpec` (`app/spec.py`) has `purpose`, `mode`, `table`, `entities`
(1–5 tickers or the table's entity codes), `dates` (≤ 10) or `date_range`, and either `columns`
(`VALUE`, 1–4) or `aggregations` plus `per_entity` (`AGGREGATE`, 1–4 of `SUM`, `AVG`, `MIN`,
`MAX`, `COUNT`). It has no ordering, ranking, statistic, or free filter field.

The Governor turns the spec into an ordinary Data Request Spec (entity `IN` filter, date `IN` or
`BETWEEN` filter on the catalog's entity and time columns) and runs **gates 1–9 unchanged**, so
the table allowlist, column permissions, allowed aggregations, coverage, and EXPLAIN limits are
exactly those of `request_data`. Then:
- `VALUE`: at most 20 values (rows × columns) and at most 10 distinct dates; otherwise
  `REJECTED`/`LOOKUP_TOO_LARGE`. Explicit keys without a source row are listed in `missing`.
- `AGGREGATE`: the database computes the aggregates over the explicit scope (one row per entity
  or one row in total), at most 20 values; the scope comes back whole with every fact.

Each fact carries `fact_id`, `kind`, `table`, `column`, `aggregation`, `entity`, `date` or
`scope`, the `value` (numerics as exact decimal strings), and `query_id`.

| decision | next_action | Meaning |
|---|---|---|
| `FACTS_READY` | `USE_FACTS` | The facts are in `facts` |
| `REJECTED` (`LOOKUP_NOT_ALLOWED`, `LOOKUP_TOO_LARGE`, `AGGREGATION_NOT_ALLOWED`) | `USE_ANALYSIS_PATH` | Not a fact lookup (too many values, ranking, a statistic, or another shape): use `request_data` plus a Python analysis |
| `REJECTED` (other gates) | `STOP_OR_REFORMULATE` | For example `TABLE_NOT_APPROVED`, `UNKNOWN_COLUMN` |
| `NEEDS_NARROWING` | `REVISE_LOOKUP` | For example `OUTSIDE_VERIFIED_COVERAGE` |

## Parquet snapshots and manifest

Objects are immutable (write-once, checksum-verified):
- `datasets/<dataset_id>/data.parquet`: zstd-compressed. The file metadata carries
  `dataset_id` and `query_hash`.
- `datasets/<dataset_id>/manifest.json`: contains `dataset_id`, `format`, `compression`,
  `checksum_sha256`, `row_count`, `column_count`, `byte_count`, `schema` (PostgreSQL and Parquet
  types, source table and column, aggregation), `source_tables`, `query_id`, `query_hash`,
  `request_id`, `request_spec`, `requested_scope` (date range, entities), `actual_date_range`,
  `entities_present_count`, `entities_present` (up to 5,000), `missing_entities`, `truncated`
  (always `false`; oversize is refused), `completeness_status`, `created_at`, `expires_at`, and
  `governor_version`.

### Expiry

Railway buckets do not support lifecycle rules yet ("Bucket lifecycle configuration" is listed as
not supported). The Governor therefore runs an expiry janitor (`app/janitor.py`). It is a
background thread that runs at startup and then every `SQL_DATASET_CLEANUP_INTERVAL_SECONDS`.
- It lists `datasets/`, reads each manifest's `expires_at`, and deletes `data.parquet` once that
  time has passed. The default is one week after creation.
- The readable `manifest.json` stays as a **tombstone** for
  `SQL_DATASET_TOMBSTONE_RETENTION_HOURS` (default 720, 30 days) and is then deleted, so a later
  lookup answers `DATASET_EXPIRED` rather than `DATASET_NOT_FOUND`. An unreadable manifest is
  deleted together with the data.
- A dataset without a readable manifest, such as an interrupted write, expires
  `SQL_DATASET_RETENTION_HOURS` after its oldest object.
- Only keys shaped `datasets/ds_<24 hex>/(data.parquet|manifest.json)` are ever deleted.
- Each pass logs `sql_governor_dataset_cleanup` with the counts and the deleted dataset ids.
- Storage errors are logged, and the next pass retries.

PostgreSQL `numeric` is stored as `float64` in Parquet, and the manifest notes this. Inline
results keep exact decimal strings.

The manifest is what `get_dataset_manifest(dataset_id)` (market-ai-orc) and
`run_python_analysis` (market-python-sandbox, through the access endpoint) read. It describes
what this extract contains, while `get_data_coverage` describes what the source is believed to
contain.

Legacy market-ai-backend snapshots are `JSON_GZIP` in `Analytics_Dataset_Snapshot`. This
service writes no database rows: its role is read-only, so metadata lives in the manifest.

## External data contract (not connected)

`app/external.py` defines the contract a future external data provider (macro, yields, FX,
fundamentals, news, estimates) must meet, so such data would reach an analysis only as a governed
dataset with provenance, never as rows handed to the model:
- a `ProviderDescriptor` (source, grain, units, currency, history, revisions, entitlements, rate
  limit, timeout, response size) whose state starts `DISABLED` and must reach `AVAILABLE`
  (configured and authorized) before use;
- normalized errors (`EXTERNAL_PROVIDER_UNKNOWN`, `EXTERNAL_PROVIDER_DISABLED`,
  `EXTERNAL_RATE_LIMITED`, `EXTERNAL_TIMEOUT`, `EXTERNAL_RESPONSE_TOO_LARGE`, ...);
- `point_in_time_filter`: for a signal dated D, an observation is usable only when it was
  available on or before D; a later revision never replaces the vintage available at D, and
  retrieval time never makes data historically available.

The provider registry is empty, no endpoint or tool uses the module, and no credential is
configured. market-ai-orc reports `external_data: false`. The tests use fixture providers only.

## Database role

Migration `database/migrations/20260923_005_create_market_ai_sql_reader.sql`:
- Creates `NOLOGIN` role `market_ai_sql_reader` with `USAGE` on `public` and `SELECT` on
  exactly 12 tables: the 5 AI catalogs plus `Feature_01_Stock_Daily`,
  `Feature_02_Broker_Rolling`, `Feature_03_Stock_Broker_Daily`, `IDX_Broker_Profile`,
  `IDX_Broker_Summary`, `IDX_Stock_Universe`, and `Price_Stock_Indonesia_IDX`.
- Gives no write, DDL, or `CREATE` privilege.
- Fails the transaction if the role could read or write anything else.

`scripts/provision_market_sql_governor_login.py`:
- Inputs: `DATABASE_URL` (admin) and `MARKET_SQL_GOVERNOR_DB_PASSWORD`.
- Creates or rotates login `market_sql_governor`, a member of `market_ai_sql_reader` only.
- Role settings: `CONNECTION LIMIT 5`, `default_transaction_read_only=on`,
  `statement_timeout=60s`, `lock_timeout=2s`, `idle_in_transaction_session_timeout=30s`.
  The service sets its own, tighter session timeouts.
- Then verifies that the readable tables are exactly those 12 and that none are writable.

A table that the catalog approves but the role cannot read fails with
`DATABASE_PERMISSION_DENIED`. That is layer 2 (the role) protecting against a layer 1 (catalog)
mistake.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `SQL_GOVERNOR_API_KEY` | required (secret, ≥ 32 chars) | Bearer key that market-ai-orc must send |
| `GOVERNOR_DATABASE_URL` | required (secret) | DSN of the `market_sql_governor` login, on the private network |
| `SQL_CONNECT_TIMEOUT_SECONDS` | 5 | Connection timeout |
| `SQL_STATEMENT_TIMEOUT_SECONDS` | 20 | Per-statement timeout (≤ 120) |
| `SQL_LOCK_TIMEOUT_SECONDS` | 2 | Lock wait timeout |
| `SQL_MAX_TABLES` / `SQL_MAX_JOINS` | 3 / 2 | Tables and joins per request |
| `SQL_MAX_COLUMNS` / `SQL_MAX_FILTERS` / `SQL_MAX_IN_VALUES` | 20 / 10 / 100 | Request breadth |
| `SQL_MAX_ESTIMATED_SCAN_ROWS` | 2,000,000 | EXPLAIN scan ceiling |
| `SQL_MAX_PLAN_COST` | 600,000 | EXPLAIN total-cost ceiling, calibrated on live dev data on 2026-09-23: cost 411k took 29 s (106k Feature 02 rows) and cost 819k took over 74 s |
| `SQL_MAX_EXECUTION_SECONDS` | 60 | Wall-clock bound on one whole extraction; must be at least `SQL_STATEMENT_TIMEOUT_SECONDS` |
| `SQL_MAX_DATE_RANGE_DAYS` / `SQL_MAX_UNFILTERED_DATE_RANGE_DAYS` | 3660 / 400 | Date span with / without an entity filter |
| `SQL_MAX_DATASET_ROWS` / `SQL_MAX_DATASET_BYTES` | 500,000 / 128 MiB | Snapshot ceilings |
| `SQL_DATASET_RETENTION_HOURS` | 168 (one week) | `expires_at` in the manifest; the janitor deletes the dataset after it |
| `SQL_DATASET_CLEANUP_INTERVAL_SECONDS` | 3600 | How often the expiry janitor runs (0 disables it; at most 86400) |
| `SQL_DATASET_BUCKET_NAME`, `_ENDPOINT`, `_REGION`, `_ACCESS_KEY_ID`, `_SECRET_ACCESS_KEY` | unset | Private S3-compatible dataset bucket |
| `SQL_DATASET_LOCAL_DIR` | unset | Development and test storage (mutually exclusive with the bucket); access URLs are `file://` there |
| `SQL_GOVERNOR_DATASET_ACCESS_KEY` | unset (secret, ≥ 32 chars, ≠ API key) | market-python-sandbox key for manifests and dataset access; the access endpoint is disabled (401) without it |
| `SQL_DATASET_ACCESS_URL_TTL_SECONDS` | 120 | Presigned GET lifetime (30–900) |
| `SQL_DATASET_TOMBSTONE_RETENTION_HOURS` | 720 | How long an expired dataset's manifest is kept as a tombstone (0 deletes it with the data) |
| `SQL_EXTRACT_MAX_PARTS` | 64 | Partitions one DataNeed request may be split into (`/v1/extract`) |
| `SQL_EXTRACT_MAX_IN_VALUES` | 500 | IN / NOT_IN values per scope predicate in an extraction |
| `SQL_EXTRACT_MAX_COLUMNS` | 60 | Columns per extraction |
| `SQL_EXTRACT_MAX_WINDOW_DAYS` | 3660 | Longest window of one extraction part; longer windows are split by date |

These limits are not in any prompt or tool description, and no request field can raise them.

## Logging

Each query writes one JSON line (`event = sql_governor_query`) with `request_id`, `query_id`,
`query_hash`, `source_tables`, `requested_columns`, `decision`, `reason_code`, `next_action`,
`estimated_scan_rows`, `estimated_plan_cost`, `returned_rows`, `output_bytes`, `dataset_id`, and
`runtime_ms`. Filter values, rows, SQL parameters, credentials, and headers are never logged.

Each lookup writes `event = sql_governor_lookup` with `request_id`, `query_id`, `query_hash`,
`mode`, `table`, `decision`, `reason_code`, `next_action`, `fact_count`, and per fact its
`fact_id`, `column`, `aggregation`, `entity`, and `date`, plus `values_sha256`. The values
themselves are not logged; the hash lets an audit confirm what was returned.

## Railway deployment

- Service `market-sql-governor` (`1a322795-4f93-4c51-a25e-5fcfc5ab4722`), project `lucid-patience`, environment `dev`.
  It is private at `http://market-sql-governor.railway.internal:8080`, with no public domain.
  The health check is `/ready`, and restart is `ALWAYS`.
- Since 2026-09-25 it deploys from GitHub `rednightt33/saniti` branch `main`, root `/apps/market-sql-governor`,
  watch path `/apps/market-sql-governor/**`. A push to `main` that changes this folder deploys it. Earlier
  versions were local uploads.
- Variables:
  - `SQL_GOVERNOR_API_KEY` and `MARKET_SQL_GOVERNOR_DB_PASSWORD` are secrets set through stdin.
  - `GOVERNOR_DATABASE_URL` references that password and the `Postgres` private domain.
  - `SQL_DATASET_BUCKET_*` reference bucket `market-sql-datasets` (region `sjc`).
  - The limits use the code defaults.
- market-ai-orc reaches the service through `SQL_GOVERNOR_URL` and references `SQL_GOVERNOR_API_KEY`.
- Live acceptance and calibration results are recorded in `RAILWAY_CHANGELOG.md` and `DATABASE_CHANGELOG.md`.

## Run tests

```bash
cd apps/market-sql-governor
pip install -r requirements-dev.txt
python -m pytest                                     # unit tests
GOVERNOR_TEST_POSTGRES_URL=postgresql://postgres@127.0.0.1:55432/postgres python -m pytest
```

The integration tests build a temporary database. It has the exact AI catalog DDL from
`20260922_001`, the seven market tables with their exact live columns, keys, and indexes, and
synthetic rows (30 tickers × about 435 trading days). They apply migration 005, provision the
login, run every request as `market_sql_governor`, and drop everything afterwards.
