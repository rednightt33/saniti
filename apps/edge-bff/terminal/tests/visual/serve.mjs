/* A static server for the 1:1 check: /ref/ is the reference page (the user's file, never committed; path in
   TERMINAL_REFERENCE_HTML) and /terminal-app/ the built TypeScript page (../../../static/terminal-app). */
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';

const BUILD = fileURLToPath(new URL('../../../static/terminal-app/', import.meta.url));
const TYPES = { '.html':'text/html', '.js':'text/javascript', '.css':'text/css', '.json':'application/json', '.svg':'image/svg+xml' };

export function serve(reference) {
  const server = createServer(async (req, res) => {
    const path = decodeURIComponent(new URL(req.url, 'http://x').pathname);
    let file = null;
    if (path === '/ref/') file = reference;
    else if (path.startsWith('/terminal-app/')) {
      const rel = normalize(path.slice('/terminal-app/'.length) || 'index.html');
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
