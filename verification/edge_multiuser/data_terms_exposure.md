# EDGE-MULTIUSER: data terms, exposure and privacy for external users

Area: the data EDGE shows or computes from, what the repository says about each source's terms, what each screen exposes
(raw or derived), what an external user can export, the questions to settle with the data providers, and the personal
data EDGE would hold per user. READ-ONLY: no repository edit, no git change, no Railway mutation, no database write.
Live reads on 2026-10-28: database through `pgq2.py` (role `pgweb`, read-only, bounded SELECTs), Railway variable
NAMES only (`railway variables --json`, keys printed, values never read out).

Labels: FACT (file:line, query or command), INFERENCE, PROPOSED, UNKNOWN. No legal conclusion is drawn anywhere: where the
repository is silent on a source's terms, the item is UNKNOWN and becomes a question for the user and the provider.

Basis: user decision P29, 2026-10-28, "External / Ini termasuk tab2 lagi ya monitor, terminal, backtest juga"
(`EXEC.md` EXEC-SCREENER); `PLAN.md:912-927` (EDGE-MULTIUSER lists "izin data untuk tampilan ke user eksternal (harga,
broker summary Stockbit, corporate action, insider)" as an open question); `EXEC.md:8517-8518` ("Belum diketahui, harus
dijawab sebelum user eksternal: izin data"); report 6d row E6 / M-U6 (`verification/screener/AUDIT.md:2135`). Identity,
roles, sessions and per-user isolation are covered by the sibling file
`verification/edge_multiuser/identity_sessions_per_user_state.md`;
this file only refers to it.

---

## 1. Dataset inventory

### 1.1 Market data from TradingView

| # | Dataset | How it is pulled (FACT) | Stored in (FACT) | What the repository says about terms |
|---|---|---|---|---|
| T1 | IDX stock and IHSG daily OHLCV | `idx-price-cron` (17:00 WIB) and `idx-price-recovery-cron` (06:00 WIB) open `wss://data.tradingview.com/socket.io/websocket` with `Origin: https://www.tradingview.com` and `set_auth_token ["unauthorized_user_token"]`, so no TradingView account is used (`apps/idx-price-cron/price_update.py:32-33, 263`; schedule `apps/idx-price-cron/README.md:9-12`). IHSG is `IDX:COMPOSITE` (same README, "Candle-date" section) | `Price_Stock_Indonesia_IDX`: 1,331,548 final daily rows, 845 tickers, 2018-01-02 to 2026-10-28 (query, 2026-10-28) | FACT: `EXEC.md:8190-8193` (EXEC-MCAP): prices are pulled "tanpa akun lewat endpoint tidak resmi; TradingView tidak memberi izin tertulis untuk pengambilan otomatis ... Risiko lisensi sama dengan harga sekarang, ditambah bila market cap ditampilkan ke pengguna EDGE". Nothing else in the repository on TradingView's terms, or on IDX (the exchange) as the owner of the prices: UNKNOWN |
| T2 | Fixed income (48 series: Indonesian and US government benchmark yields and prices, `TVC:` symbols such as `TVC:ID10Y`) | four `fixed-income-*` crons, same websocket and anonymous token (`apps/fixed-income-price-cron/fixed_income_update.py:32-33, 187`); symbols from `Universe_Fixed_income` (48 rows, query) | `Price_Fixed_Income` (~121,649 rows est.), view `Price_Fixed_Income_Final` | None found (grep of all `*.md` for licen*/terms/redistribut*/lisensi): UNKNOWN |
| T3 | Market cap, share counts, free float (planned, EXEC-MCAP "menunggu go") | TradingView quote session on the same socket (`EXEC.md:8152-8270`) | not stored yet | FACT: same lines `EXEC.md:8190-8193`: fundamentals come from third-party suppliers of TradingView; licence risk named |
| T4 | Logo SVGs (fallback) and `logoid` list | `terminal-publisher` POSTs `scanner.tradingview.com/indonesia/scan` with columns `name, logoid` and fetches `s3-symbol-logos.tradingview.com/{logoid}--big.svg` (`apps/terminal-publisher/publisher.py:143-144, 158-173`) | bucket `terminal-display` `v1/logo/{ticker}.svg`, `ref/logos.json.gz` | See logos, section 1.4 |

### 1.2 Market data from Stockbit

