# Railway changelog

## 2026-09-26 — DataNeed switched on in dev; lookup_fact disabled after the parity test

- Scope approved by the user (DataNeed rollout, phase 5): switch the flags on in `dev`, run the PoCs, and disable `lookup_fact` after a parity test.
- **Fix deployed first**, commit `4aa3272` (code only): an INNER relationship now restricts both requests. A real-model rehearsal against the local Governor and sandbox had found that a spec written reference-left delivered prices for every ticker. Automatic deployments, each `SUCCESS`:
  - market-python-sandbox `181527f0-20a8-4c09-af7e-70e91f3bbaa6`;
  - market-sql-governor `2136ce9e-f54f-4d5a-80e6-611df5348647` (README only);
  - market-ai-orc: `SKIPPED` (no change).
- **Variables** (set with `railway variable set`, each triggering a redeploy):

  | Service | Variable | Value | Deployment | Status |
  |---|---|---|---|---|
  | market-python-sandbox | `PY_SANDBOX_DATANEED_ENABLED` | `true` | `e9faab10-bf91-40bb-a620-40d5b48b4e43` | `SUCCESS` |
  | market-ai-orc | `AI_ENABLE_DATANEED` | `true` | `84f5470c-45be-456d-96b3-605e1113244e` | `SUCCESS` |
  | market-ai-orc | `AI_ENABLE_LOOKUP_FACT` | `false` | `d21aefdf-c134-4f21-9b75-a44cc7eacf2c` | `SUCCESS` |

  - The sandbox was switched on first, so the orchestrator's startup readiness check saw it ready.
  - The sandbox started with `isolation_enforced=true`, and `sessions_started` closed 0 orphan sessions.
  - The orc logged no `python_sandbox_not_ready`, and `/ready` returned 200.
  - Startup logs held no secret-like values.
  - `railway config pull --force` added the three names to `.railway/railway.ts` as `preserve()`. `railway config plan` shows only the three accepted source drifts of the deactivated legacy services, which were not applied.
- **Temporary one-off service** `dataneed-poc-job` (`15021c62-c3d8-41ab-ba28-e2e91eb74eb8`):
  - reference variables only (`DATABASE_URL=${{Postgres.DATABASE_URL}}` for read-only ground-truth sessions, `MARKET_AI_ORC_API_KEY`, `PY_SANDBOX_API_KEY`), all redacted from its output;
  - deployed by `railway up --path-as-root` and deleted with `railway service delete`.
- **PoC on dev** (deployment `1260d059-ebd4-4ea5-8250-3f8109bb72bf`): real model, real data, reference date 2026-09-25, with `lookup_fact` still on. The ground truth comes from read-only SQL and pandas.

  | Question | Result | Label | Tool calls | Seconds | Cost (USD) | Ground truth |
  |---|---|---|---|---|---|---|
  | YTD of bank stocks vs. the same period last year | ANSWER; coverage PASS; warnings FREQUENCY_GAPS, HISTORICAL_REFERENCE_USES_CURRENT_STATE, HISTORY_BUFFER_SHORTFALL | DATA_COVERAGE_VERIFIED | 18 | 237 | 0.0168 | 48 `Banks` tickers, both requests restricted. Every figure equals the ground truth with the model's stated base, the previous year's last close (deployment `c1f86a6a`) |
  | Research: BBCA's 10-day return after RSI-14 falls below 30 | ANSWER as a historical pattern; unmet minimum sample, no holdout and no correction disclosed | DATA_COVERAGE_VERIFIED | 16 | 240 | 0.0166 | 10 event days in the same 5 episodes |
  | Stocks per sector | ANSWER | DATA_COVERAGE_VERIFIED | 10 | 22 | 0.0110 | exact (844 tickers, 12 values) |
  | BBRI's average weekly volume in August 2026 | ANSWER | DATA_COVERAGE_VERIFIED | 11 | 37 | 0.0124 | exact (5 ISO weeks, mean 693,500,400) |
  | Top 10 one-month returns across the IDX | ANSWER; FREQUENCY_GAPS disclosed | DATA_COVERAGE_VERIFIED | 12 | 140 | 0.0089 | the all-ticker ranking is exact; the headline ranking also excludes tickers without a full month, as stated |
  | BBCA close on 2026-09-25 | ANSWER via `lookup_fact` | FACT | 4 | 22 | 0.0022 | exact (6,250) |

  Every answer passed the number-provenance gate with 0 unsupported numbers.
- **`lookup_fact` parity** (deployments `c1f86a6a-788c-49c7-ba47-314d36b98cd1` with the tool on and `8e5bfa0f-a59f-4082-817c-037b88d019f6` with it off). All six answers equal the ground truth:

  | Question | `lookup_fact` on | DataNeed only |
  |---|---|---|
  | BBCA close on 2026-09-25 | 6,250, FACT, 3 calls, 14 s, $0.0009 | 6,250, DATA_COVERAGE_VERIFIED, 9 calls, 35 s, $0.0060 |
  | BBRI average daily volume, 22–25 Sep 2026 | 173,824,325, DATABASE_AGGREGATE, $0.0026 | 173,824,325, DATA_COVERAGE_VERIFIED, $0.0029 |
  | TLKM's highest high in September 2026 | 2,720 on 15 Sep, DATABASE_AGGREGATE, $0.0084 | 2,720 on 15 Sep, DATA_COVERAGE_VERIFIED, $0.0082 |

  `AI_ENABLE_LOOKUP_FACT=false` stays set in `dev`. `/v1/lookup` stays in the Governor, so setting the variable back to `true` (or deleting it) is the rollback.
- Rollback of the whole switch: delete `AI_ENABLE_DATANEED` on market-ai-orc, which restores the Analysis Spec path, then `PY_SANDBOX_DATANEED_ENABLED` on market-python-sandbox. Sessions and bundles in `/data` are kept; no database change is involved.
- OpenRouter usage for the PoC, parity and local rehearsals: about $0.2 of the $10 key limit.

## 2026-09-26 — Apply migration 20260925_003 on dev through a temporary job

- Scope approved by the user: apply the DataNeed catalog migration on `dev` through a temporary one-off service, as in earlier releases.
- **Temporary one-off service** `dataneed-migrate-job` (`e567e0e8-c9ed-4dbf-a72c-de95420de2ae`):
  - it held reference variables only (`DATABASE_URL=${{Postgres.DATABASE_URL}}`, `MARKET_AI_ORC_API_KEY`, `PY_SANDBOX_API_KEY`, `SQL_GOVERNOR_API_KEY`), all redacted from its output;
  - it was deployed by `railway up --path-as-root` from a local directory and deleted with `railway service delete`.
- Deployment `9144cfee-1d9b-402e-b8fc-7d00fcccb899` (read-only):
  - inspected the catalog state before the migration;
  - `/ready` returned 200 on market-sql-governor, market-python-sandbox and market-ai-orc;
  - the sandbox reported `isolation_enforced=true` for the phases 3–5 deployment `e03c61f8`;
  - `POST /v1/data-needs` answered 404 because the flag is off.
- Deployment `f6ef3174-a00a-4823-ae30-0588cb18279b` applied the migration, read it back, checked the Governor's catalog contract, and ran the catalog/schema refresh (see `DATABASE_CHANGELOG.md`).
- No variable, deployment, volume, domain or restart policy of another service was changed. The job's logs held no secret-like values.

## 2026-09-26 — DataNeed architecture phases 3–5 deployed dark (commit daa05cc)

- Same approved rollout: merged to `main` (fast-forward) with every DataNeed flag off; `main` auto-deployed the changed services to `dev`.
- Code:
  - sandbox: persistent analysis sessions (`/v1/sessions`, execute, inspect, outputs, complete, close), the ExecutionManifest, processing coverage and the final status. The routes answer 404 without `PY_SANDBOX_DATANEED_ENABLED`. The image adds the session users `session1`…`session4` (uid 20201–20204);
  - orc: the session tools and the DataNeed mode of the orchestrator (exclusive tools, DATA NEED RULES, the DataNeed answer gate, `execution.analysis_final_status`), all behind `AI_ENABLE_DATANEED`.
- Tests before the merge: market-ai-orc 453 passed; market-python-sandbox 435 passed.
- No variable was added or changed. `AI_ENABLE_DATANEED` and `PY_SANDBOX_DATANEED_ENABLED` stay unset (read back by name on 2026-09-25). `PY_SANDBOX_SESSION_*` and the orc's `PY_SANDBOX_SESSION_TIMEOUT_SECONDS` use their code defaults.
- Automatic deployments of `daa05cc`:
  - market-python-sandbox `e03c61f8-37ec-4d8a-803f-e26605950867`: `SUCCESS`; the Railway health check on `/ready` returned 200;
  - market-ai-orc `48b22523-0828-4981-97b4-d55756deda07`: `SUCCESS`; `/ready` 200;
  - market-sql-governor `72078656-8cd9-4af6-a097-2563132b03fb`: `SKIPPED` (no change under its watch path).
- The startup logs held no secret-like values. The sandbox's `isolation_enforced=true` was read back afterwards by the migration job's read-only run (entry above).
- Migration `20260925_003` was applied afterwards (entry above).
- Rollback: redeploy the phase 2 deployments (sandbox `c2ab2125`, orc `df85aac2`), or revert `daa05cc` on `main`. The flags are off, so the live Analysis Spec path did not change.

## 2026-09-25 — DataNeed architecture phase 2 deployed dark (commit 07fd68b)

