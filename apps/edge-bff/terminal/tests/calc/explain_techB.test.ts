// EXEC-IND-CARDS IC4, extra checks for explainTechB.ts (I27-I53): the card's number is the chart's number on every
// fixture ticker, with parameters the main test does not try (MA and smoothing types, VWAP anchors and band modes, sample
// stdev, simple returns, length 1) and on synthetic bars with a gap, flat candles and zero volume; the formula line names
// every term; the steps have numbers, not NaN.
import { describe, expect, it } from 'vitest';
import { DEFAULTS, F, type Bars } from '../../src/calc/indicators';
import { TECH_EXPLAIN_B } from '../../src/calc/explainTechB';
import { termWords } from '../../src/app/indCard';
import { loadFixtures } from './fixtures.mjs';

const VARIANTS: Record<string, Record<string, any>[]> = {
  bollinger: [{ basis_ma_type:'EMA' }, { basis_ma_type:'WMA' }, { basis_ma_type:'RMA' }, { basis_ma_type:'VWMA' }, { std_dev:1 }, { length:1 }],
  bollinger_pctb: [{ basis_ma_type:'EMA', source:'ohlc4' }, { basis_ma_type:'VWMA' }],
  bollinger_width: [{ basis_ma_type:'WMA', length:7 }, { basis_ma_type:'RMA' }],
  atr: [{ smoothing_type:'SMA' }, { smoothing_type:'EMA' }, { smoothing_type:'WMA' }, { length:1 }, { smoothing_type:'SMA', length:1 }],
  natr: [{ smoothing_type:'EMA', length:5 }, { length:1 }],
  stddev: [{ stdev_method:'sample' }, { stdev_method:'sample', length:1 }, { length:1 }, { source:'hl2' }],
  hist_vol: [{ return_type:'simple' }, { annualization_periods:365, length:10 }],
  volume_ema: [{ length:1 }], volume_roc: [{ length:1 }], rvol: [{ length:1 }],
  pvo: [{ fast_length:3, slow_length:7, signal_length:4 }, { signal_length:1 }],
  vwap: [{ anchor:'Week' }, { anchor:'Month' }, { anchor:'Year', source:'close' }, { anchor:'Quarter', bands_mode:'Percentage', band_1_multiplier:2.5 }, { bands_mode:'None' }],
  chaikin_osc: [{ fast_length:1, slow_length:1 }, { fast_length:5, slow_length:20 }],
  mfi: [{ length:1 }], force_index: [{ length:1 }], eom: [{ length:1, volume_scale:1 }],
  nvi: [{ initial_value:100 }], kvo: [{ fast_length:5, slow_length:9, signal_length:3 }], market_fi: [{ volume_scale:1e6 }],
};

const close = (a: number, b: number) => Math.abs(a - b) <= 1e-9 * Math.max(1, Math.abs(b));
function check(key: string, B: Bars, p: Record<string, any>, ts: number[], where: string) {
  const out = F[key](B, p), explain = TECH_EXPLAIN_B[key];
  for (const k of Object.keys(out).filter(x => !x.startsWith('_')))
    for (const t of ts) {
      const chart = (out as any)[k][t] ?? null, e = explain(B, p, t, k), w = `${where} ${key} ${JSON.stringify(p)} ${k} t=${t}`;
      if (chart === null) { expect(e?.value ?? null, w).toBeNull(); continue }
      expect(e, w).not.toBeNull();
      expect(e!.output, w).toBe(k);
      expect(close(e!.value!, chart), `${w}: value ${e!.value} chart ${chart}`).toBe(true);
      const v = e!.combine(Object.fromEntries(e!.terms.map(x => [x.key, x.value])));
      expect(v !== null && close(v, chart), `${w}: combine ${v} chart ${chart}`).toBe(true);
      const named = new Set(e!.expr.match(termWords(e!.terms)) || []);
      expect(e!.terms.filter(x => !named.has(x.key)).map(x => x.key), `${w}: terms in expr "${e!.expr}"`).toEqual([]);
      const text = JSON.stringify(e!.steps) + e!.terms.map(x => x.label).join(' ');
      expect(text, w).not.toMatch(/NaN|undefined|Infinity|Screener/);
      expect(e!.terms.every(x => Number.isFinite(x.value)), `${w}: finite terms`).toBe(true);
    }
}

describe('explainTechB on every fixture ticker', () => {
  const data = loadFixtures();
  for (const key of Object.keys(TECH_EXPLAIN_B)) it(key, () => {
    for (const d of data) {
      const B: Bars = { T:d.T, O:d.O, H:d.H, L:d.L, C:d.C, V:d.V }, N = d.C.length;
      const ts = [...Array.from({ length:70 }, (_, i) => i), ...Array.from({ length:40 }, (_, i) => Math.floor(70 + (N - 71) * i / 39))];
      for (const v of [{}, ...(VARIANTS[key] || [])]) check(key, B, { ...(DEFAULTS[key] || {}), ...v }, ts, d.ticker);
    }
  }, 120_000);
});

/* 90 synthetic bars: a gap of missing bars, a run of flat candles (H = L, unchanged close) and zero-volume candles */
function synthetic(): Bars {
  const N = 90, T: string[] = [], O: (number | null)[] = [], H: (number | null)[] = [], L: (number | null)[] = [], C: (number | null)[] = [], V: (number | null)[] = [];
  let px = 1000, seed = 11;
  const r = () => (seed = (seed * 1664525 + 1013904223) >>> 0) / 2 ** 32;
  for (let i = 0; i < N; i++) {
    T.push(new Date(Date.UTC(2026, 0, 1 + i)).toISOString().slice(0, 10));
    if (i === 40 || i === 41) { O.push(null); H.push(null); L.push(null); C.push(null); V.push(null); continue }
    const flat = i >= 20 && i < 28;
    const o = px, c = flat ? px : Math.round(px * (1 + (r() - 0.5) * 0.06)), h = flat ? px : Math.max(o, c) + Math.round(r() * 15), l = flat ? px : Math.min(o, c) - Math.round(r() * 15);
    O.push(o); H.push(h); L.push(l); C.push(c); V.push(i % 17 === 5 || (i >= 60 && i < 63) ? 0 : Math.round(1e5 + r() * 9e5)); px = c;
  }
  return { T, O, H, L, C, V };
}
describe('explainTechB on synthetic edge cases', () => {
  const B = synthetic(), ts = Array.from({ length:90 }, (_, i) => i);
  for (const key of Object.keys(TECH_EXPLAIN_B)) it(key, () => {
    for (const v of [{}, ...('length' in (DEFAULTS[key] || {}) ? [{ length:3 }] : []), ...(VARIANTS[key] || [])]) check(key, B, { ...(DEFAULTS[key] || {}), ...v }, ts, 'synthetic');
  });
});
