/* backtest-worker per-instance cold start and first jobs, the real worker process (the image's command) against the
   tests' fake terminal-api + bucket (apps/backtest-worker/tests/fake-terminal.mjs) serving REAL price history (the full
   dump) in the publisher's format. Measured from outside: spawn -> 'start' log line (listening) -> first GET /v1/catalog
   answer; jobs submit -> FINISHED (polled every 25 ms; edge-bff polls every 2 s in production); RSS from /proc every
   20 ms. Then a second process on the same (now filled) disk cache dir.
   Flow/broker files are not served (no broker data in the sandbox): the jobs are price-only (the page default entry
   without flow cards, as tests/server.test.ts pageDefault). Usage:
   node --experimental-strip-types --no-warnings --import <loader> bt_cold.mts <price_full.json> <out.json> [--api-delay ms] [--file-delay ms]
   Read-only on the repository (the cache dir is a fresh scratch directory). */
import { spawn } from 'node:child_process';
import { mkdtempSync, readFileSync, writeFileSync, readdirSync, statSync } from 'node:fs';
import http from 'node:http';
import zlib from 'node:zlib';
import { DEFAULT_ENTRY, LEGACY, legacyCard, legacyToCondition } from '/home/user/saniti/apps/edge-bff/backtest/src/core/catalog.ts';
import type { LegacyCard } from '/home/user/saniti/apps/edge-bff/backtest/src/core/catalog.ts';
import type { BacktestRequest } from '/home/user/saniti/apps/edge-bff/backtest/src/core/contract.ts';
import { brokersRef, pricePack, priceYears, startFakeTerminal, tickersRef } from '/home/user/saniti/apps/backtest-worker/tests/fake-terminal.mjs';

const [dataPath, outPath, ...rest] = process.argv.slice(2);
const opt = (k: string, d: number) => rest.includes(k) ? Number(rest[rest.indexOf(k) + 1]) : d;
const API_DELAY = opt('--api-delay', 0), FILE_DELAY = opt('--file-delay', 0);
const WORKER_DIR = '/home/user/saniti/apps/backtest-worker';
const WORKER_KEY = 'bench-worker-key-'.padEnd(48, 'w'), PROXY_KEY = 'bench-proxy-key-'.padEnd(48, 'p');
const SINGLE = 'BBCA';
const PORTFOLIO = ['BBCA', 'BBRI', 'BMRI', 'BBNI', 'TLKM', 'ASII', 'UNVR', 'ICBP', 'ADRO', 'ANTM', 'GOTO', 'AMMN'];
const PUBLISHED = ['IHSG', ...new Set([SINGLE, ...PORTFOLIO, 'INDF', 'KLBF', 'PGAS'])];

/* ---- the published market: real rows ---- */
const t00 = performance.now();
const D = JSON.parse(readFileSync(dataPath, 'utf8')) as Record<string, { d: string[]; o: number[]; h: number[]; l: number[]; c: number[]; v: (number | null)[] }>;
for (const t of PUBLISHED) if (!D[t]) throw new Error(`no data for ${t}`);
const THROUGH = D.IHSG.d[D.IHSG.d.length - 1];
const rowsOf = (t: string) => D[t].d.map((d, i) => [d, D[t].o[i], D[t].h[i], D[t].l[i], D[t].c[i], D[t].v[i]]);
const MARKET = Object.fromEntries(PUBLISHED.map(t => [t, { generated_at: '2026-10-27T13:03:00+00:00', datasets: {
  price: { data_through: THROUGH, first_year: +D[t].d[0].slice(0, 4), files: [{ pack: 'price', doc: pricePack(t, rowsOf(t)) }, ...priceYears(t, rowsOf(t))] },
  ...(t === 'IHSG' ? {} : { events: { data_through: null, files: [] } }),
} }]));
const REFS = {
  tickers: tickersRef(Object.keys(D).sort().map(t => [t, `${t} (bench name)`, t === 'IHSG' ? 'index' : 'stock', t === 'IHSG' ? null : 'Sector B', t === 'IHSG' ? 'Undefined' : 'Industry B'])),
  brokers: brokersRef([['YU', 'bench broker', 'Foreign'], ['ZP', 'bench broker 2', 'Local']]),
};
const fake = await startFakeTerminal({ key: PROXY_KEY, tickers: MARKET, refs: REFS, delayMs: API_DELAY, fileDelayMs: FILE_DELAY,
  state: { finished_at: '2026-10-27T13:03:00+00:00', price_through: THROUGH, broker_through: THROUGH } });
