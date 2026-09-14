# Revised Implementation Plan — Production AI Market Analyst

## Status dan Scope

Plan ini menggantikan working plan sebelumnya dan memasukkan requirements dari
`Tools.md`, AI Analyst addendum, final limit/context requirements, dan empat
historical-integrity requirements terakhir.

Status eksekusi per 2026-09-13:

- Feature 1, Feature 2, dan Feature 3 telah backfill, direkonsiliasi, divalidasi,
  serta terdaftar. Feature 2 memiliki 42.598.713 row/38 definisi `v1`; Feature 3
  memiliki 2.268.015 row/24 definisi `v1`.
- Release 1A selesai: foundation, historical-integrity metadata, Golden Test
  tables, least-privilege roles, dan index-plan acceptance sudah live serta
  terdokumentasi melalui migration forward-only.
- Release 1B backend sudah diimplementasikan di `apps/market-ai-backend`.
  Structured handlers, limit enforcement, token-aware semantic compaction,
  progressive tool exposure, durable request worker, audit, evidence, dan
  immutable result snapshot tersedia.
- Release 1B hardening menambahkan satu `Analysis_Model_Call` per provider call,
  bounded provider-returned reasoning retention, conditional/scoped QC untuk
  semua tool, dan compaction saat cumulative-input pressure mencapai 75%.
- Migration `20260913_021_finalize_market_ai_release_1b.sql` dan limit-alignment
  `20260913_022_align_market_ai_tool_limits.sql` sudah diterapkan. Live handler
  verification PASS dan deterministic Golden Test suite 16/16 PASS. Tool generik
  `find_condition_runs` sekarang menangani rangkaian kondisi pada observasi hari
  transaksi tanpa Analytics Worker.
- Railway service `market-ai-backend` sudah terhubung ke GitHub, terdeploy, dan
  sehat. Initial deployment `db143fa6-3eff-4cf3-9ebe-c1d56d53b171` dan current
  diagnostic deployment `8bbb044a-b8bf-49f9-b4ab-b85d234ec1a5` mencapai
  `SUCCESS`; startup dan private `/health` HTTP 200 terverifikasi. Seluruh 43
  configuration keys tersedia. Login `market_ai_app` dapat membaca
  Feature/katalog dan menulis audit, tetapi raw-table SELECT ditolak.
- Model-call audit hardening deployment `4d49e4a1-afdd-4abb-b92b-974edc63eb09`
  mencapai `SUCCESS`; live DeepSeek request membuat delapan per-call audit rows,
  backend verification PASS, dan Golden Test tetap 16/16 PASS.
- `OPENAI_API_KEY` tetap tersimpan tetapi akun tersebut menolak request dengan
  `insufficient_quota` / `credit_balance_exhausted`. Project owner kemudian
  menambahkan `OPENROUTER_DEEPSEEK`; bounded function-call dan strict structured
  output probe untuk `deepseek/deepseek-v4.1-flash` PASS. `dev` sekarang memilih
  OpenRouter melalui provider adapter yang allowlisted.
- Otomasi update Feature 2/3 tetap di luar scope ini. Release 2 generic Analytics
  Worker, immutable bounded snapshot handoff, and the first telco forward-outcome
  Golden Test are implemented by migration `040` and the two market AI services.

Transport mendukung provider allowlist `openai` dan `openrouter` tanpa arbitrary
base URL atau silent fallback. OpenAI default tetap `gpt-5.6-terra`/`medium`;
OpenRouter default dan konfigurasi `dev` adalah
`deepseek/deepseek-v4.1-flash`/`high`. Private backend dibuat dan distabilkan
sebelum integrasi Telegram.

## Prinsip Arsitektur

Sistem harus:

1. memakai generic tools yang menemukan Feature baru melalui catalog;
2. menolak free-form SQL dan unsafe cross-grain joins;
3. memisahkan database limits, Analytics Worker limits, dan LLM context limits;
4. memberi model hanya hasil ringkas yang relevan, bukan seluruh query result;
5. memperluas tool families secara progresif ketika bukti mengharuskan;
6. membedakan invalid data dari market anomaly yang valid;
7. menjaga point-in-time validity, no-look-ahead, reproducibility, dan golden tests;
8. menggunakan least privilege dan menyimpan evidence yang dapat diaudit.

