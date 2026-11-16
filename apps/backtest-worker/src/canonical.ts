/* EXEC-BACKTEST-REVAMP P2 (user K7 a, 2026-11-15: "normalkan (bawaan diisi, terjemahan kanonik) untuk hash baru"; ERRORS
   M452): the form of a request its hashes are taken over (variant hash = one trial, lineage key, request hash), so the
   same strategy written two ways is one trial. The run itself reads the request as sent (the numbers are the same:
   every filled-in value is the default the run applies anyway); only the hashes read this form.
   - every condition's parameters complete: an indicator condition's with the registry defaults (registry.ts
     resolveParams), a price-action condition's with its defaults and default operator (conditions.ts PRICE_ACTION), a
     condition in the Screener's grammar checked and completed by the Screener's own validation (grammar.ts checkTest);
   - a grammar condition that says exactly what an indicator condition says is written as that indicator condition
     (the canonical translation): one indicator with one parameter set on every side, the bar field the indicator's
     "price" means, operators gt / lt / crosses_above / crosses_below, a constant only on the right; its window is the
     one the entry rule applies to an indicator condition (window_bars W: an EVENT within W for a cross, a window
     "ever" over W sessions for gt / lt, the test itself when W is 1; an exit reads the bar itself). Price on the right
     is the same comparison turned over (x gt price = price lt x), as the Screener reads it;
   - every other condition as sent.
   An indicator condition written with its parameters left out (params {}) therefore hashes as the same condition with
   its defaults written: its variant hash and request hash change once (K7 a), its lineage key does not (parameters
   are not part of the strategy shape, hash.ts lineageShape). */
import type { BacktestRequest, Condition, IndicatorCondition, TestCondition } from '../../edge-bff/backtest/src/core/contract.ts';
import { PRICE_ACTION, comparedOutput } from '../../edge-bff/backtest/src/core/conditions.ts';
import { canonicalJson, canonicalRequest } from '../../edge-bff/backtest/src/core/hash.ts';
import { BY_ID, resolveParams } from '../../edge-bff/backtest/src/core/registry.ts';
import { checkTest } from './grammar.ts';

type Obj = Record<string, unknown>;
const isObj = (x: unknown): x is Obj => !!x && typeof x === 'object' && !Array.isArray(x);
const LEGACY_OPS = new Set(['gt', 'lt', 'crosses_above', 'crosses_below']);
const TURNED: Record<string, IndicatorCondition['op']> = { gt: 'lt', lt: 'gt', crosses_above: 'crosses_below', crosses_below: 'crosses_above' };

/** The comparison inside a grammar test the entry or exit window W reads as an indicator condition's, or null. */
function comparison(t: Obj, W: number): { lhs: unknown; op: string; rhs: unknown } | null {
  if (t.kind === 'event') {
    const s = t.signal as Obj;
    return t.within === W && isObj(s) && (s.op === 'crosses_above' || s.op === 'crosses_below') && 'lhs' in s ? { lhs: s.lhs, op: s.op as string, rhs: s.rhs } : null;
  }
  const level = (x: Obj) => x.kind === 'value' ? (x.op === 'gt' || x.op === 'lt' ? { lhs: x.metric, op: x.op, rhs: { value: x.value } } : null)
    : x.kind === 'state' && (x.op === 'gt' || x.op === 'lt') && 'lhs' in x ? { lhs: x.lhs, op: x.op as string, rhs: x.rhs } : null;
  if (W === 1) return level(t);
  return t.kind === 'window' && t.mode === 'ever' && t.length === W && isObj(t.test) ? level(t.test as Obj) : null;
}

/** The indicator condition a grammar test says exactly, or null (see the header). */
export function asIndicatorCondition(c: TestCondition, test: Obj, W: number): IndicatorCondition | null {
  const k = comparison(test, W);
  if (!k || !LEGACY_OPS.has(k.op)) return null;
  const ind = [k.lhs, k.rhs].filter(s => isObj(s) && s.kind === 'indicator') as Obj[];
  if (!ind.length || ind.some(s => s.indicator !== ind[0].indicator || canonicalJson(s.params ?? {}) !== canonicalJson(ind[0].params ?? {}))) return null;
  const r = BY_ID[ind[0].indicator as string];
  if (!r) return null;
  let params;
  try { params = resolveParams(r, ind[0].params) } catch { return null }
  const side = (s: unknown): IndicatorCondition['lhs'] | IndicatorCondition['rhs'] | 'price' | null => {
    if (!isObj(s)) return null;
    if (s.kind === 'indicator') return r.outputs.includes(s.output as string) ? { type: 'output', output: s.output as string } : null;
    if (s.kind === 'price') return s.field === r.price_input ? 'price' : null;
    if (!('kind' in s) && typeof s.value === 'number' && Object.keys(s).length === 1) return { type: 'value', value: s.value };
    return null;
  };
  let lhs = side(k.lhs), rhs = side(k.rhs), op = k.op as IndicatorCondition['op'];
  if (!lhs || !rhs) return null;
  if (rhs === 'price' && lhs !== 'price' && (lhs as { type: string }).type === 'output') { [lhs, rhs] = ['price', lhs]; op = TURNED[op] }
  const L = lhs === 'price' ? { type: 'price' as const } : lhs, R = rhs;
  if (L.type === 'value' || R === 'price' || (L.type === 'price' && R.type === 'value')) return null;
  return { id: c.id, ...(c.enabled === false ? { enabled: false } : {}), kind: 'indicator', indicator: r.id, params, lhs: L as IndicatorCondition['lhs'], op, rhs: R as IndicatorCondition['rhs'] };
}

