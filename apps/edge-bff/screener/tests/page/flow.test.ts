/* The Terminal's flow indicators on the page (EXEC-SCREENER-FLOW-CANDLES P5c; verification/screener/P5_FLOW.md
   section 4, OPERATORS.md sections 3-5), over the fixture catalog, whose flow entries are the core's own as the worker
   publishes them (tests/fixture/api.ts FLOW_METRICS): every condition and every measure x test x comparison the page
   offers on every flow output builds a wire test the core's own validation accepts (the page never offers what the core
   refuses) and reads back to the same card; what the page does not offer for an output's type, the core refuses;
   "=" and "!=" are offered exactly where the core takes them (K7); the broker sessions (K1) bound the fields; the
   Terminal's parameters (lists, broker codes, selects, whole numbers, an anchor date) travel in the Terminal's shapes;
   and a flow cell names its broker data date. Every case is chosen from the catalog's data, never by an indicator id,
   so a change of the catalog needs no change here. */
import { beforeAll, beforeEach, describe, expect, it } from 'vitest';
import type { CatalogResponse, Test } from '../../src/core/contract.ts';
import { depthHint, entriesOf, flowBudget, flowOutputs, type Entry } from '../../src/entries.ts';
import { cardErrors, condText, fromWire, newCard, toWire, type Card } from '../../src/forms.ts';
import { canonical, ctx, freshUniverse, S } from '../../src/state.ts';
import { cancelRun, screenNow, sync } from '../../src/run.ts';
import { OP_OPT, addItem, listItems, resetRules, ruleErrors, ruleOf, setOpt, ALL } from '../../src/add-condition.ts';
import { defaultOp, fieldHint, fieldMax, measuresFor, opsFor, plainOffered, seriesList, testsFor, withMeasure, withTest, type OpState } from '../../src/operators.ts';
import { cellTitle, flowDateShown } from '../../src/texts.ts';
import { cellText } from '../../src/cell-text.ts';
import { validateTest, availabilityMap } from '../../src/core/validate.ts';
import { METRICS_CATALOG } from '../../src/core/catalog.ts';
import { vctx } from '../core/helpers.ts';
import { fixtureApi } from '../fixture/api.ts';
import { BROKER_WINDOW, FLOW_CTX } from '../fixture/broker.ts';

let catalog: CatalogResponse;
beforeAll(async () => {
  const c = await fixtureApi().catalog(null); if (c.status !== 200) throw new Error('fixture catalog');
  catalog = c.body;
});
beforeEach(() => {
  ctx.catalog = catalog; ctx.entries = entriesOf(catalog); ctx.byKey = new Map(ctx.entries.map(e => [e.key, e]));
  ctx.api = { run: () => { throw new Error('the window sent a run') } } as never;
  ctx.metrics = []; S.universe = freshUniverse(); S.cards = []; S.errors = {};
  resetRules();
});
/** the worker's validation context on the fixture's complete broker window (K1: 60 sessions) */
const CTX = { ...vctx(['BBCA']), flow: FLOW_CTX, availability: availabilityMap({}, METRICS_CATALOG, undefined, FLOW_CTX) };
const flows = () => ctx.entries.filter(e => e.flow && e.available);
const refusal = (t: Test, where = 'f'): { code: string; field?: string } | null => { try { validateTest(t, where, CTX); return null } catch (e) { return e as { code: string; field?: string } } };
const accepts = (e: Entry, c: Card, where: string) => {
  expect(cardErrors(e, c), where).toEqual({});
  const w = toWire(e, c), r = refusal(w.test, where);
  expect(r && `${r.code} ${r.field}: ${(r as unknown as Error).message}`, where).toBeNull();
  const back = fromWire(w, ctx.byKey);
  expect(back.raw, where).toBeUndefined();
  expect(canonical(toWire(e, back).test), where).toBe(canonical(w.test));
  return w;
};

