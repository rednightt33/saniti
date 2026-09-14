# Feature 03 v2 — stock broker and investor daily structure

`Feature_03_Stock_Broker_Daily` compresses broker-level flows into one row per `date × ticker × market_board`. `Regular`, `Nego`, and `Tunai` are always separate; consumers should filter `market_board = 'Regular'` when they want regular-market structure. All symbols present in Broker Summary remain eligible, including instruments outside the current stock universe.

## Calculation contract

The refresh has two deliberate aggregation paths. `foreign_net_value` and `domestic_net_value` sum the point-in-time `Feature_02_Broker_Rolling.investor_type` rows directly. They represent investor identity from the source Broker Summary, not broker domicile. All other broker-level metrics first sum Domestic and Foreign activity per broker, then aggregate those broker totals. This keeps `active_broker_count`, rankings, and HHI as broker—not investor-type-row—metrics.

`active_broker_count` includes a broker with any nonzero gross value or lots. Positive, negative, and zero-net brokers are distinct: zero-net active brokers remain in the denominator of `net_buy_broker_ratio` but do not enter its numerator or `net_sell_broker_count`.

Source Domestic/Foreign investor flows and current Institutional-heavy/Retail-heavy/Mixed/Niche broker classifications are two independent axes. A foreign broker can serve a domestic investor and vice versa. An unmatched future broker remains included in gross totals, breadth, dominant-broker, and HHI calculations but is excluded from current broker-classification sums until its profile exists.

`top_buyer` is the broker with the greatest positive daily net value; `top_seller` is the broker with the lowest negative daily net value. Equal net values use broker code ascending. The seller value retains its negative sign. Top-three buyer value uses only positive-net brokers. Its share is null when total positive net value is zero.

For broker `i`, HHI uses `weight_i = ABS(net_value_i) / SUM(ABS(net_value))`, then sums `weight_i²`. It is null when every broker net value is zero. Higher values indicate net flow concentrated in fewer brokers.

## Validated historical coverage

The production backfill contains 2,268,015 rows. Board coverage is Regular 1,955,758 rows/3,942 tickers, Nego 300,796 rows/1,399 tickers, and Tunai 11,461 rows/1,117 tickers. Regular and Nego cover 2016-01-04 through 2026-08-31; Tunai begins 2016-01-06 and ends 2026-08-31.

The v1 results above are historical evidence only. The v2 full rebuild again produced 2,268,015 rows over the same date range. Every row passed `foreign_net_value + domestic_net_value = total daily net value`; independent 20-field raw checks passed for BBCA Regular, BBCA Nego, and ADRO Tunai on 2026-08-31. Complete current column formulas and null rules are active in `Feature_Catalog` version `v2`.

## Refresh operation

`refresh_feature_03_stock_broker_daily(changed_date, tickers)` transactionally replaces the affected date/ticker scope. A null date means all available history within the optional ticker scope. An empty ticker array is a safe no-op. The PostgreSQL advisory lock prevents concurrent Feature 03 refreshes.

The full historical command is:

```powershell
python scripts/backfill_feature_03.py --host <proxy-host> --port <proxy-port>
```

Feature 03 does not yet have an automatic worker. After a valid Broker Summary update, Feature 02 must be refreshed first, followed by Feature 03 for the same changed date/tickers. The existing Feature 01 worker does not calculate Feature 02 or Feature 03.

Use `scripts/validate_feature_03.py` for complete SQL reconciliation and `scripts/check_feature_03_sample.py` for independent raw-source samples. Safe joins are registered in `Feature_Relationship_Catalog`: Feature 02 joins many-to-one on `(ticker, market_board, date)`, while Feature 01 joins require a board filter or explicit Feature 03 preaggregation.