| # | Dataset | How it is pulled (FACT) | Stored in (FACT) | Terms in the repository |
|---|---|---|---|---|
| S1 | Broker summary (per symbol, date, broker, investor type, board: buy/sell value and lots, avg prices, buy/sell frequency) | `exodus.stockbit.com`: `/marketdetectors/{symbol}` (`apps/stockbit-updater/broker_import.py:129`), `/order-trade/broker/activity` and `/findata-view/marketdetectors/brokers` (`apps/stockbit-broker-backfill/stockbit_marketwide_broker_activity.py:34, 258, 295`; `apps/stockbit-updater/stockbit_ihsg_daily.py:162, 194`), with browser headers `Origin`/`Referer: https://stockbit.com` (`stockbit_ihsg_daily.py:114-115`). Credential: `STOCKBIT_TOKEN`, "the user's JWT" (`apps/stockbit-updater/README.md`, Variables), i.e. one personal Stockbit account; the user replaces it to start a round (`UPDATE_TABLE.md:18-21`; user's words `FUTURE_PLAN.md:713`). Raw responses kept on the service volume `RAW_RETENTION_DAYS=3` (README Variables) | `IDX_Broker_Summary` ~45.07 M rows (reltuples); historical backfill to 2018-01-01 (`PROJECT_CONTEXT.md:99-103`). Derived: Feature 02, 03, 05, 06 and the `_INDEX` tables. FACT: `Feature_05_Foreign_Domestic_Broker_Detail` has the source's grain (BBCA 2026-10-27: 112 rows in both tables, query) | None found: UNKNOWN |
| S2 | Corporate actions (dividends, splits, rights, tender offers ... with terms) | `exodus.stockbit.com/corpaction/{type}?year=` (`apps/stockbit-event-annotation/stockbit_events.py:5, 25`) | `stockbit_corporate_action` 19,267 rows est.; `idx_event_annotation` 19,266 CORPORATE_ACTION rows, 2003-01-10 to 2026-12-18 (query) | None found: UNKNOWN |
| S3 | Insider and major-holder movements | `exodus.stockbit.com/insider/company/majorholder?symbol=&page=` (`stockbit_events.py:6`) | `stockbit_insider_transaction` ~104,038 rows est.; `idx_event_annotation` INSIDER rows: 22,440 with `data_origin` IDX and 81,597 with KSEI; `holder_name` set on 103,856 rows, 2,212 distinct names (IDX origin) and 3,066 (KSEI origin); roles include DIREKTUR, KOMISARIS, PENGENDALI (query; names not read out) | None found: UNKNOWN. The data originates in IDX and KSEI disclosures (column `data_origin`; quirks in `ERRORS_AND_SOLUTIONS.md` D21) |
| S4 | Logo PNGs (primary) | `assets.stockbit.com/logos/companies/{ticker}.png` (`publisher.py:142, 158`) | bucket `v1/logo/{ticker}.png` | See logos, section 1.4 |

### 1.3 Reference data

| # | Dataset | Origin (FACT from `Table_Catalog.source_system` / `Column_Catalog`, query) | Terms |
|---|---|---|---|
| R1 | `IDX_Stock_Universe` (844 stocks, 1 index): name, TradingView symbol and URL, ISIN, Sector, Industry | "TradingView and curated reference data"; `Sector`/`Industry` = "Source sector classification" without naming the source | Which source the sector classification comes from is UNKNOWN; terms UNKNOWN |
| R2 | `Universe_Equity_Description` (descriptions, `TV_Sector`, `TV_Industry`) | "Universe_Equity_Description.xlsx"; `TV_Sector` = "TradingView sector classification" (`DATABASE_SCHEMA.md:3814`). Not exposed to the AI (not in `scripts/provision_market_sql_governor_login.py:24-34`) | Origin of the xlsx UNKNOWN |
| R3 | `IDX_Broker_Profile` (112 brokers: code, name, Domestic/Foreign, usage profile) | `source_system` empty; `broker_classification` is "User-confirmed meaning" (the user's own label) | Code and name source UNKNOWN; the classification is the user's own work (INFERENCE) |
| R4 | `Equity_Market_Schedule`, `Fixed_Income_Market_Schedule` | "Operator-approved configuration" | Own configuration (INFERENCE: no third-party terms) |

### 1.4 Logos and brand names

- FACT: `FUTURE_PLAN.md:868-870`: "Hak pakai: logo adalah merek emiten; Stockbit dan TradingView menyalinnya untuk layanan
  mereka sendiri, dan menyalin ulang ke layanan berbayar kita perlu dicek terhadap syarat penggunaan masing-masing (belum
  diperiksa)." `idx.co.id` (LogoEmiten) answers 403 to automated access (`FUTURE_PLAN.md:868`).
- FACT: logos are served by terminal-api `GET /logo/{ticker}` with no quota and no audit row (`apps/terminal-api/app/main.py:302-305`).
- FACT: the Screener page names "Stockbit & Ajaib screeners" among its "Preset sources" (`apps/edge-bff/screener/src/preview.ts:192`);
  the Terminal flow chart is documented as working "like Stockbit's F Flow" (`apps/edge-bff/terminal/src/app/flow.ts:183-184`, a code comment).
- FACT: EDGE ships model brand logos (`apps/edge-bff/static/model-logos/`) shown in answers and share cards (`apps/edge-bff/README.md:277`).

### 1.5 AI web results (market-web-governor) and model output

| # | Source | How (FACT) | Kept (FACT) | Terms in the repository |
|---|---|---|---|---|
| W1 | Exa search through OpenRouter (`openrouter:web_search`, engine `exa`) | `apps/market-web-governor/app/ask.py:1046-1047`, `fact.py:267-278`, `orc_web.py:664-675`; `WEB_OPENROUTER_ENGINE` default `exa` (`config.py:221`) | Excerpts and verified quotes: SQLite on the service volume (`WEB_RETENTION_HOURS`, default 168, `config.py:244`; the variable is set on dev, value not read) and Postgres-E8GM `web_event_item` (INSERT-only), `web_fact` 30 days, `web_orc_result` `WEB_ORC_CACHE_DAYS` (default 7, `config.py:294`) (`PROJECT_CONTEXT.md:14`) | None: UNKNOWN |
| W2 | Google News RSS | `news.google.com/rss/search` (`ask.py:404`) | `web_ask` `WEB_ASK_RETENTION_DAYS` default 30 (`config.py:272`; the variable is not set on dev, so 30) | FACT: "the Google News RSS feed is unofficial and may change or rate-limit" (`apps/market-web-governor/README.md:160`). Terms otherwise UNKNOWN |
| W3 | Direct fetch of any public HTTPS document | governor downloads the page itself, User-Agent `SanitiMarketWebGovernor/1.0` (`app/fetcher.py:22, 96-103`); "official" domains idx.co.id, ojk.go.id, bi.go.id, bps.go.id, ksei.co.id, kppu.go.id, sec.gov (`app/sources.py:12`) | stored excerpt (full; the response copy may be shortened, README:288-289) | FACT: no robots.txt handling in `apps/market-web-governor/app` (grep "robots": none). Copyright of quoted news text: UNKNOWN |
| W4 | Model text (answers, summaries, classifications) | OpenRouter: `deepseek/deepseek-v4.1-flash` and the EDGE model choices (`AGENTS.md`, Model and provider; `AI_MODELS.md`) | conversations (section 5) | Output-use terms of OpenRouter and of each model provider: not in the repository, UNKNOWN |

### 1.6 Third-party software and assets on the pages

- FACT: `lightweight-charts` 5.2.1 in Terminal, Backtest and Screener (`apps/edge-bff/{terminal,backtest,screener}/package.json`);
  the bundled header reads "TradingView Lightweight Charts™ v5.2.1, Copyright (c) 2026 TradingView, Inc., Licensed under
  Apache License 2.0" (built `apps/edge-bff/screener/dist/assets/index-BC5I0mTj.js`). Every chart sets `attributionLogo:false`
  (`terminal/src/app/chart.ts:23`, `terminal/src/app/flow.ts:42`, `backtest/src/signals.ts:127`,
  `backtest/src/results/overview.ts:46`, `screener/src/preview.ts:151`). Whether the library's attribution notice is
  given elsewhere on EDGE: not found in the repository, UNKNOWN (`node_modules` is not installed here, so its NOTICE file
  was not read).
- FACT: html-to-image 1.11.13, MIT, with its licence file (`apps/edge-bff/README.md:282`). Google Fonts loaded from
  `fonts.googleapis.com` / `fonts.gstatic.com` (`apps/edge-bff/app/main.py:40-42, 55-56, 262`).

### 1.7 Computed in-house (derived)

Feature 01-06 and their `_INDEX` tables, Feature 04 (57 indicator columns), the Terminal's browser-side statistics
(`verification/terminal_api/DESIGN.md` section 1), the Backtest results, the Screener's 53 indicators and the approved
flow indicators FL01-FL18 (`EXEC.md` EXEC-SCREENER, D1-D14), and AI answers. INFERENCE: every one of them is computed from
T1, S1, S2/S3 or R1-R3, so whatever the providers allow for derived works applies to them; none of the repository's
documents says what that is (UNKNOWN).

---

## 2. Exposure per screen (raw vs derived)

"Raw" = source values at source grain (a price bar, a broker row, an event row). "Derived" = computed by Saniti.

| Screen | Raw data that reaches the user | Derived data | How it reaches the browser (FACT) | Bound per user today (FACT) |
|---|---|---|---|---|
| **Monitor (AI chat)** | Anything the SQL Governor exposes, which includes raw `IDX_Broker_Summary`, `Price_Stock_Indonesia_IDX`, `idx_event_annotation` (holder names), `Price_Fixed_Income_Final`, `IDX_Broker_Profile`, universe history (`scripts/provision_market_sql_governor_login.py:24-34`); 20-row previews and answer tables; web quotes and links | Answers, statistics, research results, charts | Orc answers through edge-bff | One export per table at a time (409 `EXPORT_IN_PROGRESS`, `apps/market-ai-orc/README.md:2420`). No per-user export or data quota found; the sibling file proposes one (R9) |
| **Terminal** | Every published price year (one pack per ticker), broker rows at source grain per ticker-year (`d,b,i,m,bv,sv,bl,sl`), all events of a ticker with holder names (`EVENT_COLUMNS` includes `holder`), ticker and broker reference files, logos (`publisher.py:26-44, 99-101, 657-662`); older dates through `/history/price` and `/history/broker` (`terminal-api/app/main.py:470-491`) | Weekly/monthly bars, returns, seasonality, flow aggregates, broker inventory, indicators, all computed in the browser (`verification/terminal_api/DESIGN.md` section 1) | The browser downloads the gzip JSON files itself from the private bucket through presigned URLs (TTL 120 s), host `*.t3.storageapi.dev` (`main.py` CSP `:40-42`; `terminal/src/data/live.ts:2`) | Per-subscriber quotas exist (60 files/h, 30 tickers/h, 150 tickers/day, 300 MB/day, 20 history queries/h; `database/migrations/20261025_100_create_terminal_schema.sql:78-88`), but every EDGE request uses one gateway subscriber with a TEMPORARY 1e9 override (sibling file 2.6), so today there is no per-EDGE-user bound. `DESIGN.md:133-134`: "a subscriber who stays within the quota can still copy what they are allowed to see" |
| **Backtest** | Candles of the picked stocks in the signal preview (files presigned by `/bundle`, README:36-38) | Signals, trades, equity curve, statistics, trials | edge-bff relays the private backtest-worker; previews download rack files in the browser | 3 queued jobs per owner (`BACKTEST_QUEUED_PER_OWNER`, README table); one running job per owner |
| **Screener** | Cross-section of last close, 1-day change, ADV20, name, sector and industry for the universe; the last 260 OHLCV bars of a previewed ticker (`screener/src/core/contract.ts:322-335`) | 53 indicator values, VALUE/STATE/EVENT statuses, ranks, near misses, flow indicators (Phase 2) | The page reads no rack file; every answer comes from `/api/v1/screener` (`apps/edge-bff/README.md:127-129`); the worker reads the cross-sectional files once per publication with the gateway key under the `REF` quota (`terminal-api/app/main.py:418-428`) | INFERENCE: Screener reads by users are not counted against any terminal-api quota (the worker fetches once for everyone). Per-user compute limits are being built (P33); whether they also bound how many tickers' bars one user can preview is not stated (UNKNOWN) |

---

## 3. What an external user could export (FACT unless labelled)

| Screen | Export | Content | Size bound |
|---|---|---|---|
| Monitor | Table download (XLSX) of an answer table | every row of the kept table, the shown columns, plus definition, lineage and **input sheets** (the raw rows the analysis read) (`apps/market-ai-orc/README.md:2412-2420`) | input sheets together at most 200,000 rows (`apps/market-python-sandbox/app/stored_tables.py:115`); a file at most 20 MB (`stored_tables.py:22`) |
| Monitor | `export_result` tool: CSV, XLSX or Parquet of an output (`AI_ENABLE_EXPORT` is set on dev; value not read) | an analysis output (`README.md:2408-2411`) | 20 MB |
| Monitor | Share card: PDF, PNG, Word | one answer with its tables, footer "Not investment advice" (`apps/edge-bff/README.md:273-287`; `static/edge-labels.js:113`) | one card |
| Terminal | "Copy the table as CSV" in the broker summary pop-out | per broker: buy lots/value/avg, sell lots/value/avg, net value/lots, share, and the total (`terminal/src/app/popout.ts:134-137, 251-253`) | one period's table |
| Terminal | the raw files themselves | INFERENCE: the gzip JSON files land in the browser and its cache (`terminal/src/data/rack.ts:7`), so a user with developer tools holds them; the quota is the only bound and today it is the shared 1e9 override | quota |
| Backtest | Trade list CSV | ticker, entry/exit date and price, shares, days, return, P&L, MAE, MFE, exit reason (`backtest/src/results/list.ts:14`) | one result |
| Screener | Results CSV (all visible rows or the selected ones) | metadata lines (screen, evaluation date, publication, versions, definition hash) and per row symbol, name, sector, industry, last, 1D %, ADV20, status, and per condition its value, status, event date, bars ago and remark; formula-injection guard (`screener/src/csv.ts:1-4, 30-52`) | the screen's rows |

FACT: grep of `static/edge-labels.js`, `static/index.html` and the three page sources found no data-source attribution
(no "Data: TradingView" or "Sumber: Stockbit"), no terms of use and no privacy notice; the only user-facing notice is the
share card footer "Not investment advice".

---

## 4. Questions to settle with the data providers before external users (UNKNOWN until answered)

Each answer decides, per source, one of: may be shown raw / only derived / only to the owner / not at all, and with what
attribution. None is answered anywhere in the repository.

**TradingView (T1-T4, chart library)**
1. Is automated access to the websocket and the scanner without an account permitted at all (`EXEC.md:8190-8193` says no
   written permission exists)?
2. May end-of-day OHLCV of IDX stocks, IHSG and the `TVC:` bond series be stored and shown to external, possibly paying,
   users? Raw bars (Terminal, Screener preview, AI input sheets), or derived values only?
3. May derived values (indicators, screens, backtests) computed from those bars be shown and exported?
4. Market cap, share counts and free float (EXEC-MCAP): the fields come from third-party suppliers; may they be shown?
5. Logo SVGs: may they be copied and served?
6. Lightweight Charts: with `attributionLogo:false` on every chart, how is the attribution the library expects given?
7. If not permitted: which licensed source replaces it (an IDX data vendor or TradingView's commercial data offering)?

**Stockbit (S1-S4)**
1. Does Stockbit allow data pulled with one personal account's token to feed a service used by other people?
2. Broker summary: may it be shown at source grain (Terminal broker files, AI input sheets, Terminal CSV), or only as
   derived flows? History back to 2018?
3. Corporate actions and insider movements: may they be redistributed? With holder names?
4. Derived "bandarmology" metrics (flow indicators FL01-FL18) and the wording "like Stockbit's F Flow" or "Stockbit & Ajaib
   screeners" in the page.
5. Logos (PNG): may they be copied and served?
6. Volume and frequency of pulls; is there an official API or data licence for this use?

**IDX (Bursa Efek Indonesia), the owner of the market data, and KSEI**
1. Does showing end-of-day prices, IHSG values and broker-level transaction summaries to external users require an IDX
   data licence or vendor agreement, whichever redistributor they were taken from?
2. IHSG: index values and the index name.
3. Insider and major-holder disclosures (`data_origin` IDX and KSEI): may they be reproduced with holder names?
4. Source and terms of the sector and industry classification in `IDX_Stock_Universe` and `Universe_Equity_Description`
   (which source is it: TradingView's, IDX-IC, or the user's curation?).

**Issuers**: logos are their trademarks (`FUTURE_PLAN.md:868-870`); is a per-issuer permission or a general rule needed?

**Web and AI**
1. Exa through OpenRouter and Google News RSS (documented as unofficial): may results be shown to external users?
2. Quoting news excerpts verbatim in answers and storing full excerpts: limits?
3. Fetching any public page without robots.txt handling: acceptable for a multi-user product?
4. OpenRouter and each model provider: may their output be offered to external users, and what do they do with users'
   prompts (logging, training)? FACT: the code sets no OpenRouter data-policy option (grep `data_collection`, `zdr`:
   none in `apps/market-ai-orc/app` and `apps/market-web-governor/app`). Setting one is a provider change and needs the
   user's approval (`AGENTS.md`, Model and provider).

**Questions for the user (not the providers)**
1. Will EDGE be paid? `FUTURE_PLAN.md:870` already speaks of "layanan berbayar kita"; the answer changes every question above.
2. Is the AI chat (Monitor) open to external users (`PLAN.md:926-927`)? It is the widest raw-data path (27 exposed objects,
   200,000 input rows per XLSX).
3. Until terms are answered, which sources stay owner-only? PROPOSED: a per-source exposure switch (owner-only / derived
   only / raw) read by edge-bff, Orc's SQL Governor list and the publisher, with external accounts off for any source not
   yet cleared; and a source line on every screen and export once attribution is settled.

---

## 5. Privacy: personal data EDGE stores or sends per user

### 5.1 Stored today (FACT, migrations and live counts 2026-10-28)

| Store | Personal data | Owner link | Retention today |
|---|---|---|---|
| `edge_bff.sessions` | session token hash, timestamps | `owner_key` | cleaned when the loop starts and hourly (`apps/edge-bff/README.md:333`) |
| `edge_bff.jobs` (est. 340 rows) | `input` jsonb: the user's question and settings (`20261008_002_create_edge_bff.sql:25-41, 63`) | `owner_key` | **no automatic purge** (`README.md:329-330`) |
| `edge_bff.conversation_ui` (est. 88) | conversation titles, bookmarks, pins | `owner_key` | no purge |
| `edge_bff.backtest_jobs` / `backtest_results` / `backtest_trials` | backtest requests (tickers, rules), results, trial Sharpe per variant | `owner_key` | jobs: no purge; results 30 days; trials never reset (K3) (`README.md:330-331`) |
| `edge_bff.screener_items`, `edge_bff.watchlist_items` | saved screen names and definitions, My metrics, watched tickers (`20261028_001_edge_bff_screener.sql:26-59`) | `owner_key` | not purged; capped per owner (`README.md:331-333`) |
| `AI_conversation` + `_turn` (`user_message`, `assistant_text`, `response`), `_output`, `_execution`, `_export` (files in a bucket), `_evidence`, `_run_memory` | the conversations | `AI_conversation` owner key; children by `conversation_id` | 30 days after the last activity: `AI_CONVERSATION_RETENTION_DAYS` default 30 (`apps/market-ai-orc/README.md:345, 614-616`); the variable is not set on dev (names listed), so 30 applies. Live: 534 conversations, `expires_at` 2026-10-28 to 2026-11-25. Bundles and outputs 24 h (`README.md:666`) |
| `AI_research_run_audit` (1,376 rows, 2026-09-24 to 2026-10-26) | `question` (the user's message, up to 16,000 characters) and `answer` | **no owner column**; only `request_id` (`20260924_004_create_research_run_audit.sql:40-60`) | **INSERT only, "never updated or deleted by the application"** (`:115`) |
| Web governor: `web_ask`, `web_fact`, `web_orc_result`, `web_orc_budget`, `web_event_item`, SQLite store | questions and search queries derived from user turns (INFERENCE), cost per user turn | by request / turn | `web_ask`, `web_fact` 30 days; `web_orc_result` 7 days default; `web_orc_budget` 1 day; `web_event_item` INSERT-only (no delete); SQLite `WEB_RETENTION_HOURS` (default 168) (`PROJECT_CONTEXT.md:14`; `config.py:244, 272, 294`) |
| Sandbox records, Governor datasets | analysis inputs and code | by run | about 30 days and about 7 days (`apps/market-audit-store/README.md:166-167`) |
| `terminal.subscriber`, `session`, `access_log`, `sign_in_attempt`, `admin_log` | email, display name, password hash, account expiry; session IP; per file: ticker, dataset, bytes, IP; sign-in email and IP (`20261025_100_create_terminal_schema.sql:23-104`) | `subscriber_id` | `access_log` 90 days (`apps/terminal-api/app/main.py:36`, `store.py:78-80`); `sign_in_attempt`: no pruning found in `apps/terminal-api/app` (UNKNOWN). Today EDGE uses one gateway subscriber; with P31 every EDGE user gets a subscriber row and their own access log |
| market-audit-store (implemented, **not deployed**) | run events, sanitized tool arguments, final responses | run / conversation | planned 90 days standard, 365 pinned; destructive cleanup not enabled (`apps/market-audit-store/README.md:5-9, 161-172`) |

Also third-party personal data EDGE shows: insider holder names (directors, commissioners, controlling holders), 2,212
distinct names of IDX origin and 3,066 of KSEI origin (the two sets may overlap) (section 1.2, S3), in the Terminal's event files and to the AI.

### 5.2 Sent to third parties (FACT)

- OpenRouter and the model provider it routes to: every prompt, including the user's messages, with the conversation id
  as OpenRouter's `session_id` (`AGENTS.md`, Model and provider, EXEC-S). No data-policy option is set (section 4).
- Exa (through OpenRouter) and Google News: search queries the governor writes from the user's question.
- The bucket's storage host `*.t3.storageapi.dev`: each Terminal/Backtest file download, with the user's IP and the ticker in the key.
- Google Fonts: the user's IP on every page load.
- Railway: service logs under Railway's log retention (`apps/market-ai-orc/README.md:1529`).
- Manual agent: `AI_ENABLE_MANUAL_AGENT` is set on market-ai-orc dev (name listed; `EXEC.md:232` recorded `true` on
  2026-10-17). A manual step queues the exact model packet, which includes the user's conversation, for a Claude session
  run by the operator (`EXEC.md:216-226`). The sibling file proposes admin-only routes or keeping it off.

### 5.3 Privacy questions for the user

1. Retention per store for external users: `edge_bff.jobs.input`, `conversation_ui`, backtest jobs and trials, screener
   items and watchlist (none purged today); is 30 days right for conversations?
2. Account deletion: what it erases. `AI_research_run_audit` keeps questions and answers forever without an owner column,
   and `web_event_item` is INSERT-only, so a deletion cannot reach them today. Keep them (and say so in a privacy notice),
   link them to the owner, or stop storing question text for external users?
3. A privacy notice and terms of use page: none exists today (section 3). Which data-protection law applies to the users
   (for Indonesian users, for example, the Personal Data Protection Law, UU No. 27/2022) is for the user to confirm; no
   legal conclusion is drawn here.
4. Prompts to model providers: is sending external users' messages to OpenRouter's default routing acceptable, or must a
   data-policy setting (no logging or training) be requested from the providers, with the user's approval?
5. Manual agent: off for external users, or admin-only?
6. Insider holder names: shown to external users or not (also a provider question, section 4)?

---

## 6. Key facts and open questions in one list

- FACT: the two market sources are taken without a licence recorded anywhere in the repository. TradingView: anonymous
  token on an endpoint the docs call unofficial, with no written permission (`EXEC.md:8190-8193`). Stockbit: one
  personal account's JWT. For IDX, KSEI, the sector classification, logos, web search and model output, the docs are
  silent (UNKNOWN). Logo rights were explicitly noted as unchecked (`FUTURE_PLAN.md:870`).
- FACT: raw data at source grain reaches the browser on three screens (Terminal files, Screener preview bars, AI answer
  tables and XLSX input sheets of up to 200,000 rows) and can be exported as CSV or XLSX on all four screens.
- FACT: the per-user download limits exist only in terminal-api, and EDGE bypasses them today through one gateway
  subscriber with a TEMPORARY 1e9 override. The Screener and the AI have no per-user data quota.
- FACT: EDGE shows no source attribution, terms of use or privacy notice; the only notice is "Not investment advice".
- FACT: per-user data includes the users' questions (kept with no purge in `edge_bff.jobs` and forever in
  `AI_research_run_audit`), conversations (30 days), backtests, screens, watchlists, and in terminal-api email, IP and
  per-file access (90 days).
- OPEN (user and providers): per source, may it be shown raw, derived only, or owner-only, with what attribution, and
  for a paid service? Is the AI chat open to external users? Retention and deletion rules, and a privacy notice. These
  block the first external user (M6 in the sibling file; E6 / M-U6 in report 6d).
