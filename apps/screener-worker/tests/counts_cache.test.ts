/* The counts cache (server.ts CountsCache; report 8.6 "cached per (price_data, definition_hash)"; performance review
   2026-10-29): bounded, least recently used out, the presets' counts pinned, dropped with their snapshot. Before the
   bound, the worker kept one entry per distinct definition computed until the next publication. */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { COUNTS_KEEP, CountsCache } from '../src/server.ts';

test('counts cache: at most `max` unpinned entries, least recently used out; pinned entries stay; a snapshot drops its own', () => {
  assert.ok(COUNTS_KEEP >= 10_000 && COUNTS_KEEP <= 100_000, 'the production bound holds many saved screens and stays small');
  const c = new CountsCache(3), v = (n: number, sid = 's1') => ({ match_count: n, near_count: 0, sid });
  c.set('preset', v(9), true);
  for (const k of ['a', 'b', 'c']) c.set(k, v(1));
  assert.equal(c.get('a')?.match_count, 1);                 // a is now the most recently used
  c.set('d', v(2));                                        // over the bound: b (least recently used) goes
  assert.equal(c.get('b'), undefined);
  assert.deepEqual(['a', 'c', 'd'].map(k => c.get(k)?.match_count), [1, 1, 2]);
  for (let i = 0; i < 100; i++) c.set(`x${i}`, v(i));
  assert.equal(c.size, 4, 'three unpinned plus the pinned preset, whatever was added');
  assert.equal(c.get('preset')?.match_count, 9, 'a pinned entry is never evicted');
  c.set('x99', v(5));                                      // replacing an entry keeps the count of unpinned entries
  assert.equal(c.size, 4);
  c.set('other', v(7, 's2'));
  c.dropSnapshot('s1');
  assert.equal(c.get('preset'), undefined, 'a snapshot drops its pinned entries too');
  assert.equal(c.get('other')?.match_count, 7);
  assert.equal(c.size, 1);
});
