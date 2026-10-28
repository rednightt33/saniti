import { readFileSync } from 'node:fs';
import { F, isN } from '/home/user/saniti/apps/edge-bff/terminal/src/calc/indicators.ts';
const bars = JSON.parse(readFileSync(process.argv[2], 'utf8'));
const cut = (b: any, k: number) => ({ O: b.O.slice(-k), H: b.H.slice(-k), L: b.L.slice(-k), C: b.C.slice(-k), V: b.V.slice(-k), T: b.T.slice(-k) });
for (const key of ['stoch_rsi', 'rsi']) for (const k of [250, 500, 1000]) {
  let worst = 0, at = '', vals = '';
  for (const [t, b] of Object.entries<any>(bars)) {
    if (b.C.length <= k) continue;
    const o = key === 'stoch_rsi' ? 'k' : 'rsi';
    const a = F[key](b, {})[o], x = F[key](cut(b, k), {})[o];
    const A = a[a.length - 1], X = x[x.length - 1];
    if (isN(A) && isN(X) && Math.abs(A - X) > worst) { worst = Math.abs(A - X); at = t; vals = `${A} vs ${X}` }
  }
  console.log(key, 'K', k, 'max abs diff', worst, at, vals);
}
