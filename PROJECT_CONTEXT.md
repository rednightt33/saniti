# Project context

## Purpose

Saniti stores Indonesian equity reference data, daily prices, and Stockbit broker activity in Railway PostgreSQL. This repository provides the durable operating context and change history for humans and AI agents.

## Railway scope

- Project: `lucid-patience`
- Project ID: `8aef1702-030b-49cb-9df7-5ac2e0a42691`
- Environment: `dev`
- Environment ID: `4d3e5af2-302b-4a2e-84e2-7d7476d6ff49`
- PostgreSQL service ID: `bb21a9f4-a9d3-4a51-945f-fa86b63f4b86`
- IDX price cron service: `idx-price-cron`
- IDX price cron service ID: `43c86c6f-3221-4403-83c3-cd3056441558`
- IDX price recovery cron service: `idx-price-recovery-cron`
- IDX price recovery cron service ID: `a8e6e32a-fcd8-4c33-9ecc-1488a4b2db05`
- Feature 01 worker service: `feature-01-worker`
- Feature 01 worker service ID: `de4e34ee-435b-408f-a77f-63e6698a2dab`
- Telegram notification service: `telegram-monitor`
- Telegram notification service ID: `a6b4e061-721f-4173-82f8-07ccb45740fc`
- Telegram command service: `telegram-trigger`
- Telegram command service ID: `5a3f820c-2bb2-494b-b771-15fa6a5eb48a`
- Telegram command service instance ID: `78bd93d5-f74a-42fb-ad25-2be856bbda07`
- Market AI backend service: `market-ai-backend`
- Market AI backend service ID: `2cefa0cd-c9fc-4b84-992e-fdf08535a064`
- Dashboard: <https://railway.com/project/8aef1702-030b-49cb-9df7-5ac2e0a42691?environmentId=4d3e5af2-302b-4a2e-84e2-7d7476d6ff49>
- GitHub: <https://github.com/rednightt33/saniti>

Always scope Railway CLI calls with these explicit IDs. Do not rely on an unrelated locally linked project.

### Service sources and deployment isolation

All application services deploy from `rednightt33/saniti` on branch `main`. Each service has a monorepo root directory and a matching watch path so unrelated application or documentation changes do not trigger its deployment:

| Railway service | Root directory | Watch path |
| --- | --- | --- |
| `idx-price-cron` | `/apps/idx-price-cron` | `/apps/idx-price-cron/**` |
| `idx-price-recovery-cron` | `/apps/idx-price-cron` | `/apps/idx-price-cron/**` |
| `telegram-monitor` | `/apps/telegram-monitor` | `/apps/telegram-monitor/**` |
| `telegram-trigger` | `/apps/telegram-trigger` | `/apps/telegram-trigger/**` |
| `feature-01-worker` | `/apps/feature-01-worker` | `/apps/feature-01-worker/**` |
| `market-ai-backend` | `/apps/market-ai-backend` | `/apps/market-ai-backend/**` |

Connecting or changing a service source must preserve its environment variables and secrets, cron schedule, start command, health check, domain, private networking, restart/serverless policy, and database references. Source-configuration work must not use **Run now** on either price service and must not issue a TradingView query. Record the currently active deployment ID before each change so it remains available as the rollback reference, then wait for the new deployment to reach `SUCCESS` before changing the next service.

## Data flows

Broker-summary backfill:

```text
Forward:    Stockbit API -> local Python runner -> Railway PostgreSQL -> daily CSV on the local PC
Historical: Stockbit API -> local Python runner -> Railway PostgreSQL
```

The forward run covers 2025-11-17 through 2026-08-31 in ascending order and is complete. Historical work is split between two database-only local supervisors running in parallel: the recent worker covers 2025-08-31 through 2021-01-01, and the older worker covers 2020-12-31 through 2018-01-01, both in descending order. The two historical workers use three API workers each so their combined concurrency remains six. Each run uses separate status and log files. The supervisor recreates the temporary Railway TCP proxy when needed, skips dates logged as `COMPLETED`, and records repeatedly failing dates as `NEEDS_REVIEW`. Five consecutive Stockbit HTTP 401/403 responses stop an affected query as `STOPPED_INVALID_TOKEN`; a refreshed JWT and supervisor restart are then required.

