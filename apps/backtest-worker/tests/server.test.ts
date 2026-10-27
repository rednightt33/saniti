/* The worker's private HTTP API (src/server.ts, src/compute.ts, src/catalog.ts, src/config.ts) as edge-bff
   app/backtest.py WorkerClient calls it, on real stored bars: the Terminal parity fixtures (7 stocks and IHSG)
   published by tests/fake-terminal.mjs in the publisher's format. A job runs on the job thread; its gzip result must be
   the result run.ts computes in this process from the same files (meta.duration_ms aside; JSON writes -0 as 0).
   A small proxy in front of the fake terminal-api delays /bundle answers on demand, so a job can be held in its
   loading phase (BUSY, cancel, timeout) without a timer inside the worker, and holds /reference answers until the test
   releases them, so a request can be held while the worker waits for the reference lists (review V1). Sector labels
   and company names of the fake reference list are test labels, not published values. */
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import http from 'node:http';
import net from 'node:net';
import { after, before, test } from 'node:test';
import zlib from 'node:zlib';
import { loadFixtures } from '../../edge-bff/terminal/tests/calc/fixtures.mjs';
import type { BacktestRequest, BacktestResult, Catalog, JobProgress, JobStatus, SignalsPreview } from '../../edge-bff/backtest/src/core/contract.ts';
import { DEFAULT_ENTRY, LEGACY, legacyCard, legacyToCondition } from '../../edge-bff/backtest/src/core/catalog.ts';
import type { LegacyCard } from '../../edge-bff/backtest/src/core/catalog.ts';
import { MAX_PORTFOLIO_TICKERS, MAX_POSITIONS } from '../../edge-bff/backtest/src/core/engine.ts';
import { lineageKey, variantHash } from '../../edge-bff/backtest/src/core/hash.ts';
import { packResult } from '../src/compute.ts';
import { FLOW_OFF_REASON, loadConfig } from '../src/config.ts';
import { PlannedClient } from '../src/load.ts';
import { setLogSink } from '../src/log.ts';
import { runJob, runSignals } from '../src/run.ts';
import { createApp } from '../src/server.ts';
import type { WorkerApp } from '../src/server.ts';
import type { References } from '../src/validate.ts';
import { ENGINE_VERSION, REGISTRY_VERSION, checkRegistry } from '../src/version.ts';
import { brokersRef, pricePack, priceYears, startFakeTerminal, tickersRef } from './fake-terminal.mjs';

const WORKER_DIR = new URL('..', import.meta.url).pathname;
/** the image's command (Dockerfile CMD, exec form): the start-up test runs exactly it, with this test's node */
const IMAGE_CMD: string[] = JSON.parse(fs.readFileSync(new URL('../Dockerfile', import.meta.url), 'utf8').match(/^CMD (\[.*\])$/m)![1]);

/* ---- the published market (as tests/run.test.ts) -------------------------------------------------------------------- */
interface Fixture { ticker: string; T: string[]; O: number[]; H: number[]; L: number[]; C: number[]; V: (number | null)[] }
const FX = new Map((loadFixtures() as Fixture[]).map(f => [f.ticker, f]));
const STOCKS = [...FX.keys()].filter(t => t !== 'IHSG').sort();
const THROUGH = [...FX.values()].map(f => f.T[f.T.length - 1]).sort().pop()!;
const SECTOR: Record<string, string> = { BBCA: 'Sector A', UNVR: 'Sector A', GOTO: 'Sector A' };    // test labels
// test labels of the publisher's industry column; 'Undefined' is the table's value for no classification (PF6)
const INDUSTRY: Record<string, string> = { BBCA: 'Industry A', UNVR: 'Industry A', GOTO: 'Undefined' };
const SECTOR_A = ['BBCA', 'GOTO', 'UNVR'];
// broker manifests (test dates, no file): the publisher wrote its broker data_through into UNVR's manifest last, BBCA's earlier
const BROKER_THROUGH: Record<string, string> = { UNVR: THROUGH, BBCA: '2026-10-20' };
// price: the pack the worker reads and the yearly files the publisher writes next to it (the manifest lists those)
const rowsOf = (f: Fixture) => f.T.map((d, i) => [d, f.O[i], f.H[i], f.L[i], f.C[i], f.V[i]]);
const MARKET = Object.fromEntries([...FX.values()].map(f => [f.ticker, { generated_at: '2026-10-25T18:20:00+00:00', datasets: {
  price: { data_through: THROUGH, first_year: +f.T[0].slice(0, 4), files: [{ pack: 'price', doc: pricePack(f.ticker, rowsOf(f)) }, ...priceYears(f.ticker, rowsOf(f))] },
  ...(f.ticker === 'IHSG' ? {} : { events: { data_through: null, files: [] } }),
  ...(BROKER_THROUGH[f.ticker] ? { broker: { data_through: BROKER_THROUGH[f.ticker], first_year: 2016, files: [] } } : {}),
} }]));
const REFS = {
  // LQ45: a test row of an index without a company name (the reference file holds null there)
  tickers: tickersRef([...[...FX.keys()].sort().map(t => [t, `${t} (test name)`, t === 'IHSG' ? 'index' : 'stock', t === 'IHSG' ? null : SECTOR[t] ?? 'Sector B',
    t === 'IHSG' ? 'Undefined' : INDUSTRY[t] ?? 'Industry B']), ['LQ45', null, 'index', null, null]]),
  brokers: brokersRef([['YU', 'test broker', 'Foreign'], ['ZP', 'test broker 2', 'Local']]),
};

