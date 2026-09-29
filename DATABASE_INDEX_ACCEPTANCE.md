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
