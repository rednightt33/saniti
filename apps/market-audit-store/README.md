# market-audit-store

Durable, queryable audit storage for AI research runs (implementation plan IP2, solution 2).

The service is **implemented but not deployed**:

- the Railway service and the private bucket do not exist yet;
- migration `20260928_001_create_ai_audit_store.sql` has not been applied;
- every producer flag is off.

## What it owns

| Piece | Where |
|---|---|
| Audit metadata | PostgreSQL schema `ai_audit` (migration `20260928_001`). |
| Audit objects | A private bucket, for example `market-ai-audit-artifacts`, separate from `market-sql-datasets`. |
| Contract | `openapi/audit-store-v1.json` (contract `audit-store/v1`), generated from the app with `python -m app.export_openapi`. |

Producers, and what each hands over:

| Producer | What it hands over | How |
|---|---|---|
| market-sql-governor | Raw input Parquet and extraction manifest of each dataset, with checksum and lineage. | Outbox markers in its dataset bucket, drained by `app/audit_archive.py`. |
| market-python-sandbox | Exact Python source, runtime/library manifest, execution trace, released outputs, execution manifest, validation result, approved DataNeed contract and input bundle manifest. | SQLite outbox plus a root-only spool, drained by `app/audit.py` in the root harness. |
| market-ai-orc | Run and conversation identity, observable model and tool events, sanitized tool arguments and results, final response, model/provider metadata, token and duration summary. | One `RUN_FINISHED` row INSERTed into `ai_audit.ingest_outbox`, consumed by this service. |

**Hidden model reasoning is never stored.**

- No table has a column for it.
- Producer payloads refuse any key that names reasoning.
- The outbox consumer drops such keys as a second guard.
- market-ai-orc stores only a reasoning *token count*.
- `OPENROUTER store=false` is unchanged.

`AI_research_run_audit` remains the per-run summary and the recovery fallback.

## Schema `ai_audit`

| Table | Content |
|---|---|
| `run` | One row per `request_id`: stable `run_id`, conversation and turn, parent run of a rerun, status, retention class and `expires_at`, model/provider, deployment, summary, and the expectations and missing items. |
| `event` | Ordered events, `seq` from 1 per run. **Append-only**: no UPDATE grant, and a trigger refuses UPDATE and DELETE for every role. Payload up to 16 KiB; larger content is an artifact referenced by `artifact_id`. Idempotent on `(run, source, idempotency_key)`. |
| `artifact` | One content-addressed object (`objects/sha256/<ab>/<sha256>`), deduplicated on sha256 and byte count. State `PENDING` → `READY` / `REJECTED`; `DELETED` is reserved for retention. |
| `run_artifact` | Links a run to an artifact with a role, and an optional execution and label. Idempotent. |
| `execution` | One sandbox execution: session, bundle, sequence, status, source hash, runtime image, library evidence, seed, timezone, input checksums in order, contract hash, resample traces, resource usage. |
| `runtime_image` | One runtime inventory: Python, OS, architecture, locked-requirements hash, every installed distribution and version. Keyed by the sha256 fingerprint. |
| `artifact_access` | Append-only log of every read granted: who, why, which run, and when the URL expires. |
| `retention_hold` | A pin or legal hold on one run or one artifact. |
| `ingest_outbox` | market-ai-orc's `RUN_FINISHED` rows. The orchestrator may only INSERT the producer columns. This service records `PENDING`, `COMPLETE`, `FAILED_RETRYABLE` or `INCOMPLETE`. |

Roles and logins:

| Role | Privileges | Login |
|---|---|---|
| `market_ai_audit_store` | SELECT, INSERT, UPDATE on the tables; no DELETE or TRUNCATE anywhere. | `market_ai_audit`, created by `scripts/provision_market_ai_audit_login.py`. |
| `market_ai_audit_outbox_writer` | INSERT of `(source, idempotency_key, request_id, kind, payload)` into `ingest_outbox` only. | Granted to `market_ai_orc` by `scripts/provision_market_ai_orc_login.py`. |

The SQL Governor, catalog, preview and conversation roles have no access to the schema.

`Table_Catalog` documents public tables only (constraint `Table_Catalog_target_schema_check`), so these tables are
documented here and in the migration.

## Run state

`OPEN` → `FINALIZING` → `COMPLETE`, or `INCOMPLETE` (retryable).

1. A run is `OPEN` until market-ai-orc's `RUN_FINISHED` arrives. That row names the executions and completions the
   sandbox must have archived.
