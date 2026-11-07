/* A fake terminal-api and bucket for the screener-worker's tests (plain JS, no dependency), modelled on
   apps/backtest-worker/tests/fake-terminal.mjs, whose publisher-format encoders it imports (the documents are byte for
   byte Python's json.dumps; gzip level 9, mtime 0): node:http answers the routes the worker uses with the shapes of
   apps/terminal-api/app/main.py and serves the files as presigned bucket URLs.

   startFakeTerminal({ key, publication, ttl, processes }) -> { url, requests, fault(match, statuses), publish(p),
   state(n), close() }:
     publication  { finished_at, price_through?, broker_through?, prices: {TICKER: rows[]}, ref: [[ticker, name, type,
                  sector, industry], ...], actions?: rows[], files?: {name: {body?, sha256?, bytes?}} }: the price and
                  actions xsection files (publisher.py xsection_price_doc / xsection_actions_doc), the per-ticker yearly
                  files /manifest names (their rows and last dates), the reference file. files overrides what the index
                  claims for a file (a corrupt sha256, a size) or its bytes (a truncated body)
     processes    terminal-api runs two processes that re-read state.json each on its own (rack-api log): stateFor(req)
                  picks which publication answers; the default serves the latest to every route
   Routes: GET /api/terminal/v1/state; POST /api/terminal/v1/xsection {names} (proxy key only); GET
   /api/terminal/v1/manifest/{ticker}; GET /api/terminal/v1/reference/tickers; GET /bucket/v1/<key> (presigned).
   requests: every request seen ({ method, path, headers, body }); fault(match, statuses): the next requests whose path
   starts with `match` (or for which match(req) is true) answer these statuses ('reset' drops the connection);
   publish(p): a new publication (new index, objects kept as the publisher keeps the previous index's).
   EXEC-SCREENER-FLOW-CANDLES P4 (verification/screener/P4_BROKER_DAYS.md section 1): publication.broker = {date: rows}
   adds one broker day file per date (index name broker-YYYY-MM-DD, as_of the date) in the publisher's format
   (xsectionBrokerDoc, encodeBrokerDay); files[name].doc replaces a file's document (a broken one). /xsection refuses
   more than 16 names, as terminal-api's MAX_XSECTION_NAMES does. */
import crypto from 'node:crypto';
import http from 'node:http';
import zlib from 'node:zlib';
import { encode, priceYears, pricePack, tickersRef } from '../../backtest-worker/tests/fake-terminal.mjs';

export const PRICE_XSECTION_COLUMNS = ['t', 'd', 'o', 'h', 'l', 'c', 'v'];
export const ACTION_COLUMNS = ['t', 'd', 'type', 'ratio_old', 'ratio_new', 'amount_per_share', 'currency'];
const sha = b => crypto.createHash('sha256').update(b).digest('hex');

/** The `price` xsection document (publisher.py xsection_price_doc): prices = {TICKER: [[d, o, h, l, c, v], ...]}. */
export function xsectionPriceDoc(prices) {
  const columns = Object.fromEntries(PRICE_XSECTION_COLUMNS.map(c => [c, []])), tickers = [];
  for (const t of Object.keys(prices).sort()) {
    const rows = prices[t];
    columns.t.push(...rows.map(() => t));
    PRICE_XSECTION_COLUMNS.slice(1).forEach((c, i) => columns[c].push(...rows.map(r => r[i])));
    tickers.push({ t, pack_sha256: encode(pricePack(t, rows)).sha256, first: rows[0][0], last: rows[rows.length - 1][0], rows: rows.length });
  }
  return { schema_version: 1, dataset: 'xsection', name: 'price', units: { o: 'IDR per share (index points for an index)', v: 'shares' },
    means: { t: 'ticker; rows ordered by ticker (code point order), then date' }, columns: PRICE_XSECTION_COLUMNS, ...columns, tickers };
}
/** The `actions` xsection document (publisher.py xsection_actions_doc): rows = [[t, d, type, ratio_old, ratio_new, amount, currency], ...]. */
export function xsectionActionsDoc(rows) {
  return { schema_version: 1, dataset: 'xsection', name: 'actions', units: { ratio_old: 'shares', ratio_new: 'shares', amount_per_share: 'currency per share' },
    columns: ACTION_COLUMNS, ...Object.fromEntries(ACTION_COLUMNS.map((c, i) => [c, rows.map(r => r[i])])) };
}