const setup_ms = Math.round(performance.now() - t00);

/* ---- requests (tests/server.test.ts pageDefault / portfolioDefault) ---- */
function pageDefault(ticker: string): BacktestRequest {
  const cards = DEFAULT_ENTRY.map(([t, over], k) => legacyCard(t, `c${k + 1}`, over as Partial<LegacyCard>)).filter(c => LEGACY[c.type].group !== 'flow');
  return {
    schema_version: 1, mode: 'single', single: { ticker, benchmark: 'buy_and_hold' },
    period: { from: '2019-06-03', to: THROUGH, oos_fraction: 0.3 },
    entry: { logic: 'at_least', at_least: 3, window_bars: 5, conditions: cards.map(legacyToCondition) },
    exit: {
      atr_length: 14,
      stop: { mode: 'pct', pct: 0.07, atr_mult: 2, reward_risk_x: 2, line: { indicator: 'I09', output: 'supertrend' } },
      take_profit: { mode: 'pct', pct: 0.15, r_multiple: 2, atr_mult: 3 },
      trailing: { mode: 'none', pct: 0.05, chandelier_length: 22, chandelier_mult: 3, line: { indicator: 'I01', output: 'sma' } },
      max_hold_bars: 20, signals: { logic: 'any', conditions: [] },
    },
    sizing: { capital_idr: 100e6, allocation_fraction: 1 },
    costs: { buy_fee: 0.0015, sell_fee: 0.0025, slippage: 0.0005, skip_ara_open_gap: true, ara_gap_fraction: 0.2 },
    robustness: { monte_carlo_runs: 1000, seed: 7, sensitivity: true },
  } as BacktestRequest;
}
function portfolioDefault(tickers: string[]): BacktestRequest {
  const q = pageDefault('BBCA') as any; delete q.single;
  return { ...q, mode: 'portfolio', portfolio: { tickers: [...tickers], max_positions: 5, rank_by: 'adx', min_avg_value_20d_idr: 5e9 } };
}

/* ---- the worker process ---- */
const ENV = (cacheDir: string): Record<string, string> => ({
  PATH: process.env.PATH ?? '', PORT: '0',
  BACKTEST_WORKER_KEY: WORKER_KEY, TERMINAL_URL: fake.url, TERMINAL_PROXY_KEY: PROXY_KEY,
  // dev values (BACKTEST_END_TO_END.md 7.4) where they matter for memory and lanes; retries 0 (a local fake)
  BACKTEST_CACHE_BYTES: String(1.5e9), BACKTEST_DOWNLOAD_CONCURRENCY: '16', BACKTEST_DOWNLOAD_RETRIES: '0', BACKTEST_RETRY_BASE_MS: '0', BACKTEST_HTTP_TIMEOUT_MS: '60000',
  BACKTEST_FILE_ORIGIN: fake.url, BACKTEST_MAX_FILE_BYTES: '100000000', BACKTEST_CACHE_DIR: cacheDir, BACKTEST_CACHE_DIR_BYTES: String(1 << 30),
  BACKTEST_MAX_DOWNLOAD_BYTES: String(1.5e9), BACKTEST_MAX_BROKER_ROWS: '20000000', BACKTEST_TIMEOUT_SECONDS: '900',
  BACKTEST_MAX_CONDITIONS: '32', BACKTEST_MAX_RESULT_BYTES: '33554432', BACKTEST_FLOW_ENABLED: '1',
});
const statusOf = (pid: number) => { try { const s = readFileSync(`/proc/${pid}/status`, 'utf8'); const g = (k: string) => Number((new RegExp(`^${k}:\\s+(\\d+)`, 'm').exec(s) || [])[1] || 0) / 1024; return { rss: g('VmRSS'), hwm: g('VmHWM') } } catch { return null } };

