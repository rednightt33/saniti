// EXEC-IND-CARDS IC3: extra checks of the Flow explainers FL20-FL39 (src/calc/explainFlowB.ts) on the paths the shared
// test (explain.test.ts) cannot reach with its 60 candles and defaults: percentiles with a short baseline, the broker
// classification, insider rows, a changing volume, rows without transaction counts, every broker scope and rank, an
// anchor date, Broker Inventory in rupiah, per candle and with its total (and the chart's slots b1..b5).
import { describe, expect, it } from 'vitest';
import { computeFlow, flowDefaults, flowRows, type FlowContext } from '../../src/calc/flow';
import type { Explanation } from '../../src/calc/explain';
import { FLOW_EXPLAIN_B } from '../../src/calc/explainFlowB';

function rng(seed: number) { return () => (seed = (seed * 1664525 + 1013904223) >>> 0) / 2 ** 32 }
/* like explain.test.ts syntheticFlow, longer, with a moving volume, rows without counts, insider rows, a classification */
function context(seed = 11, N = 120, gaps = true): FlowContext {
  const r = rng(seed), dates = Array.from({ length:N }, (_, k) => new Date(Date.UTC(2026, 0, 5 + k)).toISOString().slice(0, 10));
  const rows: any[] = [], brokers = ['AK', 'BK', 'CC', 'DX', 'KZ', 'SQ', 'XL', 'YU', 'ZP'];
  dates.forEach((d, k) => {
    if (k < 4 || k === 30 || k === 31 || k === 77) return;
    for (const b of brokers) for (const i of ['Foreign', 'Domestic']) for (const m of ['Regular', 'Nego', 'Tunai']) {
      if (r() < (m === 'Regular' ? 0.2 : 0.85)) continue;
      const bl = Math.round(r() * 5000) + (r() < 0.1 ? 0.37 : 0), sl = Math.round(r() * 5000), px = 8000 + 400 * r();
      const noCount = gaps && k >= 50 && k <= 52 && r() < 0.3;
      rows.push({ d, b, i, m, bv:bl * 100 * px, sv:sl * 100 * px, bl, sl, bf:noCount ? null : Math.max(1, Math.round(bl / 40)), sf:noCount ? null : Math.max(1, Math.round(sl / 40)) });
    }
  });
  const at = new Map(dates.map((d, k) => [d, k]));
  const close = dates.map((_, k) => 8000 + 40 * Math.sin(k / 3) + (k % 7 === 0 ? 30 : 0)), volume = dates.map((_, k) => 1e6 * (1 + (k % 11 < 4 ? 1.2 : 0)));
  const insider = [{ t:10, value:5e9 }, { t:12, value:-2e9 }, { t:12, value:7e8 }, { t:40, value:-3e9 }, { t:95, value:1e9 }];
  return { rows:flowRows(rows, N, d => at.get(d) ?? -1), dates, close, volume, insider,
    classification:{ AK:'Institutional-heavy', CC:'Institutional-heavy', XL:'Institutional-heavy', YU:'Retail-heavy', ZP:'Retail-heavy', DX:'Mixed' } };
}

