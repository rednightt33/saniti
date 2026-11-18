/* Request checks that need no market data beyond terminal-api's reference ticker list (CONTRACT.md section 3), shared
   by POST /v1/validate, POST /v1/jobs (a refused request never becomes a job) and the job itself:
   - every object holds only the fields the page sends (contract.ts); anything else is refused, never ignored;
   - the engine's own checks (engine.ts validateRun: mode, period, sizing, costs, exit modes and their numbers, the
     price lines, max_positions 1 to limits.max_positions and the picked stocks' count, against the configured limits
     so a refusal names the limit the catalog reports, CWP-2) and the signal checks (signals.ts requestConditions: the
     entry logic, window, at_least, ids);
   - what the engine does not check: schema_version 1, oos_fraction one of the page's 0 / 0.2 / 0.3 / 0.4, Monte Carlo
     runs exactly limits.monte_carlo_runs or 0 and a whole seed >= 0, the single ticker a published stock, the picked
     stocks 1 to limits.max_portfolio_tickers distinct published stocks (pickedStocks, PF2; an index is not tradable);
     the numbers and price lines the chosen modes do not read held to their type (unreadTypes), and no value on a
     price-action type without a threshold;
   - every condition, enabled or not, as conditions.ts checks it, on an empty bar set: its kind, the registry
     indicator, its parameters, operator, outputs and value, the price-action parameters and thresholds, the flow
     condition's shape (flowConditionShape). Only INDICATOR_OUTPUT_EMPTY needs the ticker's bars, so it is left to the
     run. A disabled condition is not evaluated, but it is stored with the job and kept by the page, so it is held to
     the same shape; what only an evaluation needs is checked on the enabled ones: flow conditions and rank_by 'fnet'
     are FLOW_UNAVAILABLE while flow is off (catalog.flow.available false), and a broker condition's code must be a
     broker of terminal-api's broker reference list (UNKNOWN_BROKER; a listed broker without any row on a ticker's bars
     has a net of 0 there, flow.ts brokerNet);
   - a condition id has the page's shape (CONDITION_ID) and a list has at most limits.max_conditions enabled
     conditions (LIMIT_EXCEEDED): the result repeats the ids per ticker track and per trade.
   PERIOD_AFTER_DATA (IHSG's last bar) and FLOW_DATA_THROUGH (the broker data's date) need terminal-api's manifests
   (run.ts checkPublished, at /v1/validate, and the run again); the other data-dependent errors are the run's: they need
   the published files. */
import type { BacktestRequest, SignalsPreviewRequest } from '../../edge-bff/backtest/src/core/contract.ts';
import { Calc, PRICE_ACTION, conditionSeries, flowConditionShape } from '../../edge-bff/backtest/src/core/conditions.ts';
import type { Condition as CoreCondition, FlowCondition } from '../../edge-bff/backtest/src/core/conditions.ts';
import { lineOf, portfolioTickers, validateRun } from '../../edge-bff/backtest/src/core/engine.ts';
import { ValidationError } from '../../edge-bff/backtest/src/core/registry.ts';
import { RANK_ITEM, byTicker, isIsoDate, requestConditions } from '../../edge-bff/backtest/src/core/signals.ts';
import { LEGACY } from '../../edge-bff/backtest/src/core/catalog.ts';
import type { ActiveCondition } from '../../edge-bff/backtest/src/core/signals.ts';
import type { Config } from './config.ts';
import { invalid } from './errors.ts';
import { checkTest, flowRefs, installBacktestGrammar, testItems } from './grammar.ts';
import { ALLOW_ALL, requireItem } from './access.ts';
import type { Allow } from './access.ts';
import { D_RIGHT, isD } from './pit/spec.ts';
import { canonicalJson } from '../../edge-bff/backtest/src/core/hash.ts';
import { FLOW_BY_ID } from '../../edge-bff/screener/src/core/flowmetrics.ts';
import SCREENER_METRICS from '../../edge-bff/screener/src/core/screener-metrics.json' with { type: 'json' };
import { CANDLE_IDS } from '../../edge-bff/backtest/src/core/candles.ts';
import type { AllowKind } from './access.ts';
import type { BrokerRef, TickerRef } from './terminal.ts';