/** The page's boot request (tests/run.test.ts pageDefault: state.ts S through buildRequest, flow cards left out). */
function pageDefault(ticker: string): BacktestRequest {
  const cards = DEFAULT_ENTRY.map(([t, over], k) => legacyCard(t, `c${k + 1}`, over as Partial<LegacyCard>)).filter(c => LEGACY[c.type].group !== 'flow');
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
/** The page's portfolio defaults (tests/run.test.ts portfolioDefault) on picked stocks, every fixture stock unless named. */
function portfolioDefault(tickers: string[] = STOCKS): BacktestRequest {
  const q = pageDefault('BBCA');
  delete q.single;
  return { ...q, mode: 'portfolio', portfolio: { tickers: [...tickers], max_positions: 5, rank_by: 'adx', min_avg_value_20d_idr: 5 * 1e9 } };
}
const noDuration = (r: BacktestResult) => ({ ...r, meta: { ...r.meta, duration_ms: 0 } });
/** As JSON carries a value: -0 written as 0. */
const plusZero = (v: unknown): unknown => typeof v === 'number' ? (v === 0 ? 0 : v) : Array.isArray(v) ? v.map(plusZero)
  : v && typeof v === 'object' ? Object.fromEntries(Object.entries(v).map(([k, x]) => [k, plusZero(x)])) : v;
function finiteOrNull(v: unknown, path = 'result'): void {
  if (typeof v === 'number') assert.ok(Number.isFinite(v), `${path} = ${v}`);
  else if (Array.isArray(v)) v.forEach((x, i) => finiteOrNull(x, `${path}[${i}]`));
  else if (v && typeof v === 'object') for (const [k, x] of Object.entries(v)) finiteOrNull(x, `${path}.${k}`);
  else assert.ok(v === null || typeof v === 'string' || typeof v === 'boolean', `${path} is ${typeof v}`);
}
const PHASES: JobProgress['phase'][] = ['queued', 'loading', 'signals', 'backtest', 'sensitivity', 'monte_carlo', 'finalizing'];

/* ---- the fake terminal-api, a delaying proxy in front of it, the worker ------------------------------------------- */
const WORKER_KEY = 'server-test-worker-key-'.padEnd(48, 'w');
const PROXY_KEY = 'server-test-proxy-key-'.padEnd(48, 'p');
let fake: Awaited<ReturnType<typeof startFakeTerminal>>;
const slow = { bundleMs: 0 };
/** While shut, the proxy keeps every /reference request (in arrival order) until release(). */
const hold = {
  shut: false, held: 0, waiting: [] as (() => void)[],
  release() { this.shut = false; for (const go of this.waiting.splice(0)) go() },
};
let proxy: http.Server, proxyUrl = '';
function startProxy(): Promise<void> {
  proxy = http.createServer((req, res) => {
    const parts: Buffer[] = [];
    req.on('data', c => parts.push(c));
    req.on('end', () => {
      const go = () => {
        const out = http.request(fake.url + req.url, { method: req.method, headers: req.headers }, a => { res.writeHead(a.statusCode!, a.headers); a.pipe(res) });
        out.on('error', () => res.destroy());
        out.end(Buffer.concat(parts));
      };
      if (hold.shut && req.url?.startsWith('/api/terminal/v1/reference/')) { hold.held++; hold.waiting.push(go) }
      else if (req.url === '/api/terminal/v1/bundle' && slow.bundleMs) setTimeout(go, slow.bundleMs); else go();
    });
  });
  return new Promise(ok => proxy.listen(0, '127.0.0.1', () => { proxyUrl = `http://127.0.0.1:${(proxy.address() as net.AddressInfo).port}`; ok() }));
}
const ENV = (over: Record<string, string> = {}): Record<string, string> => ({
  BACKTEST_WORKER_KEY: WORKER_KEY, TERMINAL_URL: proxyUrl, TERMINAL_PROXY_KEY: PROXY_KEY,
  BACKTEST_CACHE_BYTES: '100000000', BACKTEST_DOWNLOAD_CONCURRENCY: '4', BACKTEST_DOWNLOAD_RETRIES: '0', BACKTEST_RETRY_BASE_MS: '0', BACKTEST_HTTP_TIMEOUT_MS: '20000',
  BACKTEST_FILE_ORIGIN: fake.url, BACKTEST_MAX_FILE_BYTES: '100000000',
  BACKTEST_MAX_DOWNLOAD_BYTES: '1000000000', BACKTEST_MAX_BROKER_ROWS: '1000000000', BACKTEST_TIMEOUT_SECONDS: '60',
  BACKTEST_MAX_CONDITIONS: '20', BACKTEST_MAX_RESULT_BYTES: '100000000', ...over,
});

const lines: string[] = [];
let app: WorkerApp, base = '', refs: References;
before(async () => {
  setLogSink(line => lines.push(line));
  fake = await startFakeTerminal({ key: PROXY_KEY, tickers: MARKET, refs: REFS });
  await startProxy();
  app = createApp(loadConfig(ENV()));
  base = `http://127.0.0.1:${await app.listen(0, '127.0.0.1')}`;
  refs = { tickers: (await local().reference('tickers')).tickers, brokers: await local().reference('brokers') };
});
after(async () => { await app.close(); proxy.closeAllConnections(); await new Promise(ok => proxy.close(ok)); await fake.close() });

/** A client in this process, for the result run.ts computes without the HTTP layer. */
const local = () => new PlannedClient({ url: fake.url, proxyKey: PROXY_KEY, cacheBytes: 100_000_000, concurrency: 4, retries: 0, retryBaseMs: 0, timeoutMs: 20_000, fileOrigin: fake.url, maxFileBytes: 100_000_000 });
const directEnv = () => {
  const c = loadConfig(ENV());
  return { client: local(), config: { limits: c.limits, flow: c.flow, terminal: { concurrency: 4 } }, versions: { engine_version: ENGINE_VERSION, registry_version: REGISTRY_VERSION } };
};

interface Answer { status: number; headers: http.IncomingHttpHeaders; body: Buffer; json(): any }
function call(method: string, path: string, body?: unknown, o: { key?: string | null; at?: string; raw?: string; signal?: AbortSignal; agent?: http.Agent } = {}): Promise<Answer> {
  return new Promise((ok, no) => {
    const data = o.raw ?? (body === undefined || method === 'GET' ? undefined : JSON.stringify(body));
    const headers: Record<string, string> = { 'content-type': 'application/json', ...(data === undefined ? {} : { 'content-length': String(Buffer.byteLength(data)) }) };
    if (o.key !== null) headers['x-backtest-worker-key'] = o.key ?? WORKER_KEY;
    const req = http.request((o.at ?? base) + path, { method, headers, signal: o.signal, agent: o.agent }, res => {
      const parts: Buffer[] = [];
      res.on('data', c => parts.push(c));
      res.on('end', () => { const b = Buffer.concat(parts); ok({ status: res.statusCode!, headers: res.headers, body: b, json: () => JSON.parse(b.toString()) }) });
    });
    req.on('error', no);
    req.end(data);
  });
}
const tick = (ms: number) => new Promise(r => setTimeout(r, ms));
let n = 0;
const newId = () => `bt_${(++n).toString(16).padStart(8, '0')}${'0'.repeat(24)}`;
const jobBody = (job_id: string, request: unknown, prior_trials: unknown[] = []) => ({ job_id, request, context: { job_id, prior_trials } });
/** Polls the job until it ends; the distinct phases seen on the way. */
async function until(id: string, at = base, ms = 30_000): Promise<{ status: JobStatus; phases: string[] }> {
  const phases: string[] = [], t0 = Date.now();
  for (;;) {
    const a = await call('GET', `/v1/jobs/${id}`, undefined, { at });
    assert.equal(a.status, 200, a.body.toString());
    const s = a.json() as JobStatus;
    if (s.progress && phases[phases.length - 1] !== s.progress.phase) phases.push(s.progress.phase);
    if (['FINISHED', 'FAILED', 'CANCELLED'].includes(s.state)) return { status: s, phases };
    assert.ok(Date.now() - t0 < ms, `job ${id} still ${s.state} after ${ms} ms`);
    await tick(3);
  }
}
const resultOf = async (id: string, at = base): Promise<BacktestResult> => {
  const a = await call('GET', `/v1/jobs/${id}/result`, undefined, { at });
  assert.equal(a.status, 200, a.body.toString());
  return JSON.parse(zlib.gunzipSync(a.body).toString());
};
const subsequence = (seen: string[], of: string[]) => seen.every((p, k) => of.includes(p) && (k === 0 || of.indexOf(p) > of.indexOf(seen[k - 1])));

/* ---- auth, health, catalog, validate ----------------------------------------------------------------------------- */
test('every route but /health needs x-backtest-worker-key', async () => {
  const h = await call('GET', '/health', undefined, { key: null });
  assert.equal(h.status, 200);
  assert.deepEqual(h.json(), { ok: true, engine_version: ENGINE_VERSION, registry_version: REGISTRY_VERSION });
  const routes: [string, string][] = [['GET', '/v1/catalog'], ['POST', '/v1/validate'], ['POST', '/v1/signals'], ['POST', '/v1/jobs'],
    ['GET', `/v1/jobs/${newId()}`], ['GET', `/v1/jobs/${newId()}/result`], ['POST', `/v1/jobs/${newId()}/cancel`], ['GET', '/v1/nothing']];
  for (const [m, p] of routes) for (const key of [null, '', 'x'.repeat(48), WORKER_KEY.slice(0, -1), WORKER_KEY + 'x']) {
    const a = await call(m, p, {}, { key });
    assert.equal(a.status, 401, `${m} ${p} with ${key === null ? 'no key' : `a key of ${key.length}`}`);
    assert.deepEqual(a.json(), { error: { code: 'UNAUTHORIZED' } });
  }
  // a refused POST leaves its keep-alive connection usable (the answer waits for the end of the body)
  const agent = new http.Agent({ keepAlive: true, maxSockets: 1 });
  try {
    for (let k = 0; k < 3; k++) {
      assert.equal((await call('POST', '/v1/jobs', { job_id: newId(), request: pageDefault('UNVR') }, { key: null, agent })).status, 401);
      assert.equal((await call('POST', '/v1/validate', { request: {} }, { agent })).status, 422);
    }
  } finally { agent.destroy() }
  assert.equal((await call('GET', '/v1/nothing')).status, 404);
  assert.deepEqual((await call('GET', '/v1/nothing')).json().error.code, 'NOT_FOUND');
  assert.equal((await call('GET', '/v1/validate')).json().error.code, 'METHOD_NOT_ALLOWED');
  assert.equal((await call('POST', '/health', undefined, { key: null })).status, 405);
});

test('catalog: the published tickers with their groups, the groupings, the brokers, IHSG\'s first and last bar, limits, flow off with its reason', async () => {
  const a = await call('GET', '/v1/catalog');
  assert.equal(a.status, 200);
  const c = a.json() as Catalog;
  assert.equal(c.schema_version, 1); assert.equal(c.engine_version, ENGINE_VERSION); assert.equal(c.registry_version, REGISTRY_VERSION);
  assert.equal(c.data_through, FX.get('IHSG')!.T.at(-1)); assert.equal(c.first_date, FX.get('IHSG')!.T[0]);
  assert.deepEqual(c.tickers, refs.tickers.map(r => ({ ticker: r.ticker, name: r.name, type: r.type, groups: r.groups })));
  assert.deepEqual(c.tickers.find(t => t.ticker === 'IHSG'), { ticker: 'IHSG', name: 'IHSG (test name)', type: 'index', groups: { sector: null, industry: null } });
  assert.deepEqual(c.tickers.find(t => t.ticker === 'LQ45'), { ticker: 'LQ45', name: null, type: 'index', groups: { sector: null, industry: null } });   // as published
  assert.deepEqual(c.tickers.find(t => t.ticker === 'GOTO')!.groups, { sector: 'Sector A', industry: null });   // 'Undefined': unclassified
  // PF6: the grouping columns of the publisher's reference file, in its order; the stocks only (IHSG and LQ45 are
  // indices, not counted); GOTO's 'Undefined' industry is counted apart, never a value
  assert.deepEqual(c.groupings, [{ key: 'sector', values: [{ value: 'Sector A', tickers: 3 }, { value: 'Sector B', tickers: STOCKS.length - 3 }], unclassified: 0 },
    { key: 'industry', values: [{ value: 'Industry A', tickers: 2 }, { value: 'Industry B', tickers: STOCKS.length - 3 }], unclassified: 1 }]);
  assert.equal('universes' in c, false);
  assert.deepEqual(c.flow, { available: false, reason: FLOW_OFF_REASON, brokers: ['YU', 'ZP'], data_through: null });
  const manifests = () => fake.requests.filter(r => r.path.startsWith('/api/terminal/v1/manifest/')).length, m0 = manifests();
  assert.deepEqual(c.limits, { max_positions: MAX_POSITIONS, window_bars: { min: 1, max: 20 }, monte_carlo_runs: 1000, max_portfolio_tickers: MAX_PORTFOLIO_TICKERS, max_download_bytes: 1e9, max_broker_rows: 1e9, timeout_seconds: 60, queued_per_owner: 3, max_conditions: 20 });
  assert.equal(manifests(), m0, 'flow off: no manifest is asked');
  // flow on: available, no reason, and the newest broker data_through of every stock's manifest
  const on = createApp(loadConfig(ENV({ BACKTEST_FLOW_ENABLED: '1' })));
  try {
    const at = `http://127.0.0.1:${await on.listen(0, '127.0.0.1')}`;
    assert.deepEqual((await call('GET', '/v1/catalog', undefined, { at })).json().flow, { available: true, reason: null, brokers: ['YU', 'ZP'], data_through: THROUGH });
    assert.equal(manifests() - m0, STOCKS.length, 'one manifest per stock (no index)');
    // the broker list of terminal-api reaches the validation: an unlisted code is UNKNOWN_BROKER, a listed one passes
    const q = pageDefault('UNVR'), withBroker = (code: string) => ({ ...q, entry: { ...q.entry, conditions: [...q.entry.conditions, legacyToCondition(legacyCard('broker', 'b1', { broker: code, len: 5, val: 0 }))] } });
    const x = await call('POST', '/v1/validate', { request: withBroker('XX') }, { at });
    assert.equal(x.status, 422); assert.deepEqual([x.json().error.code, x.json().error.field], ['UNKNOWN_BROKER', 'entry.conditions[3].params.broker']);
    assert.equal((await call('POST', '/v1/validate', { request: withBroker('ZP') }, { at })).status, 200);
    const j = await call('POST', '/v1/jobs', jobBody(newId(), withBroker('XX')), { at });
    assert.equal(j.status, 422); assert.equal(j.json().error.code, 'UNKNOWN_BROKER');
  } finally { await on.close() }
});

test('validate: the hashes and tickers of a valid request, the field of a refused one, nothing started', async () => {
  const q = pageDefault('UNVR');
  const a = await call('POST', '/v1/validate', { request: q });
  assert.equal(a.status, 200, a.body.toString());
  assert.deepEqual(a.json(), { ok: true, lineage_key: await lineageKey(q), variant_hash: await variantHash(q), tickers: ['UNVR'] });
  // three picked stocks, in any order (PF3): the same answer, the hashes of the sorted request
  const picked = await call('POST', '/v1/validate', { request: portfolioDefault(SECTOR_A) });
  assert.deepEqual(picked.json(), { ok: true, lineage_key: await lineageKey(portfolioDefault(SECTOR_A)), variant_hash: await variantHash(portfolioDefault(SECTOR_A)), tickers: SECTOR_A });
  assert.deepEqual((await call('POST', '/v1/validate', { request: portfolioDefault(['UNVR', 'BBCA', 'GOTO']) })).json(), picked.json());
  const refused: [unknown, string, string][] = [
    [{ request: { ...q, single: { ticker: 'IHSG', benchmark: 'buy_and_hold' } } }, 'UNKNOWN_TICKER', 'single.ticker'],
    [{ request: portfolioDefault(['BBCA', 'IHSG']) }, 'UNKNOWN_TICKER', 'portfolio.tickers[1]'],
    [{ request: portfolioDefault(Array.from({ length: MAX_PORTFOLIO_TICKERS + 1 }, (_, k) => `S${k}`)) }, 'INVALID_PORTFOLIO', 'portfolio.tickers'],
    [{ request: { ...q, extra: 1 } }, 'UNKNOWN_FIELD', 'extra'],
    [{ request: { ...q, client_request_id: 'c'.repeat(32) } }, 'UNKNOWN_FIELD', 'client_request_id'],   // edge-bff strips it
    [{ request: { ...q, period: { ...q.period, from: '2019-02-30' } } }, 'INVALID_PERIOD', 'period.from'],
    [{ request: { ...q, entry: { ...q.entry, conditions: [...q.entry.conditions, legacyToCondition(legacyCard('fnet', 'f1', { len: 5, val: 0 }))] } } }, 'FLOW_UNAVAILABLE', 'entry.conditions[3]'],
    [{ request: q, more: 1 }, 'INVALID_REQUEST', 'body'],
    [[q], 'INVALID_REQUEST', 'body'],
    [{}, 'INVALID_REQUEST', 'request'],
  ];
  for (const [body, code, field] of refused) {
    const r = await call('POST', '/v1/validate', body);
    assert.equal(r.status, 422, `${code}: ${r.body}`);
    assert.equal(r.json().error.code, code); assert.equal(r.json().error.field, field);
    assert.equal(typeof r.json().error.message, 'string');
  }
  const bad = await call('POST', '/v1/validate', undefined, { raw: '{"request":' });
  assert.equal(bad.status, 422); assert.equal(bad.json().error.code, 'INVALID_JSON');
  // the published data (lead decision 2026-10-26): PERIOD_AFTER_DATA with the job's code, field and message, on IHSG's
  // manifest alone: no /bundle (terminal-api counts every file it grants in the quota and writes an audit row), no file
  // but the reference lists
  for (const to of ['2026-10-26', '2026-10-24']) {                     // the day after IHSG's last bar (a Saturday) is after it too
    const late = { ...q, period: { ...q.period, to } }, r0 = fake.requests.length;
    const after = await call('POST', '/v1/validate', { request: late });
    const seen = fake.requests.slice(r0).map(x => x.path);
    assert.equal(after.status, 422, after.body.toString());
    assert.deepEqual(seen.filter(x => x.startsWith('/api/terminal/v1/')).sort(), ['/api/terminal/v1/manifest/IHSG', '/api/terminal/v1/reference/brokers', '/api/terminal/v1/reference/tickers']);
    assert.deepEqual(seen.filter(x => x.startsWith('/bucket/v1/')).sort(), ['/bucket/v1/ref/brokers.json.gz', '/bucket/v1/ref/tickers.json.gz']);
    const job = await runJob(late, { prior_trials: [] }, refs, directEnv()).catch(e => e);
    assert.deepEqual([after.json().error.code, after.json().error.field, after.json().error.message], ['PERIOD_AFTER_DATA', 'period.to', job.message]);
    assert.equal(job.message, `period.to is after the latest published bar (${FX.get('IHSG')!.T.at(-1)}).`);
  }
  assert.equal((await call('POST', '/v1/validate', { request: { ...q, period: { ...q.period, to: THROUGH } } })).status, 200, 'period.to on the last bar');
});

test('validate with flow on: FLOW_DATA_THROUGH on the stocks\' manifests (the catalog\'s date) before PERIOD_AFTER_DATA, as the job', async () => {
  const t = createApp(loadConfig(ENV({ BACKTEST_FLOW_ENABLED: '1' })));
  try {
    const at = `http://127.0.0.1:${await t.listen(0, '127.0.0.1')}`, q = pageDefault('UNVR');
    const flow = { ...q, entry: { ...q.entry, conditions: [...q.entry.conditions, legacyToCondition(legacyCard('fnet', 'f1', { len: 5, val: 0 }))] } };
    const asked = async (request: unknown) => {
      const r0 = fake.requests.length, a = await call('POST', '/v1/validate', { request }, { at }), seen = fake.requests.slice(r0).map(x => x.path);
      assert.ok(!seen.includes('/api/terminal/v1/bundle') && seen.every(x => !x.startsWith('/bucket/v1/') || x.startsWith('/bucket/v1/ref/')), seen.join(' '));
      return { a, manifests: seen.filter(x => x.startsWith('/api/terminal/v1/manifest/')).map(x => x.slice('/api/terminal/v1/manifest/'.length)) };
    };
    // UNVR's manifest says THROUGH, BBCA's 2026-10-20: the broker data is published through THROUGH. UNVR's own
    // manifest reaches period.to, so no other stock's is asked; then IHSG's for PERIOD_AFTER_DATA
    const ok = await asked(flow);
    assert.equal(ok.a.status, 200, ok.a.body.toString());
    assert.deepEqual(ok.manifests, ['UNVR', 'IHSG']);
    // three picked stocks: their manifests first (UNVR among them)
    const sector = await asked({ ...portfolioDefault(SECTOR_A), entry: flow.entry });
    assert.equal(sector.a.status, 200, sector.a.body.toString());
    assert.deepEqual(sector.manifests.sort(), ['BBCA', 'GOTO', 'IHSG', 'UNVR']);
    // after the broker date: every stock's manifest is asked (none reaches period.to), and the date named is the catalog's
    const late = await asked({ ...flow, period: { ...flow.period, to: '2026-10-26' } });
    assert.equal(late.a.status, 422, late.a.body.toString());
    assert.deepEqual(late.manifests.sort(), STOCKS);
    assert.deepEqual([late.a.json().error.code, late.a.json().error.field, late.a.json().error.message], ['FLOW_DATA_THROUGH', 'period.to',
      `The broker data is published through ${THROUGH}: a run with flow conditions or ranked by foreign net flow must end on or before it (period.to is 2026-10-26).`]);
    assert.equal((await call('GET', '/v1/catalog', undefined, { at })).json().flow.data_through, THROUGH);
    // without a flow condition the broker date is not asked: PERIOD_AFTER_DATA on IHSG's manifest
    const plain = await asked({ ...q, period: { ...q.period, to: '2026-10-26' } });
    assert.deepEqual([plain.a.json().error.code, plain.manifests], ['PERIOD_AFTER_DATA', ['IHSG']]);
  } finally { await t.close() }
});

/* ---- jobs ---------------------------------------------------------------------------------------------------------- */
test('a single-stock job with the page default settings: 202, phases in order, the gzip result until the next job, then 410', async () => {
  const q = pageDefault('UNVR'), id = newId(), prior = [{ variant_hash: 'c'.repeat(64), sharpe_daily: 0.02 }];
  const t0 = performance.now();
  const p = await call('POST', '/v1/jobs', jobBody(id, q, prior));
  assert.equal(p.status, 202); assert.deepEqual(p.json(), { job_id: id });
  const { status, phases } = await until(id);
  const ms = performance.now() - t0;
  assert.equal(status.state, 'FINISHED', JSON.stringify(status.error));
  assert.ok(subsequence(phases, PHASES), phases.join(','));
  assert.deepEqual(status.progress, { phase: 'finalizing', done: 1, total: 1 });
  assert.equal(status.request_id, id); assert.equal(status.error, null);
  assert.ok(status.created_at <= status.started_at! && status.started_at! <= status.finished_at!);
  assert.ok(Number.isInteger(status.duration_ms) && status.duration_ms! >= 0 && status.duration_ms! <= ms + 5);

  const a = await call('GET', `/v1/jobs/${id}/result`);
  assert.equal(a.status, 200);
  assert.equal(a.headers['content-encoding'], 'gzip'); assert.equal(a.headers['content-type'], 'application/json');
  assert.equal(+a.headers['content-length']!, a.body.length); assert.equal(status.result_bytes, a.body.length);
  const r = JSON.parse(zlib.gunzipSync(a.body).toString()) as BacktestResult;
  const direct = await runJob(q, { prior_trials: prior }, refs, directEnv());
  assert.deepStrictEqual(noDuration(r), plusZero(noDuration(direct)));
  assert.ok(r.meta.duration_ms > 0 && r.meta.duration_ms <= status.duration_ms!);
  assert.equal(r.meta.trials.prior, 1); assert.equal(r.robustness.monte_carlo!.runs, 1000);
  finiteOrNull(r);
  observed.single = { job_ms: status.duration_ms!, compute_ms: r.meta.duration_ms, json_bytes: zlib.gunzipSync(a.body).length, gzip_bytes: a.body.length, trades: r.trades.length };

  // asked again (a caller that lost the answer): the same bytes, until the next job starts (lead decision 2026-10-26)
  for (let k = 0; k < 2; k++) {
    const again = await call('GET', `/v1/jobs/${id}/result`);
    assert.equal(again.status, 200); assert.deepEqual(again.body, a.body);
  }
  assert.equal((await call('GET', `/v1/jobs/${id}`)).json().state, 'FINISHED');     // the status stays
  // the same id again: 202 (edge-bff retries a POST whose answer it lost), nothing new starts
  assert.equal((await call('POST', '/v1/jobs', jobBody(id, q))).status, 202);
  assert.equal((await call('GET', `/v1/jobs/${id}`)).json().state, 'FINISHED');
  assert.equal((await call('GET', `/v1/jobs/${id}/result`)).status, 200);
  // a newer job: the replaced job's result is gone (410), its status unknown; one job further back, both unknown
  const next = newId();
  assert.equal((await call('POST', '/v1/jobs', jobBody(next, pageDefault('BBCA')))).status, 202);
  const gone = await call('GET', `/v1/jobs/${id}/result`);
  assert.equal(gone.status, 410); assert.equal(gone.json().error.code, 'RESULT_GONE');
  assert.deepEqual((await call('GET', `/v1/jobs/${id}`)).json(), { error: { code: 'UNKNOWN_JOB' } });
  assert.equal((await until(next)).status.state, 'FINISHED');
  const third = newId();
  assert.equal((await call('POST', '/v1/jobs', jobBody(third, pageDefault('BBCA')))).status, 202);
  assert.equal((await call('GET', `/v1/jobs/${id}/result`)).status, 404);
  assert.equal((await call('GET', `/v1/jobs/${next}/result`)).status, 410);
  assert.equal((await until(third)).status.state, 'FINISHED');
});

test('the same request on the same data gives the same result through the API (meta.duration_ms aside)', async () => {
  const q = pageDefault('UNVR'), out: BacktestResult[] = [];
  for (let k = 0; k < 2; k++) {
    const id = newId();
    assert.equal((await call('POST', '/v1/jobs', jobBody(id, q))).status, 202);
    assert.equal((await until(id)).status.state, 'FINISHED');
    out.push(await resultOf(id));
  }
  assert.deepStrictEqual(noDuration(out[1]), noDuration(out[0]));
});

test('a portfolio job on the fixture tickers through the API', async () => {
  const q = portfolioDefault(), id = newId();
  assert.equal((await call('POST', '/v1/jobs', jobBody(id, q))).status, 202);
  const { status, phases } = await until(id);
  assert.equal(status.state, 'FINISHED', JSON.stringify(status.error));
  assert.ok(subsequence(phases, PHASES), phases.join(','));
  const r = await resultOf(id);
  assert.deepEqual(r.meta.tickers, STOCKS); assert.deepEqual(r.meta.benchmark, { kind: 'ihsg', ticker: 'IHSG' });
  assert.deepStrictEqual(noDuration(r), plusZero(noDuration(await runJob(q, { prior_trials: [] }, refs, directEnv()))));
  finiteOrNull(r);
  observed.portfolio = { job_ms: status.duration_ms!, compute_ms: r.meta.duration_ms, tickers: r.meta.tickers.length, trades: r.trades.length, gzip_bytes: status.result_bytes! };
});

test('one job at a time: BUSY for another id while one runs, 202 for its own id, UNKNOWN_JOB, NOT_FINISHED', async () => {
  slow.bundleMs = 400;
  try {
    const id = newId(), other = newId();
    assert.equal((await call('POST', '/v1/jobs', jobBody(id, pageDefault('UNVR')))).status, 202);
    const busy = await call('POST', '/v1/jobs', jobBody(other, pageDefault('BBCA')));
    assert.equal(busy.status, 409); assert.equal(busy.json().error.code, 'BUSY');
    assert.equal((await call('POST', '/v1/jobs', jobBody(id, pageDefault('UNVR')))).status, 202);
    const s = (await call('GET', `/v1/jobs/${id}`)).json() as JobStatus;
    assert.equal(s.state, 'RUNNING'); assert.ok(['queued', 'loading'].includes(s.progress!.phase));
    const nf = await call('GET', `/v1/jobs/${id}/result`);
    assert.equal(nf.status, 409); assert.equal(nf.json().error.code, 'NOT_FINISHED');
    for (const p of [`/v1/jobs/${other}`, `/v1/jobs/${other}/result`]) {
      const u = await call('GET', p);
      assert.equal(u.status, 404); assert.deepEqual(u.json(), { error: { code: 'UNKNOWN_JOB' } });
    }
    assert.equal((await call('POST', `/v1/jobs/${other}/cancel`)).status, 404);
    assert.equal((await until(id)).status.state, 'FINISHED');
    // once it ended, the next job starts and the previous one is gone
    slow.bundleMs = 0;
    assert.equal((await call('POST', '/v1/jobs', jobBody(other, pageDefault('BBCA')))).status, 202);
    assert.equal((await call('GET', `/v1/jobs/${id}`)).status, 404);
    assert.equal((await until(other)).status.state, 'FINISHED');
  } finally { slow.bundleMs = 0 }
});

test('cancel: 202, the job ends CANCELLED without an error or a result; a cancel after the end changes nothing', async () => {
  slow.bundleMs = 300;
  try {
    const id = newId();
    assert.equal((await call('POST', '/v1/jobs', jobBody(id, pageDefault('UNVR')))).status, 202);
    const c = await call('POST', `/v1/jobs/${id}/cancel`);
    assert.equal(c.status, 202); assert.equal((c.json() as JobStatus).request_id, id);
    const { status } = await until(id);
    assert.equal(status.state, 'CANCELLED'); assert.equal(status.error, null); assert.equal(status.result_bytes, null);
    assert.equal((await call('GET', `/v1/jobs/${id}/result`)).json().error.code, 'NOT_FINISHED');
    assert.equal((await call('POST', `/v1/jobs/${id}/cancel`)).status, 202);
    assert.equal((await call('GET', `/v1/jobs/${id}`)).json().state, 'CANCELLED');
  } finally { slow.bundleMs = 0 }
  const done = newId();
  assert.equal((await call('POST', '/v1/jobs', jobBody(done, pageDefault('BBCA')))).status, 202);
  assert.equal((await until(done)).status.state, 'FINISHED');
  assert.equal((await call('POST', `/v1/jobs/${done}/cancel`)).status, 202);
  assert.equal((await call('GET', `/v1/jobs/${done}`)).json().state, 'FINISHED');
  assert.equal((await call('GET', `/v1/jobs/${done}/result`)).status, 200);
});

test('job bodies: the job id, the context and its prior trials are checked; a refused request never becomes a job', async () => {
  const q = pageDefault('UNVR'), id = newId();
  const cases: [unknown, string, string][] = [
    [{ ...jobBody(id, q), job_id: 'bt_123' }, 'INVALID_JOB_ID', 'job_id'],
    [{ ...jobBody(id, q), job_id: `bt_${'A'.repeat(32)}` }, 'INVALID_JOB_ID', 'job_id'],
    [{ job_id: id, request: q }, 'INVALID_CONTEXT', 'context'],
    [{ job_id: id, request: q, context: { job_id: newId(), prior_trials: [] } }, 'INVALID_CONTEXT', 'context.job_id'],
    [{ job_id: id, request: q, context: { job_id: id } }, 'INVALID_CONTEXT', 'context.prior_trials'],
    [{ job_id: id, request: q, context: { job_id: id, prior_trials: [], owner: 'x' } }, 'UNKNOWN_FIELD', 'context.owner'],
    [jobBody(id, q, [{ variant_hash: 'x', sharpe_daily: 0 }]), 'INVALID_CONTEXT', 'context.prior_trials[0].variant_hash'],
    [jobBody(id, q, [{ variant_hash: 'a'.repeat(64), sharpe_daily: null }]), 'INVALID_CONTEXT', 'context.prior_trials[0].sharpe_daily'],
    [jobBody(id, q, [{ variant_hash: 'a'.repeat(64), sharpe_daily: 0, kind: 'run' }]), 'INVALID_CONTEXT', 'context.prior_trials[0]'],
    [{ ...jobBody(id, q), priority: 1 }, 'UNKNOWN_FIELD', 'priority'],
    [jobBody(id, { ...q, robustness: { ...q.robustness, monte_carlo_runs: 10 } }), 'INVALID_ROBUSTNESS', 'robustness.monte_carlo_runs'],
    [jobBody(id, portfolioDefault(['BBCA', 'NOPE'])), 'UNKNOWN_TICKER', 'portfolio.tickers[1]'],
    [jobBody(id, { ...portfolioDefault(), portfolio: { ...portfolioDefault().portfolio!, universe: 'all' } }), 'UNKNOWN_FIELD', 'portfolio.universe'],
  ];
  for (const [body, code, field] of cases) {
    const a = await call('POST', '/v1/jobs', body);
    assert.equal(a.status, 422, `${code}: ${a.body}`);
    assert.equal(a.json().error.code, code); assert.equal(a.json().error.field, field);
  }
  assert.equal((await call('GET', `/v1/jobs/${id}`)).status, 404, 'no job was made');
});

test('a field the chosen mode does not read is checked before the hand-over: a 4000-deep object is 422, never a 500 (review VAL-1)', async () => {
  // exit.stop.line under stop mode pct, its params 4000 objects deep (25 KB, under edge-bff's 128 KiB body limit): it
  // passed /v1/validate, then failed POST /v1/jobs with 500 INTERNAL_ERROR (RangeError in Worker.postMessage), which
  // edge-bff retries and ends WORKER_LOST
  const depth = 4000, id = newId(), errors0 = lines.filter(l => /"level":"error"/.test(l)).length;
  const text = JSON.stringify(pageDefault('UNVR')).replace('"line":{"indicator":"I09","output":"supertrend"}',
    `"line":{"indicator":"I09","output":"supertrend","params":${'{"a":'.repeat(depth)}1${'}'.repeat(depth)}}`);
  assert.ok(text.length > 25_000 && text.length < 128 * 1024, String(text.length));
  for (const [path, raw] of [['/v1/validate', `{"request":${text}}`], ['/v1/jobs', `{"job_id":"${id}","request":${text},"context":{"job_id":"${id}","prior_trials":[]}}`]]) {
    const a = await call('POST', path, undefined, { raw });
    assert.equal(a.status, 422, `${path}: ${a.body.toString().slice(0, 200)}`);
    assert.deepEqual([a.json().error.code, a.json().error.field], ['PARAM_NOT_ACCEPTED', 'exit.stop.line.params.a'], path);
  }
  assert.equal((await call('GET', `/v1/jobs/${id}`)).status, 404, 'no job was made');
  assert.equal(lines.filter(l => /"level":"error"/.test(l)).length, errors0, 'no error was logged');
});

test('a data error after the hand-over ends the job FAILED with the error the core gave', async () => {
  const q = pageDefault('ISEA'), id = newId();
  q.period = { from: '2019-06-03', to: '2023-12-29', oos_fraction: 0 };     // ISEA has no bar before 2024-07-08
  assert.equal((await call('POST', '/v1/jobs', jobBody(id, q))).status, 202);
  const { status } = await until(id);
  assert.equal(status.state, 'FAILED');
  assert.equal(status.error!.code, 'DATA_MISSING'); assert.equal(status.error!.field, 'ISEA');
  assert.equal((await call('GET', `/v1/jobs/${id}/result`)).json().error.code, 'NOT_FINISHED');
  const late = pageDefault('UNVR'), id2 = newId(); late.period.to = '2026-10-26';
  assert.equal((await call('POST', '/v1/jobs', jobBody(id2, late))).status, 202);
  const s2 = (await until(id2)).status;
  assert.equal(s2.state, 'FAILED'); assert.deepEqual([s2.error!.code, s2.error!.field], ['PERIOD_AFTER_DATA', 'period.to']);
  assert.equal((await call('GET', `/v1/jobs/${id}/result`)).status, 404, 'a replaced job without a result is unknown, not gone');
});

test('a result over BACKTEST_MAX_RESULT_BYTES of JSON ends the job FAILED LIMIT_EXCEEDED with its sizes; one at the limit is kept', async () => {
  const r = await runJob(pageDefault('UNVR'), { prior_trials: [] }, refs, directEnv()), bytes = Buffer.byteLength(JSON.stringify(r));
  const packed = packResult(r, bytes);
  assert.deepEqual([packed.json_bytes, JSON.parse(zlib.gunzipSync(packed.gzip).toString()).meta.request_hash], [bytes, r.meta.request_hash]);
  const e = (() => { try { packResult(r, bytes - 1) } catch (x) { return x as { status: number; code: string; details: unknown } } assert.fail('not refused') })();
  assert.deepEqual([e.status, e.code, e.details], [422, 'LIMIT_EXCEEDED', { limit: 'max_result_bytes', allowed: bytes - 1, needed: bytes }]);
  // the job's own result differs from r only in meta.duration_ms, whose digits are its own (review V3): the limit is
  // the size with a 1-digit duration less a byte, which any duration exceeds; the job's size is that size with its
  // duration's digits, 1 to 5 (BACKTEST_TIMEOUT_SECONDS is 60 here, so at most 60000 ms)
  const least = Buffer.byteLength(JSON.stringify(noDuration(r))), maxDigits = String(60 * 1000).length;
  const t = createApp(loadConfig(ENV({ BACKTEST_MAX_RESULT_BYTES: String(least - 1) })));
  try {
    const at = `http://127.0.0.1:${await t.listen(0, '127.0.0.1')}`, id = newId();
    assert.equal((await call('POST', '/v1/jobs', jobBody(id, pageDefault('UNVR')), { at })).status, 202);
    const { status } = await until(id, at);
    assert.equal(status.state, 'FAILED');
    const d = status.error!.details as { limit: string; allowed: number; needed: number };
    assert.deepEqual([status.error!.code, d.limit, d.allowed], ['LIMIT_EXCEEDED', 'max_result_bytes', least - 1]);
    const digits = d.needed - (least - 1);
    assert.ok(Number.isInteger(digits) && digits >= 1 && digits <= maxDigits, `needed ${d.needed}: ${digits} duration digits`);
    assert.equal((await call('GET', `/v1/jobs/${id}/result`, undefined, { at })).json().error.code, 'NOT_FINISHED');
  } finally { await t.close() }
});

test('a job over BACKTEST_TIMEOUT_SECONDS ends FAILED TIMEOUT, its thread is stopped, and the next job runs', async () => {
  const t = createApp(loadConfig(ENV({ BACKTEST_TIMEOUT_SECONDS: '1' })));
  try {
    const at = `http://127.0.0.1:${await t.listen(0, '127.0.0.1')}`;
    slow.bundleMs = 1500;
    const id = newId(), t0 = performance.now();
    assert.equal((await call('POST', '/v1/jobs', jobBody(id, pageDefault('UNVR')), { at })).status, 202);
    const { status } = await until(id, at);
    assert.equal(status.state, 'FAILED'); assert.equal(status.error!.code, 'TIMEOUT');
    assert.ok(performance.now() - t0 < 1450, 'ended at the deadline, not when the download came back');
    assert.equal(t.threads.jobs.busy, false);
    // a preview over the time: 504 TIMEOUT
    const p = await call('POST', '/v1/signals', { schema_version: 1, tickers: STOCKS, period: { from: '2019-06-03', to: THROUGH }, entry: pageDefault('UNVR').entry }, { at });
    assert.equal(p.status, 504); assert.equal(p.json().error.code, 'TIMEOUT');
    slow.bundleMs = 0;
    const next = newId();
    assert.equal((await call('POST', '/v1/jobs', jobBody(next, pageDefault('BBCA')), { at })).status, 202);
    assert.equal((await until(next, at)).status.state, 'FINISHED');
  } finally { slow.bundleMs = 0; await t.close() }
});

/* ---- signals preview ------------------------------------------------------------------------------------------------ */
test('signals preview: the rows run.ts computes, its refusals, and a preview the caller abandoned does not block the next', async () => {
  const body = { schema_version: 1, tickers: STOCKS, period: { from: '2019-06-03', to: THROUGH }, entry: pageDefault('UNVR').entry };
  const t0 = performance.now();
  const a = await call('POST', '/v1/signals', body);
  observed.preview_ms = Math.round(performance.now() - t0);
  assert.equal(a.status, 200, a.body.toString());
  const p = a.json() as SignalsPreview;
  assert.deepEqual(p, await runSignals(body, refs, directEnv()));
  assert.deepEqual(p.rows.map(r => r.ticker), STOCKS);
  const bad = await call('POST', '/v1/signals', { ...body, tickers: ['BBCA', 'NOPE'] });
  assert.equal(bad.status, 422); assert.deepEqual([bad.json().error.code, bad.json().error.field], ['UNKNOWN_TICKER', 'tickers[1]']);
  // previews run while a job runs (their own thread)
  slow.bundleMs = 300;
  const id = newId();
  try {
    assert.equal((await call('POST', '/v1/jobs', jobBody(id, pageDefault('UNVR')))).status, 202);
    const ac = new AbortController();
    const gone = call('POST', '/v1/signals', body, { signal: ac.signal }).catch(e => e);
    await tick(100); ac.abort();
    assert.equal((await gone).name, 'AbortError');
    slow.bundleMs = 0;
    const b = await call('POST', '/v1/signals', body);
    assert.equal(b.status, 200); assert.deepEqual(b.json(), p);
  } finally { slow.bundleMs = 0 }
  assert.equal((await until(id)).status.state, 'FINISHED');
});

test('a caller that leaves while the worker waits for the reference lists queues nothing: no preview, no job (review V1)', async () => {
  // before 2026-10-27 the caller-gone watch was added after that wait, and a 'close' that came during it was never seen:
  // the abandoned preview ran for nobody and the next preview waited behind it; an abandoned job started
  const t = createApp(loadConfig(ENV()));
  const previews: string[][] = [], jobs: string[] = [];
  const runPreview = t.threads.previews.run.bind(t.threads.previews), runJobTask = t.threads.jobs.run.bind(t.threads.jobs);
  t.threads.previews.run = (task, p) => { previews.push((task.request as { tickers: string[] }).tickers); return runPreview(task, p) };
  t.threads.jobs.run = (task, p) => { jobs.push((task.request as BacktestRequest).single!.ticker); return runJobTask(task, p) };
  const preview = (tickers: string[]) => ({ schema_version: 1, tickers, period: { from: '2019-06-03', to: THROUGH }, entry: pageDefault('UNVR').entry });
  /** Sends a request held at the reference lists, leaves when both are held, then lets them through. */
  const leave = async (path: string, body: unknown, at: string) => {
    hold.shut = true;
    const held = hold.held, ac = new AbortController();
    const gone = call('POST', path, body, { at, signal: ac.signal }).catch(e => e);
    for (const t0 = Date.now(); hold.held < held + 2; await tick(2)) assert.ok(Date.now() - t0 < 10_000, 'the reference lists were never asked');
    ac.abort();
    assert.equal((await gone).name, 'AbortError');
    hold.release();
  };
  try {
    const at = `http://127.0.0.1:${await t.listen(0, '127.0.0.1')}`, b0 = fake.requests.length;
    await leave('/v1/signals', preview(['BBCA']), at);
    const next = await call('POST', '/v1/signals', preview(['UNVR']), { at });
    assert.equal(next.status, 200, next.body.toString());
    assert.deepEqual(next.json(), await runSignals(preview(['UNVR']), refs, directEnv()));
    const after = await call('POST', '/v1/signals', preview(['GOTO']), { at });
    assert.equal(after.status, 200, after.body.toString());
    assert.deepEqual(previews, [['UNVR'], ['GOTO']], 'the abandoned preview never reached the preview thread, so the next one waited for nothing');
    // and it loaded no data: the bundles asked since are the two previews' own (a fresh thread: nothing is cached)
    const bundled = fake.requests.slice(b0).filter(x => x.path === '/api/terminal/v1/bundle').map(x => JSON.parse(x.body).ticker);
    assert.deepEqual([...new Set(bundled)].sort(), ['GOTO', 'UNVR']);
    // a job: the abandoned POST /v1/jobs never starts (edge-bff finds the id unknown and posts it again)
    const left = newId();
    await leave('/v1/jobs', jobBody(left, pageDefault('BBCA')), at);
    const id = newId();
    let a: Answer;
    for (const t0 = Date.now(); (a = await call('POST', '/v1/jobs', jobBody(id, pageDefault('UNVR')), { at })).status === 409; await tick(5))
      assert.ok(Date.now() - t0 < 30_000, 'still BUSY');                // BUSY only while the abandoned request still waits
    assert.equal(a.status, 202, a.body.toString());
    assert.equal((await until(id, at)).status.state, 'FINISHED');
    assert.deepEqual(jobs, ['UNVR'], 'the abandoned job was never started');
    assert.equal((await call('GET', `/v1/jobs/${left}`, undefined, { at })).status, 404);
  } finally { hold.release(); await t.close() }
});

/* ---- logs and start-up ---------------------------------------------------------------------------------------------- */
test('logs: one JSON object per line, no key, no presigned URL, no request body', async () => {
  assert.ok(lines.length > 20);
  const events = new Set<string>();
  for (const l of lines) {
    const o = JSON.parse(l);
    assert.ok(typeof o.ts === 'string' && ['info', 'warn', 'error'].includes(o.level) && typeof o.event === 'string', l);
    events.add(o.event);
    for (const secret of [WORKER_KEY, PROXY_KEY, 'X-Amz-Signature', '/bucket/v1/', 'x-terminal-proxy-key', 'x-backtest-worker-key']) assert.ok(!l.includes(secret), `a log line holds ${secret.slice(0, 12)}: ${l.slice(0, 200)}`);
    assert.ok(!l.includes('"conditions"'), 'a request body was logged');
  }
  for (const e of ['http', 'job_start', 'job_end', 'job_cancel', 'terminal_bundle', 'terminal_file']) assert.ok(events.has(e), `no ${e} line`);
  assert.ok(lines.some(l => l.includes('"event":"job_end"') && l.includes('"code":"TIMEOUT"')));
});

test('start-up: the registry artifact matches; a bad configuration exits 1 naming the variable, never a value', async () => {
  assert.equal(IMAGE_CMD[0], 'node');
  const reg = await checkRegistry();
  assert.equal(reg.ok, true, JSON.stringify(reg));
  const run = (env: Record<string, string>, until?: (out: string) => boolean) => new Promise<{ code: number | null; out: string; child: ReturnType<typeof spawn> }>(ok => {
    const child = spawn(process.execPath, IMAGE_CMD.slice(1), { cwd: WORKER_DIR, env: { PATH: process.env.PATH ?? '', ...env } });
    let out = '';
    child.stdout.on('data', c => { out += c; if (until?.(out)) ok({ code: null, out, child }) });
    child.stderr.on('data', c => { out += c });
    child.on('exit', code => ok({ code, out, child }));
  });
  const missing = await run({ ...ENV(), BACKTEST_WORKER_KEY: '' });
  assert.equal(missing.code, 1);
  const line = JSON.parse(missing.out.trim().split('\n').pop()!);
  assert.deepEqual([line.event, line.message], ['config_invalid', 'BACKTEST_WORKER_KEY is required.']);
  assert.ok(!missing.out.includes(PROXY_KEY));
  const short = await run({ ...ENV(), TERMINAL_PROXY_KEY: 'short-secret' });
  assert.equal(short.code, 1); assert.ok(!short.out.includes('short-secret') && short.out.includes('TERMINAL_PROXY_KEY'));
  assert.equal((await run({ ...ENV(), BACKTEST_FLOW_ENABLED: 'yes' })).code, 1);
  // the image's command with a valid configuration: listens, answers /health, stops on SIGTERM
  const port = await new Promise<number>(ok => { const s = net.createServer().listen(0, '127.0.0.1', () => { const p = (s.address() as net.AddressInfo).port; s.close(() => ok(p)) }) });
  const t0 = performance.now();
  const up = await run({ ...ENV(), PORT: String(port) }, out => out.includes('"event":"start"'));
  observed.startup_ms = Math.round(performance.now() - t0);
  try {
    const start = JSON.parse(up.out.split('\n').find(l => l.includes('"event":"start"'))!);
    assert.equal(start.port, port); assert.equal(start.engine_version, ENGINE_VERSION); assert.equal(start.flow_enabled, false);
    assert.ok(!up.out.includes(WORKER_KEY) && !up.out.includes(PROXY_KEY));
    const h = await call('GET', '/health', undefined, { at: `http://127.0.0.1:${port}`, key: null });
    assert.deepEqual(h.json(), { ok: true, engine_version: ENGINE_VERSION, registry_version: REGISTRY_VERSION });
  } finally {
    const exit = new Promise<number | null>(ok => up.child.on('exit', ok));
    up.child.kill('SIGTERM');
    assert.equal(await exit, 0);
  }
});

/* ---- what was observed (durations on this machine, for the report; not asserted) ---------------------------------- */
const observed: Record<string, unknown> = {};
after(() => { process.stdout.write(`# observed ${JSON.stringify(observed)}\n`) });
