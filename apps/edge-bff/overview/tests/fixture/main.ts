/* EXEC-OVERVIEW O5, fixture build only (vite --mode fixture): the page on saved Overview files of a local rehearsal
   (tests/fixture/save.py), for the look check. Never part of the production bundle (tests/bundle.test.mjs). */
import '../../src/styles/overview.css';
import { start } from '../../src/app.ts';
import type { OverviewApi } from '../../src/types.ts';

const docs = import.meta.glob('./data/*.json', { eager: true, import: 'default' }) as Record<string, any>;
const api: OverviewApi = {
  index: async () => docs['./data/index.json'],
  file: async <T>(name: string) => { const d = docs[`./data/${name}.json`]; if (!d) throw new Error(`no fixture ${name}`); return d as T },
};
const p = new URLSearchParams(location.search);
if (p.get('theme') === 'dark') { document.documentElement.dataset.theme = 'dark'; document.documentElement.classList.add('dark') }
void start(api, document.getElementById('view') as HTMLElement).boot();
