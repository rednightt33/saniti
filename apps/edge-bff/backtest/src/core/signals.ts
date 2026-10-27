/* Signals of a backtest request on one ticker's own bars, and their place on the result calendar (CONTRACT.md
   sections 4-6). One module for the engine (worker) and the page's preview, so a marker the page draws before a run
   and the event a trade executes after it come from the same code:
   - the enabled entry and exit conditions as conditions.ts computes them (page semantics, registry formulas);
   - the combined entry state (combineEntry) and its entry events: bars where it switches from false to true on the
     ticker's own bars (D-E1); the combined exit-signal state (combineExit);
   - per event, the entry conditions true within the window (a trade's entry_condition_ids);
   - the portfolio ranking scores and the liquidity value on a signal bar (section 6, D-E5 ranking, D-K9);
   - the result calendar (section 4, D-K5c), the ticker-bar <-> calendar index maps, and the SignalTracks;
   - a portfolio's picked stocks whose own data cannot serve the strategy: left out of the run and of the preview
     alike, listed in the same TICKERS_EXCLUDED warning, and UNIVERSE_EMPTY when none is left (lead decisions
     2026-10-26), so a preview never fails where the matching run succeeds.
   Pure module: no DOM and no Node API. */
import type { BacktestRequest, Condition, SignalTrack, Warning } from './contract.ts';
import type { FlowData } from './flow.ts';
import type { Num } from '../../../terminal/src/calc/indicators.ts';
import { isN, sma } from '../../../terminal/src/calc/indicators.ts';
import { combineEntry, combineExit, conditionSeries, entryNeed, switchOns } from './conditions.ts';
import type { Calc, Signal } from './conditions.ts';
import { BY_ID, ValidationError, resolveParams } from './registry.ts';

/* ---- the conditions a request evaluates ------------------------------------------------------------------ */

/** An enabled condition with the field path its errors name (entry.conditions[2], exit.signals.conditions[0]). */
export interface ActiveCondition { id: string; field: string; cond: Condition }

/** The enabled conditions of one list. The list and each condition's id and enabled flag are checked here; the
    condition itself is checked by conditions.ts when it is evaluated. A disabled condition is kept by the page but not
    evaluated, so it is not checked further. */
export function activeConditions(list: unknown, field: string): ActiveCondition[] {
  if (!Array.isArray(list)) throw new ValidationError('INVALID_CONDITION', field, `${field} must be a list.`);
  const out: ActiveCondition[] = [];
  list.forEach((c, k) => {
    const f = `${field}[${k}]`;
    if (!c || typeof c !== 'object' || Array.isArray(c)) throw new ValidationError('INVALID_CONDITION', f, `${f} must be an object.`);
    const { id, enabled } = c as { id?: unknown; enabled?: unknown };
    if (typeof id !== 'string' || !id) throw new ValidationError('INVALID_CONDITION', `${f}.id`, `${f}.id must be a non-empty string.`);
    if (enabled !== undefined && typeof enabled !== 'boolean') throw new ValidationError('INVALID_CONDITION', `${f}.enabled`, `${f}.enabled must be true or false.`);
    if (enabled !== false) out.push({ id, field: f, cond: c as Condition });
  });
  return out;
}

/** What signals read from a request: the entry rule, and the exit rule when there is one (a backtest always has it; the
    signals preview, SignalsPreviewRequest, has only the entry). */
export interface SignalRequest { entry: BacktestRequest['entry']; exit?: Pick<BacktestRequest['exit'], 'signals'> }

/** The entry and exit conditions a request evaluates. At least one enabled entry condition (NO_ACTIVE_CONDITION); ids
    unique across both lists, because events.conditions names a track by condition id and ticker only. The entry
    logic, window and at_least are checked once here (combineEntry refuses them), so a run with no bars to evaluate
    still refuses them. */
