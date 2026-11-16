/* Memory of the backtest worker on real published files (ERRORS M463, user 2026-11-16 "Go untuk opsi 1"): the worker as
   its image starts it (Dockerfile CMD and ENV lines), against tests/fake-terminal.mjs serving the files fetch.py saved
   from dev, the process's RSS sampled every 50 ms from /proc. It sends a signals preview of the request's stocks, then
   the run, then a 3-stock preview, and reads the memory after each step (1, 3, 10, 30 s later). Read only on dev:
   nothing is sent there.

     node measure.mjs DATA_DIR REQUEST.json OUT.json [VAR=value ...]

   DATA_DIR: fetch.py's output (one folder per ticker with bundle.json and its files, ref-brokers.json, ref-tickers.json;
   IHSG included). REQUEST.json: a BacktestRequest (single or portfolio), e.g. a request of e2e_dev.py's report
   (steps.portfolio.request). VAR=value: a worker variable over the defaults below (the dev values of 2026-11-16 that
   are not secrets; the keys here are local and made up), e.g. BACKTEST_DOWNLOAD_CONCURRENCY=16 for the old setting,
   WORKER_DIR=<checkout>/apps/backtest-worker to measure another checkout. Linux only (/proc). */
import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const { startFakeTerminal } = await import(path.join(ROOT, 'apps/backtest-worker/tests/fake-terminal.mjs'));
const [dataDir, requestPath, outPath, ...extra] = process.argv.slice(2);
if (!dataDir || !requestPath || !outPath) { console.error('usage: node measure.mjs DATA_DIR REQUEST.json OUT.json [VAR=value ...]'); process.exit(2) }
const q = JSON.parse(fs.readFileSync(requestPath, 'utf8'));
const picked = q.mode === 'single' ? [q.single.ticker] : q.portfolio.tickers;

// the published files, as terminal-api answers them (the packs: the broker archive holds the years before the first yearly file)
const tickers = {};
for (const t of fs.readdirSync(dataDir).filter(n => fs.statSync(path.join(dataDir, n)).isDirectory())) {
  const b = JSON.parse(fs.readFileSync(path.join(dataDir, t, 'bundle.json'), 'utf8')), datasets = {};
  for (const [name, d] of Object.entries(b.datasets)) {
    datasets[name] = { data_through: d.data_through, first_year: d.first_year, files: d.files.map(f => {
      const o = { body: fs.readFileSync(path.join(dataDir, t, `${name}-${f.pack || f.year || 'all'}.gz`)), rows: f.rows };
      if (f.pack) { o.pack = f.pack; if (f.pack === 'broker-archive') o.years = [b.window.broker_first_year, Math.min(...d.files.filter(x => x.year).map(x => x.year)) - 1] }
      else if (name !== 'events') o.year = f.year;
      return o;
    }) };
  }
  tickers[t] = { generated_at: b.generated_at, window: b.window, datasets };
}
const refs = Object.fromEntries(['brokers', 'tickers'].map(n => [n, JSON.parse(fs.readFileSync(path.join(dataDir, `ref-${n}.json`), 'utf8'))]));
const PROXY = 'measure-proxy-key-'.padEnd(48, 'p'), KEY = 'measure-worker-key-'.padEnd(48, 'w'), PORT = 18099;
const fake = await startFakeTerminal({ key: PROXY, tickers, refs, ttl: 600 });
const cacheDir = fs.mkdtempSync(path.join(fs.realpathSync(process.env.TMPDIR || '/tmp'), 'backtest-measure-'));

// the image's own environment (ENV lines of the Dockerfile), then the service's variables
const workerDir = path.join(ROOT, 'apps/backtest-worker');
const image = {};
for (const line of fs.readFileSync(path.join(workerDir, 'Dockerfile'), 'utf8').split('\n'))
  if (/^ENV\s/.test(line)) for (const kv of line.slice(4).trim().split(/\s+/)) { const i = kv.indexOf('='); image[kv.slice(0, i)] = kv.slice(i + 1) }
