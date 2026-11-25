/* EXEC-TERMINAL-SESSION-TOGGLE item 2 (user 2026-11-24, "toggle between timeline masih laggy"; UD50): a timeframe is built
   in place (main.ts switchTimeframe). One build of the page is a life (src/app/life.ts): what it registered on window,
   document, <body> and <html>, the observers and intervals it started and the charts it made go when it ends; a listener
   with a signal of its own (a page-long one, shared/edge-session.ts) stays; a timeout is left to run (a pending save is
   still sent); an animation frame of an ended life runs with its error kept quiet; module resets run at every end.
   Node has EventTarget and AbortController; the page's globals are stand-ins. */
import { afterAll, beforeAll, describe, expect, it } from 'vitest';

const g = globalThis as any;
const saved: Record<string, any> = {};
/* <body> and <html>: an event target with attributes and a class list (the parts restorePage reads and writes) */
class FakeEl extends EventTarget {
  innerHTML = '';
  private at = new Map<string, string>();
  get attributes() { return [...this.at].map(([name, value]) => ({ name, value })) }
  getAttributeNames() { return [...this.at.keys()] }
  getAttribute(n: string) { return this.at.has(n) ? this.at.get(n)! : null }
  setAttribute(n: string, v: string) { this.at.set(n, String(v)) }
  removeAttribute(n: string) { this.at.delete(n) }
  get classList() {
    const names = () => (this.getAttribute('class') || '').split(/\s+/).filter(Boolean);
    return { contains:(c: string) => names().includes(c), add:(c: string) => { if (!names().includes(c)) this.setAttribute('class', [...names(), c].join(' ')) },
             remove:(c: string) => this.setAttribute('class', names().filter(x => x !== c).join(' ')) };
  }
}
const frames: ((t: number) => void)[] = [];
beforeAll(() => {
  for (const k of ['window', 'document', 'ResizeObserver', 'MutationObserver']) saved[k] = g[k];
  const win: any = new EventTarget();
  win.setInterval = (fn: any, ms: number) => setInterval(fn, ms) as any;
  win.clearInterval = (id: any) => clearInterval(id);
  win.requestAnimationFrame = (fn: (t: number) => void) => { frames.push(fn); return frames.length };
  const doc: any = new EventTarget();
  doc.body = new FakeEl(); doc.documentElement = new FakeEl();
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

  /* ERRORS M563 re-check: full screen on during a switch left html.ml-full (the Flow Timeline and the footer hidden, the
     button not pressed); every attribute a life put on <html> or <body> goes, as a reload leaves the page, whatever
     module wrote it, and only the embedding (edge-rail) is carried */
  it('puts <body> and <html> back as the page shipped them, carrying only the classes named', async () => {
    const life = await import('../../src/app/life');
    const root = document.documentElement as unknown as FakeEl, body = document.body as unknown as FakeEl;
    root.setAttribute('lang', 'en'); root.setAttribute('class', 'fit'); body.innerHTML = '<main>shipped</main>';
    life.shipPage();
    expect(life.pageShipped()).toBe(true);
    root.classList.add('edge-rail');                                   // boot: ?in=edge, or EDGE's hello (stats.ts)
    root.classList.add('ml-full'); root.classList.add('ind-filters-off'); root.classList.add('ind-narrow');
    root.setAttribute('style', '--ax-l: 120px; --ax-r: 64px;'); root.setAttribute('data-x', '1'); root.setAttribute('lang', 'id');
    root.classList.remove('fit');
    body.setAttribute('class', 'fi-mode locked-broker'); body.setAttribute('style', 'cursor: grab'); body.innerHTML = '<main>built</main>';
    life.restorePage(['edge-rail', 'not-on']);
    expect(Object.fromEntries(root.attributes.map(a => [a.name, a.value]))).toEqual({ lang:'en', class:'fit edge-rail' });
    expect(body.attributes).toEqual([]);
    expect(body.innerHTML).toBe('<main>shipped</main>');
    life.restorePage();                                                // nothing carried: exactly as shipped
    expect(Object.fromEntries(root.attributes.map(a => [a.name, a.value]))).toEqual({ lang:'en', class:'fit' });
  });

  it('is what the timeframe switch builds on: <body> and <html> put back between the old build and the new one', async () => {
    // @ts-expect-error: the Terminal's tsconfig has no Node types; vitest runs in Node
    const { readFileSync } = await import('node:fs');
    const main = readFileSync(new URL('../../src/main.ts', import.meta.url), 'utf8');
    const sw = main.slice(main.indexOf('async function switchTimeframe'));
    expect(main).toMatch(/trackLives\(\);\s*shipPage\(\);/);                    // kept before boot changes <html> (edge-rail)
    expect(sw).toMatch(/disposeLife\(\); liveCtx = null;\s*restorePage\(EMBEDDING\);/);
    expect(sw).not.toMatch(/document\.body\.(innerHTML|className)\s*=/);       // not <body> alone (the defect)
    expect(main).toMatch(/const EMBEDDING = \['edge-rail'\];/);
  });

  /* the class of the defect: a state on <html> a new part adds is decided here, rebuilt by the new life (put back as
     shipped, then set again by the part that owns it, as after a reload) or carried (EMBEDDING: learned at the page's
     load, which a switch does not have) */
  it('decides every state the page puts on <html>: rebuilt by the new life, or carried', async () => {
    // @ts-expect-error: the Terminal's tsconfig has no Node types; vitest runs in Node
    const { readdirSync, readFileSync, statSync } = await import('node:fs');
    // @ts-expect-error: the Terminal's tsconfig has no Node types; vitest runs in Node
    const { join } = await import('node:path');
    const src = new URL('../../src/', import.meta.url).pathname, found = new Set<string>();
    const walk = (d: string) => readdirSync(d).forEach(f => { const p = join(d, f); if (statSync(p).isDirectory()) walk(p);
      else if (/\.ts$/.test(f)) for (const m of readFileSync(p, 'utf8').matchAll(/documentElement\.(?:classList\.(?:add|remove|toggle)|style\.setProperty|setAttribute|dataset\.)\(?'([\w-]+)'/g)) found.add(m[1]) });
    walk(src);
    const REBUILT: Record<string, string> = {
      'ml-full': 'full screen (ui/fullscreen.ts): off after a reload, its panels open as stored',
      'ind-filters-off': 'the indicator filters (drawings.ts): set again from ml.ind.filters at every start',
      'ind-narrow': 'the narrow legend (indicators.ts narrowCheck): measured again at every start',
      '--ax-l': 'the axis widths (flow.ts syncAxisWidths): set again at the first range change', '--ax-r': 'as --ax-l', '--lab-l': 'as --ax-l',
      'fit': 'shipped on <html>; the fixture build alone removes it, and it never switches'
    };
    const CARRIED = ['edge-rail'];
    expect([...found].sort()).toEqual([...Object.keys(REBUILT), ...CARRIED].sort());
    const main = readFileSync(join(src, 'main.ts'), 'utf8');
    expect(main).toContain(`const EMBEDDING = ${JSON.stringify(CARRIED).replace(/"/g, "'")};`);
  });
});
