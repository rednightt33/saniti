/* 3f proof builds (tests/test_3f_public_bundles.py): the Terminal built as in production, with one fixture lab
   indicator added to its registry (fixture-entry.json, never in the release file) and, in the lab build, its formula
   (fixture-lab.ts) as the lab module. Run from apps/edge-bff/terminal:
     EDGE_LAB_PROOF_OUT=<dir> npx vite build --config tests/lab/proof.config.mjs [--mode lab] */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';
import { terminalConfig } from '../../vite.config.ts';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const read = (name) => JSON.parse(fs.readFileSync(path.join(HERE, name), 'utf8'));

// the fixture lab indicator (the main bundle) and the fixture lab Flow indicator (the main bundle and the Web Worker's,
// which imports the Flow registry: checker L1); EDGE_LAB_PROOF_RELEASES, when set, is a release file that lists both as
// lab (the case of a real lab item), else they are unlisted, so lab too
export default defineConfig(({ mode }) => terminalConfig({
  lab: mode === 'lab',
  extra: { 'terminal/src/data/indRegistry.json': { entries: [read('fixture-entry.json')] },
           'terminal/src/data/flowRegistry.json': { entries: [read('fixture-flow-entry.json')] } },
  labModule: mode === 'lab' ? path.join(HERE, 'fixture-lab.ts') : undefined,
  outDir: process.env.EDGE_LAB_PROOF_OUT,
  releases: process.env.EDGE_LAB_PROOF_RELEASES || undefined,
}));
