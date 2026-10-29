// Cost growth with length for the window-scan kernels (O(N*n)) vs running-sum kernels (O(N)), BBCA 2,125 bars.
import fs from 'node:fs';
const { F } = await import('/home/user/saniti/apps/edge-bff/terminal/src/calc/indicators.ts');
const B = JSON.parse(fs.readFileSync(new URL('./data/BBCA.ts.json', import.meta.url))).bars;
const cases = [['sma',{length:1000}],['wma',{length:1000}],['hma',{length:1000}],['aroon',{length:1000}],['donchian',{length:1000}],['stochastic',{k_length:1000}],['stoch_rsi',{stoch_length:1000}],['williams_r',{length:1000}],['cci',{length:1000}],['kama',{length:1000}],['ultimate_osc',{slow_length:1000}],['bollinger',{length:1000}]];
for (const [k, p] of cases) {
  for (let w = 0; w < 3; w++) F[k](B, p);
  const R = 20, t0 = process.hrtime.bigint(); for (let r = 0; r < R; r++) F[k](B, p);
  const ms = Number(process.hrtime.bigint() - t0) / 1e6 / R;
  console.log(`${k.padEnd(13)} ${JSON.stringify(p).padEnd(22)} ${ms.toFixed(2).padStart(7)} ms/ticker  ~${(ms * 845 / 1000).toFixed(1)} s/845 tickers`);
}
