/* EXEC-SCREENER-V21 phase C: how a value reaches the user.
   - the format of a number comes from the catalog (entries.ts formatOfOpt / formatOfOutput / formatOfMetric), never
     from the wire's coarse Cell.unit, which is 'dimensionless' for a percent in production (ERRORS M355): percent with
     its sign, a multiple (×), shares, IDR per share, a rank, percentage points, and the units words of a header;
   - the states of a cell are kept apart: a value of 0, a missing value (null), n/a with its reason, not evaluated,
     loading, failed, and the price-break mark (texts.ts extraCellView, cellTitle);
   - the table sorts an extra column numerically with n/a and missing values last in both directions (results.ts
     sortRows on 'c:x:<id>', extra-columns.ts extraSortKey), as the condition columns already are (page.test.ts). */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import type { CatalogResponse, Cell, RunRequest, RunResponse, UniverseResponse } from '../../src/core/contract.ts';
import type { CallOpts, RunAnswer, ScreenerApi } from '../../src/api/types.ts';
import { compact, fmtValue, formatOfMetric, formatOfOutput, unitWords, valueText, type ValueFormat } from '../../src/format.ts';
import { entriesOf, formatOfOpt } from '../../src/entries.ts';
import { newCard } from '../../src/forms.ts';
import { ctx, freshUniverse, S, type Row } from '../../src/state.ts';
import { cancelRun, screenNow, sync } from '../../src/run.ts';
import { availableColumns, extraCell, extraReset, extraSortKey, setColumns } from '../../src/extra-columns.ts';
import { sortRows } from '../../src/results.ts';
import { cellTitle, extraCellView, naText } from '../../src/texts.ts';
import { fixtureApi } from '../fixture/api.ts';

const MINUS = '−';
describe('fmtValue: the catalog format of a number', () => {
  const cases: [number | null, ValueFormat, string][] = [
    [1.254, 'pct_signed', '+1.25%'], [-4.53, 'pct_signed', `${MINUS}4.53%`], [12.34, 'pct_signed', '+12.3%'], [123.4, 'pct_signed', '+123%'], [0, 'pct_signed', '0.00%'],
    [-0.004, 'pct_signed', `${MINUS}0.004%`],                  // a small negative never reads as 0
    [45.6, 'pct', '45.6%'], [1.1634, 'multiple', '1.16×'], [0.83, 'multiple', '0.83×'],
    [1_240_000, 'volume', '1.24M'], [-15_100_000, 'volume', `${MINUS}15.1M`], [980, 'volume', '980'],
    [7000, 'price', '7,000'], [8.5, 'price', '8.50'], [-125.4, 'price_change', `${MINUS}125`], [3.4e12, 'idr', 'Rp 3.40T'], [1.85e9, 'idr', 'Rp 1.9B'],
    [73.4, 'rank', '73'], [2.34, 'pts', '+2.3 pts'], [55.55, 'index', '55.6'], [-0.25, 'fraction', `${MINUS}0.25`], [14, 'count', '14'],
    [null, 'pct_signed', '—'], [Number.NaN, 'multiple', '—'],
  ];
  it.each(cases)('%s as %s is %s', (v, f, want) => { expect(fmtValue(v, f)).toBe(want) });
  it('the units a header names: %, ×, IDR per share, shares, IDR, percentile, percentage points', () => {
    expect((['pct_signed', 'multiple', 'price', 'price_change', 'volume', 'idr', 'rank', 'pts', 'index', 'raw'] as ValueFormat[]).map(unitWords))
      .toEqual(['%', '×', 'IDR per share', 'IDR per share', 'shares', 'IDR', 'percentile', 'percentage points', '', '']);
  });
  it('compact keeps a sign and three significant digits', () => {
    expect([compact(3.4e9), compact(-12_345), compact(12.5), compact(null)]).toEqual(['3.40B', `${MINUS}12.3K`, '12.50', '—']);
  });
});

