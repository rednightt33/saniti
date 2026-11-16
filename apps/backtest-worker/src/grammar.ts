/* EXEC-BACKTEST-REVAMP P1-P2 (user 2026-11-15: "Setuju untuk usulanmu ... satu bahasa kondisi bersama (permanen)"): the
   Backtest reads conditions in the Screener's grammar (kind 'test': VALUE, STATE, EVENT and window tests over indicators,
   bar fields, transforms and patterns) with the Screener core's own code, so the two never compute a condition two ways.
   The Screener core imports the Backtest core; the Backtest core never imports the Screener core (a module cycle stops
   the screener-worker at start, Stage A Agent 3), so the grammar is installed into the core from here (conditions.ts
   installGrammar, once per thread when validate.ts loads) and validated here.

   The Backtest's rules on top of the Screener's (EXEC "Aturan yang tidak ditanyakan"):
   - per bar: condition.ts conditionSignal on whole series (the Screener's own evaluate() reads only its last bar);
   - EVENT `within` applies per condition, as in the Screener (a rolling OR over the last `within` bars); the entry
     rule's window does not widen it again (signals.ts: such a condition's window is 1 bar);
   - bar 0 is never true (the Backtest's rule for every condition, conditions.ts compare);
   - a series a condition reads without any value on the ticker's bars up to `last` is INDICATOR_OUTPUT_EMPTY, the
     error the Backtest raises for its own indicator conditions (a portfolio then leaves the ticker out, signals.ts);
   - refused, because they have no per-day value without look-ahead: universe attributes (a snapshot at the evaluation
     date), cross-section values and ranks (a population fixed at the evaluation date); the Flow indicators are read
     on every bar from the whole broker history (P3, flowRefusal below for the ones refused).
   Series are kept per ticker under their resolved key (Calc.seriesMemo), so the sensitivity grid's cells reuse them. */
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { Calc, installGrammar } from '../../edge-bff/backtest/src/core/conditions.ts';
import type { GrammarEvaluator, Signal, TestCondition } from '../../edge-bff/backtest/src/core/conditions.ts';
import { ValidationError } from '../../edge-bff/backtest/src/core/registry.ts';
import { bindCondition, conditionSignal } from '../../edge-bff/screener/src/core/condition.ts';
import type { BoundCondition } from '../../edge-bff/screener/src/core/condition.ts';
import { METRICS_CATALOG, catalogProblems } from '../../edge-bff/screener/src/core/catalog.ts';
import type { ConditionDef, Test } from '../../edge-bff/screener/src/core/contract.ts';
import { ScreenerError } from '../../edge-bff/screener/src/core/errors.ts';
import { resolveSeries } from '../../edge-bff/screener/src/core/metrics.ts';
import type { ResolvedSeries, TickerBars } from '../../edge-bff/screener/src/core/metrics.ts';
import { FLOW_BY_ID, indicatorDepth, readsFlow, seriesKeyOf } from '../../edge-bff/screener/src/core/flowmetrics.ts';
import type { FlowBindContext, TickerFlow } from '../../edge-bff/screener/src/core/flowmetrics.ts';
import type { FlowParamValue } from '../../edge-bff/screener/src/core/contract.ts';
import { basisBlocked } from './basis.ts';
import FLOW_REGISTRY from '../../edge-bff/terminal/src/data/flowRegistry.json' with { type: 'json' };
import { checkDTest, dSignal, hasD } from './pit/evaluate.ts';
import { dSeries, namedWithoutRows } from './pit/series.ts';
import { checkDRef, isD } from './pit/spec.ts';
import type { DRef } from './pit/spec.ts';
import { computeFlow } from '../../edge-bff/terminal/src/calc/flow.ts';
import type { FlowContext, FlowOut } from '../../edge-bff/terminal/src/calc/flow.ts';
import { SOURCES as SCREENER_SOURCES, registryProblems } from '../../edge-bff/screener/src/core/registry.ts';
import { IMPLEMENTED_PATTERNS, IMPLEMENTED_TRANSFORMS } from '../../edge-bff/screener/src/core/transforms.ts';
import { availabilityMap, validateTest } from '../../edge-bff/screener/src/core/validate.ts';
import type { ValidateContext } from '../../edge-bff/screener/src/core/validate.ts';

