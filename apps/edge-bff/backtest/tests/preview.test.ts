/* The portfolio table's preview (preview.ts, CONTRACT.md section 10, D-P8): the preview in flight is aborted as soon as
   the settings change, before a cached answer or the run's rows are returned (review PAGE-V4); a preview another tab
   replaced (409 PREVIEW_REPLACED) shows nothing and is asked again only after a user action (review PAGE-V3); the
   toast of an answer's warnings is one short line (review PAGE-V1); a failed preview is not asked again by a redraw,
   and one that leaves every picked stock out (UNIVERSE_EMPTY) is that short line with its rows (review PG-2). */
import { describe, expect, it, vi } from 'vitest';
import type { SignalsPreview, SignalsPreviewRequest, Warning } from '../src/core/contract.ts';
import { ApiFailure } from '../src/api/types.ts';
import { DASHES, previewKey, previewNote, Previews, type Rows } from '../src/preview.ts';

const req = (...tickers: string[]): SignalsPreviewRequest =>
  ({ schema_version:1, tickers, period:{ from:'2019-06-03', to:'2022-12-30' }, entry:{} as SignalsPreviewRequest['entry'] });
const answer = (q: SignalsPreviewRequest, warnings: Warning[] = []): SignalsPreview =>
  ({ data_version:'v', rows:q.tickers.map(t => ({ ticker:t, entry_signals:2, last_signal:'2022-12-01' })), warnings });
const left = (...tickers: string[]): Warning => ({ code:'TICKERS_EXCLUDED', message:`${tickers.length} ticker(s) of the universe were left out.`,
  count:tickers.length, tickers, reasons:tickers.map(t => ({ ticker:t, code:'INDICATOR_OUTPUT_EMPTY', message:`${t} has no value of the entry conditions.` })) });

/* a server whose answers the test gives: each ask waits until answered or rejected */
function server() {
  const asks: { q: SignalsPreviewRequest; signal: AbortSignal; ok: (p: SignalsPreview) => void; no: (e: unknown) => void }[] = [];
  const ask = vi.fn((q: SignalsPreviewRequest, { signal }: { signal: AbortSignal }) =>
    new Promise<SignalsPreview>((ok, no) => asks.push({ q, signal, ok, no })));
  return { asks, ask };
}
function previews(current: () => SignalsPreviewRequest | null) {
  const s = server(), answered = vi.fn(), failed = vi.fn();
  const p = new Previews({ ask:s.ask, current:() => { const q = current(); return q ? previewKey(q) : null }, answered, failed });
  return { ...s, p, answered, failed };
}
const tick = () => new Promise(r => setTimeout(r, 0));

describe('the preview in flight (review PAGE-V4)', () => {
  it('is aborted when the settings change, before a cached answer is returned', async () => {
    let cur = req('BBCA');
    const t = previews(() => cur);
    t.p.rows(cur);                                            // asks for BBCA
    t.asks[0].ok(answer(req('BBCA'))); await tick();          // cached
    cur = req('BBCA', 'BBRI'); t.p.rows(cur);                 // asks for BBCA+BBRI
    expect(t.asks).toHaveLength(2);
    cur = req('BBCA');
    const rows = t.p.rows(cur);                               // back to the cached settings
    expect(t.asks[1].signal.aborted).toBe(true);
    expect(rows('BBCA')).toEqual({ n:2, last:'2022-12-01' });
    expect(t.p.inFlight).toBe(null);
  });
  it('is aborted when the run\'s own rows are shown', () => {
    const t = previews(() => req('BBCA'));
    t.p.rows(req('BBCA'));
    const run: Rows = () => ({ n:7, last:null });
    expect(t.p.rows(req('BBCA', 'BBRI'), run)).toBe(run);
    expect(t.asks[0].signal.aborted).toBe(true);
  });
  it('is kept while the settings are the same (the run\'s rows are shown meanwhile)', () => {
    const t = previews(() => req('BBCA'));
    t.p.rows(req('BBCA'));
    const run: Rows = () => ({ n:7, last:null });
    expect(t.p.rows(req('BBCA'), run)).toBe(run);
    expect(t.p.rows(req('BBCA'))).toBe(DASHES);
    expect(t.asks).toHaveLength(1);
    expect(t.asks[0].signal.aborted).toBe(false);
  });
  it('is aborted when nothing is left to preview; the order of the picked stocks is no new setting (PF3)', () => {
    const t = previews(() => null);
    t.p.rows(req('BBRI', 'BBCA'));
    t.p.rows(req('BBCA', 'BBRI'));
    expect(t.asks[0].signal.aborted).toBe(false);
    expect(t.p.rows(null)).toBe(DASHES);
    expect(t.asks[0].signal.aborted).toBe(true);
    expect(t.asks).toHaveLength(1);
  });
  it('an answer that arrives after its abort is not drawn', async () => {
    const t = previews(() => req('BBCA', 'BBRI'));
    t.p.rows(req('BBCA'));
    t.p.rows(req('BBCA', 'BBRI'));
    t.asks[0].ok(answer(req('BBCA'))); await tick();
    expect(t.answered).not.toHaveBeenCalled();
  });
});

