/* EXEC-SECTOR-ANALYSIS check 1 (2026-11-27): the findings of the five checkers (verification/sector_analysis/check1/,
   FIXES.md) that the page's arithmetic and words decide, each keyed by its run and id, on the made-up fixture files and
   their edge cases (tests/fixture/make.mjs edgeCases). The layout and the interactions are tests/look/check1.mjs. */
import { describe, expect, it } from 'vitest';
import * as M from '../src/model.ts';
import { calc, cloneState, DEFAULT_STATE, type Ctx, type StocksState } from '../src/ctx.ts';
import { compare, drillRows } from '../src/cards/rs.ts';
import { lineStyle, mmReading } from '../src/cards/ov.ts';
import { pmT } from '../src/cards/pm.ts';
import { audOf, brN } from '../src/cards/br.ts';
import { rotA } from '../src/cards/rot.ts';
import { labelInk } from '../src/charts.ts';
import { readHash } from '../src/app.ts';
import { W } from '../src/words.ts';
// @ts-ignore: a plain module of the tests
import { makeFiles } from './fixture/make.mjs';

const F = makeFiles(), meta = F.files['sector-meta'], series = F.files['sector-series'];
const data = (d = meta.dates.at(-1)) => M.makeData(meta, series, F.files[`sector-day-${d}`]);
function ctx(D = data(), S = cloneState(DEFAULT_STATE)): Ctx {
  return {
    D, S, win: false, example: false, lock(n, t = true) { S.pin = t && n === S.pin ? null : n }, redraw() {}, terminal() {},
    stocks: (sector: string): StocksState => ({ state: 'ready', file: F.files[`sector-stocks-${D.meta.sectors.find(s => s.name === sector)!.index.toLowerCase()}`] }),
  };
}

describe('agents_20261127-sector-data', () => {
  it('D-2 (with brdt BD-6): 1D advancers, unchanged and decliners are Feature 08\'s, as the Overview', () => {
    const c = ctx(), b = c.D.breadth('IHSG')!, E = c.D.E, a = audOf(c, 'IHSG', 'r1d');
    expect([a.u, a.f, a.d]).toEqual([b.adv[E], b.unch[E], b.dec[E]]);
    // the day file cannot place a stock that did not trade on the previous session (XTHN): the old count lost it
    const old = M.aud(c.D.rows.map(r => r.r1d));
    expect(old.N).toBeLessThan(a.N);
    for (const s of c.D.names) { const x = audOf(c, s, 'r1d'), bs = c.D.breadth(s)!; expect([x.u, x.f, x.d]).toEqual([bs.adv[E], bs.unch[E], bs.dec[E]]) }
    // the window of the card: the card's counts, and the stocks it cannot place named
    const d = brN.detail!(c);
    expect(d.sub).toBe(W.brN.dSub(a.u, a.f, a.d));
    expect(d.note).toBe(W.brN.dNote(a.N - old.N));
    // 1W and 1M: the stocks without the return are said, not dropped silently
    c.S.adH = 'r5d';
    const w = audOf(c, 'IHSG', 'r5d');
    expect(w.of).toBe(c.D.rows.length);
    expect(W.brN.den('1W', w.N, w.of)).toMatch(w.N < w.of ? /of \d+ stocks have a 1W return/ : /every stock/);
    expect(W.brT.cellTip(3, 9, 33.3, 10, '1W')).toContain('1 of the 10 stocks have no 1W return');
  });
  it('D-3: "Days" counts market sessions from "Since", so the two agree for a thinly traded stock', () => {
    const D = data(), r = D.rows.find(x => x.t === 'XTHN')!;
    expect(r.since50).not.toBeNull();
    const own = r.days50 as number, k = D.dates.indexOf(r.since50 as string), st = M.statusSessions(D.dates, D.E, r.since50, own)!;
    expect(st).toEqual({ n: D.E - k + 1, more: false });
    expect(st.n).toBeGreaterThan(own);                                   // its own bars are fewer than the market's sessions
    expect(M.statusSessions(D.dates, D.E, null, 300)).toEqual({ n: 300, more: true });             // at the cap: 300+
    expect(M.statusSessions(D.dates, D.E, '2000-01-03', 120)).toEqual({ n: 300, more: true });     // before the series
    expect(W.brD.daysTip('EMA50')).toMatch(/^Market sessions/);
  });
  it('D-1, D-4: where industry rows sit beside sector rows the page says what each is and the industry scale', () => {
    const c = ctx(), { IND } = drillRows(c), n = IND.filter(u => u.rt != null).length;
    const t = W.rsD.indNote(c.D.weightLabel, n);
    expect(t).toContain('official IDX sector index'); expect(t).toContain('20-day average traded value'); expect(t).toContain(`among all ${n} industries`);
    expect(W.rsD.tips.rt).toMatch(/an industry among all industries/);
  });
  it('D-7: the market rows count the stocks without an IDX-IC sector, and say so', () => {
    const D = data();
    expect(D.other).toBe(3);
    expect(D.names.reduce((s, n) => s + D.members(n).length, 0) + D.other).toBe(D.members('IHSG').length);
    expect(W.brT.other('IHSG', D.other)).toBe('IHSG (all) also counts 3 stocks without an IDX-IC sector, which no sector row shows');
  });
  it('D-8: an industry level carries over the dates without one (the contract), so a return across them is known', () => {
    const D = data(), raw = series.industry['Alternative Energy Equipment'].level as M.N[], gap = raw.findIndex((v, i) => i > 0 && v == null);
    expect(gap).toBeGreaterThan(0);
    expect(M.ret(raw, D.E, D.E - gap)).toBeNull();                       // the base on a date without a level
    expect(M.ret(D.indLevel('Alternative Energy Equipment'), D.E, D.E - gap)).not.toBeNull();
    expect(M.carryLevels([null, 100, null, null, 101])).toEqual([null, 100, 100, 100, 101]);
  });
});

