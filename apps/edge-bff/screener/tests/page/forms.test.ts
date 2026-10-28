/* The page's card <-> wire mapping (src/forms.ts) on the generated catalog (src/core/screener-registry.json through
   the fixture catalog): every offered indicator test form builds a wire condition of report 8.5 and maps back onto the
   same card; a wire condition the page cannot map is kept as it is (raw), never changed; invalid input is refused in
   place, never rounded (report 9.2). */
import { describe, expect, it } from 'vitest';
import type { CatalogResponse, ConditionDef } from '../../src/core/contract.ts';
import { entriesOf, paramError, type Entry } from '../../src/entries.ts';
import { cardErrors, condText, fromWire, newCard, toWire, type Card } from '../../src/forms.ts';
import { fixtureApi } from '../fixture/api.ts';

const api = fixtureApi();
const cat = (await api.catalog(null)) as { status: 200; body: CatalogResponse };
const entries = entriesOf(cat.body), byKey = new Map(entries.map(e => [e.key, e]));
const strip = (c: Card) => ({ entry:c.entry, opt:c.opt, params:c.params, value:c.value, value2:c.value2, within:c.within, ...(c.opt.includes('_instance') ? { second:c.second } : {}) });

describe('catalog entries (entries.ts)', () => {
  it('offers every registry indicator with its tests, and the metrics and fundamentals', () => {
    expect(entries.filter(e => e.kind === 'indicator').length).toBe(cat.body.indicators.length);
    expect(entries.find(e => e.key === 'I01')!.opts.map(o => o.label)).toContain('Close above SMA');
    expect(entries.find(e => e.key === 'I09')!.opts.find(o => o.form === 'state_value')).toMatchObject({ label:'In uptrend', value:'fixed' });
  });
  it('keeps a test form the overlay shows disabled, with its reason (raw cumulative levels)', () => {
    const obv = byKey.get('I40')!;
    const off = obv.opts.filter(o => o.disabled);
    expect(off.length).toBeGreaterThan(0);
    expect(off[0].disabled).toMatch(/history starts/);
  });
  it('marks entries without data unavailable with their reason (P11 a)', () => {
    const roe = byKey.get('roe')!;
    expect(roe.available).toBe(false);
    expect(roe.reason).toMatch(/No data/);
  });
});

describe('toWire / fromWire (forms.ts)', () => {
  const cases: [string, Entry][] = [];
  for (const e of entries) if (e.available) for (const o of e.opts) if (!o.disabled) cases.push([`${e.key} ${o.key}`, e]);
  it.each(cases)('round-trips %s', (name, e) => {
    const optKey = name.slice(e.key.length + 1);
    const c = newCard(e, [], { opt:optKey, value:12, value2:34, within:7 });
    if (e.params.length && e.params[0].type === 'integer') c.params[e.params[0].key] = Number(e.params[0].default) + 1;   // a custom parameter
    const w = toWire(e, c);
    expect(w.id).toBe(c.id);
    const back = fromWire(w, byKey);
    expect(back.raw).toBeUndefined();
    const o = e.opts.find(x => x.key === optKey)!;
    const want = strip(c), got = strip(back);
    if (o.value !== 'input') { delete (want as any).value; delete (got as any).value }
    if (!o.between) { delete (want as any).value2; delete (got as any).value2 }
    if (!o.within) { delete (want as any).within; delete (got as any).within }
    expect(got).toEqual(want);
  });
  it('builds the forms of report 8.5', () => {
    const sma = byKey.get('I01')!;
    const above = toWire(sma, newCard(sma, [], { opt:'state_level|sma|gt', params:{ length:50, source:'close' } }));
    expect(above.test).toEqual({ kind:'state', lhs:{ kind:'price', field:'close' }, op:'gt', rhs:{ kind:'indicator', indicator:'I01', params:{ length:50 }, output:'sma' } });
    const dist = toWire(sma, newCard(sma, [], { opt:'value_pct_distance|sma|between', value:-3, value2:3 }));
    expect(dist.test).toEqual({ kind:'value', op:'between', value:-3, value2:3, metric:{ kind:'transform', fn:'pct_distance', of:{ kind:'indicator', indicator:'I01', output:'sma' } } });
    const golden = toWire(sma, newCard(sma, [], { opt:'event_instance|sma|crosses_above', params:{ length:50, source:'close' }, second:{ length:200, source:'close' }, within:20 }));
    expect(golden.test).toEqual({ kind:'event', within:20, signal:{ lhs:{ kind:'indicator', indicator:'I01', params:{ length:50 }, output:'sma' }, op:'crosses_above', rhs:{ kind:'indicator', indicator:'I01', params:{ length:200 }, output:'sma' } } });
    const st = byKey.get('I09')!;
    expect(toWire(st, newCard(st, [], { opt:'state_value|direction|gt' })).test).toEqual({ kind:'state', lhs:{ kind:'indicator', indicator:'I09', output:'direction' }, op:'gt', rhs:{ value:0 } });
  });
  it('maps every fixture preset onto cards without loss', () => {
    for (const p of cat.body.presets) for (const cd of p.definition.conditions) {
      const card = fromWire(cd, byKey);
      if (card.raw) continue;                                            // kept as it is: checked below
      expect(toWire(byKey.get(card.entry!)!, card).test).toEqual(normalize(cd));
    }
  });
  it('keeps a wire condition it cannot map as it is, and sends it unchanged', () => {
    const cd: ConditionDef = { id:'z', enabled:true, test:{ kind:'state', lhs:{ kind:'indicator', indicator:'I13', output:'rsi' }, op:'gt', rhs:{ kind:'transform', fn:'change', of:{ kind:'price', field:'close' }, args:{ bars:3 } } } };
    const card = fromWire(cd, byKey);
    expect(card.raw).toEqual(cd.test);
    expect(toWire(undefined, card)).toEqual(cd);
    expect(condText(undefined, card)).toMatch(/not editable/);
  });
  it('scales IDR values to Rp B on the card and back', () => {
    const adv = byKey.get('adv20_idr')!;
    const c = newCard(adv, [], { opt:'metric|value|gt', value:12.5 });
    expect((toWire(adv, c).test as any).value).toBe(12.5e9);
    expect(fromWire(toWire(adv, c), byKey).value).toBe(12.5);
  });
});

