# Plan 2: onboarding a new table for the AI (currency, FX, index, macro)

Status (2026-10-01): **plan only, not executed** (user decision: record now, run later). Updated 2026-10-02 with the
summary rules a new table must carry (section 1a, G18 phase 1). Goal: when a new table is
exposed to the AI, every existing guarantee keeps holding (catalog, Governor, sandbox, answer gates, coverage,
audit), the user knows exactly what to define, the backend changes are known in advance, and the tests are fixed.

It builds on `ERRORS_AND_SOLUTIONS.md` Part A (the data-format standard) and Part C (risks of cross-asset and macro
data), `DATABASE_CATALOG.md`, and `AGENTS.md` step 5. Those stay authoritative; this plan turns them into one
checklist and removes the places where a table must be added by hand.

## 1. What the user defines (per new table)

Collected before any load; the agent fills it in with the user and records the answers in the migration.

| # | Item | Where it lands | Part A |
|---|---|---|---|
| 1 | Purpose, source (provider, endpoint/file), licence, refresh schedule | `Table_Catalog` (`definition`, `source_system`, `update_rule`) | A5.21 |
| 2 | Grain and primary key; every meaning-bearing dimension in the key (currency, tenor, series, board) | migration, `Table_Catalog.grain` | A1.1 |
| 3 | Entity identifier and its code system (`USDIDR`, ISIN, series code); mapping to existing codes if they differ | `AI_table_catalog`, mapping table if needed | A1.2 |
| 4 | Subject metadata: `data_domain`, `entity_type`, `asset_type`, `supported_frequencies`, `time_semantics` | `AI_table_catalog` | A1.3 |
| 5 | Time: type (`date` / `timestamptz` + exchange time zone), calendar (IDX days, 24/5 FX, monthly release) | `time_semantics` | A2.5–6 |
| 6 | Macro only: reference period, `release_date`, vintage/revision policy | columns + catalog | A2.7 |
| 7 | Per numeric column: unit, percent-or-decimal, sign convention, adjustment basis, meaning of NULL, sparse or not | `Column_Catalog`, `AI_column_catalog.unit` | A3.10–15 |
| 8 | Per column: `ai_allowed`, `is_sensitive`, `filter_allowed`, `group_by_allowed`, `value_time_basis` (current-state columns marked) | `AI_column_catalog` | A2.8, A4.16 |
| 9 | Resample rule per resamplable column (`FIRST`/`LAST`/`MAX`/`MIN`/`SUM`, or none) | `AI_column_catalog.resample_aggregation` | A4.18 |
| 9b | **Summary rules (G18, see section 1a)**: per measure, whether it adds up across entities on one date (`cross_entity_aggregation` SUM or deliberately NULL) and over time (item 9); `semantic_type` (MEASURE, IDENTIFIER, DIMENSION, TIME) and `group_by_allowed` decided per column, not defaulted | `AI_column_catalog.cross_entity_aggregation`, `semantic_type`, `group_by_allowed` | A4.18 |
| 10 | Safe joins to existing tables: columns, temporal rule (`EXACT_DATE`, `AS_OF` on the availability date, `EFFECTIVE_DATED`, `CURRENT_STATE`), output grain, pre-aggregation | `AI_catalog_relationships` | A4.17 |
| 11 | Searchable description words (asset class, source, measure, abbreviations) | table and column descriptions | A4.19 |
| 12 | Derived columns (if any): formula, interpretation, recommended use, misuse warning, evidence | `Feature_Catalog` | A4.16 |
| 13 | Typical questions (3–5) with their expected answers, for the golden tests | this plan's test list | — |

## 1a. Summary rules: what the model can ask the warehouse to total (added 2026-10-02, G18)

Since G18 phase 1 a DataNeed request may carry an `aggregate`, and the warehouse returns one row per group instead
of every raw row. The rules come only from the catalog, and the model is told from the catalog that a summary exists
(`get_catalog_details` COLUMNS `summaries`, the `summary_available` note on an approved raw request and on
`BUNDLE_TOO_LARGE`). A wrong catalog rule therefore produces a wrong total that passes every gate. This is the
history to avoid: before 2026-09-25 the warehouse summed by `allowed_aggregations`, a list with no direction, which
allowed SUM of prices, ratios, rolling totals over time and broker counts per board (`WAREHOUSE_AGGREGATION_PLAN.md`
section 2).

For every new table, decide with the user and record in the migration:

| Question | Rule | Examples |
|---|---|---|
| Does the column add up across entities on one date? | `cross_entity_aggregation` = SUM only for flows and counts of things that do not overlap between entities; otherwise NULL | net value, volume in one currency: SUM. Price, rate, yield, index level, ratio, share, percent change, z-score, an HHI, a count of distinct brokers: NULL |
| Does it add up over time? | `resample_aggregation` = SUM for flows; LAST/FIRST/MAX/MIN for levels; NULL for rolling windows | daily net: SUM. 5-day rolling total: NULL (summing overlapping windows counts days twice). Close: LAST |
| Can the entities be mixed at all? | When a table holds several units or currencies in one column (FX pairs, macro series with different units), no measure may be SUM across entities: the rows are not the same quantity. Keep the unit or currency in the grain and leave `cross_entity_aggregation` NULL | macro: CPI (index) + GDP (IDR) in one value column: NULL. FX: USDIDR + EURIDR rates: NULL |
| Which columns may group? | `group_by_allowed` true only for keys and dimensions; never for a measure | ticker, broker, board, sector: yes. net value: no |
| What kind of column is it? | `semantic_type` decides MIN/MAX (MEASURE only) and COUNT_DISTINCT (IDENTIFIER, DIMENSION, TIME) | a date stored as an identifier still counts as TIME for the summary |
| Is a key meaning-bearing? | Every key that changes the meaning of a value (currency, tenor, board, investor type) is in the grain, so dropping it is a visible decision of the request, never silent | — |

