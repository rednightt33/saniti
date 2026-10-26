/* Reconciliation of the engine's ledger on randomly generated markets and requests (test-only generator: random walks
   with suspensions, late listings and tickers that stop trading before the end; random entry and exit rules, costs,
   sizing and portfolio settings). For every run:
   - cash (rebuilt from the trades' costs and proceeds) + market value (shares x the ticker's last close) = equity on
     every day, and exposure = market value / equity;
   - every trade: cost = entry fill x shares x (1 + buy fee), proceeds = exit fill x shares x (1 - sell fee),
     pnl = proceeds - cost, return = pnl / cost; fills at the bar's prices with slippage; whole lots;
   - capital + sum of pnl = final equity (all positions are closed at the end of the test);
   - per-ticker pnl sums to the total;
   - trades never overlap in one ticker, never exceed the free slots, and each executes an entry switch-on of its
     ticker on the next calendar day; every entry event is a trade or a skipped signal;
   - a repeated run (same context, and a fresh one) is deep-equal.
   Sums are compared within the rounding bound of double arithmetic: n additions of terms bounded by S differ from the
   exact sum by at most n x 2^-53 x S, so two summation orders differ by at most 2n x 2^-53 x S = n x EPSILON x S. */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { prepare, run } from '../../edge-bff/backtest/src/core/engine.ts';
import type { MarketData } from '../../edge-bff/backtest/src/core/engine.ts';
import type { BacktestRequest, Condition } from '../../edge-bff/backtest/src/core/contract.ts';
import type { Ledger } from '../../edge-bff/backtest/src/core/ledger.ts';

let seed = 20261026;
const rnd = () => ((seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0) / 4294967296);
const pick = <T>(a: readonly T[]): T => a[Math.floor(rnd() * a.length)];
const int = (lo: number, hi: number) => lo + Math.floor(rnd() * (hi - lo + 1));

const weekdays = (n: number, start: string) => {
  const out: string[] = [];
  for (let t = Date.parse(`${start}T00:00:00Z`); out.length < n; t += 864e5) { const d = new Date(t).getUTCDay(); if (d && d < 6) out.push(new Date(t).toISOString().slice(0, 10)) }
  return out;
};
const ALL = weekdays(260, '2023-01-02');

function series(ticker: string, dates: string[], p0: number, withVolume: boolean) {
  let p = p0;
  const O: number[] = [], H: number[] = [], L: number[] = [], C: number[] = [], V: (number | null)[] = [];
  for (let i = 0; i < dates.length; i++) {
    const o = p * (1 + (rnd() - 0.5) * 0.03 + (rnd() < 0.03 ? (rnd() - 0.4) * 0.4 : 0));   // occasional gaps (ARA, stops)
    const c = o * (1 + (rnd() - 0.48) * 0.06);
    O.push(o); C.push(c); H.push(Math.max(o, c) * (1 + rnd() * 0.03)); L.push(Math.min(o, c) * (1 - rnd() * 0.03));
    V.push(withVolume ? Math.round(1e6 * (0.3 + rnd() * (rnd() < 0.1 ? 4 : 1))) : null);
    p = c;
  }
  return { ticker, dates, dropped: 0, bars: { T: dates, O, H, L, C, V } };
}

function randomMarket(): MarketData {
  const n = int(1, 6), tickers: MarketData['tickers'] = {};
  for (let k = 0; k < n; k++) {
    const start = int(0, 60), end = rnd() < 0.2 ? ALL.length - int(1, 5) : ALL.length;   // late listing, early stop
    const dates = ALL.slice(start, end).filter(() => rnd() > 0.02);                        // suspensions
    const t = `T${String.fromCharCode(65 + k)}${k}`, s = series(t, dates, pick([80, 400, 1500, 6000]), true);
    const actions = dates.filter(() => rnd() < 0.01).map(date => ({ date, type: pick(['stock_split', 'bonus', 'rights']) }));
    tickers[t] = { prices: s as any, corporate_actions: actions, flow: { fnet: Float64Array.from(dates, () => (rnd() - 0.5) * 1e10), brokers: new Map() } as any };
  }
  const ihsg = ALL.filter(() => rnd() > 0.01);
  return { ihsg: series('IHSG', ihsg, 7000, false) as any, tickers };
}

