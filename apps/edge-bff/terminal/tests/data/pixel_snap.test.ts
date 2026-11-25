/* Re-check wf_c2fe2424-bf4/terminal:NEW-1: the label boxes of Alpha Extract and Alpha Divergence (and a broker's tag at a
   line's end) on whole pixels of their canvas. At device scale 1.25 and 1.5 the bottom edge of 12 of 46 boxes was off
   the grid by 0.027-0.05 device px: the height was not snapped. Every edge (left, top, right, bottom) is now on the grid,
   at the device ratios 1, 1.25, 1.5, 2 and 3 and at a pane's own fractional ratios (135 rows for 135.19 media px). */
import { describe, expect, it } from 'vitest';
// @ts-expect-error: the Terminal's tsconfig has no Node types; vitest runs in Node
import { readFileSync } from 'node:fs';
import { snapBox, snapTo } from '../../src/data/pixelSnap';

const RATIOS = [1, 1.25, 1.5, 2, 3, 135 / 135.19, 169 / 135.19, 198 / 198.39, 125 / 124.8, 312 / 124.66];
const onGrid = (v: number, r: number) => Math.abs(v * r - Math.round(v * r)) < 1e-9;
// a fixed pseudo-random sequence: positions and sizes as the labels have them (text widths, Pine sizes, fractional y)
let seed = 7; const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;

describe('a label box on the canvas pixels', () => {
  it('puts every edge on a whole pixel, each axis on its own ratio', () => {
    for (const rh of RATIOS) for (const rv of RATIOS) for (let k = 0; k < 80; k++) {
      const x = rnd() * 1400, y = rnd() * 600, w = 12 + rnd() * 80, h = [15, 18, 20, 24][k % 4];
      const b = snapBox(x, y, w, h, { h:rh, v:rv });
      for (const [v, r] of [[b.x, rh], [b.x + b.w, rh], [b.y, rv], [b.y + b.h, rv]]) expect(onGrid(v, r), `${v} at ${r}`).toBe(true);
      // it moves and grows by at most half a pixel of its canvas, and keeps its size wherever it is drawn
      expect(Math.abs(b.x - x)).toBeLessThanOrEqual(.5 / rh + 1e-9); expect(Math.abs(b.y - y)).toBeLessThanOrEqual(.5 / rv + 1e-9);
      expect(Math.abs(b.w - w)).toBeLessThanOrEqual(.5 / rh + 1e-9); expect(Math.abs(b.h - h)).toBeLessThanOrEqual(.5 / rv + 1e-9);
      expect(snapBox(x + 37.3, y + 11.9, w, h, { h:rh, v:rv })).toMatchObject({ w:b.w, h:b.h });
    }
  });

  it('is the bottom edge of the re-check: an 18 px box at a vertical ratio of 0.9986 ends on a row', () => {
    const r = 135 / 135.19, top = snapTo(117 / r, r), b = snapBox(255, top, 40, 18, { h:1, v:r });
    expect(((b.y + 18) * r) % 1).toBeGreaterThan(.9);                          // before: 134.973, between two rows
    expect(onGrid(b.y + b.h, r)).toBe(true);
  });

  it('is what the label primitives and the end tags draw with', () => {
    const src = readFileSync(new URL('../../src/app/indicators.ts', import.meta.url), 'utf8');
    const paint = src.slice(src.indexOf('function paintLabels'), src.indexOf('function labelScale'));
    expect(paint).toMatch(/snapBox\(x - \(m\.w \+ 12\) \/ 2, Math\.max\(0, Math\.min\(paneH - H, want\)\), m\.w \+ 12, size, ratio\)/);
    expect(paint).toMatch(/roundRect\(left, top, w, H, 3\)/);
    expect(paint).toMatch(/const H = snapTo\(size, ratio\.v\)/);
    const tags = src.slice(src.indexOf('class EndLabels'), src.indexOf('/* flow indicators: one series'));
    expect(tags).toMatch(/const ratio = labelRatio\(target\)/);
    expect(tags).toMatch(/snapBox\(Math\.min\(g\.x \+ 6, mediaSize\.width - tw - 2\), y - 8, tw, 16, ratio\)/);
    expect(tags).toMatch(/roundRect\(x, top, w, h, 3\)/);
  });
});
