# EDGE backtest — contract and execution rules (schema_version 1)

Source of the types: `src/core/contract.ts`. This file states the rules the types cannot carry. Decisions taken for
the user on 2026-10-26 (they approved steps 1–5 and asked me to decide open points and report them) are marked
**[D-…]**; the list with the alternatives is in section 12.

## 1. Parts and ownership

| Part | Path | Owns |
|---|---|---|
| Shared core (pure TS, no DOM, no Node API) | `apps/edge-bff/backtest/src/core/` | registry + parameter validation (`registry.ts`), conditions (`conditions.ts`), contract (`contract.ts`), page catalog and templates (`catalog.ts`), data-file decoding (`datafile.ts`), engine (`engine.ts`), statistics and robustness (`stats.ts`, `robustness.ts`), result assembly (`result.ts`) |
| Indicator formulas | `apps/edge-bff/terminal/src/calc/indicators.ts` | the 53 functions (Terminal module, K1 = C); never copied |
| Worker (Node 22, private) | `apps/backtest-worker/` | HTTP service, terminal-api client, cache, job runner (worker_threads), catalog endpoint |
| edge-bff (Python) | `apps/edge-bff/app/` | public API `/api/v1/backtests…`, job tables, queue loop, trials, result storage, `/backtest` route |
| Page (Vite + TS) | `apps/edge-bff/backtest/` | UI 1:1 with `backtest.html`, preview signals, rendering, CSV export |

The worker has **no** Postgres or bucket credentials. It reads market data only through terminal-api `/bundle` and
the presigned file URLs it returns. ORC and `Postgres-E8GM` are not in the path.

## 2. Market data

- Datasets: `price` (`d,o,h,l,c,v`), `broker` (`d,b,i,m,bv,sv,bl,sl`), `events` (corporate actions), from
  `POST /api/terminal/v1/bundle {ticker, datasets, packs: true}` (header `x-terminal-proxy-key`; the gateway account
  `TERMINAL_PROXY_SUBSCRIBER`, quota unlimited for now **[D-U1]**). Every file is checked against its manifest
  `sha256` and `bytes` before use; a mismatch, a missing file, or a missing dataset is an explicit error
  (`DATA_INTEGRITY`, `DATA_MISSING`), never a fallback.
- Prices are used exactly as published (no adjusted close). Rows must be strictly increasing by date; a duplicate or
  unsorted date is `DATA_INTEGRITY`. `v` may be null (index): volume conditions on such a series give
  `INDICATOR_OUTPUT_EMPTY`.
- Cache: by file sha256 (content-addressed), so a cached file can never belong to another data version.
- `data_version` = sha256 over the sorted lines `ticker \t dataset \t file sha256` of every file the run read.
- Indicators and conditions run on the ticker's **full published history** (warm-up before `period.from` uses real
  bars), and the ticker's own bars (no filling). Trading happens only inside the period.

## 3. Request validation (worker, before any download where possible)

- Everything outside the page's controls is refused with `{error:{code, field, message}}`; nothing is clamped,
  rounded or silently dropped (registry rule).
- `period.from <= period.to`, both ISO dates; `to` later than the IHSG `data_through` is refused (`PERIOD_AFTER_DATA`).
- Single: `single.ticker` must be a published ticker of type stock; `benchmark` `buy_and_hold | ihsg`.
- Portfolio: `universe` from the catalog (`all`, `sector:<name>`); `max_positions` 1–10; `rank_by` `fnet` needs flow.
- Entry: at least one enabled condition (`NO_ACTIVE_CONDITION`); `window_bars` 1–20; `at_least` ≥ 1.
- Exit: `take_profit.mode = 'r'` needs `stop.mode` `pct | atr | line` (an R target from an R:R stop is circular,
  `INVALID_EXIT`); `stop.mode = 'rr'` needs `take_profit.mode` `pct | atr`. Numbers must be finite and > 0 where the
  mode uses them; `max_hold_bars` whole ≥ 0.
- Flow conditions and `rank_by = 'fnet'` are refused with `FLOW_UNAVAILABLE` while `catalog.flow.available` is false.
- Costs: fractions in [0, 0.1); `ara_gap_fraction` in (0, 1). Sizing: `capital_idr` ≥ 1, `allocation_fraction` (0, 1].
- Monte Carlo runs: exactly `limits.monte_carlo_runs` (1000) or 0 (off); `seed` a whole number ≥ 0.

## 4. Calendar

The result calendar `dates` is the sorted union of the published bar dates of IHSG and every run ticker inside
`[from, to]` **[D-K5c]**. On a day without a bar a ticker cannot trade; its position is marked at its last close
(`flags.stale_mark` on the trade when that happened while held or at the exit). Signals, "within N bars" windows and
`bars_held` count the ticker's own bars.