export function requestConditions(req: SignalRequest): { entry: ActiveCondition[]; exit: ActiveCondition[] } {
  if (!req.entry || typeof req.entry !== 'object') throw new ValidationError('INVALID_ENTRY', 'entry', 'entry is required.');
  if (req.exit !== undefined && (!req.exit || typeof req.exit !== 'object' || !req.exit.signals || typeof req.exit.signals !== 'object'))
    throw new ValidationError('INVALID_EXIT', 'exit.signals', 'exit.signals is required.');
  const entry = activeConditions(req.entry.conditions, 'entry.conditions');
  const exit = req.exit ? activeConditions(req.exit.signals.conditions, 'exit.signals.conditions') : [];
  if (!entry.length) throw new ValidationError('NO_ACTIVE_CONDITION', 'entry.conditions', 'At least one entry condition must be enabled.');
  combineEntry([], req.entry.logic, req.entry.at_least, req.entry.window_bars, 0);
  if (req.exit) combineExit([], req.exit.signals.logic, 0);
  const seen = new Map<string, string>();
  for (const [list, field] of [[req.entry.conditions, 'entry.conditions'], [req.exit ? req.exit.signals.conditions : [], 'exit.signals.conditions']] as const)
    (list as { id: string }[]).forEach(({ id }, k) => {
      const f = `${field}[${k}].id`;
      if (seen.has(id)) throw new ValidationError('DUPLICATE_CONDITION_ID', f, `${f}: ${JSON.stringify(id)} is already used by ${seen.get(id)}.`);
      seen.set(id, f);
    });
  return { entry, exit };
}

/* ---- one ticker ------------------------------------------------------------------------------------------- */

export interface TickerSignals {
  entryConditions: { id: string; s: Signal }[];        // enabled entry conditions, request order
  exitConditions: { id: string; s: Signal }[];         // enabled exit conditions, request order
  entry: Signal;                                       // combined entry state
  exit: Signal;                                        // combined exit-signal state (all 0 without exit conditions)
  window: number;                                      // entry.window_bars
}

/** Every enabled condition of the request on the ticker's bars (full history: warm-up uses real bars). `last`: the
    last bar the caller can see (the backtest: the ticker's last bar inside the period); whether a condition's series
    has any value at all is decided on the bars up to it (conditions.ts), so later bars never decide it.
    `portfolio` (a portfolio run and the signals preview): a condition whose series has no value on those bars (an
    error of EXCLUDED_CODES) is false on every bar, as a series is before its first value, and the ticker is left out
    (that error is thrown) only when its entry can then never switch on: fewer entry conditions with a value than the
    entry needs (conditions.ts entryNeed); an exit condition never leaves it out. A condition that has its first value
    on a later bar has none on the bars before it, where it is false all the same, so whether the ticker trades up to
    a day never depends on its bars after that day (no look-ahead). Without it (single mode) the error is thrown. */
export function tickerSignals(calc: Calc, req: SignalRequest, active = requestConditions(req), last?: number, portfolio = false): TickerSignals {
  const n = calc.n, empty: ValidationError[] = [];
  // conditions.ts names its own Condition union (page shapes); the wire conditions of contract.ts are the same objects
  const series = (list: ActiveCondition[], entry: boolean) => list.map(a => {
    try { return { id: a.id, s: conditionSeries(calc, a.cond as Parameters<typeof conditionSeries>[1], a.field, last) } }
    catch (e) {
      if (!portfolio || !(e instanceof ValidationError) || !EXCLUDED_CODES.includes(e.code)) throw e;
      if (entry) empty.push(e);
      return { id: a.id, s: new Uint8Array(n) };
    }
  });
  const entryConditions = series(active.entry, true), exitConditions = series(active.exit, false);
  if (empty.length && entryConditions.length - empty.length < entryNeed(req.entry.logic, req.entry.at_least, entryConditions.length)) throw empty[0];
  return {
    entryConditions, exitConditions,
    entry: combineEntry(entryConditions.map(x => x.s), req.entry.logic, req.entry.at_least, req.entry.window_bars, n),
    exit: req.exit ? combineExit(exitConditions.map(x => x.s), req.exit.signals.logic, n) : new Uint8Array(n),
    window: req.entry.window_bars,
  };
}

/** Entry events (switch-ons of the combined entry state) on the ticker's bars first..last. */
export const entryEvents = (sig: TickerSignals, first: number, last: number): number[] => switchOns(sig.entry, first, last);

/** The first index of an ascending date list at or after d, and the first one after d (the list's length when none). */
function lowerBound(a: readonly string[], d: string): number { let lo = 0, hi = a.length; while (lo < hi) { const mid = (lo + hi) >> 1; if (a[mid] < d) lo = mid + 1; else hi = mid } return lo }
function upperBound(a: readonly string[], d: string): number { let lo = 0, hi = a.length; while (lo < hi) { const mid = (lo + hi) >> 1; if (a[mid] <= d) lo = mid + 1; else hi = mid } return lo }

