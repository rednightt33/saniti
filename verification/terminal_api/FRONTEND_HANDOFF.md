# Financial terminal — frontend integration handoff

Status 2026-10-25: backend live on Railway `dev` (EXEC-TERMINAL-API). This is what the frontend phase may rely on.
Design and decisions: `DESIGN.md`; live evidence: `PHASE1_PHASE2.md`, `INTEGRITY.md`, Phase 7 results in `EXEC.md`.

## 1. How data reaches the page

```
sign in ─► GET manifest/{ticker} ─► POST files {ticker, dataset, years} ─► presigned URLs (120 s)
        ─► fetch each URL directly from the bucket (CORS: terminal origin only) ─► gunzip ─► compute in the browser
older than the published window ─► GET history/price | history/broker (PostgreSQL, bounded)
```

Base URL: `https://terminal-api-dev.up.railway.app/api/terminal/v1`. All JSON. Cookie session (`terminal_session`,
HttpOnly, Secure, SameSite=Lax), so the page must be served from an allowed origin (today
`https://terminal-api-dev.up.railway.app`; another origin needs `TERMINAL_ALLOWED_ORIGINS` and the bucket CORS rule
updated, `scripts/terminal_bucket_cors.py`). Every POST must carry the page's `Origin` (browsers do this).

## 2. Endpoints

| Method and path | Body / query | Answer |
|---|---|---|
| `POST /auth/sign-in` | `{email, password}` | sets the cookie; `401 sign_in_failed`, `403 subscription_inactive`, `429 too_many_attempts` |
| `POST /auth/sign-out` | — | clears the session |
| `GET /auth/session` | — | `{email, display_name, subscription_expires_at}` or `401` |
| `POST /auth/change-password` | `{current_password, new_password ≥ 12}` | other sessions are signed out |
| `GET /reference/tickers`, `GET /reference/brokers` | — | `{url, expires_in_seconds}` of a gzip JSON list |
| `GET /manifest/{ticker}` | — | window (first/last year), per dataset `data_through` and per year `bytes, rows, first, last, sha256` |
| `POST /files` | `{ticker, dataset: "price"|"broker", years: [≤ 6]}` or `{ticker, dataset: "events"}` (one file, no years) | `files: [{year, url, sha256, bytes, rows}]`, `expires_in_seconds: 120` |
| `POST /bundle` | `{ticker, datasets?: ["price","broker","events"]}` (default all three) | manifest window plus per dataset `{data_through, first_year, files: [{year, url, sha256, bytes, rows}]}`, every published file; counted like `/files` (one entry per file, one quota lock); a dataset the ticker lacks answers `files: []` (section 9) |
| `GET /history/price` | `ticker, from, to` (≤ 3,660 days, only before the window) | columnar `d,o,h,l,c,v` |
| `GET /history/broker` | `ticker, from, to` (≤ 366 days, only before the window), optional `brokers` (≤ 20), `investor_type`, `market_board` | columnar `d,b,i,m,bv,sv,bl,sl,gap` |

Errors are `{"error": code, "message": text}`; `400` invalid input lists `fields`; `429 quota_exceeded` names the
quota and its window. Download URLs expire after 120 s: fetch right after `POST /files`, request again if expired.

## 3. Files (gzip JSON, decompress with `DecompressionStream('gzip')`)

| Dataset | Columns | Units | Notes |
|---|---|---|---|
| price | `d` date `YYYY-MM-DD`, `o h l c`, `v` | IDR per share (index points for IHSG); `v` shares | `v` is `null` for IHSG; prices as stored, not dividend-adjusted |
| broker | `d`, `b` broker code, `i` investor type `Foreign`/`Domestic`, `m` board `Regular`/`Nego`/`Tunai`, `bv sv` IDR, `bl sl` lots | 1 lot = 100 shares; **lots are decimals** (odd lots) | `gap`: `[[date, board], …]` where the source's total buy ≠ total sell (show it; do not claim net-to-zero there) |

| events | `d` date, `role` date role (`EX_DATE`, `MEETING_DATE`, `TRADING_START`, …), `family` (`CORPORATE_ACTION`, `INSIDER`), `type` (`DIVIDEND`, `RUPS`, `WARRANT`, …), `action`, `holder`, `holder_role`, `broker`, `instrument`, `shares_change`, `pct_after`, `pct_change`, `pct_flag`, `price`, `price_estimated`, `value`, `origin` | as stored in `idx_event_annotation` | one file per ticker (`all`), every date; no `source_payload` (corporate-action amounts and ratios are not in the columns) |

