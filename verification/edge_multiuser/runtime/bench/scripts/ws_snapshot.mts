/* The data part of a cold start through the screener-worker's OWN snapshot code (apps/screener-worker/src/snapshot.ts,
   work in progress at the time of the run): inflateVerified -> buildSnapshot (priceSeries per ticker into
   SharedArrayBuffer columns, universe rows, the pinned series list: 53 x start params + the presets' references) ->
   prewarmChunk over every ticker on ONE thread -> snapshotDigest. The xsection file of this bench is relabelled
   dataset 'xsection' in memory (the publisher's label in the WIP code); actions empty; reference rows from the data.
   Usage: node --experimental-strip-types --no-warnings --expose-gc --import <loader> ws_snapshot.mts <xsection.gz> <meta.json> */
import { readFileSync } from 'node:fs';
import { inflateVerified } from '/home/user/saniti/apps/edge-bff/backtest/src/core/datafile.ts';
import { buildSnapshot, prewarmChunk, snapshotDigest } from '/home/user/saniti/apps/screener-worker/src/snapshot.ts';
import { definitionRefs, loadPresets } from '/home/user/saniti/apps/screener-worker/src/catalog.ts';

const BOOT_MS = performance.now();
const [file, metaPath] = process.argv.slice(2);
const mb = (b: number) => Math.round(b / 1048576);
const cpu = () => { const c = process.cpuUsage(); return (c.user + c.system) / 1000 };
const st: Record<string, unknown> = { boot_ms: Math.round(BOOT_MS) };
const stage = async <T>(n: string, f: () => T | Promise<T>) => { const c0 = cpu(), t0 = performance.now(); const r = await f(); st[n] = { wall_ms: Math.round(performance.now() - t0), cpu_ms: Math.round(cpu() - c0), rss_mb: mb(process.memoryUsage().rss) }; return r };
const meta = JSON.parse(readFileSync(metaPath, 'utf8'));
let raw: Uint8Array | null = new Uint8Array(readFileSync(file));
let price: any = await stage('inflate_verify_parse', () => inflateVerified(raw!, meta, 'xsection price', 200_000_000));
raw = null; price.dataset = 'xsection';
const ref = { groupings: ['sector', 'industry'], tickers: (price.tickers as { t: string }[]).map(x => ({ ticker: x.t, name: x.t, type: x.t === 'IHSG' ? 'index' : 'stock', groups: { sector: 'Sector B', industry: 'Industry B' } })) };
const actions = { schema_version: 1, columns: ['t', 'd', 'type', 'ratio_old', 'ratio_new'], t: [], d: [], type: [], ratio_old: [], ratio_new: [] };
const presets = loadPresets() ?? [];
const extra = presets.flatMap((p: any) => definitionRefs(p.definition ?? p));
const built = await stage('buildSnapshot', () => buildSnapshot({ price, actions: actions as any, ref: ref as any,
  state: { finished_at: '2026-10-27T13:03:00Z', price_through: '2026-10-27', broker_through: '2026-10-27', broker_behind_sessions: 0, xsection: null },
  engine: { screener_engine: 'bench', registry: 'bench', screener_registry: 'bench' }, tailLength: 131, capBudgetMs: 2000, extra }));
price = null; (globalThis as any).gc?.();
const T = built.desc.tickers.length;
const pw = await stage('prewarm_all_one_thread', () => prewarmChunk(built.desc, 0, T, 2000));
const digest = await stage('digest', () => snapshotDigest(built.desc));
(globalThis as any).gc?.();
console.log(JSON.stringify({ event: 'ready', ready_ms: Math.round(performance.now()), ...st, presets: presets.length, extra_refs: extra.length, series: built.stats.series, skipped: built.stats.skipped.length,
  tickers: T, stocks: built.stats.stocks, bars: built.stats.bars, tails_mb: mb(built.desc.tails.byteLength), prewarm_series: pw.series, digest: (digest as string).slice(0, 16),
  rss_mb: mb(process.memoryUsage().rss), heap_mb: mb(process.memoryUsage().heapUsed), peak_rss_mb: Math.round(process.resourceUsage().maxRSS / 1024), total_cpu_ms: Math.round(cpu()) }));
