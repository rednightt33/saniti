/* The Terminal's 48 flow indicators as Screener series (EXEC-SCREENER-FLOW-CANDLES P5a; the contract is
   verification/screener/P5_FLOW.md sections 1 and 2; decisions in EXEC.md: G1 the registry's Regular board, G2 the
   stock's own price bars, K1 the 60-session broker window, K7 "=" and "!=" only on D, F and B outputs).

   One formula source: every value is apps/edge-bff/terminal/src/calc/flow.ts computeFlow(id, ctx, params) called as the
   Terminal calls it, on a FlowRows built by flowRows-equivalent code (brokerFlowRows) from the broker rows the worker
   holds (P4: ThreadSnapshot.brokerRows), so a value equals the Terminal's for the same rows. Nothing here computes a
   flow figure itself.
   - Sessions (G2): the candles are the stock's own price bars whose dates fall inside the loaded broker window; each
     broker row goes to its candle by date, a row on a date without a price bar is not counted (as the Terminal's
     flowRows). The P4 files code investor types Domestic=0, Foreign=1 and boards Regular, Nego, Tunai; flow.ts reads
     INVESTORS Foreign=0, Domestic=1 and BOARDS Regular, Nego, Cash: the codes are converted by name through flow.ts's own
     investorIndex and boardIndex (Tunai = Cash).
   - Context: close and volume of the same bars, dates the bars' dates, the broker classification of the reference file
     `brokers` (IDX_Broker_Profile, the file the Terminal reads; FL34), insider none (FL31 needs data the Screener does
     not hold: REQUIRES_DATA).
   - Parameters (resolveFlowParams): the registry's (flowRegistry.json through the generated screener-registry.json
     `flows`), each checked against its kind, range and options; a parameter left out takes flowDefaults' value, except a
     built-in percentile baseline (FL08, FL09, FL21, FL37, FL47) that does not fit the loaded window: it is capped to the
     window less the indicator's own window (K1, derived from the depth, never listed); the kinds that only draw
     (levels, button, fixed) and a select or switch the generator finds changes no value (display_only, the Terminal's
     "Plot") are refused, and computeFlow takes their default.
   - Output: one series the registry names and computeFlow gives at these parameters (a sided indicator draws its sell
     line only with side sell or both; FL23 draws one line per broker: `lines` reads the line of the one broker named,
     `total` needs total true).
   - Depth (K1): the sessions an indicator reads back at its parameters, derived by running computeFlow on a synthetic
     context with broker data on every candle (flowDepth: the first candle with a value, plus one); the operators' N,
     length and within are added by their callers (transforms.ts, condition.ts), and the sum may not exceed the loaded
     window's sessions (LIMIT_EXCEEDED broker_depth).
   - Series: the output aligned to the stock's bars (null outside the window), so every operator applies to it as to an
     indicator; one computeFlow per (ticker, id, parameters) through the caller's memo (TickerFlow.memo, the thread's
     per-snapshot memo), the outputs of one call shared.
   P5b (P5_FLOW.md section 3): the Screener's versions (FL18-FL20, FL44, FL45 with the anchor N sessions back; FL23's
   Broker Inventory series a, b, c and the count of holders that moved), FL34's point-in-time guard and the Screener's
   own entries (fnet; ksei_net REQUIRES_DATA) are computed by flowscreener.ts on top of the same computeFlow (computeEntry
   dispatches on the entry's `compute`).
   Worker-side module (imports the Terminal's flow module); the page reads the entries from GET /catalog. */
import { boardIndex, computeFlow, flowDefaults, investorIndex } from '../../../terminal/src/calc/flow.ts';
import type { FlowContext, FlowOut, FlowRows, Num } from '../../../terminal/src/calc/flow.ts';
import { canonicalJson } from '../../../backtest/src/core/hash.ts';
import { isIsoDate } from '../../../backtest/src/core/signals.ts';
import type { FlowParamValue, FlowRef, MetricRef } from './contract.ts';
import { ScreenerError } from './errors.ts';
import { FLOW_REASONS } from './catalog.ts';
import { anchoredAt, anchoredLazy, anchoredSeries, foreignNet, inventory } from './flowscreener.ts';
import type { FlowCall, InventorySetup } from './flowscreener.ts';
import { SCREENER_REGISTRY } from './registry.ts';
import { probeContext, probeLength } from './flowprobe.ts';
import type { FlowKindSpec, FlowRegistryEntry, FlowRegistryParam } from './registry.ts';
import kindsDoc from './flow-kinds.json' with { type: 'json' };
import type { ResolvedSeries, TickerBars, TickerCalc } from './metrics.ts';

/* ---- the entries ------------------------------------------------------------------------------------------------ */

