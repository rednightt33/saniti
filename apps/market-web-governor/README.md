# Market Web Governor

`market-web-governor` is Saniti's private, provider-neutral web evidence service. It accepts an explicit research
intent from an orchestrator, compiles that intent into bounded provider operations, stores the exact evidence it
returns, and reports criterion-level coverage. It does not decide the user's investment conclusion and does not
receive hidden model reasoning.

The Railway service stays on the private network; it has no public domain.

The first adapter uses OpenRouter's Responses API with the `openrouter:web_search` and `openrouter:web_fetch` server
tools. Provider details remain behind the internal adapter interface so callers depend only on the v1 Saniti
contract.

## Boundaries

- Input is a `WebNeedSpec`: objective, optional hypothesis statement, entities, time window, evidence criteria,
  source policy, budgets, and stop conditions.
- Each criterion is searched independently. This preserves the link from hypothesis criterion to provider call,
  evidence, citation, coverage, and final downstream use.
- Search prompts explicitly request supporting and contradicting evidence. Page content is treated as untrusted data.
- The service returns source records and coverage. A caller decides whether to refine the need or synthesize an
  answer.
- The service has no PostgreSQL credentials and no access to Saniti market-data tables.

## API

All `/v1/*` endpoints require `Authorization: Bearer $WEB_GOVERNOR_API_KEY`.

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Process liveness. |
| `GET /ready` | SQLite evidence-store readiness. |
| `GET /v1/capabilities` | Contract versions, operations, features, adapter versions, and hard limits. |
| `POST /v1/web-needs` | Validate and persist a v1 `WebNeedSpec`; return the planned criterion tasks. |
| `POST /v1/web-needs/{web_need_id}/execute` | Execute the approved tasks and return structured evidence. |
| `GET /v1/web-needs/{web_need_id}` | Read the plan or terminal execution response. |
| `GET /v1/evidence/{evidence_id}` | Read one persisted evidence record. |
| `POST /v1/search` | Fast path: create and execute a single-criterion web need. |
| `POST /v1/fetch` | Fetch one exact public HTTPS URL through the provider adapter. |

### WebNeedSpec example

```json
{
  "contract_version": "v1",
  "request_id": "run-123",
  "conversation_id": "conversation-123",
  "web_need": {
    "objective": "Verify whether the issuer raised its 2026 capital-expenditure guidance.",
    "hypothesis": {
      "hypothesis_id": "hyp-capex",
      "statement": "The issuer raised capex guidance.",
      "falsification_test": "The latest issuer filing keeps or lowers the prior guidance."
    },
    "entities": [
      {"entity_type": "ISSUER", "entity_id": "EXAMPLE", "aliases": []}
    ],
    "time_window": {"start": "2026-01-01", "end": "2026-09-28", "as_of": "2026-09-28"},
    "evidence_standard": "PRIMARY_REQUIRED",
    "criteria": [
      {
        "criterion_id": "latest-guidance",
        "question": "What capex guidance appears in the latest issuer filing?",
        "required": true,
        "direction": "BOTH",
        "minimum_sources": 1,
        "preferred_source_tiers": ["PRIMARY"],
        "document_types": ["issuer filing"],
        "inclusion_terms": ["capital expenditure", "guidance"],
        "exclusion_terms": []
      }
    ],
    "source_policy": {
      "profile": "FINANCIAL_PRIMARY",
      "minimum_primary_sources": 1,
      "minimum_independent_sources": 1,
      "allowed_domains": [],
      "excluded_domains": [],
      "primary_domains": ["example.co.id"],
      "trusted_secondary_domains": []
    },
    "budget": {
      "max_searches": 1,
      "max_results_per_search": 5,
      "max_evidence_items": 5,
      "max_output_characters": 16000
    },
    "stop_conditions": {
      "all_required_criteria_covered": true,
      "stop_on_primary_source": true
    },
    "locale": "id-ID",
    "timezone": "Asia/Jakarta"
  }
}
```

The execution response contains:

- `status`: `EVIDENCE_READY`, `PARTIAL`, `BLOCKED`, or `FAILED`;
- `requested_policy`, `applied_policy`, and `unapplied_constraints` so provider limitations are not silent;
- one coverage row per criterion: `SATISFIED`, `PARTIAL`, `NOT_FOUND`, `CONTRADICTED`, or `BLOCKED`;
- evidence records with stable `evidence_id` and `citation_id`, canonical URL, source tier, retrieval time, excerpt kind,
  and SHA-256;
- provider call count, usage totals (`web_search_requests`, `tool_calls_observed`, tokens, cost), and
  `execution.provider_calls`: per call its status (`SUCCEEDED`, `INCOMPLETE`, `FAILED`), the provider response status,
  incomplete reason, output item types, annotation count and usage, without any response body;
