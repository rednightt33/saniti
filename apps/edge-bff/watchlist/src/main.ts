/* EXEC-WATCHLIST L5: the production entry. The page follows EDGE's one theme (the shell's key, as the Overview and the
   Radar) and reads its data from edge-bff only (src/api.ts). */
import './styles/watchlist.css';
import { live } from './api.ts';
import { start } from './app.ts';

const THEME_KEY = 'edge-auth-monitor-theme';
function applyTheme() {
  let dark = false;
  try { dark = localStorage.getItem(THEME_KEY) === 'dark' } catch { /* storage off: light */ }
  document.documentElement.dataset.theme = dark ? 'dark' : 'light';
  document.documentElement.classList.toggle('dark', dark);
}
applyTheme();
const page = start(live, document.getElementById('page') as HTMLElement);
addEventListener('storage', e => { if (e.key === THEME_KEY || e.key === null) { applyTheme(); page.rerender() } });
void page.boot();
