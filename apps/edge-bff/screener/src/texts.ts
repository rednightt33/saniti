/* The Screener page's own words (report FRONTEND INTEGRATION 9.1: words inside the app stay in the app, as the
   Backtest's api/texts.ts; the shell's words live in static/edge-labels.js). Plain text: the page escapes every string
   it puts into markup (format.ts esc). The API sends codes, never messages for the page to show verbatim where the
   page has its own wording (report 9.2: remarks are worded here from the API's codes). */
import type { CellRemark, NaReason, RowRemark } from './core/contract.ts';
import { nf } from './format.ts';

export const T = {
  signIn: 'Sign in to EDGE first, then open the Screener tab again.',
  forbidden: 'EDGE refused this request (the session or its token is no longer valid). Reload the page.',
  unreachable: 'The screener service cannot be reached; retry shortly.',
  // waiting states (report 6c.6); every ring is the shared one (terminal/src/ui/spin.ts)
  loadingIndicators: 'Loading indicators',
  loadingPresets: 'Loading presets',
  loadingResults: 'Loading results',
  loadingData: 'Loading data status',
  running: 'Running screen',
  updating: 'Updating…',
  outOfDate: 'Out of date',
  retry: 'Retry',
  // fixed reasons for what has no data (report 9.2 D rows; P11 a: shown disabled with the reason, not removed)
  noIndex: 'No data: index membership (LQ45, IDX30, IDX80, ISSI) is not in the market database.',
  noBoard: 'No data: the listing board (Main, Development) is not in the market database; market_board is the trading board.',
  noCap: 'No data: market cap waits for EXEC-MCAP (shares outstanding), which has no go yet.',
  noFreeFloat: 'No data: free float is not in the market database.',
  noNotation: 'No data: special notation / FCA flags are not in the market database, so this filter is off (P11).',
  noFundamentals: 'No data: fundamentals wait for a data source and its own decision (P11).',
  sendPhase: 'Send to Backtest comes with Phase 1b (its rules, P13, are confirmed first).',
  // P17 consequence (catalog default_offered false: I43 VWAP, whose registry default anchor Session is not offered)
  noDefault: 'The screener does not offer this indicator\'s registry default, so the card opens at the starting parameters shown; change them here.',
  noWatchlistPage: 'Saved in your EDGE watchlist.',
} as const;

/** Why a cell is n/a (contract NaReason), as its tooltip says it. */
export const NA_TEXT: Record<NaReason, string> = {
  INSUFFICIENT_HISTORY: 'n/a: not enough history for this indicator up to the evaluation date',
  NULL_AT_EVALUATION: 'n/a: no value on the evaluation date (flat window, zero band width or zero volume)',
  FLOW_UNAVAILABLE: 'n/a: flow data is not available for this stock',
  FLOW_LAGGED: 'n/a: flow data is older than the price data',
  NOT_APPLICABLE: 'n/a: this metric does not apply to this stock',
  DATA_INTEGRITY: 'n/a: the data failed its integrity check in this publication',
  MIXED_ADJUSTMENT_BASIS: 'n/a: the window crosses an unadjusted corporate action',
};
export const naText = (r: string | null | undefined) => r ? (NA_TEXT as Record<string, string>)[r] || `n/a (${r})` : 'n/a';

const ACTION: Record<string, string> = { STOCK_SPLIT:'stock split', REVERSE_SPLIT:'reverse split', RIGHTS_ISSUE:'rights issue',
  BONUS_SHARES:'bonus shares', STOCK_DIVIDEND:'stock dividend', WARRANT:'warrant' };
export const actionText = (a: string) => ACTION[a] || a.toLowerCase().replace(/_/g, ' ');

/** A row remark (P4), as the Remark column and the preview say it (report 9.2 wording). */
export function remarkText(r: RowRemark): string {
  if (r.code === 'STALE') return `Stale: last trade ${r.last_bar_date}`;
  const ratio = r.ratio_old != null && r.ratio_new != null ? ` (${nf(r.ratio_old, 0)}:${nf(r.ratio_new, 0)})` : '';
  return `Price break: ${actionText(r.action)}${ratio} ex ${r.ex_date}, history not adjusted`;
}
/** The short badge of a remark and its full reason (title). */
export const remarkBadge = (r: RowRemark) => r.code === 'STALE' ? 'Stale' : 'Price break';
export function remarkTitle(r: RowRemark): string {
  if (r.code === 'STALE') return `${remarkText(r)}. The stock is evaluated at its own last bar; its values are shown.`;
  const cr = r.close_ratio != null ? ` Close on the ex-date ÷ the close before: ${nf(r.close_ratio, 3)}.` : '';
  return `${remarkText(r)}. Values whose look-back crosses the ex-date are shown and marked (P4.1 A).${cr} TEMPORARY until the data layer adjusts history (D22).`;
}
/** The CSV's remark cell (report 9.6): the code and its date. */
export const remarkCsv = (rs: RowRemark[]) => rs.map(r => r.code === 'STALE' ? `STALE ${r.last_bar_date}` : `PRICE_BREAK ${r.action} ${r.ex_date}`).join('; ');