/** A ticker's signals for a period [from, to], as the backtest and the preview both read them: its bars inside the
    period (first..last; first > last: none), its signals (null without a bar inside the period: it cannot trade and
    has no event there) and its entry events inside the period. Whether a condition's series has any value is decided
    on its bars up to period.to (tickerSignals `last`), so bars after the period never decide it; in a portfolio
    (`portfolio`) a series without one leaves the ticker out only when its entry cannot switch on without it, so
    bars inside the period after a day never decide what it trades up to that day either (no look-ahead). */
export function periodSignals(calc: Calc, tickerDates: readonly string[], req: SignalRequest, active: ReturnType<typeof requestConditions>, from: string, to: string,
  portfolio = false): { first: number; last: number; sig: TickerSignals | null; events: number[] } {
  const first = lowerBound(tickerDates, from), last = upperBound(tickerDates, to) - 1;
  const sig = first <= last ? tickerSignals(calc, req, active, last, portfolio) : null;
  return { first, last, sig, events: sig ? entryEvents(sig, first, last) : [] };
}

/** The entry conditions true within the window on bar j (true on one of the bars j-W+1..j), the rule combineEntry
    counts: the conditions that made the entry event, in request order. */
export function conditionsWithin(sig: TickerSignals, j: number): string[] {
  const from = Math.max(0, j - sig.window + 1), ids: string[] = [];
  for (const c of sig.entryConditions) for (let t = j; t >= from; t--) if (c.s[t]) { ids.push(c.id); break }
  return ids;
}

/* ---- portfolio ranking and liquidity (CONTRACT section 6) -------------------------------------------------- */
export type RankBy = 'adx' | 'fnet' | 'vol' | 'rsi';
export const RANK_BY: RankBy[] = ['adx', 'fnet', 'vol', 'rsi'];
/* The page's rankScore: adx(D, 14), rollsum(fnet, 5), v / sma(v, 20) of the bar before, -rsi(c, 14); here on the
   registry indicators I07 (DI length 14, ADX smoothing 14), I35 (length 20) and I13 (length 14, close). */
const RANK = { adx: { di_length: 14, adx_smoothing: 14 }, fnet_bars: 5, vol: { length: 20 }, rsi: { length: 14 } };
/** The page's liquidity value: the 20-bar SMA of close x volume (avgVal = sma(val, 20), val = c x v; D-K9). */
export const LIQUIDITY_BARS = 20;

/** The ranking score of every bar, highest ranks first; null where the score has no value (warm-up, a missing input,
    a zero average volume). Ranking on the signal bar only reads that bar and earlier ones. */
export function rankScores(calc: Calc, rankBy: RankBy, flow?: FlowData): Num[] {
  const n = calc.n, out: Num[] = new Array(n).fill(null);
  if (rankBy === 'adx') {
    const a = calc.out(BY_ID.I07.key, resolveParams(BY_ID.I07, RANK.adx)).adx;
    for (let i = 0; i < n; i++) out[i] = isN(a[i]) ? a[i] : null;
  } else if (rankBy === 'rsi') {
    const r = calc.out(BY_ID.I13.key, resolveParams(BY_ID.I13, RANK.rsi)).rsi;
    for (let i = 0; i < n; i++) out[i] = isN(r[i]) ? -(r[i] as number) : null;            // lowest RSI first
  } else if (rankBy === 'vol') {
    const V = calc.bars.V, avg = calc.out(BY_ID.I35.key, resolveParams(BY_ID.I35, RANK.vol)).volume_sma;
    for (let i = 1; i < n; i++) { const v = V[i], a = avg[i - 1]; out[i] = isN(v) && isN(a) && a !== 0 ? v / a : null }
  } else {
    if (!flow) throw new ValidationError('FLOW_UNAVAILABLE', 'portfolio.rank_by', 'Ranking by foreign net flow needs the broker data, which is not available for this ticker.');
    const f = flow.fnet, k = RANK.fnet_bars;
    for (let i = k - 1; i < n; i++) {
      let s = 0, ok = true;
      for (let t = i - k + 1; t <= i && ok; t++) { const v = f[t]; if (isN(v)) s += v; else ok = false }
      out[i] = ok ? s : null;
    }
  }
  return out;
}

