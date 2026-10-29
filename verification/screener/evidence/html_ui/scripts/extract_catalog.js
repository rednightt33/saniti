// Runs the prototype's pure data/catalog section (lines 563-1115) plus toBacktest in an isolated vm context
// and prints the catalog inventory as JSON. No DOM, no network.
const fs = require('fs'), vm = require('vm');
const src = fs.readFileSync(process.argv[2], 'utf8').split('\n');
const L = (a, b) => src.slice(a - 1, b).join('\n');
const tb = src.findIndex(l => l.startsWith('function toBacktest(c){')) + 1;
let end = tb; while(!src[end - 1].startsWith('}')) end++;
const code = L(563, 1115) + '\n' + L(tb, end) + `
const OUT = {};
OUT.catCount = Object.keys(CAT).length;
OUT.byGroup = {}; for(const [k,I] of Object.entries(CAT)) (OUT.byGroup[I.g] ??= []).push(k);
OUT.cat = Object.fromEntries(Object.entries(CAT).map(([k,I]) => [k, {g:I.g, label:I.label, short:I.short, unit:I.unit, params:I.params.map(p=>({k:p.k, def:p.def, opts:p.opts})), ops:I.ops, custom:Object.fromEntries(Object.entries(I.custom||{}).map(([o,c])=>[o,{label:c.label, kind:c.kind}])), def:I.def, cross:!!I.cross, last:!!I.last, overlay:!!I.overlay}]));
OUT.metricFilterOpts = GROUPS.map(g => [g, Object.entries(CAT).filter(([, I]) => I.g === g && !I.custom && I.ops.includes('gt')).map(([k]) => k)]);
OUT.presets = PRESETS.map(p => ({id:p.id, cat:p.cat, name:p.name, conds:p.conds, universe:p.universe, sort:p.sort}));
OUT.presetCondKeys = [...new Set(PRESETS.flatMap(p => p.conds.map(c => c[0])))];
// toBacktest coverage over every (key, op) pair with default params
const mk = (key, op) => { const I = CAT[key], p = {}; I.params.forEach(x => p[x.k] = x.def); return {key, op, p, v: I.def.v ?? 0, v2: I.def.v2 ?? '', n: I.def.n ?? 5} };
OUT.toBacktest = []; for(const [k,I] of Object.entries(CAT)) for(const op of I.ops){ const r = toBacktest(mk(k, op)); if(r) OUT.toBacktest.push([k, op, r]) }
OUT.N = N; OUT.days = [DAYS[0], DAYS[N-1]]; OUT.tickers = TICKERS.length;
JSON.stringify(OUT);
`;
const ctx = vm.createContext({Math, Date, JSON, Object, Array, Float64Array, Int8Array, Uint8Array, Set, Map, String, Number, isFinite, isNaN, NaN, Infinity});
const res = vm.runInContext(code, ctx, {timeout: 60000});
fs.writeFileSync(process.argv[3], JSON.stringify(JSON.parse(res), null, 1));
console.log('ok');
