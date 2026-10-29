/* The page's refusal wording (src/texts.ts errorText; report API CONTRACT 8.8, 8.9; AGENTS.md "Gates and evidence"
   (d)): every code and every limit the worker and edge-bff send the page is worded with where the problem is and how
   to fix it, from the catalog's limits[] (no limit and no number kept in the page), in plain words (no limit name, no
   field path, no code). LIMITS is GET /api/v1/screener/catalog limits[] as the worker (apps/screener-worker/src/
   catalog.ts limitEntries, at the values below) and edge-bff (app/screener.py own_limits) generated it on 2026-10-29;
   the tests check that each message is built from its entry, so a change of the generated words or values needs no
   change here. */
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import type { CatalogResponse, LimitEntry } from '../../src/core/contract.ts';
import { ERROR_CODES } from '../../src/core/contract.ts';
import { errorText, fieldWords, placeText } from '../../src/texts.ts';
import { ctx, S } from '../../src/state.ts';
import { liveApi } from '../../src/api/live.ts';
import { ApiFailure } from '../../src/api/types.ts';
import type { Card } from '../../src/forms.ts';
import type { Entry } from '../../src/entries.ts';

const L = (name: string, value: number, unit: string, rule: string, example_ok: string, example_refused: string): LimitEntry => ({ name, value, unit, rule, example_ok, example_refused });
/** the worker's limits at max_cpu_ms 20000, cap_budget_ms 2000, deadline_ms 20000, max_conditions 20, max_metric_filters 8,
    within_max 130, max_counts 50, max_response_bytes 2097152, queue 4, owner_inflight 2, owner_cpu_ms 60000,
    previous_grace_s 600 (the refresh caps are left out: they fail a refresh, never a request), then edge-bff's own */
const LIMITS: LimitEntry[] = [
  L('max_conditions', 20, 'conditions', 'at most 20 enabled conditions in one screen', 'a screen with 20 enabled conditions', 'a screen with 21 enabled conditions (switch one off or remove it)'),
  L('max_metric_filters', 8, 'filters', 'at most 8 universe metric filters in one screen', '8 metric filters', '9 metric filters (remove one)'),
  L('within_max', 130, 'sessions', '"within" is a whole number of sessions from 1 to 130', 'within 130 sessions', 'within 131 sessions (use 130 or fewer)'),
  L('cap_budget_ms', 2000, 'ms', "a length parameter is at most its cap (the catalog's max), the longest whose computation over the whole market fits 2000 ms on one thread", 'Hull Moving Average length 252', 'Hull Moving Average length 253 (use 252 or less)'),
  L('compute_budget', 20000, 'ms', "a screen's predicted worst-case compute is at most 20000 ms; a costlier screen is refused before it runs, naming its costliest condition", 'a screen of default indicators (read from the snapshot)', 'a screen whose custom conditions are predicted at 20001 ms (use fewer custom conditions or shorter lengths)'),
  L('deadline_ms', 20000, 'ms', 'a screen is answered within 20000 ms, waiting included, or stopped with TIMEOUT', 'a screen answered after 20000 ms', 'a screen still running after 20000 ms (use fewer custom conditions or shorter lengths)'),
  L('owner_inflight', 2, 'requests', 'at most 2 requests of one user compute at once on a replica; the next ones wait their turn', '2 requests computing at once', 'request 3 waits until one of them ends (it is not refused)'),
  L('owner_cpu_budget', 60000, 'ms per minute', "one user's requests use at most 60000 ms of compute per minute on a replica (P33); a request that would pass it is refused with the seconds to wait", 'requests using 60000 ms within one minute', 'a request that would bring the minute to 60001 ms (wait the seconds named, or use fewer custom conditions)'),
  L('previous_grace_s', 600, 's', 'after new data is published, a page still showing the previous data is served on it for 600 s', 'a screen pinned to the previous data 600 s after the new data arrived', 'a screen pinned to the previous data 601 s after (DATA_VERSION_CHANGED: the page re-reads the catalog and runs again)'),
  L('queue', 4, 'requests', 'at most 4 requests wait for a compute thread on a replica, every user together', 'a request arriving while 3 wait', 'a request arriving while 4 wait (BUSY: retry in a few seconds)'),
  L('max_counts', 50, 'definitions', 'counts for at most 50 saved screens per request', '50 saved screens', '51 saved screens (ask for the rest in a second request)'),
  L('max_response_bytes', 2097152, 'bytes', 'an answer is at most 2097152 bytes of JSON', 'an answer of 2097152 bytes', 'an answer of 2097153 bytes (narrow the universe or add a condition)'),
  L('saved_items', 50, 'items of each kind', 'at most 50 saved screens and 50 My metrics', 'saving a new screen while 49 are saved', 'saving a new screen while 50 are saved (delete one first)'),
  L('watchlist', 500, 'tickers', 'at most 500 tickers in the watchlist', 'watching a new ticker while 499 are watched', 'watching a new ticker while 500 are watched (remove one first)'),
  L('saved_definition_bytes', 65536, 'bytes', 'a saved screen or My metric is at most 65,536 bytes of JSON as stored (a space after each colon and comma)', 'a saved definition of 65,536 bytes', 'a saved definition of 65,537 bytes (remove conditions or filters)'),
  L('request_bytes', 131072, 'bytes', 'a request to the screener is at most 131,072 bytes', 'a run request of 131,072 bytes', 'a run request of 131,073 bytes (remove conditions or filters)'),
  L('inflight_per_page', 1, 'requests of each kind per page', '1 screen and 1 preview in flight per page: a newer one replaces the older one, which answers SCREEN_REPLACED or PREVIEW_REPLACED', 'a preview while the same page runs a screen, or a screen run in another tab', 'a second screen of the same page while its first is running (the first is replaced; nothing to do)'),
];
const limit = (name: string) => LIMITS.find(l => l.name === name)!;