## 5. Signals

- Condition series as `conditions.ts` (page semantics, verified formulas). The combined entry state is
  `combineEntry`; the **entry event** is a bar where the combined state switches from false to true on the ticker's
  own bars **[D-E1]**. Only events are orders; a state that stays true does not re-enter after an exit.
- An event on the ticker's bar `j` (close of day t) orders a buy at the open of the **next calendar day**; if the
  ticker has no bar that day the event is skipped with `no_next_bar` (no stale fills).
- Exit signal: `combineExit` of the enabled exit conditions; true on a bar after the entry bar sets a pending sell at
  the ticker's next bar open (that sell waits for the next bar however late; a position is never abandoned).

## 6. Event clock (per calendar day t) **[D-E2, E3, E4, E5, E6]**

Before the open (data up to the previous close only): update each held position's trailing level (page
`trailLevel`: pct = peak × (1 − pct), peak starts at the entry fill and then takes each close; chandelier = highest
high of the ticker bars from `max(entry bar, i − length)` to `i − 1` minus `mult × ATR(length)[i−1]`; line = line
value at `i − 1`; a level not below the previous close is inactive (−1); the level only rises).

1. **Open.** For every held position with a bar today, in ticker order:
   `lvl = max(stop, trail)`; if `lvl > 0` and `open ≤ lvl` → sell at `open`, reason `stop_loss` when `lvl = stop`
   else `trailing_stop`; else if `open ≥ target` → `take_profit` at `open`; else if a sell is pending → `exit_signal`
   at `open`. Phase `open`. Proceeds are cash immediately (same auction, sells before buys).
   Then **entries**: candidates = tickers with an entry event on their previous bar (whose date is inside the period),
   not held (`already_held`), not on the last calendar day of the period (`period_end`). Portfolio: liquidity filter
   `SMA20(close × volume)` on the signal bar ≥ `min_avg_value_20d_idr` (`below_min_value`) **[D-K9]**; rank by score
   on the signal bar, highest first, ties by ticker: `adx` = I07 adx (14, 14); `fnet` = 5-bar foreign net (flow);
   `vol` = volume ÷ I35 volume SMA(20) of the bar before; `rsi` = −I13 RSI(14) (lowest first) **[D-E5 ranking]**.
   Walk the ranked list until the free slots (`max_positions` − held; single = 1) are filled; a candidate that is
   skipped (ARA gap, too little cash) lets the next one in **[D-slots]**; the rest are `no_slot`.
   ARA: skip when `open ≥ previous close × (1 + ara_gap_fraction)` (`ara_open_gap`) **[D-K5a]**.
   Sizing: `equity_now = cash + Σ shares × (open today, else last close)`; budget = `min(cash, equity_now ×
   allocation_fraction)` (single) or `min(cash, equity_now / max_positions)` (portfolio); fill = `open × (1 +
   slippage)`; shares = `floor(budget / (fill × (1 + buy_fee)) / 100) × 100`; below 100 → `insufficient_cash`; cost =
   `fill × shares × (1 + buy_fee)`; cash −= cost. No leverage, shorting, fractional shares or rebalancing; unused cash
   stays cash without interest.
   Initial levels (page `exitLevels`, signal bar `s`): stop pct = fill × (1 − pct); atr = fill − mult × ATR(atr_length)[s]
   (I30, RMA); line = line value at `s` if finite and below fill, else none; target pct = fill × (1 + pct); atr = fill +
   mult × ATR[s]; stop rr = fill − (target − fill) / x; risk = fill − stop; target r = fill + r × risk (none without a
   valid stop). ATR is the registry I30 with `smoothing_type: 'RMA'`.
2. **Intraday** (every position still held with a bar today, including the ones bought this open **[D-E3]**):
   `lvl` as above; if `lvl > 0` and `low ≤ lvl` → sell at `min(open, lvl)`; else if `high ≥ target` → sell at
   `max(open, target)`. Both touched in one candle: the stop is taken and `flags.stop_and_target_same_bar` is set
   **[D-E4]**. Phase `intraday`. MAE/MFE take the bar's low/high when the position lives through the intraday phase;
   a position sold at the open uses the exit price instead of the bar's range **[D-E5 MAE]**.
3. **Close.** Time exit when `max_hold_bars > 0` and the ticker bars from the entry bar (included) reach it → sell at
   the close (`time_exit`). Exit signal true on today's bar (after the entry bar) → pending sell for the next bar.
   On the last calendar day of the period every open position sells at its (last) close (`end_of_test`). Otherwise
   `peak = max(peak, close)`.
4. **Mark.** equity = cash + Σ shares × close (last close when no bar); exposure = market value ÷ equity.

