/* Phase 4, the admin page (CONTRACT.md 10; the user, 2026-11-22: "1A, 2B, 3A"): the production entry. The page follows
   EDGE's one theme (the shell's key, as the other pages) and reads its data from edge-bff only (src/api.ts). The ticket of
   its own address (?ticket=<id>, which the shell passes from /admin?ticket=<id>) opens first. */
import './styles/admin.css';
import { live } from './api.ts';
import { start } from './app.ts';
import { ticketOf } from './model.ts';

const THEME_KEY = 'edge-auth-monitor-theme';
function applyTheme() {
  let dark = false;
  try { dark = localStorage.getItem(THEME_KEY) === 'dark' } catch { /* storage off: light */ }
  document.documentElement.dataset.theme = dark ? 'dark' : 'light';
  document.documentElement.classList.toggle('dark', dark);
}
applyTheme();
const page = start(live, document.getElementById('page') as HTMLElement, { ticket: ticketOf(location.search) });
addEventListener('storage', e => { if (e.key === THEME_KEY || e.key === null) { applyTheme(); page.rerender() } });
void page.boot();
