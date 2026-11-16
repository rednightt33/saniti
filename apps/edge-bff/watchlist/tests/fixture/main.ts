/* EXEC-WATCHLIST L5, fixture build only (vite --mode fixture): the page on a small made-up watchlist-stocks file
   (watchlist-stocks.sample.json: invented companies and values in the publisher's shape) and an in-memory list store
   that answers as edge-bff's /api/v1/watchlist/lists does (limits, refusals and their messages), for the look check.
   A local look check may put a file built from a rehearsal database in data/ (never committed: market data):
   data/watchlist-stocks.json, data/lists.json ({name: [tickers]}) and data/logos/<TICKER>.png.
   Never part of the production bundle (tests/bundle.test.mjs). ?theme=dark, ?empty=1 (a first visit: no list). */
import '../../src/styles/watchlist.css';
import { start } from '../../src/app.ts';
import { WatchlistError } from '../../src/api.ts';
import type { CreateBody, Limit, StocksFile, WList, WatchlistApi } from '../../src/types.ts';
import sample from './watchlist-stocks.sample.json';

const saved = import.meta.glob('./data/*.json', { eager: true, import: 'default' }) as Record<string, any>;
const pngs = import.meta.glob('./data/logos/*.png', { eager: true, query: '?url', import: 'default' }) as Record<string, string>;
const file = (saved['./data/watchlist-stocks.json'] || sample) as StocksFile;
const real = !!saved['./data/watchlist-stocks.json'];
const p = new URLSearchParams(location.search);
if (p.get('theme') === 'dark') { document.documentElement.dataset.theme = 'dark'; document.documentElement.classList.add('dark') }

/* logos: the saved PNGs, or three drawn marks for the made-up file (the other stocks show their monogram) */
const mark = (c: string, d: string) => 'data:image/svg+xml,' + encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 28 28"><circle cx="14" cy="14" r="14" fill="${c}"/><path d="${d}" fill="#fff"/></svg>`);
const LOGO: Record<string, string> = real
  ? Object.fromEntries(Object.entries(pngs).map(([k, v]) => [k.split('/').pop()!.replace('.png', ''), v]))
  : { ALFQ: mark('#0b5394', 'M8 19l6-11 6 11z'), BETQ: mark('#b45309', 'M8 8h12v4H8zM8 15h12v4H8z'), INTQ: mark('#087f5b', 'M14 7a7 7 0 1 0 .01 0zM14 11a3 3 0 1 1-.01 0z') };

const LIMITS: Limit[] = [
  { name: 'lists', value: 20, unit: 'lists', rule: 'at most 20 lists', example_ok: '', example_refused: '' },
  { name: 'tickers', value: 50, unit: 'stocks', rule: 'at most 50 stocks in one list', example_ok: '', example_refused: '' },
  { name: 'indicators', value: 8, unit: 'indicators', rule: '1 to 8 indicators per list', example_ok: '', example_refused: '' },
  { name: 'name', value: 40, unit: 'characters', rule: 'a list name has 1 to 40 characters', example_ok: '', example_refused: '' },
];
const lim = (n: string) => LIMITS.find(l => l.name === n)!.value;
const SEEDED: Record<string, string[]> = saved['./data/lists.json'] || {
  Core: ['ALFQ', 'BETQ', 'CAKQ', 'DELQ', 'EKAQ', 'FAJQ', 'GALQ', 'HARQ', 'INTQ', 'NUSQ'],
  Banks: ['BETQ', 'NUSQ'], Commodities: ['ALFQ', 'CAKQ', 'INTQ', 'LOKQ'],
};
let seq = 0;
const now = () => new Date(Date.UTC(2026, 10, 16, 8, 0, seq++)).toISOString();
const uid = () => `00000000-0000-4000-8000-${String(++seq).padStart(12, '0')}`;
const mk = (name: string, position: number, tickers: string[], indicators: string[] | null = null): WList =>
  ({ id: uid(), name, position, indicators, tickers: tickers.map((ticker, i) => ({ ticker, position: i })), created_at: now(), updated_at: now() });
let db: WList[] = p.get('empty') ? [] : Object.entries(SEEDED).map(([n, ts], i) => mk(n, i, ts));

