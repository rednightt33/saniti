# market-sql-governor

The only path from the AI to market data in PostgreSQL. `market-ai-orc` exposes one tool,
`request_data`, which forwards a structured **Data Request Spec** to this service. The service
validates the spec against the five AI catalogs, compiles safe SQL, checks the planner estimate,
executes read-only, and decides how the result is delivered:
- **inline**, for small results;
- as an **immutable Parquet snapshot**, for approved large results;
- or it returns a structured refusal.

The AI never sends SQL, never sees a database credential, and never chooses the delivery format.

```text
market-ai-orc ── request_data(spec) ──► POST /v1/query (Bearer SQL_GOVERNOR_API_KEY)
                                              │
      Gate 1-7  AI catalog policy (tables, columns, filters, joins, grouping, aggregation, coverage)
      Gate 8    SQL compiler (psycopg.sql identifiers, every value a bound parameter)
      Gate 9    EXPLAIN (FORMAT JSON) scan-rows and cost gate
      Gate 10   read-only execution ── small ──► INLINE_RESULT (rows)
                                    └─ large ──► Parquet + manifest in a private bucket ─► DATASET_READY (dataset_id)
```

## Separation and credentials

| | market-ai-orc | market-sql-governor |
|---|---|---|
| Database login | `market_ai_orc`: catalogs + 20-row preview function | `market_sql_governor`: 5 catalogs + 7 market tables |
| SQL logic | none | all of it |
| Bucket credentials | none | the dataset bucket only |
| Talks to OpenRouter | yes | never |

`market-ai-orc` holds only `SQL_GOVERNOR_URL` and `SQL_GOVERNOR_API_KEY`.

## API

- `GET /health`: liveness.
- `GET /ready`: returns 200 only when the governed database is reachable.
- `POST /v1/query`: requires `Authorization: Bearer ${SQL_GOVERNOR_API_KEY}`. The body is
  exactly `{"request_id": "...", "spec": DataRequestSpec}`. Any other key gets a 422.

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
`estimated_plan_cost`, `returned_rows`, `output_bytes`, `rows`, `dataset`, `details`,
`warnings`, and `runtime_ms`.

| decision | next_action | Meaning |
|---|---|---|
| `INLINE_RESULT` | `USE_INLINE_RESULT` | Executed; `rows` holds the observations. Numerics are exact decimal strings |
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

## Routing

- **Inline:** if the rows (≤ `SQL_MAX_INLINE_ROWS`) and their serialized JSON
  (≤ `SQL_MAX_INLINE_OUTPUT_BYTES`) both fit, the result is `INLINE_RESULT`.
- **Dataset:** otherwise rows stream in batches of 10,000 into a zstd Parquet file, bounded by
  `SQL_MAX_DATASET_ROWS` and `SQL_MAX_DATASET_BYTES`. Exceeding a bound gives
  `NEEDS_NARROWING`/`DATASET_TOO_LARGE`, and nothing is stored.
- **No storage:** without dataset storage an oversized result gets
  `NEEDS_NARROWING`/`RESULT_TOO_LARGE_FOR_INLINE`.

The AI cannot influence routing beyond lowering `requested_limit`.

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
- It lists `datasets/`, reads each manifest's `expires_at`, and deletes `data.parquet` and then
  `manifest.json` once that time has passed. The default is one week after creation.
- A dataset without a readable manifest, such as an interrupted write, expires
  `SQL_DATASET_RETENTION_HOURS` after its oldest object.
- Only keys shaped `datasets/ds_<24 hex>/(data.parquet|manifest.json)` are ever deleted.
- Each pass logs `sql_governor_dataset_cleanup` with the counts and the deleted dataset ids.
- Storage errors are logged, and the next pass retries.

PostgreSQL `numeric` is stored as `float64` in Parquet, and the manifest notes this. Inline
results keep exact decimal strings.

The manifest is what a future `get_dataset_manifest(dataset_id)` and
`run_python_analysis(dataset_id=...)` will read. It describes what this extract contains, while
`get_data_coverage` describes what the source is believed to contain.

Legacy market-ai-backend snapshots are `JSON_GZIP` in `Analytics_Dataset_Snapshot`. This
service writes no database rows: its role is read-only, so metadata lives in the manifest.

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
| `SQL_MAX_INLINE_ROWS` / `SQL_MAX_INLINE_OUTPUT_BYTES` | 200 / 24000 | Inline routing thresholds |
| `SQL_MAX_ESTIMATED_SCAN_ROWS` | 2,000,000 | EXPLAIN scan ceiling |
| `SQL_MAX_PLAN_COST` | 600,000 | EXPLAIN total-cost ceiling, calibrated on live dev data on 2026-09-23: cost 411k took 29 s (106k Feature 02 rows) and cost 819k took over 74 s |
| `SQL_MAX_EXECUTION_SECONDS` | 60 | Wall-clock bound on one whole extraction; must be at least `SQL_STATEMENT_TIMEOUT_SECONDS` |
| `SQL_MAX_DATE_RANGE_DAYS` / `SQL_MAX_UNFILTERED_DATE_RANGE_DAYS` | 3660 / 400 | Date span with / without an entity filter |
| `SQL_MAX_DATASET_ROWS` / `SQL_MAX_DATASET_BYTES` | 500,000 / 128 MiB | Snapshot ceilings |
| `SQL_DATASET_RETENTION_HOURS` | 168 (one week) | `expires_at` in the manifest; the janitor deletes the dataset after it |
| `SQL_DATASET_CLEANUP_INTERVAL_SECONDS` | 3600 | How often the expiry janitor runs (0 disables it; at most 86400) |
| `SQL_DATASET_BUCKET_NAME`, `_ENDPOINT`, `_REGION`, `_ACCESS_KEY_ID`, `_SECRET_ACCESS_KEY` | unset | Private S3-compatible dataset bucket |
| `SQL_DATASET_LOCAL_DIR` | unset | Development and test storage (mutually exclusive with the bucket) |

These limits are not in any prompt or tool description, and no request field can raise them.

## Logging

Each query writes one JSON line (`event = sql_governor_query`) with `request_id`, `query_id`,
`query_hash`, `source_tables`, `requested_columns`, `decision`, `reason_code`, `next_action`,
`estimated_scan_rows`, `estimated_plan_cost`, `returned_rows`, `output_bytes`, `dataset_id`, and
`runtime_ms`. Filter values, rows, SQL parameters, credentials, and headers are never logged.

## Railway deployment

- Service `market-sql-governor` (`1a322795-4f93-4c51-a25e-5fcfc5ab4722`), project `lucid-patience`, environment `dev`.
  It is private at `http://market-sql-governor.railway.internal:8080`, with no public domain.
  The health check is `/ready`, and restart is `ALWAYS`.
- It is deployed by local upload of this folder with `--path-as-root`. There is no GitHub source and no watch path.
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
