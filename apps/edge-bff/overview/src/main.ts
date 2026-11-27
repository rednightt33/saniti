/* EXEC-OVERVIEW O5: the production entry. The page follows EDGE's one theme (the shell's key, as the Radar and the
   Screener) and reads its data from edge-bff only (src/api.ts). */
import '../../shared/focus-modality.ts';   // UD75: the focus ring follows the last input (no ring after a mouse or a touch)
import './styles/overview.css';
import { example, live } from './api.ts';
import { exampleMode } from '../../shared/example-view.ts';
import { start } from './app.ts';

const THEME_KEY = 'edge-auth-monitor-theme';
function applyTheme() {
  let dark = false;
  try { dark = localStorage.getItem(THEME_KEY) === 'dark' } catch { /* storage off: light */ }
  document.documentElement.dataset.theme = dark ? 'dark' : 'light';
  document.documentElement.classList.toggle('dark', dark);
}
applyTheme();
// 3e, the example mode (user 2026-11-21; ERRORS M527): the shell opens the page with ?example=1 for a principal holding
// overview.example; the page then reads the example's files and locks its time controls (src/app.ts)
const asExample = exampleMode();
const page = start(asExample ? example : live, document.getElementById('view') as HTMLElement, { example: asExample });
addEventListener('storage', e => { if (e.key === THEME_KEY || e.key === null) { applyTheme(); page.rerender() } });
void page.boot();
