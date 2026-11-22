/* EXEC-BACKTEST-REVAMP P4: a condition in the grammar that reads a point-in-time Flow indicator (pit/spec.ts). The
   Screener's validation and binding do not know these (the Screener has its own window versions of FL18-FL23, FL44,
   FL45 under other parameters, and no FL51), so this module checks and evaluates such a test itself, with the
   Screener's own per-bar rules so the meaning stays one language: valuePasses for a VALUE test, compareAt (the
   Backtest core's compare) for STATE and EVENT, EVENT within as a rolling window, the window test as the Screener
   counts it, bar 0 never true.
   Forms: VALUE {metric: D, op, value[, value2]}; STATE {lhs, op gt|lt, rhs}; EVENT {signal: {lhs, op crosses_above |
   crosses_below, rhs}, within}; window {mode, length[, count], test} over one of them. A side is a point-in-time
   reference, a constant {value} (on the right), or any other reference of the grammar (the Screener resolves it). A
   point-in-time reference inside a transform is refused (not available yet). Units: a price level is compared with a
   price level (the close, a moving average, another broker price) or a constant; a percentage or an amount with a
   constant or the same unit; cohort_changed (0/1) in a VALUE test. */
import { VALUE_OPS, WINDOW_MODES } from '../../../edge-bff/screener/src/core/contract.ts';
import { compareAt, valuePasses, viewOfSeries } from '../../../edge-bff/screener/src/core/evaluate.ts';
import type { Operand } from '../../../edge-bff/screener/src/core/evaluate.ts';
import { ValidationError } from '../../../edge-bff/backtest/src/core/registry.ts';
import { checkDRef, isD } from './spec.ts';
import type { DRef, Unit } from './spec.ts';

type Obj = Record<string, unknown>;
const isObj = (x: unknown): x is Obj => !!x && typeof x === 'object' && !Array.isArray(x);
const bad = (code: string, field: string, message: string): never => { throw new ValidationError(code, field, message) };
const isDRef = (x: unknown): x is Obj => isObj(x) && x.kind === 'flow' && isD(x.metric);
const isConst = (x: unknown): x is { value: number } => isObj(x) && !('kind' in x) && typeof x.value === 'number' && Number.isFinite(x.value) && Object.keys(x).length === 1;

/** Whether a test reads a point-in-time Flow indicator anywhere (a walk with its own list, never calling itself: a request
    nested thousands of levels deep is read like a flat one; 3f W2, test-out wf_c72ae04c-a73). */
export function hasD(x: unknown): boolean {
  const todo: unknown[] = [x];
  while (todo.length) {
    const v = todo.pop();
    if (Array.isArray(v)) { for (const w of v) todo.push(w); continue }      // a loop: spreading a long list overflows too
    if (!isObj(v)) continue;
    if (isDRef(v)) return true;
    for (const w of Object.values(v)) todo.push(w);
  }
  return false;
}

/** What the checks need to know of a side that is not a point-in-time reference (the Screener resolves it). */
export interface OtherSide { unit: string | null; comparableWith: string | null }
const unitOf = (s: OtherSide): Unit | 'other' => s.comparableWith === 'close' || s.unit === 'price' ? 'price' : s.unit === 'percent' || s.unit === '%' ? 'pct' : 'other';

