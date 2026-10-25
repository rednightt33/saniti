/* Loads the parity fixtures (gzip JSON written by tools/fetch_live.py, gen_talib.py, gen_html.mjs).
   CALC_FIXTURES=<dir> points the tests at another fixture directory (e.g. the 23-ticker run). Plain JS so the
   package needs no Node type declarations. */
import fs from 'node:fs';
import zlib from 'node:zlib';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const fixtureDir = process.env.CALC_FIXTURES || path.join(path.dirname(fileURLToPath(import.meta.url)), 'fixtures');

export function loadFixtures() {
  return fs.readdirSync(fixtureDir).filter(f => f.endsWith('.json.gz')).sort()
    .map(f => JSON.parse(zlib.gunzipSync(fs.readFileSync(path.join(fixtureDir, f))).toString()));
}

/** Writes the comparison summary when CALC_REPORT=<file> is set (used to fill PARITY.md). */
export function writeReport(rows) {
  if (process.env.CALC_REPORT) fs.writeFileSync(process.env.CALC_REPORT, JSON.stringify(rows, null, 1));
}
