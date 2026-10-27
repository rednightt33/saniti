/* The backtest engine: one run of a request on published bars, as the event clock of CONTRACT.md sections 4-6
   (decisions D-E1..E6, K5a, K5c, K9, slots, period_end). Long only, whole IDX lots, no leverage, shorting, fractional
   shares or rebalancing; unused cash stays cash without interest. The output is the Ledger (ledger.ts) that
   result.ts turns into statistics, tables and robustness numbers.

   Per calendar day t of the result calendar (the union of IHSG's and the run tickers' bars inside the period):
   before the open the trailing levels move (data up to the previous close only); at the open stops, trailing stops
   and targets that gapped and pending exit-signal sells fill, then entries (sells before buys, same auction); intraday
   stops and targets on the day's range, entry bar included; at the close time exits, new exit signals (sold at the
   next bar's open), the end of the test; then the marks. Cash from an intraday or close sale is usable from the next
   open. Signals, windows and bars_held count the ticker's own bars; a day without a bar of a ticker is not filled in.

   What the period and the universe become on the data (lead decisions 2026-10-26): single mode starts at the ticker's
   first published bar when period.from is earlier (warning PERIOD_CLIPPED); a portfolio keeps its period and leaves
   out a ticker whose own data cannot serve the strategy (signals.ts EXCLUDED_CODES, and the loader's
   MarketData.excluded), listed in the warning TICKERS_EXCLUDED, and is refused when every ticker is left out
   (UNIVERSE_EMPTY: no cash-only result); the calendar is built from the tickers that run. The primary benchmark must
   have a close on the first calendar day (PERIOD_BEFORE_DATA).

   prepare(data) keeps one indicator memo per ticker (conditions.ts Calc), so the sensitivity grid's reruns of
   run(context, request) recompute only the comparisons, not the indicators. Pure module: no DOM and no Node API. */
import type { BacktestRequest, ExitPhase, ExitReason, SkippedSignal, SignalTrack } from './contract.ts';
import type { CorporateAction, PriceSeries } from './datafile.ts';
import type { FlowData } from './flow.ts';
import type { Ledger, LedgerTrade } from './ledger.ts';
import type { Num, Params } from '../../../terminal/src/calc/indicators.ts';
import { isN } from '../../../terminal/src/calc/indicators.ts';
import display from '../../../terminal/src/data/indRegistry.json' with { type: 'json' };
import { Calc } from './conditions.ts';
import { BY_ID, REGISTRY, ValidationError, indicator, resolveParams } from './registry.ts';
import { RANK_BY, barMap, conditionsWithin, emptyTrack, isIsoDate, leftOut, liquidity, periodSignals, rankScores, requestConditions, resultCalendar, signalSummary, track, unlessLeftOut } from './signals.ts';
import type { BarMap, Exclusion, RankBy, TickerSignals } from './signals.ts';
export { EXCLUDED_CODES } from './signals.ts';
export type { Exclusion } from './signals.ts';

/* ---- input ---------------------------------------------------------------------------------------------- */

/** One ticker's market data, decoded and verified by datafile.ts (and flow.ts for the broker files). */
export interface TickerData {
  prices: PriceSeries;                     // published bars as they are (no adjusted close), bars.T = dates
  corporate_actions: CorporateAction[];    // price-affecting actions only (datafile corporateActions)
  flow?: FlowData;                         // aligned with prices.bars; absent while catalog.flow.available is false
}
/** Everything a run reads. IHSG is always present (calendar, IHSG benchmark). Single mode reads the request's ticker;
    portfolio mode trades every ticker of `tickers`, so the worker loads exactly the universe the run uses.
    excluded: universe tickers the loader left out (portfolio: no published files, DATA_MISSING); the run lists them
    in its TICKERS_EXCLUDED warning with the tickers it leaves out itself. */
export interface MarketData { ihsg: PriceSeries; tickers: Record<string, TickerData>; excluded?: Exclusion[] }

export interface Hooks { progress?(done: number, total: number): void; shouldStop?(): boolean }
/** Thrown by run() when hooks.shouldStop() answers true (job state CANCELLED). */
export class Cancelled extends Error {
  code = 'CANCELLED';
  constructor() { super('The backtest was cancelled.'); this.name = 'Cancelled' }
}

/** Market data that cannot be used as it is (datafile.ts raises the same codes while decoding). */
export class EngineDataError extends Error {
  code: 'DATA_MISSING' | 'DATA_INTEGRITY'; field?: string;
  constructor(code: 'DATA_MISSING' | 'DATA_INTEGRITY', message: string, field?: string) { super(message); this.code = code; this.field = field; this.name = 'EngineDataError' }
}

