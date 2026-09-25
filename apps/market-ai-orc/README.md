# market-ai-orc

AI orchestration service. It receives an AI request from a trusted backend, calls
OpenRouter, runs registered tools when the model asks for them, and returns a validated
structured response. Phase 2 added read-only **catalog discovery** over Saniti's five
`AI_*` metadata tables. Phase 3 adds **full catalog access** (every catalog row, paginated)
and a fixed **20-row market-data preview** of seven approved tables. The SQL Governor milestone
adds **`request_data`**. It forwards a structured Data Request Spec to the separate
`market-sql-governor` service, which is the only component that compiles and runs market-data
SQL (see [`../market-sql-governor/README.md`](../market-sql-governor/README.md)).

It was derived from `apps/market-ai-backend`. It keeps that service's proven OpenRouter
Responses transport, bounded retry, quota handling, usage accounting, strict final-schema
validation with bounded retries, and bounded agent loop. It removes everything tied to
market data: PostgreSQL, catalogs, SQL governance, query sandbox, statistical worker,
S3 snapshots, evidence and completion gates, and analysis routing.

`market-ai-orc` has **no market-data query access and no bucket credentials**. Its only
database access is optional and read-only: the `market_ai_orc` login can SELECT exactly the
five `AI_*` catalog tables (see [Catalog discovery](#catalog-discovery)) and EXECUTE one
database function that returns at most 20 example rows from one of seven approved tables
(see [Market-data preview](#market-data-preview)). It has no SELECT privilege on any
market-data table. `request_data` reaches market data only through the Governor's HTTP API
(`SQL_GOVERNOR_URL` and `SQL_GOVERNOR_API_KEY`); this service holds no Governor database
credential and no SQL logic. It is stateless: the caller owns conversation persistence.

## Architecture

Current (Phase 3):

```text
Backend
   ↓  POST /v1/agent/run  (Bearer MARKET_AI_ORC_API_KEY)
market-ai-orc
   ↓  POST https://openrouter.ai/api/v1/responses
OpenRouter → AI model
   ↓  optional function_call
market-ai-orc executes a registered tool → function_call_output
   │    discover_catalog / get_catalog_details → targeted, visibility-filtered catalog metadata
   │    read_catalog_rows → complete AI_* catalog rows, keyset-paginated
   │    preview_table_rows → public.ai_preview_table_rows(): ≤ 20 fixed-order example rows
   │    request_data → market-sql-governor POST /v1/query → DATASET_READY (reference, never rows) |
   │                   NEEDS_NARROWING | REJECTED (with next_action)
   │    lookup_fact → market-sql-governor POST /v1/lookup → FACTS_READY (≤ 20 facts with fact_id) |
   │                   REJECTED (USE_ANALYSIS_PATH for statistics, rankings, or larger requests)
   ↓  (repeat within limits)
strict final response
   ↓  validation gate (code): failed analyses, routing guard, number provenance, evidence_label
Backend
```

Python analysis (when the sandbox is configured) adds a validation path:
`create_analysis_spec` → `request_data` → `run_python_analysis` → `get_analysis_result`, and a
backend validation gate on the final response (see [Python analysis](#python-analysis)). When the
analysis tools are not registered, `python_analysis` is `false` and the model must not claim an
analysis ran.

## Request flow

1. The backend calls `POST /v1/agent/run` with the internal bearer key.
2. The request is validated. Callers cannot send a system prompt, extra fields, or history
   roles other than `user`/`assistant`.
3. The model input is built from the fixed system prompt, the latest history turns that fit
   `AI_MAX_HISTORY_TOKENS` (passed as one context-only item), and the latest message.
4. OpenRouter is called with `store: false` and `provider.require_parameters: true`. There
   are two kinds of turn:
   - **Tool turns** (at least one tool registered and available) send the tools with
     `tool_choice: auto` and **no** `text.format`.
   - **Structured turns** (no tools available, finalization, or format repair) send strict
     `text.format` (`json_schema`, `saniti_agent_response`) and no tools.
5. Each requested tool call is checked, validated, and run sequentially. The
   `function_call` and its `function_call_output` are appended, then OpenRouter is called
   again. Provider reasoning items are never replayed into later calls.
6. When a tool turn ends in text, it is accepted if it is already valid schema JSON.
   Otherwise, one structured finalization turn converts the draft, and the response
   contract is spelled out for the model. This does not count as a retry. An invalid
   structured output gets a short correction and retries, up to
   `AI_FINAL_RESPONSE_MAX_RETRIES` times.
7. Code, not the model, wraps the answer in the API envelope with status, usage, and timing.

### Context budget

Before every model call the context is estimated: system prompt, input items including all
prior tool outputs, tool definitions, and schema. `AI_MAX_OUTPUT_TOKENS` is added to the
estimate.

- **Soft limit.** A tool turn would reach `AI_MAX_CONTEXT_TOKENS × AI_CONTEXT_SOFT_LIMIT_RATIO`
  (64000 × 0.8 = 51200 by default). The run then degrades instead of failing:
  - Tools are withdrawn through the same mechanism as the `AI_MAX_TOOL_CALLS` budget.
  - A finalization instruction is added, telling the model that tool access ended at the
    context budget.
  - The model must answer only from what was already retrieved. It returns `LIMITATION`,
    or an `ANSWER` whose `limitations` say what was read and what remains unread.
  - An `ANSWER` without limitations, or a `CLARIFICATION`, is rejected and retried.
  - `execution.tools_withdrawn_reason` is `CONTEXT_BUDGET`. It is `TOOL_CALL_BUDGET` when the
    tool-call budget ended tool use.
  - Prior tool outputs are never dropped, summarized, or truncated.
- **Iteration cap (not degraded yet).** `AI_MAX_TOOL_ITERATIONS` (default 8) still ends a run
  with `MAX_ITERATIONS` when every call requests another tool. With 16 KB pages, each page adds
  about 5k provider tokens, so a page-by-page read of a large catalog reaches 8 iterations
  (about 37k tokens) before the 51.2k soft limit. Verified live on 2026-09-23 with
  `AI_calculation_catalog`. Railway `dev` therefore sets `AI_MAX_TOOL_ITERATIONS=20`. With the
  default `AI_MAX_TOOL_CALLS=12`, the tool-call budget or the context soft limit, both graceful,
  now ends such runs first.
- **Hard limit.** When even the tool-free finalization turn would exceed
  `AI_MAX_CONTEXT_TOKENS`, for example with oversized history or one very large tool
  output, the run fails with `CONTEXT_LIMIT`. The same happens when provider-reported input
  exceeds the ceiling.

### Why tool turns carry no `text.format`, and there is no `parallel_tool_calls`

Both were verified live against OpenRouter with `deepseek/deepseek-v4.1-flash` on 2026-09-22:

- OpenRouter providers enforce `text.format: json_schema` by constraining the whole
  generation. With tools and a strict format in the same turn, the model never called a
  tool; it answered "Let me check…" as schema JSON (3/3 trials). Without the format, it
  called the tool 3/3 times.
- None of the 23 OpenRouter endpoints for this model supports `parallel_tool_calls`.
  With `require_parameters: true`, sending the field, even as `false`, leaves no eligible
  endpoint (HTTP 404). Sequential execution is enforced in code instead.

Loop protection is enforced in code: iterations, total tool calls, identical repeated calls,
wall-clock time, output tokens, and a context ceiling checked before each provider call.

### Prompt caching and model usage

DeepSeek caches prompts implicitly on the provider side (OpenRouter bills a cache read at 0.1x the input
price). This service keeps no prompt cache of its own. It only shapes the requests so the provider can
reuse the prefix of one run's calls:

- **One session per run.** Every model call of a run sends `session_id` = the run's `request_id` in the
  Responses body. OpenRouter uses it as the sticky-routing key, so the calls of a run go to the same
  provider endpoint. A new request is a new session.
- **Stable prefix.** `instructions` is the constant `SYSTEM_PROMPT` (it holds no time, id, or count).
  Tools are sent in registration order with schemas built once at registration. The conversation only
  grows at the end: earlier items are never rewritten, and dynamic notes (a gate's rejection, the
  context-budget instruction) are appended after them. The prefix legitimately changes when tools are
  withdrawn or the final turn switches to the strict JSON format.
- **Final re-ask on the same prefix.** When the model drafts prose on a tool turn, the first request
  for the final JSON response is sent exactly like a tool turn: same tools and `tool_choice`, no
  `text.format`. `FINALIZE_INSTRUCTION` carries the JSON contract, and the answer is still parsed and
  validated strictly. The tools are sent but not offered, so a tool call in that turn is refused
  (`TOOLS_NOT_AVAILABLE`). Only when that answer is still invalid, or when the model calls a tool
  there, does the next turn drop the tools and enforce the strict schema. A gate rejection reopens
  the tools for the repair.

  The reason: with `provider.require_parameters`, a strict-format turn can only run on endpoints that
  support structured outputs. As of 2026-09-24, Relace, the endpoint OpenRouter chose for this model's
  tool turns, advertises `tools` but not `response_format` or `structured_outputs`, so that turn had to
  move to another provider without the run's cache. Keeping the tools while sending `tool_choice: "none"`
  did not help: the tool definitions were dropped from the prompt, and the turn still moved provider.
- **Usage per call** (`ai_model_call` log event): `session_id`, `iteration`, the `model` and `provider`
  that served it, `latency_ms`, and `static_prefix_sha256`, a fingerprint of everything sent except
  `input`. The usage fields are:
  - `input_tokens` (all prompt tokens);
  - `cached_input_tokens` and `cache_write_tokens`, from `usage.input_tokens_details`, with
    `prompt_tokens_details` as the fallback;
  - `fresh_input_tokens` (`input_tokens - cached_input_tokens`);
  - `cache_metrics_reported` (false when the response carried no cache fields, so a missing report is
    not read as zero);
  - `output_tokens` and `reasoning_tokens`;
  - `cost`, OpenRouter's `usage.cost` for the call, or null when none was reported.
- **Run summary** (`ai_model_usage_summary` log event): the totals above, `cache_ratio` =
  cached / prompt tokens (null without prompt tokens), total `cost` (null when no call reported one),
  `average_latency_ms`, and `distinct_static_prefixes`. `execution.cached_input_tokens`,
  `execution.cache_write_tokens`, and `execution.cost` carry the same totals in the response.
- **Serving provider.** The Responses body has no `provider` field. `ai_model_call` logs
  `provider_response_id`, and `GET https://openrouter.ai/api/v1/generation?id=<it>` returns
  `provider_name`, `session_id`, and `native_tokens_cached` for that call.

Measured on `dev` (2026-09-24, see `RAILWAY_CHANGELOG.md`):
- A z-score run made 8 calls, and calls 1–7 stayed on one provider with a byte-identical static prefix.
  The cache ratio was 0.70 (92,416 of 132,042 prompt tokens), at $0.0065 for the run.
- The same prompt without `session_id` already stayed sticky through OpenRouter's conversation hash
  (ratio 0.75), so `session_id` did not measurably change the ratio in that comparison.
- The remaining miss was the structured-final turn, when the model drafted prose on a tool turn. That
  turn withdrew tools and added the strict JSON format, which changed the prefix and moved the call to
  another provider (Relace to DekaLLM).
- The final re-ask above fixes this. In a probe of 5 runs with the production prefix, the re-ask stayed
  on Relace with 9,728 of about 10,400 prompt tokens cached. It returned a valid final JSON and no tool
  call every time. The strict-format turn moved to another provider every time, in 6 of 6 trials.

## Environment variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `MARKET_AI_ORC_API_KEY` | yes (secret) | — | Bearer key the backend must send |
| `OPENROUTER_API_KEY` | yes (secret) | — | OpenRouter API key |
| `AI_MODEL` | no | `deepseek/deepseek-v4.1-flash` | OpenRouter model ID |
| `AI_REASONING_EFFORT` | no | `high` | One of `minimal`, `low`, `medium`, `high`, `xhigh`, `max`; the model must support it (`require_parameters` rejects it otherwise) |
| `AI_REQUEST_TIMEOUT_SECONDS` | no | `180` | Timeout for one provider call |
| `AI_MAX_OUTPUT_TOKENS` | no | `3000` | `max_output_tokens` per call |
| `AI_MAX_TOOL_ITERATIONS` | no | `8` | Maximum model calls per run |
| `AI_MAX_TOOL_CALLS` | no | `12` | Maximum tool calls per run; after that, tools are withdrawn |
| `AI_MAX_IDENTICAL_TOOL_CALLS` | no | `2` | Executions allowed for the same tool and arguments while the result is unchanged |
| `AI_MAX_REPAIR_ATTEMPTS` | no | `3` | Repairs allowed per run for the same tool rejection (tool + reason code) before `REPAIR_BUDGET_EXHAUSTED` |
| `AI_ENABLE_LOOKUP_FACT` | no | `true` | Register the model-facing `lookup_fact` tool and its prompt rule |
| `AI_ENABLE_REQUEST_DATA` | no | `false` | Register the model-written `request_data` tool (rollback path; analysis data is prepared by `prepare_analysis_data`) |
| `AI_MAX_ANALYSIS_SECONDS` | no | `600` | Wall-clock limit per run |
| `AI_MAX_CONTEXT_TOKENS` | no | `64000` | Hard context ceiling (estimated before the call, provider-reported after) |
| `AI_CONTEXT_SOFT_LIMIT_RATIO` | no | `0.8` | 0.5–0.95. At `AI_MAX_CONTEXT_TOKENS ×` this ratio, tools are withdrawn and the run finalizes from what was already retrieved (see [Context budget](#context-budget)). `AI_MAX_OUTPUT_TOKENS` must stay below this soft limit |
| `AI_MAX_HISTORY_TOKENS` | no | `4000` | Budget for supplied history; the newest whole turns are kept |
| `AI_FINAL_RESPONSE_MAX_RETRIES` | no | `2` | Retries after an invalid final response (`0` allowed) |
| `OPENROUTER_HTTP_REFERER` | no | unset | Optional `HTTP-Referer` header |
| `OPENROUTER_X_TITLE` | no | `Saniti Market AI` | `X-Title` header |
| `CATALOG_DATABASE_URL` | no (secret) | unset | DSN for the catalog-only `market_ai_orc` login. When unset, the catalog tools are not registered |
| `CATALOG_CONNECT_TIMEOUT_SECONDS` | no | `5` | Catalog connection timeout (≤ 30) |
| `CATALOG_STATEMENT_TIMEOUT_MS` | no | `5000` | Per-statement timeout for catalog queries (100–30000) |
| `CATALOG_PAGE_SIZE_DEFAULT` | no | `100` | `read_catalog_rows` page size when the model passes `null` (≤ `CATALOG_PAGE_SIZE_MAX`) |
| `CATALOG_PAGE_SIZE_MAX` | no | `200` | Largest `page_size` the model may request (≤ 1000) |
| `CATALOG_PAGE_MAX_BYTES` | no | `16000` | Serialized row budget per catalog page (4096–131072); a page ends early rather than exceeding it |
| `SQL_GOVERNOR_URL` | no | unset | market-sql-governor base URL (private network). When unset, `request_data` is not registered |
| `SQL_GOVERNOR_API_KEY` | with URL (secret, ≥ 32 chars) | — | Bearer key for the Governor; reference `${{market-sql-governor.SQL_GOVERNOR_API_KEY}}` |
| `SQL_GOVERNOR_TIMEOUT_SECONDS` | no | `90` | HTTP timeout for one Governor call (≤ 300); the tool timeout is this plus 5 s |
| `REQUEST_DATA_MAX_RESULT_BYTES` | no | `40000` | Hard cap on one `request_data` or `lookup_fact` result sent to the model (8192–131072) |
| `MARKET_DATA_PREVIEW_ENABLED` | no | `true` | `false` unregisters `preview_table_rows` without touching the catalog tools |
| `PY_SANDBOX_URL` | no | unset | market-python-sandbox base URL (private network). `run_python_analysis` and `get_analysis_result` are registered only when this is set **and** the sandbox reports `/ready` at startup (3 attempts, 2 s apart) |
| `PY_SANDBOX_API_KEY` | with URL (secret, ≥ 32 chars) | — | Bearer key for the sandbox; reference `${{market-python-sandbox.PY_SANDBOX_API_KEY}}` |
| `PY_SANDBOX_REQUEST_TIMEOUT_SECONDS` | no | `45` | HTTP timeout for one sandbox call (10–300); the tool timeout is this plus 5 s. Keep it above the sandbox's submit wait |
| `PY_SANDBOX_POLL_WAIT_SECONDS` | no | `20` | How long `get_analysis_result` waits for a running analysis (≤ 60, at least 10 s below the request timeout) |
| `PYTHON_ANALYSIS_MAX_RESULT_BYTES` | no | `40000` | Hard cap on one analysis tool result sent to the model (8192–131072) |
| `RESEARCH_AUDIT_DATABASE_URL` | no (secret) | unset | DSN of a login holding `market_ai_research_audit_writer` (INSERT only on `AI_research_run_audit`). When unset, the per-run PostgreSQL audit copy is disabled; the report still goes to the sandbox (see [Research run audit](#research-run-audit)) |
| `ANALYSIS_TIMEZONE` | no | `Asia/Jakarta` | IANA time zone of the analysis reference date (the request date in this zone anchors "last 3 months", "latest", and similar periods); invalid zones stop startup |

Secrets have no defaults, and the service refuses to start without them. It never logs API
keys, `Authorization` headers, prompts, user messages, or provider reasoning.

## API contract

### `GET /health`
Returns `{"status": "ok"}` while the process is alive.

### `GET /ready`
Returns `{"status": "ready"}` once configuration has loaded and the app has started. It does
**not** call OpenRouter.

### `POST /v1/agent/run`
Header: `Authorization: Bearer ${MARKET_AI_ORC_API_KEY}`. Missing or wrong key → `401`.

Request:

```json
{
  "request_id": "abc123",
  "conversation_id": null,
  "message": "What capabilities do you currently have?",
  "history": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}],
  "metadata": {}
}
```

- `request_id` (1–200 characters) and `message` (1–16,000 characters, not blank) are required.
- `history` is optional, with at most 50 turns. Roles other than `user`/`assistant` are rejected (`422`).
- `metadata` is optional, at most 8 KB of JSON. It is not sent to the model.
- Unknown fields, including any attempt to pass `instructions` or a system prompt, are rejected (`422`).

Response (HTTP `200` for every agent outcome, including `FAILED`):

```json
{
  "request_id": "abc123",
  "status": "COMPLETED",
  "response": {
    "response_type": "ANSWER",
    "answer": "...",
    "clarification_question": null,
    "assumptions": [],
    "limitations": []
  },
  "execution": {
    "provider": "openrouter",
    "model": "deepseek/deepseek-v4.1-flash",
    "provider_response_id": "gen-...",
    "iterations": 2,
    "tool_call_count": 1,
    "input_tokens": 0,
    "output_tokens": 0,
    "reasoning_tokens": 0,
    "total_tokens": 0,
    "cached_input_tokens": 0,
    "cache_write_tokens": 0,
    "cost": null,
    "duration_ms": 0,
    "tools_withdrawn_reason": null,
    "analyses": [],
    "validation_gate": "NOT_APPLICABLE",
    "number_provenance": {"checked": 0, "unsupported": []},
    "research": null
  },
  "error": null,
  "evidence_label": null
}
```

`execution.analyses` lists every Python analysis of the run with `analysis_id`, `spec_id`,
`execution_status`, `validation_status`, `validation_level`, and `reason_codes`, taken from the
sandbox records, not from the model. `execution.validation_gate` is `NOT_APPLICABLE` (no
analysis), `PASSED`, `ANNOTATED` (mandatory validation limitations were appended), or
`FORCED_LIMITATION` (the gate converted the response to `LIMITATION`).
`execution.number_provenance` counts the numbers checked in the answer and lists those without a
governed source (null when the gate did not check numbers, for example on a clarification).
`execution.research.experiments` lists every analysis spec of the run (null when none was created)
with its `evidence_standard` (`CALCULATION` when the spec has no research block), `hypothesis_id`,
`followup_of`, the Research Governor's `governor_decision`, the latest analysis and its validation,
the `evidence_decision`/`evidence_level` of its evidence assessment, and `retained`: `RETAINED`
(the answer cites numbers of that analysis), `DISCARDED` (it ran, but the answer does not rely
on it), `FOLLOWED_UP` (a later experiment followed it up and the answer does not cite it), or
`NOT_RUN`. `retained` is derived by code from number provenance, never stated by the model.

`evidence_label` is set by code, never by the model, for a frontend badge:

| `evidence_label` | Shown as | When |
|---|---|---|
| `FACT` | Fakta | every data number comes from `lookup_fact` mode `VALUE` |
| `DATABASE_AGGREGATE` | Agregat database | a data number comes from `lookup_fact` mode `AGGREGATE` |
| `CALCULATION_VERIFIED` | Terverifikasi (dihitung ulang dan cocok) | an analysis with validation `PASS` and level `CALCULATION_VERIFIED` |
| `SCOPE_VERIFIED` | Cakupan terverifikasi | `PASS` at `SCOPE_VERIFIED` (for example a custom method; values not recalculated) |
| `UNVERIFIED_EXPLORATORY` | Belum terverifikasi (eksploratif) | an analysis with validation `UNVERIFIED` |
| `NOT_VALIDATED` | Tidak tervalidasi | `INCOMPLETE`/`FAILED`, or numbers without a source; the response is `LIMITATION` |

A mixed answer carries its weakest label (the order above is strongest to weakest). Each number is
attributed to the strongest source it matches; user, spec, and manifest numbers are context and
do not set a label. An answer without data numbers gets the weakest label of the evidence the run
consulted (analyses and facts), or `null` when it consulted none, as for clarifications and
capability questions. "Terverifikasi" means recalculated independently and matching, not
"certainly correct"; approved defaults and exploratory derived features stay in
`assumptions`/`limitations`.

The model produces only `response`. Code sets `status` from `response_type`:
`ANSWER → COMPLETED`, `CLARIFICATION → NEEDS_CLARIFICATION`, `LIMITATION → LIMITED`.
On failure, `status` is `FAILED`, `response` is `null`, and `error` is `{code, message}`.
The error codes are:

`PROVIDER_TIMEOUT`, `PROVIDER_NETWORK_ERROR`, `PROVIDER_UNAVAILABLE`, `PROVIDER_REJECTED`,
`PROVIDER_QUOTA_EXHAUSTED`, `PROVIDER_MALFORMED_RESPONSE`, `PROVIDER_PROTOCOL_ERROR`,
`MAX_ITERATIONS`, `ANALYSIS_TIMEOUT`, `CONTEXT_LIMIT`, `INVALID_FINAL_RESPONSE`,
`INTERNAL_ERROR`.

Final-response rules: `CLARIFICATION` needs a non-empty `clarification_question`. The other
types need it to be `null`. `ANSWER` needs a non-empty `answer`, and `LIMITATION` needs at
least one limitation. No extra fields are allowed.

Provider retries: `408`, `409`, `429` (except `credit_balance_exhausted` and
`insufficient_quota`), `5xx`, timeouts, and network errors are retried up to 3 attempts with
backoff. Quota or billing failures and other `4xx` errors are not retried. A `2xx` response
with malformed JSON is not retried, because tokens were already consumed.

## Tool registration pattern

Tools live in `app/tools/` and are registered in one place, `build_default_registry()` in
`app/tools/__init__.py`. Adding a tool never changes the orchestration loop.

```python
class LookupArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")   # required, also on every nested model
    dataset: str                                 # every field required; use `X | None` for optional
    ticker: str | None

registry.register(ToolSpec(
    name="lookup",
    description="...",
    arguments_model=LookupArguments,             # validates arguments AND generates the strict schema
    handler=lambda args: {...},                  # returns a JSON object
    timeout_seconds=10,
    max_result_bytes=None,                       # optional per-tool cap; default is the registry's 32 KB
))
```

Guarantees:

- Only registered, enabled handlers run. Unknown tools fail closed with `UNKNOWN_TOOL`.
- Arguments are parsed as JSON and validated by the same Pydantic model that generates the
  strict provider schema. Invalid input returns `INVALID_ARGUMENTS` to the model.
- Handler errors return `TOOL_ERROR` (a `ToolError` message) or `TOOL_FAILED` (internal
  detail hidden). Timeouts return `TOOL_TIMEOUT`. Oversized results return
  `TOOL_RESULT_TOO_LARGE` rather than being silently truncated.
- Results are normalized to `{"ok": true, "tool": ..., "result": {...}}` or
  `{"ok": false, "tool": ..., "error": {"code", "message"}}`, and are always linked to
  their `call_id`.
- Registration rejects invalid names, duplicates, models without `extra="forbid"`, and fields
  with defaults, at every nesting level.
- Nested models are allowed (for `request_data`). They are inlined into the provider schema
  (no `$ref`/`$defs`). The provider receives only keywords already verified live with
  OpenRouter strict tools: `type`, `properties`, `required`, `additionalProperties`, `items`,
  `anyOf`, `enum`, and `description`. Patterns, lengths, and ranges are still enforced by the
  Pydantic model on every call.
- The agent run's `request_id` is carried into handler threads through a context variable, so
  Governor logs join to the run.

## Currently available tools

| Tool | Arguments | Result |
|---|---|---|
| `get_system_capabilities` | none | Capability flags plus `available_tools`, for example `{"catalog_discovery": true, "database_query": false, "python_analysis": false, "web_search": false, "external_data": false, "available_tools": [...]}` |
| `discover_catalog` | none | AI-visible tables with their catalog metadata (see below) |
| `get_catalog_details` | `table_names`, `sections`, `column_names`, `entity_ids` | Requested catalog sections (see below) |
| `read_catalog_rows` | `catalog_name`, `page_size`, `cursor` | One page of complete catalog rows (see [Full catalog access](#full-catalog-access)) |
| `preview_table_rows` | `table_name` | At most 20 example rows (see [Market-data preview](#market-data-preview)) |
| `request_data` | `purpose`, `from_table`, `columns`, `joins`, `filters`, `group_by`, `aggregations`, `order_by`, `requested_limit` | The SQL Governor decision: always a dataset reference when approved, never rows (see [Data requests](#data-requests)) |
| `lookup_fact` | `purpose`, `mode` (`VALUE`/`AGGREGATE`), `table`, `entities` (1–5), `dates` (≤ 10) or `date_range`, `columns` (1–4) or `aggregations` (1–4 of SUM/AVG/MIN/MAX/COUNT) with `per_entity` | At most 20 facts, each with `fact_id`, table, column, entity, date or scope, and value |
| `get_dataset_manifest` | `dataset_id` | The Governor's bounded dataset manifest: `AVAILABLE`, or explicit `DATASET_EXPIRED` / `DATASET_NOT_FOUND` (see [Python analysis](#python-analysis)) |
| `get_dimension_values` | `table`, `column`, `match` (optional substring) | The canonical values (at most 200, no counts) of one groupable text column of an approved static table, for writing exact scope predicates and segments |
| `create_analysis_spec` | Analysis Spec V2: `spec_version`, `analysis_type`, `question`, `subject`, `inputs` (with roles), `relationships`, `scope`, `time_scope` (null for static data), `calculations` (optionally `signal`, `expression`, `formula_refs`, `meaning`, `unit`, `data_policies`, `group_by` or `segments`), `outputs` (with `key_columns`, `ranking`), `exclusion_rules`, each requirement with its provenance, and `research` for RESEARCH | The spec review: `status`, `spec_id` when approved, `validation_profile`, `scope_sha256`, `resolved_period`, `required_input` (with warm-up), `data_plan` summary, `output_contract`, mismatches, unverified requirements, clarification needed, `convention_notes`, the Research Governor decision (`governor`), and `replayed` for an idempotent resubmission |
| `prepare_analysis_data` | `spec_id` | `READY` with `input_bundle_id` and per-input row counts and completeness, or a structured rejection |
| `run_python_analysis` | `spec_id`, `input_bundle_id`, `python_code` (≤ 20000), `expected_outputs` ⊆ {TABLE, METRICS, CHART, ARTIFACT} | The analysis record: `execution_status`, `validation_status`, `validation_level`, `reason_codes`, `next_action`, scopes, outputs, evidence, `evidence_assessment`, `leakage_check`, derived features with `formula_status`, error |
| `get_analysis_result` | `analysis_id` | The same record for a queued/running/finished analysis |

Each capability flag is derived from the registry. It becomes `true` only when its providing
tool is actually registered: `catalog_discovery` → `discover_catalog`, `full_catalog_read` →
`read_catalog_rows`, `market_data_preview` → `preview_table_rows`, `database_query` →
`request_data`, `python_analysis` → `run_python_analysis`, `web_search` → `search_web`, `external_data` →
`request_external_data` (not implemented: no external provider is connected, so it is always
`false`; the provider contract is in market-sql-governor `app/external.py`). The
catalog tools are registered only when `CATALOG_DATABASE_URL` is set;
`preview_table_rows` additionally requires `MARKET_DATA_PREVIEW_ENABLED=true`; and
`request_data` and `get_dataset_manifest` only when `SQL_GOVERNOR_URL` is set; and
`run_python_analysis`/`get_analysis_result` only when `PY_SANDBOX_URL` is set and the sandbox was
ready at startup. Otherwise `python_analysis` is `false`.

The logical catalog tool surface maps onto the existing tools. It keeps the names used by the
DATA DISCOVERY RULES prompt block:

| Logical tool | Implemented by |
|---|---|
| `search_catalog()` | `discover_catalog()` |
| `get_table_context()` | `get_catalog_details(sections=["COLUMNS", "RELATIONSHIPS"])` |
| `get_calculation_definition()` | `get_catalog_details(sections=["CALCULATIONS"])`, including `status` and `validation_evidence` |
| `get_data_coverage()` | `get_catalog_details(sections=["COVERAGE"])`, with an explicit `availability_interpretation` per dataset |

## Data requests

`request_data` takes the Data Request Spec defined in `app/tools/request_data.py`. It is
identical to the Governor's `app/spec.py`, and a contract test enforces this. The tool:
- checks the spec with the same strict model (unknown fields and malformed identifiers never
  leave this service);
- posts `{request_id, spec}` to `SQL_GOVERNOR_URL/v1/query` with the bearer key;
- returns the Governor's JSON: `decision`, `next_action`, `reason_code`, the dataset reference,
  and details. An approved request is always `DATASET_READY`; a response that carries rows or an
  unknown decision (for example from an outdated Governor) becomes a `TOOL_ERROR`, so data rows
  never reach the model through this tool.

`lookup_fact` takes the Lookup Fact Spec (identical to the Governor's, contract-tested) and posts
it to `SQL_GOVERNOR_URL/v1/lookup`. It is the only way specific source values reach the model:
at most 20 per call, each with a `fact_id`. Refusals with `next_action = USE_ANALYSIS_PATH` send
the model to the analysis path. Statistics never go through it.

Governor HTTP errors and timeouts become a generic `TOOL_ERROR`. The spec has no SQL,
expression, join-key, or delivery-format field, and the row, scan, and byte ceilings exist
only in Governor configuration. The DATA QUERY RULES block is appended after DATA DISCOVERY
RULES in the system prompt; it contains no thresholds or credentials.

## Two-path analysis (Analysis Spec V2)

The model writes **one** Analysis Spec V2 (`create_analysis_spec`). It then names only the spec_id to
`prepare_analysis_data`, and only the returned `input_bundle_id` to `run_python_analysis`. The model
never restates the scope as a data request.

- **`prepare_analysis_data`** (`app/tools/data_compiler.py`, DataRequestCompiler):
  - It reads the approved contract from the sandbox (same request only, V2 only).
  - It compiles each logical input's data plan into a Data Request Spec: the columns, the catalog
    relationship joins, the attribute/entity filters with values typed by the catalog, and the
    warm-up date range. It submits each request to the Governor with data-plan lineage.
  - On a size refusal (`DATE_RANGE_TOO_LARGE`, scan, result, cost, time) it splits the date range
    into contiguous partitions, at most 16, without changing entities, predicates, metric or
    period.
  - Anything it cannot fix comes back as a structured rejection: `stage`, `reason_code`,
    `observed`, `limit`, `allowed_actions`, `forbidden_actions` (for example `CHANGE_USER_SCOPE`,
    `DROP_ENTITIES`, `SAMPLE_WITHOUT_PERMISSION`), and `retryable`.
- **Input bundles.**
  - `run_python_analysis` takes `input_bundle_id`, and the backend binds that bundle's datasets.
  - A bundle resolves only for the request and spec it was prepared for (`INPUT_BUNDLE_MISMATCH`
    otherwise).
  - The sandbox independently proves each dataset's executed scope equals the approved plan.
- **Flags.**
  - `AI_ENABLE_LOOKUP_FACT` (default `true`) registers `lookup_fact` and its prompt rule. With
    `false`, the tool and the rule leave the tool schema and the prompt; `/v1/lookup` stays in the
    Governor for rollback.
  - `AI_ENABLE_REQUEST_DATA` (default `false`) registers the model-written `request_data` tool, a
    rollback path only.
  - The system prompt is fixed per deployment, so prompt caching keeps one prefix.
- **Repair ledger.**
  - The same rejection (tool + reason code, for example `INVALID_SPEC:UNKNOWN_COLUMN` or a failed
    analysis error code) may be repaired `AI_MAX_REPAIR_ATTEMPTS` times per run (default 3).
  - After that, the tool answers `REPAIR_BUDGET_EXHAUSTED` and the model must report a
    LIMITATION.
  - The counters are logged with `ai_run_completed` (`repair_ledger`).
- **Catalog discovery** includes each table's `subject` (data_domain, entity_type, asset_type,
  supported_frequencies, time_semantics, subject_metadata_status) once migration 20260925_001 is
  applied.
- **`get_dimension_values`** lists the exact values of a groupable text dimension before the model
  writes an attribute predicate or a segment. The Governor serves it from an approved static table
  only (`POST /v1/catalog/dimension-values`, orc key), with a bounded scan, at most 200 values, and
  no counts.
- **Generic operations in the spec.** The sandbox validates all of these:
  - `PERIOD_RETURN`, and `PERIOD_STAT` (a per-entity statistic over the period, for example the
    standard deviation of daily returns, never an annualized stored feature);
  - `GROUP_AGGREGATE` by catalog keys of any input or by labelled `segments` (predicates on
    different columns), per group or per group and date;
  - `GROUP_CORRELATION` of aligned group series (`GROUP_PAIR` output);
  - top-N `ranking` over the complete population.

  A return averaged across entities over a period needs a stated basis (period return versus
  daily returns); otherwise the review asks the user.

## Python analysis

market-ai-orc never executes model-generated Python. The sandbox runs the code and validates it
(see [`../market-python-sandbox/README.md`](../market-python-sandbox/README.md)); this service
supplies the user's own words, enforces the order of the tools, and gates the final response.

**1. `create_analysis_spec`.** The model states the requested analysis as a structured spec
(universe, period, frequency, inputs, calculations with parameters, outputs, exclusion rules), each
requirement marked `USER_EXPLICIT`, `USER_CLARIFIED`, `APPROVED_DEFAULT` (with its `default_id`),
or `AI_INFERRED`. The tool adds what the model cannot choose, from the run itself (`RunContext`):
the `request_id`, the reference time (`wall_clock`, pinned in tests), `ANALYSIS_TIMEZONE`, and the
user's actual messages (history plus the current message; assistant turns are included so a
clarified answer can be recognised). The sandbox checks the spec against those messages with
deterministic rules and answers `APPROVED`, `APPROVED_WITH_UNVERIFIED`, `ANALYSIS_SPEC_MISMATCH`, or
`NEEDS_CLARIFICATION`. Only approved specs get an immutable `spec_id`. The model sees a compact
view: `status`, `spec_id`, `resolved_period`, `required_input` (the date range to request,
including warm-up), `output_contract` (the key and value columns each output must contain),
mismatches, unverified requirements, and clarification needed.

**2. `run_python_analysis`.** `{request_id, spec_id, inputs, python_code, expected_outputs}` is
validated by a strict model aligned with the sandbox's `AnalysisRequest` (contract test) and posted
to `PY_SANDBOX_URL/v1/analyses`. The sandbox waits briefly and returns either a finished record or
`QUEUED`/`RUNNING` with `next_action=GET_ANALYSIS_RESULT` and `retry_after_seconds`;
`get_analysis_result` then waits up to `PY_SANDBOX_POLL_WAIT_SECONDS`. The runtime interface
(pre-bound `saniti` helpers such as `load`, `sql`, `in_period`, `emit_table`, `pd` and `np`, and
the libraries including TA-Lib) is described in the tool description.

**What the model sees:**
- `execution_status` and `validation_status` (`PASS`, `INCOMPLETE`, `FAILED`, `UNVERIFIED`) with
  `validation_level`, `reason_codes`, and a deterministic `next_action`;
- `expected_scope`, `actual_scope`, and compact `validation_evidence` (a calculation mismatch may
  carry a diagnosis such as `PARAMETER_DIFFERS` or `WARMUP_NOT_USED`);
- TABLE: `row_count`, columns, a bounded preview, and `result_id`. The complete table stays in
  the sandbox (`GET /v1/results/{id}` for backend/frontend presentation). METRICS: the values.
  CHART and ARTIFACT: ids and metadata only, never bytes;
- `evidence_assessment` for a research spec (claim type, `decision`, `evidence_level`, checks,
  statistics, and `reporting_constraints`) and the `leakage_check` outcome, both computed by the
  sandbox validator;
- warnings (including `CORPORATE_ACTIONS_NOT_ADJUSTED`), derived features (`formula_status`
  `VALIDATED_CUSTOM_FORMULA_RESULT` when a CUSTOM expression was recalculated and matched,
  otherwise `EXPLORATORY_UNVALIDATED`; statistical validation `NOT_PERFORMED`), a structured error with only the model's own code lines, and a compact
  lineage (spec hash, code hash, seed, library versions, dataset checksums).

Sandbox limits, deployment ids, and resource usage are removed. Refusals such as `QUEUE_FULL`,
`SPEC_NOT_FOUND`, `REQUEST_BUDGET_EXCEEDED`, or `SANDBOX_ISOLATION_UNAVAILABLE` come back as
`status: REJECTED` with a `next_action`. Transport failures become `TOOL_ERROR`.

**3. Validation gate.** Every analysis result the model receives is recorded in the run state
from the sandbox's record. When the model returns its final response, the latest analysis of each
spec is checked:
- validation `FAILED` or `INCOMPLETE`, or an execution that did not complete: an `ANSWER` is
  rejected once with an instruction to fix, rerun, request data, or report a limitation, and the
  tools stay available for that repair. A second `ANSWER` is converted to `LIMITATION` with a
  notice and the findings as limitations (`FORCED_LIMITATION`);
- validation `UNVERIFIED`, a level below `CALCULATION_VERIFIED`, or unverified spec requirements:
  the matching limitation lines are appended when the model left them out (`ANNOTATED`).
- **routing guard:** when the user's question asks for a statistic (the sandbox's deterministic
  method-family rules: RSI, moving average, standard deviation, z-score, return, forward return,
  correlation) or a ranking or percentage change, an `ANSWER` needs an analysis whose outputs are
  a source (execution `COMPLETED`, validation `PASS` or `UNVERIFIED`); facts alone are rejected
  once, then forced to `LIMITATION`. A plain average over an explicit scope may instead come from
  a `lookup_fact` `AVG` aggregate. When the latest message answers a clarification question, the
  previous user turn is checked too;
- **number provenance** (`app/provenance.py`): every number in `answer` (tables included) must
  match a source of this run: a `lookup_fact` value, an output (METRICS or table preview) of an
  analysis with execution `COMPLETED` and validation `PASS` or `UNVERIFIED`, a number in the
  user's messages, an approved spec (its parameters, resolved period, and required input), a
  dataset manifest, the counts in validation evidence and scopes, or the application's own
  prompt and tool descriptions. Outputs of `FAILED`/`INCOMPLETE` analyses, mismatch examples, and
  `preview_table_rows` values are never sources. A match allows rounding to the displayed
  decimals, decimal ↔ percent, Indonesian and English separators, "ribu/juta/miliar" style
  multipliers, and a sign stated in words ("turun 2,4%"). Dates, years, list markers, and digits
  inside identifiers (T001, ids) are not checked. Unsupported numbers are rejected once with
  their list, then the response is forced to `LIMITATION` with a notice (this also applies to a
  `LIMITATION` that quotes them). The statistics of an evidence assessment (for example the
  interval of a mean difference) are validator outputs and count as sources;
- **claim gate:** causal wording ("causes", "menyebabkan", "penyebab", ...) is never supported by
  these analyses, and predictive wording ("will rise", "akan naik", "predicts", "sinyal beli",
  ...) needs an analysis with evidence standard `PREDICTIVE` whose assessment is `SUPPORTED`. A
  match preceded within 40 characters by a negation ("not a prediction", "bukan penyebab") is not
  a claim. An unsupported claim in an `ANSWER` is rejected once, then forced to `LIMITATION`;
- **research lines:** for each research analysis, its evidence decision and level and its
  `reporting_constraints` are appended to `limitations` when the model left them out, and when an
  analysis warned `CORPORATE_ACTIONS_NOT_ADJUSTED` a line discloses that prices are not
  dividend-adjusted.

Each check rejects at most once per run, and tools stay available for the repair.
`CLARIFICATION` responses are never blocked. The gate is code, not a prompt rule: the prompt
blocks only explain it to the model.

`get_dataset_manifest` calls the Governor's `GET /v1/datasets/{id}/manifest` with the existing
Governor key. The orc key cannot obtain dataset URLs.

The PYTHON ANALYSIS RULES, ANALYSIS VALIDATION RULES, and RESEARCH RULES blocks are appended after
DATA QUERY RULES. They contain no limits, URLs, credentials, or security details.

### Research runs

One research run is one `request_id`; there is still one orchestrator and no second agent. The
model marks a research question with `research` in `create_analysis_spec`:
`evidence_standard` (`CALCULATION`, `SCREEN`, `DESCRIPTIVE`, `HISTORICAL_PATTERN`, `EXPLORATORY`,
`PREDICTIVE`, `SCENARIO`), `objective`, `hypothesis`, `method_ref` (an `AI_research_catalog`
method as methodology reference), `followup_of`, `candidates`, `holdout`, and the design
(`design_type` `EVENT_STUDY` / `COMPARATIVE` / `ASSOCIATION` / `PREDICTIVE_TEMPORAL` /
`EXPLORATORY_SEARCH`, `primary_metric`, `observation_unit`, `comparator`,
`multiple_testing_policy`). The deterministic
Research Governor in the sandbox (see
[`../market-python-sandbox/README.md`](../market-python-sandbox/README.md#research-governor-evidence-assessment-and-leakage))
answers `APPROVED`, `REPLAN_REQUIRED`, or `REJECTED` with a `reason_code` and the run's budget;
the model sees that decision and must follow it. A plain calculation, screen, or description needs
no research block. The model cannot change a governor decision, an evidence assessment, or a
leakage outcome: they come from sandbox records.

### Research run audit

After every run (`app/audit.py`), the orchestrator:
1. posts the final report (answer and its sha256, question sha256, evidence label, gate outcome,
   limitations, number provenance, experiments) to the sandbox `POST /v1/runs/{request_id}/report`
   when the run used the sandbox. The sandbox keeps the run's operational state (specs, governor
   decisions, analyses, budgets) and stores the report once;
2. reads `GET /v1/runs/{request_id}` and, when `RESEARCH_AUDIT_DATABASE_URL` is set, inserts one
   summary row into PostgreSQL `AI_research_run_audit` (datasets by id and checksum, experiments
   with code hash and leakage outcome, budget). The writer role has INSERT only; a retried
   `request_id` keeps its first row (`ON CONFLICT DO NOTHING`).

Auditing never changes the response and never fails the run; failures are logged as
`research_audit` events. Hidden model reasoning, secrets, and dataset contents are never recorded.

## Catalog discovery

The five `AI_*` tables created by `database/migrations/20260922_001_create_ai_catalogs.sql`,
the global `AI_research_catalog` created by
`database/migrations/20260924_001_create_ai_research_catalog.sql`, and the global
`AI_formula_reference` created by
`database/migrations/20260924_003_create_ai_formula_reference.sql` provide metadata.
The service creates no catalog tables and never accepts model-supplied SQL.
The research migration creates the 19-column table and read-only role grant; it contains no
workbook rows. After inspecting the target database, use
`scripts/import_ai_research_catalog.py /path/to/Saniti_DB_AI_Research_Catalog.xlsx`
with `DATABASE_URL` set to that database. The script requires `openpyxl` and `psycopg`,
checks the reviewed workbook SHA256, refuses a nonempty target, inserts the 18 records in
one transaction, and reads every field back before committing. The formula migration creates
the 8-column table the same way, activating FORMULAS support immediately (the three tools are
already active, unlike the RESEARCH rollout); use
`scripts/import_ai_formula_reference.py /path/to/AI_Calculation_Formula.xlsx` the same way for
its 200 records. Run these before deploying ORC code that reads the new tables. Keep both
workbooks outside the public repository.

### Visibility rules

All rules come from the catalog's own flags:

| Catalog | A row is visible when |
|---|---|
| `AI_table_catalog` | `is_active AND ai_access_level = 'BOUNDED_READ'` |
| `AI_column_catalog` | its table is visible, `ai_allowed`, and `NOT is_sensitive` |
| `AI_catalog_relationships` | `is_allowed`, and both `left_table` and `right_table` are visible |
| `AI_calculation_catalog` | its `target_table` is visible and `status = 'ACTIVE'` |
| `AI_data_coverage` | its `dataset_name` is visible and that table has `coverage_enabled` |
| `AI_research_catalog` | all reference methods are discoverable; `implementation_status` is reported verbatim, not treated as an execution permission |
| `AI_formula_reference` | all documented formulas are discoverable; there is no per-row status, but every FORMULAS response repeats that these are documented definitions, not verified or executable implementations |

`documentation_status` (`VERIFIED`, `PARTIAL`, `NEEDS_REVIEW`) is passed through, never used
to hide rows. These rules apply only to the two targeted tools; both notices say so, and
`read_catalog_rows` returns every row including the ones they hide. A `NULL` description is returned as `null`: per `DATABASE_CATALOG.md`, the
meaning is not established and must not be inferred.

### `discover_catalog()`

This tool takes no arguments. For each visible table it returns `table_name`, `description`,
`category`, `grain`, `primary_key_columns`, `time_column`, `entity_column`,
`documentation_status`, `freshness_sla`, `coverage_enabled`, and `available_metadata`
(counts of visible columns, active calculations, and allowed relationships). At most 50
tables are returned, with a `truncated` flag.
The separate `research_catalog` field reports the global method count and counts by
`implementation_status`; `formula_catalog` reports the global formula count. Neither is
added to the market-data `tables` list.

### `get_catalog_details(table_names, sections, column_names, entity_ids, method_ids, formula_ids)`

| Argument | Contract |
|---|---|
| `table_names` | 1–3 visible market-table names, or `[]` when requesting only `RESEARCH`/`FORMULAS` |
| `sections` | 1–6 of `COLUMNS`, `RELATIONSHIPS`, `CALCULATIONS`, `COVERAGE`, `RESEARCH`, `FORMULAS` |
| `column_names` | `null`, or 1–40 names matching `^[A-Za-z0-9_][A-Za-z0-9_ ]{0,62}$` (spaces allowed, e.g. `Investor Type`); narrows `COLUMNS` and `CALCULATIONS` |
| `entity_ids` | `null`, or 1–20 ids matching `^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$` (e.g. tickers); adds per-entity `COVERAGE` rows |
| `method_ids` | `null` for all methods, or 1–40 exact research `method_id` values; narrows `RESEARCH` |
| `formula_ids` | `null` for all formulas, or 1–40 exact `calculation_id` values; narrows `FORMULAS` |

The tool schema is strict and generated from the same Pydantic model that validates the
arguments. Unknown fields are rejected, and invalid input never reaches the database.

What each section returns:

| Section | Source | Fields |
|---|---|---|
| `COLUMNS` | `AI_column_catalog` | `column_name`, `description`, `data_type`, `semantic_type`, `unit`, `nullable`, `is_primary_key`, `source_column_or_expression`, `allowed_aggregations`, `filter_allowed`, `group_by_allowed`, `example_value`, `documentation_status`; grouped by table, in `ordinal_position` order |
| `RELATIONSHIPS` | `AI_catalog_relationships` | `relationship_id`, `left_table`, `left_columns`, `right_table`, `right_columns`, `relationship_type`, `temporal_rule`, `safe_output_grain`, `requires_preaggregation`, `description`, `version` (`left_columns[i]` joins `right_columns[i]`) |
| `CALCULATIONS` | `AI_calculation_catalog` | `calculation_name`, `version`, `status`, `target_columns`, `definition`, `required_inputs`, `parameters`, `defaults`, `alignment_rules`, `missing_data_policy`, `output_definition`, `validation_evidence`; `implementation_ref` is omitted to save space |
| `COVERAGE` | `AI_data_coverage` | The `DATASET` row per table with `availability_interpretation` (`CONFIRMED_SOURCE_RANGE`, `SNAPSHOT`, `PIPELINE_CONFIRMED`, or `EXPECTED_NOT_CONFIRMED`; an expected range is never confirmation), `entity_status_counts` (entity rows grouped by pipeline, verification, and quality status), and the matching `ENTITY` rows only when `entity_ids` is given. It never dumps the ~14k per-ticker rows |
| `RESEARCH` | `AI_research_catalog` | The 19 fields defining each global method. Returns summary fields when full entries exceed the payload budget; narrow with `method_ids` for complete records. `REFERENCE_ONLY` does not mean sandbox support or independent validation. |
| `FORMULAS` | `AI_formula_reference` | The 8 fields defining each global formula (`formula_method` renamed from the source workbook's `formula / method`). Returns summary fields when full entries exceed the payload budget; narrow with `formula_ids` for complete records. A documented formula is not sandbox support or independent validation. |

A field that is `NULL` or empty in the catalog is omitted from the entry, except the
explicit `description`/`definition` `null`. The result notice states this.

Other cases are reported explicitly:
- Requested tables that are unknown or hidden: `unknown_tables`, or `TOOL_ERROR` when none
  are visible.
- Columns and entities not found: `unknown_columns` and `unknown_entities`.
- Tables with coverage disabled: `coverage_disabled_tables`.
- Tables with no coverage row: `no_coverage_record`.
- Empty sections: a `note`.

### Bounds

- **SQL:** fixed statements with `%s` parameters only; table, column, and entity names are
  bound as values, never as identifiers.
- **Row caps:** 150 columns, 100 calculations, 50 relationships, 50 research methods, 50 formulas, 60 status groups,
  and 60 entity rows per call.
- **Payload budget:** the result stays within a 24 KB budget, below the registry's 32 KB
  hard cap. Small sections are filled first. A large `COLUMNS` or `CALCULATIONS` section
  first switches to `detail: "SUMMARY"` (names, definitions, types, units), then truncates,
  always with `returned`, `total_matching`, `truncated`, and a `hint` to narrow with
  `column_names`.
- **Database session:** one read-only transaction per tool call, opened with
  `default_transaction_read_only=on`, `statement_timeout`, and a connect timeout. Database
  errors return a generic `TOOL_ERROR` with no server message or DSN.

## Full catalog access

`read_catalog_rows(catalog_name, page_size, cursor)` returns the complete records of one of
the seven `AI_*` catalogs: every column and every row, including rows that the visibility
rules above hide (inactive or denied tables, disallowed or sensitive columns, disallowed
relationships, inactive calculations). No filter is applied.

| Argument | Contract |
|---|---|
| `catalog_name` | Exactly one of `AI_table_catalog`, `AI_column_catalog`, `AI_catalog_relationships`, `AI_calculation_catalog`, `AI_data_coverage`, `AI_research_catalog`, `AI_formula_reference` (enum) |
| `page_size` | `null` for `CATALOG_PAGE_SIZE_DEFAULT` (100), or 1–`CATALOG_PAGE_SIZE_MAX` (200) |
| `cursor` | `null` for the first page, or the exact `next_cursor` of the previous page |

Result: `catalog_name`, `columns` (`name`, `type`, `nullable`, in table order), `order_by`
(the primary-key columns), `rows` (arrays aligned to `columns`), `returned_rows`,
`page_size`, `page_limited_by` (`PAGE_SIZE`, `BYTE_BUDGET`, or `null` on the last page),
`total_rows`, `rows_before_this_page`, `has_more`, `next_cursor`, and `notice`.

How paging stays complete:
- **Keyset order.** Rows are ordered by the primary key, discovered at run time from
  `pg_index`, and each page continues with `WHERE (pk...) > (last key)`. Pages never skip or
  repeat a row of an unchanged table. If a catalog has no primary key, the tool refuses
  rather than paging unstably.
- **No silent truncation.** A page fetches `page_size + 1` rows to know whether more exist.
  It ends early only to stay within `CATALOG_PAGE_MAX_BYTES`, and then says
  `page_limited_by: "BYTE_BUDGET"` with `has_more: true`. A single row larger than the
  budget is an explicit `TOOL_ERROR`, never a cut row.
- **Cursor.** The cursor is base64url JSON `{"v":1,"c":catalog,"k":[last key values]}` plus a
  truncated HMAC-SHA256. The secret is derived from `MARKET_AI_ORC_API_KEY`, so cursors
  survive restarts and replicas. A cursor carries key values, never SQL. It is bound to its
  catalog, and a tampered or foreign cursor is rejected. It is tamper-evident, not
  encrypted: it holds only key values the model has already seen.
- **Consistency.** Each page is one `REPEATABLE READ`, read-only transaction. Rows inserted or
  deleted between two pages can appear or disappear, as with any keyset pagination. The
  catalogs change only on pipeline refreshes.

Exact values: rows are produced by PostgreSQL `to_json` and parsed with `Decimal`, so
`numeric` values are returned as exact decimal strings (`"12345678901234567.89"`). Integers
stay JSON integers, and dates and timestamps are ISO strings.

`AI_data_coverage` has about 14k rows (about 141 pages at the default size), which is more
than one agent run's tool budget. `get_catalog_details(..., sections=["COVERAGE"])` gives the
aggregated status counts instead.

## Market-data preview

`preview_table_rows(table_name)` returns up to 20 example rows, with all columns, from one of
seven approved tables. The only argument is the table name. There are no filters, offsets,
custom limits, ordering choices, or pagination, so repeated calls return the same rows.
Rows are example records, marked `is_sample: true`. They are not a random or representative
sample and not an analytical result.

| Table | Fixed order (`ordering.order_by`) | Backing index |
|---|---|---|
| `Feature_01_Stock_Daily` | `date DESC, ticker DESC` | `(date)` index, then top-N sort within the latest date |
| `Feature_02_Broker_Rolling` | `date DESC, market_board DESC, ticker DESC, broker DESC, investor_type DESC` | `(date, market_board, ticker)` index, then a small incremental sort |
| `Feature_03_Stock_Broker_Daily` | `date DESC, market_board DESC, ticker DESC` | `(date, market_board, ticker)` index |
| `IDX_Broker_Profile` | `broker_code ASC` | primary key |
| `IDX_Broker_Summary` | `"Date" DESC, "Symbol" DESC, "Broker" DESC, "Investor Type" DESC, "Market Board" DESC` | primary key, scanned backward |
| `IDX_Stock_Universe` | `"Ticker" ASC` | primary key |
| `Price_Stock_Indonesia_IDX` | `date DESC, ticker DESC` | `(date)` index, then top-N sort within the latest date |

Result: `table_name`, `columns`, `rows` (arrays aligned to `columns`, with exact decimal
strings), `returned_rows`, `row_limit: 20`, `ordering` (`order_by` and a plain-language
`description`), `is_sample: true`, and `notice`. A preview larger than 48,000 bytes is an
explicit `TOOL_ERROR`; a partial preview is never returned.

**The database enforces the boundary.** The service calls only
`SELECT public.ai_preview_table_rows(%s)`, with the table name bound as a value. That
function (migration `20260923_002_create_market_ai_preview_interface.sql`):
- maps the name through a hard-coded `CASE` allowlist and raises `insufficient_privilege`
  for anything else;
- composes identifiers with `format('%I')` and literals with `format('%L')`, and hard-codes
  `ORDER BY` and `LIMIT 20`;
- is `SECURITY DEFINER` with `search_path = pg_catalog, pg_temp`. It is owned by `NOLOGIN`
  role `market_ai_preview_owner`, which has `SELECT` on exactly the seven tables and no
  write privilege;
- is executable only by `market_ai_preview_reader` (`PUBLIC` is revoked). That role has no
  table privilege at all.

The login therefore cannot read market tables directly, cannot pick another table, and
cannot get more than 20 rows, whatever the application does. The service also checks the
function's reply (table, `row_limit`, row count, ordering) and returns nothing if it
disagrees.

## Database access

1. Apply `database/migrations/20260923_001_create_market_ai_catalog_reader.sql`. It creates
   `NOLOGIN` role `market_ai_catalog_reader` with `USAGE` on schema `public` and `SELECT` on
   exactly the five `AI_*` tables. It fails the transaction if that role could read or
   modify any other public table.
2. Apply `database/migrations/20260923_002_create_market_ai_preview_interface.sql` as a
   superuser, which is needed to hand the function to its owner role. It creates the
   preview function and the roles `market_ai_preview_reader` and `market_ai_preview_owner`.
   It fails the whole transaction if any of these hold: the function already exists, a
   table is missing, the owner or reader has any privilege beyond the design, or `PUBLIC`
   can execute the function.
3. Run `scripts/provision_market_ai_orc_login.py` with `DATABASE_URL` (admin) and
   `MARKET_AI_ORC_DB_PASSWORD`. It creates or rotates login `market_ai_orc` with
   `CONNECTION LIMIT 5`, `default_transaction_read_only=on`, `statement_timeout=5s`,
   `lock_timeout=2s`, and `idle_in_transaction_session_timeout=15s`. The login is a member
   only of `market_ai_catalog_reader`, plus `market_ai_preview_reader` when step 2 was
   applied. The script then verifies that the readable public tables are exactly the seven
   catalogs, and that preview EXECUTE matches membership.
4. Set `CATALOG_DATABASE_URL` to the private DSN for `market_ai_orc`
   (`postgres.railway.internal:5432`).
5. Run `scripts/verify_market_ai_orc_data_access.py` with that `CATALOG_DATABASE_URL`. It
   uses the service's own tool code to read every catalog to the end, checking that rows
   read = distinct keys = `total_rows`, and to preview each approved table. It prints only
   counts, column names, ordering, and byte sizes, never row values.

`scripts/inspect_ai_catalogs.py` is a read-only report of catalog structure, visibility
states, sizes, and samples. It works with the `market_ai_orc` login.

All database access is one read-only `REPEATABLE READ` transaction per tool call, rolled
back at the end. A timeout, a missing interface, or a permission error returns a
generic `TOOL_ERROR` with no server message or DSN.

## Known catalog gaps

These are observed in the migration seed and reported, not changed:
- `AI_calculation_catalog.definition` is copied from `Feature_Catalog.definition`. The
  separate `Feature_Catalog.calculation` expression is **not** in the AI catalog.
- `AI_column_catalog.example_value` is seeded `NULL` for every row.
- Every seeded column has `ai_allowed = true` and `is_sensitive = false`.

## Currently unavailable capabilities

These are not implemented, and no placeholder pretends they exist: model-written SQL (market
data is reached only through `request_data` and the Governor), the legacy
`Table_Catalog`/`Column_Catalog`/`Feature_Catalog` catalogs, external data providers (the
contract exists in market-sql-governor `app/external.py`, but no provider is registered and no
credential is configured), causal inference or probabilistic forecasting beyond the event-study
evidence assessment, web search, RAG or vector search, long-term memory, multi-agent flows, Redis,
frontend, and Telegram.

## Railway deployment

- Service `market-ai-orc` (`41dc17ee-3bac-41ef-90ec-8b9356815c71`) runs in project `lucid-patience`, environment `dev`.
- It is private: `http://market-ai-orc.railway.internal:8080`. There is no public domain.
- `request_data` is live. `SQL_GOVERNOR_URL=http://market-sql-governor.railway.internal:8080`, and
  `SQL_GOVERNOR_API_KEY` is a reference to `${{market-sql-governor.SQL_GOVERNOR_API_KEY}}`.
- Its health check is `/ready`. The start command is
  `uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8080`.
- `OPENROUTER_API_KEY` is a Railway reference to `${{market-ai-backend.OPENROUTER_DEEPSEEK}}`,
  so rotating that key updates both services.
- A future backend caller should reference `${{market-ai-orc.MARKET_AI_ORC_API_KEY}}` rather
  than copying it.
- It is currently deployed by local upload. A GitHub `main` source is not connected yet.
  The service watch path `/apps/market-ai-orc/**` also applies to CLI uploads, so a
  `--path-as-root` upload of this folder is skipped as "No changes to watched files". Upload
  a staging folder instead: it keeps the code under `apps/market-ai-orc/` and has a root
  Dockerfile that copies `apps/market-ai-orc/requirements.txt` and `apps/market-ai-orc/app`.
- Catalog and preview access are live. Migrations `20260923_001`–`003` are applied, and the
  `market_ai_orc` login is provisioned. `CATALOG_DATABASE_URL` is a Railway reference built
  from `MARKET_AI_ORC_DB_PASSWORD` and the `Postgres` service's private domain.
- The run audit is live (migration `20260924_004`). `RESEARCH_AUDIT_DATABASE_URL` is the same
  reference template as `CATALOG_DATABASE_URL`: the `market_ai_orc` login also holds the
  INSERT-only `market_ai_research_audit_writer` role.
- Capacity on `dev` (since the Research AI release): `AI_MAX_TOOL_CALLS=60`,
  `AI_MAX_TOOL_ITERATIONS=60`, `AI_MAX_CONTEXT_TOKENS=500000` (the model's window is 1,048,576),
  and `AI_MAX_ANALYSIS_SECONDS=1800`. A caller of `/v1/agent/run` needs an HTTP timeout above
  1800 s.

## Run locally

```bash
cd apps/market-ai-orc
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
export MARKET_AI_ORC_API_KEY=... OPENROUTER_API_KEY=...
uvicorn app.main:create_app --factory --port 8080

curl -s localhost:8080/v1/agent/run \
  -H "Authorization: Bearer $MARKET_AI_ORC_API_KEY" -H "Content-Type: application/json" \
  -d '{"request_id":"smoke-1","message":"What capabilities do you currently have?"}'
```

The container runs the same factory command on port `8080`.

## Run tests

```bash
cd apps/market-ai-orc
pip install -r requirements-dev.txt
python -m pytest
```

The tests mock all HTTP traffic and make no OpenRouter calls. The integration tests in
`tests/test_catalog_postgres.py` and `tests/test_data_access_postgres.py` run only when
`ORC_TEST_POSTGRES_URL` points to a disposable PostgreSQL server:

```bash
ORC_TEST_POSTGRES_URL=postgresql://postgres@127.0.0.1:55432/postgres python -m pytest
```

They create a temporary database from the exact DDL in
`20260922_001_create_ai_catalogs.sql`. They add the seven market tables with the exact
columns, keys, and indexes of `DATABASE_SCHEMA.md`, filled with synthetic rows. They apply
both migrations and the provisioning script, call every tool as the `market_ai_orc` login,
and drop everything afterwards.
