/* EXEC-MU-ACCOUNTS 3e, the example mode as the user set it on 2026-11-21 (ERRORS M527): "screener juga oke": the preset
   "52W Breakout + Volume" (brk52) with its results, the data of 30 October 2026. The Screener evaluates every stock at
   its newest bar and has no evaluation date of its own, so its example is this worker's answer on its own input files
   as they stood at that date. Used by verification/edge_multiuser/example_mode/screener_capture.ts (the capture, on
   terminal-api's publication) and tests/example_capture.test.ts (on these tests' made-up market):
     readPublication  terminal-api's publication for the worker (GET /state, POST /xsection, the reference files), each
                      file checked against its sha256 and size, as the fake terminal's publication rows
                      (tests/fake-terminal.mjs startFakeTerminal)
     cutPublication   that publication as it stood at the date: every price, action and broker day after it left out, a
                      stock without a price by then left out of the reference, no stock lists (their members are recorded
                      only since 10 November 2026, ERRORS M527: the Index and Group pickers, behind a click, say no
                      data), and the date itself as the publication's time (the page's data line: "published <date>")
     screenOn         the worker itself (createApp with the configuration given) on a publication served by the fake
                      terminal: its catalog, its universe and its run of one preset for a context (the items the run may
                      read, no right), as edge-bff relays them
   Nothing here computes a screen: the worker's own refresh, snapshot and run do, as in production. */
import { TerminalApi, XSECTION_MAX_NAMES } from '../src/refresh.ts';
import { inflateVerified } from '../../edge-bff/backtest/src/core/datafile.ts';
import type { Columnar } from '../../edge-bff/backtest/src/core/datafile.ts';
import { createApp } from '../src/server.ts';
import { loadConfig } from '../src/config.ts';
import { ACTION_COLUMNS, startFakeTerminal } from './fake-terminal.mjs';
import { auth, call, KEY, PROXY } from './helpers.ts';

/** a publication as the fake terminal serves it (tests/fake-terminal.mjs startFakeTerminal) */
export interface Publication {
  finished_at: string; price_through?: string | null; broker_through?: string | null;
  prices: Record<string, unknown[][]>; ref: unknown[][]; refColumns?: string[]; actions: unknown[][];
  broker?: Record<string, unknown[][]>; brokers?: unknown[][];
}
export interface Example { catalog: any; universe: any; screen: { preset: string; name: string; definition: unknown }; run: any }

const BROKER_COLUMNS = ['code', 'name', 'type', 'classification'];
const column = (doc: Columnar, c: string): unknown[] => {
  const v = doc[c];
  if (!Array.isArray(v)) throw new Error(`the document has no column ${c}`);
  return v;
};

/** the price file's rows per ticker, [[d, o, h, l, c, v], ...] in date order (publisher.py xsection_price_doc) */
export function pricesOf(doc: Columnar): Record<string, unknown[][]> {
  const [t, d, o, h, l, c, v] = ['t', 'd', 'o', 'h', 'l', 'c', 'v'].map(k => column(doc, k)), out: Record<string, unknown[][]> = {};
  for (let k = 0; k < t.length; k++) (out[t[k] as string] ??= []).push([d[k], o[k], h[k], l[k], c[k], v[k]]);
  for (const rows of Object.values(out)) rows.sort((a, b) => (a[0] as string) < (b[0] as string) ? -1 : 1);
  return out;
}
/** the actions file's rows [t, d, type, ratio_old, ratio_new, amount_per_share, currency] */
export function actionsOf(doc: Columnar): unknown[][] {
  const cols = ACTION_COLUMNS.map((k: string) => column(doc, k));
  return cols[0].map((_, k) => cols.map(c => c[k]));
}
/** one broker day file's rows [t, broker, investor_type, board, bv, sv, bl, sl, bf, sf, gap] (P4 section 1) */
export function brokerRowsOfDay(doc: Columnar): unknown[][] {
  const brokers = doc.brokers as string[], types = doc.investor_types as string[], boards = doc.boards as string[];
  const tickers = doc.tickers as { t: string; rows: number }[], gap = new Set((doc.gap as [string, string][] ?? []).map(g => JSON.stringify(g)));
  const [b, i, m, bv, sv, bl, sl, bf, sf] = ['b', 'i', 'm', 'bv', 'sv', 'bl', 'sl', 'bf', 'sf'].map(k => column(doc, k));
  const rows: unknown[][] = [];
  let k = 0;
  for (const { t, rows: n } of tickers) for (let j = 0; j < n; j++, k++) {
    const board = boards[m[k] as number];
    rows.push([t, brokers[b[k] as number], types[i[k] as number], board, bv[k], sv[k], bl[k], sl[k], bf[k], sf[k], gap.has(JSON.stringify([t, board]))]);
  }
  if (k !== b.length) throw new Error(`the broker day ${doc.date} lists ${k} rows under its tickers, not ${b.length}`);
  return rows;
}
/** a reference file's rows and columns */
export function rowsOf(doc: Columnar, columns = doc.columns): unknown[][] {
  const cols = columns.map(c => column(doc, c));
  return cols[0].map((_, k) => cols.map(c => c[k]));
}

