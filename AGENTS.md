# Agent instructions

## Required reading

Before touching Railway or PostgreSQL, read `README.md`, `PROJECT_CONTEXT.md`, `DATABASE_SCHEMA.md`, `DATABASE_CATALOG.md`, `DATABASE_CHANGELOG.md`, `RAILWAY_CHANGELOG.md`, and `ERRORS_AND_SOLUTIONS.md` completely. Read the relevant files under `database/migrations/` before changing an existing table.

`ERRORS_AND_SOLUTIONS.md` lists every error found so far, with its root cause, solution and status. Check it before diagnosing a failure: the error may already be known. Its Part A is the data-format standard. Before adding a new data source or table (for example cross-asset or macro data), confirm that it meets every item of Part A, and settle any gap with the user before loading.

## Plans

- `EXEC.md` holds every execution the user approved, one complete section per execution (user decision 2026-10-06).
  `PLAN.md` holds approved work that has no execution plan yet. `FUTURE_PLAN.md` holds proposals, future work and open
  user decisions. Do not create dated plan files (`PLAN_YYYY-MM-DD.md`, `ROUND_PLAN_*`); the old ones are discussion
  history (user decision 2026-10-06).
- Record an approval in `PLAN.md` or `EXEC.md` in the same task, with its date and the user's words, even when the user
  approves "in general"; keep only the open details as questions on that item (R34). Approval to plan is not a command to
  execute: an execution starts only after the user's go confirmation.
- When an item is done, record it in `ERRORS_AND_SOLUTIONS.md` and the changelogs and remove it from `PLAN.md` or
  `EXEC.md`.
- Before a golden test, compare `PLAN.md` and `EXEC.md` with the deployed behaviour and report any approved item not yet
  built.

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
   - AI models: when a model call is added, removed or changed (model, reasoning, output-token limit, tools, structured output, provider routing), when a model setting is added or renamed in a service's `config.py`, or when a model, reasoning, token, provider or slot variable changes on Railway, regenerate `AI_MODELS.md` in the same task with `scripts/generate_ai_models_doc.py` (from the repository root). For a Railway change pass `--dev-values` with the listed names and their values only (never secrets; the generator refuses secret-looking values). Every new call site needs its plain-language sentence in the generator's `PURPOSE`. `apps/market-ai-orc/tests/test_ai_models_doc.py` fails when the file and the code drift apart.
   - AI router: when the routing criteria change (classes, their descriptions, the action each class runs, the fallback, or which requests the router reads), update `AI_ROUTER.md` in the same task (it is generated from the router code with `scripts/generate_ai_router_doc.py` once the first-turn router lands) and re-run the router benchmark set before deploying.
   - Errors: record every new error, defect or data problem in `ERRORS_AND_SOLUTIONS.md`: symptom, verified root cause, solution, status and lesson for new data (Part D). When a fix lands, update the entry's status in place; never delete entries. If the lesson changes how data must be shaped, update Part A too.
   - After a direct Railway dashboard or CLI configuration change, run `railway config pull --force` and `railway config plan` so `.railway/railway.ts` matches the live project.
6. Run `git diff --check`, review the diff, commit, push `main`, and verify the branch matches `origin/main`.
7. If the GitHub push fails, report the task as incomplete and explain what remains unpushed.

## Model and provider

`AI_MODELS.md` lists every model call, its settings and the dev values; keep it current (Mandatory workflow, AI models).

The user decided on 2026-09-27 that `market-ai-orc` keeps the model `deepseek/deepseek-v4.1-flash` through OpenRouter's default provider routing. Do not set `AI_PROVIDER_SORT`, do not change `AI_MODEL`, and do not switch provider without the user's explicit approval.

On 2026-09-30 the user approved a model switcher: `AI_MODEL_SWITCH=1` (default) runs `AI_MODEL` (`deepseek/deepseek-v4.1-flash`), `AI_MODEL_SWITCH=2` runs `AI_MODEL_2` (`xiaomi/mimo-v2.6-pro`). Model 1 stays the default; leave `AI_MODEL_SWITCH` unset or `1` except for a test the user asked for, and do not change `AI_MODEL` or `AI_MODEL_2` without approval.

On 2026-10-04 the user approved (plan `PLAN_FINAL_2026-10-04.md`, decision K1) `AI_MODEL_2=xiaomi/mimo-v2.6-flash` with `AI_MODEL_SWITCH=2` on dev, measured first with a small golden test; `AI_MODEL` stays `deepseek/deepseek-v4.1-flash` as the way back (`AI_MODEL_SWITCH=1`). The same day the user approved routing away from providers that barely discount cache reads: `AI_PROVIDER_MAX_CACHE_PRICE_RATIO=0.25` on dev, a list derived from OpenRouter's endpoint pricing (`app/provider_policy.py`). `AI_PROVIDER_SORT` stays unset; any other provider change still needs approval. Later on 2026-10-04 the user switched dev back to DeepSeek (`AI_MODEL_SWITCH=1`) before the final golden test; `AI_MODEL_2` stays `xiaomi/mimo-v2.6-flash` for a later test. The provider rule applies to the model in use (DeepSeek: Relace, Wafer and InferenceNet skipped). Later on 2026-10-04 the user kept the provider routing as is (O1 not done) and kept `xiaomi/mimo-v2.5` (web-governor slot 2) for event classification, cross-checked by slot 1.

On 2026-10-05 the user approved a speed preference after the p1 analysis (M75 recurrence on Sail Research): `AI_PROVIDER_MIN_THROUGHPUT=50` on dev, sent as OpenRouter `provider.preferred_min_throughput` `{p50: 50}`. It is a preference, not a filter or a sort: slower endpoints are tried last and the price weighting stays on. `AI_PROVIDER_SORT` stays unset; changing the threshold or any other provider setting still needs approval.

On 2026-10-06 the user decided "1 conversation ID = 1 session ID … RUN ID ya bisa berbeda" (EXEC-S): every model call
of a conversation (each turn, each mode 4 step, the routers) sends the conversation id as OpenRouter's `session_id`,
its sticky-routing key, so the calls stay with one provider endpoint and reuse its prompt cache; a request without a
conversation id keeps the run id. This changes no variable; `AI_PROVIDER_SORT` stays unset.

On 2026-09-30 the user approved mode 4 (`AI_ENABLE_MODE4`, `app/mode4.py`) and a mode switcher: `AI_MODE_SWITCH` sets the default mode (1 AUTO, 2 ANALYSIS, 3 RESEARCH, 4 MODE4) and `analysis_path` chooses per request. The user chose default 4 on dev; do not change `AI_MODE_SWITCH` without approval.

## Security

Never commit secret values, database URLs, passwords, private keys, Railway tokens, Stockbit JWTs, or GitHub PATs. For a secret change, record only the variable name, Railway scope, action, and verification status. Redact secrets from logs and terminal output.

## History rules

- Never edit an old migration after it has been applied. Add a new migration.
- Do not use GitHub as a row-by-row database mirror. Record data-load metadata and keep operational row history in PostgreSQL load logs.
- Do not claim a Railway deployment succeeded until its exact deployment reaches `SUCCESS`.
- Do not claim a database change succeeded until the live schema/data has been read back and verified.
