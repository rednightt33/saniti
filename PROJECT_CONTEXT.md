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
- Telegram notification service: `telegram-monitor`
- Telegram notification service ID: `a6b4e061-721f-4173-82f8-07ccb45740fc`
- Dashboard: <https://railway.com/project/8aef1702-030b-49cb-9df7-5ac2e0a42691?environmentId=4d3e5af2-302b-4a2e-84e2-7d7476d6ff49>
- GitHub: <https://github.com/rednightt33/saniti>

Always scope Railway CLI calls with these explicit IDs. Do not rely on an unrelated locally linked project.

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

`telegram-monitor` has no cron schedule and does not poll PostgreSQL. It sleeps while idle and is called only after a DAILY or RECOVERY monitoring transaction commits. The caller retries temporary cold-start/network failures; Telegram failure never rolls back price data. Delivery is deduplicated by source table plus `execution_id`.

## Main database objects

- `IDX_Broker_Profile`: broker reference data.
- `IDX_Broker_Summary`: daily broker activity.
- `IDX_Stock_Universe`: Indonesian listed-security universe.
- `Universe_Equity_Description`: company and industry descriptions.
- `Price_Stock_Indonesia_IDX`: daily IDX OHLCV price history.
- `Monitoring_Price_ALL`: per-execution daily/recovery completeness, trigger source, query time, missing symbols, and status grouped by the universe `Security Type` value.
- `Telegram_Notification_Log`: Telegram delivery status and anti-duplicate ledger keyed by source table and source `execution_id`.
- `stockbit_broker_summary_load_log`: resume, retry, and `NEEDS_REVIEW` history.
- `Database_Table_Status`: freshness and tracking catalog.

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
