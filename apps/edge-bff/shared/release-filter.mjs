/* 3f (EXEC option A item 4; CONTRACT.md 8 "Lab code"): the page build keeps an item's definition only for the build it
   is meant for.

   - The public build (the one every visitor downloads, served without a session) keeps, in each registry below, the
     entries whose item is `released` or `preview` in the release file, apps/edge-bff/catalog/releases.json. A preview
     entry carries `release: 'preview'` (the user 2026-11-23, EXEC-MU-ACCOUNTS "A preview release stage": on both sites,
     held only by the principals whose grants name it, the admin's `*`), so a page that lists entries from its registry
     leaves one out for a principal the catalog does not list it for, rather than show it locked (the Terminal's menu,
     the Backtest's line choices). Its definition and formula are public; a formula that must stay out of the files a
     visitor downloads stays lab.
   - The lab build (the admin's, which edge-bff serves only to the admin on the beta, under /<app>-app/lab/) keeps every
     entry, a preview one with the same mark.
   - An item the release file does not list is lab. A release file that is missing or cannot be read stops the build
     (fail closed), so a public bundle is never built from a guess.

   A lab item's formula lives in a module under apps/edge-bff/terminal/src/lab/ that only the alias '@edge-lab' reaches:
   the public build points the alias at src/lab/none.ts (labAlias below). LIVE_PROMOTION.md section 3 lists the tests
   that hold this; INDICATOR_BETA_TO_LIVE.md is the checklist of a lab indicator (tests/test_releases.py LAB_KIND_HELD
   names the kinds that may not be lab yet). */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const EDGE_BFF = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
export const RELEASES = path.join(EDGE_BFF, 'catalog', 'releases.json');

const asList = (key) => ({ list: d => d[key], put: (d, l) => ({ ...d, [key]: l }) });
/** Every file a page may import that names items, by its path under apps/edge-bff: a list of entries with their ids
    (`list`, or several lists with their kinds), or an object keyed by item id (`keyed`). terminal/tests/lab/coverage.test.mjs
    derives the files a public entry reaches that name a release-file id, and fails on one this list does not cover.
    Defence in depth (ERRORS M523, BUN2-7): candle-registry, screener-metrics, presets and screener-registry are reached by
    no public page entry today (the workers and the generators read them); they stay listed so that a page that starts
    importing one is filtered from its first build, and terminal/tests/lab/plant.mjs plants and imports every file listed
    here, so the proof builds hold these four too. */
export const REGISTRIES = [
  { file: 'terminal/src/data/indRegistry.json', kind: 'indicator', list: d => d, put: (d, l) => l },
  { file: 'terminal/src/data/flowRegistry.json', kind: 'flow_indicator', ...asList('indicators') },
  { file: 'backtest/src/core/backtest-registry.json', kind: 'indicator', ...asList('indicators') },
  { file: 'backtest/src/core/candle-registry.json', kind: 'candle_pattern', ...asList('patterns') },
  { file: 'screener/src/core/screener-metrics.json', kind: 'screener_metric', ...asList('metrics') },
  { file: 'screener/src/core/presets.json', kind: 'screener_preset', ...asList('presets') },
  // the generated Screener registry holds three kinds: each list is filtered by its own kind
  { file: 'screener/src/core/screener-registry.json', lists: [['indicators', 'indicator'], ['flows', 'flow_indicator'], ['candles', 'candle_pattern']] },
  // the Backtest page's comparison lag, keyed by indicator id (checker L3, 2026-11-21)
  { file: 'backtest/src/core/compare-lag.json', kind: 'indicator', keyed: 'price_compare_lag' },
];

/** The release stages of an item (app/releases.py STAGES). */
export const STAGES = ['lab', 'preview', 'released'];
/** The stages a public build keeps: every other (lab, or an id the release file does not list) is left out. */
export const PUBLIC_STAGES = ['preview', 'released'];
export const PREVIEW = 'preview';

/** The release stages: a Map of `${kind}\t${id}` -> 'lab' | 'preview' | 'released', read from the release file (or
    `file`). Throws when the file is missing, is not JSON, has no items list or an entry of another stage: the build
    stops. */
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
    if (!it || typeof it.kind !== 'string' || typeof it.id !== 'string' || !STAGES.includes(it.stage))
      throw new Error(`release filter: ${file} has an entry without kind, id or a stage ${STAGES.join('|')}: ${JSON.stringify(it)}`);
    stages.set(`${it.kind}\t${it.id}`, it.stage);
  }
  return stages;
}