Reference and price uploads:

```text
Local CSV/XLSX -> validation -> one-transaction PostgreSQL load -> live read-back verification
```

Automated daily IDX prices:

```text
idx-price-cron at 17:00 Asia/Jakarta, or Run now -> all IDX_Stock_Universe tickers -> TradingView
-> bulk upsert Price_Stock_Indonesia_IDX -> Monitoring_Price_ALL -> send execution_id to telegram-monitor
-> Telegram message -> Telegram_Notification_Log records SENT

idx-price-recovery-cron at 06:00 Asia/Jakarta, or Run now -> previous-weekday DAILY missing tickers only -> TradingView
-> bulk upsert Price_Stock_Indonesia_IDX -> Monitoring_Price_ALL -> send execution_id to telegram-monitor
-> Telegram message with remaining missing tickers -> Telegram_Notification_Log records SENT
```

Railway evaluates separate UTC schedules: `idx-price-cron` uses `0 10 * * *`, and `idx-price-recovery-cron` uses `0 23 * * *`. Both use explicit modes and exit after each execution. Weekend recovery targets Friday. A price row is accepted only when the TradingView candle timestamp matches the exact target date; a prior candle is never used as today's value. The `(ticker, date)` primary key makes repeated runs replace only the same daily row. A shared PostgreSQL advisory lock prevents concurrent runs. Every execution has its own monitoring `execution_id`; the system never performs an automatic third TradingView query.

After a committed price insert/update with non-null `ingestion_time`, the PostgreSQL trigger opens a Feature 01 queue item for that ticker/date in the same transaction. The always-on `feature-01-worker` polls the queue, runs the incremental SQL refresh, validates affected rows, and updates `Feature_Calculation_Queue`, `Feature_Status`, and `Feature_Calculation_Log`. It has no cron schedule and never queries TradingView. A historical price correction can refresh up to 120 subsequent trading observations. Its `SUCCESS` status measures price-driven freshness only; universe classification changes need a separate refresh path.

`telegram-monitor` has no cron schedule and does not poll PostgreSQL. It sleeps while idle and is called only after a DAILY or RECOVERY monitoring transaction commits. The caller retries temporary cold-start/network failures; Telegram failure never rolls back price data. Delivery is deduplicated by source table plus `execution_id`. Each final message shows the job's `run_time` as `Triggered at` and `finished_at` as `Finished at`, converted to Asia/Jakarta.

Telegram manual control:

```text
Telegram owner -> telegram-trigger webhook -> validate webhook secret and Chat ID
-> record Telegram_Command_Log -> Railway Run Now on the fixed DAILY or RECOVERY service
-> normal price/monitoring flow -> telegram-monitor sends the final result
```

`telegram-trigger` accepts only `/run_price`, `/run_recovery`, and the matching fixed buttons. Telegram retries are deduplicated by `telegram_update_id`, while a short per-service cooldown blocks rapid repeat clicks. The trigger service sends only the immediate started/failed control acknowledgement; `telegram-monitor` remains responsible for the final data result.

## Main database objects

