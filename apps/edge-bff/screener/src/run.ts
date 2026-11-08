/* The table and the definition it answers (report 6c.4 S5 and S8), behind the explicit Screen now gate of
   EXEC-SCREENER-V21 (product decision 6, user 2026-11-06: "Editing a condition does not replace the table at once: the
   previous table stays visible, marked out of date, until the user presses Screen now").
   - An edit (universe, quick filter, condition, parameter, logic, at least, a preset, Reset, Duplicate) changes the
     page's definition only: no request, the table stays, ctx.pending and ctx.stale say it no longer answers the page
     (sync, called by app.ts refresh after every edit). This holds for a definition listed locally from the universe
     rows too: it is listed on Screen now, not before.
   - A screen is brought to the table only by go(): Screen now (screenNow: the buttons, Alt+S, Ctrl/Cmd+Enter), the
     page boot restoring the last screen (its cached result when its versions equal the catalog's, else a run), opening
     a saved screen, Retry (retry), and a publication change (republished: the definition the table answered, never
     the pending edits).
   - A screen without an active condition and without a metric filter the page cannot evaluate is listed from the
     universe rows (no run); any other is sent as POST run at once, latest wins (the previous fetch is aborted, as
     backtest/src/preview.ts; edge-bff's unless_gone then cancels the worker call). The previous result stays visible,
     marked out of date, with the ring.
   - Failures follow report 6c.6: BUSY retries twice (1 s, 2 s), NOT_READY after Retry-After, an unreachable service
     once after 2 s, then a message and a Retry button; refusals are shown with the field and the fix (report 8.8).
   The auxiliary request of the extra columns (extra-columns.ts) runs on its own client_order page only after the main
   run has settled; every main run cancels it first. */
import { ApiFailure, isAbort } from './api/types.ts';
import { sameVersions } from './api/boot-cache.ts';
import { activeCards, canonical, cardOfField, ctx, definitionOf, rowOfResult, rowOfUniverse, S, stateOfDefinition, ui, type Result, type ScreenPhase } from './state.ts';
import { universeView } from './universe-view.ts';
import { errorText, T } from './texts.ts';
import type { Definition, RunResponse } from './core/contract.ts';
import type { Card } from './forms.ts';
import { extraCancel, extraKick } from './extra-columns.ts';

interface Want { def: Definition; key: string; name: string }
/** the definition last brought to the table (asked by Screen now, the boot, a saved screen, Retry or a publication
    change): the table answers it, or its run is on its way, or it failed (ctx.runError) */
let want: Want | null = null;
let timer: ReturnType<typeof setTimeout> | undefined, ctl: AbortController | null = null, attempt = 0;
/** the definition the worker last refused (a 4xx refusal, or a 504 TIMEOUT / 503 SCREENER_DISABLED, which 6c.6 does
    not retry): not sent again by Screen now until it changes; Retry sends it again */
let refusedKey = '';
/** a hook the app sets: a run answer and its bytes (kept for the cached paint, 6c.3) */
export const runHooks = { answered:(_def: Definition, _bytes: Uint8Array, _r: RunResponse) => {}, mark:(_n: string) => {} };

/** whether the definition can be listed from the universe rows alone (no run): 'local', 'run', or 'wait' while the
    universe has not answered yet */
export function localOnly(def: Definition): 'local' | 'run' | 'wait' {
  if (def.conditions.some(c => c.enabled) || !universeView([], def.universe).exact) return 'run';
  return ctx.universe ? 'local' : 'wait';
}
/** the result of a definition listed from the universe rows (no run); `name` is the screen's name when it was screened */
export function localResult(def: Definition, key: string, name?: string): Result | null {
  if (!ctx.universe) return null;
  const v = universeView(ctx.universe.rows, def.universe);
  return { rows:v.rows.map(rowOfUniverse), run:null, defHash:key, def, name, eligible:v.counts.eligible, listed:v.counts.listed, staleHidden:v.counts.stale_hidden, breakHidden:v.counts.price_break_hidden };
}
export const resultOf = (r: RunResponse, key: string, def?: Definition, name?: string): Result => ({ rows:r.rows.map(rowOfResult), run:r, defHash:key, def, name, eligible:r.universe.eligible,
  listed:r.universe.listed, staleHidden:r.universe.stale_hidden, breakHidden:r.universe.price_break_hidden });

