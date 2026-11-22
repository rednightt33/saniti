/* 3f checker TR-2, B3 (FUTURE_PLAN.md "Before the first lab item or tab"; the user's go 2026-11-22): the lab formulas have
   one registration point, the Terminal's src/lab/index.ts reached as '@edge-lab', and every Node process that runs a
   formula loads it: both workers (their start command and each compute thread they start) and both registry
   generators. Before, none did, so the first lab indicator would have turned registry:check red and could not run in a
   backtest or a screen. Derived from the services' own files (package.json scripts, the Worker() calls), so a new entry
   or thread is held without a change here; the engine versions read the lab folder; the images copy it
   (scripts/check_image_imports.mjs follows the alias, tests/image-imports.test.ts of each worker). */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const LAB = 'apps/edge-bff/terminal/src/lab/index.ts';
const read = (f: string) => fs.readFileSync(path.join(ROOT, f), 'utf8');

/** The files a service's package.json runs (the start command and the registry scripts). */
function scriptEntries(pkg: string): string[] {
  const dir = path.dirname(pkg), scripts = JSON.parse(read(pkg)).scripts as Record<string, string>;
  return Object.entries(scripts).filter(([name]) => name === 'start' || name.startsWith('registry'))
    .flatMap(([, cmd]) => [...cmd.matchAll(/(?:^|\s)((?:\.\.?\/)?[\w./-]+\.(?:ts|mjs))(?=\s|$)/g)].map(m => m[1]))
    .filter(f => !f.includes('loader/register.mjs'))
    .map(f => path.posix.normalize(path.posix.join(dir, f)));
}

/** The thread files a worker's sources start: a module that starts itself (new Worker(new URL(import.meta.url))) and any
    module named for loading at run time (new URL('./<file>.ts', import.meta.url), the Screener's pool script). */
function threadEntries(srcDir: string): string[] {
  const out: string[] = [];
  for (const f of fs.readdirSync(path.join(ROOT, srcDir)).filter(n => n.endsWith('.ts'))) {
    const rel = `${srcDir}/${f}`, src = read(rel);
    if (/new Worker\(new URL\(import\.meta\.url\)/.test(src)) out.push(rel);
    for (const m of src.matchAll(/new URL\('(\.\/[\w.-]+\.ts)', import\.meta\.url\)/g)) out.push(path.posix.join(srcDir, m[1]));
  }
  return out;
}

const ENTRIES = [
  ...scriptEntries('apps/backtest-worker/package.json'), ...threadEntries('apps/backtest-worker/src'),
  ...scriptEntries('apps/screener-worker/package.json'), ...threadEntries('apps/screener-worker/src'),
  ...scriptEntries('apps/edge-bff/screener/package.json').filter(f => f.includes('registry')),
];

test('every Node process that runs a formula loads the lab registration point first', () => {
  const unique = [...new Set(ENTRIES)];
  for (const must of ['apps/backtest-worker/src/server.ts', 'apps/backtest-worker/src/compute.ts', 'apps/backtest-worker/scripts/build-registry.mjs',
    'apps/screener-worker/src/server.ts', 'apps/screener-worker/src/thread.ts', 'apps/edge-bff/screener/scripts/build-screener-registry.mjs'])
    assert.ok(unique.includes(must), `the derivation misses ${must}: ${unique.join(', ')}`);
  // '@edge-lab' (the loader maps it) or a relative path to the same module (a file vitest loads too: the generators)
  const loads = (f: string) => [...read(f).matchAll(/^import '([^']+)';/gm)].some(m => m[1] === '@edge-lab'
    || path.posix.normalize(path.posix.join(path.posix.dirname(f), m[1])) === LAB);
  const missing = unique.filter(f => !loads(f));
  assert.deepEqual(missing, [], `these entries do not import '@edge-lab' (add it before their other imports): ${missing.join(', ')}`);
});

test("the workers' loader resolves '@edge-lab' to the Terminal's lab module", async () => {
  const resolved = import.meta.resolve('@edge-lab');
  assert.equal(fileURLToPath(resolved), path.join(ROOT, LAB));
});

test('both engine versions read the lab folder, so a lab formula changes the version like a released one', () => {
  for (const f of ['apps/backtest-worker/src/version.ts', 'apps/screener-worker/src/version.ts'])
    assert.match(read(f), /\['apps\/edge-bff\/terminal\/src\/lab', \/\\\.ts\$\/\]/, f);
});
