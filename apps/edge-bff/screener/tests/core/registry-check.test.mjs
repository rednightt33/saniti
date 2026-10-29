/* The generated screener-registry.json is current (report 6.8; TEST PLAN 10b.10 "Generated registry"): the generator's
   --check re-derives every probe field (and the oracle, through python3) and fails on any diff. It is reproducible: the
   same bytes when every clock jumps at random (tests/core/noisy-clock.mjs), so no field depends on how long anything
   took, and (REGISTRY_LOAD_TEST=1, not in the default run because it saturates every core) five checks in a row pass
   while busy loops hold three times as many runnable processes as there are cores. The timeouts are wide because a
   loaded machine slows the check (about 50 s at load 13 on 4 cores) without changing its answer. Plain JavaScript,
   because it spawns a process (node:child_process; the app's TypeScript has no Node typings, as the Backtest page). */
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { describe, expect, it } from 'vitest';

const HERE = path.dirname(fileURLToPath(import.meta.url)), APP = path.resolve(HERE, '../..');
/** build-screener-registry.mjs --check as npm run registry:check starts it, with extra environment. */
const check = (env = {}) => new Promise((resolve, reject) => {
  const p = spawn(process.execPath, ['--experimental-strip-types', '--no-warnings=ExperimentalWarning', '--import', '../../backtest-worker/loader/register.mjs',
    'scripts/build-screener-registry.mjs', '--check'], { cwd: APP, env: { ...process.env, ...env } });
  let stdout = '', stderr = '';
  p.stdout.on('data', d => { stdout += d });
  p.stderr.on('data', d => { stderr += d });
  p.on('error', reject);
  p.on('close', status => resolve({ status, stdout, stderr }));
});
const expectCurrent = r => {
  expect(r.stderr).toBe('');
  expect(r.status).toBe(0);
  expect(r.stdout).toContain('is current');
};

describe('screener-registry.json', () => {
  it.concurrent('is current: build-screener-registry.mjs --check finds no diff', async () => {
    expectCurrent(await check());
  }, 600_000);

  it.concurrent('is current when every clock of the generator and its cost probe jumps at random', async () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'noisy-clock-')), log = path.join(dir, 'pids');
    try {
      const noisy = `--import=${pathToFileURL(path.join(HERE, 'noisy-clock.mjs')).href}`;
      expectCurrent(await check({ NODE_OPTIONS: `${process.env.NODE_OPTIONS ?? ''} ${noisy}`.trim(), NOISY_CLOCK_LOG: log }));
      expect(fs.readFileSync(log, 'utf8').trim().split('\n').length).toBeGreaterThanOrEqual(2);   // the generator and its probe child
    } finally {
      fs.rmSync(dir, { recursive: true, force: true });
    }
  }, 600_000);

  it.runIf(process.env.REGISTRY_LOAD_TEST === '1')('is current in 5 of 5 checks under full synthetic CPU load', async () => {
    const busy = Array.from({ length: 3 * os.availableParallelism() }, () => spawn(process.execPath, ['-e', 'for(;;){}'], { stdio: 'ignore' }));
    try {
      for (let k = 0; k < 5; k++) expectCurrent(await check());
    } finally {
      for (const b of busy) b.kill('SIGKILL');
    }
  }, 1_800_000);
});
