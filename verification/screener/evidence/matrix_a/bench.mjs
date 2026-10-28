// Per-indicator cost on one full-history ticker (BBCA, 2,125 bars), extrapolated to 845 tickers (single thread).
import fs from 'node:fs';
const { F } = await import('/home/user/saniti/apps/edge-bff/terminal/src/calc/indicators.ts');
const d = JSON.parse(fs.readFileSync(new URL('./data/BBCA.ts.json', import.meta.url)));
const B = d.bars;
const KEYS = ['sma','ema','wma','hma','kama','macd','adx','aroon','supertrend','donchian','keltner','psar','rsi','stoch_rsi','stochastic','williams_r','roc','momentum','cci','cmo','tsi','trix','ultimate_osc','awesome_osc','ppo','bop','bollinger'];
let total = 0; const rows = [];
for (const k of KEYS) {
  for (let w = 0; w < 30; w++) F[k](B, {});
  const R = 300, t0 = process.hrtime.bigint();
  for (let r = 0; r < R; r++) F[k](B, {});
  const us = Number(process.hrtime.bigint() - t0) / 1e3 / R; total += us;
  rows.push(`${k.padEnd(14)} ${us.toFixed(1).padStart(8)} us/ticker  ~${(us * 845 / 1e3).toFixed(0).padStart(5)} ms/845 tickers`);
}
console.log(rows.join('\n'));
console.log(`ALL 27 defaults: ${total.toFixed(0)} us/ticker; ~${(total * 845 / 1e6).toFixed(2)} s for 845 tickers x 2,125 bars on one core`);
