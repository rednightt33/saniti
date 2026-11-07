# P5 — the Terminal's flow indicators in the Screener

EXEC-SCREENER-FLOW-CANDLES P5 (decisions in EXEC.md: two layers, B, C, D, E, G1, G2, G3, K1, K7, old formulas; map in
`verification/screener/FLOW_MAP.md`; operators in `OPERATORS.md`; data from P4, `P4_BROKER_DAYS.md`). The Screener
computes every flow value with the Terminal's own module, so a value equals the Terminal's for the same rows.

## 1. Engine (stage P5a)

- **One formula source.** `apps/edge-bff/terminal/src/calc/flow.ts` `computeFlow(id, ctx, params)` with
  `flowDefaults(id)`. Under Node its `import REG from '../data/flowRegistry.json'` fails
  (`ERR_IMPORT_ATTRIBUTE_MISSING`): give it `with { type: 'json' }` as `backtest/src/core/engine.ts:30` does (Vite builds
  it the same). flow.ts is not on the backtest tripwire's ALWAYS list; the Terminal's numbers do not change.
- **Reference.** `FlowRef` in `contract.ts` becomes `{ kind: 'flow', metric: 'FL01'..'FL48', output?: string, params:
  Record<string, ParamValue> }` (output: the registry's `outputs`, default the first). Parameters are the registry's
  (`flowRegistry.json` indicators[].params: int with min/max, multi with options, select, date, levels); a parameter left
  out takes `flowDefaults`. `levels` and `button`/`fixed` kinds are display-only and refused as condition parameters.
  So is a select or switch whose every option gives the same values (QA unit B, QA5: the Terminal's "Plot" on FL10,
  FL11, FL14, FL25, FL26, FL31, FL34, FL41), derived at catalog build, never listed: `build-screener-registry.mjs`
  `displayOnlyParams` runs `computeFlow` on the depth probe's synthetic context (`src/core/flowprobe.ts`, shared with
  `indicatorDepth`) at the registry defaults and with each other select, switch or list set to each of its other values
  in turn; identical outputs everywhere (with a value somewhere) make it `condition: false, display_only: true`: the
  page does not offer it, the core refuses it if sent (naming the parameters a condition takes) and computeFlow takes
  its default. A choice that changes a value stays (FL34 "Change line vs", FL07 "Denominator" under one investor type).
  `flow.ts` and `flowprobe.ts` are sources of the registry (`flow_calc`, `flow_probe`), so a change to either needs
  `npm run registry`.
- **Validation.** Every parameter checked against the registry (kind, min, max, options), refusal `PARAM_OUT_OF_RANGE` /
  `INVALID_CONDITION` naming the field, following the gate rule of AGENTS.md (rule, how to pass, right and wrong
  example, message). **Depth (K1):** the sessions an indicator reads back (its window or N parameters, plus any operator
  length or within) may not exceed the loaded broker window (`data.broker_window.sessions`, 60): `LIMIT_EXCEEDED`
  `broker_depth`, derived from the loaded window, never a hand list.
- **Sessions (G2).** The candles are the stock's own daily price bars whose dates fall inside the loaded broker window;
  `FlowRows` is built with `flowRows`-equivalent code from `ThreadSnapshot.brokerRows(ticker, first, last)` (P4), mapping
  each broker row to its candle by date; a broker row on a date without a price bar is not counted (as the Terminal).
  Index mapping: P4 files code investor types Domestic=0, Foreign=1 and boards Regular, Nego, Tunai; flow.ts uses
  INVESTORS Foreign=0, Domestic=1 and BOARDS Regular, Nego, Cash (Tunai = Cash): convert, test it.
- **Context.** `close`, `volume` from the same bars; `dates` the bars' dates; `classification` from the reference file
  `brokers` (`IDX_Broker_Profile` classes, the file the Terminal reads; the worker loads it beside `tickers`);
  `insider` is not published to the worker: FL31 stays unavailable (`REQUIRES_DATA`) until an insider file exists.
- **Evaluation date (P10 a).** A flow value is read at the stock's last candle with broker data on or before the
  evaluation date; the cell carries `eval_date` = that date and source `flow`. A stock without broker data in the window
  is `na` with `FLOW_UNAVAILABLE`.
- **Availability.** Flow conditions need `broker_window.complete` true; otherwise the screen is refused with
  `FLOW_UNAVAILABLE` and a message saying the broker data is still loading. With no broker days at all every flow entry
  shows `REQUIRES_DATA`.
