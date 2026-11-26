// EXEC-PINE-INDICATORS (2026-11-23): the lab formula Alpha Divergence (the user's Pine v6 "Nic - Divergence Detector -
// Swing Comparison") against a second implementation written here with the Pine's own variable names, bar by bar, in
// both swing modes; the outputs dated on the confirmation (the Screener's and the Backtest's, the user's "1-4 OK"); the
// Terminal's drawing (labels on the swing candles, divergence lines, the active BUY A level, the background ranges),
// which is never an output; and causality of every output.
import { describe, expect, it } from 'vitest';
import { DRAWINGS, F } from '../../src/calc/indicators';
// released 2026-11-26: the formulas are in calc/indicators.ts (INDICATOR_BETA_TO_LIVE.md Part B)

type N = number | null;
function bars(n: number, seed = 2718) {
  let s = seed; const rnd = () => (s = (s * 1103515245 + 12345) % 2147483648) / 2147483648;
  const O: number[] = [], H: number[] = [], L: number[] = [], C: number[] = [];
  let c = 4000;
  for (let i = 0; i < n; i++) {
    const o = c; c = Math.max(100, Math.round(o + 70 * Math.sin(i / 9) + 25 * Math.sin(i / 47) + (rnd() - 0.5) * 90));
    O.push(o); H.push(Math.max(o, c) + Math.round(rnd() * 35)); L.push(Math.min(o, c) - Math.round(rnd() * 35)); C.push(c);
  }
  return { O, H, L, C, V: C.map(() => 1e6), T: C.map((_, i) => String(i)) };
}

/* ---- the Pine, bar by bar, with its variable names ---- */
function pine(B: ReturnType<typeof bars>, usePriceExtreme: boolean) {
  const n = B.C.length;
  const ema = (len: number) => { const buf: N[] = []; let prev: N = null, a = 2 / (len + 1);
    return (x: N): N => { buf.push(x); if (prev === null) { const w = buf.slice(-len); if (w.length < len || w.some(v => v === null)) return null; prev = (w as number[]).reduce((p, q) => p + q, 0) / len; return prev } if (x === null) return null; prev = a * x + (1 - a) * prev; return prev } };
  const e1 = ema(3), e2 = ema(3), e3 = ema(3), e4 = ema(3);
  const smi: N[] = [];
  const v: Record<string, any> = { trackingLow: false, trackingHigh: false, curLowPrice: NaN, curLowSig: NaN, curHighPrice: NaN, curHighSig: NaN,
    lastLowPrice: null, lastLowSig: null, lastHighPrice: null, lastHighSig: null, bullArmed: false, buyLevel: null, buyTriggered: false };
  const out = { bull: [] as N[], bear: [] as N[], buy: [] as N[], sh: [] as N[], sl: [] as N[] };
  for (let t = 0; t < n; t++) {
    let hh: N = null, ll: N = null;
    if (t >= 9) { hh = Math.max(...B.H.slice(t - 9, t + 1)); ll = Math.min(...B.L.slice(t - 9, t + 1)) }
    const num = e2(e1(hh === null ? null : B.C[t] - (hh + (ll as number)) / 2)), den = e4(e3(hh === null ? null : hh - (ll as number)));
    smi[t] = num === null || den === null || den === 0 ? null : 200 * (num / den);
    const s = smi[t], s1 = t ? smi[t - 1] : null;
    const crossUp = s !== null && s1 !== null && s > 0 && s1 <= 0, crossDown = s !== null && s1 !== null && s < 0 && s1 >= 0;
    if (s !== null && s < -40 && !v.trackingLow) Object.assign(v, { trackingLow: true, curLowPrice: B.L[t], curLowSig: s });
    if (s !== null && s > 40 && !v.trackingHigh) Object.assign(v, { trackingHigh: true, curHighPrice: B.H[t], curHighSig: s });
    if (v.trackingLow) {
      if (usePriceExtreme) { if (B.L[t] < v.curLowPrice) v.curLowPrice = B.L[t]; if (s !== null && s < v.curLowSig) v.curLowSig = s }
      else if (s !== null && s < -40 && s < v.curLowSig) Object.assign(v, { curLowPrice: B.L[t], curLowSig: s });
    }
    if (v.trackingHigh) {
      if (usePriceExtreme) { if (B.H[t] > v.curHighPrice) v.curHighPrice = B.H[t]; if (s !== null && s > v.curHighSig) v.curHighSig = s }
      else if (s !== null && s > 40 && s > v.curHighSig) Object.assign(v, { curHighPrice: B.H[t], curHighSig: s });
    }
    let bear = 0, bull = 0, buy = 0;
    if (v.trackingHigh && crossDown) {
      const prevHighPrice = v.lastHighPrice, prevHighSig = v.lastHighSig;
      v.lastHighPrice = v.curHighPrice; v.lastHighSig = v.curHighSig; v.trackingHigh = false;
      if (prevHighPrice !== null && v.lastHighPrice > prevHighPrice && v.lastHighSig < prevHighSig) bear = 1;
    }
    if (v.trackingLow && crossUp) {
      const prevLowPrice = v.lastLowPrice, prevLowSig = v.lastLowSig;
      v.lastLowPrice = v.curLowPrice; v.lastLowSig = v.curLowSig; v.trackingLow = false;
      if (prevLowPrice !== null && v.lastLowPrice < prevLowPrice && v.lastLowSig > prevLowSig) { bull = 1; v.bullArmed = true; v.buyLevel = v.lastHighPrice; v.buyTriggered = false }
    }
    if (v.bullArmed && !v.buyTriggered && v.buyLevel !== null && B.C[t] > v.buyLevel) { v.buyTriggered = true; buy = 1 }
    if (v.buyTriggered) v.bullArmed = false;
    out.bull[t] = s === null ? null : bull; out.bear[t] = s === null ? null : bear; out.buy[t] = s === null ? null : buy;
    out.sh[t] = v.lastHighPrice; out.sl[t] = v.lastLowPrice;
  }
  return out;
}

