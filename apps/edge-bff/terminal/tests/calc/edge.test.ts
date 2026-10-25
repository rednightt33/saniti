/* Registry coverage and edge cases of src/calc/indicators.ts on synthetic bars: flat prices, zero volume,
   zero range (H = L), a single bar, a length longer than the series, missing (null/NaN) inputs, a gap of dates,
   invalid parameters. */
import { describe, expect, it } from 'vitest';
import { DEFAULTS, F, type Bars, type Out } from '../../src/calc/indicators';

/* indRegistry of 03-terminal-right-panel.html (line 770): key -> id, output keys, parameter defaults */
const REGISTRY: Record<string, { id: string; outs: string[]; defs: Record<string, any> }> = {
  sma: { id: 'I01', outs: ['sma'], defs: { length: 20, source: 'close' } },
  ema: { id: 'I02', outs: ['ema'], defs: { length: 20, source: 'close' } },
  wma: { id: 'I03', outs: ['wma'], defs: { length: 20, source: 'close' } },
  hma: { id: 'I04', outs: ['hma'], defs: { length: 9, source: 'close' } },
  kama: { id: 'I05', outs: ['kama'], defs: { length: 10, fast_length: 2, slow_length: 30, source: 'close' } },
  macd: { id: 'I06', outs: ['macd', 'signal', 'histogram'], defs: { fast_length: 12, slow_length: 26, signal_length: 9, source: 'close' } },
  adx: { id: 'I07', outs: ['adx', 'plus_di', 'minus_di'], defs: { di_length: 14, adx_smoothing: 14 } },
  aroon: { id: 'I08', outs: ['aroon_up', 'aroon_down'], defs: { length: 14 } },
  supertrend: { id: 'I09', outs: ['supertrend', 'direction'], defs: { atr_length: 10, factor: 3 } },
  donchian: { id: 'I10', outs: ['upper', 'basis', 'lower'], defs: { length: 20 } },
  keltner: { id: 'I11', outs: ['upper', 'basis', 'lower'], defs: { length: 20, source: 'close', multiplier: 2, use_exponential_ma: true, bands_style: 'ATR', atr_length: 10 } },
  psar: { id: 'I12', outs: ['sar', 'direction'], defs: { start: 0.02, increment: 0.02, maximum: 0.2 } },
  rsi: { id: 'I13', outs: ['rsi'], defs: { length: 14, source: 'close' } },
  stoch_rsi: { id: 'I14', outs: ['k', 'd'], defs: { rsi_length: 14, stoch_length: 14, smooth_k: 3, smooth_d: 3, source: 'close' } },
  stochastic: { id: 'I15', outs: ['k', 'd'], defs: { k_length: 14, smooth_k: 3, d_length: 3 } },
  williams_r: { id: 'I16', outs: ['williams_r'], defs: { length: 14, source: 'close' } },
  roc: { id: 'I17', outs: ['roc'], defs: { length: 9, source: 'close' } },
  momentum: { id: 'I18', outs: ['momentum'], defs: { length: 10, source: 'close' } },
  cci: { id: 'I19', outs: ['cci'], defs: { length: 20, constant: 0.015 } },
  cmo: { id: 'I20', outs: ['cmo'], defs: { length: 14, source: 'close' } },
  tsi: { id: 'I21', outs: ['tsi', 'signal'], defs: { long_length: 25, short_length: 13, signal_length: 7, source: 'close' } },
  trix: { id: 'I22', outs: ['trix'], defs: { length: 15, source: 'close' } },
  ultimate_osc: { id: 'I23', outs: ['uo'], defs: { fast_length: 7, middle_length: 14, slow_length: 28, weight_fast: 4, weight_middle: 2, weight_slow: 1 } },
  awesome_osc: { id: 'I24', outs: ['ao'], defs: { fast_length: 5, slow_length: 34 } },
  ppo: { id: 'I25', outs: ['ppo', 'signal', 'histogram'], defs: { fast_length: 12, slow_length: 26, signal_length: 9, source: 'close' } },
  bop: { id: 'I26', outs: ['bop'], defs: { source: 'OHLC' } },
  bollinger: { id: 'I27', outs: ['upper', 'basis', 'lower'], defs: { length: 20, source: 'close', basis_ma_type: 'SMA', std_dev: 2 } },
  bollinger_pctb: { id: 'I28', outs: ['percent_b'], defs: { length: 20, source: 'close', std_dev: 2, basis_ma_type: 'SMA' } },
  bollinger_width: { id: 'I29', outs: ['bandwidth'], defs: { length: 20, source: 'close', std_dev: 2, basis_ma_type: 'SMA' } },
  atr: { id: 'I30', outs: ['atr'], defs: { length: 14, smoothing_type: 'RMA' } },
  natr: { id: 'I31', outs: ['natr'], defs: { length: 14, smoothing_type: 'RMA' } },
  stddev: { id: 'I32', outs: ['stddev'], defs: { length: 20, source: 'close', stdev_method: 'population' } },
  hist_vol: { id: 'I33', outs: ['historical_volatility'], defs: { length: 20, source: 'close', return_type: 'log', annualization_periods: 252 } },
  adr: { id: 'I34', outs: ['adr'], defs: { length: 14, timeframe: '1D' } },
  volume_sma: { id: 'I35', outs: ['volume_sma'], defs: { length: 20 } },
  volume_ema: { id: 'I36', outs: ['volume_ema'], defs: { length: 20 } },
  rvol: { id: 'I37', outs: ['rvol'], defs: { length: 20, reference_method: 'rolling_sma', include_current_bar: false } },
  pvo: { id: 'I38', outs: ['pvo', 'signal', 'histogram'], defs: { fast_length: 12, slow_length: 26, signal_length: 9 } },
  volume_roc: { id: 'I39', outs: ['volume_roc'], defs: { length: 10 } },
  obv: { id: 'I40', outs: ['obv'], defs: { calculation_parameters: 'none' } },
  pvt: { id: 'I41', outs: ['pvt'], defs: { calculation_parameters: 'none' } },
  vwma: { id: 'I42', outs: ['vwma'], defs: { length: 20, source: 'close' } },
  vwap: { id: 'I43', outs: ['vwap', 'upper1', 'lower1'], defs: { anchor: 'Session', source: 'hlc3', bands_mode: 'StdDev', band_1_multiplier: 1 } },
  adl: { id: 'I44', outs: ['adl'], defs: { calculation_parameters: 'none' } },
  cmf: { id: 'I45', outs: ['cmf'], defs: { length: 20 } },
  chaikin_osc: { id: 'I46', outs: ['chaikin_osc'], defs: { fast_length: 3, slow_length: 10 } },
  mfi: { id: 'I47', outs: ['mfi'], defs: { length: 14 } },
  force_index: { id: 'I48', outs: ['force_index'], defs: { length: 13 } },
  eom: { id: 'I49', outs: ['eom'], defs: { length: 14, volume_scale: 1000000 } },
  nvi: { id: 'I50', outs: ['nvi'], defs: { initial_value: 1000 } },
  pvi: { id: 'I51', outs: ['pvi'], defs: { initial_value: 1000 } },
  kvo: { id: 'I52', outs: ['kvo', 'signal'], defs: { fast_length: 34, slow_length: 55, signal_length: 13 } },
  market_fi: { id: 'I53', outs: ['market_fi'], defs: { volume_scale: 1 } },
};
/* registry parameters the calculation does not read (fixed by the spec or informational) */
const IGNORED = ['bop.source', 'adr.timeframe', 'rvol.reference_method', 'rvol.include_current_bar', 'obv.calculation_parameters', 'pvt.calculation_parameters', 'adl.calculation_parameters'];
const KEYS = Object.keys(REGISTRY);

