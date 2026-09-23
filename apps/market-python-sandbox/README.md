# market-python-sandbox

Isolated Python execution for governed datasets. `market-ai-orc` submits model-generated
analysis code here through `run_python_analysis`. This service runs the code over the
immutable Parquet datasets that `market-sql-governor` extracted (`DATASET_READY`) and
returns structured outputs: TABLE, METRICS, CHART, and ARTIFACT.

```text
market-ai-orc ──(bearer PY_SANDBOX_API_KEY)──► market-python-sandbox (harness, root)
                                                 │ POST /v1/datasets/{id}/access  (SQL_GOVERNOR_DATASET_ACCESS_KEY)
                                                 ▼
                                          market-sql-governor ── presigned GET, 120 s, one object
                                                 │
                         verified, read-only copy of the Parquet file
                                                 ▼
                     analysis process: fresh, non-root slot user, rlimits, seccomp
```

The service holds **no PostgreSQL credential and no bucket credential**. It holds two keys:
- `PY_SANDBOX_API_KEY`: accepts requests from market-ai-orc.
- `SQL_GOVERNOR_DATASET_ACCESS_KEY`: can read dataset manifests and obtain short-lived read
  URLs. It cannot submit queries.

Analysis processes hold no keys at all.

## Execution isolation

Every analysis runs in a **fresh process** (`runtime/runner.py`). The model's Python is never
`exec`'d inside the FastAPI process.

| Control | Mechanism |
|---|---|
| Separate user | Each concurrency slot has its own non-root UID (`sandbox1..4`, UID 20001+). The harness starts the child through `subprocess` `user=`/`group=`/`extra_groups=[]`, with no `preexec_fn`. |
| No inherited secrets | The environment is constructed from scratch (PATH, HOME, TMPDIR, locale, thread caps, `PYTHONHASHSEED=0`). File descriptors are closed. The harness runs as root, so `/proc/<harness>/environ` is unreadable to the slot user. |
| Private files | Layout is `jobs/<analysis_id>/`, with the jobs root at 0711 (not listable). `job.json` and `input/*.parquet` are root-owned and read-only. `work/` and `output/` belong to the slot user at 0700. Service storage (`/data`) and the dataset cache are 0700 root. `/tmp` and `/var/tmp` are not writable in the image. |
| CPU | CPU affinity is pinned to `PY_SANDBOX_CPUS_PER_JOB`. `RLIMIT_CPU` is set to runtime × CPUs + 5 s. Thread pools are capped (OpenBLAS/OMP/Polars env, DuckDB `threads`). |
| Memory | An RSS watchdog kills the process at `PY_SANDBOX_MAX_MEMORY_MB`, sampled every 100 ms. `RLIMIT_AS` enforces a hard virtual ceiling of `PY_SANDBOX_MAX_VIRTUAL_MEMORY_MB`. The ceiling is separate because the libraries reserve virtual memory: importing the full stack fails at 1 GiB AS. |
| Runtime | A wall-clock watchdog SIGKILLs the process group at `PY_SANDBOX_MAX_RUNTIME_SECONDS`. |
| Output / disk | `RLIMIT_FSIZE` is set to the per-output byte limit. A job-directory quota (`PY_SANDBOX_MAX_WORKDIR_BYTES`) is checked every second. |
| Syscalls | A seccomp-bpf filter (`runtime/seccomp.py`) is installed before any model code while the process is single-threaded, with TSYNC. It cannot be removed. |

The seccomp filter enforces the following:

- **No sockets.** `socket()` fails with `EACCES` for every family, so there is no TCP, UDP, DNS,
  raw, netlink, or Unix-domain socket. Only an anonymous `AF_UNIX` `socketpair()` is allowed.
- **No new programs or processes.** `execve`, `execveat`, `fork`, and `vfork` are denied, and so
  is `clone()` without `CLONE_THREAD`. `clone3` returns `ENOSYS`, so the C library falls back to
  `clone()` for threads. `subprocess`, `os.system`, and `multiprocessing` therefore fail.
