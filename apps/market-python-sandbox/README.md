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

## DataNeed flow (in progress, off unless `PY_SANDBOX_DATANEED_ENABLED=true`)

The DataNeed architecture replaces the Analysis Spec with a data-only contract. It is built in phases next to the
current flow; while the flag is off, its routes answer 404 and the service keeps no DataNeed state.

**Phase 1 (implemented): DataNeedSpec validation.** `POST /v1/data-needs` takes
`{request_id, reference_time, timezone, spec, research_governance}`.
- `spec` is a `data_need_spec/v1` document (`app/data_need.py`). It lists logical data requests and catalog
  relationships only:
  - each request names one catalog table, its columns, a scope expression tree (ALL, PREDICATE, AND/OR with
    children, NOT with child; depth ≤ 4, ≤ 40 nodes, IN lists ≤ 500 values), named time ranges, the source and
    analysis frequencies with `resample`, history and future buffers, ordering and `sampling_allowed` (always
    false);
  - a relationship names a catalog `relationship_id`, INNER or LEFT, and the join semantics the catalog supports
    (CURRENT_STATE, EXACT_DATE, AS_OF, EFFECTIVE_DATED; migration `20260925_003`).
  - **Composite keys (IP1 Stage B).** `data_need_spec/v1` names one key pair (`left_column`, `right_column`);
    `data_need_spec/v2` names every entity key pair (`left_columns`, `right_columns`, 1–8 each, any order). Both are
    accepted (`GET /v1/runtime` reports `data_need_spec_versions`). The pairs must equal the catalog relationship's
    keys without its time column: leaving one out (for example Broker Summary ↔ Feature 02 on ticker and date only,
    which would mix brokers, investor types and boards) or adding one is `RELATIONSHIP_KEY_MISMATCH`; a v2
    relationship may repeat `left_column` / `right_column` only when they equal its single pair
    (`RELATIONSHIP_KEY_FORMAT_CONFLICT` otherwise). The approved contract keeps one canonical form: a single pair as
    `left_column` / `right_column` (so single-key contracts and their hashes do not change between v1 and v2), two or
    more as `left_columns` / `right_columns` in catalog order; restrictions follow the same rule. Approved
    relationships also carry `relationship_type` (read in the spec's orientation) and `requires_preaggregation`.
  - **Warehouse summaries (G18 phase 1, 2026-10-02).** A request may carry `aggregate`:
    `{"group_by": [columns], "measures": [{"column", "function", "as"}]}` and the SQL Governor then delivers one row
    per group instead of every raw row (`bind_aggregate` in `app/data_need.py`; the Governor re-checks the same rules
    from its own contract). Rules, derived from the catalog, fail closed: mode ANALYSIS only and no `resample`;
    `group_by` columns are `group_by_allowed` or grain keys, a dated table keeps its time column (phase 1 summarises
    across entities only, so every date stays checkable), at least one grain key is dropped; SUM needs
    `cross_entity_aggregation` = SUM (`AGGREGATION_NOT_ADDITIVE` names the dropped keys), MIN and MAX a numeric
    MEASURE, COUNT counts rows (`column` null), COUNT_DISTINCT an IDENTIFIER, DIMENSION or TIME column; `columns` are
    exactly the grouped and measured columns; ordering uses grouped columns; a relationship of the request keeps its
    key columns grouped (`AGGREGATE_DROPS_JOIN_KEY`). The approved request carries the summary's grain: `aggregate`,
    `key_columns` = `group_by`, `extract_columns` = `group_by` + measure names, `entity_column` only when kept, the
    output column types (counts `bigint`), and empty `resample_rules` / `aggregation_rules` (a summary is not
    resampled or preaggregated again). Profiling, delivery coverage (the executed `aggregate` must equal the approved
    one) and the session helpers follow that grain. A summary serves only the same summary for reuse
    (`contract_covers`), and a raw request's contract hash is unchanged. Not in phase 1: summaries over time, AVG
    (send SUM and COUNT), medians, percentiles, correlations. An approved raw ANALYSIS request whose requested columns add up across entities carries `summary_available` (`summary_options`: groupable, kept and droppable columns, the summable measures and an example aggregate), so the model knows the option before it pulls raw rows.
  - **Preaggregation (IP1 Stage C).** A relationship with `requires_preaggregation = true` (Feature 02 → Feature 03)
    is no longer refused: its INNER restriction is a semi-join that never multiplies rows, and in the session
    `saniti.join` refuses a row join until the many side came from `saniti.preaggregate`. Each approved request
    carries `aggregation_rules`, the catalog's `cross_entity_aggregation` per column (migration `20260927_005`).
  - **Time basis (IP1 Stage D).** `data_need_spec/v2` may state `time_basis`: `HISTORICAL_DESCRIPTIVE` (the
    default) or `POINT_IN_TIME` (opt-in; `GET /v1/runtime` reports `point_in_time`). The checks need the Governor
    contract of migration `20260927_006` (`value_time_basis` per column, the Table_Catalog `availability` per table,
    `history_available_from` per EFFECTIVE_DATED relationship):
    - either mode: an EFFECTIVE_DATED relationship answers only dates its history covers, so a left request that
      extracts a date before `history_available_from` (range start minus history buffer), or a history that is
      still empty, is `POINT_IN_TIME_UNAVAILABLE`; the join is never left to drop those rows silently;
    - `HISTORICAL_DESCRIPTIVE`: a dated request that reads or filters a `CURRENT_STATE` column (Feature 01 sector
      and industry, Feature 02 broker_classification, Feature 03 institutional/retail/mixed/niche net values) is
      approved with the warning `CURRENT_STATE_COLUMN`;
    - `POINT_IN_TIME`: `POINT_IN_TIME_UNAVAILABLE` for a CURRENT_STATE relationship, a CURRENT_STATE column read or
      filtered, a table whose `point_in_time_status` is `UNAVAILABLE` (the current-state reference tables), and for
      any spec when the catalog lacks that metadata (fail closed). Never replaced by current data.
    The approved contract, the bundle and the final status carry `time_basis`; each approved request carries its
    table's `availability`. A point-in-time data contract never reuses descriptive data (its hash adds
    `time_basis`; descriptive hashes are unchanged).
  - There is no formula, calculation, indicator, method, ranking or output grain.
- The DataNeedValidator checks four layers: schema, catalog binding (Governor catalog contract), cross-request
  relationships, and planning feasibility. It answers `APPROVED`, `REVISION_REQUIRED` or `CATALOG_UNAVAILABLE`.
  Every issue is `{data_request_id, code, field_path, rejected_value}`; the validator never suggests a replacement.
- Revisions: the first revision of a request group is 1 and each next one is the highest judged revision + 1. An
  identical resubmission replays its answer. A different document under a used revision, or a skipped number, is
  `REVISION_CONFLICT`. A catalog outage or a conflict does not use up a revision number. Every submission is
  recorded in `/data/dataneed.sqlite3`.
- An approved need stores the contract the later phases work from:
  - per request: extract columns (keys first), column types, the canonical scope and its hash, one extraction
    window per range (widened by the buffers, the future capped at the reference date), resample rules from the
    catalog, and the restrictions that INNER relationships impose. An INNER relationship restricts both of its
    requests, each to rows with a match in the other request's own scope, whichever side the spec puts left.
    Restrictions are one level deep, a superset of the exact join, which `saniti.join` performs in the session.
    For `AS_OF` and `EFFECTIVE_DATED`, only the observation side is restricted; the reference history keeps its
    own scope. `HISTORICAL_REFERENCE_USES_CURRENT_STATE` names the request that holds the historical observations;
  - the spec hash, the catalog hash and the reference date.
  `GET /v1/data-needs/{need_id}` returns it.
- **Feasibility drafts** (Research Plan feasibility). `POST /v1/data-needs/check` takes `{request_id, reference_time,
  timezone, spec}` and runs the same four validator layers without a revision, a `research_governance` or a Research
  Governor review. An approved spec is stored as a draft (`draft_` + 24 hex, table `data_need_drafts`, SQLite schema
  version 2, kept seven days) and answers `{status: APPROVED, draft_id, next_action: ESTIMATE_EXTRACTION}`; otherwise
  `REVISION_REQUIRED` / `CATALOG_UNAVAILABLE` with issues. `GET /v1/data-need-drafts/{draft_id}` returns the draft in
  the planner's need shape (`need_id` = the draft id), so market-ai-orc can have the Governor estimate it. A draft is
  never a need: `GET /v1/data-needs/{draft_id}` is 404 and nothing can be extracted from it. `GET /v1/runtime` reports
  `plan_feasibility: {enabled, version: 1}`.
