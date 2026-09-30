# Market Web Governor

`market-web-governor` is Saniti's private, provider-neutral web evidence service. It accepts an explicit research
intent from an orchestrator, compiles that intent into bounded provider operations, stores the exact evidence it
returns, and reports criterion-level coverage. It does not decide the user's investment conclusion and does not
receive hidden model reasoning.

The Railway service stays on the private network; it has no public domain.

The first adapter uses OpenRouter's Responses API with the `openrouter:web_search` and `openrouter:web_fetch` server
tools. Provider details remain behind the internal adapter interface so callers depend only on the v1 Saniti
contract.

## Lean ask (`POST /v1/ask`), recommended path

One question in, one cited answer out. It runs next to the older web-need flow (kept for comparison until the lean
path is accepted) and shares only the OpenRouter provider with it.

```
question -> plan     1 model call: 2-4 keyword queries (question language and English; a listed company by its
                     name and ticker), the subject (short name) and its 1-2 sectors, up to 10 forward queries
                     (upcoming plans, schedules, pending rules), optional period; history = true for questions
                     on whether/when something happened (pernah, kapan, sejak, terakhir kali, ...) with up to 2
                     earlier names of the subject
         -> turn 0   backward (code): subject queries x 8 three-month windows (two years back from the question
                     date) on Google News, Exa for the first two; a history question: the same 8 windows plus 5
                     one-year windows (years 3-7 back), earlier names included
         -> turn 1   forward (code, runs with turn 0): the AI forward queries plus templates for the subject and
                     each sector ("{x} rencana {next_year}", "{x} akan berlaku", "{x} jadwal",
                     "{x} target {next_year}"; WEB_ASK_FORWARD_TEMPLATES, WEB_ASK_FORWARD_TEMPLATE_LIST) over the
                     two newest windows; forward queries naming a past year are dropped
         -> turn 2   wider (guaranteed by code): "<sector>" and "<sector> regulasi pemerintah" first, then the
                     review call's proposals (max 5 queries)
         -> claims   the plan also lists 3-8 points the answer must cover; every review marks each point covered
                     (with headline numbers), missing, or not_in_news (allowed from turn 4)
         -> turn 3   optional: up to 3 deeper queries from the review call, or none
         -> turn 4+  only while points are missing, up to WEB_ASK_MAX_TURNS (default 8); the search stops at the
                     first of: all points settled (from turn 3), two reviews without new evidence (saturated), no
                     new queries, or a hard limit of the search phase: WEB_ASK_MAX_NEWS_REQUESTS (300),
                     WEB_ASK_MAX_COST_USD (0.30), WEB_ASK_MAX_SECONDS (180). The reason is in plan.stop; evidence
                     headlines are always kept in the final sources; the answer gets the checklist and lists
                     unsettled points under "Tidak terjawab"; plan.claims keeps status and citation numbers
                     (history questions: a review query may name an older year; it is then searched in that year's
                     four quarters, the drill-down)
         -> merge    code: dedupe by headline; WEB_ASK_MAX_SOURCES (default 500): backward at least 50%, forward
                     at least 20%, wider the rest (unused shares pass over), each spread across the windows
         -> read     1 model call picks up to WEB_ASK_READ_ARTICLES (default 12, 0 = off) headlines whose full
                     text matters most (conflicting figures, latest facts); one Exa search per chosen title fetches
                     its text (kept only when the result's title matches); listed with up to 2,500 characters
         -> answer   1 model call with reasoning on (WEB_ASK_ANSWER_REASONING, default on): only from the numbered sources, investor-material first, industry & policy
                     section, labelled inferences; a period in the question limits the answer; differing figures
                     about one thing are explained (what each measures, denied or replaced, latest confirmed)
         -> implications  1 model call (strict JSON): impacts (affected, direction, channel), scenarios for
                     forward-looking questions, and a forward timeline of scheduled/planned/proposed actions about
                     the subject or its sector (no forecasts, nothing already done); code keeps an item only if its sources
                     exist, and a timeline entry only if its time text is written in a cited source and lies after
                     the question date; rendered as "Implikasi & yang perlu dipantau" (IMPLICATIONS_FAILED keeps
                     the answer when this call fails)
         -> check    code: every ISO date on a cited line must be a cited source's date (else corrected or
                     removed, DATE_CORRECTED); `answer` without [n] and without repeated date markers, `answer_cited` renumbered 1..k, `citations` with the same numbers;
                     `plan.implications` keeps the structured items
```

Measured locally on 2026-09-29 for "kenapa saham ptro naik 1 tahun terakhir": 3 turns, 80 Google News requests
(no rate limiting), 500 sources from 2024-09-25 to 2026-09-29, 31 s, USD 0.031.

