/* A finished run's answers as edge-bff serves them (CONTRACT.md section 9; apps/edge-bff/app/backtest.py split_result
   and the /result and /events routes), for the test BacktestApis (fixture/api.ts, smoke/stub.ts):
   - /result: the part core, everything but events.conditions and events.exits; in single mode the ticker's part
     events:<ticker> merged back into events, so the run's events are all there;
   - /events?ticker=: that ticker's part, {conditions: its condition tracks, exits: {ticker: its exit track}}. */
import type { BacktestResult, BacktestResultCore, TickerEvents } from '../src/core/contract.ts';

export function servedEvents(r: BacktestResult, ticker: string): TickerEvents {
  return { conditions:r.events.conditions.filter(c => c.ticker === ticker), exits:ticker in r.events.exits ? { [ticker]:r.events.exits[ticker] } : {} };
}

export function servedResult(r: BacktestResult, singleTicker: string | null): BacktestResultCore {
  const { conditions: _conditions, exits: _exits, ...rest } = r.events;
  return { ...r, events:singleTicker === null ? rest : { ...rest, ...servedEvents(r, singleTicker) } };
}