export const FLOWS: readonly FlowRegistryEntry[] = SCREENER_REGISTRY.flows;
export const FLOW_BY_ID: Readonly<Record<string, FlowRegistryEntry>> = Object.fromEntries(FLOWS.map(f => [f.id, f]));
/** K1 (user 2026-11-07): the broker window the publisher writes (P4 BROKER_DAY_SESSIONS), the window a left-out
    baseline is capped to when the caller names no loaded window (flow-kinds.json window_sessions). */
export const FLOW_DESIGN_SESSIONS: number = (kindsDoc as { window_sessions: number }).window_sessions;

/** The loaded broker window a binding is checked against (the worker's data.broker_window and its reference file):
    its sessions and dates, whether every day of it is loaded, and whether the broker classification is published. */
export interface FlowBindContext { sessions: number; first: string | null; last: string | null; complete: boolean; classification: boolean }

/** The flow entry of a reference, or INVALID_CONDITION with the 48 ids. */
export function flowEntry(id: unknown, field: string): FlowRegistryEntry {
  const e = typeof id === 'string' && Object.prototype.hasOwnProperty.call(FLOW_BY_ID, id) ? FLOW_BY_ID[id] : undefined;
  if (!e) throw new ScreenerError('INVALID_CONDITION', `${field}: ${JSON.stringify(id)} is not a flow indicator; use one of ${FLOWS.map(f => f.id).join(', ')}.`, field, { allowed: FLOWS.map(f => f.id) });
  return e;
}
/** The value of a select option or multi option of the registry ([value, label] or value). */
const optionValue = (o: string | [string, string]): string => Array.isArray(o) ? o[0] : o;
/** An output's kind and unit at resolved parameters (flow-kinds.json through the entry: a letter, {kind, unit}, or by a
    select parameter's value, which may again follow another select parameter: FL23's value by series, then by unit). */
export function outputKind(e: FlowRegistryEntry, output: string, params: Record<string, FlowParamValue>): { kind: string; unit: string } {
  const o = e.outputs.find(x => x.key === output);
  let s: FlowKindSpec | undefined = o?.kind;
  while (s && typeof s === 'object' && 'by' in s) s = (s as Record<string, unknown>)[String(params[(s as { by: string }).by])] as FlowKindSpec | undefined;
  if (typeof s === 'string') return { kind: s, unit: e.unit };
  if (s && typeof s === 'object' && 'kind' in s) return { kind: String(s.kind), unit: String((s as { unit: string }).unit) };
  throw new RangeError(`flow: ${e.id}.${output} has no kind at ${JSON.stringify(params)}`);
}
/** The parameters a condition takes (the kinds that only draw are not among them). */
const conditionParams = (e: FlowRegistryEntry): FlowRegistryParam[] => e.params.filter(p => p.condition && p.default !== undefined);
/** A broker list given as the registry's own default token (FL23 'auto_c', FL34 'class:Institutional-heavy'): the
    Terminal resolves it from the rows or the classification (flow.ts resolveBrokers). */
const isToken = (v: unknown, p: FlowRegistryParam) => typeof v === 'string' && v === p.default;
const BROKER = /^[A-Z0-9]{1,6}$/;

/* ---- parameters ---------------------------------------------------------------------------------------------------- */

const range = (p: FlowRegistryParam, whole: boolean) => `${whole ? 'a whole number' : 'a number'}${p.min !== undefined && p.min !== null ? ` from ${p.min}` : ''}${p.max !== undefined && p.max !== null ? ` to ${p.max}` : ''}`;
/** One parameter's value checked against the registry (kind, range, options); the refusal names the field, the rule and
    a right and a wrong value (AGENTS.md "Gates and evidence"). */