const ENTRY: (() => Omit<Condition, 'id'>)[] = [
  () => ({ kind: 'indicator', indicator: 'I13', params: { length: pick([6, 10, 14]) }, lhs: { type: 'output', output: 'rsi' }, op: pick(['lt', 'gt', 'crosses_above', 'crosses_below'] as const), rhs: { type: 'value', value: pick([30, 40, 50, 60]) } }),
  () => ({ kind: 'indicator', indicator: 'I01', params: { length: pick([5, 10, 20]) }, lhs: { type: 'price' }, op: pick(['gt', 'crosses_above'] as const), rhs: { type: 'output', output: 'sma' } }),
  () => ({ kind: 'indicator', indicator: 'I07', lhs: { type: 'output', output: 'plus_di' }, op: 'gt', rhs: { type: 'output', output: 'minus_di' } }),
  () => ({ kind: 'price_action', type: 'dip', op: 'lte', value: pick([-0.01, -0.02]) }),
  () => ({ kind: 'price_action', type: 'breakout', params: { length: pick([5, 10]) }, op: 'close_above_high' }),
  () => ({ kind: 'price_action', type: 'volspike', params: { length: 10 }, op: 'gt', value: pick([1.2, 1.5]) }),
  () => ({ kind: 'price_action', type: 'macross', params: { fast_length: 5, slow_length: 20 }, op: pick(['golden_cross', 'fast_above_slow']) }),
];
const EXIT: (() => Omit<Condition, 'id'>)[] = [
  () => ({ kind: 'indicator', indicator: 'I13', lhs: { type: 'output', output: 'rsi' }, op: 'gt', rhs: { type: 'value', value: pick([60, 70]) } }),
  () => ({ kind: 'indicator', indicator: 'I01', params: { length: 10 }, lhs: { type: 'price' }, op: 'lt', rhs: { type: 'output', output: 'sma' } }),
];
const LINES = [{ indicator: 'I01', output: 'sma', params: { length: 10 } }, { indicator: 'I10', output: 'lower' }, { indicator: 'I09', output: 'supertrend' }, { indicator: 'I27', output: 'lower' }];

function randomRequest(m: MarketData): BacktestRequest {
  const tickers = Object.keys(m.tickers), mode = tickers.length > 1 && rnd() < 0.6 ? 'portfolio' : 'single';
  const from = int(20, 120), to = int(from + 20, ALL.length - 1);
  let stop = pick(['pct', 'atr', 'rr', 'line', 'none'] as const), tp = pick(['pct', 'r', 'atr', 'none'] as const);
  if (tp === 'r' && !['pct', 'atr', 'line'].includes(stop)) stop = pick(['pct', 'atr', 'line'] as const);
  if (stop === 'rr' && !['pct', 'atr'].includes(tp)) tp = pick(['pct', 'atr'] as const);
  const conditions = Array.from({ length: int(1, 3) }, (_, k) => ({ id: `e${k}`, ...pick(ENTRY)(), ...(rnd() < 0.1 ? { enabled: false } : {}) }) as Condition);
  conditions[0].enabled = true;
  return {
    schema_version: 1, mode,
    ...(mode === 'single' ? { single: { ticker: pick(tickers), benchmark: pick(['buy_and_hold', 'ihsg'] as const) } }
      : { portfolio: { universe: 'all', max_positions: int(1, 5), rank_by: pick(['adx', 'fnet', 'vol', 'rsi'] as const), min_avg_value_20d_idr: pick([0, 0, 1e8, 5e8]) } }),
    period: { from: ALL[from], to: ALL[to], oos_fraction: 0 },
    entry: { logic: pick(['all', 'any', 'at_least'] as const), at_least: int(1, 3), window_bars: int(1, 5), conditions },
    exit: {
      atr_length: pick([5, 14]),
      stop: { mode: stop, pct: pick([0.03, 0.07]), atr_mult: pick([1, 2]), reward_risk_x: pick([1, 2]), line: pick(LINES) },
      take_profit: { mode: tp, pct: pick([0.05, 0.15]), r_multiple: pick([1, 2, 3]), atr_mult: pick([2, 3]) },
      trailing: { mode: pick(['none', 'pct', 'chandelier', 'line'] as const), pct: pick([0.05, 0.1]), chandelier_length: pick([5, 22]), chandelier_mult: pick([2, 3]), line: pick(LINES) },
      max_hold_bars: pick([0, 0, 5, 10, 20]),
      signals: { logic: pick(['any', 'all'] as const), conditions: Array.from({ length: int(0, 2) }, (_, k) => ({ id: `x${k}`, ...pick(EXIT)() }) as Condition) },
    },
    sizing: { capital_idr: pick([1e6, 1e7, 1e8]), allocation_fraction: pick([0.25, 0.5, 1]) },
    costs: { buy_fee: pick([0, 0.0015]), sell_fee: pick([0, 0.0025]), slippage: pick([0, 0.0005, 0.001]), skip_ara_open_gap: rnd() < 0.5, ara_gap_fraction: pick([0.1, 0.2, 0.25]) },
    robustness: { monte_carlo_runs: 0, seed: 7, sensitivity: false },
  };
}

