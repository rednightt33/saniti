/* Signals (backtest.html sections 6 and 7): each condition's series and the combined entry per ticker, and the signal
   chart (candles, a small arrow when a condition switches on, a bold arrow when the entry rule does, one lane per
   condition, chips with counts, zoom, the portfolio signal table).
   Before a run, and while the settings are changed after one, the page previews the signals on the ticker's published
   bars with the API's condition series (the reference's live preview). After a run the chart shows the run's own
   events: the condition and entry tracks and the trades of the result (CONTRACT.md section 10). */
import * as L from 'lightweight-charts';
import type { SignalTrack } from './core/contract.ts';
import type { Card } from './api/types.ts';
import { API, DATA, load, loaded } from './env.ts';
import { $, COLORS, css, esc, nf, OPS, PAL, cls, rp, toast, toastError } from './format.ts';
import { catOf, condReady, evalCond, needsFlow, opLabel, regName } from './reg.ts';
import { S } from './state.ts';
import { renderNav, updateViewbar } from './builder.ts';
import { TT, ttH } from './results/svg.ts';
import { previewRequest } from './api/request.ts';
import { renderWSMid } from './workspace.ts';
import { chartTicker, runTickers } from './picked.ts';
import { Previews, portRows, previewKey, type Rows } from './preview.ts';
import { NO_STOCK } from './picker.ts';

export interface Sig { series: { c: Card; s: Uint8Array }[]; entry: Uint8Array; dates: string[] }

/* =====================================================================
   6 · SIGNALS (per ticker): each condition's series + the combined entry
   ===================================================================== */
export const inRange = (DAYS: string[], i: number) => DAYS[i] >= S.from && DAYS[i] <= S.to;
export const signalsFor = (tk: string): Sig => {
  const DAYS = DATA[tk].dates, N = DAYS.length;
  const active = S.conds.filter(c=>c.on && condReady(c));
  const series = active.map(c => ({c, s: evalCond(tk, c)}));
  const need = S.logic==='all' ? active.length : S.logic==='any' ? 1 : Math.min(S.atLeast, active.length);
  const W = Math.max(1, S.window|0), entry = new Uint8Array(N);
  if(active.length){
    const recent = series.map(() => -1e9);
    for(let i=0;i<N;i++){
      let met = 0; series.forEach((x,k) => { if(x.s[i]) recent[k] = i; if(i - recent[k] < W) met++ });
      entry[i] = met >= need ? 1 : 0;
    }
  }
  return {series, entry, dates: DAYS};
};
/** the stocks the settings run on: the ticker in single mode, the picked stocks in portfolio mode (PF1) */
export const universe = () => S.mode==='single' ? [S.ticker] : S.tickers;

/* a track of the result calendar on a ticker's own bars: true where the track is true; the bar before the period
   holds what the chart's "switches on" test needs (the track's own `on` decides the period's first bar) */
export function onBars(track: SignalTrack | undefined, days: string[], dates: string[]): Uint8Array {
  const n = dates.length, s = new Uint8Array(n);
  if (!track) return s;
  const at = new Map(days.map((d, k) => [d, k])), on = new Set(track.on), inRun = new Uint8Array(days.length);
  for (let j = 0; j + 1 < track.runs.length; j += 2) for (let k = track.runs[j]; k <= track.runs[j + 1]; k++) inRun[k] = 1;
  let first = -1;
  for (let i = 0; i < n; i++) { const k = at.get(dates[i]); if (k === undefined) continue; if (first < 0) first = i; s[i] = inRun[k] }
  if (first > 0) s[first - 1] = s[first] && !on.has(at.get(dates[first])) ? 1 : 0;
  return s;
}
/* after a run, while the settings are those of the run: the run's events (entries for every ticker come with the
   result; the condition tracks of a portfolio ticker are read when the chart shows it) */
const fresh = () => !!S.result && !S.stale && S.result.raw.meta.mode === S.mode;   // the mode switch keeps S.result for one render
const fromEvents = (tk: string): Sig | null => {
  const R = S.result, conds = R.ev.cond.get(tk);
  if (!conds) return null;
  const D = DATA[tk], active = S.conds.filter(c=>c.on && condReady(c));
  return { series: active.map(c => ({c, s: onBars(conds.get(c.id), R.days, D.dates)})), entry: onBars(R.ev.entries[tk], R.days, D.dates), dates: D.dates };
};
const chartSignals = (tk: string): Sig => (fresh() && fromEvents(tk)) || signalsFor(tk);
/** the tickers of the run the chart shows (none while the settings are not the run's) */
const ran = () => fresh() ? runTickers(S.result.raw) : [];

