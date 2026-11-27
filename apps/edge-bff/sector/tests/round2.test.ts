/* EXEC-SECTOR-ANALYSIS visual round 2 (2026-11-27, the user's decisions V1-V10 and UD76-UD79 in EXEC.md; the record:
   verification/sector_analysis/round2/CHANGES.md): what the page's arithmetic, state and wiring decide, item by item, on
   the made-up fixture files. The layout and the clicks are tests/look/round2.mjs. */
import { describe, expect, it } from 'vitest';
import * as M from '../src/model.ts';
import { cloneState, DEFAULT_STATE, type Ctx, type StocksState } from '../src/ctx.ts';
import { CORR_CAP, FLAT, STEPS, corrHeat, heat, step } from '../src/ui.ts';
import { spans } from '../src/windows.ts';
import { hxCard, mkCard, mmCard, rcCard } from '../src/cards/ov.ts';
import { rsA, rsB, rsD, rsL, rsW } from '../src/cards/rs.ts';
import { rotA, rotB, rotC, rotD, tlGeom, tlPad } from '../src/cards/rot.ts';
import { clearPair, pair, pmM, pmR, pmS, pmT, setPair } from '../src/cards/pm.ts';
import { brA, brD, brH, brN, brT } from '../src/cards/br.ts';
import { colorOf } from '../../overview/src/model.ts';
import { W } from '../src/words.ts';
// @ts-ignore: a plain module of the tests
import { makeFiles } from './fixture/make.mjs';

const F = makeFiles(), meta = F.files['sector-meta'], series = F.files['sector-series'];
const data = (d = meta.dates.at(-1)) => M.makeData(meta, series, F.files[`sector-day-${d}`]);
function ctx(D = data(), S = cloneState(DEFAULT_STATE), win = false): Ctx & { draws: number } {
  const c = {
    D, S, win, example: false, draws: 0, lock(n: string, t = true) { S.pin = t && n === S.pin ? null : n; c.draws++ }, redraw() { c.draws++ }, terminal() {},
    stocks: (sector: string): StocksState => ({ state: 'ready', file: F.files[`sector-stocks-${D.meta.sectors.find(s => s.name === sector)!.index.toLowerCase()}`] }),
  };
  return c;
}
// the sources as text (Vite's ?raw), for what only the markup shows (the sheet's rules: round2.styles.test.mjs)
import uiSrc from '../src/ui.ts?raw';
import ovSrc from '../src/cards/ov.ts?raw';
import rsSrc from '../src/cards/rs.ts?raw';
import rotSrc from '../src/cards/rot.ts?raw';
import pmSrc from '../src/cards/pm.ts?raw';
import brSrc from '../src/cards/br.ts?raw';
const SRC: Record<string, string> = { 'ui.ts': uiSrc, 'cards/ov.ts': ovSrc, 'cards/rs.ts': rsSrc, 'cards/rot.ts': rotSrc, 'cards/pm.ts': pmSrc, 'cards/br.ts': brSrc };
const src = (f: string) => SRC[f];