/** The grammar's limits (the Screener's own dev values: SCREENER_CAP_BUDGET_MS 4500, SCREENER_WITHIN_MAX 130). */
export interface GrammarLimits { capBudgetMs: number; withinMax: number }
export const GRAMMAR_DEFAULTS: GrammarLimits = { capBudgetMs: 4500, withinMax: 130 };

/** Metric reference kinds that have no per-day value in a backtest, with the reason the refusal gives. */
export const NOT_PER_DAY: Record<string, string> = {
  universe: 'a universe attribute is a value on the screen date only, so a backtest cannot read it on earlier days',
  xsection: 'a cross-section value ranks the stocks listed on the screen date, so a backtest cannot read it on earlier days without look-ahead',
  rank: 'a rank across stocks uses the stocks listed on the screen date, so a backtest cannot read it on earlier days without look-ahead',
};

/* EXEC-BACKTEST-REVAMP P3: the Flow indicators in the grammar ({"kind":"flow","metric":"FL01",...}). A backtest reads
   each on every bar from the ticker's whole broker history with the Terminal's formula as it is (calc/flow.ts
   computeFlow, through the Screener's flow series): the registry's baselines (the Screener lowers a baseline to fit its
   60-session window; here nothing is lowered) and today's broker classification on every date (FL34, user decision 5).
   The eight that choose their brokers with later data (FL18, FL19, FL20, FL23, FL44, FL45, FL51, FL52) are read in
   their point-in-time versions (pit/, P4, admins only: validate.ts). Refused, with the reason: the Screener's own
   entries (foreign net, KSEI) and an entry that needs data not published (FL31 insider). */
function flowRefusal(metric: unknown): string | null {
  if (isD(metric)) return null;                                      // the worker's point-in-time versions (pit/), P4
  const e = typeof metric === 'string' ? FLOW_BY_ID[metric] : undefined;
  if (!e) return null;                                               // the Screener's validation names the ids
  if (e.requires === 'insider') return `${e.id} needs insider transactions with the date they were made public; the published insider rows carry the transaction date only, so a backtest would read them before anyone could know them`;
  if (e.requires) return `${e.id} needs data that is not published yet (${e.requires})`;
  if (e.compute !== 'terminal') return `${e.id} is the Screener's own entry on its broker window, not a Terminal Flow indicator a backtest can read on every bar`;
  return null;
}

const isObj = (x: unknown): x is Record<string, unknown> => !!x && typeof x === 'object' && !Array.isArray(x);
/** Every metric reference inside a test: its kind, the field it sits at, the reference. */
function refKinds(x: unknown, field: string, out: [string, string, Record<string, unknown>][] = []): [string, string, Record<string, unknown>][] {
  if (Array.isArray(x)) x.forEach((v, k) => refKinds(v, `${field}[${k}]`, out));
  else if (isObj(x)) {
    if (typeof x.kind === 'string' && !['value', 'state', 'event', 'window'].includes(x.kind)) out.push([x.kind, field, x]);
    for (const [k, v] of Object.entries(x)) if (k !== 'kind') refKinds(v, `${field}.${k}`, out);
  }
  return out;
}

/** A ScreenerError (or any error of the Screener core) as the Backtest's ValidationError: same code, field, words and
    details (the limit, allowed and needed values CONTRACT section 3 promises; errors.ts answers them; Stage C F9). */
function asValidation(e: unknown, field: string): unknown {
  if (e instanceof ScreenerError) return Object.assign(new ValidationError(e.code, e.field ?? field, e.message), e.details ? { details: e.details } : {});
  return e;
}

/* Stage C2 (lens 1 F2 and F3, ERRORS M459): a Flow reference that names its brokers (a list of the registry's kind
   'brokers': brokers, inst, retail, num_brokers, den_brokers; read where it is in use: its `<prefix>scope` set to
   'selected', or no scope of its prefix) reads each named broker from its own first row for the stock on. The Terminal
   puts a broker in the stock's broker set when it has a row anywhere in the rows it is given (calc/flow.ts cohort), so on
   the whole history a broker that starts trading the stock later counted as a member (value 0) on the days before, where
   the data up to that day has no such broker (FL13: "no member: no value"). The series is therefore computed per stretch
   of days with the same members (tickerFlow: one computeFlow per stretch, the names not yet trading replaced by a code no
   row has) and joined; a broker with no row at all is in neither set, as before. Stage C refused a broker whose first row
   came after the period (UNKNOWN_BROKER), which let rows after the period decide the run (lens 1 F3); that refusal is
   gone. */
