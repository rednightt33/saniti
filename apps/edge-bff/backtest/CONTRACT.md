# EDGE backtest — contract and execution rules (schema_version 1)

Source of the types: `src/core/contract.ts`. This file states the rules the types cannot carry. Decisions taken for
the user on 2026-10-26 (they approved steps 1–5 and asked me to decide open points and report them) are marked
**[D-…]**; the list with the alternatives is in section 12, where the decisions the lead took during the review rounds
are marked (lead).

## 1. Parts and ownership

| Part | Path | Owns |
|---|---|---|
| Shared core (pure TS, no DOM, no Node API) | `apps/edge-bff/backtest/src/core/` | registry + parameter validation (`registry.ts`), conditions (`conditions.ts`), signals, ranking, calendar and portfolio exclusions (`signals.ts`), broker flow (`flow.ts`), contract (`contract.ts`), page catalog and templates (`catalog.ts`), data-file decoding (`datafile.ts`), engine (`engine.ts`), statistics and robustness (`stats.ts`, `robustness.ts`), result assembly (`ledger.ts`, `result.ts`), hashes (`hash.ts`) |
| Indicator formulas | `apps/edge-bff/terminal/src/calc/indicators.ts` | the 53 functions (Terminal module, K1 = C); never copied |
| Worker (Node 22, private) | `apps/backtest-worker/` | HTTP service, request checks, terminal-api client, cache, job runner (worker_threads), catalog endpoint |
| edge-bff (Python) | `apps/edge-bff/app/` | public API `/api/v1/backtests…`, job tables, queue loop, trials, result storage, `/backtest` route |
| Page (Vite + TS) | `apps/edge-bff/backtest/` | UI 1:1 with `backtest.html`, preview signals, rendering, CSV export |

The worker has **no** Postgres or bucket credentials. It reads market data only through terminal-api (`/bundle` and
the presigned file URLs it returns, `/manifest/{ticker}`, `/reference/{tickers|brokers}`). ORC and `Postgres-E8GM` are
not in the path.

## 2. Market data

- Datasets: `price` (`d,o,h,l,c,v`), `broker` (`d,b,i,m,bv,sv,bl,sl`), `events` (corporate actions), from
  `POST /api/terminal/v1/bundle {ticker, datasets, packs: true}` (header `x-terminal-proxy-key`; the gateway account
  `TERMINAL_PROXY_SUBSCRIBER`, quota unlimited for now **[D-U1]**). Every file is checked against its manifest
  `sha256` and `bytes` before use; a mismatch, a missing file, or a missing dataset is an explicit error
  (`DATA_INTEGRITY`, `DATA_MISSING`), never a fallback (a portfolio leaves out a ticker without published files, below).
- What the worker accepts from terminal-api and the bucket: a file or reference URL on `BACKTEST_FILE_ORIGIN` only
  (scheme, host, port; a leading `*.` matches subdomains, as the pages' CSP `https://*.t3.storageapi.dev`), redirects
  refused; any other URL is `DATA_INTEGRITY` and never requested. Bodies are read as streams and dropped at their size:
  a data file at its manifest `bytes` (`DATA_INTEGRITY`), any other body at `BACKTEST_MAX_FILE_BYTES` (a reference file
  `DATA_INTEGRITY`; a terminal-api answer or a bucket error answer `DATA_UNAVAILABLE`). A file never inflates past
  `BACKTEST_MAX_FILE_BYTES` (`DATA_INTEGRITY`; inflating stops there, so a gzip bomb never fills the memory).
- Presigned URLs: a `/bundle` answer's URLs live `expires_in_seconds` (terminal-api `url_ttl_seconds`). The worker
  first asks every ticker's `/bundle` (the manifests decide the exclusions, the limits and `FLOW_DATA_THROUGH`; no file
  is downloaded), then loads each ticker from that answer while its age plus `BACKTEST_HTTP_TIMEOUT_MS` is under the
  lifetime (an answer without a lifetime is too old at once) or while every file it names is in the worker's memory or
  disk cache (no URL is needed; a cached copy that fails its check is downloaded with that answer's URL), else from a
  new answer asked right before the ticker's downloads; a ticker whose file the bucket still refuses with 403 (the URL
  expired) is loaded once more from a new answer. A new answer is the run's data, from a later publish too: its files
  are the ones read (`data_version`) and take the place of the ticker's first ones in the limits (section 3). Every
  answer counts its files in terminal-api's quota and writes an audit row, so a ticker costs one answer, two once its
  first one is too old and a file of it is not cached, three with a 403 (review COST-1). A download in flight is
  shared only by callers of the same file and URL. Known limits: the publisher rewrites a changed file under the same
  bucket key, so an answer reused across a publish reads other bytes and fails the run (`DATA_INTEGRITY`); a ticker
  whose new answer is a 404 or lacks a dataset fails the run (`DATA_MISSING`), in a portfolio too;
  `FLOW_DATA_THROUGH` reads the first answers only.
- Portfolio **[D-exclude]**: a universe ticker without published files (terminal-api 404, or no file of a dataset the
  run reads; events aside: the publisher writes an events file only for a ticker with events) is left out with
  `DATA_MISSING` (section 4). This is decided on the manifests, before the limits are summed and before any download,
  so its files count in no limit. In single mode it is the run's `DATA_MISSING`. A file a manifest names that the
  bucket does not have (404), or that fails its checks, fails the run in either mode.
- Prices are used exactly as published (no adjusted close); a row without its four prices (`o, h, l, c`) is dropped,
  as the Terminal's `priceRows`. Rows must be strictly increasing by date; a duplicate or unsorted date is
  `DATA_INTEGRITY`. `v` may be null (index): volume conditions on such a series give `INDICATOR_OUTPUT_EMPTY`.
