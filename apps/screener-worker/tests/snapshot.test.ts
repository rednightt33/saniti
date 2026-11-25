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
  // EXEC-PRICE-DISTORTION D-5: the actions file's optional basis column holds a status text or null per row
  const ex = u.prices.T001[200][0] as string;
  await assert.rejects(buildSnapshot(await input(u.prices, u.ref, [['T001', ex, 'STOCK_SPLIT', 1, 2, null, null, 7]])), integrity('actions'));
  const ok = await buildSnapshot(await input(u.prices, u.ref, [['T001', ex, 'STOCK_SPLIT', 1, 2, null, null, 'terms']]));
  assert.deepEqual(ok.desc.flowBasis, {}, 'no broker window loaded: no flow cell to mark');
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

test('price breaks (EXEC-PRICE-DISTORTION): the one rule of pricecheck.ts on the closes: a split whose jump is in the history flags the row on any date, one the history already absorbed does not, an action under 10 % from ADJUSTED_HISTORY_BOUNDARY on is uncertain, a session beyond 35 % with no action is an anomaly; after the last bar or a dividend does not', async () => {
  const u = market();
  const n = u.prices.T001.length, ex = u.prices.T001[n - 10][0] as string;
  assert.ok(ex >= ADJUSTED_HISTORY_BOUNDARY);
  // T001: a 1:5 split whose history before the ex-date is still on the old scale (raw: the close falls to a fifth)
  u.prices.T001 = u.prices.T001.map((b: unknown[], i: number) => i < n - 10 ? [b[0], ...(b.slice(1, 5) as number[]).map(x => x * 5), b[5]] : b);
  // T002: a 1:2 split before the boundary whose history is raw too (no date rule: it is flagged)
  const exOld = u.prices.T002[n - 80][0] as string;
  assert.ok(exOld < ADJUSTED_HISTORY_BOUNDARY);
  u.prices.T002 = u.prices.T002.map((b: unknown[], i: number) => i < n - 80 ? [b[0], ...(b.slice(1, 5) as number[]).map(x => x * 2), b[5]] : b);
  // T004: one wrong bar with no action (WGSH's case): half the close, then back
  const bad = n - 30;
  u.prices.T004 = u.prices.T004.map((b: unknown[], i: number) => i === bad ? [b[0], b[1], b[2], (b[4] as number) / 2, (b[4] as number) / 2, b[5]] : b);
  const actions = [
    ['T000', ex, 'STOCK_SPLIT', 1, 5, null, null],                       // adjusted already (the six stocks pulled again)
    ['T001', ex, 'STOCK_SPLIT', 1, 5, null, null],
    ['T002', exOld, 'STOCK_SPLIT', 1, 2, null, null],
    ['T003', ex, 'BONUS_SHARE', 20, 1, null, null],                      // effect 5 %: cannot be told from a day's move (UD43)
    ['T003', '2026-11-02', 'RIGHT_ISSUE', 10, 3, 500, 'IDR'],           // after the last bar (MGLV's case)
    ['T004', ex, 'DIVIDEND', null, null, 12.5, 'IDR'],                   // a cash dividend
  ];
  const { desc } = await buildSnapshot(await input(u.prices, u.ref, actions));
  const remarks = (t: string) => desc.rows.find(r => r.ticker === t)!.remarks.map(r => [(r as any).kind, (r as any).ex_date, (r as any).action]);
  assert.deepEqual(remarks('T000'), []);
  assert.deepEqual(remarks('T001'), [['unadjusted', ex, 'STOCK_SPLIT']]);
  assert.deepEqual(remarks('T002'), [['unadjusted', exOld, 'STOCK_SPLIT']]);
  assert.deepEqual(remarks('T003'), [['uncertain', ex, 'BONUS_SHARE']]);
  assert.deepEqual(remarks('T004'), [['anomaly', u.prices.T004[bad][0], 'PRICE_ANOMALY'], ['anomaly', u.prices.T004[bad + 1][0], 'PRICE_ANOMALY']]);
  // a stock with no action row at all is checked for the 35 % cap too (re-check 2026-11-25: the worker ran the rule only
  // for a ticker with actions, the Backtest for every ticker)
  const short = u.prices.SHORT.length;
  u.prices.SHORT = u.prices.SHORT.map((b: unknown[], i: number) => i === short - 20 ? [b[0], b[1], b[2], (b[4] as number) / 2, (b[4] as number) / 2, b[5]] : b);
  const again = await buildSnapshot(await input(u.prices, u.ref, actions));
  assert.deepEqual(again.desc.rows.find(r => r.ticker === 'SHORT')!.remarks.map(r => [(r as any).kind, (r as any).ex_date]),
    [['anomaly', u.prices.SHORT[short - 20][0]], ['anomaly', u.prices.SHORT[short - 19][0]]]);
  const split = desc.rows.find(r => r.ticker === 'T001')!.remarks[0] as any;
  assert.ok(Math.abs(split.close_ratio - 0.2) < 0.03 && Math.abs(split.effect - 4) < 1e-9, JSON.stringify(split));
});

test('groupings: the Backtest rule (backtest-worker catalog.ts groupingsOf) on the same reference file', () => {
  const ref = refOf([['IHSG', 'Composite', 'index', 'Undefined', 'Undefined'], ['BBCA', 'BCA', 'stock', 'Financials', 'Banks'], ['XCID', 'Fund', 'stock', 'Undefined', 'Undefined'],
    ['ADRO', 'Adaro', 'stock', 'Energy', 'Coal'], ['BMRI', 'Mandiri', 'stock', 'Financials', 'Banks'], ['ODD', 'Odd', 'stock', 'Energy', '']]);
  assert.deepEqual(groupingsOf(ref), backtestGroupings(ref));
  assert.deepEqual(groupingsOf(ref)[0], { key: 'sector', values: [{ value: 'Energy', tickers: 2 }, { value: 'Financials', tickers: 2 }], unclassified: 1 });
});
