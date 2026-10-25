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
import { $, store } from './app/context';
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

function start(M: MarketData, rawSeries: Record<string, Point[]>) {
  const container = $('chart');
  if (!container) return;
  const ohlc = M.ohlc;
  const ctx = {
    M, L, SYMBOL:M.symbol, INSTRUMENTS:M.instruments, container,
    dates:ohlc.map(b => b.time), ohlc, volume:M.volume, lineData:M.lineData,
    closes:ohlc.map(b => b.close), N:ohlc.length, idxByTime:new Map(ohlc.map((b, i) => [b.time, i])),
    active:new Map(), catalog:M.catalog, rawSeries, IND_REG
  } as unknown as Ctx;

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
}

/* a load failure is shown on the chart, in the reference's own panel style */
function fail(message: string) {
  const host = $('chart');
  const box = document.createElement('div');
  box.className = 'st-tip';
  box.setAttribute('role', 'alert');
  box.style.cssText = 'position:absolute;left:50%;top:40%;transform:translate(-50%,-50%);max-width:420px;pointer-events:auto';
  box.textContent = message;
  (host?.parentElement || document.body).appendChild(box);
}

function boot() {
  const stored = store.get('ml.symbol');
  if (new URLSearchParams(location.search).get('fixture') === 'reference') {
    /* synchronous, like the reference: it builds every compare series up front, so adding one is immediate */
    const M = fixtureData(stored);
    start(M, M.rawSeries);
    return;
  }
  liveData(stored).then(M => start(M, {}), e =>
    fail(e instanceof TerminalError ? e.message : 'The terminal could not load its data. Reload the page to try again.'));
}

boot();
