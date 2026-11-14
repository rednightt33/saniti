/* EXEC-RADAR R7 (plain JS: node types are not in the page tsconfig): the production bundle (dist/, `npm run build`) carries no fixture code or saved data. */
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const dir = new URL('../dist/assets/', import.meta.url);
describe.skipIf(!existsSync(dir))('the production bundle', () => {
  it('has no fixture entry, saved Radar file or bucket address', () => {
    for (const f of readdirSync(dir).filter(n => n.endsWith('.js'))) {
      const js = readFileSync(new URL(f, dir), 'utf8');
      expect(js).not.toContain('tests/fixture');
      expect(js).not.toContain('"schema":1');
      expect(js).not.toMatch(/storageapi\.dev|X-Amz-/);
      expect(js).toContain('/api/v1/radar/');
    }
  });
});
