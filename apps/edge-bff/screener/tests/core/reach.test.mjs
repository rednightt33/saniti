/* UD36 (ERRORS M558 SC-3; EXEC-PRICE-DISTORTION step F2b, the user's go 2026-11-24): the registry's history classes
   against real prices. An output classed window promises that its value at bar t reads only the bars t - firstValid .. t
   (evaluate.ts lookbackStart), and the cell remark PRICE_BREAK_IN_LOOKBACK ("Distorted") is set from that promise: an
   output that reads further back loses the remark whenever its window has passed the price break but the value has not.
   The generator measures the class on synthetic series (the cut probe, then the reach probe on four price shapes); this
   test cuts the Terminal's real-price parity fixtures (apps/edge-bff/terminal/tests/calc/fixtures: BBCA, CLAY, DEWI,
   GOTO, IHSG, ISEA, KOCI, UNVR, daily bars from 2018 or their listing to 2026-10-23, the same files the Backtest
   worker's tests read) at every 37th
   bar, as the evidence of 2026-11-24 did on BBCA and BBRI, and fails when an output classed window differs from the
   full history at a bar whose window the cut holds. It reads the registry file itself: an import passes the public
   build's release filter (vite.config.ts), which leaves the lab indicators out. Plain JavaScript (node:fs), as
   registry-check.test.mjs. */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import * as G from '../../scripts/build-screener-registry.mjs';      // registers the lab formulas by path (3f TR-2)
import { DEFAULTS, F } from '../../../terminal/src/calc/indicators.ts';
import { loadFixtures } from '../../../terminal/tests/calc/fixtures.mjs';
import { movingBars } from '../../src/core/effective.ts';
import { historyOf, inputsOf } from '../../src/core/registry.ts';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REGISTRY = JSON.parse(fs.readFileSync(path.join(HERE, '../../src/core/screener-registry.json'), 'utf8'));
const STOCKS = loadFixtures().map(f => ({ ticker: f.ticker, bars: { T: f.T, O: f.O, H: f.H, L: f.L, C: f.C, V: f.V } }));
const CUT_FROM = 30, CUT_EVERY = 37, MARGIN = 300;
const slice = (B, a) => ({ O: B.O.slice(a), H: B.H.slice(a), L: B.L.slice(a), C: B.C.slice(a), V: B.V.slice(a), T: B.T.slice(a) });

/** For each of `outputs` of the indicator at its start configuration, the longest reach beyond its window on the real
    prices (G.reachBeyond, the generator's own measure), with the stock and the cut that gave it. */
function realReach(ind, outputs) {
  const params = { ...DEFAULTS[ind.key], ...ind.start_params }, worst = Object.fromEntries(outputs.map(o => [o, { beyond: 0 }]));
  for (const { ticker, bars } of STOCKS) {
    const full = F[ind.key](bars, params);
    for (let cut = CUT_FROM; cut < bars.C.length - MARGIN; cut += CUT_EVERY) {
      const part = F[ind.key](slice(bars, cut), params);
      for (const o of outputs) {
        const beyond = G.reachBeyond(full[o], part[o], cut);
        if (beyond > worst[o].beyond) worst[o] = { beyond, ticker, cut };
      }
    }
  }
  return worst;
}
const stageOf = id => JSON.parse(fs.readFileSync(path.join(HERE, '../../../catalog/releases.json'), 'utf8')).items.find(x => x.kind === 'indicator' && x.id === id)?.stage ?? 'lab';

