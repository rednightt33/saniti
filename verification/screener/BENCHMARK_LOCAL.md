# EDGE Screener worker: local performance benchmark (LOCAL, not dev)

**LOCAL, NOT THE SERVICE.** Every number here was measured in the build sandbox on 2026-10-29, on the real code and the
real full price history, but not on Railway. The Phase 17 benchmark on the dev service (report section 11b) replaces
every number and every proposed value below; nothing here may be copied into Railway without that run. Written by the
performance review of EXEC-SCREENER Phase 1. Nothing was deployed and nothing was written to a database.

## 1. Setup

| Item | Value |
|---|---|
| Machine | 4 vCPU Intel Xeon @ 2.80 GHz, 1 thread per core, 15.7 GB RAM, Linux 6.18, Node v22.22.0 |
| Machine sharing | other build agents ran test suites on the same machine (load average 2 to 13). Every run records its load. Wall times of runs under load are higher; CPU ms per run is the steadier figure |
| Data | `price_full.json`: 845 tickers (844 stocks and IHSG), 2018-01-02 to 2026-10-27, 1,329,893 bars after the row rule, 3,403 corporate actions |
| Chain | the real publisher wrote publication A (to 2026-10-26) and B (to 2026-10-27): price file 11,758,823 B gzip (74,272,854 B inflated), actions 20,752 B (179,331 B) -> the real terminal-api app over a local bucket stand-in -> the real worker process (`npm start`'s command, every variable set) -> HTTP as edge-bff sends it (key, owner tag, gzip) |
| Not in the path | edge-bff and the network between Railway services. Latencies are at the worker, measured by the client on localhost |
| Variables | as report 8.9 provisional values unless a row says otherwise: `SCREENER_CACHE_BYTES` 512 MiB, `SCREENER_MAX_CPU_MS` 20000, `SCREENER_CAP_BUDGET_MS` 10000 (caps 1261 for every O(N·n) length), `SCREENER_DEADLINE_MS` 20000, `SCREENER_QUEUE` 2K, `SCREENER_OWNER_INFLIGHT` 2, `SCREENER_OWNER_CPU_MS` 120000, `SCREENER_PREVIOUS_GRACE_S` 600, `SCREENER_THREAD_HEAP_MB` 512 (new, section 6) |
| Method | each scenario: warm-up runs, then 30 measured runs (12 to 15 for heavy ones, 1 for the O(N·n) caps). "Cold" = a result-cache miss; for a custom series also a series-cache miss (each run uses a new length). "LRU-warm" = the same custom series with a new threshold. "Hit" = the same definition again. RSS from `/proc/<pid>/status` every 50 ms (VmHWM reset per phase); CPU from `/proc/<pid>/stat`; predicted, busy and queue ms from the worker's own `run` log lines |
| Correctness after the changes | the local end-to-end against an independent per-ticker oracle (every cell, match and near set, P4 remarks, versions, preview, counts, presets): 109 of 109 checks |

Runs used below: **before** = the committed tree b960bca (2026-10-29 02:25, load 1.7 rising to 13); **final** = the
working tree with the fixes of section 6 (03:36, load 2.2 to 3.2); K = 1 and K = 4 runs of the final code (03:11 and
03:17, load 2 to 4).

## 2. Against the targets (report 11b.5, 06c.7, 06d)

| Target | Source | Measured locally (final, K = 2) | Verdict |
|---|---|---|---|
| Default-only screen p95 <= 0.5 s through edge-bff | 11b.5 S1 | worker p95 15 ms (1 condition), 39 ms (5), 68 ms (10), whole market | met at the worker; edge-bff and network not included |
| Mixed screen p95 <= 2 s through edge-bff, warm | 11b.5 S5 | cold p95 403 ms (custom SMA + default RSI + `return_rank`, ALL, 844 stocks); LRU-warm 18 to 28 ms | met at the worker |
| Preview p95 <= 1 s | 11b.5 S16, 6c.7 | cold p95 15 ms, hit p95 1.5 ms (one ticker, 3 conditions) | met at the worker |
| Refresh <= 2 min after `finished_at` | 11b.5 S14 | refresh while serving 33.9 s (builder alone, pre-warm 25.8 s) after the poll that sees it (up to 60 s): about 76 s after the switch. Under load the refresh took 47 to 58 s | met, little margin under load |
| Backtest job duration unchanged within 5% | 11b.5 S20 | not measured (no Backtest job ran beside it) | open |
| `/ready` about 10-15 s split over K = 2 | 06d.4 | 16.0 s (download 1.6 s, decode 2.6 s, manifest check 1.8 s, 53 defaults 8.7 s on builder + 2 threads, install 0.06 s, presets 0.17 s) | at the upper edge |
| Steady RSS about 0.4-0.7 GB, 0.7-1.2 GB at a refresh with the previous snapshot | 06d.4 | idle after start 0.57 GB; refresh with both snapshots 1.46 GB peak; with both caches full and the previous snapshot in its grace 1.81 GB | above the inference (section 4) |
| Uncached screen 0.5 vCPU s (three custom conditions) | 06d.9 `c_run` | one custom + rs_rank + default: 0.58 CPU s; five custom: 1.7 CPU s; default-only: 0.02 to 0.06 CPU s | of the order inferred |

## 3. Screens (final, K = 2; before in brackets)

| Scenario | p50 / p95 ms | CPU ms per run | Payload gzip / JSON |
|---|---|---|---|
| S1 default, 1 condition (RSI 14 < x), whole market | 11 / 15 (60 / 108) | 17 (96) | 7.3 KB / 53 KB |
| S1 default, 5 conditions ALL | 24 / 39 (172 / 266) | 33 (220) | 10.7 KB / 93 KB |
| S1 default, 10 conditions ALL | 42 / 68 (239 / 388) | 62 (314) | 12.3 KB / 114 KB |
| S1 default, 1 condition, page universe (347 eligible) | 8 / 14 (27 / 38) | 16 (40) | 4.7 KB / 32 KB |
| S13 result-cache hit | 2.4 / 3.0 (2.0 / 4.6) | 3 | as the answer |
| S2 custom RSI(L) < 30, cold | 296 / 386 (322 / 473) | 533 (492) | 1.4 KB |
| S2 custom RSI(7), LRU-warm | 11 / 20 (64 / 91) | 21 (107) | 11 KB / 86 KB |
| S3 five custom O(N) (EMA, RSI, ATR, SMA, MACD), cold | 1056 / 1323 (1393 / 1902) | 1665 (1480) | 7.8 KB |
| S3 the same, LRU-warm | 19 / 28 (157 / 335) | 23 (188) | 8.1 KB |
| S5 mixed (default RSI, custom SMA, `return_rank`) ALL, cold | 333 / 403 (400 / 548) | 577 (473) | 34 KB / 305 KB |
| S5 the same, page universe | 129 / 178 (182 / 378) | 247 (223) | 16 KB / 138 KB |
| S6 mixed ANY, cold (843 rows) | 328 / 398 (425 / 554) | 582 (535) | 64 KB / 581 KB |
| S6 mixed ALL exhaustive, cold | 316 / 358 (324 / 462) | 565 (455) | 33 KB / 293 KB |
| S7 event MACD x signal within 1-30, pinned | 24 / 34 (before not comparable: cache hits) | 29 | 28 KB / 229 KB |
| S7 event custom MACD(f, 26, 9) within 5, cold | 687 / 816 (596 / 802) | 1086 (763) | 15 KB |
| AT LEAST 5 of 6 defaults (near-heavy) | 25 / 30 (102 / 208) | 39 (159) | 16 KB / 143 KB |
| AT LEAST 2 of 3 mixed, cold (422 match, 421 near) | 351 / 448 (397 / 550) | 624 (493) | 64 KB / 580 KB |
| S9 universe only (844 rows) | 13 / 16 (49 / 77) | 14 (47) | 34 KB / 275 KB |
| S10b 20 custom O(N) events within 130, ANY, cold | 8017 / 8323 (13064 / 14335) | 11000 (13090) | 28 KB / 257 KB |
| S10c the same, ALL exhaustive | 7835 / 8120 (11450 / 13705) | 10772 (11312) | 22 KB / 200 KB |
| S10 20 conditions at caps, ANY, within 130 | refused before compute: `LIMIT_EXCEEDED compute_budget`, predicted 198 s | 0 | |
| S4 five O(N·n) at caps together | refused before compute, predicted 33 s | 0 | |
| S11 the 8 available presets | 1.5 / 3.0 (cache hits, computed at the swap) | | 2.9-18 KB |
| S16 preview, 1 ticker, 3 conditions | cold 8.8 / 15.2 (17 / 37); hit 1.1 / 1.5 | | 11.5 KB / 28 KB |
| Counts, 50 saved screens of 3-5 default conditions | 0.82-0.90 s (9.2-9.8 s); hit 0.03 s | | 0.5 KB / 3 KB |
| Counts, 50 saved screens each with its own custom series | 14.6 s (before: 504 TIMEOUT at 20 s) | | |

O(N·n) indicators, one condition, whole market, cold (final): CCI at the cap 1261 6.8 s, at 200 2.9 s; Williams %R
2.6 / 1.5 s; Donchian 2.6 / 1.6 s; Aroon 3.2 / 1.9 s; Stochastic 2.4 / 1.6 s. CPU ms per run of custom series rose
by 10 to 45% with the per-thread heap limit (more garbage collection on the helper threads) at an equal or lower wall
time; section 4 shows what it saves.

Catalog: 177,115 B JSON, 22,501 B gzip, p95 6 ms, `304` on `If-None-Match`. Universe: 225,284 B JSON, 35,759 B gzip.

## 4. Memory and refresh

| K = 2 | before | fixes 1-4 only | final (with `SCREENER_THREAD_HEAP_MB` 512) |
|---|---|---|---|
| Cold start to `/ready` | 24.0 s (loaded) | 15.7 s | 16.0 s |
| Peak RSS at the cold start | 1,380 MB | 1,405 MB | 891 MB |
| RSS idle after start | 0.67 GB | 0.66 GB | 0.57 GB |
| Refresh while serving (A -> B, builder alone, 2 owners screening) | 46.9 s, pre-warm 36.6 s | 58.2 s (load 9-10) | 33.9 s, pre-warm 25.8 s |
| Screens during that refresh, p95 | 863 ms | 935 ms | 469 ms |
| Peak RSS during it (both snapshots) | 2,828 MB | 2,057 MB | 1,457 MB |
| RSS at the end (caches full, previous snapshot in its grace) | 3,860 MB | 2,745 MB | 1,813 MB |

| Final | K = 1 | K = 2 | K = 4 (owner inflight 3) |
|---|---|---|---|
| Cold start to `/ready` (pre-warm) | 19.4 s (12.6 s) | 16.0 s (8.7 s) | 15.5 s (8.6 s) |
| Peak RSS at the cold start | 770 MB | 891 MB | 1,098 MB |
| Refresh while serving (pre-warm, builder alone) | 33.0 s (23.8 s) | 33.9 s (25.8 s) | 32.7 s (25.8 s) |
| Peak RSS during it | 1,174 MB | 1,457 MB | 1,565 MB |
| RSS at the end | 1,478 MB | 1,813 MB | 2,244 MB |

Where the memory goes (instrumented copy, per-thread `getHeapStatistics`, K = 2, before the heap limit): each compute
thread's V8 heap grew to 600-850 MB while its live part swung between 200 and 800 MB: garbage V8 had not collected,
because a worker thread's default heap limit on this host is 2,096 MB. Each thread's series LRU lives outside the heap
(typed arrays, up to its share of `SCREENER_CACHE_BYTES`, 170 MB here, measured 250 MB external at the busiest). The
two snapshots' shared columns and tails are about 0.16 GB each. With a 384 MB limit the whole matrix ran with no
out-of-memory stop and each heap stayed at or under 354 MB; the builder's heap stayed at or under 265 MB.

Single-thread pre-warm of all 113 pinned series (53 defaults, 76 outputs, the declared derived series and the presets')
on the whole market: 21.1-21.9 s in process (22.9 s before the column change of section 6, item 6); the profile is
F (indicators.ts, protected) and garbage collection.

## 5. Concurrency, fairness, caches

S5-class mixed screens, each owner sending one after the other (`client p50 / p95 ms`, throughput):

| Owners at once | K = 1 | K = 2 (inflight 2) | K = 2 (inflight 1) | K = 4 (inflight 3) |
|---|---|---|---|---|
| 1 | 337 / 401, 3.1/s | 293 / 349, 3.4/s | 265 / 334 | 283 / 343, 3.5/s |
| 2 | 527 / 563, 3.8/s | 262 / 350, 6.9/s | 260 / 283 | 277 / 344, 7.0/s |
| 4 | 828 / 909, BUSY 8 of 32 | 551 / 641, 7.3/s | 506 / 590 | 417 / 610, 9.1/s |
| 8 | 842 / 928, BUSY 30 of 48 | 819 / 995, BUSY 12 of 48 | 770 / 877, BUSY 12 of 48 | 788 / 944, 9.8/s, no BUSY |
| 8, default-only screens | 52 / 86, 44/s | 64 / 109, 82/s | 73 / 122 | 67 / 121, 108/s |

Before the fixes, K = 2 (load 8-9): 1 owner 398 / 606, 2 owners 780 / 1088, 8 owners 2,298 / 3,364 ms; 8 owners of
default-only screens 916 / 1,394 ms.

Fairness (S23, 06d.10 trigger "light owners' p95 > 1.5 x their solo p95"): one owner loops five-custom screens on two
pages, three light owners send default-only screens.

| | light solo p95 | light with the heavy owner, p95 | ratio |
|---|---|---|---|
| K = 1 | 30 ms | 3,142 ms | 105 |
| K = 2, `SCREENER_OWNER_INFLIGHT` 2 | 25-33 ms | 796-1,355 ms | 32-41 |
| K = 2, `SCREENER_OWNER_INFLIGHT` 1 | 38 ms | 63 ms | 1.6 |
| K = 4, `SCREENER_OWNER_INFLIGHT` 3 | 33 ms | 57 ms | 1.7 |

With `SCREENER_OWNER_INFLIGHT` = K one owner holds every thread and a light request waits for a heavy one to end;
with K - 1 a thread always stays free for the others. The heavy owner then runs slower (p50 2.5 s instead of 1.7 s):
a heavy user slows only themself, as report 6d.6 intends.

Caches. A skewed workload (300 requests over 60 definitions, Zipf weights; presets-like defaults, 12 custom RSI
lengths, 15 custom SMA lengths): result-cache hit ratio 0.824, custom-series LRU hit ratio 0.676 (22,773 LRU hits,
10,908 series computed), p50 3.2 ms, p95 28 ms. It needs only about 25 MB of series cache, so it shows no knee between
64 MB and 512 MB. Sizes: one custom series on the whole market is 0.94 MB in the series LRU (844 tails of 131 values);
a result is 0.6 to 64 KB of gzip; a counts entry about 360 B.

## 6. Defects found and fixed (with tests)

1. **A default-only screen read every ticker's bars.** `missingInput` (core) scanned the ticker's price columns for
   every cell, the lazy columns were therefore made for every ticker, and each request rebuilt every ticker's dates
   and a `Calc` (whose constructor reads the close column). Stage S2, "O(1) per ticker" in report 6.10, cost O(bars).
   Fix: `snapshot.ts TickerView` (the thread keeps each ticker's dates for the snapshot's life, about 10.6 MB per
   thread; columns and `Calc` made on first use; `missingInput` answered from the snapshot's per-ticker mask through a
   new optional core hook `TickerBars.missing`, which must equal the scan); each resolved series' cache key computed
   once per request. Effect: S1 one condition 96 -> 17 CPU ms, ten conditions 314 -> 62; counts of 50 default screens
   9.5 s -> 0.85 s. Tests: `apps/screener-worker/tests/views.test.ts` (the mask equals the scan for every ticker,
   field set and bar; a pre-warmed screen makes no column and answers as the plain-array path does).
2. **A request kept every survivor's computed outputs.** `CALC_KEEP` dropped a ticker from a map, but the planner holds
   every survivor's input to the end of the screen, so each ticker's `Calc` memo (every full output it computed) stayed
   alive. Five custom conditions kept about 0.2 GB per request; a ten-condition ANY screen ran out of a 600 MB heap
   (in process, measured). Fix: a view that falls out of the request's LRU (touched on every use) releases its `Calc`.
   With it the same screen ran within 400 MB. Test: `views.test.ts` (same answer, at most `keep` views hold a `Calc`).
3. **`return_rank` was computed on every request.** Report 6.7 has the cross-sections pre-warmed per publication; the
   worker did not implement the core's `xsectionValues` hook. Fix: each thread computes a window's ranks once per
   snapshot with the core's own functions (at most 16 windows). Test: `views.test.ts` (same ranks as screen.ts
   computes; the second request reads no column).
4. **The counts cache had no bound.** One entry per distinct definition until the next publication; with external
   users (P29) and default screens now taking milliseconds, that is about 100 MB an hour at the measured 82 distinct
   default screens a second (K = 2). Fix:
   `server.ts CountsCache` (50,000 entries, about 18 MB, least recently used out, the presets' counts pinned). Test:
   `apps/screener-worker/tests/counts_cache.test.ts`.
5. **Thread heaps had no bound.** V8's default limit for a worker thread here is 2,096 MB; heaps grew with garbage to
   600-850 MB each and the replica reached 2.7-3.9 GB at K = 2, above the 2 GB starting memory limit (report 6.17),
   where Railway would stop the whole replica. Fix: `SCREENER_THREAD_HEAP_MB` (required, no default, at least 64),
   applied as `resourceLimits.maxOldGenerationSizeMb` to every compute thread and the builder. A thread that needs more
   stops alone with `ERR_WORKER_OUT_OF_MEMORY` (its request answers `500 OUT_OF_MEMORY`) and is started again, as
   before for a crash. Effect: end RSS 2.75 -> 1.81 GB, refresh peak 2.06 -> 1.46 GB, cold-start peak 1.40 -> 0.89 GB.
   Tests: `apps/screener-worker/tests/heap.test.ts` (required and checked; applied to compute and builder threads; an
   out-of-memory thread stops alone and the pool serves again).
6. **A getter call on every read of a price column.** F reads `B.C`, `B.H` ... in its loops; the lazy getters ran on
   each read. Fix: a column becomes a plain data property after its first read. Pre-warm 22.9 -> 21.1-21.9 s, custom
   RSI p50 308-337 -> 279-293 ms (in process, single thread). Covered by `typed_views.test.ts` (bit-identical F) and `views.test.ts`.

Suites after the fixes: worker `npm test` 57 of 57; screener `npm run typecheck`, vitest 639 of 639 (22 files, with
the other reviewers' new tests), `registry:check` current, `build` pass; `npm run tripwire` OK (7 protected paths
unchanged); backtest-worker 186 of 186 and `registry:check` current; worker strict typecheck clean.

## 7. Cost model accuracy (not fixed: Phase 17)

The compute budget and the caps rest on the provisional cost model (registry `cost_model`: 5.96 ns per bar per length
unit, from one CCI(1000) run) and a per-replica tracker that learns one ns value per indicator. Measured, one custom
series on the whole market, single thread, in process (`costfit`, best of 2):

| Indicator | Cost by length (ms) | Line fit (ms) | Model (ms) at the same lengths |
|---|---|---|---|
| I19 CCI | 20: 703, 50: 1,097, 200: 2,882, 600: 5,669, 1261: 6,330 | 1,404 + 4.53 n | 158, 396, 1,584, 4,751, 9,985 |
| I04 HMA | 9: 363, 50: 702, 200: 1,526, 600: 3,321, 1261: 4,060 | 744 + 2.95 n | 71 ... 9,985 |
| I15 Stochastic | 14: 645, 50: 830, 200: 1,435, 600: 2,582, 1261: 2,107 | 1,007 + 1.21 n | 111 ... 9,985 |
| I08 Aroon | 14: 429, 50: 524, 200: 1,094, 600: 1,952, 1261: 1,735 | 689 + 1.08 n | |
| I10 Donchian | 20: 418, 50: 534, 200: 965, 600: 1,695, 1261: 1,554 | 639 + 0.92 n | |
| I16 Williams %R | 14: 441, 50: 564, 200: 950, 600: 1,527, 1261: 1,454 | 645 + 0.81 n | |
| I14 Stochastic RSI | 14: 577, 50: 859, 200: 1,260, 600: 2,176, 1261: 1,861 | 920 + 1.00 n | |
| I33 Historical volatility | 20: 470, 50: 670, 200: 1,361, 600: 2,502, 1261: 2,499 | 805 + 1.63 n | |
| I32 Standard deviation | 20: 223 ... 1261: 192 (flat) | 249 | |
| O(N): SMA, EMA, RSI, ATR, MFI, VWMA, ADX, TSI, MACD, Bollinger | 192 to 491 (144 to 369 ns per bar) | | 7.9 |

- Every series pays 150-1,400 ms for the whole market whatever its length (F's wrapper, the columns, the tail, the
  garbage). The model prices an O(N) series at 7.9 ms (24-62 times too low) until the tracker has seen it once.
- O(N·n) cost grows with n far more slowly than n, and falls again past 600 because tickers shorter than n compute
  nothing: at the caps the real cost is 0.2-6.3 s where the model says 10 s (the caps are 1.6 to 50 times
  conservative); I32 is O(N) in its implementation.
- The tracker's single value per indicator mispredicts by 0.24 to 4.36 times (S4: CCI, Williams, Aroon, Stochastic at
  200 after a run at the cap: 2.7-4.4 times under). An LRU-warm series is priced as a cold one (S2, S3 LRU-warm:
  predicted 279-1,468 ms, actual 7-15 ms). After it has learned, O(N) predictions are within 0.98-1.20 times.

Consequence: a request priced under the budget can run up to 4.4 times its price, so with `SCREENER_MAX_CPU_MS` at
the 20 s deadline it can end in `504 TIMEOUT` instead of the `compute_budget` refusal that names its costliest
condition (AGENTS.md gate rule). Proposal for Phase 17: per indicator (and transform) a fitted `a + b x min(n, bars)`
measured on the service and written into the generated registry, and caps derived from it; the estimate should treat
a series held in a thread's LRU as cheap (or route the request to that thread).

## 8. Proposed worker limits and memory (LOCAL; each from its rule in report 11b.4 and the numbers above)

| Variable | Rule | Measured input (local) | Proposed (local) |
|---|---|---|---|
| `SCREENER_THREADS` (K) | largest K with S5 p95 at concurrency K <= 1.5 x single and peak RSS x 1.5 within the limit | 4 vCPU: K = 2 gives 350 vs 349 ms (x 1.00); K = 4 gives 610 vs 343 ms (x 1.78, fails) | 2 on a 4-vCPU replica (K = 3 not measured); re-measure on the service's vCPU |
| `SCREENER_THREAD_HEAP_MB` (new) | above every thread's live heap with margin | the matrix ran within a 384 MB limit (heaps <= 354 MB, builder <= 265 MB) | 512 |
| Memory limit | 1.5 x the peak RSS with both snapshots alive (S19); here the steady state with full caches and the grace snapshot was higher, so the larger is used | K = 2: S19 1.46 GB, end 1.81 GB; K = 4: 1.57 / 2.24 GB | K = 2: 2.75 GB (with `SCREENER_CACHE_BYTES` 512 MiB); K = 4: 3.4 GB. The 2 GB start value is too low without fix 5, and has no margin with it |
| `SCREENER_OWNER_INFLIGHT` | light owners' p95 <= 1.5 x solo with a heavy owner (06d.10) | inflight = K: x 32-41; K - 1: x 1.6-1.7 | K - 1 (1 at K = 2); K = 1 cannot meet the rule (x 105) |
| `SCREENER_QUEUE` | 2 x K unless queueing at 8 owners passes the deadline | queue p95 at 8 owners 739 ms | 4 at K = 2 (8 owners at once then get 25% `409 BUSY`; raise to 4 x K if dev shows BUSY above 1%, 06d.10) |
| `SCREENER_MAX_CPU_MS` | S10 CPU p99, so every definition inside the published limits passes | S10 itself is priced at 198 s: no budget under the deadline admits it, so the budget must refuse it. The worst measured under-prediction is 4.36 x | 20000 / 4.36 = 4,500 until the cost model of section 7 lands; then deadline / (2 x its measured error) |
| `SCREENER_CAP_BUDGET_MS` | keeps S4 at the caps within the deadline; a lone condition at its cap must pass the per-request budget | at budget 10000 the caps cost 0.2-6.8 s (CCI the most); a cap priced above `SCREENER_MAX_CPU_MS` could never be used | equal to `SCREENER_MAX_CPU_MS`: 4,500 (caps 1261 -> 567; CCI(567) about 4.0 s measured by the fit) |
| `SCREENER_DEADLINE_MS` | 2 x S10 p99 wall, at most 20 s | heaviest admitted (S10b, 20 custom events) p99 8.3 s; a 4,500 ms-priced request may run 4.36 x | 20000 (edge-bff `SCREENER_TIMEOUT_SECONDS` 20) |
| `SCREENER_OWNER_CPU_MS` | (P33; no rule in 11b) at least `SCREENER_MAX_CPU_MS` | a heavy owner looping five-custom screens on one lane uses about 60 s per minute; an editing user (06d.9: 0.15 uncached runs a second) 3-10 s | 30000 (about half a thread-minute per minute) |
| `SCREENER_MAX_CONDITIONS` / `SCREENER_MAX_METRIC_FILTERS` / `SCREENER_WITHIN_MAX` | kept if S10 fits the deadline | the admitted 20-condition, within-130 screens took 8-10 s | 20 / 8 / 130 |
| `SCREENER_MAX_COUNTS` | at least `SCREEN_LIMIT` while 50 definitions fit the deadline | 50 default screens 0.75-0.9 s; 50 with their own custom series 13.4-17.2 s | 50, with the counts open item (section 9) |
| `SCREENER_CACHE_BYTES` | the knee of the hit ratio against memory | no knee in the synthetic workload (it fits in 25 MB); one custom series 0.94 MB, one answer 0.6-64 KB gzip | 256 MiB at K = 2 (about 90 custom series per thread, 85 MB of answers); set the knee from dev's `run` lines (`lru_hits` against `series_computed`) |
| `SCREENER_MAX_RESPONSE_BYTES` | 2 x the S9 payload | S9 275 KB JSON, but legitimate ANY answers measured 581 KB; a row is about 325 B and a cell 120-150 B, so the largest answer inside the limits (20 conditions, every stock a row) is about 2.8 MB | 4,194,304 (gzip of such an answer about 0.3 MB) |
| `SCREENER_MAX_FILE_BYTES` / `SCREENER_MAX_INFLATED_BYTES` / `SCREENER_MAX_REFRESH_BYTES` | 2 x the largest file, inflated document and refresh total | price 11,758,823 B gzip, 74,272,854 B inflated; refresh 11,772,808 B | 24,000,000 / 150,000,000 / 24,000,000 |

## 9. Open (not changed here)

- The cost model (section 7): provisional constant, single-value tracker, LRU-blind estimate.
- Counts are one job on one thread and all-or-nothing: 50 screens with their own custom series took 13-17 s with a
  20 s deadline, and a timeout loses every entry computed before it (each retry starts again). Split the entries over
  the owner's lane with a per-entry cache, or answer the entries past the budget with their own `LIMIT_EXCEEDED`.
- The refresh pre-warm runs on the builder alone while a snapshot serves: 24-29 s single-threaded, 47 s under load.
  If the 2-minute target is missed on the service, idle compute threads could take pre-warm chunks.
- The heap limit trades CPU for memory: custom-series screens cost 10-45% more CPU (garbage collection) at equal wall
  time. RAM is what the bill follows (06d.9), so the trade is kept; re-check on a 2-vCPU replica, where the
  collector's helper threads compete with the compute threads.
- Not measured locally: S8 flow (Phase 2), S15 publisher, S17 and S25 through edge-bff, S20 a Backtest job beside the
  worker, S22 two replicas, the sandbox-to-Railway round trip.

## 10. Reproducing

The harness is scratch only (not in the repository): `build/perf/bench.mts <K> <out.json>` (variables `BENCH_TAG`,
`BENCH_WORKER_DIR`, `BENCH_OWNER_INFLIGHT`, `BENCH_HEAP_MB`, `--only=`), `build/perf/prof.mts` and
`build/perf/costfit.mts` (in-process, through the real terminal-api app), `build/perf/summarize.py`, the end-to-end
`build/perf/e2e.mts`, and the publications `build/cwi/pubA`, `build/cwi/pubB` written by `build/cwi/make_publication.py`.
The price history they read is market data and stays outside the repository.