describe('every flow condition the page offers is one the core accepts, and reads back', () => {
  it('lists the catalog\'s flow indicators with their Terminal parameters', () => {
    expect(flows().length).toBeGreaterThan(40);
    for (const e of flows()) {
      expect(e.group).toBe('Flow');
      // the parameters a condition takes: the catalog's, the kinds that only draw left out
      expect(e.params.map(p => p.key)).toEqual(e.flow!.params.filter(p => p.condition && p.default !== undefined).map(p => p.key));
      expect(e.ops).toBeDefined();
    }
    // the lists (boards, investor types), selects and whole numbers are there with their options and ranges
    const types = new Set(flows().flatMap(e => e.params.map(p => p.type)));
    for (const t of ['multi', 'enum', 'integer']) expect(types).toContain(t);
    const boards = flows().flatMap(e => e.params).find(p => p.type === 'multi')!;
    expect(boards.options!.length).toBeGreaterThan(1);
    expect(listItems('', ALL, 'group').filter(it => it.entry?.flow).length).toBe(ctx.entries.filter(e => e.flow).length);
  });
  it('the card\'s own conditions on every drawn output', () => {
    let n = 0;
    for (const e of flows()) for (const o of e.opts) {
      if (!flowOutputs(e).find(x => x.key === o.output)?.drawn) continue;
      accepts(e, newCard(e, [], { opt: o.key, value: 1, value2: 2 }), `${e.key} ${o.key}`); n++;
    }
    expect(n).toBeGreaterThan(150);
  });
  it('every measure x test x comparison on every drawn output, at the catalog setup', () => {
    let n = 0;
    for (const e of flows()) {
      const ops = e.ops!;
      for (const s of seriesList(e).filter(x => x.drawn)) {
        for (const m of [...(plainOffered(ops, e, s.key) ? [{ fn: 'none' }] : []), ...measuresFor(ops, e, s.key)]) {
          let op = withMeasure(ops, e, defaultOp(ops, e, s.key), m.fn);
          for (const t of testsFor(ops, e, op)) {
            op = withTest(ops, e, op, t.key);
            for (const cmp of opsFor(e, op, t)) {
              const o: OpState = { ...op, cmp, value: 1, value2: cmp === 'between' || cmp === 'outside' ? 2 : '' };
              accepts(e, newCard(e, [], { op: o }), `${e.key}.${s.key}.${m.fn}.${t.key}.${cmp}`); n++;
            }
          }
        }
      }
    }
    expect(n).toBeGreaterThan(2000);
  }, 60_000);                                                           // a few thousand validations: seconds under a full parallel run
  it('what the page leaves out for an output type, the core refuses (OPERATORS.md section 4)', () => {
    let n = 0;
    for (const e of flows()) {
      const ops = e.ops!, B = flowBudget(e) ?? 60;
      for (const s of seriesList(e).filter(x => x.drawn && x.type)) {
        const plain: OpState = { output: s.key, measure: 'none', margs: {}, by: '', test: 'value', cmp: 'gt', value: 1, value2: '', n: '', k: '' };
        // a test its type does not take (not_on), or a cross of a fixed value it takes only against a series
        for (const t of ops.tests) {
          const off = (t.not_on || []).includes(s.type!) || (t.key === 'cross' && ((t as { not_against_value?: string[] }).not_against_value || []).includes(s.type!));
          if (!off || ((t.within || t.length) && B < 2)) continue;
          expect(testsFor(ops, e, plain).map(x => x.key), `${e.key}.${s.key} ${t.key}`).not.toContain(t.key);
          const cmp = t.key === 'range' ? 'between' : t.key === 'cross' ? 'crosses_above' : t.ops[0];
          const w = toWire(e, newCard(e, [], { op: { ...plain, test: t.key, cmp, value2: 2, n: 1, k: 1 } }));
          expect(refusal(w.test)?.code, `${e.key}.${s.key} ${t.key}`).toBe('INVALID_CONDITION'); n++;
        }
        // a measure its type does not take
        for (const m of ops.measures.filter(x => x.not_on.includes(s.type!))) {
          expect(measuresFor(ops, e, s.key).map(x => x.fn)).not.toContain(m.fn);
          const w = toWire(e, newCard(e, [], { op: { ...plain, measure: m.fn, margs: { length: 2, bars: 1 } } }));
          expect(refusal(w.test)?.code, `${e.key}.${s.key} ${m.fn}`).toBe('INVALID_CONDITION'); n++;
        }
      }
    }
    expect(n).toBeGreaterThan(50);
  });
  it('"=" and "!=" exactly where the core takes them: the series itself of a whole-number output (K7)', () => {
    let yes = 0, no = 0;
    for (const e of flows()) for (const s of seriesList(e).filter(x => x.drawn)) {
      const ops = e.ops!, op: OpState = { output: s.key, measure: 'none', margs: {}, by: '', test: 'value', cmp: 'eq', value: 1, value2: '', n: '', k: '' };
      const offered = testsFor(ops, e, op).some(t => t.key === 'value') && opsFor(e, op, ops.tests.find(t => t.key === 'value')!).includes('eq');
      const taken = refusal(toWire(e, newCard(e, [], { op })).test) === null;
      expect(offered, `${e.key}.${s.key} (${s.type})`).toBe(taken);
      offered ? yes++ : no++;
      // never on a measured series
      const pct = withMeasure(ops, e, { ...op, cmp: 'ge' }, measuresFor(ops, e, s.key)[0]?.fn ?? 'none');
      if (pct.measure !== 'none') expect(opsFor(e, pct, ops.tests.find(t => t.key === 'value')!)).not.toContain('eq');
    }
    expect(yes).toBeGreaterThan(0); expect(no).toBeGreaterThan(0);
  });
});

