// Latest-value warm-up for longer custom lengths (EMA 50/200, RSI 50, ADX 50): full history vs last K bars. Read-only.
import { readFileSync } from 'node:fs';
import { F, isN } from '/home/user/saniti/apps/edge-bff/terminal/src/calc/indicators.ts';
const bars = JSON.parse(readFileSync(process.argv[2], 'utf8'));
const KS = [250, 400, 500, 750, 1000, 1500];
const cut = (b: any, k: number) => ({ O: b.O.slice(-k), H: b.H.slice(-k), L: b.L.slice(-k), C: b.C.slice(-k), V: b.V.slice(-k), T: b.T.slice(-k) });
const cases: [string, any, string][] = [['ema', { length: 50 }, 'ema'], ['ema', { length: 200 }, 'ema'], ['rsi', { length: 50 }, 'rsi'], ['adx', { di_length: 50, adx_smoothing: 50 }, 'adx'], ['macd', { fast_length: 50, slow_length: 200, signal_length: 50 }, 'signal'], ['atr', { length: 100 }, 'atr']];
console.log(['key', 'params', 'output', ...KS.map(k => `K=${k}`)].join(' | '));
for (const [key, p, o] of cases) {
  const row: string[] = [];
  for (const k of KS) {
    let worst = 0, n = 0, nul = 0;
    for (const b of Object.values<any>(bars)) {
      if (b.C.length <= k) continue;
      const a = F[key](b, p)[o], x = F[key](cut(b, k), p)[o], A = a[a.length - 1], X = x[x.length - 1];
      if (!isN(A)) continue; n++;
      if (!isN(X)) { nul++; continue }
      const tail = a.slice(-250).filter(isN).map((v: number) => Math.abs(v)).sort((u: number, w: number) => u - w);
      worst = Math.max(worst, Math.abs(A - X) / Math.max(tail[tail.length >> 1], 1e-12));
    }
    row.push(`${nul ? `null:${nul}/` : ''}${worst ? worst.toExponential(1) : '0'} (n=${n})`);
  }
  console.log([key, JSON.stringify(p), o, ...row].join(' | '));
}
