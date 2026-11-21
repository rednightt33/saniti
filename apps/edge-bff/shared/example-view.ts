/* EXEC-MU-ACCOUNTS 3e, the example mode as the user set it on 2026-11-21 (EXEC.md option A; ERRORS M527): "user hanya
   bisa view data terakhir. Dia tidak bisa klik tombol. Kalau dia klik tombol, maka untuk user yang belum login, akan
   muncul login box ... kalau tidak [berbayar], maka dia akan diarahkan ke paywall."

   A page the shell opens with ?example=1 (static/edge-app.js ExampleTabPage) reads its example's files
   (/api/v1/examples/<tab>, app/examples.py) and is kept still by this layer:
   - a click, a double or middle click, a context menu, a press of a pointer, a drag, a drop, a form's input or change and
     a key that acts on a control (Enter or Space on it, or any key in a field) are stopped on the window before the
     page's own handlers run; a click or such a key asks the shell for its box ({source, type: 'locked', kind:
     'example', id, name}: sign in for a visitor, the paywall for an account), at most once every LOCK_MS;
   - hover is stopped the same way (no tooltip of the page's own opens), an SVG takes no pointer (its <title> never
     shows), and every title attribute (and SVG <title>) is removed whenever the pointer enters an element: a native
     tooltip needs the pointer on its element and shows only after a delay, so none ever opens. No observer and no
     timer watch the page (the pages' bundle rules: the Screener's forbids both, EXEC-SCREENER-V21);
   - the page's own styles of a pointer over, a focus or a press (:hover, :focus, :focus-visible, :focus-within,
     :active) are taken out of its style sheets (the example-mode checker, ERRORS M527: a tooltip drawn by CSS alone,
     the Backtest's "Within N bars" or the Radar's rail hints, opens without any script): hover and focus change nothing
     on the page, which stays as it was drawn. A sheet that comes later is read on the next pointer entry or focus.
     Tab still moves between controls, shown by one plain focus ring of the example's own;
   - scrolling keeps working: the wheel and touch are stopped only for the page's handlers (a chart's zoom), never for
     the browser, and the keys that scroll are left alone outside a control.
   The Market Overview is the exception the user set (lockOnly below): it stays clickable, and only its time controls ask
   for the box. The server is the guarantee (the example routes serve only the example's files to <tab>.example); this
   layer only keeps the page a view of one day. */

export const EXAMPLE_PARAM = 'example';
const LOCK_MS = 400;
const STOPPED = ['click', 'dblclick', 'auxclick', 'contextmenu', 'mousedown', 'mouseup', 'pointerdown', 'pointerup',
  'dragstart', 'drop', 'input', 'change', 'submit', 'beforeinput', 'paste', 'cut'];
const HOVER = ['mouseover', 'mouseout', 'mouseenter', 'mouseleave', 'mousemove', 'pointerover', 'pointerout',
  'pointerenter', 'pointerleave', 'pointermove', 'focusin', 'focusout'];
const SCROLLING = ['wheel', 'touchstart', 'touchmove', 'touchend'];
const ASKS = new Set(['click', 'auxclick', 'contextmenu']);
const CONTROL = 'a[href], button, input, select, textarea, summary, [role=button], [role=radio], [role=tab], '
  + '[role=checkbox], [role=switch], [role=menuitem], [role=option], [role=slider], [tabindex], [contenteditable]';
const FIELD = 'input, select, textarea, [contenteditable]';

/** Whether the shell opened this page as its example (?example=1). */
export function exampleMode(search = typeof location === 'undefined' ? '' : location.search): boolean {
  return new URLSearchParams(search).get(EXAMPLE_PARAM) === '1';
}

export interface ViewOnly { stop(): void }

// a selector that applies only while the pointer is over, a focus is on or a press is held on something (an interaction
// pseudo-class outside :not(), which keeps the rest state)
const INTERACTION = /:(?:hover|focus|focus-visible|focus-within|active)(?![\w-])/;
const FOCUS_RING = 'html.edge-example :focus-visible { outline: 2px solid var(--text-3, #8a8f98) !important; outline-offset: 2px !important; }';

