# Railway changelog

## 2026-09-23 — Deploy market-ai-orc context budget and 16 KB catalog pages (c1b4e93)

- **Deployment:**
  - What changed:
    - Soft context limit `AI_CONTEXT_SOFT_LIMIT_RATIO` (default `0.8`): tools are withdrawn and the run finalizes with `LIMITATION` instead of failing.
    - New execution field `execution.tools_withdrawn_reason`.
    - Code default of `CATALOG_PAGE_MAX_BYTES` changed from 32000 to 16000.
  - No Railway variable was added or changed, so both new defaults apply.
  - Upload method: the same watch-path-compatible staging upload as before.
  - Deployment `4d2a7665-696f-4f5f-b9fc-8df6a35db7b0` reached `SUCCESS`, with a clean Uvicorn start and `GET /ready` returning `200`.
  - Rollback reference: `2d6c60ca-4b44-4473-a2de-8e6482075d92`.
- **Temporary one-off service `orc-db-update`** (`b7efbd14-a030-4540-8880-f39485cea5a9`):
  - It had only reference variables (`${{Postgres.DATABASE_URL}}` and `${{market-ai-orc.MARKET_AI_ORC_API_KEY}}`) and restart policy `NEVER`, and ran as deployment `fc6e2821-4fe4-480d-b426-51945a29468d`.
  - It applied migration 004 and ran two live smoke tests. It was deleted afterwards.
  - `railway config plan` reported `dev` up to date.
- **Smoke test 1: regression** (broker accumulation question).
  - Result: `COMPLETED`/`ANSWER` in 48 s, 5 model calls, 9 tool calls, `tools_withdrawn_reason = null`.
  - Behavior is unchanged from the Phase 2+3 run.
- **Smoke test 2: stress** ("read the complete `AI_calculation_catalog`, every page").
  - Result: `FAILED` with `MAX_ITERATIONS` after 8 model calls, each reading one page.
  - Provider-reported input per call grew about 5k tokens per 16 KB page, from 2.0k to 37.3k. That is below the 51.2k soft limit, so `AI_MAX_TOOL_ITERATIONS = 8` ended the run before the context budget applied.
  - This is not a regression. With 32 KB pages the same request would have hit `CONTEXT_LIMIT` after about four pages. But the iteration cap still fails hard instead of degrading. This is recorded as an open follow-up, not changed in this deployment.

## 2026-09-23 — Deploy market-ai-orc Phase 2+3 (catalog discovery, full catalog access, 20-row preview)

- **Variables on `market-ai-orc`**, both set with `--skip-deploys`:
  - `MARKET_AI_ORC_DB_PASSWORD`: a new random 48-character secret, set through stdin and never printed.
  - `CATALOG_DATABASE_URL`: a reference template, `postgresql://market_ai_orc:${{MARKET_AI_ORC_DB_PASSWORD}}@${{Postgres.RAILWAY_PRIVATE_DOMAIN}}:5432/${{Postgres.PGDATABASE}}`. It resolves to the private host `postgres.railway.internal`.
  - No other variable changed.
- **Deployment:**
  - Deployed commit `456081d` (Phase 2+3 only; the later context-budget change is not deployed).
  - Upload `98ec3d4f-8009-43d3-8fd7-8827f54c0ffd` was `SKIPPED` ("No changes to watched files"): the service watch path `/apps/market-ai-orc/**` also applies to CLI uploads, and a `--path-as-root` upload of `apps/market-ai-orc` places files at `app/...`.
  - The code was then uploaded with its repository layout under `apps/market-ai-orc/`, plus a root wrapper Dockerfile that builds the same image as `apps/market-ai-orc/Dockerfile`.
  - Deployment `2d6c60ca-4b44-4473-a2de-8e6482075d92` reached `SUCCESS`. Uvicorn started cleanly and `GET /ready` returned `200`.
- **Temporary one-off service `orc-db-setup`** (`a916cd58-4b22-4e45-bbd9-d57e330b57b1`):
  - Created with only reference variables (`${{Postgres.DATABASE_URL}}` and three `${{market-ai-orc.*}}` references) and restart policy `NEVER`. It ran once as deployment `11b4d8ad-c908-49eb-a9f9-174a3248ce04`.
  - It applied the three database migrations, provisioned `market_ai_orc`, and ran the live verification, privilege checks, and `EXPLAIN` evidence (see `DATABASE_CHANGELOG.md`).
  - It then smoke-tested the deployed service over the private network and finished with `SETUP COMPLETE`.
  - It was deleted afterwards; the service list confirms it is gone.
- **Live smoke test** ("Explain which tables and calculations are available for analyzing broker accumulation, and show me example records."):
  - Result: `COMPLETED`/`ANSWER` in 24 s, 5 model calls, and 9 real tool calls (`get_system_capabilities`, `discover_catalog`, 3 × `get_catalog_details`, 4 × `preview_table_rows`).
  - Tokens: 63.8k in total, with a peak single-call input of about 22k.
  - The limitations correctly stated that no SQL or Python analysis ran, that the previews are example rows, and that Feature 02/03 are `UNVERIFIED`/`MANUAL_REFRESH_REQUIRED`.
- Ran `railway config pull --force`. `.railway/railway.ts` now preserves `CATALOG_DATABASE_URL` and `MARKET_AI_ORC_DB_PASSWORD`, and the follow-up `railway config plan` reported `dev` up to date. No other service, domain, schedule, or source was changed.
- **Rollback:** redeploy `60f622a5-eed1-4077-8b5b-cb0c0c2faf57` (Phase 1). The catalog tools are registered only when `CATALOG_DATABASE_URL` is set.

## 2026-09-23 — Deploy market-ai-orc Phase 1 orchestrator

