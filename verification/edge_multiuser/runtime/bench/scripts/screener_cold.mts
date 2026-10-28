/* One fresh screener instance, data part of a cold start (download excluded), on the real full history and the real code:
   read the downloaded xsection bytes from disk -> inflateVerified (size + sha256 + gunzip + JSON + column check) ->
   slice per ticker into a pack-shaped document -> priceSeries (the Terminal/Backtest row rules) -> dataVersion ->
   pre-warm every indicator of the screener registry at its start configuration (registry.ts startParams, 53 indicators,
   every output) through THE series path (metrics.ts series(..., prewarm = true)) with a SeriesCache, tails of
   tailLength(130). Then "serve": a default-only screen (lookups), a 3-condition custom screen (RSI(7) < 30,
   close > SMA(75), MACD default crosses above signal within 4 bars: two dynamic series + one pre-warmed), the same
   custom screen again (LRU hit). Prints JSON lines; the parent harness (run_screener.mjs) samples RSS from /proc.
   Usage: node --experimental-strip-types --no-warnings --expose-gc --import <loader> screener_cold.mts <xsection.gz> <meta.json> [--threads K]
   Read-only: imports the repository's modules, writes nothing. */
import { readFileSync } from 'node:fs';
import { Worker, isMainThread, parentPort, workerData } from 'node:worker_threads';
import { inflateVerified, priceSeries, dataVersion } from '/home/user/saniti/apps/edge-bff/backtest/src/core/datafile.ts';
import type { Columnar } from '/home/user/saniti/apps/edge-bff/backtest/src/core/datafile.ts';
import { INDICATORS, startParams } from '/home/user/saniti/apps/edge-bff/screener/src/core/registry.ts';
import { SeriesCache, resolveIndicator, series, seriesKey, tailLength, tickerCalc } from '/home/user/saniti/apps/edge-bff/screener/src/core/metrics.ts';
import type { ResolvedIndicator, SeriesContext, TickerBars, Tail } from '/home/user/saniti/apps/edge-bff/screener/src/core/metrics.ts';

const BOOT_MS = performance.now();                       // node bootstrap + loader + module graph (imports run first)
const OPTS = { capBudgetMs: 2000 };                       // the core tests' budget (tests/fixture/api.ts)
const WITHIN_MAX = 130;                                   // report 8.9 provisional within_max (builder.ts fallback)
const gc = (globalThis as any).gc as (() => void) | undefined;
const mb = (b: number) => Math.round(b / 1048576);
const mem = () => { const m = process.memoryUsage(); return { rss_mb: mb(m.rss), heap_mb: mb(m.heapUsed), ext_mb: mb(m.external), ab_mb: mb(m.arrayBuffers) } };
const cpu = () => { const c = process.cpuUsage(); return (c.user + c.system) / 1000 };
const say = (o: Record<string, unknown>) => console.log(JSON.stringify(o));

/** Every (indicator, output) of the registry at its start configuration, resolved once. */
function resolvedDefaults(): ResolvedIndicator[] {
  const out: ResolvedIndicator[] = [];
  for (const ind of INDICATORS) {
    const params = startParams(ind, OPTS);
    for (const o of ind.outputs) out.push(resolveIndicator({ kind: 'indicator', indicator: ind.id, params, output: o.key }, 'bench', OPTS));
  }
  return out;
}

interface WireTail { key: string; ticker: string; n: number; from: number; firstValid: number; lastValid: number; values: Float64Array }
/** Pre-warm a set of tickers into ctx; returns counts. */
function prewarm(ctx: SeriesContext, list: TickerBars[], R: ResolvedIndicator[], wire?: WireTail[]) {
  let tails = 0, errors = 0; const errCodes: Record<string, number> = {};
  for (const t of list) {
    const tc = tickerCalc(t);
    for (const r of R) {
      try {
        const { tail } = series(ctx, tc, r, true); tails++;
        if (wire) wire.push({ key: r.key, ticker: t.ticker, n: tail.n, from: tail.from, firstValid: tail.firstValid, lastValid: tail.lastValid, values: tail.values });
      } catch (e) { errors++; const c = (e as any)?.code ?? (e as Error)?.name; errCodes[c] = (errCodes[c] ?? 0) + 1 }
    }
  }
  return { tails, errors, errCodes };
}

