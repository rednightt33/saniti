/* 3e, the example mode (ERRORS M527): prints the made-up Backtest example (tests/example-made-up.ts) as JSON, for the
   edge-bff tests (tests/example_docs.py backtest_example hands it to the publisher's own builder, terminal-publisher
   examples.py backtest_files, as the capture job hands it the worker's):
   node --experimental-transform-types --no-warnings=ExperimentalWarning \
     --import ./apps/backtest-worker/loader/register.mjs apps/edge-bff/backtest/tests/example-files.ts <as_of> <first>
   (from the repository root) */
import { madeUpExample } from './example-made-up.ts';

// node's own globals (the page's tsconfig has the browser's types only)
declare const process: { argv: string[]; stdout: { write(s: string): boolean } };

const [asOf, first] = process.argv.slice(2);
if (!/^\d{4}-\d{2}-\d{2}$/.test(asOf ?? '') || !/^\d{4}-\d{2}-\d{2}$/.test(first ?? '') || first >= asOf)
  throw new Error('usage: example-files.ts <as_of> <first> (ISO dates, first before as_of)');
process.stdout.write(JSON.stringify(await madeUpExample(asOf, first)) + '\n');
