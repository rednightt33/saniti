/* EXEC-TERMINAL-FLOW-IND S5: the Terminal's Flow calculations (apps/edge-bff/terminal/src/calc/flow.ts) against the
   independent oracle (oracle/oracle.py, written from FORMULAS.md without reading flow.ts), on the same raw rows.

   The raw rows are the oracle's own cache (oracle/cache/<TICKER>.json.gz: Feature 05 with buy_freq/sell_freq, the daily
   prices, the insider events) and the broker classes (cache/broker_profile.json). They are shaped the way the Terminal's
   worker shapes the published broker files (data/worker.ts flowRowsOf: a row on a date without a price candle is not on
   the chart), then every case of oracle/cases.json is computed with computeFlow and compared with oracle/out/<TICKER>.json
   from report_from: same nulls, |a - b| <= 1e-9 x max(1, |a|, |b|).

   Run from apps/edge-bff/terminal:  npx vite-node ../../../verification/terminal_api/flow_indicators/oracle_compare.ts [TICKER ...]
   Writes oracle/compare.json (every mismatch, at most 5 per case and output) and prints a summary. */
import { readFileSync, writeFileSync } from 'node:fs';
import { gunzipSync } from 'node:zlib';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { computeFlow, flowRows, type FlowContext } from '../../../apps/edge-bff/terminal/src/calc/flow';

const HERE = dirname(fileURLToPath(import.meta.url)), OR = join(HERE, 'oracle');
const cfg = JSON.parse(readFileSync(join(OR, 'cases.json'), 'utf8'));
const profile: [string, string][] = JSON.parse(readFileSync(join(OR, 'cache', 'broker_profile.json'), 'utf8'));
const classification = Object.fromEntries(profile.filter(r => r[1]).map(r => [r[0], r[1]]));
const tickers = process.argv.slice(2).length ? process.argv.slice(2) : cfg.tickers;
const close = (a: number, b: number) => Math.abs(a - b) <= 1e-9 * Math.max(1, Math.abs(a), Math.abs(b));

const report: any = { report_from:cfg.report_from, tickers:{} };
let total = 0, bad = 0;
for (const tk of tickers) {
  const raw = JSON.parse(gunzipSync(readFileSync(join(OR, 'cache', `${tk}.json.gz`))).toString('utf8'));
  const oracle = JSON.parse(readFileSync(join(OR, 'out', `${tk}.json`), 'utf8'));
  const dates: string[] = raw.price.map((r: any) => r[0]), N = dates.length, idx = new Map(dates.map((d, i) => [d, i]));
  const rows = raw.broker.filter((r: any) => r[0] <= cfg.broker_through).map((r: any) => ({ d:r[0], b:r[1], i:r[2], m:r[3],
    bv:Number(r[4]), sv:Number(r[5]), bl:Number(r[6]), sl:Number(r[7]), bf:r[8], sf:r[9] }));
  const insider = raw.insider.filter((r: any) => (r[1] === 'BUY' || r[1] === 'SELL') && idx.has(r[0]))
    .map((r: any) => ({ t:idx.get(r[0])!, value:(r[1] === 'BUY' ? 1 : -1) * Number(r[2] ?? 0) }));
  const ctx: FlowContext = { rows:flowRows(rows, N, d => idx.get(d) ?? -1), dates, close:raw.price.map((r: any) => Number(r[1])),
    volume:raw.price.map((r: any) => Number(r[2])), insider, classification };
  const from = dates.findIndex(d => d >= cfg.report_from), per: any[] = [];
  for (const c of oracle.cases) {
    const t0 = performance.now(), got: any = computeFlow(c.id, ctx, structuredClone(c.params)), ms = performance.now() - t0;
    const entry: any = { id:c.id, case:c.case, ms:Math.round(ms), outputs:{} };
    for (const [k, want] of Object.entries<[string, number | null][]>(c.outputs)) {
      const s = got[k], diffs: any[] = []; let n = 0, nbad = 0;
      if (!s) { entry.outputs[k] = { missing:true }; bad++; total++; continue }
      for (const [d, w] of want) {
        const i = idx.get(d)!; if (i < from) continue;
        const g = s[i] ?? null; n++;
        const ok = g === null || w === null ? g === w : close(g, w);
        if (!ok) { nbad++; if (diffs.length < 5) diffs.push({ d, terminal:g, oracle:w }) }
      }
      total += n; bad += nbad;
      entry.outputs[k] = { compared:n, mismatches:nbad, ...(diffs.length ? { first:diffs } : {}) };
    }
    const extra = Object.keys(got).filter(k => !(k in c.outputs) && !k.startsWith('_'));
    if (c.id === 'FL23' && extra.length) entry.terminal_only = extra;
    per.push(entry);
  }
  report.tickers[tk] = per;
  const fails = per.filter(e => Object.values<any>(e.outputs).some(o => o.missing || o.mismatches));
  const slow = per.filter(e => e.ms > 50).map(e => `${e.id}/${e.case} ${e.ms}ms`);
  console.log(`${tk}: ${per.length} cases, ${fails.length} with differences${fails.length ? ': ' + fails.map(e => `${e.id}/${e.case}`).join(', ') : ''}`
    + (slow.length ? ` | over 50 ms: ${slow.join(', ')}` : ''));
}
report.summary = { values:total, mismatches:bad };
writeFileSync(join(OR, 'compare.json'), JSON.stringify(report, null, 1));
console.log(`values compared ${total}, mismatches ${bad}`);
