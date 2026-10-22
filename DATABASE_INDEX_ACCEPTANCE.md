# Database Index Acceptance — AI Analyst Feature Queries

## Scope

Controlled live PostgreSQL validation on Railway `dev`, 2026-09-13. The purpose
is to prove physical scan efficiency independently from API row limits.

Validated tables:

- `Feature_01_Stock_Daily`;
- `Feature_02_Broker_Rolling` (approximately 42.6 million rows).

The test used `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` with a 60-second local
statement timeout. Execution times and cache buffers are observations from this
run, not permanent latency guarantees.

## Existing Indexes

| Table | Index | Definition | Live size |
|---|---|---|---:|
| Feature 1 | `Feature_01_Stock_Daily_pkey` | `(ticker,date)` unique | 39 MB |
| Feature 1 | `Feature_01_Stock_Daily_date_idx` | `(date)` | 9 MB |
| Feature 2 | `Feature_02_Broker_Rolling_pkey` | `(ticker,market_board,broker,date)` unique | 2,423 MB |
| Feature 2 | `Feature_02_Broker_Rolling_date_board_ticker_idx` | `(date,market_board,ticker)` | 361 MB |

## Representative Plans

The historical test range was 2023-01-01 through 2023-12-31. `SQ` was selected
as the most frequently represented BBCA broker in that bounded sample.

| Query pattern | Chosen access path | Scan rows / returned | Execution | Shared hit/read blocks | Result |
|---|---|---:|---:|---:|---|
| Feature 1: BBCA ticker/date history | Index Scan, Feature 1 PK | 239 / 239 | 6.744 ms | 0 / 12 | PASS |
| Feature 1: 2023-12-29 return rank, top 100 | Bitmap date index + bounded sort | 741 / 100 | 242.795 ms | 5 / 742 | PASS |
| Feature 2: BBCA ticker/date history | Index Scan, Feature 2 PK | 17,340 / 17,340 | 19.652 ms | 1,417 / 672 | PASS |
| Feature 2: BBCA + Regular + date history | Index Scan, Feature 2 PK | 15,333 / 15,333 | 13.489 ms | 1,629 / 0 | PASS |
| Feature 2: BBCA + SQ + date history | Index Scan, Feature 2 PK | 467 / 467 | 0.316 ms | 60 / 0 | PASS |
| Feature 2: BBCA + Regular + SQ + date history | Index Scan, Feature 2 PK | 239 / 239 | 0.156 ms | 22 / 0 | PASS |
| Feature 2: 2023-12-29 full cross section | Bitmap date/board/ticker index | 19,762 / 19,762 | 124.289 ms | 70 / 19,620 | PASS |
| Feature 2: 2023-12-29 Regular z-score rank, top 100 | Bitmap date/board/ticker index + bounded sort | 19,547 index entries; 16,127 after filter / 100 | 74.337 ms | 69 / 19,417 | PASS |

Planning time was 0.075–0.233 ms across the eight representative plans. No plan
used a full-table sequential scan.

## Decision

No additional Feature 1 or Feature 2 index is justified by this acceptance run.
The existing primary keys efficiently support selective histories, including the
tested Feature 2 patterns where date or board is not the next key component. The
existing date-leading indexes support cross-sectional screening/ranking.

In particular, no speculative `(ticker,date)`, `(ticker,market_board,date)`, or
`(ticker,broker,date)` Feature 2 index will be added now. This avoids additional
multi-gigabyte storage and write overhead without measured benefit.

## Ongoing Requirement

For each new major Feature table or materially changed query shape:

1. define expected high-frequency access patterns;
2. run bounded `EXPLAIN (ANALYZE, BUFFERS)` against representative data;
3. reject an avoidable full-table sequential scan;
4. add an index only when the measured existing plan is insufficient;
5. record before/after plan, rows, time, and buffers;
6. rerun this acceptance after significant PostgreSQL statistics, schema, or
   workload changes.

