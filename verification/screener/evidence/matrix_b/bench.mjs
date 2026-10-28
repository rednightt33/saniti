// Per-indicator cost of the TS functions on BBCA's full history (defaults), after JIT warm-up.
import fs from 'node:fs'; import path from 'node:path';
const { F } = await import('/home/user/saniti/apps/edge-bff/terminal/src/calc/indicators.ts');
const D = path.dirname(new URL(import.meta.url).pathname);
const d = JSON.parse(fs.readFileSync(path.join(D, 'data', 'BBCA.json')));
const B = { O: d.O, H: d.H, L: d.L, C: d.C, V: d.V, T: d.T };
const KEYS = ['bollinger_pctb','bollinger_width','atr','natr','stddev','hist_vol','adr','volume_sma','volume_ema','rvol','pvo','volume_roc','obv','pvt','vwma','vwap','adl','cmf','chaikin_osc','mfi','force_index','eom','nvi','pvi','kvo','market_fi'];
const R = 300, out = {}; let total = 0;
for (const k of KEYS) { for (let i = 0; i < 30; i++) F[k](B, {}); const t0 = performance.now(); for (let i = 0; i < R; i++) F[k](B, {}); const us = (performance.now() - t0) / R * 1000; out[k] = +us.toFixed(1); total += us }
const bars = B.C.length, mkt = 1330722;
console.log(JSON.stringify({ bars, us_per_call: out, total_us_26: +total.toFixed(0), est_full_market_seconds_26_indicators_single_thread: +(total / bars * mkt / 1e6).toFixed(2) }));
