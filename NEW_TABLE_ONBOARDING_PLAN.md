# Onboarding a table or Feature for the AI

Status (2026-10-22): **the procedure for every new raw table or Feature.** Rewritten from the plan of 2026-10-01/09/20
after the first integration (EXEC-ONBOARD-1, 2026-10-20: `Price_Fixed_Income` through the view
`Price_Fixed_Income_Final`, `Universe_Fixed_income`, `Feature_04_Technical_Indicator`) and audited against the code at
`main` `33cf07b`. The benchmark is Feature 04 (section 1); index acceptance is mandatory (section 3); the jobs are in
`scripts/onboarding/` (section 4). The earlier text is in Git history (`git log -- NEW_TABLE_ONBOARDING_PLAN.md`).

**How to use this document (for a person or an AI agent).** Onboarding is one task: read section 1 (the standard),
then follow section 4 step by step, asking the user only the decisions of step 2. Every step reads the code and the
live database at that moment; nothing is written from memory (AGENTS.md, Gates and evidence). The detailed rules stay
authoritative where they are, and the steps point to them:
- `ERRORS_AND_SOLUTIONS.md` Part A (data-format standard, items A1.1–A5.24) and Part C (cross-asset and macro risks);
- `DATABASE_CATALOG.md` (catalog roles, field contract, mandatory maintenance);
- `AGENTS.md` Mandatory workflow step 5 (migration, catalogs, changelogs, generated documents);
- `DATABASE_INDEX_ACCEPTANCE.md` (measured plans of the exposed tables).

## 0. How a table becomes visible to the AI

The AI never reads a table directly. It sees what the catalog shows and reads rows only through the SQL Governor
(`apps/market-sql-governor`). Each link is read at run time; a missing link has the effect in the last column.

| # | Link | Read by | Without it |
|---|---|---|---|
| V1 | `GRANT SELECT` to role `market_ai_sql_reader` (the Governor login `market_sql_governor` reads through it) | Governor extraction | the Governor's SQL fails on permission |
| V2 | `AI_table_catalog` row with `is_active` and `ai_access_level = 'BOUNDED_READ'` | Governor policy (`TABLE_INACTIVE`, `TABLE_DENIED`); orc `discover_catalog` | the table does not exist for the AI |
| V3 | `AI_column_catalog` rows; a column is visible only with `ai_allowed` and not `is_sensitive` | `get_catalog_details` COLUMNS, Governor contract, sandbox validator, export `kolom` sheet | the column is invisible; an empty `unit` disables the unit checks |
| V4 | `AI_catalog_relationships` with non-empty `supported_join_semantics` | DataNeed planner, Governor, `saniti` join helpers | no join to any other table |
| V5 | `AI_calculation_catalog` rows for Feature columns (a column holding a reference formula names it in `implementation_ref`) | `get_catalog_details` CALCULATIONS; FORMULAS `stored_in` (orc `tools/catalog.py` `STORED_IN_SQL`) | the AI does not see the formula and recomputes a stored indicator; **only a migration fills it** |
| V6 | `AI_data_coverage` rows | discovery and COVERAGE details, freshness, data record, follow-up ideas | the AI does not know the date range; freshness reads UNKNOWN. **Written only by the coverage job, whose `RAW_SOURCES` lists tables by hand** |
| V7 | `AI_table_catalog.freshness_sla` | `app/freshness.py` (SEGAR / TERLAMBAT / BASI) | freshness UNKNOWN |
| V8 | `Table_Catalog` availability columns (`observation_date_column`, `data_available_at_column`, `availability_rule`, `point_in_time_status`, `historical_metadata_method`) | point-in-time DataNeed checks | a point-in-time request cannot be checked; look-ahead risk (Part C) |
| V9 | A table without a time column is a reference table | `lookup_reference` and the database check before a web lookup | — |
| V10 | `AI_metric_catalog` rows (optional) | `query_metric` (one Governor summary per period) | no one-call official metric; the AI uses a data need |
| V11 | Searchable words in table and column descriptions (A4.19) | `discover_catalog` keyword search (without a keyword at most 50 tables, `MAX_DISCOVERED_TABLES`) | the AI finds the table only by an exact keyword |
| V12 | Prompt, tool descriptions and router text that say what the database does or does not hold (section 4 step 6) | system prompt `OUTSIDE_DATA_*_RULE`, `research_web` description, router `WAREHOUSE_SCOPE` | the model goes to the web for data the table holds (found twice in EXEC-ONBOARD-1 L3, M194) |
| V13 | Indexes for the query patterns (section 3) | Governor gates: EXPLAIN scan estimate, row count, date split | extractions are refused (`ESTIMATED_SCAN_TOO_LARGE`, `REJECTED_SCAN_SIZE`) or slow, and fill the Postgres page cache (billed as memory, M198) |

