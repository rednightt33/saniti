/* EXEC-OVERVIEW O5: what the page arranges from the Overview files (src/model.ts), on small hand-made files. */
import { describe, expect, it } from 'vitest';
import * as M from '../src/model.ts';
import type { Day, Meta, Series } from '../src/types.ts';

const meta: Meta = {
  schema: 1, market: 'IHSG', benchmark: 'LQ45',
  stocks: { ticker: ['AAAA', 'BBBB', 'CCCC', 'DDDD'], name: ['A Tbk', 'B Tbk', 'C Tbk', 'D Tbk'], sector: ['Financials', 'Financials', 'Energy', 'Other'] },
  sectors: [{ name: 'Energy', index: 'IDXENERGY' }, { name: 'Financials', index: 'IDXFINANCE' }, { name: 'Other', index: null }],
  lists: [{ key: 'INDEX:1', kind: 'INDEX', code: 'LQ45', name: 'LQ45', members: ['AAAA', 'CCCC'] },
          { key: 'KONGLO:2', kind: 'KONGLO', code: 'G', name: 'Group G', members: ['BBBB', 'DDDD'] }],
  dates: ['2026-11-12', '2026-11-13'], size_basis: 'adv20_value', prices_through: '2026-11-13', broker_through: '2026-11-12',
  periods: { flow: ['1D', '5D', '1M', '3M'] },
};
const day: Day = {
  schema: 1, date: '2026-11-13', prior_date: '2026-11-12', size_basis: 'adv20_value',
  index: { IHSG: { open: 100, high: 104, low: 99, close: 103, prior_close: 100 } },
  volatility: { window: 20, value: 12.5, rank_1y: 40 }, breadth: { advancers: 2, decliners: 1, unchanged: 1 },
  market: { date: '2026-11-12', turnover: 8e12, turnover_avg20: 1e13, turnover_ratio: 0.8, foreign_net_1d: 1e11, foreign_net_10d: -2e12,
            periods: { '1D': { buy: 3e12, sell: 2.9e12, net: 1e11, from: '2026-11-12' }, '5D': null, '1M': null, '3M': null } },
  stocks: { i: [0, 1, 2, 3], close: [1000, 500, 200, 50], r1d: [2, -1, 0, null], r5d: [4, -6, 1, 3], r1m: [8, -12, 2, 1],
            size: [3e11, 1e11, 2e11, null], above_ema50: [1, 0, 1, null], above_ema200: [1, 0, 0, null],
            fnet_1d: [5e10, -2e10, 0, null], fnet_5d: [1e11, -3e11, 2e10, null], fnet_1m: [null, null, null, null], fnet_3m: [1, -1, 2, null] },
  intraday: { '5m': { t: [1794535200, 1794535500], c: [101, 103] }, '1h': { t: [1794189600, 1794535200], c: [99, 103] } },
};
const dates = ['2025-12-29', '2025-12-30', '2026-01-02', '2026-01-05', '2026-01-06'];
const series: Series = {
  schema: 1, dates, index: { IHSG: [100, 101, 102, null, 110], LQ45: [10, 10, 10, 10, 10] },
  sector: { Energy: [50, 50, 55, 60, 66], Financials: [20, 20, 19, 18, 18] },
  above_ema50: [10, 20, 30, 40, 50], above_ema200: [5, 5, 5, 5, 5], breadth_n: dates.map(() => [4, 4] as [number, number]),
  flow: { dates: ['2026-01-02'], foreign_buy: [1], foreign_sell: [1], turnover: [2] },
};

describe('labels and numbers', () => {
  it('names dates and WIB times', () => {
    expect(M.dateLabel('2026-11-13', true)).toBe('Fri 13 Nov');
    expect(M.wibTime(1794535200)).toBe('09:00');          // 02:00 UTC
    expect(M.wibDate(1794535200)).toBe('2026-11-13');
  });
  it('writes rupiah in T, B and M with a real minus', () => {
    expect(M.rp(8.153e12)).toBe('Rp 8.15T');
    expect(M.rp(116.6e9, true)).toBe('+Rp 116.6B');
    expect(M.rp(-2.81e12, true)).toBe('−Rp 2.81T');
    expect(M.amount(-523e9)).toBe('−523B');
    expect(M.pct(-1.234)).toBe('−1.23%');
    expect(M.rp(null)).toBe('—');
  });
  it('names the size basis the files carry, so a market cap source needs no page change', () => {
    expect(M.sizeLabel('adv20_value')).toBe('20-day average value traded');
    expect(M.sizeLabel('market_cap')).toBe('market cap');
    expect(M.sizeLabel('free_float_cap')).toBe('free float cap');
  });
});