function checkParam(e: FlowRegistryEntry, p: FlowRegistryParam, v: unknown, f: string): FlowParamValue {
  const bad = (rule: string, details?: Record<string, unknown>) => new ScreenerError('INVALID_CONDITION', `${f}: ${e.id} ${e.name} "${p.label}" ${rule}.`, f, details);
  switch (p.kind) {
    case 'int': case 'num': {
      const whole = p.kind === 'int';
      if (typeof v !== 'number' || !Number.isFinite(v)) throw bad(`must be ${range(p, whole)} (right: ${p.default}; wrong: "${p.default}")`);
      const lo = p.min ?? undefined, hi = p.max ?? undefined;
      if ((whole && !Number.isInteger(v)) || (lo !== undefined && v < lo) || (hi !== undefined && v > hi))
        throw new ScreenerError('PARAM_OUT_OF_RANGE', `${f}: ${e.id} ${e.name} "${p.label}" must be ${range(p, whole)} (right: ${p.default}; wrong: ${hi !== undefined ? hi + 1 : (lo ?? 0) - 1}).`, f,
          { field: f, ...(lo !== undefined ? { min: lo } : {}), ...(hi !== undefined ? { max: hi } : {}), integer: whole });
      return v;
    }
    case 'bool':
      if (typeof v !== 'boolean') throw bad('must be true or false', { allowed: [true, false] });
      return v;
    case 'select': {
      const allowed = (p.options || []).map(optionValue);
      if (typeof v !== 'string' || !allowed.includes(v)) throw bad(`must be one of ${allowed.join(', ')} (right: ${JSON.stringify(p.default)}; wrong: "other")`, { allowed });
      return v;
    }
    case 'multi': {
      const allowed = (p.options || []).map(optionValue);
      if (!Array.isArray(v) || !v.length || v.some(x => typeof x !== 'string' || !allowed.includes(x)) || new Set(v).size !== v.length)
        throw bad(`is a list of at least one of ${allowed.join(', ')}, each once (right: ${JSON.stringify(p.default)}; wrong: [] or ${JSON.stringify([allowed[0], allowed[0]])})`, { allowed });
      return [...v] as string[];
    }
    case 'date':
      if (v !== 'view' && !(typeof v === 'string' && isIsoDate(v)))
        throw bad('is "view" (the first session of the loaded broker window) or a date YYYY-MM-DD inside that window (right: "view"; wrong: "last week")', { allowed: ['view'] });
      return v as string;
    case 'brokers': {
      if (isToken(v, p)) return v as string;
      const lo = p.min ?? 0, hi = p.max ?? undefined;
      if (!Array.isArray(v) || v.some(x => typeof x !== 'string' || !BROKER.test(x)) || new Set(v).size !== v.length || v.length < lo || (hi !== undefined && v.length > hi))
        throw bad(`is ${typeof p.default === 'string' ? `${JSON.stringify(p.default)} or ` : ''}a list of ${lo && hi !== undefined ? `${lo} to ${hi} ` : hi !== undefined ? `at most ${hi} ` : lo ? `at least ${lo} ` : ''}broker codes, each once (right: ["YP", "AK"]; wrong: ["yp", "YP", "YP"])`);
      return [...v] as string[];
    }
  }
  throw bad('only draws on the Terminal\'s chart (a reference line, a button or a fixed text); a condition does not take it');
}
/** The Terminal's "nothing chosen" rules (flowIndicators.ts emptyChoice, ratioRefusal): a scope of selected brokers
    with no broker named has no line, so it is refused naming the field; P5b: so are FL23's holders "Selected brokers"
    with none named (its other holders do not read the list). */
function emptyChoice(e: FlowRegistryEntry, params: Record<string, FlowParamValue>, field: string): void {
  for (const pre of ['', 'num_', 'den_']) {
    const brokers = params[`${pre}brokers`], scope = params[`${pre}scope`] ?? params[`${pre}holders`];
    if (Array.isArray(brokers) && !brokers.length && (scope === undefined || scope === 'selected') && e.params.some(p => p.key === `${pre}brokers`))
      throw new ScreenerError('INVALID_CONDITION', `${field}.params.${pre}brokers: ${e.id} ${e.name} reads the selected brokers, and none is named: name at least one broker, or choose another ${params[`${pre}holders`] !== undefined ? 'holders setting' : 'broker scope'} (right: ["YP"]; wrong: []).`, `${field}.params.${pre}brokers`);
  }
}

/** The parameters of a flow reference, checked and complete (normalized: every condition parameter stated, so a request
    that leaves a default out hashes as one that states it). A parameter left out takes the registry default (flow.ts
    flowDefaults; a screener parameter its own default, P5b), except `baseline` when the indicator at its default would read more sessions than `sessions` (the
    loaded window, FLOW_DESIGN_SESSIONS without one): it is lowered by the excess, never below its minimum (K1: "60
    dikurangi jendela"). An unknown key, a kind that only draws, or a value outside its rule is refused. */