describe('history class on real prices (UD36)', () => {
  it('reads the fixtures: eight stocks of 548 to 2,125 daily bars, each cut several times', () => {
    expect(STOCKS.length).toBeGreaterThanOrEqual(8);
    for (const s of STOCKS) expect(s.bars.C.length).toBeGreaterThan(MARGIN + CUT_FROM + 4 * CUT_EVERY);
  });

  it('every output the registry classes window reads no bar before its window, on every stock and cut', () => {
    const problems = [];
    let checked = 0;
    for (const ind of REGISTRY.indicators) {
      const outs = ind.outputs.filter(o => o.history_class === 'window').map(o => o.key);
      if (!outs.length) continue;
      checked += outs.length;
      for (const [o, w] of Object.entries(realReach(ind, outs))) if (w.beyond > 0)
        problems.push(`${ind.id}.${o} (${ind.name}, ${stageOf(ind.id)}) is classed window, but on ${w.ticker} cut at bar ${w.cut} its value still differs ${w.beyond} bar(s) before its window: the generator's reach probe (PROBE.reach.shapes in scripts/build-screener-registry.mjs) misses this; add a price shape that holds its mechanism and run npm run registry`);
    }
    expect(checked).toBeGreaterThanOrEqual(40);              // 46 window outputs on 2026-11-24: the check reads the registry
    expect(problems).toEqual([]);
  }, 300_000);

  /* The check's power (as the look-ahead gate's self-test catches a centred average): every output the reach probe moved
     out of window (the cut probe alone finds it window, the registry does not), read as window, fails on these prices,
     the 16 lab outputs of 2026-11-24 among them (Alpha Volatile's flags, Inside Bar's inside and break up, Alpha KAMA's
     ENTER SHORT, Alpha Extract's at or above 0, Alpha Divergence's divergences, BUY A and swing levels). REACH_ONLY names
     an output the shapes catch and these stocks do not, with the reason; none today. */
  const REACH_ONLY = {};
  it('catches every output the reach probe moved out of window, read as window', () => {
    const B = G.fixture(), cut = slice(B, G.PROBE.cut_at), moved = [];
    for (const ind of REGISTRY.indicators) {
      const run = b => F[ind.key](b, { ...DEFAULTS[ind.key], ...ind.start_params }), full = run(B), part = run(cut);
      const hasAnchor = ind.params.some(p => p.key === 'anchor');
      const outs = ind.outputs.filter(o => o.history_class !== 'window' && G.historyClass(full[o.key], part[o.key], G.PROBE.cut_at, hasAnchor) === 'window').map(o => o.key);
      if (!outs.length) continue;
      for (const [o, w] of Object.entries(realReach(ind, outs))) moved.push({ out: `${ind.id}.${o}`, beyond: w.beyond });
    }
    expect(moved.length).toBeGreaterThanOrEqual(16);
    const missed = moved.filter(m => m.beyond === 0 && !(m.out in REACH_ONLY)).map(m => m.out);
    expect(missed, 'the reach probe moved these out of window, but no real-price fixture shows it: name them in REACH_ONLY with the shape that does').toEqual([]);
    for (const out of ['I55.ib', 'I58.short', 'I60.buy_a', 'I60.swing_low']) expect(moved.map(m => m.out)).toContain(out);
  }, 300_000);

  it('measures the window exactly: one bar short is caught, residue under the tolerance is not, a state left out is', () => {
    // a value of two bars (x[t] and x[t-1]) that has a value on bar 0 promises a window of one bar: one bar short (the
    // Inside Bar's inside flag, bar 0 is 0); the same with no value on bar 0 promises two bars: kept
    const x = Array.from({ length: 60 }, (_, i) => Math.sin(i) * 10 + 100);
    const two = (s, first) => s.map((v, i) => i === 0 ? first(v) : v + s[i - 1]);
    expect(G.reachBeyond(two(x, v => v), two(x.slice(20), v => v), 20)).toBe(1);
    expect(G.reachBeyond(two(x, () => null), two(x.slice(20), () => null), 20)).toBe(0);
    // running-sum residue far under the tolerance (MFI on CLAY: 7.9e-8 against -2.3e-8 on a scale of 100) is equal
    const flat = x.map(v => v / 2), noisy = flat.map((v, i) => i % 7 ? v : v + 1e-7);
    expect(G.reachBeyond(flat, noisy.slice(20), 20)).toBe(0);
    // the last swing: a level held from bar 5, which a history cut at bar 20 has not seen until a new one at bar 50
    const held = x.map((_, i) => i < 5 ? null : i < 50 ? 120 : 130), cutHeld = x.slice(20).map((_, i) => i + 20 < 50 ? null : 130);
    expect(G.reachBeyond(held, cutHeld, 20)).toBe(50 - 20 - 5);
  });

  it('the reach probe on the synthetic shapes: SMA, Donchian and Price Action keep their window; the last swing low does not', () => {
    const at = (key, outs) => G.reachProbe(b => F[key](b, DEFAULTS[key]), outs);
    expect(at('sma', ['sma']).sma.beyond).toBe(0);
    expect(at('donchian', ['upper', 'lower']).upper.beyond).toBe(0);
    expect(Object.values(at('price_action_buy', ['level_1', 'level_a', 'level_b', 'break_a'])).map(r => r.beyond)).toEqual([0, 0, 0, 0]);
    const swing = at('alpha_divergence', ['swing_low']).swing_low;
    expect(swing.beyond).toBeGreaterThan(0);
    expect(G.PROBE.reach.shapes.map(s => s.name)).toContain(swing.shape);
    expect(G.reachClass('window', swing.beyond)).toBe('recursive');
    expect([G.reachClass('window', 0), G.reachClass('recursive', 0), G.reachClass('cumulative', 3)]).toEqual(['window', 'recursive', 'cumulative']);
  }, 120_000);
});

