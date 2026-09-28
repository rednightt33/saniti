# Web Governor plan

Planned work for `market-web-governor` and its consumers. **Nothing in this file is implemented yet.** Each item needs
the user's go-ahead before it runs; record the implementation in `RAILWAY_CHANGELOG.md`, `DATABASE_CHANGELOG.md` and
`ERRORS_AND_SOLUTIONS.md` as usual. Current behaviour is described in `apps/market-web-governor/README.md`.

Status values: `PLANNED` (agreed, not started), `DRAFT` (proposal awaiting a decision).

## P1 — Answer cards in PostgreSQL (one table) — PLANNED

Requested 2026-09-28: a consistent, retrievable format for research answers shown to users, stored in PostgreSQL in
one table.

### Table `Web_Answer_Card`

One row per answer card. The evidence shown on the card is an ordered JSONB array inside the row, so the card is one
table and one read.

| Column | Type | Meaning |
|---|---|---|
| `card_id` | `text` PK | `card_<uuid>` |
| `created_at` | `timestamptz` | When the card was written |
| `conversation_id`, `run_id` | `text` | AI-Orc conversation and research run that produced it |
| `web_need_id`, `web_run_id` | `text` | The Web Governor research behind it (audit link; the Web Governor keeps 30 days) |
| `question` | `text` | The question as shown to the user |
| `verdict` | `text` + CHECK | `CONFIRMED`, `PARTIAL`, `NOT_FOUND`, `CONTRADICTED`, `BLOCKED` |
| `verdict_label` | `text` | User-facing label, e.g. "Terkonfirmasi (rencana, belum selesai)" |
| `first_known_date` | `date` NULL | Earliest verified public date, when the question asks for one |
| `summary` | `text` | Model interpretation, always shown as interpretation |
| `limitations` | `jsonb` | Array of strings |
| `evidence` | `jsonb` | Ordered array: `rank`, `evidence_id`, `citation_id`, `source_type` (`OFFICIAL`, `TRUSTED_MEDIA`, `OTHER_MEDIA`), `publisher`, `published_date`, `published_date_source`, `quote`, `url`, `retrieved_at`, `content_sha256` |
| `other_source_count` | `integer` | Sources not shown on the card |
| `model_slot`, `model` | `integer`, `text` | Model that produced the research |
| `locale` | `text` | e.g. `id-ID` |
| `card_version` | `integer` | Format version (starts at 1) |

Rules:

- **Writer:** AI-Orc writes the table, not the Web Governor. The Web Governor keeps no PostgreSQL credentials. It uses
  an INSERT-only grant, the same pattern as `AI_research_run_audit`. A card is immutable; a correction is a new card.
- **Content:** quotes and URLs are copied into the card, so a card stays readable after the Web Governor's 30-day
  retention; `evidence_id` and `content_sha256` keep the audit link while the evidence exists.
- **Validation:** every evidence entry must name an `evidence_id` from the same `web_need_id`, and its `quote` must
  equal a stored excerpt or a sub-span of it. `summary` is never shown without `evidence`.
- **Retention:** permanent unless the user decides otherwise.

### Records the change needs

- A forward migration.
- `DATABASE_SCHEMA.md`, `DATABASE_CHANGELOG.md`.
- `Table_Catalog` and `Column_Catalog` rows (per `AGENTS.md`).
- The AI-Orc grant and its writer path.
- A read tool, or an endpoint, `get_answer_card(card_id)`.

## P2 — Default source policy — PLANNED

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

## P3 — Pre-event indicator analysis ("precursor" research) — DRAFT

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

### Open questions

- Default lookback: 12 or 24 months?
- Is a market-behaviour comparison wanted in the first version?
- Must a DIRECT signal come from a trusted source?
