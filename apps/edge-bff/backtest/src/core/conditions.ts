/* Entry and exit conditions on one ticker's bars, with the semantics of the backtest page (backtest.html `regEval`,
   `cmpSeries`, the CATALOG conditions, `signalsFor` and `exitSeries`), computed on the Terminal's verified indicator
   outputs instead of the page's demo formulas. A condition is a 0/1 series aligned with the bars:
   - bar 0 is never true (the page starts every comparison at bar 1);
   - a bar where either side is not a finite number is false, and a cross also needs both sides on the bar before;
   - "within N bars" keeps, per condition, the last bar it was true; the entry is true on bar i when at least `need`
     conditions were true on one of the bars i-N+1..i (they need not be true on the same bar).
   Flow and broker conditions (kind 'flow': CATALOG fnet, broker, top5) read the ticker's broker files through
   flow.ts (the Terminal's flow definitions, values in IDR); the Calc carries them as its second argument. Whether
   the page and the worker offer them is catalog.flow.available (CONTRACT.md section 3), not decided here. */
import { F, isN } from '../../../terminal/src/calc/indicators.ts';
import type { Bars, Num, Out, Params } from '../../../terminal/src/calc/indicators.ts';
import type { FlowData } from './flow.ts';
import { brokerNet, rollingSum, top5Accumulation } from './flow.ts';
import { ValidationError, indicator, resolveParams } from './registry.ts';

export type Op = 'gt' | 'lt' | 'crosses_above' | 'crosses_below';
export interface Side { type: 'price' | 'output' | 'value'; output?: string; value?: number }
export interface IndicatorCondition { id: string; enabled?: boolean; kind: 'indicator'; indicator: string; params?: Params; lhs: Side; op: Op; rhs: Side }
export interface PriceActionCondition { id: string; enabled?: boolean; kind: 'price_action'; type: string; params?: Params; op?: string; value?: number }
export interface FlowCondition { id: string; enabled?: boolean; kind: 'flow'; type: string; params?: { length?: unknown; broker?: unknown; [key: string]: unknown }; op?: string; value?: number }
export type Condition = IndicatorCondition | PriceActionCondition | FlowCondition;
export type Signal = Uint8Array;

const OPS: Op[] = ['gt', 'lt', 'crosses_above', 'crosses_below'];
type Series = ReadonlyArray<Num | undefined>;
const val = (s: Series | null, v: number, i: number): number => s ? (isN(s[i]) ? s[i] as number : NaN) : v;

/** Per-ticker memo of indicator outputs, keyed by function and parameters, and of flow series (the ticker's flow
    data, flow.ts flowData on the same bars, when its broker files were loaded). */
export class Calc {
  bars: Bars; n: number; memo = new Map<string, Out>(); flow?: FlowData; flowMemo = new Map<string, Float64Array>();
  constructor(bars: Bars, flow?: FlowData) {
    this.bars = bars; this.n = bars.C.length;
    if (flow && flow.fnet.length !== this.n) throw new RangeError(`Calc: flow data has ${flow.fnet.length} bars, the prices ${this.n}.`);
    this.flow = flow;
  }
  out(key: string, params: Params): Out {
    const id = key + JSON.stringify(params);
    let o = this.memo.get(id);
    if (!o) { o = F[key](this.bars, params); this.memo.set(id, o) }
    return o;
  }
  flowSeries(key: string, make: () => Float64Array): Float64Array {
    let s = this.flowMemo.get(key);
    if (!s) { s = make(); this.flowMemo.set(key, s) }
    return s;
  }
}

/** a OP b on every bar (b is a series or a constant), with the page's comparison rules. */
export function compare(a: Series, op: Op, b: Series | null, v: number, n: number): Signal {
  const r = new Uint8Array(n);
  for (let i = 1; i < n; i++) {
    const x = val(a, 0, i), y = val(b, v, i);
    if (Number.isNaN(x) || Number.isNaN(y)) continue;
    const px = val(a, 0, i - 1), py = val(b, v, i - 1);
    r[i] = op === 'gt' ? +(x > y) : op === 'lt' ? +(x < y) : op === 'crosses_above' ? +(px <= py && x > y) : +(px >= py && x < y);
  }
  return r;
}