/* ---- the gate ------------------------------------------------------------------------------------------------ */
const pageKey = () => canonical(definitionOf());

/** Why Screen now cannot run the page's definition (a field the page refuses in place, more active conditions than
    max_conditions), in the words shown beside the disabled button; null when it can. Gate rule (AGENTS.md "Gates and
    evidence"): the rule and the fix are in the message, the catalog's examples of max_conditions with it. */
export function screenBlocked(): string | null {
  if (!ctx.catalog) return null;
  if (Object.keys(S.errors).length) return 'Fix the highlighted field of a condition; the screen runs once every field is valid.';
  const lim = ctx.catalog.limits.find(l => l.name === 'max_conditions'), n = activeCards().length;
  // the catalog's rule opens the sentence (the worker writes it in lower case, as a clause)
  const rule = lim ? lim.rule.charAt(0).toUpperCase() + lim.rule.slice(1).replace(/[.\s]+$/, '') : '';
  if (lim && n > lim.value) return `${rule}. Switch off or remove ${n - lim.value} condition(s). Allowed: ${lim.example_ok}. Refused: ${lim.example_refused}.`;
  return null;
}

/** Where the table stands against the page's definition: a run on its way; the page's definition differs from the
    one the table answers (pending, also when Screen now is blocked: screenBlocked says why); the last screen failed
    (error: ctx.runError, with Retry); or up to date (clean). */
export function screenPhase(): ScreenPhase {
  return ctx.running ? 'running' : ctx.pending ? 'pending' : ctx.runError ? 'error' : 'clean';
}
/** Whether Screen now would do something: a pending definition that is not blocked, or a failed screen that Screen now
    may send again (not one the worker refused: that one waits for an edit or Retry). */
export function screenReady(): boolean {
  const ph = screenPhase();
  if (ph === 'running' || ph === 'clean' || !ctx.catalog) return false;
  if (screenBlocked()) return false;
  return ph === 'pending' || pageKey() !== refusedKey;
}

/** The definition the table's rows answer, or the run on its way (the preview, the CSV and the extra columns describe
    these rows, never the pending edits); null before the first screen. */
export function screenedDefinition(): Definition | null {
  if (ctx.running && want) return want.def;
  return ctx.R?.def ?? null;
}
/** The cards of screenedDefinition (the condition columns, the preview's labels), mapped on the catalog's entries as a
    loaded definition is (state.ts stateOfDefinition); kept per definition key and catalog. */
let cardsMemo: { key: string; byKey: unknown; cards: Card[]; on: Card[] } | null = null;
export function screenedCards(all = false): Card[] {
  const d = screenedDefinition(); if (!d) return [];
  const key = canonical(d);
  if (!cardsMemo || cardsMemo.key !== key || cardsMemo.byKey !== ctx.byKey) { const cards = stateOfDefinition(d).cards; cardsMemo = { key, byKey:ctx.byKey, cards, on:cards.filter(c => c.on) } }
  return all ? cardsMemo.cards : cardsMemo.on;
}
/** The page card that a screened card is: the same id, on the same entry and test form (opt). A preset or a saved
    screen reuses ids ('a', 'b', …), so an id alone can name another indicator on the page (QA M1, ERRORS M358). The
    parameters may differ: that is the pending edit. null for a raw card, a My metric or a card not on the page. */
export function pageCardOf(c: Card): Card | null {
  if (!c.entry || c.raw || c.metric) return null;
  const p = S.cards.find(x => x.id === c.id);
  return p && p.entry === c.entry && p.opt === c.opt && !p.raw && !p.metric ? p : null;
}

/** After an edit (app.ts refresh, ui.schedule()): no request; the gate and the out-of-date mark follow the page's
    definition. A local definition asked for before the universe answered is listed now. */
