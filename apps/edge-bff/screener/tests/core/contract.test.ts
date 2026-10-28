/* The wire contract (report API CONTRACT section 8) as a compile test and its constants: the examples of report 8.5
   type-check as RunRequest and RunResponse (tsc --noEmit covers this file), the error table is exactly report 8.8,
   and contract.ts stays importable by the page: it imports nothing at run time (report I1, 9.1). */
import { describe, expect, it } from 'vitest';
import contractSource from '../../src/core/contract.ts?raw';
import {
  CELL_REMARKS, CONDITION_ID, ERROR_CODES, ERROR_STATUS, ITEM_ID, NA_REASONS, PREVIEW_BARS, ROW_REMARK_CODES, SCHEMA_VERSION,
  TICKER, UNIVERSE_DEFAULTS, WORKER_ERROR_STATUS, WORKER_GZIP_ROUTES, WORKER_KEY_HEADER, WORKER_OWNER_HEADER, WORKER_ROUTES,
} from '../../src/core/contract.ts';
import type {
  Cell, CountsRequest, Definition, PreviewRequest, ResultRow, RowRemark, RunRequest, RunResponse, SavedItem, Test,
  UniverseRow, ValidateResponse,
} from '../../src/core/contract.ts';
import { ScreenerError } from '../../src/core/errors.ts';

/* report 8.5 example, request and answer, typed exactly (a missing or extra field fails tsc) */
const definition = {
  universe: { security_types: ['stock'], price_min: 50, adv20_min_idr: 1000000000, traded_on_eval_date: true, exclude_price_breaks: true },
  conditions: [
    { id: 'a', enabled: true, test: { kind: 'value', op: 'lt', value: 30, metric: { kind: 'indicator', indicator: 'I13', params: { length: 7 }, output: 'rsi' } } },
    { id: 'b', enabled: true, test: { kind: 'state', op: 'gt', lhs: { kind: 'price', field: 'close' }, rhs: { kind: 'indicator', indicator: 'I01', params: { length: 50 }, output: 'sma' } } },
    { id: 'c', enabled: true, test: { kind: 'event', within: 5, signal: { op: 'crosses_above',
      lhs: { kind: 'indicator', indicator: 'I06', params: {}, output: 'macd' }, rhs: { kind: 'indicator', indicator: 'I06', params: {}, output: 'signal' } } } },
  ],
  logic: 'at_least', at_least: 2,
} satisfies Definition;
const request = {
  schema_version: 1, client_order: { page: 'pg_3f2a9c0d1e2b4a5c6d7e8f9012345678', seq: 7 }, definition, options: { exhaustive: false, explain: false },
} satisfies RunRequest;
const answer = {
  schema_version: 1,
  versions: { screener_engine: '0a1b2c3d4e5f6071', registry: '8192a3b4c5d6e7f8', screener_registry: '1f2e3d4c5b6a7980', price_data: 'f'.repeat(64), flow_data: null, definition_hash: 'e'.repeat(64) },
  data: { evaluation_date: '2026-10-27', price_through: '2026-10-27', flow_through: null, broker_behind_sessions: 0, published_at: '2026-10-27T13:03:23Z' },
  mode: 'screen', universe: { listed: 844, eligible: 340, stale_hidden: 16, price_break_hidden: 8, filtered_out: 480 },
  conditions: [
    { id: 'a', source: 'dynamic', metric: 'I13.rsi', params_resolved: { length: 7, source: 'close' }, is_default: false, kind: 'value', unit: 'index', evaluated: 340, passed: 61, na: 0, exhaustive: true, eval_date_basis: 'ticker_last_bar' },
    { id: 'b', source: 'precomputed', metric: 'I01.sma', params_resolved: { length: 50, source: 'close' }, is_default: false, kind: 'state', unit: 'price', evaluated: 340, passed: 120, na: 1, exhaustive: true, eval_date_basis: 'ticker_last_bar' },
    { id: 'c', source: 'precomputed', metric: 'I06.macd x I06.signal', params_resolved: { fast_length: 12, slow_length: 26, signal_length: 9, source: 'close' }, is_default: true, kind: 'event', unit: 'price', evaluated: 171, passed: 40, na: 0, exhaustive: false, eval_date_basis: 'ticker_last_bar' },
  ],
  need: 2, match_count: 25, near_count: 118,
  rows: [{ ticker: 'XMPL', name: 'Example Tbk', sector: 'Financials', industry: 'Banks', board: null, market_cap: null,
    last: 1234, chg_1d_pct: -1.2, adv20_idr: 45600000000, last_bar_date: '2026-10-27', stale: false, remarks: [],
    status: 'match', met: 2, need: 2, na_count: 0,
    cells: [{ id: 'a', status: 'pass', value: 27.4, unit: 'index', eval_date: '2026-10-27', reason: null, remark: null },
      { id: 'b', status: 'fail', lhs: 1234, rhs: 1250.5, eval_date: '2026-10-27', reason: null, remark: null },
      { id: 'c', status: 'pass', lhs: -3.1, rhs: -3.4, eval_date: '2026-10-27', event_date: '2026-10-23', bars_ago: 2, market_sessions_ago: 2, last_event_date: '2026-10-23', reason: null, remark: null }] }],
  warnings: [], timings_ms: { queue: 0, s0: 2, s1: 0, s2: 3, s3: 95, s4: 12, total: 118 },
} satisfies RunResponse;

