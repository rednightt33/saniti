// Runs the terminal indicators (I01-I27 + atr) on fetched bars; compares with Feature 04; dumps TS outputs for the TA-Lib check.
import fs from 'node:fs';
import path from 'node:path';
const { F, DEFAULTS } = await import('/home/user/saniti/apps/edge-bff/terminal/src/calc/indicators.ts');
const dir = path.dirname(new URL(import.meta.url).pathname);
const tickers = process.argv.slice(2);
const rel = (a, b) => (a === b ? 0 : Math.abs(a - b) / Math.max(Math.abs(a), Math.abs(b)));
const firstValid = s => s.findIndex(v => v !== null && v !== undefined);
const report = [];
const KEYS = ['sma','ema','wma','hma','kama','macd','adx','aroon','supertrend','donchian','keltner','psar','rsi','stoch_rsi','stochastic','williams_r','roc','momentum','cci','cmo','tsi','trix','ultimate_osc','awesome_osc','ppo','bop','bollinger','atr'];
for (const t of tickers) {
  const d = JSON.parse(fs.readFileSync(path.join(dir, 'data', t + '.json')));
  const P = d.price.rows, Fc = d.f04.cols, Fr = d.f04.rows;
  const B = { T: P.map(r => r[0]), O: P.map(r => r[1]), H: P.map(r => r[2]), L: P.map(r => r[3]), C: P.map(r => r[4]), V: P.map(r => r[5]) };
  const datesEqual = Fr.length === P.length && Fr.every((r, i) => r[0] === P[i][0]);
  const col = name => Fr.map(r => r[Fc.indexOf(name)]);
  const pairs = [
    ['sma_20', F.sma(B, { length: 20 }).sma], ['sma_50', F.sma(B, { length: 50 }).sma],
    ['ema_12', F.ema(B, { length: 12 }).ema], ['ema_26', F.ema(B, { length: 26 }).ema],
    ['ema_50', F.ema(B, { length: 50 }).ema], ['ema_200', F.ema(B, { length: 200 }).ema],
    ['rsi_14', F.rsi(B, {}).rsi],
    ['macd', F.macd(B, {}).macd], ['macd_signal', F.macd(B, {}).signal], ['macd_histogram', F.macd(B, {}).histogram],
    ['atr_14', F.atr(B, {}).atr], ['adx_14', F.adx(B, {}).adx],
    ['bb_upper_20', F.bollinger(B, {}).upper], ['bb_middle_20', F.bollinger(B, {}).basis], ['bb_lower_20', F.bollinger(B, {}).lower],
    ['close', B.C],
  ];
  for (const [name, ts] of pairs) {
    const f4 = col(name);
    let maxr = 0, nullMismatch = 0, n = 0, argmax = -1;
    for (let i = 0; i < ts.length; i++) {
      const a = ts[i], b = f4[i];
      if ((a === null) !== (b === null)) { nullMismatch++; continue }
      if (a === null) continue;
      n++; const r = rel(a, b); if (r > maxr) { maxr = r; argmax = i }
    }
    report.push({ ticker: t, bars: P.length, datesEqual, column: name, ts_first: firstValid(ts), f04_first: firstValid(f4), compared: n, nullMismatch, maxRel: maxr, at: argmax >= 0 ? P[argmax][0] : null });
  }
  // dump TS outputs (defaults + a few alternates) for the TA-Lib comparison
  const dump = {};
  for (const k of KEYS) dump[k] = F[k](B, {});
  dump['kama_alt'] = F.kama(B, { length: 5, source: 'hl2' });
  dump['adx_7'] = F.adx(B, { di_length: 7, adx_smoothing: 7 });
  dump['adx_14_7'] = F.adx(B, { di_length: 14, adx_smoothing: 7 });
  dump['stochastic_5_1_3'] = F.stochastic(B, { k_length: 5, smooth_k: 1, d_length: 3 });
  dump['ppo_5_20_4'] = F.ppo(B, { fast_length: 5, slow_length: 20, signal_length: 4 });
  dump['bollinger_ema'] = F.bollinger(B, { basis_ma_type: 'EMA' });
  dump['bollinger_10_1_5'] = F.bollinger(B, { length: 10, std_dev: 1.5 });
  dump['psar_alt'] = F.psar(B, { start: 0.01, increment: 0.03, maximum: 0.25 });
  dump['cci_14'] = F.cci(B, { length: 14 });
  dump['uo_alt'] = F.ultimate_osc(B, { fast_length: 5, middle_length: 10, slow_length: 20 });
  dump['wma_hlc3'] = F.wma(B, { length: 9, source: 'hlc3' });
  fs.writeFileSync(path.join(dir, 'data', t + '.ts.json'), JSON.stringify({ bars: B, out: dump }));
}
fs.writeFileSync(path.join(dir, 'f04_vs_ts.json'), JSON.stringify(report, null, 1));
console.table(report.map(r => ({ t: r.ticker, n: r.bars, d: r.datesEqual, col: r.column, tsF: r.ts_first, f4F: r.f04_first, cmp: r.compared, nullMis: r.nullMismatch, maxRel: r.maxRel.toExponential(2), at: r.at })));
