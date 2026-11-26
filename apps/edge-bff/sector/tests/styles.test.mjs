/* EXEC-SECTOR-ANALYSIS S4, as the Admin page's (apps/edge-bff/admin/tests/styles.test.mjs): the page's copies of the EDGE
   design system (src/styles/spec-v1.2.css and edge-canonical.css) hold the system's own rules as they are
   (.claude/skills/edge-design-system/assets); a change of the system is copied here in the same commit. Only the leading
   usage note may differ (EDGE's own Inter, never Google Fonts). The page's own sheet has no literal colour the tokens
   name: every colour of a chart is a token. */
import { existsSync, readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const rules = (text) => text.replace(/^\s*\/\*[\s\S]*?\*\/\s*/, '');
const system = new URL('../../../../.claude/skills/edge-design-system/assets/', import.meta.url);
describe.skipIf(!existsSync(system))('the design system copies', () => {
  for (const name of ['spec-v1.2.css', 'edge-canonical.css']) {
    it(`${name} is the system's own`, () => {
      const copy = readFileSync(new URL(`../src/styles/${name}`, import.meta.url), 'utf8'), own = readFileSync(new URL(name, system), 'utf8');
      expect(rules(copy).length).toBeGreaterThan(1000);
      expect(rules(copy)).toBe(rules(own));
      expect(copy).not.toMatch(/fonts\.(googleapis|gstatic)\.com/);
    });
  }
});
describe('the page sheet', () => {
  it('loads the system first and names no chart colour of the prototype', () => {
    const css = readFileSync(new URL('../src/styles/sector.css', import.meta.url), 'utf8');
    expect(css.indexOf("@import './spec-v1.2.css'")).toBeLessThan(css.indexOf("@import './edge-canonical.css'"));
    expect(css).not.toMatch(/#17348c|#087f5b|#d62839|#b7791f|#2962ff|#f5a623|#089981|#f23645/i);
  });
  it('the sources draw with tokens, not the prototype\'s literal colours', () => {
    for (const f of ['ui.ts', 'charts.ts', 'cards/ov.ts', 'cards/rs.ts', 'cards/rot.ts', 'cards/pm.ts', 'cards/br.ts']) {
      const t = readFileSync(new URL(`../src/${f}`, import.meta.url), 'utf8');
      expect(t, f).not.toMatch(/#17348c|#087f5b|#d62839|#b7791f|#2962ff|#f5a623|#089981|#f23645|#171717|#bdbdbd|#dcdcdc/i);
    }
  });
});
