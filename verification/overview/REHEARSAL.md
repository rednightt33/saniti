# EXEC-OVERVIEW O1-O5: rehearsal of the Market Overview files (2026-11-15)

Nothing here wrote to the dev database. Dev was only read (pgweb, read-only role) to measure the statements and to
build the local rehearsal copy. Migration `20261115_020_overview_stock_size.sql` is applied only on the local copy; on
dev it waits for the user's go (EXEC-OVERVIEW O7).

## Setup

- PostgreSQL 16, a local cluster, database `overview`.
- Stub tables with the live names and column types, loaded with a read-only extract of dev (2026-11-15):
  - `Price_Stock_Indonesia_IDX`, daily final rows of IHSG, LQ45, the 11 sector indexes and every common stock, plus the
    20 sessions the size function reads;
  - `Feature_01_Stock_Daily`, `Feature_04_Technical_Indicator` (Daily, equity), `Feature_06_Foreign_Domestic` (Regular)
    and `Feature_06_Foreign_Domestic_INDEX` (IHSG, Regular) over the dates a run reads;
  - `price_stock_idx_intraday` (IHSG 5m and 1h), `IDX_Stock_Universe`, `Feature_Index_Entity`, `Stock_List` and
    `Stock_List_Member`.
- Applied: `database/migrations/20261115_020_overview_stock_size.sql`.
- Extract and build scripts: the session scratchpad (`ov_fx/extract.py`, `ov_fx/build_local2.py`); the fixture builder
  `apps/edge-bff/overview/tests/fixture/save.py` (publisher code, files not committed).

## Results

