# market-python-sandbox

Isolated Python execution for governed datasets, with an **Execution Validation Gate**.
`market-ai-orc` submits model-generated analysis code here. This service runs the code over the
immutable Parquet snapshots that `market-sql-governor` extracted (`DATASET_READY`), returns
structured outputs (TABLE, METRICS, CHART, ARTIFACT), and then checks, independently of the
code, whether those outputs match the analysis the user asked for.

```text
user request ─► market-ai-orc ─► POST /v1/specs     Analysis Spec V2 ─► catalog contract (Governor) + intent check
                                                     ─► immutable spec_id with scope_sha256 and a data plan
                              ─► prepare_analysis_data  backend compiler ─► SQL Governor datasets with lineage
                              ─► POST /v1/analyses   spec_id + prepared input bundle + code
                                     │
         market-python-sandbox harness (root) ─► Governor /v1/datasets/{id}/access ─► verified local Parquet
                                     │
         workspace ─► preflight validator ─► analysis process ─► outputs ─► postflight validator
                                     │
         execution_status  +  validation_status (PASS / INCOMPLETE / FAILED / UNVERIFIED)  +  validation_level
```

The service holds **no PostgreSQL credential and no bucket credential**. It holds two keys:
- `PY_SANDBOX_API_KEY`: accepts requests from market-ai-orc.
- `SQL_GOVERNOR_DATASET_ACCESS_KEY`: can read dataset manifests and obtain short-lived read
  URLs. It cannot submit queries.

Analysis and validator processes hold no keys at all.

## Analysis Spec V2 (two paths: ANALYSIS and RESEARCH)

`POST /v1/specs` accepts two contract versions (`app/spec_v2.py SpecRequestAny`). A spec with
`spec_version: "2.0"` is V2; a spec without it is V1 and is never reinterpreted.
market-ai-orc sends V2 only.

- **One base contract.**
  - `analysis_type` is `ANALYSIS` (research must be null) or `RESEARCH` (research block
    required).
  - `ANALYSIS` validates with profile **Y**. `RESEARCH` validates with profile **X**: the Y checks
    plus the Research Governor and evidence assessment.
  - Only RESEARCH specs reach the Research Governor, so counts, rankings and correlations never
    consume a research experiment.
- **Catalog-bound, no dictionaries.**
  - The service fetches the catalog contract of every named table from the Governor
    (`POST /v1/catalog/contract`) and rejects, with a code per problem, any of these:
    - an unknown table or column (`UNKNOWN_TABLE`, `UNKNOWN_COLUMN`);
    - a subject that differs from the tables' `data_domain` / `entity_type` / `asset_type`
      (`SUBJECT_TABLE_MISMATCH`);
    - an entity or time column other than the catalog's (`KEY_COLUMN_MISMATCH`);
    - an unknown, disallowed, pre-aggregation or non-input relationship;
    - an unsupported frequency (`FREQUENCY_NOT_SUPPORTED`);
    - a non-filterable predicate column (`FILTER_NOT_ALLOWED`) or a mistyped predicate value;
    - a non-groupable grouping key (`GROUP_BY_NOT_ALLOWED`).
  - The per-table catalog hashes are stored with the approved contract.
- **Scope.**
  - The selection types are `ALL_ELIGIBLE`, `ENTITY_LIST`, and `ATTRIBUTE_FILTER`. The last one
    takes 1-8 predicates, all of which must hold, each on a filterable catalog column with typed
    values and provenance.
  - A predicate on another input's table reaches an input through exactly one declared catalog
    relationship; otherwise the spec is rejected with `SCOPE_NOT_APPLICABLE_TO_INPUT`.
  - `CATALOG_RESOLVED` predicates must quote the user's words (`user_text`), and those words must
    appear in the request. They are disclosed as unverified interpretations.
  - The code has no topic vocabulary.
- **Time.**
  - `time_scope` is null exactly when every input is static reference data (mode `STATIC`, no
    period, no warm-up).
  - A dated input without a time scope is `TIME_SCOPE_REQUIRED`.
  - A static-only spec with a time scope is `TIME_SCOPE_NOT_APPLICABLE`.
- **Generic operations.**
  - `PERIOD_RETURN` is the change over the whole period, with a base of `PREVIOUS_OBSERVATION` or
    `FIRST_IN_PERIOD`.
  - `PERIOD_STAT` is a statistic (`MEAN`/`MEDIAN`/`STD`/`MIN`/`MAX`/`SUM`/`COUNT`) of one entity's
    observations inside the period, for example the volatility of daily returns (`STD` of a
    1-observation `RETURN`; `ddof` 1 by default; never annualized). It does not use warm-up rows.
  - `GROUP_AGGREGATE` computes `COUNT`/`COUNT_DISTINCT`/`SUM`/`AVG`/`MEDIAN`/`MIN`/`MAX` of a column
    or of a per-entity calculation. It groups either by 1-3 catalog grouping keys of any input
    (mapped by entity), or by up to 10 labelled `segments`. Its parameters are `per_date`,
    `missing_group_policy`, `unknown_group_values`, and `min_observations`.
    - A segment is a set of up to four predicates, all of which must hold. Each predicate is on a
      filterable catalog column, with values typed like scope predicates.
    - An entity belongs to every segment whose predicates all hold. Entities in no segment are not
      aggregated. The output's key column is `segment`.
    - A segment that no in-scope entity satisfies stops the analysis in preflight with
      `SEGMENT_EMPTY` (INCOMPLETE).
  - With `per_date`, a `GROUP_AGGREGATE` is one aligned series per group.
  - `GROUP_CORRELATION` correlates those series for every pair of non-null groups. The series are
    aligned on common dates (`DEFAULT_SERIES_ALIGNMENT`: no forward fill, lag 0), with `method` and
    `min_overlap` as for `CORRELATION`.
  - The `GROUP`, `GROUP_DATE` and `GROUP_PAIR` output grains take generic `key_columns`
    (`<key>_a` / `<key>_b` for pairs).
  - Averaging a return across entities over a multi-date period is materially ambiguous unless
    the request says which return is meant:
    - each entity's return over the whole period (`PERIOD_RETURN`); or
    - each entity's daily returns inside the period (`PERIOD_STAT MEAN` of a `RETURN`).

    The intent review returns `NEEDS_CLARIFICATION` when the request does not say. A stated basis
    that differs from the spec is `RETURN_BASIS_MISMATCH`. A reply to the clarification settles
    it.
  - A `ranking` is a top-N (`direction`, `limit`, `tie_policy`) over the complete candidate
    population.
