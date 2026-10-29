import fs from 'node:fs';
import { F, DEFAULTS } from '/home/user/saniti/apps/edge-bff/terminal/src/calc/indicators.ts';
const rows = fs.readFileSync('/tmp/claude-0/-home-user-saniti/65bd49d0-9dca-5072-b7db-b62314cf2cd3/scratchpad/audit/html_model/data/BBCA.txt', 'utf8').split('\n').filter(l => /^\d{4}-/.test(l)).map(l => l.split(','));
const B = {O:rows.map(r => +r[1]), H:rows.map(r => +r[2]), L:rows.map(r => +r[3]), C:rows.map(r => +r[4]), V:rows.map(r => +r[5]), T:rows.map(r => r[0])};
const keys = Object.keys(F); let t0 = performance.now();
for(let k = 0; k < 844; k++) for(const key of keys) F[key](B, DEFAULTS[key]);
const ms = performance.now() - t0;
console.log(`53 indicators x 844 tickers x ${B.C.length} bars (default params, one thread): ${ms.toFixed(0)} ms; per ticker ${(ms/844).toFixed(2)} ms`);
t0 = performance.now(); for(let k = 0; k < 844; k++) F.rsi(B, {length:14}); console.log('rsi only x844:', (performance.now()-t0).toFixed(0), 'ms');
