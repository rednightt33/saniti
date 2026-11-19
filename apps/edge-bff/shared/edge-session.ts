/* EXEC-MU-ACCOUNTS Phase 0 (verification/edge_multiuser/access_tiers/CONTRACT.md sections 3 and 12): the one session
   module of EDGE. The six Vite pages import it from here (apps/edge-bff/shared, copied beside each page in the
   Dockerfile); the shell loads the same code as /edge-session.js (static/edge-session.js, built from this file by
   shared/build-shell.mjs; tests/test_storage_registry.py fails when the two differ).

   It owns:
   - the error contract: every refusal is {"error":{"code","message","details"}}; during the rollout the old FastAPI
     {"detail": "..."} of a 401 or 403 is read the same way (M471);
   - the session call and CSRF: a write carries the token; only a 403 CSRF_INVALID reads the session again and repeats
     the write once; a 401 is the only answer that means "signed out"; any other 403 (a plan or capability refusal) keeps
     the session and is shown as a message (M471);
   - the storage registry: every localStorage, sessionStorage and IndexedDB key of the shell and the six pages, classed
     `browser` (how this browser shows EDGE: theme, widths, folds) or `user` (anything that belongs to an account);
     clearUserState() removes the `user` ones on sign-out and when another login signs in on this browser (M473).
     tests/test_storage_registry.py fails on a key found in the code that is not classed here;
   - what the account holds (Phase 2, contract 8a): access(), can(key) and limit(key) mirror the server from the session
     answer's `access`; catalog(kind) reads GET /api/v1/catalog/{kind}, kept in memory only (no storage key);
   - the guest (track guest, decision 1 of 2026-11-19 "1a"): a page that a visitor without an account may open (the
     Terminal) calls allowGuest(); its session read then answers a 401 with GET /api/v1/auth/guest, the guest plan's
     access (`guest` true, no login, no CSRF token), and access(), can(), limit() and catalog() read it like an account's.
     A visitor is never a user of this browser's storage: no last-login mark, no clean-up; a visitor who signs in, or an
     account whose session ended, reloads the page as the other.

   No figure, no market data and no wording of the pages lives here; the messages below are only the fallbacks for the
   session refusals when the server sends none (the server's own `message` is shown first). */

/* ---- the storage registry ------------------------------------------------------------------------------------ */

export type StorageKind = 'browser' | 'user';
export type StorageArea = 'local' | 'session' | 'idb';
export interface StorageEntry {
  key: string;                       // the key, or the start of the keys when match is 'prefix'
  match: 'exact' | 'prefix';
  area: StorageArea;                 // localStorage, sessionStorage, or an IndexedDB database name
  kind: StorageKind;
  /* a `user` key is one of two (tests/test_storage_registry.py): `sync` (a preference or saved item, copied to the
     account, contract 4b: GET/PUT /api/v1/preferences) or `cache` (the account holds the original elsewhere, or it is
     transient: offline copies, pointers, caches, legacy keys) */
  sync?: true;
  cache?: true;
  /* a `sync` key holding one tab's data: the capability (that tab's view) the account must hold for the server to
     serve or store it (re-check R1-18, CONTRACT.md 8b D5: reads need <tab>.view). None for a key every tab shares.
     shared/build-shell.mjs writes these to catalog/storage_sync.json, which app/preferences.py reads. */
  cap?: string;
  where: string;                     // who writes it
  what: string;                      // what it holds, in plain words
}

