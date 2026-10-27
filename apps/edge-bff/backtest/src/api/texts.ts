/* The production page's words on its data (SourceTexts, lead decision 2026-10-27), in place of the reference's words on
   its synthetic market: the header names the published data's last day (catalog.data_through, the page's date
   format), the Robustness warning box names what the run reports about itself (every meta.warnings message), and the
   trial count is the server's per owner and strategy line (CONTRACT.md K3), not per page session. */
import type { BacktestResultCore, Warning } from '../core/contract.ts';
import type { SourceTexts } from './types.ts';
import { fmtD } from '../format.ts';

/** a warning as the page shows it: its message, then the tickers it names (with each left-out ticker's error code
    where the warning gives the reasons, TICKERS_EXCLUDED) */
export const warningText = (w: Warning) => {
  const code = new Map((w.reasons || []).map(r => [r.ticker, r.code]));
  const tickers = (w.tickers || []).map(t => code.has(t) ? `${t} (${code.get(t)})` : t);
  return w.message + (tickers.length ? ` Tickers: ${tickers.join(', ')}.` : '');
};

export const PUBLISHED_TEXTS: SourceTexts = {
  dataNote: catalog => `Published data to ${fmtD(catalog.data_through)} · long-only`,
  robustnessWarning: (result: BacktestResultCore) => ['⚠︎ Single market path: history happened once.', ...result.meta.warnings.map(warningText),
    'Before trusting a result: keep the out-of-sample untouched while tuning, and re-check the liquidity of every fill.'].join(' '),
  trials: 'for this strategy',
};