- `mode: RESEARCH` needs a ResearchGovernanceRequest (hypothesis, candidate count, pairwise comparisons, a
  multiple-testing policy, an optional holdout range and minimum sample, `followup_of`). The Research Governor
  (`app/research_governance.py`) answers `APPROVED`, `REPLAN_REQUIRED` or `REJECTED` with a reason code, from the
  same research budgets as the Analysis Spec path. Revisions of one request group reuse its reservation.
  `mode: ANALYSIS` with a governance request is `MODE_MISMATCH`.
- The request may also declare `condition`, `outcome` and `baseline`: optional (absent or null), otherwise
  non-blank text of at most 1,000 characters (`INVALID_FIELD_VALUE` otherwise). They are recorded with the need and
  returned in `research_governance.constraints.declarations`. They are declarations only: the governor never
  checks the analysis code against them. market-ai-orc binds them to the user's approved Research Plan before it
  calls this endpoint (see its README, Research Plan confirmation); the sandbox itself does not know about plans.

**Phase 2 (implemented): governed data bundles.** market-ai-orc's Execution Planner extracts every part of an
approved need through the Governor's `/v1/extract`. It then sends `POST /v1/bundles {request_id, need_id, plan}`,
where the plan lists every part: `partition_id`, `dataset_id`, `part_key`, window, and entity partition.
`app/bundles.py` then:

1. checks that the need is approved for this request and that the plan is well formed;
2. obtains a Governor grant for every dataset and refuses before any download when the bundle would exceed
   `PY_SANDBOX_BUNDLE_MAX_ROWS` / `_MAX_BYTES` (`BUNDLE_TOO_LARGE`, next action `REVISE_DATA_NEED_SPEC`) or the
   request's input budget;
3. downloads each file with its checksum verified and stores it read-only (0444) under
   `PY_SANDBOX_BUNDLE_DIR` (`/data/bundles`, root only), where it survives restarts until the bundle expires;
4. runs the **Data Quality Profiler** (`runtime/profiler.py`, DuckDB). It runs in a confined process as the
   validator user, with the validator's limits and seccomp. It measures and never changes the data: no
   recalculation, cleaning, imputation or outlier removal. Per data request it reports:
   - rows, entities, first and last date;
   - each requested range with its requested, extracted and actual bounds, rows, entities and status (OK,
     PARTIAL, EMPTY);
   - partitions with rows outside their window;
   - duplicate primary keys and null counts per column;
   - frequency gaps against the dataset's own calendar (listings and delistings are not gaps);
   - history and future buffer shortfalls per range;
   - empty entities the scope named explicitly;
   - backward date steps;
   - `quality_flags`, the codes of every finding that is not clean;
5. runs **delivery coverage** (`app/coverage.py`). It compares the approved need, the SQL execution manifests
   (lineage and executed scope), the Data Quality Manifests and the delivered files:
   - the lineage and executed scope of every part: need, plan, request, part key, scope and restriction hashes,
     columns, table, window;
   - no sampling and no truncation;
   - the catalog version each part ran under;
   - partition tiling: on every date of every approved window, each entity residue is delivered exactly once;
   - each part's delivered rows and entity set against its SQL manifest (an entity present in SQL but missing
     downstream fails).
   Quality findings are flags, not coverage failures.
6. records the bundle with its manifest checksum. Coverage `PASS` gives `READY` (next action
   `OPEN_ANALYSIS_SESSION`). `FAIL` gives `REJECTED` and removes the files; the next action is `REPORT_LIMITATION`,
   or `REVISE_DATA_NEED_SPEC` when the catalog changed since approval. The same plan again replays the bundle.

`GET /v1/bundles/{bundle_id}` returns the complete manifest, including the Data Quality Manifests and coverage.
The POST answer is the model view: no file paths and no dataset internals. Expired bundles are deleted, and the
oldest are evicted above `PY_SANDBOX_BUNDLE_STORE_BYTES`.

**Phase 3 (implemented): persistent analysis sessions** (`app/sessions.py`, `runtime/session_worker.py`,
`runtime/saniti_session.py`). `POST /v1/sessions {request_id, bundle_id}` starts one long-lived worker on a READY
bundle of the same request.
- The worker runs as a dedicated session user (`PY_SANDBOX_SESSION_UID_BASE` + slot, users `session1..4` in the
  image). It gets a constructed environment and a private response pipe. Before it reads any command it confines
  itself: the session CPU budget as `RLIMIT_CPU`, virtual memory, file size, process count, CPU set, and seccomp (no
  sockets, no new processes).
- The workspace: the bundle files are copied read-only into `input/` with their checksums verified;
  `intermediate/` and `output/` are private to the session user; `session.json` is root-owned. The bundle store,
  the jobs root and other sessions are out of reach.
- `POST /v1/sessions/{id}/execute {request_id, code}` runs code in the persistent namespace, one command at a time.
  Variables and functions survive between executions. The result is `OK`, `SCRIPT_ERROR`, `TIMEOUT` or
  `INSUFFICIENT_INPUT_DATA`:
  - `SCRIPT_ERROR` carries `error_type`, `line`, `field` (for example a missing column), a traceback of the
    session's own code, and next action `REVISE_PYTHON_CODE`;
  - `TIMEOUT` means the wall clock (`PY_SANDBOX_SESSION_EXECUTION_SECONDS`) was reached. The harness sends SIGINT and
    the session survives; if the code does not yield within 5 s, SIGKILL ends the session;
  - `INSUFFICIENT_INPUT_DATA` comes from `saniti.insufficient_data(request, range_id, value, unit, reason)`, with
    next action `REVISE_DATA_NEED_SPEC`.
- Resident memory and the disk quotas are watched continuously; a breach ends the session. `MemoryError` under the
  virtual-memory limit is an ordinary `SCRIPT_ERROR`.
- A session that ends answers `409 SESSION_ENDED` with its `close_reason` (S16, 2026-09-30):
  - `SESSION_STATE_CORRUPTED`: the code changed the worker's own state (for example `saniti_session` or the
    `research_*` modules) so that the bookkeeping after the execution failed; the worker answers this status and exits
    with code 3, and the message says not to import or modify those modules;
  - `WORKER_CRASHED` (with the exit code) or `PROTOCOL_ERROR` (a line on the private protocol pipe that is not JSON):
    the harness waits up to 2 s for the process to exit before it labels it, so a crash is no longer reported as
    `WORKER_UNRESPONSIVE`;
  - the worker reads commands from private duplicates of its pipes: closing `sys.stdin` or fd 0 no longer ends the
    session, and `sys.argv` names no fd (robustness, not a security boundary);
  - before the workspace is removed, the last 600 bytes of `worker.log` are logged as `session_worker_ended`
    (server log only, never returned to the model), and the execution that ended the session is archived to the
    audit store with status `SESSION_ENDED` (its exact source included) when audit archival is on.
- `POST /v1/sessions/{id}/inspect {request_id, names?, max_rows?}` lists or describes variables with bounded
  previews.
- `GET /v1/sessions/{id}?request_id=` returns the session state, the execution log and the outputs.
- `GET /v1/sessions/{id}/outputs/{output_id}?request_id=&offset=&limit=` reads an output back: table rows page by
  page, JSON or text; charts and files give metadata only.
