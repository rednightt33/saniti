/* EXEC-BACKTEST-REVAMP P6.4: the look-ahead gate on real data (the CI gate, apps/backtest-worker/tests/lookahead.test.ts
   and pit.test.ts, runs on synthetic data). A value on day t may use only data up to t: for each ticker exported by
   export.sh (px.json, br.json), every series the Backtest reads is computed on the whole data and on the data cut at a
   few days t and at days where it changes (the CI gate's cuts.ts, re-check of 2026-11-25); every value on a day <= t
   must be equal. Covered: the 53 indicators at their defaults, the price-action
   types, the 20 candles, a set of grammar tests, the 41 clean Flow indicators at their defaults, and the 8 point-in-time
   indicators (anchor / start 60 sessions after the first broker day). P9: with the publisher's broker basis of the
   ticker (basis.json, verification/backtest/basis/basis_from_export.py) the lots are put on the price basis and the
   corporate actions are in the data (kept whole at every cut: the basis is part of the published price history); the
   report counts the sessions still off the price basis with and without the factors. Read-only, nothing written but the
   report.
     node --experimental-strip-types --no-warnings --import ../../../apps/backtest-worker/loader/register.mjs \
       real_data.ts out/BBRI out/GOTO ... > report.json */
import fs from 'node:fs';
import { DEFAULTS } from '../../../apps/edge-bff/terminal/src/calc/indicators.ts';
import { Calc, PRICE_ACTION, conditionSeries } from '../../../apps/edge-bff/backtest/src/core/conditions.ts';
import { CANDLE_IDS } from '../../../apps/edge-bff/backtest/src/core/candles.ts';
import type { BrokerColumns } from '../../../apps/edge-bff/backtest/src/core/datafile.ts';
import { REGISTRY, ValidationError } from '../../../apps/edge-bff/backtest/src/core/registry.ts';
import { FLOWS } from '../../../apps/backtest-worker/tests/lookahead/flow-helpers.ts';
import { installBacktestGrammar, seriesOfRef } from '../../../apps/backtest-worker/src/grammar.ts';
import { offBasisCount } from '../../../apps/backtest-worker/src/basis.ts';
import { brokerBasis, onPriceBasis } from '../../../apps/edge-bff/backtest/src/core/datafile.ts';
import type { BasisAction } from '../../../apps/edge-bff/backtest/src/core/datafile.ts';
import { changeBars, cutsOf } from '../../../apps/edge-bff/screener/tests/core/cuts.ts';

installBacktestGrammar();
type Doc = { columns: string[]; rows: unknown[][] };
const read = (f: string): Doc => JSON.parse(fs.readFileSync(f, 'utf8'));

function load(dir: string) {
  const px = read(`${dir}/px.json`), br = read(`${dir}/br.json`);
  const dates = px.rows.map(r => String(r[0])), col = (k: number) => px.rows.map(r => r[k] === null ? null : Number(r[k]));
  const bars = { O: col(1), H: col(2), L: col(3), C: col(4), V: col(5), T: dates };
  const rows = br.rows.map(r => ({ d: String(r[0]), b: String(r[1]), i: String(r[2]), m: String(r[3]), bv: Number(r[4]), sv: Number(r[5]), bl: Number(r[6]), sl: Number(r[7]),
    bf: r[8] === null ? NaN : Number(r[8]), sf: r[9] === null ? NaN : Number(r[9]) }));
  // P9: the publisher's broker basis of the ticker (verification/backtest/basis/basis_from_export.py), when written
  const basis: BasisAction[] = fs.existsSync(`${dir}/basis.json`) ? brokerBasis([{ columns: [], basis: read(`${dir}/basis.json`) } as never], []) : [];
  return { ticker: dir.split('/').pop()!, dates, bars, rows, basis };
}
function columns(rows: ReturnType<typeof load>['rows']): BrokerColumns {
  const dates: string[] = [], brokers: string[] = [], at = new Map<string, number>(), inv = ['Foreign', 'Domestic'], brd = ['Regular', 'Nego', 'Tunai'];
  const D: number[] = [], B: number[] = [], I: number[] = [], M: number[] = [], V: number[][] = [[], [], [], [], [], []];
  for (const r of rows) {
    if (dates[dates.length - 1] !== r.d) dates.push(r.d);
    if (!at.has(r.b)) { at.set(r.b, brokers.length); brokers.push(r.b) }
    D.push(dates.length - 1); B.push(at.get(r.b)!); I.push(inv.indexOf(r.i)); M.push(brd.indexOf(r.m === 'Cash' ? 'Tunai' : r.m));
    [r.bv, r.sv, r.bl, r.sl, r.bf, r.sf].forEach((x, k) => V[k].push(x));
  }
  const f = (a: number[]) => Float64Array.from(a);
  return { rows: D.length, dates, brokers, investor_types: inv, boards: brd, D: Int32Array.from(D), B: Int32Array.from(B), I: Uint8Array.from(I), M: Uint8Array.from(M),
    BV: f(V[0]), SV: f(V[1]), BL: f(V[2]), SL: f(V[3]), BF: f(V[4]), SF: f(V[5]) };
}

