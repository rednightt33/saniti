/* EXEC-RADAR R7 (user go 2026-11-14; D7 "bangun dari latest R10"): the Radar page, the R10 design
   (verification/radar/index-r10.html, its script ported here) on the Radar files. Routes: #/radar (board) and
   #/filter/<column>?s=<TICKER> (filter detail). Every number shown is a Feature 07 value or a hit count; the page
   evaluates no rule. Wording is the R10 page's (English, the EDGE sub-apps' language). */
import { cached, RadarError } from './api.ts';
import {
  closesOf, columns, conditions, COND_KEYS, counts, dayLabel, inUniverse, LEVEL_LABEL, levelOf, lists, membersOn,
  metBits, monthOf, runs, stockFacts, type Column, type Row,
} from './model.ts';
import type { Board, Days, FilterFile, FilterMeta, Gate, Meta, RadarApi, RadarIndex } from './types.ts';

const $ = <T extends Element = HTMLElement>(s: string, r: ParentNode = document) => r.querySelector(s) as unknown as T;
const $$ = <T extends Element = HTMLElement>(s: string, r: ParentNode = document) => [...r.querySelectorAll(s)] as unknown as T[];
const esc = (s: unknown) => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const ic = (n: string, c = 'ic ic-sm') => `<svg class="${c}"><use href="#i-${n}"/></svg>`;
const num = (x: number | null, d = 1) => (x == null ? '—' : x.toFixed(d));
const px = (x: number | null) => (x == null ? '—' : Math.round(x).toLocaleString('en-US'));
const sg = (x: number | null, d = 2) => (x == null ? '—' : (x > 0 ? '+' : x < 0 ? '−' : '') + Math.abs(x).toFixed(d) + '%');
const pt = (x: number | null, d = 1) => (x == null ? '—' : (x > 0 ? '+' : x < 0 ? '−' : '') + Math.abs(x).toFixed(d) + ' pt');
const rp = (x: number | null) => (x == null ? '—' : (x > 0 ? '+' : x < 0 ? '−' : '') + 'Rp ' + Math.abs(x / 1e9).toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + 'B');
const plural = (n: number, one: string, many = one + 's') => `${n} ${n === 1 ? one : many}`;
/* an axis of at most `most` round steps between 0 (or lo) and hi */
const niceStep = (span: number, most: number) => { const raw = span / Math.max(1, most), mag = Math.pow(10, Math.floor(Math.log10(raw || 1))); return [1, 2, 2.5, 5, 10].map(n => n * mag).find(x => x >= raw) || mag * 10 };
const pc = (x: number | null) => (x == null ? '—' : 'P' + x.toFixed(x >= 99.95 || x === Math.round(x) ? 0 : 1));
const cl = (x: number | null) => (x == null ? '' : x > 0 ? 'up' : x < 0 ? 'down' : '');

type Facts = ReturnType<typeof stockFacts>;
type Col = [string, (t: string, g: Gate, r?: Row) => string, ((t: string, g: Gate) => string)?];

/* the filters' own columns (RADAR_PAGE_SPEC.md section 5): which Feature 07 measure each shows, formatted */
function ownColumns(column: string, F: Facts): Col[] {
  const m = (t: string, k: string) => F.measure(t, k);
  const g2 = (k: string) => (t: string, g: Gate) => m(t, `${k}_${g}`);
  const f5: Col = ['Foreign 5D', t => rp(m(t, 'foreign_net_5d')), t => cl(m(t, 'foreign_net_5d'))];
  const days: Col = ['Buy days', t => (m(t, 'buy_days_5d') == null ? '—' : `${m(t, 'buy_days_5d')}/5`)];
  switch (column) {
    case 'S1': return [f5, ['of buying', t => num(m(t, 'foreign_ratio_5d')) + '%'], ['vs own 1Y', t => pc(m(t, 'foreign_net_5d_pct252'))],
                       ['z', t => num(m(t, 'foreign_net_5d_z252'), 2)], days];
    case 'S2': return [f5, ['Ratio now', t => num(m(t, 'foreign_ratio_5d')) + '%'], ['5 sessions ago', t => num(m(t, 'foreign_ratio_5d_prev')) + '%'],
                       ['Change', t => pt(m(t, 'foreign_ratio_5d_change'))], ['Rank', (t, g) => pc(g2('s2_rank')(t, g))]];
    case 'S3': return [['Net buyers', t => px(m(t, 's3_net_buyers'))], ['Top 3 − even', t => num(m(t, 's3_cr3_excess'), 3)],
                       ['Group rank', (t, g) => pc(g2('s3_group_rank')(t, g))],
                       ['Intensity', t => (m(t, 's3_intensity') == null ? '—' : (100 * m(t, 's3_intensity')).toFixed(1) + '%')],
                       ['Rank', (t, g) => pc(g2('s3_intensity_rank')(t, g))], f5];
    case 'S6': return [f5, ['Ratio', t => num(m(t, 'foreign_ratio_5d')) + '%'], ['vs own 1Y', t => pc(m(t, 'foreign_ratio_5d_pct252'))], days];
    case 'S6D': return [['Ratio', t => num(m(t, 'foreign_ratio_5d')) + '%'], ['Ratio change', t => pt(m(t, 'foreign_ratio_5d_change'))],
                        ['vs own 1Y', t => pc(m(t, 'foreign_ratio_5d_pct252'))], ['Rank change', t => pt(m(t, 'foreign_ratio_5d_pct252_change'))], f5];
    case 'S7': return [['FL34 before', t => num(m(t, 'fl34_5d_prev'))], ['FL34 now', t => num(m(t, 'fl34_5d'))],
                       ['Change', t => pt(m(t, 'fl34_5d') == null || m(t, 'fl34_5d_prev') == null ? null : m(t, 'fl34_5d') - m(t, 'fl34_5d_prev'))],
                       ['Institutional net', t => rp(m(t, 'inst_net_5d')), t => cl(m(t, 'inst_net_5d'))],
                       ['of buying', t => num(m(t, 'inst_share_5d')) + '%']];
    case 'S8': return [['Foreign 1D', t => rp(m(t, 'foreign_net_1d')), t => cl(m(t, 'foreign_net_1d'))],
                       ['Robust z', t => { const a = [m(t, 'rz_foreign_ratio_1d'), m(t, 'rz_net_vs_adv20')].filter(v => v != null); return a.length ? Math.max(...a).toFixed(1) : '—' }],
                       ['of ADV20', t => num(m(t, 'net_vs_adv20'), 0) + '%'], ['vs own', t => pc(m(t, 'net_1d_pct252'))],
                       ['Level', (_t, _g, r) => (r?.status === 'hit' ? (r.strong ? 'Strong' : 'Watch') : '—')]];
    default: return [];
  }
}

