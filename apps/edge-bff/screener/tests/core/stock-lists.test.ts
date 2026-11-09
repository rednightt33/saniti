/* EXEC-SCREENER-STOCK-LISTS (user 2026-11-09, options 1A, 2, 3): the index and group (KONGLO) universe filters in the
   core. applyUniverse: _in keeps a member of at least one chosen list of its kind, _out drops a member of any chosen
   list, Index and Group combine with AND and with sector and industry; a stock in no list is not unclassified. The
   normalized definition and its hash are those of before when the new keys are absent or empty (hashes pinned from
   commit 1a28d2ca, before the filters existed). validateUniverse refuses an unknown code, a code of the other kind, one
   listed twice and one both included and excluded, and a list filter while the stock-lists file is not available, each
   naming the field, how to pass and a right and a wrong example (AGENTS.md "Gates and evidence"). */
import { describe, expect, it } from 'vitest';
import { UNIVERSE_DEFAULTS } from '../../src/core/contract.ts';
import type { StockListsBlock, UniverseDef, UniverseRow } from '../../src/core/contract.ts';
import { applyUniverse } from '../../src/core/universe.ts';
import { ScreenerError } from '../../src/core/errors.ts';
import { STOCK_LISTS_MISSING, definitionHash, validateDefinition, validateUniverse } from '../../src/core/validate.ts';
import { vctx } from './helpers.ts';

const row = (ticker: string, o: Partial<UniverseRow> = {}): UniverseRow => ({
  ticker, name: `${ticker} Tbk`, sector: 'Financials', industry: 'Banks', last: 1000, chg_1d_pct: 0.5, adv20_idr: 5e9,
  first_bar: '2018-01-02', last_bar: '2026-10-27', bars: 2100, stale: false, remarks: [], indices: [], groups: [], ...o,
});
/* BBCA: LQ45 + DJARUM; BBRI: LQ45 + IDX30; ICBP: LQ45 + SALIM; INDF: SALIM only; XCID: unclassified, in no list;
   ADHI: stale, LQ45; BUMI: IDX30 + BAKRIE; an older worker's row without the membership fields */
const ROWS: UniverseRow[] = [
  row('BBCA', { indices: ['LQ45'], groups: ['DJARUM'] }),
  row('BBRI', { indices: ['LQ45', 'IDX30'] }),
  row('ICBP', { sector: 'Consumer', industry: 'Food', indices: ['LQ45'], groups: ['SALIM'] }),
  row('INDF', { sector: 'Consumer', industry: 'Food', groups: ['SALIM'] }),
  row('XCID', { sector: null, industry: null }),
  row('ADHI', { indices: ['LQ45'], stale: true, last_bar: '2026-08-21', remarks: [{ code: 'STALE', last_bar_date: '2026-08-21' }] }),
  row('BUMI', { sector: 'Energy', industry: 'Coal', indices: ['IDX30'], groups: ['BAKRIE'] }),
  (({ indices: _i, groups: _g, ...r }) => r)(row('OLD')),
];
const def = (o: Partial<UniverseDef> = {}): UniverseDef => ({ ...UNIVERSE_DEFAULTS, ...o } as UniverseDef);
const tickers = (u: Partial<UniverseDef>) => applyUniverse(ROWS, def(u)).eligible.map(r => r.ticker);

