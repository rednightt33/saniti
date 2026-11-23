/* EXEC-BACKTEST-REVAMP P6 (user decision 3, 2026-11-15: the look-ahead test is a mandatory CI gate; ERRORS M448): a value
   on day t may use only data up to t. For every series the backtest can read, the value computed on the full data and the
   value computed on the data cut at t must be equal on every day up to t. The series are derived from the registries
   (the 53 indicators with short, long and extreme parameters and every option; the transform functions and pattern
   types the shared grammar implements; the 20 candles; the Flow indicators with every option), so a new entry is covered
   without a list here, and a coverage check fails when one has no case. The engine is checked as a whole too: the same
   request on the full data and on the data cut at t gives the same ledger. A deliberately leaking series (a centred
   moving average) must be caught (self-test). Synthetic data only (tests/lookahead/fixture.ts); the real-data run is
   verification/backtest/lookahead/real_data.ts. */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { F } from '../../edge-bff/terminal/src/calc/indicators.ts';
import * as TF from '../../edge-bff/terminal/src/calc/flow.ts';
import FLOW_REG from '../../edge-bff/terminal/src/data/flowRegistry.json' with { type: 'json' };
import { REGISTRY, ValidationError, resolveParams } from '../../edge-bff/backtest/src/core/registry.ts';
import { Calc, FLOW, PRICE_ACTION, conditionSeries, flowCondition, priceActionCondition } from '../../edge-bff/backtest/src/core/conditions.ts';
import { CANDLE_IDS, candleSignal } from '../../edge-bff/backtest/src/core/candles.ts';
import { flowData } from '../../edge-bff/backtest/src/core/flow.ts';
import { prepare, run } from '../../edge-bff/backtest/src/core/engine.ts';
import { IMPLEMENTED_PATTERNS, IMPLEMENTED_TRANSFORMS, resolveSignal } from '../../edge-bff/screener/src/core/transforms.ts';
import { resolveSeries, tickerCalc } from '../../edge-bff/screener/src/core/metrics.ts';
import { SCREENER_REGISTRY } from '../../edge-bff/screener/src/core/registry.ts';
import { brokerColumns, head, market, type Row, type Ticker } from './lookahead/fixture.ts';
import { installBacktestGrammar, seriesOfRef } from '../src/grammar.ts';
import { onPriceBasis } from '../../edge-bff/backtest/src/core/datafile.ts';
import type { BasisAction } from '../../edge-bff/backtest/src/core/datafile.ts';

installBacktestGrammar();
const M = market(), A = M.stocks[0], N = A.dates.length, CUTS = [150, 260, 390, 520];
const TERMINAL_HINDSIGHT = ['FL18', 'FL19', 'FL20', 'FL23', 'FL44', 'FL45', 'FL51', 'FL52'];   // ERRORS M448; the backtest uses point-in-time versions

type Out = Record<string, unknown> | null;
const num = (v: unknown) => typeof v === 'number' && Number.isFinite(v) ? v : null;
/** The first difference on days up to each cut between `run(N)` and `run(cut + 1)`; null when none. */
function leak(runAt: (n: number) => Out, cuts = CUTS, total = N): string | null {
  const full = runAt(total);
  if (!full) return null;
  for (const c of cuts) {
    const part = runAt(c + 1) ?? {};
    for (const k of new Set([...Object.keys(full), ...Object.keys(part)])) {
      if (k.startsWith('_')) continue;
      const a = full[k] as ArrayLike<unknown> | undefined, b = part[k] as ArrayLike<unknown> | undefined;
      if (!a || !b || typeof a.length !== 'number' || typeof b.length !== 'number') { if (!a !== !b) return `cut ${c}: output ${k} only with ${a ? 'the full' : 'the cut'} data`; continue }
      for (let i = 0; i <= c; i++) {
        const x = num(a[i]), y = num(b[i]);
        if ((x === null) !== (y === null) || (x !== null && y !== null && Math.abs(x - y) > 1e-9 * Math.max(1, Math.abs(x)))) return `cut ${c}: ${k}[${i}] full ${a[i]} vs cut ${b[i]}`;
      }
    }
  }
  return null;
}
const bars = (t: Ticker, n: number) => head(t, n).bars;
const safely = (f: () => Out): Out => { try { return f() } catch { return null } };   // a refused setting is not a series

