// Computes every terminal indicator series (53 technical + Flow FL01-FL50 with the registry defaults) for one stock, with the terminal's own calc engine.
// Usage: TERMINAL_SRC=<.../apps/edge-bff/terminal/src> npx vite-node point_series.ts <input.json> <output.json>
// input.json: { dates, O, H, L, C, V, rows:[{d,b,i,m,bv,sv,bl,sl,bf,sf}], classification:{broker:class} }   output.json: { series:{'T:rsi.rsi': [...], 'F:FL38.value': [...]}, errors:{...} }
// Left out (point_behaviour plan, section 2): FL18, FL19, FL20, FL44, FL45 (anchored), FL31 (insider data), FL51, FL52 (views).
import fs from 'node:fs';

const SRC = process.env.TERMINAL_SRC!;
const ind: any = await import(SRC + '/calc/indicators.ts');
const flow: any = await import(SRC + '/calc/flow.ts');
const inp = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const N = inp.dates.length, at = new Map<string, number>(inp.dates.map((d: string, k: number) => [d, k]));
const B = { O: inp.O, H: inp.H, L: inp.L, C: inp.C, V: inp.V, T: inp.dates };
const out: any = { series: {}, errors: {} };
for (const id of Object.keys(ind.F)) {
  try { const r = ind.F[id](B, {}); for (const [k, v] of Object.entries(r)) if (k !== '_breaks' && Array.isArray(v)) out.series[`T:${id}.${k}`] = v; }
  catch (e) { out.errors[id] = String(e).slice(0, 200); }
}
const ctx = { rows: flow.flowRows(inp.rows, N, (d: string) => at.get(d) ?? -1), dates: inp.dates, close: inp.C, volume: inp.V, insider: [], classification: inp.classification };
const skip = new Set(['FL18', 'FL19', 'FL20', 'FL44', 'FL45']);
for (let k = 1; k <= 50; k++) {
  const id = 'FL' + String(k).padStart(2, '0'); if (skip.has(id)) continue;
  try { const r = flow.computeFlow(id, ctx, {}); for (const [kk, v] of Object.entries(r)) if (Array.isArray(v)) out.series[`F:${id}.${kk}`] = v; }
  catch (e) { out.errors[id] = String(e).slice(0, 200); }
}
fs.writeFileSync(process.argv[3], JSON.stringify(out));
console.log(`${process.argv[2]}: ${Object.keys(out.series).length} series, ${Object.keys(out.errors).length} errors ${JSON.stringify(out.errors)}`);
