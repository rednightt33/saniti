/* The page's refusal wording (src/texts.ts errorText; report API CONTRACT 8.8, 8.9; AGENTS.md "Gates and evidence"
   (d)): every code and every limit the worker and edge-bff send the page is worded with where the problem is and how
   to fix it, from the catalog's limits[] (no limit and no number kept in the page), in plain words (no limit name, no
   field path, no code). LIMITS is GET /api/v1/screener/catalog limits[] as the worker (apps/screener-worker/src/
   catalog.ts limitEntries) and edge-bff (app/screener.py own_limits) generate it, copied in tests/page/limits.ts and
   checked against both generators; the tests check that each message is built from its entry, so a change of the
   generated words or values needs no change here. */
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import type { CatalogResponse, LimitEntry } from '../../src/core/contract.ts';
import { ERROR_CODES } from '../../src/core/contract.ts';
import { errorText, failureOn, fieldWords, placeText, savedErrorText } from '../../src/texts.ts';
import { ctx, definitionOf, freshUniverse, S } from '../../src/state.ts';
import { entriesOf } from '../../src/entries.ts';
import { newCard } from '../../src/forms.ts';
import { ScreenerError } from '../../src/core/errors.ts';
import { validateDefinition } from '../../src/core/validate.ts';
import { vctx } from '../core/helpers.ts';
import { fixtureApi } from '../fixture/api.ts';
import { liveApi } from '../../src/api/live.ts';
import { ApiFailure } from '../../src/api/types.ts';
import type { Card } from '../../src/forms.ts';
import type { Entry } from '../../src/entries.ts';
import { L, LIMITS } from './limits.ts';
import { INTERNAL } from './plain-words.ts';

// LIMITS: the catalog's limits[] copy (tests/page/limits.ts; plain-words.test.ts checks it against the generators)
const limit = (name: string) => LIMITS.find(l => l.name === name)!;

/* the page's cards: condition 1 SMA, condition 2 RSI, condition 3 a flow metric, universe filter 1 ADV20 (VWAP: a card of
   another definition, for a saved screen's refusal) */
const P = (key: string, label: string, min: number, max: number) => ({ key, type:'integer', label, default:min, min, max, exclusive_min:false, integer:true, step:1 });
const entry = (key: string, label: string, params: unknown[] = []) => ({ key, kind:'indicator', group:'Trend', label, short:label, desc:'', params, opts:[],
  def:{ opt:'', value:'', value2:'', within:1 }, available:true, availability:'AVAILABLE', reason:null, synonyms:[], history:null }) as unknown as Entry;
const ENUM = (key: string, label: string, options: string[]) => ({ key, type:'enum', label, default:options[0], options, exclusive_min:false });
const ENTRIES = [entry('I01', 'Simple Moving Average', [P('length', 'Length', 1, 567)]), entry('I13', 'Relative Strength Index', [P('length', 'Length', 2, 500)]),
  entry('fnet', 'Foreign net flow'), entry('adv20_idr', 'Average daily value'), entry('I43', 'Volume Weighted Average Price', [ENUM('anchor', 'Anchor', ['Week', 'Month'])])];
const card = (id: string, e: string): Card => ({ id, on:true, entry:e, params:{}, opt:'', value:'', value2:'', within:'', second:{} });

/** what a page message must never show: INTERNAL (tests/page/plain-words.ts: a limit or field name, a code, a contract
    path, an environment variable, a decision, registry, flow or plan id, a wire name, a route, a replica) */
const plainWords = (s: string) => { expect(s, s).not.toMatch(INTERNAL); return s };
/** the page's own words of a message: what is left once the catalog's rules are taken out. A rule is shown as the
    catalog writes it (Method & sources lists the same words); its plain wording is the catalog generators' (worker
    catalog.ts limitEntries, edge-bff screener.py own_limits), not the page's. */
