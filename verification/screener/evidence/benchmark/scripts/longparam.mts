/* Warm-up sensitivity for long custom parameters: latest value on the last K bars vs full history. */
import { readFileSync, writeFileSync } from 'node:fs';
import { F, isN } from '/home/user/saniti/apps/edge-bff/terminal/src/calc/indicators.ts';
const D = JSON.parse(readFileSync('data/price_full.json', 'utf8'));
const cases: [string, Record<string, unknown>, string][] = [['ema', { length: 200 }, 'ema'], ['ema', { length: 50 }, 'ema'], ['rsi', { length: 50 }, 'rsi'],
  ['macd', { fast_length: 50, slow_length: 100, signal_length: 20 }, 'signal'], ['adx', {}, 'adx'], ['kvo', {}, 'kvo'], ['kama', {}, 'kama']];
const Ks = [250, 500, 750, 1000, 1500];
const out: Record<string, Record<string, unknown>> = {};
for (const [key, p, o] of cases) {
  const name = key + JSON.stringify(p) + '.' + o; out[name] = {};
  for (const K of Ks) {
    let n = 0, diff = 0, mx = 0, longer = 0;
    for (const [t, s] of Object.entries<any>(D)) {
      const N = s.d.length; if (N <= K) continue; longer++;
      const b = (k: number) => ({ O: s.o.slice(k), H: s.h.slice(k), L: s.l.slice(k), C: s.c.slice(k), V: s.v.slice(k), T: s.d.slice(k) });
      const x = F[key](b(0), p)[o][N - 1], y = F[key](b(N - K), p)[o][K - 1];
      if (!isN(x) || !isN(y)) continue; n++;
      const m = Math.max(Math.abs(x), Math.abs(y)), d = Math.abs(x - y), rel = m ? d / m : 0;
      if (rel > 1e-9 && d > 1e-9) diff++; if (rel > mx) mx = rel;
    }
    out[name]['K' + K] = { tickers_longer_than_K: longer, compared: n, differ_rel_and_abs_gt_1e9: diff, max_rel: +mx.toPrecision(3) };
  }
  console.log(name, JSON.stringify(out[name]));
}
writeFileSync('results/longparam.json', JSON.stringify(out, null, 1));