describe('agents_20261127-sector-ovrs', () => {
  it('OR-1: the Momentum corner names follow which axis holds the shorter horizon', () => {
    const c = ctx();
    const a = mmReading(c, '3M', '1M');                                   // X long, Y short
    expect(a.name(-1, 1)).toBe('Turning up'); expect(a.name(1, -1)).toBe('Turning down'); expect(a.corner).toBe('Top left');
    const b = mmReading(c, '1W', '1M');                                   // X short, Y long: the finding's case
    expect(b.name(1, -1)).toBe('Turning up'); expect(b.name(-1, 1)).toBe('Turning down'); expect(b.corner).toBe('Bottom right');
    expect(W.mm.foot(b.corner, false)).toContain('bottom right = turning up');
    expect(M.hzRead(1, -1, 20, 20)).toBe('xonly');                        // the same length: neutral
  });
  it('OR-6 (with brdt BD-7): the Custom popover prints the range the card prints', () => {
    const D = data(), r = M.checkRange(D.dates, D.E, D.dates[D.E - 59], D.dates[D.E])!;
    const sp = calc(D).span('C', { a: D.dates[D.E - 59], b: D.dates[D.E] });
    expect(r.msg).toBe(`${M.rangeLabel(D.dates[sp.b], D.dates[sp.e])} · ${W.sessions(sp.e - sp.b)}`);   // the card's footer
    const lv = M.checkRange(D.dates, D.E, D.dates[D.E - 59], D.dates[D.E], { level: true });
    expect(lv.msg.startsWith(M.dateLabel(D.dates[D.E - 59]))).toBe(true);                               // a level: its first session
  });
  it('OR-9: plain wording', () => {
    expect(W.rc.ex('Financials', -11.3, 10.09, -12, 'IHSG')).toMatch(/^Financials returned −11\.3%/);
    expect(W.rsA.read(true, 'IHSG', 5)).not.toMatch(/chosen in this window/);
    expect(W.rsB.note('Thu 19 Nov 2026', 5)).not.toMatch(/vs the date shown/);
  });
  it('OR-10: lines past the sixth colour are dashed', () => {
    expect(lineStyle(0).dash).toBe(false); expect(lineStyle(6).dash).toBe(true); expect(lineStyle(6).c).toBe(lineStyle(0).c);
  });
});

