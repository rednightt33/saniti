/* EXEC-BACKTEST-REVAMP Stage D (ERRORS M460 item 1): a panel removed from the markup leaves the code that reads its id
   behind, and that fails only at run time (the keyboard shortcuts read the removed entry workspace, #ews, and threw on
   every key press). Every id the page's code reads by name ($('x') or getElementById('x')) must be in index.html (outside
   comments) or be written by the page's own code (id="x" in a template, el.id = 'x'). The shared core (src/core) reads
   no element. */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const PAGE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const files = dir => fs.readdirSync(dir, { withFileTypes: true }).flatMap(e => {
  const p = path.join(dir, e.name);
  return e.isDirectory() ? (e.name === 'core' ? [] : files(p)) : e.name.endsWith('.ts') ? [p] : [];
});

describe('ids the page reads', () => {
  it('exist in the markup or are written by the page', () => {
    const html = fs.readFileSync(path.join(PAGE, 'index.html'), 'utf8').replace(/<!--[\s\S]*?-->/g, '');
    const known = new Set([...html.matchAll(/\bid="([A-Za-z][\w-]*)"/g)].map(m => m[1]));
    const reads = new Map();
    for (const f of files(path.join(PAGE, 'src'))) {
      const t = fs.readFileSync(f, 'utf8');
      for (const re of [/\bid=\\?"([A-Za-z][\w-]*)\\?"/g, /\bid='([A-Za-z][\w-]*)'/g, /\.id\s*=\s*['"]([\w-]+)['"]/g])
        for (const m of t.matchAll(re)) known.add(m[1]);
      for (const m of t.matchAll(/(?:\$|getElementById)\('([A-Za-z][\w-]*)'\)/g))
        reads.set(m[1], [...(reads.get(m[1]) || []), path.relative(PAGE, f)]);
    }
    expect(reads.size).toBeGreaterThan(50);              // the scan found the page's reads
    const missing = [...reads].filter(([id]) => !known.has(id)).map(([id, fs]) => `${id} (${[...new Set(fs)].join(', ')})`);
    expect(missing, 'ids read but neither in index.html nor written by the page').toEqual([]);
  });
});
