/* HYBRID option probe: compute the 53-default snapshot ONCE, serialise its tails (Float64 values + per-entry index), and
   measure what a fresh instance would pay to LOAD it instead of computing it: bytes raw / gzip, inflate + rebuild time.
   Uses the same real path as screener_cold.mts (single thread). Writes the artifact into bench/data (scratch).
   Usage: node --experimental-strip-types --no-warnings --expose-gc --import <loader> snapshot_ship.mts <xsection.gz> <meta.json> <outdir> */
import { readFileSync, writeFileSync } from 'node:fs';
import { gzipSync, gunzipSync } from 'node:zlib';
import { inflateVerified, priceSeries } from '/home/user/saniti/apps/edge-bff/backtest/src/core/datafile.ts';
import type { Columnar } from '/home/user/saniti/apps/edge-bff/backtest/src/core/datafile.ts';
import { INDICATORS, startParams } from '/home/user/saniti/apps/edge-bff/screener/src/core/registry.ts';
import { SeriesCache, resolveIndicator, series, seriesKey, tailLength, tickerCalc } from '/home/user/saniti/apps/edge-bff/screener/src/core/metrics.ts';
import type { ResolvedIndicator, TickerBars, Tail } from '/home/user/saniti/apps/edge-bff/screener/src/core/metrics.ts';

const [file, metaPath, outDir] = process.argv.slice(2);
const OPTS = { capBudgetMs: 2000 }, TL = tailLength(130);
const meta = JSON.parse(readFileSync(metaPath, 'utf8'));
const doc = await inflateVerified(new Uint8Array(readFileSync(file)), meta, 'xsection', 200_000_000) as Columnar & Record<string, any>;
const bars: TickerBars[] = []; let at = 0;
for (const x of doc.tickers as { t: string; rows: number }[]) {
  const end = at + x.rows, sl = (c: string) => (doc[c] as unknown[]).slice(at, end);
  const ps = priceSeries(x.t, [{ schema_version: 1, dataset: 'price-pack', ticker: x.t, columns: ['d', 'o', 'h', 'l', 'c', 'v'], d: sl('d'), o: sl('o'), h: sl('h'), l: sl('l'), c: sl('c'), v: sl('v') } as any]);
  bars.push({ ticker: ps.ticker, dates: ps.dates, bars: ps.bars }); at = end;
}
const R: ResolvedIndicator[] = [];
for (const ind of INDICATORS) { const params = startParams(ind, OPTS); for (const o of ind.outputs) R.push(resolveIndicator({ kind: 'indicator', indicator: ind.id, params, output: o.key }, 'b', OPTS)) }
const versions = { price_data: 'bench', screener_engine: 'bench' };
const ctx = { versions, tailLength: TL, cache: new SeriesCache(0) };
const entries: { k: number; t: number; n: number; from: number; fv: number; lv: number; len: number }[] = [];
const chunks: Float64Array[] = [];
bars.forEach((t, ti) => { const tc = tickerCalc(t); R.forEach((r, k) => { const { tail } = series(ctx, tc, r, true); entries.push({ k, t: ti, n: tail.n, from: tail.from, fv: tail.firstValid, lv: tail.lastValid, len: tail.values.length }); chunks.push(tail.values) }) });
// artifact: one Float64 body + a JSON index (keys, tickers, per-entry ints)
const total = chunks.reduce((a, c) => a + c.length, 0), body = new Float64Array(total); let o = 0;
for (const c of chunks) { body.set(c, o); o += c.length }
const index = Buffer.from(JSON.stringify({ keys: R.map(r => r.key), tickers: bars.map(b => b.ticker), e: entries.map(e => [e.k, e.t, e.n, e.from, e.fv, e.lv, e.len]) }));
const raw = Buffer.concat([Buffer.from(new Uint32Array([index.length]).buffer), index, Buffer.from(body.buffer)]);
const sizes: Record<string, number> = { raw_bytes: raw.length, index_bytes: index.length, values: total };
const t0 = performance.now(); const gz1 = gzipSync(raw, { level: 1 }); sizes.gzip1_bytes = gz1.length; const gz1_ms = performance.now() - t0;
const t1 = performance.now(); const gz6 = gzipSync(raw, { level: 6 }); sizes.gzip6_bytes = gz6.length; const gz6_ms = performance.now() - t1;
writeFileSync(`${outDir}/snapshot_tails.bin.gz`, gz6);
// LOAD: what a fresh instance pays instead of the pre-warm (inflate + rebuild the cache entries)
const l0 = performance.now(), c0 = process.cpuUsage();
const inflated = gunzipSync(readFileSync(`${outDir}/snapshot_tails.bin.gz`));
const ilen = inflated.readUInt32LE(0), idx = JSON.parse(inflated.subarray(4, 4 + ilen).toString());
const vals = new Float64Array(inflated.buffer.slice(inflated.byteOffset + 4 + ilen, inflated.byteOffset + inflated.length));
const cache = new SeriesCache(0); let p = 0;
const keyed = idx.keys.map((k: string) => seriesKey(versions, { key: k } as any));
for (const [k, t, n, from, fv, lv, len] of idx.e) { const tail: Tail = { n, from, firstValid: fv, lastValid: lv, values: vals.subarray(p, p + len) }; p += len; cache.set(keyed[k], idx.tickers[t], tail, true) }
const load_ms = performance.now() - l0, cu = process.cpuUsage(c0);
const out = { ...sizes, gzip1_ms: Math.round(gz1_ms), gzip6_ms: Math.round(gz6_ms), load_inflate_rebuild_ms: Math.round(load_ms), load_cpu_ms: Math.round((cu.user + cu.system) / 1000), entries: idx.e.length,
  rss_mb: Math.round(process.memoryUsage().rss / 1048576) };
console.log(JSON.stringify(out));
writeFileSync(`${outDir}/../raw/snapshot_ship.json`, JSON.stringify(out, null, 1));
