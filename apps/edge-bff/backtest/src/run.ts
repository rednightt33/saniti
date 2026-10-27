/* Run (backtest.html section 10 · RUN): the reference computes the backtest in the page; here the page sends the
   settings as a BacktestRequest (api/request.ts), polls the job about once a second while it shows the reference's
   own running state, and renders the server's result through the adapter (api/adapt.ts). The texts are the
   reference's; #runNote also names the job phase and its progress while the job runs. An error is shown with
   toastError() and stays in #runNote until the next run (review PG-6: the toast lasts 2.2 s). */
import type { JobStatus } from './core/contract.ts';
import { ApiFailure } from './api/types.ts';
import { adaptResult } from './api/adapt.ts';
import { currentRequest } from './api/request.ts';
import { API, catalogReady, whenCatalog } from './env.ts';
import { $, toast, toastError } from './format.ts';
import { edits, S } from './state.ts';
import { refreshSignals } from './signals.ts';
import { renderResults } from './results/index.ts';
import { ensureCmp } from './results/overview.ts';
import { setView, updateViewbar } from './builder.ts';
import { BX, setExpanded } from './layout.ts';

/** how often the job's status is asked for while it runs */
export const POLL_MS = 1000;
const sleep = (ms: number) => new Promise<void>(ok => setTimeout(ok, ms));
const buttons = (on: boolean) => document.querySelectorAll('.js-run').forEach((b: Element) => (b as HTMLButtonElement).disabled = !on);

/* the job's phase and progress after the reference's "Running…" */
const progressNote = (st: JobStatus) => {
  const p = st.progress; if (!p) return 'Running…';
  return `Running… · ${p.phase.replace(/_/g, ' ')}${p.total ? ` ${p.done}/${p.total}` : ''}`;
};
/* the message of a job that did not finish */
const jobError = (st: JobStatus) => {
  const e = st.error;
  if (st.state === 'CANCELLED') return 'The backtest was cancelled.';
  return (e && (e.message || e.code)) || 'The backtest failed.';
};

/* a status call that does not reach the server is tried again (twice) before the run is given up */
const statusOf = async (id: string): Promise<JobStatus> => {
  for (let k = 0; ; k++) {
    try { return await API.status(id) }
    catch (e) { if (k >= 2 || !(e instanceof ApiFailure) || e.status) throw e; await sleep(POLL_MS) }
  }
};

/* the run in flight: a newer run, a mode switch or leaving the page abandons it (its job is cancelled) */
let token = 0, job: string | null = null;

/** abandon the run in flight, if any: its job is cancelled and its result is not shown */
export function abortRun() {
  if (!S.running) return;
  token++;
  const id = job; job = null;
  if (id) API.cancel(id).catch(() => {});
  buttons(true); S.running = false; $('runNote').textContent = idleNote; updateViewbar();
}
let idleNote = '', failedNote = false;   // failedNote: #runNote holds the last run's error, not an idle note

export const run = async (scroll = true) => {
  if(!S.conds.some(c=>c.on)){ toast('Add at least one active condition'); return }
  if(S.mode==='portfolio' && !S.tickers.length){ toast('Add at least one stock'); return }     // the server refuses it too (INVALID_PORTFOLIO)
  if (S.running) return;
  // EXEC-BACKTEST-LOAD: the request needs the catalog's limits and dates; a Run before it answers waits for it
  if (!catalogReady()) {
    $('runNote').textContent = 'Loading…';
    try { await whenCatalog() } catch (e) { const m = (e as Error).message || 'The backtest service could not be reached.'; toastError(m); $('runNote').textContent = m; return }
    if (S.running) return;
  }
  if (!failedNote) idleNote = $('runNote').textContent;
  failedNote = false;
  document.querySelectorAll('.js-run').forEach((b: Element) => (b as HTMLButtonElement).disabled = true); $('runNote').textContent = 'Running…'; S.running = true; updateViewbar();
  const my = ++token;
  await sleep(30);
  if (my !== token) return;
  // the settings the job runs: a change after this point leaves its result out of date
  const seq = edits.n, cards = JSON.parse(JSON.stringify(S.conds));
  try {
    const request = currentRequest();
    const { request_id } = await API.submit(request);
    if (my !== token) { API.cancel(request_id).catch(() => {}); return }
    job = request_id;
    let st = await statusOf(request_id);
    while (st.state === 'QUEUED' || st.state === 'RUNNING') {
      if (my !== token) return;
      $('runNote').textContent = progressNote(st);
      await sleep(POLL_MS);
      if (my !== token) return;
      st = await statusOf(request_id);
    }
    if (my !== token) return;
    if (st.state !== 'FINISHED') throw new ApiFailure(jobError(st), st.error?.code || st.state);
    const res = await API.result(request_id);
    if (my !== token) return;
    const R = adaptResult(request_id, res, request, cards);
    // the comparison lines of the overview are drawn on the new result's days
    await ensureCmp(R, S.cmp).catch(e => toastError(e.message));
    if (my !== token) return;
    job = null;
    S.result = R; S.trials = R.trials;
    document.querySelectorAll('.js-run').forEach((b: Element) => (b as HTMLButtonElement).disabled = false); S.running = false; $('runNote').textContent = `Done in ${R.ms} ms · ${S.trials} variants tried ${API.texts.trials}`;
    // a settings change while the job ran leaves the result stale (the reference cannot change settings in its 30 ms)
    S.stale = edits.n !== seq;
    refreshSignals(); renderResults();
    if(scroll) setView('results'); else updateViewbar();
  } catch (e) {
    if (my !== token) return;
    job = null;
    const msg = (e as Error).message || 'The backtest failed.';
    buttons(true); S.running = false; $('runNote').textContent = msg; failedNote = true; updateViewbar();
    toastError(msg);
  }
};

/** the run buttons, the focus-mode backdrop, and the job of a page that is left */
export const bindRun = () => {
  document.querySelectorAll('.js-run').forEach((b: Element) => (b as HTMLButtonElement).onclick = () => { if(BX()) setExpanded(false); run(true) });
  $('bdrop').onclick = () => setExpanded(false);
  addEventListener('pagehide', () => abortRun());
};
