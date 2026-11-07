/* QA5 unit B (the Screener's flow page) and the 20-question front-end test, on the fixture, which is the worker's own
   catalog and computation (tests/fixture/api.ts, engine.ts): the fixture lists exactly the generated catalog and presets
   and runs them with the core (the silent preset included); its broker data is the same in every engine; a rank is over
   the filtered universe (decision C); a screen while the broker data loads is refused FLOW_UNAVAILABLE on its card, and a
   stock without broker data reads n/a with its reason; the depth refusal states one count; an empty broker list, an
   operator row's toast and a flow series' session field say what they mean; the close against a flow price level is a
   condition of its own, read at the broker data date. Every case is chosen from the catalog's data, not by an id the
   catalog may change. */
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import type { CatalogResponse, Definition, RunResponse, Test } from '../../src/core/contract.ts';
import { METRICS_CATALOG } from '../../src/core/catalog.ts';
import { presetDefinitions, validateTest, availabilityMap } from '../../src/core/validate.ts';
import { applyUniverse } from '../../src/core/universe.ts';
import { percentRank } from '../../src/core/xsection.ts';
import { BY_ID, calculate, resolveParams } from '../../../backtest/src/core/registry.ts';
import { entriesOf, optionText } from '../../src/entries.ts';
import { condText, fromWire, newCard, toWire } from '../../src/forms.ts';
import { ctx, freshUniverse, S } from '../../src/state.ts';
import { cancelRun, screenNow, sync } from '../../src/run.ts';
import { ALL, OP_OPT, addItem, listItems, resetRules, ruleOf, setOpt } from '../../src/add-condition.ts';
import { defaultOp, measuresFor, seriesList, withMeasure, withTest } from '../../src/operators.ts';
import { paramTitle } from '../../src/param-fields.ts';
import { cellText, levelAtFlowDate } from '../../src/cell-text.ts';
import { cellTitle, errorText, levelAsOfText } from '../../src/texts.ts';
import { ApiFailure } from '../../src/api/types.ts';
import { vctx } from '../core/helpers.ts';
import { fixtureApi } from '../fixture/api.ts';
import { FLOW_CTX, NO_BROKER_DATA } from '../fixture/broker.ts';

let catalog: CatalogResponse;
const fx = fixtureApi();
beforeAll(async () => {
  const c = await fx.catalog(null); if (c.status !== 200) throw new Error('fixture catalog');
  catalog = c.body;
});
const use = (cat: CatalogResponse) => { ctx.catalog = cat; ctx.entries = entriesOf(cat); ctx.byKey = new Map(ctx.entries.map(e => [e.key, e])) };
beforeEach(() => {
  use(catalog);
  ctx.api = { run: () => { throw new Error('the window sent a run') } } as never;
  ctx.metrics = []; S.universe = freshUniverse(); S.cards = []; S.errors = {};
  resetRules();
});
const flows = () => ctx.entries.filter(e => e.flow && e.available);
const CTX = { ...vctx(['BBCA']), flow: FLOW_CTX, availability: availabilityMap({}, METRICS_CATALOG, undefined, FLOW_CTX) };
const refusal = (t: Test) => { try { validateTest(t, 'f', CTX); return null } catch (e) { return e as { code: string } } };
const run = async (api: ReturnType<typeof fixtureApi>, def: Definition): Promise<RunResponse> => (await api.run({ schema_version: 1, definition: def, options: { exhaustive: true, explain: false } } as never)).body;
/** the default universe of the presets, every stock listed */
const U = () => ({ ...catalog.presets[0].definition.universe });
/** the screen on the page: its cards, Screen now, and the answer or the refusal on its card */
async function screenOnPage(api: ReturnType<typeof fixtureApi>, cards: typeof S.cards) {
  ctx.api = api; ctx.universe = (await api.universe(null) as never as { body: never }).body;
  S.cards = cards; sync(); screenNow();
  for (let k = 0; k < 100 && ctx.running; k++) await new Promise(ok => setTimeout(ok, 5));
}

