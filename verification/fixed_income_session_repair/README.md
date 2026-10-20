# Fixed-income selected-date repair

Status 2026-10-20: **live repair completed and independently verified at18:43–18:46 WIB**.
The Git-based job was used after the user resumed execution. No SSH was required.
Prepared288 selected replacement candles; replaced178 existing source rows;
144 selected-date Feature rows now exist. All312 affected Feature rows matched
all51 output columns;174 rows were inserted/updated. All24 queues DONE and
all1,224 per-column statuses SUCCESS. Independent readback found zero invalid
selected candles and zero source/Feature close mismatches.

Prepare deployment e9ffd3bf-461e-43ea-b672-b97111ff7bb4 and apply deployment
3e23614a-d23e-488d-a3e7-b8bdd2c1c8d8 reached SUCCESS. Run ID
8bff9518-6410-4738-a25f-699bc69da6d3 identifies the24 calculation audit records.
The temporary service was deleted. The100MB evidence volume
7f146278-0e8c-40d0-b2cc-7f244252170d remains unattached, preserving the plan,
pre-migration backup, before-image and results at `/repair/fi-selected-20261020-a/`.
See LIVE_LOGS.json, LIVE_READBACK.json and VALIDATION.json. Do not replay the plan.

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

## Historical sandbox runbook (superseded by the Git-based job below)

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
   No older candle substitutes for a missing date. Provider availability was established successfully for all288 replacements in this execution. The plan expires after24hours.
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
Final suite before live execution: **109 passed in14.63s**, including the actual forward migration and repeat-run guard against local PostgreSQL with minimal catalog tables. See VALIDATION.json. No Telegram messages are sent by the operator.

The recovery-wrapper fixes remain code-only. Existing live recovery services call
`fixed_income_update.py --mode recovery` directly; activating wrappers is a separate
configuration rollout and must not be represented as already running.

## Git-based job (approved replacement for sandbox execution)

`apps/fixed-income-repair-job/Dockerfile` runs `scripts/run_fixed_income_repair_job.py`. No SSH, listening endpoint or arbitrary SQL execution API. Scope is supplied as explicit runtime variables. Prepare uses the pgweb read-only reference and stores the plan on a dedicated persistent volume. Apply is a separate deployment requiring exact plan and migration SHA256, a write-capable operator reference and the existing prepared plan. Stage-started markers and restart NEVER prevent accidental re-execution. Two additional real-Postgres job tests passed: prepare has no DB writes, apply/readback persist, restart does not repeat, and a missing volume fails before database access.

## Main code release

The owner explicitly approved “Okay, merge and release ke main ya” on2026-10-20. PR37 was merged at19:09 WIB as e3f7dfd9e2be074d019304eb32c999b88af8028d. The earlier approval hold is resolved. Four bonds cron deployments were triggered automatically from Git, retaining their schedules/start commands. No repair or migration replay. All four bonds cron deployments and the Feature04 worker reached SUCCESS on the merge commit. See RELEASE.json for exact IDs. Cron schedules remain ID17:00/18:00 WIB and US06:00/07:00 WIB. No scheduled production ingestion is claimed before those next runs.
