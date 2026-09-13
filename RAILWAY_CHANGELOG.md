# Railway changelog

This file records intentional changes to the Railway project. Git history preserves every revision. Never include secret values.

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
