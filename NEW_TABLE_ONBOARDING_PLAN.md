# Plan 2: onboarding a new table for the AI (macro, fundamental, FX, cross-market, commodities, Features)

Status (2026-10-20, later): **first integration executed** (EXEC-ONBOARD-1: `Price_Fixed_Income` through the view `Price_Fixed_Income_Final`, `Universe_Fixed_income`, `Feature_04_Technical_Indicator`; validated L0-L3, section 6.6); **section 7 is the ingestion guideline** for the next raw table or Feature.
Earlier status (2026-10-20): plan only, not executed. Re-inspected 2026-10-20 at `main` `6850d7f` for the first two tables
to integrate, `Price_Fixed_Income` (raw) and `Feature_04_Technical_Indicator` (Feature): section 6 (user 2026-10-20:
"Ini akan jadi 2 table (raw dan feature) yang kita integrate pertama kali … tinggal dibuat guidelinenya"); section 1b
gains the fixed-income class; section 2 gains the current state of 2026-10-20.
Earlier status (2026-10-09): plan only, not executed. Recorded 2026-10-01 (user decision: record now, run later); section 1a
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
| Fixed income (government bonds; added 2026-10-20) | price and yield in one value column are different quantities: the metric (`metric_type` price / yield_to_maturity) and its unit (`value_unit`) stay in the grain, nothing sums across instruments; only final daily rows are visible (`is_final`, timeframe `1D`); market calendar and close time per country (`Fixed_Income_Market_Schedule`); the identity the AI uses (`ticker`) and its universe (`Universe_Fixed_income`, exposed as a reference table); tenor and country as searchable words; yields are levels (LAST over time, never SUM) | A1.1, A2.5–6, A3.11, A4.18, C units |
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

**Current state 2026-10-20 (read from the code at `6850d7f`):** rows 1–5, 7–9, 11–14 unchanged. Row 1:
`APPROVED` still lists 5 catalogs + 7 tables. Row 3: `RAW_SOURCES` still lists `Price_Stock_Indonesia_IDX` and
`IDX_Broker_Summary` only, and `validate_access_contract` forbids the job to read Feature tables, so a Feature's coverage
can only be derived (`reference_for`) from one raw source; a Feature built from two raw sources (Feature 04: equity
prices and fixed-income prices) is new. Row 4: `PRICE_TABLES = {Price_Stock_Indonesia_IDX, Feature_01_Stock_Daily}`.
Row 7: `OUTSIDE_DATA_RULE` (orchestrator, standard and fast prompts) still names "macro data, yields, fundamentals" as
outside the catalog; it becomes false for bond yields as soon as `Price_Fixed_Income` is visible. Row 8: `research_web`
still says "not in the market database". Row 10 depends on the pending router decision (`prompts/fastlane_unified/`).
New since 2026-10-09: fast-lane category values come from single-column `CHECK` lists (`tools/catalog.py`
`check_value_lists`; governor `catalog_contract.check_value_lists`), entity names and aliases (`AI_column_catalog.
entity_name`, migration `20261015_014`), the table download with input sheets (row limit per input), and value
references by key; none lists tables by hand. There is no row-level filter in `AI_table_catalog` or the Governor:
a table is visible whole, so a table holding provisional rows needs a view (section 6).

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

## 6. First integration: `Price_Fixed_Income` (raw) and `Feature_04_Technical_Indicator` (Feature) (2026-10-20)

User 2026-10-20: expose both tables to the AI; join Feature 04's candle and indicator columns to the calculation
catalogs so the AI can use the stored column instead of computing it; every Orc part (tools, catalogs) updated; map and
inspect first, everything from the code; a method to check that the AI knows the tables exist. **Plan, not executed.**
Facts below are from the code and documents at `main` `6850d7f` (`DATABASE_SCHEMA.md` synced from the live database
on 2026-10-12); the live values marked "live read" are not yet read in this inspection.

### 6.1 Current state of the two tables