/* One entry per line (the test reads this table line by line): { key, match, area, kind, sync|cache, cap?, where, what }. */
export const STORAGE: readonly StorageEntry[] = Object.freeze([
  // the shell (static/index.html, static/edge-client.js)
  { key:'edge-auth-monitor-theme', match:'exact', area:'local', kind:'browser', where:'shell, all pages', what:'light or dark theme' },
  { key:'edge-monitor-collapsed', match:'exact', area:'local', kind:'browser', where:'shell', what:'Monitor sidebar folded' },
  { key:'edge-monitor-width', match:'exact', area:'local', kind:'browser', where:'shell', what:'Monitor sidebar width' },
  { key:'edge-details-width', match:'exact', area:'local', kind:'browser', where:'shell', what:'details panel width' },
  { key:'edge-details-open', match:'exact', area:'session', kind:'browser', where:'shell', what:'details panel open' },
  { key:'edge-pins-height', match:'exact', area:'local', kind:'browser', where:'shell', what:'pinned answers panel height' },
  { key:'edge-pins-open', match:'exact', area:'local', kind:'browser', where:'shell', what:'pinned answers panel open' },
  { key:'edge-flow-open', match:'exact', area:'local', kind:'browser', where:'shell', what:'flow panel open' },
  { key:'edge-sources-open:', match:'prefix', area:'local', kind:'browser', where:'shell', what:'a Sources part opened (by its title)' },
  { key:'edge-last-login', match:'exact', area:'local', kind:'browser', where:'shared/edge-session.ts', what:'the identity signed in last (owner:<owner key>, else the login), to see a change of user; removed on sign-out' },
  { key:'edge-side-attach:', match:'prefix', area:'session', kind:'user', cache:true, where:'shell', what:'a passage quoted into a side chat (by conversation id)' },
  { key:'edge-model-choice', match:'exact', area:'local', kind:'user', sync:true, cap:'monitor.view', where:'shell', what:'the chosen AI model and level' },
  { key:'edge-research-context', match:'exact', area:'session', kind:'user', cache:true, where:'shell (legacy)', what:'an older research context; removed on load' },
  { key:'edge-research-context', match:'exact', area:'local', kind:'user', cache:true, where:'shell (legacy)', what:'an older research context; removed on load' },
  { key:'edge-auth-monitor-conversations', match:'exact', area:'local', kind:'user', cache:true, where:'shell (legacy)', what:'an older conversation list; removed on load' },
  { key:'edge-auth-monitor-conversations', match:'exact', area:'session', kind:'user', cache:true, where:'shell (legacy)', what:'an older conversation list; removed on load' },
  { key:'edge-session', match:'exact', area:'local', kind:'user', cache:true, where:'shell (legacy)', what:'an older session copy; removed on load' },
  { key:'edge-session', match:'exact', area:'session', kind:'user', cache:true, where:'shell (legacy)', what:'an older session copy; removed on load' },
  { key:'edge-active-run', match:'exact', area:'local', kind:'user', cache:true, where:'shell (legacy)', what:'an older running question; removed on load' },
  { key:'edge-active-run', match:'exact', area:'session', kind:'user', cache:true, where:'shell (legacy)', what:'an older running question; removed on load' },
  // the Terminal (terminal/src): a chart's content and the account's saved things are the user's; panel sizes are the browser's
  { key:'ml.symbol', match:'exact', area:'local', kind:'user', sync:true, where:'Terminal, Backtest, Screener, Radar, Overview, Watchlist', what:'the ticker the Terminal opens on' },
  { key:'ml.tf', match:'exact', area:'local', kind:'user', sync:true, cap:'terminal.view', where:'Terminal (layout)', what:'timeframe' },
  { key:'ml.tfs', match:'exact', area:'local', kind:'browser', where:'Terminal', what:'timeframes the data offered' },
  { key:'ml.fi.metric', match:'exact', area:'local', kind:'user', sync:true, cap:'terminal.view', where:'Terminal (layout)', what:'bond yield or price' },
  { key:'ml.chart.style', match:'exact', area:'local', kind:'user', sync:true, cap:'terminal.view', where:'Terminal (layout)', what:'candle or line' },
  { key:'ml.chart.mode', match:'exact', area:'local', kind:'user', sync:true, cap:'terminal.view', where:'Terminal (layout)', what:'price or return' },
  { key:'ml.vol.on', match:'exact', area:'local', kind:'user', sync:true, cap:'terminal.view', where:'Terminal (layout)', what:'volume shown' },
  { key:'ml.vol.removed', match:'exact', area:'local', kind:'user', sync:true, cap:'terminal.view', where:'Terminal (layout)', what:'volume removed' },
  { key:'ml.ind.v1', match:'exact', area:'local', kind:'user', sync:true, cap:'terminal.view', where:'Terminal (layout)', what:'the indicators on the chart' },
  { key:'ml.ind.filters', match:'exact', area:'local', kind:'user', sync:true, cap:'terminal.view', where:'Terminal (layout)', what:'indicator filters' },
  { key:'ml.ind.favs', match:'exact', area:'local', kind:'user', sync:true, cap:'terminal.view', where:'Terminal', what:'favourite indicators' },
  { key:'ml.ind.box', match:'exact', area:'local', kind:'browser', where:'Terminal', what:'Indicators window size' },
  { key:'ml.ind.navw', match:'exact', area:'local', kind:'browser', where:'Terminal', what:'Indicators window group list width' },
  { key:'ml.legend.hidden', match:'exact', area:'local', kind:'user', sync:true, cap:'terminal.view', where:'Terminal (layout)', what:'indicator names hidden' },
  { key:'ml.events.v1', match:'exact', area:'local', kind:'user', sync:true, cap:'terminal.view', where:'Terminal (layout)', what:'event markers chosen' },
  { key:'ml.flow.filters', match:'exact', area:'local', kind:'user', sync:true, cap:'terminal.view', where:'Terminal (layout)', what:'Flow Timeline filters' },
  { key:'ml.flow.cum', match:'exact', area:'local', kind:'user', sync:true, cap:'terminal.view', where:'Terminal (layout)', what:'Flow Timeline cumulative line' },
  { key:'ml.flow.collapsed', match:'exact', area:'local', kind:'user', cache:true, where:'Terminal (layout)', what:'Flow Timeline folded' },
  { key:'ml.flow.h', match:'exact', area:'local', kind:'user', cache:true, where:'Terminal (layout)', what:'Flow Timeline height' },
  { key:'ml.flow.ratio', match:'exact', area:'local', kind:'user', cache:true, where:'Terminal (layout)', what:'Flow Timeline height share' },
  { key:'ml.layout.', match:'prefix', area:'local', kind:'user', cache:true, where:'Terminal', what:'the open saved layout, its autosave and base' },
  { key:'ml.drawings.', match:'prefix', area:'local', kind:'user', cache:true, where:'Terminal', what:'drawings kept while the account cannot be reached (stamped with the login, M468)' },
  { key:'ml.assets.v1', match:'exact', area:'local', kind:'user', sync:true, cap:'terminal.view', where:'Terminal', what:'series added to the chart' },
  { key:'ml.assets.defaults', match:'exact', area:'local', kind:'browser', where:'Terminal', what:'default look of an added series' },
  { key:'ml.assets.flow.', match:'prefix', area:'local', kind:'user', cache:true, where:'Terminal', what:'an added series pane folded or its height, by its ticker (the account\'s series, re-check R1-20)' },
  { key:'ml.draw.', match:'prefix', area:'local', kind:'browser', where:'Terminal', what:'drawing tool choices (cursor, line, shape, measure, magnet)' },
  { key:'ml.stats.', match:'prefix', area:'local', kind:'browser', where:'Terminal', what:'left panel width, fold, sections and order' },
  { key:'ml.broker.', match:'prefix', area:'local', kind:'browser', where:'Terminal', what:'right panel width, fold, sections and order' },
  { key:'ml.acc.top', match:'exact', area:'local', kind:'browser', where:'Terminal', what:'top brokers shown' },
  { key:'ml.fd.', match:'prefix', area:'local', kind:'browser', where:'Terminal', what:'Foreign x Domestic top count and readout' },
  { key:'ml.win.', match:'prefix', area:'local', kind:'browser', where:'Terminal', what:'floating window places and which are open' },
  { key:'ml.winst.', match:'prefix', area:'local', kind:'browser', where:'Terminal', what:'floating broker window sort and view' },
  { key:'terminal-files', match:'exact', area:'idb', kind:'user', cache:true, where:'Terminal, Backtest, Screener', what:'downloaded data files and the Screener\'s last result' },
  // the Backtest (backtest/src)
  { key:'ml.my', match:'exact', area:'local', kind:'user', sync:true, cap:'backtest.view', where:'Backtest', what:'my conditions' },
  { key:'ml.bw', match:'exact', area:'local', kind:'browser', where:'Backtest', what:'panel width' },
  { key:'ml.panel', match:'exact', area:'local', kind:'browser', where:'Backtest', what:'panel shown' },
  // the Screener (screener/src)
  { key:'scr.last', match:'exact', area:'local', kind:'user', sync:true, cap:'screener.view', where:'Screener', what:'the last screen definition' },
  { key:'scr.boot', match:'exact', area:'local', kind:'user', cache:true, where:'Screener', what:'the cached first paint pointer (with its login)' },
  { key:'scr.extraCols', match:'exact', area:'local', kind:'user', sync:true, cap:'screener.view', where:'Screener', what:'extra columns chosen' },
  { key:'scr.panel', match:'exact', area:'local', kind:'browser', where:'Screener', what:'panel layout' },
  { key:'scr.panes', match:'exact', area:'local', kind:'browser', where:'Screener', what:'pane sizes' },
  { key:'scr.popsize', match:'exact', area:'local', kind:'browser', where:'Screener', what:'pop-up sizes' },
  { key:'scr.colorder', match:'exact', area:'local', kind:'browser', where:'Screener', what:'column order' },
  // the Watchlist (watchlist/src)
  { key:'edge.watchlist.view', match:'exact', area:'local', kind:'user', sync:true, cap:'watchlist.view', where:'Watchlist', what:'the open list id and Table or Cards' },
  { key:'edge.watchlist.logos', match:'exact', area:'local', kind:'user', cache:true, where:'Watchlist', what:'issuer logo list (12 hours; a reference file the plan reads, so it leaves with the account: re-check R1-17)' },
]);