if (!isMainThread) {
  /* ---- a pre-warm thread: its share of the tickers, tails sent back (transferred) ---- */
  const { list, versions } = workerData as { list: TickerBars[]; versions: { price_data: string; screener_engine: string } };
  const ctx: SeriesContext = { versions, tailLength: tailLength(WITHIN_MAX), cache: new SeriesCache(0) };
  const c0 = cpu(), t0 = performance.now(), wire: WireTail[] = [];
  const r = prewarm(ctx, list, resolvedDefaults(), wire);
  parentPort!.postMessage({ wire, ...r, wall_ms: performance.now() - t0, cpu_ms: cpu() - c0 }, wire.map(w => w.values.buffer as ArrayBuffer));
} else {
  const [file, metaPath, ...rest] = process.argv.slice(2);
  const K = rest.includes('--threads') ? Number(rest[rest.indexOf('--threads') + 1]) : 1;
  const meta = JSON.parse(readFileSync(metaPath, 'utf8')) as { sha256: string; bytes: number };
  const st: Record<string, unknown> = { boot_ms: +BOOT_MS.toFixed(0), threads: K };
  const stage = async <T>(name: string, f: () => T | Promise<T>): Promise<T> => {
    const c0 = cpu(), t0 = performance.now(); const r = await f();
    st[name] = { wall_ms: +(performance.now() - t0).toFixed(0), cpu_ms: +(cpu() - c0).toFixed(0), ...mem() };
    return r;
  };
  let raw: Uint8Array | null = await stage('read_cached_bytes', () => new Uint8Array(readFileSync(file)));
  let doc: Columnar | null = await stage('inflate_verify_parse', () => inflateVerified(raw!, meta, 'xsection price', 200_000_000));
  const bars = await stage('slice_priceSeries', () => {
    const d = doc!, list = (d as any).tickers as { t: string; rows: number; pack_sha256: string }[];
    const out: TickerBars[] = []; let at = 0;
    for (const x of list) {
      const end = at + x.rows, sl = (c: string) => (d[c] as unknown[]).slice(at, end);
      if ((d.t as string[])[at] !== x.t || (d.t as string[])[end - 1] !== x.t) throw new Error(`xsection: ${x.t} rows misaligned`);
      const pack = { schema_version: 1, dataset: 'price-pack', ticker: x.t, columns: ['d', 'o', 'h', 'l', 'c', 'v'], d: sl('d'), o: sl('o'), h: sl('h'), l: sl('l'), c: sl('c'), v: sl('v') } as unknown as Columnar;
      const ps = priceSeries(x.t, [pack]);
      out.push({ ticker: ps.ticker, dates: ps.dates, bars: ps.bars });
      at = end;
    }
    return { out, list };
  });
  const price_data = await stage('data_version', () => dataVersion(bars.list.map(x => ({ ticker: x.t, dataset: 'price', sha256: x.pack_sha256 }))));
  doc = null; raw = null;
  await stage('gc_after_decode', () => { gc?.() });
  const versions = { price_data, screener_engine: 'bench' };
  const ctx: SeriesContext = { versions, tailLength: tailLength(WITHIN_MAX), cache: new SeriesCache(512 * 1048576) };
  const R = resolvedDefaults();
  let pw: { tails: number; errors: number; errCodes: Record<string, number>; per_thread?: unknown[] };
  if (K <= 1) pw = await stage('prewarm_53', () => prewarm(ctx, bars.out, R));
  else pw = await stage('prewarm_53', async () => {
    const chunks: TickerBars[][] = Array.from({ length: K }, () => []);
    bars.out.forEach((t, i) => chunks[i % K].push(t));
    const answers = await Promise.all(chunks.map(list => new Promise<any>((ok, no) => {
      const w = new Worker(new URL(import.meta.url), { workerData: { list, versions } });
      w.once('message', ok); w.once('error', no);
    })));
    let tails = 0, errors = 0; const errCodes: Record<string, number> = {};
    const keyOf = new Map(R.map(r => [r.key, r]));
    for (const a of answers) {
      tails += a.tails; errors += a.errors; for (const [k, v] of Object.entries(a.errCodes)) errCodes[k] = (errCodes[k] ?? 0) + (v as number);
      for (const w of a.wire as WireTail[]) {
        const r = keyOf.get(w.key)!; const tail: Tail = { n: w.n, from: w.from, firstValid: w.firstValid, lastValid: w.lastValid, values: w.values };
        // insert as a pre-warmed (pinned) entry through the same cache the series path reads
        ctx.cache.set(seriesKey(versions, r), w.ticker, tail, true);
      }
    }
    return { tails, errors, errCodes, per_thread: answers.map(a => ({ wall_ms: Math.round(a.wall_ms), cpu_ms: Math.round(a.cpu_ms), tails: a.tails })) };
  });
  await stage('gc_after_prewarm', () => { gc?.() });
  const READY_MS = performance.now();
  say({ event: 'ready', ready_ms: +READY_MS.toFixed(0), ...st, outputs: R.length, indicators: INDICATORS.length, tickers: bars.out.length,
    tails: pw.tails, errors: pw.errors, err_codes: pw.errCodes, per_thread: pw.per_thread, cache_bytes: ctx.cache.bytes, ...mem() });

  /* ---- serve ---- */
  const at = (t: TickerBars) => t.bars.C.length - 1;
  const lastOf = (tail: Tail, i: number) => tail.values[i - tail.from];
  const byId = (id: string, output: string, params?: Record<string, unknown>) => resolveIndicator({ kind: 'indicator', indicator: id, params: params as any, output }, 'q', OPTS);
  const s = { rsi14: byId('I13', 'rsi'), sma20: byId('I01', 'sma'), rsi7: byId('I13', 'rsi', { length: 7 }), sma75: byId('I01', 'sma', { length: 75 }), macd: byId('I06', 'macd'), sig: byId('I06', 'signal') };
  function screen(kind: 'default' | 'custom') {
    let match = 0, dynamic = 0, pre = 0;
    for (const t of bars.out) {
      const tc = tickerCalc(t), i = at(t);
      const get = (r: ResolvedIndicator) => { try { const x = series(ctx, tc, r); x.source === 'precomputed' ? pre++ : dynamic++; return x.tail } catch { return null } };
      if (kind === 'default') {
        const a = get(s.rsi14), b = get(s.sma20); if (!a || !b) continue;
        if (lastOf(a, i) < 30 && t.bars.C[i] > lastOf(b, i)) match++;
      } else {
        const a = get(s.rsi7), b = get(s.sma75), m = get(s.macd), g = get(s.sig); if (!a || !b || !m || !g) continue;
        let cross = false; for (let k = i; k > i - 4 && k - 1 >= m.from; k--) if (lastOf(m, k) > lastOf(g, k) && lastOf(m, k - 1) <= lastOf(g, k - 1)) cross = true;
        if (lastOf(a, i) < 30 && t.bars.C[i] > lastOf(b, i) && cross) match++;
      }
    }
    return { match, dynamic, pre };
  }
  const serve: Record<string, unknown> = {};
  for (const [name, kind] of [['default_screen_1', 'default'], ['default_screen_2', 'default'], ['custom_screen_cold', 'custom'], ['custom_screen_repeat', 'custom']] as const) {
    const c0 = cpu(), t0 = performance.now(); const r = screen(kind);
    serve[name] = { wall_ms: +(performance.now() - t0).toFixed(1), cpu_ms: +(cpu() - c0).toFixed(1), ...r };
  }
  gc?.();
  say({ event: 'served', ...serve, cache_bytes: ctx.cache.bytes, steady: mem(), peak_rss_mb: Math.round(process.resourceUsage().maxRSS / 1024), total_ms: +performance.now().toFixed(0), total_cpu_ms: +cpu().toFixed(0) });
  /* idle: an awake instance holding its snapshot (the cache stays referenced) */
  const HOLD = rest.includes('--hold') ? Number(rest[rest.indexOf('--hold') + 1]) : 0;
  for (const s2 of [5, 15, 30, 60].filter(x => x <= HOLD)) {
    await new Promise(r => setTimeout(r, (s2 - ([0, 5, 15, 30].find((_, j, a) => [5, 15, 30, 60][j] === s2) ?? 0)) * 1000));
    gc?.(); say({ event: 'idle', after_s: s2, cache_tails: ctx.cache.bytes.total, ...mem() });
  }
}