- **Series.** A flow output is a full series over the window candles, so every operator (OPERATORS.md: measures and
  tests, rank across stocks at S1) applies to it as to an indicator; the output type for K7 and the measure rules comes
  from the feasibility table (section 2).
- **Cost.** One `computeFlow` per (ticker, id, params) per snapshot, cached in the thread's series cache; cost units from
  what it computes on the ticker: its broker rows and its grid of brokers x (sessions + 1) cells (QA unit B, QA4; the
  window length alone predicted about 3000 times too low; `verification/screener/BENCHMARK_FLOW_COST.md`); the plan
  prunes as for indicators.
- **Cells and words.** Values in the registry's `unit`; the condition summary names the FL id, name and parameters.

## 2. Catalog (stage P5a)

- Generated from `flowRegistry.json` by the screener registry generator (`apps/edge-bff/screener/scripts/
  build-screener-registry.mjs`): 48 entries, one per FL, with the registry's name, family, unit, outputs, tip and
  parameters, and the default board Regular (G1, the registry's default). They replace the 20 old flow entries of
  `screener-metrics.json` (FLOW_MAP.md maps each old entry to its FL).
- A data table (`apps/edge-bff/screener/src/core/flow-kinds.json`) gives each FL output its kind from EXEC.md (K
  normalized, P percentile/z, Rp rupiah, L lots per transaction, H price level, D day count, F 0/1 signal, B broker
  count) and the ADV floor flag (FL03-FL06, FL08, FL10, FL13-FL15, FL36, FL46). The operators block reads it: rank and
  percentile-type measures not on H, = and != only on D, F and B (K7). A test fails when an FL has no row.
- FL31 is listed with `REQUIRES_DATA` (no insider file).

## 3. Screener-only versions and old formulas (stage P5b)

- FL23 screener version (decision B): series a cumulative inventory, b daily net, c inventory / traded value over L
  sessions; Top-K holders, lookback L, at least X brokers.
- FL18, FL19, FL20, FL44, FL45 with an anchor N sessions back from the evaluated date (decisions D, E) instead of a date.
- Old formulas (user 2026-11-07): rebuilt with operators (broker net N sessions through FL23 a; 1/H through FL38; Big
  Acc/Dist through a range on FL24 ±6/±10; distribution days through Persistence); kept as screener entries (`fnet`
  foreign net rupiah D sessions; KSEI major-holder net stays `REQUIRES_DATA`: no KSEI file; FL34 point-in-time guard);
  the old breadth entry removed (FL22 replaces it). The 8 bandar presets map to these. A test shows each rebuilt one
  equals the old definition on the same rows.

As built (2026-11-07; data in `apps/edge-bff/screener/src/core/flow-kinds.json` `screener`, `screener_params`,
`screener_entries`; generated by `build-screener-registry.mjs` flowEntries; computed by `src/core/flowscreener.ts`
through `flowmetrics.ts` computeEntry; tests `tests/core/flow-screener.test.ts`, `tests/core/old-formulas.test.ts`):
- **Anchor N sessions back** (FL18, FL19, FL20, FL44, FL45; `compute: anchored`): the date `anchor` is replaced by
  `anchor_sessions` (int 1 to window - 1 = 59, default 20). At each candle s, computeFlow runs on the candles s - N .. s
  (sliceContext, equal to flowRows of those candles' rows) with the anchor date of candle s - N, read at s, so the
  frozen Top-N cohort sees no candle after s (FORMULAS.md A8). Missing when s - N is before the first candle with broker
  data. Depth (K1) N + 1. Cost: a screen binds with `flowLazy` (screen.ts screenBinding), so the series is computed
  only on the last R + 1 sessions with broker data, R = the sessions its test reads (an event's within, a window's
  length) plus its local operators' N (transforms.ts operandReach; a moving average, a historical average or a rising
  run reads the whole history, so the full series), one memo entry per candle shared with the full series; the first
  value is found too when a read session has none (the NA reason). A value test: one computeFlow per stock (heavy
  fixture, 100 brokers, 15,694 rows: FL18 full 19.1 ms, value test 0.5 ms, cross within 3 1.5 ms). The worker's cost
  units count, per session computed, the slice's rows (rows x (N + 1) / the window) and its grid of brokers x (N + 2),
  plus the window's rows once (run.ts costUnits; BENCHMARK_FLOW_COST.md).
- **FL23 Broker Inventory, screener version** (`compute: inventory`; parameters `holders` top / selected / all,
  `brokers` (0-5, read with selected), `top` K (1-5), `unit`, `series`, `lookback` L (1-60, default 20), `boards`,
  `investors`, `move` up / down, `move_min`; the Terminal's `view`, `total`, `start` are not condition parameters):
  per broker the Terminal's FL23 daily net d_b; a_b(s) = d_b over the L candles ending at s, added in candle order (the
  Terminal's cumulative line started at s - L + 1); c_b(s) = 100 x a_b(s) / TV(s), TV = every investor's gross buy
  (lots for unit lot) on the boards over the L candles. Holders: the K largest positive a_b (ties by code), the named
  brokers, or every broker. Output `value`: the sum over the holders of a (series cum), d (daily) or 100 x sum a / TV
  (norm); kind Rp (lot or IDR) for a and b, K (%) for c. Output `count` (kind B, "=" offered): the holders whose series
  is above 0 and at least move_min (up) or below 0 and at most -move_min (down). Depth L (1 for daily without Top-K).
- **fnet** (`compute: foreign_net`; `window` D 1-60 default 20, `boards` default every board): the foreign investors'
  buy value minus sell value over the D candles ending at t, kind Rp.
- **ksei_net** (`requires: ksei`, never computed): REQUIRES_DATA with its reason.
- **FL34 guard** (`current_only`): the value is kept on the last date of the loaded broker window only; every earlier
  candle is missing, so a stock whose last broker session is earlier and any operator over FL34's history are n/a.
- **Old formulas as operators**: broker(N, X) = FL23 {selected [X], value, cum, lookback N, every board}; effective
  buyers 1/H >= k = FL38 {all, 20, value, every board} <= 1/k; Big Acc, Acc or better, Dist or worse, Big Dist = FL24
  {top 3, 10, every board} inside 10..100, 6..100, -100..-6, -100..-10; at least K distribution days of D = Persistence
  (at least K of D) of FL24 {window 1} below -x.
- **Presets** (bigacc, fstreak, silent, freq, bavg, follow, qflow, vacc): the old definitions' setup on the regular
  board (G1, user 2026-11-07: "Opsi P8B berubah, OK"; FL24 top 3, 10 sessions; FL26 all brokers, Foreign, cap 60; fnet
  20; FL32 transactions, buy, baseline 20; FL39 top 3, 10 sessions; FL23 YP, value, lookback 5), each compared with the
  old formula on the regular board; the other old formulas and Big Acc on every board on both sides.
- The 20 old Phase 2 flow entries are removed from `screener-metrics.json`; a request naming one is refused
  INVALID_CONDITION with the flow entries' ids.

## 4. Page (stage P5c)

- Flow entries in Add a condition with their Terminal parameters (multi boards and investor types, selects, ints) and
  the operators; = and != shown for D, F and B outputs; the broker data date in the cells and the Preview.

## 5. Tests

- Parity: for every FL and default parameters, the Screener's value equals `computeFlow` called the Terminal's way
  (Terminal `flowRows` from the same rows), bit for bit, on a fixture of several stocks over 60 sessions, including a
  Nego-only day and a day without a price bar.
- Validation refusals per rule; depth refusal derived from the window; availability; evaluation date; mapping of
  investor types and boards; operators on a flow series (percentile, at_least, rank); K7.

## 4b. As built (P5c, 2026-11-07)

- Every flow entry is offered from its catalog data (no FL id in the page): parameters by kind (whole numbers and numbers
  with min/max, selects, switches, boards and investor types as checkboxes, broker codes, and the anchor as a whole number
  of sessions back from the evaluated date: the catalog's anchored entries take `anchor_sessions`, section 3; a date field
  inside the broker window is drawn only for an entry the catalog anchors by a date, and none does), the entry's own
  conditions per output type, and Measure + Test; "=" and "!=" only on D, F and B outputs.
- Depth: the worker is the only authority (the page bundle may not import flow.ts). The page shows "about N sessions of
  broker data left at this setup" as a hint and never refuses a depth in place; a too-deep condition gets the worker's
  `LIMIT_EXCEEDED broker_depth` refusal on its card. Follow-up (not in this release): a depth table generated from the
  core probe into the catalog, so the page can refuse exactly in place.
- The broker data date: cell tooltip, a short date beside a value older than the stock's prices, under each condition in
  the Preview, and "Broker data through ..." in Method & sources. The old disabled "Bandar status thresholds (Phase 3)"
  fields are gone: each condition holds its own thresholds.