describe('the format comes from the catalog, never from the wire unit (ERRORS M355)', () => {
  it("a 'dimensionless' output is a percent only when the catalog says so", () => {
    expect(formatOfOutput('dimensionless', 'percent_signed')).toBe('pct_signed');
    expect(formatOfOutput('dimensionless', 'percent_nonnegative')).toBe('pct');
    expect(formatOfOutput('dimensionless', 'index_0_100')).toBe('index');
    expect(formatOfOutput('dimensionless', 'ratio')).toBe('fraction');
    expect(formatOfOutput('dimensionless', null)).toBe('raw');
    expect(formatOfOutput('price', null)).toBe('price');
    expect(formatOfOutput('volume', null)).toBe('volume');
    expect(formatOfOutput('price_x_volume', null)).toBe('idr');
    // the test form of a transform decides first: distance from a moving average is a signed percent
    expect(formatOfOutput('price', null, 'value_pct_distance')).toBe('pct_signed');
    expect(formatOfOutput('price', null, 'value_band_position')).toBe('pct');
  });
  it("a metric's catalog unit: %, x, IDR, IDR per share, sessions, rank, pts", () => {
    expect(['%', 'x', 'IDR', 'IDR per share', 'shares', 'sessions', 'years', 'rank', 'pts', null].map(formatOfMetric))
      .toEqual(['pct_signed', 'multiple', 'idr', 'price', 'volume', 'count', 'count', 'rank', 'pts', 'raw']);
  });
  it("the old wire-unit path writes a 'dimensionless' percent without % (why the page must not use it)", () => {
    expect(valueText(-4.53, 'dimensionless')).toBe(`${MINUS}4.53`);
    expect(valueText(-4.53, '%', true)).toBe(`${MINUS}4.5%`);
  });
  it('on the fixture catalog: every offered extra column has a format that is not raw, and the percent ones read %', async () => {
    const c = await fixtureApi().catalog(null); if (c.status !== 200) throw new Error('fixture');
    ctx.catalog = c.body; ctx.entries = entriesOf(c.body); ctx.byKey = new Map(ctx.entries.map(e => [e.key, e]));
    const cols = availableColumns();
    expect(cols.length).toBeGreaterThan(8);
    for (const col of cols) expect(col.format, col.id).not.toBe('raw');
    const f = Object.fromEntries(cols.map(x => [x.id, x.format]));
    expect(f).toMatchObject({ ret_1m:'pct_signed', ret_1y:'pct_signed', hi52_pct:'pct_signed', lo52_pct:'pct_signed', rvol:'multiple', vol_20:'volume', natr:'pct' });
    // the cards' own value test on the same catalog: hi52 (a 'transform' metric, unit '%') formats as a signed percent
    const hi = ctx.byKey.get('hi52')!; expect(formatOfOpt(hi, hi.opts.find(o => o.kind === 'value'))).toBe('pct_signed');
  });
});

describe('cell states are kept apart (texts.ts extraCellView, cellTitle)', () => {
  const cell = (over: Partial<Cell>): Cell => ({ id:'x0', status:'pass', eval_date:'2026-10-23', reason:null, remark:null, value:0, unit:'dimensionless', ...over });
  const view = (s: Parameters<typeof extraCellView>[0], f: ValueFormat = 'pct_signed', remarks: any[] = []) => extraCellView(s, f, remarks, '2026-10-23');
  it('zero is a value, null is missing, n/a names its reason, not evaluated is a dot', () => {
    expect(view({ kind:'value', cell:cell({ value:0 }) })).toMatchObject({ text:'0.00%', muted:false });
    expect(view({ kind:'value', cell:cell({ value:null }) }).text).toBe('—');
    const na = view({ kind:'value', cell:cell({ status:'na', value:null, reason:'INSUFFICIENT_HISTORY' }) });
    expect(na.text).toBe('n/a'); expect(na.title).toContain(naText('INSUFFICIENT_HISTORY')); expect(na.title).not.toMatch(/INSUFFICIENT_HISTORY/);
    expect(view({ kind:'value', cell:cell({ status:'not_evaluated', value:null }) }).text).toBe('·');
    expect(view({ kind:'loading' }).text).toBe('…');
    expect(view({ kind:'error', message:'The service is busy.' })).toMatchObject({ text:'—', title:expect.stringContaining('The service is busy.') });
  });
  it('a value whose look-back crosses a price break keeps its value and carries the mark', () => {
    const v = view({ kind:'value', cell:cell({ value:12.5, remark:'PRICE_BREAK_IN_LOOKBACK' }) });
    expect(v).toMatchObject({ text:'+12.5%', mark:true, tone:'up' });
  });
  it('a stale stock names its own last trade beside the screen date', () => {
    expect(cellTitle(cell({ eval_date:'2026-10-20' }), [], '2026-10-23')).toMatch(/Evaluated 2026-10-20 \(the stock's last trade; the screen's date is 2026-10-23\)/);
  });
  it('the unit of the wire cell does not change the text: the column format does', () => {
    const a = view({ kind:'value', cell:cell({ value:-4.53, unit:'dimensionless' }) }), b = view({ kind:'value', cell:cell({ value:-4.53, unit:'%' }) });
    expect(a.text).toBe(`${MINUS}4.53%`); expect(b.text).toBe(a.text);
  });
});

