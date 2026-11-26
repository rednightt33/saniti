// EXEC-PINE-INDICATORS (2026-11-23): the lab formula Alpha KAMA (the user's Pine v5 "VHF Adaptive Linear Regression
// KAMA", © simwai, MPL-2.0) against a second implementation written here as the Pine runs it: one loop over the bars,
// every Pine variable a history array, every block's own history advanced only on the bars it runs. Both follow the same
// reading of Pine (EXEC: TradingView values are still asked of the user); this checks the formula's code against that
// reading on every bar, the colour groups, the signals, the start of history and causality.
import { describe, expect, it } from 'vitest';
import { F } from '../../src/calc/indicators';
import { KAMA_PALETTE } from '../../src/calc/indicators';

type N = number | null;
function bars(n: number, seed = 4242) {
  let s = seed; const rnd = () => (s = (s * 1103515245 + 12345) % 2147483648) / 2147483648;
  const O: number[] = [], H: number[] = [], L: number[] = [], C: number[] = [];
  let c = 2000;
  for (let i = 0; i < n; i++) {
    const regime = Math.floor(i / 140) % 3;                      // trend up, chop, trend down
    const drift = regime === 0 ? 9 : regime === 2 ? -8 : 0;
    const o = c; c = Math.max(100, Math.round(o + drift + (rnd() - 0.5) * 70));
    O.push(o); H.push(Math.max(o, c) + Math.round(rnd() * 30)); L.push(Math.min(o, c) - Math.round(rnd() * 30)); C.push(c);
  }
  for (let i = 600; i < 625; i++) { O[i] = C[599]; H[i] = C[599]; L[i] = C[599]; C[i] = C[599] }   // a suspension: flat bars
  return { O, H, L, C, V: C.map(() => 1e6), T: C.map((_, i) => String(i)) };
}

