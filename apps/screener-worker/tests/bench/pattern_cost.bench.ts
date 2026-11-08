/* The pattern cost benchmark (verification/screener/BENCHMARK_FLOW_COST.md section 6; QA unit C, QA4): the worker end to
   end on a price-only market (fake-terminal.mjs universe: BENCH_STOCKS stocks, default 300, of BENCH_BARS price bars,
   default 1330, the longest history of the publication), SCREENER_THREADS 2, every series memo-cold. Not part of npm
   test (it takes minutes and its numbers depend on the machine). Run from apps/screener-worker:

     node --experimental-strip-types --no-warnings=ExperimentalWarning --import ../backtest-worker/loader/register.mjs \
       --test tests/bench/pattern_cost.bench.ts

   BENCH_MODE=calibrate: every pattern the Screener computes (the catalog's pattern entries that are available), alone in
   a state test on the whole market, at its defaults and at the parameters that move its window (the core's own
   lookback: candles.ts candleLookback for a candlestick pattern, transforms.ts PATTERNS window for the others) or do not
   (min_range_ticks), each a new series; per run the window, the measured ns per bar of its series from the worker's
   own observations (run.ts Observation) and the prediction against busy_ms.
   BENCH_MODE=check (default): QA4's cases of unit C (event within 3; QA's harness: 150 stocks of 1330 bars) and their
   pairs at other windows, cold (each key's first run: the prior), then learned (a second parameter set of the same
   key), predicted against measured. Lines start with BENCH. */
import assert from 'node:assert/strict';
import os from 'node:os';
import { test } from 'node:test';
import { coreEngine, createApp } from '../../src/server.ts';
import type { RunOutcome } from '../../src/run.ts';
import { METRICS_CATALOG } from '../../../edge-bff/screener/src/core/catalog.ts';
import { IMPLEMENTED_PATTERNS, resolveSignal } from '../../../edge-bff/screener/src/core/transforms.ts';
import { startFakeTerminal, universe } from '../fake-terminal.mjs';
import { OWNER_A, PROXY, auth, call, captureLogs, configFor } from '../helpers.ts';

const logs = captureLogs();
const STOCKS = Number(process.env.BENCH_STOCKS || 300), BARS = Number(process.env.BENCH_BARS || 1330);
const U = { security_types: ['stock'], price_min: null, adv20_min_idr: null };
const pattern = (type: string, params?: Record<string, unknown>) => ({ kind: 'pattern', type, ...(params ? { params } : {}) });
const state = (type: string, params?: Record<string, unknown>) => ({ kind: 'state', pattern: pattern(type, params) });
const event = (type: string, params?: Record<string, unknown>) => ({ kind: 'event', within: 3, signal: { pattern: pattern(type, params) } });
/** the core's own window of a pattern at these parameters (the bars a signal reads) */
const windowOf = (type: string, params?: Record<string, unknown>) => resolveSignal(pattern(type, params) as never, 'bench', { capBudgetMs: 1e9 }).window;

async function start(stocks: number, bars: number, env: Record<string, string>) {
  const fake = await startFakeTerminal({ key: PROXY, publication: { finished_at: '2026-10-27T13:03:23Z', ...universe(stocks, bars), actions: [] } });
  const cfg = configFor(fake.url, { SCREENER_THREADS: '2', SCREENER_THREAD_HEAP_MB: '2048', SCREENER_OWNER_CPU_MS: '2000000000', SCREENER_OWNER_INFLIGHT: '4', SCREENER_QUEUE: '10',
    SCREENER_CACHE_BYTES: String(512 << 20), SCREENER_MAX_RESPONSE_BYTES: String(8 << 20), SCREENER_CAP_BUDGET_MS: '600000', SCREENER_DEADLINE_MS: '600000', ...env });
  const core = coreEngine(cfg), seen: RunOutcome['observe'] = [];
  const app = createApp(cfg, { pollMs: 3_600_000, engine: { ...core, observe(list) { seen.push(...list); core.observe(list) } } });
  const port = await app.listen(0, '127.0.0.1');
  await app.refresher.tick();
  assert.ok(app.state().current, 'snapshot loaded');
  await new Promise(r => setTimeout(r, 3000));                  // the catalog's preset counts (system runs) settle
  let seq = 0;
  const run = async (name: string, t: unknown) => {
    seen.length = 0;
    const definition = { universe: U, logic: 'all', conditions: [{ id: 'c0', enabled: true, test: t }] };
    const r = await call(port, 'POST', '/v1/run', { schema_version: 1, client_order: { page: 'bench', seq: ++seq }, definition, options: { exhaustive: true } }, auth(OWNER_A));
    await new Promise(res => setTimeout(res, 30));
    const ev = logs.events('run').at(-1) ?? {};
    // the series' own time: the observations of the pattern's units (run.ts costUnits: its fixed part per bar and its
    // window, each over the stock's bars), whatever the model (the old one had a single unit)
    let ms = 0, units = 0, unit = '';
    for (const o of seen) if (o.units[0].key.startsWith('pattern:')) { ms += o.ms; units += o.bars[0]; unit = o.units.map(u => `${u.key.split(':').slice(2).join(':') || 'bar'} ${u.costClass} x ${u.length}`).join(' + ') }
    return { name, status: r.status, body: r.body, predicted: ev.predicted_ms as number, busy: ev.busy_ms as number, ms, nsPerBar: units ? ms * 1e6 / units : NaN, unit };
  };
  return { run, close: async () => { await app.close(); await fake.close() } };
}
const ratio = (p: number, m: number) => m > 0 ? (p / m).toFixed(2) : '-';

