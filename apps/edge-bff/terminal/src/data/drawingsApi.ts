/* EXEC-DRAW-PANES (user 2026-11-07: "semua gambar harus di simpan di akun EDGE, sama seperti trading view"; "3 jalankan
   dulu"): the drawings on the EDGE account (apps/edge-bff/app/drawings.py, /api/v1/terminal/drawings; table
   edge_bff.terminal_drawings). One set per ticker and place: 'chart', 'flow', or 'pane_' and an indicator pane's id.

   The page keeps working without the account: when the account cannot be read (no connection, the table not there yet),
   a set is kept in this browser as before and moves to the account the next time it can be read. The sets kept in this
   browser before (ml.drawings.*) move to the account once, merged by drawing id with what the account holds.
   A refusal of the plan (403 CAPABILITY_REQUIRED or PLAN_EXPIRED: the plan holds no terminal.drawings) is not an outage
   (re-check R1-19): its own words are said, and nothing is kept in this browser for it (a copy there is dropped). */
import { savedClient, sendOnLeave, primeToken, LayoutApiError } from './layoutsApi';
import { store } from '../app/context';
import { edge, isLastLogin, loginKey, onReset } from '../../../shared/edge-session';

/* M468 (EXEC-MU-ACCOUNTS Phase 0): a copy kept in this browser is stamped with the login that wrote it,
   {"owner": login, "drawings": [...]}, and joins the account only for that login. A copy of the older form (a bare
   list, no owner) joins only when the login signed in is the one this browser signed in with last (the shell's mark,
   shared/edge-session.ts); any other copy is dropped, never shown and never written to this account. */
export function ownCopy(text: string | null, login: string): unknown[] | null {
  if (!text) return null;
  let v: any;
  try { v = JSON.parse(text) } catch { return null }
  if (Array.isArray(v)) return isLastLogin(login) ? v : null;
  if (v && typeof v === 'object' && Array.isArray(v.drawings)) return !!loginKey(login) && v.owner === loginKey(login) ? v.drawings : null;
  return null;
}
/** the text kept in this browser for `login`; null when the login is not known (nothing is kept then: a copy without
    an owner could join whichever account the browser marks next) */
export function stampCopy(text: string, login: string): string | null {
  const owner = loginKey(login);
  if (!owner) return null;
  try { return JSON.stringify({ owner, drawings:JSON.parse(text) }) } catch { return null }
}
/* the account this page opened with (its first session read), never the browser's last-login mark: that mark moves to
   another account when one signs in in another tab (C1 M2, C2 #3). Phase 1: the session's stable owner key. */
const signedIn = () => edge.identity;
const keepCopy = (local: string, text: string) => { const stamped = stampCopy(text, signedIn()); if (stamped !== null) store.set(local, stamped) };

const BASE = '/api/v1/terminal/drawings';
const call = savedClient(BASE, 'drawing');
export const TICKER = /^[A-Z0-9]{1,12}$/;                  // terminal-api's ticker rule (app/drawings.py)
export const SET_ID = /^(chart|flow|pane_[0-9a-f]{16})$/;  // app/drawings.py, migration 20261107_001
export const newPaneId = () => [...crypto.getRandomValues(new Uint8Array(8))].map(b => b.toString(16).padStart(2, '0')).join('');

interface ServerSet { ticker: string; set_id: string; drawings: unknown[]; revision: number }
export const drawingsApi = {
  list: (ticker: string) => call<{ sets: ServerSet[] }>('GET', `?ticker=${encodeURIComponent(ticker)}`),
  put: (ticker: string, setId: string, drawings: unknown[], revision?: number | null) =>
    call<ServerSet>('PUT', `/${ticker}/${setId}`, { drawings, ...(revision ? { revision } : {}) }),
  remove: (ticker: string, setId: string) => call<void>('DELETE', `/${ticker}/${setId}`)
};

/** keeps the stored text of every set in step with the account: load (with the one-time move of this browser's set), save
    (a short pause after the last change, then one write), remove; `say` reports a refusal in a plain sentence */
