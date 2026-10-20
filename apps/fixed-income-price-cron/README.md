# Fixed-income daily close jobs

This app is the Git source for four short-lived Railway cron roles. Each role reads its
series from `Universe_Fixed_income`, uses `Fixed_Income_Market_Schedule` for the market
clock, requests the exact TradingView `1D` candle, and writes only after that session is
complete. The application has no ticker roster and does not derive source symbols from
ticker spelling.

## Railway roles

Railway evaluates cron expressions in UTC. The US clock uses
`America/New_York`, so the 23:00 UTC job is one hour after a 17:00 New York close in
standard time and two hours after it during daylight time.

| Service | UTC schedule | Role |
|---|---:|---|
| `fixed-income-price-cron` | `0 10 * * *` | Indonesia final close, 17:00 WIB after the configured 16:00 close. |
| `fixed-income-price-recovery-cron` | `0 11 * * *` | Indonesia full latest-session verification/correction, 18:00 WIB. |
| `fixed-income-price-us-cron` | `0 23 * * *` | US final close, 06:00 WIB. |
| `fixed-income-price-us-recovery-cron` | `0 0 * * *` | US full latest-session verification/correction, 07:00 WIB. |

Start commands are explicit:

```text
python fixed_income_update.py --market ID --mode daily
python recovery_window.py --market ID
python fixed_income_update.py --market US --mode daily
python recovery_window.py --market US
```

Both recovery roles read `correction_lookback_sessions` from the market schedule and query
the complete market universe for each of the latest five observed completed sessions,
oldest first. An absent latest completed candidate is checked as well. This allows a
corrected final candle to replace an earlier value. The material UPSERT predicate avoids
writes when the final payload is identical, so an idempotent recovery does not enqueue
Feature04.

## Final-candle contract

- The loader validates the provider-resolved timezone and starts from the UTC calendar
  component that TradingView's fixed-income `1D` protocol returns as its raw chart label.
- `Fixed_Income_Market_Schedule.source_date_mapping` defines the provider convention for
  each market. Indonesia maps weekend labels to the preceding business day; the US maps
  each raw label to the next business day. The worker does not select this behavior by
  ticker or country.
- The original timestamp remains in `source_bar_time`, and only a candle that resolves to
  the exact target business date can be accepted.
- `market_close_at` is calculated from the selected market row and observation date.
- The job refuses to load a target session before `market_close_at` plus
  `finality_delay_minutes`.
- Accepted rows store `source_bar_time`, `market_close_at`, `is_final=true`, and
  `finalized_at`.
- OHLC values must be finite, nonnegative, and internally consistent. Bond volume may be
  NULL because TradingView does not expose it for every series.
- `Price_Fixed_Income` keeps one row per source symbol/date/metric/timeframe. Only a
  material source correction refreshes `ingestion_time`.

Feature04 reads only `metric_type='price'`, `"Timeframe"='1D'`, `is_final=true` rows.
The database trigger enqueues only a material final price change. A monitoring row then
binds changed tickers to the market execution. Telegram receives the price result first;
the Feature04 outbox remains gated until that delivery is recorded.

## Monitoring

`Monitoring_Fixed_Income` records the market, target session, exact-date final count,
material-change count, missing series, service, and run origin. `updated_series` retains
its existing Telegram meaning: exact-date series verified during the run.

Scheduled/manual origin remains inferred because Railway exposes no official Run Now
marker. A 90-minute tolerance accommodates the fixed 23:00 UTC US cron across daylight
saving changes.

## Runtime variables

All four roles require:

```text
DATABASE_URL=${{Postgres.DATABASE_URL}}
TELEGRAM_NOTIFY_URL=http://${{telegram-monitor.RAILWAY_PRIVATE_DOMAIN}}:8080/notify
TELEGRAM_NOTIFY_SECRET=${{telegram-monitor.TELEGRAM_NOTIFY_SECRET}}
TRADINGVIEW_VERIFY_TLS=true
```

TLS verification is fail-closed. The script exits after every attempt; `FAILED` returns a
nonzero code, while a reviewable missing-candle or holiday result remains in monitoring.

## Validation

```bash
python -m pip install -r requirements-dev.txt
pytest -q test_fixed_income_update.py
```

## Selected-date/session repair (2026-10-20)

The provider-session verification reader requires migration `20261013_011_verify_fixed_income_sessions.sql` before rollout. `provider_timezone_name` and `provider_session` verify TradingView metadata; they do not redefine market closing clocks. The one-off ID+US selected-date repair, validation evidence and live blocker are documented in `verification/fixed_income_session_repair/README.md` at repository root. Migration and six-date cleansing completed and independently verified on2026-10-20. Compatible code rollout is recorded separately in RAILWAY_CHANGELOG.md.
