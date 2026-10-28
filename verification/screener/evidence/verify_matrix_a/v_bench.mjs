// Verifier: full-market cost of long custom lengths (n = 1000) per kernel, one core.
import fs from 'node:fs';
const { F } = await import('/home/user/saniti/apps/edge-bff/terminal/src/calc/indicators.ts');
const dir = '/tmp/claude-0/-home-user-saniti/65bd49d0-9dca-5072-b7db-b62314cf2cd3/scratchpad/audit/verify_matrix_a/data_all/';
const bars = {};
for (const f of fs.readdirSync(dir).filter(f => f.startsWith('price_'))) for (const r of JSON.parse(fs.readFileSync(dir + f)).rows) (bars[r[0]] ||= []).push(r);
const Bs = Object.values(bars).map(P => ({ T: P.map(r => r[1]), O: P.map(r => r[2]), H: P.map(r => r[3]), L: P.map(r => r[4]), C: P.map(r => r[5]), V: P.map(r => r[6]) }));
const runs = [['cci', { length: 1000 }], ['hma', { length: 1000 }], ['aroon', { length: 1000 }], ['donchian', { length: 1000 }], ['stochastic', { k_length: 1000 }],
  ['stoch_rsi', { stoch_length: 1000 }], ['williams_r', { length: 1000 }], ['wma', { length: 1000 }], ['sma', { length: 1000 }], ['kama', { length: 1000 }], ['cci', {}]];
for (const [k, p] of runs) { const t0 = performance.now(); for (const B of Bs) F[k](B, p); const ms = performance.now() - t0; console.log(`${k} ${JSON.stringify(p)}: ${(ms / 1000).toFixed(2)} s market, ${(ms / Bs.length).toFixed(2)} ms/ticker`) }