const NOT_YET = '\u0000';
/** The broker lists a Flow entry reads at these parameters, with their codes. */
function namedLists(e: (typeof FLOW_BY_ID)[string], params: Record<string, unknown>): { key: string; codes: string[] }[] {
  const out: { key: string; codes: string[] }[] = [];
  for (const p of e.params) {
    const v = params[p.key];
    if (p.kind !== 'brokers' || !Array.isArray(v)) continue;
    const scope = `${p.key.slice(0, p.key.length - 'brokers'.length)}scope`;
    const sp = p.key.endsWith('brokers') ? e.params.find(q => q.key === scope) : undefined;
    if (sp && (params[scope] ?? sp.default) !== 'selected') continue;
    out.push({ key: p.key, codes: v.filter((x): x is string => typeof x === 'string') });
  }
  return out;
}

/** The metrics' availability as the Screener's validation reads it: every metric a backtest has no file for is
    unavailable as on a publication without files, except the Flow indicators, whose broker files the worker loads and
    whose availability (catalog.flow.available) it checks itself (validate.ts). */
const AVAILABILITY = (() => {
  const m = new Map(availabilityMap({}));
  for (const x of METRICS_CATALOG.metrics) if ((x as { flow?: unknown }).flow) m.set(x.id, { availability: 'AVAILABLE', reason: null });
  return m;
})();
function validateContext(limits: GrammarLimits, tickers: Iterable<string>): ValidateContext {
  return { limits: { max_conditions: 64, max_metric_filters: 8, within_max: limits.withinMax }, capBudgetMs: limits.capBudgetMs, tickers: new Set(tickers),
    groupings: [], metrics: METRICS_CATALOG, availability: AVAILABILITY };
}

/** The Flow references of a test with their field (validate.ts: broker files, FLOW_UNAVAILABLE, broker codes). */
export function flowRefs(test: unknown, field: string): { field: string; ref: Record<string, unknown> }[] {
  return refKinds(test, field).filter(([k]) => k === 'flow').map(([, f, ref]) => ({ field: f, ref }));
}

/* EXEC-BACKTEST-REVAMP P3 (K3 a, ERRORS M450), P9 (option A, M458 item 2): a Flow value that compares a broker price
   with the close (the registry's family "Buy VWAP & Implied Cost", or a price unit) reads the broker lots on the
   published prices' basis (datafile.ts onPriceBasis, the factor the publisher measured per corporate action) and is left
   empty only where its window reads a bar whose basis is not settled by the data up to its own bar (basis.ts
   basisBlocked: a bar whose broker VWAP is outside its own range, or an action across which the basis is pending,
   unresolved or the close was not reloaded). Derived from the registry and the ticker's events; a new indicator of that
   family is covered without a code change. */
const BROKER_PRICE = new Set((FLOW_REGISTRY as { indicators: { id: string; family: string; unit: string }[] }).indicators
  .filter(r => r.family === 'Buy VWAP & Implied Cost' || r.unit === 'price').map(r => r.id));
/** The bars [lo, lo + N) of the flow window whose value must stay empty, for a series that reads `depth` sessions up to
    its bar (null: the whole history). */
function basisMask(c: Calc, lo: number, N: number, depth: number | null): Uint8Array {
  const mask = new Uint8Array(N);
  for (let k = 0; k < N; k++) { const i = lo + k; mask[k] = +basisBlocked(c, depth === null ? 0 : i - depth + 1, i) }
  return mask;
}

/* The ticker's broker data as the Screener's flow series read it (flowmetrics.ts TickerFlow): the whole history, one
   object per Calc so its FlowContext and computeFlow answers are built once per ticker (the grid's cells reuse them).
   Its memo is where every computeFlow answer passes (flowmetrics.ts memoCall), so the basis mask applies to a Flow
   series wherever it is read (directly or inside a transform), and the notes for the run's warnings are kept there. */
