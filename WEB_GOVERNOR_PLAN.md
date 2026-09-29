# Web Governor plan

Planned work for `market-web-governor` and its consumers. **Status per item below.** P1–P4 were implemented on 2026-09-28 (see `apps/market-web-governor/README.md`); what remains open is listed per item. Each item needs
the user's go-ahead before it runs; record the implementation in `RAILWAY_CHANGELOG.md`, `DATABASE_CHANGELOG.md` and
`ERRORS_AND_SOLUTIONS.md` as usual. Current behaviour is described in `apps/market-web-governor/README.md`.

Status values: `PLANNED` (agreed, not started), `DRAFT` (proposal awaiting a decision).

## P1 — Web research store in a separate PostgreSQL (one table) — IMPLEMENTED (writer: market-web-governor, not AI-Orc, by decision of 2026-09-28)

Decisions of 2026-09-28:

- **Database:** a dedicated PostgreSQL service, `Postgres-E8GM` (service `4b193143-be17-456b-bc00-c1760ef5db82`,
  volume `postgres-volume-Oz3T` / `c02c7422-019d-448e-a4fc-561bcad4a3f0`, environment `dev`), created by the user. It
  is **not** merged with the existing market-data PostgreSQL. No credentials of that database are shared with it.
- **One table.** Its grain is one row per news or event item, because a research agent must later query items by
  ticker and date (event markers) and a JSONB array inside a card row cannot be queried well. Card-level fields are
  repeated on each row of a card (a card has at most about ten items).

### Table `web_event_item`

| Group | Column | Type | Meaning |
|---|---|---|---|
| Identity | `item_id` | `text` PK | `item_<uuid>` |
| | `card_id`, `card_rank` | `text`, `int` | Answer card it belongs to and its position (NULL when not shown on a card) |
| | `event_cluster_id` | `text` | Same real-world event across several articles (e.g. every report of the 18 Sep 2026 deal) |
| Card | `question`, `verdict`, `verdict_label`, `summary`, `limitations` | `text`, `text` CHECK, `text`, `text`, `jsonb` | Card header, repeated per row; `summary` is interpretation |
| Subject | `tickers` | `text[]` | e.g. `{ULTJ}` |
| | `entities` | `jsonb` | Other parties (FrieslandCampina, Frisian Flag Indonesia) |
| Dates | `event_date`, `event_date_precision` | `date`, `text` | When the event happened or was announced; precision `DAY`, `MONTH`, `QUARTER`, `YEAR` |
| | `published_at`, `published_at_source` | `timestamptz`, `text` | Publication time and where it was read: `PROVIDER`, `HTML_META`, `JSON_LD`, `URL`, `TEXT`, `UNKNOWN` |
| | `retrieved_at` | `timestamptz` | When the service read the source |
| Anchor (precursor mode) | `anchor_event_date`, `temporal_status`, `lead_time_days`, `relation_to_anchor` | `date`, `text`, `int`, `text` | `PRE_EVENT`, `POST_EVENT_RETROSPECTIVE`, `UNDATED`; `DIRECT`, `INDIRECT`, `CONTEXT`, `COUNTER` |
| Source | `publisher`, `url`, `domain`, `source_tier` | `text` | `OFFICIAL`, `TRUSTED_MEDIA`, `OTHER_MEDIA`, `UNVERIFIED` |
| | `source_verified`, `source_note` | `bool`, `text` | FALSE for a blocklisted or copying source, noted "Sumber ini belum diverifikasi" |
| | `quote`, `content_sha256` | `text`, `text` | Verbatim excerpt and its hash |
| | `evidence_id`, `citation_id`, `web_need_id` | `text` | Audit link to the Web Governor (kept 30 days there) |
| Importance (P4) | `event_type`, `impact_level`, `impact_direction`, `impact_scope`, `novelty`, `certainty`, `materiality_metric`, `materiality_value`, `impact_rationale`, `impact_confidence`, `rubric_version` | see P4 | AI assessment, always labelled as interpretation |
| Review | `review_status`, `reviewed_by`, `reviewed_at`, `review_note` | `text`, `text`, `timestamptz`, `text` | `UNREVIEWED`, `CONFIRMED`, `OVERRIDDEN` |
| Provenance | `model_slot`, `model`, `locale`, `created_at`, `record_version` | | Who produced the row and when |

