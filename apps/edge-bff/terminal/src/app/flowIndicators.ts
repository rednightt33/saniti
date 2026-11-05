/* EXEC-TERMINAL-FLOW-IND (user go 2026-10-30), live: the 39 Flow indicators FL01-FL39 as indicator definitions of the
   generic engine (indicators.ts, the same path as the 53 registry indicators: legend row, settings dialog, undo, saved
   list). Everything about an indicator comes from src/data/flowRegistry.json (generated from the agreed spreadsheet by
   scripts/build_flow_registry.py); the numbers come from calc/flow.ts on the raw broker rows the worker sends
   (ctx.flowRows). Rules of the spreadsheet that need the chart: the default anchor and Broker Inventory's start are the
   first visible candle; "days" are the chart's candles (user 2026-10-30: "2-3 OK"). */
import { classBrokers, computeFlow, defaultInventoryBrokers, flowDefaults, type FlowContext, type FlowRows, type InsiderRow } from '../calc/flow';
import { FLOW_EXPLAIN } from '../calc/explainIndex';
import REG from '../data/flowRegistry.json';
import type { Ctx } from './context';
import { nfCompact, rupiah } from './context';
import * as spec from '../data/specFormat';
import { INV_COLORS } from './broker';
import { markerOnCandles, onCandles } from '../data/timeframe';

export interface FlowRegParam { key: string; label: string; kind: string; status: string; default?: any; options?: any[]; min?: number | null; max?: number | null; text?: string }
export interface FlowRegIndicator { id: string; name: string; family: string; place: 'pane' | 'price' | 'marker'; unit: string; needs_frequency: boolean; outputs: string[]; tip: string; params: FlowRegParam[] }
export const FLOW_REG = REG as unknown as { families: string[]; indicators: FlowRegIndicator[] };
/* EXEC-IHSG-FLOW (user go 2026-11-03: "Sembunyikan. FL28 tetap hitung"): the Flow indicators that read one security's
   lots or its Rupiah-per-share average price. On an index (the market aggregate of every stock) they are hidden
   (data/inputs.ts 'single'): lots of different stocks do not add up (2 Nov: GOTO 43.1 M lots = Rp104 bn, BUMI 38.2 M lots
   = Rp482 bn), a Rupiah-per-share VWAP is not the index level, an index has no volume and no insider. Review in EXEC.md. */
export const SINGLE_SECURITY = new Set(['FL01', 'FL03', 'FL05', 'FL06', 'FL07', 'FL08', 'FL09', 'FL13', 'FL14', 'FL15',
  'FL17', 'FL18', 'FL19', 'FL20', 'FL27', 'FL31', 'FL39']);
/** on an index: what the indicator means there (the "bandar" ones: the brokers that drive the market's net flow) */
const INDEX_NOTE: Record<string, string> = {
  FL24:' Pada indeks (IHSG): broker penggerak arus bersih seluruh pasar, bukan bandar satu saham.',
  FL25:' Pada indeks (IHSG): broker penggerak arus bersih seluruh pasar, bukan bandar satu saham.',
  FL29:' Pada indeks (IHSG): broker penggerak arus bersih seluruh pasar, bukan bandar satu saham.',
  FL23:' Pada indeks (IHSG) hanya dalam Rupiah: lot berbagai saham tidak bisa dijumlahkan.',
  FL28:' Pada indeks (IHSG): jumlah nilai beli semua broker per hari, karena indeks tidak punya volume.',
};

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

/** K4: a parameter choice that counts transactions (a measure or unit 'tx') needs the broker files' counts */
export const needsCounts = (p: any) => !!p && Object.values(p).some(v => v === 'tx');
/** EXEC-TERMINAL-IND-EDIT (aturan IHSG, user 2026-11-05): the options a select offers; on an index no Lot */
export const offeredOptions = (q: FlowRegParam, onIndex: boolean) => (q.options || []).filter(o => !(onIndex && o[0] === 'lot'));
/** on an index a saved or default Lot reads as the select's next option (Rupiah); the parameters are changed in place */
export function withoutLot(params: FlowRegParam[], p: any, onIndex: boolean) {
  if (onIndex) for (const f of params) if (f.kind === 'select' && p[f.key] === 'lot') { const os = offeredOptions(f, true); p[f.key] = (os.find(o => o[0] === 'value') ?? os[0])?.[0] }
  return p;
}

