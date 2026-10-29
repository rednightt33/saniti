/* Availability is capability (ERRORS M299; report 6.12 "Availability is derived at run time"): the catalog shows a
   metric AVAILABLE only when the publication indexes its file AND this build reads that file (snapshot.ts
   PHASE1_FILES, the one list the refresh downloads and the builder decodes; catalog.ts metricAvailability), so a file
   the publisher writes before the worker reads it (a Phase 2 broker_window) shows its metrics REQUIRES_DATA with a
   plain reason, and a run with one is refused with that same reason before compute; an advance (the same files on a
   new publication) applies the rule to the new index; and over the whole catalog, with every file any metric needs
   indexed, a metric is AVAILABLE exactly when a definition with it validates and runs (refused ones with the catalog's
   own availability and reason), an available universe attribute is a field of every universe row, and every preset
   runs exactly when the catalog shows it AVAILABLE. The files, the metrics and the presets are read from the catalog
   and the worker's file list, never listed here. */
import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { METRICS_CATALOG } from '../../edge-bff/screener/src/core/catalog.ts';
import type { MetricDefinition } from '../../edge-bff/screener/src/core/catalog.ts';
import { presetAvailability, presetDefinitions } from '../../edge-bff/screener/src/core/validate.ts';
import { createApp } from '../src/server.ts';
import type { WorkerApp } from '../src/server.ts';
import { PHASE1_FILES } from '../src/snapshot.ts';
import { startFakeTerminal, universe } from './fake-terminal.mjs';
import { OWNER_A, PROXY, auth, call, captureLogs, configFor } from './helpers.ts';

const logs = captureLogs();
const open: { app: WorkerApp; fake: { close(): Promise<void> } }[] = [];
after(async () => { for (const o of open) { await o.app.close(); await o.fake.close() } });

const U = { security_types: ['stock'], price_min: null, adv20_min_idr: null };
const READ: readonly string[] = PHASE1_FILES;
/** every file a metric of the catalog needs, and those this build does not read */
const FILES = [...new Set(METRICS_CATALOG.metrics.flatMap(m => m.requires ? [m.requires.file] : []))];
const UNREAD = FILES.filter(f => !READ.includes(f));
/** an index entry for a file the bucket does not hold: the worker never downloads a file outside its list */
const indexed = (names: readonly string[]) => Object.fromEntries(names.map(n => [n, { index: { key: `v1/xsection/${n}.${'0'.repeat(16)}.json.gz`, sha256: '0'.repeat(64), bytes: 1000, rows: 10, as_of: null } }]));
const pubOf = (finished_at: string, files: readonly string[] = []) => ({ finished_at, ...universe(6, 300), actions: [], files: indexed(files) });

async function start(publication: ReturnType<typeof pubOf>) {
  const fake = await startFakeTerminal({ key: PROXY, publication });
  const app = createApp(configFor(fake.url, { SCREENER_THREADS: '1' }), { pollMs: 3_600_000 });
  const port = await app.listen(0, '127.0.0.1');
  open.push({ app, fake });
  await app.refresher.tick();
  assert.ok(app.state().current, 'snapshot loaded');
  return { app, fake, port };
}
const catalogOf = async (port: number) => {
  const c = await call(port, 'GET', '/v1/catalog', undefined, auth());
  assert.equal(c.status, 200);
  return new Map<string, any>([...c.body.metrics, ...c.body.fundamentals].map((m: any) => [m.id, m]));
};
/** the smallest test of a metric as a card states it: its reference (the template of a transform-based metric) in a
    value test, or a state test where it has no value form; a pattern in its state form, else its event form */
function probe(m: MetricDefinition): unknown {
  const ref = m.ref ?? (m.kind === 'pattern' ? { kind: 'pattern', type: m.id } : m.kind === 'universe' ? { kind: 'universe', attr: m.id } : { kind: m.kind, metric: m.id });
  if (m.kind === 'pattern') return m.tests.includes('state') ? { kind: 'state', pattern: ref } : { kind: 'event', within: 1, signal: { pattern: ref } };
  return m.tests.includes('value') ? { kind: 'value', metric: ref, op: 'gt', value: 0 } : { kind: 'state', lhs: ref, op: 'gt', rhs: { value: 0 } };
}
const definitionOf = (m: MetricDefinition) => ({ universe: U, logic: 'all', conditions: [{ id: 'a', enabled: true, test: probe(m) }] });