2. Evaluation then requires all of the following to be `READY`:
   - `TOOL_TRACE` and `FINAL_RESPONSE`;
   - for each expected execution: its record, `PYTHON_SOURCE` and `RUNTIME_MANIFEST`;
   - every raw input its record names, linked as `RAW_INPUT_PARQUET` by checksum;
   - an `EXECUTION_MANIFEST` for each expected completion;
   - every released output;
   - every dataset the Governor announced.
3. Anything missing makes the run `INCOMPLETE`, with the missing items listed. It is re-evaluated whenever a late
   artifact, link or execution arrives, and by a periodic sweep within `AUDIT_REEVALUATE_HOURS`.
4. A new unmet expectation brings a `COMPLETE` run back to `INCOMPLETE`. **Completion is never reported while required
   evidence is missing.**

## Artifact protocol

1. **Register.** `POST /v1/internal/artifacts` with sha256, size and media type.
   - An existing `READY` object is deduplicated: no upload.
   - A different size for a known sha256 is refused (`ARTIFACT_SIZE_CONFLICT`).
   - Otherwise the producer receives one presigned PUT for a one-off **staging** key (`staging/<artifact_id>/<nonce>`),
     valid for `AUDIT_UPLOAD_URL_TTL_SECONDS` (default 300).
2. **Upload.** The producer PUTs the bytes.
3. **Verify.** `POST /v1/internal/artifacts/{id}/verify`: this service reads the staged object and computes sha256 and
   size itself.
   - On a match, it copies the object to its content address and marks it `READY`.
   - Otherwise the artifact is `REJECTED` (`CHECKSUM_MISMATCH` or `SIZE_MISMATCH`) and can be prepared again.
   - The staged object is deleted either way.
4. **Why staging.** A still-valid upload URL writes a key that nothing reads, so it can never replace a `READY`
   object.
5. **What producers never do.** They never list or read the bucket, and never see an object key. Responses carry
   artifact IDs only.

The server-side hash is deliberate. Whether Railway buckets (Tigris) enforce signed `x-amz-checksum-sha256` headers on
presigned PUTs is not documented, so this service does not rely on it.

## API (contract `audit-store/v1`)

**Producer endpoints.** Each takes `AUDIT_STORE_GOVERNOR_KEY` or `AUDIT_STORE_SANDBOX_KEY`, and the caller is recorded
as the source.

| Endpoint | Purpose |
|---|---|
| `POST /v1/internal/runs` | Register a run. Idempotent on `request_id`. |
| `POST /v1/internal/runs/{run_id}/events` | Append events. Idempotent on the event key. |
| `POST /v1/internal/artifacts` | Prepare an artifact (`upload: false` only references content another producer uploads). |
| `POST /v1/internal/artifacts/{artifact_id}/verify` | Verify an upload. |
| `POST /v1/internal/runs/{run_id}/artifacts` | Link artifacts to a run. |
| `POST /v1/internal/executions` | Register an execution, with its runtime inventory and library evidence. |
| `POST /v1/internal/runs/{run_id}/finalize` | Add expectations (dataset ids, output checksums). Only market-ai-orc's `RUN_FINISHED` marks a run finished. |

**Query endpoints.** They take `AUDIT_STORE_READER_KEY`. An optional `X-Audit-Accessor` header names the person.

| Endpoint | Purpose |
|---|---|
| `GET /v1/runs/{run_id}`, `GET /v1/requests/{request_id}/run` | The run, its counts, expectations and missing items. |
| `GET /v1/runs/{run_id}/events?after_seq=&limit=` | Ordered events. |
| `GET /v1/runs/{run_id}/artifacts` | Linked artifacts: role, checksum, size, state. Never the object key. |
| `GET /v1/conversations/{conversation_id}/runs` | The runs of one conversation. |
| `GET /v1/executions/{execution_id}/runtime` | Runtime image and library evidence of one execution. |
| `GET /v1/runs/{run_id}/replay-manifest` | Everything a replay needs (see below). |
| `POST /v1/artifacts/{artifact_id}/access` | `{purpose, run_id?}` → a presigned GET valid for `AUDIT_ACCESS_URL_TTL_SECONDS`. Logged in `artifact_access`; `READY` artifacts only. |
| `POST /v1/retention-holds`, `POST /v1/retention-holds/{hold_id}/release` | Pin or legal hold. |
| `GET /v1/retention/report` | Dry-run retention report. |

