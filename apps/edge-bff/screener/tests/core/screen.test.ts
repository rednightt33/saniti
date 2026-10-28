/* One screen over a snapshot (report TARGET ARCHITECTURE 6.7, 6.10, 6.12; API CONTRACT 8.5; TEST PLAN 10b.2
   "Explicit defaults hit the snapshot", "Dynamic equals a direct call", 10b.4 "Stale tickers", "Price breaks", 10b.5
   "Hidden tickers and the rank population", 10b.6 "Budget"):
   - parity: the same screens run on a pre-warmed snapshot (every series pinned, stage S2) and on an empty cache (every
     series computed for the request, stage S3) give identical answers apart from `source`, and both equal a brute-force
     evaluation through F directly;
   - P4: stale and price-break tickers are hidden by default and counted; shown, a stale ticker is evaluated at its own
     last bar with its STALE remark and a price-break ticker keeps its values with the remarks; preset ranks do not move;
   - universe_only lists the universe; metric filters that need a formula drop the tickers that fail them;
   - a definition costed above the budget is refused before any compute, naming the costliest condition. */
import { describe, expect, it } from 'vitest';
import { F } from '../../../terminal/src/calc/indicators.ts';
import type { Definition, ResultRow, UniverseRow } from '../../src/core/contract.ts';
import { UNIVERSE_DEFAULTS } from '../../src/core/contract.ts';
import { PRESETS } from '../../src/core/catalog.ts';
import { bindCondition } from '../../src/core/condition.ts';
import { ScreenerError } from '../../src/core/errors.ts';
import { previewCells, runScreen } from '../../src/core/screen.ts';
import { validateDefinition, validateTest } from '../../src/core/validate.ts';
import { OPTS, WITHIN_MAX, headBars, memoryEnv, rowOf, synth, tailBars, vctx } from './helpers.ts';
import type { MemoryEnv } from './helpers.ts';

const IX = (() => { const t = synth('IHSG', 3, 520, '2024-06-03'); return { ...t, bars: { ...t.bars, V: t.bars.V.map(() => null) } } })();
const E = IX.dates[IX.dates.length - 1];
const base = Array.from({ length: 60 }, (_, k) => synth(`S${String(k).padStart(2, '0')}`, 500 + k, 520, '2024-06-03'));
const STALE = headBars(synth('STAL', 900, 520, '2024-06-03'), 505);
const SHORT = tailBars(synth('RANS', 901, 520, '2024-06-03'), 74);
const BROKE = synth('PBSA', 902, 520, '2024-06-03');
const EX = BROKE.dates[BROKE.dates.length - 9];
const TICKERS = [...base, STALE, SHORT, BROKE];
const rows: UniverseRow[] = TICKERS.map(t => rowOf(t, E, { adv20_idr: 5e9, last: 1000 },
  t === BROKE ? [{ code: 'PRICE_BREAK', action: 'STOCK_SPLIT', ex_date: EX, ratio_old: 1, ratio_new: 2, close_ratio: 0.5 }] : []));
