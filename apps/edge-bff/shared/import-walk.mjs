/* The modules a page entry reaches, as Vite resolves its imports: a relative import as written, then with .ts, then as
   a folder's index.ts; a bare name only through `aliases` (a package such as vite or lightweight-charts is not a
   repository module). A Web Worker's entry (new Worker(new URL(...))) is not an import: pageEntries finds each one in
   the modules a page reaches. Used by the Backtest's worker-only test (EXEC-BACKTEST-REVAMP P0.4,
   backtest/tests/worker-only.test.mjs) and by 3f's tests (terminal/tests/lab/public-entries.test.mjs, coverage.test.mjs,
   and the proof builds of tests/test_3f_public_bundles.py, which plant into every entry). */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
export const IMPORT = /(?:import|export)\s[^'"]*?from\s*['"]([^'"]+)['"]|import\(\s*['"]([^'"]+)['"]\s*\)|import\s+['"]([^'"]+)['"]/g;

export function resolveImport(from, spec, aliases = {}) {
  if (Object.hasOwn(aliases, spec)) return aliases[spec];
  if (!spec.startsWith('.')) return null;                       // packages (vite, the fonts) are not repository modules
  const base = path.resolve(path.dirname(from), spec);
  for (const c of [base, `${base}.ts`, path.join(base, 'index.ts')]) if (fs.existsSync(c) && fs.statSync(c).isFile()) return c;
  throw new Error(`${path.relative(ROOT, from)}: cannot resolve ${spec}`);
}

/** Every module the entry reaches (itself included), as paths from the repository root, sorted. */
export function reachable(entry, { aliases = {} } = {}) {
  const seen = new Set(), todo = [entry];
  while (todo.length) {
    const f = todo.pop();
    if (seen.has(f)) continue;
    seen.add(f);
    if (!/\.(ts|mjs|js)$/.test(f)) continue;
    for (const m of fs.readFileSync(f, 'utf8').matchAll(IMPORT)) { const r = resolveImport(f, m[1] ?? m[2] ?? m[3], aliases); if (r) todo.push(r) }
  }
  return [...seen].map(f => path.relative(ROOT, f)).sort();
}

export const EDGE = path.join(ROOT, 'apps', 'edge-bff');
const MODULE_SCRIPT = /<script\b[^>]*\btype="module"[^>]*\bsrc="([^"]+)"/g;
const WORKER = /\bnew\s+(?:Shared)?Worker\s*\(/g;
const WORKER_URL = /\bnew\s+(?:Shared)?Worker\s*\(\s*new\s+URL\s*\(\s*(['"])([^'"\n]+)\1\s*,\s*import\.meta\.url\s*\)/y;

/** The pages under apps/edge-bff (or `edge`): each folder holding a vite.config.ts and an index.html, sorted. */
export function pages(edge = EDGE) {
  return fs.readdirSync(edge, { withFileTypes: true })
    .filter(d => d.isDirectory() && ['vite.config.ts', 'index.html'].every(f => fs.existsSync(path.join(edge, d.name, f))))
    .map(d => d.name).sort();
}

/** Every entry of a page, as paths under `edge` (3f round 2 of its checker, BUN2-3: a hand-kept list missed a new
    worker): the module scripts of its index.html, then each Web Worker a module they reach starts with a literal
    `new Worker(new URL('<file>', import.meta.url))`, walked again for a worker that starts one. A Worker started any
    other way throws: the walk cannot follow it, so no page may start one so. */
export function pageEntries(page, { edge = EDGE, aliases = {} } = {}) {
  const dir = path.join(edge, page);
  const out = [...fs.readFileSync(path.join(dir, 'index.html'), 'utf8').matchAll(MODULE_SCRIPT)].map(m => path.join(dir, m[1].replace(/^\//, '')));
  if (!out.length) throw new Error(`${page}/index.html has no <script type="module" src>`);
  for (let i = 0; i < out.length; i++) {
    for (const mod of reachable(out[i], { aliases })) {
      const file = path.join(ROOT, mod);
      if (!/\.(ts|mjs|js)$/.test(file)) continue;
      const text = fs.readFileSync(file, 'utf8');
      for (const m of text.matchAll(WORKER)) {
        WORKER_URL.lastIndex = m.index;
        const url = WORKER_URL.exec(text);
        if (!url) throw new Error(`${mod}: a Web Worker started without a literal new URL('<file>', import.meta.url); 3f's walk cannot follow it`);
        const worker = path.resolve(path.dirname(file), url[2]);
        if (!fs.existsSync(worker)) throw new Error(`${mod}: the Web Worker ${url[2]} is not a file`);
        if (!out.includes(worker)) out.push(worker);
      }
    }
  }
  return out.map(f => path.relative(edge, f));
}
