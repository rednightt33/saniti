/* Stage S0 (report TARGET ARCHITECTURE 6.10, 6.12; TEST PLAN 10b.5): the one universe function of the page and the
   worker. P4 chips on by default (stale and price-break tickers hidden and counted once), P15 unclassified stocks
   (include filters keep them only with include_unclassified, exclude filters never drop them), inclusive bounds, a null
   attribute fails a bound, universe-attribute metric filters applied here and the others left to the worker. */
import { describe, expect, it } from 'vitest';
import { UNIVERSE_DEFAULTS } from '../../src/core/contract.ts';
import type { UniverseDef, UniverseRow } from '../../src/core/contract.ts';
import { applyUniverse, hasPriceBreak, isStale, priceBreakDates, priceBreakRemarks } from '../../src/core/universe.ts';

const row = (ticker: string, o: Partial<UniverseRow> = {}): UniverseRow => ({
  ticker, name: `${ticker} Tbk`, sector: 'Financials', industry: 'Banks', last: 1000, chg_1d_pct: 0.5, adv20_idr: 5e9,
  first_bar: '2018-01-02', last_bar: '2026-10-27', bars: 2100, stale: false, remarks: [], ...o,
});
const ROWS: UniverseRow[] = [
  row('BBCA'),
  row('ADHI', { sector: 'Infrastructures', industry: 'Construction', last_bar: '2026-08-21', stale: true, remarks: [{ code: 'STALE', last_bar_date: '2026-08-21' }] }),
  row('PBSA', { sector: 'Energy', industry: 'Coal', last: 302, remarks: [{ code: 'PRICE_BREAK', action: 'STOCK_SPLIT', ex_date: '2026-10-14', ratio_old: 1, ratio_new: 2, close_ratio: 0.4544 }] }),
  row('XCID', { sector: null, industry: null }),
  row('CHEAP', { last: 49, adv20_idr: 2e9 }),
  row('THIN', { adv20_idr: 999_999_999 }),
  row('EDGE', { last: 50, adv20_idr: 1e9, bars: 74 }),
  row('NOADV', { adv20_idr: null }),
];
const def = (o: Partial<UniverseDef> = {}): UniverseDef => ({ ...UNIVERSE_DEFAULTS, ...o } as UniverseDef);
const tickers = (u: UniverseDef) => applyUniverse(ROWS, u).eligible.map(r => r.ticker);

describe('applyUniverse', () => {
  it('hides stale and price-break tickers by default and counts each once; the counts add up', () => {
    const r = applyUniverse(ROWS, def());
    expect(r.eligible.map(x => x.ticker)).toEqual(['BBCA', 'XCID', 'EDGE']);
    expect(r.counts).toEqual({ listed: 8, eligible: 3, stale_hidden: 1, price_break_hidden: 1, filtered_out: 3 });
    expect(r.pending).toEqual([]);
  });
  it('lists them with the chips off (their remarks stay on the row), and counts 0 hidden', () => {
    const r = applyUniverse(ROWS, def({ traded_on_eval_date: false, exclude_price_breaks: false }));
    expect(r.eligible.map(x => x.ticker)).toEqual(['BBCA', 'ADHI', 'PBSA', 'XCID', 'EDGE']);
    expect([r.counts.stale_hidden, r.counts.price_break_hidden]).toEqual([0, 0]);
    expect(r.eligible.find(x => x.ticker === 'PBSA')!.remarks[0].code).toBe('PRICE_BREAK');
  });
  it('a request that leaves the P4 chips out hides as the defaults do (report 8.5 "Default true"); only false shows', () => {
    const { traded_on_eval_date: _t, exclude_price_breaks: _e, ...rest } = def();
    const r = applyUniverse(ROWS, rest as UniverseDef);
    expect(r.eligible.map(x => x.ticker)).toEqual(['BBCA', 'XCID', 'EDGE']);
    expect([r.counts.stale_hidden, r.counts.price_break_hidden]).toEqual([1, 1]);
    expect(tickers(def({ traded_on_eval_date: false }))).toContain('ADHI');
  });
  it('a stale ticker that also has a price break is counted once, as stale', () => {
    const both = [row('BOTH', { stale: true, remarks: [{ code: 'PRICE_BREAK', action: 'RIGHT_ISSUE', ex_date: '2026-09-22', ratio_old: null, ratio_new: null, close_ratio: null }] })];
    expect(applyUniverse(both, def()).counts).toEqual({ listed: 1, eligible: 0, stale_hidden: 1, price_break_hidden: 0, filtered_out: 0 });
  });
  it('keeps unclassified stocks out of include filters unless asked, and never drops them by an exclude filter (P15)', () => {
    expect(tickers(def({ sectors_in: ['Financials'] }))).toEqual(['BBCA', 'EDGE']);
    expect(tickers(def({ sectors_in: ['Financials'], include_unclassified: true }))).toEqual(['BBCA', 'XCID', 'EDGE']);
    expect(tickers(def({ sectors_out: ['Financials'] }))).toEqual(['XCID']);
    expect(tickers(def({ industries_in: ['Banks'], include_unclassified: true }))).toEqual(['BBCA', 'XCID', 'EDGE']);
  });
  it('bounds are inclusive and a null attribute fails a set bound', () => {
    expect(tickers(def({ price_min: 50, adv20_min_idr: 1e9 }))).toContain('EDGE');
    expect(tickers(def({ price_min: 50.01 }))).not.toContain('EDGE');
    expect(tickers(def({ adv20_min_idr: null, price_min: null }))).toEqual(['BBCA', 'XCID', 'CHEAP', 'THIN', 'EDGE', 'NOADV']);
    expect(tickers(def({ min_history_bars: 75 }))).not.toContain('EDGE');
    expect(tickers(def({ min_history_bars: 74 }))).toContain('EDGE');
  });
  it('keeps only an explicit ticker list', () => {
    expect(tickers(def({ tickers: ['EDGE', 'BBCA', 'ADHI'] }))).toEqual(['BBCA', 'EDGE']);
  });
  it('applies universe-attribute metric filters here and leaves the others to the worker', () => {
    const u = def({ metric_filters: [
      { kind: 'value', op: 'between', value: 0.5, value2: 0.5, metric: { kind: 'universe', attr: 'chg_1d_pct' } },
      { kind: 'value', op: 'lt', value: 30, metric: { kind: 'indicator', indicator: 'I13', output: 'rsi' } },
    ] });
    const r = applyUniverse(ROWS, u);
    expect(r.pending).toEqual([1]);
    expect(r.eligible.map(x => x.ticker)).toEqual(['BBCA', 'XCID', 'EDGE']);
    const none = applyUniverse(ROWS, def({ metric_filters: [{ kind: 'value', op: 'gt', value: 0.5, metric: { kind: 'universe', attr: 'chg_1d_pct' } }] }));
    expect(none.eligible).toEqual([]);
  });
  it('isStale and hasPriceBreak read the row', () => {
    expect([isStale({ last_bar: '2026-10-24' }, '2026-10-27'), isStale({ last_bar: '2026-10-27' }, '2026-10-27')]).toEqual([true, false]);
    expect(ROWS.map(hasPriceBreak).filter(Boolean).length).toBe(1);
  });
});