test('pattern cost benchmark', { timeout: 3_600_000 }, async () => {
  console.log(`BENCH machine ${os.cpus()[0]?.model} x${os.cpus().length} node ${process.version} load ${os.loadavg().map(x => x.toFixed(2)).join(' ')}`);
  const available = METRICS_CATALOG.metrics.filter(m => m.kind === 'pattern' && !m.decision && IMPLEMENTED_PATTERNS.includes(m.id));
  if (process.env.BENCH_MODE === 'calibrate') {
    const w = await start(STOCKS, BARS, { SCREENER_MAX_CPU_MS: '1000000000' });
    console.log(`BENCH market ${STOCKS} stocks x ${BARS} bars`);
    for (const m of available) {
      const keys = new Set(m.params.map(p => p.key));
      const variants: [string, Record<string, unknown> | undefined][] = [['defaults', undefined]];
      if (keys.has('trend_length')) variants.push(['trend 2', { trend_length: 2 }], ['trend 100', { trend_length: 100 }]);
      if (keys.has('body_avg_length')) variants.push(['avg 100', { body_avg_length: 100 }]);
      if (keys.has('min_range_ticks')) variants.push(['ticks 50', { min_range_ticks: 50 }]);
      // the other patterns: each whole-number parameter at a larger value (their windows grow with them)
      for (const p of m.params) if (!['trend_length', 'body_avg_length', 'min_range_ticks'].includes(p.key) && p.integer && typeof p.max === 'number')
        variants.push([`${p.key} ${Math.min(p.max, 200)}`, { [p.key]: Math.min(p.max, 200) }]);
      for (const [label, params] of variants) {
        let win: number;
        try { win = windowOf(m.id, params) } catch (e) { console.log(`BENCH skip ${m.id} ${label}: ${(e as Error).message}`); continue }
        const r = await w.run(`${m.id} ${label}`, state(m.id, params));
        console.log(`BENCH-NS ${m.id.padEnd(22)} ${label.padEnd(18)} window ${String(win).padStart(4)} http ${r.status} series_ms ${Math.round(r.ms)} ns/bar ${r.nsPerBar.toFixed(1)} unit ${r.unit} predicted_ms ${r.predicted} busy_ms ${r.busy} pred/busy ${ratio(r.predicted, r.busy)}`);
      }
    }
    await w.close();
    return;
  }
  // QA4 of unit C (150 stocks x 1330 bars, event within 3: Hammer at its defaults, then at trend 100), each case cold
  // (the key's first run), then the same key at another window (learned)
  const cases: [string, string, Record<string, unknown> | undefined, Record<string, unknown> | undefined][] = [
    ['hammer default, then trend 100 (QA4)', 'hammer', undefined, { trend_length: 100 }],
    ['hanging man trend 100, then 50', 'hanging_man', { trend_length: 100 }, { trend_length: 50 }],
    ['marubozu avg 100 trend 100', 'bullish_marubozu', { body_avg_length: 100, trend_length: 100 }, { body_avg_length: 20 }],
    ['morning star default', 'morning_star', undefined, { trend_length: 30 }],
    ['evening star avg 100 trend 100', 'evening_star', { body_avg_length: 100, trend_length: 100 }, undefined],
    ['soldiers ticks 50', 'three_white_soldiers', { min_range_ticks: 50 }, { min_range_ticks: 2 }],
    ['breakout length 20', 'breakout', undefined, { length: 100 }],
    ['squeeze default', 'squeeze', undefined, { lookback: 60 }],
  ];
  const stocks = Number(process.env.BENCH_STOCKS || 150);
  const w = await start(stocks, BARS, { SCREENER_MAX_CPU_MS: '1000000000' });
  console.log(`BENCH market ${stocks} stocks x ${BARS} bars`);
  for (const [name, type, cold, learned] of cases) {
    const a = await w.run(`cold ${name}`, event(type, cold));
    console.log(`BENCH ${a.name.padEnd(40)} window ${String(windowOf(type, cold)).padStart(4)} http ${a.status} predicted_ms ${a.predicted} busy_ms ${a.busy} pred/busy ${ratio(a.predicted, a.busy)} series_ms ${Math.round(a.ms)}`);
    const b = await w.run(`learned ${name}`, event(type, learned ?? { min_range_ticks: 2 }));
    console.log(`BENCH ${b.name.padEnd(40)} window ${String(windowOf(type, learned ?? { min_range_ticks: 2 })).padStart(4)} http ${b.status} predicted_ms ${b.predicted} busy_ms ${b.busy} pred/busy ${ratio(b.predicted, b.busy)} series_ms ${Math.round(b.ms)}`);
  }
  await w.close();
});
