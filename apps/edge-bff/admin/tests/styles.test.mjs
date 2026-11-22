/* Phase 4: the admin page's copies of the EDGE design system (src/styles/spec-v1.2.css and edge-canonical.css) hold the
   system's own rules as they are (.claude/skills/edge-design-system/assets); a change of the system is copied here in the
   same commit, so the page never drifts from it unseen. Only the leading usage note may differ: the page's names EDGE's
   own Inter (/fonts/inter-400-700.css, R2-28) where the user's verbatim spec names Google Fonts, as the Watchlist's copy
   does (tests/test_decisions_small.py refuses a page source that names Google Fonts). */
import { existsSync, readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

/** the file without its leading comment (the usage note) */
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