## Database dan Catalog

### Existing foundation

Migration `009` sudah menambahkan:

- readiness metadata pada `Table_Catalog`;
- usage metadata pada `Feature_Catalog`;
- `Feature_Relationship_Catalog`;
- `Tool_Catalog`;
- `Analysis_Request`;
- `Analysis_Step_Log`;
- `Analysis_Evidence`;
- `check_analysis_data_readiness(text[])`;
- NOLOGIN roles `market_ai_reader`, `market_ai_logger`, dan
  `market_analytics_worker`.

### Corrective forward-only migration

Migration berikutnya menambahkan kontrak yang baru disetujui:

#### `Table_Catalog`

- `observation_date_column`;
- `data_available_at_column`;
- `availability_rule`;
- `point_in_time_status`: `AVAILABLE`, `PARTIAL`, `UNAVAILABLE`, atau
  `NOT_APPLICABLE`;
- `historical_metadata_method`.

`data_available_at_column` hanya diisi jika timestamp tersebut memang memiliki
makna historis yang terbukti. `calculated_at` dari backfill tidak boleh dianggap
sebagai waktu data dahulu tersedia.

#### `Feature_Catalog`

- `availability_rule` untuk menjelaskan kapan nilai boleh dipakai oleh keputusan;
- `point_in_time_safe`;
- `historical_metadata_warning`;
- `analytical_interpretation`;
- `recommended_use`;
- `misuse_warning`;
- `semantic_review_status`;
- `validation_evidence`.

Semua 91 baris aktif Feature 1–3 telah diisi dan diaudit sebagai
`CALCULATION_VERIFIED`. Query data/aggregation menjalankan semantic preflight:
orchestrator otomatis memuat ringkasan definisi kolom output, filter, ordering,
grouping, metric, dan condition yang relevan dalam call yang sama. AI tidak
ditolak hanya karena lupa memanggil definisi terlebih dahulu. Definisi lengkap
tetap diambil melalui `get_feature_definition` ketika formula/metodologi rinci
dibutuhkan; katalog penuh tidak dimuat otomatis.

Material formula or methodology changes selalu membuat versi baru. Old versions
tidak ditimpa atau diinterpretasikan ulang.

#### `Analysis_Request`

Tambahkan structured `version_snapshot jsonb` dan `methodology_metadata jsonb`.
Existing `input_tokens`, `output_tokens`, and `total_tokens` are defined as
cumulative usage across every OpenAI call belonging to the request, not merely the
last call. Add `current_context_tokens` and `peak_context_tokens` so the hard
per-call context ceiling can be audited separately from cumulative cost. Existing
`context_compaction_count` records each compaction event. Usage updates must be
atomic so retries or concurrent lease recovery cannot silently lose counts.
Snapshot minimum:

```text
model_provider
model_id
reasoning_effort
orchestrator_version
orchestrator_prompt_version
feature_table_versions_used
feature_definition_versions_used
tool_names_used
tool_versions_used
analytics_method_versions_used
analysis_ready_date
analysis_timestamp
relevant_query_hashes
evidence_ids
```

`methodology_metadata` menyimpan setidaknya:

```text
universe_method
point_in_time_universe_available
survivorship_bias_warning
historical_metadata_method
signal_observation_time
signal_available_time
entry_time
lookahead_check_status
```

Version snapshot ditulis saat request selesai dan bersifat immutable setelah
status `SUCCESS`.

#### `Analysis_Model_Call`

Satu row per provider call menyimpan request/iteration, provider/model/reasoning
effort, analytical stage, exposed tool families, provider response ID, per-call
input/output/reasoning tokens, estimated active context, dan concise
`decision_summary`. Hanya reasoning block yang benar-benar dikembalikan provider
yang boleh disimpan; hidden chain-of-thought tidak direkonstruksi. Raw reasoning
dibatasi per-call, memiliki retention deadline, lalu dipurge secara idempotent
tanpa menghapus row audit atau decision summary.

