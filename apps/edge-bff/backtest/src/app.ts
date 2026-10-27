/* The page's start (backtest.html's top-level statements, in their order): the palette, the builder width and the
   panel as the user left them, the catalog (with the API's note on its data in the header) and the bars of the shown
   ticker from the injected BacktestApi, then the reference's listeners and its first render. The reference ends with
   run(false); this page does not run at load (CONTRACT.md D-no-autorun) and opens in its own "Not run yet" state,
   unless a test build asks for the reference's start (the fixture's 1:1 check). */
import type { BacktestApi } from './api/types.ts';
import type { Catalog } from './core/contract.ts';
import { CAT, PROVISIONAL, STOCKS, load, setEnv, setWaiting } from './env.ts';
import { $, initColors, setPal, toastError } from './format.ts';
import { needsFlow } from './reg.ts';
import { applyCatalog, edits, S } from './state.ts';
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

/* EXEC-BACKTEST-LOAD (user 2026-10-27: "menu-menu itu yang di sebelah kiri dan di tengah ... bisa ready langsung ketika
   user buka ... Tidak perlu semuanya di loading all at once"; "Agar waktu loading bisa sama. Seperti bagian terminal."):
   the catalog and the shown ticker's prices are asked at once and the page does not wait for them. What answers within
   QUICK_MS is used for the first render (a cached catalog, the test fixture: the same start as before); otherwise the
   builder and the chart draw on PROVISIONAL (env.ts) and the parts that need the catalog say they are loading, then the
   page draws again when it answers (catalogArrived). The chart draws the candles as soon as the prices are there; the
   broker data of a flow card follows (signals.ts prepare). */
const QUICK_MS = 60;
const within = <T>(p: Promise<T>, ms: number): Promise<T | undefined> => Promise.race([p, new Promise<undefined>(ok => setTimeout(ok, ms))]);

export async function boot(api: BacktestApi, opts: BootOptions = {}) {
  setPal(); initColors();
  initResize(); restorePanel();
  document.documentElement.style.setProperty('--vb', (document.querySelector('.viewbar') as HTMLElement).offsetHeight+'px');
  const runButtons = () => document.querySelectorAll('.js-run') as NodeListOf<HTMLButtonElement>;
  const failed = (e: unknown) => {
    const msg = (e as Error)?.message || 'The backtest service could not be reached.';
    toastError(msg); $('runNote').textContent = msg; runButtons().forEach(b => b.disabled = true);
  };
  const asked = api.catalog();
  setWaiting(asked); asked.catch(() => {});                // its failure is shown below, once
  setEnv(api, PROVISIONAL);
  let early: Catalog | undefined;
  try { early = await within(asked, QUICK_MS) } catch (e) { failed(e); return }
  if (early) { setEnv(api, early); $('dataNote').textContent = api.texts.dataNote(CAT); applyCatalog(opts.portfolio) }
  // the shown ticker's prices (and its broker data when a flow card needs it) start now; the first render waits for
  // them only QUICK_MS, so the page is drawn at once and the chart fills in (signals.ts prepare)
  const tk = S.sigTicker, bars = load(tk, false, needsFlow()).then(() => needsFlow() ? load(tk, true) : undefined);
  bars.catch(() => {});                                    // a failed load is shown by the chart's own prepare
  await within(bars.catch(() => {}), QUICK_MS);
  bindLayout(); bindFocusEscape(); bindViewSeg(); bindMenuClose(); bindSignals(); bindTicker(); bindRun(); bindHover(); bindTheme(); bindWS();
  runButtons().forEach(b => b.disabled = false);
  renderBuilder(); initPriceChart(); refreshSignals(); renderResults();
  if (!early) asked.then(cat => catalogArrived(api, cat), failed);
  if (opts.autorun) run(false);
}

/* the catalog answered after the first render: the data's own defaults are taken when the user has not changed a
   setting yet (else only the ticker when it is not published, and the period's ends inside the published days), and
   the builder and the chart draw again. A builder field in use is left alone until it loses the focus. */
function catalogArrived(api: BacktestApi, cat: Catalog) {
  const untouched = edits.n === 0, ticker = S.ticker;
  setEnv(api, cat);
  $('dataNote').textContent = api.texts.dataNote(CAT);
  if (untouched) applyCatalog();
  else {
    const stocks = STOCKS();
    if (!stocks.includes(ticker)) { S.ticker = stocks.includes('MAPI') ? 'MAPI' : stocks[0]; if (S.mode === 'single') S.sigTicker = S.ticker }
    if (S.from < CAT.first_date) S.from = CAT.first_date;
    if (S.to > CAT.data_through) S.to = CAT.data_through;
    S.tickers = S.tickers.filter(t => stocks.includes(t)).slice(0, CAT.limits.max_portfolio_tickers);
  }
  const redraw = () => { renderBuilder(); refreshSignals() };
  const b = $('builder') as HTMLElement | null, inUse = b && b.contains(document.activeElement);
  if (inUse) b.addEventListener('focusout', function later(e: FocusEvent) {
    if (b.contains(e.relatedTarget as Node)) return;
    b.removeEventListener('focusout', later); redraw();
  }); else redraw();
}