Cash from an intraday or close sale is usable from the next day's open **[D-E2]**. Exit fills: fill = price × (1 −
slippage); proceeds = fill × shares × (1 − sell_fee) (the page's sell fee includes the 0.1 % sales tax **[D-K5d]**);
pnl = proceeds − cost; return = pnl ÷ cost. Within one phase the page's priority breaks ties: stop loss → trailing stop
→ take profit → time exit → exit signal. A pending exit signal is filled at the open **before** that bar's intraday
stop/target, so it never takes a price from later in the day **[D-E6]**.

## 7. Results (numbers only; the page owns layout, labels, colours, charts)

All statistics reproduce the page's formulas (`seriesStats`, `tradeStats`, `dsr`, `monteCarlo`, and the tables the
renderers derive: monthly, annual, weekday, rolling Sharpe 126 (window excludes the current return), five deepest
drawdowns, exit reasons, per ticker), so the page shows what `backtest.html` shows for the same ledger.

- `oos.cut` = `floor(n × (1 − fraction))` (page `cut`); in-sample stats when `cut > 20`, out-of-sample when
  `n − cut > 20`; trade split by entry calendar index ≤ cut day.
- Benchmark: single `buy_and_hold` = the ticker's close (as of each calendar day), `ihsg` = IHSG close; portfolio =
  IHSG. Scaled to the capital on the first day. Beta, alpha and correlation are against this primary benchmark.
- Comparison lines (`S.cmp`, up to 2 tickers) are display-only: the page draws them from published closes with the
  shared as-of function in `datafile.ts` **[D-X2]**.
- Monte Carlo: seed from the request (page default 7), LCG of the page; scale = allocation (single) or 1 / max
  positions (portfolio); null with fewer than 3 trades.
- Sensitivity **[D-grid]**: the first enabled entry condition with a numeric threshold (indicator value, dip,
  volspike, flow); xs = base + k × step, k = −2..2, step = max(1, |base_display| × 0.2) in display units
  (`catalog.ts DISPLAY`), rounded to 2 decimals in display units; ys from the stop mode (pct: step 2 %, min 1 %; atr:
  0.5 / 0.5; rr: 0.5 / 0.5; else max hold step 5, min 2). 25 full runs; each cell is a trial.
- Trials **[D-K3]**: lineage = hash of the strategy shape (mode, universe, condition kinds/indicators/operators/
  outputs, exit modes; no numbers). Variant hash = hash of the canonical request. edge-bff passes the lineage's
  prior trials; the run adds its own variant and the 25 cells (distinct variant hashes only). DSR uses the trials'
  Sharpe variance when there are ≥ 2 distinct trials, else the sample variance (`sharpe_variance_from`).
