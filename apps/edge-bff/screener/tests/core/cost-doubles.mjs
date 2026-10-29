/* Test doubles for the generator's cost probe (registry-cost.test.mjs): kernels in the shape of indicators.ts F,
   (bars, params) => outputs, whose growth with the length is known by construction. The probe imports this module in its
   child process after its work meter starts, as it imports indicators.ts for the registry. */
const nul = n => new Array(n).fill(null);

/** O(N): a running mean (each bar adds one value and drops one), seeded over the first n values. */
function runningMean(x, n) {
  const o = nul(x.length);
  let s = 0;
  for (let i = 0; i < x.length; i++) {
    s += x[i];
    if (i >= n) s -= x[i - n];
    if (i >= n - 1) o[i] = s / n;
  }
  return o;
}

/** O(N·n): the highest value of each window of n, found by looping over the window (TA-Lib MAX). */
function windowMax(x, n) {
  const o = nul(x.length);
  for (let i = n - 1; i < x.length; i++) {
    let m = x[i - n + 1];
    for (let j = i - n + 2; j <= i; j++) if (x[j] > m) m = x[j];
    o[i] = m;
  }
  return o;
}

/* Run once when the module loads, so these two kernels are compiled at import: the probe has to start its work meter
   before it imports the measured module (costWork), or their loops run without block counts and the probe stops
   (registry-cost.test.mjs: with the module loaded before the meter, the probe refuses). */
windowMax([3, 1, 2], 2);
runningMean([1, 2, 3], 2);

export const DEFAULTS = {
  window_max: { length: 14 },
  window_reduce: { length: 14 },
  wide_window: { length: 1500 },
  window_over_intermediate: { length: 14, smooth: 3 },
  running_mean: { length: 20 },
  recursive: { length: 20 },
  switchable: { length: 20, method: 'running' },
  stepped: { length: 20 },
};

export const F = {
  window_max: (B, p) => ({ out: windowMax(B.C, p.length) }),
  // O(N·n) through a built-in that calls back into JavaScript: each window's slice summed by reduce (the callback runs
  // n times per bar and is counted); a window inside a built-in that does not call back is not counted (the generator's
  // executedChars notes)
  window_reduce: (B, p) => ({ out: B.C.map((_, i) => (i >= p.length - 1 ? B.C.slice(i - p.length + 1, i + 1).reduce((a, b) => a + b, 0) / p.length : null)) }),
  // the window loop at a default so large that the probe's second length (at most a quarter of the bars) is close to it
  wide_window: (B, p) => ({ out: windowMax(B.C, p.length) }),
  // O(N·n) in length on an internal intermediate array, O(N) in smooth (Stochastic RSI's shape: RSI, then a window)
  window_over_intermediate: (B, p) => {
    const m = runningMean(B.C, p.smooth);
    const valid = m.map(v => (v === null ? -Infinity : v));
    return { out: windowMax(valid, p.length) };
  },
  running_mean: (B, p) => ({ out: runningMean(B.C, p.length) }),
  // O(N): an exponential average, seeded with the mean of the first n values
  recursive: (B, p) => {
    const x = B.C, n = p.length, a = 2 / (n + 1), o = nul(x.length);
    let s = 0;
    for (let i = 0; i < n && i < x.length; i++) s += x[i];
    let prev = s / n;
    for (let i = n; i < x.length; i++) { prev = a * x[i] + (1 - a) * prev; o[i] = prev }
    return { out: o };
  },
  // O(N) at its default method, O(N·n) at the other option (I32 stddev 'sample' swaps its kernel the same way)
  switchable: (B, p) => ({ out: p.method === 'loop' ? windowMax(B.C, p.length) : runningMean(B.C, p.length) }),
  // between the classes: per bar one heavy step at the short length and three at the long one, so the work grows by
  // about 2 (less than 2 for the per-bar overhead, more than 1 because the step outweighs it), which neither class owns
  stepped: (B, p) => {
    const x = B.C, steps = p.length >= 500 ? 3 : 1, o = nul(x.length);
    for (let i = 1; i < x.length; i++) {
      let v = x[i];
      for (let k = 0; k < steps; k++) {
        const d = x[i] - x[i - 1], q = d * d, r = Math.abs(d) + 1, t = q / r, u = Math.sqrt(t + 1), w = u * 0.5;
        const y = (w + t) / (r + q + 1), z = y * y + w, h = Math.max(z, y), g = Math.min(h, u);
        v = v + g - h * 0.5 + (y - z) * 0.25;
      }
      o[i] = v;
    }
    return { out: o };
  },
};