/* UD55 and UD52 (EXEC-PRICE-DISTORTION; the user 2026-11-25, "3. Ok boleh": "an effective window per output ... 0.1 % of
   its size", "one class per output and setting"): the generator measures each recursive output's effective window on
   synthetic shapes at a tolerance a hundred times tighter than the user's (build-screener-registry.mjs effectiveProbe)
   and how it grows with the whole-number parameters (effectiveScaling); registry.ts historyOf reads the window of a
   setting. Here the same cut is made on the real-price fixtures at the user's tolerance, 0.1 % of the output's
   magnitude (scaleOf), the window counted in moving bars on the output's inputs (effective.ts): beyond its window the
   value from a cut start must equal the full history's within the tolerance, at the start configuration, with every
   whole-number parameter raised x1.5, x2 and x3 where the rule covers it, and at every option with a window of its
   own. */
const TOL = G.PROBE.effective.tolerance;
const startOf = ind => ({ ...DEFAULTS[ind.key], ...ind.start_params });
/** The most moving bars any cut of the fixtures still differs on, at the user's tolerance, per output of `outs` at the
    start configuration with `over` applied (G.effectiveCut, the generator's own measure), with the stock and the cut. */
function realMoving(ind, outs, over) {
  const params = { ...startOf(ind), ...over }, worst = Object.fromEntries(outs.map(o => [o, { moving: 0 }]));
  for (const { ticker, bars } of STOCKS) {
    const full = F[ind.key](bars, params);
    const mv = Object.fromEntries(outs.map(o => [o, movingBars(bars, inputsOf(ind.outputs.find(x => x.key === o), params))]));
    const tol = Object.fromEntries(outs.map(o => [o, TOL * G.scaleOf(full[o])]));
    for (let cut = CUT_FROM; cut < bars.C.length - MARGIN; cut += CUT_EVERY) {
      const part = F[ind.key](slice(bars, cut), params);
      for (const o of outs) { const x = G.effectiveCut(full[o], part[o], cut, mv[o], tol[o]); if (x.moving > worst[o].moving) worst[o] = { moving: x.moving, ticker, cut } }
    }
    // and a break of every size the generator plants (PROBE.effective.break_factors, re-check round 2 H2-1), at its
    // real-fixture stride: the broken history against the bars from the break on
    const E = G.PROBE.effective;
    for (const k of E.break_factors) for (let d = E.real_from; d < bars.C.length - E.real_margin; d += E.real_every) {
      const broken = G.breakBars(bars, d, k), bf = F[ind.key](broken, params), bp = F[ind.key](slice(broken, d), params);
      for (const o of outs) {
        const x = G.effectiveCut(bf[o], bp[o], d, movingBars(broken, inputsOf(ind.outputs.find(y => y.key === o), params)), TOL * G.scaleOf(bf[o]));
        if (x.moving > worst[o].moving) worst[o] = { moving: x.moving, ticker, cut: `${d} x${k}` };
      }
    }
  }
  return worst;
}
/** The settings each indicator's effective windows are checked at: the start configuration, every whole-number
    parameter raised by 1.5, 2 and 3, and each option with a window of its own (history_by_option). */