// EXEC-BACKTEST-REVAMP P1: conditions in the Screener's grammar (kind 'test') are computed by the Screener core
// (grammar.ts). Every path that checks or runs a request imports this module (server.ts on the main thread, run.ts in
// each compute thread), so the grammar is installed once per thread here, before any condition is read.
installBacktestGrammar();

export const OOS_FRACTIONS = [0, 0.2, 0.3, 0.4];         // the page's Out-of-sample select: none, last 20 / 30 / 40 %
/** A condition id as the page makes it, Math.random().toString(36).slice(2, 8) (state.ts mkCond, reg.ts mkReg,
    workspace.ts): 1 to 6 base-36 digits. */
export const CONDITION_ID = /^[0-9a-z]{1,6}$/;
const fail = (code: string, field: string, message: string): never => { throw new ValidationError(code, field, message) };
const isObject = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);

/* ---- the fields of each object (contract.ts, as the page's buildRequest and catalog.ts write them) ------------------ */
const FIELDS: Record<string, string[]> = {
  request: ['schema_version', 'mode', 'single', 'portfolio', 'period', 'entry', 'exit', 'sizing', 'costs', 'robustness'],
  single: ['ticker', 'benchmark'],
  portfolio: ['tickers', 'max_positions', 'rank_by', 'min_avg_value_20d_idr'],
  period: ['from', 'to', 'oos_fraction'],
  entry: ['logic', 'at_least', 'window_bars', 'conditions'],
  exit: ['atr_length', 'stop', 'take_profit', 'trailing', 'max_hold_bars', 'signals'],
  stop: ['mode', 'pct', 'atr_mult', 'reward_risk_x', 'line'],
  take_profit: ['mode', 'pct', 'r_multiple', 'atr_mult'],
  trailing: ['mode', 'pct', 'chandelier_length', 'chandelier_mult', 'line'],
  line: ['indicator', 'output', 'params'],
  signals: ['logic', 'conditions'],
  sizing: ['capital_idr', 'allocation_fraction'],
  costs: ['buy_fee', 'sell_fee', 'slippage', 'skip_ara_open_gap', 'ara_gap_fraction'],
  robustness: ['monte_carlo_runs', 'seed', 'sensitivity'],
  indicator: ['id', 'enabled', 'kind', 'indicator', 'params', 'lhs', 'op', 'rhs'],
  price_action: ['id', 'enabled', 'kind', 'type', 'params', 'op', 'value'],
  flow: ['id', 'enabled', 'kind', 'type', 'params', 'op', 'value'],
  preview: ['schema_version', 'tickers', 'period', 'entry', 'detail'],
  preview_period: ['from', 'to'],
  preview_detail: ['ticker', 'exit_signals'],
};
const CONDITION_KINDS = ['indicator', 'price_action', 'flow'];
const SIDE: Record<string, string[]> = { price: ['type'], output: ['type', 'output'], value: ['type', 'value'] };

/** Refuses a field the object should not have (a plain object only; a missing or malformed one is the checks' job). */
function only(o: unknown, kind: string, field: string): void {
  if (!isObject(o)) return;
  for (const k of Object.keys(o)) if (!FIELDS[kind].includes(k))
    fail('UNKNOWN_FIELD', field ? `${field}.${k}` : k, `${field ? `${field}.${k}` : k} is not a field of the request.`);
}
function conditionFields(list: unknown, field: string): void {
  if (!Array.isArray(list)) return;
  list.forEach((c, k) => {
    const f = `${field}[${k}]`;
    if (!isObject(c) || typeof c.kind !== 'string' || !CONDITION_KINDS.includes(c.kind)) return;   // conditions.ts refuses the kind itself
    only(c, c.kind, f);
    // a price-action type without a threshold (conditions.ts PRICE_ACTION value false) has no value: contract.ts
    // "dip (fraction) and volspike (ratio) only", and the page's cards send none (catalog.ts legacyToCondition)
    if (c.kind === 'price_action' && 'value' in c && typeof c.type === 'string' && Object.prototype.hasOwnProperty.call(PRICE_ACTION, c.type) && PRICE_ACTION[c.type].value === false)
      fail('UNKNOWN_FIELD', `${f}.value`, `${f}.value is not a field of a ${c.type} condition: it has no threshold.`);
    if (c.kind === 'indicator') for (const s of ['lhs', 'rhs'] as const) {
      const side = c[s];
      if (isObject(side) && typeof side.type === 'string' && SIDE[side.type])
        for (const key of Object.keys(side)) if (!SIDE[side.type].includes(key)) fail('UNKNOWN_FIELD', `${f}.${s}.${key}`, `${f}.${s}.${key} is not a field of a ${side.type} side.`);
    }
  });
}
function entryFields(e: unknown, field: string): void {
  only(e, 'entry', field);
  if (isObject(e)) conditionFields(e.conditions, `${field}.conditions`);
}

