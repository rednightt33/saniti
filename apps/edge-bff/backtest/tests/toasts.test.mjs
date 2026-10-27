/* Review PG-6: a message the page did not write (an error's text) can be any length, so it goes through toastError
   (format.ts: the window's width); a plain toast() keeps the reference's half-window pill for the page's own short
   texts. A source check, so a new error path cannot slip back to the narrow pill. */
import { readdirSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const SRC = fileURLToPath(new URL('../src', import.meta.url));
const sources = readdirSync(SRC, { recursive:true }).filter(f => f.endsWith('.ts') && f !== 'format.ts')
  .map(f => [f, readFileSync(join(SRC, f), 'utf8')]);

describe('toasts (format.ts)', () => {
  it('shows every error text through toastError', () => {
    const plain = sources.flatMap(([f, s]) => [...s.matchAll(/\btoast\(([^)]*)\)/g)]
      .filter(m => /message|msg|\be\b|err/i.test(m[1])).map(m => `${f}: ${m[0]}`));
    expect(plain).toEqual([]);
    expect(sources.filter(([, s]) => s.includes('toastError(')).length).toBeGreaterThan(3);
  });
});
