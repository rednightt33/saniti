// CPU cost: the 53 registry indicators (defaults) and a few typical conditions on full history, plus decoding a price
// pack shaped as the publisher writes it (gzip JSON) with the shared core's priceSeries. Read-only.
import { readFileSync } from 'node:fs';
import { gzipSync } from 'node:zlib';
import { F } from '/home/user/saniti/apps/edge-bff/terminal/src/calc/indicators.ts';
import { Calc, conditionSeries } from '/home/user/saniti/apps/edge-bff/backtest/src/core/conditions.ts';
import { decodeColumnar, priceSeries } from '/home/user/saniti/apps/edge-bff/backtest/src/core/datafile.ts';
const reg = JSON.parse(readFileSync('/home/user/saniti/apps/edge-bff/backtest/src/core/backtest-registry.json', 'utf8'));
const bars = JSON.parse(readFileSync(process.argv[2], 'utf8'));
const tickers = Object.keys(bars), nBars = tickers.reduce((n, t) => n + bars[t].C.length, 0);
// warm the JIT
for (const r of reg.indicators) F[r.key](bars[tickers[0]], {});
let t0 = performance.now();
for (const t of tickers) for (const r of reg.indicators) F[r.key](bars[t], {});
const all53 = performance.now() - t0;
console.log(`53 indicators x ${tickers.length} tickers (${nBars} bars): ${all53.toFixed(0)} ms; per ticker ${(all53 / tickers.length).toFixed(1)} ms; x845 ~ ${(all53 / tickers.length * 845 / 1000).toFixed(1)} s`);
const conds = [
  { id: 'a', kind: 'indicator', indicator: 'I13', params: {}, lhs: { type: 'output', output: 'rsi' }, op: 'lt', rhs: { type: 'value', value: 30 } },
  { id: 'b', kind: 'indicator', indicator: 'I01', params: { length: 50 }, lhs: { type: 'price' }, op: 'gt', rhs: { type: 'output', output: 'sma' } },
  { id: 'c', kind: 'indicator', indicator: 'I06', params: {}, lhs: { type: 'output', output: 'macd' }, op: 'crosses_above', rhs: { type: 'output', output: 'signal' } },
  { id: 'd', kind: 'indicator', indicator: 'I07', params: {}, lhs: { type: 'output', output: 'adx' }, op: 'gt', rhs: { type: 'value', value: 25 } },
  { id: 'e', kind: 'price_action', type: 'volspike', params: { length: 20 }, op: 'gt', value: 2 },
];
t0 = performance.now();
for (const t of tickers) { const c = new Calc(bars[t]); for (const q of conds) conditionSeries(c, q as any, 'c') }
const five = performance.now() - t0;
console.log(`5 conditions x ${tickers.length} tickers: ${five.toFixed(0)} ms; per ticker ${(five / tickers.length).toFixed(2)} ms; x845 ~ ${(five / tickers.length * 845).toFixed(0)} ms`);
// decode cost of a price pack
const docs = tickers.map(t => { const b = bars[t]; return gzipSync(Buffer.from(JSON.stringify({ schema_version: 1, dataset: 'price-pack', ticker: t, year: null, columns: ['d','o','h','l','c','v'], d: b.T, o: b.O, h: b.H, l: b.L, c: b.C, v: b.V })), { level: 9 }) });
t0 = performance.now();
for (let k = 0; k < tickers.length; k++) priceSeries(tickers[k], [await decodeColumnar(new Uint8Array(docs[k]), 'x')]);
const dec = performance.now() - t0;
console.log(`decode ${tickers.length} price packs: ${dec.toFixed(0)} ms; per ticker ${(dec / tickers.length).toFixed(2)} ms; gz bytes avg ${(docs.reduce((n, d) => n + d.byteLength, 0) / docs.length).toFixed(0)}`);
console.log('heap MB', (process.memoryUsage().heapUsed / 1e6).toFixed(0));
