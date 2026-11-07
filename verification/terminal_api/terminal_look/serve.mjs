/* The stand-in for EDGE, terminal-api and the bucket that serves the built Terminal page with exported rows (shared by
   look_check2.mjs; look_check.mjs keeps its own copy). serve(DATA, TICKER) -> { origin, close } */
import { createServer } from 'node:http';
import { createHash } from 'node:crypto';
import { gzipSync } from 'node:zlib';
import { readFile } from 'node:fs/promises';
import { existsSync, readFileSync } from 'node:fs';
import { extname, join, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';

export async function serve(DATA, TICKER) {
  const brokerCodes = [...new Set((JSON.parse(existsSync(join(DATA, `bk_${TICKER}.json`)) ? readFileSync(join(DATA, `bk_${TICKER}.json`), 'utf8') : '{"rows":[]}').rows).map(r => r[1]))].sort();
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

  const REFS = { tickers:TICKERS, brokers:gz({ columns:['code', 'name', 'type'], code:brokerCodes, name:brokerCodes, type:brokerCodes.map(() => 'Domestic') }),
    logos:gz({ columns:['ticker', 'sha256'], ticker:[], sha256:[] }) };

  const files = new Map(); let origin = '';
  const LAYOUTS = { rows:new Map(), calls:[], tick:0 }, PRESETS = { rows:new Map(), calls:[], tick:0 }, DRAWINGS = { rows:new Map(), calls:[], down:false };
  const server = createServer(async (req, res) => {
    const url = new URL(req.url, 'http://x'), path = decodeURIComponent(url.pathname);
    const json = (o, status = 200) => { res.writeHead(status, { 'Content-Type':'application/json' }); res.end(JSON.stringify(o)) };
    if (path === '/api/v1/auth/session') return json({ csrf_token:'t', login:'look' });
    /* EXEC-TERMINAL-LAYOUTS: an in-memory stand-in of edge-bff's /api/v1/terminal/layouts (apps/edge-bff/app/layouts.py):
       revision, conflicts, names unique, opened order; writes need the CSRF header */
    /* EXEC-DRAW-PANES: an in-memory stand-in of /api/v1/terminal/drawings (apps/edge-bff/app/drawings.py): sets per
       ticker and place, revisions, the ticker and set rules; DRAWINGS.down = true answers 503 DRAWINGS_NOT_READY */
    const drw = path.match(/^\/api\/v1\/terminal\/drawings(?:\/([^/]+)\/([^/]+))?$/);
    if (drw) {
      const [, t, sid] = drw, err = (code, status, extra = {}) => json({ error:{ code, message:code, ...extra } }, status);
      if (DRAWINGS.down) return err('DRAWINGS_NOT_READY', 503);
      if (req.method !== 'GET' && req.headers['x-csrf-token'] !== 't') return err('CSRF', 403);
      let body = {}; if (req.method === 'PUT') { let x = ''; for await (const c of req) x += c; body = JSON.parse(x || '{}') }
      DRAWINGS.calls.push(`${req.method} ${t || url.searchParams.get('ticker')}/${sid || ''}`);
      if (!t) { const tk = url.searchParams.get('ticker') || ''; if (!/^[A-Z0-9]{1,12}$/.test(tk)) return err('INVALID_INPUT', 422, { field:'ticker' });
        return json({ sets:[...DRAWINGS.rows.values()].filter(r => r.ticker === tk).sort((a, b) => a.set_id < b.set_id ? -1 : 1), limits:{ set_bytes:100000, sets:5000 } }) }
      if (!/^[A-Z0-9]{1,12}$/.test(t)) return err('INVALID_INPUT', 422, { field:'ticker' });
      if (!/^(chart|flow|pane_[0-9a-f]{16})$/.test(sid)) return err('INVALID_INPUT', 422, { field:'set_id' });
      const key = `${t}/${sid}`, row = DRAWINGS.rows.get(key), now = new Date().toISOString();
      if (req.method === 'DELETE') { if (!row) return err('NOT_FOUND', 404); DRAWINGS.rows.delete(key); res.writeHead(204); return res.end() }
      if (!Array.isArray(body.drawings)) return err('INVALID_INPUT', 422, { field:'drawings' });
      if (JSON.stringify(body.drawings).length > 100000) return err('LIMIT_EXCEEDED', 422, { field:'drawings', message:'The drawings of one place are at most 100,000 bytes.' });
      if (body.revision == null) { if (row) return err('REVISION_CONFLICT', 409, { details:{ revision:row.revision } });
        const r = { ticker:t, set_id:sid, drawings:body.drawings, schema_version:1, revision:1, created_at:now, updated_at:now }; DRAWINGS.rows.set(key, r); return json(r, 201) }
      if (!row) return err('NOT_FOUND', 404);
      if (row.revision !== body.revision) return err('REVISION_CONFLICT', 409, { details:{ revision:row.revision } });
      Object.assign(row, { drawings:body.drawings, revision:row.revision + 1, updated_at:now }); return json(row);
    }
    /* EXEC-IND-PRESETS: an in-memory stand-in of /api/v1/terminal/presets (apps/edge-bff/app/presets.py) */
    const pre = path.match(/^\/api\/v1\/terminal\/presets(?:\/(ipr_[0-9a-f]{32}))?$/);
    if (pre) {
      const id = pre[1], err = (code, status, extra = {}) => json({ error:{ code, message:code, ...extra } }, status);
      if (req.method !== 'GET' && req.headers['x-csrf-token'] !== 't') return err('CSRF', 403);
      let body = {}; if (req.method === 'PUT' || req.method === 'PATCH') { let t = ''; for await (const c of req) t += c; body = JSON.parse(t || '{}') }
      const now = new Date(Date.now() + PRESETS.tick++).toISOString(), row = id && PRESETS.rows.get(id);
      PRESETS.calls.push(`${req.method} ${id || ''}`.trim());
      if (!id) return json({ presets:[...PRESETS.rows.values()].sort((a, b) => Number(b.favorite) - Number(a.favorite) || (a.used_at < b.used_at ? 1 : -1)), limit:100 });
      if (req.method === 'DELETE') { if (!row) return err('NOT_FOUND', 404); PRESETS.rows.delete(id); res.writeHead(204); return res.end() }
      if (req.method === 'PATCH') { if (!row) return err('NOT_FOUND', 404); if (body.favorite !== undefined) row.favorite = body.favorite; if (body.used) row.used_at = now; return json(row) }
      const name = String(body.name || '').trim();
      if (body.revision != null && row && row.revision !== body.revision) return err('REVISION_CONFLICT', 409, { details:{ revision:row.revision } });
      if ([...PRESETS.rows.values()].some(r => r.name === name && r.preset_id !== id)) return err('NAME_TAKEN', 409, { field:'name', message:'Another preset has this name: choose another name.' });
      if (body.revision == null) { if (row) return err('REVISION_CONFLICT', 409);
        const r = { preset_id:id, name, def_id:body.def_id, config:body.config, summary:body.summary || '', schema_version:1, favorite:false, revision:1, created_at:now, updated_at:now, used_at:now };
        PRESETS.rows.set(id, r); return json(r, 201) }
      if (!row) return err('NOT_FOUND', 404);
      Object.assign(row, { name, def_id:body.def_id, config:body.config, summary:body.summary || '', revision:row.revision + 1, updated_at:now, used_at:now }); return json(row);
    }
    const lay = path.match(/^\/api\/v1\/terminal\/layouts(?:\/(lay_[0-9a-f]{32}))?$/);
    if (lay) {
      const id = lay[1], meta = r => { const { state, ...m } = r; return m }, err = (code, status, extra = {}) => json({ error:{ code, message:code, ...extra } }, status);
      if (req.method !== 'GET' && req.headers['x-csrf-token'] !== 't') return err('CSRF', 403);
      let body = {}; if (req.method === 'PUT' || req.method === 'PATCH') { let t = ''; for await (const c of req) t += c; body = JSON.parse(t || '{}') }
      const now = new Date(Date.now() + LAYOUTS.tick++).toISOString(), row = id && LAYOUTS.rows.get(id);
      LAYOUTS.calls.push(`${req.method} ${id || ''}`.trim());
      if (!id) return json({ layouts:[...LAYOUTS.rows.values()].sort((a, b) => a.opened_at < b.opened_at ? 1 : -1).map(meta), limit:50 });
      if (req.method === 'GET') return row ? json(row) : err('NOT_FOUND', 404);
      if (req.method === 'DELETE') { if (!row) return err('NOT_FOUND', 404); LAYOUTS.rows.delete(id); res.writeHead(204); return res.end() }
      if (req.method === 'PATCH') { if (!row) return err('NOT_FOUND', 404); if (body.favorite !== undefined) row.favorite = body.favorite; if (body.opened) row.opened_at = now; return json(meta(row)) }
      const name = String(body.name || '').trim();
      if ([...LAYOUTS.rows.values()].some(r => r.name === name && r.layout_id !== id)) return err('NAME_TAKEN', 409, { field:'name', message:'Another layout has this name: choose another name.' });
      if (body.revision == null) { if (row) return err('REVISION_CONFLICT', 409, { details:{ revision:row.revision } });
        const r = { layout_id:id, name, summary:body.summary || '', schema_version:1, favorite:false, revision:1, created_at:now, updated_at:now, opened_at:now, state:body.state };
        LAYOUTS.rows.set(id, r); return json(r, 201) }
      if (!row) return err('NOT_FOUND', 404);
      if (row.revision !== body.revision) return err('REVISION_CONFLICT', 409, { details:{ revision:row.revision } });
      Object.assign(row, { name, state:body.state, summary:body.summary || '', revision:row.revision + 1, updated_at:now, opened_at:now }); return json(row);
    }
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

  return { origin, close:() => server.close(), layouts:LAYOUTS, presets:PRESETS, drawings:DRAWINGS };
}
