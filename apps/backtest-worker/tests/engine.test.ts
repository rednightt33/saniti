/* The execution rules of CONTRACT.md sections 4-6 on small hand-made bar sets with hand-computed fills (the prompt's
   "Execution tests" plus E1, E3, E6, period_end, no_next_bar and suspensions). The entry condition is "volume above
   1,500" (I35 price side = volume) and the exit signal "volume below 500", so a test places signals by setting a
   bar's volume and keeps its prices free for the fills. Prices are chosen so the arithmetic is exact in doubles where
   a test compares to a decimal; where it is not, the expected value is written as the contract's formula in the same
   order of operations, so the comparison is exact. */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { F } from '../../edge-bff/terminal/src/calc/indicators.ts';
import { Cancelled, LEVEL_LINES, MAX_PORTFOLIO_TICKERS, MAX_POSITIONS, prepare, run } from '../../edge-bff/backtest/src/core/engine.ts';
import { leftOut, previewRow } from '../../edge-bff/backtest/src/core/signals.ts';
import type { MarketData } from '../../edge-bff/backtest/src/core/engine.ts';
import type { BacktestRequest, Condition } from '../../edge-bff/backtest/src/core/contract.ts';
import type { Ledger } from '../../edge-bff/backtest/src/core/ledger.ts';
import { ValidationError } from '../../edge-bff/backtest/src/core/registry.ts';
import { toApiError } from '../src/errors.ts';

/* ---- fixtures -------------------------------------------------------------------------------------------- */
const weekdays = (n: number, start: string) => {
  const out: string[] = [];
  for (let t = Date.parse(`${start}T00:00:00Z`); out.length < n; t += 864e5) { const d = new Date(t).getUTCDay(); if (d && d < 6) out.push(new Date(t).toISOString().slice(0, 10)) }
  return out;
};
const DAYS = weekdays(80, '2024-01-01');
interface B { o: number; h: number; l: number; c: number; v: number }
const flat = (n: number, c = 100, v = 1000): B[] => Array.from({ length: n }, () => ({ o: c, h: c, l: c, c, v }));
const bar = (o: number, h: number, l: number, c: number, v = 1000): B => ({ o, h, l, c, v });
const put = (b: B[], i: number, x: Partial<B>) => { b[i] = { ...b[i], ...x }; return b };
const prices = (ticker: string, dates: string[], b: { o: number; h: number; l: number; c: number; v: number | null }[]) =>
  ({ ticker, dates, dropped: 0, bars: { T: dates, O: b.map(x => x.o), H: b.map(x => x.h), L: b.map(x => x.l), C: b.map(x => x.c), V: b.map(x => x.v) } });
interface Spec { bars: B[]; dates?: string[]; actions?: { date: string; type: string }[]; flow?: { fnet: Float64Array; brokers: Map<string, Float64Array> } }
function market(spec: Record<string, Spec>, ihsgDates?: string[]): MarketData {
  const tickers: MarketData['tickers'] = {};
  let n = 0;
  for (const [t, s] of Object.entries(spec)) {
    const d = s.dates ?? DAYS.slice(0, s.bars.length);
    n = Math.max(n, DAYS.indexOf(d[d.length - 1]) + 1);
    tickers[t] = { prices: prices(t, d, s.bars) as any, corporate_actions: s.actions ?? [], flow: s.flow as any };
  }
  const id = ihsgDates ?? DAYS.slice(0, n);
  return { ihsg: prices('IHSG', id, id.map(() => ({ o: 7000, h: 7000, l: 7000, c: 7000, v: null }))) as any, tickers };
}
const VOL = (id = 'v', value = 1500): Condition => ({ id, kind: 'indicator', indicator: 'I35', params: { length: 1 }, lhs: { type: 'price' }, op: 'gt', rhs: { type: 'value', value } });
const QUIET = (id = 'x'): Condition => ({ id, kind: 'indicator', indicator: 'I35', params: { length: 1 }, lhs: { type: 'price' }, op: 'lt', rhs: { type: 'value', value: 500 } });
/** A single-ticker request on AAA over DAYS[from]..DAYS[to], no costs, no exits, 1,000,000 rupiah, all-in. */
function request(to: number, f?: (r: BacktestRequest) => void, from = 0): BacktestRequest {
  const r: BacktestRequest = {
    schema_version: 1, mode: 'single', single: { ticker: 'AAA', benchmark: 'buy_and_hold' },
    period: { from: DAYS[from], to: DAYS[to], oos_fraction: 0 },
    entry: { logic: 'all', at_least: 1, window_bars: 1, conditions: [VOL()] },
    exit: {
      atr_length: 14,
      stop: { mode: 'none', pct: 0.07, atr_mult: 2, reward_risk_x: 2, line: { indicator: 'I09', output: 'supertrend' } },
      take_profit: { mode: 'none', pct: 0.15, r_multiple: 2, atr_mult: 3 },
      trailing: { mode: 'none', pct: 0.05, chandelier_length: 22, chandelier_mult: 3, line: { indicator: 'I01', output: 'sma' } },
      max_hold_bars: 0, signals: { logic: 'any', conditions: [] },
    },
    sizing: { capital_idr: 1_000_000, allocation_fraction: 1 },
    costs: { buy_fee: 0, sell_fee: 0, slippage: 0, skip_ara_open_gap: false, ara_gap_fraction: 0.2 },
    robustness: { monte_carlo_runs: 0, seed: 7, sensitivity: false },
  };
  f?.(r);
  return r;
}
/** Portfolio mode; go() and picking() pick the stocks of the test's market, loaded or left out by the loader, as the
    worker loads exactly the picked stocks (the engine refuses a market of another set: CWP-1). */
const portfolio = (r: BacktestRequest, max = 2, rank: 'adx' | 'fnet' | 'vol' | 'rsi' = 'vol', min = 0) => {
  r.mode = 'portfolio'; delete r.single;
  r.portfolio = { tickers: ['AAA'], max_positions: max, rank_by: rank, min_avg_value_20d_idr: min };
};
const picking = (m: MarketData, r: BacktestRequest): BacktestRequest => r.mode !== 'portfolio' ? r
  : { ...r, portfolio: { ...r.portfolio!, tickers: [...Object.keys(m.tickers), ...(m.excluded ?? []).map(x => x.ticker)] } };
const go = (m: MarketData, r: BacktestRequest): Ledger => run(prepare(m), picking(m, r));
const only = (l: Ledger) => { assert.equal(l.trades.length, 1, JSON.stringify(l.trades.map(t => [t.ticker, t.entry_bar, t.exit_bar, t.exit_reason]))); return l.trades[0] };
const refused = (f: () => unknown) => { try { f() } catch (e) { assert.ok(e instanceof ValidationError, String(e)); return [(e as ValidationError).code, (e as ValidationError).field] } assert.fail('not refused') };

/* ---- the order cycle ------------------------------------------------------------------------------------- */

test('a signal at the close fills at the next open; slippage, fees and whole lots; the end of the test sells at the last close', () => {
  const b = flat(10); put(b, 3, { v: 2000 }); b[4] = bar(101, 103, 100, 102);
  for (let i = 5; i < 10; i++) b[i] = bar(102, 102, 102, 102);
  const l = go(market({ AAA: { bars: b } }), request(9, r => { r.costs = { buy_fee: 0.0015, sell_fee: 0.0025, slippage: 0.0005, skip_ara_open_gap: false, ara_gap_fraction: 0.2 } }));
  const t = only(l);
  assert.deepEqual([t.signal_bar, t.signal_event, t.entry_bar, t.exit_bar, t.exit_reason, t.exit_phase, t.bars_held], [3, 0, 4, 9, 'end_of_test', 'close', 6]);
  // by hand: fill 101 x 1.0005 = 101.0505; 1e6 / (101.0505 x 1.0015) = 9881.2 shares -> 98 lots
  assert.equal(t.shares, 9800);
  assert.equal(t.entry_price, 101 * (1 + 0.0005));
  assert.equal(t.cost_idr, t.entry_price * 9800 * (1 + 0.0015));
  assert.equal(t.exit_price, 102 * (1 - 0.0005));
  assert.equal(t.proceeds_idr, t.exit_price * 9800 * (1 - 0.0025));
  assert.equal(t.pnl_idr, t.proceeds_idr - t.cost_idr);
  assert.equal(t.return, t.pnl_idr / t.cost_idr);
  // the same numbers as decimals (101.0505 x 9800 x 1.0015 = 991,780.34235; 101.949 x 9800 x 0.9975 = 996,602.4495)
  for (const [x, d] of [[t.cost_idr, 991780.34235], [t.proceeds_idr, 996602.4495], [t.pnl_idr, 4822.10715]])
    assert.ok(Math.abs(x - d) < 1e-6, `${x} vs ${d}`);
  assert.equal(t.mae, 100 / t.entry_price - 1);
  assert.equal(t.mfe, 103 / t.entry_price - 1);
  assert.deepEqual(l.equity.slice(0, 4), [1e6, 1e6, 1e6, 1e6]);
  assert.equal(l.equity[4], 1e6 - t.cost_idr + 9800 * 102);
  assert.equal(l.equity[9], 1e6 - t.cost_idr + t.proceeds_idr);
  assert.equal(l.exposure[4], 9800 * 102 / l.equity[4]);
  assert.equal(l.exposure[9], 0);
  assert.deepEqual(l.events.entries.AAA, { on: [3], runs: [3, 3] });
  assert.deepEqual(l.benchmark_close, [100, 100, 100, 100, 102, 102, 102, 102, 102, 102]);
  assert.deepEqual(l.benchmark, { kind: 'buy_and_hold', ticker: 'AAA' });
  assert.deepEqual(l.per_ticker_signals, [{ ticker: 'AAA', entry_signals: 1, last_signal: DAYS[3] }]);
  assert.deepEqual(l.warnings.map(w => w.code), ['ARB_NOT_MODELLED', 'TICK_NOT_MODELLED']);
});

/* a random walk (test-only) for the look-ahead test */
function walk(n: number, seed: number): B[] {
  let s = seed >>> 0, p = 1000;
  const rnd = () => ((s = (Math.imul(s, 1664525) + 1013904223) >>> 0) / 4294967296);
  return Array.from({ length: n }, () => {
    const o = p * (1 + (rnd() - 0.5) * 0.02), c = o * (1 + (rnd() - 0.5) * 0.06);
    p = c;
    return { o, h: Math.max(o, c) * (1 + rnd() * 0.02), l: Math.min(o, c) * (1 - rnd() * 0.02), c, v: Math.round(1e6 * (0.5 + rnd())) };
  });
}

