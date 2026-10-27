/* The worker's job and preview orchestration (src/run.ts, src/load.ts, src/validate.ts) on real stored bars: the
   Terminal parity fixtures (apps/edge-bff/terminal/tests/calc/fixtures: 7 stocks and IHSG as Feature 04 stores them)
   published by tests/fake-terminal.mjs in the publisher's format and read back through terminal-api's /bundle and
   presigned files. A run's result must be what the shared core computes from the same bars (prepare, run, the
   sensitivity reruns, buildResult), with the versions and hashes of CONTRACT.md sections 2 and 7; every refusal names
   its field; the limits refuse before any file is downloaded; cancellation stops between and inside phases.
   Sector names and company names of the fake reference list are test labels, not published values; the broker rows
   and the corporate action of the flow and events tests are test rows, marked where they are made. */
import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { loadFixtures } from '../../edge-bff/terminal/tests/calc/fixtures.mjs';
import type { BacktestRequest, BacktestResult, Condition, JobProgress } from '../../edge-bff/backtest/src/core/contract.ts';
import { DEFAULT_ENTRY, LEGACY, legacyCard, legacyToCondition } from '../../edge-bff/backtest/src/core/catalog.ts';
import type { LegacyCard } from '../../edge-bff/backtest/src/core/catalog.ts';
import { Calc } from '../../edge-bff/backtest/src/core/conditions.ts';
import { DataError, dataVersion } from '../../edge-bff/backtest/src/core/datafile.ts';
import type { PriceSeries } from '../../edge-bff/backtest/src/core/datafile.ts';
import { Cancelled, MAX_PORTFOLIO_TICKERS, MAX_POSITIONS, prepare, run } from '../../edge-bff/backtest/src/core/engine.ts';
import type { Exclusion } from '../../edge-bff/backtest/src/core/engine.ts';
import { lineageKey, requestHash, variantHash } from '../../edge-bff/backtest/src/core/hash.ts';
import type { CellRun } from '../../edge-bff/backtest/src/core/ledger.ts';
import { ValidationError } from '../../edge-bff/backtest/src/core/registry.ts';
import { assertFiniteJson, buildResult } from '../../edge-bff/backtest/src/core/result.ts';
import { sensitivityPlan } from '../../edge-bff/backtest/src/core/robustness.ts';
import { previewRow, requestConditions } from '../../edge-bff/backtest/src/core/signals.ts';
import type { Config } from '../src/config.ts';
import { WorkerError } from '../src/errors.ts';
import { PlannedClient } from '../src/load.ts';
import { runJob, runSignals } from '../src/run.ts';
import type { RunEnv } from '../src/run.ts';
import type { TickerRef } from '../src/terminal.ts';
import { checkRequest } from '../src/validate.ts';
import type { References } from '../src/validate.ts';
import { ENGINE_VERSION, REGISTRY_VERSION } from '../src/version.ts';
import { EVENT_COLUMNS, brokerArchive, brokersRef, encode, eventsDoc, pricePack, startFakeTerminal, tickersRef } from './fake-terminal.mjs';

/* ---- the published market: the fixtures' bars as price packs ------------------------------------------------------- */
interface Fixture { ticker: string; T: string[]; O: number[]; H: number[]; L: number[]; C: number[]; V: (number | null)[] }
const FX = new Map((loadFixtures() as Fixture[]).map(f => [f.ticker, f]));
const STOCKS = [...FX.keys()].filter(t => t !== 'IHSG').sort();
const THROUGH = [...FX.values()].map(f => f.T[f.T.length - 1]).sort().pop()!;
const SECTOR: Record<string, string> = { BBCA: 'Sector A', UNVR: 'Sector A', GOTO: 'Sector A' };    // test labels
const rowsOf = (f: Fixture) => f.T.map((d, i) => [d, f.O[i], f.H[i], f.L[i], f.C[i], f.V[i]]);
const PACK = new Map([...FX.values()].map(f => [f.ticker, pricePack(f.ticker, rowsOf(f))]));
const series = (t: string): PriceSeries => { const f = FX.get(t)!; return { ticker: t, dates: f.T, dropped: 0, bars: { O: f.O, H: f.H, L: f.L, C: f.C, V: f.V, T: f.T } } };
type Extra = Record<string, { events?: object; broker?: { data_through: string; doc: object } }>;
function market(extra: Extra = {}) {
  const out: Record<string, unknown> = {};
  for (const [t, f] of FX) {
    const e = extra[t] ?? {};
    out[t] = { generated_at: '2026-10-25T18:20:00+00:00', datasets: {
      price: { data_through: THROUGH, first_year: +f.T[0].slice(0, 4), files: [{ pack: 'price', doc: PACK.get(t) }] },
      ...(t === 'IHSG' ? {} : { events: { data_through: e.events ? '2026-10-25 17:04:28+00' : null, files: e.events ? [{ doc: e.events }] : [] } }),
      ...(e.broker ? { broker: { data_through: e.broker.data_through, first_year: 2026, files: [{ pack: 'broker-archive', doc: e.broker.doc }] } } : {}),
    } };
  }
  return out;
}
// the publisher's columns (fake-terminal.mjs TICKER_COLUMNS): sector and industry (test labels)
const REF_ROWS = [...FX.keys()].sort().map(t => [t, `${t} (test name)`, t === 'IHSG' ? 'index' : 'stock', t === 'IHSG' ? null : SECTOR[t] ?? 'Sector B',
  t === 'IHSG' ? 'Undefined' : 'Industry B']);
const REFS = { tickers: tickersRef(REF_ROWS), brokers: brokersRef([['YU', 'test broker', 'Foreign'], ['ZP', 'test broker', 'Domestic']]) };
/** A stock of the reference list without any published file (test row). */
const NOPX: TickerRef = { ticker: 'NOPX', name: 'NOPX (test name)', type: 'stock', groups: { sector: 'Sector C', industry: 'Industry C' } };
/** The stocks of the test label Sector A, a picked set of three. */
const SECTOR_A = ['BBCA', 'GOTO', 'UNVR'];

const KEY = 'run-test-proxy-key-'.padEnd(48, 'x');
const LIMITS: Config['limits'] = { max_positions: MAX_POSITIONS, window_bars: { min: 1, max: 20 }, monte_carlo_runs: 1000, max_portfolio_tickers: MAX_PORTFOLIO_TICKERS, max_download_bytes: 1e9, max_broker_rows: 1e9, timeout_seconds: 600, queued_per_owner: 3, max_conditions: 20 };
const OFF: Config['flow'] = { enabled: false, reason: 'flow is off in this test' };
let fake: Awaited<ReturnType<typeof startFakeTerminal>>;
let refs: References;
/** The reference lists with NOPX added (a stock without any published file). */
const withNopx = () => ({ ...refs, tickers: [...refs.tickers, NOPX] });
const env = (over: { limits?: Partial<Config['limits']>; flow?: Config['flow']; url?: string } = {}): RunEnv => ({
  client: new PlannedClient({ url: over.url ?? fake.url, proxyKey: KEY, cacheBytes: 100_000_000, concurrency: 4, retries: 0, retryBaseMs: 0, timeoutMs: 20_000, fileOrigin: over.url ?? fake.url, maxFileBytes: 100_000_000 }),
  config: { limits: { ...LIMITS, ...over.limits }, flow: over.flow ?? OFF, terminal: { concurrency: 4 } },
  versions: { engine_version: ENGINE_VERSION, registry_version: REGISTRY_VERSION },
});
before(async () => {
  fake = await startFakeTerminal({ key: KEY, tickers: market(), refs: REFS });
  const c = env().client;
  refs = { tickers: (await c.reference('tickers')).tickers, brokers: await c.reference('brokers') };
});
after(() => fake.close());

