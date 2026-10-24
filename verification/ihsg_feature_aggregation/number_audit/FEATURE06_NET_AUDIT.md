# Feature06 cumulative, rolling nets and turnover ratio audit

Read-only 2026-10-24; output date 2026-08-31. User questioned 12 columns: 2 cumulative,
5 foreign rolling, 4 domestic rolling, and foreign_net_turnover_ratio_1d. Existing script/SQL
was read; no data/formula/schema/service changes were executed.

## Result and evidence limits

**36 comparisons (12 columns × 3 boards), zero mismatches** against aggregation of non-index
Feature06 additive daily flows on a common source-session calendar. The previous writer independently
validated against canonical Feature05 history. This audit also proves that the sum of the latest cumulative
row of every historical ticker/board equals stored IHSG cumulative on all three boards.
This establishes arithmetic/definition consistency, not that every historical source observation is complete.

See `feature6_column_comparisons.csv` for every field; `feature6_net_windows.sql/.json` contains daily
aggregation reference, stored values, date-only sums, latest-as-of cumulative sums and period boundaries.

## 1. Cumulative values: preserve balances of inactive instruments

Regular board:

| Metric | Sum of non-index rows dated 2026-08-31 only | Sum of latest balance per ticker as of date = IHSG |
|---|---:|---:|
| foreign_cumulative_net | -214,944,851,014,130 | -244,441,949,513,771 |
| domestic_cumulative_net | 215,624,596,680,730 | 244,966,243,326,235 |

There are 3,942 historical Regular symbols but only 1,313 have a row on the selected date. The other
2,629 symbols carry cumulative balances from their last observed row. Their foreign cumulative sum is
-29,497,098,499,641; domestic sum 29,341,646,645,505. Adding these omitted balances reconciles exactly.
Nego: 1,399 historical symbols vs 128 present; Tunai: 1,117 vs 5. Their latest-as-of cumulative sums
also reconcile exactly. No synthetic source trades or global forward-fill rows are needed for this check.

The cumulative index sample starts at broker history **2016-01-04**. IHSG price history starts
**2018-01-02**. These baselines are different data-source contracts; choosing a new baseline must be
explicit before INDEX-table execution, not inferred from a desired matching figure.

## 2. Rolling values: common date range vs ticker-observed sessions

Existing non-index rolling counts each ticker's observed sessions across its boards. The index counts
observed aggregate market sessions. A sum of ticker rolling fields on the selected date can omit tickers
without a row that day, use older dates for irregularly traded tickers, or omit NULL warmup outputs.
Rolling cash flows ARE additive when the constituent set and exact date window are aligned.

Verified index windows ending 2026-08-31:

| Window | First date | Sessions |
|---|---|---:|
| 5 | 2026-08-24 | 5 |
| 10 | 2026-08-14 | 10 |
| 20 | 2026-07-31 | 20 |
| 40 | 2026-07-03 | 40 |
| 60 | 2026-06-04 | 60 |

Regular foreign 5D: date-only sum of ticker 5D fields=-2,022,012,804,000;
common-window sum of all ticker DAILY flows=IHSG=-2,023,719,641,100.
The difference -1,706,837,100 decomposes exactly into:
- -1,601,871,400 from tickers with activity inside the common window but no row on the target date;
- -104,965,700 from calendar differences among tickers present on the target date (no 5D warmup cases).

For 20D/60D, NULL warmups also occur (81/274 present Regular symbols). The bounded decomposition
query gives common-window flow, missing-on-date contributions and combined calendar/warmup effects.
Do not assert equality to SUM(ticker rolling columns) until these comparison contracts are aligned.
Do not redefine the index's market window merely to force sums of different ticker windows to match.

## 3. Ratio: recompute using aggregate numerator and denominator

Formula: 100 × SUM(foreign_net_1d) / SUM(foreign_buy_1d + domestic_buy_1d), same date/board/universe.
Regular: -710,561,717,600 / 20,968,636,367,500 × 100 = **-3.3886882539549577%**, matching IHSG.
SUM of non-index ratios on that date is +92.29298334965077%, a different and invalid market-ratio
aggregation. Where denominators are positive, the market ratio is the turnover-weighted average, not
an unweighted sum/mean. Zero denominator remains NULL.

EMAS alone: foreign net=-189,357,617,500; turnover=786,528,127,500; ratio=-24.07512342907279%.
Comparing EMAS directly to IHSG also changes the constituent universe.

## 4. Actual source imbalance found inside the 60-session window

2026-07-27 Regular, ticker **MAPADRCU6A**:
- Raw Buy Value=1,408,200; Sell Value=555,000; imbalance=+853,200.
- Non-index Feature06 marks the source gap; its daily Foreign+Domestic net also equals +853,200.
- This explains why IHSG foreign_net_60d=-31,368,652,139,900 while domestic_net_60d=
  +31,368,652,993,100: their sum is +853,200.

This is an input-data quality issue, preserved rather than fabricated away. It is distinct from the
non-index/index comparison-window differences. No correction, zeroing or refetch was executed.
The all-raw-symbol scope includes non-stock instruments; settle the desired index instrument universe
before bulk. Evidence: `feature6_recent_source_balance.json`, `feature6_recent_raw_gap.json`.

## Audit query performance

The first rolling-decomposition attempt hit PostgreSQL statement_timeout. That failure is retained as
`feature6_rolling_decomposition_attempt1_error.json`. The successful query materializes only the
verified 60-session date range and reuses those rows. No timeouts/limits/indexes were changed.

## Plan implications

For future INDEX tables: reconcile cumulative using latest-as-of balances and a declared initial date;
reconcile rolling using identical date ranges and source membership; recompute ratios from matching
aggregate inputs. Existing non-index calendars are not changed by this audit. Any desired common-calendar
redefinition, scope restriction, new baseline or source correction requires user agreement first.
The previously approved future frequency correction remains separate and has not been executed.