describe('the fixture is the generated catalog and presets, computed by the core (item 4)', () => {
  it('lists every catalog entry in its order with the worker\'s availability, and no entry the catalog dropped', () => {
    const listed = [...catalog.metrics, ...catalog.fundamentals].map(m => m.id).sort();
    expect(listed).toEqual(METRICS_CATALOG.metrics.map(m => m.id).sort());
    expect(catalog.metrics.filter(m => !/fundamental/i.test(m.group)).map(m => m.id)).toEqual(METRICS_CATALOG.metrics.filter(m => !/fundamental/i.test(m.group)).map(m => m.id));
    const words = JSON.stringify([...catalog.metrics, ...catalog.fundamentals].map(m => (m as { label?: string }).label));
    for (const old of ['Broker net buy', 'Top-N broker net', 'Bandar status', 'Foreign net-buy streak']) expect(words).not.toContain(old);
  });
  it('serves the presets of presets.json with their own legs, each available one counted by the core', () => {
    expect(catalog.presets.map(p => [p.id, p.definition])).toEqual(presetDefinitions().map(p => [p.id, p.definition]));
    const avail = catalog.presets.filter(p => p.availability === 'AVAILABLE');
    expect(avail.length).toBeGreaterThan(10);
    // the silent preset (a pattern the fixture's own evaluator did not know) runs: the core's pattern signal
    const silent = catalog.presets.find(p => p.definition.conditions.some(c => (c.test as { pattern?: { type?: string } }).pattern?.type === 'silent'))!;
    expect(silent.availability).toBe('AVAILABLE');
    expect(typeof silent.match_count).toBe('number');
  });
  it('a preset run answers what its catalog counts say, every enabled leg summarized', async () => {
    for (const p of catalog.presets.filter(x => x.availability === 'AVAILABLE' && x.match_count != null)) {
      const r = await run(fx, p.definition);
      expect([p.id, r.match_count, r.conditions.length]).toEqual([p.id, p.match_count, p.definition.conditions.filter(c => c.enabled).length]);
    }
  });
});

describe('the fixture\'s broker data is the same in every engine (20-question test, item A)', () => {
  it('does not depend on the engine\'s sort: data built under another sort algorithm is identical', async () => {
    const a = await import('../fixture/data.ts');
    vi.resetModules();
    const sort = Array.prototype.sort;
    // an insertion sort: a valid sort with another order of comparisons than the engine's
    Object.defineProperty(Array.prototype, 'sort', { configurable: true, writable: true, value(this: unknown[], f?: (x: unknown, y: unknown) => number) {
      const cmp = f ?? ((x: unknown, y: unknown) => String(x) < String(y) ? -1 : String(x) > String(y) ? 1 : 0);
      for (let i = 1; i < this.length; i++) { const v = this[i]; let j = i - 1; while (j >= 0 && cmp(this[j], v) > 0) { this[j + 1] = this[j]; j-- } this[j + 1] = v }
      return this;
    } });
    let b;
    try { b = await import('../fixture/data.ts') } finally { Object.defineProperty(Array.prototype, 'sort', { configurable: true, writable: true, value: sort }) }
    expect(b).not.toBe(a);
    for (const tk of ['BBCA', 'PANI', 'BJBR', 'GOTO']) {
      expect(b.T[tk].bandarIdx, tk).toEqual(a.T[tk].bandarIdx);
      expect(Array.from(b.T[tk].net[0] as Float64Array), tk).toEqual(Array.from(a.T[tk].net[0] as Float64Array));
    }
  });
});

