// EXEC-PINE-INDICATORS (2026-11-23): the lab formula Alpha Extract (the user's Pine v6 "Baseline Deviation Oscillator
// [Alpha Extract]") against a second implementation written here as the Pine runs it, bar by bar: ta.ema / ta.rma seeded
// with the SMA of their first values, ta.atr (Wilder, the first true range high - low), the 4-value median, ta.highest /
// ta.lowest over the window with a missing value left out, nz to 0 for the levels, crossover / crossunder. Plus the
// signals the user asked for (BULL, BEAR; no zero cross), the warm-up as TradingView draws it, and causality.
import { describe, expect, it } from 'vitest';
import { F } from '../../src/calc/indicators';
// released 2026-11-26: the formulas are in calc/indicators.ts (INDICATOR_BETA_TO_LIVE.md Part B)

type N = number | null;
function bars(n: number) {
  let s = 31337; const rnd = () => (s = (s * 1103515245 + 12345) % 2147483648) / 2147483648;
  const O: number[] = [], H: number[] = [], L: number[] = [], C: number[] = [];
  let c = 5000;
  for (let i = 0; i < n; i++) {
    const o = c; c = Math.max(100, Math.round(o + 30 * Math.sin(i / 25) + (rnd() - 0.5) * 120));
    O.push(o); H.push(Math.max(o, c) + Math.round(rnd() * 40)); L.push(Math.min(o, c) - Math.round(rnd() * 40)); C.push(c);
  }
  return { O, H, L, C, V: C.map(() => 1e6), T: C.map((_, i) => String(i)) };
}

