/* 3e, the example mode (ERRORS M527): the Screener example's capture (tests/example-capture.ts) on this suite's made-up
   market. The worker's answer on the publication cut at a date never depends on a row after it (every later price,
   volume, action and broker day changed: the same catalog, universe and run), names no later date, and is evaluated on
   that date; the cut keeps every earlier row and the reference of every stock priced by then. Red without the cut. */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { brokerRowsOf, universe } from './fake-terminal.mjs';
import { envFor, EDGE_CONTEXT } from './helpers.ts';
import { cutPublication, screenOn, type Publication } from './example-capture.ts';

const LAST = '2026-10-27';
function market(): Publication {
  const u = universe(12, 330, { last: LAST });
  const days = (u.prices.IHSG as unknown[][]).map(r => r[0] as string);
  u.prices.LATE = (u.prices.T000 as unknown[][]).slice(-3).map(r => [...r]);          // listed after the date: no price by then
  u.ref.push(['LATE', 'Late listing', 'stock', 'Energy', 'Energy industry']);
  return { finished_at: `${LAST}T13:03:23Z`, ...u, actions: [['T001', days[days.length - 5], 'STOCK_SPLIT', 1, 2, null, null], ['T002', days[100], 'STOCK_SPLIT', 1, 2, null, null]],
    broker: Object.fromEntries(days.slice(-62, -2).map((d, k) => [d, brokerRowsOf(k + 1, d, ['T000', 'T001', 'T002'])])),
    brokers: [['AK', 'A', 'Local', 'Institutional-heavy'], ['BK', 'B', 'Foreign', 'Retail-heavy'], ['CC', 'C', 'Local', 'Mixed'], ['DX', 'D', 'Local', 'Institutional-heavy'], ['YP', 'Y', 'Local', 'Retail-heavy'], ['ZP', 'Z', 'Foreign', 'Mixed']] };
}
const p0 = market(), days = (p0.prices.IHSG as unknown[][]).map(r => r[0] as string), AS_OF = days[days.length - 9];
/** every row after the date changed: prices tenfold, volumes a hundredfold, a split and a broker day of other figures */
function later(p: Publication): Publication {
  const q = structuredClone(p) as Publication;
  for (const rows of Object.values(q.prices)) for (const r of rows) if ((r[0] as string) > AS_OF) for (let k = 1; k <= 4; k++) r[k] = (r[k] as number) * 10;
  for (const rows of Object.values(q.prices)) for (const r of rows) if ((r[0] as string) > AS_OF && r[5] != null) r[5] = (r[5] as number) * 100;
  q.actions.push(['T003', days[days.length - 2], 'STOCK_SPLIT', 1, 5, null, null]);
  for (const [d, rows] of Object.entries(q.broker ?? {})) if (d > AS_OF) for (const r of rows) { r[4] = (r[4] as number) * 7 + 1; r[5] = (r[5] as number) * 3 + 2 }
  return q;
}
const ENV = envFor('http://127.0.0.1:9');
const without = (x: any) => { const { timings_ms: _t, ...rest } = x ?? {}; return rest };
let shown: Awaited<ReturnType<typeof screenOn>> | undefined;
const onCut = async () => shown ??= await screenOn(cutPublication(p0, AS_OF), ENV, 'brk52', EDGE_CONTEXT);

test('the cut keeps every row up to the date, the reference of every stock priced by then, no stock list, and the date as the time', () => {
  const cut = cutPublication(p0, AS_OF);
  assert.equal(cut.finished_at, AS_OF);
  assert.equal(cut.price_through, AS_OF);
  for (const [t, rows] of Object.entries(p0.prices)) {
    const kept = rows.filter(r => (r[0] as string) <= AS_OF);
    assert.deepEqual(cut.prices[t] ?? [], kept, t);
  }
  assert.ok(!('LATE' in cut.prices) && !cut.ref.some(r => r[0] === 'LATE'), 'a stock listed after the date');
  assert.deepEqual(cut.actions, p0.actions.filter(r => (r[1] as string) <= AS_OF));
  assert.ok(Object.keys(cut.broker!).every(d => d <= AS_OF) && Object.keys(cut.broker!).length === Object.keys(p0.broker!).filter(d => d <= AS_OF).length);
  assert.ok(!('stockLists' in cut));
  assert.throws(() => cutPublication(p0, '2026-10-31'), /no price on 2026-10-31/);      // a date the data does not reach
});

test('the worker\'s answer on the cut publication depends on no row after the date and names no later date', async () => {
  const shown = await onCut();
  const again = await screenOn(cutPublication(later(p0), AS_OF), ENV, 'brk52', EDGE_CONTEXT);
  assert.deepEqual(again.catalog, shown.catalog);
  assert.deepEqual(again.universe, shown.universe);
  assert.deepEqual(without(again.run), without(shown.run));
  assert.equal(shown.catalog.data.evaluation_date, AS_OF);
  assert.equal(shown.run.data.evaluation_date, AS_OF);
  assert.equal(shown.catalog.data.published_at, AS_OF);
  assert.deepEqual(shown.screen, { preset: 'brk52', name: shown.screen.name, definition: shown.catalog.presets.find((x: any) => x.id === 'brk52').definition });
  const late = [...JSON.stringify([shown.catalog, shown.universe, shown.run]).matchAll(/\d{4}-\d\d-\d\d/g)].map(m => m[0]).filter(d => d > AS_OF);
  assert.deepEqual([...new Set(late)], []);
  assert.ok(shown.run.rows.every((r: any) => r.eval_date === AS_OF || r.eval_date === null), 'every row evaluated on the date');
});

test('red without the cut: the full publication gives another answer', async () => {
  const full = await screenOn({ ...p0, finished_at: AS_OF }, ENV, 'brk52', EDGE_CONTEXT);
  assert.notDeepEqual(without(full.run), without((await onCut()).run));
});
