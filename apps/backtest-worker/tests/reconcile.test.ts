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
   And the variant hash (K3, hash.ts variantOf) on the same generator: what the engine does not read leaves it and the
   trades unchanged; a change of any one field of the request that changes the trades or the equity changes it.
   Sums are compared within the rounding bound of double arithmetic: n additions of terms bounded by S differ from the
   exact sum by at most n x 2^-53 x S, so two summation orders differ by at most 2n x 2^-53 x S = n x EPSILON x S. */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { isDeepStrictEqual } from 'node:util';
import { PRICE_ACTION } from '../../edge-bff/backtest/src/core/conditions.ts';
import { prepare, run } from '../../edge-bff/backtest/src/core/engine.ts';
import type { MarketData } from '../../edge-bff/backtest/src/core/engine.ts';
import type { BacktestRequest, Condition } from '../../edge-bff/backtest/src/core/contract.ts';
import { variantHash } from '../../edge-bff/backtest/src/core/hash.ts';
import type { Ledger } from '../../edge-bff/backtest/src/core/ledger.ts';
import { ValidationError } from '../../edge-bff/backtest/src/core/registry.ts';

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

/* ---- the variant hash is what the engine reads (CONTRACT.md section 7, K3: hash.ts variantOf) --------------------- */
/* A trial is a run's trades and equity curve. (1) What the engine does not read leaves the variant hash and the trades
   as they are: the page's reload (a new id on every card), another card order, a disabled card, `enabled: true`
   written out, the numbers of the stop, take-profit and trailing modes that are not chosen, atr_length without an ATR
   mode, at_least outside logic at_least or above the number of enabled entry cards, the exit logic without an enabled
   exit card, the OOS share, the ARA fraction while the rule is off, the allocation of a portfolio, the benchmark, the
   robustness settings and the key order. (2) Every leaf of the request changed on its own (another number, enum,
   date, ticker or flag the engine accepts): when the trades or the equity change, the variant hash changes too. */
const clone = <T>(v: T): T => JSON.parse(JSON.stringify(v));
const trialOf = (l: Ledger) => ({ dates: l.dates, equity: l.equity, exposure: l.exposure, trades: l.trades.map(({ entry_condition_ids: _ids, ...t }) => t) });
const signalsOf = (l: Ledger) => ({ ...trialOf(l), skipped: l.events.skipped, entries: l.events.entries, exits: l.events.exits, per_ticker: l.per_ticker_signals });
const shuffle = <T>(a: T[]) => { for (let i = a.length - 1; i > 0; i--) { const j = int(0, i); [a[i], a[j]] = [a[j], a[i]] } return a };
const keysReversed = (v: unknown): unknown => Array.isArray(v) ? v.map(keysReversed)
  : v && typeof v === 'object' ? Object.fromEntries(Object.entries(v).reverse().map(([k, x]) => [k, keysReversed(x)])) : v;