const env = { PATH: process.env.PATH, ...image, PORT: String(PORT), BACKTEST_WORKER_KEY: KEY, TERMINAL_URL: fake.url, TERMINAL_PROXY_KEY: PROXY,
  BACKTEST_FILE_ORIGIN: fake.url, BACKTEST_CACHE_DIR: cacheDir, BACKTEST_CACHE_DIR_BYTES: '1073741824', BACKTEST_CACHE_BYTES: '1500000000',
  BACKTEST_DOWNLOAD_CONCURRENCY: '4', BACKTEST_DOWNLOAD_RETRIES: '3', BACKTEST_RETRY_BASE_MS: '500', BACKTEST_HTTP_TIMEOUT_MS: '60000',
  BACKTEST_FLOW_ENABLED: '1', BACKTEST_MAX_BROKER_ROWS: '20000000', BACKTEST_MAX_CONDITIONS: '32', BACKTEST_MAX_DOWNLOAD_BYTES: '1500000000',
  BACKTEST_MAX_FILE_BYTES: '67108864', BACKTEST_MAX_RESULT_BYTES: '33554432', BACKTEST_TIMEOUT_SECONDS: '900' };
let dir = workerDir;
for (const kv of extra) { const i = kv.indexOf('='); if (kv.slice(0, i) === 'WORKER_DIR') dir = kv.slice(i + 1); else env[kv.slice(0, i)] = kv.slice(i + 1) }
const cmd = JSON.parse(/^CMD\s+(\[.*\])/m.exec(fs.readFileSync(path.join(workerDir, 'Dockerfile'), 'utf8'))[1]);
const child = spawn(process.execPath, cmd.slice(1), { cwd: dir, env });
const logged = [];
child.stdout.on('data', c => logged.push(String(c))); child.stderr.on('data', c => logged.push(String(c)));
let exited = null; child.on('exit', (code, sig) => { exited = { code, sig } });

const rss = () => { try { return Number(/VmRSS:\s+(\d+)/.exec(fs.readFileSync(`/proc/${child.pid}/status`, 'utf8'))[1]) * 1024 } catch { return 0 } };
const MB = b => Math.round(b / 1048576), sleep = ms => new Promise(r => setTimeout(r, ms));
let peak = 0, since = 0;
const sampler = setInterval(() => { const r = rss(); peak = Math.max(peak, r); since = Math.max(since, r) }, 50);
const steps = [];
const mark = (name, extraFields = {}) => { steps.push({ name, rss_mb: MB(rss()), peak_since_previous_mb: MB(since), ...extraFields }); since = rss() };
const after = async (label, seconds) => { let at = 0; for (const s of seconds) { await sleep((s - at) * 1000); at = s; mark(`${label} +${s}s`) } };
const base = `http://127.0.0.1:${PORT}`, H = { 'content-type': 'application/json', 'x-backtest-worker-key': KEY };
const post = (p, body) => fetch(base + p, { method: 'POST', headers: H, body: JSON.stringify(body) });
const preview = tickers => post('/v1/signals', { request: { schema_version: 1, tickers, period: { from: q.period.from, to: q.period.to }, entry: q.entry }, context: { rights: [] } });

for (let i = 0; i < 300; i++) { try { if ((await fetch(base + '/health')).ok) break } catch {} await sleep(100) }
mark('started');
let t0 = performance.now(), r = await preview(picked);
mark(`preview of ${picked.length} stock(s)`, { status: r.status, ms: Math.round(performance.now() - t0), rows: ((await r.json()).rows || []).length });
await after('after the preview', [1, 3]);
const id = 'bt_' + 'a'.repeat(32);
t0 = performance.now(); r = await post('/v1/jobs', { job_id: id, request: q, context: { job_id: id, prior_trials: [], rights: [] } });
let st = { state: `submit ${r.status}` };
if (r.status === 202) for (;;) {
  await sleep(200);
  st = await (await fetch(`${base}/v1/jobs/${id}`, { headers: H })).json();
  if (['FINISHED', 'FAILED', 'CANCELLED'].includes(st.state) || exited) break;
}
mark('run', { state: st.state, code: st.error?.code ?? null, ms: Math.round(performance.now() - t0) });
await after('after the run', [1, 3, 10, 30]);
t0 = performance.now(); r = await preview(picked.slice(0, 3));
mark('preview of 3 stocks', { status: r.status, ms: Math.round(performance.now() - t0) }); await r.json();
await after('after it', [1, 3]);
clearInterval(sampler);
const out = { request: path.basename(requestPath), variables: extra, peak_rss_mb: MB(peak), steps, exited,
  log: logged.join('').split('\n').filter(l => /"(thread_start|thread_end|preview_end|job_end|start)"/.test(l)).map(l => JSON.parse(l)) };
fs.writeFileSync(outPath, JSON.stringify(out, null, 1));
console.log(JSON.stringify({ peak_rss_mb: out.peak_rss_mb, steps, exited }, null, 1));
child.kill('SIGTERM'); await fake.close(); fs.rmSync(cacheDir, { recursive: true, force: true }); process.exit(0);