/** terminal-api's reference lists a request is checked against (GET /reference/tickers and /reference/brokers). */
export interface References { tickers: readonly TickerRef[]; brokers: readonly BrokerRef[] }

/* ---- the picked stocks of a portfolio (PF1-PF3, user N 2026-10-27) -------------------------------------------------- */
/** A tradable security: every published type but an index (stock, fund = ETF; EXEC-UNIVERSE-BROKER S1.4, 2026-11-05). */
export const tradable = (r: TickerRef) => !!r.type && r.type !== 'index';
/** Every published tradable security (above), ticker order. */
export const stocksOf = (refs: readonly TickerRef[]) => refs.filter(tradable).map(r => r.ticker).sort(byTicker);
/** A portfolio's picked stocks (portfolio.tickers, a preview's tickers): 1 to limits.max_portfolio_tickers distinct
    strings (engine.ts portfolioTickers: INVALID_PORTFOLIO at `field`), each a published stock (UNKNOWN_TICKER at
    `field`[i], single.ticker's code and wording: an index is not tradable), checked before any download; in ticker
    order, the canonical order the run and its hashes use (PF3). */
export function pickedStocks(v: unknown, refs: References, max: number, field: string): string[] {
  const sorted = portfolioTickers(v, max, 'INVALID_PORTFOLIO', field);
  (v as string[]).forEach((t, k) => {
    if (!refs.tickers.some(x => x.ticker === t && tradable(x))) fail('UNKNOWN_TICKER', `${field}[${k}]`, `${t} is not a published stock.`);
  });
  return sorted;
}

/* ---- conditions without bars --------------------------------------------------------------------------------------- */
const EMPTY = { O: [], H: [], L: [], C: [], V: [], T: [] };
/** field: where the condition's refusals point (a preview's detail.exit_signals as a run's exit.signals); path: its
    JSON path in the body, which a CAPABILITY_REQUIRED refusal names (Phase 3b). */
interface Listed { field: string; path: string; cond: CoreCondition; enabled: boolean }
/** Every condition of a list, enabled or not, after requestConditions has checked the list, each object, id and flag. */
const listed = (list: unknown, field: string, path = field): Listed[] =>
  (list as CoreCondition[]).map((cond, k) => ({ field: `${field}[${k}]`, path: `${path}[${k}]`, cond, enabled: (cond as { enabled?: boolean }).enabled !== false }));
/** At most limits.max_conditions enabled conditions per list. */
function withinConditions(lists: [readonly ActiveCondition[], string][], max: number): void {
  for (const [list, field] of lists) if (list.length > max)
    throw invalid('LIMIT_EXCEEDED', field, `${field} has ${list.length} enabled conditions; the limit is ${max}.`, { limit: 'max_conditions', allowed: max, needed: list.length });
}
/** What the conditions read besides the prices: the broker files (a flow condition, a Flow indicator in the grammar),
    and the broker rows as columns (a Flow indicator in the grammar, EXEC-BACKTEST-REVAMP P3). */
interface Reads { broker: boolean; columns: boolean }
/** The broker codes a Flow reference names must be brokers of the published broker list (UNKNOWN_BROKER, naming the
    entry). Its lists are the registry's parameters of kind 'brokers' (brokers, num_brokers, den_brokers, FL34's inst and
    retail; Stage C F8: a name pattern missed inst and retail), so a new one is covered. */