- Created only `market-ai-orc` (service ID `41dc17ee-3bac-41ef-90ec-8b9356815c71`) in Railway `dev`. The user-approved pinned IaC plan (`sha256:f1547b72…`) was exactly one safe create, zero changes, zero destroys.
- Configuration: region `sfo`, one replica, Dockerfile build, start command `uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8080`, health check `/ready` (120 s), restart `ALWAYS`. It is private: no public domain. Other services reach it at `market-ai-orc.railway.internal:8080`.
- There is no GitHub source yet; the code was uploaded from `apps/market-ai-orc` at commit `1a857f9`. Connect GitHub `main` at root `/apps/market-ai-orc` with watch path `/apps/market-ai-orc/**` in a separate approved change.
- Variables: `PORT`, `AI_MODEL=deepseek/deepseek-v4.1-flash`, and `AI_REASONING_EFFORT=high` are literals. `OPENROUTER_API_KEY` is a Railway reference to `${{market-ai-backend.OPENROUTER_DEEPSEEK}}`, so the existing OpenRouter key is reused without copying it; a hash comparison confirmed the resolved value matches. `MARKET_AI_ORC_API_KEY` is a new random 64-character bearer secret, set through stdin. No secret value was printed or committed.
- Deployment `60f622a5-eed1-4077-8b5b-cb0c0c2faf57` reached `SUCCESS`. The logs show a clean Uvicorn start, and Railway's `GET /ready` health check returned `200`.
- Before deployment, the same code passed three local live acceptance runs against OpenRouter with the existing key. Each run was `COMPLETED`/`ANSWER` with one real `get_system_capabilities` call, reported database, Python, and web search as unavailable, and used about 2.9–3.0k tokens.
- Two OpenRouter incompatibilities were found live and fixed in code (details in `apps/market-ai-orc/README.md`):
  - No DeepSeek V4.1 Flash endpoint supports `parallel_tool_calls`, which caused a 404 under `require_parameters`.
  - A strict `text.format` sent in the same turn as tools prevented any tool call.
- Pulled the live Railway configuration into `.railway/railway.ts`; the follow-up plan reported `dev` already up to date. No existing service, variable, database, domain, schedule, or data was changed.

## 2026-09-23 — Deploy AI data coverage cron

- Created only `ai-data-coverage` (service ID `d2e57c12-cebf-4434-a66a-ba2d6d2f176d`) in Railway `dev`; the reviewed IaC plan was exactly one add, zero changes, and zero destroys.
- Connected GitHub `rednightt33/saniti` branch `main` at root `/apps/ai-data-coverage`, Dockerfile build, start command `python coverage_job.py --mode nightly`, `NEVER` restart policy, and schedule `30 0 * * *` UTC (07:30 Asia/Jakarta). `DATABASE_URL` is present as the existing Postgres service reference; no credential value was printed or committed.
- Initial deployment `31aab1e5-4baa-43b8-b770-1b8183d717b2` built commit `7d8f29513e5f2f07a365ab6829f6e33a68ca7f30` and reached `SUCCESS`.
- A manual local full run and nightly-mode run both succeeded against Railway PostgreSQL before deployment. The job writes only `AI_data_coverage` and does not scan or modify Feature 01–03.
- Pulled the live Railway configuration into `.railway/railway.ts`; the follow-up plan reported the `dev` environment already up to date. No existing service, schedule, endpoint, volume, secret value, raw row, or Feature row was changed.

## 2026-09-14 — Three-path Market AI execution architecture

- Added service `market-query-sandbox` (`c6bf3085-4784-43f3-90a1-da74456f6c4d`) for isolated custom joins, windows, and descriptive transformations.
- Re-scoped `market-analytics-worker` (`75fc5bbc-2ff9-4850-b007-011735506ce6`) as the statistical validation worker.
- Configured distinct sealed worker credentials and separate query-sandbox/statistical row, byte, estimated-scan, ticker, date-range, runtime, memory, and output limits on `market-ai-backend`.
- Neither worker receives `DATABASE_URL` or private bucket credentials; each can claim only its own `Analytics_Job.execution_class` through a separate backend endpoint.
- Backend deployment `e69b3c4f-5c9d-47b9-a8d0-a9c04c9b763d` reached `SUCCESS` after correcting the local monorepo upload scope. Initial worker local-upload builds failed because Railway treated the repository root as a Node application; no running worker was replaced by those failed builds.
- Final worker deployment IDs and end-to-end acceptance results are recorded below after the configuration-managed GitHub deployments complete.

This file records intentional changes to the Railway project. Git history preserves every revision. Never include secret values.

## 2026-09-14 — Provision private generic analytics handoff

- Created private Railway bucket `market-analytics-input` in `sin` and service `market-analytics-worker`. Bucket credentials are configured only on `market-ai-backend`; the worker receives only a separate internal worker token and the backend private URL.
- Added independent, configurable analytics limits without changing interactive query or LLM token limits: 50,000 rows, 30 columns, four datasets, 20 MiB input, 2,000,000 estimated rows, 120 seconds, 2 GiB, 500 result rows, 256 KiB result, 24-hour maximum snapshot retention, one-hour terminal grace, and 90-day compact-result retention.
- Added `AI_MAX_DISCOVERY_CALLS=4` plus a compact per-request analytics handoff. It tells the model when to use ordinary queries versus the generic worker, how to prefilter/select columns, how QC and anomalies behave, how idempotent job labels work, and when to stop. Repeated exact catalog discovery uses the session cache and `list_tools` no longer dumps inactive/deferred capabilities.
- Local integration used the real Railway PostgreSQL and private bucket with a local copy of both services. The known workstation CA issue required explicit `AWS_CA_BUNDLE` for Boto3; TLS verification remained enabled. Final worker Golden Test passed and verified the no-database-credentials boundary.

## 2026-09-14 — Harden analyst finalization and complete compaction A/B

