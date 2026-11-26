# EXEC-SECTOR-ANALYSIS S1: local rehearsal of migration 20261126_001 (2026-11-26)

Nothing here ran on the dev database. Dev was only read (pgweb, read-only role, statement timeout 30 s) for the table
definitions and the measurements of `EXPLAIN.md`.

## Setup
- PostgreSQL 16.15, a scratch cluster, database `f08_rehearsal` (dropped and created by the script).
- `rehearsal/dev_ddl.sql`: the definitions read from dev (columns, checks, keys, indexes, the catalog triggers and their
  functions) of `Price_Stock_Indonesia_IDX`, `Feature_Index_Entity`, `IDX_Stock_Universe`, `Feature_04_Technical_Indicator`,
  `Table_Catalog`, `Column_Catalog`, `Feature_Catalog`, `Monitoring_Feature04`, `Equity_Market_Schedule`; the size function
  is read from its own migration (`20261115_020`). Roles `terminal_market_reader` and `pgweb_reader` (NOLOGIN).
- Synthetic data (`rehearsal/rehearse.py` docstring): 30 market dates, 8 stocks chosen for the rules (a suspension, a new
  listing, volume 0, a close equal to its EMA, a stock without a Feature 04 row on one date, an industry without weights,
  an industry without members, a fund with a weight), IHSG, 11 SECTOR entities, a non-final weekday.

## Results (`rehearsal/rehearse_output.txt`, VERDICT PASS, 39 checks)

| Check | Result |
|---|---|
| Migration (sha256 `ec5288b6…`) | COMMIT, its own checks passed (18 columns catalogued, 18 active Feature definitions, the grants) |
| A second application | refused: "Feature_08_Group_Daily already exists" |
| Every column of every row (17 groups x 30 dates = 510 rows) against an independent Python computation of CONTRACT section 2 | 0 differences |
| `validate_feature_08.py` (the dev validator) on every date | 0 differences |
| The Banks return of 2026-02-02 uses the previous date's weights | 1.452488 % (same-date weights would give 1.479767 %) |
| Chain: level(t) = last non-NULL level x (1 + ret / 100), first date 100, NULL over the 19 dates without weights (the size function needs 20 sessions) | holds on every date |
| An industry without weights (Oil & Gas, volume 0) | level 100 on its first date, NULL after; weight_basis and weight_sum NULL |
| An industry without members (Tobacco, never priced) | members 0 on every date, level NULL after the first |
| MARKET breadth against the Overview's own `BREADTH_SQL` (imported from overview.py) | equal on all 30 dates |
| Idempotent: every date again; from an older date onward | the same values (sums in ticker order: equal bits) |
| A date after a missing date | refused: "the previous market date 2026-02-09 has no row while older dates have: refresh the dates in order from the first missing one" |
| A Saturday, a non-final weekday, NULL | refused: "not a market date" / "a market date is required" |
| A reclassified industry (Banks -> Banking) | the old name's row of that date deleted, the new one starts at 100 with 2 members; restored afterwards |
| Grants | `terminal_market_reader` reads the table and `feature_08_weight`, gets "permission denied" on `refresh_feature_08_day` |
| `feature_08_weight` | the rows of `overview_stock_size`, one basis `adv20_value` |
| Worker (`Feature08Refresher` with the real SQL) | the finished equity run is due (not the bond run, not the open one); its window = the 5 market dates ending at it through the newest date (7 dates); it waits while the backfill lock is held; refreshes; the values unchanged; every row of the window rewritten (119); then nothing is due; a finished Telegram retry without a date is due on the newest market date |
| Publisher (`apps/terminal-publisher/sector.py`, every statement it sends, as the role `terminal_market_reader`; a stand-in Feature 01 for the picker dates) | available; not busy; the stamp reads every input; 33 files (meta, series, 11 sector-stocks named by the lowercased index, 20 day files); the series breadth and industry levels are the Feature 08 rows; the newest day file's 1D returns and sessions in status equal a count over the rows |
| Backfill job (`backfill/backfill_job.py`, run locally on this database) | DRYRUN: 5 dates rolled back, 0 differences; APPLY: 30 dates, 510 rows, 16 breadth dates equal to BREADTH_SQL, 3 dates validated with 0 differences, no negative level, VERDICT APPLY_OK |

Example values (2026-02-02): MARKET members 7, EMA50 3 of 5, EMA200 2 of 4, advancers 6, unchanged 1, decliners 0,
weight sum 2,848,277.5, return +1.588 %, level 101.588.

## On dev, read-only (`crosscheck_dev_20261126.txt`)

`dev_crosscheck.py` runs the migration's SELECT (cut from the file) on dev and compares it with the validator's
independent recomputation from the raw rows, for 2021-01-26, 2021-07-15, 2022-03-09, 2023-06-14, 2024-10-01, 2025-03-03
and 2026-11-25: 70 groups each, **0 differences** (VERDICT CROSSCHECK_OK). The MARKET row of 2026-11-25: 837 members,
EMA50 133 of 837, EMA200 132 of 829 (the Overview's BREADTH_SQL on dev: 837 / 133 / 829 / 132), advancers 197,
unchanged 187, decliners 453, weighted return -1.593 %.

## Rerun
```
python verification/sector_analysis/db/rehearsal/rehearse.py "host=<socket dir> port=<port> user=postgres dbname=postgres"
PYTHONPATH=<dir of a read-only pgweb helper pgx.py> python verification/sector_analysis/db/dev_crosscheck.py <dates>
```