export function accountDrawings(say: (text: string, error?: boolean) => void, SAVE_MS = 400) {
  // per ticker: its sets, null (unreachable), or the plan's refusal
  const lists = new Map<string, Promise<Map<string, ServerSet> | LayoutApiError | null>>();
  let locked = false;                                                        // the plan refused the drawings
  const rev = new Map<string, number | null>();                              // `${ticker}/${set}` -> the revision held
  const last = new Map<string, string>();                                    // the text the account holds
  const pending = new Map<string, { json: string; timer: any }>();
  let warned = false;
  const k = (t: string, s: string) => `${t}/${s}`;
  const fits = (t: string, s: string) => TICKER.test(t) && SET_ID.test(s);
  const listOf = (t: string) => {
    let p = lists.get(t);
    if (!p) {
      p = drawingsApi.list(t).then(r => new Map(r.sets.map(x => [x.set_id, x])),
        (e: unknown) => e instanceof LayoutApiError && e.access ? e : null);
      lists.set(t, p);
    }
    return p;
  };
  const unreachable = () => {
    if (warned) return; warned = true;
    say('Your drawings could not be saved to your EDGE account just now: they are kept in this browser and move to the account when it can be reached.', true);
  };
  /* the plan's refusal: said once in its own words; nothing of the drawings stays in this browser for it */
  const refused = (e: LayoutApiError, local?: string) => {
    if (local) store.remove(local);
    if (locked) return; locked = true;
    say(e.message, true);
  };
  primeToken();
  // the account ended or changed (a 401, the 'cleared' broadcast): pending changes are dropped, never stamped or sent
  onReset(() => { pending.forEach(p => clearTimeout(p.timer)); pending.clear() });

  /** the stored text of a set; `local` is this browser's key for it (kept, or moved to the account once) */
  async function load(t: string, s: string, local: string): Promise<string> {
    const here = store.get(local);
    if (!fits(t, s)) return here || '[]';
    const sets = await listOf(t);
    // Phase 1: the page's identity (owner:<owner key> once the session carries it, else the login), as the stamps hold
    const who = await edge.session().then(() => edge.identity, () => edge.identity);
    const mine = ownCopy(here, who);
    if (here !== null && mine === null) store.remove(local);          // M468: another login's copy (or not a list)
    if (sets instanceof LayoutApiError) { refused(sets, local); return '[]' }
    if (!sets) { unreachable(); return mine ? JSON.stringify(mine) : '[]' }
    const got = sets.get(s);
    rev.set(k(t, s), got ? got.revision : null);
    let text = got ? JSON.stringify(got.drawings) : '[]';
    last.set(k(t, s), text);
    if (mine && !mine.length) store.remove(local);
    if (mine && mine.length) {
      // the one-time move: this browser's drawings join the account's (a drawing the account has is kept as it is there)
      const ids = new Set((got?.drawings || []).map((d: any) => d && d.id).filter(Boolean));
      const merged = [...(got?.drawings || []), ...mine.filter((d: any) => !(d && d.id && ids.has(d.id)))];
      if (merged.length !== (got?.drawings || []).length) {
        text = JSON.stringify(merged);
        if (await write(t, s, text)) store.remove(local);
      } else store.remove(local);
    }
    return text;
  }

  /** one write of the set's current text; a revision another tab moved on is read again and the write repeated once
      (the newest change on screen wins); true when the account holds it, 'refused' when the plan refused it */
  async function write(t: string, s: string, text: string, again = true): Promise<boolean | 'refused'> {
    const key = k(t, s);
    if (last.get(key) === text) return true;
    try {
      const r = await drawingsApi.put(t, s, JSON.parse(text), rev.get(key));
      rev.set(key, r.revision); last.set(key, text); return true;
    } catch (e: any) {
      if (e instanceof LayoutApiError && again && (e.status === 409 || e.status === 404)) {
        const fresh = await drawingsApi.list(t).then(r => r.sets.find(x => x.set_id === s) || null, () => undefined);
        if (fresh !== undefined) { rev.set(key, fresh ? fresh.revision : null); last.delete(key); return write(t, s, text, false) }
      }
      if (e instanceof LayoutApiError && e.access) { refused(e); return 'refused' }
      if (e instanceof LayoutApiError && e.status === 422) say(e.message, true);
      else if (e instanceof LayoutApiError && (e.status === 0 || e.status >= 500)) unreachable();
      else say(e?.message || 'Your drawings could not be saved. Try again in a minute.', true);
      return false;
    }
  }

  /** a change: written a moment after the last one (a drag sends many); kept in this browser if the account is away */
  function save(t: string, s: string, text: string, local: string) {
    if (!fits(t, s)) { store.set(local, text); return }
    const key = k(t, s), was = pending.get(key);
    if (was) clearTimeout(was.timer);
    const timer = setTimeout(async () => {
      pending.delete(key);
      const sets = await listOf(t);
      if (sets instanceof LayoutApiError) { refused(sets, local); return }
      if (!sets) { keepCopy(local, text); unreachable(); return }
      const wrote = await write(t, s, text);
      if (wrote === 'refused') store.remove(local);
      else if (!wrote) keepCopy(local, text);                  // not lost: moves to the account on the next load
    }, SAVE_MS);
    pending.set(key, { json:text, timer });
  }

  /** a pane removed by the user: its set leaves the account (Undo puts it back through save) */
  async function remove(t: string, s: string) {
    const key = k(t, s), was = pending.get(key);
    if (was) { clearTimeout(was.timer); pending.delete(key) }
    if (!fits(t, s) || rev.get(key) == null) return;
    try { await drawingsApi.remove(t, s) } catch { /* already gone */ }
    rev.set(key, null); last.delete(key);
  }

  /* a change still waiting as the page goes away is sent then (keepalive; a set over the browser's 64 KB keepalive limit
     stays in this browser and moves on the next load) */
  window.addEventListener('pagehide', () => pending.forEach(({ json, timer }, key) => {
    clearTimeout(timer);
    if (locked) return;                                      // the plan refused the drawings: nothing sent or kept
    const [t, s] = key.split('/'), r = rev.get(key);
    if (json.length < 60000) sendOnLeave(`${BASE}/${t}/${s}`, 'PUT', { drawings:JSON.parse(json), ...(r ? { revision:r } : {}) });
    keepCopy(s === 'chart' ? `ml.drawings.${t}` : s === 'flow' ? `ml.drawings.flow.${t}` : `ml.drawings.pane.${t}.${s.slice(5)}`, json);
  }));

  return { load, save, remove, flushNow: () => pending.forEach((p, key) => { clearTimeout(p.timer); pending.delete(key); const [t, s] = key.split('/'); write(t, s, p.json) }) };
}
