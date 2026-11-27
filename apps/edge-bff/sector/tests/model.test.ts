/* EXEC-SECTOR-ANALYSIS S4: the page's arithmetic (src/model.ts) and the figures the cards compute from the files (their
   detail tables, DOM-free), on hand-made numbers and on the made-up fixture files (tests/fixture/make.mjs). */
import { describe, expect, it } from 'vitest';
import * as M from '../src/model.ts';
import { calc, cloneState, DEFAULT_STATE, shown, type Ctx, type StocksState } from '../src/ctx.ts';
import { drillRows, rsA, rsB, rsL, rsD } from '../src/cards/rs.ts';
import { mkCard, hxCard, rcCard } from '../src/cards/ov.ts';
import { pmT, pmS } from '../src/cards/pm.ts';
import { brN, brT, brH, brA } from '../src/cards/br.ts';
import { rotA, rotB } from '../src/cards/rot.ts';
// @ts-ignore: a plain module of the tests
import { makeFiles } from './fixture/make.mjs';

const F = makeFiles();
const day = (d?: string) => F.files[`sector-day-${d || F.files['sector-meta'].dates.at(-1)}`];
const data = (d?: string) => M.makeData(F.files['sector-meta'], F.files['sector-series'], day(d));
function ctx(D = data(), S = cloneState(DEFAULT_STATE)): Ctx {
  return {
    D, S, win: false, example: false,
    lock(n, t = true) { S.pin = t && n === S.pin ? null : n }, redraw() {}, terminal() {},
    stocks: (sector: string): StocksState => { const ix = D.meta.sectors.find(s => s.name === sector)!.index; return { state: 'ready', file: F.files[`sector-stocks-${ix.toLowerCase()}`] } },
  };
}

describe('formats (en-US, U+2212 minus)', () => {
  it('writes percent, points, rupiah and dates', () => {
    expect(M.pct(1.234)).toBe('+1.23%'); expect(M.pct(-0.004)).toBe('0.00%'); expect(M.pct(null)).toBe('—');
    expect(M.pp(-2.5, 1)).toBe('−2.5 pp'); expect(M.ppx(0.04, 1)).toBe('0.0'); expect(M.fnum(-0.142)).toBe('−0.14');
    expect(M.rp(8.15e12)).toBe('Rp 8.15T'); expect(M.rp(116.6e9)).toBe('Rp 116.6B');
    expect(M.weightText('adv20_value', 2e9)).toBe('Rp 2.0B/day'); expect(M.weightText('market_cap', 2e12)).toBe('Rp 2.00T');
    expect(M.dateLabel('2026-11-17', true)).toBe('Tue 17 Nov');
    expect(M.rangeLabel('2025-10-24', '2026-11-17')).toBe('24 Oct 2025 – 17 Nov 2026');   // D11: years across years
    expect(M.tagDate('2026-11-16')).toBe("Mon 16 Nov '26");
  });
});

describe('periods (decision E: as the Overview)', () => {
  const dates = ['2025-12-29', '2025-12-30', '2026-01-02', '2026-01-05', '2026-01-06', '2026-01-07'];
  it('counts sessions and starts YTD at the last session of the previous year', () => {
    expect(M.PERIODS).toMatchObject({ '1W': 5, '1M': 20, '3M': 60, '6M': 120, '1Y': 252 });
    expect(M.periodStart(dates, 5, 'YTD')).toBe(1);
    expect(M.periodStart(dates, 5, 3)).toBe(2);
    expect(M.periodStart(dates, 2, 10)).toBe(0);
    expect(M.ytdBase(['2026-01-02', '2026-01-05'], 1)).toBe(0);              // no previous year in the data: the first
  });
  it('anchors a Custom range on the session before its first day and caps it at a year', () => {
    const D = F.files['sector-series'].dates as string[], E = D.length - 1;
    const r = M.checkRange(D, E, D[10], D[40]);
    expect(r.ok).toBe(true); expect(r.span).toEqual({ first: 10, last: 40, base: 9, n: 31 });
    expect(r.msg).toBe(`${M.rangeLabel(D[9], D[40])} · 31 sessions`);          // the card's own label: from the base close (OR-6)
    expect(M.checkRange(D, E, D[1], D[E]).msg).toMatch(/at most 1 year/);
    expect(M.checkRange(D, E, D[0], D[40]).msg).toMatch(/^Pick dates from/);       // RP-1: before the first usable date, refused
    expect(M.checkRange(D, E, D[40], D[10]).ok).toBe(false);
    expect(M.checkRange(D, E, D[10], D[12]).msg).toMatch(/at least 5/);
    expect(M.checkRange(D, E, D[10], D[160], { max: 130, maxWhy: 'max 26 weeks' }).msg).toBe('max 26 weeks');   // D09
  });
});

