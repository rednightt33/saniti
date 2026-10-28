// Runs the terminal TS indicators (I28..I53, defaults) on data/<T>.json; writes ts/<T>.json.
// Optional: START=YYYY-MM-DD truncates history (warm-up / start-dependence test) -> ts/<T>_<START>.json
import fs from 'node:fs'; import path from 'node:path';
const { F } = await import('/home/user/saniti/apps/edge-bff/terminal/src/calc/indicators.ts');
const D = path.dirname(new URL(import.meta.url).pathname);
const KEYS = ['bollinger_pctb','bollinger_width','atr','natr','stddev','hist_vol','adr','volume_sma','volume_ema','rvol','pvo','volume_roc','obv','pvt','vwma','vwap','adl','cmf','chaikin_osc','mfi','force_index','eom','nvi','pvi','kvo','market_fi'];
fs.mkdirSync(path.join(D, 'ts'), { recursive: true });
const start = process.env.START || null;
for (const t of process.argv.slice(2)) {
  const d = JSON.parse(fs.readFileSync(path.join(D, 'data', t + '.json')));
  let i0 = 0; if (start) i0 = d.T.findIndex(x => x >= start);
  const B = { O: d.O.slice(i0), H: d.H.slice(i0), L: d.L.slice(i0), C: d.C.slice(i0), V: d.V.slice(i0), T: d.T.slice(i0) };
  const out = { ticker: t, start: d.T[i0], i0, n: B.C.length, res: {} };
  const t0 = performance.now();
  for (const k of KEYS) { const r = F[k](B, {}); delete r._breaks; out.res[k] = r }
  out.ms = performance.now() - t0;
  fs.writeFileSync(path.join(D, 'ts', t + (start ? '_' + start : '') + '.json'), JSON.stringify(out));
  console.log(t, out.n, 'bars from', out.start, 'ms', out.ms.toFixed(1));
}