test('self-test: a centred moving average (it reads the next bars) is caught', () => {
  const centred = (n: number) => { const c = bars(A, n).C as number[]; return { v: c.map((_, i) => i < 2 || i + 2 >= c.length ? null : (c[i - 2] + c[i - 1] + c[i] + c[i + 1] + c[i + 2]) / 5) } };
  assert.match(leak(centred) ?? '', /cut/);
});

test('every registry indicator (53 released and any at the lab stage): defaults, short, long and extreme numbers, every option', () => {
  const leaks: string[] = []; let runs = 0;
  // every registry indicator has its formula in this process (a lab one through loader/register.mjs): `safely` below
  // reads a refused setting as no series, so a missing formula would pass the gate unseen (lab dry run, 2026-11-23)
  assert.deepEqual(REGISTRY.indicators.filter(r => typeof F[r.key] !== 'function').map(r => r.id), []);
  // ... and computes: its defaults run outside `safely` and give at least one finite value, so a formula that throws on
  // every call (a missing DEFAULTS entry, a wrong need) fails here naming it (test-out of 2026-11-23, LLA-F1)
  const dead: string[] = [];
  for (const r of REGISTRY.indicators) {
    try {
      const out = F[r.key](bars(A, N), resolveParams(r, {})) as Record<string, unknown> | null;
      const finite = Object.values(out ?? {}).some(a => a != null && typeof (a as ArrayLike<unknown>).length === 'number'
        && Array.from(a as ArrayLike<unknown>).some(x => num(x) !== null));
      if (!finite) dead.push(`${r.id}: no finite value at its defaults`);
    } catch (e) { dead.push(`${r.id}: ${(e as Error).message}`) }
  }
  assert.deepEqual(dead, []);
  for (const r of REGISTRY.indicators) {
    const variants: Record<string, unknown>[] = [{}];
    for (const p of r.params) {
      if (p.type === 'integer' || p.type === 'number') {
        const d = Number(p.default), lo = p.min ?? (p.type === 'integer' ? 1 : d / 4), hi = p.max ?? d * 10;
        for (const v of [lo, Math.min(hi, d * 3), hi, p.type === 'integer' ? Math.min(hi, 400) : hi]) variants.push({ [p.key]: p.type === 'integer' ? Math.round(v) : v });
      } else if (p.type === 'enum') for (const o of p.options ?? []) variants.push({ [p.key]: o });
      else if (p.type === 'boolean') variants.push({ [p.key]: true }, { [p.key]: false });
    }
    for (const v of variants) {
      let params: Record<string, unknown>;
      try { params = resolveParams(r, v) } catch { continue }
      runs++;
      const l = leak(n => safely(() => F[r.key](bars(A, n), params)));
      if (l) leaks.push(`${r.id} ${JSON.stringify(v)}: ${l}`);
    }
  }
  assert.ok(runs > 200, `${runs} parameter sets`);
  assert.deepEqual(leaks, []);
});

test('the price-action conditions, every operator, and the core flow conditions', () => {
  const leaks: string[] = [];
  for (const [type, spec] of Object.entries(PRICE_ACTION)) for (const op of spec.ops) {
    const cond = { id: 'x', kind: 'price_action', type, op, ...(spec.value ? { value: type === 'dip' ? -0.02 : 1.5 } : {}) } as Parameters<typeof priceActionCondition>[1];
    const l = leak(n => ({ s: priceActionCondition(new Calc(bars(A, n)), cond) }));
    if (l) leaks.push(`${type}:${op}: ${l}`);
  }
  for (const t of M.stocks) for (const type of Object.keys(FLOW)) for (const length of [1, 5, 20]) {
    const cond = { id: 'f', kind: 'flow', type, op: 'gt', params: { length, ...(type === 'broker' ? { broker: 'SQ' } : {}) }, value: 0 } as Parameters<typeof flowCondition>[1];
    const total = t.dates.length, cuts = CUTS.filter(c => c < total - 1);
    const l = leak(n => { const d = t.dates.slice(0, n), rows = M.rows[t.ticker].filter(r => r.d <= d[d.length - 1]);
      return safely(() => ({ s: flowCondition(new Calc(head(t, n).bars, flowData(rows, d)), cond) })) }, cuts, total);
    if (l) leaks.push(`${t.ticker} ${type}(${length}): ${l}`);
  }
  assert.deepEqual(leaks, []);
});