describe('priceBreakRemarks (P4; report 6.12 rule, TEST PLAN 10b.4 "Price breaks")', () => {
  const BOUNDARY = '2026-09-12', TYPES = ['STOCK_SPLIT', 'REVERSE_SPLIT', 'BONUS_SHARE', 'RIGHT_ISSUE', 'STOCK_DIVIDEND'];
  const dates = ['2026-07-15', '2026-07-16', '2026-10-13', '2026-10-14', '2026-10-27'];
  const closes = [920, 875, 845, 384, 302];
  const act = (type: string, ex_date: string, ratio_old: number | null = 1, ratio_new: number | null = 2) => ({ ticker: 'X', type, ex_date, ratio_old, ratio_new });
  const opts = { boundary: BOUNDARY, priceActionTypes: TYPES };
  it('flags a price-affecting action with boundary <= ex-date <= the last bar, with the observed close ratio', () => {
    expect(priceBreakRemarks([act('STOCK_SPLIT', '2026-10-14')], dates, closes, opts)).toEqual([
      { code: 'PRICE_BREAK', action: 'STOCK_SPLIT', ex_date: '2026-10-14', ratio_old: 1, ratio_new: 2, close_ratio: 384 / 845 }]);
  });
  it('never flags an action before the boundary (RAJA, adjusted), one after the last bar (MGLV) or a cash dividend', () => {
    expect(priceBreakRemarks([act('STOCK_SPLIT', '2026-07-16'), act('STOCK_SPLIT', '2026-11-02'), act('DIVIDEND', '2026-10-13', null, null)], dates, closes, opts)).toEqual([]);
  });
  it('an ex-date between sessions reads the next bar; missing ratios stay null; a duplicate is one remark; oldest first', () => {
    const r = priceBreakRemarks([act('RIGHT_ISSUE', '2026-10-20', null, null), act('BONUS_SHARE', '2026-10-01'), act('BONUS_SHARE', '2026-10-01')], dates, closes, opts);
    expect(r.map(x => [x.action, x.ex_date, x.ratio_old, x.close_ratio])).toEqual([['BONUS_SHARE', '2026-10-01', 1, 845 / 875], ['RIGHT_ISSUE', '2026-10-20', null, 302 / 384]]);
    expect(priceBreakRemarks([act('STOCK_SPLIT', '2026-10-14')], [], [], opts)).toEqual([]);
  });
  it('the ex-dates of a row\'s PRICE_BREAK remarks are what the cell rule reads', () => {
    expect(priceBreakDates(ROWS.find(r => r.ticker === 'PBSA')!)).toEqual(['2026-10-14']);
    expect(priceBreakDates(ROWS.find(r => r.ticker === 'ADHI')!)).toEqual([]);
  });
});