/* ---- the Pine, bar by bar ---- */
type P = { ma: string; src: string; len: number; med: number; atr: number; sm: number; win: number; ds: number; ex: number; mult: number };
function pine(B: ReturnType<typeof bars>, P: P) {
  const n = B.C.length, na = (v: N | undefined): v is null => v === null || v === undefined;
  const mkEma = (len: number, alpha = 2 / (len + 1)) => { const buf: N[] = []; let prev: N = null;
    return (x: N): N => { buf.push(x); if (prev === null) { const w = buf.slice(-len); if (w.length < len || w.some(na)) return null; prev = (w as number[]).reduce((a, b) => a + b, 0) / len; return prev }
      if (na(x)) return null; prev = alpha * x + (1 - alpha) * prev; return prev } };
  const mkSma = (len: number) => { const buf: N[] = []; return (x: N): N => { buf.push(x); const w = buf.slice(-len); return w.length < len || w.some(na) ? null : (w as number[]).reduce((a, b) => a + b, 0) / len } };
  const mkWma = (len: number) => { const buf: N[] = []; return (x: N): N => { buf.push(x); const w = buf.slice(-len); if (w.length < len || w.some(na)) return null; let s = 0; for (let j = 0; j < len; j++) s += (w[len - 1 - j] as number) * (len - j); return s / (len * (len + 1) / 2) } };
  let ma: (x: N) => N;
  if (P.ma === 'SMA') ma = mkSma(P.len);
  else if (P.ma === 'RMA') ma = mkEma(P.len, 1 / P.len);
  else if (P.ma === 'WMA') ma = mkWma(P.len);
  else if (P.ma === 'HMA') { const a = mkWma(Math.floor(P.len / 2)), b = mkWma(P.len), c = mkWma(Math.floor(Math.sqrt(P.len))); ma = x => { const u = a(x), v = b(x); return c(na(u) || na(v) ? null : 2 * u - v) } }
  else if (P.ma === 'TEMA') { const e1 = mkEma(P.len), e2 = mkEma(P.len), e3 = mkEma(P.len); ma = x => { const a = e1(x), b = e2(a), c = e3(b); return na(a) || na(b) || na(c) ? null : 3 * a - 3 * b + c } }
  else ma = mkEma(P.len);
  const atrE = mkEma(P.atr, 1 / P.atr), oscE = mkEma(P.sm), sigE = mkEma(Math.max(2, Math.round(P.sm * P.mult))), upE = mkEma(P.ds), dnE = mkEma(P.ds);
  const baseRaw: N[] = [], osc: N[] = [];
  const out = { bdo: [] as N[], signal: [] as N[], upper: [] as N[], lower: [] as N[], uext: [] as N[], lext: [] as N[], bull: [] as N[], bear: [] as N[] };
  for (let t = 0; t < n; t++) {
    const src = P.src === 'HL2' ? (B.H[t] + B.L[t]) / 2 : P.src === 'Open' ? B.O[t] : B.C[t];
    baseRaw[t] = ma(src);
    let base: N = null;
    if (t >= P.med - 1) { const w = baseRaw.slice(t - P.med + 1, t + 1); if (!w.some(na)) { const s = (w as number[]).slice().sort((a, b) => a - b); base = P.med % 2 ? s[(P.med - 1) / 2] : (s[P.med / 2 - 1] + s[P.med / 2]) / 2 } }
    const tr = t === 0 ? B.H[t] - B.L[t] : Math.max(B.H[t] - B.L[t], Math.abs(B.H[t] - B.C[t - 1]), Math.abs(B.L[t] - B.C[t - 1]));
    const a = atrE(tr);
    const raw = na(base) || na(a) ? null : (B.C[t] - base) / Math.max(1e-10, ((base + a) - (base - a)) * 0.5);
    osc[t] = oscE(raw);
    const sig = sigE(osc[t]);
    const ext = (hi: boolean): N => { if (t < P.win - 1) return null; let m: N = null; for (let j = t - P.win + 1; j <= t; j++) { const v = osc[j]; if (!na(v) && (m === null || (hi ? v > m : v < m))) m = v } return m };
    const upRaw = upE(ext(true)), dnRaw = dnE(ext(false));
    const U = Math.max(na(upRaw) ? 0 : upRaw, 0), D = Math.min(na(dnRaw) ? 0 : dnRaw, 0);
    out.bdo[t] = osc[t]; out.signal[t] = sig; out.upper[t] = U; out.lower[t] = -Math.abs(D); out.uext[t] = U * (1 + P.ex); out.lext[t] = -Math.abs(D * (1 + P.ex));
    const xo = (b: N[]) => t > 0 && !na(osc[t]) && !na(osc[t - 1]) && (osc[t] as number) > (b[t] as number) && (osc[t - 1] as number) <= (b[t - 1] as number);
    const xu = (b: N[]) => t > 0 && !na(osc[t]) && !na(osc[t - 1]) && (osc[t] as number) < (b[t] as number) && (osc[t - 1] as number) >= (b[t - 1] as number);
    const ready = t > 0 && !na(osc[t]) && !na(osc[t - 1]);
    out.bull[t] = ready ? (xo(out.lower) || xo(out.lext) ? 1 : 0) : null;
    out.bear[t] = ready ? (xu(out.upper) || xu(out.uext) ? 1 : 0) : null;
  }
  return out;
}

const near = (a: N, b: N) => a === null || b === null ? a === b : Math.abs(a - b) <= 1e-9 * Math.max(1, Math.abs(b));
const DEF: P = { ma: 'EMA', src: 'Close', len: 23, med: 4, atr: 14, sm: 5, win: 120, ds: 10, ex: 0.2, mult: 1.5 };
const B = bars(1500);