- **Scope proof** (`app/logical.py verify_scope`). The approved contract holds `scope_sha256`
  and a data plan per logical input: its exact filters, joins, and warm-up date range. Before any
  analysis runs, every bound dataset must pass these checks through the Governor's internal
  validator manifest. Each is refused with its own code:
  - the lineage names this spec, its sha256, its scope hash and this input
    (`SCOPE_LINEAGE_MISSING` / `SCOPE_LINEAGE_MISMATCH`);
  - its executed scope has exactly the approved filters and joins, and nothing else
    (`EXECUTED_SCOPE_MISMATCH`);
  - it was extracted under the approved catalog version (`CATALOG_VERSION_MISMATCH`);
  - its partitions cover the approved date range without gaps or overlaps (`PARTITION_MISSING` /
    `PARTITION_GAP` / `DATE_RANGE_NOT_COVERED` → INCOMPLETE, `PARTITION_OVERLAP` → FAILED).

  The PASS evidence (`scope.lineage.<input>`) is part of the validation evidence.
- **Validator** (profile Y):
  - It recomputes every group from entity rows, taking membership from the catalog attribute
    (grouping column or segment predicates). An omitted or extra group is
    `GROUP_COVERAGE_MISMATCH`; a contaminated value is `CALCULATION_MISMATCH`.
  - It recomputes the aligned group series of a `GROUP_CORRELATION` from entity rows, then the
    correlation of every pair. A result is `CALCULATION_VERIFIED` only when both the series and
    the correlations match.
  - A period statistic that differs from the reference by a constant factor is diagnosed
    (`SCALE_DIFFERS`, for example `ANNUALIZED_SQRT_252`).
  - It recomputes `PERIOD_RETURN` for every candidate and checks the top-N against the whole
    population (`RANKING_MISMATCH`, even when the output has exactly N rows).
  - It reports the attribute scope's population (`scope.population`; `SCOPE_EMPTY` when no member
    matches).
- Source semantics come from the Governor's `source_contracts` (catalog). No per-table dictionary
  remains in this service.

## Execution Validation Gate

A successful Python run is not treated as proof that the request was answered. Every analysis
goes through these steps, all in backend code:

1. **Structured Analysis Spec** (`app/spec.py`). The model proposes a machine-readable contract:
   universe, analysis period, frequency, logical inputs, calculations with method-specific
   parameters, the outputs the code will emit, and exclusion rules. Every material requirement
   carries a **provenance**:
   - `USER_EXPLICIT`: stated by the user;
   - `USER_CLARIFIED`: stated in a reply to a clarification question;
   - `APPROVED_DEFAULT`: one of the approved defaults below, named by `default_id`;
   - `AI_INFERRED`: chosen by the model, and reported as an unverified requirement.

   Method parameters the model omits are filled with their approved default and marked as such.
2. **Independent intent check** (`app/intent.py`). market-ai-orc sends the user's own messages
   from the run, the run's reference time, and the time zone; the model cannot supply these. A
   deterministic English/Indonesian extractor builds the expected-requirements record: periods,
   trading-day counts, "latest", explicit dates and months, tickers, "all stocks", frequency,
   method keywords, and method-bound windows and thresholds. It then compares that record with
   the spec.
   - **Dates:** day-level dates are read as one period. This covers "1 Juli sampai 31 Agustus
     2026", "July 1 to August 31, 2026", "1-15 Juli 2026", "sejak 3 Maret 2026", and a single
     "5 Agustus 2026"; the year may be stated only once.
   - **Outcome horizons are not the analysis period:** "dalam 5 hari perdagangan berikutnya",
     "5 days ahead", and a move "dalam sehari" are skipped.
   - **Distributive words:** "tiap/setiap/every/each saham" means each named ticker when tickers are
     named in the same message, and all stocks otherwise. There are four outcomes:
   - **`APPROVED`:** the spec is stored immutably and returned as `spec_id` plus `spec_sha256`.
   - **`APPROVED_WITH_UNVERIFIED`:** stored as well. The requirements the extractor could not
     confirm are listed as `UNVERIFIED_REQUIREMENT` and must be disclosed.
   - **`ANALYSIS_SPEC_MISMATCH`:** a contradiction, such as three months requested but two
     proposed, a different window, or a subset of the requested universe. Nothing is stored.
   - **`NEEDS_CLARIFICATION`:** material ambiguity, such as "recently", "last month", or no
     period for a time-series result.

   The check never accepts the model's own confirmation as evidence, and anything it does not
   recognise is never assumed to match.
3. **Resolved period and required input.** Relative periods are resolved against the reference
   date. `TRAILING` periods get dates immediately; `TRADING_DAYS` and `LATEST` are resolved from
   the input calendar. The service computes each method's warm-up (minimum and recommended) and
   look-ahead, and returns the date range to request from the Governor. Warm-up history is
   never part of the analysis period. The spec response also carries an `output_contract`: for
   each declared output, the key columns (entity, date, or pair columns) and the value columns
   the validator will read.
