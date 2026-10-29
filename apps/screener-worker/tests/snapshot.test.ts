/* The snapshot (snapshot.ts; report 6.5, 6.7; TEST PLAN 10b.1 typed views, 10b.4 evaluation date, version stability,
   price breaks, 10b.5 sector source): built from files in the publisher's format (tests/fake-terminal.mjs), checked
   against the backtest core's own decoding and the screener core's own functions. */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { DataError, dataVersion } from '../../edge-bff/backtest/src/core/datafile.ts';
import { ADJUSTED_HISTORY_BOUNDARY } from '../../edge-bff/backtest/src/core/engine.ts';
import { SeriesCache, series, seriesKey, tickerCalc, universeAttributes } from '../../edge-bff/screener/src/core/metrics.ts';
import { presetDefinitions } from '../../edge-bff/screener/src/core/validate.ts';
import { declaredDerivedSeries } from '../../edge-bff/screener/src/core/condition.ts';
import { round12 } from '../../edge-bff/screener/src/core/evaluate.ts';
import { groupingsOf as backtestGroupings } from '../../backtest-worker/src/catalog.ts';
import { ThreadSnapshot, buildSnapshot, groupingsOf, materialize, pinnedTail, prewarmChunk, resolvePinned, snapshotDigest } from '../src/snapshot.ts';
import { encode, pricePack } from '../../backtest-worker/tests/fake-terminal.mjs';
import { xsectionPriceDoc } from './fake-terminal.mjs';
import { CAP, decode, input, market, refOf, state } from './fixtures.ts';

const integrity = (field?: string) => (e: unknown) => { assert.ok(e instanceof DataError && e.code === 'DATA_INTEGRITY', String(e)); if (field) assert.equal((e as DataError).field, field); return true };

test('the snapshot: price_data over every ticker\'s pack sha256, E = price_through, the stock rows from the core\'s own functions, IHSG apart', async () => {
  const u = market(), inp = await input(u.prices, u.ref), { desc, entries, stats } = await buildSnapshot(inp);
  const packs = Object.keys(u.prices).sort().map(t => ({ ticker: t, dataset: 'price', sha256: encode(pricePack(t, u.prices[t])).sha256 }));
  assert.equal(desc.versions.price_data, await dataVersion(packs));
  assert.deepEqual(entries.map(e => e.t), Object.keys(u.prices).sort());
  assert.equal(desc.data.evaluation_date, '2026-10-27');
  assert.equal(desc.data.published_at, '2026-10-27T13:03:23Z');
  assert.equal(stats.stocks, Object.keys(u.prices).length - 1);
  assert.ok(!desc.rows.some(r => r.ticker === 'IHSG'), 'IHSG is never a stock row');
  for (const r of desc.rows) {
    const j = desc.tickers.indexOf(r.ticker), a = universeAttributes(tickerCalc(materialize(desc, j)), '2026-10-27');
    assert.deepEqual({ last: r.last, chg_1d_pct: r.chg_1d_pct, adv20_idr: r.adv20_idr, bars: r.bars, stale: r.stale, last_bar: r.last_bar },
      { last: round12(a.last), chg_1d_pct: round12(a.chg_1d_pct), adv20_idr: round12(a.adv20_idr), bars: a.bars, stale: a.stale, last_bar: a.last_bar }, 'the core\'s attributes at 12 significant digits (the wire)');
  }
  const stale = desc.rows.find(r => r.ticker === 'STALE')!;
  assert.deepEqual(stale.remarks, [{ code: 'STALE', last_bar_date: '2026-08-21' }]);
  assert.equal(desc.rows.find(r => r.ticker === 'FLAT')!.sector, null, "the source's Undefined is no classification");
  // without price_through E is the newest bar of the file
  const { desc: d2 } = await buildSnapshot({ ...inp, state: state({ price_through: null }) });
  assert.equal(d2.data.evaluation_date, '2026-10-27');
});

