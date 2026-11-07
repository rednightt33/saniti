/* EXEC-TERMINAL-FLOW-IND (user go 2026-10-30), live: the 39 Flow indicators FL01-FL39 as indicator definitions of the
   generic engine (indicators.ts, the same path as the 53 registry indicators: legend row, settings dialog, undo, saved
   list). Everything about an indicator comes from src/data/flowRegistry.json (generated from the agreed spreadsheet by
   scripts/build_flow_registry.py); the numbers come from calc/flow.ts on the raw broker rows the worker sends
   (ctx.flowRows). Rules of the spreadsheet that need the chart: the default anchor and Broker Inventory's start are the
   first visible candle; "days" are the chart's candles (user 2026-10-30: "2-3 OK"). */
import { autoInventoryBrokers, boardIndex, classBrokers, computeFlow, defaultInventoryBrokers, investorIndex, type FlowContext, type FlowRows, type InsiderRow } from '../calc/flow';
import REG from '../data/flowRegistry.json';
import type { Ctx } from './context';
import { nfCompact, rupiah, visibleBars } from './context';
import { longDay } from '../ui/calendar';
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
/** EXEC-FLOW-PANE-FILTERS (user go 2026-11-06): the choices shown on a Flow indicator's legend row, in this order, when the
    indicator has them (Broker Inventory 2026-11-06: brokers, boards, investors). FL46's two sides use prefixed keys
    (num_, den_), so it gets none and keeps its settings dialog; the others (window, baseline, unit, levels, Side) stay
    in the dialog. */
export const PANE_FILTER_KEYS = ['scope', 'top', 'rank', 'brokers', 'boards', 'investors'] as const;
/** QA M2: the whole market's cohort (every broker, both investor types). EXEC-QA5-FIX (QA 2026-11-07, agent 5 F4): an
    indicator without a broker choice at all (no scope, no Top N, no brokers: FL32, FL40) reads the whole market too */
export const allBrokersBothSides = (p: any, marketWide = false) => !!p && (p.scope === 'all' || (marketWide && p.scope === undefined))
  && (!Array.isArray(p.investors) || p.investors.length >= 2);
/** the two sides of the whole market over both investor types are the same trades: a buy side equal to its sell side */
export const sidesEqual = (o: any) => Array.isArray(o?.buy) && Array.isArray(o?.sell) && o.buy.some((v: any) => v !== null)
  && o.buy.every((v: any, i: number) => v === o.sell[i] || (v !== null && o.sell[i] !== null && Math.abs(v - o.sell[i]) <= 1e-9 * Math.max(1, Math.abs(v))));
/** a result with no finite non-zero value in any output series (all 0 or empty) */
/** QA round 2 (R2-M1, 2026-11-06): a result that carries nothing: it has values and every value is the same (0 for a net,
    a flat 50 for the percentile of a constant 0). An empty result (too little history) is not this case: it gets the
    history note instead */
export const carriesNothing = (o: any) => {
  const series = Object.values(o || {}).filter(Array.isArray) as any[][];
  let first: number | null = null;
  for (const a of series) for (const v of a) {
    if (v === null || v === undefined || !Number.isFinite(v)) continue;
    if (first === null) first = v; else if (Math.abs(v - first) > 1e-9 * Math.max(1, Math.abs(first))) return false;
  }
  return first !== null;
};
/** the first candle with a value in any output, or -1 */
export const firstValueAt = (o: any) => {
  let f = -1;
  for (const a of Object.values(o || {}).filter(Array.isArray) as any[][]) {
    const k = a.findIndex(v => v !== null && v !== undefined && Number.isFinite(v));
    if (k >= 0 && (f < 0 || k < f)) f = k;
  }
  return f;
};
/** EXEC-TERMINAL-LOOK-2 (3): a list the user emptied (Clear) draws nothing and says what to choose */
export function emptyChoice(p: any): string {
  if (!p) return '';
  const brokersShown = p.scope === undefined || p.scope === 'selected';
  if (brokersShown && Array.isArray(p.brokers) && !p.brokers.length && 'brokers' in p) return 'Choose at least one broker';
  if (Array.isArray(p.boards) && !p.boards.length) return 'Choose at least one board';
  if (Array.isArray(p.investors) && !p.investors.length) return 'Choose at least one investor';
  return '';
}
export const SINGLE_SECURITY = new Set(['FL01', 'FL03', 'FL05', 'FL06', 'FL07', 'FL08', 'FL09', 'FL13', 'FL14', 'FL15',
  'FL17', 'FL18', 'FL19', 'FL20', 'FL27', 'FL31', 'FL39',
  /* EXEC-TERMINAL-IND-EDIT (user 2026-11-05 "Ok, masukan exec"): the new ones built on a Rupiah-per-share price */
  'FL42', 'FL43', 'FL44', 'FL45']);
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
/* the candles with a broker row that has no transaction counts */
const missing = new WeakMap<FlowRows, Uint8Array>();
const missingAt = (R: FlowRows) => {
  let m = missing.get(R);
  if (!m) { m = new Uint8Array(R.N); for (let k = 0; k < R.n; k++) if (Number.isNaN(R.bf[k]) || Number.isNaN(R.sf[k])) m[R.t[k]] = 1; missing.set(R, m) }
  return m;
};
const hasCounts = (R: FlowRows) => {
  let v = counts.get(R);
  if (v === undefined) { v = false; for (let k = 0; k < R.n; k++) if (!Number.isNaN(R.bf[k])) { v = true; break } counts.set(R, v) }
  return v;
};
const NF2 = new Intl.NumberFormat('en-US', { minimumFractionDigits:2, maximumFractionDigits:2 });