/* ---- P4: broker day files ----------------------------------------------------------------------------------- */
export const BROKER_DAY_COLUMNS = ['b', 'i', 'm', 'bv', 'sv', 'bl', 'sl', 'bf', 'sf'];
export const BROKER_INVESTOR_TYPES = ['Domestic', 'Foreign'];
export const BROKER_BOARDS = ['Regular', 'Nego', 'Tunai'];
const cp = (a, b) => a < b ? -1 : a > b ? 1 : 0;
/** One broker day file (P4 section 1, publisher.py): rows = [[t, broker, investor_type, board, bv, sv, bl, sl, bf, sf,
    gap?], ...] in any order; the file orders them by ticker, broker, investor_type, market_board (the primary key's
    text order), indexes broker, investor type and board into its tables and adds tickers, gap and check. */
export function xsectionBrokerDoc(date, rows) {
  const sorted = [...rows].sort((x, y) => cp(x[0], y[0]) || cp(x[1], y[1]) || cp(x[2], y[2]) || cp(x[3], y[3]));
  const brokers = [...new Set(sorted.map(r => r[1]))].sort(cp);
  const tickers = [];
  for (const r of sorted) { const last = tickers[tickers.length - 1]; if (last && last.t === r[0]) last.rows++; else tickers.push({ t: r[0], rows: 1 }) }
  const col = k => sorted.map(r => r[k]);
  const gap = [...new Set(sorted.filter(r => r[10]).map(r => JSON.stringify([r[0], r[3]])))].sort(cp).map(g => JSON.parse(g));
  return {
    schema_version: 1, dataset: 'xsection', name: `broker-${date}`, date, source: 'Feature_05_Foreign_Domestic_Broker_Detail',
    units: { bv: 'IDR', sv: 'IDR', bl: 'lots (100 shares; odd lots as fractions)', sl: 'lots', bf: 'buy transactions', sf: 'sell transactions' },
    means: { b: 'index into brokers', i: 'index into investor_types (the source investor identity, not broker domicile)', m: 'index into boards' },
    brokers, investor_types: BROKER_INVESTOR_TYPES, boards: BROKER_BOARDS, tickers, columns: BROKER_DAY_COLUMNS,
    b: sorted.map(r => brokers.indexOf(r[1])), i: sorted.map(r => BROKER_INVESTOR_TYPES.indexOf(r[2])), m: sorted.map(r => BROKER_BOARDS.indexOf(r[3])),
    bv: col(4), sv: col(5), bl: col(6), sl: col(7), bf: col(8), sf: col(9), gap,
    check: { rows: sorted.length, bv: col(4).reduce((a, x) => a + x, 0), sv: col(5).reduce((a, x) => a + x, 0) },
  };
}
/** The publisher's encode of a broker day (P4 section 1): compact JSON, a whole number as an integer (1234, not 1234.0),
    the check sums as floats; gzip level 9, mtime 0, OS byte 255 (as the backtest fake's encode). */