const copy = <T>(x: T): T => JSON.parse(JSON.stringify(x));
const wait = <T>(v: T) => new Promise<T>(r => setTimeout(() => r(copy(v)), 40));
const order = () => db.sort((a, b) => a.position - b.position || String(a.created_at).localeCompare(String(b.created_at)));
const one = (id: string) => { const l = db.find(x => x.id === id); if (!l) throw new WatchlistError('NOT_FOUND', 'This list no longer exists; reload the page.', 404); return l };
const taken = (name: string, except?: string) => db.some(l => l.id !== except && l.name.toLowerCase() === name.toLowerCase());
const over = (msg: string) => new WatchlistError('LIMIT_EXCEEDED', msg, 422);

const api: WatchlistApi = {
  // ?fail=index or ?fail=file: the figures cannot be read (M466 (a): the lists must still be shown)
  index: async () => {
    if (new URLSearchParams(location.search).get('fail') === 'index') throw new WatchlistError('WATCHLIST_UNAVAILABLE', 'The Terminal data service did not answer. Try again in a minute.', 503);
    return { finished_at: 'fixture', files: { 'watchlist-stocks': { sha256: 'f'.repeat(64), bytes: 0, rows: file.ticker.length, as_of: file.prices_through } } };
  },
  file: async <T>() => {
    if (new URLSearchParams(location.search).get('fail') === 'file') throw new WatchlistError('WATCHLIST_FILE_NOT_PUBLISHED', 'The watchlist figures are not published yet. They come with the next daily publication; try again later.', 404);
    return wait(file as unknown as T);
  },
  lists: async () => wait({ lists: order(), limits: LIMITS }),
  async create(b: CreateBody) {
    const name = (b.name || '').trim();
    if (db.length >= lim('lists')) throw over(`At most ${lim('lists')} lists: you have ${db.length}. Delete one first.`);
    if (taken(name)) throw new WatchlistError('NAME_TAKEN', 'Another list already has this name. Pick another name.', 409, 'name');
    if (b.position != null) db.forEach(x => { if (x.position >= b.position!) x.position += 1 });   // as the server: Undo's place
    const l = mk(name, b.position ?? Math.max(-1, ...db.map(x => x.position)) + 1, [...new Set(b.tickers || [])], b.indicators ?? null);
    db.push(l); order(); return wait(l);
  },
  async rename(id, name) {
    const l = one(id);
    if (taken(name, id)) throw new WatchlistError('NAME_TAKEN', 'Another list already has this name. Pick another name.', 409, 'name');
    l.name = name; l.updated_at = now(); return wait(l);
  },
  async setIndicators(id, indicators) { const l = one(id); l.indicators = indicators; return wait(l) },
  async setIndicatorsAll(indicators) { db.forEach(l => (l.indicators = indicators)); return wait(order()) },
  async remove(id) {
    const gone = one(id);
    if (db.length <= 1) throw new WatchlistError('LAST_LIST', 'The last list cannot be deleted. Create another list first.', 409);
    db = db.filter(l => l.id !== id); return wait(JSON.parse(JSON.stringify(gone)));
  },
  async addTickers(id, tickers, position) {
    const l = one(id), known = new Set(l.tickers.map(x => x.ticker)), add = tickers.filter(t => !known.has(t));
    if (l.tickers.length + add.length > lim('tickers'))
      throw over(`At most ${lim('tickers')} stocks in one list: it has ${l.tickers.length}, these would make ${l.tickers.length + add.length}. Remove some or use another list.`);
    const s = position ?? Math.max(-1, ...l.tickers.map(x => x.position)) + 1;
    add.forEach((ticker, i) => l.tickers.push({ ticker, position: s + i }));
    l.tickers.sort((a, b) => a.position - b.position);
    return wait({ added: add, already: tickers.filter(t => known.has(t)), list: l });
  },
  async removeTicker(id, t) { const l = one(id); l.tickers = l.tickers.filter(x => x.ticker !== t); await wait(0) },
  logos: async () => Object.fromEntries(Object.keys(LOGO).map(t => [t, 'fixture'])),
  logoSrc: t => LOGO[t] || `/no-logo/${t}.png`,
};
void start(api, document.getElementById('page') as HTMLElement).boot();
