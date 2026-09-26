# Database changelog

## 2026-09-26 — Research Plan confirmation: audit values and submit_data_need_spec v2 (migration 20260926_002)

- Status: **applied to `dev` at about 12:40 UTC**, approved by the user as part of the Research Plan rollout. It was run by the temporary one-off service `plan-migrate-job` (`251281c4-9dac-46e2-9e3a-f0008b28aa9f`), deleted afterwards (see `RAILWAY_CHANGELOG.md`).
- Deployment `7a507c80-0f0f-428e-a40a-5619fe03cb0d` inspected the live state read-only, applied the file as one transaction, and read it back. Its own preflight and `$verify$` blocks passed, it committed, and no notice was raised.
- Before (read-only):
  - `ai_research_run_audit_status_check` allowed `COMPLETED`, `NEEDS_CLARIFICATION`, `LIMITED`, `FAILED`;
  - `ai_research_run_audit_response_check` allowed `NULL`, `ANSWER`, `CLARIFICATION`, `LIMITATION`;
  - audit rows: 35 `COMPLETED`/`ANSWER`, 14 `LIMITED`/`LIMITATION`, 2 `NEEDS_CLARIFICATION`/`CLARIFICATION`;
  - `Tool_Catalog`: 62 rows, 25 active; `submit_data_need_spec` v1 and `run_python` v1 inactive at `runtime_commit = "daa05cc"`.
- `database/migrations/20260926_002_research_plan_confirmation.sql`:
  - widens both check constraints: status `AWAITING_CONFIRMATION` and response type `RESEARCH_PLAN_CONFIRMATION` (a Research Plan response is a run outcome like the others);
  - updates the `Column_Catalog` definitions of `status` and `response_type`, and appends the migration to their `source_code_paths` and to `Table_Catalog.source_code_paths` of `AI_research_run_audit`;
  - inserts `submit_data_need_spec` v2 (`is_active = false`, `runtime_commit = "be59c68"`). Its input schema adds the `condition`/`outcome`/`baseline` declarations to `research_governance`, and its limits record the `RESEARCH_PLAN_*` refusals and the `AI_REQUIRE_RESEARCH_PLAN_CONFIRMATION` flag;
  - sets `tool_specific_limits.superseded_by = "v2"` on `submit_data_need_spec` v1;
  - adds `tool_specific_limits.standard_period_return` to `run_python` v1 (helper `saniti.period_return`, flag `AI_ENABLE_STANDARD_PERIOD_RETURN`). Its input schema is unchanged.
- Read back live by the same run:
  - both constraints list the new values;
  - the audit rows are unchanged (35/14/2);
  - the two `Column_Catalog` definitions and the three path arrays carry the migration;
  - `Tool_Catalog`: 63 rows, still 25 active. v2 is inactive with the 12 `research_governance` fields; v1 has `superseded_by = "v2"`; `run_python` v1 has the note;
  - a probe `INSERT` of an `AWAITING_CONFIRMATION`/`RESEARCH_PLAN_CONFIRMATION` row was accepted inside a transaction that was rolled back; 0 probe rows remain.
- The same run then did the standard refresh against live `dev`:
  - `scripts/sync_database_catalog.py`: `Catalog reconciled: 640 physical columns, 19 updated`. `AI_research_run_audit` has 21 columns; the migration had already appended the path to `status` and `response_type`, so the 19 updates are consistent with the refresh copying the new `Table_Catalog` path to the other 19, as in the two previous runs;
  - `scripts/sync_database_schema.py`: `Synchronized 38 tables`. The regenerated `DATABASE_SCHEMA.md` was returned as gzip+base64 chunks and verified by sha256 (`e9b22272…`, 157,617 bytes). Its only changes are timestamp drift and the two constraints and two column definitions above.
- Rehearsed first on a disposable local PostgreSQL 16 database built from the documented structures: a plan row refused before and accepted after, unknown values still refused, readback, and a refused second run.
- No market-data table, market-data row, grant or role was changed.
- Rollback (forward-only): a new migration that narrows the checks again. It would fail while `AWAITING_CONFIRMATION` rows exist, so they would have to be kept or the checks left wide. The `Tool_Catalog` rows are inactive and read by no running service.

## 2026-09-26 — Register the DataNeed tools in Tool_Catalog (migration 20260926_001)

- Status: **applied to `dev`** as part of the approved DataNeed rollout (phase 6). It was run by the temporary one-off service `dataneed-tools-job` (`65be8872-aa0b-4466-86f2-592a212545bd`), deleted afterwards.
- Generated from the market-ai-orc tool definitions as deployed at `daa05cc` (description, strict input schema). The output schemas and limits are summaries of the sandbox and planner contracts.
- The read-only run first (deployment `f32c1d3a-3d77-4329-b3bd-d6c0070612e9`) found a `complete_analysis` v1 row that belongs to market-ai-backend (`META`, still `is_active` for that deactivated service). Because the primary key is `(tool_name, version)`, the file was regenerated to register market-ai-orc's unrelated `complete_analysis` as version `orc-v1`. The backend row is untouched, and `max(version)` for that name is still `v1`.
- Deployment `c4c3d6c2-7690-4652-b353-bf7acb86a89c` applied it as one transaction. Its preflight (none of the seven `(tool_name, version)` pairs exists) and `$verify$` blocks passed, and it committed.
  - Inserts seven inactive `ORCHESTRATOR` rows: `submit_data_need_spec` v1, `prepare_data_bundle` v1, `open_analysis_session` v1, `run_python` v1, `inspect_session` v1, `get_session_output` v1 and `complete_analysis` orc-v1. Their `tool_specific_limits` record the runtime service, `runtime_commit`, the feature flags, executor endpoints and contract limits.
  - Adds `tool_specific_limits.dataneed_flow` to the latest market-ai-orc versions of `create_analysis_spec` (v3), `prepare_analysis_data` (v1), `run_python_analysis` (v4), `get_analysis_result` (v3) and `get_dataset_manifest` (v1). The note names the DataNeed tool that replaces each one while `AI_ENABLE_DATANEED` is on. The key is new, so existing `model_facing` notes are kept.
- Read back live in a read-only session by the same run:
  - `Tool_Catalog` went from 55 to 62 rows, and the number of active rows is still 25;
  - the seven new rows are inactive, `ADVANCED`, `ORCHESTRATOR`, with object input and output schemas and `feature_flag = AI_ENABLE_DATANEED`;
  - the five notes are on the latest versions only;
  - older versions and every other row are unchanged.
- Rehearsed first on a disposable local PostgreSQL 16 database built from the documented `Tool_Catalog` structure, including an active backend `complete_analysis` v1: apply, readback, and a refused second run.
- No schema, market-data, catalog-table or role change.

## 2026-09-26 — Add point-in-time join semantics and resample rules to the AI catalogs (migration 20260925_003)

- Status: **applied to `dev` at about 04:56 UTC**, approved by the user as part of the DataNeed rollout. It was run by the temporary one-off service `dataneed-migrate-job` (`e567e0e8-c9ed-4dbf-a72c-de95420de2ae`), deleted afterwards (see `RAILWAY_CHANGELOG.md`).
- Before applying, a read-only run (deployment `9144cfee-1d9b-402e-b8fc-7d00fcccb899`) confirmed:
  - none of the six columns existed;
  - `AI_catalog_relationships` held five rows;
  - each of the five seeds matched exactly one relationship, and no relationship of the verified left tables was left without a seed;
  - `AI_column_catalog` held 138 rows, and no `Column_Catalog` row existed for the new columns.
- Deployment `f6ef3174-a00a-4823-ae30-0588cb18279b` repeated that preflight and applied the file as one transaction. Its own preflight and `$verify$` blocks passed, it committed, and no notice was raised.
- `database/migrations/20260925_003_add_relationship_join_semantics.sql`:
  - adds `AI_catalog_relationships.supported_join_semantics` (`text[]`, not null, default `'{}'`), `left_time_column`, `right_time_column`, `effective_from_column` and `effective_to_column`, with three check constraints (allowed semantics, time columns for `EXACT_DATE`/`AS_OF`, validity columns for `EFFECTIVE_DATED`);
  - adds `AI_column_catalog.resample_aggregation` (`FIRST`, `LAST`, `MAX`, `MIN`, `SUM`, or `NULL`), with a check constraint;
  - seeds `CURRENT_STATE` on `IDX_Stock_Universe` → `Price_Stock_Indonesia_IDX` and `IDX_Broker_Profile` → `IDX_Broker_Summary`, and `EXACT_DATE` with their date columns on the three same-date relationships. It seeds no resample rule;
  - inserts six `Column_Catalog` rows (`PARTIAL`) and appends the migration to `Table_Catalog.source_code_paths` of both tables.
- Read back live in a read-only session by the same run:
  - the six columns with the expected types, nullability and default, and the four check constraints;
  - the relationships: 1 `Price_Stock_Indonesia_IDX`→`Feature_01_Stock_Daily` `EXACT_DATE` (`date`/`date`); 2 `IDX_Stock_Universe`→`Price_Stock_Indonesia_IDX` `CURRENT_STATE`; 3 `IDX_Broker_Profile`→`IDX_Broker_Summary` `CURRENT_STATE`; 4 `IDX_Broker_Summary`→`Feature_02_Broker_Rolling` `EXACT_DATE` (`Date`/`date`); 5 `Feature_02_Broker_Rolling`→`Feature_03_Stock_Broker_Daily` `EXACT_DATE` (`date`/`date`);
  - `resample_aggregation`: 0 of 138 rows set;
  - `Column_Catalog`: 6 rows, ordinal positions 15–19 and 21, `PARTIAL`;
  - `market_sql_governor`, `market_ai_sql_reader`, `market_ai_orc` and `market_ai_catalog_reader` can SELECT the new columns; none can INSERT, UPDATE or DELETE either table.
- The deployed SQL Governor's `POST /v1/catalog/contract` now returns the relationships with their join semantics and time columns. It detects the columns on every call, so no redeploy was needed.
- The same run then did the standard refresh against live `dev`:
  - `scripts/sync_database_catalog.py`: `Catalog reconciled: 640 physical columns, 40 updated`. The 40 updates are the `source_code_paths` of the 19 `AI_catalog_relationships` and 21 `AI_column_catalog` columns, which follow the path the migration appended to `Table_Catalog`;
  - `scripts/sync_database_schema.py`: `Synchronized 38 tables`. The regenerated `DATABASE_SCHEMA.md` was returned as gzip+base64 chunks and verified by sha256 (`9e4b6f05…`, 157,454 bytes). Its only changes are timestamp drift and the six new columns with their four check constraints.
- Rehearsed first on a disposable local PostgreSQL 16 database: apply, readback, a refused second run, and refusal of unknown semantics, `AS_OF` or `EFFECTIVE_DATED` without their columns, and an unknown resample rule.
- No market-data table, market-data row, grant or role was changed. The only live changes are the six catalog columns and their seeded values, their `Column_Catalog` rows and `Table_Catalog` paths, and the refresh's own physical facts and `Database_Table_Status` rows.
- Rollback (forward-only): a new migration that drops the six columns, their constraints and their `Column_Catalog` rows. The deployed services read the columns only when present.

## 2026-09-25 — Purge the retained provider reasoning of the deactivated market-ai-backend (data change, no schema change)

- Approved by the user as part of retiring `market-ai-backend`. That service's hourly cleanup cleared `Analysis_Model_Call.reasoning_details` when `reasoning_expires_at` passed; with the service deactivated the cleanup no longer runs, so the remaining reasoning was purged now instead of on its 2026-10-14 expiry.
- Statement: the backend's own `UPDATE` (`reasoning_details='[]'`, `reasoning_format='PURGED'`, `reasoning_purged_at=clock_timestamp()` for `reasoning_format NOT IN ('NONE','PURGED')`) without the expiry condition.
  - It ran in one transaction through the backend's least-privilege login (`${{market-ai-backend.DATABASE_URL}}`), from the temporary service `legacy-retire-job`, deployment `582b8b26-e849-45c0-993f-847f76335391`.
  - The transaction checked, before committing, that the updated row count equals the retained count, and that no retained or non-empty purged reasoning remains.
  - It was rehearsed first on a scratch PostgreSQL 16 database with the exact DDL of migrations `20260914_037`/`038`, including a second run that updated nothing.
- **Before:** 792 rows; 758 `TEXT` with about 725 KB of reasoning, expiring 2026-10-14; 34 `NONE`.
- **After (read back):**
  - 758 `PURGED` and 34 `NONE`.
  - 0 rows still retain reasoning.
  - Still 792 rows. No row was deleted, and usage, decision summaries and requests are unchanged.
- The legacy queues were empty and were not changed:
  - `Analysis_Request`: 52 `SUCCESS`, 65 `FAILED`, 5 `CANCELLED`.
  - `Analytics_Job`: 14 `SUCCESS`, 5 `FAILED`.
  - `Analytics_Dataset_Snapshot`: 19 `DELETED`.
- No schema, catalog, role or `Tool_Catalog` change. `Tool_Catalog.is_active` is now read by no running service and was deliberately left as it was (see `DATABASE_CATALOG.md`).

## 2026-09-25 — Add AI_table_catalog subject metadata and the two-path tool contracts (migrations 20260925_001 and 20260925_002)

