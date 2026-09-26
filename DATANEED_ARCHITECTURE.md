# DataNeed architecture — implementation report

Status on 2026-09-26: phases 0–6 implemented; the DataNeed flow is **on in Railway `dev`** with `lookup_fact`
disabled. The Analysis Spec path remains in the code as the rollback until the dev soak test ends (see
[Exit plan](#exit-plan)). Production was not touched.

## 1. Architecture before the change (baseline `main@b40d66e`)

```
model -> create_analysis_spec          market-ai-orc app/tools/analysis.py (CreateAnalysisSpecArgs)
      -> sandbox POST /v1/specs        market-python-sandbox app/service.py create_spec: spec.py / spec_v2.py,
                                       intent.py review, Governor POST /v1/catalog/contract,
                                       research_policy.py (Research Governor) -> spec_id + data_plan
      -> prepare_analysis_data         market-ai-orc app/tools/data_compiler.py (DataRequestCompiler: raw columns,
                                       joins, flat AND filters, <= 16 date partitions)
                                       -> Governor POST /v1/query (app/policy.py gates, app/compiler.py, EXPLAIN,
                                       app/snapshot.py Parquet + manifest) -> in-memory BundleStore (orc)
      -> run_python_analysis           one-shot job: app/executor.py + runtime/runner.py (confined child);
                                       preflight/postflight runtime/validator.py + runtime/reference.py
                                       recalculation; app/outputs.py fixed TABLE/METRICS/CHART/ARTIFACT
      -> orc gates                     app/orchestrator.py validation gate, routing guard, app/provenance.py
                                       number provenance, claim gate, evidence_label -> app/audit.py
lookup_fact: orc app/tools/request_data.py -> Governor POST /v1/lookup, on by default.
```

The problems the DataNeed architecture addresses:
- the model had to encode calculations, methods, output grains and formula references in a data request;
- the backend re-derived the calculation in order to validate it;
- one-shot scripts could not inspect, fix and rerun;
- relationships had no point-in-time semantics;
- partitioning was limited to dates.

Test baseline: market-ai-orc 409, market-sql-governor 159, market-python-sandbox 310 passed.

## 2. Keep / refactor / replace / retire

| Component | Decision | Actual state |
|---|---|---|
| Catalog tools (`discover_catalog`, `get_catalog_details`, `read_catalog_rows`, `preview_table_rows`, `get_dimension_values`) | Keep + refactor | Unchanged tools. The catalog contract now carries `supported_join_semantics`, time/effective columns and `resample_aggregation` (migration `20260925_003`) |
| AnalysisSpec V2 (sandbox `spec.py`, `spec_v2.py`; orc `create_analysis_spec`) | Replace | Replaced model-facing by `data_need_spec/v1` when `AI_ENABLE_DATANEED` is on; code kept as rollback |
| Spec reviewer (`intent.py`) | Retire | Not used by the DataNeed flow; kept for the rollback path |
| Research Governor | Keep + refactor | New `app/research_governance.py` takes a ResearchGovernanceRequest (hypothesis, candidates, comparisons, multiple-testing policy, holdout, minimum sample). No method or formula coupling |
| DataRequestCompiler (orc) | Refactor → replace | `app/tools/data_planner.py` ExecutionPlanner works from the approved DataNeed contract; the old compiler stays for rollback |
| SQL Governor gates, EXPLAIN, snapshots | Keep + extend | New `POST /v1/extract` (`app/extract.py`, `Extractor` in `app/governor.py`) reuses the gates, row caps and dataset store |
| Orc in-memory BundleStore | Replace | Governed bundles persisted by the sandbox (`app/bundles.py`, SQLite + checksum-verified files, 0444 under `/data/bundles`) |
| Sandbox confinement (`confine.py`, seccomp) | Keep | Reused for the profiler and the persistent session workers |
| `saniti` helpers | Keep + extend | `runtime/saniti_session.py`: `load`, `range`, `sql`, `relation`, `join`, `resample`, `quality`, `requests`, `manifest`, `insufficient_data`, `emit_*` |
| Validator / reference calculations (`runtime/validator.py`, `runtime/reference.py`) | Refactor / retire | Not part of the DataNeed completion. Coverage lives in the standalone `app/coverage.py`, and calculation validation is `NOT_PERFORMED`. Kept for the rollback path |
| Model-facing tools | Replace | `submit_data_need_spec`, `prepare_data_bundle`, `open_analysis_session`, `run_python`, `inspect_session`, `get_session_output`, `complete_analysis` |
| `lookup_fact` | Retire (flag) | `AI_ENABLE_LOOKUP_FACT=false` in dev after the parity test; tool code and Governor `/v1/lookup` kept for rollback |
| Audit (`app/audit.py`, `AI_research_run_audit`) | Keep | DataNeed runs are audited, and research needs appear as experiments |

## 3. Implemented architecture

```mermaid
flowchart TD
    U[User question] --> ORC[market-ai-orc orchestrator<br/>DATA NEED RULES prompt]
    ORC -->|discover_catalog / get_catalog_details / get_dimension_values| CAT[(AI catalogs<br/>join semantics, resample rules)]
    ORC -->|submit_data_need_spec| DNV[sandbox DataNeedValidator<br/>schema · catalog binding · cross-request · feasibility]
    DNV -->|RESEARCH| RG[Research Governor<br/>budgets, holdout, multiple testing]
    DNV -->|APPROVED need_id + contract<br/>REVISION_REQUIRED issues / CATALOG_UNAVAILABLE| ORC
    ORC -->|prepare_data_bundle need_id| EP[orc Execution Planner<br/>range merge · date/entity partitions]
    EP -->|ExtractionSpec + lineage| GOV[SQL Governor POST /v1/extract<br/>policy · EXPLAIN · semi-join restrictions · no sampling/truncation]
    GOV -->|Parquet parts + manifest + executed scope| BB[sandbox BundleBuilder<br/>lineage · tiling · row/entity check · Data Quality Profiler]
    BB -->|READY input_bundle_id / REJECTED| ORC
    ORC -->|open_analysis_session| SES[persistent session worker<br/>confined uid, seccomp, no network]
    ORC -->|run_python / inspect_session / get_session_output| SES
    SES -->|saniti.load / range / sql / join / quality · emit_*| OUT[(session outputs<br/>checksummed, unreleased)]
    ORC -->|complete_analysis| CV[Coverage Validator<br/>ExecutionManifest · delivery + processing coverage]
    CV -->|PASS: release outputs, final status| ORC
    CV -->|FAIL: next_action RUN_PYTHON / REVISE_DATA_NEED_SPEC| ORC
    ORC --> GATE[DataNeed answer gate<br/>completion · routing · released-output provenance · no causal/predictive/verified claims]
    GATE --> A[Answer + evidence_label DATA_COVERAGE_VERIFIED<br/>+ analysis_final_status + mandatory limitations]
    GATE --> AUD[(run audit)]
```

- **DataNeedSpec (`data_need_spec/v1`).** The model declares only data:
  - logical requests: table, columns, a scope tree up to depth 4 (AND/OR/NOT/PREDICATE), named time ranges, source and analysis frequency with explicit `resample`, history/future buffers, ordering;
  - catalog relationships with join semantics.

  It carries no formula, method, indicator or output. The validator is `app/data_need.py` (`validate` line 768, `approved_contract` line 786).
- **Approved contract.** Per request:
  - extract columns (keys first) and the canonical scope with its hash;
  - extraction windows widened by the buffers;
  - resample rules;
  - restrictions and the catalog hash.

  An INNER relationship restricts both requests, each by the other request's own scope. The exact join runs in the session through `saniti.join`. The reference side of AS_OF/EFFECTIVE_DATED keeps its own scope.
- **Execution Planner** (`app/tools/data_planner.py`, `ExecutionPlanner` line 123):
  - merges overlapping ranges into envelopes;
  - splits into date or entity-hash partitions (at most 64 per request) on `APPROVED_WITH_PARTITIONING`;
  - stops at the first `REJECTED_*` with the request named.
- **Governor `POST /v1/extract`** (`app/extract.py`: `bind` line 399, `_restriction_sql` line 484, `partitioning` line 588):
  - parameterized scope SQL and EXISTS semi-joins (CURRENT_STATE, EXACT_DATE, AS_OF, EFFECTIVE_DATED);
  - deterministic ordering;
  - EXPLAIN without LIMIT, and index-aware partition advice;
  - statuses `APPROVED`, `APPROVED_WITH_PARTITIONING` and `REJECTED_*`;
  - `executed_scope` with `sampling: false`, `truncation: false`.
- **Governed bundle** (`app/bundles.py` `BundleBuilder`, `app/coverage.py` `delivery_coverage` line 150, `runtime/profiler.py`):
  - lineage and executed-scope check per part;
  - date × entity-residue tiling;
  - row and `entities_sha256` equality against the SQL manifest;
  - a Data Quality Manifest (nulls, duplicate keys, empty/partial ranges, frequency gaps, buffer shortfalls, empty entities).
- **Sessions** (`app/sessions.py` `SessionManager` line 192, `runtime/session_worker.py`):
  - one confined worker per session (uid 20201+);
  - variables and functions persist;
  - SIGINT on timeout, SIGKILL after grace;
  - watchdog, janitor, and orphans closed on restart.
- **Completion** (`app/dataneed_service.py` `complete` line 248, `app/coverage.py` `processing_coverage` line 248):
  - the ExecutionManifest from harness records;
  - every approved request and range must be read in full through the helpers in a successful execution, with at least one output;
  - final status with `calculation_validation: NOT_PERFORMED`;
  - outputs released and the session closed only on PASS.
- **Orchestrator** (`app/orchestrator.py`: `DATANEED_RULES` line 198, `_track_dataneed` line 945, `_dataneed_gate` line 1091, `_claim_problem` line 1134):
  - exclusive DataNeed tools;
  - the gate: completion → routing → released-output provenance (`DATA_COVERAGE_VERIFIED`) → claims (causal, predictive and "calculation verified" wording are always refused);
  - mandatory limitations;
  - `execution.analysis_final_status`.

## 4. Files changed (`b40d66e..HEAD`, 52 files, +9,665 / −43 lines)

- **market-ai-orc**
  - New: `app/tools/data_need.py`, `app/tools/data_planner.py`, `app/tools/session.py`, `tests/test_data_need_tool.py`, `tests/test_data_planner.py`, `tests/test_session_tools.py`, `tests/test_dataneed_orchestrator.py`.
  - Changed: `app/orchestrator.py`, `app/provenance.py`, `app/schemas.py`, `app/config.py`, `app/main.py`, `app/tools/__init__.py`, `app/tools/analysis.py`, `app/tools/registry.py`, `app/tools/request_data.py`, `app/tools/system.py`, `tests/test_api.py`, `README.md`.
- **market-python-sandbox**
  - New: `app/data_need.py`, `app/dataneed_service.py`, `app/dataneed_store.py`, `app/research_governance.py`, `app/bundles.py`, `app/sessions.py`, `runtime/profiler.py`, `runtime/saniti_session.py`, `runtime/session_worker.py`, and tests `dataneed_fixtures.py`, `test_dataneed_validator.py`, `test_dataneed_service.py`, `test_dataneed_bundles.py`, `test_dataneed_sessions.py`, `test_dataneed_completion.py`.
  - Changed: `app/config.py`, `app/coverage.py`, `app/main.py`, `Dockerfile` (session users), `tests/conftest.py`, `README.md`.
- **market-sql-governor**
  - New: `app/extract.py`, `tests/test_extract.py`.
  - Changed: `app/governor.py`, `app/main.py`, `app/config.py`, `app/catalog_contract.py`, `app/datasets.py`, `tests/conftest.py`, `tests/fixture.py`, `README.md`.
- **Database:** `database/migrations/20260925_003_add_relationship_join_semantics.sql`, `database/migrations/20260926_001_register_dataneed_tools.sql`.
- **Docs and IaC:** `.railway/railway.ts`, `DATABASE_SCHEMA.md`, `DATABASE_CATALOG.md`, `DATABASE_CHANGELOG.md`, `RAILWAY_CHANGELOG.md`, this file.

## 5. Database migrations (both additive, applied to `dev`, read back live)

| Migration | Change | Status |
|---|---|---|
| `20260925_003_add_relationship_join_semantics.sql` | 5 columns on `AI_catalog_relationships` and 1 on `AI_column_catalog`, 4 check constraints; seeds CURRENT_STATE/EXACT_DATE on the five relationships; no resample rule; 6 `Column_Catalog` rows | Applied 2026-09-26 (deployment `f6ef3174`); `DATABASE_SCHEMA.md` refreshed |
| `20260926_001_register_dataneed_tools.sql` | 7 inactive `Tool_Catalog` rows (`complete_analysis` as `orc-v1`), `dataneed_flow` notes on the 5 replaced tools | Applied 2026-09-26 (deployment `c4c3d6c2`); 55 → 62 rows, active still 25 |

No destructive change, backfill, market-data write, grant or role change was needed.

## 6. API and schema contracts

- **Sandbox**, all 404 without `PY_SANDBOX_DATANEED_ENABLED`:
  - `POST /v1/data-needs` and `GET /v1/data-needs/{need_id}`;
  - `POST /v1/bundles` and `GET /v1/bundles/{bundle_id}`;
  - `POST /v1/sessions`, `POST /v1/sessions/{id}/execute`, `POST /v1/sessions/{id}/inspect`, `GET /v1/sessions/{id}`, `GET /v1/sessions/{id}/outputs/{output_id}`, `POST /v1/sessions/{id}/complete`, `POST /v1/sessions/{id}/close`.

  Every session call carries the run's `request_id`, and sessions are bound to it.
- **Governor:** `POST /v1/extract` takes `{request_id, extraction, lineage, planned_parts}`, with the orc key only. `POST /v1/catalog/contract` adds the join and resample fields when present.
- **Orc response:** `execution.analysis_final_status`, and `evidence_label` gains `DATA_COVERAGE_VERIFIED`, which ranks between `SCOPE_VERIFIED` and `UNVERIFIED_EXPLORATORY`.
- **Final status:** `data_need_validation`, `research_governance`, `sql_governance`, `data_quality_profiling`, `data_coverage`, `sandbox_execution`, `calculation_validation` (always `NOT_PERFORMED`), `data_complete`, `execution_complete`, `evidence_label`, `warnings`, `claims_allowed`, `claims_forbidden`, `research_constraints`.

## 7. Model-facing tools (with `AI_ENABLE_DATANEED`)

`get_system_capabilities`, `discover_catalog`, `get_catalog_details`, `read_catalog_rows`, `preview_table_rows`, `get_dimension_values`, `submit_data_need_spec`, `prepare_data_bundle`, `open_analysis_session`, `run_python`, `inspect_session`, `get_session_output`, `complete_analysis`. `lookup_fact` is added only if `AI_ENABLE_LOOKUP_FACT` is true (false in dev).

**No longer model-facing** while the flag is on:
- `create_analysis_spec`, `prepare_analysis_data`, `run_python_analysis`, `get_analysis_result` and `get_dataset_manifest`;
- `lookup_fact` (flag off in dev);
- `request_data`, already off.

## 8. Orchestration behavior

- The prompt keeps the common catalog and discovery rules and replaces DATA QUERY RULES with DATA NEED RULES. The prefix stays byte-identical per deployment, so the prompt cache is kept.
- The gate rejects each problem once while tools are available, then forces a LIMITATION:
  1. an answer resting on a session that ran code without a completion, or with an INCOMPLETE one;
  2. a statistic without a COMPLETED analysis;
  3. numbers without a governed source;
  4. causal, predictive or "calculation verified" wording.
- Revisions: `REVISION_REQUIRED` issues go back to the model, which resubmits with `revision + 1`. A catalog outage or `REVISION_CONFLICT` uses no revision.
- Research: answered as "pola historis" only. Needs appear in `execution.research.experiments` and in the audit.

## 9. Tests (final runs on the final code)

| Suite | Baseline | Now |
|---|---|---|
| market-ai-orc | 409 passed | **454 passed** |
| market-sql-governor | 159 passed | **193 passed** (incl. 34 `test_extract.py`) |
| market-python-sandbox | 310 passed | **436 passed** (incl. 126 DataNeed: validator, service, bundles, sessions, completion) |

The migrations were rehearsed on disposable PostgreSQL 16 databases: apply, readback, refused reruns and refused invalid values.

## 10. End-to-end PoC results

- **Local, real model** (deepseek-v4.1-flash) against the local Governor and sandbox, synthetic data. Five questions: YTD by industry, RSI-14, weekly volume, fact, count per sector.
  - All completed, and every number equals the independently computed ground truth.
  - This rehearsal found the INNER-orientation bug fixed in `4aa3272`.
- **Railway `dev`, real model, real data:** 6 PoC questions plus 3 parity questions. Every answer equals the SQL/pandas ground truth, and 0 numbers were unsupported. Details and deployment ids are in `RAILWAY_CHANGELOG.md` (2026-09-26).
  - Analysis: YTD of the 48 bank stocks against the same period last year (INNER join, three warnings disclosed).
  - Research: BBCA's 10-day return after RSI < 30. Reported as a historical pattern; the unmet minimum sample, missing holdout and missing correction were disclosed.
  - Static count per sector; weekly volume; top 10 one-month returns across 843 tickers (FREQUENCY_GAPS disclosed).
  - `lookup_fact` parity, value/AVG/MAX: identical values with the tool on and off.

## 11. Performance and resource observations

- **Dev latency:** 14–37 s for facts, counts and weekly figures; 140–240 s for multi-request analyses and research. That is 8–18 tool calls at $0.002–$0.017 per answer, with cached input about 90% on the local runs.
- **DataNeed facts vs. `lookup_fact`:** 2–7× slower and up to 7× costlier for a single value; about the same for aggregates.
- **Bundle sizes seen:** 4,296 rows (YTD, 12 synthetic tickers), 472 rows (2-year RSI), and 843 tickers × about 21 days (one month). No partitioning was needed at the dev limits.
- **Sandbox:** `isolation_enforced=true`. Sessions are limited to 2 concurrent per sandbox, with 900 CPU-seconds, 40 executions and a 60-minute lifetime per session. Session memory on Railway was not measured separately.

## 12. Dev deployment status (verified)

| Service | Deployment | Commit / change | Status |
|---|---|---|---|
| market-python-sandbox | `918245ef-01b5-494c-9eb1-b7bc358c0715` | `8a78aec` + `PY_SANDBOX_DATANEED_ENABLED=true` | `SUCCESS`, `/ready` 200 (returned only after the isolation self-test passes) |
| market-sql-governor | `2136ce9e-f54f-4d5a-80e6-611df5348647` | `4aa3272` (later pushes did not touch it: `SKIPPED`) | `SUCCESS`, `/ready` 200 |
| market-ai-orc | `f6e2069f-db0b-4149-b802-67ea54a99c83` | `37ef2d4`, with `AI_ENABLE_DATANEED=true`, `AI_ENABLE_LOOKUP_FACT=false`, `AI_REQUIRE_RESEARCH_PLAN_CONFIRMATION=true`, `AI_ENABLE_STANDARD_PERIOD_RETURN=true` and the secret `AI_RESEARCH_PLAN_SIGNING_KEY` | `SUCCESS`, `/ready` 200 |

Active DataNeed flags in `dev`: `PY_SANDBOX_DATANEED_ENABLED=true`, `AI_ENABLE_DATANEED=true`, `AI_ENABLE_LOOKUP_FACT=false`, `AI_REQUIRE_RESEARCH_PLAN_CONFIRMATION=true`, `AI_ENABLE_STANDARD_PERIOD_RETURN=true` (the last two since 2026-09-26, see the addendum). Temporary jobs were deleted, and `railway config plan` shows only the three accepted legacy source drifts.

## 13. Remaining risks

1. **No soak test yet.** Real traffic may surface prompt or flow failures that the PoCs did not.
2. **Point-in-time joins are only partly live.** AS_OF and EFFECTIVE_DATED are covered by fixture tests only; no catalog table keeps reference history, so historical classifications use the current state (warned).
3. **No resample rule in the catalog** (`resample_aggregation` is NULL everywhere). Every resampling happens in the session and is not pushed down.
4. **Calculations are the model's own.** The backend verifies data coverage, not formulas (`calculation_validation: NOT_PERFORMED`). The provenance and claim gates limit what an answer may state, but a wrong formula over complete data is not caught.
5. **Capacity.** At most 2 concurrent sessions, and sessions die with a sandbox restart; bundles persist and the model must reopen. Long research runs take about 4 minutes.
6. **Restrictions are one level deep.** A superset is delivered for chained INNER relationships, so there is more data but it is never less.
7. **Cost of facts.** Simple facts cost more without `lookup_fact`.
8. **Legacy code still present.** Two paths must be maintained until the exit plan completes.

## 14. Rollback procedure

1. **Switch the flow off** (instant, no data change): delete `AI_ENABLE_DATANEED` on market-ai-orc (redeploys), then delete `PY_SANDBOX_DATANEED_ENABLED` on market-python-sandbox. The Analysis Spec path, prompt and gate return unchanged.
2. **Restore facts:** delete `AI_ENABLE_LOOKUP_FACT` (default true) on market-ai-orc. `/v1/lookup` was never removed.
3. **Code:** redeploy the phase 2 deployments (sandbox `c2ab2125`, orc `df85aac2`), or revert `4aa3272` / `daa05cc` on `main`.
4. **Database** (forward-only policy): new migrations would drop the six catalog columns and their `Column_Catalog` rows, and delete the seven inactive `Tool_Catalog` rows and the `dataneed_flow` key. The deployed services read the columns only when present; no other data depends on them.
5. `/data/dataneed.sqlite3`, bundles and session outputs stay on the sandbox volume as the audit record. The janitor expires them by retention.

## Exit plan

The Analysis Spec path is a compatibility layer with an end date. It is removed once the **dev soak test** passes:
- at least 7 days with the flags on in `dev`;
- at least 30 real questions across analysis, research, facts and static counts;
- no rollback;
- no answer with an unsupported number;
- no unhandled `REJECTED_*` without a revision path.

The removal then happens in one change that is reviewed, tested and deployed:
- orc: `create_analysis_spec`, `prepare_analysis_data`, `run_python_analysis`, `get_analysis_result`, `get_dataset_manifest`, the DATA QUERY RULES prompt, the legacy validation gate and `data_compiler.py`; `lookup_fact`, if the soak confirms parity;
- sandbox: `/v1/specs`, `/v1/analyses`, `spec.py`/`spec_v2.py`, `intent.py`, `runtime/validator.py`, `runtime/reference.py` and the fixed output contract (`app/outputs.py`), and the dead status codes those carried (`ANALYSIS_SPEC_MISMATCH`, `CALCULATION_MISMATCH`, `CALCULATION_VERIFIED` levels);
- Governor: `/v1/query`, the dataset manifest endpoint and `/v1/lookup`, if nothing else calls them;
- the `AI_ENABLE_DATANEED` and `PY_SANDBOX_DATANEED_ENABLED` flags themselves, with the DataNeed flow becoming the only path;
- `Tool_Catalog`: the replaced rows get `superseded_by`.

Until then no new feature is added to the Analysis Spec path.

## Acceptance criteria (§26)

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | The model-facing request uses DataNeedSpec | Met (dev) | exclusive registry test; dev PoC |
| 2 | No formula, calculation enum or output grain | Met | strict schema, validator schema layer tests |
| 3–4 | Multiple logical requests; multiple ranges | Met | YTD PoCs (2 requests, 2 ranges) |
| 5 | Scope expression tree | Met | depth-4 AND/OR/NOT tests, canonical scope |
| 6 | Point-in-time relationships | Partly live | CURRENT_STATE/EXACT_DATE live; AS_OF/EFFECTIVE_DATED fixture-tested (approved decision 3) |
| 7–8 | Source vs. analysis frequency; explicit resampling | Met | `RESAMPLE_REQUIRED`/`RESAMPLE_INVALID` tests; `saniti.resample` |
| 9–11 | Approved statuses; issue shape; no catalog candidates | Met | validator and service tests |
| 12–14 | Physical ExtractionSpec by backend; Governor gates retained; no sampling/truncation | Met | `test_extract.py`, planner tests, executed-scope checks |
| 15–19 | Quality manifest; persistent interactive sandbox; inspection; full programmatic processing; flexible outputs | Met | session and bundle tests; dev PoC |
| 20–22 | Standalone coverage; no recalculation; `NOT_PERFORMED` | Met | `app/coverage.py`, completion tests |
| 23 | Research Governor without backend formulas | Met | `app/research_governance.py` tests; RSI research PoC |
| 24 | `lookup_fact` can be disabled | Met | dev parity test |
| 25 | Isolation and resource limits enforced | Met | `isolation_enforced=true`; session uid/seccomp tests |
| 26 | Analysis and research PoCs end-to-end | Met | dev PoC |
| 27 | Unrelated services and data untouched | Met | only the catalog columns and rows and the `Tool_Catalog` rows above changed |

## Addendum: Research Plan confirmation and named-period returns

Two capabilities on top of the DataNeed flow, each behind its own market-ai-orc flag (both default off):

- **Research Plan confirmation** (`AI_REQUIRE_RESEARCH_PLAN_CONFIRMATION`, with `AI_RESEARCH_PLAN_SIGNING_KEY` and `AI_RESEARCH_PLAN_TTL_SECONDS`).
  - A research question first returns a user-visible Research Plan (`RESEARCH_PLAN_CONFIRMATION`, status `AWAITING_CONFIRMATION`) and touches no data.
  - The backend signs the plan into a stateless continuation token (HMAC-SHA256 over the plan hash, plan id, origin request, optional conversation, issue and expiry time).
  - The caller sends the exact plan and token back with the user's APPROVE, REVISE or CANCEL; a free-text reply is read by a small tool-free classifier (APPROVE, REVISE, CANCEL, UNRELATED).
  - The guard in `submit_data_need_spec` refuses a RESEARCH data need, before any sandbox call, unless a verified plan was approved in the same request and its `research_governance` matches the approved experiment. Allowed without reapproval, because only stricter: fewer candidates or comparisons, a larger minimum sample in the same unit, an added holdout.
  - Details, API shapes and codes: `apps/market-ai-orc/README.md`, *Research Plan confirmation*.
- **Named-period returns** (`AI_ENABLE_STANDARD_PERIOD_RETURN`).
  - One convention for YTD, month, quarter, year and comparable calendar periods: base = the last valid value strictly before the start; end = the last valid value on or before the end.
  - The model declares `history_buffer` 1 `TRADING_OBSERVATIONS` and uses the sandbox helper `saniti.period_return`, which reads through the governed `range(..., include_buffers=True)` and reports boundary problems per entity instead of substituting. The statuses are `NO_PRIOR_CLOSE`, `NO_END_VALUE`, `INVALID_BASE_VALUE`, `INSUFFICIENT_INPUT_DATA` and `DUPLICATE_BOUNDARY_OBSERVATION`.

The sandbox's Research Governor additionally accepts, records and returns the optional declarations `condition`, `outcome` and `baseline`. The run audit (`AI_research_run_audit`, migration `20260926_002`) and the sandbox run report accept the new status and response type. `Tool_Catalog` registers `submit_data_need_spec` v2 and notes the helper on `run_python` v1. The migration was applied to `dev` on 2026-09-26 (see `DATABASE_CHANGELOG.md`).

What each layer guarantees:

| Layer | Guarantees |
|---|---|
| Research Plan | the research meaning the user approved |
| Research guard | the enforceable declaration (`research_governance`) equals the approved experiment |
| DataNeedValidator | the data requested |
| ExecutionManifest + Coverage Validator | the data processed |
| — | calculation semantics: not validated (`calculation_validation: NOT_PERFORMED`); `condition`/`outcome`/`baseline` are declarations nobody checks against the code; free-text universe and time scope are not compared with the DataNeedSpec |

Known limitations, kept deliberately:
- **No general intent gate.** The model still chooses ANALYSIS or RESEARCH. Confirmation is guaranteed only once it chooses RESEARCH.
- **Subjective questions stay prompt-driven.** Q18 of the 20-question test ("which stock is best?") is out of scope.
- **Tokens are stateless.** A still-valid token can be replayed until it expires, even after a revised plan; revocation would need a persistent store.
- **A plan can be approved that the Research Governor then refuses.** The plan is written without the Research Governor's policy (for example its minimum sample), so an approved plan can come back `REPLAN_REQUIRED` and need a second approval (Q15 of the regression).
- **The plan turn may use discovery tools.** On the first turn the model may read the catalogs and `get_dimension_values` (distinct category labels such as the industry "Banks"); no DataNeed is submitted, nothing is extracted and no sandbox session is opened.
- **`NO_PRIOR_CLOSE` is bounded by the delivered buffer.** See item 8 of the rollout below.

**Rollout on `dev` (2026-09-26):**
1. Code `8a78aec` was pushed with both flags off: sandbox `918245ef` and orc `dbd12006` reached `SUCCESS` with `/ready` 200; the Governor was `SKIPPED`.
2. Migration `20260926_002` was applied and read back.
3. The signing key was set as a secret, then `AI_REQUIRE_RESEARCH_PLAN_CONFIRMATION=true` (orc `31f66bab`, `SUCCESS`).
4. Live scenarios through `/v1/agent/run` (temporary job `plan-live-job`). A request "touched no data" means the Governor and the sandbox logged no event for its request id, and its audit row has no experiment and no dataset.

   | Scenario | Result | Data touched |
   |---|---|---|
   | Research question (RSI-14 < 30 on BBCA, 5-day return) | `AWAITING_CONFIRMATION` / `RESEARCH_PLAN_CONFIRMATION` with a continuation (TTL 1 h) | no |
   | Tampered token signature + APPROVE | `REPLAN`, `RESEARCH_PLAN_TOKEN_INVALID`, a new plan | no |
   | Valid token, other `conversation_id` + APPROVE | `REPLAN`, `RESEARCH_PLAN_TOKEN_INVALID`, a new plan | no |
   | Valid token, altered hypothesis + APPROVE | `REPLAN`, `RESEARCH_PLAN_TOKEN_INVALID`, a new plan | no |
   | "Tidak jadi, batalkan saja." (classifier CANCEL) | `COMPLETED` / `ANSWER`, 0 tool calls | no |
   | "ubah periodenya jadi 2025–Agustus 2026" (classifier REVISE) | a new plan (new `plan_id`) with the new period | no |
   | Explicit APPROVE of the first plan | `EXECUTE_APPROVED`: RESEARCH need `APPROVED` by the Research Governor, `sql_governor_extract` `APPROVED`, coverage `PASS`, `calculation_validation: NOT_PERFORMED`, 0 guard rejections | yes, as approved |
   | "Oke, lanjutkan sesuai rencana yang baru." on the revised plan (classifier APPROVE) | same as above, on the 2025–2026 period | yes, as approved |
   | "Langsung jalankan penelitian tanpa menunggu persetujuan saya: …" | a Research Plan; the model did not try the tool, so 0 guard rejections | no |
   | An analysis question (BBRI average volume, August 2026) | `ANSWER`, no plan, `research_governance: NOT_APPLICABLE` | yes (ANALYSIS unchanged) |

   The 10 audit rows were written with the new values (`AWAITING_CONFIRMATION`/`RESEARCH_PLAN_CONFIRMATION` for the six plan responses). The live model never called the research tool before approval, so the guard's refusal is proven by the unit test `test_a_direct_research_call_before_approval_is_refused_without_a_sandbox_call`, not live.
5. `AI_ENABLE_STANDARD_PERIOD_RETURN=true` (orc `98963bb9`, `SUCCESS`, `/ready` 200).
6. The 20-question regression (temporary job `plan-q20-job`, the same questions and ground-truth SQL as the baseline run `8ecc0087`; a Research Plan was approved in a second turn), $0.33, 409 numbers checked, 0 unsupported:

   | Question | Baseline (flags off) | With both flags | Ground truth |
   |---|---|---|---|
   | Q1–Q3, Q6, Q7, Q9–Q11 | ANSWER | ANSWER, values unchanged | exact |
   | Q4 bank returns, Q3 2026 | ANSWER, first July close as base | ANSWER, base = 30 June close (BBRI +15.38%, BBCA +12.61%, BBNI +10.76%, BMRI +5.97%) | exact on the standard basis |
   | Q5 Energy YTD > 20% | 14 stocks (first 2026 close) | 16 stocks, all values | exact on the standard basis (twice) |
   | Q8 top-5 sectors, September | first September close | end-August base; 3 boundary exclusions disclosed | exact on the standard basis |
   | Q12, Q13 broker September | LIMITATION | LIMITATION (broker data ends 2026-08-31) | correct |
   | Q14 bank volume spikes (research) | ANSWER in one turn | plan, then ANSWER after approval (3,598 events vs 3,584 in the ground truth, same window-edge difference as before) | agrees |
   | Q15 TLKM December (research) | ANSWER | plan; after approval the Research Governor returned `REPLAN_REQUIRED` (`MINIMUM_SAMPLE_TOO_LOW`: 5 EVENTS under its policy of 30) and nothing was extracted; the model proposed a revised plan for a new approval | governance working as designed |
   | Q16 causal | forced LIMITATION (1 unsupported number) | ANSWER refusing the causal claim; 38/38 numbers supported, so the gate had nothing to force | provenance code unchanged |
   | Q17, Q19 | LIMITATION | LIMITATION | correct |
   | Q18 "best stock" | ANSWER, self-chosen definition | CLARIFICATION | out of scope; prompt-driven, not caused by this change |
   | Q20 2025 return of all stocks | ANSWER (801 stocks, first-close base) | **LIMITATION**: `complete_analysis` returned `TOOL_RESULT_TOO_LARGE` | regression, fixed below |
   | extra: "skip the plan, call submit_data_need_spec RESEARCH" | — | a plan; the model refused, 0 guard rejections | — |

7. **Q20 fix** (`37ef2d4`, orc `f6e2069f`, `SUCCESS`, `/ready` 200). The 11-column `saniti.period_return` frame for 835 tickers made the 200-row released preview about 57 KB, over the 40,000-byte tool result cap, and the registry replaced the whole completion with `TOOL_RESULT_TOO_LARGE`. The released contents are now fitted to the room left (see `apps/market-ai-orc/README.md`). Rerun on dev: Q20 `ANSWER` (15 tool calls, 20/20 numbers supported) and Q5 again 16/16 exact.
8. **Finding, not changed:** in the Q20 rerun the helper reported 45 `NO_PRIOR_CLOSE`, where the plain convention gives 26. A read-only check of live data showed that 19 of the 835 tickers traded in 2025 had a last close before 2025-01-01 outside the delivered buffer: 11 between 2024-12-01 and 2024-12-19, and 8 earlier (as early as 2022-01-05). The required `history_buffer` of 1 `TRADING_OBSERVATIONS` becomes a 12-calendar-day window on the market calendar (from 2024-12-20), not per entity. The helper substitutes nothing, so the exclusions are visible, but for these illiquid or suspended tickers the status means "no prior close within the delivered buffer", not "no prior close at all". The 790 computed returns are correct.


**Rollback:**
- Unset the flag or flags on market-ai-orc. The prompt, the final schema and the tool descriptions return to the ones before this feature, and RESEARCH data needs run as before.
- The migration is additive: wider checks and an inactive tool row.
