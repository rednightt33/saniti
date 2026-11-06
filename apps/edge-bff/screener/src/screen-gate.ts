/* EXEC-SCREENER-V21: the Screen now controls (product decision 6: an edit does not replace the table; the previous
   table stays visible, marked out of date, until Screen now). The reference's design (three-panel v21, layout.js
   "Screen now") is ported onto the page's own state: run.ts owns the gate (screenPhase, screenReady, screenBlocked,
   screenNow); this module draws it and binds its clicks and shortcuts, once.
   - .top-screen, first in #pageActs (app.ts renderHeader writes the other actions after it): "Screen now" / "Screening…" /
     "Up to date", with the shortcut;
   - .screen-bar in #screenBar (the bottom of the builder pane): the same button, full width, with a hint line that
     names why it cannot run (a field to fix, too many conditions) or what it does;
   - .pend in #pendBar (above the table), shown only while the screen has changed: "Your screen changed. The table
     still shows the previous results." and Screen now.
   Shortcuts (the reference's): Alt+S and Ctrl/Cmd+Enter. Alt+S is left alone inside a text field (on some keyboards it
   types a letter); Ctrl/Cmd+Enter types nothing and works in every field outside a dialog. A number typed but not yet
   applied (app.ts debounces number fields by 350 ms) is applied first (gateHooks.flush), so the shortcut screens what
   the field shows. A button that cannot run is aria-disabled (it stays focusable and its reason readable), never
   removed. */
import { ctx } from './state.ts';
import { screenBlocked, screenNow, screenPhase, screenReady } from './run.ts';
import { esc } from './format.ts';
import { dialogOpen } from './dialogs.ts';
import { afterPress } from './press.ts';

/** app.ts sets flush: apply a number field the user typed in and that its 350 ms debounce has not applied yet */
export const gateHooks = { flush:() => {} };

// SVG path data written without spaces (tests/page/plain-words.test.ts reads every sentence-like string of the page)
const PLAY_D = 'M7,5v14l11-7Z', CLOCK_D = 'M12,7v5l3,2';
const PLAY = `<svg class="ico s" viewBox="0 0 24 24" aria-hidden="true"><path d="${PLAY_D}"/></svg>`;
const CLOCK = `<svg class="ico s" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="${CLOCK_D}"/></svg>`;
export const SHORTCUTS = 'Alt+S Control+Enter Meta+Enter';
export const TEXTS = {
  now:'Screen now', running:'Screening…', clean:'Up to date',
  changed:'Your screen changed. The table still shows the previous results.',
  hintNow:'Runs the screen and updates the table · Alt+S',
  hintClean:'Change a condition, preset or filter, then screen',
  hintRunning:'Screening the current conditions…',
  hintRefused:'This screen did not run. Change it, or press Retry above the table to send it again.',
  hintFailed:'The last screen did not finish. Screen now tries again.',
  titleClean:'The table matches the current screen',
};

/** what the three controls show now */
export interface GateView { phase: ReturnType<typeof screenPhase>; ready: boolean; label: string; hint: string; blocked: string | null }
export function gateView(): GateView {
  const phase = screenPhase(), ready = screenReady(), blocked = phase === 'pending' || phase === 'error' ? screenBlocked() : null;
  const label = phase === 'running' ? TEXTS.running : phase === 'clean' ? TEXTS.clean : TEXTS.now;
  const hint = phase === 'running' ? TEXTS.hintRunning : blocked ? blocked : phase === 'pending' ? TEXTS.hintNow
    : phase === 'error' ? (ready ? TEXTS.hintFailed : TEXTS.hintRefused) : TEXTS.hintClean;
  return { phase, ready, label, hint, blocked };
}
const dis = (v: GateView) => v.ready ? '' : ' aria-disabled="true"';
const busy = (v: GateView) => v.phase === 'running' ? ' aria-busy="true"' : '';

/** the top button's title: what it does, or why it cannot run */
const topTitle = (v: GateView) => v.ready ? 'Run the screen and update the table (Alt+S)' : v.phase === 'clean' ? TEXTS.titleClean : v.hint;
/** the page action (first in #pageActs; drawn here, app.ts renderHeader writes the actions after it) */
export function topScreenHtml(v = gateView()): string {
  return `<button type="button" class="btn top-screen${v.ready ? ' ready' : ''}" data-screen aria-keyshortcuts="${SHORTCUTS}" title="${esc(topTitle(v))}"${dis(v)}${busy(v)}>${PLAY}<span data-slabel>${esc(v.label)}</span><kbd>Alt+S</kbd></button>`;
}
/** the builder pane's bar (#screenBar) */
export function screenBarHtml(v = gateView()): string {
  return `<div class="screen-bar"><button type="button" class="btn primary block${v.ready ? ' ready' : ''}" data-screen aria-keyshortcuts="${SHORTCUTS}" aria-describedby="screenHint"${dis(v)}${busy(v)}>${PLAY}<span data-slabel>${esc(v.label)}</span></button><small id="screenHint" data-shint${v.blocked ? ' class="down"' : ''}>${esc(v.hint)}</small></div>`;
}
/** the out-of-date bar's message (#pendBar [data-pmsg]) */
const pendMsg = (v: GateView) => `${esc(TEXTS.changed)}${v.blocked ? ` <b class="down">${esc(v.blocked)}</b>` : ''}`;
/** the out-of-date bar's content (#pendBar; shown only while the screen changed) */
export function pendHtml(v = gateView()): string {
  return `${CLOCK}<span data-pmsg>${pendMsg(v)}</span><button type="button" class="btn sm primary" data-screen aria-keyshortcuts="${SHORTCUTS}"${dis(v)}>${esc(TEXTS.now)}</button>`;
}