`LIMIT`, query output rows, estimated-row policy, and physical scan efficiency
remain separate controls.

---

# SQL Governor extraction cost — broker × bank universe (A4, 2026-09-29)

## Scope

Read-only investigation of error G10 (`REJECTED_JOIN_COST` in the broker screening run of 2026-09-28). A temporary
Railway job on `dev` (`a4-explain-job`, deleted after the run) ran every statement in a `READ ONLY` transaction with
`statement_timeout` 20 s. The queries mirror the form the SQL Governor compiles (`extract.compile_extraction`): the
extracted table `t0` restricted by `EXISTS` on `IDX_Stock_Universe` (`Ticker` = `Symbol`, `Industry` = 'Banks', 48
tickers), optionally by `EXISTS` on `Price_Stock_Indonesia_IDX` (`ticker, date` = `Symbol, Date`), ordered by key
columns. Dates: 2025-06. PostgreSQL 18.6; `random_page_cost` 4, `seq_page_cost` 1, `work_mem` 4 MB,
`shared_buffers` 128 MB. `IDX_Broker_Summary`: 43.7 million rows, 8.1 GB; its only index is the primary key
`("Date", "Symbol", "Broker", "Investor Type", "Market Board")`.

## Planner cost (EXPLAIN) by window

| Query | 1 day | 1 week | 1 month | 3 months |
|---|---:|---:|---:|---:|
| broker × banks | 40,326 | **227,842** | 37,036 | 96,644 |
| broker × banks × price | 41,419 | **211,382** | 55,060 | 143,850 |
| broker, all symbols, no restriction | 41,243 | 226,813 | 774,106 | 1,040,708 |
| `Feature_02_Broker_Rolling` × banks | 50,130 | 128,667 | 90,484 | 224,742 |

The cost is not monotonic in the window. For 1 day, 1 month and 3 months the planner loops over the 48 banks
(nested loop, primary-key scan per bank). For 1 week it scans the primary key over the whole date range for every
symbol (parallel index scan, about 95,000 rows) and hash-joins the result to the 48 banks, which is six times more
expensive than the 1-month plan.

## Actual execution (EXPLAIN ANALYZE, BUFFERS)

| Query | Planner cost | Rows | Execution | Buffers hit / read |
|---|---:|---:|---:|---:|
| broker × banks, 1 day | 40,326 | 1,734 | 2.3 ms | 1,906 / 0 |
| broker × banks × price, 1 day | 41,419 | 1,734 | 5.2 ms | 7,109 / 0 |
| broker × banks, 1 week | 227,842 | 6,546 | 1,281 ms | 93,415 / 1,742 |
| broker × banks × price, 1 week | 211,382 | 6,546 | 566 ms | 17,799 / 5,176 |
| `Feature_02` × banks, 1 week | 128,667 | 6,546 | 631 ms | 6,489 / 2,421 |

## Findings

1. The refused b01 parts (plan cost 604,535–827,899; 6,573–13,568 result rows, about one to two weeks of bank rows)
   match the expensive plan shape above: a date-range scan over every symbol, then a hash join to the banks.
2. Actual run time of that shape is about 1.3 s per week of data, far below `SQL_STATEMENT_TIMEOUT_SECONDS` (20 s).
   The 600,000 plan-cost limit refuses queries that finish in a few seconds.
3. Because the cost is not monotonic in the window, splitting a part into smaller windows can make it more expensive
   (1 month 37,036 → 1 week 227,842). A0/A2 must not assume that splitting always lowers the cost.
4. The primary key leads with `Date`, so a per-bank lookup can only use `Symbol` inside the date range, not seek to it.
   A `("Symbol", "Date")` index would let every window use a direct per-bank seek, but no index is added from this
   evidence alone (AGENTS.md): its benefit must be measured against build time, about 1–2 GB of space and write
   cost on a 43.7-million-row table.

## Decision

