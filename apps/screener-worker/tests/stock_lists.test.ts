/* EXEC-SCREENER-STOCK-LISTS (user 2026-11-09: options 1A, 2, 3): the reference file `stock_lists` in the worker, end to
   end against the fake terminal-api with the file in the publisher's format (publisher.py stock_lists_doc): its lists
   restricted to the snapshot's listed stocks (members outside the universe and non-stocks never appear or count), the
   catalog block and the universe rows' memberships, a run with index and group filters (any of a kind, both kinds
   together, an exclusion), the refusals (an unknown code; a list filter while the file is not available), a missing,
   not indexed, broken or off-origin file that leaves the Screener running with the lists unavailable, and a refresh
   when the file's sha256 changes (none when it is the same). */
import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { createApp } from '../src/server.ts';
import type { WorkerApp } from '../src/server.ts';
import { referenceHash } from '../src/snapshot.ts';
import { STOCK_LISTS_REASONS, StockListsBroken, parseStockLists, stockListsOf } from '../src/stocklists.ts';
import type { UniverseRow } from '../../edge-bff/screener/src/core/contract.ts';
import { startFakeTerminal, universe } from './fake-terminal.mjs';
import { OWNER_A, PROXY, auth, call, captureLogs, configFor } from './helpers.ts';
import { refOf } from './fixtures.ts';

const logs = captureLogs();
const open: { app: WorkerApp; fake: { close(): Promise<void> } }[] = [];
after(async () => { for (const o of open) { await o.app.close(); await o.fake.close() } });

const AS_OF = '2026-11-09T13:31:48.255552+00:00';
/* six stocks T000..T005 plus IHSG (an index, not a stock); XOUT and YOUT are members outside the universe */
const LISTS = [
  ['INDEX:467', 'INDEX', 'IHSG', 'IHSG', 'Indeks Harga Saham Gabungan.', AS_OF, ['IHSG', 'T000', 'T001', 'T002', 'T003', 'T004', 'T005', 'XOUT']],
  ['INDEX:550', 'INDEX', 'LQ45', 'LQ45', '45 saham likuid.', AS_OF, ['T000', 'T001', 'T002']],
  ['INDEX:551', 'INDEX', 'JII', 'JII', 'Jakarta Islamic Index.', AS_OF, ['T002', 'T003']],
  ['KONGLO:9', 'KONGLO', 'SALIM', 'Salim', 'Grup usaha versi Stockbit.', AS_OF, ['T001', 'T002', 'XOUT', 'YOUT']],
  ['KONGLO:59', 'KONGLO', 'DJARUM', 'Djarum', 'Grup usaha versi Stockbit.', AS_OF, ['T004']],
  ['KONGLO:60', 'KONGLO', 'EMPTY', 'Only outside', 'Every member outside the universe.', null, ['XOUT']],
];
const u = universe(6, 300);
const pubOf = (finished_at: string, extra: Record<string, unknown> = {}) => ({ finished_at, ...u, actions: [], stockLists: LISTS, ...extra });
const U = { security_types: ['stock'], price_min: null, adv20_min_idr: null };
let seq = 0;
const run = (port: number, universe: Record<string, unknown>) => call(port, 'POST', '/v1/run',
  { schema_version: 1, client_order: { page: 'p', seq: ++seq }, definition: { universe: { ...U, ...universe }, conditions: [], logic: 'all' }, options: { exhaustive: true } }, auth(OWNER_A));
const tickers = (body: any) => (body.rows as any[]).map(r => r.ticker).sort();

async function start(publication: any) {
  const fake = await startFakeTerminal({ key: PROXY, publication });
  const app = createApp(configFor(fake.url, { SCREENER_THREADS: '1' }), { pollMs: 3_600_000 });
  const port = await app.listen(0, '127.0.0.1');
  open.push({ app, fake });
  await app.refresher.tick();
  assert.ok(app.state().current, 'snapshot loaded');
  return { app, fake, port };
}