function unread(q0: BacktestRequest): BacktestRequest {
  const q = clone(q0), x = q.exit;
  let k = 0;
  const id = () => `${int(0, 1295).toString(36)}${(k++).toString(36)}`;                      // unique, the page's alphabet
  for (const list of [q.entry.conditions, x.signals.conditions]) { for (const c of list) c.id = id(); shuffle(list) }
  if (rnd() < 0.7) { const list = rnd() < 0.5 ? q.entry.conditions : x.signals.conditions; list.splice(int(0, list.length), 0, { ...pick(ENTRY)(), id: id(), enabled: false } as Condition) }
  for (const c of [...q.entry.conditions, ...x.signals.conditions]) if (c.enabled !== false && rnd() < 0.5) c.enabled = true;
  if (x.stop.mode !== 'pct') x.stop.pct = pick([0.02, 0.05, 0.1]);
  if (x.stop.mode !== 'atr') x.stop.atr_mult = pick([0.5, 1.5, 3]);
  if (x.stop.mode !== 'rr') x.stop.reward_risk_x = pick([0.5, 1.5, 3]);
  if (x.stop.mode !== 'line') x.stop.line = pick(LINES);
  if (x.take_profit.mode !== 'pct') x.take_profit.pct = pick([0.03, 0.1, 0.3]);
  if (x.take_profit.mode !== 'r') x.take_profit.r_multiple = pick([0.5, 1.5, 4]);
  if (x.take_profit.mode !== 'atr') x.take_profit.atr_mult = pick([1, 2.5, 5]);
  if (x.trailing.mode !== 'pct') x.trailing.pct = pick([0.02, 0.2]);
  if (x.trailing.mode !== 'chandelier') { x.trailing.chandelier_length = pick([3, 10, 30]); x.trailing.chandelier_mult = pick([1, 2.5]) }
  if (x.trailing.mode !== 'line') x.trailing.line = pick(LINES);
  if (x.stop.mode !== 'atr' && x.take_profit.mode !== 'atr') x.atr_length = pick([3, 7, 21]);
  const enabled = q.entry.conditions.filter(c => c.enabled !== false).length;
  if (q.entry.logic !== 'at_least') q.entry.at_least = int(1, 5);
  else if (q.entry.at_least >= enabled) q.entry.at_least = int(enabled, enabled + 3);
  if (!x.signals.conditions.some(c => c.enabled !== false)) x.signals.logic = pick(['any', 'all'] as const);
  q.period.oos_fraction = pick([0, 0.2, 0.3, 0.4] as const);
  if (!q.costs.skip_ara_open_gap) q.costs.ara_gap_fraction = pick([0.05, 0.3, 0.5]);
  if (q.mode === 'portfolio') q.sizing.allocation_fraction = pick([0.1, 0.5, 1]);
  else q.single!.benchmark = pick(['buy_and_hold', 'ihsg'] as const);
  q.robustness = { monte_carlo_runs: pick([0, 1000]), seed: int(0, 99), sensitivity: rnd() < 0.5 };
  return keysReversed(q) as BacktestRequest;
}

type Path = (string | number)[];
function leafPaths(v: unknown, p: Path = [], out: Path[] = []): Path[] {
  if (v && typeof v === 'object') for (const [k, x] of Object.entries(v)) leafPaths(x, [...p, Array.isArray(v) ? +k : k], out);
  else out.push(p);
  return out;
}
const valueAt = (o: unknown, p: Path) => p.reduce((v: any, k) => v[k], o);
const label = (p: Path) => p.map(k => typeof k === 'number' ? '[]' : k).join('.').replace(/\.\[\]/g, '[]');
const ENUMS: Record<string, readonly string[]> = {
  'exit.stop.mode': ['pct', 'atr', 'rr', 'line', 'none'], 'exit.take_profit.mode': ['pct', 'r', 'atr', 'none'], 'exit.trailing.mode': ['none', 'pct', 'chandelier', 'line'],
  'entry.logic': ['all', 'any', 'at_least'], 'exit.signals.logic': ['any', 'all'], 'portfolio.rank_by': ['adx', 'fnet', 'vol', 'rsi'], 'single.benchmark': ['buy_and_hold', 'ihsg'],
};
/** Another value of the leaf at p that the engine may accept, or undefined for a leaf this check does not vary (the
    schema version, the mode, a condition's kind, indicator, type, sides and id: the transformations above vary ids). */
function another(q: BacktestRequest, p: Path, m: MarketData): unknown {
  const v = valueAt(q, p), l = label(p), key = p[p.length - 1];
  if (typeof v === 'boolean') return !v;
  if (typeof v === 'number') return l === 'schema_version' ? undefined : pick([v + 1, v - 1, v * 1.5, v / 2, v + 0.01].filter(x => x !== v));
  if (typeof v !== 'string') return undefined;
  if (l === 'period.from' || l === 'period.to') return ALL[Math.min(ALL.length - 1, Math.max(0, ALL.indexOf(v) + pick([-3, -1, 1, 3])))];
  if (l === 'single.ticker') { const others = Object.keys(m.tickers).filter(t => t !== v); return others.length ? pick(others) : undefined }
  if (key === 'op' && (l === 'entry.conditions[].op' || l === 'exit.signals.conditions[].op')) {
    const c = valueAt(q, p.slice(0, -1)) as Condition;
    const ops = c.kind === 'indicator' ? ['gt', 'lt', 'crosses_above', 'crosses_below'] : c.kind === 'price_action' ? PRICE_ACTION[c.type].ops : [];
    const others = ops.filter(o => o !== v);
    return others.length ? pick(others) : undefined;
  }
  const options = ENUMS[l]?.filter(o => o !== v);
  return options?.length ? pick(options) : undefined;
}

