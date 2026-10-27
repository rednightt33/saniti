/* Daily foreign and broker flow of one ticker on its price bars, with the Terminal's definitions, and the rolling sums
   the backtest page's flow conditions read (backtest.html CATALOG fnet, broker, top5).

   Terminal definitions (edge-bff/terminal/src/data/worker.ts brokerData, app/flow.ts recomputeFlow, app/indicators.ts
   netBuyFlow / brokerLines):
   - net = buy value - sell value (IDR) per broker x investor type x board ("combo"), on each price session; a broker
     row on a date without a price bar is skipped (counted here in `unmatched_rows`);
   - foreign net (fnet) = the sum over every broker and board of investor type Foreign (flow.ts default filter: all
     brokers, all boards, investor Foreign); broker X = the sum over both investor types and every board of broker X
     (brokerLines default); sums are taken combo by combo in the combos' first-appearance order, as the Terminal adds
     them, so the values are the Terminal's to the last bit;
   - investor and board as flow.ts normInvestor and worker.ts board (datafile.ts admits only the Feature 05 values,
     for which both are the identity, Tunai -> Cash); fnet and broker sums take every board, so the board never
     changes a value here;
   - a price session without any broker row counts 0 (the Terminal's arrays start at 0 and only rows add to them);
     FLOW_DATA_CHECK.md found 3 such sessions for DGIK, 1 for BMSR, 0 for 10 other tickers; for the same reason a
     broker without any row on the ticker's price bars (it did not trade the ticker) has a net of 0 on every session
     with broker data (brokerNet), as a Terminal broker filter that matches no combo;
   - the publisher's `gap` markers (source_balance_gap, ERRORS M157: brokers missing from the 2016-2020 source) are not
     read by the Terminal; the values are kept as they are and the gap sessions are listed in `gap_bars`.
   Outside the sessions that have broker data (before the first and after the last price bar with a broker row, the
   Terminal's flowFrom / flowTo) there is no flow: the Terminal's Flow summary leaves those sessions out (flow.ts
   flowSummary), its indicator lines draw them as 0. Here they are NaN, so no flow condition or ranking reads a value
   on a session without broker data (broker files start in 2016, price packs in 2018; the broker data can end before
   the price data, FLOW_DATA_CHECK.md). Inside, every value equals the Terminal's.
   Pure module: no DOM and no Node API. */
import type { BrokerGap, BrokerRow } from './datafile.ts';

export interface FlowData {
  fnet: Float64Array;                      // per price bar: foreign net (IDR); NaN outside [from, to]
  brokers: Map<string, Float64Array>;      // per broker code with a row on a price bar: its net (IDR); NaN outside [from, to]
  from: number; to: number;                // first and last price bar with a broker row (from > to: none)
  gap_bars: number[];                      // price bars named by the publisher's gap markers (any board), ascending
  unmatched_rows: number;                  // broker rows on a date without a price bar (skipped, as the Terminal does)
}

const normInvestor = (s: string) => /foreign|asing/i.test(s) ? 'Foreign' : 'Domestic';      // terminal app/flow.ts
const board = (m: string) => /nego/i.test(m) ? 'Nego' : /cash|tunai/i.test(m) ? 'Cash' : 'Regular';   // terminal data/worker.ts