test('no look-ahead: changing later bars changes nothing before them', () => {
  const b = walk(80, 11), cut = 60;                                 // calendar index 40 (period from bar 20)
  const changed = b.map((x, i) => i < cut ? x : { o: x.o * 1.3, h: x.h * 1.5, l: x.l * 0.6, c: x.c * 0.9, v: x.v * 3 });
  const r = request(79, q => {
    q.entry = { logic: 'any', at_least: 1, window_bars: 3, conditions: [
      { id: 'rsi', kind: 'indicator', indicator: 'I13', params: { length: 6 }, lhs: { type: 'output', output: 'rsi' }, op: 'lt', rhs: { type: 'value', value: 40 } },
      { id: 'div', kind: 'price_action', type: 'macd', params: { fast_length: 3, slow_length: 6, signal_length: 3 }, op: 'bullish_divergence' },
      { id: 'brk', kind: 'price_action', type: 'breakout', params: { length: 5 }, op: 'close_above_high' }] };
    q.exit.atr_length = 5; q.exit.stop.mode = 'atr'; q.exit.take_profit = { mode: 'r', pct: 0.1, r_multiple: 3, atr_mult: 3 };
    q.exit.trailing = { mode: 'chandelier', pct: 0.05, chandelier_length: 5, chandelier_mult: 2, line: { indicator: 'I01', output: 'sma' } };
    q.exit.max_hold_bars = 8;
    q.exit.signals = { logic: 'any', conditions: [{ id: 'hot', kind: 'indicator', indicator: 'I13', params: { length: 6 }, lhs: { type: 'output', output: 'rsi' }, op: 'gt', rhs: { type: 'value', value: 75 } }] };
  }, 20);
  const a = go(market({ AAA: { bars: b } }), r), z = go(market({ AAA: { bars: changed } }), r);
  const k = cut - 20;
  const before = (l: Ledger) => l.trades.filter(t => t.exit_bar < k);
  assert.ok(before(a).length >= 2, 'the fixture must trade before the change');
  assert.deepEqual(before(z), before(a));
  assert.deepEqual(z.trades.filter(t => t.entry_bar < k).map(t => [t.entry_bar, t.shares, t.entry_price, t.initial_stop, t.initial_target]),
    a.trades.filter(t => t.entry_bar < k).map(t => [t.entry_bar, t.shares, t.entry_price, t.initial_stop, t.initial_target]));
  assert.deepEqual(z.equity.slice(0, k), a.equity.slice(0, k));
  const early = (l: Ledger) => l.events.conditions.map(c => c.track.on.filter(i => i < k));
  assert.deepEqual(early(z), early(a));
  assert.deepEqual(z.events.skipped.filter(s => s.signal_date < DAYS[cut - 1]), a.events.skipped.filter(s => s.signal_date < DAYS[cut - 1]));
});

test('event order: an open sale funds a buy at the same open; trades are listed by exit day, then phase, then ticker', () => {
  // AAA: bought at bar 3, exit signal on bar 5, sold at bar 6's open (110); BBB signals on bar 5 and buys at that open
  const a = flat(10); put(a, 2, { v: 2000 }); put(a, 5, { v: 100 }); a[6] = bar(110, 110, 110, 110);
  const b = flat(10, 50); put(b, 5, { v: 2000 });
  const r = request(9, q => { portfolio(q, 1); q.exit.signals.conditions = [QUIET()] });
  const l = go(market({ AAA: { bars: a }, BBB: { bars: b } }), r);
  assert.deepEqual(l.trades.map(t => [t.ticker, t.entry_bar, t.exit_bar, t.exit_reason, t.exit_phase, t.shares]),
    [['AAA', 3, 6, 'exit_signal', 'open', 10000], ['BBB', 6, 9, 'end_of_test', 'close', 22000]]);   // 1.1M / 50
  // same day, two phases: BBB sold at the open (pending exit), AAA stopped intraday: BBB is listed first
  const a2 = flat(10); put(a2, 1, { v: 2000 }); a2[6] = bar(100, 100, 90, 95);
  const b2 = flat(10, 50); put(b2, 1, { v: 2000 }); put(b2, 5, { v: 100 }); b2[6] = bar(52, 52, 52, 52);
  const l2 = go(market({ AAA: { bars: a2 }, BBB: { bars: b2 } }), request(9, q => { portfolio(q, 2); q.exit.stop.mode = 'pct'; q.exit.stop.pct = 0.05; q.exit.signals.conditions = [QUIET()] }));
  assert.deepEqual(l2.trades.map(t => [t.ticker, t.exit_bar, t.exit_phase, t.exit_reason]), [['BBB', 6, 'open', 'exit_signal'], ['AAA', 6, 'intraday', 'stop_loss']]);
});

test('no reuse of cash before it exists: an intraday sale funds the next open, not the same one', () => {
  // AAA: 5,000 shares at 100 (half of the capital), target +200 % = 300, hit intraday on bar 5
  const a = flat(10); put(a, 1, { v: 2000 }); a[3] = bar(200, 200, 200, 200); a[4] = bar(290, 290, 290, 290);
  a[5] = bar(295, 310, 295, 305); for (let i = 6; i < 10; i++) a[i] = bar(305, 305, 305, 305);
  const b = flat(10, 50); put(b, 4, { v: 2000 });
  const c = flat(10, 20); put(c, 5, { v: 2000 });
  const r = request(9, q => { portfolio(q, 2); q.exit.take_profit.mode = 'pct'; q.exit.take_profit.pct = 2 });
  const l = go(market({ AAA: { bars: a }, BBB: { bars: b }, CCC: { bars: c } }), r);
  const by = Object.fromEntries(l.trades.map(t => [t.ticker, t]));
  assert.deepEqual([by.AAA.exit_bar, by.AAA.exit_phase, by.AAA.exit_price], [5, 'intraday', 100 * (1 + 2)]);
  // bar 5 open: cash 500,000, equity 500,000 + 5,000 x 295 -> budget min(500,000, 987,500): 10,000 shares, not 19,700
  assert.deepEqual([by.BBB.entry_bar, by.BBB.shares], [5, 10000]);
  // bar 6 open: cash 1,500,000 (AAA sold at 300), equity 1,500,000 + 10,000 x 50 -> budget min(1.5M, 1M): 50,000 shares
  assert.deepEqual([by.CCC.entry_bar, by.CCC.shares], [6, 50000]);
});

test('sizing: equity at the open values held positions at today\'s open (else their last close); allocation in single mode', () => {
  // AAA: 5,000 shares at 100 (budget 1,000,000 / 2), cash 500,000; on bar 4 it opens at 60
  const a = flat(8); put(a, 1, { v: 2000 }); for (let i = 4; i < 8; i++) a[i] = bar(60, 60, 60, 60);
  const b = flat(8, 50); put(b, 3, { v: 2000 });
  const shares = (m: MarketData) => go(m, request(7, q => portfolio(q, 2))).trades.find(t => t.ticker === 'BBB')!.shares;
  assert.equal(shares(market({ AAA: { bars: a }, BBB: { bars: b } })), 8000);           // (500,000 + 5,000 x 60) / 2 / 50
  // AAA without a bar on day 4: its last close (100) values it: (500,000 + 5,000 x 100) / 2 / 50
  const dates = DAYS.slice(0, 8).filter((_, i) => i !== 4);
  assert.equal(shares(market({ AAA: { bars: flat(7).map((x, i) => i === 1 ? { ...x, v: 2000 } : x), dates }, BBB: { bars: b } }, DAYS.slice(0, 8))), 10000);
  const one = put(flat(8), 3, { v: 2000 });
  assert.equal(only(go(market({ AAA: { bars: one } }), request(7, q => { q.sizing.allocation_fraction = 0.5 }))).shares, 5000);
  const lots = put(flat(8, 333), 3, { v: 2000 });                                        // 1,000,000 / 333 = 3,003 shares -> 30 lots
  assert.equal(only(go(market({ AAA: { bars: lots } }), request(7))).shares, 3000);
  const poor = go(market({ AAA: { bars: one } }), request(7, q => { q.sizing.capital_idr = 9_999 }));   // one lot costs 10,000
  assert.deepEqual([poor.trades.length, poor.events.skipped.map(x => x.reason), poor.equity[7]], [0, ['insufficient_cash'], 9_999]);
});

test('ARA rule: skip when the open is at least the previous close x (1 + ara_gap_fraction)', () => {
  const b = flat(8); put(b, 3, { v: 2000 }); b[4] = bar(120, 121, 119, 120);
  const ara = (skip: boolean) => request(7, q => { q.costs.skip_ara_open_gap = skip });
  const l = go(market({ AAA: { bars: b } }), ara(true));
  assert.equal(l.trades.length, 0);
  assert.deepEqual(l.events.skipped, [{ ticker: 'AAA', signal_date: DAYS[3], signal_event: 0, reason: 'ara_open_gap' }]);
  assert.equal(only(go(market({ AAA: { bars: b } }), ara(false))).entry_price, 120);
  const below = flat(8); put(below, 3, { v: 2000 }); below[4] = bar(119.99, 121, 119, 120);
  assert.equal(only(go(market({ AAA: { bars: below } }), ara(true))).entry_price, 119.99);
});

test('stop: a gap through the stop sells at the open, a touch sells at the stop', () => {
  const r = request(9, q => { q.exit.stop.mode = 'pct'; q.exit.stop.pct = 0.05 });
  const gap = flat(10); put(gap, 3, { v: 2000 }); gap[6] = bar(90, 92, 88, 91);
  const t = only(go(market({ AAA: { bars: gap } }), r));
  assert.deepEqual([t.exit_bar, t.exit_reason, t.exit_phase, t.exit_price, t.initial_stop], [6, 'stop_loss', 'open', 90, 100 * (1 - 0.05)]);
  assert.equal(t.mae, 90 / 100 - 1);                                // sold at the open: the open, not the day's low (D-E5)
  const touch = flat(10); put(touch, 3, { v: 2000 }); touch[6] = bar(97, 98, 94, 96);
  const u = only(go(market({ AAA: { bars: touch } }), r));
  assert.deepEqual([u.exit_bar, u.exit_reason, u.exit_phase, u.exit_price], [6, 'stop_loss', 'intraday', 100 * (1 - 0.05)]);
  assert.equal(u.mae, 94 / 100 - 1);
  assert.equal(u.initial_risk_pct, (100 - 100 * (1 - 0.05)) / 100);
});