export function resolveFlowParams(e: FlowRegistryEntry, given: unknown, field: string, sessions = FLOW_DESIGN_SESSIONS, output?: string): Record<string, FlowParamValue> {
  if (given !== undefined && (!given || typeof given !== 'object' || Array.isArray(given))) throw new ScreenerError('INVALID_CONDITION', `${field}.params must be an object of the indicator's parameters.`, `${field}.params`);
  const g = (given || {}) as Record<string, unknown>, specs = conditionParams(e), keys = specs.map(p => p.key);
  for (const k of Object.keys(g)) {
    const p = e.params.find(x => x.key === k);
    if (p && !p.condition) throw new ScreenerError('INVALID_CONDITION', `${field}.params.${k}: "${p.label}" of ${e.id} ${e.name} ${p.display_only ? 'only changes how the Terminal draws the indicator (each of its options gives the same values)' : 'only draws on the Terminal\'s chart (a reference line, a button or a fixed text)'}; a condition does not take it, so remove it (the parameters a condition takes: ${keys.join(', ')}; right: ${keys.length ? `{"${keys[0]}": ${JSON.stringify(conditionParams(e)[0].default)}}` : '{}'}; wrong: {"${k}": ...}).`, `${field}.params.${k}`, { allowed: keys });
    if (!p) throw new ScreenerError('INVALID_CONDITION', `${field}.params.${k}: not a parameter of ${e.id} ${e.name}; use only ${keys.join(', ')}.`, `${field}.params.${k}`, { allowed: keys });
  }
  const defaults = flowDefaults(e.id), out: Record<string, FlowParamValue> = {};
  for (const p of specs) out[p.key] = checkParam(e, p, Object.prototype.hasOwnProperty.call(g, p.key) ? g[p.key] : p.screener ? structuredClone(p.default) : defaults[p.key], `${field}.params.${p.key}`);
  emptyChoice(e, out, field);
  // K1: a built-in baseline left out is capped to the window less the indicator's own window (derived, flowDepth)
  const base = specs.find(p => p.key === 'baseline' && p.kind === 'int');
  if (base && !Object.prototype.hasOwnProperty.call(g, 'baseline')) {
    const o = output ?? e.default_output, d = indicatorDepth(e, o, out);
    if (d !== null && d > sessions) {
      const lowered = Math.max(base.min ?? 1, (out.baseline as number) - (d - sessions));
      if (lowered < (out.baseline as number)) out.baseline = lowered;
    }
  }
  return out;
}

/* ---- outputs -------------------------------------------------------------------------------------------------------- */

const EMPTY_ROWS = (N: number): FlowRows => ({ n: 0, N, t: new Int32Array(0), b: new Uint16Array(0), inv: new Uint8Array(0), brd: new Uint8Array(0),
  bv: new Float64Array(0), sv: new Float64Array(0), bl: new Float64Array(0), sl: new Float64Array(0), bf: new Float64Array(0), sf: new Float64Array(0),
  brokers: [], has: new Uint8Array(N) });
const outputMemo = new Map<string, string[]>();
/** The output keys computeFlow gives at these parameters (computed once on an empty context, as the Terminal's
    flowIndicators.ts probes an indicator): a sided indicator's lines follow its side. A screener version or entry (P5b)
    gives every output it names. */
export function producedOutputs(id: string, params: Record<string, FlowParamValue>): string[] {
  const e = FLOW_BY_ID[id];
  if (e && e.compute !== 'terminal') return e.outputs.map(o => o.key);
  const key = canonicalJson([id, params]);
  let keys = outputMemo.get(key);
  if (!keys) {
    const ones = [1];
    keys = Object.keys(computeFlow(id, { rows: EMPTY_ROWS(1), dates: ['2000-01-03'], close: ones, volume: ones, insider: [], classification: {} }, params));
    if (outputMemo.size > 4096) outputMemo.clear();
    outputMemo.set(key, keys);
  }
  return keys;
}
/** The series key of the output in computeFlow's answer, or the refusal naming the field: an output the entry does
    not name; a sided line the side does not draw; `total` without total. */
export function seriesKeyOf(e: FlowRegistryEntry, output: string, params: Record<string, FlowParamValue>, field: string): string {
  if (!e.outputs.some(o => o.key === output))
    throw new ScreenerError('INVALID_CONDITION', `${field}.output: ${JSON.stringify(output)} is not an output of ${e.id} ${e.name}; use one of ${e.outputs.map(o => o.key).join(', ')}.`, `${field}.output`, { allowed: e.outputs.map(o => o.key) });
  const produced = producedOutputs(e.id, params);
  if (!produced.includes(output)) {
    const side = e.params.find(p => p.key === 'side'), total = e.params.find(p => p.key === 'total' && p.kind === 'bool');
    const how = side && (output === 'buy' || output === 'sell') ? `set params.side to ${output} or both (it is ${JSON.stringify(params.side)}), or read output ${produced[0]}`
      : total && output === 'total' ? 'set params.total to true' : `read one of ${produced.join(', ')}`;
    const f = side ? `${field}.params.side` : total ? `${field}.params.total` : `${field}.output`;
    throw new ScreenerError('INVALID_CONDITION', `${f}: ${e.id} ${e.name} gives no ${output} series at these parameters: ${how} (right: output ${produced[0]}; wrong: output ${output}).`, f, { allowed: produced });
  }
  return output;
}

/* ---- depth (K1) ------------------------------------------------------------------------------------------------------ */

/* ---- computing an entry (P5b: the Screener's versions on top of computeFlow) ----------------------------------------- */

/** The Terminal's parameters of a screener version (its screener parameters left out): what computeFlow is given. */
const terminalParams = (e: FlowRegistryEntry, params: Record<string, FlowParamValue>): Record<string, FlowParamValue> =>
  Object.fromEntries(Object.entries(params).filter(([k]) => !e.params.find(p => p.key === k)?.screener));
