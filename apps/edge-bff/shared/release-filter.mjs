/* 3f (EXEC option A item 4; CONTRACT.md 8a "Lab code"): the page build keeps an item's definition only for the build it
   is meant for.

   - The public build (the one every visitor downloads, served without a session) keeps, in each registry below, the
     entries whose item is `released` in the release file, apps/edge-bff/catalog/releases.json.
   - The lab build (the admin's, which edge-bff serves only to the admin on the beta, under /<app>-app/lab/) keeps every
     entry.
   - An item the release file does not list is lab. A release file that is missing or cannot be read stops the build
     (fail closed), so a public bundle is never built from a guess.

   A lab item's formula lives in a module under apps/edge-bff/terminal/src/lab/ that only the alias '@edge-lab' reaches:
   the public build points the alias at src/lab/none.ts (labAlias below). LIVE_PROMOTION.md section 3 has the recipe for
   a lab item, and the tests that hold this are listed there. */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const EDGE_BFF = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
export const RELEASES = path.join(EDGE_BFF, 'catalog', 'releases.json');

const asList = (key) => ({ list: d => d[key], put: (d, l) => ({ ...d, [key]: l }) });
/** Every registry a page may import, by its path under apps/edge-bff, with the release kind of its entries and where
    the entries are. The ids of a file's entries are its items' ids. */
export const REGISTRIES = [
  { file: 'terminal/src/data/indRegistry.json', kind: 'indicator', list: d => d, put: (d, l) => l },
  { file: 'terminal/src/data/flowRegistry.json', kind: 'flow_indicator', ...asList('indicators') },
  { file: 'backtest/src/core/backtest-registry.json', kind: 'indicator', ...asList('indicators') },
  { file: 'backtest/src/core/candle-registry.json', kind: 'candle_pattern', ...asList('patterns') },
  { file: 'screener/src/core/screener-metrics.json', kind: 'screener_metric', ...asList('metrics') },
  { file: 'screener/src/core/presets.json', kind: 'screener_preset', ...asList('presets') },
  // the generated Screener registry holds three kinds: each list is filtered by its own kind
  { file: 'screener/src/core/screener-registry.json', lists: [['indicators', 'indicator'], ['flows', 'flow_indicator'], ['candles', 'candle_pattern']] },
];

/** The release stages: a Map of `${kind}\t${id}` -> 'lab' | 'released', read from the release file (or `file`). Throws
    when the file is missing, is not JSON or has no items list: the build stops. */
export function readStages(file = RELEASES) {
  let data;
  try {
    data = JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch (e) {
    throw new Error(`release filter: ${file} cannot be read (${e.message}); the page build needs apps/edge-bff/catalog/releases.json`);
  }
  if (!data || !Array.isArray(data.items)) throw new Error(`release filter: ${file} has no "items" list`);
  const stages = new Map();
  for (const it of data.items) {
    if (!it || typeof it.kind !== 'string' || typeof it.id !== 'string' || !['lab', 'released'].includes(it.stage))
      throw new Error(`release filter: ${file} has an entry without kind, id or a stage lab|released: ${JSON.stringify(it)}`);
    stages.set(`${it.kind}\t${it.id}`, it.stage);
  }
  return stages;
}

/** The registry document as the build keeps it: every entry for the lab build, the released ones for the public build
    (an unlisted id is lab). `extra` adds entries first, for the proof builds of the tests only. */
export function filtered(spec, doc, { lab, stages, extra = {} }) {
  const keep = kind => e => lab || (e && typeof e.id === 'string' && stages.get(`${kind}\t${e.id}`) === 'released');
  if (spec.lists) {
    let out = doc;
    for (const [key, kind] of spec.lists)
      if (Array.isArray(out[key])) out = { ...out, [key]: [...out[key], ...(extra[key] || [])].filter(keep(kind)) };
    return out;
  }
  const list = spec.list(doc);
  if (!Array.isArray(list)) throw new Error(`release filter: ${spec.file} has no list of entries where it is expected`);
  return spec.put(doc, [...list, ...(extra.entries || [])].filter(keep(spec.kind)));
}

/** The Vite plugin: it loads each registry filtered for the build (lab: every entry; else the released ones). `releases`
    and `extra` ({registry file: {entries | <list key>: [...]}}) are for the tests' proof builds. */
export function releaseFilter({ lab = false, releases = RELEASES, extra = {} } = {}) {
  let stages = null;
  const byPath = new Map(REGISTRIES.map(spec => [path.join(EDGE_BFF, spec.file), spec]));
  return {
    name: 'edge-release-filter',
    enforce: 'pre',
    buildStart() { stages = readStages(releases) },
    load(id) {
      const file = id.split('?')[0];
      const spec = byPath.get(file);
      if (!spec) return null;
      stages ??= readStages(releases);
      const doc = JSON.parse(fs.readFileSync(file, 'utf8'));
      return JSON.stringify(filtered(spec, doc, { lab, stages, extra: extra[spec.file] || {} }));
    },
  };
}

/** The alias '@edge-lab': the lab formulas (src/lab/index.ts) in the lab build, an empty module in the public one.
    `module` replaces the lab module for the tests' proof builds. */
export function labAlias({ lab = false, module } = {}) {
  const dir = path.join(EDGE_BFF, 'terminal', 'src', 'lab');
  return { '@edge-lab': module ?? path.join(dir, lab ? 'index.ts' : 'none.ts') };
}
