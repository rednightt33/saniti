/* Phase 4 (plain JS: node types are not in the page tsconfig): the production bundle (dist/, `npm run build`) carries no
   fixture code or made-up account, and reads only edge-bff's admin routes and the session. */
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const dir = new URL('../dist/assets/', import.meta.url);
describe.skipIf(!existsSync(dir))('the production bundle', () => {
  it('has no fixture entry or made-up data, and names its routes', () => {
    const js = readdirSync(dir).filter(n => n.endsWith('.js')).map(f => readFileSync(new URL(f, dir), 'utf8')).join('\n');
    expect(js).not.toContain('tests/fixture');
    expect(js).not.toContain('fixture.example');               // the made-up accounts' domain (tests/fixture/main.ts)
    expect(js).toContain('/api/v1/admin');
    expect(js).toContain('/api/v1/auth/session');
    expect(js).not.toMatch(/storageapi\.dev|X-Amz-|innerHTML/);
  });
});