- Same approved rollout as phase 1: merged to `main` with every DataNeed flag off; `main` auto-deployed the three services to `dev`.
- Code:
  - the Governor's `POST /v1/extract`, callable with the orc key only. Only the orc Execution Planner calls it, and the planner is registered only with `AI_ENABLE_DATANEED`;
  - the Governor's validator manifest now also carries `row_count` and `truncated`;
  - the orc Execution Planner and `prepare_data_bundle`;
  - the sandbox's governed bundles, Data Quality Profiler and delivery coverage (`POST`/`GET /v1/bundles`, 404 without `PY_SANDBOX_DATANEED_ENABLED`).
- No variable was added or changed; `AI_ENABLE_DATANEED` and `PY_SANDBOX_DATANEED_ENABLED` stay unset. The new limits use their code defaults: `SQL_EXTRACT_*` and `PY_SANDBOX_BUNDLE_*`. With the flag off the sandbox creates no bundle directory.
- Migration `20260925_003` is still not applied.
- Automatic deployments of `07fd68b`, each `SUCCESS` with `/ready` 200:
  - market-sql-governor `a1db4a3e-02fa-4e82-9cd7-ed5af7aa3bf5`;
  - market-python-sandbox `c2ab2125-6ba9-4d31-b74e-438d8060f054`, with `isolation_enforced=true` and 0 interrupted analyses;
  - market-ai-orc `df85aac2-31d9-464b-bdf6-9d00484febd1`.
- The startup logs held no secret-like values.
- Rollback: redeploy the phase 1 deployments (Governor `a01d1535`, sandbox `fa9a1576`, orc `a2bdd594`), or revert `07fd68b` on `main`.

## 2026-09-25 — DataNeed architecture phase 1 deployed dark (commit d7d18ea)

- Scope approved by the user: build the DataNeed architecture in phases, merge each phase to `main` with its flags off (GitHub `main` auto-deploys the three services to `dev`), and verify health.
- Code: the sandbox's DataNeedSpec validator and Research Governor with `POST /v1/data-needs` and `GET /v1/data-needs/{need_id}`; the orc tool `submit_data_need_spec`; the Governor's catalog contract reading the join-semantics columns of migration `20260925_003` when they exist.
- Flags, both unset on `dev` and read back by name: `PY_SANDBOX_DATANEED_ENABLED` (sandbox, default off: the routes answer 404 and no DataNeed state is created) and `AI_ENABLE_DATANEED` (orc, default off: the tool is not registered). No variable was added or changed.
- Migration `20260925_003_add_relationship_join_semantics.sql` is in the repository but **not applied**. Until it is, the catalog contract is unchanged.
- Automatic deployments of `d7d18ea`, each `SUCCESS`, `/ready` 200:
  - market-sql-governor `a01d1535-83f4-42a0-aa69-3862b750cfe0`;
  - market-python-sandbox `fa9a1576-8091-457b-a735-aef212be27a7`, with `isolation_enforced=true` and 0 interrupted analyses;
  - market-ai-orc `a2bdd594-54b9-47f1-90ff-283c7ed8bb54`.
- The deactivated backend and workers created no deployment. The startup logs held no bearer token, OpenRouter key or DSN with a password.
- Rollback: redeploy the previous deployments (Governor `747732ed`, sandbox `035fd115`, orc `a9128831`), or revert `d7d18ea` on `main`. The flags are off, so the live Analysis Spec path did not change.

## 2026-09-25 — Retire market-ai-backend and its workers; connect market-sql-governor, market-python-sandbox and market-ai-orc to GitHub main

- Scope approved by the user:
  - migrate every market-ai-orc dependency on `market-ai-backend`;
  - deactivate `market-ai-backend`, `market-query-sandbox` and `market-analytics-worker` by removing their active deployments and disconnecting their GitHub source, keeping the services, variables and history;
  - purge the retained provider reasoning in `Analysis_Model_Call` now, instead of waiting for the backend's 30-day hourly cleanup (see `DATABASE_CHANGELOG.md`);
  - leave `Tool_Catalog` unchanged;
  - connect the three market-ai-orc services to GitHub `main`.
- **Read-only inspection** (unrendered variables of every service, code, `Tool_Catalog` readers, logs):
  - The only market-ai-orc dependency on the backend was `OPENROUTER_API_KEY = ${{market-ai-backend.OPENROUTER_DEEPSEEK}}`.
  - No other service references a variable of the three legacy services. The two workers depend only on the backend, through a literal `MARKET_AI_BACKEND_URL`.
  - `Tool_Catalog` is read only by market-ai-backend.
  - The backend had been idle since 2026-09-14. Its log held only the two workers' `claim` polls (HTTP 204).
  - Bucket `market-analytics-input` holds 1 object (269 bytes, 2026-09-14) that no `AVAILABLE` snapshot row references. It was left in place.
- **market-ai-orc `OPENROUTER_API_KEY`** is now the service's own literal secret.
  - It was set through the API with `skipDeploys`, read in-process from the backend value and never printed.
  - Read-back: no market-ai-orc variable references `market-ai-backend`, and the resolved value's hash equals the backend's `OPENROUTER_DEEPSEEK`.
  - `GET https://openrouter.ai/api/v1/key` accepted the key; this makes no model call. The key's remaining credit limit was about $2.27.
- **GitHub sources:** `rednightt33/saniti` branch `main`, one service at a time, each after its root directory and watch path were set.
  - Every other setting was compared before and after and was unchanged: Dockerfile, start command, health check, restart policy, replicas, region, schedule and sleep.
  - Each connection deployed `f553258`, whose application code equals the deployed `a5e11a4`.

  | Service | Root / watch path | Rollback reference | New deployment | Verified |
  |---|---|---|---|---|
  | market-sql-governor | `/apps/market-sql-governor` / `/apps/market-sql-governor/**` | `293ba2e2` | `4732bb12-a96c-439d-8b71-635e115a23be` `SUCCESS` | Health check `/ready` 200; dataset janitor ran |
  | market-python-sandbox | `/apps/market-python-sandbox` / `/apps/market-python-sandbox/**` | `beec8e84` | `c24452ca-85b3-4473-874f-8ebc1bc700ab` `SUCCESS` | Volume mounted; `isolation_enforced=true`; 0 interrupted analyses; `/ready` 200 |
  | market-ai-orc | `/apps/market-ai-orc` / `/apps/market-ai-orc/**` | `3669447c` | `643133af-c2a2-4992-9035-9565f3d08950` `SUCCESS` | Clean start; `/ready` 200; first deployment with its own `OPENROUTER_API_KEY` |

- **Temporary one-off service** `legacy-retire-job` (`ad612a88-be0f-4a73-acfe-8acbcdc8a5a9`):
  - It held only `DATABASE_URL = ${{market-ai-backend.DATABASE_URL}}`, the backend's own least-privilege login. The purge therefore ran with exactly the privileges of the backend's cleanup.
  - Deployment `582b8b26-e849-45c0-993f-847f76335391` read the legacy queues, purged the reasoning, and read back.
  - The service was then deleted with `railway service delete`. Its output held counts and timestamps only; no DSN or credential appeared.
  - The queues were empty before the deactivation:
    - `Analysis_Request`: 52 `SUCCESS`, 65 `FAILED`, 5 `CANCELLED`; the latest from 2026-09-14.
    - `Analytics_Job`: 14 `SUCCESS`, 5 `FAILED`.
    - `Analytics_Dataset_Snapshot`: 19 `DELETED`.
    - No row was `PENDING`, `PROCESSING` or `AVAILABLE`.
- **Deactivated**, in dependency order. Each source was disconnected first, then the active deployment removed:

  | Service | Removed deployment | After |
  |---|---|---|
  | market-analytics-worker | `43c3a864-4851-4a01-a615-e532e9d42845` | `REMOVED`, no source |
  | market-query-sandbox | `4ab6ebb2-e41c-4563-a573-241eb7b17f46` | `REMOVED`, no source |
  | market-ai-backend | `8b423a58-19c7-4527-9fa5-12c7776ca815` | `REMOVED`, no source |

  - None of the three has a running deployment left. Their remaining non-`REMOVED` deployments are `SKIPPED` watch-path events and `FAILED` builds from 2026-09-14.
  - Root directory, watch path, all variables (99 on the backend, including `OPENROUTER_DEEPSEEK` and `OPENAI_API_KEY`) and deployment history are kept.
  - Rollback: reconnect `main` and deploy the backend first, then the two workers. Their database objects, logins and `Tool_Catalog` rows were not changed.
- Postgres, pgweb, db-ops-runner, the price crons, the Telegram services, `feature-01-worker` and `ai-data-coverage` were not touched. The environment has 15 services.
- **Configuration sync.** `railway config pull --force` updated `.railway/railway.ts`:
  - The three market-ai-orc services now carry `source: github(...)` with their root directories and watch paths.
  - The three deactivated services have no `source`.
