/* 3e, the example mode (ERRORS M527): the part of the Backtest worker's catalog the example's request is built on
   (verification/edge_multiuser/example_mode/backtest_request.ts for the real example, tests/example-made-up.ts for the
   made-up one). The capture holds it next to the request (capture_backtest.json built_on) and stops when the worker's
   catalog, cut to the example's period, does not hold it as it is (terminal-publisher examples.py outside); the page
   then reads the stored catalog and builds the request that was run (src/api/example.ts answers only that one).
   The part keeps the catalog's dates, versions, flow block and limits, and cuts its lists to what the request names: its
   ticker as a stock, the brokers its conditions name, no grouping, no Flow indicator. tests/example.test.ts holds the
   rule to the page: on the made-up market the page's request on the part is its request on the whole catalog, so a
   field the default request comes to read outside the part fails there before an example is captured on it. */
import type { BacktestRequest, Catalog } from '../src/core/contract.ts';

/** every broker a request's conditions name (a 'broker' parameter at any depth), sorted */
export function brokersOf(q: BacktestRequest): string[] {
  const out = new Set<string>();
  JSON.stringify(q, (k, v) => { if (k === 'broker' && typeof v === 'string') out.add(v); return v });
  return [...out].sort();
}

/** the part of a catalog (already cut to the example's period) the request is built on */
export function catalogPart(cat: Catalog, q: BacktestRequest): Catalog {
  const t = q.single?.ticker, named = new Set(brokersOf(q));
  return {
    schema_version: cat.schema_version, engine_version: cat.engine_version, registry_version: cat.registry_version,
    first_date: cat.first_date, data_through: cat.data_through,
    tickers: cat.tickers.filter(x => x.ticker === t && x.type === 'stock').map(x => ({ ticker: x.ticker, type: x.type })),
    groupings: [],
    flow: { available: cat.flow.available, reason: cat.flow.reason, brokers: cat.flow.brokers.filter(b => named.has(b)),
            data_through: cat.flow.data_through },
    limits: cat.limits,
  } as unknown as Catalog;
}
