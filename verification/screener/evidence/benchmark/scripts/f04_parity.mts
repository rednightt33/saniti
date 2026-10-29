/* Latest-bar values from F on full history for the Feature 04 default columns, compared with Feature 04 rows of 2026-10-27. */
import { readFileSync, writeFileSync } from 'node:fs';
import { F, isN } from '/home/user/saniti/apps/edge-bff/terminal/src/calc/indicators.ts';
const D = JSON.parse(readFileSync('data/price_full.json', 'utf8'));
const R = JSON.parse(readFileSync('data/f04_20261027.json', 'utf8'));
const map: [string, string, Record<string, unknown>, string][] = [
  ['sma_20', 'sma', { length: 20 }, 'sma'], ['sma_50', 'sma', { length: 50 }, 'sma'], ['ema_12', 'ema', { length: 12 }, 'ema'], ['ema_26', 'ema', { length: 26 }, 'ema'],
  ['ema_50', 'ema', { length: 50 }, 'ema'], ['ema_200', 'ema', { length: 200 }, 'ema'], ['rsi_14', 'rsi', { length: 14 }, 'rsi'], ['macd', 'macd', {}, 'macd'],
  ['macd_signal', 'macd', {}, 'signal'], ['macd_histogram', 'macd', {}, 'histogram'], ['atr_14', 'atr', { length: 14 }, 'atr'],
  ['bb_upper_20', 'bollinger', {}, 'upper'], ['bb_middle_20', 'bollinger', {}, 'basis'], ['bb_lower_20', 'bollinger', {}, 'lower'], ['adx_14', 'adx', {}, 'adx']];
const stats: Record<string, { n: number; exact: number; rel_gt_1e9: number; max_rel: number; max_t: string; null_mm: number }> = {};
for (const [col] of map) stats[col] = { n: 0, exact: 0, rel_gt_1e9: 0, max_rel: 0, max_t: '', null_mm: 0 };
let notLast = 0;
for (const row of R) {
  const s = D[row.ticker]; if (!s) continue;
  const k = s.d.indexOf(row.d); if (k < 0) continue; if (k !== s.d.length - 1) notLast++;
  const bars = { O: s.o.slice(0, k + 1), H: s.h.slice(0, k + 1), L: s.l.slice(0, k + 1), C: s.c.slice(0, k + 1), V: s.v.slice(0, k + 1), T: s.d.slice(0, k + 1) };
  const memo = new Map<string, any>();
  for (const [col, key, p, out] of map) {
    const id = key + JSON.stringify(p); if (!memo.has(id)) memo.set(id, F[key](bars, p));
    const x = memo.get(id)[out][k], y = row[col], st = stats[col];
    if (!isN(x) || y === null) { if (isN(x) !== (y !== null)) st.null_mm++; continue }
    st.n++; if (x === y) st.exact++;
    const m = Math.max(Math.abs(x), Math.abs(y)), rel = m ? Math.abs(x - y) / m : 0;
    if (rel > 1e-9) st.rel_gt_1e9++; if (rel > st.max_rel) { st.max_rel = rel; st.max_t = row.ticker }
  }
}
writeFileSync('results/f04_parity.json', JSON.stringify({ rows: R.length, notLast, stats }, null, 1));
console.log(JSON.stringify({ rows: R.length, notLast }));
for (const [c, s] of Object.entries(stats)) console.log(c.padEnd(16), JSON.stringify(s));