/** the registry entry of a key, or null when the key is not classed (a defect: tests/test_storage_registry.py) */
export function classify(key: string, area: StorageArea = 'local'): StorageEntry | null {
  let best: StorageEntry | null = null;
  for (const e of STORAGE) {
    if (e.area !== area) continue;
    if (e.match === 'exact' ? key === e.key : key.startsWith(e.key)) {
      if (e.match === 'exact') return e;
      if (!best || e.key.length > best.key.length) best = e;
    }
  }
  return best;
}

/* a key no entry names but in EDGE's own namespaces is treated as the user's (privacy first: a missed preference costs
   less than another account's data left behind) */
const OURS = /^(?:ml\.|scr\.|edge[.:-])/;
const isUserKey = (key: string, area: StorageArea) => { const e = classify(key, area); return e ? e.kind === 'user' : OURS.test(key) };

export const LAST_LOGIN_KEY = 'edge-last-login';
const CHANNEL = 'edge-session';
const norm = (login: string) => String(login || '').trim().toLowerCase();

function areaOf(area: 'local' | 'session'): Storage | null {
  try { return area === 'local' ? globalThis.localStorage ?? null : globalThis.sessionStorage ?? null } catch { return null }
}
function keysOf(s: Storage): string[] {
  const out: string[] = [];
  try { for (let i = 0; i < s.length; i++) { const k = s.key(i); if (k !== null) out.push(k) } } catch { /* storage off */ }
  return out;
}

/** the login stored as the last one signed in on this browser ('' when none) */
export function lastLogin(): string {
  try { return areaOf('local')?.getItem(LAST_LOGIN_KEY) || '' } catch { return '' }
}

/* this page's own messages are not read back (a page that clears for itself already dropped what it holds) */
const PAGE_ID = Math.random().toString(36).slice(2) + Date.now().toString(36);
function post(message: Record<string, unknown>) {
  try { if (typeof BroadcastChannel !== 'undefined') { const c = new BroadcastChannel(CHANNEL); c.postMessage({ ...message, from:PAGE_ID }); c.close() } } catch { /* not offered */ }
}

/** removes every `user` key of localStorage and sessionStorage and the `user` IndexedDB databases of this browser.
    `signOut` also removes the last-login mark (nothing of the account remains). Resolves when the databases are gone
    or, when a page still holds one open, once the browser has queued their removal (they go when that page closes). */
function clearArea(area: 'local' | 'session', signOut: boolean) {
  const s = areaOf(area); if (!s) return;
  for (const k of keysOf(s)) {
    if (k === LAST_LOGIN_KEY ? signOut : isUserKey(k, area)) { try { s.removeItem(k) } catch { /* storage off */ } }
  }
}
/* Phase 2: what a page holds in memory for its account (the catalog answers) goes with the user state */
const memoryClears = new Set<() => void>();
export function clearUserState(opts: { signOut?: boolean } = {}): Promise<void> {
  memoryClears.forEach(fn => { try { fn() } catch { /* the others still run */ } });
  clearArea('local', !!opts.signOut);
  clearArea('session', !!opts.signOut);
  post({ type:'cleared', signOut:!!opts.signOut });
  const idb: IDBFactory | undefined = (() => { try { return globalThis.indexedDB } catch { return undefined } })();
  const names = STORAGE.filter(e => e.area === 'idb' && e.kind === 'user').map(e => e.key);
  if (!idb) return Promise.resolve();
  return Promise.all(names.map(n => new Promise<void>(done => {
    try {
      const r = idb.deleteDatabase(n);
      r.onsuccess = r.onerror = () => done();
      r.onblocked = () => done();                  // queued: removed when the page holding it open closes
    } catch { done() }
  }))).then(() => undefined);
}

/* EXEC-MU-ACCOUNTS Phase 1: an identity is `owner:<owner key>` when the session answer carries the stable owner key
   (contract section 2), else the login (Phase 0 and the switch off). A username cannot hold ':' (^[a-z0-9_]{3,30}$), so
   the two forms never meet. The marks and the drawing stamps written with the login by the same account are moved to
   the owner key once (migrateIdentity). */
export const identityOf = (login: string, ownerKey?: string | null) => ownerKey ? `owner:${norm(ownerKey)}` : norm(login);

/** a `user` key (or our namespaces' unknown key) is held in this browser's storage */
function hasUserState(): boolean {
  for (const area of ['local', 'session'] as const) {
    const s = areaOf(area); if (!s) continue;
    if (keysOf(s).some(k => k !== LAST_LOGIN_KEY && isUserKey(k, area))) return true;
  }
  return false;
}
/** a drawing copy stamped with `owner` is held here */
function hasStampsOf(owner: string): boolean {
  const s = areaOf('local'); if (!s || !owner) return false;
  return keysOf(s).some(k => { if (!k.startsWith('ml.drawings.')) return false;
    try { const v = JSON.parse(s.getItem(k) || 'null'); return !!v && typeof v === 'object' && !Array.isArray(v) && v.owner === owner } catch { return false } });
}

/** the drawing copies stamped with `from` (the login) are stamped with `to` (the owner key): the same account */
export function migrateIdentity(from: string, to: string) {
  const s = areaOf('local'); if (!s || !from || !to || from === to) return;
  for (const k of keysOf(s)) {
    if (!k.startsWith('ml.drawings.')) continue;
    try {
      const v = JSON.parse(s.getItem(k) || 'null');
      if (v && typeof v === 'object' && !Array.isArray(v) && v.owner === from) s.setItem(k, JSON.stringify({ ...v, owner:to }));
    } catch { /* not a stamped copy */ }
  }
}

/* a mark or a drawing stamp of the bare-login form was written by Phase 0, when EDGE had one account (user #1): every
   identity written since Phase 1 is `owner:<key>` (the session answer carries the owner key) */
const bareForm = (id: string) => !!id && !id.startsWith('owner:');
/** user #1's Phase 0 drawing stamps (the bare-login form) are stamped with its owner identity `to` */
function migrateBare(to: string) {
  const s = areaOf('local'); if (!s || bareForm(to)) return;
  for (const k of keysOf(s)) {
    if (!k.startsWith('ml.drawings.')) continue;
    try {
      const v = JSON.parse(s.getItem(k) || 'null');
      if (v && typeof v === 'object' && !Array.isArray(v) && typeof v.owner === 'string' && bareForm(v.owner)) s.setItem(k, JSON.stringify({ ...v, owner:to }));
    } catch { /* not a stamped copy */ }
  }
}
/** `seed` (the session answer's access.seed, user #1) keeps this browser's state: it has no mark, or a mark of the
    bare-login form (Phase 0), so its state was written while EDGE had one account (C3 Phase 1 B1, C4) */