4. **Preflight** (validator process, before the code runs). It checks that the bound datasets
   cover the contract:
   - the source table, required columns, and column types;
   - the requested and actual date range against the analysis period;
   - whether the requested universe was extracted;
   - warm-up history per entity;
   - duplicate and grain problems.

   Shortfalls that more data would fix stop the job before execution with
   `INPUT_VALIDATION_FAILED` and validation `INCOMPLETE`. These include
   `INSUFFICIENT_WARMUP_HISTORY`, the period or universe not
   extracted, and `PERIOD_NOT_COVERED`. Unusable inputs (`DUPLICATE_CONFLICT`,
   `GRAIN_AMBIGUOUS`, `INCOMPATIBLE_LOGICAL_DATASET`) are `FAILED`.
   - For `INSUFFICIENT_WARMUP_HISTORY` the refusal names the entities and a `suggested_from`
     date. The date is the earlier of the spec's recommended range and an estimate from each
     short entity's own trading density (a thinly traded ticker needs more calendar days per
     observation), plus 25%. The refusal also offers excluding those tickers with an
     `EXCLUDE_TICKERS` rule. The gate stays strict: undefined early values are never passed on
     silently.
5. **Execution** in the isolated analysis process (below).
6. **Postflight** (validator process, after the analysis process has exited). The validator
   reads only harness-written files: the manifest, the spec, the read-only inputs, and harness
   copies of the outputs the spec declares. It never reads the analysis's private directories
   and never accepts anything the code reported about itself. For every declared output it:
   - checks the declared grain and key columns (duplicate keys → `OUTPUT_GRAIN_VIOLATION`);
   - measures the actual scope: entities, date range, rows, and rows outside the analysis
     period;
   - builds the expected keys from the inputs, the universe, and documented exclusion rules;
   - classifies every missing expected observation:

     | Classification | Meaning | Effect |
     |---|---|---|
     | `SOURCE_UNAVAILABLE` | The source has no row (ticker missing, no data in the period) | reported; `INCOMPLETE` for a named ticker or a period the source does not cover |
     | `NOT_EXTRACTED` | The dataset request did not cover it (may be SQL Governor limits) | blocked at preflight |
     | `INSUFFICIENT_WARMUP_HISTORY` | Too little history before the period (source-limited, e.g. a recent listing) | reported with affected observations; `INCOMPLETE` for a named ticker |
     | `LOST_IN_TRANSFORMATION` | Present in the input with a defined value, absent from the output | `ANALYSIS_SCOPE_MISMATCH` or `UNIVERSE_MISMATCH` (`FAILED`) |
     | `DOCUMENTED_EXCLUSION` | Excluded by a declared exclusion rule, recomputed by the validator | reported |

   - recomputes every supported calculation with its own reference implementation
     (`runtime/reference.py`, NumPy, not TA-Lib or pandas rolling) on the full input history of
     each entity. A difference beyond `rtol 1e-6` is `CALCULATION_MISMATCH`. The validator also
     tries to explain the difference: a different parameter (for example "values match
     window = 10"), ignored warm-up, or no per-entity partitioning. For pair correlations it
     tries the other transforms and methods, returns computed only from in-period prices
     (`WARMUP_NOT_USED`), and listwise deletion across all tickers (`LISTWISE_DELETION`).
   - recomputes selection screens (such as RSI < 30): missing or extra rows are
     `SELECTION_MISMATCH`.

### Statuses

`execution_status` and `validation_status` are independent:

| execution_status | Meaning |
|---|---|
| `QUEUED`, `RUNNING` | not finished (`validation_status` is `PENDING`) |
| `COMPLETED` | the code ran and its outputs were collected |
| `FAILED` | the code or its inputs failed (validation is `INCOMPLETE`/`FAILED` for preflight problems, else `UNVERIFIED`) |
| `CANCELLED`, `EXPIRED` | cancelled / stored outputs expired (metadata kept) |

| validation_status | Meaning |
|---|---|
| `PASS` | every declared output was checked and matched the contract |
| `INCOMPLETE` | the source or the extracted data cannot cover the requested scope |
| `FAILED` | the outputs contradict the contract (scope, universe, grain, calculation, selection) |
| `UNVERIFIED` | nothing could be checked independently (no checkable output, or the validator failed) |

`validation_level` states how far verification got:
- `EXECUTION_ONLY`: nothing was verified.
- `SCOPE_VERIFIED`: the scope was checked, but at least one calculation (a CUSTOM method)
  has no independent reference.
- `CALCULATION_VERIFIED`: the scope was checked and every emitted calculation was recalculated
  independently. Arbitrary AI-generated code never reaches this level on its own.

`next_action` is a fixed function of both statuses and the codes:
- `USE_ANALYSIS_RESULT`
- `USE_RESULT_WITH_VALIDATION_LIMITATION`
- `REVISE_ANALYSIS`
- `REQUEST_MORE_DATA_OR_REPORT_INCOMPLETE`
- `REPORT_INCOMPLETE_RESULT`
- `REVISE_DATA_REQUEST`
- `REVISE_SPEC_OR_INPUTS`
- `REQUEST_DATA_AGAIN`
- `REPORT_LIMITATION`
- `GET_ANALYSIS_RESULT`
- `STOP_OR_REFORMULATE`
- `RERUN_ANALYSIS_IF_NEEDED`

market-ai-orc enforces the gate on the final answer; see its README.

### Supported methods and approved defaults

Conventions follow a fixed order: **TA-Lib** where TA-Lib defines the calculation, else the
**`AI_formula_reference`** entry named below, else an **AI-generated formula** (`CUSTOM`).
`app/spec.py` `CONVENTIONS` records the source of every method, and the spec review returns
`convention_notes` wherever Saniti deliberately differs from a formula-reference entry (for
example RSI is 0, not 50, when average gain and loss are both 0, as in TA-Lib). A `CUSTOM`
calculation that cites (`formula_refs`) an entry a tested method implements is refused: use the
method.

| Method | Parameters (default) | Convention | Independent check |
|---|---|---|---|
| `SMA` | `window`, `window_unit` (`TRADING_OBSERVATIONS`) | TA-Lib SMA | reference recalculation |
| `ROLLING_STD` | `window`, `ddof` (0) | TA-Lib STDDEV (population) | reference recalculation |
| `ROLLING_ZSCORE` | `window`, `ddof` (1), `include_current` (true for a level series, false for a return) | CALC_054 / CALC_053 | reference recalculation |
| `RETURN` | `horizon` (1), `kind` (`SIMPLE`/`LOG`), `as_percent` (false) | TA-Lib ROCP | reference recalculation |
| `FORWARD_RETURN` | `horizon`, `kind`, `as_percent`, `entry` (`NEXT_OPEN`: columns `[close, open]`; `SIGNAL_CLOSE`: `[close]`) — a look-ahead label | CALC_011 / CALC_010 | reference recalculation |
| `RSI` | `period` (14), `smoothing` (`WILDER`) | TA-Lib RSI | reference recalculation (matches TA-Lib to ~1e-14) |
| `ROLLING_CORRELATION` | `window`, `method` (`PEARSON`/`SPEARMAN`), `transform` | TA-Lib CORREL | reference recalculation |
| `CORRELATION` | `method`, `transform` (`SIMPLE_RETURN`), `min_overlap` (20); `ENTITY_PAIR` output | TA-Lib CORREL | reference recalculation per pair |
| `PERIOD_RETURN` | `kind`, `as_percent`, `base` (`PREVIOUS_OBSERVATION`) | Saniti | reference recalculation |
| `PERIOD_STAT` | `function` (`MEAN`/`MEDIAN`/`STD`/`MIN`/`MAX`/`SUM`/`COUNT`), `ddof` (1, `STD` only), `min_observations` (1) | Saniti | reference recalculation (expanding within the period) |
| `GROUP_AGGREGATE` | `function`, `per_date` (false), `missing_group_policy` (`SEPARATE_GROUP`), `unknown_group_values` ([]), `min_observations` (1); `group_by` or `segments` | Saniti | groups recalculated from entity rows |
| `GROUP_CORRELATION` | `method` (`PEARSON`), `min_overlap` (20), `alignment` (`COMMON_DATES`); input = a per-date `GROUP_AGGREGATE`; `GROUP_PAIR` output | Saniti | series and correlations recalculated |
| `EVENT_STUDY` | `min_events` (30), `overlap_policy` (`NON_OVERLAPPING`), `baseline` (`ALL_ELIGIBLE`); `input_calculation` = the `FORWARD_RETURN` outcome; `signal` = predicates on earlier trailing calculations; one `SUMMARY` output | CALC_176–179 | events, outcomes and baseline recalculated |
| `CUSTOM` with `expression` | the expression language below; `formula_refs`, `meaning`, `unit`, `data_policies` | AI-generated | expression re-evaluated (`VALIDATED_CUSTOM_FORMULA_RESULT` on a match) |
| `CUSTOM` without `expression` | anything, plus a required `formula` and `time_alignment` | AI-generated | scope, units and the prefix leakage re-run only; never `CALCULATION_VERIFIED` |

Calculations can chain through `input_calculation`, for example `ROLLING_STD` of a `RETURN`.

**CUSTOM expressions** (`runtime/expression.py`, parsed with an AST allowlist when the spec is
reviewed, evaluated independently by the validator):
- Names: the calculation's input columns and ids of earlier calculations.
- Operators: `+ - * / **`, comparisons, `& | ~`.
- Functions: `abs log exp sqrt sign min max where(c, a, b)`, plus the per-entity past-only
  functions `lag(x, k)`, `rolling_sum(x, n)`, `rolling_mean(x, n)`.
- An expression can never look ahead, and its warm-up is derived from it.
- A zero denominator follows `data_policies.zero_denominator` (`NULL` by default, never
  infinity).
- The preflight refuses additions, comparisons, `min`/`max` and `where` branches between
  columns of different `AI_column_catalog` units (`UNIT_MISMATCH`). The Governor manifest
  carries the units.

**EVENT_STUDY** summary: one row per `segment` (`ALL`, plus `IN_SAMPLE` and `OUT_OF_SAMPLE`
when the research block has a holdout). Columns:
- `event_count`, `mean`, `median`, `hit_rate`;
- `baseline_count`, `baseline_mean`, `baseline_median`, `delta_mean`;
- `censored_count`, `overlapping_dropped`.

An event is a period observation where every signal predicate holds. `NON_OVERLAPPING` keeps an
entity's next event only once the previous event's horizon has passed. Events without a
complete outcome are censored, not counted. A signal may not use a look-ahead calculation
(`FUTURE_LABEL_IN_SIGNAL`).
Approved defaults for interpreting requests:
- The reference date is the request date in Asia/Jakarta.
- "Last N days/weeks/months/years" is the trailing window `(reference − N units, reference]`.
- "Last N trading days" is the last N distinct trading dates in the input.
- "Latest" is each entity's newest observation at or before the reference date; stale ones
  are reported.
- A month named without a year is its most recent occurrence.
- "All IDX stocks" is every ticker in the governed source table (current listings, so
  survivorship bias applies).

Recursive indicators depend on where their input starts. Wilder RSI, for example, has a seed
error that decays by (n−1)/n per observation. The recommended warm-up is therefore
10 × period, and entities with less are reported as `PATH_DEPENDENT_WARMUP`.

### Research Governor, evidence assessment, and leakage

A spec may carry a `research` block. It holds:
- `evidence_standard`: `CALCULATION`, `SCREEN`, `DESCRIPTIVE`, `HISTORICAL_PATTERN`, `EXPLORATORY`, `PREDICTIVE` or `SCENARIO`;
- `objective`, `hypothesis {id, statement}`;
- `method_ref`: an `AI_research_catalog` method_id;
- `followup_of`, `candidates`, `holdout`.

After the intent check approves such a spec, `app/research_policy.py` decides deterministically:
- `APPROVED`: the spec_id is the reservation.
- `REPLAN_REQUIRED`: correctable.
- `REJECTED`: the run's research budget is used.

Each decision carries `reason_code`, `budget_before`, `budget_after_reservation`, and the
required validation for the standard. The ledger is the run's approved research specs (one run
= one orchestrator `request_id`). It counts:
- experiments;
- distinct hypotheses;
- follow-ups per hypothesis (a follow-up must name a completed experiment on the same hypothesis);
- pairwise candidates (n choose 2 of a TICKERS universe);
- declared candidates.

