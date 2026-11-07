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
  the window length; the plan prunes as for indicators.
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

## 4. Page (stage P5c)

- Flow entries in Add a condition with their Terminal parameters (multi boards and investor types, selects, ints) and
  the operators; = and != shown for D, F and B outputs; the broker data date in the cells and the Preview.

## 5. Tests

- Parity: for every FL and default parameters, the Screener's value equals `computeFlow` called the Terminal's way
  (Terminal `flowRows` from the same rows), bit for bit, on a fixture of several stocks over 60 sessions, including a
  Nego-only day and a day without a price bar.
- Validation refusals per rule; depth refusal derived from the window; availability; evaluation date; mapping of
  investor types and boards; operators on a flow series (percentile, at_least, rank); K7.
