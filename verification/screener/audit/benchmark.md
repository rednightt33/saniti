# EDGE Screener: preliminary compute and data benchmark (read-only audit)

This is evidence for the approval gate, not the final Phase 17 benchmark. Nothing in `/home/user/saniti` was modified (`git status` is clean, HEAD `3db84ae`). Railway was not touched, no EDGE service was called, and the database was used read-only through pgweb (SELECT and EXPLAIN only). The broker tables were not read.
Scratch root: `/tmp/claude-0/-home-user-saniti/65bd49d0-9dca-5072-b7db-b62314cf2cd3/scratchpad/audit/benchmark/` (subfolders `scripts/`, `data/`, `results/`, `explain/`).

## 0. Environment and method (FACT)
- The machine has 4 CPUs and runs node v22.22.0. The database is PostgreSQL 18.6 with `shared_buffers` = 128MB (`show shared_buffers`, `select version()`).
- Formulas are imported read-only, never copied: `F` and `isN` come from `apps/edge-bff/terminal/src/calc/indicators.ts`; `Calc`, `indicatorCondition` and `compare` come from `apps/edge-bff/backtest/src/core/conditions.ts`; `REGISTRY`, `BY_ID` and `resolveParams` come from `core/registry.ts`; `inflateVerified` and `priceSeries` come from `core/datafile.ts`. Scripts run as `node --experimental-strip-types --expose-gc --import /home/user/saniti/apps/backtest-worker/loader/register.mjs scripts/bench.mts ...`. conditions.ts was importable, so scenario (c) uses the backtest core's `crosses_above`, not a hand-written cross.
- Each scenario runs in its own process, on a single JS thread, with 3 repetitions per process. I report the first repetition (cold JIT) and the min of the 3. Wall time comes from `performance.now`, CPU from `process.cpuUsage` (user+system; GC helper threads can push CPU above wall), and peak RSS from `process.resourceUsage().maxRSS`.
- The "latest value" is the ticker's own last bar. 16 tickers have a last bar before 2026-10-27, so they are stale or suspended (FACT, `results/run_all.log`).

## 1. Data pull (step 1)
| Item | Value | Label / source |
|---|---|---|
| Query | `ticker, date, open..volume::float8` with `timeframe='Daily' and is_final`, 18 half-year chunks 2018-01-01..2027-01-01, `order by ticker, date` | FACT, `scripts/pull.py` |
| Rows / tickers | 1,330,722 rows / 845 tickers (844 stocks + IHSG), 2018-01-02..2026-10-27 | FACT; matches per-year group-by (98,748 … 159,829) |
| Is every row final daily | yes (non-final count = 0 in every year) | FACT, group-by query |
| Pull wall time | 44.2 s total; client round trips 0.86–5.9 s per chunk; server `query_duration_ms` 182–5,261 ms per chunk, 29.1 s sum (2018–2021 chunks 2–5 s, likely cold; 2021-H2 onward 0.2–1.5 s) | FACT, `data/pull_log.json` |
| pgweb JSON per chunk | 2.75–5.52 MB | FACT |
| Stored full history | `data/price_full.json` 52,843,773 B (13,474,582 B gzip -9); max 2,127 bars per ticker | FACT |
| Stored 3 years (≥2023-10-01) | `data/price_3y.json` 576,678 rows, 845 tickers, 21,680,993 B (4,460,902 B gzip); max 731 bars per ticker | FACT |
| Rows per recent date | 829–835 per date (2026-10-15..27) | FACT |

INFERENCE: a calendar window ("since 2023-10-01") is not a bar window. XSPI has 80 bars in total and 64 since 2023-10-01, and DEFI has 1,061 bars in total and 240 since then. A warm-up rule therefore has to count bars, not dates (section 2e).

## 2. Compute (step 2)
Data held in memory: JSON parse plus bar build takes 0.46–0.54 s wall / 0.58–0.67 s CPU. After the load, RSS is 229 MB and heap 110 MB. Peak RSS of a load-only process is 279 MB (FACT, `results/load_full.metrics.json`). Every scenario's peak RSS (278–299 MB) comes mostly from this load.