Further rules:
- `HISTORICAL_PATTERN` and `PREDICTIVE` need a hypothesis and an `EVENT_STUDY`.
- `PREDICTIVE` also needs a temporal holdout inside the period, covering at least 20% of it.
- Re-sending the same spec for the same request and user messages returns the stored spec_id
  (`replayed: true`) and reserves nothing.

After postflight the validator adds `evidence_assessment`:
- `claim_type` and `decision`: `SUPPORTED`, `PARTIALLY_SUPPORTED`, `INSUFFICIENT_EVIDENCE` or `INVALID`.
- `evidence_level`: `OBSERVATION`, `PATTERN`, `PREDICTIVE_SIGNAL`, `EXPLORATORY`, `SCENARIO` or `NONE`.
- `checks` and `reporting_constraints`.
- `statistics`: the validator's own numbers, never the analysis's.

How each claim type is assessed:
- Calculations, screens and descriptions skip the statistical checks (`NOT_APPLICABLE`).
- Pattern claims need:
  - `min_events` events and `min_baseline_observations` baseline observations;
  - coverage;
  - the 95% interval of the difference from the baseline (Welch) excluding zero;
  - a Bonferroni-adjusted interval over every test run on the hypothesis.
- Predictive claims also need an out-of-sample difference of the same sign.
- An exploration is at most `PARTIALLY_SUPPORTED`.

