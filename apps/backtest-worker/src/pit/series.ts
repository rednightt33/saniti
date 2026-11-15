/* EXEC-BACKTEST-REVAMP P4: a point-in-time reference's series on a ticker's bars, from its broker rows (the same FlowRows
   the Terminal's formulas read: flowmetrics.ts brokerFlowRows on the bars from its first to its last broker day). One
   computation per family and parameters serves every output (FL18, FL19, FL20, FL44, FL45 and cohort_changed of one
   cohort rule in one pass), kept per ticker. Checked per ticker: the anchor not before its first broker day
   (ANCHOR_BEFORE_DATA; a portfolio leaves such a stock out, signals.ts EXCLUDED_CODES). A named broker without rows
   is checked up to the period's end by the caller (namedWithoutRows): rows after it never decide a run. A price or percentage value is left empty where its span from the anchor reads broker
   lots on another basis than the prices (K3 a, ERRORS M448: an action on or before ADJUSTED_HISTORY_BOUNDARY after the
   anchor, or a later one inside the span), noted for FLOW_BASIS_CHANGE; FLOW_PRE_2021 reads the anchor's date. */
import type { Calc } from '../../../edge-bff/backtest/src/core/conditions.ts';
import { ADJUSTED_HISTORY_BOUNDARY } from '../../../edge-bff/backtest/src/core/engine.ts';
import { canonicalJson } from '../../../edge-bff/backtest/src/core/hash.ts';
import { ValidationError } from '../../../edge-bff/backtest/src/core/registry.ts';
import { brokerFlowRows } from '../../../edge-bff/screener/src/core/flowmetrics.ts';
import { anchored, candleAt, inventory, loaders } from './compute.ts';
import type { AnchoredParams, InventoryParams, LoadersParams, Num } from './compute.ts';
import { D_SPECS } from './spec.ts';
import type { DRef } from './spec.ts';

const MEMO = new WeakMap<Calc, Map<string, Record<string, Num[]>>>();

/** The first named broker of a reference without a row on or before `until` (a date), with its place in the list, or
    null: UNKNOWN_BROKER ("ZZ has no broker rows for BBCA") decided on the rows up to the period's end only. */
export function namedWithoutRows(c: Calc, ref: DRef, until: string): [code: string, k: number] | null {
  const named = Array.isArray(ref.params.brokers) ? ref.params.brokers as string[] : [], cols = c.meta.broker?.columns;
  if (!named.length || !cols) return null;
  const seen = new Set<string>();
  for (let k = 0; k < cols.rows && cols.dates[cols.D[k]] <= until; k++) seen.add(cols.brokers[cols.B[k]]);
  const k = named.findIndex(code => !seen.has(code));
  return k < 0 ? null : [named[k], k];
}

/** The series of a checked point-in-time reference on every bar of the ticker (null where it has no value). */
export function dSeries(c: Calc, ref: DRef, field: string): Num[] {
  const b = c.meta.broker, dates = c.meta.dates ?? [], ticker = c.meta.ticker ?? 'this stock';
  if (!b) throw new ValidationError('FLOW_UNAVAILABLE', field, `${field}: this condition reads the broker data, which is not loaded for ${ticker}.`);
  const cols = b.columns, spec = D_SPECS[ref.metric], p = ref.params, dateKey = spec.date, pf = `${field}.params`;
  if (!cols.rows) throw new ValidationError('FLOW_OUTPUT_EMPTY', field, `${field}: ${ticker} has no broker rows, so ${ref.metric} has no value.`);
  const first = cols.dates[0], last = cols.dates[cols.dates.length - 1], anchor = p[dateKey] as string;
  if (anchor < first) throw new ValidationError('ANCHOR_BEFORE_DATA', `${pf}.${dateKey}`, `${ticker} has broker data from ${first}; set params.${dateKey} on or after it.`);

  let memo = MEMO.get(c);
  if (!memo) MEMO.set(c, memo = new Map());
  const key = canonicalJson([spec.family, p]);
  let out = memo.get(key);
  if (!out) {
    // the bars from the first to the last broker day (the Terminal's FlowRows are on those candles)
    let lo = 0; while (lo < dates.length && dates[lo] < first) lo++;
    let hi = dates.length - 1; while (hi >= 0 && dates[hi] > last) hi--;
    const w = dates.slice(lo, hi + 1), R = brokerFlowRows(cols as never, w), C = c.bars.C as ArrayLike<number | null>;
    const close: Num[] = w.map((_, k) => { const v = C[lo + k]; return typeof v === 'number' && Number.isFinite(v) ? v : null });
    const part: Record<string, Num[]> = spec.family === 'anchored' ? anchored(R, w, close, p as unknown as AnchoredParams)
      : spec.family === 'inventory' ? inventory(R, w, p as unknown as InventoryParams) : loaders(R, w, close, p as unknown as LoadersParams);
    out = {};
    for (const [k, s] of Object.entries(part)) { const full: Num[] = new Array(dates.length).fill(null); for (let j = 0; j < s.length; j++) full[lo + j] = s[j]; out[k] = full }
    memo.set(key, out);
  }
  const name = spec.family === 'anchored' ? (ref.output === 'cohort_changed' ? 'cohort_changed' : ref.metric) : ref.output;
  const s = [...out[name]], unit = spec.outputs[ref.output];
  // K3 a: a price or percentage from the anchor across an action the prices are adjusted for (FL51's share is a ratio of lots)
  const notes = c.flowNotes ??= { depth: 0, masked: new Set<number>() };
  if (!notes.first || anchor < notes.first) notes.first = anchor;
  if ((p.boards as string[]).some(x => x !== 'Regular')) notes.crossing = true;
  if ((unit === 'price' || unit === 'pct') && !(ref.metric === 'FL51' && ref.output === 'share')) {
    const a = candleAt(dates, anchor), actions = b.actions ?? [];
    for (let i = a; i < s.length; i++)
      if (s[i] !== null && actions.some(d => dates[a] < d && (d <= ADJUSTED_HISTORY_BOUNDARY || dates[i] >= d))) { s[i] = null; notes.masked.add(i) }
  }
  return s;
}
