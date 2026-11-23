// EXEC-PINE-INDICATORS (the user's Pine "Nic - Tail Move Indicator V2 (RAW Distance)", named Alpha Volatile, 2026-11-23):
// the lab formula (src/lab/index.ts) against a separate implementation written here from the Pine's own semantics
// (ta.ema seeded with the SMA of its first `length` values, ta.sma, ta.stdev biased, the sorted-window decile), plus the
// first valid bars, the flags and the edges (flat prices, short history, SMA, decile 10). INDICATOR_BETA_TO_LIVE.md
// Part A step 7: the page tests run the public build and never see a lab formula.
import { describe, expect, it } from 'vitest';
import { F } from '../../src/calc/indicators';
import '../../src/lab/index';

type N = number | null;
/** a deterministic price path: trend, two waves, noise from a fixed LCG, three jumps (so the band is left both ways) */
function closes(n: number): number[] {
  let s = 12345; const rnd = () => (s = (s * 1103515245 + 12345) % 2147483648) / 2147483648;
  return Array.from({ length: n }, (_, i) => {
    const jump = i > 300 && i < 310 ? 900 : i > 520 && i < 526 ? -1100 : i > 700 && i < 703 ? 1500 : 0;
    return Math.round(5000 + 2 * i + 400 * Math.sin(i / 17) + 150 * Math.sin(i / 3.3) + 120 * (rnd() - 0.5) + jump);
  });
}
const bars = (C: number[]) => ({ O: C, H: C.map(c => c + 10), L: C.map(c => c - 10), C, V: C.map(() => 1000), T: C.map((_, i) => `2020-01-${i}`) });

/* ---- the separate implementation (Pine semantics, plain loops) ---- */
function pineEma(x: number[], n: number): N[] {
  const o: N[] = x.map(() => null); if (x.length < n) return o;
  let v = 0; for (let i = 0; i < n; i++) v += x[i]; v /= n; o[n - 1] = v;
  const a = 2 / (n + 1); for (let i = n; i < x.length; i++) { v = a * x[i] + (1 - a) * v; o[i] = v }
  return o;
}
function pineSma(x: N[], n: number): N[] {
  return x.map((_, i) => { if (i < n - 1) return null; let s = 0; for (let j = i - n + 1; j <= i; j++) { const v = x[j]; if (v === null) return null; s += v } return s / n });
}
function pineStdev(x: N[], n: number): N[] {
  const m = pineSma(x, n);
  return x.map((_, i) => { const mi = m[i]; if (mi === null) return null; let s = 0; for (let j = i - n + 1; j <= i; j++) s += ((x[j] as number) - mi) ** 2; return Math.sqrt(s / n) });
}
function reference(C: number[], p: { ma_type: string; ma_length: number; lookback_length: number; decile: number; z_multiplier: number }) {
  const ma = p.ma_type === 'SMA' ? pineSma(C, p.ma_length) : pineEma(C, p.ma_length);
  const d: N[] = ma.map((m, i) => m === null ? null : C[i] - m);
  const mean = pineSma(d, p.lookback_length), sd = pineStdev(d, p.lookback_length);
  const up = mean.map((m, i) => m === null ? null : m + p.z_multiplier * (sd[i] as number));
  const lo = mean.map((m, i) => m === null ? null : m - p.z_multiplier * (sd[i] as number));
  const dec = d.map((_, i) => {
    if (i < p.lookback_length - 1) return null;
    const w = d.slice(i - p.lookback_length + 1, i + 1); if (w.some(v => v === null)) return null;
    const sorted = (w as number[]).slice().sort((a, b) => a - b);
    return sorted[Math.max(Math.floor((p.decile / 10) * sorted.length) - 1, 0)];
  });
  return { d, up, lo, dec };
}
const close = (a: N, b: N) => a === null || b === null ? a === b : Math.abs(a - b) <= 1e-9 * Math.max(1, Math.abs(b));
const DEF = { ma_type: 'EMA', ma_length: 26, lookback_length: 100, decile: 9, z_multiplier: 2 };

