/* 3e, the example mode (ERRORS M527): a made-up Backtest example for the tests, from the reference's synthetic market of
   the page's 1:1 check (tests/fixture/api.ts fixtureApi: ten demo stocks and IHSG with their broker data, every weekday
   of 2019-01-02..2026-10-23, from the reference's own generator; no market data), made the way the capture makes the
   real one (verification/edge_multiuser/example_mode):
     raw       the market's catalog with the worker's limits (what the capture reads from the worker)
     catalog   raw cut as the capture cuts it (terminal-publisher examples.py backtest_catalog: from the period's first
               day to the example's date, the broker date no later, the Flow indicators every plan may read)
     built_on  the part of the cut catalog the request is built on (tests/example-part.ts catalogPart)
     request   the page's own default request on built_on (S, applyCatalog, currentRequest), as backtest_request.ts
               builds the real one; checked to be the page's request on the whole cut catalog (ids aside)
     result    the market's answer to that request (submit, status, result: the reference's run through the core's result
               builder; in single mode the ticker's condition and exit tracks are part of it, as in the worker's)
     bars      the ticker's bars of the period, as the publisher's BARS_SQL rows [date, open, high, low, close, volume] */
import { S, applyCatalog } from '../src/state.ts';
import { setEnv } from '../src/env.ts';
import { currentRequest } from '../src/api/request.ts';
import { requestForm } from '../src/api/example.ts';
import type { BacktestRequest, BacktestResultCore, Catalog } from '../src/core/contract.ts';
import { fixtureApi } from './fixture/api.ts';
import { catalogPart } from './example-part.ts';

const FROM = S.from;                                     // the page's default start, before any catalog raised it

/** the page's own default request on a catalog: every card calculable (the example's run computes them all) */
export function defaultRequestOn(cat: Catalog): BacktestRequest {
  S.from = FROM;
  setEnv({ texts: {}, ready: () => true } as never, cat);
  applyCatalog();
  return currentRequest();
}

export interface MadeUp { raw: Catalog; catalog: Catalog; built_on: Catalog; request: BacktestRequest; result: BacktestResultCore;
  bars: [string, number, number, number, number, number][]; ticker: string }

export async function madeUpExample(asOf: string, first: string): Promise<MadeUp> {
  const api = fixtureApi();
  const market = await api.catalog();
  // the worker's limits (the reference has none on conditions, flow series or downloads)
  const raw: Catalog = { ...market, limits: { ...market.limits, max_conditions: 32, max_flow_series: 8, max_download_bytes: 1.5e9, max_broker_rows: 2e7 } };
  const catalog: Catalog = { ...raw, first_date: first, data_through: asOf,
    flow: { ...raw.flow, data_through: raw.flow.data_through && raw.flow.data_through < asOf ? raw.flow.data_through : asOf },
    flow_indicators: (raw.flow_indicators ?? []).filter(f => f.access === 'all') };
  const whole = defaultRequestOn(catalog), built_on = catalogPart(catalog, whole), request = defaultRequestOn(built_on);
  if (requestForm(request) !== requestForm(whole)) throw new Error('the page builds another request on the catalog part than on the whole catalog');
  if (request.mode !== 'single' || request.period.from !== first || request.period.to !== asOf)
    throw new Error(`the page's request is ${request.mode} ${request.period.from}..${request.period.to}, not single ${first}..${asOf}`);
  const { request_id } = await api.submit(request);
  let st = await api.status(request_id);
  while (st.state === 'RUNNING' || st.state === 'QUEUED') st = await api.status(request_id);
  if (st.state !== 'FINISHED') throw new Error(`the made-up run ended ${st.state}`);
  const result = await api.result(request_id);
  const b = await api.bars(request.single!.ticker, {});
  const bars = b.dates.map((d, k) => [d, b.o[k], b.h[k], b.l[k], b.c[k], b.v[k]] as [string, number, number, number, number, number])
    .filter(r => r[0] >= first && r[0] <= asOf);
  return { raw, catalog, built_on, request, result, bars, ticker: request.single!.ticker };
}