/** The test checked and completed (its point-in-time references with every parameter), or the refusal naming the field. */
export function checkDTest(t: unknown, field: string, other: (ref: unknown, field: string) => OtherSide, withinMax: number): Obj {
  if (!isObj(t)) bad('INVALID_CONDITION', field, `${field} must be a test object.`);
  const side = (s: unknown, f: string, right: boolean): { v: unknown; unit: Unit | 'other' | 'const' } => {
    if (isDRef(s)) { const d = checkDRef(s, f); return { v: { kind: 'flow', metric: d.metric, output: d.output, params: d.params }, unit: d.unit } }
    if (isConst(s)) { if (!right) bad('INVALID_CONDITION', f, `${f}: a constant goes on the right of a comparison (right: {"lhs": <series>, "rhs": {"value": 5}}).`); return { v: s, unit: 'const' } }
    if (!isObj(s) || typeof s.kind !== 'string') bad('INVALID_CONDITION', f, `${f} must be a reference or, on the right, a constant {"value": n}.`);
    if (hasD(s)) bad('CONDITION_UNAVAILABLE', f, `${f}: a point-in-time Flow indicator inside a transform or pattern is not available in a backtest yet; compare it directly (right: FL45 above 5; wrong: the z-score of FL45).`);
    return { v: s, unit: unitOf(other(s, f)) };
  };
  const fits = (a: { unit: string }, b: { unit: string }, f: string) => {
    if (b.unit === 'const' || a.unit === b.unit) return;
    if (a.unit === 'flag' || b.unit === 'flag') bad('INVALID_CONDITION', f, `${f}: cohort_changed is 0 or 1; test it in a VALUE test (right: cohort_changed gt 0).`);
    bad('INVALID_CONDITION', f, `${f}: a comparison of two series needs the same unit, and these are ${a.unit} and ${b.unit} (right: close against FL18, both price levels; wrong: FL45, a percentage, against the close).`);
  };
  const k = t.kind;
  if (k === 'value') {
    for (const x of Object.keys(t)) if (!['kind', 'metric', 'op', 'value', 'value2'].includes(x)) bad('INVALID_CONDITION', `${field}.${x}`, `${field}.${x} is not a field of a value test.`);
    if (!isDRef(t.metric)) bad('INVALID_CONDITION', `${field}.metric`, `${field}.metric must be a point-in-time Flow reference here.`);
    if (!(VALUE_OPS as readonly unknown[]).includes(t.op)) bad('INVALID_CONDITION', `${field}.op`, `${field}.op must be one of ${VALUE_OPS.join(', ')}.`);
    if (typeof t.value !== 'number' || !Number.isFinite(t.value)) bad('INVALID_CONDITION', `${field}.value`, `${field}.value must be a number.`);
    const two = t.op === 'between' || t.op === 'outside';
    if (two && !(typeof t.value2 === 'number' && Number.isFinite(t.value2) && t.value2 >= (t.value as number)))
      bad('INVALID_CONDITION', `${field}.value2`, `${field}.value2 must be a number of at least the lower value (${t.value}) for ${t.op}.`);
    if (!two && t.value2 !== undefined) bad('INVALID_CONDITION', `${field}.value2`, `${field}.value2 is used only with between and outside; remove it.`);
    return { kind: 'value', metric: side(t.metric, `${field}.metric`, false).v, op: t.op, value: t.value, ...(two ? { value2: t.value2 } : {}) };
  }
  if (k === 'state' || k === 'event') {
    const sig = (k === 'state' ? t : t.signal) as Obj, sf = k === 'state' ? field : `${field}.signal`;
    if (!isObj(sig)) bad('INVALID_CONDITION', sf, `${sf} must be a comparison {lhs, op, rhs}.`);
    const ops = k === 'state' ? ['gt', 'lt'] : ['crosses_above', 'crosses_below'];
    if (!ops.includes(sig.op as string)) bad('INVALID_CONDITION', `${sf}.op`, `${sf}.op must be one of ${ops.join(', ')}.`);
    const L = side(sig.lhs, `${sf}.lhs`, false), R = side(sig.rhs, `${sf}.rhs`, true);
    fits(L, R, `${sf}.rhs`);
    const cmp = { lhs: L.v, op: sig.op, rhs: R.v };
    if (k === 'state') return { kind: 'state', ...cmp };
    const w = t.within;
    if (!Number.isInteger(w) || (w as number) < 1 || (w as number) > withinMax) bad('INVALID_CONDITION', `${field}.within`, `${field}.within must be a whole number of sessions from 1 to ${withinMax}.`);
    return { kind: 'event', signal: cmp, within: w };
  }
  if (k === 'window') {
    if (!(WINDOW_MODES as readonly unknown[]).includes(t.mode)) bad('INVALID_CONDITION', `${field}.mode`, `${field}.mode must be one of ${WINDOW_MODES.join(', ')}.`);
    if (!Number.isInteger(t.length) || (t.length as number) < 1 || (t.length as number) > withinMax) bad('INVALID_CONDITION', `${field}.length`, `${field}.length must be a whole number of sessions from 1 to ${withinMax}.`);
    if (t.mode === 'at_least' && !(Number.isInteger(t.count) && (t.count as number) >= 1 && (t.count as number) <= (t.length as number)))
      bad('INVALID_CONDITION', `${field}.count`, `${field}.count must be a whole number from 1 to the window's length (${t.length}).`);
    // refused before the inner test is checked, so a window of a window of ... thousands deep is not walked (3f W2)
    if (isObj(t.test) && t.test.kind === 'window') bad('INVALID_CONDITION', `${field}.test`, `${field}.test: a window holds a value, state or event test, not another window.`);
    const inner = checkDTest(t.test, `${field}.test`, other, withinMax);
    return { kind: 'window', mode: t.mode, length: t.length, ...(t.mode === 'at_least' ? { count: t.count } : {}), test: inner };
  }
  return bad('INVALID_CONDITION', `${field}.kind`, `${field}.kind must be value, state, event or window.`);
}