- `POST /v1/sessions/{id}/close` closes the session.
- Helpers (`saniti`, pre-bound by name with `pd` and `np`):
  - `requests()`, `manifest()`, `quality(request)`;
  - `load(request)` (the whole dataset in delivered order), `load_range(request, range_id, include_buffers=False)` (also `saniti.range`; S21: a helper named
    like a Python built-in is not pre-bound, so plain `range()` stays the built-in),
    `sql(query)` (one read-only DuckDB view per logical name), `relation(request)`;
  - `join(relationship_id, left, right, how)`, the approved relationship with its point-in-time semantics
    (CURRENT_STATE, EXACT_DATE, AS_OF backward, EFFECTIVE_DATED half-open), on every key pair. It checks the
    declared cardinality: a side declared "one" (and an AS_OF / EFFECTIVE_DATED history per key and time) must be
    unique, otherwise `JoinCardinalityError`; a result larger than the grain allows is refused; a LEFT join keeps
    every left row with `_saniti_match` = `matched` / `unmatched`; null keys never match. For EFFECTIVE_DATED, history
    rows whose validity is empty (`effective_to <= effective_from`, for example knowledge superseded the day it was
    recorded) are dropped first, as the Governor's restriction never matches them, and the remaining versions of a
    key must not overlap (`JoinCardinalityError` otherwise); the right side may be filtered first (a sector scope),
    because the version is chosen by date, not by the filter (IP1 Stage D). `join_report()` gives the
    rows on each side and out, unmatched rows, null keys and the grain checked (also in the access log);
  - `preaggregate(relationship_id, frame, measures)`: the many side aggregated to the relationship's key grain
    (entity keys and date) with each column's catalog cross-entity rule. A column without one (ratios, percentiles,
    z-scores, day counts, repeated stock-level values) raises `AggregationRuleMissing`; a given rule must equal the
    catalog's. The result has `source_rows` and is the only input `join` accepts for a relationship that requires
    preaggregation;
  - `resample(frame, request, frequency)` with the catalog rules;
  - `period_return(request, range_id, value_column='close', entity_column=None, date_column=None)`, a named
    calendar-period return per entity (see below);
  - `event_study(request, event, outcome, horizon, ...)`, an event study the backend recomputes at completion (see
    [Event study](#event-study-g2-2026-10-02));
  - `insufficient_data(...)`, `intermediate_path(name)`;
  - `emit_table`, `emit_chart`, `emit_json`, `emit_text`, `emit_file` (TABLE, CHART, JSON, TEXT, PARQUET, CSV, PNG,
    ARTIFACT). `emit_table` and `emit_json` take `units={column or field: 'FRACTION' | 'PERCENT' | 'P_VALUE'}` (P23,
    2026-10-02): FRACTION is a share or a decimal return (0.12 is 12%), PERCENT a value already in percent, P_VALUE a
    p-value. An unknown unit or column is refused (`OUTPUT_INVALID`); the collector re-checks them and keeps them in
    the output's `meta.units`, which `GET /v1/sessions/{id}/outputs/{output_id}` returns and market-ai-orc formats the
    answer's figures by.
  - **Output definitions (H1, M63, 2026-10-02).** `emit_table` and `emit_json` take
    `definition={'filters': [{'column', 'operator', 'value'}], 'period': {'start', 'end'}, 'entities', 'thresholds',
    'notes'}`: how the result was made beyond the data request. The filters use the DataNeed scope operators.
    - `{}` states that no filter beyond the data request was applied.
    - The runtime validates the definition and the collector keeps it in `meta.definition`.
    - `complete_analysis` does not release a TABLE or JSON whose latest version has no definition. It returns
      `INCOMPLETE`, `next_action RUN_PYTHON` and `missing_definitions`.
    - The helpers (`event_study`, `event_summary`) fill their own definitions.
    - Released outputs carry `definition` and `lineage` (execution_id, code_sha256, need_id, bundle_id).
    - Carried tables and `load_output(...).attrs` carry the definition, and `final_status.carried_inputs` lists the
      definition of each loaded table.
    - The approved view of a data need shows each request's `scope` and `restrictions`, readable (DERIVED).
  - **Research records (S13).** The host refuses a second `research_call_`/`research_input_` record of an angle that a
    successful execution of the epoch already stored (`rejected_outputs` reason `ANGLE_ALREADY_RECORDED`). It reads the
    store, not the worker's memory.
  - **Approved success rule (M28).** A hypothesis plan's `success_rule` `{operator, value}` reaches the session
    (`session.json` `research_v1`).
    - `event_summary` applies it and refuses a different `success_above` or a `success_column`.
    - It records the rule used in `research_summary_<id>`.
    - `research_findings.evaluate` returns INVALID when that rule is not the approved one.
- Value types of every frame from `load`, `range`, `sql` and `join`:
  - the time column holds `datetime.date` objects (object dtype);
  - numeric columns are float64, and text columns are pandas strings.

  The open-session response states this in `data_types` and names each dataset's `time_column`. Code should therefore
  compare dates with `datetime.date(...)` or select a period with `range()`, or convert with `pd.to_datetime` before
  using `.dt`, `.resample()` or a string comparison. In the 2026-09-26 stress test, 15 of 106 executions failed with
  `SCRIPT_ERROR`, mostly from pandas date idioms applied to these objects. The `session_execution` log event carries
  the first 200 characters of a failed execution's error message (`error_message`).
- Every helper read is recorded per execution (call, request, range, rows) for processing coverage. Reads outside
  the helpers are not recorded, so they count as not processed.
- `period_return` applies one boundary convention to named calendar periods (YTD, month, quarter, year, a comparable
  calendar period):
  - base = the last valid (non-null, finite) value strictly before the range start; end = the last valid value on or
    before the range end, observed inside the range (a value from before the start is never reused as the end);
    `return_decimal = end / base - 1`, `return_pct = return_decimal * 100`, never rounded;
  - it reads through `range(request, range_id, include_buffers=True)`, so the range and its history buffer are
    recorded for coverage; without a history buffer before the range it refuses (`PeriodReturnError`: declare
    `history_buffer` 1 `TRADING_OBSERVATIONS`) instead of using the first value inside the period;
  - one row per entity of the delivered range window, plus entities the scope named without data, sorted by entity:
    `entity, base_date, base_value, end_date, end_value, return_decimal, return_pct, calculation_status, range_id,
    period_start, period_end`; input order does not matter;
  - `calculation_status`: `COMPLETE`; `NO_PRIOR_CLOSE` (no valid value before the start within the delivered
    buffer); `NO_END_VALUE` (no valid value inside the period); `INVALID_BASE_VALUE` (a zero or negative base: no
    division); `INSUFFICIENT_INPUT_DATA` (no valid value, or an entity the scope named that has no row);
    `DUPLICATE_BOUNDARY_OBSERVATION` (different valid values for one entity on the base or end date: none is
    picked; identical duplicates are fine). A summary warning `PERIOD_RETURN_EXCLUSIONS` counts the entities that are
    not `COMPLETE`;
  - arguments are validated (range, value column numeric, entity column, the date column must be the request's time
    column) with a bounded `PeriodReturnError`. The entity and time columns default to the request's catalog columns;
  - it is a standard calculation utility, not a validator: the Coverage Validator still checks only data coverage,
    and custom formulas, TA-Lib, pandas and DuckDB stay available. market-ai-orc teaches the convention only with its
    `AI_ENABLE_STANDARD_PERIOD_RETURN` flag.
- Every emitted output is copied into a root-only store with its checksum, and is `released: false` until the
  analysis completes with coverage PASS (phase 4).
- Budgets per session: executions, failed executions, CPU seconds, outputs, idle time and lifetime. Sessions are
  bound to their request and do not survive a restart (`SANDBOX_RESTARTED`); bundles and outputs do. A janitor
  closes idle and expired sessions and deletes expired outputs and bundles.

**Phase 4 (implemented): completion.** `POST /v1/sessions/{id}/complete {request_id}` builds, from the harness's
own records (never from anything the code reported about itself):

- the **ExecutionManifest**: every execution with its code hash, status, CPU and outputs; what the helpers read per
  request and range in successful executions; every output with its checksum;
- **processing coverage**: an approved request is PROCESSED when a successful execution read it in full
  (`load`, `sql` naming its view, `relation`, or `join` on the whole datasets), or read every one of its ranges with
  `range`. Reads in failed executions and direct file reads do not count;
- the **Coverage Validator** result: delivery coverage (from the bundle) and processing coverage per request and
  range, with the partitions expected and delivered, `sampling` and `truncation`;
- the **final status**:
  - `data_need_validation`, `research_governance` (NOT_APPLICABLE for ANALYSIS), `sql_governance`,
    `data_quality_profiling`, `data_coverage`;
  - `sandbox_execution`: SUCCESS needs a successful execution with outputs, and no later
    `INSUFFICIENT_INPUT_DATA`;
  - `calculation_validation`: always `NOT_PERFORMED`;
  - `data_complete`, `execution_complete`;
  - `evidence_label`: `DATA_COVERAGE_VERIFIED` or `NOT_VALIDATED`;
  - `warnings`: relationship warnings and quality flags;
  - `claims_allowed` and `claims_forbidden`. For RESEARCH, the forbidden claims also include causal effects and
    predictions.

When coverage passes and the execution succeeded, the outputs of successful executions are **released**
(`released: true`), the completion is stored, and the session closes (`COMPLETED`). Otherwise nothing is released
and the session stays open. `next_action` is `RUN_PYTHON` with the requests and ranges not yet processed,
`REVISE_DATA_NEED_SPEC` after insufficient data, or `REPORT_LIMITATION`. A COMPLETED completion replays; an
INCOMPLETE one is evaluated again at the next call, so an analysis that read its data but had no output yet can finish
after the fix (`ERRORS_AND_SOLUTIONS.md` S06; before, an INCOMPLETE result with coverage PASS was replayed forever).

### Conversation reuse (`PY_SANDBOX_ENABLE_CONVERSATION_REUSE`, off by default)

Implementation plan of 2026-09-27, phases S1 and S2, for market-ai-orc's `history_mode: SERVER` conversations.
Everything below needs the flag; without it the header is ignored and nothing changes (sessions close on a passed
completion, completion responses keep their shape).

- **Conversation key.** market-ai-orc sends `X-Saniti-Conversation-Key: ck_<32 hex>` on every call of a run. It
  derives the key from the conversation and its owner; the model can neither see nor set it. A need submitted with
  the key records it together with `contract_sha256`, the hash of its **data contract** (`data_need.py`
  `data_contract_sha256`): mode, subject, every request's `data_request_id`, `logical_name`, table, columns, column
  types, canonical scope and restrictions, extraction windows, frequencies, resample rules, buffers, ordering and
  catalog table version, the relationships, and the catalog version. The request group, revision and question are
  left out. A bundle built for such a need belongs to the same conversation.
- **Bundle reuse (S1, coverage 2c).** `POST /v1/bundles/reuse {request_id, need_id}` binds this request's own
  approved need to the newest READY, unexpired bundle of the conversation from an earlier request whose need has the
  same `contract_sha256` or **covers** it, when all its files are still present. Covering (`data_need.contract_covers`,
  user decision 2026-10-02): the mode is ignored (an analysis bundle serves a research need and back) and the earlier
  columns, extract columns, column types and resample rules may be wider; every other contract field (requests and
  their tables, scope, restrictions, windows, frequencies, buffers, ordering, catalog versions, relationships,
  subject, time basis) must be equal. A narrower scope or a shorter window is not served: it extracts again (speed
  plan step 9 item 4, open). The binding (`bundle_bindings`) records the source need and request. The bundle's
  manifest and checksum never change. The answer is the bundle view with the current `need_id`, `reused: true` and
  `reused_from` (`bundle_id`, source `need_id` and `request_id`, `extracted_at`, `expires_at`, `equal_candidates`).
  Otherwise the answer is `NO_MATCH` with a reason (`NO_COVERING_CONTRACT`, `EXPIRED`, `NEED_NOT_IN_CONVERSATION`). A
  changed catalog changes `catalog_sha256`, so it never reuses.
- **Warm sessions (S2).** A passed completion of a session with a conversation key leaves the worker `WARM_IDLE`
  instead of closing it, unless an execution of that epoch timed out, which leaves the namespace uncertain.
  - `POST /v1/sessions` on a bound bundle (or the request's own) first looks for a `WARM_IDLE` session on it in the
    conversation. If one exists, it is **attached**: a new epoch starts for the current request and its approved
    need (`session_epochs`), and the answer carries `reused_session: true`, `epoch`, `origin_request_id`,
    `parent_completion_id`, the earlier `variables` and `session_budget`.
  - Otherwise a new worker opens on the bundle, and the RAM of the earlier message is gone.
  - After an attach, the earlier request can no longer use the session.
  - Execution count, failed count, CPU and lifetime are cumulative and never reset by an attach.
  - Running code in a `WARM_IDLE` session of the same request (after its own completion passed) starts a new epoch.
  - With no free slot, the least recently used `WARM_IDLE` session is closed (`EVICTED`); an `ACTIVE` or `BUSY`
    session never is. `WARM_IDLE` sessions close after the idle time like any other.
  - A caller's close of an attached session that ran nothing in its epoch returns it to `WARM_IDLE`
    (`DETACHED_UNCHANGED`); any other close ends it.
- **Per-epoch completion.** `complete` works on the current epoch only: its executions (sequence after the epoch
  start) and their outputs.
  - A COMPLETED result of an earlier epoch never completes a later one.
  - An epoch with no successful execution and output is INCOMPLETE.
  - Only the epoch's own outputs are released; earlier completions and outputs are never changed.
  - A request that this epoch did not read again but that any earlier PASS epoch of the same session and bundle read
    in full counts as `INHERITED` (coverage `processing: INHERITED`). The final status then names
    `inherited_coverage` (`parent_completion_id`, `parent_request_id`, `ancestor_completion_ids`,
    `data_request_ids`). Every earlier passed epoch counts, because they share one namespace (S07).
  - The completion carries `epoch` and `session_status` (`WARM_IDLE` or `CLOSED`).
- **Released outputs across requests (READ_RELEASED).** `GET /v1/sessions/{id}/outputs/{output_id}` with the
  conversation key also serves a **released** output of an earlier request of the conversation, or of an earlier
  epoch. The answer adds `read_mode: READ_RELEASED` and `origin`: the completion that released it, its request,
  need, time, `evidence_label` and warnings. The label is never raised. An unreleased output of another request or
  epoch, a wrong key or no key: `OUTPUT_NOT_FOUND`.
- **Resources.** `GET /v1/conversations/{key}/resources` lists, for market-ai-orc's note to the model, ids and
  summaries only, no data:
  - up to 3 unexpired READY bundles, each with its approved `data_need_spec` to resubmit and its warm session;
  - up to 12 unexpired released outputs, each with the completion that released it.
- **Recovery.** A restart closes every session, `WARM_IDLE` included (`SANDBOX_RESTARTED`). Bundles and released
  outputs survive within their retention (24 h), so a later message reuses the bundle and computes again, or reads
  the released outputs.
- **Research.** Reuse never replaces approval. An attach needs this request's own approved need, and a RESEARCH need
  is approved only with its Research Governor decision. A bundle may serve both modes (2c), but a warm worker never
  does: a RESEARCH need always opens a fresh worker (the variables of an earlier epoch are not part of what its plan
  approved, and it gets its own compute budget), and an ANALYSIS need never takes over a research worker.
- **Carried results (2a, 2d) and data profiles (P1, P2, P5), user decisions 2026-10-02.** Before every execution
  the released PARQUET tables of the conversation (newest first, at most 40, never another session's backend records
  `research_call_` / `event_study_call_`, never expired) are hard-linked read-only into the session's `input/carried/`
  with a `manifest.json` (`app/carried.py`): per table its `output_id`, name, path (`kind`: G4 `research_input_`, G3
  `research_events_` / `research_summary_`, G2 a recomputed event-study table, else G1), `label` and `label_meaning`,
  columns, rows, `origin` (completion, request, need, time, calculation validation) and a `profile`.
  - In code: `saniti.carried()` lists them; `saniti.load_output(output_id_or_name, columns=None)` loads one within the
    frame budget, sets `frame.attrs` label, origin and kind, and logs the load; the completion lists the loaded tables
    as `final_status.carried_inputs` (output id, name, kind, label), and market-ai-orc flags research findings that
    loaded one as IN_SAMPLE.
  - A session of a RESEARCH need carries only the tables its approved plan names: `POST /v1/sessions` takes
    `carried_outputs` (at most 40 output ids); a RESEARCH need without it carries none (fail closed). Other needs
    carry every released table of the conversation.
  - The open view adds `carried_outputs` (a listing with labels and origins, at most 20 with a count of the rest) and
    a `carried_note`; every bundle dataset in the view gets a `profile` (P1).
  - Profile (one DuckDB scan, cached per table): rows, entities and date range; per column (first 40, the rest
    counted) type, nulls, approximate distinct values and min / median / max (numbers), min / max (dates) or the 5
    most frequent values (text, first 12 text columns); 5 sample rows. It is for understanding the data before writing
    code; answers still cite released outputs and findings.
  - P5: `GET /v1/sessions/{id}/outputs/{output_id}` adds `label` and `label_meaning` to every page
    (CALCULATION_VERIFIED for a recomputed event-study table, else the completion's evidence label; NOT_RELEASED for an
    output not released yet).
- **SQLite.** Schema version 1 (`PRAGMA user_version`), applied at startup in one transaction per version, adds
  nullable or defaulted columns and two tables:
  - columns: `conversation_key` and `contract_sha256` on needs, `conversation_key` on bundles,
    `origin_request_id`, `conversation_key`, `need_id`, `epoch` and `epoch_start_seq` on sessions, `epoch` and
    `request_id` on executions, `epoch` and `parent_completion_id` on completions;
  - tables: `bundle_bindings` and `session_epochs`.
  Existing rows keep epoch 1. Code without these columns still reads and writes the database, so a rollback of the
  code is safe (`WARM_IDLE` rows are then only closed by the next restart).
- `GET /v1/runtime` reports `conversation_reuse: {enabled, version: 1}`. market-ai-orc turns its reuse on only when
  both are right.

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
  - `PERIOD_STAT` is a statistic (`AVG`/`MEDIAN`/`STD`/`MIN`/`MAX`/`SUM`/`COUNT`) of one entity's
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
    - each entity's daily returns inside the period (`PERIOD_STAT AVG` of a `RETURN`).

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

   Every `INVALID_SPEC` problem ends with its machine code in parentheses. When the fix follows from
   the spec itself, the message states it:
   - the dataset a chained calculation must use (the dataset of the chain's first calculation, so
     one wrong link is reported once);
   - the expected `key_columns` of a group output;
   - the reference date for an open-ended period ("sejak ...");
   - for a period `ANALYSIS_SCOPE_MISMATCH`, the requested dates. A `PERIOD_RETURN` with base
     `PREVIOUS_OBSERVATION` already takes its base from before the start, so the start is not
     moved back.
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
| `ROLLING_CORRELATION` | `window`, `method` (`PEARSON`/`SPEARMAN`), `transform` (`NONE`, `DEFAULT_ROLLING_CORRELATION_TRANSFORM`) | TA-Lib CORREL | reference recalculation |
| `CORRELATION` | `method`, `transform` (`SIMPLE_RETURN`), `min_overlap` (20); `ENTITY_PAIR` output | TA-Lib CORREL | reference recalculation per pair |
| `PERIOD_RETURN` | `kind`, `as_percent`, `base` (`PREVIOUS_OBSERVATION`) | Saniti | reference recalculation |
| `PERIOD_STAT` | `function` (`AVG`/`MEDIAN`/`STD`/`MIN`/`MAX`/`SUM`/`COUNT`; `MEAN` is accepted as `AVG`), `ddof` (1, `STD` only), `min_observations` (1) | Saniti | reference recalculation (expanding within the period) |
| `GROUP_AGGREGATE` | `function`, `per_date` (false, `DEFAULT_GROUP_PER_DATE`), `missing_group_policy` (`SEPARATE_GROUP`), `unknown_group_values` ([]), `min_observations` (1); `group_by` or `segments` | Saniti | groups recalculated from entity rows |
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
- `followup_of`, `candidates`, `holdout`;
- the design (the evidence contract):
  - `design_type`: `EVENT_STUDY`, `COMPARATIVE`, `ASSOCIATION`, `PREDICTIVE_TEMPORAL` or
    `EXPLORATORY_SEARCH`;
  - `primary_metric`: the calculation the claim is about;
  - `observation_unit` (derived when null);
  - `comparator`: `GROUPS` or `ALL_OTHERS`, optionally with the compared `groups`;
  - `multiple_testing_policy`: `NONE` or `BONFERRONI`.

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
- `HISTORICAL_PATTERN` and `PREDICTIVE` need a hypothesis.
- A V2 `HISTORICAL_PATTERN`, `PREDICTIVE` or `EXPLORATORY` claim declares its design
  (`RESEARCH_DESIGN_REQUIRED`). The design must fit the claim (`DESIGN_STANDARD_MISMATCH`):
  - `PREDICTIVE` claims need `PREDICTIVE_TEMPORAL`;
  - `EXPLORATORY_SEARCH` is for `EXPLORATORY` claims only;
  - `EVENT_STUDY`, `COMPARATIVE` and `ASSOCIATION` support pattern, exploratory and descriptive
    claims.
- Design requirements, none of them topic-specific:
  - `EVENT_STUDY` and `PREDICTIVE_TEMPORAL` need an `EVENT_STUDY` calculation, the implemented
    temporal evaluator.
  - `COMPARATIVE` needs a `GROUP_AGGREGATE AVG` (not per date) of a per-entity metric in a `GROUP`
    output (`PRIMARY_METRIC_INVALID`), and a comparator (`COMPARATOR_REQUIRED`).
  - `ASSOCIATION` needs a `CORRELATION` or `GROUP_CORRELATION`.
  - `EXPLORATORY_SEARCH` declares its search space as `candidates` of at least 2
    (`SEARCH_SPACE_REQUIRED`).
- A design with more than one comparison declares them:
  - `candidates` must be at least the comparisons the spec determines (`CANDIDATES_UNDERSTATED`);
  - `multiple_testing_policy` must be `BONFERRONI` (`MULTIPLE_TESTING_POLICY_REQUIRED`).
- A V1 spec without a design keeps the earlier rule: pattern and predictive claims need an
  `EVENT_STUDY`.
- `PREDICTIVE` also needs a temporal holdout inside the period, covering at least 20% of it.
- The physical date partitions of one approved data plan are not experiments: one approved spec
  is one experiment.
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
- `COMPARATIVE` designs (profile X) use the validator's own per-entity values of each group:
  - group sizes of at least `min_group_observations` (10);
  - Welch 95% intervals of each difference of group means;
  - a Bonferroni adjustment over every comparison actually made. When the data yields more
    comparisons than declared, the larger count is used.
- `ASSOCIATION` designs use each recalculated correlation with its common observations:
  - at least `min_association_observations` (30) observations;
  - a Fisher-z interval and the same adjustment over every evaluated pair;
  - a reporting constraint that time-series autocorrelation can make the interval too narrow.
- An exploration is at most `PARTIALLY_SUPPORTED`.
- A non-significant result is reported as such. Another look at the same hypothesis is an
  explicit, budgeted follow-up of a completed experiment, and it widens the adjustment.

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
| `POST /v1/data-needs`, `GET /v1/data-needs/{need_id}` | DataNeedSpec validation and the approved contract (only with `PY_SANDBOX_DATANEED_ENABLED`; see above) |
| `POST /v1/data-needs/check`, `GET /v1/data-need-drafts/{draft_id}` | Research Plan feasibility drafts: validated, never extracted (only with `PY_SANDBOX_DATANEED_ENABLED`; see above) |
| `POST /v1/bundles`, `GET /v1/bundles/{bundle_id}` | Governed data bundle: verification, profiling, delivery coverage (only with `PY_SANDBOX_DATANEED_ENABLED`) |
| `POST /v1/sessions`, `POST /v1/sessions/{id}/execute`, `POST /v1/sessions/{id}/inspect`, `GET /v1/sessions/{id}`, `GET /v1/sessions/{id}/outputs/{output_id}`, `POST /v1/sessions/{id}/complete`, `POST /v1/sessions/{id}/close` | Persistent analysis sessions (only with `PY_SANDBOX_DATANEED_ENABLED`) |
| `POST /v1/research-runs`, `GET /v1/research-runs/{id}`, `POST /v1/research-runs/{id}/groups/{g}/close` | Multi-Angle Research runs (only with `PY_SANDBOX_MULTI_ANGLE_RESEARCH_ENABLED`; see above) |
| `POST /v1/runs/{request_id}/report` | market-ai-orc's final report of the run (answer and hash, evidence label, gate, experiments). Stored once; a retry keeps the first. `status` may also be `AWAITING_CONFIRMATION` with `response_type` `RESEARCH_PLAN_CONFIRMATION` (a Research Plan awaiting the user's approval). |

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
cleanup does not depend on redeploys. Active workspaces are never touched, and neither are the
`sess_*` workspaces of analysis sessions, which the session manager owns and removes when it closes a session (S14,
2026-09-29: the janitor had deleted an open session's inputs mid-run). After the input
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
| `PY_SANDBOX_FRAME_MEMORY_PERCENT` | 40 (share of the memory limit one pandas frame may take; G14) |
| `PY_SANDBOX_MAX_INTERMEDIATE_BYTES` | 1 GiB (includes DuckDB temp) |
| `PY_SANDBOX_MAX_OUTPUT_DIR_BYTES` | 256 MiB |
| `PY_SANDBOX_CPUS_PER_JOB` / `_THREADS_PER_JOB` | 2 / 2 |

#### DuckDB first: the frame budget (G14)

A session's data are DuckDB views; pandas frames are what fill its memory. Before `load()`, `range()` or `sql()` turn
a result into a pandas frame, the session estimates the frame's size (rows, counted up to one row past the limit, times
bytes per value by column type: 8 for numbers, 64 for dates, 72 for text) and refuses a frame over the budget
(`PY_SANDBOX_FRAME_MEMORY_PERCENT` of `PY_SANDBOX_MAX_MEMORY_MB`, 819 MB with the defaults) with
`MaterializationLimitExceeded`. Nothing is loaded and the session, its data and variables stay; the execution result
says `next_action: AGGREGATE_IN_SQL` and forbids preparing the data again. The opened session (`datasets[]`) and
`requests()` show per dataset `frame_mb`, `frame_budget_mb` and `materialize` (`DIRECT` or `AGGREGATE_FIRST`), so the
model knows before writing code whether to reduce the data in DuckDB first. `relation()` stays lazy and its own `.df()`
is not size-checked; the memory watchdog (`MEMORY_LIMIT_EXCEEDED`) still applies. With conversation reuse on, a data
need prepared again in its own request gets its READY bundle back (`reused`, `replayed`) instead of a new extraction.
`GET /v1/runtime` reports `bundle_max_rows`, `bundle_max_bytes` and `bundle_max_parts` in its top-level `limits`, so
every caller can check a bundle's size before extracting it.
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
| `PY_SANDBOX_MAX_TABLES` / `_TABLE_OUTPUT_ROWS` / `_TABLE_PREVIEW_ROWS` | 8 / 0 (no row limit, P12 2026-10-01; was 100,000) / 50 |
| `PY_SANDBOX_MAX_METRICS` / `_METRICS_BYTES` / `_OUTPUT_BYTES` | 8 / 8000 / 24,000 |
| `PY_SANDBOX_MAX_ARTIFACT_BYTES` / `_CHARTS` / `_ARTIFACTS` | 64 MiB / 8 / 8 |
| `PY_SANDBOX_SUBMIT_WAIT_SECONDS` / `_MAX_POLL_WAIT_SECONDS` / `_RETRY_AFTER_SECONDS` | 25 / 20 / 15 |
| `PY_SANDBOX_RESULT_RETENTION_HOURS` / `_RECORD_RETENTION_DAYS` | 24 / 30 |
| `PY_SANDBOX_FAILED_WORKSPACE_TTL_HOURS` / `_MAX_BYTES` | 6 / 64 MiB |
| `PY_SANDBOX_CLEANUP_INTERVAL_SECONDS` | 900 |
| `PY_SANDBOX_DATANEED_ENABLED` | false (the DataNeed routes answer 404) |
| `PY_SANDBOX_BUNDLE_DIR` | `<data dir>/bundles` (root only, on the volume) |
| `PY_SANDBOX_BUNDLE_RETENTION_HOURS` | 24 |
| `PY_SANDBOX_BUNDLE_MAX_ROWS` / `_MAX_BYTES` | `PY_SANDBOX_MAX_INPUT_ROWS` / `_MAX_INPUT_BYTES` |
| `PY_SANDBOX_BUNDLE_MAX_PARTS` | 128 |
| `PY_SANDBOX_BUNDLE_STORE_BYTES` | 8 GiB (oldest bundles evicted above it) |
| `PY_SANDBOX_SESSION_UID_BASE` / `PY_SANDBOX_MAX_SESSIONS` | 20201 / 2 |
| `PY_SANDBOX_SESSION_EXECUTION_SECONDS` | `PY_SANDBOX_MAX_RUNTIME_SECONDS` (per execution, SIGINT then SIGKILL) |
| `PY_SANDBOX_SESSION_CPU_SECONDS` | 900 per session (a RESEARCH need uses its approved compute budget when lower) |
| `PY_SANDBOX_SESSION_IDLE_SECONDS` / `_MAX_SECONDS` | 900 / 3600 |
| `PY_SANDBOX_SESSION_MAX_EXECUTIONS` / `_MAX_FAILED` / `_MAX_OUTPUTS` | 40 / 15 / 40 |
| `PY_SANDBOX_ENABLE_CONVERSATION_REUSE` | false ([conversation reuse](#conversation-reuse-py_sandbox_enable_conversation_reuse-off-by-default): bundle binding, warm sessions, per-epoch completion, READ_RELEASED) |
| `PY_SANDBOX_DERIVED_FREQUENCY_ENABLED` | false ([derived weekly/monthly](#derived-weekly-and-monthly-ip2-off-unless-py_sandbox_derived_frequency_enabledtrue)) |
| `PY_SANDBOX_AUDIT_STORE_ENABLED` | false ([audit archival](#audit-archival-ip2-off-unless-py_sandbox_audit_store_enabledtrue)); `AUDIT_STORE_URL` and `AUDIT_STORE_SANDBOX_KEY` are required only when on |
| `PY_SANDBOX_AUDIT_SPOOL_MAX_BYTES` / `_POLL_SECONDS` / `_MAX_ATTEMPTS` / `_TIMEOUT_SECONDS` | 512 MiB / 15 / 12 / 30 |

### Text filter values (G16 / review P14, 2026-10-01)

At approval every text filter value (EQ, NEQ, IN, NOT_IN on a text column) is matched to its stored spelling,
regardless of letter case:
- The stored values come from the Governor's catalog contract `value_domains`: single-column CHECK lists, and the
  category columns of static tables. Entity codes never travel there.
- Values are matched before any hash or extraction, so "regular" selects "Regular".
- A value with no stored match in a complete list is refused (`VALUE_NOT_FOUND`, with the stored values), and so are
  two stored values that differ only in case (`VALUE_AMBIGUOUS`).
- An entity code is upper-cased and trimmed (Part A A1.2).
- Each change is a `TEXT_VALUE_RESOLVED` warning.
- A column with no list (a dated category without a CHECK list) keeps the value as written.

### Table outputs and `resample` (review P12, P13, 2026-10-01)

- A table output has no row limit by default (`PY_SANDBOX_MAX_TABLE_OUTPUT_ROWS` 0). Outputs are kept for further
  analysis and research; what the model reads stays the preview (`_TABLE_PREVIEW_ROWS`) and pages of at most 500 rows.
- The byte limits per file (`PY_SANDBOX_MAX_ARTIFACT_BYTES`) and per session output directory
  (`PY_SANDBOX_MAX_OUTPUT_DIR_BYTES`) still apply.
- `resample` without a `resample_semantics_version`:
  - groups by the request's grain (`key_columns`, for example `market_board`) instead of asking for a rule for it;
  - returns the derived semantics' period columns (`period_start`, `period_end`, `actual_first_date`,
    `actual_last_date`, `period_complete`) after its existing columns; values are unchanged.

### Derived weekly and monthly (IP2, off unless `PY_SANDBOX_DERIVED_FREQUENCY_ENABLED=true`)

Weekly and monthly data are always derived from daily rows, never read from a weekly table, and monthly is never built
from weekly. With the flag on:

- **Validation.** A request with `resample` must have `source_frequency` `1D` (`RESAMPLE_SOURCE_NOT_DAILY`), and every
  requested measure must have a catalog `resample_aggregation` (`RESAMPLE_RULE_MISSING`, refused before any
  extraction).
- **Contract.** The approved contract carries `resample_semantics_version` 1 and hashes it. Requests without
  `resample`, and every request with the flag off, keep their previous hash.
- **`saniti.resample(frame, request)`** (semantics version 1):
  - groups by the table's full grain, so no entity or broker is mixed;
  - refuses duplicate `entity + trading_date` rows (`DUPLICATE_ENTITY_DATE`) and a frame that was already resampled;
  - converts timestamps to Asia/Jakarta trading dates;
  - uses calendar weeks Saturday–Friday labelled by the Friday, and calendar months labelled by the month end;
  - sorts deterministically;
  - FIRST/LAST take the first/last non-null value; MAX/MIN ignore nulls; SUM is null when every value is null;
    nothing is filled;
  - adds `period_start`, `period_end`, `actual_first_date`, `actual_last_date`, `observations` and
    `period_complete`.
- **Completeness.** `period_complete` is true only when the whole calendar period lies inside the approved extraction
  window, ends on or before the reference date, and the data reaches its last calendar day. The open week or month,
  or a partly covered one, is false.
- **Trace.** Each call leaves a bounded trace in the execution record (log `saniti_resample`: request, frequencies,
  input and output rows, periods, rules hash, semantics version, incomplete periods), never the data.
- **Returns.** `saniti.resampled_returns(resampled, request)`: the period close (LAST) over the previous period's
  close, minus one, with the base period, `periods_between` and both periods' completeness. Daily returns are never
  summed.
- **Final status.** It gains `derived_frequency`: per request the frequencies, period policy and resample calls, the
  completeness and null rules, the contract hash, the input checksum and the execution ids.

With the flag off, a `resample` request behaves as before. The legacy `saniti.resample()` aggregation was corrected to
one rule per column (ERRORS_AND_SOLUTIONS S09); its output shape is unchanged.

### Event study (G2, 2026-10-02)

Plan: `G2_G3_REACTIVATION_PLAN.md` section 3 (repository root). Always available in analysis and research sessions;
the orc describes it to the model only with `AI_ENABLE_EVENT_STUDY`.

- **Helper.** `event_study(request, event, outcome, horizon, *, range_id=None, overlap_policy='NON_OVERLAPPING',
  baseline='ALL_ELIGIBLE', min_events=None, holdout_start=None, outcome_unit='PERCENT', name=None)`:
  - `event`: a condition in the research expression grammar over the request's columns (per entity, past values only),
    for example `close / lag(close, 1) - 1 <= -0.05`; `outcome`: `{'forward_return': '<price column>'}`, with
    `'request': '<data request id>'` when the price is in another request; `horizon`: observations (1 to 260);
  - every range is built on its own extracted window (`extract_from`..`extract_to`), so a forward return never spans
    two ranges (S24); overlapping ranges are refused; the request needs one row per entity and date;
  - events: NON_OVERLAPPING keeps an entity's next event only `horizon` observations after the last kept one (ALL keeps
    every one); an event whose outcome runs past the data is censored and counted apart;
  - baseline: ALL_ELIGIBLE (every row with a defined condition and outcome, the Analysis Spec convention) or
    NON_EVENT; `min_events` (default 30, a recorded policy value) sets `meets_min_events`; `holdout_start` adds
    IN_SAMPLE and OUT_OF_SAMPLE rows;
  - statistics from `runtime/research_engines.py`: dates are clusters and dates closer than the horizon are thinned,
    so a market-wide day with many events counts once (the Analysis Spec version treated rows as independent).
- **Outputs.** `<name>` (one row per segment: `event_count`, `event_dates`, `effective_event_dates`, `mean`,
  `median`, `hit_rate`, `baseline_count`, `baseline_mean`, `baseline_median`, `delta_mean`, `delta_ci_low`,
  `delta_ci_high`, `delta_p_value`, `censored_count`, `overlapping_dropped`, `meets_min_events`), `<name>_events`
  (`date`, `entity`, `outcome` of every kept event), `<name>_baseline` (the baseline rows, same columns; 2b,
  2026-10-02, so a later step can load it) and the internal JSON record `event_study_call_<name>` (the declaration and
  parameters). The prefix `event_study_call_` is reserved like `research_call_`. P23: the tables declare their units
  (`event_study.summary_units`: the outcome columns in `outcome_unit`, DECIMAL as FRACTION; `hit_rate` FRACTION;
  `delta_p_value` P_VALUE; `outcome` of the events and baseline tables in `outcome_unit`), and the recalculation below
  also checks the summary's declared units. Research findings carry their units too: v2 `estimates.units`
  (`research_engines.estimate_units`) and v1 `units` (`research_stats.summary_units`).
- **Event flow (S27, 2026-10-02).** The helper also releases `<name>_flow`, one row per segment: rows_in_window,
  condition_unknown, condition_true (the qualifying events), censored, overlapping_dropped, used. condition_true =
  censored + overlapping_dropped + used. The answer quotes these counts instead of deriving them, and the
  recalculation below checks this table too (`FLOW_MISSING` when it is absent).
- **Independent recalculation** (`app/event_study_validation.py`, at `complete_analysis`): the harness reads the
  declaration, rebuilds the input from the bundle files with `runtime/research_inputs.py`, recomputes the three tables
  with `runtime/event_study.py` and compares them with the released ones (counts exactly, numbers within a relative
  1e-9).
  - PASS: `final_status.event_studies[*].status` PASS, the three output ids in `final_status.verified_output_ids`,
    `calculation_validation` FORMULA_AND_STATISTICS_VERIFIED when every released output is such a table, else
    PARTIAL; the forbidden claims are scoped to the other calculations and an allowed claim names the studies;
  - FAIL (CALCULATION_MISMATCH, SUMMARY_MISSING, EVENTS_MISSING, BASELINE_MISSING, TABLE_UNREADABLE): the completion
    is INCOMPLETE with `next_action` RUN_PYTHON and a message naming the differing cells;
  - INVALID (the record cannot be rebuilt; reason named): the completion is not blocked and the tables are released
    without the label.
- **Return value.** The summary rows, the output metadata, and `events` and `baseline` as frames (`date`, `entity`,
  `outcome`), so a hypothesis plan (G3) can pass the same rows to `event_summary(events, baseline, hypothesis_id=...,
  outcome_column='outcome', date_column='date')`; findings v1 and Multi-Angle Research run in the same deployment.
- **Release.** The declaration record is released for the audit but left out of `released_outputs` and of the
  conversation resources (the `research_input_` and `research_call_` records are left out of the resources too). A
  read of a released event-study table in a later message carries `origin.calculation_verified`.

### Method guides (4b, 2026-10-02)

`app/method_guides.py` (byte-identical in market-ai-orc) holds the model-facing menu and manual of G1 free code, G2
event study, G3 hypothesis plan, G4 multi-angle plan and the main helpers. `GET /v1/runtime` reports
`method_guides: {enabled, version, sha256}` and `event_study: {enabled, version}`; market-ai-orc serves the guides only
when its copy and `public."AI_method_guide"` (migration `20261002_001`, generated by
`scripts/generate_ai_method_guide_migration.py`) carry the same hash. `tests/test_method_guides.py` keeps the guides
true to the code: every helper input is a parameter with the same default, every runnable example runs in a session,
the migration equals the generator's output.

### Research findings v1 (off unless `PY_SANDBOX_RESEARCH_FINDINGS_ENABLED=true`)

A condition -> outcome research experiment is judged by the backend, not by the model:

- **No fixed minimum sample.** With the flag on the Research Governor no longer refuses a plan whose declared minimum
  sample is below `PY_SANDBOX_RESEARCH_MIN_EVENTS` (the gate stays as before with the flag off). A RESEARCH
  `research_governance` must declare `expected_direction` (HIGHER, LOWER, DIFFERENT), `outcome_horizon_periods`,
  `outcome_unit` (PERCENT, DECIMAL, OTHER) and may declare `success_definition` and `min_effect`; they are recorded in
  `constraints.findings`.
- **`event_summary(events, baseline, hypothesis_id=..., outcome_column=..., date_column=...)`** (pre-bound only with the
  flag, via `session.json` `extra_helpers`) releases `research_events_<hypothesis_id>` (per-date aggregates: group,
  date, n, total, total_sq, k, m) and `research_summary_<hypothesis_id>`.
- **`complete_analysis`** of a RESEARCH need is COMPLETED only when that aggregate table was released; the harness
  reads the released copy and recomputes everything with `runtime/research_stats.py` and the approved values
  (`app/research_findings.py`): angle A (mean difference, CI, p-value), angle B (success share against the baseline
  share, Wilson/Newcombe), the effective sample (distinct dates at least `outcome_horizon_periods` apart), the smallest
  detectable effect (80% power, alpha 5% adjusted by the multiple-testing policy), the sample category and the verdict.
  The result is `final_status.research_findings`.
- Fixed categories: INSUFFICIENT (effective < 2 in a group: no verdict), ANECDOTAL (< 10), UNDERPOWERED (detectable
  effect above the smallest effect of interest: the plan's `min_effect`, else 0.5 percentage points for PERCENT, 0.005
  for DECIMAL, 0.2 standard deviations for OTHER), ADEQUATE. Verdicts: SUPPORTED, NOT_SUPPORTED, INCONCLUSIVE,
  NOT_EVALUATED (rules in `runtime/research_stats.py`).
- Limits: date clustering and horizon thinning approximate cluster-robust errors; correlation across dates beyond the
  horizon is not modelled. `/v1/runtime` reports `research_findings: {enabled, version: 1}`.

### Multi-Angle Research (off unless `PY_SANDBOX_MULTI_ANGLE_RESEARCH_ENABLED=true`)

Design, contracts and decisions: `MULTI_ANGLE_RESEARCH.md` (repository root); fixes after suite20:
`MULTI_ANGLE_FIX_PLAN.md`. Needs `PY_SANDBOX_DATANEED_ENABLED`. `GET /v1/runtime` reports `multi_angle_research`
(enabled, version 2, angle limits (two to six since 2026-09-29), grouped execution, findings and governance versions,
the method registry and its hash, the research library hash `library_sha256`, bundle limits); market-ai-orc turns its
side on only when they match.

- `PY_SANDBOX_RESEARCH_MIN_ANGLES` (default `2`, 1 to 6; user decision 2026-09-30): the fewest angles one plan may
  have, reported as `min_angles`. market-ai-orc's mode 4 proposes one-angle follow-up plans only when it is `1`; its own
  `AI_RESEARCH_MIN_ANGLES` (default 2) still applies to every plan outside mode 4.

- Research library (C07): `app/research_library.py` (byte-identical in market-ai-orc) describes the eight methods for
  the model: family, question, input roles, parameters, data requirements, sample unit, secondary checks,
  interpretation, misuse warning and an example. Migration `20260930_001` writes it to `public."AI_research_library"`
  (`scripts/generate_ai_research_library_migration.py`; `tests/test_research_library.py` fails on drift). It
  describes; the engines and `research_engines.decide` stay the enforcement.

- `POST /v1/research-runs` `{request_id, origin_request_id, research_governance, research_data_plan}`: the Research
  Governor v2 reviews the declaration (angle count and budgets, parameters bound to each method, multiple testing,
  follow-up semantics, `app/research_governance.py`); every hash is recomputed and each signed feasibility draft of
  the origin request is promoted into one approved RESEARCH need per bundle group. A retry returns the same run.
- `GET /v1/research-runs/{id}?request_id=` returns the groups and every finding;
  `POST /v1/research-runs/{id}/groups/{g}/close` `{request_id, reason}` records a failed group's angles as `NOT_RUN`.
- A session on a group's bundle has the research helpers (`research_conditional`, `research_persistence`,
  `research_group_comparison`, `research_quantiles`, `research_temporal_dependency`, `research_custom`): the
  declarative form (request and expressions, rebuilt by the backend) is `FORMULA_AND_STATISTICS_VERIFIED`, a frame
  built by code is `STATISTICS_VERIFIED`, `research_custom` is `EXECUTION_ONLY`. Each call stores the input
  (`research_input_<angle>`) and the call (`research_call_<angle>`); the `research_` names are reserved.
- Outcome (S15, 2026-09-29): a declarative forward return may read the price column of another request of the angle's
  contract (`{'forward_return': '<price column>', 'request': '<request id>'}`); the backend computes it per entity on
  that request's calendar and joins it on entity and date (`ENTITY_MISMATCH`, `REQUEST_OUTSIDE_CONTRACT` otherwise).
  A PERCENT or DECIMAL outcome whose values look like a price level (median magnitude above 100 or 1) is refused in
  the session and in the harness: the angle is `INVALID` with `OUTCOME_NOT_APPROVED`. Findings carry
  `outcome_source` (`FORWARD_RETURN`, `EXPRESSION` or `FRAME`); the research view's example call uses the contract's
  price column.
- `POST /v1/sessions/{id}/complete` `{request_id, finalize?}` validates the group: every approved angle recorded once,
  inside its contract, recomputed by `runtime/research_engines.py`, one `research_findings/v2` finding per angle
  (`final_status.research_findings_v2`, `calculation_validation` = the weakest level relied on). Missing angles keep
  the completion open (`next_action` RUN_PYTHON) unless `finalize` records them as `NOT_RUN`.
- Store schema version 4 adds `research_runs`, `research_groups` and `research_findings`.

### Imported modules (item C)

Every session execution records the top-level modules its code imports (`import x.y`, `from x.y import z` → `x`),
read from the code's syntax tree before it runs; relative imports and code that does not parse record none. The list
is stored on the execution record (`executions.modules`, store schema version 3) and logged with
`session_execution` (`modules`). The code text itself is not stored (only `code_sha256`). With
`PY_SANDBOX_MODULES_AUDIT_ENABLED=true` the completion's `final_status.modules_used` lists the modules of the
session's successful executions; without it the final status keeps its shape.

### Audit archival (IP2, off unless `PY_SANDBOX_AUDIT_STORE_ENABLED=true`)

The root harness archives to `market-audit-store` (`app/audit.py`). The analysis process never does.

**Per execution:**

- the exact source (`PYTHON_SOURCE`);
- a runtime/library manifest (`RUNTIME_MANIFEST`);
- the execution trace (`EXECUTION_TRACE`, and `ERROR_DETAIL` on failure);
- the execution record:
  - the runtime inventory from `importlib.metadata` (pip is removed from the image);
  - `declared_imports` from the AST;
  - `loaded_distributions` observed in `sys.modules` (the worker reports the names only while the flag is on);
  - `prebound_packages`, `stdlib_modules` and `unresolved_modules`;
  - seed, timezone, input checksums in order, and the contract hash;
- a link to each raw input Parquet by content. The Governor uploads those bytes.

**Per completion:**

- released outputs (`OUTPUT`);
- the execution manifest;
- the validation result;
- the approved DataNeed contract;
- the input bundle manifest;
- the released output checksums, as expectations of the run.

Delivery:

- **Durable outbox.** `<data dir>/audit_outbox.sqlite3`, plus a spool of the bytes in `<data dir>/audit-spool`
  (root only, mode 0700; `PY_SANDBOX_AUDIT_SPOOL_MAX_BYTES`). A file that does not fit is recorded as omitted and the
  item ends `INCOMPLETE`.
- **Drain.** A background thread drains due items idempotently. Statuses: `PENDING`, `FAILED_RETRYABLE` (backoff),
  `COMPLETE`, and `INCOMPLETE` after `PY_SANDBOX_AUDIT_MAX_ATTEMPTS`.
- **Failure handling.** An enqueue or archive failure is logged and never fails an execution or a completion.

Boundaries:

- The analysis processes keep their constructed environment: no `AUDIT_STORE_*` variable, no key, no upload URL, and
  no access to the spool (tested).
- `app/audit_client.py` is a small client of contract `audit-store/v1`, checked by `tests/test_audit_contract.py`.

**Paths:**
- `PY_SANDBOX_DATA_DIR` (`/data`, the Railway volume)
- `PY_SANDBOX_JOBS_DIR` (`/sandbox/jobs`)
- `PY_SANDBOX_CACHE_DIR` (`/sandbox/cache`)
- `PY_SANDBOX_DATASET_CACHE_BYTES` (1 GiB)
- `PY_SANDBOX_DATASET_URL_SCHEMES` (`https`; `file` is for tests only)

### Session release and the open queue (S28, round 2026-10-03)

- `POST /v1/requests/{request_id}/release`: the orchestrator calls it when the answer of a request ends. Each open
  session of the request that completed goes to `WARM_IDLE` (reusable by the conversation, evicted when a slot is
  needed); any other session closes with `RELEASED`. Idempotent.
- One active session per request: opening another session in the same request settles its completed sessions to
  `WARM_IDLE`; with no free slot, the request's own uncompleted session is closed (`REPLACED_IN_REQUEST`) before
  anything else of another request is touched (an ACTIVE or BUSY session of another request never is).
- `PY_SANDBOX_OPEN_WAIT_SECONDS` (default 0, maximum 120; dev 60): with every slot in use, an open waits in arrival
  order and retries the eviction; after the wait, `SESSION_CAPACITY_EXCEEDED` carries `waited_seconds`.
- `GET /v1/runtime` reports `session_release {enabled, version 1, open_wait_seconds}`. The 900 s idle sweep remains
  the safety net.

### Durable results (R-STORE, round 2026-10-03)

- `GET /v1/sessions/{id}/outputs/{output_id}/file?request_id=`: the stored file of a released output (headers
  `X-Saniti-Checksum-Sha256`, `X-Saniti-Format`), under the access rule of the output route; market-ai-orc copies it
  into its conversation store.
- A completion's `released_outputs[].lineage` carries `data_as_of` (the largest actual end date of the bundle's
  ranges) and `reference_date`.
- `POST /v1/sessions/{id}/carried?request_id=` (raw Parquet body; metadata as base64url JSON in
  `X-Saniti-Output-Meta`): a stored table of the same conversation uploaded back, checksum and Parquet verified, kept as
  a released output of the session under its original `output_id` with `restored`, its origin label, definition,
  units and `data_as_of`; `carried()` and `load_output` offer it as before. At most `PY_SANDBOX_RESTORE_MAX_BYTES`
  (256 MiB) per table.
- The open view lists every carried id (`carried_output_ids`); a DataNeed body may carry `as_of_date`, and a range
  ending `LATEST` then ends there when it is earlier than the reference date (the window records `as_of_date`).
- `GET /v1/runtime` reports `result_store {enabled, version 1, restore_max_bytes}`.

## Railway service

Deployed on `dev` as `market-python-sandbox`, with no public domain. The Railway volume is mounted
at `/data`, so it runs as a single replica. `RAILWAY_CHANGELOG.md` has the details.

- Since 2026-09-25 it deploys from GitHub `rednightt33/saniti` branch `main`, root
  `/apps/market-python-sandbox`, watch path `/apps/market-python-sandbox/**`. Earlier versions were
  local uploads.
- A push to `main` that changes this folder redeploys it, and so restarts the service. At startup,
  analyses that were still running are marked interrupted (`interrupted_analyses` in the
  `sandbox_started` log event).
- A change to the API contract shared with market-ai-orc must reach both services together.
- The existing SQLite records are migrated in place (new columns and tables only).

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