function side(c: Calc, s: Side, outs: Out, outputs: string[], priceInput: 'close' | 'volume', field: string, allowValue: boolean): Series | null {
  if (!s || typeof s !== 'object') throw new ValidationError('INVALID_CONDITION', field, `${field} is required.`);
  if (s.type === 'price') return priceInput === 'volume' ? c.bars.V : c.bars.C;
  if (s.type === 'output') {
    if (!outputs.includes(s.output as string)) throw new ValidationError('UNKNOWN_OUTPUT', `${field}.output`, `${field}.output must be one of ${outputs.join(', ')}.`);
    return outs[s.output as string];
  }
  if (s.type === 'value' && allowValue) {
    if (typeof s.value !== 'number' || !Number.isFinite(s.value)) throw new ValidationError('INVALID_CONDITION', `${field}.value`, `${field}.value must be a number.`);
    return null;
  }
  throw new ValidationError('INVALID_CONDITION', `${field}.type`, `${field}.type must be ${allowValue ? 'output or value' : 'price or output'}.`);
}

/** Whether a series has a value on one of the bars 0..last. */
function anyValue(s: ArrayLike<Num | undefined>, last: number, ok: (v: Num | undefined) => boolean): boolean {
  for (let i = 0; i <= last && i < s.length; i++) if (ok(s[i])) return true;
  return false;
}
/* `last`: the last bar the caller can see (a backtest: the ticker's last bar inside the period; not given: every bar).
   Whether a series has any value at all (INDICATOR_OUTPUT_EMPTY, FLOW_OUTPUT_EMPTY, FLOW_UNAVAILABLE) is decided on
   the bars up to it, so bars published after a backtest's period never decide whether its conditions can run, nor
   the error's message (no look-ahead); the series themselves are computed on every bar and are causal. A portfolio
   and the signals preview read such a condition as false on every bar instead, as a series is before its first
   value, unless the entry cannot switch on without it (signals.ts tickerSignals): what a ticker trades up to a day
   then never depends on its bars after that day either. */
const upTo = (last: number | undefined) => last === undefined ? '' : ' up to the end of the period';

export function indicatorCondition(c: Calc, cond: IndicatorCondition, field = 'condition', last?: number): Signal {
  const r = indicator(cond.indicator, `${field}.indicator`), params = resolveParams(r, cond.params, `${field}.params`);
  if (!OPS.includes(cond.op)) throw new ValidationError('INVALID_CONDITION', `${field}.op`, `${field}.op must be one of ${OPS.join(', ')}.`);
  const outs = c.out(r.key, params);
  const a = side(c, cond.lhs, outs, r.outputs, r.price_input, `${field}.lhs`, false);
  const b = side(c, cond.rhs, outs, r.outputs, r.price_input, `${field}.rhs`, true);
  // parameters the registry accepts can still leave an output without a single value (CCI constant 0, a length longer
  // than the history, a volume indicator on an index); that is an error, not a condition that is silently never true
  for (const [s, f] of [[a, `${field}.lhs`], [b, `${field}.rhs`]] as [Series | null, string][])
    if (s && !anyValue(s, last ?? c.n - 1, isN)) throw new ValidationError('INDICATOR_OUTPUT_EMPTY', f, `${f}: ${r.id} with these parameters has no value on this ticker's bars${upTo(last)}.`);
  return compare(a as Series, cond.op, b, b ? 0 : cond.rhs.value as number, c.n);
}

