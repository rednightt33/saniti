# saniti

This repository is the operational history and documentation source for the Saniti Railway project. Railway and PostgreSQL remain the live systems; GitHub records how and why they changed.

## AI start here

An AI working on this project must read these files in order before changing Railway or PostgreSQL:

1. [`AGENTS.md`](AGENTS.md) — mandatory working and GitHub-update rules.
2. [`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md) — Railway scope, resource identities, data flows, and access method.
3. [`DATABASE_SCHEMA.md`](DATABASE_SCHEMA.md) — current generated tables, columns, keys, indexes, and relationships.
4. [`DATABASE_CATALOG.md`](DATABASE_CATALOG.md) — what the table, column, and Feature catalogs mean and how to maintain them.
5. [`DATABASE_CHANGELOG.md`](DATABASE_CHANGELOG.md) — database migrations and data-load history.
6. [`RAILWAY_CHANGELOG.md`](RAILWAY_CHANGELOG.md) — services, deployments, networking, and configuration history.
7. [`database/migrations/`](database/migrations/) — executable SQL history for schema changes.
8. [`apps/idx-price-cron/README.md`](apps/idx-price-cron/README.md) — TradingView daily/recovery schedule, data rules, and runtime contract.
9. [`apps/telegram-monitor/README.md`](apps/telegram-monitor/README.md) — event-driven Telegram delivery, anti-duplicate rules, and secret-variable contract.
10. [`apps/telegram-trigger/README.md`](apps/telegram-trigger/README.md) — authorized Telegram controls for Railway Run Now actions and command deduplication.
11. [`apps/stockbit-broker-backfill/README.md`](apps/stockbit-broker-backfill/README.md) — local Stockbit backfill, parallel date ranges, retry behavior, and invalid-token stop rule.
12. [`apps/feature-01-worker/README.md`](apps/feature-01-worker/README.md) — Feature 01 price queue, worker retries, and status/log operating contract.
13. [`FEATURE_02_BROKER_ROLLING.md`](FEATURE_02_BROKER_ROLLING.md) — board-separated broker features, ticker transaction-date windows, full backfill, and refresh limitations.
14. [`FEATURE_03_STOCK_BROKER_DAILY.md`](FEATURE_03_STOCK_BROKER_DAILY.md) — stock-level broker breadth, classified flows, dominant brokers, HHI, board separation, and refresh limitations.
15. [`AI_ANALYST_IMPLEMENTATION_PLAN.md`](AI_ANALYST_IMPLEMENTATION_PLAN.md) — approved staged architecture, limits, point-in-time/no-look-ahead policy, reproducibility, and Golden Test gates.
16. [`DATABASE_INDEX_ACCEPTANCE.md`](DATABASE_INDEX_ACCEPTANCE.md) — measured Feature 1–2 query plans, buffers, latency, and index decisions.

Automatic price-driven Feature 01 calculation is active in Railway `dev`: PostgreSQL transactionally enqueues price writes with non-null `ingestion_time`, and the always-on `feature-01-worker` processes them. The live Railway worker completed a re-ingestion test. See [`FEATURE_01_AUTOMATION_PLAN.md`](FEATURE_01_AUTOMATION_PLAN.md) and [`apps/feature-01-worker/README.md`](apps/feature-01-worker/README.md).

Feature 02 is a separate broker-derived table for all `IDX_Broker_Summary` symbols and three board partitions (`Regular`, `Nego`, `Tunai`). Its 5/20/60D windows use each ticker's transaction dates across any board. The Feature 01 price worker does not update Feature 02; see [`FEATURE_02_BROKER_ROLLING.md`](FEATURE_02_BROKER_ROLLING.md) for the manual backfill and current refresh contract.

Feature 03 aggregates Feature 02 into one stock/day/board row for efficient AI screening and statistical analysis. Regular, Nego, and Tunai remain separate. Its 24 active definitions are in `Feature_Catalog`, and safe joins are in `Feature_Relationship_Catalog`; see [`FEATURE_03_STOCK_BROKER_DAILY.md`](FEATURE_03_STOCK_BROKER_DAILY.md).

The market-AI database foundation is live: generic tool, relationship, readiness, point-in-time/availability, analysis audit, version snapshot, and Golden Test contracts are registered. The private `market-ai-backend` has not yet been deployed. Database query, Analytics Worker, and LLM context/cumulative token limits are separate policies. Historical Feature 1–3 analysis uses conservative close-`t` to entry-`t+1` timing and must disclose survivorship/current-metadata limitations.

## Mandatory update contract

Every successful change to Railway or its PostgreSQL database must be recorded and pushed to this repository in the same task. A change is not complete until its Git commit is visible on `origin/main`.

- Database structure change: add a dated SQL file under `database/migrations/`, refresh `DATABASE_SCHEMA.md`, and append `DATABASE_CHANGELOG.md`.
- Every new/changed public data table or column must update `Table_Catalog` or `Column_Catalog` (apart from the three explicit internal-table exclusions); every new/changed Feature definition must also update `Feature_Catalog`. New/changed PostgreSQL routines must be registered in the related `Table_Catalog.related_functions` and described in the migration/changelog. Follow [`DATABASE_CATALOG.md`](DATABASE_CATALOG.md) for exact fields, confidence levels, and update commands.
- Data upload, replacement, or backfill: append `DATABASE_CHANGELOG.md` with the source filename, checksum when available, row count, covered date range, target table, and verification result. Do not commit large raw datasets unless explicitly requested.
- Railway service, environment, networking, deployment, or non-secret variable change: update `.railway/railway.ts` when represented there and append `RAILWAY_CHANGELOG.md`.
- Secret change: record only the variable name, scope, and action. Never record its value.
- Process or navigation change: update this README, `PROJECT_CONTEXT.md`, or `AGENTS.md` as applicable.

Required finish sequence:

```bash
git pull --ff-only
# After a direct Railway dashboard/CLI configuration change:
railway config pull --force
railway config plan
python scripts/sync_database_catalog.py
python scripts/sync_database_schema.py
git diff --check
git status --short
git add <changed-files>
git commit -m "<type>: <short description>"
git push origin main
git status --short --branch
```

When a change starts by editing `.railway/railway.ts`, run `railway config plan`, obtain explicit approval for its exact effects, apply it, verify Railway, and then continue with the Git finish sequence. Never run a destructive IaC apply without explicit approval.

Do not place `DATABASE_URL`, Railway tokens, Stockbit JWTs, GitHub PATs, passwords, or decrypted Railway variables in source control.

## Automated state refresh

[`DATABASE_SCHEMA.md`](DATABASE_SCHEMA.md) is generated from live Railway PostgreSQL. [`.railway/railway.ts`](.railway/railway.ts) is a secret-safe snapshot of the Railway services and configuration. The `Track Railway and database state` GitHub Action refreshes both daily at 01:17 Asia/Jakarta and can also run manually. Direct dashboard changes therefore appear as ordinary Git history.

Before generating the schema, the Action reconciles `Column_Catalog` physical metadata and fails if a table, column, or active Feature definition is missing from its required catalog. It does not invent semantic definitions; unresolved meanings remain `NEEDS_REVIEW`.

The repository must have an Actions secret named `RAILWAY_TOKEN`; the value is never written to Git. The automated snapshot complements the mandatory human/AI changelogs: Git captures exactly what changed, while the changelogs explain why.

Local refresh:

```bash
python -m pip install -r requirements-schema.txt
DATABASE_URL="postgresql://..." python scripts/sync_database_schema.py
```
