import fs from 'node:fs'; import vm from 'node:vm';
import { F } from '/home/user/saniti/apps/edge-bff/terminal/src/calc/indicators.ts';
const HTML = '/root/.claude/uploads/65bd49d0-9dca-5072-b7db-b62314cf2cd3/9c79bf9c-screener_EDGE_layout.html';
const DATA = '/tmp/claude-0/-home-user-saniti/65bd49d0-9dca-5072-b7db-b62314cf2cd3/scratchpad/audit/html_model/data/';
const lines = fs.readFileSync(HTML, 'utf8').split('\n');
const code = lines.slice(749, 776).join('\n') + '\n' + lines.slice(865, 968).join('\n') + '\nglobalThis.__X = {XI, SUPERTREND, RSI};';
const [tk, key, pk, fk] = process.argv.slice(2);
const rows = fs.readFileSync(DATA + tk + '.txt', 'utf8').split('\n').filter(l => /^\d{4}-/.test(l)).map(l => l.split(','));
const d = rows.map(r => r[0]), o = rows.map(r => +r[1]), h = rows.map(r => +r[2]), l = rows.map(r => +r[3]), c = rows.map(r => +r[4]), v = rows.map(r => +r[5]);
const N = c.length, ctx = vm.createContext({N, DAYS:d}); vm.runInContext(code, ctx); const X = ctx.__X;
const t = {tk, o, h, l, c, v, tp:c.map((x, i) => (x + h[i] + l[i]) / 3)}, B = {O:o, H:h, L:l, C:c, V:v, T:d};
const P = JSON.parse(process.argv[6] || '{}');
const a = X.XI[key](t, P)[pk], b = F[key](B, P)[fk]; let shown = 0, cnt = 0;
for(let i = 0; i < N; i++){ const x = a[i], y = b[i]; const fx = Number.isFinite(x), fy = Number.isFinite(y); if(!fx && !fy) continue; if(fx !== fy || Math.abs(x - y) > 1e-9 * Math.max(1, Math.abs(y))){ cnt++; if(shown < 8 && i > N - 400){ shown++; console.log(i, d[i], 'proto', x, 'F', y, 'c', c.slice(i-3,i+1).join('/'), 'h', h[i], 'l', l[i], 'v', v[i]) } } }
console.log('total differing bars (full history):', cnt, 'of', N);