/** The ticker's bar index on a date, and its last bar on or before it. */
function locate(m: MarketData, t: string) {
  const d = m.tickers[t].prices.dates, at = new Map(d.map((x, i) => [x, i]));
  return { at: (date: string) => at.get(date) ?? -1, asof: (date: string) => { let lo = 0, hi = d.length - 1, r = -1; while (lo <= hi) { const mid = (lo + hi) >> 1; if (d[mid] <= date) { r = mid; lo = mid + 1 } else hi = mid - 1 } return r } };
}

function reconcile(m: MarketData, r: BacktestRequest, l: Ledger) {
  const cap = r.sizing.capital_idr, { buy_fee: fb, sell_fee: fs, slippage: sl } = r.costs, n = l.dates.length;
  const maxPos = r.mode === 'single' ? 1 : r.portfolio!.max_positions;
  const loc = Object.fromEntries(Object.keys(m.tickers).map(t => [t, locate(m, t)]));
  const P = (t: string) => m.tickers[t].prices.bars as unknown as { O: number[]; H: number[]; L: number[]; C: number[] };
  for (const t of l.trades) {
    const b = P(t.ticker), lt = loc[t.ticker], ei = lt.at(l.dates[t.entry_bar]), si = lt.at(l.dates[t.signal_bar]);
    assert.ok(t.shares >= 100 && t.shares % 100 === 0, 'whole lots');
    assert.equal(l.events.entries[t.ticker].on[t.signal_event], t.signal_bar, 'the trade executes an entry switch-on');
    assert.equal(t.entry_bar, t.signal_bar + 1, 'fill on the next calendar day');
    assert.equal(ei, si + 1, 'the ticker has bars on the signal and the entry day');
    assert.equal(t.entry_price, b.O[ei] * (1 + sl));
    assert.equal(t.cost_idr, t.entry_price * t.shares * (1 + fb));
    assert.equal(t.proceeds_idr, t.exit_price * t.shares * (1 - fs));
    assert.equal(t.pnl_idr, t.proceeds_idr - t.cost_idr);
    assert.equal(t.return, t.pnl_idr / t.cost_idr);
    const xi = lt.at(l.dates[t.exit_bar]), px = t.exit_price / (1 - sl), last = xi >= 0 ? xi : lt.asof(l.dates[t.exit_bar]);
    assert.equal(t.bars_held, last - ei + 1);
    assert.equal(t.flags.stale_mark || xi < 0, t.flags.stale_mark);
    if (t.exit_phase === 'open') assert.equal(t.exit_price, b.O[xi] * (1 - sl));
    else if (t.exit_phase === 'close') assert.equal(t.exit_price, b.C[last] * (1 - sl));
    else assert.ok(px >= b.L[xi] * (1 - 1e-12) && px <= b.H[xi] * (1 + 1e-12), 'intraday fill inside the bar');
    assert.ok(t.exit_bar >= t.entry_bar && t.mae <= 0 && t.mfe >= 0);
    assert.ok(t.flags.corporate_actions.every(c => c.date > l.dates[t.entry_bar] && c.date <= l.dates[t.exit_bar]));
  }
  // trades never overlap in a ticker; a sale at the open may be followed by a buy at the same open
  const scale = cap + l.trades.reduce((s, t) => s + t.cost_idr + t.proceeds_idr, 0);   // bounds every partial sum of cash
  const by = new Map<string, Ledger['trades']>();
  for (const t of l.trades) by.set(t.ticker, [...(by.get(t.ticker) || []), t]);
  for (const [, ts] of by) {
    ts.sort((a, b) => a.entry_bar - b.entry_bar);
    for (let k = 1; k < ts.length; k++) assert.ok(ts[k].entry_bar > ts[k - 1].exit_bar || (ts[k].entry_bar === ts[k - 1].exit_bar && ts[k - 1].exit_phase === 'open'), 'overlap');
  }
  // every entry event inside the period is a trade or a skipped signal, once
  for (const [t, tr] of Object.entries(l.events.entries)) {
    const evs = [...l.trades.filter(x => x.ticker === t).map(x => x.signal_event), ...l.events.skipped.filter(x => x.ticker === t).map(x => x.signal_event)].sort((a, b) => a - b);
    assert.deepEqual(evs, tr.on.map((_, k) => k), `events of ${t}`);
  }
  // cash + market value = equity, every day
  for (let k = 0; k < n; k++) {
    let cash = cap, mv = 0, open = 0;
    for (const t of l.trades) {
      if (t.entry_bar <= k) cash -= t.cost_idr;
      if (t.exit_bar <= k) cash += t.proceeds_idr;
      if (t.entry_bar <= k && t.exit_bar > k) { mv += t.shares * P(t.ticker).C[loc[t.ticker].asof(l.dates[k])]; open++ }
    }
    const held = l.trades.filter(t => t.entry_bar <= k && (t.exit_bar > k || (t.exit_bar === k && t.exit_phase !== 'open'))).length;
    assert.ok(held <= maxPos, `day ${k}: ${held} positions, max ${maxPos}`);
    const tol = (2 * l.trades.length + open + 2) * Number.EPSILON * scale;
    assert.ok(cash >= -tol, `day ${k}: cash ${cash}`);
    assert.ok(Math.abs(cash + mv - l.equity[k]) <= tol, `day ${k}: cash ${cash} + mv ${mv} != equity ${l.equity[k]}`);
    // market value <= equity (no leverage): the two sums of `open` terms differ by at most open x EPSILON x equity
    assert.ok(Math.abs(mv / l.equity[k] - l.exposure[k]) <= (open + 2) * Number.EPSILON, `day ${k}: exposure`);
  }
  // all positions are closed at the end: capital + sum of pnl = final equity; per-ticker pnl sums to the total
  assert.ok(l.trades.every(t => t.exit_bar < n));
  const total = l.trades.reduce((s, t) => s + t.pnl_idr, 0), tol = (2 * l.trades.length + 2) * Number.EPSILON * scale;
  assert.ok(Math.abs(cap + total - l.equity[n - 1]) <= tol, `final equity ${l.equity[n - 1]} vs ${cap + total}`);
  const perTicker = [...by.values()].reduce((s, ts) => s + ts.reduce((u, t) => u + t.pnl_idr, 0), 0);
  assert.ok(Math.abs(perTicker - total) <= tol);
  assert.equal(l.exposure[n - 1], 0);
}