const CTX = vctx(TICKERS.map(t => t.ticker));
const U = { ...UNIVERSE_DEFAULTS, price_min: null, adv20_min_idr: null } as Definition['universe'];
const close = { kind: 'price', field: 'close' } as const;
const ind = (indicator: string, output: string, params?: Record<string, unknown>) => ({ kind: 'indicator' as const, indicator, output, ...(params ? { params } : {}) });
const norm = (d: unknown) => validateDefinition(d, CTX);
const SCREENS: Definition[] = [
  { universe: U, logic: 'at_least', at_least: 2, conditions: [
    { id: 'a', enabled: true, test: { kind: 'value', op: 'lt', value: 45, metric: ind('I13', 'rsi', { length: 7 }) } },
    { id: 'b', enabled: true, test: { kind: 'state', lhs: close, op: 'gt', rhs: ind('I01', 'sma', { length: 50 }) } },
    { id: 'c', enabled: true, test: { kind: 'event', within: 10, signal: { lhs: ind('I06', 'macd'), op: 'crosses_above', rhs: ind('I06', 'signal') } } },
    { id: 'd', enabled: true, test: { kind: 'state', lhs: close, op: 'gt', rhs: ind('I10', 'upper') } },
    { id: 'e', enabled: false, test: { kind: 'value', op: 'gt', value: 0, metric: { kind: 'flow', metric: 'fnet', params: { window: 20 } } } } ] },
  { universe: U, logic: 'any', conditions: [
    { id: 'a', enabled: true, test: { kind: 'event', within: 30, signal: { pattern: { kind: 'pattern', type: 'breakout', params: { length: 40 } } } } },
    { id: 'b', enabled: true, test: { kind: 'value', op: 'gt', value: 50, metric: { kind: 'xsection', metric: 'return_rank', params: { window: 60 } } } },
    { id: 'c', enabled: true, test: { kind: 'value', op: 'between', value: -15, value2: 0, metric: { kind: 'transform', fn: 'pct_distance', of: { kind: 'transform', fn: 'rolling_max', of: { kind: 'price', field: 'high' }, args: { length: 252 } } } } } ] },
  { universe: { ...U, traded_on_eval_date: false, exclude_price_breaks: false }, logic: 'all', conditions: [
    { id: 'a', enabled: true, test: { kind: 'state', lhs: ind('I01', 'sma', { length: 20 }), op: 'gt', rhs: { kind: 'transform', fn: 'lag', of: ind('I01', 'sma', { length: 20 }), args: { bars: 5 } } } },
    { id: 'b', enabled: true, test: { kind: 'value', op: 'gt', value: 0, metric: { kind: 'transform', fn: 'vs_index', of: close, args: { window: 63 } } } },
    { id: 'c', enabled: true, test: { kind: 'state', lhs: close, op: 'gt', rhs: ind('I27', 'basis', { basis_ma_type: 'VWMA' }) } } ] },
].map(norm) as Definition[];

const strip = (rows: ResultRow[]) => rows;
function cold(): MemoryEnv { return memoryEnv(TICKERS, IX, rows, E) }
function warm(defs: Definition[]): MemoryEnv {
  const env = memoryEnv(TICKERS, IX, rows, E);
  for (const d of defs) for (const c of d.conditions.filter(x => x.enabled)) env.prewarm(bindCondition(c, 'c', env).series);
  return env;
}

describe('precomputed and dynamic are the same call at two times (report 6.7)', () => {
  it('a pre-warmed snapshot and an empty cache give identical rows, cells and counts; only the source differs', () => {
    const w = warm(SCREENS), c = cold();
    for (const d of SCREENS) {
      const a = runScreen(d, w, { explain: true }), b = runScreen(d, c, { explain: true, exhaustive: true });
      const bp = runScreen(d, cold(), { explain: true });
      expect(strip(a.rows)).toEqual(strip(b.rows));
      expect(strip(bp.rows)).toEqual(strip(a.rows));
      expect([a.match_count, a.near_count, a.need, a.universe]).toEqual([b.match_count, b.near_count, b.need, b.universe]);
      for (const s of a.conditions) expect(s.source === 'precomputed' || s.source === 'xsection').toBe(true);
      for (const s of b.conditions) if (s.source !== 'xsection') expect(s.source).toBe('dynamic');
      expect(a.conditions.map(x => [x.id, x.passed, x.na, x.evaluated])).toEqual(b.conditions.map(x => [x.id, x.passed, x.na, x.evaluated]));
    }
    expect(w.computed).toBe(0);                                                              // nothing computed for the request
  });
  it('the cells equal a brute-force reading of F at each ticker\'s last bar', () => {
    const r = runScreen(SCREENS[0], cold(), { exhaustive: true });
    expect(r.rows.length).toBeGreaterThan(5);
    for (const row of r.rows) {
      const t = TICKERS.find(x => x.ticker === row.ticker)!, at = t.dates.length - 1, C = t.bars.C as number[];
      const rsi7 = F.rsi(t.bars, { length: 7 }).rsi[at], sma50 = F.sma(t.bars, { length: 50 }).sma[at];
      const m = F.macd(t.bars, {}), up = F.donchian(t.bars, {}).upper;
      let ev = -1; for (let i = at; i > at - 10; i--) if ((m.macd[i - 1]! <= m.signal[i - 1]!) && m.macd[i]! > m.signal[i]!) { ev = i; break }
      const want = [rsi7! < 45, C[at] > sma50!, ev >= 0, C[at] > up[at - 1]!].map(x => x ? 'pass' : 'fail');
      expect([row.ticker, row.cells.map(x => x.status)]).toEqual([row.ticker, want]);
      expect(row.cells[0].value).toBe(Number(rsi7!.toPrecision(12)));
      expect(row.met).toBe(want.filter(x => x === 'pass').length);
    }
  });
});

