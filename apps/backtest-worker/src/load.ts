/* The market data of one job or preview, through terminal.ts (CONTRACT.md section 2), within the limits:
   1. the /bundle manifest of every ticker first (no file downloaded yet), so a run that would read more than
      limits.max_download_bytes (the manifest sizes of every file it reads, cached or not, so the answer does not
      depend on the cache) or more than limits.max_broker_rows (the manifest row counts of the broker files) is
      refused before any download: LIMIT_EXCEEDED, 422;
   2. then each ticker's files, decoded by terminal.ts loadTicker from that same manifest (one /bundle call per
      ticker). A presigned URL that has expired by the time its file is fetched (the bucket answers 403) is fetched
      again once from a new /bundle answer; the totals are checked again on the files actually read.
   Cancellation is checked between tickers; progress counts tickers. data_version is datafile.ts dataVersion over
   every file read (CONTRACT section 2). */
import { DataError, dataVersion } from '../../edge-bff/backtest/src/core/datafile.ts';
import type { Limits } from '../../edge-bff/backtest/src/core/contract.ts';
import { Cancelled } from '../../edge-bff/backtest/src/core/engine.ts';
import { TerminalClient } from './terminal.ts';
import type { Dataset, LoadedTicker, ReadFile, TerminalOptions } from './terminal.ts';
import { WorkerError } from './errors.ts';

type Bundle = Awaited<ReturnType<TerminalClient['bundle']>>;

/** A TerminalClient whose loadTicker can start from a /bundle answer already fetched (step 1), so a ticker's manifest
    is asked for once. Any other bundle() call goes to terminal-api as usual. */
export class PlannedClient extends TerminalClient {
  private planned = new Map<string, Bundle>();
  constructor(o: TerminalOptions) { super(o) }
  plan(b: Bundle, datasets: readonly Dataset[]) { this.planned.set(key(b.ticker, datasets), b) }
  async bundle(ticker: string, datasets: readonly Dataset[]): Promise<Bundle> {
    const k = key(ticker, datasets), b = this.planned.get(k);
    if (b) { this.planned.delete(k); return b }
    return super.bundle(ticker, datasets);
  }
}
const key = (ticker: string, datasets: readonly Dataset[]) => `${ticker}|${[...datasets].sort().join(',')}`;

export interface LoadGroup { tickers: readonly string[]; datasets: readonly Dataset[] }
export interface Loaded {
  tickers: Map<string, LoadedTicker>;
  files: ReadFile[];
  data_version: string;
  bytes: number;                 // manifest bytes of every file read
  broker_rows: number;           // manifest rows of every broker file read
}
export interface LoadHooks { shouldStop?(): boolean; progress?(done: number, total: number): void }

function totals(files: readonly { dataset: string; bytes: number; rows?: number | null }[], what: string) {
  let bytes = 0, rows = 0;
  for (const f of files) {
    bytes += f.bytes;
    if (f.dataset === 'broker') {
      if (!Number.isSafeInteger(f.rows)) throw new DataError('DATA_INTEGRITY', `${what}: a broker file has no row count in its manifest.`, what);
      rows += f.rows as number;
    }
  }
  return { bytes, rows };
}
function within(limits: Pick<Limits, 'max_download_bytes' | 'max_broker_rows'>, t: { bytes: number; rows: number }, field: string, tickers: number): void {
  if (t.bytes > limits.max_download_bytes)
    throw new WorkerError(422, 'LIMIT_EXCEEDED', `This run would read ${t.bytes} bytes of published files for ${tickers} ticker(s); the limit is ${limits.max_download_bytes}. Choose a smaller universe or switch off the conditions that need broker data.`,
      field, { limit: 'max_download_bytes', allowed: limits.max_download_bytes, needed: t.bytes });
  if (t.rows > limits.max_broker_rows)
    throw new WorkerError(422, 'LIMIT_EXCEEDED', `This run would read ${t.rows} broker rows for ${tickers} ticker(s); the limit is ${limits.max_broker_rows}. Choose a smaller universe or switch off the conditions that need broker data.`,
      field, { limit: 'max_broker_rows', allowed: limits.max_broker_rows, needed: t.rows });
}

/** At most n tasks at a time over the items, in order; the first error stops new tasks and is thrown. */
async function lanes<T>(items: readonly T[], n: number, task: (item: T, k: number) => Promise<void>): Promise<void> {
  let next = 0, failed: unknown = null;
  const lane = async () => {
    while (!failed && next < items.length) {
      const k = next++;
      try { await task(items[k], k) } catch (e) { failed ||= e }
    }
  };
  await Promise.all(Array.from({ length: Math.max(1, Math.min(n, items.length)) }, lane));
  if (failed) throw failed;
}

export async function loadMarket(client: PlannedClient, groups: readonly LoadGroup[], limits: Pick<Limits, 'max_download_bytes' | 'max_broker_rows'>,
  field: string, concurrency: number, hooks: LoadHooks = {}): Promise<Loaded> {
  const stop = () => { if (hooks.shouldStop?.()) throw new Cancelled() };
  const jobs = groups.flatMap(g => [...new Set(g.tickers)].map(ticker => ({ ticker, datasets: g.datasets })));
  const total = jobs.length;
  let done = 0;
  hooks.progress?.(0, total);
  // 1. manifests, and the limits on them
  const bundles: Bundle[] = new Array(total);
  await lanes(jobs, concurrency, async (j, k) => { stop(); bundles[k] = await client.bundle(j.ticker, j.datasets) });
  const planned = bundles.flatMap(b => (Object.entries(b.datasets) as [Dataset, { files: { bytes: number; rows?: number }[] }][])
    .flatMap(([dataset, ds]) => ds.files.map(f => ({ dataset, bytes: f.bytes, rows: f.rows ?? null }))));
  within(limits, totals(planned, field), field, total);
  // 2. the files, decoded
  const out = new Map<string, LoadedTicker>();
  await lanes(jobs, concurrency, async (j, k) => {
    stop();
    client.plan(bundles[k], j.datasets);
    let t: LoadedTicker;
    try { t = await client.loadTicker(j.ticker, j.datasets, { keepBrokerRows: false }) }
    catch (e) {
      // a presigned URL that expired while the run waited for it: once more from a new manifest
      if (!(e instanceof DataError && e.code === 'DATA_UNAVAILABLE' && e.details?.status === 403)) throw e;
      stop();
      t = await client.loadTicker(j.ticker, j.datasets, { keepBrokerRows: false });
    }
    out.set(j.ticker, t);
    hooks.progress?.(++done, total);
  });
  const files = [...out.values()].flatMap(t => t.files);
  const sum = totals(files, field);
  within(limits, sum, field, total);
  return { tickers: out, files, data_version: await dataVersion(files), bytes: sum.bytes, broker_rows: sum.rows };
}
