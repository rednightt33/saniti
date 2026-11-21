/* EXEC-MU-ACCOUNTS 3e, the example mode (ERRORS M527): the Backtest example's request, built by the page's own code
   (apps/edge-bff/backtest/src: its default state S, applyCatalog and currentRequest; tests/example-made-up.ts
   defaultRequestOn) on the part of the worker's catalog that backtest_catalog_job.py prints (cut to the example's
   period, so the page's default period is that year). The part must be exactly the part of itself for that request
   (tests/example-part.ts catalogPart: the request names its ticker and brokers); the capture then checks that the
   worker's catalog holds it (examples.py outside), and the page, reading the stored catalog, builds this request
   (src/api/example.ts answers only it, the cards' random ids aside).

   node --experimental-transform-types --no-warnings=ExperimentalWarning \
     --import ./apps/backtest-worker/loader/register.mjs verification/edge_multiuser/example_mode/backtest_request.ts \
     <part.json>      (from the repository root; prints {"built_on": the part, "request": the request} as JSON) */
import fs from 'node:fs';
import { defaultRequestOn } from '../../../apps/edge-bff/backtest/tests/example-made-up.ts';
import { catalogPart } from '../../../apps/edge-bff/backtest/tests/example-part.ts';

const sorted = (v: unknown): unknown => Array.isArray(v) ? v.map(sorted)
  : v && typeof v === 'object' ? Object.fromEntries(Object.entries(v).sort(([a], [b]) => a < b ? -1 : 1).map(([k, w]) => [k, sorted(w)])) : v;
const part = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const request = defaultRequestOn(part);
if (request.mode !== 'single' || request.period.from !== part.first_date || request.period.to !== part.data_through)
  throw new Error(`the page's request is ${request.mode} ${request.period.from}..${request.period.to}, not single ${part.first_date}..${part.data_through}`);
if (JSON.stringify(sorted(catalogPart(part, request))) !== JSON.stringify(sorted(part)))
  throw new Error('the catalog given is not the part the request names (tests/example-part.ts): print it again with backtest_catalog_job.py');
process.stdout.write(JSON.stringify({ built_on: part, request }) + '\n');
