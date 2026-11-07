/* EXEC-SCREENER-FLOW-CANDLES P6 evidence (verification/screener/P6_CANDLES.md section 6): the 20 candlestick patterns of
   the Backtest core (candles.ts) on the Terminal parity fixtures (apps/edge-bff/terminal/tests/calc/fixtures, the seven
   stocks; IHSG has no volume), as the bar indexes where each fires, at three settings:
   - default: the registry defaults;
   - notrend: the prior-trend test off (for the four patterns that do not offer "none" it is added here in memory, for
     this comparison only; the registry and the Screener keep it required);
   - notrend_tick1: the trend off and the minimum range at 1 tick (closest to TA-Lib's definitions, which have neither).
   Read by f04_compare.py. Run from the repository root:
     node --experimental-strip-types --no-warnings=ExperimentalWarning --import ./apps/backtest-worker/loader/register.mjs \
       verification/screener/p6_candles/export_signals.mjs <out.json> */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const at = rel => pathToFileURL(path.join(ROOT, rel)).href;
const { loadFixtures } = await import(at('apps/edge-bff/terminal/tests/calc/fixtures.mjs'));
const K = await import(at('apps/edge-bff/backtest/src/core/candles.ts'));
for (const p of K.CANDLES.patterns) { const t = p.params.find(q => q.key === 'trend'); if (!t.options.includes('none')) t.options.push('none') }
const SETTINGS = { default: undefined, notrend: { trend: 'none' }, notrend_tick1: { trend: 'none', min_range_ticks: 1 } };
const out = {};
for (const f of loadFixtures()) {
  if (f.ticker === 'IHSG') continue;
  const bars = { T: f.T, O: f.O, H: f.H, L: f.L, C: f.C, V: f.V };
  out[f.ticker] = { n: f.T.length, sig: {} };
  for (const id of K.CANDLE_IDS) for (const [v, params] of Object.entries(SETTINGS)) {
    const s = K.candleSignal(bars, id, params);
    out[f.ticker].sig[`${id}|${v}`] = [...s.keys()].filter(i => s[i]);
  }
}
fs.writeFileSync(process.argv[2], JSON.stringify(out));
console.log(`wrote ${process.argv[2]}`);