/** Broker rows (datafile.ts brokerRows) -> flow on the ticker's price bars (priceDates = PriceSeries.dates). */
export function flowData(rows: readonly BrokerRow[], priceDates: readonly string[], gaps: readonly BrokerGap[] = []): FlowData {
  const N = priceDates.length, idx = new Map<string, number>();
  priceDates.forEach((d, i) => idx.set(d, i));
  // the Terminal's combos in first-appearance order; on each bar its rows as [combo, net] in row order
  const comboOf = new Map<string, number>(), comboBroker: string[] = [], comboForeign: boolean[] = [];
  const perBar: ([number, number][] | undefined)[] = new Array(N);
  let from = N, to = -1, unmatched = 0;
  for (const r of rows) {
    const i = idx.get(r.d);
    if (i === undefined) { unmatched++; continue }
    if (i < from) from = i;
    if (i > to) to = i;
    const investor = normInvestor(r.i), key = `${r.b}|${investor}|${board(r.m)}`;
    let c = comboOf.get(key);
    if (c === undefined) { comboOf.set(key, c = comboBroker.length); comboBroker.push(r.b); comboForeign.push(investor === 'Foreign') }
    (perBar[i] ||= []).push([c, (r.bv || 0) - (r.sv || 0)]);
  }
  const fnet = new Float64Array(N).fill(NaN), brokers = new Map<string, Float64Array>();
  for (const b of comboBroker) if (!brokers.has(b)) brokers.set(b, new Float64Array(N).fill(NaN));
  for (let i = from; i <= to; i++) {
    fnet[i] = 0;
    for (const a of brokers.values()) a[i] = 0;
    const list = perBar[i];
    if (!list) continue;
    list.sort((x, y) => x[0] - y[0]);                  // stable: rows of one combo keep their order
    for (let k = 0; k < list.length;) {
      const c = list[k][0];
      let net = 0;                                     // the combo's value on this bar: 0 + its rows, as c.net[i] += ...
      for (; k < list.length && list[k][0] === c; k++) net += list[k][1];
      if (comboForeign[c]) fnet[i] += net;
      (brokers.get(comboBroker[c]) as Float64Array)[i] += net;
    }
  }
  const gap = new Set<number>();
  for (const g of gaps) { const i = idx.get(g.d); if (i !== undefined) gap.add(i) }
  return { fnet, brokers, from, to, gap_bars: [...gap].sort((a, b) => a - b), unmatched_rows: unmatched };
}

/** The net of broker `code` on the ticker's price bars: its series when it has a row on one of them, else 0 on every
    bar with broker data [from, to] (the broker did not trade the ticker; nothing adds to the Terminal's zeros) and
    NaN outside, as every flow series here. */
export function brokerNet(flow: FlowData, code: string): Float64Array {
  const a = flow.brokers.get(code);
  if (a) return a;
  const z = new Float64Array(flow.fnet.length).fill(NaN);
  for (let i = Math.max(0, flow.from); i <= flow.to; i++) z[i] = 0;
  return z;
}

/** The page's rollsum (running sum, first value at bar n-1 of the series) on the bars that have broker data
    [from, to]: NaN before from + n - 1 and after to. Where both have a value it equals the Terminal's netBuyFlow
    rolling sum (its zeros before `from` add nothing). */
export function rollingSum(a: ArrayLike<number>, n: number, from: number, to: number): Float64Array {
  const r = new Float64Array(a.length).fill(NaN);
  let s = 0;
  for (let i = Math.max(0, from); i <= to && i < a.length; i++) {
    s += a[i];
    if (i - from >= n) s -= a[i - n];
    if (i - from >= n - 1) r[i] = s;
  }
  return r;
}

/** The page's top-5 broker accumulation (CATALOG top5): on each bar, the n-bar net of every broker (rollsum), sorted
    from the biggest buyer down; the positive values among the first five plus the negative values among the last five,
    added in the page's order. The page starts at bar n of its series (not n - 1); its series starts here at `from`.
    NaN where it has no value. Brokers: every broker with a row on a price bar of the ticker. */
export function top5Accumulation(flow: FlowData, n: number): Float64Array {
  const N = flow.fnet.length, out = new Float64Array(N).fill(NaN);
  const sums = [...flow.brokers.values()].map(a => rollingSum(a, n, flow.from, flow.to));
  const m = sums.length, v = new Float64Array(m);
  for (let i = flow.from + n; i <= flow.to; i++) {
    for (let k = 0; k < m; k++) v[k] = sums[k][i];
    v.sort();                                          // ascending; the page's descending list is v read backwards
    let pos = 0, neg = 0;
    for (let k = m - 1; k >= Math.max(0, m - 5); k--) if (v[k] > 0) pos += v[k];      // desc.slice(0, 5), x > 0
    for (let k = Math.min(4, m - 1); k >= 0; k--) if (v[k] < 0) neg += v[k];          // desc.slice(-5), x < 0
    out[i] = pos + neg;
  }
  return out;
}
