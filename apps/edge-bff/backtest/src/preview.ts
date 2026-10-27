/* The portfolio table's entry signals before a run (CONTRACT.md section 10, D-P8): the server's preview of the current
   settings, the latest wins. signals.ts asks rows() on every redraw; this module keeps what was answered, the preview
   in flight and the one another tab replaced. Pure: no DOM (the toast and the redraw are the caller's callbacks).
   - A preview in flight whose settings are no longer the current ones is aborted at the next rows(), before a cached
     answer or the run's own rows are returned (review PAGE-V4), so edge-bff closes its worker call.
   - A preview edge-bff ended because a newer one of the same owner arrived (409 PREVIEW_REPLACED: another tab of the
     owner) is no error to show: the table keeps what it drew (the loading dashes for settings never answered), and
     the preview is asked again only after the next user action on this page, never by itself (two tabs would keep
     replacing each other; review PAGE-V3).
   - An answer's warnings are one short line in the reference's toast (review PAGE-V1): the stocks left out
     (TICKERS_EXCLUDED) as their count; each one's error stays in its row's tooltip.
   - A preview that leaves every picked stock out (422 UNIVERSE_EMPTY, core/signals.ts leftOut) is the answer of its
     settings, the same short line and every row "—" with that error in its tooltip; any other failure is its message
     in the toast, and the same settings are not asked again until they change (review PG-2: a redraw, such as a zoom
     button or a legend chip, never asks or toasts again). */
import type { SignalsPreview, SignalsPreviewRequest, Warning } from './core/contract.ts';
import { byTicker } from './core/signals.ts';
import { isAbort } from './api/types.ts';
import { stocksText } from './picked.ts';

/** a table row: entry signals and the last one, or why the stock was left out (n null) */
export interface PortRow { n: number | null; last: string | null; left?: { code: string; message: string } }
export type Rows = (ticker: string) => PortRow;
/** the loading dashes (also every row while nothing is picked) */
export const DASHES: Rows = () => ({ n:null, last:null });

/** rows of a preview or a run (per_ticker), with the left-out stocks of its TICKERS_EXCLUDED warnings */
export const portRows = (rows: SignalsPreview['rows'], warnings: readonly Warning[]): Rows => {
  const got = new Map(rows.map(r => [r.ticker, { n:r.entry_signals, last:r.last_signal }]));
  const left = new Map(warnings.filter(w => w.code === 'TICKERS_EXCLUDED').flatMap(w => w.reasons || []).map(r => [r.ticker, r]));
  return (t: string): PortRow => got.get(t) ?? (left.has(t) ? { n:null, last:null, left:left.get(t) } : { n:0, last:null });
};

/** The toast of a preview's warnings, one short line: "3 stocks left out (see the — rows)" for TICKERS_EXCLUDED, any
    other warning by its message (the core's plain sentence); '' when there is none. */
export function previewNote(warnings: readonly Warning[]): string {
  const left = new Set(warnings.filter(w => w.code === 'TICKERS_EXCLUDED').flatMap(w => [...(w.tickers || []), ...(w.reasons || []).map(r => r.ticker)]));
  return [...(left.size ? [leftNote(left.size)] : []), ...warnings.filter(w => w.code !== 'TICKERS_EXCLUDED').map(w => w.message)].join(' ');
}
const leftNote = (n: number) => `${stocksText(n)} left out (see the — row${n === 1 ? '' : 's'})`;

/** the preview's identity: the request with its stocks in ticker order (the order they were picked in does not
    matter, PF3: the worker sorts them the same way) */
export const previewKey = (q: SignalsPreviewRequest) => JSON.stringify({ ...q, tickers:[...q.tickers].sort(byTicker) });

export interface PreviewHooks {
  ask(q: SignalsPreviewRequest, opts: { signal: AbortSignal }): Promise<SignalsPreview>;
  /** the key of the settings the page shows now (null: nothing to preview, e.g. not in portfolio mode) */
  current(): string | null;
  /** an answer for the current settings arrived: redraw; note = its toast ('' for none) */
  answered(note: string): void;
  /** a preview failed (not aborted, not replaced, not UNIVERSE_EMPTY): its message for the toast */
  failed(message: string): void;
}

export class Previews {
  private answers = new Map<string, Rows>();
  private pending: { key: string; ctl: AbortController } | null = null;
  private held: string | null = null;         // the settings whose preview another tab replaced, until a user action
  private refused: string | null = null;      // the settings whose preview failed, until the settings change
  private shown = '';                         // the last note shown, so an answer toasts only a new one
  constructor(private hooks: PreviewHooks) {}

  /** The rows for request `q` (null: nothing picked, the dashes), unless `run` (the fresh run's own rows) is given. */
  rows(q: SignalsPreviewRequest | null, run: Rows | null = null): Rows {
    const key = q ? previewKey(q) : null;
    if (this.pending && this.pending.key !== key) this.drop();
    if (this.refused !== key) this.refused = null;
    if (run) return run;
    if (!q || !key) return DASHES;
    const got = this.answers.get(key);
    if (got) return got;
    if (this.held === key || this.refused === key || this.pending) return DASHES;
    const mine = this.pending = { key, ctl:new AbortController() };
    this.hooks.ask(q, { signal:mine.ctl.signal }).then(p => {
      if (mine.ctl.signal.aborted) return;          // an API that answers anyway is not drawn either
      this.answered(key, portRows(p.rows, p.warnings), previewNote(p.warnings));
    }, e => {
      if (isAbort(e) || mine.ctl.signal.aborted) return;
      const code = (e as { code?: string })?.code;
      if (code === 'PREVIEW_REPLACED') { this.held = key; return }
      if (code === 'UNIVERSE_EMPTY') {
        const left = { code, message:(e as Error).message };
        this.answered(key, () => ({ n:null, last:null, left }), leftNote(new Set(q.tickers).size));
        return;
      }
      this.refused = key;
      this.hooks.failed((e as Error).message);
    }).finally(() => { if (this.pending === mine) this.pending = null });
    return DASHES;
  }
  /* the rows of settings answered; drawn, with the note when it is new, while they are the current settings */
  private answered(key: string, rows: Rows, note: string) {
    this.answers.set(key, rows);
    if (this.hooks.current() !== key) return;
    const fresh = note && note !== this.shown;
    this.shown = note;
    this.hooks.answered(fresh ? note : '');
  }
  /** abort the preview in flight (the page left portfolio mode, or its settings changed) */
  drop() { this.pending?.ctl.abort(); this.pending = null }
  /** the user acted on this page: a preview another tab replaced may be asked again at the next redraw */
  userAction() { this.held = null }
  /** whether a preview is in flight (tests) */
  get inFlight() { return this.pending?.key ?? null }
}