function same(e: Explanation | null, chart: number | null, where: string) {
  if (chart === null || chart === undefined) { expect(e?.value ?? null, where).toBeNull(); return 0 }
  expect(e, where).not.toBeNull();
  expect(e!.value!, where).toBeCloseTo(chart, 8);
  const fromTerms = e!.combine(Object.fromEntries(e!.terms.map(x => [x.key, x.value])));
  expect(fromTerms!, `${where}: combine(terms)`).toBeCloseTo(chart, 8);
  expect(e!.steps.length, `${where}: steps`).toBeGreaterThan(0);
  const text = JSON.stringify([e!.expr, e!.terms.map(x => x.label), e!.steps]);
  expect(text, `${where}: text`).not.toMatch(/undefined|NaN|null|\[object/);
  expect(new Set(e!.terms.map(x => x.key)).size, `${where}: term keys`).toBe(e!.terms.length);
  return 1;
}
/** every output and candle of one indicator and parameter set; returns how many candles had a value */
function check(id: string, c: FlowContext, given: Record<string, any>) {
  const p = { ...flowDefaults(id), ...given }, out = computeFlow(id, c, p);
  let n = 0;
  for (const key of Object.keys(out).filter(k => !k.startsWith('_') && Array.isArray(out[k])))
    for (let t = 0; t < c.dates.length; t++) {
      const e = FLOW_EXPLAIN_B[id](c, p, t, key);
      if (e) expect(e.output).toBe(key);
      n += same(e, out[key][t] ?? null, `${id} ${JSON.stringify(given)} ${key} t=${t}`);
    }
  return n;
}

const c = context();
const COHORT = [{ scope:'all' }, { scope:'selected', brokers:['BK', 'SQ', 'ZZ'] }, { scope:'topn', top:2, rank:'gross_buy' }, { scope:'topn', rank:'net_sell' }];
const CASES: Record<string, Record<string, any>[]> = {
  FL20: [{}, { scope:'selected', brokers:['AK', 'XL'] }, { rank:'gross_buy', top:5 }, { rank:'net_sell' }, { anchor:'2026-02-20' }, { anchor:'2026-06-01' }, { boards:['Nego', 'Cash'] }, { boards:[] }],
  FL21: [{ baseline:10 }, { baseline:30, window:3 }, { baseline:20, window:5, investors:['Domestic'] }, ...COHORT.map(x => ({ baseline:15, ...x })),
    { baseline:15, measure:'gross_buy' }, { baseline:15, measure:'gross_sell', scope:'all', investors:['Foreign'] }],
  FL22: [{}, { window:5 }, { boards:['Cash'] }, { investors:['Domestic'], window:20 }, { measure:'count' }, { measure:'count', window:5 }],
  FL23: [{}, { unit:'value' }, { view:'daily' }, { unit:'value', view:'daily', total:true }, { total:true }, { brokers:['YU', 'QQ', 'AK'], total:true },
    { brokers:'class:Institutional-heavy', unit:'value', total:true }, { start:'2026-03-01', total:true }, { brokers:['AK', 'AK', 'BK'], total:true }, { boards:['Regular'], investors:['Foreign'], total:true }],
  FL25: [{}, { window:1 }, { top:1, window:30 }, { boards:['Nego'] }],
  FL26: [{}, { scope:'topn' }, { scope:'topn', window:3, top:1 }, { scope:'selected', brokers:['CC', 'KZ'] }, { window:2 }, { scope:'all', investors:['Foreign', 'Domestic'], window:4 }],
  FL27: [{}, { volx:1.2, move:5 }, { recent:3, baseline:8, volx:1, move:1 }, { n_net:1, x_net:0.5, n_gross:5, x_gross:0.8 }, { n_net:20, x_net:3 }],
  FL28: [{}, { window:1 }, { window:7 }],
  FL29: [{}, { window:5, threshold:-5 }, { top:1, threshold:2 }, { window:30, boards:['Regular'] }],
  FL30: [{}, { window:1 }, { investors:['Foreign'] }],
  FL31: [{}, { window:1 }, { window:5 }, { window:60 }],
  FL32: [{}, { baseline:3 }, { baseline:30, boards:['Regular'] }, { measure:'value', side:'both' }, { measure:'lot', side:'sell', baseline:5 }, { side:'both', investors:['Foreign'] }],
  FL33: [{}, { recent:1, baseline:4 }, { recent:10, baseline:10, investors:['Foreign'] }, { scope:'topn' }, { scope:'topn', top:1, side:'both', rank:'gross_buy' },
    { scope:'selected', brokers:['AK', 'ZP'], side:'sell' }, { scope:'topn', side:'sell', recent:2, baseline:6 }],
  FL34: [{}, { window:3 }, { inst:['AK', 'BK'], retail:['ZP'] }, { inst:['AK'], retail:[] }, { inst:['AK', 'YU'] }, { retail:'class:Mixed' }, { boards:['Nego', 'Cash'] }],
  FL35: [{}, { window:3 }, { window:1, investors:['Domestic'] }],
  FL36: [{}, ...COHORT, { window:1, investors:['Foreign', 'Domestic'] }],
  FL37: [{ baseline:10 }, { baseline:25, window:5 }, ...COHORT.map(x => ({ baseline:12, window:3, ...x })), { baseline:10, stat:'z' }, { baseline:25, window:5, stat:'z', scope:'all', investors:['Foreign'] }],
  FL38: [{}, { window:1 }, { window:40 }, { unit:'lot' }, { unit:'lot', window:5 },
    // to-do 5: a cohort's part of the net buyers' HHI (Top-N, selected brokers with a seller among them)
    { scope:'topn', top:3 }, { scope:'topn', top:1, rank:'gross_buy', window:5 }, { scope:'topn', top:20, unit:'lot' },
    { scope:'selected', brokers:['AK', 'ZP', 'QQ'] }, { scope:'selected', brokers:[] }],
  FL39: [{}, ...COHORT.filter(x => x.scope !== 'all'), { window:1, boards:['Regular', 'Nego', 'Cash'] }],
};

describe('Flow explainers FL20-FL39 on the other paths', () => {
  for (const [id, cases] of Object.entries(CASES)) it(id, () => {
    let shown = 0;
    for (const v of cases) shown += check(id, c, v);
    expect(shown, `${id}: candles with a value`).toBeGreaterThan(0);
  }, 60_000);     // thousands of explanations, each formatting its numbers (explain.ts fmt)
  it('FL27 marks some candles and not others', () => {
    const out = computeFlow('FL27', c, { ...flowDefaults('FL27'), volx:1.2, move:5 }).value;
    expect(out.some(v => v === 1) && out.some(v => v === 0)).toBe(true);
  });
  it('FL32 and FL33 are null where a row lacks the counts', () => {
    const t = 51, e = FLOW_EXPLAIN_B.FL32(c, flowDefaults('FL32'), t);
    expect(computeFlow('FL32', c, flowDefaults('FL32')).buy[t]).toBeNull();      // Activity Spike draws buy/sell (to-do 2)
    expect(e).toBeNull();
  });
  it('FL23 answers the chart slots b1..b5 and total', () => {
    const p = { ...flowDefaults('FL23'), total:true }, out = computeFlow('FL23', c, p), codes = Object.keys(out).filter(k => k !== 'total');
    expect(codes.length).toBe(3);
    for (let t = 0; t < c.dates.length; t++) codes.forEach((code, j) => {
      const e = FLOW_EXPLAIN_B.FL23(c, p, t, `b${j + 1}`);
      if (out[code][t] === null) expect(e).toBeNull(); else { expect(e!.output).toBe(`b${j + 1}`); expect(e!.value).toBeCloseTo(out[code][t]!, 8) }
    });
    expect(FLOW_EXPLAIN_B.FL23(c, p, 60, 'b4')).toBeNull();
    expect(FLOW_EXPLAIN_B.FL23(c, { ...p, total:false }, 60, 'total')).toBeNull();
    expect(FLOW_EXPLAIN_B.FL23(c, p, 60)!.output).toBe(codes[0]);
  });
  it('an output the indicator does not draw has no explanation', () => {
    expect(FLOW_EXPLAIN_B.FL25(c, flowDefaults('FL25'), 60, 'buy')).toBeNull();
    expect(FLOW_EXPLAIN_B.FL25(c, flowDefaults('FL25'), 60)!.output).toBe('value');
  });
  it('a parameter given as undefined takes its default, as computeFlow', () => {
    const p = { ...flowDefaults('FL26'), scope:undefined }, out = computeFlow('FL26', c, p).value;
    for (let t = 0; t < c.dates.length; t++) expect(FLOW_EXPLAIN_B.FL26(c, p, t)?.value ?? null).toEqual(out[t]);
  });
  it('every indicator FL20-FL39 except FL24 has an explainer here', () => {
    const ids = Array.from({ length:20 }, (_, k) => `FL${20 + k}`).filter(id => id !== 'FL24');
    expect(ids.filter(id => !FLOW_EXPLAIN_B[id])).toEqual([]);
    expect(FLOW_EXPLAIN_B.FL24).toBeUndefined();
  });
});
