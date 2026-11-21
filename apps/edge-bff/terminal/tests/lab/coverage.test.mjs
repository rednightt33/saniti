/* 3f (checker L3, 2026-11-21; CONTRACT.md 8 "Lab code"): the release filter covers every file a public entry reaches
   that names an item. The list of filtered files (shared/release-filter.mjs REGISTRIES) is written by hand, so this
   derives the files it must hold: every JSON module that a page's or a Web Worker's entry reaches (the import walk,
   shared/import-walk.mjs, type imports included) and that names a release-file id, as an entry's `id` or as an object
   key. Prose that mentions an id (a tip, a note) is not an entry and is not counted. The self-test plants such a file. */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { ROOT, reachable } from '../../../shared/import-walk.mjs';
import { EDGE_BFF, REGISTRIES, RELEASES, labAlias } from '../../../shared/release-filter.mjs';

const ENTRIES = ['terminal/src/main.ts', 'terminal/src/data/worker.ts', 'backtest/src/main.ts', 'backtest/src/api/load.worker.ts',
  'screener/src/main.ts', 'radar/src/main.ts', 'overview/src/main.ts', 'watchlist/src/main.ts'];
const IDS = new Set(JSON.parse(fs.readFileSync(RELEASES, 'utf8')).items.map(it => it.id));
const COVERED = new Set(REGISTRIES.map(r => r.file));

/** The release-file ids a JSON document names as an entry's id or as an object key, anywhere in it. */
function namedIds(doc, ids = IDS) {
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

/** Each JSON module the public entries reach that names an item, with a few of the ids it names. */
function namingFiles(entries) {
  const out = new Map();
  for (const entry of entries)
    for (const mod of reachable(path.join(EDGE_BFF, entry), { aliases: labAlias({ lab: false }) })) {
      if (!mod.endsWith('.json') || out.has(mod)) continue;
      const ids = namedIds(JSON.parse(fs.readFileSync(path.join(ROOT, mod), 'utf8')));
      if (ids.size) out.set(mod, [...ids].slice(0, 5));
    }
  return out;
}

describe('3f: the release filter covers every file a public entry reaches that names an item', () => {
  it('each JSON module that names a release-file id is one the filter loads', () => {
    const files = namingFiles(ENTRIES);
    expect(files.size).toBeGreaterThan(0);                          // the Terminal's and the Backtest's registries at least
    const uncovered = [...files].filter(([mod]) => !COVERED.has(path.relative(EDGE_BFF, path.join(ROOT, mod))));
    expect(uncovered, 'add each to shared/release-filter.mjs REGISTRIES (list or keyed)').toEqual([]);
  });

  it('a planted file that names an item is caught, and prose that mentions one is not (the self-test)', () => {
    const [someId] = IDS;
    expect(namedIds({ price_lag: { [someId]: { up: 1 } } })).toEqual(new Set([someId]));
    expect(namedIds({ list: [{ id: someId, name: 'x' }] })).toEqual(new Set([someId]));
    expect(namedIds({ tip: `reads ${someId} first`, note: [someId + 'x'] })).toEqual(new Set());
  });
});