- **No escalation surface.** ptrace, process_vm_*, pidfd_getfd, bpf, perf_event_open, io_uring,
  keyrings, mount (including the new mount API), namespaces, module loading, kexec, handle
  opens, userfaultfd, mknod, and personality are all denied. A non-x86_64 architecture or the
  x32 ABI kills the process.

**Network isolation, stated precisely.** Railway has no egress firewall, and it does not allow
namespaces inside a container. On dev, `unshare(CLONE_NEWNET)` returned EPERM and
`unshare(USER|NET)` returned EACCES. So this is **not a network namespace**. The analysis
process cannot create any socket, which the kernel enforces through seccomp. The service
container itself keeps normal Railway egress, because it must download datasets from the
bucket over the public network.

**Fail closed.** At startup the harness runs a self-test job through the same path and checks:
- non-root UID;
- seccomp active and no_new_privs set;
- inet, inet6, and unix sockets denied;
- fork and execve denied;
- parent and PID 1 environments unreadable;
- clean environment;
- TA-Lib RSI, SMA, STDDEV, and CDLENGULFING results.

If any check fails, `/ready` returns 503 and every analysis is refused with
`SANDBOX_ISOLATION_UNAVAILABLE`. `GET /v1/runtime` (bearer) reports each check and the
library versions.

The source screen (`app/policy.py`) rejects clearly dangerous imports and calls (`subprocess`,
`socket`, `requests`, `urllib`, `ctypes`, `os.system`, `os.environ`, and so on) with
`FORBIDDEN_IMPORT` or `FORBIDDEN_OPERATION`. It is **defense in depth only**. Tests deliberately
bypass it (`getattr(__builtins__, '__import__')`) to prove the kernel filter is the boundary.

## Dataset access

1. For each input the harness calls `POST {SQL_GOVERNOR_URL}/v1/datasets/{id}/access` with
   `{request_id, analysis_id}`. The Governor refuses a missing dataset (404
   `DATASET_NOT_FOUND`), an expired one (410 `DATASET_EXPIRED`, kept distinguishable by
   manifest tombstones), a malformed id, and a file whose size mismatches.
2. For an available dataset, the Governor returns its bounded manifest and a **presigned SigV4
   GET URL for exactly `datasets/<id>/data.parquet`**. The URL expires in
   `SQL_DATASET_ACCESS_URL_TTL_SECONDS` (default 120). It is read-only, cannot list or write,
   and carries only the access-key id and a signature, never the secret key.
3. The harness enforces the input limits before downloading
   (`PY_SANDBOX_MAX_INPUT_ROWS` / `_BYTES`). It streams the file, stops at the manifest's byte
   count, and verifies the manifest SHA-256 (`DATASET_INTEGRITY_ERROR` on mismatch). The
   verified copy is cached read-only in a root-only cache and hard-linked into the job's
   `input/` directory.

The URL is never logged, never stored in a record, never returned to market-ai-orc, and never
visible to the analysis process. Model code receives only the harness-controlled mapping:

```python
DATASETS = {"ds_…": "/sandbox/jobs/ana_…/input/ds_….parquet"}
```

Limitation: within its TTL the URL is a bearer grant for that one object. Anyone holding it
could read that dataset until it expires.

## Runtime interface for analysis code

- **Libraries** (pinned, see `requirements-analysis.txt`): numpy, pandas, polars, pyarrow,
  duckdb, scipy, statsmodels, matplotlib (Agg), and TA-Lib (`import talib`; the wheel bundles
  the TA-Lib C library). pip is removed from the image, and no package can be installed at
  runtime.
