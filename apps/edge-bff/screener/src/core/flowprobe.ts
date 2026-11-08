/* The synthetic broker context the flow probes run on (EXEC-SCREENER-FLOW-CANDLES P5a; verification/screener/P5_FLOW.md
   sections 1 and 2): flowmetrics.ts indicatorDepth (K1: the sessions an indicator reads back) and the registry
   generator's display-only probe (scripts/build-screener-registry.mjs flowEntries: a parameter whose every option gives
   the same values is not a condition parameter, QA unit B, QA5). One module for both, so the two probes read the same
   rows; it imports only the Terminal's flow types (no generated file), so the generator can load it.
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