/* ---- price-action and pattern conditions of the page (CATALOG: dip, breakout, volspike, macross, macd) ---- */
const num = (p: Params, key: string, def: number, field: string, integer = true, min = 1): number => {
  const v = p[key] === undefined ? def : p[key];
  if (typeof v !== 'number' || !Number.isFinite(v) || (integer && !Number.isInteger(v)) || v < min)
    throw new ValidationError('INVALID_PARAM', `${field}.${key}`, `${field}.${key} must be ${integer ? 'a whole number' : 'a number'} of at least ${min}.`);
  return v;
};
const threshold = (cond: PriceActionCondition, field: string): number => {
  const spec = PRICE_ACTION[cond.type].value as ThresholdRange;
  if (typeof cond.value !== 'number' || !Number.isFinite(cond.value)) throw new ValidationError('INVALID_CONDITION', `${field}.value`, `${field}.value must be a number.`);
  if (!inRange(spec, cond.value)) throw new ValidationError('VALUE_OUT_OF_RANGE', `${field}.value`, `${field}.value is a ${spec.unit} and must be ${spec.open ? 'above' : 'at least'} ${spec.min}.`);
  return cond.value;
};

/* value: what the threshold measures and the range that quantity can take; a threshold outside it is refused (a
   percent typed where a fraction is expected, -3 for -3%, would otherwise give a condition that is never true).
   min with open = true: the value must be above min; open = false: at least min. A one-day return is above -1 (a
   close of 0 is not a price); a volume ratio is at least 0 (volume and its average are never negative), and 0 is a
   valid, trivial threshold (true on every bar with volume) that the page's sensitivity grid reaches from 2. */
export interface ThresholdRange { unit: string; min: number; open: boolean }
export const PRICE_ACTION: Record<string, { ops: string[]; params: Record<string, number>; value: false | ThresholdRange }> = {
  dip: { ops: ['lte'], params: {}, value: { unit: 'one-day return, fraction', min: -1, open: true } },     // return <= value
  breakout: { ops: ['close_above_high'], params: { length: 20 }, value: false },     // close > highest high of the previous N bars
  volspike: { ops: ['gt'], params: { length: 20 }, value: { unit: 'volume ratio', min: 0, open: false } },  // volume / SMA(volume, N) ending the bar before > value
  macross: { ops: ['golden_cross', 'fast_above_slow'], params: { fast_length: 20, slow_length: 50 }, value: false },
  macd: { ops: ['bullish_divergence', 'crosses_above_signal', 'histogram_positive'], params: { fast_length: 12, slow_length: 26, signal_length: 9 }, value: false },
};
const inRange = (r: ThresholdRange, v: number) => r.open ? v > r.min : v >= r.min;
/** Whether a price-action threshold is inside what its quantity can take (PRICE_ACTION value); true for a type
    without a threshold or an unknown type (those are refused by priceActionCondition itself). The sensitivity grid
    (robustness.ts) asks this before it runs a cell. */
export function thresholdAccepted(type: string, value: number): boolean {
  const spec = Object.prototype.hasOwnProperty.call(PRICE_ACTION, type) ? PRICE_ACTION[type].value : false;
  return !spec || (Number.isFinite(value) && inRange(spec, value));
}

/* bullish divergence (page `bullDiv`): a swing low confirmed k bars later, below the previous swing low within `look`
   bars, while the MACD line makes a higher low; flagged on the confirmation bar, so it uses no later data */
export function bullishDivergence(low: Series, line: Series, look = 40, k = 3): Signal {
  const n = low.length, out = new Uint8Array(n), piv: number[] = [], l = (i: number) => val(low, 0, i), m = (i: number) => val(line, 0, i);
  for (let i = k; i < n - k; i++) {
    let isLow = !Number.isNaN(l(i));                                  // a missing low is never a swing low
    for (let j = 1; j <= k && isLow; j++) if (!(l(i) <= l(i - j)) || !(l(i) <= l(i + j))) isLow = false;
    if (isLow) piv.push(i);
  }
  for (let p = 1; p < piv.length; p++) {
    const a = piv[p - 1], b = piv[p];
    if (b - a > look) continue;
    if (l(b) < l(a) && m(b) > m(a)) out[b + k] = 1;                   // NaN on either side compares false
  }
  return out;
}

