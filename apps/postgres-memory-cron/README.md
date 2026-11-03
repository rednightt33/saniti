# postgres-memory-cron

Restarts Postgres on a schedule and on request, to free the Linux page cache that Railway bills as Postgres memory
(EXEC-PG-RESTART-CRON, user go 2026-11-03; why: EXEC-PG-MEMORY and ERRORS M319). Code: `scripts/restart_postgres.py
--cron` (the same file agents run by hand). A restart takes Postgres down for about 12 seconds.

## When it runs

| Run | Starts from | Restarts when |
|---|---|---|
| `scheduled` | the cronSchedule, at the times in `PG_RESTART_TIMES_WIB` (09:45 and 20:45 WIB) | auto is ON, memory ≥ `PG_RESTART_MIN_GB` (0.8 GB), every guard passes |
| `manual-telegram` | Telegram "🔄 Restart Postgres" or `/restart_postgres` (telegram-trigger Run Now; `RESTART_POSTGRES` in `Telegram_Command_Log`) | every guard passes (memory and auto ignored) |
| `manual-railway` | Run Now in the Railway dashboard, away from a listed time | every guard passes (memory and auto ignored) |
| `tick` | another tick of the cron's minute × hour product | never (exits) |

Guards (every run): no cron of another service within 45 minutes and outside B6 (07:00-08:45, 19:00-20:20 WIB) stop the
run; a running statement or an active user run (ERRORS M340: `edge_bff.jobs` QUEUED/RUNNING/RECOVERING, orc turn
RUNNING, within 2 hours) is waited for up to `PG_RESTART_WAIT_MINUTES` (60), checked every 5 minutes.

## Switch and status

Auto ON/OFF is the newest `PG_AUTO_ON` / `PG_AUTO_OFF` row in `Telegram_Command_Log` (Telegram buttons, default ON).
`PG_RESTART_AUTO=false` on this service turns it off regardless. The Telegram status ("🧠 Postgres restart") shows the
switch, the schedule (read from the live cronSchedule), Postgres's start time and the last three reports.

## Telegram messages (telegram-monitor source `Postgres_Restart`)

🔔 manual request received · ⏳ restart started · ✅ success (seconds down, memory before → after, EDGE ready) · ❌
failed (Postgres not back in 10 minutes, or EDGE not ready) · ⚠️ refused with the reason (a manual run always; a
scheduled run when a guard stops it) · 🧪 check (mode `check`: what it would have done). A scheduled run skipped for low
memory or auto OFF sends nothing (its log line says why).

## Variables (names only)

`DATABASE_URL` (`${{Postgres.DATABASE_URL}}`, read in read-only sessions), `RAILWAY_RESTART_TOKEN` (a project token of
this service only, set by stdin; revoke it in Project Settings → Tokens to stop it), `TELEGRAM_NOTIFY_URL` and
`TELEGRAM_NOTIFY_SECRET` (telegram-monitor), `PG_RESTART_TIMES_WIB`, `PG_RESTART_MODE` (`check` or `apply`), optional
`PG_RESTART_AUTO`, `PG_RESTART_WAIT_MINUTES`, `PG_RESTART_MIN_GB`. telegram-trigger holds
`RAILWAY_PG_RESTART_SERVICE_INSTANCE_ID` (the Run Now target) and `RAILWAY_PG_RESTART_SERVICE_ID` (to read the schedule).

## Changing it

- Times: `python3 scripts/set_postgres_restart_times.py --wib 09:45,20:45` (check), then `--apply` with the user's
  approval. It refuses a time near another cron or in B6, and keeps the variable and the cronSchedule together.
- Code: `apps/postgres-memory-cron/deploy.sh` (CLI upload; a push to `main` deploys nothing here). A cron service does
  not run on deploy, and a variable reaches it only through a new upload, not a redeploy (ERRORS M229).
- Mode: `railway variable set PG_RESTART_MODE=apply -s postgres-memory-cron --skip-deploys`, then `deploy.sh`.
- Log: every run prints `PG_RESTART {...}` lines (kind, action, reasons, memory).