**Prefix leakage re-run.** For `CUSTOM` code without an expression in an `ENTITY_DATE` output
(explicit or trailing period, at least 10 trading dates, enough CPU budget), the sandbox runs the
same code again. That run uses inputs truncated at the date 60% into the period. Values at or
before that date must be identical. Otherwise the result is `TEMPORAL_LEAKAGE_DETECTED`
(validation `FAILED`, evidence `INVALID`). This generically catches `shift(-k)`, centred windows
and full-sample normalisation. It costs about one more run and counts toward the request CPU
budget.

**Corporate actions.** Analyses of returns from the price tables carry the warning
`CORPORATE_ACTIONS_NOT_ADJUSTED`. Prices are split-adjusted as fetched and not
dividend-adjusted, and stored history is not re-adjusted after a later split.

### Derived features

Every calculation output is a derived feature of the analysis. It is distinct from database
features, which are input columns that come from `Feature_*` tables and are listed in
`database_features`. Each derived feature carries a machine-readable definition:
- the method and formula;
- the source logical input, source table, and input columns;
- the parameters;
- the output grain and time alignment;
- `origin: DERIVED_IN_ANALYSIS`, `status: EXPLORATORY_UNVALIDATED`, and
  `statistical_validation: NOT_PERFORMED`;
- its SHA-256;
- `independent_check_result`: `RECALCULATED_MATCH`, `RECALCULATED_MISMATCH`, or `NOT_CHECKED`.

Definitions are stored as a harness-written JSON artifact (`derived_feature_definitions`) next
to the result tables, and in the `derived_features` table of the records database for a future
Research Governor. Nothing is written to PostgreSQL, and no `AI_calculation_catalog` entry is
created.

## Workspace and logical datasets

Each job gets its own workspace. Every path is created by the harness:

```text
/sandbox/jobs/<analysis_id>/          0755 root
├── manifest.json                     0444 root  logical datasets → approved local files (+ checksums, lineage)
├── analysis_spec.json                0444 root  the immutable approved spec, resolved period, required input
├── analysis.py                       0444 root  the model's code
├── runtime.json                      0444 root  limits, CPU set, DuckDB settings, input views
├── input/input_001.parquet …         0444 root  hard links to the checksum-verified cache
├── intermediate/                     0700 slot user  HOME, TMPDIR, DuckDB temp, intermediate Parquet
├── output/                           0700 slot user  emitted outputs
├── validation/                       0755 root
│   ├── request.json, outputs/        0444 root  harness copies of the declared outputs
│   └── result/, home/                0700 validator user
└── execution_report.json             0444 root  statuses, checksums, usage (also persisted)
```

- **Logical datasets** (`app/logical.py`). A spec names logical inputs (for example `prices`),
  and each run binds every input to one or more Governor `dataset_ids`. Files are combined only
  when all of the following hold:
  - they come from the spec input's source table;
  - their column contracts are identical: name, type, source table, source column, and
    aggregation;
  - their grain comes from the source contract, or from the group-by columns of an aggregated
    extract.

  Different grains or meanings stay separate inputs (`INCOMPATIBLE_LOGICAL_DATASET`,
  `SOURCE_TABLE_MISMATCH`). Overlapping rows follow the binding's `duplicate_policy`:
  - identical rows are removed;
  - conflicting rows are refused (`ERROR_ON_CONFLICT`, the default), or resolved by the newest
    snapshot (`PREFER_LATEST_SNAPSHOT`).

  The model cannot put a path, dataset id, or table into the manifest. The Governor's
  seven-table allowlist is unchanged.
- **Semantic contracts** of the seven approved tables record the meaning, grain,
  entity and time columns, frequency, time zone, and units.

## Runtime interface for analysis code

