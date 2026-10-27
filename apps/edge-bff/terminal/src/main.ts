/* EDGE financial terminal (EXEC-TERMINAL-API T5): the reference page 03-terminal-right-panel.html as modular
   TypeScript. The sections start in the reference's own order, so listeners and first draws happen in the same
   sequence. /terminal-app/?fixture=reference runs on the reference's synthetic data for the 1:1 check; otherwise the
   page reads the published files of the rack through EDGE. */
import './styles/terminal.css';
import * as L from 'lightweight-charts';
import IND_REG from './data/indRegistry.json';
import { fixtureData } from './data/fixture';
import { liveData, TerminalError } from './data/live';
import type { MarketData, Point } from './data/types';
import type { Ctx } from './app/context';
import { $, brokerEnd, setLogos, spin, store } from './app/context';
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

function start(M: MarketData, rawSeries: Record<string, Point[]>) {
  const container = $('chart');
  if (!container) return null;
  const ohlc = M.ohlc;
  const ctx = {
    M, L, SYMBOL:M.symbol, INSTRUMENTS:M.instruments, container,
    dates:ohlc.map(b => b.time), ohlc, volume:M.volume, lineData:M.lineData,
    closes:ohlc.map(b => b.close), N:ohlc.length, idxByTime:new Map(ohlc.map((b, i) => [b.time, i])),
    active:new Map(), catalog:M.catalog, rawSeries, IND_REG
  } as unknown as Ctx;
  ctx.brokerEnd = brokerEnd(ctx.dates, M.through?.broker);

  setLogos(M.logos);                                       // live only: the fixture has no logos (1:1 check)
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
  initSearch(ctx);
  initSelect();
  initBroker(ctx);
  initRangeSelect(ctx);
  if (M.mode === 'live') initReorder();                    // EXEC-TERMINAL-PANELS A1; the fixture keeps the reference order
  if (M.mode === 'live') initFullscreen();                 // EXEC-TERMINAL-FULL; the fixture's top bar stays the reference's
  if (M.mode === 'live') document.querySelector('#symbolPill .exchange')?.remove();   // EXEC-TERMINAL-FULL-2: no "IDX" label
  return ctx;
}

/* live (EXEC-TERMINAL-UI-1026 U5): the chart is drawn; the broker files follow into the Flow Timeline, and into Broker
   activity when that panel is open */
function later(ctx: Ctx, M: MarketData) {
  if (!M.later) return;
  const failed = () => { const note = $('flowNote'); note.textContent = 'Broker data could not be loaded. Reload the page to try again.'; note.hidden = false };
  /* F5: the recent years first (Flow and Broker activity), then the whole history replaces them in the Flow Timeline */
  M.later.broker.then(b => {
    ctx.setFlowData(b.combos, b.flowFrom, true, b.flowTo); ctx.setBrokerPanelData(b.broker); mark('flow: last two years');
    M.later!.brokerAll.then(all => {
      ctx.setFlowData(all.combos, all.flowFrom, false, all.flowTo); mark('flow: every year');
      if (all.broker.dates.length > b.broker.dates.length) ctx.setBrokerPanelData(all.broker);   // B1: the full two years
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
  liveData(stored).then(M => { loading.remove(); const ctx = start(M, {}); mark('chart drawn'); if (ctx) later(ctx, M) }, e => { loading.remove();
    fail(e instanceof TerminalError ? e.message : 'The terminal could not load its data. Reload the page to try again.') });
}

boot();
