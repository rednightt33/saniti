// EXEC-PINE-INDICATORS (2026-11-23): the lab formulas Inside Bar Detection (Pine "Nic- Inside Bar Chain Break Alert") and
// Alpha Price Action BUY / SELL (Pine "Nic - Candle A BUY" / "Nic - Candle A SELL") against implementations written here
// line by line from the Pine (its offsets, its loops, its na rules), on a deterministic path with compressions and runs,
// plus the edges and causality. INDICATOR_BETA_TO_LIVE.md Part A step 7.
import { describe, expect, it } from 'vitest';
import { F } from '../../src/calc/indicators';
// released 2026-11-26: the formulas are in calc/indicators.ts (INDICATOR_BETA_TO_LIVE.md Part B)

type N = number | null;
function path(n: number) {
  let s = 777; const rnd = () => (s = (s * 1103515245 + 12345) % 2147483648) / 2147483648;
  const O: number[] = [], H: number[] = [], L: number[] = [], C: number[] = [];
  let c = 1000;
  for (let i = 0; i < n; i++) {
    const squeeze = i % 37 > 30;                                   // runs of narrow bars: compressions
    const o = c, move = (rnd() - 0.5) * (squeeze ? 6 : 60) + 8 * Math.sin(i / 23);
    c = Math.max(50, Math.round(o + move));
    const hi = Math.max(o, c) + Math.round(rnd() * (squeeze ? 2 : 25)), lo = Math.min(o, c) - Math.round(rnd() * (squeeze ? 2 : 25));
    O.push(o); H.push(hi); L.push(lo); C.push(c);
  }
  for (let i = 100; i < 104; i++) { H[i] = H[99]; L[i] = L[99]; C[i] = C[99]; O[i] = C[99] }   // a day without trades repeats the bar
  return { O, H, L, C, V: C.map(() => 1000), T: C.map((_, i) => String(i)) };
}

/* ---- Pine, line by line ---- */
function pineInside(B: ReturnType<typeof path>) {
  let mh: N = null, ml: N = null, on = false; const ib: number[] = [], up: number[] = [], dn: number[] = [];
  for (let t = 0; t < B.C.length; t++) {
    const isInsidePrev = t > 0 && B.H[t] <= B.H[t - 1] && B.L[t] >= B.L[t - 1];
    if (!on && isInsidePrev) { mh = B.H[t - 1]; ml = B.L[t - 1]; on = true }
    if (on && B.H[t] <= (mh as number) && B.L[t] >= (ml as number)) on = true;
    const breakUp = on && B.C[t] > (mh as number), breakDown = on && B.C[t] < (ml as number);
    ib.push(isInsidePrev ? 1 : 0); up.push(breakUp ? 1 : 0); dn.push(breakDown ? 1 : 0);
    if (breakUp || breakDown) { on = false; mh = null; ml = null }
  }
  return { ib, break_up: up, break_down: dn };
}
function pineCandleA(B: ReturnType<typeof path>, N: number, buy: boolean, close: boolean) {
  const lev: Record<string, N[]> = { level_1: [], level_a: [], level_b: [] };
  const low = (t: number, i: number) => B.L[t - i], high = (t: number, i: number) => B.H[t - i];
  for (let t = 0; t < B.C.length; t++) {
    let c1o: N = null, c1x: N = null, c1y: N = null, ao: N = null, ay: N = null, by: N = null;
    if (t >= N) {
      for (let i = 1; i <= N; i++) {
        const x = buy ? low(t, i) : high(t, i);
        if (c1o === null || (buy ? x < (c1x as number) : x > (c1x as number))) { c1o = i; c1x = x; c1y = buy ? high(t, i) : low(t, i) }
      }
      for (let i = 1; i <= N; i++) { const y = buy ? high(t, i) : low(t, i); if (i > (c1o as number) && (buy ? y > (c1y as number) : y < (c1y as number))) { ao = i; ay = y; break } }
      if (ao !== null) for (let i = 1; i <= N; i++) { const y = buy ? high(t, i) : low(t, i); if (i > ao && (buy ? y > (ay as number) : y < (ay as number))) { by = y; break } }
    }
    lev.level_1.push(c1y); lev.level_a.push(ay); lev.level_b.push(by);
  }
  const src = close ? B.C : buy ? B.H : B.L;
  const brk = (Lv: N[]) => Lv.map((l, t) => l === null ? null : t === 0 ? 0 : (buy ? src[t] > l && src[t - 1] <= l : src[t] < l && src[t - 1] >= l) ? 1 : 0);
  return { ...lev, break_1: brk(lev.level_1), break_a: brk(lev.level_a), break_b: brk(lev.level_b) } as Record<string, N[]>;
}