/** The selectors of a list, split at the commas outside parentheses. */
function selectors(text: string): string[] {
  const out: string[] = [];
  let depth = 0, from = 0;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (c === '(') depth++;
    else if (c === ')') depth--;
    else if (c === ',' && depth === 0) { out.push(text.slice(from, i)); from = i + 1 }
  }
  out.push(text.slice(from));
  return out.map(x => x.trim()).filter(Boolean);
}
/** Whether a selector applies only in an interaction state: its pseudo-class outside every :not(...). */
export function interactive(selector: string): boolean {
  let rest = '', i = 0;
  while (i < selector.length) {
    if (selector.startsWith(':not(', i)) {
      let depth = 0, j = i + 4;
      for (; j < selector.length; j++) { if (selector[j] === '(') depth++; else if (selector[j] === ')' && --depth === 0) break }
      i = j + 1;
      continue;
    }
    rest += selector[i++];
  }
  return INTERACTION.test(rest);
}
/** Takes the interaction selectors out of a list of rules (and the rules nested in them): a rule left with none goes. */
function stillRules(list: CSSRuleList, owner: { deleteRule(i: number): void }) {
  for (let i = list.length - 1; i >= 0; i--) {
    const r = list[i] as CSSRule & { selectorText?: string; cssRules?: CSSRuleList; deleteRule?(i: number): void; styleSheet?: CSSStyleSheet };
    if (typeof r.selectorText === 'string') {
      const all = selectors(r.selectorText), kept = all.filter(x => !interactive(x));
      if (!kept.length) { owner.deleteRule(i); continue }
      if (kept.length < all.length) r.selectorText = kept.join(', ');
    }
    if (r.cssRules && r.deleteRule) stillRules(r.cssRules, r as unknown as { deleteRule(i: number): void });
    else if (r.styleSheet) still(r.styleSheet);
  }
}
const stilled = new WeakSet<CSSStyleSheet>();
/** A style sheet without its interaction styles (module comment); a sheet of another origin cannot be read and is left. */
function still(sheet: CSSStyleSheet) {
  if (stilled.has(sheet)) return;
  let rules: CSSRuleList;
  try { rules = sheet.cssRules } catch { return }
  stilled.add(sheet);
  stillRules(rules, sheet);
}

/** The shell's box, asked for at most once every LOCK_MS: {source, type: 'locked', kind: 'example', id, name}. */
function asker(win: Window, source: string, name: string): () => void {
  let last = -Infinity;
  return () => {
    const now = Date.now();
    if (now - last < LOCK_MS) return;
    last = now;
    const box = { source, type: 'locked', kind: 'example', id: source, name };
    try { if (win.parent !== win) win.parent.postMessage(box, win.location.origin) } catch { /* not framed */ }
  };
}

/** The Market Overview's example (the user, 2026-11-21: "semuanya clickable ... Tapi kalau seandainya user klik 5D, 1M,
 *  atau custom, ataupun filter yang sifatnya adalah time frame, baru diarahkan ke paywall. atau diarahkan ke login kalau
 *  user belum login"): only a control `locked` names is stopped before the page's handlers and asks for the box (a click,
 *  or Enter or Space on it); everything else, hover and scrolling included, stays the page's own. */
