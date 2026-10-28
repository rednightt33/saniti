// verify_matrix_b: run terminal F (I28..I53) on data/<T>.json. START env truncates history. PARAMS env: JSON {key: params}.
import fs from 'node:fs'; import path from 'node:path';
const { F } = await import('/home/user/saniti/apps/edge-bff/terminal/src/calc/indicators.ts');
const D = path.dirname(new URL(import.meta.url).pathname);
const KEYS = ['bollinger_pctb','bollinger_width','atr','natr','stddev','hist_vol','adr','volume_sma','volume_ema','rvol','pvo','volume_roc','obv','pvt','vwma','vwap','adl','cmf','chaikin_osc','mfi','force_index','eom','nvi','pvi','kvo','market_fi'];
const start = process.env.START || null, extra = JSON.parse(process.env.PARAMS || '{}'), tag = process.env.TAG || '';
for (const t of process.argv.slice(2)) {
  const d = JSON.parse(fs.readFileSync(path.join(D, 'data', t + '.json')));
  let i0 = 0; if (start) { i0 = d.T.findIndex(x => x >= start); if (i0 < 0) continue }
  const B = { O: d.O.slice(i0), H: d.H.slice(i0), L: d.L.slice(i0), C: d.C.slice(i0), V: d.V.slice(i0), T: d.T.slice(i0) };
  const res = {};
  for (const k of (Object.keys(extra).length ? Object.keys(extra) : KEYS)) { const r = F[k](B, extra[k] || {}); delete r._breaks; res[k] = r }
  fs.writeFileSync(path.join(D, 'ts', t + (start ? '_' + start : '') + tag + '.json'), JSON.stringify({ ticker: t, i0, T: B.T, res }));
}
