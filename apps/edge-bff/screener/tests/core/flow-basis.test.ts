/* EXEC-PRICE-DISTORTION D-1 and D-5 (the user 2026-11-24: "untuk mereka yang tertangkap, maka akan tetap di show
   seluruhnya, tapi dengan badge, berikut juga untuk cell flownya?", yes; go "Untuk 2-5 bisa go"):
   - the generator's basis probe (build-screener-registry.mjs basisReads) on the real entries, as the generated registry
     holds them, and a self-test that it catches a dependence planted in a made-up entry (and finds none where none is);
   - a Flow cell is marked only when its output reads what an action or a price break distorts, over the sessions it
     reads: FLOW_BASIS_IN_LOOKBACK across an action whose broker lots are not on one basis, PRICE_BREAK_IN_LOOKBACK across a
     price break when it reads the close or the volume; the value, pass and fail never change; remark_dates names them;
   - universe.ts flowBasisDates: which actions count (every status but `same`, none included: R2);
   - D-1: a run's row keeps a PRICE_BREAK badge only when a cell crossed its date or the date is the row's last bar. */
import { describe, expect, it } from 'vitest';
import * as G from '../../scripts/build-screener-registry.mjs';
import type { Cell, Definition, PriceBreakRemark, RowRemark, Test } from '../../src/core/contract.ts';
import { bindCondition } from '../../src/core/condition.ts';
import { evaluationBar } from '../../src/core/evaluate.ts';
import { FLOW_BY_ID, FLOWS } from '../../src/core/flowmetrics.ts';
import { FLOW_READS } from '../../src/core/registry.ts';
import { previewCells, runScreen, shownRemarks } from '../../src/core/screen.ts';
import { flowBasisDates } from '../../src/core/universe.ts';
import type { ActionRow } from '../../src/core/universe.ts';
import { cellRemarkText } from '../../src/texts.ts';
import { OPTS, WITHIN_MAX, memoryEnv, rowOf, synth } from './helpers.ts';
import { E, FIRST, FLOW_CTX, LAST, PRICE_BARS, STOCKS, WINDOW } from './flow-fixture.ts';

const out = (id: string, key: string) => FLOW_BY_ID[id].outputs.find(o => o.key === key)!;

/* ---- the basis probe ------------------------------------------------------------------------------------------------ */

