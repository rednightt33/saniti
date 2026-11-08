/* The 20 candlestick patterns (EXEC-SCREENER-FLOW-CANDLES P6; verification/screener/P6_CANDLES.md; user decisions
   2026-11-07 "2A": in the Backtest core, used by the Screener and later the Backtest, so engine_version changes; K2 "A").
   One registry (candle-registry.json: each pattern a list of rules over the candle primitives, with its parameters,
   their defaults, meaning, min and max) and one evaluator (candleSignal): no pattern has geometry of its own here.
   - Primitives per candle: open, high, low, close, range, body, upper and lower shadow, body top, bottom and middle,
     colour (dir), and the average body of the sessions before the pattern (avg_body).
   - Prior trend: the session before candle 1; `average`: close below (a bullish pattern) or above (a bearish one) the
     average of the last trend_length closes, compared as trend_length x close against their sum; `change`: close
     below / above the close trend_length sessions earlier; `none`: no test. Every window sum is taken afresh, in bar
     order, on every bar, so a value never depends on where the history starts (the position dependence TA-Lib's rolling
     totals show, features/feature04/engine.py _calculate_canonical_pattern).
   - IDX guards, on every candle of a pattern: it traded (open, high, low and close finite and above 0, high at or above
     and low at or below the open and the close, volume finite and above 0), so a day without trades (O=H=L=C with
     volume 0) or a missing bar is never a pattern candle (not a doji); and its range spans at least min_range_ticks
     price ticks of its price band (registry tick_bands: the tick is derived from the price, never kept per stock). A
     suspended stock has no bar on its suspended days: a pattern reads the stock's own consecutive bars, as every other
     condition (the Screener's sessions, user 2026-11-07 G2).
   - Prices are the bars the caller gives (the adjusted series the core already reads); nothing is adjusted here.
   - A signal is 1 on the pattern's last candle (bar 0 never, as every core condition: conditions.ts compare); within N
     sessions is eventWithin (the EVENT "within" rule of the Screener, the entry window of the Backtest).
   Pure module: no DOM and no Node API. */
import type { Bars } from '../../../terminal/src/calc/indicators.ts';
import doc from './candle-registry.json' with { type: 'json' };
import { ValidationError } from './registry.ts';

export type Signal = Uint8Array;
export type CandleParamValue = number | string;
export type CandleParams = Record<string, CandleParamValue>;
export type Expr = number | string | (string | number | Expr)[];
export interface CandleParam {
  key: string; type: 'integer' | 'number' | 'enum'; label: string; default: CandleParamValue; meaning: string;
  min?: number; max?: number; options?: string[];
}
export interface CandleRule { lhs: Expr; op: '<' | '<=' | '>' | '>='; rhs: Expr; text: string; when?: Record<string, string> }
export interface CandlePattern {
  id: string; name: string; side: 'bullish' | 'bearish'; pair: string; mirror: string; bars: number; trend: 'down' | 'up';
  summary: string; misuse: string; synonyms: string[];
  /** the pattern's parameters, complete (a shared one merged with the pattern's overrides) */
  params: CandleParam[];
  rules: CandleRule[];
}
interface RawDoc {
  schema_version: number; note: string; tick_bands: { below: number | null; tick: number }[]; tick_source: string;
  primitives: Record<string, string>; params: Record<string, Omit<CandleParam, 'key'>>;
  patterns: (Omit<CandlePattern, 'params'> & { params: (string | (Partial<CandleParam> & { key: string }))[] })[];
}
const RAW = doc as unknown as RawDoc;

/** The candle primitives a rule may read on a candle (registry `primitives`, avg_body aside). */
export const PRIMITIVES = ['open', 'high', 'low', 'close', 'range', 'body', 'upper', 'lower', 'top', 'bottom', 'mid', 'dir'] as const;
type Prim = typeof PRIMITIVES[number];
const OPS = ['<', '<=', '>', '>='];
const FNS: Record<string, number | null> = { '+': null, '-': 2, '*': null, abs: 1, ticks: 2 };      // arity (null: 2 or more)
export const TREND_OPTIONS = ['average', 'change', 'none'];

