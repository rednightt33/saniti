# Financial terminal — Phase 3 (mapping), Phase 4 (serving layer), Phase 5 (API contract)

Status: **PROPOSED**. Nothing here has been built. Basis: `PHASE1_PHASE2.md` (HTML inspection and live read-only
database inspection, 2026-10-24) and the user decisions in `EXEC.md` (EXEC-TERMINAL-API):

- latency under 5 seconds is acceptable;
- display data is separated from the database the AI uses, through files pre-published in object storage, 5 years,
  with PostgreSQL as the fallback beyond that;
- browsers download those files directly from the bucket through presigned URLs, with safeguards (option B); the
  users are subscribers;
- "Foreign" = source investor type (`investor_type`) everywhere;
- realized volatility for display = log return, 20 sessions, sample (n−1), × √252.

## 1. Phase 3 — UI-to-source mapping matrix

Where a metric is "computed in browser", the browser computes it from the published file of section 3; the formula
is fixed here so the frontend phase implements exactly this.

Abbreviations: P = `public."Price_Stock_Indonesia_IDX"`, F05 = `public."Feature_05_Foreign_Domestic_Broker_Detail"`,
BP = `public."IDX_Broker_Profile"`, U = `public."IDX_Stock_Universe"`.

| Panel | Component | Metric | Source | Columns | Grain | Formula | Filters | Status |
|---|---|---|---|---|---|---|---|---|
| Main | Candles + volume | OHLCV | P (`timeframe='Daily' AND is_final`) | date, open, high, low, close, volume | ticker × date | as stored (not dividend-adjusted, ERRORS D10) | ticker, date range | VERIFIED |
| Main | Timeframe D | daily bars | P | same | ticker × date | — | — | VERIFIED |
| Main | Timeframe W / M | weekly / monthly bars | P | same | ticker × ISO week / month | open = first open, high = max, low = min, close = last close, volume = Σ; partial current period flagged | ticker | DERIVED (browser) |
| Main | Timeframe 5M/15M/1H/4H | intraday bars | — | — | — | — | — | **UNKNOWN — no intraday data exists**; buttons hidden or disabled |
| Main | Compare series (IHSG, tickers) | close rebased | P | date, close | ticker × date | `(close/close_first − 1) × 100`, joined on common dates | tickers | VERIFIED / DERIVED |
| Left | Return distribution | session return | P | close | ticker × date | `r = close_t/close_(t−1) − 1`; mean, median, % `r > 0`, n; histogram binning is UI-only | visible range | DERIVED (browser) |
| Left | Seasonality — month | monthly return | P | date, close | ticker × month | last close of month / last close of previous month − 1, months ending in range; **the current unfinished month is excluded** (proposed fix of S3) | visible range | DERIVED (browser) |
| Left | Seasonality — weekday | avg session return per weekday | P | date, close | weekday | mean `r` per Mon–Fri; a return after a holiday counts on its trading day | visible range | DERIVED (browser) |
| Left | Drawdown | from running peak | P | close | ticker × date | `close/max(close since first visible bar) − 1` | visible range | DERIVED (browser) |
| Left | Realized volatility | 20-session annualized | P | close | ticker × date | `stdev_samp(ln(close_t/close_(t−1)), 20) × √252 × 100`; NULL until 20 returns | visible range (window may reach before the range) | DERIVED (browser) |
| Left | Relative performance | ticker vs IHSG | P (ticker, `IHSG`) | date, close | date | both rebased to the first common visible date; difference in pp; dates present in only one series (IHSG 2026-09-17/18) are skipped | visible range | DERIVED (browser) |
| Left | Volume distribution | volume ÷ 20D avg | P | volume | ticker × date | `v_t / avg(v_(t−19..t))`; NULL for IHSG (no volume) | visible range | DERIVED (browser) |
| Right | Broker summary | buy, sell, net, gross, lot, avg | F05 | date, broker, investor_type, market_board, buy/sell value, buy/sell lots | ticker × date × broker × investor × board | Σ per broker over the range; net = Σbuy − Σsell; gross = Σbuy (buyers) / Σsell (sellers); avg price = value / (lots × 100); lots are decimals (odd lots) | investor All/Foreign/Domestic; board All/Regular/Nego/Tunai (label "Cash" is UI-only); date range | VERIFIED (agg. DERIVED) |
| Right | Broker action gauge | top-5 buy vs sell | F05 | same | range | HTML heuristic | — | **UNVERIFIED** — not shipped until the user approves a definition |
| Right | Top accumulators | net ranking | F05 | same | broker over range | rank by Σ net value (buy: > 0 desc; sell: < 0 asc), All investors, All boards | range (default 5 sessions) | DERIVED (browser) |
| Right | Broker inventory | cumulative net | F05 | same | broker × date | running Σ net lots or net value from the first session of the range, 0 on sessions without rows; labelled "cumulative net transactions", not holdings | 1–5 brokers, unit, range | DERIVED (browser) |
| Right | Bandar detector | verdict, top-N | F05 | same | range | HTML heuristic; "Foreign share of buyers" = Σ net of Foreign investor-type rows of the top-N buyers ÷ Σ net of the top-N buyers (can be < 0 or > 100%) | top 3/5/10, range | **AGREED 2026-10-30** (EXEC-TERMINAL-FLOW-IND): verdict = Bandar Balance · % (FL24), Neutral < 6 %, Acc / Dist from 6 %, Big from 10 %, default Top 3; shown live since the user's "Sekarang." (2026-10-30). "Foreign share of buyers" unchanged |
| Right | Broker tag colour | broker identity | BP | broker_code, broker_name, broker_type | broker | label only, not a figure | — | VERIFIED |
| Bottom | Flow timeline bars | daily net | F05 | same | date | Σ net value of rows passing the filters; 0 on sessions without matching rows | brokers (multi), boards (multi), investor types (multi, default Foreign), range | DERIVED (browser) |
| Bottom | Cumulative line | running net | F05 | same | date | running Σ from the first loaded session; the summary states that start date | same | DERIVED (browser) |
| Bottom | Summary | latest, total, avg | F05 | same | range | avg daily net = total ÷ sessions in range (sessions without rows count as 0) | same | DERIVED (browser) |
| Bottom | "Nets to zero" note | — | F05 `source_balance_gap` | — | date × ticker × board | show only when no row in range has a gap; otherwise state the gap (ERRORS M157) | — | VERIFIED |
| All | Data date | freshness | manifest | `data_through` per dataset | ticker | price and broker dates shown separately (broker ends 2026-08-31, price 2026-10-23) | — | VERIFIED |

