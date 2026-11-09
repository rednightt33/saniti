/* EDGE financial terminal (EXEC-TERMINAL-API T5): the reference page 03-terminal-right-panel.html as modular
   TypeScript. The sections start in the reference's own order, so listeners and first draws happen in the same
   sequence. /terminal-app/?fixture=reference runs on the reference's synthetic data for the 1:1 check; otherwise the
   page reads the published files of the rack through EDGE. */
import './styles/terminal.css';
import './styles/spin.css';                                  // EXEC-BACKTEST-SPIN: the shared loading ring
import * as L from 'lightweight-charts';
import IND_REG from './data/indRegistry.json';
import { fixtureData } from './data/fixture';
import { liveData, TerminalError } from './data/live';
import type { MarketData, Point } from './data/types';
import type { Ctx } from './app/context';
import { $, brokerEnd, setCountries, setLogos, spin, store } from './app/context';
import { mark } from './app/perf';
import { initChart } from './app/chart';
import { initStats } from './app/stats';
import { initVolume } from './app/volume';
import { initAxis } from './app/axis';
import { initPicker } from './app/picker';
import { finishFlow, initFlow } from './app/flow';
import { initEvents } from './app/events';
import { initDrawings } from './app/drawings';
import { initIndicators } from './app/indicators';
import { initSearch } from './app/search';
import { initSelect } from './ui/select';
import { initBroker } from './app/broker';
import { initRangeSelect } from './app/rangeSelect';
import { initReorder } from './ui/reorder';
import { initFullscreen } from './ui/fullscreen';
import { initPopout } from './app/popout';
import { initLayouts } from './app/layouts';
import { initPresets } from './app/presets';
import { initAssets } from './app/assets';
import { asTimeframe, isIntraday, periodsPerYear, tfLabel, tfTitle, type Timeframe } from './data/timeframe';
import { keyedCharts } from './data/chartTime';

/* EXEC-TERMINAL-WM (user 2026-10-27: "time frame ditambah weekly dan monthly"), live: D, W and M. The page's sections
   take the candles once when they start, so another timeframe is remembered and the page loads again (its files come
   from the browser cache); the same button again brings back the first view of the timeframe. */
let liveCtx: Ctx | null = null;
/* EXEC-INTRADAY-FEATURES C3 (user 2026-11-01): the intraday timeframes before D, W and M, those the ticker's /bundle
   answer lists (remembered for the next load, so the buttons are there before the data); one the ticker lacks is off */
const intradayOrder = (tfs: string[]) => tfs.filter(isIntraday).sort((a, b) => (parseInt(a) * (a.endsWith('h') ? 60 : 1)) - (parseInt(b) * (b.endsWith('h') ? 60 : 1)));
function paintTimeframes(tf: Timeframe, offered: string[], have?: string[]) {
  const group = $('timeframeGroup') as HTMLElement;
  group.innerHTML = [...intradayOrder(offered), 'D', 'W', 'M'].map(t => {
    const off = !!have && isIntraday(t) && !have.includes(t);
    const title = off ? `${tfTitle(t as Timeframe)}: not published for this ticker` : tfTitle(t as Timeframe);
    return `<button type="button" data-timeframe="${t}" title="${title}" aria-label="${title}" aria-pressed="${t === tf}" class="${t === tf ? 'active' : ''}"${off ? ' disabled' : ''}>${tfLabel(t as Timeframe)}</button>`;
  }).join('');
}
function timeframeButtons(): Timeframe {
  const tf = asTimeframe(store.get('ml.tf')), group = $('timeframeGroup') as HTMLElement;
  let offered: string[] = [];
  try { offered = JSON.parse(store.get('ml.tfs') || '[]') } catch {}
  paintTimeframes(tf, isIntraday(tf) && !offered.includes(tf) ? [...offered, tf] : offered);
  group.addEventListener('click', (e: any) => {
    const b = e.target.closest('button'); if (!b) return;
    e.stopImmediatePropagation();                           // the reference's handler only zooms
    if (b.dataset.timeframe === tf) { liveCtx?.resetRange(); return }
    store.set('ml.tf', b.dataset.timeframe); location.reload();
  }, true);
  return tf;
}