describe('the broker sessions (K1): the fields stop where the broker data does', () => {
  it('an indicator that reads every loaded session at its setup takes no measure and no test over sessions; the core agrees', () => {
    const full = flows().find(e => flowBudget(e) === 0 && seriesList(e).some(s => s.drawn))!;
    expect(full).toBeDefined();
    const ops = full.ops!, s = seriesList(full).find(x => x.drawn)!;
    expect(measuresFor(ops, full, s.key)).toEqual([]);
    const plain: OpState = { output: s.key, measure: 'none', margs: {}, by: '', test: 'value', cmp: 'gt', value: 1, value2: '', n: '', k: '' };
    expect(testsFor(ops, full, plain).filter(t => t.within || t.length)).toEqual([]);
    expect(full.opts.some(o => o.within)).toBe(false);
    const w = toWire(full, newCard(full, [], { op: { ...plain, measure: 'change', margs: { bars: 1 } } }));
    expect(refusal(w.test)).toMatchObject({ code: 'LIMIT_EXCEEDED' });
  });
  it('N: at most the broker sessions held, a hint of what the setup leaves, no refusal in place; the worker refuses too deep, on its card', async () => {
    const e = flows().find(x => { const B = flowBudget(x); return B != null && B >= 20 && B <= 55 && seriesList(x).some(s => s.drawn && (s.type === 'K' || s.type === 'Rp')) })!;
    const ops = e.ops!, s = seriesList(e).find(x => x.drawn && (x.type === 'K' || x.type === 'Rp'))!, B = flowBudget(e)!;
    let op = withTest(ops, e, withMeasure(ops, e, defaultOp(ops, e, s.key), 'percentile'), 'ever');
    const len = op.margs.length as number;
    expect(len).toBeLessThanOrEqual(Math.floor(B / 2));                 // opens within half the sessions the hint leaves
    expect(fieldMax(ops, e, op, 'n', 130)).toBe(e.flow!.sessions);    // the hard maximum: the broker sessions held
    expect(fieldMax(ops, e, op, 'arg', 130)).toBe(e.flow!.sessions);
    expect(fieldHint(ops, e, op, 'n')).toBe(B - len);
    expect(depthHint(fieldHint(ops, e, op, 'n'))).toBe(`about ${B - len} sessions of broker data left at this setup`);
    accepts(e, newCard(e, [], { op: { ...op, n: B - len } }), 'at the hint');
    // one more: not refused in place, refused by the worker (the core's depthRefusal), shown on its card
    const deep = newCard(e, [], { op: { ...op, n: B - len + 1 } });
    expect(cardErrors(e, deep)).toEqual({});
    expect(refusal(toWire(e, deep).test)).toMatchObject({ code: 'LIMIT_EXCEEDED' });
    expect(cardErrors(e, newCard(e, [], { op: { ...op, n: e.flow!.sessions + 1 } }))['o.n']).toMatch(/holds the last 60 sessions of broker data/);
    ctx.api = fixtureApi(); ctx.universe = (await fixtureApi().universe(null) as never as { body: never }).body;
    S.cards = [deep]; sync(); screenNow();
    for (let k = 0; k < 50 && ctx.running; k++) await new Promise(ok => setTimeout(ok, 5));
    expect(ctx.refused?.id).toBe(deep.id);
    expect(ctx.refused!.message).toMatch(/Limit reached in condition 1 .*: a flow condition reads at most the 60 sessions of broker data the Screener holds.*; this one needs \d+ sessions\. Use a shorter window or N\.$/);
    expect(ctx.refused!.message).not.toMatch(/in all/);                // one count: this one's, never the example's (QA5 D2)
    cancelRun();
  });
  it('a longer window of the indicator leaves fewer sessions to N', () => {
    const e = flows().find(x => x.params.some(p => p.sessions && typeof p.max === 'number' && (p.default as number) + 10 <= p.max) && (flowBudget(x) ?? 0) > 20)!;
    const p = e.params.find(q => q.sessions && typeof q.max === 'number' && (q.default as number) + 10 <= q.max)!;
    expect(flowBudget(e, { ...newCard(e, []).params, [p.key]: (p.default as number) + 10 })).toBe(flowBudget(e)! - 10);
  });
});

