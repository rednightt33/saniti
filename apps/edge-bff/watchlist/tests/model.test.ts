/* EXEC-WATCHLIST L5: what the page arranges from the daily file and the lists (src/model.ts), on small hand-made data. */
import { describe, expect, it } from 'vitest';
import * as M from '../src/model.ts';
import type { CatalogItem, StocksFile, WList } from '../src/types.ts';
import sample from './fixture/watchlist-stocks.sample.json';

const c = (key: string, unit: string, signed: boolean, family = 'Technical', date: 'price' | 'broker' = 'price'): CatalogItem =>
  ({ key, name: key.toUpperCase(), short: key, note: '', family, unit, date, signed });
const CATALOG = [c('rsi', 'index', false), c('macdh', 'price', true), c('ema50', 'pct', true), c('volr', 'ratio', false, 'Price & volume'),
  c('vol20', 'pct', false, 'Price & volume'), c('dd60', 'pct', false, 'Price & volume'), c('fn5', 'rp', true, 'Foreign flow', 'broker'),
  c('fp5', 'rank', false, 'Foreign flow', 'broker')];
const file: StocksFile = {
  schema: 1, prices_through: '2026-11-13', broker_through: '2026-11-09', radar_date: '2026-11-09', events_loaded: '2026-11-09',
  event_days: 30, radar_board: { level: 'standard', gate: 'broad' }, dates: ['2026-11-12', '2026-11-13'],
  catalog: CATALOG, default: ['rsi', 'volr', 'dd60', 'fn5'],
  radar_filters: [{ label: 'S2', name: 'Strengthening foreign flow' }, { label: 'S7', name: 'Institutions in, retail out' }],
  ticker: ['AAAA', 'BBBB', 'CCCC'], name: ['A Tbk', 'Bank B Tbk', 'C Tbk'], sector: ['Energy', 'Financials', 'Energy'],
  last: [10700, 9150, null], r1d: [1.6627, -0.2075, null], r1m: [8.08, -15.5, null], trend: [[100, 110], [120, 100], [null, null]],
  values: { rsi: [48.08, 66.1, null], macdh: [-33.446, 2, null], ema50: [-1.24, 12.87, null], volr: [0.6089, 1.2, null],
            vol20: [50.47, 42.5, null], dd60: [-14.056, 0, null], fn5: [13713390000, -416919462500, null], fp5: [59.92, 42.46, null] },
  events: { BBBB: [['DIVIDEND', '2026-11-20', 'CUM_DATE'], ['RUPS', '2026-11-24', 'MEETING_DATE']] },
  radar: { AAAA: ['S2', 'S7'] },
};
const cat = M.catalog(file), by = M.stocks(file);
const list = (id: string, tickers: string[], indicators: string[] | null = null, position = 0): WList =>
  ({ id, name: id.toUpperCase(), position, indicators, tickers: tickers.map((ticker, i) => ({ ticker, position: i * 2 })) });

describe('labels and numbers', () => {
  it('names dates with no-break spaces', () => {
    expect(M.dateLabel('2026-11-13', true)).toBe('Fri 13 Nov');
    expect(M.dateLabel('2026-11-09')).toBe('9 Nov');
    expect(M.dateLabel(null)).toBe('—');
  });
  it('writes 1D with 2 decimals and the minus sign, prices rounded with thousands', () => {
    expect(M.fPct(1.6627)).toBe('+1.66%');
    expect(M.fPct(-0.2075)).toBe('−0.21%');
    expect(M.fPct(-0.001)).toBe('0.00%');                            // the sign of the rounded value
    expect(M.fPct(8.08, 1)).toBe('+8.1%');
    expect(M.fPx(10700)).toBe('10,700');
    expect(M.fPct(null)).toBeNull();
  });
  it('writes rupiah as the mockup: a no-break space after Rp, M/B/T, the minus sign', () => {
    expect(M.fRp(13713390000)).toBe('+Rp 13.7B');
    expect(M.fRp(-416919462500)).toBe('−Rp 416.9B');
    expect(M.fRp(2.1e12)).toBe('+Rp 2.1T');
    expect(M.fRp(5528035)).toBe('+Rp 5.5M');
    expect(M.fRp(40000)).toBe('Rp 0');
    expect(M.fRp(0)).toBe('Rp 0');
  });
  it('formats each indicator by its catalog unit', () => {
    const f = (k: string, v: number) => M.formatValue(cat.by[k], v);
    expect(f('rsi', 48.08)).toBe('48.1');                              // index: 1 decimal
    expect(f('macdh', -33.446)).toBe('−33.4');
    expect(f('ema50', 12.87)).toBe('+12.9%');                          // a signed pct: its sign
    expect(f('ema50', -1.24)).toBe('−1.2%');
    expect(f('vol20', 50.47)).toBe('50.5%');                           // not signed: no "+"
    expect(f('dd60', -14.056)).toBe('−14.1%');
    expect(f('dd60', 0)).toBe('0.0%');
    expect(f('volr', 0.6089)).toBe('0.6×');                            // ratio
    expect(f('fn5', 13713390000)).toBe('+Rp 13.7B');             // rp
    expect(f('fp5', 59.92)).toBe('P60');                               // rank
    expect(M.formatValue(cat.by.rsi, null)).toBeNull();
  });
});

