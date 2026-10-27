/* The portfolio picker's rules (picked.ts, CONTRACT.md PF1-PF7) and the picked stocks at boot (state.ts applyCatalog):
   the search's order and size, the groups' AND and their unclassified stocks, the limit, the chart's ticker always one
   of the picked stocks (review finding (a)), the tickers of a run whose events edge-bff keeps (review PAGE-V2). */
import { afterEach, describe, expect, it } from 'vitest';
import type { BacktestResultCore, Catalog } from '../src/core/contract.ts';
import { MAX_PORTFOLIO_TICKERS } from '../src/core/engine.ts';
import { Compute } from '../src/api/compute.ts';
import type { BacktestApi } from '../src/api/types.ts';
import { setEnv } from '../src/env.ts';
import { applyCatalog, S } from '../src/state.ts';
import { addTickers, chartTicker, groupLabel, groupStocks, limitText, runTickers, searchMatches, stocksOf, stocksText, tickersLabel, titleNames, type Stock } from '../src/picked.ts';
import { CATALOG } from './smoke/stub.ts';

const st = (ticker: string, name: string | null, sector: string | null, industry: string | null = null): Stock =>
  ({ ticker, name, type:'stock', groups:{ sector, industry } });
const STOCKS: Stock[] = [
  st('BBCA', 'Bank Central Asia', 'Banks', 'Banking'), st('ABBA', 'Mahaka Media', 'Media', null),
  st('BBRI', 'Bank Rakyat Indonesia', 'Banks', 'Banking'), st('MAPI', 'Mitra Adiperkasa', 'Retail', 'Apparel'),
  st('BANK', 'Bank Aladin Syariah', 'Banks', null), st('XBBC', null, null, null),
];
const tickers = (list: Stock[]) => list.map(s => s.ticker);

describe('the search (searchMatches)', () => {
  it('lists the ticker prefix matches first, then the name matches, each in catalog order, case-insensitive', () => {
    // "ba": BANK starts with it; BBCA, BBRI (Bank ...) and BANK's own name contain it (BANK is listed once)
    expect(tickers(searchMatches(STOCKS, 'ba', 10).shown)).toEqual(['BANK', 'BBCA', 'BBRI']);
    expect(tickers(searchMatches(STOCKS, 'BB', 10).shown)).toEqual(['BBCA', 'BBRI']);
    expect(tickers(searchMatches(STOCKS, 'MEDIA', 10).shown)).toEqual(['ABBA']);
  });
  it('shows at most `limit` of them and counts every match', () => {
    expect(searchMatches(STOCKS, 'b', 2)).toEqual({ shown:[STOCKS[0], STOCKS[2]], total:3 });
    expect(searchMatches(STOCKS, 'b', 0)).toEqual({ shown:[], total:3 });
  });
  it('a blank query matches nothing; a stock without a name is found by its ticker only', () => {
    expect(searchMatches(STOCKS, '  ', 10)).toEqual({ shown:[], total:0 });
    expect(tickers(searchMatches(STOCKS, 'xb', 10).shown)).toEqual(['XBBC']);
  });
});

describe('the groups (groupStocks)', () => {
  it('lists the stocks with the chosen value of every grouping that has one (AND)', () => {
    expect(tickers(groupStocks(STOCKS, { sector:'Banks' }))).toEqual(['BBCA', 'BBRI', 'BANK']);
    expect(tickers(groupStocks(STOCKS, { sector:'Banks', industry:'Banking' }))).toEqual(['BBCA', 'BBRI']);
    expect(tickers(groupStocks(STOCKS, { sector:'Retail', industry:'Banking' }))).toEqual([]);
  });
  it('null chooses the unclassified stocks of that grouping', () => {
    expect(tickers(groupStocks(STOCKS, { industry:null }))).toEqual(['ABBA', 'BANK', 'XBBC']);
    expect(tickers(groupStocks(STOCKS, { sector:'Banks', industry:null }))).toEqual(['BANK']);
  });
  it('lists nothing while no grouping has a chosen value', () => {
    expect(groupStocks(STOCKS, {})).toEqual([]);
  });
  it('a grouping\'s label is its column name; the catalog\'s stocks leave the indexes out', () => {
    expect([groupLabel('sector'), groupLabel('sub_industry')]).toEqual(['Sector', 'Sub industry']);
    const cat = { tickers:[...STOCKS, { ticker:'COMPOSITE', name:'IDX Composite', type:'index', groups:{} }] } as unknown as Catalog;
    expect(tickers(stocksOf(cat))).toEqual(tickers(STOCKS));
  });
});