/** the number shown in the legend and on the axis, from the indicator's unit */
export function flowFormat(unit: string): { fmt: (v: number) => string; minMove: number } {
  /* EDGE Design Spec v1.2 section 6 (user 2026-11-01): data/specFormat.ts; a flag still reads Yes/No */
  switch (unit) {
    case 'IDR/tx': case 'IDR': return { fmt:spec.idr, minMove:1 };
    case 'lot|IDR': return { fmt:spec.compact, minMove:1 };
    case '%': return { fmt:spec.pctLevel, minMove:.01 };
    case 'x': return { fmt:spec.ratio, minMove:.001 };
    case '0-1': case '-1..1': case 'diff': return { fmt:v => spec.smart(v, 2), minMove:.0001 };   // diff: HHI buy - sell (Reviewer B, B5)
    case 'days': return { fmt:v => spec.num(Math.round(v), 0), minMove:1 };
    case 'flag': return { fmt:v => v ? 'Yes' : 'No', minMove:1 };
    default: return { fmt:spec.indicator, minMove:.01 };      // lot/tx, 0-100, price
  }
}

export function initFlowIndicators(ctx: Ctx) {
  const { M, idxByTime } = ctx;
  /* EXEC-INTRADAY-FEATURES C4 (user 2026-11-01, "Opsi 1"): on an intraday chart the Flow indicators are computed on the
     daily sessions, as on the daily chart, and drawn on the candles that show each session (timeframe.ts dayOfCandles) */
  const DAY = M.intraday;
  const dates = DAY ? DAY.days : ctx.dates, closes = DAY ? DAY.daily.map(r => r.c) : ctx.closes;
  const tf = DAY ? 'D' : M.tf || 'D', word = tf === 'W' ? 'weeks' : tf === 'M' ? 'months' : 'days', letter = tf, one = word.slice(0, -1);
  const firstOn = (d: string) => { let lo = 0, hi = dates.length; while (lo < hi) { const m = (lo + hi) >> 1; if (dates[m] < d) lo = m + 1; else hi = m } return lo < dates.length ? lo : undefined };
  /* insider rows and the broker classification arrive with the events and reference files */
  let insider: InsiderRow[] = [], classification: Record<string, string> = {};
  M.loadInsider?.().then(rows => {
    insider = rows.flatMap(r => { const time = DAY ? null : M.barOf ? M.barOf(r.d) : r.d, t = DAY ? firstOn(r.d) : time == null ? undefined : idxByTime.get(time); return t === undefined ? [] : [{ t, value:r.value }] });
    ctx.refreshFlowIndicators?.();
  }, () => {});
  let classState: 'loading' | 'ready' | 'missing' = M.brokerClass ? 'loading' : 'missing';
  M.brokerClass?.then(c => { classification = c; classState = Object.keys(c).length ? 'ready' : 'missing'; ctx.refreshFlowIndicators?.() },
    () => { classState = 'missing'; ctx.refreshFlowIndicators?.() });
  // a candle without volume in the source is null here, never the histogram's 0 (an index: FL28 read "Rp 0", audit 2026-10-30)
  const volume = DAY ? DAY.daily.map(r => r.v ?? null) : M.volume.map(v => v.none ? null : v.value ?? null), noVolume = volume.every(v => v === null);
  /* an indicator that does not read broker rows (prices, insider events): derived once by computing it with no broker rows
     on prices and volumes of 1, not listed */
  const ones = dates.map(() => 1), probe: FlowContext = { rows:EMPTY(dates.length), dates, close:ones, volume:ones, insider:[], classification:{} };
  const brokerFree = new Map<string, boolean>();
  const isBrokerFree = (r: FlowRegIndicator) => {
    let v = brokerFree.get(r.id);
    if (v === undefined) {
      const p = Object.fromEntries(r.params.filter(q => q.default !== undefined).map(q => [q.key, q.default]));
      v = Object.values(computeFlow(r.id, probe, p)).some((a: any) => Array.isArray(a) && a.some(x => x !== null));
      brokerFree.set(r.id, v);
    }
    return v;
  };
  let cached: { rows: FlowRows; ins: InsiderRow[]; cls: Record<string, string>; c: FlowContext } | null = null;
  const context = (): FlowContext => {
    const rows = ctx.flowRows || EMPTY(dates.length);
    if (!cached || cached.rows !== rows || cached.ins !== insider || cached.cls !== classification)
      cached = { rows, ins:insider, cls:classification, c:{ rows, dates, close:closes, volume, insider, classification, index:!!ctx.M.index } };
    return cached.c;
  };
  /* the first visible candle's date (the default anchor and Broker Inventory's start) */
  const firstVisible = () => {
    const r = ctx.chart.timeScale().getVisibleLogicalRange(), cd = ctx.dates;
    return cd[Math.max(0, Math.min(cd.length - 1, r ? Math.ceil(r.from) : 0))].slice(0, 10);    // a candle's session date
  };
  /* the daily outputs on the candles: a value on every candle of its day, a marker once */
  const toCandles = (o: any, marker: boolean) => {
    if (!DAY) return o;
    const out: any = {};
    for (const k of Object.keys(o)) out[k] = Array.isArray(o[k]) ? (marker ? markerOnCandles : onCandles)(o[k], DAY.dayOf) : o[k];
    return out;
  };
  /** a token default (`class:...`, `top3_net_buy_20`) as broker codes, for the settings dialog */
  const brokersOf = (v: any): string[] =>
    Array.isArray(v) ? v : typeof v === 'string' && v.startsWith('class:') ? classBrokers(context(), v.slice(6))
      : v === 'top3_net_buy_20' ? defaultInventoryBrokers(context().rows) : [];

  const tokenLabel = (v: string) => v.startsWith('class:') ? v.slice(6) : v === 'top3_net_buy_20' ? 'Top 3 net buyers, last 20' : v;
  const per = tf === 'W' ? 'weekly' : tf === 'M' ? 'monthly' : 'daily';
  /* a candle is a "day" (user 2026-10-30: "2-3 OK"); on weekly and monthly charts the words follow the candle (Reviewer B,
     B2, B3: "Rolling weeks (1 = daily)", "Average Daily Value · 20W") */
  const relabel = (s: string) => s.replace(/\bdays\b/, word).replace(/\bSessions\b/, tf === 'D' ? 'Sessions' : word[0].toUpperCase() + word.slice(1))
    .replace(/\(1 = daily\)/, `(1 = ${per})`).replace(/\bDaily\b/, per[0].toUpperCase() + per.slice(1));
  /* EXEC-TERMINAL-IND-EDIT (user 2026-11-05): the cohort in words. With a Side (R1) the Rank is Net or Gross and the side
     says buyers or sellers ("Top 3 net sellers"); without one the Rank says who ("Top 3 net sellers" = rank Net sell) */
  const scopeText = (p: any, sided: boolean) => {
    if (p.scope === 'all') return 'All brokers';
    if (p.scope === 'selected') return Array.isArray(p.brokers) && p.brokers.length ? (p.brokers.length <= 3 ? p.brokers.join(', ') : `${p.brokers.length} brokers`) : 'no broker';
    const gross = p.rank === 'gross_buy' || p.rank === 'gross_sell';
    if (sided) return `Top ${p.top} ${gross ? 'gross' : 'net'} ${p.side === 'sell' ? 'sellers' : p.side === 'both' ? 'buyers & sellers' : 'buyers'}`;
    return `Top ${p.top} ${p.rank === 'gross_buy' ? 'gross buyers' : p.rank === 'net_sell' ? 'net sellers' : 'net buyers'}`;
  };
  const filterText = (p: any) => [p.investors && p.investors.length === 1 ? p.investors[0] : '', p.boards && p.boards.length < 3 ? p.boards.join('+') : '']
    .filter(Boolean).join(' · ');

  return FLOW_REG.indicators.map(r => {
    const F = flowFormat(r.unit), byKey = Object.fromEntries(r.params.map(q => [q.key, q]));
    const levels = String(byKey.levels?.default ?? '').split(/[,;\s]+/).filter(Boolean).map(Number).filter(Number.isFinite);
    const plotDefault = byKey.plot?.default === 'hist' ? 'histogram' : 'line';
    const outs = (plot: string, p?: any) => {
      const kind = r.place === 'marker' ? 'marker' : plot;
      /* Broker Inventory: the panel's inventory colours, the total in ink (front-end audit 2026-10-30: two orange lines) */
      if (r.id === 'FL23') return [...SLOTS.map((k, j) => ({ k, label:`Broker ${j + 1}`, r:kind, role:'numeric_line', vis:true, w:2, rule:'', cond:'', color:INV_COLORS[j] })),
        { k:'total', label:'Total', r:kind, role:'numeric_line', vis:true, w:2, rule:'', cond:'', color:'#171717' }];
      /* to-do 18: FL27's broker triggers are optional marks, off until turned on in the Style tab; to-do 12: FL29's size */
      const extra: Record<string, any> = { net:{ label:'Net trigger', vis:false }, gross:{ label:'Gross trigger', vis:false }, balance:{ label:'Balance %' } };
      return r.outputs.map(k => extra[k] ? { k, r:kind, role:'numeric_line', vis:true, w:2, rule:'', cond:'', ...extra[k] } : k === 'change'
        /* EXEC-TERMINAL-IND-EDIT (FL34 to-do 17, FL11 U2): the change line is a line on its own scale (left), in points */
        ? { k, label:'Change', r:'line', role:'numeric_line', vis:true, w:2, rule:'', cond:'', scale:'left', fmt:spec.points, minMove:.01 }
        : { k, label:k === 'buy' ? 'Buy' : k === 'sell' ? 'Sell' : r.name.split(' · ').pop()!, r:kind, role:'numeric_line', vis:true, w:2, rule:'', cond:'',
            /* U3: a share minus the even share reads in points; U6: a count of brokers; U1: a z-score */
            ...(p && p.even ? { fmt:spec.points, minMove:.01 } : p && p.measure === 'count' ? { fmt:(v: number) => spec.num(v, 0), minMove:1 }
              : p && p.stat === 'z' ? { fmt:(v: number) => spec.smart(v, 2), minMove:.01 } : {}) });
    };
    const note = ctx.M.index ? INDEX_NOTE[r.id] || '' : '';
    const reg = { key:r.id, id:r.id, name:r.name, short:r.name, zone:r.place === 'pane' ? 'panel' : 'overlay', unit:r.unit, outs:outs(plotDefault),
      guides:levels, levelsParam:!!byKey.levels, fill:null, tip:r.tip + note, info:r.tip + note + (r.needs_frequency ? ' Membutuhkan jumlah transaksi (frekuensi) di file broker.' : ''), flow:true, place:r.place };
    /* a field that only applies to one broker scope is shown only with it (audit I8: "Brokers: None" beside Top-N) */
    const hasScope = r.params.some(q => q.key === 'scope');
    const topnOnly = hasScope ? { when:(p: any) => (p.scope ?? 'topn') === 'topn' } : {};
    /* EXEC-IHSG-FLOW, EXEC-TERMINAL-IND-EDIT (user 2026-11-05 "Ok, masukan exec"): an index has no lots (lots of different
       stocks do not add up), so on an index a choice of Lot is not offered and a saved Lot reads as the next choice
       (Rupiah); a choice left with one option is not shown (FL23's unit). Derived from the options, not listed by id. */
    const onIndex = !!ctx.M.index;
    const noLot = (q: any) => withoutLot(r.params, q, onIndex), optionsOf = (q: FlowRegParam) => offeredOptions(q, onIndex);
    const inputs = r.params.filter(q => q.key !== 'levels' && !(q.kind === 'select' && onIndex && optionsOf(q).length < 2)).map(q => {
      const base: any = { key:q.key, label:relabel(q.label), hint:q.status === 'PROPOSED' ? 'Proposed default' : undefined,
        ...(['top', 'rank', 'ranking'].includes(q.key) ? topnOnly : {}) };
      switch (q.kind) {
        case 'select': { const os = optionsOf(q), def = os.some(o => o[0] === q.default) ? q.default : os[0]?.[0];
          return { ...base, kind:'select', options:os.map(o => o[0]), labels:Object.fromEntries(os.map(o => [o[0], o[1]])), def } }
        case 'multi': {
          const isBoard = q.key === 'boards', all = isBoard ? ctx.BOARDS : ctx.INVESTORS;
          return { ...base, kind:'multi', def:q.default, options:() => all, all:() => all.map(x => x.id), title:isBoard ? 'Board' : 'Investor' };
        }
        case 'brokers': return { ...base, kind:'brokers', def:q.default, max:q.max ?? undefined, resolve:brokersOf, tokenLabel,
          ...(hasScope ? { when:(p: any) => p.scope === 'selected' } : {}) };
        case 'int': return { ...base, kind:'int', min:q.min ?? 1, max:q.max ?? 5000, def:q.default };
        case 'num': return { ...base, kind:'num', min:q.min ?? -1e12, max:q.max ?? 1e12, minExclusive:!!(q as any).min_exclusive, step:'any', def:q.default };
        case 'bool': return { ...base, kind:'bool', def:!!q.default };
        case 'date': return { ...base, kind:'date', def:'view', first:firstVisible };
        case 'button': return { ...base, kind:'button', reset:['inst', 'retail'] };
        default: return { ...base, kind:'fixed', text:q.text };
      }
    });
    const viewBound = r.params.some(q => q.kind === 'date') || r.id === 'FL23';
    return {
      id:r.id, name:r.name, reg, multi:true, flow:true, single:SINGLE_SECURITY.has(r.id), viewBound, inputs, style:[], fill:null,
      pane:r.place === 'pane' ? 'sub' : 'overlay', format:F.fmt, minMove:F.minMove,
      outsOf:(p: any) => outs(p.plot === 'hist' ? 'histogram' : p.plot === 'line' ? 'line' : plotDefault, p),
      compute:(p: any) => {
        const q = { ...p };
        if (q.anchor === 'view' || q.anchor == null) q.anchor = firstVisible();
        if (r.id === 'FL23') q.start = firstVisible();
        noLot(q);
        const o: any = toCandles(computeFlow(r.id, context(), q), r.place === 'marker');
        if (r.id !== 'FL23') return o;
        const codes = Object.keys(o).filter(k => k !== 'total'), slots: any = { _labels:codes };
        codes.forEach((c, j) => { slots[SLOTS[j]] = o[c] });
        if (o.total) slots.total = o.total;
        return slots;
      },
      /* EXEC-IND-CARDS: how the value at candle t is made (the card), on the session the candle shows; undefined = no
         explainer, null = no value at t. The parameters the settings dialog does not show (levels) take their defaults. */
      explain:(p: any, t: number, out?: string) => {
        const ex = FLOW_EXPLAIN[r.id]; if (!ex) return undefined;
        // as computeFlow: a parameter left undefined takes its default
        const q: any = { ...flowDefaults(r.id), ...Object.fromEntries(Object.entries(p || {}).filter(([, v]) => v !== undefined)) };
        if (q.anchor === 'view' || q.anchor == null) q.anchor = firstVisible();
        if (r.id === 'FL23') q.start = firstVisible();
        noLot(q);
        const d = DAY ? DAY.dayOf[t] : t;
        return d < 0 ? null : ex(context(), q, d, out);
      },
      /* the legend's text where the value is empty: why, when the reason is the data (plan S4: a message, not a zero) */
      note:(i: number, raw: any, p: any) => {
        const R = ctx.flowRows;
        if (isBrokerFree(r)) return noVolume ? 'No volume for this ticker' : '';
        /* a list given as a classification (FL34) waits for the reference file's classes */
        const usesClass = p && Object.values(p).some(v => typeof v === 'string' && v.startsWith('class:'));
        if (usesClass && classState !== 'ready') return classState === 'loading' ? 'Loading the broker classification' : 'No broker classification published yet';
        if (!R) return 'Loading broker data';
        if (!R.n) return 'No broker data for this ticker';
        if (i > ctx.brokerEnd) return 'No broker data yet';
        const di = DAY ? DAY.dayOf[i] : i;
        if (di < 0 || !R.has[di]) return `No broker data on this ${one}`;
        /* K4 (user 2026-11-05 "3 ok"): a choice that counts transactions needs them; the others draw without them */
        if ((r.needs_frequency || needsCounts(p)) && !hasCounts(R)) return r.needs_frequency ? 'Needs the transaction counts'
          : 'No transaction counts for this ticker: choose Value or Lot';
        return '';
      },
      validate:(p: any) => {
        if (p.scope === 'selected' && !(Array.isArray(p.brokers) && p.brokers.length)) return 'Choose at least one broker.';
        if (r.id === 'FL34') { const a = new Set(brokersOf(p.inst)); if (brokersOf(p.retail).some(b => a.has(b))) return 'A broker cannot be in both the institutional and the retail list.' }
        if (r.id === 'FL23' && Array.isArray(p.brokers) && (p.brokers.length < 1 || p.brokers.length > 5)) return 'Choose 1 to 5 brokers.';
        return '';
      },
      /* Design Spec v1.2: the parameters in parentheses, "Bandar Balance · % (Top 3, 10D)" */
      title:(p: any) => {
        const parts = [relabel(r.name)];
        if (DAY) parts.push('Daily');
        const sided = r.params.some(q => q.key === 'side');
        if (p.scope) parts.push(scopeText(p, sided));
        if (p.side && p.side !== 'buy' && !(sided && p.scope === 'topn')) parts.push(p.side === 'both' ? 'Buy & Sell' : 'Sell');
        const f = filterText(p); if (f) parts.push(f);
        if (p.window) parts.push(`${p.window}${letter}`);
        return spec.titled(parts[0], parts.slice(1));
      },
    };
  });
}
