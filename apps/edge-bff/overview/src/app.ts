/* EXEC-OVERVIEW O5: the Market Overview page, ported from the design market-overview-target-c-ihsg-flow.html with the
   publisher's files in place of its illustration (all English, decision 8). It loads three files (overview-meta,
   overview-series, the newest overview-day) and computes nothing of its own: src/model.ts picks the rows of the user's
   universe, period and metric. The state lives in the URL hash, as in the design. */
import { OverviewError, cached } from './api.ts';
import { lockOnly } from '../../shared/example-view.ts';
import * as M from './model.ts';
import type { Day, Meta, OverviewApi, OverviewIndex, Series, StocksFile } from './types.ts';

const $ = <T extends HTMLElement = HTMLElement>(s: string, r: ParentNode = document) => r.querySelector(s) as T;
const $$ = <T extends HTMLElement = HTMLElement>(s: string, r: ParentNode = document) => [...r.querySelectorAll(s)] as T[];
const esc = (s: unknown) => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c] as string);
const DOT = ' · ';

type Ema = 'EMA50' | 'EMA200';
type Window = '60D' | '120D' | '1Y' | 'C';
type SectorP = M.SectorPeriod | 'C';
interface State {
  u: string; mm: M.MapMetric; cl: M.TilePeriod; per: M.IhsgPeriod; sp: SectorP; brk: Ema; brp: Window;
  tmp: M.TilePeriod; ff: M.FlowPeriod; date: string; sel: string | null; open: boolean;
  // F1: each panel's Custom range (period 'C'), in the hash as <key>r=YYYY-MM-DD_YYYY-MM-DD
  clr: M.Range | null; spr: M.Range | null; brr: M.Range | null; tmr: M.Range | null; ffr: M.Range | null;
}
const ONE_OF: Record<string, string[]> = {
  mm: ['perf', 'fb'], cl: ['1D', '5D', '1M', 'C'], per: ['1D', '5D', '1M', '1Y'], sp: ['20D', '60D', 'YTD', '1Y', 'C'], brk: ['EMA50', 'EMA200'],
  brp: ['60D', '120D', '1Y', 'C'], tmp: ['1D', '5D', '1M', 'C'], ff: ['1D', '5D', '1M', '3M', 'C'],
};
const WINDOW: Record<string, number> = { '60D': 60, '120D': 120, '1Y': M.YEAR };
/* F1 (user 2026-11-15: "yang berkaitan dengan period, kecuali IHSG, tambahkan "Custom" ... maksimal 1 tahun"; "1A ...
   2 A"): the five panels' period keys, their range keys and their default when the hash names no usable range */
const CUSTOM = { cl: 'clr', sp: 'spr', brp: 'brr', tmp: 'tmr', ff: 'ffr' } as const;
type PKey = keyof typeof CUSTOM;
const DEFAULT: Record<PKey, string> = { cl: '1D', sp: '60D', brp: '120D', tmp: '1D', ff: '1D' };
/* 3e, the example mode (user 2026-11-21; ERRORS M527): the time controls are the choices whose every value is a period
   (1D, 60D, 1Y, YTD, Custom...), derived from ONE_OF: cl, per, sp, brp, tmp, ff; the map's measure and the EMA are not */
const TIME_KEYS = new Set(Object.keys(ONE_OF).filter(k => ONE_OF[k].every(v => /^(\d+[DMY]|YTD|C)$/.test(v))));

