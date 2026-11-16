/* EXEC-BACKTEST-REVAMP Tahap D, decision 2a (user 2026-11-15 "1 setuju, 2a"): the left header over the price chart (the
   design's #xsHd: the ticker, the title, the period, the out-of-sample share, the last run and its run time), built from
   the page's state here; the data source note (decision 2a) is in the view bar (#dataNote, index.html). The design filled it by copying the text of a hidden header row
   (xsHdR); that row is gone. Its elements keep the old row's ids (ctxTicker, ctxTitle, ctxPeriod, lastRun, staleTag) so
   the page's tests read the same facts. The Add indicator and Run buttons are markup (index.html). */
import { $, cls, esc, fmtD, num, pct } from './format.ts';
import { S } from './state.ts';
import { openCondWin } from './condwin.ts';

/** the data source note in the view bar (api.texts.dataNote of the catalog; set by app.ts when the catalog answers) */
export const setDataNote = (t: string) => {
  const el = $('dataNote') as HTMLElement | null;
  if (el) { el.textContent = t; el.title = t; el.hidden = !t }
};

const ICON = {
  period: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
  oos: '<path d="M12 3v18M4 12h4M16 12h4"/>',
  run: '<path d="M4 17l6-6 4 4 6-8"/>',
  time: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
};
const row = (icon: string, label: string, body: string) =>
  `<div class="xh-r"><svg viewBox="0 0 24 24" aria-hidden="true">${icon}</svg><div><b>${label}</b>${body}</div></div>`;

/** the header from the state (the title of a portfolio is set by builder.ts portfolioTitle after this) */
export function renderHeader() {
  const box = $('xsHdB');
  if (!box) return;
  const R = S.result, stale = !!(S.stale && R);
  const run = S.running ? '<span class="xh-mu">Running backtest…</span>'
    // the design's wording: net return · Sharpe · max drawdown · trades, without the labels "Net" and "DD" (Agent 10, M460 item 5)
    : R ? `<span class="xh-k"><b class="${cls(R.st.tot)}">${pct(R.st.tot)}</b> · Sharpe <b>${num(R.st.sharpe)}</b> · <b class="down">${pct(R.st.mdd)}</b> · <b>${R.trades.length}</b> trades</span>`
    : '<span class="xh-mu">Not run yet · press Run backtest</span>';
  box.innerHTML = `<div class="xh-id"><span class="xh-tk" id="ctxTicker">${esc(S.mode === 'single' ? S.ticker : 'PORTFOLIO')}</span><b id="ctxTitle">${S.mode === 'single' ? 'Single-stock backtest' : ''}</b></div>`
    + row(ICON.period, 'Period', `<span id="ctxPeriod">${esc(fmtD(S.from))} – ${esc(fmtD(S.to))}</span>`)
    + row(ICON.oos, 'Out-of-sample', S.oos ? `Last ${S.oos}% of the period` : 'Off')
    + row(ICON.run, 'Last run', `<div id="lastRun" class="${stale ? 'is-stale' : ''}"><span class="xh-st" id="staleTag" ${stale ? '' : 'hidden'} title="Settings changed — run again to update results">Out of date</span>${run}</div>`)
    + row(ICON.time, 'Run time', R && !S.running ? `${R.ms} ms · ${S.trials} variant${S.trials === 1 ? '' : 's'}` : '—');
}

/** the header's Add indicator button: the conditions workspace on the entry side (the design's xsAddInd) */
export const bindHeader = () => { $('xsAdd').onclick = () => openCondWin(null, 'entry') };