interface State {
  uni: string; gate: Gate; lv: number; show: 'all' | 'new' | 'multi'; q: string; variant: string; last: string; date: string;
  detail: { sort: 'own' | 'new'; prev: '3M' | '6M' | '1Y'; q: string; day: number; col: string };
}

export function start(api: RadarApi, view: HTMLElement) {
  const files = cached(api);
  let index: RadarIndex, meta: Meta, days: Days, board: Board, F: Facts, cols: Column[];
  const fileCache = new Map<string, FilterFile>();
  const ST: State = { uni: 'all', gate: 'broad', lv: 1, show: 'all', q: '', variant: '', last: 'S1', date: '',
                      detail: { sort: 'own', prev: '1Y', q: '', day: 0, col: '' } };
  let toastT = 0;
  const toast = (m: string) => { const t = $('#toast'); t.textContent = m; t.hidden = false; clearTimeout(toastT); toastT = window.setTimeout(() => (t.hidden = true), 3200) };

  const get = async <T>(name: string, again = true): Promise<T> => {
    const e = index.files[name];
    try {
      if (!e) throw new RadarError('RADAR_FILE_NOT_PUBLISHED', `The Radar file ${name} is not published.`, 404);
      return await files.file<T>(name, e.sha256);
    } catch (err) {
      // QA 2026-11-14: a newer publication replaced the file (409) or renamed the dates (404): read the index again once
      if (again && err instanceof RadarError && (err.status === 409 || err.status === 404)) {
        index = await files.index();
        return get<T>(name, false);
      }
      throw err;
    }
  };
  const variantOf = (c: Column) => c.variants.find(v => v.id === ST.variant) || c.variants[0];
  const filterOf = (c: Column) => (c.variants.length > 1 ? variantOf(c) : c.variants[0]);
  const keepUni = (t: string) => inUniverse(meta, ST.uni)(t);
  const dateIndex = () => days.dates.indexOf(ST.date);
  const isDefault = () => ST.uni === 'all' && ST.gate === 'broad' && ST.lv === 1 && ST.show === 'all' && !ST.q;
  const hitSets = () => new Map(cols.map(c => [c.id, new Set(lists(board, filterOf(c), ST.lv, ST.gate).hits.map(h => h.t))] as [string, Set<string>]));
  const alsoIn = (c: Column, t: string, sets = hitSets()) => cols.filter(g => g !== c && sets.get(g.id)?.has(t));
  const uniLabel = () => {
    if (ST.uni === 'all') return ['All stocks', 'Universe'];
    const l = meta.lists.find(x => x.key === ST.uni);
    return l ? [l.name || l.code, l.kind === 'INDEX' ? 'Index' : 'Group'] : ['All stocks', 'Universe'];
  };
  const gateCut = (g: Gate) => { const i = dateIndex(), v = i >= 0 ? days.gate[`${g}_cut`][i] : null; return v == null ? '—' : (v / 1e9).toFixed(2) };

  /* ---------- shared UI (R10) ---------- */
  const sparkBars = (a: number[], w: number, h: number) => {
    const m = Math.max(1, ...a), bw = w / Math.max(1, a.length);
    return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" aria-hidden="true">${a.map((v, i) => { const hh = Math.max(1.5, v / m * (h - 2)); return `<rect x="${i * bw + .5}" y="${h - hh}" width="${Math.max(.5, bw - 1.5)}" height="${hh}" rx="1" fill="${i === a.length - 1 ? 'var(--text)' : 'var(--gray-300)'}"/>` }).join('')}</svg>`;
  };
  const priceSpark = (t: string) => {
    const a = F.spark(t).filter((x): x is number => x != null);
    if (a.length < 2) return '';
    const lo = Math.min(...a), hi = Math.max(...a), up = a[a.length - 1] >= a[0], W = 46, H = 16, n = a.length - 1;
    return `<svg class="ks" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="${t} price, last ${a.length} sessions, ${up ? 'up' : 'down'}"><polyline fill="none" stroke="${up ? 'var(--up)' : 'var(--down)'}" stroke-width="1.3" stroke-linejoin="round" stroke-linecap="round" points="${a.map((x, i) => (i / n * (W - 2) + 1).toFixed(1) + ',' + (1 + (hi - x) / ((hi - lo) || 1) * (H - 2)).toFixed(1)).join(' ')}"/></svg>`;
  };
  const countMark = (n: number) => `<span class="cnt8 ${n ? '' : 'z'}" aria-hidden="true">${'<i></i>'.repeat(Math.min(n, 10))}${n > 10 ? `<em>+${n - 10}</em>` : ''}<b>${n}</b></span>`;
  const dayTag = (d: number | null) => (d === 1 ? '<span class="tag new">New</span>' : `<span class="tag">Day ${d ?? '—'}</span>`);
  const flagTag = (r: Row) => (r.flag ? `<span class="tag warn" title="${esc(r.flag)}">Outlier</span>` : '');

  function dropdown(btn: HTMLElement, items: any[], onPick: (v: string) => void, opts: { w?: number } = {}) {
    closeMenus();
    const r = btn.getBoundingClientRect(), m = document.createElement('div') as HTMLDivElement & { _btn?: HTMLElement };
    m.className = 'pop menu'; m.setAttribute('role', 'listbox');
    m.style.cssText = `position:fixed;left:${Math.max(8, Math.min(r.left, innerWidth - (opts.w || 260) - 12))}px;top:${r.bottom + 6}px;width:${opts.w || 260}px;max-height:${Math.max(160, innerHeight - r.bottom - 24)}px;overflow:auto;z-index:var(--z-pop)`;
    m.innerHTML = items.map(it => it.title ? `<div class="menu-title">${it.title}</div>` : it.note ? `<div class="menu-note">${it.note}</div>`
      : `<button class="menu-item ${it.on ? 'on' : ''}" role="option" aria-selected="${!!it.on}" ${it.disabled ? 'disabled' : ''} data-v="${esc(it.v)}"><span>${it.label}</span>${it.right ? `<span class="mr">${it.right}</span>` : ''}</button>`).join('');
    document.body.appendChild(m); btn.setAttribute('aria-expanded', 'true');
    const os = $$<HTMLButtonElement>('.menu-item:not([disabled])', m);
    (os.find(b => b.classList.contains('on')) || os[0])?.focus();
    m.addEventListener('click', e => { const b = (e.target as HTMLElement).closest('.menu-item') as HTMLButtonElement; if (!b || b.disabled) return; closeMenus(); onPick(b.dataset.v); btn.focus() });
    m.addEventListener('keydown', e => { const i = os.indexOf(document.activeElement as HTMLButtonElement); if (e.key === 'ArrowDown') { e.preventDefault(); os[(i + 1) % os.length].focus() } if (e.key === 'ArrowUp') { e.preventDefault(); os[(i - 1 + os.length) % os.length].focus() } if (e.key === 'Escape') { closeMenus(); btn.focus() } });
    m._btn = btn;
  }
  function closeMenus() { $$<any>('.menu').forEach(m => { m._btn?.setAttribute('aria-expanded', 'false'); m.remove() }) }
  document.addEventListener('mousedown', e => { const t = e.target as HTMLElement; if (!t.closest('.menu') && !t.closest('[aria-haspopup]')) closeMenus() });
  addEventListener('resize', closeMenus);
  // QA 2026-11-14: scrolling a long menu (about 68 stock lists) must not close it; any other scroll does
  addEventListener('scroll', e => { const t = e.target as Element; if (!(t instanceof Element && t.closest('.menu'))) closeMenus() }, true);

  function uniMenu(btn: HTMLElement, after: () => void) {
    const of = (kind: string) => meta.lists.filter(l => l.kind === kind).map(l => ({ v: l.key, label: esc(l.name || l.code), on: l.key === ST.uni }));
    dropdown(btn, [{ v: 'all', label: 'All stocks', on: ST.uni === 'all' }, { title: 'Index' }, ...of('INDEX'), { title: 'Group' }, ...of('KONGLO'),
      { note: 'Narrows the results shown. Ranks across stocks (S2, S3) stay computed on every stock that passes the gate.' }], v => { ST.uni = v; after() }, { w: 270 });
  }
  const uniBtn = (cls = 'btn uni', compact = false) => { const u = uniLabel(); return `<button class="${cls}" data-act="uni" aria-haspopup="listbox" aria-expanded="false" aria-label="Universe: ${esc(u[0])}">${compact ? '' : ic('search')}<span class="uv"><b>${esc(u[0])}</b>${compact ? '' : `<span>${u[1]}</span>`}</span>${ic('chev')}</button>` };
  const seg = (key: string, opts: [string | number, string, string?][], lbl: string) => `<div class="f"><span class="lbl" id="${key}L">${lbl}</span><div class="seg sm" role="radiogroup" aria-labelledby="${key}L" data-seg="${key}">${opts.map(([v, l, t]) => `<button role="radio" aria-checked="${String((ST as any)[key]) === String(v)}" class="${String((ST as any)[key]) === String(v) ? 'on' : ''}" data-v="${v}"${t ? ` title="${esc(t)}"` : ''}>${l}</button>`).join('')}</div></div>`;
  const statusPills = () => {
    const behind = !!(days.prices_through && days.broker_through && days.broker_through < days.prices_through);
    return `<span class="pill" title="Daily prices loaded to EDGE"><span class="dot"></span>Prices to ${dayLabel(days.prices_through)}</span><span class="pill ${behind ? 'warn' : ''}" title="Broker data arrives after the price data. Results use the last date both sources have."><span class="dot"></span>Broker data to ${dayLabel(days.broker_through)}</span>`;
  };
  const dateBtn = () => `<button class="btn" data-act="date" aria-haspopup="listbox" aria-expanded="false">${ic('cal')}Results for ${dayLabel(ST.date)}${ic('chev')}</button>`;
  function bindDate(after: () => void) {
    const b = $('[data-act=date]');
    if (b) b.onclick = e => dropdown(e.currentTarget as HTMLElement, [...[...days.boards].reverse().map(d => ({ v: d, label: `${dayLabel(d)} · after close`, on: d === ST.date })),
      { note: 'A date has results once prices and broker data for it are both loaded.' }], v => { pickDate(v).then(after, e => toast((e as Error).message)) }, { w: 300 });
  }
  async function pickDate(d: string) {
    if (d === ST.date) return;
    board = await get<Board>(`radar-board-${d}`); ST.date = d; F = stockFacts(meta, board); ST.detail.day = 0;
  }

  /* ---------- board (R10 renderRadar / drawKanban) ---------- */
  function renderRadar() {
    document.title = 'EDGE — Radar';
    view.innerHTML = `<div class="head"><div><h1>Radar</h1><p class="muted">Stocks picked up by the screener library, and which filters found them. Candidates to study, not buy or sell signals.</p></div>
     <div class="actions">${statusPills()}${dateBtn()}</div></div>
    <div class="card bar-t">${uniBtn()}
     ${seg('gate', [['broad', 'Broad', `Drops the 50% of stocks with the smallest buying over 5 sessions. On ${dayLabel(ST.date, false)}: at least Rp ${gateCut('broad')}B over 5 sessions`], ['liquid', 'Liquid', `Drops the 80% of stocks with the smallest buying over 5 sessions. On ${dayLabel(ST.date, false)}: at least Rp ${gateCut('liquid')}B over 5 sessions`]], 'Gate')}
     <span class="gh muted">≥ Rp ${gateCut(ST.gate)}B / 5 days</span>
     ${seg('lv', LEVEL_LABEL.map((l, i) => [i, l] as [number, string]), 'Level')}
     ${seg('show', [['all', 'All hits'], ['new', 'New today'], ['multi', 'In 2+ filters']], 'Show')}
     <span class="sp"></span><label class="srch">${ic('search')}<input id="rq" placeholder="Find a ticker in results" value="${esc(ST.q)}" aria-label="Find a ticker in results"></label></div>
    <div class="kb" id="kb"></div>`;
    drawKanban();
    ($('[data-act=uni]', view) as HTMLElement).onclick = e => uniMenu(e.currentTarget as HTMLElement, renderRadar);
    bindDate(renderRadar);
    $$('[data-seg]', view).forEach(s => (s.onclick = e => { const b = (e.target as HTMLElement).closest('button') as HTMLButtonElement; if (!b) return; (ST as any)[s.dataset.seg] = s.dataset.seg === 'lv' ? +b.dataset.v : b.dataset.v; renderRadar(); ($(`[data-seg=${s.dataset.seg}] .on`) as HTMLElement)?.focus() }));
    const q = $<HTMLInputElement>('#rq', view);
    q.oninput = () => { ST.q = q.value.trim().toLowerCase(); drawKanban() };
    q.onkeydown = e => { if (e.key === 'Escape') { q.value = ''; ST.q = ''; drawKanban() } };
  }
  function drawKanban() {
    const kb = $('#kb'); if (!kb) return;
    let tot = 0;
    const sets = hitSets(), di = dateIndex();
    kb.innerHTML = cols.map(c => {
      const f = filterOf(c);
      const hs = lists(board, f, ST.lv, ST.gate, keepUni).hits.filter(h => {
        if (ST.show === 'new' && h.run !== 1) return false;
        if (ST.show === 'multi' && !alsoIn(c, h.t, sets).length) return false;
        if (ST.q && !(h.t + ' ' + F.name(h.t)).toLowerCase().includes(ST.q)) return false;
        return true;
      });
      const h = counts(days, f, ST.lv, ST.gate, di, 20), d = h.length > 1 ? h[h.length - 1] - h[h.length - 2] : 0;
      tot += hs.length;
      return `<section class="card kc ${c.id === ST.last ? 'on' : ''}" aria-label="${esc(c.label)} ${esc(f.name)}"><button class="kh" data-open="${esc(c.id)}" aria-label="Open ${esc(c.label)}, ${esc(f.name)}, ${hs.length} stocks"><div style="display:flex;align-items:center;gap:var(--s-3)"><b>${esc(c.label)}</b><span class="grow" style="flex:1"></span>${countMark(hs.length)}</div><small>${esc(f.name)}${c.variants.length > 1 ? ` · ${esc(f.variant)}` : ''}</small>
       <div style="display:flex;align-items:center;justify-content:space-between;margin-top:var(--s-3)">${sparkBars(h, 70, 18)}<span class="${isDefault() ? cl(d) : ''}" style="font-size:var(--fs-xs)">${f.own_levels && ST.lv !== 1 ? '<span class="muted" title="S8 has its own levels: Strong and Watch">own levels</span>' : isDefault() ? `${d >= 0 ? '+' : '−'}${Math.abs(d)} vs yday` : '<span class="muted">filtered</span>'}</span></div></button>
      <div class="kl">${hs.map(hr => {
        const o = alsoIn(c, hr.t, sets), lvl = f.own_levels && !hr.strong ? '<span class="tag" title="Large and unusual, below the top 5% of its own history">Watch</span>' : '';
        return `<button class="ki" data-open="${esc(c.id)}" data-stock="${esc(hr.t)}" aria-label="${esc(hr.t)}, ${sg(F.chg(hr.t))}"><div class="t"><b>${esc(hr.t)}</b><span class="${cl(F.chg(hr.t))}">${sg(F.chg(hr.t))}</span></div><div class="t2">${dayTag(hr.run)}${lvl}${o.length ? `<span class="tag" title="Also in ${o.map(g => g.label).join(', ')}">+${o.length}</span>` : ''}${flagTag(hr)}<span class="ksp" title="Price, last 20 sessions">${priceSpark(hr.t)}</span></div></button>`;
      }).join('') || `<p class="empty-col">${emptyCol()}</p>`}</div></section>`;
    }).join('');
    if (!tot) kb.insertAdjacentHTML('beforeend', `<div class="kb-empty card"><b>No stocks match these settings.</b><span class="muted">Try All stocks, the Broad gate or the Loose level.</span><button class="btn sm" id="rst">Reset settings</button></div>`);
    const r = $('#rst'); if (r) r.onclick = () => { Object.assign(ST, { uni: 'all', gate: 'broad', lv: 1, show: 'all', q: '' }); renderRadar() };
    $$('[data-open]', kb).forEach(b => (b.onclick = () => go(`#/filter/${b.dataset.open}${b.dataset.stock ? '?s=' + b.dataset.stock : ''}`)));
  }
  const emptyCol = () => ST.q ? 'No match for this search.' : ST.uni !== 'all' ? `None in ${esc(uniLabel()[0])} today.` : ST.show !== 'all' ? 'None with this view.' : `None pass at the ${LEVEL_LABEL[ST.lv]} level.`;

  /* ---------- filter detail (R10 renderDetail) ---------- */
  function renderDetail(colId: string, stock: string | null) {
    const c = cols.find(x => x.id === colId);
    if (!c) return renderMissing(`Filter ${esc(colId)}`);
    if (ST.detail.col !== colId) { ST.detail.day = 0; ST.detail.q = ''; ST.detail.col = colId }
    ST.last = colId;
    const f = filterOf(c);
    document.title = `EDGE — Radar · ${c.label}`;
    const C = conditions(meta, f, ST.lv), own = ownColumns(c.id, F);
    const qn = ST.detail.q.trim().toLowerCase(), keep = (r: Row) => !qn || (r.t + ' ' + F.name(r.t)).toLowerCase().includes(qn);
    const L = lists(board, f, ST.lv, ST.gate, keepUni);
    const rows = L.hits.filter(keep), nr = L.near.filter(keep);
    if (ST.detail.sort === 'new') rows.sort((a, b) => (a.run ?? 0) - (b.run ?? 0) || (b.sort ?? -Infinity) - (a.sort ?? -Infinity));
    const sel = rows.find(r => r.t === stock) || nr.find(r => r.t === stock) || rows[0];
    const sets = hitSets();
    view.innerHTML = `<div class="head"><div><p class="crumb"><button class="lk" data-go="#/radar">${ic('chevl')}Radar</button></p><h1 style="display:flex;align-items:center;gap:var(--s-5)">${esc(c.label)} · ${esc(f.name)}</h1><p class="muted">${esc(f.question)}</p></div>
     <div class="actions">${statusPills()}${dateBtn()}<button class="btn" data-act="follow">${ic('saved')}Follow</button></div></div>
    <div class="note-read card">${ic('info')}<span><b>How to read it.</b> ${esc(f.warning)} ${f.own_levels ? 'S8 uses its own levels, so the Level switch does not change it.' : ''}</span></div>
    <div class="top3"><div class="card"><div class="card-h chart-h"><h3>Stocks found per day</h3><span class="lg"><i class="sw bar"></i>Stocks found (left)</span><span class="lg"><i class="sw ln"></i>IHSG (right)</span><span class="grow"></span><span class="hint">Last ${days.dates.length} sessions · select a bar to see that day</span></div><div class="hist" id="h60"></div></div>
     <div class="card tdy" id="tdy"></div></div>
    <div class="dg"><div class="card ct"><div class="ct-head"><div class="card-h"><h3>Candidates</h3><span class="hint">${qn ? `${rows.length} of ${L.hits.length}` : rows.length} stocks${f.own_levels ? '' : ` meet all ${C.length}`}${nr.length ? ` · ${nr.length} near miss${nr.length > 1 ? 'es' : ''}` : ''} · ${LEVEL_LABEL[ST.lv]} · ${ST.gate === 'broad' ? 'Broad' : 'Liquid'} gate</span></div>
      <div class="ct-r">${c.variants.length > 1 ? `<div class="sortg"><span class="lbl" id="dmL">Change in</span><div class="seg sm" role="radiogroup" aria-labelledby="dmL" data-dseg="variant">${c.variants.map(v => `<button role="radio" aria-checked="${v.id === f.id}" class="${v.id === f.id ? 'on' : ''}" data-v="${v.id}">${esc(v.variant)}</button>`).join('')}</div></div>` : ''}
       <label class="srch">${ic('search')}<input id="cq" placeholder="Find a ticker or name" value="${esc(ST.detail.q)}" aria-label="Find a candidate" autocomplete="off"></label>${uniBtn('btn sm uni', true)}
       <div class="sortg"><span class="lbl" id="soL">Sort</span><div class="seg sm" role="radiogroup" aria-labelledby="soL" data-dseg="sort">${[['own', 'By ' + f.sort_label], ['new', 'New first']].map(([v, l]) => `<button role="radio" aria-checked="${ST.detail.sort === v}" class="${ST.detail.sort === v ? 'on' : ''}" data-v="${v}">${esc(l)}</button>`).join('')}</div></div></div></div>
      <div class="conds">${C.map(r => `<span><i>${esc(r.cond)}</i>${esc(r.label)}</span>`).join('')}</div>
      <div class="tbl-wrap"><table class="tbl" id="tb"></table></div></div>
     <div class="card pv" id="pv" aria-live="polite"></div></div>`;
    const dots = (r: Row) => { const m = metBits(r.met, C.length); return `<span class="dots" aria-label="${m.filter(Boolean).length} of ${m.length} conditions met">${m.map((x, k) => `<i class="${x ? '' : 'off'}" title="${esc(C[k]?.label)}: ${x ? 'met' : 'not met'}">${COND_KEYS[k]}</i>`).join('')}</span>` };
    const also = (t: string) => alsoIn(c, t, sets).map(g => `<span class="tag">${esc(g.label)}</span>`).join('') || '<span class="muted">—</span>';
    const row = (r: Row, nm = false) => `<tr tabindex="0" data-s="${esc(r.t)}" class="${r === sel ? 'on' : ''} ${nm ? 'nm' : ''}" aria-selected="${r === sel}"><td class="l tk"><b>${esc(r.t)}</b><small>${esc(F.name(r.t))}</small></td><td>${dots(r)}</td><td class="${nm ? '' : cl(F.chg(r.t))}">${sg(F.chg(r.t))}</td>
      ${own.map(oc => `<td class="${oc[2] && !nm ? oc[2](r.t, ST.gate) : ''}">${oc[1](r.t, ST.gate, r)}</td>`).join('')}<td class="l">${nm ? '<span class="tag">Near miss</span>' : dayTag(r.run)}${flagTag(r)}</td><td class="l">${also(r.t)}</td></tr>`;
    $('#tb').innerHTML = `<thead><tr><th class="l">Stock</th><th>Conditions</th><th>1D</th>${own.map(oc => `<th>${oc[0]}</th>`).join('')}<th class="l">In radar</th><th class="l">Also in</th></tr></thead><tbody>` +
      (rows.map(r => row(r)).join('') || `<tr><td colspan="${own.length + 5}" class="l muted" style="height:80px;text-align:center">${qn ? `No candidate matches “${esc(ST.detail.q.trim())}”.` : `No stock passes at the ${LEVEL_LABEL[ST.lv]} level with this gate and universe.`}</td></tr>`) +
      (nr.length ? `<tr class="sep"><td colspan="${own.length + 5}" class="l">Near misses · all but one condition met</td></tr>` + nr.map(r => row(r, true)).join('') : '') + '</tbody>';
    $$('#tb tr[data-s]').forEach(tr => {
      const pick = () => { history.replaceState(null, '', `#/filter/${encodeURIComponent(colId)}?s=${encodeURIComponent(tr.dataset.s)}`); renderDetail(colId, tr.dataset.s); ($(`#tb tr[data-s="${tr.dataset.s}"]`) as HTMLElement)?.focus() };
      tr.onclick = pick;
      tr.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pick() } if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); let n = (e.key === 'ArrowDown' ? tr.nextElementSibling : tr.previousElementSibling) as HTMLElement; while (n && !n.dataset.s) n = (e.key === 'ArrowDown' ? n.nextElementSibling : n.previousElementSibling) as HTMLElement; n?.focus() } };
    });
    drawToday(c, f, L, sets);
    drawHist(c, f);
    void withFile(f, file => { if (ST.detail.col === colId) { drawDay(c, f, file); preview(c, f, sel, file) } });
    preview(c, f, sel, fileCache.get(f.id) || null);
    ($('[data-act=follow]') as HTMLElement).onclick = () => toast('Coming soon');
    ($('[data-go]') as HTMLElement).onclick = () => go('#/radar');
    bindDate(() => renderDetail(colId, sel?.t || null));
    const cq = $<HTMLInputElement>('#cq');
    cq.oninput = () => { const p = cq.selectionStart; ST.detail.q = cq.value; renderDetail(colId, sel?.t || null); const n = $<HTMLInputElement>('#cq'); n.focus(); n.setSelectionRange(p, p) };
    ($('[data-act=uni]') as HTMLElement).onclick = e => uniMenu(e.currentTarget as HTMLElement, () => renderDetail(colId, stock));
    $$('[data-dseg]', view).forEach(s => (s.onclick = e => { const b = (e.target as HTMLElement).closest('button') as HTMLButtonElement; if (!b) return; if (s.dataset.dseg === 'variant') ST.variant = b.dataset.v; else ST.detail.sort = b.dataset.v as any; renderDetail(colId, sel?.t || null); ($(`[data-dseg=${s.dataset.dseg}] .on`) as HTMLElement)?.focus() }));
  }

  async function withFile(f: FilterMeta, then: (file: FilterFile) => void) {
    if (fileCache.has(f.id)) return then(fileCache.get(f.id));
    try {
      const file = await get<FilterFile>(`radar-f-${f.id.toLowerCase()}`);
      fileCache.set(f.id, file); then(file);
    } catch (e) {
      const m = `<span class="muted">${esc((e as Error).message)}</span>`;
      const p = $('#dayp'); if (p) p.innerHTML = m;
      const pv = $('#pv .sec p.muted'); if (pv) pv.outerHTML = `<p>${m}</p>`;
    }
  }

  function drawHist(c: Column, f: FilterMeta, noDay = false) {
    const el = $('#h60'); if (!el) return;
    const N = days.dates.length, H60 = counts(days, f, ST.lv, ST.gate, N - 1, N), IH = days.ihsg.map(v => v ?? NaN);
    const cs = getComputedStyle(el), W = Math.round(el.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight)) || 600,
      H = Math.max(112, Math.round(el.clientHeight - parseFloat(cs.paddingBottom))), m = Math.max(1, ...H60), PL = 28, PR = 46, bw = (W - PL - PR) / Math.max(1, N);
    const selI = dateIndex() - ST.detail.day, valid = IH.filter(v => !isNaN(v)),
      lo = (valid.length ? Math.min(...valid) : 0) - 40, hi = (valid.length ? Math.max(...valid) : 1) + 40, yI = (v: number) => 6 + (1 - (v - lo) / (hi - lo)) * (H - 24);
    let s = `<line x1="${PL}" x2="${W - PR}" y1="${H - 18}" y2="${H - 18}" stroke="var(--border)"/>`;
    const most = Math.max(2, Math.floor((H - 26) / 22)), step = Math.max(1, niceStep(m, most));   // QA: no overlapping labels
    for (let v = 0; v <= m; v += step) s += `<text x="20" y="${H - 14 - v / m * (H - 26)}" text-anchor="end" font-size="10.5" fill="var(--text-3)">${v}</text>`;
    if (valid.length) { const ist = niceStep(Math.max(...valid) - Math.min(...valid), most); for (let t = Math.ceil(Math.min(...valid) / ist) * ist; t <= Math.max(...valid); t += ist) s += `<text x="${W - PR + 8}" y="${yI(t) + 3.5}" font-size="10.5" fill="var(--text-3)">${t.toLocaleString('en-US')}</text>` }
    H60.forEach((v, i) => { const h = v / m * (H - 26); s += `<rect x="${PL + i * bw + (bw > 3 ? 1 : 0)}" y="${H - 18 - h}" width="${Math.max(1, bw - (bw > 3 ? 2 : .5))}" height="${h}" rx="${bw > 3 ? 1 : 0}" fill="${i === selI ? 'var(--text)' : i === dateIndex() ? 'var(--gray-500)' : 'var(--gray-300)'}"/>` });
    const pts = IH.map((v, i) => (isNaN(v) ? null : `${(PL + (i + .5) * bw).toFixed(1)},${yI(v).toFixed(1)}`)).filter(Boolean).join(' ');
    if (pts) s += `<polyline fill="none" stroke="var(--ihsg)" stroke-width="1.5" stroke-linejoin="round" points="${pts}"/>`;
    H60.forEach((v, i) => { s += `<rect class="hb" data-i="${i}" x="${PL + i * bw}" y="0" width="${bw}" height="${H - 18}" fill="transparent"><title>${dayLabel(days.dates[i])} · ${v} stocks</title></rect>` });
    let lx = -99;
    days.dates.forEach((dd, i) => { if (i === 0 || monthOf(dd) !== monthOf(days.dates[i - 1])) { const x = PL + i * bw; if (x - lx > 36) { s += `<text x="${x}" y="${H - 2}" font-size="10.5" fill="var(--text-3)">${monthOf(dd)}</text>`; lx = x } } });
    el.innerHTML = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="Stocks found per day and IHSG. Use left and right arrows to change day.">${s}</svg>`;
    el.tabIndex = 0;
    const back = (i: number) => { ST.detail.day = Math.max(0, Math.min(dateIndex(), dateIndex() - i)) };
    $$('.hb', el).forEach(r => (r.onclick = () => { back(+r.dataset.i); drawHist(c, f) }));
    el.onkeydown = e => { if (e.key === 'ArrowLeft' && ST.detail.day < dateIndex()) { e.preventDefault(); ST.detail.day++; drawHist(c, f); el.focus() } if (e.key === 'ArrowRight' && ST.detail.day > 0) { e.preventDefault(); ST.detail.day--; drawHist(c, f); el.focus() } };
    const anyEl = el as any;
    if (!anyEl._ro) { anyEl._ro = new ResizeObserver(() => { const sv = $('svg', el); const c2 = getComputedStyle(el), w = Math.round(el.clientWidth - parseFloat(c2.paddingLeft) - parseFloat(c2.paddingRight)); if (sv && +sv.getAttribute('width') !== w) drawHist(c, f, true) }); anyEl._ro.observe(el) }
    if (!noDay && fileCache.has(f.id)) drawDay(c, f, fileCache.get(f.id));
  }

  function drawDay(c: Column, f: FilterMeta, file: FilterFile) {
    const p = $('#dayp'); if (!p) return;
    const k = ST.detail.day, di = dateIndex() - k, d = days.dates[di], today = k === 0;
    const fi = file.dates.indexOf(d), mem = fi >= 0 ? membersOn(file, f, ST.lv, ST.gate, fi) : new Map<string, number>();
    const now = new Set(lists(board, f, ST.lv, ST.gate).hits.map(h => h.t));
    const ts = [...mem.keys()].filter(keepUni).sort();
    p.innerHTML = `<div class="dh"><b>${dayLabel(d)}${today ? ' · result date' : ''}</b><span class="muted">${plural(ts.length, 'stock')}</span>${today ? '' : `<button class="lk" data-today>Back to ${dayLabel(ST.date, false)}</button>`}</div>
     <div class="dchips">${ts.map(t => `<button class="tkc ${now.has(t) ? (today && mem.get(t) === 1 ? 'nw' : '') : 'gone'}" data-t="${esc(t)}">${esc(t)}</button>`).join('') || '<span class="muted">No stocks this day.</span>'}</div>${today ? '' : '<p class="dleg"><span class="tkc">BBCA</span> still in on the result date <span class="tkc gone">BBCA</span> no longer in</p>'}`;
    const bt = $('[data-today]', p) as HTMLElement; if (bt) bt.onclick = () => { ST.detail.day = 0; drawHist(c, f) };
    $$('.dchips .tkc', p).forEach(ch => (ch.onclick = () => { const t = ch.dataset.t; if (!now.has(t)) { toast(`${t} is not in ${c.label} on ${dayLabel(ST.date, false)}, so it has no row in Candidates.`); return } history.replaceState(null, '', `#/filter/${encodeURIComponent(c.id)}?s=${encodeURIComponent(t)}`); renderDetail(c.id, t) }));
  }

  function drawToday(c: Column, f: FilterMeta, L: ReturnType<typeof lists>, sets: Map<string, Set<string>>) {
    const el = $('#tdy'); if (!el) return;
    const hs = L.hits, nw = hs.filter(h => h.run === 1), cont = hs.filter(h => (h.run ?? 0) > 1), C = conditions(meta, f, ST.lv);
    const avg = cont.length ? cont.reduce((a, h) => a + (h.run ?? 0), 0) / cont.length : 0;
    const ov = cols.filter(g => g !== c).map(g => [g, hs.filter(h => sets.get(g.id)?.has(h.t)).length] as [Column, number]).sort((a, b) => b[1] - a[1])[0];
    const why = (k: string | null) => k === 'gate' ? 'Fell out of the gate' : k === 'no_data' ? 'No Regular trade on the date' : `${esc(C.find(r => r.cond === k)?.label || k)} no longer met`;
    const newest = ST.date === days.boards[days.boards.length - 1];
    el.innerHTML = `<div class="card-h"><h3>${newest ? 'Today' : dayLabel(ST.date, false)} in ${esc(c.label)}</h3><span class="hint">vs the previous session</span></div>
     <div class="hs"><div><div class="v">${nw.length}</div><div class="l">entered</div></div><div><div class="v">${cont.length}</div><div class="l">stayed · avg ${avg.toFixed(1)} days</div></div><div><div class="v">${L.left.length}</div><div class="l">left</div></div></div>
     <div class="tdl"><span class="muted">Left</span><span class="tk3">${L.left.map(o => `<span class="tkc out" title="${why(o.why)}">${esc(o.t)}<i>${o.why && o.why.length === 1 ? o.why : '·'}</i></span>`).join('') || '<span class="muted">none</span>'}</span></div>
     <div class="tdl"><span class="muted">Most overlap</span><span>${ov && ov[1] ? `<b>${esc(ov[0].label)}</b> · ${ov[1]} of ${hs.length} stocks also there` : '<span class="muted">none</span>'}</span></div>
     <div class="dayp" id="dayp" aria-live="polite"><span class="ml-loading" role="status"><span class="ml-spin" aria-hidden="true"></span>Loading the filter's history</span></div>`;
  }

  function preview(c: Column, f: FilterMeta, sel: Row | undefined, file: FilterFile | null) {
    const pv = $('#pv'); if (!pv) return;
    if (!sel) { pv.innerHTML = `<div class="card-h"><h3>No stock selected</h3></div><p class="muted" style="padding:0 var(--s-8) var(--s-8)">Select a candidate to see when ${c.label} found it.</p>`; return }
    const t = sel.t, close = F.close(t), chg = F.chg(t);
    let chart = '<p class="muted">Loading the filter\'s history…</p>';
    if (file) {
      const di = file.dates.indexOf(ST.date), N = di + 1;
      const len = Math.min(N, { '3M': 63, '6M': 126, '1Y': 250 }[ST.detail.prev]), I0 = N - len;
      const all = closesOf(file, t).slice(0, N), cc = all.slice(I0);
      const eps = runs(file, f, ST.lv, ST.gate, t).filter(e => e[0] <= di).map(e => [e[0], Math.min(e[1], di)] as [number, number]);
      const vis = eps.filter(e => e[1] >= I0), act = vis.reduce((a, e) => a + e[1] - Math.max(e[0], I0) + 1, 0);
      const valid = cc.filter((x): x is number => x != null);
      if (valid.length >= 2) {
        const pad = 16, W = Math.round(pv.clientWidth - 2 * pad) || 330, PL = 38, H = 96, BH = 22, lo = Math.min(...valid), hi = Math.max(...valid), bw = (W - PL) / len,
          xf = (k: number) => PL + (k + .5) * bw, yf = (x: number) => 4 + (hi - x) / ((hi - lo) || 1) * (H - 8);
        const raw = (hi - lo) / 3, mag = Math.pow(10, Math.floor(Math.log10(raw || 1))), stp = Math.max(1, [1, 2, 2.5, 5, 10].map(n => n * mag).find(x => x >= raw) || 1);
        let g = '';
        for (let x = Math.ceil(lo / stp) * stp; x <= hi; x += stp) g += `<text x="${PL - 6}" y="${(yf(x) + 3.5).toFixed(1)}" text-anchor="end" font-size="10" fill="var(--text-3)">${px(x)}</text>`;
        vis.forEach(e => { const a = Math.max(e[0], I0); g += `<rect x="${PL + (a - I0) * bw}" y="0" width="${(e[1] - a + 1) * bw}" height="${H}" fill="var(--gray-100)"/>` });
        g += `<polyline fill="none" stroke="var(--text)" stroke-width="1.3" stroke-linejoin="round" points="${cc.map((x, k) => (x == null ? null : xf(k).toFixed(1) + ',' + yf(x).toFixed(1))).filter(Boolean).join(' ')}"/><rect x="${PL}" y="${H + 6}" width="${W - PL}" height="${BH}" rx="3" fill="var(--gray-50)"/>`;
        vis.forEach(e => { const a = Math.max(e[0], I0); g += `<rect x="${PL + (a - I0) * bw}" y="${H + 9}" width="${Math.max(2, (e[1] - a + 1) * bw)}" height="${BH - 6}" fill="var(--text)"/>` });
        let lx = -99;
        for (let k = 0; k < len; k++) { const i = I0 + k; if (k === 0 || monthOf(file.dates[i]) !== monthOf(file.dates[i - 1])) { const x = PL + k * bw; if (x - lx > 40 && x < W - 18) { g += `<text x="${x}" y="${H + BH + 20}" font-size="10" fill="var(--text-3)">${monthOf(file.dates[i])}</text>`; lx = x } } }
        const recent = vis.slice(-3).reverse().map(e => { const L2 = e[1] - e[0] + 1; return `<div class="kv2"><span>${dayLabel(file.dates[e[0]], false)}${L2 > 1 ? ' – ' + dayLabel(file.dates[e[1]], false) : ''}</span><b>${e[1] === di && sel.status === 'hit' ? '<span class="tag new">Active · day ' + (sel.run ?? L2) + '</span>' : L2 + ' day' + (L2 > 1 ? 's' : '')}</b></div>` }).join('');
        chart = `<svg width="${W}" height="${H + BH + 24}" viewBox="0 0 ${W} ${H + BH + 24}" role="img" aria-label="Price of ${t} with the days ${c.label} found it">${g}</svg>
          <div class="kv2" style="margin-top:var(--s-3)"><span><b style="color:var(--text)">${act}</b> ${act === 1 ? 'day' : 'days'} found · <b style="color:var(--text)">${vis.length}</b> ${vis.length === 1 ? 'run' : 'runs'} in ${ST.detail.prev}</span></div><div style="margin-top:var(--s-3)">${recent}</div>`;
      } else chart = `<p class="muted">${t} has no price line in ${c.label}'s history${sel.status === 'near' ? ' (a near miss is not in the filter yet)' : ''}.</p>`;
    }
    pv.innerHTML = `<div class="card-h"><h3>${esc(t)}</h3><span class="hint">${esc(F.name(t))}</span><span class="grow"></span><b style="font-weight:var(--fw-semibold)">${px(close)}</b><span class="${cl(chg)}" style="font-size:var(--fs-12)">${sg(chg)}</span></div>
     ${sel.flag ? `<div class="flagnote">${ic('info')}<span>${esc(sel.flag)}. Check for a block trade or corporate action before reading the flow.</span></div>` : ''}
     <div class="sec"><div style="display:flex;align-items:center;gap:var(--s-4);margin-bottom:var(--s-4)"><span class="eyebrow2" style="margin:0">When ${esc(c.label)} found it</span><span style="flex:1"></span><div class="seg sm" role="radiogroup" aria-label="Range" data-pv>${['3M', '6M', '1Y'].map(r => `<button role="radio" aria-checked="${ST.detail.prev === r}" class="${ST.detail.prev === r ? 'on' : ''}" data-v="${r}">${r}</button>`).join('')}</div></div>${chart}</div>
     <div class="acts"><button class="btn sm primary" data-act="term">Open ${esc(t)} in Terminal</button></div>`;
    ($('[data-act=term]', pv) as HTMLElement).onclick = () => openTerminal(t);
    ($('[data-pv]', pv) as HTMLElement).onclick = e => { const b = (e.target as HTMLElement).closest('button') as HTMLButtonElement; if (!b) return; ST.detail.prev = b.dataset.v as any; preview(c, f, sel, fileCache.get(f.id) || null) };
  }

  /* the Terminal opens on the stock: the symbol it reads at start (ml.symbol, as the Screener) and the shell's page
     switch (edge-nav; the shell accepts it only from its own frames, ERRORS M425) */
  function openTerminal(t: string) {
    try { localStorage.setItem('ml.symbol', t) } catch { /* storage off: the Terminal opens on its own symbol */ }
    try { parent.postMessage({ type: 'edge-nav', route: 'terminal' }, location.origin) } catch { /* not framed */ }
    if (parent === window) toast(`${t} is set for the Terminal. Open the Terminal page to see it.`);
  }

  function renderMissing(n: string) {
    document.title = 'EDGE — Radar';
    view.innerHTML = `<div class="missing card"><h1>${n}</h1><p class="muted">The Radar has no such page.</p><button class="btn primary" data-go="#/radar">Go to Radar</button></div>`;
    ($('[data-go]', view) as HTMLElement).onclick = () => go('#/radar');
  }
  function renderError(e: unknown) {
    const m = e instanceof RadarError ? e.message : 'The Radar could not be shown. Reload the page; if it stays, the Radar data is not published yet.';
    view.innerHTML = `<div class="boot"><span class="err">${ic('info')}</span><span>${esc(m)}</span><button class="btn sm" data-act="retry">Try again</button></div>`;
    ($('[data-act=retry]', view) as HTMLElement).onclick = () => void boot();
  }

  function go(h: string) { if (location.hash === h) route(); else location.hash = h }
  function route() {
    closeMenus();
    const h = location.hash || '#/radar', [path, qs] = h.slice(1).split('?'), p = new URLSearchParams(qs || ''), seg2 = path.split('/').filter(Boolean);
    if (seg2[0] === 'filter') renderDetail(seg2[1], p.get('s'));
    else if (!seg2.length || seg2[0] === 'radar') renderRadar();
    else renderMissing('Page not found');
    view.scrollTop = 0;
  }

  async function boot() {
    view.innerHTML = `<div class="boot"><span class="ml-loading" role="status"><span class="ml-spin" aria-hidden="true"></span>Loading the Radar</span></div>`;
    try {
      index = await files.index();
      [meta, days] = await Promise.all([get<Meta>('radar-meta'), get<Days>('radar-days')]);
      cols = columns(meta);
      ST.variant = cols.find(c => c.variants.length > 1)?.variants[0].id || '';
      if (!days.boards.length) {
        view.innerHTML = `<div class="boot"><span>Results are not ready yet: the Radar has no result date published. They appear after the next broker update.</span></div>`;
        return;
      }
      ST.date = days.boards[days.boards.length - 1];
      board = await get<Board>(`radar-board-${ST.date}`);
      F = stockFacts(meta, board);
    } catch (e) { renderError(e); return }
    route();
  }
  addEventListener('hashchange', route);
  return { boot, rerender: () => (meta ? route() : undefined) };
}
