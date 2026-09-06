# Project context

## Purpose

Saniti stores Indonesian equity reference data, daily prices, and Stockbit broker activity in Railway PostgreSQL. This repository provides the durable operating context and change history for humans and AI agents.

## Railway scope

- Project: `lucid-patience`
- Project ID: `8aef1702-030b-49cb-9df7-5ac2e0a42691`
- Environment: `dev`
- Environment ID: `4d3e5af2-302b-4a2e-84e2-7d7476d6ff49`
- PostgreSQL service ID: `bb21a9f4-a9d3-4a51-945f-fa86b63f4b86`
- Application service: `valiant-connection`
- Application service ID: `4f56808b-2797-4d41-bbc5-4e66b9f4304c`
- IDX price cron service: `idx-price-cron`
- IDX price cron service ID: `43c86c6f-3221-4403-83c3-cd3056441558`
- Dashboard: <https://railway.com/project/8aef1702-030b-49cb-9df7-5ac2e0a42691?environmentId=4d3e5af2-302b-4a2e-84e2-7d7476d6ff49>
- GitHub: <https://github.com/rednightt33/saniti>

Always scope Railway CLI calls with these explicit IDs. Do not rely on an unrelated locally linked project.

## Data flows

Broker-summary backfill:

```text
Stockbit API -> local Python runner -> Railway PostgreSQL -> daily CSV on the local PC
```

The local supervisor restarts a failed broker-summary runner, recreates the temporary Railway TCP proxy when needed, skips dates logged as `COMPLETED`, and records repeatedly failing dates as `NEEDS_REVIEW`.

Reference and price uploads:

```text
Local CSV/XLSX -> validation -> one-transaction PostgreSQL load -> live read-back verification
```

Automated daily IDX prices:

```text
17:00 Asia/Jakarta DAILY -> all IDX_Stock_Universe tickers -> TradingView
-> bulk upsert Price_Stock_Indonesia_IDX -> Monitoring_Price_ALL

06:00 Asia/Jakarta RECOVERY -> prior DAILY missing tickers only -> TradingView
-> bulk upsert Price_Stock_Indonesia_IDX -> Monitoring_Price_ALL
```

Railway evaluates the combined cron schedule `0 10,23 * * *` in UTC. The service chooses `DAILY` or `RECOVERY` from the current Asia/Jakarta hour and exits after each run. It never performs an automatic third TradingView query.

## Main database objects

- `IDX_Broker_Profile`: broker reference data.
- `IDX_Broker_Summary`: daily broker activity.
- `IDX_Stock_Universe`: Indonesian listed-security universe.
- `Universe_Equity_Description`: company and industry descriptions.
- `Price_Stock_Indonesia_IDX`: daily IDX OHLCV price history.
- `Monitoring_Price_ALL`: per-run daily/recovery completeness, missing symbols, and status grouped by the universe `Security Type` value.
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