describe('stocks, universes and the market map', () => {
  const R = M.rows(meta, day);
  it('joins the day rows with the meta names and sectors', () => {
    expect(R.map(r => `${r.t}:${r.sector}:${r.ret['1D']}`)).toEqual(['AAAA:Financials:2', 'BBBB:Financials:-1', 'CCCC:Energy:0', 'DDDD:Other:null']);
  });
  it('skips a position the meta does not hold instead of making a row without a ticker', () => {
    const other = { ...day, stocks: { ...day.stocks, i: [0, 9] } };
    expect(M.rows(meta, other).map(r => r.t)).toEqual(['AAAA']);
  });
    it('defaults to the benchmark list and offers every stock first', () => {
    const U = M.universes(meta);
    expect(U.map(u => `${u.key}:${u.kind}`)).toEqual(['all:Market', 'INDEX:1:Index', 'KONGLO:2:Group']);
    expect(M.defaultUniverse(meta)).toBe('INDEX:1');
    expect(R.filter(M.inUniverse(U[1])).map(r => r.t)).toEqual(['AAAA', 'CCCC']);
    expect(M.defaultUniverse({ ...meta, lists: [] })).toBe(M.ALL);
  });
  it('groups sized stocks by sector, weights returns by size and sums foreign net', () => {
    const g = M.mapGroups(R, 'perf', '5D');
    expect(g.map(x => x.name)).toEqual(['Financials', 'Energy']);           // DDDD has no size: not drawn
    expect(g[0].size).toBe(4e11);
    expect(g[0].agg).toBeCloseTo((3e11 * 4 + 1e11 * -6) / 4e11);
    expect(M.mapGroups(R, 'fb', '5D')[0].agg).toBe(1e11 - 3e11);
    expect(M.mapGroups(R, 'fb', '1M')[0].agg).toBeNull();                    // no figure is not zero
  });
  it('colours with the design steps and scales', () => {
    expect(M.tile(R[0], 'perf', '1D').col[0]).toBe('var(--green-500)');      // +2% in 1D
    expect(M.tile(R[0], 'perf', '1M').col[0]).toBe('var(--green-500)');      // +8% / 4
    expect(M.tile(R[1], 'fb', '5D').col[0]).toBe('var(--red-300)');          // -300 bn / (120 bn x sqrt 5) = -1.12
    expect(M.tile(R[2], 'perf', '1D').col[0]).toBe('var(--ov-flat)');        // 0%: the neutral step
  });
  it('lays a squarified treemap whose areas follow the values', () => {
    const rects = M.squarify([{ v: 6, item: 'a' }, { v: 3, item: 'b' }, { v: 1, item: 'c' }], 0, 0, 100, 50);
    const area = (k: string) => rects.filter(r => r.item === k).reduce((s, r) => s + r.w * r.h, 0);
    expect(area('a') + area('b') + area('c')).toBeCloseTo(5000);
    expect(area('a')).toBeCloseTo(3000);
    expect(rects.every(r => r.x >= -1e-9 && r.y >= -1e-9 && r.x + r.w <= 100 + 1e-9 && r.y + r.h <= 50 + 1e-9)).toBe(true);
    expect(M.squarify([], 0, 0, 10, 10)).toEqual([]);
  });
  it('picks movers and the largest net foreign buyers and sellers', () => {
    const m = M.movers(R, '5D', 2);
    expect(m.up.map(r => r.t)).toEqual(['AAAA', 'DDDD']);
    expect(m.down.map(r => r.t)).toEqual(['BBBB']);
    expect([m.count, m.ups, m.downs]).toEqual([4, 3, 1]);
    const f = M.foreignTop(R, '1D');
    expect(f.buy.map(r => r.t)).toEqual(['AAAA']);
    expect(f.sell.map(r => r.t)).toEqual(['BBBB']);                            // zero is neither
  });
});

describe('series up to the chosen date', () => {
  it('starts YTD at the last session of the previous year and clamps a long window', () => {
    expect(M.periodStart(dates, 4, 'YTD')).toBe(1);                           // 30 Dec 2025
    expect(M.periodStart(dates, 4, '20D')).toBe(0);
    expect(M.periodStart(dates, 4, 2)).toBe(2);
  });
  it('computes cumulative returns and keeps a missing close as a gap', () => {
    expect(M.cumulative(series.index.IHSG, 1, 4).map(v => (v == null ? null : +v.toFixed(4)))).toEqual([0, 0.9901, null, 8.9109]);
    const s = M.sectorLines(series, 'IHSG', 4, 'YTD');
    expect(s.lines.map(l => l.name)).toEqual(['Energy', 'Financials']);
    expect(s.lines[0].last).toBeCloseTo(32);
    expect(s.market[s.market.length - 1]).toBeCloseTo(8.9109, 3);
  });
  it('finds the series end of a date and the flow index of a broker date', () => {
    expect(M.seriesEnd(series, '2026-01-05')).toBe(3);
    expect(M.seriesEnd(series, '2026-01-04')).toBe(2);
    expect(M.flowEnd(series, '2026-01-02')).toBe(0);
    expect(M.flowEnd(series, null)).toBe(-1);
  });
  it('draws IHSG 1D against the prior close and 1M from the daily closes', () => {
    const d1 = M.ihsgChart(series, day, 'IHSG', 4, '1D');
    expect([d1.ref, d1.prior, d1.pts.length, d1.pts[0].tip]).toEqual([100, true, 2, '13 Nov, 09:00 WIB']);
    const m1 = M.ihsgChart(series, day, 'IHSG', 4, '1M');
    expect(m1.pts.map(p => p.v)).toEqual([100, 101, 102, 110]);               // the missing close is skipped
    expect([m1.ref, m1.prior]).toEqual([100, false]);
    expect(M.ihsgChart(series, { ...day, intraday: {} }, 'IHSG', 4, '5D').pts).toEqual([]);
  });
});
