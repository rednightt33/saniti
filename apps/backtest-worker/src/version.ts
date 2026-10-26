/* The versions a result carries (contract.ts BacktestResult.meta, CONTRACT.md section 7):
   - registry_version: registry.ts REGISTRY_VERSION, the content hash build-registry.mjs writes into the registry
     artifact; checkRegistry() recomputes it from the files in the image at start (a stale artifact cannot run);
   - engine_version: a content hash computed here at start, the first 16 hex characters of the sha256 over the sorted
     lines `<path from the repository root> \t <sha256 of the file>` of every file that decides a number of a result:
     the shared core (apps/edge-bff/backtest/src/core/*.ts and *.json) and the worker's own modules
     (apps/backtest-worker/src/*.ts). Not a hand-kept number, so it cannot stay the same while the code changes; the
     image keeps the repository layout, so the same files give the same version in the repository and in the image.
     The indicator formulas are in registry_version (indicators.ts and indRegistry.json). */
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { REGISTRY_VERSION } from '../../edge-bff/backtest/src/core/registry.ts';

const HERE = path.dirname(fileURLToPath(import.meta.url));
export const REPO_ROOT = path.resolve(HERE, '../../..');
const SOURCES: [dir: string, pattern: RegExp][] = [
  ['apps/edge-bff/backtest/src/core', /\.(ts|json)$/],
  ['apps/backtest-worker/src', /\.ts$/],
];

const sha256 = (b: Buffer | string) => crypto.createHash('sha256').update(b).digest('hex');

export function engineVersion(root = REPO_ROOT): string {
  const lines: string[] = [];
  for (const [dir, pattern] of SOURCES)
    for (const name of fs.readdirSync(path.join(root, dir)).filter(n => pattern.test(n)).sort())
      lines.push(`${dir}/${name}\t${sha256(fs.readFileSync(path.join(root, dir, name)))}`);
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
