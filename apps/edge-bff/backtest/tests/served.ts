/* A finished run's answers as edge-bff serves them (CONTRACT.md section 9; apps/edge-bff/app/backtest.py split_result
   and the /result and /events routes), for the test BacktestApis (fixture/api.ts, smoke/stub.ts):
   - /result: the part core, everything but events.conditions and events.exits; in single mode the ticker's part
     events:<ticker> merged back into events, so the run's events are all there;
   - /events?ticker=: that ticker's part, {conditions: its condition tracks, exits: {ticker: its exit track}}, for every
     ticker of the run (meta.tickers) and every ticker its events name; any other ticker has no part: 404
     EVENTS_NOT_FOUND (field ticker), as the live page's ApiFailure of that answer (src/api/live.ts failure). */
import type { BacktestResult, BacktestResultCore, TickerEvents } from '../src/core/contract.ts';
import { ApiFailure } from '../src/api/types.ts';

export function servedEvents(r: BacktestResult, ticker: string): TickerEvents {
  const parts = new Set([...r.meta.tickers, ...r.events.conditions.map(c => c.ticker), ...Object.keys(r.events.exits), ...Object.keys(r.events.entries)]);
  if (!parts.has(ticker)) throw new ApiFailure('The backtest service answered 404 (EVENTS_NOT_FOUND).', 'EVENTS_NOT_FOUND', 404, 'ticker');
  return { conditions:r.events.conditions.filter(c => c.ticker === ticker), exits:ticker in r.events.exits ? { [ticker]:r.events.exits[ticker] } : {} };
}

export function servedResult(r: BacktestResult, singleTicker: string | null): BacktestResultCore {
  const { conditions: _conditions, exits: _exits, ...rest } = r.events;
  return { ...r, events:singleTicker === null ? rest : { ...rest, ...servedEvents(r, singleTicker) } };
}