/* ---- the page's default settings (edge-bff/backtest/src/state.ts S, api/request.ts buildRequest) ---------------------- */
/** The request the page sends with its boot settings: the default entry cards through the page's one card mapping
    (core catalog.ts DEFAULT_ENTRY, legacyToCondition), without the flow cards (the page leaves out a card that is not
    ready, and flow cards are not ready while catalog.flow.available is false); percents divided by 100 as buildRequest
    does; Monte Carlo runs = catalog limits.monte_carlo_runs; the period from S.from to the catalog's data_through. */
function pageDefault(ticker: string, flow = false): BacktestRequest {
  const cards = DEFAULT_ENTRY.map(([t, over], k) => legacyCard(t, `c${k + 1}`, over as Partial<LegacyCard>)).filter(c => flow || LEGACY[c.type].group !== 'flow');
  return {
    schema_version: 1, mode: 'single', single: { ticker, benchmark: 'buy_and_hold' },
    period: { from: '2019-06-03', to: THROUGH, oos_fraction: 30 / 100 as 0.3 },
    entry: { logic: 'at_least', at_least: 3, window_bars: 5, conditions: cards.map(legacyToCondition) },
    exit: {
      atr_length: 14,
      stop: { mode: 'pct', pct: 7 / 100, atr_mult: 2, reward_risk_x: 2, line: { indicator: 'I09', output: 'supertrend' } },
      take_profit: { mode: 'pct', pct: 15 / 100, r_multiple: 2, atr_mult: 3 },
      trailing: { mode: 'none', pct: 5 / 100, chandelier_length: 22, chandelier_mult: 3, line: { indicator: 'I01', output: 'sma' } },
      max_hold_bars: 20, signals: { logic: 'any', conditions: [] },
    },
    sizing: { capital_idr: 100e6, allocation_fraction: 100 / 100 },
    costs: { buy_fee: .15 / 100, sell_fee: .25 / 100, slippage: .05 / 100, skip_ara_open_gap: true, ara_gap_fraction: 0.2 },
    robustness: { monte_carlo_runs: 1000, seed: 7, sensitivity: true },
  };
}
/** The page's portfolio defaults on picked stocks (every fixture stock unless named), 5 positions, ranked by ADX,
    minimum 20-day value Rp 5 B. */
function portfolioDefault(tickers: string[] = STOCKS): BacktestRequest {
  const q = pageDefault('BBCA');
  delete q.single;
  return { ...q, mode: 'portfolio', portfolio: { tickers: [...tickers], max_positions: 5, rank_by: 'adx', min_avg_value_20d_idr: 5 * 1e9 } };
}
const clone = <T>(x: T): T => JSON.parse(JSON.stringify(x));

/** The oracle: the shared core run on the fixture bars directly (no terminal-api, no worker), as CONTRACT.md sections
    4-7 compose it: prepare, run, one run per sensitivity cell, buildResult with the hashes and versions. */
async function direct(q: BacktestRequest, tickers: string[], files: { ticker: string; dataset: string; sha256: string }[], prior: { variant_hash: string; sharpe_daily: number }[] = [],
  excluded?: Exclusion[]): Promise<BacktestResult> {
  const ctx = prepare({ ihsg: series('IHSG'), tickers: Object.fromEntries(tickers.map(t => [t, { prices: series(t), corporate_actions: [] }])), ...(excluded ? { excluded } : {}) });
  const ledger = run(ctx, q), plan = sensitivityPlan(q);
  let sensitivity = null;
  if (plan) {
    const cells: (CellRun | null)[][] = [];
    for (const row of plan.requests) { const r: (CellRun | null)[] = []; for (const c of row) r.push(c ? { ledger: run(ctx, c), variant_hash: await variantHash(c) } : null); cells.push(r) }
    const { requests: _r, ...axes } = plan;
    sensitivity = { ...axes, cells };
  }
  const data_version = await dataVersion(files), v = { engine_version: ENGINE_VERSION, registry_version: REGISTRY_VERSION, data_version };
  // meta.tickers: a portfolio's tickers the run ran on (the ones it left out are in TICKERS_EXCLUDED)
  const ran = q.mode === 'single' ? tickers : ledger.per_ticker_signals.map(t => t.ticker);
  return buildResult({ request: q, ledger, versions: { ...v, data_through: THROUGH }, tickers: ran, prior_trials: prior, sensitivity, duration_ms: 0,
    variant_hash: await variantHash(q), lineage_key: await lineageKey(q), request_hash: await requestHash(q, v) });
}
const priceFile = (t: string) => ({ ticker: t, dataset: 'price', sha256: encode(PACK.get(t)).sha256 });
const noDuration = (r: BacktestResult) => ({ ...r, meta: { ...r.meta, duration_ms: 0 } });
function finiteOrNull(v: unknown, path = 'result'): void {
  if (typeof v === 'number') assert.ok(Number.isFinite(v), `${path} = ${v}`);
  else if (Array.isArray(v)) v.forEach((x, i) => finiteOrNull(x, `${path}[${i}]`));
  else if (v && typeof v === 'object') for (const [k, x] of Object.entries(v)) finiteOrNull(x, `${path}.${k}`);
  else assert.ok(v === null || typeof v === 'string' || typeof v === 'boolean', `${path} is ${typeof v}`);
}
/** The value with every -0 as 0, as JSON carries it (stats.ts gives a gross loss of -0 when there is no loss). */
const plusZero = (v: unknown): unknown => typeof v === 'number' ? (v === 0 ? 0 : v) : Array.isArray(v) ? v.map(plusZero)
  : v && typeof v === 'object' ? Object.fromEntries(Object.entries(v).map(([k, x]) => [k, plusZero(x)])) : v;
const refusal = async (p: Promise<unknown>) => {
  try { await p } catch (e) { return [(e as { code: string }).code, (e as { field?: string }).field] }
  assert.fail('not refused');
};
const PHASES: JobProgress['phase'][] = ['loading', 'signals', 'backtest', 'sensitivity', 'monte_carlo', 'finalizing'];

/* ---- single and portfolio jobs --------------------------------------------------------------------------------------- */
test('a single-stock job with the page default settings: every phase in order, and the result the core computes from the same bars', async () => {
  const q = pageDefault(STOCKS[0]);                                    // the page picks the first published stock without MAPI
  assert.equal(q.single!.ticker, 'BBCA');
  assert.deepEqual(q.entry.conditions.map(c => c.kind === 'indicator' ? c.indicator : c.kind === 'price_action' ? c.type : c.kind), ['I07', 'I15', 'macd']);
  const seen: JobProgress[] = [];
  const t0 = performance.now();
  const r = await runJob(q, { prior_trials: [] }, refs, env(), { progress: p => seen.push(p) });
  const ms = performance.now() - t0;
  const order = seen.map(p => p.phase).filter((p, i, a) => p !== a[i - 1]);
  assert.deepEqual(order, PHASES);
  for (const p of seen) assert.ok(Number.isInteger(p.done) && Number.isInteger(p.total) && p.done <= Math.max(p.total, p.done) && p.done >= 0);
  assert.deepEqual(seen.filter(p => p.phase === 'sensitivity').pop(), { phase: 'sensitivity', done: 25, total: 25 });

  const expected = await direct(q, ['BBCA'], [priceFile('IHSG'), priceFile('BBCA')]);
  assert.deepStrictEqual(noDuration(r), noDuration(expected));
  assert.equal(r.meta.engine_version, ENGINE_VERSION); assert.equal(r.meta.registry_version, REGISTRY_VERSION);
  assert.equal(r.meta.data_version, await dataVersion([priceFile('IHSG'), priceFile('BBCA')]));
  assert.deepEqual(r.meta.tickers, ['BBCA']); assert.deepEqual(r.meta.benchmark, { kind: 'buy_and_hold', ticker: 'BBCA' });
  assert.equal(r.meta.data_through, THROUGH); assert.equal(r.dates[r.dates.length - 1], THROUGH); assert.ok(r.dates[0] >= q.period.from);
  assert.ok(r.meta.duration_ms > 0 && r.meta.duration_ms <= ms + 1);
  assert.equal(r.robustness.sensitivity!.cells.flat().filter(Boolean).length, 25);
  assert.deepEqual(r.meta.warnings.map(w => w.code), ['ADJUSTED_HISTORY_BOUNDARY', 'ARB_NOT_MODELLED', 'TICK_NOT_MODELLED']);
  assertFiniteJson(r); finiteOrNull(r);
  assert.deepStrictEqual(JSON.parse(JSON.stringify(r)), plusZero(r)); // nothing JSON would drop or change (JSON writes -0 as 0)
});

