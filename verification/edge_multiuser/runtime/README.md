# Multi-user runtime for Terminal, Backtest and Screener (read-only design, 2026-10-28)

User direction of 2026-10-28 (`PLAN.md` EDGE-MULTIUSER, "Arah user berikutnya"): the Screener worker, the Backtest
machine and the Terminal must handle many users, with cost, process speed and accuracy first; AI Orc stays as is. Then:
explore one copy of each service per user (idle copies cost nothing) against best-practice benchmarks.

Nothing here changed the repository's code, Railway or the database. Code citations are at `main` `15ec418` unless a
file says otherwise. Numbers labelled INFERENCE are models; the Railway sandbox is in the US, nothing was measured from
Indonesia yet.

| File | What it is |
|---|---|
| `RUNTIME.md` | The combined design: shared principles, per-service design, shared grant gate, cost, latency targets, accuracy guarantees, phased plan, decisions RT1-RT15 |
| `RINGKASAN_RUNTIME.md` | Indonesian summary of `RUNTIME.md` |
| `backtest.md` | Backtest runtime study (B1-B12, decisions D-R1..D-R7) |
| `terminal.md` | Terminal runtime study (T1-T12, decisions D-T1..D-T6) |
| `SILO_VS_POOL.md` | One copy per user (silo) against one shared pool, and the hybrid; the decision paper |
| `RINGKASAN_SILO.md` | Indonesian summary of `SILO_VS_POOL.md` |
| `silo_research.md` | Railway facts (sleep, wake, limits, prices) and industry practice (AWS, Azure, Fly.io, Cloudflare, Lambda, Cloud Run), with quotes and links |
| `silo_bench.md` | Local cold-start benchmarks (Screener snapshot build, Backtest worker start, empty-process baselines) and the cost model for 10/50/200 users |
| `models/` | Cost and queue models (`rt_cost.py`, `rt_lock.py`, `bt_cost.py`, `bt_queue.py`) |
| `bench/scripts/`, `bench/raw/` | Benchmark scripts and their raw outputs (the generated market-data files stay local) |

Paths written as `scratchpad/mu_runtime/<file>` inside these files refer to this folder. Where `silo_research.md` §5
proposes turning sleep on with a pre-warm cron, `SILO_VS_POOL.md` §7 and `RUNTIME.md` RT14 supersede it: always on at
launch, sleep revisited after measurement (the Screener's 60 s `/state` poll keeps it awake as built).

Read-only Railway reads behind the silo paper (usage, network and cron log extracts in the session scratchpad
`mu_runtime/svp/`) and the `railway status --json` snapshot are not committed: they are raw operational dumps; their
results are quoted in the papers.
