/* The backtest page's own condition code (backtest.html, 2026-10-26 upload: cmpSeries/regEval, signalsFor, the
   marker loop of refreshSignals, exitSeries, and the CATALOG conditions dip, breakout, volspike, macross, macd with
   its helpers sma, highest, bullDiv), kept as close to the page as possible and used only as the test oracle.
   Inputs are Float64Arrays with NaN where the worker's series hold null, as on the page. */
export const toF = s => Float64Array.from(s, v => (typeof v === 'number' && Number.isFinite(v)) ? v : NaN);

// regEval (op names mapped: gt, lt, ca, cb)
export function regEval(a, b, v, op) {
  const N = a.length, o = new Uint8Array(N), at = i => b ? b[i] : v;
  for (let i = 1; i < N; i++) {
    const x = a[i], y = at(i), px = a[i - 1], py = at(i - 1); if (isNaN(x) || isNaN(y)) continue;
    o[i] = op === 'gt' ? x > y : op === 'lt' ? x < y : op === 'ca' ? (px <= py && x > y) : (px >= py && x < y);
  }
  return o;
}

export function signalsFor(series, logic, atLeast, window) {
  const N = series[0].length, need = logic === 'all' ? series.length : logic === 'any' ? 1 : Math.min(atLeast, series.length);
  const W = Math.max(1, window | 0), entry = new Uint8Array(N);
  if (series.length) {
    const recent = series.map(() => -1e9);
    for (let i = 0; i < N; i++) {
      let met = 0; series.forEach((s, k) => { if (s[i]) recent[k] = i; if (i - recent[k] < W) met++ });
      entry[i] = met >= need ? 1 : 0;
    }
  }
  return entry;
}

export const markers = (s, idx) => idx.filter(i => s[i] && !s[i - 1]);

export function exitSeries(ss, logic) {
  const N = ss[0].length, r = new Uint8Array(N);
  for (let i = 0; i < N; i++) { const hit = ss.filter(s => s[i]).length; r[i] = logic === 'all' ? hit === ss.length : hit > 0 }
  return r;
}

export const sma = (a, n) => { const r = new Float64Array(a.length).fill(NaN); let s = 0; for (let i = 0; i < a.length; i++) { s += a[i]; if (i >= n) s -= a[i - n]; if (i >= n - 1) r[i] = s / n } return r };
export const highest = (a, n) => { const r = new Float64Array(a.length).fill(NaN); for (let i = n; i < a.length; i++) { let m = -1e18; for (let j = i - n; j < i; j++) m = Math.max(m, a[j]); r[i] = m } return r };
export const bullDiv = (l, mline, look, k = 3) => {
  const out = new Uint8Array(l.length), piv = [];
  for (let i = k; i < l.length - k; i++) { let isLow = true; for (let j = 1; j <= k; j++) if (l[i] > l[i - j] || l[i] > l[i + j]) { isLow = false; break } if (isLow) piv.push(i) }
  for (let p = 1; p < piv.length; p++) { const a = piv[p - 1], b = piv[p]; if (b - a > look) continue; if (l[b] < l[a] && mline[b] > mline[a] && !isNaN(mline[a])) out[b + k] = 1 }
  return out;
};

// CATALOG conditions; dip compares the return as a fraction (the page multiplies by 100 and compares percent)
export function dip(c, v) { const N = c.length, r = new Uint8Array(N); for (let i = 1; i < N; i++) r[i] = (c[i] / c[i - 1] - 1) <= v; return r }
export function breakout(h, c, len) { const N = c.length, hh = highest(h, len), r = new Uint8Array(N); for (let i = 0; i < N; i++) r[i] = c[i] > hh[i]; return r }
export function volspike(v, len, val) { const N = v.length, a = sma(v, len), r = new Uint8Array(N); for (let i = len; i < N; i++) r[i] = v[i] / a[i - 1] > val; return r }
export function macross(c, fast, slow, op) { const N = c.length, a = sma(c, fast), b = sma(c, slow), r = new Uint8Array(N); for (let i = 1; i < N; i++) r[i] = op === 'golden' ? (a[i - 1] <= b[i - 1] && a[i] > b[i]) : a[i] > b[i]; return r }
export function macdCond(m, sig, hist, op) { const N = m.length, r = new Uint8Array(N); for (let i = 1; i < N; i++) r[i] = op === 'xsig' ? (m[i - 1] <= sig[i - 1] && m[i] > sig[i]) : hist[i] > 0; return r }
