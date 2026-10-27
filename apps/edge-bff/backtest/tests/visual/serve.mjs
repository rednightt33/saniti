/* A static server for the 1:1 check: /ref/ is the reference page (the user's backtest.html, never committed; path in
   BACKTEST_REFERENCE_HTML), /backtest-app/ the fixture build of the TypeScript page (vite build --mode fixture ->
   ../../dist-fixture) and the EDGE icons the page links (edge-bff's static/, as app/main.py serves them). */
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';

const BUILD = fileURLToPath(new URL('../../dist-fixture/', import.meta.url));
const STATIC = fileURLToPath(new URL('../../../static/', import.meta.url));
const ICONS = ['/favicon.svg', '/favicon-32.png'];
const TYPES = { '.html':'text/html', '.js':'text/javascript', '.css':'text/css', '.json':'application/json', '.svg':'image/svg+xml', '.png':'image/png' };

export function serve(reference) {
  const server = createServer(async (req, res) => {
    const path = decodeURIComponent(new URL(req.url, 'http://x').pathname);
    let file = null;
    if (path === '/ref/') file = reference;
    else if (ICONS.includes(path)) file = join(STATIC, path.slice(1));
    else if (path.startsWith('/backtest-app/')) {
      const rel = normalize(path.slice('/backtest-app/'.length) || 'index.html');
      if (!rel.startsWith('..')) file = join(BUILD, rel);
    }
    try {
      if (!file) throw new Error('not found');
      const body = await readFile(file);
      res.writeHead(200, { 'Content-Type': TYPES[extname(file)] || 'application/octet-stream' }); res.end(body);
    } catch (e) { res.writeHead(404); res.end('not found') }
  });
  return new Promise(ok => server.listen(0, '127.0.0.1', () => ok({ server, origin:`http://127.0.0.1:${server.address().port}` })));
}
