# EXEC-RADAR on the dev database (2026-11-14)

User go 2026-11-14: "1 A, 2 A 3 A go" (EXEC.md EXEC-RADAR): install the Railway CLI in the session, then on the dev
database migrations `20261114_001` and `20261114_002` (DRYRUN, then APPLY) and the first fill
`verification/radar/backfill_job.py` (DRYRUN, then APPLY with `large_write` and a Postgres restart afterwards). Merge to
`main` and service deploys are not part of it. Every job ran on `orc-test-runner` (dev) through
`scripts/onboarding/run_job.sh`; the logs are in `jobs/` (no secret in them).

## Steps

| UTC | Job | What | Result |
|---|---|---|---|
| 15:17 | `b1ffba1e` | migrations 001 + 002, DRYRUN | `DRYRUN_BODY_OK` both; rules S1-S8 (S7 D 2 / 5 / 10), catalog 5 / 88 / 68, grants read back, 5 functions |
| 15:19 | `0d9f6fe9` | migrations 001 + 002, APPLY | sha256 `0b0808bc…` and `da46d238…`; the same probes read back |
| 15:26 | `57232933` | backfill DRYRUN (20 tickers, 3 dates, rolled back) | estimate: tickers 9.9 min, **day steps 359.5 min** (about 86 s a date) |
| — | read-only EXPLAIN (pgweb) | the day step's S3 read | a hash join over a sequential scan of all of Feature 05 (45 M rows); a per-ticker primary-key lookup read the same rows in 0.6 s (ERRORS M432) |
| 15:30 | `70b5cc98`, `d85c7cb9` | migration 003 (`20261114_003_feature_07_radar_s3_lookup.sql`), DRYRUN then APPLY | sha256 `8bce1a3f…`; the function holds the lookup; locally 9,417 rows identical before and after |
| 15:33 | `475022cd` | backfill DRYRUN again | estimate: tickers 6.9 min, **day steps 3.9 min**; same sample results as the first DRYRUN |
| 15:34-15:41 | `72049533` | backfill APPLY, 250 result sessions 2025-10-24 to 2026-11-09, 901 tickers | 405 s; VERDICT APPLY_OK (below) |
| 15:42, 15:54 | `scripts/restart_postgres.py` check | Postgres restart after the large write | refused both times: memory 0.475 and 0.497 GB, below 0.8 GB (nothing to free); 0 statements, 0 user runs. The job's own step did not run (ERRORS M433) |

## Backfill result (read back)

- 214,992 measure rows = 214,992 Regular rows of Feature 06 over the same dates and tickers; daily foreign net and
  buying sums equal to Feature 06; 250 gate rows; 0 rows without their cross-section.
- 3 Nov: G2 universe 859, Broad 430 (cut Rp 2.30 bn), Liquid 172 (cut Rp 25.50 bn), as in the rehearsal. 9 Nov: 855,
  428, 171.
- Standard hits equal the rehearsal on 3 and 9 Nov except S3 Broad on 3 Nov: 30 on dev, 31 in the rehearsal. The
  library's own recount is 30. The rehearsal's copy held Feature 05 from 28 Oct only, so a stock whose own 5 sessions
  start earlier had fewer broker rows there, which moves the cross-stock ranks; with the full rows the recalculation
  below agrees with dev's 30.

## Independent recalculation on dev's tables

`verification/radar/validate_radar.py` (Python, written from the library and the spec, not from the SQL) against the dev
tables (`out_measure`, `out_gate`, `out_result` read through pgweb, read-only), **every ticker** (`--tickers 0`) on six
dates: 2026-09-15, 10-01, 10-20, 11-03, 11-06, 11-09 (and the date before each for near and left).

- First run, on the rehearsal's source copy (Feature 06 from 2024-11-01, Feature 03 from 2026-08-01, Feature 05 on
  9 dates): differences only where the copy was shorter than what the SQL reads. Examples: ABDA and BLTZ have no
  own-year rank in the copy (253 and 135 sessions in it, 702 and 1,425 on dev); DEFI's robust z used a shorter baseline;
  S3 on dates before 28 Oct had no broker rows in the copy.
- Second run, on a copy cut to the SQL's own read window (each ticker from the 400th session before 2025-10-24, the
  backfill start; `refresh_feature_07` line 316): Feature 06 173,780 more rows, Feature 03 131, Feature 05 472,224 (each
  stock's own 5 sessions of every checked date): **0 differences** (860, 859, 871, 859, 853 and 857 tickers; 2,398 to
  3,594 hit and near rows a date; every measure, gate, rank, result, left reason and run of days).

## S6Δ thresholds over 20 dates (R4, option C; not applied)

Method locked in SCREENER_LIBRARY.md 11.1 (user D2, 2026-11-14 "Ya udah, kita opsi C"): among the stocks that pass V1
(5-session foreign ratio ≥ 5%) in the Broad gate, the distribution of V1Δ (ratio minus the ratio 5 sessions earlier, in
points) and V2Δ (own-year rank minus the rank 5 sessions earlier); Loose ≈ P50, Standard ≈ P75, Strict ≈ P90; here the
median of each percentile over the 20 newest result dates (2026-10-13 to 11-09; 49 to 142 stocks a date, median 100 and
95). Read-only from `Feature_07_Radar_Measure`.

| | P50 | P75 | P90 | Provisional (3 Nov) | 3 Nov from dev |
|---|---:|---:|---:|---|---|
| V1Δ Broad, median of 20 dates | 10.4 | 18.2 | 28.6 | 12 / 20 / 35 | 11.3 / 18.5 / 34.7 |
| V2Δ Broad, median of 20 dates | 32.1 | 59.3 | 77.6 | 40 / 65 / 90 | 43.1 / 64.0 / 89.1 |
| V1Δ Liquid (for reference) | 10.3 | 18.6 | 27.5 | | |
| V2Δ Liquid (for reference) | 28.8 | 49.1 | 65.7 | | |

The day-to-day spread is wide (V1Δ P90 16.3 on 26 Oct, 43.5 on 14 Oct; V2Δ P50 7.9 on 27 Oct, 48.4 on 4 Nov). Average
hits a day over the 20 dates, Broad, Standard: S6 28.6; ratio 10.3 with either set; rank 9.6 (provisional) or 10.4
(rounded 30 / 60 / 80); both 5.0 or 5.5. **User decision 2026-11-14 ("1A"): the thresholds stay 12 / 20 / 35 and
40 / 65 / 90**, now decided; no new rule version. The rows' `provisional` label is replaced by migration
`proposed/20261114_004_feature_07_radar_s6d_decided.sql` (tested locally; moved to `database/migrations/` and run on
dev once the user gives its go).