/* ---- drawing (ui.renderScreen). Each control is created once and then patched in place (its class, aria-disabled,
   aria-busy, title and texts), never re-created: a button replaced between the press and the release of a pointer
   loses its click (QA H1, ERRORS M357; press.ts holds the other areas' drawing during a press). A text is written
   only when it changed, so the live region of the out-of-date bar speaks once per change and the focus stays. ---- */
function patchButton(b: HTMLElement, v: GateView, label: string, title?: string) {
  b.classList.toggle('ready', v.ready);
  if (v.ready) b.removeAttribute('aria-disabled'); else b.setAttribute('aria-disabled', 'true');
  if (v.phase === 'running') b.setAttribute('aria-busy', 'true'); else b.removeAttribute('aria-busy');
  if (title !== undefined && b.title !== title) b.title = title;
  const l = b.querySelector('[data-slabel]');
  if (l && l.textContent !== label) l.textContent = label;
}
const drawn = { pmsg:'', pending:null as boolean | null };
export function renderScreen() {
  if (typeof document === 'undefined') return;
  // under a pressed pointer nothing moves: the out-of-date bar appearing above the table would push the pressed
  // control away from the pointer before its release (QA H1, ERRORS M357)
  if (afterPress('screen', renderScreen)) return;
  const v = gateView(), pending = v.phase === 'pending';
  const acts = document.getElementById('pageActs');
  if (acts) {
    const top = acts.querySelector<HTMLElement>('.top-screen');
    if (top) patchButton(top, v, v.label, topTitle(v)); else acts.insertAdjacentHTML('afterbegin', topScreenHtml(v));
  }
  const bar = document.getElementById('screenBar');
  if (bar) {
    const b = bar.querySelector<HTMLElement>('.screen-bar [data-screen]'), hint = bar.querySelector<HTMLElement>('[data-shint]');
    if (!b || !hint) bar.innerHTML = screenBarHtml(v);
    else {
      patchButton(b, v, v.label);
      if (hint.textContent !== v.hint) hint.textContent = v.hint;
      hint.classList.toggle('down', !!v.blocked);
    }
  }
  const pend = document.getElementById('pendBar');
  if (pend) {
    if (!pend.classList.contains('pend')) { pend.classList.add('pend'); pend.setAttribute('role', 'status'); pend.setAttribute('aria-live', 'polite') }
    if (!pending) { if (pend.firstChild) pend.innerHTML = ''; drawn.pmsg = '' }   // emptied, so the next change is spoken
    else {
      const msg = pend.querySelector<HTMLElement>('[data-pmsg]'), b = pend.querySelector<HTMLElement>('[data-screen]');
      if (!msg || !b) { pend.innerHTML = pendHtml(v); drawn.pmsg = pendMsg(v) }
      else {
        const m = pendMsg(v);
        if (drawn.pmsg !== m) { msg.innerHTML = m; drawn.pmsg = m }
        patchButton(b, v, TEXTS.now);
      }
    }
    pend.hidden = !pending;
  }
  if (drawn.pending !== pending) { drawn.pending = pending; document.body.classList.toggle('scr-pending', pending) }
}

/* ---- events, bound once --------------------------------------------------------------------------------------- */
const TEXT_TYPES = /^(text|search|email|url|tel|password)$/;
/** a field where Alt+S may type a character (left alone by the shortcut) */
export function typingTarget(el: Element | null): boolean {
  if (!el) return false;
  const h = el as HTMLElement;
  if (h.isContentEditable) return true;
  if (el.tagName === 'TEXTAREA') return true;
  return el.tagName === 'INPUT' && TEXT_TYPES.test(((el as HTMLInputElement).type || 'text').toLowerCase());
}
/** Which shortcut a key event is: 'alt-s', 'mod-enter' or null (exported for the tests). */
export function shortcutOf(e: Pick<KeyboardEvent, 'altKey' | 'ctrlKey' | 'metaKey' | 'shiftKey' | 'key' | 'code' | 'repeat' | 'isComposing'>): 'alt-s' | 'mod-enter' | null {
  if (e.repeat || e.isComposing) return null;
  if (e.altKey && !e.ctrlKey && !e.metaKey && (e.code === 'KeyS' || e.key === 's' || e.key === 'S')) return 'alt-s';
  if ((e.ctrlKey || e.metaKey) && !e.altKey && !e.shiftKey && e.key === 'Enter') return 'mod-enter';
  return null;
}
function go() { gateHooks.flush(); if (screenReady()) screenNow() }

let bound = false;
export function bindScreenGate() {
  if (bound || typeof document === 'undefined') return; bound = true;
  document.addEventListener('click', e => {
    const b = (e.target as HTMLElement | null)?.closest?.('[data-screen]'); if (!b) return;
    e.preventDefault(); go();
  });
  document.addEventListener('keydown', e => {
    const k = shortcutOf(e); if (!k) return;
    if (dialogOpen()) return;                                   // a dialog's own keys (save, confirm) come first
    if (k === 'alt-s' && typingTarget(document.activeElement)) return;
    if (!ctx.catalog) return;
    e.preventDefault(); go();
  });
}