test('the 20 candlestick patterns', () => {
  const leaks = CANDLE_IDS.map(id => [id, leak(n => ({ s: candleSignal(bars(A, n), id) }))]).filter(([, l]) => l);
  assert.equal(CANDLE_IDS.length, 20);
  assert.deepEqual(leaks, []);
});

test('the shared grammar: every transform function and every pattern type it implements', () => {
  const ihsgAt = (n: number) => ({ ticker: 'IHSG', dates: M.ihsg.dates.slice(0, n), bars: head(M.ihsg, n).bars });
  const opts = (n: number) => ({ capBudgetMs: 2000, index: ihsgAt(n) });
  // an operand of the right kind for each function, found in the screener registry by the test forms it offers
  const outputWith = (form: string) => { for (const ind of SCREENER_REGISTRY.indicators) for (const o of ind.outputs) if (o.tests.some(t => t.form === form)) return { kind: 'indicator', indicator: ind.id, output: o.key }; return null };
  const close = { kind: 'price', field: 'close' }, volume = { kind: 'price', field: 'volume' }, open = { kind: 'price', field: 'open' };
  const ofFor: Record<string, unknown> = { pct_distance: outputWith('value_pct_distance'), band_position: outputWith('value_band_position') };
  const leaks: string[] = [], ran = new Set<string>();
  for (const fn of IMPLEMENTED_TRANSFORMS) {
    const ref: Record<string, unknown> = { kind: 'transform', fn, of: ofFor[fn] ?? close,
      args: fn === 'ratio' ? { by: volume } : fn === 'relative' ? { by: open } : {} };
    const l = leak(n => { const t = tickerCalc({ ticker: A.ticker, dates: A.dates.slice(0, n), bars: bars(A, n) });
      const r = resolveSeries(ref as never, 'gate', opts(n)); ran.add(fn); return { s: r.full(t) as ArrayLike<unknown> } });
    if (l) leaks.push(`${fn}: ${l}`);
  }
  for (const type of IMPLEMENTED_PATTERNS) {
    let ok = true;
    const l = leak(n => { const t = tickerCalc({ ticker: A.ticker, dates: A.dates.slice(0, n), bars: bars(A, n) });
      try { return { s: resolveSignal({ kind: 'pattern', type, params: {} } as never, 'gate', opts(n)).full(t) as ArrayLike<unknown> } } catch { ok = false; return null } });
    if (ok) ran.add(`pattern:${type}`);
    if (l) leaks.push(`pattern ${type}: ${l}`);
  }
  assert.deepEqual(IMPLEMENTED_TRANSFORMS.filter(fn => !ran.has(fn)), [], 'a transform function without a gate case');
  assert.ok(IMPLEMENTED_PATTERNS.filter(t => ran.has(`pattern:${t}`)).length >= 20);
  assert.deepEqual(leaks, []);
});

test('Flow FL01-FL52 with every option: only the Terminal hindsight group reads future data (ERRORS M448)', () => {
  const ctxAt = (t: Ticker, rows: Row[], n: number): TF.FlowContext => {
    const d = t.dates.slice(0, n), at = new Map(d.map((x, k) => [x, k])), b = head(t, n).bars;
    return { rows: TF.flowRows(rows.filter(r => r.d <= d[d.length - 1]), n, x => at.get(x) ?? -1), dates: d, close: b.C as number[], volume: b.V as number[],
      insider: [], classification: { AA: 'Institutional-heavy', BK: 'Retail-heavy', SQ: 'Institutional-heavy', YP: 'Retail-heavy', XL: 'Mixed' } };
  };
  const leaking = new Set<string>(); let runs = 0;
  for (const r of (FLOW_REG as { indicators: { id: string; params: { key: string; kind: string; options?: unknown[] }[] }[] }).indicators) {
    const variants: Record<string, unknown>[] = [{}];
    for (const q of r.params) {
      const opts = q.kind === 'select' ? (q.options ?? []).map(o => Array.isArray(o) ? o[0] : o) : q.kind === 'bool' ? [true, false] : q.kind === 'multi' ? (q.options ?? []).map(o => [Array.isArray(o) ? o[0] : o]) : [];
      for (const v of opts) variants.push({ [q.key]: v });
    }
    for (const v of variants) {
      runs++;
      if (leak(n => safely(() => TF.computeFlow(r.id, ctxAt(A, M.rows[A.ticker], n), v) as Out))) leaking.add(r.id);
    }
  }
  assert.ok(runs > 400, `${runs} variants`);
  assert.deepEqual([...leaking].sort(), TERMINAL_HINDSIGHT);
});

