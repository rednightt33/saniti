# Agent instructions

## Required reading

Before touching Railway or PostgreSQL, read `README.md`, `PROJECT_CONTEXT.md`, `DATABASE_SCHEMA.md`, `DATABASE_CATALOG.md`, `DATABASE_CHANGELOG.md`, and `RAILWAY_CHANGELOG.md` completely. Read the relevant files under `database/migrations/` before changing an existing table.

## Mandatory workflow

1. Confirm the requested scope and exact target names with the user when ambiguous.
2. Inspect current Railway and database state before mutation. Use explicit project, environment, and service IDs from `PROJECT_CONTEXT.md`.
3. Preserve unrelated services, tables, rows, files, and user changes.
4. Apply the smallest safe change and verify it from the live system.
5. Record the change in GitHub during the same task:
   - Schema: add a forward SQL migration, refresh `DATABASE_SCHEMA.md`, and append `DATABASE_CHANGELOG.md`.
   - Metadata: update `Table_Catalog` for every new/changed public data table, `Column_Catalog` for every new/changed column in those tables, and `Feature_Catalog` for new/changed Feature definitions. The only initial exclusions are `Database_Table_Status`, `Table_Catalog`, and `Column_Catalog` themselves. Register new/changed PostgreSQL routines in related `Table_Catalog.related_functions`; see `DATABASE_CATALOG.md`. Do not mark inferred meanings VERIFIED.
   - Data: append source metadata and verification results to `DATABASE_CHANGELOG.md`.
   - Railway infrastructure/config/deployment: update `.railway/railway.ts` if applicable and append `RAILWAY_CHANGELOG.md`.
   - Documentation/process: update the relevant Markdown file.
   - After a direct Railway dashboard or CLI configuration change, run `railway config pull --force` and `railway config plan` so `.railway/railway.ts` matches the live project.
6. Run `git diff --check`, review the diff, commit, push `main`, and verify the branch matches `origin/main`.
7. If the GitHub push fails, report the task as incomplete and explain what remains unpushed.

## Security

Never commit secret values, database URLs, passwords, private keys, Railway tokens, Stockbit JWTs, or GitHub PATs. For a secret change, record only the variable name, Railway scope, action, and verification status. Redact secrets from logs and terminal output.

## History rules

- Never edit an old migration after it has been applied. Add a new migration.
- Do not use GitHub as a row-by-row database mirror. Record data-load metadata and keep operational row history in PostgreSQL load logs.
- Do not claim a Railway deployment succeeded until its exact deployment reaches `SUCCESS`.
- Do not claim a database change succeeded until the live schema/data has been read back and verified.