export function priceActionCondition(c: Calc, cond: PriceActionCondition, field = 'condition'): Signal {
  const spec = PRICE_ACTION[cond.type];
  if (!spec) throw new ValidationError('UNKNOWN_CONDITION', `${field}.type`, `${field}.type must be one of ${Object.keys(PRICE_ACTION).join(', ')}.`);
  const op = cond.op === undefined ? spec.ops[0] : cond.op;             // absent: the type's operator (contract.ts op?)
  if (!spec.ops.includes(op)) throw new ValidationError('INVALID_CONDITION', `${field}.op`, `${field}.op must be one of ${spec.ops.join(', ')}.`);
  const p = cond.params === undefined ? {} : cond.params, f = `${field}.params`;
  if (p === null || typeof p !== 'object' || Array.isArray(p)) throw new ValidationError('INVALID_PARAMS', f, `${f} must be an object.`);
  for (const key of Object.keys(p)) if (!(key in spec.params)) throw new ValidationError('PARAM_NOT_ACCEPTED', `${f}.${key}`, `${cond.type} does not accept ${key}.`);
  const { C, H, L, V } = c.bars, n = c.n, r = new Uint8Array(n);
  const at = (s: Series, i: number) => isN(s[i]) ? s[i] as number : NaN;
  if (cond.type === 'dip') {
    const v = threshold(cond, field);
    for (let i = 1; i < n; i++) r[i] = +(at(C, i) / at(C, i - 1) - 1 <= v);
  } else if (cond.type === 'breakout') {
    const len = num(p, 'length', spec.params.length, f);
    for (let i = len; i < n; i++) { let m = -Infinity; for (let j = i - len; j < i; j++) m = Math.max(m, at(H, j)); r[i] = +(at(C, i) > m) }
  } else if (cond.type === 'volspike') {
    const len = num(p, 'length', spec.params.length, f), v = threshold(cond, field), avg = c.out('volume_sma', { length: len }).volume_sma;
    for (let i = len; i < n; i++) r[i] = +(at(V, i) / at(avg, i - 1) > v);
  } else if (cond.type === 'macross') {
    const fast = num(p, 'fast_length', spec.params.fast_length, f), slow = num(p, 'slow_length', spec.params.slow_length, f);
    const a = c.out('sma', { length: fast, source: 'close' }).sma, b = c.out('sma', { length: slow, source: 'close' }).sma;
    return op === 'golden_cross' ? compare(a, 'crosses_above', b, 0, n) : compare(a, 'gt', b, 0, n);
  } else {
    const q = { fast_length: num(p, 'fast_length', 12, f), slow_length: num(p, 'slow_length', 26, f), signal_length: num(p, 'signal_length', 9, f), source: 'close' };
    const m = c.out('macd', q);
    if (op === 'bullish_divergence') return bullishDivergence(L, m.macd);
    if (op === 'crosses_above_signal') return compare(m.macd, 'crosses_above', m.signal, 0, n);
    return compare(m.histogram, 'gt', null, 0, n);
  }
  return r;
}

/* ---- flow and broker conditions of the page (CATALOG: fnet, broker, top5), values in IDR ---- */
/* fnet: foreign net summed over `length` bars gt | lt value; broker: the broker's net summed over `length` bars gt
   value; top5: the page's top-5 accumulation over `length` bars gt value. The page compares in Rp B (x / 1e9 > val);
   the wire carries IDR (contract.ts), so the comparison is x > value. */
export const FLOW: Record<string, { ops: string[]; params: string[] }> = {
  fnet: { ops: ['gt', 'lt'], params: ['length'] },
  broker: { ops: ['gt'], params: ['length', 'broker'] },
  top5: { ops: ['gt'], params: ['length'] },
};

/** The checks a flow condition must pass without any data (type, operator, parameters, value), so a request can be
    refused before its broker files are downloaded. */
