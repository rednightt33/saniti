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
raw (`2026-10-29 12:59:56.101946+00:00`); fixed in code as ERRORS M302 (shown in WIB), deployed with the next
edge-bff deployment.

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
