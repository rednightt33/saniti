/* A static server of one test build (dist-smoke or dist-fixture) at /screener-app/, with edge-bff's EDGE icons, for
   the smoke run and the visual shots. No API routes: the test builds answer from the fixture ScreenerApi. Every answer
   carries edge-bff's own sub-app policy (apps/edge-bff/app/main.py SCREENER_CSP, read from the source so the two never
   drift), so the Chromium runs meet the production CSP: an inline script or handler, eval, or a request to another
   origin is refused and shows as a console error (EXEC-SCREENER-V21 phase C). */
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';

const STATIC = fileURLToPath(new URL('../../../static/', import.meta.url));
const ICONS = ['/favicon.svg', '/favicon-32.png'];
/** SCREENER_CSP as main.py builds it (adjacent Python string literals joined) */
export async function screenerCsp() {
  const py = await readFile(fileURLToPath(new URL('../../../app/main.py', import.meta.url)), 'utf8');
  const m = /^SCREENER_CSP = \(([\s\S]*?)\)\s*$/m.exec(py);
  if (!m) throw new Error('serve.mjs: SCREENER_CSP not found in apps/edge-bff/app/main.py');
  const csp = [...m[1].matchAll(/"([^"]*)"/g)].map(x => x[1]).join('');
  if (!/script-src 'self';/.test(csp)) throw new Error('serve.mjs: SCREENER_CSP has no script-src \'self\': ' + csp);
  return csp;
}
const TYPES = { '.html':'text/html', '.js':'text/javascript', '.css':'text/css', '.json':'application/json', '.svg':'image/svg+xml', '.png':'image/png' };

export async function serve(build) {
  const root = fileURLToPath(new URL(`../../${build}/`, import.meta.url)), csp = await screenerCsp();
  const server = createServer(async (req, res) => {
    const path = decodeURIComponent(new URL(req.url, 'http://x').pathname);
    const rel = path.startsWith('/screener-app/') ? normalize(path.slice('/screener-app/'.length) || 'index.html') : null;
    try {
      if (ICONS.includes(path)) { const f = join(STATIC, path.slice(1)); res.writeHead(200, { 'Content-Type':TYPES[extname(f)] }); res.end(await readFile(f)); return }
      if (!rel || rel.startsWith('..')) throw new Error('not found');
      const f = join(root, rel);
      res.writeHead(200, { 'Content-Type':TYPES[extname(f)] || 'application/octet-stream', 'Cache-Control':'no-store', 'Content-Security-Policy':csp }); res.end(await readFile(f));
    } catch { res.writeHead(404); res.end('not found') }
  });
  await new Promise(ok => server.listen(0, '127.0.0.1', ok));
  return { origin:`http://127.0.0.1:${server.address().port}`, csp, close:() => new Promise(ok => server.close(ok)) };
}