/* ---- the file's shape and the memberships (pure) ---------------------------------------------------------------- */
const docOf = (lists: unknown[][]) => {
  const cols = ['list_key', 'kind', 'code', 'name', 'definition', 'as_of', 'members'];
  return { schema_version: 1, columns: cols, ...Object.fromEntries(cols.map((c, i) => [c, lists.map(r => r[i])])) } as Record<string, unknown>;
};
const row = (ticker: string): UniverseRow => ({ ticker, name: ticker, sector: 'Energy', industry: 'Coal', last: 100, chg_1d_pct: 0, adv20_idr: 1e9, first_bar: '2026-01-02', last_bar: '2026-10-27', bars: 200, stale: false, remarks: [] });

test('parseStockLists reads the publisher\'s file and refuses any file it cannot have written', () => {
  const lists = parseStockLists(docOf(LISTS));
  assert.deepEqual(lists.map(l => [l.key, l.kind, l.code, l.members.length]), [['INDEX:467', 'INDEX', 'IHSG', 8], ['INDEX:550', 'INDEX', 'LQ45', 3], ['INDEX:551', 'INDEX', 'JII', 2],
    ['KONGLO:9', 'KONGLO', 'SALIM', 4], ['KONGLO:59', 'KONGLO', 'DJARUM', 1], ['KONGLO:60', 'KONGLO', 'EMPTY', 1]]);
  // the same code in the two kinds is two lists (a filter names its kind); twice in one kind is a broken file
  assert.equal(parseStockLists(docOf([...LISTS, ['KONGLO:61', 'KONGLO', 'LQ45', 'A group', 'x', null, []]])).length, 7);
  const broken: [string, Record<string, unknown>, RegExp][] = [
    ['a missing column', (() => { const d = docOf(LISTS); delete d.members; return d })(), /column members is missing/],
    ['columns of two lengths', (() => { const d = docOf(LISTS); (d.code as unknown[]).pop(); return d })(), /differ in length/],
    ['a code twice in a kind', docOf([...LISTS, ['INDEX:999', 'INDEX', 'LQ45', 'Again', 'x', null, []]]), /code LQ45 is used twice for INDEX/],
    ['an unknown kind', docOf([['SECTOR:1', 'SECTOR', 'X', 'X', 'x', null, []]]), /kind "SECTOR"/],
    ['an empty name', docOf([['INDEX:1', 'INDEX', 'X', ' ', 'x', null, []]]), /no code, name or definition/],
    ['a member twice', docOf([['INDEX:1', 'INDEX', 'X', 'X', 'x', null, ['T000', 'T000']]]), /not distinct tickers/],
    ['a member that is no ticker', docOf([['INDEX:1', 'INDEX', 'X', 'X', 'x', null, ['t000']]]), /not distinct tickers/],
    ['an as_of that is no time', docOf([['INDEX:1', 'INDEX', 'X', 'X', 'x', 'soon', []]]), /as_of that is not a time/],
  ];
  for (const [what, d, want] of broken) assert.throws(() => parseStockLists(d), (e: unknown) => e instanceof StockListsBroken && want.test((e as Error).message), what);
});

test('stockListsOf: memberships and counts over the listed stocks only, in the file\'s order; without a file the rows carry nothing', () => {
  const rows = ['T000', 'T001', 'T002', 'T004', 'T005'].map(row);
  const block = stockListsOf({ sha256: 'a'.repeat(64), lists: parseStockLists(docOf(LISTS)) }, rows);
  assert.equal(block.availability, 'AVAILABLE');
  assert.equal(block.as_of, AS_OF);
  // T003 is not listed here, XOUT/YOUT are outside the universe, IHSG is not a stock: none of them counts
  assert.deepEqual(block.lists.map(l => [l.code, l.tickers]), [['IHSG', 5], ['LQ45', 3], ['JII', 1], ['SALIM', 2], ['DJARUM', 1], ['EMPTY', 0]]);
  assert.deepEqual(rows.map(r => [r.ticker, r.indices, r.groups]), [['T000', ['IHSG', 'LQ45'], []], ['T001', ['IHSG', 'LQ45'], ['SALIM']],
    ['T002', ['IHSG', 'LQ45', 'JII'], ['SALIM']], ['T004', ['IHSG'], ['DJARUM']], ['T005', ['IHSG'], []]]);
  const bare = ['T000'].map(row);
  assert.deepEqual(stockListsOf({ reason: STOCK_LISTS_REASONS.unreadable }, bare), { availability: 'REQUIRES_DATA', reason: STOCK_LISTS_REASONS.unreadable, as_of: null, lists: [] });
  assert.deepEqual(stockListsOf(undefined, bare).reason, STOCK_LISTS_REASONS.not_indexed);
  assert.ok(!('indices' in bare[0]) && !('groups' in bare[0]), 'no membership field without a file');
});