test('a single job with trades on UNVR: trades point at entry events, OOS split, Monte Carlo of 1000 runs, prior trials counted', async () => {
  const q = pageDefault('UNVR'), prior = [{ variant_hash: 'a'.repeat(64), sharpe_daily: 0.01 }, { variant_hash: 'b'.repeat(64), sharpe_daily: -0.02 }];
  const r = await runJob(q, { prior_trials: prior }, refs, env());
  assert.deepStrictEqual(noDuration(r), noDuration(await direct(q, ['UNVR'], [priceFile('IHSG'), priceFile('UNVR')], prior)));
  assert.ok(r.trades.length >= 3, `${r.trades.length} trades`);
  for (const t of r.trades) assert.equal(r.dates[r.events.entries.UNVR.on[t.signal_event]], t.signal_date);
  assert.equal(r.robustness.monte_carlo!.runs, 1000); assert.equal(r.robustness.monte_carlo!.final_returns.length, 1000);
  assert.equal(r.oos.cut, Math.floor(r.dates.length * 0.7));
  assert.equal(r.meta.trials.prior, 2); assert.equal(r.robustness.deflated.trials, r.meta.trials.total);
  assert.equal(r.meta.trials.variants[0].kind, 'run'); assert.equal(r.meta.trials.variants[0].variant_hash, await variantHash(q));
});

test('a rerun after a reload adds no trial (K3): new card ids, another card order, a disabled card, another OOS share', async () => {
  const q = pageDefault('UNVR'), a = await runJob(q, { prior_trials: [] }, refs, env());
  const b = clone(q);
  b.entry.conditions = b.entry.conditions.map((c, k) => ({ ...c, id: `r${k}x` }));                 // the page's ids are new on each load
  [b.entry.conditions[1], b.entry.conditions[2]] = [b.entry.conditions[2], b.entry.conditions[1]];   // the grid's condition (ADX) stays first
  b.entry.conditions.push({ ...b.entry.conditions[0], id: 'off1', enabled: false });
  b.period.oos_fraction = 0.2;
  const prior = a.meta.trials.variants.map(({ variant_hash, sharpe_daily }) => ({ variant_hash, sharpe_daily }));
  const r = await runJob(b, { prior_trials: prior }, refs, env());
  assert.ok(a.meta.trials.total > 1, `${a.meta.trials.total} trials`);
  assert.deepEqual([r.meta.trials.prior, r.meta.trials.this_run, r.meta.trials.total], [a.meta.trials.total, 0, a.meta.trials.total]);
  assert.deepEqual(r.robustness.deflated, a.robustness.deflated);
  assert.deepEqual([r.equity, r.trades.map(t => [t.entry_date, t.exit_date, t.pnl_idr])], [a.equity, a.trades.map(t => [t.entry_date, t.exit_date, t.pnl_idr])]);
});

test('the same request on the same published data gives the same result, cold or warm cache (meta.duration_ms aside)', async () => {
  const q = pageDefault('UNVR'), e = env();
  const a = await runJob(q, { prior_trials: [] }, refs, e), b = await runJob(clone(q), { prior_trials: [] }, refs, e), c = await runJob(clone(q), { prior_trials: [] }, refs, env());
  assert.deepStrictEqual(noDuration(b), noDuration(a)); assert.deepStrictEqual(noDuration(c), noDuration(a));
  assert.ok(e.client.stats.cache_hits >= 2, 'the second run read its files from the cache');
  const p = portfolioDefault();
  assert.deepStrictEqual(noDuration(await runJob(p, { prior_trials: [] }, refs, e)), noDuration(await runJob(clone(p), { prior_trials: [] }, refs, env())));
});

test('a portfolio job on the fixture tickers: the picked stocks, IHSG benchmark, slots, per-ticker rows, the core result', async () => {
  const q = portfolioDefault();
  const r = await runJob(q, { prior_trials: [] }, refs, env());
  assert.deepEqual(r.meta.tickers, STOCKS);
  assert.deepStrictEqual(noDuration(r), noDuration(await direct(q, STOCKS, [priceFile('IHSG'), ...STOCKS.map(priceFile)])));
  assert.deepEqual(r.meta.benchmark, { kind: 'ihsg', ticker: 'IHSG' });
  assert.ok(r.meta.warnings.some(w => w.code === 'SURVIVORSHIP'));
  assert.deepEqual(r.tables.per_ticker.map(x => x.ticker), STOCKS);
  assert.ok(r.trades.length > 0 && new Set(r.trades.map(t => t.ticker)).size > 1);
  // never more than max_positions held after a day's open entries (a sale at that open has left)
  for (let k = 0; k < r.dates.length; k++) {
    const held = r.trades.filter(t => r.dates.indexOf(t.entry_date) <= k && (r.dates.indexOf(t.exit_date) > k || (r.dates.indexOf(t.exit_date) === k && t.exit_phase !== 'open'))).length;
    assert.ok(held <= 5, `${held} positions on ${r.dates[k]}`);
  }
  assert.equal(r.robustness.monte_carlo?.scale ?? 1 / 5, 1 / 5);
  // three picked stocks: those only
  const s = await runJob(portfolioDefault(SECTOR_A), { prior_trials: [] }, refs, env());
  assert.deepEqual(s.meta.tickers, ['BBCA', 'GOTO', 'UNVR']);
  assert.deepEqual(s.tables.per_ticker.map(x => x.ticker), ['BBCA', 'GOTO', 'UNVR']);
  // PF5: more positions than picked stocks runs, each slot 1/max_positions of equity (engine.test.ts checks the sizes)
  const m = portfolioDefault(SECTOR_A); m.portfolio!.max_positions = MAX_POSITIONS;
  const w = await runJob(m, { prior_trials: [] }, refs, env());
  assert.deepStrictEqual(noDuration(w), noDuration(await direct(m, SECTOR_A, [priceFile('IHSG'), ...SECTOR_A.map(priceFile)])));
  assert.equal(w.robustness.monte_carlo?.scale ?? 1 / MAX_POSITIONS, 1 / MAX_POSITIONS);
});

test('PF3: the same picked stocks in any order give the same hashes and the same result bytes (meta.duration_ms aside), and the same preview', async () => {
  // lead decision 2026-10-27 (PF3): the worker sorts the picked stocks (engine.ts byTicker) before it hashes, records
  // the lineage or runs; NOPX (no published file) is in the set so the order of the left-out stocks is covered too
  const picked = [...STOCKS, 'NOPX'], orders = [picked, [...picked].reverse(), ['UNVR', 'NOPX', ...STOCKS.filter(t => t !== 'UNVR')]];
  const rs = [];
  for (const o of orders) rs.push(await runJob(portfolioDefault(o), { prior_trials: [] }, withNopx(), env()));
  const [a] = rs, bytes = (r: BacktestResult) => JSON.stringify(noDuration(r));
  const variant = (r: BacktestResult) => r.meta.trials.variants.find(v => v.kind === 'run')!.variant_hash;
  assert.ok(a.meta.warnings.some(w => w.code === 'TICKERS_EXCLUDED'), 'NOPX left out');
  for (const r of rs.slice(1)) {
    assert.deepEqual([r.meta.request_hash, variant(r), r.meta.lineage_key], [a.meta.request_hash, variant(a), a.meta.lineage_key]);
    assert.equal(bytes(r), bytes(a));
  }
  // the hashes are the core's of the sorted request, whatever order was sent
  const sorted = portfolioDefault([...picked].sort());
  assert.equal(variant(a), await variantHash(sorted)); assert.equal(a.meta.lineage_key, await lineageKey(sorted));
  // another set is another variant (PF4) on the same portfolio lineage
  const fewer = await runJob(portfolioDefault(SECTOR_A), { prior_trials: [] }, refs, env());
  assert.notEqual(variant(fewer), variant(a)); assert.equal(fewer.meta.lineage_key, a.meta.lineage_key);
  const entry = pageDefault('UNVR').entry, period = { from: '2019-06-03', to: THROUGH };
  const ps = [];
  for (const o of orders) ps.push(await runSignals({ schema_version: 1, tickers: o, period, entry }, withNopx(), env()));
  for (const p of ps.slice(1)) assert.equal(JSON.stringify(p), JSON.stringify(ps[0]));
});

