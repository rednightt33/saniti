/* EXEC-RADAR R7, fixture build only (vite --mode fixture): the page on saved Radar files of a local rehearsal
   (tests/fixture/save.py), for the look check. Never part of the production bundle. */
import '../../src/styles/radar.css';
import { start } from '../../src/app.ts';
import type { RadarApi } from '../../src/types.ts';

const docs = import.meta.glob('./data/*.json', { eager: true, import: 'default' }) as Record<string, any>;
const api: RadarApi = {
  index: async () => docs['./data/index.json'],
  file: async <T>(name: string) => { const d = docs[`./data/${name}.json`]; if (!d) throw new Error(`no fixture ${name}`); return d as T },
};
const p = new URLSearchParams(location.search);
if (p.get('theme') === 'dark') { document.documentElement.dataset.theme = 'dark'; document.documentElement.classList.add('dark') }
void start(api, document.getElementById('view') as HTMLElement).boot();