Rules:

- **Writer:** AI-Orc writes the rows with an INSERT-only grant on this database. The Web Governor keeps no database
  credentials.
- **Immutable rows:** a correction is a new row. Only the review columns may be updated, by a separate review role.
- **Evidence:** every row must have a `quote` that equals a stored excerpt (or a sub-span of it) of its `evidence_id`.
- **Market data:** comparing items with market data is not part of the first version. `event_date` and `ticker` are
  stored so a research agent can later use the rows as important-event markers.

### Records the change needs

- A migration set of its own for the new database.
- A schema document.
- Catalog rows. The existing `Table_Catalog` lives in the other database, so the catalog location is to be decided.
- `PROJECT_CONTEXT.md` identities.
- `.railway/railway.ts`.

## P2 — Default source policy — IMPLEMENTED (blocklist starts empty; copy detection active)

Requested 2026-09-28: add a default blocklist and a standard trusted-source list for Indonesian equity research,
applied when a request gives no domain lists of its own. Both lists become configuration (not code), reported in
`requested_policy` / `applied_policy`.

- **Primary (official) additions** to the built-in list (`idx.co.id`, `ojk.go.id`, `bi.go.id`, `bps.go.id`, `*.go.id`):
  `ksei.co.id` (was classed SECONDARY in the live test, W07), `kppu.go.id`, and each issuer's own investor-relations
  domain when the request names the issuer.
- **Trusted media (initial list, for the user to confirm):**
  - Indonesian business press: `bisnis.com`, `kontan.co.id`, `cnbcindonesia.com`, `kompas.com`, `katadata.co.id`,
    `investor.id`, `idxchannel.com`, `idnfinancials.com`, `tempo.co`, `antaranews.com`;
  - English-language press and deal outlets: `thejakartapost.com`, `reuters.com`, `bloomberg.com`,
    `bloombergtechnoz.com`, `dealstreetasia.com`, `asia.nikkei.com`, `ft.com`, `wsj.com`.
- **Blocklist:** start from sources that republish other outlets' text.
  - The governor flags a citation whose excerpt is a verbatim copy of an excerpt from another domain in the same run
    (`COPY_OF`, keeping the earliest original).
  - Domains flagged repeatedly are proposed for the blocklist; the user approves each addition.
  - No outlet is blocklisted on reputation alone.
- **Blocklisted sources stay in the results** (decision of 2026-09-28): they are not dropped. They are marked
  `source_verified = false` with the note "Sumber ini belum diverifikasi", and never count as a trusted or official
  source for coverage.

## P3 — Pre-event indicator analysis ("precursor" research) — IMPLEMENTED (market-data comparison still out of scope)

Question shape: *"Find indications, before ULTJ announced the Frisian Flag acquisition, that it would happen."* The
current contract finds the event itself; this needs evidence **dated before** an anchor event, and has to resist
hindsight.

### Contract changes (WebNeedSpec v1 → additive fields)

- `analysis_mode`: `EVIDENCE` (today) or `EVENT_PRECURSOR`.
- `anchor_event`: `description`, `event_date` (T0, e.g. 2026-09-18), and optionally `evidence_ids` that establish it.
- `lookback`: start of the search window, e.g. T0 − 24 months; evidence must be **published before T0**.
- `indicator_categories`: the hypothesis template; each category becomes one or more criteria. For an acquisition:
  - **Seller side:** strategic review, divestment or restructuring statements, impairments, leadership changes.
  - **Buyer side:** cash build-up, capital plans, AGM agenda items (authorised capital, rights issue),
    management remarks on inorganic growth, a halted buyback.
  - **Existing ties:** co-manufacturing, supply or distribution agreements, shared shareholders, board overlaps.
  - **Regulatory and filings:** merger notifications, affiliated-transaction or material-information disclosures.
  - **Media:** "people familiar with the matter" reports, analyst notes.
  - **Market behaviour:** abnormal price, volume or broker accumulation, and IDX unusual-market-activity notices.
    This category comes from Saniti's own market data, not from the web (see "Division of work").

### Evidence changes

