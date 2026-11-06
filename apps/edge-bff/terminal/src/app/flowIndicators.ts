/* EXEC-TERMINAL-FLOW-IND (user go 2026-10-30), live: the 39 Flow indicators FL01-FL39 as indicator definitions of the
   generic engine (indicators.ts, the same path as the 53 registry indicators: legend row, settings dialog, undo, saved
   list). Everything about an indicator comes from src/data/flowRegistry.json (generated from the agreed spreadsheet by
   scripts/build_flow_registry.py); the numbers come from calc/flow.ts on the raw broker rows the worker sends
   (ctx.flowRows). Rules of the spreadsheet that need the chart: the default anchor and Broker Inventory's start are the
   first visible candle; "days" are the chart's candles (user 2026-10-30: "2-3 OK"). */
import { autoInventoryBrokers, classBrokers, computeFlow, defaultInventoryBrokers, type FlowContext, type FlowRows, type InsiderRow } from '../calc/flow';
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
/** EXEC-FLOW-PANE-FILTERS (user go 2026-11-06): the choices shown on a Flow indicator's legend row, in this order, when the
    indicator has them (Broker Inventory 2026-11-06: brokers, boards, investors). FL46's two sides use prefixed keys
    (num_, den_), so it gets none and keeps its settings dialog; the others (window, baseline, unit, levels, Side) stay
    in the dialog. */
export const PANE_FILTER_KEYS = ['scope', 'top', 'rank', 'brokers', 'boards', 'investors'] as const;
/** QA M2: the whole market's cohort (every broker, both investor types) */
export const allBrokersBothSides = (p: any) => !!p && p.scope === 'all' && (!Array.isArray(p.investors) || p.investors.length >= 2);
/** a result with no finite non-zero value in any output series (all 0 or empty) */
export const carriesNothing = (o: any) => {
  const series = Object.values(o || {}).filter(Array.isArray) as any[][];
  return series.length > 0 && series.every(a => a.every(v => v === null || v === undefined || !Number.isFinite(v) || v === 0));
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
      const extra: Record<string, any> = { net:{ label:'Net trigger', vis:false, color:'#0070f3' }, gross:{ label:'Gross trigger', vis:false, color:'#d6409f' },
        /* FL29's size (a few %) on its own left scale, beside the days (0-100) on the right, so it does not read flat */
        balance:{ label:'Balance %', scale:'left', fmt:spec.pctLevel, fk:'pct', minMove:.01, color:'#8b5cf6' } };
      return r.outputs.map(k => extra[k] ? { k, r:kind, role:'numeric_line', vis:true, w:2, rule:'', cond:'', ...extra[k] } : k === 'change'
        /* EXEC-TERMINAL-IND-EDIT (FL34 to-do 17, FL11 U2): the change line is a line on its own scale (left), in points */
        ? { k, label:'Change', r:'line', role:'numeric_line', vis:true, w:2, rule:'', cond:'', scale:'left', fmt:spec.points, fk:'pt', minMove:.01 }
        : { k, label:k === 'buy' ? 'Buy' : k === 'sell' ? 'Sell' : r.name.split(' · ').pop()!, r:kind, role:'numeric_line', vis:true, w:2, rule:'', cond:'',
            /* U3: a share minus the even share reads in points; U6: a count of brokers; U1: a z-score */
            ...(p && p.even ? { fmt:spec.points, fk:'pt', minMove:.01 } : p && p.measure === 'count' ? { fmt:(v: number) => spec.num(v, 0), fk:'count', minMove:1 }
              : p && p.stat === 'z' ? { fmt:(v: number) => spec.smart(v, 2), fk:'z', minMove:.01 } : p && p.stat === 'pct' && r.unit === '%' ? { fmt:spec.indicator, fk:'pctile', minMove:.01 }
              : p && p.form === 'ratio' ? { fmt:spec.ratio, fk:'ratio', minMove:.001 } : {}) });
    };
    /* on an index: the indicator's own note, else (a Lot choice offered on a stock) that Lot is not offered here */
    const hasLot = r.params.some(q => q.kind === 'select' && (q.options || []).some(o => o[0] === 'lot'));
    const note = ctx.M.index ? INDEX_NOTE[r.id] || (hasLot ? ' Pada indeks (IHSG) tanpa pilihan Lot: lot berbagai saham tidak bisa dijumlahkan.' : '') : '';
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
        const o: any = toCandles(computeFlow(r.id, context(), q), r.place === 'marker');
        /* QA M2 (2026-11-06, user "go with your advice"): every broker over both investor types nets to 0 (each buy has a
           seller), so a net reading of that cohort carries no information; read from the result, not a list of indicators */
        if (ctx.flowRows?.n && allBrokersBothSides(p) && carriesNothing(o)) return { _allZero:true };
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
        if (raw?._allZero) return 'All brokers over both investor types always net to 0: choose Foreign or Domestic, or a Top-N cohort';
        if (isBrokerFree(r)) return noVolume ? 'No volume for this ticker' : '';
        /* a list given as a classification (FL34) waits for the reference file's classes */
        const usesClass = p && Object.values(p).some(v => typeof v === 'string' && v.startsWith('class:'));
        if (usesClass && classState !== 'ready') return classState === 'loading' ? 'Loading the broker classification' : 'No broker classification published yet';
        if (!R) return ctx.brokerFailed ? 'Broker data could not be loaded: reload the page' : 'Loading broker data';
        if (!R.n) return 'No broker data for this ticker';
        if (i > ctx.brokerEnd) return 'No broker data yet';
        const di = DAY ? DAY.dayOf[i] : i;
        if (di < 0 || !R.has[di]) return `No broker data on this ${one}`;
        /* QA M8 (2026-11-06): a value still empty because the window or baseline reaches before the first broker candle */
        { const need = Math.max(1, Number(p?.window) || 1) + Math.max(0, Number(p?.baseline) || 0) + Math.max(0, Number(p?.recent) || 0) - 1;
          let seen = 0; for (let k = 0; k <= di; k++) if (R.has[k]) seen++;
          if (seen < need) return `Needs ${need} ${one}s of broker history (${seen} so far)` }
        /* K4 (user 2026-11-05 "3 ok"): a choice that counts transactions needs them; the others draw without them */
        if ((r.needs_frequency || needsCounts(p)) && !hasCounts(R)) return r.needs_frequency ? 'Needs the transaction counts'
          : 'No transaction counts for this ticker: choose Value or Lot';
        /* some rows in the candles the value reads have no counts (verification 2026-11-05: a silent blank) */
        if (r.needs_frequency || needsCounts(p)) {
          const span = Math.max(1, ...['window', 'baseline', 'recent'].map(k => Number(p?.[k]) || 0)) + (Number(p?.recent) || 0), M = missingAt(R);
          for (let k = Math.max(0, di - span); k <= di; k++) if (M[k]) return needsCounts(p) && !r.needs_frequency
            ? `Some broker rows from ${dates[k] ?? ''} have no transaction counts: choose Value or Lot` : 'Some broker rows in this window have no transaction counts';
        }
        return '';
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
        for (const q of r.params) if (q.kind === 'select' && !TITLE_SKIP.test(q.key) && p[q.key] !== undefined && p[q.key] !== q.default)
          parts.push((q.options || []).find(o => o[0] === p[q.key])?.[1] ?? String(p[q.key]));
        if (!r.params.some(q => q.key === 'scope') && r.params.some(q => q.key === 'top') && p.top) parts.push(`Top ${p.top}`);
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
