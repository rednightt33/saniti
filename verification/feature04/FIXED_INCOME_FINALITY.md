# Fixed-income final close and Feature04 validation

Date: 2026-10-12
Scope: Railway `lucid-patience` / `dev`, primary `Postgres`.

## Decision and source ownership

The user approved separate Indonesia and US close/recovery jobs and authorized execution
after the old source location and Git push ability were confirmed. The old daily and
recovery deployments were Railway CLI uploads with no repository/branch. The controlled
replacement is `apps/fixed-income-price-cron` in `rednightt33/saniti`.

All 48 source series are selected from `Universe_Fixed_income`. The application contains
no ticker roster. The universe now stores each exact TradingView symbol and unit, while
`Fixed_Income_Market_Schedule` stores country, timezone, close time, finality delay and
enabled state.

## Database rollout

Migration `20261012_001_finalize_fixed_income_markets.sql`, SHA256
`0b406080b68c16512a820a922a2be5573722136056bfd96b8e41c2922f02b7fc`, ran first in a
transaction ending `ROLLBACK`. Readback after rehearsal found no schedule table and no new
price columns. Exact rehearsal deployment: `21755d0f-ec0c-4bdb-b1a7-9c1106d31d1c`
(`SUCCESS`).

Live apply deployment `fec4a73a-1655-494a-b4ad-84e661bba269` reached `SUCCESS` and read
back:

- two enabled markets: ID / Indonesia / `Asia/Jakarta` / 16:00 + 60 minutes; US /
  United States / `America/New_York` / 17:00 + 60 minutes;
- 48/48 universe ticker/metric rows with explicit source symbol and unit;
- 121,649 `Price_Fixed_Income` rows, all initialized as completed sessions;
- zero rows missing `market_close_at` or `finalized_at`;
- zero active Feature04 claims during migration.

Historical `source_bar_time` remains NULL because the old loader did not retain the exact
provider timestamp. The new loader populates it. A recent-session re-query is required
before claiming current final-close verification.

## Code validation

- Fixed-income loader and Telegram monitor: 25 tests passed.
- The tests cover Indonesia close delay, weekends, US standard/daylight close conversion,
  exact provider-timezone session mapping, strict target-date selection, nullable bond
  volume, invalid OHLC, TLS fail-closed behavior, monitoring states, framing, and retained
  provider timestamps.
- The Indonesia dry-run exposed TradingView's bond convention: Friday observations carry
  a weekend raw label. The configured `CURRENT_OR_PREVIOUS_BUSINESS_DAY` rule maps it to
  Friday while preserving the original timestamp.
- The US dry-run exposed a different convention: each raw UTC label belongs to the next
  business session. The configured `NEXT_BUSINESS_DAY` rule maps Thursday to Friday and
  Friday to Monday. Market behavior comes from `Fixed_Income_Market_Schedule`, not a ticker
  or country branch in application code.
- Final dry-run deployments `75565757-5da3-4e75-b09a-172e57b52f8b` (Indonesia) and
  `38b5c160-0cbe-4579-9917-8f12c86792d9` (US) each found every expected 2026-10-09 series:
  22/22 and 26/26 respectively.
- Feature04 worker and bounded pipeline read bonds only where `metric_type='price'`,
  `Timeframe='1D'`, and `is_final=true`.

## Cutover and canary

Pending Git push, four-service Railway cutover, five-session market re-query, Feature04
terminal-state verification, exact deployment IDs, and temporary-resource cleanup.