### 2a–2c and the three combined (FACT, `results/{a,b,c,abc}_*.metrics.json`; times in ms, first / min of 3)
| Scenario | full history (1,330,722 bars) | last 750 (609,500) | last 500 (414,583) | last 250 (209,725) | from 2023-10-01 (576,678) |
|---|---|---|---|---|---|
| (a) RSI(7) latest + `rsi < 30` | 123.8 / 80.5 (cpu 172) | 64.2 / 37.0 | 47.9 / 30.8 | 34.8 / 18.2 | 63.1 / 46.7 |
| (b) SMA(75), `close > sma` state | 141.2 / 89.7 (cpu 185) | 85.8 / 56.4 | 51.0 / 30.0 | 31.7 / 17.2 | 87.3 / 47.2 |
| (c) MACD(12,26,9) `crosses_above` signal, last event, ≤4 bars ago | 250.5 / 161.5 (cpu 338) | 136.1 / 93.3 | 120.6 / 57.7 | 68.6 / 46.6 | 129.3 / 92.0 |
| (a)+(b)+(c) on one `Calc` per ticker | 461.1 / 353.7 (cpu 565); repeat processes 563.5 / 427.7 and 474.8 / 413.6 | 258.0 / 233.7 | 182.0 / 118.0 | 142.3 / 109.2 | 236.3 / 150.7 |

- Matches on the latest bar (FACT, every window gives the same counts): RSI(7)<30 = 183, close>SMA(75) = 166, MACD cross up within the last 5 bars = 221, all three = 0.
- (b) throws `INDICATOR_OUTPUT_EMPTY` for 1 ticker with fewer than 75 bars, and for 2 tickers in the from-2023 window. The core treats this as a refusal, not "false", so a screener must catch it per ticker (FACT, `conditions.ts:107-109`).
- (c) definition (FACT, `conditions.ts:52-61`): bar i is true when `macd[i-1] <= signal[i-1] && macd[i] > signal[i]`. "Within the last 5 sessions" means the last true bar index is ≥ n-5 on the ticker's own bars, and sessions_ago = n-1-i.
- Payload for 845 rows of ticker plus 5 values (close, rsi7, sma75, macd, signal) (FACT, `results/abc_full.metrics.json`):

  | Format | JSON bytes | gzip bytes |
  |---|---|---|
  | objects, full precision | 112,458 | 37,066 |
  | objects, 10 significant digits | 91,912 | 27,472 |
  | columnar, 10 significant digits | 49,722 | 23,552 |

### 2d. All 53 indicators at registry defaults (76 outputs), whole universe (FACT, `results/all53_*.metrics.json`, `repeat*_all53_full.json`)
| Window | sum of first-rep wall | sum of min wall | first-rep CPU | output values in one pass |
|---|---|---|---|---|
| full | 9,074 ms (repeats 10,192 / 9,553) | 8,079 ms (repeats 8,950 / 8,796) | 9,639 ms | 101,134,872 (771.6 MB as float64 if every series is kept) |
| last 750 | 4,406 | 3,772 | 4,960 | 46,322,000 |
| last 500 | 3,200 | 2,646 | 3,863 | 31,508,308 |
| last 250 | 1,799 | 1,363 | 2,372 | 15,939,100 |
| from 2023-10-01 | 4,312 | 3,687 | 4,898 | 43,827,528 |

- Peak RSS is 299 MB, nearly all of it the input data.
- Slowest indicators on full history (min ms): CCI 573, Stochastic 328, Donchian 325, Stoch RSI 321, Hist. vol 314, VWAP 305, Williams %R 283, CMF 268, Aroon 264. The fastest are EMA 43, Volume SMA 46, Volume EMA 46 and KAMA 49. The top 5 account for 23% of the total.
- Full per-indicator table: `results/all53_full.metrics.json` (`per_indicator`).
- The volume indicators have no latest value for IHSG, whose volume is null (FACT).
- Latest-value matrix (76 outputs × 845 tickers = 64,220 values): 737,916 B JSON / 324,382 B gzip at 10 significant digits (FACT).
- INFERENCE: a nightly precompute of all 53 defaults over full history costs about 8–10 s of single-thread CPU. Running in parallel on 4 CPUs would be about 4× faster.

