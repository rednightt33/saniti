/* EXEC-WATCHLIST L5: what the page arranges from the daily file and the account's lists, with no figure of its own (the
   publisher's watchlist-stocks holds every value as stored; WATCHLIST_FORMULAS.md). Pure functions, tested in
   tests/model.test.ts: labels and number formats, the indicators the file's catalog offers, a list's indicators, the
   filters, the badges, the search and the bodies that undo a deletion. */
import type { CatalogItem, CreateBody, EventRow, Limit, StocksFile, WList } from './types.ts';

export const NB = ' ', MINUS = '−', DOT = ' · ';
/** the card shows the first CARD_IND indicators of a list; the table shows all (the design's) */
export const CARD_IND = 4;

/* ---------- dates ---------- */
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const WD = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
/** "13 Nov", or "Fri 13 Nov" with the weekday; no-break spaces, so a date never splits */
export function dateLabel(iso: string | null | undefined, wd = false): string {
  if (!iso) return '—';
  const d = new Date(iso + 'T00:00:00Z');
  return (wd ? WD[d.getUTCDay()] + NB : '') + d.getUTCDate() + NB + MON[d.getUTCMonth()];
}

/* ---------- numbers ---------- */
export const sgn = (v: number) => (v > 0 ? '+' : v < 0 ? MINUS : '');
export const cls = (v: number | null | undefined) => (v == null ? '' : v > 0 ? 'up' : v < 0 ? 'down' : '');
/** a percentage with its sign: "+1.66%", "−0.21%", "0.00%" (the sign of the rounded value) */
export function fPct(v: number | null | undefined, d = 2): string | null {
  return v == null ? null : sgn(+v.toFixed(d)) + Math.abs(v).toFixed(d) + '%';
}
export const fPx = (v: number | null | undefined) => (v == null ? null : Math.round(v).toLocaleString('en-US'));
/** rupiah with M/B/T: "+Rp 13.7B", "−Rp 416.9B", "Rp 0" below a million (the mockup's fRp) */
export function fRp(v: number | null | undefined): string | null {
  if (v == null) return null;
  const a = Math.abs(v);
  const [n, u] = a >= 1e12 ? [a / 1e12, 'T'] : a >= 1e9 ? [a / 1e9, 'B'] : a >= 1e6 ? [a / 1e6, 'M'] : [0, ''];
  if (!u || n.toFixed(1) === '0.0') return 'Rp' + NB + '0';
  return sgn(v) + 'Rp' + NB + n.toFixed(1) + u;
}
/* 1 decimal; 2 below 1 (a MACD histogram of a low-priced stock, 0.04) so a small value does not read as 0.0 */
const plain = (v: number) => { const d = Math.abs(v) < 1 ? 2 : 1; return (+v.toFixed(d) < 0 ? MINUS : '') + Math.abs(v).toFixed(d) };
/** one indicator value by its catalog unit: index 1 decimal, pct with its sign (a "+" only where the catalog colours the
    sign), ratio "0.6×", rp as fRp, rank "P83"; price (the MACD histogram) 1 decimal */
export function formatValue(item: CatalogItem, v: number | null | undefined): string | null {
  if (v == null || !Number.isFinite(v)) return null;
  switch (item.unit) {
    case 'pct': return item.signed ? fPct(v, 1) : (+v.toFixed(1) < 0 ? MINUS : '') + Math.abs(v).toFixed(1) + '%';
    case 'ratio': return v.toFixed(1) + '×';
    case 'rp': return fRp(v);
    case 'rank': return 'P' + Math.round(v);
    default: return plain(v);
  }
}

/* ---------- the catalog: the page offers exactly the file's indicators ---------- */
export interface Catalog { items: CatalogItem[]; by: Record<string, CatalogItem>; families: [string, CatalogItem[]][]; def: string[] }
export function catalog(f: Pick<StocksFile, 'catalog' | 'default'>): Catalog {
  const by: Record<string, CatalogItem> = {}, fam = new Map<string, CatalogItem[]>();
  for (const c of f.catalog || []) {
    if (!c || typeof c.key !== 'string' || by[c.key]) continue;
    by[c.key] = c;
    if (!fam.has(c.family)) fam.set(c.family, []);
    fam.get(c.family)!.push(c);
  }
  const items = Object.values(by);
  let def = (f.default || []).filter(k => by[k]);
  if (!def.length) def = items.slice(0, CARD_IND).map(c => c.key);
  return { items, by, families: [...fam.entries()], def };
}
/** a list's indicators as shown: its own choice (null = the file's default), keys the catalog does not hold skipped, at
    most `max`; a choice left with none shows the default */