No index or limit changed. The evidence is recorded for the decision on A0/A2 and on the cost limit (see
`EXTRACTION_AND_AUDIT_PLAN.md`).

---

# Feature 04 and Feature 05 under the SQL Governor gate (2026-10-22)

## Scope

Read-only, through pgweb (role `pgweb`, `default_transaction_read_only` on, PostgreSQL 18.6, database statement
timeout 30 s). Each query has the form `extract.compile_extraction` builds (selected columns, `BETWEEN` window,
`= ANY` scope, `EXISTS` restriction on `IDX_Stock_Universe` for CURRENT_STATE, `ORDER BY` the table's key columns).
For each query the gate is recomputed with the Governor's own rule (`governor.py` `_explain`: largest node rows, a
sequential scan counted as the relation's `reltuples`; dev limits `SQL_MAX_ESTIMATED_SCAN_ROWS` 2,000,000,
`SQL_MAX_PLAN_COST` 600,000, `SQL_MAX_DATASET_ROWS` 500,000), then the query is run with `EXPLAIN (ANALYZE, BUFFERS)`
unless its plan sequentially scans a relation above the scan limit. One run each; times include cold reads and are
observations, not guarantees. Script: the session's `acc.py` (pattern kept in this section).

Indexes at the time: Feature 04 primary key `(ticker, trade_date, timeframe, asset_type)` only; Feature 05 primary key
`(ticker, trade_date, broker, investor_type, market_board)` only; Feature 02 primary key plus
`(date, market_board, ticker)`.

## Results

| Query | Gate (from EXPLAIN) | Planner rows | Actual rows | ms | Blocks hit / read | Access |
|---|---|---:|---:|---:|---:|---|
| F04 3 tickers, 1 year | approved, cost 5,320 | 1,360 | 714 | 29 | 13 / 106 | PK bitmap |
| F04 all tickers, 1 date | approved, cost 3,734 | **1** | 856 | 1,335 | 1,718 / 1,735 | PK skip scan |
| F04 all tickers, 1 month | approved, cost 101,170 | 32,251 | 17,927 | 3,209 | 3,980 / 7,948 | PK bitmap |
| F04 all tickers, 3 months | approved, cost 260,682 | 112,910 | 53,998 | 2,138 | 1,877 / 17,124 | PK bitmap |
| F04 banks, 1 month | approved, cost 7,762 | 1,804 | 989 | 4 | 1,061 / 4 | PK + universe PK |
| F04 banks, 1 year | approved, cost 94,809 | 24,477 | 11,138 | 282 | 1,046 / 865 | PK bitmap |
| F04 RSI < 30, 1 date | approved, cost 3,734 | 1 | 409 | 14 | 3,453 / 0 | PK skip scan |
| F05 1 ticker, 1 year | approved, cost 97,055 | 27,776 | 25,030 | 412 | 2 / 673 | PK bitmap |
| F05 1 ticker 1 broker, 3 years | approved, cost 8,935 | 1,128 | 1,837 | 743 | 1,191 / 972 | PK |
| F05 3 tickers foreign, 3 months | approved, cost 141,586 | 2,354 | **4,811** | 26 | 182 / 323 | PK |
| F05 all tickers, 1 date | approved, cost 53,357 | 12,703 | **27,059** | 5,104 | 8,703 / 6,817 | PK bitmap (skip) |
| F05 all foreign Regular, 1 week | approved, cost 64,658 | 13,675 | 11,736 | 1,234 | 14,475 / 2,573 | PK bitmap (skip) |
| F05 all foreign Regular, 1 month | approved, cost 190,943 | 49,399 | 54,009 | 3,435 | 8,418 / 18,025 | PK bitmap (skip) |
| F05 banks, 1 month | approved, cost 66,742 | 16,391 | 27,515 | 223 | 514 / 493 | universe PK + PK |
| F05 banks, 6 months | approved, cost 356,551 | 94,823 | **179,470** | 209 | 427 / 4,624 | PK bitmap |
| F05 1 broker all tickers, 1 month | approved, cost 221,800 | 7,858 | 9,453 | 4,333 | 17,529 / 8,364 | PK |
| F05 1 broker all tickers, 6 months | **refused (COST 792,776)** | 45,458 | 60,271 | **2,102** | 8,889 / 71,809 | PK bitmap |
| F02 all tickers, 1 date | approved, cost 63,524 | 16,922 | 27,059 | 9,040 | 4 / 26,585 | date index |
| F02 all foreign Regular, 1 week | approved, cost 405,404 | 10,076 | 11,736 | **16,830** | 2,897 / 100,601 | date index |
| F02 1 broker all tickers, 1 month | approved, cost 106,273 | 8,095 | 9,453 | 12,577 | 16,122 / 11,049 | PK |
| F02 all foreign Regular, 1 month | refused (COST 784,173) | 50,473 | — | **timeout > 30 s** | — | date index |
| F02 1 broker all tickers, 6 months | approved, cost 236,342 | 45,857 | 60,271 | 6,545 | 17,958 / 12,053 | PK bitmap |

