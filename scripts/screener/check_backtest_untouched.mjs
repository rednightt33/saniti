/* Tripwire of the EDGE Screener build (EXEC-SCREENER, go 2026-10-28; report TARGET ARCHITECTURE 6.1 invariants I3
   "Backtest untouched" and I4 "Feature 04 unchanged", DATABASE / FEATURE CHANGES 7.1 "Must not change", TEST PLAN
   10b.9), with the approved Backtest worker changes of EXEC-MU-RUNTIME (go 2026-10-28; Phase 0 "waktu per fase
   Backtest, request_key dan preview_wait_ms di log", Phase 2 the Backtest runtime). The Screener never changes the
   Backtest engine, its formulas or Feature 04; the Backtest worker may change, but only as a recorded approval says.
   It fails (exit 1, each problem named) when, against the base commit (origin/main by default):
   - ALWAYS (the formulas and the engine core, Feature 04, the Stockbit updater) differs from the base
     (`git diff --quiet <base> -- <paths>`, working tree included) or holds a file git does not track yet: no baseline
     can approve that;
   - apps/backtest-worker differs from the base and the recorded baseline (BASELINE, a JSON file committed with the
     change) does not approve exactly this tree: its `worker_tree` is the content hash of every file under
     apps/backtest-worker (tracked or not yet tracked, ignored files aside; workerTree), so any other worker change,
     a test or the Dockerfile included, fails until a new baseline is recorded and committed;
   - engine_version (apps/backtest-worker/src/version.ts engineVersion, the content hash every Backtest result carries:
     the core's *.ts|json and the worker's src/*.ts, computed by the worker's own function on this tree and on the
     base tree, never a copy of its rule) or REGISTRY_VERSION (the artifact's, core registry.ts) is not the base's
     while the worker is unchanged, or not the baseline's while the baseline approves the worker: a baseline recorded
     on other sources is stale;
   - the baseline names an EXEC section that is not a heading of EXEC.md, or lacks the fields it must have;
   - the registry's sources (apps/backtest-worker/scripts/build-registry.mjs registryVersion) disagree with the
     artifact (the worker refuses to start then, server.ts registry_mismatch).
   A baseline names the base commit it was approved against (`base_commit`, for the reviewer's
   `git diff <base_commit> -- apps/backtest-worker`; informational: the guarantee is the content hash, which survives
   cherry-picks and rebases, ERRORS lesson MU-E1), the commit it was recorded on, the versions and the EXEC section
   with the user's words. Only a deliberate commit changes it: the check never writes; `--record --exec <section>
   --decision <user's words> --note <what changed>` writes BASELINE from this tree (refused while ALWAYS differs) and
   prints it, for the commit that carries the approved worker change.
   Read-only besides --record: git rev-parse, diff, ls-files, show and archive only; nothing is fetched (run
   `git fetch` yourself when the local origin/main may be behind). Run from the repository root:
     node --experimental-strip-types --no-warnings=ExperimentalWarning --import ./apps/backtest-worker/loader/register.mjs \
       scripts/screener/check_backtest_untouched.mjs [--base <commit>] [--record --exec <section> --decision <text> --note <text>] */
import crypto from 'node:crypto';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const option = name => { const k = process.argv.indexOf(name); return k > 0 ? process.argv[k + 1] : undefined };
const BASE = option('--base') ?? 'origin/main';
/** report 7.1 "Must not change (tripwire, I3 and I4)": never changed by the Screener build or by a baseline; the
    Feature 04 tables are checked by the migrations, not here. */
export const ALWAYS = [
  'apps/edge-bff/terminal/src/calc/indicators.ts',
  'apps/edge-bff/terminal/src/data/indRegistry.json',
  'apps/edge-bff/backtest/src/core',
  'features/feature04',
  'apps/feature-04-worker',
  'apps/stockbit-updater',
];
/** changed only as BASELINE approves (EXEC-MU-RUNTIME) */
export const WORKER = 'apps/backtest-worker';
export const PROTECTED = [...ALWAYS, WORKER];
export const BASELINE = 'scripts/screener/backtest_worker_baseline.json';
const ENGINE_DIRS = ['apps/edge-bff/backtest/src/core', 'apps/backtest-worker/src'];
const ARTIFACT = 'apps/edge-bff/backtest/src/core/backtest-registry.json';