function flowBrokers(ref: Record<string, unknown>, field: string, brokers: readonly BrokerRef[]): void {
  const params = ref.params && typeof ref.params === 'object' ? ref.params as Record<string, unknown> : {};
  const e = typeof ref.metric === 'string' ? FLOW_BY_ID[ref.metric] : undefined;
  const lists = (k: string) => e ? e.params.some(p => p.key === k && p.kind === 'brokers') : /(^|_)brokers$/.test(k);
  for (const [k, v] of Object.entries(params)) if (lists(k) && Array.isArray(v))
    v.forEach((code, j) => { if (typeof code === 'string' && !brokers.some(b => b.code === code)) fail('UNKNOWN_BROKER', `${field}.params.${k}[${j}]`, `${field}.params.${k}[${j}]: ${code} is not a broker of the published broker list.`) });
}
/** The rights a request's context carries (P5: set by edge-bff from the session; none when absent: fail closed). */
export type Rights = ReadonlySet<string>;
export const NO_RIGHTS: Rights = new Set();
/** The catalog kind of a legacy card's type (a price-action or flow card of the Backtest core), derived from the
    registries at load so a future legacy type that matches a catalog id is gated by it: a Screener metric id
    (screener-metrics.json metrics, the ids of releases.json screener_metric: breakout, volspike, macross today), a Flow
    indicator id (the Screener registry's flows: flowRegistry.json and fnet, ksei_net; fnet today), a legacy card of
    the core's flow group (catalog.ts LEGACY group 'flow': fnet, broker, top5; they read broker data, so they follow
    the flow rule, CONTRACT 8b "3b follow-up", user decision 2026-11-18; releases.json lists them, edge-bff
    tests/test_releases.py derives them from the same group) or a candlestick id. null: a built-in technical type with
    no catalog id (dip, macd today), part of the Backtest and not gated. */
const METRIC_IDS = new Set((SCREENER_METRICS as { metrics: { id: string }[] }).metrics.map(m => m.id));
const LEGACY_FLOW = new Set(Object.entries(LEGACY).filter(([, s]) => s.group === 'flow').map(([t]) => t));
export function legacyItemKind(type: string): AllowKind | null {
  if (METRIC_IDS.has(type)) return 'screener_metric';
  if (Object.prototype.hasOwnProperty.call(FLOW_BY_ID, type) || LEGACY_FLOW.has(type)) return 'flow_indicator';
  if (CANDLE_IDS.includes(type)) return 'candle_pattern';
  return null;
}
/** Phase 3b (CONTRACT 8b): every catalog item a condition names, enabled or switched off (it is stored with the job and
    kept by the page), must be in the plan's allow, else 403 CAPABILITY_REQUIRED at the item's JSON path: a registry
    indicator condition's indicator, every item of a grammar test (grammar.ts testItems), and a legacy price-action or
    flow card whose type is a catalog id (legacyItemKind), so the legacy cards are no second path around the plan. */
function conditionItems(list: readonly Listed[], allow: Allow): void {
  if (allow === ALLOW_ALL) return;
  for (const { path, cond: c } of list) {
    if (c.kind === 'indicator' && typeof (c as { indicator?: unknown }).indicator === 'string') requireItem(allow, 'indicator', (c as { indicator: string }).indicator, `${path}.indicator`);
    if (c.kind === 'test') for (const it of testItems((c as { test?: unknown }).test, `${path}.test`)) requireItem(allow, it.kind, it.id, it.field);
    if ((c.kind === 'price_action' || c.kind === 'flow') && typeof (c as { type?: unknown }).type === 'string') {
      const type = (c as { type: string }).type, kind = legacyItemKind(type);
      if (kind) requireItem(allow, kind, type, `${path}.type`);
    }
  }
}
/** The price lines of the exits (stop and trailing), held to the plan whatever their mode: both are stored with the
    job and hashed, as the numbers the chosen modes do not read (unreadTypes). The ATR stop, target and chandelier
    compute I30 as part of the Backtest and name no item (CONTRACT 8b "3b follow-up", user decision 2026-11-18). */