const seedKeeps = (was: string, now: string, seed?: boolean) => seed === true && was !== now && (!was || bareForm(was));

/** the shell, after a sign-in or a session read: another identity than the last one clears the previous account's
    state first; then this one is the last. A mark holding this account's login while the answer now carries its owner
    key is the same account: the mark and its drawing stamps move to the owner key. `same`: the local state was this
    identity's (edge-client.js then uploads its values with no server copy once).
    A browser with no mark (EDGE last used there before the Phase 0 deploy, or the mark was removed) holds state of an
    unknown account, with one exception: `seed`, the session answer's access.seed, says this is user #1, the one account
    EDGE had before accounts. State written before the mark existed, or under a Phase 0 mark (the bare login, which may
    differ from the seed's username with the switch on: EDGE_LOGIN 'edge' is reserved), can only be its: kept, its stamps
    moved, uploaded once (C3 Phase 1 B1, C4). Any other identity never adopts it (C2 Phase 1 #3): only drawing copies
    stamped by this same login are its (the one-time move to the owner key); anything else is cleared. */
export function noteIdentity(login: string, ownerKey?: string | null, opts: { seed?: boolean } = {}): { changed: boolean; same: boolean } {
  const now = identityOf(login, ownerKey); if (!now) return { changed:false, same:false };
  const was = lastLogin();
  const seed = seedKeeps(was, now, opts.seed);
  const ownStamps = !was && hasStampsOf(norm(login));
  const upgraded = !seed && !!ownerKey && (was === norm(login) || ownStamps);
  if (seed) migrateBare(now); else if (upgraded) migrateIdentity(norm(login), now);
  const unknown = !was && !ownStamps && !seed && hasUserState();
  const changed = (!!was && was !== now && !upgraded && !seed) || unknown;
  if (changed) clearUserState();
  try { areaOf('local')?.setItem(LAST_LOGIN_KEY, now) } catch { /* storage off: nothing of the account is kept either */ }
  return { changed, same:(!!was && (was === now || upgraded || seed)) || (!was && (ownStamps || seed)) };
}
/** noteIdentity's `changed` (Phase 0 callers) */
export const noteLogin = (login: string, ownerKey?: string | null): boolean => noteIdentity(login, ownerKey).changed;

/** a page (inside the shell's frame or opened alone): another identity than the shell's last one clears the previous
    account's state. A page never writes the mark (the shell does), so its own storage stays its own keys; a mark of
    this account's login with its owner key now known is the same account (its stamps move, the shell moves the mark). */
export function checkUser(login: string, ownerKey?: string | null, opts: { seed?: boolean } = {}): boolean {
  const now = identityOf(login, ownerKey), was = lastLogin();
  if (!now || !was || was === now) return false;
  if (ownerKey && was === norm(login)) { migrateIdentity(was, now); return false }
  if (seedKeeps(was, now, opts.seed)) { migrateBare(now); return false }       // user #1 under its Phase 0 mark (C4)
  clearUserState();
  return true;
}

/** true when `login` is the login this browser last signed in with (M468: an unstamped offline copy is kept only then) */
export const isLastLogin = (login: string) => !!norm(login) && lastLogin() === norm(login);
/** the form of a login the marks compare (M468 stamps an offline copy with it) */
export const loginKey = norm;

/* ---- the error contract (section 3) ---------------------------------------------------------------------------- */

export type ErrorKind = 'signin' | 'csrf' | 'upgrade' | 'mfa' | 'limit' | 'wait' | 'origin' | 'not_found' | 'other';
export interface EdgeError {
  status: number;
  code: string;
  message: string;                   // the server's message ('' when it sent none)
  details: Record<string, unknown>;
  field?: string;
  retryAfter: number | null;         // seconds (Retry-After, else details.retry_after_s)
  legacy: boolean;                   // the old {"detail": ...} shape
  kind: ErrorKind;
}

/** Reads Retry-After (seconds, or an HTTP date) as whole seconds; null when absent or unreadable. */
export function retryAfter(h: string | null | undefined, now = Date.now()): number | null {
  if (!h) return null;
  const s = Number(h);
  if (Number.isFinite(s) && s >= 0) return Math.ceil(s);
  const t = Date.parse(h);
  return Number.isFinite(t) ? Math.max(0, Math.ceil((t - now) / 1000)) : null;
}

const KIND: Record<string, ErrorKind> = {
  UNAUTHENTICATED:'signin', CSRF_INVALID:'csrf', CAPABILITY_REQUIRED:'upgrade', PLAN_EXPIRED:'upgrade', MFA_REQUIRED:'mfa',
  LIMIT_REACHED:'limit', SIGN_IN_RATE_LIMIT:'wait', ORIGIN_REJECTED:'origin', NOT_FOUND:'not_found',
};

/** one refusal in the contract's terms, from its status, its JSON body (or null) and its Retry-After header */
export function readError(status: number, body: any, retryAfterHeader?: string | null): EdgeError {
  const err = body && typeof body.error === 'object' && body.error ? body.error : null;
  let code = '', message = '', legacy = false;
  if (err) { code = String(err.code || ''); message = typeof err.message === 'string' ? err.message : '' }
  else if (body && typeof body.error === 'string') code = body.error;
  else if (body && 'detail' in body && (status === 401 || status === 403)) {
    legacy = true;
    const detail = typeof body.detail === 'string' ? body.detail : '';
    code = status === 401 ? 'UNAUTHENTICATED' : /csrf/i.test(detail) ? 'CSRF_INVALID' : 'FORBIDDEN';
    message = detail;
  }
  if (!code) code = status === 401 ? 'UNAUTHENTICATED' : `HTTP_${status}`;
  const details = err && err.details && typeof err.details === 'object' ? err.details as Record<string, unknown> : {};
  const fromDetails = typeof details.retry_after_s === 'number' ? Math.ceil(details.retry_after_s) : null;
  const kind: ErrorKind = status === 401 ? 'signin' : status === 403 && code === 'CSRF_INVALID' ? 'csrf' : KIND[code] && KIND[code] !== 'signin' && KIND[code] !== 'csrf' ? KIND[code] : 'other';
  return { status, code, message, details, ...(err && typeof err.field === 'string' ? { field:err.field } : {}),
    retryAfter:retryAfter(retryAfterHeader) ?? fromDetails, legacy, kind };
}

/** the refusal of a Response that is not ok (reads its body; pass a clone to keep the body for the caller) */
export async function errorOf(res: Response): Promise<EdgeError> {
  let body: any = null;
  try { body = await res.json() } catch { /* no JSON body */ }
  return readError(res.status, body, res.headers?.get?.('Retry-After'));
}

