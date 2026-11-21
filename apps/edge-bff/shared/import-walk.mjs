/* The modules a page entry reaches, as Vite resolves its imports: a relative import as written, then with .ts, then as
   a folder's index.ts; a bare name only through `aliases` (a package such as vite or lightweight-charts is not a
   repository module). A Web Worker's entry (new Worker(new URL(...))) is not an import: list it as an entry of its own.
   Used by the Backtest's worker-only test (EXEC-BACKTEST-REVAMP P0.4, backtest/tests/worker-only.test.mjs) and by 3f's
   public-entry test (terminal/tests/lab/public-entries.test.mjs). */
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
