/* When the table needs the worker (report 6c.4 S5 and S8): a screen without an active condition and without a metric
   filter the page cannot evaluate is listed from the universe rows, no run; any other definition is sent as POST run,
   debounced 350 ms after an edit, latest wins (the previous fetch is aborted, as backtest/src/preview.ts; edge-bff's
   unless_gone then cancels the worker call). The previous result stays visible, marked out of date, with the ring.
   Failures follow report 6c.6: BUSY retries twice (1 s, 2 s), NOT_READY after Retry-After, an unreachable service
   once after 2 s, then a message and a Retry button; refusals are shown with the field and the fix (report 8.8). */
import { ApiFailure, isAbort } from './api/types.ts';
import { activeCards, canonical, cardOfField, ctx, definitionOf, rowOfResult, rowOfUniverse, S, ui, type Result } from './state.ts';
import { universeView } from './universe-view.ts';
import { errorText, T } from './texts.ts';
import type { Definition, RunResponse } from './core/contract.ts';

export const DEBOUNCE_MS = 350;
let timer: ReturnType<typeof setTimeout> | undefined, ctl: AbortController | null = null, attempt = 0, wantKey = '';
/** the definition the worker last refused (a 4xx refusal, or a 504 TIMEOUT / 503 SCREENER_DISABLED, which 6c.6 does
    not retry): not sent again until it changes or the user presses Retry, so an unrelated re-render never repeats it */
let refusedKey = '';
/** a hook the app sets: a run answer and its bytes (kept for the cached paint, 6c.3) */
export const runHooks = { answered:(_def: Definition, _bytes: Uint8Array, _r: RunResponse) => {}, mark:(_n: string) => {} };

/** whether the definition can be listed from the universe rows alone (no run): 'local', 'run', or 'wait' while the
    universe has not answered yet */
export function localOnly(def: Definition): 'local' | 'run' | 'wait' {
  if (def.conditions.some(c => c.enabled) || !universeView([], def.universe).exact) return 'run';
  return ctx.universe ? 'local' : 'wait';
}
/** the result of a definition listed from the universe rows (no run) */
export function localResult(def: Definition, key: string): Result | null {
  if (!ctx.universe) return null;
  const v = universeView(ctx.universe.rows, def.universe);
  return { rows:v.rows.map(rowOfUniverse), run:null, defHash:key, eligible:v.counts.eligible, listed:v.counts.listed, staleHidden:v.counts.stale_hidden, breakHidden:v.counts.price_break_hidden };
}
export const resultOf = (r: RunResponse, key: string): Result => ({ rows:r.rows.map(rowOfResult), run:r, defHash:key, eligible:r.universe.eligible,
  listed:r.universe.listed, staleHidden:r.universe.stale_hidden, breakHidden:r.universe.price_break_hidden });

/** Bring the table to the current definition: at once when local, else a run after DEBOUNCE_MS (`now`: at once). */
export function schedule(now = false) {
  clearTimeout(timer);
  if (!ctx.catalog) return;
  const def = definitionOf(), key = canonical(def);
  if (key !== wantKey) ctx.refused = null;                    // an edit: the refusal of the previous definition goes
  const lim = ctx.catalog.limits.find(l => l.name === 'max_conditions');
  if (Object.keys(S.errors).length) {
    ctl?.abort(); ctl = null; ctx.running = false; ctx.stale = !!ctx.R; ctx.runError = 'Fix the highlighted field of a condition; the screen runs once every field is valid.';
    ui.refresh('results'); return;
  }
  if (lim && activeCards().length > lim.value) {
    ctl?.abort(); ctl = null; ctx.running = false; ctx.stale = !!ctx.R; ctx.runError = `${lim.rule}. Switch off or remove ${activeCards().length - lim.value} condition(s). Allowed: ${lim.example_ok}. Refused: ${lim.example_refused}.`;
    ui.refresh('results'); return;
  }
  const how = localOnly(def);
  if (how !== 'run') {
    ctl?.abort(); ctl = null; ctx.running = false; ctx.runError = null; ctx.stale = false; wantKey = key;
    const r = how === 'local' ? localResult(def, key) : null; if (r) { ctx.R = r; runHooks.mark('results') }
    ui.refresh('results'); return;
  }
  if (ctx.R?.defHash === key && ctx.R.run && !now) { ctx.stale = false; ctx.running = false; ui.refresh('results'); return }
  if (key === refusedKey && !now) { ui.refresh('results'); return }       // still refused: the message stays
  refusedKey = '';
  if (key === wantKey && ctl && !now) return;     // the same definition is already on its way
  wantKey = key; attempt = 0;
  ctx.stale = !!ctx.R && ctx.R.defHash !== key; ctx.runError = null;
  ctx.running = true; ui.refresh('results');
  timer = setTimeout(() => send(def, key), now ? 0 : DEBOUNCE_MS);
}

async function send(def: Definition, key: string) {
  ctl?.abort();
  const c = new AbortController(); ctl = c;
  ctx.running = true;
  try {
    const { body, bytes } = await ctx.api.run({ schema_version:1, definition:def, options:{ exhaustive:false, explain:false } }, { signal:c.signal });
    if (ctl !== c) return;
    ctl = null; attempt = 0;
    ctx.R = resultOf(body, key); ctx.running = false; ctx.stale = false; ctx.runError = null;
    runHooks.mark('results');
    runHooks.answered(def, bytes, body);
    ui.versionSeen(body.versions);
    ui.refresh('results');
  } catch (e) {
    if (isAbort(e) || ctl !== c) return;
    ctl = null;
    const f = e instanceof ApiFailure ? e : new ApiFailure(T.unreachable, 'NETWORK');
    if (f.code === 'SCREEN_REPLACED') return;                     // a newer answer follows
    const again = (ms: number, msg: string) => { attempt++; ctx.runError = msg; ui.refresh('results'); timer = setTimeout(() => { if (wantKey === key) send(def, key) }, ms) };
    if (f.code === 'BUSY' && attempt < 2) return again(1000 * (attempt + 1), errorText('BUSY'));
    if (f.code === 'SCREENER_NOT_READY') return again(Math.max(1, f.retryAfter ?? 5) * 1000, f.message);
    if ((f.code === 'SCREENER_UNAVAILABLE' || f.code === 'NETWORK') && attempt < 1) return again(2000, T.unreachable);
    ctx.running = false; ctx.runError = f.message || T.unreachable;
    // 6c.6: a refusal (4xx), 504 TIMEOUT and 503 SCREENER_DISABLED are not retried: the same definition is sent again
    // only after an edit or Retry (BUSY, NOT_READY and an unreachable service took their retries above)
    if ((f.status >= 400 && f.status < 500) || f.code === 'TIMEOUT' || f.code === 'SCREENER_DISABLED') refusedKey = key;
    const card = cardOfField(f.field);
    ctx.refused = card ? { id:card.id, message:f.message || T.unreachable } : null;
    if (card) ui.renderConds();                                      // the card names the refusal (no new run)
    ui.refresh('results');
  }
}
/** forget the in-flight run (a new catalog or a reset) */
export function cancelRun() { clearTimeout(timer); ctl?.abort(); ctl = null; wantKey = ''; refusedKey = ''; ctx.running = false }