#### Golden-test storage

Buat:

- `Golden_Analysis_Test`: versioned test definition, expected capabilities,
  fixed date/range, expected features/tools, numerical/result conditions,
  tolerance, warnings, expected status, activation state;
- `Golden_Analysis_Test_Run`: release/model/prompt/tool/Feature version snapshot
  dan aggregate pass/fail result;
- `Golden_Analysis_Test_Result`: result per test, observed metrics, deviation,
  warnings, evidence IDs, duration, tokens, and failure reason.

Ketiga tabel mengikuti catalog policy dan tidak menyimpan secrets atau large raw
results.

#### Analytics phase storage

Release 2 creates `Analytics_Job` and `Analytics_Dataset_Snapshot`. Input data is
stored as an immutable short-lived `.json.gz` object in a private Railway bucket,
not as large JSON in a job row. The worker has no PostgreSQL/raw/Feature credentials.

## Data Readiness dan Availability

`check_analysis_data_readiness` tetap menghitung latest safe common data date,
tetapi freshness bukan bukti availability time.

Tool execution memakai tiga waktu terpisah:

```text
observation_date
data_available_at
decision_available_at
```

Jika historical availability timestamp tidak terbukti, daily Feature 1–2 memakai
aturan konservatif:

```text
signal memakai data melalui close t
earliest permitted entry = next valid trading observation t+1
```

Kondisi database sekarang:

- `Price_Stock_Indonesia_IDX.ingestion_time` tersedia untuk ingestion baru, tetapi
  dapat NULL untuk historical rows;
- `Feature_01_Stock_Daily.sector` dan `industry` adalah current metadata, bukan
  point-in-time metadata;
- `IDX_Broker_Summary` belum menyimpan historical source-availability timestamp;
- `Feature_02_Broker_Rolling.calculated_at` adalah materialization time, bukan
  bukti historical decision availability;
- Feature 2 `broker_type` dan `broker_classification` adalah current metadata.

Karena itu, timestamp backfill atau current classification tidak boleh dipakai
untuk mengklaim point-in-time correctness.

## Point-in-Time Universe dan Survivorship Bias

Historical screen, event study, signal validation, forward-return analysis, dan
backtest tidak boleh diam-diam memakai current `IDX_Stock_Universe` sebagai
historical universe.

Preferred flow:

```text
historical analysis date
→ eligible securities at that date
→ point-in-time metadata where available
→ analysis
```

Initial Feature 1–2 reality:

- complete point-in-time IDX universe dan metadata history belum tersedia;
- Feature 1 was built through current-universe matching, sehingga delisted or
  currently missing tickers may be absent;
- Feature 2 retains source symbols even when absent from current universe.

Sampai historical universe tersedia, analysis masih boleh berjalan bila
methodology lain valid, tetapi wajib:

- set `point_in_time_universe_available=false`;
- set `SURVIVORSHIP_BIAS_WARNING`;
- menjelaskan apakah fallback memakai observed-data universe, current universe,
  atau subset lain;
- tidak menganggap first/last observed price sebagai proof of listing/delisting;
- mempertahankan historical symbols yang masih ada di Feature source;
- hanya memasukkan new listings setelah minimum feature history terpenuhi.

Roadmap data yang disarankan adalah versioned `Security_Universe_History` dan
`Security_Metadata_History` dengan valid-from/valid-to evidence. Tabel tersebut
tidak boleh dibuat dari inference lemah dan baru ditambahkan ketika authoritative
source tersedia.

## Data Quality Policy

`check_data_quality` menghasilkan:

- `FAIL`: impossible/invalid data, duplicate grain, broken constraints, unsafe
  join, look-ahead failure, or method without usable sample;
- `WARNING`: incomplete history, missing metadata, stale dependency, unknown
  historical availability, survivorship limitation, or weak sample;
- `PASS` plus anomaly flag: statistically extreme but source-valid market
  observations.

Large returns, volume spikes, extreme broker flow, or z-scores are not removed
merely for being extreme. They remain available to `detect_anomalies` and retain
source/evidence references.