/* ---- synthetic bars ---- */
function dates(n: number, start = Date.UTC(2024, 0, 1)): string[] {
  const out: string[] = []; let t = start;
  while (out.length < n) { const d = new Date(t); if (d.getUTCDay() % 6) out.push(d.toISOString().slice(0, 10)); t += 864e5 }
  return out;
}
function walk(n: number, seed = 7): Bars {                     // deterministic random walk with integer prices
  let s = seed; const r = () => ((s = (s * 16807) % 2147483647) / 2147483647);
  const O: number[] = [], H: number[] = [], L: number[] = [], C: number[] = [], V: number[] = [];
  let c = 1000;
  for (let i = 0; i < n; i++) {
    const o = c, cl = Math.max(50, Math.round(o + (r() - 0.5) * 60)), h = Math.max(o, cl) + Math.round(r() * 20), l = Math.min(o, cl) - Math.round(r() * 20);
    O.push(o); H.push(h); L.push(l); C.push(cl); V.push(Math.round(r() * 1e6)); c = cl;
  }
  return { T: dates(n), O, H, L, C, V };
}
const flat = (n: number, price = 100, vol = 1000): Bars => ({ T: dates(n), O: Array(n).fill(price), H: Array(n).fill(price), L: Array(n).fill(price), C: Array(n).fill(price), V: Array(n).fill(vol) });
const last = (o: Out, k: string) => o[k][o[k].length - 1];
const finiteOrNull = (o: Out) => Object.entries(o).every(([k, a]) => k === '_breaks' || a.every(v => v === null || Number.isFinite(v)));