test('a file the index names but this build does not read (broker_window): its metrics show REQUIRES_DATA with a plain reason, and a run with one is refused with that same reason', async () => {
  assert.ok(!READ.includes('broker_window'), 'the case needs a file this build does not read');
  const { port } = await start(pubOf('2026-10-27T13:03:23Z', ['broker_window']));
  const cat = await catalogOf(port);
  const over = METRICS_CATALOG.metrics.filter(m => m.requires?.file === 'broker_window');
  assert.ok(over.filter(m => !m.decision).length >= 5, 'the flow metrics of the first set read broker_window');
  for (const m of over) {
    const c = cat.get(m.id);
    if (m.decision) { assert.deepEqual([m.id, c.availability, c.reason], [m.id, 'REQUIRES_DECISION', m.decision]); continue }
    assert.equal(c.availability, 'REQUIRES_DATA', `${m.id}: the publication names its file, this build cannot read it`);
    assert.equal(c.reason, `${m.unavailable_reason} It needs data that the Screener does not read yet.`, m.id);
  }
  // a run, a validation and a counts entry with one: refused before compute with the catalog's availability and reason
  // (validate.ts checkRef), never let through to be refused at bind with other words
  const m = over.find(x => !x.decision)!, c = cat.get(m.id);
  const body = { schema_version: 1, client_order: { page: 'p', seq: 1 }, definition: definitionOf(m) };
  for (const [path, req] of [['/v1/run', body], ['/v1/validate', { schema_version: 1, definition: definitionOf(m) }]] as const) {
    const r = await call(port, 'POST', path, req, auth(OWNER_A));
    assert.equal(r.status, 422, `${path}: ${JSON.stringify(r.body)}`);
    assert.deepEqual([r.body.error.code, r.body.error.field, r.body.error.details], ['METRIC_UNAVAILABLE', 'definition.conditions[0].test.metric', { metric: m.id, availability: 'REQUIRES_DATA', reason: c.reason }]);
    assert.ok(r.body.error.message.endsWith(c.reason), r.body.error.message);
  }
  const counts = await call(port, 'POST', '/v1/counts', { schema_version: 1, definitions: [{ item_id: 'x', definition: definitionOf(m) }] }, auth(OWNER_A));
  assert.equal(counts.status, 200);
  assert.deepEqual([counts.body.counts[0].error.code, counts.body.counts[0].error.details.reason], ['METRIC_UNAVAILABLE', c.reason]);
  // a preset with a leg over it is not available and quotes the same reason
  const cat2 = (await call(port, 'GET', '/v1/catalog', undefined, auth())).body;
  const leg = cat2.presets.find((p: any) => p.reason && p.reason.includes(c.reason));
  assert.ok(leg && leg.availability === 'REQUIRES_DATA' && leg.match_count === null, 'a preset over broker_window names the reason');
});

test('an advance (the same files on a new publication) takes availability from the new index by the same rule, and validation follows it', async () => {
  // a universe metric over a file this build does not read, which a preset reads (so the presets follow it too)
  const fund = METRICS_CATALOG.metrics.find(m => m.requires && !m.decision && !READ.includes(m.requires.file) && m.kind === 'universe'
    && presetDefinitions().some(p => JSON.stringify(p.definition).includes(JSON.stringify({ kind: 'universe', attr: m.id }))))!;
  assert.ok(fund, 'a preset reads a universe metric over a file this build does not read');
  const { app, fake, port } = await start(pubOf('2026-10-27T13:03:23Z'));
  const sid = app.state().current!.sid;
  const reasonAt = async () => {
    const c = (await catalogOf(port)).get(fund.id);
    const v = await call(port, 'POST', '/v1/validate', { schema_version: 1, definition: definitionOf(fund) }, auth(OWNER_A));
    assert.equal(v.status, 422);
    assert.deepEqual([c.availability, v.body.error.details.reason], ['REQUIRES_DATA', c.reason], 'the catalog and validation agree');
    return c.reason as string;
  };
  /** the catalog document as it is at this moment: every preset by the snapshot's map now (read synchronously, before
      the presets' counts are computed again in the system lane: a catalog read meanwhile, as edge-bff's after /health
      names the new publication, never shows a preset by the map before; review of the last guards) */
  const presetsFollow = () => {
    const s = app.state().current!, doc = JSON.parse(s.catalog.json.toString());
    assert.equal(doc.data.published_at, s.finished_at);
    for (const p of doc.presets) {
      const a = presetAvailability(presetDefinitions().find(d => d.id === p.id)!, s.availability, METRICS_CATALOG);
      assert.deepEqual([p.id, p.availability, p.reason, p.unavailable_legs], [p.id, a.availability, a.reason, a.unavailable_legs]);
    }
    assert.ok(doc.presets.some((p: any) => p.reason && p.reason.includes(fund.unavailable_reason!)), 'a preset reads the metric');
  };
  assert.match(await reasonAt(), /It needs data that this publication does not carry\.$/);
  // the publisher now indexes the file: the same price and actions files, so the snapshot stays and the index advances
  fake.publish(pubOf('2026-10-27T23:00:00Z', [fund.requires!.file]));
  await app.refresher.tick();
  presetsFollow();
  assert.equal(logs.events('refresh_skipped').at(-1)!.published_at, '2026-10-27T23:00:00Z');
  assert.equal(app.state().current!.sid, sid, 'no swap');
  assert.match(await reasonAt(), /It needs data that the Screener does not read yet\.$/);
  // and drops it again
  fake.publish(pubOf('2026-10-28T01:00:00Z'));
  await app.refresher.tick();
  presetsFollow();
  assert.equal(app.state().current!.sid, sid, 'no swap');
  assert.match(await reasonAt(), /It needs data that this publication does not carry\.$/);
  presetsFollow();
});