const FLOWS_OF = new WeakMap<Calc, TickerFlow>();
function tickerFlow(c: Calc): TickerFlow | undefined {
  const b = c.meta.broker;
  if (!b) return undefined;
  let f = FLOWS_OF.get(c);
  if (!f) {
    const cols = b.columns, first = cols.rows ? cols.dates[0] : null, last = cols.rows ? cols.dates[cols.dates.length - 1] : null, memo = new Map<string, FlowOut>();
    const dates = c.meta.dates ?? [], lo = first === null ? 0 : (() => { let i = 0; while (i < dates.length && dates[i] < first) i++; return i })();
    const notes = c.flowNotes ??= { depth: 0, masked: new Set<number>() };
    // Stage C2 (lens 1 F4): the window's sessions with a broker row; on a session without one (a source gap) a Flow value
    // is empty, as on the data up to that session (the window then ends at the session before)
    const rowDay = new Set(cols.dates), N = (() => { let i = lo; while (i < dates.length && last !== null && dates[i] <= last) i++; return i - lo })();
    const noRow = Uint8Array.from({ length: N }, (_, j) => +!rowDay.has(dates[lo + j]));
    // each named broker's first session in the window (lens 1 F2)
    const firstAt = new Map<string, number>();
    for (let k = 0; k < cols.rows; k++) { const b0 = cols.brokers[cols.B[k]], d0 = firstAt.get(b0); if (d0 === undefined || cols.D[k] < d0) firstAt.set(b0, cols.D[k]) }
    const at = new Map(dates.slice(lo, lo + N).map((d, j) => [d, j]));
    const firstIn = (code: string) => { const d = firstAt.get(code); return d === undefined ? undefined : at.get(cols.dates[d]) };
    let ctx: FlowContext | undefined;
    const set = (k: string, out: FlowOut) => {
      const key = JSON.parse(k) as [string, string, Record<string, FlowParamValue>, string?, number?], [, id, params] = key, e = FLOW_BY_ID[id];
      for (const s of Object.values(out)) {
        if (key.length === 5) { if (noRow[key[4]!]) s.fill(null) }
        else for (let j = 0; j < s.length && j < N; j++) if (noRow[j]) s[j] = null;
      }
      for (const o of key.length === 5 ? [] : e?.outputs ?? []) {
        const d = indicatorDepth(e, o.key, params);
        if (notes.depth !== null) notes.depth = d === null ? null : Math.max(notes.depth, d);
        if (!BROKER_PRICE.has(id)) continue;
        const key = seriesKeyOf(e, o.key, params, 'mask'), s = out[key];
        if (!s) continue;
        const m = basisMask(c, lo, s.length, d);
        for (let j = 0; j < s.length; j++) if (m[j] && s[j] !== null) { s[j] = null; notes.masked.add(lo + j) }
      }
      memo.set(k, out);
    };
    /** computeFlow per stretch of sessions with the same named members, joined (undefined: no named broker starts
        inside the window, the memo's caller computes it as the Terminal does) */
    const members = (k: string): FlowOut | undefined => {
      const key = JSON.parse(k) as unknown[], e = key.length === 3 ? FLOW_BY_ID[key[1] as string] : undefined;
      if (!e || e.compute !== 'terminal' || !ctx) return undefined;
      const params = key[2] as Record<string, FlowParamValue>, lists = namedLists(e, params);
      const starts = [...new Set(lists.flatMap(l => l.codes.map(firstIn)).filter((j): j is number => j !== undefined && j > 0))].sort((x, y) => x - y);
      if (!starts.length) return undefined;
      const bounds = [0, ...starts, ctx.dates.length];
      let out: FlowOut | undefined;
      for (let s0 = 0; s0 + 1 < bounds.length; s0++) {
        const a0 = bounds[s0], b0 = bounds[s0 + 1], q: Record<string, unknown> = { ...params };
        for (const { key: lk, codes } of lists) q[lk] = codes.map(code => (firstIn(code) ?? -1) <= a0 ? code : NOT_YET + code);
        const r = computeFlow(e.id, ctx, q as never);
        if (!out) out = Object.fromEntries(Object.entries(r).map(([sk, v]) => [sk, Array.from(v)]));
        else for (const [sk, v] of Object.entries(r)) if (out[sk]) for (let j = a0; j < b0; j++) out[sk][j] = v[j];
      }
      set(k, out!);
      return memo.get(k);
    };
    f = { first, last, rows: () => cols, classification: b.classification, memo: { get: k => memo.get(k) ?? members(k), set },
      meter: { context: <T>(build: () => T): T => { const x = build(); ctx = x as unknown as FlowContext; return x } } };
    FLOWS_OF.set(c, f);
  }
  return f;
}
const flowBind = (f: TickerFlow | undefined): FlowBindContext | undefined => f && ({ sessions: Number.MAX_SAFE_INTEGER, first: f.first, last: f.last, complete: true,
  classification: Object.keys(f.classification).length > 0, allDates: true });

