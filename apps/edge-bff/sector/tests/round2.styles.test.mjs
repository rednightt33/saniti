/* EXEC-SECTOR-ANALYSIS visual round 2 (2026-11-27; verification/sector_analysis/round2/CHANGES.md): the rules of the page's
   own sheet that the items set (the arithmetic and the wiring: round2.test.ts; the pixels: look/round2.mjs). */
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const css = readFileSync(new URL('../src/styles/sector.css', import.meta.url), 'utf8');

describe('the sheet of visual round 2', () => {
  it('V6 / UD77 2A: no heat cell is dimmed while a sector is locked or a pair chosen; the row is marked by its name cell', () => {
    expect(css).not.toMatch(/\.ovx-hm\.pk>\.c|\.rsw\.has \.c|\.pmg\.has|\.ovx-mk\.sub \.mk-g:not\(\.on\)|\.br-t \.tbl\.has/);
    expect(css).not.toMatch(/--sx-hot|--sx-navy-ink/);
    expect(css).toMatch(/\.ovx-hm \.nm\.hl\{[^}]*background:var\(--sel\)/);
    expect(css).toMatch(/\.rsw \.nm\.pk\{font-weight/);
    expect(css).toMatch(/\.pmg \.nm\.on\{background:var\(--sel\);font-weight/);
    // the picked industry of the market map: an outline, the others keep their colour
    expect(css).toMatch(/\.mk-g\.on\{box-shadow:0 0 0 2px var\(--text\)/);
  });
  it('V6: the flat step is the Overview\'s --ov-flat in each theme', () => {
    expect(css).toMatch(/:root\{--sx-flat:var\(--gray-200\);--sx-flat-fg:var\(--gray-900\)\}/);
    expect(css).toMatch(/:root\.dark,:root\[data-theme="dark"\]\{--sx-flat:#2b2b2b;--sx-flat-fg:var\(--text\)\}/);
    const ov = readFileSync(new URL('../../overview/src/styles/overview.css', import.meta.url), 'utf8');
    expect(ov).toContain('--ov-flat:var(--gray-200);--ov-flat-fg:var(--gray-900)');
    expect(ov).toContain('--ov-flat:#2b2b2b;--ov-flat-fg:var(--text)');
  });
  it('V2: the cumulative list keeps its rows at most a table row apart, its bars take the room, the chart the list\'s height', () => {
    expect(css).toMatch(/\.ovx-cr\{[^}]*grid-template-columns:minmax\(0,1fr\) 300px[^}]*max-height:calc\(var\(--n, 11\) \* 36px \+ 24px\)/);
    expect(css).toMatch(/\.ovx-bl \.r\{[^}]*grid-template-columns:76px minmax\(0,1fr\) 50px/);
    expect(css).toMatch(/\.ovx-cr\{grid-template-columns:minmax\(0,1fr\);max-height:none\}/);       // one column: no cap
  });
  it('C1: one 52 px band and 36 px rows on both sides of the Rotation detail window; chips on a phone', () => {
    expect(css).toMatch(/\.c1-band,\.fw\.c1 \.fw-dh\{height:52px/);
    expect(css).toMatch(/\.fw\.c1 \.tbl th,\.fw\.c1 \.tbl td\{height:36px\}/);
    expect(css).toMatch(/\.c1-chip\{[^}]*height:32px/);
  });
  it('A: the aligned windows give both scrollers the same gutter', () => {
    expect(css).toMatch(/\.fw\.al \.fw-tw,\.fw\.al \.fw-l \.tbl-wrap\{scrollbar-gutter:stable;scrollbar-width:thin;overflow-x:auto\}/);
  });
});
