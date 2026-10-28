// Verifier: latest-bar equality on a tail of K bars for long custom lengths (EMA 200, RSI 50, ADX 50, MACD 50/200/20).
import fs from 'node:fs';
const { F } = await import('/home/user/saniti/apps/edge-bff/terminal/src/calc/indicators.ts');
const dir = '/tmp/claude-0/-home-user-saniti/65bd49d0-9dca-5072-b7db-b62314cf2cd3/scratchpad/audit/verify_matrix_a/data_all/';
const bars = {};
for (const f of fs.readdirSync(dir).filter(f => f.startsWith('price_'))) for (const r of JSON.parse(fs.readFileSync(dir + f)).rows) (bars[r[0]] ||= []).push(r);
const toB = (P, s = 0) => ({ T: P.slice(s).map(r => r[1]), O: P.slice(s).map(r => r[2]), H: P.slice(s).map(r => r[3]), L: P.slice(s).map(r => r[4]), C: P.slice(s).map(r => r[5]), V: P.slice(s).map(r => r[6]) });
const runs = [['ema', { length: 200 }, 'ema'], ['rsi', { length: 50 }, 'rsi'], ['adx', { di_length: 50, adx_smoothing: 50 }, 'adx'], ['macd', { fast_length: 50, slow_length: 200, signal_length: 20 }, 'signal']];
for (const [k, p, o] of runs) for (const K of [500, 1000]) {
  let n = 0, bad = 0, worst = 0, wt = '';
  for (const [t, P] of Object.entries(bars)) { if (t === 'IHSG' || P.length < K + 300) continue;
    const a = F[k](toB(P), p)[o].at(-1), b = F[k](toB(P, P.length - K), p)[o].at(-1); n++;
    if (a === null || b === null) { if (a !== b) bad++; continue }
    const r = Math.abs(a - b) / Math.max(Math.abs(a), 1e-9); if (r > 1e-6) bad++; if (r > worst) { worst = r; wt = `${t} full=${a.toPrecision(8)} tail=${b.toPrecision(8)}` } }
  console.log(`${k} ${JSON.stringify(p)} K=${K}: ${bad}/${n} tickers differ > 1e-6 rel at the latest bar; worst rel ${worst.toExponential(1)} ${wt}`);
}