describe('V6 / UD77 2A: the heat cells take the Overview\'s seven solid steps', () => {
  it('a step is the Overview\'s colorOf, signed, the flat cell its token', () => {
    const flat = (x: string) => (x === 'var(--ov-flat)' ? FLAT[0] : x === 'var(--ov-flat-fg)' ? FLAT[1] : x);
    for (const c of [-9, -3, -2.999, -1.5, -1.49, -0.5, -0.49, -0.01, 0, 0.01, 0.49, 0.5, 1.49, 1.5, 2.99, 3, 7]) {
      expect(step(c).map(flat), String(c)).toEqual(colorOf(c, true).map(flat));
    }
    expect(STEPS.map(s => s[0])).toEqual(['var(--red-600)', 'var(--red-500)', 'var(--red-300)', 'var(--sx-flat)', 'var(--green-300)', 'var(--green-500)', 'var(--green-600)']);
  });
  it('a column\'s cap maps onto the scale: the strongest step at the cap, the middle from half of it, light off the centre', () => {
    expect(heat(4, 4)).toBe('background:var(--green-600);color:#fff');
    expect(heat(2, 4)).toBe('background:var(--green-500);color:#fff');
    expect(heat(1.99, 4)).toBe('background:var(--green-300);color:var(--gray-900)');
    expect(heat(0.01, 4)).toBe('background:var(--green-300);color:var(--gray-900)');
    expect(heat(0, 4)).toBe('background:var(--sx-flat);color:var(--sx-flat-fg)');
    expect(heat(-4, 4)).toBe('background:var(--red-600);color:#fff');
    expect(heat(-2.5, 4)).toBe('background:var(--red-500);color:#fff');
    expect(heat(null, 4)).toBe('');
    // Breadth: centred at 50 %, the cap 50 points: 100 % the strongest, 75 % the middle, 51 % light, 50 % flat
    expect(heat(100, 50, 50)).toContain('--green-600'); expect(heat(75, 50, 50)).toContain('--green-500');
    expect(heat(51, 50, 50)).toContain('--green-300'); expect(heat(50, 50, 50)).toContain('--sx-flat'); expect(heat(20, 50, 50)).toContain('--red-500');
  });
  it('the correlation matrix: the same steps in navy and red on a fixed scale (0.4 / 0.8)', () => {
    expect(CORR_CAP).toBe(0.8);
    expect(corrHeat(0.85)).toContain('--navy-600'); expect(corrHeat(0.8)).toContain('--navy-600');
    expect(corrHeat(0.5)).toContain('--navy-500'); expect(corrHeat(0.39)).toContain('--navy-300');
    expect(corrHeat(-0.5)).toContain('--red-500'); expect(corrHeat(0)).toContain('--sx-flat');
  });
  it('no heat cell is blended transparent any more (the sheet: round2.styles.test.mjs)', () => {
    for (const f of ['ui.ts', 'cards/ov.ts', 'cards/rs.ts', 'cards/pm.ts', 'cards/br.ts']) expect(src(f), f).not.toMatch(/color-mix\(in srgb,var\(--(up|down|navy)\) \$\{/);
  });
});

describe('V3 V4 / UD76 2a, answer 3A: seven side-by-side windows end level', () => {
  it('the seven windows the user named fit their detail table; the others keep their layout', () => {
    expect([rcCard, mmCard, hxCard, rsA, rsB, rsW, rsL].map(x => !!x.fit)).toEqual(Array(7).fill(true));
    // left as they are (UD76): the market map, Pair matrix, Breadth and the Rotation windows not in items 5-7 (the map
    // itself follows its prototype, V8, and fits its readings in the Map view)
    expect([mkCard, rotB, rotC, rotD, pmM, pmR, pmT, pmS, brH, brT, brA, brN, brD, rsD].some(x => x.fit)).toBe(false);
    expect(rotA.fit).toEqual(['.rrg']);
  });
  it('the cumulative list gives the sheet its row count; the window fits to the list (V2)', () => {
    expect(src('cards/ov.ts')).toContain('<div class="ovx-cr" style="--n:${rows.length}">');
    expect(rcCard.fit).toEqual(['.ovx-cr', '.ovx-bl']);
  });
});

describe('V9: the stock momentum quadrant has no legend under its chart', () => {
  it('the card draws no legend and its words no longer carry its two lines', () => {
    const body = src('cards/rot.ts').split('export const rotC: Card')[1].split('detail(c): Detail')[0];
    expect(body).not.toContain('class="lgd"');
    expect((W.rotC as Record<string, unknown>).foot).toBeUndefined();
    expect(W.rotC.sub('IHSG', null)).toContain('size = weight');
  });
});

describe('C1: Rotation detail in a window (user 2026-11-27)', () => {
  it('the window shows the chosen sectors\' changes; none chosen: the locked one, else the first of the list', () => {
    const c = ctx(), d = rotB.detail!(c), names = new Set(d.rows.map(r => r.nm));
    expect(names.size).toBeLessThanOrEqual(1);
    c.S.pin = c.D.names[3];
    expect(new Set(rotB.detail!(c).rows.map(r => r.nm))).toEqual(new Set(rotB.detail!(c).rows.length ? [c.D.names[3]] : []));
    c.S.rotSel = [c.D.names[1], c.D.names[2]];
    const two = rotB.detail!(c);
    expect(two.rows.every(r => c.S.rotSel.includes(r.nm))).toBe(true);
    expect(two.sub).toContain(c.D.short(c.D.names[1])); expect(two.sub).toContain(c.D.short(c.D.names[2]));
    expect(two.cols.map(x => x.l)).toEqual([W.col.weekEnding, W.col.sector, W.col.from, W.col.to, W.col.path]);
    expect(two.rows.every(r => r.f !== r.t)).toBe(true);
  });
  it('"All columns" is the card\'s table with every column; a click there chooses the sector and returns to its changes', () => {
    const c = ctx(); c.S.rbV = 'all';
    const d = rotB.detail!(c);
    expect(d.rows.length).toBe(c.D.names.length);
    expect(d.cols.map(x => x.l)).toEqual([W.col.sector, W.rotB.now, W.rotB.prev('5D'), W.rotD.speed, W.rotB.last]);
    d.onRow!(d.rows[4]);
    expect(c.S.rotSel).toEqual([d.rows[4].nm]); expect(c.S.rbV).toBe('ch');
    c.S.rbV = 'all';
    rotB.detail!(c).onRow!(d.rows[6], { ctrlKey: true } as MouseEvent);              // Ctrl or Cmd adds, the view stays
    expect(c.S.rotSel.sort()).toEqual([d.rows[4].nm, d.rows[6].nm].sort()); expect(c.S.rbV).toBe('all');
  });
  it('the window layout is the C1 one, drawn by its own window function', () => {
    expect(rotB.layout).toBe('c1');
    expect(src('cards/rot.ts')).toMatch(/if \(c\.win\) \{ rbWindow\(el, c, rows, prev\); return \}/);
  });
});

describe('V7 answers: the Stretched pairs window shows only "Spread across horizons", driven by the card\'s controls', () => {
  it('the columns are "Spread 1D" … "Spread 3M", without |1M|; the ranking horizon is marked', () => {
    const c = ctx(), d = pmS.detail!(c);
    expect(d.cols.map(x => x.l)).toEqual([W.col.pair, 'Spread 1D', 'Spread 3D', 'Spread 1W', 'Spread 2W', 'Spread 1M', 'Spread 3M']);
    expect(d.cols.find(x => x.hl)!.l).toBe('Spread 1M');
    expect(d.cols.some(x => /\|/.test(x.l))).toBe(false);
    expect(pmS.stack).toBe(true);
  });
  it('Rank by ranks it by |spread| of that horizon, the filter keeps the card\'s pairs, Show limits the rows', () => {
    const c = ctx(); c.S.stH = '3D'; c.S.stF = 'up'; c.S.stN = '7';
    const d = pmS.detail!(c), rows = M.msSort([...d.rows], [], {}, d.sort);
    expect(d.limit).toBe(7);
    expect(rows.every(r => r.s3D > 0)).toBe(true);
    for (let i = 1; i < rows.length; i++) expect(Math.abs(rows[i - 1].s3D)).toBeGreaterThanOrEqual(Math.abs(rows[i].s3D));
    expect(d.cols.find(x => x.hl)!.l).toBe('Spread 3D');
    c.S.stN = 'all'; c.S.stF = 'all';
    expect(pmS.detail!(c).limit).toBeUndefined(); expect(pmS.detail!(c).rows.length).toBe(55);
    // ranked by 1M every leader is ahead: the filter is off, as on the card
    c.S.stH = '1M'; c.S.stF = 'dn';
    expect(pmS.detail!(c).rows.length).toBe(55);
    expect(d.limitNone!('ZZ')).toBe(W.pmS.noneTop('ZZ', 7));
  });
});

describe('A: the drill-down and Beta windows put both tables on one column grid', () => {
  it('both windows stay stacked and align their tables', () => {
    expect([rsD.stack, rsD.align, pmT.stack, pmT.align]).toEqual([true, true, true, true]);
  });
  it('spans: each column of the smaller table covers neighbouring slots so no slot widens; spare slots trail', () => {
    // the same widths: one slot each
    expect(spans([80, 60, 60], [80, 60, 60])).toEqual([1, 1, 1]);
    // a wide industry column takes two slots instead of widening one
    expect(spans([90, 60, 60, 60, 70, 70], [90, 110, 60, 70, 70])).toEqual([1, 2, 1, 1, 1]);
    // the drill-down's shape: 13 sector columns over 8 stock columns; every slot is covered or trails, nothing widens
    const top = [102, 63, 64, 71, 72, 73, 92, 93, 54, 58, 78, 101, 91], bot = [102, 270, 73, 92, 93, 112, 78, 192];
    const s = spans(top, bot);
    expect(s.reduce((a, b) => a + b, 0)).toBeLessThanOrEqual(top.length);
    let at = 0;
    s.forEach((n, j) => { expect(top.slice(at, at + n).reduce((a, b) => a + b, 0) + 0.5).toBeGreaterThanOrEqual(bot[j]); at += n });
  });
});

describe('V10 / UD79 1A: a second click unselects the pair; none selected shows the automatic pair', () => {
  it('the page opens with no pair chosen: the automatic pair shows, nothing is written into the state', () => {
    const c = ctx(), p = pair(c);
    expect(p.auto).toBe(true);
    expect([c.S.pmA, c.S.pmB]).toEqual([null, null]);
    // the automatic pair: the ratio furthest from its 60-session mean
    let best = 0;
    c.D.names.forEach(x => c.D.names.forEach(y => { if (x !== y) { const z = M.pairZ(c.D.sec(x), c.D.sec(y), 60, c.D.E); if (z != null) best = Math.max(best, Math.abs(z)) } }));
    expect(Math.abs(M.pairZ(c.D.sec(p.a), c.D.sec(p.b), 60, c.D.E) as number)).toBeCloseTo(best);
    // no row of the pair lists is selected while it is automatic
    expect(pmM.detail!(c).rows.some(r => pmM.detail!(c).isSel!(r))).toBe(false);
    expect(pmS.detail!(c).rows.some(r => pmS.detail!(c).isSel!(r))).toBe(false);
    expect(pmT.detail!(c).sub).toContain(W.pmT.autoA);
    expect(W.pmR.subAuto).toMatch(/^Automatic pair/);
  });
  it('a pair row clicked again (either order) clears the choice; a matrix cell is ordered; the selects only choose', () => {
    const c = ctx(), [a, b] = c.D.names;
    setPair(c, a, b);
    expect(pair(c)).toEqual({ a, b, auto: false });
    expect(pmS.detail!(c).rows.filter(r => pmS.detail!(c).isSel!(r)).length).toBe(1);
    setPair(c, b, a);                                                    // the same pair from a list: unselected
    expect(pair(c).auto).toBe(true); expect([c.S.pmA, c.S.pmB]).toEqual([null, null]);
    setPair(c, a, b, { ordered: true }); setPair(c, b, a, { ordered: true });     // the other cell: the reversed pair
    expect(pair(c)).toEqual({ a: b, b: a, auto: false });
    setPair(c, b, a, { ordered: true });                                 // the same cell again: none
    expect(pair(c).auto).toBe(true);
    setPair(c, a, b, { toggle: false }); setPair(c, a, b, { toggle: false });
    expect(pair(c).auto).toBe(false);
    clearPair(c); expect(pair(c).auto).toBe(true);
  });
});

describe('V8: the rotation map follows the prototype', () => {
  it('in a window the Timeline hides the readings; the Map keeps them', () => {
    const c = ctx(); c.S.rotV = 'tl';
    expect(rotA.hideDetail!(c)).toBe(true);
    c.S.rotV = 'map';
    expect(rotA.hideDetail!(c)).toBe(false);
    expect(rotA.wide).toBe(true);
  });
  it('the timeline\'s cells are square in a window, its rows never under 16 px; the strip shares its columns', () => {
    const names = data().names.map(n => M.SHORT[n] || n);
    const win = tlGeom(1240, 560, names), card = tlGeom(600, 420, names);
    expect(win.rh).toBeCloseTo(win.cw); expect(win.cw).toBeGreaterThan(16);
    expect(card.rh).toBe(16);
    // the strip's first and last weeks sit on the centres of the timeline's first and last columns
    const { pl, pr } = tlPad(1240, names), cw = (1240 - pl - pr) / 52;
    expect(pl).toBe(win.pl); expect(cw).toBeCloseTo(win.cw);
    expect(W.rot.stripLabel('26 Nov', '5,242', '+2.8%', true, true)).toBe('26 Nov · 5,242 · +2.8%');
  });
});