describe('an extra column sorts numerically, n/a and missing last in both directions', () => {
  type Call = { req: Omit<RunRequest, 'client_order'>; opts: CallOpts; resolve: (a: RunAnswer) => void };
  const fx = fixtureApi();
  let catalog: CatalogResponse, universe: UniverseResponse, calls: Call[] = [];
  const flush = () => new Promise(ok => setTimeout(ok, 0));
  beforeAll(async () => {
    const c = await fx.catalog(null), u = await fx.universe(null);
    if (c.status !== 200 || u.status !== 200) throw new Error('fixture');
    catalog = c.body; universe = u.body;
  });
  beforeEach(() => {
    cancelRun(); calls = [];
    ctx.api = { ...fx, run:(req, opts = {}) => new Promise<RunAnswer>(resolve => { calls.push({ req, opts, resolve }) }) } as ScreenerApi;
    ctx.catalog = catalog; ctx.universe = universe; ctx.entries = entriesOf(catalog); ctx.byKey = new Map(ctx.entries.map(e => [e.key, e]));
    ctx.R = null; ctx.running = false; ctx.runError = null; ctx.refused = null; ctx.pending = false; ctx.stale = false;
    S.universe = freshUniverse(); S.cards = []; S.logic = 'all'; S.atLeast = 2; S.errors = {};
    extraReset(); setColumns([]);
  });
  afterEach(() => { vi.useRealTimers() });
  it('values 9, 10, −2, 0 and two n/a: asc −2, 0, 9, 10 then n/a; desc 10, 9, 0, −2 then n/a', async () => {
    setColumns(['ret_1m']);
    S.cards.push(newCard(ctx.byKey.get('I13')!, [], { value:100, opt:'value|rsi|lt' })); sync(); screenNow();
    const main = calls.find(c => c.opts.lane !== 'aux')!;
    const body = (await fx.run(main.req)).body;
    main.resolve({ body, bytes:new Uint8Array() }); await flush();
    const aux = calls.find(c => c.opts.lane === 'aux')!;
    const tks = ctx.R!.rows.slice(0, 6).map(r => r.ticker);
    const VALUES: Record<string, number | null> = { [tks[0]]:9, [tks[1]]:10, [tks[2]]:-2, [tks[3]]:null, [tks[4]]:0, [tks[5]]:null };
    const ab: RunResponse = (await fx.run(aux.req)).body;
    const colId = aux.req.definition.conditions[1].id;
    const rows = ab.rows.map(r => !(r.ticker in VALUES) ? r : { ...r, cells:r.cells.map(c => c.id !== colId ? c : VALUES[r.ticker] == null
      ? { ...c, status:'na' as const, value:null, reason:'INSUFFICIENT_HISTORY' as const } : { ...c, value:VALUES[r.ticker] }) });
    aux.resolve({ body:{ ...ab, rows }, bytes:new Uint8Array() }); await flush();
    expect(extraCell(tks[3], 'ret_1m')).toMatchObject({ kind:'value', cell:{ status:'na' } });
    expect(extraSortKey(tks[4], 'ret_1m')).toBe(0);                      // zero is a value, not missing
    const six = ctx.R!.rows.filter(r => r.ticker in VALUES).map(r => ({ ...r, status:'match' as const })) as Row[];
    const order = (dir: 'asc' | 'desc') => sortRows(six, { key:'c:x:ret_1m', dir }).map(r => VALUES[r.ticker]);
    expect(order('asc')).toEqual([-2, 0, 9, 10, null, null]);
    expect(order('desc')).toEqual([10, 9, 0, -2, null, null]);
  });
});
