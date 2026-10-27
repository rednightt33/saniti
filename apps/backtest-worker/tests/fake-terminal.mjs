/* A fake terminal-api and bucket for the worker's tests (plain JS, no dependency): node:http answers the routes the
   worker uses with the shapes of apps/terminal-api/app/main.py, and serves the files as presigned bucket URLs. The
   files are built in the publisher's format (apps/terminal-publisher/publisher.py price_doc, broker_doc, events_doc,
   the packs and the reference files; `encode`: compact JSON as Python's json.dumps writes it, gzip level 9, mtime 0).

   startFakeTerminal({ key, tickers, refs, ttl, delayMs, fileDelayMs }) -> { url, close(), requests, fault(match,
   statuses), publish(ticker, t), inflight: { max }, expired }:
     key      the proxy key terminal-api accepts (x-terminal-proxy-key); a wrong one answers 401 proxy_key_rejected
     tickers  { TICKER: { generated_at?, window?, datasets: { price|broker|events: { data_through, first_year?,
              files: [{ doc | body, year?, pack?, sha256?, bytes?, missing?, status?, url? }] } } } }
              (year: a yearly file; pack: 'price' | 'broker-archive'; events: one file without year or pack;
              sha256 / bytes: what the manifest claims instead of the truth; missing: the bucket answers 404;
              status: the bucket answers that status; url: what /bundle names instead of the presigned URL)
     refs     { tickers?: doc, brokers?: doc } for GET /reference/{name}
     state    GET /state's answer (the publication: finished_at, price_through, broker_through), settable as .state; null
              answers 404, as a terminal-api without the route
     ttl      the presigned URLs' lifetime in seconds (expires_in_seconds; main.py grant: url_ttl_seconds): the bucket
              refuses a URL that reaches it later than that after its grant with S3's 403 (AccessDenied, Request has
              expired), decided when the request arrives; `expired` counts these refusals
     delayMs  every answer waits this long; fileDelayMs: a bucket answer waits this much longer (a slow download)
     GET /manifest/{ticker} answers the manifest per dataset as main.py does: data_through and the yearly files (events:
     'all'; the packs are not listed there) with bytes, rows, first, last and sha256; no URL.
     /bundle with packs: true answers the price pack instead of the yearly price files, and the broker archive plus the
     yearly broker files after its last year, as main.py does.
   requests: every request seen ({ method, path, headers, body }); fault(match, statuses): the next requests whose path
   starts with `match` (or for which match(req) is true) are answered with these statuses in turn ('reset' drops the
   connection) before the normal answer; publish(ticker, t): the ticker's files published again in the `tickers` shape
   (a publisher run: the same keys, new bytes and manifest). */
import crypto from 'node:crypto';
import http from 'node:http';
import zlib from 'node:zlib';

export const SCHEMA_VERSION = 1;
export const EVENT_COLUMNS = ['d', 'role', 'family', 'type', 'action', 'holder', 'holder_role', 'broker', 'instrument',
  'shares_change', 'pct_after', 'pct_change', 'pct_flag', 'price', 'price_estimated', 'value', 'origin', 'title', 'detail'];
// columns the publisher's SQL reads as float8 (Python floats: json.dumps writes 105.0, not 105)
const FLOAT_COLUMNS = new Set(['o', 'h', 'l', 'c', 'v', 'bv', 'sv', 'bl', 'sl', 'shares_change', 'pct_after', 'pct_change', 'price', 'value']);

/* ---- publisher documents ---------------------------------------------------------------------------------------- */
const columnar = (rows, names) => Object.fromEntries(names.map((n, i) => [n, rows.map(r => r[i])]));
/** rows: [d, o, h, l, c, v] (v null for an index) */
export const priceDoc = (ticker, year, rows) => ({
  schema_version: SCHEMA_VERSION, dataset: 'price', ticker, year,
  units: { o: 'IDR per share (index points for an index)', v: 'shares' },
  columns: ['d', 'o', 'h', 'l', 'c', 'v'], ...columnar(rows, ['d', 'o', 'h', 'l', 'c', 'v']),
});
export const pricePack = (ticker, rows) => ({ ...priceDoc(ticker, null, rows), dataset: 'price-pack' });
/** The yearly price files the publisher writes next to the pack (publish: one file per calendar year of the rows), as
    file entries; /manifest lists them, /bundle with packs: true hands out the pack instead. */