export function flowConditionShape(cond: FlowCondition, field = 'condition'): { type: string; op: 'gt' | 'lt'; length: number; broker: string | null; value: number } {
  const spec = Object.prototype.hasOwnProperty.call(FLOW, cond.type) ? FLOW[cond.type] : undefined;
  if (!spec) throw new ValidationError('UNKNOWN_CONDITION', `${field}.type`, `${field}.type must be one of ${Object.keys(FLOW).join(', ')}.`);
  if (!spec.ops.includes(cond.op as string)) throw new ValidationError('INVALID_CONDITION', `${field}.op`, `${field}.op must be ${spec.ops.join(' or ')}.`);
  const p = cond.params, f = `${field}.params`;
  if (!p || typeof p !== 'object' || Array.isArray(p)) throw new ValidationError('INVALID_PARAMS', f, `${f} must be an object.`);
  for (const key of Object.keys(p)) if (!spec.params.includes(key)) throw new ValidationError('PARAM_NOT_ACCEPTED', `${f}.${key}`, `${cond.type} does not accept ${key}.`);
  const length = p.length;
  if (typeof length !== 'number' || !Number.isInteger(length) || length < 1) throw new ValidationError('INVALID_PARAM', `${f}.length`, `${f}.length must be a whole number of at least 1.`);
  let broker: string | null = null;
  if (cond.type === 'broker') {
    if (typeof p.broker !== 'string' || !p.broker) throw new ValidationError('INVALID_PARAM', `${f}.broker`, `${f}.broker must be a broker code.`);
    broker = p.broker;
  }
  if (typeof cond.value !== 'number' || !Number.isFinite(cond.value)) throw new ValidationError('INVALID_CONDITION', `${field}.value`, `${field}.value must be a number (IDR).`);
  return { type: cond.type, op: cond.op as 'gt' | 'lt', length, broker, value: cond.value };
}

/** A flow condition on the ticker's flow data. Without flow data every flow condition is FLOW_UNAVAILABLE, whatever
    its shape (CONTRACT.md section 3 refuses them all while flow is unavailable); then the shape; then what needs the
    data: no broker row on any price bar (FLOW_UNAVAILABLE), a series without any value on the ticker's bars (a window
    longer than the bars with broker data: FLOW_OUTPUT_EMPTY, the rule of INDICATOR_OUTPUT_EMPTY). A broker without a
    row on this ticker's bars did not trade it: its net is 0 on every bar with broker data (flow.ts brokerNet), so its
    condition is evaluated; whether the code is a broker at all is checked against the published broker list by the
    caller (the worker's validation, UNKNOWN_BROKER). Both data checks look at the bars up to `last` only (see
    indicatorCondition). */
export function flowCondition(c: Calc, cond: FlowCondition, field = 'condition', last?: number): Signal {
  const flow = c.flow, n = c.n, unavailable = (why: string) => new ValidationError('FLOW_UNAVAILABLE', field, `${field}: flow conditions need the ticker's broker data, which ${why}.`);
  if (!flow) throw unavailable('is not available');
  const q = flowConditionShape(cond, field);
  const to = Math.min(flow.to, last ?? n - 1);
  if (!(flow.from <= to)) throw unavailable(`has no row on any of its price bars${upTo(last)}`);
  const s = q.type === 'top5' ? c.flowSeries(`top5|${q.length}`, () => top5Accumulation(flow, q.length))
    : q.type === 'fnet' ? c.flowSeries(`fnet|${q.length}`, () => rollingSum(flow.fnet, q.length, flow.from, flow.to))
    : c.flowSeries(`broker|${q.broker}|${q.length}`, () => rollingSum(brokerNet(flow, q.broker as string), q.length, flow.from, flow.to));
  if (!anyValue(s, to, v => Number.isFinite(v)))
    throw new ValidationError('FLOW_OUTPUT_EMPTY', `${field}.params.length`, `${field}: ${q.type} over ${q.length} bars has no value on this ticker's bars${upTo(last)} (its broker data covers ${to - flow.from + 1} price bars).`);
  if (q.type === 'top5') {
    const r = new Uint8Array(n);
    for (let i = 0; i < n; i++) r[i] = +(s[i] > q.value);                  // NaN (no value) compares false
    return r;
  }
  return compare(s as unknown as Series, q.op, null, q.value, n);     // the page's cmpSeries: bar 0 never, NaN false
}

/** A condition's 0/1 series on the ticker's bars; `last` as in indicatorCondition (price-action conditions have no
    data check). */