describe('a rank is over the filtered universe (decision C; 20-question test, item B)', () => {
  it('ADV20 at least the median and RSI rank >= 90: the core\'s rank over the universe\'s stocks, not over every listed one', async () => {
    const rows = (await fx.universe(null) as never as { body: { rows: { ticker: string; adv20_idr: number | null }[] } }).body.rows;
    const base = applyUniverse(rows as never, U()).eligible.map(r => r.adv20_idr!).sort((a, b) => a - b);
    const median = base[Math.floor((base.length - 1) / 2)];
    const e = ctx.byKey.get(ctx.entries.find(x => x.kind === 'indicator' && x.label === 'Relative Strength Index')!.key)!;
    const op = withTest(e.ops!, e, { ...defaultOp(e.ops!, e), measure: 'none', margs: {} }, 'rank');
    const def: Definition = { universe: { ...U(), adv20_min_idr: median }, conditions: [toWire(e, newCard(e, [], { op: { ...op, cmp: 'ge', value: 90 } }))], logic: 'all' };
    const got = (await run(fx, def)).rows.filter(r => r.status === 'match').map(r => r.ticker).sort();
    // the expectation, apart from the fixture: RSI (the registry's formula) at each stock's last bar, ranked among the
    // S0 survivors of this universe
    const m = fx.market, pop = applyUniverse(rows as never, def.universe).eligible.map(r => r.ticker);
    const reg = BY_ID[e.key], rsi = (tk: string) => { const t = m.byTicker.get(tk)!, s = calculate(reg, { O: t.o, H: t.h, L: t.l, C: t.c, V: t.v, T: t.d }, resolveParams(reg, {})).rsi; return s[s.length - 1] as number };
    const values = new Map(pop.map(tk => [tk, rsi(tk)] as [string, number]));
    const ranks = percentRank(values, new Set(pop));
    const want = pop.filter(tk => (ranks.get(tk) ?? -1) >= 90).sort();
    expect(got).toEqual(want);
    expect(got).toContain('PANI');
    expect(got.length).toBe(5);
    // ranked over every listed stock it would be another answer (the fixture's old population)
    const all = new Map(m.tickers.filter(t => !t.remarks.length).map(t => [t.ticker, rsi(t.ticker)] as [string, number]));
    const wide = percentRank(all, new Set(all.keys()));
    expect(pop.filter(tk => (wide.get(tk) ?? -1) >= 90).sort()).not.toEqual(want);
  });
});

describe('broker data that is not there (item 5)', () => {
  it('a stock without broker data in the window: its flow cell is n/a with that reason, shown in a default screen', async () => {
    const e = flows().find(x => x.opts.some(o => o.kind === 'value'))!;
    const sma = ctx.entries.find(x => x.kind === 'indicator' && x.opts.some(o => o.form === 'state_level'))!;
    const flow = newCard(e, [], { opt: e.opts.find(o => o.kind === 'value')!.key, value: -1e18 });
    const level = newCard(sma, [flow.id], { opt: sma.opts.find(o => o.form === 'state_level' && o.op === 'gt')!.key });
    const tk = [...NO_BROKER_DATA].find(t => fx.market.byTicker.get(t)?.sector)!;
    const r = await run(fx, { universe: U(), conditions: [toWire(e, flow), toWire(sma, level)], logic: 'any' });
    const row = r.rows.find(x => x.ticker === tk)!;
    expect(row, `${tk} is not a row of a default screen`).toBeDefined();
    const cell = row.cells.find(c => c.id === flow.id)!;
    expect(cell).toMatchObject({ status: 'na', reason: 'FLOW_UNAVAILABLE', eval_date: null });
    expect(cellText(e, flow, cell)).toBe('n/a');
    expect(cellTitle(cell, row.remarks, r.data.evaluation_date, true)).toMatch(/no broker data in the sessions the Screener holds/);
    expect(r.conditions.find(s => s.id === flow.id)!.na).toBeGreaterThanOrEqual(1);
  });
  it('the broker data still loading: flow entries and flow presets unavailable, a flow screen refused FLOW_UNAVAILABLE on its card', async () => {
    const loading = fixtureApi({ brokerLoading: 12 }), cat = (await loading.catalog(null) as { body: CatalogResponse }).body;
    expect(cat.data.broker_window).toMatchObject({ sessions: 12, complete: false });
    // every flow entry the complete window offers (an entry that needs data the Screener does not hold keeps its reason)
    const fl = cat.metrics.filter(m => m.flow && catalog.metrics.find(x => x.id === m.id)?.availability === 'AVAILABLE');
    expect(fl.length).toBeGreaterThan(40);
    for (const m of fl) expect([m.id, m.availability, m.reason]).toEqual([m.id, 'REQUIRES_DATA', expect.stringMatching(/still loading \(12 sessions loaded so far\)/)]);
    const flowPreset = cat.presets.find(p => p.definition.conditions.some(c => JSON.stringify(c.test).includes('"kind":"flow"')))!;
    expect(flowPreset.availability).toBe('REQUIRES_DATA');
    // a flow card kept from before (a saved screen, the last open screen): the worker refuses it, on its card
    const e = flows().find(x => x.opts.some(o => o.kind === 'value'))!, card = newCard(e, [], { opt: e.opts.find(o => o.kind === 'value')!.key, value: 0 });
    let refused: ApiFailure | null = null;
    try { await run(loading, { universe: U(), conditions: [toWire(e, card)], logic: 'all' }) } catch (x) { refused = x as ApiFailure }
    expect(refused).toMatchObject({ code: 'METRIC_UNAVAILABLE', field: expect.stringMatching(/^definition\.conditions\[0\]\.test/), details: expect.objectContaining({ reason_code: 'FLOW_UNAVAILABLE' }) });
    use(cat);
    await screenOnPage(loading, [card]);
    expect(ctx.refused?.id).toBe(card.id);
    expect(ctx.refused!.message).toMatch(new RegExp(`^Condition 1 \\(${e.label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\) is not available yet: The broker data is still loading \\(12 sessions loaded so far\\).*Switch it off or remove it to run the screen\\.$`));
    cancelRun();
  });
});

