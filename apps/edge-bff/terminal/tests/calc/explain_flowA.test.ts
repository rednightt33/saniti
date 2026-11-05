// EXEC-IND-CARDS IC3, explainFlowA.ts (FL01-FL19): the checks of tests/calc/explain.test.ts on the parameters its
// default variants do not reach: the Sell output, every scope and ranking, the denominators, a baseline the 60
// synthetic candles can fill, anchors, FL09's switches, rows without transaction counts and fractional lots.
import { describe, expect, it } from 'vitest';
import { computeFlow, flowDefaults, flowRows, type FlowContext } from '../../src/calc/flow';
import type { Explanation } from '../../src/calc/explain';
import { FLOW_EXPLAIN_A } from '../../src/calc/explainFlowA';

function rng(seed: number) { return () => (seed = (seed * 1664525 + 1013904223) >>> 0) / 2 ** 32 }
/** like explain.test.ts syntheticFlow; `gaps`: some rows without bf/sf; `odd`: fractional lots; `big`: larger values */
function synth(seed: number, o: { gaps?: boolean; odd?: boolean; big?: boolean } = {}, N = 60): FlowContext {
  const r = rng(seed), dates = Array.from({ length:N }, (_, k) => new Date(Date.UTC(2026, 0, 5 + k)).toISOString().slice(0, 10));
  const rows: any[] = [], brokers = ['AK', 'BK', 'CC', 'DX', 'KZ', 'SQ', 'XL', 'YU', 'ZP', 'RX', 'LG'];
  dates.forEach((d, k) => {
    if (k < 3 || k === 20 || k === 41) return;
    for (const b of brokers) for (const i of ['Foreign', 'Domestic']) for (const m of ['Regular', 'Nego', 'Tunai']) {
      if (r() < (m === 'Regular' ? 0.25 : 0.85)) continue;
      const scale = o.big ? 400 : 1, frac = o.odd ? Math.round(r() * 100) / 100 : 0;
      const bl = Math.round(r() * 5000 * scale) + frac, sl = Math.round(r() * 5000 * scale) + (o.odd ? 0.37 : 0), px = 8000 + 400 * r();
      const miss = o.gaps && k > 30 && k < 36 && r() < 0.1;
      rows.push({ d, b, i, m, bv:bl * 100 * px, sv:sl * 100 * px, bl, sl,
        bf:miss ? null : Math.max(1, Math.round(bl / 40)), sf:miss ? null : Math.max(1, Math.round(sl / 40)) });
    }
  });
  const at = new Map(dates.map((d, k) => [d, k]));
  return { rows:flowRows(rows, N, d => at.get(d) ?? -1), dates, close:dates.map((_, k) => 8000 + 10 * k), volume:dates.map(() => 1e6), insider:[], classification:{} };
}

function same(e: Explanation | null, chart: number | null | undefined, where: string, key: string) {
  if (chart === null || chart === undefined) { expect(e?.value ?? null, where).toBeNull(); return 0 }
  expect(e, where).not.toBeNull();
  expect(e!.output, where).toBe(key);
  expect(e!.value!, where).toBeCloseTo(chart, 8);
  const v = e!.combine(Object.fromEntries(e!.terms.map(x => [x.key, x.value])));
  expect(v, `${where}: combine`).not.toBeNull();
  expect(v!, `${where}: combine`).toBeCloseTo(chart, 8);
  expect(e!.steps.length, where).toBeGreaterThan(0);
  for (const s of e!.steps) { expect(s.text, where).not.toMatch(/undefined|NaN/); for (const r of s.table?.rows ?? []) expect(r.join(' '), where).not.toMatch(/undefined|NaN/) }
  return 1;
}

const COHORT: Record<string, any>[] = [{}, { rank:'gross_buy' }, { rank:'net_sell' }, { scope:'selected', brokers:['BK', 'ZP', 'QQ'] }, { scope:'selected', brokers:[] },
  { scope:'all' }, { top:5, window:4 }, { top:20, rank:'gross_buy_lots' }, { boards:['Nego', 'Tunai'], investors:['Domestic'] }];
