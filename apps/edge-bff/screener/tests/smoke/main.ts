/* Smoke build entry (vite build --mode smoke): the production page modules on the fixture ScreenerApi with answers
   that arrive late or fail first, chosen by the query string, for the Chromium smoke run (tests/smoke/smoke.mjs; the
   late-data lesson of ERRORS M253, report 6c.9 item 2). Never part of the production bundle (vite.config.ts).
     ?slow=session:800,catalog:1500,run:3000   extra milliseconds per call
     ?fail=catalog:SCREENER_NOT_READY:503:1:2   code:status:times[:retry-after]; run:BUSY:409:1
     ?newpub=1                                  a new publication after the first run
     ?noidb=1                                   IndexedDB refuses to open (the page works without its cache) */
import '../../src/styles/screener.css';
import '../../../terminal/src/styles/spin.css';
import { bootPage } from '../../src/app.ts';
import { fileCache } from '../../../terminal/src/data/rack.ts';
import { fixtureApi, type FixtureOpts } from '../fixture/api.ts';

const q = new URLSearchParams(location.search);
const opts: FixtureOpts = { delay:{}, fail:{} };
for (const part of (q.get('slow') || '').split(',').filter(Boolean)) { const [k, ms] = part.split(':'); (opts.delay as any)[k] = Number(ms) }
for (const part of (q.get('fail') || '').split(',').filter(Boolean)) { const [k, code, status, times, ra] = part.split(':'); (opts.fail as any)[k] = { code, status:Number(status), times:Number(times), retryAfter:ra ? Number(ra) : undefined } }
if (q.get('newpub')) opts.newPublicationAfterRuns = Number(q.get('newpub'));
const api = fixtureApi(opts);
(window as any).__fixture = api;
const refusing = { open:() => { const r: any = {}; setTimeout(() => { r.error = new DOMException('blocked', 'UnknownError'); r.onerror?.({ preventDefault() {} }) }, 0); return r } } as unknown as IDBFactory;
bootPage(api, q.get('noidb') ? { cache:fileCache(refusing) } : {});
