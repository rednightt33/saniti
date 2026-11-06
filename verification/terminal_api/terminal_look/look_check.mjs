/* EXEC-TERMINAL-LOOK, EXEC-BROKER-INV-PANEL, EXEC-IND-DIALOG (user go 2026-11-06): the built Terminal page with real data
   in Chromium. A stand-in for EDGE, terminal-api and the bucket (as apps/edge-bff/terminal/tests/smoke/integrity.mjs)
   serves the page from ../../../apps/edge-bff/static/terminal-app and BBRI's price and broker rows exported read-only from
   PostgreSQL (DATA dir: px_<T>.json, bk_<T>.json, pgweb /api/query answers). Screenshots go to OUT.
   Usage: (cd apps/edge-bff/terminal && npm run build) && node look_check.mjs DATA OUT [TICKER] [WIDTH] */
import { createRequire } from 'node:module';
import { createServer } from 'node:http';
import { createHash } from 'node:crypto';
import { gzipSync } from 'node:zlib';
import { readFile, mkdir } from 'node:fs/promises';
import { existsSync, readFileSync } from 'node:fs';
import { extname, join, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';
const { chromium } = createRequire(import.meta.url)('playwright');

const [DATA, OUT, TICKER = 'BBRI', WIDTH = '1440'] = process.argv.slice(2);
const BUILD = fileURLToPath(new URL('../../../apps/edge-bff/static/terminal-app/', import.meta.url));
const TYPES = { '.html':'text/html', '.js':'text/javascript', '.css':'text/css', '.svg':'image/svg+xml' };
const sha = b => createHash('sha256').update(b).digest('hex');
const gz = doc => gzipSync(Buffer.from(JSON.stringify(doc)));
const load = n => existsSync(join(DATA, n)) ? JSON.parse(readFileSync(join(DATA, n), 'utf8')).rows : null;
const columnar = (rows, cols) => Object.fromEntries(cols.map((c, k) => [c, rows.map(r => r[k])]));

function pricePack(t) {
  const rows = load(`px_${t}.json`); if (!rows) return null;
  const doc = { schema_version:1, dataset:'price-pack', ticker:t, columns:['d', 'o', 'h', 'l', 'c', 'v'], ...columnar(rows, ['d', 'o', 'h', 'l', 'c', 'v']) };
  return { body:gz(doc), through:rows.at(-1)[0], rows:rows.length };
}
function brokerYears(t) {
  const rows = load(`bk_${t}.json`); if (!rows) return [];
  const years = [...new Set(rows.map(r => r[0].slice(0, 4)))];
  return years.map(y => { const yr = rows.filter(r => r[0].startsWith(y));
    const data = yr.map(r => [r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[9] == null ? null : +r[9], r[10] == null ? null : +r[10]]);
    const doc = { schema_version:1, dataset:'broker', ticker:t, year:+y, columns:['d', 'b', 'i', 'm', 'bv', 'sv', 'bl', 'sl', 'bf', 'sf'],
      ...columnar(data, ['d', 'b', 'i', 'm', 'bv', 'sv', 'bl', 'sl', 'bf', 'sf']), gap:[...new Set(yr.filter(r => r[8]).map(r => `${r[0]}|${r[3]}`))].map(s => s.split('|')) };
    return { year:+y, body:gz(doc), rows:yr.length, through:yr.at(-1)[0] } });
}
const TICKERS = gz({ columns:['ticker', 'name', 'type', 'sector'], ticker:['BBRI', 'IHSG'], name:['Bank Rakyat Indonesia', 'Composite Index'], type:['stock', 'index'], sector:['Finance', null] });
const brokerCodes = [...new Set((load(`bk_${TICKER}.json`) || []).map(r => r[1]))].sort();
const REFS = { tickers:TICKERS, brokers:gz({ columns:['code', 'name', 'type'], code:brokerCodes, name:brokerCodes, type:brokerCodes.map(() => 'Domestic') }),
  logos:gz({ columns:['ticker', 'sha256'], ticker:[], sha256:[] }) };

const files = new Map(); let origin = '';
const server = createServer(async (req, res) => {
  const url = new URL(req.url, 'http://x'), path = decodeURIComponent(url.pathname);
  const json = (o, status = 200) => { res.writeHead(status, { 'Content-Type':'application/json' }); res.end(JSON.stringify(o)) };
  if (path === '/api/v1/auth/session') return json({ csrf_token:'t', login:'look' });
  const ref = path.match(/^\/api\/terminal\/v1\/reference\/(\w+)$/);
  if (ref && REFS[ref[1]]) { const key = `/bucket/ref/${ref[1]}`; files.set(key, REFS[ref[1]]); return json({ url:origin + key, sha256:sha(REFS[ref[1]]), bytes:REFS[ref[1]].length, rows:1 }) }
  if (path === '/api/terminal/v1/bundle' && req.method === 'POST') {
    let body = ''; for await (const c of req) body += c;
    const { ticker, datasets } = JSON.parse(body), out = {};
    for (const d of datasets) {
      if (d === 'price') { const p = pricePack(ticker); if (!p) { out[d] = { files:[], data_through:null }; continue }
        const key = `/bucket/price/${ticker}`; files.set(key, p.body);
        out[d] = { data_through:p.through, first_year:2025, files:[{ pack:'price', url:origin + key, sha256:sha(p.body), bytes:p.body.length, rows:p.rows }] }; continue }
      if (d === 'broker') { const ys = brokerYears(ticker); if (!ys.length) { out[d] = { files:[], data_through:null }; continue }
        out[d] = { data_through:ys.at(-1).through, first_year:ys[0].year, files:ys.map(y => { const key = `/bucket/broker/${ticker}/${y.year}`; files.set(key, y.body);
          return { year:y.year, url:origin + key, sha256:sha(y.body), bytes:y.body.length, rows:y.rows } }) }; continue }
      out[d] = { files:[], data_through:null };
    }
    return json({ ticker, datasets:out, expires_in_seconds:120 });
  }
  if (path.startsWith('/api/terminal/v1/logo/')) return json({ error:'no_logo' }, 404);
  if (files.has(path)) { res.writeHead(200, { 'Content-Type':'application/gzip', 'Access-Control-Allow-Origin':'*' }); return res.end(files.get(path)) }
  if (path.startsWith('/terminal-app/')) {
    const rel = normalize(path.slice('/terminal-app/'.length) || 'index.html');
    if (!rel.startsWith('..')) try { const b = await readFile(join(BUILD, rel)); res.writeHead(200, { 'Content-Type':TYPES[extname(rel)] || 'application/octet-stream' }); return res.end(b) } catch {}
  }
  res.writeHead(404); res.end('not found');
});
await new Promise(ok => server.listen(0, '127.0.0.1', ok));
origin = `http://127.0.0.1:${server.address().port}`;
await mkdir(OUT, { recursive:true });

const browser = await chromium.launch();
const context = await browser.newContext({ viewport:{ width:+WIDTH, height:900 } });
const page = await context.newPage();
const errors = []; page.on('pageerror', e => errors.push(e.message)); page.on('console', m => { if (m.type() === 'error') errors.push(m.text()) });
const shot = (n, el) => (el ? page.locator(el).first() : page).screenshot({ path:join(OUT, `${n}.png`) });
const report = {};
try {
  await page.goto(`${origin}/terminal-app/?t=${TICKER}`);
  await page.waitForFunction(() => !document.querySelector('.ml-boot'), null, { timeout:30_000 });
  await page.waitForTimeout(1500);
  await shot('01_page');
  report.axis = await page.evaluate(() => [...document.querySelectorAll('#chart td:last-child canvas')].length);
  // the Indicators window
  await page.click('#indBtn'); await page.waitForTimeout(300); await shot('02_dialog', '.im-box');
  await page.fill('#imSearch', 'Broker Inventory'); await page.waitForTimeout(200);
  await page.click('.im-row[data-id="FL23"] .im-add'); await page.waitForTimeout(250);
  report.toast = await page.$eval('.im-toast', e => [e.textContent, e.classList.contains('show')]);
  await shot('03_dialog_added', '.im-box');
  await page.keyboard.press('Escape'); await page.waitForTimeout(1200);
  await shot('04_with_fl23');
  report.fl23 = await page.evaluate(() => { const row = [...document.querySelectorAll('.ind-row.in-pane')].find(r => r.dataset.def === 'FL23');
    return { title:row?.querySelector('.ind-k')?.textContent, filters:[...(row?.querySelectorAll('.fl-btn') || [])].map(b => b.textContent.trim()),
      zero:(() => { const z = document.querySelector('.ind-zero'); return z && !z.hidden ? z.getBoundingClientRect().toJSON() : null })() } });
  report.saved = await page.evaluate(() => { try { return JSON.parse(localStorage.getItem('ml.ind.v1') || 'null') } catch { return null } });
  // the right panel (opened when collapsed), its sections scrolled into view
  if (await page.$eval('#workspace', e => e.classList.contains('right-collapsed')).catch(() => false)) { await page.click('#rpExpand'); await page.waitForTimeout(800) }
  await page.locator('.st[data-sec="acc"]').scrollIntoViewIfNeeded().catch(() => {});
  report.lanes = await page.$$eval('.acc-lane', ls => ls.map(l => l.textContent.replace(/\s+/g, ' ').trim()));
  report.accTag = await page.$eval('.acc-bal', e => e.textContent.replace(/\s+/g, ' ').trim()).catch(() => null);
  await shot('05_top_brokers', '.st[data-sec="acc"]');
  report.map = await page.$eval('#fdBody', e => e.textContent.replace(/\s+/g, ' ').trim()).catch(() => null);
  await page.locator('.st[data-sec="fdmap"]').scrollIntoViewIfNeeded().catch(() => {});
  await shot('06_map', '.st[data-sec="fdmap"]');
  report.legendRows = await page.$$eval('.chart-legend .ind-row', rs => rs.map(r => [r.querySelector('.ind-k')?.textContent, getComputedStyle(r.querySelector('.ind-k') || r).color, getComputedStyle(r).fontSize]));
  report.overflow = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
} catch (e) { errors.push('harness: ' + e.message) }
report.errors = errors;
console.log(JSON.stringify(report, null, 1));
await browser.close(); server.close();