describe('a preview another tab replaced: 409 PREVIEW_REPLACED (review PAGE-V3)', () => {
  const replaced = () => new ApiFailure('The backtest service answered 409 (PREVIEW_REPLACED).', 'PREVIEW_REPLACED', 409);
  it('shows no toast, keeps the dashes and is not asked again by itself', async () => {
    const t = previews(() => req('BBCA'));
    t.p.rows(req('BBCA'));
    t.asks[0].no(replaced()); await tick();
    expect(t.failed).not.toHaveBeenCalled();
    expect(t.answered).not.toHaveBeenCalled();
    for (let k = 0; k < 3; k++) expect(t.p.rows(req('BBCA'))).toBe(DASHES);       // redraws: no new ask
    expect(t.ask).toHaveBeenCalledTimes(1);
  });
  it('is asked again at the next redraw after a user action', async () => {
    const t = previews(() => req('BBCA'));
    t.p.rows(req('BBCA'));
    t.asks[0].no(replaced()); await tick();
    t.p.userAction();
    t.p.rows(req('BBCA'));
    expect(t.ask).toHaveBeenCalledTimes(2);
    t.asks[1].ok(answer(req('BBCA'))); await tick();
    expect(t.answered).toHaveBeenCalledWith('');
    expect(t.p.rows(req('BBCA'))('BBCA')).toEqual({ n:2, last:'2022-12-01' });
  });
  it('keeps the rows of settings answered before; other settings are asked as usual', async () => {
    const t = previews(() => req('BBCA'));
    t.p.rows(req('BBCA')); t.asks[0].ok(answer(req('BBCA'))); await tick();
    t.p.rows(req('BBRI')); t.asks[1].no(replaced()); await tick();
    expect(t.p.rows(req('BBCA'))('BBCA').n).toBe(2);
    t.p.rows(req('TLKM'));
    expect(t.ask).toHaveBeenCalledTimes(3);
  });
  it('any other failure is the toast', async () => {
    const t = previews(() => req('BBCA'));
    t.p.rows(req('BBCA'));
    t.asks[0].no(new ApiFailure('The backtest service answered 503.', 'UNAVAILABLE', 503)); await tick();
    expect(t.failed).toHaveBeenCalledWith('The backtest service answered 503.');
  });
});

