/* Tripwire of the EDGE Screener build (EXEC-SCREENER, go 2026-10-28; report TARGET ARCHITECTURE 6.1 invariants I3
   "Backtest untouched" and I4 "Feature 04 unchanged", DATABASE / FEATURE CHANGES 7.1 "Must not change", TEST PLAN
   10b.9), with the approved Backtest worker changes of EXEC-MU-RUNTIME (go 2026-10-28; Phase 0 "waktu per fase
   Backtest, request_key dan preview_wait_ms di log", Phase 2 the Backtest runtime), the approval path for Backtest
   core changes of EXEC-SCREENER-FLOW-CANDLES (user 2026-11-07, K2 "A": "jalur persetujuan untuk perubahan core Backtest
   di tripwire (seperti baseline worker), ditambah tes bahwa hasil kondisi lama tetap sama"; the first such change is
   P6, the candle patterns, decision "2A") and the release record of an indicator release of EXEC-TRIPWIRE-LAB (ERRORS
   M553; user 2026-11-24: "UD29: ok with opsi A", "Untuk 2-5 bisa go": a lab or released indicator changes the formula
   file and its registry by design, INDICATOR_BETA_TO_LIVE.md Part A and Part B). The Screener never changes the
   Backtest formulas or Feature 04; an indicator release changes the formulas only as its record says; the Backtest core
   and worker may change, but only as a recorded approval says.
   It fails (exit 1, each problem named) when, against the base commit (origin/main by default):
   - the Feature 04 and Stockbit updater paths of ALWAYS (FEATURE04) differ from the base (`git diff --quiet <base> --
     <paths>`, working tree included) or hold a file git does not track yet: no record can approve that;
   - the formula paths of ALWAYS (FORMULAS: the indicator formulas and their registry source) differ from the base and
     the release record (RELEASE_RECORD, a JSON file committed with the release) does not approve exactly this tree:
     its `formula_tree` is the content hash of the two files (treeHash), so any other formula change fails until a new
     record is made and committed; the record names the indicators it releases (`ids`: I.. of indRegistry.json, FL.. of
     flowRegistry.json), the EXEC section, the user's words and their date; and the difference stays within those ids
     (releaseScope): no row of another id added, changed or gone in indRegistry.json, and no formula of calc/indicators.ts
     but theirs added, gone or computing otherwise than the base's (each of the base's formulas run on a fixed series
     at its defaults and with each parameter moved alone, by the base's module and by this tree's; the lab module is not
     an ALWAYS path: engine_version, which the records hold, hashes it);
   - apps/edge-bff/backtest/src/core (CORE) differs from the base and the core record (CORE_BASELINE, a JSON file
     committed with the change) does not approve exactly this tree: its `core_tree` is the content hash of every file
     under the core (tracked or not yet tracked, ignored files aside; treeHash), so any other core change fails until a
     new record is made and committed; the record names the EXEC section, the user's decision and its date;
   - apps/backtest-worker differs from the base and the recorded baseline (BASELINE, a JSON file committed with the
     change) does not approve exactly this tree: its `worker_tree` is the content hash of every file under
     apps/backtest-worker (tracked or not yet tracked, ignored files aside; treeHash), so any other worker change,
     a test or the Dockerfile included, fails until a new baseline is recorded and committed;
   - engine_version (apps/backtest-worker/src/version.ts engineVersion, the content hash every Backtest result carries:
     the core's *.ts|json and the worker's src/*.ts, computed by the worker's own function on this tree and on the
     base tree, never a copy of its rule) or REGISTRY_VERSION (the artifact's, core registry.ts) is not the expected
     one: the base's while neither the core nor the worker changed and no release record approves this tree, the
     release record's while neither changed (a lab formula or a Flow registry entry moves engine_version without a core
     or worker change), the core record's while only the core changed, the worker baseline's while the worker changed
     (a record made on other sources is stale);
   - a record names an EXEC section that is not a heading of EXEC.md, or lacks the fields it must have;
   - the registry's sources (apps/backtest-worker/scripts/build-registry.mjs registryVersion) disagree with the
     artifact (the worker refuses to start then, server.ts registry_mismatch).
   A record names the base commit it was approved against (`base_commit`, for the reviewer's `git diff <base_commit>
   -- <dir>`; informational: the guarantee is the content hash, which survives cherry-picks and rebases, ERRORS lesson
   MU-E1), the commit it was recorded on, the versions and the EXEC section with the user's words. Only a deliberate
   commit changes it: the check never writes. An indicator release records in this order, each refused until the one
   before it is made: the release, the core, the worker;
   - `--record-release --exec <section> --decision <user's words> --date <YYYY-MM-DD of the decision> --ids
     <I54,I55,...> --note <what changed>` writes RELEASE_RECORD from this tree (refused while FEATURE04 differs, an id
     is no registry id, the difference reaches an id it does not name, or neither the formula paths nor the versions
     differ from the base), for the commit that carries the release the user approved (INDICATOR_BETA_TO_LIVE.md
     Part A, Part B, Part C and the lab Flow indicator);
   - `--record --exec <section> --decision <user's words> --note <what changed>` writes BASELINE from this tree (refused
     while FEATURE04 differs, the formula paths differ without their release record, or the core differs without its
     record) and prints it, for the commit that carries the approved worker change;
   - `--record-core --exec <section> --decision <user's words> --date <YYYY-MM-DD of the decision> --note <what
     changed>` writes CORE_BASELINE from this tree (refused while FEATURE04 differs, the formula paths differ without
     their release record, or the core is the base's), for the commit that carries the approved core change; a worker
     change still needs its own baseline.
   Read-only besides the three record modes: git rev-parse, diff, ls-files, show and archive only; nothing is fetched
   (run `git fetch` yourself when the local origin/main may be behind). Run from the repository root:
     node --experimental-strip-types --no-warnings=ExperimentalWarning --import ./apps/backtest-worker/loader/register.mjs \
       scripts/screener/check_backtest_untouched.mjs [--base <commit>] [--record-release ... | --record ... | --record-core ...] */
