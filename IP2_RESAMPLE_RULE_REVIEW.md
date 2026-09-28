# IP2 resample rule review

This review supports migration `20260928_002_seed_resample_rules.sql` (implementation plan IP2, solution 1). The
migration is **prepared, not applied**.

## How to read it

`AI_column_catalog.resample_aggregation` tells `saniti.resample()` how one column of a daily table aggregates to a
week or a month.

- Aggregation happens within one entity and one full table grain: ticker, plus broker, investor type and board where
  the table has them.
- Weekly and monthly periods are always built from the daily rows. Monthly is never built from weekly.
- A column without a rule fails closed with `RESAMPLE_RULE_MISSING`.

Sources for each column's meaning:

- the catalog definition (`Column_Catalog.definition`, which is copied to `AI_column_catalog.description`);
- the table's check constraints, as documented in `DATABASE_SCHEMA.md`.

Inspection method: repository only. Live read-only database access is not reachable from the working environment,
because the PostgreSQL TCP proxy timed out. The migration's preflight therefore re-checks the following on the live
catalog, and aborts if any check fails:

- each column exists;
- each column is a numeric measure of a dated table;
- no column carries a conflicting rule;
- no rule exists outside the seed.

## Columns seeded (27)

| Table | Column | Rule | Supporting definition |
|---|---|---|---|
| Price_Stock_Indonesia_IDX | open | FIRST | "Opening price." The first open of the period. |
| Price_Stock_Indonesia_IDX | high | MAX | "Highest price." Check: `low <= open <= high`. |
| Price_Stock_Indonesia_IDX | low | MIN | "Lowest price." |
| Price_Stock_Indonesia_IDX | close | LAST | "Closing price." The last close of the period. |
| Price_Stock_Indonesia_IDX | volume | SUM | "Trading volume reported by the source" for one trading date. |
| Feature_01_Stock_Daily | close | LAST | "Closing price for the ticker on the trading date." |
| Feature_01_Stock_Daily | volume | SUM | "Trading volume reported for the ticker on the trading date." |
| IDX_Broker_Summary | Buy Value | SUM | "Gross purchase value for the key combination" (one date). |
| IDX_Broker_Summary | Sell Value | SUM | "Gross sale value for the key combination." |
| IDX_Broker_Summary | Net Value | SUM | "Buy Value minus Sell Value." Check `Net Value = Buy Value - Sell Value`, so the sum over days equals the period's buy minus sell. |
| IDX_Broker_Summary | Buy Lots | SUM | "Number of lots purchased." |
| IDX_Broker_Summary | Sell Lots | SUM | "Number of lots sold." |
| IDX_Broker_Summary | Net Lots | SUM | "Buy Lots minus Sell Lots." Check enforces it. |
| Feature_02_Broker_Rolling | buy_value_1d | SUM | "Source Buy Value for this date, ticker, broker, investor type and board." |
| Feature_02_Broker_Rolling | sell_value_1d | SUM | "Source Sell Value for this date, ..." |
| Feature_02_Broker_Rolling | net_value_1d | SUM | "Buy value minus sell value for this date, ..." Check `net_value_1d = buy_value_1d - sell_value_1d`. |
| Feature_02_Broker_Rolling | buy_lots_1d | SUM | "Source Buy Lots for this date, ..." |
| Feature_02_Broker_Rolling | sell_lots_1d | SUM | "Source Sell Lots for this date, ..." |
| Feature_02_Broker_Rolling | net_lots_1d | SUM | "Buy lots minus sell lots for this date, ..." Check enforces it. |
| Feature_03_Stock_Broker_Daily | total_buy_value | SUM | "Sum of all broker buy_value_1d for the ticker, date and board." |
| Feature_03_Stock_Broker_Daily | total_sell_value | SUM | "Sum of all broker sell_value_1d for the ticker, date and board." |
| Feature_03_Stock_Broker_Daily | foreign_net_value | SUM | "Sum of daily net value for source Foreign Investor Type across all brokers." |
| Feature_03_Stock_Broker_Daily | domestic_net_value | SUM | "Sum of daily net value for source Domestic Investor Type across all brokers." |
| Feature_03_Stock_Broker_Daily | institutional_net_value | SUM | "Sum of daily broker net value where current broker_classification is Institutional-heavy." Additive, but see note 1. |
| Feature_03_Stock_Broker_Daily | retail_net_value | SUM | Same form, Retail-heavy. See note 1. |
| Feature_03_Stock_Broker_Daily | mixed_net_value | SUM | Same form, Mixed. See note 1. |
| Feature_03_Stock_Broker_Daily | niche_net_value | SUM | Same form, Niche. See note 1. |