/* ---- prepared context: per-ticker indicator memos, reused by every run on the same data --------------------- */
interface Prepared {
  ticker: string; data: TickerData; calc: Calc;
  O: readonly number[]; H: readonly number[]; L: readonly number[]; C: readonly number[];
  scores: Partial<Record<RankBy, Num[]>>; liq: Num[] | null; maps: Map<string, BarMap>;
}
export interface Context {
  data: MarketData;
  tickers: Map<string, Prepared>;          // filled on first use
  calendars: Map<string, string[]>;        // result calendars by period and run tickers
}

function checkSeries(s: PriceSeries, name: string, ohlc: boolean): void {
  const { dates, bars } = s, n = dates.length;
  if (bars.C.length !== n || (ohlc && (bars.O.length !== n || bars.H.length !== n || bars.L.length !== n)))
    throw new EngineDataError('DATA_INTEGRITY', `${name}: bars and dates have different lengths.`, name);
  for (let i = 0; i < n; i++) {
    if (i && !(dates[i] > dates[i - 1])) throw new EngineDataError('DATA_INTEGRITY', `${name}: dates are not strictly increasing at ${dates[i]}.`, name);
    if (!isN(bars.C[i]) || (ohlc && !(isN(bars.O[i]) && isN(bars.H[i]) && isN(bars.L[i]))))
      throw new EngineDataError('DATA_INTEGRITY', `${name}: the bar of ${dates[i]} has no ${ohlc ? 'open, high, low and close' : 'close'}.`, name);
  }
}

export function prepare(data: MarketData): Context {
  if (!data || !data.ihsg) throw new EngineDataError('DATA_MISSING', 'The IHSG price series is missing.', 'IHSG');
  checkSeries(data.ihsg, data.ihsg.ticker || 'IHSG', false);
  return { data, tickers: new Map(), calendars: new Map() };
}

function prepared(ctx: Context, ticker: string, field: string): Prepared {
  let p = ctx.tickers.get(ticker);
  if (p) return p;
  const d = ctx.data.tickers[ticker];
  if (!d || !d.prices) throw new EngineDataError('DATA_MISSING', `No price data was loaded for ${ticker}.`, field);
  checkSeries(d.prices, ticker, true);
  const b = d.prices.bars;
  // conditions.ts Calc takes the ticker's flow data as its second argument (flow conditions, kind 'flow')
  const calc = new Calc(b, d.flow);
  p = { ticker, data: d, calc, O: b.O as number[], H: b.H as number[], L: b.L as number[], C: b.C as number[], scores: {}, liq: null, maps: new Map() };
  ctx.tickers.set(ticker, p);
  return p;
}

/* ---- price lines a stop or a trailing stop can sit on (the page's LEVEL_LINES) ----------------------------- */
/* The page offers the outputs of the indicators drawn on the price (indRegistry zone 'overlay'), without their
   'direction' output (a +1/-1 state, not a price). Derived from the registries, not listed by hand. */
const OVERLAY = new Set((display as unknown as { id: string; zone: string }[]).filter(r => r.zone === 'overlay').map(r => r.id));
export const LEVEL_LINES: { indicator: string; output: string }[] = REGISTRY.indicators
  .filter(r => OVERLAY.has(r.id) && r.available_for_backtest)
  .flatMap(r => r.outputs.filter(o => o !== 'direction').map(output => ({ indicator: r.id, output })));

export interface Line { key: string; params: Params; output: string }
/** A price line as the page sends it (contract.ts LineRef): a registry overlay indicator, one of its outputs other
    than direction, its parameters as the registry takes them. The worker's validate.ts holds the line of a stop or
    trailing mode that is not chosen to it too. */
export function lineOf(ref: unknown, field: string): Line {
  if (!ref || typeof ref !== 'object' || Array.isArray(ref)) throw new ValidationError('INVALID_EXIT', field, `${field} must name an indicator line.`);
  const { indicator: id, output, params } = ref as { indicator?: unknown; output?: unknown; params?: unknown };
  const r = indicator(id, `${field}.indicator`);
  if (!OVERLAY.has(r.id)) throw new ValidationError('INVALID_LINE', `${field}.indicator`, `${field}.indicator: ${r.id} is not drawn on the price, so it is not a price line.`);
  const allowed = r.outputs.filter(o => o !== 'direction');
  if (typeof output !== 'string' || !allowed.includes(output)) throw new ValidationError('UNKNOWN_OUTPUT', `${field}.output`, `${field}.output must be one of ${allowed.join(', ')}.`);
  return { key: r.key, params: resolveParams(r, params, `${field}.params`), output };
}

