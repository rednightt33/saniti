/* FIXTURE ONLY: a small evaluator of the wire definition (report 8.5) over the prototype's synthetic bars, so the page
   can be seen and smoke-tested without the worker. Indicator values come from the Terminal's module through the
   Backtest core (registry.ts calculate, the one formula per indicator); the fixture adds only the condition
   arithmetic of the wire forms (transforms, crosses, the near rule of report 6.9). It is not the worker's engine and is
   never part of the production bundle (tests/bundle). */
import { BY_ID, calculate, resolveParams } from '../../../backtest/src/core/registry.ts';
import type { Bars } from '../../../terminal/src/calc/indicators.ts';
import type {
  Cell, ConditionDef, ConditionSummary, Definition, MetricRef, PreviewResponse, ResultRow, RowRemark, RunResponse, Side, UniverseRow, Versions,
} from '../../src/core/contract.ts';
import { universeView } from '../../src/universe-view.ts';
import { resolveSeries, tickerCalc } from '../../src/core/metrics.ts';
import { valuePasses } from '../../src/core/evaluate.ts';
import { percentRank } from '../../src/core/xsection.ts';
import { metricSpec } from '../../src/core/catalog.ts';
import { FLOW_CTX, tickerFlow } from './broker.ts';

export type S = (number | null)[];
export interface Tk {
  ticker: string; name: string; sector: string | null; industry: string | null;
  d: string[]; o: number[]; h: number[]; l: number[]; c: number[]; v: number[];
  remarks: RowRemark[]; breakAt: number | null;
}
export interface Market { tickers: Tk[]; byTicker: Map<string, Tk>; days: string[]; ihsg: number[]; evalDate: string }

const memo = new Map<string, S>();
const isN = (x: unknown): x is number => typeof x === 'number' && Number.isFinite(x);
const barsOf = (t: Tk): Bars => ({ O:t.o, H:t.h, L:t.l, C:t.c, V:t.v, T:t.d });
/** a series of the core on the ticker's bars, with its broker data (a flow indicator and the operators over it, P5c) */
const coreSeries = (t: Tk, r: MetricRef): S => Array.from(resolveSeries(r, 'fixture', { capBudgetMs:2000, flow:FLOW_CTX })
  .full(tickerCalc({ ticker:t.ticker, dates:t.d, bars:barsOf(t), flow:tickerFlow(t.ticker, t.d) })) as ArrayLike<number | null | undefined>, x => isN(x) ? x : null);
/** whether a test reads a flow indicator (it is then evaluated at the stock's last session with broker data, P10 a) */
export const readsFlow = (x: unknown): boolean => !!x && typeof x === 'object' && ((x as { kind?: unknown }).kind === 'flow' || Object.values(x as object).some(readsFlow));
/** the stock's last bar with broker data on or before its last bar (-1: none in the window) */
export function flowBar(t: Tk): number {
  const rows = tickerFlow(t.ticker, t.d).rows(); if (!rows || !rows.rows) return -1;
  const days = new Set(Array.from(rows.D, k => rows.dates[k]));
  for (let i = t.c.length - 1; i >= 0; i--) if (days.has(t.d[i])) return i;
  return -1;
}

const sma = (a: S, n: number): S => { const r: S = new Array(a.length).fill(null); for (let i = n - 1; i < a.length; i++) { let s = 0, ok = true; for (let j = i - n + 1; j <= i; j++) { const x = a[j]; if (!isN(x)) { ok = false; break } s += x } if (ok) r[i] = s / n } return r };
const ema = (a: S, n: number): S => { const r: S = new Array(a.length).fill(null), k = 2 / (n + 1); let e: number | null = null, s = 0, m = 0; for (let i = 0; i < a.length; i++) { const x = a[i]; if (!isN(x)) continue; if (e == null) { s += x; m++; if (m === n) { e = s / n; r[i] = e } } else { e = x * k + e * (1 - k); r[i] = e } } return r };