- Broker flow (`flow.ts`, the Terminal's definitions): a ticker's broker coverage runs from its first to its last price
  bar with a broker row. Inside it the daily foreign and broker nets have a value: a session without rows counts 0, and
  a broker without any row on the ticker's bars (it did not trade the ticker) has a net of 0 (`brokerNet`); an n-bar
  sum has one once its window lies inside it (top5 one bar later, the page's rule). Outside it every flow series is
  NaN, so no condition or ranking reads a value there. A flow condition without any value on the ticker's bars up to
  `period.to` (a window longer than the coverage) is `FLOW_OUTPUT_EMPTY` (field `….params.length`); a ticker without
  any broker row on those bars is `FLOW_UNAVAILABLE` (section 4). Whether a code is a broker at all is the request
  check `UNKNOWN_BROKER` (section 3), not the ticker's rows.
- `catalog.flow.data_through`: the newest broker `data_through` of every stock's manifest (terminal-api `/manifest`:
  no file granted, no quota, no audit row); null while flow is off. The publisher writes its date only into the
  manifests of the stocks its run touched, so only the newest one is the broker data's date. A run or a preview that
  reads broker files is refused with `FLOW_DATA_THROUGH` (field `period.to`, the message gives the date) when
  `period.to` is after it, on the manifests before any download: the request's own tickers' manifests first, then the
  other stocks' until one reaches `period.to`, so it is refused exactly when the catalog's date is before `period.to`.
  This replaces the earlier `DATA_UNAVAILABLE` check on the loaded tickers' broker `data_through`. Caching
  **[D-L3]**: the worker keeps no date, because no terminal-api answer marks a publish exactly (`load.ts
  brokerDataThrough` gives the reasons); each catalog build asks every stock's manifest, `BACKTEST_DOWNLOAD_CONCURRENCY`
  at a time. terminal-api keeps manifests until the publisher's next run (state.json `finished_at`); edge-bff keeps
  the catalog 60 s.
- Cache: by file sha256 (content-addressed: the worker's memory and optional disk caches, the page's browser cache
  **[D-P5]**), so a cached file can never belong to another data version; it is checked against its manifest again
  each time it is used, and a damaged copy is never used (the file is downloaded again).
- `data_version` = sha256 over the sorted lines `ticker \t dataset \t file sha256` of every file the run read.
- Indicators and conditions run on the ticker's **full published history** (warm-up before `period.from` uses real
  bars), and the ticker's own bars (no filling). Trading happens only inside the period. Whether a condition's series
  has any value at all (`INDICATOR_OUTPUT_EMPTY`, `FLOW_OUTPUT_EMPTY`, `FLOW_UNAVAILABLE`) is decided on the ticker's
  bars up to `period.to` only, so bars published after the period never decide it (no look-ahead). In a portfolio and
  the signals preview such a condition is false on every bar, as a series is before its first value, and the ticker
  is left out (section 4) only when its entry can then never switch on: fewer entry conditions with a value than the
  entry needs (every one under `all`, one under `any`, `min(at_least, enabled)` under `at_least`); an exit condition
  never leaves it out (review LA-1). So a ticker's trades up to a day, and the slots they take, never depend on its
  bars after that day; in single mode these errors fail the run. Known limit: a ticker left out does not reach the
  calendar (section 4), so a day on which only it has a bar (no bar of IHSG or of a ticker that runs) is a calendar
  day when it runs and not when it is left out, and can be another ticker's next calendar day (`no_next_bar`).

## 3. Request validation (worker `validate.ts`, before any download)

- edge-bff calls the worker's `POST /v1/validate` before it queues a job (`POST /api/v1/backtests`) and relays a
  refusal as it is (422, 424): a refused request never becomes a job **[D-L2]**. The worker checks the request again
  before its 202 on `POST /v1/jobs`, and the job checks the published data again on what it reads.
- Everything outside the page's controls is refused with `{error:{code, field, message}}`; nothing is clamped,
  rounded or silently dropped (registry rule). Every object holds only the fields the page sends (`UNKNOWN_FIELD` with
  the path); edge-bff takes its `client_request_id` out first.
