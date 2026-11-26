# EXEC-SECTOR-ANALYSIS S1/S2: measured query plans on dev (read-only, 2026-11-26)

`explain_dev.py` ran `EXPLAIN (ANALYZE, BUFFERS)` through pgweb (read-only role, statement timeout 30 s) before the
migration exists on dev. The refresh's statement is cut from the migration file (the `WITH ... agg` part, with
`feature_08_weight` replaced by its body `overview_stock_size`); the publisher's statements are sector.py's own constants.
Plans: `explain/explain_<query>_<date>.txt`; summary: `explain/summary.json`. A pair of numbers is the first read (pages
from disk) of that date in the session.

| Query | 2026-11-25 | 2026-10-29 | 2023-06-14 | 2021-03-15 |
|---|---|---|---|---|
| refresh_feature_08_day's SELECT (one date, 70 groups) | 61 ms, 6,856 pages | 297 ms, 8,693 pages (1,018 read) | 815 ms, 38,220 pages (1,803 read) | 1,261 ms, 29,096 pages (2,102 read) |
| sector.py DAY_SQL (one day's stocks with Feature 04) | 2.5 ms | 2.5 ms | 18.5 ms | 3.2 ms |
| the weights of one date (overview_stock_size) | 10 ms | 10 ms | 18 ms | 13 ms |
| FP_F04_SQL (3 window dates) | 9 ms | 11 ms | 414 ms | 229 ms |
| F04_HISTORY_SQL, 50 stocks x 301 rows | 2,055 ms (2,490 read) | 51 ms | 586 ms | 3,202 ms |

Reading of the numbers:
- The first version of the refresh (CTEs inlined) took 2.3 s for 2021-03-15: the planner repeated the price and Feature 04
  lookups for every group membership (2,544 loops instead of 862) and ran a nested-loop join over the weights (1.59 M
  rows removed by a join filter). With the per-stock working sets `MATERIALIZED` (the migration as committed) the same
  date ran in 66 ms warm (`explain2_*` in the session's scratchpad; the committed plans are those of the final text).
- Backfill: 1,407 market dates x 0.06-1.3 s = about 2-30 minutes, one statement per date (each far below the job's 5 min
  and the worker's 120 s timeout). It reads the prices of every date since 2020-12 and Feature 04 of every date since
  2021-01-25: a large update (`"large_write": true`, Postgres restart afterwards).
- Daily refresh by the worker: the correction window (5 dates, usually 7 with the dates after an older anchor), about
  0.3-2 s in all.
- The publisher's first run (or the manual mode `sector`): the sessions in status of every stock counted back once,
  about 18 statements of 50 stocks, 0.05-3.2 s each (the 120 s statement timeout of the publisher login is not near).
  A daily run counts back only the stocks missing from the previous day file (a suspension), usually none.
- Not measurable before the migration: sector.py `F08_SQL` and `F08_FP_SQL` over the 300 series dates read about 21,000
  rows (70 groups x 300 dates, about 150 bytes each: about 400 pages) through the primary key's leading `date`; and the
  refresh's `lv` step, one backward primary-key scan per group from the date (about 70 entries each).
- The Feature 08 table needs no index besides its primary key: every reader filters by date.