| | `Price_Fixed_Income` | `Feature_04_Technical_Indicator` |
|---|---|---|
| Content | final daily OHLC per fixed-income instrument and country; `metric_type` `price` or `yield_to_maturity` in the same `open/high/low/close` columns, `value_unit` per row; finality evidence (`is_final`, `market_close_at`, `finalized_at`, `source_bar_time`) | 57 columns: identity, `close`, SMA/EMA/RSI/MACD/ATR/Bollinger/ADX, 25 TA-Lib candle codes (`cdl_*`), `inside_bar`, Pine SMI and swing state, calculation metadata; equity 844 tickers / 1,318,633 rows and bonds 24 tickers / 60,409 rows (`DATABASE_CATALOG.md`) |
| Key | `(tradingview_symbol, date, metric_type, "Timeframe")`; FK `(ticker, metric_type)` → `Universe_Fixed_income` | `ticker, trade_date, timeframe` with `asset_type` (`equity`/`bonds`) |
| Visible to the AI | **no**: no `AI_table_catalog` row, no grant to `market_ai_sql_reader`, not in `APPROVED`, `RAW_SOURCES`, `ORDERING` | **no**: "No AI allowlist or permission change" (`DATABASE_CATALOG.md`); `Feature_Catalog` v4 has 57 active definitions |
| Refresh | fixed-income crons per market (`apps/fixed-income-price-cron`), schedule in `Fixed_Income_Market_Schedule` | event-driven `feature-04-worker` after final price changes |

### 6.2 Where the change lands (code map, 2026-10-20)

| Layer | Place (read at run time) | Change for these two tables |
|---|---|---|
| Database grants | `GRANT SELECT … TO market_ai_sql_reader` (V1); `scripts/provision_market_sql_governor_login.py` `APPROVED` | grant the exposed objects; add them to `APPROVED` (fix the row-1 drift for the history tables in the same change) |
| Visibility | `AI_table_catalog` (`is_active`, `ai_access_level`), read by Orc `tools/catalog.py` `VISIBLE_TABLES` and Governor `policy.py` | one row per exposed object with subject metadata, `row_presence`, `freshness_sla`, `coverage_enabled` |
| Columns | `AI_column_catalog` → Orc `get_catalog_details` COLUMNS, Governor `catalog_contract.py`, sandbox `app/logical.py`, `runtime/validator.py`, `runtime/saniti_session.py`, `tools/metric.py` | every column with unit, `semantic_type`, permissions, resample and cross-entity rules, `value_time_basis`, `description_id`; Feature 04 state columns (`tracking_*`, `temp_*`, `*_bar`, `calculation_version`, `calculated_at`) `ai_allowed = false` |
| Category values | single-column `CHECK` lists (`metric_type`, `asset_type` exist) | `Timeframe`, `Country`, `value_unit` need a `CHECK` or stay free text (decision) |
| Joins | `AI_catalog_relationships` (Governor, DataNeed, `saniti` join helpers) | Feature 04 ↔ `Price_Stock_Indonesia_IDX` / `Feature_01_Stock_Daily` on `(ticker, trade_date/date)` EXACT_DATE (safe only for equity rows); Feature 04 ↔ bond price view on `(ticker, trade_date/date)`; bond price view ↔ `Universe_Fixed_income` |
| Stored calculations | `AI_calculation_catalog` (V5: only a migration fills it) → `get_catalog_details` CALCULATIONS | one row per indicator family and per candle family on `Feature_04_Technical_Indicator`, `implementation_ref` naming the related `AI_formula_reference` ids |
| Formula reference | `AI_formula_reference` (200 rows from `AI_Calculation_Formula.xlsx`; FORMULAS section and `discover_catalog` formula matches) | indicator and candle formulas exist: CALC_021 SMA, 022 EMA, 028 RSI Wilder, 032–034 MACD, 040 ADX, 042 ATR Wilder, 049/050 Bollinger, 161/162 engulfing, 165 doji ratio, 166 hammer geometry, 167 inside bar. Orc change: a formula entry shows the stored column that holds it ("stored in Feature_04_Technical_Indicator.rsi_14, v4"), read by joining `AI_calculation_catalog.implementation_ref`; a stored TA-Lib code is described as related, not identical, to the reference definition (TA-Lib engulfing returns +100/−100 for bullish/bearish; CALC_161 is bullish only) |
| Coverage | `apps/ai-data-coverage/coverage_job.py` `RAW_SOURCES` (hand list; Feature tables never read) | add the bond source; Feature 04 coverage derived from two raw sources by `asset_type` (code change), or `coverage_enabled = false` for the first release (decision) |
| Freshness | `app/freshness.py` (Monday–Friday below 7 days) | `freshness_sla` 1 day for both; bond markets with other holidays read as late on those days (known limit) |
| Preview | `tools/preview.py` `ORDERING`, DB function `ai_preview_table_rows` | add both (or leave out of preview for the first release; decision) |
| Corporate actions | sandbox `PRICE_TABLES` | add Feature 04 (its equity `close` is the raw price); bonds have no corporate actions |
| Prompt and tools | `orchestrator.py` `OUTSIDE_DATA_RULE`, `OUTSIDE_DATA_WEB_RULE`, `OUTSIDE_DATA_RESEARCH_RULE` (standard and fast prompts), `tools/web_research.py` `research_web` description, `tools/reference.py` database check before a web lookup | remove "yields" from the outside-the-catalog examples; the web check covers a bond yield the catalog holds; a candle/indicator rule: a stored Feature column is read before an indicator is computed; prompt snapshot and `AI_TOOLS.md` |
| Entities | `tools/research_planner.py` `ENTITY_TOKEN` (`[A-Z]{4,6}`), entity names (`entity_name`) | bond tickers (live read) may not match the token; `instrument_name` marked as the entity name column |
| Method guides | `AI_method_guide` v8 | a note that candle and indicator questions start from Feature 04; new guide version |
| Records | `Table_Catalog`, `Column_Catalog`, `Feature_Catalog`, `Tool_Catalog`, `DATABASE_SCHEMA.md`, `DATABASE_CHANGELOG.md`, `AI_TOOLS.md`, `PROJECT_CONTEXT.md` (approved-table count) | per `AGENTS.md` step 5 |

