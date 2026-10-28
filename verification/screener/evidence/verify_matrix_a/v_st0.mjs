// Verifier: Supertrend factor = 0 edge case: how often prevSt equals both final bands (ambiguous state) on real bars.
import fs from 'node:fs';
const { F } = await import('/home/user/saniti/apps/edge-bff/terminal/src/calc/indicators.ts');
const D = '/tmp/claude-0/-home-user-saniti/65bd49d0-9dca-5072-b7db-b62314cf2cd3/scratchpad/audit/verify_matrix_a/data/';
for (const t of ['BBRI', 'BLTA', 'ASPR']) {
  const P = JSON.parse(fs.readFileSync(D + t + '.json')).price.rows;
  const B = { O: P.map(r => r[1]), H: P.map(r => r[2]), L: P.map(r => r[3]), C: P.map(r => r[4]), V: P.map(r => r[5]) };
  for (const f of [0, 3]) { const o = F.supertrend(B, { factor: f }); let flips = 0, up = 0, n = 0, lineAboveCloseInUp = 0;
    for (let i = 1; i < P.length; i++) { const d = o.direction[i]; if (d === null) continue; n++; if (d === 1) { up++; if (o.supertrend[i] > B.C[i]) lineAboveCloseInUp++ } if (o.direction[i - 1] !== null && d !== o.direction[i - 1]) flips++ }
    console.log(t, 'factor', f, 'bars', n, 'up', up, 'flips', flips, 'up-trend bars with line above close', lineAboveCloseInUp) }
}
