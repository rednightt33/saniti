/* EXEC-TERMINAL-FLOW-IND (user go 2026-10-30), live: the 39 Flow indicators FL01-FL39 as indicator definitions of the
   generic engine (indicators.ts, the same path as the 53 registry indicators: legend row, settings dialog, undo, saved
   list). Everything about an indicator comes from src/data/flowRegistry.json (generated from the agreed spreadsheet by
   scripts/build_flow_registry.py); the numbers come from calc/flow.ts on the raw broker rows the worker sends
   (ctx.flowRows). Rules of the spreadsheet that need the chart: the default anchor and Broker Inventory's start are the
   first visible candle; "days" are the chart's candles (user 2026-10-30: "2-3 OK"). */
import { classBrokers, computeFlow, defaultInventoryBrokers, type FlowContext, type FlowRows, type InsiderRow } from '../calc/flow';
import REG from '../data/flowRegistry.json';
import type { Ctx } from './context';
import { nfCompact, rupiah } from './context';

export interface FlowRegParam { key: string; label: string; kind: string; status: string; default?: any; options?: any[]; min?: number | null; max?: number | null; text?: string }
export interface FlowRegIndicator { id: string; name: string; family: string; place: 'pane' | 'price' | 'marker'; unit: string; needs_frequency: boolean; outputs: string[]; tip: string; params: FlowRegParam[] }
export const FLOW_REG = REG as unknown as { families: string[]; indicators: FlowRegIndicator[] };

const EMPTY = (N: number): FlowRows => ({ n:0, N, t:new Int32Array(0), b:new Uint16Array(0), inv:new Uint8Array(0), brd:new Uint8Array(0),
  bv:new Float64Array(0), sv:new Float64Array(0), bl:new Float64Array(0), sl:new Float64Array(0), bf:new Float64Array(0), sf:new Float64Array(0),
  brokers:[], has:new Uint8Array(N) });
const SLOTS = ['b1', 'b2', 'b3', 'b4', 'b5'];
/* the rows carry transaction counts (files published before EXEC-TERMINAL-FLOW-IND S2 have none) */
const counts = new WeakMap<FlowRows, boolean>();
const hasCounts = (R: FlowRows) => {
  let v = counts.get(R);
  if (v === undefined) { v = false; for (let k = 0; k < R.n; k++) if (!Number.isNaN(R.bf[k])) { v = true; break } counts.set(R, v) }
  return v;
};
const NF2 = new Intl.NumberFormat('en-US', { minimumFractionDigits:2, maximumFractionDigits:2 });

/** the number shown in the legend and on the axis, from the indicator's unit */
export function flowFormat(unit: string): { fmt: (v: number) => string; minMove: number } {
  switch (unit) {
    case 'IDR/tx': case 'IDR': return { fmt:v => rupiah(v), minMove:1 };
    case 'lot|IDR': return { fmt:v => nfCompact.format(v), minMove:1 };
    case '%': case 'diff': return { fmt:v => v.toFixed(2) + (unit === '%' ? '%' : ''), minMove:.01 };
    case 'x': return { fmt:v => v.toFixed(3) + 'x', minMove:.001 };
    case '0-1': case '-1..1': return { fmt:v => v.toFixed(4), minMove:.0001 };
    case 'days': return { fmt:v => String(Math.round(v)), minMove:1 };
    case 'flag': return { fmt:v => v ? 'Yes' : 'No', minMove:1 };
    default: return { fmt:v => NF2.format(v), minMove:.01 };      // lot/tx, 0-100, price
  }
}