describe('registry coverage', () => {
  it('has the 53 registry keys and no other', () => {
    expect(KEYS).toHaveLength(53);
    expect(Object.keys(F).sort()).toEqual([...KEYS].sort());
  });
  it.each(KEYS)('%s returns every registry output, aligned to the bars', key => {
    const B = walk(300), o = F[key](B, REGISTRY[key].defs);
    for (const k of REGISTRY[key].outs) expect(o[k], `${key}.${k}`).toHaveLength(300);
    expect(finiteOrNull(o)).toBe(true);
    if (key === 'vwap') expect(Array.isArray(o._breaks)).toBe(true);
  });
  it.each(KEYS)('%s: DEFAULTS equal the registry defaults', key => {
    for (const [k, v] of Object.entries(REGISTRY[key].defs)) {
      if (IGNORED.includes(`${key}.${k}`)) continue;
      expect(DEFAULTS[key][k], `${key}.${k}`).toEqual(v);
    }
    expect(F[key](walk(120))).toEqual(F[key](walk(120), REGISTRY[key].defs));   // missing params take the defaults
  });
});

describe('flat prices', () => {
  const B = flat(120), all = Object.fromEntries(KEYS.map(k => [k, F[k](B)]));
  it('never produce NaN or Infinity', () => { for (const k of KEYS) expect(finiteOrNull(all[k]), k).toBe(true) });
  it('follow the zero-range conventions', () => {
    expect(last(all.rsi, 'rsi')).toBe(0);                                  // I13: TA-Lib 0
    expect(last(all.stochastic, 'k')).toBe(0); expect(last(all.stochastic, 'd')).toBe(0);   // I15
    expect(last(all.stoch_rsi, 'k')).toBe(0); expect(last(all.stoch_rsi, 'd')).toBe(0);     // I14
    expect(last(all.williams_r, 'williams_r')).toBe(0);                    // I16: TA-Lib WILLR 0
    expect(last(all.bop, 'bop')).toBe(0);                                  // I26
    expect(last(all.cci, 'cci')).toBe(0);                                  // I19: TA-Lib 0
    expect(last(all.cmo, 'cmo')).toBeNull();                               // I20: 0/0 -> null (HTML)
    expect(last(all.mfi, 'mfi')).toBe(0);                                  // I47: TA-Lib 0 below 1
    expect(last(all.atr, 'atr')).toBe(0); expect(last(all.natr, 'natr')).toBe(0);
    expect(last(all.adx, 'plus_di')).toBe(0); expect(last(all.adx, 'adx')).toBe(0);
    expect(last(all.stddev, 'stddev')).toBe(0); expect(last(all.hist_vol, 'historical_volatility')).toBe(0);
    expect(last(all.bollinger, 'upper')).toBe(100); expect(last(all.bollinger, 'lower')).toBe(100);
    expect(last(all.bollinger_pctb, 'percent_b')).toBeNull();              // zero band width -> null
    expect(last(all.bollinger_width, 'bandwidth')).toBe(0);
    expect(last(all.kama, 'kama')).toBe(100); expect(last(all.ema, 'ema')).toBe(100);
    expect(last(all.aroon, 'aroon_up')).toBe(100);                         // most recent extreme wins ties
    expect(last(all.obv, 'obv')).toBe(1000);                               // I40: starts at the first volume
    expect(last(all.adl, 'adl')).toBe(0); expect(last(all.chaikin_osc, 'chaikin_osc')).toBe(0);
    expect(last(all.roc, 'roc')).toBe(0); expect(last(all.trix, 'trix')).toBe(0);
    expect(last(all.ppo, 'ppo')).toBe(0); expect(last(all.macd, 'histogram')).toBe(0);
  });
});

