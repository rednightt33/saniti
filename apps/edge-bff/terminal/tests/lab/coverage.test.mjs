/* 3f (checker L3 and round 2 of the checker, 2026-11-21; CONTRACT.md 8 "Lab code"): the release filter covers every file a
   public entry reaches that could name an item, and each part of such a file that names one.

   - The entries are derived, never listed: each page's index.html script and each Web Worker it starts
     (shared/import-walk.mjs pages, pageEntries; round 2 BUN2-3: a hand-kept list missed a new worker).
   - Every JSON module a public entry reaches (type imports included) is a registry the filter loads
     (shared/release-filter.mjs REGISTRIES), or is named in NAMES_NO_ITEM with why it names no item (round 2 BUN2-5: a
     new file naming only ids the release file does not list yet was seen by no test). The proof builds
     (tests/test_3f_public_bundles.py) show that every page applies the filter to every registry.
   - Each registry, filtered for a public build with no item released, names none of the ids of its own kinds (those it
     holds and those the release file lists), as an entry's `id` or as an object key, anywhere in what is left (round 2
     BUN2-4: a second map or list a spec does not filter). A part a spec names that is missing stops the build
     (release-filter.mjs filtered). */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { ROOT, pageEntries, pages, reachable } from '../../../shared/import-walk.mjs';
import { EDGE_BFF, REGISTRIES, RELEASES, filtered, labAlias, readStages } from '../../../shared/release-filter.mjs';

/** JSON files a public entry reaches that are not registries, each with why it names no item (none today). */
const NAMES_NO_ITEM = {};
const ITEMS = JSON.parse(fs.readFileSync(RELEASES, 'utf8')).items;
const COVERED = new Set(REGISTRIES.map(r => r.file));
const entriesOf = edge => pages(edge).flatMap(page => pageEntries(page, { edge, aliases: labAlias({ lab: false }) }));
const ENTRIES = entriesOf(EDGE_BFF);

/** The ids a JSON document names as an entry's id or as an object key, anywhere in it, of the set `ids`. */
function namedIds(doc, ids) {
  const found = new Set();
  const walk = x => {
    if (Array.isArray(x)) { x.forEach(walk); return }
    if (!x || typeof x !== 'object') return;
    if (typeof x.id === 'string' && ids.has(x.id)) found.add(x.id);
    for (const [k, v] of Object.entries(x)) { if (ids.has(k)) found.add(k); walk(v) }
  };
  walk(doc);
  return found;
}

/** The JSON modules the entries (under `edge`) reach, as paths under `edge`. */
function reachedJson(entries, edge = EDGE_BFF) {
  const out = new Set();
  for (const entry of entries)
    for (const mod of reachable(path.join(edge, entry), { aliases: labAlias({ lab: false }) }))
      if (mod.endsWith('.json')) out.add(path.relative(edge, path.join(ROOT, mod)));
  return [...out].sort();
}

const kindsOf = spec => [...new Set([...(spec.keyedParts ?? []).flatMap(([, kinds]) => kinds), ...(spec.lists ?? []).map(([, kind]) => kind),
  ...(spec.kind ? [spec.kind] : [])])];
/** The ids a registry holds in the parts its spec filters. */
const heldIds = (spec, doc) => (spec.keyed ? Object.keys(doc[spec.keyed])
  : [...(spec.keyedParts ?? []).flatMap(([key]) => Object.keys(doc[key])),
     ...(spec.lists ?? []).flatMap(([key, , field = 'id']) => doc[key].map(e => e?.[field])),
     ...(!spec.keyedParts && !spec.lists ? spec.list(doc).map(e => e?.id) : [])]).filter(x => typeof x === 'string');