### 2e. Warm-up and recursion sensitivity: latest value on the last K bars vs full history
"Differ" means a relative difference > 1e-9. The second count also requires an absolute difference > 1e-9, which excludes numerically-zero residues.
Sources: FACT, `results/compare.txt` and `results/compare.json`.

(a)–(c), as differ count and max relative difference:

| Value | K=250 | K=500 | K=750 | from 2023-10-01 |
|---|---|---|---|---|
| RSI(7) | 0 (max 1.5e-15) | 0 | 0 | 1 (XSPI 2.1e-4) |
| SMA(75) | 0 (5.96e-14) | 0 | 0 | 0, plus 1 that is null in the window |
| MACD line | 762 (max 7.0e-6) | 0 (1.5e-14) | 0 | 5 (8.3e-3) |
| MACD signal | 796 (max 6.8e-4) | 0 (2.0e-12) | 0 | 5 (1.15e-2) |
| Condition flags a/b/c that change | 0 / 0 / 0 | 0 | 0 | b: 1, c sessions_ago: 1 |

All 53 at defaults (outputs that still differ beyond 1e-9 relative and absolute):
- **K=750:**
  - KAMA: 1 ticker (BABP, 4.6e-5; a flat price regime makes KAMA's memory long).
  - EOM: 3 tickers (≤1.8e-7, running-sum drift in `sma()`, `indicators.ts:46-55`).
  - KVO / signal: 25 / 29 tickers (≤1.5e-7).
  - The 5 cumulative series OBV, PVT, ADL, NVI and PVI differ for 746–749 of the tickers longer than K. Their level depends on the start bar by definition (`indicators.ts:490, 544-545`).
- **K=500:** the same, plus ADX on 2 tickers (1.6e-8) and KVO/signal on 774/778 tickers (1.6e-4 / 4.4e-4).
- **K=250:** the whole EMA/Wilder family differs: MACD, PPO, PVO, RSI(14), ATR/NATR, ADX/DI, TSI and Stoch RSI, each on 588–830 tickers, max relative 9.7e-4 (ADX). PSAR differs on 1 ticker (3.4e-2) and KAMA on 104.
- **Stochastic-type outputs (I14, I15, I47 MFI):** relative difference up to 2, but the absolute difference is ≤ 5.3e-13. The values are numerically 0 (floating residue), so this is not material.
- **Window-free indicators:** SMA, WMA, HMA, Aroon, Donchian, Bollinger family, ROC, Momentum, CCI, CMO, Williams %R, BOP, Std dev, Hist. vol, ADR, Volume SMA/ROC, RVOL, VWMA, VWAP, CMF and MFI are within 1e-9 at every K.

Long custom parameters (FACT, `results/longparam.json`; the registry sets `min: 1` and no `max` on these lengths, `backtest-registry.json`):

| Indicator | K=750 | K=1000 | K=1500 |
|---|---|---|---|
| EMA(200) | 750/750 differ, max 4.5e-3 | 662/664, 6.2e-4 | 516/532, 1.2e-5 |
| RSI(50) | 696/750, 2.8e-6 | 87/664, 2.6e-8 | 0 |
| MACD(50,100,20) signal | 740/750, 2.6e-2 | 568/664, 2.7e-5 | 0 (9.1e-10) |
| EMA(50) | 0 | — | — |

The first row in the table where a parameter reaches 0 is where it converges; EMA(50) is already within 1e-9 at K=750, and EMA(200) is not within 1e-9 even at K=1500.

INFERENCE: K=500 bars reproduces the default MACD/RSI/ATR/ADX values to within 1e-9 (KVO excepted). Custom long lengths need full history, as do KAMA in flat regimes and the cumulative series. With a fixed K, how long a custom length can be has to be bounded, or the full history loaded.

### 2f. Parity spot check: F on full history vs stored Feature 04 (2026-10-27, 828 equity rows)
FACT (`results/f04_parity.json`): `sma_20, sma_50, ema_12/26/50/200, rsi_14, macd, macd_signal, macd_histogram, atr_14, bb_upper/middle/lower_20, adx_14` match on every row and give no null mismatches. The max relative difference is 1.16e-15. Values are bit-identical except `rsi_14` (556/828 exact) and `adx_14` (500/828 exact), which differ in the last unit.

## 3. Default path in the database (step 3)
Measured with `EXPLAIN (ANALYZE, BUFFERS)` (`explain/e1_f04.out`, `e2_price.out`, `e3_window.out`). Run 1 is the first touch in this session and run 2 follows immediately; the cache state cannot be controlled, so run 1 is not a guaranteed cold read. pgweb adds about 0.2–0.3 s of HTTP round trip on top of the execution time.

| Query | Rows | Run 1 exec | Run 2 exec | Buffers (run 1) | Plan |
|---|---|---|---|---|---|
| F04 latest per ticker, `DISTINCT ON` over the last 30 days | 840 | 1,785 ms | 89 ms | hit 1,018, read 6,366 | bitmap on `trade_date_idx`, 7,364 heap blocks for 18,235 rows, then sort |
| F04 `LATERAL ... ORDER BY trade_date DESC LIMIT 1` per universe ticker | 844 | 65 ms | 27 ms | hit 2,528, read 884 | PK backward scan, 845 probes |
| F04 snapshot `trade_date = max(trade_date)` | 828 | 1.7 ms* | 1.6 ms | hit 846 | bitmap on `trade_date_idx` |
| Price: latest close, previous close, 1D change, 20-day average of close*volume, `LATERAL` last 21 rows | 845 | 2,288 ms | 31 ms | hit 18,768, read 1,412 | `Price_..._final_idx` (ticker, date DESC) |
| Price: same columns, date-bounded window functions (45 days) | 842 | 117 ms | 84 ms | hit 507, read 131 | bitmap on `date_idx`, 585 heap blocks |
| Price 3-year window, whole universe, server side | 576,678 | 16,076 ms** | 857 ms | read 13,584, sort spills 37 MB to disk | bitmap on `date_idx` + external merge sort |
| Price full history, whole universe, server side | 1,330,722 | 3,015 ms | 1,374 ms | read 33,717 | PK index scan |

\* Run 1 of the snapshot query reused pages that the DISTINCT ON query had just read.
\** 14.1 s of that run was spent in the bitmap index scan with only 1,209 block reads. INFERENCE: I/O contention (other auditors were querying at the same time) or a cold volume. Run 2 took 0.86 s.

Other measurements:
- Feature 04 rows are wide (2,479 MB heap / 1.38M rows ≈ 1.8 KB per row) and `trade_date` correlation is -0.038 (FACT, pg_class / pg_stats). A date-range scan therefore touches about one heap block per row, while a single-date snapshot touches about 840 blocks.
- The Feature 04 equity snapshot holds 828 rows: the Price rows for the date, without IHSG, which is in the `_INDEX` table (FACT).
- INFERENCE: the cheap default path is the single-date snapshot or the LATERAL form, both below about 70 ms even on first touch. The date-bounded DISTINCT ON reads about 8× more blocks. For the price columns, the date-bounded window form is the more robust when cold.

## 4. Published-file path through terminal-api (step 4), comparison (INFERENCE unless stated)

**FACT inputs:**
- `loadMarket` calls `/bundle` once per ticker in step 1 (`load.ts:113-127`), then downloads; a ticker re-bundles only when its answer is no longer usable and it is not cached (`load.ts:147`).
- Each `/bundle` takes the per-subscriber advisory lock, runs the usage aggregate over the subscriber's last day (`store.py:60-66`; index `(subscriber_id, at DESC)`) and inserts 1 `terminal.access_log` row (`main.py:308-322`).
- Documented speeds: `/bundle` median 166 ms from `sfo`, and 0.53 s median with 20 concurrent calls. A file download takes 2,268 ms median from `sfo`. 845 `/manifest` calls take 2.3 s (catalog). Download concurrency is 16 lanes. The URL TTL is 120 s, with a 60 s HTTP-timeout margin (BACKTEST_END_TO_END.md 6.2, 6.5, 7.3, 7.4, 15).
- Default quotas (`database/migrations/20261025_100_create_terminal_schema.sql:79-83`): files_per_hour 60, tickers_per_hour 30, tickers_per_day 150, megabytes_per_day 300. The gateway account is overridden to 1e9 (TEMPORARY, doc 6.1).
- `MAX_PORTFOLIO_TICKERS = 12` (`engine.ts:151`).
- `terminal.access_log` reltuples is 6,334 (2.36 MB). pgweb is denied access to schema `terminal`, so the quota rows themselves could not be read live.

**Price pack size** (FACT for my rebuild, INFERENCE that it equals the published bytes): packs rebuilt from the same rows with the publisher's encoding (`publisher.py:55-57, 153-162`, gzip level 9) total 14.22 MB gzip / 65.0 MB JSON. Per pack, the median is 17.2 KB, p90 25.6 KB, max 42.3 KB (BRPT). Limited to the last 750 bars, the total is 6.38 MB.

**Decode cost** (FACT, measured locally): running the core's real reader (`inflateVerified` + `priceSeries`) on all 845 packs takes 2.77–3.32 s wall and 2.9–3.4 s CPU, with RSS 190 MB (`results/decode_packs.txt`). That is about 7× the cost of computing the 3-condition screen.

**Cold full-universe load estimate (INFERENCE):**
- 845 `/bundle` calls at about 0.4–0.5 s per 16-lane round take about 21–27 s, serialized on one subscriber lock.
- 845 downloads take 845/16 × 0.5–2.27 s ≈ 26–120 s. Small packs may be latency-bound below the 2.27 s median, which was measured on mixed files.
- Decode adds about 3 s and compute about 0.4 s.
- Total: about 50 s to 2.5 min. Downloads that start more than 60 s after their `/bundle` need a new one, so the load makes 845 to about 1,690 grant transactions and audit rows, for about 14 MB.
- Any subscriber on default quotas is refused (429) after 30 tickers per hour. Only the temporarily unlimited gateway account passes.
- Today the worker caps a portfolio at 12 stocks, so it cannot load the universe without a change.

**Warm load (every pack in the disk cache):** step 1 still makes 845 `/bundle` calls and writes 845 audit rows (about 21–27 s), plus about 3 s of decode.

**Database alternative, measured:** full history for the whole universe takes one statement of 1.4–3.0 s server time, or 0.86 s warm for the 3-year window. The default columns from Feature 04 or Price take 1.6–117 ms warm. Moving the rows into a Railway service has not been measured; the pgweb/JSON pull here (44 s over the internet in 18 chunks) is an upper bound, not representative.

## 5. What this suggests (PROPOSED, for the gate)
1. **Default parameters:** read the Feature 04 snapshot (bit-equal to F for its 15 columns) and the Price universe columns from PostgreSQL. Both cost milliseconds.
2. **Custom parameters:** compute server-side with the shared F/conditions core over full history per ticker (about 0.35–0.56 s single-thread for a 3-condition screen, about 9 s for all 53). The bars should come from one bounded SQL read or an in-memory daily snapshot, not from 845 `/bundle` calls.
3. **Bar window:** if a window is wanted, express it in bars (K ≥ 500 for default lengths). Cumulative series, KAMA, KVO and long custom lengths need full history, or a cap on the parameter range.
4. **Staleness:** flag tickers whose last bar is stale (16 today) and tickers that refuse with INDICATOR_OUTPUT_EMPTY.
5. **Backtest worker:** leave it unchanged. This benchmark only imported its modules read-only.

## Scratch files
- `scripts/`: pull.py, bench.mts, run_all.sh, compare.py, packsize.py, write_packs.py, decode_packs.mts, f04_latest.py, f04_parity.mts, longparam.mts
- `data/`: price_full.json, price_3y.json, pull_log.json, f04_20261027.json, packs/
- `results/`: run_all.log, *.metrics.json, compare.txt, compare.json, packsize.json, decode_packs.txt, f04_parity.json, longparam.json, repeat*
- `explain/`: e1_f04.out, e2_price.out, e3_window.out (plus their .sql)