describe('the basis probe of the flow outputs (derived, never listed)', () => {
  it('gives every computed output its reads, and an entry never computed none', () => {
    for (const f of FLOWS) for (const o of f.outputs) {
      if (f.compute === 'none') { expect([f.id, o.reads, o.reads_from, o.reads_probe]).toEqual([f.id, undefined, undefined, undefined]); continue }
      expect([f.id, o.key, o.reads!.every(x => FLOW_READS.includes(x)), ['depth', 'window_start'].includes(o.reads_from!), ['measured', 'cannot_tell'].includes(o.reads_probe!)])
        .toEqual([f.id, o.key, true, true, true]);
    }
  });
  it('on the real entries: a rupiah or transaction output reads none of them, a VWAP reads the lots, a VWAP distance the lots and the close, the average daily value the close and the volume', () => {
    expect(out('FL25', 'value')).toMatchObject({ reads: [], reads_probe: 'measured' });        // Top Brokers · Rupiah
    expect(out('FL02', 'buy')).toMatchObject({ reads: [], reads_probe: 'measured' });          // Transaction Size · Value
    expect(out('FL04', 'buy')).toMatchObject({ reads: [], reads_probe: 'measured' });          // Share · Transactions
    expect(out('fnet', 'value')).toMatchObject({ reads: [], reads_probe: 'measured' });        // the foreign net in rupiah
    expect(out('FL17', 'value')).toMatchObject({ reads: ['lots'], reads_from: 'depth' });      // Buy VWAP · Rolling
    expect(out('FL01', 'buy')).toMatchObject({ reads: ['lots'] });                              // Transaction Size · Lot (one candle)
    expect(out('FL03', 'buy').reads).toEqual(['lots']);                                         // Share · Volume: one candle is basis-free, a window is not
    expect(out('FL39', 'value')).toMatchObject({ reads: ['lots', 'close'], reads_from: 'depth' });   // Buy VWAP · Rolling · Distance %
    expect(out('FL28', 'value')).toMatchObject({ reads: ['close', 'volume'] });                 // Average Daily Value: close x volume
    // a flag that never fires on the probe cannot be told: read as everything, from the window's start
    expect(out('FL27', 'value')).toMatchObject({ reads: ['lots', 'close', 'volume'], reads_from: 'window_start', reads_probe: 'cannot_tell' });
  });

  /* A made-up entry computed by a planted function: each output reads one thing, so the probe must find exactly it. */
  const roll = (x: number[], W: number) => x.map((_, t) => t < W - 1 ? null : x.slice(t - W + 1, t + 1).reduce((a, b) => a + b, 0));
  const planted = (_e: unknown, c: any, p: any) => {
    const R = c.rows, N = R.N, W = p.window as number, per = (col: string) => { const s = new Array(N).fill(0); for (let k = 0; k < R.n; k++) s[R.t[k]] += R[col][k]; return s };
    const BL = per('bl'), BV = per('bv'), SL = per('sl'), SV = per('sv'), close = c.close as number[], vol = c.volume as number[];
    const rbl = roll(BL, W), rbv = roll(BV, W);
    let acc = 0;
    return {
      lots: rbl, rupiah: rbv, close: close.map((x, t) => t < W - 1 ? null : x), volume: roll(vol, W),
      vwap_vs_close: rbv.map((v, t) => v === null ? null : v / rbl[t]! / 100 / close[t]),
      lagged: BL.map((_, t) => t < 2 ? null : BL[t - 2]),
      cum: BL.map(x => (acc += x)), flag: BL.map(() => 0),
      ...(p.side === 'sell' ? { sell: roll(p.unit === 'lot' ? SL : SV, W) } : {}),
    };
  };
  const ENTRY = { id: 'XP', compute: 'terminal', requires: null,
    outputs: ['lots', 'rupiah', 'close', 'volume', 'vwap_vs_close', 'lagged', 'cum', 'flag', 'sell'].map(key => ({ key, kind: 'K' })),
    params: [{ key: 'window', label: 'Window', kind: 'int', default: 1, min: 1, max: 20, condition: true },
      { key: 'side', label: 'Side', kind: 'select', options: [['buy', 'Buy'], ['sell', 'Sell']], default: 'buy', condition: true },
      { key: 'unit', label: 'Unit', kind: 'select', options: [['value', 'Value'], ['lot', 'Lot']], default: 'value', condition: true }] };
  it('self-test: finds the planted dependences and none where none is planted', () => {
    const r = G.basisReads(ENTRY, planted);
    expect(Object.fromEntries(Object.entries(r).map(([k, v]: [string, any]) => [k, [v.reads, v.reads_from, v.reads_probe]]))).toEqual({
      lots: [['lots'], 'depth', 'measured'], rupiah: [[], 'depth', 'measured'], close: [['close'], 'depth', 'measured'], volume: [['volume'], 'depth', 'measured'],
      vwap_vs_close: [['lots', 'close'], 'depth', 'measured'], lagged: [['lots'], 'depth', 'measured'],
      cum: [['lots'], 'window_start', 'measured'],                       // a running sum from the first candle reads past any depth
      flag: [['lots', 'close', 'volume'], 'window_start', 'cannot_tell'],  // never moves: cannot tell, so everything
      // the sell line exists only with side sell and reads lots only with unit lot: found through the side's anchor
      sell: [['lots'], 'depth', 'measured'],
    });
  });
  it('self-test: the contexts hold the defaults, each option, the anchor of an output the defaults do not give, and each again with the session parameters raised', () => {
    const cs = G.basisContexts(ENTRY, planted);
    expect(cs[0]).toEqual({ window: 1, side: 'buy', unit: 'value' });
    for (const want of [{ window: 5, side: 'buy', unit: 'value' }, { window: 1, side: 'sell', unit: 'value' }, { window: 1, side: 'sell', unit: 'lot' }, { window: 5, side: 'sell', unit: 'lot' }])
      expect(cs).toContainEqual(want);
    expect(G.basisReads({ ...ENTRY, compute: 'none' }, planted)).toBeNull();
  });
});

/* ---- the Flow cells (D-5) ----------------------------------------------------------------------------------------- */

const INDEX = synth('IHSG', 2, PRICE_BARS, '2026-07-01');
const A = STOCKS.AAAA.t;                                         // broker data on every date of the window
const brk = (d: string): PriceBreakRemark => ({ code: 'PRICE_BREAK', kind: 'unadjusted', action: 'STOCK_SPLIT', ex_date: d, ratio_old: 1, ratio_new: 2, close_ratio: 0.5 });
const flow = (metric: string, params?: Record<string, unknown>, output?: string) => ({ kind: 'flow', metric, ...(output ? { output } : {}), ...(params ? { params } : {}) }) as never;
const value = (metric: unknown): Test => ({ kind: 'value', metric, op: 'gt', value: -1e18 } as Test);
/** One condition on AAAA, evaluated at its last candle with broker data (LAST), with the row's remarks and the actions
    of the broker window whose lots are not on one basis. */