- Deployed the priority 1–6 hardening sequence through commits `e9fda44`, `37d7be8`, `c744c6f`, `9a84c82`, and `88a5514`. The backend now reserves finalization budget, requires tool use before evidence, locks data tools after sufficient evidence, requires `complete_analysis`, validates evidence-ready dates, records exact bounded final-output failures, and stores a decisive audit digest. Priority 7 remained intentionally deferred.
- Raised only `AI_MAX_CUMULATIVE_INPUT_TOKENS` to 150,000 and added the configurable A/B switch plus two finalization reserves and two bounded final-response retries. Database-query, LLM-facing result, Analytics Worker, 64k active-context, cumulative-output, provider-call, and wall-clock policies remain separate.
- Canary request `e8835b86-e4ad-4dcb-bba2-81212c8b88d8` finished `SUCCESS`/`FINAL` after the final evidence-date fix: 16,553 input tokens, 2,178 output tokens, 4 tool calls, 5 iterations, and 5,823 peak active-context tokens.
- Ran the same fixed ten-question DeepSeek suite with cross-iteration compaction disabled and with `PRESERVE_DECISIVE`. Disabled completed 7/10 using 902,667 input tokens and 996.363 seconds total; preserve completed 8/10 using 857,164 input tokens and 573.907 seconds. All 15 successful answers had durable, correctly cited evidence and both modes made zero data/QC calls after the evidence gate.
- Only two preserve-mode requests actually compacted. S5 still failed after exceeding the 150k cumulative-input ceiling, and F4 lost explicitly requested numeric columns that the non-compacted answer retained. The apparently additional S2 success did not use compaction and reflects provider-output variance. Strict answer review was six complete/one partial/three failed for disabled versus five complete/three partial/two failed for preserve.
- Restored `AI_CONTEXT_COMPACTION_MODE=DISABLED` as the current `dev` setting. Deployment `e962dc56-8c02-4f22-a943-e4a2a1d1c332` reached `SUCCESS` on runtime commit `88a5514`; documentation commit `9eb55e6` then deployed as `945dad67-b1e9-410d-bcbf-26a40ee3215a` and also reached `SUCCESS`. Per-tool result shaping remains enabled; only cross-iteration compaction is disabled.
- All 180 A/B provider calls stored bounded reasoning details, concise decision summaries, usage, and 30-day expiry in `Analysis_Model_Call`. Unit tests passed 58/58, live backend verification passed, and deterministic Golden Test run `801f4f11-5d8a-4774-9fa6-58bf60f68f47` passed 16/16. Full results and unresolved gaps are in `MARKET_AI_AB_TEST_2026-09-14.md`.
- The first local Railway read hit the known Avast TLS `UnknownIssuer`; setting `SSL_CERT_FILE` to the verified CA bundle restored the connection without disabling TLS validation. No secret, provider/model, database/Feature value, schedule, volume, endpoint, or unrelated service was changed.

## 2026-09-14 — Deploy per-model-call audit and global conditional QC

- Added five non-secret `market-ai-backend` variables without exposing their values as secrets: `AI_CUMULATIVE_COMPACTION_THRESHOLD_PERCENT`, `AI_STORE_REASONING_DETAILS`, `AI_REASONING_RETENTION_DAYS`, `AI_REASONING_MAX_BYTES_PER_CALL`, and `AI_REASONING_CLEANUP_INTERVAL_SECONDS`. Database/query, Analytics Worker, 64k active-context, 100k cumulative-input, 12k cumulative-output, 32-call, and 20-iteration ceilings were not increased.
- Git commit `fe8cb06` deployed as `97f4892d-ff28-4d47-85f4-eaf18f9a9f7b` and reached `SUCCESS`; startup completed and private `/health` returned HTTP 200. It added per-provider-call audit, 75%-cumulative-input semantic compaction, bounded reasoning retention, and global conditional/scoped QC behavior.
- First post-deploy streak smoke `56cf2a0c-76f0-483c-9e84-ff7e2780227d` completed seven successful data tools but failed at iteration 5 because DeepSeek returned truncated `record_evidence` JSON. The database and query results were valid. Audit rows captured per-call usage/reasoning without storing credentials.
- Commit `baadbff` made malformed provider tool arguments recoverable and stored only argument length/SHA-256 in failed-step audit, not partial content. Deployment `4d49e4a1-afdd-4abb-b92b-974edc63eb09` reached `SUCCESS`; startup and private `/health` HTTP 200 passed.
- Identical rerun `9ad62d13-cc26-492c-8f3a-769d9d4e3741` completed `SUCCESS`/`FINAL` in 8 iterations and 9 tool calls with 68,273 input tokens, 4,166 output tokens, 72,439 combined tokens, and 15,688 peak active-context tokens. It created exactly eight retry-safe `Analysis_Model_Call` rows; per-call reasoning formats/token usage/tool-family stages and 30-day expiry were populated where the provider supplied them. No broad 2015–2026 QC scan ran.
- Live backend verification PASS, Feature Catalog semantic audit PASS at 91/91 calculation-verified definitions, and deterministic Golden Test run `5d2a8f03-58af-4807-ae8e-7dc4ab5f1491` passed 16/16. Local application tests passed 41/41.
- After `config pull --force`, the first IaC plan repeated the known false CLI-version failure because Node resolved PowerShell `_` rather than the verified CLI. Setting `_` to the actual Railway 5.54.1 executable made `config plan` report `dev` fully up to date. No certificate verification was disabled.
- No secret value, provider/model, Feature value/formula, Feature 2 v2 activation, schedule, volume, endpoint, or unrelated Railway service changed.

## 2026-09-14 — Deploy generic condition-run screening and compact semantic preflight

- Added only two non-secret `market-ai-backend` limits: `CONDITION_RUNS_MAX_DATE_RANGE_DAYS=7305` and `CONDITION_RUNS_MAX_EPISODES=200`. Existing ticker, estimated-row, timeout, backend-byte, LLM-result, cumulative-token, and context limits remain independent and unchanged.
- Git commit `4843c4e` deployed as `3fdef450-76c3-4685-b741-b5baf732c96c` and reached `SUCCESS`. The new generic `find_condition_runs` tool evaluates catalog-approved AND conditions over consecutive per-ticker trading observations and returns compact episodes; it does not accept model-written SQL or require Analytics Worker/raw-table access.
- The first identical DeepSeek streak smoke `edf80a9f-91f2-4078-b432-5db4bc3195c4` found the correct BBCA episodes but reached the unchanged 100,000 cumulative-input gate before finalization (101,627 input tokens, 4,702 output tokens, 14 calls, 9 iterations). Audit identified redundant semantic preflight and an over-broad quality request; no token or query limit was increased.
- Git commit `0ce0abe` deployed as `8231132b-974c-49fb-a48b-022ad68f31c7` and reached `SUCCESS`. Data handlers now auto-load compact semantics for only referenced catalog columns; complete definition retrieval remains available for detailed methodology, while missing/inactive catalog entries still reject execution.
- The exact rerun `2d7f8adf-5119-4a60-9ac4-c1b789497ff5` finished `SUCCESS`/`FINAL`: 11 tool calls, 9 iterations, 85,591 cumulative input tokens, 4,129 output tokens, 89,720 combined tokens, and 18,476 peak active-context tokens. It stored evidence `438daac1-8e52-4207-8a88-25130dc7dfb8` and reported the two qualifying BBCA positive-return runs at 2019-05-23 through 2019-06-11 (8 observations) and 2023-04-06 through 2023-04-26 (9 observations).
- Local tests passed 33/33; deterministic golden run `4ff14bf3-8c5e-4248-b506-08af06b65dec` passed 16/16; live catalog audit remained 91/91 calculation-verified definitions with zero incomplete rows. Both deployments completed startup and returned private `/health` HTTP 200.
- Final linked-context `railway config plan` reported the `dev` environment already up to date. The first read-only attempt hit the workstation's known TLS `UnknownIssuer`; retrying with the verified local CA bundle succeeded without disabling certificate validation or changing Railway state.
- No secret value, provider/model, raw/Feature value, calculation worker, schedule, public endpoint, volume, or unrelated Railway service changed.

