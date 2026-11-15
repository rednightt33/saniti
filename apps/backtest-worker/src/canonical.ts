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
import { PRICE_ACTION } from '../../edge-bff/backtest/src/core/conditions.ts';
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

/** One condition in its hash form. `W` is the window the rule applies to an indicator condition (entry: window_bars;
    exit: 1). A disabled condition is left as sent (no hash reads it). */
export function canonicalCondition(c: Condition, W: number, field: string): Condition {
  if (c.enabled === false) return c;
  if (c.kind === 'indicator') {
    const r = BY_ID[c.indicator];
    return r ? { ...c, params: resolveParams(r, c.params, `${field}.params`) } : c;
  }
  if (c.kind === 'price_action') {
    const pa = PRICE_ACTION[c.type];
    return pa ? { ...c, params: { ...pa.params, ...(c.params || {}) }, op: c.op ?? pa.ops[0] } : c;
  }
  if (c.kind === 'test') {
    const test = checkTest(c, field) as unknown as Obj;
    return asIndicatorCondition(c, test, W) ?? { ...c, test };
  }
  return c;
}

/** The request in the form its hashes are taken over (canonicalRequest first: the picked stocks in ticker order). Only
    for a request the worker's validation accepted. */
export function hashForm(request: BacktestRequest): BacktestRequest {
  const q = canonicalRequest(request), W = q.entry.window_bars;
  return {
    ...q,
    entry: { ...q.entry, conditions: q.entry.conditions.map((c, k) => canonicalCondition(c, W, `entry.conditions[${k}]`)) },
    exit: { ...q.exit, signals: { ...q.exit.signals, conditions: q.exit.signals.conditions.map((c, k) => canonicalCondition(c, 1, `exit.signals.conditions[${k}]`)) } },
  };
}