- `published_at` must be verified. The governor reads it from the provider, the page's HTML meta or JSON-LD, the URL
  (`/2026/09/18/`, `20260918`) or the text. It records `published_at_source` and a confidence level. This also closes
  W07.
- `temporal_status`:
  - `PRE_EVENT`: published before T0.
  - `POST_EVENT_RETROSPECTIVE`: published after T0 and describing an earlier signal.
  - `UNDATED`.
- Only `PRE_EVENT` evidence can support an indicator. A retrospective article is a lead that needs a dated pre-event
  source.
- The provider's date filters (Exa `startPublishedDate` / `endPublishedDate`) are passed when OpenRouter supports them;
  this is not verified yet. The governor filters by date after retrieval in any case.
- `relation_to_event`:
  - `DIRECT`: names the deal.
  - `INDIRECT`: consistent with the deal but does not name it.
  - `CONTEXT`.

### Output

- A `timeline` sorted by verified date. Each entry carries:
  - category and relation;
  - `lead_time_days` (T0 − published date);
  - evidence IDs;
  - the model's interpretation, labelled as interpretation.
- `earliest_direct_signal` and `earliest_indirect_signal`, or `NOT_FOUND`.
- `counter_indications`: signals that pointed elsewhere (another buyer, denials).
- A hindsight warning: an indirect signal is shown as consistent with the event, not as proof that it was predictable.

### Flow

1. **Plan:** the model proposes indicator hypotheses per category without searching; the user approves.
2. **Retrieve:** date-bounded searches run per hypothesis; key documents are fetched governor-side, with verified
   quotes.
3. **Assemble:** the governor builds the timeline deterministically from verified dates; the model writes only the
   labelled interpretation.

### Division of work

- **Web Governor:** web evidence and its timeline.
- **AI-Orc:** compares the timeline with price, volume and broker data before T0 through the SQL Governor, and writes
  the answer card (P1).
- The Web Governor keeps no market-data access.

### Estimated cost

About 6 categories × 1–2 searches plus 2–4 fetches ≈ USD 0.10–0.30 per analysis at current prices.

### Decisions (2026-09-28)

- **Lookback:** 12 months by default.
- **Market data:** comparing with price, volume and broker data is not in the first version. Every indicator is
  stored in `web_event_item` with its dates (P1) for later use.
- **DIRECT signals:** may come from any source as long as the source tier is labelled.
- **Output:** the timeline format was approved, without icons or emoji.

## P4 — Event importance classification — IMPLEMENTED (golden set and human review queue still to build)

Each stored item gets an AI assessment of how important the event is. The assessment follows a fixed rubric; it is
never a free opinion.

### Columns (in `web_event_item`)

| Column | Values | Meaning |
|---|---|---|
| `event_type` | `M_AND_A`, `CHANGE_OF_CONTROL`, `CAPITAL_RAISE`, `DIVIDEND`, `BUYBACK`, `EARNINGS`, `GUIDANCE`, `MANAGEMENT_CHANGE`, `CONTRACT`, `PARTNERSHIP`, `REGULATORY`, `LEGAL`, `RATING`, `CORPORATE_GOVERNANCE`, `OPERATIONS`, `MARKETING`, `MARKET_ACTIVITY`, `MACRO`, `OTHER` | What happened |
| `impact_level` | 1–5 (`NOISE`, `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`) | Importance for the issuer's shareholders under the rubric |
| `impact_direction` | `POSITIVE`, `NEGATIVE`, `MIXED`, `UNCLEAR` | For existing shareholders; `UNCLEAR` when the source does not decide it |
| `impact_scope` | `ISSUER`, `GROUP`, `SECTOR`, `MARKET` | Who is affected |
| `novelty` | `NEW`, `UPDATE`, `REPEAT` | A repeat of an earlier event keeps that event's level |
| `certainty` | `OFFICIAL`, `REPORTED`, `RUMOUR`, `UNVERIFIED` | How established the fact is |
| `materiality_metric`, `materiality_value` | e.g. `TRANSACTION_TO_EQUITY_PCT`, `178.24` | Numeric anchor, only from numbers in the quote |
| `impact_rationale` | text (≤ 400 characters) | Short reason that names the rubric rule and the quote |
| `impact_confidence` | `HIGH`, `MEDIUM`, `LOW` | Confidence in the assessment |
| `rubric_version` | e.g. `idx-event-rubric-v1` | Rubric used; scores are comparable only within one version |