describe('returns, ranks and ratings', () => {
  const a = [100, 110, 99, null, 120];
  it('measures returns over sessions and from a base, null where a close is missing', () => {
    expect(M.ret(a, 1, 1)).toBeCloseTo(10); expect(M.ret(a, 3, 1)).toBeNull(); expect(M.ret(a, 1, 5)).toBeNull();
    expect(M.retAt(a, 0, 4)).toBeCloseTo(20); expect(M.path(a, 0, 2).map(v => v && +v.toFixed(2))).toEqual([0, 10, -1]);
    expect(M.maxDrawdown(a, 0, 4)).toBeCloseTo(-10);
  });
  it('ranks highest first with a missing value last, and rates 1-99', () => {
    expect(M.rankOf(['a', 'b', 'c'], n => ({ a: 1, b: null, c: 5 })[n] as M.N)).toEqual({ c: 1, a: 2, b: 3 });
    const rows = [{ v: 3 }, { v: 1 }, { v: 2 }, { v: null }] as any[];
    M.rate(rows, 'v');
    expect(rows.map(r => r.rt)).toEqual([99, 1, 50, null]);
    expect(M.momTag(1, 0, 20)![0]).toBe('Gaining'); expect(M.momTag(0, 4, 20)![0]).toBe('Fading'); expect(M.momTag(1, 4, 20)![0]).toBe('Steady');
    expect(M.streak([1, -1, 2, 3])).toBe(2); expect(M.streak([1, -2, -3])).toBe(-2);
    expect(M.weekEnds(20, 3)).toEqual([10, 15, 20]);
  });
});

describe('the rotation map (relative strength and momentum, the prototype formula D11)', () => {
  it('is 100 when the sector moves with the market, and reads the quadrant and the move', () => {
    const ih = Array.from({ length: 40 }, (_, i) => 100 + i), same = ih.map(v => v * 2);
    const g = M.rotation(same, ih);
    expect(g.rs[18]).toBeNull(); expect(g.rs[19]).toBeCloseTo(100); expect(g.mom[24]).toBeCloseTo(100); expect(g.mom[23]).toBeNull();
    const up = ih.map((v, i) => v * (1 + i * 0.01)), gu = M.rotation(up, ih);
    expect(gu.rs[39]).toBeGreaterThan(100);
    expect(M.quad(101, 101)).toBe('Leading'); expect(M.quad(101, 99)).toBe('Weakening'); expect(M.quad(99, 101)).toBe('Improving'); expect(M.quad(99, 99)).toBe('Lagging');
    const mv = M.move({ rs: [100, null, 101], mom: [100, null, 101] }, 2, 2)!;
    expect(mv.deg).toBeCloseTo(45); expect(mv.sp).toBeCloseTo(Math.SQRT2); expect(M.heading(mv.deg)).toBe('Both up');
    expect(M.clockwise('Lagging', 'Improving')).toBe(true); expect(M.clockwise('Leading', 'Lagging')).toBe(false);
  });
});

describe('pairs: spread, correlation, beta, the ratio band', () => {
  it('computes correlation and beta from daily returns (population, as logic.js L650-654)', () => {
    const b = [100, 101, 99, 102, 103, 101, 104], a = b.map((v, i) => 50 * (1 + 2 * (v / b[0] - 1)) + (i ? 0 : 0));
    const ra = M.dailyRets(a, 0, 6), rb = M.dailyRets(b, 0, 6);
    expect(M.corr(rb, rb)).toBeCloseTo(1);
    expect(M.beta(rb.map(x => (x as number) * 2), rb)).toBeCloseTo(2);
    expect(M.corr(ra, rb)).toBeGreaterThan(0.99);
    expect(M.corr([1, null, 2], [1, 2, null])).toBeNull();                     // fewer than 3 pairs
  });
  it('rebases the ratio to 100 with its moving average and band, and its z', () => {
    const A = Array.from({ length: 30 }, (_, i) => 100 + i), B = A.map(() => 100);
    const r = M.ratioBand(A, B, 10, 29, 5);
    expect(r.v[0]).toBeCloseTo(100); expect(r.v.length).toBe(20); expect(r.up[0]! > r.m[0]!).toBe(true); expect(r.z[19]).toBeGreaterThan(1);
    expect(M.pairZ(A, B, 5, 29)).toBeCloseTo(r.z[19] as number);
  });
});