/* P4 rows and cells (report 8.4, 8.5): a shown stale or price-break row carries its remark; a cell keeps its value */
const remarks: RowRemark[] = [
  { code: 'STALE', last_bar_date: '2026-08-21' },
  { code: 'PRICE_BREAK', action: 'STOCK_SPLIT', ex_date: '2026-10-14', ratio_old: 1, ratio_new: 2, close_ratio: 0.4544 },
];
const marked: Cell = { id: 'a', status: 'pass', value: 22.8, eval_date: '2026-10-27', reason: null, remark: 'PRICE_BREAK_IN_LOOKBACK' };
const na: Cell = { id: 'b', status: 'na', value: null, eval_date: '2026-10-27', reason: 'INSUFFICIENT_HISTORY', remark: null };
const universeRow: UniverseRow = { ticker: 'PBSA', name: null, sector: null, industry: null, last: 302, chg_1d_pct: 0, adv20_idr: 1e9, first_bar: '2018-01-02', last_bar: '2026-10-27', bars: 2100, stale: false, remarks };
const pinned = { schema_version: 1, data_version: 'f'.repeat(64), definitions: [{ item_id: 'scr_' + '0'.repeat(32), definition }] } satisfies CountsRequest;
const preview = { schema_version: 1, client_order: { page: 'p', seq: 1 }, definition, ticker: 'BBCA', data_version: 'f'.repeat(64) } satisfies PreviewRequest;
const valid = { valid: true, definition_hash: 'e'.repeat(64), normalized: definition } satisfies ValidateResponse;
const between: Test = { kind: 'value', op: 'between', value: 30, value2: 30, metric: { kind: 'universe', attr: 'last' } };
const item: SavedItem = { item_id: 'scr_' + 'a'.repeat(32), kind: 'metric', name: 'RSI dip', definition: { test: between }, schema_version: 1,
  registry_version: 'b6a8dc0ba206ed65', screener_registry_version: '0123456789abcdef', definition_hash: 'e'.repeat(64), revision: 1,
  created_at: '2026-10-28T00:00:00Z', updated_at: '2026-10-28T00:00:00Z', needs_review: [] };

