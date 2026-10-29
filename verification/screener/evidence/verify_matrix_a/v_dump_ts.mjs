// Verifier: dump terminal F outputs (defaults and selected alternates) per ticker to data/<T>.ts.json
import fs from 'node:fs';
const { F } = await import('/home/user/saniti/apps/edge-bff/terminal/src/calc/indicators.ts');
const dir = '/tmp/claude-0/-home-user-saniti/65bd49d0-9dca-5072-b7db-b62314cf2cd3/scratchpad/audit/verify_matrix_a/data/';
const RUNS = [
  ['sma', {}], ['ema', {}], ['wma', {}], ['wma_hlc3_9', 'wma', { length: 9, source: 'hlc3' }], ['hma', {}], ['hma_16', 'hma', { length: 16 }], ['hma_7', 'hma', { length: 7 }],
  ['kama', {}], ['kama_hl2_5', 'kama', { length: 5, source: 'hl2' }], ['kama_3_20', 'kama', { fast_length: 3, slow_length: 20 }],
  ['macd', {}], ['adx', {}], ['adx_7_7', 'adx', { di_length: 7, adx_smoothing: 7 }], ['adx_14_7', 'adx', { di_length: 14, adx_smoothing: 7 }],
  ['aroon', {}], ['supertrend', {}], ['donchian', {}], ['keltner', {}], ['psar', {}], ['psar_alt', 'psar', { start: 0.01, increment: 0.03, maximum: 0.25 }],
  ['rsi', {}], ['stoch_rsi', {}], ['stochastic', {}], ['stochastic_5_1_3', 'stochastic', { k_length: 5, smooth_k: 1, d_length: 3 }],
  ['williams_r', {}], ['williams_r_hl2', 'williams_r', { source: 'hl2' }], ['roc', {}], ['momentum', {}], ['cci', {}], ['cci_14', 'cci', { length: 14 }], ['cmo', {}],
  ['tsi', {}], ['trix', {}], ['ultimate_osc', {}], ['uo_desc', 'ultimate_osc', { fast_length: 28, middle_length: 14, slow_length: 7 }],
  ['awesome_osc', {}], ['ppo', {}], ['ppo_5_20_4', 'ppo', { fast_length: 5, slow_length: 20, signal_length: 4 }], ['ppo_swap', 'ppo', { fast_length: 26, slow_length: 12 }],
  ['bop', {}], ['bollinger', {}], ['bb_ema', 'bollinger', { basis_ma_type: 'EMA' }], ['bb_wma', 'bollinger', { basis_ma_type: 'WMA' }],
  ['bb_rma', 'bollinger', { basis_ma_type: 'RMA' }], ['bb_vwma', 'bollinger', { basis_ma_type: 'VWMA' }], ['atr', {}], ['atr_10', 'atr', { length: 10 }],
];
for (const t of process.argv.slice(2)) {
  const d = JSON.parse(fs.readFileSync(dir + t + '.json'));
  const P = d.price.rows;
  const B = { T: P.map(r => r[0]), O: P.map(r => r[1]), H: P.map(r => r[2]), L: P.map(r => r[3]), C: P.map(r => r[4]), V: P.map(r => r[5]) };
  const res = {};
  for (const r of RUNS) {
    const [name, a, b] = r; const key = typeof a === 'string' ? a : name, p = typeof a === 'string' ? b : a;
    res[name] = F[key](B, p);
  }
  fs.writeFileSync(dir + t + '.ts.json', JSON.stringify(res));
  console.log(t, Object.keys(res).length);
}
