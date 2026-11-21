/* EXEC-MU-ACCOUNTS 3e, the example mode as the user set it on 2026-11-21 (ERRORS M527): "screener juga oke": a preset
   with its results, the data of 30 October 2026 (Golden Cross: brk52 matched no stock that day, the user chose "A";
   terminal-publisher examples.py SCREENER_PRESET). The ScreenerApi of the page opened with
   ?example=1 for a principal holding screener.example: everything comes from the example's files
   (/api/v1/examples/screener, edge-bff app/examples.py), written once by the capture job
   (apps/terminal-publisher/examples.py screener_files, from the real screener-worker run on its own input files cut at
   the example's date):
     screener-catalog   the worker's catalog of that cut publication, for the narrowest context (the released items, no
                        right)
     screener-universe  the universe document of that publication
     screener-screen    the screen the page opens: the preset's id, name and definition
     screener-run       the worker's answer to that screen
   The page opens on that screen (main.ts: it is the last screen of a storage kept in memory, so nothing of the example
   goes into the browser's storage and nothing of the visitor's own comes out), and its run is answered with the stored
   run only when the page asks for that definition: both compared in the page's own form (its cards keep no parameter at
   its default, so the page sends a preset's volume spike without its default length: state.ts stateOfDefinition, then
   definitionOf, canonical); anything else is refused. Saved screens, My
   metrics and the watchlist are empty; nothing else is asked (no preview, validation, count or write). The page stays
   still (shared/example-view.ts): a click asks to sign in or to upgrade. */
import type { CatalogResponse, Definition, RunResponse, UniverseResponse } from '../core/contract.ts';
import { canonical, definitionOf, stateOfDefinition } from '../state.ts';
import { ApiFailure, type Conditional, type ScreenerApi } from './types.ts';

const BASE = '/api/v1/examples/screener';
const NOT_HERE = 'This is an example of the Screener: sign in or upgrade to change it and run your own.';
/** a definition in the page's own form (the cards it would show, then the definition they send; the catalog is loaded
    before any run, so the cards know their entries) */
export const pageForm = (d: Definition) => canonical(definitionOf(stateOfDefinition(d)));

/** the screen the example opens (screener-screen) */
export interface ExampleScreen { preset: string; name: string; definition: Definition }
interface Index { finished_at: string | null; as_of: string; files: Record<string, { sha256: string }> }
interface Got<T> { body: T; bytes: Uint8Array; sha: string }

async function fetched(url: string): Promise<Uint8Array> {
  let r: Response;
  try { r = await fetch(url, { credentials: 'same-origin', headers: { accept: 'application/json' } }) }
  catch { throw new ApiFailure('The example could not be reached. Check the connection and reload the page.', 'NETWORK') }
  const bytes = new Uint8Array(await r.arrayBuffer().catch(() => new ArrayBuffer(0)));
  if (!r.ok) {
    let e: { code?: string; message?: string } | null = null;
    try { e = JSON.parse(new TextDecoder().decode(bytes))?.error ?? null } catch { e = null }
    throw new ApiFailure(e?.message || 'The example could not be read. Try again in a minute.', e?.code || `HTTP_${r.status}`, r.status);
  }
  return bytes;
}

export function exampleApi(): ScreenerApi & { screen(): Promise<ExampleScreen> } {
  let index: Promise<Index> | null = null;
  const files = new Map<string, Promise<Got<unknown>>>();
  const file = <T>(name: string): Promise<Got<T>> => {
    let got = files.get(name);
    if (!got) {
      got = (async () => {
        const i = await (index ??= fetched(`${BASE}/index`).then(b => JSON.parse(new TextDecoder().decode(b)) as Index));
        const e = i.files[name];
        if (!e) throw new ApiFailure(`The example has no ${name}. Reload the page.`, 'EXAMPLE_FILE_NOT_FOUND', 404);
        const bytes = await fetched(`${BASE}/file/${encodeURIComponent(name)}?sha=${e.sha256}`);
        return { body: JSON.parse(new TextDecoder().decode(bytes)), bytes, sha: e.sha256 };
      })();
      got.catch(() => files.delete(name));                 // a failed read is asked again on the next call
      files.set(name, got);
    }
    return got as Promise<Got<T>>;
  };
  const whole = async <T>(name: string): Promise<Conditional<T>> => {
    const f = await file<T>(name);
    return { status: 200, etag: f.sha, body: f.body, bytes: f.bytes };
  };
  const refuse = () => Promise.reject(new ApiFailure(NOT_HERE, 'EXAMPLE', 403));
  return {
    kind: 'live',
    async screen() { return (await file<ExampleScreen>('screener-screen')).body },
    session: async () => ({ login: 'example', csrf: '', access: null }),
    catalog: () => whole<CatalogResponse>('screener-catalog'),
    universe: () => whole<UniverseResponse>('screener-universe'),
    async run(req) {
      const [s, r] = await Promise.all([file<ExampleScreen>('screener-screen'), file<RunResponse>('screener-run')]);
      if (pageForm(req.definition) !== pageForm(s.body.definition)) throw new ApiFailure(NOT_HERE, 'EXAMPLE', 403);
      return { body: r.body, bytes: r.bytes };
    },
    preview: refuse,
    validate: refuse,
    counts: refuse,
    items: async () => ({ items: [] }),
    putItem: refuse,
    deleteItem: refuse,
    watchlist: async () => ({ tickers: [] }),
    watch: refuse,
  };
}