async function instance(label: string, cacheDir: string, jobs: { name: string; request: BacktestRequest }[], idleS: number[]) {
  const t0 = performance.now(), at = () => Math.round(performance.now() - t0);
  // PORT 0 is refused by loadConfig (min 1): pick a free port first
  const port = await new Promise<number>(ok => { const s = http.createServer(); s.listen(0, '127.0.0.1', () => { const p = (s.address() as any).port; s.close(() => ok(p)) }) });
  const env = { ...ENV(cacheDir), PORT: String(port) };
  const child = spawn(process.execPath, ['--experimental-strip-types', '--import', './loader/register.mjs', 'src/server.ts'], { cwd: WORKER_DIR, env, stdio: ['ignore', 'pipe', 'pipe'] });
  let hwm = 0, phasePeak = 0; const curve: [number, number][] = [];
  const tick = setInterval(() => { const s = statusOf(child.pid!); if (s) { hwm = Math.max(hwm, s.hwm); phasePeak = Math.max(phasePeak, s.rss); curve.push([at(), Math.round(s.rss)]) } }, 20);
  const logs: any[] = []; let buf = '', err = '', startAt: number | null = null;
  child.stdout!.on('data', d => { buf += d; let i; while ((i = buf.indexOf('\n')) >= 0) { const l = buf.slice(0, i); buf = buf.slice(i + 1); try { const j = JSON.parse(l); logs.push({ at: at(), event: j.event, ms: j.ms, path: j.path, status: j.status, ...(j.event === 'start' ? { engine_version: j.engine_version } : {}) }); if (j.event === 'start' && startAt === null) startAt = at() } catch { } } });
  child.stderr!.on('data', d => { err += d });
  const base = `http://127.0.0.1:${port}`;
  const call = (method: string, path: string, body?: unknown) => new Promise<{ status: number; body: Buffer }>((ok, no) => {
    const data = body === undefined ? undefined : JSON.stringify(body);
    const req = http.request(base + path, { method, headers: { 'content-type': 'application/json', 'x-backtest-worker-key': WORKER_KEY, ...(data ? { 'content-length': String(Buffer.byteLength(data)) } : {}) } }, res => {
      const parts: Buffer[] = []; res.on('data', c => parts.push(c)); res.on('end', () => ok({ status: res.statusCode!, body: Buffer.concat(parts) }));
    });
    req.on('error', no); req.end(data);
  });
  while (startAt === null) { if (child.exitCode !== null) throw new Error(`worker exited: ${err.slice(-500)}`); await new Promise(r => setTimeout(r, 5)) }
  const rssAtStart = statusOf(child.pid!)?.rss;
  const c0 = at(); const cat = await call('GET', '/v1/catalog'); const catalog_ms = at() - c0;
  const res: any = { label, spawn_to_listen_ms: startAt, rss_at_listen_mb: Math.round(rssAtStart ?? 0), first_catalog: { status: cat.status, answered_at_ms: at(), request_ms: catalog_ms, bytes: cat.body.length },
    rss_after_catalog_mb: Math.round(statusOf(child.pid!)?.rss ?? 0), jobs: [] };
  let n = 0;
  for (const j of jobs) {
    const id = `bt_${label.charCodeAt(0).toString(16)}${(++n).toString(16).padStart(6, '0')}${'0'.repeat(24)}`;
    phasePeak = 0;
    const s0 = performance.now();
    const p = await call('POST', '/v1/jobs', { job_id: id, request: j.request, context: { job_id: id, prior_trials: [] } });
    if (p.status !== 202) { res.jobs.push({ name: j.name, submit_status: p.status, body: p.body.toString().slice(0, 400) }); continue }
    let st: any;
    for (;;) { const a = await call('GET', `/v1/jobs/${id}`); st = JSON.parse(a.body.toString()); if (['FINISHED', 'FAILED', 'CANCELLED'].includes(st.state)) break; await new Promise(r => setTimeout(r, 25)) }
    const done_ms = Math.round(performance.now() - s0);
    const r = await call('GET', `/v1/jobs/${id}/result`);
    let meta: any = null; try { meta = JSON.parse(zlib.gunzipSync(r.body).toString()).meta } catch { }
    res.jobs.push({ name: j.name, state: st.state, error: st.error ?? null, submit_to_finished_ms: done_ms, worker_duration_ms: meta?.duration_ms ?? null,
      result_gzip_bytes: r.body.length, phase_peak_rss_mb: Math.round(phasePeak), data_version: meta?.data_version?.slice?.(0, 12) ?? null });
  }
  for (const s of idleS) { await new Promise(r => setTimeout(r, s * 1000)); res[`idle_rss_after_${s}s_more_mb`] = Math.round(statusOf(child.pid!)?.rss ?? 0) }
  res.peak_rss_mb = Math.round(hwm);
  const files = (() => { try { const f = readdirSync(cacheDir); return { files: f.length, bytes: f.reduce((a, x) => a + statSync(`${cacheDir}/${x}`).size, 0) } } catch { return null } })();
  res.disk_cache = files;
  child.kill('SIGTERM'); await new Promise(r => child.once('exit', r)); clearInterval(tick);
  res.bundle_requests = fake.requests.filter((q: any) => q.path === '/api/terminal/v1/bundle').length;
  res.bucket_requests = fake.requests.filter((q: any) => q.path.startsWith('/bucket/')).length;
  fake.requests.length = 0;
  res.log_events = logs.filter(l => l.event !== 'http').slice(0, 40);
  res.rss_curve = curve.filter((_, i) => i % 10 === 0);
  res.stderr_tail = err.slice(-300);
  return res;
}