describe('the indicators come from the file', () => {
  it('offers exactly the catalog, grouped by family in its order', () => {
    expect(cat.items.map(x => x.key)).toEqual(CATALOG.map(x => x.key));
    expect(cat.families.map(([f, a]) => [f, a.length])).toEqual([['Technical', 3], ['Price & volume', 3], ['Foreign flow', 2]]);
    const other = M.catalog({ catalog: [c('zz', 'index', false, 'New family')], default: ['zz'] });
    expect(other.items.map(x => x.key)).toEqual(['zz']);               // a new indicator needs no page change
    expect(other.families[0][0]).toBe('New family');
  });
  it('the publisher sample file holds every catalog key in values', () => {
    const s = sample as unknown as StocksFile;
    expect(Object.keys(s.values).sort()).toEqual(s.catalog.map(x => x.key).sort());
    expect(s.trend.every(t => t.length === s.dates.length)).toBe(true);
  });
  it('a list without its own choice shows the default; unknown keys are skipped; the limit holds', () => {
    expect(M.indicatorsOf({ indicators: null }, cat)).toEqual(['rsi', 'volr', 'dd60', 'fn5']);
    expect(M.indicatorsOf({ indicators: ['gone', 'fp5', 'rsi', 'fp5'] }, cat)).toEqual(['fp5', 'rsi']);
    expect(M.indicatorsOf({ indicators: ['gone'] }, cat)).toEqual(['rsi', 'volr', 'dd60', 'fn5']);
    expect(M.indicatorsOf({ indicators: CATALOG.map(x => x.key) }, cat, 3)).toEqual(['rsi', 'macdh', 'ema50']);
    expect(M.catalog({ catalog: CATALOG, default: ['nope'] }).def).toEqual(['rsi', 'macdh', 'ema50', 'volr']);
  });
  it('reads a value of a stock, and a missing one as a dash', () => {
    expect(M.indVal(file, cat.by.fn5, by.get('BBBB')!)).toEqual({ v: '−Rp 416.9B', k: 'down', na: false });
    expect(M.indVal(file, cat.by.rsi, by.get('CCCC')!)).toEqual({ v: '—', k: '', na: true });
    expect(M.indVal(file, cat.by.rsi, M.unknownStock('GONE'))).toEqual({ v: '—', k: '', na: true });
    expect(M.indVal(file, cat.by.volr, by.get('AAAA')!).k).toBe('');   // not signed: not coloured
    expect(M.flowPill(cat.by.fn5)).toBe(true);
    expect(M.flowPill(cat.by.fp5)).toBe(false);
  });
  it('takes the limits edge-bff publishes, and none it does not', () => {
    const l = M.limitsOf([{ name: 'lists', value: 20, unit: 'lists', rule: '', example_ok: '', example_refused: '' },
      { name: 'tickers', value: 50, unit: '', rule: '', example_ok: '', example_refused: '' },
      { name: 'indicators', value: 8, unit: '', rule: '', example_ok: '', example_refused: '' }]);
    expect(l).toEqual({ lists: 20, tickers: 50, indicators: 8, name: Infinity });
  });
});

describe('badges and filters', () => {
  it('names events as the mockup and counts the others', () => {
    expect(M.evName(['RUPS', '2026-11-17', 'MEETING_DATE'])).toBe('RUPS');
    expect(M.evName(['DIVIDEND', '2026-11-20', 'CUM_DATE'])).toBe('Dividend cum');
    expect(M.evName(['DIVIDEND', '2026-11-23', 'EX_DATE'])).toBe('Dividend ex');
    expect(M.evName(['CASH_OFFER', '2026-12-08', ''])).toBe('Cash offer');
    expect(M.evName(['PUBLIC_EXPOSE', '2026-11-20', 'EXPOSE_DATE'])).toBe('Public expose');   // not an ex date
    expect(M.eventBadge(by.get('BBBB')!)).toEqual({ label: 'Dividend cum 20 Nov', more: 1, all: ['Dividend cum 20 Nov', 'RUPS 24 Nov'] });
    expect(M.eventBadge(by.get('AAAA')!)).toBeNull();
  });
  it('writes the Radar badge long on a card and short in the table', () => {
    expect(M.radarBadge(by.get('AAAA')!, false)).toBe('Radar S2 S7');
    expect(M.radarBadge(by.get('AAAA')!, true)).toBe('2 Radar');
    expect(M.radarBadge(by.get('BBBB')!, true)).toBeNull();
    expect(M.radarNames(file).S7).toBe('Institutions in, retail out');
  });
  it('filters on Radar, on a corporate action, or both', () => {
    const all = ['AAAA', 'BBBB', 'CCCC'].map(t => by.get(t)!);
    const keep = (f: M.Filter) => all.filter(s => M.passes(s, f)).map(s => s.t);
    expect(keep({ radar: false, ev: false })).toEqual(['AAAA', 'BBBB', 'CCCC']);
    expect(keep({ radar: true, ev: false })).toEqual(['AAAA']);
    expect(keep({ radar: false, ev: true })).toEqual(['BBBB']);
    expect(keep({ radar: true, ev: true })).toEqual([]);
  });
});