describe('Alpha Extract (lab)', () => {
  const out = F.alpha_extract(B as any, {}) as Record<string, N[]>, ref = pine(B, DEF);
  const same = (o: Record<string, N[]>, r: ReturnType<typeof pine>, tag: string) => {
    for (let t = 0; t < B.C.length; t++) {
      expect(near(o.bdo[t], r.bdo[t]), `${tag} bdo ${t}`).toBe(true); expect(near(o.signal[t], r.signal[t]), `${tag} signal ${t}`).toBe(true);
      expect(near(o.upper[t], r.upper[t]), `${tag} upper ${t}`).toBe(true); expect(near(o.lower[t], r.lower[t]), `${tag} lower ${t}`).toBe(true);
      expect(near(o.upper_extreme[t], r.uext[t]), `${tag} +ext ${t}`).toBe(true); expect(near(o.lower_extreme[t], r.lext[t]), `${tag} -ext ${t}`).toBe(true);
      expect(o.bull[t], `${tag} bull ${t}`).toBe(r.bull[t]); expect(o.bear[t], `${tag} bear ${t}`).toBe(r.bear[t]);
    }
  };
  it('BDO, Signal, the four levels, BULL and BEAR equal the Pine on every bar (defaults)', () => same(out, ref, 'default'));
  it('the path reaches every case: BULL and BEAR, some in the warm-up where the levels are 0', () => {
    expect(ref.bull.filter(v => v === 1).length).toBeGreaterThan(5); expect(ref.bear.filter(v => v === 1).length).toBeGreaterThan(5);
    const firstUp = ref.upper.findIndex(v => (v as number) > 0);
    expect(firstUp).toBeGreaterThan(100);                                              // 0 until the dynamic level exists
    expect(out.upper[0]).toBe(0); expect(out.lower[0]).toBe(0);
    expect(out.bdo[24]).toBeNull(); expect(out.bdo[30]).not.toBeNull();                // EMA 23, median 4, EMA 5
  });
  it('other settings follow the same reading: SMA, RMA, WMA, HMA, TEMA, HL2 and Open, short windows', () => {
    const cases: [Record<string, unknown>, P][] = [
      [{ ma_type: 'SMA', source: 'HL2' }, { ...DEF, ma: 'SMA', src: 'HL2' }],
      [{ ma_type: 'RMA', median_length: 5, signal_multiplier: 2 }, { ...DEF, ma: 'RMA', med: 5, mult: 2 }],
      [{ ma_type: 'WMA', dynamic_window: 30, dynamic_smooth: 3 }, { ...DEF, ma: 'WMA', win: 30, ds: 3 }],
      [{ ma_type: 'HMA', source: 'Open', smooth_length: 1 }, { ...DEF, ma: 'HMA', src: 'Open', sm: 1 }],
      [{ ma_type: 'TEMA', atr_length: 7, dynamic_expansion: 0.5 }, { ...DEF, ma: 'TEMA', atr: 7, ex: 0.5 }],
    ];
    for (const [p, P] of cases) same(F.alpha_extract(B as any, p) as Record<string, N[]>, pine(B, P), JSON.stringify(p));
  });
  it('no zero cross is a BULL or BEAR by itself once the levels exist (the user\'s 3: labels only)', () => {
    let zeroOnly = 0;
    for (let t = 200; t < B.C.length; t++) {
      const a = out.bdo[t], b = out.bdo[t - 1];
      if (a === null || b === null || !(a > 0 && b <= 0)) continue;
      if ((out.lower[t] as number) < 0 && (out.lower_extreme[t] as number) < 0 && !(b <= (out.lower[t - 1] as number) || b <= (out.lower_extreme[t - 1] as number))) { zeroOnly++; expect(out.bull[t]).toBe(0) }
    }
    expect(zeroOnly).toBeGreaterThan(0);
  });
  it('causal: every output at bar t is the same when the bars after t are cut', () => {
    for (const t of [40, 140, 700, 1499]) {
      const cut = F.alpha_extract({ ...B, O: B.O.slice(0, t + 1), H: B.H.slice(0, t + 1), L: B.L.slice(0, t + 1), C: B.C.slice(0, t + 1), V: B.V.slice(0, t + 1), T: B.T.slice(0, t + 1) } as any, {}) as Record<string, N[]>;
      for (const k of Object.keys(cut)) if (Array.isArray(out[k])) expect(near(cut[k][t], out[k][t]), `${k} at ${t}`).toBe(true);
    }
  });
});
