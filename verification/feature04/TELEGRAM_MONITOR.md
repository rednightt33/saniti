# Feature04 Telegram monitor verification

Execution authorized 2026-10-12 with `"Okay gas."` after the Feature04-only monitoring
contract was confirmed.

## Contract

- Scheduled DAILY and RECOVERY for one market/trade date use one Feature04 message.
- The message is final and compact: eligible, success, failed, blocked, at most ten failure
  details, and a link to the failure-only retry menu.
- A ticker or column retry covers exactly the latest configured five final sessions and
  loads the compatible checkpoint before that window.
- The retry acknowledgement is edited with the terminal result. A completion cannot race
  before its acknowledgement has been recorded.
- Price notifications, price schedules, Feature04 formulas, and Railway topology do not
  change.

## Database execution

- Migration: `database/migrations/20261012_004_feature04_telegram_monitor.sql`
- SHA256: `cc9768a3c10d82d9ede1939e381d304c1f1620a603b19fa886ac041e200ebda1`
- Corrected rollback rehearsal: `e4c44a8c-12d2-4073-a22d-b7230544e919` (`SUCCESS`)
- Live apply: `84cb9310-42b8-4562-ba18-4e597bdf67f0` (`SUCCESS`)
- Independent readback: `0ad9188a-bf33-402c-9e7c-382437fbcb9c` (`SUCCESS`)
- Delivery-key catalog migration: `20261012_005_document_feature04_delivery_key.sql`
  (`1ff8e3f0842327b3df99bf9b3563f47b45bbe7636d2cb3f84a46c399836afd58`)
- Catalog rollback/apply: `48babe35-9412-4b4d-94e2-8f98aa87db46` /
  `6e7db0c4-33c9-49d6-bdd6-e36510713790` (both `SUCCESS`)

Live readback found the new column, nonnegative constraint, retry-window function, and
VERIFIED catalog entry. Equity `AADI` and bond `ID01MY` both returned dirty date
`2026-10-05`, equal to the oldest of their five latest final source dates. No active queue
claim or sending outbox was introduced by the read-only check.

## Application validation

```text
PYTHONPATH=/tmp/feature04-telegram-testdeps python -m pytest -q \
  features/feature04/tests \
  apps/telegram-monitor/test_telegram_monitor.py \
  apps/telegram-trigger/test_telegram_trigger.py
68 passed in 1.76s
```

`py_compile` passed for the worker, monitor, and trigger. `git diff --check` passed. The test
set covers the compact ten-item failure cap, retry button, acknowledgement recording, failed
acknowledgement fallback, and existing Feature04 engine behavior.

## Rollout

- Git main commit: `35fee3f`
- Feature04 worker: `cc083003-e92f-4c2e-9b24-0ddba6055dbc` (`SUCCESS`)
- Telegram monitor: `bbdef14e-de3a-4dc3-8918-1112402f5c4e` (`SUCCESS`, `/health` passed)
- Telegram trigger: `621f630c-2419-4792-84d0-beb628a6c0b4` (`SUCCESS`, `/health` passed)

The rollout did not send a synthetic Telegram notification; the next normal terminal
Feature04 execution exercises the delivery path without adding test noise to the owner chat.
Temporary Function `feature04-telegram-ops` was deleted project-wide. Final inventory shows
no such service and no detached volume. No permanent service, cron, variable, domain,
replica, price flow, formula, or source data changed.