test('version stability: the same files give the same price_data, sid and digest; one changed bar changes them (TEST PLAN 10b.4)', async () => {
  const u = market();
  const build = async (prices: Record<string, unknown[][]>) => { const { desc } = await buildSnapshot(await input(prices, u.ref)); prewarmChunk(desc, 0, desc.tickers.length, CAP); return { v: desc.versions.price_data, sid: desc.sid, digest: snapshotDigest(desc) } };
  const a = await build(u.prices), b = await build(JSON.parse(JSON.stringify(u.prices)));
  assert.deepEqual(a, b);
  const changed = JSON.parse(JSON.stringify(u.prices));
  changed.T001[changed.T001.length - 1][4] += 1;
  const c = await build(changed);
  assert.notEqual(c.v, a.v); assert.notEqual(c.digest, a.digest);
});

test('the pre-warm: the 53 at their start configuration (76 outputs), the declared derived series and the presets\' series, each tail equal to the dynamic series() on the same bars', async () => {
  const u = market(), presets = presetDefinitions().filter(p => ['golden', 'brk52', 'squeeze', 'minervini'].includes(p.id));
  const { desc, stats } = await buildSnapshot(await input(u.prices, u.ref, [], { presets: [...presets] }));
  assert.ok(stats.series > 76, `the presets add series: ${stats.series}`);
  assert.equal(desc.series.slice(0, 76).length, 76);
  const half = Math.floor(desc.tickers.length / 2);
  prewarmChunk(desc, 0, half, CAP); prewarmChunk(desc, half, desc.tickers.length, CAP);     // two chunks, as two threads would
  const dv = { price_data: desc.versions.price_data, screener_engine: desc.versions.screener_engine };
  const fresh = { versions: dv, tailLength: desc.tailLength, cache: new SeriesCache(1e9) };
  const ihsg = materialize(desc, desc.index);
  let patterns = 0;
  for (const [s, { ref, key }] of desc.series.entries()) {
    if (ref.kind === 'pattern') patterns++;
    const r = resolvePinned(ref, 'x', { capBudgetMs: CAP, index: ihsg });
    assert.equal(seriesKey(dv, r), key);
    for (const j of [0, desc.index, desc.tickers.indexOf('SHORT'), desc.tickers.indexOf('FLAT')]) {
      const want = series(fresh, tickerCalc(materialize(desc, j)), r).tail, got = pinnedTail(desc, s, j);
      assert.deepEqual({ n: got.n, from: got.from, firstValid: got.firstValid, lastValid: got.lastValid }, { n: want.n, from: want.from, firstValid: want.firstValid, lastValid: want.lastValid });
      assert.deepEqual([...got.values], [...want.values], `${key} on ${desc.tickers[j]}`);
    }
  }
  assert.ok(patterns > 0, 'the presets\' pattern signals are pinned too');
  // every series a default card reads is pinned (core condition.ts declaredDerivedSeries: bar fields, the Donchian
  // prior bands, the rising lags and vs-MA averages), so a default card is a snapshot lookup (stage S2)
  const pinnedKeys = new Set(desc.series.map(x => x.key)), declared = declaredDerivedSeries({ capBudgetMs: CAP, index: ihsg });
  assert.ok(declared.some(r => r.label === 'lag(I10.upper, 1)'), 'the Donchian prior band is declared');
  for (const r of declared) assert.ok(pinnedKeys.has(seriesKey(dv, r)), `${r.label} is pinned`);
  // a thread installs them as pinned entries: a lookup is 'precomputed'
  const snap = new ThreadSnapshot(desc, 1e6), r0 = resolvePinned(desc.series[0].ref, 'x', { capBudgetMs: CAP, index: ihsg });
  const hit = series({ versions: snap.dv, tailLength: desc.tailLength, cache: snap.cache }, tickerCalc(snap.bars('T001')), r0);
  assert.equal(hit.source, 'precomputed');
});