export const priceYears = (ticker, rows) => [...new Set(rows.map(r => r[0].slice(0, 4)))].sort()
  .map(y => ({ year: +y, doc: priceDoc(ticker, +y, rows.filter(r => r[0].startsWith(y))) }));
/** rows: [d, b, i, m, bv, sv, bl, sl, gap] (gap: source_balance_gap of the row) */
export const brokerDoc = (ticker, year, rows) => {
  const gaps = [...new Set(rows.filter(r => r[8]).map(r => JSON.stringify([r[0], r[3]])))].sort().map(g => JSON.parse(g));
  return {
    schema_version: SCHEMA_VERSION, dataset: 'broker', ticker, year,
    units: { bv: 'IDR', sv: 'IDR', bl: 'lots (100 shares; odd lots as fractions)', sl: 'lots' },
    investor_type: 'source investor identity (Foreign/Domestic), not broker domicile',
    columns: ['d', 'b', 'i', 'm', 'bv', 'sv', 'bl', 'sl'], ...columnar(rows.map(r => r.slice(0, 8)), ['d', 'b', 'i', 'm', 'bv', 'sv', 'bl', 'sl']), gap: gaps,
  };
};
export const brokerArchive = (ticker, rows, years) => ({ ...brokerDoc(ticker, null, rows), dataset: 'broker-archive', years });
/** rows: one value per EVENT_COLUMNS name */
export const eventsDoc = (ticker, rows) => ({
  schema_version: SCHEMA_VERSION, dataset: 'events', ticker,
  units: { shares_change: 'shares', pct_after: 'percent of shares', pct_change: 'percentage points', price: 'IDR per share', value: 'IDR' },
  format: 2,
  means: { d: 'annotation date; its meaning is in role (EX_DATE, MEETING_DATE, TRANSACTION_DATE, ...)' },
  columns: EVENT_COLUMNS, ...columnar(rows, EVENT_COLUMNS),
});
/** rows: one value per column, by default the publisher's [ticker, name, type, sector, industry] (publisher.py
    publish_refs; 'Undefined' as the table has it for no classification; readers take columns by name); a row without
    the last values has null there */
export const TICKER_COLUMNS = ['ticker', 'name', 'type', 'sector', 'industry'];
export const tickersRef = (rows, columns = TICKER_COLUMNS) => ({ schema_version: SCHEMA_VERSION, columns, ...columnar(rows, columns) });
/** rows: [code, name, type] */
export const brokersRef = rows => ({ schema_version: SCHEMA_VERSION, columns: ['code', 'name', 'type'],
  type_means: 'broker domicile (label only; the Foreign figures use investor type)', ...columnar(rows, ['code', 'name', 'type']) });