/** The test of a kind-'test' condition checked by the Screener's validation and normalized (parameters complete), or
    the refusal. A reference kind without a per-day value is refused with its reason (CONDITION_UNAVAILABLE). */
export function checkTest(cond: unknown, field: string, limits: GrammarLimits = GRAMMAR_DEFAULTS, tickers: Iterable<string> = []): Test {
  if (!isObj(cond)) throw new ValidationError('INVALID_CONDITION', field, `${field} must be an object.`);
  const enabled = cond.enabled !== false;
  for (const [kind, at, ref] of refKinds(cond.test, `${field}.test`)) {
    if (NOT_PER_DAY[kind]) throw new ValidationError('CONDITION_UNAVAILABLE', at, `${at}: ${NOT_PER_DAY[kind]}.`);
    const why = kind === 'flow' ? flowRefusal(ref.metric) : null;
    if (why) throw new ValidationError('CONDITION_UNAVAILABLE', at, `${at}: ${why}.`);
  }
  // P4: a test that reads a point-in-time Flow indicator is checked by the worker (pit/evaluate.ts), with the Screener
  // resolving every other side
  if (hasD(cond.test)) return checkDTest(cond.test, `${field}.test`, (ref, f) => {
    try { const r = resolveSeries(ref as never, f, { capBudgetMs: limits.capBudgetMs, catalog: METRICS_CATALOG }); return { unit: r.unit ?? null, comparableWith: r.comparableWith ?? null } }
    catch (e) { throw asValidation(e, f) }
  }, limits.withinMax) as unknown as Test;
  try { return validateTest(cond.test, `${field}.test`, validateContext(limits, tickers), enabled) }
  catch (e) { throw asValidation(e, `${field}.test`) }
}

/** The condition on every bar with the Backtest's rules: bar 0 is never true, for a window's inner test too (the page
    starts every comparison at bar 1, conditions.ts compare), and an EVENT is true on its marker and the next within-1
    bars (the Screener's evaluateEvent at each bar). A window test counts its inner test's passes as condition.ts
    conditionSignal does (ever: one in the last `length` bars; at_least: `count`; always: a run of `length`), on the
    inner series with bar 0 false. */
function perBar(b: BoundCondition, full: (r: ResolvedSeries) => ArrayLike<number | null | undefined>, n: number): Signal | null {
  if (b.window) {
    const p = perBar(b.window.inner, full, n), { mode, length, count } = b.window, out = new Uint8Array(n);
    if (!p) return null;
    let sum = 0, run = 0;
    for (let i = 0; i < n; i++) {
      sum += p[i]; if (i >= length) sum -= p[i - length];
      run = p[i] ? run + 1 : 0;
      out[i] = +(mode === 'ever' ? sum >= 1 : mode === 'at_least' ? sum >= count : run >= length);
    }
    if (n) out[0] = 0;
    return out;
  }
  const raw = conditionSignal(b, full, n);
  if (!raw) return null;
  if (n) raw[0] = 0;
  if (b.test.kind !== 'event') return raw;
  const w = (b.test as { within: number }).within, out = new Uint8Array(n);
  for (let i = 0, lastOn = -1e9; i < n; i++) { if (raw[i]) lastOn = i; out[i] = +(i - lastOn < w) }
  return out;
}

/** Every series a bound condition reads, a window's inner test included. */
const seriesOf = (b: BoundCondition): ResolvedSeries[] => [...b.series, ...(b.window ? seriesOf(b.window.inner) : [])];