## 2026-09-14 — Enable bounded INSIGHT stopping policy

- Added non-secret `market-ai-backend` configuration `AI_ANALYSIS_MODE=INSIGHT`, `AI_MIN_INSIGHT_DATA_CALLS=2`, and `AI_MAX_ANALYSIS_SECONDS=600`. The 32-tool-call, 20-iteration, 100,000 cumulative-input, 12,000 cumulative-output, 64,000 hard-context, and independent query limits were not increased.
- Git commit `d3f0e53` deployed as `353675ba-ecfc-4065-aa5f-52dbb9259d9c` and reached `SUCCESS`. It separated durable `record_evidence` calls from new `complete_analysis` finalization and enforced two distinct successful analytical query hashes for data/screening questions in INSIGHT mode.
- First INSIGHT smoke `a2118f3d-344a-4838-8816-ebb949123541` correctly continued past its first observation, but accumulated 102,812 input tokens across 15 tool calls before completion because it attempted extra Feature definitions, retried invalid calls, and wrote three separate evidence rows. It failed at the unchanged 100,000-input hard gate; no limit was raised.
- Git commit `ffa8b10` deployed as `72e25310-328b-4d75-9b15-459864151cec` and reached `SUCCESS`. Direct ticker retrieval now omits Screening schemas until required, evidence is normally consolidated, and a successful evidence result tells the model whether the distinct-query stopping condition has been met.
- Exact smoke rerun `19b5ef94-a6c3-4cb8-8396-aad7414f2a08` finished `SUCCESS`/`FINAL`: 12 tool calls, 11 iterations, 98,681 cumulative input tokens, 4,183 output tokens, 102,864 combined tokens, and 18,174 peak active-context tokens. It ran two distinct analytical queries, consolidated one evidence item, passed `complete_analysis`, and automatically compared BBCA with large-bank peers after the initial direct result. The final answer reported 2026-08-31 as the common Feature 1–3 date, BBCA close 6,475 and 20-trading-day return +0.39%, a source-valid elevated-volume anomaly, and no predictive claim.
- Git commit `b3b7b18` added the independent 600-second whole-analysis circuit breaker and deployed as `c94b5423-a1dc-4006-b0b4-97c5caf03b0c`; deployment, startup, and `/health` 200 all passed. The 180-second provider timeout remains per call. Local tests passed 30/30; live catalog/backend verification and deterministic golden acceptance passed.
- The local smoke harness initially stopped waiting at 240 seconds while its Railway request was still healthy and later completed successfully. Its default wait is now 720 seconds, longer than the 600-second orchestration budget, so harness timeout is no longer misreported as an application failure.
- Final `railway config pull --force` and `railway config plan` reported `dev` already up to date. No secret, provider/model, database/Feature value, schedule, volume, endpoint, or unrelated service changed.

## 2026-09-14 — Enable advanced orchestration limits and verify four-bank insight

- Increased only the per-analysis orchestration circuit breakers on `market-ai-backend`: `AI_MAX_TOOL_CALLS` from 12 to 32 and `AI_MAX_TOOL_ITERATIONS` from 8 to 20. Deployment `87d3e4dd-ceda-4efb-9710-3e08110b10fe` reached `SUCCESS`. This does not activate the deferred ADVANCED/Analytics Worker tools; the separate 100,000 cumulative-input, 12,000 cumulative-output, 64,000 hard-context, database query, and timeout limits remain unchanged.
- First advanced-profile request `b24fd791-4536-4cac-a76c-b776e397e038` completed discovery, quality validation, semantic preflight, and the four-bank query, but OpenRouter/DeepSeek omitted required `record_evidence.evidence_type`. The handler's direct key access raised fatal `KeyError`; the requested market values were not published as a completed answer.
- Added backend validation so missing/invalid evidence fields produce a recoverable tool error before database access. Migration `database/migrations/20260914_030_validate_evidence_requests_in_backend.sql` records that runtime contract. Git commit `bf6f8b8` deployed as `6d209137-0ed8-4b1a-ab6e-b8d64194875b` and reached `SUCCESS`; unit tests passed 25/25.
- Exact-question rerun `87b682d6-2092-453b-ba00-d71dab1f8f6d` finished `SUCCESS`/`FINAL` with 9 tool calls, 10 iterations, 81,280 input tokens, 3,989 output tokens, 85,269 total tokens, and 13,697 peak active-context tokens. It stayed below every cumulative/context limit, cited one same-request evidence row, stored version/methodology snapshots, and identified BBCA and BBNI as descriptive price-volume divergence candidates on 2026-09-11 without making predictive claims.
- Final `railway config plan` reported the `dev` environment already up to date. No database row/query limits, raw or Feature values, model/provider, secret, schedule, volume, endpoint, or other Railway service was changed.

## 2026-09-14 — Complete OpenRouter DeepSeek end-to-end acceptance

