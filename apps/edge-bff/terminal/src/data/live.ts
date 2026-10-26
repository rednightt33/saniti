/* Live data: the pre-published files of the rack (bucket terminal-display) reached through EDGE's /api/terminal
   gateway (FRONTEND_HANDOFF.md). The page asks for presigned URLs and downloads the gzip JSON files itself.
   Everything is mapped into the reference page's own shapes (types.ts). */
import type { Bar, BrokerRow, Combo, CompareSpec, Instrument, MarketData, MarketEvent, Point, VolumePoint } from './types';

const API = '/api/terminal/v1';
const MAX_YEARS_PER_CALL = 6;           // terminal-api FilesRequest

export class TerminalError extends Error {
  constructor(message: string, readonly status = 0) { super(message) }
}

/* the compare list of the reference's Add Series panel, with its colours; offered when the ticker is published */
const COMPARE: CompareSpec[] = [
  { id:'ihsg', symbol:'IHSG', name:'Composite Index', color:'#0070f3' },
  { id:'bbca', symbol:'BBCA', name:'Bank Central Asia', color:'#7928ca' },
  { id:'bbri', symbol:'BBRI', name:'Bank Rakyat Indonesia', color:'#7c5cff' },
  { id:'bmri', symbol:'BMRI', name:'Bank Mandiri', color:'#f59e0b' },
  { id:'tlkm', symbol:'TLKM', name:'Telkom Indonesia', color:'#ef4444' },
  { id:'asii', symbol:'ASII', name:'Astra International', color:'#14b8a6' },
  { id:'unvr', symbol:'UNVR', name:'Unilever Indonesia', color:'#8b5cf6' },
  { id:'goto', symbol:'GOTO', name:'GoTo Gojek Tokopedia', color:'#10b981' },
  { id:'antm', symbol:'ANTM', name:'Aneka Tambang', color:'#06b6d4' },
  { id:'excl', symbol:'EXCL', name:'XL Axiata', color:'#ec4899' }
];

/* idx_event_annotation corporate actions → the reference's event types; the date role names the tooltip row */
const EVENT_TYPE: Record<string, string> = {
  DIVIDEND:'dividend', STOCK_SPLIT:'stocksplit', REVERSE_SPLIT:'reversesplit', RIGHT_ISSUE:'rightissue',
  BONUS_SHARE:'bonus', RUPS:'rups', TENDER_OFFER:'tenderoffer', WARRANT:'warrant'
};
const EVENT_TITLE: Record<string, string> = {
  dividend:'Dividend', stocksplit:'Stock split', reversesplit:'Reverse split', rightissue:'Rights issue',
  bonus:'Bonus shares', rups:'RUPS', tenderoffer:'Tender offer', warrant:'Warrant'
};
/* one detail value as the reference tooltip writes it (Rp 25 / share, 2.50%, 2026-08-28); null → Unavailable */
export const UNAVAILABLE = 'Unavailable';
export function detailText(value: unknown, kind: string): string {
  if (value === null || value === undefined || value === '') return UNAVAILABLE;
  if (typeof value !== 'number') return String(value);
  const idr = (n: number) => 'Rp ' + (Number.isInteger(n) ? n : +n.toFixed(2)).toLocaleString('en-US');
  if (kind === 'idr_per_share') return idr(value) + ' / share';
  if (kind === 'idr') return idr(value);
  if (kind === 'pct') return value.toFixed(2) + '%';
  if (kind === 'shares') return Math.round(value).toLocaleString('en-US');
  return String(value);
}
const roleLabel = (role: string) => role.toLowerCase().split('_').map((w, i) => i ? w : w[0].toUpperCase() + w.slice(1)).join(' ');

interface Columnar { columns: string[]; [k: string]: any }
const rowsOf = (doc: Columnar) => {
  const n = doc[doc.columns[0]].length;
  return Array.from({ length:n }, (_, i) => Object.fromEntries(doc.columns.map(c => [c, doc[c][i]])));
};

async function api(path: string, csrf: string, body?: unknown) {
  const res = await fetch(API + path, body === undefined ? { credentials:'same-origin' }
    : { method:'POST', credentials:'same-origin', headers:{ 'Content-Type':'application/json', 'X-CSRF-Token':csrf }, body:JSON.stringify(body) });
  let data: any = null;
  try { data = await res.json() } catch(e) {}
  if (!res.ok) {
    const msg = data && (data.message || (data.error && (data.error.code || data.error)));
    throw new TerminalError(res.status === 401 ? 'Sign in to EDGE first, then open the Terminal tab again.'
      : res.status === 429 ? `Download limit reached: ${msg || 'try again later'}.`
      : `The terminal data service answered ${res.status}${msg ? ` (${msg})` : ''}.`, res.status);
  }
  return data;
}

