/* EXEC-SECTOR-ANALYSIS check 2 (2026-11-27): the findings of the five checkers (verification/sector_analysis/check2/,
   FIXES.md) that the page's arithmetic, words and touch areas decide, each keyed by its run and id. The sheet's rules are
   check2.styles.test.mjs; the layout and the interactions tests/look/check2.mjs (and look/round2.mjs step 7 for OV2-1 and
   RP2-4); the touch areas on every page verification/edge_states/round2_focus_contrast.mjs. */
import { describe, expect, it } from 'vitest';
import * as M from '../src/model.ts';
import { heat, FLAT, SEG } from '../src/ui.ts';
import { quadTag } from '../src/cards/rs.ts';
import { lines } from '../src/cards/ov.ts';
import { tlGeom, tlHeight } from '../src/cards/rot.ts';
import { dotRadius, sides } from '../src/touch.ts';
import { W } from '../src/words.ts';


describe('agents_20261127-sector-r2-brdt', () => {
  it('BD2-2: a quadrant pill\'s text is the tag ink of its tint, never the up/down colour', () => {
    expect(quadTag('Lagging')).toContain('color:var(--red-tag)');
    expect(quadTag('Improving')).toContain('color:var(--blue-tag)');
    expect(quadTag('Leading')).toContain('color:var(--green-tag)');
    expect(quadTag('Weakening')).toContain('color:var(--amber-tag)');
  });
  it('BD2-3: a status older than the data reads as a sentence, never "since The status is …"', () => {
    const t = W.brD.tip(1, 'EMA200', '300+', null);
    expect(t).toBe('Above EMA200 for 300+ sessions: the status began before the 300 sessions of data');
    expect(t).not.toMatch(/since The/);
    expect(W.brD.tip(0, 'EMA50', '12', '3 Nov')).toBe('Below EMA50 for 12 sessions, since 3 Nov');
  });
  it('BD2-4: a cell is coloured as printed: "0 pp" is the flat step, the same text the same colour', () => {
    const flat = `background:${FLAT[0]};color:${FLAT[1]}`;
    expect(heat(0.3, 25, 0, 0)).toBe(flat);                       // the Breadth table's "0 pp" (+0.3)
    expect(heat(-0.4, 25, 0, 0)).toBe(flat);
    expect(heat(0.6, 25, 0, 0)).toBe(heat(1, 25, 0, 0));          // printed "+1 pp" both
    expect(heat(50.4, 50, 50, 0)).toBe(flat);                     // "50%" at the centre
    expect(heat(0.04, 5, 0, 1)).toBe(flat);                       // "+0.0%" in Sector × horizon
    expect(heat(0.3, 25)).not.toBe(flat);                         // without the printed decimals: the old colour
    // the text colour, the same mechanism: up/down as printed
    expect(M.cls(0.004)).toBe(''); expect(M.cls(-0.04, 1)).toBe(''); expect(M.cls(0.06, 1)).toBe('up');
    expect(M.cls(-0.0004, null)).toBe('down');                    // pctSigned keeps its "−0.0%" (check 1 BD-12)
    expect(M.clsText(0.03, '0.0 pp')).toBe(''); expect(M.clsText(-0.2, '−0.2%')).toBe('down'); expect(M.clsText(3, '▲3')).toBe('up');
    expect(M.clsText(0.92, '0.92')).toBe('up');
  });
});

describe('agents_20261127-sector-r2-ovrs', () => {
  it('OV2-3: the Custom popover names the close a return starts from and the From date it follows', () => {
    expect(W.range.fromClose('3 Sep', '4 Sep')).toBe('Measured from the 3 Sep close, the session before From (4 Sep), as the Overview’s Custom.');
  });
});

