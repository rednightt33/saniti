import fs from 'node:fs';
const { F } = await import('/home/user/saniti/apps/edge-bff/terminal/src/calc/indicators.ts');
const D = '/tmp/claude-0/-home-user-saniti/65bd49d0-9dca-5072-b7db-b62314cf2cd3/scratchpad/audit/verify_matrix_b';
const KEYS = ['bollinger_pctb','bollinger_width','atr','natr','stddev','hist_vol','adr','volume_sma','volume_ema','rvol','pvo','volume_roc','obv','pvt','vwma','vwap','adl','cmf','chaikin_osc','mfi','force_index','eom','nvi','pvi','kvo','market_fi'];
const d = JSON.parse(fs.readFileSync(D + '/data/BBCA.json'));
const B = { O: d.O, H: d.H, L: d.L, C: d.C, V: d.V, T: d.T };
for (let w = 0; w < 30; w++) for (const k of KEYS) F[k](B, {});
const per = {}; const R = 50; let tot = 0;
for (const k of KEYS) { const t0 = performance.now(); for (let r = 0; r < R; r++) F[k](B, {}); const ms = (performance.now() - t0) / R; per[k] = ms; tot += ms }
console.log('bars', B.C.length, 'all26_ms', tot.toFixed(2), 'max', Object.entries(per).sort((a,b)=>b[1]-a[1]).slice(0,4).map(([k,v])=>k+':'+v.toFixed(3)).join(' '));
console.log('market estimate s (x 1330722/' + B.C.length + '):', (tot * 1330722 / B.C.length / 1000).toFixed(2));