test('take profit: a gap over the target sells at the open, a touch sells at the target', () => {
  const r = request(9, q => { q.exit.take_profit.mode = 'pct'; q.exit.take_profit.pct = 0.1 });
  const gap = flat(10); put(gap, 3, { v: 2000 }); gap[6] = bar(115, 118, 114, 116);
  assert.deepEqual((t => [t.exit_reason, t.exit_phase, t.exit_price, t.mfe])(only(go(market({ AAA: { bars: gap } }), r))), ['take_profit', 'open', 115, 115 / 100 - 1]);
  const touch = flat(10); put(touch, 3, { v: 2000 }); touch[6] = bar(105, 112, 104, 108);
  assert.deepEqual((t => [t.exit_reason, t.exit_phase, t.exit_price])(only(go(market({ AAA: { bars: touch } }), r))), ['take_profit', 'intraday', 100 * (1 + 0.1)]);
});

test('stop and target in one candle: the stop is taken and flagged (D-E4)', () => {
  const b = flat(10); put(b, 3, { v: 2000 }); b[6] = bar(100, 112, 94, 100);
  const t = only(go(market({ AAA: { bars: b } }), request(9, q => { q.exit.stop.mode = 'pct'; q.exit.stop.pct = 0.05; q.exit.take_profit.mode = 'pct'; q.exit.take_profit.pct = 0.1 })));
  assert.deepEqual([t.exit_reason, t.exit_phase, t.exit_price, t.flags.stop_and_target_same_bar], ['stop_loss', 'intraday', 100 * (1 - 0.05), true]);
});

test('trailing stop in percent: from the entry fill and the closes, inactive while not below the previous close', () => {
  // entry 100 (peak), close 85: level 90 is above the previous close -> inactive on bars 5 and 6; active on bar 7
  const b = flat(10); put(b, 3, { v: 2000 }); b[4] = bar(100, 100, 84, 85); b[5] = bar(86, 89, 84, 88); b[6] = bar(89, 96, 88, 95); b[7] = bar(94, 95, 89, 90);
  const t = only(go(market({ AAA: { bars: b } }), request(9, q => { q.exit.trailing.mode = 'pct'; q.exit.trailing.pct = 0.1 })));
  assert.deepEqual([t.exit_bar, t.exit_reason, t.exit_phase, t.exit_price], [7, 'trailing_stop', 'intraday', 100 * (1 - 0.1)]);
});

test('chandelier trailing stop: highest high since entry within the lookback minus k x ATR of the bar before; it only rises', () => {
  // true range 4 on every bar up to 17, so I30 ATR(3, RMA) = 4: level = highest high - 8
  const b = Array.from({ length: 22 }, () => bar(100, 102, 98, 100));
  put(b, 10, { v: 2000 });
  b[12] = bar(101, 104, 100, 102); b[13] = bar(103, 106, 102, 104); b[14] = bar(105, 108, 104, 106); b[15] = bar(105, 106, 102, 104);
  b[16] = bar(104, 105, 101, 103); b[17] = bar(103, 105, 101, 103); b[18] = bar(101, 102, 97, 98);
  const atr = F.atr({ O: b.map(x => x.o), H: b.map(x => x.h), L: b.map(x => x.l), C: b.map(x => x.c), V: b.map(x => x.v) }, { length: 3, smoothing_type: 'RMA' }).atr;
  assert.deepEqual(atr.slice(3, 18), Array(15).fill(4));
  // levels: 94, 96, 98, 100 (bar 15: high 108 in the window), 100, 100, then the window gives 98 but the level stays 100
  const t = only(go(market({ AAA: { bars: b } }), request(21, q => { q.exit.trailing = { mode: 'chandelier', pct: 0.05, chandelier_length: 3, chandelier_mult: 2, line: { indicator: 'I01', output: 'sma' } } })));
  assert.deepEqual([t.entry_bar, t.exit_bar, t.exit_reason, t.exit_price], [11, 18, 'trailing_stop', 100]);
});

test('line trailing stop: the line on the bar before, inactive above the previous close, never lowered', () => {
  // I01 SMA(2) of the closes: 100 (bar 11), 102, 106, 107.5
  const b = flat(18); put(b, 10, { v: 2000 });
  b[12] = bar(101, 105, 101, 104); b[13] = bar(105, 109, 104, 108); b[14] = bar(108, 109, 106.5, 107); b[15] = bar(106.8, 107, 105, 105.5);
  const t = only(go(market({ AAA: { bars: b } }), request(17, q => { q.exit.trailing = { mode: 'line', pct: 0.05, chandelier_length: 22, chandelier_mult: 3, line: { indicator: 'I01', output: 'sma', params: { length: 2 } } } })));
  assert.deepEqual([t.exit_bar, t.exit_reason, t.exit_price], [15, 'trailing_stop', 106]);   // 107.5 was not below 107: the level stays 106
});

test('time exit at the close once the trade has max_hold_bars of its own bars', () => {
  const b = flat(10); put(b, 3, { v: 2000 }); b[6] = bar(100, 104, 100, 103);
  const t = only(go(market({ AAA: { bars: b } }), request(9, q => { q.exit.max_hold_bars = 3 })));
  assert.deepEqual([t.entry_bar, t.exit_bar, t.exit_reason, t.exit_phase, t.exit_price, t.bars_held], [4, 6, 'time_exit', 'close', 103, 3]);
});

test('exit signal at the close sells at the next open; not on the entry bar', () => {
  const b = flat(10); put(b, 3, { v: 2000 }); put(b, 4, { v: 100 }); put(b, 7, { v: 100 }); b[8] = bar(104, 105, 99, 100);
  const l = go(market({ AAA: { bars: b } }), request(9, q => { q.exit.signals.conditions = [QUIET()] }));
  const t = only(l);
  assert.deepEqual([t.exit_bar, t.exit_reason, t.exit_phase, t.exit_price, t.mfe, t.mae], [8, 'exit_signal', 'open', 104, 104 / 100 - 1, 0]);
  assert.deepEqual(l.events.exits.AAA, { on: [4, 7], runs: [4, 4, 7, 7] });
  assert.deepEqual(l.events.conditions.map(c => c.condition_id), ['v', 'x']);
});

test('exit priority: stop before trailing, take profit, time exit and exit signal', () => {
  const pct = (q: BacktestRequest) => { q.exit.stop.mode = 'pct'; q.exit.stop.pct = 0.05; q.exit.signals.conditions = [QUIET()] };
  // open: a pending exit signal and a gap through the stop on the same open -> stop
  const a = flat(10); put(a, 3, { v: 2000 }); put(a, 5, { v: 100 }); a[6] = bar(90, 91, 89, 90);
  assert.deepEqual((t => [t.exit_reason, t.exit_phase, t.exit_price])(only(go(market({ AAA: { bars: a } }), request(9, pct)))), ['stop_loss', 'open', 90]);
  // intraday stop on the bar the time exit is due -> stop
  const b = flat(10); put(b, 3, { v: 2000 }); b[6] = bar(99, 100, 94, 99);
  assert.deepEqual((t => [t.exit_reason, t.exit_phase])(only(go(market({ AAA: { bars: b } }), request(9, q => { pct(q); q.exit.max_hold_bars = 3 })))), ['stop_loss', 'intraday']);
  // intraday target on the bar the time exit is due -> take profit
  const c = flat(10); put(c, 3, { v: 2000 }); c[6] = bar(101, 111, 100, 104);
  assert.deepEqual((t => [t.exit_reason, t.exit_price])(only(go(market({ AAA: { bars: c } }), request(9, q => { q.exit.take_profit.mode = 'pct'; q.exit.take_profit.pct = 0.1; q.exit.max_hold_bars = 3 })))), ['take_profit', 100 * (1 + 0.1)]);
  // time exit and an exit signal at the same close -> time exit
  const d = flat(10); put(d, 3, { v: 2000 }); put(d, 6, { v: 100 });
  assert.deepEqual((t => [t.exit_reason, t.exit_bar])(only(go(market({ AAA: { bars: d } }), request(9, q => { q.exit.max_hold_bars = 3; q.exit.signals.conditions = [QUIET()] })))), ['time_exit', 6]);
  // stop and trailing level equal -> stop loss; trailing above the stop -> trailing stop
  const e = flat(10); put(e, 3, { v: 2000 }); e[4] = bar(100, 100, 100, 100); e[5] = bar(100, 100, 94, 96);
  assert.equal(only(go(market({ AAA: { bars: e } }), request(9, q => { pct(q); q.exit.trailing.mode = 'pct'; q.exit.trailing.pct = 0.05 }))).exit_reason, 'stop_loss');
  const f = flat(10); put(f, 3, { v: 2000 }); f[4] = bar(100, 110, 100, 110); f[5] = bar(108, 108, 103, 104);
  assert.deepEqual((t => [t.exit_reason, t.exit_price])(only(go(market({ AAA: { bars: f } }), request(9, q => { pct(q); q.exit.trailing.mode = 'pct'; q.exit.trailing.pct = 0.05 })))), ['trailing_stop', 110 * (1 - 0.05)]);
});

/* ---- portfolio --------------------------------------------------------------------------------------------- */

test('maximum positions, ranking by volume ratio (highest first, ties by ticker) and the next candidate after a skip', () => {
  // 25 bars of volume 1,000, signals on bar 24: ratio = volume / SMA20(volume) of the bar before = volume / 1,000
  const mk = (v: number) => put(flat(30), 24, { v });
  const m = market({ AAA: { bars: mk(2000) }, BBB: { bars: mk(4000) }, CCC: { bars: mk(3000) }, DDD: { bars: mk(2000) } });
  const l = go(m, request(29, q => portfolio(q, 2), 20));
  assert.deepEqual(l.trades.map(t => [t.ticker, t.entry_bar, t.shares]), [['BBB', 5, 5000], ['CCC', 5, 5000]]);   // 500,000 / 100 each
  assert.deepEqual(l.events.skipped.map(s => [s.ticker, s.reason]), [['AAA', 'no_slot'], ['DDD', 'no_slot']]);
  // a ranked candidate skipped by the ARA rule lets the next one in (D-slots); a tie goes to the first ticker
  const gapped = mk(4000); gapped[25] = bar(130, 130, 130, 130);
  const l2 = go(market({ AAA: { bars: mk(2000) }, BBB: { bars: gapped }, CCC: { bars: mk(3000) }, DDD: { bars: mk(2000) } }), request(29, q => { portfolio(q, 2); q.costs.skip_ara_open_gap = true }, 20));
  assert.deepEqual(l2.trades.map(t => t.ticker).sort(), ['AAA', 'CCC']);
  assert.deepEqual(l2.events.skipped.map(s => [s.ticker, s.reason]), [['BBB', 'ara_open_gap'], ['DDD', 'no_slot']]);
});

