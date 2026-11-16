/* Builds static/edge-session.js (the shell's copy of shared/edge-session.ts: one classic script that sets
   window.EdgeSession) with the esbuild of the Terminal page (terminal/node_modules; `npm ci` there first).
   Usage (from apps/edge-bff):  node shared/build-shell.mjs           writes static/edge-session.js
                                node shared/build-shell.mjs --check   exit 1 when the file is not this build
   The first line names the sha256 of the source; tests/test_storage_registry.py fails when it is not the source's. */
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const here = p => fileURLToPath(new URL(p, import.meta.url));
const SRC = here('./edge-session.ts'), OUT = here('../static/edge-session.js');
const { buildSync } = createRequire(here('../terminal/package.json'))('esbuild');

const source = readFileSync(SRC);
const sha = createHash('sha256').update(source).digest('hex');
const built = buildSync({ entryPoints:[SRC], bundle:true, format:'iife', globalName:'EdgeSession', target:'es2020',
  write:false, charset:'utf8', legalComments:'none' }).outputFiles[0].text;
const text = `/* generated from apps/edge-bff/shared/edge-session.ts sha256=${sha} by shared/build-shell.mjs; do not edit */\n${built}`;

if (process.argv.includes('--check')) {
  const now = existsSync(OUT) ? readFileSync(OUT, 'utf8') : '';
  if (now !== text) { console.error('static/edge-session.js is not the build of shared/edge-session.ts: run node shared/build-shell.mjs'); process.exit(1) }
  console.log('static/edge-session.js matches shared/edge-session.ts');
} else {
  writeFileSync(OUT, text);
  console.log(`wrote static/edge-session.js (${text.length} bytes, source sha256 ${sha.slice(0, 12)})`);
}
