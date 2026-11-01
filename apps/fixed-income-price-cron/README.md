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

Start commands are explicit (live, `.railway/railway.ts`, read 2026-11-01):

```text
python fixed_income_update.py --market ID --mode daily
python fixed_income_update.py --market ID --mode recovery
python fixed_income_update.py --market US --mode daily
python fixed_income_update.py --market US --mode recovery
```

The recovery roles re-run only the latest completed session, one hour after the daily role. `recovery_window.py`
(re-verify the latest `correction_lookback_sessions` stored sessions plus newer missing candidates, oldest first)
exists but no service runs it. Neither path refills a date older than the latest stored one, or a single series missing
on a date the other series have (ERRORS M324). The material UPSERT predicate avoids writes when the final payload is
identical, so an idempotent recovery does not enqueue Feature04.

## Final-candle contract

- The loader validates the provider-resolved timezone. TradingView labels a fixed-income `1D` bar with its session
  start in the provider's zone (`provider_timezone_name`, America/New_York for both markets).
- `Fixed_Income_Market_Schedule.source_date_mapping` defines the provider convention for each market. Both ID and US
  use `PROVIDER_SESSION_START` (ERRORS M323, migration `20261101_002`): the label is read in the provider's zone
  against the session start (`provider_session`, ID 1700-1700, US 1900-1730); a label at or after the start belongs to
  the next day's session, a weekend date moves on to Monday. No daylight-saving date is written in code. The worker
  does not select this behavior by ticker or country.
- Two source bars on one date stop the series with `SOURCE_DATE_COLLISION` (nothing written), so a change in the
  source's labels shows up as an error instead of shifted rows.
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