test('the engine as a whole: the same request on the full data and on the data cut at t gives the same ledger', () => {
  // P9 ('action'): AAAA as published after a rights issue at session 260 with factor 1.4: the fixture's prices
  // (adjusted), its broker lots before the ex date on the traded scale, and the publisher's basis {terms, 1.4}, kept whole
  // at every cut (it is part of the published price history)
  const EX = A.dates[260], FX = 1.4, BASIS: BasisAction[] = [{ ex: EX, type: 'RIGHT_ISSUE', factor: FX, status: 'terms', price: 'adjusted' }];
  const tickerData = (t: Ticker, n: number | null, flow: boolean | 'action') => {
    const k = n ?? t.dates.length, h = head(t, k), d = h.dates, act = flow === 'action' && t.ticker === 'AAAA';
    const rows = M.rows[t.ticker].filter(r => r.d <= d[d.length - 1]).map(r => act && r.d < EX ? { ...r, bl: r.bl / FX, sl: r.sl / FX } : r);
    return { prices: { ticker: t.ticker, dates: d, bars: h.bars, dropped: 0 }, corporate_actions: act ? [{ date: EX, type: 'RIGHT_ISSUE' }] : [],
      ...(flow ? { flow: flowData(rows, d), broker: onPriceBasis(brokerColumns(rows), act ? BASIS : []), ...(act ? { basis: BASIS } : {}) } : {}) };
  };
  const cutDate = (k: number) => A.dates[k];
  const marketAt = (to: string | null, flow: boolean | 'action') => {
    const n = (t: Ticker) => to === null ? null : t.dates.filter(d => d <= to).length;
    return { ihsg: { ticker: 'IHSG', dates: head(M.ihsg, n(M.ihsg) ?? N).dates, bars: head(M.ihsg, n(M.ihsg) ?? N).bars, dropped: 0 },
      tickers: Object.fromEntries(M.stocks.map(t => [t.ticker, tickerData(t, n(t), flow)])), classification: { AA: 'Institutional-heavy', BK: 'Retail-heavy', YP: 'Retail-heavy' } };
  };
  const base = (over: Record<string, unknown>) => ({
    schema_version: 1, period: { from: A.dates[60], to: A.dates[N - 1], oos_fraction: 0 },
    entry: { logic: 'any', at_least: 1, window_bars: 3, conditions: [] as unknown[] },
    exit: { atr_length: 14, stop: { mode: 'atr', pct: 0.07, atr_mult: 2, reward_risk_x: 2, line: { indicator: 'I09', output: 'supertrend' } },
      take_profit: { mode: 'r', pct: 0.15, r_multiple: 2, atr_mult: 3 },
      trailing: { mode: 'chandelier', pct: 0.05, chandelier_length: 22, chandelier_mult: 3, line: { indicator: 'I01', output: 'sma' } },
      max_hold_bars: 30, signals: { logic: 'any', conditions: [] as unknown[] } },
    sizing: { capital_idr: 100_000_000, allocation_fraction: 1 },
    costs: { buy_fee: 0.0015, sell_fee: 0.0025, slippage: 0.001, skip_ara_open_gap: true, ara_gap_fraction: 0.2 },
    robustness: { monte_carlo_runs: 0, seed: 7, sensitivity: false }, ...over });
  const RSI = { id: 'rsi', kind: 'indicator', indicator: 'I13', params: { length: 14 }, lhs: { type: 'output', output: 'rsi' }, op: 'crosses_above', rhs: { type: 'value', value: 40 } };
  const BRK = { id: 'brk', kind: 'price_action', type: 'breakout', params: { length: 20 }, op: 'close_above_high' };
  const FNET = { id: 'fn', kind: 'flow', type: 'fnet', op: 'gt', params: { length: 5 }, value: 0 };
  // Stage C F1 (ERRORS M458): the grammar, its Flow indicators and the point-in-time indicators through the engine too
  // (a leak in the point-in-time comparison or in the empty-series decision left every other case green)
  const test_ = (id: string, t: unknown) => ({ id, kind: 'test', test: t });
  const rsi = { kind: 'indicator', indicator: 'I13', output: 'rsi', params: {} }, close = { kind: 'price', field: 'close' };
  const G_EVENT = test_('ge', { kind: 'event', within: 2, signal: { lhs: { kind: 'flow', metric: 'FL11', params: {} }, op: 'crosses_above', rhs: { value: 0 } } });
  const G_Z = test_('gz', { kind: 'window', mode: 'at_least', length: 10, count: 3, test: { kind: 'value', metric: { kind: 'transform', fn: 'zscore', of: close, args: { length: 40 } }, op: 'gt', value: 0.5 } });
  const G_SEL = test_('gs', { kind: 'state', lhs: { kind: 'flow', metric: 'FL11', params: { scope: 'selected', brokers: ['AA', 'BK'] } }, op: 'gt', rhs: { value: 0 } });
  const D_STATE = test_('ds', { kind: 'state', lhs: close, op: 'gt', rhs: { kind: 'flow', metric: 'FL18', params: { anchor: A.dates[120] } } });
  const D_EVENT = test_('de', { kind: 'event', within: 3, signal: { lhs: { kind: 'flow', metric: 'FL45', params: { anchor: A.dates[100] } }, op: 'crosses_above', rhs: { value: 2 } } });
  const D_VALUE = test_('dv', { kind: 'value', metric: { kind: 'flow', metric: 'FL51', output: 'distance', params: { start: A.dates[90] } }, op: 'lt', value: 0 });
  const cases: [string, Record<string, unknown>, boolean | 'action'][] = [
    ['single', base({ mode: 'single', single: { ticker: 'AAAA', benchmark: 'buy_and_hold' }, entry: { logic: 'any', at_least: 1, window_bars: 3, conditions: [RSI, BRK] } }), false],
    ['portfolio fnet', base({ mode: 'portfolio', portfolio: { tickers: ['AAAA', 'BBBB', 'SUSP'], max_positions: 2, rank_by: 'fnet', min_avg_value_20d_idr: 0 },
      entry: { logic: 'any', at_least: 1, window_bars: 2, conditions: [RSI, FNET] } }), true],
    ['single grammar and Flow', base({ mode: 'single', single: { ticker: 'AAAA', benchmark: 'buy_and_hold' }, entry: { logic: 'any', at_least: 1, window_bars: 3, conditions: [G_EVENT, G_Z, G_SEL] } }), true],
    ['single point in time', base({ mode: 'single', single: { ticker: 'AAAA', benchmark: 'buy_and_hold' }, entry: { logic: 'any', at_least: 1, window_bars: 1, conditions: [D_STATE, D_EVENT, D_VALUE] },
      exit: { ...(base({}).exit as object), signals: { logic: 'any', conditions: [test_('xe', { kind: 'state', lhs: close, op: 'lt', rhs: { kind: 'flow', metric: 'FL19', params: { anchor: A.dates[120] } } })] } } }), true],
    ['portfolio grammar and point in time', base({ mode: 'portfolio', portfolio: { tickers: ['AAAA', 'BBBB', 'SUSP'], max_positions: 2, rank_by: 'fnet', min_avg_value_20d_idr: 0 },
      entry: { logic: 'at_least', at_least: 1, window_bars: 2, conditions: [{ ...test_('pg', { kind: 'event', within: 3, signal: { lhs: rsi, op: 'crosses_above', rhs: { value: 45 } } }) },
        test_('pd', { kind: 'value', metric: { kind: 'flow', metric: 'FL51', output: 'share', params: { start: A.dates[90] } }, op: 'gt', value: 20 })] } }), true],
    ['single published world with a corporate action', base({ mode: 'single', single: { ticker: 'AAAA', benchmark: 'buy_and_hold' }, entry: { logic: 'any', at_least: 1, window_bars: 1,
      conditions: [test_('ca', { kind: 'state', lhs: close, op: 'gt', rhs: { kind: 'flow', metric: 'FL17', params: { window: 10 } } }), D_STATE] } }), 'action'],
    ['portfolio published world with a corporate action', base({ mode: 'portfolio', portfolio: { tickers: ['AAAA', 'BBBB', 'SUSP'], max_positions: 2, rank_by: 'fnet', min_avg_value_20d_idr: 0 },
      entry: { logic: 'any', at_least: 1, window_bars: 2, conditions: [test_('cb', { kind: 'event', within: 3, signal: { lhs: close, op: 'crosses_above', rhs: { kind: 'flow', metric: 'FL17', params: { window: 10 } } } })] } }), 'action'],
    // a series whose first value comes after the first cuts (SMA 200): refused or left out on the bars up to the period's
    // end only, never decided by later bars
    ...(['single', 'portfolio'] as const).map(mode => [`${mode} late series`, base({ mode, ...(mode === 'single' ? { single: { ticker: 'AAAA', benchmark: 'buy_and_hold' } }
      : { portfolio: { tickers: ['AAAA', 'BBBB', 'SUSP'], max_positions: 2, rank_by: 'fnet', min_avg_value_20d_idr: 0 } }),
      entry: { logic: 'all', at_least: 1, window_bars: 1, conditions: [test_('ls', { kind: 'state', lhs: close, op: 'gt', rhs: { kind: 'indicator', indicator: 'I01', output: 'sma', params: { length: 200 } } })] } }), true] as [string, Record<string, unknown>, boolean]),
  ];
  const strip = (x: unknown) => JSON.parse(JSON.stringify(x, (k, v) => k === 'duration_ms' ? undefined : v));
  for (const [name, q, flow] of cases) for (const k of CUTS) {
    const req = { ...q, period: { ...(q.period as object), to: cutDate(k) } } as never;
    // a refusal is part of the outcome: the same on both, with the same code
    const go = (to: string | null) => { try { return strip(run(prepare(marketAt(to, flow) as never), req)) } catch (e) { if (e instanceof ValidationError) return { refused: e.code }; throw e } };
    const a = go(null), b = go(cutDate(k));
    assert.deepEqual(b, a, `${name} cut ${cutDate(k)}`);
    if (k === CUTS[CUTS.length - 1]) assert.ok(a.trades?.length > 0, `${name}: the case trades (${a.trades?.length})`);
  }
});

