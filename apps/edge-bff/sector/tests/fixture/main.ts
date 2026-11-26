/* EXEC-SECTOR-ANALYSIS S4, fixture build only (vite --mode fixture): the page on the local prototype's files
   (tests/fixture/data, from_prototype.mjs; never committed) when they exist, else on made-up files (make.mjs), for the look
   check. Never part of the production bundle (tests/bundle.test.mjs). ?example=1 opens the example's view. */
import '../../src/styles/sector.css';
import { start } from '../../src/app.ts';
import type { SectorApi } from '../../src/types.ts';
// @ts-ignore: a plain module of the tests
import { makeFiles } from './make.mjs';

const saved = import.meta.glob('./data/*.json', { eager: true, import: 'default' }) as Record<string, any>;
const made = saved['./data/index.json'] ? null : makeFiles();
const doc = (name: string) => (made ? made.files[name] : saved[`./data/${name}.json`]);
const api: SectorApi = {
  index: async () => (made ? made.index : saved['./data/index.json']),
  file: async <T>(name: string) => { const d = doc(name); if (!d) throw new Error(`no fixture ${name}`); return d as T },
};
const p = new URLSearchParams(location.search);
if (p.get('theme') === 'dark') { document.documentElement.dataset.theme = 'dark'; document.documentElement.classList.add('dark') }
void start(api, document.getElementById('view') as HTMLElement, { example: p.get('example') === '1' }).boot();