const git = (args, opts = {}) => execFileSync('git', ['-C', ROOT, ...args], { encoding: 'utf8', maxBuffer: 64 << 20, ...opts });
const lines = text => text.trim().split('\n').filter(Boolean);
const sha256 = b => crypto.createHash('sha256').update(b).digest('hex');

/** The files of `paths` that differ from the base (tracked, working tree included) and those git does not track yet. */
function changedFrom(base, paths) {
  let changed = [];
  try { git(['diff', '--quiet', base, '--', ...paths]) }
  catch (e) { if (e.status !== 1) throw e; changed = lines(git(['diff', '--name-only', base, '--', ...paths])) }
  return { changed, untracked: lines(git(['ls-files', '--others', '--exclude-standard', '--', ...paths])) };
}
/** The content hash of a directory as it is: sha256 over the sorted lines `<path> \t <sha256 of the file>` of every
    file git tracks or would track there (ignored files aside); a tracked file that is gone counts as `-`. */
export function workerTree(dir = WORKER) {
  const files = [...new Set(lines(git(['ls-files', '--cached', '--others', '--exclude-standard', '--', dir])))].sort();
  const entries = files.map(f => { const at = path.join(ROOT, f); return `${f}\t${fs.existsSync(at) ? sha256(fs.readFileSync(at)) : '-'}` });
  return { hash: sha256(entries.join('\n')), files: files.length };
}
/** The EXEC.md sections (`## <name> — ...` headings), by name. */
function execSections() {
  const at = path.join(ROOT, 'EXEC.md');
  const text = fs.existsSync(at) ? fs.readFileSync(at, 'utf8') : '';
  return new Set([...text.matchAll(/^## (EXEC-[A-Z0-9-]+)\b/gm)].map(m => m[1]));
}
const HEX = /^[0-9a-f]+$/;
/** The baseline's problems (empty when it is well formed and names an EXEC section). */
function baselineProblems(b, sections) {
  const out = [];
  if (!b || typeof b !== 'object') return [`${BASELINE} is not a JSON object`];
  if (b.schema !== 1) out.push(`${BASELINE}: schema must be 1`);
  for (const k of ['base_commit', 'recorded_on', 'engine_version', 'registry_version', 'worker_tree'])
    if (typeof b[k] !== 'string' || !HEX.test(b[k])) out.push(`${BASELINE}: ${k} must be a hex string`);
  if (!b.exec || typeof b.exec.section !== 'string' || !sections.has(b.exec.section))
    out.push(`${BASELINE}: exec.section ${JSON.stringify(b.exec?.section ?? null)} is not a section of EXEC.md (an approval names the EXEC section that records it)`);
  if (!b.exec || typeof b.exec.decision !== 'string' || !b.exec.decision.trim()) out.push(`${BASELINE}: exec.decision (the user's words) is missing`);
  if (typeof b.note !== 'string' || !b.note.trim()) out.push(`${BASELINE}: note (what the approved change is) is missing`);
  return out;
}

const problems = [];
const base = git(['rev-parse', '--verify', `${BASE}^{commit}`]).trim();

// 1. the formulas, the core and Feature 04: as the base, always
const always = changedFrom(base, ALWAYS);
if (always.changed.length) problems.push(`formula, core or Feature 04 paths differ from ${BASE} (no baseline approves these): ${always.changed.join(', ')}`);
if (always.untracked.length) problems.push(`untracked files in formula, core or Feature 04 paths: ${always.untracked.join(', ')}`);

// 2. the versions, by the backtest worker's own functions, here and on the base tree
const { engineVersion, REGISTRY_VERSION } = await import(pathToFileURL(path.join(ROOT, 'apps/backtest-worker/src/version.ts')).href);
const { registryVersion } = await import(pathToFileURL(path.join(ROOT, 'apps/backtest-worker/scripts/build-registry.mjs')).href);
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'screener-tripwire-'));
let baseEngine;
try {
  const tar = path.join(tmp, 'base.tar');
  fs.writeFileSync(tar, execFileSync('git', ['-C', ROOT, 'archive', '--format=tar', base, ...ENGINE_DIRS], { maxBuffer: 64 << 20 }));
  fs.mkdirSync(path.join(tmp, 'tree'));
  execFileSync('tar', ['-xf', tar, '-C', path.join(tmp, 'tree')]);
  baseEngine = engineVersion(path.join(tmp, 'tree'));
} finally { fs.rmSync(tmp, { recursive: true, force: true }) }
const engine = engineVersion(ROOT);
const baseRegistry = JSON.parse(git(['show', `${base}:${ARTIFACT}`])).registry_version;
const sources = registryVersion();
if (sources !== REGISTRY_VERSION) problems.push(`the registry's sources hash to ${sources}, the artifact says ${REGISTRY_VERSION} (backtest-worker would refuse to start)`);
const tree = workerTree();

if (process.argv.includes('--record')) {
  const section = option('--exec'), decision = option('--decision'), note = option('--note');
  const recorded = {
    schema: 1,
    about: 'The approved state of apps/backtest-worker for scripts/screener/check_backtest_untouched.mjs: the tripwire passes a worker that differs from origin/main only while its content hash is worker_tree and the versions are these. Recorded with --record and changed only by a deliberate commit (EXEC-MU-RUNTIME).',
    base_commit: base, recorded_on: git(['rev-parse', 'HEAD']).trim(), recorded_at: new Date().toISOString().slice(0, 10),
    engine_version: engine, base_engine_version: baseEngine, registry_version: REGISTRY_VERSION,
    worker_tree: tree.hash, worker_files: tree.files, exec: { section, decision }, note,
  };
  const refused = [...problems, ...baselineProblems(recorded, execSections())];
  if (refused.length) {
    console.error(`Backtest baseline NOT recorded:\n  - ${refused.join('\n  - ')}`);
    process.exit(1);
  }
  fs.writeFileSync(path.join(ROOT, BASELINE), JSON.stringify(recorded, null, 2) + '\n');
  console.log(`Backtest baseline recorded in ${BASELINE} (commit it with the worker change):\n${JSON.stringify(recorded, null, 2)}`);
  process.exit(0);
}

// 3. the worker: as the base, or exactly as the recorded baseline approves
const worker = changedFrom(base, [WORKER]);
let mode;
if (!worker.changed.length && !worker.untracked.length) {
  mode = `${WORKER} unchanged`;
  if (engine !== baseEngine) problems.push(`engine_version ${engine} differs from ${BASE}'s ${baseEngine}`);
  if (REGISTRY_VERSION !== baseRegistry) problems.push(`registry_version ${REGISTRY_VERSION} (backtest-registry.json) differs from ${BASE}'s ${baseRegistry}`);
} else {
  const named = [...worker.changed, ...worker.untracked.map(f => `${f} (untracked)`)].join(', ');
  const at = path.join(ROOT, BASELINE);
  let b = null;
  if (fs.existsSync(at)) { try { b = JSON.parse(fs.readFileSync(at, 'utf8')) } catch { b = 'unreadable' } }
  if (b === null) problems.push(`${WORKER} differs from ${BASE} (${named}) and no recorded baseline approves it: ${BASELINE} is missing (an approved change records it with --record and commits it)`);
  else if (b === 'unreadable') problems.push(`${WORKER} differs from ${BASE} (${named}) and ${BASELINE} is not JSON`);
  else {
    const bad = baselineProblems(b, execSections());
    problems.push(...bad);
    if (b.worker_tree !== tree.hash)
      problems.push(`${WORKER} differs from ${BASE} (${named}) and from the tree ${BASELINE} approves (worker_tree ${String(b.worker_tree).slice(0, 12)}…, this tree ${tree.hash.slice(0, 12)}…): a worker change needs its own approval, recorded with --record and committed`);
    else {
      if (engine !== b.engine_version) problems.push(`engine_version ${engine} is not the baseline's ${b.engine_version} (the baseline was recorded on other sources)`);
      if (REGISTRY_VERSION !== b.registry_version) problems.push(`registry_version ${REGISTRY_VERSION} is not the baseline's ${b.registry_version}`);
    }
    if (!bad.length) mode = `${WORKER} as approved by ${b.exec.section} (${BASELINE}, against ${String(b.base_commit).slice(0, 12)})`;
  }
}

if (problems.length) {
  console.error(`Backtest tripwire FAILED against ${BASE} ${base.slice(0, 12)}:\n  - ${problems.join('\n  - ')}`);
  process.exit(1);
}
console.log(`Backtest tripwire OK against ${BASE} ${base.slice(0, 12)}: ${ALWAYS.length} formula, core and Feature 04 paths unchanged; ${mode}; engine_version ${engine}, registry_version ${REGISTRY_VERSION}.`);