test('random markets and requests reconcile: cash, equity, pnl, positions and events', () => {
  let trades = 0, runs = 0, portfolios = 0, kinds = new Set<string>();
  for (let c = 0; c < 60; c++) {
    const m = randomMarket(), ctx = prepare(m);
    for (let q = 0; q < 4; q++) {
      const r = randomRequest(m);
      const l = run(ctx, r);
      reconcile(m, r, l);
      assert.deepEqual(run(ctx, r), l, 'rerun on the same context');
      if (q === 0) assert.deepEqual(run(prepare(m), r), l, 'rerun on a fresh context');
      trades += l.trades.length; runs++; if (r.mode === 'portfolio') portfolios++;
      for (const t of l.trades) kinds.add(`${t.exit_reason}/${t.exit_phase}`);
      for (const s of l.events.skipped) kinds.add(s.reason);
      if (l.trades.some(t => t.flags.stale_mark)) kinds.add('stale_mark');
      if (l.trades.some(t => t.flags.corporate_actions.length)) kinds.add('corporate_actions');
    }
  }
  // the generator must reach the rules it is meant to check
  assert.ok(trades > 500 && portfolios > 50, `${trades} trades in ${runs} runs (${portfolios} portfolio)`);
  for (const k of ['stop_loss/open', 'stop_loss/intraday', 'trailing_stop/intraday', 'take_profit/open', 'take_profit/intraday', 'time_exit/close', 'exit_signal/open', 'end_of_test/close',
    'already_held', 'no_slot', 'ara_open_gap', 'below_min_value', 'no_next_bar', 'period_end', 'stale_mark', 'corporate_actions'])
    assert.ok(kinds.has(k), `not reached: ${k} (${[...kinds].sort().join(', ')})`);
});
