/* Chromium smoke of the Terminal page's file check (EXEC-MU-RUNTIME T7): the built page (`npm run build`, served from
   ../../../static/terminal-app) against a stand-in for EDGE, terminal-api and the bucket on 127.0.0.1, whose files are
   gzip JSON announced with their sha256 and size as terminal-api announces them. The real browser runs the Web Worker
   and IndexedDB `terminal-files`. Scenarios: correct files draw (and the second load reads them from IndexedDB); a
   price file unlike its announcement on the first /bundle draws the second /bundle's file; one that never matches shows
   the plain message after exactly one new /bundle; a cached copy whose bytes changed is downloaded again and replaced;
   a reference file announced with sha256 and size (T5) is checked, one without them is read as before; a broker file
   unlike its announcement gives the Flow from one new /bundle, on the chart's sessions also when that answer's price
   window moved (review of T7).
   Usage: npm run build && node tests/smoke/integrity.mjs */
import { createRequire } from 'node:module';
import { createServer } from 'node:http';
import { createHash } from 'node:crypto';
import { gzipSync } from 'node:zlib';
import { readFile } from 'node:fs/promises';
import { extname, join, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';
const { chromium } = createRequire(import.meta.url)('playwright');   // the preinstalled Playwright (global NODE_PATH)

const BUILD = fileURLToPath(new URL('../../../static/terminal-app/', import.meta.url));
const MESSAGE = 'A data file did not match its published checksum; reload the page.';
const TYPES = { '.html':'text/html', '.js':'text/javascript', '.css':'text/css', '.svg':'image/svg+xml' };
const sha = b => createHash('sha256').update(b).digest('hex');
const gz = doc => gzipSync(Buffer.from(JSON.stringify(doc)), { level:9 });

/* ---- the published files ---------------------------------------------------------------------------------------- */
const ALL = []; for (let t = Date.UTC(2025, 0, 2); ALL.length < 261; t += 864e5) { const d = new Date(t); if (d.getUTCDay() % 6) ALL.push(d.toISOString().slice(0, 10)) }
const DAYS = ALL.slice(0, 260), MOVED = ALL.slice(1);          // MOVED: a later publication whose window lost a session and gained one
function price(ticker, base, lastVolume, days = DAYS) {
  const c = days.map((_, k) => +(base * (1 + 0.1 * Math.sin(k / 9)) + k).toFixed(2));
  const v = ticker === 'IHSG' ? null : days.map((_, k) => k === days.length - 1 ? lastVolume : 1_000_000 + k);
  return gz({ schema_version:1, dataset:'price-pack', ticker, columns:['d', 'o', 'h', 'l', 'c', 'v'], d:days, o:c, h:c.map(x => x * 1.01), l:c.map(x => x * 0.99), c, v });
}
const broker = (d, buy) => gz({ schema_version:1, dataset:'broker', ticker:'MAPI', columns:['d', 'b', 'i', 'm', 'bv', 'sv', 'bl', 'sl'], d, b:d.map(() => 'AK'),
  i:d.map(() => 'Foreign'), m:d.map(() => 'RG'), bv:buy, sv:d.map(() => 0), bl:d.map(() => 1), sl:d.map(() => 0), gap:[] });
const GOOD = price('MAPI', 1400, 7_000_000), STALE = price('MAPI', 900, 3_000_000), IHSG = price('IHSG', 7000, 0);
const FLIPPED = Buffer.from(GOOD); FLIPPED[FLIPPED.length - 9] ^= 0xff;                      // the announced size, another sha256
const BROKER = broker(DAYS.slice(-3), [3e9, 5e9, 7e9]), BROKER_FLIPPED = Buffer.from(BROKER); BROKER_FLIPPED[BROKER_FLIPPED.length - 9] ^= 0xff;
const MOVED_PRICE = price('MAPI', 1400, 7_000_000, MOVED), MOVED_BROKER = broker(MOVED.slice(-4), [3e9, 5e9, 7e9, 9e9]);
const TICKERS = gz({ columns:['ticker', 'name', 'type', 'sector'], ticker:['MAPI', 'IHSG'], name:['Mitra Adiperkasa', 'Composite Index'], type:['stock', 'index'], sector:['Consumer', null] });
const REFS = { tickers:TICKERS, brokers:gz({ columns:['code', 'name', 'type'], code:['AK'], name:['UBS'], type:['Foreign'] }), logos:gz({ columns:['ticker', 'sha256'], ticker:[], sha256:[] }) };

/* ---- EDGE + terminal-api + bucket ------------------------------------------------------------------------------- */
/* `plan`: what the k-th /bundle of MAPI's price serves (body) under the good file's announcement, or {served, announced,
   through}; `refPlan` the same for /reference/tickers (null: answered without sha256, as an older terminal-api);
   `brokerPlan` the k-th /bundle's broker file {served, announced, through} (none: no broker files) */
const S = { plan:[GOOD], refPlan:[null], brokerPlan:[], bundles:0, refs:0, downloads:{} };
const reset = (plan, refPlan = [null], brokerPlan = []) => Object.assign(S, { plan, refPlan, brokerPlan, bundles:0, refs:0, downloads:{} });
const files = new Map();
let origin = '';
const server = createServer(async (req, res) => {
  const url = new URL(req.url, 'http://x'), path = decodeURIComponent(url.pathname);
  const json = (o, status = 200) => { res.writeHead(status, { 'Content-Type':'application/json' }); res.end(JSON.stringify(o)) };
  if (path === '/api/v1/auth/session') return json({ csrf_token:'t', login:'smoke' });
  const ref = path.match(/^\/api\/terminal\/v1\/reference\/(\w+)$/);
  if (ref) {
    const name = ref[1], k = name === 'tickers' ? S.refs++ : 0, plan = name === 'tickers' ? S.refPlan[Math.min(k, S.refPlan.length - 1)] : null;
    const key = `/bucket/ref/${name}/${k}`; files.set(key, plan || REFS[name]);
    return json(plan ? { url:origin + key, sha256:sha(REFS[name]), bytes:REFS[name].length, rows:2 } : { url:origin + key, sha256:null, bytes:null, rows:null });
  }
  if (path === '/api/terminal/v1/bundle' && req.method === 'POST') {
    let body = ''; for await (const c of req) body += c;
    const { ticker, datasets } = JSON.parse(body), out = {};
    const k = ticker === 'MAPI' ? S.bundles++ : 0;
    const nth = list => list[Math.min(k, list.length - 1)];
    for (const d of datasets) {
      const step = ticker !== 'MAPI' ? (d === 'price' ? IHSG : null) : d === 'price' ? nth(S.plan) : d === 'broker' && S.brokerPlan.length ? nth(S.brokerPlan) : null;
      if (!step) { out[d] = { files:[], data_through:null }; continue }
      const f = Buffer.isBuffer(step) ? { served:step, announced:ticker === 'MAPI' ? GOOD : IHSG, through:DAYS.at(-1) } : step;
      const key = `/bucket/${d}/${ticker}/${k}`; files.set(key, f.served);
      out[d] = { data_through:f.through, first_year:2025, files:[{ ...(d === 'price' ? { pack:'price' } : { year:2025 }), url:origin + key, sha256:sha(f.announced), bytes:f.announced.length, rows:DAYS.length }] };
    }
    return json({ ticker, datasets:out, expires_in_seconds:120 });
  }
  if (path.startsWith('/api/terminal/v1/logo/')) return json({ error:'no_logo' }, 404);
  if (files.has(path)) {
    S.downloads[path.split('/').slice(0, 4).join('/')] = (S.downloads[path.split('/').slice(0, 4).join('/')] || 0) + 1;
    res.writeHead(200, { 'Content-Type':'application/gzip', 'Access-Control-Allow-Origin':'*' }); return res.end(files.get(path));
  }
  if (path.startsWith('/terminal-app/')) {
    const rel = normalize(path.slice('/terminal-app/'.length) || 'index.html');
    if (!rel.startsWith('..')) try { const b = await readFile(join(BUILD, rel)); res.writeHead(200, { 'Content-Type':TYPES[extname(rel)] || 'application/octet-stream' }); return res.end(b) } catch {}
  }
  res.writeHead(404); res.end('not found');
});
await new Promise(ok => server.listen(0, '127.0.0.1', ok));
origin = `http://127.0.0.1:${server.address().port}`;

/* ---- the browser --------------------------------------------------------------------------------------------------- */
const browser = await chromium.launch();
const context = await browser.newContext({ viewport:{ width:1440, height:900 } });
const page = await context.newPage();
const errors = [], warnings = [];
page.on('pageerror', e => errors.push(e.message));
page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); if (m.type() === 'warning') warnings.push(m.text()) });
let failed = 0;
const seen = () => ({ bundles:S.bundles, refs:S.refs, downloads:S.downloads });
const check = (name, ok, got) => { console.log(`${ok ? 'ok  ' : 'FAIL'} ${name}${ok ? '' : `: ${JSON.stringify(got === S ? seen() : got?.S ? { ...got, S:seen() } : got)}`}`); if (!ok) failed++ };