## 2. Phase 4 — serving layer

### 2.1 Decision

| Need | Choice | Why |
|---|---|---|
| Price and broker data, last 5 years | **Pre-published files in a new private bucket** (option D-like, physical copy) | User decision: isolate display load from the AI database. Measured cost is low: one active stock-year of broker rows ≈ 250 KB gzip (BBCA 2025: 24,286 rows, 1,522 KB JSON → 251 KB; GOTO 2025: 251 KB); price ≈ 2 KB per stock-year; all stocks' F05 rows in 2025 = 5,348,402 → about 55 MB gzip per year, about 300 MB for 5 years. Storage $0.015/GB-month; bucket egress free. |
| Older than 5 years | **Direct parameterized query** on P and F05 through a dedicated read-only login | Measured < 4 s cold for a whole history (PHASE1_PHASE2 2.4); within the 5 s target. No index needed. |
| Statistics, aggregates, rankings | **Browser** | Computed from the same files; no extra storage; the formulas are fixed in section 1. |
| New tables, views or materialized views in the market database | **None** | The existing P, F05, BP and U have the right grain and keys. |

Rejected: per-ticker tables or views (forbidden, and not needed); a materialized view (no measured bottleneck);
using the AI's `market-sql-datasets` bucket (would mix AI and display data); routing through `market-sql-governor`
(AI-only contract); Parquet in the browser (needs a WASM library; gzip JSON decompresses with the browser's built-in
`DecompressionStream`).

### 2.2 Object layout (bucket `terminal-display`, PROPOSED)