/* ---- encoding: json.dumps(doc, separators=(',', ':'), allow_nan=False) then gzip.compress(level 9, mtime 0) ------- */
function pyFloat(x) {
  if (!Number.isFinite(x)) throw new Error('allow_nan=False: no NaN or Infinity');
  if (x === 0) return Object.is(x, -0) ? '-0.0' : '0.0';
  const [mant, exp] = x.toExponential().split('e'), e = Number(exp);
  if (e < -4 || e >= 16) return `${mant}e${e < 0 ? '-' : '+'}${String(Math.abs(e)).padStart(2, '0')}`;   // Python repr
  const s = String(x);
  return s.includes('.') ? s : `${s}.0`;
}
const pyString = s => JSON.stringify(s).replace(/[\u0080-￿]/g, c => '\\u' + c.charCodeAt(0).toString(16).padStart(4, '0'));
export function pyJson(v, float = false) {
  if (v === null || v === undefined) return 'null';
  if (typeof v === 'boolean') return v ? 'true' : 'false';
  if (typeof v === 'number') { if (!Number.isFinite(v)) throw new Error('allow_nan=False'); return float ? pyFloat(v) : String(v) }
  if (typeof v === 'string') return pyString(v);
  if (Array.isArray(v)) return '[' + v.map(x => pyJson(x, float)).join(',') + ']';
  return '{' + Object.entries(v).map(([k, x]) => pyString(k) + ':' + pyJson(x, FLOAT_COLUMNS.has(k))).join(',') + '}';
}
/** A document as the publisher writes it: the JSON text is byte for byte Python's json.dumps (checked against the
    publisher's encode); the gzip stream is node:zlib's (level 9, mtime 0, header OS byte 255 as Python's), whose
    deflate bytes differ from Python's zlib build, so the sha256 is not the one the publisher would give the rows. */
export function encode(doc) {
  const body = zlib.gzipSync(Buffer.from(pyJson(doc)), { level: 9 });
  body[9] = 255;
  return { body, sha256: crypto.createHash('sha256').update(body).digest('hex') };
}

/* ---- the server ------------------------------------------------------------------------------------------------ */
const TICKER = /^[A-Z0-9]{1,12}$/;
const send = (res, status, body, type = 'application/json') => {
  const b = Buffer.isBuffer(body) ? body : Buffer.from(typeof body === 'string' ? body : JSON.stringify(body));
  res.writeHead(status, { 'content-type': type, 'content-length': b.length }); res.end(b);
};
const readBody = req => new Promise((ok, no) => { const parts = []; req.on('data', c => parts.push(c)); req.on('end', () => ok(Buffer.concat(parts))); req.on('error', no) });