/* EXEC-FI-TERMINAL (user go 2026-11-01, Opsi A; "nomor 2 pakai your advice"): a government bond's page. Its yield by
   default with a Price button (the Price | Return pair becomes Yield | Price: a bond's "return" in % of a yield would
   mislead), the unit beside the symbol (a US bill's price is a discount quote, value_unit PCTDY), and no Flow Timeline,
   broker panel or events (a bond has none). The intraday buttons stay off: no intraday file is published for a bond. */
function bondPage(M: MarketData) {
  const fi = M.fixedIncome!;
  document.body.classList.add('fi-mode');
  $('workspace').classList.remove('has-right');
  const group = $('modeGroup');
  const title = (m: string) => m === 'yield' ? 'Yield to maturity, % (Statistics in basis points)'
    : fi.units.price === 'PCTDY' ? 'Price as quoted: a discount quote (US bill)' : 'Price, % of par';
  group.setAttribute('aria-label', 'Bond value');
  group.innerHTML = (['yield', 'price'] as const).map(m => `<button type="button" data-fi="${m}" class="${m === fi.metric ? 'active' : ''}" `
    + `aria-pressed="${m === fi.metric}" title="${title(m)}">${m === 'yield' ? 'Yield' : 'Price'}</button>`).join('');
  group.addEventListener('click', (e: any) => {
    const b = e.target.closest('button'); if (!b) return;
    e.stopImmediatePropagation();                           // the chart's Price | Return handler is not for a bond
    if (b.dataset.fi !== fi.metric) { store.set('ml.fi.metric', b.dataset.fi); location.reload() }
  }, true);
  const unit = fi.metric === 'yield' ? 'Yield, %' : fi.units.price === 'PCTDY' ? 'Discount quote' : 'Price, % of par';
  $('symText').insertAdjacentHTML('afterend', `<span class="fi-unit" title="${title(fi.metric)} · ${fi.name}${fi.country ? ', ' + fi.country : ''}">${unit}</span>`);
}

