/* EXEC-SECTOR-ANALYSIS S4, fixture build only (vite --mode fixture): the page on the local prototype's files
   (tests/fixture/data, from_prototype.mjs; never committed) when they exist, else on made-up files (make.mjs), for the look
   check. Never part of the production bundle (tests/bundle.test.mjs). ?example=1 opens the example's view.
   Test hooks of the look check (tests/look/check1.mjs, check 1 of 2026-11-27): ?slow=<date>:<ms> answers that date's day
   file late (BD-5, two quick picks), ?fail=1 refuses every read (MX-7, the header while only an error shows). */
import '../../src/styles/sector.css';
import { start } from '../../src/app.ts';
import { SectorError } from '../../src/api.ts';
import type { SectorApi } from '../../src/types.ts';
// @ts-ignore: a plain module of the tests
import { makeFiles } from './make.mjs';

const saved = import.meta.glob('./data/*.json', { eager: true, import: 'default' }) as Record<string, any>;
const made = saved['./data/index.json'] ? null : makeFiles();
const doc = (name: string) => (made ? made.files[name] : saved[`./data/${name}.json`]);
const p = new URLSearchParams(location.search);
const [slowDate, slowMs] = (p.get('slow') || '').split(':'), fail = p.get('fail') === '1';
const refuse = () => Promise.reject(new SectorError('SECTOR_UNAVAILABLE', 'The sector analysis could not be read. Try again in a minute.', 503));
const api: SectorApi = {
  index: async () => (fail ? refuse() : made ? made.index : saved['./data/index.json']),
  file: async <T>(name: string) => {
    if (fail) return refuse();
    const d = doc(name); if (!d) throw new Error(`no fixture ${name}`);
    if (slowDate && name === `sector-day-${slowDate}`) await new Promise(r => setTimeout(r, +slowMs || 1500));
    return d as T;
  },
};
if (p.get('theme') === 'dark') { document.documentElement.dataset.theme = 'dark'; document.documentElement.classList.add('dark') }
void start(api, document.getElementById('view') as HTMLElement, { example: p.get('example') === '1' }).boot();