/** @param {{ key: string, tickers?: Record<string, any>, refs?: Record<string, any>, ttl?: number, delayMs?: number, fileDelayMs?: number }} options */
export async function startFakeTerminal({ key, tickers: initial = {}, refs = {}, ttl = 120, delayMs = 0, fileDelayMs = 0, state = null }) {
  let publication = state;                       // GET /state (EXEC-BACKTEST-LOAD); null: 404, as an older terminal-api
  const tickers = {};                            // what is published now (publish replaces a ticker)
  const objects = new Map();                     // bucket key -> { body, status? , missing? }
  const answers = {};                            // ticker -> dataset -> [{ key, entry, file }]
  function put(ticker, t) {
    tickers[ticker] = t;
    answers[ticker] = {};
    for (const [name, ds] of Object.entries(t.datasets || {})) {
      answers[ticker][name] = (ds.files || []).map((f, k) => {
        const real = f.body ? { body: Buffer.from(f.body), sha256: crypto.createHash('sha256').update(Buffer.from(f.body)).digest('hex') } : encode(f.doc);
        const id = name === 'events' ? 'all' : f.pack ?? f.year ?? `x${k}`;
        const key = f.pack ? `pack/${ticker}/${f.pack}.json.gz` : `${name}/${ticker}/${id}.json.gz`;
        objects.set(key, { body: real.body, missing: !!f.missing, status: f.status });
        return { key, f, entry: { sha256: f.sha256 ?? real.sha256, bytes: f.bytes ?? real.body.length, rows: f.rows ?? (f.doc ? (f.doc.d || []).length : null) } };
      });
    }
  }
  for (const [ticker, t] of Object.entries(initial)) put(ticker, t);
  for (const [name, doc] of Object.entries(refs)) objects.set(`ref/${name}.json.gz`, { body: encode(doc).body });

  const requests = [], faults = [], inflight = { now: 0, max: 0 };
  let base = '', expired = 0;
  // X-Amz-Date: the grant time (the fake's, in milliseconds); a URL without one never expires
  const presign = key => `${base}/bucket/v1/${key}?X-Amz-Date=${Date.now()}&X-Amz-Expires=${ttl}&X-Amz-Signature=${crypto.createHash('sha256').update(key).digest('hex')}`;
  const lapsed = u => { const at = Number(u.searchParams.get('X-Amz-Date')), s = Number(u.searchParams.get('X-Amz-Expires')); return Number.isFinite(at) && at > 0 && Date.now() > at + s * 1000 };

  function bundle(body) {
    const extra = Object.keys(body).filter(k => !['ticker', 'datasets', 'packs'].includes(k));
    if (extra.length || typeof body.ticker !== 'string' || !TICKER.test(body.ticker))
      return [400, { error: 'invalid_request', message: 'Check the listed fields.', fields: extra.length ? extra.map(f => ({ field: f, problem: 'Extra inputs are not permitted' })) : [{ field: 'ticker', problem: 'String should match pattern' }] }];
    const t = tickers[body.ticker];
    if (!t) return [404, { error: 'unknown_ticker', message: `No published data for ${body.ticker}.` }];
    const asked = [...new Set(body.datasets ?? ['price', 'broker', 'events'])];
    const datasets = {};
    for (const name of asked) {
      const ds = t.datasets?.[name] ?? {}, all = answers[body.ticker][name] ?? [];
      let chosen = all.filter(x => x.f.year !== undefined && x.f.year !== null || name === 'events').sort((a, b) => (a.f.year ?? 0) - (b.f.year ?? 0));
      if (body.packs && name === 'price' && all.some(x => x.f.pack === 'price')) chosen = all.filter(x => x.f.pack === 'price');
      const archive = all.find(x => x.f.pack === 'broker-archive');
      if (body.packs && name === 'broker' && archive) {
        const last = (archive.f.doc?.years ?? archive.f.years ?? [0, 0])[1];
        chosen = [archive, ...chosen.filter(x => x.f.year > last)];
      }
      datasets[name] = { data_through: ds.data_through ?? null, first_year: ds.first_year ?? null,
        files: chosen.map(x => ({ year: x.f.pack ? null : name === 'events' ? null : x.f.year, url: x.f.url ?? presign(x.key), ...x.entry, ...(x.f.pack ? { pack: x.f.pack } : {}) })) };
    }
    return [200, { ticker: body.ticker, window: t.window ?? null, generated_at: t.generated_at ?? null, expires_in_seconds: ttl, encoding: 'gzip json', datasets }];
  }

  function manifest(ticker) {
    const t = tickers[ticker];
    if (!TICKER.test(ticker)) return [400, { error: 'invalid_ticker', message: 'A ticker is 1-12 capital letters or digits, for example BBCA.' }];
    if (!t) return [404, { error: 'unknown_ticker', message: `No published data for ${ticker}.` }];
    const datasets = {};
    for (const [name, ds] of Object.entries(t.datasets || {})) {
      const years = {};
      for (const x of answers[ticker][name] ?? []) {
        if (x.f.pack || (name !== 'events' && (x.f.year === undefined || x.f.year === null))) continue;
        const d = x.f.doc?.d ?? [];
        years[name === 'events' ? 'all' : String(x.f.year)] = { bytes: x.entry.bytes, rows: x.entry.rows, first: d[0] ?? null, last: d[d.length - 1] ?? null, sha256: x.entry.sha256 };
      }
      datasets[name] = { data_through: ds.data_through ?? null, years: Object.fromEntries(Object.entries(years).sort()) };
    }
    return [200, { ticker, window: t.window ?? null, generated_at: t.generated_at ?? null, datasets }];
  }

  const server = http.createServer(async (req, res) => {
    const u = new URL(req.url, 'http://fake'), entry = { method: req.method, path: u.pathname, headers: { ...req.headers }, body: '' };
    const bucket = u.pathname.startsWith('/bucket/v1/'), late = bucket && lapsed(u);
    requests.push(entry);
    inflight.now++; inflight.max = Math.max(inflight.max, inflight.now);
    res.on('close', () => { inflight.now-- });
    try {
      const body = await readBody(req);
      entry.body = body.toString();
      const fault = faults.find(f => f.queue.length && (typeof f.match === 'function' ? f.match(entry) : u.pathname.startsWith(f.match)));
      if (fault) {
        const status = fault.queue.shift();
        if (status === 'reset') { req.socket.destroy(); return }
        return send(res, status, { error: status === 429 ? 'quota_exceeded' : 'fault', message: `fake fault ${status}` });
      }
      const wait = delayMs + (bucket ? fileDelayMs : 0);
      if (wait) await new Promise(r => setTimeout(r, wait));
      if (bucket) {
        // a presigned URL is the only credential: S3 refuses a second auth mechanism, and the worker must send none
        if (req.headers.authorization || req.headers.cookie || req.headers['x-terminal-proxy-key']) return send(res, 400, '<Error><Code>InvalidArgument</Code></Error>', 'application/xml');
        if (late) { expired++; return send(res, 403, '<Error><Code>AccessDenied</Code><Message>Request has expired</Message></Error>', 'application/xml') }
        const o = objects.get(u.pathname.slice('/bucket/v1/'.length));
        if (!o || o.missing) return send(res, 404, '<Error><Code>NoSuchKey</Code></Error>', 'application/xml');
        if (o.status) return send(res, o.status, '<Error><Code>Fault</Code></Error>', 'application/xml');
        return send(res, 200, o.body, 'application/gzip');
      }
      if (!u.pathname.startsWith('/api/terminal/v1/')) return send(res, 404, { detail: 'Not Found' });
      const given = req.headers['x-terminal-proxy-key'];
      if (given === undefined) return send(res, 401, { error: 'not_signed_in', message: 'Sign in first.' });
      if (given !== key) return send(res, 401, { error: 'proxy_key_rejected', message: 'The gateway key is not valid.' });
      if (req.method === 'POST' && u.pathname === '/api/terminal/v1/bundle') {
        let parsed;
        try { parsed = JSON.parse(body.toString() || '{}') } catch { return send(res, 400, { error: 'invalid_request', message: 'Check the listed fields.', fields: [] }) }
        const [status, answer] = bundle(parsed);
        return send(res, status, answer);
      }
      if (req.method === 'GET' && u.pathname === '/api/terminal/v1/state') return publication ? send(res, 200, publication) : send(res, 404, { detail: 'Not Found' });
      const man = /^\/api\/terminal\/v1\/manifest\/([^/]+)$/.exec(u.pathname);
      if (req.method === 'GET' && man) {
        const [status, answer] = manifest(decodeURIComponent(man[1]));
        return send(res, status, answer);
      }
      const ref = /^\/api\/terminal\/v1\/reference\/([^/]+)$/.exec(u.pathname);
      if (req.method === 'GET' && ref) {
        if (!objects.has(`ref/${ref[1]}.json.gz`)) return send(res, 404, { error: 'unknown_reference', message: 'Reference files: tickers, brokers, logos.' });
        return send(res, 200, { url: presign(`ref/${ref[1]}.json.gz`), expires_in_seconds: ttl, encoding: 'gzip json' });
      }
      return send(res, 404, { detail: 'Not Found' });
    } catch (e) { send(res, 500, { error: 'fake_error', message: String(e) }) }
  });
  await new Promise(ok => server.listen(0, '127.0.0.1', ok));
  base = `http://127.0.0.1:${server.address().port}`;
  return {
    url: base, requests, inflight, get expired() { return expired },
    get state() { return publication }, set state(v) { publication = v },
    fault(match, statuses) { faults.push({ match, queue: [...statuses] }) },
    publish: put,
    close: () => new Promise(ok => { server.closeAllConnections?.(); server.close(() => ok()) }),
  };
}