test('integrity: a price ticker outside the reference file, a tickers list that does not cover the columns, rows out of ticker order, a slice that is not its entry, no IHSG', async () => {
  const u = market();
  await assert.rejects(buildSnapshot(await input(u.prices, u.ref.filter(r => r[0] !== 'T002'))), integrity('ref'));
  const doc = JSON.parse(JSON.stringify(xsectionPriceDoc(u.prices)));
  const withDoc = async (d: object) => buildSnapshot({ ...(await input(u.prices, u.ref)), price: await decode(d) });
  await assert.rejects(withDoc({ ...doc, tickers: doc.tickers.map((e: any, i: number) => i === 1 ? { ...e, rows: e.rows - 1 } : e) }), integrity());
  await assert.rejects(withDoc({ ...doc, tickers: [...doc.tickers].reverse() }), integrity());
  await assert.rejects(withDoc({ ...doc, tickers: doc.tickers.map((e: any, i: number) => i === 2 ? { ...e, last: '2026-10-26' } : e) }), integrity());
  await assert.rejects(withDoc({ ...doc, t: doc.t.map((t: string, i: number) => i === 5 ? 'T004' : t) }), integrity());
  const noIndex = Object.fromEntries(Object.entries(u.prices).filter(([t]) => t !== 'IHSG'));
  await assert.rejects(buildSnapshot(await input(noIndex, u.ref)), (e: unknown) => e instanceof DataError && e.code === 'DATA_MISSING');
});

test('no look-ahead (6.5 as-of policy): a price file with a bar after its publication\'s price_through is refused (DATA_INTEGRITY), never evaluated past E or off its tails', async () => {
  const u = market(), inp = await input(u.prices, u.ref);
  // the fixture ends on 2026-10-27; a state naming 2026-10-26 is torn (a session loaded while the publisher ran)
  await assert.rejects(buildSnapshot({ ...inp, state: state({ price_through: '2026-10-26' }) }), (e: unknown) => integrity('price')(e) && /after the publication's price_through 2026-10-26/.test((e as Error).message));
  // must not apply: price_through on the newest bar, or later (no session after it yet), loads
  for (const through of ['2026-10-27', '2026-10-28']) {
    const { desc } = await buildSnapshot({ ...inp, state: state({ price_through: through }) });
    assert.equal(desc.data.evaluation_date, through);
  }
});

test('price breaks (P4): a price-affecting action from ADJUSTED_HISTORY_BOUNDARY to the last bar flags the row; before the boundary, after the last bar, or a dividend does not', async () => {
  const u = market();
  const ex = u.prices.T001[u.prices.T001.length - 10][0] as string;
  assert.ok(ex >= ADJUSTED_HISTORY_BOUNDARY);
  const actions = [
    ['T001', ex, 'STOCK_SPLIT', 1, 5, null, null],
    ['T002', '2026-07-16', 'STOCK_SPLIT', 1, 2, null, null],             // before the boundary (RAJA's case)
    ['T003', '2026-11-02', 'RIGHT_ISSUE', 10, 3, 500, 'IDR'],           // after the last bar (MGLV's case)
    ['T004', ex, 'DIVIDEND', null, null, 12.5, 'IDR'],                   // a cash dividend
  ];
  const { desc } = await buildSnapshot(await input(u.prices, u.ref, actions));
  const remarks = (t: string) => desc.rows.find(r => r.ticker === t)!.remarks;
  assert.deepEqual(remarks('T001').map(r => [r.code, (r as any).ex_date, (r as any).action]), [['PRICE_BREAK', ex, 'STOCK_SPLIT']]);
  for (const t of ['T002', 'T003', 'T004']) assert.deepEqual(remarks(t), [], t);
});

test('groupings: the Backtest rule (backtest-worker catalog.ts groupingsOf) on the same reference file', () => {
  const ref = refOf([['IHSG', 'Composite', 'index', 'Undefined', 'Undefined'], ['BBCA', 'BCA', 'stock', 'Financials', 'Banks'], ['XCID', 'Fund', 'stock', 'Undefined', 'Undefined'],
    ['ADRO', 'Adaro', 'stock', 'Energy', 'Coal'], ['BMRI', 'Mandiri', 'stock', 'Financials', 'Banks'], ['ODD', 'Odd', 'stock', 'Energy', '']]);
  assert.deepEqual(groupingsOf(ref), backtestGroupings(ref));
  assert.deepEqual(groupingsOf(ref)[0], { key: 'sector', values: [{ value: 'Energy', tickers: 2 }, { value: 'Financials', tickers: 2 }], unclassified: 1 });
});
