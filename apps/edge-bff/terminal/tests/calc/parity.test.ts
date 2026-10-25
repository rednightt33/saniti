/* Parity of src/calc/indicators.ts with Feature 04 (stored values), TA-Lib 0.6.8 and the reference engine
   (03-terminal-right-panel.html with the spec's conventions), on the full history of every fixture ticker.
   Rule: same first valid bar, same null pattern, relative difference |a-b|/max(|a|,|b|) <= 1e-9 on every bar.
   Feature 04 and TA-Lib are compared strictly. The reference engine sums in another order than TA-Lib, so for it a
   difference within 1e-12 of the series' largest value also counts as equal (rounding residue next to zero), and the
   Stochastic RSI bars whose RSI window is flat (range < 1e-9, where rounding noise decides %K in every engine) are
   counted, not compared (PARITY.md). */
import { afterAll, describe, expect, it } from 'vitest';
import { F, type Series } from '../../src/calc/indicators';
import { loadFixtures, writeReport } from './fixtures.mjs';

export const TOL = 1e-9;
type Enc = { s: number; v: (number | null)[] };
type Case = { name: string; key: string; params: Record<string, any>; outs: Record<string, Enc>; breaks?: number[]; note?: string };

/* Feature 04 column -> terminal key, params, output */
const F04: Record<string, [string, Record<string, any>, string]> = {
  sma_20: ['sma', { length: 20, source: 'close' }, 'sma'], sma_50: ['sma', { length: 50, source: 'close' }, 'sma'],
  ema_12: ['ema', { length: 12, source: 'close' }, 'ema'], ema_26: ['ema', { length: 26, source: 'close' }, 'ema'],
  ema_50: ['ema', { length: 50, source: 'close' }, 'ema'], ema_200: ['ema', { length: 200, source: 'close' }, 'ema'],
  rsi_14: ['rsi', { length: 14, source: 'close' }, 'rsi'],
  macd: ['macd', { fast_length: 12, slow_length: 26, signal_length: 9, source: 'close' }, 'macd'],
  macd_signal: ['macd', { fast_length: 12, slow_length: 26, signal_length: 9, source: 'close' }, 'signal'],
  macd_histogram: ['macd', { fast_length: 12, slow_length: 26, signal_length: 9, source: 'close' }, 'histogram'],
  atr_14: ['atr', { length: 14, smoothing_type: 'RMA' }, 'atr'],
  bb_upper_20: ['bollinger', { length: 20, source: 'close', std_dev: 2, basis_ma_type: 'SMA' }, 'upper'],
  bb_middle_20: ['bollinger', { length: 20, source: 'close', std_dev: 2, basis_ma_type: 'SMA' }, 'basis'],
  bb_lower_20: ['bollinger', { length: 20, source: 'close', std_dev: 2, basis_ma_type: 'SMA' }, 'lower'],
  adx_14: ['adx', { di_length: 14, adx_smoothing: 14 }, 'adx'],
};

export interface Diff { firstExp: number; firstGot: number; nullMismatch: number; compared: number; skipped: number; maxRel: number; worstBar: number }
/** floor: a difference within floor x max|expected| counts as 0; skip(i): bar not compared (counted). */
export function compare(exp: Enc, got: Series, floor = 0, skip?: (i: number) => boolean): Diff {
  const N = got.length, full: (number | null)[] = new Array(exp.s).fill(null).concat(exp.v);
  let S = 0; for (const v of full) if (v !== null) S = Math.max(S, Math.abs(v));
  let nullMismatch = 0, compared = 0, skipped = 0, maxRel = 0, worstBar = -1;
  for (let i = 0; i < N; i++) {
    const a = got[i], b = full[i] ?? null;
    if (a === null || b === null) { if (a !== b) nullMismatch++; continue }
    if (skip && skip(i)) { skipped++; continue }
    compared++;
    const d = Math.abs(a - b), r = d === 0 || d <= floor * S ? 0 : d / Math.max(Math.abs(a), Math.abs(b));
    if (r > maxRel) { maxRel = r; worstBar = i }
  }
  const firstGot = got.findIndex(v => v !== null);
  return { firstExp: exp.s >= N ? -1 : exp.s, firstGot, nullMismatch, compared, skipped, maxRel, worstBar };
}

/** Bars of a Stochastic RSI output that read a flat RSI window (range < 1e-9). */
function flatRsiBars(B, p: Record<string, any>, out: string): (i: number) => boolean {
  const rsi = F.rsi(B, { length: p.rsi_length, source: p.source }).rsi, m = p.stoch_length, N = rsi.length, flat: boolean[] = [];
  for (let t = 0; t < N; t++) {
    let hi = -Infinity, lo = Infinity, ok = t >= m - 1;
    for (let j = t - m + 1; ok && j <= t; j++) { const v = rsi[j]; if (v === null) ok = false; else { hi = Math.max(hi, v); lo = Math.min(lo, v) } }
    flat.push(ok && hi - lo < 1e-9);
  }
  const span = p.smooth_k + (out === 'd' ? p.smooth_d - 1 : 0);
  return i => { for (let t = Math.max(0, i - span + 1); t <= i; t++) if (flat[t]) return true; return false };
}

const report: any[] = [];
const fixtures: any[] = loadFixtures();

describe.each(fixtures.map((d): [string, any] => [d.ticker, d]))('%s', (ticker: string, d: any) => {
  const B = { T: d.T, O: d.O, H: d.H, L: d.L, C: d.C, V: d.V };
  const groups: [string, Case[]][] = [
    ['FEATURE_04', Object.entries(F04).map(([col, [key, params, out]]) => ({ name: col, key, params, outs: { [out]: d.f04[col] } }))],
    ['TA-Lib 0.6.8', d.talib ?? []],
    ['reference HTML', d.html ?? []],
  ];
  for (const [oracle, cases] of groups) {
    it.each(cases.map((c): [string, Case] => [c.name, c]))(`${oracle}: %s`, (_name: string, c: Case) => {
      const r = F[c.key](B, c.params);
      const html = oracle === 'reference HTML';
      for (const [out, exp] of Object.entries(c.outs)) {
        const x = compare(exp, r[out], html ? 1e-12 : 0, html && c.key === 'stoch_rsi' ? flatRsiBars(B, c.params, out) : undefined);
        report.push({ ticker, oracle, case: c.name, key: c.key, out, ...x });
        const where = `${ticker} ${oracle} ${c.name}.${out}`;
        expect(x.firstGot, `${where}: first valid bar`).toBe(x.firstExp);
        expect(x.nullMismatch, `${where}: bars null on one side only`).toBe(0);
        expect(x.maxRel, `${where}: max relative difference at bar ${x.worstBar} (${d.T[x.worstBar]})`).toBeLessThanOrEqual(TOL);
      }
      if (c.breaks) expect(r._breaks, `${ticker} ${c.name}: _breaks`).toEqual(c.breaks);
    });
  }
});

afterAll(() => writeReport(report));