/** Every output of a flow entry on a context, by the entry's `compute` (registry.ts FlowCompute): the Terminal's
    computeFlow (`call`: the caller's memo of it on the same context); the anchor N sessions back (flowscreener.ts
    anchoredSeries); the Screener's Broker Inventory (inventory, its FL23 calls through `call`); the foreign net (fnet,
    foreignNet). An entry whose data is not published (compute none) is never computed. */
export function computeEntry(e: FlowRegistryEntry, ctx: FlowContext, params: Record<string, FlowParamValue>, call: FlowCall = computeFlow): FlowOut {
  switch (e.compute) {
    case 'terminal': return call(e.id, ctx, params);
    case 'anchored': {
      const q = terminalParams(e, params), n = params.anchor_sessions as number;
      return Object.fromEntries(e.outputs.map(o => [o.key, anchoredSeries(e.id, ctx, q, n, o.key)]));
    }
    case 'inventory': return inventory(ctx, params as unknown as InventorySetup, call);
    case 'foreign_net': return { value: foreignNet(ctx.rows, params.boards as string[], params.window as number) };
  }
  throw new RangeError(`flow: ${e.id} is not computed (${e.requires ?? 'no'} data)`);
}
const depthMemo = new Map<string, number | null>();
/** The sessions the indicator reads back at these parameters (K1): on the probe context with broker data on every
    candle, the first candle of the output with a value, plus one (each(R, W, ...) gives W; a percentile over a
    baseline of a W-session series W + baseline; an anchored line 1, its anchor being the first candle). The probe is
    as long as any sum of the indicator's session parameters can reach. null when the output has no value on the probe
    at all (its emptiness is not a matter of history, e.g. a net of every broker over both investor types). An anchor
    date is probed at the first candle (its place in the window is checked by the caller). P5b: a screener version is
    probed the same way through computeEntry (the anchor N sessions back reads N + 1 sessions, FL23's lookback L). */
export function indicatorDepth(e: FlowRegistryEntry, output: string, params: Record<string, FlowParamValue>): number | null {
  if (e.compute === 'none') return null;                       // never computed (its data is not published)
  const p: Record<string, FlowParamValue> = { ...params };
  for (const q of e.params) if (q.kind === 'date' && typeof p[q.key] === 'string') p[q.key] = 'view';
  const key = canonicalJson([e.id, output, p]);
  const hit = depthMemo.get(key);
  if (hit !== undefined) return hit;
  const c = probeContext(probeLength(e.params, p)), s = computeEntry(e, c, p)[output];
  let first = -1;
  if (s) for (let t = 0; t < s.length; t++) if (typeof s[t] === 'number' && Number.isFinite(s[t] as number)) { first = t; break }
  const depth = first < 0 ? null : first + 1;
  if (depthMemo.size > 4096) depthMemo.clear();
  depthMemo.set(key, depth);
  return depth;
}
/** The refusal of a flow condition that reads more sessions than the loaded window holds (K1; OPERATORS.md section 5
    "Flow window beyond the broker data": the message names the indicator's sessions, the operators' and the window). */
export function depthRefusal(field: string, what: string, own: number, extra: number, sessions: number): ScreenerError {
  const total = own + extra;
  return new ScreenerError('LIMIT_EXCEEDED', `${field}: ${what} reads ${own} session${own === 1 ? '' : 's'} of broker data${extra ? ` and its operators ${extra} more, ${total} in all` : ''}; the Screener holds the last ${sessions} sessions of broker data, so a flow condition may read at most ${sessions} (the indicator's own window plus the operator's N, length or within). Use a shorter window or N (right: Bandar Balance · % window 10 with a percentile over 40 = 50 sessions; wrong: a percentile over 55 = 65).`,
    field, { limit: 'broker_depth', allowed: sessions, needed: total });
}

/* ---- the broker rows -> FlowRows (G2) ------------------------------------------------------------------------------- */

/** One ticker's broker rows as the worker's store gives them (P4: ThreadSnapshot.brokerRows, broker.ts BrokerRows):
    D indexes dates, B brokers, I investor_types (Domestic, Foreign), M boards (Regular, Nego, Tunai); a null bf or sf
    is NaN; ordered by date, then the file's order. */
export interface BrokerRowsLike {
  rows: number; dates: readonly string[]; brokers: readonly string[]; investor_types: readonly string[]; boards: readonly string[];
  D: ArrayLike<number>; B: ArrayLike<number>; I: ArrayLike<number>; M: ArrayLike<number>;
  BV: ArrayLike<number>; SV: ArrayLike<number>; BL: ArrayLike<number>; SL: ArrayLike<number>; BF: ArrayLike<number>; SF: ArrayLike<number>;
}
/** flow.ts flowRows on the store's columns, value for value (tests/core/flow.test.ts holds the two equal): the rows whose
    date is a candle, in their order; brokers the sorted codes of those rows; investor type and board by name through
    flow.ts investorIndex and boardIndex (Domestic -> 1, Foreign -> 0; Tunai -> Cash 2); values `|| 0`; a missing
    transaction count NaN; has[t] = 1 on a candle with a row. */