/** The registry with every pattern's parameters complete (shared definitions merged with the pattern's overrides). */
export const CANDLES = {
  note: RAW.note, tick_bands: RAW.tick_bands, tick_source: RAW.tick_source, primitives: RAW.primitives,
  patterns: RAW.patterns.map(p => ({
    ...p,
    params: p.params.map(x => {
      const key = typeof x === 'string' ? x : x.key, shared = RAW.params[key];
      return { key, ...(shared || {}), ...(typeof x === 'string' ? {} : x) } as CandleParam;
    }),
  })) as CandlePattern[],
};
export const CANDLE_IDS: readonly string[] = CANDLES.patterns.map(p => p.id);
const BY_ID = new Map(CANDLES.patterns.map(p => [p.id, p]));

/* ---- price ticks (IDX price bands) ------------------------------------------------------------------------------- */

/** The tick of a price: the tick of the band the price is in. */
export function tickSize(price: number): number {
  for (const b of CANDLES.tick_bands) if (b.below === null || price < b.below) return b.tick;
  return CANDLES.tick_bands[CANDLES.tick_bands.length - 1].tick;
}
/** The number of price ticks between two prices, band by band (each part of the span in its own band's tick); in
    either order. Exact for prices on the tick grid; on adjusted prices the same measure, continuous. */
export function ticksBetween(a: number, b: number): number {
  const lo = Math.min(a, b), hi = Math.max(a, b);
  let n = 0, from = 0;
  for (const band of CANDLES.tick_bands) {
    const to = band.below === null ? Infinity : band.below, x = Math.max(lo, from), y = Math.min(hi, to);
    if (y > x) n += (y - x) / band.tick;
    from = to;
  }
  return n;
}

/* ---- the registry's checks (asserted at import) -------------------------------------------------------------------- */

