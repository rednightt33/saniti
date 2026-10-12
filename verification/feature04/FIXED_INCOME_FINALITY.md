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
`Fixed_Income_Market_Schedule` stores country, timezone, close time, finality delay,
source-label mapping and enabled state.

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

- Fixed-income loader and Telegram monitor: 30 tests passed.
- The tests cover Indonesia close delay, weekends, US standard/daylight close conversion,
  schedule-driven source-label mapping, strict target-date selection, nullable bond
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

Git commit `5385325` is the deployed main revision. Exact successful Railway deployments:

| Job | Schedule UTC | Deployment |
| --- | --- | --- |
| ID daily | `0 10 * * *` | `b43127d3-bae9-4498-acd9-eadaa24e843f` |
| ID recovery | `0 11 * * *` | `ebef2984-2cf2-47ed-926b-35d02a06a748` |
| US daily | `0 23 * * *` | `7ca45494-a5ed-4953-8370-09e1e8ab266c` |
| US recovery | `0 0 * * *` | `efe1a249-fa67-48d4-baa9-1376aa8dbf6a` |

Migration `20261012_002_configure_fixed_income_source_dates.sql`, SHA256
`bc12e2efb5bb156f2fa986ad98970116b74f57d67adac5dc04212656a66c4f8a`, was rehearsed
with rollback deployment `70bbf1e9-5d9d-4f79-a232-33e9b53adb9e` and applied by
`32f7d785-2b8c-4aa8-997d-1f873d0a9850`.

## Five-session live verification

Deployment `6764d42f-6b1b-4316-a97d-ae73e0d8d6b3` re-queried 2026-10-05 through
2026-10-09 for both markets. All ten monitoring runs are `SUCCESS`:

- Indonesia: five runs × 22 series = 110 final series, zero missing;
- United States: five runs × 26 series = 130 final series, zero missing;
- every row in the window has `is_final=true` and a retained `source_bar_time`;
- all 24 price tickers completed Feature04; 120/120 expected feature rows exist and
  `Feature_04_Technical_Indicator.close` has zero mismatch with the final source close;
- all 24 fixed-income queue rows are `DONE`; every price notification and every terminal
  Feature04 notification is `SENT`.

Idempotence deployment `191d9364-6094-49a7-a017-dbf94060f62c` re-queried US 2026-10-09,
verified 26/26 final series, wrote `changed_series=0`, and created a `SKIPPED` Feature04
execution with zero eligible tickers.

Runtime/schema audit deployment `3cb1c709-2d79-4d76-8ccf-f19122e74c5a` passed semantic
coverage for 148/148 active definitions. Schema-sync deployment
`4da6b1fb-3a06-43e6-9cad-d345b8f2abcc` regenerated the live 91-table schema export with
the market schedule classified as Reference. The temporary inspector/schema services and
both temporary sandboxes were deleted; final Railway IaC plan is up to date.