QC runtime bersifat conditional dan scoped untuk semua tool. Ia dipanggil ketika
hasil menunjukkan gap/NULL/coverage, freshness atau cross-feature concern,
anomali yang perlu divalidasi, atau ketika quality evidence material bagi
kesimpulan. Ia tidak otomatis memindai seluruh periode setiap query. `WARNING`
dan `PASS` dengan anomaly flag tetap dianalisis; hanya `FAIL` impossible/invalid
yang memblokir kesimpulan pada scope terkait.

Any methodology failing the explicit no-look-ahead validation must not be
reported as valid predictive evidence.

## Database Indexing and Physical Scan Policy

Result limits and physical scan efficiency are independent. `LIMIT 5000` and
`QUERY_MAX_ESTIMATED_ROWS` do not make a query acceptable if PostgreSQL must scan
an unnecessarily large portion of a Feature table.

For every major Feature table, document and validate these high-frequency access
patterns before production:

- single-ticker historical date range;
- ticker plus market board plus date range;
- ticker plus broker plus date range;
- single-date cross section;
- date-bounded screening and ranking.

Expected initial paths:

- Feature 1 ticker history: primary key `(ticker,date)`;
- Feature 1 cross section: existing `(date)` index;
- Feature 2 exact ticker/board/broker history: primary key
  `(ticker,market_board,broker,date)`;
- Feature 2 cross section: existing `(date,market_board,ticker)` index.

The existing paths must be tested rather than assumed sufficient. In particular,
Feature 2 ticker/date, ticker/board/date without broker, and ticker/broker/date
without board may need a different index order. Do not add those large indexes
blindly.

Run controlled `EXPLAIN (ANALYZE, BUFFERS)` using representative bounded queries,
including BBCA during 2023. Record:

```text
query pattern
chosen index
plan node type
rows scanned/removed
rows returned
planning time
execution time
shared hit/read buffers
```

Production acceptance requires the intended Index Scan or Bitmap Index Scan for
selective history queries, not a full-table sequential scan. Add a forward-only
index migration only where the measured plan is insufficient. Re-run the same
plans after any new index and record the before/after evidence. Screening queries
may use a date index followed by a bounded sort; feature-value-specific indexes are
added only after observed production/golden-test demand justifies their write and
storage cost.

## Three Independent Resource Policies

### 1. Database/query policy

```text
QUERY_DEFAULT_ROWS=500
QUERY_MAX_ROWS=5000
QUERY_MAX_TICKERS=20
QUERY_MAX_COLUMNS=20
QUERY_MAX_DATE_RANGE_DAYS=1825
QUERY_MAX_UNFILTERED_DATE_RANGE_DAYS=31
QUERY_MAX_ESTIMATED_ROWS=100000
QUERY_TIMEOUT_SECONDS=15
QUERY_MAX_OUTPUT_BYTES=1048576
QUERY_MAX_GROUPS=1000
QUERY_MAX_PERIODS=6
CONDITION_RUNS_MAX_DATE_RANGE_DAYS=7305
CONDITION_RUNS_MAX_EPISODES=200
```

`QUERY_MAX_ROWS=5000` is a backend processing/result ceiling where allowed. It is
not permission to inject 5,000 rows into model context.

`find_condition_runs` mempunyai rentang lebih panjang daripada retrieval umum
karena PostgreSQL mengembalikan episode ringkas, bukan seluruh candle. Pengecualian
ini tetap memakai maksimum ticker, estimated-row, timeout, output-byte, dan
LLM-facing budgets. Semua kondisi digabung dengan AND, NULL memutus rangkaian,
dan unit consecutive adalah observasi perdagangan per ticker.

### 2. LLM-facing tool results and context