- **Known drift.** `railway config plan` reports 3 changes, not "up to date", with exit code 0, so the daily state-tracking workflow still passes. For each deactivated service it proposes `source.rootDirectory` → null and `source.type` "github" → null.
  - The IaC format keeps the root directory inside the source block, so it cannot represent a disconnected service that keeps its root directory.
  - Setting the backend's root directory to an empty value did not clear `source.type`, so the value was restored at once. No deployment was triggered.
  - Cause, from the environment config: each deactivated service keeps a `source` block holding only `rootDirectory`, with no repository, and the IaC engine reads that as a GitHub source. The services are truly disconnected: push `e8c3d47` changed `apps/market-ai-backend/README.md` and created no deployment.
  - The user first approved `railway config apply`. The pinned plan (0 add, 3 change, 0 destroy, not destructive) marks each of the three changes `deployEffect: deploy`, so applying it would also start a deployment of each deactivated service. With no source, that deployment would most likely rebuild the service's last deployment, a failed 2026-09-14 build, but it could also restart its old image.
  - The plan was not applied. The user chose to keep the drift. Do not apply it without handling those deployments.
- **Autodeploy verified.** The documentation push `e8c3d47` changed the three services' READMEs and triggered their first GitHub deployments. Each reached `SUCCESS` with `/ready` 200:
  - Governor `747732ed-2c6f-40f1-a116-23fc1cbc0d3d`;
  - sandbox `035fd115-b064-4bab-bd27-278be3380413`, with `isolation_enforced=true` and 0 interrupted analyses;
  - orc `a9128831-e7c0-4e9b-87d1-d220f5bd8b44`.
  - The deactivated services created no deployment for that commit.
  - The startup logs held no bearer token, OpenRouter key or DSN with a password.

## 2026-09-25 — Deploy the two-path release: migrations 20260925_001/002, market-sql-governor, market-python-sandbox, market-ai-orc (commit a5e11a4)

- Scope approved by the user: apply both migrations, deploy the three services, refresh the catalog and schema documentation, delete the temporary service, and sync the configuration. The user skipped the 10-question stress test, so no model run was made on `dev` after the deploy. The same code was tested with the real model on a read-only copy of the live data earlier the same day (entry below). It was also tested in local real-model reproductions.
- **Pre-deploy checks:**
  - No new Railway variable is needed. The code defaults `AI_MAX_OUTPUT_TOKENS=8000`, `AI_ENABLE_LOOKUP_FACT=true`, `AI_ENABLE_REQUEST_DATA=false` and `AI_MAX_REPAIR_ATTEMPTS=3` now apply to market-ai-orc: the model-facing `request_data` is off, and analysis data comes from `prepare_analysis_data`.
  - The sandbox SQLite schema did not change.
  - The migrations were rehearsed again on a scratch database with the job's own code.
- **Rollback references**, recorded before deploying: Governor `8682d991-986d-4c4d-8916-d3f9335dabb6`, sandbox `3cd9de07-73d0-4a73-8dc8-7f6fcba298a2`, orc `3e06e8d6-dfa5-4826-b7c2-28e4e7ac171b`.
  - The three roll back together: the orc's V2 spec tools need the sandbox's V2 parser and the Governor's catalog contract and scope lineage.
  - The migrations are additive: older versions ignore the new columns and inactive rows.
- **Temporary one-off service** `two-path-deploy-job` (`437fba8c-a6a8-4347-b1d5-79c53d75f671`):
  - It held reference variables only (`DATABASE_URL`, `MARKET_AI_ORC_API_KEY`, `PY_SANDBOX_API_KEY`, `SQL_GOVERNOR_API_KEY`), redacted from its output, and was deleted with `railway service delete`.
  - Deployment `b3a4370d-4217-48b4-8cb4-7b5c6137e814` applied the migrations (see `DATABASE_CHANGELOG.md`).
  - Deployment `746ed7b0-9fcf-47f5-9e52-16863544bce6` ran the smoke checks and the catalog/schema refresh.
- **Deployed** by local upload (`railway up <app> --path-as-root`, clean `git archive` of `a5e11a4`), one at a time. Each deployment reached `SUCCESS`:
  - Governor `293ba2e2-11e3-47f5-b272-16c43bea25e6`: clean start, Railway health check on `/ready` passed, and the dataset janitor ran.
  - Sandbox `beec8e84-d84a-4f33-89cd-f6497f1d6c7c`: `isolation_enforced=true`, 0 interrupted analyses, `/ready` 200.
  - Orc `3669447c-a5e4-4913-aead-f66131a97961`: clean start, `/ready` 200.
  - No variable, secret, volume, domain, schedule or restart policy was changed.
- **Smoke checks** over the private network (read-only, no model call):
  - `/ready` returned 200 on all three services, and the sandbox runtime reports `isolation_enforced=true`.
  - The Governor's new `POST /v1/catalog/dimension-values` (`IDX_Stock_Universe.Sector`) returned `VALUES_READY` with the 12 stored values, including the string `0`.
  - The sandbox read the catalog contract from the Governor and refused a deliberately wrong V2 spec with `INVALID_SPEC` / `UNKNOWN_COLUMN`. Refused specs are not stored.
- The job's output (both deployments) and the three new deployments' startup logs were scanned. There was no bearer token, OpenRouter key, DSN with a password, AWS key id, or presigned-URL signature. An in-process comparison against the three services' secret and URL variable values also found none.
- **Wrap-up:** the environment is back to 15 services. `railway config pull --force` left `.railway/railway.ts` unchanged, and `railway config plan` reports the configuration up to date.

## 2026-09-25 — Two-path live test: temporary job with the feature-branch stack (no deploy, no live write)

- Approved by the user as the live test of the two-path architecture (feature branch `claude/upbeat-dijkstra-iybq2f`, commit `1ae56c1`). A local run was not possible: this environment's egress allows HTTPS only, so PostgreSQL could not be reached through the existing TCP proxy.
- The temporary service `two-path-live-job` (`b6b512f7-5c97-49c5-9b27-9ab7182b528a`) ran once and was deleted afterwards.
  - Deployment `8b177cf0-00e8-4ab9-b3c8-149396e87716` did the run.
  - The first deployment `5e1090df-8ce4-4eb6-ac90-2e937fb2ae33` crashed before reading anything: the image's `/tmp` was not writable for the in-container PostgreSQL socket.
  - It held only references: `GOVERNOR_DATABASE_URL` (market-sql-governor), `CATALOG_DATABASE_URL` and `OPENROUTER_API_KEY` (market-ai-orc). It printed no secrets; a scan of the captured logs found none.
- **What it did:**
  - It read live PostgreSQL only in `default_transaction_read_only` sessions, with the Governor's least-privilege role and the orc catalog role. It copied into a PostgreSQL 16 cluster inside the container:
    - the five AI catalogs, `AI_research_catalog` and `AI_formula_reference`;
    - `IDX_Stock_Universe` (844 rows) and `IDX_Broker_Profile`;
    - `Price_Stock_Indonesia_IDX` from 2025-01-01 (329,394 rows) and `Feature_01_Stock_Daily` from 2025-06-01 (257,280 rows).
  - It applied migration `20260925_001` (subject metadata) to that copy only.
  - It ran market-sql-governor, market-python-sandbox (isolation enforced, all checks PASS) and market-ai-orc from the branch, with the dev model `deepseek/deepseek-v4.1-flash` (reasoning `high`) and the dev limits.
- **Results** (ground truth computed with SQL on the same copy):
  - All five sector questions of the 2026-09-24 stress test were answered `CALCULATION_VERIFIED`, and every number equals the ground truth:
    - counts per sector;
    - top 3 sectors by August return, after one return-basis clarification: Transportation & Logistic +14.02%, Basic Materials +12.72%, Infrastructures +8.99%;
    - top 5 banks over one month: BSIM +38.0%, BNBA +17.9%, BTPN +6.0%, NOBU +5.0%, BEKS +4.5%;
    - Energy vs Technology mean daily-return volatility: 0.03275 vs 0.03547;
    - banks vs property daily-return correlation since 1 January 2026: 0.7988 over 170 dates.
  - Before (2026-09-24, deployed code): 5 of 5 ended in `LIMITATION`, 251 s, $0.0721, 67% of prompt tokens cached.
  - After: 5 of 5 answered plus 1 clarification, 619 s, $0.0801, 87% cached.
- The environment is back to 15 services. `railway config plan` reports the configuration up to date. No service, variable, deployment of an existing service, database row, or schema was changed.
- **Follow-up: repair friction (local only; Railway was only read).**
  - In every live run the first `create_analysis_spec` call was rejected, and several spec rejections had no machine code.
  - A local reproduction with the dev model found the causes:
    - `const` was dropped from the provider schema;
    - OpenRouter closes a tool call cut off at `AI_MAX_OUTPUT_TOKENS` (3000, reasoning included) and still reports it completed;
    - the provider does not enforce the strict schema;
    - two parameters had defaults without a `default_id`;
    - `MEAN` and `AVG` were both in use;
    - the shared spec rules had no machine codes.
  - `OPENROUTER_API_KEY` was read in-process from the Railway variables and never printed.
  - Commits `6b6a52f` and `ab38c50` fix these:
    - a truncation guard (`MODEL_OUTPUT_TRUNCATED`);
    - an `AI_MAX_OUTPUT_TOKENS` code default of 8000. `dev` does not set the variable, so the new default takes effect at the next market-ai-orc deploy;
    - coded, actionable spec rejections.
  - The same six runs (five questions plus the Q3 follow-up) on a synthetic fixture:
    - `create_analysis_spec` repair calls: 14, then 8 after the first fix, then 6 after the second;
    - model iterations: 64, then 58, then 55;
    - cost: $0.094, then $0.084, then $0.090;
    - uncoded rejections: 8, then 0.
  - Every answer was `CALCULATION_VERIFIED`. The remaining rejections are ordinary model mistakes, each repaired in one turn.
