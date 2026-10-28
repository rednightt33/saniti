import fs from 'node:fs';
const { F } = await import('/home/user/saniti/apps/edge-bff/terminal/src/calc/indicators.ts');
const D = '/tmp/claude-0/-home-user-saniti/65bd49d0-9dca-5072-b7db-b62314cf2cd3/scratchpad/audit/verify_matrix_a/data/';
for (const t of ['BBRI', 'BLTA', 'GOTO']) {
  const P = JSON.parse(fs.readFileSync(D + t + '.json')).price.rows, f1 = JSON.parse(fs.readFileSync(D + t + '.f01.json'));
  const B = { T: P.map(r => r[0]), O: P.map(r => r[1]), H: P.map(r => r[2]), L: P.map(r => r[3]), C: P.map(r => r[4]), V: P.map(r => r[5]) };
  const pos = new Map(P.map((r, i) => [r[0], i]));
  for (const [n, col] of [[5, 1], [20, 2], [60, 3]]) { const roc = F.roc(B, { length: n }).roc; let nm = 0, mx = 0, k = 0;
    for (const r of f1) { const i = pos.get(r[0]); if (i === undefined) { nm++; continue } const a = roc[i], b = r[col]; if ((a === null) !== (b === null)) { nm++; continue } if (a === null) continue; k++; mx = Math.max(mx, Math.abs(a - b)) }
    console.log(t, `ROC${n} vs return_${n}d_pct: rows=${f1.length} n=${k} nullMismatch=${nm} maxAbs=${mx.toExponential(2)}`) }
}
