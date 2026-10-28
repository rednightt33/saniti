/* A static server of one test build (dist-smoke or dist-fixture) at /screener-app/, with edge-bff's EDGE icons, for
   the smoke run and the visual shots. No API routes: the test builds answer from the fixture ScreenerApi. */
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';

const STATIC = fileURLToPath(new URL('../../../static/', import.meta.url));
const ICONS = ['/favicon.svg', '/favicon-32.png'];
const TYPES = { '.html':'text/html', '.js':'text/javascript', '.css':'text/css', '.json':'application/json', '.svg':'image/svg+xml', '.png':'image/png' };

export async function serve(build) {
  const root = fileURLToPath(new URL(`../../${build}/`, import.meta.url));
  const server = createServer(async (req, res) => {
    const path = decodeURIComponent(new URL(req.url, 'http://x').pathname);
    const rel = path.startsWith('/screener-app/') ? normalize(path.slice('/screener-app/'.length) || 'index.html') : null;
    try {
      if (ICONS.includes(path)) { const f = join(STATIC, path.slice(1)); res.writeHead(200, { 'Content-Type':TYPES[extname(f)] }); res.end(await readFile(f)); return }
      if (!rel || rel.startsWith('..')) throw new Error('not found');
      const f = join(root, rel);
      res.writeHead(200, { 'Content-Type':TYPES[extname(f)] || 'application/octet-stream', 'Cache-Control':'no-store' }); res.end(await readFile(f));
    } catch { res.writeHead(404); res.end('not found') }
  });
  await new Promise(ok => server.listen(0, '127.0.0.1', ok));
  return { origin:`http://127.0.0.1:${server.address().port}`, close:() => new Promise(ok => server.close(ok)) };
}
