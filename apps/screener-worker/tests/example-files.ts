/* 3e, the example mode (ERRORS M527): prints a made-up Screener example as JSON for the edge-bff tests
   (tests/example_docs.py screener_example hands it to the publisher's own builder, terminal-publisher examples.py
   screener_files, with the release file, as the capture job hands it the real one): this suite's made-up market (twelve
   random walks, no market data) with two stocks drawn to break out of their year's high on volume, cut at its last day
   and screened by the worker itself (tests/example-capture.ts) with the preset brk52, for the context of the released
   items of apps/edge-bff/catalog/releases.json and no right.
   node --experimental-strip-types --no-warnings=ExperimentalWarning --import ./apps/backtest-worker/loader/register.mjs \
     apps/screener-worker/tests/example-files.ts      (from the repository root) */
import fs from 'node:fs';
import { universe } from './fake-terminal.mjs';
import { envFor } from './helpers.ts';
import { cutPublication, screenOn, type Publication } from './example-capture.ts';
import { setLogSink } from '../src/log.ts';

declare const process: { stdout: { write(s: string): boolean } };
export const AS_OF = '2026-10-27';
const KINDS = ['indicator', 'flow_indicator', 'candle_pattern', 'screener_metric'];

setLogSink(() => {});                                       // the worker's log lines stay out of the JSON printed
const u = universe(12, 330, { last: AS_OF });
// two stocks quiet for a year, then a close above the year's high two sessions ago and a volume spike on the last day
for (const [k, t] of ['BRKA', 'BRKB'].entries()) {
  u.prices[t] = (u.prices.IHSG as unknown[][]).map(([d], i, all) => {
    const end = all.length - 1, base = 500 + 100 * k, up = Math.round(i >= end - 1 ? base * 1.06 : base * (1 + 0.02 * Math.sin(i / 7)));
    return [d, up, Math.round(up * 1.01), Math.round(up * 0.99), up, i === end ? 2e7 : 5e6];   // liquid: Rp 2.5B a day and more
  });
  u.ref.push([t, `Breakout ${k + 1}`, 'stock', 'Industrials', 'Industrials industry']);
}
const p: Publication = { finished_at: `${AS_OF}T13:03:23Z`, ...u, actions: [] };
const releases = JSON.parse(fs.readFileSync(new URL('../../edge-bff/catalog/releases.json', import.meta.url), 'utf8'));
const allow = Object.fromEntries(KINDS.map(k => [k, releases.items.filter((i: any) => i.kind === k && i.stage === 'released').map((i: any) => i.id).sort()]));
const example = await screenOn(cutPublication(p, AS_OF), envFor('http://127.0.0.1:9'), 'brk52', { allow, rights: [] });
process.stdout.write(JSON.stringify(example) + '\n');