test('ranking by lowest RSI(14) and by the 5-bar foreign net', () => {
  // AAA only rises (RSI 100), BBB only falls (RSI 0): BBB ranks first
  const up = Array.from({ length: 30 }, (_, i) => bar(100 + i, 100 + i, 100 + i, 100 + i)), down = Array.from({ length: 30 }, (_, i) => bar(200 - i, 200 - i, 200 - i, 200 - i));
  put(up, 24, { v: 2000 }); put(down, 24, { v: 2000 });
  const l = go(market({ AAA: { bars: up }, BBB: { bars: down } }), request(29, q => portfolio(q, 1, 'rsi'), 20));
  assert.deepEqual(l.trades.map(t => t.ticker), ['BBB']);
  // foreign net summed over bars 20..24: AAA 5 x 3e9 = 15e9, BBB 4 x 4e9 + 1e9 = 17e9; AAA's 50e9 on bar 19 is outside the window
  const fl = (vals: (i: number) => number) => ({ fnet: Float64Array.from({ length: 30 }, (_, i) => vals(i)), brokers: new Map() });
  const m = market({ AAA: { bars: put(flat(30), 24, { v: 2000 }), flow: fl(i => i === 19 ? 50e9 : i >= 20 ? 3e9 : 0) }, BBB: { bars: put(flat(30), 24, { v: 2000 }), flow: fl(i => i === 22 ? 1e9 : i >= 20 ? 4e9 : 0) } });
  assert.deepEqual(go(m, request(29, q => portfolio(q, 1, 'fnet'), 20)).trades.map(t => t.ticker), ['BBB']);
  // a ticker without flow data cannot be ranked by it: left out of the portfolio run (TICKERS_EXCLUDED), never refused
  const x = go(market({ AAA: { bars: put(flat(30), 24, { v: 2000 }) }, BBB: { bars: put(flat(30), 24, { v: 2000 }), flow: fl(() => 1e9) } }), request(29, q => portfolio(q, 1, 'fnet'), 20));
  assert.deepEqual(x.trades.map(t => t.ticker), ['BBB']);
  const w = x.warnings.find(w => w.code === 'TICKERS_EXCLUDED')!;
  assert.deepEqual([w.count, w.tickers, w.reasons!.map(r => [r.ticker, r.code, r.field])], [1, ['AAA'], [['AAA', 'FLOW_UNAVAILABLE', 'portfolio.rank_by']]]);
  assert.deepEqual(x.per_ticker_signals.map(t => t.ticker), ['BBB']);
});

test('ranking by ADX follows the registry I07 adx(14, 14) on the signal bar', () => {
  const tk = ['AAA', 'BBB', 'CCC'], bars = tk.map((_, k) => put(walk(60, 100 + k), 50, { v: 9e6 }));
  const adx = bars.map(b => F.adx({ O: b.map(x => x.o), H: b.map(x => x.h), L: b.map(x => x.l), C: b.map(x => x.c), V: b.map(x => x.v) }, { di_length: 14, adx_smoothing: 14 }).adx[50] as number);
  const best = tk[adx.indexOf(Math.max(...adx))];
  const l = go(market(Object.fromEntries(tk.map((t, k) => [t, { bars: bars[k] }]))), request(59, q => { portfolio(q, 1, 'adx'); q.entry.conditions = [VOL('v', 5e6)] }, 45));
  assert.equal(l.trades.find(t => t.signal_bar === 5)!.ticker, best);
});

test('minimum 20-day average traded value on the signal bar (close x volume, D-K9)', () => {
  // SMA20 of close x volume on bar 24: (19 x 100 x 1,000 + 100 x 3,000) / 20 = 110,000
  const m = () => market({ AAA: { bars: put(flat(30), 24, { v: 3000 }) } });
  assert.equal(go(m(), request(29, q => portfolio(q, 1, 'vol', 110_000), 20)).trades.length, 1);
  const l = go(m(), request(29, q => portfolio(q, 1, 'vol', 110_001), 20));
  assert.deepEqual([l.trades.length, l.events.skipped.map(s => s.reason)], [0, ['below_min_value']]);
  assert.equal(go(m(), request(29, q => portfolio(q, 1, 'vol', 0), 3)).trades.length, 1);   // 0 = off, also without 20 bars
});

test('no second position in a ticker that is held (already_held), and no re-entry while the entry state stays true (D-E1)', () => {
  const b = flat(16); put(b, 2, { v: 2000 }); put(b, 4, { v: 2000 });          // off on bar 3, on again on bar 4 while held
  const l = go(market({ AAA: { bars: b } }), request(15));
  assert.deepEqual(l.trades.map(t => [t.signal_bar, t.entry_bar]), [[2, 3]]);
  assert.deepEqual(l.events.skipped, [{ ticker: 'AAA', signal_date: DAYS[4], signal_event: 1, reason: 'already_held' }]);
  // state true on bars 3..9: one event; the time exit on bar 5 is not followed by a new trade until the next switch-on (bar 11)
  const c = flat(16); for (let i = 3; i <= 9; i++) put(c, i, { v: 2000 }); put(c, 11, { v: 2000 });
  const l2 = go(market({ AAA: { bars: c } }), request(15, q => { q.exit.max_hold_bars = 2 }));
  assert.deepEqual(l2.trades.map(t => [t.signal_bar, t.entry_bar, t.exit_bar]), [[3, 4, 5], [11, 12, 13]]);
  assert.deepEqual(l2.events.entries.AAA.on, [3, 11]);
});

test('a stop on the entry bar (D-E3) and a pending exit sold before that bar\'s stop (D-E6)', () => {
  const b = flat(10); put(b, 3, { v: 2000 }); b[4] = bar(100, 101, 94, 97);
  const t = only(go(market({ AAA: { bars: b } }), request(9, q => { q.exit.stop.mode = 'pct'; q.exit.stop.pct = 0.05 })));
  assert.deepEqual([t.entry_bar, t.exit_bar, t.exit_phase, t.exit_price, t.bars_held, t.mae, t.mfe], [4, 4, 'intraday', 100 * (1 - 0.05), 1, 94 / 100 - 1, 101 / 100 - 1]);
  const c = flat(10); put(c, 3, { v: 2000 }); put(c, 7, { v: 100 }); c[8] = bar(99, 99, 90, 92);
  const u = only(go(market({ AAA: { bars: c } }), request(9, q => { q.exit.stop.mode = 'pct'; q.exit.stop.pct = 0.05; q.exit.signals.conditions = [QUIET()] })));
  assert.deepEqual([u.exit_bar, u.exit_reason, u.exit_phase, u.exit_price], [8, 'exit_signal', 'open', 99]);
});

test('period_end: no entry on the last day of the period, and an event on the last day has no next day', () => {
  const b = flat(10); put(b, 8, { v: 2000 }); put(b, 6, { v: 2000 });
  const l = go(market({ AAA: { bars: b } }), request(9, q => { q.exit.max_hold_bars = 1 }));
  assert.deepEqual(l.trades.map(t => [t.entry_bar, t.exit_bar]), [[7, 7]]);
  assert.deepEqual(l.events.skipped.map(s => [s.signal_date, s.reason]), [[DAYS[8], 'period_end']]);
  const c = flat(10); put(c, 9, { v: 2000 });
  assert.deepEqual(go(market({ AAA: { bars: c } }), request(9)).events.skipped.map(s => [s.signal_date, s.reason]), [[DAYS[9], 'period_end']]);
});

test('no_next_bar: no fill on a later day when the ticker has no bar on the next calendar day', () => {
  const dates = DAYS.slice(0, 10).filter((_, i) => i !== 4), b = flat(9); put(b, 3, { v: 2000 });
  const l = go(market({ AAA: { bars: b, dates } }, DAYS.slice(0, 10)), request(9));
  assert.deepEqual([l.trades.length, l.events.skipped.map(s => s.reason)], [0, ['no_next_bar']]);
  assert.deepEqual(l.warnings.find(w => w.code === 'DATA_GAP'), { code: 'DATA_GAP', count: 1, tickers: ['AAA'], message: l.warnings[0].message });
});

test('suspension: a held ticker without a bar is marked at its last close and flagged; bars_held counts its own bars', () => {
  const dates = DAYS.slice(0, 12).filter((_, i) => i !== 6 && i !== 7 && i !== 11);   // no bar on days 6, 7 and the last day
  const b = flat(9); put(b, 3, { v: 2000 }); b[5] = bar(100, 104, 100, 104); b[6] = bar(90, 95, 90, 95);    // bar 6 = day 8
  const l = go(market({ AAA: { bars: b, dates } }, DAYS.slice(0, 12)), request(11));
  const t = only(l);
  assert.equal(l.dates.length, 12);
  assert.deepEqual([l.equity[6], l.equity[7], l.equity[8]], [1e6 + 10000 * 4, 1e6 + 10000 * 4, 1e6 - 10000 * 5]);
  assert.deepEqual([t.exit_bar, t.exit_reason, t.exit_phase, t.exit_price, t.bars_held, t.flags.stale_mark], [11, 'end_of_test', 'close', 100, 5, true]);
  assert.deepEqual(l.warnings.find(w => w.code === 'DATA_GAP')!.count, 3);
});