function settings(ind) {
  const base = startOf(ind), out = [['start', {}]];
  for (const f of [1.5, 2, 3]) out.push([`x${f}`, Object.fromEntries(ind.params.filter(p => p.integer && base[p.key] > 0).map(p => [p.key, Math.min(p.max ?? Infinity, Math.round(base[p.key] * f))]))]);
  const opts = new Set();
  for (const o of ind.outputs) for (const [k, byOpt] of Object.entries(o.history_by_option ?? {})) for (const [v, h] of Object.entries(byOpt)) if (h.effective_window?.bars) opts.add(JSON.stringify([k, v]));
  for (const kv of opts) { const [k, v] = JSON.parse(kv), p = ind.params.find(q => q.key === k); out.push([`${k}=${v}`, { [k]: p.type === 'boolean' ? v === 'true' : v }]) }
  return out;
}
/** Every (indicator, setting, output) with a window there (historyOf), with the most moving bars the fixtures still
    differ on at the user's tolerance (realMoving). Measured once for both tests below; it yields to the event loop
    after each setting, so a slow machine still answers the test runner while it measures. */
async function measureWindows() {
  const rows = [];
  for (const ind of REGISTRY.indicators) for (const [name, over] of settings(ind)) {
    const params = { ...startOf(ind), ...over };
    const W = Object.fromEntries(ind.outputs.map(o => [o.key, historyOf(ind, o, params).effectiveWindow]).filter(([, w]) => w !== null));
    if (!Object.keys(W).length) continue;
    for (const [o, real] of Object.entries(realMoving(ind, Object.keys(W), over))) rows.push({ ind, name, output: o, window: W[o], real });
    await new Promise(resolve => setImmediate(resolve));
  }
  return rows;
}
let measured = null;
const windowRows = () => measured ??= measureWindows();
/** The rows whose real difference reaches `scale` x their window, as problems. */
const windowProblems = (rows, scale = 1) => rows.filter(r => r.real.moving >= Math.max(1, Math.floor(r.window * scale))).map(r =>
  `${r.ind.id}.${r.output} (${r.ind.name}, ${stageOf(r.ind.id)}) at ${r.name}: an effective window of ${Math.max(1, Math.floor(r.window * scale))} moving bars, but on ${r.real.ticker} cut at bar ${r.real.cut} the value still differs by more than 0.1 % of its magnitude ${r.real.moving} moving bars after the cut`);