Loading without exposing: data can be loaded and checked with no `AI_table_catalog` row or `is_active = false`
(V2); the Governor and the AI do not see it (the state of Feature 05/06 on 2026-10-22, before EXEC-M204 step 5).

## 1. The standard: what every exposed table has (benchmark Feature 01–04)

Read from the code and migrations at `33cf07b`. A new table is onboarded when it has every row of this table, or the
user decided in step 2 to leave one out (recorded in the migration header).

| Artifact | Feature 01 | Feature 02 | Feature 03 | Feature 04 (benchmark) | Bonds (`Price_Fixed_Income_Final`) |
|---|---|---|---|---|---|
| Key, entity-first | `(ticker, date)` | `(ticker, market_board, broker, investor_type, date)` | `(ticker, market_board, date)` | `(ticker, trade_date, timeframe, asset_type)` | base `(tradingview_symbol, date, metric_type, "Timeframe")`; view key `(ticker, metric_type, date)` |
| Index leading with the time column (section 3) | `(date)` | `(date, market_board, ticker)` | `(date, market_board, ticker)` | `(trade_date)` since 2026-10-23 (`20261023_001`; before it every ticker over 365 days was refused and the calendar took 7.0 s, M204) | `(date)` and partial `("Country", date DESC, …) WHERE is_final` on the base table, seen through the view since M205 |
| `Feature_Catalog` (formula, interpretation, use, misuse warning, review, evidence) | yes | yes (v2) | yes | 57 active v4 | — (raw) |
| `AI_table_catalog` (subject metadata, `row_presence`, `freshness_sla`, `coverage_enabled`) | yes | yes | yes | yes (`asset_type` NULL: cross-asset) | yes |
| `AI_column_catalog` (unit, semantic type, aggregation and resample rules, `value_time_basis`, DRAFT `description_id`) | yes | yes | yes | yes; Pine state and bookkeeping columns `ai_allowed = false` | yes |
| `AI_calculation_catalog` | migration `20260922_001` | `20260922_001` | `20260922_001` | `20261020_001`, with `AI_formula_reference:<id>` (`STORED_VARIANT` / `RELATED_NOT_IDENTICAL`) | — |
| `AI_catalog_relationships` | yes | yes | yes | to stock prices / Feature 01 (equity) and the bond view | to `Universe_Fixed_income` |
| Coverage (`coverage_job.py`) | derived from `Price_Stock_Indonesia_IDX` | derived from `IDX_Broker_Summary` | derived from `IDX_Broker_Summary` | derived from two raw sources by `asset_type` | raw source |
| Grant + Governor login list (`provision_market_sql_governor_login.py` `APPROVED`) | yes | yes | yes | yes | view and universe (base table hidden) |
| Preview (`tools/preview.py` `ORDERING` + `ai_preview_table_rows`) | yes | yes | yes | yes (hidden columns left out) | yes |
| Corporate-action note (sandbox `PRICE_TABLES`) | yes | — | — | yes (equity `close` is the raw price) | — |
| Independent validation script | `verify_feature_01_auto.py` | `validate_feature_02.py` | `validate_feature_03.py` | `verification/feature04/` | L0 counts |
| Refresh path | Feature 01 worker | manual backfill | manual backfill | `feature-04-worker` | fixed-income crons |
| AI validation | — (seed) | — (seed) | — (seed) | L0, L2, L3 (section 5) | L0, L2, L3 |

Feature 05 and 06 are exposed since 2026-10-23 (EXEC-M204 step 5, migration `20261023_004`) through stock views,
the bond pattern:
- `Feature_05_Foreign_Domestic_Broker_Detail_Stock` and `Feature_06_Foreign_Domestic_Stock` show the current IDX stock
  universe only (`IDX_Stock_Universe`, 844 of 4,125 codes; user: "khusus saham saja for now. Jadi dibuat view");
- the base tables stay hidden;
- every row of the table above, except the following decisions:
  - Indonesian meanings later (step 2 item 11);
  - refresh is manual;
  - delisted codes and ETFs are not visible.

They pass section 3 through the base tables' `(trade_date)` indexes (Feature 05 `20261023_002`, Feature 06
`(trade_date, market_board)`), the Governor level of section 5 (rows equal `count(*)`) and L2. L3 is pending
(paid). F02/F03 keep every code (user "1 aja").

## 2. What the user defines (per new table)

Collected before any load; the agent fills it in with the user and records the answers in the migration header.