export function conditionSeries(c: Calc, cond: Condition, field = 'condition', last?: number): Signal {
  if (!cond || typeof cond !== 'object') throw new ValidationError('INVALID_CONDITION', field, `${field} must be an object.`);
  if (cond.kind === 'indicator') return indicatorCondition(c, cond, field, last);
  if (cond.kind === 'price_action') return priceActionCondition(c, cond, field);
  if (cond.kind === 'flow') return flowCondition(c, cond, field, last);
  throw new ValidationError('UNKNOWN_CONDITION', `${field}.kind`, `${field}.kind must be indicator, price_action or flow.`);
}

export type EntryLogic = 'all' | 'any' | 'at_least';

export const WINDOW_BARS = { min: 1, max: 20 };                  // the page's "within N bars" input (min 1, max 20)

/** How many of `count` active entry conditions combineEntry needs true within the window: all of them, one, or
    at_least (above the count: all of them, as on the page). */
export const entryNeed = (logic: EntryLogic, atLeast: number | undefined, count: number): number =>
  logic === 'all' ? count : logic === 'any' ? 1 : Math.min(atLeast as number, count);

/** The combined entry state (page `signalsFor`). Inputs outside the page's controls are refused, never adjusted:
    logic all/any/at_least, a whole window of 1-20 bars, and at_least a whole number of at least 1. As on the page, an
    at_least above the number of active conditions means all of them (a condition switched off keeps the rule usable). */
export function combineEntry(series: Signal[], logic: EntryLogic, atLeast: number | undefined, windowBars: number, n: number): Signal {
  if (!['all', 'any', 'at_least'].includes(logic)) throw new ValidationError('INVALID_ENTRY', 'entry.logic', 'entry.logic must be all, any or at_least.');
  if (!Number.isInteger(windowBars) || windowBars < WINDOW_BARS.min || windowBars > WINDOW_BARS.max)
    throw new ValidationError('INVALID_ENTRY', 'entry.window_bars', `entry.window_bars must be a whole number from ${WINDOW_BARS.min} to ${WINDOW_BARS.max}.`);
  if (logic === 'at_least' && !(Number.isInteger(atLeast) && (atLeast as number) >= 1))
    throw new ValidationError('INVALID_ENTRY', 'entry.at_least', 'entry.at_least must be a whole number of at least 1.');
  const entry = new Uint8Array(n);
  if (!series.length) return entry;
  const need = entryNeed(logic, atLeast, series.length);
  const W = windowBars, recent = series.map(() => -1e9);
  for (let i = 0; i < n; i++) {
    let met = 0;
    for (let k = 0; k < series.length; k++) { if (series[k][i]) recent[k] = i; if (i - recent[k] < W) met++ }
    entry[i] = met >= need ? 1 : 0;
  }
  return entry;
}

/** The exit-signal state (page `exitSeries`): any or all of the active exit conditions on the same bar. */
export function combineExit(series: Signal[], logic: 'any' | 'all', n: number): Signal {
  if (logic !== 'any' && logic !== 'all') throw new ValidationError('INVALID_EXIT', 'exit.signals.logic', 'exit.signals.logic must be any or all.');
  const r = new Uint8Array(n);
  if (!series.length) return r;
  for (let i = 0; i < n; i++) { let hit = 0; for (const s of series) hit += s[i]; r[i] = logic === 'all' ? +(hit === series.length) : +(hit > 0) }
  return r;
}

/** Bars inside [from, to] where a signal switches on (false on the bar before, true on this one): the chart's arrows. */
export function switchOns(s: Signal, from: number, to: number): number[] {
  const out: number[] = [];
  for (let i = Math.max(0, from); i <= to && i < s.length; i++) if (s[i] && !(i > 0 && s[i - 1])) out.push(i);
  return out;
}

/** Bars inside [from, to] where a signal is true (the chips' "true on N days"). */
export function trueBars(s: Signal, from: number, to: number): number {
  let n = 0;
  for (let i = Math.max(0, from); i <= to && i < s.length; i++) n += s[i];
  return n;
}