describe('effective windows on real prices (UD55)', () => {
  it('beyond its window every output reads the full history\'s value within 0.1 % of its magnitude, on every stock and cut, at every measured setting', async () => {
    const rows = await windowRows();
    expect(rows.length).toBeGreaterThanOrEqual(150);        // 2026-11-25: 208, 33 outputs at the start, their raised settings and the options
    expect(windowProblems(rows), 'the generator\'s effective probe (PROBE.effective.shapes in scripts/build-screener-registry.mjs) misses a mechanism of these prices: add a shape that holds it and run npm run registry').toEqual([]);
  }, 600_000);

  /* The check's power (as the look-ahead gate's self-test catches a centred average): every window cut to a third is
     caught on these prices, so a probe that measured too short a window would fail above. */
  // a quarter since re-check round 2 (H2-1): the windows are sized by the largest break the generator plants (a 1:100
  // split), which its synthetic shapes hold longer than these eight stocks do (Chaikin Oscillator at x1.5: 165 moving
  // bars, 54 on BBCA), so a third of a window is no longer always reached here; a probe four times too short still is
  it('catches a window that is too short: every window at a quarter of its length fails on these prices', async () => {
    const rows = await windowRows(), problems = windowProblems(rows, 1 / 4);
    expect(problems.length).toBe(rows.length);
    expect(problems.some(p => p.startsWith('I13.rsi ') && p.includes(' at start:'))).toBe(true);
  }, 600_000);

  /* What the window is for: a price break the data did not adjust. Planted on the fixtures (every price before bar d
     times k, the volume divided by it: a split of 1:5 or of any size the generator plants, 1:100 to a 100000:1 reverse
     split, left in the history, every 97th bar), the value on
     the broken history differs from the one on the bars from d on, which never saw the break, for fewer moving bars
     than the window: a cell past it is unmarked rightly. */
  it('a planted unadjusted split moves every output by more than 0.1 % of its magnitude only inside its window', async () => {
    const problems = [];
    let checked = 0;
    for (const ind of REGISTRY.indicators) {
      const outs = ind.outputs.filter(o => o.effective_window?.bars), params = startOf(ind);
      if (!outs.length) continue;
      checked += outs.length;
      // the sizes the generator plants (PROBE.effective.break_factors: every size the data holds, 1:100 splits to 100000:1
      // reverse splits; re-check round 2, H2-1) and 1:5, at its real-fixture stride
      const E = G.PROBE.effective;
      for (const { ticker, bars } of STOCKS) for (const k of [5, ...E.break_factors]) for (let d = E.real_from; d < bars.C.length - E.real_margin; d += E.real_every) {
        const at = (x, i) => i < d && x !== null && x !== undefined ? x * k : x;
        const broken = { ...bars, O: bars.O.map(at), H: bars.H.map(at), L: bars.L.map(at), C: bars.C.map(at), V: bars.V.map((x, i) => i < d && x !== null && x !== undefined ? x / k : x) };
        const full = F[ind.key](broken, params), part = F[ind.key](slice(broken, d), params);
        for (const o of outs) {
          const x = G.effectiveCut(full[o.key], part[o.key], d, movingBars(broken, inputsOf(o, params)), TOL * G.scaleOf(full[o.key]));
          if (x.moving >= o.effective_window.bars) problems.push(`${ind.id}.${o.key}: a split x${k} on ${ticker} at bar ${d} still moves it ${x.moving} moving bars later, past its window of ${o.effective_window.bars}`);
        }
      }
      await new Promise(resolve => setImmediate(resolve));
    }
    expect(checked).toBeGreaterThanOrEqual(30);
    expect(problems).toEqual([]);
  }, 600_000);

  it('the rule: RSI 14 reads a bounded window, RSI 28 twice it, RSI 100 (past max_ratio) and the outputs without one the whole history', () => {
    const rsiInd = REGISTRY.indicators.find(i => i.id === 'I13'), rsi = rsiInd.outputs[0], e = rsi.effective_window;
    expect(e.bars).toBeGreaterThan(50);
    expect(e.scaling.max_ratio).toBeGreaterThanOrEqual(2);
    const at = length => historyOf(rsiInd, rsi, { ...startOf(rsiInd), length }).effectiveWindow;
    expect(at(14)).toBe(e.bars);
    expect(at(28)).toBe(Math.ceil(e.bars * 2 ** e.scaling.exponent * (1 + e.scaling.margin)));
    expect(at(7)).toBe(e.scaling.lower ? e.bars : null);
    expect(at(100)).toBe(null);
    // no window: whole numbers (Supertrend's direction), a reset (Parabolic SAR), a state the reach probe found (UD36)
    const out = (id, key) => REGISTRY.indicators.find(i => i.id === id).outputs.find(o => o.key === key);
    expect([out('I09', 'direction'), out('I12', 'sar'), out('I60', 'swing_low')].map(o => o.effective_window.reason)).toEqual(['discrete', 'reset', 'reach']);
    // cumulative outputs keep the whole history: no window is measured for them
    expect(REGISTRY.indicators.flatMap(i => i.outputs).filter(o => o.history_class === 'cumulative' && o.effective_window)).toEqual([]);
  });

  it('UD52: Bollinger Bands, %B and Band Width read a window at the SMA basis and the whole history at EMA and RMA, bounded by an effective window or not', () => {
    const B = G.fixture(), cut = slice(B, G.PROBE.cut_at);
    for (const id of ['I27', 'I28', 'I29']) {
      const ind = REGISTRY.indicators.find(i => i.id === id);
      for (const o of ind.outputs) {
        expect([id, o.key, historyOf(ind, o, startOf(ind)).historyClass]).toEqual([id, o.key, 'window']);
        for (const basis of ['EMA', 'RMA']) {
          const params = { ...startOf(ind), basis_ma_type: basis }, h = historyOf(ind, o, params);
          expect([id, o.key, basis, h.historyClass]).toEqual([id, o.key, basis, 'recursive']);
          expect(o.history_by_option.basis_ma_type[basis].history_class).toBe('recursive');
          // the cut probe itself: from a later start the value differs inside its window at this basis
          expect(G.historyClass(F[ind.key](B, params)[o.key], F[ind.key](cut, params)[o.key], G.PROBE.cut_at, false)).toBe('recursive');
        }
      }
    }
  });
});
