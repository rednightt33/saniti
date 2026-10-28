/* POST /v1/preview: one ticker under one definition, pinned to a data_version (report API CONTRACT 8.6; TARGET
   ARCHITECTURE 6.18 C2: the page holds no formula and reads no rack file, so the chart's bars, overlays and markers come
   from here, from the same snapshot as the table). Computed on a compute thread on the run's ScreenEnv (run.ts
   screenEnv): the cells, met, need, status (the one near rule) and remarks are core screen.ts previewCells; the ticker's
   cells and status are returned even outside the universe.
   - bars: the last PREVIEW_BARS of the ticker's bars; ihsg_close: IHSG's close aligned to those dates with datafile.ts
     asOf (6.13 "IHSG aligned by asOf");
   - overlays: per enabled condition, every series it reads that is not a bar field or a pattern signal (lagged sides
     included, as the condition reads them), over the same bars (full history computed, then cut);
   - markers: per EVENT condition, every bar of the window where its signal fires (core condition.ts conditionSignal on
     the full series), with the operator or the pattern type as the kind;
   - perf ("Stock vs IHSG", P14 relabelled): over the session counts of screener-metrics.json `periods` (P23 a), the
     return of the stock and of IHSG aligned to the stock's dates, both through F's roc (the one formula path). */
import type { Definition, PerfPeriod, Periods, PreviewResponse } from '../../edge-bff/screener/src/core/contract.ts';
import { PERF_PERIODS, PREVIEW_BARS } from '../../edge-bff/screener/src/core/contract.ts';
import { conditionSignal } from '../../edge-bff/screener/src/core/condition.ts';
import { round12 } from '../../edge-bff/screener/src/core/evaluate.ts';
import type { ResolvedIndicator, ResolvedSeries } from '../../edge-bff/screener/src/core/metrics.ts';
import { previewCells } from '../../edge-bff/screener/src/core/screen.ts';
import { asOf } from '../../edge-bff/backtest/src/core/datafile.ts';
import { Calc } from '../../edge-bff/backtest/src/core/conditions.ts';
import type { Bars } from '../../edge-bff/terminal/src/calc/indicators.ts';
import { pack, screenEnv } from './run.ts';
import type { ThreadEnv } from './run.ts';
import type { ThreadSnapshot } from './snapshot.ts';

export interface PreviewTask {
  kind: 'preview'; sid: string; definition: Definition; ticker: string; periods: Periods | null;
  versions: PreviewResponse['versions']; data: PreviewResponse['data'];
}
export interface PreviewOutcome { kind: 'preview'; gzip: Uint8Array; etag: string; json_bytes: number; busy_ms: number; status: string }

const r12 = (xs: ArrayLike<number | null | undefined>, from: number, to: number): (number | null)[] => {
  const out: (number | null)[] = [];
  for (let i = from; i < to; i++) out.push(round12(xs[i] ?? null));
  return out;
};
/** The overlay name of a series: its label, with the parameters when they are not the registry defaults (two
    instances of one indicator in one condition, SMA50 vs SMA200, stay apart). */
function overlayName(r: ResolvedSeries): string {
  const ind = r.kind === 'indicator' ? r as ResolvedIndicator : null;
  return ind && !ind.isDefault ? `${r.label}(${Object.entries(ind.params).map(([k, v]) => `${k}=${v}`).join(',')})` : r.label;
}
/** The return over p bars at `at` (F.roc on close, length p); null when there are fewer bars. */
function roc(calc: Calc, p: number, at: number): number | null {
  if (at - p < 0) return null;
  return round12(calc.out('roc', { length: p, source: 'close' }).roc[at]);
}

export function runPreview(task: PreviewTask, snap: ThreadSnapshot, env: ThreadEnv): PreviewOutcome {
  const t0 = performance.now();
  const s = screenEnv(snap, env, () => false);
  const p = previewCells(task.definition, s.env, task.ticker);
  const tc = s.calc(task.ticker)!, n = tc.dates.length, from = Math.max(0, n - PREVIEW_BARS), at = n - 1;
  const bars = tc.bars, dates = tc.dates.slice(from, n) as string[];
  const ih = snap.ihsg;
  const aligned = asOf(ih.dates, ih.bars.C as (number | null)[], tc.dates as string[]);
  const full = (r: ResolvedSeries) => r.full(tc);
  const overlays: PreviewResponse['overlays'] = [], markers: PreviewResponse['markers'] = [];
  for (const b of p.bound) {
    for (const r of b.series) if (r.kind !== 'price' && r.kind !== 'pattern') overlays.push({ condition_id: b.id, output: overlayName(r), values: r12(full(r), from, n) });
    if (b.kind !== 'event') continue;
    const sig = conditionSignal(b, full, n);
    if (!sig) continue;
    const t = b.test as Extract<PreviewResponse['cells'][number], never> | any;
    const kind = 'pattern' in t.signal ? String(t.signal.pattern.type) : String(t.signal.op);
    const fired: { date: string; kind: string }[] = [];
    for (let i = Math.max(1, from); i < n; i++) if (sig[i] === 1) fired.push({ date: tc.dates[i], kind });
    markers.push({ condition_id: b.id, bars: fired });
  }
  const perf = {} as PreviewResponse['perf'];
  const index = new Calc({ O: aligned, H: aligned, L: aligned, C: aligned, V: aligned.map(() => null) } as Bars);
  for (const k of PERF_PERIODS as readonly PerfPeriod[]) {
    const len = task.periods?.[k];
    perf[k] = typeof len === 'number' ? { stock_pct: roc(tc.calc, len, at), ihsg_pct: roc(index, len, at) } : { stock_pct: null, ihsg_pct: null };
  }
  const answer: PreviewResponse = {
    versions: task.versions, data: task.data,
    ticker: task.ticker, status: p.status, remarks: p.remarks, met: p.met, need: p.need, cells: p.cells,
    bars: { d: dates, o: r12(bars.O, from, n), h: r12(bars.H, from, n), l: r12(bars.L, from, n), c: r12(bars.C, from, n), v: r12(bars.V, from, n) },
    ihsg_close: r12(aligned, from, n), overlays, markers, perf,
  };
  return { kind: 'preview', ...pack(answer, env.maxResponseBytes), busy_ms: Math.round(performance.now() - t0), status: p.status };
}