/** title(): the selects named elsewhere or not changing the number */
const TITLE_SKIP = /^(scope|brokers|top|rank|ranking|side|plot|boards|investors|levels|lag|num_.*|den_.*)$/;
/** EXEC-QA5-FIX (QA 2026-11-07, Q3/F3/F2-12): selects that say what the number is, named even at their default (FL15 lots
    and FL16 Rupiah read the same title before) */
const TITLE_ALWAYS = /^(unit|measure)$/;
/** a date as the title shows it: "28 Oct 2025" */
const dayText = (d: string) => longDay(d);
const MEASURE_TEXT: Record<string, string> = { gross_buy:'Gross buy', gross_sell:'Gross sell', net_buy:'Net buy', net_sell:'Net sell' };
/** one side of FL46 in short: "Gross buy · Top 3 · Foreign" */
export function ratioSideText(p: any, pre: string): string {
  const scope = p[pre + 'scope'] ?? 'all', inv = p[pre + 'investors'], brd = p[pre + 'boards'];
  const who = scope === 'topn' ? `Top ${p[pre + 'top'] ?? 3}` : scope === 'selected' ? ((p[pre + 'brokers'] || []).join(', ') || 'no broker') : 'all';
  return [MEASURE_TEXT[p[pre + 'measure']] || 'Gross buy', who, Array.isArray(inv) && inv.length === 1 ? inv[0] : '', Array.isArray(brd) && brd.length && brd.length < 3 ? brd.join('+') : '']
    .filter(Boolean).join(' · ');
}
/** FL46 Flow Ratio's gates (to-do 20, user 2026-11-05; AGENTS.md "Gates and evidence": the rule is shown in the dialog,
    the message says where and how to fix it). A net measure of every broker with both investor types is always 0 (each
    buy has a seller); selected brokers need at least one. */