/** the plan refusals and limits keep the session: only `signin` means the user must sign in again (M471) */
export const keepsSession = (e: EdgeError) => e.kind !== 'signin';
/** a refusal of the account's plan, role or limits (shown as a message, never retried, never a sign-out) */
export const isAccessRefusal = (e: EdgeError) => e.kind === 'upgrade' || e.kind === 'mfa' || e.kind === 'limit' || e.kind === 'wait';

const secs = (n: number | null) => n == null ? 'a minute' : n === 1 ? '1 second' : `${n} seconds`;
/** the sentence for a session refusal: the server's message first, else a fallback that names what to do; null for the
    refusals the page words itself (validation, not found, server errors) */
export function accessText(e: EdgeError): string | null {
  const name = typeof e.details.display_name === 'string' && e.details.display_name ? e.details.display_name : '';
  switch (e.kind) {
    case 'signin': return e.message && !e.legacy ? e.message : 'Your EDGE sign-in has ended. Sign in to EDGE again, then open this page again.';
    case 'csrf': return 'This page\'s sign-in check failed. Reload the page and try again.';
    case 'upgrade': return e.message || (e.code === 'PLAN_EXPIRED'
      ? 'Your EDGE plan has ended. Renew it to use this again; you are still signed in.'
      : `${name || 'This feature'} is not part of your EDGE plan. Upgrade the plan to use it; you are still signed in.`);
    case 'mfa': return e.message || 'This needs your sign-in code. Enter the code from your authenticator app in EDGE, then try again.';
    case 'limit': return e.message || `You have reached your plan's limit. Try again in ${secs(e.retryAfter)}, or upgrade the plan.`;
    case 'wait': return e.message || `Too many sign-in attempts. Wait ${secs(e.retryAfter)}, then try again.`;
    default: return null;
  }
}

/* ---- the session and CSRF -------------------------------------------------------------------------------------- */

export const SESSION_URL = '/api/v1/auth/session';
export const ENTITLEMENTS_HEADER = 'X-Edge-Entitlements';

export interface EdgeSessionInfo { login: string; ownerKey: string | null; csrf: string; access: unknown; raw: any; guest?: boolean }
/* track guest: what a visitor without an account holds (app/main.py GET /api/v1/auth/guest), and the identity of such a
   page (never a login or an owner key: identityOf makes neither) */
export const GUEST_URL = '/api/v1/auth/guest';
export const GUEST_IDENTITY = 'guest:';

/* EXEC-MU-ACCOUNTS Phase 2 (contract sections 4 and 8a): the session answer's `access` object. `capabilities` holds the
   flag keys the account holds (`*`: every capability, the admin plan and the switch-off principal, version 'env');
   `limits` holds the limits (a number) and the lists (strings); a key with no entry has no limit. */
export interface EdgeAccess {
  plan?: string | null; role?: string | null; status?: string | null; expires_at?: string | null; expired_plan?: string | null;
  mfa_ok?: boolean; mfa_enrolled?: boolean; seed?: boolean; owner_key?: string | null; next?: string | null;
  capabilities: string[];
  limits: Record<string, number | string[]>;
  version?: string | null;
  [other: string]: unknown;
}
export const CATALOG_URL = '/api/v1/catalog/';
export interface CatalogEntry { id: string; stage: string }
export interface CatalogAnswer { kind: string; entries: readonly CatalogEntry[] }
/** an item key `<family>:<id>` (for example terminal.indicator:I01): held by stage or id, which the session answer does
    not carry, so can() decides it only for `*`; use catalog(kind) for the items the account holds */
const isItemKey = (key: string) => key.includes(':');

/** a failed session read: `error` is the refusal (kind 'signin' on a 401), or null when EDGE could not be reached */
export class SessionError extends Error {
  constructor(public error: EdgeError | null, message: string) { super(message) }
}

const clients = new Set<() => void>();
/* Phase 0 fix round (C1 M1-M2, C2 #2-#3): what a page must drop when its user may have changed (a 401, another
   account's session, the 'cleared' broadcast): pending writes such as the drawings' autosave (onReset) */
const resets = new Set<() => void>();
const fireResets = () => resets.forEach(fn => { try { fn() } catch { /* the others still run */ } });
/** `fn` runs when this page's account ended or changed: drop pending writes, never stamp or send them */
export function onReset(fn: () => void): () => void { resets.add(fn); return () => { resets.delete(fn) } }
/* the 'cleared' broadcast of another page, for any role: the shell drops its in-memory views and reads the session again */
const clearedHooks = new Set<() => void>();
/** `fn` runs when another page cleared the user state (a sign-out, or another account signed in) */
export function onCleared(fn: () => void): () => void { clearedHooks.add(fn); return () => { clearedHooks.delete(fn) } }
/* re-check R2-16, R2-31: a new X-Edge-Entitlements version, seen by this page or broadcast by another (a frame), for a
   client that keeps its own copy of the session (the shell's edge-client.js `auth`, the model list) */
const versionHooks = new Set<(version: string | null) => void>();
const fireVersion = (v: string | null) => versionHooks.forEach(fn => { try { fn(v) } catch { /* the others still run */ } });
/** `fn` runs when the account's access may have changed (a new X-Edge-Entitlements here or in another page) */
export function onVersion(fn: (version: string | null) => void): () => void { versionHooks.add(fn); return () => { versionHooks.delete(fn) } }
/* re-check R2-17 (CONTRACT.md 3: a 401 UNAUTHENTICATED goes to sign-in): a page whose own session ended (idle, sign-out
   everywhere, a reset or a disable elsewhere) says so to the shell, which holds the sign-in page; a frame has none */
const signedOutHooks = new Set<() => void>();
const fireSignedOut = () => signedOutHooks.forEach(fn => { try { fn() } catch { /* the others still run */ } });
/** `fn` runs when another page of this browser met a 401 of its own session (the shell then reads its own session) */
export function onSignedOut(fn: () => void): () => void { signedOutHooks.add(fn); return () => { signedOutHooks.delete(fn) } }
export const SIGNED_OUT = 'signed-out';
function saySignedOut() {
  post({ type:SIGNED_OUT });
  // the shell's frames also tell their parent directly (a browser without BroadcastChannel); same origin only
  try { if (typeof window !== 'undefined' && window.parent && window.parent !== window) window.parent.postMessage({ type:'edge-session', event:SIGNED_OUT }, location.origin) } catch { /* no parent */ }
}
let role: 'app' | 'shell' = 'app';
let parentListening = false;
/** the shell says so at load: a page ('app', the default) reloads on 'cleared'; the shell keeps its own sign-in flow
    and hears a frame's ended session (onSignedOut) */