### 6.3 Decisions before execution

1. **Final rows only.** No row filter exists in the catalog or the Governor. Proposed: expose a view
   `Price_Fixed_Income_Final` (`WHERE is_final AND "Timeframe" = '1D'`) instead of the base table; the base table stays
   hidden. Live read first: rows with `is_final = false` and the `Timeframe` values. The same live read for
   `Price_Stock_Indonesia_IDX` (already exposed, also has `is_final`): if it holds provisional rows, the AI sees them
   today (separate finding).
2. **Reference table.** Expose `Universe_Fixed_income` (country, instrument, unit) as a reference table (no time column),
   so `lookup_reference` and joins can name an instrument.
3. **Feature 04 cross-asset.** `asset_type` subject metadata NULL (mixed) with `asset_type` as a filter dimension; join
   rules per asset (live read: no ticker in both universes); the Pine state columns hidden.
4. **Coverage** derived from two sources (code) or off for the first release.
5. **Preview** in or out for the first release.
6. **Indonesian meanings** (`description_id`) written as DRAFT by the agent, reviewed by the user.
7. **Live reads** need database access: a temporary Railway TCP proxy (as in `PROJECT_CONTEXT.md`) or a one-off job;
   read-only queries only.

### 6.4 Validation: does the AI know the tables exist (prepared, not run)

| Level | Method | Pass |
|---|---|---|
| L0 Database (no model) | read-only queries: catalog rows, grants, view row counts against the base table with the filter, `sync_database_catalog.py` strict | every link V1–V8 present; counts equal |
| L1 Governor contract (no model) | `POST /v1/catalog/contract` for the two tables from a one-off job; a bounded `/v1/extract` of one bond and one equity ticker with `SELECT count(*)` ground truth | contract loads, units and values present, counts equal (G13) |
| L2 Orc tools without a model | the manual agent (`AI_ENABLE_MANUAL_AGENT`, model `saniti/claude-manual`): a runner answers each step with a fixed tool call (`discover_catalog` "yield obligasi", "candle hammer"; `get_catalog_details` COLUMNS, CALCULATIONS, FORMULAS for `rsi`) and records the tool results | the tables are found by their own words; COLUMNS show units; CALCULATIONS list the Feature 04 rows; the RSI formula names `rsi_14` |
| L3 Model awareness (paid, fast lane) | fixed questions through `orc-test-runner`: (a) "Berapa yield obligasi pemerintah Indonesia 10 tahun terakhir?" (b) "Saham apa yang membentuk pola hammer di sesi terakhir?" (c) "RSI 14 BBRI hari ini berapa?" (d) "Bandingkan pergerakan yield SUN 10 tahun dengan IHSG sebulan terakhir" (e) control: "Berapa inflasi Indonesia terakhir?" (still web) | (a)–(d) read the new tables through a data need, no `research_web` for the stored values, no `run_python` recomputation of a stored indicator; figures equal SQL ground truth; (e) unchanged |
| L4 Regression | Orc, Governor, sandbox, coverage test suites; the existing A/B questions t1, j2, s1 | no new failure; no change in their tables and answers caused by the new catalog rows |