/** How many series the grammar computed in this thread (a memo miss); tests read it to prove the memo serves the
    sensitivity grid's cells. */
export const grammarStats = { computed: 0 };

export function grammarEvaluator(limits: GrammarLimits = GRAMMAR_DEFAULTS): GrammarEvaluator {
  return {
    signal(c: Calc, cond: TestCondition, field: string, last?: number): Signal {
      const n = c.n, test = checkTest(cond, field, limits);
      if (hasD(test)) return pitSignal(c, test as unknown as Record<string, unknown>, `${field}.test`, field, n, last, limits);
      const index: TickerBars | undefined = c.meta.index ? { ticker: 'IHSG', dates: [...c.meta.index.dates], bars: c.meta.index.bars } : undefined;
      let b: BoundCondition;
      const flow = tickerFlow(c);
      try { b = bindCondition({ id: cond.id, enabled: true, test } as ConditionDef, field, { capBudgetMs: limits.capBudgetMs, withinMax: limits.withinMax, catalog: METRICS_CATALOG, index, flow: flowBind(flow) }) }
      catch (e) { throw asValidation(e, `${field}.test`) }
      const tc = { ticker: c.meta.ticker ?? '', dates: [...(c.meta.dates ?? [])], bars: c.bars, calc: c, ...(flow ? { flow } : {}) };
      const full = (r: ResolvedSeries) => {
        let s = c.seriesMemo.get(r.key);
        if (!s) {
          try { s = r.full(tc as never) as ArrayLike<number | null> } catch (e) { throw asValidation(e, `${field}.test`) }
          grammarStats.computed++;
          c.seriesMemo.set(r.key, s);
        }
        return s;
      };
      // a series without any value on the bars up to `last` (later bars never decide it): the Backtest's refusal; on no
      // bars at all (the request check, validate.ts) nothing is computed
      if (!n) throw new ValidationError('INDICATOR_OUTPUT_EMPTY', `${field}.test`, `${field}: there are no bars to compute this condition on.`);
      if (!flow && seriesOf(b).some(readsFlow))
        throw new ValidationError('FLOW_UNAVAILABLE', `${field}.test`, `${field}: this condition reads the broker data, which is not loaded for this ticker.`);
      // the sessions a Flow condition reads before its bar: its series' own (an operator's included) and the test's
      // within or window length (FlowNotes.depth, the run's FLOW_PRE_2021)
      if (flow && c.flowNotes && c.flowNotes.depth !== null) {
        const extra = (test.kind === 'event' ? (test as { within: number }).within : test.kind === 'window' ? (test as { length: number }).length : 1) - 1;
        for (const r of seriesOf(b)) if (readsFlow(r)) {
          const d = (r as { flowDepth?: number | null }).flowDepth;
          c.flowNotes.depth = d === null || d === undefined ? null : Math.max(c.flowNotes.depth ?? 0, d + extra);
          if (c.flowNotes.depth === null) break;
        }
      }
      const upTo = last === undefined ? n - 1 : Math.min(last, n - 1);
      for (const r of seriesOf(b)) {
        const s = full(r);
        let any = false;
        for (let i = 0; i <= upTo && !any; i++) { const v = s[i]; any = typeof v === 'number' && Number.isFinite(v) }
        if (!any) throw new ValidationError(readsFlow(r) ? 'FLOW_OUTPUT_EMPTY' : 'INDICATOR_OUTPUT_EMPTY', `${field}.test`, `${field}: ${r.label} has no value on this ticker's bars${last === undefined ? '' : ' up to the end of the period'}.`);
      }
      const out = perBar(b, full, n);
      if (!out) throw new ValidationError('CONDITION_UNAVAILABLE', `${field}.test`, `${field}: this test has no per-day value.`);
      return out;
    },
  };
}

/** The start-up check of the grammar, as the screener-worker makes it (apps/screener-worker/src/version.ts
    checkStartup): the Screener registry, its catalog against the transforms and patterns transforms.ts computes, and
    every source file the registry was built from in the image with the hash it was built from (the oracle script is
    used only to build it). Empty when the worker may start; server.ts exits otherwise. */
