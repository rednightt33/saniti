/* In-process profile of one flow condition on the benchmark market (verification/screener/BENCH_FLOW_COST.md method):
   the snapshot built as the builder thread builds it, one compute thread's view (ThreadSnapshot), runTask on the
   universe named by PROFILE_UNIVERSE (all, large, small), PROFILE_FL (default FL10), repeated PROFILE_RUNS times with
   fresh parameters (memo-cold each time). Run with --cpu-prof to see where a ticker's time goes. */
import { inflateVerified } from '../../../edge-bff/backtest/src/core/datafile.ts';
import { METRICS_CATALOG } from '../../../edge-bff/screener/src/core/catalog.ts';
import { availabilityMap } from '../../../edge-bff/screener/src/core/validate.ts';
import type { ValidateContext } from '../../../edge-bff/screener/src/core/validate.ts';
import { decodeBrokerDay } from '../../src/broker.ts';
import { normalize, runTask } from '../../src/run.ts';
import { ThreadSnapshot, buildSnapshot, flowContextOf, groupingsOf } from '../../src/snapshot.ts';
import { encodeBrokerDay, xsectionBrokerDoc } from '../fake-terminal.mjs';
import { CAP, WITHIN, input } from '../fixtures.ts';
import { BROKER, DAYS, LARGE, SMALL, U0 } from './market.ts';

const base = await input(U0.prices, U0.ref);
const days = await Promise.all(DAYS.map(async d => {
  const e = encodeBrokerDay(xsectionBrokerDoc(d, BROKER[d]));
  return decodeBrokerDay(await inflateVerified(new Uint8Array(e.body), { sha256: e.sha256, bytes: e.body.length }), `broker-${d}`, e.sha256);
}));
const { desc } = await buildSnapshot({ ...base, broker: { days, carry: null, missing: 0 } });
const vctx: ValidateContext = { limits: { max_conditions: 20, max_metric_filters: 8, within_max: WITHIN }, capBudgetMs: CAP, tickers: new Set(desc.rows.map(r => r.ticker)),
  groupings: groupingsOf(base.ref), metrics: METRICS_CATALOG, availability: availabilityMap({}, METRICS_CATALOG, undefined, flowContextOf(desc)), flow: flowContextOf(desc) };
const snap = new ThreadSnapshot(desc, 64 * 2 ** 20), ENV = { capBudgetMs: CAP, withinMax: WITHIN, maxResponseBytes: 64 << 20 };
const which = process.env.PROFILE_UNIVERSE ?? 'small', id = process.env.PROFILE_FL ?? 'FL10', runs = Number(process.env.PROFILE_RUNS ?? 4);
const tickers = which === 'large' ? LARGE : which === 'small' ? SMALL : undefined;
for (let k = 0; k < runs; k++) {
  const d = { universe: { security_types: ['stock'], traded_on_eval_date: false, exclude_price_breaks: false, ...(tickers ? { tickers } : {}) }, logic: 'all',
    conditions: [{ id: 'a', enabled: true, test: { kind: 'value', metric: { kind: 'flow', metric: id, params: { window: 3 + k } }, op: 'gt', value: -1e12 } }] };
  const n = await normalize(d, vctx), t0 = performance.now();
  const o = runTask({ kind: 'run', sid: desc.sid, definition: n.normalized, hash: n.hash, options: { exhaustive: true, explain: false }, queue_ms: 0, s0_ms: 0, versions: desc.versions, data: desc.data }, snap, ENV, () => false);
  console.log(`PROFILE ${id} ${which} run ${k} ms ${Math.round(performance.now() - t0)} busy ${o.busy_ms} observe ${JSON.stringify(o.observe.map(x => [x.units.map(u => u.key).join('+'), Math.round(x.ms), x.bars, x.series]))}`);
}