const B = path(1200);
describe('Inside Bar Detection (lab)', () => {
  const out = F.inside_bar(B as any, {}) as Record<string, N[]>, ref = pineInside(B);
  it('every bar equals the Pine', () => { for (const k of ['ib', 'break_up', 'break_down']) expect(out[k], k).toEqual(ref[k as keyof typeof ref]) });
  it('the path reaches every case: inside bars, both breaks, a day without trades counted as inside', () => {
    expect(ref.ib.filter(Boolean).length).toBeGreaterThan(20);
    expect(ref.break_up.filter(Boolean).length).toBeGreaterThan(3); expect(ref.break_down.filter(Boolean).length).toBeGreaterThan(3);
    expect(out.ib.slice(100, 104)).toEqual([1, 1, 1, 1]);
  });
  it('causal: a bar\'s flags do not change when later bars are cut', () => {
    for (const t of [150, 404, 777, 1199]) { const cut = F.inside_bar({ ...B, O: B.O.slice(0, t + 1), H: B.H.slice(0, t + 1), L: B.L.slice(0, t + 1), C: B.C.slice(0, t + 1), V: B.V.slice(0, t + 1), T: B.T.slice(0, t + 1) } as any, {}) as Record<string, N[]>;
      for (const k of ['ib', 'break_up', 'break_down']) expect(cut[k][t], `${k} ${t}`).toBe(out[k][t]) }
  });
});

describe('Alpha Price Action BUY / SELL (lab)', () => {
  const cases: [string, boolean, Record<string, unknown>, number, boolean][] = [
    ['price_action_buy', true, {}, 30, false], ['price_action_buy', true, { break_source: 'Close', lookback_length: 12 }, 12, true],
    ['price_action_sell', false, {}, 30, false], ['price_action_sell', false, { break_source: 'Close', lookback_length: 50 }, 50, true]];
  for (const [key, buy, p, N, close] of cases) it(`${key} ${JSON.stringify(p)} equals the Pine on every bar`, () => {
    const out = F[key](B as any, p) as Record<string, N[]>, ref = pineCandleA(B, N, buy, close);
    for (const k of Object.keys(ref)) expect(out[k], k).toEqual(ref[k]);
    expect(ref.level_b.filter(v => v !== null).length).toBeGreaterThan(50);                 // B found on many bars
    expect(ref.break_a.filter(v => v === 1).length).toBeGreaterThan(3);
    expect(out.level_1.slice(0, N).every(v => v === null)).toBe(true); expect(out.level_1[N]).not.toBeNull();
  });
  it('causal: the levels and breaks of a bar do not change when later bars are cut', () => {
    const out = F.price_action_buy(B as any, {}) as Record<string, N[]>;
    for (const t of [60, 333, 1199]) { const cut = F.price_action_buy({ ...B, O: B.O.slice(0, t + 1), H: B.H.slice(0, t + 1), L: B.L.slice(0, t + 1), C: B.C.slice(0, t + 1), V: B.V.slice(0, t + 1), T: B.T.slice(0, t + 1) } as any, {}) as Record<string, N[]>;
      for (const k of Object.keys(cut)) expect(cut[k][t], `${k} ${t}`).toBe(out[k][t]) }
  });
});
