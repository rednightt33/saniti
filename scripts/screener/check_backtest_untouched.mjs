/* Tripwire of the EDGE Screener build (EXEC-SCREENER, go 2026-10-28; report TARGET ARCHITECTURE 6.1 invariants I3
   "Backtest untouched" and I4 "Feature 04 unchanged", DATABASE / FEATURE CHANGES 7.1 "Must not change", TEST PLAN
   10b.9). It fails (exit 1, each problem named) when, against the base commit (origin/main by default):
   - engineVersion() of apps/backtest-worker/src/version.ts differs: the content hash every Backtest result key carries
     (apps/edge-bff/backtest/src/core/*.ts|json and apps/backtest-worker/src/*.ts), computed on this tree and on the
     base tree by the worker's own function, never a copy of its rule;
   - REGISTRY_VERSION differs: the artifact's registry_version (backtest core registry.ts) or the hash of its sources
     (apps/backtest-worker/scripts/build-registry.mjs registryVersion), and the two must also agree with each other
     (the worker refuses to start otherwise, server.ts registry_mismatch);
   - any protected path differs from the base (`git diff --quiet <base> -- <paths>`, working tree included) or holds a
     file git does not track yet.
   Read-only: git rev-parse, diff, ls-files, show and archive only; nothing is fetched (run `git fetch` yourself when
   the local origin/main may be behind). Run from the repository root:
     node --experimental-strip-types --no-warnings=ExperimentalWarning --import ./apps/backtest-worker/loader/register.mjs \
       scripts/screener/check_backtest_untouched.mjs [--base <commit>] */
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const arg = process.argv.indexOf('--base');
const BASE = arg > 0 ? process.argv[arg + 1] : 'origin/main';
/** report 7.1 "Must not change (tripwire, I3 and I4)"; the Feature 04 tables are checked by the migrations, not here. */
export const PROTECTED = [
  'apps/edge-bff/terminal/src/calc/indicators.ts',
  'apps/edge-bff/terminal/src/data/indRegistry.json',
  'apps/edge-bff/backtest/src/core',
  'apps/backtest-worker',
  'features/feature04',
  'apps/feature-04-worker',
  'apps/stockbit-updater',
];
const ENGINE_DIRS = ['apps/edge-bff/backtest/src/core', 'apps/backtest-worker/src'];
const ARTIFACT = 'apps/edge-bff/backtest/src/core/backtest-registry.json';

const git = (args, opts = {}) => execFileSync('git', ['-C', ROOT, ...args], { encoding: 'utf8', maxBuffer: 64 << 20, ...opts });
const problems = [];

const base = git(['rev-parse', '--verify', `${BASE}^{commit}`]).trim();

// protected paths: no diff against the base (tracked files, working tree included) and no untracked file in them
try { git(['diff', '--quiet', base, '--', ...PROTECTED]) }
catch (e) {
  if (e.status !== 1) throw e;
  const names = git(['diff', '--name-only', base, '--', ...PROTECTED]).trim().split('\n').filter(Boolean);
  problems.push(`protected paths differ from ${BASE}: ${names.join(', ')}`);
}
const untracked = git(['ls-files', '--others', '--exclude-standard', '--', ...PROTECTED]).trim().split('\n').filter(Boolean);
if (untracked.length) problems.push(`untracked files in protected paths: ${untracked.join(', ')}`);

// engine_version and registry_version, by the backtest worker's own functions
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
if (engine !== baseEngine) problems.push(`engine_version ${engine} differs from ${BASE}'s ${baseEngine}`);
if (REGISTRY_VERSION !== baseRegistry) problems.push(`registry_version ${REGISTRY_VERSION} (backtest-registry.json) differs from ${BASE}'s ${baseRegistry}`);
if (sources !== REGISTRY_VERSION) problems.push(`the registry's sources hash to ${sources}, the artifact says ${REGISTRY_VERSION} (backtest-worker would refuse to start)`);

if (problems.length) {
  console.error(`Backtest tripwire FAILED against ${BASE} ${base.slice(0, 12)}:\n  - ${problems.join('\n  - ')}`);
  process.exit(1);
}
console.log(`Backtest tripwire OK against ${BASE} ${base.slice(0, 12)}: engine_version ${engine}, registry_version ${REGISTRY_VERSION}; ${PROTECTED.length} protected paths unchanged.`);
