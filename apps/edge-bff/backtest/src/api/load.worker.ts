/* The Backtest page's loading worker (EXEC-BACKTEST-LOAD, K3; as the Terminal's src/data/worker.ts, EXEC-TERMINAL-UI-1026
   U7: "supaya layar tidak membeku"): downloads, checks and decodes a ticker's files off the page's main thread
   (load.ts) and answers the decoded prices or broker flow. Its own handle on the shared browser cache. */
import { fileCache } from '../../../terminal/src/data/rack.ts';
import { loadFlow, loadPrice, type LoadAnswer, type LoadJob } from './load.ts';

const cache = fileCache();
const scope = globalThis as unknown as { onmessage: ((e: MessageEvent<LoadJob>) => void) | null; postMessage(m: LoadAnswer): void };
scope.onmessage = async (e: MessageEvent<LoadJob>) => {
  const job = e.data;
  try {
    const out = job.kind === 'price' ? await loadPrice(job.ticker, job.files, cache) : await loadFlow(job.ticker, job.files, job.dates, cache);
    scope.postMessage({ id: job.id, ok: true, out });
  } catch (err: any) {
    scope.postMessage({ id: job.id, ok: false, error: { message: String(err?.message || err), code: String(err?.code || 'DATA_INTEGRITY'), status: Number(err?.status) || 0, field: err?.field } });
  }
};