const dir = mkdtempSync('/tmp/claude-0/-home-user-saniti/65bd49d0-9dca-5072-b7db-b62314cf2cd3/scratchpad/mu_runtime/bench/data/btcache-');
const J = [
  { name: 'single_BBCA_first', request: pageDefault(SINGLE) },
  { name: 'single_BBCA_repeat', request: pageDefault(SINGLE) },
  { name: 'portfolio12_first', request: portfolioDefault(PORTFOLIO) },
  { name: 'portfolio12_repeat', request: portfolioDefault(PORTFOLIO) },
];
const out: any = { node: process.version, api_delay_ms: API_DELAY, file_delay_ms: FILE_DELAY, setup_ms, published: PUBLISHED, through: THROUGH };
out.cold_empty_disk = await instance('cold', dir, J, [10, 20]);
out.restart_disk_filled = await instance('restart', dir, [J[0], J[2]], []);
await fake.close();
writeFileSync(outPath, JSON.stringify(out, null, 1));
const brief = (r: any) => ({ listen: r.spawn_to_listen_ms, catalog_at: r.first_catalog.answered_at_ms, catalog_status: r.first_catalog.status, rss_listen: r.rss_at_listen_mb, rss_cat: r.rss_after_catalog_mb, peak: r.peak_rss_mb,
  jobs: r.jobs.map((j: any) => [j.name, j.state, j.submit_to_finished_ms, j.worker_duration_ms, j.phase_peak_rss_mb, j.error?.code ?? '']), idle10: r.idle_rss_after_10s_more_mb, idle30: r.idle_rss_after_20s_more_mb, disk: r.disk_cache, bundles: r.bundle_requests, bucket: r.bucket_requests });
console.log(JSON.stringify({ cold: brief(out.cold_empty_disk), restart: brief(out.restart_disk_filled) }));