/** An indicator condition that compares the price with an output the core reads one bar late (conditions.ts
    comparedOutput, compare-lag.json: K5 a, ERRORS M451, the Donchian bands) carries `compare_lag: 1` in its hash form:
    its trades changed when the lag was introduced, so a run after it is another trial than a run before it under the
    same request (Stage C F10, ERRORS M458). Derived from the core's own rule, so an output the probe marks later is
    covered; its lineage is unchanged (hash.ts conditionShape reads no such field). */
function withCompareLag(c: IndicatorCondition): IndicatorCondition {
  const r = BY_ID[c.indicator];
  if (!r || c.lhs.type !== 'price' || c.rhs.type !== 'output') return c;
  const probe: number[] = [1, 2];
  return comparedOutput(r.id, c.rhs.output as string, r.price_input, c.op, probe) !== probe ? { ...c, compare_lag: 1 } as IndicatorCondition : c;
}

/** One condition in its hash form. `W` is the window a grammar condition is translated at (entry: entryWindow; exit: 1,
    an exit reads the bar itself), null for none. A disabled condition is left as sent (no hash reads it). */
export function canonicalCondition(c: Condition, W: number | null, field: string): Condition {
  if (c.enabled === false) return c;
  if (c.kind === 'indicator') {
    const r = BY_ID[c.indicator];
    return r ? withCompareLag({ ...c, params: resolveParams(r, c.params, `${field}.params`) }) : c;
  }
  if (c.kind === 'price_action') {
    const pa = PRICE_ACTION[c.type];
    return pa ? { ...c, params: { ...pa.params, ...(c.params || {}) }, op: c.op ?? pa.ops[0] } : c;
  }
  if (c.kind === 'test') {
    const test = checkTest(c, field) as unknown as Obj;
    const k = W !== null ? asIndicatorCondition(c, test, W) : null;
    return k ? withCompareLag(k) : { ...c, test };
  }
  return c;
}

/** The window a grammar test reads by itself, as an indicator condition reads the entry rule's window: an EVENT's
    within, an "ever" window's length, 1 for a value or state test; null for another form. */
function ownWindow(t: Obj): number | null {
  if (t.kind === 'event') return Number.isInteger(t.within) ? t.within as number : null;
  if (t.kind === 'window') return t.mode === 'ever' && Number.isInteger(t.length) ? t.length as number : null;
  return t.kind === 'value' || t.kind === 'state' ? 1 : null;
}

/** The window the entry's grammar conditions are translated at. With an enabled indicator, price-action or flow
    condition, the entry rule's window_bars (it reads them, and a grammar test equals an indicator condition only at that
    window). With grammar conditions only, window_bars reads none of them (conditions.ts combineEntry gives each its own
    window), so it must not decide the hash form (Stage C F4, ERRORS M458: "RSI crosses above 50 within 3" had one
    lineage with window_bars 3 and another with any other window_bars): their common own window when every one of them
    is an indicator condition at it (the list is then the indicator conditions under that window), otherwise none
    (null: no translation). */
function entryWindow(q: BacktestRequest): number | null {
  const on = q.entry.conditions.map((c, k) => [c, k] as const).filter(([c]) => c.enabled !== false);
  if (!on.length || on.some(([c]) => c.kind !== 'test')) return q.entry.window_bars;
  const tests = on.map(([c, k]) => checkTest(c, `entry.conditions[${k}]`) as unknown as Obj), own = new Set(tests.map(ownWindow));
  const w = own.size === 1 ? [...own][0] : null;
  return w !== null && on.every(([c], j) => asIndicatorCondition(c as TestCondition, tests[j], w)) ? w : null;
}

/** The request in the form its variant and request hashes are taken over (canonicalRequest first: the picked stocks in
    ticker order). Only for a request the worker's validation accepted. */
export function hashForm(request: BacktestRequest): BacktestRequest {
  const q = canonicalRequest(request), W = entryWindow(q);
  return {
    ...q,
    entry: { ...q.entry, ...(W !== null ? { window_bars: W } : {}), conditions: q.entry.conditions.map((c, k) => canonicalCondition(c, W, `entry.conditions[${k}]`)) },
    exit: { ...q.exit, signals: { ...q.exit.signals, conditions: q.exit.signals.conditions.map((c, k) => canonicalCondition(c, 1, `exit.signals.conditions[${k}]`)) } },
  };
}

/** The request in the form its lineage key is taken over (hash.ts lineageShape, which reads no number): the hash form
    with each grammar condition that is an indicator condition at its own window written as that condition, whatever
    window_bars is, so a strategy keeps one line however its windows are set (Stage C F4). */
export function lineageForm(request: BacktestRequest): BacktestRequest {
  const q = hashForm(request);
  const own = (c: Condition, field: string): Condition => {
    if (c.kind !== 'test' || c.enabled === false) return c;
    const t = (c as TestCondition).test as unknown as Obj, w = ownWindow(t);
    return (w !== null ? asIndicatorCondition(c as TestCondition, t, w) : null) ?? c;
  };
  return {
    ...q,
    entry: { ...q.entry, conditions: q.entry.conditions.map((c, k) => own(c, `entry.conditions[${k}]`)) },
    exit: { ...q.exit, signals: { ...q.exit.signals, conditions: q.exit.signals.conditions.map((c, k) => own(c, `exit.signals.conditions[${k}]`)) } },
  };
}