import crypto from 'node:crypto';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const option = name => { const k = process.argv.indexOf(name); return k > 0 ? process.argv[k + 1] : undefined };
const BASE = option('--base') ?? 'origin/main';
/** report 7.1 "Must not change (tripwire, I3 and I4)": never changed by the Screener build; the Feature 04 tables are
    checked by the migrations, not here. */
export const ALWAYS = [
  'apps/edge-bff/terminal/src/calc/indicators.ts',
  'apps/edge-bff/terminal/src/data/indRegistry.json',
  'features/feature04',
  'apps/feature-04-worker',
  'apps/stockbit-updater',
];
/** the ALWAYS paths an indicator release changes by design (INDICATOR_BETA_TO_LIVE.md Part A steps 1 and 3, Part B
    step 2): changed only as RELEASE_RECORD approves (EXEC-TRIPWIRE-LAB) */
export const FORMULAS = ALWAYS.slice(0, 2);
const [CALC, IND_REGISTRY] = FORMULAS;
/** the other ALWAYS paths: no record approves a change there */
export const FEATURE04 = ALWAYS.filter(p => !FORMULAS.includes(p));
const FLOW_REGISTRY = 'apps/edge-bff/terminal/src/data/flowRegistry.json';
/** changed only as CORE_BASELINE approves (EXEC-SCREENER-FLOW-CANDLES K2 A) */
export const CORE = 'apps/edge-bff/backtest/src/core';
/** changed only as BASELINE approves (EXEC-MU-RUNTIME) */
export const WORKER = 'apps/backtest-worker';
export const PROTECTED = [...ALWAYS, CORE, WORKER];
export const BASELINE = 'scripts/screener/backtest_worker_baseline.json';
export const CORE_BASELINE = 'scripts/screener/backtest_core_baseline.json';
export const RELEASE_RECORD = 'scripts/screener/backtest_release_record.json';
const ARTIFACT = 'apps/edge-bff/backtest/src/core/backtest-registry.json';