```text
LLM_TOOL_RESULT_MAX_ROWS=200
LLM_TOOL_RESULT_MAX_BYTES=131072
AI_MAX_OUTPUT_TOKENS=3000
AI_MAX_TOOL_RESULT_TOKENS_PER_CALL=4000
AI_MAX_TOOL_RESULT_TOKENS_TOTAL=12000
AI_FINALIZATION_TOOL_RESULT_RESERVE_TOKENS=1000
AI_MAX_HISTORY_TOKENS=4000
AI_MAX_FEATURE_METADATA_TOKENS=5000
AI_CONTEXT_RESERVE_TOKENS=8000
AI_TARGET_CONTEXT_TOKENS=24000
AI_CONTEXT_COMPACTION_THRESHOLD_TOKENS=32000
AI_MAX_CONTEXT_TOKENS=64000
AI_MAX_CUMULATIVE_INPUT_TOKENS=150000
AI_MAX_CUMULATIVE_OUTPUT_TOKENS=12000
AI_FINALIZATION_OUTPUT_RESERVE_TOKENS=4000
AI_CUMULATIVE_COMPACTION_THRESHOLD_PERCENT=75
AI_CONTEXT_COMPACTION_MODE=DISABLED
AI_FINAL_RESPONSE_MAX_RETRIES=2
AI_STORE_REASONING_DETAILS=true
AI_REASONING_RETENTION_DAYS=30
AI_REASONING_MAX_BYTES_PER_CALL=65536
AI_REASONING_CLEANUP_INTERVAL_SECONDS=3600
AI_MAX_TOOL_ITERATIONS=20
AI_MAX_TOOL_CALLS=32
AI_ANALYSIS_MODE=INSIGHT
AI_MIN_INSIGHT_DATA_CALLS=2
AI_MAX_ANALYSIS_SECONDS=600
AI_REQUEST_TIMEOUT_SECONDS=180
```

These values implement two different controls:

- `AI_TARGET_CONTEXT_TOKENS=24000` is the normal active-context target;
- `AI_CONTEXT_COMPACTION_THRESHOLD_TOKENS=32000` triggers compaction before the
  next model call;
- `AI_MAX_CONTEXT_TOKENS=64000` remains the hard per-call operational ceiling,
  intentionally below the model's theoretical maximum;
- cumulative input and output limits bound total usage across all iterations of
  one `Analysis_Request`, even when every individual call remains below 64k.

The 150k cumulative-input ceiling is independent from the 64k per-call context
ceiling. Finalization reserves prevent earlier query/tool chatter from consuming
the budget needed to persist evidence, accept completion, and generate the answer.

`AI_MAX_OUTPUT_TOKENS=3000` is the per-call generation ceiling. It is separate
from the 12,000-token cumulative output ceiling, tool-result limits, and database
row limits.

`AI_ANALYSIS_MODE` is a stopping-depth policy, not a resource ceiling. `QUICK`
may finalize once direct evidence answers the question. `INSIGHT` requires a
distinct, justified interpretation follow-up for data/screening questions before
`complete_analysis` can close the tool loop. `record_evidence` never closes the
loop by itself. The configurable `AI_MIN_INSIGHT_DATA_CALLS` counts distinct
successful analytical query hashes, so retries or duplicate queries do not satisfy
the policy. Optional deeper work remains in `recommended_next_analysis`.

After consolidated evidence is recorded and the minimum query count is met, data
tools are programmatically locked. Only `complete_analysis` remains exposed; after
it succeeds no tools remain. Strict final-output repair is limited to two retries,
and each rejected candidate records the exact schema or contract issue.

`AI_MAX_ANALYSIS_SECONDS` bounds the full orchestration lifecycle independently
of the 180-second timeout for one provider call. The wall-clock gate is checked
before each new model iteration, so a slow provider cannot multiply the 20-iteration
ceiling into an unbounded background analysis.

Normal operation should remain within approximately 24k–32k active tokens. A
request crossing 32k is not automatically terminated: lower-priority material is
compacted first, and necessary follow-up work may continue. The backend must never
send an OpenAI request whose estimated active context exceeds 64k.

Independently, crossing 75% of the cumulative input ceiling triggers one semantic
compaction of superseded intermediate results even if active context remains
below 32k. Per-call records in `Analysis_Model_Call` make cumulative pressure,
active context, and model output separately auditable.

When a result exceeds its model-facing budget, the handler creates a compact
representation with:

- summary statistics;
- top and bottom relevant observations;
- relevant exceptions and warnings;
- processed and returned row counts;
- query hash;
- evidence references;
- pagination/follow-up handle where appropriate.