```
v1/manifest/{ticker}.json                 small; never cached long
v1/price/{ticker}/{year}.json.gz          columnar: d, o, h, l, c, v
v1/broker/{ticker}/{year}.json.gz         columnar: d, b, i, m, bv, sv, bl, sl, bf, sf (2026-10-30), gap(date×board list)
v1/ref/brokers.json.gz                    broker_code, broker_name, broker_type
v1/ref/tickers.json.gz                    ticker, company name, security type
```

- One file per ticker-year: the current year changes, past years are immutable unless the source is corrected.
- File names carry no secret; the bucket is private, there is no public read and no list permission for users.
- Manifest per ticker: for each file its key, `sha256`, row count, first/last date, `generated_at`; per dataset
  `data_through`; and `schema_version`.

### 2.3 Publisher (new job, PROPOSED)

- Universe derived at run time: every `U` row with `"Security Type" IN ('stock','index')` (845 today, no hardcoded
  list); broker files for stocks only (F05 has no IHSG rows; the `_INDEX` tables stay out of scope).
- Changes derived from the database, not enumerated: price ticker-years whose `max(ingestion_time)` is newer than the
  manifest; broker ticker-years whose `max(calculated_at)` in F05 is newer than the manifest.
- Runs after `idx-price-cron` (daily) and after a manual Feature 05 refresh; idempotent; writes the data files first
  and the manifest last, so a reader never sees a manifest pointing at a missing file.
- Reads through its own read-only login; writes only to the new bucket.
- Same code covers any future dataset (cross-asset, macro) by adding one dataset definition (source, columns, grain,
  change column); it does **not** fit intraday data (size and constant change).

### 2.4 Staleness

| Data | Fresh after | Shown to the user |
|---|---|---|
| Price | the next publisher run after the daily price cron | `data_through` per dataset |
| Broker | the next publisher run after a **manual** Feature 05 refresh (today ends 2026-08-31) | same, separately |

## 3. Phase 5 — API contract (PROPOSED)

All under `/api/terminal/v1`, JSON, authenticated subscriber session required, dates `YYYY-MM-DD` in the IDX
trading calendar (Asia/Jakarta), money in IDR, lots decimal (1 lot = 100 shares).

| Endpoint | Purpose | Parameters | Response |
|---|---|---|---|
| `GET /tickers` | ticker list | — | presigned URL of `ref/tickers.json.gz` |
| `GET /manifest/{ticker}` | what exists | ticker (must be in U) | manifest JSON (section 2.2) |
| `POST /files` | presigned URLs | `{ticker, dataset: price\|broker, years: [..]}` (max 6 years per call) | `[{year, url, expires_at, sha256, bytes}]` |
| `GET /logo/{ticker}` | logo image (added 2026-10-26, EXEC-TERMINAL-LOGO) | ticker | PNG or SVG, cached a week; 404 when none |
| `POST /bundle` | every file of one ticker (added 2026-10-26, EXEC-TERMINAL-UI-1026 U6) | `{ticker, datasets?}` | manifest window and per dataset the presigned URLs; quota and audit as `/files` |
| `GET /state` | the publication the files belong to (added 2026-10-27, EXEC-BACKTEST-LOAD K1; `xsection` added 2026-10-28, EXEC-SCREENER; `refs` added 2026-10-28, EXEC-MU-RUNTIME T5) | — | `{finished_at, price_through, broker_through, broker_behind_sessions, xsection, refs}`; no file granted, no quota, no audit row (`BACKTEST_END_TO_END.md` §6.2) |
| `POST /xsection` | cross-sectional files for the screener-worker (added 2026-10-28, EXEC-SCREENER P1 a); the screener-worker's service key (EXEC-MU-RUNTIME T1) or, until a later step removes it, the gateway key; any other caller, a subscriber session included, is 403 `gateway_only` | `{names: [..]}` (1-16 names of the `/state` index) | `{finished_at, expires_in_seconds, encoding, files: [{name, url, sha256, bytes, rows, as_of}]}`; one file per name and its bytes against the quota under `REF`, one audit row (dataset `xsection`) |
| `GET /history/price` | fallback > 5 years | ticker, from, to (≤ 10 years) | columnar OHLCV |
| `GET /history/broker` | fallback > 5 years | ticker, from, to (≤ 1 year per call), optional brokers[], investor_type, market_board | columnar F05 rows |

