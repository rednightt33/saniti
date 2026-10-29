// Verifier: flat-stretch artefacts (running-sum residue) market-wide: CMO non-null on a flat 14-bar window; UO outside [0,100];
// RSI on flat 14-change windows that are not 0; Bollinger bands != basis on flat 20-bar windows. Full history, defaults.
import fs from 'node:fs';
const { F } = await import('/home/user/saniti/apps/edge-bff/terminal/src/calc/indicators.ts');
const dir = '/tmp/claude-0/-home-user-saniti/65bd49d0-9dca-5072-b7db-b62314cf2cd3/scratchpad/audit/verify_matrix_a/data_all/';
const bars = {};
for (const f of fs.readdirSync(dir).filter(f => f.startsWith('price_'))) for (const r of JSON.parse(fs.readFileSync(dir + f)).rows) (bars[r[0]] ||= []).push(r);
const toB = P => ({ T: P.map(r => r[1]), O: P.map(r => r[2]), H: P.map(r => r[3]), L: P.map(r => r[4]), C: P.map(r => r[5]), V: P.map(r => r[6]) });
const st = { cmoFlat: 0, cmoFlatNonNull: 0, cmoEx: [], uoOut: 0, uoEx: [], uoFlat: 0, uoFlatNonZero: 0, rsiFlat: 0, rsiFlatNonZero: 0, rsiEx: [], bbFlat: 0, bbFlatWide: 0, last: { cmo: 0, uo: 0, rsi: 0 }, tick: new Set() };
for (const [t, P] of Object.entries(bars)) {
  if (t === 'IHSG') continue;
  const B = toB(P), N = B.C.length, cmo = F.cmo(B, {}).cmo, uo = F.ultimate_osc(B, {}).uo, rsi = F.rsi(B, {}).rsi, bb = F.bollinger(B, {});
  const flatC = (i, n) => { for (let j = i - n; j < i; j++) if (B.C[j] !== B.C[j + 1]) return false; return true };   // n changes = 0
  const flatHLC = (i, n) => { for (let j = i - n + 1; j <= i; j++) if (B.H[j] !== B.C[i] || B.L[j] !== B.C[i] || B.C[j] !== B.C[i]) return false; return B.C[i - n] === B.C[i] };
  for (let i = 30; i < N; i++) {
    if (flatC(i, 14)) { st.cmoFlat++; if (cmo[i] !== null) { st.cmoFlatNonNull++; st.tick.add(t); if (st.cmoEx.length < 5) st.cmoEx.push(`${t} ${B.T[i]} cmo=${cmo[i].toFixed(2)}`); if (i === N - 1) st.last.cmo++ }
      st.rsiFlat++; if (rsi[i] !== 0) { st.rsiFlatNonZero++; if (st.rsiEx.length < 5) st.rsiEx.push(`${t} ${B.T[i]} rsi=${rsi[i]?.toFixed(2)}`); if (i === N - 1) st.last.rsi++ } }
    if (uo[i] !== null && (uo[i] < -1e-9 || uo[i] > 100 + 1e-9)) { st.uoOut++; if (st.uoEx.length < 5) st.uoEx.push(`${t} ${B.T[i]} uo=${uo[i].toFixed(2)}`) }
    if (i >= 28 && flatHLC(i, 28)) { st.uoFlat++; if (uo[i] !== 0) { st.uoFlatNonZero++; if (i === N - 1) st.last.uo++ } }
    if (flatC(i, 19)) { st.bbFlat++; if (bb.upper[i] !== null && bb.upper[i] - bb.basis[i] > 1e-9 * bb.basis[i]) st.bbFlatWide++ }
  }
}
st.tick = st.tick.size;
console.log(JSON.stringify(st, null, 1));