describe('the depth refusal states one count (D2)', () => {
  it('an anchor at its last session and a percentile over 30: "this one needs N sessions", the fix without the example\'s count', async () => {
    // an indicator anchored a number of sessions back (its anchor parameter's range ends one session short of the window)
    const e = flows().find(x => x.params.some(p => p.sessions && p.max === x.flow!.sessions - 1) && seriesList(x).some(s => s.drawn && measuresFor(x.ops!, x, s.key).some(m => m.fn === 'percentile')))!;
    const anchor = e.params.find(p => p.sessions && p.max === e.flow!.sessions - 1)!;
    const params = { ...newCard(e, []).params, [anchor.key]: anchor.max! };
    const s = seriesList(e, params).find(x => x.drawn && measuresFor(e.ops!, e, x.key, params).some(m => m.fn === 'percentile'))!;
    const op = withMeasure(e.ops!, e, defaultOp(e.ops!, e, s.key, params), 'percentile', params);
    const card = Object.assign(newCard(e, [], { op: { ...op, margs: { ...op.margs, length: 30 } } }), { params });
    let refused: ApiFailure | null = null;
    try { await run(fx, { universe: U(), conditions: [toWire(e, card)], logic: 'all' }) } catch (x) { refused = x as ApiFailure }
    expect(refused?.code).toBe('LIMIT_EXCEEDED');
    const needed = refused!.details!.needed as number;
    expect(needed).toBeGreaterThan(e.flow!.sessions);
    await screenOnPage(fx, [card]);
    expect(ctx.refused?.id).toBe(card.id);
    const msg = ctx.refused!.message;
    expect(msg).toMatch(new RegExp(`^Limit reached in condition 1 \\(.+\\): a flow condition reads at most the ${e.flow!.sessions} sessions of broker data the Screener holds: the indicator's own window plus the operator's N, length or within; this one needs ${needed} sessions\\. Use a shorter window or N\\.$`));
    expect(msg).not.toMatch(/in all/);
    expect(msg.match(/\d+ sessions/g)).toEqual([`${e.flow!.sessions} sessions`, `${needed} sessions`]);
    cancelRun();
  });
  it('a limit whose refused example names only the limit keeps its fix (the rule\'s own number is no example count)', () => {
    use({ ...catalog, limits: catalog.limits });
    expect(errorText('LIMIT_EXCEEDED', { details: { limit: 'within_max', allowed: 130, needed: 131 } })).toMatch(/Use 130 or fewer\.$/);
  });
});

describe('words of the flow fields (item 3; 20-question test, items D and E)', () => {
  it('an empty broker list reads as what it means, never "default default brokers"', () => {
    const lists = flows().flatMap(e => e.params.filter(p => p.type === 'brokers').map(p => [e, p] as const));
    expect(lists.length).toBeGreaterThan(10);
    for (const [e, p] of lists) {
      const t = paramTitle(p, p.default);
      expect(t, `${e.key} ${p.key}`).not.toMatch(/default default/);
      expect(optionText(p, ''), `${e.key} ${p.key}`).toBe(typeof p.wire === 'string' ? `the ${String(p.wire).replace(/^class:/, '')} brokers` : 'none named');
    }
    // a named list reads by its codes
    expect(optionText(lists[0][1], 'YP,AK')).toBe('YP + AK');
  });
  it('a row added with an operator names the operator\'s rule in its toast', () => {
    const e = flows().find(x => x.opts.length && seriesList(x).some(s => s.drawn))!;
    setOpt(e, OP_OPT);
    const r = addItem(listItems('', ALL, 'group').find(it => it.key === e.key)!);
    expect(r.ok).toBe(true);
    expect(r.message.startsWith(`${e.label} added · `)).toBe(true);
    expect(r.message).not.toMatch(/·\s*$/);
    expect(r.message.slice(`${e.label} added · `.length)).toBe(condText(e, S.cards[0]).split(': ').slice(1).join(': '));
    // a row with its own condition names that condition
    const f = flows().find(x => x !== e && x.opts.length)!;
    expect(addItem(listItems('', ALL, 'group').find(it => it.key === f.key)!).message).toBe(`${f.label} added · ${f.opts.find(o => o.key === ruleOf(f).opt)!.label}`);
  });
});

