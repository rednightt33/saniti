/* The flow cost benchmark (verification/screener/BENCHMARK_FLOW_COST.md; QA unit B, QA4): the worker end to end on the
   benchmark market (market.ts: 900 stocks, 60 broker days of about 25,000 rows), SCREENER_THREADS 2. Not part of npm
   test (it takes minutes and its numbers depend on the machine). Run from apps/screener-worker:

     node --experimental-strip-types --no-warnings=ExperimentalWarning --import ../backtest-worker/loader/register.mjs \
       --test tests/bench/flow_cost.bench.ts

   BENCH_MODE=calibrate: every flow entry the Screener computes, at its defaults, alone, on the whole market, on the 100
   large stocks and on the 800 small ones (each memo-cold): the measured ms per broker row of its kernel and of the
   broker-data series, from the worker's own observations (run.ts Observation), and the prediction against busy_ms.
   BENCH_MODE=check (default): QA4's cases cold (a key's first run: the prior), then again with other parameters (the
   model learned), predicted against measured; then the production budget (SCREENER_MAX_CPU_MS 4500, deadline 20000)
   refuses what is predicted above it with compute_budget, naming how to pass. Lines start with BENCH. */
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import os from 'node:os';
import { test } from 'node:test';
import { coreEngine, createApp } from '../../src/server.ts';
import type { RunOutcome } from '../../src/run.ts';
import { OWNER_A, auth, call, captureLogs, configFor } from '../helpers.ts';

const logs = captureLogs();
const TICKERS = Array.from({ length: 900 }, (_, k) => `T${String(k).padStart(3, '0')}`), LARGE = TICKERS.slice(0, 100), SMALL = TICKERS.slice(100);
const ALL_BOARDS = ['Regular', 'Nego', 'Cash'];
const U = (tickers?: string[]) => ({ security_types: ['stock'], price_min: null, adv20_min_idr: null, ...(tickers ? { tickers } : {}) });
const flow = (metric: string, params: Record<string, unknown> = {}, output?: string) => ({ kind: 'flow', metric, params, ...(output ? { output } : {}) });
const value = (metric: unknown, op = 'gt', v = -1e12) => ({ kind: 'value', metric, op, value: v });
const pct = (m: unknown, length: number) => value({ kind: 'transform', fn: 'percentile', of: m, args: { length } }, 'ge', 50);

async function start(env: Record<string, string>) {
  const child = spawn(process.execPath, ['--experimental-strip-types', '--no-warnings=ExperimentalWarning', '--import', new URL('../../../backtest-worker/loader/register.mjs', import.meta.url).href,
    new URL('./serve_market.ts', import.meta.url).pathname], { stdio: ['ignore', 'pipe', 'inherit'] });
  const line: string = await new Promise(ok => child.stdout.on('data', d => { if (String(d).startsWith('URL')) ok(String(d)) }));
  const url = line.split(' ')[1];
  let cfg;
  try {
    cfg = configFor(url, { SCREENER_THREADS: '2', SCREENER_THREAD_HEAP_MB: '512', SCREENER_OWNER_CPU_MS: '2000000000', SCREENER_OWNER_INFLIGHT: '4', SCREENER_QUEUE: '10',
      SCREENER_MAX_RESPONSE_BYTES: String(8 << 20), SCREENER_MAX_CONDITIONS: '20', ...env });
  } catch (e) { child.kill(); throw e }
  const core = coreEngine(cfg), seen: RunOutcome['observe'] = [];
  const app = createApp(cfg, { pollMs: 3_600_000, engine: { ...core, observe(list) { seen.push(...list); core.observe(list) } } });
  const port = await app.listen(0, '127.0.0.1');
  await app.refresher.tick(); await app.refresher.tick();
  assert.ok(app.state().current, 'snapshot loaded');
  await new Promise(r => setTimeout(r, 3000));                  // the catalog's preset counts (system runs) settle
  let seq = 0;
  const run = async (name: string, tests: unknown[], universe = U()) => {
    seen.length = 0;
    const definition = { universe, logic: 'all', conditions: tests.map((t, k) => ({ id: `c${k}`, enabled: true, test: t })) };
    const t0 = performance.now();
    const r = await call(port, 'POST', '/v1/run', { schema_version: 1, client_order: { page: "bench", seq: ++seq }, definition, options: { exhaustive: true } }, auth(OWNER_A));
    const wall = Math.round(performance.now() - t0);
    await new Promise(res => setTimeout(res, 30));
    const ev = logs.events('run').at(-1) ?? {};
    return { name, status: r.status, body: r.body, wall, predicted: ev.predicted_ms as number, busy: ev.busy_ms as number, reused: ev.series_reused as number, observed: [...seen] };
  };
  return { app, run, close: async () => { await app.close(); child.kill() } };
}
const ratio = (p: number, m: number) => m > 0 ? (p / m).toFixed(2) : '-';
const show = (r: Awaited<ReturnType<Awaited<ReturnType<typeof start>>['run']>>) =>
  console.log(`BENCH ${r.name.padEnd(28)} http ${r.status} predicted_ms ${r.predicted} busy_ms ${r.busy} pred/busy ${r.status === 200 ? ratio(r.predicted, r.busy) : '-'} reused ${r.reused ?? 0}${r.status !== 200 ? ` ${JSON.stringify(r.body?.error).slice(0, 400)}` : ''}${(() => { const c = perKey(r.observed)['flow:context']; return c ? ` context ${Math.round(c.ms)} ms ${c.ns.toFixed(1)} ns/row` : '' })()}`);