describe('agents_20261127-sector-r2-rotpm', () => {
  it('RP2-2: the axis ends at the last stock inside Tukey\'s fences, so the 26 Nov outliers no longer squeeze it', () => {
    // Health's 1M vs IHSG of 26 Nov 2026 (the checker's dots): RSCH and MMIX at −56 and −61 pp, AYAM-like −34
    const x = [-60.56, -56.25, -34.03, -19.49, -17.83, -16.99, -14.09, -13.12, -12.83, -12.83, -12.09, -11.66, -10.79, -10.23, -7.68, -7.15, -6.71, -6.43, -5.62, -4.47, -3.84, -3.65, -3.53, -3.45, -3.35, -2.83, -2.83, -2.51, -0.24, 0, 2.14, 4.17, 5.03, 5.05, 5.17, 5.57, 6.7, 8.65, 9.76];
    const [lo, hi] = M.axisRange(x);
    expect(lo).toBe(-19.49); expect(hi).toBe(9.76);
    expect(-lo / (hi - lo)).toBeLessThan(0.7);                    // the zero line at 67% of the width (was 81%)
    expect(M.axisRange([-56, 1, 2])[0]).toBe(-56);                // too few values: every value inside (check 1 RP-5)
  });
  it('RP2-1 / RP2-5: the Timeline fills a card on the page grid; in a window or the one-column layout it is square and as tall as itself', () => {
    const names = ['Industrials', 'Energy', 'Technology', 'Cons. Cyclicals', 'Basic Materials', 'Financials', 'Healthcare', 'Infrastructure', 'Properties', 'Transportation', 'Cons. Non-Cyclicals'];
    const card = tlGeom(700, 420, names, 52, true), win = tlGeom(1300, Infinity, names, 52, false), phone = tlGeom(358, Infinity, names, 52, false);
    expect(card.rh * names.length + card.pt + card.pb).toBeCloseTo(420);     // the rows take the card's height
    expect(card.square).toBe(false);
    expect(win.rh).toBeCloseTo(win.cw); expect(win.square).toBe(true);
    expect(phone.rh).toBe(16);
    expect(tlHeight(win, names.length)).toBeCloseTo(win.pt + names.length * win.rh + 20);
    // a window short of room shrinks its rows, never under 16 px
    expect(tlGeom(1300, 200, names, 52, false).rh).toBe(16);
  });
});

describe('agents_20261127-sector-r2-mobex', () => {
  it('MX2-6: a segmented control and its label wrap together', () => {
    expect(SEG('k', 'Show', [['7', 'Top 7'], ['all', 'All']], '7')).toMatch(/^<span class="sgrp"><span class="plab">Show<\/span><div class="seg sm"/);
    expect(SEG('k', '', [['a', 'A']], 'a')).toMatch(/^<div class="seg sm"/);
  });
  it('MX2-9: a group name wider than its group takes its lines', () => {
    expect(lines('Healthcare Equipment & Supplies +1.2', 87)).toBeGreaterThanOrEqual(2);
    expect(lines('Banks +0.4', 200)).toBe(1);
  });
  it('MX2-4 / MX2-5: a side reaches to the next target, half way to another area; the 44 px are shared between the sides', () => {
    const me = { l: 100, t: 100, r: 130, b: 122 };                          // a 30 × 22 button
    // free all round: 7 and 11 each side (44 × 44)
    expect(sides(me, [])).toEqual({ t: 11, b: 11, l: 7, r: 7 });
    // another area 6 px to the right: 3 px; a plain target 4 px above: 4 px, the 7 the top cannot take go below
    const s = sides(me, [{ b: { l: 136, t: 100, r: 160, b: 122 }, area: true }, { b: { l: 90, t: 80, r: 140, b: 96 }, area: false }]);
    expect(s.r).toBe(3); expect(s.t).toBe(4); expect(s.b).toBe(18); expect(s.l).toBe(11);
    // segmented buttons that touch: no side between them, the outer sides reach out
    expect(sides(me, [{ b: { l: 130, t: 100, r: 160, b: 122 }, area: true }]).r).toBe(0);
    // a target over the control's own box (a sticky cell): nothing
    expect(sides(me, [{ b: { l: 110, t: 95, r: 140, b: 110 }, area: false }])).toEqual({ t: 0, b: 0, l: 0, r: 0 });
    // inside a pinned or clipping box: no side past its edge
    expect(sides(me, [], { l: 95, t: 100, r: 200, b: 200 }).t).toBe(0);
    // two areas never overlap: each side at most half the gap
    const a = { l: 0, t: 0, r: 20, b: 20 }, b = { l: 30, t: 0, r: 50, b: 20 };
    expect(sides(a, [{ b, area: true }]).r + sides(b, [{ b: a, area: true }]).l).toBeLessThanOrEqual(10);
  });
  it('MX2-4: a chart dot\'s circle reaches half way to the next dot and never under the dot itself', () => {
    const p = { x: 0, y: 0, r: 5 }, q = { x: 20, y: 0, r: 5 };
    expect(dotRadius(p, [p, q], [])).toBe(10);
    expect(dotRadius(p, [p, { x: 6, y: 0, r: 5 }], [])).toBe(5);
    expect(dotRadius(p, [p], [])).toBe(22);
    expect(dotRadius(p, [p], [{ l: 12, t: -2, r: 16, b: 2 }])).toBe(12);   // a trail point's hint 12 px away
  });
});