/** the series of a reference on a ticker's bars (null where it has no value) */
export function series(m: Market, t: Tk, ref: MetricRef | Side): S {
  if ((ref as any).value !== undefined && !(ref as any).kind) return t.c.map(() => (ref as any).value);
  const key = t.ticker + JSON.stringify(ref);
  const hit = memo.get(key); if (hit) return hit;
  const r = ref as MetricRef, n = t.c.length;
  let out: S;
  switch (r.kind) {
    case 'indicator': {
      const reg = BY_ID[r.indicator]; if (!reg) throw new Error('unknown indicator ' + r.indicator);
      const o = calculate(reg, barsOf(t), resolveParams(reg, r.params || {}));
      out = Array.from(o[r.output] || [], x => isN(x) ? x : null); break;
    }
    case 'price': out = ({ open:t.o, high:t.h, low:t.l, close:t.c, volume:t.v } as Record<string, number[]>)[r.field].slice(); break;
    case 'transform': {
      const of = series(m, t, r.of), a = r.args || {};
      switch (r.fn) {
        case 'pct_distance': out = t.c.map((c, i) => isN(of[i]) && of[i] ? (c / (of[i] as number) - 1) * 100 : null); break;
        case 'band_position': {
          const ind = r.of as any, reg = BY_ID[ind.indicator], o = calculate(reg, barsOf(t), resolveParams(reg, ind.params || {}));
          const up = o.upper || o.upper1, lo = o.lower || o.lower1;
          out = t.c.map((c, i) => { const u = up?.[i], l = lo?.[i]; return isN(u) && isN(l) && u - l > 0 ? (c - l) / (u - l) * 100 : null }); break;
        }
        case 'lag': { const b = Number(a.bars ?? 1); out = of.map((_, i) => i >= b ? of[i - b] : null); break }
        case 'ma': { const len = Number(a.length ?? 20); out = String(a.ma ?? 'EMA') === 'SMA' ? sma(of, len) : ema(of, len); break }
        case 'rolling_max': case 'rolling_min': { const len = Number(a.length ?? 252); out = of.map((_, i) => { if (i < len - 1) return null; let x = r.fn === 'rolling_max' ? -Infinity : Infinity; for (let j = i - len + 1; j <= i; j++) { const y = of[j]; if (!isN(y)) return null; x = r.fn === 'rolling_max' ? Math.max(x, y) : Math.min(x, y) } return x }); break }
        case 'vs_index': { const w = Number(a.window ?? 63); const ix = m.ihsg, off = m.days.length - n; out = t.c.map((c, i) => i >= w ? ((c / t.c[i - w]) - (ix[off + i] / ix[off + i - w])) * 100 : null); break }
        // every other transform (the universal operators, P3) is the worker's own, through the core on these bars
        default: out = coreSeries(t, r);
      }
      break;
    }
    case 'pattern': {
      const p = r.params || {};
      if (r.type === 'breakout') { const len = Number(p.length ?? 20); out = t.c.map((c, i) => { if (i < len) return 0; let mx = -Infinity; for (let j = i - len; j < i; j++) mx = Math.max(mx, t.h[j]); return c > mx ? 1 : 0 }) }
      else if (r.type === 'volspike') { const len = Number(p.length ?? 20), x = Number(p.ratio ?? 2); out = t.v.map((v, i) => { if (i < len) return 0; let s = 0; for (let j = i - len; j < i; j++) s += t.v[j]; return v > x * s / len ? 1 : 0 }) }
      else throw new Error('fixture: unknown pattern ' + r.type);
      break;
    }
    case 'xsection': {
      const w = Number(r.params?.window ?? 252), ret = (k: Tk) => { const i = k.c.length - 1; return i >= w ? k.c[i] / k.c[i - w] : null };
      const pop = m.tickers.filter(k => !k.remarks.length).map(ret).filter(isN), me = ret(t);
      const v = me == null || pop.length < 2 ? null : 100 * pop.filter(x => x < me).length / (pop.length - 1);
      out = t.c.map((_, i) => i === n - 1 ? v : null); break;
    }
    case 'rank': {
      // operator 11 over the fixture's listed stocks without a remark (the worker ranks within the filtered universe)
      // a flow series is read at each stock's last session with broker data (P10 a)
      const atOf = (k: Tk) => readsFlow((r as any).of) ? flowBar(k) : k.c.length - 1;
      const val = (k: Tk) => { const s = series(m, k, (r as any).of), i = atOf(k); return i < 0 ? null : s[i] };
      const values = new Map(m.tickers.map(k => [k.ticker, val(k)] as [string, number | null]));
      const pop = new Set(m.tickers.filter(k => !k.remarks.length && isN(values.get(k.ticker))).map(k => k.ticker));
      const v = percentRank(values, pop).get(t.ticker) ?? null, me = atOf(t);
      out = t.c.map((_, i) => i === me ? v : null); break;
    }
    // a flow indicator (P5c): the core's flowmetrics.ts on the fixture's broker rows (broker.ts)
    case 'flow': out = coreSeries(t, r); break;
    case 'universe': {
      const i = n - 1, adv = sma(t.c.map((c, j) => c * t.v[j]), 20);
      const val = r.attr === 'last' ? t.c[i] : r.attr === 'adv20_idr' ? adv[i] : r.attr === 'chg_1d_pct' ? (t.c[i] / t.c[i - 1] - 1) * 100 : r.attr === 'bars' ? n : null;
      out = t.c.map((_, j) => j === i ? val : null); break;
    }
    default: throw new Error('fixture: unknown metric kind');
  }
  memo.set(key, out);
  return out;
}