/** ns per unit (a flow kernel's row or grid cell, an indicator's bar) of each key of a run's one-kernel observations */
function perKey(obs: RunOutcome['observe']): Record<string, { ms: number; bars: number; ns: number }> {
  const out: Record<string, { ms: number; bars: number; ns: number }> = {};
  for (const o of obs) {
    if (o.units.length !== 1) continue;                        // a series of one kernel: its time is its own
    const u = o.units[0], m = u.costClass === 'O(N·n)' ? Math.max(1, u.length) : 1, x = out[u.key] ??= { ms: 0, bars: 0, ns: 0 };
    x.ms += o.ms; x.bars += o.bars[0] * m;
  }
  for (const x of Object.values(out)) x.ns = x.ms * 1e6 / x.bars;
  return out;
}

test('flow cost benchmark', { timeout: 3_600_000 }, async () => {
  console.log(`BENCH machine ${os.cpus()[0]?.model} x${os.cpus().length} node ${process.version} load ${os.loadavg().map(x => x.toFixed(2)).join(' ')}`);
  if (process.env.BENCH_MODE === 'calibrate') {
    const w = await start({ SCREENER_MAX_CPU_MS: '1000000000', SCREENER_DEADLINE_MS: '600000' });
    const { FLOWS } = await import('../../../edge-bff/screener/src/core/flowmetrics.ts');
    const rows: string[] = [];
    for (const e of FLOWS) {
      if (e.requires) continue;
      const out = e.default_output, kind = e.outputs.find(o => o.key === out)!.kind;
      const k = typeof kind === 'string' ? kind : 'K';
      // a test the output type takes (OPERATORS.md section 4): a value for most, "= 1" on a 0/1 signal, a percentile on
      // lots per transaction and price levels
      const t = (p: Record<string, unknown>) => k === 'F' ? value(flow(e.id, p), 'eq', 1) : k === 'L' || k === 'H' ? pct(flow(e.id, p), 5) : value(flow(e.id, p), k === 'D' || k === 'B' ? 'ge' : 'gt', k === 'D' || k === 'B' ? 0 : -1e12);
      const boards = e.params.some(p => p.key === 'boards') ? { boards: ['Regular', 'Nego'] } : null;
      for (const [name, params, universe] of [[`${e.id} all`, {}, U()], [`${e.id} large`, boards ?? {}, U(LARGE)], [`${e.id} small`, boards ?? {}, U(SMALL)]] as const) {
        const r = await w.run(name, [t(params)], universe);
        show(r);
        const per = perKey(r.observed);
        rows.push(`BENCH-NS ${name.padEnd(14)} ${Object.entries(per).map(([key, x]) => `${key} ${x.ns.toFixed(1)} ns/unit (${Math.round(x.ms)} ms over ${Math.round(x.bars)} units)`).join('; ')}`);
        console.log(rows.at(-1));
      }
    }
    await w.close();
    return;
  }
  // QA4's cases (the QA harness's T and V lists): cold, then learned
  const cases: [string, unknown[], unknown[]][] = [
    ['FL10 nego foreign w5', [value(flow('FL10', { boards: ['Regular', 'Nego'], investors: ['Foreign'], window: 5 }))], [value(flow('FL10', { boards: ['Regular'], investors: ['Domestic'], window: 3 }))]],
    ['FL36 domestic all w20', [value(flow('FL36', { boards: ALL_BOARDS, investors: ['Domestic'], window: 20 }))], [value(flow('FL36', { boards: ['Regular'], investors: ['Foreign'], window: 10 }))]],
    ['FL38 all boards w20', [value(flow('FL38', { window: 20, boards: ALL_BOARDS }))], [value(flow('FL38', { window: 10, boards: ['Regular'] }))]],
    ['FL18 anchor 20 pctl 20', [pct(flow('FL18', { investors: ['Domestic'], anchor_sessions: 20 }), 20)], [pct(flow('FL18', { investors: ['Foreign'], anchor_sessions: 10 }), 10)]],
    ['FL18 anchor 35 pctl 20', [pct(flow('FL18', { investors: ['Domestic'], boards: ALL_BOARDS, anchor_sessions: 35 }), 20)], [pct(flow('FL18', { investors: ['Foreign'], boards: ALL_BOARDS, anchor_sessions: 30 }), 20)]],
    ['FL23 inventory top 5', [value(flow('FL23', { holders: 'top', top: 5, lookback: 20 }))], [value(flow('FL23', { holders: 'top', top: 3, lookback: 10 }))]],
    ['FL24 pctl 50', [pct(flow('FL24', { window: 5 }), 50)], [pct(flow('FL24', { window: 6 }), 40)]],
  ];
  const five = (a: number, investors = ['Domestic']) => ['FL18', 'FL19', 'FL20', 'FL44', 'FL45'].map(m => pct(flow(m, { anchor_sessions: a, investors }), 10));
  const seven = (w: number) => [value(flow('FL24', { top: 3, window: w })), value(flow('FL10', { boards: ['Regular', 'Nego'], investors: ['Foreign'], window: w })),
    value(flow('FL36', { boards: ALL_BOARDS, investors: ['Domestic'], window: w + 10 })), value(flow('FL26', { scope: 'all', investors: ['Foreign'], window: 60 - w }), 'ge', 0),
    value(flow('FL38', { window: w + 10, boards: ALL_BOARDS })), pct(flow('FL18', { investors: ['Domestic'], anchor_sessions: 20 + w }), 20), value(flow('FL23', { holders: 'top', top: 5, lookback: 20 + w }))];
  {
    const w = await start({ SCREENER_MAX_CPU_MS: '1000000000', SCREENER_DEADLINE_MS: '600000' });
    for (const [name, cold] of cases) show(await w.run(`cold ${name}`, cold));
    show(await w.run('cold five anchored at 40', five(40)));
    for (const [name, , learned] of cases) show(await w.run(`learned ${name}`, learned));
    show(await w.run('learned five anchored at 40', five(40, ['Foreign'])));
    show(await w.run('learned seven flow w10', seven(10)));
    show(await w.run('learned FL10 large only', [value(flow('FL10', { boards: ['Regular'], investors: ['Foreign'], window: 7 }))], U(LARGE)));
    show(await w.run('learned FL10 small only', [value(flow('FL10', { boards: ['Regular'], investors: ['Foreign'], window: 7 }))], U(SMALL)));
    show(await w.run('again: memo-warm FL10 w7', [value(flow('FL10', { boards: ['Regular'], investors: ['Foreign'], window: 7 }), 'gt', -1e11)]));
    await w.close();
  }
  {
    const w = await start({ SCREENER_MAX_CPU_MS: '1000000000', SCREENER_DEADLINE_MS: '600000' });
    show(await w.run('cold seven flow w5', seven(5)));
    await w.close();
  }
  // the production budget: 4500 ms, deadline 20000 ms
  const g = await start({ SCREENER_MAX_CPU_MS: '4500', SCREENER_DEADLINE_MS: '20000' });
  const refusedCold = await g.run('gate cold five anchored at 40', five(40));
  show(refusedCold);
  const passes = await g.run('gate FL10 alone', [value(flow('FL10', { boards: ['Regular', 'Nego'], investors: ['Foreign'], window: 5 }))]);
  show(passes);
  const refusedSeven = await g.run('gate seven flow w8', seven(8));
  show(refusedSeven);
  const refusedLearned = await g.run('gate learned five at 40', five(40, ['Foreign']));
  show(refusedLearned);
  for (const r of [refusedCold, refusedSeven, refusedLearned]) {
    if (r.status !== 422) continue;
    console.log(`BENCH refusal ${r.name}: ${r.body.error.message} ${JSON.stringify(r.body.error.details)}`);
  }
  await g.close();
});