test('P9: a corporate action: the published world (prices adjusted, lots scaled back by the factor) gives the traded world\'s signals, and no value on day t reads a later day', () => {
  // the fixture is on one basis (broker VWAP near the close); a rights issue at session EX with factor F:
  // traded: the closes before EX are F times the fixture's, the broker lots before EX F times fewer (VWAP F x the close);
  // published: the fixture's closes (adjusted), the same broker rows, the publisher's basis {terms, F}
  const EX = 260, F = 1.4, ex = A.dates[EX], rows = M.rows[A.ticker];
  const traded = rows.map(r => r.d < ex ? { ...r, bl: r.bl / F, sl: r.sl / F } : r);
  const scale = (k: number) => (a: ArrayLike<number | null>) => Array.from(a, (v, i) => i < k && typeof v === 'number' ? v * F : v);
  const tradedBars = (n: number) => { const b = bars(A, n); return { ...b, O: scale(EX)(b.O), H: scale(EX)(b.H), L: scale(EX)(b.L), C: scale(EX)(b.C) } };
  const world = (n: number, published: boolean) => {
    const h = head(A, n), last = h.dates[h.dates.length - 1], r = traded.filter(x => x.d <= last);
    const basis: BasisAction[] = published ? [{ ex, type: 'RIGHT_ISSUE', factor: F, status: 'terms', price: 'adjusted' }] : [{ ex, type: 'RIGHT_ISSUE', factor: 1, status: 'same', price: 'raw' }];
    return new Calc((published ? h.bars : tradedBars(n)) as never, undefined, { ticker: A.ticker, dates: h.dates,
      broker: { columns: onPriceBasis(brokerColumns(r), basis), classification: {}, basis } });
  };
  const fl17 = { kind: 'flow', metric: 'FL17', params: { window: 10 } }, close = { kind: 'price', field: 'close' };
  const cond = { id: 'b', kind: 'test', test: { kind: 'state', lhs: close, op: 'gt', rhs: fl17 } } as never;
  const sig = (c: Calc) => conditionSeries(c, cond, 'b');
  const pub = sig(world(N, true)), trd = sig(world(N, false));
  let same = 0, differs = 0;
  for (let i = 1; i < N; i++) {
    const crosses = i - 9 < EX && i >= EX;                     // the window [i-9, i] reads both sides of the action
    if (crosses) continue;
    if (pub[i] === trd[i]) same++; else differs++;
  }
  assert.equal(differs, 0, `the published world's signal differs from the traded world's on ${differs} bars`);
  assert.ok(same > N - 20, `${same} bars compared`);
  const on = Array.from(pub).filter(Boolean).length;
  assert.ok(on > 30 && on < N - 30, `the condition is on for ${on} bars, off for the others`);
  // without the factor (the lots left on the traded scale) the bars before the action differ, or are emptied by the
  // per-day guard: the factor is what makes the two worlds one
  const raw = sig((() => { const h = head(A, N); return new Calc(h.bars as never, undefined, { ticker: A.ticker, dates: h.dates, broker: { columns: brokerColumns(traded), classification: {}, basis: [] } }) })());
  assert.ok(Array.from({ length: EX - 10 }, (_, k) => k + 10).some(i => raw[i] !== trd[i]), 'the unscaled lots change the signals before the action');
  // the published world on the data cut at t (the basis is part of the published price history, so it is kept)
  const out = (n: number) => ({ fl17: seriesOfRef(world(n, true), fl17, 'f') as unknown as ArrayLike<unknown>, sig: sig(world(n, true)) as unknown as ArrayLike<unknown> });
  assert.equal(leak(out as never), null);
});