describe('the close against a flow price level (20-question test, item C)', () => {
  /** the flow entries with a price-level output, from the catalog's kinds */
  const levels = () => flows().filter(e => seriesList(e).some(s => s.drawn && s.comparable === 'close'));
  it('is offered as "Close above / below <the line>", taken by the core, read back to the same card', () => {
    expect(levels().length).toBeGreaterThan(2);
    for (const e of levels()) {
      const o = e.opts.filter(x => x.form === 'state_level');
      expect(o.map(x => x.label), e.key).toEqual([`Close above ${seriesList(e).find(s => s.comparable === 'close')!.label}`, `Close below ${seriesList(e).find(s => s.comparable === 'close')!.label}`]);
      for (const x of o) {
        const c = newCard(e, [], { opt: x.key }), w = toWire(e, c);
        expect(w.test).toMatchObject({ kind: 'state', lhs: { kind: 'price', field: 'close' }, op: x.op, rhs: { kind: 'flow', metric: e.key } });
        expect(refusal(w.test), `${e.key} ${x.key}`).toBeNull();
        const back = fromWire(w, ctx.byKey);
        expect([back.raw, back.opt]).toEqual([undefined, x.key]);
        expect(levelAtFlowDate(back, e)).toBe(true);
      }
      // the open is not the line's comparable field: kept raw, never read as the close
      const w = toWire(e, newCard(e, [], { opt: o[0].key }));
      expect(fromWire({ ...w, test: { ...w.test, lhs: { kind: 'price', field: 'open' } } as Test }, ctx.byKey).raw).toBeDefined();
    }
    // no other flow output is offered it
    for (const e of flows().filter(x => !levels().includes(x))) expect(e.opts.some(x => x.form === 'state_level'), e.key).toBe(false);
  });
  it('the card says both sides are of the broker data date, for the condition and for an operator comparing with the close', () => {
    const e = levels()[0], d = catalog.data;
    const words = levelAsOfText(d);
    expect(words).toMatch(new RegExp(`^Both sides as of the broker data date, \\d{1,2} [A-Z][a-z]{2} \\(each stock's latest broker data; prices are of \\d{1,2} [A-Z][a-z]{2}\\)\\.$`));
    const s = seriesList(e).find(x => x.comparable === 'close')!;
    const rel = e.ops!.measures.find(m => m.second)!;
    const op = withMeasure(e.ops!, e, defaultOp(e.ops!, e, s.key), rel.fn);
    expect(op.by).toBe('price:close');
    expect(levelAtFlowDate(newCard(e, [], { op }), e)).toBe(true);
    // other cards say nothing of it
    expect(levelAtFlowDate(newCard(e, [], { op: withMeasure(e.ops!, e, defaultOp(e.ops!, e, s.key), measuresFor(e.ops!, e, s.key).find(m => !m.second)!.fn) }), e)).toBe(false);
    const k = flows().find(x => !levels().includes(x) && x.opts.length)!;
    expect(levelAtFlowDate(newCard(k, []), k)).toBe(false);
  });
  it('the fixture runs it at each stock\'s broker data date', async () => {
    const e = levels()[0], c = newCard(e, [], { opt: e.opts.find(x => x.form === 'state_level')!.key });
    const r = await run(fx, { universe: U(), conditions: [toWire(e, c)], logic: 'all' });
    expect(r.conditions[0]).toMatchObject({ eval_date_basis: 'flow_date', source: 'flow' });
    expect(r.rows.length).toBeGreaterThan(0);
    for (const row of r.rows) expect(row.cells[0].eval_date).toBe(catalog.data.broker_window!.last);
  });
});