- At that point the two-path code was merged to `main` without a deploy (deployed later the same day; see the release entry above). market-sql-governor, market-python-sandbox and market-ai-orc still ran the deployments recorded on 2026-09-24 (`8682d991`, `3cd9de07` and `3e06e8d6`, all `SUCCESS`, read back from Railway), and migrations `20260925_001` and `20260925_002` were not yet applied.

## 2026-09-24 — Stress test: 10 price and sector questions (no deploy, no change)

- Requested by the user before a full code review. The temporary job `stress-test-job` (`162aa153-fc78-4739-aecd-d4478f461e39`, deployment `e85a9fd1-6985-4a1d-bbc8-ba014487b241`) was deleted afterwards. It held references to `MARKET_AI_ORC_API_KEY` and `DATABASE_URL`, used the latter only in a read-only session, and printed no secrets.
- It sent 10 questions to `market-ai-orc` (`3e06e8d6`) in sequence, and read ground truth for the checkable ones from PostgreSQL. Totals: 481 s, $0.12476, 629,120 of 875,714 prompt tokens cached (0.718).
- **Results:**
  - Correct numbers, equal to the database: BBRI and TLKM closes on 2026-09-23 (`FACT`), BBCA +15.625% from the 1 July to the 31 August close (`CALCULATION_VERIFIED`), and TLKM's September average close 2,589.375 (`DATABASE_AGGREGATE`).
  - Appropriate behaviour: a clarification for "which sector is most attractive now", and a limitation for "technology versus IHSG", since IHSG is not in the data.
  - Not answered, all five sector questions: tickers per sector, top sectors by August return, top 5 banks by one-month change, energy versus technology volatility, and banks versus property correlation.
- **Why the sector questions failed, from the orc, sandbox and Governor logs:**
  - Four ended with `LIMITATION` without calling `create_analysis_spec`. One called it once; the orc argument validation refused the call, and the model did not retry.
  - The Analysis Spec cannot express a sector-filtered universe (only `ALL_IN_SOURCE` or a ticker list) or a per-sector output grain.
  - The model has no path to enumerate a sector's tickers: datasets never reach it, previews are 20 rows, and `lookup_fact` takes at most 5 entities.
  - The answers say the work "was not run yet" rather than that the path is unsupported.
- **Data note:** `IDX_Stock_Universe` has 3 tickers whose `Sector` is the string `0`.
- No service, variable, or data was changed. `railway config plan` reports the configuration up to date; the environment is back to 15 services.

## 2026-09-24 — Deploy the PoC fixes: sandbox intent dates and universe, warm-up remedy, cache-friendly final re-ask (commit 9085ee7)

- Scope approved by the user: fix the defects found by the Research AI PoC, and act on the structured-final cache miss (F.2). Local suites: sandbox 225 (19 new), orc 383.
- **Sandbox** (`1614b9c`):
  - Day-level date ranges are read as one period: "1 Juli sampai 31 Agustus 2026", "July 1 to August 31, 2026", "1-15 Juli 2026", "sejak 3 Maret 2026", and single days.
  - Outcome horizons ("dalam 5 hari … berikutnya") and a move "dalam sehari" are no longer taken for the analysis period.
  - "tiap/setiap/every/each saham" means each named ticker when tickers are named.
  - An `INSUFFICIENT_WARMUP_HISTORY` refusal now names the entities and a `suggested_from` estimated from their own trading density, and offers `EXCLUDE_TICKERS`. The gate stays strict.
- **Orc** (`9085ee7`): the first re-ask for the final JSON is sent exactly like a tool turn: same tools, no `text.format`, tools not offered. Only an invalid answer, or a tool call there, falls back to the strict schema.
  - Evidence: OpenRouter's endpoint list shows Relace (tools, but no `response_format` or `structured_outputs`). A local probe with the production prefix gave these results:
    - Strict final turn: moved provider 6/6.
    - Tools kept with `tool_choice: "none"`: definitions dropped, provider moved 3/3.
    - Tool-turn-shaped re-ask: stayed on Relace 5/5 with about 93% cached and a valid JSON 5/5.
- **Rollback references:** sandbox `3d38acaf-eff8-43f8-9f36-2319af6c7f8f`, orc `c79aac06-dc7b-4c76-9b61-2f1e18f2c1c3`.
- **Deployed** by local upload (`git archive` of `9085ee7`). Both reached `SUCCESS`:
  - Sandbox `3cd9de07-73d0-4a73-8dc8-7f6fcba298a2` (`isolation_enforced=true`, `/ready` 200).
  - Orc `3e06e8d6-dfa5-4826-b7c2-28e4e7ac171b` (`/ready` 200).
  - No variable changed.
- **Live verification:** the temporary job `fix-verify-job` (`0a677eb3-55b2-47c0-9c53-3e8608d32de1`, only a reference to `MARKET_AI_ORC_API_KEY`, deleted afterwards) re-ran the two PoC requests that had failed, with the exact same wording, plus the z-score request.

  | Run | Before | After | Calls | Cached / prompt | Cost |
  |---|---|---|---|---|---|
  | poc-2 custom formula (upper-shadow ratio, BBCA and BBRI, "1 Juli sampai 31 Agustus 2026") | `LIMITATION`, spec refused 15 times | `ANSWER`, `CALCULATION_VERIFIED`, gate `ANNOTATED`; last values on 2026-08-31: BBCA 0.2883, BBRI 0.1964 | 14 | 378,368 / 423,786 (0.893) | $0.02370 |
  | poc-3 event study (fall over 7% in a day, 5-day forward return, 2025-01-02 to 2026-07-31) | `LIMITATION`, no spec attempted | `ANSWER` (details below) | 15 | 401,280 / 432,582 (0.928) | $0.02922 |
  | z-score, 3 tickers, 3 months | `CALCULATION_VERIFIED` | `CALCULATION_VERIFIED`, gate `PASSED` | 10 | 151,552 / 177,887 (0.852) | $0.00796 |

  - poc-3 details:
    - Research Governor `APPROVED` (`HISTORICAL_PATTERN`, H1).
    - The first analysis was `FAILED` (`CALCULATION_MISMATCH`, caught by the validator); the second was `PASS` / `CALCULATION_VERIFIED`, evidence `PARTIALLY_SUPPORTED` / `PATTERN`.
    - 8,048 events against a baseline of 300,168 observations. Mean 5-day forward return +0.519% against +0.617%, delta −0.097 pp, CI95 −0.445 to +0.251. So the pattern was not better than the baseline, and the answer said so.
  - **Caching:** every run kept one static prefix (`distinct_static_prefixes=1`) and one provider for all its calls (Together, Together, Relace), per OpenRouter's generation records.
    - The final re-ask now reuses the cache. In the z-score run, the re-ask after a prose draft had 24,064 of 25,723 prompt tokens cached; the same turn had 0 cached before this fix.
    - The earlier runs had cache ratios of 0.700 and 0.752.
- The job's output and the orc logs were scanned: no bearer token, OpenRouter key, or DSN with a password. `railway config plan` reports the configuration up to date; the environment is back to 15 services.

## 2026-09-24 — Deploy market-ai-orc prompt-caching-aware model calls (commit 73b3c4e)

- Scope approved by the user: the model-call layer of `market-ai-orc` only, keeping the OpenRouter Responses API.
  - Every call of a run sends `session_id` = `request_id`.
  - Usage now includes cached and cache-write tokens, fresh tokens, cost, latency, and a static-prefix fingerprint per call, with a run summary.
  - No custom prompt cache. `market-ai-backend` was not changed.
  - Orc suite: 382 passed.
- **Verified against OpenRouter documentation** (prompt-caching and usage-accounting pages):
  - `session_id` in the body is accepted by both the Chat and Responses APIs and becomes the sticky-routing key.
  - DeepSeek caching is implicit, and a cache read is billed at 0.1x input.
  - Responses reports cache use in `usage.input_tokens_details`, and `usage.cost` is always present.
  - The Responses body carries no `provider` field. The serving provider comes from `GET /api/v1/generation?id=<provider_response_id>`.
- Rollback reference: orc `7fe7f1f6-0adf-4dd5-b118-4aa01b99d51d`. Deployed `c79aac06-dc7b-4c76-9b61-2f1e18f2c1c3` by local upload (clean `git archive` of `73b3c4e`); it reached `SUCCESS` with `/ready` 200. No variable changed.
- **Live PoC:** the temporary job `cache-poc-job` (`292d969e-90ab-4db5-861d-85552c285bee`, only a reference to `MARKET_AI_ORC_API_KEY`, deleted afterwards) ran `cache-poc-1`, "Hitung z-score rolling 20 hari … BBCA, BBRI, TLKM … 3 bulan terakhir". Result: `ANSWER`, `CALCULATION_VERIFIED`, gate `PASSED`, 8 model calls, 7 tool calls, 107.5 s. Per call, from the orc logs and OpenRouter's generation records:

  | Call | Prompt | Cached | Fresh | Completion | Cost (USD) | Provider | Prefix |
  |---|---|---|---|---|---|---|---|
  | 1 | 10,841 | 0 | 10,841 | 101 | 0.00102114 | Relace | `6078453d` |
  | 2 | 12,090 | 10,752 | 1,338 | 254 | 0.00033149 | Relace | `6078453d` |
  | 3 | 15,378 | 12,032 | 3,346 | 837 | 0.00078608 | Relace | `6078453d` |
  | 4 | 16,355 | 15,360 | 995 | 419 | 0.00041634 | Relace | `6078453d` |
  | 5 | 17,284 | 16,640 | 644 | 499 | 0.00043227 | Relace | `6078453d` |
  | 6 | 20,483 | 17,152 | 3,331 | 1,833 | 0.00127901 | Relace | `6078453d` |
  | 7 | 23,884 | 20,480 | 3,404 | 751 | 0.00082863 | Relace | `6078453d` |
  | 8 (structured final) | 15,727 | 0 | 15,727 | 803 | 0.00143208 | DekaLLM | `ad094799` |

  - Totals: 132,042 prompt tokens, of which 92,416 cached (ratio 0.6999), 39,626 fresh and 5,497 completion; cost $0.00652703; average latency 12.4 s.
  - Every call carried the same `session_id`, and OpenRouter recorded it on each generation. Calls 1–7 had a byte-identical static prefix and stayed on one provider.
  - `cache_write_tokens` was 0 on every call; DeepSeek endpoints report no cache writes.