- Warnings: `SURVIVORSHIP` (portfolio: today's universe, no delisted tickers) **[D-K6]**; `ADJUSTED_HISTORY_BOUNDARY`
  (period crosses 2026-09-12: history before is back-adjusted for splits/bonus/rights, after is raw) and per-trade
  `flags.corporate_actions` **[D-K4]**; `DATA_GAP` (calendar days without a bar for a held or signalled ticker);
  `ARB_NOT_MODELLED` (stops always fill at min(open, level); no lower-limit lock) **[D-K5a]**; `TICK_NOT_MODELLED`.
- Events: per condition and ticker, a `SignalTrack` on the result calendar; entries and exits per ticker; every trade
  points at its entry event (`signal_event`); skipped events with a reason.

## 8. Worker private API (shared secret header `x-backtest-worker-key`)

`GET /health` · `GET /v1/catalog` · `POST /v1/validate {request}` · `POST /v1/signals {SignalsPreviewRequest}` ·
`POST /v1/jobs {job_id, request, context}` → 202 · `GET /v1/jobs/{id}` → `JobStatus` · `GET /v1/jobs/{id}/result` →
gzip JSON · `POST /v1/jobs/{id}/cancel`. One job computes at a time in a worker thread; the HTTP thread stays free.

## 9. edge-bff public API (session cookie; POST needs CSRF like `/api/v1/runs`)

`GET /api/v1/backtests/catalog` · `POST /api/v1/backtests` (202, `{request_id}`; body = request + optional
`client_request_id`) · `GET /api/v1/backtests` (latest jobs) · `GET /api/v1/backtests/{id}` (status) ·
`GET /api/v1/backtests/{id}/result` · `GET /api/v1/backtests/{id}/events?ticker=X` · `POST
/api/v1/backtests/{id}/cancel` · `POST /api/v1/backtests/signals` (preview, no trial). Off when `BACKTEST_WORKER_URL`
is empty (`BACKTEST_DISABLED`, 503). Tables (migration `20261026_005_edge_bff_backtest.sql`):
`edge_bff.backtest_jobs`, `edge_bff.backtest_results` (gzip JSON bytea per `(request_id, part)`, kept 30 days),
`edge_bff.backtest_trials`. No market data in these tables. On ingest edge-bff splits the worker's result into the
part `core` (everything except `events.conditions` and `events.exits`) and one part `events:<ticker>` per ticker
(`{conditions, exits}` of that ticker), because a portfolio of hundreds of tickers would otherwise send every lane of
every ticker to the page. `/result` returns `core` (plus the single ticker's events in single mode); the page asks
`/events?ticker=` for the ticker it shows.

## 10. Page

`/backtest` (EDGE tab "Backtest", iframe) → `/backtest-app/`. Markup and CSS of `backtest.html` verbatim; behaviour
ported to TS modules. Preview signals in the browser with the shared core on the ticker's published bars (via the
existing `/api/terminal/v1` proxy); after a run, markers come from the result events only. No run at page load
**[D-no-autorun]**; the page opens in its own "Not run yet" state. The synthetic generator and the mock-up engine
exist only in the test fixture build (`?fixture=reference`), checked absent from the production bundle.

## 11. Errors

`{error:{code, field?, message?, details?}}`. Validation 422; data errors 424 (`DATA_MISSING`, `DATA_INTEGRITY`,
`DATA_UNAVAILABLE`); limits 429 (`QUEUE_FULL`); `BACKTEST_DISABLED` 503; worker lost → job `FAILED`
`WORKER_LOST`; timeout → `TIMEOUT`; cancel → `CANCELLED`.

## 12. Decisions taken for the user (2026-10-26)

| Id | Question | Options | Chosen | Why |
|---|---|---|---|---|
| E1 | Entry from a new event or whenever the state is true | event / state | event | every trade traces to an entry marker (prompt recommendation) |
| E2 | Same-day cash | page order / event clock | clock: open (sells, then buys), intraday, close; intraday/close cash next day | chronologically valid |
| E3 | Stop/TP on the entry bar | no (page) / yes | yes | the day's range after the open fill is real risk |
| E4 | Stop and target in one candle | stop / target / skip | stop + flag | conservative, the prompt forbids inventing a rule; this is the page's own order |
| E5 | Trailing, time exit, MAE/MFE, ranking | page / page with fixes | page rules; ranking on registry I07/I13/I35; MAE/MFE at the exit price for open exits | verified formulas, no look-ahead |
| E6 | Pending exit signal vs same-bar stop/TP | page priority / clock | clock | the page sells at prices from later in the day |
| K3 | Trial count | browser / per owner + lineage | per owner + lineage, +1 per distinct variant and per cell, no reset | DSR stays honest across reloads |
| K4 | Mixed adjusted/raw history | flag (D3, TEMPORARY) / reload | D3 flags + warning | data fix belongs to the data layer (plan D1) |
| K5a | ARB/ARA | page ARA rule / dated rule table | page rule (`ara_gap_fraction` 0.2) + `ARB_NOT_MODELLED` warning, TEMPORARY | no sourced rule table exists |
| K5b | Tick rounding | none / round | none + warning, TEMPORARY | meaningless on back-adjusted prices |
| K5c | Gaps / suspensions | shared calendar | union calendar, own-bar windows, no fill, flags | real data has holes |
| K5d | Sales tax | in sell fee (page) / separate field | in sell fee | the page has one field |
| K6 | Portfolio universe | demo lists / all + sectors / wait | all + published sectors + `SURVIVORSHIP` warning | demo lists are synthetic |
| K7b | Limits | — | env-configurable, measured in the dev E2E | — |
| K9 | Liquidity value | close × volume / Σ broker buy | close × volume | the page's definition, needs no broker data |
| K10 | fast < slow | require / follow page | follow page | the page and TradingView accept it |
| U1 | Worker data identity | gateway key / own service key | gateway key via `${{terminal-api.TERMINAL_PROXY_KEY}}`, TEMPORARY | no terminal-api change while Terminal work runs in parallel |
| X2 | Benchmark + compare | request field / browser | benchmark in the request; compare lines in the browser | compare lines do not change results |
| slots | ARA/cash skip wastes the slot | page / next candidate | next candidate | slots go to eligible signals |
| grid | Which condition the grid varies | page (legacy cards only) / any numeric threshold | any numeric threshold | registry cards were only excluded by the mock-up |
| no-autorun | Run at page load | yes (mock-up) / no | no | each run is a trial and a job |
| period_end | Entry on the last day | allow / skip | skip | it would close at the same close |
| bb bxin | Close back inside lower band | exact page op / crosses above | crosses above I27 lower | equal only when a close equals the band exactly |
