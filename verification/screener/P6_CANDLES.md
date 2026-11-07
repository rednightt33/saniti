# P6 — 20 candlestick patterns in the Backtest core, used by the Screener

EXEC-SCREENER-FLOW-CANDLES P6 (unit C). User decisions: "2A" (built in the Backtest core, used by the Screener and later
the Backtest; `engine_version` changes), K2 "A" (an approval path for Backtest-core changes in the tripwire, like the
worker baseline, plus a test that the results of every existing condition stay the same), and 2026-11-07 "Parallel,
alright" (P6 is built while unit B waits for merge). The proposal the user approved (FUTURE_PLAN SCREENER-FLOW-CANDLES,
commit 5f719923, section B) is the source of the list and the guards.

## 1. The patterns (10 bullish, 10 bearish, in pairs)
Hammer / Hanging Man; Inverted Hammer / Shooting Star; Dragonfly Doji / Gravestone Doji; Bullish / Bearish Marubozu;
Bullish / Bearish Engulfing; Bullish / Bearish Harami; Piercing Line / Dark Cloud Cover; Tweezer Bottom / Tweezer Top;
Morning Star / Evening Star; Three White Soldiers / Three Black Crows.

## 2. Design
- Candle primitives in the Backtest core: body, upper and lower shadow, range, body midpoint, body direction, and the
  prior trend (close against its own SMA or a short slope, parameterized). Every pattern is a parameterized composition
  of the primitives in one registry, with one evaluator; no pattern has its own hand-coded geometry outside it.
- Thresholds (body as % of range, shadow multiples, trend length, tolerance for tweezers, the relaxed body gap for stars)
  are registry parameters with documented defaults, each with its plain meaning, min and max.
- IDX data guards: a day without trades or a suspended day (O=H=L=C with volume 0, or a missing bar) is never a pattern
  bar (not a doji); a range below a minimum (in price ticks of the bar's price band, derived from the price, not a
  hand list per stock) does not qualify; prices are the adjusted series the core already uses; gaps are rare on IDX, so
  star patterns use the relaxed body gap.
- Signals are events: "occurred on the evaluated bar" or "within N sessions" (the existing EVENT within rule), usable
  with the operators (OPERATORS.md) as a 0/1 signal (kind F).
- Screener: each pattern a catalog `pattern` entry generated from the core registry (name, side, parameters), shown in
  Add a condition with its parameters.

## 3. Guarantees
- Tripwire (K2 A): `scripts/screener/check_backtest_untouched.mjs` gains an approval record for Backtest-core changes (as
  `backtest_worker_baseline.json` for the worker): a change passes only when the record names the new content hash and
  the user's decision; without it the tripwire fails as today.
- Every existing condition of the Backtest core gives the same result as before on the same data (a test over the
  existing conditions and fixtures, before vs after).

## 4. Tests
- Synthetic bars: a positive and a negative case per pattern and per guard.
- Symmetry: mirrored prices turn each bullish pattern into its bearish pair.
- Independent recomputation (own code from the definitions), and on the fixture stocks a frequency table per pattern.
- Comparison with Feature 04's `cdl_*` columns where the definitions match (Feature 04 has cdl_hammer, cdl_doji,
  cdl_engulfing): the differences are explained, not forced to zero.
- Screener catalog, validation and page offer (Add a condition).