| # | Item | Where it lands | Part A |
|---|---|---|---|
| 1 | Purpose, source (provider, endpoint/file), licence, refresh schedule | `Table_Catalog` (`definition`, `source_system`, `update_rule`) | A5.21 |
| 2 | Grain and primary key; every meaning-bearing dimension in the key (currency, tenor, series, board) | migration, `Table_Catalog.grain` | A1.1 |
| 3 | Entity identifier and its code system (`USDIDR`, ISIN, series code); mapping to existing codes if they differ | `AI_table_catalog`, mapping table if needed | A1.2 |
| 4 | Subject metadata: `data_domain`, `entity_type`, `asset_type` (NULL for a cross-asset Feature), `supported_frequencies`, `time_semantics` | `AI_table_catalog` | A1.3 |
| 5 | Time: type (`date` / `timestamptz` + exchange time zone), calendar (IDX days, 24/5 FX, monthly release) | `time_semantics` | A2.5–6 |
| 6 | Macro and fundamentals: reference period, `release_date`, vintage/revision policy | columns + catalog | A2.7 |
| 7 | Per numeric column: unit, percent-or-decimal, sign convention, adjustment basis, meaning of NULL | `Column_Catalog`, `AI_column_catalog.unit` | A3.10–15 |
| 8 | Per column: `ai_allowed` (state and bookkeeping columns false), `is_sensitive`, `filter_allowed`, `group_by_allowed`, `value_time_basis` | `AI_column_catalog` | A2.8, A4.16 |
| 9 | Resample rule per column (`FIRST`/`LAST`/`MAX`/`MIN`/`SUM`, or none) and summary rules (section 2.1) | `AI_column_catalog.resample_aggregation`, `cross_entity_aggregation`, `semantic_type` | A4.18 |
| 10 | Safe joins: columns, temporal rule (`EXACT_DATE`, `AS_OF` on the availability date, `EFFECTIVE_DATED`, `CURRENT_STATE`), output grain | `AI_catalog_relationships` | A4.17 |
| 11 | Searchable description words, including the Indonesian words a user types ("kurs", "inflasi", "net beli asing") | table and column descriptions | A4.19 |
| 12 | Derived columns: formula, interpretation, recommended use, misuse warning, evidence (section 2.3) | `Feature_Catalog` | A4.16 |
| 13 | Typical questions (3–5) with their expected answers | the L3 suite (section 5) | — |
| 14 | What a missing row means: `DENSE`, `ACTIVITY_ONLY` or `NOT_APPLICABLE` | `AI_table_catalog.row_presence`, `row_presence_status` | A3.15 |
| 15 | Indonesian meaning per AI column (`DRAFT` until reviewed) | `AI_column_catalog.description_id`, `description_id_status` | A3.15 |
| 16 | Freshness and coverage: `freshness_sla`, `coverage_enabled`, which raw source a Feature's coverage derives from | `AI_table_catalog`; `coverage_job.py` | A2.9 |
| 17 | Point-in-time availability (V8) | `Table_Catalog` availability columns | A2.7 |
| 18 | Fixed category values as a single-column `CHECK (column = ANY (ARRAY[...]))` (Governor and fast-lane value lists read it) | migration | A1.4 |
| 19 | Official metrics (optional) | `AI_metric_catalog` | — |
| 20 | Reader words: how the table and its unit read for a person; a monthly or quarterly period word | catalog descriptions; reader texts (section 6) | — |
| 21 | Refresh and load: loader service, schedule, load log, who is told when it fails | loader app, `RAILWAY_CHANGELOG.md`, `.railway/railway.ts` | A5.21–23 |
| 22 | The table's query patterns and expected size a year from now (section 3) | step 3 params, migration header | — |

### 2.1 Summary rules: what the model can ask the warehouse to total (G18)

A DataNeed request may carry an `aggregate`; the warehouse returns one row per group. The rules come only from the
catalog, so a wrong rule produces a wrong total that passes every gate (before 2026-09-25 the warehouse summed by
`allowed_aggregations`, a list with no direction: `WAREHOUSE_AGGREGATION_PLAN.md` section 2).

| Question | Rule | Examples |
|---|---|---|
| Adds up across entities on one date? | `cross_entity_aggregation` = SUM only for flows and counts that do not overlap; otherwise NULL | net value, volume: SUM. Price, rate, yield, ratio, share, z-score, HHI, distinct broker count: NULL |
| Adds up over time? | `resample_aggregation` SUM for flows; LAST/FIRST/MAX/MIN for levels; NULL for rolling windows | daily net: SUM. 5-day rolling total: NULL. Close: LAST |
| Can entities be mixed? | several units or currencies in one column: no SUM across entities; the unit stays in the grain | CPI + GDP in one column, USDIDR + EURIDR: NULL |
| Which columns group? | `group_by_allowed` true only for keys and dimensions | ticker, broker, board: yes. net value: no |
| What kind of column? | `semantic_type` decides MIN/MAX (MEASURE) and COUNT_DISTINCT (IDENTIFIER, DIMENSION, TIME) | — |

`allowed_aggregations` is not a permission to sum. A NULL rule is safe: the summary is refused and raw rows are pulled.
A new table's `summaries.example` must itself be approved by the validator (section 5).

### 2.2 Questions per asset class