export function setRole(r: 'app' | 'shell') {
  role = r; listen();
  if (r === 'shell' && !parentListening && typeof addEventListener === 'function') {
    parentListening = true;
    addEventListener('message', ((e: MessageEvent) => {
      try { if (e.origin !== location.origin || e.data?.type !== 'edge-session' || e.data?.event !== SIGNED_OUT) return } catch { return }
      fireSignedOut();
    }) as EventListener);
  }
}
/** reloads an app page (its in-memory state and singletons must not outlive its account); nothing outside a browser */
export function reloadPage() {
  try { if (role === 'app' && typeof location !== 'undefined' && typeof location.reload === 'function') location.reload() } catch { /* not a page */ }
}
let entitlements: string | null = null;
let listening = false;
function listen() {
  if (listening) return; listening = true;
  try {
    if (typeof BroadcastChannel === 'undefined') return;
    const c = new BroadcastChannel(CHANNEL);
    c.onmessage = (ev: MessageEvent) => {
      if (ev?.data?.from === PAGE_ID) return;
      const t = ev?.data?.type;
      if (t === 'entitlements' || t === 'cleared') clients.forEach(fn => fn());
      if (t === 'entitlements') fireVersion(typeof ev?.data?.version === 'string' ? ev.data.version : null);
      if (t === SIGNED_OUT) fireSignedOut();
      // another tab signed out or another account signed in: nothing of this page's account may survive in memory
      if (t === 'cleared') {
        // sessionStorage is per tab: the page that signed out (or saw another account) cleared only its own (C4)
        clearArea('session', !!ev?.data?.signOut);
        clearedHooks.forEach(fn => { try { fn() } catch { /* the others still run */ } });
        if (role === 'app') { fireResets(); reloadPage() }
      }
    };
    (c as unknown as { unref?: () => void }).unref?.();       // Node (tests): the channel never keeps the process alive
  } catch { /* not offered */ }
}
/* the X-Edge-Entitlements version (section 12): a new value makes every page read the session again */
function noteVersion(res: Response) {
  let v: string | null = null;
  try { v = res.headers?.get?.(ENTITLEMENTS_HEADER) ?? null } catch { v = null }
  if (!v || v === entitlements) return;
  const first = entitlements === null; entitlements = v;
  if (!first) { clients.forEach(fn => fn()); post({ type:'entitlements', version:v }); fireVersion(v) }
}

const WRITE = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

/** one session per page (`fetchImpl`: a test passes its own fetch). `session()` reads /api/v1/auth/session once and
    keeps it; `send()` is fetch with the session's rules (CSRF on writes, one repeat on CSRF_INVALID). */
