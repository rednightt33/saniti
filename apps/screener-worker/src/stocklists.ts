/* EXEC-SCREENER-STOCK-LISTS (user 2026-11-09: options 1A, 2, 3): the indices and stock groups (KONGLO) of the reference
   file `stock_lists` for the Screener's universe filters indices_* and groups_* (core universe.ts, validate.ts).

   The file (terminal-publisher publisher.py stock_lists_doc, STOCK_LIST_COLUMNS): columnar JSON with the columns
   list_key, kind ('INDEX' | 'KONGLO'), code, name, definition, as_of (ISO time of the last complete stockbit-updater
   round, or null) and members (the current tickers; they may be outside the Screener's universe or not stocks),
   indexed in state.json refs. The refresh reads it as it reads `brokers` (refresh.ts stockLists: terminal-api
   /reference/stock_lists, sha256 and size checked by TerminalClient.file, a URL on the bucket origin); this module checks
   its shape (parseStockLists) and, at the build, restricts the members to the snapshot's listed stocks (stockListsOf):
   each universe row gets the codes of its lists (row.indices, row.groups) and the catalog block counts the listed stocks
   per list. A file that is missing, not indexed or broken never stops the Screener: the block is REQUIRES_DATA with a
   plain reason, a list filter is refused METRIC_UNAVAILABLE naming it, everything else runs as before.
   Pure module (no I/O). */
import type { StockListEntry, StockListKind, StockListsBlock, UniverseRow } from '../../edge-bff/screener/src/core/contract.ts';
import { STOCK_LIST_KINDS } from '../../edge-bff/screener/src/core/contract.ts';

/** The columns the publisher writes (publisher.py STOCK_LIST_COLUMNS); a file without one of them is broken. */
export const STOCK_LIST_COLUMNS = ['list_key', 'kind', 'code', 'name', 'definition', 'as_of', 'members'] as const;
/** One list as the file holds it (members as published). */
export interface StockListDoc { key: string; kind: StockListKind; code: string; name: string; definition: string; as_of: string | null; members: string[] }
/** The file as the refresh read it: its lists and sha256 (its content key: a change is another snapshot), or the plain
    reason it is not available (the page and the refusal show it as it is). */
export type StockListsRef = { sha256: string; lists: StockListDoc[] } | { reason: string };

/** The plain reasons (no file, key or code name: they reach the page as they are, tests/page/plain-words.test.ts). */
export const STOCK_LISTS_REASONS = {
  not_indexed: 'This publication carries no index and group lists.',
  unreadable: 'The index and group lists of this publication could not be read; the next publication tries again.',
} as const;

/** Thrown by parseStockLists for a file the publisher cannot have written; the refresh logs `why` and serves the lists
    as unavailable. */
export class StockListsBroken extends Error { constructor(why: string) { super(why); this.name = 'StockListsBroken' } }

const TEXT = (v: unknown): v is string => typeof v === 'string' && v.trim() !== '';
const TICKER = /^[A-Z0-9][A-Z0-9-]{0,15}$/;            // Stock_List_Member_ticker_check (migration 20261109_001)
/** The file's lists, checked: every column present with one value per list, a kind of STOCK_LIST_KINDS, a non-empty
    key, code, name and definition, a code that appears once within its kind (the value a filter names), as_of a text or
    null, members a list of distinct tickers. The first problem throws StockListsBroken. */
export function parseStockLists(doc: Record<string, unknown>): StockListDoc[] {
  if (!doc || !Array.isArray(doc.columns)) throw new StockListsBroken('not a columnar document');
  const cols = STOCK_LIST_COLUMNS.map(c => {
    const v = doc[c];
    if (!(doc.columns as unknown[]).includes(c) || !Array.isArray(v)) throw new StockListsBroken(`column ${c} is missing`);
    return v as unknown[];
  });
  const n = cols[0].length;
  if (cols.some(c => c.length !== n)) throw new StockListsBroken('the columns differ in length');
  const out: StockListDoc[] = [], keys = new Set<string>(), codes = new Set<string>();
  for (let i = 0; i < n; i++) {
    const [key, kind, code, name, definition, as_of, members] = cols.map(c => c[i]);
    const at = `list ${i + 1}`;
    if (!TEXT(key) || keys.has(key)) throw new StockListsBroken(`${at} has no key, or one used twice`);
    if (!STOCK_LIST_KINDS.includes(kind as StockListKind)) throw new StockListsBroken(`${at} has the kind ${JSON.stringify(kind)}`);
    if (!TEXT(code) || !TEXT(name) || !TEXT(definition)) throw new StockListsBroken(`${at} has no code, name or definition`);
    if (codes.has(`${kind}:${code}`)) throw new StockListsBroken(`${at}: the code ${code} is used twice for ${String(kind)}`);
    if (as_of !== null && !(typeof as_of === 'string' && !Number.isNaN(Date.parse(as_of)))) throw new StockListsBroken(`${at} has an as_of that is not a time`);
    if (!Array.isArray(members) || members.some(t => typeof t !== 'string' || !TICKER.test(t)) || new Set(members).size !== members.length)
      throw new StockListsBroken(`${at} has members that are not distinct tickers`);
    keys.add(key); codes.add(`${kind}:${code}`);
    out.push({ key, kind: kind as StockListKind, code, name, definition, as_of: as_of as string | null, members: [...members as string[]] });
  }
  return out;
}

/** The lists restricted to the snapshot's listed stocks (`rows`, the universe rows; changed in place): each row gets
    indices and groups, the codes of the lists of that kind it is a current member of, in the file's order (none: an
    empty array); the block counts the listed stocks per list. Members outside the rows (not in the Screener's universe,
    not a stock, no price) are not counted and never appear. Without a readable file the rows carry nothing and the
    block is REQUIRES_DATA with its reason. */
export function stockListsOf(ref: StockListsRef | undefined, rows: UniverseRow[]): StockListsBlock {
  if (!ref || 'reason' in ref) return { availability: 'REQUIRES_DATA', reason: ref && 'reason' in ref ? ref.reason : STOCK_LISTS_REASONS.not_indexed, as_of: null, lists: [] };
  const at = new Map(rows.map(r => [r.ticker, r]));
  for (const r of rows) { r.indices = []; r.groups = [] }
  const lists: StockListEntry[] = [];
  let newest: string | null = null;
  for (const l of ref.lists) {
    let n = 0;
    for (const t of l.members) {
      const r = at.get(t);
      if (!r) continue;
      (l.kind === 'INDEX' ? r.indices! : r.groups!).push(l.code); n++;
    }
    lists.push({ key: l.key, kind: l.kind, code: l.code, name: l.name, definition: l.definition, tickers: n, as_of: l.as_of });
    if (l.as_of !== null && (newest === null || Date.parse(l.as_of) > Date.parse(newest))) newest = l.as_of;
  }
  return { availability: 'AVAILABLE', reason: null, as_of: newest, lists };
}
