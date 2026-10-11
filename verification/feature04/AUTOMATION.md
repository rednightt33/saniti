# Feature04 automation verification

Verified on 2026-10-11 against Railway `lucid-patience` / `dev` / primary `Postgres`.
The user authorized execution with “Ok, jalankan” and asked that all affected Markdown
documentation be identified and updated.

## Database

Forward migration `20261011_005_automate_feature04.sql` has SHA256
`0293c4bb2cecf4940a72635afa466647c47d03bb0c39fccc428c978f503b6967`.
The full migration first ran in one transaction ending `ROLLBACK`; no rehearsal objects
remained. The identical frozen file then committed live.

Independent pgweb readback found seven new physical tables, four functions, and trigger
`Price_Stock_Indonesia_IDX_enqueue_feature04`. The baseline contains 42,200 status rows:
844 source tickers × 50 output columns, all `SUCCESS`; the initial queue was empty. The
migration did not recalculate Feature04 or rewrite source prices. Evidence:
`automation_live_readback.json` and the generated `DATABASE_SCHEMA.md`.

A trigger canary changed BBCA volume inside a transaction. It created queue generation 1
and matching monitoring membership; `ROLLBACK` removed the price change, queue work, and
test monitoring row. This proves price-trigger membership without persisting a synthetic
source revision.

The retry guard was called for healthy BBCA and rejected it with PostgreSQL `P0001` and
“no active Feature04 failure”. Expected NULL availability is therefore not exposed as a
retry target.

## Tests and Railway

Local validation: 61 tests passed across the Feature04 engine/diagnostics, price integration,
Telegram monitor, and Telegram trigger. The engine regression proves diagnostic full output
equals the prior atomic calculation. Injected ADX failure leaves the SMI/swing bundle
successful. Migration rehearsal and `git diff --check` passed.

Railway IaC plan before apply: one service added, zero changed, zero destroyed. Plan after
apply: up to date. All services deployed from commit
`4082626384cc44df89b99004597be847362b0df7`:

| Service | Deployment | Terminal status |
|---|---|---|
| feature-04-worker | `2f02c16a-4fa8-404f-a192-cdc4bd59da3b` | SUCCESS |
| idx-price-cron | `37138769-e856-494d-8d9a-6f0bf5e13213` | SUCCESS |
| idx-price-recovery-cron | `a9f666b9-9c7c-4e31-99e6-11e34ca48576` | SUCCESS |
| telegram-monitor | `9e22ab6f-ef1b-447f-a03c-697a9b1ad045` | SUCCESS |
| telegram-trigger | `4939858d-d472-4688-8ae9-cdadf5179bdf` | SUCCESS |

Worker startup logged version
`feature04-v3-smi14-5-5-th40-talib0.6.8-c0.6.4`. Exact deployment metadata is in
`automation_deployments.json`.

Private execution sandbox `07d16159-76e6-4d0a-8d97-1dddd4a6cba4`, used for migration
rehearsal/apply and rollback-only trigger validation, was destroyed after verification;
terminal state `DESTROYED` was read back.

## Live BBCA canary

Execution `f04-canary-20261011-01` replayed BBCA from 2018-01-02 through 2026-10-09:
2,113 source rows and all 50 output columns. Result `SUCCESS`; failed columns 0;
changed rows 0, confirming the existing payload was already identical. Queue generation 1
reached `DONE` / completed generation 1. Monitoring finished 1/1 successful.

The Feature04 outbox reached `SENT` on attempt 1 and `Telegram_Notification_Log` recorded
`Monitoring_Feature04` as `SENT` on attempt 1 with no error. Readback:
`automation_canary_readback.json`.

## Rollback

Stop `feature-04-worker` to halt consumption while preserving queue, failure, and audit
state. Redeploy the prior price/Telegram application revisions if an application rollback
is needed. Keep the forward migration objects and data; do not drop queue or audit tables.
After a fix, redeploy the worker and replay pending/failed work through the recorded
generation and revision controls.

## NULL availability clarification

User: “Termasuk NULL yang seharusnya sudah tersedia”. The first worker's latest-candle
check was replaced by complete selected-output availability validation. The validator checks
each contiguous valid source segment, warmup lengths, native candlestick lookbacks, and the
conditional Pine swing state. Unexpected NULL on an older bar also fails. If one member is
unavailable incorrectly, the complete dependency bundle is withheld from writes.

Regression checks cover historical EMA/pattern corruption, SMI availability, active temporary
high availability, zero-range SMI, processed 0/1 flags, invalid-OHLCV history reset, and selected
column retry. Read-only live validation found zero unexpected NULLs on BBCA (2,113 bars), RANS
(62 bars), and PRDL (63 bars); RANS and PRDL EMA200 NULLs remain valid. Aggregate evidence:
`null_availability_readback.json`. Formula version and database schema are unchanged.

The complete relevant regression suite passed 67 tests. Worker deployment
`51838910-b0f0-4256-8f79-8c998ee28b9a` from `main` commit
`557ef1194d43e09638927ada7fb54f7dbb13f07b` reached terminal `SUCCESS`;
exact readback is in `null_availability_deployment.json`.
