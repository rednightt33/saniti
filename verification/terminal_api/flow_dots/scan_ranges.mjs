import { createRequire } from 'node:module';
import { readFileSync, writeFileSync } from 'node:fs';
import { serve } from '/home/user/saniti/verification/terminal_api/terminal_look/serve.mjs';
const { chromium } = createRequire('/home/user/saniti/verification/terminal_api/terminal_look/')('playwright');
const SP = '/tmp/claude-0/-home-user-saniti/5abac1e8-94e8-5166-9d5b-02bb4e4273bc/scratchpad';
const reg = JSON.parse(readFileSync('/home/user/saniti/apps/edge-bff/terminal/src/data/flowRegistry.json', 'utf8')).indicators;
const ids = reg.map(r => r.id).filter(x => x !== 'FL23');
const { origin, close } = await serve(SP + '/look', 'BBRI');
const b = await chromium.launch(), out = {};
for (let k = 0; k < ids.length; k += 8) {
  const batch = ids.slice(k, k + 8), ctx = await b.newContext({ viewport:{ width:1440, height:2400 } }), p = await ctx.newPage();
  await p.addInitScript(list => { localStorage.setItem('ml.ind.v1', JSON.stringify(list.map(d => ({ def:d, params:{} })))) }, batch);
  await p.goto(origin + '/terminal-app/'); await p.waitForFunction(() => !document.querySelector('.ml-boot'), null, { timeout:30000 }); await p.waitForTimeout(4000);
  const v = await p.evaluate(() => window.marketLabIndicators.values('2026-01-01'));
  for (const x of v) out[x.id] = { title:x.title, outputs:x.outputs };
  await ctx.close();
}
writeFileSync(`${SP}/ranges/values.json`, JSON.stringify(out));
const rows = [];
for (const r of reg) { const o = out[r.id]; if (!o) continue;
  for (const [k, a] of Object.entries(o.outputs)) { const vs = a.map(e => e[1]).filter(v => v !== null && Number.isFinite(v));
    if (!vs.length) { rows.push([r.id, k, r.unit, 0]); continue }
    const ints = vs.every(v => Math.abs(v - Math.round(v)) < 1e-9), mn = Math.min(...vs), mx = Math.max(...vs), dist = new Set(vs.map(v => +v.toFixed(6))).size;
    rows.push([r.id, k, r.unit, vs.length, ints, +mn.toFixed(3), +mx.toFixed(3), dist, r.name]) } }
writeFileSync(`${SP}/ranges/stats.json`, JSON.stringify(rows));
console.log(rows.filter(x => x[4]).map(x => x.join(' | ')).join('\n')); console.log('---non-integer, few distinct (<=30):');
console.log(rows.filter(x => !x[4] && x[7] <= 30).map(x => x.join(' | ')).join('\n'));
await b.close(); close();
