/* Tests of the Backtest tripwire (check_backtest_untouched.mjs, EXEC-MU-RUNTIME, EXEC-SCREENER-FLOW-CANDLES K2 A and
   EXEC-TRIPWIRE-LAB) on a throwaway git repository made from this tree's files (the tripwire, the worker, the core, the
   paths engine_version reads (the worker's own SOURCES: the Terminal's calc and lab modules, the Flow registry, the
   Screener core), the Terminal's indicator registry, Feature 04, a short EXEC.md), whose `origin/main` is its first
   commit:
   - a change to a Feature 04 path fails, with or without a record, and no record can be made over it; a change to a
     formula path fails without a release record, and no core or worker record approves it or is made over it;
   - an indicator release (a registry row and its lab formula, the registry artifact regenerated): refused without its
     release record; --record-release (the ids, an EXEC section, the user's words and their date) records it, refused
     with an id no registry has, a row it does not name, or a field missing; then the core and worker records as usual,
     and the tripwire passes; any further formula change fails again until recorded again; a release record that is not
     JSON or lacks a field approves nothing;
   - the release stays within its ids: a row of another id changed, gone or added, and a formula of calc/indicators.ts
     of another id added or computing otherwise (at its defaults or with one parameter moved) are refused; an export
     alone (Part A step 1) is no formula change;
   - a lab formula or a Flow registry entry alone (the core and the worker the base's) moves engine_version: refused
     without a release record, a worker baseline is no approval of it, passes as the release record says, fails again
     on a further change, and passes again once back at the base; with nothing changed there is no release to record;
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
const NODE = ['--experimental-strip-types', '--no-warnings=ExperimentalWarning', '--import', './apps/backtest-worker/loader/register.mjs'];
// the paths engine_version reads come from the worker's own list (a fixed list here lost the lab module, the Flow
// registry and the Screener core when SOURCES grew, and every test failed on the loader's '@edge-lab')
const SOURCES = JSON.parse(execFileSync(process.execPath, [...NODE, '--input-type=module', '-e',
  "const m = await import('./apps/backtest-worker/src/version.ts'); console.log(JSON.stringify(m.SOURCES.map(s => s[0])))"], { cwd: REPO, encoding: 'utf8' }));
const COPIED = [...new Set(['scripts/screener/check_backtest_untouched.mjs', 'apps/backtest-worker', 'apps/edge-bff/backtest/src/core',
  'apps/edge-bff/terminal/src/calc', 'apps/edge-bff/terminal/src/data/indRegistry.json', 'features/feature04',
  'apps/feature-04-worker', 'apps/stockbit-updater', '.gitignore', ...SOURCES])];
const EXEC = '# Executions\n\n## EXEC-MU-RUNTIME — test section\n\nApproved for the test.\n\n## EXEC-SCREENER — another\n\n## EXEC-SCREENER-FLOW-CANDLES — the core approval\n\n## EXEC-PINE-INDICATORS — the release\n';
const BASELINE = 'scripts/screener/backtest_worker_baseline.json';
const CORE_BASELINE = 'scripts/screener/backtest_core_baseline.json';
const RELEASE = 'scripts/screener/backtest_release_record.json';
const CALC = 'apps/edge-bff/terminal/src/calc/indicators.ts';
const REG = 'apps/edge-bff/terminal/src/data/indRegistry.json';
const LAB = 'apps/edge-bff/terminal/src/lab/index.ts';
let dir = '';

const git = (...args) => execFileSync('git', ['-C', dir, ...args], { encoding: 'utf8' });
function tripwire(...args) {
  const r = spawnSync(process.execPath, [...NODE, 'scripts/screener/check_backtest_untouched.mjs', ...args], { cwd: dir, encoding: 'utf8' });
  return { code: r.status, out: r.stdout + r.stderr };
}
const record = (section = 'EXEC-MU-RUNTIME') => tripwire('--record', '--exec', section, '--decision', 'Tahap 0, ukur (test)', '--note', 'log fields (test)');
const recordCore = (section = 'EXEC-SCREENER-FLOW-CANDLES', date = '2026-11-07') =>
  tripwire('--record-core', '--exec', section, '--decision', '"2A" and K2 "A" (test)', ...(date ? ['--date', date] : []), '--note', 'candle patterns (test)');
const recordRelease = (ids = 'I61', { section = 'EXEC-PINE-INDICATORS', decision = '"Ok", "Hanya di beta saja for now ya" (test)', date = '2026-11-23' } = {}) =>
  tripwire('--record-release', '--exec', section, ...(decision ? ['--decision', decision] : []), ...(date ? ['--date', date] : []),
    ...(ids ? ['--ids', ids] : []), '--note', 'a lab indicator (test)');
const append = (file, text) => fs.appendFileSync(path.join(dir, file), text);
const restore = () => { git('checkout', '--', '.'); git('clean', '-fdq', '--', 'apps', 'features'); for (const f of [BASELINE, CORE_BASELINE, RELEASE]) fs.rmSync(path.join(dir, f), { force: true }) };
const rows = () => JSON.parse(fs.readFileSync(path.join(dir, REG), 'utf8'));
const writeRows = r => fs.writeFileSync(path.join(dir, REG), JSON.stringify(r, null, 0));
/** the registry artifact from the changed sources (`npm run registry` in apps/backtest-worker): a core change */
function regen() {
  const r = spawnSync(process.execPath, [...NODE, 'apps/backtest-worker/scripts/build-registry.mjs'], { cwd: dir, encoding: 'utf8' });
  assert.equal(r.status, 0, r.stdout + r.stderr);
}
/** Part A steps 2, 3 and 6: a registry row I61 (I01's fields under its own key), its formula in the lab module, the
    artifact regenerated */
