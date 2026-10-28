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
        default: throw new Error('fixture: unknown transform ' + r.fn);
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

/** one condition on one ticker at its last bar */
export function evaluate(m: Market, t: Tk, cd: ConditionDef): { cell: Cell; signal: S | null } {
  const at = t.c.length - 1, tt = cd.test as any, eval_date = t.d[at];
  const base = { id:cd.id, eval_date, reason:null, remark:null } as Cell;
  const priceDerived = refsOf(tt).some(r => r.kind === 'indicator' || r.kind === 'transform' || r.kind === 'pattern');
  if (t.breakAt != null && priceDerived && t.breakAt > at - lookback(refsOf(tt))) base.remark = 'PRICE_BREAK_IN_LOOKBACK';
  if (tt.kind === 'value') {
    const v = series(m, t, tt.metric)[at];
    if (!isN(v)) return { cell:{ ...base, status:'na', value:null, reason:'NULL_AT_EVALUATION' }, signal:null };
    const pass = tt.op === 'gt' ? v > tt.value : tt.op === 'lt' ? v < tt.value : v >= tt.value && v <= tt.value2;
    return { cell:{ ...base, status:pass ? 'pass' : 'fail', value:v }, signal:null };
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
  const summaries: ConditionSummary[] = active.map(c => ({ id:c.id, source:'dynamic', metric:'', params_resolved:{}, is_default:false, kind:c.test.kind, unit:null, evaluated:elig.length, passed:0, na:0, exhaustive:true, eval_date_basis:'ticker_last_bar' }));
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
    for (const out of outs) if (out !== 'direction') overlays.push({ condition_id:c.id, output:out, values:sl(Array.from(o[out] || [], x => isN(x) ? x : null)) });
  }
  const markers = active.map((c, i) => ({ condition_id:c.id, bars:(ev[i].signal || []).map((s, j) => s && j >= N - 130 ? { date:t.d[j], kind:'event' } : null).filter(Boolean) as { date: string; kind: string }[] }));
  const perf = Object.fromEntries(Object.entries(periods).map(([p, n]) => [p, N - 1 - n >= 0 ? { stock_pct:(t.c[N - 1] / t.c[N - 1 - n] - 1) * 100, ihsg_pct:(ihsg[N - 1] / ihsg[N - 1 - n] - 1) * 100 } : { stock_pct:null, ihsg_pct:null }])) as PreviewResponse['perf'];
  return { versions, data, ticker, status:status as PreviewResponse['status'], remarks:t.remarks, met, need:k, cells,
    bars:{ d:sl(t.d), o:sl(t.o), h:sl(t.h), l:sl(t.l), c:sl(t.c), v:sl(t.v) }, ihsg_close:sl(ihsg), overlays, markers, perf };
}
