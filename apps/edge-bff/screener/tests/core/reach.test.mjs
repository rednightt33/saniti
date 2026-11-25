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