export function lockOnly(opts: { source: string; name: string; locked: (el: Element) => boolean; root?: Document }): ViewOnly {
  const doc = opts.root ?? document, win = doc.defaultView as Window;
  const ask = asker(win, opts.source, opts.name);
  const target = (e: Event) => (e.target instanceof Element ? e.target : null);
  const press = (e: Event) => {
    const el = target(e);
    if (!el || !opts.locked(el)) return;
    e.stopImmediatePropagation();
    e.preventDefault();
    if (e.type === 'click') ask();
  };
  const key = (e: KeyboardEvent) => {
    const el = target(e);
    if (!el || !opts.locked(el) || (e.key !== 'Enter' && e.key !== ' ')) return;
    e.stopImmediatePropagation();
    e.preventDefault();
    ask();
  };
  const PRESSES = ['click', 'dblclick', 'auxclick', 'pointerdown', 'mousedown', 'pointerup', 'mouseup'];
  const opt = { capture: true, passive: false } as AddEventListenerOptions;
  PRESSES.forEach(t => win.addEventListener(t, press, opt));
  win.addEventListener('keydown', key as EventListener, opt);
  return {
    stop() {
      PRESSES.forEach(t => win.removeEventListener(t, press, opt));
      win.removeEventListener('keydown', key as EventListener, opt);
    },
  };
}

/** Keeps the page still (module comment); `source` is the page's tab (the shell accepts a box only from the frame of
 *  its current tab), `name` its name in the box. */
export function viewOnly(opts: { source: string; name: string; root?: Document }): ViewOnly {
  const doc = opts.root ?? document, win = doc.defaultView as Window;
  const ask = asker(win, opts.source, opts.name);
  const stop = (e: Event) => {
    e.stopImmediatePropagation();
    e.preventDefault();
    if (ASKS.has(e.type)) ask();
  };
  const quiet = (e: Event) => e.stopImmediatePropagation();          // the page's handlers only; the browser goes on
  const key = (e: KeyboardEvent) => {
    const at = e.target instanceof Element ? e.target : null;
    const onControl = !!at?.closest(CONTROL), inField = !!at?.closest(FIELD);
    if (!onControl && !inField) { e.stopImmediatePropagation(); return }   // scrolling keys stay the browser's
    if (e.key === 'Tab') return;                                         // moving between controls stays possible
    e.stopImmediatePropagation();
    e.preventDefault();
    if (e.key === 'Enter' || e.key === ' ' || inField) ask();
  };
  const opt = { capture: true, passive: false } as AddEventListenerOptions;
  const style = doc.createElement('style');
  // before the hover listeners below: they stop the event for every later listener of the window (module comment)
  const sheets = () => { for (const sh of Array.from(doc.styleSheets)) if (sh.ownerNode !== style) still(sh) };
  const untitle = () => {
    sheets();
    doc.querySelectorAll('[title], svg title').forEach(n => {
      if (n.tagName.toLowerCase() === 'title') n.remove(); else n.removeAttribute('title');
    });
  };
  const SWEEPS = ['pointerover', 'mouseover', 'focusin'];
  SWEEPS.forEach(t => win.addEventListener(t, untitle, true));
  STOPPED.forEach(t => win.addEventListener(t, stop, opt));
  HOVER.forEach(t => win.addEventListener(t, quiet, true));
  SCROLLING.forEach(t => win.addEventListener(t, quiet, { capture: true, passive: true }));
  win.addEventListener('keydown', key as EventListener, opt);
  win.addEventListener('keyup', quiet, true);
  win.addEventListener('keypress', quiet, true);

  doc.documentElement.classList.add('edge-example');
  style.dataset.edgeExample = '';
  style.textContent = `html.edge-example svg, html.edge-example svg * { pointer-events: none !important; }\n${FOCUS_RING}`;
  doc.head.appendChild(style);
  untitle();

  return {
    stop() {
      STOPPED.forEach(t => win.removeEventListener(t, stop, opt));
      HOVER.forEach(t => win.removeEventListener(t, quiet, true));
      SCROLLING.forEach(t => win.removeEventListener(t, quiet, { capture: true } as EventListenerOptions));
      win.removeEventListener('keydown', key as EventListener, opt);
      win.removeEventListener('keyup', quiet, true);
      win.removeEventListener('keypress', quiet, true);
      SWEEPS.forEach(t => win.removeEventListener(t, untitle, true));
      style.remove();                         // the interaction styles taken out stay out until the page loads again
      doc.documentElement.classList.remove('edge-example');
    },
  };
}
