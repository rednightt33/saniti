/* ERRORS M405 (2026-11-08): a Node service image built from a fixed list of COPY lines holds every module its start
   command loads. calc/flow.ts started importing data/brokerAgg.ts; the screener-worker image copies terminal/src/calc and
   two JSON files only, so the deployed worker stopped at start (ERR_MODULE_NOT_FOUND) while every test passed in the full
   repository. This walks the imports from the image's own start command (CMD's entry and its --import loader), resolved
   as the workers' loader does (as written, then .ts, then /index.ts), and lists every module outside the COPY sources.
   Derived from the Dockerfile, so a new COPY line or a new import is covered without a list here.
   Usage: node scripts/check_image_imports.mjs apps/<service>/Dockerfile   (exit 1 when a module is missing) */
import { existsSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, posix, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');

/** the COPY sources (repository paths), the final WORKDIR inside the image and the start command's local modules */
export function imageOf(dockerfile) {
  const lines = readFileSync(join(ROOT, dockerfile), 'utf8').split('\n').map(l => l.trim()).filter(l => l && !l.startsWith('#'));
  const copies = [], cmd = [];
  let workdir = '/';
  for (const l of lines) {
    const [op, ...rest] = l.split(/\s+/);
    if (op === 'WORKDIR') workdir = posix.resolve(workdir, rest[0]);
    if (op === 'COPY' && !rest.some(a => a.startsWith('--from'))) {
      const args = rest.filter(a => !a.startsWith('--'));
      copies.push(...args.slice(0, -1).map(a => posix.normalize(a).replace(/\/$/, '')));
    }
    if (op === 'CMD' || op === 'ENTRYPOINT') cmd.splice(0, cmd.length, ...JSON.parse(l.slice(op.length).trim()));
  }
  const appRoot = '/app';                                     // the images copy the repository's paths under /app
  const local = a => /\.(m?[jt]s)$/.test(a) && !a.startsWith('-');
  const entries = cmd.filter(local).map(a => posix.relative(appRoot, posix.resolve(workdir, a)));
  return { copies, entries, workdir };
}

const SPEC = [/(?:^|\n)\s*import\s+(?!type\b)[^'"`;]*?from\s*['"]([^'"]+)['"]/g, /(?:^|\n)\s*export\s+(?!type\b)[^'"`;]*?from\s*['"]([^'"]+)['"]/g,
  /(?:^|\n)\s*import\s*['"]([^'"]+)['"]/g, /\bimport\(\s*['"]([^'"]+)['"]\s*\)/g];
/** the relative modules a file loads at run time (type-only imports are erased by the type stripping and do not load) */
export function importsOf(text) {
  const code = text.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
  const out = new Set();
  for (const re of SPEC) for (const m of code.matchAll(re)) if (/^\.\.?\//.test(m[1])) out.add(m[1]);
  return [...out];
}
/** a relative specifier as the workers' loader resolves it (apps/backtest-worker/loader/resolve.mjs) */
function resolveSpec(from, spec) {
  const base = join(dirname(join(ROOT, from)), spec);
  for (const c of [base, `${base}.ts`, join(base, 'index.ts')]) if (existsSync(c) && statSync(c).isFile()) return relative(ROOT, c).split('\\').join('/');
  return null;
}

/** every module the start command loads, and those the image does not hold (or that do not exist at all) */
export function checkImage(dockerfile) {
  const { copies, entries } = imageOf(dockerfile);
  const inImage = p => copies.some(c => p === c || p.startsWith(c + '/'));
  const seen = new Set(), missing = [], queue = [...entries];
  while (queue.length) {
    const file = queue.shift();
    if (seen.has(file)) continue;
    seen.add(file);
    if (!inImage(file)) missing.push({ file, why: 'not copied into the image' });
    if (!/\.(m?[jt]s)$/.test(file)) continue;              // JSON and other data: nothing imported
    for (const spec of importsOf(readFileSync(join(ROOT, file), 'utf8'))) {
      const to = resolveSpec(file, spec);
      if (!to) { missing.push({ file:`${file} -> ${spec}`, why: 'does not resolve' }); continue }
      queue.push(to);
    }
  }
  return { entries, modules: seen.size, missing };
}

if (process.argv[1] && fileURLToPath(import.meta.url) === resolve(process.argv[1])) {
  const df = process.argv[2];
  if (!df) { console.error('usage: node scripts/check_image_imports.mjs apps/<service>/Dockerfile'); process.exit(2) }
  const r = checkImage(df);
  for (const m of r.missing) console.log(`MISSING ${m.file}: ${m.why}`);
  console.log(`${df}: ${r.modules} modules from ${r.entries.join(', ')}; ${r.missing.length ? `${r.missing.length} missing` : 'all in the image'}`);
  process.exit(r.missing.length ? 1 : 0);
}