describe('the table, the search and the trend', () => {
  it('sorts the view (missing last), turns, and goes back to list order', () => {
    const ss = ['CCCC', 'AAAA', 'BBBB'].map(t => by.get(t)!);
    let s = M.nextSort(null, 'last', 'Last');
    expect(M.sortStocks(ss, s, file).map(x => x.t)).toEqual(['AAAA', 'BBBB', 'CCCC']);
    s = M.nextSort(s, 'last', 'Last');
    expect(M.sortStocks(ss, s, file).map(x => x.t)).toEqual(['BBBB', 'AAAA', 'CCCC']);
    expect(M.nextSort(s, 'last', 'Last')).toBeNull();
    expect(M.sortStocks(ss, M.nextSort(null, 't', 'Stock'), file).map(x => x.t)).toEqual(['AAAA', 'BBBB', 'CCCC']);
    expect(M.sortStocks(ss, M.nextSort(null, 'fn5', 'Foreign 5D'), file).map(x => x.t)).toEqual(['AAAA', 'BBBB', 'CCCC']);
    expect(M.sortStocks(ss, null, file)).toBe(ss);
  });
  it('finds codes first, then names; several pasted codes; suggestions from other lists then Radar', () => {
    const all = [...by.values()];
    expect(M.search(all, by, 'b').map(s => s.t)).toEqual(['BBBB', 'AAAA', 'CCCC']);   // the code first, then "Tbk"
    expect(M.search(all, by, 'tbk').map(s => s.t)).toEqual(['AAAA', 'BBBB', 'CCCC']);
    expect(M.search(all, by, 'bank').map(s => s.t)).toEqual(['BBBB']);
    expect(M.parseCodes('aaaa, bbbb;zz  aaaa')).toEqual(['AAAA', 'BBBB', 'ZZ']);
    expect(M.isMulti('AAAA BBBB')).toBe(true);
    expect(M.isMulti('AAAA')).toBe(false);
    expect(M.search(all, by, 'AAAA, ZZ, CCCC').map(s => s.t)).toEqual(['AAAA', 'CCCC']);
    const a = list('a', ['AAAA']), b = list('b', ['CCCC', 'AAAA']);
    expect(M.suggestions([a, b], a, by, file)).toEqual(['CCCC']);
    expect(M.suggestions([a, b], b, by, file)).toEqual([]);                 // AAAA (Radar) is already in b
    expect(M.suggestions([b], list('c', []), by, file)).toEqual(['CCCC', 'AAAA']);
    expect(M.dupName([a, b], ' b ')).toBe(true);
    expect(M.dupName([a, b], 'B', 'b')).toBe(false);
  });
  it('draws the trend from the closes it has, green when it ends higher', () => {
    expect(M.spark([100, 110], 84, 22)).toContain('var(--up)');
    expect(M.spark([120, 100], 84, 22)).toContain('var(--down)');
    expect(M.spark([null, null], 84, 22)).toBeNull();
    expect(M.spark([100, null, 105], 300, 40, true)).toContain('width:100%');
  });
});

describe('undo', () => {
  it('a deleted list comes back with its name, stocks in order, indicators and place', () => {
    const l = list('core', ['BBBB', 'AAAA'], ['rsi', 'fp5'], 3);
    expect(M.restoreListBody(l)).toEqual({ name: 'CORE', tickers: ['BBBB', 'AAAA'], indicators: ['rsi', 'fp5'], position: 3 });
    expect(M.restoreListBody(list('d', [], null, 0))).toEqual({ name: 'D', tickers: [], indicators: null, position: 0 });
  });
  it('a removed stock goes back at its place', () => {
    const l = list('core', ['BBBB', 'AAAA', 'CCCC']);
    expect(M.restoreTickerBody(l, 'AAAA')).toEqual({ tickers: ['AAAA'], position: 2 });
    expect(M.restoreTickerBody(l, 'ZZZZ')).toBeNull();
  });
});