- `IDX_Broker_Profile`: broker reference data.
- `IDX_Broker_Summary`: daily broker activity.
- `IDX_Stock_Universe`: Indonesian listed-security universe.
- `Universe_Equity_Description`: company and industry descriptions.
- `Price_Stock_Indonesia_IDX`: daily IDX OHLCV price history.
- `Feature_01_Stock_Daily`: SQL-side daily ticker features for price returns, volatility, volume, and drawdown; its incremental refresh routine is called by the Feature 01 worker.
- `Feature_02_Broker_Rolling`: broker flow and rolling signals for all symbols in `IDX_Broker_Summary`, partitioned by Regular/Nego/Tunai board; windows count ticker transaction dates across any board. Its initial historical backfill is SQL-side, but no automatic Feature 02 refresh worker is deployed. See `FEATURE_02_BROKER_ROLLING.md`.
- `Feature_03_Stock_Broker_Daily`: stock-level daily broker breadth, classified net flows, dominant brokers, and HHI at `date × ticker × market_board`; all three boards remain separate. It is refreshed after Feature 02, with no automatic worker in v1. See `FEATURE_03_STOCK_BROKER_DAILY.md`.
- `Feature_Calculation_Queue`: durable per-candle Feature 01 work items; a PostgreSQL price-row trigger now enqueues them in the price transaction.
- `Feature_Status`: current price-driven per-ticker Feature 01 calculation state, reconciled during enqueue and worker transitions.
- `Feature_Calculation_Log`: completed calculation attempt and retry history. The Railway worker is deployed and a live re-ingestion test passed.
- `Feature_Catalog`: machine-readable semantic and governance layer for validated columns in the four locked Feature tables. Active `v1` definitions cover validated Feature 01, Feature 02, and Feature 03 tables.
- `Feature_Relationship_Catalog`: safe join keys, cardinality, output grain, and preaggregation requirements between validated Feature tables.
- `Tool_Catalog`: generic AI tool schemas, versions, activation state, and advertised database/worker/LLM-facing limits. Backend configuration remains the enforcement authority.
- `Analysis_Request`, `Analysis_Step_Log`, and `Analysis_Evidence`: durable request lifecycle, progressive tool exposure, cumulative token/context usage, immutable version/methodology snapshot, compact steps, and reproducible claim evidence.
- `Golden_Analysis_Test`, `Golden_Analysis_Test_Run`, and `Golden_Analysis_Test_Result`: permanent analytical regression expectations and historical outcomes across data correctness, methodology, safety, and token behavior.
- `Table_Catalog`: curated purpose, grain, source, writer, and update contract for approved tables, including Feature 02 and Feature 03.
- `Column_Catalog`: physical column inventory and evidence-graded definitions for approved tables. For Feature formulas, `Feature_Catalog` remains authoritative.
- `Monitoring_Price_ALL`: per-execution daily/recovery completeness, trigger source, query time, missing symbols, and status grouped by the universe `Security Type` value.
- `Telegram_Command_Log`: incoming Telegram Run Now audit, webhook-retry deduplication, and rapid-click blocking.
- `Telegram_Notification_Log`: Telegram delivery status and anti-duplicate ledger keyed by source table and source `execution_id`.
- `stockbit_broker_summary_load_log`: resume, retry, and `NEEDS_REVIEW` history.
- `Database_Table_Status`: freshness and tracking catalog.

The market-AI database foundation and private backend are deployed. Railway reports the service deployment healthy and its private `/health` check passes. The least-privilege `market_ai_app` login can access only catalogs and VERIFIED Feature 1–3 tables plus analysis audit writes, never raw price/broker data; no analytics-worker service exists. A live durable request reached the worker, but OpenAI rejected it before tool execution because the API billing balance had no credits. Paid API credits plus a successful rerun are therefore the remaining Release 1B end-to-end gate. Historical analysis must apply close-`t` to entry-`t+1`, preserve `SURVIVORSHIP_BIAS_WARNING` when point-in-time universe data is unavailable, and retain completed version snapshots.

See `DATABASE_CATALOG.md` for the initial and current table lists, metadata fields, confidence rules, and mandatory updates when new tables, columns, Feature definitions, or routines are added. `Database_Table_Status` remains a separate operational freshness table and is not a semantic catalog target.

Use `DATABASE_SCHEMA.md` for exact current columns and constraints.

## Access requirements

An AI may need the user to provide or authorize:

- Railway project token or an authenticated Railway CLI session.
- A current Stockbit JWT for Stockbit API work.
- A GitHub token with repository content write access when no Git credential is available.
- A temporary Railway PostgreSQL TCP proxy for local database access.

Secrets must remain in environment variables or secure prompts and must never be committed.

## Sources of truth

- Live data and runtime state: Railway/PostgreSQL.
- Current database documentation: `DATABASE_SCHEMA.md`.
- Database change history: `DATABASE_CHANGELOG.md` and `database/migrations/`.
- Railway change history: `RAILWAY_CHANGELOG.md` and Git commit history.
- Mandatory agent behavior: `AGENTS.md`.
