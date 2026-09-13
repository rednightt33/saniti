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