/* ---- request checks (CONTRACT section 3) for everything the engine reads ----------------------------------- */
const fail = (code: string, field: string, message: string): never => { throw new ValidationError(code, field, message) };
const object = (v: unknown, code: string, field: string) => { if (!v || typeof v !== 'object' || Array.isArray(v)) fail(code, field, `${field} is required.`) };
const oneOf = (v: unknown, options: readonly string[], code: string, field: string) => { if (typeof v !== 'string' || !options.includes(v)) fail(code, field, `${field} must be one of ${options.join(', ')}.`) };
const finite = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
const positive = (v: unknown, code: string, field: string) => { if (!finite(v) || !(v > 0)) fail(code, field, `${field} must be a number above 0.`) };
const whole = (v: unknown, min: number, max: number, code: string, field: string) => {
  if (!finite(v) || !Number.isInteger(v) || v < min || v > max) fail(code, field, `${field} must be a whole number${max < Infinity ? ` from ${min} to ${max}` : ` of at least ${min}`}.`);
};
const within = (v: unknown, lo: number, loOpen: boolean, hi: number, hiOpen: boolean, code: string, field: string) => {
  if (!finite(v) || (loOpen ? !(v > lo) : !(v >= lo)) || (hiOpen ? !(v < hi) : !(v <= hi)))
    fail(code, field, `${field} must be in ${loOpen ? '(' : '['}${lo}, ${hi}${hiOpen ? ')' : ']'}.`);
};
/** I30 ATR with RMA smoothing (CONTRACT section 6), its length checked against the registry. */
function atrParams(length: unknown, field: string): Params {
  try { return resolveParams(BY_ID.I30, { length, smoothing_type: 'RMA' }, 'atr') }
  catch (e) { if (e instanceof ValidationError) throw new ValidationError(e.code, field, e.message.replace(/^atr\.length/, field)); throw e }
}
export const MAX_POSITIONS = 10;          // the page's Max positions input (min 1, max 10), catalog limits.max_positions
export const ADJUSTED_HISTORY_BOUNDARY = '2026-09-12';
const STOP_MODES = ['pct', 'atr', 'rr', 'line', 'none'], TP_MODES = ['pct', 'r', 'atr', 'none'], TRAIL_MODES = ['none', 'pct', 'chandelier', 'line'];

/** The exit settings resolved against the registry: I30 parameters for the ATR stop/target and the chandelier, and
    the price lines of a line stop or a line trailing stop. */
export interface ExitPlan { atr: Params | null; chandelier: Params | null; stopLine: Line | null; trailLine: Line | null }

/** Refuses a request the engine cannot run as the page means it (nothing is clamped or rounded). The conditions
    themselves are checked when they are evaluated on the first ticker (conditions.ts). */
