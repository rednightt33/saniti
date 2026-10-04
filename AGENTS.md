# Agent instructions

## Required reading

Before touching Railway or PostgreSQL, read `README.md`, `PROJECT_CONTEXT.md`, `DATABASE_SCHEMA.md`, `DATABASE_CATALOG.md`, `DATABASE_CHANGELOG.md`, `RAILWAY_CHANGELOG.md`, and `ERRORS_AND_SOLUTIONS.md` completely. Read the relevant files under `database/migrations/` before changing an existing table.

`ERRORS_AND_SOLUTIONS.md` lists every error found so far, with its root cause, solution and status. Check it before diagnosing a failure: the error may already be known. Its Part A is the data-format standard. Before adding a new data source or table (for example cross-asset or macro data), confirm that it meets every item of Part A, and settle any gap with the user before loading.

## Mandatory workflow

1. Confirm the requested scope and exact target names with the user when ambiguous.
2. Inspect current Railway and database state before mutation. Use explicit project, environment, and service IDs from `PROJECT_CONTEXT.md`.
3. Preserve unrelated services, tables, rows, files, and user changes.
4. Apply the smallest safe change and verify it from the live system.
5. Record the change in GitHub during the same task:
   - Schema: add a forward SQL migration, refresh `DATABASE_SCHEMA.md`, and append `DATABASE_CHANGELOG.md`.
   - Metadata: update `Table_Catalog` for every new/changed public data table, `Column_Catalog` for every new/changed column in those tables, and `Feature_Catalog` for new/changed Feature definitions. Every active Feature definition must include a formula, plain-language analytical interpretation, recommended use, misuse warning, semantic review status, and validation-evidence paths; run `scripts/audit_feature_catalog_semantics.py` after a Feature change. Register safe Feature joins in `Feature_Relationship_Catalog` and generic AI tools/limits in `Tool_Catalog`. The only initial exclusions are `Database_Table_Status`, `Table_Catalog`, and `Column_Catalog` themselves. Register new/changed PostgreSQL routines in related `Table_Catalog.related_functions`; see `DATABASE_CATALOG.md`. Do not mark inferred meanings VERIFIED.
   - Performance: define high-frequency query patterns for each major Feature table and run bounded `EXPLAIN (ANALYZE, BUFFERS)` before adding a large index. A result limit does not prove scan efficiency. Record measured plan evidence and do not add speculative indexes.
   - Data: append source metadata and verification results to `DATABASE_CHANGELOG.md`.
   - Railway infrastructure/config/deployment: update `.railway/railway.ts` if applicable and append `RAILWAY_CHANGELOG.md`.
   - Documentation/process: update the relevant Markdown file.
   - AI tools: when a model tool, a sandbox session helper, a method guide, or the switch that turns one on is added, removed, renamed or changed, regenerate `AI_TOOLS.md` in the same task with `scripts/generate_ai_tools_doc.py` (from `apps/market-ai-orc`, its venv). When a dev `AI_ENABLE_*` switch changes, regenerate with `--flags` built from `railway variables --kv` (names and true/false only, never other values) so the dev snapshot is current. Every new name needs its plain-language sentence in the generator's `PLAIN`. `apps/market-ai-orc/tests/test_ai_tools_doc.py` fails when the file and the code drift apart.
   - Errors: record every new error, defect or data problem in `ERRORS_AND_SOLUTIONS.md`: symptom, verified root cause, solution, status and lesson for new data (Part D). When a fix lands, update the entry's status in place; never delete entries. If the lesson changes how data must be shaped, update Part A too.
   - After a direct Railway dashboard or CLI configuration change, run `railway config pull --force` and `railway config plan` so `.railway/railway.ts` matches the live project.
6. Run `git diff --check`, review the diff, commit, push `main`, and verify the branch matches `origin/main`.
7. If the GitHub push fails, report the task as incomplete and explain what remains unpushed.

## Model and provider

The user decided on 2026-09-27 that `market-ai-orc` keeps the model `deepseek/deepseek-v4.1-flash` through OpenRouter's default provider routing. Do not set `AI_PROVIDER_SORT`, do not change `AI_MODEL`, and do not switch provider without the user's explicit approval.

On 2026-09-30 the user approved a model switcher: `AI_MODEL_SWITCH=1` (default) runs `AI_MODEL` (`deepseek/deepseek-v4.1-flash`), `AI_MODEL_SWITCH=2` runs `AI_MODEL_2` (`xiaomi/mimo-v2.6-pro`). Model 1 stays the default; leave `AI_MODEL_SWITCH` unset or `1` except for a test the user asked for, and do not change `AI_MODEL` or `AI_MODEL_2` without approval.

On 2026-10-04 the user approved (plan `PLAN_FINAL_2026-10-04.md`, decision K1) `AI_MODEL_2=xiaomi/mimo-v2.6-flash` with `AI_MODEL_SWITCH=2` on dev, measured first with a small golden test; `AI_MODEL` stays `deepseek/deepseek-v4.1-flash` as the way back (`AI_MODEL_SWITCH=1`). The same day the user approved routing away from providers that barely discount cache reads: `AI_PROVIDER_MAX_CACHE_PRICE_RATIO=0.25` on dev, a list derived from OpenRouter's endpoint pricing (`app/provider_policy.py`). `AI_PROVIDER_SORT` stays unset; any other provider change still needs approval.

On 2026-09-30 the user approved mode 4 (`AI_ENABLE_MODE4`, `app/mode4.py`) and a mode switcher: `AI_MODE_SWITCH` sets the default mode (1 AUTO, 2 ANALYSIS, 3 RESEARCH, 4 MODE4) and `analysis_path` chooses per request. The user chose default 4 on dev; do not change `AI_MODE_SWITCH` without approval.

## Security

Never commit secret values, database URLs, passwords, private keys, Railway tokens, Stockbit JWTs, or GitHub PATs. For a secret change, record only the variable name, Railway scope, action, and verification status. Redact secrets from logs and terminal output.

## History rules

- Never edit an old migration after it has been applied. Add a new migration.
- Do not use GitHub as a row-by-row database mirror. Record data-load metadata and keep operational row history in PostgreSQL load logs.
- Do not claim a Railway deployment succeeded until its exact deployment reaches `SUCCESS`.
- Do not claim a database change succeeded until the live schema/data has been read back and verified.