**Note 1.** These four sums are arithmetically additive. However, the classification is today's
(`value_time_basis = CURRENT_STATE`, migration `20260927_006`), so the weekly or monthly sum carries the same
current-state caveat as the daily value. It still triggers the `CURRENT_STATE_COLUMN` warning, and a point-in-time
request still refuses it.

## Columns deliberately left NULL

| Table | Columns | Why |
|---|---|---|
| Price_Stock_Indonesia_IDX | company_name, tradingview_symbol, source, timeframe, query_date, ingestion_time | Identity, provenance or timestamps, not measures. |
| Feature_01_Stock_Daily | sector, industry | Current-state classification repeated from another grain. |
| Feature_01_Stock_Daily | return_1d_pct, return_5d_pct, return_20d_pct, return_60d_pct, abs_return_1d_pct | Returns are never summed; a period return comes from the resampled `close` (LAST) divided by the prior period's close. |
| Feature_01_Stock_Daily | close_1d_ago, close_5d_ago, close_20d_ago, close_60d_ago | Lagged prices measured in trading observations, not periods. |
| Feature_01_Stock_Daily | volatility_*_ann_pct, volatility_*_change_pct | Rolling statistics. |
| Feature_01_Stock_Daily | volume_avg_20d, volume_std_20d, volume_ratio_20d, volume_zscore_20d | Rolling average, deviation, ratio and z-score. |
| Feature_01_Stock_Daily | high_20d, high_60d, drawdown_20d_pct, drawdown_60d_pct | Rolling windows. |
| IDX_Broker_Summary | Avg Buy, Avg Sell | Averages. A period average price would need value divided by lots, not an aggregate of daily averages. |
| Feature_02_Broker_Rolling | broker_classification | Current-state metadata. |
| Feature_02_Broker_Rolling | net_value_5d/20d/60d, net_lots_5d/20d/60d | Rolling 5/20/60-date sums. |
| Feature_02_Broker_Rolling | buy_days_*, sell_days_*, active_days_*, stock_trading_days_* | Counts inside a rolling window. |
| Feature_02_Broker_Rolling | buy_day_ratio_*, buy_share_active_days_* | Ratios. |
| Feature_02_Broker_Rolling | net_value_zscore_*, net_value_percentile_* | Z-score and percentile. |
| Feature_02_Broker_Rolling | positive_net_value_20d, largest_buy_day_20d, largest_buy_day_share_20d | Rolling window values and a share. |
| Feature_02_Broker_Rolling | calculated_at | Materialization timestamp. |
| Feature_03_Stock_Broker_Daily | active_broker_count, net_buy_broker_count, net_sell_broker_count | Counts of distinct brokers per day; the same broker is counted every day, so they do not add up across days. |
| Feature_03_Stock_Broker_Daily | net_buy_broker_ratio, top3_buyer_share, broker_concentration_hhi | Ratio, share and concentration. |
| Feature_03_Stock_Broker_Daily | top_buyer, top_buyer_net_value, top_seller, top_seller_net_value, top3_buyer_net_value | Daily top-N; a period's top-N is not an aggregate of daily top-N. |
| Feature_03_Stock_Broker_Daily | positive_net_value_total | See the ambiguous list below. |
| Feature_03_Stock_Broker_Daily | calculated_at | Materialization timestamp. |
| IDX_Stock_Universe, IDX_Broker_Profile, IDX_Stock_Universe_History, IDX_Broker_Profile_History | all | Reference tables without a daily time column. |

## Ambiguous columns that need business approval

None of these are seeded. Each needs a decision before it gets a rule:

1. **End-of-period snapshots of rolling metrics.** For example, `net_value_20d`, `close_20d_ago`, `high_20d` and
   `volatility_20d_ann_pct` taken as the value on the period's last trading day (`LAST`). IP2 allows this only when
   approved as an end-of-period snapshot. The risk is that "the weekly 20-date net value" reads like a weekly measure,
   when it is really a rolling window that ends on Friday.
2. **`positive_net_value_total` (Feature 03).** Summing it over a week gives the sum of each broker's positive *daily*
   nets. That is not the positive part of each broker's *weekly* net.
3. **The four current-classification sums (note 1).** They are seeded because they are additive. If the business
   prefers to block every current-state column from derived frequencies, a forward migration can set them back to
   NULL.

## Rollback

A wrong rule is corrected by a new forward migration that sets that column back to NULL. The schema is never rolled
back destructively.