/** The registry document as the build keeps it: every entry for the lab build, the released and preview ones for the
    public build (an unlisted id is lab); an entry of a list whose item is at preview carries `release: 'preview'` in
    both builds (an object keyed by id keeps its values as they are). Each part the spec names must be there in its
    shape, a list (`list`, each of `lists`) or an object keyed by id (`keyed`), else the build stops: a part renamed or
    rewritten would pass through unfiltered (3f checker B4, BUN2-4, CS-4). terminal/tests/lab/coverage.test.mjs checks
    that no other part of a registry file names an item. */
export function filtered(spec, doc, { lab, stages }) {
  const stage = (kind, e) => e && typeof e.id === 'string' ? stages.get(`${kind}\t${e.id}`) : undefined;
  const keep = kind => e => lab || PUBLIC_STAGES.includes(stage(kind, e));
  const mark = kind => e => stage(kind, e) === PREVIEW ? { ...e, release: PREVIEW } : e;
  if (spec.keyed) {
    const by = doc[spec.keyed];
    if (!by || typeof by !== 'object' || Array.isArray(by)) throw new Error(`release filter: ${spec.file} has no object "${spec.keyed}"`);
    return { ...doc, [spec.keyed]: Object.fromEntries(Object.entries(by).filter(([id]) => keep(spec.kind)({ id }))) };
  }
  if (spec.lists) {
    let out = doc;
    for (const [key, kind] of spec.lists) {
      if (!Array.isArray(out?.[key])) throw new Error(`release filter: ${spec.file} has no list "${key}" (the entries of kind ${kind})`);
      out = { ...out, [key]: out[key].filter(keep(kind)).map(mark(kind)) };
    }
    return out;
  }
  const list = spec.list(doc);
  if (!Array.isArray(list)) throw new Error(`release filter: ${spec.file} has no list of entries where it is expected`);
  return spec.put(doc, list.filter(keep(spec.kind)).map(mark(spec.kind)));
}

/** The Vite plugin: it loads each registry filtered for the build (lab: every entry; else the released and preview
    ones). Every page
    build puts it in `plugins` and in `worker.plugins` alike: Vite builds a Web Worker's bundle with the worker's plugins
    only (checker L1, 2026-11-21: the Terminal's worker had the whole Flow registry). tests/test_3f_public_bundles.py
    builds every page with its own configuration on a copy of apps/edge-bff whose registries hold fixture items, and
    finds each one only where it belongs. */
export function releaseFilter({ lab = false } = {}) {
  let stages = null;
  const byPath = new Map(REGISTRIES.map(spec => [path.join(EDGE_BFF, spec.file), spec]));
  return {
    name: 'edge-release-filter',
    enforce: 'pre',
    buildStart() { stages = readStages() },
    load(id) {
      const file = id.split('?')[0];
      const spec = byPath.get(file);
      if (!spec) return null;
      stages ??= readStages();
      const doc = JSON.parse(fs.readFileSync(file, 'utf8'));
      return JSON.stringify(filtered(spec, doc, { lab, stages }));
    },
  };
}

/** L11 (3f checker; built 2026-11-23 when the lab item guard was lifted): a file of a fixed name that only a lab build
    holds, at <base>assets/lab-probe.svg (a .js file would read as a bundle to the proof builds). A hashed lab file's name cannot be known from outside once the public and lab
    builds differ, so a smoke that asks for the public build's names under /lab/ passes by absence; this one name
    proves the lab build is not served (the live smoke, verification/edge_multiuser/live_smoke/http_smoke.py) and is
    served to the admin on the beta (tests/test_3f_lab_pages.py). An empty image, not a script: it holds no code, and
    the bundle scans of tests/test_3f_public_bundles.py read the builds' .js files. */
export const LAB_PROBE = 'lab-probe.svg';
export function labProbe({ lab = false } = {}) {
  return {
    name: 'edge-lab-probe',
    generateBundle() {
      if (lab) this.emitFile({ type: 'asset', fileName: `assets/${LAB_PROBE}`,
                               source: '<svg xmlns="http://www.w3.org/2000/svg"><!-- EDGE lab build probe: only the lab build holds this file --></svg>\n' });
    },
  };
}

/** The alias '@edge-lab': the lab formulas (src/lab/index.ts) in the lab build, an empty module in the public one. */
export function labAlias({ lab = false } = {}) {
  const dir = path.join(EDGE_BFF, 'terminal', 'src', 'lab');
  return { '@edge-lab': path.join(dir, lab ? 'index.ts' : 'none.ts') };
}