function labIndicator() {
  const r = rows();
  writeRows([...r, { ...r[0], id: 'I61', key: 'tw_sma', name: 'Tripwire SMA', short: 'TWSMA' }]);
  append(LAB, '\nDEFAULTS.tw_sma = { ...DEFAULTS.sma };\nF.tw_sma = F.sma;\n');
  regen();
}

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
  assert.match(r.out, /5 formula and Feature 04 paths unchanged/);
  assert.match(r.out, /apps\/edge-bff\/backtest\/src\/core unchanged/);
  assert.match(r.out, /apps\/backtest-worker unchanged/);
});

test('a change to a formula or Feature 04 path fails without a record; no core or worker record approves it or is made over it, and no release record over Feature 04', () => {
  try {
    for (const [file, text] of [[CALC, '\n// changed\n'], ['features/feature04/NEW.md', 'new\n']]) {
      append(file, text);
      const r = tripwire();
      assert.equal(r.code, 1, r.out);
      assert.match(r.out, /formula or Feature 04 paths differ|untracked files in formula or Feature 04 paths/);
      assert.ok(r.out.includes(file), r.out);
      for (const rec of [record(), recordCore(), ...(file.startsWith('features/') ? [recordRelease('I54')] : [])]) {
        assert.equal(rec.code, 1, rec.out);
        assert.match(rec.out, /NOT recorded/);
      }
      assert.ok(!fs.existsSync(path.join(dir, BASELINE)) && !fs.existsSync(path.join(dir, CORE_BASELINE)) && !fs.existsSync(path.join(dir, RELEASE)));
      restore();
    }
    // with records that approve a core and a worker change, a formula change still fails
    append('apps/edge-bff/backtest/src/core/engine.ts', '\n// approved core change\n');
    assert.equal(recordCore().code, 0);
    append('apps/backtest-worker/src/server.ts', '\n// approved log line\n');
    assert.equal(record().code, 0);
    assert.equal(tripwire().code, 0);
    append(REG, '\n');
    const r = tripwire();
    assert.equal(r.code, 1, r.out);
    assert.match(r.out, /formula or Feature 04 paths differ from origin\/main \(no record approves these\): apps\/edge-bff\/terminal\/src\/data\/indRegistry\.json/);
  } finally { restore() }
});