export function brokerFlowRows(v: BrokerRowsLike, candles: readonly string[]): FlowRows {
  const at = new Map(candles.map((d, k) => [d, k]));
  const day = Int32Array.from(v.dates, d => at.get(d) ?? -1), used = new Uint8Array(v.brokers.length);
  let n = 0;
  for (let k = 0; k < v.rows; k++) if (day[v.D[k]] >= 0) { n++; used[v.B[k]] = 1 }
  const brokers = [...new Set(v.brokers.filter((_, j) => used[j]))].sort();
  const id = new Map(brokers.map((c, j) => [c, j])), map = Int32Array.from(v.brokers, c => id.get(c) ?? -1);
  const inv = Uint8Array.from(v.investor_types, x => investorIndex(x)), brd = Uint8Array.from(v.boards, x => boardIndex(x));
  const N = candles.length;
  const R: FlowRows = { n, N, t: new Int32Array(n), b: new Uint16Array(n), inv: new Uint8Array(n), brd: new Uint8Array(n),
    bv: new Float64Array(n), sv: new Float64Array(n), bl: new Float64Array(n), sl: new Float64Array(n), bf: new Float64Array(n), sf: new Float64Array(n),
    brokers, has: new Uint8Array(N) };
  let j = 0;
  for (let k = 0; k < v.rows; k++) {
    const t = day[v.D[k]];
    if (t < 0) continue;
    R.t[j] = t; R.b[j] = map[v.B[k]]; R.inv[j] = inv[v.I[k]]; R.brd[j] = brd[v.M[k]];
    R.bv[j] = v.BV[k] || 0; R.sv[j] = v.SV[k] || 0; R.bl[j] = v.BL[k] || 0; R.sl[j] = v.SL[k] || 0;
    R.bf[j] = v.BF[k]; R.sf[j] = v.SF[k];
    R.has[t] = 1; j++;
  }
  return R;
}

/** A ticker's broker data as the series path reads it (metrics.ts TickerBars.flow; the worker's TickerView): the loaded
    window's first and last date, the ticker's rows in it, the broker classification, and the memo of computeFlow
    answers (the thread's, per snapshot) so one call per (ticker, id, parameters) serves every output and request. */
export interface TickerFlow {
  first: string | null; last: string | null;
  rows(): BrokerRowsLike | undefined;
  classification: Readonly<Record<string, string>>;
  memo?: { get(key: string): FlowOut | undefined; set(key: string, v: FlowOut): void };
}
/** The candles of a ticker inside the window: bars [lo, lo + N) (found by date, cheap), and the FlowContext on them
    (built on the first computeFlow the memo does not answer). */
interface Frame { lo: number; N: number; ctx?: FlowContext }
const frames = new WeakMap<object, Frame>();
function windowOf(t: TickerBars): Frame {
  const f = t.flow;
  if (!f) throw new RangeError(`flow: ${t.ticker} has no broker rows on this view (TickerBars.flow); a flow series is computed on the worker's snapshot`);
  let fr = frames.get(f);
  if (fr) return fr;
  // the bars from the first on or after the window's first date to the last on or before its last date
  const D = t.dates, bound = (x: string, upper: boolean) => { let a = 0, b = D.length; while (a < b) { const h = (a + b) >>> 1; if (upper ? D[h] <= x : D[h] < x) a = h + 1; else b = h } return a };
  const open = f.first === null || f.last === null, lo = open ? 0 : bound(f.first!, false), hi = open ? 0 : bound(f.last!, true);
  fr = { lo, N: Math.max(0, hi - lo) };
  frames.set(f, fr);
  return fr;
}
function contextOf(t: TickerBars): FlowContext {
  const fr = windowOf(t);
  if (fr.ctx) return fr.ctx;
  const { lo, N } = fr, dates = t.dates.slice(lo, lo + N) as string[];
  const num = (x: unknown): Num => typeof x === 'number' && Number.isFinite(x) ? x : null;
  const C = t.bars.C as ArrayLike<unknown>, V = t.bars.V as ArrayLike<unknown>;
  const close: Num[] = [], volume: Num[] = [];
  for (let i = lo; i < lo + N; i++) { close.push(num(C[i])); volume.push(num(V[i])) }
  const rows = N ? t.flow!.rows() : undefined;
  fr.ctx = { rows: rows ? brokerFlowRows(rows, dates) : EMPTY_ROWS(N), dates, close, volume, insider: [], classification: { ...t.flow!.classification } };
  return fr.ctx;
}
/** computeFlow on a ticker's window context through the memo (one call per ticker, id and parameters). */
const memoCall = (t: TickerBars): FlowCall => (id, ctx, params) => {
  const key = canonicalJson([t.ticker, id, params]);
  let out = t.flow!.memo?.get(key);
  if (!out) { out = computeFlow(id, ctx, params); t.flow!.memo?.set(key, out) }
  return out;
};
/** An anchored entry's value at one candle of a ticker's window (flowscreener.ts anchoredAt) through the memo, one
    entry per (ticker, indicator, parameters, output, candle): the full series and the lazy one share it. */