export function indicatorsOf(l: Pick<WList, 'indicators'>, cat: Catalog, max = Infinity): string[] {
  const own = [...new Set((l.indicators || []).filter(k => cat.by[k]))];
  return (own.length ? own : cat.def).slice(0, max);
}
export const brokerDated = (c: CatalogItem) => c.date === 'broker';
export const flowPill = (c: CatalogItem) => c.family === 'Foreign flow' && c.signed;   // the table's solid green/red pill

/* ---------- the limits edge-bff publishes with the lists (GET /lists `limits`) ---------- */
export interface Limits { lists: number; tickers: number; indicators: number; name: number }
export function limitsOf(ls: Limit[] | undefined): Limits {
  const v = (n: string) => { const x = (ls || []).find(l => l && l.name === n)?.value; return typeof x === 'number' && x > 0 ? x : Infinity };
  return { lists: v('lists'), tickers: v('tickers'), indicators: v('indicators'), name: v('name') };
}

/* ---------- stocks ---------- */
export interface Stock {
  t: string; n: string; sec: string; known: boolean; last: number | null; r1d: number | null; r1m: number | null;
  trend: (number | null)[]; ev: EventRow[]; rd: string[]; i: number;
}
export function stocks(f: StocksFile): Map<string, Stock> {
  const m = new Map<string, Stock>();
  f.ticker.forEach((t, i) => m.set(t, {
    t, n: f.name[i] || '', sec: f.sector[i] || '', known: true, last: f.last[i] ?? null, r1d: f.r1d[i] ?? null,
    r1m: f.r1m[i] ?? null, trend: f.trend[i] || [], ev: f.events[t] || [], rd: f.radar[t] || [], i,
  }));
  return m;
}
/** a list's stock that today's file does not hold (no longer a listed common stock): shown without values */
export const unknownStock = (t: string): Stock => ({ t, n: 'Not in today’s data', sec: '', known: false, last: null, r1d: null, r1m: null, trend: [], ev: [], rd: [], i: -1 });
export function value(f: StocksFile, key: string, s: Stock): number | null {
  return s.i < 0 ? null : f.values[key]?.[s.i] ?? null;
}
export function indVal(f: StocksFile, item: CatalogItem, s: Stock | null): { v: string; k: string; na: boolean } {
  const x = s ? value(f, item.key, s) : null, v = formatValue(item, x);
  // the colour follows what is shown: a value that reads as zero ("0.0%", "Rp 0") is not coloured (review 2026-11-16)
  return v == null ? { v: '—', k: '', na: true } : { v, k: item.signed && /[1-9]/.test(v) ? cls(x) : '', na: false };
}
export const tickersOf = (l: Pick<WList, 'tickers'>) => l.tickers.map(x => x.ticker);

/* ---------- badges ---------- */
export const EVN: Record<string, string> = { RUPS: 'RUPS', PUBLIC_EXPOSE: 'Public expose', DIVIDEND: 'Dividend', RIGHT_ISSUE: 'Rights issue', STOCK_SPLIT: 'Stock split', REVERSE_SPLIT: 'Reverse split', WARRANT: 'Warrant', BONUS: 'Bonus shares', TENDER_OFFER: 'Tender offer' };
/** "RUPS", "Dividend cum", "Dividend ex"; a type the map does not know reads as its words ("CASH_OFFER" -> "Cash offer") */
export function evName([a, , role]: EventRow): string {
  const w = (role || '').split('_');                   // CUM_DATE, EX_DATE; EXPOSE_DATE is not an ex date
  return (EVN[a] || a.charAt(0) + a.slice(1).toLowerCase().replace(/_/g, ' ')) + (w.includes('CUM') ? ' cum' : w.includes('EX') ? ' ex' : '');
}
export const evLabel = (e: EventRow) => `${evName(e)} ${dateLabel(e[1])}`;
/** the event badge: the first action, "+n" for the others, and every one in its title */
export function eventBadge(s: Stock): { label: string; more: number; all: string[] } | null {
  if (!s.ev.length) return null;
  return { label: evLabel(s.ev[0]), more: s.ev.length - 1, all: s.ev.map(evLabel) };
}
/** the Radar badge: "Radar S2 S7" on a card, "2 Radar" in the table */
export function radarBadge(s: Stock, compact: boolean): string | null {
  if (!s.rd.length) return null;
  return compact ? `${s.rd.length} Radar` : 'Radar ' + s.rd.join(' ');
}
export const radarNames = (f: StocksFile): Record<string, string> => Object.fromEntries((f.radar_filters || []).map(x => [x.label, x.name]));