/** the longest look-back of the references of a test (the fixture's stand-in for report 6.12's lookback rule) */
const lookback = (refs: any[]): number => {
  let n = 1;
  const walk = (r: any) => {
    if (!r || typeof r !== 'object') return;
    if (r.kind === 'indicator') { const reg = BY_ID[r.indicator]; const p = reg ? resolveParams(reg, r.params || {}) : {}; for (const [k, v] of Object.entries(p)) if (/length/.test(k) && typeof v === 'number') n = Math.max(n, v) }
    for (const v of Object.values(r.args || {})) if (typeof v === 'number') n = Math.max(n, v);
    for (const v of Object.values(r.params || {})) if (typeof v === 'number') n = Math.max(n, v);
    walk(r.of);
  };
  refs.forEach(walk);
  return n;
};
const refsOf = (t: any): any[] => [t.metric, t.lhs, t.rhs, t.pattern, t.signal?.lhs, t.signal?.rhs, t.signal?.pattern].filter(Boolean);

/** The wire Cell.unit (and ConditionSummary.unit) of a condition as the worker's core writes it (src/core/condition.ts:
    a value test carries its series' unit, a universe attribute its catalog unit, a cross-section rank and a pattern
    none; a STATE or EVENT the unit of its first side that is not a bar field). The unit is the core's scaling class,
    not a display unit: a percent distance, ROC or ATR % arrive as 'dimensionless' (ERRORS M355), so the page must take
    its format from the catalog; the fixture carries the same field so the page's display path is the production one.
    A cross-section rank carries its catalog unit on the summary and none on its cells, as the core does.
    tests/page/fixture-units.test.ts checks this against the real core. */
const unitMemo = new Map<string, string | null>();
export function unitOf(test: any, where: 'cell' | 'summary' = 'cell'): string | null {
  const key = where + JSON.stringify(test), hit = unitMemo.get(key); if (hit !== undefined) return hit;
  const ser = (r: any) => { try { return resolveSeries(r, 'fixture', { capBudgetMs:2000 }) } catch { return { unit:null } } };
  const sideUnit = (s: any) => s && s.kind && s.kind !== 'price' ? ser(s).unit as string | null : null;
  const anyUnit = (s: any) => s && s.kind ? ser(s).unit as string | null : null;
  let u: string | null = null;
  if (test.kind === 'value') {
    const k = test.metric?.kind;
    const spec = (kind: 'universe' | 'xsection', id: string) => { try { return (metricSpec(kind, id, 'fixture').unit ?? null) as string | null } catch { return null } };
    u = k === 'universe' ? spec('universe', test.metric.attr) : k === 'xsection' ? (where === 'summary' ? spec('xsection', test.metric.metric) : null)
      : k === 'pattern' ? null : ser(test.metric).unit as string | null;
  } else {
    const sg = test.kind === 'event' ? test.signal : test;
    if (!sg.pattern) u = sideUnit(sg.lhs) ?? sideUnit(sg.rhs) ?? anyUnit(sg.lhs) ?? anyUnit(sg.rhs);
  }
  unitMemo.set(key, u);
  return u;
}

