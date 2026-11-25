/* The synthetic broker context the flow probes run on (EXEC-SCREENER-FLOW-CANDLES P5a; verification/screener/P5_FLOW.md
   sections 1 and 2): flowmetrics.ts indicatorDepth (K1: the sessions an indicator reads back) and the registry
   generator's display-only probe (scripts/build-screener-registry.mjs flowEntries: a parameter whose every option gives
   the same values is not a condition parameter, QA unit B, QA5) and its basis probe (basisReads, EXEC-PRICE-DISTORTION
   D-5: which outputs read the broker lots, the close or the volume; the perturbations below). One module for all, so the
   probes read the same rows; it imports only the Terminal's flow types (no generated file), so the generator can load it.
   Pure module (no DOM, no Node API). */
import type { FlowContext, FlowRows, Num } from '../../../terminal/src/calc/flow.ts';

const PROBE_BROKERS = 44;
/** A synthetic context of L candles with broker data on every candle, for the probes: 44 brokers trading every candle
    on both investor types and the Regular board (a third of them on Nego, a third on Cash too), the first 22 net buyers
    and the others net sellers on every candle, transaction counts everywhere, varying prices and volumes, and a
    classification with institutional and retail brokers, so every indicator has a value as soon as its windows fit. */
export function probeContext(L: number): FlowContext {
  const brokers = Array.from({ length: PROBE_BROKERS }, (_, b) => `B${String(b).padStart(2, '0')}`);
  const per: [number, number, number][] = [];                         // [broker, investor, board] of one candle
  for (let b = 0; b < PROBE_BROKERS; b++) for (const inv of [0, 1]) {
    per.push([b, inv, 0]);
    if (b % 3 === 0) per.push([b, inv, 1]); else if (b % 3 === 1) per.push([b, inv, 2]);
  }
  const n = L * per.length, R: FlowRows = { n, N: L, t: new Int32Array(n), b: new Uint16Array(n), inv: new Uint8Array(n), brd: new Uint8Array(n),
    bv: new Float64Array(n), sv: new Float64Array(n), bl: new Float64Array(n), sl: new Float64Array(n), bf: new Float64Array(n), sf: new Float64Array(n),
    brokers, has: new Uint8Array(L).fill(1) };
  const close: Num[] = [], volume: Num[] = [], dates: string[] = [];
  let k = 0;
  for (let t = 0; t < L; t++) {
    const price = 1000 + 50 * Math.sin(t / 3);
    close.push(price); volume.push(1e6 + 1e5 * ((t * 7) % 11));
    dates.push(new Date(Date.UTC(2000, 0, 3) + t * 864e5).toISOString().slice(0, 10));
    for (const [b, inv, brd] of per) {
      const u = 1 + ((b * 7 + t * 13 + inv) % 11) / 10, buyer = b < PROBE_BROKERS / 2;
      const bl = buyer ? 10 * u + 5 : 5 * u, sl = buyer ? 5 * u : 10 * u + 5;
      R.t[k] = t; R.b[k] = b; R.inv[k] = inv; R.brd[k] = brd;
      R.bl[k] = bl; R.sl[k] = sl; R.bv[k] = bl * 100 * price * (1 + 0.01 * ((b + t) % 5)); R.sv[k] = sl * 100 * price * (1 + 0.01 * ((b + 2 * t) % 5));
      R.bf[k] = 3 + ((b + t) % 7); R.sf[k] = 2 + ((b + 3 * t) % 5);
      k++;
    }
  }
  const classification = Object.fromEntries(brokers.map((c, b) => [c, b % 4 === 0 ? 'Institutional-heavy' : b % 4 === 1 ? 'Retail-heavy' : 'Mixed']));
  return { rows: R, dates, close, volume, insider: [], classification };
}

/* ---- EXEC-PRICE-DISTORTION D-5 (user 2026-11-24): what a corporate action does to the rows a flow value reads -------
   The registry generator's basis probe (scripts/build-screener-registry.mjs basisReads) asks of every flow output which
   of the inputs an action or a price break distorts it reads: compared from a middle candle t0 on, an output reads the
   broker lots when the lots of the candles up to t0 multiplied by a factor change it (the lots before an action not
   restated to the new share count; bv, sv and the transaction counts unchanged), the close when the closes up to t0
   multiplied by a factor change it, the volume likewise (a price history not adjusted before an action, or a wrong
   bar). The context is probeContext with a third of the brokers (code index divisible by 3) turned from buyer to seller
   and back from t0 on (buy and sell lots, values and transaction counts swapped), so a net, a count of net buyers or a
   streak crosses zero across t0 and a sign-only output can show the change too. Copies, never the context given. */
const copyContext = (c: FlowContext): FlowContext => ({ ...c, rows: { ...c.rows, bv: Float64Array.from(c.rows.bv), sv: Float64Array.from(c.rows.sv),
  bl: Float64Array.from(c.rows.bl), sl: Float64Array.from(c.rows.sl), bf: Float64Array.from(c.rows.bf), sf: Float64Array.from(c.rows.sf) }, close: [...c.close], volume: [...c.volume] });
/** probeContext's rows with the brokers of code index divisible by 3 on the other side from candle t0 on. */
export function turnedContext(c: FlowContext, t0: number): FlowContext {
  const x = copyContext(c), R = x.rows;
  for (let k = 0; k < R.n; k++) if (R.t[k] >= t0 && R.b[k] % 3 === 0) {
    [R.bl[k], R.sl[k]] = [R.sl[k], R.bl[k]]; [R.bv[k], R.sv[k]] = [R.sv[k], R.bv[k]]; [R.bf[k], R.sf[k]] = [R.sf[k], R.bf[k]];
  }
  return x;
}
/** The context with the buy and sell lots of every candle up to and including t0 multiplied by `factor` (values and
    transaction counts unchanged). The candle t0 itself is included, so an output that reads the lots of its own candle
    only (lots per transaction) shows the change too: a window test over its values mixes the two sides of an action. */
export function scaledLots(c: FlowContext, t0: number, factor: number): FlowContext {
  const x = copyContext(c), R = x.rows;
  for (let k = 0; k < R.n; k++) if (R.t[k] <= t0) { R.bl[k] *= factor; R.sl[k] *= factor }
  return x;
}
/** The context with the closes (`field` close) or the volumes (`field` volume) of the candles up to and including t0
    multiplied by `factor`. */
export function scaledBars(c: FlowContext, t0: number, field: 'close' | 'volume', factor: number): FlowContext {
  const x = copyContext(c), s = x[field];
  for (let t = 0; t <= t0 && t < s.length; t++) { const v = s[t]; if (typeof v === 'number') s[t] = v * factor }
  return x;
}

/** A registry parameter as the probes read it: its key, kind and value. */
export interface ProbeParam { key: string; kind: string }
/** The probe's length for an indicator at these parameter values: as long as any sum of its session parameters can
    reach (2 plus twice every whole-number parameter and every numeric select option, e.g. a lag of "20"), so every
    output has a value as soon as its windows fit. */
export function probeLength(params: readonly ProbeParam[], values: Readonly<Record<string, unknown>>): number {
  let L = 2;
  for (const q of params) {
    const v = values[q.key];
    if (q.kind === 'int' && typeof v === 'number') L += 2 * v;
    else if (q.kind === 'select' && typeof v === 'string' && /^\d+$/.test(v)) L += 2 * Number(v);
  }
  return L;
}