### 6.5 What becomes the guideline

After this integration the steps that worked (and the ones that needed code) become the ingestion guideline for the
next raw table or Feature: the section 1 answers as a template file, one migration pattern (view if needed, catalog
rows, grants, calculation rows), the hand lists of section 2 replaced by catalog-derived values where this integration
had to touch them, and the L0–L4 checks as a reusable runner suite.

### 6.6 Result (2026-10-20, executed)

User: "Ok view saja ya untuk no 1. Jalankan." Decisions: view for final rows (1), universe as a reference table (2),
Feature 04 coverage from its two raw sources (3), live reads by one-off read-only jobs (4); preview in; Indonesian
meanings DRAFT. Migrations `20261020_001` (objects, catalogs, grants, preview) and `20261020_002` (Tool_Catalog round Z);
code `2ba744e`, fixes `a474a65` (M194) and `7e159c6` (M195). Measured, not assumed: the Feature 04 primary key
`(ticker, trade_date, …)` answers the latest-session and one-week queries in 8-14 ms (PostgreSQL skip scan), so no index
was added. Validation: L0 and L2 passed at the first attempt; L3 found two faults that no catalog check could find (the
router's hand-written description of the warehouse, and a tool note that let the model prefer the reference formula
over the stored column) and passed after the fixes; (d), (e) and the paid A/B regression were left for later (credit).
Details: EXEC.md EXEC-ONBOARD-1, DATABASE_CHANGELOG.md, RAILWAY_CHANGELOG.md, ERRORS_AND_SOLUTIONS.md M194-M195.

## 7. Ingestion guideline: onboarding the next raw table or Feature (from EXEC-ONBOARD-1)

What worked for the first raw table and the first Feature, in the order it has to happen. Every step reads the code and
the live database; nothing is written from memory. Ask the user only the decisions in 7.2.

### 7.1 Read before writing (one read-only job, no model)

1. The table's live shape: columns, types, key, CHECK lists, indexes, row count, date range, nulls per column, rows that
   must not be seen (provisional, other timeframe), whether the declared key is unique on the rows to expose.
2. Its `Table_Catalog`, `Column_Catalog` and, for a Feature, its active `Feature_Catalog` rows (unit, semantic role,
   aggregations, definition, calculation, version) and `Feature_Relationship_Catalog`.
3. Three model rows of each AI catalog for a comparable exposed table (`AI_table_catalog`, `AI_column_catalog`,
   `AI_catalog_relationships`, `AI_calculation_catalog`, `AI_data_coverage`) and the CHECK constraints of those catalogs
   (`DATABASE_SCHEMA.md`).
4. Overlap with exposed entities (does a code mean two things?), the units per row, and the `AI_formula_reference` ids
   the Feature implements (read their definitions: parameters, tie and zero conventions).

Tools: `scratchpad/onboard-read/job.py` pattern (`default_transaction_read_only=on`, `OUT {json}` lines), run on
`orc-test-runner` with `DATABASE_URL` set only for the run (`dbjob.sh`).

### 7.2 Decisions for the user

- Rows the AI may not see: a view with the filter (the catalog and the Governor have no row filter) or the base table.
- Reference tables to expose with it (names, country, tenor) and which column is the entity name (`entity_name`).
- Hidden columns (calculation state, load bookkeeping, source mappings): `ai_allowed = false`.
- Coverage: which raw source each dataset derives from, or `coverage_enabled = false` for the first release.
- Preview in or out; subject metadata (`data_domain`, `entity_type`, `asset_type`; NULL asset type for a cross-asset
  Feature).

