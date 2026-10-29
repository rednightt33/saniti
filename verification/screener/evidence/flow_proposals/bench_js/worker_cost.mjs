// Synthetic estimate of the screener-worker CPU cost of the broker metrics (FL06-FL15) for the whole universe from a
// published per-session broker window. Row counts follow the live data: ~25k F05 rows per session (q13: 487,715 rows in
// 20 sessions), 112 broker codes, ~850 tickers. Values are random; only the cost is measured.
const T = 850, S = 41, B = 112;
let seed = 7; const rnd = () => (seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648;
const tickers = [];
let rows = 0;
for (let t = 0; t < T; t++) {
  const active = 5 + Math.floor(rnd() ** 2 * 75);          // brokers per session, skewed like the live 11..89
  const d = [], b = [], bv = [], sv = [], bl = [], sl = [];
  for (let s = 0; s < S; s++) for (let k = 0; k < active; k++) {
    const br = Math.floor(rnd() ** 1.5 * B), rep = rnd() < 0.3 ? 2 : 1;   // second row: other investor type / board
    for (let r = 0; r < rep; r++) { const p = 100 + rnd() * 5000, l1 = rnd() * 1e4, l2 = rnd() * 1e4;
      d.push(s); b.push(br); bl.push(l1); sl.push(l2); bv.push(l1 * 100 * p); sv.push(l2 * 100 * p); rows++ }
  }
  tickers.push({ d: Int16Array.from(d), b: Int16Array.from(b), bv: Float64Array.from(bv), sv: Float64Array.from(sv), bl: Float64Array.from(bl), sl: Float64Array.from(sl) });
}
function metrics(x, D, N) {
  const n = new Float64Array(B), bv = new Float64Array(B), sv = new Float64Array(B), bl = new Float64Array(B), seen = new Uint8Array(B);
  const from = S - D;
  for (let i = 0; i < x.d.length; i++) if (x.d[i] >= from) { const k = x.b[i]; n[k] += x.bv[i] - x.sv[i]; bv[k] += x.bv[i]; sv[k] += x.sv[i]; bl[k] += x.bl[i]; seen[k] = 1 }
  const act = []; for (let k = 0; k < B; k++) if (seen[k]) act.push(k);
  act.sort((p, q) => n[q] - n[p] || p - q);
  let T = 0, pos = 0, pos2 = 0, buy2 = 0, sell2 = 0, BV = 0, SV = 0, buyers = 0, sellers = 0;
  for (const k of act) { T += bv[k]; BV += bv[k]; SV += sv[k]; buy2 += bv[k] ** 2; sell2 += sv[k] ** 2; if (n[k] > 0) { pos += n[k]; pos2 += n[k] ** 2; buyers++ } else if (n[k] < 0) sellers++ }
  let top = 0, vb = 0, vl = 0;
  for (let j = 0; j < Math.min(N, act.length); j++) { const k = act[j]; if (n[k] > 0) { top += n[k]; if (j < 3) { vb += bv[k]; vl += bl[k] } } }
  for (let j = act.length - 1; j >= Math.max(0, act.length - N); j--) { const k = act[j]; if (n[k] < 0) top += n[k] }
  return [top, 100 * top / T, pos2 / pos ** 2, buy2 / BV ** 2 - sell2 / SV ** 2, buyers / (buyers + sellers), vb / (100 * vl), act[0]];
}
function daily(x, D, N, top1) {   // daily top-N balance sign count and the top-1 buyer's buy days over D sessions
  const from = S - D, n = Array.from({ length: D }, () => new Float64Array(B)), v = new Float64Array(D);
  for (let i = 0; i < x.d.length; i++) if (x.d[i] >= from) { const s = x.d[i] - from; n[s][x.b[i]] += x.bv[i] - x.sv[i]; v[s] += x.bv[i] }
  let acc = 0, buyDays = 0;
  for (let s = 0; s < D; s++) { const a = Array.from(n[s]).filter(z => z !== 0).sort((p, q) => q - p);
    let bal = 0; for (let j = 0; j < Math.min(N, a.length); j++) if (a[j] > 0) bal += a[j];
    for (let j = a.length - 1; j >= Math.max(0, a.length - N); j--) if (a[j] < 0) bal += a[j];
    if (bal > 0) acc++; if (n[s][top1] > 0) buyDays++ }
  return [acc / D, buyDays / D];
}
const runs = [];
for (let rep = 0; rep < 5; rep++) {
  const t0 = performance.now(); let chk = 0;
  for (const x of tickers) { for (const D of [5, 10, 20]) for (const N of [3, 5]) { const m = metrics(x, D, N); chk += m[1] || 0 }
    const m20 = metrics(x, 20, 3); const dd = daily(x, 20, 3, m20[6]); chk += dd[0] }
  runs.push(performance.now() - t0); if (!isFinite(chk)) throw new Error('nan');
}
console.log(JSON.stringify({ rows, tickers: T, sessions: S, grid: 'D 5/10/20 x N 3/5 + daily(20,3)', ms: runs.map(r => Math.round(r)) }));
