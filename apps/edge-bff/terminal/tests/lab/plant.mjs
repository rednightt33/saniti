/* 3f proof builds (tests/test_3f_public_bundles.py; round 2 of its checker, 2026-11-21, BUN2-1/2/5, TRC2-1/3/6): plants
   fixture items into a COPY of apps/edge-bff (the folder given as the first argument, never the repository), on disk, the
   way a real item is written, so the pages are then built there with their own configurations, unchanged:

   - every registry the release filter knows (shared/release-filter.mjs REGISTRIES; each list of a file with several,
     and an object keyed by id) gets three fixture entries, each with a marker of its own: one released in the copy's
     release file (R), one at the lab stage (L) and one the release file does not list (U, so lab too);
   - shared/proof-plant.ts imports every one of those files, and every entry of every page imports it first (each
     page's index.html script and each Web Worker it starts: shared/import-walk.mjs pageEntries), so each bundle a page
     build makes carries every registry: a bundle built without the filter carries the L and U markers, and the R
     markers show the plant reached the bundle at all;
   - the lab module (terminal/src/lab/index.ts, which only the alias '@edge-lab' of a lab build reaches) gets a formula
     marker.

   Prints {markers: {<part>: {R, L, U}}, formula, entries} as JSON. */
import fs from 'node:fs';
import path from 'node:path';

const edge = path.resolve(process.argv[2] ?? '');
if (!fs.existsSync(path.join(edge, 'shared', 'release-filter.mjs')) || path.resolve(edge) === path.resolve(path.dirname(new URL(import.meta.url).pathname), '../../..'))
  throw new Error('plant.mjs <copy of apps/edge-bff>: a copy, never the repository itself');
const { REGISTRIES, RELEASES } = await import(path.join(edge, 'shared', 'release-filter.mjs'));
const { pages, pageEntries } = await import(path.join(edge, 'shared', 'import-walk.mjs'));
const { labAlias } = await import(path.join(edge, 'shared', 'release-filter.mjs'));

const PREFIX = { indicator: 'I', flow_indicator: 'FL', candle_pattern: 'CP', screener_metric: 'M', screener_preset: 'P' };
const STAGE = { R: 'released', L: 'lab' };                         // U: not in the release file
const markers = {}, items = new Map();
const idOf = (kind, s) => {
  if (!PREFIX[kind]) throw new Error(`plant.mjs: no fixture id for the kind ${kind}; add one to PREFIX`);
  return `${PREFIX[kind]}_PROOF_${s}`;
};

for (const spec of REGISTRIES) {
  const file = path.join(edge, spec.file);
  let doc = JSON.parse(fs.readFileSync(file, 'utf8'));
  const parts = spec.keyed ? [[spec.keyed, spec.kind]] : spec.lists ?? [[null, spec.kind]];
  for (const [key, kind] of parts) {
    const part = `${path.basename(spec.file, '.json')}${key ? `.${key}` : ''}`;
    markers[part] = {};
    for (const s of ['R', 'L', 'U']) {
      const id = idOf(kind, s), marker = `PROOF7F3A-${part}-${s}`;
      markers[part][s] = marker;
      if (spec.keyed) doc[spec.keyed] = { ...doc[spec.keyed], [id]: { proof: marker } };
      else if (key) doc[key] = [...doc[key], { id, proof: marker }];
      else doc = spec.put(doc, [...spec.list(doc), { id, proof: marker }]);
      if (STAGE[s]) items.set(`${kind}\t${id}`, { kind, id, stage: STAGE[s] });
    }
  }
  fs.writeFileSync(file, JSON.stringify(doc));
}

const releases = JSON.parse(fs.readFileSync(RELEASES, 'utf8'));
releases.items = [...releases.items, ...items.values()];
fs.writeFileSync(RELEASES, JSON.stringify(releases, null, 1));

const plant = path.join(edge, 'shared', 'proof-plant.ts');
fs.writeFileSync(plant, REGISTRIES.map((spec, k) => `import r${k} from '../${spec.file}';\n`).join('')
  + `(globalThis as any).__edge_proof_7f3a__ = [${REGISTRIES.map((_, k) => `r${k}`).join(', ')}];\n`);

const entries = [];
for (const page of pages(edge))
  for (const entry of pageEntries(page, { edge, aliases: labAlias({ lab: false }) })) {
    const file = path.join(edge, entry);
    let rel = path.relative(path.dirname(file), plant).split(path.sep).join('/');
    if (!rel.startsWith('.')) rel = `./${rel}`;
    fs.writeFileSync(file, `import '${rel}';\n` + fs.readFileSync(file, 'utf8'));
    entries.push(entry);
  }

const formula = 'PROOF7F3A-FORMULA';
const lab = labAlias({ lab: true })['@edge-lab'];
fs.appendFileSync(lab, `\n(globalThis as any).__edge_lab_proof_7f3a__ = '${formula}';\n`);

process.stdout.write(JSON.stringify({ markers, formula, entries }));
