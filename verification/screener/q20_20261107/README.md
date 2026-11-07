# 20 questions through the Screener front end (pre-merge, fixture page, 2026-11-07)

User request 2026-11-07 (EXEC.md EXEC-SCREENER-FLOW-CANDLES): 20 screener questions, very simple to complex
(technical indicators, price patterns, flow), built through the page as a user would, compared with an independent
recomputation. Run on the fixture build (synthetic data, the real screener core in the page) at HEAD 2067c64e, on its own
port; repeated with real data on dev after deploy.

- Method: each screen built in a fresh page through Add a condition, More filters, the Operator panel and the All/Any
  switch, then "Screen now"; the wire definition captured from the fixture API; the expected answer from independent
  brute-force code written from FORMULAS.md, OPERATORS.md and the Terminal's indicator conventions (not calling them).
  `results.json` holds the wire definitions and the page answers, `compare.json` the comparison. Scripts and screenshots
  stay in the session scratchpad (`q20/`).
- Result: 18 of the 20 runnable screens match exactly (tickers, per-card pass counts, near rows, cell values to 1e-12).
  Q10 (rank among a filtered universe) differs on the fixture only: the fixture engine ranked over all listed stocks;
  the production core gives the expected 5. Q15 (Big Accumulation preset) was blocked by the fixture's stale preset list;
  the same preset rebuilt by hand (Q15b) passes. Q21 (hammer, engulfing, doji) is not offered: the 20 candlestick
  patterns are unit C (P6). No console error or CSP violation; 77-679 ms from Screen now to results.
- Defects found (all in the fixture or the page wording; none in the production engine): fixture broker data not
  deterministic (shuffle with a random comparator), fixture rank population, fixture catalog and presets out of date, the
  card does not say a price-level flow comparison is as of the broker date, depth hint and refusal wording, an empty toast
  suffix. Fixed in the QA fix round (EXEC.md QA unit B).

| # | Question | Page | Expected | Verdict |
|---|---|---|---|---|
| 1 | Price >= 1,000 (universe filter) | 61 | 61 | PASS |
| 2 | RSI(14) < 30 | 2 | 2 | PASS |
| 3 | Close above SMA(20) | 55 | 55 | PASS |
| 4 | Volume spike (20) | 1 | 1 | PASS |
| 5 | Breakout to a 20-session high | 7 | 7 | PASS |
| 6 | RSI crosses above 50 within 3 | 10 | 10 | PASS |
| 7 | MACD histogram > 0 and close > SMA(50) | 40 | 40 | PASS |
| 8 | RSI percentile over 60 >= 90 | 15 | 15 | PASS |
| 9 | Close above SMA(20) 5 sessions in a row | 42 | 42 | PASS |
| 10 | ADV >= median and RSI rank >= 90 | 4 | 5 | FAIL on the fixture only (production core: 5) |
| 11 | Bandar Balance (FL24) >= 6 | 23 | 23 | PASS |
| 12 | Foreign net (fnet, 5) > 0 | 51 | 51 | PASS |
| 13 | Net flow streak (FL26) = 3 | 6 | 6 | PASS |
| 14 | Flow percentile (FL21) >= 90 | 9 | 9 | PASS |
| 15 | Preset Big Accumulation | blocked | - | BLOCKED (fixture presets) |
| 15b | Big Accumulation rebuilt by hand | 5 | 5 | PASS |
| 16 | Broker inventory (FL23 a, top 3) slope over 5 > 0 | 48 | 48 | PASS |
| 17 | Close vs FL18 anchored 20 back | 52 | 52 | PASS |
| 18 | Close > SMA(50), RSI 50-70, FL24 >= 6, volume spike | 0 (near 12) | 0 (12) | PASS |
| 19 | Breakout within 3, FL24 percentile >= 80, fnet > 0 on 3 of 5 | 7 | 7 | PASS |
| 20 | Any: golden cross within 5, squeeze stand-in, FL11 > 0 | 90 | 90 | PASS |
| 21 | Hammer / engulfing / doji | not offered | not offered | as expected (unit C) |
