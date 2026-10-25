/* Add the reference engine's expected values to the parity fixtures of tests/calc.

   The reference engine is `const TA = (() => { ... })();` of 03-terminal-right-panel.html (the user's
   upload; not committed). This script cuts it out of the file given on the command line, applies the
   conventions INDICATOR_SPEC.md sets for HTML rows (PATCHES, each must apply exactly once), runs the
   HTML-row cases on every <dir>/<TICKER>.json.gz and stores them under "html". I28/I29 (Bollinger %B and
   Bandwidth) are not here: the spec takes their bands from I27 (TA-Lib BBANDS), so gen_talib.py holds them.

     node apps/edge-bff/terminal/tests/calc/tools/gen_html.mjs <03-terminal-right-panel.html> <dir> [--digits 11]

   --digits as in gen_talib.py (committed fixtures: 11 significant digits).
*/
import fs from 'node:fs';
import zlib from 'node:zlib';
import path from 'node:path';

const PATCHES = [
  ['I30 (used by I09 Supertrend, I11 Keltner): no true range on the first bar (TA-Lib)',
   'const trOf = B => B.H.map((h, i) => i === 0 ? h - B.L[i] :', 'const trOf = B => B.H.map((h, i) => i === 0 ? null :'],
  ['I13 (used by I14 Stochastic RSI): RSI is 0 when gains and losses are both 0, i.e. their sum is within TA-Lib\'s 1e-14',
   'l[i] === 0 ? (a === 0 ? null : 100)', 'Math.abs(a + l[i]) < 1e-14 ? 0 : l[i] === 0 ? 100'],
  ['I14: fast %K is 0 on a zero range (TA-Lib STOCHRSI)',
   'return isN(v) && isN(r) && r !== 0 ? 100 * (v - lo[i]) / r : null', 'return isN(v) && isN(r) ? (r !== 0 ? 100 * (v - lo[i]) / r : 0) : null'],
];

function loadEngine(htmlPath) {
  const src = fs.readFileSync(htmlPath, 'utf8');
  const a = src.indexOf('const TA = (() => {'), endMark = 'return { F, isN, sma, ema, rma, wma, stdev };';
  const b = src.indexOf(endMark, a), c = src.indexOf('})();', b);
  if (a < 0 || b < 0 || c < 0) throw new Error('reference engine not found');
  let code = src.slice(a, c + 5);
  for (const [why, from, to] of PATCHES) {
    if (code.split(from).length !== 2) throw new Error('patch does not apply once: ' + why);
    code = code.replace(from, to);
  }
  return new Function(code + '\nreturn TA;')();
}