- **`saniti` helper module:**
  - `load_dataset(id, columns=None)`
  - `iter_series(df, entity, date, min_history)`: per entity, sorted by date, never mixing
    entities. Entities excluded for short history are recorded in an `INSUFFICIENT_HISTORY`
    warning. If no entity qualifies it raises `InsufficientHistory`.
  - `prepare_panel(df, entity, date, on_duplicate='error'|'keep_last'|'keep_first')`
  - `panel_check(...)`
  - `add_warning(code, message)`
  - `SEED`

  Missing values are never filled by the helpers.
- **Outputs** (only types listed in `expected_outputs`):

  | Helper | Stored as | Returned to the model |
  |---|---|---|
  | `emit_table(name, df)` | Complete Parquet (`result_id`) | `row_count`, columns, preview ≤ `PY_SANDBOX_MAX_TABLE_PREVIEW_ROWS` (50) |
  | `emit_metrics(dict)` | Inline JSON, bounded depth/size | The values |
  | `emit_chart(fig, name, title, description)` | PNG (`artifact_id`) | Metadata only; never image bytes |
  | `emit_artifact(name, data, format='PARQUET'\|'CSV'\|'JSON')` | The file (`artifact_id`) | `artifact_id`, format, rows, bytes, checksum, expiry |

  `print()` is kept only as bounded diagnostics.

The harness re-validates everything the process wrote. Code can bypass the helper, so the
harness checks:
- names and counts;
- the declared type set;
- Parquet footers (row count and columns must match what was declared, and expansion is
  bounded);
- PNG headers;
- preview sizes and JSON validity.

Files are opened with `O_NOFOLLOW`, and only regular files owned by the slot user are
accepted. Any mismatch is `OUTPUT_INVALID`; an oversized result is `OUTPUT_LIMIT_EXCEEDED`.
Nothing is silently truncated. When previews are shortened to fit
`PY_SANDBOX_MAX_OUTPUT_BYTES`, each table reports `preview_row_count` and
`preview_truncated`.

## API (private networking only, bearer `PY_SANDBOX_API_KEY`)

| Endpoint | Purpose |
|---|---|
| `GET /health`, `GET /ready` | Liveness; readiness means the isolation self-test passed |
| `POST /v1/analyses` | `{request_id, purpose, dataset_ids[1..4], python_code ≤ 20000, expected_outputs}`. Unknown fields → 422. Waits up to `PY_SANDBOX_SUBMIT_WAIT_SECONDS`. |
| `GET /v1/analyses/{id}?wait_seconds=` | Status and outputs; waits at most `PY_SANDBOX_MAX_POLL_WAIT_SECONDS` |
| `POST /v1/analyses/{id}/cancel` | Cancel a queued or running analysis |
| `GET /v1/results/{res_…}?offset&limit≤500` | Complete TABLE rows, paged (for backend/frontend presentation, not the model) |
| `GET /v1/artifacts/{art_…}` | PNG / Parquet / CSV / JSON bytes |
| `GET /v1/runtime` | Isolation checks, library versions, limits (operations) |

There are no docs routes and no public domain.

**Statuses:** `QUEUED`, `RUNNING`, `COMPLETED`, `FAILED`, `CANCELLED`, `EXPIRED`.
`next_action` is a fixed function of the status and error code:
`USE_ANALYSIS_RESULT`, `GET_ANALYSIS_RESULT` (with `retry_after_seconds`), `REVISE_ANALYSIS`,
`REVISE_DATA_REQUEST`, `REQUEST_DATA_AGAIN`, `REPORT_LIMITATION`, `STOP_OR_REFORMULATE`, and
`RERUN_ANALYSIS_IF_NEEDED`.

**Error codes:**
- `SYNTAX_ERROR`, `FORBIDDEN_IMPORT`, `FORBIDDEN_OPERATION`, `PYTHON_EXCEPTION`
- `INSUFFICIENT_HISTORY`, `DUPLICATE_OBSERVATIONS`
- `RUNTIME_LIMIT_EXCEEDED`, `MEMORY_LIMIT_EXCEEDED`, `OUTPUT_LIMIT_EXCEEDED`, `OUTPUT_INVALID`,
  `NO_OUTPUT`