- Deployed the approved OpenRouter/provider and Feature-semantic hardening sequence only to `market-ai-backend`: `234e3181-be5e-4a6c-be50-84d70ca2da0f` (`b8d9b10`), `dc857d94-fa52-4820-84bf-256384324d1d` (`ae87d89`), `e515a45c-e6ee-41b0-a432-6c9d19b07f10` (`538a8de`), `1198728d-aa9b-4a32-b8e3-0574007448b2` (`6e0d236`), `533ee5c0-6f3d-4a0a-8803-bfa8f302ad73` (`5a5d61a`), `c0e0279b-ee78-4ac9-b9e2-4c002379ec0c` (`1f03cfc`), and final `937d5add-76a6-48a7-94c2-4c507897def7` (`0017a40`). Every listed deployment reached `SUCCESS`.
- Preserved the strict parser after smoke `fc4d2245-ed78-46af-87a6-7987e95b8e81` returned a Markdown-wrapped final; only bare JSON or one exact JSON fence is accepted and Pydantic validates the complete final contract.
- Preserved the 12-call limit after smoke `6a8ba0d7-3154-450b-bed4-832bb38b4360` exhausted it. Exact table identifiers, whitespace-keyword OR discovery, and non-duplicated validation/estimation reduced redundant calls. A transient workstation outage then blocked GitHub/Railway HTTPS; per-command OpenSSL plus the trusted local CA restored Git push without printing the PAT.
- Smoke `5d974b45-d034-4df3-abbc-a15ccbaa5687` exposed two additional issues: verbose discovery output hid relevant identifiers during compaction, and a 69-character premature final failed the schema. Discovery now preserves compact candidate identifiers, complete selected-column semantics still come from `get_feature_definition`, malformed finals receive bounded corrective feedback, and final evidence IDs must exist for the current request.
- Smoke `95165771-09b7-482f-8583-34d7c80d24a8` proved a direct one-ticker/one-date request could not fit a redundant progressive-family expansion and estimate inside eight iterations. Direct retrieval now begins with Query/Screening, bounded `query_features` performs its own enforcement, and ADVANCED is not exposed for ordinary retrieval. Neither the 8-iteration nor 12-call limit was raised.
- Smoke `a31ac1d7-cb6e-4b59-a353-58e4f4875eac` successfully reached `query_features` but showed `record_evidence` was unreachable because its AUDIT family was neither core nor requestable. Only `record_evidence` is now always exposed; `get_analysis_history` remains non-core.
- Smoke `cbc44cb6-541f-448f-9914-8b4d01d2572a` successfully queried BBCA and created two evidence rows but used its final iteration looking for a nonexistent final-answer tool. Recording evidence now explicitly transitions the following model call to strict finalization without data-tool schemas.
- Final durable smoke `fb599cc3-7853-4d7c-b710-4bfd153823ee` finished `SUCCESS`/`FINAL` through the deployed Railway worker using `openrouter` and `deepseek/deepseek-v4.1-flash`: 8 tool calls, 6 iterations, 39,562 input tokens, 2,208 output tokens, 41,770 total tokens, and 12,529 peak active-context tokens. The answer used the common safe date `2026-08-31`, cited an evidence ID actually stored for that request, retained point-in-time/survivorship and source-valid-anomaly warnings, and stored both version and methodology snapshots.
- Post-deploy checks PASS: 24 backend unit tests; deterministic golden run `c16b20e2-1c49-4088-8eb2-4328471d61e1` at 15/15; 91/91 calculation-verified Feature definitions with zero semantic gaps; exact Feature 1–3 catalog/physical coverage; identifier-preserving discovery; `record_evidence` always exposed; history not core; raw-column rejection; and live `Nego`/`Regular`/`Tunai` aggregation. Final `railway config plan` reported the `dev` environment already up to date. No secret value, raw/Feature value, schedule, volume, endpoint, or other Railway service was changed.

## 2026-09-14 — Configure OpenRouter DeepSeek for market AI

- Confirmed the project-owner-supplied `OPENROUTER_DEEPSEEK` secret exists on `market-ai-backend`; its value was never printed or committed.
- Bounded live provider probes passed for both strict function calling and strict final structured output using `deepseek/deepseek-v4.1-flash`. Usage accounting was returned by the provider.
- Set only four non-secret `market-ai-backend` variables with deployment initially suppressed: `AI_PROVIDER=openrouter`, `AI_MODEL=deepseek/deepseek-v4.1-flash`, `AI_REASONING_EFFORT=high`, and `AI_MAX_FEATURE_METADATA_TOKENS=5000`. The existing OpenAI secret remains available for an explicit future provider switch; there is no silent fallback.
- Updated `.railway/railway.ts` to preserve the generic provider variables and `OPENROUTER_DEEPSEEK`. Railway config plan reported no infrastructure drift; no other service, schedule, volume, endpoint, or variable was changed.

## 2026-09-13 — Deploy private market AI backend and isolate OpenAI quota blocker

- Created private service `market-ai-backend` (service ID `2cefa0cd-c9fc-4b84-992e-fdf08535a064`) in project `lucid-patience`, environment `dev`. It has one `sfo` replica and no public domain.
- Set a least-privilege `DATABASE_URL`, generated `MARKET_AI_INTERNAL_API_KEY`, and all approved database-query, LLM-result, context, cumulative-token, model, timeout, and worker-lease variables. Values of the secrets were never printed or committed. The project owner subsequently added `OPENAI_API_KEY` directly as a Railway secret.
- Initially left the GitHub source disconnected so no knowingly failing deployment was created before the OpenAI credential existed. After the credential was confirmed, the exact planned source/build/deploy diff was limited to this service: GitHub `rednightt33/saniti`, root/watch path `/apps/market-ai-backend`, Dockerfile, private `/health`, `ALWAYS` restart, and the uvicorn start command.
- Pulled the live state into `.railway/railway.ts`. The first `config plan` invocation failed because the IaC SDK resolved PowerShell's `_` process variable instead of the Railway CLI binary; setting `_` to the verified Railway CLI 5.54.1 executable fixed evaluation, and the resulting plan reported no drift.
- Connected GitHub `rednightt33/saniti` branch `main`, applied the reviewed zero-add/three-change/zero-destroy service-only plan, and verified initial deployment `db143fa6-3eff-4cf3-9ebe-c1d56d53b171` reached `SUCCESS`. Runtime logs showed application startup and Railway `GET /health` HTTP 200.
- Local SSH inspection was unavailable because the workstation has no Railway SSH key. A durable smoke request was therefore inserted through the least-privilege public database proxy and was claimed by the running Railway worker, proving the queue-to-worker path.
- Smoke request `6a5df01f-e4c5-4296-b2a0-c4bdd5d5a756` stopped before any tool call because OpenAI returned HTTP 429 with `insufficient_quota` / `credit_balance_exhausted`. The service, key presence, database access, worker lease, and request lifecycle were operational; paid OpenAI API credits are the remaining external end-to-end gate.
- Updated the transport to report safe OpenAI error type/code/message plus request ID and to avoid retrying non-transient quota exhaustion. Transient 429 responses retain bounded retry behavior.
- Deployed that diagnostic patch from Git commit `e270c1bbeeaecbff74b184eeed09f37df32cf757` as `8bbb044a-b8bf-49f9-b4ab-b85d234ec1a5`; it reached `SUCCESS`, completed startup, and passed `/health` with HTTP 200. Post-deploy smoke request `07ea98c7-d940-4f50-8ae3-6c3cf5db70e3` recorded the exact quota codes with zero model input/output tokens and zero tool calls, confirming immediate safe failure instead of wasteful retries.
- No existing Railway service, schedule, source, network endpoint, volume, raw/Feature value, or Feature automation was changed.

