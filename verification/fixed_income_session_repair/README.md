# Fixed-income selected-date repair

Status 2026-10-20: code prepared; local PostgreSQL tests only. No live migration,
cleansing, re-ingestion, Feature writes, cron configuration changes or deployments.
Execution is blocked by workspace network access to `ssh.railway.com:2226`
(Railway sandbox WSS execution endpoint). Do not work around this with a relay.
The temporary read-only Railway sandbox was destroyed.

## Approved scope

Both Indonesia and US; price and yield; dates **2026-09-30, 2026-10-13,
2026-10-14, 2026-10-15, 2026-10-16, 2026-10-19**. Exact physical tables are
`public."Price_Fixed_Income"` and `public."Feature_04_Technical_Indicator"`;
Feature asset type is `bonds`. October 12 and every other source date are excluded.
User explicitly approved subsequent affected Feature dates for consistency.
No equity changes, formula changes or normal worker-limit changes.

## Read-only live baseline

2026-10-20: selected dates contain 178 source rows and 89 Feature rows.
September 30 contains ID22 + US26 source rows; each selected October date has
US26 and ID0. Universe contains 24 tickers / 48 price-yield series. All 24 bond
queues were DONE. No retained checkpoint precedes September 30. Counts must be
read again at execution; they are not hardcoded into repair code.

Live cron UTC schedules: ID daily10:00/recovery11:00 (17:00/18:00 WIB),
US daily23:00/recovery00:00 (06:00/07:00 WIB next calendar day).
ID October19 attempts at17:04 and18:03 WIB skipped; US October19 ingested
October20 at06:02 WIB. Cron clocks alone do not explain missing ID candles:
the source-session anchor was mapped using the wrong observation-date policy.
The pending migration verifies provider metadata separately from economic close.

## Execution sequence after network access is restored

1. Use a fresh ephemeral Railway sandbox with runtime database references;
   never put credentials in Git, command output or an image. Start with a read-only
   connection. Install the tracked Feature/ingestion dependencies (TA-Lib0.6.8,
   C library0.6.4, numpy2.3.5, psycopg3.2.13 used in local verification).
2. From this Git branch, run the read-only provider/database preflight:

```sh
python scripts/repair_fixed_income_dates.py prepare --markets ID US   --dates 2026-09-30 2026-10-13 2026-10-14 2026-10-15 2026-10-16 2026-10-19   --request-bars 60 --plan /tmp/fixed-income-plan.json
```

3. Review the printed plan SHA256 and counts. Preparation aborts if *any* selected
   series/date is absent, non-final, invalid or has unexpected provider metadata.
   No older candle substitutes for a missing date. Provider availability has **not**
   yet been freshly established for this repair. The plan expires after24hours.
4. With no active writers, apply the tracked forward migration
   `database/migrations/20261013_011_verify_fixed_income_sessions.sql`, verify its
   two metadata columns and unchanged close clocks, then roll out the compatible
   ingestion code from Git. Record migration hash and exact deployment SUCCESS.
   The migration is not repeatable: its guard intentionally rejects a second run.
   Coordinate this sequence away from cron firing times; do not deploy the new
   schedule reader before its schema exists. Refresh the plan if any guarded
   source, universe, queue, output, state or economic schedule changes.
5. Supply a write-capable operator connection only for apply:

```sh
python scripts/repair_fixed_income_dates.py apply   --plan /tmp/fixed-income-plan.json --expected-sha256 REVIEWED_SHA256   --backup /tmp/fixed-income-before.json --confirm-apply
```

6. The operator backs up the guarded before-image, acquires the native market
   writer advisory locks and source/queue locks, and checks for concurrent changes.
   One transaction deletes only the selected source/Feature dates, inserts the
   validated replacements, and updates affected downstream Features, checkpoints,
   per-column status and per-ticker calculation logs. Any failure rolls back.
   Preserve the plan/backup securely outside Git before deleting the sandbox.
7. Independently read back all48series per selected date if all were available,
   source OHLC/finality, all51 output columns, state hashes, idle queues and audit
   log run ID. Refresh schema/catalog snapshots and changelogs after actual success.
   Destroy temporary execution resources. Do not claim live success from tests.

## Recalculation and limits

Because September30 has no preceding retained checkpoint, this one-off operation
reads the existing source prefix through September29 to bootstrap recursive state.
It writes no earlier Feature rows. It then processes the affected suffix in
five-observation chunks (derived from market correction policy), retains seven
checkpoints, and compares every output to the full-reference formula engine with
absolute tolerance1e-10 and relative tolerance1e-12; NULL/integer semantics match.
This historical bootstrap is specific to this approved repair. Normal daily
workers retain their bounded five-session behavior and REPAIR_REQUIRED handling.
Unselected historical source candles remain as stored: this repair does not prove
that the entire historical database matches TradingView.

## Verification

Tests use a disposable local PostgreSQL17 database, actual enqueue trigger/function
bodies and actual source/Feature writers. Provider transport is mocked in local
tests: these establish transaction/formula behavior, not live provider coverage.
Checks cover recursive downstream changes, untouched equity/unselected source
rows, full rollback after deletion, stale source/queue/state/schedule refusal,
missing candles, expired/wrong-hash/replayed plans and migration prerequisites.
Final suite: **107 passed in12.06s**, including the actual forward migration and repeat-run guard against local PostgreSQL with minimal catalog tables. See VALIDATION.json. No Telegram messages are sent by the operator.

The recovery-wrapper fixes remain code-only. Existing live recovery services call
`fixed_income_update.py --mode recovery` directly; activating wrappers is a separate
configuration rollout and must not be represented as already running.
