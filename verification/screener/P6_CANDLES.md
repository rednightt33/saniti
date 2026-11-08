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

## 5. Built (2026-11-07, branch of unit C, not merged)

Files: `apps/edge-bff/backtest/src/core/candle-registry.json` (the registry: every pattern a list of rules over the
candle primitives, its parameters with default, meaning, min and max, and the IDX tick bands), `candles.ts` (the one
evaluator: guards, trend, rules, `candleLookback`, `eventWithin`, `candleFormula`). The Screener's 20 catalog entries are
generated from it (`build-screener-registry.mjs` `candleEntries` -> `screener-registry.json` `candles` -> `catalog.ts`
`candleMetric`, group Candlestick); `transforms.ts` computes each with `candleSignal`. `conditions.ts` is unchanged and
no Backtest request reads the patterns yet. Tripwire: `scripts/screener/backtest_core_baseline.json` (K2 A).

Shared by every pattern: `trend` (average: the close of the session before candle 1 below, for a bullish pattern, or
above, for a bearish one, its `trend_length`-session average; change: below / above the close `trend_length` sessions
earlier; none) default average (marubozu: none; Hammer, Hanging Man, Inverted Hammer and Shooting Star cannot switch it
off: the trend is what tells each from its same-shape pair), `trend_length` 10 (2-100), `min_range_ticks` 3 (1-50: every
candle spans at least 3 ticks of its price band: Rp 1 below 200, 2 below 500, 5 below 2,000, 10 below 5,000, 25 from
5,000, counted band by band); where a long candle is needed `long_body` 1 (0-10) x the average body of the
`body_avg_length` 10 (1-100) sessions before candle 1. Guards on every candle: open, high, low and close above 0 and
consistent, volume above 0 (a day without trades, O=H=L=C with volume 0, or a missing value is never a candle; an index
without volume has none). Candles are numbered 1 (oldest) to n (the signal bar, where the pattern is flagged).

| Pattern (side) | Rules | Defaults |
|---|---|---|
| Hammer (bull, after a decline) / Hanging Man (bear, after a rise) | body <= body_max_pct % of range; lower shadow >= shadow_ratio x body; upper shadow <= short_shadow_pct % of range | 30 %, 2x, 10 % |
| Inverted Hammer (bull) / Shooting Star (bear) | body <= body_max_pct % of range; upper shadow >= shadow_ratio x body; lower shadow <= short_shadow_pct % of range | 30 %, 2x, 10 % |
| Dragonfly Doji (bull) / Gravestone Doji (bear) | body <= doji_body_pct % of range; upper (gravestone: lower) shadow <= short_shadow_pct % of range | 10 %, 10 % |
| Bullish / Bearish Marubozu | white (black); body >= body_min_pct % of range; body >= long_body x average body | 90 %, 1x |
| Bullish / Bearish Engulfing | 1 black (white), 2 white (black); open2 <= close1 (>=); close2 >= open1 (<=); body2 > body1 | none of its own |
| Bullish / Bearish Harami | 1 black (white) and long; body2 inside body1 (edges included); body2 <= inside_max_pct % of body1 | 50 % |
| Piercing Line / Dark Cloud Cover | 1 black (white) and long; 2 white (black); open2 beyond close1 (open_beyond close) or beyond low1 / high1 (range); closes at least penetration_pct % of body1 into it; not past open1, strictly (close2 < open1; dark cloud close2 > open1: a close equal to open1 does not fire) | close, 50 % |
| Tweezer Bottom / Top | 1 black (white), 2 white (black); lows (highs) at most tolerance_ticks price ticks apart | 1 tick |
| Morning / Evening Star | 1 black (white) and long; star body <= star_body_pct % of body1; relaxed gap: star body top <= close1 + star_overlap_pct % of body1 (evening: bottom >= close1 - ...); 3 white (black) closing at least penetration_pct % of body1 into it | 30 %, 10 % (-50..50; negative: a real gap), 50 % |
| Three White Soldiers / Black Crows | 3 white (black), each body >= body_min_pct % of its range, upper (lower) shadow <= short_shadow_pct %, body >= long_body x average; each opens inside the previous body and closes beyond the previous close | 50 %, 25 %, 1x |

Mirror (prices p -> M - p): Hammer <-> Shooting Star, Inverted Hammer <-> Hanging Man, every other pair <-> its pair.

