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
import { needsDetail, previewRequest } from './api/request.ts';
import { testName } from './grammar.ts';
import { render as renderCondWin } from './condwin.ts';
import { spin } from '../../terminal/src/ui/spin.ts';
import { chartTicker, runTickers } from './picked.ts';
import { Previews, portRows, previewKey, type Rows } from './preview.ts';
import { NO_STOCK } from './picker.ts';
import { renderFilterBar } from './filterbar.ts';
import { LANES, NARROW, drawSignalLanes, initLanes, laneSignals } from './lanes.ts';
import { tap } from '../../shared/touch-words.ts';   // UD81: touch words on a touch screen

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
  // Stage D (D6): with a test card the worker's combined entry (its own window rule for a test), as the run reads it
  const worker = needsDetail() ? API.tracked(tk, '__entry') : null;
  if(worker) entry.set(worker);
  else if(active.length){
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
/* EXEC-BACKTEST-LOAD (user 2026-10-27: "Hanya loading chart, kemudian loading indicator yang di bawah"; "Seperti bagian
   terminal"): the chart draws once the ticker's prices (and a run's events) are there; the broker data of a flow card
   follows, and until it is there its lanes and the entry signal say they are loading (flowWait) instead of drawing a
   preview that leaves the flow card out */
const prepared = (tk: string) => loaded(tk) && (!eventsNeeded(tk) || failed.has(tk + '|events'));
const flowWait = (tk: string) => needsFlow() && !loaded(tk, true) && !failed.has(tk + '|flow') && !(fresh() && S.result.ev.cond.has(tk));
const preparing = new Set<string>();
const redrawIf = (tk: string) => { if (S.sigTicker === tk && prepared(tk)) { refreshSignals(); renderCondWin() } };
function prepare(tk: string) {
  const key = `${tk}|${eventsNeeded(tk)}`;
  // the bars and events only while they are missing: a redraw that waits for the broker data calls prepare again, and
  // asking (and redrawing on) bars it already has would never stop
  if (!prepared(tk) && !preparing.has(key)) {
    preparing.add(key);
    const R = S.result;
    const ev = eventsNeeded(tk) ? API.events(R.id, tk).then(e => { R.ev.cond.set(tk, new Map(e.conditions.filter(x => x.ticker === tk).map(x => [x.condition_id, x.track]))) },
      e => { failed.add(tk + '|events'); toastError(e.message) }) : Promise.resolve();
    Promise.all([load(tk, false, needsFlow()), ev]).then(() => { preparing.delete(key); redrawIf(tk) },
      e => { preparing.delete(key); failed.add(tk + '|bars'); toastError(e.message); if (S.sigTicker === tk) refreshSignals() });
  }
  if (needsFlow() && !loaded(tk, true) && !preparing.has(tk + '|flow')) {
    preparing.add(tk + '|flow');
    load(tk).then(() => load(tk, true)).then(() => { preparing.delete(tk + '|flow'); redrawIf(tk) },
      e => { preparing.delete(tk + '|flow'); if (loaded(tk)) { failed.add(tk + '|flow'); toastError(e.message); redrawIf(tk) } });
  }
}

/* the portfolio table's entry signals: the run's own (fresh result) or the server's preview of the current settings
   (preview.ts: the latest wins, CONTRACT.md P8). A stock the run or the preview left out (TICKERS_EXCLUDED, or every
   one of them: UNIVERSE_EMPTY) has no count: the table's '—' with the error its data gave in the page's tooltip; the
   preview's warnings are one short line in the page's toast, when an answer brings one the previous answer did not. */
const previews = new Previews({
  ask: (q, o) => API.signalsPreview(q, o),
  current: () => previewWanted() ? previewKey(previewRequest()) : null,
  // single mode has no table to point at: the chart's stock left out says its own reason (the detail's error)
  answered: note => { const d = S.mode !== 'portfolio' ? previews.detail(previewRequest()) : null;
    if (d?.error) toastError(d.error.message); else if (note) toast(note, true); refreshSignals() },
  failed: message => toastError(message),
});
/** a preview is asked: the portfolio table's, or the chart's tracks of a test card (Stage D, D6) */
const previewWanted = () => (S.mode === 'portfolio' && S.tickers.length > 0) || needsDetail();
/** Stage D (D6): the worker's tracks of the chart's ticker for the current settings into the API (asked with the
    preview); false while they are on the way. A fresh run's own events need none. */
const detailReady = (tk: string): boolean => {
  if (!needsDetail() || (fresh() && S.result.ev.cond.has(tk))) { API.tracks(tk, null); return true }
  const q = previewRequest();
  if (S.mode !== 'portfolio') previews.rows(q);                 // asks it (the portfolio table asks it in its mode)
  const d = previews.detail(q);
  API.tracks(tk, d ?? null);
  return d !== undefined;
};
const portSig = (): Rows => previews.rows(S.tickers.length ? previewRequest() : null,
  fresh() ? portRows(S.result.raw.tables.per_ticker, S.result.raw.meta.warnings) : null);

/* =====================================================================
   7 · SIGNAL CHART — candles + small arrows per condition + lanes
   ===================================================================== */
let pc: L.IChartApi, candle: L.ISeriesApi<'Candlestick'>, markers: L.ISeriesMarkersPluginApi<L.Time>, laneState: { sig: Sig; idx: number[]; wait?: boolean } | null = null, zoomN = 252;
/** the left gutter of the chart: the left header over the price pane and the lane labels and switches under it */
const LANE_GUTTER = 200;
export const initPriceChart = () => {
  const el = $('priceChart');
  pc = L.createChart(el, { autoSize:true, localization:{locale:'id-ID', priceFormatter:(v: number)=>nf(v, Math.abs(v)<100?2:0)}, layout:{background:{type:L.ColorType.Solid,color:css('--surface')}, textColor:css('--text-3'), fontFamily:'Inter, "Segoe UI", system-ui, sans-serif', attributionLogo:false, panes:{separatorColor:css('--border'), enableResize:true}},
    grid:{vertLines:{visible:false},horzLines:{visible:false}}, rightPriceScale:{borderColor:css('--border')}, leftPriceScale:{visible:!NARROW.matches, minimumWidth:LANE_GUTTER, borderColor:css('--border'), ticksVisible:false}, timeScale:{borderColor:css('--border'), rightOffset:4},
    crosshair:{mode:L.CrosshairMode.Normal} });
  candle = pc.addSeries(L.CandlestickSeries, {upColor:PAL.up,downColor:PAL.dn,borderUpColor:PAL.up,borderDownColor:PAL.dn,wickUpColor:PAL.up,wickDownColor:PAL.dn, priceLineVisible:false, priceFormat:{type:'price',precision:0,minMove:1}});
  markers = L.createSeriesMarkers(candle, []);
  pc.timeScale().subscribeVisibleLogicalRangeChange(() => requestAnimationFrame(drawLanes));
  new ResizeObserver(() => requestAnimationFrame(drawLanes)).observe($('priceChart'));
  initLanes(pc);
  NARROW.addEventListener('change', () => { pc.applyOptions({ leftPriceScale:{ visible:!NARROW.matches } }); requestAnimationFrame(drawLanes) });
};
/** theme change: the chart's colours (the reference's themeBtn handler) */
export const themeChart = () => {
  candle.applyOptions({upColor:PAL.up,downColor:PAL.dn,borderUpColor:PAL.up,borderDownColor:PAL.dn,wickUpColor:PAL.up,wickDownColor:PAL.dn});
  pc.applyOptions({layout:{background:{type:L.ColorType.Solid,color:css('--surface')}, textColor:css('--text-3')}, grid:{vertLines:{visible:false},horzLines:{visible:false}}});
};
let lastSig: Sig | null = null;
export const getLastSig = () => lastSig;
export const refreshSignals = () => {
  // the chart shows one of the stocks the settings run on, on every change of mode, picked stocks and run (review: a
  // ticker left over from single mode was asked from the run's events)
  const U = universe(), shown = U.filter(drawable), tk = S.sigTicker = chartTicker(S.sigTicker, shown, ran());
  // the ticker select and the portfolio table (which asks the preview) do not wait for the chart's bars (review PG-1)
  tickerSelect(shown, tk); portTable(U, tk);
  if(!tk){ chartLoading(null); noChart(); return }
  // EXEC-BACKTEST-SPIN S1 (user 2026-10-27): until the ticker's prices are there the chart is emptied (no candles of
  // another stock under this one's name) and shows the loading ring with the ticker (S2)
  if(!prepared(tk)){ if (chartLoading(tk)) noChart(); prepare(tk); return }
  chartLoading(null);
  const fwait = flowWait(tk); if (fwait) prepare(tk);
  // Stage D (D6): a test card waits for the worker's tracks (the preview's detail), a flow card for the broker data
  const swait = !detailReady(tk), wait = fwait || swait;
  const D = DATA[tk], DAYS = D.dates, N = DAYS.length, sig = chartSignals(tk); lastSig = wait ? null : sig;   // the signal count waits too
  const pending = (c: Card) => (fwait && catOf(c).group === 'flow' && c.type !== 'test') || (swait && c.type === 'test');
  const idx: number[] = []; for(let i=0;i<N;i++) if(inRange(DAYS, i)) idx.push(i);
  candle.setData(idx.map(i=>({time:DAYS[i], open:D.o[i], high:D.h[i], low:D.l[i], close:D.c[i]})));
  laneState = {sig, idx, wait};
  // markers (Tahap D, the design): the trades of the last run numbered (the selected one blue) with their exits and
  // returns; without trades, an arrow on each day the entry rule switches on (the conditions are the lanes below)
  const mk: L.SeriesMarker<L.Time>[] = [], R = S.result, TR = R && !S.hidden.__trades ? R.trades.filter(t=>t.tk===tk) : [];
  if(!TR.length && !S.hidden.__entry && !wait){ for(const i of idx){ if(sig.entry[i] && !sig.entry[i-1]) mk.push({time:DAYS[i], position:'belowBar', color:css('--text'), shape:'arrowUp', size:1}) } }
  TR.forEach((t, k) => { mk.push({time:R!.days[t.ei], position:'belowBar', color:k===LANES.sel?css('--blue'):PAL.up, shape:'arrowUp', size:1.1, text:String(k+1)}); mk.push({time:R!.days[t.xi], position:'aboveBar', color:t.ret>=0?PAL.up:PAL.dn, shape:'arrowDown', size:1, text:zoomN&&zoomN<=252?(t.ret>=0?'+':'')+nf(t.ret*100,1)+'%':''}) });
  mk.sort((a,b)=>a.time<b.time?-1:a.time>b.time?1:0);
  markers.setMarkers(mk);
  // Tahap D (the design): the conditions are the lanes under the chart (lanes.ts) and the formula bar above it
  // (filterbar.ts); each legacy card keeps how often its condition is true inside the period
  const span = idx.length;
  for (const x of sig.series) {
    const ce = $('cf-'+x.c.id); if(!ce) continue;
    if (pending(x.c)) { ce.textContent = x.c.type === 'test' ? 'waiting for the backtest server…' : 'loading broker data…'; continue }
    let n = 0; for(const i of idx) if(x.s[i]) n++;
    ce.innerHTML = `true on <b>${n}</b> days (${nf(span ? n/span*100 : 0,1)}%)`;
  }
  renderFilterBar(); laneSignals({ dates:DAYS, o:D.o, h:D.h, l:D.l, c:D.c }, idx, sig, tk, { card:pending, entry:wait });
  applyZoom(); drawLanes(); renderNav(); updateViewbar();
};
/** the loading ring over the chart for `tk` (null: none); true when it was not already shown for that ticker */
let loadingFor: string | null = null;
const chartLoading = (tk: string | null) => {
  let el = $('chartLoading') as HTMLElement | null;
  if (!el && tk) { el = document.createElement('div'); el.id = 'chartLoading'; el.className = 'ml-boot'; $('priceChart').parentElement.appendChild(el) }
  const changed = tk !== loadingFor; loadingFor = tk;
  if (el) { el.hidden = !tk; if (tk && changed) el.innerHTML = spin(`Loading ${esc(tk)}`) }
  return !!tk && changed;
};
const tickerSelect = (U: string[], tk: string) => { $('sigTicker').innerHTML = U.map(t=>`<option ${t===tk?'selected':''}>${esc(t)}</option>`).join(''); $('sigTicker').style.display = U.length>1 ? '' : 'none' };
/* the portfolio signal table (the reference's), on the picked stocks; nothing picked: the step's empty note */
const portTable = (U: string[], tk: string) => {
  if(S.mode!=='portfolio'){ $('portSig').hidden = true; if (!needsDetail()) previews.drop(); return }
  const P = portSig(); const rows = U.map(t => { const {n, last, left} = P(t); const tr = S.result ? S.result.trades.filter(x=>x.tk===t) : []; const w = tr.filter(x=>x.ret>0).length;
      return `<tr class="${t===tk?'on':''}" data-t="${esc(t)}"><td><b>${esc(t)}</b></td><td ${left?TT(ttH(`${esc(t)} left out`, [['Error', esc(left.code)]], esc(left.message))):''}>${n ?? '—'}</td><td>${esc(last||'—')}</td><td>${S.result?tr.length:'—'}</td><td>${S.result&&tr.length?nf(w/tr.length*100,0)+'%':'—'}</td><td class="${S.result?cls(tr.reduce((s,x)=>s+x.pnl,0)):''}">${S.result?rp(tr.reduce((s,x)=>s+x.pnl,0)):'—'}</td></tr>` }).join('');
  $('portSig').hidden = false; $('portSig').innerHTML = `<div style="font-size:12px;font-weight:600;margin-bottom:6px">Signals across the universe <span style="color:var(--text-3);font-weight:400">— ${tap('click', 'tap')} a row to show it on the chart</span></div>${U.length ? `<table class="sigtbl"><thead><tr><th>Ticker</th><th>Entry signals</th><th>Last signal</th><th>Trades</th><th>Win rate</th><th>P&L</th></tr></thead><tbody>${rows}</tbody></table>` : `<div class="exempty">${NO_STOCK}</div>`}`;
  $('portSig').querySelectorAll('[data-t]').forEach((r: HTMLElement) => r.onclick = () => { if(!drawable(r.dataset.t)) return; S.sigTicker = r.dataset.t; refreshSignals() });
};
/* no stock the chart can show (none picked, or none whose bars could be read): the chart, its legend and lanes are
   empty; the table shows the empty note or the picked stocks */
const noChart = () => {
  lastSig = null; candle.setData([]); markers.setMarkers([]); laneState = { sig:{ series:[], entry:new Uint8Array(0), dates:[] }, idx:[] };
  renderFilterBar(); laneSignals(null);
  applyZoom(); drawLanes(); renderNav(); updateViewbar();
};
const applyZoom = () => { const n = laneState ? laneState.idx.length : 0; if(!zoomN || zoomN>=n) pc.timeScale().fitContent(); else pc.timeScale().setVisibleLogicalRange({from:n-zoomN, to:n+3}) };
/** the signal lanes under the chart on its visible range (lanes.ts; the design's xsLanes) */
export const drawLanes = () => drawSignalLanes();
/** the chart's own listeners (the reference wires them at start: zoom buttons, ticker select) */
export const bindSignals = () => {
  // a user action on this page lets a preview another tab replaced be asked again (preview.ts)
  for (const ev of ['pointerdown', 'keydown']) document.addEventListener(ev, () => previews.userAction(), true);
  $('zoomSeg').onclick = (e: MouseEvent) => { const b = (e.target as HTMLElement).closest('[data-z]') as HTMLElement; if(!b) return; zoomN = +b.dataset.z; $('zoomSeg').querySelectorAll('button').forEach((x: HTMLElement)=>x.classList.toggle('on',x===b)); refreshSignals() };
};
export const bindTicker = () => { $('sigTicker').onchange = (e: Event) => { S.sigTicker = (e.target as HTMLSelectElement).value; refreshSignals() } };

export const condName = (c: Card) => { if(c.type==='test') return testName(c); if(c.type==='reg') return regName(c); const C = catOf(c), lc = c as any; const par = C.params.map(([k])=>lc[k]).join(','); return `${C.label}${par?` (${par})`:''} ${C.noVal?opLabel(c,lc.op):`${OPS[lc.op]||lc.op} ${lc.val}${C.unit&&C.unit!=='Rp B'?C.unit:C.unit?' '+C.unit:''}`}` };

/* exit signals: same condition model and catalog as entry (the reference's exitSeries, section 8) */
export const exitSeries = (tk: string) => { const N = DATA[tk] ? DATA[tk].dates.length : 0, r = new Uint8Array(N), act = S.exitConds.filter(c => c.on && condReady(c)); if(!act.length) return r;
  const ss = act.map(c => evalCond(tk, c)); for(let i=0;i<N;i++){ const hit = ss.filter(s => s[i]).length; r[i] = +(S.exitLogic==='all' ? hit===ss.length : hit>0) } return r };
