/* Screener compute benchmark (read-only audit). Imports the real formulas (Terminal F) and the backtest core's
   condition code; never copies a formula. One scenario per process so peak RSS (resourceUsage().maxRSS) is per scenario.
   Usage: node --experimental-strip-types --expose-gc --import /home/user/saniti/apps/backtest-worker/loader/register.mjs \
            bench.mts <scenario: load|a|b|c|abc|all53> <data.json> <out.json> [--last K] [--from YYYY-MM-DD] [--reps R] */
import { readFileSync, writeFileSync } from 'node:fs';
import { gzipSync } from 'node:zlib';
import { F, isN } from '/home/user/saniti/apps/edge-bff/terminal/src/calc/indicators.ts';
import type { Bars } from '/home/user/saniti/apps/edge-bff/terminal/src/calc/indicators.ts';
import { Calc, indicatorCondition } from '/home/user/saniti/apps/edge-bff/backtest/src/core/conditions.ts';
import type { IndicatorCondition } from '/home/user/saniti/apps/edge-bff/backtest/src/core/conditions.ts';
import { REGISTRY, BY_ID, resolveParams, ValidationError } from '/home/user/saniti/apps/edge-bff/backtest/src/core/registry.ts';

const [scenario, dataPath, outPath, ...rest] = process.argv.slice(2);
const opt = (k: string) => { const i = rest.indexOf(k); return i >= 0 ? rest[i + 1] : undefined };
const LAST = opt('--last') ? Number(opt('--last')) : 0;
const FROM = opt('--from') || '';
const REPS = Number(opt('--reps') || 3);
const gc = (globalThis as any).gc as (() => void) | undefined;
const mb = (b: number) => Math.round(b / 1048576 * 10) / 10;
const mem = () => { const m = process.memoryUsage(); return { rss_mb: mb(m.rss), heap_used_mb: mb(m.heapUsed), external_mb: mb(m.external), array_buffers_mb: mb(m.arrayBuffers) } };
function timed<T>(f: () => T): { r: T; wall_ms: number; cpu_ms: number } {
  const c0 = process.cpuUsage(), t0 = performance.now();
  const r = f();
  const wall = performance.now() - t0, c = process.cpuUsage(c0);
  return { r, wall_ms: +wall.toFixed(1), cpu_ms: +((c.user + c.system) / 1000).toFixed(1) };
}

/* ---- load ---- */
const tLoad = timed(() => {
  const raw = JSON.parse(readFileSync(dataPath, 'utf8')) as Record<string, { d: string[]; o: number[]; h: number[]; l: number[]; c: number[]; v: (number | null)[] }>;
  const out: { ticker: string; bars: Bars; n: number; full_n: number }[] = [];
  for (const [ticker, s] of Object.entries(raw)) {
    let k = 0;
    if (FROM) { k = s.d.findIndex(d => d >= FROM); if (k < 0) continue }
    if (LAST && s.d.length - k > LAST) k = s.d.length - LAST;
    const sl = <X>(a: X[]) => (k ? a.slice(k) : a);
    const bars: Bars = { O: sl(s.o), H: sl(s.h), L: sl(s.l), C: sl(s.c), V: sl(s.v), T: sl(s.d) };
    out.push({ ticker, bars, n: bars.C.length, full_n: s.d.length });
  }
  return out;
});
const U = tLoad.r;
if (gc) gc();
const afterLoad = mem();
const bars_total = U.reduce((a, u) => a + u.n, 0);
const lastDate = U.reduce((m, u) => (u.bars.T![u.n - 1] > m ? u.bars.T![u.n - 1] : m), '');

/* ---- scenarios ---- */
type Row = Record<string, unknown>;
const cond = (indicator: string, params: Record<string, unknown>, lhs: any, op: any, rhs: any): IndicatorCondition =>
  ({ id: indicator, kind: 'indicator', indicator, params, lhs, op, rhs });
const P_RSI = resolveParams(BY_ID.I13, { length: 7 }), P_SMA = resolveParams(BY_ID.I01, { length: 75 }), P_MACD = resolveParams(BY_ID.I06, {});
const C_A = cond('I13', { length: 7 }, { type: 'output', output: 'rsi' }, 'lt', { type: 'value', value: 30 });
const C_B = cond('I01', { length: 75 }, { type: 'price' }, 'gt', { type: 'output', output: 'sma' });
const C_C = cond('I06', {}, { type: 'output', output: 'macd' }, 'crosses_above', { type: 'output', output: 'signal' });