export function sessionClient(fetchImpl?: typeof fetch) {
  const f: typeof fetch = fetchImpl ?? ((...a: Parameters<typeof fetch>) => fetch(...a));
  let p: Promise<EdgeSessionInfo> | null = null, now: EdgeSessionInfo | null = null;
  /* the login of this page's first session read: the account the page's memory belongs to. It never changes; a later
     read of another login is refused (C1 M1, C2 #2). Phase 1: switch to the session answer's stable owner key. */
  let identity = '';
  /* Phase 2: catalog(kind) answers, in memory only (never browser storage), stamped with the X-Edge-Entitlements version
     and the page identity they were read under. Dropped with the session (a new version, a 'cleared' broadcast, a 401:
     invalidate below), when this page clears the user state, and on onReset (another account). */
  const catalogs = new Map<string, { stamp: string; answer: Promise<CatalogAnswer> }>();
  let catalogGen = 0;
  const dropCatalogs = () => { catalogs.clear(); catalogGen++ };
  const catalogStamp = () => `${entitlements ?? ''}\n${identity}`;
  const invalidate = () => { p = null; now = null; dropCatalogs() };
  clients.add(invalidate); listen();
  resets.add(dropCatalogs); memoryClears.add(dropCatalogs);
  /* track guest: whether this page may run as a visitor without an account (allowGuest), and the guest plan's answer of
     GET /api/v1/auth/guest, or null (guests off on this site, no readable client address, or a session after all) */
  let guests = false;
  async function guestRead(): Promise<EdgeSessionInfo | null> {
    let res: Response;
    try { res = await f(GUEST_URL, { credentials:'same-origin' }) } catch { return null }
    const d: any = await res.json().catch(() => null);
    if (!res.ok || d?.visitor !== true) return null;
    noteVersion(res);
    return { login:'', ownerKey:null, csrf:'', access:d?.access ?? null, raw:d, guest:true };
  }
  const session = (): Promise<EdgeSessionInfo> => p ||= (async () => {
    let res: Response;
    try { res = await f(SESSION_URL, { credentials:'same-origin' }) }
    catch { throw new SessionError(null, 'EDGE could not be reached. Check the connection and try again.') }
    if (!res.ok) {
      const e = await errorOf(res);
      const visitor = res.status === 401 && guests ? await guestRead() : null;
      if (visitor) {
        // an account whose session ended on this page: the page's memory is that account's, so it reloads as a visitor
        if (identity && identity !== GUEST_IDENTITY) { fireResets(); reloadPage() }
        if (!identity) identity = GUEST_IDENTITY;
        now = visitor;
        return visitor;
      }
      if (res.status === 401) saySignedOut();
      throw new SessionError(e, accessText(e) || `EDGE answered ${res.status}.`);
    }
    noteVersion(res);
    const d = await res.json().catch(() => ({}));
    const owner = d?.owner_key ?? d?.access?.owner_key;
    const s: EdgeSessionInfo = { login:String(d?.login || ''), ownerKey:typeof owner === 'string' && owner ? owner : null,
      csrf:String(d?.csrf_token || ''), access:d?.access ?? null, raw:d };
    const id = identityOf(s.login, s.ownerKey);
    // the same account, now named by its owner key (a deploy between two reads): the identity moves with it
    if (identity && id !== identity && s.ownerKey && identity === norm(s.login)) { migrateIdentity(identity, id); identity = id }
    if (identity === GUEST_IDENTITY) {
      // a visitor of this page signed in (another tab, the sign-in box): a visitor holds nothing of an account, so
      // nothing is cleared; the page reloads as the account (its own state, preferences and limits)
      fireResets();
      reloadPage();
      const e = readError(401, { error:{ code:'USER_CHANGED', message:'You signed in to EDGE. Reload the page to continue with your account.' } });
      throw new SessionError(e, e.message);
    }
    if (identity && id !== identity) {
      // another account signed in on this browser since the page opened: never act for it with this page's state
      fireResets();
      void clearUserState();
      reloadPage();
      const e = readError(401, { error:{ code:'USER_CHANGED', message:'Another EDGE account signed in on this browser. Reload the page to continue as that account.' } });
      throw new SessionError(e, e.message);
    }
    checkUser(s.login, s.ownerKey, { seed:d?.access?.seed === true });
    if (!identity) identity = id;
    now = s;
    return s;
  })().catch(e => { p = null; throw e });

  /** fetch with the session: a write carries X-CSRF-Token; a 403 CSRF_INVALID (or the old "Invalid CSRF token")
      reads the session again and repeats the write once; a 401 forgets the session. Network failures and session
      read failures reject as they are (the caller words them); every other answer is returned as it is. */
  const changed = (message = 'Another EDGE account signed in on this browser. Reload the page to continue as that account.') =>
    new Response(JSON.stringify({ error:{ code:'USER_CHANGED', message, details:{} } }), { status:401, headers:{ 'Content-Type':'application/json' } });
  /* `expected`: the identity the write was asked for (the page's identity when send() was called). A write goes out only
     for it: an identity forgotten (the shell's 'cleared' handler) or changed while the write waited is a change of user,
     and a repeat is sent only when the session read again is that same identity (C2 Phase 1 #2). */
  async function send(url: string, init: RequestInit = {}, retried = false, expected: string = identity): Promise<Response> {
    const method = String(init.method || 'GET').toUpperCase();
    const write = WRITE.has(method);
    const headers: Record<string, string> = { ...(init.headers as Record<string, string> || {}) };
    if (write) {
      if (retried && !expected) return changed();
      try { headers['X-CSRF-Token'] = (await session()).csrf }
      catch (e) {
        // another account's session: the write is never sent; the page gets a 401 USER_CHANGED (sign in / reload)
        if (e instanceof SessionError && e.error?.code === 'USER_CHANGED') return changed(e.message);
        throw e;
      }
      if (!retried && !expected) expected = identity;                       // the page's first read: the write is this identity's
      if (expected && identity !== expected) return changed();
    }
    const res = await f(url, { credentials:'same-origin', ...init, method, headers });
    noteVersion(res);
    // a 401 of the page's own account (its session expired) keeps pending writes: they are stamped with the page's
    // identity and join that account again; only another login, USER_CHANGED or 'cleared' drops them
    if (res.status === 401) { invalidate(); saySignedOut() }
    if (res.status === 403 && write && !retried) {
      const e = await errorOf(res.clone());
      // the repeat goes out only when the session read again is the page's own account (session() refuses another)
      if (e.kind === 'csrf') { invalidate(); return send(url, init, true, expected) }
    }
    return res;
  }

  /* ---- Phase 2: what the account holds (contract 8a; the server decides, these only mirror it for the page) ---- */

  /** the last session answer's `access` object, or null (no session read yet, or read again after a change) */
  function access(): EdgeAccess | null {
    const a: any = now?.access;
    if (!a || typeof a !== 'object' || Array.isArray(a)) return null;
    return { ...a, capabilities:Array.isArray(a.capabilities) ? a.capabilities.filter((c: unknown) => typeof c === 'string') : [],
      limits:a.limits && typeof a.limits === 'object' && !Array.isArray(a.limits) ? a.limits : {} };
  }
  /** the server's p.can(key) for flags: `*` holds every key; a flag key is held when the session answer lists it. An item
      key `<family>:<id>` is false unless `*` is held (use catalog(kind)); a limit or list key is read with limit() */
  function can(key: string): boolean {
    const caps = access()?.capabilities ?? [];
    if (caps.includes('*')) return true;
    return !!key && !isItemKey(key) && caps.includes(key);
  }
  /** the server's p.limit(key): a number (a limit) or a list of strings; undefined when absent, which means no limit */
  function limit(key: string): number | string[] | undefined {
    const v = access()?.limits?.[key];
    if (typeof v === 'number' && Number.isFinite(v)) return v;
    if (Array.isArray(v)) return v.filter(x => typeof x === 'string');
    return undefined;
  }
  /** GET /api/v1/catalog/{kind}: {kind, entries:[{id, stage}]}, the items of that kind the account holds. Kept in memory
      per X-Edge-Entitlements version and page identity. A refusal (404 NOT_FOUND for an unknown kind, 401) rejects with
      a SessionError carrying the EdgeError; EDGE out of reach rejects with a SessionError whose error is null. A
      refusal is never kept. The page's first session read comes first (the identity the answers belong to). */
  function catalog(kind: string): Promise<CatalogAnswer> {
    return identity ? catalogOf(kind) : session().then(() => catalogOf(kind));
  }
  function catalogOf(kind: string): Promise<CatalogAnswer> {
    const hit = catalogs.get(kind);
    if (hit && hit.stamp === catalogStamp()) return hit.answer;
    const gen = catalogGen;
    const entry = { stamp:catalogStamp(), answer:null as unknown as Promise<CatalogAnswer> };
    entry.answer = (async () => {
      let res: Response;
      try { res = await send(CATALOG_URL + encodeURIComponent(kind)) }
      catch { throw new SessionError(null, 'EDGE could not be reached. Check the connection and try again.') }
      if (!res.ok) { const e = await errorOf(res); throw new SessionError(e, accessText(e) || e.message || `EDGE answered ${res.status}.`) }
      const d: any = await res.json().catch(() => null);
      const entries = Array.isArray(d?.entries) ? d.entries.filter((x: any) => x && typeof x.id === 'string')
        .map((x: any) => Object.freeze({ id:x.id, stage:typeof x.stage === 'string' ? x.stage : 'lab' })) : [];
      // the answer carries the version it was decided under (a first version noted by this very answer included)
      if (gen === catalogGen && catalogs.get(kind) === entry) entry.stamp = catalogStamp();
      return Object.freeze({ kind:typeof d?.kind === 'string' ? d.kind : kind, entries:Object.freeze(entries) });
    })();
    entry.answer.catch(() => { if (catalogs.get(kind) === entry) catalogs.delete(kind) });
    catalogs.set(kind, entry);
    return entry.answer;
  }

  return { session, send, invalidate, access, can, limit, catalog, get current() { return now },
    /** track guest: this page may run as a visitor without an account (the Terminal); call before the first read */
    allowGuest() { guests = true },
    /** track guest: the session read is a visitor's (the guest plan's access), not an account's */
    get guest() { return !!now?.guest },
    /** the identity this page opened with ('' before its first session read): owner:<owner key>, else the login */
    get identity() { return identity },
    /** the shell only, on its own sign-out or sign-in: the next session read is a new identity, not a change of user */
    forget() { invalidate(); identity = '' } };
}
export type SessionClient = ReturnType<typeof sessionClient>;

/** the page's one session (global fetch, read when called so a test's stub is used) */
export const edge: SessionClient = sessionClient();

/* ---- account preferences (contract 4b; the routes of apps/edge-bff/app/preferences.py) ------------------------------ */