function exprProblems(e: Expr, p: CandlePattern, w: string, keys: Set<string>, out: string[]): void {
  if (typeof e === 'number') { if (!Number.isFinite(e)) out.push(`${w}: ${e} is not a finite number`); return }
  if (typeof e === 'string') { if (!e.startsWith('$') || !keys.has(e.slice(1))) out.push(`${w}: ${JSON.stringify(e)} is not a parameter of ${p.id}`); return }
  if (!Array.isArray(e) || !e.length || typeof e[0] !== 'string') { out.push(`${w}: ${JSON.stringify(e)} is not an expression`); return }
  const [head, ...args] = e as [string, ...Expr[]];
  if ((PRIMITIVES as readonly string[]).includes(head)) {
    if (args.length !== 1 || !Number.isInteger(args[0]) || (args[0] as number) < 1 || (args[0] as number) > p.bars) out.push(`${w}: [${head}, candle] needs a candle from 1 to ${p.bars}`);
    return;
  }
  if (head === 'avg_body') { if (args.length) out.push(`${w}: avg_body takes no argument`); if (!keys.has('body_avg_length')) out.push(`${w}: avg_body needs the parameter body_avg_length`); return }
  if (!(head in FNS)) { out.push(`${w}: ${head} is not a primitive or a function`); return }
  const arity = FNS[head];
  if (arity === null ? args.length < 2 : args.length !== arity) out.push(`${w}: ${head} takes ${arity ?? '2 or more'} arguments`);
  for (const a of args) exprProblems(a, p, w, keys, out);
}
/** Every way the registry breaks its rules; empty when sound. */
export function candleProblems(c = CANDLES): string[] {
  const out: string[] = [], ids = new Set<string>();
  let below = 0;
  c.tick_bands.forEach((b, k) => {
    if (!(b.tick > 0)) out.push(`tick band ${k}: tick must be positive`);
    if (k < c.tick_bands.length - 1 ? !(typeof b.below === 'number' && b.below > below) : b.below !== null) out.push(`tick band ${k}: bands rise and the last has no upper end`);
    if (typeof b.below === 'number') below = b.below;
  });
  for (const p of c.patterns) {
    const w = `pattern ${p.id}`;
    if (ids.has(p.id)) out.push(`${w}: repeated id`); ids.add(p.id);
    if (!/^[a-z][a-z0-9_]*$/.test(p.id)) out.push(`${w}: an id is lower-case words joined by _`);
    for (const k of ['name', 'summary', 'misuse'] as const) if (!p[k]) out.push(`${w}: ${k} is required`);
    if (!Array.isArray(p.synonyms) || !p.synonyms.length) out.push(`${w}: synonyms are required (the page's search)`);
    if (!['bullish', 'bearish'].includes(p.side)) out.push(`${w}: side must be bullish or bearish`);
    if (p.trend !== (p.side === 'bullish' ? 'down' : 'up')) out.push(`${w}: a bullish pattern follows a down trend, a bearish one an up trend`);
    if (!(Number.isInteger(p.bars) && p.bars >= 1 && p.bars <= 3)) out.push(`${w}: bars must be 1 to 3`);
    const keys = new Set<string>();
    for (const q of p.params) {
      const v = `${w}.${q.key}`;
      if (keys.has(q.key)) out.push(`${v}: repeated`); keys.add(q.key);
      if (!q.label || !q.meaning) out.push(`${v}: label and meaning are required`);
      if (q.type === 'enum') { if (!q.options?.length || !q.options.includes(q.default as string)) out.push(`${v}: an enum needs options holding its default`) }
      else if (q.type === 'integer' || q.type === 'number') {
        const d = q.default as number;
        if (typeof d !== 'number' || q.min === undefined || q.max === undefined || d < q.min || d > q.max || (q.type === 'integer' && !Number.isInteger(d))) out.push(`${v}: a number needs min <= default <= max`);
      } else out.push(`${v}: type ${q.type}`);
    }
    for (const k of ['trend', 'trend_length', 'min_range_ticks']) if (!keys.has(k)) out.push(`${w}: every pattern takes ${k}`);
    const trend = p.params.find(q => q.key === 'trend');
    if (trend && (trend.options || []).some(o => !TREND_OPTIONS.includes(o))) out.push(`${w}.trend: options are ${TREND_OPTIONS.join(', ')}`);
    if (!p.rules.length) out.push(`${w}: rules are required`);
    p.rules.forEach((r, k) => {
      const v = `${w}.rules[${k}]`;
      if (!OPS.includes(r.op)) out.push(`${v}: op must be one of ${OPS.join(' ')}`);
      if (!r.text) out.push(`${v}: text is required`);
      exprProblems(r.lhs, p, `${v}.lhs`, keys, out); exprProblems(r.rhs, p, `${v}.rhs`, keys, out);
      for (const [key, value] of Object.entries(r.when || {})) {
        const q = p.params.find(x => x.key === key);
        if (!q || q.type !== 'enum' || !q.options?.includes(value)) out.push(`${v}.when: ${key} = ${value} is not an option of ${p.id}`);
      }
    });
  }
  for (const p of c.patterns) {
    for (const [rel, want] of [['pair', 'opposite'], ['mirror', 'opposite']] as const) {
      const q = c.patterns.find(x => x.id === p[rel]);
      if (!q) { out.push(`pattern ${p.id}: ${rel} ${p[rel]} is not a pattern`); continue }
      if (q[rel] !== p.id) out.push(`pattern ${p.id}: ${rel} ${q.id} does not name it back`);
      if (want === 'opposite' && q.side === p.side) out.push(`pattern ${p.id}: its ${rel} ${q.id} is on the same side`);
      if (q.bars !== p.bars) out.push(`pattern ${p.id}: its ${rel} ${q.id} has another number of candles`);
      if (rel === 'mirror' && JSON.stringify(q.params.map(x => [x.key, x.type, x.default, x.min, x.max, x.options])) !== JSON.stringify(p.params.map(x => [x.key, x.type, x.default, x.min, x.max, x.options])))
        out.push(`pattern ${p.id}: its mirror ${q.id} must take the same parameters with the same defaults and ranges`);
    }
  }
  return out;
}
const PROBLEMS = candleProblems();
if (PROBLEMS.length) throw new Error(`candle registry: ${PROBLEMS.join('; ')}`);