Health: `GET /health` (liveness) and `GET /ready` (database and bucket reachable).

### Library evidence per execution

Each category is recorded separately:

- `runtime.distributions`: everything installed in the image, from `importlib.metadata`, because pip is removed;
- `declared_imports`: import names parsed from the source's AST;
- `loaded_distributions`: top-level modules first seen in `sys.modules` after the execution, mapped with
  `importlib.metadata.packages_distributions()`;
- `prebound_packages`: pandas, NumPy, DuckDB and saniti, bound into every namespace before the code runs;
- `stdlib_modules` and `unresolved_modules`.

A library is claimed as used only when it was observed.

### Replay

The replay manifest contains:

- raw input hashes, and the input ordering per execution;
- the approved contract hashes;
- the Python source hash;
- the random seed and the timezone;
- the resample semantics version;
- the runtime fingerprint and the package manifest;
- the output hashes.

The deterministic Python computation can be replayed when all of these dependencies are present. The model's own
output (which code it wrote, what it answered) comes from a provider and may not be reproducible.

## Retention

| Data | Retention | Owner |
|---|---|---|
| Sandbox results and outputs | About 24 hours | Unchanged |
| Governor working datasets | About 7 days | Unchanged |
| Sandbox records | About 30 days | Unchanged |
| Audit runs, standard class | 90 days (`AUDIT_RETENTION_STANDARD_DAYS`) | This service |
| Audit runs, pinned class | 365 days (`AUDIT_RETENTION_PINNED_DAYS`) | This service |
| Retention hold | Keeps a run or artifact regardless of expiry | This service |

**Destructive cleanup is not enabled in this release.** `GET /v1/retention/report` is a dry run. It lists an object as
`ELIGIBLE` only when every run that references it has expired and no active hold covers it or those runs. Shared or
held objects are reported as `REFERENCED_BY_UNEXPIRED_RUN` or `HELD`.

## Configuration

| Variable | Required | Default | Meaning |
|---|---|---|---|
| `AUDIT_DATABASE_URL` | yes | — | The `market_ai_audit` login. |
| `AUDIT_STORE_GOVERNOR_KEY`, `AUDIT_STORE_SANDBOX_KEY`, `AUDIT_STORE_READER_KEY` | at least one | — | Distinct keys, each 32+ characters. |
| `AUDIT_BUCKET_NAME`, `AUDIT_BUCKET_ENDPOINT`, `AUDIT_BUCKET_REGION`, `AUDIT_BUCKET_ACCESS_KEY_ID`, `AUDIT_BUCKET_SECRET_ACCESS_KEY` | yes (production) | — | The private audit bucket; only this service holds these credentials. |
| `AUDIT_LOCAL_OBJECT_DIR`, `AUDIT_LOCAL_SIGNING_KEY`, `AUDIT_PUBLIC_BASE_URL` | development only | — | Local objects with signed URLs served by this service. |
| `AUDIT_UPLOAD_URL_TTL_SECONDS` / `AUDIT_ACCESS_URL_TTL_SECONDS` | no | 300 / 120 | Presigned URL lifetimes. |
| `AUDIT_MAX_ARTIFACT_BYTES` | no | 268435456 | Largest accepted object. |
| `AUDIT_RETENTION_STANDARD_DAYS` / `AUDIT_RETENTION_PINNED_DAYS` | no | 90 / 365 | Retention classes. |
| `AUDIT_OUTBOX_ENABLED`, `AUDIT_OUTBOX_POLL_SECONDS`, `AUDIT_OUTBOX_BATCH`, `AUDIT_OUTBOX_MAX_ATTEMPTS` | no | true, 10, 20, 12 | The market-ai-orc outbox consumer. |
| `AUDIT_REEVALUATE_HOURS` | no | 48 | How long `INCOMPLETE` runs are re-evaluated. |

Producer flags (all default `false`):