describe('zero volume', () => {
  const B = { ...walk(120), V: Array(120).fill(0) }, o = (k: string) => F[k](B);
  it('gives null where volume divides and 0 where TA-Lib does', () => {
    for (const k of KEYS) expect(finiteOrNull(o(k)), k).toBe(true);
    expect(last(o('rvol'), 'rvol')).toBeNull(); expect(last(o('volume_roc'), 'volume_roc')).toBeNull();
    expect(last(o('vwma'), 'vwma')).toBeNull(); expect(last(o('vwap'), 'vwap')).toBeNull();
    expect(last(o('cmf'), 'cmf')).toBeNull(); expect(last(o('market_fi'), 'market_fi')).toBeNull(); expect(last(o('eom'), 'eom')).toBeNull();
    expect(last(o('mfi'), 'mfi')).toBe(0); expect(last(o('pvo'), 'pvo')).toBe(0);
    expect(last(o('obv'), 'obv')).toBe(0); expect(last(o('adl'), 'adl')).toBe(0); expect(last(o('force_index'), 'force_index')).toBe(0);
    expect(last(o('nvi'), 'nvi')).toBe(1000); expect(last(o('pvi'), 'pvi')).toBe(1000);
  });
  it('a single zero-volume bar: VROC null on the bar that divides by it', () => {
    const W = walk(40), V = [...W.V]; V[20] = 0;
    const r = F.volume_roc({ ...W, V }, { length: 10 }).volume_roc;
    expect(r[30]).toBeNull(); expect(r[29]).not.toBeNull(); expect(r[31]).not.toBeNull();
  });
});

describe('zero range bars (H = L)', () => {
  const W = walk(60), H = [...W.H], L = [...W.L], C = [...W.C], O = [...W.O];
  for (const i of [30, 31]) { H[i] = L[i] = C[i] = O[i] = W.C[i] }
  const B = { ...W, O, H, L, C };
  it('BOP 0, A/D unchanged, Market FI 0 on the bar', () => {
    expect(F.bop(B).bop[30]).toBe(0);
    const ad = F.adl(B).adl; expect(ad[30]).toBe(ad[29]);
    expect(F.market_fi(B).market_fi[30]).toBe(0);
    for (const k of KEYS) expect(finiteOrNull(F[k](B)), k).toBe(true);
  });
});

describe('short series', () => {
  it('a single bar returns length-1 outputs without throwing', () => {
    const B: Bars = { T: ['2024-01-02'], O: [10], H: [12], L: [9], C: [11], V: [500] };
    for (const k of KEYS) { const o = F[k](B); for (const out of REGISTRY[k].outs) expect(o[out], `${k}.${out}`).toHaveLength(1) }
    expect(F.obv(B).obv).toEqual([500]); expect(F.pvt(B).pvt).toEqual([0]); expect(F.nvi(B).nvi).toEqual([1000]);
    expect(F.bop(B).bop).toEqual([(11 - 10) / 3]); expect(F.vwap(B).vwap).toEqual([(12 + 9 + 11) / 3]);
    expect(F.sma(B, { length: 1 }).sma).toEqual([11]); expect(F.rsi(B).rsi).toEqual([null]); expect(F.psar(B).sar).toEqual([null]);
  });
  it('no bars returns empty outputs', () => {
    const B: Bars = { T: [], O: [], H: [], L: [], C: [], V: [] };
    for (const k of KEYS) for (const out of REGISTRY[k].outs) expect(F[k](B)[out]).toEqual([]);
  });
  it('a length longer than the series gives only nulls', () => {
    const B = walk(30);
    for (const [k, p] of [['sma', { length: 31 }], ['ema', { length: 40 }], ['rsi', { length: 30 }], ['atr', { length: 30 }], ['bollinger', { length: 31 }],
      ['adx', { di_length: 30, adx_smoothing: 5 }], ['kama', { length: 30 }], ['cci', { length: 31 }], ['mfi', { length: 30 }], ['ultimate_osc', { slow_length: 30 }],
      ['stochastic', { k_length: 31 }], ['macd', { slow_length: 31 }], ['aroon', { length: 30 }], ['chaikin_osc', { slow_length: 31 }], ['wma', { length: 31 }]] as const) {
      const o = F[k](B, p as any);
      for (const out of REGISTRY[k].outs) expect(o[out].every(v => v === null), `${k}.${out}`).toBe(true);
    }
  });
});

