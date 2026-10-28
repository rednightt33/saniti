import fs from 'node:fs'; import vm from 'node:vm';
const lines = fs.readFileSync('/root/.claude/uploads/65bd49d0-9dca-5072-b7db-b62314cf2cd3/9c79bf9c-screener_EDGE_layout.html', 'utf8').split('\n');
// lines 562..1115 (data layer, catalog, engine, evaluation, presets); stop before the UI section at 1116
const code = lines.slice(561, 1115).join('\n') + `
globalThis.__R = (() => {
  const groups = {}; for(const [k, I] of Object.entries(CAT)) (groups[I.g] ||= []).push(k);
  const rows = Object.entries(CAT).map(([k, I]) => ({key:k, g:I.g, label:I.label, unit:I.unit ?? '', params:I.params.map(p => p.k + '=' + p.def + (p.opts ? '{' + p.opts.join('/') + '}' : '')).join(', '),
    ops:I.ops.map(o => I.custom?.[o] ? o + '[' + I.custom[o].kind + ']' : o).join(' '), def:JSON.stringify(I.def), kind:I.last ? 'last-only' : 'series'}));
  const presets = PRESETS.map(p => ({id:p.id, cat:p.cat, logic:p.logic, universe:p.universe || null, sort:p.sort || null, conds:p.conds.map(([key, op, prm, v, v2, n]) => { const I = CAT[key], P = {}; I.params.forEach(x => P[x.k] = x.def); Object.assign(P, prm); return {key, op, p:P, v: v ?? I.def.v, v2: v2 ?? I.def.v2, n: n ?? I.def.n, kind: I.custom?.[op]?.kind || 'value'} })}));
  return {groups:Object.fromEntries(Object.entries(groups).map(([g, a]) => [g, a.length])), total:Object.keys(CAT).length, rows, presets, BANDAR:{...BANDAR}, tickers:TICKERS.length};
})();`;
const ctx = vm.createContext({}); vm.runInContext(code, ctx);
const R = JSON.parse(JSON.stringify(ctx.__R));
fs.writeFileSync(process.argv[2] + '/catalog.json', JSON.stringify(R, null, 1));
console.log('groups', R.groups, 'total', R.total, 'tickers', R.tickers, 'BANDAR', R.BANDAR, 'presets', R.presets.length);