function start(M: MarketData, rawSeries: Record<string, Point[]>) {
  const container = $('chart');
  if (!container) return null;
  const ohlc = M.ohlc;
  const ctx = {
    M, L:M.intraday ? keyedCharts(L) : L, SYMBOL:M.symbol, INSTRUMENTS:M.instruments, container,
    dates:ohlc.map(b => b.time), ohlc, volume:M.volume, lineData:M.lineData,
    closes:ohlc.map(b => b.close), N:ohlc.length, idxByTime:new Map(ohlc.map((b, i) => [b.time, i])),
    active:new Map(), catalog:M.catalog, rawSeries, IND_REG
  } as unknown as Ctx;
  ctx.endDates = M.endDates || ctx.dates;
  // an intraday candle has broker data when its session has (its key is later than the date)
  ctx.brokerEnd = brokerEnd(M.intraday ? ctx.endDates : ctx.dates, M.through?.broker);
  // EXEC-TERMINAL-WM: an annualising input's default follows the candles (registry: "252 only proposed for daily");
  // an intraday timeframe's bars per year come from its manifest (EXEC-INTRADAY-FEATURES C3)
  if (M.tf && M.tf !== 'D') for (const ind of IND_REG as any[]) for (const inp of ind.params || [])
    if (inp.k === 'annualization_periods') inp.def = periodsPerYear(M.tf, M.intraday?.barsPerYear);

  setLogos(M.logos);                                       // live only: the fixture has no logos (1:1 check)
  setCountries(M.countries);                               // a bond's flag (user 2026-11-01)
  M.logosLater?.then(setLogos, () => {});                  // ERRORS M333: after the chart, not before it
  if (M.fixedIncome) bondPage(M);
  initChart(ctx);
  initStats(ctx);
  initVolume(ctx);
  initAxis(ctx);
  initPicker(ctx);
  const flow = initFlow(ctx);
  initEvents(ctx);
  finishFlow(ctx, flow);
  initDrawings(ctx);
  initIndicators(ctx);
  ctx.presets = initPresets(ctx);                          // EXEC-IND-PRESETS: live only (null in the fixture)
  initSearch(ctx);
  initSelect();
  initBroker(ctx);
  initRangeSelect(ctx);
  if (M.mode === 'live') initReorder();                    // EXEC-TERMINAL-PANELS A1; the fixture keeps the reference order
  if (M.mode === 'live') initFullscreen();                 // EXEC-TERMINAL-FULL; the fixture's top bar stays the reference's
  if (M.mode === 'live') initPopout(ctx);                  // EXEC-TERMINAL-POPOUT: the right panel's windows
  if (M.mode === 'live') initAssets(ctx);                  // EXEC-TERMINAL-ASSETS: added assets and their Flow Timelines
  if (M.mode === 'live') document.querySelector('#symbolPill .exchange')?.remove();   // EXEC-TERMINAL-FULL-2: no "IDX" label
  if (M.mode === 'live') liveCtx = ctx;                     // the timeframe buttons reset the view through it
  /* EXEC-TERMINAL-LAYOUTS (user 2026-11-06): the chart type and Price/Return are kept (they are part of a layout); applied
     once every part that draws on the chart is there */
  if (M.mode === 'live') {
    if (store.get('ml.chart.style') === 'line') (document.querySelector('#styleGroup [data-style="line"]') as HTMLElement | null)?.click();
    if (store.get('ml.chart.mode') === 'return') (document.querySelector('#modeGroup [data-mode="return"]') as HTMLElement | null)?.click();
    initLayouts(ctx);
  }
  // EXEC-INTRADAY-FEATURES C4 (user 2026-11-01): on an intraday chart Broker activity and the Bandar detector are daily
  if (M.intraday) document.querySelector('#brokerPanel .side-title strong')?.insertAdjacentHTML('afterend',
    '<span class="flow-daily" title="Broker data is daily: each day’s figures, shown on that day’s candles">Daily</span>');
  return ctx;
}

/* live (EXEC-TERMINAL-UI-1026 U5): the chart is drawn; the broker files follow into the Flow Timeline, and into Broker
   activity when that panel is open */
function later(ctx: Ctx, M: MarketData) {
  if (!M.later) return;
  /* QA M6 (2026-11-06): the Flow rows say the files failed instead of "Loading broker data" for ever */
  const failed = () => { ctx.brokerFailed = true; ctx.redrawFlow?.();      // QA round 3 (R2-M3): "—" and no zero line at once
    const note = $('flowNote'); note.textContent = 'Broker data could not be loaded. Reload the page to try again.'; note.hidden = false;
    ctx.refreshFlowIndicators?.(); ctx.brokerPanelFailed?.() };
  /* F5: the recent years first (Flow and Broker activity), then the whole history replaces them in the Flow Timeline */
  M.later.broker.then(b => {
    ctx.flowRows = b.flow;                                 // EXEC-TERMINAL-FLOW-IND: read by the Flow indicators on setFlowData
    ctx.setFlowData(b.combos, b.flowFrom, true, b.flowTo); ctx.setBrokerPanelData(b.broker); mark('flow: recent years');
    M.later!.brokerAll.then(all => {
      ctx.flowRows = all.flow;
      ctx.setFlowData(all.combos, all.flowFrom, false, all.flowTo); mark('flow: every year');
      (window as any).__flowAll = true;                    // the whole broker history is in (live checks wait for it)
      if (all.broker.dates.length > b.broker.dates.length) ctx.setBrokerPanelData(all.broker);   // EXEC-BROKER-FULL: the whole history
    }, failed);
  }, () => { ctx.setFlowData([], ctx.N); failed() });
}

