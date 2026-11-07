/* Tests of the Backtest tripwire (check_backtest_untouched.mjs, EXEC-MU-RUNTIME and EXEC-SCREENER-FLOW-CANDLES K2 A) on a
   throwaway git repository made from this tree's files (the tripwire, the worker, the core, the Terminal's formulas,
   Feature 04, a short EXEC.md), whose `origin/main` is its first commit:
   - a change to a formula or Feature 04 path fails, with or without a record, and no record can be made over it;
   - a core change without a core record fails (as before K2 A); recorded (--record-core: an EXEC section, the user's
     decision and its date) it passes; any further core change, a file git does not track yet included, fails again
     until recorded again; a record naming no EXEC section, without the decision or its date, or with versions of other
     sources, fails; a core record approves no worker change and a worker baseline no core change;
   - a worker change without a baseline fails; recorded (--record, an EXEC section) it passes; any further worker change,
     a test or an untracked file too, fails again until recorded again; a baseline naming no EXEC section, or with
     versions of other sources, fails.
   Run from the repository root: node --test scripts/screener/check_backtest_untouched.test.mjs */
import assert from 'node:assert/strict';
import { execFileSync, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { after, before, test } from 'node:test';
import { fileURLToPath } from 'node:url';

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const COPIED = ['scripts/screener/check_backtest_untouched.mjs', 'apps/backtest-worker', 'apps/edge-bff/backtest/src/core',
  'apps/edge-bff/terminal/src/calc', 'apps/edge-bff/terminal/src/data/indRegistry.json', 'features/feature04',
  'apps/feature-04-worker', 'apps/stockbit-updater', '.gitignore'];
const EXEC = '# Executions\n\n## EXEC-MU-RUNTIME — test section\n\nApproved for the test.\n\n## EXEC-SCREENER — another\n\n## EXEC-SCREENER-FLOW-CANDLES — the core approval\n';
const BASELINE = 'scripts/screener/backtest_worker_baseline.json';
const CORE_BASELINE = 'scripts/screener/backtest_core_baseline.json';
let dir = '';

const git = (...args) => execFileSync('git', ['-C', dir, ...args], { encoding: 'utf8' });
function tripwire(...args) {
  const r = spawnSync(process.execPath, ['--experimental-strip-types', '--no-warnings=ExperimentalWarning', '--import',
    './apps/backtest-worker/loader/register.mjs', 'scripts/screener/check_backtest_untouched.mjs', ...args], { cwd: dir, encoding: 'utf8' });
  return { code: r.status, out: r.stdout + r.stderr };
}
const record = (section = 'EXEC-MU-RUNTIME') => tripwire('--record', '--exec', section, '--decision', 'Tahap 0, ukur (test)', '--note', 'log fields (test)');
const recordCore = (section = 'EXEC-SCREENER-FLOW-CANDLES', date = '2026-11-07') =>
  tripwire('--record-core', '--exec', section, '--decision', '"2A" and K2 "A" (test)', ...(date ? ['--date', date] : []), '--note', 'candle patterns (test)');
const append = (file, text) => fs.appendFileSync(path.join(dir, file), text);
const restore = () => { git('checkout', '--', '.'); git('clean', '-fdq', '--', 'apps', 'features'); for (const f of [BASELINE, CORE_BASELINE]) fs.rmSync(path.join(dir, f), { force: true }) };

before(() => {
  dir = fs.mkdtempSync(path.join(os.tmpdir(), 'tripwire-test-'));
  // this tree's tracked files of the copied paths, as they are now (the tripwire runs on the worktree's own code)
  const files = execFileSync('git', ['-C', REPO, 'ls-files', '--cached', '--others', '--exclude-standard', '--', ...COPIED], { encoding: 'utf8' }).trim().split('\n');
  for (const f of files) {
    if (!fs.existsSync(path.join(REPO, f))) continue;
    fs.mkdirSync(path.dirname(path.join(dir, f)), { recursive: true });
    fs.copyFileSync(path.join(REPO, f), path.join(dir, f));
  }
  fs.writeFileSync(path.join(dir, 'EXEC.md'), EXEC);
  git('init', '-q');
  git('-c', 'user.name=t', '-c', 'user.email=t@t', 'add', '-A');
  git('-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-qm', 'main');
  git('update-ref', 'refs/remotes/origin/main', 'HEAD');
});
after(() => fs.rmSync(dir, { recursive: true, force: true }));

test('unchanged: OK, the core and the worker as the base', () => {
  const r = tripwire();
  assert.equal(r.code, 0, r.out);
  assert.match(r.out, /apps\/edge-bff\/backtest\/src\/core unchanged/);
  assert.match(r.out, /apps\/backtest-worker unchanged/);
});

test('a change to a formula or Feature 04 path fails, no record approves it, and none can be recorded over it', () => {
  try {
    for (const [file, text] of [['apps/edge-bff/terminal/src/calc/indicators.ts', '\n// changed\n'], ['features/feature04/NEW.md', 'new\n']]) {
      append(file, text);
      const r = tripwire();
      assert.equal(r.code, 1, r.out);
      assert.match(r.out, /formula or Feature 04 paths differ|untracked files in formula or Feature 04 paths/);
      assert.ok(r.out.includes(file), r.out);
      for (const rec of [record(), recordCore()]) {
        assert.equal(rec.code, 1, rec.out);
        assert.match(rec.out, /NOT recorded/);
      }
      assert.ok(!fs.existsSync(path.join(dir, BASELINE)) && !fs.existsSync(path.join(dir, CORE_BASELINE)));
      restore();
    }
    // with records that approve a core and a worker change, a formula change still fails
    append('apps/edge-bff/backtest/src/core/engine.ts', '\n// approved core change\n');
    assert.equal(recordCore().code, 0);
    append('apps/backtest-worker/src/server.ts', '\n// approved log line\n');
    assert.equal(record().code, 0);
    assert.equal(tripwire().code, 0);
    append('apps/edge-bff/terminal/src/data/indRegistry.json', '\n');
    const r = tripwire();
    assert.equal(r.code, 1, r.out);
    assert.match(r.out, /formula or Feature 04 paths differ from origin\/main \(no record approves these\): apps\/edge-bff\/terminal\/src\/data\/indRegistry\.json/);
  } finally { restore() }
});

test('a core change fails without its record (as before K2 A), passes once recorded with the decision, and fails again on any further core change', () => {
  try {
    append('apps/edge-bff/backtest/src/core/engine.ts', '\n// changed\n');
    let r = tripwire();
    assert.equal(r.code, 1, r.out);
    assert.match(r.out, /apps\/edge-bff\/backtest\/src\/core differs from origin\/main \(apps\/edge-bff\/backtest\/src\/core\/engine\.ts\) and no recorded approval approves it: scripts\/screener\/backtest_core_baseline\.json is missing/);
    // a worker baseline is no approval of a core change, and cannot be recorded over one
    r = record();
    assert.equal(r.code, 1, r.out);
    assert.match(r.out, /baseline NOT recorded/);
    // a core record needs an EXEC section and the date of the decision
    r = recordCore('EXEC-NOT-THERE');
    assert.equal(r.code, 1, r.out);
    assert.match(r.out, /exec\.section "EXEC-NOT-THERE" is not a section of EXEC\.md/);
    r = recordCore('EXEC-SCREENER-FLOW-CANDLES', '');
    assert.equal(r.code, 1, r.out);
    assert.match(r.out, /exec\.date \(the date of the user's decision, YYYY-MM-DD\) is missing/);
    r = recordCore();
    assert.equal(r.code, 0, r.out);
    const b = JSON.parse(fs.readFileSync(path.join(dir, CORE_BASELINE), 'utf8'));
    assert.deepEqual([b.exec.section, b.exec.date], ['EXEC-SCREENER-FLOW-CANDLES', '2026-11-07']);
    assert.match(b.exec.decision, /2A/);
    assert.equal(b.base_commit, git('rev-parse', 'origin/main').trim());
    assert.notEqual(b.engine_version, b.base_engine_version);          // a core change changes engine_version
    assert.match(b.core_tree, /^[0-9a-f]{64}$/);
    r = tripwire();
    assert.equal(r.code, 0, r.out);
    assert.match(r.out, /apps\/edge-bff\/backtest\/src\/core as approved by EXEC-SCREENER-FLOW-CANDLES \(scripts\/screener\/backtest_core_baseline\.json, decision of 2026-11-07/);
    assert.ok(r.out.includes(`engine_version ${b.engine_version}`), r.out);
    // a further change anywhere in the core, a file git does not track yet included: not approved
    for (const [file, text] of [['apps/edge-bff/backtest/src/core/conditions.ts', '\n// more\n'], ['apps/edge-bff/backtest/src/core/extra.ts', 'export {};\n']]) {
      const at = path.join(dir, file), before = fs.existsSync(at) ? fs.readFileSync(at) : null;
      append(file, text);
      r = tripwire();
      assert.equal(r.code, 1, r.out);
      assert.match(r.out, /and from the tree scripts\/screener\/backtest_core_baseline\.json approves/);
      if (before === null) fs.rmSync(at); else fs.writeFileSync(at, before);
    }
    assert.equal(tripwire().code, 0);
    // a core record approves no worker change: that needs its own baseline (recorded on the approved core)
    append('apps/backtest-worker/tests/server.test.ts', '\n// a worker test\n');
    r = tripwire();
    assert.equal(r.code, 1, r.out);
    assert.match(r.out, /apps\/backtest-worker differs from origin\/main \(apps\/backtest-worker\/tests\/server\.test\.ts\) and no recorded baseline approves it/);
    assert.equal(record('EXEC-SCREENER-FLOW-CANDLES').code, 0);
    r = tripwire();
    assert.equal(r.code, 0, r.out);
    assert.match(r.out, /core as approved by EXEC-SCREENER-FLOW-CANDLES.*apps\/backtest-worker as approved by EXEC-SCREENER-FLOW-CANDLES/);
    git('checkout', '--', 'apps/backtest-worker'); fs.rmSync(path.join(dir, BASELINE));
    // a record with another engine_version (made on other sources), without the decision or its date, or not JSON, fails
    for (const change of [{ engine_version: '0'.repeat(16) }, { registry_version: 'f'.repeat(16) }, { exec: { section: 'EXEC-SCREENER-FLOW-CANDLES', decision: '', date: '2026-11-07' } },
      { exec: { section: 'EXEC-SCREENER-FLOW-CANDLES', decision: '2A' } }, { exec: { section: 'EXEC-GONE', decision: '2A', date: '2026-11-07' } }, { note: '' }]) {
      fs.writeFileSync(path.join(dir, CORE_BASELINE), JSON.stringify({ ...b, ...change }));
      r = tripwire();
      assert.equal(r.code, 1, `${JSON.stringify(change)}: ${r.out}`);
    }
    fs.writeFileSync(path.join(dir, CORE_BASELINE), '{not json');
    assert.match(tripwire().out, /backtest_core_baseline\.json is not JSON/);
  } finally { restore() }
});

test('the core as the base passes whatever an old core record says, and no core record is made without a core change', () => {
  try {
    append('apps/edge-bff/backtest/src/core/engine.ts', '\n// approved core change\n');
    assert.equal(recordCore().code, 0);
    git('checkout', '--', 'apps/edge-bff/backtest/src/core');
    let r = tripwire();
    assert.equal(r.code, 0, r.out);
    assert.match(r.out, /apps\/edge-bff\/backtest\/src\/core unchanged/);
    r = recordCore();
    assert.equal(r.code, 1, r.out);
    assert.match(r.out, /there is no core change to approve/);
  } finally { restore() }
});

test('a worker change fails without a baseline, passes once recorded, and fails again on any further worker change', () => {
  try {
    append('apps/backtest-worker/src/server.ts', '\n// approved log line\n');
    let r = tripwire();
    assert.equal(r.code, 1, r.out);
    assert.match(r.out, /apps\/backtest-worker differs from origin\/main \(apps\/backtest-worker\/src\/server\.ts\) and no recorded baseline approves it/);
    // an EXEC section EXEC.md does not have is no approval
    r = record('EXEC-NOT-THERE');
    assert.equal(r.code, 1, r.out);
    assert.match(r.out, /exec\.section "EXEC-NOT-THERE" is not a section of EXEC\.md/);
    r = record();
    assert.equal(r.code, 0, r.out);
    const b = JSON.parse(fs.readFileSync(path.join(dir, BASELINE), 'utf8'));
    assert.equal(b.exec.section, 'EXEC-MU-RUNTIME');
    assert.equal(b.base_commit, git('rev-parse', 'origin/main').trim());
    assert.notEqual(b.engine_version, b.base_engine_version);        // a worker src change changes engine_version
    r = tripwire();
    assert.equal(r.code, 0, r.out);
    assert.match(r.out, /apps\/backtest-worker as approved by EXEC-MU-RUNTIME/);
    assert.ok(r.out.includes(`engine_version ${b.engine_version}`), r.out);
    // a further change anywhere in the worker, a test or a file git does not track yet included: not approved
    for (const [file, text] of [['apps/backtest-worker/tests/server.test.ts', '\n// more\n'], ['apps/backtest-worker/src/extra.ts', 'export {};\n']]) {
      const at = path.join(dir, file), before = fs.existsSync(at) ? fs.readFileSync(at) : null;
      append(file, text);
      r = tripwire();
      assert.equal(r.code, 1, r.out);
      assert.match(r.out, /and from the tree scripts\/screener\/backtest_worker_baseline\.json approves/);
      if (before === null) fs.rmSync(at); else fs.writeFileSync(at, before);
    }
    assert.equal(tripwire().code, 0);
    // a baseline with another engine_version (recorded on other sources) or without an EXEC section fails
    for (const change of [{ engine_version: '0'.repeat(16) }, { exec: { section: 'EXEC-GONE', decision: 'x' } }, { note: '' }]) {
      fs.writeFileSync(path.join(dir, BASELINE), JSON.stringify({ ...b, ...change }));
      r = tripwire();
      assert.equal(r.code, 1, `${JSON.stringify(change)}: ${r.out}`);
    }
    fs.writeFileSync(path.join(dir, BASELINE), '{not json');
    assert.match(tripwire().out, /backtest_worker_baseline\.json is not JSON/);
  } finally { restore() }
});

test('the worker as the base passes whatever an old baseline says (a revert of an approved change is no new change)', () => {
  try {
    append('apps/backtest-worker/src/server.ts', '\n// approved log line\n');
    assert.equal(record().code, 0);
    git('checkout', '--', 'apps/backtest-worker');
    const r = tripwire();
    assert.equal(r.code, 0, r.out);
    assert.match(r.out, /apps\/backtest-worker unchanged/);
  } finally { restore() }
});
