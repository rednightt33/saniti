# IDX daily price cron

This short-lived Railway app updates `public."Price_Stock_Indonesia_IDX"` from TradingView without creating a local CSV. The same code is deployed as two Railway cron services with explicit roles.

## Services and schedules

Railway evaluates cron schedules in UTC.

| Railway service | UTC schedule | Jakarta time | Start command | Purpose |
| --- | --- | --- | --- | --- |
| `idx-price-cron` | `0 10 * * *` | 17:00 daily | `python price_update.py --mode daily` | Query the full live ticker universe for today's candle. |
| `idx-price-recovery-cron` | `0 23 * * *` | 06:00 the following day | `python recovery_window.py` | Reverify the configured recent completed sessions for the full live universe. |

`Run now` follows the selected service's explicit role:

- On `idx-price-cron`, it queries every current `IDX_Stock_Universe."Ticker"` for today's date.
- On `idx-price-recovery-cron`, it reads `correction_lookback_sessions` from
  `Equity_Market_Schedule` and re-queries the full universe for each of the latest five
  observed sessions, oldest first. A latest completed candidate absent from storage is also
  checked so a missing new session can be created.

## Candle-date and duplicate safety

- The target date is the latest session whose configured IDX close plus finality delay has
  passed. A TradingView row is accepted only when its candle timestamp resolves to that exact
  target date in Asia/Jakarta.
- Accepted rows retain `source_bar_time`, `market_close_at`, `is_final=true`, and
  `finalized_at`. Feature04 reads and reacts only to final Daily rows.
- A prior/last-available candle is never relabeled or written as today's candle.
- If TradingView has no current-date candle yet, no prior candle is written. The run is recorded as `SKIPPED` with `NO_CURRENT_CANDLE` when the market broadly returns only prior candles.
- Exact-date rows that are available may still be written during a partial run; unavailable tickers remain in the monitoring missing list.
- Prices are deduplicated in memory and bulk-upserted through a temporary PostgreSQL staging table.
- The `Price_Stock_Indonesia_IDX` primary key `(ticker, date)` is the final duplicate guard. Re-running the same ticker/date updates that row and preserves all other dates.
- `ingestion_time` records the PostgreSQL statement time for each successful bulk upsert. Every row in one batch shares one timezone-aware timestamp, and a repeated `(ticker, date)` upsert refreshes it. Rows that predate this field remain null because their exact ingestion time is unknown.
- A PostgreSQL advisory lock prevents the DAILY and RECOVERY services from updating prices concurrently.

## Monitoring rules

- Every service execution receives a new `execution_id`, so manual and scheduled attempts remain separate history rows.
- `trigger_source` is inferred as `SCHEDULED` inside the service's narrow schedule window and `MANUAL` outside it because Railway does not expose an official runtime variable that distinguishes **Run now** from a scheduled cron start.
- Expected symbols come from the live `IDX_Stock_Universe`, grouped by `Exchange` and `Security Type`.
- `query_time` records the UTC timestamp immediately before TradingView requests begin.
- There is no automatic query outside DAILY and the configured recovery window. Missing
  symbols after recovery are marked `NEEDS_REVIEW`.
- Weekend runs are recorded as `SKIPPED` without querying TradingView.
- If a weekday DAILY run dies before writing monitoring, recovery derives its scope from universe tickers still absent from the price table for that date.
- After the monitoring transaction commits, the service sends its `execution_id` to the separate `telegram-monitor` service. Temporary cold-start or network failures are retried four times.
- Telegram delivery is downstream: a notification failure is logged but never rolls back price or monitoring data and never causes another TradingView query.
- In the same transaction as the price upsert, the service opens `Monitoring_Feature04`
  and binds changed price rows to that execution. The database trigger coalesces those rows
  per ticker. After commit, `feature-04-worker` calculates eligible tickers. The price
  Telegram message is sent first; the Feature04 outbox remains gated until that delivery
  is recorded.

## Runtime

Both services require:

```text
DATABASE_URL=${{Postgres.DATABASE_URL}}
TELEGRAM_NOTIFY_URL=http://${{telegram-monitor.RAILWAY_PRIVATE_DOMAIN}}:8080/notify
TELEGRAM_NOTIFY_SECRET=<shared Railway secret>
```

The script must exit after each run so Railway can start the next cron execution.
The entrypoint flushes its logs and then terminates the process explicitly, preventing a completed run from remaining `Active` because a dependency left an idle background resource open.
`NEEDS_REVIEW` is a completed cron outcome recorded in `Monitoring_Price_ALL`, so it exits with code `0`; only an actual `FAILED` run exits non-zero.