test('corporate actions with ex-date in (entry, exit] are flagged; warnings for the adjusted-history boundary and survivorship', () => {
  const b = flat(10); put(b, 3, { v: 2000 });
  const actions = [{ date: DAYS[4], type: 'stock_split' }, { date: DAYS[5], type: 'bonus' }, { date: DAYS[9], type: 'rights' }];
  const t = only(go(market({ AAA: { bars: b, actions } }), request(9)));
  assert.deepEqual(t.flags.corporate_actions, actions.slice(1));
  const late = weekdays(10, '2026-09-07'), l = go(market({ AAA: { bars: b, dates: late } }, late), (() => { const r = request(9); r.period = { from: late[0], to: late[9], oos_fraction: 0 }; return r })());
  assert.ok(l.warnings.some(w => w.code === 'ADJUSTED_HISTORY_BOUNDARY'));
  const p = go(market({ AAA: { bars: b } }), request(9, q => portfolio(q, 1)));
  assert.deepEqual(p.warnings.map(w => w.code), ['ARB_NOT_MODELLED', 'TICK_NOT_MODELLED', 'SURVIVORSHIP']);
  assert.deepEqual(p.benchmark, { kind: 'ihsg', ticker: 'IHSG' });
  assert.deepEqual(p.benchmark_close, Array(10).fill(7000));
});

/* ---- what the period and the picked stocks become on the data (lead decisions 2026-10-26) --------------------- */

const SMA20: Condition = { id: 's', kind: 'indicator', indicator: 'I01', params: { length: 20 }, lhs: { type: 'price' }, op: 'gt', rhs: { type: 'output', output: 'sma' } };
const FNET10: Condition = { id: 'f', kind: 'flow', type: 'fnet', params: { length: 10 }, op: 'gt', value: 0 };
/** Flow data on n bars with broker rows on bars [from, to] (foreign net v there, NaN outside), as flow.ts builds it. */
const flowOf = (n: number, from: number, to: number, v = 1e9) => ({
  fnet: Float64Array.from({ length: n }, (_, i) => i >= from && i <= to ? v : NaN), brokers: new Map<string, Float64Array>(), from, to, gap_bars: [], unmatched_rows: 0 });

test('single mode: a period that starts before the ticker\'s first bar starts there (PERIOD_CLIPPED); a portfolio keeps its period', () => {
  const b = flat(10); put(b, 3, { v: 2000 });
  const m = market({ AAA: { bars: b, dates: DAYS.slice(5, 15) } }, DAYS.slice(0, 15));
  for (const bench of ['buy_and_hold', 'ihsg'] as const) {
    const clipped = go(m, request(14, q => { q.single!.benchmark = bench }, 0)), own = go(m, request(14, q => { q.single!.benchmark = bench }, 5));
    assert.deepEqual(clipped.warnings[0], { code: 'PERIOD_CLIPPED', message: `AAA has no published bar before ${DAYS[5]}: the backtest starts on ${DAYS[5]} instead of the requested ${DAYS[0]}.` });
    // the run from the first bar, and nothing else changes
    assert.deepEqual({ ...clipped, warnings: clipped.warnings.slice(1) }, own);
    assert.deepEqual([clipped.dates[0], clipped.dates.length, clipped.benchmark_close[0]], [DAYS[5], 10, bench === 'ihsg' ? 7000 : 100]);
    assert.ok(!own.warnings.some(w => w.code === 'PERIOD_CLIPPED'));
  }
  assert.deepEqual(only(go(m, request(14))).entry_bar, 4);                      // the signal on AAA's bar 3 (calendar day 3)
  // a portfolio is not clipped: its calendar starts on the requested day (IHSG's bars)
  const p = go(m, request(14, q => portfolio(q, 1)));
  assert.deepEqual([p.dates[0], p.dates.length, p.warnings.some(w => w.code === 'PERIOD_CLIPPED')], [DAYS[0], 15, false]);
  // a period that ends before the first bar is not clipped: a buy-and-hold benchmark has no close (the worker's
  // checkPriceRange refuses it first: DATA_MISSING)
  assert.deepEqual(refused(() => go(m, request(3))), ['PERIOD_BEFORE_DATA', 'period.from']);
  assert.equal(go(m, request(3, q => { q.single!.benchmark = 'ihsg' })).trades.length, 0);
  // the primary benchmark without a close on the first calendar day: IHSG starts after a portfolio ticker's first bar
  const late = market({ AAA: { bars: b } }, DAYS.slice(3, 10));
  assert.deepEqual(refused(() => go(late, request(9, q => portfolio(q, 1)))), ['PERIOD_BEFORE_DATA', 'period.from']);
});

test('portfolio: a ticker whose own data cannot serve the strategy is left out (TICKERS_EXCLUDED); single mode still refuses', () => {
  // IHSG and BBB have no bar on DAYS[10]; AAA (10 bars on days IHSG has: the 20-bar volume SMA has no value, so ALL of
  // the two can never be true) is left out; BBB's volume spike on its bar 24 is above both
  const days = DAYS.slice(0, 30).filter((_, i) => i !== 10), long = flat(29); put(long, 24, { v: 2000 });
  const shortBars = flat(10); put(shortBars, 3, { v: 2000 });
  const m = market({ AAA: { bars: shortBars, dates: days.slice(5, 15) }, BBB: { bars: long, dates: days } }, days);
  m.excluded = [{ ticker: 'CCC', code: 'DATA_MISSING', field: 'CCC.price', message: 'No price file is published for CCC.' }];   // the loader's
  const VSMA20: Condition = { id: 'a', kind: 'indicator', indicator: 'I35', params: { length: 20 }, lhs: { type: 'price' }, op: 'gt', rhs: { type: 'output', output: 'volume_sma' } };
  const r = request(29, q => { portfolio(q, 1); q.entry = { logic: 'all', at_least: 1, window_bars: 1, conditions: [VOL(), VSMA20] } }, 0);
  const l = go(m, r);
  assert.deepEqual(l.trades.map(t => t.ticker), ['BBB']);
  assert.deepEqual(l.per_ticker_signals.map(t => t.ticker), ['BBB']);
  assert.deepEqual(Object.keys(l.events.entries), ['BBB']);
  assert.deepEqual([l.dates.length, l.dates.includes(DAYS[10])], [29, false]);
  const w = l.warnings[0];
  assert.deepEqual([w.code, w.count, w.tickers], ['TICKERS_EXCLUDED', 2, ['AAA', 'CCC']]);
  assert.deepEqual(w.reasons!.map(x => [x.ticker, x.code, x.field]), [['AAA', 'INDICATOR_OUTPUT_EMPTY', 'entry.conditions[1].rhs'], ['CCC', 'DATA_MISSING', 'CCC.price']]);
  assert.match(w.reasons![0].message, /entry\.conditions\[1\]/);
  // a plain sentence the page shows as it is (page review V5): the codes and fields are in reasons
  assert.equal(w.message, '2 picked stocks were left out of this run because their own data cannot serve the strategy. The run trades the other 1 stock.');
  // the same run without the left-out tickers gives the same ledger, the warning aside: AAA adds no day outside IHSG's
  // calendar (PF8: a left-out ticker's bars reach the calendar, the next test)
  const alone = go(market({ BBB: { bars: long, dates: days } }, days), r);
  assert.deepEqual({ ...l, warnings: l.warnings.slice(1) }, alone);
  // flow: a window longer than the bars with broker data (FLOW_OUTPUT_EMPTY), no broker row at all (FLOW_UNAVAILABLE)
  const fm = market({ DDD: { bars: put(flat(30), 24, { v: 2000 }), flow: flowOf(30, 25, 29) as any }, EEE: { bars: put(flat(30), 24, { v: 2000 }), flow: flowOf(30, 0, 29) as any },
    FFF: { bars: put(flat(30), 24, { v: 2000 }), flow: flowOf(30, 30, -1) as any } });
  const fr = request(29, q => { portfolio(q, 1); q.entry.conditions = [VOL(), FNET10] }, 0), fl = go(fm, fr);
  assert.deepEqual(fl.trades.map(t => t.ticker), ['EEE']);
  assert.deepEqual(fl.warnings[0].reasons!.map(x => [x.ticker, x.code, x.field]), [['DDD', 'FLOW_OUTPUT_EMPTY', 'entry.conditions[1].params.length'], ['FFF', 'FLOW_UNAVAILABLE', 'entry.conditions[1]']]);
  // single mode: the same data errors fail the run
  assert.deepEqual(refused(() => go(m, request(14, q => { q.entry.conditions = [VOL(), SMA20] }, 5))), ['INDICATOR_OUTPUT_EMPTY', 'entry.conditions[1].rhs']);
  assert.deepEqual(refused(() => go(market({ AAA: { bars: put(flat(30), 24, { v: 2000 }), flow: flowOf(30, 25, 29) as any } }), request(29, q => { q.entry.conditions = [VOL(), FNET10] }))), ['FLOW_OUTPUT_EMPTY', 'entry.conditions[1].params.length']);
  // a request error fails a portfolio run too
  assert.deepEqual(refused(() => go(m, request(29, q => { portfolio(q, 1); q.entry.conditions = [VOL(), { ...SMA20, params: { length: 0 } }] }))), ['PARAM_OUT_OF_RANGE', 'entry.conditions[1].params.length']);
  // every ticker left out, by the run, by the loader or by both: refused, UNIVERSE_EMPTY (lead decision 2026-10-26: no
  // cash-only result), the message with the count and the reasons by code
  const empty = (mk: MarketData) => { try { go(mk, r) } catch (e) { assert.ok(e instanceof ValidationError, String(e)); return [e.code, e.field, e.message] } assert.fail('not refused') };
  const onlyAaa = market({ AAA: { bars: shortBars, dates: days.slice(5, 15) } }, days);
  const [code, field, message] = empty(onlyAaa);
  assert.deepEqual([code, field], ['UNIVERSE_EMPTY', 'portfolio.tickers']);
  assert.match(message, /^The picked stock was left out because its own data cannot serve the strategy \(1 INDICATOR_OUTPUT_EMPTY\): no stock is left to trade\. AAA: entry\.conditions\[1\]/);
  onlyAaa.excluded = m.excluded;
  assert.match(empty(onlyAaa)[2], /^All 2 picked stocks were left out because their own data .* \(1 INDICATOR_OUTPUT_EMPTY, 1 DATA_MISSING\): no stock is left to trade\. The first is AAA: /);
  const loaderOnly = market({}, days); loaderOnly.excluded = m.excluded;
  assert.deepEqual(empty(loaderOnly).slice(0, 2), ['UNIVERSE_EMPTY', 'portfolio.tickers']);
  // no stock at all: a run cannot get there (a picked stock is loaded or left out, CWP-1), signals.ts leftOut still says it
  try { leftOut([], 0, 'portfolio.tickers', 'run'); assert.fail('not refused') }
  catch (e) { assert.ok(e instanceof ValidationError); assert.deepEqual([e.code, e.field, e.message], ['UNIVERSE_EMPTY', 'portfolio.tickers', 'The portfolio has no stock to run.']) }
});

