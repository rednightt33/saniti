/* 3e, the example mode (ERRORS M527): prints a made-up Screener example as JSON for the edge-bff tests
   (tests/example_docs.py screener_example hands it to the publisher's own builder, terminal-publisher examples.py
   screener_files, with the release file, as the capture job hands it the real one): this suite's made-up market (twelve
   random walks, no market data) with two stocks drawn for the presets the example may show (one whose 50-session SMA
   crossed above its 200-session SMA a few sessions ago, Golden Cross; one that closed above its year's high two sessions
   ago on a volume spike, brk52), cut at its last day and screened by the worker itself (tests/example-capture.ts) with
   the preset named, for the context of the released items of apps/edge-bff/catalog/releases.json and no right.
   node --experimental-strip-types --no-warnings=ExperimentalWarning --import ./apps/backtest-worker/loader/register.mjs \
     apps/screener-worker/tests/example-files.ts <preset>      (from the repository root; examples.py SCREENER_PRESET) */
import fs from 'node:fs';
import { universe } from './fake-terminal.mjs';
import { envFor } from './helpers.ts';
import { cutPublication, screenOn, type Publication } from './example-capture.ts';
import { drawExampleStocks } from './example-market.ts';
import { setLogSink } from '../src/log.ts';

declare const process: { argv: string[]; stdout: { write(s: string): boolean } };
export const AS_OF = '2026-10-27';
const KINDS = ['indicator', 'flow_indicator', 'candle_pattern', 'screener_metric'];
const preset = process.argv[2];
if (!/^[a-z0-9]+$/.test(preset ?? '')) throw new Error('usage: example-files.ts <preset id>');

setLogSink(() => {});                                       // the worker's log lines stay out of the JSON printed
const u = universe(12, 330, { last: AS_OF });
drawExampleStocks(u);                                        // GCRS and BRKA on the last day (tests/example-market.ts)
const p: Publication = { finished_at: `${AS_OF}T13:03:23Z`, ...u, actions: [] };
const releases = JSON.parse(fs.readFileSync(new URL('../../edge-bff/catalog/releases.json', import.meta.url), 'utf8'));
const allow = Object.fromEntries(KINDS.map(k => [k, releases.items.filter((i: any) => i.kind === k && i.stage === 'released').map((i: any) => i.id).sort()]));
const example = await screenOn(cutPublication(p, AS_OF), envFor('http://127.0.0.1:9'), preset, { allow, rights: [] });
process.stdout.write(JSON.stringify(example) + '\n');
