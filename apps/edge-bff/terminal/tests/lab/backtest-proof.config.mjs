/* 3f proof builds of the Backtest page (tests/test_3f_public_bundles.py), as proof.config.mjs for the Terminal: the
   fixture lab indicator in both registries the page reads, and its formula as the lab module of the lab build. Run from
   apps/edge-bff/backtest:
     EDGE_LAB_PROOF_OUT=<dir> npx vite build --config ../terminal/tests/lab/backtest-proof.config.mjs [--mode lab] */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';
import { backtestConfig } from '../../../backtest/vite.config.ts';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const read = (name) => JSON.parse(fs.readFileSync(path.join(HERE, name), 'utf8'));

// the fixture lab indicator in the three files the page reads that name indicators: the two registries and the
// comparison lag (checker L3); EDGE_LAB_PROOF_RELEASES as in proof.config.mjs
export default defineConfig(({ mode }) => backtestConfig(mode === 'lab' ? 'lab' : 'production', {
  extra: { 'terminal/src/data/indRegistry.json': { entries: [read('fixture-entry.json')] },
           'backtest/src/core/backtest-registry.json': { entries: [read('fixture-backtest-entry.json')] },
           'backtest/src/core/compare-lag.json': { price_compare_lag: { I_LAB_PROOF: { sma: { field: 'close', gt: 1, lt: 0 } } } } },
  labModule: mode === 'lab' ? path.join(HERE, 'fixture-lab.ts') : undefined,
  outDir: process.env.EDGE_LAB_PROOF_OUT,
  releases: process.env.EDGE_LAB_PROOF_RELEASES || undefined,
}));