test('referenceHash: unchanged without the file or while it is unavailable (the snapshots of before keep their identity); another sha256 is another reference', () => {
  const ref = refOf(u.ref);
  const base = referenceHash(ref);
  assert.equal(referenceHash({ ...ref, stockLists: { reason: STOCK_LISTS_REASONS.not_indexed } }), base);
  const a = referenceHash({ ...ref, stockLists: { sha256: 'a'.repeat(64), lists: [] } }), b = referenceHash({ ...ref, stockLists: { sha256: 'b'.repeat(64), lists: [] } });
  assert.notEqual(a, base); assert.notEqual(a, b);
});

/* ---- end to end -------------------------------------------------------------------------------------------------- */
test('the file present: the catalog block, the universe rows\' memberships, and runs by index, by group, both together and excluded', async () => {
  const { port } = await start(pubOf('2026-10-27T13:03:23Z'));
  const cat = (await call(port, 'GET', '/v1/catalog', undefined, auth())).body;
  assert.equal(cat.stock_lists.availability, 'AVAILABLE');
  assert.equal(cat.stock_lists.reason, null);
  assert.deepEqual(cat.stock_lists.lists.map((l: any) => [l.key, l.kind, l.code, l.name, l.tickers, l.as_of]), [['INDEX:467', 'INDEX', 'IHSG', 'IHSG', 6, AS_OF],
    ['INDEX:550', 'INDEX', 'LQ45', 'LQ45', 3, AS_OF], ['INDEX:551', 'INDEX', 'JII', 'JII', 2, AS_OF], ['KONGLO:9', 'KONGLO', 'SALIM', 'Salim', 2, AS_OF],
    ['KONGLO:59', 'KONGLO', 'DJARUM', 'Djarum', 1, AS_OF], ['KONGLO:60', 'KONGLO', 'EMPTY', 'Only outside', 0, null]]);
  assert.equal(cat.stock_lists.lists[1].definition, '45 saham likuid.');
  const uni = (await call(port, 'GET', '/v1/universe', undefined, auth())).body;
  assert.deepEqual(uni.rows.map((r: any) => [r.ticker, r.indices, r.groups]), [['T000', ['IHSG', 'LQ45'], []], ['T001', ['IHSG', 'LQ45'], ['SALIM']],
    ['T002', ['IHSG', 'LQ45', 'JII'], ['SALIM']], ['T003', ['IHSG', 'JII'], []], ['T004', ['IHSG'], ['DJARUM']], ['T005', ['IHSG'], []]]);
  // within a kind: any of the chosen; across kinds: both; an exclusion drops a member of any chosen list
  const cases: [Record<string, unknown>, string[]][] = [
    [{ indices_in: ['LQ45'] }, ['T000', 'T001', 'T002']],
    [{ indices_in: ['LQ45', 'JII'] }, ['T000', 'T001', 'T002', 'T003']],
    [{ indices_in: ['LQ45'], groups_in: ['SALIM'] }, ['T001', 'T002']],
    [{ indices_in: ['JII'], groups_in: ['SALIM', 'DJARUM'] }, ['T002']],
    [{ indices_out: ['LQ45'] }, ['T003', 'T004', 'T005']],
    [{ indices_in: ['LQ45'], indices_out: ['JII'] }, ['T000', 'T001']],
    [{ groups_out: ['SALIM', 'DJARUM'] }, ['T000', 'T003', 'T005']],
    [{ groups_in: ['EMPTY'] }, []],
    [{ indices_in: ['IHSG'], sectors_in: ['Energy'] }, ['T001', 'T004']],
    // empty lists are no filter
    [{ indices_in: [], groups_out: [] }, ['T000', 'T001', 'T002', 'T003', 'T004', 'T005']],
  ];
  for (const [universe, want] of cases) {
    const r = await run(port, universe);
    assert.equal(r.status, 200, JSON.stringify(r.body));
    assert.deepEqual([universe, tickers(r.body), r.body.universe.eligible], [universe, want, want.length]);
  }
  // the normalized definition leaves empty lists out: its hash is the one of the same screen without them
  const v = async (universe: Record<string, unknown>) => (await call(port, 'POST', '/v1/validate', { schema_version: 1, definition: { universe: { ...U, ...universe }, conditions: [], logic: 'all' } }, auth())).body;
  const plain = await v({}), empty = await v({ indices_in: [], groups_in: [], indices_out: [], groups_out: [] }), lq = await v({ indices_in: ['LQ45'] });
  assert.equal(empty.definition_hash, plain.definition_hash);
  assert.ok(!('indices_in' in empty.normalized.universe));
  assert.deepEqual(lq.normalized.universe.indices_in, ['LQ45']); assert.notEqual(lq.definition_hash, plain.definition_hash);
  // refusals: where, how to pass, a right and a wrong example
  const bad = await run(port, { groups_in: ['SALIM', 'Salim '] });
  assert.equal(bad.status, 422);
  assert.deepEqual([bad.body.error.code, bad.body.error.field], ['INVALID_CONDITION', 'definition.universe.groups_in[1]']);
  assert.match(bad.body.error.message, /"Salim " is not the code of a group the Screener holds\. Write it as the Group list shows it: "SALIM" is accepted, "Salim " is refused\./);
  assert.deepEqual(bad.body.error.details.allowed, ['SALIM', 'DJARUM', 'EMPTY']);
  const kind = await run(port, { indices_in: ['SALIM'] });
  assert.deepEqual([kind.body.error.code, kind.body.error.field, kind.body.error.details.allowed], ['INVALID_CONDITION', 'definition.universe.indices_in[0]', ['IHSG', 'LQ45', 'JII']], 'a group is not an index');
  const both = await run(port, { indices_in: ['LQ45'], indices_out: ['JII', 'LQ45'] });
  assert.deepEqual([both.body.error.code, both.body.error.field], ['INVALID_CONDITION', 'definition.universe.indices_out[1]']);
  assert.match(both.body.error.message, /"LQ45" is both included and excluded, which leaves no stock; keep it on one side \(include "LQ45" and exclude "IHSG" is accepted; include and exclude "LQ45" is refused\)/);
});