/** the keys copied to the account (registry `sync`) */
export const SYNC_KEYS: readonly string[] = Object.freeze(STORAGE.filter(e => e.sync && e.match === 'exact' && e.area === 'local').map(e => e.key));
export const PREFERENCES_URL = '/api/v1/preferences';
/* app/preferences.py LIMITS, replaced by the GET answer's `limits`: value_bytes is the JSON text as PostgreSQL keeps it */
const DEFAULT_VALUE_BYTES = 65536;

interface PrefState { version: number | null; value: string | null }
/* a stored value is the text this browser keeps (localStorage holds text; the page writes it as a JSON string value); a
   value another client wrote as other JSON is kept as its JSON text */
const asText = (v: unknown): string | null => v == null ? null : typeof v === 'string' ? v : JSON.stringify(v);
const jsonBytes = (v: string) => { try { return new TextEncoder().encode(JSON.stringify(v)).length } catch { return v.length * 3 } };

/** the account copy of the `sync` keys, run by the shell after its session read (`client`: the shell's session).
    The routes (app/preferences.py):
    - GET /api/v1/preferences -> {preferences: {key: {value, version, updated_at}}, limits};
    - PUT /api/v1/preferences/{key} {value, version|null} -> 201 created / 200 replaced {key, value, version, updated_at};
      a stale or missing version -> 409 PREFERENCE_CONFLICT, details.current {value, version} (null: no row any more);
      a limit -> 422 PREFERENCE_LIMIT, details.limit keys | value_bytes | total_bytes.
    load(): the server copy into this browser's storage; with `uploadLocal` (the local state is this identity's) a local
    value with no server copy goes up once. note(key): a change, written a moment later (`delayMs`) with the version it
    was read with (null for a key the server does not hold); a 409 takes the server's value; a 422 PREFERENCE_LIMIT, or
    a 403 for a key of a tab the plan does not hold (the GET leaves those out; re-check R1-18), stops that key for this
    page (the page keeps working from its storage). Changes made in the pages' frames reach the shell as `storage`
    events. stop(): nothing more is written (sign-out, another account). */
export function preferences(client: { send: SessionClient['send'] }, opts: { delayMs?: number } = {}) {
  const delay = opts.delayMs ?? 1000;
  const state = new Map<string, PrefState>();
  const timers = new Map<string, ReturnType<typeof setTimeout>>();
  // keys over a limit (422 PREFERENCE_LIMIT) or of a tab the plan does not hold (403 CAPABILITY_REQUIRED or
  // PLAN_EXPIRED, re-check R1-18): not sent again by this page
  const refused = new Set<string>();
  let on = false, listening = false, valueBytes = DEFAULT_VALUE_BYTES;
  const local = () => areaOf('local');
  const onStorage = (e: StorageEvent) => {
    if (!on || !e.key || e.newValue === null || !SYNC_KEYS.includes(e.key)) return;     // a removal is a clean-up, never sent
    try { if (e.storageArea && e.storageArea !== local()) return } catch { /* no storage */ }
    note(e.key);
  };
  const keep = (key: string, value: string | null) => {
    try { if (value === null) local()?.removeItem(key); else if (local()?.getItem(key) !== value) local()?.setItem(key, value) } catch { /* storage off */ }
  };
  async function put(key: string, again = true): Promise<void> {
    timers.delete(key);
    if (!on || refused.has(key)) return;
    let value: string | null = null;
    try { value = local()?.getItem(key) ?? null } catch { value = null }
    const was = state.get(key);
    if (value === null || value === (was?.value ?? null)) return;
    if (jsonBytes(value) > valueBytes) { refused.add(key); return }          // the server would refuse it (value_bytes)
    if (!on) return;                                                         // stopped (sign-out, another account): never written
    let res: Response;
    try {
      res = await client.send(`${PREFERENCES_URL}/${encodeURIComponent(key)}`, { method:'PUT', headers:{ 'Content-Type':'application/json' },
        body:JSON.stringify({ value, version:was?.version ?? null }) });
    } catch { return }                                                       // offline: the next change sends it
    let body: any = null;
    try { body = await res.json() } catch { body = null }
    if (!on) return;
    if (res.status === 200 || res.status === 201) { state.set(key, { value, version:typeof body?.version === 'number' ? body.version : null }); return }
    const error = body?.error;
    if (res.status === 409 && error?.code === 'PREFERENCE_CONFLICT') {
      const current = error.details?.current;
      if (current && typeof current.version === 'number') {
        // another device wrote it first: its value wins here too
        const server = asText(current.value);
        state.set(key, { value:server, version:current.version });
        keep(key, server);
      } else if (again) {
        state.delete(key);                                                   // the row is gone: written again as new
        await put(key, false);
      }
      return;
    }
    if (res.status === 422 && error?.code === 'PREFERENCE_LIMIT') refused.add(key);
    else if (res.status === 403 && isAccessRefusal(readError(res.status, body))) refused.add(key);
  }
  function note(key: string) {
    if (!on || !SYNC_KEYS.includes(key) || refused.has(key)) return;
    const t = timers.get(key); if (t) clearTimeout(t);
    timers.set(key, setTimeout(() => { void put(key) }, delay));
  }
  async function load(o: { uploadLocal?: boolean } = {}): Promise<boolean> {
    let res: Response;
    try { res = await client.send(PREFERENCES_URL) } catch { return false }
    if (!res.ok) { try { await res.text() } catch { /* gone */ } return false }   // 404: the route is not there (older server)
    let body: any = null;
    try { body = await res.json() } catch { return false }
    const items = body?.preferences;
    if (!items || typeof items !== 'object' || Array.isArray(items)) return false;
    if (typeof body.limits?.value_bytes === 'number') valueBytes = body.limits.value_bytes;
    state.clear(); refused.clear(); on = true;
    for (const [key, item] of Object.entries(items) as [string, any][]) {
      if (!SYNC_KEYS.includes(key) || !item || typeof item.version !== 'number') continue;
      const value = asText(item.value);
      state.set(key, { value, version:item.version });
      keep(key, value);
    }
    if (o.uploadLocal) for (const key of SYNC_KEYS) {
      let v: string | null = null;
      try { v = local()?.getItem(key) ?? null } catch { v = null }
      if (v !== null && !state.has(key)) await put(key);                     // once: the server holds it from now on
    }
    if (!listening && typeof addEventListener === 'function') { listening = true; addEventListener('storage', onStorage as EventListener) }
    return true;
  }
  function stop() { on = false; timers.forEach(t => clearTimeout(t)); timers.clear(); state.clear() }
  async function flush() { const keys = [...timers.keys()]; timers.forEach(t => clearTimeout(t)); timers.clear(); await Promise.all(keys.map(k => put(k))) }
  return { load, note, stop, flush, get active() { return on }, state, refused };
}
/** the shell's account preferences (on the page's session) */
export const prefs = preferences(edge);