/* gzip JSON from a presigned URL; a body the browser already inflated (Content-Encoding) is read as is */
async function download(url: string): Promise<Columnar> {
  const res = await fetch(url, { credentials:'omit' });
  if (!res.ok) throw new TerminalError(`A data file could not be downloaded (${res.status}).`, res.status);
  const bytes = new Uint8Array(await res.arrayBuffer());
  if (bytes[0] === 0x1f && bytes[1] === 0x8b) {
    const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'));
    return JSON.parse(await new Response(stream).text());
  }
  return JSON.parse(new TextDecoder().decode(bytes));
}

async function session(): Promise<string> {
  const res = await fetch('/api/v1/auth/session', { credentials:'same-origin' });
  if (!res.ok) throw new TerminalError('Sign in to EDGE first, then open the Terminal tab again.', res.status);
  const data = await res.json();
  return data.csrf_token || '';
}

/* every chunk of years is asked for and downloaded at once (the URLs live 120 s, so each chunk downloads right away) */
async function datasetFiles(ticker: string, dataset: 'price' | 'broker', years: number[], csrf: string) {
  const chunks: number[][] = [];
  for (let k = 0; k < years.length; k += MAX_YEARS_PER_CALL) chunks.push(years.slice(k, k + MAX_YEARS_PER_CALL));
  const parts = await Promise.all(chunks.map(async chunk => {
    const answer = await api('/files', csrf, { ticker, dataset, years:chunk });
    return Promise.all(answer.files.map((f: any) => download(f.url)));
  }));
  return parts.flat() as Columnar[];
}

const yearsOf = (manifest: any, dataset: string) => Object.keys(manifest.datasets?.[dataset]?.years || {}).map(Number).filter(Number.isFinite).sort((a, b) => a - b);

async function prices(ticker: string, csrf: string) {
  const manifest = await api(`/manifest/${ticker}`, csrf);
  const docs = await datasetFiles(ticker, 'price', yearsOf(manifest, 'price'), csrf);
  const out: { d: string; o: number; h: number; l: number; c: number; v: number | null }[] = [];
  docs.forEach(doc => rowsOf(doc).forEach((r: any) => { if ([r.o, r.h, r.l, r.c].every(Number.isFinite)) out.push(r) }));
  out.sort((a, b) => a.d < b.d ? -1 : a.d > b.d ? 1 : 0);
  return { manifest, rows: out };
}

/* a series on the chart's sessions: the last close on or before each session (forward fill); sessions before its
   first close have no point */
function alignTo(dates: string[], rows: { d: string; c: number }[]): Point[] {
  const out: Point[] = []; let k = 0, last: number | null = null;
  for (const t of dates) {
    while (k < rows.length && rows[k].d <= t) { last = rows[k].c; k++ }
    if (last !== null) out.push({ time:t, value:last });
  }
  return out;
}