const anchoredAtMemo = (t: TickerBars, e: FlowRegistryEntry, params: Record<string, FlowParamValue>, output: string) => {
  const ctx = contextOf(t), q = terminalParams(e, params), n = params.anchor_sessions as number, memo = t.flow!.memo;
  return (s: number): Num => {
    const key = canonicalJson([t.ticker, e.id, params, output, s]), hit = memo?.get(key);
    if (hit) return hit.v[0];
    const v = anchoredAt(e.id, ctx, q, n, output, s);
    memo?.set(key, { v: [v] });
    return v;
  };
};
/** Every output of one entry on a ticker (the memo's answer when it has one; computeEntry; an anchored entry's
    candles through anchoredAtMemo). */
function flowOutOf(t: TickerBars, e: FlowRegistryEntry, params: Record<string, FlowParamValue>): { lo: number; out: FlowOut } {
  const fr = windowOf(t);
  if (e.compute === 'terminal') return { lo: fr.lo, out: memoCall(t)(e.id, contextOf(t), params) };
  const key = canonicalJson([t.ticker, e.id, params]);
  let out = t.flow!.memo?.get(key);
  if (!out) {
    out = e.compute === 'anchored' ? Object.fromEntries(e.outputs.map(o => { const at = anchoredAtMemo(t, e, params, o.key); return [o.key, Array.from({ length: windowOf(t).N }, (_, s) => at(s))] }))
      : computeEntry(e, contextOf(t), params, memoCall(t));
    t.flow!.memo?.set(key, out);
  }
  return { lo: fr.lo, out };
}
/** An anchored entry's output only where a condition reads it (flowscreener.ts anchoredLazy: the last `reach` + 1
    candles with broker data), through the same per-candle memo; not kept as a whole (its candles are). */
function lazyOutOf(t: TickerBars, e: FlowRegistryEntry, params: Record<string, FlowParamValue>, output: string, reach: number): { lo: number; s: Num[] } {
  return { lo: windowOf(t).lo, s: anchoredLazy(contextOf(t), params.anchor_sessions as number, reach, anchoredAtMemo(t, e, params, output)) };
}
/** FL34's point-in-time guard (P5b; old FL19, FLOW_MAP.md item 8): the broker classification is today's, so the value
    is kept only on the last date of the loaded window and missing on every earlier candle. */
function currentOnly(t: TickerBars, lo: number, s: ArrayLike<Num> | undefined): Num[] | undefined {
  if (!s) return undefined;
  const last = t.flow!.last;
  return Array.from(s, (v, k) => last !== null && t.dates[lo + k] === last ? v : null);
}
/** The candles with broker data, 1 or null per candle (memoized as computeFlow answers are). */
function presenceOf(t: TickerBars): { lo: number; out: FlowOut } {
  const fr = windowOf(t), key = canonicalJson([t.ticker, 'broker_data']);
  let out = t.flow!.memo?.get(key);
  if (!out) { const R = contextOf(t).rows; out = { has: Array.from(R.has, x => x ? 1 : null) }; t.flow!.memo?.set(key, out) }
  return { lo: fr.lo, out };
}
/** A series of the window's candles placed on the ticker's bars (null outside). */
function aligned(n: number, lo: number, s: ArrayLike<Num> | undefined): Num[] {
  const o: Num[] = new Array(n).fill(null);
  if (s) for (let k = 0; k < s.length; k++) o[lo + k] = s[k];
  return o;
}

/* ---- references ---------------------------------------------------------------------------------------------------- */

const NO_LAG = Object.freeze({ gt: 0, lt: 0 }) as { gt: 0 | 1; lt: 0 | 1 };
/** Extra fields of a resolved flow series (metrics.ts ResolvedSeries): the entry, the output's kind (OPERATORS.md
    section 4) and the sessions it reads. */
export interface FlowSeriesFields { flowEntry: FlowRegistryEntry; outputKind: string; flowDepth: number | null }
/** A flow reference resolved to a series (metrics.ts ResolvedSeries kind 'flow'): parameters checked and complete,
    the output and its series key in computeFlow's answer, the kind and unit (an H output a price level comparable with
    the close), the sessions it reads (flowDepth), and how to compute it on a ticker (the window's candles, aligned).
    With `ctx.flow` (the worker's loaded window): a window that is not complete, a publication without broker days,
    FL31 (no insider data), ksei_net (no KSEI data) and FL34 without the broker classification are METRIC_UNAVAILABLE
    (FLOW_UNAVAILABLE while the window loads); an anchor date outside the window is refused. */