Errors: `400` invalid ticker or range (message names the parameter and the allowed values), `401` no session,
`403` not a subscriber, `404` no data for that ticker/year, `429` quota exceeded (message states the limit and when
it resets), `503` publisher has not produced the manifest.

### 3.1 Safeguards against mass download (user requirement)

| Safeguard | Proposed default (user may tweak) |
|---|---|
| Presigned URL lifetime | 120 seconds |
| URLs per subscriber | 60 files per hour |
| Distinct tickers per subscriber | 30 per hour, 150 per day |
| Bytes per subscriber | 300 MB per day (≈ 1,200 ticker-years of broker data) |
| Fallback queries | 20 per hour |
| Concurrent sessions per account | 2 |
| Audit | every URL issued: subscriber, ticker, file, bytes, time, IP; alert above 80% of a quota |
| Revocation | disable the account → no new URLs; issued URLs die within 120 s |
| CORS on the bucket | `GET` only, origin = the terminal's domain only |

Limits: a subscriber who stays within the quota can still copy what they are allowed to see; the safeguards bound
speed and volume and leave an audit trail. Presigned URLs can be forwarded during their 120 s lifetime.

## 4. Subscriber accounts — option A (user 2026-10-25: "A dulu.")

Accounts are created and disabled by the admin; no self sign-up and no payment yet.

| Item | Proposal (follows the existing `edge_bff` pattern, migration `20261008_002`) |
|---|---|
| Storage | new schema `terminal` in the main PostgreSQL. As built (migration `20261025_100`, first named `20261025_001`): NOLOGIN groups `terminal_runtime` (read/write on `terminal`) and `terminal_market_reader` (SELECT on P, F05, BP, U); logins `terminal_api_login` (both groups, statement_timeout 10s) and `terminal_publisher_login` (market reader only, read-only transactions). |
| Tables | `terminal.subscriber` (id, email unique, display name, password hash `scrypt` like `edge-bff/app/security.py`, `active`, `expires_at`, created/updated), `terminal.session` (token hash, subscriber, expires, revoked; max 2 active), `terminal.url_issue_log` (subscriber, ticker, dataset, year, bytes, ip, issued_at), `terminal.quota_override` (optional per-subscriber limits). |
| Admin | a CLI script `scripts/terminal_subscriber.py add/disable/extend/reset-password/list`, run by the admin with the `terminal_api_login` URL; no admin web page yet. |
| Login | `POST /api/terminal/v1/auth/sign-in` (email + password) → HttpOnly Secure cookie; `sign-out`; `change-password`. A subscriber is allowed only while `active AND expires_at > now()`. |
| Service | new Railway service `terminal-api` (FastAPI, `apps/terminal-api`), separate from `edge-bff` (single owner, different users) and from the AI services. |

Other gaps:
1. Approval of a definition for the Broker action gauge and the Bandar detector, or they stay hidden.
2. Full reconciliation F05 vs `IDX_Broker_Summary` over all dates (open item from Phase 2).

## 5. Implementation plan (after approval only)

| Step | Change | Rollback | Compatibility |
|---|---|---|---|
| 1 | New private bucket `terminal-display` + CORS rule (GET, terminal origin only) | delete the bucket | existing buckets untouched |
| 2 | Forward migration: schema `terminal`, its tables, groups `terminal_runtime`, `terminal_market_reader`; logins `terminal_api_login`, `terminal_publisher_login` | forward migration dropping them | no existing object changed |
| 3 | Publisher job (`apps/terminal-publisher`) + initial 5-year backfill; each file checked against SQL (row count, Σ value per ticker-year) | delete objects / service | reads only from PostgreSQL |
| 4 | `apps/terminal-api` service: auth, manifest, presigned URLs, fallback history, quotas, audit | remove the service | EDGE and AI unchanged |
| 5 | Admin CLI, first test subscriber | disable the account | — |
| 6 | Phase 7 validation (reconciliation, filters, quotas, CORS from a browser, errors, timings) | — | — |

Every step records its migration, `DATABASE_CHANGELOG.md`, `RAILWAY_CHANGELOG.md` and live read-back per `AGENTS.md`.
