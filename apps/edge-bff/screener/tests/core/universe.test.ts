/* Stage S0 (report TARGET ARCHITECTURE 6.10, 6.12; TEST PLAN 10b.5): the one universe function of the page and the
   worker. P4 chips on by default (stale and price-break tickers hidden and counted once), P15 unclassified stocks
   (include filters keep them only with include_unclassified, exclude filters never drop them), inclusive bounds, a null
   attribute fails a bound, universe-attribute metric filters applied here and the others left to the worker. */
import { describe, expect, it } from 'vitest';
import { UNIVERSE_DEFAULTS } from '../../src/core/contract.ts';
import type { UniverseDef, UniverseRow } from '../../src/core/contract.ts';
import { applyUniverse, distortionRemarks, hasPriceBreak, isStale, priceBreakDates } from '../../src/core/universe.ts';

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
/* the chips switched on: these tests read the hiding rule (EXEC-PRICE-DISTORTION: off by default since 2026-11-24) */
const def = (o: Partial<UniverseDef> = {}): UniverseDef => ({ ...UNIVERSE_DEFAULTS, traded_on_eval_date: true, exclude_price_breaks: true, ...o } as UniverseDef);
const tickers = (u: UniverseDef) => applyUniverse(ROWS, u).eligible.map(r => r.ticker);

describe('applyUniverse', () => {
  it('hides stale and price-break tickers with the chips on and counts each once; the counts add up', () => {
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
  it('the defaults and a request that leaves the chips out list them with their remarks (EXEC-PRICE-DISTORTION: "value harus tetap ditampilkan as is dengan badge"); only true hides', () => {
    expect([UNIVERSE_DEFAULTS.traded_on_eval_date, UNIVERSE_DEFAULTS.exclude_price_breaks]).toEqual([false, false]);
    const { traded_on_eval_date: _t, exclude_price_breaks: _e, ...rest } = def();
    const r = applyUniverse(ROWS, rest as UniverseDef);
    expect(r.eligible.map(x => x.ticker)).toEqual(['BBCA', 'ADHI', 'PBSA', 'XCID', 'EDGE']);
    expect([r.counts.stale_hidden, r.counts.price_break_hidden]).toEqual([0, 0]);
    expect(tickers({ ...UNIVERSE_DEFAULTS } as UniverseDef)).toEqual(['BBCA', 'ADHI', 'PBSA', 'XCID', 'EDGE']);
    expect(tickers(def({ traded_on_eval_date: true, exclude_price_breaks: false }))).not.toContain('ADHI');
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

describe('distortionRemarks (EXEC-PRICE-DISTORTION: the one rule, pricecheck.ts)', () => {
  const BOUNDARY = '2026-09-12';
  const act = (type: string, ex_date: string, ratio_old: number | null = 1, ratio_new: number | null = 2, amount_per_share: number | null = null) =>
    ({ ticker: 'X', type, ex_date, ratio_old, ratio_new, amount_per_share });
  const opts = { boundary: BOUNDARY };
  it('a split left on the old scale is unadjusted (any date), the same split pulled again is no remark (PBSA before and after 2026-10-31)', () => {
    const dates = ['2026-10-13', '2026-10-14', '2026-10-27'];
    expect(distortionRemarks([act('STOCK_SPLIT', '2026-10-14')], dates, [845, 384, 302], opts)).toEqual([
      { code: 'PRICE_BREAK', kind: 'unadjusted', action: 'STOCK_SPLIT', ex_date: '2026-10-14', ratio_old: 1, ratio_new: 2, close_ratio: 384 / 845, effect: 1 }]);
    expect(distortionRemarks([act('STOCK_SPLIT', '2026-10-14')], dates, [422.5, 384, 302], opts)).toEqual([]);
    expect(distortionRemarks([act('STOCK_SPLIT', '2022-08-30')], ['2022-08-29', '2022-08-30'], [800, 400], opts).map(r => r.kind)).toEqual(['unadjusted']);   // an old step too (UD40)
  });
  it('an action that cannot be measured is uncertain from the boundary on, with its size; before it, read as adjusted', () => {
    const r = distortionRemarks([act('BONUS_SHARE', '2026-11-06', 30, 1)], ['2026-11-05', '2026-11-06'], [336, 334], opts);   // PSSI 3.3 %
    expect(r.map(x => [x.kind, x.action, +(x.effect ?? 0).toFixed(4)])).toEqual([['uncertain', 'BONUS_SHARE', 0.0333]]);
    expect(distortionRemarks([act('BONUS_SHARE', '2026-01-06', 30, 1)], ['2026-01-05', '2026-01-06'], [336, 334], opts)).toEqual([]);
    expect(distortionRemarks([act('RIGHT_ISSUE', '2026-10-20', null, null)], ['2026-10-19', '2026-10-21'], [300, 290], opts).map(x => [x.kind, x.effect])).toEqual([['uncertain', null]]);
  });
  it('a session beyond the cap with no action is an anomaly (WGSH); a cash dividend, an action after the last bar and a duplicate add nothing', () => {
    const r = distortionRemarks([act('DIVIDEND', '2026-03-30', null, null), act('STOCK_SPLIT', '2026-05-02')], ['2026-03-30', '2026-03-31', '2026-04-01'], [125, 65, 128], opts);
    expect(r.map(x => [x.kind, x.action, x.ex_date])).toEqual([['anomaly', 'PRICE_ANOMALY', '2026-03-31'], ['anomaly', 'PRICE_ANOMALY', '2026-04-01']]);
    const twice = distortionRemarks([act('STOCK_SPLIT', '2026-10-14'), act('STOCK_SPLIT', '2026-10-14')], ['2026-10-13', '2026-10-14'], [845, 384], opts);
    expect(twice.length).toBe(1);
    expect(distortionRemarks([act('STOCK_SPLIT', '2026-10-14')], [], [], opts)).toEqual([]);
  });
  it('the ex-dates of a row\'s PRICE_BREAK remarks are what the cell rule reads', () => {
    expect(priceBreakDates(ROWS.find(r => r.ticker === 'PBSA')!)).toEqual(['2026-10-14']);
    expect(priceBreakDates(ROWS.find(r => r.ticker === 'ADHI')!)).toEqual([]);
  });
});
