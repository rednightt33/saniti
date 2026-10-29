// (c) baseline: an empty node:http server (what an idle-but-awake per-user Node instance costs before any data)
import http from 'node:http';
const s = http.createServer((q, r) => r.end('ok'));
s.listen(0, '127.0.0.1', () => console.log(JSON.stringify({ event: 'ready', boot_ms: Math.round(performance.now()), rss_mb: Math.round(process.memoryUsage().rss / 1048576) })));