describe('Alpha Volatile (lab)', () => {
  const C = closes(900), out = F.alpha_volatile(bars(C) as any, {}) as Record<string, N[]>, ref = reference(C, DEF);

  it('defaults are the user\'s screenshot: EMA 26, lookback 100, decile 9, Z 2', () => {
    expect(F.alpha_volatile).toBeTypeOf('function');
    const again = F.alpha_volatile(bars(C) as any, DEF) as Record<string, N[]>;
    expect(again.distance).toEqual(out.distance);
  });
  it('distance, bands and decile equal the Pine semantics on every bar', () => {
    for (let i = 0; i < C.length; i++) {
      expect(close(out.distance[i], ref.d[i]), `distance ${i}`).toBe(true);
      expect(close(out.upper_z[i], ref.up[i]), `upper ${i}`).toBe(true);
      expect(close(out.lower_z[i], ref.lo[i]), `lower ${i}`).toBe(true);
      expect(close(out.decile[i], ref.dec[i]), `decile ${i}`).toBe(true);
    }
  });
  it('first valid bars: distance at 25 (EMA 26), band and decile at 124 (25 + 99)', () => {
    expect(out.distance[24]).toBeNull(); expect(out.distance[25]).not.toBeNull();
    expect(out.upper_z[123]).toBeNull(); expect(out.upper_z[124]).not.toBeNull();
    expect(out.decile[123]).toBeNull(); expect(out.decile[124]).not.toBeNull();
    expect(out.outside_any[123]).toBeNull(); expect(out.outside_any[124]).not.toBeNull();
  });
  it('flags follow the band: outside strictly beyond it, back inside on the session after one outside', () => {
    let ups = 0, downs = 0, backs = 0;
    for (let i = 125; i < C.length; i++) {
      const d = ref.d[i] as number, u = ref.up[i] as number, l = ref.lo[i] as number;
      const side = d > u ? 1 : d < l ? -1 : 0, prev = (ref.d[i - 1] as number) > (ref.up[i - 1] as number) ? 1 : (ref.d[i - 1] as number) < (ref.lo[i - 1] as number) ? -1 : 0;
      expect(out.outside_up[i]).toBe(side === 1 ? 1 : 0); expect(out.outside_down[i]).toBe(side === -1 ? 1 : 0);
      expect(out.outside_any[i]).toBe(side !== 0 ? 1 : 0); expect(out.direction[i]).toBe(side === 0 ? 1 : -1);
      expect(out.back_in_up[i]).toBe(side === 0 && prev === 1 ? 1 : 0); expect(out.back_in_down[i]).toBe(side === 0 && prev === -1 ? 1 : 0);
      expect(out.back_in_any[i]).toBe(side === 0 && prev !== 0 ? 1 : 0);
      ups += out.outside_up[i] as number; downs += out.outside_down[i] as number; backs += out.back_in_any[i] as number;
    }
    expect(ups).toBeGreaterThan(0); expect(downs).toBeGreaterThan(0); expect(backs).toBeGreaterThan(0);   // the fixture reaches every case
  });
  it('SMA and decile 10 (the window\'s largest value) follow the same semantics', () => {
    const p = { ...DEF, ma_type: 'SMA', ma_length: 20, decile: 10, lookback_length: 50, z_multiplier: 1.5 };
    const o = F.alpha_volatile(bars(C) as any, p) as Record<string, N[]>, r = reference(C, p);
    for (let i = 0; i < C.length; i++) { expect(close(o.distance[i], r.d[i])).toBe(true); expect(close(o.decile[i], r.dec[i])).toBe(true); expect(close(o.upper_z[i], r.up[i])).toBe(true) }
  });
  it('flat prices: distance 0, band 0 wide, never outside; a history shorter than the windows gives nulls', () => {
    const flat = Array(300).fill(1000), o = F.alpha_volatile(bars(flat) as any, {}) as Record<string, N[]>;
    expect(o.distance[200]).toBe(0); expect(o.upper_z[200]).toBe(0); expect(o.outside_any[200]).toBe(0);
    const short = F.alpha_volatile(bars(closes(60)) as any, {}) as Record<string, N[]>;
    expect(short.upper_z.every(v => v === null)).toBe(true); expect(short.distance[59]).not.toBeNull();
  });
  it('causal: every output at bar t is the same when the bars after t are cut', () => {
    for (const t of [130, 305, 523, 701, 899]) {
      const cut = F.alpha_volatile(bars(C.slice(0, t + 1)) as any, {}) as Record<string, N[]>;
      for (const k of Object.keys(cut)) if (Array.isArray(out[k])) expect(close(cut[k][t], out[k][t]), `${k} at ${t}`).toBe(true);
    }
  });
});