export function grammarProblems(root: string): string[] {
  const problems = [...registryProblems(), ...catalogProblems({ transforms: IMPLEMENTED_TRANSFORMS, patterns: IMPLEMENTED_PATTERNS })];
  for (const s of SCREENER_SOURCES) {
    if (s.role === 'oracle') continue;
    const file = path.join(root, s.file);
    if (!fs.existsSync(file)) { problems.push(`${s.file} (${s.role}) is not in the image`); continue }
    const got = crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
    if (got !== s.sha256) problems.push(`${s.file} (${s.role}) has sha256 ${got.slice(0, 16)}..., screener-registry.json was built from ${s.sha256.slice(0, 16)}...: run npm run registry in apps/edge-bff/screener`);
  }
  return problems;
}

/** A test with a point-in-time Flow reference on every bar (pit/evaluate.ts dSignal): its sides' series, the
    Backtest's EMPTY refusals up to `last`, no computation on empty bars. */
function pitSignal(c: Calc, test: Record<string, unknown>, field: string, cfield: string, n: number, last: number | undefined, limits: GrammarLimits): Signal {
  if (!n) throw new ValidationError('INDICATOR_OUTPUT_EMPTY', field, `${cfield}: there are no bars to compute this condition on.`);
  const upTo = last === undefined ? n - 1 : Math.min(last, n - 1), until = c.meta.dates?.[upTo] ?? '9999-12-31';
  return dSignal(test, field, n, (side, f) => {
    const d = isObj(side) && side.kind === 'flow' && isD(side.metric);
    if (d) {
      const miss = namedWithoutRows(c, side as unknown as DRef, until);
      if (miss) throw new ValidationError('UNKNOWN_BROKER', `${f}.params.brokers[${miss[1]}]`, `${f}.params.brokers[${miss[1]}]: ${miss[0]} has no broker rows for ${c.meta.ticker ?? 'this stock'}${last === undefined ? '' : ' up to the end of the period'}.`);
    }
    const s = d ? dSeries(c, side as unknown as DRef, f) : seriesOfRef(c, side, f, limits);
    let any = false;
    for (let i = 0; i <= upTo && !any; i++) { const v = s[i]; any = typeof v === 'number' && Number.isFinite(v) }
    if (!any) throw new ValidationError(d ? 'FLOW_OUTPUT_EMPTY' : 'INDICATOR_OUTPUT_EMPTY', f, `${cfield}: ${d ? `${(side as { metric: string }).metric}.${(side as { output: string }).output}` : 'a side'} has no value on this ticker's bars${last === undefined ? '' : ' up to the end of the period'}.`);
    return s;
  });
}

/** One reference's series on every bar of a ticker as a condition reads it (tests, and the worker's chart series):
    resolved with the backtest's context (IHSG, the whole broker history), memoized in the Calc. */
export function seriesOfRef(c: Calc, ref: unknown, field: string, limits: GrammarLimits = GRAMMAR_DEFAULTS): ArrayLike<number | null | undefined> {
  if (isObj(ref) && ref.kind === 'flow' && isD(ref.metric)) return dSeries(c, checkDRef(ref, field), field);
  const flow = tickerFlow(c), index: TickerBars | undefined = c.meta.index ? { ticker: 'IHSG', dates: [...c.meta.index.dates], bars: c.meta.index.bars } : undefined;
  let r: ResolvedSeries;
  try { r = resolveSeries(ref as never, field, { capBudgetMs: limits.capBudgetMs, index, flow: flowBind(flow), catalog: METRICS_CATALOG }) }
  catch (e) { throw asValidation(e, field) }
  let s = c.seriesMemo.get(r.key);
  if (!s) {
    const tc = { ticker: c.meta.ticker ?? '', dates: [...(c.meta.dates ?? [])], bars: c.bars, calc: c, ...(flow ? { flow } : {}) };
    try { s = r.full(tc as never) as ArrayLike<number | null> } catch (e) { throw asValidation(e, field) }
    grammarStats.computed++;
    c.seriesMemo.set(r.key, s);
  }
  return s;
}

/** Installs the grammar into the shared core (the worker's main thread and each compute thread). */
export function installBacktestGrammar(limits: GrammarLimits = GRAMMAR_DEFAULTS): void { installGrammar(grammarEvaluator(limits)) }
