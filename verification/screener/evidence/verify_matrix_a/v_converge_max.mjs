// Verifier, full market: (A) bars to converge after cutting history at bar 1000 (tickers with >= 1500 bars), tolerance 1e-6 x S
// (S = median |value| of the full-history series), distribution across tickers; (B) latest-bar difference when only the last K bars are used.
import fs from 'node:fs';
const { F } = await import('/home/user/saniti/apps/edge-bff/terminal/src/calc/indicators.ts');
const dir = '/tmp/claude-0/-home-user-saniti/65bd49d0-9dca-5072-b7db-b62314cf2cd3/scratchpad/audit/verify_matrix_a/data_all/';
const bars = {};
for (const f of fs.readdirSync(dir).filter(f => f.startsWith('price_'))) for (const r of JSON.parse(fs.readFileSync(dir + f)).rows) (bars[r[0]] ||= []).push(r);
const toB = P => ({ T: P.map(r => r[1]), O: P.map(r => r[2]), H: P.map(r => r[3]), L: P.map(r => r[4]), C: P.map(r => r[5]), V: P.map(r => r[6]) });
const sl = (B, s) => ({ T: B.T.slice(s), O: B.O.slice(s), H: B.H.slice(s), L: B.L.slice(s), C: B.C.slice(s), V: B.V.slice(s) });
const KEYS = ['sma','ema','wma','hma','kama','macd','adx','aroon','supertrend','donchian','keltner','psar','rsi','stoch_rsi','stochastic','williams_r','roc','momentum','cci','cmo','tsi','trix','ultimate_osc','awesome_osc','ppo','bop','bollinger'];
const med = a => { let m = 0; for (const v of a) if (v !== null && Math.abs(v) > m) m = Math.abs(v); return m };
const conv = {}, tail = {}; const CUT = 1000, Ks = [250, 500, 1000];
const tickers = Object.keys(bars).filter(t => t !== 'IHSG');
for (const t of tickers) {
  const B = toB(bars[t]), N = B.C.length;
  const full = {}; for (const k of KEYS) full[k] = F[k](B, {});
  const S = {}; for (const k of KEYS) for (const [o, s] of Object.entries(full[k])) S[k + '.' + o] = Math.max(med(s), 1e-9);
  if (N >= 1500) {
    const Bc = sl(B, CUT);
    for (const k of KEYS) { const c = F[k](Bc, {}); for (const [o, s] of Object.entries(full[k])) {
      const cs = c[o]; let last = -1;
      for (let j = 0; j < cs.length; j++) { const a = s[CUT + j], b = cs[j]; if (b === null) continue; if (a === null || Math.abs(a - b) > 1e-6 * S[k + '.' + o]) last = j }
      const fvC = cs.findIndex(v => v !== null);
      (conv[k + '.' + o] ||= []).push([Math.max(last + 1, fvC), t]);
    } }
  }
  for (const K of Ks) if (N > K + 50) {
    const Bt = sl(B, N - K);
    for (const k of KEYS) { const c = F[k](Bt, {}); for (const [o, s] of Object.entries(full[k])) {
      const a = s[N - 1], b = c[o][K - 1]; const g = ((tail[k + '.' + o] ||= {})[K] ||= { n: 0, diff: 0, maxAbsOverS: 0, worst: '' });
      g.n++; if ((a === null) !== (b === null)) { g.diff++; continue } if (a === null) continue;
      const r = Math.abs(a - b) / S[k + '.' + o]; if (r > 1e-6) g.diff++; if (r > g.maxAbsOverS) { g.maxAbsOverS = r; g.worst = `${t} full=${a.toPrecision(8)} tail=${b.toPrecision(8)} absdiff=${Math.abs(a-b).toExponential(1)}` }
    } }
  }
}
const pct = (a, p) => a[Math.min(a.length - 1, Math.floor(p * a.length))];
console.log(`(A) cut at bar ${CUT}: bars after the cut until |cut-full| <= 1e-6 x max|full| (or first valid). Tickers with >=1500 bars: ${conv['sma.sma'].length}`);
for (const [k, arr] of Object.entries(conv)) { const v = arr.map(x => x[0]).sort((a, b) => a - b); const w = arr.reduce((m, x) => x[0] > m[0] ? x : m); console.log(`${k.padEnd(24)} min=${v[0]} median=${pct(v, .5)} p95=${pct(v, .95)} max=${w[0]} (${w[1]})`) }
console.log(`\n(B) latest bar (each ticker's last bar) computed on only the last K bars vs full history: count of tickers differing by > 1e-6 x max|full| (or null mismatch)`);
for (const [k, g] of Object.entries(tail)) console.log(`${k.padEnd(24)} ` + Ks.map(K => g[K] ? `K=${K}: ${g[K].diff}/${g[K].n} max|d|/S=${g[K].maxAbsOverS.toExponential(1)}${g[K].diff ? ' [' + g[K].worst + ']' : ''}` : '').join(' | '));
