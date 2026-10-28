/* The configuration (config.ts; report 6.17, 8.9: every worker limit is an environment variable with no default, the
   service does not start without it) and the start-up checks (version.ts; TEST PLAN 10b.10 "Start-up check"). */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { test } from 'node:test';
import { describeConfig, loadConfig } from '../src/config.ts';
import { ENGINE_VERSION, REPO_ROOT, checkStartup, engineVersion } from '../src/version.ts';
import { KEY, PROXY, envFor } from './helpers.ts';

const URL0 = 'http://127.0.0.1:9';

test('every limit is required: leaving any one out refuses to start, naming the variable and never a value', () => {
  const full = envFor(URL0);
  loadConfig(full);
  for (const k of Object.keys(full)) {
    const env = { ...full }; delete env[k];
    assert.throws(() => loadConfig(env), (e: unknown) => (e as Error).message.startsWith(`${k} is required`) && !(e as Error).message.includes(KEY), k);
  }
});

test('values are checked: whole numbers, key lengths, origins, the cap budget against the defaults, the owner budget against one request', () => {
  const bad = (over: Record<string, string>, re: RegExp) => assert.throws(() => loadConfig(envFor(URL0, over)), re);
  bad({ SCREENER_THREADS: '0' }, /SCREENER_THREADS must be a whole number of at least 1/);
  bad({ SCREENER_QUEUE: '1.5' }, /SCREENER_QUEUE must be a whole number/);
  bad({ SCREENER_WORKER_KEY: 'short' }, /SCREENER_WORKER_KEY must be at least 32 characters/);
  bad({ TERMINAL_PROXY_KEY: 'short' }, /TERMINAL_PROXY_KEY must be at least 32 characters/);
  bad({ TERMINAL_URL: 'http://u:p@host' }, /user name or password/);
  bad({ TERMINAL_URL: 'http://host/path' }, /origin without a path/);
  bad({ SCREENER_FILE_ORIGIN: 'ftp://bucket' }, /SCREENER_FILE_ORIGIN must be/);
  bad({ SCREENER_CAP_BUDGET_MS: '1' }, /SCREENER_CAP_BUDGET_MS is too low/);
  bad({ SCREENER_MAX_CPU_MS: '1000', SCREENER_OWNER_CPU_MS: '999' }, /SCREENER_OWNER_CPU_MS must be at least SCREENER_MAX_CPU_MS/);
  bad({ SCREENER_CACHE_DIR: '/tmp/x' }, /SCREENER_CACHE_DIR_BYTES is required/);
  const c = loadConfig(envFor(URL0, { SCREENER_CACHE_DIR: '/tmp/x', SCREENER_CACHE_DIR_BYTES: '1000' }));
  assert.equal(c.terminal.maxFileBytes, c.limits.max_inflated_bytes, 'the inflate cap is TerminalClient maxFileBytes');
  assert.equal(c.terminal.cacheBytes, 0);
  const shown = JSON.stringify(describeConfig(c));
  assert.ok(!shown.includes(KEY) && !shown.includes(PROXY), 'no key in the start log');
});

test('screener_engine is a content hash of the files that decide a number, and of the Node major', () => {
  assert.match(ENGINE_VERSION, /^[0-9a-f]{16}$/);
  assert.equal(engineVersion(), ENGINE_VERSION);
  assert.notEqual(engineVersion(REPO_ROOT, '23'), ENGINE_VERSION, 'another Node major is another engine');
  // a copy of the sources with one byte changed in the screener core hashes differently
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'engine-'));
  for (const d of ['apps/edge-bff/screener/src/core', 'apps/screener-worker/src', 'apps/edge-bff/backtest/src/core', 'apps/edge-bff/terminal/src/calc']) fs.cpSync(path.join(REPO_ROOT, d), path.join(tmp, d), { recursive: true });
  fs.mkdirSync(path.join(tmp, 'apps/backtest-worker/src'), { recursive: true });
  fs.copyFileSync(path.join(REPO_ROOT, 'apps/backtest-worker/src/terminal.ts'), path.join(tmp, 'apps/backtest-worker/src/terminal.ts'));
  assert.equal(engineVersion(tmp), ENGINE_VERSION, 'the same files give the same version wherever they are');
  fs.appendFileSync(path.join(tmp, 'apps/edge-bff/screener/src/core/match.ts'), '\n');
  assert.notEqual(engineVersion(tmp), ENGINE_VERSION);
  fs.rmSync(tmp, { recursive: true, force: true });
});

test('the start-up check passes on this tree and names a source whose hash differs from what the registry was built from', async () => {
  const ok = await checkStartup();
  assert.deepEqual(ok.problems, []);
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'startup-'));
  for (const f of ['apps/edge-bff/backtest/src/core/backtest-registry.json', 'apps/edge-bff/terminal/src/data/indRegistry.json', 'apps/edge-bff/terminal/src/calc/indicators.ts',
    'apps/edge-bff/screener/src/core/screener-overlay.json', 'apps/edge-bff/screener/scripts/build-screener-registry.mjs']) {
    fs.mkdirSync(path.dirname(path.join(tmp, f)), { recursive: true }); fs.copyFileSync(path.join(REPO_ROOT, f), path.join(tmp, f));
  }
  assert.deepEqual((await checkStartup(tmp)).problems, [], 'the oracle script is build-only');
  fs.appendFileSync(path.join(tmp, 'apps/edge-bff/screener/src/core/screener-overlay.json'), ' ');
  fs.rmSync(path.join(tmp, 'apps/edge-bff/screener/scripts/build-screener-registry.mjs'));
  const bad = await checkStartup(tmp);
  assert.ok(bad.problems.some(p => /screener-overlay\.json \(overlay\) has sha256/.test(p)), bad.problems.join('; '));
  assert.ok(bad.problems.some(p => /build-screener-registry\.mjs \(generator\) is not in the image/.test(p)));
  fs.rmSync(tmp, { recursive: true, force: true });
});
