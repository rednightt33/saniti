/* The generated screener-registry.json is current (report 6.8; TEST PLAN 10b.10 "Generated registry"): the generator's
   --check re-derives every probe field (and the oracle, through python3) and fails on any diff. Plain JavaScript,
   because it spawns a process (node:child_process; the app's TypeScript has no Node typings, as the Backtest page). */
import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const APP = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');

describe('screener-registry.json', () => {
  it('is current: build-screener-registry.mjs --check finds no diff', () => {
    const r = spawnSync(process.execPath, ['--experimental-strip-types', '--no-warnings=ExperimentalWarning', '--import', '../../backtest-worker/loader/register.mjs',
      'scripts/build-screener-registry.mjs', '--check'], { cwd: APP, encoding: 'utf8' });
    expect(r.stderr).toBe('');
    expect(r.status).toBe(0);
    expect(r.stdout).toContain('is current');
  }, 120_000);
});
