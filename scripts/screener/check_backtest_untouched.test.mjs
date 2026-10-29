/* Tests of the Backtest tripwire (check_backtest_untouched.mjs, EXEC-MU-RUNTIME): on a throwaway git repository made
   from this tree's files (the tripwire, the worker, the core, the Terminal's formulas, Feature 04, a short EXEC.md),
   whose `origin/main` is its first commit:
   - a Screener-side change to a formula or core path fails, with or without a baseline, and a baseline cannot be
     recorded over it;
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
const EXEC = '# Executions\n\n## EXEC-MU-RUNTIME — test section\n\nApproved for the test.\n\n## EXEC-SCREENER — another\n';
const BASELINE = 'scripts/screener/backtest_worker_baseline.json';
let dir = '';

const git = (...args) => execFileSync('git', ['-C', dir, ...args], { encoding: 'utf8' });
function tripwire(...args) {
  const r = spawnSync(process.execPath, ['--experimental-strip-types', '--no-warnings=ExperimentalWarning', '--import',
    './apps/backtest-worker/loader/register.mjs', 'scripts/screener/check_backtest_untouched.mjs', ...args], { cwd: dir, encoding: 'utf8' });
  return { code: r.status, out: r.stdout + r.stderr };
}
const record = (section = 'EXEC-MU-RUNTIME') => tripwire('--record', '--exec', section, '--decision', 'Tahap 0, ukur (test)', '--note', 'log fields (test)');
const append = (file, text) => fs.appendFileSync(path.join(dir, file), text);
const restore = () => { git('checkout', '--', '.'); git('clean', '-fdq', '--', 'apps', 'features'); fs.rmSync(path.join(dir, BASELINE), { force: true }) };

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

test('unchanged: OK, the worker as the base', () => {
  const r = tripwire();
  assert.equal(r.code, 0, r.out);
  assert.match(r.out, /apps\/backtest-worker unchanged/);
});

test('a Screener-side change to a formula or core path fails, a baseline approves none, and none can be recorded over it', () => {
  try {
    for (const [file, text] of [['apps/edge-bff/backtest/src/core/engine.ts', '\n// changed\n'],
      ['apps/edge-bff/terminal/src/calc/indicators.ts', '\n// changed\n'], ['features/feature04/NEW.md', 'new\n']]) {
      append(file, text);
      const r = tripwire();
      assert.equal(r.code, 1, r.out);
      assert.match(r.out, /formula, core or Feature 04 paths differ|untracked files in formula, core or Feature 04 paths/);
      assert.ok(r.out.includes(file), r.out);
      const rec = record();
      assert.equal(rec.code, 1, rec.out);
      assert.match(rec.out, /baseline NOT recorded/);
      assert.ok(!fs.existsSync(path.join(dir, BASELINE)));
      restore();
    }
    // with a baseline that approves a worker change, a core change still fails
    append('apps/backtest-worker/src/server.ts', '\n// approved log line\n');
    assert.equal(record().code, 0);
    append('apps/edge-bff/backtest/src/core/engine.ts', '\n// changed\n');
    const r = tripwire();
    assert.equal(r.code, 1, r.out);
    assert.match(r.out, /formula, core or Feature 04 paths differ from origin\/main \(no baseline approves these\): apps\/edge-bff\/backtest\/src\/core\/engine\.ts/);
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