export function initFlowIndicators(ctx: Ctx) {
  const { M, dates, closes, idxByTime } = ctx;
  const tf = M.tf || 'D', word = tf === 'W' ? 'weeks' : tf === 'M' ? 'months' : 'days', letter = tf, one = word.slice(0, -1);
  /* insider rows and the broker classification arrive with the events and reference files */
  let insider: InsiderRow[] = [], classification: Record<string, string> = {};
  M.loadInsider?.().then(rows => {
    insider = rows.flatMap(r => { const time = M.barOf ? M.barOf(r.d) : r.d, t = time == null ? undefined : idxByTime.get(time); return t === undefined ? [] : [{ t, value:r.value }] });
    ctx.refreshFlowIndicators?.();
  }, () => {});
  M.brokerClass?.then(c => { classification = c; ctx.refreshFlowIndicators?.() }, () => {});
  const volume = M.volume.map(v => v.value ?? null);
  let cached: { rows: FlowRows; ins: InsiderRow[]; cls: Record<string, string>; c: FlowContext } | null = null;
  const context = (): FlowContext => {
    const rows = ctx.flowRows || EMPTY(ctx.N);
    if (!cached || cached.rows !== rows || cached.ins !== insider || cached.cls !== classification)
      cached = { rows, ins:insider, cls:classification, c:{ rows, dates, close:closes, volume, insider, classification } };
    return cached.c;
  };
  /* the first visible candle's date (the default anchor and Broker Inventory's start) */
  const firstVisible = () => {
    const r = ctx.chart.timeScale().getVisibleLogicalRange();
    return dates[Math.max(0, Math.min(dates.length - 1, r ? Math.ceil(r.from) : 0))];
  };
  /** a token default (`class:...`, `top3_net_buy_20`) as broker codes, for the settings dialog */
  const brokersOf = (v: any): string[] =>
    Array.isArray(v) ? v : typeof v === 'string' && v.startsWith('class:') ? classBrokers(context(), v.slice(6))
      : v === 'top3_net_buy_20' ? defaultInventoryBrokers(context().rows) : [];

  const relabel = (s: string) => s.replace(/\bdays\b/, word).replace(/\bSessions\b/, tf === 'D' ? 'Sessions' : word[0].toUpperCase() + word.slice(1));
  const scopeText = (p: any) => p.scope === 'all' ? 'All brokers' : p.scope === 'selected'
    ? (Array.isArray(p.brokers) && p.brokers.length ? (p.brokers.length <= 3 ? p.brokers.join(', ') : `${p.brokers.length} brokers`) : 'no broker')
    : `Top ${p.top}${p.rank && p.rank !== 'net_buy' ? (p.rank === 'gross_buy' ? ' gross buy' : ' net sell') : ''}`;
  const filterText = (p: any) => [p.investors && p.investors.length === 1 ? p.investors[0] : '', p.boards && p.boards.length < 3 ? p.boards.join('+') : '']
    .filter(Boolean).join(' · ');

  return FLOW_REG.indicators.map(r => {
    const F = flowFormat(r.unit), byKey = Object.fromEntries(r.params.map(q => [q.key, q]));
    const levels = String(byKey.levels?.default ?? '').split(/[,;\s]+/).filter(Boolean).map(Number).filter(Number.isFinite);
    const plotDefault = byKey.plot?.default === 'hist' ? 'histogram' : 'line';
    const outs = (plot: string) => {
      const kind = r.place === 'marker' ? 'marker' : plot;
      if (r.id === 'FL23') return [...SLOTS.map((k, j) => ({ k, label:`Broker ${j + 1}`, r:kind, role:'numeric_line', vis:true, w:2, rule:'', cond:'' })),
        { k:'total', label:'Total', r:kind, role:'numeric_line', vis:true, w:2, rule:'', cond:'' }];
      return r.outputs.map(k => ({ k, label:k === 'buy' ? 'Buy' : k === 'sell' ? 'Sell' : r.name.split(' · ').pop()!, r:kind, role:'numeric_line', vis:true, w:2, rule:'', cond:'' }));
    };
    const reg = { key:r.id, id:r.id, name:r.name, short:r.name, zone:r.place === 'pane' ? 'panel' : 'overlay', unit:r.unit, outs:outs(plotDefault),
      guides:levels, fill:null, tip:r.tip, info:r.tip + (r.needs_frequency ? ' Needs the transaction counts of the broker files.' : ''), flow:true, place:r.place };
    const inputs = r.params.filter(q => q.key !== 'levels').map(q => {
      const base: any = { key:q.key, label:relabel(q.label), hint:q.status === 'PROPOSED' ? 'Proposed default' : undefined };
      switch (q.kind) {
        case 'select': return { ...base, kind:'select', options:q.options!.map(o => o[0]), labels:Object.fromEntries(q.options!.map(o => [o[0], o[1]])), def:q.default };
        case 'multi': {
          const isBoard = q.key === 'boards', all = isBoard ? ctx.BOARDS : ctx.INVESTORS;
          return { ...base, kind:'multi', def:q.default, options:() => all, all:() => all.map(x => x.id), title:isBoard ? 'Board' : 'Investor' };
        }
        case 'brokers': return { ...base, kind:'brokers', def:q.default, max:q.max ?? undefined, resolve:brokersOf };
        case 'int': return { ...base, kind:'int', min:q.min ?? 1, max:q.max ?? 5000, def:q.default };
        case 'num': return { ...base, kind:'num', min:q.min ?? -1e12, max:q.max ?? 1e12, step:'any', def:q.default };
        case 'bool': return { ...base, kind:'bool', def:!!q.default };
        case 'date': return { ...base, kind:'date', def:'view', first:firstVisible };
        case 'button': return { ...base, kind:'button', reset:['inst', 'retail'] };
        default: return { ...base, kind:'fixed', text:q.text };
      }
    });
    const viewBound = r.params.some(q => q.kind === 'date') || r.id === 'FL23';
    return {
      id:r.id, name:r.name, reg, multi:true, flow:true, viewBound, inputs, style:[], fill:null,
      pane:r.place === 'pane' ? 'sub' : 'overlay', format:F.fmt, minMove:F.minMove,
      outsOf:(p: any) => outs(p.plot === 'hist' ? 'histogram' : p.plot === 'line' ? 'line' : plotDefault),
      compute:(p: any) => {
        const q = { ...p };
        if (q.anchor === 'view' || q.anchor == null) q.anchor = firstVisible();
        if (r.id === 'FL23') q.start = firstVisible();
        const c = context(), o: any = computeFlow(r.id, c, q);
        /* an indicator that reads broker rows is null on every candle without them; one with a value there (prices,
           insider events) gets no broker-data note */
        o._brokerBased = !Object.values(o).some((a: any) => Array.isArray(a) && a.some((v, t) => v !== null && !c.rows.has[t]));
        if (r.id !== 'FL23') return o;
        const codes = Object.keys(o).filter(k => k !== 'total' && !k.startsWith('_')), slots: any = { _labels:codes, _brokerBased:o._brokerBased };
        codes.forEach((c, j) => { slots[SLOTS[j]] = o[c] });
        if (o.total) slots.total = o.total;
        return slots;
      },
      /* the legend's text where the value is empty: why, when the reason is the data (plan S4: a message, not a zero) */
      note:(i: number, raw: any) => {
        const R = ctx.flowRows;
        if (raw && raw._brokerBased === false) return '';
        if (!R) return 'Loading broker data';
        if (!R.n) return 'No broker data for this ticker';
        if (i > ctx.brokerEnd) return 'No broker data yet';
        if (!R.has[i]) return `No broker data on this ${one}`;
        if (r.needs_frequency && !hasCounts(R)) return 'Needs the transaction counts';
        return '';
      },
      validate:(p: any) => {
        if (p.scope === 'selected' && !(Array.isArray(p.brokers) && p.brokers.length)) return 'Choose at least one broker.';
        if (r.id === 'FL34') { const a = new Set(brokersOf(p.inst)); if (brokersOf(p.retail).some(b => a.has(b))) return 'A broker cannot be in both the institutional and the retail list.' }
        if (r.id === 'FL23' && Array.isArray(p.brokers) && (p.brokers.length < 1 || p.brokers.length > 5)) return 'Choose 1 to 5 brokers.';
        return '';
      },
      title:(p: any) => {
        const parts = [r.name];
        if (p.scope) parts.push(scopeText(p));
        if (p.side && p.side !== 'buy') parts.push(p.side === 'both' ? 'Buy & Sell' : 'Sell');
        const f = filterText(p); if (f) parts.push(f);
        if (p.window) parts.push(`${p.window}${letter}`);
        return parts.join(' · ');
      },
    };
  });
}