const EXTRA: Record<string, Record<string, any>[]> = {
  FL07:[{ denom:'filter' }, { denom:'filter', investors:['Foreign'] }, { investors:['Domestic'] }],
  FL08:[{ baseline:20 }, { baseline:20, side:'sell' }, { baseline:30, window:3, top:1 }, { baseline:20, scope:'selected', brokers:['AK'] }],
  FL09:[{ baseline:20 }, { baseline:20, pct_min:50, ratio_min:0.5, part_min:1, flow_min:-100 }, { baseline:20, pct_min:0, ratio_min:0.01, part_min:0, flow_min:-100, use_imb:true, imb_min:-1 },
    { baseline:20, pct_min:30, ratio_min:0.8, part_min:2, flow_min:0, use_imb:true, imb_min:0 }, { baseline:20, rank:'gross_buy', pct_min:20, ratio_min:0.5, part_min:1, flow_min:-5 }],
  FL11:[{ lag:'1' }, { lag:'5', window:3 }, { lag:'window', window:4, scope:'all', investors:['Foreign'] }, { denom:'filter' }],   // a saved denom is ignored
  FL12:[{ window:2 }, { window:12, scope:'all' }],
  FL18:[{ anchor:'2026-01-20' }, { anchor:'2026-01-25', scope:'selected', brokers:['CC', 'XL'] }, { anchor:'2030-01-01' }, { anchor:'2026-01-20', rank:'net_sell', top:1 }, { anchor:'2026-01-10', scope:'all' }],
  FL19:[{ anchor:'2026-01-20' }, { anchor:'2026-01-25', scope:'selected', brokers:['CC', 'XL'] }, { anchor:'2030-01-01' }, { anchor:'2026-01-20', rank:'net_sell', top:1 }, { anchor:'2026-01-10', scope:'all' }, { top:8 }],
};
/* the plain data with every variant; the data with gaps, odd lots and large values with a few. Buy and Sell are both
   asked whatever the side (the card may ask either); a variant's candles are all checked, the others every third. */
const FEW: Record<string, any>[] = [{}, { scope:'selected', brokers:['BK', 'ZP', 'QQ'] }, { scope:'all', window:3 }];

describe('explainFlowA.ts: every output and parameter equals calc/flow.ts', () => {
  const data: [string, FlowContext][] = [['plain', synth(11)], ['gaps', synth(5, { gaps:true })], ['odd lots', synth(23, { odd:true })], ['big', synth(3, { big:true })]];
  for (const id of Object.keys(FLOW_EXPLAIN_A).filter(i => i !== 'FL24')) for (const [name, c] of data) it(`${id} ${name}`, () => {
    const def = flowDefaults(id), explain = FLOW_EXPLAIN_A[id], last = c.dates.length - 1;
    let checked = 0;
    const variants = name === 'plain' ? [...COHORT, ...(EXTRA[id] ?? [])] : [...FEW, ...(EXTRA[id] ?? []).slice(0, 1)];
    for (const v of variants) {
      if (Object.keys(v).some(k => !(k in def))) continue;
      const p = { ...def, ...v }, both = computeFlow(id, c, { ...p, side:'both' });
      const sided = 'buy' in both || 'sell' in both, out = sided ? both : computeFlow(id, c, p);
      const step = name === 'plain' && (v === COHORT[0] || v === (EXTRA[id] ?? [])[0]) ? 1 : 3;
      for (const key of Object.keys(out))
        for (let t = 0; t <= last; t += t + step > last && t < last ? last - t : step)
          checked += same(explain(c, p, t, key), out[key][t], `${id} ${name} ${JSON.stringify(v)} ${key} t=${t}`, key);
      /* left out, the output is the side the parameters draw (Both: buy) */
      for (const side of sided ? ['buy', 'sell', 'both'] : [undefined]) {
        const q = side ? { ...p, side } : p, main = sided ? (side === 'sell' ? 'sell' : 'buy') : Object.keys(out)[0], e = explain(c, q, last);
        if (e) expect(e.output).toBe(main);
      }
      expect(explain(c, p, last, 'nope')).toBeNull();
    }
    expect(checked, `${id}: values checked`).toBeGreaterThan(name === 'plain' ? 50 : 10);
  }, 60_000);
  it('FL09 flags both ways', () => {
    const c = synth(11), p = { ...flowDefaults('FL09'), baseline:20, pct_min:30, ratio_min:0.8, part_min:2, flow_min:0 };
    const s = computeFlow('FL09', c, p).value.filter(v => v !== null);
    expect(s).toContain(1); expect(s).toContain(0);
  });
});