/** one condition on one ticker at its last bar */
export function evaluate(m: Market, t: Tk, cd: ConditionDef): { cell: Cell; signal: S | null } {
  const tt = cd.test as any, flow = readsFlow(tt);
  // a flow condition is read at the stock's last session with broker data, its date the cell's (P10 a); without any in
  // the window it is n/a FLOW_UNAVAILABLE without a date, as the worker's core does
  const at = flow ? flowBar(t) : t.c.length - 1;
  if (at < 0) return { cell:{ id:cd.id, status:'na', eval_date:null, unit:unitOf(tt), reason:'FLOW_UNAVAILABLE', remark:null, ...(tt.kind === 'value' || tt.kind === 'window' ? { value:null } : {}) } as Cell, signal:null };
  const eval_date = t.d[at];
  const base = { id:cd.id, eval_date, unit:unitOf(tt), reason:null, remark:null } as Cell;
  const priceDerived = !flow && refsOf(tt).some(r => r.kind === 'indicator' || r.kind === 'transform' || r.kind === 'pattern');
  if (t.breakAt != null && priceDerived && t.breakAt > at - lookback(refsOf(tt))) base.remark = 'PRICE_BREAK_IN_LOOKBACK';
  if (tt.kind === 'value') {
    const v = series(m, t, tt.metric)[at];
    if (!isN(v)) return { cell:{ ...base, status:'na', value:null, reason:'NULL_AT_EVALUATION' }, signal:null };
    return { cell:{ ...base, status:valuePasses(v, tt) ? 'pass' : 'fail', value:v }, signal:null };
  }
  if (tt.kind === 'window') {
    // operators 5, 9, 10: the inner value test on each of the last `length` sessions
    const L = tt.length, it = tt.test, cross = it.kind === 'event' ? it.signal : null;
    const s = series(m, t, cross ? cross.lhs : it.metric), y = cross ? cross.rhs.value : 0;
    let hits = 0, run = 0, open = true, latest = -1, na = 0;
    for (let i = at; i > at - L; i--) {
      const x = i >= 0 ? s[i] : null;
      if (!isN(x) || (cross && !isN(s[i - 1]))) { na++; open = false; continue }
      // an event inside a window: the cross on that session (both bars finite), else the value test
      const ok = cross ? (cross.op === 'crosses_above' ? (s[i - 1]! <= y && x > y) : (s[i - 1]! >= y && x < y)) : valuePasses(x, it);
      if (ok) { hits++; if (latest < 0) latest = i; if (open) run++ } else open = false;
    }
    if (na === L) return { cell:{ ...base, unit:'sessions', status:'na', value:null, reason:'NULL_AT_EVALUATION' }, signal:null };
    const pass = tt.mode === 'ever' ? hits >= 1 : tt.mode === 'at_least' ? hits >= tt.count : run >= L;
    return { cell:{ ...base, unit:'sessions', status:pass ? 'pass' : 'fail', value:tt.mode === 'streak' ? run : hits, event_date:latest >= 0 ? t.d[latest] : null, bars_ago:latest >= 0 ? at - latest : null }, signal:null };
  }
  if (tt.kind === 'state' && tt.pattern) { const s = series(m, t, tt.pattern); return { cell:{ ...base, status:s[at] ? 'pass' : 'fail' }, signal:null } }
  if (tt.kind === 'state') {
    const a = series(m, t, tt.lhs), b = series(m, t, tt.rhs), x = a[at], y = b[at];
    if (!isN(x) || !isN(y)) return { cell:{ ...base, status:'na', lhs:x, rhs:y, reason:'NULL_AT_EVALUATION' }, signal:null };
    return { cell:{ ...base, status:(tt.op === 'gt' ? x > y : x < y) ? 'pass' : 'fail', lhs:x, rhs:y }, signal:null };
  }
  // EVENT: a cross through compare (both sides finite on the bar and the bar before) or a pattern signal
  const sg = tt.signal, n = t.c.length;
  let sig: S;
  if (sg.pattern) sig = series(m, t, sg.pattern);
  else {
    const a = series(m, t, sg.lhs), b = series(m, t, sg.rhs);
    sig = a.map((x, i) => i > 0 && isN(x) && isN(b[i]) && isN(a[i - 1]) && isN(b[i - 1]) ? (sg.op === 'crosses_above' ? (a[i - 1]! <= b[i - 1]! && x > b[i]!) : (a[i - 1]! >= b[i - 1]! && x < b[i]!)) ? 1 : 0 : 0);
  }
  let j = -1;
  for (let i = at; i > at - tt.within && i >= 0; i--) if (sig[i]) { j = i; break }
  let last = -1; for (let i = at; i > at - 130 && i >= 0; i--) if (sig[i]) { last = i; break }
  const cur = sg.pattern ? {} : { lhs:series(m, t, sg.lhs)[at], rhs:series(m, t, sg.rhs)[at] };
  return { cell:{ ...base, status:j >= 0 ? 'pass' : 'fail', ...cur, event_date:j >= 0 ? t.d[j] : null, bars_ago:j >= 0 ? at - j : null, market_sessions_ago:j >= 0 ? at - j : null, last_event_date:last >= 0 ? t.d[last] : null }, signal:sig.slice(-n) };
}