function runA(): Row[] {
  return U.map(u => {
    const c = new Calc(u.bars), n = u.n;
    try {
      const s = indicatorCondition(c, C_A, 'a');
      return { t: u.ticker, d: u.bars.T![n - 1], rsi7: c.out('rsi', P_RSI).rsi[n - 1], a: s[n - 1] };
    } catch (e) { if (e instanceof ValidationError) return { t: u.ticker, d: u.bars.T![n - 1], rsi7: null, a: null, err: e.code }; throw e }
  });
}
function runB(): Row[] {
  return U.map(u => {
    const c = new Calc(u.bars), n = u.n;
    try {
      const s = indicatorCondition(c, C_B, 'b');
      return { t: u.ticker, close: u.bars.C[n - 1], sma75: c.out('sma', P_SMA).sma[n - 1], b: s[n - 1] };
    } catch (e) { if (e instanceof ValidationError) return { t: u.ticker, close: u.bars.C[n - 1], sma75: null, b: null, err: e.code }; throw e }
  });
}
function runC(): Row[] {
  return U.map(u => {
    const c = new Calc(u.bars), n = u.n;
    try {
      const s = indicatorCondition(c, C_C, 'c');
      let i = n - 1; while (i >= 0 && !s[i]) i--;
      const o = c.out('macd', P_MACD);
      return { t: u.ticker, macd: o.macd[n - 1], signal: o.signal[n - 1], last_cross: i >= 0 ? u.bars.T![i] : null,
               sessions_ago: i >= 0 ? n - 1 - i : null, c: i >= 0 && n - 1 - i <= 4 ? 1 : 0 };
    } catch (e) { if (e instanceof ValidationError) return { t: u.ticker, macd: null, signal: null, last_cross: null, sessions_ago: null, c: null, err: e.code }; throw e }
  });
}
/* (a)+(b)+(c) on one Calc per ticker: what a screen with three conditions costs */
function runABC(): Row[] {
  return U.map(u => {
    const c = new Calc(u.bars), n = u.n, row: Row = { t: u.ticker, d: u.bars.T![n - 1], close: u.bars.C[n - 1] };
    for (const [k, cd] of [['a', C_A], ['b', C_B], ['c', C_C]] as const) {
      try { const s = indicatorCondition(c, cd, k); if (k === 'c') { let i = n - 1; while (i >= 0 && !s[i]) i--; row.c_sessions_ago = i >= 0 ? n - 1 - i : null; row.c = i >= 0 && n - 1 - i <= 4 ? 1 : 0 } else row[k] = s[n - 1] }
      catch (e) { if (e instanceof ValidationError) row[k] = null; else throw e }
    }
    row.rsi7 = c.out('rsi', P_RSI).rsi[n - 1]; row.sma75 = c.out('sma', P_SMA).sma[n - 1];
    const o = c.out('macd', P_MACD); row.macd = o.macd[n - 1]; row.signal = o.signal[n - 1];
    return row;
  });
}

const metrics: Row = { scenario, data: dataPath, last: LAST || null, from: FROM || null, reps: REPS, node: process.version,
  tickers: U.length, bars_total, max_bars_per_ticker: Math.max(...U.map(u => u.n)), last_date: lastDate,
  tickers_last_bar_before_last_date: U.filter(u => u.bars.T![u.n - 1] < lastDate).length,
  tickers_with_history_longer_than_window: LAST ? U.filter(u => u.full_n > LAST).length : null,
  load: { wall_ms: tLoad.wall_ms, cpu_ms: tLoad.cpu_ms }, mem_after_load: afterLoad };

