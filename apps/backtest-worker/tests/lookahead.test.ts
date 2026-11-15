/* EXEC-BACKTEST-REVAMP P6 (user decision 3, 2026-11-15: the look-ahead test is a mandatory CI gate; ERRORS M446): a value
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
import { REGISTRY, resolveParams } from '../../edge-bff/backtest/src/core/registry.ts';
import { Calc, FLOW, PRICE_ACTION, flowCondition, priceActionCondition } from '../../edge-bff/backtest/src/core/conditions.ts';
import { CANDLE_IDS, candleSignal } from '../../edge-bff/backtest/src/core/candles.ts';
import { flowData } from '../../edge-bff/backtest/src/core/flow.ts';
import { prepare, run } from '../../edge-bff/backtest/src/core/engine.ts';
import { IMPLEMENTED_PATTERNS, IMPLEMENTED_TRANSFORMS, resolveSignal } from '../../edge-bff/screener/src/core/transforms.ts';
import { resolveSeries, tickerCalc } from '../../edge-bff/screener/src/core/metrics.ts';
import { SCREENER_REGISTRY } from '../../edge-bff/screener/src/core/registry.ts';
import { head, market, type Row, type Ticker } from './lookahead/fixture.ts';

const M = market(), A = M.stocks[0], N = A.dates.length, CUTS = [150, 260, 390, 520];
const TERMINAL_HINDSIGHT = ['FL18', 'FL19', 'FL20', 'FL23', 'FL44', 'FL45', 'FL51', 'FL52'];   // ERRORS M446; the backtest uses point-in-time versions

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

test('the 53 registry indicators: defaults, short, long and extreme numbers, every option', () => {
  const leaks: string[] = []; let runs = 0;
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

test('Flow FL01-FL52 with every option: only the Terminal hindsight group reads future data (ERRORS M446)', () => {
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
  const tickerData = (t: Ticker, n: number | null, flow: boolean) => {
    const k = n ?? t.dates.length, h = head(t, k), d = h.dates;
    return { prices: { ticker: t.ticker, dates: d, bars: h.bars, dropped: 0 }, corporate_actions: [],
      ...(flow ? { flow: flowData(M.rows[t.ticker].filter(r => r.d <= d[d.length - 1]), d) } : {}) };
  };
  const cutDate = (k: number) => A.dates[k];
  const marketAt = (to: string | null, flow: boolean) => {
    const n = (t: Ticker) => to === null ? null : t.dates.filter(d => d <= to).length;
    return { ihsg: { ticker: 'IHSG', dates: head(M.ihsg, n(M.ihsg) ?? N).dates, bars: head(M.ihsg, n(M.ihsg) ?? N).bars, dropped: 0 },
      tickers: Object.fromEntries(M.stocks.map(t => [t.ticker, tickerData(t, n(t), flow)])) };
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
  const cases: [string, Record<string, unknown>, boolean][] = [
    ['single', base({ mode: 'single', single: { ticker: 'AAAA', benchmark: 'buy_and_hold' }, entry: { logic: 'any', at_least: 1, window_bars: 3, conditions: [RSI, BRK] } }), false],
    ['portfolio fnet', base({ mode: 'portfolio', portfolio: { tickers: ['AAAA', 'BBBB', 'SUSP'], max_positions: 2, rank_by: 'fnet', min_avg_value_20d_idr: 0 },
      entry: { logic: 'any', at_least: 1, window_bars: 2, conditions: [RSI, FNET] } }), true],
  ];
  const strip = (x: unknown) => JSON.parse(JSON.stringify(x, (k, v) => k === 'duration_ms' ? undefined : v));
  for (const [name, q, flow] of cases) for (const k of CUTS) {
    const req = { ...q, period: { ...(q.period as object), to: cutDate(k) } } as never;
    const a = strip(run(prepare(marketAt(null, flow) as never), req)), b = strip(run(prepare(marketAt(cutDate(k), flow) as never), req));
    assert.deepEqual(b, a, `${name} cut ${cutDate(k)}`);
  }
});
