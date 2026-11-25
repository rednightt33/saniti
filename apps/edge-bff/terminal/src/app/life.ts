/* EXEC-TERMINAL-SESSION-TOGGLE item 2 (user 2026-11-24: "toggle between timeline masih laggy"; UD50 "untuk ganti
   timeframe dl saja"): one build of the page (main.ts start) is a "life". Every section takes the candles once when it
   starts, so a timeframe switch used to reload the whole page (session, ticker list, bundle, script, every section).
   Now the page keeps its script and its data worker and builds again in place: what the life registered on window,
   document, <body> and <html> (listeners), the observers and intervals it started and the charts it made are taken down
   first (dispose), then <body> and <html> are put back as the page shipped them (restorePage: <body>'s markup and the
   attributes of both) and the sections start on the new candles. A timeout
   is left to run (a pending save, as the drawings' and the preferences' debounced writes, must still be sent); an
   animation frame of an ended life runs with its error kept quiet (its chart is gone), so a loop that is not the
   page's (a test's polling) goes on.

   The listeners need no change in the sections: while a life runs, a listener added to window, document, <body> or
   <html> without a signal of its own gets the life's signal, so dispose (abort) removes it. A listener meant for the
   whole page (one registered once behind a module flag, as shared/edge-session.ts's) passes a signal of its own (one
   that never aborts, `forPage`). Module state that holds page elements registers a reset with onEveryDispose. */

let ctrl = new AbortController();
let gen = 0;
const disposers: (() => void)[] = [], resets: (() => void)[] = [];
const observers = new Set<{ disconnect(): void }>();
const intervals = new Set<number>();
const charts = new Set<{ remove(): void }>();
let installed = false;

/** a signal that never aborts: for a listener meant for the page's whole life (a module-level once flag) */
export const forPage = new AbortController().signal;
/** the life's number: an answer that arrives after the page was built again checks it and drops itself */
export const lifeId = () => gen;
/** run `fn` when this life ends (once) */
export const onDispose = (fn: () => void) => { disposers.push(fn) };
/** run `fn` whenever a life ends: module state that holds page elements (registered once, at the module's load) */
export const onEveryDispose = (fn: () => void) => { resets.push(fn) };
/** a chart the life made (removed when it ends) */
export function ownChart<T extends { remove(): void }>(chart: T): T { charts.add(chart); return chart }

const pageTarget = (t: unknown) => t === window || t === document || t === document.body || t === document.documentElement;

/** install the bookkeeping once, before the first life starts (main.ts boot) */
export function trackLives() {
  if (installed || typeof window === 'undefined') return;
  installed = true;
  const add = EventTarget.prototype.addEventListener;
  EventTarget.prototype.addEventListener = function (this: EventTarget, type: string, fn: any, opts?: boolean | AddEventListenerOptions) {
    const self = this ?? window;                            // a bare addEventListener(...) in a module runs with no `this`
    if (fn && pageTarget(self) && !(opts && typeof opts === 'object' && opts.signal)) {
      opts = typeof opts === 'object' ? { ...opts, signal:ctrl.signal } : { capture:!!opts, signal:ctrl.signal };
    }
    return add.call(self, type, fn, opts);
  };
  const wrapObserver = <C extends new (...a: any[]) => { disconnect(): void }>(Base: C): C => class extends Base {
    constructor(...a: any[]) { super(...a); observers.add(this) }
    disconnect() { observers.delete(this); super.disconnect() }
  };
  if (typeof ResizeObserver !== 'undefined') (window as any).ResizeObserver = wrapObserver(ResizeObserver);
  if (typeof MutationObserver !== 'undefined') (window as any).MutationObserver = wrapObserver(MutationObserver);
  const si = window.setInterval.bind(window), ci = window.clearInterval.bind(window);
  (window as any).setInterval = (fn: any, ms?: number, ...a: any[]) => { const id = si(fn, ms, ...a); intervals.add(id); return id };
  (window as any).clearInterval = (id?: number) => { if (id !== undefined) intervals.delete(id); ci(id) };
  const raf = window.requestAnimationFrame.bind(window);
  (window as any).requestAnimationFrame = (fn: FrameRequestCallback) => { const g = gen;
    return raf(t => { if (g === gen) return fn(t); try { fn(t) } catch { /* a frame of an ended life: its chart is gone */ } }) };
}

/* ERRORS M563 re-check (full screen stayed on <html> after a switch): the page as it shipped, taken at boot before the
   first life: <body>'s markup and attributes and <html>'s attributes. A life puts state on both (on <html>: full
   screen's ml-full, the indicator filters' ind-filters-off, ind-narrow, the axis widths as CSS variables; on <body>:
   the bond and lock classes), and a reload starts again from the shipped page, so a build in place does too: every
   attribute added since goes and every changed one takes its shipped value, whatever module wrote it. Only what the page
   learns from where it is opened is carried (`carry`, classes of <html>): a reload learns it again at its load (the
   URL, EDGE's hello at the frame's load event), a switch has no load. */
export type Attrs = [string, string][];
/** an element's attributes (class, style, lang, data-* ...) */
export const attrsOf = (el: Element): Attrs => Array.from(el.attributes, a => [a.name, a.value] as [string, string]);
/** an element's attributes put back exactly as `shipped`: an attribute added since goes, a changed one takes its value */
export function restoreAttrs(el: Element, shipped: Attrs) {
  const was = new Map(shipped);
  for (const name of el.getAttributeNames()) if (!was.has(name)) el.removeAttribute(name);
  for (const [name, value] of was) if (el.getAttribute(name) !== value) el.setAttribute(name, value);
}
let shipped: { body: string; bodyAttrs: Attrs; root: Attrs } | null = null;
/** keep the page as it shipped (boot, before the page itself changes <body> or <html>) */
export function shipPage() {
  shipped = { body:document.body.innerHTML, bodyAttrs:attrsOf(document.body), root:attrsOf(document.documentElement) };
}
export const pageShipped = () => shipped !== null;
/** <body> and <html> as a reload leaves them before the sections start; `carry`: <html> classes kept if present */
export function restorePage(carry: readonly string[] = []) {
  if (!shipped) throw new Error('Terminal: the page was not kept at boot');
  const root = document.documentElement, kept = carry.filter(c => root.classList.contains(c));
  document.body.innerHTML = shipped.body;
  restoreAttrs(document.body, shipped.bodyAttrs);
  restoreAttrs(root, shipped.root);
  kept.forEach(c => root.classList.add(c));
}

/** end the life: listeners off, observers disconnected, timers cleared, charts removed, module state reset */
export function disposeLife() {
  gen++;
  ctrl.abort(); ctrl = new AbortController();
  for (const o of [...observers]) { try { o.disconnect() } catch { /* already gone */ } }
  observers.clear();
  for (const id of intervals) window.clearInterval(id);
  intervals.clear();
  for (const c of charts) { try { c.remove() } catch { /* already removed */ } }
  charts.clear();
  while (disposers.length) { try { disposers.pop()!() } catch (e) { console.error('Terminal: a part could not be reset', e) } }
  for (const fn of resets) { try { fn() } catch (e) { console.error('Terminal: a part could not be reset', e) } }
}