/* one page load: the chart drawn (the volume legend of the last session) or the alert's text */
async function open() {
  await page.goto(`${origin}/terminal-app/`);
  await page.waitForFunction(() => !document.querySelector('.ml-boot'), null, { timeout:20_000 });
  const alert = await page.$eval('[role=alert]', e => e.textContent).catch(() => null);
  const volume = await page.$eval('#volVal', e => e.textContent).catch(() => null);
  return { alert, volume, canvas:!!await page.$('#chart canvas') };
}
/* the IndexedDB record of a sha256 as the page's rack.ts stores it */
const record = h => page.evaluate(h => new Promise(ok => { const r = indexedDB.open('terminal-files'); r.onsuccess = () => { const db = r.result;
  if (!db.objectStoreNames.contains('files')) { db.close(); return ok(null) }
  const g = db.transaction('files').objectStore('files').get(h); g.onsuccess = () => { db.close(); ok(g.result ? Array.from(new Uint8Array(g.result.bytes)) : null) } } }), h);
const putRecord = (h, bytes) => page.evaluate(([h, bytes]) => new Promise(ok => { const r = indexedDB.open('terminal-files'); r.onsuccess = () => { const db = r.result;
  const t = db.transaction('files', 'readwrite'); t.objectStore('files').put({ sha:h, bytes:new Uint8Array(bytes).buffer, size:bytes.length, used:Date.now() }); t.oncomplete = () => { db.close(); ok() } } }), [h, bytes]);