| Service | Flags and variables |
|---|---|
| market-ai-orc | `AI_AUDIT_STORE_ENABLED`, `AI_AUDIT_STORE_REQUIRED`, `AUDIT_OUTBOX_DATABASE_URL` (the `market_ai_orc` login). |
| market-python-sandbox | `PY_SANDBOX_AUDIT_STORE_ENABLED`, `AUDIT_STORE_URL`, `AUDIT_STORE_SANDBOX_KEY`, `PY_SANDBOX_AUDIT_SPOOL_MAX_BYTES`, `PY_SANDBOX_AUDIT_POLL_SECONDS`, `PY_SANDBOX_AUDIT_MAX_ATTEMPTS`, `PY_SANDBOX_AUDIT_TIMEOUT_SECONDS`. |
| market-sql-governor | `SQL_GOVERNOR_AUDIT_STORE_ENABLED`, `AUDIT_STORE_URL`, `AUDIT_STORE_GOVERNOR_KEY`, `SQL_GOVERNOR_AUDIT_POLL_SECONDS`, `SQL_GOVERNOR_AUDIT_MAX_ATTEMPTS`, `SQL_GOVERNOR_AUDIT_TIMEOUT_SECONDS`. |

The Audit Store variables are validated, and required, only while the producer's flag is on.

## Runbook: manual Railway setup (done on dev, 2026-09-30)

Status on dev (2026-09-30, `RAILWAY_CHANGELOG.md`): bucket `market-ai-audit-artifacts`
(`f29461fa-0ad8-4886-bbf1-2df2b4966357`), service `market-audit-store` (`956b1479-e8c6-4f6d-bd39-2af46390a22a`,
private only), migration `20260928_001` applied and read back, login `market_ai_audit`, all three producers on in
shadow mode (`AI_AUDIT_STORE_REQUIRED=false`). Steps 1–7 below were done in that order; the deployment order below
is done up to step 7 on dev.


1. **Bucket.** Create a private bucket (for example `market-ai-audit-artifacts`) in environment `dev`. Give its
   credentials only to the new service.
2. **Service.** Create `market-audit-store`:
   - root `apps/market-audit-store`;
   - watch pattern `/apps/market-audit-store/**`;
   - Dockerfile build;
   - private networking only (`market-audit-store.railway.internal:8080`), no public domain.
3. **Migration.** Apply `20260928_001_create_ai_audit_store.sql`:
   - `scripts/apply_migration.py` in dry-run mode, then apply;
   - read back the schema, the grants and the verify block.
4. **Logins.**
   - Run `scripts/provision_market_ai_audit_login.py` (`MARKET_AI_AUDIT_DB_PASSWORD`).
   - Re-run `scripts/provision_market_ai_orc_login.py` so `market_ai_orc` joins `market_ai_audit_outbox_writer`.
5. **Keys.** Generate three distinct 32+ character keys and set the variables above. Record only names and
   verification status in `RAILWAY_CHANGELOG.md`.
6. **Verify the service.** Deploy it, then check `GET /ready`.
7. **Verify the contract.** `python -m app.export_openapi` must leave `openapi/audit-store-v1.json` unchanged
   (a test checks this).

## Deployment order

1. Migration `20260928_001`, then the logins.
2. market-audit-store, with no producer enabled yet.
3. Governor adapter, flag off.
4. Sandbox adapter, flag off.
5. market-ai-orc adapter, flag off. These three already ship with this code; with the flags off their behaviour is
   unchanged.
6. Shadow mode on dev: `SQL_GOVERNOR_AUDIT_STORE_ENABLED`, `PY_SANDBOX_AUDIT_STORE_ENABLED` and
   `AI_AUDIT_STORE_ENABLED` set to `true`, with `AI_AUDIT_STORE_REQUIRED=false`.
7. Watch the logs (`audit_run_status`, `*_audit_*`) and `GET /v1/runs/{id}` of real runs until they reach `COMPLETE`.
8. Solution 1:
   - apply migration `20260928_002_seed_resample_rules.sql` together with, or after,
     `PY_SANDBOX_DERIVED_FREQUENCY_ENABLED=true`;
   - run the golden weekly/monthly tests;
   - then set `AI_ENABLE_DERIVED_FREQUENCY=true`.
9. Promote to staging and production with the flags off, then enable them step by step.

## Rollback

- Turn the flags off: every producer returns to its previous behaviour.
- Migrations are additive and stay in place. Nothing is dropped.
- A wrong resample rule is corrected by a forward migration that sets that column back to NULL.
- Pending outbox rows stay durable (the orchestrator outbox table, sandbox SQLite, Governor markers) and drain when
  archival is re-enabled.

## Development

```bash
pip install -r requirements-dev.txt
AUDIT_TEST_POSTGRES_URL=postgresql://postgres@127.0.0.1:55432/postgres pytest -q
python -m app.export_openapi   # after an API change
```

The integration tests connect as a login that belongs only to `market_ai_audit_store`, so they also prove that the
grants are sufficient.
