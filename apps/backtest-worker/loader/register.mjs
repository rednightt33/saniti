/* Registers resolve.mjs for this process: `node --experimental-strip-types --import ./loader/register.mjs ...`, as the
   image's command and every npm script that runs the worker's TypeScript do (README "Run"). */
import { register } from 'node:module';

register('./resolve.mjs', import.meta.url);

// The lab formulas (3f TR-2; the lab item guard lifted 2026-11-23, INDICATOR_BETA_TO_LIVE.md): every process this loader
// starts registers them before any of its own modules, as the workers' entries do (src/server.ts, src/compute.ts), so a
// test process computes what the deployed worker computes. Found by the lab dry run of 2026-11-23: without it a lab
// indicator was missing from F in the worker's tests, and the look-ahead gate (tests/lookahead.test.ts) passed it
// without computing it (its `safely` read the TypeError as a refused setting).
await import('@edge-lab');