describe('breadth from the counts', () => {
  it('shares, advancers and decliners (a stock without the value is not counted)', () => {
    expect(M.breadthLine({ members: [], n50: [10, 0], a50: [4, 0], n200: [8, 5], a200: [2, 5], adv: [], unch: [], dec: [] }, 50)).toEqual([40, null]);
    expect(M.aud([1, -1, 0, null, 2])).toEqual({ u: 2, f: 1, d: 1, N: 4 });
    expect(M.flagShare([1, 0, null, 1])).toEqual({ a: 2, n: 3, p: (2 / 3) * 100 });
  });
  it('the day file gives the same market share as the series counts (the contract: Feature_08 = the Overview)', () => {
    const D = data(), b = D.breadth('IHSG')!, s = M.flagShare(D.rows.map(r => r.e50));
    expect(s.a).toBe(b.a50[D.E]); expect(s.n).toBe(b.n50[D.E]);
    const sec = D.names[0], bs = D.breadth(sec)!, ss = M.flagShare(D.members(sec).map(r => r.e200));
    expect([ss.a, ss.n]).toEqual([bs.a200[D.E], bs.n200[D.E]]);
  });
});

describe('the files arranged for the cards (model.makeData)', () => {
  it('reads every sector, short names, the periods and the market rows', () => {
    const D = data();
    expect(D.names.length).toBe(11); expect(D.E).toBe(D.dates.length - 1); expect(D.market).toBe('IHSG');
    expect(D.short('Consumer Non-Cyclicals')).toBe('Non-Cyc'); expect(D.abbr('Financials')).toBe('Fin'); expect(D.P('1M')).toBe(20); expect(D.P('5D')).toBe(5);
    expect(D.members('IHSG').length).toBe(D.rows.length);
    expect(D.rows.some(r => r.sec === 'Other')).toBe(true);                       // "Other" counts in the market only
    expect(D.other).toBeGreaterThan(0);
    expect(D.names.reduce((n, s) => n + D.members(s).length, 0)).toBe(D.rows.length - D.other);
    expect(D.weightLabel).toBe('20-day average traded value');
    const older = data(F.files['sector-meta'].dates[0]);
    expect(older.E).toBe(older.dates.indexOf(F.files['sector-meta'].dates[0]));   // an earlier date moves every card's end
  });
});