describe('a failed preview (review PG-2)', () => {
  const unavailable = () => new ApiFailure('The backtest service answered 503.', 'UNAVAILABLE', 503);
  it('is not asked again, nor toasted again, while the settings stay the same (a redraw: zoom, a legend chip)', async () => {
    const t = previews(() => req('BBCA'));
    t.p.rows(req('BBCA'));
    t.asks[0].no(unavailable()); await tick();
    for (let k = 0; k < 3; k++) expect(t.p.rows(req('BBCA'))).toBe(DASHES);
    t.p.userAction();                                        // a click on a zoom button is a user action too
    expect(t.p.rows(req('BBCA'))).toBe(DASHES);
    expect(t.ask).toHaveBeenCalledTimes(1);
    expect(t.failed).toHaveBeenCalledTimes(1);
  });
  it('is asked again once the settings changed, also back to the failed ones', async () => {
    const t = previews(() => req('BBCA'));
    t.p.rows(req('BBCA'));
    t.asks[0].no(unavailable()); await tick();
    t.p.rows(req('BBRI'));
    t.p.rows(req('BBCA'));
    expect(t.ask).toHaveBeenCalledTimes(3);
  });
  it('is the failed one\'s while the run\'s own rows are shown with the same settings', async () => {
    const t = previews(() => req('BBCA'));
    t.p.rows(req('BBCA'));
    t.asks[0].no(unavailable()); await tick();
    const run: Rows = () => ({ n:7, last:null });
    expect(t.p.rows(req('BBCA'), run)).toBe(run);
    t.p.rows(req('BBCA'));
    expect(t.ask).toHaveBeenCalledTimes(1);
  });
  it('UNIVERSE_EMPTY (every picked stock left out) is the short line and every row "—" with the error, never asked again', async () => {
    const long = 'All 8 picked stocks were left out because their own data cannot serve the strategy (8 INDICATOR_OUTPUT_EMPTY): no stock is left to count signals on. The first is W000: W000 has no value of the entry conditions on its bars up to the end of the period.';
    const q = req('W000', 'W001', 'W002', 'W003', 'W004', 'W005', 'W006', 'W007');
    const t = previews(() => q);
    t.p.rows(q);
    t.asks[0].no(new ApiFailure(long, 'UNIVERSE_EMPTY', 422, 'tickers')); await tick();
    expect(t.failed).not.toHaveBeenCalled();
    expect(t.answered).toHaveBeenCalledWith('8 stocks left out (see the — rows)');
    const rows = t.p.rows(q);
    expect(rows('W003')).toEqual({ n:null, last:null, left:{ code:'UNIVERSE_EMPTY', message:long } });
    t.p.rows(req('W000')); t.asks[1].no(new ApiFailure('The picked stock was left out …', 'UNIVERSE_EMPTY', 422, 'tickers')); await tick();
    t.p.rows(q);
    expect(t.ask).toHaveBeenCalledTimes(2);
  });
  it('UNIVERSE_EMPTY of settings no longer shown is kept, not drawn', async () => {
    const t = previews(() => req('BBRI'));
    t.p.rows(req('W000'));
    t.asks[0].no(new ApiFailure('The picked stock was left out …', 'UNIVERSE_EMPTY', 422, 'tickers')); await tick();
    expect(t.answered).not.toHaveBeenCalled();
    expect(t.p.rows(req('W000'))('W000').left?.code).toBe('UNIVERSE_EMPTY');
  });
});

describe('the toast of a preview\'s warnings (review PAGE-V1)', () => {
  const many = Array.from({ length:40 }, (_, k) => `W${String(k).padStart(3, '0')}`);
  it('is one short line: how many stocks were left out, never their tickers or reasons', () => {
    const note = previewNote([left(...many)]);
    expect(note).toBe('40 stocks left out (see the — rows)');
    expect(note).not.toMatch(/\n/);
    expect(previewNote([left('BBCA')])).toBe('1 stock left out (see the — row)');
    expect(previewNote([])).toBe('');
  });
  it('is shown once for the same warnings, and only for the current settings', async () => {
    let cur = req('BBCA', 'W000');
    const t = previews(() => cur);
    t.p.rows(cur); t.asks[0].ok(answer(req('BBCA'), [left('W000')])); await tick();
    expect(t.answered).toHaveBeenLastCalledWith('1 stock left out (see the — row)');
    cur = req('BBRI', 'W000');
    t.p.rows(cur); t.asks[1].ok(answer(req('BBRI'), [left('W000')])); await tick();
    expect(t.answered).toHaveBeenLastCalledWith('');
    t.p.rows(req('TLKM', 'W000'));                          // cur stays BBRI+W000: this answer is cached, not drawn
    t.asks[2].ok(answer(req('TLKM'), [left('W000', 'W001')])); await tick();
    expect(t.answered).toHaveBeenCalledTimes(2);
  });
});
