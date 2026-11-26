/* The generated screener-registry.json is current (report 6.8; TEST PLAN 10b.10 "Generated registry"): the generator's
   --check re-derives every probe field (and the oracle, through python3) and fails on any diff. It is reproducible: the
   same bytes when every clock jumps at random (tests/core/noisy-clock.mjs), so no field depends on how long anything
   took, and (REGISTRY_LOAD_TEST=1, not in the default run because it saturates every core) five checks in a row pass
   while busy loops hold three times as many runnable processes as there are cores. The timeouts are wide because a
   loaded machine slows the check without changing its answer: since re-check round 3 (2026-11-26, ERRORS M568) the
   effective-window probe plants every split size the data holds on the eight real-price fixtures, and one check takes
   about 9.5 minutes of one core (93 % of it that probe: 232 probes, 393 s on the real fixtures, 106 s on the shapes,
   measured 2026-11-26), so two run at a time (the check against a raised class is the plain check's run) under
   CHECK_TIMEOUT. Plain JavaScript,
   because it spawns a process (node:child_process; the app's TypeScript has no Node typings, as the Backtest page). */
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { describe, expect, it } from 'vitest';

const HERE = path.dirname(fileURLToPath(import.meta.url)), APP = path.resolve(HERE, '../..');
/** build-screener-registry.mjs --check as npm run registry:check starts it, with extra environment and arguments
    (mode null: without --check, as npm run registry starts it). */
const check = (env = {}, args = [], mode = '--check') => new Promise((resolve, reject) => {
  const p = spawn(process.execPath, ['--experimental-strip-types', '--no-warnings=ExperimentalWarning', '--import', '../../backtest-worker/loader/register.mjs',
    'scripts/build-screener-registry.mjs', ...(mode ? [mode] : []), ...args], { cwd: APP, env: { ...process.env, ...env } });
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

// the committed registry with one parameter's cost class set to `cls` (the generator compares the classes it derives
// with git HEAD; --against names this file instead), in a new temporary directory
const reg = () => JSON.parse(fs.readFileSync(path.join(APP, 'src/core/screener-registry.json'), 'utf8'));
const find = (doc, cls) => doc.indicators.flatMap(r => r.params.filter(p => p.cost_class === cls).map(p => ({ r, p })))[0];
const at = (doc, x) => doc.indicators.find(r => r.id === x.r.id).params.find(p => p.key === x.p.key);
const withClass = (dir, name, x, cls) => { const doc = reg(), f = path.join(dir, name); at(doc, x).cost_class = cls; fs.writeFileSync(f, JSON.stringify(doc)); return f };
// two full checks run at a time (about 9.5 minutes of one core each, see the head) plus the rest of the suite
const CHECK_TIMEOUT = 1_500_000;

describe('screener-registry.json', () => {
  it.concurrent('is current: build-screener-registry.mjs --check finds no diff, and lets a raised cost class through', async () => {
    // one run for both (re-check round 3: each full check is long): currency is read against the committed file on disk
    // whatever --against names, and the classes against a registry that had an O(N·n) parameter as O(N) before, a raise
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'registry-raised-'));
    try {
      expectCurrent(await check({}, ['--against', withClass(dir, 'raised.json', find(reg(), 'O(N·n)'), 'O(N)')]));
    } finally {
      fs.rmSync(dir, { recursive: true, force: true });
    }
  }, CHECK_TIMEOUT);

  it.concurrent('is current when every clock of the generator and its cost probe jumps at random', async () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'noisy-clock-')), log = path.join(dir, 'pids');
    try {
      const noisy = `--import=${pathToFileURL(path.join(HERE, 'noisy-clock.mjs')).href}`;
      expectCurrent(await check({ NODE_OPTIONS: `${process.env.NODE_OPTIONS ?? ''} ${noisy}`.trim(), NOISY_CLOCK_LOG: log }));
      expect(fs.readFileSync(log, 'utf8').trim().split('\n').length).toBeGreaterThanOrEqual(2);   // the generator and its probe child
    } finally {
      fs.rmSync(dir, { recursive: true, force: true });
    }
  }, CHECK_TIMEOUT);

  it.concurrent('refuses a regeneration that lowers a committed O(N·n) class to O(N) without a reviewed reason', async () => {
    // the committed registry as it would be had a parameter the probe derives O(N) been O(N·n) before; a raise is let
    // through by the first test's run. Both refusals stop before the effective-window probe (build: the cost classes
    // are compared first), so this test costs one cost probe, not a full check
    const was = find(reg(), 'O(N)');
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'registry-against-'));
    try {
      const lowered = withClass(dir, 'lowered.json', was, 'O(N·n)');
      const before = fs.readFileSync(path.join(APP, 'src/core/screener-registry.json'));
      const [refused, writing] = await Promise.all([check({}, ['--against', lowered]), check({}, ['--against', lowered], null)]);
      // --against is a check's: a regeneration that writes is always compared with the committed registry, so the flag
      // never lets a lowered class be written (review of the last guards); nothing is written
      expect([writing.status, writing.stdout]).toEqual([2, '']);
      expect(writing.stderr).toContain('--against <registry file> is for --check only');
      expect(fs.readFileSync(path.join(APP, 'src/core/screener-registry.json')).equals(before)).toBe(true);
      expect(refused.status).toBe(1);
      expect(refused.stdout).toBe('');
      expect(refused.stderr).toContain(`cost_class lowered: the regeneration derives O(N) for ${was.r.id}.${was.p.key} (${was.r.name}), which ${lowered} has as O(N·n)`);
      for (const part of ['\nRule: ', '\nHow to pass: ', `\nRight: {"indicator":"${was.r.id}","param":"${was.p.key}","from":"O(N·n)","to":"O(N)"`, '\nWrong: ']) expect(refused.stderr).toContain(part);
    } finally {
      fs.rmSync(dir, { recursive: true, force: true });
    }
  }, CHECK_TIMEOUT);

  it.runIf(process.env.REGISTRY_LOAD_TEST === '1')('is current in 5 of 5 checks under full synthetic CPU load', async () => {
    const busy = Array.from({ length: 3 * os.availableParallelism() }, () => spawn(process.execPath, ['-e', 'for(;;){}'], { stdio: 'ignore' }));
    try {
      for (let k = 0; k < 5; k++) expectCurrent(await check());
    } finally {
      for (const b of busy) b.kill('SIGKILL');
    }
  }, 5 * CHECK_TIMEOUT);
});
