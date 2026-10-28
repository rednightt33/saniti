explain (analyze, buffers, settings, timing)
select distinct on (ticker) ticker, trade_date, close, sma_20, sma_50, ema_12, ema_26, ema_50, ema_200, rsi_14, macd, macd_signal, macd_histogram, atr_14, bb_upper_20, bb_middle_20, bb_lower_20, adx_14
from public."Feature_04_Technical_Indicator"
where asset_type = 'equity' and timeframe = 'Daily' and trade_date >= date '2026-10-27' - 30
order by ticker, trade_date desc ;;
explain (analyze, buffers, timing)
select u."Ticker", f.*
from public."IDX_Stock_Universe" u
cross join lateral (
  select trade_date, close, sma_20, sma_50, ema_12, ema_26, ema_50, ema_200, rsi_14, macd, macd_signal, macd_histogram, atr_14, bb_upper_20, bb_middle_20, bb_lower_20, adx_14
  from public."Feature_04_Technical_Indicator" f
  where f.ticker = u."Ticker" and f.timeframe = 'Daily' and f.asset_type = 'equity'
  order by f.trade_date desc limit 1) f ;;
explain (analyze, buffers, timing)
select ticker, trade_date, close, sma_20, sma_50, ema_12, ema_26, ema_50, ema_200, rsi_14, macd, macd_signal, macd_histogram, atr_14, bb_upper_20, bb_middle_20, bb_lower_20, adx_14
from public."Feature_04_Technical_Indicator"
where asset_type = 'equity' and timeframe = 'Daily'
  and trade_date = (select max(trade_date) from public."Feature_04_Technical_Indicator" where asset_type = 'equity')