const need = (def: Definition, k: number) => def.logic === 'all' ? k : def.logic === 'any' ? Math.min(1, k) : Math.min(Math.max(1, def.at_least || 1), k);
export function universeRow(m: Market, t: Tk): UniverseRow {
  const i = t.c.length - 1, adv = sma(t.c.map((c, j) => c * t.v[j]), 20)[i];
  return { ticker:t.ticker, name:t.name, sector:t.sector, industry:t.industry, last:t.c[i], chg_1d_pct:(t.c[i] / t.c[i - 1] - 1) * 100, adv20_idr:adv,
    first_bar:t.d[0], last_bar:t.d[i], bars:t.c.length, stale:t.d[i] < m.evalDate, remarks:t.remarks };
}

export function run(m: Market, def: Definition, versions: Versions, data: RunResponse['data']): RunResponse {
  const urows = m.tickers.map(t => universeRow(m, t)), view = universeView(urows, def.universe);
  // metric filters the page cannot evaluate: evaluate them here as value conditions
  const extra = (def.universe.metric_filters || []);
  const elig = view.rows.filter(r => extra.every((f, i) => evaluate(m, m.byTicker.get(r.ticker)!, { id:'f' + i, enabled:true, test:f }).cell.status === 'pass'));
  const active = def.conditions.filter(c => c.enabled), k = need(def, active.length);
  // a flow condition is evaluated at each stock's broker data date, and its summary says so (P5a: source flow, flow_date)
  const summaries: ConditionSummary[] = active.map(c => ({ id:c.id, source:readsFlow(c.test) ? 'flow' : 'dynamic', metric:'', params_resolved:{}, is_default:false, kind:c.test.kind, unit:unitOf(c.test, 'summary'), evaluated:elig.length, passed:0, na:0, exhaustive:true, eval_date_basis:readsFlow(c.test) ? 'flow_date' : 'ticker_last_bar' }));
  const rows: ResultRow[] = [];
  for (const u of elig) {
    const t = m.byTicker.get(u.ticker)!, cells = active.map(c => evaluate(m, t, c).cell);
    cells.forEach((c, i) => { if (c.status === 'pass') summaries[i].passed++; if (c.status === 'na') summaries[i].na++ });
    const met = cells.filter(c => c.status === 'pass').length, match = active.length > 0 && met >= k, near = !match && k >= 2 && met === k - 1;
    if (!active.length || match || near) rows.push({ ticker:u.ticker, name:u.name, sector:u.sector, industry:u.industry, board:null, market_cap:null, last:u.last, chg_1d_pct:u.chg_1d_pct,
      adv20_idr:u.adv20_idr, last_bar_date:u.last_bar, stale:u.stale, remarks:u.remarks, status:match ? 'match' : 'near', met, need:k, na_count:cells.filter(c => c.status === 'na').length, cells });
  }
  const breaks = rows.filter(r => r.remarks.some(x => x.code === 'PRICE_BREAK')).length;
  return { schema_version:1, versions, data, mode:active.length ? 'screen' : 'universe_only',
    universe:{ ...view.counts, eligible:elig.length, filtered_out:view.counts.filtered_out + view.rows.length - elig.length }, conditions:summaries, need:k,
    match_count:rows.filter(r => r.status === 'match').length, near_count:rows.filter(r => r.status === 'near').length, rows,
    warnings:breaks ? [{ code:'PRICE_BREAKS_IN_RESULT', message:`${breaks} rows carry a price-break remark.`, count:breaks }] : [],
    timings_ms:{ queue:0, s0:0, s1:0, s2:0, s3:0, s4:0, total:0 } };
}

