/* EXEC-RADAR R7: the production entry. The page follows EDGE's one theme (the shell's key, as the Screener) and reads
   its data from edge-bff only (src/api.ts). */
import './styles/radar.css';
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
const page = start(live, document.getElementById('view') as HTMLElement);
addEventListener('storage', e => { if (e.key === THEME_KEY || e.key === null) { applyTheme(); page.rerender() } });
void page.boot();
