# Telegram Monitor

The service listens on Railway private IPv6 networking. Telegram messages put
one blank line between the status summary, the job's `Triggered at` / `Finished
at` timestamps in Asia/Jakarta, and any `Missing:` ticker list.

Event-driven Railway service that sends Telegram notifications after a data job
commits its monitoring rows. It does not poll the database and has no cron
schedule. The IDX DAILY and RECOVERY jobs call `POST /notify` with their shared
`execution_id`; duplicate calls are suppressed by `Telegram_Notification_Log`.

The endpoint also accepts `Monitoring_Fixed_Income` and `Monitoring_Feature04`.
Fixed-income messages report expected, queried, updated, and missing ticker/metric series.
Feature04 sends one compact final message with eligible, successful, failed, and blocked
ticker counts. It shows at most ten failed ticker/column details and links back to the
failure-only retry menu. Scheduled DAILY and RECOVERY executions for the same market and
trade date share one logical delivery key; a later result edits that message. Manual and
ad-hoc executions keep their execution-level delivery key. A retry completion edits the
acknowledgement created by `telegram-trigger` instead of sending a second message. For an
automatic price run, the price delivery sets `Monitoring_Feature04.price_notification_sent_at`;
the Feature04 worker dispatches its durable outbox only after that gate is set.
The gate includes `source_monitor_table`, so independent equity and fixed-income cron
executions cannot acknowledge each other accidentally.

## Required Railway variables

- `DATABASE_URL`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `TELEGRAM_NOTIFY_SECRET`
- `TELEGRAM_NOTIFY_SUCCESS` (optional, defaults to `true`)

Secrets must remain in Railway variables and must never be committed.
