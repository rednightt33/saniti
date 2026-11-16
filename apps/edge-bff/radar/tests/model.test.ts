/* EXEC-RADAR R7: the page picks Feature 07's rows; it decides nothing about a stock (src/model.ts). */
import { describe, expect, it } from 'vitest';
import { columns, conditions, counts, levelOf, lists, membersOn, metBits, runs, stockFacts } from '../src/model.ts';
import type { Board, Days, FilterFile, Meta } from '../src/types.ts';

const F = (id: string, position: number, column: string, extra: object = {}) => ({ id, position, column, column_label: column === 'S6D' ? 'S6Δ' : column,
  variant: null, default_variant: true, name: id, question: 'q', warning: 'w', sort_label: 's', own_levels: false, ...extra });
const meta: Meta = {
  schema: 1, levels: ['loose', 'standard', 'strict'], gates: ['broad', 'liquid'],
  filters: [F('S1', 1, 'S1'), F('S6D_RANK', 6, 'S6D', { variant: 'Rank', default_variant: false }), F('S6D_RATIO', 5, 'S6D', { variant: 'Ratio' }),
            F('S8', 9, 'S8', { own_levels: true })] as any,
  rules: [{ filter: 'S1', cond: 'B', level: 'strict', label: 'b', threshold: 5, threshold2: null, status: 'decided' },
          { filter: 'S1', cond: 'A', level: 'strict', label: 'a', threshold: 0, threshold2: null, status: 'decided' },
          { filter: 'S8', cond: 'A', level: 'standard', label: 's8a', threshold: 3, threshold2: null, status: 'decided' }],
  names: { BBCA: 'Bank Central Asia' }, lists: [{ key: 'INDEX:1', kind: 'INDEX', code: 'LQ45', name: 'LQ45', members: ['BBCA'] }],
};
const board: Board = {
  schema: 1, date: '2026-11-09',
  stocks: { ticker: ['BBCA', 'TLKM'], close: [9000, 3000], chg_1d: [1.5, -2], spark: [[1, 2], [3, 2]] },
  rows: { filter: ['S1', 'S1', 'S1', 'S8', 'S1'], stock: [0, 1, 1, 0, 0], level: ['standard', 'standard', 'standard', 'standard', 'strict'],
          gate: ['broad', 'broad', 'liquid', 'broad', 'broad'], status: ['hit', 'near', 'hit', 'hit', 'left'], met: [15, 7, 15, 3, 1],
          cond_n: [4, 4, 4, 3, 4], run_day: [3, null, 1, 1, null], left_reason: [null, null, null, null, 'B'], strong: [null, null, null, false, null],
          sort_value: [2.5, 1, 4, 3.1, null], flag: ['x', null, null, null, null] },
  measures: { columns: ['foreign_net_5d'], values: [[1e9], null] },
};

describe('the board', () => {
  it('orders columns by position and puts the default variant first', () => {
    const c = columns(meta);
    expect(c.map(x => x.id)).toEqual(['S1', 'S6D', 'S8']);
    expect(c[1].variants.map(v => v.id)).toEqual(['S6D_RATIO', 'S6D_RANK']);
  });
  it('reads the rows of one level and gate, by status, hits by their sort key', () => {
    const l = lists(board, meta.filters[0], 1, 'broad');
    expect(l.hits.map(r => [r.t, r.run, r.flag])).toEqual([['BBCA', 3, 'x']]);
    expect(l.near.map(r => r.t)).toEqual(['TLKM']);
    expect(lists(board, meta.filters[0], 1, 'liquid').hits.map(r => r.t)).toEqual(['TLKM']);
    expect(lists(board, meta.filters[0], 2, 'broad').left.map(r => [r.t, r.why])).toEqual([['BBCA', 'B']]);
    expect(lists(board, meta.filters[0], 1, 'broad', t => t !== 'BBCA').hits).toEqual([]);
  });
  it('reads S8 at its own level whatever the Level switch says', () => {
    expect(levelOf(meta.filters[3], 0)).toBe('standard');
    expect(lists(board, meta.filters[3], 2, 'broad').hits.map(r => [r.t, r.strong])).toEqual([['BBCA', false]]);
    expect(conditions(meta, meta.filters[3], 0).map(r => r.label)).toEqual(['s8a']);
    expect(conditions(meta, meta.filters[0], 2).map(r => r.cond)).toEqual(['A', 'B']);
  });
  it('turns met bits into conditions A-D', () => {
    expect(metBits(5, 4)).toEqual([true, false, true, false]);
    expect(metBits(null, 3)).toEqual([false, false, false]);
  });
  it('gives a stock its facts and measures, nothing for an unknown one', () => {
    const f = stockFacts(meta, board);
    expect([f.name('BBCA'), f.close('BBCA'), f.chg('TLKM'), f.measure('BBCA', 'foreign_net_5d'), f.measure('TLKM', 'foreign_net_5d')])
      .toEqual(['Bank Central Asia', 9000, -2, 1e9, null]);
    expect([f.close('XXXX'), f.spark('XXXX')]).toEqual([null, []]);
  });
});

describe('the detail', () => {
  const days = { dates: ['a', 'b', 'c'], counts: { S1: { 'standard/broad': [1, 2, 3] } } } as unknown as Days;
  const file: FilterFile = {
    schema: 1, filter: 'S1', dates: ['a', 'b', 'c', 'd'], stocks: { ticker: ['BBCA', 'TLKM'], close: [[1, 2, 3, 4], [5, 6, 7, 8]] },
    hits: { date: [0, 1, 3, 1], stock: [0, 0, 0, 1], level: ['standard', 'standard', 'standard', 'loose'], gate: ['broad', 'broad', 'broad', 'broad'], run_day: [1, 2, 1, 1] },
    left: { date: [2], stock: [0], level: ['standard'], gate: ['broad'], left_reason: ['A'] },
  };
  it('takes the daily counts up to a date', () => {
    expect(counts(days, meta.filters[0], 1, 'broad', 1, 20)).toEqual([1, 2]);
    expect(counts(days, meta.filters[0], 1, 'liquid', 2, 2)).toEqual([]);
  });
  it('lists the members of a day and the runs of a stock at one setting', () => {
    expect([...membersOn(file, meta.filters[0], 1, 'broad', 1)]).toEqual([['BBCA', 2]]);
    expect(runs(file, meta.filters[0], 1, 'broad', 'BBCA')).toEqual([[0, 1], [3, 3]]);
    expect(runs(file, meta.filters[0], 1, 'broad', 'TLKM')).toEqual([]);
  });
});