- `warnings`, among them `PROVIDER_OUTPUT_INCOMPLETE`, `CITATIONS_REJECTED_BY_POLICY`, `EXACT_URL_NOT_CITED`,
  `EXACT_FETCH_NOT_OBSERVED`, `EVIDENCE_BUDGET_REACHED` and `RESPONSE_COMPACTED`; and
- `next_action`: `SYNTHESIZE`, `REFINE_WEB_NEED`, `RETRY_PROVIDER`, or `REVIEW_FETCH`.

Coverage never rests on text the service could not verify:

- A provider response that is incomplete (for example `max_output_tokens`) or lacks the labelled ASSESSMENT and
  SUMMARY lines gives the criterion `BLOCKED` with gap `PROVIDER_OUTPUT_INCOMPLETE`; a blocked required criterion
  makes `next_action` `RETRY_PROVIDER`.
- A supporting, contradicting or mixed summary without any recorded evidence is withheld (gap `NO_USABLE_CITATION`).
- The model's `summary` is interpretation. Confirmed facts are the stored excerpts behind `evidence_ids`.

## Storage and idempotency

SQLite stores web needs, provider calls, evidence, and criterion-to-evidence lineage at
`WEB_GOVERNOR_STORE_PATH`. Railway mounts the service-specific `market-web-governor-data` volume at `/data`; the
default database path is `/data/web-governor.sqlite3`. `RAILWAY_RUN_UID=0` lets the process write to Railway's
root-owned mount. The evidence store survives container restarts and redeploys.

`request_id` is the idempotency key. Reusing it with the exact same normalized request returns the stored plan or
terminal response. Reusing it with different content returns HTTP 409 `IDEMPOTENCY_CONFLICT`. Evidence is persisted
before a terminal response is returned.

The model-facing response is bounded independently of provider context. Excerpts are shortened before persistence
when required to meet the requested response budget, so the stored excerpt always matches what the caller received.

## Provider behavior

The OpenRouter adapter uses one provider request and at most one server-side search per criterion. It passes hard
domain filters and result limits to `openrouter:web_search`, then enforces domain policy again on returned citations.
Document-type and source-tier preferences are reported as `BEST_EFFORT` when the provider cannot guarantee them.
The default engine is Exa because it supports explicit result and domain constraints. The deprecated `web` plugin
and `:online` model suffix are not used.

`/v1/fetch` records evidence only from a citation of the requested URL. OpenRouter's `openrouter:web_fetch` tool
currently returns no URL citations, so an exact fetch reports `EXACT_URL_NOT_CITED`, withholds the provider summary and
returns `REVIEW_FETCH` (ERRORS_AND_SOLUTIONS W03). Known open limits from the 2026-09-28 live test: the output budget
of 1800 tokens is too small for this model's reasoning in multi-search criteria (W02); `/v1/search` always requires two
distinct domains (W06); citations carry no publication date and evidence has no per-item stance (W07).

The adapter accepts both documented OpenRouter citation shapes and ignores unknown response fields. Provider errors
are normalized without response bodies, headers, or credentials. HTTP 429 and 5xx responses use bounded retries.

## Environment

Required:

- `WEB_GOVERNOR_API_KEY` — service bearer key, at least 32 characters.
- `OPENROUTER_API_KEY` — OpenRouter credential owned by this service at runtime.

Configured on Railway:

- `PORT=8080`
- `WEB_PROVIDER=openrouter`
- `WEB_GOVERNOR_STORE_PATH=/data/web-governor.sqlite3`
- `WEB_OPENROUTER_MODEL=deepseek/deepseek-v4.1-flash`
- `WEB_OPENROUTER_ENGINE=exa`
- `WEB_OPENROUTER_TIMEOUT_SECONDS=40`
- `WEB_MAX_CRITERIA=6`
- `WEB_MAX_SEARCHES=6`
- `WEB_MAX_RESULTS_PER_SEARCH=5`
- `WEB_MAX_EVIDENCE_ITEMS=20`
- `WEB_MAX_OUTPUT_CHARACTERS=32000`
- `WEB_MAX_EXCERPT_CHARACTERS=2500`
- `WEB_RETENTION_HOURS=168`
- `WEB_CLEANUP_INTERVAL_SECONDS=3600`

No request can raise the service's configured hard limits.

## Local verification

```bash
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest -q
docker build -t market-web-governor .
```

Tests cover authentication, strict contracts, idempotency conflicts, hard budgets, URL safety, citation
normalization, evidence persistence, and criterion coverage.
