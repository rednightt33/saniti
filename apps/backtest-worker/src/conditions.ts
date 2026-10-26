/* Entry and exit conditions on one ticker's bars, with the semantics of the backtest page (backtest.html `regEval`,
   `cmpSeries`, the CATALOG conditions, `signalsFor` and `exitSeries`), computed on the Terminal's verified indicator
   outputs instead of the page's demo formulas. A condition is a 0/1 series aligned with the bars:
   - bar 0 is never true (the page starts every comparison at bar 1);
   - a bar where either side is not a finite number is false, and a cross also needs both sides on the bar before;
   - "within N bars" keeps, per condition, the last bar it was true; the entry is true on bar i when at least `need`
     conditions were true on one of the bars i-N+1..i (they need not be true on the same bar).
   Flow and broker conditions are not here: they stay disabled until their storage data is verified. */
import { F, isN } from '../../edge-bff/terminal/src/calc/indicators.ts';
import type { Bars, Num, Out, Params } from '../../edge-bff/terminal/src/calc/indicators.ts';
import { ValidationError, indicator, resolveParams } from './registry.ts';

export type Op = 'gt' | 'lt' | 'crosses_above' | 'crosses_below';
export interface Side { type: 'price' | 'output' | 'value'; output?: string; value?: number }
export interface IndicatorCondition { id: string; enabled?: boolean; kind: 'indicator'; indicator: string; params?: Params; lhs: Side; op: Op; rhs: Side }
export interface PriceActionCondition { id: string; enabled?: boolean; kind: 'price_action'; type: string; params?: Params; op?: string; value?: number }
export type Condition = IndicatorCondition | PriceActionCondition;
export type Signal = Uint8Array;

const OPS: Op[] = ['gt', 'lt', 'crosses_above', 'crosses_below'];
type Series = ReadonlyArray<Num | undefined>;
const val = (s: Series | null, v: number, i: number): number => s ? (isN(s[i]) ? s[i] as number : NaN) : v;

/** Per-ticker memo of indicator outputs, keyed by function and parameters. */
export class Calc {
  bars: Bars; n: number; memo = new Map<string, Out>();
  constructor(bars: Bars) { this.bars = bars; this.n = bars.C.length }
  out(key: string, params: Params): Out {
    const id = key + JSON.stringify(params);
    let o = this.memo.get(id);
    if (!o) { o = F[key](this.bars, params); this.memo.set(id, o) }
    return o;
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

export function indicatorCondition(c: Calc, cond: IndicatorCondition, field = 'condition'): Signal {
  const r = indicator(cond.indicator, `${field}.indicator`), params = resolveParams(r, cond.params, `${field}.params`);
  if (!OPS.includes(cond.op)) throw new ValidationError('INVALID_CONDITION', `${field}.op`, `${field}.op must be one of ${OPS.join(', ')}.`);
  const outs = c.out(r.key, params);
  const a = side(c, cond.lhs, outs, r.outputs, r.price_input, `${field}.lhs`, false);
  const b = side(c, cond.rhs, outs, r.outputs, r.price_input, `${field}.rhs`, true);
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
  if (typeof cond.value !== 'number' || !Number.isFinite(cond.value)) throw new ValidationError('INVALID_CONDITION', `${field}.value`, `${field}.value must be a number.`);
  return cond.value;
};

export const PRICE_ACTION: Record<string, { ops: string[]; params: Record<string, number>; value: boolean }> = {
  dip: { ops: ['lte'], params: {}, value: true },                                   // one-day return <= value (fraction)
  breakout: { ops: ['close_above_high'], params: { length: 20 }, value: false },     // close > highest high of the previous N bars
  volspike: { ops: ['gt'], params: { length: 20 }, value: true },                   // volume / SMA(volume, N) ending the bar before > value
  macross: { ops: ['golden_cross', 'fast_above_slow'], params: { fast_length: 20, slow_length: 50 }, value: false },
  macd: { ops: ['bullish_divergence', 'crosses_above_signal', 'histogram_positive'], params: { fast_length: 12, slow_length: 26, signal_length: 9 }, value: false },
};

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
  const op = cond.op ?? spec.ops[0];
  if (!spec.ops.includes(op)) throw new ValidationError('INVALID_CONDITION', `${field}.op`, `${field}.op must be one of ${spec.ops.join(', ')}.`);
  const p = cond.params || {}, f = `${field}.params`;
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

export function conditionSeries(c: Calc, cond: Condition, field = 'condition'): Signal {
  if (!cond || typeof cond !== 'object') throw new ValidationError('INVALID_CONDITION', field, `${field} must be an object.`);
  if (cond.kind === 'indicator') return indicatorCondition(c, cond, field);
  if (cond.kind === 'price_action') return priceActionCondition(c, cond, field);
  throw new ValidationError('UNKNOWN_CONDITION', `${field}.kind`, `${field}.kind must be indicator or price_action (flow conditions are not enabled yet).`);
}

export type EntryLogic = 'all' | 'any' | 'at_least';

/** The combined entry state (page `signalsFor`). */
export function combineEntry(series: Signal[], logic: EntryLogic, atLeast: number, windowBars: number, n: number): Signal {
  const entry = new Uint8Array(n);
  if (!series.length) return entry;
  const need = logic === 'all' ? series.length : logic === 'any' ? 1 : Math.min(atLeast, series.length);
  const W = Math.max(1, windowBars | 0), recent = series.map(() => -1e9);
  for (let i = 0; i < n; i++) {
    let met = 0;
    for (let k = 0; k < series.length; k++) { if (series[k][i]) recent[k] = i; if (i - recent[k] < W) met++ }
    entry[i] = met >= need ? 1 : 0;
  }
  return entry;
}

/** The exit-signal state (page `exitSeries`): any or all of the active exit conditions on the same bar. */
export function combineExit(series: Signal[], logic: 'any' | 'all', n: number): Signal {
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