function cellOn(test: Test, remarks: RowRemark[] = [], flowBasis: string[] = []): Cell {
  const b = bindCondition({ id: 'a', enabled: true, test }, 'c', { ...OPTS, withinMax: WITHIN_MAX, flow: FLOW_CTX });
  const env = memoryEnv([A], INDEX, [rowOf(A, E)], E, { flow: FLOW_CTX });
  return b.evaluate({ ticker: 'AAAA', dates: A.dates, bars: A.bars as never, at: evaluationBar(A.dates, E), row: rowOf(A, E, {}, remarks), ihsgCalendar: INDEX.dates,
    series: r => env.series(r, A), xsection: () => null, ...(flowBasis.length ? { flowBasis } : {}) }).cell;
}
const IN = WINDOW[55], ALSO = WINDOW[57], OLD = WINDOW[5];      // inside a 20-session window ending at LAST; well before it
const plain = (c: Cell) => ({ status: c.status, value: c.value, eval_date: c.eval_date });

describe('Flow cells (D-5): marked when the output reads what is distorted, over the sessions it reads', () => {
  it('a rupiah-only Flow output is not marked, across an action whose lots are not on one basis nor across a price break', () => {
    const c = cellOn(value(flow('FL25')), [brk(IN)], [IN]);
    expect([c.remark, c.remark_dates]).toEqual([null, undefined]);
    expect(c.eval_date).toBe(LAST);
  });
  it('a lots output across such an action is FLOW_BASIS_IN_LOOKBACK naming its date; an action before its window, or none, leaves it unmarked; the value is unchanged', () => {
    const share = value(flow('FL03', { window: 20 }));          // Share · Volume over 20 sessions
    const marked = cellOn(share, [], [IN]), before = cellOn(share, [], [OLD]), none = cellOn(share);
    expect([marked.remark, marked.remark_dates]).toEqual(['FLOW_BASIS_IN_LOOKBACK', [IN]]);
    expect([before.remark, none.remark]).toEqual([null, null]);
    expect(plain(marked)).toEqual(plain(none));
    expect(typeof marked.value).toBe('number');
    // a price level (Buy VWAP) against the close: its lots side is marked the same way, its sides unchanged
    const close = { kind: 'price', field: 'close' }, vwap = { kind: 'state', lhs: close, op: 'gt', rhs: flow('FL17') } as Test;
    const v = cellOn(vwap, [], [IN]), v0 = cellOn(vwap);
    expect([v.remark, v.remark_dates, v.status, v.lhs, v.rhs]).toEqual(['FLOW_BASIS_IN_LOOKBACK', [IN], v0.status, v0.lhs, v0.rhs]);
  });
  it('a lots-only output is not marked by a price break; one that reads the close is (VWAP distance %), and FLOW_BASIS wins when both are crossed, naming both dates', () => {
    expect(cellOn(value(flow('FL03', { window: 20 })), [brk(IN)]).remark).toBeNull();
    const pb = cellOn(value(flow('FL39')), [brk(IN)]);
    expect([pb.remark, pb.remark_dates]).toEqual(['PRICE_BREAK_IN_LOOKBACK', [IN]]);
    const both = cellOn(value(flow('FL39')), [brk(IN)], [ALSO]);
    expect([both.remark, both.remark_dates]).toEqual(['FLOW_BASIS_IN_LOOKBACK', [IN, ALSO]]);
    expect(plain(both)).toEqual(plain(cellOn(value(flow('FL39')))));
  });
  it('the price side of a flow comparison keeps its own lookback: a state reads one bar, an event within 10 reads 10 more', () => {
    const close = { kind: 'price', field: 'close' };
    expect(cellOn({ kind: 'state', lhs: close, op: 'gt', rhs: flow('FL17') } as Test, [brk(IN)]).remark).toBeNull();
    const ev = cellOn({ kind: 'event', within: 10, signal: { lhs: close, op: 'crosses_above', rhs: flow('FL17') } } as Test, [brk(IN)]);
    expect([ev.remark, ev.remark_dates]).toEqual(['PRICE_BREAK_IN_LOOKBACK', [IN]]);
  });
  it('a window test counts a one-candle lots output across the action: the value alone is not marked, ten sessions of it are', () => {
    const one = value(flow('FL03'));                            // Share · Volume of one session (its default window)
    expect(cellOn(one, [], [IN]).remark).toBeNull();
    const win = cellOn({ kind: 'window', mode: 'ever', length: 10, test: one } as Test, [], [IN]);
    expect([win.remark, win.remark_dates]).toEqual(['FLOW_BASIS_IN_LOOKBACK', [IN]]);
    // a rupiah output in a window is not marked by a price break inside it (it reads no price)
    expect(cellOn({ kind: 'window', mode: 'ever', length: 10, test: value(flow('FL25')) } as Test, [brk(IN)]).remark).toBeNull();
  });
  it('a moving average of a flow output reads it from the window\'s start: marked by an action before its own window, a rupiah one still not', () => {
    const ma = (of: unknown) => value({ kind: 'transform', fn: 'ma', of, args: { ma: 'SMA', length: 5 } });
    expect(cellOn(value(flow('FL03', { window: 5 })), [], [OLD]).remark).toBeNull();       // its own 5 sessions do not reach OLD
    const c = cellOn(ma(flow('FL03', { window: 5 })), [], [OLD]);
    expect([c.remark, c.remark_dates]).toEqual(['FLOW_BASIS_IN_LOOKBACK', [OLD]]);
    expect(cellOn(ma(flow('FL25')), [brk(OLD)], [OLD]).remark).toBeNull();
  });
});

