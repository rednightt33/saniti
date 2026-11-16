# Backtest worker memory on real files (ERRORS M463)

The worker's memory on the published files of dev, measured on this machine: the worker started as its image starts
it (the Dockerfile's `CMD` and `ENV` lines), `apps/backtest-worker/tests/fake-terminal.mjs` serving the files, the
process's RSS read every 50 ms from `/proc`. Nothing is sent to dev while measuring.

1. `fetch.py OUT_DIR BBRI,TLKM,...` (as `e2e_dev.py`: `RAILWAY_TOKEN=dummy EDGE_TEST_CHROMIUM=<chrome>`, read only):
   the tickers' files as the worker asks them (`/bundle` with packs; IHSG added) and the reference lists.
2. A request file: any `BacktestRequest`, for instance `steps.portfolio.request` or `steps.single.request` of an
   `e2e_dev.py` report (the 12-stock portfolio of `WORST_CASE_TICKERS`).
3. `node measure.mjs OUT_DIR REQUEST.json RESULT.json [VAR=value ...]` (from the repository, Linux): a preview of the
   request's stocks, the run, a 3-stock preview; the memory at each step and 1, 3, 10 and 30 s after. `VAR=value` sets
   a worker variable (`BACKTEST_DOWNLOAD_CONCURRENCY=16`, `BACKTEST_THREAD_HEAP_MB=0`) or `WORKER_DIR` to measure
   another checkout.

## 2026-11-16 (the dev files of that day; this machine, no container limit)

The 12-stock portfolio of the e2e check (2019-06-03 to 2026-11-09; ADX, stochastic, MACD divergence, two flow
conditions), its preview first:

| Worker | Peak | 1 s after the run | 30 s after | Preview / run |
|---|---|---|---|---|
| as deployed that morning (long-lived threads, 16 in flight) | 1,446-1,657 MB | 986 MB | 642 MB | 5.9 / 6.7 s |
| the same before the revamp (`5bc6bdda`) | 1,623 MB | | | |
| threads end after their task | 1,123 MB | 322 MB | 322 MB | 6.4 / 6.5 s |
| + 4 in flight + heap limit 300 MB per thread | 571 MB | 267 MB | 267 MB | 7.1 / 7.5 s |
| + `MALLOC_ARENA_MAX=2`, `MALLOC_TRIM_THRESHOLD_=131072` (the change of M463) | 493 MB | 187 MB | 187 MB | 7.7 / 8.1 s |
| the same request plus two grammar Flow conditions (FL11, FL02), as deployed | 1,770 MB | | | |
| that request with the change of M463 (heap limit 300 MB) | 764 MB | 263 MB | 263 MB | 11.4 / 13.4 s |

A single-stock run (MAPI): 1.0 s and a 500 MB process after it before; 0.8-1.0 s and 147 MB after the change. A
preview on a new thread took 0.2-0.3 s longer than on a warm one. The worker starts at 107-135 MB.

The change as built (`compute.ts` ends each thread, `BACKTEST_THREAD_HEAP_MB=412` as derived at 2 GB, 4 in flight, the
image's malloc settings), `measure.mjs` from this folder on the same files:

| Request | Peak | Right after the run | 30 s after | Preview / run |
|---|---|---|---|---|
| the 12-stock portfolio | 535 MB | 224 MB | 224 MB | 6.9 / 7.5 s |
| the same with two grammar Flow conditions | 717 MB | 188 MB | 187 MB | 10.9 / 12.4 s |
| a single stock (MAPI) | 301 MB | 159 MB | 119 MB | 0.8 / 1.0 s |

`thread_start` and `thread_end` carried the process's memory at each step (for the portfolio: preview thread 108 →
190 MB, run thread 162 → 224 MB, the 3-stock preview 224 → 220 MB).