- Status: **applied to `dev` at 11:15 UTC** as part of the approved two-path release. The temporary one-off service `two-path-deploy-job` (`437fba8c-a6a8-4347-b1d5-79c53d75f671`, deployment `b3a4370d-4217-48b4-8cb4-7b5c6137e814`) ran both files in order, each as one transaction, and neither was present before. Its preflight and `$verify$` blocks passed and it committed. The services that read the new columns are deployed separately (see `RAILWAY_CHANGELOG.md`). `DATABASE_SCHEMA.md` is regenerated after the deploys.
- Read back live in a read-only session by the same run:
  - `AI_table_catalog`: the six columns with the expected types, nullability and default (`subject_metadata_status` `'INFERRED'`), and the five new check constraints (`data_domain`, `entity_type`, `asset_type`, frequencies, subject status).
  - The seven rows as seeded below, all `INFERRED`; no row was `UNCLASSIFIED` (no notice raised).
  - `Column_Catalog`: 6 rows, ordinal positions 16–21, `PARTIAL`. `Table_Catalog.source_code_paths` of `AI_table_catalog` now lists the migration.
  - `market_sql_governor`, `market_ai_sql_reader`, `market_ai_orc` and `market_ai_catalog_reader` can SELECT the new columns; none can INSERT, UPDATE or DELETE the table.
  - `Tool_Catalog`: 21 market-ai-orc rows. The four new rows are inactive; `create_analysis_spec` v2 and `run_python_analysis` v3 carry `superseded_by`; `request_data` v2 carries the `model_facing` note. The active market-ai-orc rows are still `discover_catalog`, `get_catalog_details` and `read_catalog_rows`, and the table still has 25 active rows, so market-ai-backend lists nothing new.
- After the three services were deployed, a second run of the same service (deployment `746ed7b0-9fcf-47f5-9e52-16863544bce6`) ran the standard refresh against live `dev`:
  - `scripts/sync_database_catalog.py`: `Catalog reconciled: 634 physical columns, 21 updated`. The 21 updates are the `source_code_paths` of the `AI_table_catalog` columns, which follow the path the migration appended to `Table_Catalog`.
  - `scripts/sync_database_schema.py`: `Synchronized 38 tables`. The regenerated `DATABASE_SCHEMA.md` came back as gzip+base64 chunks and was verified by sha256 (`f92d762c…`, 155,711 bytes). Its only changes are timestamp drift and the six new `AI_table_catalog` columns with their five check constraints.
- `database/migrations/20260925_001_add_ai_table_subject_metadata.sql` extends `public."AI_table_catalog"` with six columns:
  - `data_domain` (NOT NULL), `entity_type` (NOT NULL), `asset_type` (nullable).
  - `supported_frequencies` (NOT NULL; `{STATIC}` exactly when `time_column` is NULL).
  - `time_semantics`.
  - `subject_metadata_status` (NOT NULL, default `INFERRED`).
  - Values are syntax-checked (`^[A-Z][A-Z0-9_]{1,39}$`, a bounded frequency list), not enumerated in code.
  - It seeds the seven approved tables:
    - `MARKET / STOCK / IDX_EQUITY` with `{1D}` for the price, feature and broker-summary tables.
    - `MARKET / STOCK / IDX_EQUITY` with `{STATIC}` for `IDX_Stock_Universe`.
    - `MARKET / BROKER / NULL` with `{STATIC}` for `IDX_Broker_Profile`.
    - Every seeded row stays `INFERRED`; nothing is marked VERIFIED.
  - Registers the six columns in `Column_Catalog` (`PARTIAL`: defined by this migration, not verified end-to-end; the earlier draft used `NEEDS_REVIEW`, which `DATABASE_CATALOG.md` reserves for columns without an established meaning) and adds the migration to `Table_Catalog.source_code_paths`.
- `database/migrations/20260925_002_register_two_path_tools.sql` inserts four `Tool_Catalog` rows, all `is_active=false`. They are generated from the market-ai-orc tool definitions:
  - `get_dimension_values` v1 (`DISCOVERY`: the canonical values of a groupable text dimension of a static table; at most 200 values, a 2000-value scan limit, no counts);
  - `create_analysis_spec` v3 (Analysis Spec V2, including `PERIOD_STAT`, segments, `GROUP_CORRELATION`/`GROUP_PAIR`, and the research designs);
  - `prepare_analysis_data` v1 (backend DataRequestCompiler);
  - `run_python_analysis` v4 (input bundle).
  - It also marks `create_analysis_spec` v2 and `run_python_analysis` v3 `superseded_by`, and records that model-facing `request_data` is behind `AI_ENABLE_REQUEST_DATA`.
- Local rehearsal on disposable PostgreSQL 16 databases, both dropped afterwards:
  - **20260925_001**, on the catalog DDL of migration 20260922_001 with documented `Table_Catalog`/`Column_Catalog` structures.
    - Seeded values read back as listed above; 6 `Column_Catalog` rows (`PARTIAL`, rehearsed again after the status change); the `Table_Catalog` path was appended.
    - The checks refused a lowercase domain, `{1D}` on a static table, an unknown frequency, and a NULL `entity_type`.
    - A second run was refused by the preflight.
  - **20260925_002**, on a `Tool_Catalog` built from its documented structure and check constraints: four inactive rows inserted; the superseded and `request_data` notes were written. The file was regenerated after the dimension-values tool and the Q3/Q6/Q7 and research-design contract changes, and again after the repair-friction fixes (`spec_version` now reaches the model as an enum, scope provenance accepts `CATALOG_RESOLVED`, two new approved defaults), and again after the actionable-message changes (the calculation `provenance` field now tells the model that `CATALOG_RESOLVED` is not valid there; the description covers chained datasets, open-ended periods and the `PERIOD_RETURN` base). It had never been applied. Each regeneration was rehearsed again with the same result.
- No market-data table, market-data row, Governor grant or role was changed; the only live changes are the `AI_table_catalog` columns and rows above, their catalog rows, the four inactive `Tool_Catalog` rows, and the refresh's own `Column_Catalog` physical facts and `Database_Table_Status` rows.

## 2026-09-24 — Create AI_research_run_audit and register the Research AI tool contracts (migration 20260924_004)

- Applied `database/migrations/20260924_004_create_research_run_audit.sql` to `dev` at 12:11 UTC. It was run by the temporary one-off service `research-deploy-job` (`8a6534be-787a-4971-8666-6de0b60c9537`, deployment `539a778e-2b47-411f-a42a-c19ee919334f`), which was deleted afterwards. The migration is one transaction; its preflight and `$verify$` blocks passed and it committed.
  - Creates `public."AI_research_run_audit"`: one INSERT-only summary row per market-ai-orc run (question, final answer, their sha256, evidence label, gate outcome, limitations, number provenance, experiments, datasets by id and checksum, budget, model, tool calls, tokens, duration, sandbox summary status).
    - 21 columns, primary key `request_id`, and nine check constraints (request id pattern, status, response type, gate, hashes, text lengths, JSON types, counts, sandbox status).
    - Index `ai_research_run_audit_recorded_idx` on `recorded_at`.
  - Creates the NOLOGIN role `market_ai_research_audit_writer` with INSERT only on that table, granted to `market_ai_orc`. `PUBLIC` is revoked.
  - Registers the table in `Table_Catalog` (`System`, `VERIFIED`) and its 21 columns in `Column_Catalog`.
  - `Tool_Catalog`: inserts `create_analysis_spec` v2, `run_python_analysis` v3 and `get_analysis_result` v3 at `runtime_commit="0e0234c"`, all `is_active=false`, and marks `create_analysis_spec` v1, `run_python_analysis` v2 and `get_analysis_result` v2 with `superseded_by`. The capabilities purpose names the Research AI features.
- Read back live in a read-only session (deployment `22721042-d899-4abc-9730-86de42b6a5c7`):
  - 21 columns with the expected types, nullability, and defaults; 25 constraints in `pg_constraint` (15 not-null, 1 primary key, 9 checks); 2 indexes (the primary key and `ai_research_run_audit_recorded_idx`).
  - `market_ai_research_audit_writer`: `rolcanlogin=false`, `rolsuper=false`.
  - `market_ai_orc`:
    - Privileges on the table: INSERT true; SELECT, UPDATE, DELETE and TRUNCATE all false.
    - Memberships: `market_ai_catalog_reader`, `market_ai_preview_reader`, `market_ai_research_audit_writer`.
  - `market_sql_governor`, `market_ai_sql_reader`, `market_ai_catalog_reader` and `market_ai_preview_reader` have no privilege on the table, and neither does `PUBLIC`.
  - **Also found:** `pgweb_reader` has SELECT on the new table. The migration did not grant it; it comes from default privileges for tables created by `postgres`, set outside this repository for the `pgweb` viewer. It is recorded here and not changed.
  - `Table_Catalog` row present (`System`, `VERIFIED`); 21 `Column_Catalog` rows; 0 audit rows before the release.
  - 17 market-ai-orc `Tool_Catalog` rows; the only active ones are still `discover_catalog`, `get_catalog_details` and `read_catalog_rows`.
- First live writes, by the deployed orchestrator through `RESEARCH_AUDIT_DATABASE_URL` (the `market_ai_orc` login): 5 rows, one per PoC run (`poc-1-standard` … `poc-5-governor`), read back by a read-only session. See `RAILWAY_CHANGELOG.md` for the runs.
- The rehearsal before applying ran the chain `20260923_003` → `20260924_003` and then this migration on a scratch database. It covered the preflight refusal, the rerun refusal, the privilege denials, a login rotation with `scripts/provision_market_ai_orc_login.py` (which now keeps the audit grant), and the auditor INSERT then `ALREADY_RECORDED`.
- No market-data table, SQL Governor grant, or PostgreSQL source data was changed.

## 2026-09-24 — Create and populate AI_formula_reference; extend the three ORC catalog tools

