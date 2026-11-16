# EXEC-RADAR R1-R4: local rehearsal of the Radar tables (2026-11-14)

Nothing here ran on the dev database. The dev data was only read (pgweb, read-only role) to build the rehearsal copy.
The run on dev itself (2026-11-14) is in `DEV_RUN.md`.

## Setup

- PostgreSQL 16, a local cluster, database `radar`.
- Stub tables with the live names and column types (information_schema, 2026-11-14), loaded with a read-only extract of
  dev:
  - `Feature_06_Foreign_Domestic`, universe tickers, every board, 2024-11-01 to 2026-11-09: 463,373 rows;
  - `Feature_03_Stock_Broker_Daily`, Regular, 2026-08-01 to 2026-11-09: 59,456 rows;
  - `Feature_05_Foreign_Domestic_Broker_Detail`, Regular, on the 9 dates 2026-10-28 to 2026-11-09: 200,659 rows;
  - `IDX_Stock_Universe` (908 tickers) and the corporate actions of `idx_event_annotation`, 2026-08-01 to 2026-11-14
    (539 rows).
- `Table_Catalog`, `Column_Catalog` and `Feature_Catalog` rebuilt from the live DDL: columns, checks, the partial unique
  index and the two validation triggers.
- Applied: `database/migrations/20261114_001_feature_07_radar.sql`, then
  `database/migrations/20261114_002_catalog_feature_07_radar.sql`.

## Results

| Check | Result |
|---|---|
| Migration 001 on a clean database | COMMIT |
| Catalog migration 002 (constraints and triggers of dev) | COMMIT; 5 Table_Catalog, 88 Column_Catalog, 68 Feature_Catalog rows |
| Backfill job DRYRUN (`verification/radar/backfill_job.py`, 20 tickers, 3 dates, ROLLBACK) | 57 s; nothing kept (0 rows after) |
| Backfill job APPLY, 250 result sessions (2025-10-24 to 2026-11-09), 901 tickers | 2 min 55 s; 214,992 measure rows = 214,992 Regular Feature 06 rows; 250 gate rows; VERDICT APPLY_OK |
| Day step per date | 0.22 s in the backfill; 0.35 s with no statistics at all (M427) |
| Independent recalculation (`verification/radar/validate_radar.py`, Python, written from the library and the spec, not from the SQL) | 7 dates (2026-06-15, 09-15, 10-01, 10-20, 11-03, 11-06, 11-09), about 60 tickers each (40 random, seed 7, plus 20 Liquid): every measure column, every gate, every cross-stock rank, every hit/near/left row of every filter, level and gate, the left reasons and the runs of days: **0 differences** |
| Daily refresh equals a full one (`refresh_feature_07(t, '2026-09-01')` on 63 tickers incl. ARKO, BNBR, MSIN) | 3,003 rows, every per-ticker column identical |
| Round step (`refresh.refresh_radar`, the stockbit-updater venv) | after a Feature 06 change of BBCA and DOOH from 2026-11-06: 2 tickers, 2 dates, 2.0 s; the next call 0 tickers, 0.2 s; after the day rows went stale (measures newer than their gate): 50 dates redone, 18 s |
| `apps/stockbit-updater` tests | 19 passed (8 new in `test_radar_step.py`), 42 skipped as before (need a test database) |

## Against the library (SCREENER_LIBRARY.md, 3 Nov 2026 unless stated)

| Item | Library | Radar | Note |
|---|---|---|---|
| G2 universe | 859 | 859 | |
| Kept by the gate (20/50/70/80% dropped) | 687 / 430 / 258 / 172 | 687 / 430 / 258 / 172 | |
| Cut-offs, Rp bn | 0.30 / 2.30 / 8.68 / 25.64 | 0.30 / 2.30 / 8.62 / 25.50 | M428: the library summed the last 5 Regular rows; with that its cut-offs come out exactly |
| S1 Likuid | 6 before the 5% rule (BOGA, BINA, DKFT, FORU, SQMI, NATO) | 3 (BOGA, DKFT, SQMI) | the other three are below 5% (BINA 3.2, FORU 3.4, NATO 0.4); DKFT rank 95.2, z 1.48 as the library |
| S2 Likuid | 7, KOTA 89.9 not in | 7, MSIN not in, KOTA 91.3 in | M428 (MSIN's gate and previous block) |
| S3 Likuid | 11 | the same 11 tickers | k groups 10-21, 22-26, 27-31, 32-38, 39-63 as the library; BTPS 0.743 / 0.659, BBCA 0.647 / 0.193 |
| S3 Luas | 30 (recount), 31 (section 4) | 31 | |
| S6 Likuid (5 sessions) | 13 | 12 (MSIN not in) | M428; ARKO and BNBR in after M429 |
| S6-delta Likuid ratio / rank / both | 6 / 4 / 3 | 5 / 4 / 3 | provisional thresholds (option C, R4) |
| S7 institutions in, retail out | 11 / 23 | 11 / 23 | |
| S8, 9 Nov, Broad | 5 Strong / 18 Watch (EXEC plan) | 6 Strong / 18 Watch | the same 6 and 18 under either session convention; the "5" has no recorded method or list |
| G2 universe, 9 Nov | 857 (tickers trading that day) | 855 | CSMI and XSPI traded that day but have 2 Regular sessions in the last 16 dates (G2 needs 5) |

## Rerun after the five reviews (2026-11-14, ERRORS M431)

Both migrations applied again on a clean database, the job DRYRUN (1 min) and APPLY (3 min 02 s; reconcile: 214,992 rows,
daily net and buying sums equal to Feature 06, 0 rows without their cross-section), then the validator on 8 dates
(2026-06-15, 08-12, 09-15, 10-01, 10-20, 11-03, 11-06, 11-09) with the reviewed rules (S7 D 2/5/10, S8 near = all but
one, broker-class measures only from complete windows): **0 differences**. The round step on real SQL: a Feature 06 change
of TLKM from 2026-11-05 redid 1 ticker and 3 dates (2.6 s); changed corporate actions redid the 20 newest dates (7.4 s).
The hit counts of 3 and 9 Nov are unchanged by the review fixes.

## Defects found and fixed before release

M427 (plan on missing statistics), M429 (own-year rank voided by a week without Regular buying), M430 (a stock written
as near and left), M431 (the five reviews). Open: M428 (session convention, the user's decision), M425 (Screener's Open in Terminal), M426
(old non-universe rows in Feature 06).