/* a message on the chart, in the reference's own panel style: the loading notice, or a load failure (role alert) */
function notice(message: string, role = 'status') {
  const host = $('chart');
  const box = document.createElement('div');
  box.className = 'st-tip';
  box.setAttribute('role', role);
  box.style.cssText = 'position:absolute;left:50%;top:40%;transform:translate(-50%,-50%);max-width:420px;pointer-events:auto';
  box.textContent = message;
  (host?.parentElement || document.body).appendChild(box);
  return box;
}
const fail = (message: string) => notice(message, 'alert');

function boot() {
  const stored = store.get('ml.symbol');
  const params = new URLSearchParams(location.search);
  /* EXEC-NAV-LEFT (ERRORS M412): opened by EDGE (?in=edge) the Statistics button is EDGE's; known from the first paint, so
     the Terminal's own folded rail is never drawn while the data loads (the message hand-shake only starts with the chart) */
  if (params.get('in') === 'edge') document.documentElement.classList.add('edge-rail');
  if (params.get('fixture') === 'reference') {
    /* the 1:1 check keeps the reference's fixed heights; &fit=1 shows the fixture in the screen-filling layout */
    if (params.get('fit') !== '1') document.documentElement.classList.remove('fit');
    /* synchronous, like the reference: it builds every compare series up front, so adding one is immediate */
    const M = fixtureData(stored);
    start(M, M.rawSeries);
    return;
  }
  /* EXEC-TERMINAL-1026B F4 (user 2026-10-26: "Oke, untuk usulan loading mapi"): before any data, the side panels take the
     state they will have (closed unless the user left them open) and the chart says what it is loading, instead of the
     reference's empty page with its sample texts */
  const ws = $('workspace');
  ws.classList.toggle('left-collapsed', (store.get('ml.stats.collapsed') ?? '1') === '1');
  ws.classList.toggle('right-collapsed', (store.get('ml.broker.collapsed') ?? '1') === '1');
  $('symText').textContent = stored || 'MAPI';
  $('rpSub').textContent = '';
  // an open side panel shows the ring too until its data is drawn (EXEC-TERMINAL-SPIN 1A)
  if (!ws.classList.contains('left-collapsed')) $('distStats').innerHTML = `<div class="st-row">${spin('Loading')}</div>`;
  if (!ws.classList.contains('right-collapsed')) $('bsBody').innerHTML = `<div class="rp-empty">${spin('Loading')}</div>`;
  const loading = document.createElement('div');            // EXEC-TERMINAL-SPIN: a spinning ring, no box
  loading.className = 'ml-boot'; loading.innerHTML = spin(`Loading ${stored || 'MAPI'}`);
  ($('chart')?.parentElement || document.body).appendChild(loading);
  mark('page script');
  const tf = timeframeButtons();
  liveData(stored, tf, store.get('ml.fi.metric') === 'price' ? 'price' : 'yield').then(M => {
    loading.remove();
    if (M.timeframes) {
      /* the buttons: every intraday timeframe seen so far (remembered for the next load), the ticker's own enabled and
         the others off with their tooltip (ERRORS M326 F4: the same list was passed twice, so none was ever off) */
      let seen: string[] = [];
      try { seen = JSON.parse(store.get('ml.tfs') || '[]') } catch (_) {}
      const offered = [...new Set([...(Array.isArray(seen) ? seen : []), ...M.timeframes].filter(t => typeof t === 'string' && isIntraday(t)))];
      store.set('ml.tfs', JSON.stringify(offered));
      paintTimeframes(M.tf || 'D', offered, M.timeframes);
    }
    const ctx = start(M, {}); mark('chart drawn');
    if (M.note) { const n = notice(M.note); setTimeout(() => n.remove(), 6000) }
    if (ctx) later(ctx, M);
  }, e => { loading.remove();
    fail(e instanceof TerminalError ? e.message : 'The terminal could not load its data. Reload the page to try again.') });
}

boot();