- Applied `database/migrations/20260924_003_create_ai_formula_reference.sql` to `dev`, run by the temporary one-off service `ai-formula-reference-setup` (deployment `54548d1e-1236-4d36-9d27-31192c74b5a2`), deleted immediately afterwards.
  - Creates `public."AI_formula_reference"` (8 columns, `calculation_id` primary key, non-empty-id check constraint). `GRANT SELECT` to `market_ai_catalog_reader` only; `REVOKE ALL FROM PUBLIC`. Inserts the matching `Table_Catalog` row and 8 `Column_Catalog` rows (dynamically read back from `information_schema`).
  - Unlike the `AI_research_catalog` rollout, the three `market-ai-orc` `Tool_Catalog` rows were already `is_active=true`, so this single migration extends their `input_schema`/`tool_specific_limits` with `FORMULAS` support (new `sections` enum value, `formula_ids` argument, `row_caps.formulas=50`, `AI_formula_reference` added to `read_catalog_rows`'s `catalog_name` enum) and stamps `runtime_commit="cb97fac"` immediately, at the user's explicit request. The migration's own preflight/verify blocks passed: table did not already exist; all three tool rows were active beforehand; afterward, column count is 8, `market_ai_catalog_reader` has SELECT only (no write), `market_ai_sql_reader` (SQL Governor) has no access, and all three rows carry `runtime_commit="cb97fac"`.
- Ran `scripts/import_ai_formula_reference.py` against the reviewed `AI_Calculation_Formula.xlsx` (SHA256 `09326f986728a97b8e5c885c46c8270634b541d975f7090067f184ae3b22a30d`, sheet `Calculation_Catalog`) in the same service run. Transactional: locked the table, confirmed it was empty, inserted 200 rows, read every field of every row back and compared to the source before committing. Workbook content was never written to Git or logged.
- Live verification after the migration and import: `SETUP_OK columns=8 rows=200 catalog_reader_select=True governor_select=False commits={'discover_catalog': 'cb97fac', 'get_catalog_details': 'cb97fac', 'read_catalog_rows': 'cb97fac'}`.
- After `market-ai-orc` redeployed (see `RAILWAY_CHANGELOG.md`), independently verified all three tools end-to-end against live dev data using the real `market_ai_orc` login: `discover_catalog` reports `formula_catalog.formula_count=200` and excludes it from the market-table list; `get_catalog_details` with `sections=["FORMULAS"]` returns 200 total (50 per page cap) and a full 8-field definition when narrowed by `formula_ids`; `read_catalog_rows` with `catalog_name="AI_formula_reference"` pages through all 200 rows (5 pages at `page_size=50`), 8 columns each.
- Ran `scripts/sync_database_catalog.py` (`Catalog reconciled: 607 physical columns, 0 updated`) and `scripts/sync_database_schema.py` (`Synchronized 37 tables`) against live dev in a temporary service, fetched the regenerated `DATABASE_SCHEMA.md` over HTTPS, diffed it locally, and applied it; the only content changes are routine freshness-timestamp drift on unrelated tables and the new `AI_formula_reference` section.
- No table, column, or grant belonging to the SQL Governor's seven-table market-data allowlist was changed. No production environment was touched.

## 2026-09-24 — Create and populate AI_research_catalog; activate the three ORC catalog tools

- Reviewed and applied `database/migrations/20260924_001_create_ai_research_catalog.sql` (authored on `codex/ai-research-catalog`, PR [#1](https://github.com/rednightt33/saniti/pull/1); content applied verbatim, unmodified) to `dev`, run by the temporary one-off service `ai-research-catalog-setup` (deployment `da1c4d66-324c-4379-90ce-599c9223a138`), deleted immediately afterwards.
  - Creates `public."AI_research_catalog"` (19 columns, `method_id` primary key, JSON-array and non-empty-status check constraints). `GRANT SELECT` to `market_ai_catalog_reader` only; `REVOKE ALL FROM PUBLIC`. Inserts the matching `Table_Catalog` row and 19 `Column_Catalog` rows (dynamically read back from `information_schema`, not hand-typed).
  - The migration's own preflight/verify blocks passed: table did not already exist; the three market-ai-orc `Tool_Catalog` rows (`discover_catalog`, `get_catalog_details`, `read_catalog_rows`) existed and were `is_active=false` beforehand; afterward, column count is 19, `market_ai_catalog_reader` has SELECT only (no write), and `market_ai_sql_reader` (SQL Governor) has no access to the new table.
- Applied `database/migrations/20260924_002_activate_ai_research_catalog_tools.sql` (new; not part of PR #1) in the same run, setting `is_active=true` and `tool_specific_limits.runtime_commit="aa7b231"` for the three tools above, at the user's explicit request (PR #1 had deliberately left them inactive). Preflight required exactly those three rows to be inactive; verify confirmed exactly those three are now active at that commit.
- Ran `scripts/import_ai_research_catalog.py` against the reviewed `Saniti_DB_AI_Research_Catalog.xlsx` (SHA256 `49b1bfff36674d6442b984e2321b2d5ad3c81e288204a119ede220aa84a6c1e1`, sheet `AI_Research_Catalog`) in the same service run. Transactional: locked the table, confirmed it was empty, inserted 18 rows, read every field of every row back and compared to the source before committing. Workbook content was never written to Git or logged.
- Live verification after both migrations and the import: `SETUP_OK columns=19 rows=18 catalog_reader_select=True governor_select=False active_tools=['discover_catalog', 'get_catalog_details', 'read_catalog_rows']`.
- Deployed the matching `market-ai-orc` code (RESEARCH section support in the three tools; see `RAILWAY_CHANGELOG.md`) and independently verified all three tools end-to-end against live dev data using the real `market_ai_orc` login (not a disposable test database): `discover_catalog` reports `research_catalog.method_count=18` with `{"REFERENCE_ONLY": 18}` and excludes it from the market-table list; `get_catalog_details` with `sections=["RESEARCH"]` returns all 18 summarized and a full 19-field definition when narrowed by `method_ids`; `read_catalog_rows` with `catalog_name="AI_research_catalog"` pages through all 18 rows (2 pages at `page_size=10`), 19 columns each, all `implementation_status="REFERENCE_ONLY"`.
- Ran `scripts/sync_database_catalog.py` (`Catalog reconciled: 599 physical columns, 0 updated` — already consistent) and `scripts/sync_database_schema.py` (`Synchronized 36 tables`) against live dev in a temporary service, fetched the regenerated `DATABASE_SCHEMA.md` over HTTPS, diffed it locally, and applied it; the only content changes are routine freshness-timestamp drift on unrelated tables and the new `AI_research_catalog` section.
- No table, column, or grant belonging to the SQL Governor's seven-table market-data allowlist was changed. No production environment was touched.

## 2026-09-24 — Register the fact/analysis split tools in Tool_Catalog (migration 009)

- Applied `database/migrations/20260923_009_register_fact_and_analysis_tools.sql` to `dev` at about 01:27 UTC, run by the temporary one-off service `split-deploy-job` (deployment `ebaa6479-6712-47d4-8020-76a5c9c65200`), before the `AI_research_catalog` and `AI_formula_reference` rollouts below. That run's stdout was never collected by Railway (only `Starting Container` appears, although the deployment reached `SUCCESS`). The migration is a single transaction whose `$verify$` block raises on any mismatch, and `lookup_fact` exists, so it committed with its checks passing: 11 inactive market-ai-orc rows at `runtime_commit="27e118a"`, the 3 superseded v1 rows still at `81475ae`, no active market-ai-orc row.
  - It marks `request_data`, `run_python_analysis`, and `get_analysis_result` v1 with `superseded_by="v2"` and inserts `request_data` v2 (dataset-only), `lookup_fact` v1, `create_analysis_spec` v1, `run_python_analysis` v2, and `get_analysis_result` v2, all `is_active=false`. The six unchanged market-ai-orc rows moved to `runtime_commit="27e118a"`, and `get_system_capabilities` took its new purpose (it reports `fact_lookup`).
- Read back at 09:30 UTC by an idempotent rerun of the same job (deployment `1cd6b9b8-91cd-4100-a4b8-f5fe6d325d9a`; it found `lookup_fact` and skipped the SQL). There are 14 market-ai-orc rows:
  - 8 inactive at `27e118a`: `create_analysis_spec` v1, `get_analysis_result` v2, `get_dataset_manifest` v1, `get_system_capabilities` v1, `lookup_fact` v1, `preview_table_rows` v1, `request_data` v2, `run_python_analysis` v2.
  - 3 superseded v1 rows at `81475ae`.
  - 3 active rows at `cb97fac`: `discover_catalog`, `get_catalog_details`, `read_catalog_rows`. They were among the 11 when 009 committed; migrations `20260924_002` and `20260924_003` below later activated them and restamped them `aa7b231` and then `cb97fac`.
  - 25 active rows in the whole table, and `get_system_capabilities.purpose` names fact lookup.
- No market-data table, SQL Governor grant, or PostgreSQL source data was changed.

## 2026-09-23 — Register the Python analysis tools in Tool_Catalog

- Applied `database/migrations/20260923_008_register_python_analysis_tools.sql` to `dev`. It was run by the temporary one-off service `sandbox-acceptance-job` (deployment `c6cf05e3-16a5-43c0-b328-8bda4e8ef1b4`), which was deleted afterwards.
- It adds three `ORCHESTRATOR` rows (`v1`, `is_active = false`):
  - `get_dataset_manifest` (`DISCOVERY`/`RETRIEVAL`, executor `market-sql-governor`);
  - `run_python_analysis` (`ADVANCED`/`COMPUTATION`, executor `market-python-sandbox`);
  - `get_analysis_result` (`ADVANCED`/`RETRIEVAL`, executor `market-python-sandbox`).
- The input schemas were generated from the deployed market-ai-orc registry. The advertised ceilings mirror the code defaults; the Governor and sandbox configuration remain the enforcement layer.
- It moves the six existing market-ai-orc rows from `runtime_commit = f63bebc` to `81475ae`, the deployed orc commit.
- Verified by reading back live: 9 market-ai-orc rows, all at `runtime_commit = 81475ae`, none active. market-ai-backend therefore still lists none of them. The migration's own verify block passed as well.
- No table, column, routine, or market-data row changed. `DATABASE_SCHEMA.md`, `Table_Catalog`, and `Column_Catalog` are unchanged.

## 2026-09-23 — Allow MIN/MAX on date columns for the SQL Governor

- Applied `database/migrations/20260923_007_allow_min_max_on_date_columns.sql` to `dev` using the temporary one-off service `orc-mig007-job`, which was deleted afterwards.
- It appends `MIN` and `MAX` to `AI_column_catalog.allowed_aggregations` for every `date` column of the seven approved market-data tables. Existing entries are kept in order.
  - The six affected columns, with their previous values:
    - `Feature_01_Stock_Daily.date` (`COUNT`)
    - `Feature_02_Broker_Rolling.date` (`COUNT`)
    - `Feature_03_Stock_Broker_Daily.date` (`COUNT, COUNT_DISTINCT`)
    - `IDX_Broker_Summary."Date"` (`COUNT, COUNT_DISTINCT`)
    - `Price_Stock_Indonesia_IDX.date` (`COUNT, COUNT_DISTINCT`)
    - `Price_Stock_Indonesia_IDX.query_date` (`COUNT, COUNT_DISTINCT`)
  - Timestamp columns are not included.
- Verified: all six columns now include `MIN`/`MAX`, and no other `AI_column_catalog` row changed.
- Checked live through the Governor API: `MIN(date)`/`MAX(date)` per ticker for BBCA, BBRI, and TLKM returned `INLINE_RESULT` (2018-01-02 to 2026-09-22 each, 72 ms). `SUM(date)` stays rejected.
- No sync job rewrites `AI_column_catalog`; only migrations change it.

## 2026-09-23 — market-sql-governor role, request_data registration, live calibration

- Applied to `dev` (PostgreSQL 18.6, as superuser `postgres`) by the temporary one-off service `orc-governor-setup`, which was deleted afterwards:
  - `20260923_005_create_market_ai_sql_reader.sql`: `NOLOGIN` role `market_ai_sql_reader` with `USAGE` on `public` and `SELECT` on exactly the 5 AI catalogs and 7 approved market-data tables (`Feature_01_Stock_Daily`, `Feature_02_Broker_Rolling`, `Feature_03_Stock_Broker_Daily`, `IDX_Broker_Profile`, `IDX_Broker_Summary`, `IDX_Stock_Universe`, `Price_Stock_Indonesia_IDX`). It has no write, DDL, or `CREATE` privilege, and the migration's verify block passed.
  - `20260923_006_register_request_data_tool.sql`:
    - Adds `request_data` to `Tool_Catalog` (`QUERY`/`RETRIEVAL`, `ORCHESTRATOR`, `v1`). The input schema is generated from the deployed registry; the advertised ceilings mirror the Governor defaults.
    - Sets `is_active = false`, like the other market-ai-orc rows.
    - Moves the five existing market-ai-orc rows to `runtime_commit = f63bebc`.
    - Verified: 6 inactive rows, 0 visible to market-ai-backend.
- Provisioned login `market_sql_governor` with `scripts/provision_market_sql_governor_login.py`.
  - Memberships: `market_ai_sql_reader` only.
  - Settings: `CONNECTION LIMIT 5`, `default_transaction_read_only=on`, `statement_timeout=60s`, `lock_timeout=2s`, `idle_in_transaction_session_timeout=30s`.
  - Its password exists only as a Railway variable on `market-sql-governor`.
- Live checks as `market_sql_governor`:
  - Readable: the AI catalogs, `Price_Stock_Indonesia_IDX`, `Feature_02_Broker_Rolling`, and `IDX_Broker_Summary`.
  - Denied: `Table_Catalog`, `Analysis_Request`, `Analytics_Job`, `Feature_Catalog`, and `Tool_Catalog`.
  - `DELETE` failed with `ReadOnlySqlTransaction`.
- Live calibration: 13 representative requests through the real Governor, read-only, with the snapshots written to the new bucket.

  | Request | Decision | Estimated scan / plan cost | Result | Runtime |
  |---|---|---|---|---|
  | BBCA latest 20 closes | `INLINE_RESULT` | 2,282 / 71 | 20 rows | 44 ms |
  | Price universe, 365 days | `DATASET_READY` | 192,932 / 27,233 | 195,160 rows | 4.1 s |
  | BBCA full price history | `DATASET_READY` | — | 2,100 rows (2018-01-02..2026-09-22) | 0.15 s |
  | Feature 01 universe, 90 days | `DATASET_READY` | — | 51,551 rows | 0.8 s |
  | Feature 02 BBCA, 90 days | `DATASET_READY` | — | 6,341 rows | 0.5 s |
  | Feature 02 universe, 5 days | `DATASET_READY` | 106,089 / 411,619 | 106,390 rows | 28.8 s |
  | IDX_Broker_Summary BBCA, 60 days | `DATASET_READY` | — | 4,051 rows | 9.9 s |
  | Top BBCA brokers by `SUM("Net Value")` | `INLINE_RESULT` | — | 20 rows | 1.3 s |
  | Feature 03 universe, 30 days | `DATASET_READY` | — | 27,237 rows | 0.5 s |
  | Stock universe | `DATASET_READY` | — | 844 rows | 0.15 s |
  | Price joined to IDX_Stock_Universe | `INLINE_RESULT` | — | 20 rows | 56 ms |
  | Feature 02 joined to Feature 03 | `REJECTED`/`PREAGGREGATION_REQUIRED` | — | nothing executed | 25 ms |
  | Feature 02 universe, 60 days | `DATASET_TOO_LARGE` | about 1.1M estimated rows | streamed 74 s before refusal | 74 s |

- **Fix from the last row.** The 60-day Feature 02 request passed the scan and cost gates, then streamed for 74 s before being refused. That led to commit `0b0ba24`:
  - an `ESTIMATED_RESULT_TOO_LARGE` gate before execution;
  - `SQL_MAX_EXECUTION_SECONDS=60`;
  - `SQL_MAX_PLAN_COST` calibrated to 600,000.
- No table, column, or market-data row was changed. The only catalog change is the `Tool_Catalog` registration above. `DATABASE_SCHEMA.md` covers tables only and is unchanged.

## 2026-09-23 — Update market-ai-orc catalog page limit in Tool_Catalog

- Applied `database/migrations/20260923_004_update_market_ai_orc_catalog_page_limit.sql` to `dev` using a temporary one-off service, which was deleted afterwards (see `RAILWAY_CHANGELOG.md`).
- Changes to the `read_catalog_rows` row: `max_output_bytes` and `max_llm_result_bytes` 40192 → 24192, and `tool_specific_limits.page_max_bytes` 32000 → 16000.
- All five market-ai-orc rows now have `tool_specific_limits.runtime_commit = c1b4e93`.
- The input schemas and descriptions of all five tools are unchanged. This was verified by comparing the registries at `456081d` and `c1b4e93`.
- Verified on live: exactly the five market-ai-orc rows are present, all with `is_active = false`. No market-ai-orc tool is visible to market-ai-backend (0 active rows). No other row changed.

## 2026-09-23 — market-ai-orc read-only catalog and preview access

- Applied three forward-only migrations to Railway project `lucid-patience`, environment `dev` (PostgreSQL 18.6, database `railway`, as superuser `postgres`). They were applied by a temporary one-off Railway service on the private network; see `RAILWAY_CHANGELOG.md`.
  - `20260923_001_create_market_ai_catalog_reader.sql`: `NOLOGIN` role `market_ai_catalog_reader` with `USAGE` on `public` and `SELECT` on exactly the five `AI_*` catalogs.
  - `20260923_002_create_market_ai_preview_interface.sql`:
    - Creates `public.ai_preview_table_rows(text) RETURNS json`. It is `SECURITY DEFINER`, pins `search_path = pg_catalog, pg_temp`, and hard-codes the allowlist of seven tables, a fixed `ORDER BY`, and `LIMIT 20`.
    - The function is owned by `NOLOGIN` role `market_ai_preview_owner`, which has `SELECT` on exactly those seven tables and no write privilege.
    - Only `NOLOGIN` role `market_ai_preview_reader` can `EXECUTE` it (`PUBLIC` is revoked). That role has no table privilege.
    - Tables served: `Feature_01_Stock_Daily`, `Feature_02_Broker_Rolling`, `Feature_03_Stock_Broker_Daily`, `IDX_Broker_Profile`, `IDX_Broker_Summary`, `IDX_Stock_Universe`, `Price_Stock_Indonesia_IDX`.
  - `20260923_003_register_market_ai_orc_catalog_metadata.sql`:
    - Registers the five market-ai-orc tools in `Tool_Catalog` (`get_system_capabilities`, `discover_catalog`, `get_catalog_details`, `read_catalog_rows`, `preview_table_rows`; `execution_type = ORCHESTRATOR`, `version = v1`).
    - Their input schemas were generated from the deployed registry (commit `456081d`).
    - They have `is_active = false` on purpose, because market-ai-backend lists every active `META`/`DISCOVERY`/`QUALITY` row to its own model. Activation is owned by the market-ai-orc registry and recorded in `tool_specific_limits.runtime_service`.
    - Also appends `public.ai_preview_table_rows(text)` to `Table_Catalog.related_functions` for the seven tables.
- Provisioned login `market_ai_orc` with `scripts/provision_market_ai_orc_login.py`.
  - Memberships: `market_ai_catalog_reader` and `market_ai_preview_reader` only.
  - Settings: `CONNECTION LIMIT 5`, `default_transaction_read_only=on`, `statement_timeout=5s`, `lock_timeout=2s`, `idle_in_transaction_session_timeout=15s`.
  - Its password exists only as a Railway variable on `market-ai-orc`.
- Live verification as `market_ai_orc`, with counts only (`scripts/verify_market_ai_orc_data_access.py`):
  - `read_catalog_rows` traversed every catalog to the end with rows read = distinct keys = `total_rows`: `AI_table_catalog` 7, `AI_column_catalog` 138, `AI_catalog_relationships` 5, `AI_calculation_catalog` 91 (5 pages), `AI_data_coverage` 14,070 (146 pages).
  - `preview_table_rows` returned exactly 20 rows with all columns for each of the seven tables.
  - Direct `SELECT` on each of the seven tables, `Tool_Catalog`, and `Table_Catalog` was denied. Preview calls for `AI_table_catalog` and `Tool_Catalog` were denied. `DELETE` on `AI_table_catalog` failed with `ReadOnlySqlTransaction`.
- Preview query plans on live data, measured with `EXPLAIN (ANALYZE, BUFFERS)`. Every plan is index-backed and runs in under 0.5 ms; no index was added.

  | Table | Estimated rows | Plan | Execution | Buffers |
  |---|---|---|---|---|
  | `Feature_02_Broker_Rolling` | 45.2M | Backward `date_board_ticker_idx` + incremental sort | 0.10 ms | 29 |
  | `IDX_Broker_Summary` | 43.7M | Backward primary key | 0.06 ms | 24 |
  | `Feature_03_Stock_Broker_Daily` | 2.25M | Backward `date_board_ticker_idx` | 0.03 ms | 9 |
  | `Feature_01_Stock_Daily` | 1.30M | Backward `date_idx` + incremental sort | 0.41 ms | 49 |
  | `Price_Stock_Indonesia_IDX` | 1.30M | Backward `date_idx` + incremental sort | 0.21 ms | 25 |
  | `IDX_Stock_Universe` | 844 | Primary key | 0.03 ms | 5 |
  | `IDX_Broker_Profile` | 112 | Primary key | 0.01 ms | 3 |
- No table, column, market-data row, catalog row other than the five new `Tool_Catalog` rows and the seven `related_functions` arrays, or `market-ai-backend` object was changed. `DATABASE_SCHEMA.md` covers tables only and is unchanged.

## 2026-09-22 — Add AI-facing catalogs and source-derived coverage

- Applied forward-only migration `database/migrations/20260922_001_create_ai_catalogs.sql` to Railway project `lucid-patience`, environment `dev`. It created `AI_table_catalog`, `AI_column_catalog`, `AI_catalog_relationships`, `AI_calculation_catalog`, and `AI_data_coverage` without replacing the legacy catalogs.
- Seeded exactly seven approved table rows, 138 column rows, five safe-relationship rows, and 91 active Feature calculation rows (Feature 01 = 29, Feature 02 = 38, Feature 03 = 24). Registered all five new tables and 85 physical columns in the legacy catalogs; post-sync totals are 32 registered tables and 580 registered columns.
- Ran the initial full raw-source coverage successfully. `AI_data_coverage` contains 14,070 rows: 844 price tickers, 4,125 Broker Summary tickers, the corresponding source-derived Feature expectations, and dataset/snapshot summaries. Feature 01 has 839 ticker expectations confirmed by `Feature_Status` and five unverified; Feature 02/03 remain explicitly `UNVERIFIED` / `MANUAL_REFRESH_REQUIRED`.
- Verified the coverage job reads only raw price, Broker Summary, universe/profile snapshots, `Feature_Status`, and its own catalog/coverage tables. It never scans Feature 01–03 and writes only `AI_data_coverage`.
- Exact before/after checks showed no change to Feature 01–03 row counts, date ranges, or Feature 02/03 maximum write timestamps. No raw-source row, Feature formula, Feature refresh routine, backend service, or legacy-catalog row was removed.
- Catalog synchronization reconciled 580 physical columns and schema synchronization recorded 35 public tables.

## 2026-09-14 — Feature 03 v2 Investor-Type rebuild

- Applied forward-only migration `20260914_047_define_feature_03_investor_type_v2.sql` after the Feature 02 Investor-Type cutover. It replaced only the Feature 03 refresh routine and semantic contract; the physical Feature 03 schema and primary key remain `(ticker, market_board, date)`.
- `foreign_net_value` and `domestic_net_value` now sum `Feature_02_Broker_Rolling.net_value_1d` by source `investor_type` (`Foreign`/`Domestic`). They are point-in-time source investor identities and must not be interpreted as broker domicile. Broker breadth, rankings, top-three flows, HHI, and current broker-profile classifications first sum both Investor Types per broker, preserving their broker-level grain.
- Ran the transactionally safe full historical rebuild through `refresh_feature_03_stock_broker_daily(NULL, NULL)`: 2,268,015 rows, 2016-01-04 through 2026-08-31, were replaced in one committed run. The core identity check returned zero violations: `foreign_net_value + domestic_net_value = total_buy_value - total_sell_value` for every stored row.
- Independent raw-Broker-Summary samples passed all 20 calculated fields: BBCA/Regular/2026-08-31 (81 brokers), BBCA/Nego/2026-08-31 (12 brokers, zero-net edge case), and ADRO/Tunai/2026-08-31 (one-broker zero-net edge case). `scripts/validate_feature_03.py` now independently reconstructs the v2 contract for full read-only reconciliation; `scripts/check_feature_03_sample.py` independently aggregates source Investor Type and broker totals.
- Deactivated 24 v1 Feature Catalog definitions, activated 24 v2 definitions, updated column/table catalog evidence and the Feature 02 → Feature 03 safe-join contract to v3. No raw table, Feature 01, Feature 02 row, price cron, or Railway service changed. Feature 03 still has no automatic worker.
- Applied `20260914_048_record_feature_03_v2_rebuild_status.sql` to record `FULL_REBUILD_V2` and the materialization timestamp in `Database_Table_Status`; regenerated `DATABASE_SCHEMA.md` for all 30 public tables.

## 2026-09-14 — Feature 02 Investor-Type v2 cutover and v1 storage removal

- Applied `20260914_043_cutover_feature_02_investor_type.sql` to Railway project `8aef1702-030b-49cb-9df7-5ac2e0a42691`, environment `dev`, Postgres service. The migration first passed a rollback-only dry run. It promoted the validated shadow to canonical `Feature_02_Broker_Rolling`, deactivated 38 v1 Feature Catalog definitions, activated 38 v2 definitions, reconciled Table/Column/Relationship catalogs, granted `market_ai_reader` SELECT, and dropped the old 42,598,713-row v1 table with `RESTRICT` (no `CASCADE`).
- Readback PASS: canonical v2 has 45,229,673 rows, 38 physical and cataloged columns, key `(ticker, market_board, broker, investor_type, date)`, no `broker_type` column, no shadow table, and two active v2 relationship contracts. Database size decreased from approximately 36 GB to 23 GB before the new daily index.
- The existing Feature 3 refresh routine was made compatibility-safe by summing Feature 02 investor types per broker before its existing broker-level formulas. A BBCA/2026-08-31 two-board refresh returned exactly the previous stored values; the test transaction was rolled back. **Feature 3 data were not deleted, rebuilt, or redefined.** Its Domestic/Foreign columns still use current broker-profile domicile; source-Investor-Type Feature 3 is a separate future project.
- Applied `20260914_044_clarify_feature_02_v2_catalog.sql` to clarify positive/negative daily net meanings, the canonical materialization timestamp, and explicit Investor-Type source/partition notes. All 91 active semantic definitions audited PASS: Feature 1 = 29, Feature 2 v2 = 38, Feature 3 v1 = 24. Physical catalog reconciliation PASS at 495 columns.
- Retired v1 backfill and validation scripts now fail before modifying data on the v2 schema. `scripts/backfill_feature_02_v2.py` and `scripts/validate_feature_02_v2_sample.py` target the canonical name; Feature 02 refresh remains manual, not automatic.
- Post-cutover BBCA/AK/Regular/2026-08-31 sample PASS: exact source reconciliation had zero missing, extra, or 1D mismatches for the ticker; all 31 independently recalculated fields passed for both Domestic and Foreign (62 comparisons, maximum floating difference `3.33e-16`).
- Bounded pre-index plan for a single Regular-board date read 1,416,602 shared buffers via parallel sequential scan and took 2,136.7 ms. Applied `20260914_045_index_feature_02_v2_daily_reads.sql` to restore `(date, market_board, ticker)` for daily cross-ticker access. The post-index query used an index-only scan, 1,325 shared buffers, and 67.0 ms; the index is 378 MB. Database size remained about 23 GB, well below the pre-cutover ~36 GB.
- Applied `20260914_046_record_feature_02_cutover_status.sql` to record the Feature 02 cutover timestamp in `Database_Table_Status` and add the compatibility routine migration to Feature 3's code provenance. Reconciled all 495 physical catalog columns and regenerated `DATABASE_SCHEMA.md` for 30 public tables.

## 2026-09-14 — Separate query sandbox and statistical validation queues

- Applied forward-only migration `20260914_041_split_query_and_statistical_workers.sql` to Railway PostgreSQL `Postgres` in `dev`.
- Added `Analytics_Job.execution_class` with `QUERY_SANDBOX` and `STATISTICAL_VALIDATION`; replaced the claim index with `(execution_class, status, created_at, lease_expires_at)` for class-scoped `SKIP LOCKED` leasing.
- Replaced the single `run_analytics_job` catalog entry with deterministic `route_analysis`, `run_query_sandbox`, and `run_statistical_validation` tools and separate advertised resource limits.
- Expanded immutable snapshot provenance from Feature-only to catalog-approved raw/Feature inputs. The backend remains the only PostgreSQL reader and snapshot writer.
- Registered the new column in `Column_Catalog`, refreshed both affected `Table_Catalog` definitions, and created zero-login worker roles with zero public-table grants.
- Live verification passed: three active routing/worker tools, old generic tool inactive, class column and composite partial claim index present, catalog status VERIFIED, and zero table grants for both worker roles.

## 2026-09-14 — Controlled backend raw-data reads

- Applied `20260914_042_grant_backend_controlled_raw_reads.sql` so only `market_ai_app` can SELECT the five catalog-approved raw/reference tables used to build analytical snapshots.
- Explicitly revoked raw-table mutation privileges from the backend and all privileges from query/statistical worker roles. Model-authored PostgreSQL SQL remains prohibited; table/column/filter/size enforcement remains in the backend.

## 2026-09-14 — Activate generic bounded Analytics Worker

- Applied forward-only migration `database/migrations/20260914_040_create_generic_analytics_worker.sql` to Railway `dev`. It created `Analytics_Dataset_Snapshot` and `Analytics_Job`, registered all 44 new physical columns with evidence-backed definitions, activated one generic `run_analytics_job` tool, and superseded the Release 1 worker-denial Golden expectation.
- The backend performs catalog validation and controlled Feature reads, enforces 50,000 input rows, 30 columns, four datasets, 20 MiB input, planner and date limits, serializes one immutable `.json.gz` snapshot, and stores only checksum/provenance/retention metadata in PostgreSQL. The isolated worker has no PostgreSQL/raw/Feature or bucket credentials; it receives one leased job and short-lived snapshot URL.
- The worker accepts one `SELECT/WITH` DuckDB computation with external access disabled. DDL, DML, `COPY`, `ATTACH`, `INSTALL`, `LOAD`, `PRAGMA`, secrets, and file/network readers are rejected. Runtime, memory, retry, result-row, and result-byte limits are copied into each job and enforced again at completion.
- First Golden Test `R2_001_TELCO_BROKER_STREAK_FORWARD_10PCT` PASS in run `7c863e38-f479-4f14-a981-fd2463aee6c5`: 42,446 bounded input rows across Feature 1 and Feature 2, 100 ranked result rows, two reproducible component query hashes, automatic evidence, 15.079 seconds end-to-end, and idempotent same-label replay to the same job.
- Three pre-PASS failures were retained for audit and resolved without changing Feature data: local Boto3 required `AWS_CA_BUNDLE` for the workstation Avast CA; `Content-Encoding:gzip` caused HTTP auto-decompression before checksum and was replaced with `application/gzip`; the test harness sent booleans to integer counters and then omitted the nonempty success snapshot required by `Analysis_Request`. Superseded nonterminal harness rows were explicitly marked terminal.
- Catalog reconciliation PASS at 532 physical columns; `DATABASE_SCHEMA.md` now covers 31 public tables. No raw/Feature row, Feature formula, Feature 2 v2 cutover, Feature refresh schedule, or unrelated service changed.

## 2026-09-14 — Register evidence-gated analyst finalization policy

- Applied forward-only migration `database/migrations/20260914_039_harden_analysis_finalization_and_compaction.sql` to the `dev` PostgreSQL service. It changed catalog metadata only; no raw, Feature, evidence, or analysis-result row was rewritten.
- Registered stopping policy v2 for all eight active analytical data tools: after sufficient consolidated evidence is recorded, further data calls are blocked, `complete_analysis` is the only allowed tool, and a successful completion permits only the strict final answer.
- Updated `check_data_quality` metadata so `WARNING` and source-valid `PASS` anomalies explicitly continue analysis while impossible/invalid `FAIL` blocks only the affected conclusion.
- Registered reserved finalization budget, exact final-schema feedback with at most two retries, and preservation of decisive values, warnings, evidence IDs, and query hashes during context compaction.
- Catalog reconciliation PASS at 488 physical columns; regenerated `DATABASE_SCHEMA.md` from 29 public tables. Live backend verification PASS and deterministic Golden Test run `f597da6b-760c-4b4e-8cf0-8ef0b74f6874` passed 16/16.
- Final controlled A/B wrote 20 durable analysis requests, 15 completed evidence packages, and 180 bounded `Analysis_Model_Call` audit rows. All 15 successful answers cited evidence that exists for their request, and zero data/QC call ran after the evidence gate. No raw or Feature row was changed by the test.
- Final live verification remained PASS and deterministic Golden Test run `801f4f11-5d8a-4774-9fa6-58bf60f68f47` passed 16/16. The full compaction comparison and retained `DISABLED` operational decision are documented in `MARKET_AI_AB_TEST_2026-09-14.md`.

## 2026-09-14 — Add per-model-call audit and conditional quality policy

- Applied forward-only migration `database/migrations/20260914_037_create_analysis_model_call_audit.sql` to Railway `dev` PostgreSQL. It created `Analysis_Model_Call` with one row per `Analysis_Request` provider-call iteration, a foreign key with cascade lifecycle, unique request/iteration key, bounded token fields, stage/provider/reasoning checks, and a selective retention-deadline index.
- The table stores exact provider/model/stage/tool-family context, per-call input/output/reasoning tokens, backend active-context estimate, a concise decision summary, and only reasoning blocks actually returned by the provider. It does not copy prompts or tool results and does not reconstruct hidden chain-of-thought. Raw reasoning has a configurable expiry; cleanup clears `reasoning_details` while preserving the audit row and long-term decision summary.
- Registered the table as `VERIFIED` and all 21/21 final columns in `Table_Catalog`/`Column_Catalog`; granted only analysis logger SELECT/INSERT/UPDATE plus its identity sequence. Post-correction live validation reported 29 physical tables, 26 cataloged tables, 488/488 cataloged columns, zero unregistered required tables, and zero missing columns.
- Updated active `check_data_quality` metadata: QC is conditional and scoped across all tools, not an automatic full-period scan. `WARNING` and source-valid `PASS` anomalies continue analysis; only impossible/invalid `FAIL` blocks the affected conclusion.
- Raw tables, Feature rows/formulas, Feature 2 v1/v2 activation state, and calculation schedules were unchanged.
- Pre-commit recovery audit found that an expired-lease retry restarts local iteration numbering. Because applied migration 037 is immutable, corrective migration `database/migrations/20260914_038_make_model_call_audit_retry_safe.sql` adds `attempt_number` and changes uniqueness to `(request_id,attempt_number,iteration_number)`; the backend obtains the attempt number atomically from `Analysis_Request.attempt_count`.
- Live DeepSeek acceptance created eight model-call rows for successful request `9ad62d13-cc26-492c-8f3a-769d9d4e3741`; their per-call input/output/reasoning counts reconcile to the request totals, retained reasoning blocks have configured expiry timestamps, and no full-period QC step was executed. Backend verification PASS, Feature Catalog semantic audit remained 91/91, and Golden Test run `5d2a8f03-58af-4807-ae8e-7dc4ab5f1491` passed 16/16.

## 2026-09-14 — Start Investor-Type-preserving Feature 02 shadow rebuild

- Confirmed the production `Feature_02_Broker_Rolling` aggregates `IDX_Broker_Summary."Investor Type"` away and stores current `IDX_Broker_Profile.broker_type`; this is valid only as combined broker flow and cannot represent Domestic versus Foreign investor activity. The canonical table and its 42,598,713 rows were not changed.
- Applied forward-only migration `database/migrations/20260914_034_create_feature_02_investor_type_shadow.sql`, creating unreleased `Feature_02_Broker_Rolling_v2` with grain `(date,ticker,broker,investor_type,market_board)` and primary key `(ticker,market_board,broker,investor_type,date)`. `investor_type` is the exact point-in-time source label; `broker_classification` remains current profile metadata. Every rolling and 252-observation history partition now includes Investor Type.
- Added resumable SQL-side `scripts/backfill_feature_02_v2.py`. A controlled BBCA run staged and inserted 219,762 investor-specific rows; the final rolling insert took 149.6 seconds. Production BBCA v1 remained unchanged at 177,212 rows.
- BBCA source reconciliation PASS: zero extra, missing, or mismatched 1D rows. Independent AK/Regular/2026-08-31 calculation PASS for all 31 numeric/window fields for both Domestic and Foreign investors; the maximum floating-point difference was `3.33e-16`.
- The first sample-validator run passed source reconciliation but stopped on a local dictionary-row indexing error. Updating positional access to named fields fixed the validator; no database value was changed or invalidated by this failure.
- The first strict catalog sync correctly rejected the shadow because migration 034 initially categorized it as `Feature` without prematurely active Feature Catalog definitions. No partial sync was committed. Migration `database/migrations/20260914_036_register_feature_02_shadow_columns.sql` corrected the shadow to `System` staging infrastructure and registered 38/38 Column Catalog rows as `PARTIAL`; catalog/schema synchronization then passed for 467 physical columns and 28 public tables.
- Active Feature 2 v1 definitions remain unchanged. Complete calculation-verified Feature Catalog v2 definitions will be activated only after full shadow backfill and validation, immediately before or during reviewed atomic cutover. Feature 3 has not been rebuilt and Feature 4 has not started.
- Full four-range shadow backfill completed with all workers exiting successfully: 4,125 distinct tickers and 45,229,673 rows covering 2016-01-04 through 2026-08-31. Range totals were 11,446,792 rows below `CBPE`, 11,292,326 from `CBPE` through below `JIHD`, 11,117,923 from `JIHD` through below `PSAB`, and 11,372,632 from `PSAB` onward.
- Full ticker-by-ticker source reconciliation PASS: 45,229,673 grouped source rows equaled 45,229,673 shadow rows, with zero missing, extra, or mismatched 1D value/lot rows. Coverage is 40,737,689 Domestic and 4,491,984 Foreign rows; board coverage is 44,418,768 Regular, 751,598 Nego, and 59,307 Tunai.
- Constraint and invariant validation PASS: one valid primary key, all constraints validated, 38/38 physical-to-Column-Catalog coverage, and zero invalid Investor Type, board, gross, net identity, blank identity, rolling-boundary, or day-count rows. Percentile-without-z-score rows are valid zero-standard-deviation cases. The canonical Feature 2 remained at 42,598,713 rows and was not modified.
- A first monolithic full reconciliation failed read-only with PostgreSQL temporary-space exhaustion. No data changed. Replacing it with four disjoint per-ticker read-only reconciliation streams completed in about seven minutes and avoided the temp-disk spill. Atomic cutover, active Feature Catalog v2 registration, and downstream Feature 3 rebuild remain explicitly pending approval.
- Post-backfill independent sampling PASS across all four ticker ranges and all three boards. Twelve ticker/broker/date keys were checked for both Domestic and Foreign investors: 744 numeric comparisons plus 24 broker-classification joins produced zero failures, with maximum floating-point difference `8.88e-16`. Four targeted zero-standard-deviation, sparse-activity divisor, incomplete-window, and complete-60D cases added 124 numeric comparisons with zero failures. This validation was read-only and did not activate or alter the shadow, canonical Feature 2, Feature Catalog, or Feature 3.

## 2026-09-14 — Register generic consecutive-condition screening

- Applied forward-only migration `database/migrations/20260914_033_register_find_condition_runs.sql` to Railway `dev` PostgreSQL.
- Registered active backend tool `find_condition_runs` in `Tool_Catalog`. It evaluates one or more Feature-Catalog-approved conditions with AND semantics, groups consecutive per-ticker trading observations, treats NULL as a run break, and returns compact episode boundaries plus optional exact matching dates.
- The tool does not require Analytics Worker or direct raw-table privileges. Enforcement remains configurable and separate: 7,305 maximum calendar days per request, 200 maximum returned episodes, 20 tickers, 100,000 estimated rows, 15-second PostgreSQL timeout, 1 MiB backend output, and the existing smaller LLM-facing limits.
- The BBCA 2015-through-ready-date live handler verification scanned an estimated 2,466 Feature 01 observations and found two qualifying positive-return runs of at least seven trading observations. Existing `(ticker,date)` access supports this selective path; no new index was added.
- Added deterministic test `R1B_016_CONDITION_RUNS`; Golden Test run `4ff14bf3-8c5e-4248-b506-08af06b65dec` passed 16/16 with zero failures. Catalog reconciliation covered 429 physical columns and regenerated `DATABASE_SCHEMA.md`.
- No Feature value/formula, source row, Feature refresh routine, schedule, or raw-table privilege changed.

## 2026-09-14 — Auto-load compact Feature semantics during data execution

- The first live DeepSeek streak request (`edf80a9f-91f2-4078-b432-5db4bc3195c4`) correctly found the two BBCA runs but failed before finalization after 14 calls/9 iterations because cumulative input reached 101,627 tokens. Audit showed one empty freshness call, a rejected pre-definition streak call, overly broad discovery/seven-definition retrieval, and an invalid full-range quality request before the necessary episode checks.
- Applied forward-only migration `database/migrations/20260914_035_auto_load_compact_feature_semantics.sql`. Data handlers now advertise that the orchestrator auto-loads compact semantics for referenced columns; complete `get_feature_definition` retrieval is optional and remains available for detailed formula/methodology work.
- The backend no longer rejects an otherwise valid query merely because the model forgot a separate definition call. Missing or inactive catalog definitions still reject execution, so `Feature_Catalog` remains authoritative.
- The migration was initially applied from a temporary `034` filename before a concurrently created Feature 2 shadow migration claimed that sequence number. The repository migration was moved forward to `035`, and the migration itself replaces the stale temporary source-path reference with the final `035` path. No SQL behavior or Feature data was changed by the renumbering.
- A concurrently created empty `Feature_02_Broker_Rolling_v2` shadow table is `PARTIAL` and currently has neither `Column_Catalog` nor `Feature_Catalog` coverage. The strict catalog synchronizer correctly refused to certify it. This tool release did not alter or register that in-progress table; production AI access remains blocked because only `VERIFIED` Feature tables are queryable.
- Exact-question DeepSeek rerun `2d7f8adf-5119-4a60-9ac4-c1b789497ff5` finished `SUCCESS`/`FINAL` after the repair: 85,591 cumulative input tokens, 4,129 output tokens, 11 tool calls, 9 iterations, and 18,476 peak active-context tokens. It stored evidence `438daac1-8e52-4207-8a88-25130dc7dfb8`; the answer reproduced both independently verified BBCA streaks and retained the descriptive-not-predictive and point-in-time metadata caveats.

## 2026-09-14 — Separate evidence storage from the stopping-policy gate

- Applied forward-only migrations `database/migrations/20260914_031_separate_evidence_from_analysis_completion.sql` and `database/migrations/20260914_032_compact_insight_evidence_workflow.sql` to Railway `dev` PostgreSQL.
- `record_evidence` remains the durable claim/evidence writer but no longer signals finalization. New active orchestrator tool `complete_analysis` requires recorded evidence and an explicit necessary-follow-up checklist before the backend removes data tools for the final response. `Tool_Catalog` now has 18 active and 11 inactive rows.
- The model-facing catalog recommends one consolidated evidence item after necessary follow-ups and returns a completion-policy hint. Duplicate analytical query hashes do not satisfy the configured INSIGHT minimum.
- Live read-back PASS: `record_evidence.signals_finalization=false`, `complete_analysis.signals_finalization=true`, all Feature 1–3 readiness rows remain `READY`, raw-table denial and Feature-table read privileges remain unchanged, and the latest deterministic golden run `db3abfec-a474-41cc-8282-3e2cc12665e0` passed 15/15.
- Catalog synchronization reconciled 429 registered physical columns and regenerated `DATABASE_SCHEMA.md`. No Feature value, formula, raw row, Feature refresh routine, index, or schedule changed.

## 2026-09-14 — Preserve Feature discovery identifiers and harden final evidence

- Applied forward-only migration `database/migrations/20260914_026_harden_feature_discovery_and_final_evidence.sql` after a live DeepSeek analysis showed that verbose discovery metadata could trigger semantic compaction before the model selected the intended Feature column.
- `find_features` now advertises compact identifier discovery followed by complete `get_feature_definition` retrieval for selected columns. The detailed catalog contract remains the source for analytical interpretation, recommended use, misuse warnings, semantic review status, and validation evidence.
- `record_evidence` now documents that final citations must use evidence IDs actually created for the current request. No Feature definition, Feature value, query limit, raw-table privilege, or calculation routine was changed.
- Applied follow-up migration `database/migrations/20260914_027_route_bounded_retrieval_efficiently.sql` after the next smoke proved that an eight-iteration analysis cannot afford a redundant tool-family expansion and estimate for a direct one-ticker/one-date request. Direct retrieval now starts with Query/Screening exposed, bounded `query_features` documents its own validation, and ADVANCED remains excluded unless separately justified. The 8-iteration/12-call limits were not raised.
- Applied `database/migrations/20260914_028_always_expose_evidence_recording.sql` after a live step trace proved that `record_evidence` remained in the AUDIT family but AUDIT was neither core nor requestable through progressive exposure. The backend now exposes only this essential audit capability at every stage; `get_analysis_history` remains non-core, so historical context is not injected or advertised unnecessarily.
- Applied `database/migrations/20260914_029_define_evidence_finalization_transition.sql` after the next smoke successfully queried BBCA and stored two evidence rows but then wasted its last iteration asking for a nonexistent final-answer tool. `record_evidence` now explicitly signals that evidence is sufficient; the following model call removes data-tool schemas and requests only the strict final response. Necessary follow-up analysis must occur before that signal.
- Applied `database/migrations/20260914_030_validate_evidence_requests_in_backend.sql` after an advanced-profile rerun showed OpenRouter/DeepSeek could omit required `record_evidence.evidence_type` despite the strict provider schema. The handler now validates required fields and accepted evidence types before database access, returning a recoverable `ToolError` instead of terminating the analysis with `KeyError`.

## 2026-09-14 — Harden all active Feature semantics

- Applied forward-only migration `database/migrations/20260913_023_harden_feature_catalog_semantics.sql` to Railway `dev` PostgreSQL. It added `analytical_interpretation`, `recommended_use`, `misuse_warning`, `semantic_review_status`, and `validation_evidence` to `Feature_Catalog`, with nonblank/evidence/status constraints and matching verified `Column_Catalog` rows.
- Populated all 91 active Feature 1–3 definitions and marked them `CALCULATION_VERIFIED` using the already validated migration and independent-validation evidence. Clarified Feature 02 `net_value_1d`/`net_lots_1d` sign meaning and Feature 03 `ticker`/`market_board` null and board-separation rules.
- Post-migration editorial audit found overly generic `recommended_use` text for Feature 01 price references and inappropriate peer-group wording for `calculated_at`. Applied corrective forward-only migration `database/migrations/20260914_024_refine_feature_catalog_usage_guidance.sql`; price references, materialization timestamps, and Feature 03 dominant-broker identifiers now have purpose-specific guidance, and the audit script rejects those regressions.
- `scripts/audit_feature_catalog_semantics.py` PASS: 91 active, 91 calculation-verified, zero incomplete, exact physical coverage of 29 Feature 01, 38 Feature 02, and 24 Feature 03 columns. Catalog synchronization reconciled 429 registered physical columns and `DATABASE_SCHEMA.md` was regenerated from 27 public tables.
- No raw row, Feature value, formula, Feature refresh routine, queue, schedule, service, or index was changed.

## 2026-09-14 — Clarify bounded AI tool workflow

- Added forward-only migration `database/migrations/20260914_025_clarify_market_ai_tool_workflow.sql` after a live DeepSeek smoke showed avoidable calls from abbreviated table names, literal multi-word feature search, and duplicate validate/estimate preflight.
- `Tool_Catalog` now instructs the model to copy exact Feature identifiers, documents whitespace-keyword OR discovery, states that `estimate_query_size` includes request validation, and keeps explicit evidence recording. The backend `find_features` handler applies the documented eight-keyword maximum and parameterized OR search.
- Query, token, tool-call, raw-table privilege, Feature values, and service limits were not relaxed.

## 2026-09-13 — Finalize Release 1B semantics and golden acceptance

- Applied forward-only `database/migrations/20260913_021_finalize_market_ai_release_1b.sql`. It corrected the post-Feature-3 generic usage metadata: date/ticker/board and dominant-broker identifiers are groupable dimensions, calculated time is a dimension, and every numeric field now has type-appropriate aggregation/ranking rules.
- Registered 15 active Release 1B golden definitions covering discovery, common readiness, bounded BBCA retrieval, raw-column/unbounded/ticker-limit rejection, extreme-observation quality policy, Feature 3 board aggregation, query-hash reproducibility, point-in-time warnings, semantic compaction, progressive exposure, inactive Analytics Worker tools, and database least privilege.
- Applied `database/migrations/20260913_022_align_market_ai_tool_limits.sql` after detecting that the original catalog default output count (100) differed from the approved configurable backend default (500). It aligns query/screening catalog metadata with the enforced 500/5,000 row, 20 ticker/column, 1,825-day, 100,000 estimated-row, 15-second, 1 MiB backend, and 200-row/128 KiB/4,000-token LLM-facing ceilings. Runtime Railway variables remain authoritative.
- `scripts/run_market_ai_golden_tests.py` executed all 15 definitions under `market_ai_reader`; the final post-limit-alignment run `cafd05d4-aaf4-4450-b84e-3872253c0d08` finished `PASS` with 15 passed and zero failed. No OpenAI request was needed for this deterministic database/backend gate.
- `scripts/verify_market_ai_backend.py` PASS: 15 exposed Release 1B non-audit definitions in the tested families, all three verified Feature tables, common safe date 2026-08-31, BBCA quality `PASS`, 19 bounded price rows, three Feature 3 market-board groups, stable estimate/execute query hash, and rejection of an unregistered raw column.
- Follow-up Feature 3 `market_board` audit PASS: active `v1` metadata exposes it as an `IDENTITY`, filterable and groupable column with only `COUNT`/`COUNT_DISTINCT` aggregations. A live BBCA bounded aggregation returned exactly `Regular`, `Nego`, and `Tunai`; the tool-definition response now exposes these semantic flags so future AI/backend checks can verify them directly.
- Post-audit deterministic run `3484d8da-040f-4220-8039-edb549947701` again finished 15/15 `PASS` with zero failures.
- Provisioned login `market_ai_app` as a member only of `market_ai_reader` and `market_ai_logger`, with statement/lock/idle transaction timeouts. Feature/catalog read and analysis-log write are available; raw price and broker SELECT remain denied. The credential value is stored only as a Railway service variable and is not present in Git.
- Catalog/schema synchronization remained complete at 424 physical columns; `DATABASE_SCHEMA.md` was regenerated from 27 public tables. No raw row, Feature value, calculation routine, or Feature automation was changed.

## 2026-09-13 — Create market AI catalog, readiness, audit, and historical-integrity foundation

- Applied forward-only `database/migrations/20260913_009_create_market_ai_foundation.sql`. It added readiness and generic-usage metadata, `Feature_Relationship_Catalog`, `Tool_Catalog`, `Analysis_Request`, `Analysis_Step_Log`, `Analysis_Evidence`, `check_analysis_data_readiness(text[])`, and three NOLOGIN least-privilege roles. The registry contains 17 active Release 1 tools and 11 inactive analytics/deferred tools; advertised backend and LLM-facing result limits are separate.
- Applied `database/migrations/20260913_010_add_market_ai_historical_integrity.sql`. It added observation/availability and point-in-time metadata, conservative close-`t` to entry-`t+1` rules, Feature-level historical warnings, cumulative and peak context accounting, structured methodology/version snapshots, and an immutability trigger for completed analysis evidence. The first attempt hit the five-second lock timeout and rolled back fully; a read-only blocker check found no lingering activity, and the immediate retry succeeded.
- Applied `database/migrations/20260913_011_create_market_ai_golden_tests.sql`. It created `Golden_Analysis_Test`, `Golden_Analysis_Test_Run`, and `Golden_Analysis_Test_Result`, with 50/50 physical columns registered in `Column_Catalog`. Definitions are versioned and results retain correctness, methodology, evidence, warning, latency, and token outcomes; the first production suite is populated with reproducible expectations during backend acceptance.
- Feature 03 completed concurrently. Applied `database/migrations/20260913_020_register_feature_03_ai_readiness.sql` without changing its calculations. It registered Feature 03 as `DATA_DATE`, documented current-classification limitations, set its safe date to 2026-08-31, and granted only Feature-table SELECT to `market_ai_reader`.
- Live verification PASS via `scripts/verify_market_ai_foundation.py`: Feature 1, 2, and 3 returned `READY` at 2026-09-11, 2026-08-31, and 2026-08-31; `market_ai_reader` can SELECT the three verified Features but cannot SELECT raw price or broker tables; `market_analytics_worker` cannot SELECT Feature tables; and a rollback-only attempt to alter a completed version snapshot was rejected.
- Catalog/schema synchronization PASS with 424 registered physical columns and 27 public tables. Active Feature definitions are 29 Feature 1, 38 Feature 2, and 24 Feature 3. Point-in-time status is intentionally `PARTIAL`: Feature 1 sector/industry and Feature 2/3 broker classifications are current-state metadata, while exact historical broker availability timestamps are unavailable.
- Controlled `EXPLAIN (ANALYZE, BUFFERS)` acceptance covered eight high-frequency patterns. All used Index Scan or Bitmap Index Scan; none used a full-table sequential scan. BBCA 2023 Feature 1 history completed in 6.744 ms; Feature 2 ticker histories completed in 0.156–19.652 ms; one-date Feature 2 cross-section/ranking completed in 74.337–124.289 ms. No speculative multi-gigabyte index was added. See `DATABASE_INDEX_ACCEPTANCE.md`.
- No price/broker raw row, existing Feature value, Feature automation, Railway application service, or secret was changed. The private `market-ai-backend` remains the next gated release.

## 2026-09-13 — Create, backfill, validate, and catalog Feature 03 stock broker daily

- Created `public."Feature_03_Stock_Broker_Daily"` at grain `(date, ticker, market_board)` with 24 columns and primary key `(ticker, market_board, date)`. Regular, Nego, and Tunai are independent partitions. Migration: `database/migrations/20260913_009_create_feature_03_stock_broker_daily.sql`.
- Added `refresh_feature_03_stock_broker_daily(date,text[])`. It aggregates validated Feature 02 daily broker rows entirely in PostgreSQL, joins current Broker Profile categories, uses deterministic broker-code tie-breaking, and transactionally replaces only the requested date/ticker scope. Null date enables the full historical refresh; an empty ticker array is a no-op; an advisory transaction lock serializes refreshes.
- Full backfill completed in 219.8 seconds with 2,268,015 rows. Coverage: Regular 1,955,758 rows/3,942 tickers (2016-01-04 through 2026-08-31), Nego 300,796 rows/1,399 tickers (same dates), and Tunai 11,461 rows/1,117 tickers (2016-01-06 through 2026-08-31).
- Full reconciliation PASS: zero extra rows, zero missing rows, and zero mismatches across all calculated fields. Count/ratio/HHI constraints had zero violations. Domestic plus Foreign and Institutional-heavy plus Retail-heavy plus Mixed plus Niche each reconciled exactly to total daily net flow, confirming complete current profile mapping for the 111 source brokers.
- NULL results matched zero-denominator rules: `net_buy_broker_ratio` 0; `top_buyer`/`top3_buyer_share` 281,214 (12.3991%); `top_seller` 281,213 (12.3991%); and `broker_concentration_hhi` 281,048 (12.3918%). No row had zero active brokers; dominant-flow and HHI NULLs occur when broker net values cancel to zero or lack the required sign.
- Independent raw-source recalculation PASS for all 20 calculated fields on BBCA Regular and Nego at 2026-08-31 and BBCA Tunai at 2026-08-18. This covered ordinary flow, all-zero broker net flow, null denominators, dominant brokers, top-three share, and HHI. A committed BBCA 2026-08-31 scoped refresh returned two board rows and preserved both row count and independently checked values.
- Applied `database/migrations/20260913_010_catalog_feature_03_stock_broker_daily.sql` after validation. The first attempt failed atomically because active Feature definitions require the table catalog to be VERIFIED first; moving that promotion earlier in the same transaction resolved it. A second atomic attempt exposed unsupported new category labels; mapping them to the existing controlled `Broker Flow` and `Broker Concentration` categories resolved it. Neither failure left partial indexes, definitions, or status changes.
- Catalog validation PASS: 24/24 Feature 03 columns have active `Feature_Catalog` `v1` definitions and VERIFIED `Column_Catalog` entries. `Feature_03_Stock_Broker_Daily_date_board_ticker_idx` supports daily board screens; the primary key supports ticker/board history. Total table-plus-index size was approximately 609 MB.
- Registered safe joins in `Feature_Relationship_Catalog` via `database/migrations/20260913_011_catalog_feature_03_relationships.sql`: Feature 02 many-to-one into Feature 03 on ticker/board/date, and Feature 01 one-to-many into Feature 03 on ticker/date with required board filtering or preaggregation.
- No raw table, Feature 01/02 value, price automation, or Railway service was changed. Feature 03 automatic refresh is not deployed; after future Broker Summary updates, Feature 02 must refresh first and Feature 03 must then be invoked for the affected scope.

## 2026-09-13 — Create, backfill, validate, and catalog Feature 02 broker rolling signals

- Target: `public."Feature_02_Broker_Rolling"` in Railway project `lucid-patience`, environment `dev`, PostgreSQL service `bb21a9f4-a9d3-4a51-945f-fa86b63f4b86`.
- Applied forward-only migrations `database/migrations/20260913_007_create_feature_02_broker_rolling.sql` and `database/migrations/20260913_008_catalog_feature_02_broker_rolling.sql`. The table has 38 columns, primary key `(ticker, market_board, broker, date)`, a daily-consumer index `(date, market_board, ticker)`, board/ratio/percentile checks, and the exact empirical-midrank helper routine.
- Full SQL-side historical backfill completed for all source data available at execution: 42,598,713 daily derived rows, 4,125 symbols, 111 brokers, and dates 2016-01-04 through 2026-08-31. Board rows are Regular 41,903,954, Nego 636,808, and Tunai 57,951. Domestic and Foreign source rows were combined at `(date, ticker, broker, market_board)`; boards were never combined.
- Backfill used resumable per-ticker transactions. A stopped first pass left 14,167,393 committed rows; two disjoint resume workers then inserted 14,253,624 rows for ticker values below `N` and 14,177,696 rows from `N` onward. Their staged ranges summed exactly to 42,598,713. Because the run intentionally spanned an interruption and restart, one continuous wall-clock duration is not reported; representative large ticker transactions took roughly 60–100 seconds.
- Exact source reconciliation PASS: zero extra Feature rows, zero missing Feature rows, and zero mismatches in 1D buy/sell value or lots. Distinct identifiers, min/max dates, and board-level gross totals matched; primary-key duplicates are impossible and none were observed. Metadata coverage had zero null `broker_type` and zero null `broker_classification`; persistence/window invariants had zero violations.
- Independent 31-field recalculation PASS for BBCA/AK/Regular on 2026-08-31, BBCA/AK/Nego on 2026-08-31, and BBCA/MG/Tunai on 2026-08-18. Boundary tests also covered a short-history instrument, transaction-calendar gaps, zero activity, and zero historical standard deviation. Numerical differences were zero or floating-point noise no larger than `4.45e-16`.
- Resume/idempotence PASS: re-running BBCA staged 177,212 daily grains, skipped its already complete ticker, and inserted zero rows. The full validation scan completed in approximately 12 minutes and returned `overall=PASS`.
- Expected NULL boundaries: 5D 208,419 (0.4893%); 20D rolling fields 836,449 (1.9636%); 60D rolling fields 2,277,232 (5.3458%); 20D/60D z-scores 8,247,078 (19.3599%)/9,141,945 (21.4606%); 20D/60D percentiles 7,967,501 (18.7036%)/8,886,424 (20.8608%); largest-buy-day fields 2,347,232 (5.5101%).
- Catalog activation PASS: `Feature_Catalog` now has 67 active definitions, including 38/38 Feature 02 `v1` definitions. `Table_Catalog` has 15 registered tables and `Column_Catalog` has 241 columns; all 38 Feature 02 column entries are `VERIFIED`. Live catalog reconciliation updated 38 physical facts and `DATABASE_SCHEMA.md` was regenerated from 18 public tables.
- Query-plan checks use the primary key for ticker/board/broker history and `Feature_02_Broker_Rolling_date_board_ticker_idx` for one-date board/ticker access. Total table-plus-index size was approximately 13 GB after backfill and indexing.
- No raw broker row, price table, Feature 01 table, price cron, or Railway service was changed. Feature 02 automatic refresh is not deployed in this version; source corrections or new broker data require the documented manual ticker rebuild until a separate queue/worker rollout is approved.

## 2026-09-13 — Verify live Railway Feature 01 worker

- Deployed the always-on `feature-01-worker` and verified its initial deployment `5465b07b-5919-4dc1-a513-871ba7ca4ad2` reached `SUCCESS`; see `RAILWAY_CHANGELOG.md` for service configuration.
- A committed BBCA 2026-09-11 metadata-only re-ingestion reopened the existing queue key. The Railway worker claimed and recalculated it without a manual worker invocation: queue `DONE`, `Feature_Status.SUCCESS` with zero outstanding work, log `SUCCESS`, and one Feature row refreshed. The queue source version exactly matched the price row's `ingestion_time`, and the Feature row existed.
- At final read-back: two queue items `DONE`, one ticker status `SUCCESS`, four `SUCCESS` attempt logs and one earlier expected `FAILED` local-test log; no pending, processing, or failed queue item. Catalog synchronization found 203 physical columns and no metadata drift; `DATABASE_SCHEMA.md` was regenerated from 17 public tables. No OHLCV value or row count was changed by this live test.

## 2026-09-13 — Activate price-driven Feature 01 enqueue and local worker verification

- Applied forward-only migration `database/migrations/20260913_006_activate_feature_01_queue.sql` in Railway project `lucid-patience`, environment `dev`. A PostgreSQL price-row trigger now transactionally opens/reopens one Feature 01 queue item for each inserted or updated candle with non-null `ingestion_time`; no TradingView query or price-cron code change was made.
- Added `Feature_Calculation_Queue.source_attempt_count` (the per-source retry counter; lifetime `attempt_count` remains monotonic for unique attempt logs), a check constraint, status-reconciliation and enqueue trigger functions, and their `Table_Catalog.related_functions` entries. `Column_Catalog` now covers 203 physical columns across 14 registered tables; synchronization reconciled 39 source-path changes and later reported zero drift.
- Before activation, reconciled all 1,303,728 price rows to Feature 01: zero missing keys and zero close, volume, Sector, or Industry mismatches. The three control tables were empty.
- Rollback-only price update PASS: queue and status became `PENDING` inside the transaction and vanished on rollback. A committed BBCA 2026-09-11 no-OHLCV-change test then created one queue item. The first local worker attempt failed due to a result-row access bug and was recorded as `FAILED`; after fixing the worker code, automatic retry logic completed it and recorded `SUCCESS` in both queue and status. The log preserves both attempts.
- Historical BBCA 2026-01-21 no-OHLCV-change test PASS: worker refreshed exactly 121 trading observations (changed date plus 120 subsequent observations), validated source/Feature coverage, and restored ticker status to `SUCCESS`. Re-ingesting BBCA 2026-09-11 reopened its existing queue key with per-source attempts reset to zero, then a new successful worker claim completed it. OHLCV values and total price/Feature row counts remained unchanged; only ingestion timestamps for those two test candles and the expected operational/Feature refresh records changed.
- At this migration/test stage, continuous automatic processing remained pending; it was subsequently deployed and verified in the entry above. Price cron schedules, source code, and other existing services were not changed.

## 2026-09-13 — Create Feature 01 calculation control tables

- Target: Railway project `lucid-patience`, environment `dev`, PostgreSQL service `bb21a9f4-a9d3-4a51-945f-fa86b63f4b86`.
- Applied forward-only migrations `database/migrations/20260913_004_create_feature_calculation_control.sql` and `database/migrations/20260913_005_update_table_catalog_comment.sql`. Created `public."Feature_Calculation_Queue"`, `public."Feature_Status"`, and `public."Feature_Calculation_Log"`, with primary/foreign keys, state and timestamp checks, retry/lease indexes, attempt uniqueness, and documented columns. The second migration corrected the catalog table comment from the original eleven-table wording to the current approved scope without editing an applied migration.
- Registered all three new System tables and all 39 physical columns in `Table_Catalog`/`Column_Catalog`. `scripts/sync_database_catalog.py` now recognizes calculated Feature tables by catalog category, so control tables do not incorrectly require Feature formulas. Catalog synchronization PASS: 14 registered tables, 202 physical/cataloged columns, zero metadata updates on re-run. The 29 active Feature 01 formula definitions were unchanged.
- Live verification PASS: all three control tables exist and contain zero committed rows; rollback-only tests rejected duplicate queue keys, invalid queue status, and premature `Feature_Status.SUCCESS`, while valid queue/status/log inserts succeeded and were rolled back. Price source and Feature 01 remain at 1,303,728 rows each. `Database_Table_Status` and `DATABASE_SCHEMA.md` were refreshed for 17 public tables.
- No price cron, recovery cron, worker, Railway service, or raw/Feature data was changed. Automatic calculation is **not active**: the price writer does not yet enqueue in the price-upsert transaction, and no worker invokes `refresh_feature_01_stock_daily(date, text[])`. See `FEATURE_01_AUTOMATION_PLAN.md` for the required rollout.

## 2026-09-13 — Create approved table and column catalogs

- Target: `public."Table_Catalog"` and `public."Column_Catalog"` in Railway project `lucid-patience`, environment `dev`, PostgreSQL service `bb21a9f4-a9d3-4a51-945f-fa86b63f4b86`.
- Added and applied forward-only migration `database/migrations/20260913_003_create_table_and_column_catalog.sql`. It created two metadata tables, keys, checks, a column-to-table foreign key, a documentation-status index, and timestamp-maintenance triggers. Raw price/broker rows, Feature rows, and `Monitoring_Price_ALL` were not modified; `Database_Table_Status` was refreshed by the schema-documentation script.
- Registered exactly the 11 user-approved, still-existing physical tables. `Database_Table_Status`, the already-deleted `IDX_Broker_Summary_Data_Quality`, and the two catalog tables themselves were intentionally excluded from the initial semantic catalog.
- Seeded and reconciled all 163 physical columns of those tables using `scripts/sync_database_catalog.py`. Semantic grades: 31 VERIFIED, 131 PARTIAL, and one NEEDS_REVIEW (`IDX_Stock_Universe.price_feed_daily`, whose business meaning is not established by a source script). The 29 active Feature 01 definitions remain in `Feature_Catalog` and are authoritative for formulas.
- The project owner clarified `IDX_Broker_Profile.broker_classification` as a usage profile, separate from domestic/foreign `broker_type`. Live data contained Institutional-heavy, Retail-heavy, Mixed, and Niche values; that column was marked VERIFIED.
- Live validation PASS: 11 cataloged tables, 163 physical/cataloged columns, zero missing columns, zero stale catalog columns, zero physical type/nullability/default/position mismatches, zero primary-key mismatches, zero catalog rows for the deleted data-quality table, and the unchanged 29 active Feature 01 definitions. Price and Feature 01 tables each still contain 1,303,728 rows.
- Re-running the catalog synchronizer made zero inserts and zero updates, confirming idempotence. Refreshed `DATABASE_SCHEMA.md` from the live schema (14 current public tables, including `Database_Table_Status` and the two new catalogs).
- Added `DATABASE_CATALOG.md` and mandatory GitHub maintenance rules for future tables, columns, Feature definitions, and related PostgreSQL routines. Feature 01 queue/status/worker integration is only documented as a future plan; it was not created or enabled.
- Updated the daily schema-documentation GitHub Action to run catalog reconciliation first. It will fail on an unregistered public data table, missing cataloged column, stale catalog target, or missing active Feature definition instead of silently publishing incomplete metadata.

## 2026-09-13 — Track price-row ingestion time

- Target: `public."Price_Stock_Indonesia_IDX"` in Railway project `lucid-patience`, environment `dev`, PostgreSQL service `bb21a9f4-a9d3-4a51-945f-fa86b63f4b86`.
- Added forward-only migration `database/migrations/20260913_002_add_price_ingestion_time.sql`.
- Added nullable `ingestion_time timestamp with time zone` with database default `statement_timestamp()` so one successful bulk upsert assigns one consistent database-side timestamp to every row in that batch.
- Preserved all 1,303,728 pre-existing rows with `ingestion_time IS NULL` because their exact historical ingestion times cannot be reconstructed reliably.
- Updated the shared DAILY/RECOVERY price upsert so both inserts and `(ticker, date)` conflict updates set `ingestion_time` from the same PostgreSQL statement timestamp.
- Live schema read-back PASS: exact type, nullable state, default, and column comment matched the approved design.
- Rolled-back live upsert test PASS for `AADI` on `2026-09-11`: one row received a valid database statement timestamp inside the transaction, and the timestamp returned to null after rollback.
- Existing price values, primary key, indexes, query dates, feature tables, schedules, and other database objects were intentionally left unchanged.

## 2026-09-13 — Create Feature Catalog for validated Feature 01

- Target: `public."Feature_Catalog"` in Railway project `lucid-patience`, environment `dev`, PostgreSQL service `bb21a9f4-a9d3-4a51-945f-fa86b63f4b86`.
- Added forward-only migration `database/migrations/20260913_001_create_feature_catalog.sql` without changing `Feature_01_Stock_Daily`, raw tables, application services, or schedules.
- Live inspection found one of the four locked Feature tables: `Feature_01_Stock_Daily` with 29 physical columns. Feature 02–04 and any prior Feature Catalog were absent.
- Created all 18 required metadata/governance columns using the existing mixed-case table/lowercase-column convention, with primary key `(feature_table, feature_column, version)`, controlled Feature table/category/version checks, mandatory nonblank metadata, timezone-aware timestamps, and automatic `updated_at` maintenance.
- Added a governance trigger that rejects an active catalog entry unless its exact target table and column physically exist in schema `public`.
- Registered exactly 29 active `v1` definitions for Feature 01 and zero premature entries for Feature 02–04. Each entry records grain, category, detailed meaning and formula, exact source references, trading-observation lookback, minimum history, unit, null rule, refresh trigger, and dependency rule.
- Coverage validation PASS: 1 Feature table found, 29 physical Feature columns, 29 catalog entries, 29 active entries, zero missing definitions, zero catalog targets pointing to missing columns, zero duplicate definitions, and zero mandatory-field violations.
- Source validation PASS: zero broken source-table or source-column references. All references use the actual live PostgreSQL table and column casing.
- Formula spot-check PASS against `refresh_feature_01_stock_daily(date, text[])` for `return_20d_pct`, `volatility_20d_ann_pct`, and `volume_zscore_20d`. Formula checks belonging to Feature 02–04 are not applicable until those tables exist and pass their own validation.
- Governance test PASS inside a rolled-back savepoint: an attempted active definition for nonexistent column `does_not_exist` was rejected.
- Overall status: PASS. Feature Catalog is ready as the semantic/metadata layer for Feature 01; future Feature tables must be validated before their catalog rows are appended.

## 2026-09-12 — Create and backfill Feature 01 stock daily

- Target: `public."Feature_01_Stock_Daily"` in Railway project `lucid-patience`, environment `dev`, PostgreSQL service `bb21a9f4-a9d3-4a51-945f-fa86b63f4b86`.
- Added forward-only migration `database/migrations/20260912_001_create_feature_01_stock_daily.sql`.
- Created the ticker/trading-date feature table with primary key `(ticker, date)`, a separate `date` index, source close/volume and current Sector/Industry, trading-observation lags, percent returns, annualized 5/20/60-observation volatility, volatility changes, 20-observation volume metrics, rolling highs, and drawdowns.
- Added `public.refresh_feature_01_stock_daily(date, text[])`. A null date performs the initial full refresh; an incremental call recomputes the changed row and up to 120 following trading observations for the selected ticker set. Empty ticker arrays are safe no-ops, zero denominators return null, and an advisory transaction lock serializes refreshes.
- Initial SQL-side backfill completed in approximately 54 seconds and inserted 1,303,728 rows across 844 tickers from 2018-01-02 through 2026-09-11. The latest date contains the same 829 rows as the price source. The resulting table and indexes use approximately 379 MB.
- Reconciliation PASS: exact source/feature row and ticker counts, zero duplicate keys, zero missing or extra keys, zero close/volume/Sector/Industry mismatches, zero negative source values, zero one-day returns below -100%, zero positive drawdowns, and zero incomplete classifications.
- Window validation PASS: all 1/5/20/60 lag boundaries, complete-window volume/high fields, complete-window volatility fields, and zero-denominator volatility-change rules matched their expected null behavior.

| Calculated field | NULL count | NULL rate |
|---|---:|---:|
| `close_1d_ago` | 844 | 0.0647% |
| `close_5d_ago` | 4,220 | 0.3237% |
| `close_20d_ago` | 16,880 | 1.2947% |
| `close_60d_ago` | 50,555 | 3.8777% |
| `return_1d_pct` | 844 | 0.0647% |
| `return_5d_pct` | 4,220 | 0.3237% |
| `return_20d_pct` | 16,880 | 1.2947% |
| `return_60d_pct` | 50,555 | 3.8777% |
| `abs_return_1d_pct` | 844 | 0.0647% |
| `volatility_5d_ann_pct` | 4,220 | 0.3237% |
| `volatility_20d_ann_pct` | 16,880 | 1.2947% |
| `volatility_60d_ann_pct` | 50,555 | 3.8777% |
| `volatility_5d_change_pct` | 67,235 | 5.1571% |
| `volatility_20d_change_pct` | 74,665 | 5.7270% |
| `volatility_60d_change_pct` | 130,642 | 10.0206% |
| `volume_avg_20d` | 16,036 | 1.2300% |
| `volume_std_20d` | 16,036 | 1.2300% |
| `volume_ratio_20d` | 16,036 | 1.2300% |
| `volume_zscore_20d` | 16,039 | 1.2302% |
| `high_20d` | 16,036 | 1.2300% |
| `high_60d` | 49,717 | 3.8134% |
| `drawdown_20d_pct` | 16,036 | 1.2300% |
| `drawdown_60d_pct` | 49,717 | 3.8134% |

- Independent formula validation PASS for BBCA on 2026-09-11, SUPA at its 121st observation on 2026-07-01, and zero-volume DSSA on 2020-10-14. All stored values matched separate calculations within floating-point tolerance.

| Sample | Source inputs | Independently expected | Stored | Difference | Result |
|---|---|---:|---:|---:|---|
| BBCA 2026-09-11 `return_1d_pct` | close 6,325; previous trading-observation close 6,425 | -1.5564202334630295 | -1.5564202334630295 | 0 | PASS |
| BBCA 2026-09-11 `volatility_20d_ann_pct` | 20 complete close-derived daily returns | 19.06043383091717 | 19.06043383091717 | 0 | PASS |
| SUPA 2026-07-01 `return_1d_pct` | close 515; previous trading-observation close 535 | -3.738317757009346 | -3.738317757009346 | 0 | PASS |
| DSSA 2020-10-14 `volume_ratio_20d` | volume 0; complete 20-observation average 377,500 | 0 | 0 | 0 | PASS |

- Incremental validation PASS inside a rolled-back test transaction: BBCA historical refresh affected exactly 121 rows, latest-date refresh affected one row, repeated runs preserved the full ticker checksum, and each historical refresh completed in approximately 0.28 seconds.
- Query-plan validation used the `(ticker, date)` primary key for a 60-row BBCA history query (0.091 ms) and the `date` index for an 829-row latest-market query (2.363 ms).
- The first migration attempt referenced a renamed CTE alias and failed before backfill; PostgreSQL rolled back the entire transaction. The alias was corrected, absence of partial objects was verified, and the migration then applied successfully.
- Raw price and universe tables, all other Feature tables, Railway services, schedules, and price-cron application code were intentionally left unchanged. Automatic price-cron integration remains a separate future step.

## 2026-09-12 — Correct IDX stock-universe Sector and Industry values

- Target: `public."IDX_Stock_Universe"` in Railway project `lucid-patience`, environment `dev`, PostgreSQL service `bb21a9f4-a9d3-4a51-945f-fa86b63f4b86`.
- Corrected all 844 reference rows in one short transaction by swapping the values stored in `Sector` and `Industry`; table structure, the `Ticker` primary key, and every other column remained unchanged.
- Pre-change validation found 59 granular classifications under `Sector` and 12 broad classifications under `Industry`, confirming that the values were reversed semantically. Neither column contained null or blank values.
- A one-row `AADI` test changed `Coal` / `Energy` to `Energy` / `Coal` inside a transaction, then rolled back and verified the original row before the full correction ran.
- Post-change verification found 12 broad `Sector` values and 59 granular `Industry` values, zero null or blank values, and all 844 ticker pairs matching the approved swapped interpretation. Example: `AADI` now has `Sector = Energy` and `Industry = Coal`.
- Content checksum changed from `00549007e7ef4fd027dce108a965ce35` to `f1a77bc69c2ae71c8237a91690cdfe8a`; total row count remained 844.
- `public."Universe_Equity_Description"`, all other tables, and all Railway services were intentionally left unchanged. The pre-existing PostgreSQL TCP proxy was reused and left untouched. No CSV was created.
- Refreshed `DATABASE_SCHEMA.md` and `Database_Table_Status` from the verified live database after the correction.

## 2026-09-09 — Add Telegram command audit and deduplication ledger

- Added forward-only migration `database/migrations/20260909_002_create_telegram_command_log.sql`.
- Created `public."Telegram_Command_Log"` to audit authorized inbound bot commands separately from completed price results and outbound notification delivery.
- Enforced unique `telegram_update_id` values so a Telegram webhook retry cannot start a second Railway execution.
- Added per-service request-time and status indexes used by the rapid-click cooldown and operational review.
- Applied the migration to Railway PostgreSQL and regenerated `DATABASE_SCHEMA.md` plus `Database_Table_Status`.
- End-to-end verification recorded one accepted RECOVERY trigger and rejected an identical replay as a duplicate. The resulting RECOVERY execution `9926d137-6316-4c04-a1c2-099d87bd4735` completed with `NEEDS_REVIEW`, and its outbound notification was recorded as `SENT`.

## 2026-09-09 — Add Telegram notification delivery ledger

- Added forward-only migration `database/migrations/20260909_001_create_telegram_notification_log.sql`.
- Created `public."Telegram_Notification_Log"` to record `SENDING`, `SENT`, and `FAILED` delivery state without changing `Monitoring_Price_ALL.id` or `Monitoring_Price_ALL.execution_id`.
- Enforced one completed notification per `(source_table, source_execution_id, notification_type)` so repeated wake requests cannot send the same execution twice.
- Recorded Telegram message IDs, attempt count, sent time, and last delivery error for audit and retry handling.
- Applied the migration to Railway PostgreSQL and verified an end-to-end test: the first request was `SENT`; the second request for the same execution was treated as a duplicate and reused the same log row.

This file records database structure changes and material data loads. Times are Asia/Jakarta unless stated otherwise.

## 2026-09-07

### Broker-summary authentication-stop repair and recovery

- Target: `public."IDX_Broker_Summary"` and `stockbit_broker_summary_load_log`.
- Incident: after the prior Stockbit credential expired, both historical workers continued handling the authentication-limit exception as an ordinary date failure.
- Impact: 24 dates in each historical range, 48 total, were incorrectly marked `NEEDS_REVIEW`; previously completed data remained unchanged.
- Repair: authentication-limit exceptions now bypass date retries and `NEEDS_REVIEW` writes, reach the process-level `STOPPED_INVALID_TOKEN` handler, and return exit code 3 to stop the supervisor.
- Verification: an automated regression test simulated the fifth HTTP 401, confirmed `STOPPED_INVALID_TOKEN`, and confirmed that `record_needs_review` was not called.
- Recovery: restarted both historical supervisors with a refreshed in-memory credential; no secret value was stored in files or Git.
- First verified recovered dates: 2022-08-24 loaded 22,229 rows in the recent range, and 2019-09-10 loaded 14,124 rows in the older range. Both workers continued with no authentication error or new `NEEDS_REVIEW` date.

### Manual current-day IDX price run

- Target: `public."Price_Stock_Indonesia_IDX"` for 2026-09-07.
- Railway execution: `f4fd425d-edfe-433a-9925-99d052c794c5` (`MANUAL`, `DAILY`).
- Queried all 844 live `IDX_Stock_Universe` tickers; accepted and upserted 824 exact-date candles.
- Left 20 symbols missing because TradingView returned no candle dated 2026-09-07; no prior candle was substituted.
- Resulting price table: 1,300,396 rows, 844 distinct tickers, date range 2018-01-02 through 2026-09-07.
- Verification: 824 distinct target-date tickers, all 20 monitoring missing tickers absent for the target date, zero weekend rows for 2026-09-05/06, and zero duplicate `(ticker, date)` keys.

### Price-run monitoring history

- Target: `public."Monitoring_Price_ALL"`.
- Added `execution_id`, `trigger_source`, and `query_time` so every manual or scheduled execution remains separate history.
- Replaced the old date/run-type unique key with unique `(execution_id, exchange, asset_type, timeframe)`.
- Existing monitoring rows were retained and backfilled as scheduled legacy executions.
- Migration: `database/migrations/20260907_002_track_manual_price_runs.sql`.
- Verification: all three columns are non-null, the trigger-source check accepts only `SCHEDULED`/`MANUAL`, and the new execution key is active.

### IDX stock-universe classification schema

- Target: `public."IDX_Stock_Universe"`.
- Recorded the removal of obsolete profile columns and the final `Sector`/`Industry` mapping from `Universe_Equity_Description` in an idempotent migration.
- Migration: `database/migrations/20260907_001_simplify_idx_stock_universe.sql`.
- Verification: 844 rows, 844 distinct tickers, complete non-null `Sector` and `Industry`, and no remaining obsolete columns.

### Historical broker-summary range split

- Target: `public."IDX_Broker_Summary"`.
- Existing historical worker range changed to 2025-08-31 backward through 2021-01-01.
- Added a concurrent older historical worker covering 2020-12-31 backward through 2018-01-01.
- Both historical workers are database-only and do not produce local CSV files.
- Concurrency: three API workers per process, six combined, after twelve combined workers triggered a temporary Stockbit HTTP 429 response.
- Resume safety: dates already marked `COMPLETED` remain preserved and are skipped; the two active ranges do not overlap.
- First post-split verification: the recent worker loaded 21,527 rows for 2023-12-14; the older worker completed 2020-12-31 and continued to 2020-12-30. Both had zero `NEEDS_REVIEW` dates.

## 2026-09-06

### Rename daily-price table

- Action: rename `public."price_stock_indonesia_IDX"` to `public."Price_Stock_Indonesia_IDX"`.
- Data impact: no rows changed.
- Migration: `database/migrations/20260906_001_rename_price_stock_indonesia_idx.sql`.
- Verification: exact table name, row count, date range, constraints, and indexes read back from PostgreSQL.

### Initial daily-price load

- Target at load time: `public."price_stock_indonesia_IDX"` (renamed afterward).
- Source: `indonesia_stocks_daily_from_2023.csv`.
- Source SHA-256: `588064313348629bdb8f6a53c35fc5aeff4e7483f78ff36f8ca6101eaf5b2bc7`.
- Rows: 668,967.
- Distinct tickers: 844.
- Trading-date range: 2023-01-02 through 2026-09-04.
- Query date: 2026-09-06.
- Verification: zero null rows, zero duplicate `(ticker, date)` keys, and all 844 tickers matched `IDX_Stock_Universe`.

### Historical daily-price load (2018-2022)

- Target: `public."Price_Stock_Indonesia_IDX"`.
- Source: `indonesia_stocks_daily_2018_2019.csv`.
- Source SHA-256: `3b92ba28daae47469b2022dcf2cf497df6dadcfba7f3a7b5d7357d61f245d121`.
- Source rows: 209,816; 547 distinct tickers; trading-date range 2018-01-02 through 2019-12-30.
- Source: `indonesia_stocks_daily_2020_2022.csv`.
- Source SHA-256: `4a57e019dc364320e506dba30dbdb35365030ed100ba88de04fe3f897bf1e4d3`.
- Source rows: 420,789; 694 distinct tickers; trading-date range 2020-01-02 through 2022-12-30.
- Combined load: 630,605 new rows and 695 distinct tickers; no existing `(ticker, date)` keys were overwritten.
- Result: the target increased from 668,967 to 1,299,572 rows and now covers 2018-01-02 through 2026-09-04.
- Verification: exact source-to-database row match, zero duplicate source keys, zero post-upsert mismatches, valid nonnegative OHLCV values, and all source tickers matched `IDX_Stock_Universe`.

### Broker-summary backfill recovery

- Target: `public."IDX_Broker_Summary"`.
- Cause: the previous Stockbit session credential expired and affected dates were marked `NEEDS_REVIEW` instead of stopping the whole backfill.
- Recovery: restarted the local supervisor with a refreshed credential; completed dates were skipped automatically.
- First verified recovered date: 2026-03-17.
- Rows loaded for the first recovered date: 24,501.
- Verification: the load status advanced to 2026-03-18 with no authentication error; the remaining date range continues in the background.

### Price automation monitoring table

- Action: created `public."Monitoring_Price_ALL"`.
- Migration: `database/migrations/20260906_002_create_monitoring_price_all.sql`.
- Purpose: track `DAILY` and `RECOVERY` price runs by exchange, universe `Security Type`, timeframe, and target date.
- Expected-symbol source: distinct `IDX_Stock_Universe."Ticker"` values grouped by `Exchange` and `Security Type`.
- Missing-symbol handling: stores both a count and JSON ticker list; unrecovered symbols finish as `NEEDS_REVIEW`.
- Duplicate protection: unique `(exchange, asset_type, timeframe, update_for_date, run_type)` monitoring key.
- Initial rows: 0; no TradingView production query was run during table creation.
- Verification: 18 columns, primary key, run key, status/count/time checks, and date/status index read back from live PostgreSQL.

### Historical broker-summary backfill started

- Target: `public."IDX_Broker_Summary"`.
- Source: Stockbit broker-activity API; no source file or local CSV is produced.
- Requested range and order: 2025-08-31 backward through 2018-01-01; weekends are skipped.
- First verified trading date: 2025-08-29 because 2025-08-31 is a Sunday.
- First verified load: 28,715 rows from 672 complete broker/investor/board filters, with zero duplicate natural keys.
- Parallelism: runs alongside the existing ascending backfill using separate process status and log files.
- Authentication safety: five consecutive HTTP 401/403 responses stop the query as `STOPPED_INVALID_TOKEN` without advancing through the remaining dates.
- Status: the continuous historical backfill remains active; per-date results are recorded in `stockbit_broker_summary_load_log`.
