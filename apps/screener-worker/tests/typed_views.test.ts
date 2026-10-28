/* TEST PLAN 10b.1 "F on typed views = plain arrays" (report 6.4 Threads: the bars move to SharedArrayBuffer columns only
   after a bit-parity test of F): the worker never runs F on a typed view; it reads each ticker's bars back from the
   shared columns into plain arrays (snapshot.ts materialize). This holds the round trip value for value against the
   backtest core's priceSeries, and every output of the 53 indicators at their start configuration bit for bit, on
   tickers with a short history (74 bars, RANS), a flat window, an index without volume and a stale stock. */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { priceSeries } from '../../edge-bff/backtest/src/core/datafile.ts';
import { F } from '../../edge-bff/terminal/src/calc/indicators.ts';
import { INDICATORS, startParams } from '../../edge-bff/screener/src/core/registry.ts';
import { buildSnapshot, materialize } from '../src/snapshot.ts';
import { pricePack } from '../../backtest-worker/tests/fake-terminal.mjs';
import { CAP, input, market } from './fixtures.ts';

test('typed views: the bars read back from the shared columns equal priceSeries value for value, and F gives bit-identical outputs on them (TEST PLAN 10b.1)', async () => {
  const u = market(), { desc } = await buildSnapshot(await input(u.prices, u.ref));
  const same = (a: ArrayLike<unknown>, b: ArrayLike<unknown>, what: string) => {
    assert.equal(a.length, b.length, what);
    for (let i = 0; i < a.length; i++) if (!Object.is(a[i], b[i])) assert.fail(`${what}[${i}]: ${String(a[i])} vs ${String(b[i])}`);
  };
  let compared = 0;
  for (const [j, t] of desc.tickers.entries()) {
    const want = priceSeries(t, [JSON.parse(JSON.stringify(pricePack(t, u.prices[t])))]), got = materialize(desc, j);
    assert.deepEqual(got.dates, want.dates);
    for (const k of ['O', 'H', 'L', 'C', 'V', 'T'] as const) same(got.bars[k] as ArrayLike<unknown>, want.bars[k] as ArrayLike<unknown>, `${t}.${k}`);
    for (const ind of INDICATORS) {
      const p = startParams(ind, { capBudgetMs: CAP }), a = F[ind.key](want.bars, p), b = F[ind.key](got.bars, p);
      for (const o of ind.outputs) { same(b[o.key], a[o.key], `${t} ${ind.id}.${o.key}`); compared++ }
    }
  }
  assert.equal(compared, desc.tickers.length * 76);
  const ihsg = materialize(desc, desc.index);
  assert.ok(ihsg.bars.V.every(v => v === null), 'IHSG keeps a null volume, never 0 or NaN');
});