- **Request:** `{"request_id": "...", "question": "apa keputusan BI rate terakhir", "as_of": null, "model_slot": null}`.
  `as_of` defaults to today; `model_slot` to the default slot.
- **Response:** `status` (`ANSWERED`, `NO_SOURCES`, `FAILED`), `answer`, `citations` and `sources`
  (`n`, `date`, `publisher`, `title`, `url`, `via`), `plan`, `warnings`, `usage` (model calls, search calls, cost),
  `seconds`, `stored`. `plan.windows` lists the search windows and `plan.turns` each turn's queries, reasons and
  number of Google News requests. The same `request_id` returns the stored answer without new calls.
- **Why this shape:** OpenRouter's web search has no publication-date filter and lets the model write the query
  (W16). Google News returns a date for every headline, so ordering by date lets the model answer "latest" and
  "before event X" questions without special modes.
- **Storage:** one row per question in `web_ask` on Postgres-E8GM (`event_store/002_web_ask.sql`), kept
  `WEB_ASK_RETENTION_DAYS` (default 30); each write deletes expired rows. A failed write keeps the answer and adds
  `ASK_STORE_WRITE_FAILED`.
- **Limits:** the Google News RSS feed is unofficial and may change or rate-limit; a paid Google News API (Serper,
  SerpAPI) or Brave News can replace `google_news()` without changing the flow.

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
| `GET /v1/evidence/{evidence_id}` | Read one persisted evidence record, with its full stored excerpt. |
| `GET /v1/documents/{document_id}` | Read one document the governor fetched: metadata, hashes and extracted text. |
| `POST /v1/search` | Fast path: create and execute a single-criterion web need. |
| `POST /v1/fetch` | The governor downloads one exact public HTTPS URL, a model reads it, and only verified quotes become evidence. |

`POST /v1/web-needs` (inside `web_need`), `POST /v1/search` and `POST /v1/fetch` accept an optional `model_slot`
(1–7). Without it the default slot is used. The slot and its model are recorded in the plan when the need is created,
so a later configuration change does not alter an approved plan.

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
  `EXACT_FETCH_NOT_OBSERVED`, `PROVIDER_SEARCH_LIMIT_EXCEEDED`, `EVIDENCE_BUDGET_REACHED` and `RESPONSE_COMPACTED`; and
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

The response is bounded independently of provider context. When it must be compacted, only the response copy of an
excerpt is shortened; the stored evidence keeps the full excerpt.

## Provider behavior

The OpenRouter adapter uses one provider request per criterion and asks for at most one server-side search
(`max_uses: 1`). The provider does not always honour that: the 2026-09-28 live test saw 2 to 4 searches per request.
The governor then warns `PROVIDER_SEARCH_LIMIT_EXCEEDED` with the reported count (ERRORS_AND_SOLUTIONS W08); the
request count, result count per search and evidence count stay bounded by the service. It passes hard
domain filters and result limits to `openrouter:web_search`, then enforces domain policy again on returned citations.
Document-type and source-tier preferences are reported as `BEST_EFFORT` when the provider cannot guarantee them.
The default engine is Exa because it supports explicit result and domain constraints. The deprecated `web` plugin
and `:online` model suffix are not used.

## Exact-URL fetch

`/v1/fetch` no longer relies on a provider fetch tool (it returned no citations, ERRORS_AND_SOLUTIONS W03):

1. The governor downloads the URL itself: HTTPS only; every DNS answer, including after each redirect, must be a
   public address; at most `WEB_FETCH_MAX_REDIRECTS` redirects and `WEB_FETCH_MAX_BYTES` bytes; HTML, PDF (first
   `WEB_FETCH_MAX_PDF_PAGES` pages, via `pypdf`) and plain text.
2. The extracted text (up to `WEB_FETCH_MAX_CHARACTERS`) is stored with the SHA-256 of the downloaded bytes and of
   the text, the final URL, HTTP status and media type (`GET /v1/documents/{document_id}`).
3. The model receives the first `WEB_FETCH_MODEL_CHARACTERS` characters with no web tool and returns ASSESSMENT,
   SUMMARY and QUOTE lines.
4. A quote becomes evidence (`excerpt_kind` `VERIFIED_QUOTE`, with `document_id`, `quote_start`, `quote_end`) only if
   it appears verbatim in the stored text (whitespace- and typography-insensitive). Others are discarded with
   `QUOTE_NOT_IN_SOURCE`.