/* ---- refusals -------------------------------------------------------------------------------------------------------- */
test('refused requests name their field and download nothing', async () => {
  const flowCard = legacyToCondition(legacyCard('fnet', 'f1', { len: 5, val: 0 }));
  const cases: [string, (q: any) => void, string, string, Partial<Config['limits']>?][] = [
    ['an index as the single ticker', q => { q.single.ticker = 'IHSG' }, 'UNKNOWN_TICKER', 'single.ticker'],
    ['an unpublished ticker', q => { q.single.ticker = 'ZZZZ' }, 'UNKNOWN_TICKER', 'single.ticker'],
    ['an unpublished picked stock', q => { delete q.single; q.mode = 'portfolio'; q.portfolio = { tickers: ['UNVR', 'ZZZZ'], max_positions: 5, rank_by: 'adx', min_avg_value_20d_idr: 0 } }, 'UNKNOWN_TICKER', 'portfolio.tickers[1]'],
    ['the index as a picked stock', q => { delete q.single; q.mode = 'portfolio'; q.portfolio = { tickers: ['IHSG'], max_positions: 5, rank_by: 'adx', min_avg_value_20d_idr: 0 } }, 'UNKNOWN_TICKER', 'portfolio.tickers[0]'],
    ['a stock picked twice', q => { delete q.single; q.mode = 'portfolio'; q.portfolio = { tickers: ['UNVR', 'BBCA', 'UNVR'], max_positions: 5, rank_by: 'adx', min_avg_value_20d_idr: 0 } }, 'INVALID_PORTFOLIO', 'portfolio.tickers'],
    [`${MAX_PORTFOLIO_TICKERS + 1} picked stocks (engine)`, q => { delete q.single; q.mode = 'portfolio'; q.portfolio = { tickers: Array.from({ length: MAX_PORTFOLIO_TICKERS + 1 }, (_, k) => `T${k}`), max_positions: 5, rank_by: 'adx', min_avg_value_20d_idr: 0 } }, 'INVALID_PORTFOLIO', 'portfolio.tickers'],
    ['4 picked stocks over a configured 3', q => { delete q.single; q.mode = 'portfolio'; q.portfolio = { tickers: STOCKS.slice(0, 4), max_positions: 3, rank_by: 'adx', min_avg_value_20d_idr: 0 } }, 'INVALID_PORTFOLIO', 'portfolio.tickers', { max_portfolio_tickers: 3 }],
    ['a catalog universe (gone, PF1)', q => { delete q.single; q.mode = 'portfolio'; q.portfolio = { universe: 'all', tickers: STOCKS, max_positions: 5, rank_by: 'adx', min_avg_value_20d_idr: 0 } }, 'UNKNOWN_FIELD', 'portfolio.universe'],
    ['a field the page does not send', q => { q.benchmark = 'ihsg' }, 'UNKNOWN_FIELD', 'benchmark'],
    ['the page\'s client_request_id (edge-bff keeps it and strips it before the worker)', q => { q.client_request_id = 'c'.repeat(32) }, 'UNKNOWN_FIELD', 'client_request_id'],
    ['a nested unknown field', q => { q.exit.stop.level = 3 }, 'UNKNOWN_FIELD', 'exit.stop.level'],
    ['an unknown condition field', q => { q.entry.conditions[0].threshold = 3 }, 'UNKNOWN_FIELD', 'entry.conditions[0].threshold'],
    ['an unknown side field', q => { q.entry.conditions[0].rhs.output = 'adx' }, 'UNKNOWN_FIELD', 'entry.conditions[0].rhs.output'],
    ['portfolio settings in single mode', q => { q.portfolio = { tickers: STOCKS } }, 'UNKNOWN_FIELD', 'portfolio'],
    ['schema_version 2', q => { q.schema_version = 2 }, 'INVALID_REQUEST', 'schema_version'],
    ['an OOS share the page does not offer', q => { q.period.oos_fraction = 0.25 }, 'INVALID_PERIOD', 'period.oos_fraction'],
    ['500 Monte Carlo runs', q => { q.robustness.monte_carlo_runs = 500 }, 'INVALID_ROBUSTNESS', 'robustness.monte_carlo_runs'],
    ['a negative seed', q => { q.robustness.seed = -1 }, 'INVALID_ROBUSTNESS', 'robustness.seed'],
    ['a fractional seed', q => { q.robustness.seed = 1.5 }, 'INVALID_ROBUSTNESS', 'robustness.seed'],
    ['sensitivity not a boolean', q => { q.robustness.sensitivity = 1 }, 'INVALID_ROBUSTNESS', 'robustness.sensitivity'],
    [`${MAX_POSITIONS + 1} positions (engine)`, q => { delete q.single; q.mode = 'portfolio'; q.portfolio = { tickers: STOCKS, max_positions: MAX_POSITIONS + 1, rank_by: 'adx', min_avg_value_20d_idr: 0 } }, 'INVALID_PORTFOLIO', 'portfolio.max_positions'],
    ['6 positions over a configured 5', q => { delete q.single; q.mode = 'portfolio'; q.portfolio = { tickers: STOCKS, max_positions: 6, rank_by: 'adx', min_avg_value_20d_idr: 0 } }, 'INVALID_PORTFOLIO', 'portfolio.max_positions', { max_positions: 5 }],
    ['ranking by foreign flow while flow is off', q => { delete q.single; q.mode = 'portfolio'; q.portfolio = { tickers: STOCKS, max_positions: 5, rank_by: 'fnet', min_avg_value_20d_idr: 0 } }, 'FLOW_UNAVAILABLE', 'portfolio.rank_by'],
    ['a flow condition while flow is off', q => { q.entry.conditions.push(flowCard) }, 'FLOW_UNAVAILABLE', 'entry.conditions[3]'],
    ['a flow exit condition while flow is off', q => { q.exit.signals.conditions = [{ ...flowCard, id: 'x1', op: 'lt' }] }, 'FLOW_UNAVAILABLE', 'exit.signals.conditions[0]'],
    ['no enabled entry condition', q => { q.entry.conditions.forEach((c: Condition) => { c.enabled = false }) }, 'NO_ACTIVE_CONDITION', 'entry.conditions'],
    ['an indicator parameter out of range', q => { q.entry.conditions[0].params.di_length = 0 }, 'PARAM_OUT_OF_RANGE', 'entry.conditions[0].params.di_length'],
    ['a parameter the module does not read', q => { q.entry.conditions[0].params.colour = 'red' }, 'PARAM_NOT_ACCEPTED', 'entry.conditions[0].params.colour'],
    ['an output the indicator does not have', q => { q.entry.conditions[0].lhs.output = 'rsi' }, 'UNKNOWN_OUTPUT', 'entry.conditions[0].lhs.output'],
    ['a dip in percent instead of a fraction', q => { q.entry.conditions.push({ id: 'd', kind: 'price_action', type: 'dip', op: 'lte', value: -3 }) }, 'VALUE_OUT_OF_RANGE', 'entry.conditions[3].value'],
    ['an R target without a stop', q => { q.exit.stop.mode = 'none'; q.exit.take_profit.mode = 'r' }, 'INVALID_EXIT', 'exit.take_profit.mode'],
    ['a stop line that is not a price', q => { q.exit.stop.mode = 'line'; q.exit.stop.line = { indicator: 'I13', output: 'rsi' } }, 'INVALID_LINE', 'exit.stop.line.indicator'],
    ['a window of 21 bars', q => { q.entry.window_bars = 21 }, 'INVALID_ENTRY', 'entry.window_bars'],
    ['a duplicate condition id', q => { q.entry.conditions[1].id = q.entry.conditions[0].id }, 'DUPLICATE_CONDITION_ID', 'entry.conditions[1].id'],
  ];
  const before = fake.requests.length;
  for (const [label, f, code, field, limits] of cases) {
    const q = pageDefault('UNVR'); f(q);
    assert.deepEqual(await refusal(runJob(q, { prior_trials: [] }, refs, env({ limits }))), [code, field], label);
    assert.throws(() => checkRequest(q, refs, { limits: { ...LIMITS, ...limits }, flow: OFF }), (e: Error) => e instanceof ValidationError && e.code === code, label);
  }
  assert.equal(fake.requests.length, before, 'a refused request reads no market data');
  // what conditions.ts can only say on the ticker's bars is the run's: an RSI length longer than the history
  const long = pageDefault('ISEA'); (long.entry.conditions[1] as any).params.k_length = 5000;
  assert.doesNotThrow(() => checkRequest(long, refs, { limits: LIMITS, flow: OFF }));
  assert.deepEqual(await refusal(runJob(long, { prior_trials: [] }, refs, env())), ['INDICATOR_OUTPUT_EMPTY', 'entry.conditions[1].lhs']);
});