describe('the broker sessions at the boundary: the page\'s hint against the worker\'s own depth probe (the worker is the authority)', () => {
  /** the most N the core accepts for this window test (1..60; 0: none), and the page's hint for it */
  const limits = (e: Entry, params: Record<string, unknown>) => {
    const s = seriesList(e, params as never).find(x => x.drawn); if (!s) return null;
    const ops = e.ops!, base: OpState = { output: s.key, measure: 'none', margs: {}, by: '', test: 'ever', cmp: 'gt', value: 1, value2: '', n: 1, k: '' };
    const t = testsFor(ops, e, base, params as never).find(x => x.length); if (!t) return null;
    const op: OpState = { ...base, test: t.key, cmp: opsFor(e, { ...base, test: t.key }, t, params as never)[0], k: t.count ? 1 : '' };
    const card = (n: number) => { const c = newCard(e, [], { op: { ...op, n } }); Object.assign(c.params, params); return c };
    if (Object.keys(cardErrors(e, card(1))).length) return null;              // a setup refused in place on its own
    let core = 0;
    for (let n = 1; n <= 60; n++) {
      const r = refusal(toWire(e, card(n)).test); if (!r) { core = n; continue }
      if (n === 1 && r.code !== 'LIMIT_EXCEEDED') return null;          // a setup the core refuses on its own (a broker choice)
      expect(r.code).toBe('LIMIT_EXCEEDED'); break;
    }
    return { hint: fieldHint(ops, e, op, 'n', params as never)!, core, at: (n: number) => refusal(toWire(e, card(n)).test), errors: (n: number) => cardErrors(e, card(n)) };
  };
  it('at the catalog setup of every flow indicator the hint is the worker\'s limit: N = hint is taken, hint + 1 refused by the worker only', () => {
    let n = 0;
    for (const e of flows()) {
      const l = limits(e, newCard(e, []).params); if (!l) continue;
      expect(l.hint, e.key).toBe(l.core);
      if (l.hint >= 1) expect(l.at(l.hint), e.key).toBeNull();
      if (l.hint < 60) { expect(l.at(l.hint + 1)?.code, e.key).toBe('LIMIT_EXCEEDED'); expect(l.errors(l.hint + 1), e.key).toEqual({}) }
      n++;
    }
    expect(n).toBeGreaterThan(30);
  });
  it('at any other setup the page never blocks what the worker takes (a select, a capped baseline or a run limit makes the hint wrong)', () => {
    let n = 0, wrong = 0;
    for (const e of flows()) {
      const d = newCard(e, []).params, setups: Record<string, unknown>[] = [];
      for (const p of e.params) {
        if (p.type === 'integer') for (const dv of [5, -3]) { const v = (p.default as number) + dv; if ((p.min == null || v >= p.min) && (p.max == null || v <= p.max)) setups.push({ ...d, [p.key]: v }) }
        if (p.type === 'enum') for (const o of p.options || []) if (o !== p.default) setups.push({ ...d, [p.key]: o });
      }
      for (const params of setups) {
        const l = limits(e, params); if (!l || l.core < 1) continue;
        expect(l.errors(l.core), `${e.key} ${JSON.stringify(params)}`).toEqual({});           // N = the worker's limit is not refused in place
        if (l.hint !== l.core) wrong++;
        n++;
      }
    }
    expect(n).toBeGreaterThan(150);
    expect(wrong).toBeGreaterThan(0);                                   // the setups where the hint alone was stricter
  }, 60_000);                                                           // some thousand validations: seconds under a full parallel run
});