/** The point-in-time references of a checked test, with their field. */
export function dRefsOf(t: Obj, field: string, out: { ref: DRef; field: string }[] = []): { ref: DRef; field: string }[] {
  const at = (s: unknown, f: string) => { if (isDRef(s)) out.push({ ref: s as unknown as DRef, field: f }) };
  if (t.kind === 'value') at(t.metric, `${field}.metric`);
  else if (t.kind === 'state') { at(t.lhs, `${field}.lhs`); at(t.rhs, `${field}.rhs`) }
  else if (t.kind === 'event') { const s = t.signal as Obj; at(s.lhs, `${field}.signal.lhs`); at(s.rhs, `${field}.signal.rhs`) }
  else if (t.kind === 'window') dRefsOf(t.test as Obj, `${field}.test`, out);
  return out;
}

/** The checked test on every bar. `series(side, field)` gives a side's series (a point-in-time or another reference). */
export function dSignal(t: Obj, field: string, n: number, series: (side: unknown, field: string) => ArrayLike<number | null | undefined>): Uint8Array {
  const op = (s: unknown, f: string): Operand => isConst(s) ? s.value : viewOfSeries(series(s, f));
  if (t.kind === 'window') {
    const p = dSignal(t.test as Obj, `${field}.test`, n, series), out = new Uint8Array(n), length = t.length as number, count = (t.count as number) ?? 1;
    let sum = 0, run = 0;
    for (let i = 0; i < n; i++) {
      sum += p[i]; if (i >= length) sum -= p[i - length];
      run = p[i] ? run + 1 : 0;
      out[i] = +(t.mode === 'ever' ? sum >= 1 : t.mode === 'at_least' ? sum >= count : run >= length);
    }
    if (n) out[0] = 0;
    return out;
  }
  const raw = new Uint8Array(n);
  if (t.kind === 'value') {
    const v = viewOfSeries(series(t.metric, `${field}.metric`));
    for (let i = 1; i < n; i++) { const x = v.get(i); raw[i] = +(Number.isFinite(x) && valuePasses(x, t as never)) }
    return raw;
  }
  const s = (t.kind === 'state' ? t : t.signal) as Obj, sf = t.kind === 'state' ? field : `${field}.signal`;
  const L = op(s.lhs, `${sf}.lhs`), R = op(s.rhs, `${sf}.rhs`);
  for (let i = 1; i < n; i++) raw[i] = +compareAt(L, s.op as never, R, i);
  if (t.kind === 'state') return raw;
  const w = t.within as number, out = new Uint8Array(n);
  for (let i = 0, lastOn = -1e9; i < n; i++) { if (raw[i]) lastOn = i; out[i] = +(i - lastOn < w) }
  if (n) out[0] = 0;
  return out;
}