export function encodeBrokerDay(doc) {
  const num = x => x === null ? 'null' : String(x);                    // JS writes 1234 for 1234.0, as the publisher does
  const flt = x => Number.isInteger(x) ? `${x}.0` : String(x);
  const json = v => JSON.stringify(v);
  const parts = Object.entries(doc).map(([k, v]) => {
    if (BROKER_DAY_COLUMNS.includes(k)) return `${json(k)}:[${v.map(num).join(',')}]`;
    if (k === 'check') return `${json(k)}:{"rows":${v.rows},"bv":${flt(v.bv)},"sv":${flt(v.sv)}}`;
    return `${json(k)}:${json(v)}`;
  });
  const body = zlib.gzipSync(Buffer.from(`{${parts.join(',')}}`), { level: 9 });
  body[9] = 255;
  return { body, sha256: sha(body) };
}
/** Deterministic broker rows of one date for `tickers`: a few brokers per ticker on both investor types and the
    Regular board (Nego now and then), whole and fractional lots, a null frequency now and then, a gap on one row. */
export function brokerRowsOf(seed, date, tickers, { brokers = ['AK', 'BK', 'CC', 'DX', 'YP', 'ZP'] } = {}) {
  let s = (seed * 7919 + Number(date.replace(/-/g, '')) % 104729) >>> 0 || 1;
  const rnd = () => { s ^= s << 13; s >>>= 0; s ^= s >>> 17; s ^= s << 5; s >>>= 0; return s / 4294967296 };
  const rows = [];
  for (const t of tickers) {
    const n = 2 + Math.floor(rnd() * 3);
    const picked = [...brokers].sort(() => rnd() - 0.5).slice(0, n).sort();
    for (const b of picked) for (const i of BROKER_INVESTOR_TYPES) {
      const boards = rnd() < 0.2 ? ['Nego', 'Regular'] : ['Regular'];
      for (const m of boards) {
        const bl = rnd() < 0.3 ? Math.round(rnd() * 1e4) / 100 : Math.round(rnd() * 1e4), sl = Math.round(rnd() * 1e4);
        rows.push([t, b, i, m, Math.round(bl * 100 * (500 + rnd() * 100)), Math.round(sl * 100 * (500 + rnd() * 100)), bl, sl,
          rnd() < 0.05 ? null : Math.round(rnd() * 300), rnd() < 0.05 ? null : Math.round(rnd() * 300), rnd() < 0.02]);
      }
    }
  }
  return rows;
}

/** A deterministic random walk of n sessions ending on `last` (weekdays only), [[d, o, h, l, c, v], ...]. index: no volume. */
export function walk(seed, n, { last = '2026-10-27', start = 1000, index = false } = {}) {
  let s = seed >>> 0 || 1;
  const rnd = () => { s ^= s << 13; s >>>= 0; s ^= s >>> 17; s ^= s << 5; s >>>= 0; return s / 4294967296 };
  const days = [];
  const d = new Date(`${last}T00:00:00Z`);
  while (days.length < n) { const w = d.getUTCDay(); if (w !== 0 && w !== 6) days.push(d.toISOString().slice(0, 10)); d.setUTCDate(d.getUTCDate() - 1) }
  days.reverse();
  let c = start;
  return days.map(day => {
    const o = c, ch = (rnd() - 0.48) * 0.04;
    c = Math.max(1, Math.round(o * (1 + ch)));
    const h = Math.max(o, c) + Math.round(rnd() * 5), l = Math.max(1, Math.min(o, c) - Math.round(rnd() * 5));
    return [day, o, h, l, c, index ? null : Math.round(1e5 + rnd() * 1e6)];
  });
}

const send = (res, status, body, type = 'application/json') => {
  const b = Buffer.isBuffer(body) ? body : Buffer.from(typeof body === 'string' ? body : JSON.stringify(body));
  res.writeHead(status, { 'content-type': type, 'content-length': b.length }); res.end(b);
};
const readBody = req => new Promise((ok, no) => { const parts = []; req.on('data', c => parts.push(c)); req.on('end', () => ok(Buffer.concat(parts))); req.on('error', no) });

