# EDGE Screener on Railway dev: first live check (2026-10-29)

EXEC-SCREENER Phase 1, dev deploy chosen by the user on 2026-10-29 ("A": PR to `main` after every check, then the
runbook step by step). Everything below was read on dev at 13:23-13:31 UTC on the publication of 12:59:56 UTC (the
19:00 WIB publisher run, `price_through` 2026-10-29). Times are measured from the sandbox in the US, not from Indonesia.

## What runs

| Service | Deployment | Source | Checked |
|---|---|---|---|
| screener-worker | `7a961374` | GitHub `main` `5c12216` (its inputs equal `b841a45`, PR #42) | SUCCESS through `/ready`; `screener_engine` `86839fc327abfebb` equal to the local computation of `main`; registry `b6a8dc0ba206ed65`; screener registry `638ee5ea6bbf05b5` |
| edge-bff | `8191fff7` | GitHub `main` `5c12216` | SUCCESS; `SCREENER_WORKER_URL` private, `SCREENER_WORKER_KEY` equal to the worker's (compared in memory), `SCREENER_TIMEOUT_SECONDS` 20 |

## The worker's first refresh (start-up log, `event=refresh`)

845 tickers, 844 stocks, 1,332,376 bars, 3,403 actions, 0 dropped rows, 0 orphans; files `price` and `actions` granted on
its own service key (none cached); download 2.7 s, decode 1.6 s, the 53 defaults 4.5 s, the manifest check 31.4 s,
42.4 s in all; RSS 0.66 GB; 113 series pinned, 12 preset legs skipped with their reason (Ichimoku and flow are not in
Phase 1); `published_at` equals the publication's `finished_at`; then `swap`. No error line.

## The page (verification/screener/page_timing_dev.py, Chromium, signed in as the owner)

| Action | Result |
|---|---|
| Cold open to the first results | 1.62 s (shell 0.84 s) |
| Warm open (second tab, cached boot) | 1.15 s |
| First run (preset 52W Breakout + Volume) | 0.53 s |
| Edited run (a custom length 252 -> 253) | 1.10 s |
| Preview of the first row (PBID) | 0.49 s |

The screenshots showed the header "IDX equities (844 listings) · close 2026-10-29", preset counts (Oversold in Uptrend
19, Golden Cross 24, MACD Bullish Divergence 34, Minervini 12), the P4 chips (traded on 2026-10-29 hides 17; no
unadjusted price break hides 8), the result and its reasons in the preview. The header printed the publication time
raw (`2026-10-29 12:59:56.101946+00:00`); fixed as ERRORS M302 (shown in WIB) and live since
edge-bff `074b2cc9` (13:57 UTC): the head reads "published 2026-10-29 19:59 WIB"; the same page check then gave cold
1.78 s, warm 1.01 s, preset run 0.50 s, edited run 0.48 s, preview 0.31 s.

## Answers against the database (verification/screener/live_check_dev.py, then pgweb, read-only)

Four screens on a wide universe (every listed stock, no price, liquidity, stale or price-break filter), each against
each ticker's latest `Feature_04_Technical_Indicator` row on or before 2026-10-29 (the Screener evaluates a ticker on its
own last bar):

| Screen | Screener matches | Feature 04 matches | Only in Feature 04 | Only in the Screener | Max relative difference of the value |
|---|---|---|---|---|---|
| RSI(14) < 30 | 155 | 161 | 7, all bond yields (ID03Y ... ID30Y) | ADHI* | 3.95e-12 |
| close > SMA(20) | 88 | 99 | 11, all bond yields | 0 | 2.12e-15 |
| MACD histogram > 0 | 249 | 261 | 12, all bond yields | 0 | 4.34e-12 |
| ADX(14) > 25 | 442 | 460 | 18, all bond yields | 0 | 1.87e-12 |

\* ADHI's last bar is 2026-08-21 (not traded since); its Screener value 19.3524339767 equals Feature 04's 19.35243397673
on that date. It only fell outside the first query's September window. Bond yields are in Feature 04 but not in the
Screener's stock universe. Every evaluation date equals Feature 04's date for the ticker. Run times through edge-bff:
214-268 ms, of which the worker computed 6-17 ms.

## Unchanged

backtest-worker `e3c07b59` (engine `ecebb87036dd030b`, registry `b6a8dc0ba206ed65`); its Backtest E2E after the
publication passed with `data_through` 2026-10-29 (RAILWAY_CHANGELOG 2026-10-29).

## Terminal page baseline after T7 (EXEC-MU-RUNTIME Phase 0, verification/terminal_api/page_timing_dev.py)

Same session, 2026-10-29 13:30-13:31 UTC, from the US sandbox: cold open (new profile) MAPI drawn 4.00 s (shell 1.27 s,
network quiet 5.35 s); warm open 1.67 s; switch to an uncached ticker (BBRI) 1.79 s; switch back to a cached ticker
1.19 s; timeframe weekly 0.72 s, daily 0.79 s; the bundle answer 2,765,211 bytes. The earlier readings in
`verification/edge_multiuser/runtime/terminal.md` (warm 1.77 s; cached switch 1.8-2.5 s) were before T7; the targets of
`RUNTIME.md` §7 (cached switch <= 0.9 s) are for Phase 3. An Indonesian `?perf=1` reading is still to come.

## Unit C: the 20 candlestick patterns (P6), the live check after deploy (prepared 2026-11-08, not yet run on dev)

