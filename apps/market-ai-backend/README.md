# market-ai-backend

Private asynchronous LLM analyst for catalog-registered Feature tables. The
service exposes no public documentation route and accepts analysis calls only
with `Authorization: Bearer $MARKET_AI_INTERNAL_API_KEY`.

## Flow

1. `POST /v1/analyses` stores a durable `Analysis_Request` and returns `202`.
2. The in-service worker leases pending requests with `FOR UPDATE SKIP LOCKED`.
3. The Responses orchestrator starts with the smallest relevant tool
   families and can progressively add Query/Screening tools during the same run.
   A direct ticker retrieval starts without Screening schemas; explicit screening
   or ranking language exposes Screening immediately.
4. Every query is constructed from catalog-approved identifiers and operators;
   model-supplied SQL is never accepted. Before data execution, the orchestrator
   automatically loads compact semantics for only the referenced output, filter,
   order, group, metric, and condition columns. `get_feature_definition` remains
   available on demand for complete formula/methodology detail; forgetting that
   separate call no longer wastes a model retry.
5. PostgreSQL estimates and executes within query limits. Tool handlers then
   rank, aggregate, or semantically compact results to the independent LLM-facing
   row/byte/token budgets.
6. Every model response receives one `Analysis_Model_Call` row; every tool call,
   query hash, evidence item, warning, context peak, compaction, and cumulative
   token count is also audited at its appropriate grain.
7. `record_evidence` stores a decisive result without ending the investigation.
   `complete_analysis` applies the stopping checklist: evidence must exist,
   necessary follow-ups must be complete, and `INSIGHT` mode requires the
   configured minimum number of distinct successful analytical queries for data
   or screening questions. Only then does the following call remove data-tool
   schemas and perform strict finalization. A malformed or premature call returns
   recoverable feedback within the same bounded analysis budget.
8. A successful response stores an immutable version/methodology snapshot and a
   structured `recommended_next_analysis` list.

`find_condition_runs` is the first generic sequence screener. It accepts one or
more catalog-approved conditions with AND semantics and returns only qualifying
episodes. Consecutive means consecutive observations for that ticker in the
Feature table, not consecutive calendar days; a NULL condition breaks the run.
Exact matching dates are optional so long searches remain compact. The backend
enforces `CONDITION_RUNS_MAX_DATE_RANGE_DAYS`,
`CONDITION_RUNS_MAX_EPISODES`, ticker, estimated-row, timeout, byte, and
LLM-facing limits independently.

Provider calls use an allowlisted HTTPS Responses endpoint with `store=false`,
strict function schemas, strict structured output, one tool call at a time, and
explicit usage accounting. `AI_PROVIDER=openai` targets the OpenAI endpoint;
`AI_PROVIDER=openrouter` targets OpenRouter and currently defaults to
`deepseek/deepseek-v4.1-flash`. Arbitrary base URLs and silent cross-provider
fallback are not allowed.

If a provider nevertheless returns truncated or malformed tool-argument JSON,
the backend stores only its length/hash in the failed step audit and returns a
recoverable instruction to resend one complete schema-valid call. Partial raw
arguments are not copied to logs, and a single formatting deviation no longer
terminates the durable analysis immediately.

Provider-returned reasoning is stored only when actually supplied, capped by
`AI_REASONING_MAX_BYTES_PER_CALL`, and cleared after
`AI_REASONING_RETENTION_DAYS`. The worker runs an idempotent bounded cleanup on
`AI_REASONING_CLEANUP_INTERVAL_SECONDS`; per-call usage and the concise
`decision_summary` remain. The backend never reconstructs hidden reasoning or
copies prompts/tool-result payloads into the reasoning audit.

`check_data_quality` is conditional across all tool paths. The model should call
it only for a scoped coverage, NULL/gap, freshness, cross-feature, anomaly, or
material-conclusion concern. `WARNING` and source-valid anomalies continue;
only impossible/invalid `FAIL` blocks the affected conclusion.

Release 1B can read Feature 1–3 through a least-privilege login. It cannot read
raw price/broker tables or mutate Feature tables. Historical validation and
advanced analytics remain inactive until the Release 2 bounded-snapshot worker
exists.

Raw-table denial does not mean market-source values must always be hidden from
the analyst. Feature 01 already exposes cataloged `close` and `volume` source
values alongside derived features. If additional raw OHLCV fields are approved,
expose them through a dedicated cataloged read-only market-data view/tool with
the same structured query limits; do not grant the model or application role
unrestricted raw-table credentials. This preserves source-level validation while
keeping internal ingestion fields and unrelated raw tables outside the surface.

## Required secrets

- `DATABASE_URL`: private DSN for `market_ai_app`, never the PostgreSQL owner.
- `OPENAI_API_KEY`: required only when `AI_PROVIDER=openai`.
- `OPENROUTER_DEEPSEEK`: required only when `AI_PROVIDER=openrouter`.
- `MARKET_AI_INTERNAL_API_KEY`: bearer credential for private callers.

`AI_MODEL`, `AI_REASONING_EFFORT`, and `AI_MAX_FEATURE_METADATA_TOKENS` are
configured separately. The current `dev` profile uses DeepSeek V4.1 Flash,
reasoning `high`, and a 5,000-token cumulative Feature-definition budget. This
supports larger relevant definition sets but is intentionally not permission to
inject all 91 catalog rows into every request.

`AI_ANALYSIS_MODE` controls answer depth independently of the circuit breakers.
`QUICK` may finalize after sufficient direct evidence. `INSIGHT` performs a
distinct, justified interpretation follow-up before finalization for data and
screening questions. `AI_MIN_INSIGHT_DATA_CALLS` defaults to `2`; repeated copies
of the same query hash do not satisfy it. Remaining optional work is reported in
`recommended_next_analysis`, not executed solely because calls remain.
Decisive observations should normally be consolidated into one evidence item
after the required follow-up, reducing repeated model calls without weakening the
query-hash audit trail.

`AI_MAX_ANALYSIS_SECONDS` is the separate whole-analysis wall-clock circuit
breaker and defaults to 600 seconds. `AI_REQUEST_TIMEOUT_SECONDS` remains the
per-provider-call timeout; tool-call, iteration, token, and wall-clock limits are
independent safeguards.

All numeric variables and their approved defaults are listed in
`AI_ANALYST_IMPLEMENTATION_PLAN.md`; Railway variables are the enforcement source
and `Tool_Catalog` is the model-facing metadata copy.

## Smoke tests and provider errors

Run `scripts/smoke_market_ai_analysis.py` with `APP_DATABASE_URL` set to the
least-privilege application DSN. For local execution, also set
`POSTGRES_PUBLIC_URL`; the helper substitutes only its public host/port while
retaining the application user/password/database. The script inserts one bounded
durable request and waits for its terminal status; it does not bypass the normal
Railway worker.

The provider transport records only safe diagnostics: HTTP status, error type/code,
message, and request ID. `insufficient_quota` or `credit_balance_exhausted` is not
retried because it requires a billing-credit change. Transient 408, 409, 429, and
5xx responses keep the bounded retry path. Never log the API key, request headers,
or decrypted Railway variables.

Run `scripts/smoke_responses_provider.py` before a provider/model switch. It makes
one bounded strict-output request, reports only safe IDs and usage totals, and
never prints the credential.