test('Stage C2 (user 2026-11-16 "A", ERRORS M459 items 1, 9): before an action is decided, its published status changes no value on day t', () => {
  // a rights issue at session EX decided at DEC (ex + 21 days): the full data publish "terms" or, after a drift,
  // "unresolved"; the data cut at t < DEC published "pending". The lots stay scaled as published (the adjusted history,
  // K4 a). Every Flow value (a broker price and a lot sum alike) on a bar before DEC must not depend on which.
  const EX = 260, ex = A.dates[EX], dec = new Date(Date.parse(ex + 'T00:00:00Z') + 21 * 86_400_000).toISOString().slice(0, 10);
  const DEC = A.dates.findIndex(d => d >= dec), rows = M.rows[A.ticker];
  const action = (status: BasisAction['status']): BasisAction[] => [{ ex, type: 'RIGHT_ISSUE', factor: status === 'terms' ? 1.4 : 1, status, price: 'adjusted', decided: dec }];
  const columns = onPriceBasis(brokerColumns(rows.map(r => r.d < ex ? { ...r, bl: r.bl / 1.4, sl: r.sl / 1.4 } : r)), action('terms'));
  const world = (n: number, basis: BasisAction[]) => { const h = head(A, n), last = h.dates[h.dates.length - 1];
    const keep = new Set(Array.from({ length: columns.rows }, (_, k) => k).filter(k => columns.dates[columns.D[k]] <= last));
    const cut = { ...columns, rows: keep.size, D: columns.D.slice(0, keep.size), B: columns.B.slice(0, keep.size), I: columns.I.slice(0, keep.size), M: columns.M.slice(0, keep.size),
      BV: columns.BV.slice(0, keep.size), SV: columns.SV.slice(0, keep.size), BL: columns.BL.slice(0, keep.size), SL: columns.SL.slice(0, keep.size), BF: columns.BF.slice(0, keep.size), SF: columns.SF.slice(0, keep.size) };
    return new Calc(h.bars as never, undefined, { ticker: A.ticker, dates: h.dates, broker: { columns: cut, classification: {}, basis } }) };
  const refs = [{ kind: 'flow', metric: 'FL17', params: { window: 10 } }, { kind: 'flow', metric: 'FL11', params: {} }, { kind: 'flow', metric: 'FL01', output: 'buy', params: {} }];
  for (const full of ['terms', 'unresolved'] as const) for (const ref of refs) {
    const s = seriesOfRef(world(N, action(full)), ref, 'f');
    for (const k of [EX - 5, EX + 3, EX + 9, DEC - 1]) {
      const p = seriesOfRef(world(k + 1, action('pending')), ref, 'f');
      for (let i = 0; i <= k; i++) assert.equal(p[i] ?? null, s[i] ?? null, `${ref.metric} published ${full}, cut at ${k} (decided at ${DEC}): bar ${i}`);
    }
    // a window across the action (FL17's 10 sessions on bar EX + 3) is empty on every bar before DEC
    if (ref.metric === 'FL17') assert.equal(s[EX + 3] ?? null, null, `${ref.metric}: not decided yet on bar ${EX + 3}`);
  }
});
