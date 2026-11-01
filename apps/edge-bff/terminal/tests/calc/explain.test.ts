// EXEC-IND-CARDS (user go 2026-11-01): the card's number is the chart's number. Every explainer is compared, at every
// candle, with the calculation the chart draws (calc/flow.ts computeFlow, calc/indicators.ts F) on the same data, with
// the Terminal defaults and with other parameters; its last step (combine) must give the same value from its terms.
import { describe, expect, it } from 'vitest';
import { computeFlow, flowDefaults, flowRows, type FlowContext } from '../../src/calc/flow';
import { F, DEFAULTS } from '../../src/calc/indicators';
import type { Explanation } from '../../src/calc/explain';
import { FLOW_EXPLAIN, TECH_EXPLAIN } from '../../src/calc/explainIndex';
import { loadFixtures } from './fixtures.mjs';
import REG from '../../src/data/flowRegistry.json';
import IND from '../../src/data/indRegistry.json';

/* seeded broker rows: 60 candles, 9 brokers, both investor types, three boards, some candles without data */
function rng(seed: number) { return () => (seed = (seed * 1664525 + 1013904223) >>> 0) / 2 ** 32 }
export function syntheticFlow(seed = 7, N = 60): FlowContext {
  const r = rng(seed), dates = Array.from({ length:N }, (_, k) => new Date(Date.UTC(2026, 0, 5 + k)).toISOString().slice(0, 10));
  const rows: any[] = [], brokers = ['AK', 'BK', 'CC', 'DX', 'KZ', 'SQ', 'XL', 'YU', 'ZP'];
  dates.forEach((d, k) => {
    if (k < 3 || k === 20 || k === 41) return;                          // no broker data on these candles
    for (const b of brokers) for (const i of ['Foreign', 'Domestic']) for (const m of ['Regular', 'Nego', 'Tunai']) {
      if (r() < (m === 'Regular' ? 0.25 : 0.85)) continue;
      const bl = Math.round(r() * 5000), sl = Math.round(r() * 5000), px = 8000 + 400 * r();
      rows.push({ d, b, i, m, bv:bl * 100 * px, sv:sl * 100 * px, bl, sl, bf:Math.max(1, Math.round(bl / 40)), sf:Math.max(1, Math.round(sl / 40)) });
    }
  });
  const at = new Map(dates.map((d, k) => [d, k]));
  const close = dates.map((_, k) => 8000 + 10 * k), volume = dates.map(() => 1e6);
  return { rows:flowRows(rows, N, d => at.get(d) ?? -1), dates, close, volume, insider:[], classification:{} };
}

function sameAsChart(e: Explanation | null, chart: number | null, where: string) {
  if (chart === null || chart === undefined) { expect(e?.value ?? null, where).toBeNull(); return }
  expect(e, where).not.toBeNull();
  expect(e!.value, where).not.toBeNull();
  expect(e!.value!, where).toBeCloseTo(chart, 8);
  const fromTerms = e!.combine(Object.fromEntries(e!.terms.map(x => [x.key, x.value])));
  expect(fromTerms, `${where}: combine(terms)`).not.toBeNull();
  expect(fromTerms!, `${where}: combine(terms)`).toBeCloseTo(chart, 8);
  expect(e!.steps.length, `${where}: steps`).toBeGreaterThan(0);
}

/* parameter sets besides the defaults: every explainer is tried with them where the indicator has the parameter */
/* an empty board list means no row (calc/flow.ts grid), never all; a baseline of 20 lets a percentile have values on the 60
   synthetic candles (the default 250 is longer) */
const FLOW_VARIANTS: Record<string, any>[] = [{}, { window:3 }, { top:1 }, { investors:['Foreign'] }, { boards:['Regular'] }, { window:20, top:5 },
  { boards:[] }, { baseline:20 }];

describe('Flow explainers equal calc/flow.ts', () => {
  const c = syntheticFlow();
  for (const [id, explain] of Object.entries(FLOW_EXPLAIN)) it(id, () => {
    const def = flowDefaults(id);
    for (const v of FLOW_VARIANTS) {
      if (Object.keys(v).some(k => !(k in def))) continue;
      const p = { ...def, ...v }, out = computeFlow(id, c, p);
      for (const key of Object.keys(out).filter(k => !k.startsWith('_') && Array.isArray(out[k])))   // every output
        for (let t = 0; t < c.dates.length; t++) {
          const e = explain(c, p, t, key);
          if (e) expect(e.output, `${id} asked ${key}`).toBe(key);
          sameAsChart(e, out[key][t] ?? null, `${id} ${JSON.stringify(v)} ${key} t=${t}`);
        }
    }
  });
});

describe('technical explainers equal calc/indicators.ts', () => {
  const d = loadFixtures().find((x: any) => x.ticker === 'BBCA');
  const B = { T:d.T, O:d.O, H:d.H, L:d.L, C:d.C, V:d.V };
  for (const [key, explain] of Object.entries(TECH_EXPLAIN)) it(key, () => {
    const def = DEFAULTS[key] || {};
    const variants = [{}, ...('length' in def ? [{ length:5 }, { length:50 }] : []), ...('source' in def ? [{ source:'hlc3' }] : [])];
    for (const v of variants) {
      const p = { ...def, ...v }, out = F[key](B, p);
      for (const k of Object.keys(out).filter(x => !x.startsWith('_') && Array.isArray((out as any)[x])))   // every output
        for (let t = 0; t < B.C.length; t += t < 80 ? 1 : 37) {
          const e = explain(B, p, t, k);
          if (e) expect(e.output, `${key} asked ${k}`).toBe(k);
          sameAsChart(e, (out as any)[k][t] ?? null, `${key} ${JSON.stringify(v)} ${k} t=${t}`);
        }
    }
  });
});

/* each part of the explainers covers its indicators (IC3: FL01-FL39, IC4: I01-I53; ids from the registries) */
const flowIds = (REG as any).indicators.map((r: any) => r.id as string);
const techKeys = (IND as any[]).map(r => [r.id as string, r.key as string]);
const num = (id: string) => +id.replace(/\D/g, '');
describe('every indicator has an explainer', () => {
  it('Flow FL01-FL19 (explainFlowA.ts)', () => expect(flowIds.filter((i: string) => num(i) <= 19 && !FLOW_EXPLAIN[i])).toEqual([]));
  it('Flow FL20-FL39 (explainFlowB.ts)', () => expect(flowIds.filter((i: string) => num(i) >= 20 && !FLOW_EXPLAIN[i])).toEqual([]));
  it('technical I01-I26 (explainTechA.ts)', () => expect(techKeys.filter(([i, k]) => num(i) <= 26 && !TECH_EXPLAIN[k]).map(([i]) => i)).toEqual([]));
  it('technical I27-I53 (explainTechB.ts)', () => expect(techKeys.filter(([i, k]) => num(i) >= 27 && !TECH_EXPLAIN[k]).map(([i]) => i)).toEqual([]));
});