Other outcomes: `SOURCE_HTTP_ERROR`, `SOURCE_TIMEOUT`, `SOURCE_TOO_LARGE`, `PRIVATE_ADDRESS_BLOCKED`,
`UNSUPPORTED_CONTENT_TYPE`, `PDF_UNREADABLE`, `DYNAMIC_PAGE_OR_EMPTY` (no model call), `REDIRECTED_TO_OTHER_DOMAIN`,
`DOCUMENT_TRUNCATED` and `DOCUMENT_TRUNCATED_FOR_MODEL`. A script-rendered page is not executed.

## Pre-event (precursor) analysis

`web_need.analysis_mode = "EVENT_PRECURSOR"` looks for signals **published before** an anchor event:

- `anchor_event`: `description`, `event_date` (T0), optional `tickers`; `lookback_months` (default 12).
- The window is T0 − lookback to T0 − 1 day.
- Without criteria, a general template is used; it names no company, sector or deal type beyond the anchor
  description:
  - `direct_reports`
  - `party_intentions`
  - `capital_and_governance`
  - `existing_ties`
  - `filings_and_regulators`
  - `counter_indications`
- The template needs `budget.max_searches >= 6` (`PRECURSOR_BUDGET_TOO_LOW`).
- **Dates.** Every evidence item gets `published_at`, `published_precision` and `published_at_source`. The date is
  read, in order of preference, from provider metadata, page metadata, the URL, or a dateline in the text.
- **Timing.** Each item gets a `temporal_status`:
  - `PRE_EVENT` only when the whole publication period ends before T0, with `lead_time_days`;
  - `POST_EVENT_RETROSPECTIVE`: published on or after T0;
  - `UNDATED`.
- **Timeline.** The response carries a deterministic `timeline`:
  - `pre_event` sorted by date;
  - `earliest_direct_signal`, `earliest_indirect_signal`;
  - `counter_indications`, `retrospective_leads`, `undated`;
  - a note that an indirect signal does not show predictability.

## Importance classification

When `web_need.classify` is true (the default for `EVENT_PRECURSOR`), every evidence item is classified by the
classifier slot (`WEB_CLASSIFIER_SLOT`) with a strict JSON-schema structured output. Items that cite the same URL share one
classification, and several sources are classified per call.

- **Source of truth:** the rubric (`app/rubric.py`, `idx-event-rubric-v1`). It is general: five questions (control,
  scale, permanence, attribution, novelty), rule IDs per level 1–5, a dictionary of event types, attributions,
  novelty, scope, relation to the anchor and materiality metrics, and synthetic calibration examples. Market
  thresholds are parameters (`WEB_RUBRIC_MATERIAL_PCT`, `WEB_RUBRIC_CRITICAL_PCT`).
- **Server validation** rejects an answer that:
  - does not match the schema;
  - has a level that differs from its rule;
  - has a materiality figure absent from the quote;
  - applies a scale rule without a stated figure;
  - has inconsistent date or anchor fields.

  After one retry the item is `UNCLASSIFIED`, never guessed.
- **Decided by code, not the model:**
  - `certainty`: `OFFICIAL` for a primary source; `REPORTED` for attributed media; `RUMOUR`; `UNVERIFIED` for a
    blocklisted or copied source;
  - the cap for rumours and unverified sources: level at most 4, confidence at most `MEDIUM`.
- **Second check:** items at level 4–5 are re-classified by `WEB_CLASSIFIER_CHECK_SLOT`; a different level sets
  `review_status = NEEDS_REVIEW`.
- `impact_direction` is not produced.

## Source policy defaults

- **Official:** `idx.co.id`, `ojk.go.id`, `bi.go.id`, `bps.go.id`, `ksei.co.id`, `kppu.go.id`, `sec.gov`, every
  `*.go.id` and `*.gov`, and the request's `primary_domains`.
- **Trusted media:** a built-in Indonesian and international list (`app/sources.py`), plus `WEB_TRUSTED_MEDIA_EXTRA`
  and the request's `trusted_secondary_domains`.
- **Blocklist** (`WEB_SOURCE_BLOCKLIST`): blocklisted sources are **kept**. They are marked `source_verified = false`
  with the note "Sumber ini belum diverifikasi", and do not count towards coverage.
- **Copies:** an excerpt that repeats another domain's text word for word is marked the same way, with `copy_of`.

## Event store (Postgres-E8GM)

With `WEB_EVENT_STORE_URL` set, every completed search, web need or fetch writes one row per evidence item to
`web_event_item` in the separate research database Postgres-E8GM (`event_store/001_web_event_item.sql`).

