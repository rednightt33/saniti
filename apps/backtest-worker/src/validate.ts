/* Request checks that need no market data beyond terminal-api's reference ticker list (CONTRACT.md section 3), shared
   by POST /v1/validate, POST /v1/jobs (a refused request never becomes a job) and the job itself:
   - every object holds only the fields the page sends (contract.ts); anything else is refused, never ignored;
   - the engine's own checks (engine.ts validateRun: mode, period, sizing, costs, exit modes and their numbers, the
     price lines) and the signal checks (signals.ts requestConditions: the entry logic, window, at_least, ids);
   - what the engine does not check: schema_version 1, oos_fraction one of the page's 0 / 0.2 / 0.3 / 0.4, Monte Carlo
     runs exactly limits.monte_carlo_runs or 0 and a whole seed >= 0, max_positions within limits.max_positions, the
     single ticker a published stock, the universe a catalog universe;
   - every enabled condition as conditions.ts checks it, on an empty bar set: the registry indicator, its parameters,
     operator, outputs and value, the price-action parameters and thresholds. Only INDICATOR_OUTPUT_EMPTY needs the
     ticker's bars, so it is left to the run. Flow conditions and rank_by 'fnet' are FLOW_UNAVAILABLE while flow is off
     (catalog.flow.available false), else checked by conditions.ts flowConditionShape.
   PERIOD_AFTER_DATA (IHSG's last bar) and the data-dependent errors are the run's: they need the published files. */
import type { BacktestRequest, SignalsPreviewRequest } from '../../edge-bff/backtest/src/core/contract.ts';
import { Calc, conditionSeries, flowConditionShape } from '../../edge-bff/backtest/src/core/conditions.ts';
import type { Condition as CoreCondition, FlowCondition } from '../../edge-bff/backtest/src/core/conditions.ts';
import { validateRun } from '../../edge-bff/backtest/src/core/engine.ts';
import { ValidationError } from '../../edge-bff/backtest/src/core/registry.ts';
import { isIsoDate, requestConditions } from '../../edge-bff/backtest/src/core/signals.ts';
import type { ActiveCondition } from '../../edge-bff/backtest/src/core/signals.ts';
import type { Config } from './config.ts';
import type { TickerRef } from './terminal.ts';

export const OOS_FRACTIONS = [0, 0.2, 0.3, 0.4];         // the page's Out-of-sample select: none, last 20 / 30 / 40 %
const fail = (code: string, field: string, message: string): never => { throw new ValidationError(code, field, message) };
const isObject = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const byTicker = (a: string, b: string) => a < b ? -1 : a > b ? 1 : 0;

