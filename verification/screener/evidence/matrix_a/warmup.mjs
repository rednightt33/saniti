// Start dependence: run each I01-I27 default on the full history and on the history cut at bar S; report how many bars after
// the cut the truncated run needs until every later value is within 1e-6 / 1e-9 relative of the full run (and first valid bar).
import fs from 'node:fs';
import path from 'node:path';
const { F } = await import('/home/user/saniti/apps/edge-bff/terminal/src/calc/indicators.ts');
const dir = path.dirname(new URL(import.meta.url).pathname);
const KEYS = ['sma','ema','wma','hma','kama','macd','adx','aroon','supertrend','donchian','keltner','psar','rsi','stoch_rsi','stochastic','williams_r','roc','momentum','cci','cmo','tsi','trix','ultimate_osc','awesome_osc','ppo','bop','bollinger'];
const cut = Number(process.argv[2] || 1000), tickers = process.argv.slice(3);
const rel = (a, b) => (a === b ? 0 : Math.abs(a - b) / Math.max(Math.abs(a), Math.abs(b), 1e-300));
const res = {};
for (const t of tickers) {
  const d = JSON.parse(fs.readFileSync(path.join(dir, 'data', t + '.ts.json')));
  const B = d.bars, N = B.C.length; if (N <= cut + 400) continue;
  const Bc = Object.fromEntries(Object.entries(B).map(([k, v]) => [k, v.slice(cut)]));
  for (const k of KEYS) {
    const full = F[k](B, {}), part = F[k](Bc, {});
    for (const o of Object.keys(full)) {
      if (o.startsWith('_')) continue;
      const a = full[o].slice(cut), b = part[o];
      const firstB = b.findIndex(v => v !== null);
      // scale for near-zero oscillators: compare abs diff / max|full|
      const scale = Math.max(...a.filter(v => v !== null).map(Math.abs), 1e-300);
      let last6 = -1, last9 = -1, lastNull = -1;
      for (let i = 0; i < a.length; i++) {
        if ((a[i] === null) !== (b[i] === null)) { lastNull = i; last6 = i; last9 = i; continue }
        if (a[i] === null) continue;
        const r = Math.min(rel(a[i], b[i]), Math.abs(a[i] - b[i]) / scale);
        if (r > 1e-6) last6 = i; if (r > 1e-9) last9 = i;
      }
      const key = `${k}.${o}`; (res[key] ||= []).push(`${t}: first ${firstB}, conv1e-6 @${last6 + 1}, conv1e-9 @${last9 + 1}`);
    }
  }
}
for (const [k, v] of Object.entries(res)) console.log(k.padEnd(26), v.join(' | '));
