// Warm-up of the latest value: each registry indicator (registry defaults) on the full published history vs the last K
// bars only. Read-only: imports the repository's calculation module and registry; writes nothing in the repository.
import { readFileSync } from 'node:fs';
import { F, isN } from '/home/user/saniti/apps/edge-bff/terminal/src/calc/indicators.ts';
const reg = JSON.parse(readFileSync('/home/user/saniti/apps/edge-bff/backtest/src/core/backtest-registry.json', 'utf8'));
const bars = JSON.parse(readFileSync(process.argv[2], 'utf8'));
const KS = [60, 120, 250, 500, 750, 1000];
const cut = (b: any, k: number) => ({ O: b.O.slice(-k), H: b.H.slice(-k), L: b.L.slice(-k), C: b.C.slice(-k), V: b.V.slice(-k), T: b.T.slice(-k) });
const rows: any[] = [];
for (const r of reg.indicators) {
  const params: any = {}; for (const p of r.params) params[p.key] = p.default;
  const per: Record<string, { worst: Record<number, number>; nulls: Record<number, number>; n: number }> = {};
  for (const o of r.outputs) per[o] = { worst: Object.fromEntries(KS.map(k => [k, 0])), nulls: Object.fromEntries(KS.map(k => [k, 0])), n: 0 };
  for (const [t, b] of Object.entries<any>(bars)) {
    const full = F[r.key](b, params);
    for (const k of KS) {
      if (b.C.length <= k) continue;
      const part = F[r.key](cut(b, k), params);
      for (const o of r.outputs) {
        const a = full[o][full[o].length - 1], x = part[o][part[o].length - 1];
        if (k === KS[0]) per[o].n++;
        if (!isN(a) && !isN(x)) continue;
        if (!isN(a) || !isN(x)) { per[o].nulls[k]++; continue }
        const rel = Math.abs(a - x) / Math.max(Math.abs(a), 1e-12);
        if (rel > per[o].worst[k]) per[o].worst[k] = rel;
      }
    }
  }
  for (const o of r.outputs) rows.push({ id: r.id, key: r.key, output: o, n: per[o].n, ...Object.fromEntries(KS.map(k => [`K${k}`, per[o].nulls[k] ? `null:${per[o].nulls[k]}` : per[o].worst[k] === 0 ? '0' : per[o].worst[k].toExponential(1)])) });
}
console.log(['id', 'key', 'output', 'tickers', ...KS.map(k => `K=${k}`)].join(' | '));
for (const x of rows) console.log([x.id, x.key, x.output, x.n, ...KS.map(k => x[`K${k}`])].join(' | '));
