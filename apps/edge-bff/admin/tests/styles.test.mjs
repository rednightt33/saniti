/* Phase 4: the admin page's copies of the EDGE design system (src/styles/spec-v1.2.css and edge-canonical.css) are the
   system's own files as they are (.claude/skills/edge-design-system/assets); a change of the system is copied here in the
   same commit, so the page never drifts from it unseen. */
import { existsSync, readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const system = new URL('../../../../.claude/skills/edge-design-system/assets/', import.meta.url);
describe.skipIf(!existsSync(system))('the design system copies', () => {
  for (const name of ['spec-v1.2.css', 'edge-canonical.css']) {
    it(`${name} is the system's own`, () => {
      expect(readFileSync(new URL(`../src/styles/${name}`, import.meta.url), 'utf8')).toBe(readFileSync(new URL(name, system), 'utf8'));
    });
  }
});
