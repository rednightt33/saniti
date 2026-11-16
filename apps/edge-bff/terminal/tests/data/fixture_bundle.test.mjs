/* ERRORS M469 (EXEC-MU-ACCOUNTS Phase 0): edge-bff serves /terminal-app/ and its assets without a session, so the
   production build must not carry the fixture of the 1:1 check, whose BROKSUM_PROFILE and BK_BASE are a real BBCA broker
   summary (2023-12-18). Both builds are made here into temporary folders (never ../static/terminal-app): the production
   build (`npm run build`, mode production) holds none of the fixture's values; the fixture build (`--mode fixture`, the one
   the 1:1 check serves) still holds them. The values are taken from the constants themselves, so the check follows them. */
import { mkdtempSync, readdirSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { afterAll, describe, expect, it } from 'vitest';
import { build } from 'vite';
import { BK_BASE, BK_FOREIGN, BROKSUM_PROFILE } from '../../src/data/fixtureConstants';

const ROOT = fileURLToPath(new URL('../..', import.meta.url));
const dirs = [];
afterAll(() => dirs.forEach(d => rmSync(d, { recursive: true, force: true })));

async function bundle(mode) {
  const outDir = mkdtempSync(join(tmpdir(), `terminal-${mode}-`)); dirs.push(outDir);
  await build({ root: ROOT, mode, logLevel: 'silent', build: { outDir, emptyOutDir: true } });
  const files = readdirSync(join(outDir, 'assets')).map(f => join(outDir, 'assets', f));
  return [join(outDir, 'index.html'), ...files].map(f => readFileSync(f, 'utf8')).join('\n');
}

/* how a minifier may write a whole number: as is, or shortened with an exponent (294738892500 -> 2947388925e2) */
const forms = n => { const s = String(n), m = s.match(/^(\d*?[1-9])(0+)$/); return m ? [s, `${m[1]}e${m[2].length}`] : [s] };
/* the fixture's most distinctive values: the largest buy and sell values, and one with no trailing zero */
const values = [...new Set([...BROKSUM_PROFILE.flatMap(r => [r[3], r[4]]), ...BK_BASE.flatMap(r => [r[3], r[4]])])]
  .filter(v => v >= 1e8).sort((a, b) => b - a);
const distinctive = [...new Set([...values.slice(0, 10), ...values.filter(v => v % 10 !== 0).slice(0, 4)])];
const foreignList = [...BK_FOREIGN].join(' ');

describe('M469: the fixture is only in the fixture build', () => {
  it('the production build holds none of the fixture values', async () => {
    const js = await bundle('production');
    expect(js.length).toBeGreaterThan(100_000);                                   // a real bundle was read
    expect(distinctive.length).toBeGreaterThanOrEqual(10);
    for (const v of distinctive) for (const f of forms(v)) expect(js.includes(f), `${f} in the production bundle`).toBe(false);
    expect(js.includes(foreignList)).toBe(false);
  }, 120_000);

  it('the fixture build still holds them (the 1:1 check runs on it)', async () => {
    const js = await bundle('fixture');
    const found = distinctive.filter(v => forms(v).some(f => js.includes(f)));
    expect(found).toEqual(distinctive);
    expect(js.includes(foreignList)).toBe(true);
  }, 120_000);
});