/* ---- parameters --------------------------------------------------------------------------------------------------- */

/** The pattern of an id, or UNKNOWN_CONDITION naming the field and the ids. */
export function candlePattern(id: unknown, field = 'pattern'): CandlePattern {
  const p = typeof id === 'string' ? BY_ID.get(id) : undefined;
  if (!p) throw new ValidationError('UNKNOWN_CONDITION', field, `${field}: ${JSON.stringify(id)} is not a candlestick pattern; use one of ${CANDLE_IDS.join(', ')}.`);
  return p;
}
const rangeText = (q: CandleParam) => `${q.type === 'integer' ? 'a whole number' : 'a number'} from ${q.min} to ${q.max}`;
/** The checked parameters, complete (a missing one takes its default); never rounded or clamped. An unknown key is
    PARAM_NOT_ACCEPTED; a wrong type, a value outside its range or an option not listed is INVALID_PARAM /
    PARAM_OUT_OF_RANGE with the range and a right and a wrong example (AGENTS.md "Gates and evidence"). */
export function resolveCandleParams(id: unknown, given: unknown, field = 'pattern.params'): CandleParams {
  const p = candlePattern(id, field.replace(/\.params$/, '.type'));
  if (given !== undefined && (given === null || typeof given !== 'object' || Array.isArray(given)))
    throw new ValidationError('INVALID_PARAMS', field, `${field} must be an object of parameters.`);
  const g = (given || {}) as Record<string, unknown>, out: CandleParams = {};
  for (const k of Object.keys(g)) if (!p.params.some(q => q.key === k))
    throw new ValidationError('PARAM_NOT_ACCEPTED', `${field}.${k}`, `${p.name} does not accept ${k}; it takes ${p.params.map(q => q.key).join(', ')}.`);
  for (const q of p.params) {
    const f = `${field}.${q.key}`, v = Object.prototype.hasOwnProperty.call(g, q.key) ? g[q.key] : q.default;
    if (q.type === 'enum') {
      if (typeof v !== 'string' || !q.options!.includes(v))
        throw new ValidationError('INVALID_PARAM', f, `${f} must be one of ${q.options!.join(', ')} (right: ${q.default}; wrong: ${JSON.stringify(v)}).`);
    } else {
      if (typeof v !== 'number' || !Number.isFinite(v) || (q.type === 'integer' && !Number.isInteger(v)))
        throw new ValidationError('INVALID_PARAM', f, `${f} must be ${rangeText(q)} (right: ${q.default}; wrong: ${JSON.stringify(v)}).`);
      if (v < (q.min as number) || v > (q.max as number))
        throw new ValidationError('PARAM_OUT_OF_RANGE', f, `${f} must be ${rangeText(q)} (right: ${q.default}; wrong: ${v}).`);
    }
    out[q.key] = v as CandleParamValue;
  }
  return out;
}

/** The bars a signal reads (the pattern's candles, and before them the trend's sessions or the average body's,
    whichever reach further back), at least 2 because bar 0 is never true. A signal on a bar is the same whatever the
    history before these bars (the cut probe of the Screener's lookback test). */
export function candleLookback(id: string, given?: unknown): number {
  const p = candlePattern(id), q = resolveCandleParams(id, given);
  const N = q.trend_length as number, trend = q.trend === 'average' ? N : q.trend === 'change' ? N + 1 : 0;
  const avg = p.params.some(x => x.key === 'body_avg_length') ? q.body_avg_length as number : 0;
  return Math.max(2, p.bars + Math.max(trend, avg));
}

/* ---- the evaluator ------------------------------------------------------------------------------------------------ */