describe('contract', () => {
  it('types the report 8.5 example and the P4 shapes (compile test; tsc --noEmit)', () => {
    const rows: ResultRow[] = answer.rows;
    expect(request.schema_version).toBe(SCHEMA_VERSION);
    expect(rows[0].cells.map(c => c.remark)).toEqual([null, null, null]);
    expect([marked.value, marked.status, na.reason, universeRow.remarks.length, pinned.definitions.length, preview.ticker, valid.valid, item.kind])
      .toEqual([22.8, 'pass', 'INSUFFICIENT_HISTORY', 2, 1, 'BBCA', true, 'metric']);
  });

  it('has exactly the error table of report 8.8, with its statuses', () => {
    expect(ERROR_STATUS).toEqual({
      INVALID_INPUT: 422, INVALID_CONDITION: 422, UNKNOWN_INDICATOR: 422, PARAM_OUT_OF_RANGE: 422, METRIC_UNAVAILABLE: 422,
      LIMIT_EXCEEDED: 422, DATA_UNAVAILABLE: 424, DATA_INTEGRITY: 424, BUSY: 409, SCREEN_REPLACED: 409, PREVIEW_REPLACED: 409,
      DATA_VERSION_CHANGED: 409, REVISION_CONFLICT: 409, NAME_TAKEN: 409, NOT_FOUND: 404, REQUEST_TOO_LARGE: 413,
      SCREENER_DISABLED: 503, SCREENER_NOT_READY: 503, SCREENER_UNAVAILABLE: 503, TIMEOUT: 504,
    });
    expect(ERROR_CODES.length).toBe(20);
    expect(WORKER_ERROR_STATUS.DATA_VERSION_PENDING).toBe(409);                   // worker-only (report 8.8 note, 6d.4)
    expect(Object.keys(ERROR_STATUS)).not.toContain('DATA_VERSION_PENDING');
    const e = new ScreenerError('PARAM_OUT_OF_RANGE', 'p.length must be at most 252.', 'p.length', { field: 'p.length', max: 252 });
    expect([e.status, e.toApi()]).toEqual([422, { error: { code: 'PARAM_OUT_OF_RANGE', message: 'p.length must be at most 252.', field: 'p.length', details: { field: 'p.length', max: 252 } } }]);
  });

  it('lists the NA reasons and remarks of report 6.9 and P4', () => {
    expect(NA_REASONS).toEqual(['INSUFFICIENT_HISTORY', 'NULL_AT_EVALUATION', 'FLOW_UNAVAILABLE', 'FLOW_LAGGED', 'NOT_APPLICABLE', 'DATA_INTEGRITY', 'MIXED_ADJUSTMENT_BASIS']);
    expect(ROW_REMARK_CODES).toEqual(['STALE', 'PRICE_BREAK']);
    expect(CELL_REMARKS).toEqual(['PRICE_BREAK_IN_LOOKBACK']);
  });

  it('keeps the P4 chips on by default and the prototype liquidity defaults', () => {
    expect(UNIVERSE_DEFAULTS).toMatchObject({ traded_on_eval_date: true, exclude_price_breaks: true, price_min: 50, adv20_min_idr: 1e9, include_unclassified: false });
    expect(Object.isFrozen(UNIVERSE_DEFAULTS)).toBe(true);
  });

  it('keeps the id rules of the migration and terminal-api', () => {
    expect([CONDITION_ID.test('a1'), CONDITION_ID.test('abcdefg'), CONDITION_ID.test('A')]).toEqual([true, false, false]);
    expect([ITEM_ID.test('scr_' + 'a'.repeat(32)), ITEM_ID.test('scr_' + 'A'.repeat(32))]).toEqual([true, false]);
    expect([TICKER.test('BBCA'), TICKER.test('bbca')]).toEqual([true, false]);
    expect(PREVIEW_BARS).toBe(260);
  });

  it('names the worker routes and headers of report 8.11', () => {
    expect(WORKER_KEY_HEADER).toBe('x-screener-worker-key');
    expect(WORKER_OWNER_HEADER).toBe('x-screener-owner');
    expect(Object.values(WORKER_ROUTES)).toEqual(['GET /health', 'GET /ready', 'GET /v1/catalog', 'GET /v1/universe', 'POST /v1/run', 'POST /v1/preview', 'POST /v1/validate', 'POST /v1/counts']);
    expect(WORKER_GZIP_ROUTES).toEqual(['POST /v1/run', 'POST /v1/preview', 'POST /v1/counts']);
  });

  it('imports nothing at run time, so the page can import it (report I1, 9.1)', () => {
    const imports = contractSource.split('\n').filter(l => /^\s*import\s/.test(l));
    expect(imports.length).toBeGreaterThan(0);
    for (const l of imports) expect(l).toMatch(/^import type /);
  });
});
