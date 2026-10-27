/* EXEC-BACKTEST-LOAD (user 2026-10-27: "Agar waktu loading bisa sama. Seperti bagian terminal."; K3): what turns a
   /bundle answer into the page's data: each file from the browser cache or downloaded (the rack module shared with the
   Terminal: apps/edge-bff/terminal/src/data/rack.ts), checked against its manifest entry and decoded (core
   datafile.ts: every file's bytes and sha256, a complete file that is not what its manifest says is DATA_INTEGRITY and
   is not asked again), then the ticker's prices or its broker flow (core flow.ts). It runs in the page's Web Worker
   (load.worker.ts), so a large file (a broker archive) never stops the page, and on the page where there is no Worker
   (the tests). Only bytes that pass inflateVerified are stored. */
import { brokerGaps, brokerRows, inflateVerified, priceSeries, type FileEntry, type PriceSeries } from '../core/datafile.ts';
import { flowData, type FlowData } from '../core/flow.ts';
import { DownloadError, fetchFile, type FileCache } from '../../../terminal/src/data/rack.ts';
import { ApiFailure } from './types.ts';

/* a file from the cache when its bytes still match the manifest entry, else the presigned file */
async function download(f: FileEntry, what: string, cache: FileCache) {
  const sha = String(f.sha256).toLowerCase(), hit = await cache.get(sha);
  if (hit) {
    try { return await inflateVerified(hit, f, what) }
    catch { /* a stored file that does not match its manifest entry is not used: it is downloaded (and replaced) */ }
  }
  let raw: Uint8Array;
  try { raw = await fetchFile(f.url) }
  catch (e) { if (e instanceof DownloadError) throw new ApiFailure(e.message, 'DATA_UNAVAILABLE', e.status); throw e }
  const doc = await inflateVerified(raw, f, what);
  cache.put(sha, raw);                                         // inflateVerified: these bytes hash to sha
  return doc;
}
const readAll = (ticker: string, dataset: string, files: FileEntry[], cache: FileCache) =>
  Promise.all(files.map((f, k) => download(f, `${ticker} ${dataset} file ${k + 1}`, cache)));

/** a ticker's price series from its price files */
export const loadPrice = async (ticker: string, files: FileEntry[], cache: FileCache): Promise<PriceSeries> =>
  priceSeries(ticker, await readAll(ticker, 'price', files, cache));

/** a ticker's broker flow on its price dates, from its broker files */
export async function loadFlow(ticker: string, files: FileEntry[], dates: string[], cache: FileCache): Promise<FlowData> {
  const docs = await readAll(ticker, 'broker', files, cache);
  return flowData(brokerRows(docs), dates, brokerGaps(docs));
}

/** the messages between the page and its loading worker */
export type LoadJob = { id: number; kind: 'price'; ticker: string; files: FileEntry[] }
  | { id: number; kind: 'flow'; ticker: string; files: FileEntry[]; dates: string[] };
export type LoadAnswer = { id: number; ok: true; out: PriceSeries | FlowData }
  | { id: number; ok: false; error: { message: string; code: string; status: number; field?: string } };