export function resolveFlow(ref: FlowRef, field: string, ctx: { flow?: FlowBindContext; flowReach?: number | null }): ResolvedSeries & FlowSeriesFields {
  const e = flowEntry(ref.metric, `${field}.metric`);
  if (ref.output !== undefined && typeof ref.output !== 'string') throw new ScreenerError('INVALID_CONDITION', `${field}.output must be the name of one of the indicator's outputs (${e.outputs.map(o => o.key).join(', ')}).`, `${field}.output`, { allowed: e.outputs.map(o => o.key) });
  const output = ref.output ?? e.default_output;
  const params = resolveFlowParams(e, ref.params, field, ctx.flow?.sessions ?? FLOW_DESIGN_SESSIONS, output);
  // the output first (a shape refused whatever the data), then what the publication holds
  const key = seriesKeyOf(e, output, params, field);
  const unavailable = (reason: string, code?: 'FLOW_UNAVAILABLE') => new ScreenerError('METRIC_UNAVAILABLE', `${field}: ${e.name} is not available: ${reason}`, field,
    { metric: e.id, availability: 'REQUIRES_DATA', reason, ...(code ? { reason_code: code } : {}) });
  if (e.requires) throw unavailable(FLOW_REASONS[e.requires]);
  const w = ctx.flow;
  if (w) {
    if (!w.sessions) throw unavailable(FLOW_REASONS.none);
    if (!w.complete) throw unavailable(FLOW_REASONS.loading(w.sessions), 'FLOW_UNAVAILABLE');
    if (e.needs_classification && !w.classification && Object.values(params).some(v => typeof v === 'string' && v.startsWith('class:'))) throw unavailable(FLOW_REASONS.classification);
    for (const q of e.params) {
      const v = params[q.key];
      if (q.kind === 'date' && typeof v === 'string' && v !== 'view' && (w.first === null || w.last === null || v < w.first || v > w.last))
        throw new ScreenerError('INVALID_CONDITION', `${field}.params.${q.key}: the anchor ${v} is outside the loaded broker window (${w.first} to ${w.last}, the last ${w.sessions} sessions): use a date inside it, or "view" for its first session (right: "${w.first}"; wrong: a date before ${w.first}).`, `${field}.params.${q.key}`, { allowed: ['view'] });
    }
  }
  const { kind, unit } = outputKind(e, output, params);
  const norm: FlowRef = { kind: 'flow', metric: e.id, output, params };
  const level = kind === 'H';
  // P5b cost: an anchored entry a condition reads at its last `reach` sessions only is computed there only (lazy), as its
  // own series (its key names the reach, so a cached part never serves a reader that needs more)
  const reach = e.compute === 'anchored' && typeof ctx.flowReach === 'number' ? ctx.flowReach : undefined;
  return {
    kind: 'flow', key: reach === undefined ? canonicalJson(norm) : canonicalJson([norm, { reach }]), ref: norm as MetricRef, label: `${e.id}.${output}`,
    unit: level ? 'price' : unit, historyClass: 'window', inputs: [], comparableWith: level ? 'close' : null, compareLag: NO_LAG,
    integer: kind === 'D' || kind === 'F' || kind === 'B',
    flowEntry: e, outputKind: kind, flowDepth: indicatorDepth(e, output, params),
    full: (t: TickerCalc) => {
      if (reach !== undefined) { const { lo, s } = lazyOutOf(t, e, params, key, reach); return aligned(t.dates.length, lo, s) }
      const { lo, out } = flowOutOf(t, e, params);
      return aligned(t.dates.length, lo, e.current_only ? currentOnly(t, lo, out[key]) : out[key]);
    },
  };
}
/** The 0/1 series of the bars that have broker data (1 on a candle with at least one row, null elsewhere): where a flow
    condition is evaluated (its last 1 on or before the evaluation bar, P10 a) and why a session of it is
    FLOW_UNAVAILABLE. Read through the one series() path, so it is computed once per ticker. */
export const FLOW_PRESENCE: ResolvedSeries = Object.freeze({
  kind: 'flow', key: canonicalJson({ kind: 'flow', metric: 'broker_data' }), ref: { kind: 'flow', metric: 'broker_data' } as MetricRef, label: 'broker data',
  unit: null, historyClass: 'window', inputs: [], comparableWith: null, compareLag: NO_LAG, flowDepth: 1,
  full: (t: TickerCalc) => { const { lo, out } = presenceOf(t); return aligned(t.dates.length, lo, out.has) },
}) as ResolvedSeries;
/** Whether a series reads a flow indicator (directly or through an operator). */
export const readsFlow = (r: ResolvedSeries): boolean => r.flowDepth !== undefined;
