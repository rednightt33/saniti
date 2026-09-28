# Errors and solutions

Every error, defect and data problem found in this project so far, with its root cause, the solution and its status. The purpose is to avoid repeating them. The main use ahead is the scale-up to other data (cross-asset: FX, commodities, bonds, indices; macro: rates, inflation, GDP): Part A turns these errors into a data-format standard that every new source must meet before it is loaded, so all sources reach the database, the catalog and the AI in the same shape.

- **Part A** — the data-format standard for new sources (the checklist).
- **Part B** — the error catalog, by layer.
- **Part C** — errors to expect specifically from cross-asset and macro data.
- **Part D** — how to add an entry.

Sources: `RAILWAY_CHANGELOG.md`, `DATABASE_CHANGELOG.md`, `DATANEED_ARCHITECTURE.md`, the service READMEs, and the live test and stress-test reports of 2026-09-24 to 2026-09-26. Dates are when the error was found.

Status values:
- `FIXED`: the cause is removed and verified.
- `MITIGATED`: the effect is bounded or disclosed, but the cause remains.
- `OPEN`: known and not yet fixed.
- `BY DESIGN`: intended behaviour that looks like an error.
- `ACCEPTED`: a known limitation the user chose to keep.

---

## Part A — Data-format standard for new sources

A new table (any asset class, any frequency) is ready for the AI only when every item below holds. Each item names the errors in Part B it prevents.

### A1. Identity and grain

1. **One declared grain and primary key**, for example `(entity_id, date)` or `(entity_id, date, dimension…)`.
   - Every source dimension that changes the meaning of a value is part of the key: board, investor type, tenor, currency.
   - Never aggregate a source dimension away and keep a current-state attribute in its place. (D03, D04)
2. **One entity identifier column per table, with the same code system across tables**, for example `ticker` for IDX stocks.
   - A new asset class declares its identifier (`USDIDR`, an ISIN, a series code) in the catalog.
   - A mapping table links codes that differ between sources.
   - Entity codes are upper-case and trimmed.
