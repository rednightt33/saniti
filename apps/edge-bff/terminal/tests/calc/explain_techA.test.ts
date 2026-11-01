// EXEC-IND-CARDS IC4: extra checks of the I02-I26 explainers (calc/explainTechA.ts) beyond tests/calc/explain.test.ts:
// every fixture ticker (flat candles, decimal index prices), candles with a missing input (the chart restarts after
// them), parameters other than length and source, and a formula line that names every term. The card's number must be
// the chart's number and the last step (combine) must give it back from the terms.
import { describe, expect, it } from 'vitest';
import { F, DEFAULTS, type Bars } from '../../src/calc/indicators';
import type { Explanation } from '../../src/calc/explain';
import { TECH_EXPLAIN_A } from '../../src/calc/explainTechA';
import { loadFixtures } from './fixtures.mjs';

const STRIDE = Number((globalThis as any).process?.env?.EXPLAIN_STRIDE) || 97;   // EXPLAIN_STRIDE=1 checks every candle
const VARIANTS: Record<string, Record<string, any>[]> = {
  ema:[{ length:1 }, { length:3, source:'ohlc4' }],
  wma:[{ length:1 }, { length:7, source:'hl2' }],
  hma:[{ length:1 }, { length:2 }, { length:16 }, { length:50, source:'hlc3' }],
  kama:[{ length:1 }, { fast_length:5, slow_length:20 }, { length:20, source:'hl2' }],
  macd:[{ fast_length:5, slow_length:13, signal_length:1 }, { source:'ohlc4' }, { fast_length:26, slow_length:12 }],
  adx:[{ di_length:1, adx_smoothing:1 }, { di_length:5, adx_smoothing:20 }],
  aroon:[{ length:1 }, { length:25 }],
  supertrend:[{ atr_length:1, factor:0 }, { atr_length:5, factor:1.5 }],
  donchian:[{ length:1 }, { length:55 }],
  keltner:[{ use_exponential_ma:false }, { bands_style:'TR' }, { bands_style:'HL_RANGE', length:10 }, { use_exponential_ma:'false', bands_style:'TR', source:'open' }, { atr_length:1 }],
  psar:[{ start:0.01, increment:0.03, maximum:0.1 }, { start:0.3, increment:0.3, maximum:0.2 }],
  rsi:[{ length:1 }, { length:2, source:'hl2' }],
  stoch_rsi:[{ rsi_length:5, stoch_length:3, smooth_k:1, smooth_d:7 }, { smooth_k:8 }],
  stochastic:[{ k_length:1, smooth_k:1, d_length:1 }, { k_length:5, smooth_k:6, d_length:2 }],
  williams_r:[{ length:1 }, { source:'hlc3' }],
  roc:[{ length:1 }], momentum:[{ length:1 }],
  cci:[{ length:1 }, { length:7, constant:0.02 }],
  cmo:[{ length:1 }, { length:3 }],
  tsi:[{ long_length:5, short_length:3, signal_length:1 }, { source:'ohlc4' }],
  trix:[{ length:1 }, { length:5 }],
  ultimate_osc:[{ fast_length:3, middle_length:5, slow_length:9, weight_fast:1, weight_middle:0, weight_slow:2 }],
  awesome_osc:[{ fast_length:1, slow_length:3 }, { fast_length:34, slow_length:5 }],
  ppo:[{ fast_length:5, slow_length:13, signal_length:3 }],
};
/** the term keys as whole words of the formula line (as the card's termWords) */
const words = (keys: string[]) => new RegExp(`(?<![\\p{L}\\p{N}_])(${[...keys].sort((a, b) => b.length - a.length).map(k => k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})(?![\\p{L}\\p{N}_])`, 'gu');

function check(key: string, B: Bars, p: Record<string, any>, ts: number[], where: string) {
  const out = F[key](B, p), explain = TECH_EXPLAIN_A[key];
  for (const k of Object.keys(out).filter(x => !x.startsWith('_')))
    for (const t of ts) {
      const e: Explanation | null = explain(B, p, t, k), chart = out[k][t] ?? null, at = `${where} ${key} ${JSON.stringify(p)} ${k} t=${t}`;
      if (chart === null) { expect(e?.value ?? null, at).toBeNull(); continue }
      expect(e, at).not.toBeNull();
      expect(e!.output, at).toBe(k);
      expect(e!.value!, at).toBeCloseTo(chart, 8);
      expect(e!.combine(Object.fromEntries(e!.terms.map(x => [x.key, x.value])))!, `${at} combine`).toBeCloseTo(chart, 8);
      if (e!.terms.length) expect(new Set(e!.expr.match(words(e!.terms.map(x => x.key))) || []), `${at} expr names its terms`).toEqual(new Set(e!.terms.map(x => x.key)));
      expect(e!.terms.every(x => Number.isFinite(x.value)), `${at} finite terms`).toBe(true);
      const text = JSON.stringify(e!.steps);
      expect(e!.steps.length && !/NaN|undefined|Infinity|null|Screener/.test(text), `${at} steps ${text.slice(0, 300)}`).toBeTruthy();
    }
}
const sample = (N: number) => Array.from({ length:N }, (_, t) => t).filter(t => t < 70 || t % STRIDE === 0 || t >= N - 3);
const SLOW = 120_000;                                                // ms per indicator (every ticker, every output)

describe('I02-I26 explainers on every fixture ticker', () => {
  const fx = loadFixtures();
  for (const key of Object.keys(TECH_EXPLAIN_A).filter(k => k !== 'sma')) it(key, () => {
    for (const d of fx) {
      const B: Bars = { T:d.T, O:d.O, H:d.H, L:d.L, C:d.C, V:d.V };
      check(key, B, { ...DEFAULTS[key] }, sample(d.C.length), d.ticker);
      if (['BBCA', 'CLAY', 'IHSG'].includes(d.ticker)) for (const v of VARIANTS[key] || []) check(key, B, { ...DEFAULTS[key], ...v }, sample(d.C.length), d.ticker);
    }
  }, SLOW);
});

describe('I02-I26 explainers restart after a candle with a missing input', () => {
  const d = loadFixtures().find((x: any) => x.ticker === 'BBCA');
  const gap = (a: any[], at: number[]) => a.map((v, i) => (at.includes(i) ? null : v));
  const B: Bars = { T:d.T, O:gap(d.O, [905]), H:gap(d.H, [700, 1201]), L:gap(d.L, [1200, 1201, 1202]), C:gap(d.C, [300, 1500]), V:d.V };
  const ts = [300, 700, 905, 1200, 1500].flatMap(g => Array.from({ length:64 }, (_, k) => g - 3 + k));
  for (const key of Object.keys(TECH_EXPLAIN_A).filter(k => k !== 'sma')) it(key, () => {
    check(key, B, { ...DEFAULTS[key] }, ts, 'gaps');
    for (const v of (VARIANTS[key] || []).slice(0, 2)) check(key, B, { ...DEFAULTS[key], ...v }, ts, 'gaps');
  }, SLOW);
});