describe('the limit (addTickers)', () => {
  it('adds the stocks not picked yet, in their order, never past the limit; the rest is refused', () => {
    expect(addTickers(['BBCA'], ['BBRI', 'BBCA', 'MAPI'], 12)).toEqual({ picked:['BBCA', 'BBRI', 'MAPI'], refused:0 });
    expect(addTickers(['BBCA', 'BBRI'], ['MAPI', 'BANK', 'ABBA'], 3)).toEqual({ picked:['BBCA', 'BBRI', 'MAPI'], refused:2 });
    expect(addTickers(['BBCA', 'BBRI', 'MAPI'], ['BBCA'], 3)).toEqual({ picked:['BBCA', 'BBRI', 'MAPI'], refused:0 });
  });
  it('is refused with the condition limit\'s wording, "1 stock" for a limit of 1 (review PG-5)', () => {
    expect(limitText(12)).toBe('Limit reached: at most 12 stocks per portfolio.');
    expect(limitText(1)).toBe('Limit reached: at most 1 stock per portfolio.');
  });
  it('an add-all of a long group stops at the catalog\'s limit', () => {
    const many = Array.from({ length:20 }, (_, k) => `S${String(k).padStart(3, '0')}`);
    const r = addTickers([], many, MAX_PORTFOLIO_TICKERS);
    expect([r.picked.length, r.refused]).toEqual([MAX_PORTFOLIO_TICKERS, 20 - MAX_PORTFOLIO_TICKERS]);
  });
});

describe('the chart\'s ticker (chartTicker, review finding (a))', () => {
  it('stays while it is picked', () => {
    expect(chartTicker('BBRI', ['BBCA', 'BBRI'])).toBe('BBRI');
  });
  it('is never a stock that is not picked (the single-stock ticker after a switch to a portfolio without it)', () => {
    expect(chartTicker('MAPI', ['BBCA', 'BBRI'])).toBe('BBCA');
    expect(chartTicker('MAPI', [])).toBe('');
  });
  it('prefers a picked stock the shown run ran on', () => {
    expect(chartTicker('MAPI', ['BBCA', 'BBRI'], ['BBRI', 'TLKM'])).toBe('BBRI');
  });
});

describe('the tickers of a run (runTickers, review PAGE-V2)', () => {
  it('are the ones it ran on and every one its entry tracks name, each once', () => {
    const r = { meta:{ tickers:['BBCA', 'BBRI'] }, events:{ entries:{ BBCA:{}, ASII:{} } } } as unknown as BacktestResultCore;
    expect(runTickers(r)).toEqual(['BBCA', 'BBRI', 'ASII']);
  });
});

describe('the picked stocks\' words', () => {
  it('name up to three tickers, then how many more (the reference\'s "Banks (BBCA, BBRI, BMRI)")', () => {
    expect(tickersLabel(['BBCA', 'BBRI', 'BMRI'])).toBe('BBCA, BBRI, BMRI');
    expect(tickersLabel(['BBCA', 'BBRI', 'BMRI', 'TLKM', 'ASII'])).toBe('BBCA, BBRI, BMRI +2');
    expect([stocksText(1), stocksText(12)]).toEqual(['1 stock', '12 stocks']);
  });
  it('the view bar\'s title may name them by fewer tickers, longest first, each name once (review PG-3)', () => {
    expect(titleNames(['BBCA', 'BBRI', 'BMRI', 'TLKM', 'ASII'])).toEqual(['BBCA, BBRI, BMRI +2', 'BBCA, BBRI +3', 'BBCA +4']);
    expect(titleNames(['BBCA', 'BBRI'])).toEqual(['BBCA, BBRI', 'BBCA +1']);
    expect(titleNames(['BBCA'])).toEqual(['BBCA']);
  });
});

describe('the picked stocks at boot (applyCatalog)', () => {
  afterEach(() => { S.tickers = [] });
  const boot = (picked?: string[]) => { const c = new Compute(() => CATALOG); setEnv({ ready:x => c.ready(x) } as BacktestApi, CATALOG); applyCatalog(picked); return S.tickers };
  it('are none on live data (no published data names a sample set of stocks)', () => {
    S.tickers = ['BBCA'];
    expect(boot()).toEqual([]);
  });
  it('a test build\'s default portfolio keeps its published stocks, at most the limit', () => {
    expect(boot(['BBRI', 'NOPE', 'BBCA'])).toEqual(['BBRI', 'BBCA']);
    expect(CATALOG.limits.max_portfolio_tickers).toBe(MAX_PORTFOLIO_TICKERS);
  });
});