Calendar of `query_metric` (`summary.calendar_sql`, 20 newest dates; not EXPLAIN-gated, M204): F04 10,893 ms
(15.9 million blocks hit, PK); F05 plan `Parallel Seq Scan` of 45 million rows per probed date (not run); F01 25,
F02 46, F03 17, F06 20 ms (date-leading indexes).

## Findings

1. No full-table sequential scan on the extraction path for F04 and F05: every pattern uses the primary key (with the
   PostgreSQL 18 skip scan for cross-sections). The one sequential scan is the calendar query on F05 (M204).
2. The plan cost does not predict run time, in both directions (the A4 finding of 2026-09-29, again): F05 "1 broker,
   all tickers, 6 months" is refused at cost 792,776 but runs in 2.1 s; F02 "all foreign Regular, 1 week" is approved at
   cost 405,404 and takes 16.8 s, close to `SQL_STATEMENT_TIMEOUT_SECONDS` 20. A refused query is split by date
   (`extract.partitioning`, COST); an approved one that times out is split after the timeout (`_runtime_stop`, TIME).
3. The planner's row estimate is up to 2x low on F05 (27,059 for 12,703; 179,470 for 94,823; 4,811 for 2,354), the
   G15 pattern; the estimate count (`SQL_ESTIMATE_COUNT_ENABLED`, 7 s) is what keeps bundle sizes right.
4. The "scanned rows" the gate reads is not the work done by a skip scan: F04 "all tickers, 1 date" is estimated at 1
   row and reads 3,453 blocks for 856 rows.
5. A date-leading index is not automatically better: on the same data shape Feature 02 with `(date, market_board,
   ticker)` is slower than Feature 05 without it for every cross-section (9.0 s vs 5.1 s; 16.8 s vs 1.2 s; timeout vs
   3.4 s), because the date index fetches heap rows scattered across a table stored in ticker order (Feature 05 was
   written ticker-ordered, commit `d6f967c`).

## Decision (proposal; nothing changed)

- No general date index for F04 or F05 from the extraction patterns: the primary keys pass, and the Feature 02
  comparison shows a date index can make cross-sections slower.
- The calendar query needs a fix before F05 is exposed (and fixes F04 now): either a narrow `(trade_date)` index
  measured in a DRYRUN transaction (create, EXPLAIN ANALYZE the calendar and every cross-section above, ROLLBACK) to
  prove the planner does not move cross-sections onto it, or a Governor change that EXPLAIN-gates the calendar and
  refuses with a clear message when no index leads with the time column (M204). Both need the user's go.
- The cost limit stays as it is (EXEC 2026-10-20 option 6: tightening adds refusals); the gap between cost and time
  is handled by the existing date split and runtime split, and is recorded here for the decision on a time-based
  gate.