const pageWords = (s: string) => {
  const own = LIMITS.reduce((m, l) => m.split(l.rule).join(''), s);
  plainWords(own);
  // nor the service's own parts (the page speaks of the screener and EDGE, not of where a server keeps its errors)
  expect(own, s).not.toMatch(/\b(?:worker|replica|thread|log|edge-bff|snapshot)\b/i);
  return s;
};

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
    pageWords(m);
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
      .toBe(`Limit reached: ${limit('saved_items').rule}; this one needs 51 saved items. Delete one first.`);
    // the ticker is the request's field, not a place in the screen: the rule says where (the watchlist)
    expect(plainWords(errorText('LIMIT_EXCEEDED', { field:'ticker', details:{ limit:'watchlist', allowed:500, needed:501 } })))
      .toBe(`Limit reached: ${limit('watchlist').rule}; this one needs 501 tickers. Remove one first.`);
    expect(errorText('LIMIT_EXCEEDED', { field:'definition', details:{ limit:'saved_definition_bytes', allowed:65536, needed:70000 } }))
      .toBe(`Limit reached: ${limit('saved_definition_bytes').rule}; this one needs 70,000 bytes. Remove conditions or filters.`);
  });
  it('max_counts and max_response_bytes', () => {
    expect(plainWords(errorText('LIMIT_EXCEEDED', { field:'definitions', details:{ limit:'max_counts', allowed:50, needed:51 } })))
      .toBe(`Limit reached: ${limit('max_counts').rule}; this one needs 51 saved screens. Ask for the rest in a second request.`);
    expect(plainWords(errorText('LIMIT_EXCEEDED', { details:{ limit:'max_response_bytes', allowed:2097152, needed:2500000 } })))
      .toBe(`Limit reached: ${limit('max_response_bytes').rule}; this one needs 2500000 bytes. Narrow the universe or add a condition.`);
  });
  it('every published limit, refused, shows its rule and its fix and never its name', () => {
    for (const l of LIMITS) {
      const m = errorText('LIMIT_EXCEEDED', { details:{ limit:l.name, allowed:l.value, needed:l.value + 1 } });
      expect(m, l.name).toContain(l.rule);
      // what the page adds to the catalog's rule is plain words (the rule's own words are the catalog's)
      pageWords(m);
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
    const m = plainWords(errorText('BUSY', { details:{ limit:'queue', allowed:4 }, server:'The screener is busy: 4 screens are waiting on this server, the most it holds (4). Retry in a few seconds.' }));
    expect(m).toBe(`The screener is busy: ${limit('queue').rule}. Retry in a few seconds.`);
    expect(errorText('BUSY')).toBe(m);                      // run.ts's retry line: no body, the code's limit
    // a wait the answer names in Retry-After is said, as details.retry_after_seconds is
    expect(errorText('BUSY', { retryAfter:3 })).toBe(`${m} Try again in 3 s.`);
  });
  it('TIMEOUT words the deadline rule (its body names no limit)', () => {
    expect(pageWords(errorText('TIMEOUT', { server:'The request took longer than the 20000 ms limit and was stopped after 20003 ms: use fewer custom conditions or shorter lengths.' })))
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
  it('INVALID_CONDITION as the worker sends it: the allowed values in the card\'s words before its message (op codes, registry ids)', () => {
    // validate.ts:252: the message lists op codes, details.allowed the same codes; the page words them as its operator list
    expect(plainWords(errorText('INVALID_CONDITION', { field:'definition.conditions[0].test.op', details:{ allowed:['gt', 'lt', 'between'] },
      server:'definition.conditions[0].test.op must be one of gt, lt, between.' })))
      .toBe('Condition 1 (Simple Moving Average), operator is not valid: use one of greater than, less than, between. Change it and run again.');
    // registry.ts:231 (P17): an option the screener does not offer on a saved screen's card, named with the registry id
    const vwap = [card('v', 'I43')];
    expect(plainWords(errorText('INVALID_CONDITION', { field:'definition.conditions[0].test.rhs.params.anchor', details:{ allowed:['Week', 'Month'] }, cards:vwap,
      server:'definition.conditions[0].test.rhs.params.anchor: "Session" is not offered for I43 VWAP (it is the registry default, taken because anchor was left out); use one of Week, Month.' })))
      .toBe('Condition 1 (Volume Weighted Average Price), Anchor is not valid: use one of Week, Month. Change it and run again.');
    // allowed values that are no card's words (test kinds): the server's reason, its paths in words
    expect(errorText('INVALID_CONDITION', { field:'definition.conditions[1].test.kind', details:{ allowed:['value', 'state', 'event'] }, server:'definition.conditions[1].test.kind must be value, state or event.' }))
      .toBe('Condition 2 (Relative Strength Index), kind must be value, state or event. Change it and run again.');
  });
  it('INVALID_CONDITION without allowed values: the server\'s reason led by the place, then the fix', () => {
    // validate.ts (value test, between); the page refuses this in place before it sends (forms.ts cardErrors), so it
    // arrives only for a definition the page did not build. The reason after the place is the core's own plain words
    const m = plainWords(errorText('INVALID_CONDITION', { field:'definition.conditions[1].test.value2', server:'definition.conditions[1].test.value2 must be at least the lower value (70): "between" includes both bounds, the lower one first, and never swaps them.' }));
    expect(m).toBe('Condition 2 (Relative Strength Index), upper value must be at least the lower value (70): "between" includes both bounds, the lower one first, and never swaps them. Change it and run again.');
  });
  it('INVALID_INPUT: an edge-bff field (the name) and a request the page built', () => {
    expect(errorText('INVALID_INPUT', { field:'name', server:'name is 1 to 120 characters' })).toBe('Name is 1 to 120 characters. Correct it and try again, or reload the page.');
    expect(errorText('INVALID_INPUT', { field:'definition.universe.price_min' })).toBe('The universe, minimum price is not in a form the screener accepts. Correct it and try again, or reload the page.');
  });
  it('INVALID_INPUT of a field the page fills itself: reload, never the server\'s wire names; a field the user edits keeps its reason', () => {
    // the worker's envelope checks (screener-worker run.ts schema/order/version/closed, server.ts parseJson and the
    // ticker check) and edge-bff's (screener.py checked_item, item routes, json_object), as they answer
    const own: [string | undefined, string][] = [
      ['schema_version', 'schema_version must be 1.'],
      ['client_order', 'client_order is {page, seq}: page an id of 1-100 characters A-Z a-z 0-9 . _ : -, seq a whole number from 0.'],
      ['data_version', 'data_version must be the 64-hex price_data of the catalog.'],
      ['options.explain', 'options.explain must be true or false.'],
      ['body', 'The request body is not JSON.'],
      ['ticker', 'XYZ is not a listed stock of this publication; look up a listed ticker instead.'],
      ['definitions[2].item_id', 'definitions[2].item_id scr_1 appears twice.'],
      ['item_id', 'item_id is scr_ followed by 32 lowercase hexadecimal digits'],
      ['kind', 'this item is a metric; an item keeps its kind (save a new item instead)'],
      ['x-screener-owner', 'x-screener-owner must be 16 lowercase hex characters.'],
      [undefined, 'The body is a JSON object.'],
    ];
    const reload = errorText('INVALID_INPUT', { field:'schema_version', server:own[0][1] });
    expect(reload).toMatch(/^This page sent a request the screener does not accept .*Reload the page and try again\.$/);
    for (const [field, server] of own) {
      const m = pageWords(errorText('INVALID_INPUT', { field, server }));
      expect(m, String(field)).toBe(reload);
    }
    // the screen the user builds and the name they type: the reason, its paths in words, and "correct it"
    for (const [field, server] of [['definition.conditions[0].label', 'definition.conditions[0].label is at most 80 characters.'],
      ['definition', 'the definition holds the character U+0000, which cannot be saved; remove it'], ['name', 'name has no control character (line break, tab)'],
      ['definitions[1].definition.universe.tickers[0]', 'definitions[1].definition.universe.tickers[0] is not a ticker.']] as const)
      expect(errorText('INVALID_INPUT', { field, server }), field).toMatch(/\. Correct it and try again, or reload the page\.$/);
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
    // edge-bff main.py `unexpected`: any server error of a screener route, a code and nothing else
    expect(plainWords(errorText('SERVICE_UNAVAILABLE'))).toBe('EDGE could not complete this request because of a server error; retry shortly.');
    expect(errorText('SOMETHING_NEW', { server:'The worker said no.' })).toBe('The worker said no. Retry; if it fails again, reload the page.');
    expect(errorText('')).toBe('The screener could not answer this request. Retry; if it fails again, reload the page.');
  });
  it('every contract code is worded in plain words, with or without a catalog', () => {
    for (const withCatalog of [true, false]) {
      if (!withCatalog) ctx.catalog = null;
      for (const code of [...ERROR_CODES, 'ORIGIN_REJECTED', 'SERVICE_UNAVAILABLE', 'INTERNAL_ERROR']) {
        const m = errorText(code, { field:'definition.conditions[1].test.metric.params.length' });
        expect(m.length, code).toBeGreaterThan(20);
        expect(m, code).toMatch(/[.]$/);
        pageWords(m);
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

describe("a saved screen's counts entry (POST counts) is worded on that screen's own cards", () => {
  /* the real catalog entries (the fixture's, from the generated registry) and the real core refusal under the counts
     request's definitions[k] (apps/screener-worker/src/server.ts /v1/counts: normalize(..., `definitions[${k}].definition`)) */
  const refusal = (fn: () => unknown) => { try { fn() } catch (e) { if (e instanceof ScreenerError) return e.toApi().error; throw e } throw new Error('expected a refusal') };
  it('names the saved screen\'s card (not the page\'s, not its place in the request) and the fix', async () => {
    const cat = (await fixtureApi().catalog(null) as { status: 200; body: CatalogResponse }).body;
    ctx.byKey = new Map(entriesOf(cat).map(e => [e.key, e]));
    const hull = [...ctx.byKey.values()].find(e => e.kind === 'indicator' && /^Hull/.test(e.label))!;
    const cards = [newCard(ctx.byKey.get('I01')!, []), newCard(hull, [], { params:{ length:400 } })];
    const saved = definitionOf({ universe:freshUniverse(), cards, logic:'all', atLeast:2 });
    S.cards = [newCard(ctx.byKey.get('I13')!, []), newCard(ctx.byKey.get('I13')!, [])];     // the page shows another screen
    const e = refusal(() => validateDefinition(saved, vctx([]), 'definitions[3].definition'));
    expect(e.code).toBe('PARAM_OUT_OF_RANGE');
    expect(e.field).toMatch(/^definitions\[3\]\.definition\.conditions\[1\]\.test\.\w+\.params\.length$/);
    const m = plainWords(savedErrorText(e, saved));
    expect(m).toBe(`Condition 2 (${hull.label}), Length is out of range: use a whole number from 1 to ${(e.details as { max: number }).max}. Change it and run again.`);
    // a reason the page takes from the server's message: its definitions[k] path in the same words; a limit's place too
    const f = 'definitions[3].definition.conditions[1].test.kind';
    expect(plainWords(savedErrorText({ code:'INVALID_CONDITION', field:f, message:`${f} must be value, state or event.`, details:{ allowed:['value', 'state', 'event'] } }, saved)))
      .toBe(`Condition 2 (${hull.label}), kind must be value, state or event. Change it and run again.`);
    expect(savedErrorText({ code:'LIMIT_EXCEEDED', field:'definitions[3].definition.conditions[0].test.within', details:{ limit:'within_max', allowed:130, needed:131 } }, saved))
      .toBe(`Limit reached in condition 1 (${ctx.byKey.get('I01')!.label}), within (sessions): ${limit('within_max').rule}; this one needs 131 sessions. Use 130 or fewer.`);
    // its costliest condition (server.ts budgetRefusal) is that screen's card too
    const budget = savedErrorText({ code:'LIMIT_EXCEEDED', message:`This screen is predicted to need 31000 ms of compute, above the 20000 ms budget; the costliest condition is ${cards[1].id}.`,
      details:{ limit:'compute_budget', allowed:20000, needed:31000, costliest:cards[1].id } }, saved);
    expect(budget).toMatch(new RegExp(`The costliest is condition 2 \\(${hull.label}\\)\\.$`));
    // without the definition (an item the list no longer holds): the card's number, never the page's card of that number
    expect(plainWords(savedErrorText({ code:'METRIC_UNAVAILABLE', field:'definitions[0].definition.conditions[0].test.metric', details:{ metric:'roe', reason:'No data yet.' } }, null)))
      .toBe(`Condition 1: ${ctx.byKey.get('roe')!.label} is not available yet: No data yet. Switch it off or remove it to run the screen.`);
  });
});

describe('a request that carried another definition than the page shows', () => {
  const refusal = (fn: () => unknown) => { try { fn() } catch (e) { if (e instanceof ScreenerError) return e.toApi().error; throw e } throw new Error('expected a refusal') };
  const answering = (status: number, body: unknown, headers: Record<string, string> = {}) => {
    const answers = [() => new Response(JSON.stringify({ login:'d', csrf_token:'t' }), { status:200 }),
      () => new Response(JSON.stringify(body), { status, headers:{ 'Content-Type':'application/json', ...headers } })];
    return liveApi({ fetchImpl:(async () => answers.shift()!()) as unknown as typeof fetch });
  };
  it('a saved screen duplicated (PUT items, validated again by edge-bff) is worded on the copy\'s cards, not the page\'s', async () => {
    const cat = (await fixtureApi().catalog(null) as { status: 200; body: CatalogResponse }).body;
    ctx.byKey = new Map(entriesOf(cat).map(e => [e.key, e]));
    const hull = [...ctx.byKey.values()].find(e => e.kind === 'indicator' && /^Hull/.test(e.label))!;
    const saved = definitionOf({ universe:freshUniverse(), cards:[newCard(ctx.byKey.get('I01')!, []), newCard(hull, [], { params:{ length:400 } })], logic:'all', atLeast:2 });
    S.cards = [newCard(ctx.byKey.get('I13')!, []), newCard(ctx.byKey.get('I13')!, [])];     // the page shows another screen
    // edge-bff validated(): /v1/validate of the screen's own definition, its 422 relayed as the worker gave it
    const wire = refusal(() => validateDefinition(saved, vctx([])));
    const e = await answering(422, { error:wire }).putItem('scr_' + '0'.repeat(32), { kind:'screen', name:'copy', definition:{ definition:saved } }).catch(x => x) as ApiFailure;
    expect(e.wire).toEqual(wire);
    expect(e.message).toMatch(/^Condition 2 \(Relative Strength Index\)/);         // the page's card 2: why the caller re-words
    expect(plainWords(failureOn(e, saved))).toBe(`Condition 2 (${hull.label}), Length is out of range: use a whole number from 1 to ${(wire.details as { max: number }).max}. Change it and run again.`);
    // a failure without a contract body keeps its message; a wait the answer names is kept
    const signIn = await answering(401, { detail:'Not signed in' }).putItem('scr_' + '1'.repeat(32), { kind:'screen', name:'copy', definition:{ definition:saved } }).catch(x => x) as ApiFailure;
    expect(failureOn(signIn, saved)).toBe(signIn.message);
    const later = await answering(503, { error:{ code:'SCREENER_NOT_READY', message:'The screener tables are not installed yet; retry after the stated seconds.' } }, { 'Retry-After':'7' })
      .putItem('scr_' + '2'.repeat(32), { kind:'screen', name:'copy', definition:{ definition:saved } }).catch(x => x) as ApiFailure;
    expect(failureOn(later, saved)).toBe('The screener is starting or loading new data; retry in 7 s.');
    expect(failureOn(new Error('boom'), saved)).toBe('Error: boom');
  });
  it("a counts entry's unexpected error (the worker thread's INTERNAL_ERROR, relayed inside the 200 answer) is the page's words", () => {
    const m = pageWords(savedErrorText({ code:'INTERNAL_ERROR', message:'The worker failed; the error is in its log.' }, null));
    expect(m).toBe(errorText('SERVICE_UNAVAILABLE'));
  });
});