function lineItems(q: BacktestRequest, allow: Allow): void {
  if (allow === ALLOW_ALL) return;
  for (const part of ['stop', 'trailing'] as const) {
    const id = (q.exit[part]?.line as { indicator?: unknown } | undefined)?.indicator;
    if (typeof id === 'string') requireItem(allow, 'indicator', id, `exit.${part}.line.indicator`);
  }
}
function checkConditions(list: readonly Listed[], flow: Config['flow'], brokers: readonly BrokerRef[], maxFlow = Number.MAX_SAFE_INTEGER, rights: Rights = NO_RIGHTS, allow: Allow = ALLOW_ALL): Reads {
  let needsBroker = false, columns = false;
  const series = new Set<string>();
  conditionItems(list, allow);
  for (const { field, cond: c, enabled } of list) {
    if (!CONDITION_ID.test(c.id)) fail('INVALID_CONDITION', `${field}.id`, `${field}.id must be 1 to 6 lowercase letters or digits, as the page makes it.`);
    // EXEC-BACKTEST-REVAMP P4-P5: the point-in-time indicators are for admins only, enforced here at every depth of the
    // test and on a switched-off condition too (it is stored with the job and kept by the page): CONDITION_RESTRICTED
    if (c.kind === 'test') for (const r of flowRefs((c as { test?: unknown }).test, `${field}.test`))
      if (isD(r.ref.metric) && !rights.has(D_RIGHT))
        fail('CONDITION_RESTRICTED', r.field, `${field}: ${r.ref.metric} (point in time) is available to admins only; remove this condition to run the strategy.`);
    if (c.kind === 'test' && enabled) {
      const refs = flowRefs((c as { test?: unknown }).test, `${field}.test`);
      if (refs.length) {
        if (!flow.enabled) fail('FLOW_UNAVAILABLE', refs[0].field, `${refs[0].field}: the Flow indicators need the broker data, which is not available. ${flow.reason ?? ''}`.trim());
        for (const r of refs) flowBrokers(r.ref, r.field, brokers);
        // distinct by their completed form (the Screener's validation fills the parameters)
        for (const r of flowRefs(checkTest(c, field), `${field}.test`)) series.add(canonicalJson({ metric: r.ref.metric, output: r.ref.output ?? null, params: r.ref.params ?? {} }));
        if (series.size > maxFlow)
          throw invalid('FLOW_BUDGET_EXCEEDED', field, `This request reads ${series.size} distinct Flow series; the limit is ${maxFlow} (catalog limits.max_flow_series). Remove some Flow conditions, or read the same Flow indicator with the same settings in several conditions.`,
            { limit: 'max_flow_series', allowed: maxFlow, needed: series.size });
        needsBroker = columns = true;
      }
    }
    if (c.kind === 'flow') {
      if (enabled && !flow.enabled) fail('FLOW_UNAVAILABLE', field, `${field}: flow and broker conditions are not available. ${flow.reason ?? ''}`.trim());
      const { broker } = flowConditionShape(c as FlowCondition, field);
      if (!enabled) continue;
      if (broker !== null && !brokers.some(b => b.code === broker))
        fail('UNKNOWN_BROKER', `${field}.params.broker`, `${field}: ${broker} is not a broker of the published broker list.`);
      needsBroker = true;
      continue;
    }
    try { conditionSeries(new Calc(EMPTY), c, field) }                // an unknown kind is UNKNOWN_CONDITION here
    catch (e) { if (!(e instanceof ValidationError && e.code === 'INDICATOR_OUTPUT_EMPTY')) throw e }   // needs the ticker's bars
  }
  return { broker: needsBroker, columns };
}

/* ---- the fields the chosen modes do not read ----------------------------------------------------------------------- */
/* engine.ts validateRun checks a number or a price line where the chosen mode reads it (its range there too), and
   combineEntry checks at_least under logic at_least only. The others are stored with the job and hashed into
   request_hash all the same, so each is held to its contract.ts type: a finite number, a price line as a line mode
   takes it (engine.ts lineOf). Only the type: the page keeps what was typed into a field it no longer shows (builder.ts
   reads a cleared number input as 0), so a range there would refuse a request whose run does not depend on it. */
const UNREAD_NUMBERS = { stop: ['pct', 'atr_mult', 'reward_risk_x'], take_profit: ['pct', 'r_multiple', 'atr_mult'], trailing: ['pct', 'chandelier_length', 'chandelier_mult'] } as const;
const number = (v: unknown, code: string, field: string) => { if (typeof v !== 'number' || !Number.isFinite(v)) fail(code, field, `${field} must be a number.`) };
const entryTypes = (e: BacktestRequest['entry']) => number(e.at_least, 'INVALID_ENTRY', 'entry.at_least');
function unreadTypes(q: BacktestRequest): void {
  entryTypes(q.entry);
  number(q.exit.atr_length, 'INVALID_EXIT', 'exit.atr_length');
  for (const [part, keys] of Object.entries(UNREAD_NUMBERS) as [keyof typeof UNREAD_NUMBERS, readonly string[]][])
    for (const k of keys) number((q.exit[part] as unknown as Record<string, unknown>)[k], 'INVALID_EXIT', `exit.${part}.${k}`);
  lineOf(q.exit.stop.line, 'exit.stop.line');
  lineOf(q.exit.trailing.line, 'exit.trailing.line');
  number(q.sizing.allocation_fraction, 'INVALID_SIZING', 'sizing.allocation_fraction');
}