/** A cell remark (P4.1 A): the mark's tooltip, naming the ex-date(s) of the row. */
export function cellRemarkText(c: CellRemark, rowRemarks: RowRemark[]): string {
  const ex = rowRemarks.filter(r => r.code === 'PRICE_BREAK').map(r => (r as Extract<RowRemark, { code: 'PRICE_BREAK' }>).ex_date);
  return c === 'PRICE_BREAK_IN_LOOKBACK'
    ? `Distorted: this value's look-back contains the unadjusted ex-date${ex.length ? ' ' + ex.join(', ') : ''}. Shown as computed (P4.1 A).`
    : c;
}

/** The universe chips (P4): label while on, and what the drawer's checkbox says. */
export const chipTraded = (e: string | null) => `Traded on ${e || 'the evaluation date'}`;
export const chipNoBreak = 'No unadjusted price break';

/** The page's wording of a refusal or failure (report 8.8, last column), from its code; `server` is the server's
    message, used where the page has no wording of its own. Every refusal says where the problem is and how to fix it
    (AGENTS.md "Gates and evidence" (d)). */
export function errorText(code: string, ctx: { field?: string; details?: Record<string, unknown> | null; retryAfter?: number | null; server?: string } = {}): string {
  const d = ctx.details || {}, at = ctx.field ? ` (${ctx.field})` : '';
  switch (code) {
    case 'INVALID_INPUT': return `The request was refused${at}: ${ctx.server || 'a field is malformed'}.`;
    case 'INVALID_CONDITION': return `${ctx.server || 'A condition is not valid'}${at}${Array.isArray((d as any).allowed) ? `. Allowed: ${(d as any).allowed.join(', ')}` : ''}.`;
    case 'UNKNOWN_INDICATOR': return `Unknown indicator${at}. Pick one from the catalog.`;
    case 'PARAM_OUT_OF_RANGE': {
      const r = d as { min?: number; max?: number };
      return `A parameter is out of range${at}${r.min != null || r.max != null ? `: allowed ${r.min ?? '…'} to ${r.max ?? '…'}` : ''}. Change it and run again.`;
    }
    case 'METRIC_UNAVAILABLE': return `${(d as any).metric || 'This metric'} is not available: ${(d as any).reason || ctx.server || 'no data'}.`;
    case 'LIMIT_EXCEEDED': {
      const l = d as { limit?: string; allowed?: number; needed?: number; costliest?: string };
      if (l.limit === 'compute_budget') return `The screen is too costly to run${l.costliest ? `; the costliest condition is ${l.costliest}` : ''}. Use fewer custom conditions or shorter lengths.`;
      return `Limit reached${l.limit ? ` (${l.limit})` : ''}${l.allowed != null ? `: at most ${l.allowed}` : ''}${l.needed != null ? `, this needs ${l.needed}` : ''}.`;
    }
    case 'DATA_UNAVAILABLE': return 'No published data is loaded yet; it loads after the next publication or within minutes of a restart; try again later.';
    case 'DATA_INTEGRITY': return 'The latest publication failed its checks and no earlier one is loaded; it retries at the next publication.';
    case 'BUSY': return 'The screener is busy; retrying.';
    case 'SCREEN_REPLACED': case 'PREVIEW_REPLACED': return 'A newer request replaced this one.';
    case 'DATA_VERSION_CHANGED': return 'New data was published; the screen is re-run.';
    case 'REVISION_CONFLICT': return 'This screen was changed elsewhere since you opened it. Reload it, or save as a copy.';
    case 'NAME_TAKEN': return 'A saved item with this name exists. Pick another name.';
    case 'NOT_FOUND': return 'This saved item no longer exists; reload the list.';
    case 'REQUEST_TOO_LARGE': return 'The definition is too large: remove conditions or filters.';
    case 'SCREENER_DISABLED': return 'The screener is switched off on this environment.';
    case 'SCREENER_NOT_READY': return `The screener is starting; it retries in ${ctx.retryAfter ?? 5} s.`;
    case 'SCREENER_UNAVAILABLE': return T.unreachable;
    case 'TIMEOUT': return `The screen took longer than the limit: fewer custom conditions or shorter lengths${(d as any).costliest ? ` (costliest: ${(d as any).costliest})` : ''}.`;
    default: return ctx.server || '';
  }
}

/** The page head's data line (report 9.2): listings, evaluation date and publication. */
export const dataLine = (listed: number, evalDate: string, published: string) =>
  `IDX equities (${nf(listed)} listings) · close ${evalDate} · published ${published.replace('T', ' ').replace(/:\d\d(\.\d+)?Z$/, ' UTC').replace(/Z$/, ' UTC')}`;

/** "How conditions work", rewritten to the real semantics (report 9.2 Method & sources). */
export const methodText = (evalDate: string) =>
  `VALUE tests read each stock's value on the evaluation date (${evalDate}). STATE tests compare two values on that date. ` +
  `EVENT tests (crosses, breakouts, divergences, flips) pass when the event happened within the chosen number of sessions, ` +
  `counted on the stock's own bars. A stock without a trade on ${evalDate} is stale: it is hidden by default, and when shown ` +
  `it is evaluated at its own last bar with a remark. Near misses are one condition short of the match.`;