describe('the Terminal\'s parameters travel in its own shapes', () => {
  /** a card at these parameters: the entry's default condition, or its default operator where it has no condition */
  const card = (e: Entry, params: Record<string, unknown>) => {
    const c = newCard(e, [], e.opts.length ? {} : { op: defaultOp(e.ops!, e) }); Object.assign(c.params, params); return c;
  };
  it('a list (the boards): sent as a list, at least one, read back', () => {
    const e = flows().find(x => x.params.some(p => p.type === 'multi' && (p.options || []).length >= 3))!;
    const p = e.params.find(q => q.type === 'multi' && (q.options || []).length >= 3)!, two = p.options!.slice(0, 2).join(',');
    const w = accepts(e, card(e, { [p.key]: two }), 'two boards');
    expect(JSON.stringify(w.test)).toContain(JSON.stringify({ [p.key]: p.options!.slice(0, 2) }).slice(1, -1));
    expect(fromWire(w, ctx.byKey).params[p.key]).toBe(two);
    setOpt(e, e.def.opt); ruleOf(e).params = { ...ruleOf(e).params, [p.key]: '' };
    expect(ruleErrors(e)[`p.${p.key}`]).toMatch(/at least one/);
  });
  it('a select that names the lines (Side): the other line is refused in place, then taken once the select draws it', () => {
    const names = (x: Entry) => (p: Entry['params'][number]) => p.type === 'enum' && (p.options || []).filter(o => x.flow!.outputs.some(y => y.key === o)).length >= 2;
    const e = flows().find(x => x.params.some(names(x)) && x.opts.some(o => !seriesList(x).find(s => s.key === o.output)?.drawn))!;
    const side = e.params.find(names(e))!;
    const other = seriesList(e).find(s => !s.drawn && e.opts.some(o => o.output === s.key))!;
    const o = e.opts.find(x => x.output === other.key)!;
    const off = newCard(e, [], { opt: o.key, value: 1 });
    expect(cardErrors(e, off).op).toMatch(new RegExp(side.label!));
    expect(refusal(toWire(e, off).test)?.code).toBe('INVALID_CONDITION');
    // Side set to that line: the default line is now the one not drawn, and says so
    expect(cardErrors(e, card(e, { [side.key]: other.key })).op).toMatch(new RegExp(side.label!));
    accepts(e, Object.assign(newCard(e, [], { opt: o.key, value: 1 }), { params: { ...newCard(e, []).params, [side.key]: other.key } }), 'the other line');
  });
  it('broker codes: a scope of selected brokers names one; codes in capitals, sent as a list', () => {
    const e = flows().find(x => x.params.some(p => p.key === 'scope' && (p.options || []).includes('selected')) && x.params.some(p => p.key === 'brokers'))!;
    const none = card(e, { scope: 'selected', brokers: '' });
    expect(cardErrors(e, none).brokers).toMatch(/name at least one broker/);
    expect(refusal(toWire(e, none).test)?.code).toBe('INVALID_CONDITION');
    const w = accepts(e, card(e, { scope: 'selected', brokers: 'YP,AK' }), 'two brokers');
    expect(JSON.stringify(w.test)).toContain('"brokers":["YP","AK"]');
  });
  it('an anchor date, where an indicator has one: "view" or a date inside the broker data', () => {
    const e = flows().find(x => x.params.some(p => p.type === 'date'));
    if (!e) return;                                                     // the catalog may anchor by sessions instead
    const p = e.params.find(q => q.type === 'date')!;
    accepts(e, card(e, { [p.key]: BROKER_WINDOW.first }), 'first day');
    setOpt(e, e.def.opt); ruleOf(e).params = { ...ruleOf(e).params, [p.key]: '2001-01-02' };
    expect(ruleErrors(e)[`p.${p.key}`]).toMatch(/inside the broker data/);
  });
  it('a kept preset leg in a shape the page cannot keep stays raw, never changed', () => {
    const e = flows()[0], test = { kind: 'value', op: 'gt', value: 1, metric: { kind: 'flow', metric: e.key, params: { nope: 1 } } } as unknown as Test;
    const c = fromWire({ id: 'z', enabled: true, test }, ctx.byKey);
    expect(c.raw).toEqual(test);
  });
});