describe('applyUniverse: index and group filters', () => {
  it('within a kind several choices mean any of them; an exclusion drops a member of any chosen list', () => {
    expect(tickers({ indices_in: ['LQ45'] })).toEqual(['BBCA', 'BBRI', 'ICBP']);
    expect(tickers({ indices_in: ['LQ45', 'IDX30'] })).toEqual(['BBCA', 'BBRI', 'ICBP', 'BUMI']);
    expect(tickers({ groups_in: ['SALIM', 'DJARUM'] })).toEqual(['BBCA', 'ICBP', 'INDF']);
    expect(tickers({ indices_out: ['LQ45'] })).toEqual(['INDF', 'XCID', 'BUMI', 'OLD']);
    expect(tickers({ groups_out: ['SALIM', 'BAKRIE'] })).toEqual(['BBCA', 'BBRI', 'XCID', 'OLD']);
    expect(tickers({ indices_in: ['LQ45'], indices_out: ['IDX30'] })).toEqual(['BBCA', 'ICBP']);
  });
  it('across kinds both must hold, and with sector and industry as before', () => {
    expect(tickers({ indices_in: ['LQ45'], groups_in: ['SALIM'] })).toEqual(['ICBP']);
    expect(tickers({ indices_in: ['LQ45', 'IDX30'], groups_in: ['SALIM', 'BAKRIE'] })).toEqual(['ICBP', 'BUMI']);
    expect(tickers({ indices_in: ['LQ45'], groups_out: ['DJARUM'] })).toEqual(['BBRI', 'ICBP']);
    expect(tickers({ groups_in: ['SALIM'], sectors_in: ['Consumer'], industries_out: ['Food'] })).toEqual([]);
    expect(tickers({ indices_in: ['IDX30'], sectors_out: ['Energy'] })).toEqual(['BBRI']);
  });
  it('a stock in no list is not unclassified: include_unclassified keeps it out of an index filter and the sector rule is untouched', () => {
    expect(tickers({ indices_in: ['LQ45'], include_unclassified: true })).toEqual(['BBCA', 'BBRI', 'ICBP']);
    expect(tickers({ sectors_in: ['Financials'], include_unclassified: true })).toEqual(['BBCA', 'BBRI', 'XCID', 'OLD']);
    expect(tickers({ sectors_out: ['Financials'], groups_out: ['SALIM'] })).toEqual(['XCID', 'BUMI']);
  });
  it('empty lists are no filter; the P4 chips still apply first and count apart (ADHI, stale, is hidden, not filtered out)', () => {
    expect(tickers({ indices_in: [], groups_out: [] })).toEqual(['BBCA', 'BBRI', 'ICBP', 'INDF', 'XCID', 'BUMI', 'OLD']);
    const r = applyUniverse(ROWS, def({ indices_in: ['LQ45'] }));
    expect(r.counts).toEqual({ listed: 8, eligible: 3, stale_hidden: 1, price_break_hidden: 0, filtered_out: 4 });
    expect(tickers({ indices_in: ['LQ45'], traded_on_eval_date: false })).toEqual(['BBCA', 'BBRI', 'ICBP', 'ADHI']);
  });
  it('a row without membership fields (an older worker) is in no list', () => {
    expect(tickers({ groups_in: ['SALIM'] })).not.toContain('OLD');
    expect(tickers({ groups_out: ['SALIM'] })).toContain('OLD');
  });
});

/* ---- validation ---------------------------------------------------------------------------------------------- */
const LISTS: StockListsBlock = { availability: 'AVAILABLE', reason: null, as_of: '2026-11-09T13:31:48Z', lists: [
  { key: 'INDEX:467', kind: 'INDEX', code: 'IHSG', name: 'IHSG', definition: 'x', tickers: 4, as_of: null },
  { key: 'INDEX:550', kind: 'INDEX', code: 'LQ45', name: 'LQ45', definition: 'x', tickers: 3, as_of: null },
  { key: 'INDEX:555', kind: 'INDEX', code: 'IDX30', name: 'IDX30', definition: 'x', tickers: 2, as_of: null },
  { key: 'KONGLO:9', kind: 'KONGLO', code: 'SALIM', name: 'Salim', definition: 'x', tickers: 2, as_of: null },
  { key: 'KONGLO:59', kind: 'KONGLO', code: 'DJARUM', name: 'Djarum', definition: 'x', tickers: 1, as_of: null },
] };
const BASE = vctx(['BBCA', 'BBRI', 'TLKM', 'ASII']);
const CTX = { ...BASE, stockLists: LISTS };
const U = { ...UNIVERSE_DEFAULTS } as any;
function refusal(fn: () => unknown): ScreenerError {
  try { fn() } catch (e) { if (e instanceof ScreenerError) return e; throw e }
  throw new Error('expected a ScreenerError');
}
const RSI = { id: 'a', enabled: true, test: { kind: 'value', op: 'lt', value: 30, metric: { kind: 'indicator', indicator: 'I13', output: 'rsi' } } };