const git = (args, opts = {}) => execFileSync('git', ['-C', ROOT, ...args], { encoding: 'utf8', maxBuffer: 64 << 20, ...opts });
const lines = text => text.trim().split('\n').filter(Boolean);
const sha256 = b => crypto.createHash('sha256').update(b).digest('hex');
const short = h => String(h).slice(0, 12);

/** The files of `paths` that differ from the base (tracked, working tree included) and those git does not track yet. */
function changedFrom(base, paths) {
  let changed = [];
  try { git(['diff', '--quiet', base, '--', ...paths]) }
  catch (e) { if (e.status !== 1) throw e; changed = lines(git(['diff', '--name-only', base, '--', ...paths])) }
  return { changed, untracked: lines(git(['ls-files', '--others', '--exclude-standard', '--', ...paths])) };
}
const named = d => [...d.changed, ...d.untracked.map(f => `${f} (untracked)`)];
/** The content hash of directories or files as they are: sha256 over the sorted lines `<path> \t <sha256 of the file>`
    of every file git tracks or would track there (ignored files aside); a tracked file that is gone counts as `-`. */
export function treeHash(dirs) {
  const files = [...new Set(lines(git(['ls-files', '--cached', '--others', '--exclude-standard', '--', ...[dirs].flat()])))].sort();
  const entries = files.map(f => { const at = path.join(ROOT, f); return `${f}\t${fs.existsSync(at) ? sha256(fs.readFileSync(at)) : '-'}` });
  return { hash: sha256(entries.join('\n')), files: files.length };
}
export const workerTree = (dir = WORKER) => treeHash(dir);
/** The EXEC.md sections (`## <name> — ...` headings), by name. */
function execSections() {
  const at = path.join(ROOT, 'EXEC.md');
  const text = fs.existsSync(at) ? fs.readFileSync(at, 'utf8') : '';
  return new Set([...text.matchAll(/^## (EXEC-[A-Z0-9-]+)\b/gm)].map(m => m[1]));
}
const HEX = /^[0-9a-f]+$/, DATE = /^\d{4}-\d{2}-\d{2}$/, ID = /^(I|FL)\d+$/;
/** A record's problems (empty when it is well formed and names an EXEC section); `file` the record, `tree` its tree
    field, `dated` whether the user's decision carries its date (the core and release records). */
function recordProblems(b, sections, file, tree, dated) {
  const out = [];
  if (!b || typeof b !== 'object') return [`${file} is not a JSON object`];
  if (b.schema !== 1) out.push(`${file}: schema must be 1`);
  for (const k of ['base_commit', 'recorded_on', 'engine_version', 'registry_version', tree])
    if (typeof b[k] !== 'string' || !HEX.test(b[k])) out.push(`${file}: ${k} must be a hex string`);
  if (!b.exec || typeof b.exec.section !== 'string' || !sections.has(b.exec.section))
    out.push(`${file}: exec.section ${JSON.stringify(b.exec?.section ?? null)} is not a section of EXEC.md (an approval names the EXEC section that records it)`);
  if (!b.exec || typeof b.exec.decision !== 'string' || !b.exec.decision.trim()) out.push(`${file}: exec.decision (the user's words) is missing`);
  if (dated && !(b.exec && typeof b.exec.date === 'string' && DATE.test(b.exec.date))) out.push(`${file}: exec.date (the date of the user's decision, YYYY-MM-DD) is missing`);
  if (typeof b.note !== 'string' || !b.note.trim()) out.push(`${file}: note (what the approved change is) is missing`);
  return out;
}
const baselineProblems = (b, sections) => recordProblems(b, sections, BASELINE, 'worker_tree', false);
const coreProblems = (b, sections) => recordProblems(b, sections, CORE_BASELINE, 'core_tree', true);
function releaseProblems(b, sections) {
  const out = recordProblems(b, sections, RELEASE_RECORD, 'formula_tree', true);
  if (!b || typeof b !== 'object') return out;
  if (!Array.isArray(b.ids) || !b.ids.length || b.ids.some(i => typeof i !== 'string' || !ID.test(i)))
    out.push(`${RELEASE_RECORD}: ids must name the indicators the release carries by their registry ids (I.. or FL..; --ids I54,I55)`);
  else if (new Set(b.ids).size !== b.ids.length) out.push(`${RELEASE_RECORD}: ids name an indicator twice`);
  return out;
}
/** A record file: null when missing, 'unreadable' when not JSON. */
function readRecord(file) {
  const at = path.join(ROOT, file);
  if (!fs.existsSync(at)) return null;
  try { return JSON.parse(fs.readFileSync(at, 'utf8')) } catch { return 'unreadable' }
}
/** A JSON file of the base (rev) or of this tree (rev null); null when it is not there or not JSON. */
function readJson(rev, file) {
  try { return JSON.parse(rev ? git(['show', `${rev}:${file}`], { stdio: ['ignore', 'pipe', 'ignore'] }) : fs.readFileSync(path.join(ROOT, file), 'utf8')) }
  catch { return null }
}
/** JSON with the keys of every object sorted: a row is "changed" by its values, not by the order of its keys. */
const canonical = v => JSON.stringify(v, (_, x) => x && typeof x === 'object' && !Array.isArray(x) ? Object.fromEntries(Object.keys(x).sort().map(k => [k, x[k]])) : x);

/* The series a formula of the base and of this tree are both run on (releaseScope): 400 daily bars of a seeded random
   walk with a flat bar and a bar without a close (a break restarts every formula). Fixed, so the check is the same on
   every machine; not market data. */
export const RELEASE_PROBE = { bars: 400, seed: 20261124, flat_bar: 120, gap_bar: 260 };
function probeBars() {
  let s = RELEASE_PROBE.seed | 0;
  const rnd = () => { s = (s + 0x6D2B79F5) | 0; let t = Math.imul(s ^ (s >>> 15), 1 | s); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296 };
  const B = { O: [], H: [], L: [], C: [], V: [], T: [] };
  let c = 1000;
  for (let i = 0; i < RELEASE_PROBE.bars; i++) {
    const o = c; c = Math.max(1, c * (1 + (rnd() - 0.5) * 0.05));
    const flat = i === RELEASE_PROBE.flat_bar;
    B.O.push(flat ? c : o); B.H.push(flat ? c : Math.max(o, c) * (1 + rnd() * 0.015)); B.L.push(flat ? c : Math.min(o, c) * (1 - rnd() * 0.015));
    B.C.push(i === RELEASE_PROBE.gap_bar ? null : c); B.V.push(Math.round(1e5 * (0.2 + rnd())));
    B.T.push(new Date(Date.UTC(2024, 0, 1) + i * 864e5).toISOString().slice(0, 10));
  }
  return B;
}
/** The parameters a formula is run with: its defaults ({}), then each registry parameter moved alone (every other
    option of a choice, the other value of a switch, a number halved and raised, within its bounds). */
function probeParams(row) {
  const out = [{}];
  for (const p of row?.params ?? []) {
    if (p.type === 'enum') for (const o of p.opts ?? []) { if (o !== p.def) out.push({ [p.k]: o }) }
    else if (p.type === 'boolean') out.push({ [p.k]: !p.def });
    else if ((p.type === 'integer' || p.type === 'number') && typeof p.def === 'number')
      for (let v of p.type === 'integer' ? [Math.round(p.def / 2), p.def + 3] : [p.def / 2, p.def * 1.5 + 0.1]) {
        if (typeof p.min === 'number') v = Math.max(v, p.min);
        if (typeof p.max === 'number') v = Math.min(v, p.max);
        if (v !== p.def) out.push({ [p.k]: v });
      }
  }
  return out;
}
function runFormula(fn, bars, params) {
  const B = Object.fromEntries(Object.entries(bars).map(([k, v]) => [k, v.slice()]));
  try { return JSON.stringify(fn(B, params)) } catch (e) { return `threw ${e?.message ?? e}` }
}

const problems = [];
const base = git(['rev-parse', '--verify', `${BASE}^{commit}`]).trim();
const sections = execSections();

// 1. Feature 04 and the Stockbit updater: as the base, always
const always = changedFrom(base, FEATURE04);
if (always.changed.length) problems.push(`formula or Feature 04 paths differ from ${BASE} (no record approves these): ${always.changed.join(', ')}`);
if (always.untracked.length) problems.push(`untracked files in formula or Feature 04 paths: ${always.untracked.join(', ')}`);

// 2. the versions, by the backtest worker's own functions, here and on the base tree
const { engineVersion, REGISTRY_VERSION, SOURCES } = await import(pathToFileURL(path.join(ROOT, 'apps/backtest-worker/src/version.ts')).href);
// the paths engine_version reads, from the worker's own list (EXEC-BACKTEST-REVAMP added the Terminal's calc module,
// its flow registry and the Screener core; a fixed list here made the base tree lack them, ERRORS M458)
const ENGINE_DIRS = SOURCES.map(([entry]) => entry);
const { registryVersion } = await import(pathToFileURL(path.join(ROOT, 'apps/backtest-worker/scripts/build-registry.mjs')).href);
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'screener-tripwire-'));
process.on('exit', () => fs.rmSync(tmp, { recursive: true, force: true }));
const tar = path.join(tmp, 'base.tar'), baseTree = path.join(tmp, 'tree');
fs.writeFileSync(tar, execFileSync('git', ['-C', ROOT, 'archive', '--format=tar', base, ...ENGINE_DIRS], { maxBuffer: 64 << 20 }));
fs.mkdirSync(baseTree);
execFileSync('tar', ['-xf', tar, '-C', baseTree]);
const baseEngine = engineVersion(baseTree);
const engine = engineVersion(ROOT);
const baseRegistry = JSON.parse(git(['show', `${base}:${ARTIFACT}`])).registry_version;
const sources = registryVersion();
if (sources !== REGISTRY_VERSION) problems.push(`the registry's sources hash to ${sources}, the artifact says ${REGISTRY_VERSION} (backtest-worker would refuse to start)`);
const versionsAsBase = engine === baseEngine && REGISTRY_VERSION === baseRegistry;

// 3. the formulas: as the base, or exactly as the release record approves and within its ids (EXEC-TRIPWIRE-LAB)
const formulaDiff = changedFrom(base, FORMULAS), formulasChanged = named(formulaDiff).length > 0, formulaNow = treeHash(FORMULAS);
/** The problems of a release that names `ids`: an id no registry has, and a difference of the formula paths from the
    base that reaches an id it does not name (a row of indRegistry.json, a formula of calc/indicators.ts). */
async function releaseScope(ids) {
  const out = [], release = new Set(ids);
  const baseRows = readJson(base, IND_REGISTRY) ?? [], nowRows = readJson(null, IND_REGISTRY) ?? [];
  const known = new Set([...baseRows, ...nowRows, ...(readJson(null, FLOW_REGISTRY)?.indicators ?? [])].map(r => r.id));
  for (const id of ids) if (!known.has(id)) out.push(`--ids ${id}: no row of indRegistry.json or flowRegistry.json has this id (a release names the indicators it carries by their registry ids)`);
  const before = new Map(baseRows.map(r => [r.id, r])), after = new Map(nowRows.map(r => [r.id, r]));
  for (const [id, r] of before) if (!after.has(id) && !release.has(id)) out.push(`${IND_REGISTRY}: the row ${id} (${r.key}) is gone, and the release does not name ${id}`);
  for (const [id, r] of after) {
    if (release.has(id)) continue;
    if (!before.has(id)) out.push(`${IND_REGISTRY}: the row ${id} (${r.key}) is added, and the release does not name ${id}`);
    else if (canonical(before.get(id)) !== canonical(r)) out.push(`${IND_REGISTRY}: the row ${id} (${r.key}) is changed, and the release does not name ${id}`);
  }
  if (!named(changedFrom(base, [CALC])).length) return out;
  // the formulas, by the base's module and by this tree's, both without the lab module ('?public': a module of its own,
  // which the lab formulas the loader registered into this tree's module never reach)
  const baseCalc = path.join(baseTree, CALC);
  if (!fs.existsSync(baseCalc)) { fs.mkdirSync(path.dirname(baseCalc), { recursive: true }); fs.writeFileSync(baseCalc, git(['show', `${base}:${CALC}`])) }
  const was = await import(pathToFileURL(baseCalc).href), now = await import(`${pathToFileURL(path.join(ROOT, CALC)).href}?public`);
  const rows = [...nowRows, ...baseRows], idOf = new Map(rows.map(r => [r.key, r.id])), rowOf = new Map(baseRows.map(r => [r.key, r]));
  const releasedKeys = new Set(rows.filter(r => release.has(r.id)).map(r => r.key));
  const label = k => `${k} (${idOf.get(k) ?? 'no registry row'})`;
  for (const k of Object.keys(was.F)) if (!(k in now.F) && !releasedKeys.has(k)) out.push(`${CALC}: the formula ${label(k)} is gone, and the release does not name it`);
  for (const k of Object.keys(now.F)) if (!(k in was.F) && !releasedKeys.has(k)) out.push(`${CALC}: the formula ${label(k)} is added, and the release does not name it`);
  const bars = probeBars();
  for (const k of Object.keys(was.F)) {
    if (releasedKeys.has(k) || !(k in now.F)) continue;
    const moved = probeParams(rowOf.get(k)).find(p => runFormula(was.F[k], bars, p) !== runFormula(now.F[k], bars, p));
    if (moved) out.push(`${CALC}: the formula ${label(k)} computes otherwise than ${BASE}'s (parameters ${JSON.stringify(moved)} on the probe series, RELEASE_PROBE), and the release does not name it`);
  }
  return out;
}
const releaseOf = b => `${b.exec.section} (${b.ids.join(', ')}; ${RELEASE_RECORD}, decision of ${b.exec.date}, against ${short(b.base_commit)})`;

if (process.argv.includes('--record-release')) {
  const section = option('--exec'), decision = option('--decision'), date = option('--date'), note = option('--note');
  const ids = (option('--ids') ?? '').split(',').map(s => s.trim()).filter(Boolean);
  const recorded = {
    schema: 1,
    about: `The approved indicator release for scripts/screener/check_backtest_untouched.mjs: the tripwire passes ${CALC} and ${IND_REGISTRY} that differ from origin/main only while their content hash is formula_tree and the difference stays within ids (no row of another id added, changed or gone; every other formula computing as the base's), and, while the core and the worker are the base's, only while the versions are these. Recorded with --record-release and changed only by a deliberate commit (EXEC-TRIPWIRE-LAB, ERRORS M553).`,
    base_commit: base, recorded_on: git(['rev-parse', 'HEAD']).trim(), recorded_at: new Date().toISOString().slice(0, 10),
    engine_version: engine, base_engine_version: baseEngine, registry_version: REGISTRY_VERSION, base_registry_version: baseRegistry,
    formula_tree: formulaNow.hash, formula_files: formulaNow.files, ids, exec: { section, decision, date }, note,
  };
  const refused = [...problems, ...releaseProblems(recorded, sections), ...(await releaseScope(ids))];
  if (!formulasChanged && versionsAsBase) refused.push(`the formula paths and the versions are as ${BASE}'s: there is no release to record`);
  if (refused.length) {
    console.error(`Backtest release record NOT recorded:\n  - ${refused.join('\n  - ')}`);
    process.exit(1);
  }
  fs.writeFileSync(path.join(ROOT, RELEASE_RECORD), JSON.stringify(recorded, null, 2) + '\n');
  console.log(`Backtest release record written to ${RELEASE_RECORD} (commit it with the release; the core and worker records follow it):\n${JSON.stringify(recorded, null, 2)}`);
  process.exit(0);
}

const rel = readRecord(RELEASE_RECORD);
let verdict = null;
/** The problems of the release record against this tree (empty: it approves this tree), read once. */
async function releaseVerdict() {
  if (verdict) return verdict;
  if (rel === null) return verdict = [`${RELEASE_RECORD} is missing`];
  if (rel === 'unreadable') return verdict = [`${RELEASE_RECORD} is not JSON`];
  const bad = releaseProblems(rel, sections);
  if (rel.formula_tree !== formulaNow.hash)
    bad.push(`the formula paths are not the tree ${RELEASE_RECORD} approves (formula_tree ${short(rel.formula_tree)}…, this tree ${short(formulaNow.hash)}…): a release needs its own record, made with --record-release and committed`);
  if (Array.isArray(rel.ids)) bad.push(...(await releaseScope(rel.ids.filter(i => typeof i === 'string'))));
  return verdict = bad;
}
let releaseRecord = null, formulaMode = `${ALWAYS.length} formula and Feature 04 paths unchanged`;
if (formulasChanged) {
  const files = named(formulaDiff).join(', '), bad = await releaseVerdict();
  if (rel === null) problems.push(`formula or Feature 04 paths differ from ${BASE} (no record approves these): ${files} (an indicator release the user approved is recorded with --record-release and committed: ${RELEASE_RECORD} is missing)`);
  else if (bad.length) problems.push(`the formula paths differ from ${BASE} (${files}) and ${RELEASE_RECORD} does not approve them`, ...bad);
  else { releaseRecord = rel; formulaMode = `${FEATURE04.length} Feature 04 paths unchanged, the formulas as released by ${releaseOf(rel)}` }
}

// 4. the core: as the base, or exactly as the core record approves (K2 A)
const coreDiff = changedFrom(base, [CORE]), coreChanged = coreDiff.changed.length + coreDiff.untracked.length > 0, coreNow = treeHash(CORE);
let coreRecord = null, coreMode = `${CORE} unchanged`;
if (coreChanged) {
  const named = [...coreDiff.changed, ...coreDiff.untracked.map(f => `${f} (untracked)`)].join(', ');
  const b = readRecord(CORE_BASELINE);
  if (b === null) problems.push(`${CORE} differs from ${BASE} (${named}) and no recorded approval approves it: ${CORE_BASELINE} is missing (a core change the user approved records it with --record-core and commits it)`);
  else if (b === 'unreadable') problems.push(`${CORE} differs from ${BASE} (${named}) and ${CORE_BASELINE} is not JSON`);
  else {
    const bad = coreProblems(b, sections);
    problems.push(...bad);
    if (b.core_tree !== coreNow.hash)
      problems.push(`${CORE} differs from ${BASE} (${named}) and from the tree ${CORE_BASELINE} approves (core_tree ${String(b.core_tree).slice(0, 12)}…, this tree ${coreNow.hash.slice(0, 12)}…): a core change needs its own approval, recorded with --record-core and committed`);
    else if (!bad.length) { coreRecord = b; coreMode = `${CORE} as approved by ${b.exec.section} (${CORE_BASELINE}, decision of ${b.exec.date}, against ${String(b.base_commit).slice(0, 12)})` }
  }
}

if (process.argv.includes('--record-core')) {
  const section = option('--exec'), decision = option('--decision'), date = option('--date'), note = option('--note');
  const recorded = {
    schema: 1,
    about: `The approved state of ${CORE} for scripts/screener/check_backtest_untouched.mjs: the tripwire passes a core that differs from origin/main only while its content hash is core_tree (and, while the worker is the base's, the versions are these). Recorded with --record-core and changed only by a deliberate commit (EXEC-SCREENER-FLOW-CANDLES, K2 A).`,
    base_commit: base, recorded_on: git(['rev-parse', 'HEAD']).trim(), recorded_at: new Date().toISOString().slice(0, 10),
    engine_version: engine, base_engine_version: baseEngine, registry_version: REGISTRY_VERSION,
    core_tree: coreNow.hash, core_files: coreNow.files, exec: { section, decision, date }, note,
  };
  const refused = [...problems.filter(p => !p.startsWith(`${CORE} differs`) && !p.startsWith(CORE_BASELINE)), ...coreProblems(recorded, sections)];
  if (!coreChanged) refused.push(`${CORE} is as ${BASE}'s: there is no core change to approve`);
  if (refused.length) {
    console.error(`Backtest core record NOT recorded:\n  - ${refused.join('\n  - ')}`);
    process.exit(1);
  }
  fs.writeFileSync(path.join(ROOT, CORE_BASELINE), JSON.stringify(recorded, null, 2) + '\n');
  console.log(`Backtest core record written to ${CORE_BASELINE} (commit it with the core change):\n${JSON.stringify(recorded, null, 2)}`);
  process.exit(0);
}

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
  const refused = [...problems, ...baselineProblems(recorded, sections)];
  if (refused.length) {
    console.error(`Backtest baseline NOT recorded:\n  - ${refused.join('\n  - ')}`);
    process.exit(1);
  }
  fs.writeFileSync(path.join(ROOT, BASELINE), JSON.stringify(recorded, null, 2) + '\n');
  console.log(`Backtest baseline recorded in ${BASELINE} (commit it with the worker change):\n${JSON.stringify(recorded, null, 2)}`);
  process.exit(0);
}