/* what the chart of a ticker needs before it can draw: its bars (with the broker data when a flow card is present)
   and, after a run, the run's events for it; only a ticker of the run has events (edge-bff answers any other with
   404 EVENTS_NOT_FOUND): a picked stock the run left out keeps the preview drawing (review PAGE-V2). A ticker whose
   bars could not be read (a published stock without price files, which a run leaves out with DATA_MISSING, or a
   failed download) is not drawn: its toast is shown once and the chart shows another stock (review PG-1). */
const failed = new Set<string>();
const drawable = (tk: string) => !failed.has(tk + '|bars');
const eventsNeeded = (tk: string) => ran().includes(tk) && !S.result.ev.cond.has(tk);
const prepared = (tk: string) => loaded(tk) && (!needsFlow() || loaded(tk, true) || failed.has(tk + '|flow')) && (!eventsNeeded(tk) || failed.has(tk + '|events'));
const preparing = new Set<string>();
function prepare(tk: string) {
  const flow = needsFlow(), key = `${tk}|${flow}|${eventsNeeded(tk)}`;
  if (preparing.has(key)) return;
  preparing.add(key);
  const R = S.result;
  const ev = eventsNeeded(tk) ? API.events(R.id, tk).then(e => { R.ev.cond.set(tk, new Map(e.conditions.filter(x => x.ticker === tk).map(x => [x.condition_id, x.track]))) },
    e => { failed.add(tk + '|events'); toastError(e.message) }) : Promise.resolve();
  const bars = load(tk).then(() => flow ? load(tk, true).catch(e => { failed.add(tk + '|flow'); toastError(e.message) }) : undefined);
  Promise.all([bars, ev]).then(() => {
    preparing.delete(key);
    if (S.sigTicker === tk && prepared(tk)) { refreshSignals(); if (!$('ews').hidden) renderWSMid() }
  }, e => { preparing.delete(key); failed.add(tk + '|bars'); toastError(e.message); if (S.sigTicker === tk) refreshSignals() });
}

/* the portfolio table's entry signals: the run's own (fresh result) or the server's preview of the current settings
   (preview.ts: the latest wins, CONTRACT.md P8). A stock the run or the preview left out (TICKERS_EXCLUDED, or every
   one of them: UNIVERSE_EMPTY) has no count: the table's '—' with the error its data gave in the page's tooltip; the
   preview's warnings are one short line in the page's toast, when an answer brings one the previous answer did not. */
const previews = new Previews({
  ask: (q, o) => API.signalsPreview(q, o),
  current: () => S.mode === 'portfolio' && S.tickers.length ? previewKey(previewRequest()) : null,
  answered: note => { if (note) toast(note, true); refreshSignals() },
  failed: message => toastError(message),
});
const portSig = (): Rows => previews.rows(S.tickers.length ? previewRequest() : null,
  fresh() ? portRows(S.result.raw.tables.per_ticker, S.result.raw.meta.warnings) : null);

/* =====================================================================
   7 · SIGNAL CHART — candles + small arrows per condition + lanes
   ===================================================================== */