describe('validateUniverse: index and group filters', () => {
  it('a definition without the new keys normalizes and hashes as before the filters existed (pinned at commit 1a28d2ca), with or without the lists', async () => {
    const before: [unknown, string][] = [
      [{ universe: { security_types: ['stock'] }, conditions: [], logic: 'all' }, '821bd576b9c379bcf295c8d08997600a73cf2cc4ef7c8936af188d6d4fbdd438'],
      [{ universe: { security_types: ['stock'], sectors_in: ['Financials', 'Energy'], industries_out: ['Coal'], price_min: 50, adv20_min_idr: 1e9, tickers: ['BBCA', 'TLKM'] }, conditions: [RSI], logic: 'all' },
        '9286be56f17e50c5b19d985be16a2efff49f988fed6c28afbaca5968f4d4732c'],
      [{ universe: { security_types: ['stock'], include_unclassified: true, traded_on_eval_date: false, metric_filters: [{ kind: 'value', metric: { kind: 'universe', attr: 'last' }, op: 'gt', value: 100 }] }, conditions: [RSI], logic: 'any' },
        '72ee993a070fefed8ab029e17b25e1b87bf2ee9225f8c1900618cd811d0b6934'],
    ];
    for (const [d, hash] of before) {
      expect(await definitionHash(validateDefinition(d, BASE))).toBe(hash);
      expect(await definitionHash(validateDefinition(d, CTX))).toBe(hash);
      // empty lists are left out, as the sector lists are: the same hash, no new key in the normalized form
      const empty = { ...(d as any), universe: { ...(d as any).universe, indices_in: [], indices_out: [], groups_in: [], groups_out: [] } };
      const n = validateDefinition(empty, BASE);
      expect(Object.keys(n.universe).filter(k => /^(indices|groups)_/.test(k))).toEqual([]);
      expect(await definitionHash(n)).toBe(hash);
    }
  });
  it('keeps the codes as given and hashes each choice apart', async () => {
    const u = validateUniverse({ ...U, indices_in: ['LQ45', 'IDX30'], groups_out: ['DJARUM'] }, 'u', CTX);
    expect([u.indices_in, u.groups_out, u.indices_out, u.groups_in]).toEqual([['LQ45', 'IDX30'], ['DJARUM'], undefined, undefined]);
    const h = async (x: Record<string, unknown>) => definitionHash(validateDefinition({ universe: { ...U, ...x }, conditions: [], logic: 'all' }, CTX));
    const all = await Promise.all([h({}), h({ indices_in: ['LQ45'] }), h({ indices_out: ['LQ45'] }), h({ groups_in: ['SALIM'] }), h({ groups_out: ['SALIM'] })]);
    expect(new Set(all).size).toBe(5);
  });
  it('refuses an unknown code, a code of the other kind and a wrong spelling, with the field, the allowed codes and a right and a wrong example', () => {
    const e = refusal(() => validateUniverse({ ...U, indices_in: ['LQ45', 'LQ46'] }, 'definition.universe', CTX));
    expect([e.code, e.field, (e.details as any).allowed]).toEqual(['INVALID_CONDITION', 'definition.universe.indices_in[1]', ['IHSG', 'LQ45', 'IDX30']]);
    expect(e.message).toBe('definition.universe.indices_in[1]: "LQ46" is not the code of an index the Screener holds. Pick it from the Index list, which shows each by its code: "LQ45" is accepted, "LQ46" is refused.');
    const g = refusal(() => validateUniverse({ ...U, groups_in: ['LQ45'] }, 'u', CTX));
    expect([g.field, (g.details as any).allowed, g.message]).toEqual(['u.groups_in[0]', ['SALIM', 'DJARUM'], 'u.groups_in[0]: "LQ45" is not the code of a group the Screener holds. Pick it from the Group list, which shows each by its code: "SALIM" is accepted, "LQ45" is refused.']);
    const s = refusal(() => validateUniverse({ ...U, groups_out: ['salim'] }, 'u', CTX));
    expect(s.message).toBe('u.groups_out[0]: "salim" is not the code of a group the Screener holds. Write it as the Group list shows it: "SALIM" is accepted, "salim" is refused.');
    expect(refusal(() => validateUniverse({ ...U, indices_in: 'LQ45' }, 'u', CTX)).code).toBe('INVALID_INPUT');
    expect(refusal(() => validateUniverse({ ...U, indices_in: [45] }, 'u', CTX)).field).toBe('u.indices_in[0]');
  });
  it('refuses a code listed twice, and one both included and excluded (it leaves no stock)', () => {
    const t = refusal(() => validateUniverse({ ...U, groups_in: ['SALIM', 'SALIM'] }, 'u', CTX));
    expect([t.code, t.field, t.message]).toEqual(['INVALID_CONDITION', 'u.groups_in[1]', 'u.groups_in[1]: "SALIM" is listed twice; list it once ("SALIM" once is accepted, "SALIM" twice is refused).']);
    const b = refusal(() => validateUniverse({ ...U, indices_in: ['IHSG', 'LQ45'], indices_out: ['LQ45'] }, 'u', CTX));
    expect([b.code, b.field]).toEqual(['INVALID_CONDITION', 'u.indices_out[0]']);
    expect(b.message).toBe('u.indices_out[0]: "LQ45" is both included and excluded, which leaves no stock; keep it on one side (include "LQ45" and exclude "IHSG" is accepted; include and exclude "LQ45" is refused). Each index is either included or excluded.');
    // the same code as an index and as a group are two kinds: no conflict between them
    expect(validateUniverse({ ...U, indices_in: ['LQ45'], groups_out: ['SALIM'] }, 'u', CTX)).toMatchObject({ indices_in: ['LQ45'], groups_out: ['SALIM'] });
  });
  it('refuses a list filter while the stock-lists file is not available (METRIC_UNAVAILABLE naming why and how to pass); an empty one passes', () => {
    const missing = { ...BASE, stockLists: { availability: 'REQUIRES_DATA', reason: 'This publication carries no index and group lists.', as_of: null, lists: [] } as StockListsBlock };
    const e = refusal(() => validateUniverse({ ...U, groups_in: ['SALIM'] }, 'definition.universe', missing));
    expect([e.code, e.field, e.details]).toEqual(['METRIC_UNAVAILABLE', 'definition.universe.groups_in', { metric: 'stock_lists', availability: 'REQUIRES_DATA', reason: 'This publication carries no index and group lists.' }]);
    expect(e.message).toBe('definition.universe.groups_in: a group filter needs the index and group lists, which are not available: This publication carries no index and group lists. Remove the Group filter to run the screen (the same screen without it runs; with Group "SALIM" it waits for the lists).');
    // no block at all (a context without lists): the generic reason
    const n = refusal(() => validateUniverse({ ...U, indices_out: ['LQ45'] }, 'u', BASE));
    expect([n.code, (n.details as any).reason]).toEqual(['METRIC_UNAVAILABLE', STOCK_LISTS_MISSING]);
    expect(validateUniverse({ ...U, indices_in: [], groups_in: [] }, 'u', missing)).not.toHaveProperty('indices_in');
  });
});
