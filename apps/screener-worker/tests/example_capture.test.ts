/* 3e, the example mode (ERRORS M527): the Screener example's capture (tests/example-capture.ts) on this suite's made-up
   market, with the stocks of tests/example-market.ts drawn so that the example's preset (terminal-publisher
   examples.py SCREENER_PRESET, read there) and brk52 match on the date the publication is cut at (the example-mode
   checker: a screen with no row would check nothing). The worker's answer on the publication cut at that date never
   depends on a row after it (every later price, volume, action and broker day changed: the same catalog, universe and
   runs, their rows included), names no later date, and is evaluated on that date; the cut keeps every earlier row and
   the reference of every stock priced by then. Red without the cut: the full publication gives other rows. */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { brokerRowsOf, universe } from './fake-terminal.mjs';
import { envFor, EDGE_CONTEXT } from './helpers.ts';
import { cutPublication, screenOn, type Publication } from './example-capture.ts';
import { drawExampleStocks } from './example-market.ts';

/** the example's preset, as the capture job takes it (examples.py SCREENER_PRESET) */
const PRESET = /^SCREENER_PRESET = '([a-z0-9]+)'/m.exec(
  fs.readFileSync(new URL('../../terminal-publisher/examples.py', import.meta.url), 'utf8'))?.[1];
assert.ok(PRESET, 'examples.py names no SCREENER_PRESET');
/** each preset run here and the stock drawn to match it on the date */
const MATCHED: Record<string, string> = { [PRESET!]: 'GCRS', brk52: 'BRKA' };
assert.equal(PRESET, 'golden', 'a new example preset needs its stock drawn in tests/example-market.ts and named here');

const LAST = '2026-10-27';
const base = universe(12, 330, { last: LAST });
const days = (base.prices.IHSG as unknown[][]).map(r => r[0] as string), AS_OF = days[days.length - 9];
function market(): Publication {
  const u = universe(12, 330, { last: LAST });
  drawExampleStocks(u, days.indexOf(AS_OF));
  u.prices.LATE = (u.prices.T000 as unknown[][]).slice(-3).map(r => [...r]);          // listed after the date: no price by then
  u.ref.push(['LATE', 'Late listing', 'stock', 'Energy', 'Energy industry']);
  return { finished_at: `${LAST}T13:03:23Z`, ...u, actions: [['T001', days[days.length - 5], 'STOCK_SPLIT', 1, 2, null, null], ['T002', days[100], 'STOCK_SPLIT', 1, 2, null, null]],
    broker: Object.fromEntries(days.slice(-62, -2).map((d, k) => [d, brokerRowsOf(k + 1, d, ['T000', 'T001', 'T002'])])),
    brokers: [['AK', 'A', 'Local', 'Institutional-heavy'], ['BK', 'B', 'Foreign', 'Retail-heavy'], ['CC', 'C', 'Local', 'Mixed'], ['DX', 'D', 'Local', 'Institutional-heavy'], ['YP', 'Y', 'Local', 'Retail-heavy'], ['ZP', 'Z', 'Foreign', 'Mixed']] };
}
const p0 = market();
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
const shown: Record<string, Awaited<ReturnType<typeof screenOn>>> = {};
const onCut = async (preset: string) => shown[preset] ??= await screenOn(cutPublication(p0, AS_OF), ENV, preset, EDGE_CONTEXT);
const tickersOf = (run: any): string[] => (run.rows ?? []).map((r: any) => r.ticker);
/** the dates a run row and its cells carry (src/core contract: Row last_bar_date; Cell eval_date, event_date,
    last_event_date), each named: a row without them would check nothing */
function rowDates(r: any): (string | null)[] {
  assert.equal(typeof r.last_bar_date, 'string', `${r.ticker}: no last_bar_date`);
  assert.ok(Array.isArray(r.cells) && r.cells.length && r.cells.every((c: any) => 'eval_date' in c), `${r.ticker}: no cell eval_date`);
  return [r.last_bar_date, ...r.cells.flatMap((c: any) => [c.eval_date, c.event_date ?? null, c.last_event_date ?? null])];
}

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

for (const [preset, stock] of Object.entries(MATCHED)) {
  test(`the worker's ${preset} on the cut publication has its matches, depends on no row after the date and names no later date`, async () => {
    const one = await onCut(preset);
    // the screen checks something: the stock drawn for it matches on the date (example-market.ts)
    assert.ok(one.run.match_count > 0 && tickersOf(one.run).includes(stock), `${preset}: ${one.run.match_count} matches ${tickersOf(one.run)}`);
    const again = await screenOn(cutPublication(later(p0), AS_OF), ENV, preset, EDGE_CONTEXT);
    assert.deepEqual(again.catalog, one.catalog);
    assert.deepEqual(again.universe, one.universe);
    assert.deepEqual(without(again.run), without(one.run));
    assert.equal(one.catalog.data.evaluation_date, AS_OF);
    assert.equal(one.run.data.evaluation_date, AS_OF);
    assert.equal(one.catalog.data.published_at, AS_OF);
    assert.deepEqual(one.screen, { preset, name: one.screen.name, definition: one.catalog.presets.find((x: any) => x.id === preset).definition });
    const late = [...JSON.stringify([one.catalog, one.universe, one.run]).matchAll(/\d{4}-\d\d-\d\d/g)].map(m => m[0]).filter(d => d > AS_OF);
    assert.deepEqual([...new Set(late)], []);
    // every row and cell on or before the date, the drawn stock's evaluated on it
    assert.ok(one.run.rows.length > 0);
    for (const r of one.run.rows) assert.ok(rowDates(r).every(d => d === null || d <= AS_OF), `${r.ticker}: ${rowDates(r)}`);
    const drawn = one.run.rows.find((r: any) => r.ticker === stock);
    assert.equal(drawn.last_bar_date, AS_OF);
    assert.ok(drawn.cells.every((c: any) => c.eval_date === AS_OF), JSON.stringify(drawn.cells));
  });
}

test('red without the cut: the full publication gives other rows', async () => {
  const full = await screenOn({ ...p0, finished_at: AS_OF }, ENV, PRESET!, EDGE_CONTEXT);
  const cut = await onCut(PRESET!);
  assert.notDeepEqual(without(full.run).rows, without(cut.run).rows);
});
