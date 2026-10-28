/* Smoke build entry (vite build --mode smoke): the production page modules on the fixture ScreenerApi with answers
   that arrive late or fail first, chosen by the query string, for the Chromium smoke run (tests/smoke/smoke.mjs; the
   late-data lesson of ERRORS M253, report 6c.9 item 2). Never part of the production bundle (vite.config.ts).
     ?slow=session:800,catalog:1500,run:3000   extra milliseconds per call
     ?fail=catalog:SCREENER_NOT_READY:503:1:2   code:status:times[:retry-after[:field]]; run:BUSY:409:1
     ?newpub=1                                  a new publication after the first run
     ?pub=2                                     the page load starts at the second publication
     ?noidb=1                                   IndexedDB refuses to open (the page works without its cache)
     ?hostile=1                                 markup in a company name and a sector (rendered as text only) */
import '../../src/styles/screener.css';
import '../../../terminal/src/styles/spin.css';
import { bootPage } from '../../src/app.ts';
import { fileCache } from '../../../terminal/src/data/rack.ts';
import { fixtureApi, type FixtureOpts } from '../fixture/api.ts';

const q = new URLSearchParams(location.search);
const opts: FixtureOpts = { delay:{}, fail:{} };
for (const part of (q.get('slow') || '').split(',').filter(Boolean)) { const [k, ms] = part.split(':'); (opts.delay as any)[k] = Number(ms) }
for (const part of (q.get('fail') || '').split(',').filter(Boolean)) { const [k, code, status, times, ra, field] = part.split(':'); (opts.fail as any)[k] = { code, status:Number(status), times:Number(times), retryAfter:ra ? Number(ra) : undefined, field:field || undefined } }
if (q.get('newpub')) opts.newPublicationAfterRuns = Number(q.get('newpub'));
if (q.get('pub')) opts.publication = Number(q.get('pub'));
if (q.get('hostile')) opts.hostile = true;
const api = fixtureApi(opts);
(window as any).__fixture = api;
const refusing = { open:() => { const r: any = {}; setTimeout(() => { r.error = new DOMException('blocked', 'UnknownError'); r.onerror?.({ preventDefault() {} }) }, 0); return r } } as unknown as IDBFactory;
/* The synthetic market is generated while this script is evaluated (tests/fixture/data.ts), work the production page
   never does: it is counted as the fixture's (api.busy), and the page boots in the next task, so the smoke run's
   long-task check sees the page's own boot apart from it (report 6c.9 item 2). */
api.busy.push([0, performance.now()]);
setTimeout(() => bootPage(api, q.get('noidb') ? { cache:fileCache(refusing) } : {}), 0);