test('checks against the published data: PERIOD_AFTER_DATA, PERIOD_CLIPPED, no bar in the period, an unpublished stock', async () => {
  const late = pageDefault('UNVR'); late.period.to = '2026-10-26';
  assert.deepEqual(await refusal(runJob(late, { prior_trials: [] }, refs, env())), ['PERIOD_AFTER_DATA', 'period.to']);
  // GOTO's first bar is 2022-04-11: a single run from 2019 starts there (PERIOD_CLIPPED), with either benchmark
  const first = FX.get('GOTO')!.T[0];
  for (const benchmark of ['buy_and_hold', 'ihsg'] as const) {
    const goto = pageDefault('GOTO'); goto.single!.benchmark = benchmark;
    const r = await runJob(goto, { prior_trials: [] }, refs, env());
    assert.deepStrictEqual(noDuration(r), noDuration(await direct(goto, ['GOTO'], [priceFile('IHSG'), priceFile('GOTO')])));
    assert.deepEqual(r.meta.warnings[0], { code: 'PERIOD_CLIPPED', message: `GOTO has no published bar before ${first}: the backtest starts on ${first} instead of the requested 2019-06-03.` });
    assert.deepEqual([r.dates[0], r.benchmark[0]], [first, goto.sizing.capital_idr]);
    // the same run as one requested from the first bar (its request, hashes and warning aside)
    const own = await runJob({ ...clone(goto), period: { ...goto.period, from: first } }, { prior_trials: [] }, refs, env());
    assert.ok(!own.meta.warnings.some(w => w.code === 'PERIOD_CLIPPED'));
    assert.deepStrictEqual([r.dates, r.equity, r.benchmark, r.trades], [own.dates, own.equity, own.benchmark, own.trades]);
  }
  // ISEA has no bar before 2024-07-08: a period that ends before it has nothing to clip to
  const isea = pageDefault('ISEA'); isea.period = { from: '2019-06-03', to: '2023-12-29', oos_fraction: 0 };
  assert.deepEqual(await refusal(runJob(isea, { prior_trials: [] }, refs, env())), ['DATA_MISSING', 'ISEA']);
  // a stock of the reference list without published files: in single mode terminal-api's 404 is DATA_MISSING
  const m = await runJob(pageDefault('NOPX'), { prior_trials: [] }, withNopx(), env()).catch(x => x);
  assert.ok(m instanceof DataError && m.code === 'DATA_MISSING', String(m));
});

test('portfolio: a ticker without published files and a ticker with too short a history are left out (TICKERS_EXCLUDED)', async () => {
  // an entry condition whose window is longer than ISEA's history (and shorter than every other stock's); with ALL of
  // the conditions ISEA's entry can never switch on, so it is left out (with ANY it runs: below)
  const isea = FX.get('ISEA')!.T.length;
  assert.ok(STOCKS.every(t => t === 'ISEA' || FX.get(t)!.T.length > isea + 30));
  const q = portfolioDefault([...STOCKS, 'NOPX']);
  q.entry.conditions.push({ id: 'long', kind: 'indicator', indicator: 'I01', params: { length: isea + 1 }, lhs: { type: 'price' }, op: 'gt', rhs: { type: 'output', output: 'sma' } });
  q.entry.logic = 'all';
  const b0 = fake.requests.length;
  const r = await runJob(q, { prior_trials: [] }, withNopx(), env());
  // NOPX: no /bundle answer (404), nothing downloaded for it; ISEA: loaded, then left out by the engine
  assert.ok(fake.requests.slice(b0).every(x => !x.path.includes('NOPX') || x.path === '/api/terminal/v1/bundle'));
  const nopx = { ticker: 'NOPX', code: 'DATA_MISSING', field: 'NOPX', message: 'The data of NOPX: terminal-api answered 404 (unknown_ticker: No published data for NOPX.).' };
  const ran = STOCKS.filter(t => t !== 'ISEA');
  assert.deepEqual(r.meta.tickers, ran);
  assert.deepEqual(r.tables.per_ticker.map(x => x.ticker), ran);
  const w = r.meta.warnings[0];
  assert.deepEqual([w.code, w.count, w.tickers], ['TICKERS_EXCLUDED', 2, ['ISEA', 'NOPX']]);
  assert.deepEqual(w.reasons!.map(x => [x.ticker, x.code, x.field]), [['ISEA', 'INDICATOR_OUTPUT_EMPTY', 'entry.conditions[3].rhs'], ['NOPX', 'DATA_MISSING', 'NOPX']]);
  assert.deepEqual(w.reasons![1], nopx);
  // the core on the same bars with the loader's exclusion; every file read counts in data_version (ISEA's too)
  assert.deepStrictEqual(noDuration(r), noDuration(await direct(q, STOCKS, [priceFile('IHSG'), ...STOCKS.map(priceFile)], [], [nopx])));
  // picked stocks that are all left out are refused (lead decision 2026-10-26: no cash-only result), with the count and
  // the reasons; NOPX alone, and NOPX with ISEA, which the engine leaves out
  const c = await runJob(portfolioDefault(['NOPX']), { prior_trials: [] }, withNopx(), env()).catch(x => x);
  assert.ok(c instanceof ValidationError && c.code === 'UNIVERSE_EMPTY' && c.field === 'portfolio.tickers', String(c));
  assert.equal(c.message, `The picked stock was left out because its own data cannot serve the strategy (1 DATA_MISSING): no stock is left to trade. NOPX: ${nopx.message}`);
  const e = await runJob({ ...clone(q), portfolio: { ...q.portfolio!, tickers: ['NOPX', 'ISEA'] } }, { prior_trials: [] }, withNopx(), env()).catch(x => x);
  assert.ok(e instanceof ValidationError && e.code === 'UNIVERSE_EMPTY' && e.field === 'portfolio.tickers', String(e));
  assert.match(e.message, /^All 2 picked stocks were left out because their own data cannot serve the strategy \(1 INDICATOR_OUTPUT_EMPTY, 1 DATA_MISSING\): no stock is left to trade\. The first is ISEA: /);
  // single mode still refuses what a portfolio leaves out
  const one = pageDefault('ISEA'); one.entry.conditions.push(q.entry.conditions[3]);
  assert.deepEqual(await refusal(runJob(one, { prior_trials: [] }, refs, env())), ['INDICATOR_OUTPUT_EMPTY', 'entry.conditions[3].rhs']);
  // with ANY, ISEA's entry can switch on without 'long': ISEA runs, 'long' false on every one of its bars (review LA-1:
  // whether a ticker trades never depends on a value that comes later), as the core computes it on the same bars
  const any = { ...clone(q), entry: { ...q.entry, logic: 'any' as const } };
  const ra = await runJob(any, { prior_trials: [] }, withNopx(), env());
  assert.deepEqual(ra.meta.tickers, STOCKS);
  assert.deepEqual(ra.meta.warnings[0].reasons!.map(x => [x.ticker, x.code]), [['NOPX', 'DATA_MISSING']]);
  assert.deepEqual(ra.events.conditions.find(c => c.ticker === 'ISEA' && c.condition_id === 'long')!.track, { on: [], runs: [] });
  assert.deepStrictEqual(noDuration(ra), noDuration(await direct(any, STOCKS, [priceFile('IHSG'), ...STOCKS.map(priceFile)], [], [nopx])));
});

