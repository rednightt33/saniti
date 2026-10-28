/* Warm-decode cost of a full-universe price load through the core's real reader: read each pack from local disk,
   inflateVerified (size + sha256 + gunzip + JSON) and priceSeries, sequential and with 16 concurrent promises. */
import { readFileSync } from 'node:fs';
import { inflateVerified, priceSeries } from '/home/user/saniti/apps/edge-bff/backtest/src/core/datafile.ts';
const idx = JSON.parse(readFileSync('data/packs/index.json', 'utf8')) as Record<string, { sha256: string; bytes: number }>;
const T = Object.keys(idx);
async function one(t: string) { const raw = new Uint8Array(readFileSync(`data/packs/${t}.json.gz`)); const doc = await inflateVerified(raw, idx[t], t); return priceSeries(t, [doc]).bars.C.length }
for (const mode of ['sequential', 'concurrent16', 'sequential']) {
  const c0 = process.cpuUsage(), t0 = performance.now(); let bars = 0;
  if (mode === 'sequential') for (const t of T) bars += await one(t);
  else { let i = 0; await Promise.all(Array.from({ length: 16 }, async () => { while (i < T.length) { const n = await one(T[i++]); bars += n } })) }
  const c = process.cpuUsage(c0);
  console.log(JSON.stringify({ mode, tickers: T.length, bars, wall_ms: +(performance.now() - t0).toFixed(1), cpu_ms: +((c.user + c.system) / 1000).toFixed(1), rss_mb: Math.round(process.memoryUsage().rss / 1048576) }));
}
console.log(JSON.stringify({ peak_rss_mb: Math.round(process.resourceUsage().maxRSS / 1024) }));
