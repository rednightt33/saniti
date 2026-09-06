# saniti

This repository is the operational history and documentation source for the Saniti Railway project. Railway and PostgreSQL remain the live systems; GitHub records how and why they changed.

## AI start here

An AI working on this project must read these files in order before changing Railway or PostgreSQL:

1. [`AGENTS.md`](AGENTS.md) — mandatory working and GitHub-update rules.
2. [`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md) — Railway scope, resource identities, data flows, and access method.
3. [`DATABASE_SCHEMA.md`](DATABASE_SCHEMA.md) — current generated tables, columns, keys, indexes, and relationships.
4. [`DATABASE_CHANGELOG.md`](DATABASE_CHANGELOG.md) — database migrations and data-load history.
5. [`RAILWAY_CHANGELOG.md`](RAILWAY_CHANGELOG.md) — services, deployments, networking, and configuration history.
6. [`database/migrations/`](database/migrations/) — executable SQL history for schema changes.
7. [`apps/idx-price-cron/README.md`](apps/idx-price-cron/README.md) — TradingView daily/recovery schedule, data rules, and runtime contract.

## Mandatory update contract

Every successful change to Railway or its PostgreSQL database must be recorded and pushed to this repository in the same task. A change is not complete until its Git commit is visible on `origin/main`.

- Database structure change: add a dated SQL file under `database/migrations/`, refresh `DATABASE_SCHEMA.md`, and append `DATABASE_CHANGELOG.md`.
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

The repository must have an Actions secret named `RAILWAY_TOKEN`; the value is never written to Git. The automated snapshot complements the mandatory human/AI changelogs: Git captures exactly what changed, while the changelogs explain why.

Local refresh:

```bash
python -m pip install -r requirements-schema.txt
DATABASE_URL="postgresql://..." python scripts/sync_database_schema.py
```
