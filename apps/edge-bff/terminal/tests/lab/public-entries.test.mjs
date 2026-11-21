/* 3f (EXEC option A item 4; CONTRACT.md 8 "Lab code"): no public entry reaches a lab formula. Every page's entry and
   every Web Worker's entry, derived (shared/import-walk.mjs pages, pageEntries: each index.html script and each Web
   Worker it starts), is walked as the public build resolves it ('@edge-lab' is src/lab/none.ts there,
   shared/release-filter.mjs labAlias), and none may reach a module under terminal/src/lab other than none.ts. The lab
   build resolves the alias to src/lab/index.ts: the walk is run that way too and must reach it (the walk's self-test),
   and on a planted entry that imports a lab module directly, which must be caught. That each page's own configuration
   resolves the alias this way is shown by the proof builds (tests/test_3f_public_bundles.py: the lab formula is in the
   lab builds only), and the built files are scanned for the lab items themselves there too. */
import fs from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { ROOT, pageEntries, pages, reachable } from '../../../shared/import-walk.mjs';
import { labAlias } from '../../../shared/release-filter.mjs';

const EDGE = path.join(ROOT, 'apps/edge-bff');
const LAB_DIR = 'apps/edge-bff/terminal/src/lab/';
const NONE = `${LAB_DIR}none.ts`;
const ENTRIES = pages().flatMap(page => pageEntries(page, { aliases: labAlias({ lab: false }) }));
/** the pages built twice, public and lab (their build script has a --mode lab build) */
const LAB_PAGES = pages().filter(page => JSON.parse(fs.readFileSync(path.join(EDGE, page, 'package.json'), 'utf8')).scripts.build.includes('--mode lab'));
const labOf = (entry, lab) => reachable(path.join(EDGE, entry), { aliases: labAlias({ lab }) }).filter(m => m.startsWith(LAB_DIR));

describe('3f: no public entry reaches a lab formula', () => {
  it.each(ENTRIES)('%s reaches no lab module in the public build', entry => {
    expect(fs.existsSync(path.join(EDGE, entry))).toBe(true);
    expect(labOf(entry, false).filter(m => m !== NONE)).toEqual([]);
  });

  it('the pages with a lab build register the lab module first, and the lab build reaches it (the self-test)', () => {
    expect(LAB_PAGES).toEqual(['backtest', 'terminal']);
    for (const page of LAB_PAGES) {
      const [entry] = pageEntries(page, { aliases: labAlias({ lab: false }) });
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