/* ---- the Pine, bar by bar ---- */
function pine(B: ReturnType<typeof bars>, P: { kamaLength: number; f1: number; f2: number; smoothing: string; sLen: number; vhf: boolean; linreg: boolean; gl: number }) {
  const n = B.C.length;
  const na = (v: N | undefined): v is null => v === null || v === undefined || Number.isNaN(v);
  const nzv = (v: N | undefined) => na(v) ? 0 : v as number;
  const h = (arr: N[], t: number, k: number): N => t - k >= 0 ? arr[t - k] : null;
  // t3 call instances: each has six series
  const mkT3 = () => ({ s: [[], [], [], [], [], []] as N[][] });
  const t3call = (inst: ReturnType<typeof mkT3>, t: number, src: N, len: number) => {
    const a = 1, al = 2 / (1 + len);
    let inp = src; const v: N[] = [];
    for (let k = 0; k < 6; k++) { const p1 = nzv(h(inst.s[k], t, 1)); const x = na(inp) ? null : p1 + al * ((inp as number) - p1); inst.s[k][t] = x; v.push(x); inp = x }
    if (na(v[5])) return null;
    return -a * a * a * (v[5] as number) + (3 * a * a + 3 * a * a * a) * (v[4] as number) + (-6 * a * a - 3 * a - 3 * a * a * a) * (v[3] as number) + (1 + 3 * a + a * a * a + 3 * a * a) * (v[2] as number);
  };
  const hann = (series: N[], t: number, len: number) => { let sum = 0, coef = 0; for (let i = 1; i <= len; i++) { const c = 1 - Math.cos(2 * Math.PI * i / (len + 1)); sum += c * nzv(h(series, t, i - 1)); coef += c } return coef !== 0 ? sum / coef : 0 };
  const T3c = mkT3(), T3l = mkT3(), T3h = mkT3();
  const rawC: N[] = [], rawL: N[] = [], rawH: N[] = [];
  const _close: N[] = [], _low: N[] = [], _high: N[] = [];
  const vhfDiff: N[] = [], vhfNoise: N[] = [], kamaS: N[] = [], kamaRaw: N[] = [], tr: N[] = [], atrS: N[] = [], slope: N[] = [];
  // the kama() block's own history (advanced on the bars it runs) and its math.sum buffer
  const blockTmp: N[] = [], sumBuf: N[] = [];
  const out = { kama: [] as N[], idx: [] as N[], state: [] as N[], long: [] as N[], short: [] as N[] };
  for (let t = 0; t < n; t++) {
    // [_close, _low, _high] = [close[1], high[1], low[1]]
    rawC[t] = t > 0 ? B.C[t - 1] : null; rawL[t] = t > 0 ? B.H[t - 1] : null; rawH[t] = t > 0 ? B.L[t - 1] : null;
    let c: N = rawC[t], l: N = rawL[t], hh: N = rawH[t];
    if (P.smoothing === 'T3') { c = t3call(T3c, t, c, P.sLen); l = t3call(T3l, t, l, P.sLen); hh = t3call(T3h, t, hh, P.sLen) }
    if (P.smoothing === 'Hann Window') { c = hann(rawC, t, P.sLen); l = hann(rawL, t, P.sLen); hh = hann(rawH, t, P.sLen) }
    _close[t] = c; _low[t] = l; _high[t] = hh;
    let kLen: N = P.kamaLength;
    if (P.vhf) {
      const prevC = h(_close, t, 1);
      vhfDiff[t] = na(c) ? null : (c as number) > nzv(prevC) ? (c as number) - nzv(prevC) : nzv(prevC) - (c as number);
      vhfNoise[t] = na(vhfDiff[t]) ? null : nzv(h(vhfNoise, t, 1)) - nzv(h(vhfDiff, t, P.kamaLength)) + (vhfDiff[t] as number);
      let HCP: N = null, LCP: N = null;
      if (t >= P.kamaLength - 1) for (let j = 0; j < P.kamaLength; j++) { const v = _close[t - j]; if (!na(v)) { HCP = HCP === null ? v : Math.max(HCP, v as number); LCP = LCP === null ? v : Math.min(LCP, v as number) } }
      const vhf = HCP === null || LCP === null || na(vhfNoise[t]) ? null : (HCP - LCP) / (vhfNoise[t] as number);
      const pa = vhf === null || !Number.isFinite(vhf) ? null : Math.round(P.kamaLength * vhf * 2);
      kLen = pa;
    }
    // kama(_close, _kamaLength)
    let k: N = null;
    if (kLen !== null && t > kLen) {
      const len = Math.max(kLen, 1);
      sumBuf.push(na(h(_close, t, 1)) ? null : Math.abs((c as number) - (h(_close, t, 1) as number)));
      let s: N = null;
      if (sumBuf.length >= len) { s = 0; for (let j = 1; j <= len; j++) { const v = sumBuf[sumBuf.length - j]; if (na(v)) { s = null; break } s += v as number } }
      const prevTmp = blockTmp.length ? blockTmp[blockTmp.length - 1] : null;
      const back = h(_close, t, kLen);
      const er = (!na(s) && s !== 0) ? (na(back) ? null : Math.abs((c as number) - (back as number)) / (s as number)) : 0;
      const tmp = er === null ? null : nzv(prevTmp) + Math.pow(er * (P.f1 - P.f2) + P.f2, 2) * ((c as number) - nzv(prevTmp));
      blockTmp.push(tmp); k = tmp;
    }
    kamaRaw[t] = k;
    if (P.linreg) {
      let v: N = null;
      if (t >= 4) { const y = [4, 3, 2, 1, 0].map(j => kamaRaw[t - j]); if (y.every(q => !na(q))) { const ys = y as number[]; const xm = 2, ym = ys.reduce((a, b) => a + b, 0) / 5; let sxy = 0, sxx = 0; ys.forEach((q, i) => { sxy += (i - xm) * (q - ym); sxx += (i - xm) ** 2 }); v = ym + (sxy / sxx) * (2 - xm) } }
      kamaS[t] = v;
    } else kamaS[t] = k;
    // maDiff, ATR (Hann over the true range of the swapped high and low), slope
    let ma: N = null;
    if (t >= P.gl - 1) { let s = 0; for (let j = 0; j < P.gl; j++) { const v = kamaS[t - j]; if (na(v)) { s = NaN; break } s += v as number } ma = Number.isNaN(s) ? null : s / P.gl }
    tr[t] = na(hh) || na(l) ? null : Math.max(Math.max((hh as number) - (l as number), Math.abs((hh as number) - nzv(h(_close, t, 1)))), Math.abs((l as number) - nzv(h(_close, t, 1))));
    atrS[t] = hann(tr, t, P.gl);
    slope[t] = na(kamaS[t]) || ma === null || atrS[t] === 0 ? null : Math.atan(((kamaS[t] as number) - ma) / (atrS[t] as number)) * 180 / Math.PI;
    const cross = (a: N[], b: (t: number) => N, dn: boolean) => { const a0 = a[t], b0 = b(t), a1 = h(a, t, 1), b1 = t > 0 ? b(t - 1) : null;
      if (na(a0) || na(b0) || na(a1) || na(b1)) return false; return dn ? (a0 as number) < (b0 as number) && (a1 as number) >= (b1 as number) : (a0 as number) > (b0 as number) && (a1 as number) <= (b1 as number) };
    const sl = slope[t];
    const sig = (dn: boolean) => na(kamaS[t]) || sl === null ? null : cross(_close, q => kamaS[q], dn) && cross(kamaS, q => h(kamaS, q, 1), dn) && (dn ? sl < -0.5 : sl > 0.5) ? 1 : 0;
    out.kama[t] = kamaS[t];
    // rescale(): int(19 * (slope + 20)) / int(40), kept to 0..19
    const idx = sl === null ? null : Math.min(19, Math.max(0, Math.trunc(Math.trunc(19 * (sl + 20)) / 40)));
    out.idx[t] = idx; out.state[t] = idx === null ? null : Math.floor(idx / 4);
    out.long[t] = sig(false); out.short[t] = sig(true);
  }
  return out;
}

