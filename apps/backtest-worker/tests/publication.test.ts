/* EXEC-BACKTEST-LOAD (user 2026-10-27, K1): what is derived from the published files is kept per publication
   (catalog.ts ByPublication): built once per terminal-api /state finished_at, checked at most every checkMs, one build
   shared by its callers, nothing kept while terminal-api cannot name the publication. */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { ByPublication } from '../src/catalog.ts';
import type { Publication } from '../src/terminal.ts';

function setup(first: Publication | null) {
  let pub = first, clock = 0, builds = 0, asks = 0;
  const kept = new ByPublication<string>({ publication: async () => { asks++; return pub } },
    async p => { builds++; return `built ${builds} for ${p?.finished_at ?? 'none'}` }, 60_000, () => clock);
  return { kept, set: (p: Publication | null) => { pub = p }, at: (t: number) => { clock = t }, counts: () => ({ builds, asks }) };
}
const run = (id: string): Publication => ({ finished_at: id, price_through: '2026-10-27', broker_through: '2026-10-27' });

test('one build per publication, checked at most every interval', async () => {
  const s = setup(run('run-1'));
  assert.equal(await s.kept.get(), 'built 1 for run-1');
  s.at(59_999); assert.equal(await s.kept.get(), 'built 1 for run-1'); assert.deepEqual(s.counts(), { builds: 1, asks: 1 });
  s.at(60_000); assert.equal(await s.kept.get(), 'built 1 for run-1'); assert.deepEqual(s.counts(), { builds: 1, asks: 2 });   // same run
  s.set(run('run-2')); s.at(120_000);
  assert.equal(await s.kept.get(), 'built 2 for run-2'); assert.deepEqual(s.counts(), { builds: 2, asks: 3 });
});

test('callers at the same time share one build', async () => {
  const s = setup(run('run-1'));
  const all = await Promise.all([s.kept.get(), s.kept.get(), s.kept.get()]);
  assert.deepEqual(all, Array(3).fill('built 1 for run-1')); assert.deepEqual(s.counts(), { builds: 1, asks: 1 });
});

test('without a publication nothing is kept: every call builds', async () => {
  const s = setup(null);
  await s.kept.get(); await s.kept.get();
  assert.deepEqual(s.counts(), { builds: 2, asks: 2 });
  s.set(run('run-1')); await s.kept.get(); s.at(10); await s.kept.get();
  assert.deepEqual(s.counts(), { builds: 3, asks: 3 });
});

test('a failed build keeps nothing and the next call tries again', async () => {
  let fail = true, builds = 0;
  const kept = new ByPublication<number>({ publication: async () => run('run-1') }, async () => { builds++; if (fail) throw new Error('down'); return builds }, 60_000, () => 0);
  await assert.rejects(kept.get(), /down/);
  fail = false;
  assert.equal(await kept.get(), 2);
});
