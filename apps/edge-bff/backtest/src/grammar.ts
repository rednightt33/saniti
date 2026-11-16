/* EXEC-BACKTEST-REVAMP Stage D (D5; user 2026-11-15 "satu bahasa kondisi bersama", decision 2a; 2026-11-16 "Opsi C"): the
   shared condition grammar on the page. The condition window lists the Screener's catalog (its own entries.ts entriesOf,
   the rows the design's CWDATA was taken from); a row the page's own cards cannot write exactly becomes a card of kind
   'test', the Screener's own card (forms.ts) whose wire condition the worker computes (the page never does: CONTRACT.md
   13.9, tests/worker-only.test.mjs). Whether the Backtest can read a row is derived, never listed here: the backtest
   catalog's grammar_refusals (the worker's reference kinds without a per-day value), its flow_indicators (each Flow
   indicator's availability and reason; the point-in-time ones only in an admin's catalog, edge-bff rights.py) and the
   Screener catalog's own availability of the entry on this publication. Pure: no DOM. */
import type { CatalogResponse } from '../../screener/src/core/contract.ts';
import { entriesOf, type Entry } from '../../screener/src/entries.ts';
import { cardErrors, condText, newCard, toWire as screenerWire, type Card as ScreenerCard } from '../../screener/src/forms.ts';
import { defaultOp, opText } from '../../screener/src/operators.ts';
import type { Condition } from './core/contract.ts';
import { CAT } from './env.ts';
import type { TestCard } from './api/types.ts';

/** the Screener catalog as entries (empty until it answers) */
export const SC: { entries: Entry[]; by: Map<string, Entry>; state: 'loading' | 'ready' | 'failed'; reason: string } =
  { entries: [], by: new Map(), state: 'loading', reason: '' };
export function setScreenerCatalog(cat: CatalogResponse) {
  SC.entries = entriesOf(cat); SC.by = new Map(SC.entries.map(e => [e.key, e])); SC.state = 'ready';
}
export const screenerCatalogFailed = (message: string) => { SC.state = 'failed'; SC.reason = message };

/** the Screener's reference kind of an entry (an indicator entry has none: it is read per bar) */
const kindOf = (e: Entry): string => e.flow ? 'flow' : e.kind === 'indicator' ? 'indicator' : e.metricKind ?? e.kind;

/** Why the Backtest cannot read an entry, from the engine and the catalogs (null: it can). */
export function refusalOf(e: Entry): string | null {
  const refused = CAT?.grammar_refusals?.[kindOf(e)];
  if (refused) return `Not in the backtest: ${refused}.`;
  if (e.flow) {
    const f = (CAT?.flow_indicators ?? []).find(x => x.id === e.key);
    if (!f) return 'Not in the backtest for this account.';
    if (!f.available) return `Not in the backtest: ${f.reason ?? 'the broker data is not available'}.`;
  }
  if (!e.available) return e.reason || 'Not available on the published data.';
  return null;
}

/** a new test card on an entry at its defaults (the Screener's newCard; its id the page's own) */
export function mkTest(e: Entry, id: string): TestCard {
  const sc = newCard(e, []);
  // an entry offered through the catalog's universal operators only (a flow series such as FL01's lots per transaction):
  // its default operator, as the Screener's builder opens it (operators.ts defaultOp)
  if (!e.opts.length && e.ops) sc.op = defaultOp(e.ops, e, undefined, sc.params);
  return { id, type: 'test', on: true, entry: e.key, sc: { ...sc, id } };
}
/** the key a card's choice has in the window when it is an operator (no option of the entry) */
export const OP_CHOICE = '__op';
/** the operator's words (the window's only choice for such an entry) */
export const opWords = (e: Entry, c: TestCard): string => c.sc.op && e.ops ? opText(e.ops, e, c.sc.op, c.sc.params) : 'Operator';
export const entryOf = (c: TestCard): Entry | undefined => SC.by.get(c.entry);

/** the card's wire condition (kind 'test'), as the worker validates it */
export function testWire(c: TestCard): Condition {
  const e = entryOf(c), d = screenerWire(e, { ...c.sc, id: c.id, on: c.on });
  return { id: c.id, kind: 'test', enabled: c.on, test: d.test } as unknown as Condition;
}
/** whether the card can be sent: its entry is known and readable, and its fields are valid (the Screener's own checks) */
export function testReady(c: TestCard): boolean {
  const e = entryOf(c);
  return !!e && !refusalOf(e) && Object.keys(cardErrors(e, c.sc)).length === 0;
}
/** the card's plain name: the entry and its rule in the Screener's words ("RSI (14) greater than 70") */
export function testName(c: TestCard): string {
  const e = entryOf(c);
  return e ? condText(e, c.sc) : 'Condition';
}
/** the card's group in the page's terms (the lanes' colour groups and needsFlow) */
export const testGroup = (c: TestCard): 'tech' | 'flow' | 'price' => {
  const e = entryOf(c);
  return !e ? 'tech' : e.flow || e.group === 'Flow' ? 'flow' : e.group === 'Candlestick' || e.group === 'PriceVolume' ? 'price' : 'tech';
};
export type { Entry, ScreenerCard };