test('the calendar is IHSG and every ticker the run read, run or left out: a left-out ticker\'s later bars never move another\'s next day (PF8)', () => {
  // D = DAYS[25]: IHSG and AAA have no bar there, XXX has one. AAA's volume spike on its bar of DAYS[24] (20-bar volume
  // SMA defined) orders a buy for the next calendar day. XXX never signals; with all its bars (DAYS[0..39]) it runs,
  // cut to DAYS[20..29] its volume SMA has no value up to period.to and it is left out (core fix report, open issue 1:
  // before PF8 the cut moved AAA's buy from no_next_bar to DAYS[26], a path from XXX's later bars into AAA's trades)
  const D = DAYS[25], days = DAYS.slice(0, 40).filter(d => d !== D), a = put(flat(39), 24, { v: 2000 });
  const VSMA20: Condition = { id: 'a', kind: 'indicator', indicator: 'I35', params: { length: 20 }, lhs: { type: 'price' }, op: 'gt', rhs: { type: 'output', output: 'volume_sma' } };
  const r = request(39, q => { portfolio(q, 2); q.entry = { logic: 'all', at_least: 1, window_bars: 1, conditions: [VOL(), VSMA20] } }, 0);
  r.period = { from: DAYS[0], to: DAYS[39], oos_fraction: 0 };
  const mk = (x: string[]) => market({ AAA: { bars: a, dates: days }, XXX: { bars: flat(x.length), dates: x } }, days);
  const runs = go(mk(DAYS.slice(0, 40)), r), cut = go(mk(DAYS.slice(20, 30)), r);
  assert.deepEqual(cut.warnings[0].reasons!.map(x => [x.ticker, x.code]), [['XXX', 'INDICATOR_OUTPUT_EMPTY']]);
  assert.ok(!runs.warnings.some(w => w.code === 'TICKERS_EXCLUDED'));
  for (const l of [runs, cut]) {
    assert.deepEqual([l.dates.length, l.dates.includes(D)], [40, true]);
    assert.deepEqual(l.trades, []);
    assert.deepEqual(l.events.skipped, [{ ticker: 'AAA', signal_date: DAYS[24], signal_event: 0, reason: 'no_next_bar' }]);
  }
  assert.deepEqual([cut.equity, cut.exposure, cut.benchmark_close], [runs.equity, runs.exposure, runs.benchmark_close]);
  assert.deepEqual(cut.events.entries.AAA, runs.events.entries.AAA);
  // without XXX the day is no calendar day: AAA buys on DAYS[26]; the property "the same run without its left-out
  // tickers" holds only for a left-out ticker without a day outside IHSG's calendar (the test above)
  const alone = go(market({ AAA: { bars: a, dates: days } }, days), r);
  assert.deepEqual([alone.dates.includes(D), alone.trades.map(t => [t.ticker, alone.dates[t.entry_bar]])], [false, [['AAA', DAYS[26]]]]);
});

test('a portfolio runs its picked stocks: market data of another set is a caller error, never a result (CWP-1)', () => {
  // AAA and BBB loaded, both signal on bar 3; the request and variant hashes carry portfolio.tickers, so the market
  // must hold each picked stock once, loaded or left out by the loader (MarketData.excluded), and no other ticker
  const m = (...out: string[]) => {
    const x = market({ AAA: { bars: put(flat(10), 3, { v: 2000 }) }, BBB: { bars: put(flat(10), 3, { v: 2000 }) } });
    if (out.length) x.excluded = out.map(t => ({ ticker: t, code: 'DATA_MISSING', field: `${t}.price`, message: `No price file is published for ${t}.` }));
    return x;
  };
  const pick = (...tickers: string[]) => request(9, q => { portfolio(q, 2); q.portfolio!.tickers = tickers });
  const ran = (l: Ledger) => [l.per_ticker_signals.map(t => t.ticker), l.trades.map(t => t.ticker)];
  // the run's stocks are the picked ones, in ticker order whatever the order picked (PF3)
  assert.deepEqual(ran(run(prepare(m()), pick('BBB', 'AAA'))), [['AAA', 'BBB'], ['AAA', 'BBB']]);
  assert.deepEqual(run(prepare(m()), pick('BBB', 'AAA')), run(prepare(m()), pick('AAA', 'BBB')));
  const l = run(prepare(m('CCC')), pick('CCC', 'AAA', 'BBB'));
  assert.deepEqual([...ran(l), l.warnings[0].tickers], [['AAA', 'BBB'], ['AAA', 'BBB'], ['CCC']]);
  // anything else is refused before any signal: the worker's INTERNAL_ERROR (500, logged), not a request error
  const internal = (f: () => unknown) => {
    try { f() } catch (e) { assert.deepEqual([toApiError(e).status, toApiError(e).error.code, toApiError(e).known], [500, 'INTERNAL_ERROR', false]); return (e as Error).message }
    assert.fail('not refused');
  };
  assert.equal(internal(() => run(prepare(m()), pick('AAA'))), 'engine: the market data holds BBB, which is not a picked stock.');
  assert.equal(internal(() => run(prepare(m('CCC')), pick('AAA', 'BBB'))), 'engine: the market data holds CCC, which is not a picked stock.');
  assert.equal(internal(() => run(prepare(m()), pick('AAA', 'BBB', 'CCC'))), 'engine: the picked stock CCC is neither loaded nor left out.');
  assert.equal(internal(() => run(prepare(m('BBB')), pick('AAA', 'BBB'))), 'engine: the picked stock BBB is loaded and left out.');
  assert.equal(internal(() => run(prepare(m('CCC', 'CCC')), pick('AAA', 'BBB', 'CCC'))), 'engine: the picked stock CCC is left out more than once.');
  assert.equal(internal(() => run(prepare(market({}, DAYS.slice(0, 10))), pick('AAA'))), 'engine: the picked stock AAA is neither loaded nor left out.');
  // single mode reads its ticker only, as before: other tickers of the market are not read
  assert.deepEqual(ran(run(prepare(m()), request(9))), [['AAA'], ['AAA']]);
});

test('max_positions above the stocks picked: a slot is still 1 / max_positions of equity, the idle slots stay cash (PF5)', () => {
  // 1,200,000 rupiah over 12 slots: 100,000 a slot, 1,000 shares at 100; AAA and BBB signal on bar 3
  const m = market({ AAA: { bars: put(flat(10), 3, { v: 2000 }) }, BBB: { bars: put(flat(10), 3, { v: 2000 }) } });
  const l = go(m, request(9, q => { portfolio(q, MAX_POSITIONS); q.sizing.capital_idr = 1_200_000 }));
  assert.deepEqual(l.trades.map(t => [t.ticker, t.entry_bar, t.shares, t.cost_idr]), [['AAA', 4, 1000, 100_000], ['BBB', 4, 1000, 100_000]]);
  assert.deepEqual([l.equity[4], l.exposure[4]], [1_200_000, 200_000 / 1_200_000]);
});

/* ---- initial levels and checks ------------------------------------------------------------------------------ */

test('initial levels: ATR stop and target, R target, reward:risk stop, line stop below the fill only', () => {
  // true range 4 on every bar: I30 ATR(14, RMA) = 4 from bar 14
  const b = Array.from({ length: 24 }, () => bar(100, 102, 98, 100)); put(b, 18, { v: 2000 });
  const one = (f: (q: BacktestRequest) => void) => only(go(market({ AAA: { bars: b } }), request(23, f, 15)));
  let t = one(q => { q.exit.stop.mode = 'atr'; q.exit.take_profit.mode = 'atr' });
  assert.deepEqual([t.initial_stop, t.initial_target, t.initial_risk_pct], [100 - 2 * 4, 100 + 3 * 4, 8 / 100]);
  t = one(q => { q.exit.stop.mode = 'atr'; q.exit.take_profit.mode = 'r' });
  assert.deepEqual([t.initial_stop, t.initial_target], [92, 100 + 2 * 8]);
  t = one(q => { q.exit.stop.mode = 'rr'; q.exit.take_profit.mode = 'pct'; q.exit.take_profit.pct = 0.15 });
  assert.equal(t.initial_target, 100 * (1 + 0.15));
  assert.equal(t.initial_stop, 100 - (100 * (1 + 0.15) - 100) / 2);
  // I10 Donchian(5) lower = 98 on the signal bar, below the fill 100: the stop; the upper line (102) is above: no stop
  t = one(q => { q.exit.stop.mode = 'line'; q.exit.stop.line = { indicator: 'I10', output: 'lower', params: { length: 5 } } });
  assert.equal(t.initial_stop, 98);
  t = one(q => { q.exit.stop.mode = 'line'; q.exit.stop.line = { indicator: 'I10', output: 'upper', params: { length: 5 } } });
  assert.deepEqual([t.initial_stop, t.initial_risk_pct], [null, null]);
});

test('price lines are the outputs of the overlay indicators without direction (the page\'s LEVEL_LINES)', () => {
  const ids = (id: string, outs: string[]) => outs.map(output => ({ indicator: id, output }));
  assert.deepEqual(LEVEL_LINES, [...ids('I01', ['sma']), ...ids('I02', ['ema']), ...ids('I03', ['wma']), ...ids('I04', ['hma']), ...ids('I05', ['kama']),
    ...ids('I09', ['supertrend']), ...ids('I10', ['upper', 'basis', 'lower']), ...ids('I11', ['upper', 'basis', 'lower']), ...ids('I12', ['sar']),
    ...ids('I27', ['upper', 'basis', 'lower']), ...ids('I42', ['vwma']), ...ids('I43', ['vwap', 'upper1', 'lower1'])]);
});