### Decisions (2026-09-28, second round)

- **Model:** the classifier uses MiMo V2.5 (model slot 2).
- **`impact_direction`:** not shown to users, because it can read as investment advice. Whether it is stored for
  internal use only, or dropped, is decided at implementation.
- **Prompt:** the system prompt must be general (no company, sector or real case in it), yet precise enough that the
  task is unambiguous.

### Where it runs, and who guarantees the table

A separate classification step after retrieval, not inside the search call. It reads only the stored quotes of one
event cluster. The model never writes to the database and does not need to know the table:

- **Code fills** the identities, ticker, URL, publisher, quote, hashes, dates and `published_at_source`,
  `temporal_status`, `lead_time_days`, source tier and `source_verified`, model, `rubric_version` and timestamps.
- **The model fills one small form:** `event_type`, `impact_level`, `impact_scope`, `novelty`, `certainty`,
  `materiality_metric`/`materiality_value`, `impact_rationale` (with a rubric rule ID) and `impact_confidence`.

Four layers guarantee what reaches the table:

1. **Structured output:** a JSON schema with enumerations (MiMo supports structured outputs on OpenRouter).
2. **Server validation before insert:**
   - reject unknown values or unknown rubric rule IDs;
   - reject a `materiality_value` that cannot be computed from numbers in the quote.
   - After one retry the row is stored as `UNCLASSIFIED`, never filled with a guess.
3. **Database constraints:** CHECK constraints on every enumerated column, NOT NULL on required columns, and an
   INSERT-only role for AI-Orc.
4. **Tests:** schema and validator unit tests, and a golden-set run on every rubric or model change.

### System prompt design (`idx-event-rubric-v1`, general)

- **Principles, not examples.** Every event is judged on the same five questions:
  - **control:** does it change who controls the company or its capital structure?
  - **scale:** size relative to the company, from numbers in the quotes only;
  - **permanence:** permanent or one-off?
  - **certainty:** official, reported by media, or rumour?
  - **novelty:** new, update or repeat?
- **Levels 1–5** are defined by combinations of these answers, not by named companies or sectors.
- **Market thresholds are parameters,** outside the prompt text: e.g. the OJK material-transaction thresholds for IDX,
  to be confirmed. Another market means other parameters, not a new prompt.
- **Calibration examples are synthetic** ("Company A announces …"). They cover every level and event type and the
  hard cases: rumour, repeat, missing numbers, conflicting sources.
- **Real cases are used only in the golden set** that tests the prompt; they are never put in it.

### Review

- **Model check:** items at level 4–5 are re-classified by a second model (slot 1). A disagreement marks the row
  `NEEDS_REVIEW`.
- **Review queue:** `UNCLASSIFIED` rows also go to the queue.
- **Human review:** the user reviews only that small queue, occasionally; overrides are kept and feed the next rubric
  version. No routine review of every item in the first version.

### Quality control

- **Golden set:** about 30 hand-labelled items from IDX news, measured before and after every rubric change.
- **Acceptance:** exact agreement on level of at least 70%, and never more than one level off.
- **Human review:** a reviewer can confirm or override (`review_status`). Overrides feed the next rubric version.

### Open questions

- Confirm the OJK material-transaction thresholds before the rubric parameters are set.

## P5 — `/v1/ask`: implications and what to watch — IMPLEMENTED (PR #33/#34, live 2026-09-29)

**Why.** An answer that only lists news is information, not something a reader can use. Benchmarks (Axios "Why it
matters / What's next", sell-side research with scenarios and dated catalysts, ICD-203 signposts, and grounded-LLM
practice of separating facts from inference) all put the consequence and the next events next to the facts, and
keep them visibly apart from the facts.

**User decisions.** No "key judgments" section. Implications are generated separately from the factual answer and
labelled as analysis. No buy/sell recommendation.

**Design.**
- One extra model call after the answer (about USD 0.005 and 5–10 s), with a strict JSON schema; code renders it as a
  section "Implikasi & yang perlu dipantau" and stores it with the answer (`plan.implications`, no table change).
