import fs from 'node:fs';
const { F } = await import('/home/user/saniti/apps/edge-bff/terminal/src/calc/indicators.ts');
const d = JSON.parse(fs.readFileSync(new URL('./data/BEKS.ts.json', import.meta.url)));
const B = d.bars, cut = 1000, Bc = Object.fromEntries(Object.entries(B).map(([k, v]) => [k, v.slice(cut)]));
for (const [k, o] of [['ultimate_osc','uo'],['bollinger','upper'],['rsi','rsi'],['adx','adx'],['cmo','cmo']]) {
  const a = F[k](B, {})[o].slice(cut), b = F[k](Bc, {})[o];
  let worst = 0, at = -1, nm = 0;
  for (let i = 0; i < a.length; i++) { if ((a[i] === null) !== (b[i] === null)) { nm++; continue } if (a[i] === null) continue; const x = Math.abs(a[i] - b[i]); if (x > worst && i > 60) { worst = x; at = i } }
  console.log(k, o, 'max abs diff after bar 60:', worst, 'at', at, B.T[cut + at], 'full', a[at], 'cut', b[at], 'nullMismatch', nm);
}
console.log('BEKS close sample', B.C.slice(cut, cut + 5), 'distinct closes in cut window', new Set(B.C.slice(cut)).size);