Arbitrary silent row truncation is forbidden. The orchestrator may issue a
follow-up bounded query. Full `Feature_Catalog` and large history are never
injected automatically: `find_features` runs first, then only relevant definitions
or prior evidence are loaded.

Context compaction is semantic, not simple tail truncation. Once a later step
supersedes an old tool result, the full old payload is removed from active context
and replaced with summary statistics, key observations, unresolved warnings,
query hashes, and evidence IDs. Reproducible detail remains outside model context
through evidence references.

`AI_CONTEXT_COMPACTION_MODE=DISABLED` is an experiment mode that skips only this
cross-iteration compaction. It does not disable per-tool row/byte/token shaping,
which is a mandatory separation between database capacity and LLM context.

The 2026-09-14 ten-question A/B promoted `DISABLED` from experiment to the
current `dev` operational default. Preserve mode remains available but must pass
an explicit output-fidelity regression before it is enabled by default. The
decision and measurements are recorded in `MARKET_AI_AB_TEST_2026-09-14.md`.

Compaction priority is:

1. remove duplicated schemas and metadata already represented by stable IDs;
2. compact superseded raw observations and intermediate rankings;
3. compact older history unrelated to the current hypothesis;
4. retain user intent, current methodology, open warnings, decisive evidence,
   query hashes, and required version metadata;
5. preserve at least `AI_CONTEXT_RESERVE_TOKENS` for reasoning and final output.

Crossing a cumulative limit stops optional deeper exploration first. Necessary
follow-up analysis remains allowed when compaction can keep both the next call and
cumulative usage inside hard limits. If a reliable answer genuinely cannot be
completed within the hard cumulative ceilings, the request returns an explicit
bounded/incomplete result and a `recommended_next_analysis` continuation rather
than fabricating a conclusion.

### 3. Analytics Worker policy

```text
ANALYTICS_MAX_ROWS=50000
ANALYTICS_MAX_COLUMNS=30
ANALYTICS_MAX_INPUT_BYTES=20971520
ANALYTICS_MAX_RUNTIME_SECONDS=120
ANALYTICS_MAX_MEMORY_MB=2048
ANALYTICS_MAX_CONCURRENT_JOBS=1
ANALYTICS_MAX_EVENTS=20000
ANALYTICS_MAX_HORIZONS=4
ANALYTICS_SNAPSHOT_RETENTION_HOURS=24
ANALYTICS_RESULT_RETENTION_DAYS=90
```

The effective limit is the lower of an active tool's catalog ceiling and the
service's Railway configuration. Config/catalog mismatches fail service readiness.

## Analytics Worker Data Handoff

The worker never receives raw or Feature-table credentials.

```text
market-ai-backend
→ controlled Feature query
→ data-quality and size validation
→ immutable bounded snapshot
→ Analytics_Job
→ market-analytics-worker
→ compact analytical result/evidence
```

Snapshot contract:

- storage: private Railway Object Storage bucket dedicated to analytical input;
- object key: `snapshots/{request_id}/{job_id}/{content_sha256}.json.gz`;
- job metadata records request ID, job ID, object key, content SHA-256, schema,
  row count, uncompressed/compressed bytes, created time, and expiry time;
- write-once random job path and checksum verification make the input immutable;
- backend enforces analytics row/column/byte limits before upload;
- worker gets neither bucket credentials nor database credentials. It holds only a
  dedicated backend worker token and receives one short-lived presigned URL for the
  exact leased snapshot;
- worker cannot call interactive query endpoints as a limits bypass;
- object retention is at most 24 hours by default;
- terminal jobs delete input after a short configurable grace period;
- an hourly sweeper deletes expired/orphaned objects;
- compact job/result metadata remains for 90 days by default;
- raw snapshot payload is never sent to OpenAI or stored in evidence rows.

## Generic Tools and Progressive Exposure

### Release 1 active families

- Meta: `list_tools`, `validate_query_request`, `estimate_query_size`.
- Discovery: `find_features`, `get_feature_definition`,
  `list_feature_tables`.