/* ---- which actions count (universe.ts flowBasisDates) -------------------------------------------------------------------- */

describe('flowBasisDates: the actions of the broker window whose lots are not on one basis', () => {
  const act = (ex_date: string, basis: string | null | undefined, type = 'STOCK_SPLIT'): ActionRow => ({ ticker: 'AAAA', type, ex_date, ratio_old: 1, ratio_new: 2, ...(basis === undefined ? {} : { basis }) });
  it('a lots cell across a `same` action is not marked; across a `terms`, `pending` or `unresolved` one it is', () => {
    expect(flowBasisDates([act(WINDOW[10], 'same')], FIRST, LAST)).toEqual([]);
    expect(flowBasisDates([act(WINDOW[10], 'terms'), act(WINDOW[20], 'pending'), act(WINDOW[30], 'unresolved')], FIRST, LAST)).toEqual([WINDOW[10], WINDOW[20], WINDOW[30]]);
  });
  it('an old file without the column (R2), or a status the publisher left null, marks rather than stays silent', () => {
    expect(flowBasisDates([act(WINDOW[10], undefined)], FIRST, LAST)).toEqual([WINDOW[10]]);
    expect(flowBasisDates([act(WINDOW[10], null)], FIRST, LAST)).toEqual([WINDOW[10]]);
  });
  it('only price-affecting actions strictly after the window\'s first date and up to its last; none without a window', () => {
    expect(flowBasisDates([act(WINDOW[10], null, 'DIVIDEND'), act(FIRST, 'terms'), act('2099-01-02', 'terms'), act(WINDOW[3], 'terms', 'RIGHT_ISSUE'), act(WINDOW[3], 'terms', 'RIGHT_ISSUE')], FIRST, LAST)).toEqual([WINDOW[3]]);
    expect(flowBasisDates([act(WINDOW[10], 'terms')], null, null)).toEqual([]);
  });
  it('a screen carries them to the cells (ScreenEnv.flowBasisDates); the warning counts the marked rows and cells, a row without a price break included', () => {
    const rows = [rowOf(A, E)], env = memoryEnv([A], INDEX, rows, E, { flow: FLOW_CTX, flowBasisDates: t => t === 'AAAA' ? [IN] : [] });
    const def = { universe: { security_types: ['stock'], price_min: null, adv20_min_idr: null }, logic: 'all', conditions: [
      { id: 'a', enabled: true, test: value(flow('FL03', { window: 20 })) }, { id: 'b', enabled: true, test: value(flow('FL25')) }] } as unknown as Definition;
    const r = runScreen(def, env, { exhaustive: true }), row = r.rows.find(x => x.ticker === 'AAAA')!;
    expect(row.cells.map(c => c.remark)).toEqual(['FLOW_BASIS_IN_LOOKBACK', null]);
    expect(row.remarks).toEqual([]);
    expect(r.warnings).toContainEqual(expect.objectContaining({ code: 'PRICE_BREAKS_IN_RESULT', count: 1, details: { rows: 1, cells: 1 } }));
  });
});

