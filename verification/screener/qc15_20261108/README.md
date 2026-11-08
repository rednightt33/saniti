# 15 candle questions through the Screener front end (unit C, fixture page, 2026-11-08)

User request 2026-11-07 for every unit (EXEC.md EXEC-SCREENER-FLOW-CANDLES: "Try to ask maybe 20 questions and see
whether the screener actually works ... as if it was run on the front end"), here for unit C (P6, the 20 candlestick
patterns), after QA unit C. Run on the fixture build (synthetic data, the real screener core in the page) of branch
`claude/charming-hamilton-faq25e` at HEAD f646370e, before the QA fix round.

- Method (as in `../q20_20261107/`): each screen built in a fresh page through Add a condition (the Candlestick patterns
  group or the search), Detected / Detected (event), Customize for parameters and within, the All/Any/At least switch,
  then "Screen now". The wire definition and the answer are captured from the fixture API. The expected answer comes
  from an independent brute-force candle evaluator written from `P6_CANDLES.md` (not `candles.ts`, not the oracle in
  `apps/backtest-worker/tests/`); RSI, SMA, volume spike and FL24 reuse the q20 run's independent code. `results.json`
  holds the wire definitions and page answers, `compare.json` the comparison (its `_meta`: method, timing, readings,
  untested guards). Scripts and screenshots stay in the session scratchpad (`qc15/`).
- Result: all 15 screens (17 with 4b and 7b) match exactly: tickers, per-card pass and n/a counts, near rows, every
  cell's status, event date and sessions ago. A wire-level sweep of all 20 patterns (within 130 and on the bar, defaults
  and a looser setup, 40 setups, 2,405 event cells) is equal too. 105-308 ms from Screen now to results (median 152);
  no console error, no CSP violation.
- Window operators on a pattern ("Hammer on at least 3 of the last 10", "Bullish Engulfing every session of the last
  2") were not offered on this build, as expected; the core accepted them on the wire (5 such tests equal to the
  independent code). The page path landed in the QA fix round (ERRORS M399). Bullish Engulfing two sessions in a row can
  never match (the first ends on a white candle, the next must start on a black one).
- Defects: a parameter refused at Add closes the panel without marking the field (ERRORS M403, open); the Customize
  select "Prior trend measured by" cut to "averag" (fixed in M399); the fixture's BBRI last bar has a low above its close
  (ERRORS M404, open, fixture only, changes no answer).
- Not tested by this data: the fixture has no day without trades and no missing bar, so the trade and consistency
  guards are covered by the unit tests and QA2, not here.

| # | Question | Page | Expected | Verdict |
|---|---|---|---|---|
| 1 | Hammer within 3, defaults (group, no search) | 1 (ADRO, 2 sessions ago) | 1 | PASS |
| 2 | Tweezer Top "Detected" on the bar | 9 | 9 | PASS |
| 3 | Shooting Star (bearish) within 10 | 4 | 4 | PASS |
| 4 | Three White Soldiers within 20 ("soldiers") | 3 | 3 | PASS |
| 4b | Evening Star within 20 ("bintang sore") | 4 | 4 | PASS |
| 5 | Bullish Engulfing within 3, trend none | 16 | 16 | PASS |
| 6 | Hammer within 10, min_range_ticks 1 | 12 | 12 | PASS |
| 7 | Shooting Star within 10, trend_length 60 | 4 | 4 | PASS |
| 7b | Piercing Line within 60, open_beyond range | 12 | 12 | PASS |
| 8 | Any: Hammer w3, Bullish Engulfing w3 | 6 | 6 | PASS |
| 9 | All: Bullish Harami w15, RSI(14) < 30 | 1 (10 near) | 1 (10) | PASS |
| 10 | All: Bullish Marubozu w10, close > SMA(50) | 11 (55 near) | 11 (55) | PASS |
| 11 | All: Tweezer Bottom w10, FL24 >= 6 | 7 (27 near) | 7 (27) | PASS |
| 12 | All: Bullish Marubozu w10, volume spike | 1 (16 near) | 1 (16) | PASS |
| 13 | At least 2 of 3: Engulfing w10, close > SMA(50), FL24 >= 6 | 24 (43 near) | 24 (43) | PASS |
| 14 | Search "palu" / "doji" | Hammer, Inverted Hammer / Dragonfly Doji, Gravestone Doji | same | PASS |
| 15 | 8 out-of-range parameters | all refused, nothing added, no run sent | refused | PASS |
| 16 | Hammer on at least 3 of the last 10 | not offered | not offered on this build | as expected (M399) |
| 17 | Bullish Engulfing every session of the last 2 | not offered | not offered on this build | as expected (M399) |