test('the variant hash is what the engine reads: unread fields keep it and the trades, every field that changes a trade changes it', async () => {
  const runOrRefused = (ctx: ReturnType<typeof prepare>, q: BacktestRequest): Ledger | null => {
    try { return run(ctx, q) } catch (e) { if (e instanceof ValidationError) return null; throw e }
  };
  seed = 20261027;                                                     // its own sequence, whichever tests run before it
  const read = new Set<string>(), unreadSeen = new Set<string>();
  let requests = 0, variations = 0;
  for (let c = 0; c < 60; c++) {
    const m = randomMarket(), ctx = prepare(m);
    for (let n = 0; n < 2; n++) {
      const q = randomRequest(m), base = runOrRefused(ctx, q);
      if (!base) continue;
      requests++;
      const h = await variantHash(q), trial = trialOf(base), signals = signalsOf(base);
      for (let k = 0; k < 3; k++) {
        const u = unread(q), l = run(ctx, u);
        assert.equal(await variantHash(u), h, `unread fields changed the variant hash: ${JSON.stringify(u)}`);
        assert.deepEqual(signalsOf(l), signals, 'unread fields changed the run');
      }
      for (const p of leafPaths(q)) {
        const v = another(q, p, m);
        if (v === undefined) continue;
        const q2 = clone(q), parent = valueAt(q2, p.slice(0, -1));
        parent[p[p.length - 1]] = v;
        const l2 = runOrRefused(ctx, q2);
        if (!l2) continue;
        variations++;
        const h2 = await variantHash(q2);
        if (!isDeepStrictEqual(trialOf(l2), trial)) {
          assert.notEqual(h2, h, `${label(p)}: ${JSON.stringify(valueAt(q, p))} -> ${JSON.stringify(v)} changes the trades or the equity, not the variant hash`);
          read.add(label(p));
        } else if (h2 === h) unreadSeen.add(label(p));
      }
    }
  }
  // the generator must reach what the engine reads, and leaves it does not read must come back with the same hash
  assert.ok(requests >= 60 && variations >= 2000, `${requests} requests, ${variations} variations`);
  for (const f of ['period.from', 'period.to', 'single.ticker', 'portfolio.max_positions', 'portfolio.rank_by', 'portfolio.min_avg_value_20d_idr',
    'entry.logic', 'entry.at_least', 'entry.window_bars', 'entry.conditions[].enabled', 'entry.conditions[].op', 'entry.conditions[].params.length', 'entry.conditions[].rhs.value', 'entry.conditions[].value',
    'exit.atr_length', 'exit.stop.mode', 'exit.stop.pct', 'exit.stop.atr_mult', 'exit.stop.reward_risk_x', 'exit.take_profit.mode', 'exit.take_profit.pct', 'exit.take_profit.r_multiple', 'exit.take_profit.atr_mult',
    'exit.trailing.mode', 'exit.trailing.pct', 'exit.trailing.chandelier_length', 'exit.trailing.chandelier_mult', 'exit.max_hold_bars', 'exit.signals.logic', 'exit.signals.conditions[].rhs.value',
    'sizing.capital_idr', 'sizing.allocation_fraction', 'costs.buy_fee', 'costs.sell_fee', 'costs.slippage', 'costs.skip_ara_open_gap', 'costs.ara_gap_fraction'])
    assert.ok(read.has(f), `no variation of ${f} changed the trades (${[...read].sort().join(', ')})`);
  for (const f of ['period.oos_fraction', 'single.benchmark', 'robustness.seed', 'robustness.monte_carlo_runs', 'robustness.sensitivity', 'exit.stop.atr_mult', 'exit.take_profit.r_multiple', 'exit.trailing.pct', 'entry.at_least'])
    assert.ok(unreadSeen.has(f), `no variation of ${f} where the engine does not read it (${[...unreadSeen].sort().join(', ')})`);
});