/* the page's cards: condition 1 SMA, condition 2 RSI, condition 3 a flow metric, universe filter 1 ADV20 */
const P = (key: string, label: string, min: number, max: number) => ({ key, type:'integer', label, default:min, min, max, exclusive_min:false, integer:true, step:1 });
const entry = (key: string, label: string, params: unknown[] = []) => ({ key, kind:'indicator', group:'Trend', label, short:label, desc:'', params, opts:[],
  def:{ opt:'', value:'', value2:'', within:1 }, available:true, availability:'AVAILABLE', reason:null, synonyms:[], history:null }) as unknown as Entry;
const ENTRIES = [entry('I01', 'Simple Moving Average', [P('length', 'Length', 1, 567)]), entry('I13', 'Relative Strength Index', [P('length', 'Length', 2, 500)]),
  entry('fnet', 'Foreign net flow'), entry('adv20_idr', 'Average daily value')];
const card = (id: string, e: string): Card => ({ id, on:true, entry:e, params:{}, opt:'', value:'', value2:'', within:'', second:{} });

/** what a page message must never show: a limit or field name (snake_case), a code (UPPER_CASE), a contract path, an
    environment variable */
const INTERNAL = /\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b|\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b|definition\.|conditions\[|universe\./;
const plainWords = (s: string) => { expect(s, s).not.toMatch(INTERNAL); return s };

beforeEach(() => {
  ctx.byKey = new Map(ENTRIES.map(e => [e.key, e]));
  S.cards = [card('a', 'I01'), card('b', 'I13'), card('c', 'fnet')];
  S.universe.filters = [card('f', 'adv20_idr')];
  ctx.catalog = { limits:LIMITS } as unknown as CatalogResponse;
});
afterEach(() => { ctx.catalog = null; ctx.byKey = new Map(); S.cards = []; S.universe.filters = [] });

describe('the place a refusal names (the field as the page shows it)', () => {
  it('names the card by its number and name and the parameter by its catalog label', () => {
    expect(placeText('definition.conditions[1].test.metric.params.length')).toBe('condition 2 (Relative Strength Index), Length');
    expect(placeText('definition.conditions[0].test.within')).toBe('condition 1 (Simple Moving Average), within (sessions)');
    expect(placeText('conditions[2].test')).toBe('condition 3 (Foreign net flow)');
  });
  it('names the universe, its filters and their fields in words', () => {
    expect(placeText('definition.universe.metric_filters[0].value')).toBe('universe filter 1 (Average daily value), value');
    expect(placeText('definition.universe.metric_filters')).toBe('the universe filters');
    expect(placeText('definition.universe.sectors_in[2]')).toBe('the universe, included sectors 3');
    expect(placeText('definition.universe.price_min')).toBe('the universe, minimum price');
    expect(fieldWords('adv20_min_idr')).toBe('minimum ADV20');
  });
  it('words a field outside the screen, the whole screen, and no field', () => {
    expect(placeText('name')).toBe('name');
    expect(placeText('definition')).toBe('the screen');
    expect(placeText('definition.conditions')).toBe('the conditions');
    expect(placeText(undefined)).toBe('');
    // a card the field names that the page does not hold (another definition): its number only
    expect(placeText('definition.conditions[7].test')).toBe('condition 8');
    // the cards of another definition, passed by the caller; a card whose catalog entry is not loaded: its number only
    expect(placeText('conditions[0].test', { cards:[card('z', 'I13')] })).toBe('condition 1 (Relative Strength Index)');
    ctx.byKey = new Map();
    expect(placeText('definition.conditions[1].test.metric.params.length')).toBe('condition 2, length');
  });
});

describe('LIMIT_EXCEEDED is worded from its catalog entry: where, the rule, what was needed, the fix', () => {
  it('owner_cpu_budget: the per-user budget names the wait the worker sends (details.retry_after_seconds)', () => {
    const l = limit('owner_cpu_budget');
    const m = errorText('LIMIT_EXCEEDED', { details:{ limit:'owner_cpu_budget', allowed:60000, needed:61000, retry_after_seconds:12 },
      server:"This user's screens used 59000 ms of compute in the last minute and have 0 ms waiting; with this one (about 2000 ms) that is above the 60000 ms a user may use per minute. Wait 12 s, or use fewer custom conditions." });
    expect(m).toBe(`Limit reached: ${l.rule}; this one needs 61000 ms per minute. Wait the seconds named, or use fewer custom conditions. Try again in 12 s.`);
    expect(m).not.toContain('owner_cpu_budget');
  });
  it('within_max on a condition (a case other than owner_cpu_budget): the card, the rule and the fix', () => {
    const m = plainWords(errorText('LIMIT_EXCEEDED', { field:'definition.conditions[0].test.within', details:{ limit:'within_max', allowed:130, needed:131 } }));
    expect(m).toBe(`Limit reached in condition 1 (Simple Moving Average), within (sessions): ${limit('within_max').rule}; this one needs 131 sessions. Use 130 or fewer.`);
  });
  it('compute_budget names the costliest condition by its place', () => {
    const m = plainWords(errorText('LIMIT_EXCEEDED', { details:{ limit:'compute_budget', allowed:20000, needed:31000, costliest:'b' } }));
    expect(m).toBe(`Limit reached: ${limit('compute_budget').rule}; this one needs 31000 ms. Use fewer custom conditions or shorter lengths. The costliest is condition 2 (Relative Strength Index).`);
  });
  it('max_conditions and max_metric_filters name the list to shorten', () => {
    expect(plainWords(errorText('LIMIT_EXCEEDED', { field:'definition.conditions', details:{ limit:'max_conditions', allowed:20, needed:23 } })))
      .toBe(`Limit reached in the conditions: ${limit('max_conditions').rule}; this one needs 23 conditions. Switch one off or remove it.`);
    expect(plainWords(errorText('LIMIT_EXCEEDED', { field:'definition.universe.metric_filters', details:{ limit:'max_metric_filters', allowed:8, needed:9 } })))
      .toBe(`Limit reached in the universe filters: ${limit('max_metric_filters').rule}; this one needs 9 filters. Remove one.`);
  });
  it("edge-bff's limits: saved items, the watchlist and the saved definition's size (numbers as the rule writes them)", () => {
    expect(plainWords(errorText('LIMIT_EXCEEDED', { details:{ limit:'saved_items', allowed:50, needed:51 }, server:'At most 50 saved screens: delete one before saving another.' })))
      .toBe(`Limit reached: ${limit('saved_items').rule}; this one needs 51 items of each kind. Delete one first.`);
    // the ticker is the request's field, not a place in the screen: the rule says where (the watchlist)
    expect(plainWords(errorText('LIMIT_EXCEEDED', { field:'ticker', details:{ limit:'watchlist', allowed:500, needed:501 } })))
      .toBe(`Limit reached: ${limit('watchlist').rule}; this one needs 501 tickers. Remove one first.`);
    expect(errorText('LIMIT_EXCEEDED', { field:'definition', details:{ limit:'saved_definition_bytes', allowed:65536, needed:70000 } }))
      .toBe(`Limit reached: ${limit('saved_definition_bytes').rule}; this one needs 70,000 bytes. Remove conditions or filters.`);
  });
  it('max_counts and max_response_bytes', () => {
    expect(plainWords(errorText('LIMIT_EXCEEDED', { field:'definitions', details:{ limit:'max_counts', allowed:50, needed:51 } })))
      .toBe(`Limit reached: ${limit('max_counts').rule}; this one needs 51 definitions. Ask for the rest in a second request.`);
    expect(plainWords(errorText('LIMIT_EXCEEDED', { details:{ limit:'max_response_bytes', allowed:2097152, needed:2500000 } })))
      .toBe(`Limit reached: ${limit('max_response_bytes').rule}; this one needs 2500000 bytes. Narrow the universe or add a condition.`);
  });
  it('every published limit, refused, shows its rule and its fix and never its name', () => {
    for (const l of LIMITS) {
      const m = errorText('LIMIT_EXCEEDED', { details:{ limit:l.name, allowed:l.value, needed:l.value + 1 } });
      expect(m, l.name).toContain(l.rule);
      // what the page adds to the catalog's rule is plain words (the rule's own words are the catalog's)
      plainWords(m.replace(l.rule, ''));
      const fix = /\(([^()]*)\)\W*$/.exec(l.example_refused)?.[1].replace(/^[A-Z_]+:\s*/, '');
      expect(m.toLowerCase(), l.name).toContain((fix || l.example_ok).toLowerCase());
    }
  });
  it('is derived from the catalog: another value, another message; a limit the page never saw is worded from its entry', () => {
    const other = [L('max_conditions', 30, 'conditions', 'at most 30 enabled conditions in one screen', 'a screen with 30 enabled conditions', 'a screen with 31 enabled conditions (switch one off or remove it)')];
    expect(errorText('LIMIT_EXCEEDED', { field:'definition.conditions', details:{ limit:'max_conditions', allowed:30, needed:31 }, limits:other }))
      .toBe('Limit reached in the conditions: at most 30 enabled conditions in one screen; this one needs 31 conditions. Switch one off or remove it.');
    const future = [L('max_tickers_listed', 200, 'tickers', 'at most 200 tickers in the universe ticker list', '200 tickers', '201 tickers')];
    expect(plainWords(errorText('LIMIT_EXCEEDED', { field:'definition.universe.tickers', details:{ limit:'max_tickers_listed', allowed:200, needed:250 }, limits:future })))
      .toBe('Limit reached in the universe, tickers: at most 200 tickers in the universe ticker list; this one needs 250 tickers. Allowed: 200 tickers.');
  });
  it('without the catalog entry (catalog not loaded): the server\'s reason with its paths in words, never the limit name', () => {
    ctx.catalog = null;
    const m = plainWords(errorText('LIMIT_EXCEEDED', { field:'definition.conditions[0].test.within', details:{ limit:'within_max', allowed:130, needed:131 },
      server:'definition.conditions[0].test.within is at most 130 sessions.' }));
    expect(m).toBe('Limit reached: Condition 1 (Simple Moving Average), within (sessions) is at most 130 sessions.');
    expect(plainWords(errorText('LIMIT_EXCEEDED', { details:{ limit:'owner_cpu_budget', allowed:60000, needed:61000, retry_after_seconds:3 } })))
      .toBe('Limit reached: at most 60,000, this one needs 61,000. Reduce it and try again. Try again in 3 s.');
  });
});

describe('codes that stand for a limit (BUSY queue, TIMEOUT deadline, REQUEST_TOO_LARGE request size)', () => {
  it('BUSY words the queue rule and the fix after the code in its refused example', () => {
    const m = plainWords(errorText('BUSY', { details:{ limit:'queue', allowed:4 }, server:'The screener is busy: 4 screens are waiting on this replica, the most it holds (SCREENER_QUEUE 4). Retry in a few seconds.' }));
    expect(m).toBe(`The screener is busy: ${limit('queue').rule}. Retry in a few seconds.`);
    expect(errorText('BUSY')).toBe(m);                      // run.ts's retry line: no body, the code's limit
    // a wait the answer names in Retry-After is said, as details.retry_after_seconds is
    expect(errorText('BUSY', { retryAfter:3 })).toBe(`${m} Try again in 3 s.`);
  });
  it('TIMEOUT words the deadline rule (its body names no limit)', () => {
    expect(errorText('TIMEOUT', { server:'The request took longer than the 20000 ms limit (SCREENER_DEADLINE_MS) after 20003 ms: use fewer custom conditions or shorter lengths.' }))
      .toBe(`The screen took too long: ${limit('deadline_ms').rule}. Use fewer custom conditions or shorter lengths.`);
  });
  it('REQUEST_TOO_LARGE words the request size', () => {
    expect(plainWords(errorText('REQUEST_TOO_LARGE', { details:{ limit:'request_bytes', allowed:131072 } })))
      .toBe(`The request is too large: ${limit('request_bytes').rule}. Remove conditions or filters.`);
  });
  it('without a catalog they keep the report 8.8 wording', () => {
    ctx.catalog = null;
    expect(errorText('BUSY')).toBe('The screener is busy; retry in a few seconds.');
    expect(errorText('TIMEOUT')).toBe('The screen took longer than the limit: use fewer custom conditions or shorter lengths.');
    expect(errorText('REQUEST_TOO_LARGE')).toBe('The definition is too large: remove conditions or filters.');
  });
});

describe('the other refusals name where and how to fix', () => {
  it('PARAM_OUT_OF_RANGE: the parameter and its range, from the refusal or else from the catalog parameter', () => {
    const field = 'definition.conditions[1].test.metric.params.length';
    const m = plainWords(errorText('PARAM_OUT_OF_RANGE', { field, details:{ field:'length', min:2, max:500, integer:true } }));
    expect(m).toBe('Condition 2 (Relative Strength Index), Length is out of range: use a whole number from 2 to 500. Change it and run again.');
    expect(errorText('PARAM_OUT_OF_RANGE', { field })).toBe(m);
    expect(plainWords(errorText('PARAM_OUT_OF_RANGE', { field:'definition.universe.price_min', details:{ field:'price_min', min:0, integer:false } })))
      .toBe('The universe, minimum price is out of range: use a number of at least 0. Change it and run again.');
    expect(errorText('PARAM_OUT_OF_RANGE', { field:'definition.conditions[0].test.metric.params.mult', details:{ field:'mult', min:0, max:10, exclusive_min:true } }))
      .toBe('Condition 1 (Simple Moving Average), mult is out of range: use a number above 0 and at most 10. Change it and run again.');
  });
  it('INVALID_CONDITION: the server\'s reason with its paths in words, or the allowed values in words', () => {
    const m = plainWords(errorText('INVALID_CONDITION', { field:'definition.conditions[1].test.value2', server:'definition.conditions[1].test.value2 must be at least value (70): between is value <= x <= value2, and the bounds are never swapped.' }));
    expect(m).toMatch(/^Condition 2 \(Relative Strength Index\), upper value must be at least value \(70\)/);
    expect(m).toMatch(/Change it and run again\.$/);
    expect(errorText('INVALID_CONDITION', { field:'definition.conditions[0].test.op', details:{ allowed:['gt', 'lt'] } }))
      .toBe('Condition 1 (Simple Moving Average), operator is not valid: use one of greater than, less than. Change it and run again.');
  });
  it('INVALID_INPUT: an edge-bff field (the name) and a request the page built', () => {
    expect(errorText('INVALID_INPUT', { field:'name', server:'name is 1 to 120 characters' })).toBe('Name is 1 to 120 characters. Correct it and try again, or reload the page.');
    expect(errorText('INVALID_INPUT', { field:'definition.universe.price_min' })).toBe('The universe, minimum price is not in a form the screener accepts. Correct it and try again, or reload the page.');
  });
  it('UNKNOWN_INDICATOR and METRIC_UNAVAILABLE name the card and what to do with it', () => {
    expect(errorText('UNKNOWN_INDICATOR', { field:'definition.conditions[0].test.metric.indicator', details:{ allowed:['I01', 'I02'] } }))
      .toBe("Condition 1 (Simple Moving Average), indicator: this indicator is not in the screener's catalog (it was renamed or removed). Remove the condition, or add it again from the indicator list.");
    expect(plainWords(errorText('METRIC_UNAVAILABLE', { field:'definition.conditions[2].test.metric', details:{ metric:'fnet', availability:'REQUIRES_DATA', reason:'Flow arrives with Phase 2.' } })))
      .toBe('Condition 3 (Foreign net flow) is not available yet: Flow arrives with Phase 2. Switch it off or remove it to run the screen.');
  });
  it('the saved-item, data and service codes say what happened and what to do', () => {
    expect(errorText('NAME_TAKEN', { field:'name' })).toMatch(/Pick another name/);
    expect(errorText('REVISION_CONFLICT', { field:'revision', details:{ revision:4 } })).toMatch(/Reload it, or save yours as a copy\.$/);
    expect(errorText('NOT_FOUND')).toMatch(/reload the list\.$/);
    expect(errorText('DATA_UNAVAILABLE')).toMatch(/try again later\.$/);
    expect(errorText('DATA_INTEGRITY')).toMatch(/Try again later\.$/);
    expect(errorText('DATA_VERSION_CHANGED')).toMatch(/runs again/);
    expect(errorText('SCREEN_REPLACED')).toMatch(/nothing to do/);
    expect(errorText('SCREENER_DISABLED')).toMatch(/administrator switches it on/);
    expect(errorText('SCREENER_NOT_READY', { retryAfter:7 })).toBe('The screener is starting or loading new data; retry in 7 s.');
    expect(errorText('SCREENER_NOT_READY', { details:{ retry_after_seconds:2 } })).toMatch(/retry in 2 s/);
    expect(errorText('SCREENER_UNAVAILABLE')).toMatch(/retry shortly/);
    expect(errorText('ORIGIN_REJECTED')).toMatch(/Open EDGE at its own address and try again/);
    expect(errorText('SOMETHING_NEW', { server:'The worker said no.' })).toBe('The worker said no. Retry; if it fails again, reload the page.');
    expect(errorText('')).toBe('The screener could not answer this request. Retry; if it fails again, reload the page.');
  });
  it('every contract code is worded in plain words, with or without a catalog', () => {
    for (const withCatalog of [true, false]) {
      if (!withCatalog) ctx.catalog = null;
      for (const code of ERROR_CODES) {
        const m = errorText(code, { field:'definition.conditions[1].test.metric.params.length' });
        expect(m.length, code).toBeGreaterThan(20);
        expect(m, code).toMatch(/[.]$/);
        plainWords(m);
      }
    }
  });
});

describe('through the live client (the production path: edge-bff answer -> ApiFailure.message)', () => {
  it("a 422 owner_cpu_budget refusal is worded from the page's catalog, with the wait", async () => {
    const answers = [() => new Response(JSON.stringify({ login:'d', csrf_token:'t' }), { status:200, headers:{ 'Content-Type':'application/json' } }),
      () => new Response(JSON.stringify({ error:{ code:'LIMIT_EXCEEDED', message:'Wait 9 s, or use fewer custom conditions.', details:{ limit:'owner_cpu_budget', allowed:60000, needed:60500, retry_after_seconds:9 } } }), { status:422, headers:{ 'Content-Type':'application/json' } })];
    const f = (async () => answers.shift()!()) as unknown as typeof fetch;
    const e = await liveApi({ fetchImpl:f }).run({ schema_version:1, definition:{} as any }).catch(x => x) as ApiFailure;
    expect(e).toBeInstanceOf(ApiFailure);
    expect(e.code).toBe('LIMIT_EXCEEDED');
    expect(e.message).toBe(`Limit reached: ${limit('owner_cpu_budget').rule}; this one needs 60500 ms per minute. Wait the seconds named, or use fewer custom conditions. Try again in 9 s.`);
  });
});