EXEC-SCREENER-FLOW-CANDLES P6 (`verification/screener/P6_CANDLES.md`). To run on dev once the user has approved the
merge and the deploy and both edge-bff and screener-worker are at `SUCCESS`. It signs in like `live_parity_dev.py`
(edge-bff's Railway variables, in memory only), uses the public API only, saves nothing (no screen, item or watchlist;
it signs out at the end) and prints no secret. It opens at most `--max-sample` (20) tickers in the owner's Terminal quota
(`tickers_per_hour` 30 by default), so do not run it right after other Terminal-heavy checks.

    python3 verification/screener/live_candles_dev.py <OUT>
    node verification/screener/live_candles_compute.mjs <OUT>        # the judge again, offline, on a fetched OUT

What it does (`live_candles_dev.py` header): the catalog and universe; 144 screens on a wide universe (every listed
stock, stale and price-break stocks included), pinned to the catalog's `price_data`: each pattern as Detected and as
Detected within 3 at the defaults, within 3 with the other trend setting (the trend test on, average, where the default
is off since the user decision of 2026-11-08; by change for the four that cannot switch it off), with `min_range_ticks` 2 and 1, within 5 with `trend_length` 60, within 10 with its own parameters moved, plus a
candle with RSI(14) < 50, a candle with FL11 > 0 and those two alone; then a sample (3 liquid, 3 illiquid, one near each
price band boundary 200 / 500 / 2,000 / 5,000, up to 2 with a PRICE_BREAK remark, 1 stale, then a stock for every
screen whose pattern no sample stock shows yet) whose own price pack it reads through `POST /api/terminal/v1/bundle` as
the Terminal page does (sha256, bytes and rows checked). The judge (`live_candles_compute.mjs`) recomputes every pattern
with its own implementation written from P6_CANDLES.md section 5 (nothing imported from `candles.ts`, the registry or
the screener core) and compares.

Passing (exit 0, `report.json` verdict `PASS`) means all of these hold:
- the catalog lists exactly the 20 patterns in the Candlestick group, AVAILABLE, tests state and event, default test
  within 3, each parameter with the document's default (and the shared ranges); the publication and engine versions
  are recorded in `report.json` `publication`;
- all 144 screens answered at one `price_data`, and the catalog read at the end names the same publication;
- every candle condition's `params_resolved` equals the document's parameters, `is_default` is right, and its
  `eval_date_basis` is the stock's last bar;
- over the whole universe: Detected = Detected within 3 with `bars_ago` 0; `min_range_ticks` 2 and 1 and the trend test
  off never lose a stock that the default finds; each mixed screen matches exactly the intersection of its two halves,
  with the same candle cell (event date, bars_ago) and, for the flow half, `eval_date_basis` `flow_date`;
- for every sample stock: the Terminal's bars equal the Screener's (first and last date, number of bars after the rows
  without four prices are left out), and on every screen the Screener lists the stock exactly when the independent
  recomputation finds the pattern, with the same `eval_date`, `event_date`, `bars_ago`, `last_event_date` (within the
  catalog's `within_max`) and PRICE_BREAK_IN_LOOKBACK cell remark (`parity.jsonl`, one line per stock and screen).

Other exits: 1 a mismatch or a refusal other than by a limit (`report.json` `failures`, `parity.first_mismatches`); 2 the
publication changed during the check (run it again after the publisher's run); 3 incomplete (`incomplete`: a failed
request, the Terminal quota, a flow screen while the broker window loads); 4 every answer matched but a published limit
refused some screen (`limit_refused`: limit, allowed, needed; for example `compute_budget` on `trend_length` 60, where the
worker's estimate counts a pattern's largest parameter, QA4 note 1). `report.json` `coverage` names any pattern no
sample stock showed (not a failure on dev, where a rare pattern may have no stock in the last sessions). Commit
`report.json` and, when it is small or holds a mismatch, `parity.jsonl` (some 1 MB for 20 stocks), as
`verification/screener/live_q20_20261108/`; the `bars/` files are the Terminal's prices and stay out of Git.

Offline proof (no dev, Railway or database; `verification/screener/live_candles_local.mjs`, evidence in
`verification/screener/live_candles_local_20261108/`):

    node --experimental-strip-types --no-warnings=ExperimentalWarning --import ./apps/backtest-worker/loader/register.mjs \
      verification/screener/live_candles_local.mjs [OUT]

On 2026-11-08 every one of its 17 checks held: the independent implementation equals `candles.ts` bar for bar on the 8
fixtures at the check's 6 parameter sets (1,336,680 comparisons, 20,555 signals) and on random bars in every band with
adjusted prices, days without trades, missing values and inconsistent bars (728,000, 17,487 signals); 68 hand-derived
boundary cases from the document hold; its frequency table equals P6_CANDLES.md section 5 (2,908 signals on 9,014 bars);
`live_candles_dev.py --base-url` against a local stack (the fake terminal-api of `apps/screener-worker/tests` with
the fixture stocks and synthetic ones near each band boundary, an illiquid one, one with left-out rows, one with a split
after the adjusted-history boundary, one with fractional adjusted prices, a stale one, four built to show the rarest
patterns, 60 broker days; the real screener-worker; a stand-in for edge-bff's sign-in, CSRF, catalog, universe, run
relay and Terminal bundle) exited 0: 144 of 144 screens, 78 relations, 2,698 of 2,698 comparisons on 19 stocks, every
pattern shown by a sample stock, 12 price-break remarks compared, only the read routes used, no secret in its output.
Injected faults were caught: the Terminal's last three bars of BBCA changed (exit 1, 15 mismatches, all BBCA); one
Screener `bars_ago` changed (exit 1, that one cell); the publication moved (exit 2); the Terminal quota refused the fourth
bundle (exit 3); a compute_budget refusal of one screen (exit 4, the rest equal).

Not verifiable offline: dev's data and timings, its `compute_budget` and `owner_cpu_budget` values against these
screens, the owner's Terminal quota, the real edge-bff relay (latest wins per page, its CSRF and Origin checks, its
error mapping) and the bucket's presigned host from the sandbox.