test('requests outside the page controls are refused with the field that is wrong', () => {
  const m = market({ AAA: { bars: put(flat(10), 3, { v: 2000 }) } });
  const no = (f: (q: BacktestRequest) => void) => refused(() => run(prepare(m), request(9, f)));   // the picked stocks as written
  assert.deepEqual(no(q => { q.exit.take_profit.mode = 'r' }), ['INVALID_EXIT', 'exit.take_profit.mode']);
  assert.deepEqual(no(q => { q.exit.stop.mode = 'rr' }), ['INVALID_EXIT', 'exit.stop.mode']);
  assert.deepEqual(no(q => { q.exit.stop.mode = 'pct'; q.exit.stop.pct = 0 }), ['INVALID_EXIT', 'exit.stop.pct']);
  assert.deepEqual(no(q => { q.exit.stop.mode = 'atr'; q.exit.atr_length = 2.5 }), ['INVALID_PARAM', 'exit.atr_length']);
  assert.deepEqual(no(q => { q.exit.stop.mode = 'line'; q.exit.stop.line = { indicator: 'I13', output: 'rsi' } }), ['INVALID_LINE', 'exit.stop.line.indicator']);
  assert.deepEqual(no(q => { q.exit.trailing.mode = 'line'; q.exit.trailing.line = { indicator: 'I09', output: 'direction' } }), ['UNKNOWN_OUTPUT', 'exit.trailing.line.output']);
  assert.deepEqual(no(q => { q.exit.trailing.mode = 'line'; q.exit.trailing.line = { indicator: 'I01', output: 'sma', params: { length: 0 } } }), ['PARAM_OUT_OF_RANGE', 'exit.trailing.line.params.length']);
  assert.deepEqual(no(q => { q.exit.max_hold_bars = -1 }), ['INVALID_EXIT', 'exit.max_hold_bars']);
  assert.deepEqual(no(q => { q.costs.slippage = 0.1 }), ['INVALID_COSTS', 'costs.slippage']);
  assert.deepEqual(no(q => { q.costs.ara_gap_fraction = 0 }), ['INVALID_COSTS', 'costs.ara_gap_fraction']);
  assert.deepEqual(no(q => { q.sizing.allocation_fraction = 1.5 }), ['INVALID_SIZING', 'sizing.allocation_fraction']);
  assert.deepEqual(no(q => { portfolio(q, MAX_POSITIONS + 1) }), ['INVALID_PORTFOLIO', 'portfolio.max_positions']);
  assert.deepEqual(no(q => { portfolio(q, 1); q.portfolio!.tickers = Array.from({ length: MAX_PORTFOLIO_TICKERS + 1 }, (_, k) => `T${k}`) }), ['INVALID_PORTFOLIO', 'portfolio.tickers']);
  assert.deepEqual(no(q => { portfolio(q, 1); q.portfolio!.tickers = [] }), ['INVALID_PORTFOLIO', 'portfolio.tickers']);
  assert.deepEqual(no(q => { portfolio(q, 1); q.portfolio!.tickers = ['AAA', 'AAA'] }), ['INVALID_PORTFOLIO', 'portfolio.tickers']);
  assert.deepEqual(no(q => { portfolio(q, 1); delete (q.portfolio as Partial<NonNullable<BacktestRequest['portfolio']>>).tickers }), ['INVALID_PORTFOLIO', 'portfolio.tickers']);
  assert.deepEqual(no(q => { q.period.to = DAYS[40] }), ['PERIOD_AFTER_DATA', 'period.to']);
  assert.deepEqual(no(q => { q.period.from = '2024-02-30' }), ['INVALID_PERIOD', 'period.from']);
  assert.deepEqual(no(q => { q.period.from = '2024-13-01' }), ['INVALID_PERIOD', 'period.from']);
  assert.deepEqual(no(q => { q.period.from = DAYS[5]; q.period.to = DAYS[4] }), ['INVALID_PERIOD', 'period.to']);
  assert.deepEqual(no(q => { q.entry.conditions[0].enabled = false }), ['NO_ACTIVE_CONDITION', 'entry.conditions']);
  assert.deepEqual(no(q => { q.entry.conditions.push({ ...VOL('w'), params: { length: 0 } }) }), ['PARAM_OUT_OF_RANGE', 'entry.conditions[1].params.length']);
  assert.deepEqual(no(q => { q.exit.signals.conditions = [QUIET('v')] }), ['DUPLICATE_CONDITION_ID', 'exit.signals.conditions[0].id']);
  assert.deepEqual(no(q => { q.entry.window_bars = 21 }), ['INVALID_ENTRY', 'entry.window_bars']);
});

test('a rerun on the same context reuses the indicator outputs and gives the same ledger; cancel and progress hooks', () => {
  const m = market({ AAA: { bars: walk(60, 5) } });
  const r = request(59, q => { q.entry.conditions = [{ id: 'rsi', kind: 'indicator', indicator: 'I13', lhs: { type: 'output', output: 'rsi' }, op: 'lt', rhs: { type: 'value', value: 45 } }]; q.exit.stop.mode = 'atr' }, 20);
  const ctx = prepare(m), a = run(ctx, r), memo = ctx.tickers.get('AAA')!.calc.memo.size;
  const steps: [number, number][] = [];
  const b = run(ctx, r, { progress: (d, t) => steps.push([d, t]) });
  assert.deepEqual(b, a);
  assert.equal(ctx.tickers.get('AAA')!.calc.memo.size, memo);
  assert.deepEqual(steps.at(-1), [1 + 40, 1 + 40]);
  assert.throws(() => run(ctx, r, { shouldStop: () => true }), Cancelled);
});

test('the signals preview counts the same entry events as the backtest (portfolio table before a run)', () => {
  const m = market({ AAA: { bars: walk(70, 1) }, BBB: { bars: walk(70, 2) }, CCC: { bars: walk(70, 3) } });
  const r = request(69, q => { portfolio(q, 2); q.entry = { logic: 'at_least', at_least: 2, window_bars: 4, conditions: [
    { id: 'rsi', kind: 'indicator', indicator: 'I13', lhs: { type: 'output', output: 'rsi' }, op: 'lt', rhs: { type: 'value', value: 50 } },
    { id: 'dip', kind: 'price_action', type: 'dip', op: 'lte', value: -0.01 }, VOL('v', 9e5)] } }, 25);
  const ctx = prepare(m), l = run(ctx, picking(m, r));
  assert.ok(l.per_ticker_signals.some(x => x.entry_signals > 1));
  for (const row of l.per_ticker_signals) {
    const p = ctx.tickers.get(row.ticker)!;
    assert.deepEqual({ ticker: row.ticker, ...previewRow(p.calc, p.data.prices.dates, { entry: r.entry }, r.period.from, r.period.to) }, row);
  }
});

/* ---- review findings 2026-10-26 ------------------------------------------------------------------------------- */

test('no look-ahead through the data checks: a result inside the period never depends on bars after period.to', () => {
  // BBB lists on DAYS[60]: 20 bars inside a period ending DAYS[79]; ALL of volume above 1,500 (true on BBB's bar 5)
  // and close above SMA(30), which has no value on BBB before its bar 29 (DAYS[89], after period.to), so its entry
  // cannot switch on inside the period (with ANY it runs: the next test)
  const D = weekdays(110, '2024-01-01'), sma30: Condition = { id: 's', kind: 'indicator', indicator: 'I01', params: { length: 30 }, lhs: { type: 'price' }, op: 'gt', rhs: { type: 'output', output: 'sma' } };
  const all = D.slice(60), bb = put(flat(all.length), 5, { v: 2000 });
  const mk = (bDates: string[]) => {
    const m = market({ AAA: { bars: flat(110), dates: D }, BBB: { bars: bb.slice(0, bDates.length), dates: bDates } }, D);
    return m;
  };
  const r = (single: boolean) => {
    const q = request(0, x => { if (!single) portfolio(x, 2); else x.single!.ticker = 'BBB'; x.entry = { logic: 'all', at_least: 1, window_bars: 1, conditions: [VOL(), sma30] } }, 0);
    q.period = { from: D[single ? 60 : 40], to: D[79], oos_fraction: 0 };
    return q;
  };
  const later = mk(all), asOfTo = mk(all.filter(d => d <= D[79]));
  // the portfolio leaves BBB out in both: its SMA(30) has no value on its bars up to period.to
  const a = go(later, r(false)), b = go(asOfTo, r(false));
  assert.deepEqual(a, b);
  assert.deepEqual(a.warnings[0].reasons!.map(x => [x.ticker, x.code, x.field]), [['BBB', 'INDICATOR_OUTPUT_EMPTY', 'entry.conditions[1].rhs']]);
  assert.match(a.warnings[0].reasons![0].message, /up to the end of the period/);
  // single mode refuses it in both
  assert.deepEqual(refused(() => go(later, r(true))), ['INDICATOR_OUTPUT_EMPTY', 'entry.conditions[1].rhs']);
  assert.deepEqual(refused(() => go(asOfTo, r(true))), ['INDICATOR_OUTPUT_EMPTY', 'entry.conditions[1].rhs']);
  // flow: broker rows only after period.to (FLOW_UNAVAILABLE), or a window that has a value only after it (FLOW_OUTPUT_EMPTY)
  const fr = (to: number) => request(to, q => { portfolio(q, 1); q.entry = { logic: 'all', at_least: 1, window_bars: 1, conditions: [VOL(), FNET10] } }, 0);
  const fm = (flow: ReturnType<typeof flowOf>, n = 40) => market({ AAA: { bars: put(flat(n), 24, { v: 2000 }), flow: flowOf(n, 0, n - 1) as any }, DDD: { bars: put(flat(n), 24, { v: 2000 }), flow: flow as any } });
  const codes = (l: Ledger) => l.warnings[0].reasons!.map(x => [x.ticker, x.code]);
  assert.deepEqual(codes(go(fm(flowOf(40, 32, 39)), fr(29))), [['DDD', 'FLOW_UNAVAILABLE']]);
  assert.deepEqual(go(fm(flowOf(40, 32, 39)), fr(29)), go(fm(flowOf(30, 30, -1), 30), fr(29)));         // cut at period.to: no row
  assert.deepEqual(codes(go(fm(flowOf(40, 25, 39)), fr(29))), [['DDD', 'FLOW_OUTPUT_EMPTY']]);
  assert.deepEqual(go(fm(flowOf(40, 25, 39)), fr(29)), go(fm(flowOf(30, 25, 29), 30), fr(29)));
  // a series with a value up to period.to is evaluated as before
  assert.deepEqual(go(fm(flowOf(40, 15, 39)), fr(29)).trades.map(t => t.ticker), ['AAA']);
});