test('limits: LIMIT_EXCEEDED before any file is downloaded; exactly at the limit runs', async () => {
  const q = pageDefault('UNVR');
  const total = encode(PACK.get('IHSG')).body.length + encode(PACK.get('UNVR')).body.length;
  const bucket = () => fake.requests.filter(r => r.path.startsWith('/bucket/')).length;
  const b0 = bucket();
  const e = await runJob(q, { prior_trials: [] }, refs, env({ limits: { max_download_bytes: total - 1 } })).catch(x => x);
  assert.ok(e instanceof WorkerError && e.code === 'LIMIT_EXCEEDED' && e.field === 'single.ticker' && e.status === 422, String(e));
  assert.deepEqual(e.details, { limit: 'max_download_bytes', allowed: total - 1, needed: total });
  assert.equal(bucket(), b0, 'nothing was downloaded');
  assert.equal((await runJob(q, { prior_trials: [] }, refs, env({ limits: { max_download_bytes: total } }))).trades.length > 0, true);
  const p = await runSignals({ schema_version: 1, tickers: STOCKS, period: { from: '2019-06-03', to: THROUGH }, entry: q.entry }, refs, env({ limits: { max_download_bytes: 1000 } })).catch(x => x);
  assert.ok(p instanceof WorkerError && p.code === 'LIMIT_EXCEEDED' && p.field === 'tickers');
});

test('flow on: broker files only when a flow condition needs them, counted against max_broker_rows, FLOW_DATA_THROUGH, brokers', async () => {
  // test rows: broker YU buying UNVR as a foreign investor on its last 30 sessions (not published values)
  const days = FX.get('UNVR')!.T.slice(-30);
  const rows = days.map((d, k) => [d, 'YU', 'Foreign', 'Regular', 1e9 * (k % 3), 5e8, 1e4, 5e3, false]);
  const doc = brokerArchive('UNVR', rows, [2026, 2026]);
  const flowFake = await startFakeTerminal({ key: KEY, tickers: market({ UNVR: { broker: { data_through: THROUGH, doc } }, BBCA: { broker: { data_through: '2026-10-20', doc: brokerArchive('BBCA', [], [2026, 2026]) } } }), refs: REFS });
  try {
    const on: Config['flow'] = { enabled: true, reason: null };
    const q = pageDefault('UNVR', true);                                   // the page default with its two flow cards
    q.period.from = days[0];
    const brokerAsked = () => flowFake.requests.filter(r => r.path === '/api/terminal/v1/bundle').length;
    const r = await runJob(q, { prior_trials: [] }, refs, env({ url: flowFake.url, flow: on }));
    assert.equal(r.events.conditions.filter(c => c.condition_id === 'c4' || c.condition_id === 'c5').length, 2);
    const files = [priceFile('IHSG'), priceFile('UNVR'), { ticker: 'UNVR', dataset: 'broker', sha256: encode(doc).sha256 }];
    assert.equal(r.meta.data_version, await dataVersion(files));
    assert.deepEqual(await refusal(runJob(q, { prior_trials: [] }, refs, env({ url: flowFake.url, flow: on, limits: { max_broker_rows: rows.length - 1 } }))), ['LIMIT_EXCEEDED', 'single.ticker']);
    // without a flow condition no broker file is read
    const plain = pageDefault('UNVR'); plain.period.from = days[0];
    const n = brokerAsked();
    const s = await runJob(plain, { prior_trials: [] }, refs, env({ url: flowFake.url, flow: on }));
    assert.equal(brokerAsked() - n, 2);
    assert.equal(s.meta.data_version, await dataVersion([priceFile('IHSG'), priceFile('UNVR')]));
    // BBCA's manifest says 2026-10-20 (the publisher did not touch it since): the date of the broker data is the
    // newest of every stock's manifest (UNVR: THROUGH), so the period may end on THROUGH; BBCA's broker file has no row
    // on its bars, which a single run refuses (a portfolio leaves BBCA out, below)
    const manifests = () => flowFake.requests.filter(r => r.path.startsWith('/api/terminal/v1/manifest/')).length;
    const m0 = manifests();
    const bbca = pageDefault('BBCA', true); bbca.period.from = days[0];
    assert.deepEqual(await refusal(runJob(bbca, { prior_trials: [] }, refs, env({ url: flowFake.url, flow: on }))), ['FLOW_UNAVAILABLE', 'entry.conditions[3]']);
    // BBCA's date is its /bundle answer's; the other stocks' manifests are asked until one reaches period.to (UNVR, the last)
    assert.equal(manifests() - m0, STOCKS.length - 1, 'every other stock\'s manifest was asked once');
    await runJob(q, { prior_trials: [] }, refs, env({ url: flowFake.url, flow: on }));
    assert.equal(manifests() - m0, STOCKS.length - 1, 'UNVR\'s own manifest reaches period.to: no other manifest is asked');
    // GOTO has no broker file: DATA_MISSING in single mode
    const goto = pageDefault('GOTO', true); goto.period.from = days[0]; goto.single!.benchmark = 'ihsg';
    assert.deepEqual(await refusal(runJob(goto, { prior_trials: [] }, refs, env({ url: flowFake.url, flow: on }))), ['DATA_MISSING', 'GOTO.broker']);
    // a portfolio leaves GOTO out (no broker file, DATA_MISSING, on its manifest); BBCA (no broker row on its bars) runs
    // with its two flow conditions false on every bar, because AT LEAST 3 of the 5 can switch on without them (review
    // LA-1), and is left out with FLOW_UNAVAILABLE when the entry needs 4 of them
    const sector = portfolioDefault(SECTOR_A); sector.entry = q.entry; sector.period.from = days[0];
    const ps = await runJob(sector, { prior_trials: [] }, refs, env({ url: flowFake.url, flow: on }));
    assert.deepEqual(ps.meta.tickers, ['BBCA', 'UNVR']);
    assert.deepEqual(ps.meta.warnings[0].reasons!.map(x => [x.ticker, x.code, x.field]), [['GOTO', 'DATA_MISSING', 'GOTO.broker']]);
    assert.deepEqual(ps.events.conditions.filter(c => c.ticker === 'BBCA' && ['c4', 'c5'].includes(c.condition_id)).map(c => c.track), [{ on: [], runs: [] }, { on: [], runs: [] }]);
    const four = { ...clone(sector), entry: { ...sector.entry, at_least: 4 } };
    const p4 = await runJob(four, { prior_trials: [] }, refs, env({ url: flowFake.url, flow: on }));
    assert.deepEqual(p4.meta.tickers, ['UNVR']);
    assert.deepEqual(p4.meta.warnings[0].reasons!.map(x => [x.ticker, x.code, x.field]), [['BBCA', 'FLOW_UNAVAILABLE', 'entry.conditions[3]'], ['GOTO', 'DATA_MISSING', 'GOTO.broker']]);
    // a broker code is checked against the published broker list (UNKNOWN_BROKER, before any download); a listed
    // broker without any row on UNVR's bars (ZP) has a net of 0 there: its condition runs and never switches on
    const broker = (code: string) => { const b = clone(q); b.entry.conditions.push(legacyToCondition(legacyCard('broker', 'b9', { broker: code, len: 5, val: 0 }))); return b };
    const b0 = flowFake.requests.length;
    assert.deepEqual(await refusal(runJob(broker('XX'), { prior_trials: [] }, refs, env({ url: flowFake.url, flow: on }))), ['UNKNOWN_BROKER', 'entry.conditions[5].params.broker']);
    assert.throws(() => checkRequest(broker('XX'), refs, { limits: LIMITS, flow: on }), (e: Error) => e instanceof ValidationError && e.code === 'UNKNOWN_BROKER');
    assert.equal(flowFake.requests.length, b0, 'a refused broker reads nothing');
    const zp = await runJob(broker('ZP'), { prior_trials: [] }, refs, env({ url: flowFake.url, flow: on }));
    assert.deepEqual(zp.events.conditions.find(c => c.condition_id === 'b9')!.track, { on: [], runs: [] });
    const yu = await runJob(broker('YU'), { prior_trials: [] }, refs, env({ url: flowFake.url, flow: on }));
    assert.ok(yu.events.conditions.find(c => c.condition_id === 'b9')!.track.on.length > 0);
  } finally { await flowFake.close() }
  // no stock's manifest reaches period.to: FLOW_DATA_THROUGH (period.to), refused before any file is downloaded
  const staleRows = days.map(d => [d, 'YU', 'Foreign', 'Regular', 1e9, 5e8, 1e4, 5e3, false]);
  const stale = await startFakeTerminal({ key: KEY, tickers: market({ UNVR: { broker: { data_through: days[25], doc: brokerArchive('UNVR', staleRows, [2026, 2026]) } } }), refs: REFS });
  try {
    const on: Config['flow'] = { enabled: true, reason: null };
    const q = pageDefault('UNVR', true); q.period.from = days[0];
    const e = await runJob(q, { prior_trials: [] }, refs, env({ url: stale.url, flow: on })).catch(x => x);
    assert.ok(e instanceof ValidationError && e.code === 'FLOW_DATA_THROUGH' && e.field === 'period.to', String(e));
    assert.equal(e.message, `The broker data is published through ${days[25]}: a run with flow conditions or ranked by foreign net flow must end on or before it (period.to is ${THROUGH}).`);
    assert.equal(stale.requests.filter(r => r.path.startsWith('/bucket/')).length, 0, 'nothing was downloaded');
    // ranked by foreign net flow: the same rule
    const p = portfolioDefault(SECTOR_A); p.portfolio!.rank_by = 'fnet'; p.period.from = days[0];
    assert.deepEqual(await refusal(runJob(p, { prior_trials: [] }, refs, env({ url: stale.url, flow: on }))), ['FLOW_DATA_THROUGH', 'period.to']);
    // without flow the broker date does not matter; ending on it, the flow run runs
    assert.ok(await runJob(pageDefault('UNVR'), { prior_trials: [] }, refs, env({ url: stale.url, flow: on })));
    q.period.to = days[25];
    assert.equal((await runJob(q, { prior_trials: [] }, refs, env({ url: stale.url, flow: on }))).dates.at(-1), days[25]);
  } finally { await stale.close() }
});