- **Baseline for comparison:** the same prompt before this change (`poc-1-standard`, orc `7fe7f1f6`, no `session_id`), looked up in OpenRouter's generation records.
  - 7 calls: 114,506 prompt tokens, 86,060 cached (ratio 0.7516), cost $0.00560759.
  - Calls 1–6 stayed on Relace through OpenRouter's default conversation-hash stickiness, since the first system and user messages are stable within a run. The last call went to OpenInference.
  - **Conclusion:** in this single-sample comparison, `session_id` did not measurably raise the cache ratio. Excluding the final call, the ratio is 0.795 with `session_id` and 0.771 without, which is within run-to-run variation. What it adds is explicit stickiness from the first call and session grouping in OpenRouter's logs.
- **Cache miss, evidenced and not fixed:** in both runs, and in a local probe, the final call lost the cache.
  - It is the structured-final turn: the model drafted prose on a tool turn, so the orchestrator asks again with tools withdrawn and a strict `text.format` JSON schema.
  - That changes the static prefix (the fingerprint differs). With `provider.require_parameters=true`, it also moved to another provider, presumably one that supports structured outputs, so sticky routing could not apply.
  - In `cache-poc-1` that single call carried 40% of the fresh prompt tokens and 22% of the cost.
  - Changing it touches structured output and tool choice, which the user excluded from this change. It is reported for a separate decision.
- No other service, variable, or schedule was changed. `railway config plan` reports the configuration up to date.

## 2026-09-24 — Deploy the Research AI release: Research Governor, event studies, evidence assessment, claim gate, run audit (commit bc589d3)

- Scope approved by the user: apply migration `20260924_004`, deploy `market-sql-governor`, `market-python-sandbox` and `market-ai-orc`, set the 3x capacity limits and `RESEARCH_AUDIT_DATABASE_URL`, and run the live PoC.
  - Local suites on the release tree: sandbox 206, orc 373, Governor 135 passed. The migration was rehearsed on a scratch database.
  - `origin/main` had no new commits, so the release is the feature branch fast-forwarded.
- **Pre-deploy checks:**
  - OpenRouter's models API reports `deepseek/deepseek-v4.1-flash` with a 1,048,576-token context window, so `AI_MAX_CONTEXT_TOKENS=500000` is below the model limit. Listed pricing is $0.14/M input, $0.42/M output, and $0.0042/M cache read.
  - No caller of `/v1/agent/run` exists in the repository besides the temporary jobs. The private network has no proxy timeout, and the job's HTTP timeout is 1900 s, above `AI_MAX_ANALYSIS_SECONDS`.
  - A SQLite file in the old schema, written by the code at `ca10721`, opened cleanly with the new code: columns were added, old rows read back, and reopening was idempotent.
- **Rollback references**, recorded before deploying: Governor `ddd1d851-a0c8-4dc8-9361-e2333018db7a`, sandbox `d7f57f10-6fc1-4bee-a231-a76b3716c3d5`, orc `7f463b78-19a9-4b15-8e30-5b0d8b8254ea`.
  - The orc v3 tool contract, sandbox research fields, and Governor units ship together, so these three roll back together.
  - Rolling back does not remove `AI_research_run_audit`. With an older orc, the table simply stops receiving rows.
- **Variables**, all set with `--skip-deploys` before deploying:
  - `market-python-sandbox`: `PY_SANDBOX_MAX_ANALYSES_PER_REQUEST=18`, `PY_SANDBOX_MAX_SPECS_PER_REQUEST=30`, `PY_SANDBOX_MAX_CPU_SECONDS_PER_REQUEST=3600`. These were code defaults (6, 10, 1200) and are now explicit.
  - `market-ai-orc`:
    - `AI_MAX_TOOL_CALLS` 20 → 60.
    - `AI_MAX_TOOL_ITERATIONS` 20 → 60.
    - `AI_MAX_CONTEXT_TOKENS=500000` (was the code default 64000).
    - `AI_MAX_ANALYSIS_SECONDS=1800` (was the code default 600).
    - `RESEARCH_AUDIT_DATABASE_URL` (secret): a reference template, `postgresql://market_ai_orc:${{MARKET_AI_ORC_DB_PASSWORD}}@${{Postgres.RAILWAY_PRIVATE_DOMAIN}}:5432/${{Postgres.PGDATABASE}}`. It is the same template as `CATALOG_DATABASE_URL`: the `market_ai_orc` login now also holds the INSERT-only `market_ai_research_audit_writer` role. A read-back confirmed it resolves, equals the catalog DSN, and has no unresolved reference. Its value was never printed.
- **Deployed** by local upload (`railway up <app> --path-as-root`, clean `git archive` of `bc589d3`), one at a time. Each deployment reached `SUCCESS`:
  - Governor `8682d991-986d-4c4d-8916-d3f9335dabb6`.
  - Sandbox `3d38acaf-eff8-43f8-9f36-2319af6c7f8f`. Startup logged `isolation_enforced=true`, 0 interrupted analyses, and `/ready` 200.
  - Orc `7fe7f1f6-0adf-4dd5-b118-4aa01b99d51d`, `/ready` 200.
- **Temporary one-off service** `research-deploy-job` (`8a6534be-787a-4971-8666-6de0b60c9537`): reference variables only (`DATABASE_URL`, `MARKET_AI_ORC_API_KEY`, `PY_SANDBOX_API_KEY`, `SQL_GOVERNOR_API_KEY`), redacted from its output, deleted afterwards. Deployments:
  - `539a778e` applied migration 004. Its own read-back query failed on a wrong column name after the commit.
  - `22721042` read back read-only.
  - `0618e56d` ran the live PoC.
  - `6b682dc0` ran the controlled event study and the catalog/schema sync.
- **Live PoC** (§71 of the Research AI spec) over the private network with the real model, reported as observed:

  | Run | Result | Tool calls | Tokens | Time | Note |
  |---|---|---|---|---|---|
  | poc-1 standard: "z-score rolling 20 hari … BBCA, BBRI, TLKM … 3 bulan terakhir" | `ANSWER`, `CALCULATION_VERIFIED`, gate `PASSED` | 7 | 119,253 | 113.5 s | 186/186 values recalculated and matching; experiment `RETAINED`; audit row written |
  | poc-2 custom formula: upper-shadow ratio 10-day mean, BBCA and BBRI, "dari 1 Juli sampai 31 Agustus 2026" | `LIMITATION` | 15 | 545,324 | 140.1 s | **Failed.** Every spec was refused `ANALYSIS_SPEC_MISMATCH` by the sandbox intent review, for two reasons. First, "tiap saham" is read as an all-stocks universe. Second, "1 Juli sampai 31 Agustus 2026" is read as August 2026 only. The model correctly did not bend the user's parameters. |
  | poc-3 event study: "turun lebih dari 7% dalam sehari … 5 hari … 2 Januari 2025 sampai 31 Juli 2026" | `LIMITATION` | 5 | 126,494 | 48.8 s | **Not exercised.** The model never called `create_analysis_spec` and answered with a limitation after catalog discovery. |
  | poc-4 ambiguous: "Saham bank mana yang bagus sekarang?" | `CLARIFICATION` | 3 | 49,933 | 32.6 s | Asked for the criterion, period and universe; disclosed that fundamentals are unavailable |
  | poc-5 pairwise correlation across all IDX stocks in 2025 | `LIMITATION` | 4 | 71,483 | 29.5 s | Refused by spec validation (`INVALID_SPEC`: a pairwise output needs a TICKERS universe), not by the Research Governor. The model did not propose a bounded universe. |