/* ---- D-1: the row badge --------------------------------------------------------------------------------------------- */

describe('D-1: a run row shows a price-break badge only when a cell crossed it or it is on the last bar', () => {
  const T = synth('DONE', 77, 300, '2025-01-06'), n = T.dates.length, LASTBAR = T.dates[n - 1], OLDBRK = T.dates[n - 60];
  const ROWS = [rowOf(T, LASTBAR, { adv20_idr: 5e9, last: 1000 }, [brk(OLDBRK), brk(LASTBAR)])];
  const env = () => memoryEnv([T], synth('IHSG', 3, 300, '2025-01-06'), ROWS, LASTBAR);
  const close = { kind: 'price', field: 'close' }, sma5 = { kind: 'indicator', indicator: 'I01', output: 'sma', params: { length: 5 } }, rsi = { kind: 'indicator', indicator: 'I13', output: 'rsi' };
  const screen = (test: Test) => runScreen({ universe: { security_types: ['stock'], price_min: null, adv20_min_idr: null }, logic: 'any', conditions: [{ id: 'a', enabled: true, test }] } as unknown as Definition, env(), { exhaustive: true });
  it('a window output past an old break drops it and keeps the break on the last bar; the universe rows keep both', () => {
    const r = screen({ kind: 'value', metric: sma5, op: 'gt', value: -1 } as Test), row = r.rows[0];
    expect(row.cells[0].remark_dates).toEqual([LASTBAR]);
    expect(row.remarks.map(x => (x as PriceBreakRemark).ex_date)).toEqual([LASTBAR]);
    expect(ROWS[0].remarks.length).toBe(2);
  });
  it('a whole-history output crosses every old break, so it keeps them all (the known limit: D-1 helps window outputs only)', () => {
    const row = screen({ kind: 'value', metric: rsi, op: 'gt', value: -1 } as Test).rows[0];
    expect(row.cells[0].remark_dates).toEqual([OLDBRK, LASTBAR]);
    expect(row.remarks.map(x => (x as PriceBreakRemark).ex_date)).toEqual([OLDBRK, LASTBAR]);
  });
  it('the preview follows the same rule', () => {
    const p = previewCells({ universe: { security_types: ['stock'], price_min: null, adv20_min_idr: null }, logic: 'all', conditions: [{ id: 'a', enabled: true, test: { kind: 'state', lhs: close, op: 'gt', rhs: sma5 } }] } as unknown as Definition, env(), 'DONE');
    expect(p.remarks.map(x => (x as PriceBreakRemark).ex_date)).toEqual([LASTBAR]);
  });
  it('STALE stays, a break on the last bar stays without any cell, and a marked cell without dates keeps every break', () => {
    const stale = { code: 'STALE', last_bar_date: '2025-01-01' } as RowRemark, rs = [stale, brk('2025-01-02'), brk('2025-03-04')];
    expect(shownRemarks(rs, [], ['2025-03-03', '2025-03-05'])).toEqual([stale, brk('2025-03-04')]);   // the ex date between the last two bars
    expect(shownRemarks(rs, [{ id: 'a', status: 'pass', eval_date: '2025-03-05', reason: null, remark: 'PRICE_BREAK_IN_LOOKBACK' }], ['2025-03-05'])).toEqual(rs);
  });
});

/* ---- the page's words (texts.ts) ---------------------------------------------------------------------------------- */

describe('the cell remark words name the dates crossed', () => {
  it('FLOW_BASIS names the action; PRICE_BREAK names the dates crossed, or the row\'s breaks on an older cell without them', () => {
    expect(cellRemarkText('FLOW_BASIS_IN_LOOKBACK', [], ['2026-10-14'])).toBe("Distorted: this value's broker window crosses the corporate action of 2026-10-14; broker lots before it are on the old share count. Shown as computed.");
    expect(cellRemarkText('PRICE_BREAK_IN_LOOKBACK', [brk('2022-08-30'), brk('2026-10-14')], ['2026-10-14'])).toBe("Distorted: this value's look-back contains the price break of 2026-10-14. Shown as computed.");
    expect(cellRemarkText('PRICE_BREAK_IN_LOOKBACK', [brk('2022-08-30'), brk('2026-10-14')])).toBe("Distorted: this value's look-back contains the price break of 2022-08-30, 2026-10-14. Shown as computed.");
  });
});