export function sync() {
  if (!ctx.catalog) { ctx.pending = false; ui.renderScreen(); return }
  const key = pageKey();
  if (want && key !== want.key) ctx.refused = null;          // an edit: the refusal of the screened definition goes
  const late = !!want && !ctl && !ctx.running && ctx.R?.defHash !== want.key && !ctx.runError && localOnly(want.def) === 'local';
  if (late) listLocal(want!);
  mark(key);
  if (late) extraKick();
}
/** the gate's flags against the page's key; then the Screen now controls are drawn again */
function mark(key = pageKey()) {
  const answers = want?.key ?? ctx.R?.defHash ?? null;
  ctx.pending = !!ctx.catalog && key !== answers;
  ctx.stale = !!ctx.R && ctx.R.defHash !== key;
  ui.renderScreen();
}
/** the gate's flags, the table, then the extra columns (only once the main run has settled) */
function settle() {
  mark();
  ui.refresh('results');
  if (!ctx.running) extraKick();
}
function listLocal(w: Want) {
  const r = localResult(w.def, w.key, w.name);
  if (r) { ctx.R = r; runHooks.mark('results') }
}
function abortMain() { clearTimeout(timer); ctl?.abort(); ctl = null }

/** Bring `def` to the table. force: send it even when the table already answers it at the catalog's versions or the
    worker refused it (Retry); otherwise those cases send nothing. */
function go(def: Definition, key: string, force: boolean, name: string) {
  if (!ctx.catalog) { want = { def, key, name }; return }
  const before = want?.key;
  if (before !== key) ctx.refused = null;
  want = { def, key, name };
  const how = localOnly(def);
  if (how !== 'run') {                                         // listed from the universe rows, at once (no request)
    abortMain(); extraCancel();
    ctx.running = false; ctx.runError = null; refusedKey = '';
    if (how === 'local') listLocal(want);
    return settle();
  }
  const R = ctx.R;
  if (!force && R?.defHash === key && R.run && sameVersions(R.run.versions, ctx.catalog.versions)) {
    abortMain(); ctx.running = false; ctx.runError = null; return settle();
  }
  if (!force && key === refusedKey) { abortMain(); ctx.running = false; return settle() }   // still refused: its message stays
  if (!force && before === key && ctl) return settle();       // this definition is already on its way
  clearTimeout(timer);
  refusedKey = ''; attempt = 0; ctx.runError = null; ctx.running = true;
  extraCancel();                                               // a new main run cancels the auxiliary request
  send(def, key, name);
  settle();
}

/** Screen now (the top button, the builder bar, the out-of-date bar, Alt+S, Ctrl/Cmd+Enter; also the boot and an
    opened saved screen): bring the page's definition to the table. Nothing when it is blocked (screenBlocked). */
export function screenNow() {
  if (!ctx.catalog || screenBlocked()) { mark(); return }
  const def = definitionOf();
  go(def, canonical(def), false, S.name);
}
/** Retry (the results' button; ui.schedule(true); the preview's DATA_VERSION_CHANGED): send the screened definition
    again, even a refused one; never the pending edits. Before any screen: Screen now. */
export function retry() {
  const d = want?.def ?? ctx.R?.def;
  if (!d) return screenNow();
  go(d, canonical(d), true, want?.name ?? ctx.R?.name ?? S.name);
}
/** A publication change (a new catalog or universe, app.ts versionSeen and boot S4): the definition the table answered
    (or the one on its way) is brought to the new publication: a local one is listed again, a run is sent unless the
    table already answers it at the new versions. Never the pending edits. */
export function republished() {
  extraCancel();
  const d = ctx.running && want ? want.def : ctx.R?.def ?? want?.def;
  if (!d || !ctx.catalog) { mark(); return }
  go(d, canonical(d), false, (ctx.running && want ? want.name : ctx.R?.name ?? want?.name) ?? S.name);
}
/** The cached result of the remembered screen (app.ts restoreLast, 6c.4 S5), when its versions equal the catalog's. */
export function useCached(r: RunResponse, def: Definition, name = S.name) {
  const key = canonical(def);
  ctx.R = resultOf(r, key, def, name); want = { def, key, name };
}