- **Libraries** (pinned, see `requirements-analysis.txt`): numpy, pandas, polars, pyarrow,
  duckdb, scipy, statsmodels, matplotlib (Agg), and TA-Lib. pip is removed from the image.
- **Namespace.** The `saniti` module and every public name in `saniti.__all__` (helpers, `INPUTS`,
  `SPEC`, the period constants, the exception classes) are pre-bound in the analysis namespace,
  together with `pd` (pandas) and `np` (numpy), so `saniti.load(...)`, `emit_table(...)`,
  `pd.DataFrame(...)`, and `import saniti` all work. The first real-model
  rehearsal showed that a model otherwise spends its analysis budget discovering the API.
- **Inputs:** each logical input is a DuckDB view with the same name on a locked connection.
  - `saniti.sql(query, params, max_rows)` and `saniti.load(name, columns, start, end, entities,
    max_rows)` return pandas DataFrames. They refuse to materialize more than
    `PY_SANDBOX_MAX_MATERIALIZE_ROWS` (`MATERIALIZATION_LIMIT_EXCEEDED`); filter or aggregate in
    SQL instead. Without `start`/`end`, `load` returns the whole input, including the warm-up
    history before the analysis period; the tool description never shows `start`/`end`, because
    cutting the input to the period before computing is the most common cause of
    `WARMUP_NOT_USED`.
  - `saniti.in_period(frame, date_column=None, entity_column=None)` is a boolean mask of the
    rows inside the approved period, resolved like the validator: `start ≤ date ≤ end`, and for a
    `LATEST` period each entity's newest row on or before the period end. Analysis code computes
    on the full history and then emits `frame[in_period(frame)]`.
  - `saniti.relation(name)` is lazy.
  - `INPUTS` lists each input's files and columns (for polars/pyarrow scans).
  - `SPEC`, `ANALYSIS_START`, `ANALYSIS_END`, and `REFERENCE_DATE` come from the approved
    contract.
  - `saniti.intermediate_path(name)` is the only place for intermediate Parquet.
- **DuckDB lockdown.** The runner replaces DuckDB's default connection and `duckdb.connect()`
  before any model code runs:
  - `memory_limit` and `threads` are set;
  - `temp_directory` is `intermediate/.duckdb_tmp`, with `max_temp_directory_size`;
  - `allowed_directories` is only the job's `input/` and `intermediate/`;
  - `enable_external_access=false`;
  - automatic extension install and load are off, and the extension directory is outside
    the workspace;
  - community extensions are off;
  - `lock_configuration=true`;
  - only in-memory databases are allowed.

  The self-test proves at startup, and requires DuckDB's own permission error for each
  refusal, that reading outside the workspace, changing the configuration, INSTALL, LOAD,
  ATTACH, and a new connection are all refused. A determined script could still reach DuckDB's
  raw C module, so the security boundary remains the OS isolation below, not DuckDB settings.
- **Helpers:**
  - `iter_series`, `prepare_panel`, and `panel_check` keep each entity's history separate and
    date-ordered and surface duplicates; they never fill missing values.
  - `add_warning` records a limitation.
  - `emit_table`, `emit_metrics`, `emit_chart`, and `emit_artifact` are the only official
    results.
  - Anything the code reports about itself (METRICS claims, the helper access log) is kept
    under `self_reported` and never used as evidence.

The harness re-validates everything the process wrote, as before:
- names, counts, and the declared type set;
- Parquet footers and PNG headers;
- previews and JSON validity;
- `O_NOFOLLOW`, regular files owned by the slot user.

## Execution isolation

Every analysis runs in a **fresh process** (`runtime/runner.py`). The validator is another
fresh process (`runtime/validator.py`). Both run as dedicated non-root users (analysis slots
`sandbox1..4`, UID 20001+; validator `sandboxv`, UID 20100). Both are confined by
`runtime/confine.py` before any work starts:
- rlimits: AS, CPU, FSIZE, NOFILE, NPROC, and CORE;
- a pinned CPU set;
- a seccomp-bpf filter.

The model's Python is never `exec`'d inside the FastAPI process.

