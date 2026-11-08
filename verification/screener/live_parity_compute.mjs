/* EDGE Screener unit B live parity (2026-11-08): the Terminal's own computation from the Terminal's own files of each
   stock (live_parity_dev.py writes them: price pack + broker files from /api/terminal bundle), flow.ts flowRows on the
   stock's price candles, computeFlow with the registry defaults, read on the Screener cell's broker date; compared with
   the Screener's cell (P4 broker day files). Usage: node --experimental-strip-types live_parity_compute.mjs DIR */
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
const { computeFlow, flowRows } = await import('../../apps/edge-bff/terminal/src/calc/flow.ts');
const dir = process.argv[2], ids = { fl24: 'FL24', fl26: 'FL26', fl11: 'FL11' };
const out = [];
for (const f of readdirSync(dir).filter(n => n.endsWith('.json'))) {
  const j = JSON.parse(readFileSync(join(dir, f), 'utf8'));
  const p = j.price[0], dates = p.d, at = new Map(dates.map((d, k) => [d, k]));
  const rows = [];
  for (const doc of j.broker) for (let k = 0; k < doc.d.length; k++)
    rows.push({ d: doc.d[k], b: doc.b[k], i: doc.i[k], m: doc.m[k], bv: doc.bv[k], sv: doc.sv[k], bl: doc.bl[k], sl: doc.sl[k], bf: doc.bf[k], sf: doc.sf[k] });
  const R = flowRows(rows, dates.length, d => at.get(d) ?? -1);
  const num = x => typeof x === 'number' && Number.isFinite(x) ? x : null;
  const ctx = { rows: R, dates, close: p.c.map(num), volume: p.v.map(num), insider: [], classification: {} };
  for (const [key, id] of Object.entries(ids)) {
    const cell = j.screener?.[key]; if (!cell) { out.push({ t: j.ticker, id, screener: null }); continue }
    const k = at.get(cell[1]), v = computeFlow(id, ctx, {}).value?.[k] ?? null;
    const same = v === null ? cell[0] === null : Math.abs(v - cell[0]) <= 1e-9 * Math.max(1, Math.abs(v));
    out.push({ t: j.ticker, id, date: cell[1], screener: cell[0], terminal: v, same });
  }
}
for (const r of out) console.log(JSON.stringify(r));
console.log(JSON.stringify({ compared: out.length, equal: out.filter(r => r.same).length }));
