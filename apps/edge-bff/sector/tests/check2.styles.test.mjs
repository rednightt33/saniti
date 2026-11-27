/* EXEC-SECTOR-ANALYSIS check 2 (2026-11-27; verification/sector_analysis/check2/FIXES.md): the rules of the page's own
   sheet that the fixes set (the arithmetic and the words: check2.test.ts; the pixels: look/check2.mjs). */
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const css = readFileSync(new URL('../src/styles/sector.css', import.meta.url), 'utf8');
const src = f => readFileSync(new URL(`../src/${f}`, import.meta.url), 'utf8');
/** the rules of a sheet, in order: [selector list, body] (media blocks flattened) */
const rules = s => [...s.replace(/\/\*[\s\S]*?\*\//g, '').matchAll(/([^{}@]+)\{([^{}]*)\}/g)].map(m => [m[1].trim(), m[2]]);
/** a simple selector's specificity [ids, classes/attributes/pseudo-classes, elements] (no :is/:not inside) */
const spec = sel => {
  const s = sel.replace(/::?[\w-]+\([^)]*\)/g, m => (m.startsWith('::') ? '' : ':x')).replace(/::[\w-]+/g, '');
  return [(s.match(/#[\w-]+/g) || []).length, (s.match(/\.[\w-]+|\[[^\]]+\]|:[\w-]+/g) || []).length, (s.replace(/[#.][\w-]+|\[[^\]]+\]|:[\w-]+/g, ' ').match(/(^|[\s>+~])[a-z][\w-]*/gi) || []).length];
};
// a later rule wins a tie: the ring must be strictly more specific than a later reset
const gt = (a, b) => a[0] !== b[0] ? a[0] > b[0] : a[1] !== b[1] ? a[1] > b[1] : a[2] > b[2];

describe('the sheet of check 2', () => {
  it('BD2-1 / MX2-3: no rule after the page\'s focus ring takes it away again (the slope rows, the map dots)', () => {
    const all = rules(css), i = all.findIndex(([s, b]) => /:focus-visible/.test(s) && /outline:2px solid var\(--focus-ring\)/.test(b) && /\.sl:focus-visible/.test(s));
    expect(i).toBeGreaterThan(-1);
    // the compounds the ring names outside :is(): .ovx-dot, .sl, .pt, g.dt
    const ringed = all[i][0].split(',').map(x => x.trim()).filter(x => !x.startsWith(':is')).map(x => x.replace(':focus-visible', ''));
    for (const [s, b] of all.slice(i + 1)) {
      if (!/outline:\s*(none|0)/.test(b)) continue;
      for (const one of s.split(',').map(x => x.trim())) {
        const last = one.split(/\s+|>/).pop();
        for (const r of ringed) if (last === r.split(/\s+/).pop()) expect(gt(spec(r + ':focus-visible'), spec(one)), `${one} {${b}} after the ring of ${r}`).toBe(true);
      }
    }
    expect(css).not.toMatch(/\.slope \.sl\{[^}]*outline:none/);
    expect(css).not.toMatch(/\.rrg \.pt\{[^}]*outline:none/);
  });
  it('MX2-7: the sort arrow of the order a table is in is never drawn faded', () => {
    expect(css).not.toMatch(/\.df \.sk[^{]*\{[^}]*opacity/);
  });
  it('RP2-3 / MX2-2: a segmented control never stacks its own buttons; on a phone the Rotation detail band grows', () => {
    expect(css).toMatch(/\n\.seg\{flex-wrap:nowrap;flex:none\}/);
    expect(css).toMatch(/\.fw\.c1 \.fw-dh\{height:auto;min-height:52px;padding-block:var\(--s-4\);flex-wrap:wrap\}\.fw\.c1 \.fw-dt span\{white-space:normal\}/);
  });
  it('MX2-6: a label wraps with its control; the search keeps its placeholder\'s width on a phone', () => {
    expect(css).toMatch(/\.sgrp\{display:inline-flex;align-items:center;gap:var\(--s-4\);flex:none\}/);
    expect(css).not.toMatch(/\.fw-q input\{width:110px\}/);
  });
  it('RP2-4: one cell padding in both aligned tables, an industry row still indented', () => {
    expect(css).toMatch(/\.fw\.al :is\(\.fw-l \.tbl,\.fw-tb\) :is\(th,td\)\{padding-left:4px!important;padding-right:4px!important\}/);
    expect(css).toMatch(/\.fw\.al \.rs-d \.tbl tr\.u>td:first-child\{padding-left:42px!important\}/);
  });
  it('RP2-1 / RP2-5: a window whose detail is hidden ends under its content; the Timeline\'s box follows the Timeline', () => {
    expect(css).toMatch(/\.fw\.bare \.fw-c\{align-items:start\}\.fw\.bare \.fw-l\{min-height:0\}/);
    expect(css).toMatch(/\.rrg\.tlh\{flex:none!important;min-height:0;height:var\(--tlh,240px\)\}/);
  });
  it('MX2-9: a market map group\'s name may take more lines', () => {
    expect(css).toMatch(/\.mk-gl\.wr\{white-space:normal;line-height:14px;display:-webkit-box/);
  });
  it('MX2-4 / MX2-5: the touch areas read their four measured sides, 0 until measured, never past 44 px', () => {
    const t = css.slice(css.indexOf('@media (pointer:coarse){\n  :is(.seg button'));
    for (const k of ['t', 'b', 'l', 'r']) expect(t).toMatch(new RegExp(`calc\\(-1 \\* var\\(--hit-${k},0px\\)\\),min\\(0px,calc\\(100% - 44px\\)\\)`));
    // a clipped name keeps its clip on an inner span (the cell's area is not clipped with it)
    expect(css).toMatch(/\.ovx-hm \.nm>span,\.rsw \.nm>span,\.pmg \.nm>span\{min-width:0;overflow:hidden;white-space:nowrap\}/);
    expect(css).not.toMatch(/\.ovx-hm \.nm\{[^}]*overflow:hidden/);
    expect(css).not.toMatch(/\.pmg \.nm\{[^}]*overflow:hidden/);
    // the old fixed 44 px boxes (check 1 MX-4) are gone: every area is measured
    expect(css).not.toMatch(/\.fwx::after|\.car::after|\.fw-x::after/);
  });
});

describe('the sources of check 2', () => {
  it('BD2-2: a tint never carries the up/down colours as text; the quadrant pills take the tag inks', () => {
    for (const f of ['cards/ov.ts', 'cards/rs.ts', 'cards/rot.ts', 'cards/pm.ts', 'cards/br.ts', 'ui.ts', 'windows.ts']) expect(src(f)).not.toMatch(/-bg\)[^`]{0,80}color:var\(--(green|red|blue|amber)\)/);
    expect(src('cards/rs.ts')).toMatch(/const QFG[^;]*'var\(--green-tag\)'[^;]*'var\(--amber-tag\)'[^;]*'var\(--red-tag\)'[^;]*'var\(--blue-tag\)'/);
  });
  it('BD2-3: the Stock detail\'s tip gets no reason sentence in its "since" place', () => {
    expect(src('cards/br.ts')).toContain('W.brD.tip(r.ab, lab, days(r.dy, r.more), r.since ? M.dateLabel(r.since, false, true) : null)');
  });
  it('OV2-3: a return card\'s Custom popover writes the close it is measured from', () => {
    expect(src('cards/ov.ts')).toMatch(/noteOf: o\.level \|\| o\.label \|\| o\.note \? undefined : r => \(r\.ok && r\.span \? W\.range\.fromClose\(/);
  });
  it('MX2-8: every mouse word of the page has its touch word (tap)', () => {
    const w = src('words.ts').split('\n').filter(l => !/^\s*(\/\/|\/\*|\*)/.test(l));
    for (const l of w) if (/\b(click|Click|hover|Hover|point at)\b/.test(l)) expect(l, l.trim().slice(0, 90)).toMatch(/tap\(/);
  });
  it('MX2-1: the Rotation detail window\'s chip row is a scroller with the edge cue', () => {
    expect(src('ui.ts')).toMatch(/const CUED = '[^']*\.c1-chips/);
  });
});