- **Controlled checks** through the live services (direct API, labelled as injected; they test the gates, not the model):
  - An approved z-score spec for BBCA/BBRI/TLKM received a Governor dataset of 258 rows, `COMPLETE`. The manifest reports `unit: null` for `close`, because `AI_column_catalog.unit` is empty for the price table, so the unit preflight has nothing to compare yet.
  - Injected wrong window 10 → `FAILED`, `CALCULATION_MISMATCH` on 186/186 values, diagnosis `PARAMETER_DIFFERS` (`window`, spec 20, values match 10), evidence `INVALID`.
  - The correct window 20 → `PASS`, `CALCULATION_VERIFIED`, evidence `SUPPORTED`/`OBSERVATION`.
  - A `HISTORICAL_PATTERN` research spec without an event study → Research Governor `REPLAN_REQUIRED`, `MISSING_BASELINE_DEFINITION`, `next_action=REVISE_SPEC`, with the 18-experiment and 4-hypothesis budget shown.
  - **Controlled live event study** (`poc-direct-event`), for all IDX stocks from 2025-01-02 to 2026-06-30: a 20-day z-score below −1.5, followed by the 5-day forward return from the next open.
    - Spec `APPROVED`; the Research Governor reserved experiment 1/18 and hypothesis 1/4. Resubmitting the same spec replayed the same `spec_id`, so no budget was consumed twice.
    - First data request, one unfiltered 602-day range: the SQL Governor answered `NEEDS_NARROWING`/`DATE_RANGE_TOO_LARGE`, because unfiltered requests are capped at 400 days.
    - Split into two requests and bound as one logical input: 201,031 + 108,740 rows, 843 tickers, both `COMPLETE`.
    - The sandbox preflight refused it `INSUFFICIENT_WARMUP_HISTORY`. 26 thinly traded tickers had fewer than 19 observations inside the recommended request range (from 2024-11-23). Their remedy text, "request data from 2024-11-23 or earlier", repeats the range already requested.
    - A retry starting 90 days earlier (199,039 + 160,495 rows) still left 2 tickers (CSMI, TFCO) short and was refused the same way.
    - Evidence was `INSUFFICIENT_EVIDENCE` both times; no finding was produced. The event-study recalculation itself was therefore not reached on live data; it is covered by the local fixture tests only.
    - The two attempts ran as analyses 1 and 2 of that request's 18.
- **Run audit:** each of the 5 orc runs wrote one `AI_research_run_audit` row through the `market_ai_orc` login.
  - poc-1 carries its experiment (code hash, dataset id and checksum), budget, and `sandbox_summary_status=REPORTED`.
  - The other four carry `NOT_USED`, because no analysis ran. Refused specs are not stored by the sandbox, so they are visible only in logs, not in the audit row.
- **Catalog and schema refresh** (deployment `6b682dc0-2159-4aa0-9232-b74a94998e97`):
  - `scripts/sync_database_catalog.py` reported `Catalog reconciled: 628 physical columns, 21 updated`, the physical facts of the new table's columns. `scripts/sync_database_schema.py` reported `Synchronized 38 tables`.
  - The regenerated `DATABASE_SCHEMA.md` came back as gzip+base64 chunks and was verified locally by sha256 (`37347e25…`, 153,842 bytes). Its only changes are timestamp drift and the new `AI_research_run_audit` section.
- Deleted `research-deploy-job` with `railway service delete`; the environment is back to its 15 services. Then ran `railway config pull --force`: `.railway/railway.ts` now preserves the new variable names (three `PY_SANDBOX_MAX_*`, `AI_MAX_ANALYSIS_SECONDS`, `AI_MAX_CONTEXT_TOKENS`, `RESEARCH_AUDIT_DATABASE_URL`), without values. `railway config plan` reported the configuration up to date.
- The job's output (all six deployments) and the three new deployments' logs were scanned: no bearer token, OpenRouter key, DSN with a password, AWS key id, or presigned-URL signature. A direct in-process comparison against the 13 secret and URL variable values of the three services also found none of them in any log. The 64-hex strings in the logs are sha256 checksums (spec, code, dataset, query).
- No other service's variables, source, schedule, volume, domain, or restart policy was changed.

## 2026-09-24 — Deploy the fact/analysis split: Governor dataset-only + lookup, sandbox v2 validation gate, orc answer gates (commit 1361644)

- Scope approved by the user: one joint release of migration 009, `market-sql-governor`, `market-python-sandbox` v2, and `market-ai-orc`. Before deploying, `origin/main` was found eight commits ahead (the `AI_research_catalog` and `AI_formula_reference` rollouts, deployed to `market-ai-orc` as `89ed23b6` at 09:17 UTC). The feature branch merged `origin/main` cleanly as `1361644`, so the release keeps those features. The orc, Governor, and sandbox suites pass on the merged tree (363, 118, 164 tests; local PostgreSQL 16 for the database tests). Governor and sandbox code was not touched by those main commits.
- Rollback references, recorded before deploying: Governor `92aaf788-b147-4437-88ec-6d36bbad6e96`, sandbox `4310a9f6-43e6-438f-b55e-8155155beeaf`, orc `89ed23b6-3ff5-481e-96af-733888dae794`. Note: Governor v2 no longer returns inline rows and sandbox v2 requires a `spec_id`, so these three must be rolled back together.
- Deployed by local upload (`railway up <app> --path-as-root`, clean `git archive` of `1361644`). Each deployment reached `SUCCESS`:
  - Governor `ddd1d851-a0c8-4dc8-9361-e2333018db7a`.
  - Sandbox `d7f57f10-6fc1-4bee-a231-a76b3716c3d5`. Startup logged `isolation_enforced=true` with no interrupted analyses.
  - Orc `7f463b78-19a9-4b15-8e30-5b0d8b8254ea`.
  - Each service answered `200` on `/ready`, both from Railway's health probe and over the private network.
- No variable, secret, volume, domain, schedule, or restart policy of these services was changed. The orc keeps `AI_MAX_TOOL_CALLS=20` and `AI_MAX_TOOL_ITERATIONS=20`; the sandbox and Governor run on their code defaults.
- The temporary one-off service `split-deploy-job` (`836e701d-926c-4ffe-b0c0-f50487185e20`) held reference variables only (`DATABASE_URL`, `MARKET_AI_ORC_API_KEY`, `PY_SANDBOX_API_KEY`, `SQL_GOVERNOR_API_KEY`) and redacted them from its output. It ran four jobs:
  - Migration 009 (see `DATABASE_CHANGELOG.md`).
  - The live acceptance run below.
  - Three read-only catalog inspections, in `default_transaction_read_only` sessions.
  - The first migration run's output was never collected by Railway's log pipeline, and later runs lost some long lines. The job now waits before exiting and prints one row per line.
- Live acceptance over the private network (deployment `5a71843e-74e9-488c-9f35-90952fe12551`):
  - **Governor, direct calls:**
    - A small `/v1/query` returns `DATASET_READY` with no `rows` field.
    - `/v1/lookup` VALUE (BBCA close on 2026-09-23) and AGGREGATE (SUM of volume, 2026-09-15..23) both return `FACTS_READY` and equal the PostgreSQL values.
    - Five refusals behave as specified:
      - too many values → `LOOKUP_TOO_LARGE` / `USE_ANALYSIS_PATH`;
      - an `order_by` field → `LOOKUP_NOT_ALLOWED` / `USE_ANALYSIS_PATH`;
      - STDDEV → `LOOKUP_NOT_ALLOWED` / `USE_ANALYSIS_PATH`;
      - a table outside the allowlist → `TABLE_NOT_APPROVED`;
      - an unknown column → `UNKNOWN_COLUMN`.
  - **Sandbox:** `/v1/runtime` reports `isolation_enforced=true` and validator checks `validator_seccomp_filter_active`, `validator_socket_inet_denied`, `validator_uid_non_root`.
  - **Orc, real model** (`deepseek/deepseek-v4.1-flash`); six runs, every one HTTP 200 with `number_provenance.unsupported=[]`. Every first data call was on the intended path. Results:

    | Run | Result | Tool calls | Time | Note |
    |---|---|---|---|---|
    | "Berapa harga close BBCA kemarin?" | `ANSWER`, `FACT` | 4 | 43.5 s | |
    | "total volume BBCA minggu ini" | `ANSWER`, `DATABASE_AGGREGATE` | 4 | 13.1 s | Discloses the partial week |
    | BBCA–BBRI daily-return correlation, Jun–Aug 2026 | `ANSWER`, `CALCULATION_VERIFIED`, gate `PASSED` | 6 | 26.2 s | |
    | "average of the preview rows, without Python" | `ANSWER`, `DATABASE_AGGREGATE` | 7 | 27.1 s | Refused to compute from preview rows; used a lookup AVG |
    | 20-day rolling z-score, 5 tickers, 3 months | `ANSWER`, `CALCULATION_VERIFIED`, gate `PASSED` | 6 | 30.7 s | |
    | RSI(14) < 30 + bullish engulfing, all IDX | `LIMITATION`, `UNVERIFIED_EXPLORATORY`, gate `ANNOTATED` | 12 | 44.2 s | Custom engulfing rule; `PATH_DEPENDENT_WARMUP`, `STALE_LATEST_OBSERVATION`; tools withdrawn at `CONTEXT_BUDGET` after 251k cumulative tokens |

- The logs of the three services and of the job were scanned for bearer tokens, provider keys, DSNs with credentials, bucket secrets, and presigned-URL signatures: no match. The Governor logs `sql_governor_lookup` events with fact ids and a values hash, not the values.

## 2026-09-24 — Deploy market-ai-orc with AI_formula_reference FORMULAS support (commit cb97fac); clear its watchPatterns

