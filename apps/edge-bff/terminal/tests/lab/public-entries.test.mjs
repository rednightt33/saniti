/* 3f (EXEC option A item 4; CONTRACT.md 8a "Lab code"): no public entry reaches a lab formula. Every page's entry and
   every Web Worker's entry is walked as the public build resolves it ('@edge-lab' is src/lab/none.ts there,
   shared/release-filter.mjs labAlias), and none may reach a module under terminal/src/lab other than none.ts. The lab
   build resolves the alias to src/lab/index.ts: the walk is run that way too and must reach it (the walk's self-test),
   and on a planted entry that imports a lab module directly, which must be caught. The built files are scanned for the
   lab items themselves by tests/test_3f_public_bundles.py. */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { ROOT, reachable } from '../../../shared/import-walk.mjs';
import { labAlias } from '../../../shared/release-filter.mjs';

const EDGE = path.join(ROOT, 'apps/edge-bff');
const LAB_DIR = 'apps/edge-bff/terminal/src/lab/';
const NONE = `${LAB_DIR}none.ts`;
// each page's entry (its index.html's script) and each Web Worker's entry (new Worker(new URL(...)) in the page)
const ENTRIES = ['terminal/src/main.ts', 'terminal/src/data/worker.ts', 'backtest/src/main.ts', 'backtest/src/api/load.worker.ts',
  'screener/src/main.ts', 'radar/src/main.ts', 'overview/src/main.ts', 'watchlist/src/main.ts'];
const labOf = (entry, lab) => reachable(path.join(EDGE, entry), { aliases: labAlias({ lab }) }).filter(m => m.startsWith(LAB_DIR));

describe('3f: no public entry reaches a lab formula', () => {
  it.each(ENTRIES)('%s reaches no lab module in the public build', entry => {
    expect(fs.existsSync(path.join(EDGE, entry))).toBe(true);
    expect(labOf(entry, false).filter(m => m !== NONE)).toEqual([]);
  });

  it('the pages that carry formulas register the lab module first, and the lab build reaches it (the self-test)', () => {
    for (const entry of ['terminal/src/main.ts', 'backtest/src/main.ts']) {
      const first = fs.readFileSync(path.join(EDGE, entry), 'utf8').match(/^import\s+['"]([^'"]+)['"]/m);
      expect(first?.[1], entry).toBe('@edge-lab');
      expect(labOf(entry, false), entry).toEqual([NONE]);
      expect(labOf(entry, true), entry).toEqual([`${LAB_DIR}index.ts`]);
    }
  });

  it('a planted entry that imports a lab module directly is caught (the self-test)', () => {
    const dir = fs.mkdtempSync(path.join(EDGE, 'terminal', 'src', '.planted-'));
    try {
      const entry = path.join(dir, 'main.ts');
      fs.writeFileSync(entry, "import '../lab/index';\n");
      const mods = reachable(entry, { aliases: labAlias({ lab: false }) }).filter(m => m.startsWith(LAB_DIR));
      expect(mods).toEqual([`${LAB_DIR}index.ts`]);
    } finally {
      fs.rmSync(dir, { recursive: true, force: true });
    }
  });
});