const near = (a: N, b: N) => a === null || b === null ? a === b : Math.abs(a - b) <= 1e-7 * Math.max(1, Math.abs(b));
const DEF = { kamaLength: 89, f1: 0.66, f2: 0.0645, smoothing: 'T3', sLen: 3, vhf: true, linreg: false, gl: 14 };
const B = bars(1400);

describe('Alpha KAMA (lab)', () => {
  const out = F.alpha_kama(B as any, {}) as Record<string, N[]>, ref = pine(B, DEF);
  it('KAMA, colour index and state, ENTER LONG and SHORT equal the Pine on every bar (defaults)', () => {
    for (let t = 0; t < B.C.length; t++) {
      expect(near(out.kama[t], ref.kama[t]), `kama ${t}: ${out.kama[t]} vs ${ref.kama[t]}`).toBe(true);
      expect(out.color_index[t], `index ${t}`).toBe(ref.idx[t]);
      expect(out.color_state[t], `state ${t}`).toBe(ref.state[t]);
      expect(out.long[t], `long ${t}`).toBe(ref.long[t]);
      expect(out.short[t], `short ${t}`).toBe(ref.short[t]);
    }
  });
  it('the path reaches every case: all five states, both signals, a skipped block early on', () => {
    expect(new Set(ref.state.filter(v => v !== null))).toEqual(new Set([0, 1, 2, 3, 4]));
    expect(ref.long.filter(v => v === 1).length).toBeGreaterThan(0);
    expect(ref.short.filter(v => v === 1).length).toBeGreaterThan(0);
    const firstK = out.kama.findIndex(v => v !== null);
    expect(firstK).toBeGreaterThan(88);                                      // VHF needs 89 smoothed closes
    // bars where bar_index <= the adaptive period after the first run: the block skips, KAMA is missing there and the
    // next run continues from the last one (the Pine above checks the values on either side)
    const gaps = out.kama.map((v, i) => i > firstK && v === null ? i : -1).filter(i => i >= 0);
    expect(gaps.length).toBeGreaterThan(0);
    expect(Math.min(...gaps)).toBeLessThanOrEqual(178);
    // KAMA starts from 0 and reaches the price level within the first few hundred bars
    expect(out.kama[firstK] as number).toBeLessThan(B.C[firstK] / 10);
    expect(Math.abs((out.kama[400] as number) / B.C[400] - 1)).toBeLessThan(0.15);
  });
  it('other settings follow the same reading: no smoothing, Hann, VHF off, linear regression, shorter lengths', () => {
    const cases: [Record<string, unknown>, typeof DEF][] = [
      [{ smoothing_method: 'None' }, { ...DEF, smoothing: 'None' }],
      [{ smoothing_method: 'Hann Window', smoothing_length: 4 }, { ...DEF, smoothing: 'Hann Window', sLen: 4 }],
      [{ vhf_adaptive: false, kama_length: 30 }, { ...DEF, vhf: false, kamaLength: 30 }],
      [{ linear_regression: true, gradient_lookback: 10, kama_factor_1: 0.5, kama_factor_2: 0.05 }, { ...DEF, linreg: true, gl: 10, f1: 0.5, f2: 0.05 }],
    ];
    for (const [p, P] of cases) {
      const o = F.alpha_kama(B as any, p) as Record<string, N[]>, r = pine(B, P);
      for (let t = 0; t < B.C.length; t++) {
        expect(near(o.kama[t], r.kama[t]), `${JSON.stringify(p)} kama ${t}`).toBe(true);
        expect(o.color_index[t], `${JSON.stringify(p)} index ${t}`).toBe(r.idx[t]);
        expect(o.long[t], `${JSON.stringify(p)} long ${t}`).toBe(r.long[t]);
      }
    }
  });
  it('the colour groups are the user\'s 1a: index 0-3 red ... 16-19 green, boundaries at -11.6, -3.2, +5.3, +13.7 degrees', () => {
    expect(KAMA_PALETTE.length).toBe(20);
    const idxOf = (a: number) => { const x = Math.trunc(19 * (a + 20)); return x <= 0 ? 0 : Math.min(19, Math.floor(x / 40)) };
    expect([-30, -11.6, -11.5, -3.2, -3.1, 5.2, 5.3, 13.6, 13.7, 30].map(a => Math.floor(idxOf(a) / 4))).toEqual([0, 0, 1, 1, 2, 2, 3, 3, 4, 4]);
    for (let t = 0; t < B.C.length; t++) if (out.color_index[t] !== null) expect(out.color_state[t]).toBe(Math.floor((out.color_index[t] as number) / 4));
  });
  it('EMA X is the released EMA (I02) of today\'s close', () => {
    const o = F.alpha_kama(B as any, { ema_length: 10 }) as Record<string, N[]>, e = F.ema(B as any, { length: 10 }) as Record<string, N[]>;
    expect(o.ema_x).toEqual(e.ema);
  });
  it('causal: every output at bar t is the same when the bars after t are cut', () => {
    for (const t of [150, 333, 610, 900, 1399]) {
      const cut = F.alpha_kama({ ...B, O: B.O.slice(0, t + 1), H: B.H.slice(0, t + 1), L: B.L.slice(0, t + 1), C: B.C.slice(0, t + 1), V: B.V.slice(0, t + 1), T: B.T.slice(0, t + 1) } as any, {}) as Record<string, N[]>;
      for (const k of Object.keys(cut)) if (Array.isArray(out[k])) expect(near(cut[k][t], out[k][t]), `${k} at ${t}`).toBe(true);
    }
  });
  it('KAMA at bar t does not read bar t: a change of today\'s bar moves no KAMA value of today', () => {
    const t = 1000, C2 = B.C.slice(), H2 = B.H.slice(), L2 = B.L.slice(); C2[t] *= 1.3; H2[t] *= 1.3; L2[t] *= 1.3;
    const o = F.alpha_kama({ ...B, C: C2, H: H2, L: L2 } as any, {}) as Record<string, N[]>;
    expect(o.kama[t]).toBe(out.kama[t]); expect(o.color_index[t]).toBe(out.color_index[t]);
    expect(o.kama[t + 1]).not.toBe(out.kama[t + 1]);
  });
});