const OVERLAY_SHAPES = new Set(['line', 'band', 'dir']);
export function preview(m: Market, def: Definition, ticker: string, versions: Versions, data: PreviewResponse['data'], shapeOf: (id: string) => string | undefined, periods: Record<string, number>): PreviewResponse {
  const t = m.byTicker.get(ticker); if (!t) throw Object.assign(new Error('unknown ticker'), { code:'INVALID_INPUT' });
  const active = def.conditions.filter(c => c.enabled), k = need(def, active.length);
  const ev = active.map(c => evaluate(m, t, c)), cells = ev.map(e => e.cell), met = cells.filter(c => c.status === 'pass').length;
  const inU = universeView([universeRow(m, t)], def.universe).rows.length > 0;
  const status = !inU ? 'outside_universe' : met >= k && active.length ? 'match' : !active.length ? 'match' : k >= 2 && met === k - 1 ? 'near' : 'fail';
  const N = t.c.length, from = Math.max(0, N - 260), sl = <T>(a: T[]) => a.slice(from);
  const off = m.days.length - N, ihsg = m.ihsg.slice(off).map(x => x * 7000);
  const overlays: PreviewResponse['overlays'] = [];
  for (const c of active) {
    const tt = c.test as any, ind = [tt.metric?.of, tt.metric, tt.rhs, tt.lhs, tt.signal?.rhs, tt.signal?.lhs].find(x => x?.kind === 'indicator');
    if (!ind || !OVERLAY_SHAPES.has(shapeOf(ind.indicator) || '')) continue;
    const reg = BY_ID[ind.indicator], o = calculate(reg, barsOf(t), resolveParams(reg, ind.params || {}));
    const outs = shapeOf(ind.indicator) === 'band' ? Object.keys(o).filter(x => !x.startsWith('_')) : [ind.output];
    // each overlay carries the core's unit of that output, as the worker does (EXEC-SCREENER-ADD, ERRORS M368)
    for (const out of outs) if (out !== 'direction') overlays.push({ condition_id:c.id, output:out, unit:unitOf({ kind:'value', metric:{ ...ind, output:out } }), values:sl(Array.from(o[out] || [], x => isN(x) ? x : null)) });
  }
  const markers = active.map((c, i) => ({ condition_id:c.id, bars:(ev[i].signal || []).map((s, j) => s && j >= N - 130 ? { date:t.d[j], kind:'event' } : null).filter(Boolean) as { date: string; kind: string }[] }));
  const perf = Object.fromEntries(Object.entries(periods).map(([p, n]) => [p, N - 1 - n >= 0 ? { stock_pct:(t.c[N - 1] / t.c[N - 1 - n] - 1) * 100, ihsg_pct:(ihsg[N - 1] / ihsg[N - 1 - n] - 1) * 100 } : { stock_pct:null, ihsg_pct:null }])) as PreviewResponse['perf'];
  return { versions, data, ticker, status:status as PreviewResponse['status'], remarks:t.remarks, met, need:k, cells,
    bars:{ d:sl(t.d), o:sl(t.o), h:sl(t.h), l:sl(t.l), c:sl(t.c), v:sl(t.v) }, ihsg_close:sl(ihsg), overlays, markers, perf };
}
