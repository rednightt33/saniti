# Feature04 worker

Always-on Railway worker for cross-asset `Feature_04_Technical_Indicator`. It consumes the durable
`Feature04_Calculation_Queue`; it has no cron schedule and does not fetch market data.

Committed final insert, update, or delete changes on either supported price source coalesce
into one job per ticker at the earliest changed session. The worker requires an exact,
version-compatible checkpoint immediately before that date and calculates only the affected
suffix through latest. It fences the write and new checkpoints with the queue's source
generation and work revision. A newer price change supersedes the old claim. Missing, stale,
or out-of-window state stops with `REPAIR_REQUIRED`; daily work never falls back to a
full-history replay.

Queue identity is `(asset_type,ticker,timeframe)`. Classification comes from the live
universe tables: `IDX_Stock_Universe` for equity and `Universe_Fixed_income` for bonds.
The worker reads final equity candles from `Price_Stock_Indonesia_IDX` and bond candles from
`Price_Fixed_Income` where `metric_type='price'`, `"Timeframe"='1D'`, and `is_final=true`. No ticker roster
is embedded in code. Bond `NULL` volume is valid because the indicator bundle uses OHLC.
Each full refresh also copies the exact source `close` for every target `trade_date`.
`close` participates in the same per-column status and failure-only retry mechanism.

Each formula group is isolated. Valid bundles commit even when another group fails;
`Feature04_Column_Status` records the exact failed columns. Automatic retries use bounded
backoff and stop after five source attempts. Expected formula NULLs such as EMA200 with
fewer than 200 bars and SMI on a zero range are successful outcomes. Availability validation
checks every calculated observation, including candlestick lookbacks and conditional SMI/swing
state. A NULL where the formula requires a value is an error even on an older bar. Invalid
source rows restart warmup; their expected NULLs do not become false failures. If one member
fails, its complete dependency bundle is withheld from writes and becomes a retry target.

`Monitoring_Feature04` is finalized only when all eligible tickers are terminal. The
durable notification outbox waits until `telegram-monitor` has recorded the price message
as sent, then requests the separate Feature04 Telegram result. Telegram delivery failure
never rolls back calculated data.

`Feature04_Calculation_State` stores recent recursive and rolling state by
`(asset_type,ticker,timeframe,checkpoint_date)`. Retention and the maximum normal suffix are
derived from each market's `correction_lookback_sessions`; the initial bootstrap is an
explicit operator command:

```text
python bootstrap_states.py --dry-run
python bootstrap_states.py
```

The dry run rebuilds state from full history and shadow-compares the recent suffix with the
stored table without writing. The write run changes state only. It does not rewrite Feature04
output.

For the independent fixed-income daily and recovery crons, the outbox first sends the
related `Monitoring_Fixed_Income` result through `telegram-monitor`. The Feature04
completion remains gated until that price notification is recorded sent.

Required Railway variables:

- `DATABASE_URL=${{Postgres.DATABASE_URL}}`
- `TELEGRAM_NOTIFY_URL=http://${{telegram-monitor.RAILWAY_PRIVATE_DOMAIN}}:8080/notify`
- `TELEGRAM_NOTIFY_SECRET=${{telegram-monitor.TELEGRAM_NOTIFY_SECRET}}`
