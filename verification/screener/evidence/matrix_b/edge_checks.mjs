// Small code-behaviour checks on the TS module (no repo change).
import fs from 'node:fs'; import path from 'node:path';
const { F } = await import('/home/user/saniti/apps/edge-bff/terminal/src/calc/indicators.ts');
const D = path.dirname(new URL(import.meta.url).pathname);
const d = JSON.parse(fs.readFileSync(path.join(D, 'data', 'BBCA.json')));
const B = { O: d.O, H: d.H, L: d.L, C: d.C, V: d.V, T: d.T };
const last = (o, k) => o[k][o[k].length - 1];
// 1. annualization_periods is floored (LENGTH_KEYS matches "_periods")
console.log('hist_vol 252 vs 252.9:', last(F.hist_vol(B, { annualization_periods: 252 }), 'historical_volatility'), last(F.hist_vol(B, { annualization_periods: 252.9 }), 'historical_volatility'));
// 2. VWAP anchors: last values for Session / Week / Month / Year and band width
for (const a of ['Session', 'Week', 'Month', 'Quarter', 'Year']) { const r = F.vwap(B, { anchor: a }); console.log('vwap', a, last(r, 'vwap').toFixed(3), 'upper1', last(r, 'upper1').toFixed(3), 'breaks', r._breaks.length) }
// 3. bollinger basis RMA vs SMA, and VWMA (not in registry options) accepted by the module?
console.log('pctb SMA/RMA/VWMA:', last(F.bollinger_pctb(B, {}), 'percent_b'), last(F.bollinger_pctb(B, { basis_ma_type: 'RMA' }), 'percent_b'), last(F.bollinger_pctb(B, { basis_ma_type: 'VWMA' }), 'percent_b'));
// 4. invalid bar handling: a null close in the middle breaks volume-only indicators? (need V only)
const B2 = { ...B, C: B.C.slice() }; B2.C[1000] = null;
const vs = F.volume_sma(B2, {}).volume_sma, at = F.atr(B2, {}).atr, ob = F.obv(B2, {}).obv;
console.log('null close at 1000 -> volume_sma[1000..1001]', vs[1000] !== null, vs[1001] !== null, '| atr[1000], atr first valid after', at[1000], at.slice(1001).findIndex(v => v !== null) + 1001, '| obv[999], obv[1001] (restarts at V[1001])', ob[999], ob[1001], B.V[1001]);
// 5. OBV/ADL level start dependence illustration: obv full vs started at 2025-01-02 at the last bar
const i0 = d.T.findIndex(x => x >= '2025-01-02'); const Bt = { O: d.O.slice(i0), H: d.H.slice(i0), L: d.L.slice(i0), C: d.C.slice(i0), V: d.V.slice(i0), T: d.T.slice(i0) };
console.log('obv last full vs 2025 start:', last(F.obv(B, {}), 'obv'), last(F.obv(Bt, {}), 'obv'), '| nvi:', last(F.nvi(B, {}), 'nvi'), last(F.nvi(Bt, {}), 'nvi'));
// 6. %B range on BBCA (can be <0, >1)
const p = F.bollinger_pctb(B, {}).percent_b.filter(v => v !== null); console.log('%B min/max', Math.min(...p).toFixed(3), Math.max(...p).toFixed(3));
