/* The production page's words on its data (SourceTexts, lead decision 2026-10-27), in place of the reference's words on
   its synthetic market: the header says the data is the published data, the Robustness warning box names what the run
   reports about itself (every meta.warnings message), and the trial count is the server's per owner and strategy line
   (CONTRACT.md K3), not per page session.
   The header has no date: "Published data to <catalog.data_through> · long-only" wraps where the reference's
   "Synthetic demo data · long-only" does not (Chromium, the reference's CSS, "23 October 2026": 7 lines at 390 px
   against the reference's 5, 5 against 3 at 480, 3 against 2 at 560, 2 against 1 at 640 and 720), so the header takes
   the lead's shorter form, which never wraps more than the reference (4, 3, 2, then 1 line from 640 px). */
import type { BacktestResultCore, Warning } from '../core/contract.ts';
import type { SourceTexts } from './types.ts';

/** a warning as the page shows it: its message, then the tickers it names (with each left-out ticker's error code
    where the warning gives the reasons, TICKERS_EXCLUDED) */
export const warningText = (w: Warning) => {
  const code = new Map((w.reasons || []).map(r => [r.ticker, r.code]));
  const tickers = (w.tickers || []).map(t => code.has(t) ? `${t} (${code.get(t)})` : t);
  return w.message + (tickers.length ? ` Tickers: ${tickers.join(', ')}.` : '');
};

export const PUBLISHED_TEXTS: SourceTexts = {
  dataNote: () => 'Published data · long-only',
  robustnessWarning: (result: BacktestResultCore) => ['⚠︎ Single market path: history happened once.', ...result.meta.warnings.map(warningText),
    'Before trusting a result: keep the out-of-sample untouched while tuning, and re-check liquidity of every fill.'].join(' '),
  trials: 'for this strategy',
};
