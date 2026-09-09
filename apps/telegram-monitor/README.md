# Telegram Monitor

The service listens on Railway private IPv6 networking. Telegram messages put
one blank line between the status summary, the job's `Triggered at` / `Finished
at` timestamps in Asia/Jakarta, and any `Missing:` ticker list.

Event-driven Railway service that sends Telegram notifications after a data job
commits its monitoring rows. It does not poll the database and has no cron
schedule. The IDX DAILY and RECOVERY jobs call `POST /notify` with their shared
`execution_id`; duplicate calls are suppressed by `Telegram_Notification_Log`.

## Required Railway variables

- `DATABASE_URL`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `TELEGRAM_NOTIFY_SECRET`
- `TELEGRAM_NOTIFY_SUCCESS` (optional, defaults to `true`)

Secrets must remain in Railway variables and must never be committed.