## 2026-09-13 — Activate always-on Feature 01 calculation worker

- Created `feature-01-worker` (service ID `de4e34ee-435b-408f-a77f-63e6698a2dab`) in project `lucid-patience`, environment `dev`. It deploys `rednightt33/saniti` branch `main` from `/apps/feature-01-worker`, with matching watch path, Dockerfile build, `python worker.py`, one `sfo` replica, `ALWAYS` restart, and no cron schedule or public domain.
- Set only `DATABASE_URL` as a Railway reference to the existing `Postgres` service; no credential value was copied to GitHub. Price cron services, schedules, source, variables, and TradingView behavior were unchanged.
- Initial deployment `5465b07b-5919-4dc1-a513-871ba7ca4ad2` of Git commit `6c1ee21d202641eaf545882892e349a2f0795f06` reached `SUCCESS`. Runtime logs showed `worker_started`, then `claim_started` and `calculation_completed` for a committed metadata-only BBCA 2026-09-11 re-ingestion.
- Live database read-back: the reopened BBCA queue key returned to `DONE` with `source_attempt_count=1`; `Feature_Status` was `SUCCESS` with zero outstanding items; `Feature_Calculation_Log` recorded `SUCCESS` and one refreshed Feature row. The queue had two `DONE` items, one ticker `SUCCESS`, and no pending/processing/failed item at verification. No OHLCV value was changed by the test.
- Pulled the live Railway configuration into `.railway/railway.ts`; `railway config plan` reported no drift. The pull also captured the pre-existing `DB2` and `db-ops-runner` resources, which were not modified.

## 2026-09-13 — Record database-side price ingestion timestamps

- Updated the shared `apps/idx-price-cron` bulk upsert so `idx-price-cron` and `idx-price-recovery-cron` assign `Price_Stock_Indonesia_IDX.ingestion_time` from PostgreSQL `statement_timestamp()` on both insert and `(ticker, date)` conflict update.
- Deployed Git commit `a988a0e2fc37d1ba58db70e365f1d63be98bc9fa` to DAILY as deployment `ae37f76e-caa2-4397-b93d-c5e588d95fe4` and RECOVERY as deployment `08c05d86-fc2b-44d1-9a9a-d4e2ea7fb74e`; both reached `SUCCESS`.
- Preserved the preceding successful deployments as rollback references: DAILY `3b73e6c5-a60e-459b-ac1b-314c362cf3e9` and RECOVERY `65de3099-051e-45a7-81b2-b135f3bcced4`.
- Kept both cron schedules, start commands, service variables and secrets, watch paths, restart policies, monitoring flow, and Telegram behavior unchanged.
- No **Run now** action or TradingView query was issued during deployment.

## 2026-09-09 — Connect application services to GitHub monorepo

- Connected all four application services to `rednightt33/saniti` on branch `main`, one service at a time, and waited for each resulting deployment to reach `SUCCESS` before continuing.
- Set `idx-price-cron` and `idx-price-recovery-cron` to root `/apps/idx-price-cron` with watch path `/apps/idx-price-cron/**`; their successful source deployments are `3b73e6c5-a60e-459b-ac1b-314c362cf3e9` and `65de3099-051e-45a7-81b2-b135f3bcced4`.
- Set `telegram-monitor` to root `/apps/telegram-monitor` with watch path `/apps/telegram-monitor/**`; deployment `9c25be22-9fba-48fc-81a3-1a1b555dd59d` reached `SUCCESS` after Railway passed its `/health` check.
- Set `telegram-trigger` to root `/apps/telegram-trigger` with watch path `/apps/telegram-trigger/**`; deployment `f5bf0056-460f-437f-b2bd-4d0a8334e73d` reached `SUCCESS`, Railway passed its `/health` check, and the public health endpoint returned HTTP 200 with status `ok`.
- Saved the preceding active deployments as rollback references: DAILY `db51a5fe-b845-44c3-abcc-5a91a3883bba`, RECOVERY `1c3e79af-19aa-4482-906a-bab7584c51c4`, monitor `c03b134b-0879-4e58-aca5-add943f74afa`, and trigger `3e8fd2fe-1cb6-47e7-9233-209bf259d404`.
- Preserved all environment-variable and secret keys, cron schedules, start commands, health checks, domain, private networking, restart/serverless settings, and PostgreSQL configuration. No **Run now** action or TradingView query was issued.
- Pulled the resulting live configuration into `.railway/railway.ts`.

## 2026-09-09 — Show IDX job start and finish times in Telegram

- Extended `telegram-monitor` messages with separate `Triggered at` and `Finished at` timestamps in Asia/Jakarta, sourced from `Monitoring_Price_ALL.run_time` and `finished_at`.
- Kept the existing headline, duration, missing-ticker list, delivery ledger, DAILY/RECOVERY schedules, and trigger flow unchanged.
- Added regression coverage for UTC-to-WIB conversion and verified the formatter against a live monitoring row without sending a duplicate Telegram message.
- The first upload attempt (`aa896904-a563-48b1-8b0c-fa77ca712092`) failed before Railway could create its code snapshot; the previous deployment remained active.
- Retried once and verified deployment `c03b134b-0879-4e58-aca5-add943f74afa` reached `SUCCESS`.

## 2026-09-09 — Telegram controls for manual IDX price runs

