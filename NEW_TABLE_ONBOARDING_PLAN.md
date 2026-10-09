# Plan 2: onboarding a new table for the AI (macro, fundamental, FX, cross-market, commodities, Features)

Status (2026-10-09): **plan only, not executed.** Recorded 2026-10-01 (user decision: record now, run later); section 1a
added 2026-10-02 (G18 phase 1). Re-inspected 2026-10-09 against the code and the live dev catalog, after the user said
they plan to load macro, fundamental, FX, cross-market and commodity data and then Features ("ini adalah proses
onboarding only"). The 2026-10-09 inspection added section 0 (how a table becomes visible to the AI), items 14–21 of
section 1, sections 1b and 1c, the current state of every place in section 2 (with the places found since), the
must-land-first list in section 3, and the visibility tests of section 4.

Goal: when a new table is exposed to the AI, every existing guarantee keeps holding (catalog, Governor, sandbox, answer
gates, coverage, audit, reader texts), the AI actually uses the database for what the table holds instead of the web,
the user knows exactly what to define, the backend changes are known in advance, and the tests are fixed.

**This document is the single checklist for onboarding a table.** It does not repeat the detailed rules; those stay
authoritative where they are, and each item below points to them:
- `ERRORS_AND_SOLUTIONS.md` Part A (data-format standard, items A1.1–A5.24) and Part C (risks of cross-asset and macro
  data);
- `DATABASE_CATALOG.md` (catalog roles, field contract, mandatory maintenance);
- `AGENTS.md` Mandatory workflow step 5 (migration, catalogs, changelogs, and the generated documents when code
  changes: `AI_TOOLS.md`, `AI_ROUTER.md`, prompt snapshots);
- `DATABASE_INDEX_ACCEPTANCE.md` (measured indexes).

## 0. How a table becomes visible to the AI (verified 2026-10-09)

The AI never reads a table directly. It sees what the catalog shows and reads rows only through the SQL Governor. Each
link below is read at run time; a missing link has the effect in the last column.

| # | Link | Read by | Without it |
|---|---|---|---|
| V1 | `GRANT SELECT` on the table to role `market_ai_sql_reader` (the Governor login `market_sql_governor` reads through it) | SQL Governor extraction | the Governor's SQL fails on permission |
| V2 | `AI_table_catalog` row with `is_active` and `ai_access_level = 'BOUNDED_READ'` | Governor policy (`TABLE_INACTIVE`, `TABLE_DENIED`); orc `discover_catalog` (`VISIBLE_TABLES`) | the table does not exist for the AI |
| V3 | `AI_column_catalog` rows; a column is visible only with `ai_allowed` and not `is_sensitive` | `get_catalog_details` COLUMNS, Governor contract, export `kolom` sheet | the column is invisible; an empty `unit` disables the unit preflight |
| V4 | `AI_catalog_relationships` with non-empty `supported_join_semantics` | DataNeed planner, Governor, `saniti` join helpers | no join to any other table |
| V5 | `AI_calculation_catalog` rows for Feature columns | `get_catalog_details`, discovery counts | the AI does not see the formula; **no sync script fills it**, the migration must insert the rows (seeded once by `20260922_001`) |
| V6 | `AI_data_coverage` rows (actual or expected date range) | discovery and COVERAGE details, freshness status, data record, follow-up insight ideas | the AI does not know the date range; freshness reads UNKNOWN; follow-up ideas cannot name a period. **Written only by the coverage job, whose `RAW_SOURCES` lists tables by hand** |
| V7 | `AI_table_catalog.freshness_sla` | `app/freshness.py` (SEGAR / TERLAMBAT / BASI) | freshness UNKNOWN |
| V8 | `Table_Catalog` availability columns (`observation_date_column`, `data_available_at_column`, `availability_rule`, `point_in_time_status`, `historical_metadata_method`) | point-in-time DataNeed checks | a point-in-time request cannot be checked; look-ahead risk (Part C) |
| V9 | A table without a time column is a reference table | `lookup_reference` and the database check before a web lookup (derived, no code change) | — |
| V10 | `AI_metric_catalog` rows (optional) | `query_metric` (one Governor summary per period) | no one-call official metric; the AI uses a data need instead |
| V11 | Searchable words in table and column descriptions (A4.19) | `discover_catalog` keyword search; without a keyword it lists at most 50 tables (`MAX_DISCOVERED_TABLES`), then `truncated` | with many new tables the AI finds a table only by keyword |
| V12 | Prompt, tool descriptions and router criteria that tell the model what the database does **not** hold | system prompt (`OUTSIDE_DATA_*_RULE`), `research_web` description, router classes | today they name "macro data, yields, fundamentals" as outside the database, so the model goes to the web even after the table exists (section 2, rows 7–9) |

Live state 2026-10-09 (read-only, pgweb): 9 tables in `AI_table_catalog`, all `MARKET`, `subject_metadata_status`
INFERRED; 173 AI columns; 23 relationships (EXACT_DATE, CURRENT_STATE, EFFECTIVE_DATED; **no AS_OF relationship
exists yet**, so the first macro join is also the first live use of AS_OF); coverage rows for the 7 original tables only
(the two history tables have `coverage_enabled = false` and no SLA); `AI_CATALOG_SUMMARY_IN_PROMPT` is off on dev.

## 1. What the user defines (per new table)

Collected before any load; the agent fills it in with the user and records the answers in the migration.

| # | Item | Where it lands | Part A |
|---|---|---|---|
| 1 | Purpose, source (provider, endpoint/file), licence, refresh schedule | `Table_Catalog` (`definition`, `source_system`, `update_rule`) | A5.21 |
| 2 | Grain and primary key; every meaning-bearing dimension in the key (currency, tenor, series, board) | migration, `Table_Catalog.grain` | A1.1 |
| 3 | Entity identifier and its code system (`USDIDR`, ISIN, series code); mapping to existing codes if they differ | `AI_table_catalog`, mapping table if needed | A1.2 |
| 4 | Subject metadata: `data_domain`, `entity_type`, `asset_type`, `supported_frequencies`, `time_semantics` | `AI_table_catalog` | A1.3 |
| 5 | Time: type (`date` / `timestamptz` + exchange time zone), calendar (IDX days, 24/5 FX, monthly release) | `time_semantics` | A2.5–6 |
| 6 | Macro and fundamentals: reference period, `release_date` (filing or announcement date for fundamentals), vintage/revision policy | columns + catalog | A2.7 |
| 7 | Per numeric column: unit, percent-or-decimal, sign convention, adjustment basis, meaning of NULL, sparse or not | `Column_Catalog`, `AI_column_catalog.unit` | A3.10–15 |
| 8 | Per column: `ai_allowed`, `is_sensitive`, `filter_allowed`, `group_by_allowed`, `value_time_basis` (current-state columns marked) | `AI_column_catalog` | A2.8, A4.16 |
| 9 | Resample rule per resamplable column (`FIRST`/`LAST`/`MAX`/`MIN`/`SUM`, or none) | `AI_column_catalog.resample_aggregation` | A4.18 |
| 9b | **Summary rules (G18, see section 1a)**: per measure, whether it adds up across entities on one date (`cross_entity_aggregation` SUM or deliberately NULL) and over time (item 9); `semantic_type` (MEASURE, IDENTIFIER, DIMENSION, TIME) and `group_by_allowed` decided per column, not defaulted | `AI_column_catalog.cross_entity_aggregation`, `semantic_type`, `group_by_allowed` | A4.18 |
| 10 | Safe joins to existing tables: columns, temporal rule (`EXACT_DATE`, `AS_OF` on the availability date, `EFFECTIVE_DATED`, `CURRENT_STATE`), output grain, pre-aggregation | `AI_catalog_relationships` | A4.17 |
| 11 | Searchable description words (asset class, source, measure, abbreviations, the Indonesian words a user types: "kurs", "inflasi", "suku bunga", "laba bersih", "harga minyak") | table and column descriptions | A4.19 |
| 12 | Derived columns (if any): formula, interpretation, recommended use, misuse warning, evidence | `Feature_Catalog` (section 1c) | A4.16 |
| 13 | Typical questions (3–5) with their expected answers, for the golden tests | this plan's test list | — |
| 14 | **What a missing row means** (added 2026-10-09): `DENSE` (every expected period has a row; absent = missing data), `ACTIVITY_ONLY` (a row only when something happened) or `NOT_APPLICABLE` (no time column); review state | `AI_table_catalog.row_presence`, `row_presence_status` | A3.15 |
| 15 | **Indonesian meaning per AI column** (added 2026-10-09): written or machine-translated once, `DRAFT` until reviewed; without it the Excel `kolom` sheet shows the English text marked "teks Inggris" | `AI_column_catalog.description_id`, `description_id_status` | A3.15 |
| 16 | **Freshness and coverage** (added 2026-10-09): the expected delay of the newest row (`freshness_sla`; 1 day for the daily IDX tables today; a monthly release or quarterly reports need their own value, decided per source), whether coverage is tracked, and how coverage is written (section 2, row 3) | `AI_table_catalog.freshness_sla`, `coverage_enabled`; `AI_data_coverage` | A2.9 |
| 17 | **Point-in-time availability** (added 2026-10-09): observation date column, availability column (release or filing date), availability rule, point-in-time status | `Table_Catalog` availability columns (V8) | A2.7 |
| 18 | **Fixed category values** (added 2026-10-09): a category column whose set is fixed (tenor, series type, report type, contract month) declares it as a single-column `CHECK (column = ANY (ARRAY[...]))` so the Governor matches filter values | migration | A1.4 |
| 19 | **Official metrics** (optional, added 2026-10-09): values a user asks for by name over periods (BI-Rate, the latest CPI, USDIDR close) | `AI_metric_catalog` | — |
| 20 | **Reader words** (added 2026-10-09): how the table and its unit read for a person ("data makro BPS", "kurs JISDOR", "Rp per USD"); a monthly or quarterly table's period word ("bulan", "kuartal") | catalog descriptions; reader texts derived from the catalog (section 2, rows 10–12) | — |
| 21 | **Refresh and load** (added 2026-10-09): the loader service, its schedule, its load log, and who is told when it fails | loader app, `RAILWAY_CHANGELOG.md`, `.railway/railway.ts` | A5.21–23 |

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

## 1b. Questions per asset class (added 2026-10-09)

Part C lists the risks; these are the decisions that settle them, asked before the first load of each class.

| Class | Decide with the user | Part A / C |
|---|---|---|
| Macro (BI-Rate, CPI, GDP, reserves, money supply) | one table per series family or one long table with `series_id` in the key; reference period plus `release_date`; vintages kept or "latest revision" stated; unit per series (index, %, IDR bn, USD m) in the grain when mixed; joins to daily data `AS_OF` backward on `release_date` | A2.7, A1.1, A3.11, C look-ahead, revisions |
| Fundamental (financial statements, ratios) | period type (quarter, half, year; cumulative or quarterly flow); fiscal period end versus filing date (availability); restatements kept as versions; reporting currency (some IDX issuers report in USD) and scale (reports in thousands or millions); consolidated or parent; TTM and ratios as Features (section 1c), not stored raw | A2.7, A3.11, A3.14 |
| FX | quote convention (`USDIDR` = IDR per 1 USD), the fixing or close used (JISDOR, market close, time zone), mid or bid/ask; 24/5 calendar against IDX days, joined `AS_OF` backward | A1.2, A2.5–6, C calendar, currency |
| Cross-market (foreign indices, ADRs, US yields) | exchange calendar and time zone (a US close lands on the next Jakarta date); index level is never summed; total-return or price index | A2.5–6, A3.14, C time zones |
| Commodities | spot or futures; for futures the contract and roll rule (continuous series method); unit (USD/bbl, USD/t, USD/oz) and currency; exchange and time zone | A3.11, A3.14, C continuity |

## 1c. Derived Feature tables (added 2026-10-09)

A Feature table computed from the new raw tables needs, in addition to section 1:
- one `Feature_Catalog` row per column and version: formula, analytical interpretation, recommended use, misuse
  warning, semantic review status, validation-evidence paths; then `scripts/audit_feature_catalog_semantics.py`
  (`AGENTS.md` step 5);
- `Feature_Relationship_Catalog` for safe Feature joins, and `AI_catalog_relationships` for the AI;
- `AI_calculation_catalog` rows inserted by the same migration (V5: no sync fills them);
- coverage as `expected` from its source (the way Feature 02/03 are derived from Broker Summary), or actual;
- a refresh path: the existing Feature 01 worker and its queue serve the stock price table only; a new Feature table
  needs its own job or worker, its schedule and its `freshness_sla`;
- an independent validation (the pattern of `scripts/validate_feature_02.py` / `validate_feature_03.py`) before
  `semantic_review_status` and `documentation_status` move past their draft values.

## 2. Backend places that list tables by hand or assume today's data (found 2026-10-01, re-checked 2026-10-09)

Each must be handled for a new table; the plan replaces each with a value derived from the catalog (user rule: derive,
do not enumerate). "Current state" is the code and live catalog on 2026-10-09. Rows 7–14 were found on 2026-10-09.

| # | Place | What it hard-codes or assumes | Current state (2026-10-09) | Proposed: derived from (layer) |
|---|---|---|---|---|
| 1 | `scripts/provision_market_sql_governor_login.py` `APPROVED` | tables the Governor login may SELECT | still 5 catalogs + 7 tables. **Already drifted:** migration `20260927_006` granted the two history tables to `market_ai_sql_reader`, so a re-run would now stop with `extra=[IDX_Broker_Profile_History, IDX_Stock_Universe_History]` (read from the code, not run). `PROJECT_CONTEXT.md` still says "7 approved market tables" | expected set = the AI catalogs + every active `BOUNDED_READ` row of `AI_table_catalog` (backend, the script verifies equality) |
| 2 | `apps/market-ai-orc/app/tools/preview.py` `PreviewTable`, `ORDERING`; DB function `public.ai_preview_table_rows` (migration `20260923_002`) | the 20-row preview tables and their order | still the 7 original tables; the history tables are already not previewable | a `preview_order` column in `AI_table_catalog`; one generic function |
| 3 | `apps/ai-data-coverage/coverage_job.py` `RAW_SOURCES` | which tables get coverage, their entity/date columns | still by hand; a new table gets no `AI_data_coverage` row, so V6 fails | `AI_table_catalog` (entity and time columns are already there, `coverage_enabled`); coverage written by the loader itself (C06) |
| 4 | `apps/market-python-sandbox/app/service.py` `PRICE_TABLES` and the corporate-action note in `market-ai-orc` `orchestrator.py` | which tables carry the dividend/split warning | still the IDX price and Feature 01 tables | the adjustment basis declared per column (Part A3.14) |
| 5 | `apps/market-ai-orc/app/tools/research_planner.py` `ENTITY_TOKEN`, `NOT_ENTITIES` | ticker-shaped entity detection (4–6 capitals) | unchanged; a series code with digits or underscores is not seen, a 6-letter FX pair is | the table's own entity values (`ANSWER_INTEGRITY_FIX_PLAN.md` / G13-1b) |
| 6 | `scripts/sync_database_catalog.py`, `scripts/sync_database_schema.py` | strict catalog completeness (checks, not lists) | unchanged; they do not touch the `AI_*` catalogs | unchanged: they are the gate |
| 7 | `apps/market-ai-orc/app/orchestrator.py` `OUTSIDE_DATA_RULE`, `OUTSIDE_DATA_WEB_RULE`, `OUTSIDE_DATA_RESEARCH_RULE` (system prompt) | "Data the catalog does not contain (for example macro data, yields, fundamentals, or news) … is looked up with research_web … for market data the database wins" | the examples become false as soon as macro or fundamental tables exist; the model is told to go to the web for them | one rule without examples: anything the catalog holds is read from the database, the web only for what it does not hold (prompt; a prompt snapshot per `AGENTS.md`) |
| 8 | `apps/market-ai-orc/app/tools/web_research.py` description of `research_web` | "Information that is not in the market database" | same as row 7, in the tool contract | "not in the database" (`Tool_Catalog` round, `AI_TOOLS.md`) |
| 9 | `apps/market-ai-orc/app/tools/reference.py`: the database check before a web lookup | only the static reference tables (no time column) are compared with the asked attribute | a value the database holds as a dated series (BI-Rate, USDIDR, net income) is not checked: the web call runs | the check covers every visible table: the asked attribute against all visible columns and descriptions, the newest value read through the Governor (backend guarantee, not prompt) |
| 10 | `apps/market-ai-orc/app/conversation_router.py` route classes | FACT and ANALYSIS are defined over "market data"; EXPLORE's example is "macro context plus stock candidates" | a macro or fundamental calculation reads as outside the data routes | classes defined over "the data in the catalog" (router criteria: `AI_ROUTER.md` and the router benchmark before deploy) |
| 11 | `apps/market-ai-orc/app/user_texts.py` `EXPORT_READING` (`period`, `group`) | "({calendar} hari bursa)", "sumber punya data pada {source} hari" | wrong words for a monthly or quarterly table, or a 24/5 FX table | the period word from `supported_frequencies` / `time_semantics` ("tanggal", "bulan", "kuartal") (reader text) |
| 12 | `apps/market-ai-orc/app/user_texts.py` `SOURCE_NAMES` (`fact` and `metric` = "data pasar"), `WARNING_LINES["FREQUENCY_GAPS"]` ("Sebagian saham …") | reader labels that assume stock data | a macro value would read as "data pasar", a gap as "saham" | the label from the table's `data_domain` / `entity_type` (reader text) |
| 13 | `apps/market-ai-orc/app/freshness.py` | for an SLA below 7 days, age counts Monday–Friday | right for IDX; for a 24/5 FX table about right; public holidays not in the catalog | unchanged until a calendar per table exists (A2.6) |
| 14 | `apps/market-ai-orc/app/catalog_summary.py` (prompt summary, off on dev) and `MAX_DISCOVERED_TABLES = 50` | at most 24,000 characters, then without column descriptions, then no summary; discovery without a keyword lists 50 tables | many new tables push the summary out (if switched on) and past 50 tables discovery needs a keyword | keep off, or summarise by domain; searchable descriptions (item 11) carry discovery |

Method guides and research engines (event study, backtest, the `saniti` helpers) were built on IDX stock prices; using
them on macro or FX series is a new method decision, and a guide change needs a new guide version and `AI_TOOLS.md`.

## 3. Steps for one new table

1. Section 1 answers (and 1b, 1c where they apply) agreed with the user; Part A checklist passes.
2. Forward migration: table, keys, indexes (measured with `EXPLAIN (ANALYZE, BUFFERS)` on the planned query patterns),
   `Table_Catalog` (with the availability columns), `Column_Catalog`, the `AI_*` catalog rows (`AI_table_catalog` with
   subject metadata, `row_presence`, `freshness_sla`; `AI_column_catalog` with units, rules, `value_time_basis`,
   `description_id`; relationships; calculation rows for Features), `GRANT SELECT` to `market_ai_sql_reader`.
3. Loader: idempotent upsert, load log, coverage written in the same transaction, auth failures stop the load.
4. Dry run on dev (temporary job), apply, read back; `sync_database_catalog.py` and `sync_database_schema.py`.
5. Tests below; then expose (`is_active`, `ai_access_level = 'BOUNDED_READ'`).
6. Records: `DATABASE_CHANGELOG.md` (source, checksum, rows, range, verification), `RAILWAY_CHANGELOG.md`,
   `ERRORS_AND_SOLUTIONS.md` for anything found.

**Must land before the first table of a new domain is exposed** (2026-10-09; each is a proposal awaiting the user's go,
not built):
- section 2 rows 7–10 (the model is told the data is outside the database, and nothing in the backend stops a web
  lookup for a value the database holds): without them the table is loaded but the AI answers macro and fundamental
  questions from the web;
- row 3 (coverage): without it the AI does not see the table's date range;
- row 1 (Governor login check): without it the next re-provisioning stops;
- rows 11–12 (reader words) for monthly and quarterly tables.

Rows 2, 4, 5, 13 and 14 can stay manual or unchanged for the first tables, with the manual step recorded in the
migration.

**Loading without exposing.** Data can be loaded and checked first with `is_active = false` (V2): the Governor and the
AI do not see it, and the checks of section 4 that read the table directly can run. Exposure is a separate step.

## 4. Tests (fixed per new table)

| Level | Test | Proves |
|---|---|---|
| Catalog | `sync_database_catalog.py` strict; a Part A checker (new script, not built) over the new rows: units, subject metadata, `row_presence`, `freshness_sla`, `description_id`, resample and summary rules, relationship semantics, searchable words | nothing is missing or guessed |
| Visibility (added 2026-10-09) | `discover_catalog` with the table's own search words finds it; `get_catalog_details` COLUMNS shows units and summaries; COVERAGE shows its date range and freshness; `lookup_reference` lists it if it has no time column | the AI can see and find it |
| Database first (added 2026-10-09) | a question whose answer is in the new table (for example "berapa BI-Rate terakhir", "kurs USDIDR kemarin") is answered from the database with a data reference, without a `research_web` call | the AI uses the table instead of the web |
| Governor | extraction of one entity and of all entities over 400 days; row count equals `SELECT count(*)` (G13); refusal names a valid narrowing | limits and estimates hold |
| Join | the new table with stock prices via its relationship (`AS_OF` for macro on `release_date`, the first live AS_OF; calendar mismatch IDX vs 24/5); row counts before and after | no look-ahead, no dropped or duplicated rows |
| Sandbox | DataNeed validation, bundle, `saniti.resample` against the source for one known month | helpers work on the new grain |
| Summary (G18) | for each SUM-rule measure: a summary across entities equals `SELECT … GROUP BY` computed independently; a NULL-rule measure is refused `AGGREGATION_NOT_ADDITIVE`; the catalog `summaries.example` is approved by the validator; a multi-unit table offers no SUM | the catalog rules give right totals and refuse wrong ones |
| Answer | value references to the new identity column (`rows[series=USDIDR]`), lists, nulls (P14); no positional row in a keyed table (M44) | figures stay bound to their entity |
| Export (added 2026-10-09) | an Excel export from the new table: `kolom` sheet meanings in Indonesian, the `definisi` row rule and completeness line with the right period word (monthly: not "hari bursa") | the file a person downloads reads right |
| Golden | the 3–5 user questions of item 13, with ground truth by SQL | end-to-end correctness |
| Coverage | coverage row appears after the first load without waiting for the nightly job | freshness is visible |

## 5. Before this plan runs

- Done: `ANSWER_INTEGRITY_FIX_PLAN.md` items M44, P14 and G13 (value references by key, null handling, counted rows)
  are built; G18 phase 1 (summary rules) is built.
- Open: which of the section 3 "must land first" proposals the user approves, and in which order relative to the
  first load.
- Data can be loaded before those land if it stays unexposed (`is_active = false`).
