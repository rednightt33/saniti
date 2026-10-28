// Proof of composition (scratch only): VALUE / STATE / EVENT for the screener derived from the shared core without a
// new formula: calc.out (registry outputs), conditionSeries (0/1 series), entryNeed. Read-only.
import { readFileSync } from 'node:fs';
import { Calc, conditionSeries, entryNeed } from '/home/user/saniti/apps/edge-bff/backtest/src/core/conditions.ts';
import { BY_ID, resolveParams, ValidationError } from '/home/user/saniti/apps/edge-bff/backtest/src/core/registry.ts';
import { EXCLUDED_CODES } from '/home/user/saniti/apps/edge-bff/backtest/src/core/signals.ts';
const bars = JSON.parse(readFileSync(process.argv[2], 'utf8'));
const value = (c: Calc, id: string, params: any, output: string, at: number) => {
  const r = BY_ID[id]; const v = c.out(r.key, resolveParams(r, params))[output][at]; return v ?? null;
};
const state = (s: Uint8Array, at: number) => s[at] === 1;
const event = (s: Uint8Array, at: number, n: number, dates: string[]) => {
  for (let j = at; j > at - n && j >= 0; j--) if (s[j]) return { date: dates[j], sessions_ago: at - j };
  return null;
};
const safe = (c: Calc, cond: any) => { try { return conditionSeries(c, cond, 'c') } catch (e) { if (e instanceof ValidationError && EXCLUDED_CODES.includes(e.code)) return null; throw e } };
for (const t of ['BBCA', 'GOTO', 'MDLA', 'PMUI']) {
  const b = bars[t], c = new Calc(b), at = b.C.length - 1;
  const conds = {
    rsi_lt_30: { id: 'a', kind: 'indicator', indicator: 'I13', params: {}, lhs: { type: 'output', output: 'rsi' }, op: 'lt', rhs: { type: 'value', value: 30 } },
    close_gt_sma200: { id: 'b', kind: 'indicator', indicator: 'I01', params: { length: 200 }, lhs: { type: 'price' }, op: 'gt', rhs: { type: 'output', output: 'sma' } },
    macd_x_signal: { id: 'c', kind: 'indicator', indicator: 'I06', params: {}, lhs: { type: 'output', output: 'macd' }, op: 'crosses_above', rhs: { type: 'output', output: 'signal' } },
    st_flip_up: { id: 'd', kind: 'indicator', indicator: 'I09', params: {}, lhs: { type: 'output', output: 'direction' }, op: 'crosses_above', rhs: { type: 'value', value: 0 } },
    st_up: { id: 'e', kind: 'indicator', indicator: 'I09', params: {}, lhs: { type: 'output', output: 'direction' }, op: 'gt', rhs: { type: 'value', value: 0 } },
  };
  const s = Object.fromEntries(Object.entries(conds).map(([k, q]) => [k, safe(c, q)]));
  const out = {
    ticker: t, bars: b.C.length, date: b.T[at],
    rsi14: value(c, 'I13', {}, 'rsi', at), sma200: value(c, 'I01', { length: 200 }, 'sma', at),
    rsi_lt_30: s.rsi_lt_30 ? state(s.rsi_lt_30, at) : 'n/a', close_gt_sma200: s.close_gt_sma200 ? state(s.close_gt_sma200, at) : 'n/a',
    macd_x_signal_within_20: s.macd_x_signal ? event(s.macd_x_signal, at, 20, b.T) : 'n/a',
    st_flip_up_within_60: s.st_flip_up ? event(s.st_flip_up, at, 60, b.T) : 'n/a', st_up: s.st_up ? state(s.st_up, at) : 'n/a',
  };
  const met = [out.rsi_lt_30 === true, out.close_gt_sma200 === true, !!out.macd_x_signal_within_20 && out.macd_x_signal_within_20 !== 'n/a'].filter(Boolean).length;
  console.log(JSON.stringify({ ...out, met_of_3: met, need_all: entryNeed('all', undefined, 3), need_at_least_2: entryNeed('at_least', 2, 3) }));
}
