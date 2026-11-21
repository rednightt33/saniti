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
import { setLogSink } from '../src/log.ts';

declare const process: { argv: string[]; stdout: { write(s: string): boolean } };
export const AS_OF = '2026-10-27';
const KINDS = ['indicator', 'flow_indicator', 'candle_pattern', 'screener_metric'];
const preset = process.argv[2];
if (!/^[a-z0-9]+$/.test(preset ?? '')) throw new Error('usage: example-files.ts <preset id>');

setLogSink(() => {});                                       // the worker's log lines stay out of the JSON printed
const u = universe(12, 330, { last: AS_OF });
const days = (u.prices.IHSG as unknown[][]).map(r => r[0] as string), n = days.length;
const bar = (d: string, c: number, v: number) => [d, c, Math.round(c * 1.01), Math.round(c * 0.99), c, v];
const sma = (c: number[], i: number, len: number) => { let s = 0; for (let k = i - len + 1; k <= i; k++) s += c[k]; return s / len };
// Golden Cross: a long fall, then a rise steep enough that the 50-session SMA crosses above the 200-session one a few
// sessions before the last day (the turn is searched, so the cross lands where the preset looks: within 20 sessions)
function crossing(): number[] {
  for (let turn = n - 150; turn < n - 20; turn++) {
    const c = days.map((_, i) => Math.round(i < turn ? 1500 - i * 2 : (1500 - turn * 2) + (i - turn) * 9));
    const last = [...Array(n).keys()].filter(i => i >= 200 && sma(c, i - 1, 50) <= sma(c, i - 1, 200) && sma(c, i, 50) > sma(c, i, 200)).pop();
    if (last !== undefined && last >= n - 8 && last <= n - 3) return c;
  }
  throw new Error('no golden cross could be drawn on the made-up calendar');
}
const golden = crossing();
u.prices.GCRS = days.map((d, i) => bar(d, golden[i], 5e6));
u.ref.push(['GCRS', 'Golden cross', 'stock', 'Industrials', 'Industrials industry']);
// brk52: quiet for a year, then a close above the year's high two sessions ago and a volume spike on the last day
u.prices.BRKA = days.map((d, i) => bar(d, Math.round(i >= n - 2 ? 530 : 500 * (1 + 0.02 * Math.sin(i / 7))), i === n - 1 ? 2e7 : 5e6));
u.ref.push(['BRKA', 'Breakout', 'stock', 'Industrials', 'Industrials industry']);
const p: Publication = { finished_at: `${AS_OF}T13:03:23Z`, ...u, actions: [] };
const releases = JSON.parse(fs.readFileSync(new URL('../../edge-bff/catalog/releases.json', import.meta.url), 'utf8'));
const allow = Object.fromEntries(KINDS.map(k => [k, releases.items.filter((i: any) => i.kind === k && i.stage === 'released').map((i: any) => i.id).sort()]));
const example = await screenOn(cutPublication(p, AS_OF), envFor('http://127.0.0.1:9'), preset, { allow, rights: [] });
process.stdout.write(JSON.stringify(example) + '\n');
