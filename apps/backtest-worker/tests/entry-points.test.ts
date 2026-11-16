/* EXEC-BACKTEST-REVAMP P0.3: every module of the shared cores loads as the FIRST module of a fresh process. An ES-module
   cycle between the Backtest core and the Screener core fails only for some load orders (a TDZ ReferenceError, e.g.
   "Cannot access 'SCREENER_REGISTRY' before initialization"), so a test that enters elsewhere can pass while a worker
   whose start module loads the cycle first dies at start (Stage A, Agent 3, reproduced on a scratch copy). Each module
   here is its own entry point, in its own process, through the workers' loader. */
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const LOADER = path.join(ROOT, 'apps/backtest-worker/loader/register.mjs');
const DIRS = ['apps/edge-bff/backtest/src/core', 'apps/edge-bff/screener/src/core'];
const ENTRIES = ['apps/backtest-worker/src/version.ts', 'apps/backtest-worker/src/run.ts', 'apps/screener-worker/src/version.ts', 'apps/screener-worker/src/run.ts'];

function modules(): string[] {
  const out: string[] = [];
  const walk = (rel: string) => {
    for (const d of fs.readdirSync(path.join(ROOT, rel), { withFileTypes: true }))
      if (d.isDirectory()) walk(`${rel}/${d.name}`); else if (d.name.endsWith('.ts')) out.push(`${rel}/${d.name}`);
  };
  for (const d of DIRS) walk(d);
  return [...out.sort(), ...ENTRIES];
}

test('every core module and every worker start module loads as the first module of a fresh process', () => {
  const failed: string[] = [];
  for (const m of modules()) {
    try {
      execFileSync(process.execPath, ['--experimental-strip-types', '--no-warnings', '--import', LOADER, '-e', `await import(${JSON.stringify(path.join(ROOT, m))})`],
        { cwd: path.join(ROOT, 'apps/backtest-worker'), stdio: 'pipe', timeout: 60_000 });
    } catch (e) { failed.push(`${m}: ${String((e as { stderr?: Buffer }).stderr ?? e).split('\n').find(l => /Error/.test(l)) ?? 'failed'}`) }
  }
  assert.deepEqual(failed, []);
});