const near = (a: unknown, b: unknown) => {
  const x = typeof a === 'number' && Number.isFinite(a) ? a : null, y = typeof b === 'number' && Number.isFinite(b) ? b : null;
  return x === y || (x !== null && y !== null && Math.abs(x - y) <= 1e-9 * Math.max(1, Math.abs(x)));
};

function check(dir: string) {
  const T = load(dir), N = T.dates.length;
  const cut = (n: number) => {
    const last = T.dates[n - 1], s = <V,>(a: V[]) => a.slice(0, n);
    return new Calc({ O: s(T.bars.O), H: s(T.bars.H), L: s(T.bars.L), C: s(T.bars.C), V: s(T.bars.V), T: s(T.dates) } as never, undefined,
      { ticker: T.ticker, dates: s(T.dates), broker: { columns: onPriceBasis(columns(T.rows.filter(r => r.d <= last)), T.basis), classification: {}, basis: T.basis } });
  };
  const cuts = [0.35, 0.55, 0.75, 0.9].map(f => Math.floor(N * f));
  const full = cut(N), parts = new Map(cuts.map(k => [k, cut(k)]));
  const firstBroker = T.rows.length ? T.rows[0].d : null, i0 = firstBroker ? T.dates.findIndex(d => d >= firstBroker) : -1;
  const anchor = i0 >= 0 ? T.dates[Math.min(N - 1, i0 + 60)] : null;
  const leaks: string[] = [], refused: string[] = [], groups: Record<string, number> = {}, unchanged: string[] = [];
  let series = 0, group = '', derived = 0;
  // the four fixed cuts and, per series, cuts on bars where it changes (apps/edge-bff/screener/tests/core/cuts.ts, the CI
  // gate's rule; re-check of 2026-11-25, recheck2/NEW-1: a read of the next bar in a sparse series shows only there);
  // a derived cut's data is built for its series and not kept (a cut of a long broker history is large)
  const run = (name: string, f: (c: Calc) => ArrayLike<unknown> | null) => {
    let s: ArrayLike<unknown> | null;
    try { s = f(full) } catch (e) { if (e instanceof ValidationError) { refused.push(`${name}: ${e.code}`); return } throw e }
    if (!s) return;
    series++; groups[group] = (groups[group] ?? 0) + 1;
    // a series that never changes after the first cut cannot show a read of a later bar (listed, not a leak)
    if (!changeBars(s, N).some(j => j >= cuts[0] - 1 && j <= N - 2)) unchanged.push(name);
    for (const k of cutsOf(s, N, cuts.map(x => x - 1)).map(c => c + 1)) {
      if (!parts.has(k)) derived++;
      let p: ArrayLike<unknown> | null;
      try { p = f(parts.get(k) ?? cut(k)) } catch (e) { if (e instanceof ValidationError) continue; throw e }
      for (let i = 0; i < k; i++) if (!near(s![i], p?.[i])) { leaks.push(`${name}: ${T.dates[i]} (cut ${T.dates[k - 1]})`); break }
    }
  };
  group = 'indicators';
  for (const r of REGISTRY.indicators) for (const o of r.outputs) run(`${r.id}.${o}`, c => c.out(r.key, { ...DEFAULTS[r.key] })[o]);
  group = 'price_action';
  for (const [type, spec] of Object.entries(PRICE_ACTION)) for (const op of spec.ops)
    run(`price_action ${type} ${op}`, c => conditionSeries(c, { id: 'p', kind: 'price_action', type, op, ...(spec.value ? { value: type === 'dip' ? -0.03 : 1.5 } : {}) } as never, 'p'));
  group = 'candles';
  for (const id of CANDLE_IDS) run(`candle ${id}`, c => conditionSeries(c, { id: 'k', kind: 'test', test: { kind: 'state', pattern: { kind: 'pattern', type: id, params: {} } } } as never, 'k'));
  const rsi = { kind: 'indicator', indicator: 'I13', output: 'rsi', params: {} }, close = { kind: 'price', field: 'close' };
  const tests: Record<string, unknown> = {
    value: { kind: 'value', metric: rsi, op: 'lt', value: 35 }, event: { kind: 'event', within: 5, signal: { lhs: rsi, op: 'crosses_above', rhs: { value: 50 } } },
    zscore: { kind: 'value', metric: { kind: 'transform', fn: 'zscore', of: close, args: { length: 60 } }, op: 'gt', value: 1 },
    window: { kind: 'window', mode: 'at_least', length: 20, count: 5, test: { kind: 'state', lhs: close, op: 'gt', rhs: { kind: 'indicator', indicator: 'I01', output: 'sma', params: {} } } },
  };
  group = 'grammar';
  for (const [k, t] of Object.entries(tests)) run(`grammar ${k}`, c => conditionSeries(c, { id: 'g', kind: 'test', test: t } as never, 'g'));
  group = 'flow_a_c';
  for (const e of FLOWS) for (const o of e.outputs) run(`${e.id}.${o}`, c => seriesOfRef(c, { kind: 'flow', metric: e.id, output: o, params: {} }, 'f'));
  group = 'point_in_time';
  if (anchor) {
    for (const id of ['FL18', 'FL19', 'FL20', 'FL44', 'FL45']) for (const o of ['value', 'cohort_changed']) run(`${id}.${o} (point in time)`, c => seriesOfRef(c, { kind: 'flow', metric: id, output: o, params: { anchor } }, 'f'));
    for (const o of ['total', 'cohort_changed']) run(`FL23.${o} (point in time)`, c => seriesOfRef(c, { kind: 'flow', metric: 'FL23', output: o, params: { start: anchor } }, 'f'));
    for (const o of ['cost', 'distance', 'share', 'cohort_changed']) run(`FL51.${o} (point in time)`, c => seriesOfRef(c, { kind: 'flow', metric: 'FL51', output: o, params: { start: anchor } }, 'f'));
  }
  // P9: the sessions still off the price basis after the factors (their broker-price values stay empty), without them
  const plain = new Calc(T.bars as never, undefined, { ticker: T.ticker, dates: T.dates, broker: { columns: columns(T.rows), classification: {} } });
  const basis = T.basis.map(a => [a.ex, a.type, a.status, a.factor, a.price]);
  return { ticker: T.ticker, bars: N, from: T.dates[0], to: T.dates[N - 1], broker_rows: T.rows.length, cuts: cuts.map(k => T.dates[k - 1]), derived_cuts: derived, anchor,
    basis, off_basis_sessions: offBasisCount(full), off_basis_sessions_without_factors: offBasisCount(plain), series, groups, leaks, refused, unchanged };
}

const report = process.argv.slice(2).map(check);
console.log(JSON.stringify(report, null, 1));
if (report.some(r => r.leaks.length)) process.exitCode = 1;
