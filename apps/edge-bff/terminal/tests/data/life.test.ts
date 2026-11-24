/* EXEC-TERMINAL-SESSION-TOGGLE item 2 (user 2026-11-24, "toggle between timeline masih laggy"; UD50): a timeframe is built
   in place (main.ts switchTimeframe). One build of the page is a life (src/app/life.ts): what it registered on window,
   document, <body> and <html>, the observers and intervals it started and the charts it made go when it ends; a listener
   with a signal of its own (a page-long one, shared/edge-session.ts) stays; a timeout is left to run (a pending save is
   still sent); an animation frame of an ended life runs with its error kept quiet; module resets run at every end.
   Node has EventTarget and AbortController; the page's globals are stand-ins. */
import { afterAll, beforeAll, describe, expect, it } from 'vitest';

const g = globalThis as any;
const saved: Record<string, any> = {};
const frames: ((t: number) => void)[] = [];
beforeAll(() => {
  for (const k of ['window', 'document', 'ResizeObserver', 'MutationObserver']) saved[k] = g[k];
  const win: any = new EventTarget();
  win.setInterval = (fn: any, ms: number) => setInterval(fn, ms) as any;
  win.clearInterval = (id: any) => clearInterval(id);
  win.requestAnimationFrame = (fn: (t: number) => void) => { frames.push(fn); return frames.length };
  const doc: any = new EventTarget();
  doc.body = new EventTarget(); doc.documentElement = new EventTarget();
  class Obs { on = true; disconnect() { this.on = false } }
  g.window = win; g.document = doc; g.ResizeObserver = Obs; g.MutationObserver = Obs;
  win.ResizeObserver = Obs; win.MutationObserver = Obs;
});
afterAll(() => { for (const [k, v] of Object.entries(saved)) g[k] = v });

describe('a build of the page is a life', () => {
  it('takes down what it registered and keeps the page-long listeners, the timeouts and other targets', async () => {
    const life = await import('../../src/app/life');
    life.trackLives();
    const seen: string[] = [];
    window.addEventListener('resize', () => seen.push('win'));
    document.addEventListener('keydown', () => seen.push('doc'), true);
    document.body.addEventListener('click', () => seen.push('body'));
    window.addEventListener.call(undefined as any, 'message', () => seen.push('bare'));   // a bare call in a module: no `this`
    window.addEventListener('storage', () => seen.push('page-long'), { signal:new AbortController().signal });
    const other = new EventTarget(); other.addEventListener('x', () => seen.push('other'));
    const ro = new (window as any).ResizeObserver(() => {}), mo = new (window as any).MutationObserver(() => {});
    let ticks = 0; const iv = window.setInterval(() => { ticks++ }, 5);
    let removed = 0; life.ownChart({ remove:() => { removed++ } });
    let resets = 0; life.onEveryDispose(() => { resets++ });
    let once = 0; life.onDispose(() => { once++ });
    let timedOut = false; setTimeout(() => { timedOut = true }, 20);
    const fire = () => { for (const [t, e] of [[window, 'resize'], [document, 'keydown'], [document.body, 'click'], [window, 'message'], [window, 'storage'], [other, 'x']] as const) (t as EventTarget).dispatchEvent(new Event(e)) };
    fire();
    expect(seen).toEqual(['win', 'doc', 'body', 'bare', 'page-long', 'other']);
    const id = life.lifeId();
    life.disposeLife();
    expect(life.lifeId()).toBe(id + 1);
    seen.length = 0; fire();
    expect(seen).toEqual(['page-long', 'other']);                   // the life's listeners went; the page-long one and an element's stay
    expect([ro.on, mo.on]).toEqual([false, false]);
    expect(removed).toBe(1);
    expect([resets, once]).toEqual([1, 1]);
    const at = ticks; await new Promise(r => setTimeout(r, 30));
    expect(ticks).toBe(at);                                          // the interval stopped
    expect(timedOut).toBe(true);                                     // a timeout ran (a pending save is still sent)
    window.clearInterval(iv);
    life.disposeLife();
    expect([resets, once]).toEqual([2, 1]);                          // a module reset runs at every end; onDispose once
  });

  it('runs an animation frame of an ended life with its error kept quiet', async () => {
    const life = await import('../../src/app/life');
    let ran = 0;
    window.requestAnimationFrame(() => { ran++; throw new Error('chart is gone') });
    window.requestAnimationFrame(() => { ran++ });
    life.disposeLife();
    expect(() => frames.forEach(f => f(0))).not.toThrow();
    expect(ran).toBe(2);
    frames.length = 0;
    window.requestAnimationFrame(() => { throw new Error('a frame of the live build') });
    expect(() => frames[0](0)).toThrow('a frame of the live build');  // the current life's errors are not hidden
  });
});
