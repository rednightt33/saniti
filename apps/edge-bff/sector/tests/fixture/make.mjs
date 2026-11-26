/* EXEC-SECTOR-ANALYSIS S4, tests only: MADE-UP sector files (fixtures, no market data): 300 weekday sessions, the 11 IDX-IC
   sector names (a public classification), invented industries' tickers and prices from a seeded random walk. The shapes
   are the contract's (build.mjs). Used by the unit tests and by the fixture build when no local prototype data exists. */
import { buildFiles, SECTORS } from './build.mjs';

export function rng(seed = 7) { let s = seed >>> 0 || 1; return () => ((s = Math.imul(s, 1664525) + 1013904223 >>> 0) / 4294967296) }
/** weekday dates ending on `last`, oldest first */
export function weekdays(last, n) {
  const out = [], d = new Date(last + 'T00:00:00Z');
  while (out.length < n) { const w = d.getUTCDay(); if (w !== 0 && w !== 6) out.push(d.toISOString().slice(0, 10)); d.setUTCDate(d.getUTCDate() - 1) }
  return out.reverse();
}
const walk = (r, n, start, vol, drift = 0, link = null, beta = 0) => {
  const out = [start];
  for (let i = 1; i < n; i++) { const m = link ? link[i] / link[i - 1] - 1 : 0, z = (r() + r() + r() - 1.5) * 2; out.push(Math.max(1, out[i - 1] * (1 + drift + beta * m + vol * z))) }
  return out;
};
/** opts: { sessions = 300, last = '2026-11-17', perIndustry = 4, seed = 7, sectors = 11 } */
export function makeFiles(opts = {}) {
  const r = rng(opts.seed ?? 7), n = opts.sessions ?? 300, dates = weekdays(opts.last ?? '2026-11-17', n);
  const ih = walk(r, n, 7000, 0.006, 0.0001).map(v => Math.round(v * 100) / 100), lq = walk(r, n, 900, 0.004, 0, ih, 1).map(v => Math.round(v * 100) / 100);
  const secs = SECTORS.slice(0, opts.sectors ?? 11), sector = {}, industries = [], stocks = [];
  let t = 0;
  secs.forEach(([name], k) => {
    sector[name] = walk(r, n, 1000 + 100 * k, 0.004, (r() - 0.5) * 0.002, ih, 0.6 + r() * 0.8).map(v => Math.round(v * 100) / 100);
    for (let j = 0; j < 2 + (k % 2); j++) {
      const ind = `${name.split(' ')[0]} industry ${String.fromCharCode(65 + j)}`;
      industries.push({ name: ind, sector: name });
      for (let q = 0; q < (opts.perIndustry ?? 4); q++) {
        const tk = 'X' + String.fromCharCode(65 + (t % 26)) + String.fromCharCode(65 + Math.floor(t / 26) % 26) + (q % 2 ? 'K' : 'Q'); t++;
        const close = walk(r, n, 200 + r() * 4000, 0.012 + r() * 0.01, (r() - 0.5) * 0.002, sector[name], 0.5 + r()).map(v => Math.round(v));
        const late = q === 3 ? 40 : 0;                                   // one stock per industry listed later (nulls before)
        stocks.push({ t: tk, n: `PT Contoh ${tk} Tbk`, sec: name, ind, close: close.map((v, i) => (i < late ? null : v)), volume: close.map(() => Math.round(1e5 + r() * 5e6)) });
      }
    }
  });
  stocks.push({ t: 'XOTH', n: 'PT Contoh Lain Tbk', sec: 'Other', ind: null, close: walk(r, n, 500, 0.01).map(v => Math.round(v)), volume: Array(n).fill(2e5) });
  return buildFiles({ market: 'IHSG', lq45: 'LQ45', dates, index: { IHSG: ih, LQ45: lq }, sector, industries, stocks, days: opts.days ?? 20 });
}