describe('Add a condition', () => {
  it('an output without a condition of its own (lots per transaction) opens on the operator; its card is added and taken by the core', () => {
    const e = flows().find(x => !x.opts.length && seriesList(x).some(s => s.drawn));
    if (!e) return;
    expect(ruleOf(e).opt).toBe(OP_OPT);
    expect(ruleErrors(e)).toEqual({});
    expect(addItem(listItems('', ALL, 'group').find(it => it.key === e.key)!).ok).toBe(true);
    const w = toWire(e, S.cards[0]);
    expect(refusal(w.test)).toBeNull();
    expect(condText(e, S.cards[0])).toContain(e.label);
  });
  it('a flow row added with its default condition is the core\'s', () => {
    for (const e of flows().filter(x => x.opts.length).slice(0, 12)) {
      const it0 = listItems('', ALL, 'group').find(it => it.key === e.key)!;
      const r = addItem(it0);
      if (!r.ok) { expect(r.message).toMatch(/:/); continue }               // refused in place, with its reason
      expect(refusal(toWire(e, S.cards[S.cards.length - 1]).test), e.key).toBeNull();
    }
  });
});

describe('a flow cell names its broker data date (P10 a)', () => {
  it('the fixture run: cells of the broker data date, summary flow_date, a stock without broker data n/a', async () => {
    const api = fixtureApi(), e = flows().find(x => x.opts.some(o => o.kind === 'value'))!;
    const c = newCard(e, [], { opt: e.opts.find(o => o.kind === 'value')!.key, value: -1e18 });
    const def = { universe: { ...catalog.presets[0].definition.universe, adv20_min_idr: 0, price_min: 0 }, conditions: [toWire(e, c)], logic: 'all' as const };
    const run = await api.run({ schema_version: 1, definition: def } as never);
    expect(run.body.conditions[0]).toMatchObject({ eval_date_basis: 'flow_date', source: 'flow' });
    const row = run.body.rows.find(r => r.ticker === 'BBCA')!, cell = row.cells[0];
    expect(cell.eval_date).toBe(BROKER_WINDOW.last);
    expect(cellTitle(cell, [], catalog.data.evaluation_date, true)).toBe(`Broker data of ${BROKER_WINDOW.last} (the stock's latest broker data; prices are of ${catalog.data.evaluation_date})`);
    expect(flowDateShown(cell, row.last_bar_date)).toMatch(/^\d{1,2} [A-Z][a-z]{2}$/);
    expect(cellText(e, c, cell)).not.toBe('n/a');
    // a stock without broker data in the window: n/a FLOW_UNAVAILABLE, no date (the core's noFlowCell)
    const none = await api.run({ schema_version: 1, definition: { ...def, universe: { ...def.universe, tickers: ['MTDL'] } } } as never);
    expect(none.body.conditions[0]).toMatchObject({ evaluated: 1, na: 1, passed: 0 });
    const cellOf = (await api.preview({ schema_version: 1, definition: def, ticker: 'MTDL', data_version: catalog.versions.price_data })).cells[0];
    expect(cellOf).toMatchObject({ status: 'na', reason: 'FLOW_UNAVAILABLE', eval_date: null });
    expect(cellTitle(cellOf, [], catalog.data.evaluation_date, true)).toMatch(/no broker data/);
  });
  it('is shown only when older than the stock\'s prices', () => {
    const cell = { id: 'a', status: 'pass', value: 1, eval_date: '2026-10-22', reason: null, remark: null } as const;
    expect(flowDateShown(cell, '2026-10-23')).toBe('22 Oct');
    expect(flowDateShown(cell, '2026-10-22')).toBeNull();
    expect(flowDateShown({ ...cell, status: 'na' }, '2026-10-23')).toBeNull();
  });
});