describe('missing inputs', () => {
  const W = walk(200);
  it.each([null, NaN, undefined, Infinity])('a bar of %s values is null and every calculation restarts after it', bad => {
    const put = (a: Bars['C']) => { const x: (number | null | undefined)[] = [...a]; x[90] = bad; return x };
    const B = { ...W, O: put(W.O), H: put(W.H), L: put(W.L), C: put(W.C), V: put(W.V) }, after = (b: Bars) => ({ T: b.T!.slice(91), O: b.O.slice(91), H: b.H.slice(91), L: b.L.slice(91), C: b.C.slice(91), V: b.V.slice(91) });
    for (const k of KEYS) {
      const o = F[k](B), fresh = F[k](after(W));
      expect(finiteOrNull(o), k).toBe(true);
      for (const out of REGISTRY[k].outs) {
        expect(o[out][90], `${k}.${out} on the missing bar`).toBeNull();
        expect(o[out].slice(91), `${k}.${out} after the missing bar`).toEqual(fresh[out]);
      }
    }
  });
  it('a missing close nulls the indicators that read it', () => {
    const C: (number | null)[] = [...W.C]; C[90] = null;
    for (const k of ['sma', 'rsi', 'atr', 'adx', 'macd', 'obv', 'stochastic', 'cci', 'mfi', 'bop']) expect(F[k]({ ...W, C })[REGISTRY[k].outs[0]][90], k).toBeNull();
    expect(F.aroon({ ...W, C })).toEqual(F.aroon(W)); expect(F.donchian({ ...W, C })).toEqual(F.donchian(W));
  });
  it('indicators that do not read the missing input are unaffected', () => {
    const V: (number | null)[] = [...W.V]; V[90] = null;
    expect(F.rsi({ ...W, V })).toEqual(F.rsi(W)); expect(F.atr({ ...W, V })).toEqual(F.atr(W));
    expect(F.obv({ ...W, V }).obv[90]).toBeNull();
  });
  it('a series without volume (index) gives null volume indicators and full price indicators', () => {
    const B = { ...W, V: Array(200).fill(null) };
    expect(F.obv(B).obv.every(v => v === null)).toBe(true); expect(F.mfi(B).mfi.every(v => v === null)).toBe(true);
    expect(F.rsi(B)).toEqual(F.rsi(W));
  });
  it('does not change its inputs', () => {
    const B = walk(100), copy = JSON.parse(JSON.stringify(B));
    for (const k of KEYS) F[k](B);
    expect(B).toEqual(copy);
  });
});

describe('a gap of missing dates', () => {
  it('is not filled: bars are consecutive observations (only VWAP anchors read the dates)', () => {
    const W = walk(80), T = [...W.T!]; for (let i = 40; i < 80; i++) T[i] = dates(80, Date.UTC(2024, 6, 1))[i];   // a three-month gap after bar 39
    const G = { ...W, T };
    for (const k of KEYS) if (k !== 'vwap') expect(F[k](G), k).toEqual(F[k](W));
    expect(F.vwap(G, { anchor: 'Month' })._breaks).toContain(40);
  });
});

describe('parameters', () => {
  const B = walk(100);
  it('an invalid length gives all-null outputs', () => {
    for (const v of [0, -3, NaN, 'abc']) expect(F.sma(B, { length: v }).sma.every(x => x === null)).toBe(true);
    expect(F.macd(B, { signal_length: 0 }).macd.every(x => x === null)).toBe(true);
  });
  it('numeric strings and fractional lengths are accepted (lengths are floored)', () => {
    expect(F.rsi(B, { length: '14' })).toEqual(F.rsi(B, { length: 14 }));
    expect(F.sma(B, { length: 20.7 })).toEqual(F.sma(B, { length: 20 }));
    expect(F.keltner(B, { use_exponential_ma: 'false' })).toEqual(F.keltner(B, { use_exponential_ma: false }));
  });
  it('sources select the price', () => {
    const hl2 = B.H.map((h, i) => ((h as number) + (B.L[i] as number)) / 2);
    expect(F.sma(B, { length: 5, source: 'hl2' }).sma).toEqual(F.sma({ ...B, C: hl2 }, { length: 5 }).sma);
  });
  it('VWAP restarts on every anchor period and reports the restarts', () => {
    const o = F.vwap(B, { anchor: 'Month' });
    const firsts = B.T!.map((d, i) => i && d.slice(0, 7) !== B.T![i - 1].slice(0, 7) ? i : -1).filter(i => i > 0);
    expect(o._breaks).toEqual(firsts);
    expect(F.vwap(B)._breaks).toHaveLength(99);                           // Session: every daily bar
  });
});