describe('review 2026-11-16: a value that reads as zero is not coloured', () => {
  const file = sample as unknown as StocksFile, cat = M.catalog(file);
  it('a small MACD histogram keeps two decimals and a rounded zero has no colour', () => {
    expect(M.formatValue(cat.by.macdh, 0.04)).toBe('0.04');
    expect(M.formatValue(cat.by.macdh, -0.004)).toBe('0.00');
    expect(M.formatValue(cat.by.macdh, -12.34)).toBe('−12.3');
    const s = { ...M.stocks(file).values().next().value!, i: 0 };
    const at = (k: string, v: number) => { const f = { ...file, values: { ...file.values, [k]: [v] } } as StocksFile; return M.indVal(f, cat.by[k], s) };
    expect(at('fn5', 400000)).toEqual({ v: 'Rp\u00a00', k: '', na: false });
    expect(at('r5d', -0.04)).toEqual({ v: '0.0%', k: '', na: false });
    expect(at('r5d', -0.06).k).toBe('down');
  });
});

describe('Alt+A (Add stocks), shaped as the Screener Alt+S', () => {
  const k = (o: Partial<KeyboardEvent>) => ({ altKey: false, ctrlKey: false, metaKey: false, shiftKey: false, key: '', code: '', repeat: false, isComposing: false, ...o });
  it('is Alt with the A key alone, by the physical key too (a layout where Alt+A types å)', () => {
    expect(M.isAltA(k({ altKey: true, code: 'KeyA', key: 'a' }))).toBe(true);
    expect(M.isAltA(k({ altKey: true, code: 'KeyA', key: 'å' }))).toBe(true);
    expect(M.isAltA(k({ altKey: true, key: 'A' }))).toBe(true);
  });
  it('is not A alone, Ctrl/Cmd/Shift with it, Alt+S, a held key or a composition', () => {
    expect(M.isAltA(k({ code: 'KeyA', key: 'a' }))).toBe(false);
    expect(M.isAltA(k({ altKey: true, ctrlKey: true, code: 'KeyA' }))).toBe(false);
    expect(M.isAltA(k({ altKey: true, metaKey: true, code: 'KeyA' }))).toBe(false);
    expect(M.isAltA(k({ altKey: true, shiftKey: true, code: 'KeyA' }))).toBe(false);
    expect(M.isAltA(k({ altKey: true, code: 'KeyS', key: 's' }))).toBe(false);
    expect(M.isAltA(k({ altKey: true, code: 'KeyA', repeat: true }))).toBe(false);
    expect(M.isAltA(k({ altKey: true, code: 'KeyA', isComposing: true }))).toBe(false);
  });
  it('leaves a text field alone, not a button', () => {
    const el = (tagName: string, type?: string) => ({ tagName, type, isContentEditable: false }) as unknown as Element;
    expect(M.typingTarget(el('INPUT', 'search'))).toBe(true);
    expect(M.typingTarget(el('INPUT'))).toBe(true);
    expect(M.typingTarget(el('TEXTAREA'))).toBe(true);
    expect(M.typingTarget(el('INPUT', 'checkbox'))).toBe(false);
    expect(M.typingTarget(el('BUTTON'))).toBe(false);
    expect(M.typingTarget(null)).toBe(false);
  });
});

describe('the Radar file of its own (EXEC-MU-ACCOUNTS Phase 3d, ERRORS M476)', () => {
  const { radar_date, radar_board, radar_filters, radar, ...base } = file;
  const radarFile = { schema: 1, radar_date, radar_board, radar_filters, radar };
  it('merges watchlist-radar into the figures when the account may read it', () => {
    const m = M.withRadar(base as StocksFile, radarFile);
    expect(m.radar).toBe(true);
    expect(M.stocks(m.file).get('AAAA')!.rd).toEqual(['S2', 'S7']);
    expect(M.radarNames(m.file).S2).toBe('Strengthening foreign flow');
  });
  it('shows no Radar badge or filter without it (no radar.view): the figures stay', () => {
    const m = M.withRadar(base as StocksFile, null);
    expect(m.radar).toBe(false);
    expect(m.file.radar).toEqual({});
    expect(M.stocks(m.file).get('AAAA')!.rd).toEqual([]);
    expect(M.stocks(m.file).get('AAAA')!.last).toBe(10700);
  });
  it('reads the Radar fields of a base file published before 3d', () => {
    const m = M.withRadar(file, null);
    expect(m.radar).toBe(true);
    expect(M.stocks(m.file).get('AAAA')!.rd).toEqual(['S2', 'S7']);
  });
});