async function send(def: Definition, key: string, name: string) {
  ctl?.abort();
  const c = new AbortController(); ctl = c;
  ctx.running = true;
  try {
    const { body, bytes } = await ctx.api.run({ schema_version:1, definition:def, options:{ exhaustive:false, explain:false } }, { signal:c.signal });
    if (ctl !== c) return;
    ctl = null; attempt = 0;
    ctx.R = resultOf(body, key, def, name); ctx.running = false; ctx.runError = null;
    runHooks.mark('results');
    runHooks.answered(def, bytes, body);
    ui.versionSeen(body.versions);
    settle();
  } catch (e) {
    if (isAbort(e) || ctl !== c) return;
    ctl = null;
    const f = e instanceof ApiFailure ? e : new ApiFailure(T.unreachable, 'NETWORK');
    if (f.code === 'SCREEN_REPLACED') return;                     // a newer answer follows
    const again = (ms: number, msg: string) => { attempt++; ctx.runError = msg; mark(); ui.refresh('results'); timer = setTimeout(() => { if (want?.key === key && ctx.running) send(def, key, name) }, ms) };
    if (f.code === 'BUSY' && attempt < 2) return again(1000 * (attempt + 1), errorText('BUSY'));
    if (f.code === 'SCREENER_NOT_READY') return again(Math.max(1, f.retryAfter ?? 5) * 1000, f.message);
    if ((f.code === 'SCREENER_UNAVAILABLE' || f.code === 'NETWORK') && attempt < 1) return again(2000, T.unreachable);
    ctx.running = false; ctx.runError = f.message || T.unreachable;
    // 6c.6: a refusal (4xx), 504 TIMEOUT and 503 SCREENER_DISABLED are not retried: the same definition is sent again
    // only after an edit or Retry (BUSY, NOT_READY and an unreachable service took their retries above)
    if ((f.status >= 400 && f.status < 500) || f.code === 'TIMEOUT' || f.code === 'SCREENER_DISABLED') refusedKey = key;
    // the refusal's field names a card of the definition that ran; it is marked on the page's card only while the
    // page still shows that definition (an edit since then is pending, and its cards may differ)
    const card = pageKey() === key ? cardOfField(f.field) : null;
    ctx.refused = card ? { id:card.id, message:f.message || T.unreachable } : null;
    if (card) ui.renderConds();                                      // the card names the refusal (no new run)
    settle();
  }
}

/** A preview or an extra-column request refused DATA_VERSION_CHANGED: the worker answers another publication than
    the one the table's rows came from. The screened definition runs again (retry), at most once per (definition, the
    rows' price_data, the catalog's price_data). A second refusal at the same three is not run again: a replica still
    behind the others, or a catalog edge-bff has not refreshed yet, would otherwise make every answer ask again (QA
    M3: 159 runs in 5 s, ERRORS M359). Then the caller shows its message with Retry, and nothing is sent until the
    user asks, the definition changes or a publication arrives. Returns whether a run was sent. */
let dataChangedAt = '';
export function dataChanged(): boolean {
  const d = screenedDefinition(); if (!d || !ctx.catalog) return false;
  const at = `${canonical(d)}|${ctx.R?.run?.versions.price_data ?? ''}|${ctx.catalog.versions.price_data}`;
  if (at === dataChangedAt) return false;
  dataChangedAt = at; retry(); return true;
}

/** The old entry point (ui.schedule): without an argument an edit (sync: no request), with `true` Retry. */
export function schedule(now = false) { if (now) retry(); else sync() }
/** forget the in-flight run and what was asked (tests; a new page state that must not keep the old one's run) */
export function cancelRun() { abortMain(); extraCancel(); want = null; refusedKey = ''; dataChangedAt = ''; ctx.running = false; mark() }