- Quality: `check_data_freshness`, `check_data_quality`.
- Query: `query_features`, `get_timeseries`, `compare_periods`.
- Screening: `screen_features`, `rank_features`, `aggregate_features`,
  `compare_groups`.
- Audit/orchestration: `record_evidence`, `complete_analysis`,
  `get_analysis_history`.

### Release 2 generic analytical surface

The model receives one generic `run_analytics_job` tool rather than one tool per
ticker, signal, question, or statistical method. It describes bounded Feature-only
datasets with structured catalog-validated filters and one analytical `SELECT/WITH`
query over those named snapshots. Database SQL is never model-authored. The isolated
worker executes DuckDB with external access disabled and strict memory, runtime,
input-row/input-byte, output-row/output-byte, and retry limits.

Event study, signal validation, forward-return measurement, streak combinations,
descriptive statistics, correlations, and backtest-like transformations are internal
query/method patterns on this surface. Each predictive/historical use must still
return the universe and availability/no-look-ahead metadata described above. New
methods are added inside the worker policy rather than as a new public tool unless a
materially different authority boundary is required.

At the beginning of every `Analysis_Request`, the orchestrator injects one compact
analytics handoff explaining available capabilities, the query-versus-worker decision,
limits, efficient filtering/column selection, conditional scoped QC, idempotent job
labels, evidence rules, and stopping policy. It is retained as session policy; the
model must not rediscover these rules or dump the catalog on every turn.

### Deferred

- regression;
- clustering;
- HMM;
- PCA;
- specialized methods that cannot yet be expressed safely in bounded DuckDB SQL,
  including production HMM/clustering implementations;
- unrestricted dynamic code execution (the bounded generic SQL sandbox replaces the
  earlier proposal; unrestricted Python remains prohibited);
- Redis/cache layer.

The orchestrator always retains a small meta family. It starts with the smallest
relevant tool set, then may expose additional approved families during the same
request:

```text
discovery
→ screening
→ interesting pattern
→ historical validation
→ advanced method only if active and justified
```

Necessary follow-up analysis runs automatically within limits. Optional deeper
exploration is not automatically executed and is returned under
`recommended_next_analysis`.

## Reproducibility and Audit

Every material claim must have evidence ID and query hash. The completed request
logs, where available:

- cumulative input, output, total, tool-result, metadata, and history tokens;
- one `Analysis_Model_Call` row per provider response, including provider-returned
  reasoning format/retention and concise decision-summary source;
- current and peak active-context tokens plus compaction count;
- tool call and iteration counts;
- provider, model, reasoning effort, OpenAI response ID, and request ID;
- feature/table definition versions;
- tool and analytics methodology versions;
- orchestrator and prompt versions;
- analysis-ready date and timestamp;
- methodology metadata and warnings.

Old completed analyses are read with their stored version snapshot, never silently
rebound to the current Feature or tool version.

## Final Structured Response

Minimum fields:

```text
observation
historical_evidence
interpretation
risks_and_weaknesses
analysis_ready_date
features_used
evidence_ids
methodology_metadata
recommended_next_analysis
```

`recommended_next_analysis` lists useful but nonessential next work such as missing
Feature/data, regime segmentation, benchmark comparison, cross-sector analysis,
historical validation, or a new derived Feature.

## Golden Test Suite

Target final suite: 15–30 versioned tests. It evaluates correctness and method,
not exact wording.

Required categories:

1. basic Feature retrieval;
2. broker accumulation and board-specific ranking;
3. cross-Feature joins without grain duplication;
4. period comparison;
5. readiness/staleness;
6. event study;
7. signal validation;
8. deterministic backtest;
9. query/security rejection;
10. data-quality classification, including extreme-but-valid observations;
11. point-in-time/survivorship warnings;
12. data availability and no-look-ahead checks;
13. version-snapshot reproducibility;
14. token-aware compaction and progressive tool exposure.

Token tests must separately verify the 24k normal target, 32k compaction trigger,
64k per-call hard ceiling, 100k cumulative input ceiling, and 12k cumulative output
ceiling. A multi-iteration test must prove that superseded results are compacted
while a justified follow-up analysis still completes.

Each test stores:

```text
test_id
question
required_capabilities
fixed historical date/range
expected features/tools
expected numerical/result conditions
tolerance
expected warnings
expected status
version
is_active
```

Run the suite before a major release and after material prompt, Feature formula,
tool methodology, or model changes. Infrastructure PASS with a material golden
analytical regression blocks production promotion.

## Staged Rollout and Gates

### Gate 0 — Feature 2: completed

Backfill, reconciliation, validation, catalog activation, index, documentation,
commit, and push have passed.

### Release 1A — Reconcile applied foundation

1. Resolve the duplicate local `009` prefix without modifying any applied
   migration; verify the Feature 3 draft has not reached the live database.
2. Validate live objects created by market-AI migration `009`.
3. Create and apply a new forward-only migration for availability, point-in-time,
   version snapshots, and golden-test tables.
4. Refresh `DATABASE_SCHEMA.md`, `DATABASE_CATALOG.md`,
   `DATABASE_CHANGELOG.md`, `PROJECT_CONTEXT.md`, and Railway documentation.
5. Verify catalog coverage and least-privilege raw-table denial.
6. Run and document controlled Feature 1–2 index-plan acceptance; create an index
   migration only when measured plans show an insufficient access path.
7. Commit and push only after the database gate passes.

### Release 1B — Core private analyst

1. Build `market-ai-backend` with structured request/query builders only.
2. Implement all three independent limit policies and token-aware compaction.
3. Track per-call context separately from cumulative request usage and enforce the
   target, threshold, reserve, and hard ceilings above.
4. Implement progressive tool exposure and structured final responses.
5. Set Railway variables without committing secrets.
6. Deploy private service and confirm exact deployment `SUCCESS`.
7. Run core golden tests for retrieval, readiness, join safety, quality, limits,
   point-in-time warnings, and reproducibility.
8. Do not proceed if analytical or security gates fail.

An OpenAI API credential is required at deployment time. Absence of the secret
blocks deployment, not database/schema work.

### Release 2 — Historical validation analytics

1. Provision private object bucket and scoped credentials.
2. Create `Analytics_Job` and immutable snapshot metadata.
3. Build/deploy separate `market-query-sandbox` and statistical
   `market-analytics-worker` services without raw/Feature credentials.
4. Route every request once from declared operation classes: built-in tools for
   simple operations, query sandbox for custom joins/windows/descriptive work,
   and statistical worker for inferential/predictive validation.
5. Allow only catalog-approved raw/Feature tables in backend-built immutable
   snapshots; never expose unrestricted raw-table SQL or bulk rows to the LLM.
6. Activate analytical methods individually after method-specific acceptance.
7. Expand golden tests to event study, signal validation, forward returns,
   anomaly detection, correlation, and backtest.
8. Require point-in-time disclosure and no-look-ahead PASS for valid predictive
   evidence.

### Release 3 — Telegram

Extend existing `telegram-trigger` with `/analyze <question>` after API stability.
Existing price commands remain unchanged. Use immediate acknowledgement, private
API request ID, signed result callback, and deduplication.

### Release 4 — Feature 3 and Feature 4

For each Feature: create, backfill, validate, catalog, availability/readiness,
relationships, point-in-time metadata, read grant, golden regression, then confirm
generic discovery/query without backend changes.

### Release 5 — Advanced analytics review

Use audit and golden-test evidence to decide whether regression, clustering, HMM,
or PCA should be implemented. They remain inactive until justified.

## Stop/Promotion Conditions

A release is promoted only if:

- migrations are forward-only and catalog-complete;
- service deployment is `SUCCESS`;
- AI roles cannot access raw tables or mutate Feature data;
- config/catalog limit consistency passes;
- representative Feature history and cross-sectional queries pass measured index
  plan acceptance without unjustified full-table scans;
- unsafe/unbounded queries are rejected;
- look-ahead failures cannot become predictive claims;
- survivorship limitations are disclosed;
- version snapshot and evidence are complete;
- required golden tests pass within tolerance;
- Git `main` equals `origin/main`.

Any failed gate is fixed and rerun before advancing. Optional deeper analysis does
not consume resources automatically merely because a tool exists.