export function validateRun(req: BacktestRequest, ihsgThrough?: string): ExitPlan {
  object(req, 'INVALID_REQUEST', 'request');
  oneOf(req.mode, ['single', 'portfolio'], 'INVALID_MODE', 'mode');
  if (req.mode === 'single') {
    object(req.single, 'INVALID_SINGLE', 'single');
    if (typeof req.single!.ticker !== 'string' || !req.single!.ticker) fail('INVALID_SINGLE', 'single.ticker', 'single.ticker is required.');
    oneOf(req.single!.benchmark, ['buy_and_hold', 'ihsg'], 'INVALID_SINGLE', 'single.benchmark');
  } else {
    object(req.portfolio, 'INVALID_PORTFOLIO', 'portfolio');
    const p = req.portfolio!;
    if (typeof p.universe !== 'string' || !p.universe) fail('INVALID_PORTFOLIO', 'portfolio.universe', 'portfolio.universe is required.');
    whole(p.max_positions, 1, MAX_POSITIONS, 'INVALID_PORTFOLIO', 'portfolio.max_positions');
    oneOf(p.rank_by, RANK_BY, 'INVALID_PORTFOLIO', 'portfolio.rank_by');
    if (!finite(p.min_avg_value_20d_idr) || p.min_avg_value_20d_idr < 0) fail('INVALID_PORTFOLIO', 'portfolio.min_avg_value_20d_idr', 'portfolio.min_avg_value_20d_idr must be a number of at least 0.');
  }
  object(req.period, 'INVALID_PERIOD', 'period');
  if (!isIsoDate(req.period.from)) fail('INVALID_PERIOD', 'period.from', 'period.from must be a date YYYY-MM-DD.');
  if (!isIsoDate(req.period.to)) fail('INVALID_PERIOD', 'period.to', 'period.to must be a date YYYY-MM-DD.');
  if (req.period.from > req.period.to) fail('INVALID_PERIOD', 'period.to', 'period.to must not be before period.from.');
  if (ihsgThrough !== undefined && req.period.to > ihsgThrough) fail('PERIOD_AFTER_DATA', 'period.to', `period.to is after the latest published bar (${ihsgThrough}).`);

  object(req.sizing, 'INVALID_SIZING', 'sizing');
  if (!finite(req.sizing.capital_idr) || req.sizing.capital_idr < 1) fail('INVALID_SIZING', 'sizing.capital_idr', 'sizing.capital_idr must be a number of at least 1.');
  if (req.mode === 'single') within(req.sizing.allocation_fraction, 0, true, 1, false, 'INVALID_SIZING', 'sizing.allocation_fraction');
  object(req.costs, 'INVALID_COSTS', 'costs');
  for (const k of ['buy_fee', 'sell_fee', 'slippage'] as const) within(req.costs[k], 0, false, 0.1, true, 'INVALID_COSTS', `costs.${k}`);
  if (typeof req.costs.skip_ara_open_gap !== 'boolean') fail('INVALID_COSTS', 'costs.skip_ara_open_gap', 'costs.skip_ara_open_gap must be true or false.');
  within(req.costs.ara_gap_fraction, 0, true, 1, true, 'INVALID_COSTS', 'costs.ara_gap_fraction');

  const X = req.exit;
  object(X, 'INVALID_EXIT', 'exit');
  object(X.stop, 'INVALID_EXIT', 'exit.stop'); object(X.take_profit, 'INVALID_EXIT', 'exit.take_profit'); object(X.trailing, 'INVALID_EXIT', 'exit.trailing');
  oneOf(X.stop.mode, STOP_MODES, 'INVALID_EXIT', 'exit.stop.mode');
  oneOf(X.take_profit.mode, TP_MODES, 'INVALID_EXIT', 'exit.take_profit.mode');
  oneOf(X.trailing.mode, TRAIL_MODES, 'INVALID_EXIT', 'exit.trailing.mode');
  // an R target is measured from a stop; an R:R stop is placed from a target (CONTRACT section 3)
  if (X.take_profit.mode === 'r' && !['pct', 'atr', 'line'].includes(X.stop.mode))
    fail('INVALID_EXIT', 'exit.take_profit.mode', 'An R-multiple target needs a stop in percent, ATR or on a line.');
  if (X.stop.mode === 'rr' && !['pct', 'atr'].includes(X.take_profit.mode))
    fail('INVALID_EXIT', 'exit.stop.mode', 'A reward:risk stop needs a take-profit in percent or ATR.');
  const plan: ExitPlan = { atr: null, chandelier: null, stopLine: null, trailLine: null };
  if (X.stop.mode === 'pct') positive(X.stop.pct, 'INVALID_EXIT', 'exit.stop.pct');
  if (X.stop.mode === 'atr') positive(X.stop.atr_mult, 'INVALID_EXIT', 'exit.stop.atr_mult');
  if (X.stop.mode === 'rr') positive(X.stop.reward_risk_x, 'INVALID_EXIT', 'exit.stop.reward_risk_x');
  if (X.stop.mode === 'line') plan.stopLine = lineOf(X.stop.line, 'exit.stop.line');
  if (X.take_profit.mode === 'pct') positive(X.take_profit.pct, 'INVALID_EXIT', 'exit.take_profit.pct');
  if (X.take_profit.mode === 'r') positive(X.take_profit.r_multiple, 'INVALID_EXIT', 'exit.take_profit.r_multiple');
  if (X.take_profit.mode === 'atr') positive(X.take_profit.atr_mult, 'INVALID_EXIT', 'exit.take_profit.atr_mult');
  if (X.stop.mode === 'atr' || X.take_profit.mode === 'atr') plan.atr = atrParams(X.atr_length, 'exit.atr_length');
  if (X.trailing.mode === 'pct') positive(X.trailing.pct, 'INVALID_EXIT', 'exit.trailing.pct');
  if (X.trailing.mode === 'chandelier') {
    plan.chandelier = atrParams(X.trailing.chandelier_length, 'exit.trailing.chandelier_length');
    positive(X.trailing.chandelier_mult, 'INVALID_EXIT', 'exit.trailing.chandelier_mult');
  }
  if (X.trailing.mode === 'line') plan.trailLine = lineOf(X.trailing.line, 'exit.trailing.line');
  whole(X.max_hold_bars, 0, Infinity, 'INVALID_EXIT', 'exit.max_hold_bars');
  return plan;
}

/* ---- the run ------------------------------------------------------------------------------------------- */

interface Run {
  p: Prepared; m: BarMap; sig: TickerSignals | null;
  events: number[];                        // ticker bars of the entry events inside the period
  atr: Num[] | null; chandelier: Num[] | null; stopLine: Num[] | null; trailLine: Num[] | null;
  score: Num[] | null; liq: Num[] | null;
}
interface Order { r: Run; j: number; ev: number }          // entry event ev on bar j, buy at the open of bar j + 1
interface Position {
  r: Run; j: number; ev: number;
  eb: number; ek: number;                  // entry bar (ticker) and entry day (calendar)
  fill: number; shares: number; cost: number;
  peak: number; stop: number; target: number; trail: number; risk: number | null;
  pending: boolean; mae: number; mfe: number; stale: boolean; both: boolean; ids: string[];
}
const PHASE: Record<ExitPhase, number> = { open: 0, intraday: 1, close: 2 };
const byTicker = (a: string, b: string) => a < b ? -1 : a > b ? 1 : 0;

