/* EXEC-SCREENER-V21 extra columns: the auxiliary definition (src/extra-columns.ts nextAuxDefinition) run through the
   REAL screener core (src/core/validate.ts validateDefinition, src/core/screen.ts runScreen over tests/core/helpers.ts
   memoryEnv, the worker's role in memory). Proves that the worker returns, for every ticker of the table and nothing
   else, one cell per column with status, value, unit, eval_date, the NA reason and the price-break remark, and that the
   value equals the one a condition on the same metric gets in a main run. */
import { beforeAll, describe, expect, it } from 'vitest';
import type { CatalogResponse, Definition, UniverseRow } from '../../src/core/contract.ts';
import { UNIVERSE_DEFAULTS } from '../../src/core/contract.ts';
import { runScreen } from '../../src/core/screen.ts';
import { validateDefinition } from '../../src/core/validate.ts';
import { entriesOf } from '../../src/entries.ts';
import { canonical, ctx, rowOfUniverse } from '../../src/state.ts';
import { availableColumns, nextAuxDefinition, setColumns } from '../../src/extra-columns.ts';
import { fixtureApi } from '../fixture/api.ts';
import { headBars, memoryEnv, rowOf, synth, tailBars, vctx } from '../core/helpers.ts';

const IX = (() => { const t = synth('IHSG', 3, 520, '2024-06-03'); return { ...t, bars: { ...t.bars, V: t.bars.V.map(() => null) } } })();
const E = IX.dates[IX.dates.length - 1];
const base = Array.from({ length: 30 }, (_, k) => synth(`S${String(k).padStart(2, '0')}`, 700 + k, 520, '2024-06-03'));
const STALE = headBars(synth('STAL', 900, 520, '2024-06-03'), 505);
const SHORT = tailBars(synth('RANS', 901, 520, '2024-06-03'), 74);          // 74 bars: a 252-session return is NA
const BROKE = synth('PBSA', 902, 520, '2024-06-03');
const EX = BROKE.dates[BROKE.dates.length - 9];                               // ex-date 9 bars ago: inside a 21-bar lookback
const TICKERS = [...base, STALE, SHORT, BROKE];
const rows: UniverseRow[] = TICKERS.map(t => rowOf(t, E, { adv20_idr: 5e9, last: 1000 },
  t === BROKE ? [{ code: 'PRICE_BREAK', action: 'STOCK_SPLIT', ex_date: EX, ratio_old: 1, ratio_new: 2, close_ratio: 0.5 }] : []));
const CTX = vctx(TICKERS.map(t => t.ticker));
// the table's universe: stale and price-break tickers listed (their remarks shown)
const U = { ...UNIVERSE_DEFAULTS, price_min: null, adv20_min_idr: null, traded_on_eval_date: false, exclude_price_breaks: false } as Definition['universe'];
// the table: a screen whose rows are a subset of the universe (8 tickers, the short, stale and broken ones included)
const TABLE = ['S03', 'S07', 'S11', 'S19', 'S28', 'STAL', 'RANS', 'PBSA'];

let catalog: CatalogResponse;
beforeAll(async () => {
  const fx = fixtureApi();
  const c = await fx.catalog(null); if (c.status !== 200) throw new Error('fixture catalog');
  catalog = c.body;
  ctx.catalog = catalog; ctx.entries = entriesOf(catalog); ctx.byKey = new Map(ctx.entries.map(e => [e.key, e]));
  const tableDef: Definition = { universe: U, conditions: [{ id: 'a', enabled: true, test: { kind: 'value', op: 'gt', value: 0, metric: { kind: 'universe', attr: 'bars' } } }], logic: 'all' };
  ctx.R = { rows: rows.filter(r => TABLE.includes(r.ticker)).map(rowOfUniverse), run: null, defHash: canonical(tableDef), def: tableDef, eligible: TABLE.length, listed: rows.length, staleHidden: 0, breakHidden: 0 };
  ctx.running = false;
  ctx.api = { run: () => new Promise(() => {}) } as any;          // the auxiliary request setColumns sends stays in flight
  setColumns(['ret_1m', 'ret_1y', 'rvol', 'hi52_pct', 'natr']);
});