describe('stage S0 and the P4 chips', () => {
  const plain = norm({ universe: U, logic: 'all', conditions: [] });
  it('no condition lists the universe (universe_only): stale and price-break tickers hidden and counted', () => {
    const r = runScreen(plain, cold());
    expect([r.mode, r.need, r.universe]).toEqual(['universe_only', 0, { listed: 63, eligible: 61, stale_hidden: 1, price_break_hidden: 1, filtered_out: 0 }]);
    expect(r.rows.every(x => x.status === 'match' && x.met === 0 && x.cells.length === 0)).toBe(true);
    expect(r.rows.some(x => x.ticker === 'STAL' || x.ticker === 'PBSA')).toBe(false);
  });
  it('shown, a stale ticker is evaluated at its own last bar with STALE; a price-break ticker keeps its values with both remarks', () => {
    const d = norm({ universe: { ...U, traded_on_eval_date: false, exclude_price_breaks: false }, logic: 'all', conditions: [
      { id: 'a', enabled: true, test: { kind: 'value', op: 'gt', value: 0, metric: ind('I13', 'rsi') } },
      { id: 'b', enabled: true, test: { kind: 'state', lhs: close, op: 'gt', rhs: ind('I01', 'sma', { length: 5 }) } }] });
    const r = runScreen({ ...d, logic: 'at_least', at_least: 1 }, cold());
    const stale = r.rows.find(x => x.ticker === 'STAL')!, broke = r.rows.find(x => x.ticker === 'PBSA')!;
    expect([stale.stale, stale.last_bar_date, stale.cells[0].eval_date, stale.remarks]).toEqual([true, STALE.dates[504], STALE.dates[504], [{ code: 'STALE', last_bar_date: STALE.dates[504] }]]);
    expect(broke.remarks[0]).toMatchObject({ code: 'PRICE_BREAK', ex_date: EX });
    expect([broke.cells[0].remark, typeof broke.cells[0].value, broke.cells[1].remark]).toEqual(['PRICE_BREAK_IN_LOOKBACK', 'number', null]);   // RSI recursive; SMA(5) past it
    expect(r.warnings).toContainEqual(expect.objectContaining({ code: 'PRICE_BREAKS_IN_RESULT', details: { rows: 1, cells: 1 } }));
  });
  it('the 74-bar ticker is NA INSUFFICIENT_HISTORY on SMA(200), never a fabricated value', () => {
    const d = norm({ universe: { ...U, tickers: ['RANS'] }, logic: 'any', conditions: [
      { id: 'a', enabled: true, test: { kind: 'state', lhs: close, op: 'gt', rhs: ind('I01', 'sma', { length: 200 }) } },
      { id: 'b', enabled: true, test: { kind: 'value', op: 'gt', value: 0, metric: ind('I13', 'rsi') } }] });
    const p = previewCells(d, cold(), 'RANS');
    expect(p.cells[0]).toMatchObject({ status: 'na', reason: 'INSUFFICIENT_HISTORY', rhs: null });
    expect([p.status, p.need, p.met]).toEqual([p.met >= 1 ? 'match' : 'fail', 1, p.met]);
  });
  it('a metric filter that needs a formula drops the tickers it fails (and NA ones), counted in filtered_out', () => {
    const d = norm({ universe: { ...U, metric_filters: [{ kind: 'value', op: 'gt', value: 50, metric: ind('I13', 'rsi') }] }, logic: 'all', conditions: [] });
    const r = runScreen(d, cold());
    const keep = TICKERS.filter(t => t !== STALE && t !== BROKE).filter(t => (F.rsi(t.bars, {}).rsi.at(-1) ?? -1) > 50).map(t => t.ticker).sort();
    expect(r.rows.map(x => x.ticker).sort()).toEqual(keep);
    expect(r.universe.filtered_out).toBe(61 - keep.length);
  });
  it('turning a chip off moves no rank: return_rank is computed on the fixed population', () => {
    const rank = (u: Definition['universe']) => runScreen(norm({ universe: u, logic: 'all', conditions: [
      { id: 'r', enabled: true, test: { kind: 'value', op: 'between', value: 0, value2: 100, metric: { kind: 'xsection', metric: 'return_rank', params: { window: 60 } } } }] }), cold());
    const on = rank(U), off = rank({ ...U, traded_on_eval_date: false, exclude_price_breaks: false });
    const v = (r: ReturnType<typeof rank>) => new Map(r.rows.map(x => [x.ticker, x.cells[0].value]));
    for (const [t, x] of v(on)) expect([t, v(off).get(t)]).toEqual([t, x]);
    expect(off.rows.find(x => x.ticker === 'PBSA')!.cells[0].remark).toBe('PRICE_BREAK_IN_LOOKBACK');   // ex-date inside (at - 60, at]
  });
});

