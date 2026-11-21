/* EXEC-WATCHLIST L5 (plain JS: node types are not in the page tsconfig): the production bundle (dist/, `npm run build`)
   carries no fixture code, made-up file or bucket address, and reads only edge-bff's routes. */
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const dir = new URL('../dist/assets/', import.meta.url);
describe.skipIf(!existsSync(dir))('the production bundle', () => {
  it('has no fixture entry, sample file or bucket address', () => {
    for (const f of readdirSync(dir).filter(n => n.endsWith('.js'))) {
      const js = readFileSync(new URL(f, dir), 'utf8');
      expect(js).not.toContain('tests/fixture');
      expect(js).not.toContain('ALFQ');                       // a made-up ticker of the sample file
      expect(js).not.toMatch(/storageapi\.dev|X-Amz-/);
      expect(js).toContain('/api/v1/watchlist/');
      expect(js).toContain('/api/v1/examples/watchlist');   // 3e, the example mode's data path (src/api.ts)
      expect(js).toContain('/api/terminal/v1/logo/');
    }
  });
});
