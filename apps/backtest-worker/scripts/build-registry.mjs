/* Builds edge-bff/backtest/src/core/backtest-registry.json, the backtest's indicator registry (prompt "INDICATOR CATALOG"), from the two
   sources the Terminal already runs on: the 53-indicator registry generated from the workbook
   (edge-bff/terminal/src/data/indRegistry.json) and the executable defaults of the calculation module
   (edge-bff/terminal/src/calc/indicators.ts, DEFAULTS). Nothing is listed by hand:
   - a parameter is accepted only when the calculation module reads it (it has a default in DEFAULTS); the others are
     recorded under not_accepted with the reason (fixed in the workbook, or not read by the module, e.g. I37);
   - the default is the module's executable default (the workbook's proposed default is kept only when they differ);
   - visual settings (colour, width, panel, guides, tooltips) are left out; price_input says what "price" means in a
     condition (the close, or the volume for the volume-pane indicators), as the backtest page does.
   Run: npm run registry (writes) / npm run registry:check (fails when the committed file is stale). */
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..');
const REGISTRY_SRC = path.resolve(root, '../edge-bff/terminal/src/data/indRegistry.json');
const CALC_SRC = path.resolve(root, '../edge-bff/terminal/src/calc/indicators.ts');
// the artifact lives next to the pure modules the page and the worker share (edge-bff/backtest/src/core)
const OUT = path.resolve(root, '../edge-bff/backtest/src/core/backtest-registry.json');

const sha256 = file => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
/** Content hash of the two sources (no hand-kept version number); the worker recomputes it at start. */
export const registryVersion = () => crypto.createHash('sha256').update(fs.readFileSync(REGISTRY_SRC)).update(fs.readFileSync(CALC_SRC)).digest('hex').slice(0, 16);
const rel = file => path.relative(path.resolve(root, '../..'), file).split(path.sep).join('/');

export async function build() {
  const source = JSON.parse(fs.readFileSync(REGISTRY_SRC, 'utf8'));
  const { DEFAULTS, F } = await import(CALC_SRC);
  const indicators = source.map(r => {
    if (!F[r.key]) throw new Error(`${r.id} ${r.key}: no function in the calculation module`);
    const defaults = DEFAULTS[r.key] || {};
    const params = [], notAccepted = [];
    for (const p of r.params) {
      if (p.type === 'fixed') { notAccepted.push({ key: p.k, value: p.def, reason: 'fixed in the workbook' }); continue }
      if (!(p.k in defaults)) { notAccepted.push({ key: p.k, value: p.def, reason: 'not read by the calculation module' }); continue }
      const q = { key: p.k, type: p.type, default: defaults[p.k] };
      if (defaults[p.k] !== p.def) q.workbook_default = p.def;
      for (const [from, to] of [['min', 'min'], ['max', 'max'], ['step', 'step'], ['opts', 'options']]) if (p[from] !== undefined) q[to] = p[from];
      params.push(q);
    }
    const unknown = Object.keys(defaults).filter(k => !r.params.some(p => p.k === k));
    if (unknown.length) throw new Error(`${r.id}: module parameters missing from the registry: ${unknown}`);
    return {
      id: r.id, key: r.key, name: r.name, category: r.cat, function: `F.${r.key}`, inputs: r.req.split(''),
      price_input: r.zone === 'volume' ? 'volume' : 'close', outputs: r.outs.map(o => o.k), params,
      not_accepted: notAccepted, available_for_backtest: true,
    };
  });
  return {
    schema_version: 1,
    registry_version: registryVersion(),
    generated_by: 'apps/backtest-worker/scripts/build-registry.mjs',
    sources: [{ file: rel(REGISTRY_SRC), sha256: sha256(REGISTRY_SRC) }, { file: rel(CALC_SRC), sha256: sha256(CALC_SRC) }],
    indicators,
  };
}

export const serialize = doc => JSON.stringify(doc, null, 2) + '\n';

if (process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1])) {
  const text = serialize(await build());
  if (process.argv.includes('--check')) {
    const current = fs.existsSync(OUT) ? fs.readFileSync(OUT, 'utf8') : '';
    if (current !== text) { console.error(`${rel(OUT)} is stale: run npm run registry`); process.exit(1) }
    console.log(`${rel(OUT)} is current`);
  } else {
    fs.writeFileSync(OUT, text);
    console.log(`wrote ${rel(OUT)}`);
  }
}
