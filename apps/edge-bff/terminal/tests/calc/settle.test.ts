// EXEC-PINE-INDICATORS UD33 option B (user 2026-11-24: "UD33: Alpha KAMA --> ok pakai opsi B", then "Untuk 2-5 bisa go"):
// the Terminal draws Alpha KAMA only from the bar where the start of the data no longer matters (calc/settle.ts). The
// point is measured: the output on every bar against the output on the same bars without their first `cut`, agreeing
// within `tolerance` x the close on every later bar. Checked here on a recursion whose point is known in closed form, on
// the "for good" rule, on a short (monthly-like) history that never settles, on a run restarted by a bar without data,
// and on Alpha KAMA itself (BBCA daily since 2018 from the parity fixtures, its months): the outputs the rule names are
// empty before the point, every value from the point on is the formula's own, and the other outputs are untouched.
import { describe, expect, it } from 'vitest';
import { F, type Bars, type IndicatorFn } from '../../src/calc/indicators';
import { SETTLE, cutOf, settleRuns, settled, unsettledAt, type Settle } from '../../src/calc/settle';
// released 2026-11-26: the formulas are in calc/indicators.ts (INDICATOR_BETA_TO_LIVE.md Part B)
import { loadFixtures } from './fixtures.mjs';

type N = number | null;
/** y = y[1] + a (close - y[1]) from 0 (a recursion that remembers its start, as KAMA's), z = 2 x close (none); a bar
    without a close restarts it, as def() restarts a formula after a bar without its inputs */
const recursion = (a: number): IndicatorFn => (B: Bars) => {
  const y: N[] = [], z: N[] = []; let prev: N = null;
  for (let t = 0; t < B.C.length; t++) {
    const c = B.C[t];
    if (typeof c !== 'number') { y.push(null); z.push(null); prev = null; continue }
    prev = (prev ?? 0) + a * (c - (prev ?? 0)); y.push(prev); z.push(2 * c);
  }
  return { y, z };
};
const flat = (closes: N[]): Bars => ({ O: closes, H: closes, L: closes, C: closes, V: closes.map(() => 1) });
const rule = (cut: number, tolerance = 0.005): Settle => ({ measure: 'y', hides: ['y'], tolerance, cut: { default: cut, M: 3 } });

/** the definition itself, by brute force: the first bar s >= cut from which every later bar agrees (n: never) */
function bruteForce(fn: IndicatorFn, B: Bars, s: Settle, cut: number, measure = s.measure): number {
  const n = B.C.length, full = fn(B, {})[measure];
  const part = fn({ O: B.O.slice(cut), H: B.H.slice(cut), L: B.L.slice(cut), C: B.C.slice(cut), V: B.V.slice(cut) }, {})[measure];
  const agrees = (t: number) => { const a = full[t], b = part[t - cut], c = B.C[t] as number; return a !== null && b !== null && Math.abs(a - b) <= s.tolerance * Math.abs(c) };
  for (let at = cut; at < n; at++) { let all = true; for (let t = at; t < n; t++) if (!agrees(t)) { all = false; break } if (all) return at }
  return n;
}

describe('the settle point (UD33 option B)', () => {
  it('is where the two starts agree for good: a recursion from 0 on a flat close settles at bar 56', () => {
    // close 100, a = 0.1, cut 10: the gap is 100 x (1 - 0.9^10) x 0.9^(t - 9) (both runs see the same closes, so it only
    // decays); it is at most 0.5 (0.5 % of the close) from t - 9 >= 47, so from bar 56 on
    const fn = recursion(0.1), B = flat(new Array(200).fill(100)), s = rule(10);
    const gap = (t: number) => 100 * (1 - 0.9 ** 10) * 0.9 ** (t - 9);
    expect(gap(55)).toBeGreaterThan(0.5); expect(gap(56)).toBeLessThanOrEqual(0.5);
    expect(settleRuns(fn, B, {}, s, 'C', 10)).toEqual([{ from: 0, at: 56, to: 200 }]);
    expect(bruteForce(fn, B, s, 10)).toBe(56);
  });

  it('"for good": a later bar where they part again moves the point past it', () => {
    // the close falls to 1 at bar 60: the same gap is now large against the close, so the bars from 56 agree only for a while
    const closes = Array.from({ length: 300 }, (_, t) => t < 60 ? 100 : 1), fn = recursion(0.1), B = flat(closes), s = rule(10);
    const [run] = settleRuns(fn, B, {}, s, 'C', 10);
    expect(run.at).toBeGreaterThan(60);
    expect(run.at).toBe(bruteForce(fn, B, s, 10));
  });

  it('a history too short to settle (a monthly-like 40 bars of a slow recursion) is never drawn', () => {
    const fn = recursion(0.02), B = flat(new Array(40).fill(100)), s = rule(12);
    expect(settleRuns(fn, B, {}, s, 'C', 12)).toEqual([{ from: 0, at: 40, to: 40 }]);
    expect(bruteForce(fn, B, s, 12)).toBe(40);
    // and a history no longer than the cut cannot be measured: never drawn either
    expect(settleRuns(fn, flat(new Array(12).fill(100)), {}, s, 'C', 12)).toEqual([{ from: 0, at: 12, to: 12 }]);
    const { out } = settled(fn, B, {}, s, 'C', 12);
    expect(out.y.every(v => v === null)).toBe(true);
    expect(out.z.every(v => v === 200)).toBe(true);                  // not named by the rule: untouched
  });

  it('a run the formula restarts after a bar without data is measured from its own start', () => {
    const closes: N[] = new Array(250).fill(100); closes[120] = null;
    const fn = recursion(0.1), B = flat(closes), s = rule(10);
    expect(settleRuns(fn, B, {}, s, 'C', 10)).toEqual([{ from: 0, at: 56, to: 120 }, { from: 121, at: 121 + 56, to: 250 }]);
    const { out, runs } = settled(fn, B, {}, s, 'C', 10);
    expect(out.y.slice(0, 56).every(v => v === null)).toBe(true);
    expect(out.y.slice(121, 177).every(v => v === null)).toBe(true);
    expect(out.y[56]).not.toBeNull(); expect(out.y[177]).not.toBeNull();
    expect(unsettledAt(runs, 55)).toEqual(runs[0]); expect(unsettledAt(runs, 56)).toBeNull();
    expect(unsettledAt(runs, 120)).toBeNull();                       // the bar without data is in no run
    expect(unsettledAt(runs, 130)).toEqual(runs[1]); expect(unsettledAt(runs, 177)).toBeNull();
  });

  it('the cut follows the chart\'s timeframe (12 on the monthly chart, else the default)', () => {
    const s = rule(50);
    expect(cutOf(s, 'D')).toBe(50); expect(cutOf(s, 'W')).toBe(50); expect(cutOf(s, '15m')).toBe(50); expect(cutOf(s, 'M')).toBe(3);
    expect([cutOf(SETTLE.alpha_kama, 'D'), cutOf(SETTLE.alpha_kama, 'W'), cutOf(SETTLE.alpha_kama, '1h'), cutOf(SETTLE.alpha_kama, 'M')]).toEqual([50, 50, 50, 12]);
  });
});