describe('the auxiliary definition through the real core (extra-columns.ts, core screen.ts)', () => {
  it('offers the audited candidates from the catalog, without YTD or a page-derived 52-week price, each with its catalog format', () => {
    const cols = availableColumns(), by = new Map(cols.map(c => [c.id, c]));
    // REMOVE verdicts of the data audit (product decision 4; page arithmetic): never offered, not even greyed
    for (const id of ['ret_ytd', 'hi52_px', 'lo52_px']) expect(by.has(id), id).toBe(false);
    // the 1M return reads its session count from catalog.periods and says sessions in its label (ROC is close to close
    // over the stock's own sessions); a percent column is written as a signed percent, never from Cell.unit
    expect(by.get('ret_1m')).toMatchObject({ unavailable: null, params: { length: 21 }, format: 'pct_signed', label: 'Return, 21 sessions (1M)' });
    expect(by.get('rvol')?.format).toBe('multiple');
    expect(by.get('vol_20')?.format).toBe('volume');
    expect(cols.some(c => c.id === 'ind_I13' && c.unavailable === null && c.format === 'index')).toBe(true);
    // a value without a plain unit is BLOCKED (Ease of Movement, Market Facilitation Index): not offered
    expect(cols.some(c => c.format === 'raw')).toBe(false);
  });
  it('is valid, and returns exactly the table tickers, one cell per column each, NA with its reason, the price-break remark kept', () => {
    const aux = nextAuxDefinition()!;
    expect(aux.logic).toBe('any');
    expect(aux.conditions[0]).toMatchObject({ id: 'xa', test: { kind: 'value', metric: { kind: 'universe', attr: 'bars' }, op: 'gt', value: 0 } });
    expect([...aux.universe.tickers!]).toEqual([...TABLE].sort());
    const norm = validateDefinition(aux, CTX);                       // the worker's own validation: no refusal
    const env = memoryEnv(TICKERS, IX, rows, E);
    const r = runScreen(norm, env);
    expect(r.rows.map(x => x.ticker).sort()).toEqual([...TABLE].sort());      // every table ticker, nothing else
    expect(r.rows.every(x => x.status === 'match')).toBe(true);
    const ids = aux.conditions.slice(1).map(c => c.id);
    for (const row of r.rows) {
      for (const id of ids) {
        const c = row.cells.find(x => x.id === id)!;
        expect(c, `${row.ticker} ${id}`).toBeTruthy();
        expect(['pass', 'fail', 'na']).toContain(c.status);          // never not_evaluated: nothing is pruned (need 1)
        expect(c.eval_date).toBeTruthy();
        if (c.status === 'na') { expect(c.reason).toBeTruthy(); expect(c.value ?? null).toBeNull() }
        else { expect(c.reason).toBeNull(); expect(typeof c.value).toBe('number') }
      }
    }
    // the 252-session return of a 74-bar ticker is NA with its reason (the reference's "logic any, value > -1e15"
    // would have dropped this row and lost the reason)
    const idOf = (metricLen: number) => aux.conditions.find(c => (c.test as any).metric?.indicator === 'I17' && (c.test as any).metric?.params?.length === metricLen)!.id;
    const rans = r.rows.find(x => x.ticker === 'RANS')!.cells.find(x => x.id === idOf(252))!;
    expect(rans).toMatchObject({ status: 'na', reason: 'INSUFFICIENT_HISTORY' });
    // the price-break row keeps its row remark, and the 21-session return crossing the ex-date its cell remark
    const pb = r.rows.find(x => x.ticker === 'PBSA')!;
    expect(pb.remarks.map(x => x.code)).toContain('PRICE_BREAK');
    expect(pb.cells.find(x => x.id === idOf(21))!.remark).toBe('PRICE_BREAK_IN_LOOKBACK');
    // the stale ticker is evaluated at its own last bar, with its remark
    const st = r.rows.find(x => x.ticker === 'STAL')!;
    expect(st.remarks.map(x => x.code)).toContain('STALE');
    expect(st.cells.find(x => x.id === idOf(21))!.eval_date).toBe(STALE.dates[STALE.dates.length - 1]);
    // resolved parameters are in the answer's summaries
    expect(r.conditions.find(x => x.id === idOf(21))!.params_resolved).toMatchObject({ length: 21 });
  });
  it('gives the same value as a condition on the same metric in a main run', () => {
    const aux = nextAuxDefinition()!, env = memoryEnv(TICKERS, IX, rows, E);
    const r = runScreen(validateDefinition(aux, CTX), env);
    for (const col of aux.conditions.slice(1)) {
      const main = runScreen(validateDefinition({ universe: U, logic: 'all', conditions: [{ id: 'm', enabled: true, test: { ...(col.test as any), op: 'gt', value: -1e15 } }] }, CTX), memoryEnv(TICKERS, IX, rows, E), { exhaustive: true });
      for (const row of r.rows) {
        const a = row.cells.find(x => x.id === col.id)!, m = main.rows.find(x => x.ticker === row.ticker)?.cells[0];
        if (a.status === 'na') expect(m, `${row.ticker} ${col.id}: a NA value is not a row of a "> -1e15" run`).toBeUndefined();
        else expect(m!.value).toBe(a.value);
      }
    }
  });
});
