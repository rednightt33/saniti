/* The market data of one job or preview, through terminal.ts (CONTRACT.md section 2), within the limits:
   1. the /bundle manifest of every ticker first (no file downloaded yet). A group marked skipUnpublished (a portfolio
      universe) leaves out a ticker that terminal-api does not publish (404) or that has no file of a dataset asked
      (events aside: terminal.ts unpublished), listed in Loaded.excluded (lead decision 2026-10-26: no published files,
      DATA_MISSING, leaves the ticker out of a portfolio run); in any other group that is the run's DATA_MISSING. Then
      hooks.planned sees the manifests of the tickers that stay (a check on their data_through before any download),
      and a run that would read more than limits.max_download_bytes (the manifest sizes of every file it reads, cached
      or not, so the answer does not depend on the cache) or more than limits.max_broker_rows (the manifest row counts
      of the broker files) is refused before any download: LIMIT_EXCEEDED, 422;
   2. then each ticker's files, decoded by terminal.ts loadTicker from that same manifest (one /bundle call per
      ticker). A presigned URL that has expired by the time its file is fetched (the bucket answers 403) is fetched
      again once from a new /bundle answer; the totals are checked again on the files actually read.
   Cancellation is checked between tickers; progress counts tickers (a left-out ticker counts as done once its
   manifest is read). data_version is datafile.ts dataVersion over every file read (CONTRACT section 2). */
import { DataError, dataVersion } from '../../edge-bff/backtest/src/core/datafile.ts';
import type { Limits } from '../../edge-bff/backtest/src/core/contract.ts';
import { Cancelled } from '../../edge-bff/backtest/src/core/engine.ts';
import type { Exclusion } from '../../edge-bff/backtest/src/core/engine.ts';
import { TerminalClient, unpublished } from './terminal.ts';
import type { Dataset, LoadedTicker, ReadFile, TerminalOptions } from './terminal.ts';
import { WorkerError } from './errors.ts';

export type Bundle = Awaited<ReturnType<TerminalClient['bundle']>>;

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

export interface LoadGroup {
  tickers: readonly string[]; datasets: readonly Dataset[];
  skipUnpublished?: boolean;     // a ticker without published files is left out (Loaded.excluded), not an error
}
export interface Loaded {
  tickers: Map<string, LoadedTicker>;
  excluded: Exclusion[];         // the skipUnpublished tickers left out, with their DATA_MISSING, in the order asked
  files: ReadFile[];
  data_version: string;
  bytes: number;                 // manifest bytes of every file read
  broker_rows: number;           // manifest rows of every broker file read
}
export interface LoadHooks {
  shouldStop?(): boolean;
  progress?(done: number, total: number): void;
  /** the manifests of the tickers that are loaded, after step 1 and before any file is downloaded */
  planned?(bundles: ReadonlyMap<string, Bundle>): void | Promise<void>;
}

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
  const jobs = groups.flatMap(g => [...new Set(g.tickers)].map(ticker => ({ ticker, datasets: g.datasets, skip: !!g.skipUnpublished })));
  const total = jobs.length;
  let done = 0;
  hooks.progress?.(0, total);
  // 1. manifests, the tickers without published files, and the limits on the manifests
  const bundles: (Bundle | null)[] = new Array(total).fill(null), gone: (Exclusion | null)[] = new Array(total).fill(null);
  await lanes(jobs, concurrency, async (j, k) => {
    stop();
    let b: Bundle;
    try { b = await client.bundle(j.ticker, j.datasets) }
    catch (e) {
      if (!(j.skip && e instanceof DataError && e.code === 'DATA_MISSING')) throw e;
      gone[k] = { ticker: j.ticker, code: e.code, field: e.field, message: e.message };
      return;
    }
    const none = unpublished(b, j.datasets);
    if (none && !j.skip) throw none;
    if (none) gone[k] = { ticker: j.ticker, code: none.code, field: none.field, message: none.message };
    else bundles[k] = b;
  });
  const excluded = gone.filter((x): x is Exclusion => x !== null);
  done = excluded.length;
  if (done) hooks.progress?.(done, total);
  const kept = jobs.map((j, k) => ({ ...j, bundle: bundles[k] })).filter((j): j is typeof j & { bundle: Bundle } => j.bundle !== null);
  await hooks.planned?.(new Map(kept.map(j => [j.ticker, j.bundle])));
  const planned = kept.flatMap(({ bundle: b }) => (Object.entries(b.datasets) as [Dataset, { files: { bytes: number; rows?: number }[] }][])
    .flatMap(([dataset, ds]) => ds.files.map(f => ({ dataset, bytes: f.bytes, rows: f.rows ?? null }))));
  within(limits, totals(planned, field), field, kept.length);
  // 2. the files, decoded
  const out = new Map<string, LoadedTicker>();
  await lanes(kept, concurrency, async j => {
    stop();
    client.plan(j.bundle, j.datasets);
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
  within(limits, sum, field, kept.length);
  return { tickers: out, excluded, files, data_version: await dataVersion(files), bytes: sum.bytes, broker_rows: sum.rows };
}

/** The date the broker data is published through: the newest broker data_through among the stocks' manifests
    (terminal-api /manifest, no file granted). The publisher writes its broker data_through into the manifest of every
    stock whose files it changes, so a stock without new files (a suspended one) keeps an older date and only the
    newest is the broker data's date. A stock terminal-api does not publish (404) has none; null when no stock has one. */
export async function brokerDataThrough(client: TerminalClient, stocks: readonly string[], concurrency: number, shouldStop?: () => boolean): Promise<string | null> {
  let newest: string | null = null;
  await lanes(stocks, concurrency, async t => {
    if (shouldStop?.()) throw new Cancelled();
    let d: string | null | undefined;
    try { d = (await client.manifest(t)).data_through.broker }
    catch (e) { if (e instanceof DataError && e.code === 'DATA_MISSING') return; throw e }
    if (typeof d === 'string' && (newest === null || d > newest)) newest = d;
  });
  return newest;
}