/* ---- the fields of each object (contract.ts, as the page's buildRequest and catalog.ts write them) ------------------ */
const FIELDS: Record<string, string[]> = {
  request: ['schema_version', 'mode', 'single', 'portfolio', 'period', 'entry', 'exit', 'sizing', 'costs', 'robustness'],
  single: ['ticker', 'benchmark'],
  portfolio: ['universe', 'max_positions', 'rank_by', 'min_avg_value_20d_idr'],
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
  preview: ['schema_version', 'universe', 'period', 'entry'],
  preview_period: ['from', 'to'],
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

/* ---- universes (CONTRACT section 3, D-K6): every published stock, and the stocks of each published sector ------------ */
export interface Universe { id: string; label: string; tickers: string[] }
export const stocksOf = (refs: readonly TickerRef[]) => refs.filter(r => r.type === 'stock').map(r => r.ticker).sort(byTicker);
export function universes(refs: readonly TickerRef[]): Universe[] {
  const stocks = refs.filter(r => r.type === 'stock'), all = stocksOf(refs);
  const sectors = [...new Set(stocks.map(r => r.sector).filter((s): s is string => typeof s === 'string' && s !== ''))].sort(byTicker);
  // labels as the page shows them: the name, then the count in parentheses (env.ts universeName drops the parenthesis)
  return [{ id: 'all', label: `All stocks (${all.length})`, tickers: all },
    ...sectors.map(s => { const t = stocks.filter(r => r.sector === s).map(r => r.ticker).sort(byTicker); return { id: `sector:${s}`, label: `${s} (${t.length})`, tickers: t } })];
}
export function universeMembers(refs: readonly TickerRef[], id: unknown): string[] | null {
  if (typeof id !== 'string') return null;
  return universes(refs).find(u => u.id === id)?.tickers ?? null;
}

/* ---- conditions without bars --------------------------------------------------------------------------------------- */
const EMPTY = { O: [], H: [], L: [], C: [], V: [], T: [] };
function checkConditions(list: readonly ActiveCondition[], flow: Config['flow']): boolean {
  let needsBroker = false;
  for (const a of list) {
    const c = a.cond as CoreCondition;
    if (c.kind === 'flow') {
      if (!flow.enabled) fail('FLOW_UNAVAILABLE', a.field, `${a.field}: flow and broker conditions are not available. ${flow.reason ?? ''}`.trim());
      flowConditionShape(c as FlowCondition, a.field);
      needsBroker = true;
      continue;
    }
    try { conditionSeries(new Calc(EMPTY), c, a.field) }
    catch (e) { if (!(e instanceof ValidationError && e.code === 'INDICATOR_OUTPUT_EMPTY')) throw e }   // needs the ticker's bars
  }
  return needsBroker;
}

export interface CheckedRequest {
  tickers: string[];            // single: [ticker]; portfolio: the universe's stocks, ticker order
  broker: boolean;              // the run reads the broker files (a flow condition, or rank_by 'fnet')
}

/** A backtest request checked as far as it can be without market data; ValidationError (422) otherwise. */
export function checkRequest(input: unknown, refs: readonly TickerRef[], cfg: Pick<Config, 'limits' | 'flow'>): CheckedRequest {
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

  validateRun(q);
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
    if (!refs.some(x => x.ticker === t && x.type === 'stock')) fail('UNKNOWN_TICKER', 'single.ticker', `${t} is not a published stock.`);
    tickers = [t];
  } else {
    const p = q.portfolio!;
    if (p.max_positions > cfg.limits.max_positions) fail('INVALID_PORTFOLIO', 'portfolio.max_positions', `portfolio.max_positions must be at most ${cfg.limits.max_positions}.`);
    const members = universeMembers(refs, p.universe);
    if (!members) fail('UNKNOWN_UNIVERSE', 'portfolio.universe', `${JSON.stringify(p.universe)} is not a universe of the catalog.`);
    tickers = members!;
    if (p.rank_by === 'fnet') {
      if (!cfg.flow.enabled) fail('FLOW_UNAVAILABLE', 'portfolio.rank_by', `Ranking by foreign net flow needs the broker data, which is not available. ${cfg.flow.reason ?? ''}`.trim());
      broker = true;
    }
  }
  const active = requestConditions(q);
  if (checkConditions([...active.entry, ...active.exit], cfg.flow)) broker = true;
  return { tickers, broker };
}

/** A signals preview request (SignalsPreviewRequest) checked the same way. */
export function checkSignalsRequest(input: unknown, refs: readonly TickerRef[], cfg: Pick<Config, 'flow'>): CheckedRequest {
  if (!isObject(input)) fail('INVALID_REQUEST', 'request', 'The request must be a JSON object.');
  const q = input as unknown as SignalsPreviewRequest;
  only(q, 'preview', ''); only(q.period, 'preview_period', 'period'); entryFields(q.entry, 'entry');
  if (q.schema_version !== 1) fail('INVALID_REQUEST', 'schema_version', 'schema_version must be 1.');
  if (!isObject(q.period)) fail('INVALID_PERIOD', 'period', 'period is required.');
  if (!isIsoDate(q.period.from)) fail('INVALID_PERIOD', 'period.from', 'period.from must be a date YYYY-MM-DD.');
  if (!isIsoDate(q.period.to)) fail('INVALID_PERIOD', 'period.to', 'period.to must be a date YYYY-MM-DD.');
  if (q.period.from > q.period.to) fail('INVALID_PERIOD', 'period.to', 'period.to must not be before period.from.');
  const tickers = universeMembers(refs, q.universe);
  if (!tickers) fail('UNKNOWN_UNIVERSE', 'universe', `${JSON.stringify(q.universe)} is not a universe of the catalog.`);
  const active = requestConditions({ entry: q.entry });
  return { tickers: tickers!, broker: checkConditions(active.entry, cfg.flow) };
}
