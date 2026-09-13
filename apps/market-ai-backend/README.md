# market-ai-backend

Private asynchronous OpenAI analyst for catalog-registered Feature tables. The
service exposes no public documentation route and accepts analysis calls only
with `Authorization: Bearer $MARKET_AI_INTERNAL_API_KEY`.

## Flow

1. `POST /v1/analyses` stores a durable `Analysis_Request` and returns `202`.
2. The in-service worker leases pending requests with `FOR UPDATE SKIP LOCKED`.
3. The OpenAI Responses orchestrator starts with the smallest relevant tool
   families and can progressively add Query/Screening tools during the same run.
4. Every query is constructed from catalog-approved identifiers and operators;
   model-supplied SQL is never accepted.
5. PostgreSQL estimates and executes within query limits. Tool handlers then
   rank, aggregate, or semantically compact results to the independent LLM-facing
   row/byte/token budgets.
6. Every tool call, query hash, evidence item, warning, context peak, compaction,
   and cumulative token count is audited.
7. A successful response stores an immutable version/methodology snapshot and a
   structured `recommended_next_analysis` list.

OpenAI calls use the official HTTPS Responses endpoint with `store=false`, strict
function schemas, strict structured output, one tool call at a time, and explicit
usage accounting. This small transport avoids a Windows Application Control issue
that blocked the Python SDK's native `jiter` module during local verification;
the API contract and provider remain OpenAI.

Release 1B can read Feature 1–3 through a least-privilege login. It cannot read
raw price/broker tables or mutate Feature tables. Historical validation and
advanced analytics remain inactive until the Release 2 bounded-snapshot worker
exists.

## Required secrets

- `DATABASE_URL`: private DSN for `market_ai_app`, never the PostgreSQL owner.
- `OPENAI_API_KEY`: OpenAI credential.
- `MARKET_AI_INTERNAL_API_KEY`: bearer credential for private callers.

All numeric variables and their approved defaults are listed in
`AI_ANALYST_IMPLEMENTATION_PLAN.md`; Railway variables are the enforcement source
and `Tool_Catalog` is the model-facing metadata copy.

## Smoke test and provider errors

Run `scripts/smoke_market_ai_analysis.py` with `APP_DATABASE_URL` set to the
least-privilege public-proxy DSN. The script inserts one bounded durable request
and waits for its terminal status; it does not bypass the normal Railway worker.

The OpenAI transport records only safe diagnostics: HTTP status, error type/code,
message, and request ID. `insufficient_quota` or `credit_balance_exhausted` is not
retried because it requires a billing-credit change. Transient 408, 409, 429, and
5xx responses keep the bounded retry path. Never log the API key, request headers,
or decrypted Railway variables.
