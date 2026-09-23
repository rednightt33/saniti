# market-ai-orc

AI orchestration service. It receives an AI request from a trusted backend, calls
OpenRouter, runs registered tools when the model asks for them, and returns a validated
structured response. Phase 2 adds read-only **catalog discovery** over Saniti's five
`AI_*` metadata tables.

It was derived from `apps/market-ai-backend`. It keeps that service's proven OpenRouter
Responses transport, bounded retry, quota handling, usage accounting, strict final-schema
validation with bounded retries, and bounded agent loop. It removes everything tied to
market data: PostgreSQL, catalogs, SQL governance, query sandbox, statistical worker,
S3 snapshots, evidence and completion gates, and analysis routing.

`market-ai-orc` has **no market-data access and no bucket credentials**. Its only database
access is optional and read-only: the `market_ai_orc` login can SELECT exactly the five
`AI_*` catalog tables (see [Catalog discovery](#catalog-discovery)). It is stateless: the
caller owns conversation persistence.

## Architecture

Current (Phase 2):

```text
Backend
   ↓  POST /v1/agent/run  (Bearer MARKET_AI_ORC_API_KEY)
market-ai-orc
   ↓  POST https://openrouter.ai/api/v1/responses
OpenRouter → AI model
   ↓  optional function_call
market-ai-orc executes a registered tool → function_call_output
   │    discover_catalog / get_catalog_details → read-only AI_* catalog metadata
   ↓  (repeat within limits)
strict final response
   ↓
Backend
```

Future (not built yet):

```text
Backend
   ↓
market-ai-orc
   ↓
OpenRouter AI
   │
   ├── request_data()        [future — NOT IMPLEMENTED]
   │       ↓
   │   SQL Governor
   │
   └── run_python_analysis() [future — NOT IMPLEMENTED]
           ↓
       Python Sandbox
```

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
| `AI_MAX_ANALYSIS_SECONDS` | no | `600` | Wall-clock limit per run |
| `AI_MAX_CONTEXT_TOKENS` | no | `64000` | Context ceiling (estimated before the call, provider-reported after) |
| `AI_MAX_HISTORY_TOKENS` | no | `4000` | Budget for supplied history; the newest whole turns are kept |
| `AI_FINAL_RESPONSE_MAX_RETRIES` | no | `2` | Retries after an invalid final response (`0` allowed) |
| `OPENROUTER_HTTP_REFERER` | no | unset | Optional `HTTP-Referer` header |
| `OPENROUTER_X_TITLE` | no | `Saniti Market AI` | `X-Title` header |
| `CATALOG_DATABASE_URL` | no (secret) | unset | DSN for the catalog-only `market_ai_orc` login. When unset, the catalog tools are not registered |
| `CATALOG_CONNECT_TIMEOUT_SECONDS` | no | `5` | Catalog connection timeout (≤ 30) |
| `CATALOG_STATEMENT_TIMEOUT_MS` | no | `5000` | Per-statement timeout for catalog queries (100–30000) |

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
    "duration_ms": 0
  },
  "error": null
}
```

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
class RequestDataArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")   # required
    dataset: str                                 # every field required; use `X | None` for optional
    ticker: str | None

registry.register(ToolSpec(
    name="request_data",
    description="...",
    arguments_model=RequestDataArguments,        # validates arguments AND generates the strict schema
    handler=lambda args: {...},                  # returns a JSON object
    timeout_seconds=10,
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
- Registration rejects invalid names, duplicates, models without `extra="forbid"`, fields
  with defaults, and nested models.

## Currently available tools

| Tool | Arguments | Result |
|---|---|---|
| `get_system_capabilities` | none | Capability flags plus `available_tools`, for example `{"catalog_discovery": true, "database_query": false, "python_analysis": false, "web_search": false, "available_tools": [...]}` |
| `discover_catalog` | none | AI-visible tables with their catalog metadata (see below) |
| `get_catalog_details` | `table_names`, `sections`, `column_names`, `entity_ids` | Requested catalog sections (see below) |

Each capability flag is derived from the registry. It becomes `true` only when its providing
tool (`discover_catalog`, `request_data`, `run_python_analysis`, `search_web`) is actually
registered. The two catalog tools are registered only when `CATALOG_DATABASE_URL` is set.

## Catalog discovery

The five `AI_*` tables created by `database/migrations/20260922_001_create_ai_catalogs.sql`
are the only metadata source. The service creates no catalog tables, hardcodes no table
list, and never accepts SQL.

### Visibility rules

All rules come from the catalog's own flags:

| Catalog | A row is visible when |
|---|---|
| `AI_table_catalog` | `is_active AND ai_access_level = 'BOUNDED_READ'` |
| `AI_column_catalog` | its table is visible, `ai_allowed`, and `NOT is_sensitive` |
| `AI_catalog_relationships` | `is_allowed`, and both `left_table` and `right_table` are visible |
| `AI_calculation_catalog` | its `target_table` is visible and `status = 'ACTIVE'` |
| `AI_data_coverage` | its `dataset_name` is visible and that table has `coverage_enabled` |

`documentation_status` (`VERIFIED`, `PARTIAL`, `NEEDS_REVIEW`) is passed through, never used
to hide rows. A `NULL` description is returned as `null`: per `DATABASE_CATALOG.md`, the
meaning is not established and must not be inferred.

### `discover_catalog()`

This tool takes no arguments. For each visible table it returns `table_name`, `description`,
`category`, `grain`, `primary_key_columns`, `time_column`, `entity_column`,
`documentation_status`, `freshness_sla`, `coverage_enabled`, and `available_metadata`
(counts of visible columns, active calculations, and allowed relationships). At most 50
tables are returned, with a `truncated` flag.

### `get_catalog_details(table_names, sections, column_names, entity_ids)`

| Argument | Contract |
|---|---|
| `table_names` | 1–3 unique names matching `^[A-Za-z0-9_]{1,63}$`; must be visible |
| `sections` | 1–4 of `COLUMNS`, `RELATIONSHIPS`, `CALCULATIONS`, `COVERAGE` |
| `column_names` | `null`, or 1–40 names matching `^[A-Za-z0-9_][A-Za-z0-9_ ]{0,62}$` (spaces allowed, e.g. `Investor Type`); narrows `COLUMNS` and `CALCULATIONS` |
| `entity_ids` | `null`, or 1–20 ids matching `^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$` (e.g. tickers); adds per-entity `COVERAGE` rows |

The tool schema is strict and generated from the same Pydantic model that validates the
arguments. Unknown fields are rejected, and invalid input never reaches the database.

What each section returns:

| Section | Source | Fields |
|---|---|---|
| `COLUMNS` | `AI_column_catalog` | `column_name`, `description`, `data_type`, `semantic_type`, `unit`, `nullable`, `is_primary_key`, `source_column_or_expression`, `allowed_aggregations`, `filter_allowed`, `group_by_allowed`, `example_value`, `documentation_status`; grouped by table, in `ordinal_position` order |
| `RELATIONSHIPS` | `AI_catalog_relationships` | `relationship_id`, `left_table`, `left_columns`, `right_table`, `right_columns`, `relationship_type`, `temporal_rule`, `safe_output_grain`, `requires_preaggregation`, `description`, `version` (`left_columns[i]` joins `right_columns[i]`) |
| `CALCULATIONS` | `AI_calculation_catalog` | `calculation_name`, `version`, `target_columns`, `definition`, `required_inputs`, `parameters`, `defaults`, `alignment_rules`, `missing_data_policy`, `output_definition`; `implementation_ref` and `validation_evidence` are omitted to save space |
| `COVERAGE` | `AI_data_coverage` | The `DATASET` row per table, `entity_status_counts` (entity rows grouped by pipeline, verification, and quality status), and the matching `ENTITY` rows only when `entity_ids` is given. It never dumps the ~14k per-ticker rows |

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
- **Row caps:** 150 columns, 100 calculations, 50 relationships, 60 status groups, and 60
  entity rows per call.
- **Payload budget:** the result stays within a 24 KB budget, below the registry's 32 KB
  hard cap. Small sections are filled first. A large `COLUMNS` or `CALCULATIONS` section
  first switches to `detail: "SUMMARY"` (names, definitions, types, units), then truncates,
  always with `returned`, `total_matching`, `truncated`, and a `hint` to narrow with
  `column_names`.
- **Database session:** one read-only transaction per tool call, opened with
  `default_transaction_read_only=on`, `statement_timeout`, and a connect timeout. Database
  errors return a generic `TOOL_ERROR` with no server message or DSN.

### Database access

1. Apply `database/migrations/20260923_001_create_market_ai_catalog_reader.sql`. It creates
   `NOLOGIN` role `market_ai_catalog_reader` with `USAGE` on schema `public` and `SELECT` on
   exactly the five `AI_*` tables. It fails the transaction if that role could read or
   modify any other public table.
2. Run `scripts/provision_market_ai_orc_login.py` with `DATABASE_URL` (admin) and
   `MARKET_AI_ORC_DB_PASSWORD`. It creates or rotates login `market_ai_orc`, a member only of
   `market_ai_catalog_reader`, with `CONNECTION LIMIT 5`,
   `default_transaction_read_only=on`, `statement_timeout=5s`, `lock_timeout=2s`, and
   `idle_in_transaction_session_timeout=15s`. It then verifies that the readable public
   tables are exactly the five catalogs.
3. Set `CATALOG_DATABASE_URL` to the private DSN for `market_ai_orc`
   (`postgres.railway.internal:5432`).

`scripts/inspect_ai_catalogs.py` is a read-only report of catalog structure, visibility
states, sizes, and samples. It works with the `market_ai_orc` login.

### Known catalog gaps

These are observed in the migration seed and reported, not changed:
- `AI_calculation_catalog.definition` is copied from `Feature_Catalog.definition`. The
  separate `Feature_Catalog.calculation` expression is **not** in the AI catalog.
- `AI_column_catalog.example_value` is seeded `NULL` for every row.
- Every seeded column has `ai_allowed = true` and `is_sensitive = false`.

## Currently unavailable capabilities

These are not implemented, and no placeholder pretends they exist: SQL generation or
execution, the SQL Governor, PostgreSQL market-data access, the legacy
`Table_Catalog`/`Column_Catalog`/`Feature_Catalog` catalogs, a Python or DuckDB sandbox, statistical analysis (event study, backtest, regression, HMM,
clustering), web search, RAG or vector search, long-term memory, multi-agent flows, Redis,
frontend, and Telegram.

## Railway deployment

- Service `market-ai-orc` (`41dc17ee-3bac-41ef-90ec-8b9356815c71`) runs in project `lucid-patience`, environment `dev`.
- It is private: `http://market-ai-orc.railway.internal:8080`. There is no public domain.
- Its health check is `/ready`. The start command is
  `uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8080`.
- `OPENROUTER_API_KEY` is a Railway reference to `${{market-ai-backend.OPENROUTER_DEEPSEEK}}`,
  so rotating that key updates both services.
- A future backend caller should reference `${{market-ai-orc.MARKET_AI_ORC_API_KEY}}` rather
  than copying it.
- It is currently deployed by local upload
  (`railway up apps/market-ai-orc --path-as-root --service market-ai-orc`). A GitHub `main`
  source with watch path `/apps/market-ai-orc/**` is not connected yet.

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

The tests mock all HTTP traffic and make no OpenRouter calls. The catalog integration tests
in `tests/test_catalog_postgres.py` run only when `ORC_TEST_POSTGRES_URL` points to a
disposable PostgreSQL server:

```bash
ORC_TEST_POSTGRES_URL=postgresql://postgres@127.0.0.1:55432/postgres python -m pytest
```

They create a temporary database from the exact DDL in
`20260922_001_create_ai_catalogs.sql`, apply the reader-role migration and the provisioning
script, and drop everything afterwards.
