/* The versions every answer carries (report API CONTRACT 8.3; TARGET ARCHITECTURE 6.8 "Versions") and the start-up
   checks (6.8 "Consumers", TEST PLAN 10b.10 "Start-up check"):
   - screener_engine: a content hash computed here at start, the first 16 hex of the sha256 over the sorted lines
     `<path from the repository root> \t <sha256 of the file>` of every file that decides a number of an answer: the
     screener core (apps/edge-bff/screener/src/core, .ts and .json: contract, evaluation, the generated registry), the
     worker's own modules, the backtest core and the Terminal's calculation module the screener core imports, the
     backtest worker's terminal.ts (it decodes the files), plus the line `node \t <major>` (report 6.8: "and the Node
     major version"). Not a hand-kept number, so it cannot stay the same while the code changes; the image keeps the
     repository layout, so the same files give the same version in the repository and in the image;
   - registry: the backtest registry_version, passed through; screener_registry: screener-registry.json's own hash.
   Start-up (checkStartup): the backtest registry artifact must match its sources in the image (the backtest worker's
   own check, through build-registry.mjs), and every source screener-registry.json names, except the build-only oracle
   script, must be in the image with the sha256 the file records; otherwise the worker refuses to start. */
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { REGISTRY_VERSION } from '../../edge-bff/backtest/src/core/registry.ts';
import { SCREENER_REGISTRY_VERSION, SOURCES, registryProblems } from '../../edge-bff/screener/src/core/registry.ts';

const HERE = path.dirname(fileURLToPath(import.meta.url));
export const REPO_ROOT = path.resolve(HERE, '../../..');
/** [directory or file from the repository root, the names it covers] */
const ENGINE_SOURCES: [string, RegExp][] = [
  ['apps/edge-bff/screener/src/core', /\.(ts|json)$/],
  ['apps/screener-worker/src', /\.ts$/],
  ['apps/edge-bff/backtest/src/core', /\.(ts|json)$/],
  ['apps/edge-bff/terminal/src/calc', /\.ts$/],
  ['apps/backtest-worker/src/terminal.ts', /\.ts$/],
];
/** SOURCES roles the image does not carry: the oracle mapping is read at build time only (registry.ts SOURCES). */
const BUILD_ONLY = new Set(['oracle']);

const sha256 = (b: Buffer | string) => crypto.createHash('sha256').update(b).digest('hex');

export function engineVersion(root = REPO_ROOT, nodeMajor = process.versions.node.split('.')[0]): string {
  const lines: string[] = [];
  for (const [entry, pattern] of ENGINE_SOURCES) {
    const at = path.join(root, entry);
    const files = fs.statSync(at).isDirectory() ? fs.readdirSync(at).filter(n => pattern.test(n)).sort().map(n => `${entry}/${n}`) : [entry];
    for (const f of files) lines.push(`${f}\t${sha256(fs.readFileSync(path.join(root, f)))}`);
  }
  lines.sort();
  lines.push(`node\t${nodeMajor}`);
  return sha256(lines.join('\n')).slice(0, 16);
}

export const ENGINE_VERSION = engineVersion();
export { REGISTRY_VERSION, SCREENER_REGISTRY_VERSION };

/** The start-up checks; problems = what disagrees (empty when the worker may start). */
export async function checkStartup(root = REPO_ROOT): Promise<{ ok: boolean; problems: string[] }> {
  const problems = [...registryProblems()];
  const { registryVersion } = await import('../../backtest-worker/scripts/build-registry.mjs') as { registryVersion: () => string };
  const found = registryVersion();
  if (found !== REGISTRY_VERSION) problems.push(`backtest-registry.json has registry_version ${REGISTRY_VERSION}, its sources hash to ${found}`);
  for (const s of SOURCES) {
    if (BUILD_ONLY.has(s.role)) continue;
    const file = path.join(root, s.file);
    if (!fs.existsSync(file)) { problems.push(`${s.file} (${s.role}) is not in the image`); continue }
    const got = sha256(fs.readFileSync(file));
    if (got !== s.sha256) problems.push(`${s.file} (${s.role}) has sha256 ${got.slice(0, 16)}..., screener-registry.json was built from ${s.sha256.slice(0, 16)}...: run npm run registry in apps/edge-bff/screener`);
  }
  return { ok: problems.length === 0, problems };
}