| Class | Decide with the user | Part A / C |
|---|---|---|
| Macro (BI-Rate, CPI, GDP, reserves) | one table per series family or a long table with `series_id` in the key; reference period plus `release_date`; vintages or "latest revision"; unit per series in the grain; joins to daily data `AS_OF` on `release_date` (the first live AS_OF) | A2.7, A1.1, A3.11, C |
| Fundamental (statements, ratios) | period type; fiscal period end versus filing date; restatements as versions; reporting currency and scale; consolidated or parent; TTM and ratios as Features | A2.7, A3.11, A3.14 |
| FX | quote convention (`USDIDR` = IDR per 1 USD); fixing or close (JISDOR, time zone); 24/5 calendar joined `AS_OF` backward | A1.2, A2.5–6, C |
| Cross-market | exchange calendar and time zone (a US close lands on the next Jakarta date); index levels never summed | A2.5–6, A3.14, C |
| Fixed income (done 2026-10-20) | price and yield in one value column: `metric_type` and `value_unit` in the grain, nothing sums across instruments; final daily rows only through a view; the universe as a reference table; yields are levels (LAST, never SUM) | A1.1, A2.5–6, A3.11, A4.18 |
| Commodities | spot or futures; contract and roll rule; unit and currency; exchange and time zone | A3.11, A3.14, C |

### 2.3 Derived Feature tables

In addition to section 2:
- the name matches `^Feature_[0-9]{2}_[A-Za-z0-9_]+$` (the `Feature_Catalog` trigger refuses any other, M202);
- one `Feature_Catalog` row per column and version (formula, interpretation, recommended use, misuse warning, semantic
  review status, validation-evidence paths), then `scripts/audit_feature_catalog_semantics.py`;
- `Feature_Relationship_Catalog` for safe Feature joins and `AI_catalog_relationships` for the AI;
- one `AI_calculation_catalog` row per active definition, inserted by the onboarding migration (V5);
- every calculation whose lookback reads several observations carries `parameters.window_basis` (`ENTITY_SESSIONS`,
  `EXCHANGE_DAYS` or `CALENDAR_DAYS`, read from the Feature's code) and `window_length` (EXEC-M209, migration
  `20261025_016`); COLUMNS shows them as `window` and the system's window-basis line reads them;
- coverage derived from its raw source (`coverage_job.py` `reference_for`), or actual;
- a refresh path (worker or job, schedule, `freshness_sla`);
- an independent validation (`scripts/validate_feature_02.py` pattern) before `semantic_review_status` and
  `documentation_status` move past their draft values.

## 3. Indexing and the SQL Governor (mandatory for every new table)

Every query the AI causes goes through the Governor, and the Governor decides from the database's own plan and counts.
A table whose query patterns are not served by an index is refused or slow, and its scans fill the Postgres page cache
(6–13 GB idle on 2026-10-21, billed as memory: M198). So an onboarding includes index acceptance, measured, never
assumed (AGENTS.md: no speculative index).

**What the Governor does (code at `33cf07b`, limits live on dev 2026-10-22):**

| Gate | Code | Rule |
|---|---|---|
| EXPLAIN | `governor.py` `_prepare`, `_explain` | every query is EXPLAINed before it runs; a `Seq Scan` node counts the whole relation (`reltuples`), not the planner's row guess. Refused above 2,000,000 scanned rows (`SQL_MAX_ESTIMATED_SCAN_ROWS`, `ESTIMATED_SCAN_TOO_LARGE`) or plan cost 600,000 (`SQL_MAX_PLAN_COST`) |
| Counted rows (G13, G15, G22-3) | `governor.py` `_counted` | the planner's result-row estimate was up to 3× off (e02: 108,091 estimated, 319,801 returned), so plans failed after the user approved them. Estimates now run `SELECT count(*)` over the same compiled SQL, unordered and stopped at the cap, within 7,000 ms (`SQL_ESTIMATE_COUNT_ENABLED=true`, `SQL_ESTIMATE_COUNT_TIMEOUT_MS=7000`): `row_basis` COUNTED, AT_LEAST (stopped at the cap) or PLANNER with `ROW_ESTIMATE_UNCERTAIN` (timed out). The scan and cost gates still use EXPLAIN |
| Date split | `extract.py` `partitioning`; `INDEX_LEADING_SQL` | an extraction above a limit is split by date only when an index's **first** column is the table's time column (`pg_index.indkey[0]`); a skip scan over a ticker-first key does not count. Otherwise `REJECTED_SCAN_SIZE` |
| Time limits | `config.py`, `governor.py` | `statement_timeout` 20 s per statement, 60 s per extraction (`SQL_MAX_EXECUTION_SECONDS`), read-only REPEATABLE READ |
| Heavy-query queue (G22-4) | `governor.py` `_heavy_slot` | at most 2 extractions and counts at once (`SQL_HEAVY_QUERY_CONCURRENCY=2`), others wait up to 120 s then 503 |

