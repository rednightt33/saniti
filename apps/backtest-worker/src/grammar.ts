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
     date), cross-section values and ranks (a population fixed at the evaluation date), the Screener's flow entries (a
     window of the last 60 broker sessions); Flow indicators come in through the Backtest's own Flow conditions.
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
import type { ResolvedSeries, TickerBars } from '../../edge-bff/screener/src/core/metrics.ts';
import { SOURCES as SCREENER_SOURCES, registryProblems } from '../../edge-bff/screener/src/core/registry.ts';
import { IMPLEMENTED_PATTERNS, IMPLEMENTED_TRANSFORMS } from '../../edge-bff/screener/src/core/transforms.ts';
import { availabilityMap, validateTest } from '../../edge-bff/screener/src/core/validate.ts';
import type { ValidateContext } from '../../edge-bff/screener/src/core/validate.ts';

/** The grammar's limits (the Screener's own dev values: SCREENER_CAP_BUDGET_MS 4500, SCREENER_WITHIN_MAX 130). */
export interface GrammarLimits { capBudgetMs: number; withinMax: number }
export const GRAMMAR_DEFAULTS: GrammarLimits = { capBudgetMs: 4500, withinMax: 130 };

/** Metric reference kinds that have no per-day value in a backtest, with the reason the refusal gives. */
const NOT_PER_DAY: Record<string, string> = {
  universe: 'a universe attribute is a value on the screen date only, so a backtest cannot read it on earlier days',
  xsection: 'a cross-section value ranks the stocks listed on the screen date, so a backtest cannot read it on earlier days without look-ahead',
  rank: 'a rank across stocks uses the stocks listed on the screen date, so a backtest cannot read it on earlier days without look-ahead',
  flow: 'the Screener\'s flow entries read its last 60 broker sessions; in a backtest use the Flow conditions of the backtest',
};

const isObj = (x: unknown): x is Record<string, unknown> => !!x && typeof x === 'object' && !Array.isArray(x);
/** Every metric reference kind inside a test, with the field it sits at. */
function refKinds(x: unknown, field: string, out: [string, string][] = []): [string, string][] {
  if (Array.isArray(x)) x.forEach((v, k) => refKinds(v, `${field}[${k}]`, out));
  else if (isObj(x)) {
    if (typeof x.kind === 'string' && !['value', 'state', 'event', 'window'].includes(x.kind)) out.push([x.kind, field]);
    for (const [k, v] of Object.entries(x)) if (k !== 'kind') refKinds(v, `${field}.${k}`, out);
  }
  return out;
}

/** A ScreenerError (or any error of the Screener core) as the Backtest's ValidationError: same code, field and words. */
function asValidation(e: unknown, field: string): unknown {
  if (e instanceof ScreenerError) return new ValidationError(e.code, e.field ?? field, e.message);
  return e;
}

function validateContext(limits: GrammarLimits, tickers: Iterable<string>): ValidateContext {
  return { limits: { max_conditions: 64, max_metric_filters: 8, within_max: limits.withinMax }, capBudgetMs: limits.capBudgetMs, tickers: new Set(tickers),
    groupings: [], metrics: METRICS_CATALOG, availability: availabilityMap({}) };
}

/** The test of a kind-'test' condition checked by the Screener's validation and normalized (parameters complete), or
    the refusal. A reference kind without a per-day value is refused with its reason (CONDITION_UNAVAILABLE). */
export function checkTest(cond: unknown, field: string, limits: GrammarLimits = GRAMMAR_DEFAULTS, tickers: Iterable<string> = []): Test {
  if (!isObj(cond)) throw new ValidationError('INVALID_CONDITION', field, `${field} must be an object.`);
  const enabled = cond.enabled !== false;
  for (const [kind, at] of refKinds(cond.test, `${field}.test`))
    if (NOT_PER_DAY[kind]) throw new ValidationError('CONDITION_UNAVAILABLE', at, `${at}: ${NOT_PER_DAY[kind]}.`);
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
      const index: TickerBars | undefined = c.meta.index ? { ticker: 'IHSG', dates: [...c.meta.index.dates], bars: c.meta.index.bars } : undefined;
      let b: BoundCondition;
      try { b = bindCondition({ id: cond.id, enabled: true, test } as ConditionDef, field, { capBudgetMs: limits.capBudgetMs, withinMax: limits.withinMax, catalog: METRICS_CATALOG, index }) }
      catch (e) { throw asValidation(e, `${field}.test`) }
      const tc = { ticker: c.meta.ticker ?? '', dates: [...(c.meta.dates ?? [])], bars: c.bars, calc: c };
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
      const upTo = last === undefined ? n - 1 : Math.min(last, n - 1);
      for (const r of seriesOf(b)) {
        const s = full(r);
        let any = false;
        for (let i = 0; i <= upTo && !any; i++) { const v = s[i]; any = typeof v === 'number' && Number.isFinite(v) }
        if (!any) throw new ValidationError('INDICATOR_OUTPUT_EMPTY', `${field}.test`, `${field}: ${r.label} has no value on this ticker's bars${last === undefined ? '' : ' up to the end of the period'}.`);
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

/** Installs the grammar into the shared core (the worker's main thread and each compute thread). */
export function installBacktestGrammar(limits: GrammarLimits = GRAMMAR_DEFAULTS): void { installGrammar(grammarEvaluator(limits)) }
