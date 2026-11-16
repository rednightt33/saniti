/* The versions a result carries (contract.ts BacktestResult.meta, CONTRACT.md section 7):
   - registry_version: registry.ts REGISTRY_VERSION, the content hash build-registry.mjs writes into the registry
     artifact; checkRegistry() recomputes it from the files in the image at start (a stale artifact cannot run);
   - engine_version: a content hash computed here at start, the first 16 hex characters of the sha256 over the sorted
     lines `<path from the repository root> \t <sha256 of the file>` of every file that decides a number of a result:
     the shared core (apps/edge-bff/backtest/src/core, .ts and .json, subfolders included), the worker's own modules
     (apps/backtest-worker/src, subfolders included), the Terminal's calculation module the core imports
     (apps/edge-bff/terminal/src/calc: indicators.ts, flow.ts, fd.ts) and the flow registry calc/flow.ts reads its
     defaults from (EXEC-BACKTEST-REVAMP P0.2, ERRORS M453: a Flow formula or default could change a result while
     the version stayed the same), and the Screener core with its catalog and registries (EXEC-BACKTEST-REVAMP P1: the
     conditions in the Screener's grammar, kind 'test', are computed by it, grammar.ts). Not a hand-kept number, so it cannot stay the same while the code changes; the
     image keeps the repository layout, so the same files give the same version in the repository and in the image.
     The indicator formulas are also in registry_version (indicators.ts and indRegistry.json). */
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { REGISTRY_VERSION } from '../../edge-bff/backtest/src/core/registry.ts';

const HERE = path.dirname(fileURLToPath(import.meta.url));
export const REPO_ROOT = path.resolve(HERE, '../../..');
/** [directory or file from the repository root, the names it covers]; a directory is walked with its subfolders */
export const SOURCES: [entry: string, pattern: RegExp][] = [
  ['apps/edge-bff/backtest/src/core', /\.(ts|json)$/],
  ['apps/backtest-worker/src', /\.ts$/],
  ['apps/edge-bff/terminal/src/calc', /\.ts$/],
  ['apps/edge-bff/terminal/src/data/flowRegistry.json', /\.json$/],
  // EXEC-BACKTEST-REVAMP P1: the Screener's grammar computes the conditions of kind 'test' (grammar.ts)
  ['apps/edge-bff/screener/src/core', /\.(ts|json)$/],
];

const sha256 = (b: Buffer | string) => crypto.createHash('sha256').update(b).digest('hex');

/** Every file the version covers, as paths from the repository root, sorted. */
export function sourceFiles(root = REPO_ROOT): string[] {
  const out: string[] = [];
  const walk = (rel: string, pattern: RegExp) => {
    const at = path.join(root, rel);
    if (!fs.statSync(at).isDirectory()) { out.push(rel); return }
    for (const d of fs.readdirSync(at, { withFileTypes: true }))
      if (d.isDirectory()) walk(`${rel}/${d.name}`, pattern); else if (pattern.test(d.name)) out.push(`${rel}/${d.name}`);
  };
  for (const [entry, pattern] of SOURCES) walk(entry, pattern);
  return out.sort();
}

export function engineVersion(root = REPO_ROOT): string {
  const lines = sourceFiles(root).map(f => `${f}\t${sha256(fs.readFileSync(path.join(root, f)))}`);
  return sha256(lines.sort().join('\n')).slice(0, 16);
}

export const ENGINE_VERSION = engineVersion();
export { REGISTRY_VERSION };

/** registry_version of the artifact = the hash of the registry's sources in this image (build-registry.mjs). */
export async function checkRegistry(): Promise<{ ok: boolean; expected: string; found: string }> {
  const { registryVersion } = await import('../scripts/build-registry.mjs') as { registryVersion: () => string };
  const found = registryVersion();
  return { ok: found === REGISTRY_VERSION, expected: REGISTRY_VERSION, found };
}