interface Ctx { O: Float64Array; H: Float64Array; L: Float64Array; C: Float64Array; avg: Float64Array; first: number }
type Fn = (x: Ctx) => number;
const num = (v: unknown) => typeof v === 'number' && Number.isFinite(v) ? v : NaN;

function compile(e: Expr, q: CandleParams): Fn {
  if (typeof e === 'number') return () => e;
  if (typeof e === 'string') { const v = q[e.slice(1)] as number; return () => v }
  const [head, ...args] = e as [string, ...Expr[]];
  if ((PRIMITIVES as readonly string[]).includes(head)) {
    const k = (args[0] as number) - 1, prim = head as Prim;
    return x => {
      const i = x.first + k, o = x.O[i], h = x.H[i], l = x.L[i], c = x.C[i];
      switch (prim) {
        case 'open': return o; case 'high': return h; case 'low': return l; case 'close': return c;
        case 'range': return h - l; case 'body': return Math.abs(c - o);
        case 'upper': return h - Math.max(o, c); case 'lower': return Math.min(o, c) - l;
        case 'top': return Math.max(o, c); case 'bottom': return Math.min(o, c); case 'mid': return (o + c) / 2;
        case 'dir': return c > o ? 1 : c < o ? -1 : 0;
      }
    };
  }
  if (head === 'avg_body') return x => x.first > 0 ? x.avg[x.first - 1] : NaN;
  const fs = args.map(a => compile(a, q));
  switch (head) {
    case '+': return x => fs.reduce((s, f) => s + f(x), 0);
    case '-': return x => fs[0](x) - fs[1](x);
    case '*': return x => fs.reduce((s, f) => s * f(x), 1);
    case 'abs': return x => Math.abs(fs[0](x));
    case 'ticks': return x => ticksBetween(fs[0](x), fs[1](x));
  }
  throw new Error(`candles: ${head} is not a function`);
}
function rulesOf(p: CandlePattern, q: CandleParams): ((x: Ctx) => boolean)[] {
  return p.rules.filter(r => Object.entries(r.when || {}).every(([k, v]) => q[k] === v)).map(r => {
    const a = compile(r.lhs, q), b = compile(r.rhs, q);
    switch (r.op) {
      case '<': return x => a(x) < b(x);
      case '<=': return x => a(x) <= b(x);
      case '>': return x => a(x) > b(x);
      default: return x => a(x) >= b(x);
    }
  });
}

/** Whether bar i is a candle a pattern may use: it traded (prices finite and above 0, high and low around the open and
    the close, volume above 0) and spans at least minTicks price ticks. */
export function patternBar(bars: Bars, i: number, minTicks: number): boolean {
  const o = num(bars.O[i]), h = num(bars.H[i]), l = num(bars.L[i]), c = num(bars.C[i]), v = num(bars.V[i]);
  if (!(o > 0 && h > 0 && l > 0 && c > 0 && v > 0)) return false;              // NaN (missing) compares false
  if (!(h >= o && h >= c && l <= o && l <= c)) return false;
  return ticksBetween(l, h) >= minTicks;
}

/** The pattern's 0/1 signal on the bars: 1 on bar i when the pattern's last candle is bar i, every candle of it is a
    pattern bar (patternBar), the trend before it holds (unless trend none) and every rule holds. Bar 0 is never true.
    `given`: the pattern's parameters (resolveCandleParams). */
