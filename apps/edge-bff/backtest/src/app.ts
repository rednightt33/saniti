/* The page's start (backtest.html's top-level statements, in their order): the palette, the builder width and the
   panel as the user left them, the catalog (with the API's note on its data in the header) and the bars of the shown
   ticker from the injected BacktestApi, then the reference's listeners and its first render. The reference ends with
   run(false); this page does not run at load (CONTRACT.md D-no-autorun) and opens in its own "Not run yet" state,
   unless a test build asks for the reference's start (the fixture's 1:1 check). */
import type { BacktestApi } from './api/types.ts';
import { CAT, load, setEnv } from './env.ts';
import { $, initColors, setPal, toast } from './format.ts';
import { needsFlow } from './reg.ts';
import { applyCatalog, S } from './state.ts';
import { bindFocusEscape, bindLayout, bindTheme, initResize, restorePanel } from './layout.ts';
import { bindMenuClose, bindViewSeg, renderBuilder } from './builder.ts';
import { bindSignals, bindTicker, initPriceChart, refreshSignals } from './signals.ts';
import { bindHover } from './results/svg.ts';
import { renderResults } from './results/index.ts';
import { bindWS } from './workspace.ts';
import { bindRun, run } from './run.ts';

export interface BootOptions {
  /** run once after the first render, as the reference does (test builds only) */
  autorun?: boolean;
  /** the portfolio's picked stocks at load (test builds only: the fixture's reference portfolio); none otherwise */
  portfolio?: string[];
}

export async function boot(api: BacktestApi, opts: BootOptions = {}) {
  setPal(); initColors();
  initResize(); restorePanel();
  document.documentElement.style.setProperty('--vb', (document.querySelector('.viewbar') as HTMLElement).offsetHeight+'px');
  const runButtons = () => document.querySelectorAll('.js-run') as NodeListOf<HTMLButtonElement>;
  runButtons().forEach(b => b.disabled = true);
  try {
    setEnv(api, await api.catalog());
    $('dataNote').textContent = api.texts.dataNote(CAT);
    applyCatalog(opts.portfolio);
    await load(S.sigTicker, needsFlow());
  } catch (e) {
    const msg = (e as Error).message || 'The backtest service could not be reached.';
    toast(msg); $('runNote').textContent = msg;
    return;
  }
  bindLayout(); bindFocusEscape(); bindViewSeg(); bindMenuClose(); bindSignals(); bindTicker(); bindRun(); bindHover(); bindTheme(); bindWS();
  runButtons().forEach(b => b.disabled = false);
  renderBuilder(); initPriceChart(); refreshSignals(); renderResults();
  if (opts.autorun) run(false);
}