test('events: price-affecting corporate actions reach the trades held across them', async () => {
  const q = pageDefault('UNVR');
  const plain = await runJob(q, { prior_trials: [] }, refs, env());
  const t = plain.trades.find(x => x.exit_date > x.entry_date)!;
  // a test annotation on that trade's exit day (not a published action), and a cash dividend that is not price-affecting
  const ev = (d: string, type: string) => EVENT_COLUMNS.map(c => ({ d, role: 'EX_DATE', family: 'CORPORATE_ACTION', type } as Record<string, unknown>)[c] ?? null);
  const events = eventsDoc('UNVR', [ev(t.exit_date, 'STOCK_SPLIT'), ev(t.exit_date, 'DIVIDEND')]);
  const evFake = await startFakeTerminal({ key: KEY, tickers: market({ UNVR: { events } }), refs: REFS });
  try {
    const r = await runJob(q, { prior_trials: [] }, refs, env({ url: evFake.url }));
    const u = r.trades.find(x => x.trade_id === t.trade_id)!;
    assert.deepEqual(u.flags.corporate_actions, [{ date: t.exit_date, type: 'STOCK_SPLIT' }]);
    assert.equal(r.meta.data_version, await dataVersion([priceFile('IHSG'), priceFile('UNVR'), { ticker: 'UNVR', dataset: 'events', sha256: encode(events).sha256 }]));
    assert.deepEqual(r.equity, plain.equity, 'a flag changes no number');
  } finally { await evFake.close() }
});

/* ---- cancellation and an expired URL ----------------------------------------------------------------------------- */
test('cancellation between and inside phases: Cancelled, and no later phase starts', async () => {
  for (const at of ['loading', 'signals', 'backtest', 'sensitivity', 'monte_carlo', 'finalizing'] as const) {
    let stop = false;
    const seen: string[] = [];
    const q = at === 'signals' || at === 'backtest' ? portfolioDefault() : pageDefault('UNVR');
    const e = await runJob(q, { prior_trials: [] }, refs, env(), {
      progress: p => { seen.push(p.phase); if (p.phase === at) stop = true },
      shouldStop: () => stop,
    }).catch(x => x);
    assert.ok(e instanceof Cancelled, `${at}: ${e}`);
    assert.ok(!seen.slice(seen.indexOf(at)).some(p => PHASES.indexOf(p as JobProgress['phase']) > PHASES.indexOf(at)), `${at}: ${seen.join(',')}`);
  }
  // inside the engine: stopped on the first calendar days, not at the end of the backtest
  let days = 0;
  const e = await runJob(portfolioDefault(), { prior_trials: [] }, refs, env(), { progress: p => { if (p.phase === 'backtest') days = Math.max(days, p.done) }, shouldStop: () => days > 0 || false }).catch(x => x);
  assert.ok(e instanceof Cancelled);
});

test('a presigned URL that expired before its download is fetched again from a new manifest', async () => {
  const q = pageDefault('UNVR'), bundles = () => fake.requests.filter(r => r.path === '/api/terminal/v1/bundle').length;
  const n = bundles();
  fake.fault((r: { path: string }) => r.path === '/bucket/v1/pack/UNVR/price.json.gz', [403]);
  const r = await runJob(q, { prior_trials: [] }, refs, env());
  assert.equal(bundles() - n, 3, 'IHSG and UNVR, then UNVR again');
  assert.deepStrictEqual(noDuration(r), noDuration(await direct(q, ['UNVR'], [priceFile('IHSG'), priceFile('UNVR')])));
});