export function candleSignal(bars: Bars, id: string, given?: unknown, field = 'pattern.params'): Signal {
  const p = candlePattern(id, field.replace(/\.params$/, '.type')), q = resolveCandleParams(id, given, field);
  const n = bars.C.length, k = p.bars, r = new Uint8Array(n);
  const O = Float64Array.from(bars.O, num), H = Float64Array.from(bars.H, num), L = Float64Array.from(bars.L, num), C = Float64Array.from(bars.C, num);
  const minTicks = q.min_range_ticks as number, N = q.trend_length as number, trend = q.trend as string, up = p.trend === 'up';
  // the average body ending at each bar over body_avg_length bars, each window summed afresh (position independent)
  const avg = new Float64Array(n).fill(NaN), M = p.params.some(x => x.key === 'body_avg_length') ? q.body_avg_length as number : 0;
  if (M) for (let j = M - 1; j < n; j++) { let s = 0; for (let t = j - M + 1; t <= j; t++) s += Math.abs(C[t] - O[t]); avg[j] = s / M }
  const ok = new Uint8Array(n);
  for (let i = 0; i < n; i++) ok[i] = +patternBar(bars, i, minTicks);
  const trendAt = (j: number): boolean => {
    if (trend === 'none') return true;
    if (j < 0) return false;
    if (trend === 'change') { if (j - N < 0) return false; const a = C[j], b = C[j - N]; return up ? a > b : a < b }
    if (j - N + 1 < 0) return false;
    let s = 0;
    for (let t = j - N + 1; t <= j; t++) s += C[t];
    const x = N * C[j];
    return up ? x > s : x < s;                                                  // NaN anywhere compares false
  };
  const rules = rulesOf(p, q), ctx: Ctx = { O, H, L, C, avg, first: 0 };
  for (let i = Math.max(1, k - 1); i < n; i++) {
    const first = i - k + 1;
    let all = true;
    for (let t = first; t <= i && all; t++) if (!ok[t]) all = false;
    if (!all || !trendAt(first - 1)) continue;
    ctx.first = first;
    r[i] = +rules.every(f => f(ctx));
  }
  return r;
}

/** An event within N sessions: 1 on bar i when the signal is 1 on one of the bars i-within+1 .. i (within 1: on the
    bar itself). */
export function eventWithin(s: Signal, within: number): Signal {
  if (!(Number.isInteger(within) && within >= 1)) throw new ValidationError('INVALID_CONDITION', 'within', `within must be a whole number of at least 1 (right: 3; wrong: ${within}).`);
  const r = new Uint8Array(s.length);
  let last = -Infinity;
  for (let i = 0; i < s.length; i++) { if (s[i]) last = i; r[i] = +(i - last < within) }
  return r;
}

/* ---- plain text of a definition (the Screener's catalog formula) -------------------------------------------------- */

function exprText(e: Expr): string {
  if (typeof e === 'number') return String(e);
  if (typeof e === 'string') return e.slice(1);
  const [head, ...args] = e as [string, ...Expr[]];
  if ((PRIMITIVES as readonly string[]).includes(head)) return `${head}${args[0]}`;
  if (head === 'avg_body') return 'avg_body';
  const parts = args.map(a => Array.isArray(a) && ['+', '-'].includes(a[0] as string) ? `(${exprText(a)})` : exprText(a));
  if (head === 'abs') return `|${parts[0]}|`;
  if (head === 'ticks') return `ticks(${parts[0]}, ${parts[1]})`;
  return parts.join(head === '*' ? ' x ' : ` ${head} `);
}
/** The exact definition in words and rules: the guards, the trend and each rule as the registry writes it (candles
    numbered from the oldest, candle n the signal bar). */
export function candleFormula(id: string): string {
  const p = candlePattern(id), c = p.bars === 1 ? 'the candle' : `each of the ${p.bars} candles`;
  const rules = p.rules.map(r => `${r.when ? `[${Object.entries(r.when).map(([k, v]) => `${k} = ${v}`).join(', ')}] ` : ''}${exprText(r.lhs)} ${r.op} ${exprText(r.rhs)}`);
  return `${p.name} (${p.bars} candle${p.bars === 1 ? '' : 's'}, flagged on the last): ${c} traded (volume above 0, never a day without trades) and spans at least min_range_ticks IDX price ticks; `
    + `trend before candle 1 ${p.trend === 'down' ? 'down' : 'up'} (trend = average: close ${p.trend === 'down' ? 'below' : 'above'} its trend_length-session average; change: ${p.trend === 'down' ? 'below' : 'above'} the close trend_length sessions earlier; none: no test); `
    + `rules: ${rules.join('; ')}.`;
}