3. **Subject metadata in `AI_table_catalog`** for every data table:
   - `data_domain`, `entity_type` and `asset_type`, as upper-case identifiers (`^[A-Z][A-Z0-9_]{1,39}$`, the DataNeed validator's rule);
   - `supported_frequencies` (`1D`, `1W`, `1M`, `1Q`, `STATIC`, …);
   - `time_semantics` in words.

   The model copies these values into every DataNeedSpec, so a missing or guessed value fails validation. (C02, C01)
4. **Category values are real values.** No placeholder such as the string `0` for "unknown": use NULL plus a documented reason. Validate category cardinality after every load, because broad and granular classifications have been stored swapped once. (D01, D02)

### A2. Time

5. **A typed time column**:
   - `date` for daily and lower frequencies;
   - `timestamptz` for intraday, with the exchange time zone stated in `time_semantics`.

   The sandbox helpers return the time column as `datetime.date` objects. Code and documentation must not assume strings or pandas timestamps. (S01)
6. **Trading calendar per source.** State which calendar the dates follow (IDX trading days, a 24/5 FX market, monthly release dates).
   - Do not insert weekend or holiday rows, and do not forward-fill silently.
   - Missing observations are flagged (`FREQUENCY_GAPS`), not invented.
   - For a daily candle, only the exact date is valid: never substitute a previous candle for a missing day. (D11)
7. **Reference period versus availability (macro).** A macro observation needs:
   - its reference period (`period_start`, `period_end`);
   - the date it became public (`release_date`);
   - its vintage, when revisions exist.

   Point-in-time joins use `release_date`, never the reference period, otherwise the analysis reads data before it existed (look-ahead). See Part C.
8. **Current-state reference tables are marked as such.** Examples: classifications, broker profiles.
   - When the attribute changes over time, keep effective-dated history (`effective_from`, `effective_to`) and register an `EFFECTIVE_DATED` relationship.
   - When the source delivers only the current state, capture history prospectively and bitemporally (pattern: migration `20260927_006`): effective period `[valid_from, valid_to)`, recorded period `[recorded_from, recorded_to)`, and an availability time kept apart from both. Never backdate the first snapshot; record the basis of each date (first capture, change captured, documented); keep superseded knowledge instead of overwriting it; and never read a key missing from one load as a delisting. Point-in-time joins use a validity that starts after the recording date, so nothing is used before Saniti had it. (D08)
   - Mark every column that repeats today's reference value on historical rows (`AI_column_catalog.value_time_basis = CURRENT_STATE`), so a point-in-time request refuses it and a descriptive one discloses it.
   - Otherwise every historical question gets the warning `HISTORICAL_REFERENCE_USES_CURRENT_STATE`. (D08)
9. **Full history, registered coverage.** Load all available history. Register actual min and max dates and the verification status in `AI_data_coverage`.
   - Recursive indicators (RSI, ATR, EMA, MACD, ADX) need about 250 observations before the first asked date. A table that starts at the first asked date answers them wrongly. (D14)
   - Illiquid entities also need their last value before a period. (D12)

### A3. Values

10. **Numeric columns are numeric**: `numeric` or `double precision`, never text.
11. **Every numeric column has a unit** in `AI_column_catalog.unit`: `IDR`, `USD`, `%`, `bps`, `index points`, `shares`, `lots`.
    - Store raw units, not display scales ("miliar").
    - A table that mixes currencies has a currency column.
    - An empty unit disables the sandbox's unit preflight. (D07)
12. **Percent or decimal is declared.** A return of 5% is either `5` or `0.05`, and the catalog says which.
13. **The sign convention is documented** (net buy positive, net sell negative; a yield change in bps). The answer gate parses signs, including a sign before a currency symbol. (P01)
14. **Price adjustment is declared**: unadjusted, split-adjusted or total-return. The price table today is unadjusted for dividends, and answers disclose it. (D10)
15. **NULL has one meaning per column**: "no activity" or "not available", stated in the column description.
    - A table that writes rows only when there was activity is **sparse**, and the catalog must say so; rolling values there are not defined on inactive days. (D05)
    - The same applies to zero-volume days.

### A4. Catalog and relationships

16. **Complete catalog rows before the AI sees the table**:
    - `Table_Catalog` and `Column_Catalog` (description, data type, unit);
    - the AI catalogs (`AI_table_catalog`, `AI_column_catalog`, `AI_catalog_relationships`, `AI_calculation_catalog`), including `ai_allowed` and `is_sensitive` flags decided per column, not defaulted;
    - `Feature_Catalog` for derived columns (formula, interpretation, misuse warning);
    - `Tool_Catalog` for new tools.

    Follow `AGENTS.md` step 5. (D18, C04)
17. **Every safe join is registered** with:
    - its join columns;
    - its temporal rule (`EXACT_DATE`, `AS_OF` backward, `EFFECTIVE_DATED`, `CURRENT_STATE`);
    - its output grain and `requires_preaggregation`.

    Joins across calendars (a daily stock versus a monthly macro series, or IDX dates versus FX dates) use `AS_OF` backward on the availability date. Grains that differ need pre-aggregation. (G05, G02, G03)
18. **Resample rules** (`resample_aggregation`: last, sum, mean, OHLC) for every column that can be resampled. Today they are NULL everywhere, so all resampling happens in the model's code. (D09)
19. **Searchable descriptions**: discovery matches keywords against table and visible column names and descriptions (M17). Write the words a user would search for into them: the asset class, the source, the measure and its common abbreviation (for example `CPI consumer price index inflation`, `USD IDR exchange rate`). A table that describes itself only as "Series table" cannot be found by keyword.
20. **Column names**: new tables use lower-case `snake_case`. Some existing tables use quoted names with spaces or capitals (`"Investor Type"`, `"Market Board"`, `"Ticker"`); they work through the catalog, but every consumer must quote them exactly.

### A5. Loading and operations

21. **Idempotent upsert on the natural key**, with `ingestion_time` set by the database (`statement_timestamp()`) and the source plus query date recorded.
    - Load results go to a PostgreSQL load log.
    - Source metadata and verification go to `DATABASE_CHANGELOG.md`.
22. **Authentication failures stop the load.** They must not mark the remaining dates `NEEDS_REVIEW`. Rate limits are respected by bounded concurrency. (D15, D16)
23. **Large reconciliations run in partitions** (per ticker range, per period), not as one query that exhausts PostgreSQL temporary space. (D17)
24. **Query patterns and indexes.** Define the high-frequency query patterns, and run a bounded `EXPLAIN (ANALYZE, BUFFERS)` before adding a large index.
    - The Governor refuses unfiltered requests longer than 400 days (`DATE_RANGE_TOO_LARGE`).
    - The sandbox bundle holds at most 2,000,000 rows / 256 MB by default.

    Size new sources so ordinary questions fit. (G01)

---

## Part B — Error catalog

### B1. Source data and database (D)

| ID | Found | Symptom | Root cause | Solution | Status | Lesson for new data |
|---|---|---|---|---|---|---|
| D01 | 2026-09-12 | `IDX_Stock_Universe`: 59 granular values under `Sector` and 12 broad values under `Industry` | The two columns were loaded swapped | One-transaction swap of all 844 rows, tested on one row first and checksum-verified (`DATABASE_CHANGELOG.md` 2026-09-12) | FIXED | Check the cardinality and meaning of classification columns after every load (A1.4) |
| D02 | 2026-09-24 | Three tickers have `Sector` = the string `0`; it appears as a sector in counts | Placeholder value from the source | None yet; answers show it as its own value | OPEN | Unknown = NULL plus reason, never a fake category (A1.4) |
| D03 | 2026-09-14 | `Feature_02_Broker_Rolling` v1 could not tell Domestic from Foreign activity | v1 summed `IDX_Broker_Summary."Investor Type"` away and stored the current `IDX_Broker_Profile.broker_type` | v2 grain `(ticker, market_board, broker, investor_type, date)` with the point-in-time source label, validated and cut over (migrations 034–046) | FIXED | Keep every meaning-bearing source dimension in the grain (A1.1) |
| D04 | 2026-09-14 | Feature 03 domestic/foreign columns used broker domicile | Built on the current broker profile, not the source investor type | Feature 03 v2 sums Feature 02 v2 by source `investor_type` (migration 047); identity check 0 violations | FIXED | Same as D03; current-state attributes do not belong in historical facts |
| D05 | 2026-09-26 | Rolling broker values such as `net_value_20d` missing on some dates | Feature 02 has rows only for partitions that traded on the date (sparse table) | Documented; the model must treat absence as "no activity" | OPEN | Declare sparse tables and the meaning of absence (A3.15) |
| D06 | 2026-09-26 | Broker questions for September answered LIMITATION | `IDX_Broker_Summary` and Features 02/03 end 2026-08-31; refresh is manual (`MANUAL_REFRESH_REQUIRED`) | None; the answers state the limitation correctly | OPEN | Every source needs an automated refresh or a visible freshness status in coverage |
| D07 | 2026-09-24 | The sandbox unit preflight had nothing to compare; the manifest showed `unit: null` for `close` | `AI_column_catalog.unit` is empty for the price table | None yet | OPEN | Units are mandatory for numeric columns (A3.11) |
| D08 | 2026-09-26 | Warning `HISTORICAL_REFERENCE_USES_CURRENT_STATE` on sector and industry analyses | Classification tables hold only the current state | Disclosed in every answer. IP1 Stage D (migration `20260927_006`, 2026-09-28): `IDX_Stock_Universe_History` and `IDX_Broker_Profile_History` capture every change prospectively (bitemporal, statement triggers), with EFFECTIVE_DATED relationships and an opt-in `POINT_IN_TIME` time basis that is refused, never silently replaced, where history does not reach. Dates before the first capture stay current-state only, and the `CURRENT_STATE_COLUMN` warning now also discloses current-state columns inside Feature tables | MITIGATED | Effective-dated history for attributes that change (A2.8) |
| D09 | 2026-09-26 | Every resampling is done by model code | `resample_aggregation` is NULL for every column | None yet | OPEN | Fill resample rules for new columns (A4.18) |
| D10 | 2026-09-26 | Returns differ from dividend-adjusted sources | Prices are stored as traded, not adjusted | Disclosed in answers ("harga sebagaimana tersimpan") | ACCEPTED | Declare the adjustment basis (A3.14) |
| D11 | 2026-09-07 | Daily runs leave some tickers without a candle (for example 20 of 844) | TradingView returned no candle dated on the target day | Exact-date rule: never substitute a previous candle; missing symbols are `PARTIAL`/`NEEDS_REVIEW` and retried by the recovery cron | BY DESIGN | Missing is recorded, never filled (A2.6) |
| D12 | 2026-09-26 | `period_return` reported 45 `NO_PRIOR_CLOSE`, where the plain convention gives 26 | A 1-observation `history_buffer` becomes a 12-calendar-day window on the market calendar, not per entity; illiquid tickers last traded earlier | Finding recorded; the helper substitutes nothing, so exclusions are visible | OPEN | Per-entity "last value before" needs its own lookup or a longer buffer (A2.9) |
| D13 | 2026-09-23 | Two analyses disagreed on the newest date (2026-09-22 against 2026-09-23) | Model-chosen windows, extraction-time freshness and Feature 01 lag | The run reference date is given to the model; actual scopes are validated | MITIGATED | Freshness per source in coverage; every answer states its last date |
| D14 | 2026-09-26 | Recursive indicators (RSI, ATR, EMA50) off from the full-history value: EMA50 +3.3%, RSI per stock up to 3.2 points | The model chooses `history_buffer` freely (20–255 observations) and TA-Lib seeds from the first row it receives; no warm-up rule exists | Diagnosis only (E2 report); proposed fixes are a prompt rule plus a planner floor of about 250 observations | OPEN (user decision pending) | Recursive indicators need about 250 prior observations (A2.9) |
| D15 | 2026-09-06 | 48 historical dates marked `NEEDS_REVIEW` during the broker backfill | An expired Stockbit credential was handled as an ordinary per-date failure | Five consecutive 401/403 stop the run as `STOPPED_INVALID_TOKEN` (exit code 3) without marking dates | FIXED | Authentication failure stops the load (A5.21) |
| D16 | 2026-09-07 | Stockbit HTTP 429 | 12 concurrent API workers | Six combined workers (three per process) | FIXED | Bounded concurrency per source |
| D17 | 2026-09-14 | Full reconciliation failed read-only | One monolithic query exhausted PostgreSQL temporary space | Four disjoint per-ticker streams (about 7 minutes) | FIXED | Partition large validations (A5.22) |
| D18 | 2026-09-23 | AI catalog lacks calculation expressions; `example_value` NULL; all columns `ai_allowed=true` and `is_sensitive=false` | Seeded by copying from the legacy catalog | Known gaps, reported | OPEN | Decide the flags per column (A4.16) |
| D19 | 2026-09-12 | First Feature 01 migration failed | A renamed CTE alias; PostgreSQL rolled the whole transaction back | Alias corrected, absence of partial objects verified, re-applied | FIXED | Migrations run in one transaction and are rehearsed on a scratch database |

### B2. Catalog and metadata (C)

| ID | Found | Symptom | Root cause | Solution | Status | Lesson for new data |
|---|---|---|---|---|---|---|
| C01 | 2026-09-24 | All five sector questions ended in LIMITATION | The analysis contract could not express a sector-filtered universe, and the model had no way to list a sector's tickers | Subject metadata (migration `20260925_001`), `get_dimension_values` for exact category values, scope by attribute; later the DataNeed flow with INNER relationships | FIXED | Every category column that can scope a question must be listable (A1.3, A1.4) |
| C02 | 2026-09-26 | With the catalog summary in the prompt, every first DataNeedSpec failed with three `INVALID_FIELD_VALUE` | The summary lacked each table's `data_domain`, `entity_type` and `asset_type`, so the model guessed them | The summary states the exact subject values and time semantics (`baa6454`) | FIXED | Subject metadata is mandatory for every table (A1.3) |
| C03 | 2026-09-25 | `DIMENSION_VALUES_STATIC_ONLY` when the model read sectors from a dated table | Distinct values are allowed only on static reference tables | The model switches to `IDX_Stock_Universe` | BY DESIGN | Keep category lists in reference tables |
| C04 | 2026-09-14 | Strict catalog sync rejected the Feature 02 shadow table | It was categorized `Feature` without active Feature Catalog definitions | Recategorized as `System` staging, and its columns registered `PARTIAL` (migration 036) | FIXED | Staging tables are `System` until cut over |
| C05 | 2026-09-27 | Test suite on dev: "does net accumulation by a broker link to a rally in mining stocks" was approved twice and never executed; the model stopped before any DataNeedSpec | The catalog documents no relationship between `Feature_02_Broker_Rolling` (broker flows) and `IDX_Stock_Universe` (sector/industry), and the prompt forbids typing a sector's member list, so broker flows cannot be scoped to a sector. A 2018–2026 all-mining broker extraction would also exceed the bundle limits | Migration `20260927_004` (IP1 Stage A) registers eleven relationships, among them `IDX_Stock_Universe` → Broker Summary, Feature 01/02/03 (`CURRENT_STATE`) and price/Feature 01 → broker tables (`EXACT_DATE`); with Research Plan feasibility the plan is sized before approval. Rerun on dev (suite4, 2026-09-27): plan after a FEASIBLE check (2024-09 to 2026-08, 73 Coal and Metals & Minerals stocks), approval executed, answer with statistics (no evidence of a link: Holm p = 1.00 for the 5-, 10- and 20-day windows) and a methodology note | FIXED | A sector scope needs a documented relationship from every table it must filter |

### B3. Data access: Governor, DataNeed, bundles (G)

| ID | Found | Symptom | Root cause | Solution | Status | Lesson for new data |
|---|---|---|---|---|---|---|
| G01 | 2026-09-23 | `NEEDS_NARROWING` / `DATE_RANGE_TOO_LARGE` | Unfiltered requests are capped at 400 days | Split the range or filter the entities | BY DESIGN | Size new sources against the caps (A5.23) |
| G02 | 2026-09-26 | A spec written reference-first delivered prices for every ticker | An INNER relationship restricted only one side | Both requests restricted (`4aa3272`) | FIXED | Test every relationship in both orientations |
| G03 | 2026-09-26 | Chained INNER restrictions deliver a superset | Restriction is one level deep | Accepted: more data, never less | ACCEPTED | Keep join chains short, or pre-join in a Feature table |
| G04 | 2026-09-24 | The model could not list entities of a group | Previews are 20 rows and `lookup_fact` takes at most 5 entities | Dimension values plus DataNeed bundles | FIXED | Data reaches Python only through governed bundles |
| G05 | 2026-09-23 | Feature 02 × Feature 03 join refused `PREAGGREGATION_REQUIRED` | The grains differ | Pre-aggregate first | BY DESIGN | Register `requires_preaggregation` (A4.17) |
| G06 | 2026-09-26 | `complete_analysis` failed with `TOOL_RESULT_TOO_LARGE`; the 2025 return of all stocks became LIMITATION | An 11-column period-return frame for 835 tickers made a 57 KB preview, over the 40,000-byte tool-result cap, and the whole completion was replaced | Released contents are fitted to the remaining byte budget (`37ef2d4`) | FIXED | Wide outputs over the whole universe must fit the result cap |
| G07 | 2026-09-24 | `INSUFFICIENT_WARMUP_HISTORY` repeated a range already requested | The remedy text was computed from the calendar, not the entities | Each entity's own `suggested_from` and an `EXCLUDE_TICKERS` option (`9085ee7`) | FIXED | Remedies must be computed from the data |
| G08 | 2026-09-26 | Bundles may omit an illiquid entity's last value before a period | Buffers are in market observations, not per entity | See D12 | OPEN | See D12 |
| G09 | 2026-09-27 | First live run of Research Plan feasibility (suite3): every `check_data_feasibility` call failed with "The SQL Governor returned an invalid response" until `REPAIR_BUDGET_EXHAUSTED`; both research questions ended as LIMITATION without a plan | market-ai-orc's `GovernorClient.extract` accepts only the extraction statuses; the Governor's estimate-only answer `WITHIN_LIMITS` was not in that list. The unit tests used a fake Governor client, so the HTTP client's status check was never exercised | `WITHIN_LIMITS` is accepted only for an `estimate_only` call (and then never with a dataset); a real extraction still refuses it. Test through the real client with a mock transport (`test_the_governor_client_accepts_an_estimate_only_answer_only_for_an_estimate`) | FIXED | A new status of a service must be tested through the real client of its caller, not a fake |

### B4. Python sandbox (S)

| ID | Found | Symptom | Root cause | Solution | Status | Lesson for new data |
|---|---|---|---|---|---|---|
| S01 | 2026-09-26 | 15 of 106 `run_python` executions failed with `SCRIPT_ERROR` (mostly `TypeError`, `KeyError`) | Helper frames hold `datetime.date` objects in the time column; the model applied string or pandas-timestamp idioms | The open-session response states `data_types` and each dataset's `time_column`; the error message is logged (`86d23ad`) | FIXED | Document the value types the helpers return (A2.5) |
| S02 | 2026-09-24 | "tiap saham" read as all stocks; "1 Juli sampai 31 Agustus 2026" read as August only | Intent parser rules | Day-level ranges, outcome horizons and "each named ticker" handled (`1614b9c`) | FIXED | Test the parser with Indonesian and English date forms |
| S03 | 2026-09-25 | Python exceptions and `NO_OUTPUT` before a successful attempt | Ordinary model coding mistakes | Repaired within the repair budget; the final output is still validated | BY DESIGN | — |
| S04 | 2026-09-23 | Network namespaces unavailable on Railway | Unprivileged containers | Per-process seccomp socket denial, non-root user, `RLIMIT_AS` | BY DESIGN | — |
| S05 | 2026-09-27 | 20-question stress test on dev: b15–b18 and r20 ended LIMITATION with `SESSION_CAPACITY_EXCEEDED` on every `open_analysis_session` | An analysis session whose executions failed (t11, b14) is never closed: market-ai-orc never calls the sandbox's `POST /v1/sessions/{id}/close`, so the session holds one of the two slots (`PY_SANDBOX_MAX_SESSIONS` default 2) until its idle timeout (900 s). The faster questions of this run (about one per minute) met two held slots. A capacity refusal was also not counted by the repair budget, so the r19 approval alternated `prepare_data_bundle` and `open_analysis_session` (33 opens) until `MAX_ITERATIONS` | market-ai-orc closes every session a run opened that did not complete with `COMPLETED` when the run ends, however it ends (best effort, log `analysis_sessions_closed`). Closing on an INCOMPLETE `complete_analysis` was proposed but dropped: its next action is often `RUN_PYTHON` in the same session. A capacity refusal reaches the model with next action `REPORT_LIMITATION` (not `RETRY_LATER`), and `open_analysis_session` rejections count toward `AI_MAX_REPAIR_ATTEMPTS` (approved 2026-09-27, market-ai-orc `app/orchestrator.py`, `app/tools/session.py`) | FIXED | Load tests must count sandbox slots, not only model calls; a sequential test can still exhaust them. Every retryable refusal needs a bound in the run |
| S06 | 2026-09-27 | Found while building conversation reuse (tests): `complete_analysis` of a session that read its data in full but had no output yet stays INCOMPLETE even after the output is emitted | `complete` replayed any earlier completion with `coverage_status` PASS, but coverage PASS does not mean the analysis completed: `sandbox_execution` can still be `FAILED` (no output). The first INCOMPLETE result was returned for every later call | Only a COMPLETED completion replays; an INCOMPLETE one is evaluated again (market-python-sandbox `app/dataneed_service.py`, regression test in `tests/test_dataneed_completion.py`) | FIXED | A replay key must be the final outcome, not one of its inputs |
| S07 | 2026-09-27 | Conversation reuse PoC on dev (D1, volatility of four banks in the reattached session): the first `complete_analysis` of epoch 3 failed coverage, and the model had to read the data again | Inherited coverage came only from the last passed epoch. Epoch 2 had only reused variables (it read nothing itself), so epoch 3 inherited nothing, although epoch 1 had read everything into the same namespace | Coverage is inherited from every earlier passed epoch of the session (same bundle, same namespace); the final status lists `ancestor_completion_ids` (market-python-sandbox `app/dataneed_service.py`, regression test `test_coverage_is_inherited_from_every_earlier_passed_epoch`) | FIXED | Lineage that lives in one namespace is cumulative; do not model it as a chain of single parents |
| S08 | 2026-09-28 | suite6 on dev (two test workers): k01 ended LIMITATION with `SESSION_CAPACITY_EXCEEDED` (HTTP 429 on `POST /v1/sessions`) | The concurrent p02 run held both slots (`PY_SANDBOX_MAX_SESSIONS` 2): it opened a second analysis session (08:34:38) before completing its first (completed 08:34:50); S05 closes a run's sessions only when the run ends | k01 run alone afterwards completed as in suite5 (19 identical days). Fix (user choice, 2026-09-28): one open session per run. Before another `open_analysis_session`, market-ai-orc closes an earlier uncompleted session of the run that has no successful execution (log `analysis_sessions_superseded`), and refuses the open with `ANALYSIS_SESSION_ALREADY_OPEN` while an earlier session has successful executions and no `complete_analysis`, so no work is discarded. `PY_SANDBOX_MAX_SESSIONS` is unchanged | FIXED | Size concurrency by sandbox slots per run, not per request; a run may hold more than one session |

### B5. Orchestrator, model and provider (M)

| ID | Found | Symptom | Root cause | Solution | Status |
|---|---|---|---|---|---|
| M01 | 2026-09-23 | HTTP 404 from OpenRouter | No DeepSeek V4.1 Flash endpoint supports `parallel_tool_calls`, and `require_parameters` drops endpoints that lack it | The parameter is omitted; sequential execution is enforced in code | FIXED |
| M02 | 2026-09-23 | No tool was ever called | A strict `text.format` in a tool turn constrains the whole generation | The output format is withheld on tool turns | FIXED |
| M03 | 2026-09-25 | The first `create_analysis_spec` call always failed with `INVALID_ARGUMENTS` | `const` was dropped from the provider schema | `const` becomes `enum: [value]` (F1) | FIXED |
| M04 | 2026-09-25 | Truncated tool arguments were executed | OpenRouter closes a tool call cut off at `max_output_tokens` and still reports it completed | Truncation guard (`MODEL_OUTPUT_TRUNCATED`); `AI_MAX_OUTPUT_TOKENS` default 8000 (F2) | FIXED |
| M05 | 2026-09-25 | Missing nullable fields rejected; `MEAN` against `AVG`; rejections without a code | The provider does not enforce the strict schema, the vocabulary was inconsistent, and the older rules had no codes | Fill nullable fields with null, one vocabulary (`AVG`), machine codes for every rejection (F4–F7, `ab38c50`) | FIXED |
| M06 | 2026-09-24 | The structured final call lost the prompt cache and moved provider | The strict-schema turn changes the request prefix, and `require_parameters` needs an endpoint with structured outputs | The first re-ask is sent like a tool turn (`9085ee7`) | FIXED |
| M07 | 2026-09-26 | About 15% of model time and 19.5% of cost regenerated a finished answer as JSON | Tool turns carry no output schema, and the prompt did not state the JSON contract | `AI_FINAL_CONTRACT_IN_PROMPT` (`86d23ad`). Local A/B: re-asks 7 → 0. On in `dev` since 2026-09-27 (`018b6d6d`) | FIXED |
| M08 | 2026-09-26 | Research Plan turns fell through to the strict-schema turn | The plan's field form was not in the prompt, so plan JSON failed validation twice | The same flag adds the exact `research_plan` form generated from the model. On in `dev` since 2026-09-27 | FIXED |
| M09 | 2026-09-26 | Catalog discovery took 73 calls and 28% of cost | Every run rediscovered the catalog in fragmented calls (capabilities, previews, one table or section per call) | `AI_CATALOG_SUMMARY_IN_PROMPT` (`86d23ad`, `baa6454`) cut discovery calls 23 → 11 locally, but it puts tables in the system prompt and grows with the catalog; **not used** (user decision 2026-09-27). Replacement implemented behind flags (`df76c77`, off in dev): complete targeted catalog responses and discovery filters/paging (`AI_ENABLE_CATALOG_DISCOVERY_V2`), and a discovery protocol with per-run reuse and a metadata guard (`AI_ENABLE_CATALOG_PROTOCOL`; implementation plan of 2026-09-27, phases C1–C3). Local A/B (2026-09-27): no reduction of discovery calls with this model (24 against 22–25 per six questions). Switched on in dev on 2026-09-27 at the user's decision. 20-question stress test on the real catalog: on the 13 comparable questions 55 discovery tool calls before and after, 175 against 179 model calls, the guard refused two data needs (each fixed with one more details call), no cache hit. No measured saving | OPEN |
| M10 | 2026-09-26 | Run time dominated by one slow upstream provider (about 49 output tokens/s against about 197) | OpenRouter's default routing is weighted to the lowest price | `AI_PROVIDER_SORT` exists in code. **Decision 2026-09-27: not used.** The model stays `deepseek/deepseek-v4.1-flash` with OpenRouter's default routing. `AI_LOG_PROVIDER` gives visibility only | ACCEPTED |
| M11 | 2026-09-23 | A page-by-page catalog read failed with `MAX_ITERATIONS` | The iteration cap ended the run before the context budget applied | Higher limits (60/60); the context budget withdraws tools gracefully | MITIGATED |
| M12 | 2026-09-26 | Period returns used different bases between runs (Q5: 14 against 16 stocks) | No convention for named periods | `AI_ENABLE_STANDARD_PERIOD_RETURN` and `saniti.period_return` | FIXED |
| M13 | 2026-09-26 | "Which stock is best?" answered with a self-chosen definition | No clarification rule for subjective criteria | CLARIFICATION observed after the Research Plan rollout; still prompt-driven | MITIGATED |
| M14 | 2026-09-26 | Gate notices in English inside Indonesian answers | The notices are fixed English strings | None yet | OPEN |
| M15 | 2026-09-13/14 | Retired `market-ai-backend`: OpenAI quota 429, a missing `record_evidence` field raised `KeyError`, truncated JSON arguments, Markdown-wrapped finals | Provider quota and unvalidated tool arguments | Quota codes not retried, recoverable argument errors, a strict final parser; the service was retired on 2026-09-25 | FIXED (retired) |
| M16 | 2026-09-27 | (Found in review, before release.) The catalog metadata guard would refuse a RESEARCH `submit_data_need_spec` with `CATALOG_DETAILS_REQUIRED` before the Research Plan guard, sending the model to read the catalog for a spec that first needs an approved plan | Two guards on one tool call, and the new one ran first | The orchestrator skips the catalog guard when the Research Plan guard will refuse the submission, so the plan refusal comes first (`df76c77`, test `test_the_research_plan_refusal_comes_before_the_catalog_guard`) | FIXED |
| M17 | 2026-09-27 | (Found in the local A/B, before release.) With the catalog protocol on, `discover_catalog` was still called two or three times per run: the first call returned no table | `query` was matched as one substring, so a phrase such as "stock daily price" matched nothing; `formula_query` behaved the same. The model also sent `data_domain: "null"` as text | Keyword matching: any keyword of 3+ letters or digits, generic words dropped, against table name, description and visible column names/descriptions, ranked by matched keywords; formulas the same. `"null"` text means no filter. A zero result lists `available_subjects` | FIXED |
| M18 | 2026-09-27 | Conversation reuse PoC on dev, turn 1 (YTD return of 48 banks): after one provenance rejection the model ran more code in its completed session and completed again; the answer was then forced to LIMITATION with the YTD figures of the first completion listed as having no source | With reuse on, a passed session stays WARM_IDLE, so the same request can run code again (a new epoch) and complete a second time. market-ai-orc kept the released values under one key per session (`completion:<session_id>`), so the second completion replaced the first one's values | The released values are kept per completion (`completion:<completion_id>`), and the research retention check reads every completion of the session (market-ai-orc `app/orchestrator.py`, regression test `test_every_completion_of_a_session_stays_a_source`) | FIXED | A source registry must be keyed by the evidence item, not by the container that produced it |
| M19 | 2026-09-27 | Same test (C05): the approval turn answered "no statistics yet" after reading the catalog only, and the approval was used up (plan `EXECUTED`) | The gates accept an ANSWER or LIMITATION without numbers in an `EXECUTE_APPROVED` turn that submitted no RESEARCH data need; H2 marks a plan executed whatever the outcome | In an `EXECUTE_APPROVED` turn a final response without any RESEARCH `submit_data_need_spec` call is rejected once (`PLAN_NOT_EXECUTED`); if still none, the answer carries a limitation, `execution.research_plan.research_submitted=false`, the same continuation is returned and `conversation_plans.advance` keeps the plan `PENDING`. A submission, whatever its outcome, still marks it `EXECUTED` (`app/orchestrator.py`, `app/conversation_plans.py`; tests `tests/test_plan_feasibility.py`) | FIXED | An approval should be consumed by an attempt, not by a turn |
| M20 | 2026-09-27 | Same test (C05): a Research Plan was presented and approved although its data could not be joined as planned (no relationship from broker flows to the sector universe) and was likely too large for one run | The plan turn only had to check that the data exists ("You may read the catalog"); the plan is conceptual (no tables), and the only join and size checks (DataNeedValidator, SQL Governor) ran after approval, inside `submit_data_need_spec` / `prepare_data_bundle` | `AI_ENABLE_PLAN_FEASIBILITY`: tool `check_data_feasibility` validates the plan's DataNeedSpec into a sandbox draft (`POST /v1/data-needs/check`) and has the Governor estimate every envelope (`estimate_only`, no rows read); a plan is issued only after a FEASIBLE check (one reminder, then a LIMITATION naming the failed check); the draft id is signed into the plan token and the approved turn starts from the draft's spec | FIXED | Check joins and size before asking the user to approve; a plan must be executable as approved |

### B6. Answer gates (P)

| ID | Found | Symptom | Root cause | Solution | Status |
|---|---|---|---|---|---|
| P01 | 2026-09-26 | A correct foreign net-sell answer (`−Rp 34.756.780.567`) forced to LIMITATION | The number parser dropped a sign placed before a currency symbol and read the value as positive | The sign is kept before `Rp`/`IDR`/`USD`, and `Rp1.000` reads like `Rp 1.000` (`86d23ad`) | FIXED |
| P02 | 2026-09-26 | A correct YTD answer forced to LIMITATION: "4, 6, 7, 8, 10, 11 have no source" | Row numbers in a Markdown table's `#` column are parsed as figures; list markers are skipped only at line start | A table's first column is treated as list markers when its header is a row-number label (`#`, `No`, `Urutan`, `Rank`, `Peringkat`, empty, ...) and its cells number the rows 1..N (0..N−1 for a pasted DataFrame index); any other first column is still checked (approved 2026-09-27, market-ai-orc `app/provenance.py`) | FIXED |
| P03 | 2026-09-26 | Answers show full precision | The model believes rounding fails the gate; it does not: a displayed number matches its source after rounding to the displayed decimals (a truncated one does not) | Both number rules of the system prompt now say that display rounding is allowed: rounded, not truncated, to the decimals shown, or a decimal shown as a percentage. The sentence has no digits, because the system prompt is a number source (approved 2026-09-27, market-ai-orc `app/orchestrator.py`) | FIXED |
| P04 | 2026-09-26 | A causal question forced to LIMITATION over one self-computed figure | The provenance gate works as designed | — | BY DESIGN |
| P05 | 2026-09-27 | A correct RSI answer (44.219; truth 44.2016 with the full history) forced to LIMITATION: "5, 10, 30 have no source" | The answer quoted the warm-up lengths of its own convergence check, an output that was not released | None yet; related to the warm-up convention (E2) | OPEN |
| P06 | 2026-09-27 | Test suite on dev (r04, RSI in Consumer Non-Cyclicals): a correct research answer forced to LIMITATION: "22, 06, 13 have no source" | The number parser splits scientific notation (`1,14e-22`, `2,58e-06`) into a mantissa and an exponent read as separate numbers | `NUMBER_RE` reads an exponent (`e`/`E`, `× 10^n`, `× 10⁻ⁿ`) with its mantissa as one number; the rounding step scales with the exponent (`app/provenance.py`; test `test_scientific_notation_is_one_number`) | FIXED | Check p-values and other scientific notation in answers |
| P07 | 2026-09-27 | Found while fixing P06: any tiny number (e.g. a wrong p-value `9,99e-22`) matched any other tiny source | The comparison added an absolute float guard of `1e-12`, larger than the values themselves | The guard is relative (`1e-12 × |value|`) | FIXED | Tolerances must scale with the magnitude of the value |

### B7. Railway, infrastructure and tooling (R)

| ID | Found | Symptom | Root cause | Solution | Status |
|---|---|---|---|---|---|
| R01 | 2026-09-23/24 | Local uploads marked `SKIPPED` ("No changes to watched files") | Watch paths also filter `railway up` uploads | Watch paths cleared, then GitHub sources connected per service with the right root | FIXED |
| R02 | 2026-09-09 | Notifications sent to `…railway.internal:/notify` | A referenced `PORT` variable was empty | Explicit port 8080 | FIXED |
| R03 | 2026-09-09 | Private network `connection refused` | The listener was IPv4 only; Railway private networking is IPv6 | Listen on IPv6 | FIXED |
| R04 | 2026-09-08/09 | A cron service stayed `Active` after its work; a reviewable outcome exited non-zero | The process did not terminate; `NEEDS_REVIEW` was treated as a crash | An explicit exit after cleanup; `NEEDS_REVIEW` exits 0 | FIXED |
| R05 | 2026-09-25 | `railway config plan` shows 3 changes for the deactivated legacy services | The IaC format cannot represent a disconnected service that keeps its root directory; applying would redeploy them | Drift kept by the user's decision; do not apply | ACCEPTED |
| R06 | 2026-09-13/14 | `config plan` failed; TLS `UnknownIssuer` | On the workstation: PowerShell `_` resolved the wrong CLI, and antivirus TLS interception | Set `_` to the Railway CLI; use a verified CA bundle; certificate verification stays on | FIXED |
| R07 | 2026-09-24 | PostgreSQL unreachable from the agent container | Egress is HTTPS only; the TCP proxy is blocked | Temporary one-off Railway services with reference variables only, deleted afterwards | MITIGATED |
| R08 | 2026-09-24 | The first job output never appeared; long log lines were lost | Railway's log pipeline | Jobs wait before exiting and print short or chunked lines | FIXED |
| R09 | 2026-09-25 | A temporary job crashed before reading | `/tmp` in the image was not writable for an in-container PostgreSQL | Writable socket directory | FIXED |
| R10 | 2026-09-23 | No bucket expiry | Railway buckets have no lifecycle configuration | Governor janitor, retention 168 h | FIXED |
| R11 | 2026-09-24 | A migration job's read-back failed after the commit | Wrong column name in the read-back query | A second, read-only deployment read the migration back. Lesson: rehearse the read-back queries together with the migration | FIXED (that instance) |
| R12 | 2026-09-26 | Setting variables on `dev` refused in agent auto mode | The permission classifier blocks changes to shared resources | Ask the user; never work around a denial | BY DESIGN |
| R13 | 2026-09-27 | The IP1 Stage D read-only inspection job (`relcat-job`, deployment `9f44200f`) stopped with `UndefinedColumn: column "table_name" does not exist` | `Database_Table_Status` names its columns in Title Case with spaces (`"Table Name"`), unlike the catalogs; the query was written from memory | Query corrected; the inspection now runs each read in its own read-only autocommit statement, so one failed read is reported and the others still run (deployment `4d67db35`) | FIXED |
| R14 | 2026-09-28 | The local rehearsal of migration `20260927_006` failed its own `$verify$` ("Unexpected CURRENT_STATE columns") although the set was right | `array_agg(x ORDER BY 1)` orders by the constant 1, not by the first column, so the aggregated array came back unsorted | The aggregate orders by its expression; caught before any dev dry run. The Governor test harness also learned to run migration SQL without parameters (psycopg reads `%` in `RAISE` as a placeholder) | FIXED |
| R15 | 2026-09-28 | The first valid `market-web-governor` image started normally but its Railway deployment failed the 120-second `/ready` health check | This service's Railway health probe could not reach the Uvicorn listener bound only to `::`; the deploy log showed application startup but no health request | Bind the Docker command and Railway start command to `0.0.0.0:8080`; deployment `1f8802e2-6dfa-49c5-948a-0afbafc7f8c0` reached `SUCCESS` and logged `GET /ready` 200 | FIXED |
| R16 | 2026-09-28 | Web Governor live test: `railway ssh` into `market-web-governor` failed ("No SSH keys found"); TCP port 22 to `ssh.railway.com` timed out from the agent container | The CLI's SSH path needs a registered key and a raw TCP connection on port 22; the agent container only has HTTPS egress through its proxy, and the service has no public domain by design | With the user's approval, a kept private runner service `web-governor-test-runner` (`8409cd61-66d1-48eb-8db7-97e607bbc6b3`, restart `NEVER`, one reference variable, no domain) runs the harness in `apps/web-governor-test-runner` on the private network | MITIGATED |
| R17 | 2026-09-28 | After the squash merge of PR #3 (`8a6c301`), the newest `market-web-governor` deployment `759b7d44` showed `SKIPPED` / `No changes to watched files`, read as a missed deploy; a manual deploy of the same commit (`9efabd95`) followed | Verified afterwards: each merge produced two GitHub-triggered deployments per service about 30 s apart. The first (`a5db8024`) built `8a6c301`; the second was skipped because nothing had changed since the first. The check read only the newest deployment | Nothing was wrong with Railway; the manual deploy was redundant (same commit, same result). After a merge, list every deployment of the commit before concluding it was skipped | BY DESIGN |

### B8. Web Governor (W)

Found by the live end-to-end test of `market-web-governor` on dev (2026-09-28; request IDs `live-smoke-20260928-*`,
`live-smoke-20260928-r2-*`). The lessons apply to every external-evidence source: a web result becomes data only
through a citation that can be stored and re-read.

| ID | Found | Symptom | Root cause | Solution | Status | Lesson for new data |
|---|---|---|---|---|---|---|
| W01 | 2026-09-28 | Multi-criterion WebNeed (T6): two required criteria returned an empty summary and were reported `NOT_FOUND`; `new_vs_repeat` returned only `ASSESSMENT: CONTRADICTED` / `SUMMARY:` and was reported `CONTRADICTED` | Verified on the rerun: the provider responses were `status=incomplete`, `incomplete_reason=max_output_tokens` (about 2,000 of 2,200 output tokens were reasoning under `WEB_OPENROUTER_MAX_OUTPUT_TOKENS=1800`); the governor parsed whatever text arrived as a verdict | An incomplete response, or one without both labels, is an `INCOMPLETE` provider call; the criterion is `BLOCKED` with gap `PROVIDER_OUTPUT_INCOMPLETE` and `next_action` `RETRY_PROVIDER` (PR #3, `8a6c301`; tests `test_truncated_response_is_incomplete_not_a_verdict`, `test_incomplete_criterion_is_blocked_and_asks_for_retry`). Live rerun: 4 of 5 criteria `BLOCKED`, none misreported | FIXED (reporting); the token budget itself is open under W02 | A truncated or unparsed provider answer is missing data, never a negative finding |
| W02 | 2026-09-28 | After W01, 4 of 5 criteria of the same WebNeed still had no verdict | `WEB_OPENROUTER_MAX_OUTPUT_TOKENS=1800` was below what `deepseek/deepseek-v4.1-flash` spends on reasoning across a 3–4-search tool loop | With the user's approval the budget was raised to 4000 (with `WEB_MAX_RESULTS_PER_SEARCH` 10 and `WEB_MAX_EXCERPT_CHARACTERS` 5000), deployment `23d0a4f6`. Live T6 (`live-smoke-20260928-r5-*`): 5 of 5 calls completed; output 3,318–4,033 tokens (reasoning 2,827–3,341), so one call finished within 7 tokens of the limit | FIXED (margin thin) | Size the output budget from measured reasoning tokens, not from the answer length |
| W03 | 2026-09-28 | Exact-URL fetch (T5) of `https://www.bi.go.id/id/statistik/indikator/bi-rate.aspx`: the provider summary quoted the page, but no evidence was recorded; the response still carried the uncited summary | Verified on the rerun: the `openrouter:web_fetch` tool ran (`fetch_tool_observed=true`) but OpenRouter returned 0 `url_citation` annotations, so there was nothing to store | First the uncited summary was withheld (PR #3). Then the provider fetch tool was replaced: the governor downloads the document itself (public-address check on every DNS answer and redirect, size, page and type limits), stores its text and hashes, lets the model read it without tools and keeps only quotes found verbatim in the stored text (`VERIFIED_QUOTE`; tests in `tests/test_fetch_and_slots.py`) | FIXED | An exact fetch must return the stored page excerpt and hash; a model's paraphrase is not evidence |
| W04 | 2026-09-28 | `execution.usage.web_search_requests` was 0 on every call although searches ran | OpenRouter's Responses API reports `usage.server_tool_use_details.web_search_requests`; the governor read `server_tool_use` | Both keys are read; `tool_calls_observed` counts server-tool output items (test `test_usage_reads_openrouter_server_tool_use_details`) | FIXED | Confirm provider usage fields against a live response, not the documentation alone |
| W05 | 2026-09-28 | `/v1/search` and `/v1/fetch` left no request-ID log line; a replayed web-need create logged `web_need_created` | Only the web-need routes logged structured events | `web_search_returned` / `web_fetch_returned` events with `request_id`, status, evidence count, provider-call count and warning codes; a replay logs `web_need_replayed` (PR #3) | FIXED | — |
| W06 | 2026-09-28 | A fast search restricted to one domain (T4, `allowed_domains=["bi.go.id"]`) can never be `SATISFIED`: five official citations still gave `PARTIAL`, `NEED_2_INDEPENDENT_SOURCES` | `/v1/search` always uses evidence standard `CORROBORATED` (two distinct domains), whatever `minimum_independent_sources` the caller asks for | None yet; the gap is reported, not hidden | OPEN | A single-publisher question needs a single-source standard, stated by the caller |
| W07 | 2026-09-28 | Evidence has no publication date (`published_at` null for every Exa citation) and no per-item stance (supporting or contradicting); the same URL is stored once per criterion with different excerpts | The provider's citations carry no date; the contract records stance only per criterion (`direction`, `assessment`); the evidence key includes the excerpt hash | None yet; dates must be read from the excerpt, stance from the criterion | OPEN | Store the source's own publication date and each item's stance when the provider cannot |
| W08 | 2026-09-28 | The adapter sends `max_uses: 1` and `max_tool_calls: 1`, yet the provider ran 2 to 4 web searches per request (`usage.server_tool_use_details.web_search_requests`), silently; the README promised at most one search per criterion | The OpenRouter server tool does not enforce `max_uses` for this model; the governor did not compare the reported count with it | The governor warns `PROVIDER_SEARCH_LIMIT_EXCEEDED` with the reported count, and the README states the real bound (requests, results per search and evidence stay capped by the service) (test `test_provider_search_overrun_is_reported`) | MITIGATED | A budget sent to a provider is a request; verify it from the provider's own usage report |
| W09 | 2026-09-28 | Live T6 with 10 results per search: criteria 4 and 5 got 0 evidence (`NO_USABLE_CITATION`, summaries withheld) and every stored excerpt was emptied (`RESPONSE_COMPACTED`) | The first two criteria used the whole `WEB_MAX_EVIDENCE_ITEMS=20` budget (10 each; evidence was filled first come, first served); 20 excerpts of up to 5,000 characters exceeded `WEB_MAX_OUTPUT_CHARACTERS=32000`, and compaction also shortened the stored excerpt | The evidence budget is shared across criteria in turn (`_allocate_evidence`); compaction shortens only the response copy and the store keeps the full excerpt; limits raised to 40 items and 64,000 characters (tests `test_evidence_budget_is_shared_across_criteria`, `test_full_excerpt_stays_stored_when_the_response_is_compacted`) | FIXED | Raising the result and excerpt limits requires the evidence and response limits to rise with them |
| W10 | 2026-09-28 | Found while fixing W09 (unit test): when a response was still above `max_output_characters` after every excerpt was removed, the excerpts were emptied silently: no `RESPONSE_COMPACTED` warning, and the response stayed over budget | `_fit_response` added its warning only when the response finally fitted | Compaction is always reported, and a response that stays above budget adds `RESPONSE_BUDGET_EXCEEDED` with its size | FIXED | A budget that cannot be met must be reported, not silently approximated |
| W11 | 2026-09-28 | ULTJ research on three slots: MiMo (slot 2) returned no evidence, 1–2 criteria of DeepSeek and GLM and every governor-fetch model read failed with `PROVIDER_REJECTED` (`OpenRouter returned HTTP 402`) | The OpenRouter account ran out of credit (total credits USD 10.00, total usage USD 10.03; the key's own limit still had USD 2.61). The key is shared with market-ai-orc through a Railway reference, so AI-Orc calls fail the same way until credit is added | None in code yet: the governor reports it as `PROVIDER_REJECTED`/`BLOCKED` with `RETRY_PROVIDER`, honestly but without naming the cause. Proposed: map HTTP 402 to `PROVIDER_CREDIT_EXHAUSTED`. Needs a credit top-up by the account owner | OPEN | A shared provider key needs a credit alert; one service's tests can stop another service |

---

## Part C — Errors to expect from cross-asset and macro data

These have not happened yet. They follow from the errors above and from how these data behave.

| Risk | Where it will show | Standard (Part A) | Check before go-live |
|---|---|---|---|
| Look-ahead in macro series | A backtest reads CPI or GDP on the reference date instead of the release date | A2.7: `release_date` plus vintage, `AS_OF` joins on availability | For a sample of dates, the joined value must be the one published by then |
| Revisions | Historical answers change after a revision | Vintage column, or a "latest revision" policy stated in the catalog | Compare two vintages for one period |
| Calendar mismatch | IDX dates against FX/US dates: joins drop or duplicate rows | A2.6, A4.17: `AS_OF` backward, declared calendar per table | Row counts before and after the join |
| Time zones | A US close recorded on the next Jakarta date | A2.5: `timestamptz` or an explicit exchange date in `time_semantics` | Check one known holiday and one DST change |
| Mixed frequency | Monthly macro against daily prices; the model resamples wrongly | A1.3 `supported_frequencies`, A4.18 resample rules | A resample of a known month equals the source |
| Units and scale | Yields in % against bps; USD against IDR; "miliar" | A3.11–A3.12 | Units filled for every numeric column |
| Currency | Returns compared across currencies without conversion | A currency column plus an FX table with a registered relationship | One converted value equals a manual conversion |
| Identifiers | `USDIDR` against `IDR=X`, bond ISIN against local code | A1.2 mapping table | Every code resolves through the mapping |
| Sparse series | Weekly or irregular releases treated as missing days | A3.15 sparse declaration | Coverage reports expected against actual observations |
| Corporate actions and continuity | Splits, dividends, contract rolls for futures | A3.14 adjustment basis | Returns across a known split date |
| Survivorship | Delisted instruments missing from history | Keep delisted entities with an end date | Count entities per year |
| Indicator warm-up | Rolling and recursive statistics on short series | A2.9, D14 | Compare with a full-history calculation |

---

## Part D — Adding an entry

Record every new error in the same task that finds it (see `AGENTS.md`). Use the next free ID in its layer (`D`, `C`, `G`, `S`, `M`, `P`, `R`, `W`), and fill these columns:

- **Found**: the date.
- **Symptom**: what was observed, with the exact code or message.
- **Root cause**: the verified cause, not a guess. Write "suspected" when it is not verified.
- **Solution**: the commit, migration or setting, and how it was verified.
- **Status**: one of the values listed at the top.
- **Lesson for new data**: when it applies, also add or adjust the rule in Part A.

Update the status in place when an `OPEN` item is fixed. Never delete an entry.