The `query_metric` calendar (`summary.calendar_sql`, a loose index scan for the newest dates) passes the gate too since
2026-10-23 (`Summarizer._gate_calendar`, M204): it is judged by its plan cost and Seq Scans, not by the largest node's
row estimate (its `LIMIT 1` probe estimates the whole table even when it runs in 0.2 ms), and refused as
`CALENDAR_NOT_INDEXED` (next step: a data need) without an index led by the time column. The index lookup follows a view
to the base columns it reads (M205).

So an index matters four ways: the count finishes within 7 s only through an index (otherwise the estimate falls back
to the planner, the old failure); a date split needs an index led by the time column; the calendar needs the same (or
`query_metric` is refused for the table); a
Seq Scan of a large table is refused before it runs. And one way against: a date-leading index can make cross-sections
slower on a table stored in entity order, because the rows of one date are scattered in the heap (Feature 02 with
`(date, market_board, ticker)` 9.0 s against Feature 05 without it 5.1 s for every ticker on one date;
`DATABASE_INDEX_ACCEPTANCE.md` 2026-10-22). An index is therefore accepted on measurements, never on its shape.

**Acceptance rule** (`scripts/onboarding/measure_indexes.py` prints the verdict; thresholds are the Governor's):

| Pattern | Shape | Pass |
|---|---|---|
| P1 | one entity, the last 365 days | the Governor would approve it, or split it by date (scan ≤ 2,000,000 and cost ≤ 600,000, or an index led by the time column); executed within 10 s (half the `statement_timeout`); counted within 7 s |
| P2 | every entity on the newest date (cross-section) | as P1 |
| P3 | every entity, the last 7 days | as P1 |
| P4 | every entity, the last 365 days | gate and count only (the case the date split serves) |
| P5 | the `query_metric` calendar, 20 newest dates | within 1 s, no Seq Scan, plan cost within 600,000 (the Governor's calendar gate, M204) |
| Table | — | when the table holds, or will hold within a year, more than 2,000,000 rows, or P5 fails: an index whose first column is the time column |

A Seq Scan of a table above 1,000,000 rows is reported as WARN (it nears the scan limit as the table grows). The
patterns carry the equality filters the AI sends (a board, an asset type, a metric); add the patterns the table's
typical questions need (item 22). Copy the verdict lines into the migration header and `DATABASE_INDEX_ACCEPTANCE.md`.

**A view** (an exposed filter over a base table, M205, M207) is measured the same way. There are two differences:
- its rows, scans and index come from the base table;
- every lookup of its newest or oldest date is written `ORDER BY t DESC LIMIT 1`. `max()` through a view that joins
  reads every row: 45 million on Feature 05, against 0.06 ms.

A filter through another table (a universe or membership list) hides its selectivity from the planner. Run section 5's
Governor level on any view with such a filter: it shows whether long requests are split again while extracting
(M208).

**Adding an index.** Prefer the narrow `(time_column)` index when only the calendar or the date split needs it; a wider
`(time, filter dimensions)` index only when P2/P3 measure faster with it. Measure first in a DRYRUN transaction:
`CREATE INDEX` inside `migration_job.py` DRYRUN, then `EXPLAIN (ANALYZE, BUFFERS)` of every pattern as probes, then
ROLLBACK, and compare with the measurement without it; keep the index only if no pattern gets slower (the planner may
move a cross-section onto it). Apply it in its own forward migration without a transaction:
`CREATE INDEX CONCURRENTLY IF NOT EXISTS …` (no write lock on the source; a failed build leaves an invalid index to
drop and retry), then `ANALYZE` and `measure_indexes.py` again. `ANALYZE` also ends every load, backfill or rebuild:
the Governor counts a Seq Scan as `reltuples`, and stale statistics doubled Feature 04's estimate (M206). A second
index for one pattern is measured with `scripts/onboarding/ab_index.py` (time, MB from cache and disk, temp spill,
Governor verdict per pattern, in a rolled-back transaction) and kept only when it pays for its size (Feature 05
`(broker, trade_date)` was not, 2026-10-23). Check the disk first (`railway volume list`:
`postgres-volume`, 75 GB since 2026-10-22). Example: Feature 06 `(trade_date, market_board)`, cross-section 2.7 s →
5.3 ms (`20261022_005`).

## 4. Steps

Jobs run on `orc-test-runner` with `DATABASE_URL` only for the run:
`scripts/onboarding/run_job.sh <job.py> <params.json> <log> [extras…]` (from the repository root; Railway CLI with a
project token; it prints `VAR_REMOVED` at the end). Before each job and each deploy: no `edge_` run in flight (orc logs);
Railway accepts deploys (status page; M198: a database setting changed while deploys were paused left Postgres without
a deployment).

1. **Read (no write).** `scripts/onboarding/read_table.py` with the tables, their time columns and Feature 04 as the
   model: columns, kind and size, constraints and CHECK lists, indexes (leading column as the Governor sees it), view
   definition, grants, exact rows and NULLs per column, date range and rows per date, `Table_Catalog`,
   `Column_Catalog`, `Feature_Catalog`, Feature relationships, any existing `AI_*` rows, and the benchmark's rows.
   Also read: overlap of entity codes with exposed tables (does a code mean two things?), the units per row, and the
   `AI_formula_reference` ids a Feature implements (parameters, tie and zero conventions).
2. **Decisions for the user** (only these; record the answers in the migration header and EXEC.md):
   rows the AI may not see (a view with the filter; the catalog and the Governor have no row filter); reference tables
   exposed with it and the entity-name column; hidden columns; coverage source or `coverage_enabled = false`; preview
   in or out; subject metadata; the section 2 items not yet answered; an index from step 3.
3. **Index acceptance (section 3).** `scripts/onboarding/measure_indexes.py` per table with its entity, time column,
   filters and expected size. Every FAIL needs an index migration (measured again) or the user's decision not to expose
   that pattern, recorded.
4. **One forward migration** (template `database/migrations/20261020_001_onboard_fixed_income_and_feature04.sql`):
   preflight (nothing registered yet; expected column and `Feature_Catalog` counts; roles and formula rows exist); the
   view if decided, `REVOKE ALL FROM PUBLIC`, `GRANT SELECT` to `market_ai_sql_reader` (and `market_ai_preview_owner`
   when previewed, `pgweb_reader` when present); `AI_table_catalog` (description with the words a user types and the
   key filters); `AI_column_catalog` from `information_schema.columns` joined to a VALUES list or `Feature_Catalog`;
   `AI_catalog_relationships` with every key column exposed; `AI_calculation_catalog` per active Feature definition;
   `ai_preview_table_rows` when previewed; `Table_Catalog` / `Column_Catalog` for a view and the migration path on the
   touched rows; a verify block for every count, privilege (the AI reader cannot read a hidden base table) and key.
5. **Rehearse and apply.** `scripts/onboarding/migration_job.py` mode DRYRUN (the files without COMMIT in one
   transaction, probes as `market_ai_sql_reader`, `market_ai_preview_reader`, and bounded `EXPLAIN (ANALYZE, BUFFERS)`
   of the patterns, then ROLLBACK) until clean; then APPLY and read back; add the hash to
   `database/migrations/APPLIED.sha256`.
6. **Code places still written by hand** (until each is derived from the catalog, section 6):

   | Place | What to add | Done for Feature 04 in |
   |---|---|---|
   | `scripts/provision_market_sql_governor_login.py` `APPROVED` | the exposed objects | `2ba744e` |
   | `apps/ai-data-coverage/coverage_job.py` `RAW_SOURCES` (`reference_for`), `SNAPSHOTS`, a derived Feature function, `FORBIDDEN_FEATURE_TABLES` | raw source, snapshot, derivation | `2ba744e` |
   | `apps/market-ai-orc/app/tools/preview.py` `PreviewTable`, `ORDERING` (the test compares it with the SQL function) | when previewed | `2ba744e` |
   | `apps/market-python-sandbox/app/service.py` `PRICE_TABLES` | a table holding raw stock prices (corporate-action note) | `2ba744e` |
   | `apps/market-ai-orc/app/conversation_router.py` `WAREHOUSE_SCOPE` | the new data domain in a few words (M194) | `a474a65` |
   | `apps/market-ai-orc/app/orchestrator.py` `OUTSIDE_DATA_RULE`, `OUTSIDE_DATA_WEB_RULE`, `OUTSIDE_DATA_RESEARCH_RULE` | remove the domain from the "outside the catalog" examples (today: macro data, fundamentals, news) | `2ba744e` |
   | `apps/market-ai-orc/app/tools/web_research.py` `research_web` description | still "not in the market database"; change when a non-market domain is exposed | — |
   | `apps/market-ai-orc/app/tools/research_planner.py` `ENTITY_TOKEN` (`[A-Z][A-Z0-9]{3,5}`), `NOT_ENTITIES` | entity codes of another shape | `2ba744e` |
   | `scripts/generate_tool_catalog_migration.py` | a round for every tool whose contract text changed (Tool_Catalog) | `2ba744e` (round Z) |

   No change is needed in `tools/catalog.py` (stored formulas are read through `AI_calculation_catalog`, `7e159c6`),
   the Governor or the sandbox validator: they read the catalog.
7. **Generated records after a code change:** `scripts/snapshot_system_prompt.py record` and the approved sentences in
   `tests/test_prompt_pass2.py` after a prompt change; `scripts/generate_ai_tools_doc.py` after a tool text change;
   `scripts/generate_ai_router_doc.py` and the router benchmark after a router change; the orc, Governor, sandbox and
   coverage suites; deploy and SUCCESS.
8. **Validation** (section 5), L0–L3 at least.
9. **Records:** `DATABASE_SCHEMA.md` (`scripts/sync_database_schema.py`), `DATABASE_CHANGELOG.md` (source, rows, range,
   verification), `DATABASE_INDEX_ACCEPTANCE.md` (plans), `RAILWAY_CHANGELOG.md`, `PROJECT_CONTEXT.md` (exposed tables),
   `DATABASE_CATALOG.md`, `ERRORS_AND_SOLUTIONS.md` for anything found, EXEC.md.

## 5. Validation (reusable)

| Level | How | Pass |
|---|---|---|
| L0 database | read-back probes of the APPLY job | counts equal the base filter; grants; the AI reader cannot read a hidden base table; relationship keys exist; `sync_database_catalog.py` strict |
| Index | `measure_indexes.py` after APPLY | every pattern PASS (section 3) |
| L1/L2 tools (no model) | `scripts/onboarding/l2_tools.py`: the coverage job once, then orc's own tools as role `market_ai_orc` | found by the user's words (`discover_catalog`); COLUMNS show units and summaries, no hidden column; COVERAGE shows the range and freshness; FORMULAS show `stored_in` for a Feature; preview rows; `lookup_reference` lists a table without a time column |
| Governor (no model) | `scripts/onboarding/governor_check.py` (the Governor's own extraction code with the privileges of `market_ai_sql_reader`, extras `apps/market-sql-governor/app` and its `requirements.txt`): one entity over 365 days, every entity over 400 days (split parts extracted and split again as the orc planner does), every entity over 2,000 days estimated | row count equals `SELECT count(*)` (G13); a refusal names a valid narrowing; parts split again while extracting are reported (M208) |
| Summary (G18) | per SUM-rule measure a summary equals an independent `GROUP BY`; a NULL-rule measure is refused `AGGREGATION_NOT_ADDITIVE`; `summaries.example` approved | right totals, wrong ones refused |
| Join | the new table with stock prices through its relationship; row counts before and after | no look-ahead, no dropped or duplicated rows |
| L3 model (paid, a few cents each) | `orc-test-runner` suite like `apps/orc-test-runner/suites/onboard_l3_20261020.json` (fast lane) with the item 13 questions, then the answers from `AI_conversation_turn` against SQL ground truth | a data route; the table is read through a data need; stored values equal SQL; no `research_web` for stored values; no recomputation of a stored indicator; value references by key |
| Export | an Excel export from the table | `kolom` sheet in Indonesian, the right period word |
| L4 regression | full orc, Governor, sandbox, coverage suites; the A/B questions when credit allows | no new failure |

Only L3 finds what the model does with the catalog: both faults of the first integration were found there (M194, M195).
Every job of this section and the L3 suite share the one-off service `orc-test-runner`: a new deployment stops the one
running, so a job waits until a suite's log prints `OTR {"event": "done"}` (M210, manual rule).

## 6. Known gaps (proposals, not built)

The hand lists of section 4 step 6 should each become a value derived from the catalog (user rule: derive, do not
enumerate). Open, in the order they start to matter:
- `research_web` description and `tools/reference.py` (the database check before a web lookup covers static reference
  tables only): needed before the first macro or fundamental table, or the model answers those from the web;
- reader words (`user_texts.py` `EXPORT_READING`, `SOURCE_NAMES`, `WARNING_LINES["FREQUENCY_GAPS"]`) assume daily
  stock data; needed before a monthly or quarterly table;
- coverage written by the loader itself instead of `RAW_SOURCES` (C06);
- `app/freshness.py` counts Monday–Friday below 7 days; holidays per market are not in the catalog;
- `catalog_summary.py` and `MAX_DISCOVERED_TABLES = 50`: past 50 tables discovery needs a keyword;
- method guides were built on IDX stock prices; using them on macro or FX series is a method decision (new guide
  version, `AI_TOOLS.md`).

## 7. History

**2026-10-20, EXEC-ONBOARD-1 (benchmark).** User: "Ok view saja ya untuk no 1. Jalankan." Decisions: a view for the
final bond rows, the universe as a reference table, Feature 04 coverage from its two raw sources, preview in, DRAFT
Indonesian meanings. Migrations `20261020_001` and `20261020_002` (Tool_Catalog round Z); code `2ba744e`, fixes
`a474a65` (M194: the router's description of the warehouse) and `7e159c6` (M195: a tool note let the model prefer the
reference formula over the stored column). Measured, not assumed: Feature 04's key answered the latest-session and
one-week patterns in 8–14 ms, so no index was added. L0 and L2 passed at the first attempt; L3 found the two faults and
passed after the fixes; L3 (d), (e) and the paid A/B regression were left for later (credit). Details: EXEC.md
EXEC-ONBOARD-1, DATABASE_CHANGELOG.md, RAILWAY_CHANGELOG.md, ERRORS_AND_SOLUTIONS.md M194–M195.

**2026-10-22, audit and rewrite.** User: "tolong juga dimasukkan agar ketika kita ada feature onboarding, maka
indexing juga aktif untuk feature atau table baru … Review dan edit bagian-bagian yang tumpang tindih atau
kontradiktif … menggunakan benchmark feature 4." Found against the code: the "current state" of the old section 2 and
the live-state line of section 0 predated EXEC-ONBOARD-1; the guideline named job files that lived only in a session
scratchpad (now `scripts/onboarding/`); the old step list exposed the table after the tests while the template
migration exposes it at once (now one order: rehearse with DRYRUN, apply, validate, roll back with a forward migration
if L3 fails); the tests table and the validation levels overlapped (now section 5); indexing was one clause (now
section 3, with the Governor's counting and date-split rules). Feature 05/06 are not exposed yet (section 1).
The acceptance thresholds of section 3 follow the Governor's limits and the measurements of the same day (`DATABASE_INDEX_ACCEPTANCE.md` "Feature 04 and Feature 05 under the SQL Governor gate", M204): the calendar pattern P5 was added and a date index is accepted only without regression.
"Section 6" in migration `20261020_001`, Tool_Catalog round Z and `DATABASE_CHANGELOG.md` 2026-10-20 means the plan of
that date (now this section and section 1); applied migrations are not edited.

**2026-10-23, EXEC-M204.** User: "Semua saham berbulan-bulan sampai bertahun-tahun harus bisa dijawab dari feature 1
sampai feature 6"; "Kenapa kita tidak tambahkan indexing saja untuk feature yang belum ada"; go. Feature 04 and 05 got
`(trade_date)` (`20261023_001`-`003`); the Governor gates the calendar and sees indexes behind a view (M204, M205);
stale statistics found and fixed (M206). Feature 04, the benchmark, now passes section 3. Not built and listed as
pending in EXEC-M204: stored summaries (P6), summaries per month/quarter/year in the Governor (P7), measuring a full
"all data" request (P8).

**2026-10-23, EXEC-M204 step 5 (Feature 05/06 exposed).** User: "1. tidak usah, khusus saham saja for now. Jadi dibuat
view; 2-10 ok; 11 nanti saja", "Daftar saham sekarang (Recommended)", "1 aja".
- Migrations `20261023_004` (views, catalogs, preview) and `20261023_005` (Tool_Catalog round AC).
- Code `d485afd`: preview list, coverage from `IDX_Broker_Summary` with the stock filter, Governor login list.
- Validating a view showed that the tools of this guide assumed a table (M207):
  - `measure_indexes.py` now judges a view as the Governor does: rows within 30 s or the planner estimate; a Seq
    Scan at the reltuples of the relation it names; counts capped at `SQL_MAX_DATASET_ROWS + 1`; the newest date by
    `ORDER BY … DESC LIMIT 1`;
  - the Governor's newest-date lookup changed the same way.
- The Governor level got its own script, `governor_check.py`. Its first run found that the planner underestimates
  rows through the universe filter, so long requests are split again while extracting (M208, open).

**2026-10-25, EXEC-INDEX-1 (Feature 01-06 INDEX tables).** User: "buat visible ke AI juga ya"; "Sesama INDEX + ke saham
per tanggal"; "Dari Feature_Vocabulary". Migrations `20261025_005` and `20261025_006` (round AD). The AI_column_catalog
rules were derived, not typed: the structure from the stock counterpart's reviewed rows, the description and unit from
the INDEX Feature_Catalog, the Indonesian meaning from Feature_Vocabulary. Found: the join contract needs an entity
key, so a join on the date alone (a stock against IHSG) cannot be registered (M216).

**2026-10-25, EXEC-GO-1025 (`idx_event_annotation`).** User: "go for this as well Service stockbit-updater dan
onboarding hanya table idx_event_annotation." One transactional table (corporate actions and insider movements); its two
source tables stay hidden. Migration `20261025_015` (DRYRUN `addf6968`, APPLY `226fc268`); code `b41a2af`: coverage
source, Governor approved list, the first-message router scope and the research_web examples (snapshot v019). Index
acceptance `f89c9b11` PASS without a new index; L2 `36fd8b6c` (found by the user's words for dividends, insiders and
splits; 22 columns with units; coverage); Governor `d10ba8ea` PASS; router benchmark with a new labelled "events" set:
2/12 before (8 data questions sent to the web), 12/12 after. L3 `edge_9380a451` (TLKM insider sales) matched SQL;
`edge_04f42c64` (BBCA dividend) found M223: the table carries one date per corporate action and none of its terms. The
coverage freshness of a table with scheduled future rows is M224. Preview and relationships were not added.