export function start(api: OverviewApi, view: HTMLElement, opts: { example?: boolean } = {}) {
  const files = cached(api);
  let index: OverviewIndex, meta: Meta, series: Series, day: Day, R: M.Row[] = [], U: M.Universe[] = [], end = -1;
  const q = new URLSearchParams(location.hash.slice(1));
  // 3e, the example mode: every time control opens on its default whatever the address says (the files hold no other)
  const pick = (k: string, dflt: string) => (opts.example && TIME_KEYS.has(k) ? dflt
    : ONE_OF[k].includes(q.get(k) || '') ? (q.get(k) as string) : dflt);
  const range = (k: string): M.Range | null => { const m = /^(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})$/.exec(q.get(k) || ''); return m ? { a: m[1], b: m[2] } : null };
  const ST: State = {
    u: q.get('u') || '', mm: pick('mm', 'perf') as M.MapMetric, cl: pick('cl', '1D') as M.TilePeriod, per: pick('per', '1D') as M.IhsgPeriod,
    sp: pick('sp', '60D') as SectorP, brk: pick('brk', 'EMA50') as Ema, brp: pick('brp', '120D') as Window,
    tmp: pick('tmp', '1D') as M.TilePeriod, ff: pick('ff', '1D') as M.FlowPeriod, date: '', sel: null, open: false,
    clr: range('clr'), spr: range('spr'), brr: range('brr'), tmr: range('tmr'), ffr: range('ffr'),
  };
  for (const k of Object.keys(CUSTOM) as PKey[]) if ((ST as any)[k] === 'C' && !(ST as any)[CUSTOM[k]]) (ST as any)[k] = DEFAULT[k];
  const persist = () => {
    const p = new URLSearchParams();
    for (const k of ['u', 'mm', 'cl', 'per', 'sp', 'brk', 'brp', 'tmp', 'ff'] as const) p.set(k, ST[k]);
    for (const k of Object.keys(CUSTOM) as PKey[]) { const r = (ST as any)[CUSTOM[k]] as M.Range | null; if ((ST as any)[k] === 'C' && r) p.set(CUSTOM[k], `${r.a}_${r.b}`) }
    history.replaceState(null, '', '#' + p.toString());
  };
  const pl = (p: string) => (p === 'C' ? 'Custom' : p);     // a period's name in a label
  /* 3e, the example mode (the user, 2026-11-21: "semuanya clickable ... kalau user klik 5D, 1M, atau custom, ataupun
     filter yang sifatnya adalah time frame, baru diarahkan ke paywall. atau diarahkan ke login"): a control of a time
     choice (a group whose key is in TIME_KEYS: its data-k, or the key bind() registers for its id) and the date picker
     ask for the shell's box; the index and group filter, the map's measure, the EMA and a stock (to the Terminal) work */
  const groupKey = new Map<string, string>();
  const timeControl = (el: Element) => {
    if (el.closest('#datebtn, #datepop')) return true;
    const g = el.closest('.seg') as HTMLElement | null, k = g ? g.dataset.k || groupKey.get(g.id) : undefined;
    return !!k && TIME_KEYS.has(k);
  };
  if (opts.example) lockOnly({ source: 'overview', name: 'Market Overview', locked: timeControl });

  let toastT = 0;
  const toast = (m: string) => { const t = $('#toast'); t.textContent = m; t.hidden = false; clearTimeout(toastT); toastT = window.setTimeout(() => (t.hidden = true), 3200) };

  const get = async <T>(name: string, again = true): Promise<T> => {
    const e = index.files[name];
    try {
      if (!e) throw new OverviewError('OVERVIEW_FILE_NOT_PUBLISHED', `The market overview file ${name} is not published. Reload the page.`, 404);
      return await files.file<T>(name, e.sha256);
    } catch (err) {
      // a newer publication replaced the file (409) or dropped the date (404): read the index again once (the Radar's
      // way), and with it the meta and series of that publication, so a day file never meets another publication's
      // stock positions or flow dates (review 2026-11-15, finding 3)
      if (again && err instanceof OverviewError && (err.status === 409 || err.status === 404)) {
        await reindex();
        return get<T>(name, false);
      }
      throw err;
    }
  };
  async function reindex() {
    const was = index;
    index = await files.index();
    const sha = (i: OverviewIndex | undefined, n: string) => i?.files?.[n]?.sha256;
    if (meta && series && (sha(was, 'overview-meta') !== sha(index, 'overview-meta') || sha(was, 'overview-series') !== sha(index, 'overview-series'))) {
      [meta, series] = await Promise.all([files.file<Meta>('overview-meta', sha(index, 'overview-meta') as string),
                                          files.file<Series>('overview-series', sha(index, 'overview-series') as string)]);
      U = M.universes(meta);
      if (!U.some(u => u.key === ST.u)) ST.u = M.defaultUniverse(meta);
    }
    if (sha(was, 'overview-stocks') !== sha(index, 'overview-stocks')) stocks = null;
  }
  /* F1: overview-stocks (about 1 MB) is read only when a panel shows a Custom range; until it is in, the panel says so */
  let stocks: StocksFile | null = null, stocksLoading: Promise<void> | null = null;
  function ensureStocks(after: () => void) {
    if (!stocksLoading) {
      stocksLoading = get<StocksFile>('overview-stocks').then(d => { stocks = d }).catch(() => {
        toast('The daily history for Custom periods could not be read. Try again in a minute.');
      }).finally(() => { stocksLoading = null });
    }
    void stocksLoading?.then(after);
  }
  const waiting = '<div class="cv-empty">Loading the daily history of every stock…</div>';
  /** the rows of a period: the day file's for a fixed period, the history's for a Custom range (null while it loads) */
  const rowsFor = (p: string, r: M.Range | null, after: () => void): M.Row[] | null => {
    if (p !== 'C' || !r) return R;
    if (!stocks) { ensureStocks(after); return null }
    return M.customRows(R, stocks, r);
  };
  const dayDates = () => meta.dates.filter(d => index.files[`overview-day-${d}`]);
  const uni = () => U.find(u => u.key === ST.u) || U[0];
  const inUni = () => R.filter(M.inUniverse(uni()));
  const mk = () => meta.market, bench = () => meta.benchmark;
  const marketDate = () => day.market?.date || null;
  const lagging = () => !!day.market && day.market.date !== day.date;

  /* ===================== head: data dates and the date picker ===================== */
  function renderHead() {
    const md = marketDate();
    $('#pills').innerHTML =
      `<span class="pill pos" title="Daily closes and every price figure"><span class="dot"></span>Prices to ${esc(M.dateLabel(day.date, true))}</span>` +
      `<span class="pill ${lagging() || !md ? 'warn' : 'pos'}" title="Turnover and foreign flow (broker summary, Regular board)"><span class="dot"></span>` +
      (md ? `Broker data to ${esc(M.dateLabel(md, true))}` : 'No broker data yet') + '</span>';
    $('#dlab').textContent = M.dateLabel(day.date, true) + DOT + 'Close';
  }
  function dateMenu(open: boolean) {
    const pop = $('#datepop'), btn = $('#datebtn');
    pop.hidden = !open; btn.setAttribute('aria-expanded', String(open));
    if (!open) return;
    const ds = dayDates().slice().reverse();
    pop.innerHTML = '<div class="menu-title">Data as of</div>' + ds.map(d => `<button class="menu-item${d === ST.date ? ' on' : ''}" data-d="${d}"><span class="l"><svg class="ic ic-sm ck">${d === ST.date ? '<use href="#i-check"/>' : ''}</svg>${esc(M.dateLabel(d, true))}</span><span class="n">Close</span></button>`).join('');
    placeMenu(pop, btn);
  }
  /* QA 2026-11-15 (class A): a menu is placed from its measured size: right-aligned to its button unless that leaves the
     screen (a phone: the date menu started at x = -43 px), and never taller than the room below it (it scrolls) */
  function placeMenu(pop: HTMLElement, anchor: HTMLElement) {
    pop.style.left = pop.style.right = pop.style.maxHeight = '';
    const a = anchor.getBoundingClientRect(), G = 8;
    if (a.right - pop.offsetWidth < G) { pop.style.right = 'auto'; pop.style.left = '0' }
    pop.style.maxHeight = Math.max(160, innerHeight - a.bottom - 6 - G) + 'px';
  }
  async function pickDate(d: string) {
    if (d === ST.date) return;
    const btn = $('#datebtn');
    btn.setAttribute('aria-busy', 'true');
    try { day = await get<Day>(`overview-day-${d}`); ST.date = d; ST.sel = null; renderAll() }
    catch (e) { toast(e instanceof OverviewError ? e.message : 'That date could not be read. Try again.') }
    finally { btn.removeAttribute('aria-busy') }
  }

  /* ===================== KPI strip ===================== */
  const TIPS: Record<string, [string, [string, string, string][]]> = {};
  function spark(vals: (number | null)[], color: string) {
    const v = vals.filter((x): x is number => x != null);
    if (v.length < 2) return '';
    const mn = Math.min(...v), mx = Math.max(...v), w = 64, h = 26;
    const d = v.map((x, i) => `${(i * w / (v.length - 1)).toFixed(1)},${(h - 2 - ((x - mn) / ((mx - mn) || 1)) * (h - 4)).toFixed(1)}`).join(' ');
    return `<polyline points="${d}" fill="none" style="stroke:${color}" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/>`;
  }
  const last30 = (a: (number | null)[], e: number) => (e < 0 ? [] : a.slice(Math.max(0, e - 29), e + 1));
  function indexCard(key: string, ticker: string, sub: string) {
    const o = day.index[ticker], c = o?.close ?? null, pc = o?.prior_close ?? null;
    const d = c != null && pc != null ? c - pc : null, dp = d != null && pc ? (d / pc) * 100 : null;
    const sp = last30(series.index[ticker] || [], end);
    const up = (sp[sp.length - 1] ?? 0) >= (sp.find(x => x != null) ?? 0);
    TIPS[key] = [`${ticker}${DOT}1D`, [['Prior close', pc == null ? '—' : M.num(pc), ''],
      ['Change', d == null ? '—' : `${M.sign(d)}${M.num(Math.abs(d))} (${M.pct(dp)})`, M.cls(d)],
      ['Day range', o?.low != null && o?.high != null ? `${M.num(o.low)}–${M.num(o.high)}` : '—', '']]];
    return `<div class="card k" data-k="${key}" tabindex="0" aria-describedby="ktt"><div class="lb"><span class="lt">${esc(ticker)}<span class="tf">1D</span></span></div><div class="ksub">${sub}</div><div><div class="v">${c == null ? '—' : M.num(c)}</div><div class="s"><b class="${M.cls(d)}">${d == null ? 'No prior close' : `${M.sign(d)}${M.num(Math.abs(d))}${DOT}${M.pct(dp)}`}</b></div></div><svg class="sp" width="64" height="26" aria-hidden="true">${spark(sp, up ? 'var(--up)' : 'var(--down)')}</svg></div>`;
  }
  function renderKpis() {
    const b = day.breadth, m = day.market, md = marketDate(), fe = M.flowEnd(series, md);
    const ad = b.decliners ? b.advancers / b.decliners : null;
    TIPS.br = [`Breadth${DOT}1D`, [['Advancers', String(b.advancers), 'up'], ['Decliners', String(b.decliners), 'down'], ['Unchanged', String(b.unchanged), ''], ['A/D', ad == null ? '—' : ad.toFixed(2) + '×', '']]];
    const brokerRow: [string, string, string] = ['Broker date', md ? M.dateLabel(md, true) : '—', ''];
    TIPS.to = [`Turnover${DOT}1D`, [['Value traded', M.rp(m?.turnover), ''], ['20D average', M.rp(m?.turnover_avg20), ''], ['Ratio', m?.turnover_ratio == null ? '—' : m.turnover_ratio.toFixed(2) + '×', ''], brokerRow]];
    TIPS.fn = [`Foreign net${DOT}1D`, [['1D', M.rp(m?.foreign_net_1d, true), M.cls(m?.foreign_net_1d)], ['10D', M.rp(m?.foreign_net_10d, true), M.cls(m?.foreign_net_10d)], brokerRow]];
    const vol = day.volatility, rank = vol.rank_1y == null ? null : Math.round(vol.rank_1y);
    TIPS.vol = [`Volatility${DOT}${vol.window}D`, [['Realized, annualized', vol.value == null ? '—' : vol.value.toFixed(1) + '%', ''], ['Percentile vs own 1Y', rank == null ? '—' : 'P' + rank, '']]];
    const datePill = lagging() && md ? `<span class="pill warn" title="Broker data to ${esc(M.dateLabel(md, true))}">${esc(M.dateLabel(md))}</span>` : '';
    $('#kpis').innerHTML =
      indexCard('ihsg', mk(), 'Composite' + DOT + 'vs prior close') +
      indexCard('lq45', bench(), 'Index' + DOT + 'vs prior close') +
      `<div class="card k" data-k="br" tabindex="0" aria-describedby="ktt"><div class="lb"><span class="lt">Breadth<span class="tf">1D</span></span></div><div class="ksub">Advancers / decliners</div><div><div class="v">${b.advancers} / ${b.decliners}</div><div class="ad"><i style="flex:${b.advancers};background:var(--up)"></i><i style="flex:${b.unchanged};background:var(--gray-300)"></i><i style="flex:${b.decliners};background:var(--down)"></i></div><div class="s">A/D <b>${ad == null ? '—' : ad.toFixed(2) + '×'}</b>${DOT}${b.unchanged} unchanged</div></div></div>` +
      `<div class="card k" data-k="to" tabindex="0" aria-describedby="ktt"><div class="lb"><span class="lt">Turnover<span class="tf">1D</span></span>${datePill}</div><div class="ksub">Value traded${DOT}Regular</div><div><div class="v">${M.rp(m?.turnover)}</div><div class="s">${m?.turnover_ratio == null ? 'No 20D average yet' : `<b>${m.turnover_ratio.toFixed(2)}×</b> 20D average`}</div></div><svg class="sp" width="64" height="26" aria-hidden="true">${spark(last30(series.flow.turnover, fe), 'var(--text-3)')}</svg></div>` +
      `<div class="card k" data-k="fn" tabindex="0" aria-describedby="ktt"><div class="lb"><span class="lt">Foreign net<span class="tf">1D</span></span>${datePill}</div><div class="ksub">Net buy${DOT}Regular</div><div><div class="v ${M.cls(m?.foreign_net_1d)}">${M.rp(m?.foreign_net_1d, true)}</div><div class="s">10D <b class="${M.cls(m?.foreign_net_10d)}">${M.rp(m?.foreign_net_10d, true)}</b></div></div></div>` +
      `<div class="card k" data-k="vol" tabindex="0" aria-describedby="ktt"><div class="lb"><span class="lt">Volatility<span class="tf">${vol.window}D</span></span></div><div class="ksub">Realized${DOT}annualized</div><div><div class="v">${vol.value == null ? '—' : vol.value.toFixed(1) + '%'}</div><div class="s">${rank == null ? 'No 1Y history yet' : `<b>P${rank}</b> vs own 1Y`}</div></div></div>`;
  }
  /* the KPI tooltip (the design's): below the card on hover or focus, above it when it does not fit; Esc or scroll hides it */
  const tt = document.createElement('div');
  tt.className = 'ktt'; tt.id = 'ktt'; tt.setAttribute('role', 'tooltip'); tt.hidden = true; document.body.append(tt);
  const showTip = (k: HTMLElement) => {
    const d = TIPS[k.dataset.k || '']; if (!d) return;
    tt.innerHTML = `<span class="t">${esc(d[0])}</span>` + d[1].map(([a, b, c]) => `<div class="r"><span>${esc(a)}</span><b class="${c}">${esc(b)}</b></div>`).join('');
    tt.hidden = false;
    const r = k.getBoundingClientRect(), w = tt.offsetWidth, h = tt.offsetHeight, G = 8;
    let y = r.bottom + 8; if (y + h > innerHeight - G) y = r.top - h - 8;
    tt.style.left = Math.max(G, Math.min(innerWidth - w - G, r.left)) + 'px'; tt.style.top = Math.max(G, y) + 'px';
  };
  const hideTip = () => (tt.hidden = true);

  /* ===================== market map ===================== */
  const tm = () => $('#tm');
  const seg = (k: keyof State, arr: [string, string][], label: string) => `<div class="seg sm" data-k="${k}" role="group" aria-label="${label}">${arr.map(([v, l]) => `<button type="button" data-v="${v}" class="${ST[k] === v ? 'on' : ''}" aria-pressed="${ST[k] === v}">${l}</button>`).join('')}</div>`;
  function renderMapBar() {
    const u = uni(), n = inUni().filter(r => r.size != null && r.size > 0).length;
    // the foreign figures are of the broker date: named when it lags the price date (QA 2026-11-15)
    const md = marketDate(), fbNote = (ST.cl === 'C' && ST.clr ? `${esc(M.rangeLabel(ST.clr.a, ST.clr.b))}${DOT}` : '')
      + (ST.mm === 'fb' && lagging() && md ? `foreign net to ${esc(M.dateLabel(md))}${DOT}` : '');
    $('#tbar').innerHTML = `<span>Metric</span>${seg('mm', [['perf', 'Performance'], ['fb', 'Foreign buy']], 'Market map metric')}<span class="sp"></span><span class="sum">${fbNote}${n} stocks${DOT}size: <b>${esc(M.sizeLabel(day.size_basis))}</b></span>`;
    $('#tper').innerHTML = `<span>Period</span>${seg('cl', [['1D', '1D'], ['5D', '5D'], ['1M', '1M'], ['C', 'Custom']], 'Market map period')}`;
    $('#univ').innerHTML = `<b>${esc(u.label)}</b><span>${esc(u.kind)}</span>`;
    $('#uni').setAttribute('aria-expanded', String(ST.open));
  }
  function renderTree() {
    const el = tm(), W = el.clientWidth, H = el.clientHeight;
    if (!W || !H) return;
    const all = rowsFor(ST.cl, ST.clr, renderTree);
    if (!all) { el.innerHTML = waiting; return }
    const keep = M.inUniverse(uni()), rows = all.filter(keep);
    // a Custom range's colour scale: its trading days (Performance) or its broker dates (Foreign buy)
    const span = ST.cl === 'C' && ST.clr && stocks
      ? (ST.mm === 'fb' ? stocks.fnet_dates.filter(d => d >= ST.clr!.a && d <= ST.clr!.b).length : M.rangeIn(stocks.dates, ST.clr)?.n) : undefined;
    const groups = M.mapGroups(rows, ST.mm, ST.cl, span);
    if (!groups.length) { el.innerHTML = `<div class="tm-empty">No stock of ${esc(uni().label)} has a size on ${esc(M.dateLabel(day.date))}. Pick another universe.</div>`; return }
    const fb = ST.mm === 'fb', aggTxt = (v: number | null) => (fb ? M.amount(v) : M.pct(v));
    let html = '', onK: M.Rect<M.Tile> | null = null, count = 0;
    tiles.clear();
    // one tab stop for the whole map (QA 2026-11-15: 836 tiles were 836 Tab presses); arrows move between tiles
    const focusT = ST.sel || tileFocus;
    for (const r of M.squarify(groups.map(g => ({ v: g.size, item: g })), 0, 0, W, H)) {
      const g = r.item, hh = r.h > 40 && r.w > 70 ? 17 : 0, name = M.SHORT[g.name] || g.name;
      // the sector's figure has priority over its name; the name ends in "…" when the heading is narrow (QA 2026-11-15)
      if (hh) html += `<div class="sh" style="left:${r.x}px;top:${r.y}px;width:${r.w}px" title="${esc(g.name)}"><span class="shn">${esc(name)}</span>${r.w >= 80 ? `<i class="${M.cls(g.agg)}">${aggTxt(g.agg)}</i>` : ''}</div>`;
      for (const k of M.squarify(g.tiles.map(t => ({ v: t.r.size as number, item: t })), r.x + 1, r.y + hh, r.w - 2, r.h - hh - 1)) {
        const t = k.item, [bg, fg] = t.col, showT = k.w >= 34 && k.h >= 18, showC = k.w >= 46 && k.h >= 34, isOn = t.r.t === ST.sel;
        if (isOn) onK = k;
        tiles.set(t.r.t, t);
        const tab = (focusT ? t.r.t === focusT : count === 0) ? 0 : -1; count++;
        html += `<div class="tile${isOn && !ST.open ? ' on' : ''}" data-t="${esc(t.r.t)}" tabindex="${tab}" role="button" aria-label="${esc(t.r.t)}, ${esc(t.r.name)}, ${esc(t.text)}" style="left:${k.x}px;top:${k.y}px;width:${k.w}px;height:${k.h}px;background:${bg};color:${fg}">${showT ? `<b>${esc(t.r.t)}</b>` : ''}${showC ? `<span>${esc(t.text)}</span>` : ''}${k.h >= 70 && k.w >= 90 ? `<span style="display:block;opacity:.8">${esc(M.sizeText(day.size_basis, t.r.size))}</span>` : ''}</div>`;
      }
    }
    if (onK && !ST.open) {
      const r = onK.item.r, p = ST.cl, rv = r.ret[p] ?? null, fv = r.fnet[p] ?? null, md = marketDate(), lag = lagging() && !!md;
      html += `<div class="pop" role="dialog" aria-label="${esc(r.t)}">
        <div class="ph"><b>${esc(r.t)}</b><span class="muted" title="${esc(M.sizeLabel(day.size_basis))}">${esc(M.sizeText(day.size_basis, r.size))}</span></div>
        <div class="kv"><span>Return (${pl(p)})</span><b class="${M.cls(rv)}">${M.pct(rv)}</b></div>
        <div class="kv"><span title="Regular board">Foreign net (${pl(p)})</span><b class="${M.cls(fv)}">${M.rp(fv, true)}</b></div>${lag ? `
        <div class="pnote">Foreign net uses broker data to ${esc(M.dateLabel(md, true))}</div>` : ''}
        <div class="btns"><button class="btn sm primary" data-act="term">Open in Terminal</button></div></div>`;
    }
    el.innerHTML = html;
    el.setAttribute('role', 'group');
    el.setAttribute('aria-label', `Market map, ${count} stocks of ${uni().label}. Arrow keys move between tiles; Enter opens one.`);
    const pop = el.querySelector('.pop') as HTMLElement | null;
    if (pop && onK) placePop(pop, onK, W, H);
  }
  /* QA 2026-11-15 (class A, "kepotong"): the popover is placed from its measured size: below the tile's label, above the
     tile when it does not fit below, always inside the map (which clips) */
  function placePop(pop: HTMLElement, k: M.Rect<M.Tile>, W: number, H: number) {
    const pw = pop.offsetWidth, ph = pop.offsetHeight, G = 4;
    let top = k.y + Math.min(30, k.h);
    if (top + ph > H - G) top = k.y - ph - G;
    pop.style.left = Math.max(G, Math.min(k.x + Math.min(54, k.w / 2), W - pw - G)) + 'px';
    pop.style.top = Math.max(G, Math.min(top, H - ph - G)) + 'px';
  }
  /* P4 (user 2026-11-15: "tambah hoverstate ... untuk kotak yang tickernya tidak ter-detect"): a mouse over a tile shows
     its ticker, name, both figures of the period and its size */
  const tiles = new Map<string, M.Tile>();
  let tileFocus: string | null = null;
  const tileTip = document.createElement('div');
  tileTip.className = 'ktt ttip'; tileTip.setAttribute('role', 'tooltip'); tileTip.hidden = true; document.body.append(tileTip);
  const hideTileTip = () => (tileTip.hidden = true);
  function showTileTip(t: string, x: number, y: number) {
    const k = tiles.get(t); if (!k || t === ST.sel) return hideTileTip();
    const r = k.r, p = ST.cl, md = marketDate();
    tileTip.innerHTML = `<span class="t">${esc(r.t)}${DOT}${esc(r.name)}</span>`
      + `<div class="r"><span>Return (${pl(p)})</span><b class="${M.cls(r.ret[p])}">${M.pct(r.ret[p])}</b></div>`
      + `<div class="r"><span>Foreign net (${pl(p)}${lagging() && md ? ', ' + esc(M.dateLabel(md)) : ''})</span><b class="${M.cls(r.fnet[p])}">${M.rp(r.fnet[p], true)}</b></div>`
      + `<div class="r"><span>Size</span><b>${esc(M.sizeText(day.size_basis, r.size))}</b></div>`;
    tileTip.hidden = false;
    const w = tileTip.offsetWidth, h = tileTip.offsetHeight, G = 8;
    tileTip.style.left = Math.max(G, Math.min(innerWidth - w - G, x + 14)) + 'px';
    tileTip.style.top = Math.max(G, y + 18 + h > innerHeight - G ? y - h - 12 : y + 18) + 'px';
  }
  function uniMenu() {
    const box = $('#unipop');
    if (!ST.open) { box.innerHTML = ''; return }
    const have = new Set(R.map(r => r.t));
    const item = (u: M.Universe) => {
      const n = u.members ? [...u.members].filter(t => have.has(t)).length : have.size;
      return `<button class="menu-item ${u.key === ST.u ? 'on' : ''}" data-u="${esc(u.key)}"><span class="l"><svg class="ic ic-sm ck">${u.key === ST.u ? '<use href="#i-check"/>' : ''}</svg>${esc(u.label)}</span><span class="n">${n} stocks</span></button>`;
    };
    // P2 (user 2026-11-15): the list scrolls inside the menu; the search field stays on top
    box.innerHTML = `<div class="unipop"><input class="inp sm" type="text" placeholder="Search index or group" aria-label="Search index or group" value="">
      <div class="unilist"><div class="menu-title">Market</div>${U.filter(u => u.kind === 'Market').map(item).join('')}
      <div class="menu-title">Index</div>${U.filter(u => u.kind === 'Index').map(item).join('')}
      <div class="menu-title">Group</div>${U.filter(u => u.kind === 'Group').map(item).join('')}</div></div>`;
    const inp = $<HTMLInputElement>('input', box), items = $$('.menu-item', box), titles = $$('.menu-title', box);
    inp.oninput = () => {
      const v = inp.value.toLowerCase();
      items.forEach(b => (b.style.display = b.textContent!.toLowerCase().includes(v) ? '' : 'none'));
      titles.forEach(t => {                          // a section without a match hides its title
        let n = t.nextElementSibling as HTMLElement | null, any = false;
        while (n && !n.classList.contains('menu-title')) { if (n.style.display !== 'none') any = true; n = n.nextElementSibling as HTMLElement | null }
        t.style.display = any ? '' : 'none';
      });
    };
    // a touch screen does not get the field focused (its keyboard would cover the list, QA 2026-11-15)
    if (!matchMedia('(pointer: coarse)').matches) inp.focus();
  }
  function setUniMenu(open: boolean) { ST.open = open; if (open) ST.sel = null; renderMapBar(); uniMenu(); renderTree() }

  /* ===================== the IHSG chart (the design's: line, light area, prior close dashed, price axis right) ===================== */
  const f0 = (v: number, d = 0) => v.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
  const niceStep = (x: number) => { const e = Math.pow(10, Math.floor(Math.log10(x))), m = x / e; return (m <= 1 ? 1 : m <= 2 ? 2 : m <= 5 ? 5 : 10) * e };
  const axisText = (x: number, y: number, t: string) => `<text x="${x.toFixed(1)}" y="${y.toFixed(1)}" font-size="10.5" fill="var(--text-3)">${t}</text>`;
  let ih: M.IhsgChart | null = null, ihGeo: { X: (i: number) => number; Y: (v: number) => number; t: number; H: number; W: number } | null = null, ihSize = '';
  function drawIhsg(force = false) {
    const el = $('#ihc'), w = el.clientWidth, h = el.clientHeight, svg = el.querySelector('svg') as SVGSVGElement;
    if (!w || !h || !ih) return;
    if (!force && ihSize === `${w}x${h}`) return;
    ihSize = `${w}x${h}`;
    svg.setAttribute('viewBox', `0 0 ${w} ${h}`);
    hideIh();
    const s = ih, rr = 46, t = 8, b = 8, W = w - rr, H = h - t - b;
    if (s.pts.length < 2) { svg.innerHTML = ''; ihGeo = null; el.dataset.empty = s.daily ? 'No closes for this period.' : 'No intraday bars for this session.'; return }
    delete el.dataset.empty;
    // the prior close is inside the range on a day that trades wholly below it too (review 2026-11-15, finding 4)
    const v = s.pts.map(p => p.v), withRef = [...v, ...(s.prior && s.ref != null ? [s.ref] : [])];
    const lo0 = Math.min(...withRef), hi = Math.max(...withRef), lo = lo0 - (hi - lo0) * 0.12;
    const n = s.pts.length - 1, X = (i: number) => (i / n) * W, Y = (y: number) => t + (hi - y) / ((hi - lo) || 1) * H;
    let o = '';
    const step = niceStep((hi - lo) / 4 || 1), dp = step < 1 ? 1 : 0;
    for (let y = Math.ceil(lo / step) * step; y <= hi; y += step) o += axisText(W + 8, Y(y) + 3.5, f0(y, dp));
    if (s.prior && s.ref != null) o += `<line x1="0" x2="${W}" y1="${Y(s.ref).toFixed(1)}" y2="${Y(s.ref).toFixed(1)}" stroke="var(--border-2)" stroke-dasharray="3 3"/>`;
    const pts = s.pts.map((p, i) => `${X(i).toFixed(1)},${Y(p.v).toFixed(1)}`);
    o += `<polygon points="0,${t + H} ${pts.join(' ')} ${X(n).toFixed(1)},${t + H}" fill="var(--text)" fill-opacity=".05"/>`;
    o += `<polyline points="${pts.join(' ')}" fill="none" stroke="var(--text-2)" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/>`;
    svg.innerHTML = o;
    ihGeo = { X, Y, t, H, W };
  }
  const hideIh = () => { const el = $('#ihc'); ($('.xh', el)).hidden = ($('.xd', el)).hidden = ($('.tip', el)).hidden = true };
  function moveIh(e: PointerEvent | MouseEvent) {
    const el = $('#ihc'); if (!ihGeo || !ih) return;
    const r = el.getBoundingClientRect(), mx = e.clientX - r.left, g = ihGeo, pts = ih.pts, n = pts.length - 1;
    if (mx < 0 || mx > g.X(n) + 10) return hideIh();
    const i = Math.max(0, Math.min(n, Math.round((mx / g.W) * n))), p = pts[i], px = g.X(i), py = g.Y(p.v), ref = ih.ref ?? pts[0].v, d = p.v - ref;
    const xh = $('.xh', el), xd = $('.xd', el), tip = $('.tip', el);
    xh.style.cssText = `left:${px}px;top:${g.t}px;height:${g.H}px`; xh.hidden = false;
    xd.style.cssText = `left:${px}px;top:${py}px`; xd.hidden = false;
    tip.innerHTML = `<span class="muted">${esc(p.tip)}</span><b>${f0(p.v, 2)}</b> <span class="${M.cls(d)}">${M.sign(d)}${f0(Math.abs(d), 2)} (${M.pct((d / ref) * 100)})</span>`;
    tip.hidden = false;
    const w = el.clientWidth, h = el.clientHeight, tw = tip.offsetWidth, th = tip.offsetHeight;
    tip.style.left = Math.max(0, Math.min(w - tw, px > w / 2 ? px - tw - 12 : px + 12)) + 'px';
    tip.style.top = Math.max(0, Math.min(h - th, py - th - 10)) + 'px';
  }
  function renderIhsg() {
    ih = M.ihsgChart(series, day, mk(), end, ST.per);
    $('#ihname').textContent = mk();
    $('#ihsub').textContent = ih.sub;
    const v = ih.pts.map(p => p.v), o = day.index[mk()];
    const cells: [string, number | null | undefined][] = ST.per === '1D'
      ? [['Open', o?.open], ['High', o?.high], ['Low', o?.low], ['Close', o?.close]]
      // QA 2026-11-15: a multi-day period shows closes (5D: hourly closes), so its labels say so; Start is the close
      // the change is measured from
      : [['Start', ih.ref], ['High close', v.length ? Math.max(...v) : null], ['Low close', v.length ? Math.min(...v) : null], ['Last', v[v.length - 1]]];
    $('#ohlc').innerHTML = cells.map(([k, x]) => `<span>${k}<b>${x == null ? '—' : f0(x, 2)}</b></span>`).join('');
    const lastV = ST.per === '1D' ? o?.close ?? v[v.length - 1] : v[v.length - 1], ref = ih.ref, d = lastV != null && ref != null ? lastV - ref : null;
    $('#ihq').innerHTML = lastV == null ? '' : `<b>${f0(lastV, 2)}</b>${d == null ? '' : `<span class="pill ${d > 0 ? 'pos' : d < 0 ? 'neg' : ''}">${M.sign(d)}${f0(Math.abs(d), 2)}${DOT}${M.pct((d / (ref as number)) * 100)}</span>`}`;
    // always 1D whatever the chart's period; the broker date when it lags the price date (QA 2026-11-15)
    const m = day.market, md = marketDate(), at = lagging() && md ? `, ${esc(M.dateLabel(md))}` : '';
    $('#ihk').innerHTML = `<div class="kpi"><span>Advancers / decliners (1D)</span><b>${day.breadth.advancers} / ${day.breadth.decliners}</b></div><div class="kpi"><span>Turnover (1D${at})</span><b>${M.rp(m?.turnover)}</b></div><div class="kpi"><span>Foreign net (1D${at})</span><b class="${M.cls(m?.foreign_net_1d)}">${M.rp(m?.foreign_net_1d, true)}</b></div>`;
    $('#ihc').setAttribute('aria-label', `${mk()} ${ih.sub.toLowerCase()}: ` + (lastV != null && ref != null
      ? `${f0(lastV, 2)}, ${M.sign(lastV - ref)}${f0(Math.abs(lastV - ref), 2)} (${M.pct(((lastV - ref) / ref) * 100)}) from ${f0(ref, 2)}` : 'no data'));
    $$('#ihp button').forEach(x => { const on = x.dataset.v === ST.per; x.classList.toggle('on', on); x.setAttribute('aria-pressed', String(on)) });
    drawIhsg(true);
  }

  /* ===================== the line chart of Sector Performance and % Above EMA (the design's engine) ===================== */
  const ctx = document.createElement('canvas').getContext('2d');
  const tw = (t: string, f = '600 10.5px Inter, sans-serif') => { if (!ctx) return t.length * 6; ctx.font = f; return ctx.measureText(t).width };
  const ticksOf = (lo: number, hi: number, n = 4) => { const raw = (hi - lo) / n || 1, p = 10 ** Math.floor(Math.log10(raw)), st = [1, 2, 2.5, 5, 10].map(m => m * p).find(m => m >= raw) as number; const t: number[] = []; for (let v = Math.ceil(lo / st) * st; v <= hi + 1e-9; v += st) t.push(+v.toFixed(6)); return t };
  interface Line { n: string; a: (number | null)[]; c: string; w?: number; z?: number; dash?: boolean; tip?: boolean; tn?: string }
  interface LineCfg { label?: string; dates: string[]; series: Line[]; base?: number; range?: [number, number]; ticks?: number[]; fy?: (v: number) => string; ft?: (v: number) => string; bands?: { lo: (number | null)[]; hi: (number | null)[]; fill: string }[] }
  function lineChart(el: HTMLElement, cfg: LineCfg) {
    const W = el.clientWidth, H = el.clientHeight;
    if (!W || !H) return;
    const n = cfg.dates.length - 1, ser = cfg.series, base = cfg.base ?? 0;
    if (n < 1) { el.innerHTML = '<div class="cv-empty">Not enough sessions for this period.</div>'; return }
    const vals = ser.flatMap(s => s.a).concat((cfg.bands || []).flatMap(b => [...b.lo, ...b.hi])).filter((v): v is number => v != null);
    let lo = Math.min(base, ...vals), hi = Math.max(base, ...vals);
    const pd = (hi - lo) * 0.06 || 1; lo -= pd; hi += pd;
    if (cfg.range) [lo, hi] = cfg.range;
    const ticks = cfg.ticks || ticksOf(lo, hi, 4), fy = cfg.fy || ((v: number) => M.sign(v) + Math.abs(+v.toFixed(1)) + '%');
    const L = Math.max(...ticks.map(t => tw(fy(t), '400 10.5px Inter, sans-serif'))) + 11, T = 6, B = 18, R = W - 4;
    const X = (i: number) => L + (i / n) * (R - L), Y = (v: number) => T + (1 - (v - lo) / (hi - lo)) * (H - T - B);
    let o = ticks.map(t => `<line x1="${L}" x2="${R}" y1="${Y(t)}" y2="${Y(t)}" stroke="${Math.abs(t - base) < 1e-9 ? 'var(--ov-base)' : 'var(--ov-grid)'}"/><text x="${L - 6}" y="${Y(t) + 3.5}" text-anchor="end" class="ax">${fy(t)}</text>`).join('');
    const XF = R - L < 170 ? [0, 1] : R - L < 260 ? [0, 0.5, 1] : [0, 1 / 3, 2 / 3, 1];
    const yAxis = cfg.dates[0].slice(0, 4) !== cfg.dates[n].slice(0, 4);     // a range across years names the first year
    XF.forEach((f, k) => { const i = Math.round(f * n); o += `<text x="${X(i)}" y="${H - 4}" text-anchor="${k === 0 ? 'start' : k === XF.length - 1 ? 'end' : 'middle'}" class="ax">${M.dateLabel(cfg.dates[i], false, yAxis && k === 0)}</text>` });
    const P = (a: (number | null)[]) => { let d = '', pen = false; a.forEach((v, i) => { if (v == null) { pen = false; return } d += (pen ? 'L' : 'M') + X(i).toFixed(1) + ' ' + Y(v).toFixed(1); pen = true }); return d };
    (cfg.bands || []).forEach(b => {
      const hiP = b.hi.map((v, i) => [i, v] as const).filter(([, v]) => v != null), loP = b.lo.map((v, i) => [i, v] as const).filter(([, v]) => v != null).reverse();
      if (hiP.length && loP.length) o += `<path d="${hiP.map(([i, v], k) => (k ? 'L' : 'M') + X(i).toFixed(1) + ' ' + Y(v as number).toFixed(1)).join('')}${loP.map(([i, v]) => 'L' + X(i).toFixed(1) + ' ' + Y(v as number).toFixed(1)).join('')}Z" fill="${b.fill}"/>`;
    });
    [...ser].sort((a, b) => (a.z || 0) - (b.z || 0)).forEach(s => (o += `<path d="${P(s.a)}" fill="none" stroke="${s.c}" stroke-width="${s.w || 1.6}" ${s.dash ? 'stroke-dasharray="4 3"' : ''} stroke-linejoin="round"/>`));
    el.innerHTML = `<svg aria-hidden="true">${o}</svg><i class="xh" hidden></i><div class="tip" hidden></div>`;
    if (cfg.label) { el.setAttribute('role', 'img'); el.setAttribute('aria-label', cfg.label) }
    const xh = $('.xh', el), tip = $('.tip', el), ft = cfg.ft || ((v: number) => M.pct(v, 1));
    const yr = cfg.dates[0].slice(0, 4) !== cfg.dates[n].slice(0, 4);
    el.onpointerleave = e => { if (e.pointerType === 'mouse') xh.hidden = tip.hidden = true };
    el.onpointerdown = el.onpointermove = e => {
      const r = el.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top;
      if (mx < L || mx > R) { xh.hidden = tip.hidden = true; return }
      const i = Math.max(0, Math.min(n, Math.round(((mx - L) / (R - L)) * n)));
      xh.style.cssText = `left:${X(i)}px;top:${T}px;height:${H - T - B}px`; xh.hidden = false;
      const rows = ser.filter(s => s.tip).map(s => ({ n: s.tn || s.n, c: s.c, v: s.a[i] })).filter(x => x.v != null).sort((a, b) => (b.v as number) - (a.v as number));
      tip.innerHTML = `<span class="d">${esc(M.dateLabel(cfg.dates[i], true, yr))}${DOT}day ${i} of ${n}</span>` + rows.map(x => `<div class="r"><i style="background:${x.c}"></i><span>${esc(x.n)}</span><b class="${(x.v as number) >= base ? 'up' : 'down'}">${ft(x.v as number)}</b></div>`).join('');
      tip.hidden = false;
      const tw2 = tip.offsetWidth, th = tip.offsetHeight;
      tip.style.left = Math.max(0, Math.min(W - tw2, mx > W / 2 ? mx - tw2 - 12 : mx + 12)) + 'px';
      tip.style.top = Math.max(0, Math.min(H - th, my - th / 2)) + 'px';
    };
  }

  /* ===================== Sector Performance: cumulative return of the 11 IDX sector indexes vs IHSG ===================== */
  const PAL = ['var(--green)', 'var(--navy)', 'var(--red)', 'var(--amber)'];
  let hl: string | null = null, drawSectors = () => {};
  function renderSectors() {
    const box = $('#spb');
    const sl = ST.sp === 'C' && ST.spr ? M.sectorLinesRange(series, mk(), ST.spr) : { ...M.sectorLines(series, mk(), end, ST.sp as M.SectorPeriod), end };
    if (!sl) { box.innerHTML = '<div class="cv-empty">No trading day in this Custom range. Pick another.</div>'; return }
    const lines = sl.lines, dates = series.dates.slice(sl.start, sl.end + 1);
    const mx = Math.max(...lines.map(x => Math.abs(x.last ?? 0))) || 1;
    box.innerHTML = `<div class="cb"><div class="cv"></div><div class="bl">${lines.map(x => {
      const v = x.last, w = v == null ? 0 : (Math.abs(v) / mx) * 50;
      return `<div class="r" data-n="${esc(x.name)}"><span title="${esc(x.name)}">${esc(M.SHORT[x.name] || x.name)}</span><div class="tr"><i style="${(v ?? 0) >= 0 ? 'left:50%' : 'right:50%'};width:${w}%;background:${(v ?? 0) >= 0 ? 'var(--up)' : 'var(--down)'}"></i></div><b class="${M.cls(v)}">${M.pct(v, 1)}</b></div>`;
    }).join('')}</div></div><div class="sfoot"><span>${esc(M.rangeLabel(dates[0], dates[dates.length - 1]))}</span><span>Point at a sector to highlight its line</span></div>`;
    $$('.bl .r', box).forEach(row => {
      row.onmouseenter = () => { hl = row.dataset.n || null; row.classList.add('on'); drawSectors() };
      row.onmouseleave = () => { hl = null; row.classList.remove('on'); drawSectors() };
    });
    const known = lines.filter(x => x.last != null), focus = known.length >= 4 ? new Set([known[0].name, known[1].name, known[known.length - 2].name, known[known.length - 1].name]) : new Set(known.map(x => x.name));
    const mkLast = M.lastKnown(sl.market);
    const label = `Sector Performance ${pl(ST.sp)}, ${M.rangeLabel(dates[0], dates[dates.length - 1])}: ` + known.map(x => `${x.name} ${M.pct(x.last, 1)}`).join(', ')
      + `; ${mk()} ${M.pct(mkLast, 1)}`;
    drawSectors = () => {
      const h = hl ? new Set([hl]) : focus; let ci = 0;
      lineChart($('.cv', box), { label, dates, series: [
        ...lines.map(x => (h.has(x.name) ? { n: x.name, a: x.a, c: hl ? 'var(--text)' : PAL[ci++ % PAL.length], w: hl ? 2 : 1.6, z: 3, tip: true } : { n: x.name, a: x.a, c: 'var(--ov-dim)', w: 1, tip: false })),
        { n: mk(), a: sl.market, c: 'var(--text)', dash: true, w: 1.3, z: 2, tip: true }] });
    };
    $$('#spp button').forEach(x => { const on = x.dataset.p === ST.sp; x.classList.toggle('on', on); x.setAttribute('aria-pressed', String(on)) });
    requestAnimationFrame(() => drawSectors());
  }

  /* ===================== % Above EMA: the share of stocks closing above their EMA50 / EMA200 (Feature 04) ===================== */
  let drawBreadth = () => {};
  function renderBreadth() {
    const box = $('#brpb'), all = ST.brk === 'EMA50' ? series.above_ema50 : series.above_ema200;
    const cr = ST.brp === 'C' && ST.brr ? M.rangeIn(series.dates, ST.brr) : null;
    const start = cr ? cr.first : M.periodStart(series.dates, end, WINDOW[ST.brp]), stop = cr ? cr.last : end;
    const a = all.slice(start, stop + 1), dates = series.dates.slice(start, stop + 1);
    const v = all[stop], v5 = stop >= 5 ? all[stop - 5] : null, d = v != null && v5 != null ? v - v5 : null, col = ST.brk === 'EMA200' ? 'var(--text)' : 'var(--navy)';
    box.innerHTML = `<div class="big"><b>${v == null ? '—' : Math.round(v) + '%'}</b><span>above ${ST.brk}${d == null ? '' : `${DOT}<span class="${M.cls(d)}">${M.sign(d)}${Math.abs(d).toFixed(1)} pp</span> vs 5 sessions`}</span></div><div class="cv"></div>`;
    $$('#brpk button').forEach(x => { const on = x.dataset.k === ST.brk; x.classList.toggle('on', on); x.setAttribute('aria-pressed', String(on)) });
    $$('#brpp button').forEach(x => { const on = x.dataset.p === ST.brp; x.classList.toggle('on', on); x.setAttribute('aria-pressed', String(on)) });
    const fl = (x: number) => Array(a.length).fill(x);
    const label = `Stocks above ${ST.brk}, ${M.rangeLabel(dates[0], dates[dates.length - 1])}: ${v == null ? 'no data' : v.toFixed(1) + '%'} on ${M.dateLabel(series.dates[stop])}`
      + (d == null ? '' : `, ${M.sign(d)}${Math.abs(d).toFixed(1)} points against 5 sessions before`);
    drawBreadth = () => lineChart($('.cv', box), { label, dates, range: [0, 100], ticks: [0, 30, 50, 70, 100], base: 50, fy: x => x + '%', ft: x => x.toFixed(1) + '%',
      bands: [{ lo: fl(70), hi: fl(100), fill: 'rgba(8,153,129,.07)' }, { lo: fl(0), hi: fl(30), fill: 'rgba(242,54,69,.07)' }, { lo: fl(0), hi: a, fill: 'rgba(23,52,140,.08)' }],
      series: [{ n: ST.brk, a, c: col, w: 1.8, tip: true }] });
    requestAnimationFrame(() => drawBreadth());
  }

  /* ===================== Top Movers: 5 up and 5 down of the whole market (user 2026-11-15: "treemap itu hanya kalau toggle
     ke LQ45 ... hanya isolated di treemap saja, tidak merubah % Above EMA, Top Movers dll") ===================== */
  function renderMovers() {
    const rows = rowsFor(ST.tmp, ST.tmr, renderMovers);
    $$('#tmvp button').forEach(x => { const on = x.dataset.p === ST.tmp; x.classList.toggle('on', on); x.setAttribute('aria-pressed', String(on)) });
    if (!rows) { $('#tmvb').innerHTML = waiting; return }
    const m = M.movers(rows, ST.tmp), mx = Math.max(...[...m.up, ...m.down].map(r => Math.abs(r.ret[ST.tmp] as number))) || 1;
    const row = (r: M.Row) => { const v = r.ret[ST.tmp] as number; return `<div class="tmv-r" tabindex="0" role="button" data-t="${esc(r.t)}" aria-label="${esc(r.t)}, ${esc(r.name)}, ${M.pct(v)}, open in Terminal" title="${esc(r.t)}${DOT}${esc(r.name)}${DOT}${M.pct(v)}"><span class="tk">${esc(r.t)}</span><div class="tmv-t"><i class="${v >= 0 ? 'pos' : 'neg'}" style="width:${Math.max(1.5, (Math.abs(v) / mx) * 50)}%"></i></div><b class="${v >= 0 ? 'pos' : 'neg'}">${M.pct(v)}</b></div>` };
    $('#tmvb').innerHTML = `<div class="tmv-l"><div class="tmv-g" aria-label="Top gainers">${m.up.map(row).join('') || '<div class="tmv-none">No stock up</div>'}</div><div class="tmv-g" aria-label="Top losers">${m.down.map(row).join('') || '<div class="tmv-none">No stock down</div>'}</div></div><div class="tmv-f"><span>${m.count} stocks${DOT}${m.ups} up / ${m.downs} down</span><span>${ST.tmp === 'C' && ST.tmr ? esc(M.rangeLabel(ST.tmr.a, ST.tmr.b)) : 'All stocks'}</span></div>`;
    $('#tmvs').textContent = 'All stocks' + DOT + 'by return';
    $$('#tmvp button').forEach(x => { const on = x.dataset.p === ST.tmp; x.classList.toggle('on', on); x.setAttribute('aria-pressed', String(on)) });
  }

  /* ===================== Foreign Flow: the market's foreign buying and selling and the largest net buyers and sellers ===================== */
  function renderFlow() {
    const out = $('#ffb'), m = day.market;
    $$('#ffp button').forEach(b => { const on = b.dataset.v === ST.ff; b.classList.toggle('on', on); b.setAttribute('aria-pressed', String(on)) });
    const custom = ST.ff === 'C' && ST.ffr ? M.flowRange(series, ST.ffr) : null;
    const per = ST.ff === 'C' ? custom : m?.periods?.[ST.ff] || null;
    if (!m || !per) { out.innerHTML = `<div class="ff-none">No broker data for ${ST.ff === 'C' && ST.ffr ? esc(M.rangeLabel(ST.ffr.a, ST.ffr.b)) : esc(ST.ff) + ' up to ' + esc(M.dateLabel(day.date))}. It appears after the next broker update.</div>`; return }
    const rows = rowsFor(ST.ff, ST.ffr, renderFlow);
    if (!rows) { out.innerHTML = waiting; return }
    const to = custom ? custom.to : m.date, over = custom && ST.ffr && ST.ffr.b > custom.to;
    const top = M.foreignTop(rows, ST.ff), mx = Math.max(...top.buy.map(r => r.fnet[ST.ff] as number), ...top.sell.map(r => -(r.fnet[ST.ff] as number)), 1);
    const W = (v: number) => Math.max(3, (Math.abs(v) / mx) * 100).toFixed(1) + '%', pb = per.buy + per.sell > 0 ? (per.buy / (per.buy + per.sell)) * 100 : 50;
    const pairs = Array.from({ length: Math.max(top.buy.length, top.sell.length) }, (_, i) => [top.buy[i], top.sell[i]] as const);
    out.innerHTML = `<div class="pd-kpis"><div class="kpi"><span>Foreign buy</span><b>${M.rp(per.buy)}</b></div><div class="kpi"><span>Foreign sell</span><b>${M.rp(per.sell)}</b></div><div class="kpi"><span>Net</span><b class="${M.cls(per.net)}">${M.rp(per.net, true)}</b></div></div>
      <div class="ff-split" role="img" aria-label="Buy ${pb.toFixed(1)}%, sell ${(100 - pb).toFixed(1)}%"><i style="width:${pb}%;background:var(--up)"></i><i style="flex:1;background:var(--down)"></i></div>
      <div class="ff-sl"><span>Buy ${pb.toFixed(1)}%</span><span>Sell ${(100 - pb).toFixed(1)}%</span></div>
      <div class="ff-ch"><span>Net buy</span><span>Net sell</span></div>
      ${pairs.map(([b, s]) => `<div class="ff-r">${b ? `<span class="tk">${esc(b.t)}</span><b class="up">${M.amount(b.fnet[ST.ff])}</b><div class="bar l"><i style="width:${W(b.fnet[ST.ff] as number)}"></i></div>` : '<span class="tk"></span><b></b><div class="bar l"></div>'}${s ? `<div class="bar r"><i style="width:${W(s.fnet[ST.ff] as number)}"></i></div><b class="down s">${M.amount(s.fnet[ST.ff])}</b><span class="tk r">${esc(s.t)}</span>` : '<div class="bar r"></div><b class="down s"></b><span class="tk r"></span>'}</div>`).join('')}
      <div class="ff-f"><span>Regular board${DOT}${esc(M.rangeLabel(per.from, to))}${over ? ' (broker data to ' + esc(M.dateLabel(to)) + ')' : ''}</span><span>Market net <b class="${M.cls(per.net)}">${M.rp(per.net, true)}</b></span></div>`;
  }

  /* ===================== F1: the Custom period popover (one, placed under the Custom button pressed) ===================== */
  const cpop = document.createElement('div');
  cpop.className = 'pop cpop'; cpop.setAttribute('role', 'dialog'); cpop.setAttribute('aria-label', 'Custom period'); cpop.hidden = true;
  document.body.append(cpop);
  let cpopFor: { key: PKey; after: () => void; button: HTMLElement } | null = null;
  const closeCustom = (focus = false) => { cpop.hidden = true; if (focus) cpopFor?.button.focus(); cpopFor = null };
  function openCustom(key: PKey, button: HTMLElement, after: () => void) {
    const dates = series.dates, min = key === 'brp' ? dates[0] : dates[1], max = dates[dates.length - 1];
    const was = (ST as any)[CUSTOM[key]] as M.Range | null, e = M.seriesEnd(series, ST.date);
    const r = was || { a: dates[Math.max(key === 'brp' ? 0 : 1, e - 20)], b: dates[e] };
    cpop.innerHTML = `<div class="ph"><b>Custom period</b></div>
      <div class="cp-f"><label>From<input type="date" id="cpa" min="${min}" max="${max}" value="${r.a}"></label>
      <label>To<input type="date" id="cpb" min="${min}" max="${max}" value="${r.b}"></label></div>
      <div class="cp-n">At most 1 year, from ${esc(M.dateLabel(min, false, true))}. The range runs from its first to its last trading day.</div>
      <div class="cp-err" role="alert" hidden></div>
      <div class="btns"><button type="button" class="btn sm" data-act="cancel">Cancel</button><button type="button" class="btn sm primary" data-act="apply">Apply</button></div>`;
    cpopFor = { key, after, button };
    cpop.hidden = false;
    const b = button.getBoundingClientRect(), w = cpop.offsetWidth, h = cpop.offsetHeight, G = 8;
    cpop.style.left = Math.max(G, Math.min(innerWidth - w - G, b.right - w)) + 'px';
    cpop.style.top = Math.max(G, b.bottom + 6 + h > innerHeight - G ? b.top - h - 6 : b.bottom + 6) + 'px';
    if (!matchMedia('(pointer: coarse)').matches) ($('#cpa', cpop) as HTMLInputElement).focus();
  }
  function applyCustom() {
    if (!cpopFor) return;
    const a = ($('#cpa', cpop) as HTMLInputElement).value, b = ($('#cpb', cpop) as HTMLInputElement).value;
    const dates = series.dates, min = cpopFor.key === 'brp' ? dates[0] : dates[1], max = dates[dates.length - 1];
    const bad = M.rangeProblem({ a, b }, min, max) ?? (M.rangeIn(dates, { a, b }) ? null : 'There is no trading day in this range. Pick another.');
    const err = $('.cp-err', cpop);
    if (bad) { err.textContent = bad; err.hidden = false; return }
    const { key, after } = cpopFor;
    (ST as any)[key] = 'C'; (ST as any)[CUSTOM[key]] = { a, b };
    persist(); closeCustom(true); after();
  }

  /* ===================== the Terminal (as the Radar's: ml.symbol and the shell's edge-nav, ERRORS M425) ===================== */
  function openTerminal(t: string | null) {
    if (t) { try { localStorage.setItem('ml.symbol', t) } catch { /* storage off: the Terminal opens on its own symbol */ } }
    try { parent.postMessage({ type: 'edge-nav', route: 'terminal' }, location.origin) } catch { /* not framed */ }
    if (parent === window) toast(t ? `${t} is set for the Terminal. Open the Terminal page to see it.` : 'Open the Terminal page from the menu.');
  }

  function renderAll() {
    R = M.rows(meta, day);
    end = M.seriesEnd(series, day.date);
    renderHead(); renderKpis(); renderMapBar(); uniMenu(); renderTree(); renderIhsg(); renderSectors(); renderBreadth(); renderMovers(); renderFlow();
    fit();
  }
  /* B2 (user 2026-11-15, zoom 125%: the controls dropped to a second row, right-aligned): derived from what is drawn,
     not from a width table. A card header first hides its "Period"/"EMA" words; if its controls still do not fit beside
     the title they go on their own row under it, left-aligned. The OHLC row turns 2 x 2 when a value is wider than its
     cell (a phone: up to 13 px). */
  function fit() {
    for (const h of $$('.card-h:not(.tmc .card-h)')) {        // the map's header keeps the design's own phone layout
      const seg = h.querySelector('.seg') as HTMLElement | null, first = h.firstElementChild as HTMLElement | null;
      if (!seg || !first) continue;
      h.classList.remove('tight', 'wrapped');
      const bad = () => h.scrollWidth > h.clientWidth + 1 || seg.getBoundingClientRect().top >= first.getBoundingClientRect().bottom - 2;
      if (!bad()) continue;
      h.classList.add('tight');
      if (!bad()) continue;
      // on their own row the controls get their words back when the row holds them on one line
      h.classList.add('wrapped'); h.classList.remove('tight');
      const segs = [...h.querySelectorAll('.seg')].map(x => x.getBoundingClientRect().top);
      if (h.scrollWidth > h.clientWidth + 1 || Math.max(...segs) - Math.min(...segs) > 2) h.classList.add('tight');
    }
    const ohlc = $('#ohlc');
    ohlc.classList.remove('two');
    if ($$('b', ohlc).some(b => b.scrollWidth > b.clientWidth + 1)) ohlc.classList.add('two');
  }

  /* ===================== events (bound once; the containers stay, their content is redrawn) ===================== */
  function bind() {
    const mapAfter = () => { renderMapBar(); renderTree(); fit() };
    const tbarClick = (e: Event) => {
      const b = (e.target as HTMLElement).closest('.seg button') as HTMLElement; if (!b) return;
      const k = (b.parentElement as HTMLElement).dataset.k as keyof State;
      if (b.dataset.v === 'C') { e.stopPropagation(); openCustom('cl', b, mapAfter); return }
      (ST as any)[k] = b.dataset.v; persist(); renderMapBar(); renderTree();
    };
    $('#tbar').addEventListener('click', tbarClick);
    $('#tper').addEventListener('click', tbarClick);
    $('#uni').addEventListener('click', e => { e.stopPropagation(); setUniMenu(!ST.open) });
    $('#unipop').addEventListener('click', e => {
      e.stopPropagation();
      const b = (e.target as HTMLElement).closest('.menu-item') as HTMLElement; if (!b) return;
      ST.u = b.dataset.u || M.ALL; persist(); setUniMenu(false); $('#uni').focus();
    });
    const select = (t: string, kb = false) => {
      ST.sel = ST.sel === t ? null : t; tileFocus = t; hideTileTip(); renderTree();
      // from the keyboard the popover's action takes the focus (QA 2026-11-15); Escape returns to the tile
      if (kb && ST.sel) (tm().querySelector('.pop [data-act=term]') as HTMLElement | null)?.focus({ preventScroll: true });
    };
    tm().addEventListener('click', e => {
      const el = e.target as HTMLElement;
      if (el.closest('.pop [data-act=term]')) { openTerminal(ST.sel); return }
      if (el.closest('.pop')) return;
      const t = el.closest('.tile') as HTMLElement;
      if (t) select(t.dataset.t as string); else if (ST.sel) { ST.sel = null; renderTree() }
    });
    tm().addEventListener('keydown', e => {
      const t = (e.target as HTMLElement).closest('.tile') as HTMLElement; if (!t) return;
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); select(t.dataset.t as string, true); return }
      const all = $$('.tile', tm()), i = all.indexOf(t);
      const to = { ArrowRight: i + 1, ArrowDown: i + 1, ArrowLeft: i - 1, ArrowUp: i - 1, Home: 0, End: all.length - 1 }[e.key];
      if (to == null) return;
      e.preventDefault();
      const next = all[Math.max(0, Math.min(all.length - 1, to))];
      t.tabIndex = -1; next.tabIndex = 0; next.focus({ preventScroll: false }); tileFocus = next.dataset.t || null;
    });
    tm().addEventListener('pointermove', e => {
      if (e.pointerType !== 'mouse') return;
      const t = (e.target as HTMLElement).closest('.tile') as HTMLElement | null;
      if (t && !(e.target as HTMLElement).closest('.pop')) showTileTip(t.dataset.t as string, e.clientX, e.clientY); else hideTileTip();
    });
    tm().addEventListener('pointerleave', hideTileTip);
    $('#tmvb').addEventListener('click', e => { const r = (e.target as HTMLElement).closest('.tmv-r') as HTMLElement; if (r) openTerminal(r.dataset.t as string) });
    $('#tmvb').addEventListener('keydown', e => { const r = (e.target as HTMLElement).closest('.tmv-r') as HTMLElement; if (r && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); openTerminal(r.dataset.t as string) } });
    $('#termbtn').addEventListener('click', () => openTerminal(ST.sel));
    $('#datebtn').addEventListener('click', e => { e.stopPropagation(); dateMenu($('#datepop').hidden) });
    $('#datepop').addEventListener('click', e => {
      const b = (e.target as HTMLElement).closest('.menu-item') as HTMLElement; if (!b) return;
      dateMenu(false); void pickDate(b.dataset.d as string);
    });
    const periodClick = (id: string, k: keyof State, attr: string, after: () => void) => (groupKey.set(id.slice(1), k), $(id)).addEventListener('click', e => {
      const b = (e.target as HTMLElement).closest('button') as HTMLElement; if (!b) return;
      if (b.dataset[attr] === 'C' && k in CUSTOM) { e.stopPropagation(); openCustom(k as PKey, b, after); return }
      (ST as any)[k] = b.dataset[attr]; persist(); after();
    });
    cpop.addEventListener('click', e => {
      const act = (e.target as HTMLElement).closest('[data-act]') as HTMLElement | null;
      if (act?.dataset.act === 'apply') applyCustom(); else if (act?.dataset.act === 'cancel') closeCustom(true);
    });
    cpop.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); applyCustom() } });
    periodClick('#ihp', 'per', 'v', () => { renderIhsg(); fit() });
    periodClick('#spp', 'sp', 'p', renderSectors);
    periodClick('#brpk', 'brk', 'k', renderBreadth);
    periodClick('#brpp', 'brp', 'p', renderBreadth);
    periodClick('#tmvp', 'tmp', 'p', renderMovers);
    periodClick('#ffp', 'ff', 'v', renderFlow);
    const ihc = $('#ihc');
    // pointer events: a mouse moves the crosshair; a finger taps a point or drags sideways along the line (QA 2026-11-15)
    ihc.addEventListener('pointermove', moveIh);
    ihc.addEventListener('pointerdown', moveIh);
    ihc.addEventListener('pointerleave', e => { if (e.pointerType === 'mouse') hideIh() });
    $('#kpis').addEventListener('mouseover', e => { const k = (e.target as HTMLElement).closest('.k[data-k]') as HTMLElement; if (k) showTip(k) });
    $('#kpis').addEventListener('mouseout', e => { const k = (e.target as HTMLElement).closest('.k[data-k]'); if (k && !k.contains(e.relatedTarget as Node)) hideTip() });
    $('#kpis').addEventListener('focusin', e => { const k = (e.target as HTMLElement).closest('.k[data-k]') as HTMLElement; if (k) showTip(k) });
    $('#kpis').addEventListener('focusout', hideTip);
    view.addEventListener('scroll', () => { hideTip(); hideTileTip() }, { passive: true });
    // a tap in the shell around this frame closes this page's menus too (QA 2026-11-15)
    const closeAll = () => { hideTip(); hideTileTip(); closeCustom(); if (!$('#datepop').hidden) dateMenu(false); if (ST.open) setUniMenu(false); if (ST.sel) { ST.sel = null; renderTree() } };
    if (parent !== window) {
      try {
        parent.document.addEventListener('pointerdown', closeAll);
        addEventListener('pagehide', () => { try { parent.document.removeEventListener('pointerdown', closeAll) } catch { /* the shell is gone */ } });
      } catch { /* another origin: nothing to listen to */ }
    }
    document.addEventListener('keydown', e => {
      if (e.key !== 'Escape') return;
      hideTip();
      if (!cpop.hidden) { closeCustom(true); return }
      if (!$('#datepop').hidden) { dateMenu(false); $('#datebtn').focus(); return }
      if (ST.open) { setUniMenu(false); $('#uni').focus(); return }
      if (ST.sel) { const t = ST.sel; ST.sel = null; renderTree(); (tm().querySelector(`.tile[data-t="${CSS.escape(t)}"]`) as HTMLElement | null)?.focus({ preventScroll: true }) }
    });
    document.addEventListener('click', e => {
      if (!cpop.hidden && !cpop.contains(e.target as Node)) closeCustom();
      if (!$('#datepop').hidden && !$('#datepop').contains(e.target as Node)) dateMenu(false);
      if (ST.open && !$('#unipop').contains(e.target as Node)) setUniMenu(false);
      if (ST.sel && !e.composedPath().includes(tm())) { ST.sel = null; renderTree() }   // a click outside the map closes its popover
    });
    // the charts and the map follow their box (every breakpoint); the state stays
    // QA 2026-11-15 (B2): card headers and the OHLC row fit what they hold, measured on every size change
    new ResizeObserver(() => fit()).observe($('#body'));
    let mapSize = '', mapT = 0;
    new ResizeObserver(() => { const el = tm(), k = el.clientWidth + 'x' + el.clientHeight; if (k === mapSize) return; mapSize = k; clearTimeout(mapT); mapT = window.setTimeout(renderTree, 80) }).observe(tm());
    new ResizeObserver(() => drawIhsg(false)).observe(ihc);
    let sk = '', bk = '';
    new ResizeObserver(() => { const b = $('#spb'), k = b.clientWidth + 'x' + b.clientHeight; if (k !== sk) { sk = k; drawSectors() } }).observe($('#spb'));
    new ResizeObserver(() => { const b = $('#brpb'), k = b.clientWidth + 'x' + b.clientHeight; if (k !== bk) { bk = k; drawBreadth() } }).observe($('#brpb'));
  }

  function renderError(e: unknown) {
    const m = e instanceof OverviewError ? e.message : 'The market overview could not be shown. Reload the page; if it stays, the overview is not published yet.';
    $('#body').hidden = true;
    const boot = $('#boot');
    boot.hidden = false;
    boot.innerHTML = `<span class="err" aria-hidden="true">!</span><span>${esc(m)}</span><button class="btn sm" data-act="retry">Try again</button>`;
    ($('[data-act=retry]', boot) as HTMLElement).onclick = () => void boot_();
  }
  let bound = false;
  async function boot_() {
    const boot = $('#boot');
    boot.hidden = false; $('#body').hidden = true;
    boot.innerHTML = '<span class="ml-loading" role="status"><span class="ml-spin" aria-hidden="true"></span>Loading the market overview</span>';
    try {
      index = await files.index();
      [meta, series] = await Promise.all([get<Meta>('overview-meta'), get<Series>('overview-series')]);
      const ds = dayDates();
      if (!ds.length) { boot.innerHTML = '<span>The market overview has no published date yet. It appears after the next price update.</span>'; return }
      ST.date = ds[ds.length - 1];
      day = await get<Day>(`overview-day-${ST.date}`);
    } catch (e) { renderError(e); return }
    U = M.universes(meta);
    if (!U.some(u => u.key === ST.u)) ST.u = M.defaultUniverse(meta);
    persist();
    boot.hidden = true; $('#body').hidden = false;
    if (!bound) { bind(); bound = true }
    renderAll();
    document.body.dataset.ready = '1';
  }
  return { boot: boot_, rerender: () => (day ? renderAll() : undefined) };
}
