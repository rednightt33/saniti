/* EXEC-BACKTEST-REVAMP P0.4 (ERRORS M456): the page computes conditions in the browser with the shared core, and its
   assets are served without a session (app/main.py /backtest-app/). Admin-only series (the point-in-time Flow
   indicators) therefore live in modules only the worker imports (apps/backtest-worker/src/pit). This walks every module
   the page's entry reaches, as Vite resolves relative imports (as written, then .ts, then /index.ts), and refuses any
   under apps/backtest-worker. The built bundle is checked for the same in tests/bundle.test.mjs. */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../..');
const ENTRY = path.join(ROOT, 'apps/edge-bff/backtest/src/main.ts');
const IMPORT = /(?:import|export)\s[^'"]*?from\s*['"]([^'"]+)['"]|import\(\s*['"]([^'"]+)['"]\s*\)|import\s+['"]([^'"]+)['"]/g;

function resolve(from, spec) {
  if (!spec.startsWith('.')) return null;                       // packages (vite, the fonts) are not repository modules
  const base = path.resolve(path.dirname(from), spec);
  for (const c of [base, `${base}.ts`, path.join(base, 'index.ts')]) if (fs.existsSync(c) && fs.statSync(c).isFile()) return c;
  throw new Error(`${path.relative(ROOT, from)}: cannot resolve ${spec}`);
}
function reachable(entry) {
  const seen = new Set(), todo = [entry];
  while (todo.length) {
    const f = todo.pop();
    if (seen.has(f)) continue;
    seen.add(f);
    if (!/\.(ts|mjs|js)$/.test(f)) continue;
    for (const m of fs.readFileSync(f, 'utf8').matchAll(IMPORT)) { const r = resolve(f, m[1] ?? m[2] ?? m[3]); if (r) todo.push(r) }
  }
  return [...seen].map(f => path.relative(ROOT, f)).sort();
}

describe('worker-only modules stay out of the page (EXEC-BACKTEST-REVAMP P0.4)', () => {
  it('the page entry reaches the shared core but no module of the backtest worker', () => {
    const mods = reachable(ENTRY);
    expect(mods).toContain('apps/edge-bff/backtest/src/core/conditions.ts');
    expect(mods.filter(m => m.startsWith('apps/backtest-worker/'))).toEqual([]);
  });
});
