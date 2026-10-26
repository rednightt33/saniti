/* Signals of a backtest request on one ticker's own bars, and their place on the result calendar (CONTRACT.md
   sections 4-6). One module for the engine (worker) and the page's preview, so a marker the page draws before a run
   and the event a trade executes after it come from the same code:
   - the enabled entry and exit conditions as conditions.ts computes them (page semantics, registry formulas);
   - the combined entry state (combineEntry) and its entry events: bars where it switches from false to true on the
     ticker's own bars (D-E1); the combined exit-signal state (combineExit);
   - per event, the entry conditions true within the window (a trade's entry_condition_ids);
   - the portfolio ranking scores and the liquidity value on a signal bar (section 6, D-E5 ranking, D-K9);
   - the result calendar (section 4, D-K5c), the ticker-bar <-> calendar index maps, and the SignalTracks.
   Pure module: no DOM and no Node API. */
import type { BacktestRequest, Condition, SignalTrack } from './contract.ts';
import type { FlowData } from './flow.ts';
import type { Num } from '../../../terminal/src/calc/indicators.ts';
import { isN, sma } from '../../../terminal/src/calc/indicators.ts';
import { combineEntry, combineExit, conditionSeries, switchOns } from './conditions.ts';
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

/** Every enabled condition of the request on the ticker's bars (full history: warm-up uses real bars). */
export function tickerSignals(calc: Calc, req: SignalRequest, active = requestConditions(req)): TickerSignals {
  const n = calc.n;
  // conditions.ts names its own Condition union (page shapes); the wire conditions of contract.ts are the same objects
  const series = (list: ActiveCondition[]) => list.map(a => ({ id: a.id, s: conditionSeries(calc, a.cond as Parameters<typeof conditionSeries>[1], a.field) }));
  const entryConditions = series(active.entry), exitConditions = series(active.exit);
  return {
    entryConditions, exitConditions,
    entry: combineEntry(entryConditions.map(x => x.s), req.entry.logic, req.entry.at_least, req.entry.window_bars, n),
    exit: req.exit ? combineExit(exitConditions.map(x => x.s), req.exit.signals.logic, n) : new Uint8Array(n),
    window: req.entry.window_bars,
  };
}

/** Entry events (switch-ons of the combined entry state) on the ticker's bars first..last. */
export const entryEvents = (sig: TickerSignals, first: number, last: number): number[] => switchOns(sig.entry, first, last);

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

/** The result calendar: the sorted union of the given bar dates inside [from, to] (IHSG and every run ticker). */
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
    [from, to] and the date of the last one, as the backtest counts them. tickerDates = the bars' dates. */
export function previewRow(calc: Calc, tickerDates: readonly string[], req: SignalRequest, from: string, to: string, active = requestConditions(req)): { entry_signals: number; last_signal: string | null } {
  let first = 0, last = tickerDates.length - 1;
  while (first <= last && tickerDates[first] < from) first++;
  while (last >= first && tickerDates[last] > to) last--;
  const on = first <= last ? entryEvents(tickerSignals(calc, req, active), first, last) : [];
  return { entry_signals: on.length, last_signal: on.length ? tickerDates[on[on.length - 1]] : null };
}