test('over the whole catalog, with every file a metric needs indexed: a metric is AVAILABLE exactly when a definition with it validates and runs, a refused one carries the catalog\'s availability and reason, an available universe attribute is a field of every universe row, and a preset runs exactly when it is shown AVAILABLE', async () => {
  assert.ok(UNREAD.length > 0);
  const { port } = await start(pubOf('2026-10-27T13:03:23Z', UNREAD));
  const cat = await catalogOf(port);
  const rows = (await call(port, 'GET', '/v1/universe', undefined, auth())).body.rows as Record<string, unknown>[];
  assert.ok(rows.length > 0);
  const seen = { available: 0, refused: 0 };
  let seq = 0;
  // validation reads the same availability map the catalog shows, so it alone cannot tell a metric the core cannot
  // compute: a run binds and computes it (condition.ts refuses what the core does not compute, e.g. flow), so a metric
  // shown AVAILABLE must also run (review of the last guards)
  const run = (definition: unknown) => call(port, 'POST', '/v1/run', { schema_version: 1, client_order: { page: 'p', seq: ++seq }, definition }, auth(OWNER_A));
  for (const m of METRICS_CATALOG.metrics) {
    const c = cat.get(m.id);
    assert.ok(c, `${m.id} is in the catalog`);
    const v = await call(port, 'POST', '/v1/validate', { schema_version: 1, definition: definitionOf(m) }, auth(OWNER_A));
    const r = await run(definitionOf(m));
    if (c.availability === 'AVAILABLE') {
      seen.available++;
      assert.equal(v.status, 200, `${m.id} is shown available, so a definition with it must validate: ${JSON.stringify(v.body)}`);
      assert.equal(r.status, 200, `${m.id} is shown available, so a run with it must be answered: ${JSON.stringify(r.body)}`);
      if (m.kind === 'universe') for (const row of rows) assert.ok(m.id in row, `${m.id} is shown available, so every universe row must carry it (${String(row.ticker)} does not)`);
    } else {
      seen.refused++;
      for (const [what, a] of [['validate', v], ['run', r]] as const) {
        assert.equal(a.status, 422, `${m.id} is shown ${c.availability} (${what}): ${JSON.stringify(a.body)}`);
        assert.deepEqual([m.id, what, a.body.error.code, a.body.error.details.availability, a.body.error.details.reason], [m.id, what, 'METRIC_UNAVAILABLE', c.availability, c.reason]);
      }
    }
  }
  assert.ok(seen.available > 10 && seen.refused > 10, JSON.stringify(seen));
  // every preset as the catalog shows it: an AVAILABLE one runs, any other is refused with a reason its own reason quotes
  // (a sector or industry the fixture's reference file does not have is left out of its universe: the fixture names
  // its own classes, and availability is about the metrics)
  const full = (await call(port, 'GET', '/v1/catalog', undefined, auth())).body, presets = full.presets as any[];
  const offered = (key: string) => new Set<string>((full.groupings as any[]).find(g => g.key === key)?.values.map((v: any) => v.value) ?? []);
  const inFixture = (u: Record<string, unknown>) => {
    const out = { ...u };
    for (const [k, g] of [['sectors_in', 'sector'], ['sectors_out', 'sector'], ['industries_in', 'industry'], ['industries_out', 'industry']] as const) {
      if (!Array.isArray(out[k])) continue;
      const kept = (out[k] as string[]).filter(v => offered(g).has(v));
      if (kept.length) out[k] = kept; else delete out[k];
    }
    return out;
  };
  assert.ok(presets.some(p => p.availability === 'AVAILABLE') && presets.some(p => p.availability !== 'AVAILABLE'));
  for (const p of presets) {
    const r = await run({ ...p.definition, universe: inFixture(p.definition.universe) });
    if (p.availability === 'AVAILABLE') assert.equal(r.status, 200, `preset ${p.id} is shown available, so it must run: ${JSON.stringify(r.body)}`);
    else {
      assert.deepEqual([p.id, r.status, r.body.error.code], [p.id, 422, 'METRIC_UNAVAILABLE'], JSON.stringify(r.body));
      assert.ok(p.reason.includes(r.body.error.details.reason), `preset ${p.id}: its reason quotes the refusal's (${r.body.error.details.reason})`);
    }
  }
  // every file this build does not read leaves its metrics unavailable, whatever the index says
  for (const m of METRICS_CATALOG.metrics.filter(x => x.requires && UNREAD.includes(x.requires.file))) assert.notEqual(cat.get(m.id).availability, 'AVAILABLE', m.id);
});