let pc: L.IChartApi, candle: L.ISeriesApi<'Candlestick'>, markers: L.ISeriesMarkersPluginApi<L.Time>, laneState: { sig: Sig; idx: number[] } | null = null, crossX: number | null = null, zoomN = 252;
const LANE_GUTTER = 136;
export const initPriceChart = () => {
  const el = $('priceChart');
  pc = L.createChart(el, { autoSize:true, localization:{locale:'id-ID', priceFormatter:(v: number)=>nf(v, Math.abs(v)<100?2:0)}, layout:{background:{type:L.ColorType.Solid,color:css('--surface')}, textColor:css('--text-3'), fontFamily:'Inter, "Segoe UI", system-ui, sans-serif', attributionLogo:false, panes:{separatorColor:css('--border'), enableResize:true}},
    grid:{vertLines:{color:css('--border')+'80'},horzLines:{color:css('--border')+'80'}}, rightPriceScale:{borderColor:css('--border')}, leftPriceScale:{visible:true, minimumWidth:LANE_GUTTER, borderColor:css('--border'), ticksVisible:false}, timeScale:{borderColor:css('--border'), rightOffset:4},
    crosshair:{mode:L.CrosshairMode.Normal} });
  candle = pc.addSeries(L.CandlestickSeries, {upColor:PAL.up,downColor:PAL.dn,borderUpColor:PAL.up,borderDownColor:PAL.dn,wickUpColor:PAL.up,wickDownColor:PAL.dn, priceLineVisible:false, priceFormat:{type:'price',precision:0,minMove:1}});
  markers = L.createSeriesMarkers(candle, []);
  pc.timeScale().subscribeVisibleLogicalRangeChange(() => requestAnimationFrame(drawLanes));
  new ResizeObserver(() => requestAnimationFrame(drawLanes)).observe($('priceChart'));
  pc.subscribeCrosshairMove(p => { crossX = p.point ? p.point.x : null; requestAnimationFrame(drawLanes) });
};
/** theme change: the chart's colours (the reference's themeBtn handler) */
export const themeChart = () => {
  candle.applyOptions({upColor:PAL.up,downColor:PAL.dn,borderUpColor:PAL.up,borderDownColor:PAL.dn,wickUpColor:PAL.up,wickDownColor:PAL.dn});
  pc.applyOptions({layout:{background:{type:L.ColorType.Solid,color:css('--surface')}, textColor:css('--text-3')}, grid:{vertLines:{color:css('--border')+'80'},horzLines:{color:css('--border')+'80'}}});
};
let lastSig: Sig | null = null;
export const getLastSig = () => lastSig;
export const refreshSignals = () => {
  // the chart shows one of the stocks the settings run on, on every change of mode, picked stocks and run (review: a
  // ticker left over from single mode was asked from the run's events)
  const U = universe(), shown = U.filter(drawable), tk = S.sigTicker = chartTicker(S.sigTicker, shown, ran());
  // the ticker select and the portfolio table (which asks the preview) do not wait for the chart's bars (review PG-1)
  tickerSelect(shown, tk); portTable(U, tk);
  if(!tk){ noChart(); return }
  if(!prepared(tk)){ prepare(tk); return }
  const D = DATA[tk], DAYS = D.dates, N = DAYS.length, sig = chartSignals(tk); lastSig = sig;
  const idx: number[] = []; for(let i=0;i<N;i++) if(inRange(DAYS, i)) idx.push(i);
  candle.setData(idx.map(i=>({time:DAYS[i], open:D.o[i], high:D.h[i], low:D.l[i], close:D.c[i]})));
  laneState = {sig, idx};
  // markers: a small arrow on the day each condition switches on; a bold arrow for the entry signal; exits after a run
  const mk: L.SeriesMarker<L.Time>[] = [];
  sig.series.forEach(x => { if(S.hidden[x.c.id]) return; const col = COLORS[S.conds.indexOf(x.c) % COLORS.length]; for(const i of idx){ if(x.s[i] && !x.s[i-1]) mk.push({time:DAYS[i], position:'belowBar', color:col, shape:'arrowUp', size:0.5}) } });
  if(!S.hidden.__entry){ for(const i of idx){ if(sig.entry[i] && !sig.entry[i-1]) mk.push({time:DAYS[i], position:'belowBar', color:css('--text'), shape:'arrowUp', size:1.4, text:''}) } }
  const R = S.result; if(R && !S.hidden.__trades){ R.trades.filter(t=>t.tk===tk).forEach(t => { mk.push({time:R.days[t.ei], position:'belowBar', color:PAL.up, shape:'circle', size:0.8}); mk.push({time:R.days[t.xi], position:'aboveBar', color:t.ret>=0?PAL.up:PAL.dn, shape:'arrowDown', size:1, text:zoomN&&zoomN<=252?(t.ret>=0?'+':'')+nf(t.ret*100,1)+'%':''}) }) }
  mk.sort((a,b)=>a.time<b.time?-1:a.time>b.time?1:0);
  markers.setMarkers(mk);
  // chips with counts (how often each condition is true inside the period)
  const span = idx.length;
  // chips are grouped by what they are: technical indicators, flow data, price action, and the strategy's own output
  const chipOf = (x: Sig['series'][number]) => { const col = COLORS[S.conds.indexOf(x.c) % COLORS.length]; let n=0, on=0; for(const i of idx){ if(x.s[i]){ n++; if(!x.s[i-1]) on++ } }
      const ce = $('cf-'+x.c.id); if(ce) ce.innerHTML = `true on <b>${n}</b> days (${nf(n/span*100,1)}%)`;
      return `<span class="chip ${S.hidden[x.c.id]?'off':''}" data-h="${x.c.id}" ${TT(ttH(esc(condName(x.c)), [['Switches on', on+'×'], ['True on', `${n} days (${nf(n/span*100,1)}%)`]], 'Click to hide or show on the chart.'))}><i style="background:${col}"></i><span class="cn">${esc(condName(x.c).replace(/\s*\([^)]*\)/,''))}</span><b>${on}×</b></span>` };
  const GROUPS = [['tech','Technical'],['flow','Flow'],['price','Price action']];
  let nEntry = 0; for(const i of idx) if(sig.entry[i] && !sig.entry[i-1]) nEntry++;
  const cols: [string, string[]][] = GROUPS.map(([g,l]) => [l, sig.series.filter(x => catOf(x.c).group===g).map(chipOf)] as [string, string[]]).filter(([,xs]) => xs.length);
  cols.push(['Strategy', [`<span class="chip entry ${S.hidden.__entry?'off':''}" data-h="__entry" ${TT(ttH('Entry signal', [['Signals', nEntry+'×']], 'Black arrow on the chart. Click to hide or show.'))}><i></i><span class="cn">Entry signal</span><b>${nEntry}×</b></span>`,
    ...(S.result ? [`<span class="chip ${S.hidden.__trades?'off':''}" data-h="__trades" ${TT(ttH('Trades', [['On this stock', S.result.trades.filter(t=>t.tk===tk).length]], 'Dot = entry, arrow = exit with its return. Click to hide or show.'))}><i style="background:${PAL.up};border-radius:50%"></i><span class="cn">Trades</span><b>${S.result.trades.filter(t=>t.tk===tk).length}</b></span>`] : [])]]);
  $('sigChips').innerHTML = cols.map(([l,xs],k) => `<div class="lg-col ${l==='Strategy'?'out':''}"><em>${l}</em><div class="lg-items">${xs.join('')}</div></div>`).join('');
  $('sigChips').querySelectorAll('[data-h]').forEach((ch: HTMLElement) => ch.onclick = () => { S.hidden[ch.dataset.h] = !S.hidden[ch.dataset.h]; refreshSignals() });
  const rw = pc.priceScale('right').width(); if(rw) $('chartTools').style.right = (rw + 10) + 'px';
  applyZoom(); drawLanes(); renderNav(); updateViewbar();
};
const tickerSelect = (U: string[], tk: string) => { $('sigTicker').innerHTML = U.map(t=>`<option ${t===tk?'selected':''}>${esc(t)}</option>`).join(''); $('sigTicker').style.display = U.length>1 ? '' : 'none' };
/* the portfolio signal table (the reference's), on the picked stocks; nothing picked: the step's empty note */
const portTable = (U: string[], tk: string) => {
  if(S.mode!=='portfolio'){ $('portSig').hidden = true; previews.drop(); return }
  const P = portSig(); const rows = U.map(t => { const {n, last, left} = P(t); const tr = S.result ? S.result.trades.filter(x=>x.tk===t) : []; const w = tr.filter(x=>x.ret>0).length;
      return `<tr class="${t===tk?'on':''}" data-t="${esc(t)}"><td><b>${esc(t)}</b></td><td ${left?TT(ttH(`${esc(t)} left out`, [['Error', esc(left.code)]], esc(left.message))):''}>${n ?? '—'}</td><td>${esc(last||'—')}</td><td>${S.result?tr.length:'—'}</td><td>${S.result&&tr.length?nf(w/tr.length*100,0)+'%':'—'}</td><td class="${S.result?cls(tr.reduce((s,x)=>s+x.pnl,0)):''}">${S.result?rp(tr.reduce((s,x)=>s+x.pnl,0)):'—'}</td></tr>` }).join('');
  $('portSig').hidden = false; $('portSig').innerHTML = `<div style="font-size:12px;font-weight:600;margin-bottom:6px">Signals across the universe <span style="color:var(--text-3);font-weight:400">— click a row to show it on the chart</span></div>${U.length ? `<table class="sigtbl"><thead><tr><th>Ticker</th><th>Entry signals</th><th>Last signal</th><th>Trades</th><th>Win rate</th><th>P&L</th></tr></thead><tbody>${rows}</tbody></table>` : `<div class="exempty">${NO_STOCK}</div>`}`;
  $('portSig').querySelectorAll('[data-t]').forEach((r: HTMLElement) => r.onclick = () => { if(!drawable(r.dataset.t)) return; S.sigTicker = r.dataset.t; refreshSignals() });
};
/* no stock the chart can show (none picked, or none whose bars could be read): the chart, its legend and lanes are
   empty; the table shows the empty note or the picked stocks */