/** terminal-api's publication for the worker, every file checked against its sha256 and size */
export async function readPublication(url: string, proxyKey: string, timeoutMs = 120_000): Promise<Publication> {
  const api = new TerminalApi({ url, proxyKey, retries: 2, retryBaseMs: 1000, timeoutMs, maxBytes: 1 << 26, concurrency: 4 });
  const st = await api.state();
  const index = st.xsection ?? {}, names = Object.keys(index);
  const docs: Record<string, Columnar> = {};
  for (let k = 0; k < names.length; k += XSECTION_MAX_NAMES) {
    const grant = await api.xsection(names.slice(k, k + XSECTION_MAX_NAMES));
    if (grant.finished_at !== st.finished_at) throw new Error('terminal-api answered another publication than /state named: run the capture again');
    for (const f of grant.files) {
      const want = index[f.name];
      if (!want || want.sha256 !== f.sha256 || want.bytes !== f.bytes) throw new Error(`the grant of ${f.name} differs from the index`);
      const res = await fetch(f.url, { signal: AbortSignal.timeout(timeoutMs) });
      if (!res.ok) throw new Error(`the file ${f.name} answered ${res.status}`);
      docs[f.name] = await inflateVerified(new Uint8Array(await res.arrayBuffer()), want, f.name);
    }
  }
  const reference = async (name: string): Promise<Columnar> => {
    const r = await api.referenceFile(name);
    const res = await fetch(r.url, { signal: AbortSignal.timeout(timeoutMs) });
    if (!res.ok) throw new Error(`the reference file ${name} answered ${res.status}`);
    const raw = new Uint8Array(await res.arrayBuffer());
    if (r.sha256 === null || r.bytes === null) throw new Error(`terminal-api names no sha256 or size for the reference file ${name}`);
    return inflateVerified(raw, { sha256: r.sha256, bytes: r.bytes }, name);
  };
  const [tickers, brokers] = [await reference('tickers'), await reference('brokers')];
  const broker = Object.fromEntries(Object.entries(docs).filter(([n]) => n.startsWith('broker-')).map(([n, d]) => [n.slice('broker-'.length), brokerRowsOfDay(d)]));
  return { finished_at: st.finished_at, price_through: st.price_through, broker_through: st.broker_through,
    prices: pricesOf(docs.price), actions: actionsOf(docs.actions), broker, ref: rowsOf(tickers), refColumns: tickers.columns,
    brokers: rowsOf(brokers, BROKER_COLUMNS) };
}

/** the publication as it stood at asOf (module comment) */
export function cutPublication(p: Publication, asOf: string): Publication {
  const prices = Object.fromEntries(Object.entries(p.prices).map(([t, rows]) => [t, rows.filter(r => (r[0] as string) <= asOf)]).filter(([, rows]) => rows.length));
  const broker = Object.fromEntries(Object.entries(p.broker ?? {}).filter(([d]) => d <= asOf));
  const days = Object.keys(broker).sort();
  const through = Object.values(prices).reduce((m, rows) => { const d = rows[rows.length - 1][0] as string; return d > m ? d : m }, '');
  if (through !== asOf) throw new Error(`the publication has no price on ${asOf} (its newest price by then is ${through || 'none'})`);
  const tickerAt = (p.refColumns ?? ['ticker']).indexOf('ticker');
  return { finished_at: asOf, price_through: asOf, broker_through: days.length ? days[days.length - 1] : null, prices,
    ref: p.ref.filter(r => (r[tickerAt] as string) in prices), refColumns: p.refColumns,
    actions: p.actions.filter(r => (r[1] as string) <= asOf), broker, brokers: p.brokers };
}

/** the worker on a publication: its catalog, universe and run of one preset for a context (module comment) */
export async function screenOn(p: Publication, env: Record<string, string>, presetId: string, context: Record<string, unknown>): Promise<Example> {
  const fake = await startFakeTerminal({ key: PROXY, publication: p });
  const app = createApp(loadConfig({ ...env, SCREENER_WORKER_KEY: KEY, TERMINAL_URL: fake.url, TERMINAL_PROXY_KEY: PROXY, SCREENER_FILE_ORIGIN: fake.url }),
    { pollMs: 3_600_000 });
  try {
    const port = await app.listen(0, '127.0.0.1');
    await app.refresher.tick();
    await app.refresher.tick();                          // a follow-up refresh of the broker days, when there are some
    if (!app.state().current) throw new Error('the worker loaded no snapshot of the publication');
    const answer = async (method: string, path: string, body?: unknown) => {
      const r = await call(port, method, path, body, auth());
      if (r.status !== 200) throw new Error(`the worker answered ${path} ${r.status} ${JSON.stringify(r.body?.error ?? r.body).slice(0, 300)}`);
      return r.body;
    };
    const catalog = await answer('GET', '/v1/catalog'), universe = await answer('GET', '/v1/universe');
    const preset = (catalog.presets ?? []).find((x: { id: string }) => x.id === presetId);
    if (!preset) throw new Error(`the catalog has no preset ${presetId}`);
    const run = await answer('POST', '/v1/run', { schema_version: 1, client_order: { page: 'example', seq: 1 }, definition: preset.definition, context });
    return { catalog, universe, screen: { preset: presetId, name: preset.name, definition: preset.definition }, run };
  } finally { await app.close(); await fake.close() }
}