/* ---- signals preview ------------------------------------------------------------------------------------------------- */
test('signals preview: each picked stock as previewRow on its own bars, data_version of the files read, refusals', async () => {
  const entry = pageDefault('UNVR').entry, period = { from: '2019-06-03', to: THROUGH };
  const p = await runSignals({ schema_version: 1, tickers: STOCKS, period, entry }, refs, env());
  const active = requestConditions({ entry });
  assert.deepEqual(p.rows, STOCKS.map(t => ({ ticker: t, ...previewRow(new Calc(series(t).bars), FX.get(t)!.T, { entry }, period.from, period.to, active) })));
  assert.equal(p.data_version, await dataVersion(STOCKS.map(priceFile)));
  assert.ok(p.rows.some(r => r.entry_signals > 0));
  const s = await runSignals({ schema_version: 1, tickers: ['UNVR', 'BBCA', 'GOTO'], period, entry }, refs, env());
  assert.deepEqual(s.rows.map(r => r.ticker), SECTOR_A, 'ticker order, whatever the order picked');
  const bad: [object, string, string][] = [
    [{ schema_version: 1, tickers: ['BBCA', 'ZZZZ'], period, entry }, 'UNKNOWN_TICKER', 'tickers[1]'],
    [{ schema_version: 1, tickers: [], period, entry }, 'INVALID_PORTFOLIO', 'tickers'],
    [{ schema_version: 1, universe: 'all', tickers: STOCKS, period, entry }, 'UNKNOWN_FIELD', 'universe'],
    [{ schema_version: 1, tickers: STOCKS, period: { from: '2026-01-02', to: '2025-01-02' }, entry }, 'INVALID_PERIOD', 'period.to'],
    [{ schema_version: 1, tickers: STOCKS, period: { ...period, oos_fraction: 0 }, entry }, 'UNKNOWN_FIELD', 'period.oos_fraction'],
    [{ schema_version: 1, tickers: STOCKS, period, entry: { ...entry, conditions: [...entry.conditions, legacyToCondition(legacyCard('top5', 't5'))] } }, 'FLOW_UNAVAILABLE', 'entry.conditions[3]'],
    [{ schema_version: 1, tickers: STOCKS, period, entry, exit: {} }, 'UNKNOWN_FIELD', 'exit'],
  ];
  for (const [req, code, field] of bad) assert.deepEqual(await refusal(runSignals(req, refs, env())), [code, field], JSON.stringify(req).slice(0, 80));
});

test('signals preview: the run\'s exclusions in the run\'s warning, UNIVERSE_EMPTY, FLOW_DATA_THROUGH: it never fails where the run succeeds', async () => {
  // lead decision 2026-10-26: the run's per-ticker exclusion (signals.ts unlessLeftOut, leftOut), reported as the
  // result's TICKERS_EXCLUDED; NOPX has no published file, ISEA's history is shorter than the 'long' condition's window
  // (ALL of the conditions: ISEA's entry can never switch on)
  const isea = FX.get('ISEA')!.T.length;
  const q = portfolioDefault([...STOCKS, 'NOPX']);
  q.entry.conditions.push({ id: 'long', kind: 'indicator', indicator: 'I01', params: { length: isea + 1 }, lhs: { type: 'price' }, op: 'gt', rhs: { type: 'output', output: 'sma' } });
  q.entry.logic = 'all';
  const preview = (tickers: string[], entry = q.entry, period = { from: q.period.from, to: q.period.to }) => ({ schema_version: 1, tickers, period, entry });
  const p = await runSignals(preview([...STOCKS, 'NOPX']), withNopx(), env()), r = await runJob(q, { prior_trials: [] }, withNopx(), env());
  const run = r.meta.warnings.find(w => w.code === 'TICKERS_EXCLUDED')!;
  assert.equal(p.warnings.length, 1);
  const w = p.warnings[0];
  assert.deepEqual(Object.keys(w).sort(), Object.keys(run).sort());
  assert.deepEqual([w.code, w.count, w.tickers, w.reasons], [run.code, run.count, run.tickers, run.reasons]);
  assert.deepEqual(w.tickers, ['ISEA', 'NOPX']);
  assert.equal(w.message, `2 picked stocks were left out of this preview because their own data cannot serve the strategy. The preview counts the signals of the other ${STOCKS.length - 1} stocks.`);
  assert.equal(run.message, `2 picked stocks were left out of this run because their own data cannot serve the strategy. The run trades the other ${STOCKS.length - 1} stocks.`);
  // the rows are the tickers the run ran on, with the run's signal counts
  assert.deepEqual(p.rows.map(x => x.ticker), r.meta.tickers);
  assert.deepEqual(p.rows.map(x => [x.ticker, x.entry_signals, x.last_signal]), r.tables.per_ticker.map(x => [x.ticker, x.entry_signals, x.last_signal]));
  // with ANY, ISEA's entry can switch on without 'long': counted in the preview as it runs in the run (review LA-1)
  const anyEntry = { ...q.entry, logic: 'any' as const };
  const pa = await runSignals(preview([...STOCKS, 'NOPX'], anyEntry), withNopx(), env()), ra = await runJob({ ...clone(q), entry: anyEntry }, { prior_trials: [] }, withNopx(), env());
  assert.deepEqual(pa.rows.map(x => [x.ticker, x.entry_signals, x.last_signal]), ra.tables.per_ticker.map(x => [x.ticker, x.entry_signals, x.last_signal]));
  assert.deepEqual(pa.rows.map(x => x.ticker), STOCKS);
  assert.deepEqual(pa.warnings[0].reasons, ra.meta.warnings.find(x => x.code === 'TICKERS_EXCLUDED')!.reasons);
  assert.deepEqual((await runSignals(preview(STOCKS, pageDefault('UNVR').entry), refs, env())).warnings, [], 'nothing left out: no warning');
  // every stock left out: refused as the run is (UNIVERSE_EMPTY), never an empty preview
  assert.deepEqual(await refusal(runSignals(preview(['NOPX']), withNopx(), env())), ['UNIVERSE_EMPTY', 'tickers']);
  assert.deepEqual(await refusal(runJob(portfolioDefault(['NOPX']), { prior_trials: [] }, withNopx(), env())), ['UNIVERSE_EMPTY', 'portfolio.tickers']);

  // flow: UNVR's broker data is published through days[25] (test rows), no other stock has broker files
  const days = FX.get('UNVR')!.T.slice(-30);
  const rows = days.map(d => [d, 'YU', 'Foreign', 'Regular', 1e9, 5e8, 1e4, 5e3, false]);
  const stale = await startFakeTerminal({ key: KEY, tickers: market({ UNVR: { broker: { data_through: days[25], doc: brokerArchive('UNVR', rows, [2026, 2026]) } } }), refs: REFS });
  try {
    const on: Config['flow'] = { enabled: true, reason: null }, flowEnv = () => env({ url: stale.url, flow: on });
    const entry = pageDefault('UNVR', true).entry, job = portfolioDefault(SECTOR_A);
    job.entry = entry; job.period.from = days[0];
    // period.to after the broker data: FLOW_DATA_THROUGH, the run's code, field and message, before any download
    const e = await runSignals(preview(SECTOR_A, entry, { from: days[0], to: THROUGH }), refs, flowEnv()).catch(x => x);
    const je = await runJob(job, { prior_trials: [] }, refs, flowEnv()).catch(x => x);
    assert.ok(e instanceof ValidationError && e.code === 'FLOW_DATA_THROUGH' && e.field === 'period.to', String(e));
    assert.deepEqual([e.code, e.field, e.message], [je.code, je.field, je.message]);
    assert.equal(stale.requests.filter(x => x.path.startsWith('/bucket/')).length, 0, 'nothing was downloaded');
    // ending on it: BBCA and GOTO (no broker file) left out of both, UNVR counted
    const ok = await runSignals(preview(SECTOR_A, entry, { from: days[0], to: days[25] }), refs, flowEnv());
    const jr = await runJob({ ...job, period: { ...job.period, to: days[25] } }, { prior_trials: [] }, refs, flowEnv());
    assert.deepEqual(ok.rows.map(x => x.ticker), jr.meta.tickers);
    assert.deepEqual(ok.warnings[0].reasons, jr.meta.warnings.find(x => x.code === 'TICKERS_EXCLUDED')!.reasons);
    assert.deepEqual(ok.warnings[0].reasons!.map(x => [x.ticker, x.code, x.field]), [['BBCA', 'DATA_MISSING', 'BBCA.broker'], ['GOTO', 'DATA_MISSING', 'GOTO.broker']]);
  } finally { await stale.close() }
});
