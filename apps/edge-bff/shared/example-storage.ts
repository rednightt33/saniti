/* EXEC-MU-ACCOUNTS 3e, the example mode (ERRORS M527, the example-mode checker): a page the shell opens with ?example=1
   keeps nothing of the visitor's browser and leaves nothing in it. The entry of every page that calls viewOnly imports
   this module first (tests/test_example_storage.py derives those entries and checks the order), so it runs before any
   other module of the page: in example mode the frame's localStorage and sessionStorage are replaced, for this load, by
   storages held in memory. A layout, a column order, a pane collapsed or a draft another session kept on this browser
   does not show in the example (the Screener's and the Backtest's modules read theirs when they load), and nothing the
   example's page writes stays.
   - The one key read through to the browser's storage is the shell's theme (THEME_KEY): the page follows the shell's
     light or dark mode, and re-reads the key on the storage event the shell's change sends. The page never writes it;
     a write of it, as every write, stays in memory.
   - The Market Overview is not a view-only page (lockOnly, the user's "semuanya clickable"): it keeps the browser's
     storage (a click on a stock writes the Terminal's symbol, ml.symbol).
   No key is listed here but the theme's: every other key, of today's pages or a later one, is held in memory. */
import { exampleMode } from './example-view.ts';

export const THEME_KEY = 'edge-auth-monitor-theme';
export const ISOLATED = ['localStorage', 'sessionStorage'] as const;

/** A Storage held in memory; the keys of `through` are read from `real` until this storage writes them. */
export function memoryStorage(real: Storage | null, through: readonly string[] = []): Storage {
  const held = new Map<string, string>(), passing = new Set(through);
  const readReal = (k: string): string | null => {
    if (!real || !passing.has(k)) return null;
    try { return real.getItem(k) } catch { return null }
  };
  const keys = () => [...held.keys(), ...[...passing].filter(k => !held.has(k) && readReal(k) !== null)];
  return {
    get length() { return keys().length },
    key: (i: number) => keys()[i] ?? null,
    getItem: (k: string) => (held.has(String(k)) ? held.get(String(k))! : readReal(String(k))),
    setItem: (k: string, v: string) => { held.set(String(k), String(v)) },
    removeItem: (k: string) => { held.delete(String(k)) },
    clear: () => { held.clear() },
  } as Storage;
}

/** Replaces the window's localStorage (the theme read through) and sessionStorage by storages in memory; true when
 *  both are replaced (a browser that refuses is reported on the console: the page then keeps the browser's storage). */
export function isolateStorage(win: Window = window): boolean {
  let done = 0;
  for (const name of ISOLATED) {
    let real: Storage | null = null;
    try { real = win[name] } catch { real = null }
    try {
      Object.defineProperty(win, name, { value: memoryStorage(real, name === 'localStorage' ? [THEME_KEY] : []),
        configurable: true, enumerable: true, writable: false });
      done += 1;
    } catch (e) {
      console.warn(`example mode: ${name} could not be held in memory`, e);
    }
  }
  return done === ISOLATED.length;
}

if (exampleMode()) isolateStorage();
