// EXEC-PINE-INDICATORS (the user 2026-11-23, UD32 "All at once"): the Style tab's colour box (src/app/colorPicker.ts).
// The grid's colours, the tints and shades it derives, and the rule that the line options (opacity, thickness, line
// style) are offered only on an indicator drawn on the price chart (the user: "opsi garis ini hanya untuk indikator yang
// ketika ditambahkan akan muncul overlay di chart ya"; UD31), checked on every indicator of the registry.
import { describe, expect, it } from 'vitest';
import { COLOR_GRID, HUES, LINE_STYLE_KEYS, lineOptions, mix } from '../../src/app/colorPicker';
import REG from '../../src/data/indRegistry.json';

describe('colour box (UD32)', () => {
  it('the grid: a grey row, the ten hues, four tints and two shades, every colour a distinct #rrggbb', () => {
    expect(COLOR_GRID.length).toBe(8);
    COLOR_GRID.forEach(row => expect(row.length).toBe(10));
    expect(COLOR_GRID[1]).toEqual(HUES);
    const all = COLOR_GRID.flat();
    all.forEach(c => expect(c).toMatch(/^#[0-9a-f]{6}$/));
    expect(new Set(all).size).toBe(all.length);
    expect(COLOR_GRID[0][0]).toBe('#ffffff'); expect(COLOR_GRID[0][9]).toBe('#000000');
  });
  it('mix moves a colour toward another by the given share', () => {
    expect(mix('#000000', '#ffffff', 0.5)).toBe('#808080');
    expect(mix('#2962ff', '#ffffff', 0)).toBe('#2962ff');
    expect(mix('#2962ff', '#000000', 1)).toBe('#000000');
    // the tint rows get lighter going down, the shade rows darker
    const lum = (c: string) => [1, 3, 5].reduce((a, i) => a + parseInt(c.slice(i, i + 2), 16), 0);
    for (let h = 0; h < 10; h++) {
      expect(lum(COLOR_GRID[2][h])).toBeGreaterThan(lum(COLOR_GRID[5][h]));
      expect(lum(COLOR_GRID[6][h])).toBeGreaterThan(lum(COLOR_GRID[7][h]));
    }
  });
  it('line options only on the price chart: a line or stepped segment gets the line style, dots get none, the rest nothing', () => {
    expect(LINE_STYLE_KEYS).toEqual(['Solid', 'Dashed', 'Dotted']);
    expect(lineOptions('overlay', 'line')).toEqual({ style: true });
    expect(lineOptions('overlay', 'seg')).toEqual({ style: true });
    expect(lineOptions('overlay', 'dots')).toEqual({ style: false });
    for (const k of ['hist', 'band', 'fill', 'shape', 'cloud', undefined]) expect(lineOptions('overlay', k)).toBeNull();
    for (const z of ['panel', 'volume', undefined]) for (const k of ['line', 'seg', 'dots']) expect(lineOptions(z, k)).toBeNull();
  });
  it('every panel and volume indicator of the registry gets no line option; every overlay one with a line gets them', () => {
    const rows = ((REG as any).indicators ?? REG) as any[];
    const overlay = rows.filter(r => r.zone === 'overlay'), other = rows.filter(r => r.zone !== 'overlay');
    expect(overlay.length).toBeGreaterThan(10); expect(other.length).toBeGreaterThan(10);
    let checked = 0;
    other.forEach(r => (r.outs || []).forEach((o: any) => { checked++; expect(lineOptions(r.zone, o.r), `${r.id} ${o.k}`).toBeNull() }));
    expect(checked).toBeGreaterThan(40);
    // overlays drawn as lines get the full options (the test build filters the lab items out, so released ones here)
    for (const name of ['Bollinger Bands', 'Donchian Channels', 'Keltner Channels']) {
      const r = overlay.find(x => x.name === name)!;
      expect(r.outs.filter((o: any) => o.vis && lineOptions(r.zone, o.r)?.style).length, name).toBeGreaterThan(0);
    }
  });
});