- Content:
  1. **Impact:** who or what is affected (sectors, listed companies, assets such as the rupiah or government bonds),
     the direction, and the channel (for example excise → selling price → volume). Each point must cite at least
     one listed source; code rejects points whose citations do not exist.
  2. **Scenarios** (only for forward-looking questions): base / bull / bear, each with its trigger.
  3. **What to watch:** upcoming events or data, with the date when a source states one (for example the next BI
     board meeting, the parliament's budget vote, a rating review). Dates come only from sources; otherwise
     "tanggal belum diumumkan".
- Every point is labelled as analysis; weak evidence must be said so in the point itself.

**Verification.** Unit tests for the schema, citation checks and rendering; live runner test with the fiscal,
CLARITY Act and Cimory questions; record in `RAILWAY_CHANGELOG.md`.

## P6 — `/v1/ask`: upcoming news and a forward timeline — IMPLEMENTED (PR #33/#34, live 2026-09-29; timeline relevance and date check W17/W18)

**Why.** A test on "apa rencana CMRY ke depan … timeline-nya" returned a mostly backward-looking timeline and missed
2027 events that Google News does have (sweetened-drink excise approved for 2027, five integrated livestock zones due in
2027), and it listed 2025 profit as a 2026 target. Direct Google News probes with forward-looking terms return many
relevant sector items ("industri susu 2027": 23 of 35 titles forward-looking; "cukai MBDK 2027": 22 of 38).

**User decisions.** AI-written forward queries and hardcoded templates **run together**; the templates can be switched
off. The AI writes **10** forward queries.

**Design.**
- Plan schema gains a required `forward_queries` field (up to 10): upcoming events about the subject and its sectors
  (plans, targets, schedules, pending rules, votes, launches, deadlines), in the terms and language of the topic.
- Templates run alongside for the subject and each sector: `"<x> rencana <next year>"`, `"<x> akan berlaku"`,
  `"<x> jadwal"`, `"<x> target <next year>"`. Settings: `WEB_ASK_FORWARD_TEMPLATES` (default on) and
  `WEB_ASK_FORWARD_TEMPLATE_LIST` (optional, `|`-separated, placeholders `{x}` and `{next_year}`). With templates off and
  no AI queries, one fallback `"<subject> <next year>"` runs.
- **Turn order (user decision of 2026-09-29):**
  - **Turn 0, backward:** the subject's queries over 8 three-month windows (two years back from the question date)
    plus Exa for the first two.
  - **Turn 1, forward:** the 10 AI forward queries and the templates, for the subject and its sectors, over the two
    newest windows only (about 44 Google News requests at most). Turns 0 and 1 run in parallel, because both only need
    the plan.
  - **Turn 2, wider (guaranteed by code):** `"<sector>"`, `"<sector> regulasi pemerintah"` and the review's proposals,
    over 8 windows. The review call already sees the forward headlines.
  - **Turn 3, optional:** up to 3 deeper queries from the review, or none.
  - Each query is labelled in `plan.turns` (`backward`, `forward: ai`, `forward: template`, `wider`, `review`).
- Source budget: backward (turn 0) at least 50%, forward (turn 1) at least 20%, wider turns the rest; unused shares pass
  over; within each group the share is spread across the 3-month windows.
- The P5 implications call also returns a **forward timeline**: event, time as written in the source, status
  (`dijadwalkan` / `direncanakan` / `diusulkan` / `masih dikaji`) and source. Code keeps an entry only if its time text
  appears verbatim in the cited source's title or excerpt and lies after the question date; entries are sorted by
  time, undated ones marked "tanggal belum diumumkan".
- Official calendars (IDX disclosures, KSEI, BI) are not reachable from the agent container (IDX 403, KSEI/BI no
  route); schedules are taken from news that announces them until access from Railway or a data API is confirmed.

**Estimate.** Per question about +USD 0.005–0.01, +20–44 Google News requests, +10–20 s.

**Verification.** Unit tests for forward queries (AI, templates, switch, fallback), two-window scan, 50/20/30 budget
and timeline date checks; live runner test with the CMRY forward question, the CLARITY Act and the Indonesian fiscal
question; record in `RAILWAY_CHANGELOG.md`.