const B = bars(1600);
describe('Alpha Divergence (lab)', () => {
  for (const [mode, price] of [['Original (SMI extreme)', false], ['Proposed (Price extreme)', true]] as const) {
    it(`${mode}: BULL DIV, BEAR DIV, BUY A and the swing levels equal the Pine on every bar`, () => {
      const o = F.alpha_divergence(B as any, { swing_mode: mode }) as Record<string, N[]>, r = pine(B, price);
      expect(o.bull_div).toEqual(r.bull); expect(o.bear_div).toEqual(r.bear); expect(o.buy_a).toEqual(r.buy);
      expect(o.swing_high).toEqual(r.sh); expect(o.swing_low).toEqual(r.sl);
      expect(r.bull.filter(x => x === 1).length).toBeGreaterThan(2); expect(r.bear.filter(x => x === 1).length).toBeGreaterThan(2);
      expect(r.buy.filter(x => x === 1).length).toBeGreaterThan(0);
    });
  }
  it('the two modes differ (the swing price comes from another candle)', () => {
    const a = F.alpha_divergence(B as any, {}) as Record<string, N[]>, b = F.alpha_divergence(B as any, { swing_mode: 'Proposed (Price extreme)' }) as Record<string, N[]>;
    expect(a.swing_low).not.toEqual(b.swing_low);
  });
  it('causal: every output at bar t is the same when the bars after t are cut', () => {
    const out = F.alpha_divergence(B as any, {}) as Record<string, N[]>;
    for (const t of [30, 300, 801, 1599]) {
      const cut = F.alpha_divergence({ ...B, O: B.O.slice(0, t + 1), H: B.H.slice(0, t + 1), L: B.L.slice(0, t + 1), C: B.C.slice(0, t + 1), V: B.V.slice(0, t + 1), T: B.T.slice(0, t + 1) } as any, {}) as Record<string, N[]>;
      for (const k of Object.keys(cut)) expect(cut[k][t], `${k} at ${t}`).toBe(out[k][t]);
    }
  });
  it('the Terminal drawing: a BULL DIV label on the swing candle, before the day the output says 1; lines, shading, the active BUY A level', () => {
    const o = F.alpha_divergence(B as any, {}) as Record<string, N[]>, d = DRAWINGS.alpha_divergence(B as any, {});
    const bulls = d.marks!.filter(m => m.text === 'BULL DIV').map(m => m.i), confirms = o.bull_div.flatMap((v, i) => v === 1 ? [i] : []);
    expect(bulls.length).toBe(confirms.length);
    bulls.forEach((i, k) => expect(i).toBeLessThan(confirms[k]));                  // hindsight placement: on the swing, known later
    bulls.forEach((i, k) => expect(o.swing_low[confirms[k]]).toBe(B.L[i]));        // the label's candle is the swing the output names
    expect(d.segments!.filter(g => g.layer === 'divergences').length).toBe(confirms.length + o.bear_div.filter(v => v === 1).length);
    expect(d.shades!.every(h => h.layer === 'shading' && h.i0 < h.i1)).toBe(true);
    expect(d.marks!.filter(m => m.text === 'BUY A').map(m => m.i)).toEqual(o.buy_a.flatMap((v, i) => v === 1 ? [i] : []));
    expect(d.segments!.filter(g => g.layer === 'buy_a').length).toBeLessThanOrEqual(1);
    expect(new Set(d.marks!.map(m => m.layer))).toEqual(new Set(['swings', 'divergences', 'buy_a']));
  });
});