const noChart = () => {
  lastSig = null; candle.setData([]); markers.setMarkers([]); laneState = { sig:{ series:[], entry:new Uint8Array(0), dates:[] }, idx:[] };
  $('sigChips').innerHTML = '';
  applyZoom(); drawLanes(); renderNav(); updateViewbar();
};
const applyZoom = () => { const n = laneState ? laneState.idx.length : 0; if(!zoomN || zoomN>=n) pc.timeScale().fitContent(); else pc.timeScale().setVisibleLogicalRange({from:n-zoomN, to:n+3}) };
// condition lanes: a strip under the chart, one row per condition (+ entry row); filled where the condition is true
const LANE_H = 18;
export const drawLanes = () => {
  if(!laneState) return; const {sig, idx} = laneState, cv = $('laneCv') as HTMLCanvasElement;
  const rows = [...sig.series.map(x=>({lbl:catOf(x.c).label, col:COLORS[S.conds.indexOf(x.c)%COLORS.length], s:x.s, off:S.hidden[x.c.id], bold:false})), {lbl:'Entry', col:css('--text'), s:sig.entry, off:S.hidden.__entry, bold:true}];
  const H = rows.length*LANE_H+10, W = cv.parentElement.clientWidth, dpr = devicePixelRatio||1;
  cv.style.height = H+'px'; cv.width = W*dpr; cv.height = H*dpr; const g = cv.getContext('2d'); g.scale(dpr,dpr); g.clearRect(0,0,W,H);
  const ts = pc.timeScale(), plotW = ts.width(), bs = Math.max(1, ts.options().barSpacing), LW = pc.priceScale('left').width() || LANE_GUTTER;
  g.save(); g.beginPath(); g.rect(LW, 0, plotW, H); g.clip(); g.translate(LW, 0);
  rows.forEach((r,k) => { const y = 5+k*LANE_H;
    g.fillStyle = k%2 ? 'transparent' : css('--surface-2'); g.fillRect(0, y, plotW, LANE_H);
    if(r.off) return; g.fillStyle = r.col; g.globalAlpha = r.bold ? 1 : .85;
    const vr = ts.getVisibleLogicalRange(); const a = Math.max(0, Math.floor(vr?vr.from:0)-1), b = Math.min(idx.length-1, Math.ceil(vr?vr.to:idx.length)+1);
    for(let j=a;j<=b;j++){ const i = idx[j]; if(!r.s[i]) continue; const x = ts.logicalToCoordinate(j as L.Logical); if(x==null) continue; g.fillRect(x-bs/2, y+4, Math.max(1,bs), LANE_H-8) }
    g.globalAlpha = 1 });
  if(crossX!=null && crossX<plotW){ g.fillStyle = css('--text-3'); g.fillRect(crossX, 0, 1, H) }
  g.restore();
  g.fillStyle = css('--border'); g.fillRect(LW-1, 0, 1, H); g.fillRect(LW+plotW, 0, 1, H);
  $('laneLabels').style.width = (LW-1)+'px';
  $('laneLabels').innerHTML = rows.map((r,k)=>`<span class="${r.off?'off':''}" style="top:${5+k*LANE_H}px;height:${LANE_H}px"><i style="background:${r.col}"></i>${esc(r.lbl)}</span>`).join('');
};
/** the chart's own listeners (the reference wires them at start: zoom buttons, ticker select) */
export const bindSignals = () => {
  // a user action on this page lets a preview another tab replaced be asked again (preview.ts)
  for (const ev of ['pointerdown', 'keydown']) document.addEventListener(ev, () => previews.userAction(), true);
  $('zoomSeg').onclick = (e: MouseEvent) => { const b = (e.target as HTMLElement).closest('[data-z]') as HTMLElement; if(!b) return; zoomN = +b.dataset.z; $('zoomSeg').querySelectorAll('button').forEach((x: HTMLElement)=>x.classList.toggle('on',x===b)); refreshSignals() };
};
export const bindTicker = () => { $('sigTicker').onchange = (e: Event) => { S.sigTicker = (e.target as HTMLSelectElement).value; refreshSignals() } };

export const condName = (c: Card) => { if(c.type==='reg') return regName(c); const C = catOf(c), lc = c as any; const par = C.params.map(([k])=>lc[k]).join(','); return `${C.label}${par?` (${par})`:''} ${C.noVal?opLabel(c,lc.op):`${OPS[lc.op]||lc.op} ${lc.val}${C.unit&&C.unit!=='Rp B'?C.unit:C.unit?' '+C.unit:''}`}` };

/* exit signals: same condition model and catalog as entry (the reference's exitSeries, section 8) */
export const exitSeries = (tk: string) => { const N = DATA[tk] ? DATA[tk].dates.length : 0, r = new Uint8Array(N), act = S.exitConds.filter(c => c.on && condReady(c)); if(!act.length) return r;
  const ss = act.map(c => evalCond(tk, c)); for(let i=0;i<N;i++){ const hit = ss.filter(s => s[i]).length; r[i] = +(S.exitLogic==='all' ? hit===ss.length : hit>0) } return r };