One file per ticker and calendar year (events: one per ticker); rows ascending by date (broker: date, broker, investor type, board). Dates
are IDX trading days (Asia/Jakarta); there are no rows for holidays and no row for a broker that did not trade.

## 4. What the frontend computes (formulas fixed in `DESIGN.md` section 1)

Return distribution, seasonality (month excludes the unfinished current month), drawdown from the running peak in the
visible range, realized volatility (`stdev_samp(ln(c_t/c_t-1), 20) × √252 × 100`), relative performance vs IHSG on
common dates, volume ÷ 20-day average, weekly/monthly bars, broker summary (net, gross, avg = value / (lots × 100)),
top accumulators, cumulative net per broker (label it cumulative net transactions, not holdings), flow timeline
(daily net and running sum; sessions without matching rows = 0). "Foreign" always means investor type `i`.
Recommended: one TypeScript calculation module with tests whose expected values come from SQL (as `validate.py` does).

## 5. Not available

- Intraday bars (5M–4H): no data exists.
- Bandar detector and the broker-action gauge: formulas not approved; keep hidden.
- Broker data after 2026-08-31 until Feature 05 is refreshed (manual today); show each dataset's `data_through`.
- IHSG broker data (none exists); transaction frequency (not published; can be added).

## 6. Limits per subscriber (table `terminal.quota`, changeable without code)

URL lifetime 120 s; 60 files/hour; 30 distinct tickers/hour, 150/day; 300 MB/day; 20 history queries/hour;
2 sessions; session 24 h; 10 failed sign-ins per email (30 per IP) in 15 min.

## 7. Through EDGE (T4, 2026-10-25)

The Terminal tab (`/terminal` in EDGE, page `/terminal-app/`) does not sign in to terminal-api itself: the page calls
`/api/terminal/v1/{manifest/T, reference/tickers|brokers, files, history/price|broker}` on edge-bff with the EDGE
session (POST also with EDGE's CSRF token), and edge-bff forwards them over the private network with
`X-Terminal-Proxy-Key`; terminal-api treats them as the one account `TERMINAL_PROXY_SUBSCRIBER` (quotas, audit).
Auth and admin routes are not forwarded. The presigned downloads go straight from the page to the bucket (CORS lists
`https://edge-bff-dev.up.railway.app`). Price files start in 2018 (first stored year); broker files in 2021.

## 8. Since 2026-10-26 (EXEC-TERMINAL-T7-T10)

- Broker files start at the first stored trade date (2016), like price (2018); each dataset's `first_year` is in the
  manifest.
- Events format 2: two more columns. `title` (e.g. "Stock split 1 : 5", "Cash dividend") and `detail` =
  `[[label, value or null, kind], …]` for corporate actions (null for insider rows), built from `source_payload`
  (ERRORS M223). `kind` ∈ `idr`, `idr_per_share`, `date`, `text`, `pct`, `shares`. A null value means the source has no
  value; the page shows "Unavailable". Derived rows: dividend yield = dividend ÷ close on the cum date × 100; price
  after a split = close on the cum date × old ÷ new; tender premium = offer price ÷ close of the last session before the
  offer start (within 10 days) − 1. A cum date not traded yet (a future event) has no close, so these rows are null.

## 9. Since 2026-10-26 (EXEC-TERMINAL-UI-1026)

- `POST /bundle` gives every published file of the displayed ticker in one call (13 API calls per ticker became 4:
  session, two references, bundle). The page asks for the remembered ticker's bundle together with the ticker list.
- One Web Worker (`src/data/worker.ts`) downloads, inflates and parses the files and builds the broker structures; it
  answers in stages: price (the chart is drawn), broker (Flow Timeline), events (markers). Side panels start closed in
  live mode (the user's last choice is remembered); Broker activity is filled when opened, IHSG (Statistics, Relative
  performance) is asked for only when that section draws.
- The page fills its frame (`html.fit`): chart 70 : Flow 30 of the column, Flow 180–346 px, the dragged split kept as a
  ratio (`ml.flow.ratio`); on a frame under 650 px the Flow Timeline starts folded. `?fixture=reference` keeps the
  reference's fixed heights for the 1:1 check (`&fit=1` shows the fixture in the new layout).
- Flow figures (live): "Period net total" and "Avg daily net" cover the chart's visible range (like Statistics); each
  figure has an info mark. Right-click on the Flow Timeline: "Reset chart view" (its value scales only). Event labels
  write dates as "03 December 2025".
- Broker dates without a price row are not on the chart's sessions and are not counted in Flow (ERRORS M238).
