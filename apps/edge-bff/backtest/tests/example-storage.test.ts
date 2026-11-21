/* 3e, the example mode (ERRORS M527, the example-mode checker): shared/example-storage.ts, the storage an example page
   holds in memory. Every key is held in memory for the load (a key another session kept on the browser reads as
   absent, a write stays in memory), the shell's theme is read through to the browser's storage while the page has not
   written it (the page follows a change of the shell's theme), and the browser's storage is never written. Red when a
   key reads or writes through, or when the window keeps its own storages. tests/test_3e_example_browser.py checks it
   on the built pages; tests/test_example_storage.py that every view-only entry imports it first. */
import { describe, expect, it } from 'vitest';
import { ISOLATED, THEME_KEY, isolateStorage, memoryStorage } from '../../shared/example-storage.ts';

/** a browser storage of the test: its items in a Map the test reads */
function real(seed: Record<string, string>) {
  const m = new Map(Object.entries(seed));
  const s = {
    get length() { return m.size },
    key: (i: number) => [...m.keys()][i] ?? null,
    getItem: (k: string) => (m.has(k) ? m.get(k)! : null),
    setItem: (k: string, v: string) => { m.set(k, String(v)) },
    removeItem: (k: string) => { m.delete(k) },
    clear: () => { m.clear() },
  };
  return { s: s as unknown as Storage, m };
}
const KEPT = { [THEME_KEY]: 'dark', 'scr.panes': '{"lcol":true,"ucol":true}', 'scr.extraCols': '["rvol"]', 'ml.panel': '0' };

describe('the storage an example page holds in memory', () => {
  it('holds every key in memory and reads only the shell\'s theme through, never writing the browser\'s', () => {
    const r = real(KEPT), s = memoryStorage(r.s, [THEME_KEY]);
    expect([s.getItem('scr.panes'), s.getItem('scr.extraCols'), s.getItem('ml.panel')]).toEqual([null, null, null]);
    expect(s.getItem(THEME_KEY)).toBe('dark');
    r.m.set(THEME_KEY, 'light');                                  // the shell switches the theme
    expect(s.getItem(THEME_KEY)).toBe('light');
    expect([s.length, s.key(0), s.key(1)]).toEqual([1, THEME_KEY, null]);
    s.setItem('scr.panes', '{"lcol":false}');
    s.setItem('scr.last', '{"name":"x"}');
    s.removeItem('ml.panel');
    expect(s.getItem('scr.panes')).toBe('{"lcol":false}');
    expect(s.length).toBe(3);
    s.setItem(THEME_KEY, 'written by the page');                   // a write of the theme stays in memory too
    expect(s.getItem(THEME_KEY)).toBe('written by the page');
    s.clear();
    expect(s.getItem('scr.last')).toBeNull();
    expect(Object.fromEntries(r.m)).toEqual({ ...KEPT, [THEME_KEY]: 'light' });   // the browser's: as the shell left it
  });

  it('replaces the window\'s localStorage and sessionStorage, the browser\'s untouched', () => {
    const local = real(KEPT), session = real({ 'scr.boot': 'x' });
    const win = { localStorage: local.s, sessionStorage: session.s } as unknown as Window;
    expect(isolateStorage(win)).toBe(true);
    expect([...ISOLATED]).toEqual(['localStorage', 'sessionStorage']);
    expect(win.localStorage).not.toBe(local.s);
    expect(win.sessionStorage).not.toBe(session.s);
    expect([win.localStorage.getItem('scr.panes'), win.localStorage.getItem(THEME_KEY), win.sessionStorage.getItem('scr.boot')])
      .toEqual([null, 'dark', null]);
    win.localStorage.setItem('ml.bw', '500');
    win.sessionStorage.setItem('scr.boot', 'y');
    expect(Object.fromEntries(local.m)).toEqual(KEPT);
    expect(Object.fromEntries(session.m)).toEqual({ 'scr.boot': 'x' });
  });
});
