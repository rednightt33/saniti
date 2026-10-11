"""Reviewed per-column formulas and usage; consumed by the forward migration generator."""
from engine import COLUMNS, PATTERNS, library_contract


def specifications():
    contract=library_contract()
    specs={
      'ticker':('Identity','IDX security code copied from source ticker.','ticker','1 source row','symbol','Identify a security without joining the current universe.','Join exact ticker identifiers; do not infer historical index membership.'),
      'trade_date':('Identity','Trading observation date copied from source date.','date','1 source row','date','Order each security history and match exact observed dates.','This is the bar date, not its publication or prediction timestamp.'),
      'timeframe':('Identity','Verified daily timeframe copied exactly from source.','timeframe = Daily','1 source row','interval','Partition only daily observations.','No intraday or fabricated weekly/monthly bars are represented.'),
      'sma_20':('Price','Unweighted mean of 20 observed closes.','TA-Lib SMA(close,20)','20 valid bars','IDR','Use as a rolling price baseline.','A level is not a return; avoid comparing raw levels across tickers.'),
      'sma_50':('Price','Unweighted mean of 50 observed closes.','TA-Lib SMA(close,50)','50 valid bars','IDR','Use as a longer rolling price baseline.','Do not fill insufficient history or infer a predictive crossing rule.'),
      'ema_12':('Price','Fast exponentially weighted close; alpha=2/13.','Seed=SMA(first12 closes); EMA[t]=EMA[t-1]+2/13*(close[t]-EMA[t-1])','12 valid bars; full available history used','IDR','Measure the recent price baseline with greater recent weight.','Seed sensitivity persists beyond the first valid bar; raw price levels are not comparable returns.'),
      'ema_26':('Price','Slow exponentially weighted close; alpha=2/27.','Seed=SMA(first26 closes); EMA[t]=EMA[t-1]+2/27*(close[t]-EMA[t-1])','26 valid bars; full available history used','IDR','Measure the slower price baseline against EMA12.','Seed and source corrections affect every later recursive value.'),
      'rsi_14':('Price Positioning','Wilder gain/loss oscillator on 14 consecutive close changes, scaled 0–100.','TA-Lib RSI(close,14): SMA seed of 14 gains/losses; RMA alpha=1/14; 100*gain/(gain+loss); both-zero uses native 0','15 valid bars; full available history used','index points','Use relative momentum as a numeric covariate.','Bounds do not provide probabilities; native flat-price 0 and TradingView edge-case parity are not verified.'),
      'macd':('Price Positioning','Difference of the stored fast and slow EMA price baselines.','ema_12 - ema_26; independently SMA-seeded EMAs, not TA-Lib MACD internal fast reseeding','26 valid bars; full available history used','IDR','Use signed fast-minus-slow momentum relative to its price scale.','Magnitude depends on price level; no direct cross-stock ranking or guaranteed signal.'),
      'macd_signal':('Price Positioning','Nine-period EMA of valid MACD line observations.','Seed=SMA(first9 valid macd); signal[t]=signal[t-1]+0.2*(macd[t]-signal[t-1])','34 valid bars; full available history used','IDR','Compare the line with a smoothed momentum baseline.','Signal seed/history can differ from TradingView; crossings have no validated hit rate.'),
      'macd_histogram':('Price Positioning','Difference between MACD line and its nine-period signal.','macd - macd_signal','34 valid bars','IDR','Measure signed deviation of momentum from its smoothed baseline.','Histogram sign is descriptive; it does not predict the next return.'),
      'atr_14':('Volatility','Wilder average of 14 true ranges using prior observed close.','TA-Lib ATR(high,low,close,14): TR=max(high-low,abs(high-prev_close),abs(low-prev_close)); first TR excludes bar1; SMA seed then RMA alpha=1/14','15 valid bars; full available history used','IDR','Measure absolute price-range volatility, without direction.','TradingView may include first-bar high-low; ATR levels depend on price scale and are not direction signals.'),
      'bb_upper_20':('Volatility','Upper 20-period Bollinger band, population standard deviation multiplier 2.','SMA20(close) + 2*sqrt(sum((close-SMA20)^2)/20)','20 valid bars','IDR','Measure an upper dispersion boundary around SMA20.','A band is not a confidence interval or calibrated reversal probability.'),
      'bb_middle_20':('Price','Middle 20-period Bollinger band, identical to SMA20.','SMA20(close)','20 valid bars','IDR','Provide the center of the paired Bollinger boundaries.','It duplicates sma_20; account for this redundancy in later model design.'),
      'bb_lower_20':('Volatility','Lower 20-period Bollinger band, population standard deviation multiplier 2.','SMA20(close) - 2*sqrt(sum((close-SMA20)^2)/20)','20 valid bars','IDR','Measure a lower dispersion boundary around SMA20.','Bands can be crossed repeatedly; do not treat them as fixed support or predictive thresholds.'),
      'calculation_version':('Metadata','Version binds formulas, seeds and pinned TA-Lib versions.','engine.VERSION','1 calculation','version','Group or audit rows under an exact reproducible implementation.','Never treat a version identifier as a numerical training feature.'),
      'calculated_at':('Metadata','Timezone-aware execution time of the last changed output row.','UTC execution timestamp; unchanged UPSERT preserves existing timestamp','1 calculation','timestamp','Audit the calculation execution independently of the bar date.','A calculation timestamp is not historical source availability or publication time.'),
    }
    for col,name in PATTERNS.items():
        info=contract['patterns'][name]
        title=col[4:].replace('_',' ')
        specs[col]=('Price Positioning',f'Native TA-Lib {title} pattern recognition code from historical OHLC.',
                    f"TA-Lib {name}(open,high,low,close), default candle settings; parameters={info['parameters']}; native signed integers including non-100 codes retained",
                    f"{info['lookback']+1} valid OHLCV bars; lookback={info['lookback']}",'signed pattern code',
                    f'Use {title} recognition as an independent numerical covariate, allowing coexisting patterns.',
                    'Zero means available non-detection; NULL means unavailable. Sign is native library convention, not a probability or proof of IDX predictive value. TradingView candlestick equivalence NOT VERIFIED.')
    assert set(specs)==set(COLUMNS)
    return specs