const base = [
  ['hma_9', 'hma', { length: 9, source: 'close' }, ['hma']],
  ['supertrend_10_3', 'supertrend', { atr_length: 10, factor: 3 }, ['supertrend', 'direction']],
  ['keltner_default', 'keltner', { length: 20, source: 'close', multiplier: 2, use_exponential_ma: true, bands_style: 'ATR', atr_length: 10 }, ['upper', 'basis', 'lower']],
  ['stoch_rsi_14_14_3_3', 'stoch_rsi', { rsi_length: 14, stoch_length: 14, smooth_k: 3, smooth_d: 3, source: 'close' }, ['k', 'd']],
  ['cmo_14', 'cmo', { length: 14, source: 'close' }, ['cmo']],
  ['tsi_25_13_7', 'tsi', { long_length: 25, short_length: 13, signal_length: 7, source: 'close' }, ['tsi', 'signal']],
  ['awesome_osc_5_34', 'awesome_osc', { fast_length: 5, slow_length: 34 }, ['ao']],
  ['hist_vol_20', 'hist_vol', { length: 20, source: 'close', return_type: 'log', annualization_periods: 252 }, ['historical_volatility']],
  ['adr_14', 'adr', { length: 14, timeframe: '1D' }, ['adr']],
];
const withVolume = [
  ['rvol_20', 'rvol', { length: 20, reference_method: 'rolling_sma', include_current_bar: true }, ['rvol']],
  ['pvt', 'pvt', {}, ['pvt']],
  ['vwma_20', 'vwma', { length: 20, source: 'close' }, ['vwma']],
  ['vwap_session', 'vwap', { anchor: 'Session', source: 'hlc3', bands_mode: 'StdDev', band_1_multiplier: 1 }, ['vwap', 'upper1', 'lower1']],
  ['vwap_month', 'vwap', { anchor: 'Month', source: 'hlc3', bands_mode: 'StdDev', band_1_multiplier: 1 }, ['vwap', 'upper1', 'lower1']],
  ['cmf_20', 'cmf', { length: 20 }, ['cmf']],
  ['force_index_13', 'force_index', { length: 13 }, ['force_index']],
  ['eom_14', 'eom', { length: 14, volume_scale: 1000000 }, ['eom']],
  ['nvi', 'nvi', { initial_value: 1000 }, ['nvi']],
  ['pvi', 'pvi', { initial_value: 1000 }, ['pvi']],
  ['kvo_34_55_13', 'kvo', { fast_length: 34, slow_length: 55, signal_length: 13 }, ['kvo', 'signal']],
  ['market_fi', 'market_fi', { volume_scale: 1 }, ['market_fi']],
];
const alt = [   // other parameters, GOTO only
  ['alt_hma_16_hl2', 'hma', { length: 16, source: 'hl2' }, ['hma']],
  ['alt_supertrend_7_2_5', 'supertrend', { atr_length: 7, factor: 2.5 }, ['supertrend', 'direction']],
  ['alt_keltner_tr_sma', 'keltner', { length: 10, source: 'hlc3', multiplier: 1.5, use_exponential_ma: false, bands_style: 'TR', atr_length: 10 }, ['upper', 'basis', 'lower']],
  ['alt_keltner_hl', 'keltner', { length: 20, source: 'close', multiplier: 2, use_exponential_ma: true, bands_style: 'HL_RANGE', atr_length: 10 }, ['upper', 'basis', 'lower']],
  ['alt_stoch_rsi_7_10_1_5', 'stoch_rsi', { rsi_length: 7, stoch_length: 10, smooth_k: 1, smooth_d: 5, source: 'ohlc4' }, ['k', 'd']],
  ['alt_cmo_9_hlc3', 'cmo', { length: 9, source: 'hlc3' }, ['cmo']],
  ['alt_tsi_13_7_5', 'tsi', { long_length: 13, short_length: 7, signal_length: 5, source: 'hl2' }, ['tsi', 'signal']],
  ['alt_ao_3_20', 'awesome_osc', { fast_length: 3, slow_length: 20 }, ['ao']],
  ['alt_hist_vol_simple', 'hist_vol', { length: 10, source: 'close', return_type: 'simple', annualization_periods: 365 }, ['historical_volatility']],
  ['alt_vwap_week_pct', 'vwap', { anchor: 'Week', source: 'close', bands_mode: 'Percentage', band_1_multiplier: 2 }, ['vwap', 'upper1', 'lower1']],
  ['alt_vwap_quarter', 'vwap', { anchor: 'Quarter', source: 'ohlc4', bands_mode: 'StdDev', band_1_multiplier: 2 }, ['vwap', 'upper1', 'lower1']],
  ['alt_vwap_year_none', 'vwap', { anchor: 'Year', source: 'hlc3', bands_mode: 'None', band_1_multiplier: 1 }, ['vwap', 'upper1', 'lower1']],
  ['alt_vwma_10_hl2', 'vwma', { length: 10, source: 'hl2' }, ['vwma']],
  ['alt_kvo_10_20_5', 'kvo', { fast_length: 10, slow_length: 20, signal_length: 5 }, ['kvo', 'signal']],
  ['alt_eom_5', 'eom', { length: 5, volume_scale: 1 }, ['eom']],
  ['alt_nvi_100', 'nvi', { initial_value: 100 }, ['nvi']],
];

const enc = (a, digits) => {
  const v = a.map(x => (x === null || x === undefined || !Number.isFinite(x)) ? null : (digits ? Number(x.toPrecision(digits)) : x));
  let s = v.findIndex(x => x !== null); if (s < 0) s = v.length;
  return { s, v: v.slice(s) };
};

const [htmlPath, dir, ...rest] = process.argv.slice(2);
const digits = rest[0] === '--digits' ? Number(rest[1]) : 0;
const TA = loadEngine(htmlPath);
for (const f of fs.readdirSync(dir).filter(f => f.endsWith('.json.gz')).sort()) {
  const file = path.join(dir, f), d = JSON.parse(zlib.gunzipSync(fs.readFileSync(file)).toString());
  const B = { T: d.T, O: d.O, H: d.H, L: d.L, C: d.C, V: d.V };
  const vol = d.V.some(v => v !== null);
  const list = [...base, ...(vol ? withVolume : []), ...(d.ticker === 'GOTO' ? alt : [])];
  d.html = list.map(([name, key, params, outs]) => {
    const r = TA.F[key](B, params), c = { name, key, params, outs: {} };
    for (const o of outs) c.outs[o] = enc(r[o], digits);
    if (r._breaks) c.breaks = r._breaks;
    return c;
  });
  d.html_meta = { engine: path.basename(htmlPath), patches: PATCHES.map(p => p[0]), digits: digits || 'full' };
  fs.writeFileSync(file, zlib.gzipSync(JSON.stringify(d), { level: 9 }));
  console.log(d.ticker, d.html.length, 'cases');
}
