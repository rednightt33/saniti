# Feature04 worker

Always-on Railway worker for `Feature04_Technical_Indicator`. It consumes the durable
`Feature04_Calculation_Queue`; it has no cron schedule and does not fetch market data.

Committed insert, update, or delete changes on `Price_Stock_Indonesia_IDX` coalesce into
one full-history job per ticker. The worker reads that ticker from its earliest Daily bar
through the latest, calculates the dependency-closed Feature04 bundle, and fences the write
with the queue's source generation and work revision. A newer price change supersedes the
old claim. Work for different tickers continues when one ticker fails.

Each formula group is isolated. Valid bundles commit even when another group fails;
`Feature04_Column_Status` records the exact failed columns. Automatic retries use bounded
backoff and stop after five source attempts. Expected formula NULLs such as EMA200 with
fewer than 200 bars and SMI on a zero range are successful outcomes. A latest NULL after
the documented minimum history for deterministic indicators is an error.

`Monitoring_Feature04` is finalized only when all eligible tickers are terminal. The
durable notification outbox waits until `telegram-monitor` has recorded the price message
as sent, then requests the separate Feature04 Telegram result. Telegram delivery failure
never rolls back calculated data.

Required Railway variables:

- `DATABASE_URL=${{Postgres.DATABASE_URL}}`
- `TELEGRAM_NOTIFY_URL=http://${{telegram-monitor.RAILWAY_PRIVATE_DOMAIN}}:8080/notify`
- `TELEGRAM_NOTIFY_SECRET=${{telegram-monitor.TELEGRAM_NOTIFY_SECRET}}`