/* ---------- filters of the open list (view only: the list does not change) ---------- */
export interface Filter { radar: boolean; ev: boolean }
export const passes = (s: Stock, fl: Filter) => (!fl.radar || s.rd.length > 0) && (!fl.ev || s.ev.length > 0);

/* ---------- the table's sorting (view only) ---------- */
export interface Sort { k: string; dir: 1 | -1; label: string }
export function sortStocks(ss: Stock[], sort: Sort | null, f: StocksFile): Stock[] {
  if (!sort) return ss;
  const a = [...ss];
  if (sort.k === 't') return a.sort((x, y) => sort.dir * x.t.localeCompare(y.t));
  const get = (s: Stock) => (sort.k === 'last' ? s.last : sort.k === 'r1d' ? s.r1d : sort.k === 'r1m' ? s.r1m : value(f, sort.k, s));
  return a.sort((x, y) => {
    const p = get(x), q = get(y);
    if (p == null && q == null) return 0;
    if (p == null) return 1;
    if (q == null) return -1;
    return sort.dir * (p - q);
  });
}
/** a header click: a first click sorts (Stock A→Z, figures high→low), a second turns it, a third goes back to list order */
export function nextSort(cur: Sort | null, k: string, label: string): Sort | null {
  const first = k === 't' ? 1 : -1;
  if (!cur || cur.k !== k) return { k, dir: first, label };
  return cur.dir === first ? { k, dir: -first as 1 | -1, label } : null;
}

/* ---------- the trend line (the newest closes) ---------- */
export function spark(trend: (number | null)[], w: number, h: number, fluid = false): string | null {
  const a = trend.filter((v): v is number => v != null);
  if (a.length < 2) return null;
  const lo = Math.min(...a), hi = Math.max(...a);
  const y = (v: number) => (2 + (hi - v) / (hi - lo || 1) * (h - 4)).toFixed(1), x = (i: number) => (i / (a.length - 1) * w).toFixed(1);
  const col = a[a.length - 1] >= a[0] ? 'var(--up)' : 'var(--down)';
  return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" style="width:${fluid ? '100%' : w + 'px'}" aria-hidden="true"><polyline fill="none" stroke="${col}" stroke-width="1.5" vector-effect="non-scaling-stroke" points="${a.map((v, i) => x(i) + ',' + y(v)).join(' ')}"/></svg>`;
}

/* ---------- adding stocks ---------- */
export const parseCodes = (q: string) => [...new Set(q.toUpperCase().split(/[\s,;]+/).filter(Boolean))];
export const isMulti = (q: string) => /[,;]/.test(q) || parseCodes(q).length > 1;
/** the stocks a search finds: codes that start with it first, then names that hold it; several codes: each known one */
export function search(all: Stock[], by: Map<string, Stock>, q: string): Stock[] {
  const u = q.trim().toUpperCase();
  if (!u) return [];
  if (isMulti(q)) return parseCodes(q).filter(c => by.has(c)).map(c => by.get(c)!);
  return all.filter(s => s.t.startsWith(u) || s.n.toUpperCase().includes(u))
    .sort((a, b) => (+b.t.startsWith(u) - +a.t.startsWith(u)) || a.t.localeCompare(b.t));
}
/** suggestions for a list: the stocks of the account's other lists it does not hold, then today's Radar stocks */
export function suggestions(lists: WList[], target: WList, by: Map<string, Stock>, f: StocksFile, n = 4): string[] {
  const have = new Set(tickersOf(target)), out: string[] = [];
  const push = (t: string) => { if (!have.has(t) && !out.includes(t) && by.has(t)) out.push(t) };
  for (const l of lists) if (l.id !== target.id) tickersOf(l).forEach(push);
  Object.entries(f.radar || {}).sort((a, b) => b[1].length - a[1].length || a[0].localeCompare(b[0])).forEach(([t]) => push(t));
  return out.slice(0, n);
}
export const dupName = (lists: WList[], name: string, except?: string) =>
  lists.some(l => l.id !== except && l.name.toLowerCase() === name.trim().toLowerCase());

/* ---------- undo ---------- */
/** Undo of a deleted list: the list again, with its name, stocks in their order, indicators and place */
export function restoreListBody(snap: WList): CreateBody {
  return { name: snap.name, tickers: tickersOf(snap), indicators: snap.indicators, position: snap.position };
}
/** Undo of a removed stock: back at its old place in the list */
export function restoreTickerBody(l: WList, t: string): { tickers: string[]; position: number } | null {
  const x = l.tickers.find(y => y.ticker === t);
  return x ? { tickers: [t], position: x.position } : null;
}