- `DATASET_NOT_FOUND`, `DATASET_EXPIRED`, `DATASET_UNAVAILABLE`, `DATASET_INTEGRITY_ERROR`,
  `INPUT_LIMIT_EXCEEDED`
- `SANDBOX_RESTARTED`, `QUEUE_FULL`, `CANCELLED`, `INTERNAL_ERROR`

Error messages carry only the model's own code frames (`<analysis>` line numbers), never
library or harness paths.

**Idempotency:** an identical submission (same request_id, purpose, datasets, code hash, and
outputs) returns the same `analysis_id`. The exception is a transient failure
(`SANDBOX_RESTARTED`, `DATASET_UNAVAILABLE`, `INTERNAL_ERROR`), which may be resubmitted.

## Records, reproducibility, retention

Records live in SQLite on the service volume (`/data/analyses.sqlite3`, root-only). Each
analysis keeps:
- `analysis_id` and `request_id`;
- status, purpose, and expected outputs;
- dataset ids with checksum, rows, bytes, completeness, source tables, and float64 columns;
- `code_sha256` and the source (`PY_SANDBOX_RETAIN_CODE`, default true);
- runtime version, Python version, and every library version (including the TA-Lib C
  version);
- the fixed seed (`PY_SANDBOX_RANDOM_SEED`, applied to `random` and `numpy`; hash seed 0);
- limits, start/completion times, `runtime_ms`, CPU seconds, and peak RSS;
- outputs and warnings;
- the error code and bounded message;
- bounded stdout/stderr tails;
- `research_context`, reserved for the future Research Governor.

Hidden model reasoning is never stored.

**Warnings.** Every analysis whose inputs contain PostgreSQL `numeric` columns carries
`NUMERIC_AS_FLOAT64`. These values are suitable for indicators, returns, and statistics, but
they are not decimal-exact. An input that is not `COMPLETE` carries `INCOMPLETE_INPUT`.

**Retention.**
- Outputs are kept `PY_SANDBOX_RESULT_RETENTION_HOURS` (24). The analysis then becomes
  `EXPIRED`, with its metadata kept.
- Records are kept `PY_SANDBOX_RECORD_RETENTION_DAYS` (30).
- On restart, analyses that were queued or running become `FAILED SANDBOX_RESTARTED`.

**Structured logs.** `sandbox_analysis` events carry:
- request_id and analysis_id;
- dataset_ids and checksums;
- code_sha256 and status;
- runtime_ms, CPU seconds, and peak RSS;
- input rows and bytes;
- output types, rows, and bytes;
- error_code.

Logs never contain keys, dataset URLs, datasets, or tables.

## Configuration