| Control | Mechanism |
|---|---|
| No inherited secrets | The environment is constructed from scratch and file descriptors are closed. The harness runs as root, so `/proc/<harness>/environ` is unreadable. |
| Private files | The jobs root is 0711. The layout is above. Service storage (`/data`) and the dataset cache are 0700 root. `/tmp` and `/var/tmp` are not writable. |
| Memory | An RSS watchdog runs every 100 ms, a hard `RLIMIT_AS` ceiling applies, and DuckDB has its own `memory_limit` (default half of the job's RSS). |
| Runtime / CPU | A wall-clock watchdog runs, and `RLIMIT_CPU` is capped by the remaining request-level CPU budget. |
| Disk | Separate quotas for `intermediate/` (including DuckDB temp) and `output/`, checked every second. `RLIMIT_FSIZE` applies. |
| Syscalls | seccomp denies every socket (only an anonymous AF_UNIX `socketpair` is allowed), `execve`/`fork`/non-thread `clone`, ptrace, bpf, io_uring, mount, namespaces, keyrings, and more. |

**Network isolation, stated precisely.** Railway has no egress firewall and allows no
namespaces. The analysis and validator processes cannot create any socket, which the kernel
enforces through seccomp. This is **not a network namespace**.

**Fail closed.** At startup, a self-test job goes through the same path. It checks:
- non-root, seccomp, and no_new_privs;
- sockets, fork, and execve denied;
- unreadable parent environments and a clean environment;
- TA-Lib;
- the DuckDB lockdown;
- the validator process's uid, seccomp, and socket denial.

If any check fails, `/ready` returns 503 and every analysis is refused with
`SANDBOX_ISOLATION_UNAVAILABLE`.

The source screen (`app/policy.py`) is defense in depth only.

## Dataset access

1. For each input the harness calls `POST {SQL_GOVERNOR_URL}/v1/datasets/{id}/access`. The
   Governor refuses a missing, expired, or malformed dataset, and a file whose size does not
   match.
2. For an available dataset, it returns the bounded manifest and a **presigned SigV4 GET for
   exactly `datasets/<id>/data.parquet`** that expires in 120 s.
3. The harness enforces the input limits and streams the file. It verifies the manifest SHA-256
   (`DATASET_INTEGRITY_ERROR` on mismatch) and caches the verified copy root-only. The cache
   entry expires with the Governor snapshot.

The URL is never logged, stored, returned, or visible to any child process.

## API (private networking only, bearer `PY_SANDBOX_API_KEY`)

| Endpoint | Purpose |
|---|---|
| `GET /health`, `GET /ready` | Liveness; readiness means the isolation self-test passed |
| `POST /v1/specs` | `{request_id, reference_time, timezone, user_messages[], spec}` → spec review (see above) |
| `GET /v1/specs/{spec_id}` | The stored immutable contract (audit). It holds a hash of the user messages, never the messages. |
| `POST /v1/analyses` | `{request_id, spec_id, inputs: [{name, dataset_ids[1..8], duplicate_policy}], python_code ≤ 20000, expected_outputs}`. The spec must be approved and belong to the same `request_id` (`SPEC_NOT_FOUND` otherwise). |
| `GET /v1/analyses/{id}?wait_seconds=` | The record, including both statuses, `expected_scope`, `actual_scope`, `validation_evidence`, derived features, and lineage |
| `POST /v1/analyses/{id}/cancel` | Cancel a queued or running analysis |
| `GET /v1/results/{res_…}?offset&limit≤500` | Complete TABLE rows, paged |
| `GET /v1/artifacts/{art_…}` | PNG / Parquet / CSV / JSON bytes, including the feature definitions |
| `GET /v1/runtime` | Isolation checks, library versions, limits |
| `GET /v1/runs/{request_id}` | Audit view of one orchestrator run: experiments with governor decisions, analyses with code/dataset fingerprints and evidence decisions, budgets, and the final report |
| `POST /v1/runs/{request_id}/report` | market-ai-orc's final report of the run (answer and hash, evidence label, gate, experiments). Stored once; a retry keeps the first. |

**Request-level budgets.** All analyses of one orchestrator request share:
- `PY_SANDBOX_MAX_ANALYSES_PER_REQUEST`;
- `PY_SANDBOX_MAX_CPU_SECONDS_PER_REQUEST` (analysis plus validator CPU);
- `PY_SANDBOX_MAX_INPUT_BYTES_PER_REQUEST`;
- `PY_SANDBOX_MAX_SPECS_PER_REQUEST`.

Repeated `run_python_analysis` calls therefore cannot bypass them (`REQUEST_BUDGET_EXCEEDED`,
429). An idempotent replay of an identical submission returns the recorded analysis and does
not count again.

## Records, reproducibility, retention

Records live in SQLite on the service volume (`/data/analyses.sqlite3`, root-only; migrated in
place). Each analysis keeps:
- its spec id and hash, logical inputs, and dataset checksums;
- both statuses, the level, reason codes, and evidence;
- the expected and actual scope;
- derived features;
- the code hash (and source), runtime and library versions, seed, and limits;
- resource usage (analysis and validator);
- `reproducible_until`, the earliest snapshot expiry;
- the execution report.

| Layer | Owner | Retention |
|---|---|---|
| PostgreSQL source data | PostgreSQL | never touched by the sandbox |
| Governor snapshots (bucket) | market-sql-governor | its own 168 h policy; the sandbox never deletes them |
| Sandbox dataset cache | sandbox | deleted when the Governor snapshot expires, or by LRU over `PY_SANDBOX_DATASET_CACHE_BYTES` |
| Workspace inputs and intermediates | sandbox | deleted as soon as a job ends; a failed job's inputs are deleted immediately |
| Failed-job diagnostics (code, reports, small intermediate/output) | sandbox | `PY_SANDBOX_FAILED_WORKSPACE_TTL_HOURS` (6), only if ≤ `PY_SANDBOX_FAILED_WORKSPACE_MAX_BYTES` |
| Result tables, charts, artifacts, feature definitions | sandbox | `PY_SANDBOX_RESULT_RETENTION_HOURS` (24), then `EXPIRED` |
| Compact audit records (specs, analyses, derived features) | sandbox | `PY_SANDBOX_RECORD_RETENTION_DAYS` (30) |

The janitor runs every `PY_SANDBOX_CLEANUP_INTERVAL_SECONDS` (900) and at startup. It removes
every workspace that no running job owns, except failed-job diagnostics within their TTL, so
cleanup does not depend on redeploys. Active workspaces are never touched. After the input
snapshot expires, a record carries `INPUT_SNAPSHOT_EXPIRED`: its checksums identify the input,
but the analysis can no longer be re-run on the same data.

**Structured logs:**
- `sandbox_spec_review`: request_id, status, and counts only.
- `sandbox_analysis`: ids, checksums, both statuses, the level, reason codes, and resource
  usage.

Logs never contain keys, dataset URLs, user messages, datasets, or tables.

## Configuration

**Required:**
- `PY_SANDBOX_API_KEY` (≥ 32 characters)
- `SQL_GOVERNOR_URL`
- `SQL_GOVERNOR_DATASET_ACCESS_KEY` (≥ 32 characters, must differ from the API key)

**Limits** (backend only; no request field can raise them):

| Variable | Default |
|---|---|
| `PY_SANDBOX_MAX_LOGICAL_DATASETS` | 4 |
| `PY_SANDBOX_MAX_INPUT_FILES` | 8 |
| `PY_SANDBOX_MAX_INPUT_ROWS` | 2,000,000 |
| `PY_SANDBOX_MAX_INPUT_BYTES` | 256 MiB |
| `PY_SANDBOX_MAX_MATERIALIZE_ROWS` | 2,000,000 |
| `PY_SANDBOX_MAX_CODE_CHARS` | 20,000 |
| `PY_SANDBOX_MAX_RUNTIME_SECONDS` | 120 |
| `PY_SANDBOX_MAX_MEMORY_MB` | 2048 |
| `PY_SANDBOX_MAX_VIRTUAL_MEMORY_MB` | 4096 |
| `PY_SANDBOX_DUCKDB_MEMORY_MB` | half of the memory limit (1024) |
| `PY_SANDBOX_MAX_INTERMEDIATE_BYTES` | 1 GiB (includes DuckDB temp) |
| `PY_SANDBOX_MAX_OUTPUT_DIR_BYTES` | 256 MiB |
| `PY_SANDBOX_CPUS_PER_JOB` / `_THREADS_PER_JOB` | 2 / 2 |
| `PY_SANDBOX_CONCURRENCY` / `_MAX_QUEUED` | 1 / 8 |
| `PY_SANDBOX_VALIDATOR_UID` | 20100 |
| `PY_SANDBOX_VALIDATOR_RUNTIME_SECONDS` / `_MEMORY_MB` | 120 / the memory limit |
| `PY_SANDBOX_MAX_ANALYSES_PER_REQUEST` | 6 |
| `PY_SANDBOX_MAX_CPU_SECONDS_PER_REQUEST` | 1200 |
| `PY_SANDBOX_MAX_INPUT_BYTES_PER_REQUEST` | 1 GiB |
| `PY_SANDBOX_MAX_SPECS_PER_REQUEST` | 10 |
| `PY_SANDBOX_RESEARCH_MAX_EXPERIMENTS` | `PY_SANDBOX_MAX_ANALYSES_PER_REQUEST` |
| `PY_SANDBOX_RESEARCH_MAX_HYPOTHESES` / `_MAX_FOLLOWUPS_PER_HYPOTHESIS` | 4 / 5 |
| `PY_SANDBOX_RESEARCH_MAX_PAIRWISE_CANDIDATES` / `_MAX_CANDIDATES` | 20,000 / 50 |
| `PY_SANDBOX_RESEARCH_MIN_EVENTS` / `_MIN_BASELINE_OBSERVATIONS` / `_MIN_COVERAGE_PCT` / `_MIN_HOLDOUT_PCT` | 30 / 100 / 95 / 20 |
| `PY_SANDBOX_LEAKAGE_CHECK` | true |
| `PY_SANDBOX_MAX_TABLES` / `_TABLE_OUTPUT_ROWS` / `_TABLE_PREVIEW_ROWS` | 8 / 100,000 / 50 |
| `PY_SANDBOX_MAX_METRICS` / `_METRICS_BYTES` / `_OUTPUT_BYTES` | 8 / 8000 / 24,000 |
| `PY_SANDBOX_MAX_ARTIFACT_BYTES` / `_CHARTS` / `_ARTIFACTS` | 64 MiB / 8 / 8 |
| `PY_SANDBOX_SUBMIT_WAIT_SECONDS` / `_MAX_POLL_WAIT_SECONDS` / `_RETRY_AFTER_SECONDS` | 25 / 20 / 15 |
| `PY_SANDBOX_RESULT_RETENTION_HOURS` / `_RECORD_RETENTION_DAYS` | 24 / 30 |
| `PY_SANDBOX_FAILED_WORKSPACE_TTL_HOURS` / `_MAX_BYTES` | 6 / 64 MiB |
| `PY_SANDBOX_CLEANUP_INTERVAL_SECONDS` | 900 |

**Paths:**
- `PY_SANDBOX_DATA_DIR` (`/data`, the Railway volume)
- `PY_SANDBOX_JOBS_DIR` (`/sandbox/jobs`)
- `PY_SANDBOX_CACHE_DIR` (`/sandbox/cache`)
- `PY_SANDBOX_DATASET_CACHE_BYTES` (1 GiB)
- `PY_SANDBOX_DATASET_URL_SCHEMES` (`https`; `file` is for tests only)

## Railway service

Deployed on `dev` as `market-python-sandbox` (v1, before the validation gate). It is a local
upload with no public domain, and the Railway volume is mounted at `/data`, so it runs as a
single replica. `RAILWAY_CHANGELOG.md` has the details. Version 2 (the validation gate) changes
the API contract together with market-ai-orc, so both must be deployed together. The existing
SQLite records are migrated in place (new columns and tables only).

## Tests

```bash
pip install -r requirements-dev.txt
sudo pytest   # root is required for the isolation tests; they are skipped otherwise
```

- `tests/test_units.py`: configuration, request schema, source screen, seccomp program,
  helpers.
- `tests/test_gate_units.py` (no child processes):
  - spec normalization and defaults;
  - intent review (mismatch, clarification, unverified, Indonesian and English);
  - logical binding;
  - reference calculations against TA-Lib and pandas;
  - validator decisions for acceptance scenarios A–D, F, and H;
  - selection screens, pair correlation, cross-entity contamination, and CUSTOM levels.
- `tests/test_sandbox.py`: real child processes covering:
  - isolation;
  - TA-Lib and time-series safety;
  - outputs and limits;
  - forged outputs;
  - dataset security;
  - no credentials in the process and no secrets in logs;
  - lifecycle, idempotency, cancel, restart, and retention.
- `tests/test_gate_sandbox.py`: acceptance A–H through the real service, including:
  - (A) three months requested, two calculated;
  - (B) warm-up;
  - (C) universe;
  - (D) wrong window;
  - (E) a large four-file DuckDB workspace, with measurements;
  - (F) logical datasets;
  - (G) cleanup and retention;
  - (H) fabricated evidence;
  - DuckDB and workspace boundaries in a real process;
  - spec immutability and request scoping;
  - request budgets.