describe('Alpha KAMA is drawn only once settled (lab rule)', () => {
  const k = SETTLE.alpha_kama;
  const bbca = loadFixtures().find((f: any) => f.ticker === 'BBCA');
  const daily: Bars = { O: bbca.O, H: bbca.H, L: bbca.L, C: bbca.C, V: bbca.V, T: bbca.T };
  /** the daily bars as calendar months: first open, highest high, lowest low, last close, summed volume */
  const months = (() => {
    const M = new Map<string, number[]>(); bbca.T.forEach((d: string, i: number) => { const key = d.slice(0, 7); M.set(key, [...(M.get(key) || []), i]) });
    const g = [...M.values()];
    return { O: g.map(x => bbca.O[x[0]]), H: g.map(x => Math.max(...x.map(i => bbca.H[i]))), L: g.map(x => Math.min(...x.map(i => bbca.L[i]))),
      C: g.map(x => bbca.C[x[x.length - 1]]), V: g.map(x => x.reduce((s, i) => s + bbca.V[i], 0)), T: g.map(x => bbca.T[x[x.length - 1]]) } as Bars;
  })();

  it('the rule hides KAMA and what is read from it (colours, ENTER LONG / SHORT), not EMA X, at 0.5 % of the close', () => {
    expect(k).toEqual({ measure: 'kama', hides: ['kama', 'color_index', 'color_state', 'long', 'short'], tolerance: 0.005, cut: { default: 50, M: 12 } });
  });

  it('BBCA daily since 2018: drawn from the measured bar; before it nothing, from it the formula\'s own values', () => {
    const cut = cutOf(k, 'D'), raw = F.alpha_kama(daily, {}), { out, runs } = settled(F.alpha_kama, daily, {}, k, 'HLC', cut);
    expect(runs).toHaveLength(1);
    const at = runs[0].at;
    expect(at).toBe(bruteForce(F.alpha_kama, daily, k, cut));
    expect(at).toBeGreaterThan(cut + 150); expect(at).toBeLessThan(cut + 300);   // UD33: 188-220 bars after the cut on the real data
    expect(raw.kama.slice(cut, at).some(v => v !== null)).toBe(true);           // the formula has values there: they are hidden
    for (const o of k.hides) {
      expect(out[o].slice(0, at).every(v => v === null), o).toBe(true);
      expect(out[o].slice(at), o).toEqual(raw[o].slice(at));                    // the numbers themselves are unchanged
    }
    expect(out.ema_x).toEqual(raw.ema_x);
    expect(unsettledAt(runs, at - 1)).toEqual(runs[0]); expect(unsettledAt(runs, at)).toBeNull();
  });

  it('BBCA monthly since 2018 (about 106 months): never settles, nothing of KAMA is drawn, EMA X is', () => {
    const { out, runs } = settled(F.alpha_kama, months, {}, k, 'HLC', cutOf(k, 'M'));
    expect(months.C.length).toBeGreaterThan(100); expect(months.C.length).toBeLessThan(120);
    expect(runs).toEqual([{ from: 0, at: months.C.length, to: months.C.length }]);
    for (const o of k.hides) expect(out[o].every(v => v === null), o).toBe(true);
    expect(out.ema_x.some(v => v !== null)).toBe(true);
    expect(unsettledAt(runs, months.C.length - 1)).toEqual(runs[0]);           // the legend's last bar: the note, not a value
  });

  it('the point follows the parameters (measured again, not a fixed count)', () => {
    const cut = cutOf(k, 'D'), at = (p: Record<string, unknown>) => settleRuns(F.alpha_kama, daily, p, k, 'HLC', cut)[0].at;
    const short = at({ kama_length: 21 });
    expect(short).toBe(bruteForce((B, p) => F.alpha_kama(B, { kama_length: 21, ...p }), daily, k, cut));
    expect(short).not.toBe(at({}));
  });
});