- **Lean ask:** `/v1/ask` answers go to `web_ask` (`002_web_ask.sql`); on that table the writer also has SELECT
  (replay) and DELETE (30-day retention).
- **Access:** the governor's role `web_event_writer` can only INSERT (`ON CONFLICT DO NOTHING` without a conflict
  target, so no SELECT is needed); `web_event_reader` can only SELECT. The market-data PostgreSQL is not reachable
  from this service.
- **Content:** rows carry the card fields, dates and anchor timing, source tier and verification, the quote and its
  hash, the classification and the review status.
- **Failure:** a failed write keeps the response and adds `EVENT_STORE_WRITE_FAILED`.

## Evidence budget

The evidence budget is shared across criteria in turn, so an early criterion cannot use all of it; a citation already
kept for another criterion is linked again without using budget. When the response must be compacted, excerpts are
shortened only in the response (`TRUNCATED_IN_RESPONSE`, `NOT_INCLUDED_IN_RESPONSE`); the store keeps the full
excerpt. `RESPONSE_BUDGET_EXCEEDED` reports a response that stays above its budget even without excerpts.

Known open limits from the 2026-09-28 live test: `/v1/search` always requires two
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
- `WEB_OPENROUTER_MODEL=deepseek/deepseek-v4.1-flash` (model slot 1 unless `WEB_SLOT_1_MODEL` is set)
- `WEB_OPENROUTER_ENGINE=exa`
- `WEB_OPENROUTER_TIMEOUT_SECONDS=90` (an 8,000-token answer needs more than 40 s)
- `WEB_OPENROUTER_MAX_OUTPUT_TOKENS=8000` (includes reasoning tokens; default for every slot)
- `WEB_MAX_CRITERIA=6`
- `WEB_MAX_SEARCHES=6`
- `WEB_MAX_RESULTS_PER_SEARCH=30`
- `WEB_MAX_EVIDENCE_ITEMS=40`
- `WEB_MAX_OUTPUT_CHARACTERS=64000`
- `WEB_MAX_EXCERPT_CHARACTERS=5000`
- `WEB_RETENTION_HOURS=720` (30 days)
- `WEB_CLEANUP_INTERVAL_SECONDS=3600`

Model slots (1–7): `WEB_SLOT_<n>_MODEL`, `_LABEL`, `_ENABLED` (default true when a model is set),
`_MAX_OUTPUT_TOKENS` (256–8000, default `WEB_OPENROUTER_MAX_OUTPUT_TOKENS`), `_REASONING_EFFORT`
(`minimal`, `low`, `medium`, `high`; unset sends no reasoning parameter) and `_ENGINE`; `WEB_DEFAULT_SLOT=1`. Every slot
uses OpenRouter's default provider routing. On dev: slot 1 `deepseek/deepseek-v4.1-flash`, slot 2 `xiaomi/mimo-v2.5`,
slot 3 `z-ai/glm-5.3-flashx`; slots 4–7 are empty.

Classification and event store: `WEB_CLASSIFIER_SLOT` (dev: 2, MiMo), `WEB_CLASSIFIER_CHECK_SLOT` (dev: 1; 0 disables),
`WEB_CLASSIFIER_WORKERS=4`, `WEB_CLASSIFIER_MAX_OUTPUT_TOKENS=3000`, `WEB_CLASSIFY_DEADLINE_SECONDS=420`,
`WEB_OPENROUTER_TOTAL_SECONDS=180` (total per provider call, W13), `WEB_STALE_RUNNING_SECONDS=1800`,
`WEB_CLASSIFIER_BATCH_SIZE=6` (distinct sources per call), `WEB_CLASSIFIER_REASONING_EFFORT=off` (reasoning disabled; `none` sends no parameter), `WEB_DATE_LOOKUP_MAX=15`
(undated pages read for their own date in pre-event mode, W14), `WEB_RUBRIC_MATERIAL_PCT=20`, `WEB_RUBRIC_CRITICAL_PCT=50` (to be confirmed against the
current OJK rules), `WEB_EVENT_STORE_URL` (secret; writer role only), `WEB_SOURCE_BLOCKLIST`, `WEB_TRUSTED_MEDIA_EXTRA`.

Fetch limits (defaults): `WEB_FETCH_TIMEOUT_SECONDS=20`, `WEB_FETCH_MAX_BYTES=5000000`, `WEB_FETCH_MAX_REDIRECTS=3`,
`WEB_FETCH_MAX_PDF_PAGES=60`, `WEB_FETCH_MAX_CHARACTERS=200000`, `WEB_FETCH_MODEL_CHARACTERS=60000`,
`WEB_FETCH_MAX_QUOTES=8`.

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