/** SMA(20) of close x volume on every bar (the indicators module's sma: a missing value restarts the window). */
export function liquidity(calc: Calc): Num[] {
  const { C, V } = calc.bars;
  return sma(C.map((c, i) => isN(c) && isN(V[i]) ? c * (V[i] as number) : null), LIQUIDITY_BARS);
}

/* ---- calendar and tracks (CONTRACT section 4) -------------------------------------------------------------- */

const ISO = /^\d{4}-\d{2}-\d{2}$/;
/** A real date written 'YYYY-MM-DD' (the wire's date format). */
export const isIsoDate = (s: unknown): s is string => {
  if (typeof s !== 'string' || !ISO.test(s)) return false;
  const t = Date.parse(`${s}T00:00:00Z`);
  return Number.isFinite(t) && new Date(t).toISOString().slice(0, 10) === s;      // 2024-02-30 is not a date
};

/** The result calendar: the sorted union of the given bar dates inside [from, to] (IHSG and every ticker whose bars
    the run read, PF8). */
export function resultCalendar(from: string, to: string, lists: ReadonlyArray<readonly string[]>): string[] {
  const days = new Set<string>();
  for (const l of lists) for (const d of l) if (d >= from && d <= to) days.add(d);
  return [...days].sort();
}

/** A ticker's bars on the result calendar. */
export interface BarMap {
  cal: Int32Array;                                     // calendar index -> the ticker's bar that day, or -1
  asof: Int32Array;                                    // calendar index -> the ticker's last bar on or before that day, or -1
  bar: Int32Array;                                     // ticker bar -> calendar index, or -1 outside the period
  first: number; last: number;                         // the ticker's first and last bar inside the period (first > last: none)
}
export function barMap(tickerDates: readonly string[], dates: readonly string[]): BarMap {
  const nb = tickerDates.length, nc = dates.length;
  const cal = new Int32Array(nc).fill(-1), asof = new Int32Array(nc).fill(-1), bar = new Int32Array(nb).fill(-1);
  let j = 0, first = -1, last = -2;
  for (let k = 0; k < nc; k++) {
    while (j < nb && tickerDates[j] < dates[k]) j++;
    if (j < nb && tickerDates[j] === dates[k]) { cal[k] = j; bar[j] = k; if (first < 0) first = j; last = j; asof[k] = j }
    else asof[k] = j - 1;
  }
  if (first < 0) first = nb;
  return { cal, asof, bar, first, last };
}

/** A 0/1 series of the ticker's bars as a track on the result calendar: the switch-ons inside the period (false on the
    ticker's previous bar, which may lie before the period) and the true runs of consecutive ticker bars, clipped to the
    period. A run spans calendar days without a bar of the ticker: its state holds until its next bar. */
export function track(s: Signal, m: BarMap): SignalTrack {
  const on: number[] = [], runs: number[] = [];
  for (const j of switchOns(s, m.first, m.last)) on.push(m.bar[j]);
  let start = -1;
  for (let j = m.first; j <= m.last; j++) {
    if (s[j]) { if (start < 0) start = j }
    else if (start >= 0) { runs.push(m.bar[start], m.bar[j - 1]); start = -1 }
  }
  if (start >= 0) runs.push(m.bar[start], m.bar[m.last]);
  return { on, runs };
}
export const emptyTrack = (): SignalTrack => ({ on: [], runs: [] });

/** The portfolio table's signal columns for one ticker: entry events inside the period and the last one's date. */
export function signalSummary(entry: SignalTrack, dates: readonly string[]): { entry_signals: number; last_signal: string | null } {
  return { entry_signals: entry.on.length, last_signal: entry.on.length ? dates[entry.on[entry.on.length - 1]] : null };
}

/** The signals preview row of one ticker (SignalsPreview, no backtest): entry events on its own bars inside
    [from, to] and the date of the last one, as the backtest counts them (periodSignals, the engine's own reading, as
    a portfolio run reads it: the preview's rows are a portfolio's). tickerDates = the bars' dates. An error of
    EXCLUDED_CODES is the run's too: the caller leaves the ticker out. */