test('an indicator release passes only as --record-release records it (ids, an EXEC section, the user\'s words and their date), then the core and worker records as usual', () => {
  try {
    labIndicator();
    let r = tripwire();
    assert.equal(r.code, 1, r.out);
    assert.match(r.out, /formula or Feature 04 paths differ from origin\/main \(no record approves these\): apps\/edge-bff\/terminal\/src\/data\/indRegistry\.json \(an indicator release the user approved is recorded with --record-release and committed: scripts\/screener\/backtest_release_record\.json is missing\)/);
    // the core and worker records come after the release record, and are refused before it
    for (const rec of [recordCore('EXEC-PINE-INDICATORS', '2026-11-23'), record('EXEC-PINE-INDICATORS')]) {
      assert.equal(rec.code, 1, rec.out);
      assert.match(rec.out, /NOT recorded[\s\S]*--record-release/);
    }
    // refused: an id no registry has, a release that does not name the row it adds, no user's words, no date, an EXEC
    // section EXEC.md does not have, no ids
    for (const [rec, message] of [
      [recordRelease('I61,I99'), /--ids I99: no row of indRegistry\.json or flowRegistry\.json has this id/],
      [recordRelease('I54'), /indRegistry\.json: the row I61 \(tw_sma\) is added, and the release does not name I61/],
      [recordRelease('I61', { decision: null }), /exec\.decision \(the user's words\) is missing/],
      [recordRelease('I61', { date: null }), /exec\.date \(the date of the user's decision, YYYY-MM-DD\) is missing/],
      [recordRelease('I61', { section: 'EXEC-NOT-THERE' }), /exec\.section "EXEC-NOT-THERE" is not a section of EXEC\.md/],
      [recordRelease(null), /ids must name the indicators the release carries/],
      [recordRelease('I61,I61'), /ids name an indicator twice/],
    ]) {
      assert.equal(rec.code, 1, rec.out);
      assert.match(rec.out, /Backtest release record NOT recorded/);
      assert.match(rec.out, message);
    }
    assert.ok(!fs.existsSync(path.join(dir, RELEASE)));
    r = recordRelease('I61');
    assert.equal(r.code, 0, r.out);
    const b = JSON.parse(fs.readFileSync(path.join(dir, RELEASE), 'utf8'));
    assert.deepEqual([b.ids, b.exec.section, b.exec.date], [['I61'], 'EXEC-PINE-INDICATORS', '2026-11-23']);
    assert.match(b.exec.decision, /Hanya di beta saja for now ya/);
    assert.equal(b.base_commit, git('rev-parse', 'origin/main').trim());
    assert.match(b.formula_tree, /^[0-9a-f]{64}$/);
    assert.notEqual(b.engine_version, b.base_engine_version);         // the lab formula moves engine_version
    assert.notEqual(b.registry_version, b.base_registry_version);     // the registry row moves registry_version
    // the formula paths pass now; the core still needs its own record
    r = tripwire();
    assert.equal(r.code, 1, r.out);
    assert.doesNotMatch(r.out, /formula or Feature 04 paths differ|the formula paths/);
    assert.match(r.out, /apps\/edge-bff\/backtest\/src\/core differs from origin\/main \(apps\/edge-bff\/backtest\/src\/core\/backtest-registry\.json\) and no recorded approval approves it/);
    assert.equal(recordCore('EXEC-PINE-INDICATORS', '2026-11-23').code, 0);
    r = tripwire();
    assert.equal(r.code, 0, r.out);
    assert.match(r.out, /3 Feature 04 paths unchanged, the formulas as released by EXEC-PINE-INDICATORS \(I61; scripts\/screener\/backtest_release_record\.json, decision of 2026-11-23/);
    assert.match(r.out, /core as approved by EXEC-PINE-INDICATORS/);
    // a worker change of the release follows with its own baseline
    append('apps/backtest-worker/tests/lookahead.test.ts', '\n// a case of the new indicator (test)\n');
    assert.equal(tripwire().code, 1);
    assert.equal(record('EXEC-PINE-INDICATORS').code, 0);
    assert.equal(tripwire().code, 0);
    // a release record that is not JSON, lacks a field, or names other ids or another tree approves nothing
    for (const change of [{ ids: [] }, { ids: ['I54'] }, { formula_tree: '0'.repeat(64) }, { note: '' },
      { exec: { section: 'EXEC-PINE-INDICATORS', decision: 'Ok' } }, { exec: { section: 'EXEC-GONE', decision: 'Ok', date: '2026-11-23' } }]) {
      fs.writeFileSync(path.join(dir, RELEASE), JSON.stringify({ ...b, ...change }));
      r = tripwire();
      assert.equal(r.code, 1, `${JSON.stringify(change)}: ${r.out}`);
      assert.match(r.out, /the formula paths differ from origin\/main \(.*\) and scripts\/screener\/backtest_release_record\.json does not approve them/);
    }
    fs.writeFileSync(path.join(dir, RELEASE), '{not json');
    assert.match(tripwire().out, /backtest_release_record\.json is not JSON/);
    fs.writeFileSync(path.join(dir, RELEASE), JSON.stringify(b, null, 2) + '\n');
    assert.equal(tripwire().code, 0);
    // any further formula change fails again until recorded again
    append(CALC, '\n// more (test)\n');
    regen();
    r = tripwire();
    assert.equal(r.code, 1, r.out);
    assert.match(r.out, /the formula paths are not the tree scripts\/screener\/backtest_release_record\.json approves/);
    git('checkout', '--', CALC);
    regen();
    assert.equal(tripwire().code, 0);
    // a Feature 04 change: no release record approves it, none is made over it
    append('features/feature04/NEW.md', 'new\n');
    assert.equal(tripwire().code, 1);
    r = recordRelease('I61');
    assert.equal(r.code, 1, r.out);
    assert.match(r.out, /untracked files in formula or Feature 04 paths: features\/feature04\/NEW\.md/);
  } finally { restore() }
});

test('a release stays within its ids: another id\'s row or formula changed, gone or added is refused; an export alone is no formula change', () => {
  try {
    // an export (Part A step 1) changes no formula
    append(CALC, '\nexport const TRIPWIRE_TEST_EXPORT = 1;\n');
    regen();
    let r = recordRelease('I54');
    assert.equal(r.code, 0, r.out);
    restore();
    // a released formula that computes otherwise at its defaults, or only with one parameter moved
    for (const [patch, params] of [['v * 1.001', '{}'], ["p?.source === 'hl2' ? v + 1 : v", '{"source":"hl2"}']]) {
      append(CALC, `\nconst twSma = F.sma;\nF.sma = (B, p) => { const o = twSma(B, p); return { sma: o.sma.map(v => v === null ? null : ${patch}) } };\n`);
      regen();
      r = recordRelease('I54');
      assert.equal(r.code, 1, r.out);
      assert.ok(r.out.includes(`calc/indicators.ts: the formula sma (I01) computes otherwise than origin/main's (parameters ${params} on the probe series`), r.out);
      assert.equal(recordRelease('I01').code, 0);               // a release that names it (the user's words say so)
      restore();
    }
    // a formula moved into calc/indicators.ts (Part B) for an id the release does not name
    const r0 = rows();
    writeRows([...r0, { ...r0[0], id: 'I61', key: 'tw_pub', name: 'Tripwire public SMA' }]);
    append(CALC, '\nDEFAULTS.tw_pub = { ...DEFAULTS.sma };\nF.tw_pub = F.sma;\n');
    regen();
    r = recordRelease('I54');
    assert.equal(r.code, 1, r.out);
    assert.match(r.out, /calc\/indicators\.ts: the formula tw_pub \(I61\) is added, and the release does not name it/);
    assert.match(r.out, /indRegistry\.json: the row I61 \(tw_pub\) is added, and the release does not name I61/);
    assert.equal(recordRelease('I61').code, 0);
    restore();
    // a row of another id changed or gone
    for (const [edit, message] of [[x => x.map(y => y.id === 'I02' ? { ...y, name: 'EMA (changed)' } : y), /the row I02 \(ema\) is changed, and the release does not name I02/],
      [x => x.filter(y => y.id !== 'I60'), /the row I60 \(alpha_divergence\) is gone, and the release does not name I60/]]) {
      writeRows(edit(rows()));
      regen();
      r = recordRelease('I54');
      assert.equal(r.code, 1, r.out);
      assert.match(r.out, message);
      restore();
    }
    // the same rows with their keys in another order are no change
    writeRows(rows().map(y => Object.fromEntries(Object.entries(y).reverse())));
    regen();
    assert.equal(recordRelease('I54').code, 0);
  } finally { restore() }
});

test('a lab formula or a Flow registry entry alone (the core and the worker the base\'s): the versions pass only as the release record says', () => {
  try {
    append(LAB, '\n// a fix of a lab formula (test)\n');
    let r = tripwire();
    assert.equal(r.code, 1, r.out);
    assert.match(r.out, /engine_version [0-9a-f]{16} differs from origin\/main's [0-9a-f]{16} \(a change the user approved is recorded and committed: a lab formula or a Flow registry entry with --record-release/);
    // a worker baseline is no approval while the worker is the base's
    assert.equal(record().code, 0);
    assert.equal(tripwire().code, 1);
    fs.rmSync(path.join(dir, BASELINE));
    r = recordRelease('FL99');
    assert.equal(r.code, 1, r.out);
    assert.match(r.out, /--ids FL99: no row of indRegistry\.json or flowRegistry\.json has this id/);
    r = recordRelease('FL01');
    assert.equal(r.code, 0, r.out);
    r = tripwire();
    assert.equal(r.code, 0, r.out);
    assert.match(r.out, /5 formula and Feature 04 paths unchanged; .*apps\/backtest-worker unchanged; the versions as released by EXEC-PINE-INDICATORS \(FL01; /);
    // a further change fails again until recorded again
    append('apps/edge-bff/terminal/src/data/flowRegistry.json', '\n');
    r = tripwire();
    assert.equal(r.code, 1, r.out);
    assert.match(r.out, /backtest_release_record\.json was made on other sources/);
    git('checkout', '--', 'apps/edge-bff/terminal/src/data/flowRegistry.json');
    assert.equal(tripwire().code, 0);
    // back at the base: passes whatever the old release record says, and there is no release to record
    git('checkout', '--', LAB);
    r = tripwire();
    assert.equal(r.code, 0, r.out);
    assert.doesNotMatch(r.out, /released by/);
    r = recordRelease('I54');
    assert.equal(r.code, 1, r.out);
    assert.match(r.out, /the formula paths and the versions are as origin\/main's: there is no release to record/);
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
