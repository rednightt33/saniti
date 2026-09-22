# market-ai-orc

Phase 1 AI orchestration service. It receives an AI request from a trusted backend,
calls OpenRouter, runs registered tools when the model asks for them, and returns a
validated structured response.

It was derived from `apps/market-ai-backend`. It keeps that service's proven OpenRouter
Responses transport, bounded retry, quota handling, usage accounting, strict final-schema
validation with bounded retries, and bounded agent loop. It removes everything tied to
market data: PostgreSQL, catalogs, SQL governance, query sandbox, statistical worker,
S3 snapshots, evidence and completion gates, and analysis routing.

`market-ai-orc` has **no database credentials, no bucket credentials, and no market-data
access**. It is stateless: the caller owns conversation persistence.

## Architecture

Current (Phase 1):

```text
Backend
   ↓  POST /v1/agent/run  (Bearer MARKET_AI_ORC_API_KEY)
market-ai-orc
   ↓  POST https://openrouter.ai/api/v1/responses
OpenRouter → AI model
   ↓  optional function_call
market-ai-orc executes a registered tool → function_call_output
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
| `get_system_capabilities` | none | `{"database_query": false, "python_analysis": false, "web_search": false, "available_tools": ["get_system_capabilities"]}` |

Each capability flag is derived from the registry. It becomes `true` only when its providing
tool (`request_data`, `run_python_analysis`, `search_web`) is actually registered.

## Currently unavailable capabilities

These are not implemented, and no placeholder pretends they exist: SQL generation or
execution, the SQL Governor, PostgreSQL market-data access, Feature/Table/Column catalogs,
a Python or DuckDB sandbox, statistical analysis (event study, backtest, regression, HMM,
clustering), web search, RAG or vector search, long-term memory, multi-agent flows, Redis,
frontend, and Telegram.

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

The tests mock all HTTP traffic and make no OpenRouter calls.