export async function startFakeTerminal({ key, publication, ttl = 120, delayMs = 0 }) {
  const objects = new Map();                     // bucket key -> { body, status? }
  const pubs = [];                               // every publication, oldest first: { state, manifests, refKey }
  let base = '';
  const presign = k => `${base}/bucket/${k}?X-Amz-Date=${Date.now()}&X-Amz-Expires=${ttl}&X-Amz-Signature=${sha(k)}`;

  function build(p) {
    const files = {};
    const put = (name, doc) => {
      const real = encode(doc), o = p.files?.[name] ?? {};
      const body = o.body ? Buffer.from(o.body) : real.body;
      const k = `v1/xsection/${name}.${real.sha256.slice(0, 16)}.json.gz`;
      objects.set(k, { body, status: o.status });
      files[name] = { key: k, sha256: o.sha256 ?? real.sha256, bytes: o.bytes ?? real.body.length, rows: (doc.t || []).length, as_of: null };
    };
    put('price', xsectionPriceDoc(p.prices));
    put('actions', xsectionActionsDoc(p.actions ?? []));
    // P4: one broker day file per date, under content keys as the publisher writes them
    for (const [date, rows] of Object.entries(p.broker ?? {})) {
      const name = `broker-${date}`, o = p.files?.[name] ?? {}, doc = o.doc ?? xsectionBrokerDoc(date, rows), real = encodeBrokerDay(doc);
      const body = o.body ? Buffer.from(o.body) : real.body;
      const k = `v1/xsection/${name}.${real.sha256.slice(0, 16)}.json.gz`;
      objects.set(k, { body, status: o.status });
      files[name] = { key: k, sha256: o.sha256 ?? real.sha256, bytes: o.bytes ?? real.body.length, rows: doc.check?.rows ?? 0, as_of: date };
    }
    for (const [name, o] of Object.entries(p.files ?? {})) if (!files[name] && o.index) files[name] = o.index;
    const manifests = {};
    for (const [t, rows] of Object.entries(p.prices)) {
      const years = {};
      for (const y of priceYears(t, rows)) {
        const e = encode(y.doc), d = y.doc.d;
        years[String(y.year)] = { bytes: e.body.length, rows: d.length, first: d[0], last: d[d.length - 1], sha256: e.sha256 };
      }
      manifests[t] = { ticker: t, window: null, generated_at: p.finished_at, datasets: { price: { data_through: rows[rows.length - 1][0], years: p.manifests?.[t] ?? years } } };
    }
    const refKey = `ref/tickers.${pubs.length}.json.gz`;
    objects.set(refKey, { body: encode(tickersRef(p.ref)).body });
    const state = { finished_at: p.finished_at, price_through: p.price_through ?? Object.values(p.prices).reduce((m, r) => r[r.length - 1][0] > m ? r[r.length - 1][0] : m, ''),
      broker_through: p.broker_through ?? null, broker_behind_sessions: p.broker_behind_sessions ?? 0, xsection: p.noIndex ? null : files };
    return { state, manifests, refKey };
  }
  pubs.push(build(publication));
  const latest = () => pubs[pubs.length - 1];
  const fake = {
    requests: [], faults: [],
    /** which publication a route answers from (skew tests replace it) */
    stateFor: (_req) => latest(),
  };

  const server = http.createServer(async (req, res) => {
    const u = new URL(req.url, 'http://fake'), entry = { method: req.method, path: u.pathname, headers: { ...req.headers }, body: '' };
    fake.requests.push(entry);
    try {
      const body = await readBody(req);
      entry.body = body.toString();
      const fault = fake.faults.find(f => f.queue.length && (typeof f.match === 'function' ? f.match(entry) : u.pathname.startsWith(f.match)));
      if (fault) {
        const status = fault.queue.shift();
        if (status === 'reset') { req.socket.destroy(); return }
        return send(res, status, { error: status === 429 ? 'quota_exceeded' : 'fault', message: `fake fault ${status}` });
      }
      if (delayMs) await new Promise(r => setTimeout(r, delayMs));
      if (u.pathname.startsWith('/bucket/')) {
        if (req.headers['x-terminal-proxy-key']) return send(res, 400, '<Error><Code>InvalidArgument</Code></Error>', 'application/xml');
        const o = objects.get(u.pathname.slice('/bucket/'.length));
        if (!o) return send(res, 404, '<Error><Code>NoSuchKey</Code></Error>', 'application/xml');
        if (o.status) return send(res, o.status, '<Error><Code>Fault</Code></Error>', 'application/xml');
        return send(res, 200, o.body, 'application/gzip');
      }
      if (!u.pathname.startsWith('/api/terminal/v1/')) return send(res, 404, { detail: 'Not Found' });
      const given = req.headers['x-terminal-proxy-key'];
      if (given !== key) return send(res, 401, { error: 'proxy_key_rejected', message: 'The gateway key is not valid.' });
      const pub = fake.stateFor(entry);
      if (req.method === 'GET' && u.pathname === '/api/terminal/v1/state') return send(res, 200, pub.state);
      if (req.method === 'POST' && u.pathname === '/api/terminal/v1/xsection') {
        let names;
        try { names = JSON.parse(entry.body || '{}').names } catch { return send(res, 400, { error: 'invalid_request' }) }
        if (!Array.isArray(names) || !names.length || names.length > 16) return send(res, 422, { error: 'invalid_request', message: `names: 1 to 16 names (MAX_XSECTION_NAMES), not ${names?.length}` });
        const index = pub.state.xsection || {};
        const missing = (names || []).filter(n => !index[n]);
        if (missing.length) return send(res, 404, { error: 'xsection_not_published', message: `No cross-sectional file ${missing}` });
        return send(res, 200, { finished_at: pub.state.finished_at, expires_in_seconds: ttl, encoding: 'gzip json',
          files: [...new Set(names)].map(n => ({ name: n, url: presign(index[n].key), sha256: index[n].sha256, bytes: index[n].bytes, rows: index[n].rows, as_of: index[n].as_of })) });
      }
      const man = /^\/api\/terminal\/v1\/manifest\/([^/]+)$/.exec(u.pathname);
      if (req.method === 'GET' && man) {
        const m = pub.manifests[decodeURIComponent(man[1])];
        return m ? send(res, 200, m) : send(res, 404, { error: 'unknown_ticker', message: 'No published data.' });
      }
      if (req.method === 'GET' && u.pathname === '/api/terminal/v1/reference/tickers') return send(res, 200, { url: presign(pub.refKey), expires_in_seconds: ttl, encoding: 'gzip json' });
      return send(res, 404, { detail: 'Not Found' });
    } catch (e) { send(res, 500, { error: 'fake_error', message: String(e) }) }
  });
  await new Promise(ok => server.listen(0, '127.0.0.1', ok));
  base = `http://127.0.0.1:${server.address().port}`;
  return Object.assign(fake, {
    url: base, objects,
    fault(match, statuses) { fake.faults.push({ match, queue: [...statuses] }) },
    publish(p) { pubs.push(build(p)); return latest() },
    publication: n => pubs[n],
    latest,
    close: () => new Promise(ok => { server.closeAllConnections?.(); server.close(() => ok()) }),
  });
}

/** A small universe: `n` stocks plus IHSG, `bars` sessions each, sector and industry, deterministic. */
export function universe(n, bars, { last = '2026-10-27' } = {}) {
  const prices = { IHSG: walk(7, bars, { last, start: 7000, index: true }) }, ref = [['IHSG', 'Composite', 'index', 'Undefined', 'Undefined']];
  const sectors = ['Financials', 'Energy', 'Industrials'];
  for (let k = 0; k < n; k++) {
    const t = `T${String(k).padStart(3, '0')}`;
    prices[t] = walk(100 + k, bars, { last, start: 200 + 50 * k });
    ref.push([t, `Ticker ${k}`, 'stock', sectors[k % 3], `${sectors[k % 3]} industry`]);
  }
  return { prices, ref };
}