Tests (2026-11-07):
- `apps/backtest-worker/tests/candles.test.ts` 13/13: a positive and a negative synthetic case per pattern; the guards
  (no trade, volume 0 or missing, a missing price, a missing close in the trend window or open in the average window,
  an inconsistent bar, the tick bands and their boundaries, the band-by-band count, a 2-tick candle of a harami, the
  star's relaxed gap and a real gap, the classic piercing open); the trend (average, change, too few sessions);
  parameter refusals with the field, the range and a right and a wrong example; symmetry on mirrored random bars (every
  pattern fires); the independent oracle (`tests/candles-oracle.mjs`) bar for bar on the 8 fixtures and on random bars
  across every price band with holes, days without trades and inconsistent bars; the exact lookback; `eventWithin`.
- `apps/backtest-worker/tests/conditions-unchanged.test.ts`: 1,629 digests of every existing condition (1,520 indicator,
  48 price-action, 56 flow on deterministic broker rows, 5 ranking and liquidity values) on the 8 fixtures, recorded with
  the core before P6 (engine_version c3a5f29a3848df7d, commit 8dea727c), equal after.
- Screener: `tests/core/candles.test.ts`, `tests/core/lookback.test.ts` (each pattern reads exactly its window),
  `tests/page/candles.test.ts` (Add a condition, search, card, refusals, a fixture run).

Frequency at the defaults on the fixture stocks (7 stocks, 9,014 bars; IHSG has no volume and shows none):

| Pattern | Signals | per 1,000 bars | Pattern | Signals | per 1,000 bars |
|---|---|---|---|---|---|
| Hammer | 155 | 17.2 | Hanging Man | 253 | 28.1 |
| Inverted Hammer | 207 | 23.0 | Shooting Star | 132 | 14.6 |
| Dragonfly Doji | 53 | 5.9 | Gravestone Doji | 31 | 3.4 |
| Bullish Marubozu | 324 | 35.9 | Bearish Marubozu | 406 | 45.0 |
| Bullish Engulfing | 163 | 18.1 | Bearish Engulfing | 184 | 20.4 |
| Bullish Harami | 195 | 21.6 | Bearish Harami | 150 | 16.6 |
| Piercing Line | 24 | 2.7 | Dark Cloud Cover | 23 | 2.6 |
| Tweezer Bottom | 296 | 32.8 | Tweezer Top | 261 | 29.0 |
| Morning Star | 23 | 2.6 | Evening Star | 16 | 1.8 |
| Three White Soldiers | 6 | 0.7 | Three Black Crows | 6 | 0.7 |

The range guard at 3 ticks leaves out 20 % of the stock bars (BBCA 11 %, UNVR 3 %, DEWI 22 %, GOTO 37 %, KOCI 49 %,
CLAY 29 % with 281 one-price days); at 2 ticks 10 %.

Reviewed by the user on 2026-11-08 (EXEC.md EXEC-SCREENER-FLOW-CANDLES, ERRORS M402): every default above stays ("3 ok
semua tetap."); a corporate action not yet adjusted in the price series is handled by the existing price-break remark
("2A": PRICE_BREAK_IN_LOOKBACK, hidden by default); and the average body counts every bar of its window, one-price days
(body 0) and the rare days without trades included ("kalau user memang mau cari candle tersebut, ya keluarin saja semua.
itulah sebetulnya fungsi filter volume"). On a thinly traded stock a run of one-price days lowers that average, so an
ordinary candle can read as long; the universe's liquidity filters (defaults: price >= 50, ADV20 >= Rp 1 billion) or a
volume condition keep such stocks out.

## 6. Comparison with Feature 04's cdl_* (no database access)

Feature 04 has 25 `cdl_*` columns: TA-Lib 0.6.8 / C 0.6.4 at default settings, each bar from a bounded window
(`features/feature04/engine.py` `PATTERNS`, `_calculate_canonical_pattern`). 18 of the 20 P6 patterns have a column
(Tweezer Top and Bottom have none; `cdl_doji`, any doji, 2,106 bars here, has no P6 counterpart).
`p6_candles/f04_compare.py` recomputes those columns with the same TA-Lib on the fixtures' bars and compares them bar
by bar with `p6_candles/export_signals.mjs` (the fixtures do not carry the cdl_* columns themselves). The differences
are definitions and are kept:

| Pattern | P6 | F04 | both | P6 with trend off and 1 tick: P6 / both | Why they differ |
|---|---|---|---|---|---|
| Bullish Engulfing | 163 | 353 | 163 | 353 / 353 | the same rule; P6 adds the trend and the tick guard: with both off the two are identical |
| Bearish Engulfing | 184 | 816 | 184 | 424 / 424 | TA-Lib colours a candle with close = open white, so 392 of its 816 follow a doji body; the other 424 are P6's exactly |
| Bullish / Bearish Harami | 195 / 150 | 556 / 461 | 183 / 133 | 539 / 502, 475 / 412 | TA-Lib: first body above its 10-bar average, second below it; P6: second at most 50 % of the first |
| Bullish / Bearish Marubozu | 324 / 406 | 338 / 485 | 256 / 351 | 395 / 320, 502 / 441 | TA-Lib: shadows under 10 % of the 10-bar average range; P6: body at least 90 % of its own range |
| Piercing Line / Dark Cloud Cover | 24 / 23 | 15 / 24 | 11 / 12 | 36 / 15, 61 / 24 | TA-Lib opens beyond the low / high (a gap); P6's relaxed open (beyond the close) contains every TA-Lib case |
| Hammer / Hanging Man | 155 / 253 | 162 / 347 | 42 / 118 | 564 / 87, 564 / 249 | TA-Lib: lower shadow > body, body near the previous low (Hammer) or high (Hanging Man), sizes against 10-bar averages; P6: shadow >= 2 x body, the trend by the average |
| Inverted Hammer / Shooting Star | 207 / 132 | 134 / 49 | 42 / 13 | 461 / 87, 461 / 29 | TA-Lib also requires a body gap down / up, rare on the IDX; P6 does not |
| Dragonfly / Gravestone Doji | 53 / 31 | 371 / 253 | 40 / 22 | 305 / 272, 210 / 179 | TA-Lib measures body and shadows against the 10-bar average range, P6 against the candle's own range; P6's trend test is on by default |
| Morning / Evening Star | 23 / 16 | 16 / 21 | 4 / 2 | 60 / 8, 59 / 10 | TA-Lib: a strict body gap and 30 % penetration; P6: the relaxed gap and 50 % |
| Three White Soldiers / Black Crows | 6 / 6 | 14 / 2 | 1 / 0 | 15 / 4, 19 / 0 | TA-Lib's crows need a white candle before them and its soldiers very short upper shadows; P6: the trend, 25 % shadows, bodies above the average |

Open for the user: the defaults above, in particular `min_range_ticks` 3, the piercing / dark cloud open relaxed to the
close, the star overlap 10 %, the tweezer tolerance 1 tick, and the trend test on by default except for the marubozu.
