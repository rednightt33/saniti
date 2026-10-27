/* stats.ts against the page's own section-9 code (tests/stats-oracle.mjs) on random and edge-case series. stats.ts
   uses the page's formulas in the page's operation order (left-to-right sums from 0, the same `**` powers, the same
   divisions), so every number must be equal bit for bit: deepStrictEqual (Object.is, NaN equals NaN), no tolerance. */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import * as S from '../../edge-bff/backtest/src/core/stats.ts';
import * as O from './stats-oracle.mjs';

/* deterministic random numbers for the test data (mulberry32) */
function rng(seed: number) {
  let a = seed >>> 0;
  return () => { a = (a + 0x6D2B79F5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296 };
}
const walk = (r: () => number, n: number, start = 1e9, vol = 0.02, drift = 0.0003) => {
  const v = [start]; for (let k = 1; k < n; k++) v.push(v[k - 1] * (1 + drift + vol * (r() - 0.5) * 2 + (r() < 0.02 ? -0.08 : 0)));
  return v;
};
const pageSeries = (s: any) => { const { psr, ...rest } = s; return { ...rest, psr0: psr(0), psrA: psr(0.05), psrB: psr(-0.1) } };
const sameSeries = (vals: number[], bench?: number[] | null, label = '') =>
  assert.deepStrictEqual(pageSeries(S.seriesStats(vals, bench)), pageSeries(O.seriesStats(vals, bench ?? undefined)), label);

test('helpers equal the page: mean, sd, skew, kurt, quant, ncdf, ninv', () => {
  const r = rng(1);
  for (let n = 0; n < 60; n++) {
    const a = Array.from({ length: n }, () => (r() - 0.5) * (r() < 0.5 ? 1 : 1e6));
    for (const f of ['mean', 'sd', 'skew', 'kurt'] as const) assert.ok(Object.is((S as any)[f](a), (O as any)[f](a)), `${f} n=${n}`);
    for (const q of [0, .01, .05, .25, .5, .75, .95, .99, 1]) assert.ok(Object.is(S.quant(a, q), O.quant(a, q)), `quant ${q} n=${n}`);
  }
  for (let k = 0; k < 2000; k++) { const x = (r() - 0.5) * 16; assert.ok(Object.is(S.ncdf(x), O.ncdf(x)), `ncdf ${x}`) }
  for (const p of [1e-12, 1e-6, .001, .02, .02425, .0243, .1, .5, .9, .97575, .98, .999, 1 - 1e-9])
    assert.ok(Object.is(S.ninv(p), O.ninv(p)), `ninv ${p}`);
  for (let k = 0; k < 2000; k++) { const p = r(); assert.ok(Object.is(S.ninv(p), O.ninv(p)), `ninv ${p}`) }
  assert.equal(S.quant([], .5), undefined);                                    // the page's empty quantile
});

test('seriesStats equals the page on random walks with and without a benchmark', () => {
  const r = rng(2);
  for (const n of [2, 3, 4, 5, 6, 21, 22, 60, 127, 128, 252, 253, 600, 1900]) for (let rep = 0; rep < 3; rep++) {
    const vals = walk(r, n, 1e9 * (1 + r())), bench = walk(r, n, 1e9, 0.012, 0.0002);
    sameSeries(vals, bench, `n=${n}`);
    sameSeries(vals, null, `n=${n} no bench`);
    sameSeries(bench, undefined, `bench n=${n}`);
    sameSeries(vals, bench.slice(1), `n=${n} unaligned bench (beta null)`);
  }
});

test('seriesStats edge cases equal the page: empty, one value, flat, zero volatility, the 3/4-return skew rule', () => {
  const cases: [string, number[]][] = [
    ['empty', []], ['one value', [1e9]], ['two values', [1e9, 1.1e9]], ['flat', Array(30).fill(1e9)],
    ['flat short', [5, 5, 5, 5]], ['zero volatility (constant return)', [1, 2, 4, 8, 16, 32]],
    ['three returns', [100, 101, 99, 102]], ['four returns', [100, 101, 99, 102, 98]],
    ['only gains', [100, 101, 103, 106, 110, 115]], ['only losses', [100, 99, 97, 94, 90, 85, 79]],
    ['one big drop', [...Array(40).fill(100), 50, ...Array(40).fill(50)]],
  ];
  for (const [label, v] of cases) {
    sameSeries(v, null, label);
    if (v.length) sameSeries(v, v.map((x, k) => 1000 + k), `${label} with bench`);
  }
  // what the page shows as '—' goes out as null
  const flat = S.toSeriesStats(S.seriesStats(Array(30).fill(1e9)));
  assert.equal(flat.sharpe, 0); assert.equal(flat.skew, null); assert.equal(flat.kurtosis, null); assert.equal(flat.psr_0, null);
  const one = S.toSeriesStats(S.seriesStats([1e9]));
  assert.equal(one.n_returns, 0); assert.equal(one.skew, 0); assert.equal(one.kurtosis, 3); assert.equal(one.psr_0, null);
  for (const s of [flat, one]) for (const [k, x] of Object.entries(s)) assert.ok(x === null || Number.isFinite(x), `${k} = ${x}`);
});

/* page trade fields from a ledger-style trade */
const pageTrade = (t: S.StatTrade) => ({ ret: t.return, pnl: t.pnl_idr, riskPct: t.initial_risk_pct, bars: t.bars_held, mae: t.mae, mfe: t.mfe });
const mkTrades = (r: () => number, n: number, opt: { win?: number; risk?: 'mixed' | 'none' | 'all'; ret?: number } = {}): S.StatTrade[] =>
  Array.from({ length: n }, () => {
    const ret = opt.ret ?? (r() < (opt.win ?? 0.45) ? r() * 0.3 : -r() * 0.12), cost = 1e7 * (1 + 9 * r());
    const risk = opt.risk === 'none' ? null : opt.risk === 'all' ? 0.02 + r() * 0.08 : (r() < 0.3 ? null : r() < 0.1 ? 0 : 0.02 + r() * 0.08);
    return { return: ret, pnl_idr: ret * cost, initial_risk_pct: risk, bars_held: 1 + Math.floor(r() * 40), mae: -r() * 0.15, mfe: r() * 0.35 };
  });
const sameTrades = (T: S.StatTrade[], label: string) => assert.deepStrictEqual(S.tradeStats(T), O.tradeStats(T.map(pageTrade)), label);

test('tradeStats equals the page: random ledgers, no trade, one trade, all wins, all losses, zero returns, no stops, SQN cap', () => {
  const r = rng(3);
  for (const n of [2, 3, 5, 17, 99, 100, 101, 400]) for (let rep = 0; rep < 4; rep++) sameTrades(mkTrades(r, n), `random n=${n}`);
  sameTrades([], 'no trade');
  sameTrades(mkTrades(r, 1), 'one trade');
  sameTrades(mkTrades(r, 1, { win: 1 }), 'one win');
  sameTrades(mkTrades(r, 12, { win: 1 }), 'all wins');
  sameTrades(mkTrades(r, 12, { win: 0 }), 'all losses');
  sameTrades(mkTrades(r, 6, { ret: 0 }), 'zero returns (losses on the page)');
  sameTrades(mkTrades(r, 6, { ret: 0.05 }), 'identical returns (sd 0: fallback risk 1 %)');
  sameTrades(mkTrades(r, 30, { risk: 'none' }), 'no stops: fallback risk');
  sameTrades(mkTrades(r, 30, { risk: 'all' }), 'every trade with a stop');
  sameTrades(mkTrades(r, 250, { win: 0.6 }), 'SQN n capped at 100');
  const wins = S.toTradeStats(S.tradeStats(mkTrades(r, 5, { win: 1 })));
  assert.equal(wins.profit_factor, 'inf'); assert.equal(wins.losses, 0);
  const none = S.toTradeStats(S.tradeStats([]));
  assert.equal(none.profit_factor, 0); assert.equal(none.n, 0);
  for (const s of [wins, none]) for (const [k, x] of Object.entries(s)) assert.ok(x === 'inf' || Number.isFinite(x), `${k} = ${x}`);
});

test('dsr equals the page for trial counts and Sharpe lists of every size', () => {
  const r = rng(4);
  for (const n of [1, 2, 5, 60, 500]) {
    const vals = walk(r, n + 1), st = S.seriesStats(vals), so = O.seriesStats(vals);
    for (const trials of [0, 1, 2, 3, 26, 27, 300]) for (const m of [0, 1, 2, 25, 26]) {
      const srs = Array.from({ length: m }, () => (r() - 0.4) * 0.1);
      assert.deepStrictEqual(S.dsr(st, trials, srs), O.dsr(so, trials, srs), `n=${n} trials=${trials} srs=${m}`);
    }
  }
  const flat = S.seriesStats(Array(30).fill(1));
  assert.ok(Number.isNaN(S.dsr(flat, 26, [0.01, 0.02]).dsr));                 // the page's NaN on a flat curve
});