| Check | Result |
|---|---|
| Migration 020 on the local copy | COMMIT; `overview_stock_size('2026-11-13')` 887 rows, 12 ms; BBCA Rp 1,685.24 bn per day |
| Fingerprint of the size function | `md5(prosrc)` on the local copy = the migration body = `f451fc552b78a6174bc47b4e2a217293` |
| Full build (no previous publication) | 22 files (meta, series, 20 day files), 0.6-0.9 s, 668 KB gzip in total |
| Second run with the carry | 0.06 s; no Feature 04 count and no day file rebuilt; meta and series equal to the first run |
| Breadth count split per 20 dates (`BREADTH_CHUNK`) | 15 statements for 300 dates; the 22 files byte-equal to the single-statement build |
| Dev examples (read-only) against the files | IHSG 5,344.41 / prior 5,250.90; breadth 564/143/129 of 836; EMA50 162/836 = 19.38%, EMA200 152/828 = 18.36%; turnover 9 Nov Rp 8,153.2 bn, average Rp 13,459.5 bn; foreign net 1D +Rp 116.6 bn, 10D -Rp 2,813.3 bn; volatility 35.98%, rank 80.95; BBCA size Rp 1,685.2 bn: **equal** |
| Independent recalculation (`validate_overview.py`: own SQL and arithmetic from OVERVIEW_FORMULAS.md, dev read-only) | dates 2026-10-20, 2026-11-05, 2026-11-13: meta (862 stocks, 66 lists, dates), every stock's close/returns/EMA flags/size/foreign net, market figures, volatility, bars, series; plus the page's default view (KPI strip, LQ45 Top Movers, Financials heading, Foreign Flow lists): **27,817 comparisons, 0 differences** |
| The validator catches errors | 5 values broken on purpose in a copy (breadth, volatility rank, 5D net, one stock's 1D return, % above EMA50): all 5 reported, plus the page KPI |
| Independent code review (a separate agent, 2026-11-15) | 4 findings, each verified and fixed: ERRORS M442 (day files kept on proxies: a new stock, late IHSG bars, a Feature 01/04 fill in progress; the page mixing publications; the 1D range) |
| After the M442 fix | rehearsal files byte-equal; a second run with the carry rebuilds nothing; stamp 0.05 s locally |
| Republication while the page is open (production build, mock server answering 409 for the old shas) | the page read the index again, fetched meta and series with the new shas, then the day: 12 Nov shown, no page error |
| Publisher tests | 196 passed (16 Overview tests incl. the chunked count, late bars, a fill or rewrite in the window, a new stock, a date leaving the window) |
| terminal-api tests | 65 passed |
| Page (`apps/edge-bff/overview`) | 14 tests, typecheck, production bundle test; look check at 1440, 1100, 375 and dark, no page overflow, no console error; 33 interaction checks |

## Statements on dev (`python3 verification/overview/explain_dev.py`, read-only EXPLAIN ANALYZE, 2026-11-15)

Two runs of the same statements a few minutes apart; times vary with the disk cache (CLOSES 1.0 s, then 3.8 s, for the
same 265 pages read).

| Statement | Execution | Buffers (top node) | Seq scans |
|---|---:|---|---|
| DATES (593) | 2.216 ms | shared hit=14 | none |
| FEATURE_DATES (40) | 22.168 ms | shared hit=101 read=62 | none |
| F04_DATES (300) | 21.691 ms | shared hit=1958 read=30 | none |
| CLOSES (13 tickers, 593 dates) | 3813.637 ms | shared hit=29 read=265 | none |
| DAY (13 Nov) | 1408.702 ms | shared hit=105 read=1743 | "IDX_Stock_Universe" |
| SIZE body (13 Nov) | 1394.439 ms | shared hit=1284 read=579 | "Feature_Index_Entity" |
| STOCK_FLOW (9 Nov) | 11.943 ms | shared hit=88 read=84 | "IDX_Stock_Universe" |
| MARKET_FLOW | 13.645 ms | shared read=58 | none |
| BREADTH (1 date) | 2.845 ms | shared hit=979 | "IDX_Stock_Universe" |
| BREADTH (5 dates) | 373.261 ms | shared hit=982 read=663 | "IDX_Stock_Universe" |
| BREADTH (one chunk: 20 older dates) | 5728.480 ms | shared hit=2658 read=7964 | none |
| INTRADAY 5m (1 session) | 281.164 ms | shared read=132 | none |
| INTRADAY 1h (5 sessions) | 190.769 ms | shared read=144 | none |
| STAMP | 401.614 ms | shared hit=6842 read=3297 | "IDX_Stock_Universe" |
| FP_PRICE (window, M442) | 23.910 ms | shared hit=1 read=130 | none |
| FP_F01 (window) | 6.244 ms | shared hit=1823 | "IDX_Stock_Universe" |
| FP_F04 (window) | 230.316 ms | shared hit=94 read=1306 | "IDX_Stock_Universe" |
| FP_F06 (broker date 9 Nov) | 14.171 ms | shared hit=88 read=84 | "IDX_Stock_Universe" |
| FP_BARS (window) | 341.019 ms | shared read=276 | none |

- The sequential scans are of the small tables only (`IDX_Stock_Universe`, about 1,000 rows; `Feature_Index_Entity`, 43
  rows). Every large table is read through its index.
- **Feature 04 is the one large read.** It is 2.5 GB and the rows of one older date are spread over the whole table
  (correlation of `trade_date` -0.04). One chunk of 20 older dates read 10,622 pages (about 83 MB) in 5.7 s. A first run,
  or the manual mode `overview`, counts the 300 series dates once: about 15 such statements, roughly 1.2 GB read and
  90 s. That is a large update for the Postgres memory rule (AGENTS.md): run `scripts/restart_postgres.py` after it.
- **Why the count is chunked.** The publisher login `terminal_publisher_login` has `statement_timeout=120s` on dev
  (`pg_db_role_setting`, read 2026-11-15). The 300 dates in one statement would take about 86 s cold (15 x 5.7 s), too
  close to that limit. With `BREADTH_CHUNK = 20` no statement grows with the number of dates.
- A daily run reads Feature 04 for the new date only (BREADTH, 1 date: 3 ms to 0.4 s) and rebuilds only the day files
  whose broker date changed (DAY, SIZE, STOCK_FLOW, INTRADAY: about 3 s per day file).

## Data notes

- The EXEC plan's fact "13 Nov: 862 stocks have EMA50, 166 above it" counted Feature 04 rows without the common-stock
  filter. The Overview counts common stocks (`Security Type = 'stock'`): 836 with EMA50, 162 above (19.38%).
- The design's per-stock foreign figures (BBCA +523, ASII +200, BMRI -134, BBNI -99, BBRI -95 bn) are the real Regular
  net of 9 Nov on dev (`Feature_06_Foreign_Domestic`, read 2026-11-15), not illustration.
