/* INDICATOR ENGINE — one schema per indicator, everything else is generic (reference lines 2965-3555).
   Two kinds of definitions share the legend row, settings dialog, persistence and remove menu:
     1. Registry indicators (53): built from the registry JSON (= the "Technical Indicators 53" workbook).
        Calculations live in the calculation module (src/calc/indicators.ts, spec INDICATOR_SPEC.md).
     2. Flow indicators (Net Buy Flow, Net Buy Flow (Line)): hand-written schema (inputs[], style[], compute, title).
   Backend: window.marketLabIndicators.export() / import() carry the saved list as JSON.
   Ported line for line; closure values the reference reassigns are read from ctx. */
import { F } from '../calc/indicators';
import { initFlowIndicators } from './flowIndicators';
import type { Ctx } from './context';
import { $, nfCompact, rupiah, store } from './context';

export function initIndicators(ctx: Ctx) {
  const { L, chart, ohlc, volume, N, closes, BOARDS, INVESTORS, allBrokers, makeFilter, IND_REG, Ind, volCtl, Hist, displayHooks, tipHooks } = ctx;
  const NF = new Intl.NumberFormat('en-US', { minimumFractionDigits:2, maximumFractionDigits:2 });
  const PALETTE = ['#171717', '#f5a623', '#7928ca', '#12a594', '#d6409f', '#0070f3', '#f23645', '#8f8f8f', '#089981'];
  const LINE_STYLES = { Solid:L.LineStyle.Solid, Dashed:L.LineStyle.Dashed, Dotted:L.LineStyle.Dotted };
  const UP = '#089981', DOWN = '#f23645';
  const alpha = (hex, a) => { if(a >= 1 || !/^#[0-9a-f]{6}$/i.test(hex)) return hex; const n = parseInt(hex.slice(1), 16); return `rgba(${n >> 16},${n >> 8 & 255},${n & 255},${a})` };

  /* ---- registry indicators ---- */
  const BARS = { O:ohlc.map(b => b.open), H:ohlc.map(b => b.high), L:ohlc.map(b => b.low), C:ohlc.map(b => b.close), V:volume.map(v => v.value), T:ohlc.map(b => b.time) };
  const smart = v => { const a = Math.abs(v); return a === 0 ? '0' : a < .01 ? v.toExponential(2) : a < 1e4 ? v.toFixed(2) : nfCompact.format(v) };
  /* number format follows the workbook's Y-axis unit, so a new unit only needs a rule here */
  const unitFormat = unit =>
    /formula_defined|per_volume/.test(unit) ? { fmt:smart, minMove:1e-8 } :
    /volume/.test(unit) ? { fmt:v => nfCompact.format(v), minMove:1 } :
    /^percent|percent_or|or_percent/.test(unit) ? { fmt:v => v.toFixed(2) + '%', minMove:.01 } :
    /^ratio/.test(unit) ? { fmt:v => v.toFixed(3), minMove:.001 } :
    { fmt:v => NF.format(v), minMove:.01 };
  /* An anchored average needs several bars per period. Bars per anchor period are derived from the bar spacing,
     so on daily bars "Session" (= one bar) is replaced as default by the first period that holds >= 10 bars (Month). */
  const BAR_DAYS = (() => { const g = []; for(let i = 1; i < Math.min(60, ohlc.length); i++) g.push((Date.parse(ohlc[i].time) - Date.parse(ohlc[i - 1].time)) / 864e5); g.sort((a, b) => a - b); return g[g.length >> 1] || 1 })();
  const PERIOD_DAYS = { Session:1, Week:7, Month:30.4, Quarter:91.3, Year:365.25, Decade:3652.5, Century:36525 };
  const barsIn = o => PERIOD_DAYS[o] / BAR_DAYS * (5 / 7);            // trading bars, 5 per calendar week
  const fitAnchor = q => {
    if(!q.opts || !q.opts.every(o => o in PERIOD_DAYS) || barsIn(q.def) >= 10) return q.def;
    return q.opts.find(o => barsIn(o) >= 10) || q.def;
  };
  const ORDER_KEYS = [['fast_length', 'middle_length', 'slow_length'], ['short_length', 'long_length']];
  const LABEL = k => k.replace(/_/g, ' ').replace(/^./, c => c.toUpperCase());
  function regDef(r) {
    const u = unitFormat(r.unit);
    const inputs = r.params.map(q => {
      const base = { key:q.k, label:q.label, hint:q.hint, evidence:q.ev };
      if(q.type === 'fixed') return { ...base, kind:'fixed', text:q.def === 'none' ? 'No adjustable inputs' : `Uses ${q.def} (fixed)` };
      if(q.type === 'integer') return { ...base, kind:'int', min:q.min ?? 1, max:q.max ?? 5000, def:q.def };
      if(q.type === 'number') return { ...base, kind:'num', min:q.min ?? -1e12, max:q.max ?? 1e12, step:q.step || 'any', def:q.def };
      if(q.type === 'boolean') return { ...base, kind:'bool', def:!!q.def };
      return { ...base, kind:'select', options:q.opts, def:fitAnchor(q) };
    });
    const fill = r.fill ? (r.fill.match(/(\w+)\s*↔\s*(\w+)/) || []).slice(1) : null;
    return {
      id:r.key, name:r.name, reg:r, multi:true, inputs, style:[], fill:fill && fill.length === 2 ? fill : null,
      pane:r.zone === 'panel' ? 'sub' : r.zone,              // 'overlay' (candle pane, price axis) | 'volume' (volume axis) | 'sub' (own pane)
      format:u.fmt, minMove:u.minMove,
      compute:p => F[r.key](BARS, p),
      validate:p => {                                          // "fast < (middle <) slow", "short < long" — derived from the parameter names
        for(const keys of ORDER_KEYS){
          const have = keys.filter(k => k in p);
          for(let a = 0; a < have.length - 1; a++) if(!(p[have[a]] < p[have[a + 1]])) return `${LABEL(have[a])} must be smaller than ${LABEL(have[a + 1]).toLowerCase()}.`;
        }
        return '';
      },
      title:p => [r.short, ...r.params.filter(q => q.type !== 'fixed' && q.type !== 'boolean').map(q => p[q.k])].join(' ')
    };
  }
  /* default look per output, from its renderer / visual role / colour rule */
  function regStyle(def, base) {
    const r = def.reg, out = {}; let n = 0;
    r.outs.forEach(o => {
      if(o.r === 'state') return;
      const s: any = { on:o.vis || /bands_mode/.test(o.cond), width:o.w || 2 };
      if(o.color) s.color = o.color;                                    // fixed by the definition (FL23: the inventory colours)
      else if(o.r === 'histogram') { s.color = UP; s.color2 = DOWN; if(/optional_state/.test(o.rule)) s.states = true }
      else if(o.r === 'segmented_line' || o.r === 'dots') { s.color = UP; s.color2 = DOWN }
      else if(o.role === 'signal_line') s.color = base === '#f5a623' ? '#d6409f' : '#f5a623';
      else if(o.role === 'center_line') s.color = base === '#f5a623' ? '#d6409f' : '#f5a623';
      else if(o.r === 'marker') s.color = UP;
      else if(/(^|_)(plus|up|buy)(_|$)/.test(o.k)) s.color = UP;
      else if(/(^|_)(minus|down|sell)(_|$)/.test(o.k)) s.color = DOWN;
      else if(o.role === 'boundary_line') s.color = base;
      else s.color = n++ === 0 ? base : PALETTE[(PALETTE.indexOf(base) + n) % 6];
      out[o.k] = s;
    });
    return { out, guides:{ on:r.guides.length > 0, levels:r.guides.join(', ') }, fill:{ on:!!r.fill, opacity:10 }, opacity:100, offset:0 };
  }
  const merge = (a, b) => { if(!b || typeof b !== 'object') return a; const o = Array.isArray(a) ? [...a] : { ...a }; for(const k in b) o[k] = a && typeof a[k] === 'object' && a[k] !== null && !Array.isArray(a[k]) ? merge(a[k], b[k]) : b[k]; return o };

  /* translucent area between two output series (band_lines_fill); drawn under the lines */
  class BandFill {
    d: any; view: any; chart: any; series: any; req: any;
    constructor() {
      this.d = null; const self = this;
      this.view = { zOrder:() => 'bottom', renderer:() => ({ draw:() => {}, drawBackground:t => self.paint(t) }) };
    }
    attached(p) { this.chart = p.chart; this.series = p.series; this.req = p.requestUpdate }
    detached() { this.chart = null }
    set(d) { this.d = d; if(this.req) this.req() }
    updateAllViews() {}
    paneViews() { return [this.view] }
    paint(target) {
      const d = this.d; if(!d || !this.chart) return;
      const ts = this.chart.timeScale(), r = ts.getVisibleLogicalRange(); if(!r) return;
      const from = Math.max(0, Math.floor(r.from) - 1), to = Math.min(d.a.length - 1, Math.ceil(r.to) + 1);
      target.useBitmapCoordinateSpace(({ context:ctx, horizontalPixelRatio:hx, verticalPixelRatio:vy }) => {
        ctx.fillStyle = d.color; let seg = [];
        const flush = () => {
          if(seg.length > 1){ ctx.beginPath(); seg.forEach((p, k) => k ? ctx.lineTo(p[0] * hx, p[1] * vy) : ctx.moveTo(p[0] * hx, p[1] * vy)); for(let k = seg.length - 1; k >= 0; k--) ctx.lineTo(seg[k][0] * hx, seg[k][2] * vy); ctx.closePath(); ctx.fill() }
          seg = [];
        };
        for(let i = from; i <= to; i++){
          const a = d.a[i], b = d.b[i];
          if(d.breaks && d.breaks.has(i)) flush();
          if(a === null || b === null){ flush(); continue }
          const x = ts.logicalToCoordinate(i), ya = this.series.priceToCoordinate(a), yb = this.series.priceToCoordinate(b);
          if(x === null || ya === null || yb === null){ flush(); continue }
          seg.push([x, ya, yb]);
        }
        flush();
      });
    }
  }

  /* ---- flow indicators (hand-written schema) ---- */
  const ALL_BOARDS = () => BOARDS.map(b => b.id), ALL_INVESTORS = () => INVESTORS.map(i => i.id);
  function netBuyFlow(p) {
    const br = p.brokers ? new Set(p.brokers) : null, bd = new Set(p.boards), iv = new Set(p.investors), net = new Float64Array(N);
    ctx.COMBOS.forEach(c => { if((br && !br.has(c.broker)) || !bd.has(c.board) || !iv.has(c.investor)) return; for(let i = 0; i < N; i++) net[i] += c.net[i] });
    const out = new Array(N).fill(null); let sum = 0;
    for(let i = 0; i < N; i++) { sum += net[i]; if(i >= p.length) sum -= net[i - p.length]; if(i >= p.length - 1) out[i] = sum }
    for(let i = ctx.brokerEnd + 1; i < N; i++) out[i] = null;      // EXEC-TERMINAL-FRESH: no broker data yet, not zero
    return out;
  }
  const flowDef = {
    id:'netflow', name:'Net Buy Flow', pane:'sub',
    tip:'Total nilai beli bersih (beli − jual) broker yang dipilih, dijumlah bergulir beberapa hari.',
    inputs: [
      { key:'brokers',   label:'Brokers',       kind:'multi', def:null, options:() => allBrokers().map(b => ({ id:b, label:b })), all:() => allBrokers(), title:'Broker', searchable:true, grid:true, mono:true },
      { key:'length',    label:'Rolling days',  kind:'int', min:1, max:250, def:5 },
      { key:'boards',    label:'Market board',  kind:'multi', def:['Regular', 'Nego', 'Cash'], options:() => BOARDS, all:ALL_BOARDS, title:'Board' },
      { key:'investors', label:'Investor type', kind:'multi', def:['Foreign'], options:() => INVESTORS, all:ALL_INVESTORS, title:'Investor' }
    ],
    style: [
      { key:'type',     label:'Plot',           kind:'select', options:['Histogram', 'Line'], def:'Histogram' },
      { key:'color',    label:'Buy / line',     kind:'color', def:'#089981' },
      { key:'colorNeg', label:'Sell (bars)',    kind:'color', def:'#f23645' }
    ],
    compute: netBuyFlow,
    series: st => st.type === 'Line' ? 'line' : 'hist',
    format: v => rupiah(v),
    title: p => {
      const few = (set, all, label, names) => !set || set.length === all.length ? `All ${label}` : set.length <= 2 ? set.join(', ') : `${set.length} ${names}`;
      return `Net buy ${p.length}D · ${few(p.brokers, allBrokers(), 'brokers', 'brokers')} · ${few(p.investors, ALL_INVESTORS(), 'investors', 'investors')}`
        + (p.boards.length === ALL_BOARDS().length ? '' : ` · ${p.boards.join(', ')}`);
    }
  };
  function brokerLines(p) {
    const bd = new Set(p.boards), iv = new Set(p.investors);
    return p.brokers.map(code => {
      const net = new Float64Array(N);
      ctx.COMBOS.forEach(c => { if(c.broker !== code || !bd.has(c.board) || !iv.has(c.investor)) return; for(let i = 0; i < N; i++) net[i] += c.net[i] });
      const vals = new Array(N).fill(null); let sum = 0;
      for(let i = 0; i < N; i++) {
        sum += net[i];
        if(p.mode === 'Rolling') { if(i >= p.length) sum -= net[i - p.length]; if(i >= p.length - 1) vals[i] = sum } else vals[i] = sum;
      }
      for(let i = ctx.brokerEnd + 1; i < N; i++) vals[i] = null;   // EXEC-TERMINAL-FRESH
      return { id:code, vals };
    });
  }
  const flowLineDef = {
    id:'netbuyline', name:'Net Buy Flow (Line)', lines:true,
    tip:'Garis beli bersih per broker di chart harga (sumbu kanan), kumulatif atau bergulir.',
    inputs: [
      { key:'brokers',   label:'Brokers (max 5)', kind:'multi', def:['DX', 'AK', 'YU'], max:5, options:() => allBrokers().map(b => ({ id:b, label:b })), all:() => allBrokers(), title:'Broker', searchable:true, grid:true, mono:true },
      { key:'mode',      label:'Calculation',     kind:'select', options:['Cumulative', 'Rolling'], def:'Cumulative' },
      { key:'length',    label:'Rolling days',    kind:'int', min:1, max:250, def:20 },
      { key:'boards',    label:'Market board',    kind:'multi', def:['Regular', 'Nego', 'Cash'], options:() => BOARDS, all:ALL_BOARDS, title:'Board' },
      { key:'investors', label:'Investor type',   kind:'multi', def:['Foreign', 'Domestic'], options:() => INVESTORS, all:ALL_INVESTORS, title:'Investor' }
    ],
    style: [
      { key:'width',     label:'Thickness',  kind:'select', options:[1, 2, 3, 4], def:2 },
      { key:'lineStyle', label:'Line style', kind:'select', options:Object.keys(LINE_STYLES), def:'Solid' }
    ],
    compute: brokerLines,
    format: v => rupiah(v),
    lineTag: p => p.mode === 'Rolling' ? `Net buy ${p.length}D` : 'Net buy',
    title: p => `${p.mode === 'Rolling' ? `Net buy ${p.length}D` : 'Net buy (cumulative)'} · ${p.brokers.length ? p.brokers.join(', ') : 'no broker'}`
  };
  /* EXEC-TERMINAL-FLOW-IND, live: the 39 Flow indicators of flowRegistry.json (the fixture keeps the reference's list) */
  const DEFS: any[] = [...IND_REG.map(regDef), flowDef, flowLineDef, ...(ctx.M.mode === 'live' ? initFlowIndicators(ctx) : [])];
  const defOf = id => DEFS.find(d => d.id === id);
  DEFS.forEach(d => { Ind.byName[d.name] = d.id; Ind.tips[d.name] = d.reg ? d.reg.tip : d.tip });

  /* ---- instances ---- */
  const KEY = 'ml.ind.v1', list = [];
  let uid = 0;
  const legend = $('indRow').parentElement;
  const EYE = $('volEye').innerHTML, XICON = $('volX').innerHTML;
  const GEAR = '<svg viewBox="0 0 20 20" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10 2.6l6.4 3.7v7.4L10 17.4l-6.4-3.7V6.3z"/><circle cx="10" cy="10" r="2.3"/></svg>';

  const save = () => store.set(KEY, JSON.stringify(list.map(i => ({ def:i.def.id, params:i.params, style:i.style, on:i.on, base:i.base }))));
  const defaults = (fields, over?) => Object.fromEntries(fields.filter(f => f.kind !== 'fixed' && f.kind !== 'button' && (f.kind !== 'color' || f.def !== undefined)).map(f => [f.key, over && over[f.key] !== undefined ? over[f.key] : f.def]));

  /* an indicator that is not a price overlay lives in its own pane under the candles */
  const layoutPanes = () => {
    const panes = chart.panes(), subs = Math.max(0, panes.length - 1);
    /* the price pane keeps at least ~45 % of the height however many panes are open (front-end audit 2026-10-30: 10 panes
       left it 113 px); up to two panes the factor stays the reference's 2.4 */
    panes.forEach((pn, k) => pn.setStretchFactor(k === 0 ? (subs ? Math.max(2.4, 0.82 * subs) : 1) : 1));
    requestAnimationFrame(() => { volCtl.relabel && volCtl.relabel(); list.forEach(placeRow) });
  };
  const stage = legend.parentElement;
  function placeRow(inst) {
    if(inst.def.pane !== 'sub' || !inst.series) return;
    const el = inst.series.getPane().getHTMLElement(); if(!el) return;
    inst.row.style.top = (el.getBoundingClientRect().top - stage.getBoundingClientRect().top + 6) + 'px';
    if(inst.watch !== el) { if(inst.ro) inst.ro.disconnect(); inst.ro = new ResizeObserver(() => placeRow(inst)); inst.ro.observe(el); inst.watch = el }
  }

  /* registry indicators: one chart series per plotted output (state outputs only drive colours) */
  function buildParts(inst, intoPane?: number) {
    const r = inst.def.reg, panel = r.zone === 'panel';
    const scale = r.zone === 'overlay' ? 'left' : r.zone === 'volume' ? 'volume' : 'right';
    let paneIdx = panel ? (intoPane ?? chart.panes().length) : 0;
    // EXEC-TERMINAL-FLOW-IND: a Flow indicator's outputs depend on its plot choice (histogram or line)
    const outs = inst.outs = inst.def.outsOf ? inst.def.outsOf(inst.params) : r.outs;
    inst.plotKey = outs.map(o => o.r).join();
    const opts: any = { priceScaleId:scale, lastValueVisible:panel, priceLineVisible:false, crosshairMarkerVisible:false };
    if(r.zone !== 'overlay') opts.priceFormat = { type:'custom', formatter:inst.def.format, minMove:inst.def.minMove };
    const mk = (type, extra) => { const s = chart.addSeries(type, { ...opts, ...extra }, paneIdx); paneIdx = s.getPane().paneIndex(); return s };
    inst.parts = [];
    outs.forEach(o => {
      if(o.r === 'state') return;
      if(o.r === 'marker') inst.parts.push({ o, kind:'marker', series:null, plugin:null });      // marks under the candles
      else if(o.r === 'histogram') inst.parts.push({ o, kind:'hist', series:mk(L.HistogramSeries, { base:0 }) });
      else if(o.r === 'segmented_line') inst.parts.push({ o, kind:'seg', series:mk(L.LineSeries, {}), series2:mk(L.LineSeries, { lastValueVisible:false }) });
      else if(o.r === 'dots') inst.parts.push({ o, kind:'dots', series:mk(L.LineSeries, { lineVisible:false, pointMarkersVisible:true }) });
      else inst.parts.push({ o, kind:'line', series:mk(L.LineSeries, {}) });
    });
    inst.series = inst.parts.find(pt => pt.series)?.series || null;
    if(panel && r.guides.length) inst.series.applyOptions({ autoscaleInfoProvider:orig => {   // keep visible reference levels inside the pane (e.g. RSI 30 / 70)
      const res = orig(), lv = inst.on && inst.style.guides.on ? guideLevels(inst) : [];
      if(!res || !res.priceRange || !lv.length) return res;
      return { ...res, priceRange:{ minValue:Math.min(res.priceRange.minValue, ...lv), maxValue:Math.max(res.priceRange.maxValue, ...lv) } };
    } });
    if(inst.def.fill) { const host = inst.parts.find(p => p.o.k === inst.def.fill[0]); if(host){ inst.fillPrim = new BandFill(); host.series.attachPrimitive(inst.fillPrim) } }
    if(panel) { chart.priceScale('right', paneIdx).applyOptions({ scaleMargins:{ top:.2, bottom:.06 } }); layoutPanes() }   // top band is kept free for the legend row
  }
  const guideLevels = inst => String(inst.style.guides.levels).split(/[,;|\s]+/).filter(Boolean).map(Number).filter(Number.isFinite);
  const STATE_COLORS = ['#089981', '#8b5a2b', '#0070f3', '#d6409f'];   // Market Facilitation: green, fade, fake, squat
  function refreshMulti(inst) {
    const r = inst.def.reg, st = inst.style, p = inst.params, N2 = N, off = st.offset | 0, op = (st.opacity ?? 100) / 100;
    const ret = r.zone === 'overlay' && ctx.displayMode === 'return', base = closes[0], conv = v => ret ? (v / base - 1) * 100 : v;
    const shift = a => { const o = new Array(N2).fill(null); if(a) a.forEach((v, i) => { const j = i + off; if(v !== null && j >= 0 && j < N2) o[j] = v }); return o };
    inst.disp = {}; (inst.outs || r.outs).forEach(o => { inst.disp[o.k] = shift(inst.raw[o.k]) });
    if(inst.raw._labels) inst.parts.forEach((pt, j) => { if(pt.o.k !== 'total') pt.o = { ...pt.o, label:inst.raw._labels[j] || `Broker ${j + 1}` } });   // FL23: the brokers' codes
    const breaks = new Set((inst.raw._breaks || []).map(i => i + off));         // calculation restarts here: never draw a line into this bar
    const dir = inst.disp.direction, bandsOff = 'bands_mode' in p && p.bands_mode === 'None', T = i => ohlc[i].time;
    const shown = pt => inst.on && st.out[pt.o.k].on && !(bandsOff && /bands_mode/.test(pt.o.cond));
    inst.parts.forEach(pt => {
      const s = st.out[pt.o.k], a = inst.disp[pt.o.k], vis = shown(pt), c1 = alpha(s.color, op), c2 = alpha(s.color2 || s.color, op);
      if(pt.kind === 'marker') {
        /* EXEC-TERMINAL-FLOW-IND: a mark under each candle where the indicator holds (FL09, FL27), on the series drawn */
        const host = ctx.chartStyle === 'line' || ctx.displayMode === 'return' ? ctx.mainLine : ctx.candle;
        if(pt.plugin && pt.host !== host) { pt.plugin.detach(); pt.plugin = null }
        if(!pt.plugin) { pt.plugin = L.createSeriesMarkers(host, []); pt.host = host }
        pt.plugin.setMarkers(vis ? a.flatMap((v, i) => v === 1 ? [{ time:T(i), position:'belowBar', color:c1, shape:'arrowUp', size:1 }] : []) : []);
        return;
      }
      if(pt.kind === 'hist') {
        const rising = /rising/.test(pt.o.rule), states = s.states && /optional_state/.test(pt.o.rule), V = BARS.V;
        pt.series.setData(a.flatMap((v, i) => v === null ? [] : [{ time:T(i), value:v,
          color: states ? (i && a[i - 1] !== null ? alpha(STATE_COLORS[v >= a[i - 1] ? (V[i] >= V[i - 1] ? 0 : 2) : (V[i] >= V[i - 1] ? 3 : 1)], op) : c1)
               : rising ? (i && a[i - 1] !== null && v < a[i - 1] ? c2 : c1) : (v >= 0 ? c1 : c2) }]));
        pt.series.applyOptions({ visible:vis });
      } else if(pt.kind === 'seg') {
        const data = want => a.map((v, i) => v === null || dir[i] !== want ? { time:T(i) } : { time:T(i), value:conv(v) });   // whitespace breaks the line at every trend flip
        pt.series.setData(data(1)); pt.series2.setData(data(-1));
        pt.series.applyOptions({ visible:vis, color:c1, lineWidth:s.width }); pt.series2.applyOptions({ visible:vis, color:c2, lineWidth:s.width });
      } else if(pt.kind === 'dots') {
        pt.series.setData(a.flatMap((v, i) => v === null ? [] : [{ time:T(i), value:conv(v), color:dir && dir[i] === -1 ? c2 : c1 }]));
        pt.series.applyOptions({ visible:vis, color:c1, pointMarkersRadius:Math.max(1, s.width) });
      } else {
        pt.series.setData(a.flatMap((v, i) => v === null ? [] : [breaks.has(i + 1) ? { time:T(i), value:conv(v), color:'rgba(0,0,0,0)' } : { time:T(i), value:conv(v) }]));
        pt.series.applyOptions({ visible:vis, color:c1, lineWidth:s.width });
      }
      if(r.zone === 'overlay') [pt.series, pt.series2].filter(Boolean).forEach(se => se.applyOptions({ priceFormat:ctx.formatMode() }));
    });
    /* reference levels (optional guides from the workbook), drawn on the pane's first series */
    (inst.guideLines || []).forEach(([se, pl]) => { try{ se.removePriceLine(pl) }catch(e){} }); inst.guideLines = [];
    if(st.guides && st.guides.on && inst.on) {
      const host = inst.parts[0].series;
      guideLevels(inst).forEach(lv =>
        inst.guideLines.push([host, host.createPriceLine({ price:lv, color:'#a3a3a3', lineWidth:1, lineStyle:L.LineStyle.Dashed, axisLabelVisible:false, title:'' })]));
    }
    if(inst.fillPrim) {
      const [ka, kb] = inst.def.fill, pa = inst.parts.find(x => x.o.k === ka), pb = inst.parts.find(x => x.o.k === kb);
      const on = st.fill.on && pa && pb && shown(pa) && shown(pb);
      inst.fillPrim.set(on ? { breaks, a:inst.disp[ka].map(v => v === null ? null : conv(v)), b:inst.disp[kb].map(v => v === null ? null : conv(v)), color:alpha(st.out[ka].color, st.fill.opacity / 100 * op) } : null);
    }
    paintRow(inst);
  }

  /* flow indicators: one series (histogram or line) */
  function ensureSeries(inst) {
    const want = inst.def.series ? inst.def.series(inst.style) : 'line';
    if(inst.sType === want) return;
    const type = want === 'hist' ? L.HistogramSeries : L.LineSeries, sub = inst.def.pane === 'sub';
    const opts: any = { priceScaleId:sub ? 'right' : 'left', lastValueVisible:false, priceLineVisible:false, crosshairMarkerVisible:false };
    if(sub) opts.priceFormat = { type:'custom', formatter:inst.def.format, minMove:1 };
    const paneIdx = !sub ? 0 : inst.series ? inst.series.getPane().paneIndex() : chart.panes().length;
    const fresh = chart.addSeries(type, opts, paneIdx);       // add first, then drop the old one, so the pane is never emptied
    if(inst.series) chart.removeSeries(inst.series);
    inst.series = fresh; inst.sType = want;
    if(sub) { chart.priceScale('right', inst.series.getPane().paneIndex()).applyOptions({ scaleMargins:{ top:.2, bottom:.06 } }); layoutPanes() }
  }
  const LINE_COLORS = ['#171717', '#f5a623', '#7928ca', '#12a594', '#d6409f'];
  function refreshLines(inst) {                              // one series per line (e.g. per broker); rebuilt on every change, there are only a few
    (inst.lines || []).forEach(l => l.series && chart.removeSeries(l.series));
    inst.lines = inst.raw.map((ln, k) => {
      const color = LINE_COLORS[k % LINE_COLORS.length];
      if(!inst.on) return { id:ln.id, color, series:null, vals:ln.vals };     // hidden: no series at all, so the right axis and its crosshair label stay empty
      const series = chart.addSeries(L.LineSeries, {
        priceScaleId:'right', color, lineWidth:inst.style.width, lineStyle:LINE_STYLES[inst.style.lineStyle], visible:inst.on,
        lastValueVisible:true, priceLineVisible:false, crosshairMarkerVisible:false, title:`${ln.id} · ${inst.def.lineTag(inst.params)}`,
        priceFormat:{ type:'custom', formatter:inst.def.format, minMove:1 }
      });
      series.setData(ln.vals.flatMap((v, i) => v === null ? [] : [{ time:ohlc[i].time, value:Math.round(v) }]));
      return { id:ln.id, color, series, vals:ln.vals };
    });
    paintRow(inst);
  }
  function refresh(inst) {                                   // redraw one indicator from its cached values
    if(inst.def.multi) return refreshMulti(inst);
    if(inst.def.lines) return refreshLines(inst);
    ensureSeries(inst);
    const sub = inst.def.pane === 'sub';
    inst.vals = inst.raw.slice();
    const point = (v, i) => {
      const value = sub ? Math.round(v) : +v.toFixed(4);
      return inst.sType === 'hist' ? { time:ohlc[i].time, value, color:v >= 0 ? inst.style.color : inst.style.colorNeg } : { time:ohlc[i].time, value };
    };
    inst.series.setData(inst.vals.flatMap((v, i) => v === null ? [] : [point(v, i)]));
    const o = { visible:inst.on };
    if(inst.sType === 'line') Object.assign(o, { color:inst.style.color, lineWidth:inst.style.width || 2, lineStyle:LINE_STYLES[inst.style.lineStyle || 'Solid'] });
    inst.series.applyOptions(o);
    paintRow(inst);
  }
  /* a Flow indicator whose plot changed (histogram or line) gets new series in its own pane, then the old ones go */
  function rebuildParts(inst) {
    const old = inst.parts, pane = inst.series ? inst.series.getPane().paneIndex() : undefined;
    (inst.guideLines || []).forEach(([se, pl]) => { try{ se.removePriceLine(pl) }catch(e){} }); inst.guideLines = [];
    buildParts(inst, pane);
    old.forEach(pt => { if(pt.series) chart.removeSeries(pt.series); if(pt.series2) chart.removeSeries(pt.series2); if(pt.plugin) pt.plugin.detach() });
    if(inst.def.pane === 'sub') layoutPanes();
  }
  const recompute = inst => {
    if(inst.def.outsOf && inst.parts && inst.def.outsOf(inst.params).map(o => o.r).join() !== inst.plotKey) rebuildParts(inst);
    inst.raw = inst.def.compute(inst.params); refresh(inst);
  };
  // live: the broker files arrive after the first draw; the flow indicators are computed again then (EXEC-TERMINAL-UI-1026 U5)
  ctx.refreshFlowIndicators = () => list.forEach(inst => { if(inst.def === flowDef || inst.def === flowLineDef || inst.def.flow) recompute(inst) });
  /* EXEC-TERMINAL-FLOW-IND: an anchor on the first visible candle (FL18-FL20) and Broker Inventory (FL23) follow the view */
  /* at most one recompute per 120 ms while the view moves (and one after it stops), and only when the first visible candle
     changed: one per frame made pan and zoom stutter with several of them (front-end audit I12) */
  let viewTimer: any = 0, viewLast = 0;
  const firstVisibleIdx = () => { const r = chart.timeScale().getVisibleLogicalRange(); return r ? Math.max(0, Math.min(N - 1, Math.ceil(r.from))) : 0 };
  const followView = () => {
    viewTimer = 0; viewLast = performance.now();
    const fv = firstVisibleIdx();
    list.forEach(inst => { if(inst.def.viewBound && (inst.def.id === 'FL23' || inst.params.anchor === 'view') && inst.viewAt !== fv) { inst.viewAt = fv; recompute(inst) } });
  };
  chart.timeScale().subscribeVisibleLogicalRangeChange(() => {
    if(viewTimer || !list.some(inst => inst.def.viewBound)) return;
    viewTimer = setTimeout(followView, Math.max(0, 120 - (performance.now() - viewLast)));
  });

  function paintRow(inst, i = ctx.lastTipIdx) {
    if(!inst.row || (inst.def.multi && !inst.disp)) return;          // still being built
    const r = inst.row, ret = ctx.displayMode === 'return';
    r.querySelector('.ind-k').textContent = inst.def.title(inst.params);
    const b = r.querySelector('b');
    if(inst.def.multi) {                                     // one coloured value per visible output
      const reg = inst.def.reg, many = inst.parts.length > 1, dir = inst.disp.direction, overlay = reg.zone === 'overlay';
      b.innerHTML = inst.parts.map(pt => {
        const s = inst.style.out[pt.o.k], v = inst.disp[pt.o.k][i];
        if(!s.on || v === null || v === undefined) return '';
        const prev = inst.disp[pt.o.k][i - 1];
        const c = pt.kind === 'marker' ? (v === 1 ? s.color : 'var(--text-3)') : pt.kind === 'seg' || pt.kind === 'dots' ? (dir && dir[i] === -1 ? s.color2 : s.color)
                : pt.kind === 'hist' ? (/rising/.test(pt.o.rule) ? (prev !== null && prev !== undefined && v < prev ? s.color2 : s.color) : /optional_state/.test(pt.o.rule) ? 'var(--text)' : (v >= 0 ? s.color : s.color2)) : s.color;
        const txt = overlay && pt.kind !== 'marker' ? (ret ? ((v / closes[0] - 1) * 100).toFixed(2) + '%' : NF.format(v)) : inst.def.format(v);   // a mark reads Yes/No
        return `<span style="color:${c === '#171717' ? 'var(--text)' : c}">${many && pt.kind !== 'seg' ? `<i class="ind-ok">${pt.o.label}</i> ` : ''}${txt}</span>`;
      }).filter(Boolean).join(' &nbsp;');
      if(!b.innerHTML && inst.def.note && inst.on) { const n = inst.def.note(i, inst.raw, inst.params); if(n) b.innerHTML = `<span class="flow-nodata-tip">${n}</span>` }   // Flow: why it is empty
      b.style.color = '';
    } else if(inst.def.lines) {
      b.innerHTML = (inst.lines || []).map(l => { const x = l.vals[i]; return `<span style="color:${l.color}">${l.id} ${x === null || x === undefined ? '' : inst.def.format(x)}</span>` }).join(' &nbsp;');
      b.style.color = '';
    } else {
      const v = inst.vals ? inst.vals[i] : null, none = v === null || v === undefined;
      b.textContent = none ? '' : inst.def.format(v);
      b.style.color = v >= 0 ? inst.style.color : inst.style.colorNeg;
    }
    r.classList.toggle('off', !inst.on);
    const eye = r.querySelector('[data-act="eye"]');
    eye.setAttribute('aria-pressed', String(inst.on)); eye.dataset.label = inst.on ? 'Hide' : 'Show';
  }

  function build(inst) {
    const r = inst.row = document.createElement('div');
    r.className = 'ind-row'; r.dataset.uid = inst.uid; r.dataset.def = inst.def.id;
    r.innerHTML = '<span class="ind-k"></span><b></b>'
      + `<button class="ind-eye" type="button" data-act="eye" aria-pressed="true" data-label="Hide" aria-label="Show or hide">${EYE}</button>`
      + `<button class="ind-eye ind-cfg" type="button" data-act="cfg" data-label="Settings" aria-label="Settings">${GEAR}</button>`
      + `<button class="ind-eye ind-x" type="button" data-act="del" data-label="Remove" aria-label="Remove">${XICON}</button>`;
    r.addEventListener('click', (e: any) => {
      const a = e.target.closest('[data-act]'); if(!a) return;
      if(a.dataset.act === 'eye') { inst.on = !inst.on; refresh(inst); save() }
      else if(a.dataset.act === 'cfg') openSettings(inst)
      else userRemove(inst);
    });
    if(inst.def.pane === 'sub') { r.classList.add('in-pane'); stage.appendChild(r) } else legend.appendChild(r);
    if(inst.def.multi) buildParts(inst);
    recompute(inst);
    placeRow(inst);
  }
  const nextBase = () => PALETTE[list.length % 6];
  const byHid = hid => list.find(i => i.hid === hid);
  function add(defId, saved?) {
    const def = defOf(defId); if(!def) return null;
    const inst: any = { uid:++uid, def, params:defaults(def.inputs, saved && saved.params), on:saved ? saved.on !== false : true };
    inst.hid = inst.uid;
    if(def.multi) { inst.base = (saved && saved.base) || nextBase(); inst.style = merge(regStyle(def, inst.base), saved && saved.style) }
    else inst.style = { ...defaults(def.style, saved && saved.style), ...(def.style.some(f => f.key === 'color' && f.def !== undefined) ? {} : { color:(saved && saved.style && saved.style.color) || PALETTE[list.length % PALETTE.length] }) };
    if(def.validate && def.validate(inst.params)) inst.params = defaults(def.inputs);     // a saved set that breaks a rule falls back to defaults
    list.push(inst); build(inst);
    if(!saved) { save(); Ind.onChange && Ind.onChange() }
    return inst;
  }
  function remove(inst) {
    const sub = inst.def.pane === 'sub', pane = sub ? inst.series.getPane() : null;
    if(inst.ro) inst.ro.disconnect();
    if(inst.def.multi) inst.parts.forEach(pt => { if(pt.series) chart.removeSeries(pt.series); if(pt.series2) chart.removeSeries(pt.series2); if(pt.plugin) pt.plugin.detach() });
    else if(inst.def.lines) (inst.lines || []).forEach(l => l.series && chart.removeSeries(l.series)); else chart.removeSeries(inst.series);
    inst.row.remove();
    if(sub && pane && pane.getSeries().length === 0 && chart.panes().length > 1) { try { chart.removePane(pane.paneIndex()) } catch(e) {} }
    list.splice(list.indexOf(inst), 1); if(sub) layoutPanes();
    save(); Ind.onChange && Ind.onChange();
  }

  /* ---- settings dialog (generic: the fields come from the definition) ---- */
  const back: any = document.createElement('div');
  back.className = 'idlg-back'; back.hidden = true; document.body.appendChild(back);
  let openFor = null;
  const esc = t => String(t).replace(/[&<>"]/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;' }[c]));
  function openSettings(inst) {
    const def = inst.def, snap = JSON.stringify({ p:inst.params, s:inst.style }), restore = () => { const o = JSON.parse(snap); inst.params = o.p; inst.style = o.s };
    let tab = 'Inputs';
    back.innerHTML = `<div class="idlg" role="dialog" aria-modal="true" aria-label="${esc(def.name)} settings">
        <div class="idlg-head"><h2></h2><button class="idlg-x" type="button" aria-label="Close">${XICON}</button></div>
        ${def.reg ? `<p class="idlg-info">${esc(def.reg.info)}</p>` : ''}
        <div class="idlg-tabs" role="tablist">${['Inputs', 'Style'].map(t => `<button type="button" role="tab" data-tab="${t}">${t}</button>`).join('')}</div>
        <div class="idlg-body"></div>
        <div class="idlg-err" role="alert" hidden></div>
        <div class="idlg-foot"><button class="idlg-btn" type="button" data-act="reset">Reset</button><span class="sp"></span><button class="idlg-btn" type="button" data-act="cancel">Cancel</button><button class="idlg-btn pri" type="button" data-act="ok">Ok</button></div></div>`;
    back.querySelector('h2').textContent = def.name;
    const body = back.querySelector('.idlg-body'), errBox = back.querySelector('.idlg-err'), dlg = back.querySelector('.idlg');
    dlg.classList.toggle('idlg-flow', !!def.flow);
    const check = () => { const m = def.validate ? def.validate(inst.params) : ''; errBox.textContent = m; errBox.hidden = !m; return !m };
    const live = needsRecompute => { if(!needsRecompute) return refresh(inst); if(check()) recompute(inst) };
    const row = (label, ctl, hint?, cls = '') => { const l = document.createElement('label'); l.className = 'idlg-row' + cls; const s = document.createElement('span'); s.textContent = label; if(hint) s.title = hint; l.append(s, ctl); return l };
    const numInput = (f, store_, recomputes, isInt) => {
      const inp: any = document.createElement('input'); inp.type = 'number'; inp.className = 'idlg-in'; inp.min = f.min; inp.max = f.max; inp.step = isInt ? 1 : f.step; inp.value = store_[f.key];
      if(def.flow) inp.title = `From ${f.min} to ${f.max}`;              // the range (audit I16), Flow only: the fixture's dialogs stay 1:1
      const okv = v => Number.isFinite(v) && (!isInt || Number.isInteger(v)) && v >= f.min && v <= f.max;
      inp.oninput = () => { const v = inp.valueAsNumber; inp.classList.toggle('bad', !okv(v)); if(okv(v)) { store_[f.key] = v; live(recomputes) } };
      inp.onchange = () => { let v = inp.valueAsNumber; if(!Number.isFinite(v)) v = f.def; v = Math.min(f.max, Math.max(f.min, isInt ? Math.round(v) : v)); inp.value = v; inp.classList.remove('bad'); store_[f.key] = v; live(recomputes) };
      return inp;
    };
    let cpop = null;
    const closeCpop = () => { if(cpop){ cpop.owner.classList.remove('open'); cpop.remove(); cpop = null } };
    function colorBtn(get, set, label) {
      const b = document.createElement('button'); b.type = 'button'; b.className = 'idlg-cbtn'; b.title = label; b.setAttribute('aria-label', label + ' colour'); b.style.setProperty('--c', get());
      b.onclick = (e: any) => {
        e.preventDefault(); e.stopPropagation(); const was = cpop && cpop.owner === b; closeCpop(); if(was) return;
        cpop = document.createElement('div'); cpop.className = 'idlg-cpop'; cpop.owner = b; b.classList.add('open');
        PALETTE.forEach(c => { const s = document.createElement('button'); s.type = 'button'; s.style.background = c; s.setAttribute('aria-label', c); s.setAttribute('aria-pressed', String(get() === c));
          s.onclick = (ev: any) => { ev.preventDefault(); ev.stopPropagation(); set(c); b.style.setProperty('--c', c); closeCpop(); refresh(inst) }; cpop.appendChild(s) });
        dlg.appendChild(cpop);
        const br = b.getBoundingClientRect(), dr = dlg.getBoundingClientRect();
        cpop.style.top = (br.bottom - dr.top + 6) + 'px'; cpop.style.left = Math.max(8, br.right - dr.left - cpop.offsetWidth) + 'px';
        cpop.querySelector('[aria-pressed="true"]')?.focus();
      };
      return b;
    }
    const sel = (options, value, onChange, fmt: (v: any) => string = String) => { const s = document.createElement('select'); s.className = 'idlg-in sm'; options.forEach(o => s.add(new Option(fmt(o), String(o), false, String(value) === String(o)))); s.onchange = () => onChange(s.value); return s };
    const checkbox = (on, onChange, label) => { const c = document.createElement('input'); c.type = 'checkbox'; c.className = 'idlg-cb'; c.checked = on; c.setAttribute('aria-label', label); c.onchange = () => onChange(c.checked); return c };
    function field(f, store_, recomputes) {
      if(f.kind === 'fixed') { const s = document.createElement('span'); s.className = 'idlg-fixed'; s.textContent = f.text; return row(f.label, s, f.hint) }
      if(f.kind === 'bool') {
        const t = document.createElement('span'); t.className = 'toggle t02';
        t.innerHTML = `<input type="checkbox" role="switch" ${store_[f.key] ? 'checked' : ''}><span class="track"></span><span class="thumb"></span>`;
        t.querySelector('input').onchange = (e: any) => { store_[f.key] = e.target.checked; live(recomputes) };
        return row(f.label, t, f.hint);
      }
      if(f.kind === 'select') {
        const s = document.createElement('select'); s.className = 'idlg-in';
        f.options.forEach(o => s.add(new Option(f.labels ? f.labels[o] ?? String(o) : String(o), String(o), false, String(store_[f.key]) === String(o))));
        s.onchange = () => {
          store_[f.key] = typeof f.options[0] === 'number' ? +s.value : s.value; live(recomputes);
          if(recomputes && def.inputs.some(x => x.when)) { paint(); (body.querySelector(`select[data-key="${f.key}"]`) as any)?.focus() }   // fields shown by this choice
        };
        if(def.flow) s.dataset.key = f.key;
        return row(f.label, s, f.hint);
      }
      if(f.kind === 'multi') {
        const host = document.createElement('div'); host.className = 'fl idlg-fl';
        const all = f.all(), state = new Set(store_[f.key] === null ? all : store_[f.key]);
        makeFilter(host, { title:f.title, searchable:f.searchable, placeholder:'Search…', grid:f.grid, mono:f.mono, max:f.max, getOptions:f.options, state,
          summary:s => s.size === all.length ? `All (${all.length})` : s.size === 0 ? 'None' : s.size <= 2 ? [...s].sort().join(', ') : `${s.size} selected`,
          onChange:() => { store_[f.key] = state.size === all.length && f.def === null ? null : [...state]; live(recomputes) } });
        return row(f.label, host);
      }
      /* EXEC-TERMINAL-FLOW-IND: broker codes (a default may be a token: a classification, the three largest net buyers) */
      if(f.kind === 'brokers') {
        const host = document.createElement('div'); host.className = 'fl idlg-fl';
        const state = new Set<string>(f.resolve(store_[f.key]));
        makeFilter(host, { title:'Broker', searchable:true, placeholder:'Search broker code…', grid:true, mono:true, max:f.max,
          getOptions:() => allBrokers().map(b => ({ id:b, label:b })), state,
          summary:s => {
            /* a default given as a rule (a classification, the largest net buyers) is named as such (audit I8) */
            const tok = typeof store_[f.key] === 'string' && f.tokenLabel ? f.tokenLabel(store_[f.key]) : '';
            if(tok) return s.size ? `${tok} (${s.size})` : `${tok} (not loaded)`;
            return s.size === 0 ? 'None' : s.size <= 3 ? [...s].sort().join(', ') : `${s.size} selected`;
          },
          onChange:() => { store_[f.key] = [...state].sort(); live(recomputes) } });
        return row(f.label, host, f.hint);
      }
      /* a date: empty = the first visible candle; "On chart" picks it with the range tool (the dialog steps aside) */
      if(f.kind === 'date') {
        const box = document.createElement('span'); box.className = 'idlg-ctl';
        const inp: any = document.createElement('input'); inp.type = 'date'; inp.className = 'idlg-in'; inp.value = store_[f.key] === 'view' ? '' : store_[f.key];
        inp.title = 'Empty: the first visible candle'; inp.setAttribute('aria-label', f.label);
        inp.onchange = () => { store_[f.key] = inp.value || 'view'; live(recomputes) };
        const pick = document.createElement('button'); pick.type = 'button'; pick.className = 'idlg-btn'; pick.textContent = 'On chart';
        pick.onclick = () => {
          back.hidden = true;
          const back_ = (sel: string) => { back.hidden = false; (body.querySelector(sel) as any)?.focus() };
          ctx.selectRangeOnChart(from => { store_[f.key] = from; live(recomputes); paint(); back_(`input[aria-label="${f.label}"]`) },
            () => back_(`input[aria-label="${f.label}"] + .idlg-btn`));
        };
        box.append(inp, pick);
        return row(f.label, box, f.hint);
      }
      if(f.kind === 'button') {
        const b = document.createElement('button'); b.type = 'button'; b.className = 'idlg-btn'; b.textContent = f.label;
        b.onclick = () => { const d = defaults(def.inputs); f.reset.forEach(k => { store_[k] = d[k] }); live(recomputes); paint() };
        const w = document.createElement('div'); w.className = 'idlg-row compact'; w.appendChild(b); return w;
      }
      if(f.kind === 'int' || f.kind === 'num') return row(f.label, numInput(f, store_, recomputes, f.kind === 'int'), f.hint);
      const box = document.createElement('div'); box.className = 'idlg-sw';
      PALETTE.forEach(c => { const b = document.createElement('button'); b.type = 'button'; b.style.background = c; b.setAttribute('aria-label', 'Color ' + c); b.setAttribute('aria-pressed', String(store_[f.key] === c));
        b.onclick = () => { store_[f.key] = c; box.querySelectorAll('button').forEach(x => x.setAttribute('aria-pressed', String(x === b))); live(false) }; box.appendChild(b) });
      return row(f.label, box);
    }
    /* Style tab of a registry indicator: one row per plotted output, then fill / guides / opacity / offset */
    function styleMulti() {
      const st = inst.style, r = def.reg;
      inst.parts.forEach(pt => {
        const s = st.out[pt.o.k], line = document.createElement('div'); line.className = 'idlg-row compact';
        const left = document.createElement('span'); left.className = 'idlg-lab';
        left.append(checkbox(s.on, v => { s.on = v; refresh(inst) }, 'Show ' + pt.o.label), document.createTextNode(pt.o.label));
        const right = document.createElement('span'); right.className = 'idlg-ctl';
        const pair = pt.kind === 'hist' ? (/rising/.test(pt.o.rule) ? ['Rising', 'Falling'] : /optional_state/.test(pt.o.rule) ? null : ['Positive', 'Negative']) : pt.kind === 'seg' || pt.kind === 'dots' ? ['Up trend', 'Down trend'] : null;
        if(pair) right.append(colorBtn(() => s.color, c => { s.color = c }, pair[0]), colorBtn(() => s.color2, c => { s.color2 = c }, pair[1]));
        else if(/optional_state/.test(pt.o.rule)) {
          const lab = document.createElement('label'); lab.className = 'idlg-mini';
          lab.append(checkbox(!!s.states, v => { s.states = v; refresh(inst) }, 'State colours'), document.createTextNode('State colours'));
          right.append(lab, colorBtn(() => s.color, c => { s.color = c }, 'Bars'));
        } else right.append(colorBtn(() => s.color, c => { s.color = c }, pt.o.label));
        if(pt.kind !== 'hist') right.append(sel([1, 2, 3, 4], s.width, v => { s.width = +v; refresh(inst) }, v => v + ' px'));
        line.append(left, right); body.appendChild(line);
      });
      const extra = (label, ctl) => { const l = document.createElement('div'); l.className = 'idlg-row compact'; const a = document.createElement('span'); a.className = 'idlg-lab'; a.append(...label); l.append(a, ctl); body.appendChild(l) };
      if(def.fill) extra([checkbox(st.fill.on, v => { st.fill.on = v; refresh(inst) }, 'Background fill'), document.createTextNode('Background fill')],
        sel([5, 10, 15, 20, 30], st.fill.opacity, v => { st.fill.opacity = +v; refresh(inst) }, v => v + '%'));
      if(r.guides.length) {
        const t = document.createElement('input'); t.type = 'text'; t.className = 'idlg-in'; t.value = st.guides.levels; t.setAttribute('aria-label', 'Reference levels');
        t.oninput = () => { st.guides.levels = t.value; refresh(inst) };
        extra([checkbox(st.guides.on, v => { st.guides.on = v; refresh(inst) }, 'Reference lines'), document.createTextNode('Reference lines')], t);
      }
      extra([document.createTextNode('Opacity')], sel([100, 75, 50, 25], st.opacity, v => { st.opacity = +v; refresh(inst) }, v => v + '%'));
      extra([document.createTextNode('Offset (bars)')], numInput({ key:'offset', min:-100, max:100, def:0 }, st, false, true));
    }
    function paint() {
      closeCpop();
      back.querySelectorAll('[data-tab]').forEach(b => b.setAttribute('aria-selected', String(b.dataset.tab === tab)));
      body.innerHTML = '';
      if(tab === 'Inputs') def.inputs.forEach(f => { if(!f.when || f.when(inst.params)) body.appendChild(field(f, inst.params, true)) });
      else if(def.multi) styleMulti();
      else def.style.forEach(f => body.appendChild(field(f, inst.style, false)));
      check();
    }
    const close = keep => {
      if(keep && !check()) { tab = 'Inputs'; paint(); return }   // keep the dialog open until the inputs are valid
      closeCpop();
      if(!keep) { restore(); recompute(inst) }
      else {
        save();
        /* EXEC-TERMINAL-UNDO (user 2026-10-29: "saya tweak parameternya ... fungsi control set adalah meng-undo parameter yang
           saya tweak"): Ok with changed inputs or style is one step of the chart's undo timeline (Ctrl/Cmd+Z, redo Ctrl+Y) */
        const after = JSON.stringify({ p:inst.params, s:inst.style });
        if(after !== snap) {
          const hid = inst.hid;
          const set = (json: string) => { const cur = byHid(hid); if(!cur) return; const o = JSON.parse(json); cur.params = o.p; cur.style = o.s; recompute(cur); save() };
          Hist.push({ undo:() => set(snap), redo:() => set(after) });
        }
      }
      back.hidden = true; document.removeEventListener('keydown', onKey, true); openFor = null; inst.row.querySelector('[data-act="cfg"]').focus({ focusVisible:false } as any);
    };
    const onKey = (e: any) => {
      if(back.hidden) return;                                            // stepped aside for a pick on the chart: its keys are the chart's
      if(cpop && e.key === 'Escape') { e.stopPropagation(); e.preventDefault(); const o = cpop.owner; closeCpop(); o.focus(); return }
      if(document.querySelector('.cs-pop:not([hidden]), .idlg .fl-pop:not([hidden])')) return;      // a dropdown list is open: it handles Esc itself
      if(e.key === 'Escape') { e.stopPropagation(); e.preventDefault(); close(false) }
      else if(e.key === 'Enter' && e.target.tagName === 'INPUT' && e.target.type === 'number') { e.preventDefault(); e.target.blur(); close(true) }
      else if(e.key === 'Tab') {
        const f = [...back.querySelectorAll('button,input,select')].filter(x => !x.disabled && x.offsetParent), a = document.activeElement;
        if(e.shiftKey && a === f[0]) { e.preventDefault(); f.at(-1).focus() } else if(!e.shiftKey && a === f.at(-1)) { e.preventDefault(); f[0].focus() }
      }
    };
    back.onmousedown = (e: any) => { if(cpop && !cpop.contains(e.target) && e.target !== cpop.owner) closeCpop() };
    back.onclick = (e: any) => {
      const t = e.target.closest('[data-tab]'), a = e.target.closest('[data-act]');
      if(e.target === back) close(false);
      else if(t) { tab = t.dataset.tab; paint() }
      else if(e.target.closest('.idlg-x')) close(false);
      else if(a && a.dataset.act === 'ok') close(true);
      else if(a && a.dataset.act === 'cancel') close(false);
      else if(a && a.dataset.act === 'reset') {
        inst.params = defaults(def.inputs);
        inst.style = def.multi ? regStyle(def, inst.base) : { ...defaults(def.style), ...(def.style.some(f => f.key === 'color' && f.def !== undefined) ? {} : { color:PALETTE[0] }) };
        recompute(inst); paint();
      }
    };
    document.addEventListener('keydown', onKey, true);
    openFor = inst; back.hidden = false; paint();
    ([...body.querySelectorAll('input:not([type=checkbox]),select,.fl-btn')].find((x: any) => x.offsetParent) as any || back.querySelector('.idlg-btn.pri')).focus();
  }

  /* ---- wiring ---- */
  displayHooks.push(() => list.forEach(refresh));
  tipHooks.push(i => list.forEach(inst => paintRow(inst, i)));
  Ind.countOf = id => list.filter(i => i.def.id === id).length;
  Ind.count = () => list.length;
  /* undo / redo: an indicator comes back with the same inputs, style and visibility */
  /* every step names its indicator by a history id that a revived indicator keeps (front-end audit I3: a step holding the
     object lost it after remove + undo, and a redo then added a second copy) */
  const snapOf = inst => JSON.parse(JSON.stringify({ def:inst.def.id, params:inst.params, style:inst.style, on:inst.on, base:inst.base, hid:inst.hid }));
  const revive = snap => {
    if(byHid(snap.hid)) return byHid(snap.hid);                       // already there: never a second copy
    const inst = add(snap.def, JSON.parse(JSON.stringify(snap))); if(inst) inst.hid = snap.hid;
    save(); Ind.onChange && Ind.onChange(); return inst;
  };
  const drop = hid => { const inst = byHid(hid); if(inst) remove(inst) };
  function userAdd(id) {
    const inst = add(id); if(!inst) return null;
    const snap = snapOf(inst);
    Hist.push({ undo:() => drop(snap.hid), redo:() => revive(snap) });
    return inst;
  }
  function userRemove(inst) {
    const snap = snapOf(inst);
    remove(inst);
    Hist.push({ undo:() => revive(snap), redo:() => drop(snap.hid) });
  }
  Ind.add = id => userAdd(id);
  Ind.removeAll = () => {
    if(!list.length) return;
    const snaps = list.map(snapOf);
    [...list].forEach(remove);
    Hist.push({ undo:() => snaps.forEach(revive), redo:() => snaps.forEach(s => drop(s.hid)) });
  };

  /* saved lists from before the registry used 'ma' / 'ema' (one MA indicator with a type switch) */
  const migrate = o => {
    if(o.def !== 'ma' && o.def !== 'ema') return o;
    const key = String(o.params && o.params.type || (o.def === 'ema' ? 'EMA' : 'SMA')).toLowerCase(), st = o.style || {};
    return { def:key, on:o.on, params:{ length:o.params && o.params.length, source:String(o.params && o.params.source || 'close').toLowerCase() },
      style:{ out:{ [key]:{ color:st.color, width:st.width } }, offset:o.params && o.params.offset || 0 } };
  };
  try { JSON.parse(store.get(KEY) || '[]').map(migrate).forEach(o => add(o.def, o)) } catch(e) {}
  save();
  const Indicators = {
    defs: DEFS,
    list: () => list.map(i => ({ uid:i.uid, def:i.def.id, params:{ ...i.params }, values:i.disp || i.vals })),
    export: () => JSON.stringify(list.map(i => ({ def:i.def.id, params:i.params, style:i.style, on:i.on }))),
    import: json => { [...list].forEach(remove); JSON.parse(json).map(migrate).forEach(o => add(o.def, o)); save() },
    add, count: () => list.length,
    /* EXEC-TERMINAL-FLOW-IND: for the live check and the reviewers (verification/terminal_api/flow_indicators) */
    removeAll: () => [...list].forEach(remove),
    flowIds: () => DEFS.filter(d => d.flow).map(d => d.id),
    values: (from = '2025-01-01') => list.filter(i => i.def.flow).map(i => ({ id:i.def.id, params:{ ...i.params }, title:i.def.title(i.params),
      outputs:Object.fromEntries(Object.entries(i.raw || {}).filter(([k]) => !k.startsWith('_')).map(([k, a]: [string, any]) =>
        [i.raw._labels && /^b\d$/.test(k) ? i.raw._labels[+k[1] - 1] : k, a.flatMap((v, t) => ohlc[t].time >= from ? [[ohlc[t].time, v]] : [])])) }))
  };
  (window as any).marketLabIndicators = Indicators;
  return Indicators;
}