describe('refused in place (report 9.2)', () => {
  const rsi = byKey.get('I13')!;
  it('refuses between with value > value2 instead of reordering', () => {
    const c = newCard(rsi, [], { opt:'value|rsi|between', value:50, value2:30 });
    expect(cardErrors(rsi, c).value2).toMatch(/at least/);
    expect((toWire(rsi, newCard(rsi, [], { opt:'value|rsi|between', value:30, value2:30 })).test as any)).toMatchObject({ value:30, value2:30 });
  });
  it('refuses within outside 1..within_max', () => {
    const c = newCard(rsi, [], { opt:'event_value|rsi|crosses_above', within:131 });
    expect(cardErrors(rsi, c, 130).within).toMatch(/1 to 130/);
    expect(cardErrors(rsi, { ...c, within:2.5 }, 130).within).toBeDefined();
    expect(cardErrors(rsi, { ...c, within:130 }, 130).within).toBeUndefined();
  });
  it('never rounds a parameter: a fraction in an integer field and a value outside the range are refused', () => {
    const len = rsi.params.find(p => p.key === 'length')!;
    expect(paramError(len, 14.5)).toMatch(/whole/);
    expect(paramError(len, 0)).toMatch(/at least/);
    expect(paramError(len, 14)).toBeNull();
    const factor = byKey.get('I09')!.params.find(p => p.key === 'factor')!;
    expect(factor.exclusive_min).toBe(true);
    expect(paramError(factor, 0)).toMatch(/above 0/);
  });
});

/** the wire as toWire writes it: parameters only where they differ from the default (missing ones take the default) */
function normalize(cd: ConditionDef): unknown {
  const fix = (r: any): any => {
    if (!r || typeof r !== 'object') return r;
    if (r.kind === 'indicator') {
      const e = byKey.get(r.indicator)!, p = Object.fromEntries(Object.entries(r.params || {}).filter(([k, v]) => String(e.params.find(x => x.key === k)?.default) !== String(v)));
      return Object.keys(p).length ? { kind:'indicator', indicator:r.indicator, params:p, output:r.output } : { kind:'indicator', indicator:r.indicator, output:r.output };
    }
    const id = r.kind === 'pattern' ? r.type : r.kind === 'xsection' ? r.metric : null, e = id ? byKey.get(id) : undefined;
    if (e && r.params) {
      const p = Object.fromEntries(Object.entries(r.params).filter(([k, v]) => String(e.params.find(x => x.key === k)?.default) !== String(v)));
      const { params, ...rest } = r; void params;
      return Object.keys(p).length ? { ...rest, params:p } : rest;
    }
    return Object.fromEntries(Object.entries(r).map(([k, v]) => [k, fix(v)]));
  };
  return fix(cd.test);
}