test('the file not published: the Screener runs, the lists are unavailable with the reason, and a list filter is refused naming it and how to pass', async () => {
  const { port, app } = await start(pubOf('2026-10-27T13:03:23Z', { stockLists: undefined }));
  const cat = (await call(port, 'GET', '/v1/catalog', undefined, auth())).body;
  assert.deepEqual(cat.stock_lists, { availability: 'REQUIRES_DATA', reason: STOCK_LISTS_REASONS.not_indexed, as_of: null, lists: [] });
  const uni = (await call(port, 'GET', '/v1/universe', undefined, auth())).body;
  assert.ok(uni.rows.every((r: any) => !('indices' in r) && !('groups' in r)));
  const ok = await run(port, { sectors_in: ['Energy'], indices_in: [] });
  assert.equal(ok.status, 200, 'an empty list filter is no filter: it runs');
  const r = await run(port, { indices_in: ['LQ45'] });
  assert.equal(r.status, 422);
  assert.deepEqual([r.body.error.code, r.body.error.field, r.body.error.details], ['METRIC_UNAVAILABLE', 'definition.universe.indices_in',
    { metric: 'stock_lists', availability: 'REQUIRES_DATA', reason: STOCK_LISTS_REASONS.not_indexed }]);
  assert.match(r.body.error.message, /needs the index and group lists, which are not available: This publication carries no index and group lists\. Remove the Index filter to run the screen \(the same screen without it runs; with Index "LQ45" it waits for the lists\)\./);
  assert.ok(logs.events('stock_lists_unavailable').length >= 1);
  assert.equal(app.state().outcome, 'ready');
});

