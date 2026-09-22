# AI data coverage

This Railway cron refreshes `public."AI_data_coverage"` from raw and control
tables only. It never reads `Feature_01_Stock_Daily`,
`Feature_02_Broker_Rolling`, or `Feature_03_Stock_Broker_Daily`.

- Price coverage is measured from `Price_Stock_Indonesia_IDX` per ticker.
- Feature 01 expected coverage inherits the price range and is marked
  `PIPELINE_CONFIRMED` only when `Feature_Status` reports a successful,
  fully-drained queue through the source maximum date.
- Broker coverage is measured from `IDX_Broker_Summary` per ticker.
- Feature 02 and Feature 03 inherit that expected range but remain
  `UNVERIFIED` with `MANUAL_REFRESH_REQUIRED` because neither has an automatic
  worker.
- Stock universe and broker profile are dataset-level snapshots.

Railway runs `python coverage_job.py --mode nightly` at 07:30 Asia/Jakarta
(`30 0 * * *` UTC). Nightly mode scans the latest 30 calendar days of raw
history and preserves the most recent full-scan counts. A controlled initial or
manual reconciliation uses:

```bash
python coverage_job.py --mode full
```

The service requires only `DATABASE_URL=${{Postgres.DATABASE_URL}}`. Its code
writes only `AI_data_coverage`; all other referenced tables are read-only.