export async function liveData(stored: string | null): Promise<MarketData> {
  const csrf = await session();
  const reference = async (name: string) => rowsOf(await download((await api(`/reference/${name}`, csrf)).url));
  /* the independent downloads start together: references, the ticker's price, IHSG and the broker files */
  const brokerRefP = reference('brokers');
  const tickers = await reference('tickers') as { ticker: string; name: string; type: string; sector: string | null }[];
  const known = new Set(tickers.map(t => t.ticker));
  const instruments: Instrument[] = tickers.map(t => [t.ticker, t.name || t.ticker, t.sector || (t.type === 'index' ? 'Index' : 'Other'), 0]);
  const SYMBOL = stored && known.has(stored) ? stored : known.has('MAPI') ? 'MAPI' : tickers[0].ticker;

  const mainP = prices(SYMBOL, csrf);
  const ihsgP = SYMBOL === 'IHSG' ? mainP : prices('IHSG', csrf);
  const brokerP = mainP.then(m => { const y = yearsOf(m.manifest, 'broker'); return y.length ? datasetFiles(SYMBOL, 'broker', y, csrf) : [] });
  const main = await mainP;
  if (!main.rows.length) throw new TerminalError(`No price data is published for ${SYMBOL}.`);
  const ohlc: Bar[] = main.rows.map(r => ({ time:r.d, open:r.o, high:r.h, low:r.l, close:r.c }));
  const volume: VolumePoint[] = main.rows.map(r => ({ time:r.d, value:r.v ?? 0, color:r.c >= r.o ? 'rgba(0,150,109,.48)' : 'rgba(235,57,69,.48)' }));
  const lineData: Point[] = ohlc.map(b => ({ time:b.time, value:b.close }));
  const dates = ohlc.map(b => b.time), N = dates.length, idx = new Map(dates.map((t, i) => [t, i]));

  /* IHSG for Statistics → Relative performance; sessions before its first close take its first close */
  const ihsgRows = (await ihsgP).rows;
  const ihsgAligned = alignTo(dates, ihsgRows);
  const first = ihsgAligned.length ? ihsgAligned[0].value : NaN;
  const ihsg: Point[] = dates.map((t, i) => ihsgAligned[i - (N - ihsgAligned.length)] ?? { time:t, value:first });

  /* broker files: Flow Timeline (net per broker × investor type × board) and Broker activity (last 30 sessions) */
  const brokerDocs = await brokerP;
  const brokerTypes = new Map((await brokerRefP).map((r: any) => [r.code, r.type]));
  const board = (m: string) => /nego/i.test(m) ? 'Nego' : /cash|tunai/i.test(m) ? 'Cash' : 'Regular';
  const combos = new Map<string, Combo>(), byDate = new Map<string, BrokerRow[]>();
  let flowFrom = N;
  brokerDocs.forEach(doc => rowsOf(doc).forEach((r: any) => {
    const m = board(r.m), key = `${r.b}|${r.i}|${m}`;
    const row: BrokerRow = [r.b, r.i, m, r.bv || 0, r.sv || 0, r.bl || 0, r.sl || 0];
    (byDate.get(r.d) || byDate.set(r.d, []).get(r.d)!).push(row);
    const i = idx.get(r.d); if (i === undefined) return;
    flowFrom = Math.min(flowFrom, i);
    if (!combos.has(key)) combos.set(key, { broker:r.b, investor:r.i, board:m, gross:0, tilt:0, net:new Float64Array(N) });
    const c = combos.get(key)!; c.net[i] += row[3] - row[4]; c.gross += row[3] + row[4];
  }));
  const brokerDates = [...byDate.keys()].sort().slice(-30);

  const catalog = COMPARE.filter(c => known.has(c.symbol));
  const loadCompare = async (id: string) => {
    const spec = catalog.find(c => c.id === id); if (!spec) return [];
    const rows = spec.symbol === 'IHSG' ? ihsgRows : spec.symbol === SYMBOL ? main.rows : (await prices(spec.symbol, csrf)).rows;
    return alignTo(dates, rows);
  };

  const loadEvents = async (): Promise<MarketEvent[]> => {
    if (!main.manifest.datasets?.events) return [];
    const answer = await api('/files', csrf, { ticker:SYMBOL, dataset:'events' });
    const doc = await download(answer.files[0].url);
    return rowsOf(doc).flatMap((r: any, k) => {
      const type = r.family === 'CORPORATE_ACTION' ? EVENT_TYPE[r.type] : undefined;
      if (!type || r.d < dates[0]) return [];
      const at = dates.find(t => t >= r.d);                 // the marker sits on the first session on or after the date
      /* T9 (user 2026-10-26): the published detail rows; a value the source leaves blank shows "Unavailable" */
      const rows: [string, string][] = Array.isArray(r.detail)
        ? r.detail.map(([label, value, kind]: [string, unknown, string]) => [label, detailText(value, kind)] as [string, string])
        : [[roleLabel(r.role || 'Date'), r.d]];
      if (r.instrument) rows.push(['Instrument', r.instrument]);
      return [{ id:`${SYMBOL}-${type}-${r.d}-${k}`, type, date:r.d, at, title:r.title || EVENT_TITLE[type], rows }];
    });
  };

  return {
    mode:'live', symbol:SYMBOL, instruments, ohlc, volume, lineData, catalog, loadCompare, ihsg,
    combos:[...combos.values()], flowSource:'real', flowFrom,
    broker: { dates:brokerDates, rows:d => byDate.get(brokerDates[d]) || [], label:SYMBOL,
              category:b => brokerTypes.get(b) === 'Foreign' ? 'F' : 'L' },
    loadEvents,
    hide: { brokerGauge:true, bandar:true }
  };
}