test('a broken file never stops the Screener: not indexed, another sha256, another size, off the bucket origin, or not in the publisher\'s shape', async () => {
  const cases: [string, Record<string, unknown>, string][] = [
    ['not indexed (no sha256)', { stockListsRef: { sha256: null } }, STOCK_LISTS_REASONS.not_indexed],
    ['another sha256', { stockListsRef: { sha256: 'f'.repeat(64) } }, STOCK_LISTS_REASONS.unreadable],
    ['another size', { stockListsRef: { bytes: 7 } }, STOCK_LISTS_REASONS.unreadable],
    ['off the bucket origin', { stockListsRef: { url: 'https://elsewhere.example/v1/ref/stock_lists.json.gz' } }, STOCK_LISTS_REASONS.unreadable],
    ['a code twice', { stockListsDoc: docOf([...LISTS, ['INDEX:999', 'INDEX', 'LQ45', 'Again', 'x', null, []]]) }, STOCK_LISTS_REASONS.unreadable],
  ];
  for (const [what, extra, reason] of cases) {
    const before = logs.events('stock_lists_unavailable').length;
    const { port, app } = await start(pubOf('2026-10-27T13:03:23Z', extra));
    assert.equal(app.state().outcome, 'ready', what);
    const cat = (await call(port, 'GET', '/v1/catalog', undefined, auth())).body;
    assert.deepEqual([what, cat.stock_lists.availability, cat.stock_lists.reason], [what, 'REQUIRES_DATA', reason]);
    assert.equal((await run(port, { price_min: 1 })).status, 200, `${what}: a screen without a list filter runs`);
    assert.equal(logs.events('stock_lists_unavailable').length, before + 1, `${what}: logged once`);
  }
});

test('a refresh when the file\'s sha256 changes (memberships follow, another snapshot); none when it is the same', async () => {
  const { app, port, fake } = await start(pubOf('2026-10-27T13:03:23Z'));
  const sid = app.state().current!.sid;
  // a new publication, the same prices and lists: the snapshot is kept (rule 3)
  (fake as any).publish(pubOf('2026-10-27T23:00:00Z'));
  await app.refresher.tick();
  assert.equal(app.state().current!.sid, sid);
  assert.equal(logs.events('refresh_skipped').at(-1)!.published_at, '2026-10-27T23:00:00Z');
  // LQ45 changes (T002 out, T005 in): the same prices, another stock-lists file
  const changed = LISTS.map(l => l[2] === 'LQ45' ? [...l.slice(0, 6), ['T000', 'T001', 'T005']] : l);
  (fake as any).publish(pubOf('2026-10-28T13:03:23Z', { stockLists: changed }));
  await app.refresher.tick();
  assert.notEqual(app.state().current!.sid, sid, 'another snapshot');
  assert.equal(app.state().current!.finished_at, '2026-10-28T13:03:23Z');
  const r = await run(port, { indices_in: ['LQ45'] });
  assert.deepEqual(tickers(r.body), ['T000', 'T001', 'T005']);
  const uni = (await call(port, 'GET', '/v1/universe', undefined, auth())).body;
  assert.deepEqual(uni.rows.find((x: any) => x.ticker === 'T002').indices, ['IHSG', 'JII']);
  // the file gone at the next publication: the lists become unavailable, the Screener keeps running
  (fake as any).publish(pubOf('2026-10-29T13:03:23Z', { stockLists: undefined }));
  await app.refresher.tick();
  const cat = (await call(port, 'GET', '/v1/catalog', undefined, auth())).body;
  assert.deepEqual([cat.data.published_at, cat.stock_lists.availability], ['2026-10-29T13:03:23Z', 'REQUIRES_DATA']);
  assert.equal((await run(port, { indices_in: ['LQ45'] })).body.error.code, 'METRIC_UNAVAILABLE');
});