Rules that stay true whatever the table:
- `allowed_aggregations` is not a permission to sum (it has no direction); do not fill it in place of the two rules.
- Phase 1 keeps the time column in every summary; totals over time (phase 2) will use `resample_aggregation` and the
  Governor's coverage statistics. A rule set NULL now is safe: the request is refused and raw rows are pulled.
- A new table's summary example (`summaries.example` in catalog details) must itself be approved by the validator
  (test below), so what the model is shown can actually run.

## 2. Backend places that list tables by hand today (found 2026-10-01)

Each must be updated for a new table **today**; the plan replaces each with a value derived from the catalog
(user rule: derive, do not enumerate).

| Place | What it hard-codes | Today: manual update | Proposed: derived from |
|---|---|---|---|
| `scripts/provision_market_sql_governor_login.py` `APPROVED` | tables the Governor login may SELECT | add the table, re-run the job | `AI_table_catalog` rows (grant follows the catalog; the script verifies equality) |
| `apps/market-ai-orc/app/tools/preview.py` `PreviewTable`, `ORDERING` and DB function `public.ai_preview_table_rows` (migration `20260923_002`) | the 20-row preview tables and their order | edit both, new migration for the function | a `preview_order` column in `AI_table_catalog`; one generic function |
| `apps/ai-data-coverage/coverage_job.py` `RAW_SOURCES` | which tables get coverage, their entity/date columns | add an entry | `AI_table_catalog` (entity and time columns already there); coverage written by the loader itself (C06) |
| `apps/market-python-sandbox/app/service.py` `PRICE_TABLES` and the corporate-action note in `market-ai-orc` `orchestrator.py` | which tables carry the dividend/split warning | add the table if it is a price series | the adjustment basis declared per column (Part A3.14) |
| `apps/market-ai-orc/app/tools/research_planner.py` `ENTITY_TOKEN`, `NOT_ENTITIES` | ticker-shaped entity detection (4–6 capitals) | cannot express FX/series codes | the table's own entity values (`ANSWER_INTEGRITY_FIX_PLAN.md` / G13-1b) |
| `scripts/sync_database_catalog.py`, `scripts/sync_database_schema.py` | strict catalog completeness (checks, not lists) | none; they fail when an item is missing | unchanged: they are the gate |

## 3. Steps for one new table (once section 2 is derived)

1. Section 1 answers agreed with the user; Part A checklist passes.
2. Forward migration: table, keys, indexes (measured with `EXPLAIN (ANALYZE, BUFFERS)` on the planned query patterns),
   `Table_Catalog`, `Column_Catalog`, the five `AI_*` catalog rows, relationships, grants.
3. Loader: idempotent upsert, load log, coverage written in the same transaction, auth failures stop the load.
4. Dry run on dev (temporary job), apply, read back; `sync_database_catalog.py` and `sync_database_schema.py`.
5. Tests below; then expose (`ai_allowed`).
6. Records: `DATABASE_CHANGELOG.md` (source, checksum, rows, range, verification), `RAILWAY_CHANGELOG.md`,
   `ERRORS_AND_SOLUTIONS.md` for anything found.

## 4. Tests (fixed per new table)

| Level | Test | Proves |
|---|---|---|
| Catalog | `sync_database_catalog.py` strict; a Part A checker (new script) over the new rows: units, subject metadata, resample rules, relationship semantics, searchable words | nothing is missing or guessed |
| Governor | extraction of one entity and of all entities over 400 days; row count equals `SELECT count(*)` (G13); refusal names a valid narrowing | limits and estimates hold |
| Join | the new table with stock prices via its relationship (`AS_OF` for macro on `release_date`; calendar mismatch IDX vs 24/5); row counts before and after | no look-ahead, no dropped or duplicated rows |
| Sandbox | DataNeed validation, bundle, `saniti.resample` against the source for one known month | helpers work on the new grain |
| Summary (G18) | for each SUM-rule measure: a summary across entities equals `SELECT … GROUP BY` computed independently; a NULL-rule measure is refused `AGGREGATION_NOT_ADDITIVE`; the catalog `summaries.example` is approved by the validator; a multi-unit table offers no SUM | the catalog rules give right totals and refuse wrong ones |
| Answer | value references to the new identity column (`rows[series=USDIDR]`), lists, nulls (P14); no positional row in a keyed table (M44) | figures stay bound to their entity |
| Golden | the 3–5 user questions of item 13, with ground truth by SQL | end-to-end correctness |
| Coverage | coverage row appears after the first load without waiting for the nightly job | freshness is visible |

## 5. Before this plan runs

- `ANSWER_INTEGRITY_FIX_PLAN.md` items (M44, P14, G13) land first: they are what keeps a new identity column and a
  larger table safe.
- Decide which of section 2's derivations ship before the first new table, and which stay manual for one table.