export interface CheckedRequest {
  tickers: string[];            // single: [ticker]; portfolio: the picked stocks, ticker order (PF3)
  broker: boolean;              // the run reads the broker files (a flow condition, or rank_by 'fnet')
  columns: boolean;             // the run keeps the broker rows as columns (a Flow indicator in the grammar, P3)
}

/** A backtest request checked as far as it can be without market data; ValidationError (422) otherwise. */
export function checkRequest(input: unknown, refs: References, cfg: Pick<Config, 'limits' | 'flow'>, rights: Rights = NO_RIGHTS, allow: Allow = ALLOW_ALL): CheckedRequest {
  if (!isObject(input)) fail('INVALID_REQUEST', 'request', 'The request must be a JSON object.');
  const q = input as unknown as BacktestRequest;
  only(q, 'request', '');
  if (q.schema_version !== 1) fail('INVALID_REQUEST', 'schema_version', 'schema_version must be 1.');
  if (q.mode === 'single' && q.portfolio !== undefined) fail('UNKNOWN_FIELD', 'portfolio', 'A single-stock request has no portfolio settings.');
  if (q.mode === 'portfolio' && q.single !== undefined) fail('UNKNOWN_FIELD', 'single', 'A portfolio request has no single-stock settings.');
  only(q.single, 'single', 'single'); only(q.portfolio, 'portfolio', 'portfolio'); only(q.period, 'period', 'period');
  entryFields(q.entry, 'entry');
  only(q.exit, 'exit', 'exit');
  if (isObject(q.exit)) {
    only(q.exit.stop, 'stop', 'exit.stop'); only(q.exit.take_profit, 'take_profit', 'exit.take_profit'); only(q.exit.trailing, 'trailing', 'exit.trailing');
    if (isObject(q.exit.stop)) only(q.exit.stop.line, 'line', 'exit.stop.line');
    if (isObject(q.exit.trailing)) only(q.exit.trailing.line, 'line', 'exit.trailing.line');
    only(q.exit.signals, 'signals', 'exit.signals');
    if (isObject(q.exit.signals)) conditionFields(q.exit.signals.conditions, 'exit.signals.conditions');
  }
  only(q.sizing, 'sizing', 'sizing'); only(q.costs, 'costs', 'costs'); only(q.robustness, 'robustness', 'robustness');

  validateRun(q, undefined, cfg.limits);
  if (!OOS_FRACTIONS.includes(q.period.oos_fraction)) fail('INVALID_PERIOD', 'period.oos_fraction', `period.oos_fraction must be one of ${OOS_FRACTIONS.join(', ')}.`);
  const r = q.robustness;
  if (!isObject(r)) fail('INVALID_ROBUSTNESS', 'robustness', 'robustness is required.');
  if (r.monte_carlo_runs !== 0 && r.monte_carlo_runs !== cfg.limits.monte_carlo_runs)
    fail('INVALID_ROBUSTNESS', 'robustness.monte_carlo_runs', `robustness.monte_carlo_runs must be ${cfg.limits.monte_carlo_runs} or 0 (off).`);
  if (!Number.isSafeInteger(r.seed) || r.seed < 0) fail('INVALID_ROBUSTNESS', 'robustness.seed', 'robustness.seed must be a whole number of at least 0.');
  if (typeof r.sensitivity !== 'boolean') fail('INVALID_ROBUSTNESS', 'robustness.sensitivity', 'robustness.sensitivity must be true or false.');

  let tickers: string[];
  let broker = false;
  if (q.mode === 'single') {
    const t = q.single!.ticker;
    if (!refs.tickers.some(x => x.ticker === t && tradable(x))) fail('UNKNOWN_TICKER', 'single.ticker', `${t} is not a published stock.`);
    tickers = [t];
  } else {
    const p = q.portfolio!;
    tickers = pickedStocks(p.tickers, refs, cfg.limits.max_portfolio_tickers, 'portfolio.tickers');
    // the item the ranking reads (signals.ts RANK_ITEM: rank_by 'fnet' the flow item fnet; the technical rankings adx,
    // vol and rsi none, part of the Backtest), held to the plan before its data is asked for (CONTRACT 8b "3b follow-up")
    const rank = RANK_ITEM[p.rank_by];
    if (rank) requireItem(allow, rank.kind, rank.id, 'portfolio.rank_by');
    if (p.rank_by === 'fnet') {
      if (!cfg.flow.enabled) fail('FLOW_UNAVAILABLE', 'portfolio.rank_by', `Ranking by foreign net flow needs the broker data, which is not available. ${cfg.flow.reason ?? ''}`.trim());
      broker = true;
    }
  }
  const active = requestConditions(q);
  unreadTypes(q);
  lineItems(q, allow);
  withinConditions([[active.entry, 'entry.conditions'], [active.exit, 'exit.signals.conditions']], cfg.limits.max_conditions);
  const reads = checkConditions([...listed(q.entry.conditions, 'entry.conditions'), ...listed(q.exit.signals.conditions, 'exit.signals.conditions')], cfg.flow, refs.brokers, cfg.limits.max_flow_series, rights, allow);
  return { tickers, broker: broker || reads.broker, columns: reads.columns };
}

