/* EXEC-SECTOR-ANALYSIS S4 (plain JS: node types are not in the page tsconfig): the production bundle (dist/, `npm run
   build`) carries no fixture code or saved file, no model name, no seeded stand-in of the prototype, and its two data
   paths: the live files and, in the example mode (decision J), the example's. */
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const dir = new URL('../dist/assets/', import.meta.url);
describe.skipIf(!existsSync(dir))('the production bundle', () => {
  const js = () => readdirSync(dir).filter(n => n.endsWith('.js')).map(f => readFileSync(new URL(f, dir), 'utf8')).join('\n');
  it('has no fixture entry, saved file or bucket address', () => {
    const t = js();
    expect(t).not.toContain('tests/fixture');
    expect(t).not.toContain('"schema":1');
    expect(t).not.toContain('PT Contoh');
    expect(t).not.toMatch(/storageapi\.dev|X-Amz-/);
    expect(t).toMatch(/["'`]\/api\/v1\/sector["'`]/);
    expect(t).toContain('/api/v1/examples/sector');
    expect(t).toContain('sector-stocks-');
  });
  it('keeps the decisions: no EMA20, no "RRG" names, no seeded stand-ins, no Screener button', () => {
    const t = js();
    expect(t).not.toMatch(/\bEMA20\b|\bema_?20\b/);                              // C1 (EMA200 stays)
    expect(t).not.toMatch(/Relative Rotation Graph|RS-Ratio|RS-Mom|\bRRG\b/);     // A (UD67 2A)
    expect(t).not.toMatch(/illustrative|Draft formula|not available in this prototype/i);   // B, G
    expect(t).not.toContain('Open in Screener');                                  // G
    expect(t).toContain('Open in Terminal');
  });
});