- Created public serverless service `telegram-trigger` (service ID `5a3f820c-2bb2-494b-b771-15fa6a5eb48a`, service-instance ID `78bd93d5-f74a-42fb-ad25-2be856bbda07`).
- Deployed the final webhook build as `3e8fd2fe-1cb6-47e7-9233-209bf259d404`; Railway reported `SUCCESS`, and `/health` returned `ok`.
- Registered `https://telegram-trigger-dev.up.railway.app/telegram/webhook` with Telegram for messages and button callbacks. Telegram reported zero pending updates and no webhook error; the bot command menu exposes `start`, `run_price`, and `run_recovery`.
- Added fixed controls for `idx-price-cron` and `idx-price-recovery-cron`. Only the configured owner Chat ID is accepted; arbitrary service names are never accepted from Telegram input.
- Stored the bot token, webhook secret, environment-scoped Railway project token, Chat ID, database reference, allowlisted service-instance IDs, and cooldown as Railway variables. No secret value is stored in Git.
- Added webhook-retry deduplication through `Telegram_Command_Log.telegram_update_id` and a 15-minute per-service rapid-click cooldown.
- Kept Telegram acknowledgement delivery independent from Railway acceptance so a temporary chat-message failure cannot relabel or repeat a successfully started cron job.
- Sent the `/start` menu successfully and ran one end-to-end RECOVERY test. The first command was accepted, an identical replay was ignored, execution `9926d137-6316-4c04-a1c2-099d87bd4735` completed for 2026-09-08, and `telegram-monitor` recorded the final message as `SENT`.
- The scheduled DAILY and RECOVERY start commands, 17:00/06:00 Asia/Jakarta schedules, exact candle-date rule, and existing completion-notification flow were not changed. No DAILY query was run during this deployment.
- Pulled the live Railway configuration into `.railway/railway.ts`; the follow-up plan reported no drift.

## 2026-09-09 — Correct Telegram private endpoint port

- Confirmed manual DAILY execution `1d50802c-caa7-4d1f-9d5d-055b0402eb4f` completed with 829 of 844 symbols but its Telegram request still failed.
- Root cause: both cron services had resolved `TELEGRAM_NOTIFY_URL` to `http://telegram-monitor.railway.internal:/notify` because the referenced service-level `PORT` variable was empty. The request therefore used the wrong port.
- Set both DAILY and RECOVERY notification URLs to the explicit private listener port `8080`; the resulting service deployments `db51a5fe-b845-44c3-abcc-5a91a3883bba` and `1c3e79af-19aa-4482-906a-bab7584c51c4` reached `SUCCESS` without querying TradingView.
- Re-sent the completed manual DAILY execution without running the price query. Telegram delivery was recorded as `SENT`; a repeat returned `duplicate`, confirming anti-duplicate handling.

## 2026-09-09 — Fix Telegram private-network wake and message spacing

- Diagnosed manual DAILY execution `c225b4c9-a009-4295-93f0-59ad4b6bb209`: TradingView processed 844 tickers in about six minutes and wrote 822 exact-date rows with 22 missing; Telegram added about nine seconds before failing with private-network `connection refused`.
- Changed only `telegram-monitor`: it now listens on Railway IPv6 private networking while preserving IPv4 compatibility where available.
- Added one blank line between the status summary and the `Missing:` ticker list.
- Notification calls remain active for both MANUAL and SCHEDULED executions of DAILY and RECOVERY. Query, worker, candle-date, and upsert behavior are unchanged.
- Deployed the fix as `282174bb-10e1-43e1-b498-f90b0742ff94`; Railway reported `SUCCESS` and `/health` returned HTTP 200.

## 2026-09-09 — Event-driven Telegram notifications for IDX price jobs

- Created the separate `telegram-monitor` service (service ID `a6b4e061-721f-4173-82f8-07ccb45740fc`) with no cron schedule, `/health` health check, `ALWAYS` restart policy, and Railway serverless sleep enabled.
- Stored the Telegram bot token, Chat ID, and shared caller secret only as Railway variables; no secret value is stored in GitHub or PostgreSQL.
- Configured `idx-price-cron` and `idx-price-recovery-cron` to send their committed `Monitoring_Price_ALL.execution_id` over Railway private networking. The caller retries temporary wake/network failures and does not roll back price data if notification delivery fails.
- Deployed `telegram-monitor` successfully as deployment `c4bf00cd-3452-4279-8342-ad21c55af9df`; Chat ID activation produced successful redeployment `19cc3f3c-c848-43fd-8fe4-5e9abd531551`, and the final shared-secret rotation produced successful deployment `6c4886fa-ebf4-45ba-b01c-1501c0a71974`.
- Deployed notification-enabled DAILY build `14ec1625-9b26-4f9f-9d53-7a3f63665266` and RECOVERY build `7a126d48-0a67-473c-a62c-004abf68a000`; both reached `SUCCESS` without executing TradingView.
- Sent one end-to-end test from historical RECOVERY execution `80d7d401-d1a2-4ac8-a276-dfbb4e89299b`. A second request returned `duplicate`, confirming the anti-duplicate ledger.
- Removed stale `valiant-connection` declarations from `.railway/railway.ts` because that service and volume are no longer present in the live `dev` environment; no live resource was deleted.

## 2026-09-09

### Correct recovery cron completion status

- Confirmed the scheduled recovery completed its database work in about two seconds, wrote 12 missing symbols as `NEEDS_REVIEW`, closed its PostgreSQL connection, and released its advisory lock.
- Corrected `NEEDS_REVIEW` to exit with code `0` because it is a completed, monitored business outcome rather than a crashed process.
- Kept a non-zero process exit exclusively for an actual `FAILED` status or an unhandled exception.
- Added regression tests for both reviewable and failed outcomes.
- Verified a no-database, no-TradingView Railway smoke execution (`7da53b07-351d-4682-93e2-9af2776e0700`) reached `EXITED` in about two seconds.
- Restored the production recovery start command and verified final RECOVERY deployment `9527e31d-fdd2-46bc-84c3-7ca29c486161` and DAILY deployment `b5d09e04-a255-4441-9dbe-dde0708b05a7` reached `SUCCESS`.

## 2026-09-08

### Guarantee IDX cron process termination