try {
  reset([GOOD]);
  let r = await open();
  check('correct files draw (one /bundle, no alert)', r.canvas && !r.alert && r.volume === '7M' && S.bundles === 1, { r, S });
  await page.waitForTimeout(300);
  check('the verified file is stored under its sha256', JSON.stringify(await record(sha(GOOD))) === JSON.stringify(Array.from(GOOD)), null);
  reset([GOOD]); r = await open();
  check('the second load reads it from IndexedDB (no download)', !r.alert && r.volume === '7M' && !S.downloads['/bucket/price/MAPI'], S);

  await putRecord(sha(GOOD), Array.from(STALE));                                 // a cached copy whose bytes changed
  reset([GOOD]); r = await open();
  await page.waitForTimeout(300);
  check('a cached copy whose bytes changed is not drawn: downloaded again and replaced', !r.alert && r.volume === '7M' && S.downloads['/bucket/price/MAPI'] === 1
    && JSON.stringify(await record(sha(GOOD))) === JSON.stringify(Array.from(GOOD)), { r, S });

  await page.evaluate(() => new Promise(ok => { const r = indexedDB.deleteDatabase('terminal-files'); r.onsuccess = r.onerror = r.onblocked = () => ok() }));
  reset([STALE, GOOD]); r = await open();
  check('a price file of another size on the first /bundle: the second /bundle\'s file is drawn', !r.alert && r.volume === '7M' && S.bundles === 2, { r, S });
  check('the stale bytes were never stored', await record(sha(STALE)) === null && JSON.stringify(await record(sha(GOOD))) === JSON.stringify(Array.from(GOOD)), null);

  await page.evaluate(() => new Promise(ok => { const r = indexedDB.deleteDatabase('terminal-files'); r.onsuccess = r.onerror = r.onblocked = () => ok() }));
  warnings.length = 0; reset([FLIPPED]); r = await open();
  check('a file that never matches: the plain message after exactly one new /bundle', r.alert === MESSAGE && S.bundles === 2, { r, S });
  check('the console names what differed, never a URL', warnings.some(w => /price\/price: the sha256 differs/.test(w)) && !warnings.some(w => /https?:\/\//.test(w)), warnings);
  check('nothing was stored', await record(sha(GOOD)) === null, null);

  const badTickers = Buffer.from(TICKERS); badTickers[badTickers.length - 9] ^= 0xff;
  reset([GOOD], [badTickers, TICKERS]); r = await open();
  check('a reference file announced with sha256 and size: one new /reference on a failed check, then drawn', !r.alert && r.volume === '7M' && S.refs === 2, { r, S });
  reset([GOOD], [badTickers]); r = await open();
  check('the verified reference file is read from IndexedDB next time (no download)', !r.alert && S.refs === 1 && !S.downloads['/bucket/ref/tickers'], { r, S });
  await page.evaluate(() => new Promise(ok => { const r = indexedDB.deleteDatabase('terminal-files'); r.onsuccess = r.onerror = r.onblocked = () => ok() }));
  reset([GOOD], [badTickers]); r = await open();
  check('a reference file that never matches: the plain message', r.alert === MESSAGE && S.refs === 2, { r, S });
  reset([GOOD], [null]); r = await open();
  check('a reference file without sha256 (older terminal-api) is read as before', !r.alert && r.volume === '7M' && S.refs === 1, { r, S });

  /* review of T7 (2026-10-29): the Flow in the real Worker. A broker file unlike its announcement is read from one new
     /bundle; when that answer comes from a later publication whose price window moved, the Flow stays on the chart's
     sessions (before the review the latest day showed the next session's Rp 9B) */
  const dropCache = () => page.evaluate(() => new Promise(ok => { const r = indexedDB.deleteDatabase('terminal-files'); r.onsuccess = r.onerror = r.onblocked = () => ok() }));
  const latestFlow = async () => {
    await page.waitForFunction(() => !/Loading/.test(document.getElementById('flowNote')?.textContent || ''), null, { timeout:20_000 });
    return page.$eval('#flowSummary .flow-stat', e => e.textContent);
  };
  const brokerOk = { served:BROKER, announced:BROKER, through:DAYS.at(-1) };
  await dropCache(); reset([GOOD], [null], [brokerOk]); r = await open();
  const flowBase = await latestFlow();
  check('the Flow from a correct broker file (one /bundle)', !r.alert && /Rp 7B/.test(flowBase) && S.bundles === 1, { r, flowBase, S });
  await dropCache(); reset([GOOD], [null], [{ ...brokerOk, served:BROKER_FLIPPED }, brokerOk]); r = await open();
  let flow = await latestFlow();
  check('a broker file unlike its announcement: the Flow comes from one new /bundle (Worker)', !r.alert && r.volume === '7M' && flow === flowBase && S.bundles === 2, { r, flow, S });
  await dropCache();
  reset([GOOD, { served:MOVED_PRICE, announced:MOVED_PRICE, through:MOVED.at(-1) }], [null], [{ ...brokerOk, served:BROKER_FLIPPED }, { served:MOVED_BROKER, announced:MOVED_BROKER, through:MOVED.at(-1) }]);
  r = await open(); flow = await latestFlow();
  check('the new answer from a publication whose window moved: the Flow stays on the chart\'s sessions', !r.alert && r.volume === '7M' && flow === flowBase && S.bundles === 2, { r, flow, S });
} finally {
  await browser.close(); server.close();
}
const real = errors.filter(e => !/Failed to load resource: the server responded with a status of 404/.test(e));
check('no page errors', !real.length, real);
console.log(failed ? `smoke: ${failed} failed` : 'smoke: every check passed');
process.exit(failed ? 1 : 0);
