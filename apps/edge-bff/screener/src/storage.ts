/* Browser storage of the page (report 9.5, 6c.3): only conveniences live here, under scr.* (panel state, preview open,
   the last open screen's draft) plus the EDGE theme the shell writes. Saved screens, My metrics and the watchlist are
   per user and come from the server on every load (P12 a); nothing of them is kept here. Every access is wrapped:
   a blocked or full storage only loses the convenience (the prototype's store). */
import type { Definition } from './core/contract.ts';

export const store = {
  get<T>(k: string, d: T): T { try { const v = localStorage.getItem(k); return v == null ? d : (JSON.parse(v) ?? d) } catch { return d } },
  set(k: string, v: unknown) { try { localStorage.setItem(k, JSON.stringify(v)) } catch { /* storage off or full */ } },
  del(k: string) { try { localStorage.removeItem(k) } catch { /* storage off */ } },
};

/** EDGE's one theme (report 9.2 Theme): the shell's key, default light (MONITOR-REVAMP, user 2026-10-29), as the shell;
 * the prototype's own key is dropped. */
export const THEME_KEY = 'edge-auth-monitor-theme';
export function readTheme(): 'light' | 'dark' {
  try { return localStorage.getItem(THEME_KEY) === 'dark' ? 'dark' : 'light' } catch { return 'light' }
}
export function applyTheme(t = readTheme()) {
  const root = document.documentElement;
  root.dataset.theme = t;
  root.classList.toggle('dark', t === 'dark');
}
/** follow the shell's theme changes: the storage event fires in a same-origin frame when the shell writes the key */
export function followTheme(onChange: () => void) {
  addEventListener('storage', e => { if (e.key === THEME_KEY || e.key === null) { applyTheme(); onChange() } });
}

/** The page's conveniences (scr.*). */
export const KEYS = { panel:'scr.panel', last:'scr.last', boot:'scr.boot' } as const;
export interface PanelPrefs { preview?: boolean; bOpen?: boolean; perPage?: number; pvView?: 'chart' | 'perf'; perf?: '1M' | '3M' | '6M' | '1Y' }
export interface LastScreen { name: string; definition: Definition; item_id?: string; preset?: string; sort?: { key: string; dir: 'asc' | 'desc' }; near?: boolean }
export const panelPrefs = (): PanelPrefs => store.get<PanelPrefs>(KEYS.panel, {});
export const savePanel = (p: PanelPrefs) => store.set(KEYS.panel, { ...panelPrefs(), ...p });
export const lastScreen = (): LastScreen | null => {
  const l = store.get<LastScreen | null>(KEYS.last, null);
  return l && typeof l === 'object' && l.definition && typeof l.definition === 'object' ? l : null;
};
export const saveLast = (l: LastScreen) => store.set(KEYS.last, l);

/** The key the Terminal reads at boot for its symbol (report 9.3 item 6: "Open in Terminal"). */
export const TERMINAL_SYMBOL = 'ml.symbol';
