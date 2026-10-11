# Telegram Trigger

Public, serverless Railway webhook that turns allowlisted Telegram commands into
Railway **Run Now** actions. It does not query TradingView and does not read price
monitoring results.

Commands:

- `/start` displays the two price controls and Feature04 status/retry entry.
- `/run_price` or **Run IDX Price** invokes `idx-price-cron`.
- `/run_recovery` or **Run IDX Recovery** invokes `idx-price-recovery-cron`.
- `/feature4`, `/feature04`, or **Feature04 Status / Retry** lists only actual failed or
  blocked ticker/column states. A full-ticker button replays the failed script for that
  ticker; a column button expands to the mandatory dependency bundle. Healthy work and
  expected warmup/formula NULLs cannot be retried through this menu.

Security and duplicate handling:

- Only `TELEGRAM_ALLOWED_CHAT_ID` is accepted.
- Telegram's webhook secret header must match `TELEGRAM_WEBHOOK_SECRET`.
- Service IDs are fixed environment variables; user input can never name an arbitrary Railway service.
- `Telegram_Command_Log.telegram_update_id` prevents Telegram webhook retries from starting a second job.
- A per-service cooldown blocks rapid distinct clicks while a recent Run Now request may still be active.
- Feature04 retry requests are inserted atomically in PostgreSQL and wake the always-on
  worker; they do not invoke Railway Run Now. `feature04_request_id` links the Telegram
  command audit to the retry execution.
- Feature04 failure rows and retry callbacks include `asset_type` (`equity` or `bonds`).
  PostgreSQL independently resolves universe membership before accepting a retry; the
  callback label is not trusted as classification and no ticker roster is hardcoded.

Required Railway variables:

- `DATABASE_URL`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_ALLOWED_CHAT_ID`
- `TELEGRAM_WEBHOOK_SECRET`
- `RAILWAY_PROJECT_TOKEN`
- `RAILWAY_DAILY_SERVICE_INSTANCE_ID`
- `RAILWAY_RECOVERY_SERVICE_INSTANCE_ID`
- `COMMAND_COOLDOWN_SECONDS` (optional; defaults to 900)

`RAILWAY_PROJECT_TOKEN`, the bot token, and webhook secret must remain Railway secrets.