if (scenario === 'load') {
  /* nothing else */
} else if (scenario === 'all53') {
  const per: Row[] = []; const latest: Record<string, Record<string, Record<string, number | null>>> = {};
  let values = 0;
  const c0 = process.cpuUsage(), t0 = performance.now();
  for (const r of REGISTRY.indicators) {
    const params = resolveParams(r, {});
    const reps: { wall_ms: number; cpu_ms: number }[] = [];
    for (let rep = 0; rep < REPS; rep++) {
      const x = timed(() => {
        const L: Record<string, Record<string, number | null>> = {}; for (const o of r.outputs) L[o] = {};
        let v = 0, empty = 0;
        for (const u of U) {
          const out = F[r.key](u.bars, params);
          let any = false;
          for (const o of r.outputs) { const s = out[o]; const val = s[u.n - 1]; L[o][u.ticker] = isN(val) ? val : null; v += s.length; if (isN(val)) any = true }
          if (!any) empty++;
        }
        return { L, v, empty };
      });
      reps.push({ wall_ms: x.wall_ms, cpu_ms: x.cpu_ms });
      if (rep === 0) { latest[r.id] = x.r.L; values += x.r.v; per.push({ id: r.id, key: r.key, outputs: r.outputs.length, tickers_without_latest_value: x.r.empty }) }
    }
    const p = per[per.length - 1];
    const walls = reps.map(q => q.wall_ms).sort((a, b) => a - b);
    p.first_wall_ms = reps[0].wall_ms; p.first_cpu_ms = reps[0].cpu_ms; p.min_wall_ms = walls[0]; p.median_wall_ms = walls[Math.floor(walls.length / 2)];
  }
  const tw = performance.now() - t0, tc = process.cpuUsage(c0);
  metrics.all53 = { total_wall_ms_all_reps: +tw.toFixed(1), total_cpu_ms_all_reps: +((tc.user + tc.system) / 1000).toFixed(1),
    sum_first_wall_ms: +per.reduce((a, p) => a + (p.first_wall_ms as number), 0).toFixed(1),
    sum_min_wall_ms: +per.reduce((a, p) => a + (p.min_wall_ms as number), 0).toFixed(1),
    sum_first_cpu_ms: +per.reduce((a, p) => a + (p.first_cpu_ms as number), 0).toFixed(1),
    output_series: per.reduce((a, p) => a + (p.outputs as number), 0), output_values_one_pass: values,
    output_values_one_pass_float64_mb: mb(values * 8) };
  metrics.per_indicator = per;
  writeFileSync(outPath, JSON.stringify({ metrics, latest }));
} else {
  const f = scenario === 'a' ? runA : scenario === 'b' ? runB : scenario === 'c' ? runC : runABC;
  const reps: { wall_ms: number; cpu_ms: number }[] = []; let rows: Row[] = [];
  for (let rep = 0; rep < REPS; rep++) { const x = timed(f); reps.push({ wall_ms: x.wall_ms, cpu_ms: x.cpu_ms }); if (rep === 0) rows = x.r }
  const walls = reps.map(q => q.wall_ms).sort((a, b) => a - b);
  metrics.compute = { reps, first_wall_ms: reps[0].wall_ms, first_cpu_ms: reps[0].cpu_ms, min_wall_ms: walls[0], median_wall_ms: walls[Math.floor(walls.length / 2)] };
  metrics.rows = rows.length;
  metrics.errors = rows.filter(r => r.err).reduce((m: Row, r) => { m[r.err as string] = ((m[r.err as string] as number) || 0) + 1; return m }, {});
  if (scenario === 'abc') {
    metrics.matches = { a_rsi7_lt_30: rows.filter(r => r.a === 1).length, b_close_gt_sma75: rows.filter(r => r.b === 1).length,
      c_macd_cross_up_last5: rows.filter(r => r.c === 1).length, all_three: rows.filter(r => r.a === 1 && r.b === 1 && r.c === 1).length };
    /* payload: ticker + 5 values (close, rsi7, sma75, macd, signal) */
    const rnd = (v: unknown) => (isN(v) ? +(v as number).toPrecision(10) : null);
    const objs = rows.map(r => ({ ticker: r.t, close: r.close, rsi7: rnd(r.rsi7), sma75: rnd(r.sma75), macd: rnd(r.macd), signal: rnd(r.signal) }));
    const cols = { ticker: objs.map(o => o.ticker), close: objs.map(o => o.close), rsi7: objs.map(o => o.rsi7), sma75: objs.map(o => o.sma75), macd: objs.map(o => o.macd), signal: objs.map(o => o.signal) };
    const objsFull = rows.map(r => ({ ticker: r.t, close: r.close, rsi7: r.rsi7, sma75: r.sma75, macd: r.macd, signal: r.signal }));
    const sz = (o: unknown) => { const s = Buffer.from(JSON.stringify(o)); return { bytes: s.length, gzip_bytes: gzipSync(s, { level: 6 }).length } };
    metrics.payload = { rows: objs.length, objects_full_precision: sz(objsFull), objects_10_sig_digits: sz(objs), columnar_10_sig_digits: sz(cols) };
  }
  writeFileSync(outPath, JSON.stringify({ metrics, rows }));
}
if (gc) gc();
const ru = process.resourceUsage();
metrics.mem_end = mem();
metrics.peak_rss_mb = mb(ru.maxRSS * 1024);
metrics.process_total_cpu_ms = +((ru.userCPUTime + ru.systemCPUTime) / 1000).toFixed(1);
metrics.process_uptime_ms = +(process.uptime() * 1000).toFixed(0);
const { per_indicator, ...brief } = metrics as any;
console.log(JSON.stringify(brief));
writeFileSync(outPath.replace(/\.json$/, '.metrics.json'), JSON.stringify(metrics, null, 1));
