/* EXEC-TERMINAL-SESSION-TOGGLE item 2 (user 2026-11-24: "toggle between timeline masih laggy"; UD50 "untuk ganti
   timeframe dl saja"): one build of the page (main.ts start) is a "life". Every section takes the candles once when it
   starts, so a timeframe switch used to reload the whole page (session, ticker list, bundle, script, every section).
   Now the page keeps its script and its data worker and builds again in place: what the life registered on window,
   document, <body> and <html> (listeners), the observers and intervals it started and the charts it made are taken down
   first (dispose), then <body> is put back as the page shipped it and the sections start on the new candles. A timeout
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
