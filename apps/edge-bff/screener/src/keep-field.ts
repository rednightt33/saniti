/* ERRORS M373: an area the page redraws replaces the field the user is typing in, and the typed text and the focus are
   lost. Seen live on dev (2026-11-06): right after Screen now, the preview answer redrew the panel while "AALI" was
   being typed in "Look up a ticker"; the box came back empty and without focus.
   press.ts holds a drawing while a pointer is pressed; this module covers the keyboard. Every area renderer that
   rewrites its host (app.ts renderHeader, results.ts renderResults, builder.ts renderConds, universe-ui.ts
   renderUniverse and its pop and drawer, presets-ui.ts renderPresets, preview.ts renderDetails) draws through
   keepField. Before the drawing it notes the focused control of the host. After it, it finds that control again by its
   id or its data attributes and puts the focus back.
   A text field is also given back its text and caret, but only text typed and not yet sent:
   - an input event marks the field;
   - a change, Enter or Escape unmarks it (the page acts on the field then, and its own drawing wins: a picked ticker
     empties the lookup, a committed value is the state's).
   When the text is given back, an input event is sent, so the page's own handlers see the box as it is (the lookup's
   suggestions, the number debounce of app.ts). */

const typed = new WeakSet<Element>();

const TEXT = /^(text|search|number|email|url|tel|password)$/;
const isText = (el: Element): el is HTMLInputElement | HTMLTextAreaElement =>
  el instanceof HTMLTextAreaElement || (el instanceof HTMLInputElement && TEXT.test(el.type || 'text'));

/** how to find a control again in a redrawn host: its id, else its tag with its name and data attributes */
export function selectorOf(el: Element): string | null {
  if (!(el instanceof HTMLElement)) return null;
  if (el.id) return '#' + CSS.escape(el.id);
  const parts = [...el.attributes].filter(a => a.name.startsWith('data-') || a.name === 'name')
    .map(a => `[${a.name}="${CSS.escape(a.value)}"]`);
  return parts.length ? el.tagName.toLowerCase() + parts.join('') : null;
}

interface Noted { sel: string; text: string | null; start: number | null; end: number | null }

function note(host: Element): Noted | null {
  const a = document.activeElement;
  if (!a || a === host || !host.contains(a)) return null;
  const sel = selectorOf(a); if (!sel) return null;
  if (!isText(a) || !typed.has(a)) return { sel, text:null, start:null, end:null };
  let start: number | null = null, end: number | null = null;
  try { start = a.selectionStart; end = a.selectionEnd } catch { /* a number field has no caret position */ }
  return { sel, text:a.value, start, end };
}

function restore(host: Element, n: Noted | null) {
  if (!n) return;
  const el = host.querySelector(n.sel) as HTMLElement | null;
  if (!el || el === document.activeElement) return;
  if (n.text != null && isText(el)) {
    const changed = el.value !== n.text;
    el.value = n.text; typed.add(el);
    el.focus({ preventScroll:true });
    try { if (n.start != null) el.setSelectionRange(n.start, n.end ?? n.start) } catch { /* a number field */ }
    if (changed) el.dispatchEvent(new Event('input', { bubbles:true }));
    return;
  }
  el.focus({ preventScroll:true });
}

/** run `draw`, which rewrites `host`, and give the focused control of `host` back its focus (and its unsent text) */
export function keepField(host: Element | null, draw: () => void) {
  const n = host ? note(host) : null;
  draw();
  if (host) restore(host, n);
}

/** Watch typing in `doc` (capture phase, before the page's own handlers act on the field). */
export function bindKeepField(doc: EventTarget) {
  doc.addEventListener('input', e => { const t = e.target as Element; if (t && isText(t)) typed.add(t) }, true);
  doc.addEventListener('change', e => { typed.delete(e.target as Element) }, true);
  doc.addEventListener('keydown', e => { const k = (e as KeyboardEvent).key; if (k === 'Enter' || k === 'Escape') typed.delete(e.target as Element) }, true);
}