describe('the run answer', () => {
  it('names each condition as report 8.5 does, with parameters, default flag, kind and unit', () => {
    const r = runScreen(SCREENS[0], cold());
    expect(r.conditions.map(c => [c.id, c.metric, c.is_default, c.kind, c.unit])).toEqual([
      ['a', 'I13.rsi', false, 'value', 'dimensionless'], ['b', 'I01.sma', false, 'state', 'price'],
      ['c', 'I06.macd x I06.signal', true, 'event', 'price_change'], ['d', 'I10.upper', true, 'state', 'price']]);
    expect(r.conditions[1].params_resolved).toEqual({ length: 50, source: 'close' });
    expect(r.rows.every((x, i, a) => i === 0 || (a[i - 1].status === 'match' && x.status === 'near') || (a[i - 1].status === x.status && a[i - 1].met >= x.met))).toBe(true);
    const any = runScreen(SCREENS[1], cold());
    expect(any.warnings.map(w => w.code)).toContain('NO_PRUNING_FOR_ANY');
  });
  it('refuses a definition costed above the budget before any compute, naming the costliest condition', () => {
    const env = memoryEnv(TICKERS, IX, rows, E, { maxCpuMs: 10, predictMs: r => r.label.startsWith('I13') ? 1 : 0.001 });
    let e: unknown;
    try { runScreen(SCREENS[0], env) } catch (x) { e = x }
    expect(e).toBeInstanceOf(ScreenerError);
    expect([(e as ScreenerError).code, (e as ScreenerError).details]).toEqual(['LIMIT_EXCEEDED', { limit: 'compute_budget', allowed: 10, needed: expect.any(Number), costliest: 'a' }]);
    expect(env.computed).toBe(0);
  });
  it('previews one ticker with the one near rule, outside the universe too', () => {
    const p = previewCells(SCREENS[0], cold(), 'STAL');
    expect(p.status).toBe('outside_universe');
    expect(p.cells.map(c => c.id)).toEqual(['a', 'b', 'c', 'd']);
    const q = previewCells(SCREENS[0], cold(), 'S01'), r = runScreen(SCREENS[0], cold()).rows.find(x => x.ticker === 'S01');
    expect(q.status).toBe(r ? r.status : 'fail');
    expect(() => previewCells(SCREENS[0], cold(), 'NOPE')).toThrow(ScreenerError);
  });
});