- `period.from <= period.to`, both ISO dates; `to` later than IHSG's last published bar is refused
  (`PERIOD_AFTER_DATA`; at validation from IHSG's manifest, the newest row of its price files); `oos_fraction` 0, 0.2,
  0.3 or 0.4 (the page's select).
- Single: `single.ticker` must be a published ticker of type stock (`UNKNOWN_TICKER`); `benchmark`
  `buy_and_hold | ihsg`.
- Portfolio: `universe` from the catalog (`all`, `sector:<name>`; `UNKNOWN_UNIVERSE`); `max_positions` 1 to
  `limits.max_positions` (≤ 10); `rank_by` `fnet` needs flow.
- Entry: at least one enabled condition (`NO_ACTIVE_CONDITION`); `window_bars` 1–20; `at_least` a whole number ≥ 1
  when the logic is `at_least`, a number under the other logics (`INVALID_ENTRY`).
- Conditions: an id has the page's shape, 1 to 6 characters `[0-9a-z]` (`INVALID_CONDITION`), unique across the entry
  and exit lists (`DUPLICATE_CONDITION_ID`); each list has at most `limits.max_conditions` enabled conditions
  (`LIMIT_EXCEEDED`, `details.limit: max_conditions`). Every condition, enabled or not, is checked for its kind,
  fields, indicator, parameters, operator, outputs and threshold: a disabled one is stored with the job, so it is held
  to the same shape, but it is not evaluated. Price-action thresholds: dip above −1 (a one-day return), volspike at
  least 0 (a volume ratio; `VALUE_OUT_OF_RANGE`); the other price-action types have no `value` (`UNKNOWN_FIELD`), a
  price-action `params` is an object (`INVALID_PARAMS`) and an `op`, when given, one of the type's operators
  (`INVALID_CONDITION`).
- Exit: `take_profit.mode = 'r'` needs `stop.mode` `pct | atr | line` (an R target from an R:R stop is circular,
  `INVALID_EXIT`); `stop.mode = 'rr'` needs `take_profit.mode` `pct | atr`. Numbers must be finite and > 0 where the
  mode uses them; `max_hold_bars` whole ≥ 0. A field the chosen modes do not read is stored with the job and hashed
  into `request_hash` all the same, so it is held to its type, not to the range its mode would check (the page keeps
  what was typed into a field it no longer shows, a cleared input as 0): `exit.atr_length` without an ATR stop or
  target and the numbers of the stop, take-profit and trailing modes not chosen are numbers (`INVALID_EXIT`), and both
  price lines are checked as a line mode checks its line (a registry overlay indicator, an output other than
  `direction`, the registry's parameters) whichever mode is chosen (review VAL-1).
- Flow: enabled flow conditions and `rank_by = 'fnet'` are refused with `FLOW_UNAVAILABLE` while
  `catalog.flow.available` is false. An enabled broker condition's code must be in terminal-api's broker reference list
  (`UNKNOWN_BROKER`, field `….params.broker`). A request reads the broker files when an enabled flow condition (entry
  or exit signals) or `rank_by = 'fnet'` needs them; it is then held to `FLOW_DATA_THROUGH` (section 2), at validation
  too.
- Costs: fractions in [0, 0.1); `ara_gap_fraction` in (0, 1). Sizing: `capital_idr` ≥ 1; in single mode
  `allocation_fraction` (0, 1], in portfolio mode a number (`INVALID_SIZING`).
- Monte Carlo runs: exactly `limits.monte_carlo_runs` (1000) or 0 (off); `seed` a whole number ≥ 0.
- Found only on the data, after the job was accepted (it ends `FAILED` with the error, section 11):
  `INDICATOR_OUTPUT_EMPTY`, `FLOW_OUTPUT_EMPTY`, `FLOW_UNAVAILABLE` (in single mode; a portfolio reads the condition
  as false or leaves the ticker out, section 2), `UNIVERSE_EMPTY`, `PERIOD_EMPTY`, `PERIOD_BEFORE_DATA`, single
  mode's `DATA_MISSING` (no bar of the ticker inside the period), the download limits and the data errors of
  section 2. The job checks `PERIOD_AFTER_DATA` again on the bars it reads: a last IHSG row without its four prices,
  which the job drops, can be refused there after validation let it through, never the other way round.

Limits **[D-K7b]**: worker variables without a code default, set from the dev E2E; `catalog.limits` reports the ones
the page can act on. The worker's `LIMIT_EXCEEDED` carries `details.limit`, `allowed` and `needed`.

| Variable | Bounds | Over it |
|---|---|---|
| `BACKTEST_MAX_DOWNLOAD_BYTES` | manifest bytes of every file a job or preview reads, cached or not (the answer does not depend on the cache); `limits.max_download_bytes` | `LIMIT_EXCEEDED` `max_download_bytes`, on the manifests before any download; again before the downloads of a ticker whose answer is asked again (section 2), and on the files read |
| `BACKTEST_MAX_BROKER_ROWS` | manifest rows of the broker files read; `limits.max_broker_rows` | `LIMIT_EXCEEDED` `max_broker_rows`, when and as `max_download_bytes` |
| `BACKTEST_MAX_CONDITIONS` | enabled conditions per list; `limits.max_conditions` | `LIMIT_EXCEEDED` `max_conditions`, at validation |
| `BACKTEST_MAX_FILE_BYTES` | what one file inflates to; a body that is not a data file | `DATA_INTEGRITY`; a terminal-api or bucket error answer `DATA_UNAVAILABLE` (section 2) |
| `BACKTEST_MAX_RESULT_BYTES` | JSON bytes of a job's result; edge-bff's variable of the same name has the same value | worker: the job ends `FAILED LIMIT_EXCEEDED` `max_result_bytes` before the result is packed; edge-bff: the unpacked result is read as it arrives and never past it, `FAILED LIMIT_EXCEEDED`, nothing stored |
| `BACKTEST_TIMEOUT_SECONDS` | a job, a preview, a validation or a catalog (worker); a job, polling included, a result download, and the relayed calls' wait (+ 30 s) (edge-bff); `limits.timeout_seconds` | `TIMEOUT` (section 11) |

## 4. Calendar

The result calendar `dates` is the sorted union of the published bar dates of IHSG and every run ticker inside
`[from, to]` **[D-K5c]**. On a day without a bar a ticker cannot trade; its position is marked at its last close
(`flags.stale_mark` on the trade when that happened while held or at the exit). Signals, "within N bars" windows and
`bars_held` count the ticker's own bars.

What the period and the universe become on the data (`engine.ts` run, after the job was accepted):

- Single **[D-period_clip]**: when `period.from` is before the ticker's first published bar and that bar is on or
  before `period.to`, the run starts at that bar, so `dates[0]` is that bar and not `period.from`; the warning
  `PERIOD_CLIPPED` names the ticker and both dates. A portfolio keeps `period.from`. The variant hash keeps the
  requested period (section 7).
- Portfolio **[D-exclude]**: a universe ticker whose own data cannot serve the strategy is left out of the run instead
  of failing it: no published files (`DATA_MISSING`, the loader, section 2) or an error of `signals.ts EXCLUDED_CODES`
  (`INDICATOR_OUTPUT_EMPTY`, `FLOW_OUTPUT_EMPTY`: an indicator or flow series the run needs without any value on its
  bars; `FLOW_UNAVAILABLE`: no broker row on its bars), decided on its bars up to `period.to`, and only when its entry
  cannot switch on without that condition (section 2; otherwise the condition is false on every bar and the ticker
  runs). `meta.tickers` lists the tickers that ran; the warning `TICKERS_EXCLUDED` lists the others, sorted by ticker
  (`count`, `tickers`, and `reasons` with each ticker's `{ticker, code, field, message}`; the message gives the counts
  by code). A universe ticker without a bar inside the period runs without any event. In single mode these errors
  fail the run; a request error (a parameter, an indicator, a field) fails it in either mode.
- Every universe ticker left out **[D-L1]**: the run is refused with `UNIVERSE_EMPTY` (field `portfolio.universe`; the
  message gives the count, the counts by code and the first ticker's error), never a cash-only result.
- The calendar is built from IHSG and the tickers that run. A period without any calendar day is `PERIOD_EMPTY`; a
  primary benchmark (section 7) without a close on or before `dates[0]` is `PERIOD_BEFORE_DATA`, because the
  benchmark is scaled by its first close (section 7). Both have field `period.from`.

## 5. Signals

- Condition series as `conditions.ts` (page semantics, verified formulas). The combined entry state is
  `combineEntry`; the **entry event** is a bar where the combined state switches from false to true on the ticker's
  own bars **[D-E1]**. Only events are orders; a state that stays true does not re-enter after an exit.
- An event on the ticker's bar `j` (close of day t) orders a buy at the open of the **next calendar day**; if the
  ticker has no bar that day the event is skipped with `no_next_bar` (no stale fills).
- Exit signal: `combineExit` of the enabled exit conditions; true on a bar after the entry bar sets a pending sell at
  the ticker's next bar open (that sell waits for the next bar however late; a position is never abandoned).
- Signals preview (`POST /v1/signals`, no backtest, no trial) **[D-L4]**: each universe ticker's entry events inside
  `[from, to]` from the run's own code (`signals.ts previewRow` = the run's `periodSignals`), with the run's checks and
  exclusions: a ticker without published files, or one an error of `EXCLUDED_CODES` leaves out (section 2), is left
  out and listed in `SignalsPreview.warnings` as the run's `TICKERS_EXCLUDED` (same keys); none left is
  `UNIVERSE_EMPTY` (field `universe`); a preview that reads broker files is held to `FLOW_DATA_THROUGH` before any
  download. A preview never fails where the matching run succeeds. Overlapping previews **[D-P8]**: the latest wins
  (sections 9 and 10).

## 6. Event clock (per calendar day t) **[D-E2, E3, E4, E5, E6]**

Before the open (data up to the previous close only): update each held position's trailing level (page
`trailLevel`: pct = peak × (1 − pct), peak starts at the entry fill and then takes each close; chandelier = highest
high of the ticker bars from `max(entry bar, i − length)` to `i − 1` minus `mult × ATR(length)[i−1]`; line = line
value at `i − 1`; a level not below the previous close is inactive (−1); the level only rises).

1. **Open.** For every held position with a bar today, in ticker order:
   `lvl = max(stop, trail)`; if `lvl > 0` and `open ≤ lvl` → sell at `open`, reason `stop_loss` when `lvl = stop`
   else `trailing_stop`; else if `open ≥ target` → `take_profit` at `open`; else if a sell is pending → `exit_signal`
   at `open`. A gap exit fills at the raw open, not at the level (the fill rule below). Phase `open`. Proceeds are cash
   immediately (same auction, sells before buys).
   Then **entries**: candidates = tickers with an entry event on their previous bar (whose date is inside the period),
   not held (`already_held`), not on the last calendar day of the period (`period_end`). Portfolio: liquidity filter
   `SMA20(close × volume)` on the signal bar ≥ `min_avg_value_20d_idr` (`below_min_value`) **[D-K9]**; rank by score
   on the signal bar, highest first; a candidate without a score there (warm-up, a missing input, a zero average
   volume, no flow) after every scored one; ties and unscored candidates by ticker: `adx` = I07 adx (14, 14); `fnet` =
   5-bar foreign net (flow); `vol` = volume ÷ I35 volume SMA(20) of the bar before; `rsi` = −I13 RSI(14) (lowest
   first) **[D-E5 ranking]**.
   Walk the ranked list until the free slots (`max_positions` − held; single = 1) are filled; a candidate that is
   skipped (ARA gap, too little cash) lets the next one in **[D-slots]**; the rest are `no_slot`.
   ARA: skip when `open ≥ previous close × (1 + ara_gap_fraction)` (`ara_open_gap`) **[D-K5a]**.
   Sizing: `equity_now = cash + Σ shares × (open today, else last close)`; budget = `min(cash, equity_now ×
   allocation_fraction)` (single) or `min(cash, equity_now / max_positions)` (portfolio); fill = `open × (1 +
   slippage)`; shares = `floor(budget / (fill × (1 + buy_fee)) / 100) × 100`, less 100 while `fill × shares × (1 +
   buy_fee) > budget` (the formula in exact arithmetic: the rounded division can give a lot one ulp over the budget);
   below 100 → `insufficient_cash`; cost = `fill × shares × (1 + buy_fee)`; cash −= cost. No leverage, shorting,
   fractional shares or rebalancing; unused cash stays cash without interest.
   Initial levels (page `exitLevels`, signal bar `s`): stop pct = fill × (1 − pct); atr = fill − mult ×
   ATR(atr_length)[s] (I30, RMA); line = line value at `s` if finite and below fill, else none; target pct = fill ×
   (1 + pct); atr = fill + mult × ATR[s]; stop rr = fill − (target − fill) / x; risk = fill − stop; target r = fill +
   r × risk (none without a valid stop). ATR is the registry I30 with `smoothing_type: 'RMA'`.
2. **Intraday** (every position still held with a bar today, including the ones bought this open **[D-E3]**):
   `lvl` as above; if `lvl > 0` and `low ≤ lvl` → sell at `min(open, lvl)`; else if `high ≥ target` → sell at
   `max(open, target)`. Both touched in one candle: the stop is taken and `flags.stop_and_target_same_bar` is set
   **[D-E4]**. Phase `intraday`. MAE/MFE take the bar's low/high when the position lives through the intraday phase;
   a position sold at the open takes the raw open (before slippage), the only price it saw that day, instead of the
   bar's range **[D-E5 MAE]**.
3. **Close.** Time exit when `max_hold_bars > 0` and the ticker bars from the entry bar (included) reach it → sell at
   the close (`time_exit`). Exit signal true on today's bar (after the entry bar) → pending sell for the next bar.
   On the last calendar day of the period every open position sells at its (last) close (`end_of_test`). Otherwise
   `peak = max(peak, close)`.
4. **Mark.** equity = cash + Σ shares × close (last close when no bar); exposure = market value ÷ equity.

Cash from an intraday or close sale is usable from the next day's open **[D-E2]**. Exit fills (every phase): fill =
price × (1 − slippage); proceeds = fill × shares × (1 − sell_fee) (the page's sell fee includes the 0.1 % sales tax
**[D-K5d]**); pnl = proceeds − cost; return = pnl ÷ cost. Within one phase the page's priority breaks ties: stop loss
→ trailing stop → take profit → time exit → exit signal. A pending exit signal is filled at the open **before** that
bar's intraday stop/target, so it never takes a price from later in the day **[D-E6]**.

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
  0.5 / 0.5; rr: 0.5 / 0.5; else max hold step 5, min 2). Up to 25 full runs: identical cell requests (one variant
  hash) run once, and a cell equal to the run is the run. A cell whose threshold the condition refuses (section 3; the
  grid can step past it, volspike 1 → −1) is null, not run and not a trial; every other cell is a trial.
- Trials **[D-K3]** (`hash.ts`): the **lineage key** (the line trials are counted in) is the hash of the strategy's
  shape: the mode; in single mode the ticker (the same strategy on another stock is another line), in portfolio mode
  the universe; the entry logic and the shapes of the enabled entry conditions (kind, indicator or type, operator,
  the output names compared; no numbers or parameters, in any order); the stop, take-profit and trailing modes, with
  the line's indicator and output for a line mode; and, when an exit condition is enabled, the exit-signal logic and
  those conditions' shapes. Every number, the parameters, condition ids, the period and OOS share, the benchmark, the
  ranking and the robustness settings are not in it: changing one is a new variant of the same line. The **variant
  hash** is the hash of what the engine reads, in a canonical form (`variantOf`): a request that differs only in what
  no trade or trial Sharpe depends on is the same trial. Left out: `robustness` (Monte Carlo runs, seed, the
  sensitivity switch), `single.benchmark`, `period.oos_fraction`; condition ids and disabled conditions (each list's
  enabled conditions are compared as a sorted list, a repeated one stays repeated); `entry.at_least` unless the logic
  is `at_least`, and then as min(`at_least`, enabled entry conditions), the number `combineEntry` uses (3 with 2
  enabled is 2); the exit-signal logic without an enabled exit condition; the numbers of the stop, take-profit and
  trailing modes not chosen, and `exit.atr_length` without an ATR stop or target; `sizing.allocation_fraction` in
  portfolio mode; `costs.ara_gap_fraction` while `skip_ara_open_gap` is off. The period is kept as requested, so a
  request that `PERIOD_CLIPPED` starts at the ticker's first bar and the same request with `period.from` on that bar
  (or a period that starts on a day without a bar) give the same ledger but two variant hashes, two trials: known
  limit, a canonical start needs the data calendar, which `/v1/validate` does not read, and edge-bff stores the
  validation's `variant_hash` on the job row.
- Trial count: edge-bff passes the line's prior trials (per owner and lineage key) in their recorded order
  (`recorded_seq`: runs in the order they finished, each run's variants in its order); the run adds its own variant
  and its run cells, distinct variant hashes only (the run wins over an identical cell). A variant evaluated again
  takes the latest run's Sharpe (current data): the worker's trial set uses this run's value (`robustness.ts
  trialSet`), and `edge_bff.backtest_trials` stores it with the kind and request_id and keeps the variant's
  `recorded_seq`. `meta.trials`: `prior` = distinct prior variants, `this_run` = this run's new ones, `total` = all
  distinct trials; `variants` = this run's distinct variants, which edge-bff records. A trial's Sharpe is the full
  run's daily Sharpe (annualised ÷ √252), finite by construction (0 without volatility) **[D-L5]**; edge-bff refuses a
  result whose `meta.trials.variants` has a missing or non-finite Sharpe, a hash that is not sha256 hex, or a repeated
  hash (`RESULT_INVALID`). DSR uses the trials' Sharpe variance when there are ≥ 2 distinct trials, else 1 / n (n
  daily returns, the page's sample rule; `sharpe_variance_from`); distinct trials with equal Sharpes give variance 0,
  so sr0 = 0 and DSR = PSR(0), as the page's `dsr`.
- Warnings: `PERIOD_CLIPPED` (single: the run starts at the ticker's first published bar, section 4)
  **[D-period_clip]**; `TICKERS_EXCLUDED` (portfolio: the universe tickers left out, with `count`, `tickers` and
  `reasons`, section 4) **[D-exclude]**; `SURVIVORSHIP` (portfolio: today's universe, no delisted tickers) **[D-K6]**;
  `ADJUSTED_HISTORY_BOUNDARY` (period crosses 2026-09-12: history before is back-adjusted for splits/bonus/rights,
  after is raw) and per-trade `flags.corporate_actions` **[D-K4]**; `DATA_GAP` (calendar days without a bar for a held
  or signalled ticker; `count` = distinct (ticker, day) pairs, `tickers`); `ARB_NOT_MODELLED` (stops always fill at
  min(open, level); no lower-limit lock) **[D-K5a]**; `TICK_NOT_MODELLED`.
- Events: per condition and ticker, a `SignalTrack` on the result calendar; entries and exits per ticker; every trade
  points at its entry event (`signal_event`); skipped events with a reason.

## 8. Worker private API (shared secret header `x-backtest-worker-key`)

- `GET /health` (no key) · `GET /v1/catalog` → `Catalog`.
- `POST /v1/validate {request}` → `200 {ok, lineage_key, variant_hash, tickers}`, or the error: `validate.ts`, then
  `FLOW_DATA_THROUGH` and `PERIOD_AFTER_DATA` (field `period.to`) with the job's code, field and message, from
  terminal-api's manifests only (no `/bundle`, no file granted); 424 `DATA_MISSING` (field `IHSG.price`) when IHSG has
  no price file **[D-L2]**.
- `POST /v1/signals {SignalsPreviewRequest}` → `SignalsPreview`, computed while the caller waits on a second thread:
  one preview at a time, the others in arrival order; a preview whose caller disconnects is cancelled.
- `POST /v1/jobs {job_id, request, context}` → 202 once `validate.ts` passed (a refused request is 422 and never a
  job); 409 `BUSY` while another job runs; the same `job_id` again is 202 (edge-bff retries a POST whose answer it
  lost). One job computes at a time in a worker thread; the HTTP thread stays free.
- `GET /v1/jobs/{id}` → `JobStatus`; 404 `UNKNOWN_JOB` for any job but the latest (the worker keeps one job, none
  across a restart).
- `GET /v1/jobs/{id}/result` → 200 gzip JSON (`Content-Encoding: gzip`), as often as it is asked until the next job
  starts; then 410 `RESULT_GONE` for the finished job that newer job replaced, 404 `UNKNOWN_JOB` for any other id;
  409 `NOT_FINISHED` for the latest job unless it is `FINISHED` (a failed or cancelled one too).
- `POST /v1/jobs/{id}/cancel` → 202 `JobStatus`; a running job stops at its next check and ends `CANCELLED` (a result
  that completes after the cancel is dropped); an ended job is left as it is.
- The catalog, a validation, a preview and a job hand-over each read terminal-api's two reference lists
  (`/reference`: one granted file each, counted in the quota, with an audit row); a job and a preview read their data
  as section 2.
- A job, a preview, a validation and the catalog each get `BACKTEST_TIMEOUT_SECONDS` (a preview's and a job
  hand-over's reference lists are read under a limit of their own first): a job over it ends `FAILED TIMEOUT`, a
  synchronous call answers 504 `TIMEOUT`; a job or preview over it has its thread terminated.

## 9. edge-bff public API (session cookie; POST needs CSRF like `/api/v1/runs`)

`GET /api/v1/backtests/catalog` (the worker's `Catalog`, kept 60 s; the last one while the worker does not answer) ·
`POST /api/v1/backtests` (body = request + optional `client_request_id`, edge-bff's submission key, taken out before
the worker sees the request; `/v1/validate` first, its 422/424 relayed as they are **[D-L2]**; then 202 `{request_id,
state, created}`; the same `client_request_id` returns the same job, another request under it 409
`SUBMISSION_CONFLICT`; 429 `QUEUE_FULL` with `BACKTEST_QUEUED_PER_OWNER` jobs queued) · `GET /api/v1/backtests`
(the owner's latest jobs, each `JobStatus` + its request) · `GET /api/v1/backtests/{id}` (status) ·
`GET /api/v1/backtests/{id}/result` · `GET /api/v1/backtests/{id}/events?ticker=X` · `POST
/api/v1/backtests/{id}/cancel` · `POST /api/v1/backtests/signals` (preview, no trial; cancelled at the worker when the
page leaves before the answer). Off when `BACKTEST_WORKER_URL` is empty (`BACKTEST_DISABLED`, 503). The catalog,
validate and signals calls are relayed on the event loop and wait for the worker's answer up to
`BACKTEST_TIMEOUT_SECONDS` + 30 s (connecting 30 s).

Previews **[D-P8]**: at most one per owner is in flight. A newer one ends the one still in flight, whose worker call is
closed and which answers 409 `PREVIEW_REPLACED` (unless its page aborted it first), and goes to the worker once that
one has ended; a preview that answered, failed or whose page left frees its owner's place. A body refused with 422
`INVALID_INPUT` is no preview and replaces none.

The loop takes one job at a time (the oldest queued job of an owner with nothing running), hands it to the worker with
the line's prior trials and follows it every poll; it never resubmits. A finished job's result is fetched and split,
then stored in one transaction (a failure stores nothing). The worker answering 404 `UNKNOWN_JOB` or 410
`RESULT_GONE` for the result ends the job `FAILED WORKER_LOST` at once **[D-B1]**; a store that fails fetches the
result again at the next poll (the worker keeps it until its next job), and 3 polls in a row without an answer or a
stored result end it `WORKER_LOST`. The result is read as it arrives and never past `BACKTEST_MAX_RESULT_BYTES` of JSON
(`FAILED LIMIT_EXCEEDED`, nothing stored); a result outside the contract is `FAILED RESULT_INVALID`. An ended job
keeps the worker's final progress (`FINISHED`: `finalizing` 1/1).

Tables (migration `20261026_005_edge_bff_backtest.sql`): `edge_bff.backtest_jobs`, `edge_bff.backtest_results` (gzip
JSON bytea per `(request_id, part)`, kept 30 days), `edge_bff.backtest_trials` (one row per owner, lineage and
variant, never reset; `recorded_seq` gives the recorded order). Grants per table: jobs SELECT/INSERT/UPDATE, results
SELECT/INSERT/DELETE, trials SELECT/INSERT/UPDATE; PUBLIC none. They are documented by the migration (column comments),
the edge-bff README and this section, not in `DATABASE_SCHEMA.md` **[D-D2]**. No market data in these tables. On
ingest edge-bff splits the worker's result into the part `core` (everything except `events.conditions` and
`events.exits`) and one part `events:<ticker>` per ticker (`{conditions, exits}` of that ticker), because a portfolio
of hundreds of tickers would otherwise send every lane of every ticker to the page. `/result` answers `core` as
`BacktestResultCore` (contract.ts), with the single ticker's `TickerEvents` merged back in single mode (= the worker's
`BacktestResult`); the page asks `/events?ticker=` (`TickerEvents`) for the ticker it shows. 409 `NOT_FINISHED` unless
the job is `FINISHED`, 410 `RESULT_EXPIRED` once the parts are pruned, 404 `EVENTS_NOT_FOUND` for a ticker the run did
not have.

## 10. Page

`/backtest` (EDGE tab "Backtest", iframe) → `/backtest-app/`. Markup and CSS of `backtest.html` verbatim; behaviour
ported to TS modules. Preview signals in the browser with the shared core on the ticker's published bars (via the
existing `/api/terminal/v1` proxy); after a run, markers come from the result events only. No run at page load
**[D-no-autorun]**; the page opens in its own "Not run yet" state. The synthetic generator and the mock-up engine
exist only in the test fixture build (`?fixture=reference`), checked absent from the production bundle.

- The default period ends on the last day every dataset the request reads is published: `catalog.data_through`, or
  the earlier `catalog.flow.data_through` for a request that reads broker files while flow is available.
- Wording that depends on the data source (header, robustness warning, trial label) is the API layer's
  (`BacktestApi`), the renderers are shared **[D-P4]**: live names the published data, the run's `meta.warnings` and
  the per-strategy trial count; the fixture keeps the reference's strings.
- Published files are kept in the Terminal's browser cache **[D-P5]**: IndexedDB `terminal-files` version 1, store
  `files` (keyPath `sha`, index `used`), its least-recently-used limit; only bytes that pass `inflateVerified`; any
  IndexedDB failure means no cache, never a failed page.
- The portfolio preview aborts a preview newer settings replaced and draws only the latest answer **[D-P8]**.

## 11. Errors

`{error:{code, field?, message?, details?}}`.

- Request 422: the worker's validation codes (section 3), `LIMIT_EXCEEDED` (`details.limit`, `allowed`, `needed`;
  section 3), and edge-bff's `INVALID_INPUT` (a body that is not a JSON object, not JSON, or nested deeper than the
  parser takes; field `client_request_id` for a bad submission key). 409 `SUBMISSION_CONFLICT`; 409
  `PREVIEW_REPLACED` (a newer preview of the owner, section 9); 429 `QUEUE_FULL`.
- Data 424: `DATA_MISSING`, `DATA_INTEGRITY`, `DATA_UNAVAILABLE`.
- Service: 503 `BACKTEST_DISABLED`, `BACKTEST_UNAVAILABLE` (the worker unreachable or answering outside its API, a 504
  without the worker's `TIMEOUT` error included), `BACKTEST_NOT_READY` (the tables are missing); 504 `TIMEOUT` relayed
  with the worker's error for the catalog, validate and signals calls (section 9).
- Jobs and results: 404 `BACKTEST_NOT_FOUND`; 409 `NOT_FINISHED`; 410 `RESULT_EXPIRED` (the parts are kept 30 days);
  404 `EVENTS_NOT_FOUND`; 409 `NOT_RUNNING` (cancel of an ended job); 500 `RESULT_INTEGRITY` (a stored part fails its
  sha256).
- A job ends `FAILED` with `JobStatus.error`: the worker's error as it gave it, at the hand-over or while it ran (the
  errors found on the data, section 3; `PERIOD_EMPTY` and `PERIOD_BEFORE_DATA` with field `period.from`, section 4;
  `LIMIT_EXCEEDED` `max_download_bytes`, `max_broker_rows`, `max_result_bytes`; `TIMEOUT` over the worker's
  `BACKTEST_TIMEOUT_SECONDS`; `OUT_OF_MEMORY`, `INTERNAL_ERROR`), or edge-bff's own: `WORKER_LOST` (the worker answers
  404 for the job, 404 or 410 `RESULT_GONE` for its result **[D-B1]**, or no answer 3 times in a row at the hand-over
  or the polls; or edge-bff's lease on the job expired), `TIMEOUT` (over `BACKTEST_TIMEOUT_SECONDS` on edge-bff's
  side; the worker is sent a cancel when it has the job), `LIMIT_EXCEEDED` (the result over
  `BACKTEST_MAX_RESULT_BYTES`, with a message), `RESULT_INVALID` (a result outside the contract, section 7),
  `WORKER_FAILED` (the worker reports `FAILED` without an error). Cancel → `CANCELLED`, without an error.

## 12. Decisions taken for the user (2026-10-26)

| Id | Question | Options | Chosen | Why |
|---|---|---|---|---|
| E1 | Entry from a new event or whenever the state is true | event / state | event | every trade traces to an entry marker (prompt recommendation) |
| E2 | Same-day cash | page order / event clock | clock: open (sells, then buys), intraday, close; intraday/close cash next day | chronologically valid |
| E3 | Stop/TP on the entry bar | no (page) / yes | yes | the day's range after the open fill is real risk |
| E4 | Stop and target in one candle | stop / target / skip | stop + flag | conservative, the prompt forbids inventing a rule; this is the page's own order |
| E5 | Trailing, time exit, MAE/MFE, ranking | page / page with fixes | page rules; ranking on registry I07/I13/I35, a candidate without a score after every scored one (the page's `rankScore` substitutes values instead); MAE/MFE at the raw open for open exits | verified formulas, no look-ahead; a substituted score would rank a candidate on a value it does not have |
| E6 | Pending exit signal vs same-bar stop/TP | page priority / clock | clock | the page sells at prices from later in the day |
| K3 | Trial count | browser / per owner + lineage | per owner + lineage, +1 per distinct variant and per run cell, no reset; variant = what the engine reads (section 7); latest Sharpe per variant, recorded order | DSR stays honest across reloads |
| K4 | Mixed adjusted/raw history | flag (D3, TEMPORARY) / reload | D3 flags + warning | data fix belongs to the data layer (plan D1) |
| K5a | ARB/ARA | page ARA rule / dated rule table | page rule (`ara_gap_fraction` 0.2) + `ARB_NOT_MODELLED` warning, TEMPORARY | no sourced rule table exists |
| K5b | Tick rounding | none / round | none + warning, TEMPORARY | meaningless on back-adjusted prices |
| K5c | Gaps / suspensions | shared calendar | union calendar, own-bar windows, no fill, flags | real data has holes |
| K5d | Sales tax | in sell fee (page) / separate field | in sell fee | the page has one field |
| K6 | Portfolio universe | demo lists / all + sectors / wait | all + published sectors + `SURVIVORSHIP` warning | demo lists are synthetic |
| K7b | Limits | — | env-configurable without a code default (section 3 Limits), measured in the dev E2E | — |
| K9 | Liquidity value | close × volume / Σ broker buy | close × volume | the page's definition, needs no broker data |
| K10 | fast < slow | require / follow page | follow page | the page and TradingView accept it |
| U1 | Worker data identity | gateway key / own service key | gateway key via `${{terminal-api.TERMINAL_PROXY_KEY}}`, TEMPORARY | no terminal-api change while Terminal work runs in parallel |
| X2 | Benchmark + compare | request field / browser | benchmark in the request; compare lines in the browser | compare lines do not change results |
| slots | ARA/cash skip wastes the slot | page / next candidate | next candidate | slots go to eligible signals |
| grid | Which condition the grid varies | page (legacy cards only) / any numeric threshold | any numeric threshold | registry cards were only excluded by the mock-up |
| no-autorun | Run at page load | yes (mock-up) / no | no | each run is a trial and a job |
| period_end | Entry on the last day | allow / skip | skip | it would close at the same close |
| period_clip | Single: `period.from` before the ticker's first published bar | refuse / start at that bar | start at that bar + `PERIOD_CLIPPED` (lead) | the ticker has no bar, and a buy-and-hold benchmark no value, before it |
| exclude | Portfolio: a universe ticker whose own data cannot serve the strategy | fail the run / leave it out | leave it out + `TICKERS_EXCLUDED`: `DATA_MISSING` and `EXCLUDED_CODES`, decided on its bars up to `period.to` (lead); for `EXCLUDED_CODES` only when its entry cannot switch on without the condition, which is otherwise false on every bar (review LA-1) | one ticker's data never fails the universe's run; bars after the period never decide it, nor bars after a day what it trades up to that day (section 2 states the calendar limit) |
| L1 | Portfolio: every universe ticker left out | cash-only result / refuse | refuse: `UNIVERSE_EMPTY`, field `portfolio.universe` (preview: `universe`) (lead) | no ticker of the strategy was run, so a cash curve would not be its result |
| L2 | When `FLOW_DATA_THROUGH` and `PERIOD_AFTER_DATA` are found | at the job (202, then `FAILED`) / at submit | at submit too: `/v1/validate` checks both on terminal-api's manifests, 422 before queueing (lead) | a job that cannot succeed is never queued; `/manifest` grants no file and counts in no quota |
| L3 | Caching `catalog.flow.data_through` | every call / per publish | per publish if terminal-api's answers mark a publish exactly; none does, so the worker keeps no date and a check stops at the first manifest that reaches its date (lead) | a cache without an exact marker could keep an old date after a publish |
| L4 | Preview on a ticker whose data cannot serve the rule | fail the preview / the run's exclusions | the run's: same code, `TICKERS_EXCLUDED` in `SignalsPreview.warnings`, `UNIVERSE_EMPTY`, `FLOW_DATA_THROUGH` (lead) | a preview never fails where the matching run succeeds |
| L5 | A trial without a finite Sharpe, or a repeated variant | skip and log / refuse | finite by construction (0 without volatility); otherwise `RESULT_INVALID` (lead) | a skipped trial would undercount the line's trials and flatter the DSR |
| D2 | Where the edge_bff backtest tables are documented | `DATABASE_SCHEMA.md` by hand / migration + READMEs | the migration's column comments, the edge-bff README and section 9; `DATABASE_SCHEMA.md` not hand-edited (lead) | it is generated from schema `public` by `scripts/sync_database_schema.py` and rewritten daily by `.github/workflows/database-schema-docs.yml`, which would erase a hand-written section |
| B1 | The worker answers 410 `RESULT_GONE` for a result edge-bff has not stored | retry / end the job | `FAILED WORKER_LOST` at the first such answer, as 404 (lead) | the worker keeps one result until its next job; no later fetch can get it |
| P4 | Wording that depends on the data source (header, robustness warning, trial label) | in the renderers / in the API layer | the API layer (`BacktestApi`): live and fixture each supply theirs, the renderers stay shared (lead) | the fixture keeps the reference's strings for the pixel harness; live names published data, the run's warnings and the per-strategy trial count |
| P5 | Browser cache of published files | the page's own / the Terminal's | the Terminal's: IndexedDB `terminal-files` version 1, store `files` (keyPath `sha`, index `used`), its least-recently-used limit; only bytes that pass `inflateVerified`; any IndexedDB failure means no cache, never a failed page (lead) | one content-addressed copy per browser for both tabs |
| P8 | Overlapping signals previews | no limit / a cap with an error / latest wins | latest wins: the page aborts a preview newer settings replaced and draws only the latest; edge-bff keeps at most one preview per owner in flight, a newer one ends the older (409 `PREVIEW_REPLACED`) (lead) | pending previews piled up and held the app (review SEC-1); a cap would show errors to a page that types fast |
| bb bxin | Close back inside lower band | exact page op / crosses above | crosses above I27 lower | equal only when a close equals the band exactly |