/** A signals preview request (SignalsPreviewRequest) checked the same way. */
export function checkSignalsRequest(input: unknown, refs: References, cfg: Pick<Config, 'limits' | 'flow'>, rights: Rights = NO_RIGHTS, allow: Allow = ALLOW_ALL): CheckedRequest {
  if (!isObject(input)) fail('INVALID_REQUEST', 'request', 'The request must be a JSON object.');
  const q = input as unknown as SignalsPreviewRequest;
  only(q, 'preview', ''); only(q.period, 'preview_period', 'period'); entryFields(q.entry, 'entry');
  // Stage D (D6): the detail ticker's tracks, with its exit signal conditions checked as a run's exit.signals
  only(q.detail, 'preview_detail', 'detail');
  const exit = isObject(q.detail) ? q.detail.exit_signals : undefined;
  if (isObject(q.detail)) { only(exit, 'signals', 'detail.exit_signals'); if (isObject(exit)) conditionFields(exit.conditions, 'exit.signals.conditions') }
  if (q.schema_version !== 1) fail('INVALID_REQUEST', 'schema_version', 'schema_version must be 1.');
  if (!isObject(q.period)) fail('INVALID_PERIOD', 'period', 'period is required.');
  if (!isIsoDate(q.period.from)) fail('INVALID_PERIOD', 'period.from', 'period.from must be a date YYYY-MM-DD.');
  if (!isIsoDate(q.period.to)) fail('INVALID_PERIOD', 'period.to', 'period.to must be a date YYYY-MM-DD.');
  if (q.period.from > q.period.to) fail('INVALID_PERIOD', 'period.to', 'period.to must not be before period.from.');
  const tickers = pickedStocks(q.tickers, refs, cfg.limits.max_portfolio_tickers, 'tickers');
  if (q.detail !== undefined) {
    if (!isObject(q.detail) || typeof q.detail.ticker !== 'string' || !tickers.includes(q.detail.ticker))
      fail('INVALID_REQUEST', 'detail.ticker', 'detail.ticker must be one of the picked tickers.');
    if (exit !== undefined && !isObject(exit)) fail('INVALID_REQUEST', 'detail.exit_signals', 'detail.exit_signals must be an object {logic, conditions}.');
  }
  const active = requestConditions({ entry: q.entry, ...(isObject(exit) ? { exit: { signals: exit } } : {}) } as never);
  entryTypes(q.entry);
  withinConditions([[active.entry, 'entry.conditions'], [active.exit, 'exit.signals.conditions']], cfg.limits.max_conditions);
  const reads = checkConditions([...listed(q.entry.conditions, 'entry.conditions'), ...(isObject(exit) ? listed(exit.conditions, 'exit.signals.conditions', 'detail.exit_signals.conditions') : [])],
    cfg.flow, refs.brokers, cfg.limits.max_flow_series, rights, allow);
  return { tickers, broker: reads.broker, columns: reads.columns };
}