export function ratioRefusal(p: any): string {
  const key = (pre: string) => JSON.stringify(['measure', 'scope', 'brokers', 'top', 'rank', 'boards', 'investors'].map(k => p[pre + k]));
  const allBoth = (pre: string) => (p[pre + 'scope'] ?? 'all') === 'all' && Array.isArray(p[pre + 'investors']) && p[pre + 'investors'].length === 2;
  for (const [pre, side] of [['num_', 'Numerator'], ['den_', 'Denominator']] as const) {
    const scope = p[pre + 'scope'] ?? 'all', inv = p[pre + 'investors'], brd = p[pre + 'boards'];
    if (Array.isArray(inv) && !inv.length) return `${side}: choose at least one investor type.`;
    if (Array.isArray(brd) && !brd.length) return `${side}: choose at least one market board.`;
    if (scope === 'selected' && !(Array.isArray(p[pre + 'brokers']) && p[pre + 'brokers'].length)) return `${side}: choose at least one broker, or another broker scope.`;
    if (String(p[pre + 'measure']).startsWith('net') && allBoth(pre))
      return `${side}: a net measure of all brokers over both investor types is always 0 (every buy has a seller). Choose one investor type, a Top-N cohort or selected brokers.`;
  }
  if (key('num_') === key('den_')) return 'The numerator and the denominator are the same, so the ratio is always 100%. Change a measure, a broker scope or a filter on one side.';
  if (allBoth('num_') && allBoth('den_') && JSON.stringify(p.num_boards) === JSON.stringify(p.den_boards)
    && [p.num_measure, p.den_measure].every(m => m === 'gross_buy' || m === 'gross_sell'))
    return 'Gross buy and gross sell of all brokers over both investor types are equal (every buy has a seller), so the ratio is always 100%. Narrow one side to a group of brokers or an investor type.';
  return '';
}
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
  /* EXEC-QA5-FIX (QA F2-03): an events file that could not be read is "not available", never "Rp 0" */
  let insiderState: 'loading' | 'ready' | 'missing' = M.loadInsider ? 'loading' : 'missing';
  M.loadInsider?.().then(rows => {
    insider = rows.flatMap(r => { const time = DAY ? null : M.barOf ? M.barOf(r.d) : r.d, t = DAY ? firstOn(r.d) : time == null ? undefined : idxByTime.get(time); return t === undefined ? [] : [{ t, value:r.value }] });
    insiderState = 'ready'; ctx.refreshFlowIndicators?.();
  }, () => { insiderState = 'missing'; ctx.refreshFlowIndicators?.() });
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
  /* an indicator that reads the insider events (FL31): derived by computing it with one made-up insider row, not listed */
  const insiderUse = new Map<string, boolean>();
  const usesInsider = (r: FlowRegIndicator) => {
    let v = insiderUse.get(r.id);
    if (v === undefined) {
      const p = Object.fromEntries(r.params.filter(q => q.default !== undefined).map(q => [q.key, q.default]));
      const a = JSON.stringify(computeFlow(r.id, probe, p)), b = JSON.stringify(computeFlow(r.id, { ...probe, insider:[{ t:0, value:1 }] }, p));
      v = a !== b; insiderUse.set(r.id, v);
    }
    return v;
  };
  /* the first candle with broker rows (before it: "before the broker data", QA agent 5 F9) */
  const firstBroker = () => { const R = ctx.flowRows; if (!R) return -1; for (let k = 0; k < R.N; k++) if (R.has[k]) return k; return -1 };
  /* the first broker session's own date (re-test N7: a weekly candle's date is its Monday, 29 Dec, not the 2 Jan session) */
  const firstBrokerDay = () => { const d0 = M.broker?.dates?.[0], fb = firstBroker(); return d0 || (fb >= 0 ? dates[fb].slice(0, 10) : '') };
  /* EXEC-QA5-FIX (QA Q2, F2-12): rows that pass the indicator's own board and investor choice in candles a..b */
  const filterHasRows = (p: any, a: number, b: number) => {
    const R = ctx.flowRows; if (!R) return true;
    const bs = Array.isArray(p?.boards) ? new Set(p.boards.map(boardIndex)) : null, is = Array.isArray(p?.investors) ? new Set(p.investors.map(investorIndex)) : null;
    if (!bs && !is) return true;
    for (let k = 0; k < R.n; k++) { const t = R.t[k]; if (t < a || t > b) continue; if ((!bs || bs.has(R.brd[k])) && (!is || is.has(R.inv[k]))) return true }
    return false;
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
    const cd = ctx.dates;                                   // the same "in view" rule as the broker windows (visibleBars)
    return cd[visibleBars(ctx.chart.timeScale().getVisibleLogicalRange(), cd.length)[0]].slice(0, 10);    // a candle's session date
  };
  /* the daily outputs on the candles: a value on every candle of its day, a marker once */
  const toCandles = (o: any, marker: boolean) => {
    if (!DAY) return o;
    const out: any = {};
    for (const k of Object.keys(o)) out[k] = Array.isArray(o[k]) ? (marker ? markerOnCandles : onCandles)(o[k], DAY.dayOf) : o[k];
    return out;
  };
  /** a token default (`class:...`, `top3_net_buy_20`, `auto_c`) as broker codes, for the settings dialog; `auto_c` (FL23,
      EXEC-BROKER-INV-PANEL option C) reads the candles on screen and the indicator's own boards and investors */
  const brokersOf = (v: any, p?: any): string[] =>
    Array.isArray(v) ? v : typeof v === 'string' && v.startsWith('class:') ? classBrokers(context(), v.slice(6))
      : v === 'top3_net_buy_20' ? defaultInventoryBrokers(context().rows)
      : v === 'auto_c' ? (ctx.flowRows?.n ? autoInventoryBrokers(context(), { start:firstVisible(), boards:p?.boards, investors:p?.investors }) : []) : [];

  const tokenLabel = (v: string) => v.startsWith('class:') ? v.slice(6) : v === 'top3_net_buy_20' ? 'Top 3 net buyers, last 20'
    : v === 'auto_c' ? '2 net buyers + 1 net seller on screen' : v;
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
    const one = Number(p.top) === 1, pl = (w: string) => one ? w.replace(/s$/, '') : w;     // QA Q7: "Top 1 net buyer"
    if (sided) return `Top ${p.top} ${gross ? 'gross' : 'net'} ${p.side === 'sell' ? pl('sellers') : p.side === 'both' ? (one ? 'buyer & seller' : 'buyers & sellers') : pl('buyers')}`;
    return `Top ${p.top} ${pl(p.rank === 'gross_buy' ? 'gross buyers' : p.rank === 'net_sell' ? 'net sellers' : 'net buyers')}`;
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
      // QA F2-12: Rupiah positions read "Rp 12.5B", lots stay compact
      const inv = (p ? (p.unit ?? byKey.unit?.default) : byKey.unit?.default) === 'value' || ctx.M.index ? { fmt:spec.idr, fk:'idr' } : {};
      if (r.id === 'FL23') return [...SLOTS.map((k, j) => ({ k, label:`Broker ${j + 1}`, r:kind, role:'numeric_line', vis:true, w:2, rule:'', cond:'', color:INV_COLORS[j], ...inv })),
        { k:'total', label:'Total', r:kind, role:'numeric_line', vis:true, w:2, rule:'', cond:'', color:'#171717', ...inv }];
      /* to-do 18: FL27's broker triggers are optional marks, off until turned on in the Style tab; to-do 12: FL29's size */
      const extra: Record<string, any> = { net:{ label:'Net trigger', vis:false, color:'#0070f3' }, gross:{ label:'Gross trigger', vis:false, color:'#d6409f' },
        /* FL29's size (a few %) on its own left scale, beside the days (0-100) on the right, so it does not read flat */
        balance:{ label:'Balance %', scale:'left', fmt:spec.pctLevel, fk:'pct', minMove:.01, color:'#8b5cf6' } };
      return r.outputs.map(k => extra[k] ? { k, r:kind, role:'numeric_line', vis:true, w:2, rule:'', cond:'', ...extra[k] } : k === 'change'
        /* EXEC-TERMINAL-IND-EDIT (FL34 to-do 17, FL11 U2): the change line is a line on its own scale (left), in points */
        ? { k, label:'Change', r:'line', role:'numeric_line', vis:true, w:2, rule:'', cond:'', scale:'left', fmt:spec.points, fk:'pt', minMove:.01 }
        : { k, label:k === 'buy' ? 'Buy' : k === 'sell' ? 'Sell' : r.outputs.includes('change') ? 'Level' : r.name.split(' · ').pop()!,   // re-test F8: not the title again r:kind, role:'numeric_line', vis:true, w:2, rule:'', cond:'',
            /* U3: a share minus the even share reads in points; U6: a count of brokers; U1: a z-score */
            ...(p && p.even ? { fmt:spec.points, fk:'pt', minMove:.01 } : p && p.measure === 'count' ? { fmt:(v: number) => spec.num(v, 0), fk:'count', minMove:1 }
              : p && p.stat === 'z' ? { fmt:(v: number) => spec.smart(v, 2), fk:'z', minMove:.01 } : p && p.stat === 'pct' && r.unit === '%' ? { fmt:spec.indicator, fk:'pctile', minMove:.01 }
              : p && p.form === 'ratio' ? { fmt:spec.ratio, fk:'ratio', minMove:.001 }
              /* agent 5 F8: a change or a distance in percent carries its sign ("+7.9%"), as the names say */
              : r.unit === '%' && /(Change|Distance) %/.test(r.name) ? { fmt:spec.pctChange, fk:'pctchg' } : {}) });
    };
    /* on an index: the indicator's own note, else (a Lot choice offered on a stock) that Lot is not offered here */
    const hasLot = r.params.some(q => q.kind === 'select' && (q.options || []).some(o => o[0] === 'lot'));
    const note0 = ctx.M.index ? INDEX_NOTE[r.id] || (hasLot ? ' Pada indeks (IHSG) tanpa pilihan Lot: lot berbagai saham tidak bisa dijumlahkan.' : '') : '';
    /* EXEC-QA5-FIX (QA 2026-11-07, Q1, F2-08): a default cohort of the day's largest net buyers leans every reading with a
       direction to the buy side (FL11 was positive on 200 of 200 days); said wherever the registry's defaults pick that
       cohort, derived from them */
    const cohortNote = byKey.rank?.default === 'net_buy' && (byKey.scope ? byKey.scope.default === 'topn' : !!byKey.top)
      ? ' Kelompok bawaan: N pembeli bersih terbesar setiap hari; ukuran yang punya arah (net, selisih, rasio beli/jual) karena itu condong ke sisi beli, jadi bandingkan besar-kecilnya antar hari.' : '';
    const note = note0 + cohortNote;
    const reg = { key:r.id, id:r.id, name:r.name, short:r.name, zone:r.place === 'pane' ? 'panel' : 'overlay', unit:r.unit, outs:outs(plotDefault),
      guides:levels, levelsParam:!!byKey.levels, fill:null, tip:r.tip + note, info:r.tip + note + (r.needs_frequency ? ' Membutuhkan jumlah transaksi (frekuensi) di file broker.' : ''), flow:true, place:r.place };
    /* a field that only applies to one broker scope is shown only with it (audit I8: "Brokers: None" beside Top-N); FL46's
       numerator and denominator each have their own scope (num_scope, den_scope) */
    const scopeKey = (key: string) => { const pre = key.replace(/(brokers|top|rank|ranking)$/, ''); return r.params.some(q => q.key === pre + 'scope') ? pre + 'scope' : null };
    const scopeDef = (k: string) => r.params.find(q => q.key === k)?.default ?? 'topn';
    const topnOnly = (key: string) => { const k = scopeKey(key); return k ? { when:(p: any) => (p[k] ?? scopeDef(k)) === 'topn' } : {} };
    /* EXEC-IHSG-FLOW, EXEC-TERMINAL-IND-EDIT (user 2026-11-05 "Ok, masukan exec"): an index has no lots (lots of different
       stocks do not add up), so on an index a choice of Lot is not offered and a saved Lot reads as the next choice
       (Rupiah); a choice left with one option is not shown (FL23's unit). Derived from the options, not listed by id. */
    const onIndex = !!ctx.M.index;
    const noLot = (q: any) => withoutLot(r.params, q, onIndex), optionsOf = (q: FlowRegParam) => offeredOptions(q, onIndex);
    /* a select left with one option on an index is still shown (FL23: Rupiah only) so its value is always set: hiding it
       let the registry default (Lot) back in (regression found by the 2026-11-05 verification, H1) */
    const inputs = r.params.filter(q => q.key !== 'levels').map(q => {
      /* the rules a choice meets, shown before the user picks (AGENTS.md "Gates and evidence"): K4's counts, FL46's gates */
      const rule = q.key.endsWith('_measure') ? 'A net measure of all brokers over both investor types is always 0 and is refused, as is a ratio that is always 100%; a day whose denominator is 0 or below has no value. Right: Net buy of a Top-3 cohort ÷ Gross buy of all brokers. Wrong: Net buy of all brokers (both investor types).'
        : q.kind === 'select' && (q.options || []).some(o => o[0] === 'tx') ? 'Transactions needs the transaction counts in the broker files; Value and Lot do not.' : undefined;
      const base: any = { key:q.key, label:relabel(q.label), hint:[q.status === 'PROPOSED' ? 'Proposed default' : '', rule ?? ''].filter(Boolean).join(' ') || undefined,
        ...(/(^|_)(top|rank|ranking)$/.test(q.key) ? topnOnly(q.key) : {}) };
      switch (q.kind) {
        case 'select': { const os = optionsOf(q), def = os.some(o => o[0] === q.default) ? q.default : os[0]?.[0];
          return { ...base, kind:'select', options:os.map(o => o[0]), allOptions:(q.options || []).map(o => o[0]), labels:Object.fromEntries(os.map(o => [o[0], o[1]])), def } }
        case 'multi': {
          const isBoard = q.key.endsWith('boards'), all = isBoard ? ctx.BOARDS : ctx.INVESTORS;
          return { ...base, kind:'multi', def:q.default, options:() => all, all:() => all.map(x => x.id), title:isBoard ? 'Board' : 'Investor' };
        }
        case 'brokers': { const k = scopeKey(q.key); return { ...base, kind:'brokers', def:q.default, max:q.max ?? undefined, resolve:brokersOf, tokenLabel,
          ...(q.default === 'auto_c' ? { freezeToken:'auto_c' } : {}),
          ...(k ? { when:(p: any) => p[k] === 'selected' } : {}) } }
        case 'int': return { ...base, kind:'int', min:q.min ?? 1, max:q.max ?? 5000, def:q.default };
        case 'num': return { ...base, kind:'num', min:q.min ?? -1e12, max:q.max ?? 1e12, minExclusive:!!(q as any).min_exclusive, step:'any', def:q.default };
        case 'bool': return { ...base, kind:'bool', def:!!q.default };
        case 'date': return { ...base, kind:'date', def:'view', first:firstVisible };
        case 'button': return { ...base, kind:'button', reset:['inst', 'retail'] };
        default: return { ...base, kind:'fixed', text:q.text };
      }
    });
    const viewBound = r.params.some(q => q.kind === 'date') || r.id === 'FL23';
    /* an indicator that models a position (an opening balance: FL19, FL20) */
    const modelled = r.params.some(q => q.key === 'opening');
    const topBothSides = !!byKey.top && !byKey.scope;
    /* an indicator with no broker choice reads the whole market (FL32, FL40) */
    const marketWide = !r.params.some(q => q.key === 'scope' || q.key === 'top' || q.key === 'brokers' || q.key === 'inst') && r.params.some(q => q.key === 'investors');
    /* the date a value starts from: the anchor (default: the first candle in view) or a fixed start (Broker Inventory) */
    const startOf = (p: any): string | null => {
      const dq = r.params.find(q => q.kind === 'date');
      if (dq) { const a = p?.[dq.key]; return a === 'view' || a == null ? firstVisible() : String(a).slice(0, 10) }
      return r.params.some(q => q.key === 'start' && q.kind === 'fixed') ? firstVisible() : null;
    };
    /* EXEC-BROKER-INV-PANEL: an indicator that counts from the first candle on screen (a fixed `start`) marks its 0 in the
       pane; the pane's own broker, board and investor buttons are the user's choice for Broker Inventory (2026-11-06) */
    const zeroLabel = r.place === 'pane' && r.params.some(q => q.key === 'start' && q.kind === 'fixed');
    const paneFilters = PANE_FILTER_KEYS.filter(k => inputs.some((f: any) => f.key === k));
    return {
      id:r.id, name:r.name, reg, multi:true, flow:true, single:SINGLE_SECURITY.has(r.id), viewBound, zeroLabel, paneFilters, inputs, style:[], fill:null,
      pane:r.place === 'pane' ? 'sub' : 'overlay', format:F.fmt, minMove:F.minMove,
      outsOf:(p: any) => outs(p.plot === 'hist' ? 'histogram' : p.plot === 'line' ? 'line' : plotDefault, p),
      compute:(p: any) => {
        if (emptyChoice(p)) return {};                 // nothing chosen: no line (the row says what to choose)
        const q = { ...p };
        if (q.anchor === 'view' || q.anchor == null) q.anchor = firstVisible();
        if (r.id === 'FL23') q.start = firstVisible();
        noLot(q);
        if (usesInsider(r) && insiderState !== 'ready') return {};      // QA F2-03: no "Rp 0" while the events are missing
        const o: any = toCandles(computeFlow(r.id, context(), q), r.place === 'marker');
        /* QA M2 (2026-11-06, user "go with your advice"): every broker over both investor types nets to 0 (each buy has a
           seller), so a net reading of that cohort carries no information; read from the result, not a list of indicators.
           EXEC-QA5-FIX (agent 5 F4, F5): also an indicator of the whole market (FL40), and the message says the constant */
        if (ctx.flowRows?.n && allBrokersBothSides(p, marketWide) && carriesNothing(o)) {
          const c = (Object.values(o).filter(Array.isArray) as any[][]).flat().find(v => v !== null && Number.isFinite(v));
          return { _allZero:true, _const:c ?? 0 };
        }
        if (r.id !== 'FL23') return o;
        const codes = Object.keys(o).filter(k => k !== 'total'), slots: any = { _labels:codes };
        codes.forEach((c, j) => { slots[SLOTS[j]] = o[c] });
        if (o.total) slots.total = o.total;
        return slots;
      },
      /* the legend's text where the value is empty: why, when the reason is the data (plan S4: a message, not a zero) */
      note:(i: number, raw: any, p: any) => {
        const R = ctx.flowRows, empty = emptyChoice(p);
        if (empty) return empty;
        /* re-test N2: before the broker data that comes first, also for a constant all-market reading */
        { const fb0 = firstBroker(), d0 = DAY ? DAY.dayOf[i] : i; if (R && R.n && fb0 >= 0 && d0 >= 0 && d0 < fb0) return `Before broker data (from ${longDay(firstBrokerDay())})` }
        if (raw?._allZero) { const c = Number(raw._const) || 0, how = marketWide ? 'choose Foreign or Domestic' : 'choose Foreign or Domestic, or a Top-N cohort';
          return Math.abs(c) < 1e-9 ? `All brokers over both investor types always net to 0: ${how}` : `All brokers over both investor types: always ${F.fmt(c)} (every buy has a seller): ${how}` }
        if (usesInsider(r) && insiderState !== 'ready') return insiderState === 'loading' ? 'Loading insider data' : 'No insider data published for this ticker';
        if (isBrokerFree(r)) return noVolume ? 'No volume for this ticker' : '';
        /* a list given as a classification (FL34) waits for the reference file's classes */
        const usesClass = p && Object.values(p).some(v => typeof v === 'string' && v.startsWith('class:'));
        if (usesClass && classState !== 'ready') return classState === 'loading' ? 'Loading the broker classification' : 'No broker classification published yet';
        if (!R) return ctx.brokerFailed ? 'Broker data could not be loaded: reload the page' : 'Loading broker data';
        if (!R.n) return 'No broker data for this ticker';
        if (i > ctx.brokerEnd) return 'No broker data yet';
        const di = DAY ? DAY.dayOf[i] : i, fb = firstBroker();
        if (di >= 0 && fb >= 0 && di < fb) return `Before broker data (from ${longDay(firstBrokerDay())})`;   // agent 5 F9
        if (di < 0 || !R.has[di]) return `No broker data on this ${one}`;
        /* EXEC-QA5-FIX (agent 5 F2, F2-07): a value that starts at a date (the anchor, Broker Inventory's start) says so */
        const start = startOf(p);
        if (start && dates[di] && dates[di].slice(0, 10) < start) return `Starts ${dayText(start)} (start date)`;
        /* QA M8, R2-M2 (2026-11-06): a value still empty because the indicator's window reaches before the first broker
           candle. The need is read from the indicator's own first value (exact for every formula); with no value yet it
           is the sum of its windows, said as "at least" */
        { const count = (to: number) => { let n = 0; for (let k = 0; k <= to && k < R.N; k++) if (R.has[k]) n++; return n };
          const f = firstValueAt(raw), seen = count(di);
          if (f >= 0) { const fd = DAY ? DAY.dayOf[f] : f; if (fd >= 0 && di < fd) return `Needs ${count(fd)} ${one}s of broker history (${seen} so far)` }
          else { const est = ['window', 'baseline', 'recent'].reduce((t, k) => t + Math.max(0, Number(p?.[k]) || 0), 0);
            if (est > seen) return `Needs at least ${est} ${one}s of broker history (${seen} so far)` } }
        /* K4 (user 2026-11-05 "3 ok"): a choice that counts transactions needs them; the others draw without them */
        if ((r.needs_frequency || needsCounts(p)) && !hasCounts(R)) return r.needs_frequency ? 'Needs the transaction counts'
          : 'No transaction counts for this ticker: choose Value or Lot';
        /* some rows in the candles the value reads have no counts (verification 2026-11-05: a silent blank) */
        if (r.needs_frequency || needsCounts(p)) {
          const span = Math.max(1, ...['window', 'baseline', 'recent'].map(k => Number(p?.[k]) || 0)) + (Number(p?.recent) || 0), M = missingAt(R);
          for (let k = Math.max(0, di - span); k <= di; k++) if (M[k]) return needsCounts(p) && !r.needs_frequency
            ? `Some broker rows from ${dates[k] ?? ''} have no transaction counts: choose Value or Lot` : 'Some broker rows in this window have no transaction counts';
        }
        /* EXEC-QA5-FIX (QA Q2, F2-12): no row of the chosen board and investor type in the window */
        { const w = Math.max(1, Number(p?.window) || 1);
          if (!filterHasRows(p, Math.max(0, di - w + 1), di)) return `No trades: ${[Array.isArray(p?.boards) ? p.boards.join('+') : '', Array.isArray(p?.investors) && p.investors.length === 1 ? p.investors[0] : ''].filter(Boolean).join(' · ') || 'this filter'}${w > 1 ? ` in ${w}${letter}` : ''}` }
        /* the rest: the formula has nothing to measure here (nothing sold by the group, a position of 0 or less) */
        /* re-test N3: a Top N of both sides (FL24, FL42, FL48: no broker scope) needs N net buyers and N net sellers */
        if (topBothSides) return `No value: fewer than ${p?.top ?? byKey.top?.default} net buyers or sellers here`;
        return modelled ? 'No value: modelled position is 0 or less' : 'No value: nothing to measure here';   // re-test N2: the model's words only where there is a model
      },
      validate:(p: any) => {
        // QA M1 (2026-11-06): an emptied list is a saved state (the row asks for a choice), not an invalid one
        if (r.id === 'FL46') { const why = ratioRefusal(p); if (why) return why }
        if (r.id === 'FL34') { const a = new Set(brokersOf(p.inst)); if (brokersOf(p.retail).some(b => a.has(b))) return 'A broker cannot be in both the institutional and the retail list.' }
        if (r.id === 'FL23' && Array.isArray(p.brokers) && p.brokers.length > 5) return 'Choose up to 5 brokers.';
        return '';
      },
      /* a ratio's neutral line is 1, an imbalance's 0 (FL48 "Show as"; verification 2026-11-05): the default guide follows */
      guidesFor:(p: any, lv: number[]) => p && p.form === 'ratio' && lv.length === 1 && lv[0] === 0 ? [1] : lv,
      /* Design Spec v1.2: the parameters in parentheses, "Bandar Balance · % (Top 3, 10D)" */
      title:(p0: any) => {
        const p = noLot({ ...p0 });            // the parameters the calculation uses (on an index a saved Lot reads Rupiah)
        const parts = [relabel(r.name)];
        if (DAY) parts.push('Daily');
        /* FL46: what the ratio is, both sides in short (verification 2026-11-05: "Flow Ratio (1D)" said nothing) */
        if (r.id === 'FL46') parts.push(`${ratioSideText(p, 'num_')} ÷ ${ratioSideText(p, 'den_')}`);
        /* a choice that changes what the number is (measure, statistic, unit, form) is named when it is not the default
           (verification 2026-11-05: FL37 showed a z-score under "Percentile"); derived from the registry's selects */
        for (const q of r.params) if (q.kind === 'select' && !TITLE_SKIP.test(q.key) && p[q.key] !== undefined && (p[q.key] !== q.default || TITLE_ALWAYS.test(q.key)))
          parts.push((q.options || []).find(o => o[0] === p[q.key])?.[1] ?? String(p[q.key]));
        /* EXEC-QA5-FIX (QA Q3, F3, F2-12): a fixed basis (FL08: Lot) and an option that turns the number into points */
        for (const q of r.params) if (q.kind === 'fixed' && q.key === 'basis' && q.text) parts.push(q.text);
        for (const q of r.params) if (q.kind === 'bool' && q.key === 'even' && p[q.key]) parts.push('minus even share');
        if (!r.params.some(q => q.key === 'scope') && r.params.some(q => q.key === 'top') && p.top) parts.push(`Top ${p.top}`);
        const sided = r.params.some(q => q.key === 'side');
        if (p.scope) parts.push(scopeText(p, sided));
        if (p.side && p.side !== 'buy' && !(sided && p.scope === 'topn')) parts.push(p.side === 'both' ? 'Buy & Sell' : 'Sell');
        const f = filterText(p); if (f) parts.push(f);
        // a window that caps a count reads "limit 60D" (QA F2-09: "60D" read as a 60-day window)
        if (p.window) parts.push(/limit/i.test(byKey.window?.label || '') ? `limit ${p.window}${letter}` : `${p.window}${letter}`);
        // re-test N4: the change line's distance when it is not the window (FL11, FL34)
        if (byKey.lag && p.lag !== undefined && p.lag !== 'window') parts.push(`change vs ${p.lag}${letter} ago`);
        /* EXEC-QA5-FIX (QA Q3, agent 5 F3): the periods compared, "last 5D vs 20D"; a baseline only where it is used (FL47
           reads its baseline only for a percentile or z-score) */
        const baseUsed = !(byKey.stat && (p.stat ?? byKey.stat.default) === 'value');
        if (p.recent && p.baseline) parts.push(`last ${p.recent}${letter} vs ${p.baseline}${letter}`);
        else if (p.baseline && baseUsed) parts.push(`vs ${p.baseline}${letter}`);
        // the date the value starts from (QA F2-01: the anchor followed the zoom without being shown)
        const start0 = startOf(p), fbd = firstBrokerDay(), start = start0 && fbd && start0 < fbd ? fbd : start0;   // re-test N5
        if (start) parts.push(`from ${dayText(start)}`);
        /* QA round 2/3 (open Low "units not written"): a figure in lots per trade says so (a lot/value choice is named by
           its select above, Rupiah figures carry "Rp" themselves) */
        if (r.unit === 'lot/tx') parts.push('lot per trade');
        return spec.titled(parts[0], parts.slice(1));
      },
    };
  });
}
