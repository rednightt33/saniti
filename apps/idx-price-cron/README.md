# IDX daily price cron

This short-lived Railway app updates `public."Price_Stock_Indonesia_IDX"` from TradingView without creating a local CSV. The same code is deployed as two Railway cron services with explicit roles.

## Services and schedules

Railway evaluates cron schedules in UTC.

| Railway service | UTC schedule | Jakarta time | Start command | Purpose |
| --- | --- | --- | --- | --- |
| `idx-price-cron` | `0 10 * * *` | 17:00 daily | `python price_update.py --mode daily` | Query the full live ticker universe for today's candle. |
| `idx-price-recovery-cron` | `0 23 * * *` | 06:00 the following day | `python price_update.py --mode recovery` | Recover the latest completed session's missing symbols, then the session audit (S7). |

`Run now` follows the selected service's explicit role:

- On `idx-price-cron`, it queries every current `IDX_Stock_Universe."Ticker"` for today's date.
- On `idx-price-recovery-cron` (live start command `python price_update.py --mode recovery`, read
  from Railway 2026-10-31; it was `recovery_window.py` until a change outside any task around
  2026-10-13), it re-queries the symbols missing from the latest completed session's DAILY run, or
  every absent symbol when that run left no monitoring row.
- Then the session audit (`recovery_window.audit_sessions`, EXEC-PRICE-GAP-0917 S7, ERRORS M238)
  reads the trading calendar from TradingView's daily candles of the universe's index symbols (the
  stored dates are the fallback). A session of the correction window (`correction_lookback_sessions`)
  whose stored stock count is below 90 % of the median gets the same recovery for its missing
  symbols, so a session with no stored row at all is filled. An older session of the last 60
  calendar sessions that is short is not written (a back-dated insert needs the Feature 04 repair,
  ERRORS D26) but reported once as a `RECOVERY` / `NEEDS_REVIEW` row (`SHORT_SESSION: ...`) in
  `Monitoring_Price_ALL`, with its Telegram notice.
- `python recovery_window.py` (manual) re-queries the full universe for every session of the
  window; `--plan-only` prints the plan and the audit without running or reporting anything.

## Candle-date and duplicate safety

Universe entries classified as `index` may publish OHLC without volume. Those
bars retain SQL NULL volume; stocks still require a nonnegative source volume.
Index requests use no split adjustment, and the TradingView symbol is taken
from the universe mapping (for example IHSG → IDX:COMPOSITE).

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

## Intraday bars and features (`idx-intraday-cron`)

EXEC-INTRADAY-IDX and EXEC-INTRADAY-FEATURES (user go 2026-10-31).
- **Schedule:** `intraday_update.py --mode daily` runs Mon-Fri at 10:30 UTC (17:30 WIB).
- **Bars:** it loads the 5m, 15m, 1h and 4h bars of the stocks and IHSG into `price_stock_idx_intraday`. Each series
  gets the sessions since its newest stored bar plus 3 sessions to recheck; only completed sessions are written. In the
  same statement it queues the first changed bar of every stock series in `intraday_feature_queue`.
- **Features:** `intraday_features.run_queue` then computes Feature 01 (`refresh_feature_01_stock_intraday`) and
  Feature 04 (the unchanged `features/feature04` engine, from the state of each series) into
  `Feature_01_Stock_Intraday` and `Feature_04_Technical_Indicator_Intraday`. A failed item stays FAILED and is retried
  by the next run.
- **Notices:** a load error, a series whose scale changed (`SCALE_CHANGED`, needs a re-pull) or a failed feature item
  writes one NEEDS_REVIEW row to `Monitoring_Price_ALL` and sends the Telegram notice; a clean run sends nothing.
- **Manual runs:**
  - `--skip-features` loads only;
  - `python intraday_features.py --mode queue` works the queue;
  - `--mode backfill` recalculates whole series.
- **Image and deploy:**
  - the image is `Dockerfile.intraday` (TA-Lib and the three engine files);
  - the service is a CLI upload, `bash apps/idx-price-cron/deploy_intraday.sh` from the repository root;
  - the price crons keep `Dockerfile`; `intraday_features.py` imports TA-Lib only when it computes, so their build
    check (M318) passes without it.
- **Variables:** `DATABASE_URL`, `TELEGRAM_NOTIFY_URL`, `TELEGRAM_NOTIFY_SECRET` (references, as above).