// 5. the worker: as the base, or exactly as the recorded baseline approves; the versions as expected
const worker = changedFrom(base, [WORKER]);
let mode, versionMode = '';
if (!worker.changed.length && !worker.untracked.length) {
  mode = `${WORKER} unchanged`;
  if (coreRecord) {
    if (engine !== coreRecord.engine_version) problems.push(`engine_version ${engine} is not the core record's ${coreRecord.engine_version} (the record was made on other sources)`);
    if (REGISTRY_VERSION !== coreRecord.registry_version) problems.push(`registry_version ${REGISTRY_VERSION} is not the core record's ${coreRecord.registry_version}`);
  } else if (!coreChanged && !versionsAsBase) {
    // a lab formula or a Flow registry entry moves engine_version with the core and the worker as the base's: the
    // release record that approves this tree holds the versions (EXEC-TRIPWIRE-LAB)
    const bad = releaseRecord ? [] : await releaseVerdict(), approving = bad.length ? null : rel;
    if (approving && approving.engine_version === engine && approving.registry_version === REGISTRY_VERSION) versionMode = `the versions as released by ${releaseOf(approving)}; `;
    else {
      const why = approving ? ` (${RELEASE_RECORD} was made on other sources: engine_version ${approving.engine_version}, registry_version ${approving.registry_version}; record the release again with --record-release)`
        : rel === null ? ` (a change the user approved is recorded and committed: a lab formula or a Flow registry entry with --record-release, a core change with --record-core, a worker change with --record)`
        : ` (${RELEASE_RECORD} does not approve this tree: ${formulasChanged ? 'the formula problems above' : bad.join('; ')})`;
      if (engine !== baseEngine) problems.push(`engine_version ${engine} differs from ${BASE}'s ${baseEngine}${why}`);
      if (REGISTRY_VERSION !== baseRegistry) problems.push(`registry_version ${REGISTRY_VERSION} (backtest-registry.json) differs from ${BASE}'s ${baseRegistry}${why}`);
    }
  }
} else {
  const named = [...worker.changed, ...worker.untracked.map(f => `${f} (untracked)`)].join(', ');
  const b = readRecord(BASELINE);
  if (b === null) problems.push(`${WORKER} differs from ${BASE} (${named}) and no recorded baseline approves it: ${BASELINE} is missing (an approved change records it with --record and commits it)`);
  else if (b === 'unreadable') problems.push(`${WORKER} differs from ${BASE} (${named}) and ${BASELINE} is not JSON`);
  else {
    const bad = baselineProblems(b, sections);
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
console.log(`Backtest tripwire OK against ${BASE} ${base.slice(0, 12)}: ${formulaMode}; ${coreMode}; ${mode}; ${versionMode}engine_version ${engine}, registry_version ${REGISTRY_VERSION}.`);
