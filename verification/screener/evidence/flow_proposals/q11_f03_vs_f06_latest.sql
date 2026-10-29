SELECT count(*) pairs,
  count(*) FILTER (WHERE abs(a.foreign_net_value - b.foreign_net_1d) > 0.5) fnet_diff,
  count(*) FILTER (WHERE abs(a.total_buy_value - (b.foreign_buy_1d + b.domestic_buy_1d)) > 0.5) value_diff,
  count(*) FILTER (WHERE abs(b.foreign_net_1d + b.domestic_net_1d) > 0.5) f_plus_d_nonzero,
  count(*) FILTER (WHERE b.foreign_buy_freq_1d + b.domestic_buy_freq_1d <> b.foreign_sell_freq_1d + b.domestic_sell_freq_1d) freq_unbalanced,
  count(*) FILTER (WHERE b.ticker IS NULL) f06_missing, count(*) FILTER (WHERE a.ticker IS NULL) f03_missing
FROM (SELECT * FROM "Feature_03_Stock_Broker_Daily" WHERE date = DATE '2026-10-27') a
FULL JOIN (SELECT * FROM "Feature_06_Foreign_Domestic" WHERE trade_date = DATE '2026-10-27') b
  ON a.ticker = b.ticker AND a.market_board = b.market_board
