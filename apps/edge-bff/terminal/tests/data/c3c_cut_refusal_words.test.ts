/* Independent 3c checker, lens "terminal" (EXEC-MU-ACCOUNTS, CONTRACT.md 8b "3c in detail" and section 3): with 3c a
   capped plan (the free plan, every guest) is counted when its cut is downloaded: terminal-api's GET /cut and
   GET /reference/<name>/cut grant the file (apps/terminal-api/app/main.py cut_file, reference_cut: grant(), so the
   files_per_hour and megabytes_per_day quotas refuse there), and edge-bff relays the refusal in the contract's shape
   (main.py relay_cut -> terminal_access.relayed: 429 LIMIT_REACHED with details.limit, retry_after_s and Retry-After;
   401 UNAUTHENTICATED when the session ended; 403 CAPABILITY_REQUIRED after a plan change). The page downloads the cut
   with rack.ts fetchFile, which reads only the status, as it did for the storage host's presigned URLs, so the person
   sees "A data file could not be downloaded (429)." instead of the limit and the wait (section 3: "show the limit
   message and the wait"), and a refused session or plan is not told apart from a broken download. */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { fetchFile } from '../../src/data/rack';

afterEach(() => { vi.unstubAllGlobals() });

const CUT = `/api/terminal/v1/cut/BBCA/price?sha256=${'a'.repeat(64)}`;

function answer(status: number, body: unknown, headers: Record<string, string> = {}) {
  vi.stubGlobal('fetch', async () => new Response(JSON.stringify(body), { status,
    headers:{ 'content-type':'application/json', ...headers } }));
}

describe('a refused cut download reaches the person in the contract words', () => {
  it('the quota of the cut (429 LIMIT_REACHED) names the limit and the wait, not a broken download', async () => {
    answer(429, { error:{ code:'LIMIT_REACHED', message:'Data files per hour reached.',
      details:{ limit:'terminal.files_per_hour', allowed:300, retry_after_s:120 } } }, { 'Retry-After':'120' });
    const e: any = await fetchFile(CUT).catch(x => x);
    expect(e).toBeInstanceOf(Error);
    expect({ code:e.code, generic:/could not be downloaded/.test(e.message) }).toEqual({ code:'LIMIT_REACHED', generic:false });
  });
  it('a plan refusal of the cut (403 CAPABILITY_REQUIRED) is a plan refusal, not a broken download', async () => {
    answer(403, { error:{ code:'CAPABILITY_REQUIRED', message:'x',
      details:{ capability:'terminal.tickers', display_name:'Tickers' } } });
    const e: any = await fetchFile(CUT).catch(x => x);
    expect({ code:e.code, generic:/could not be downloaded/.test(e.message) }).toEqual({ code:'CAPABILITY_REQUIRED', generic:false });
  });
});
