/* The screener side of scripts/screener/parity_f04.py (EXEC-SCREENER; report DATABASE / FEATURE CHANGES 7.3, TEST PLAN
   10b.1 "Snapshot vs Feature 04", "Snapshot vs Feature 01", 10b.2 "Dynamic path vs Feature 04 at its stored non-default
   configurations"): the values the screener core gives for every oracle row of screener-registry.json, at each ticker's
   bar on the oracle's date, through the one series path (apps/edge-bff/screener/src/core/metrics.ts series):
   - the snapshot path: every indicator pre-warmed at registry.ts startParams (pinned, as the worker's snapshot does at a
     publication), the oracle row then read with its explicit parameters, which must hit the pre-warmed key
     (source 'precomputed', is_default true);
   - the dynamic path: an oracle row at non-default parameters (sma_50, ema_12/26/50/200, roc 5/20/60) read through an
     empty cache with pre-warm off (source 'dynamic', is_default false).
   Bars: the price rows the job names, decoded by the backtest core's datafile.priceSeries (the rack's row rules) and cut
   at the oracle's date, so the snapshot's evaluation date is that date. Read-only; prints one JSON document.
   Run: node --experimental-strip-types --import ./apps/backtest-worker/loader/register.mjs scripts/screener/parity_f04_core.mjs <job.json>
   (from the repository root; parity_f04.py writes the job and runs it). */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const core = rel => import(path.join(ROOT, 'apps/edge-bff/screener/src/core', rel));
const { priceSeries } = await import(path.join(ROOT, 'apps/edge-bff/backtest/src/core/datafile.ts'));
const { INDICATORS, SCREENER_REGISTRY, SCREENER_REGISTRY_VERSION, startParams } = await core('registry.ts');
const { SeriesCache, resolveIndicator, series, seriesKey, tailLength, tickerCalc } = await core('metrics.ts');

const job = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const prices = JSON.parse(fs.readFileSync(job.prices, 'utf8'));
const OPTS = { capBudgetMs: job.cap_budget_ms ?? 2000 }, WITHIN_MAX = job.within_max ?? 130;
const versions = { price_data: 'parity', screener_engine: 'parity' };

/** A ticker's bars up to `date` through the rack's row rules; an optional perturbation of one bar (the self-check). */
function barsAt(ticker, date, perturb) {
  const p = prices[ticker];
  const k = p.d.findLastIndex(d => d <= date) + 1;
  if (k <= 0) return null;
  const cut = a => a.slice(0, k);
  const doc = { columns: ['d', 'o', 'h', 'l', 'c', 'v'], d: cut(p.d), o: cut(p.o), h: cut(p.h), l: cut(p.l), c: cut(p.c), v: cut(p.v) };
  if (perturb && perturb.ticker === ticker) {
    const i = doc.d.length - 1 - perturb.bar_offset;
    for (const f of ['o', 'h', 'l', 'c']) { doc[f] = doc[f].slice(); doc[f][i] = doc[f][i] * perturb.factor }
  }
  const s = priceSeries(ticker, [doc]);
  return { ticker, dates: s.dates, bars: s.bars };
}

const rows = [];
for (const r of INDICATORS) for (const o of r.oracle) rows.push({ id: r.id, ...o });
if (job.must_differ) for (const m of job.must_differ) rows.push({ ...m, must_differ: true });

function run(date, tickers, perturb) {
  const t0 = performance.now();
  const snapshot = new SeriesCache(2 ** 40), ctx = { versions, tailLength: tailLength(WITHIN_MAX), cache: snapshot };
  const out = rows.map(o => ({ ...o, values: {}, sources: new Set(), keyHit: true, isDefault: null }));
  const resolved = out.map(o => resolveIndicator({ kind: 'indicator', indicator: o.id, output: o.output, params: o.params }, `oracle.${o.id}`, OPTS));
  let prewarmMs = 0, n = 0;
  for (const ticker of tickers) {
    const t = barsAt(ticker, date, perturb);
    if (!t || t.dates[t.dates.length - 1] !== date) continue;              // no bar on the oracle's date
    n++;
    const tc = tickerCalc(t), at = t.dates.length - 1, p0 = performance.now();
    for (const ind of INDICATORS) for (const ou of ind.outputs)                // the snapshot pre-warm (report 6.7)
      series(ctx, tc, resolveIndicator({ kind: 'indicator', indicator: ind.id, output: ou.key, params: startParams(ind, OPTS) }, 'prewarm', OPTS), true);
    prewarmMs += performance.now() - p0;
    const dynamic = { versions, tailLength: tailLength(WITHIN_MAX), cache: new SeriesCache(2 ** 40) };
    out.forEach((o, k) => {
      const r = resolved[k];
      const got = r.isDefault ? series(ctx, tc, r) : series(dynamic, tickerCalc(t), r);   // dynamic: an empty LRU, pre-warm off
      o.sources.add(got.source); o.isDefault = r.isDefault;
      const v = got.tail.values[at - got.tail.from];
      o.values[ticker] = Number.isFinite(v) ? v : null;
    });
  }
  return { date, tickers: n, ms: Math.round(performance.now() - t0), prewarm_ms: Math.round(prewarmMs),
    rows: out.map(o => ({ id: o.id, output: o.output, params: o.params, table: o.table, column: o.column ?? null, expr: o.expr ?? null,
      must_differ: !!o.must_differ, is_default: o.isDefault, sources: [...o.sources], values: o.values })) };
}

const result = { registry_version: SCREENER_REGISTRY.registry_version, screener_registry_version: SCREENER_REGISTRY_VERSION, runs: {} };
for (const [name, spec] of Object.entries(job.runs)) result.runs[name] = run(spec.date, spec.tickers, spec.perturb ?? null);
process.stdout.write(JSON.stringify(result));