describe('presets on the synthetic market', () => {
  it('every available preset runs; Minervini prunes and still equals its exhaustive run', () => {
    const env = cold();
    for (const p of PRESETS.presets.filter(x => x.category === 'Technical' && x.id !== 'ichi')) {
      const d = norm({ ...p.definition, universe: { ...p.definition.universe, price_min: null, adv20_min_idr: null } });
      const a = runScreen(d, env), b = runScreen(d, env, { exhaustive: true });
      expect([p.id, a.rows]).toEqual([p.id, b.rows]);
    }
    void OPTS; void WITHIN_MAX;
  });
});

describe('the snapshot\'s declared series', () => {
  it('pre-warming the declared series makes the default cards of rising, vs-MA and the Donchian prior band snapshot lookups', async () => {
    const { declaredDerivedSeries } = await import('../../src/core/condition.ts');
    const d = declaredDerivedSeries(OPTS);
    expect(d.map(r => r.label)).toEqual(expect.arrayContaining(['lag(I10.upper, 1)', 'lag(I10.lower, 1)', 'lag(I01.sma, 5)', 'ma(I40.obv, EMA, 20)', 'ma(I50.nvi, EMA, 255)', 'lag(I40.obv, 20)']));
    const env = memoryEnv(TICKERS, IX, rows, E);
    const start = (await import('../../src/core/registry.ts')).INDICATORS.flatMap(r => r.outputs.map(o => bindCondition({ id: 'x', enabled: true,
      test: { kind: 'value', op: 'gt', value: 0, metric: { kind: 'indicator', indicator: r.id, output: o.key, params: { ...r.start_params } } } }, 'c', env).series)).flat();
    env.prewarm([...start, ...d]);
    const card = norm({ universe: U, logic: 'all', conditions: [
      { id: 'a', enabled: true, test: { kind: 'state', lhs: close, op: 'gt', rhs: ind('I10', 'upper') } },
      { id: 'b', enabled: true, test: { kind: 'state', lhs: ind('I40', 'obv'), op: 'gt', rhs: { kind: 'transform', fn: 'ma', of: ind('I40', 'obv') } } }] });
    const r = runScreen(card, env);
    expect(r.conditions.map(c => c.source)).toEqual(['precomputed', 'precomputed']);
    expect(env.computed).toBe(0);
  });
});

describe('is_default and params_resolved (report 8.5)', () => {
  it('are taken through transforms: the indicator inside at registry defaults, every argument at the catalog default', () => {
    const summary = (test: unknown) => bindCondition({ id: 'x', enabled: true, test: validateTest(test, 't', CTX) }, 'c', { ...OPTS, withinMax: WITHIN_MAX }).summary;
    const pd = (params?: Record<string, unknown>) => ({ kind: 'value', op: 'gt', value: 0, metric: { kind: 'transform', fn: 'pct_distance', of: ind('I01', 'sma', params) } });
    expect([summary(pd()).is_default, summary(pd()).params_resolved]).toEqual([true, { length: 20, source: 'close' }]);
    expect([summary(pd({ length: 50 })).is_default, summary(pd({ length: 50 })).params_resolved]).toEqual([false, { length: 50, source: 'close' }]);
    const hi52 = { kind: 'value', op: 'gt', value: -25, metric: { kind: 'transform', fn: 'pct_distance', of: { kind: 'transform', fn: 'rolling_max', of: { kind: 'price', field: 'high' }, args: { length: 252 } } } };
    expect(summary(hi52).is_default).toBe(true);
    const rising = (bars: number) => ({ kind: 'state', lhs: ind('I01', 'sma'), op: 'gt', rhs: { kind: 'transform', fn: 'lag', of: ind('I01', 'sma'), args: { bars } } });
    expect([summary(rising(5)).is_default, summary(rising(21)).is_default]).toEqual([true, false]);
    expect(summary({ kind: 'state', lhs: close, op: 'gt', rhs: ind('I43', 'vwap', { anchor: 'Week' }) }).is_default).toBe(false);   // P17: never the registry default
    expect(summary({ kind: 'event', within: 3, signal: { pattern: { kind: 'pattern', type: 'breakout', params: { length: 252 } } } })).toMatchObject({ is_default: false, metric: 'breakout', params_resolved: { length: 252 } });
  });
});