- Added `FORMULAS` support to `market-ai-orc` (`catalog.py`/`catalog_rows.py`/`orchestrator.py`), mirroring the `RESEARCH` rollout: `discover_catalog`'s `formula_catalog` count, `get_catalog_details`'s `FORMULAS` section with `formula_ids` narrowing, and `AI_formula_reference` in `read_catalog_rows`. 253 tests pass locally, 60 skipped (no disposable Postgres). Bumped the FastAPI app version to `0.2.0`.
- Recorded rollback reference before deploying: the previously active deployment was `9db01c3c-7392-4e99-9741-822ce0a4274c`.
- **Deploy incident:** three consecutive `railway up` attempts (deployments `4aa76438`, `7ad8b624`, `3a14cb15`), each with genuinely new commits, were marked `SKIPPED` by Railway with reason "No changes to watched files" — a known Railway CLI/platform issue (railwayapp/cli#787) where the `build.watchPatterns` change-detection misfires for local-upload (`railway up`) deploys, not just the git-push-triggered deploys it's meant for. Two attempts to clear `watchPatterns` via `railway config apply --yes` reported success but never actually changed the live value (confirmed by `railway config plan` still showing drift immediately after). The user cleared `market-ai-orc`'s **Watch Paths** directly from the Railway dashboard (Settings → Build), which the CLI could not do — this is what actually fixed it. Deployment `89ed23b6-3ff5-481e-96af-733888dae794` then built and deployed normally and reached `Online`.
- `watchPatterns` is deliberately left cleared (not restored) for this service: `market-ai-orc` has `source: null` (no GitHub source, local-upload only, confirmed via `railway service list --json`), so the pattern was never actually filtering anything meaningful — it only exposed this false-skip bug. `.railway/railway.ts` now reflects this (no drift after `railway config pull --force` + `railway config plan`).
- Verified all three tools end-to-end against live dev data (see `DATABASE_CHANGELOG.md` for exact results), using a temporary service (`orc-verify-2`, deleted after) that imported the identical deployed `app/` code and called it directly through `CATALOG_DATABASE_URL` — not a synthetic/disposable database.
- The three `Tool_Catalog` rows for these tools were extended (`FORMULAS` support added, `runtime_commit` stamped) in the same task at the user's explicit request; they were already `is_active=true` from the earlier `AI_research_catalog` rollout. See `DATABASE_CHANGELOG.md` migration `20260924_003`.
- No other service's schedule, source, variables, secrets, restart policy, domain, or database reference was changed. No production environment was touched.

## 2026-09-24 — Deploy market-ai-orc with AI_research_catalog RESEARCH support (commit aa7b231)

- Reviewed [PR #1](https://github.com/rednightt33/saniti/pull/1) (`codex/ai-research-catalog`, opened by the ChatGPT Codex connector) line by line and applied its `market-ai-orc` code changes directly to `main` at the user's explicit request, rather than merging the PR branch: `orchestrator.py` prompt update, `catalog.py`/`catalog_rows.py` RESEARCH-section support in `discover_catalog`, `get_catalog_details`, and `read_catalog_rows`. 249 tests passed locally, 58 skipped (no disposable Postgres), matching the PR's own report.
- Recorded rollback reference before deploying: the previously active deployment was `a292e767-071f-4afb-8978-8e93901c34c6`.
- Deployed via `railway up ./apps/market-ai-orc --path-as-root --service market-ai-orc` (local upload — this service has no GitHub source, so the `main` push alone does not deploy it). New deployment `9db01c3c-7392-4e99-9741-822ce0a4274c`, reached `Online`; startup logs show a clean `Uvicorn running` and a `200` on `/ready`.
- Verified all three tools end-to-end against live dev data (see `DATABASE_CHANGELOG.md` for exact results), using a temporary service (`orc-verify`, deleted after) that imported the identical deployed `app/` code and called it directly through `CATALOG_DATABASE_URL` (`${{market-ai-orc.CATALOG_DATABASE_URL}}`, the real read-only `market_ai_orc` login) — not a synthetic/disposable database.
- The three `Tool_Catalog` rows for these tools were activated (`is_active=true`) in the same task at the user's explicit request; see `DATABASE_CHANGELOG.md` migration `20260924_002`.
- PR #1 is superseded by this direct-to-main deployment; see its closing comment for the exact commit.
- **Sandbox network constraint** (context for the temporary-service workaround, same as the earlier pgweb deployment): this session's outbound network supports plain HTTPS request/response only; raw-TCP and WebSocket-based paths to Postgres are blocked by this environment's egress policy. All Railway CLI operations used here (`railway up`, `railway add`, `railway domain`, `railway logs`) are plain HTTPS.
- No other service's schedule, source, variables, secrets, watch path, restart policy, domain, or database reference was changed. No production environment was touched.

## 2026-09-23 — Deploy market-python-sandbox and the Python analysis tools (81475ae)

- **Governor dataset-access key:** generated a new 64-hex `SQL_GOVERNOR_DATASET_ACCESS_KEY` on `market-sql-governor`. It was set through stdin with `--skip-deploys` and never printed. A check confirmed it differs from `SQL_GOVERNOR_API_KEY`.
- **New resources** (user-approved pinned IaC plan, plan file sha256 `729913afd92dfa9d…`, change set `sha256:1299b527…`; 2 safe creates, 0 changes, 0 destroys):
  - Volume `market-python-sandbox-data` (`853e57c0-eb4c-4b48-a4ce-6bd7ffe282d8`, region `sfo`, mounted at `/data`).
  - Service `market-python-sandbox` (`225b1be1-d7f5-4b2d-a4c7-052eb53af818`):
    - Dockerfile build; start command `uvicorn app.main:create_app --factory` on `:8080`.
    - Health check `/ready` (300 s), which returns `503` unless the isolation self-test passed.
    - One replica in `sfo`, restart `ALWAYS`.
    - Private only (`market-python-sandbox.railway.internal:8080`), no public domain, no GitHub source. It is deployed by local upload.
- **`market-python-sandbox` variables:**
  - `PORT=8080` and `SQL_GOVERNOR_URL=http://market-sql-governor.railway.internal:8080`.
  - `SQL_GOVERNOR_DATASET_ACCESS_KEY` is a reference to `${{market-sql-governor.SQL_GOVERNOR_DATASET_ACCESS_KEY}}`.
  - `PY_SANDBOX_API_KEY` is a new 64-hex secret, set through stdin.
  - No `PY_SANDBOX_*` limit is overridden, so the code defaults apply.
  - The service holds no PostgreSQL or bucket credential.
- **`market-ai-orc` variables** (with `--skip-deploys`):
  - `PY_SANDBOX_URL=http://market-python-sandbox.railway.internal:8080`.
  - `PY_SANDBOX_API_KEY` is a reference to `${{market-python-sandbox.PY_SANDBOX_API_KEY}}`.
  - `AI_MAX_TOOL_CALLS=20` (previously the default of 12), approved by the user with this deployment.
- **Deployments** (each reached `SUCCESS`):
  - Governor `92aaf788-b147-4437-88ec-6d36bbad6e96` (dataset manifest/access endpoints, tombstones). Rollback: `4c66fb87-fbe2-481a-b412-067c0d61de14`.
  - Sandbox `4310a9f6-43e6-438f-b55e-8155155beeaf`. Its startup log records `isolation_enforced=true` and pinned library versions (Python 3.12.14, numpy 2.4.6, pandas 3.0.6, polars 1.44.2, pyarrow 25.0.1, duckdb 1.5.5, scipy 1.17.1, statsmodels 0.15.0, matplotlib 3.11.2, TA-Lib 0.8.1).
  - market-ai-orc `a292e767-071f-4afb-8978-8e93901c34c6`: the same watch-path-compatible staging upload as before. Rollback: `44e44fdf-330b-4fb0-b6f5-83e4fde81c10`, or unset `PY_SANDBOX_URL` to unregister the two analysis tools.
- **Temporary one-off service `sandbox-acceptance-job`** (`0e909127-145c-4b86-a87f-ed4f69322523`, deployment `c6cf05e3-16a5-43c0-b328-8bda4e8ef1b4`):
  - Reference variables only, restart `NEVER`.
  - It applied migration 008 (see `DATABASE_CHANGELOG.md`) and ran the live acceptance over the private network.
  - It was deleted afterwards; the service list confirms 15 services and no temporary job.
- **Live acceptance** (real OpenRouter model, real data):
  - A. "RSI(14) < 30 and latest-bar bullish engulfing": `COMPLETED`/`ANSWER`, 127 s, 9 tool calls. The screen covered 841 of 844 tickers. 53 matched RSI < 30 and 12 matched bullish engulfing. The answer honestly reported 0 tickers matching both. It disclosed that RSI smoothing was seeded at the start of the extracted window.
  - B. "Latest close > 2 SD above the 20-day rolling mean": `COMPLETED`/`ANSWER`, 112 s, 5 tool calls. It found 42 tickers, using sample SD (ddof=1). The full table is a `result_id`.
  - C. "Daily returns, last 10 trading days, all stocks": `COMPLETED`/`ANSWER`, 330 s, 8 tool calls. It covered 842 tickers × 10 dates, and a model-chosen cross-check against `return_1d_pct` found 0 mismatches.
  - Observation: the answers disagree on the newest date. A and C say 2026-09-22, while B's dataset contains 2026-09-23 rows. The run did not establish whether this came from the model's chosen window, source freshness at extraction time, or Feature 01 lag. The architecture addendum's reference-date and actual-scope validation targets this class of gap.
- **Direct checks:**
  - A 27,498-row dataset produced a full `TABLE` with a 50-row preview, in 709 ms.
  - An unknown dataset returned `DATASET_NOT_FOUND`; a malformed id returned `422`.
  - Sockets to PostgreSQL, the bucket endpoint, and the Governor from analysis code returned `FORBIDDEN_OPERATION`. Listing `/data` also returned `FORBIDDEN_OPERATION`.
  - Importing `psycopg` returned `FORBIDDEN_IMPORT`.
  - An over-allocation returned `MEMORY_LIMIT_EXCEEDED`, and `subprocess` returned `FORBIDDEN_OPERATION`.
  - An infinite loop returned `RUNTIME_LIMIT_EXCEEDED` at 120,039 ms. A healthy job completed afterwards.
  - Key separation: the orc API key on the access endpoint returned `401`, and the access key on `/v1/query` returned `401`.
- **Logs:** the Governor logged 15 `sql_governor_dataset_access` events and the sandbox logged 16 `sandbox_analysis` events. Neither service's logs contain presigned URLs, `X-Amz` parameters, bearer strings, or key values.
- Ran `railway config pull --force`. `.railway/railway.ts` now preserves the new orc variables (`PY_SANDBOX_URL`, `PY_SANDBOX_API_KEY`, `AI_MAX_TOOL_CALLS`) and the volume's live defaults, and the follow-up `railway config plan` reported `dev` up to date. No other service, domain, schedule, or source was changed.

## 2026-09-23 — Isolation probe for market-python-sandbox (temporary, deleted)

- **Why:** Before the sandbox was designed, a read-only probe checked which isolation primitives Railway containers allow. The Railway docs describe containers only as "non-privileged".
- **Temporary service:** `sandbox-isolation-probe` (`546162a2-7128-40e0-948a-de521cbe2be1`, deployment `b92eccc9-9b6c-424c-905f-33ca3245b6f6`, image `python:3.12-slim`, restart `NEVER`, no variables). It printed one JSON line and exited. It never printed environment values.
- **Results on `dev`:**
  - Kernel `6.18.5+deb13-cloud-amd64`, x86_64 (not gVisor). The container runs as root with capability set `0x800405fb` (Docker defaults without NET_RAW, MKNOD, and AUDIT_WRITE).
  - The runtime already applies its own seccomp filters (`Seccomp: 2`, 3 filters). cgroup is not writable. The limits are `memory.max` 24 GB, `cpu.max` 24 CPUs, and `pids.max` 1000.
  - Dropping to UID 65534 works. `/proc/1/environ` is unreadable to that user (`EACCES`), and `RLIMIT_AS` is enforced.
  - A process-level seccomp filter installs as non-root. It denies AF_INET, AF_INET6, and AF_NETLINK sockets and `execve`, while AF_UNIX stays allowed in the probe.
  - `unshare(CLONE_NEWNET)` as root returns `EPERM`, and `unshare(CLONE_NEWUSER|CLONE_NEWNET)` as non-root returns `EACCES`. **Network namespaces are not available.** Outbound TCP from the container works, and Railway has no egress firewall.
- **Cleanup:** The service was deleted with `railway service delete`. `railway config plan` reported `dev` up to date.
- The design recorded in `apps/market-python-sandbox/README.md` follows from these results: seccomp socket denial per analysis process, not a network namespace.

## 2026-09-23 — market-sql-governor: one-week dataset expiry and MIN/MAX on dates

- Railway buckets do not support lifecycle configuration: the storage-bucket docs list "Bucket lifecycle configuration" under "Not yet supported". Expiry is therefore done by the Governor's own janitor (`apps/market-sql-governor/app/janitor.py`).
  - It runs at startup and then every hour (`SQL_DATASET_CLEANUP_INTERVAL_SECONDS=3600`).
  - It deletes `datasets/ds_*/data.parquet` and `manifest.json` once the manifest's `expires_at` has passed.
  - Default retention is now one week (`SQL_DATASET_RETENTION_HOURS=168`). Both values are code defaults, so no Railway variable was added.
- Deployed commit `f2c4012` as `4c66fb87-fbe2-481a-b412-067c0d61de14`: `SUCCESS`, `/ready` `200`.
  - The first live janitor pass logged `sql_governor_dataset_cleanup datasets_seen=9 datasets_deleted=0 errors=0`, which proves bucket list and read work.
  - Datasets written before this change keep the 24-hour `expires_at` recorded in their manifests.
- Temporary one-off service `orc-mig007-job` (`72942e81-6cbf-48fa-af3c-1e6e638cfa05`, deployment `414b7d62-c82b-45c6-a480-d6af500106d4`) applied migration 007 and checked MIN/MAX live (see `DATABASE_CHANGELOG.md`). It was deleted afterwards, and `railway config plan` reported `dev` up to date.

## 2026-09-23 — Deploy market-sql-governor and request_data

- **New resources** (user-approved pinned IaC plan `sha256:c9e8e1bb…`: 2 creates, 0 changes, 0 destroys):
  - Bucket `market-sql-datasets` (`62b028ba-313f-4c6a-81b3-48a9645411c1`, region `sjc`).
  - Service `market-sql-governor` (`1a322795-4f93-4c51-a25e-5fcfc5ab4722`): Dockerfile build, `uvicorn app.main:create_app --factory` on `:8080`, health check `/ready` (which also checks the database), 1 replica in `sfo`, restart `ALWAYS`.
  - The service is private (`market-sql-governor.railway.internal:8080`) with no public domain. It has no GitHub source and no watch path; it is deployed by local upload.
- **`market-sql-governor` variables:**
  - `SQL_GOVERNOR_API_KEY` (64 hex characters) and `MARKET_SQL_GOVERNOR_DB_PASSWORD` were generated and set through stdin; they were never printed.
  - `GOVERNOR_DATABASE_URL` is a reference template: `postgresql://market_sql_governor:${{MARKET_SQL_GOVERNOR_DB_PASSWORD}}@${{Postgres.RAILWAY_PRIVATE_DOMAIN}}:5432/${{Postgres.PGDATABASE}}`.
  - `SQL_DATASET_BUCKET_{NAME,ENDPOINT,REGION,ACCESS_KEY_ID,SECRET_ACCESS_KEY}` reference `${{market-sql-datasets.*}}`.
  - `PORT=8080`. No `SQL_*` limit is overridden, so the code defaults apply.
- **`market-ai-orc` variables:** `SQL_GOVERNOR_URL=http://market-sql-governor.railway.internal:8080`, and `SQL_GOVERNOR_API_KEY=${{market-sql-governor.SQL_GOVERNOR_API_KEY}}`.
- **Temporary one-off services** (reference variables only, restart `NEVER`, deleted after use):
  - `orc-governor-setup` (`c54d2e20-947b-49ed-8867-19f9cbfaff53`, deployment `9f070d4a-1df1-42fe-a33e-6cdb67d96503`): migrations 005/006, login provisioning, privilege checks, and live calibration (see `DATABASE_CHANGELOG.md`).
  - `orc-acceptance-job` (`5931c9ca-b88e-40c5-8c55-60b55eb64563`, deployment `f01d48e9-8eb8-43f5-9399-edadcd14254b`): live acceptance tests over the private network.
- **Deployments:**
  - Governor `d8ae37a4-1321-4e89-8138-6abcfec4f850` (commit `0b0ba24`): `SUCCESS`, `/ready` returned `200`.
  - market-ai-orc `44e44fdf-330b-4fb0-b6f5-83e4fde81c10` (commit `0b0ba24`; the app code is identical to `f63bebc`): `SUCCESS`, `/ready` returned `200`.
  - Rollback references: market-ai-orc `b33d1736-1229-4ca1-b796-569b9df0a6f2`, or unset `SQL_GOVERNOR_URL` to unregister `request_data`.
- **Live acceptance** (real OpenRouter model, real data):
  1. "Ambil 20 latest daily close BBCA." → `COMPLETED`/`ANSWER` in 23 s with 4 tool calls. The Governor returned `INLINE_RESULT` (estimated scan 2,282 rows, 20 rows, 93 ms), and the answer lists the 20 real closes (2026-09-22 back to 2026-08-21).
  2. "Ambil historical price universe IDX … rolling correlation." → `COMPLETED` in 65 s.
     - The full-history request got `NEEDS_NARROWING`/`DATE_RANGE_TOO_LARGE` (3,186 days, limit 400 without a ticker filter).
     - The model revised the request and got `DATASET_READY`: 214,023 rows × 3 columns, 844 entities, `COMPLETE`, 530 KB Parquet in `market-sql-datasets`.
     - Its limitations state that rolling correlation was not calculated because no analysis tool exists.
  - Direct Governor checks: no bearer key returned `401`; an F02 × F03 join returned `REJECTED`/`PREAGGREGATION_REQUIRED`; a spec with a `sql` field returned `REJECTED`/`INVALID_REQUEST_SPEC`.
  - Governor logs carry the orc run `request_id` (for example `live-acceptance-1`).
- Ran `railway config pull --force`. `.railway/railway.ts` now includes the bucket, the service, and all preserved variables, and the follow-up plan reported `dev` up to date. No other service, domain, schedule, or source was changed.

## 2026-09-23 — market-ai-orc: AI_MAX_TOOL_ITERATIONS = 20

- At the user's request, set `AI_MAX_TOOL_ITERATIONS=20` on `market-ai-orc`. The code default is 8.
- Railway redeployed the same image as `b33d1736-1229-4ca1-b796-569b9df0a6f2`, which reached `SUCCESS` with a clean start and `GET /ready` `200`.
- `AI_MAX_TOOL_CALLS` stays at its default of 12, so a page-by-page catalog read now ends through the graceful paths instead of `MAX_ITERATIONS`: the tool-call budget (`TOOL_CALL_BUDGET`) or the context soft limit (`CONTEXT_BUDGET`), whichever comes first.
- Ran `railway config pull --force`. `.railway/railway.ts` now preserves `AI_MAX_TOOL_ITERATIONS`, and the plan reported `dev` up to date.

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