export function run(ctx: Context, req: BacktestRequest, hooks: Hooks = {}): Ledger {
  const ihsg = ctx.data.ihsg;
  const plan = validateRun(req, ihsg.dates[ihsg.dates.length - 1]);
  const active = requestConditions(req);
  const single = req.mode === 'single';
  const universe = single ? [req.single!.ticker] : Object.keys(ctx.data.tickers).sort(byTicker);
  const tickerField = single ? 'single.ticker' : 'portfolio.universe';
  const prep = universe.map(t => prepared(ctx, t, tickerField));
  const warnings: Ledger['warnings'] = [];
  const to = req.period.to;
  let from = req.period.from;
  // single mode: the ticker has no bar, and a buy-and-hold benchmark no value, before its first published bar, so a
  // period that starts earlier starts there (PERIOD_CLIPPED, lead decision 2026-10-26); a portfolio keeps its period
  const listed = single ? prep[0].data.prices.dates[0] : undefined;
  if (listed !== undefined && listed > from && listed <= to) {
    warnings.push({ code: 'PERIOD_CLIPPED', message: `${prep[0].ticker} has no published bar before ${listed}: the backtest starts on ${listed} instead of the requested ${from}.` });
    from = listed;
  }

  let done = 0, total = prep.length;                                           // tickers, then calendar days
  const tick = (force = false) => {
    if (hooks.shouldStop && hooks.shouldStop()) throw new Cancelled();
    if (hooks.progress && (force || done % 256 === 0)) hooks.progress(done, total);
  };

  /* ---- signals per ticker, on its own bars (full history; events inside the period) ---- */
  const X = req.exit, rankBy = single ? null : req.portfolio!.rank_by;
  const excluded: Exclusion[] = single ? [] : [...(ctx.data.excluded ?? [])];
  const signalled: Omit<Run, 'm'>[] = [];
  for (const p of prep) {
    tick();
    const signals = (): Omit<Run, 'm'> => {
      // a ticker without a bar inside the period cannot trade and has no event there; whether its conditions have any
      // value is decided on its bars up to period.to: bars after the period never leave it out, and in a portfolio a
      // condition without one is false unless the entry cannot switch on without it (signals.ts periodSignals)
      const { sig, events } = periodSignals(p.calc, p.data.prices.dates, req, active, from, to, !single);
      const r: Omit<Run, 'm'> = { p, sig, events, atr: null, chandelier: null, stopLine: null, trailLine: null, score: null, liq: null };
      if (sig && events.length) {
        const c = p.calc;
        if (plan.atr) r.atr = c.out(BY_ID.I30.key, plan.atr).atr;
        if (plan.chandelier) r.chandelier = c.out(BY_ID.I30.key, plan.chandelier).atr;
        if (plan.stopLine) r.stopLine = c.out(plan.stopLine.key, plan.stopLine.params)[plan.stopLine.output];
        if (plan.trailLine) r.trailLine = c.out(plan.trailLine.key, plan.trailLine.params)[plan.trailLine.output];
        if (rankBy) {
          r.score = p.scores[rankBy] ||= rankScores(c, rankBy, p.data.flow);
          r.liq = p.liq ||= liquidity(c);
        }
      }
      return r;
    };
    // portfolio: a ticker whose own data cannot serve the strategy is left out of this run, never the run itself
    const r = single ? signals() : unlessLeftOut(p.ticker, excluded, signals);
    if (r) signalled.push(r);
    done++;
  }
  const left = single ? null : leftOut(excluded, signalled.length, 'portfolio.universe', 'run');   // UNIVERSE_EMPTY when none is left
  if (left) warnings.push(left);

  /* ---- the result calendar (IHSG and the run tickers inside the period) and the primary benchmark ---- */
  const calKey = `${from}|${to}|${signalled.map(r => r.p.ticker).join(',')}`;
  let dates = ctx.calendars.get(calKey);
  if (!dates) { dates = resultCalendar(from, to, [ihsg.dates, ...signalled.map(r => r.p.data.prices.dates)]); ctx.calendars.set(calKey, dates) }
  const nCal = dates.length, lastDay = nCal - 1;
  if (!nCal) fail('PERIOD_EMPTY', 'period.from', 'The period contains no trading day.');
  total = prep.length + nCal;
  // result.ts scales the benchmark by its close on the first day: it must have one (the shared as-of rule)
  const bench = single && req.single!.benchmark === 'buy_and_hold' ? prep[0].data.prices : ihsg;
  const bm = barMap(bench.dates, dates);
  if (bm.asof[0] < 0) fail('PERIOD_BEFORE_DATA', 'period.from', `The benchmark ${bench.ticker} has no published close on or before ${dates[0]}${bench.dates.length
    ? ` (its first bar is ${bench.dates[0]}); start the period on or after ${bench.dates[0]}` : ' (it has no published bar)'}.`);

  /* ---- the events on the calendar: tracks, orders for the next calendar day, skipped signals ---- */
  const conditions: Ledger['events']['conditions'] = [], entries: Record<string, SignalTrack> = {}, exits: Record<string, SignalTrack> = {};
  const skipped: SkippedSignal[] = [], perTicker: Ledger['per_ticker_signals'] = [];
  const orders: Order[][] = Array.from({ length: nCal }, () => []);
  // DATA_GAP: the distinct (ticker, calendar day) pairs without a bar of a held or signalled ticker; a day can be both
  // (an event before it while the ticker is held), and it counts once
  const gaps = new Set<string>(), gapTickers = new Set<string>();
  const gap = (t: string, k: number) => { gaps.add(`${t}|${k}`); gapTickers.add(t) };
  const skip = (r: Run, j: number, ev: number, reason: SkippedSignal['reason']) =>
    skipped.push({ ticker: r.p.ticker, signal_date: dates![r.m.bar[j]], signal_event: ev, reason });
  for (const s of signalled) {
    let m = s.p.maps.get(calKey);
    if (!m) { m = barMap(s.p.data.prices.dates, dates); s.p.maps.set(calKey, m) }
    const r: Run = { ...s, m }, t = s.p.ticker, sig = s.sig;
    for (const [list, key] of [[active.entry, 'entryConditions'], [active.exit, 'exitConditions']] as const)
      list.forEach((a, k) => conditions.push({ condition_id: a.id, ticker: t, track: sig ? track(sig[key][k].s, m!) : emptyTrack() }));
    entries[t] = sig ? { on: r.events.map(j => m!.bar[j]), runs: track(sig.entry, m).runs } : emptyTrack();
    exits[t] = sig ? track(sig.exit, m) : emptyTrack();
    perTicker.push({ ticker: t, ...signalSummary(entries[t], dates) });
    // every event inside the period becomes an order for the next calendar day, or a skipped signal
    r.events.forEach((j, ev) => {
      const kj = m!.bar[j];
      if (kj === lastDay) skip(r, j, ev, 'period_end');                        // the next day is after the period
      else if (m!.cal[kj + 1] !== j + 1) { skip(r, j, ev, 'no_next_bar'); gap(t, kj + 1) }   // no stale fills
      else orders[kj + 1].push({ r, j, ev });
    });
  }

  /* ---- the event clock ---- */
  const fb = req.costs.buy_fee, fs = req.costs.sell_fee, slip = req.costs.slippage;
  const maxPos = single ? 1 : req.portfolio!.max_positions, minValue = single ? 0 : req.portfolio!.min_avg_value_20d_idr;
  let cash = req.sizing.capital_idr;
  let held: Position[] = [];                                                    // ticker order
  const trades: LedgerTrade[] = [];
  const equity: number[] = new Array(nCal), exposure: number[] = new Array(nCal);

  const levels = (r: Run, fill: number, s: number) => {                         // page exitLevels, signal bar s
    let stop = -1, risk: number | null = null, target = Infinity;
    const a = r.atr ? r.atr[s] : null;
    if (X.stop.mode === 'pct') stop = fill * (1 - X.stop.pct);
    else if (X.stop.mode === 'atr') { if (isN(a)) stop = fill - X.stop.atr_mult * a }
    else if (X.stop.mode === 'line') { const l = r.stopLine![s]; if (isN(l) && l < fill) stop = l }
    if (X.take_profit.mode === 'pct') target = fill * (1 + X.take_profit.pct);
    else if (X.take_profit.mode === 'atr') { if (isN(a)) target = fill + X.take_profit.atr_mult * a }
    if (X.stop.mode === 'rr' && target < Infinity) stop = fill - (target - fill) / X.stop.reward_risk_x;   // reward : risk = 1 : x
    if (stop > 0) risk = fill - stop;
    if (X.take_profit.mode === 'r' && risk) target = fill + X.take_profit.r_multiple * risk;
    return { stop, target, risk };
  };
  const trailLevel = (q: Position, i: number) => {                             // page trailLevel: bars up to i - 1 only, ratchets up
    const { H, C } = q.r.p;
    let t = -1;
    if (X.trailing.mode === 'pct') t = q.peak * (1 - X.trailing.pct);
    else if (X.trailing.mode === 'chandelier') {
      const a = q.r.chandelier![i - 1];
      let hh = -1;
      for (let j = Math.max(q.eb, i - X.trailing.chandelier_length); j < i; j++) hh = Math.max(hh, H[j]);
      if (isN(a)) t = hh - X.trailing.chandelier_mult * a;
    } else if (X.trailing.mode === 'line') { const l = q.r.trailLine![i - 1]; if (isN(l)) t = l }
    if (!(t < C[i - 1])) t = -1;                                                // above the last close: not a stop yet
    return Math.max(q.trail, t);
  };
  const sell = (q: Position, px: number, reason: ExitReason, phase: ExitPhase, k: number, i: number) => {
    const fill = px * (1 - slip), proceeds = fill * q.shares * (1 - fs), pnl = proceeds - q.cost;
    cash += proceeds;
    const t = q.r.p.ticker, entryDate = dates![q.ek], exitDate = dates![k];
    trades.push({
      ticker: t, signal_bar: q.r.m.bar[q.j], signal_event: q.ev,
      entry_bar: q.ek, entry_price: q.fill, exit_bar: k, exit_price: fill, exit_reason: reason, exit_phase: phase,
      shares: q.shares, bars_held: i - q.eb + 1,
      cost_idr: q.cost, proceeds_idr: proceeds, pnl_idr: pnl, return: pnl / q.cost, mae: q.mae, mfe: q.mfe,
      initial_stop: q.stop > 0 ? q.stop : null, initial_target: q.target < Infinity ? q.target : null,
      initial_risk_pct: q.risk ? q.risk / q.fill : null, entry_condition_ids: q.ids,
      flags: {
        corporate_actions: q.r.p.data.corporate_actions.filter(c => c.date > entryDate && c.date <= exitDate).map(c => ({ date: c.date, type: c.type })),
        stop_and_target_same_bar: q.both, stale_mark: q.stale,
      },
    });
    held = held.filter(x => x !== q);
  };
  const mark = (q: Position, k: number) => { const i = q.r.m.cal[k]; return i >= 0 ? q.r.p.C[i] : q.r.p.C[q.r.m.asof[k]] };

  for (let k = 0; k < nCal; k++) {
    tick();
    // before the open: trailing levels from data up to the previous close
    for (const q of held) { const i = q.r.m.cal[k]; if (i > q.eb) q.trail = trailLevel(q, i) }
    // 1. open: gaps through the stop or the target, then pending exit signals (ticker order)
    for (const q of [...held]) {
      const i = q.r.m.cal[k];
      if (i < 0) continue;
      const o = q.r.p.O[i], lvl = Math.max(q.stop, q.trail);
      let reason: ExitReason | null = null;
      if (lvl > 0 && o <= lvl) reason = lvl === q.stop ? 'stop_loss' : 'trailing_stop';
      else if (o >= q.target) reason = 'take_profit';
      else if (q.pending) reason = 'exit_signal';
      if (reason) {
        // sold before the day's range: the open is the only price the position saw today (D-E5 MAE)
        q.mae = Math.min(q.mae, o / q.fill - 1); q.mfe = Math.max(q.mfe, o / q.fill - 1);
        sell(q, o, reason, 'open', k, i);
      }
    }
    //    entries: events of the previous bar; the open's proceeds are already cash (same auction)
    const cands: Order[] = [];
    for (const od of orders[k]) {
      const { r, j, ev } = od;
      if (held.some(q => q.r === r)) skip(r, j, ev, 'already_held');
      else if (k === lastDay) skip(r, j, ev, 'period_end');                    // it would close at the same close
      else if (!single && minValue > 0 && !(isN(r.liq![j]) && (r.liq![j] as number) >= minValue)) skip(r, j, ev, 'below_min_value');
      else cands.push(od);
    }
    if (!single) cands.sort((a, b) => {                                         // highest score first, no score last, then ticker
      const x = a.r.score![a.j], y = b.r.score![b.j];
      if (isN(x) && isN(y) && x !== y) return y - x;
      if (isN(x) !== isN(y)) return isN(x) ? -1 : 1;
      return byTicker(a.r.p.ticker, b.r.p.ticker);
    });
    const slots = maxPos - held.length;
    let filled = 0;
    for (const { r, j, ev } of cands) {
      if (filled >= slots) { skip(r, j, ev, 'no_slot'); continue }
      const i = j + 1, o = r.p.O[i];
      if (req.costs.skip_ara_open_gap && o >= r.p.C[j] * (1 + req.costs.ara_gap_fraction)) { skip(r, j, ev, 'ara_open_gap'); continue }
      let mv = 0;
      for (const q of held) { const qi = q.r.m.cal[k]; mv += q.shares * (qi >= 0 ? q.r.p.O[qi] : q.r.p.C[q.r.m.asof[k]]) }
      const equityNow = cash + mv;
      const budget = single ? Math.min(cash, equityNow * req.sizing.allocation_fraction) : Math.min(cash, equityNow / maxPos);
      const fill = o * (1 + slip);
      let shares = Math.floor(budget / (fill * (1 + fb)) / 100) * 100;
      // the formula's meaning in exact arithmetic: the cost never exceeds the budget (no leverage); the rounded division
      // can give one lot whose cost, as computed below, is an ulp above it
      while (shares >= 100 && fill * shares * (1 + fb) > budget) shares -= 100;
      if (shares < 100) { skip(r, j, ev, 'insufficient_cash'); continue }
      const cost = fill * shares * (1 + fb);
      cash -= cost;
      const lv = levels(r, fill, j);
      const q: Position = {
        r, j, ev, eb: i, ek: k, fill, shares, cost, peak: fill, stop: lv.stop, target: lv.target, trail: -1, risk: lv.risk,
        pending: false, mae: 0, mfe: 0, stale: false, both: false, ids: conditionsWithin(r.sig!, j),
      };
      held = [...held, q].sort((a, b) => byTicker(a.r.p.ticker, b.r.p.ticker));
      filled++;
    }
    // 2. intraday: stops and targets on the day's range, the positions bought this open included (D-E3)
    for (const q of [...held]) {
      const i = q.r.m.cal[k];
      if (i < 0) continue;
      const { O, H, L } = q.r.p, lvl = Math.max(q.stop, q.trail);
      q.mae = Math.min(q.mae, L[i] / q.fill - 1); q.mfe = Math.max(q.mfe, H[i] / q.fill - 1);
      if (lvl > 0 && L[i] <= lvl) {
        q.both = H[i] >= q.target;                                              // both in one candle: the stop (D-E4)
        sell(q, Math.min(O[i], lvl), lvl === q.stop ? 'stop_loss' : 'trailing_stop', 'intraday', k, i);
      } else if (H[i] >= q.target) sell(q, Math.max(O[i], q.target), 'take_profit', 'intraday', k, i);
    }
    // 3. close: time exit, new exit signals (sold at the next bar's open), the end of the test
    for (const q of [...held]) {
      const i = q.r.m.cal[k];
      if (i >= 0) {
        if (X.max_hold_bars > 0 && i - q.eb + 1 >= X.max_hold_bars) { sell(q, q.r.p.C[i], 'time_exit', 'close', k, i); continue }
        if (q.r.sig!.exit[i] && i > q.eb) q.pending = true;
      }
      if (k === lastDay) {
        if (i < 0) { q.stale = true; gap(q.r.p.ticker, k) }                  // sold at its last close from an earlier day
        sell(q, mark(q, k), 'end_of_test', 'close', k, i >= 0 ? i : q.r.m.asof[k]);
      } else if (i >= 0) q.peak = Math.max(q.peak, q.r.p.C[i]);
    }
    // 4. marks: a ticker without a bar today is marked at its last close
    let mv = 0;
    for (const q of held) {
      if (q.r.m.cal[k] < 0) { q.stale = true; gap(q.r.p.ticker, k) }
      mv += q.shares * mark(q, k);
    }
    equity[k] = cash + mv; exposure[k] = mv / equity[k];
    done++;
  }
  tick(true);

  trades.sort((a, b) => a.exit_bar - b.exit_bar || PHASE[a.exit_phase] - PHASE[b.exit_phase] || byTicker(a.ticker, b.ticker));
  skipped.sort((a, b) => byTicker(a.signal_date, b.signal_date) || byTicker(a.ticker, b.ticker));

  /* ---- benchmark and warnings ---- */
  const benchmark_close = Array.from(bm.asof, j => bench.bars.C[j] as number);   // asof[0] >= 0 (checked above), and it only rises
  if (gaps.size) {
    const count = gaps.size;
    warnings.push({ code: 'DATA_GAP', count, tickers: [...gapTickers].sort(byTicker),
      message: `${count} calendar day(s) without a bar for a held or signalled ticker: held positions were marked at their last close (flags.stale_mark) and entry signals before such a day were skipped (no_next_bar).` });
  }
  if (from < ADJUSTED_HISTORY_BOUNDARY && to >= ADJUSTED_HISTORY_BOUNDARY)
    warnings.push({ code: 'ADJUSTED_HISTORY_BOUNDARY', message: `The period crosses ${ADJUSTED_HISTORY_BOUNDARY}: published prices before it are back-adjusted for splits, bonus shares and rights issues, prices after it are raw. Trades holding through a corporate action carry flags.corporate_actions.` });
  warnings.push({ code: 'ARB_NOT_MODELLED', message: 'Auto-rejection limits are not modelled: a stop fills at the lower of the open and the stop level, with no lower-limit lock; entries are only skipped when the open gaps up by the ARA gap fraction or more (when that option is on).' });
  warnings.push({ code: 'TICK_NOT_MODELLED', message: 'Fills are not rounded to the IDX tick size.' });
  if (!single) warnings.push({ code: 'SURVIVORSHIP', message: 'The universe is today\'s list of published tickers: stocks delisted before today are missing, which can flatter past results.' });

  return {
    dates: dates.slice(), equity, exposure, benchmark_close,
    benchmark: { kind: single ? req.single!.benchmark : 'ihsg', ticker: bench === ihsg ? ihsg.ticker : prep[0].ticker },
    trades, events: { conditions, entries, exits, skipped }, per_ticker_signals: perTicker, warnings,
  };
}