test('no look-ahead inside the period: what a portfolio ticker trades up to a day never depends on its bars after it', () => {
  // review LA-1. Period D[40]..D[119]; BBB lists on D[60], its volume spike on its bar 5 (D[65]) buys D[66] and the
  // 5-bar time exit sells D[70]; AAA's spike on D[67] wants the one slot BBB holds. SMA(30) has its first value on
  // BBB's bar 29 (D[89]). Cut: BBB has no bar after D[80] (a suspension or a delisting), its bars up to D[80] the same.
  const D = weekdays(130, '2024-01-01'), cut = D[80], bDates = D.slice(60, 120);
  const sma30 = (id: string, op: 'gt' | 'lt' = 'gt'): Condition => ({ id, kind: 'indicator', indicator: 'I01', params: { length: 30 }, lhs: { type: 'price' }, op, rhs: { type: 'output', output: 'sma' } });
  const aa = put(flat(120), 67, { v: 2000 }), bb = put(flat(bDates.length), 5, { v: 2000 });
  const mk = (to: string, bFlow?: [ReturnType<typeof flowOf>, ReturnType<typeof flowOf>]) => {
    const n = bDates.filter(d => d <= to).length;
    return market({ AAA: { bars: aa, dates: D.slice(0, 120), ...(bFlow ? { flow: flowOf(120, 0, 119) as any } : {}) },
      BBB: { bars: bb.slice(0, n), dates: bDates.slice(0, n), ...(bFlow ? { flow: bFlow[n === bDates.length ? 0 : 1] as any } : {}) } }, D.slice(0, 120));
  };
  const q = (entry: BacktestRequest['entry'], exit: Condition[] = []) => {
    const r = request(0, x => { portfolio(x, 1); x.entry = entry; x.exit.max_hold_bars = 5; x.exit.signals = { logic: 'all', conditions: exit } });
    r.period = { from: D[40], to: D[119], oos_fraction: 0 };
    return r;
  };
  const until = (l: Ledger) => l.trades.filter(t => l.dates[t.exit_bar] <= cut).map(t => [t.ticker, l.dates[t.entry_bar], l.dates[t.exit_bar], t.exit_reason]);
  const left = (l: Ledger) => l.warnings.find(w => w.code === 'TICKERS_EXCLUDED')?.reasons?.map(x => [x.ticker, x.code, x.field]) ?? [];
  const both = (r: BacktestRequest, flow?: [ReturnType<typeof flowOf>, ReturnType<typeof flowOf>]) => {
    const full = prepare(mk(D[119], flow)), short = prepare(mk(cut, flow)), a = run(full, picking(full.data, r)), b = run(short, picking(short.data, r));
    const row = (ctx: ReturnType<typeof prepare>) => { const p = ctx.tickers.get('BBB')!; return previewRow(p.calc, p.data.prices.dates, { entry: r.entry }, r.period.from, r.period.to) };
    return { a, b, rows: () => [row(full), row(short)] };
  };
  // a condition without any value on BBB's bars up to the cut is false there, as before its first value on the full
  // bars: BBB runs on both, with the same trades up to the cut, and the preview counts the same events up to it
  const FNET_LT: Condition = { ...FNET10, op: 'lt' };                                     // never true on these flows
  const cases: [string, BacktestRequest, [ReturnType<typeof flowOf>, ReturnType<typeof flowOf>]?][] = [
    ['ANY', q({ logic: 'any', at_least: 1, window_bars: 1, conditions: [VOL(), sma30('s')] })],
    ['AT LEAST 2 of 3', q({ logic: 'at_least', at_least: 2, window_bars: 1, conditions: [VOL(), VOL('w', 1800), sma30('s')] })],
    ['an exit condition', q({ logic: 'all', at_least: 1, window_bars: 1, conditions: [VOL()] }, [sma30('x', 'lt')])],
    ['ANY, broker rows only after the cut (FLOW_UNAVAILABLE on the cut bars)', q({ logic: 'any', at_least: 1, window_bars: 1, conditions: [VOL(), FNET_LT] }), [flowOf(60, 25, 59), flowOf(21, 21, -1)]],
    ['ANY, too few broker rows up to the cut (FLOW_OUTPUT_EMPTY on the cut bars)', q({ logic: 'any', at_least: 1, window_bars: 1, conditions: [VOL(), FNET_LT] }), [flowOf(60, 15, 59), flowOf(21, 15, 20)]],
  ];
  for (const [label, r, flow] of cases) {
    const { a, b, rows } = both(r, flow);
    assert.deepEqual(until(a), [['BBB', D[66], D[70], 'time_exit']], label);
    assert.deepEqual(until(b), until(a), label);
    assert.deepEqual([left(a), left(b)], [[], []], label);
    if (!label.startsWith('an exit')) assert.deepEqual(rows(), [{ entry_signals: 1, last_signal: D[65] }, { entry_signals: 1, last_signal: D[65] }], label);
  }
  // ALL: the entry cannot switch on before SMA(30) has a value, so BBB is left out on the cut bars and trades nothing
  // up to the cut on the full ones (nor does AAA, whose flat closes are never above their SMA)
  const all = q({ logic: 'all', at_least: 1, window_bars: 1, conditions: [VOL(), sma30('s')] }), { a, b } = both(all);
  assert.deepEqual([until(a), until(b)], [[], []]);
  assert.deepEqual([left(a), left(b)], [[], [['BBB', 'INDICATOR_OUTPUT_EMPTY', 'entry.conditions[1].rhs']]]);
  // AT LEAST 2 of 3 with two of them without a value: left out the same way; single mode still refuses
  assert.deepEqual(left(both(q({ logic: 'at_least', at_least: 2, window_bars: 1, conditions: [VOL(), sma30('s'), { ...sma30('t'), params: { length: 40 } }] })).b),
    [['BBB', 'INDICATOR_OUTPUT_EMPTY', 'entry.conditions[1].rhs']]);
  const one = q({ logic: 'any', at_least: 1, window_bars: 1, conditions: [VOL(), sma30('s')] });
  one.mode = 'single'; delete one.portfolio; one.single = { ticker: 'BBB', benchmark: 'ihsg' };
  assert.deepEqual(refused(() => go(mk(cut), one)), ['INDICATOR_OUTPUT_EMPTY', 'entry.conditions[1].rhs']);
});

test('DATA_GAP counts each (ticker, calendar day) once: a missing day after an event while the ticker is held', () => {
  // AAA bought on DAYS[4]; while held its entry state switches on again on DAYS[6]; AAA has no bar on DAYS[7]
  const dates = DAYS.slice(0, 12).filter(d => d !== DAYS[7]), b = flat(dates.length); put(b, 3, { v: 2000 }); put(b, 6, { v: 2000 });
  const l = go(market({ AAA: { bars: b, dates } }, DAYS.slice(0, 12)), request(11));
  assert.equal(only(l).flags.stale_mark, true);
  assert.deepEqual(l.events.skipped.map(s => [s.signal_date, s.reason]), [[DAYS[6], 'no_next_bar']]);
  const w = l.warnings.find(x => x.code === 'DATA_GAP')!;
  assert.deepEqual([w.count, w.tickers], [1, ['AAA']]);
});

test('whole lots never cost more than the budget: no cash below 0, no exposure above 1 (no leverage)', () => {
  // 50 x 20,600 x (1 + 0.0015) is 1,031,545 in decimals, but 1 + 0.0015 is above 1.0015 in binary: 20,600 shares cost
  // 1,031,545.0000000000585 in exact arithmetic on the request's numbers, more than the capital; 205 lots fit
  const b = flat(10, 50); put(b, 3, { v: 2000 });
  const l = go(market({ AAA: { bars: b } }), request(9, q => { q.sizing.capital_idr = 1_031_545; q.costs.buy_fee = 0.0015 }));
  const t = only(l);
  assert.equal(t.shares, 20500);
  assert.equal(t.cost_idr, 50 * 20500 * (1 + 0.0015));
  assert.ok(1_031_545 - t.cost_idr >= 0);
  assert.ok(l.exposure.every(x => x <= 1), String(Math.max(...l.exposure)));
  // where the division is exact the formula is unchanged: 1,000,000 at 50 without fees buys 200 lots, cash 0
  const u = only(go(market({ AAA: { bars: b } }), request(9, q => { q.sizing.capital_idr = 1_000_000 })));
  assert.deepEqual([u.shares, u.cost_idr], [20000, 1_000_000]);
});

test('MAE / MFE of a position sold at the open: the raw open, as the bar range is raw (slippage is in the exit price only)', () => {
  const b = flat(10); put(b, 3, { v: 2000 }); put(b, 5, { v: 100 }); b[6] = bar(90, 90, 90, 90);
  const t = only(go(market({ AAA: { bars: b } }), request(9, q => { q.costs.slippage = 0.02; q.exit.signals.conditions = [QUIET()] })));
  assert.deepEqual([t.exit_reason, t.exit_phase, t.entry_price, t.exit_price], ['exit_signal', 'open', 100 * (1 + 0.02), 90 * (1 - 0.02)]);
  assert.equal(t.mae, 90 / t.entry_price - 1);
  assert.equal(t.mfe, 0);                                         // no price above the fill
});

test('portfolio ranking: a candidate without a score on its signal bar ranks after every scored one, then by ticker', () => {
  // rank_by rsi (lowest RSI first): AAA has RSI(14) 100 on its signal bar; BBB lists 5 bars before it (RSI warm-up)
  const up = Array.from({ length: 30 }, (_, i) => bar(100 + i, 100 + i, 100 + i, 100 + i)); put(up, 24, { v: 2000 });
  const late = put(flat(10), 4, { v: 2000 });
  const m = market({ AAA: { bars: up }, BBB: { bars: late, dates: DAYS.slice(20, 30) } });
  const l = go(m, request(29, q => portfolio(q, 1, 'rsi'), 20));
  assert.deepEqual(l.trades.map(t => t.ticker), ['AAA']);
  assert.deepEqual(l.events.skipped.map(s => [s.ticker, s.reason]), [['BBB', 'no_slot']]);
  // two unscored candidates: by ticker
  const n = go(market({ AAA: { bars: late, dates: DAYS.slice(20, 30) }, BBB: { bars: late, dates: DAYS.slice(20, 30) } }), request(29, q => portfolio(q, 1, 'rsi'), 20));
  assert.deepEqual(n.trades.map(t => t.ticker), ['AAA']);
});
