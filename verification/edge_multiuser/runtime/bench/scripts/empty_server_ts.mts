// (c) baseline with the worker's runtime flags (--experimental-strip-types + the worker's loader), still no data
import http from 'node:http';
const s = http.createServer((q, r) => r.end('ok'));
s.listen(0, '127.0.0.1', () => console.log(JSON.stringify({ event: 'ready', boot_ms: Math.round(performance.now()), rss_mb: Math.round(process.memoryUsage().rss / 1048576) })));