**Required:**
- `PY_SANDBOX_API_KEY` (≥ 32 characters)
- `SQL_GOVERNOR_URL` (private URL)
- `SQL_GOVERNOR_DATASET_ACCESS_KEY` (≥ 32 characters, must differ from the API key and from
  the Governor's `SQL_GOVERNOR_API_KEY`)

**Limits** (backend only; no request field can raise them):

| Variable | Default |
|---|---|
| `PY_SANDBOX_MAX_DATASETS` | 4 |
| `PY_SANDBOX_MAX_INPUT_ROWS` | 2,000,000 |
| `PY_SANDBOX_MAX_INPUT_BYTES` | 256 MiB |
| `PY_SANDBOX_MAX_CODE_CHARS` | 20,000 |
| `PY_SANDBOX_MAX_RUNTIME_SECONDS` | 120 |
| `PY_SANDBOX_MAX_MEMORY_MB` | 2048 |
| `PY_SANDBOX_MAX_VIRTUAL_MEMORY_MB` | 4096 |
| `PY_SANDBOX_CPUS_PER_JOB` | 2 |
| `PY_SANDBOX_THREADS_PER_JOB` | 2 |
| `PY_SANDBOX_MAX_TABLES` | 8 |
| `PY_SANDBOX_MAX_TABLE_OUTPUT_ROWS` | 100,000 |
| `PY_SANDBOX_MAX_TABLE_PREVIEW_ROWS` | 50 |
| `PY_SANDBOX_MAX_METRICS` | 8 |
| `PY_SANDBOX_MAX_METRICS_BYTES` | 8000 |
| `PY_SANDBOX_MAX_OUTPUT_BYTES` | 24,000 (model-facing result) |
| `PY_SANDBOX_MAX_ARTIFACT_BYTES` | 64 MiB |
| `PY_SANDBOX_MAX_CHARTS` | 8 |
| `PY_SANDBOX_MAX_ARTIFACTS` | 8 |
| `PY_SANDBOX_MAX_WORKDIR_BYTES` | 512 MiB |
| `PY_SANDBOX_CONCURRENCY` | 1 |
| `PY_SANDBOX_MAX_QUEUED` | 8 |
| `PY_SANDBOX_SUBMIT_WAIT_SECONDS` | 25 |
| `PY_SANDBOX_MAX_POLL_WAIT_SECONDS` | 20 |
| `PY_SANDBOX_RETRY_AFTER_SECONDS` | 15 |
| `PY_SANDBOX_RESULT_RETENTION_HOURS` | 24 |
| `PY_SANDBOX_RECORD_RETENTION_DAYS` | 30 |
| `PY_SANDBOX_CLEANUP_INTERVAL_SECONDS` | 3600 |

**Paths:**

| Variable | Default |
|---|---|
| `PY_SANDBOX_DATA_DIR` | `/data` (the Railway volume) |
| `PY_SANDBOX_JOBS_DIR` | `/sandbox/jobs` |
| `PY_SANDBOX_CACHE_DIR` | `/sandbox/cache` |
| `PY_SANDBOX_DATASET_CACHE_BYTES` | 1 GiB |
| `PY_SANDBOX_DATASET_URL_SCHEMES` | `https` (`file` is for local tests only) |

## Railway service design (not deployed)

- **Service:** `market-python-sandbox`, local upload of this directory (like
  market-sql-governor), with no public domain.
- **Volume:** one Railway volume mounted at `/data`. Consequences:
  - single replica;
  - brief downtime on redeploy;
  - in-flight analyses become `SANDBOX_RESTARTED`.
- **Variables:**
  - `PY_SANDBOX_API_KEY`, which market-ai-orc references;
  - `SQL_GOVERNOR_URL=http://market-sql-governor.railway.internal:8080`;
  - `SQL_GOVERNOR_DATASET_ACCESS_KEY`, which the Governor also receives.
- **Changes to other services:**
  - market-sql-governor: add `SQL_GOVERNOR_DATASET_ACCESS_KEY`.
  - market-ai-orc: add `PY_SANDBOX_URL=http://market-python-sandbox.railway.internal:8080` and
    `PY_SANDBOX_API_KEY`. orc registers the three analysis tools only if the sandbox reports
    ready at orc startup.
- **Memory:** about 3 GB for one 2 GB analysis plus the harness.

## Tests

```bash
pip install -r requirements-dev.txt
sudo pytest   # root is required for the slot-user isolation tests; they are skipped otherwise
```

- `tests/test_units.py`: configuration, schema, source screen, seccomp program, helpers.
- `tests/test_sandbox.py`: real child processes covering:
  - isolation self-test;
  - TA-Lib RSI and CDLENGULFING with ticker partitioning, date ordering, and minimum history;
  - rolling z-score;
  - large-table preview and paged retrieval;
  - chart and artifact storage;
  - syntax, forbidden import, and kernel-denied network/subprocess/fork/multiprocessing
    attempts;
  - runtime, memory, row, and byte limits;
  - forged outputs and symlinks;
  - dataset not found, expired, and tampered;
  - no credentials in the process;
  - no secrets in logs;
  - lifecycle, idempotency, cancel, restart, and retention.