### 7.3 One forward migration (template: `database/migrations/20261020_001_onboard_fixed_income_and_feature04.sql`)

1. Preflight: nothing registered yet; the expected column and `Feature_Catalog` counts; roles and referenced formula rows
   exist.
2. The view (if decided), `REVOKE ALL FROM PUBLIC`, `GRANT SELECT` to `market_ai_sql_reader` (and
   `market_ai_preview_owner` when previewed; `pgweb_reader` when present).
3. `AI_table_catalog` (description written for discovery: the words a user would type, in English, with the key
   filters to apply), `AI_column_catalog` from `information_schema.columns` joined to a VALUES list or `Feature_Catalog`
   (unit, semantic type, aggregations, resample rule, `value_time_basis`, description and DRAFT `description_id`).
4. `AI_catalog_relationships` with `supported_join_semantics` and time columns; every key column exposed.
5. A Feature: one `AI_calculation_catalog` row per active definition (the `20260922_001` pattern); a column that holds a
   reference formula names `AI_formula_reference:<id>` in `implementation_ref` and `parameters.formula_reference`
   (`STORED_VARIANT` or `RELATED_NOT_IDENTICAL` with the difference read from the definitions).
6. `public.ai_preview_table_rows` replaced when previewed (and `app/tools/preview.py` `ORDERING`; the test compares both).
7. `Table_Catalog` / `Column_Catalog` for a view; migration path and `related_functions` on the touched rows.
8. A verify block for every count, privilege (the AI reader cannot read a hidden base table) and relationship key.

Rehearse with DRYRUN jobs (body without COMMIT, probes as the AI roles, bounded `EXPLAIN (ANALYZE, BUFFERS)` of the
high-frequency patterns, ROLLBACK) until clean; check the orc logs for active `edge_` runs; APPLY; read back; add the
hash to `APPLIED.sha256`.

### 7.4 Hand-written places still to update (until each is derived from the catalog)

| Place | What to add |
|---|---|
| `scripts/provision_market_sql_governor_login.py` `APPROVED` | the exposed objects |
| `apps/ai-data-coverage/coverage_job.py` `RAW_SOURCES`, `SNAPSHOTS`, derived Feature functions, `FORBIDDEN_FEATURE_TABLES` | raw source, snapshot, derivation |
| `apps/market-ai-orc/app/tools/preview.py` `PreviewTable`, `ORDERING` | when previewed |
| `apps/market-python-sandbox/app/service.py` `PRICE_TABLES` | a table holding split-adjusted stock prices |
| `apps/market-ai-orc/app/conversation_router.py` `WAREHOUSE_SCOPE` | the new data domain in a few words (M194) |
| `apps/market-ai-orc/app/orchestrator.py` `OUTSIDE_DATA_*` examples, `tools/web_research.py` description | remove the domain from "outside" examples |
| `apps/market-ai-orc/app/tools/research_planner.py` `ENTITY_TOKEN`, `NOT_ENTITIES` | entity codes of another shape |
| `scripts/generate_tool_catalog_migration.py` | a round for every tool whose contract text changed |

After an orc prompt change: `scripts/snapshot_system_prompt.py record`, the approved sentence in
`tests/test_prompt_pass2.py`, the context budget of `tests/test_orchestrator.py` if it moved; `scripts/generate_ai_router_doc.py`
after a router change.

### 7.5 Validation (reusable)

| Level | How | Pass |
|---|---|---|
| L0 | read-back queries in the APPLY job | counts, grants, view rows = base filter |
| L1/L2 (no model) | `scratchpad/onboard-l2/job.py` pattern: coverage job once, then orc's own tools (`build_default_registry`) as role `market_ai_orc` | found by the user's words; units; hidden columns absent; formulas show `stored_in`; preview rows |
| L3 (paid, a few cents each) | `orc-test-runner` suite like `suites/onboard_l3_20261020.json` (fast lane), then the answers from `AI_conversation_turn` against SQL ground truth | route is a data route; the new table is read; stored values equal SQL; no web for stored values; no recomputation of a stored indicator |
| L4 | full orc, Governor, coverage suites; the A/B questions when credit allows | no new failure |

Only L3 finds what the model does with the catalog: both faults of the first integration were found there.
