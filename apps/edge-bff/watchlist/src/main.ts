/* EXEC-WATCHLIST L5: the production entry. The page follows EDGE's one theme (the shell's key, as the Overview and the
   Radar) and reads its data from edge-bff only (src/api.ts). */
import './styles/watchlist.css';
import { example, live } from './api.ts';
import { start } from './app.ts';
import { exampleMode, viewOnly } from '../../shared/example-view.ts';

const THEME_KEY = 'edge-auth-monitor-theme';
function applyTheme() {
  let dark = false;
  try { dark = localStorage.getItem(THEME_KEY) === 'dark' } catch { /* storage off: light */ }
  document.documentElement.dataset.theme = dark ? 'dark' : 'light';
  document.documentElement.classList.toggle('dark', dark);
}
applyTheme();
// 3e, the example mode (user 2026-11-21; ERRORS M527): the shell opens the page with ?example=1 for a principal holding
// watchlist.example; the page then reads the example's files and stays a view of that day (shared/example-view.ts)
const asExample = exampleMode();
if (asExample) viewOnly({ source: 'watchlist', name: 'Watchlist' });
const page = start(asExample ? example : live, document.getElementById('page') as HTMLElement, { example: asExample });
addEventListener('storage', e => { if (e.key === THEME_KEY || e.key === null) { applyTheme(); page.rerender() } });
void page.boot();