describe('agents_20261127-sector-rotpm', () => {
  it('RP-1: a Custom range before the data is refused; a stored one is clamped visibly, never replaced silently or named "C"', () => {
    const D = data(), K = calc(D);
    expect(M.checkRange(D.dates, D.E, '2000-01-03', D.dates[100]).msg).toMatch(/^Pick dates from/);
    const sp = K.span('C', { a: '2000-01-03', b: D.dates[100] });
    expect(sp.custom).toBe(true); expect(sp.b).toBe(0); expect(sp.note).toBe(W.range.clampStart(M.dateLabel(D.dates[0], false, true)));
    const gone = K.span('C', { a: '2031-01-02', b: '2031-02-02' }, '1M');
    expect(gone).toMatchObject({ custom: false, key: '1M', note: W.range.none('1M') });
    for (const s of [sp, gone, K.span('C', null), K.span('3M', null)]) expect(K.plabel(s)).not.toBe('C');
    // Beta and correlation: the stored range's own window, or 120D with the note, never "Custom" over 120D
    const c = ctx(); c.S.btW = 'C'; c.S.btR = { a: '2000-01-03', b: D.dates[D.E] };
    expect(pmT.detail!(c).sub).toContain(`β ${D.E}D`);
    c.S.btR = { a: '2031-01-02', b: '2031-02-02' };
    expect(pmT.detail!(c).sub).toContain('β 120D');
  });
  it('RP-1, the same mechanism in Rank change: a stored compare date the page date cannot use shows 5D and says so', () => {
    const c = ctx(); c.S.rbK = 'C'; c.S.rbD = c.D.dates[c.D.E - 30];
    expect(compare(c)).toEqual({ i: c.D.E - 30, custom: true, note: null });
    c.S.rbD = '2031-01-02';
    expect(compare(c)).toMatchObject({ i: c.D.E - 5, custom: false, note: W.range.noDate('2\u00a0Jan\u00a02031') });
  });
  it('RP-5: one outlier does not squeeze the stock quadrant\'s axis', () => {
    const v = [-56, ...Array.from({ length: 30 }, (_, i) => -10 + i * 0.6)];
    const [lo] = M.axisRange(v);
    expect(lo).toBeGreaterThan(-56);
    expect(M.axisRange([-56, 1, 2])[0]).toBe(-56);                       // too few values: every value inside
  });
  it('RP-6: a date of another year than the page\'s carries its year', () => {
    expect(M.dateIn('2025-11-11', '2026-11-26')).toBe('11\u00a0Nov\u00a02025'); expect(M.dateIn('2026-05-04', '2026-11-26')).toBe('4\u00a0May');
    const c = ctx(); c.S.rotK = c.D.dates[0];                              // before the strip: its first possible week
    expect(rotA.detail!(c).title).toMatch(/20\d\d$/);
    expect(rotA.detail!(c).title).not.toContain(M.dateLabel(c.D.dates[c.D.E]));
  });
  it('RP-9: no heading reuses a quadrant\'s name', () => {
    for (const h of M.HEADINGS) expect(M.QUADS as readonly string[]).not.toContain(h);
    expect(M.heading(225)).toBe('Both down');
  });
});

describe('agents_20261127-sector-brdt and agents_20261127-sector-mobex', () => {
  it('BD-5: the last of two quick picks wins', async () => {
    const take = M.lastWins(), slow = new Promise(r => setTimeout(() => r('old'), 30)), a = take(slow), b = take(Promise.resolve('new'));
    expect(await b).toEqual({ stale: false, value: 'new' });
    expect(await a).toEqual({ stale: true, value: 'old' });
  });
  it('BD-9 (with mobex MX-6): the date menu\'s arrow keys, Home and End', () => {
    expect(M.menuStep(20, 0, 'ArrowDown')).toBe(1); expect(M.menuStep(20, 0, 'ArrowUp')).toBe(19);
    expect(M.menuStep(20, 7, 'Home')).toBe(0); expect(M.menuStep(20, 7, 'End')).toBe(19); expect(M.menuStep(20, 7, 'a')).toBeNull();
  });
  it('BD-10: the picked date is kept in the address', () => {
    const S = cloneState(DEFAULT_STATE);
    readHash(S, '#' + encodeURIComponent(JSON.stringify({ tab: 'br', date: '2026-11-12' })));
    expect(S.date).toBe('2026-11-12'); expect(S.tab).toBe('br');
  });
  it('BD-12: a distance just under its EMA keeps its minus sign', () => {
    expect(M.pctSigned(-0.03)).toBe('−0.0%'); expect(M.pctSigned(0.03)).toBe('+0.0%'); expect(M.pctSigned(0)).toBe('0.0%'); expect(M.pctSigned(256.71)).toBe('+256.7%');
  });
  it('MX-5 (the page\'s own part): an end label is the line\'s colour mixed with the text colour', () => {
    expect(labelInk('var(--c6)')).toBe('color-mix(in srgb,var(--c6) 55%,var(--text))'); expect(labelInk(undefined)).toBe('var(--text)');
  });
});