describe('the cards\' figures', () => {
  it('excess returns and the KPI strongest sector use the 1W of 5 sessions', () => {
    const c = ctx(), K = calc(c.D), w = c.D.P('1W');
    const best = [...c.D.names].sort((a, b) => (K.rr(b, w) ?? -1e9) - (K.rr(a, w) ?? -1e9))[0];
    expect(K.strongest).toBe(best); expect(shown(c)).toBe(best);
    c.S.pin = c.D.names[3]; expect(shown(c)).toBe(c.D.names[3]);
    expect(K.span('YTD', null).b).toBe(c.D.ytd()); expect(K.span('3M', null)).toMatchObject({ b: c.D.E - 60, e: c.D.E, custom: false, key: '3M', note: null });
  });
  it('the drill-down has its industry rows from series.industry, rated among industries (defect D03)', () => {
    const c = ctx(), { SEC, IND } = drillRows(c);
    expect(SEC.length).toBe(11); expect(IND.length).toBe(F.files['sector-meta'].industries.length);
    const x = IND[0], lv = c.D.series.industry[x.nm].level;
    expect(x.rM).toBeCloseTo(M.ret(lv, c.D.E, 20) as number);
    expect(IND.every(u => u.rt == null || (u.rt >= 1 && u.rt <= 99))).toBe(true);
    expect(IND.filter(u => u.rt === 99).length).toBe(1);
    expect(x.quad).not.toBeUndefined();
  });
  it('the market map\'s industries: weight share and weighted 5D (decision D1: the file\'s weight)', () => {
    const c = ctx(), d = mkCard.detail!(c), nm = shown(c), ms = c.D.members(nm);
    expect(d.rows.reduce((s, r) => s + r.n, 0)).toBe(ms.length);
    expect(d.rows.reduce((s, r) => s + r.sh, 0)).toBeCloseTo(100);
    const r = d.rows[0], k = ms.filter(x => (x.ind || 'Unclassified') === r.name && x.r5d != null && (x.w ?? 0) > 0);
    expect(r.r5).toBeCloseTo(k.reduce((s, x) => s + (x.w as number) * (x.r5d as number), 0) / k.reduce((s, x) => s + (x.w as number), 0));
    expect(d.read).toContain('20-day average traded value');
  });
  it('the stock lines and the stocks\' beta come from sector-stocks (G1, G9), not seeded values', () => {
    const c = ctx(), nm = c.D.names[0], ix = c.D.info[nm].index; c.S.pin = nm; c.S.pmA = nm; c.S.pmB = c.D.names[1];
    const f = F.files[`sector-stocks-${ix.toLowerCase()}`];
    expect(f.dates).toEqual(c.D.dates);
    const d = pmT.detail!(c), r = d.rows.find(x => x.b != null)!, k = f.ticker.indexOf(r.t);
    const exp = M.beta(M.dailyRets(f.close[k], c.D.E - 120, c.D.E), M.dailyRets(c.D.IH, c.D.E - 120, c.D.E));
    expect(r.b).toBeCloseTo(exp as number);
    expect(rsL.detail!(c).rows.length).toBeLessThanOrEqual(10);
  });
  it('breadth and day figures are the day file\'s (G6, G8): close, volume, distances', () => {
    const c = ctx(), dn = brN.detail!(c), row = dn.rows[0], src = c.D.rows.find(x => x.t === row.t)!;
    expect(row.close).toBe(src.close); expect(row.vol).toBe(src.vol);
    const da = brA.detail!(c);
    expect(da.rows.every(r => r.d50 == null || r.a == null || (r.d50 > 0) === (r.a === 1) || r.d50 === 0)).toBe(true);
    const dt = brT.detail!(c), mk = dt.rows[0], line = M.breadthLine(c.D.breadth('IHSG'), 50);
    expect(mk.a5).toBeCloseTo((line[c.D.E] as number) - (line[c.D.E - 5] as number));
    const dh = brH.detail!(c);
    expect(dh.rows.length).toBe(60);
  });
  it('the rotation detail\'s speed follows the chosen window (defect N01)', () => {
    const c = ctx(), K = calc(c.D);
    const sp = (p: number) => c.D.names.map(n => M.move(K.rot[n], c.D.E, p)!.sp);
    expect(sp(5)).not.toEqual(sp(20));
    expect(rotA.detail!(c).rows.length).toBe(11);
    expect(rotB.detail!(c).rows.every(r => r.f !== r.t)).toBe(true);
  });
  it('the detail examples read what is computed (W1, W2): the chosen window and compare date', () => {
    const c = ctx(); c.S.rsN = 10; c.S.rbK = '10';
    const a = rsA.detail!(c), ex = a.ex!(a.rows[0]);
    expect(ex).toContain('10D'); expect(a.read).toMatch(/ranks the 10D window, the one picked on the card/);
    const b = rsB.detail!(c);
    expect(b.read).toContain(M.dateLabel(c.D.dates[c.D.E - 10]));
    expect(rsD.detail!(c).rows.length).toBe(c.D.members(shown(c)).length);
    expect(hxCard.detail!(c).rows.every(r => r.ar == null || (r.ar >= 1 && r.ar <= 11))).toBe(true);
    expect(rcCard.detail!(c).rows[0].nm).toBe('IHSG');
  });
  it('stretched pairs read leader over 1M first (defect D19)', () => {
    const c = ctx(), d = pmS.detail!(c);
    expect(d.rows.length).toBe(55);
    expect(d.rows.every(r => r.s1M == null || r.s1M >= 0)).toBe(true);
  });
});