- Diagnosed `idx-price-recovery-cron` remaining `Active` after its 06:05 Asia/Jakarta work had already emitted `run_completed` and recorded 13 symbols as `NEEDS_REVIEW`.
- Added a guarded entrypoint that flushes stdout/stderr and explicitly terminates the process after database contexts close, including non-zero `NEEDS_REVIEW` and failure paths.
- Replaced the stuck recovery instance without issuing another TradingView query.
- Verified DAILY deployment `c831e1ed-0b76-42dc-9ac9-7006906832eb` and RECOVERY deployment `f751f9a1-c8d3-423a-9ccf-fd98d492d75c` reached `SUCCESS`.
- Verified both cron services returned to waiting state and recovery remains scheduled for 06:00 Asia/Jakarta.

## 2026-09-07

### Broker-summary authentication-stop repair

- Stopped both local historical supervisors after detecting repeated Stockbit HTTP 401 responses.
- Corrected the runner so authentication exhaustion reaches the supervisor as exit code 3 instead of being treated as an ordinary per-date failure.
- Replaced the Stockbit credential only in the new local process environments; its value was not persisted.
- Restarted both non-overlapping historical supervisors with three API workers each and verified successful recovery loads in both ranges.
- No Railway service, deployment, domain, or environment-variable values changed.

### Manual-safe IDX price services

- Changed `idx-price-cron` to explicit DAILY mode with schedule `0 10 * * *` UTC (17:00 Asia/Jakarta). Its **Run now** action performs a full current-day universe query.
- Created `idx-price-recovery-cron` (service ID `a8e6e32a-fcd8-4c33-9ecc-1488a4b2db05`) in environment `dev`, with explicit RECOVERY mode and schedule `0 23 * * *` UTC (06:00 Asia/Jakarta). Its **Run now** action retries only the preceding weekday's DAILY missing symbols; Saturday, Sunday, and Monday target Friday.
- Both services use the existing PostgreSQL variable reference, Dockerfile build, and `NEVER` restart policy.
- Added exact candle-date validation, `(ticker, date)` upsert protection, per-execution monitoring history, and a shared PostgreSQL advisory lock.
- No manual TradingView query was triggered during deployment.
- Verified final DAILY deployment `c9764e81-3b34-44b2-9402-c1fc212622f6` and final RECOVERY deployment `a8fc3609-2809-4bfa-b387-578631a8baa3` reached `SUCCESS`.
- Pulled the live configuration into `.railway/railway.ts`; the follow-up Railway configuration plan reported no drift.
- Triggered **Run now** on `idx-price-cron` after deployment. Execution `f4fd425d-edfe-433a-9925-99d052c794c5` ran in explicit DAILY mode, queried all 844 universe tickers, updated 824 exact-date candles, and correctly retained 20 no-current-candle symbols as missing with `PARTIAL` status.

### Historical broker-summary workers split

- Replaced the single local 2025-08-31 through 2018-01-01 supervisor with two concurrent, non-overlapping local supervisors.
- Recent range: 2025-08-31 through 2021-01-01 descending; older range: 2020-12-31 through 2018-01-01 descending.
- Set each process to three API workers so combined Stockbit concurrency remains six.
- Kept separate status and log paths, disabled local CSV output, and retained the five-consecutive-401/403 stop rule for both processes.
- Both supervisors use the existing Railway PostgreSQL TCP proxy. No Railway service, deployment, domain, or environment-variable values changed.

## 2026-09-06

### GitHub tracking contract established

- Added mandatory AI read order and same-task GitHub update rules.
- Added separate database and Railway changelogs.
- Added forward-only SQL migrations for database schema history.
- Imported the current project as a secret-safe `.railway/railway.ts` snapshot.
- Extended the daily GitHub Action to capture Railway configuration drift and database schema changes.
- Kept live secrets and raw production data outside GitHub.

### PostgreSQL daily-price table

- Loaded 668,967 daily price rows into the PostgreSQL service in environment `dev`.
- Renamed the table to `Price_Stock_Indonesia_IDX` for the requested capitalization.
- No Railway service, deployment, domain, or environment-variable values changed.

### Broker-summary supervisor

- A local Windows supervisor was introduced for the Stockbit backfill.
- This is a process on the user's PC, not a Railway service or deployment.
- It resumes incomplete dates and recreates the temporary PostgreSQL TCP proxy after connection failure.

### Broker-summary authentication recovery

- Replaced the expired Stockbit session credential in the local Windows supervisor; no credential value was committed.
- Restarted the supervisor and preserved all dates already marked `COMPLETED`.
- Confirmed the existing Railway PostgreSQL TCP proxy and database connection remained healthy.
- Verified automatic recovery from the earliest `NEEDS_REVIEW` date before allowing the backfill to continue.
- No Railway service, deployment, domain, or environment-variable values changed.

### Automated IDX daily prices

- Created service `idx-price-cron` in environment `dev` (service ID `43c86c6f-3221-4403-83c3-cd3056441558`).
- Deployed the final Python/Docker TradingView price updater; verified deployment `ddd2ba96-d64e-414a-a5c7-87e15eeb23f8` reached `SUCCESS`.
- Connected `DATABASE_URL` to the existing Railway PostgreSQL service using a Railway variable reference; no credential value is stored in GitHub.
- Set cron schedule `0 10,23 * * *` UTC, corresponding to 17:00 Asia/Jakarta for the full `DAILY` run and 06:00 Asia/Jakarta the following day for missing-symbol `RECOVERY`.
- Set restart policy to `NEVER` so a failed recovery cannot create an unapproved third TradingView query.
- The first full TradingView query is scheduled for 2026-09-07 at 17:00 Asia/Jakarta. Existing price history through 2026-09-04 remains unchanged.
- Pulled the resulting live Railway state into `.railway/railway.ts`; the follow-up configuration plan reported no drift.

### Parallel historical broker-summary backfill

- Added a second local Windows supervisor for a descending, database-only backfill from 2025-08-31 through 2018-01-01.
- Kept the existing ascending backfill active and assigned separate status/log files to each process.
- Added a five-consecutive-401/403 stop rule to both supervisors so an invalid Stockbit token stops querying instead of marking the remaining date range `NEEDS_REVIEW`.
- Historical CSV export is disabled; only operational status and logs are retained locally.
- No Railway service, deployment, domain, or environment-variable values changed.