export function previewRow(calc: Calc, tickerDates: readonly string[], req: SignalRequest, from: string, to: string, active = requestConditions(req)): { entry_signals: number; last_signal: string | null } {
  const on = periodSignals(calc, tickerDates, req, active, from, to, true).events;
  return { entry_signals: on.length, last_signal: on.length ? tickerDates[on[on.length - 1]] : null };
}

/* ---- a portfolio's picked stocks: the ones left out (lead decisions 2026-10-26) ----------------------------- */

/** The errors of one ticker's data that leave that ticker out of a portfolio run, and of the signals preview, instead
    of failing it (lead decision 2026-10-26): an indicator or flow series without any value on its bars, no broker data
    on its bars, when its entry cannot switch on without that condition (tickerSignals `portfolio`; otherwise the
    condition is false on every bar). A request error (a parameter, an indicator, a field) fails the run in either
    mode; in single mode these fail it too. The loader leaves out a ticker without published files the same way
    (DATA_MISSING). */
export const EXCLUDED_CODES: readonly string[] = ['INDICATOR_OUTPUT_EMPTY', 'FLOW_OUTPUT_EMPTY', 'FLOW_UNAVAILABLE'];
/** A picked stock of a portfolio that is left out, with the error its data gave (TICKERS_EXCLUDED reasons). */
export interface Exclusion { ticker: string; code: string; field?: string; message: string }

/** work() for one picked stock; null when it throws an error of EXCLUDED_CODES, which leaves the stock out
    (added to excluded). Any other error is thrown. */
export function unlessLeftOut<T>(ticker: string, excluded: Exclusion[], work: () => T): T | null {
  try { return work() }
  catch (e) {
    if (!(e instanceof ValidationError) || !EXCLUDED_CODES.includes(e.code)) throw e;
    excluded.push({ ticker, code: e.code, field: e.field, message: e.message });
    return null;
  }
}

/** Ticker order (UTF-16 code units, Array.prototype.sort's default): the order of a portfolio's stocks everywhere, the
    picked set's canonical order (hash.ts canonicalRequest, PF3) included. */
export const byTicker = (a: string, b: string) => a < b ? -1 : a > b ? 1 : 0;
const stocks = (n: number) => n === 1 ? '1 stock' : `${n} stocks`;
/** The left-out stocks of a portfolio as the TICKERS_EXCLUDED warning, sorted by ticker (null when none is left out);
    kept: the stocks that are run. Its message is a plain sentence the page shows as it is (no field or code names,
    page review V5); count, tickers and reasons (each stock's code, field and message) are the details. When none is
    kept the request is refused, UNIVERSE_EMPTY at `field` (lead decision 2026-10-26: no cash-only result), with the
    count and the reasons by code; the preview refuses it the same way, since the matching run is refused. */
export function leftOut(excluded: readonly Exclusion[], kept: number, field: string, what: 'run' | 'preview'): Warning | null {
  const xs = [...excluded].sort((a, b) => byTicker(a.ticker, b.ticker));
  const codes = new Map<string, number>();
  for (const x of xs) codes.set(x.code, (codes.get(x.code) || 0) + 1);
  const counts = [...codes].map(([c, n]) => `${n} ${c}`).join(', ');
  const one = xs.length === 1, its = one ? 'its' : 'their';
  if (!kept) throw new ValidationError('UNIVERSE_EMPTY', field, xs.length
    ? `${one ? 'The picked stock was' : `All ${xs.length} picked stocks were`} left out because ${its} own data cannot serve the strategy (${counts}): no stock is left to ${what === 'run' ? 'trade' : 'count signals on'}. ${one ? '' : 'The first is '}${xs[0].ticker}: ${xs[0].message}`
    : 'The portfolio has no stock to run.');
  if (!xs.length) return null;
  const n = one ? '1 picked stock was' : `${xs.length} picked stocks were`;
  return { code: 'TICKERS_EXCLUDED', count: xs.length, tickers: xs.map(x => x.ticker), reasons: xs.map(x => ({ ...x })),
    message: what === 'run'
      ? `${n} left out of this run because ${its} own data cannot serve the strategy. The run trades the other ${stocks(kept)}.`
      : `${n} left out of this preview because ${its} own data cannot serve the strategy. The preview counts the signals of the other ${stocks(kept)}.` };
}