/** The reference fields a JSON file may name an item by, beside `id` and an object key (check of steps 2-3, P4). */
const REFERENCE_FIELDS = ['indicator', 'metric', 'pattern'];
/** The ids a JSON document names by key, id or a reference field (namedIds, plus a string under REFERENCE_FIELDS). */
function referencedIds(doc, ids) {
  const found = namedIds(doc, ids);
  const walk = x => {
    if (Array.isArray(x)) { x.forEach(walk); return }
    if (!x || typeof x !== 'object') return;
    for (const f of REFERENCE_FIELDS) if (typeof x[f] === 'string' && ids.has(x[f])) found.add(x[f]);
    Object.values(x).forEach(walk);
  };
  walk(doc);
  return found;
}
/** What a public build with no item released keeps of a registry that names an item of its own kinds. */
function leftOver(spec, doc, items = ITEMS) {
  const ids = new Set([...items.filter(it => kindsOf(spec).includes(it.kind)).map(it => it.id), ...heldIds(spec, doc)]);
  return [...namedIds(filtered(spec, doc, { lab: false, stages: new Map() }), ids)];
}

describe('3f: the release filter covers every file a public entry reaches that could name an item', () => {
  it('the entries are each page\'s script and each Web Worker it starts', () => {
    expect(pages()).toEqual(expect.arrayContaining(['backtest', 'screener', 'terminal']));
    for (const page of pages()) expect(ENTRIES.filter(e => e.startsWith(`${page}/`)).length, page).toBeGreaterThan(0);
    expect(ENTRIES.filter(e => /worker/i.test(e)).length).toBeGreaterThan(0);  // the walk follows new Worker(new URL(...))
  });

  it('each JSON module a public entry reaches is a registry the filter loads, or names no item for a reason written down', () => {
    const reached = reachedJson(ENTRIES);
    expect(reached.length).toBeGreaterThan(0);
    expect(reached.filter(f => !COVERED.has(f) && !NAMES_NO_ITEM[f]),
      'add each to shared/release-filter.mjs REGISTRIES, or to NAMES_NO_ITEM here with why it names no item').toEqual([]);
    for (const [f, why] of Object.entries(NAMES_NO_ITEM)) {
      expect(reached, `${f}: no public entry reaches it any more; remove it from NAMES_NO_ITEM`).toContain(f);
      expect(typeof why === 'string' && why.length > 20, f).toBe(true);
    }
  });

  it('every JSON file under a page\'s src that names an item is covered by the filter (a page test reads the filtered view of each)', () => {
    // step 3 of 2026-11-23 (the lab Flow dry run): flow-kinds.json and screener-overlay.json name items by id; a page test
    // read the filtered registries beside them whole and disagreed. A new file of item ids is covered from its first commit.
    const ids = new Set(ITEMS.map(it => it.id));
    const walk = (dir, out = []) => {
      for (const f of fs.readdirSync(dir, { withFileTypes: true })) {
        const p = path.join(dir, f.name);
        if (f.isDirectory()) { if (!['node_modules', 'dist', 'dist-lab', 'tests'].includes(f.name)) walk(p, out) }
        else if (f.name.endsWith('.json')) out.push(p);
      }
      return out;
    };
    const naming = pages().flatMap(page => fs.existsSync(path.join(EDGE_BFF, page, 'src')) ? walk(path.join(EDGE_BFF, page, 'src')) : [])
      .map(f => path.relative(EDGE_BFF, f))
      .filter(f => { try { return referencedIds(JSON.parse(fs.readFileSync(path.join(EDGE_BFF, f), 'utf8')), ids).size > 0 } catch { return false } });
    expect(naming).toEqual(expect.arrayContaining(['screener/src/core/flow-kinds.json', 'terminal/src/data/flowRegistry.json']));
    expect(naming.filter(f => !COVERED.has(f) && !NAMES_NO_ITEM[f]),
      'add each to shared/release-filter.mjs REGISTRIES (keyedParts for an object keyed by id)').toEqual([]);
  });

  /* checker I-3 (2026-11-23): an item's id is filtered, but a sentence may name it (screener-metrics.json said "Alpha
     KAMA's colour"). The names of the items not released (their registry entries' names, read from the unfiltered
     registries) appear nowhere in a registry filtered for a public build. */
  it.each(REGISTRIES.map(spec => [spec.file, spec]))('%s, filtered with nothing released, names no unreleased item in its text', (_, spec) => {
    const released = new Set(ITEMS.filter(it => it.stage === 'released' || it.stage === 'preview').map(it => it.id));
    const names = new Set();
    for (const s2 of REGISTRIES) {
      const d = JSON.parse(fs.readFileSync(path.join(EDGE_BFF, s2.file), 'utf8')), ids = heldIds(s2, d);
      const walk = x => { if (Array.isArray(x)) return x.forEach(walk); if (!x || typeof x !== 'object') return;
        if (typeof x.id === 'string' && ids.includes(x.id) && !released.has(x.id) && typeof x.name === 'string' && x.name.length > 5) names.add(x.name);
        Object.values(x).forEach(walk) };
      walk(d);
    }
    const text = JSON.stringify(filtered(spec, JSON.parse(fs.readFileSync(path.join(EDGE_BFF, spec.file), 'utf8')), { lab: false, stages: new Map() }));
    expect([...names].filter(n => text.includes(n)), 'a sentence names an item that is not released: name the kind of output instead').toEqual([]);
  });

  it.each(REGISTRIES.map(spec => [spec.file, spec]))('%s, filtered with nothing released, names no item of its kinds', (_, spec) => {
    const doc = JSON.parse(fs.readFileSync(path.join(EDGE_BFF, spec.file), 'utf8'));
    expect(heldIds(spec, doc).length, 'the spec reads the registry\'s entries').toBeGreaterThan(0);
    expect(leftOver(spec, doc), 'a part of the file the spec does not filter names these items: add it to the spec').toEqual([]);
  });

  it('the filter keeps a released id in the public build, drops a lab one and one the release file does not list, and keeps all three in the lab build', () => {
    const spec = { file: 'x.json', kind: 'indicator', list: d => d.indicators, put: (d, l) => ({ ...d, indicators: l }) };
    const doc = { indicators: [{ id: 'R1' }, { id: 'L1' }, { id: 'U1' }] };
    const stages = new Map([['indicator\tR1', 'released'], ['indicator\tL1', 'lab']]);
    expect(filtered(spec, doc, { lab: false, stages }).indicators.map(e => e.id)).toEqual(['R1']);
    expect(filtered(spec, doc, { lab: true, stages }).indicators.map(e => e.id)).toEqual(['R1', 'L1', 'U1']);
    // the same in a list of a file with several, and in an object keyed by id
    const lists = { file: 'y.json', lists: [['a', 'indicator'], ['b', 'flow_indicator']] };
    const two = filtered(lists, { a: [{ id: 'R1' }, { id: 'U1' }], b: [{ id: 'R1' }] }, { lab: false, stages });
    expect([two.a.map(e => e.id), two.b]).toEqual([['R1'], []]);             // R1 is released as an indicator only
    const keyed = { file: 'z.json', kind: 'indicator', keyed: 'lag' };
    expect(Object.keys(filtered(keyed, { lag: { R1: 1, L1: 2, U1: 3 } }, { lab: false, stages }).lag)).toEqual(['R1']);
  });
  it('the filter keeps a preview id in both builds, marked release preview, and readStages refuses an unknown stage', () => {
    // EXEC-MU-ACCOUNTS "A preview release stage": on both sites for the admin only, its definition public
    const spec = { file: 'x.json', kind: 'indicator', list: d => d.indicators, put: (d, l) => ({ ...d, indicators: l }) };
    const doc = { indicators: [{ id: 'R1' }, { id: 'P1', name: 'Preview one' }, { id: 'L1' }] };
    const stages = new Map([['indicator\tR1', 'released'], ['indicator\tP1', 'preview'], ['indicator\tL1', 'lab']]);
    expect(filtered(spec, doc, { lab: false, stages }).indicators).toEqual([{ id: 'R1' }, { id: 'P1', name: 'Preview one', release: 'preview' }]);
    expect(filtered(spec, doc, { lab: true, stages }).indicators).toEqual([{ id: 'R1' }, { id: 'P1', name: 'Preview one', release: 'preview' }, { id: 'L1' }]);
    expect(doc.indicators[1]).toEqual({ id: 'P1', name: 'Preview one' });            // the source document is not changed
    const lists = { file: 'y.json', lists: [['a', 'indicator'], ['b', 'flow_indicator']] };
    expect(filtered(lists, { a: [{ id: 'P1' }], b: [{ id: 'P1' }] }, { lab: false, stages })).toEqual({ a: [{ id: 'P1', release: 'preview' }], b: [] });
    const keyed = { file: 'z.json', kind: 'indicator', keyed: 'lag' };
    expect(filtered(keyed, { lag: { R1: 1, P1: 2, L1: 3 } }, { lab: false, stages }).lag).toEqual({ R1: 1, P1: 2 });
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'edge-stages-'));
    const file = path.join(dir, 'releases.json');
    fs.writeFileSync(file, JSON.stringify({ items: [{ kind: 'indicator', id: 'P1', stage: 'preview' }] }));
    expect(readStages(file).get('indicator\tP1')).toBe('preview');
    fs.writeFileSync(file, JSON.stringify({ items: [{ kind: 'indicator', id: 'B1', stage: 'beta' }] }));
    expect(() => readStages(file)).toThrow(/lab\|preview\|released/);
  });

  it('a part a spec names that is missing or of another shape stops the build (round 2 BUN2-4, CS-4)', () => {
    const lists = { file: 'y.json', lists: [['indicators', 'indicator'], ['flows', 'flow_indicator']] };
    const stages = new Map();
    expect(() => filtered(lists, { indicators: [], flow: [{ id: 'FL01' }] }, { lab: false, stages })).toThrow(/has no list "flows"/);
    expect(() => filtered(lists, { indicators: [], flows: { FL01: {} } }, { lab: false, stages })).toThrow(/has no list "flows"/);
    expect(() => filtered({ file: 'z.json', kind: 'indicator', keyed: 'lag' }, { lag: [] }, { lab: false, stages })).toThrow(/has no object "lag"/);
    expect(() => filtered({ file: 'x.json', kind: 'indicator', list: d => d.indicators, put: (d, l) => l }, {}, { lab: false, stages })).toThrow(/no list of entries/);
  });

  it('a second part naming items, and a reached file the filter does not load, are caught (the self-tests)', () => {
    const keyed = { file: 'z.json', kind: 'indicator', keyed: 'price_lag' };
    expect(leftOver(keyed, { price_lag: { I01: {} }, volume_lag: { I01: {} } }, [])).toEqual(['I01']);
    const list = { file: 'x.json', kind: 'indicator', list: d => d.indicators, put: (d, l) => ({ ...d, indicators: l }) };
    expect(leftOver(list, { indicators: [{ id: 'I01' }], groups: [{ id: 'g', members: [{ id: 'I01' }] }] }, [])).toEqual(['I01']);
    expect(leftOver(list, { indicators: [{ id: 'I01' }], tip: 'reads I01 first' }, [])).toEqual([]);   // prose is not an entry
    // a planted page whose Web Worker imports a JSON file the filter does not load
    const edge = fs.mkdtempSync(path.join(os.tmpdir(), 'edge-3f-coverage-'));
    try {
      const put = (f, text) => { fs.mkdirSync(path.dirname(path.join(edge, f)), { recursive: true }); fs.writeFileSync(path.join(edge, f), text) };
      put('page/vite.config.ts', 'export default {}\n');
      put('page/index.html', '<script type="module" src="/src/main.ts"></script>\n');
      put('page/src/main.ts', "import './start';\n");
      put('page/src/start.ts', "export const w = new Worker(new URL('./names.worker.ts', import.meta.url));\n");
      put('page/src/names.worker.ts', "import names from './names.json';\nexport default names;\n");
      put('page/src/names.json', '{"I54": {"name": "x"}}\n');
      expect(entriesOf(edge)).toEqual(['page/src/main.ts', 'page/src/names.worker.ts']);
      expect(reachedJson(entriesOf(edge), edge).filter(f => !COVERED.has(f))).toEqual(['page/src/names.json']);
      put('page/src/start.ts', "const u = './names.worker.ts';\nexport const w = new Worker(new URL(u, import.meta.url));\n");
      expect(() => entriesOf(edge)).toThrow(/without a literal new URL/);
    } finally {
      fs.rmSync(edge, { recursive: true, force: true });
    }
  });
});
