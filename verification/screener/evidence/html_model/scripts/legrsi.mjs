import fs from 'node:fs'; import vm from 'node:vm';
import { F } from '/home/user/saniti/apps/edge-bff/terminal/src/calc/indicators.ts';
const lines = fs.readFileSync('/root/.claude/uploads/65bd49d0-9dca-5072-b7db-b62314cf2cd3/9c79bf9c-screener_EDGE_layout.html', 'utf8').split('\n');
const code = lines.slice(749, 776).join('\n') + '\nglobalThis.__X = {RSI, SUPERTREND};';
for(const tk of ['DADA','GOTO','BBCA','MTDL','ADRO']){
  const rows = fs.readFileSync('../data/' + tk + '.txt', 'utf8').split('\n').filter(l => /^\d{4}-/.test(l)).map(l => l.split(','));
  const d = rows.map(r => r[0]), o = rows.map(r => +r[1]), h = rows.map(r => +r[2]), l = rows.map(r => +r[3]), c = rows.map(r => +r[4]), v = rows.map(r => +r[5]);
  const ctx = vm.createContext({N:c.length}); vm.runInContext(code, ctx);
  const a = ctx.__X.RSI(c, 14), b = F.rsi({O:o,H:h,L:l,C:c,V:v}, {length:14}).rsi;
  let n = 0, ex = null; for(let i = 0; i < c.length; i++){ const x = a[i], y = b[i]; if(Number.isFinite(x) !== Number.isFinite(y) || (Number.isFinite(x) && Math.abs(x - y) > 1e-6)){ n++; ex ??= [d[i], x, y] } }
  const s1 = Array.from(ctx.__X.SUPERTREND({tk, o, h, l, c, v}, 10, 3)), s2 = F.supertrend({O:o,H:h,L:l,C:c,V:v}, {}).direction; let m = 0; for(let i = 30; i < c.length; i++) if(s1[i] !== s2[i]) m++;
  console.log(tk, 'legacy RSI14 bars differing (full history):', n, ex ? JSON.stringify(ex) : '', '| legacy SUPERTREND dir differing bars after bar 30:', m);
}
